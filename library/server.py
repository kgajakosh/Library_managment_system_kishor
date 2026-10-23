import argparse
import csv
import hmac
import io
import json
import os
import secrets
import sqlite3
import tempfile
import time
from http.cookies import SimpleCookie
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse
from . import db

STATIC=Path(__file__).parent/'static'
MAX_BODY=32*1024*1024
SESSION_TTL=8*60*60
LOGIN_WINDOW=15*60
MAX_LOGIN_ATTEMPTS=5
SESSIONS={}
LOGIN_ATTEMPTS={}

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs): super().__init__(*args,directory=str(STATIC),**kwargs)
    def end_headers(self):
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.send_header('Cache-Control','no-store')
        super().end_headers()
    def output(self,body,status=200,content_type='application/json',filename=None):
        if not isinstance(body,bytes): body=json.dumps(body).encode()
        self.send_response(status); self.send_header('Content-Type',content_type)
        if filename: self.send_header('Content-Disposition',f'attachment; filename="{filename}"')
        self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def redirect(self,location):
        self.send_response(303); self.send_header('Location',location); self.send_header('Content-Length','0'); self.end_headers()
    def trusted(self):
        if self.headers.get('Host') not in self.server.allowed_hosts: return False
        origin=self.headers.get('Origin')
        return not origin or origin in self.server.allowed_origins
    def session_token(self):
        cookie=SimpleCookie()
        try: cookie.load(self.headers.get('Cookie',''))
        except Exception: return None
        morsel=cookie.get(self.server.cookie_name)
        token=morsel.value if morsel else None
        expires=SESSIONS.get(token)
        if not expires: return None
        if expires<=time.time(): SESSIONS.pop(token,None); return None
        SESSIONS[token]=time.time()+SESSION_TTL
        return token
    def client_ip(self):
        remote_ip=self.client_address[0]
        if remote_ip in ('127.0.0.1','::1'):
            forwarded=self.headers.get('X-Forwarded-For','').split(',',1)[0].strip()
            if forwarded: return forwarded
        return remote_ip
    def set_session_cookie(self,token):
        secure='; Secure' if self.server.secure_cookie else ''
        self.send_header('Set-Cookie',f'{self.server.cookie_name}={token}; Path=/; Max-Age={SESSION_TTL}; HttpOnly; SameSite=Strict{secure}')
    def clear_session_cookie(self):
        secure='; Secure' if self.server.secure_cookie else ''
        self.send_header('Set-Cookie',f'{self.server.cookie_name}=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict{secure}')
    def login_page(self):
        if self.session_token(): return self.redirect('/')
        try: body=(STATIC/'login.html').read_bytes()
        except OSError: return self.output({'error':'Login page unavailable'},500)
        self.output(body,content_type='text/html; charset=utf-8')
    def login(self):
        if (not self.trusted() or self.headers.get('Origin') not in self.server.allowed_origins
                or self.headers.get('X-Library-Request')!='1'):
            return self.output({'error':'Invalid login request'},403)
        try: size=int(self.headers.get('Content-Length','0'))
        except ValueError: return self.output({'error':'Invalid request'},400)
        if size<0 or size>4096: return self.output({'error':'Invalid request'},400)
        try:
            data=json.loads(self.rfile.read(size) or b'{}')
            if not isinstance(data,dict): raise ValueError()
            username=data.get('username',''); password=data.get('password','')
            if not isinstance(username,str) or not isinstance(password,str): raise ValueError()
        except (ValueError,UnicodeError): return self.output({'error':'Invalid username or password'},400)
        address=self.client_ip(); now=time.time()
        attempts=[t for t in LOGIN_ATTEMPTS.get(address,[]) if t>now-LOGIN_WINDOW]
        if len(attempts)>=MAX_LOGIN_ATTEMPTS:
            LOGIN_ATTEMPTS[address]=attempts
            return self.output({'error':'Too many attempts. Try again in 15 minutes.'},429)
        valid=(hmac.compare_digest(username.encode('utf-8'),self.server.login_username.encode('utf-8'))
               and hmac.compare_digest(password.encode('utf-8'),self.server.login_password.encode('utf-8')))
        if not valid:
            attempts.append(now); LOGIN_ATTEMPTS[address]=attempts
            return self.output({'error':'Invalid username or password'},401)
        LOGIN_ATTEMPTS.pop(address,None)
        token=secrets.token_urlsafe(32); SESSIONS[token]=now+SESSION_TTL
        self.send_response(200); self.send_header('Content-Type','application/json')
        self.set_session_cookie(token); body=b'{"ok":true}'; self.send_header('Content-Length',str(len(body)))
        self.end_headers(); self.wfile.write(body)
    def logout(self):
        if (not self.trusted() or self.headers.get('Origin') not in self.server.allowed_origins
                or self.headers.get('X-Library-Request')!='1'):
            return self.output({'error':'Invalid logout request'},403)
        token=self.session_token()
        if token: SESSIONS.pop(token,None)
        self.send_response(200); self.send_header('Content-Type','application/json')
        self.clear_session_cookie(); body=b'{"ok":true}'; self.send_header('Content-Length',str(len(body)))
        self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if not self.trusted(): return self.output({'error':'Invalid local origin'},403)
        path=urlparse(self.path).path
        if path=='/login': return self.login_page()
        if path in ('/login.js','/login.css'):
            if self.session_token(): return self.send_error(404)
            return super().do_GET()
        if not self.session_token():
            if path.startswith('/api/'): return self.output({'error':'Authentication required'},401)
            return self.redirect('/login')
        if not path.startswith('/api/'):
            return super().do_GET()
        conn=db.connect(self.server.db_path)
        try:
            if path=='/api/data': return self.output(db.snapshot(conn))
            if path=='/api/backup':
                with tempfile.TemporaryDirectory() as folder:
                    target=Path(folder)/'library.sqlite3'
                    dest=sqlite3.connect(target)
                    try: conn.backup(dest)
                    finally: dest.close()
                    return self.output(target.read_bytes(),content_type='application/octet-stream',filename=f'library-{db.today()}.sqlite3')
            if path.startswith('/api/export/'):
                kind=path.rsplit('/',1)[1]
                fields={'books':['id','title','author','publication_year','price','publisher','pages','seller','isbn','category','shelf','total_copies','available_copies','archived','notes'], 'members':['member_code','full_name','phone','email','address','registration_date','status','notes'], 'loans':['id','title','full_name','borrow_date','due_date','return_date','status','notes']}
                if kind not in fields: raise ValueError('Unknown export')
                stream=io.StringIO(); writer=csv.DictWriter(stream,fieldnames=fields[kind],extrasaction='ignore'); writer.writeheader()
                for row in db.snapshot(conn)[kind]:
                    # Prevent spreadsheet applications from interpreting user text as formulas.
                    writer.writerow({k:("'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')) else v) for k,v in row.items()})
                return self.output(('\ufeff'+stream.getvalue()).encode(),content_type='text/csv; charset=utf-8',filename=f'{kind}-{db.today()}.csv')
            self.output({'error':'Not found'},404)
        except (ValueError,sqlite3.Error) as exc: self.output({'error':str(exc)},400)
        finally: conn.close()
    def do_POST(self):
        path=urlparse(self.path).path
        if path=='/api/login': return self.login()
        if path=='/api/logout': return self.logout()
        self.mutate()
    def do_PUT(self): self.mutate()
    def do_DELETE(self): self.mutate()
    def mutate(self):
        if not self.trusted() or self.headers.get('Origin') not in self.server.allowed_origins or self.headers.get('X-Library-Request')!='1': return self.output({'error':'Invalid local request'},403)
        if not self.session_token(): return self.output({'error':'Authentication required'},401)
        conn=None
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size<0 or size>MAX_BODY: raise ValueError('Upload exceeds the 32 MB limit')
            raw=self.rfile.read(size); path=urlparse(self.path).path
            if path=='/api/restore' and self.command=='POST':
                self.restore(raw); return self.output({'ok':True})
            data=json.loads(raw or '{}')
            if not isinstance(data,dict): raise ValueError('Expected an object')
            parts=path.strip('/').split('/')
            conn=db.connect(self.server.db_path)
            if len(parts) in (2,3) and parts[0]=='api' and parts[1] in ('books','members'):
                kind=parts[1]; record_id=db.integer(parts[2],'Record') if len(parts)==3 else None
                if self.command=='POST' and record_id is None: db.save(conn,kind,data)
                elif self.command=='PUT' and record_id: db.save(conn,kind,data,record_id)
                elif self.command=='DELETE' and record_id: db.remove(conn,kind,record_id)
                else: raise ValueError('Invalid operation')
            elif path=='/api/loans' and self.command=='POST': db.borrow(conn,data)
            elif len(parts)==4 and parts[:2]==['api','loans'] and parts[3]=='return' and self.command=='POST': db.return_book(conn,db.integer(parts[2],'Loan'),data)
            else: return self.output({'error':'Not found'},404)
            self.output({'ok':True})
        except (ValueError,sqlite3.Error,UnicodeError) as exc: self.output({'error':str(exc)},400)
        finally:
            if conn: conn.close()
    def restore(self,raw):
        if not raw.startswith(b'SQLite format 3\x00'): raise ValueError('Choose a valid SQLite backup exported by this app')
        with tempfile.TemporaryDirectory(dir=Path(self.server.db_path).parent) as folder:
            incoming=Path(folder)/'incoming.sqlite3'; incoming.write_bytes(raw)
            reference=Path(folder)/'reference.sqlite3'; db.initialize(reference,seed=False)
            source=db.connect(incoming); expected=db.connect(reference)
            try:
                schema="SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
                if [tuple(r) for r in source.execute(schema)] != [tuple(r) for r in expected.execute(schema)]: raise ValueError('Backup schema does not match this application')
                if source.execute('PRAGMA user_version').fetchone()[0]!=2: raise ValueError('Unsupported backup version')
                if source.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or source.execute('PRAGMA foreign_key_check').fetchone(): raise ValueError('Backup failed integrity checks')
                state=db.snapshot(source)
                for book in state['books']:
                    db.clean(book,'books')
                    if book['available_copies']<0: raise ValueError('Backup has invalid copy counts')
                for member in state['members']: db.clean(member,'members')
                for loan in state['loans']:
                    for key in ('borrow_date','due_date','return_date'):
                        if loan[key] is not None: db.date(loan[key],key)
                    if loan['borrow_date']>db.today() or (loan['return_date'] and loan['return_date']>db.today()): raise ValueError('Backup contains future transactions')
                current=db.connect(self.server.db_path)
                safety=sqlite3.connect(str(self.server.db_path)+'.before-restore.sqlite3')
                try: current.backup(safety)
                finally: current.close(); safety.close()
            finally: source.close(); expected.close()
            os.replace(incoming,self.server.db_path)

def main():
    parser=argparse.ArgumentParser(description='Local Library Management System')
    parser.add_argument('--bind-address',default='127.0.0.1',help='Network interface address to bind (default: loopback only)'); parser.add_argument('--port',type=int,default=8765); parser.add_argument('--db',default='data/library.sqlite3'); parser.add_argument('--empty',action='store_true',help='Create an empty database without samples')
    args=parser.parse_args()
    username=os.environ.get('LIBRARY_USERNAME'); password=os.environ.get('LIBRARY_PASSWORD')
    if not username or not password: parser.error('Set LIBRARY_USERNAME and LIBRARY_PASSWORD before starting the server')
    path=Path(args.db).resolve(); db.initialize(path,seed=not args.empty and not path.exists())
    default_host=f'127.0.0.1:{args.port}'
    hosts={h.strip() for h in os.environ.get('LIBRARY_ALLOWED_HOST',f'{default_host},localhost:{args.port}').split(',') if h.strip()}
    default_origins=f'http://127.0.0.1:{args.port},http://localhost:{args.port}'
    origins={o.strip().rstrip('/') for o in os.environ.get('LIBRARY_ALLOWED_ORIGIN',default_origins).split(',') if o.strip()}
    server=HTTPServer((args.bind_address,args.port),Handler); server.db_path=path
    server.login_username=username; server.login_password=password
    server.allowed_hosts=hosts; server.allowed_origins=origins
    server.secure_cookie=bool(origins) and all(origin.startswith('https://') for origin in origins)
    server.cookie_name='__Host-library_session' if server.secure_cookie else 'library_session'
    print(f'Library is ready: http://{args.bind_address}:{args.port}\nDatabase: {path}',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: print('\nLibrary stopped.')
    finally: server.server_close()

if __name__=='__main__': main()

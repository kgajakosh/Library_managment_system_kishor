import base64
import datetime as dt
import re
import sqlite3
from pathlib import Path

MIGRATIONS = (
    Path(__file__).parent / 'migrations/001_initial.sql',
    Path(__file__).parent / 'migrations/002_book_catalog_fields.sql',
    Path(__file__).parent / 'migrations/003_remove_issuing_date.sql',
)

def today():
    return dt.date.today().isoformat()

def connect(path):
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    return conn

def initialize(path, seed=True):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    try:
        version = conn.execute('PRAGMA user_version').fetchone()[0]
        if version > 3:
            raise ValueError('Database version is newer than this app')
        if version == 0:
            conn.executescript(MIGRATIONS[0].read_text())
        if version < 2:
            conn.executescript(MIGRATIONS[1].read_text())
        if version < 3:
            conn.executescript(MIGRATIONS[2].read_text())
        if seed and not conn.execute('SELECT 1 FROM books').fetchone():
            with conn:
                conn.executemany('INSERT INTO books(title,author,category,total_copies,shelf,notes) VALUES(?,?,?,?,?,?)', [
                    ('The Midnight Library','Matt Haig','Fiction',3,'A-01','A story about possibility and second chances.'),
                    ('Atomic Habits','James Clear','Personal growth',2,'B-02','Small changes, remarkable results.'),
                    ('A Brief History of Time','Stephen Hawking','Science',2,'C-01','An exploration of the universe.'),
                    ('Pride and Prejudice','Jane Austen','Classics',1,'A-03',''),
                    ('The Art of Gathering','Priya Parker','Community',2,'B-01',''),
                    ('The Hobbit','J. R. R. Tolkien','Fantasy',2,'A-04','')])
                conn.executemany('INSERT INTO members(full_name,phone,email,registration_date,status) VALUES(?,?,?,?,?)', [
                    ('Alex Morgan','','alex@example.test',today(),'Active'),('Sam Rivera','','sam@example.test',today(),'Active'),('Taylor Chen','','taylor@example.test',today(),'Active')])
                day = dt.date.today()
                conn.executemany('INSERT INTO loans(book_id,member_id,borrow_date,due_date,return_date,notes) VALUES(?,?,?,?,?,?)', [
                    (1,1,str(day-dt.timedelta(days=5)),str(day+dt.timedelta(days=9)),None,''),
                    (4,2,str(day-dt.timedelta(days=20)),str(day-dt.timedelta(days=6)),None,'Sample overdue loan'),
                    (2,3,str(day-dt.timedelta(days=30)),str(day-dt.timedelta(days=16)),str(day-dt.timedelta(days=18)),'Sample returned loan')])
    finally:
        conn.close()

def date(value, label):
    try:
        result = dt.date.fromisoformat(str(value))
        if str(result) != value: raise ValueError()
        return value
    except (ValueError, TypeError):
        raise ValueError(f'{label} must be a valid YYYY-MM-DD date')

def integer(value, label, minimum=1, maximum=1000000):
    if isinstance(value,bool) or not re.fullmatch(r'\d+',str(value)): raise ValueError(f'{label} must be a whole number')
    value=int(value)
    if not minimum <= value <= maximum: raise ValueError(f'{label} must be between {minimum} and {maximum}')
    return value

def decimal(value, label):
    if isinstance(value,bool) or not re.fullmatch(r'\d+(?:\.\d{1,2})?',str(value)):
        raise ValueError(f'{label} must be a valid amount')
    value=float(value)
    if not 0 < value <= 10000000: raise ValueError(f'{label} must be between 0.01 and 10000000')
    return value

def clean(data, kind):
    fields = ('title author isbn category publisher shelf cover notes seller'.split() if kind=='books' else 'full_name phone email address notes'.split())
    out={key:str(data.get(key,'')).strip() for key in fields}
    for key,value in out.items():
        if len(value) > (2800000 if key=='cover' else 10000): raise ValueError(f'{key} is too long')
    for key in (['title','author','publisher'] if kind=='books' else ['full_name']):
        if not out[key]: raise ValueError(f'{key.replace("_"," ").title()} is required')
    if kind=='books':
        out['total_copies']=integer(data.get('total_copies'), 'Total copies')
        out['publication_year']=integer(data.get('publication_year'),'Publication year',1,9999)
        out['price']=decimal(data.get('price'),'Price')
        out['pages']=integer(data.get('pages'),'Number of pages',1,100000)
        if out['cover']:
            if not re.fullmatch(r'data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+',out['cover']): raise ValueError('Cover must be an uploaded PNG, JPEG or WebP image')
            try: base64.b64decode(out['cover'].split(',')[1],validate=True)
            except ValueError: raise ValueError('Invalid cover image')
    else:
        if out['email'] and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',out['email']): raise ValueError('Enter a valid email address')
        out['registration_date']=date(data.get('registration_date'),'Registration date')
        out['status']=data.get('status','Active')
        if out['status'] not in ('Active','Inactive'): raise ValueError('Invalid participant status')
    return out

def snapshot(conn):
    books=[dict(r) for r in conn.execute('SELECT b.*, b.total_copies-(SELECT COUNT(*) FROM loans l WHERE l.book_id=b.id AND l.return_date IS NULL) AS available_copies FROM books b ORDER BY b.id DESC')]
    members=[dict(r,member_code=f'MEM-{r["id"]:04d}') for r in conn.execute('SELECT * FROM members ORDER BY full_name')]
    loans=[dict(r) for r in conn.execute('SELECT l.*,b.title,m.full_name FROM loans l JOIN books b ON b.id=l.book_id JOIN members m ON m.id=l.member_id ORDER BY l.id DESC')]
    for loan in loans: loan['status']=loan_status(loan,today())
    return dict(books=books,members=members,loans=loans,today=today())

def loan_status(loan, day):
    return 'Returned' if loan['return_date'] else ('Overdue' if loan['due_date'] < day else 'Borrowed')

def save(conn,kind,data,record_id=None):
    values=clean(data,kind)
    with conn:
        if record_id:
            cur=conn.execute(f'UPDATE {kind} SET '+','.join(f'{key}=?' for key in values)+' WHERE id=?',[*values.values(),record_id])
            if cur.rowcount!=1: raise ValueError('Record not found')
        else:
            conn.execute(f'INSERT INTO {kind}('+','.join(values)+') VALUES('+','.join('?' for _ in values)+')',list(values.values()))

def remove(conn,kind,record_id):
    foreign='book_id' if kind=='books' else 'member_id'
    with conn:
        if not conn.execute(f'SELECT 1 FROM {kind} WHERE id=?',(record_id,)).fetchone(): raise ValueError('Record not found')
        if conn.execute(f'SELECT 1 FROM loans WHERE {foreign}=?',(record_id,)).fetchone():
            conn.execute(f'UPDATE {kind} SET '+('archived=1' if kind=='books' else "status='Inactive'")+' WHERE id=?',(record_id,))
        else: conn.execute(f'DELETE FROM {kind} WHERE id=?',(record_id,))

def borrow(conn,data):
    book=integer(data.get('book_id'),'Book'); member=integer(data.get('member_id'),'Participant')
    start=date(data.get('borrow_date'),'Borrow date'); due=date(data.get('due_date'),'Due date')
    if start>today(): raise ValueError('Borrow date cannot be in the future')
    if due<start: raise ValueError('Due date cannot precede borrow date')
    notes=str(data.get('notes','')).strip()
    if len(notes)>10000: raise ValueError('Notes are too long')
    with conn: conn.execute('INSERT INTO loans(book_id,member_id,borrow_date,due_date,notes) VALUES(?,?,?,?,?)',(book,member,start,due,notes))

def return_book(conn,loan_id,data):
    returned=date(data.get('return_date'),'Return date')
    if returned>today(): raise ValueError('Return date cannot be in the future')
    with conn:
        cur=conn.execute('UPDATE loans SET return_date=? WHERE id=? AND return_date IS NULL',(returned,loan_id))
        if cur.rowcount!=1: raise ValueError('Loan not found or already returned')

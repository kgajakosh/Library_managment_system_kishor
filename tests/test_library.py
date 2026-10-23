import datetime as dt
import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from http.server import HTTPServer
from library import db
from library.server import Handler

class CirculationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.path=Path(self.temp.name)/'library.sqlite3'
        db.initialize(self.path,seed=False); self.conn=db.connect(self.path)
        db.save(self.conn,'books',dict(title='A book',author='An author',total_copies=2))
        db.save(self.conn,'members',dict(full_name='A reader',registration_date=db.today(),status='Active'))
    def tearDown(self): self.conn.close(); self.temp.cleanup()
    def borrow(self,**extra):
        values=dict(book_id=1,member_id=1,borrow_date=db.today(),due_date=db.today()); values.update(extra); db.borrow(self.conn,values)
    def available(self): return db.snapshot(self.conn)['books'][0]['available_copies']
    def test_borrow_and_return(self):
        self.borrow(); self.assertEqual(self.available(),1)
        db.return_book(self.conn,1,{'return_date':db.today()}); self.assertEqual(self.available(),2)
        self.assertEqual(db.snapshot(self.conn)['loans'][0]['status'],'Returned')
        with self.assertRaises(ValueError): db.return_book(self.conn,1,{'return_date':db.today()})
        self.assertEqual(self.available(),2)
    def test_unavailable_and_stock_reduction(self):
        self.borrow(); self.borrow()
        with self.assertRaises(sqlite3.IntegrityError): self.borrow()
        self.assertEqual(self.available(),0)
        with self.assertRaises(sqlite3.IntegrityError): db.save(self.conn,'books',dict(title='A book',author='An author',total_copies=1),1)
        self.assertEqual(self.available(),0)
    def test_inactive_and_archived(self):
        self.conn.execute("UPDATE members SET status='Inactive'");self.conn.commit()
        with self.assertRaises(sqlite3.IntegrityError): self.borrow()
        self.conn.execute("UPDATE members SET status='Active'");self.conn.commit()
        self.borrow(); db.remove(self.conn,'books',1); db.remove(self.conn,'members',1)
        data=db.snapshot(self.conn); self.assertEqual(data['books'][0]['archived'],1);self.assertEqual(data['members'][0]['status'],'Inactive');self.assertEqual(len(data['loans']),1)
        db.return_book(self.conn,1,dict(return_date=db.today()));self.assertEqual(self.available(),2)
        with self.assertRaises(sqlite3.IntegrityError): self.borrow()
    def test_invalid_dates_and_foreign_keys(self):
        with self.assertRaises(ValueError): self.borrow(due_date='1900-01-01')
        with self.assertRaises(ValueError): self.borrow(borrow_date='9999-01-01',due_date='9999-01-01')
        with self.assertRaises(sqlite3.IntegrityError): self.borrow(book_id=999)
        self.borrow()
        with self.assertRaises(sqlite3.IntegrityError): db.return_book(self.conn,1,dict(return_date='1900-01-01'))
    def test_overdue_boundary(self):
        day=db.today(); prior=str(dt.date.today()-dt.timedelta(days=1))
        self.assertEqual(db.loan_status(dict(return_date=None,due_date=day),day),'Borrowed')
        self.assertEqual(db.loan_status(dict(return_date=None,due_date=prior),day),'Overdue')
        self.assertEqual(db.loan_status(dict(return_date=day,due_date=prior),day),'Returned')
    def test_delete_without_history(self):
        db.remove(self.conn,'books',1);db.remove(self.conn,'members',1)
        self.assertEqual(db.snapshot(self.conn)['books'],[]);self.assertEqual(db.snapshot(self.conn)['members'],[])
    def test_member_ids_not_reused(self):
        db.remove(self.conn,'members',1);db.save(self.conn,'members',dict(full_name='Another',registration_date=db.today()))
        self.assertEqual(db.snapshot(self.conn)['members'][0]['member_code'],'MEM-0002')
    def test_seed_idempotence(self):
        another=Path(self.temp.name)/'sample.sqlite3';db.initialize(another);db.initialize(another)
        conn=db.connect(another)
        try:
            state=db.snapshot(conn);self.assertEqual(len(state['books']),6);self.assertEqual(len(state['loans']),3)
        finally: conn.close()

class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.path=Path(cls.temp.name)/'db.sqlite3';db.initialize(cls.path)
        cls.server=HTTPServer(('127.0.0.1',0),Handler);cls.server.db_path=cls.path
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start();cls.url=f'http://127.0.0.1:{cls.server.server_port}'
    @classmethod
    def tearDownClass(cls): cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.temp.cleanup()
    def request(self,path,method='GET',data=None,headers=None):
        body=data if isinstance(data,bytes) else json.dumps(data).encode() if data is not None else None
        req=urllib.request.Request(self.url+path,data=body,method=method,headers=headers or {'X-Library-Request':'1'})
        try:
            with urllib.request.urlopen(req) as response:return response.status,response.read(),response.headers
        except urllib.error.HTTPError as error:
            with error: return error.code,error.read(),error.headers
    def test_static_and_csv(self):
        for path in ('/','/style.css','/app.js','/api/data','/api/export/books','/api/export/members','/api/export/loans'):
            status,body,headers=self.request(path);self.assertEqual(status,200,path);self.assertTrue(body);self.assertIn('Content-Security-Policy',headers)
    def test_request_protection(self):
        status,_,_=self.request('/api/books','POST',{},headers={'Origin':'https://example.com','X-Library-Request':'1'});self.assertEqual(status,403)
        status,_,_=self.request('/api/books','POST',{},headers={'Content-Type':'application/json'});self.assertEqual(status,403)
    def test_validation(self):
        status,_,_=self.request('/api/books','POST',{'title':'','author':'A','total_copies':1});self.assertEqual(status,400)
        status,_,_=self.request('/api/books','POST',[]);self.assertEqual(status,400)
    def test_backup_restore_roundtrip(self):
        _,before,_=self.request('/api/data');status,backup,_=self.request('/api/backup');self.assertEqual(status,200)
        status,_,_=self.request('/api/books','POST',dict(title='Temporary',author='Test',total_copies=1));self.assertEqual(status,200)
        status,body,_=self.request('/api/restore','POST',backup);self.assertEqual(status,200,body)
        _,after,_=self.request('/api/data');self.assertEqual(json.loads(before),json.loads(after));self.assertTrue(Path(str(self.path)+'.before-restore.sqlite3').exists())
        status,_,_=self.request('/api/restore','POST',b'invalid');self.assertEqual(status,400)
        _,unchanged,_=self.request('/api/data');self.assertEqual(after,unchanged)
    def test_reject_foreign_schema(self):
        path=Path(self.temp.name)/'foreign.sqlite3';conn=sqlite3.connect(path);conn.execute('CREATE TABLE unrelated (id INTEGER)');conn.close()
        status,_,_=self.request('/api/restore','POST',path.read_bytes());self.assertEqual(status,400)

if __name__=='__main__': unittest.main()

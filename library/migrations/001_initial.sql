CREATE TABLE IF NOT EXISTS books (
 id INTEGER PRIMARY KEY, title TEXT NOT NULL, author TEXT NOT NULL,
 isbn TEXT NOT NULL DEFAULT '', category TEXT NOT NULL DEFAULT '', publisher TEXT NOT NULL DEFAULT '',
 publication_year INTEGER, shelf TEXT NOT NULL DEFAULT '', total_copies INTEGER NOT NULL CHECK(total_copies >= 1),
 cover TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1)),
 created_at TEXT NOT NULL DEFAULT (date('now'))
);
CREATE TABLE IF NOT EXISTS members (
 id INTEGER PRIMARY KEY AUTOINCREMENT, full_name TEXT NOT NULL, phone TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '',
 address TEXT NOT NULL DEFAULT '', registration_date TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('Active','Inactive')),
 notes TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS loans (
 id INTEGER PRIMARY KEY, book_id INTEGER NOT NULL REFERENCES books(id), member_id INTEGER NOT NULL REFERENCES members(id),
 borrow_date TEXT NOT NULL, due_date TEXT NOT NULL CHECK(due_date >= borrow_date),
 return_date TEXT CHECK(return_date IS NULL OR return_date >= borrow_date), notes TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS loans_book_active ON loans(book_id,return_date);
CREATE INDEX IF NOT EXISTS loans_member ON loans(member_id);
CREATE TRIGGER IF NOT EXISTS guard_borrow BEFORE INSERT ON loans WHEN NEW.return_date IS NULL BEGIN
 SELECT CASE WHEN (SELECT archived FROM books WHERE id=NEW.book_id) != 0 THEN RAISE(ABORT,'Book is archived') END;
 SELECT CASE WHEN (SELECT status FROM members WHERE id=NEW.member_id) != 'Active' THEN RAISE(ABORT,'Participant is inactive') END;
 SELECT CASE WHEN (SELECT COUNT(*) FROM loans WHERE book_id=NEW.book_id AND return_date IS NULL) >= (SELECT total_copies FROM books WHERE id=NEW.book_id) THEN RAISE(ABORT,'No copies available') END;
END;
CREATE TRIGGER IF NOT EXISTS guard_copies BEFORE UPDATE OF total_copies ON books BEGIN
 SELECT CASE WHEN NEW.total_copies < (SELECT COUNT(*) FROM loans WHERE book_id=OLD.id AND return_date IS NULL) THEN RAISE(ABORT,'Total copies cannot be less than borrowed copies') END;
END;
PRAGMA user_version = 1;

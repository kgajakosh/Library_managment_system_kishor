# Little Library

A complete, local Library Management System for a personal or community collection. A warm, responsive interface runs in your browser; all records and uploaded covers stay in a SQLite database on your computer. No cloud account, network connection, package installation, or build step is required.

## Run

Requires **Python 3.10 or newer** and a current Chrome, Edge, Firefox, or Safari browser.

From this folder:

```sh
python3 -m library.server
```

On Windows, use `py -m library.server` if `python3` is unavailable.

Open **http://127.0.0.1:8765**. Keep the terminal running while using the app. Stop it with Ctrl+C. Restart with the same command; your records persist.

On its first run, the app creates `data/library.sqlite3` and adds six books, three participants, two current loans (including an overdue loan), and one returned loan. Sample dates are relative to your computer's current date. It never re-seeds an existing database.

For a separate, empty library:

```sh
python3 -m library.server --db data/my-library.sqlite3 --empty
```

To change ports:

```sh
python3 -m library.server --port 8766
```

The application binds only to `127.0.0.1`. It is designed for one local library instance, not public hosting or authenticated multi-user access. Run only one server per database, particularly when restoring backups.

## Windows desktop or laptop setup

These steps use **Command Prompt** on Windows 10/11. The app runs locally in your browser, with a terminal window keeping the server running. Internet access is needed to download Python initially; the configured app works offline.

### 1. Install Python

Download the Python install manager from the [official Python website](https://www.python.org/downloads/windows/) and follow its installation prompts. Open a new Command Prompt and install a Python runtime:

```bat
py install 3.14
py --version
```

If you already have Python 3.10 or newer, skip installation and verify it with `py --version`. The `py install` command is for the new install manager; older Python launchers do not support it. See the [official Windows installation guide](https://docs.python.org/3/using/windows.html) for installation troubleshooting.

No separate SQLite, Node.js, npm, or Python packages are required.

### 2. Copy the application to your computer

Copy or extract the complete project into a writable local folder, for example:

```text
C:\Users\YourName\LittleLibrary\
    README.md
    library\
        __init__.py
        db.py
        server.py
        migrations\
        static\
    tests\
```

The commands below assume the folder is `%USERPROFILE%\LittleLibrary`. Substitute your actual folder if you use a different location. Extract ZIP files before running the app. Keep the working database in a local folder outside OneDrive or other live-sync folders; downloaded backups can be copied elsewhere.

### 3. Start the library

Open Command Prompt and run:

```bat
cd /d "%USERPROFILE%\LittleLibrary"
py -m library.server
```

Wait for `Library is ready: http://127.0.0.1:8765`, then open that address in Edge, Chrome, or Firefox. Leave Command Prompt open while using the library. To stop, select its window and press **Ctrl+C**. Run the same commands to start it again after restarting Windows.

The default database is `%USERPROFILE%\LittleLibrary\data\library.sqlite3`. On first launch, the app creates it with sample records. To start a separate library without samples, use:

```bat
py -m library.server --db data\my-library.sqlite3 --empty
```

Use the same `--db data\my-library.sqlite3` option every time you reopen that library. The `--empty` option prevents initial sample data; it does not erase an existing database.

### 4. Create a desktop shortcut

For convenient startup, open Notepad and paste:

```bat
@echo off
cd /d "%~dp0"
echo Starting Little Library...
echo When the server is ready, open http://127.0.0.1:8765 in your browser.
echo Keep this window open. Press Ctrl+C here to stop the server.
py -m library.server
pause
```

Save this in the project folder as **Start Library.bat**, selecting **All files** as the file type so Notepad does not append `.txt`. If using the empty library from step 3, change the script's server command to `py -m library.server --db data\my-library.sqlite3`.

Right-click `Start Library.bat` and choose **Send to → Desktop (create shortcut)**; on Windows 11, **Show more options** may expose that menu. Keep the original batch file in the project folder because it uses its own location to find the app. Double-click the desktop shortcut to start the server, then open or bookmark **http://127.0.0.1:8765** in your browser. Start only one instance at a time.

### 5. Back up or move your library

In **Settings & backup**, download a database backup regularly. To move to another Windows desktop or laptop, copy the source code, install Python, start the app there, and restore the exported backup through **Settings & backup**. Restore replaces the destination library, including its sample data. The backup contains all books, participants, loans, and covers. For backups larger than 32 MB, follow the manual restore instructions in the Backups section below.

### Windows troubleshooting

| Problem | What to do |
| --- | --- |
| `py` is not recognized | Finish installing Python and reopen Command Prompt. If `python --version` works and reports 3.10 or newer, replace `py` with `python` in the startup commands and batch file. |
| `No module named library` | Run from the project folder containing the `library` directory, not from inside that directory. Check that the ZIP was fully extracted. |
| Port 8765 is already in use / `WinError 10048` | Check whether the app is already running. Otherwise use `py -m library.server --port 8766` and open `http://127.0.0.1:8766`. Update the shortcut script if keeping this port. |
| Browser says it cannot connect | Keep the server terminal open, check it for errors, and use the exact `http://127.0.0.1:8765` address and configured port. |
| Permission denied or database is read-only | Move the project to a writable folder under your user account, rather than `Program Files`, and run it from there. |
| Your records appear to be missing | Check that you started from the same project folder with the same `--db` option. Relative database paths are resolved from the terminal's working folder. |

The app listens only on this computer; no router port forwarding or inbound network sharing configuration is required.

## Using the app

- **Dashboard:** title/copy counts, active participants, current and overdue borrowings, recent additions, and most frequently borrowed books.
- **Books:** add books, upload optional covers, search title/author/category/ISBN, filter availability, and open details to edit or lend a copy. Cards display current borrowers. Check “Include archived” to see archived titles.
- **Participants:** register members with generated, non-reused `MEM-0001` style IDs. Open a participant to see contact information, current books and complete loan history. Phone and email can be left blank.
- **Borrow & return:** select an active participant and an available book, then enter borrow/due dates and optional notes. Return a loan with its actual return date.
- **Borrowing history:** search every transaction, including returned loans, and filter status.
- **Reports:** download UTF-8 CSV inventory, participant and loan exports. Print current or overdue loans, or save the print view as PDF using your browser.
- **Settings & backup:** download a full SQLite backup or restore a previously exported backup. Covers are included.

### Circulation rules

Availability is derived from total copies minus open loans, so it cannot drift out of sync. A database trigger rejects loans beyond available stock, archived books and inactive participants. Another trigger rejects stock reductions below the number of open loans. Returning is atomic and can happen only once.

A loan is overdue when its due date is **before** the computer's current local date. A book due today is not overdue. Returned loans remain `Returned`, even when they were returned late. Borrow and return dates cannot be in the future; due dates cannot precede borrow dates; returns cannot precede borrowing.

Deleting a book/member with any loan history archives/inactivates it and preserves all relationships. Current loans remain returnable. Records without history are permanently deleted after confirmation. Inactive participants can be reactivated through Edit. Archived books remain archived. History displays the current book title and participant name, so correcting their spelling updates the display while retaining the original IDs and transaction dates.

Dashboard title, total-copy and available-copy figures exclude archived titles. Borrowed and overdue counts include all outstanding loans, including archived books.

### Backups

Backups are portable SQLite files. Restore checks the exact schema, schema version, SQLite integrity, foreign keys, form data, dates and copy counts before replacing the database. Invalid files leave the current library intact. Restore accepts files up to **32 MB**; book covers accept PNG/JPEG/WebP up to **2 MB** each.

Before each successful restore, a safety backup is saved next to the database as `library.sqlite3.before-restore.sqlite3` (or `<your database filename>.before-restore.sqlite3`). The next restore replaces this safety copy. Download regular backups and store them separately from your computer.

For databases above the 32 MB restore limit, stop the server and replace the database file manually with a trusted backup. Retain a copy of the old file first. Backups contain participant contact information and are not encrypted.

## Implementation

Python's standard-library HTTP server + SQLite provide a dependency-free backend. The frontend is plain JavaScript, semantic HTML and responsive CSS. This intentionally uses the specification's local-web-app option rather than Electron, React or a Node build pipeline. No external fonts, images, analytics or CDN resources are loaded.

```text
library/
  db.py                       Validation, circulation rules, sample data, queries
  server.py                   Local HTTP/API server, CSV export, backup/restore
  migrations/001_initial.sql  Version 1 schema, indexes, constraints, triggers
  static/index.html           Application shell
  static/app.js               Screens and interactive workflows
  static/style.css            Responsive interface and print styles
tests/test_library.py         Database and HTTP integration tests
```

The SQL migration is applied idempotently on startup. `PRAGMA user_version` records schema version 1. Newer unsupported versions are rejected. Future schema versions should add sequential migrations; no future-version migration mechanism is implied by this initial release.

Mutation routes require a same-origin local Host/Origin and an application request header. User-facing content is HTML-escaped, SQL values are parameterized, a content security policy blocks remote assets, and CSV fields are protected against spreadsheet formula execution. The static document root contains only frontend assets; the database is not served as a static file.

### API

- `GET /api/data` — books, participants, loans and local date
- `POST /api/books`, `PUT /api/books/:id`, `DELETE /api/books/:id`
- `POST /api/members`, `PUT /api/members/:id`, `DELETE /api/members/:id`
- `POST /api/loans` — borrow a copy
- `POST /api/loans/:id/return` — record a return
- `GET /api/export/books`, `/api/export/members`, `/api/export/loans`
- `GET /api/backup` — consistent SQLite snapshot
- `POST /api/restore` — raw SQLite backup bytes

Mutation requests must include `X-Library-Request: 1`. All mutations except restore accept JSON.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

Tests use temporary databases and a temporary loopback port. They cover borrowing and returning, repeated returns, unavailable copies, stock reductions, inactive/archived records, dates, overdue boundaries, deletion/history retention, stable member IDs, seeding, API validation, local request protection, exports, backup/restore round trips, and invalid backups.

For a manual check, borrow the last available copy, confirm another loan is blocked, return it, and verify stock recovers. Open a participant and check their current books. Export each CSV; preview both print reports. Download a backup, add a record, restore the backup, and confirm the new record disappears. Check the Books screen at both desktop and narrow mobile widths.

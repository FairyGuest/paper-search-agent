import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime


def now():
    return datetime.now(UTC).isoformat()


def identifier():
    return uuid.uuid4().hex


class Store:
    def __init__(self, path):
        self.lock = threading.RLock()
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA foreign_keys=ON;
            CREATE TABLE IF NOT EXISTS papers (
                id TEXT PRIMARY KEY, pmid TEXT UNIQUE, doi TEXT, metadata TEXT NOT NULL,
                file_name TEXT, page_count INTEGER DEFAULT 0, text_status TEXT DEFAULT 'abstract',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS papers_doi ON papers(doi);
            CREATE TABLE IF NOT EXISTS pages (
                paper_id TEXT REFERENCES papers(id) ON DELETE CASCADE,
                number INTEGER, text TEXT NOT NULL, PRIMARY KEY(paper_id, number)
            );
            CREATE TABLE IF NOT EXISTS edges (
                source TEXT REFERENCES papers(id), target TEXT REFERENCES papers(id), relation TEXT,
                PRIMARY KEY(source, target, relation)
            );
            CREATE TABLE IF NOT EXISTS searches (
                id TEXT PRIMARY KEY, query TEXT, details TEXT, created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS notes (
                id TEXT PRIMARY KEY, paper_id TEXT REFERENCES papers(id), kind TEXT,
                title TEXT, content TEXT, revision INTEGER DEFAULT 1, metadata TEXT DEFAULT '{}',
                created_at TEXT, updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT, paper_id TEXT REFERENCES papers(id),
                role TEXT, content TEXT, scope TEXT, created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, kind TEXT, status TEXT, progress INTEGER, message TEXT,
                result TEXT DEFAULT '{}', created_at TEXT, updated_at TEXT
            );
        """)
        self.execute(
            "UPDATE jobs SET status='interrupted', message='服务已重启，请重新发起任务' "
            "WHERE status IN ('queued','running','waiting_user')"
        )

    def execute(self, query, params=()):
        with self.lock, self.connection:
            return self.connection.execute(query, params).rowcount

    def rows(self, query, params=()):
        with self.lock:
            return [dict(row) for row in self.connection.execute(query, params).fetchall()]

    def row(self, query, params=()):
        rows = self.rows(query, params)
        return rows[0] if rows else None

    def close(self):
        self.connection.close()

    def upsert_paper(self, metadata):
        with self.lock:
            found = None
            if metadata.get("pmid"):
                found = self.row("SELECT id FROM papers WHERE pmid=?", (metadata["pmid"],))
            if not found and metadata.get("doi"):
                found = self.row("SELECT id FROM papers WHERE lower(doi)=lower(?)", (metadata["doi"],))
            if found:
                paper_id = found["id"]
                previous = self.paper(paper_id)
                merged = previous["metadata"] | {key: value for key, value in metadata.items() if value}
                self.execute(
                    "UPDATE papers SET pmid=?, doi=?, metadata=? WHERE id=?",
                    (
                        merged.get("pmid") or None,
                        merged.get("doi", ""),
                        json.dumps(merged, ensure_ascii=False),
                        paper_id,
                    ),
                )
            else:
                paper_id = identifier()
                self.execute(
                    "INSERT INTO papers(id,pmid,doi,metadata,created_at) VALUES(?,?,?,?,?)",
                    (
                        paper_id,
                        metadata.get("pmid") or None,
                        metadata.get("doi", ""),
                        json.dumps(metadata, ensure_ascii=False),
                        now(),
                    ),
                )
            return self.paper(paper_id)

    @staticmethod
    def decode_paper(row):
        if row:
            row["metadata"] = json.loads(row["metadata"])
            row["has_pdf"] = bool(row["file_name"])
        return row

    def paper(self, paper_id):
        return self.decode_paper(self.row("SELECT * FROM papers WHERE id=?", (paper_id,)))

    def papers(self):
        return [self.decode_paper(row) for row in self.rows("SELECT * FROM papers ORDER BY created_at DESC")]

    def set_pdf(self, paper_id, filename, pages):
        text_length = sum(len(text.strip()) for text in pages)
        with self.lock, self.connection:
            self.connection.execute("DELETE FROM pages WHERE paper_id=?", (paper_id,))
            self.connection.executemany(
                "INSERT INTO pages VALUES(?,?,?)",
                ((paper_id, number, text) for number, text in enumerate(pages, 1)),
            )
            self.connection.execute(
                "UPDATE papers SET file_name=?,page_count=?,text_status=? WHERE id=?",
                (filename, len(pages), "fulltext" if text_length >= 80 else "scan", paper_id),
            )
        return self.paper(paper_id)

    def pages(self, paper_id):
        return self.rows("SELECT number,text FROM pages WHERE paper_id=? ORDER BY number", (paper_id,))

    def edge(self, source, target, relation):
        if source != target:
            self.execute("INSERT OR IGNORE INTO edges VALUES(?,?,?)", (source, target, relation))

    def add_search(self, query, details):
        self.execute(
            "INSERT INTO searches VALUES(?,?,?,?)",
            (identifier(), query, json.dumps(details, ensure_ascii=False), now()),
        )

    def create_note(self, title, content="", paper_id=None, kind="note", metadata=None):
        note_id = identifier()
        self.execute(
            "INSERT INTO notes VALUES(?,?,?,?,?,1,?,?,?)",
            (
                note_id,
                paper_id,
                kind,
                title,
                content,
                json.dumps(metadata or {}, ensure_ascii=False),
                now(),
                now(),
            ),
        )
        return self.note(note_id)

    def note(self, note_id):
        note = self.row("SELECT * FROM notes WHERE id=?", (note_id,))
        if note:
            note["metadata"] = json.loads(note["metadata"])
        return note

    def update_note(self, note_id, title, content, revision):
        count = self.execute(
            "UPDATE notes SET title=?,content=?,revision=revision+1,updated_at=? WHERE id=? AND revision=?",
            (title, content, now(), note_id, revision),
        )
        if not count:
            raise ValueError("笔记已被其他页面修改，请复制当前内容后重新打开")
        return self.note(note_id)

    def messages(self, paper_id):
        return self.rows("SELECT * FROM messages WHERE paper_id=? ORDER BY id", (paper_id,))

    def add_message(self, paper_id, role, content, scope):
        self.execute(
            "INSERT INTO messages(paper_id,role,content,scope,created_at) VALUES(?,?,?,?,?)",
            (paper_id, role, content, scope, now()),
        )

    def create_job(self, kind):
        job_id = identifier()
        self.execute(
            "INSERT INTO jobs VALUES(?,?,'queued',0,'等待执行','{}',?,?)", (job_id, kind, now(), now())
        )
        return self.job(job_id)

    def update_job(self, job_id, status, progress, message, result=None):
        self.execute(
            "UPDATE jobs SET status=?,progress=?,message=?,result=?,updated_at=? WHERE id=?",
            (status, progress, message, json.dumps(result or {}, ensure_ascii=False), now(), job_id),
        )

    def job(self, job_id):
        row = self.row("SELECT * FROM jobs WHERE id=?", (job_id,))
        if row:
            row["result"] = json.loads(row["result"])
        return row

"""Small durable state machine; no raw Slack payloads or API responses."""

from contextlib import contextmanager
import os
import hashlib
import json
import sqlite3
import stat
import threading

from .config import Refused


class Store:
    def __init__(self, path):
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
                raise Refused()
        finally:
            os.close(fd)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=DELETE")
        self.db.execute("PRAGMA secure_delete=ON")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS envelopes (
                id TEXT PRIMARY KEY
            );
            CREATE TABLE IF NOT EXISTS binding (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1), digest TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY, thread TEXT NOT NULL, requester TEXT NOT NULL,
                kind TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending'
            );
            CREATE TABLE IF NOT EXISTS proposals (
                thread TEXT PRIMARY KEY, requester TEXT NOT NULL, text TEXT,
                received REAL NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
                issue_id TEXT, issue_identifier TEXT, retry_after INTEGER,
                polling INTEGER NOT NULL DEFAULT 1,
                poll_sequence INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS deliveries (
                id TEXT PRIMARY KEY, thread TEXT NOT NULL, state TEXT NOT NULL,
                retry_after INTEGER
            );
        """)
        self.db.commit()

    @contextmanager
    def transaction(self):
        with self.lock, self.db:
            yield self.db

    def close(self):
        self.db.close()

    def bind(self, config):
        # Never reinterpret old private threads as belonging to a new workspace,
        # channel, company, frontend, bot, or authorization cohort.
        values = [getattr(config, key) for key in (
            "workspace_id", "app_id", "bot_user_id", "bot_id", "channel_id",
            "company_id", "company_prefix", "paperclip_api_url", "paperclip_public_url")]
        values.append(sorted(config.allowed_user_ids))
        # Preserve the exact historical digest for default/explicit allowlist.
        # Dynamic membership changes authorization policy, not just its roster.
        if config.access_mode != "allowlist":
            values.append({"access_mode": config.access_mode})
        digest = hashlib.sha256(json.dumps(values).encode("utf-8")).hexdigest()
        with self.transaction() as db:
            saved = db.execute("SELECT digest FROM binding WHERE singleton=1").fetchone()
            if saved is not None and saved[0] != digest:
                raise Refused()
            db.execute("INSERT OR IGNORE INTO binding VALUES (1,?)", (digest,))

    def recover(self):
        # A committed "creating"/"sending" receipt may precede a successful remote
        # POST. Neither an outage nor a restart is evidence that it failed.
        with self.transaction() as db:
            db.execute("UPDATE proposals SET state='uncertain',text=NULL "
                       "WHERE state='creating'")
            db.execute("UPDATE deliveries SET state='uncertain' WHERE state='sending'")

    def accept(self, envelope, event, thread, requester, text, now):
        with self.transaction() as db:
            if db.execute("SELECT 1 FROM envelopes WHERE id=?", (envelope,)).fetchone():
                return
            db.execute("INSERT INTO envelopes VALUES (?)", (envelope,))
            if db.execute("SELECT 1 FROM events WHERE id=?", (event,)).fetchone():
                return
            pending = db.execute(
                "SELECT count(*) FROM events WHERE state='pending'").fetchone()[0]
            if pending >= 100:
                # Roll back the envelope too: do not acknowledge accepted work
                # that has not been durably queued.
                raise Refused()
            known = db.execute(
                "SELECT 1 FROM proposals WHERE thread=?", (thread,)).fetchone()
            if not known:
                db.execute(
                    "INSERT INTO proposals(thread,requester,text,received) VALUES (?,?,?,?)",
                    (thread, requester, text, now))
            db.execute("INSERT INTO events(id,thread,requester,kind) VALUES (?,?,?,?)",
                       (event, thread, requester, "reference" if known else "initial"))

    def pending_event(self):
        with self.lock:
            return self.db.execute(
                "SELECT * FROM events WHERE state='pending' ORDER BY rowid LIMIT 1"
            ).fetchone()

    def proposal(self, thread):
        with self.lock:
            return self.db.execute(
                "SELECT * FROM proposals WHERE thread=?", (thread,)).fetchone()

    def finish_event(self, event):
        with self.transaction() as db:
            db.execute("UPDATE events SET state='finished' WHERE id=?", (event,))

    def reject(self, thread):
        with self.transaction() as db:
            db.execute("UPDATE proposals SET state='rejected',text=NULL "
                       "WHERE thread=? AND state='pending'", (thread,))

    def expire_pending(self, now):
        with self.transaction() as db:
            db.execute("UPDATE proposals SET state='rejected',text=NULL "
                       "WHERE state='pending' AND received<=?", (now - 3600,))

    def begin_create(self, thread):
        with self.transaction() as db:
            row = db.execute("SELECT * FROM proposals WHERE thread=? AND state='pending'",
                             (thread,)).fetchone()
            if row is not None:
                db.execute("UPDATE proposals SET state='creating',text=NULL WHERE thread=?",
                           (thread,))
            return row

    def created(self, thread, issue):
        with self.transaction() as db:
            db.execute("UPDATE proposals SET state='created',issue_id=?,issue_identifier=? "
                       "WHERE thread=? AND state='creating'",
                       (issue.id, issue.identifier, thread))

    def create_failed(self, thread, retry_after=None):
        state = "rate_limited" if retry_after is not None else "uncertain"
        with self.transaction() as db:
            db.execute("UPDATE proposals SET state=?,text=NULL,retry_after=? "
                       "WHERE thread=? AND state='creating'",
                       (state, retry_after, thread))

    def poll_batch(self):
        # Bound external reads and rotate fairly, including across restarts.
        with self.transaction() as db:
            rows = db.execute(
                "SELECT * FROM proposals WHERE state='created' AND polling=1 "
                "ORDER BY poll_sequence,rowid LIMIT 10").fetchall()
            sequence = db.execute(
                "SELECT coalesce(max(poll_sequence),0) FROM proposals").fetchone()[0]
            for offset, row in enumerate(rows, 1):
                db.execute("UPDATE proposals SET poll_sequence=? WHERE thread=?",
                           (sequence + offset, row["thread"]))
            return rows

    def stop_polling(self, thread):
        with self.transaction() as db:
            db.execute("UPDATE proposals SET polling=0 WHERE thread=?", (thread,))

    def has_delivery(self, key):
        with self.lock:
            return self.db.execute(
                "SELECT 1 FROM deliveries WHERE id=?", (key,)).fetchone() is not None

    def begin_delivery(self, key, thread, terminal=False):
        with self.transaction() as db:
            inserted = db.execute(
                "INSERT OR IGNORE INTO deliveries(id,thread,state) VALUES (?,?,'sending')",
                (key, thread)).rowcount == 1
            if terminal:
                # Same commit as the send receipt: a crash/ambiguous send must
                # not keep closed proposals in the recurring poll workload.
                db.execute("UPDATE proposals SET polling=0 WHERE thread=?", (thread,))
            return inserted

    def delivery_finished(self, key, state, retry_after=None):
        with self.transaction() as db:
            db.execute("UPDATE deliveries SET state=?,retry_after=? "
                       "WHERE id=? AND state='sending'", (state, retry_after, key))

"""Durable proposal/chat states; never raw Slack or provider payloads."""

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
            CREATE TABLE IF NOT EXISTS chat_turns (
                id TEXT PRIMARY KEY, thread TEXT NOT NULL, requester TEXT NOT NULL,
                mode TEXT NOT NULL CHECK(mode='conversation'),
                received REAL NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
                prompt TEXT, reply TEXT, attempted REAL, sent REAL
            );
            CREATE INDEX IF NOT EXISTS chat_attempts ON chat_turns(attempted,requester);
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
            db.execute("UPDATE chat_turns SET state='uncertain',prompt=NULL,reply=NULL "
                       "WHERE state='generating'")

    def _seen_event(self, db, event):
        return db.execute(
            "SELECT 1 FROM events WHERE id=? UNION ALL "
            "SELECT 1 FROM chat_turns WHERE id=? LIMIT 1", (event, event)).fetchone() is not None

    def accept(self, envelope, event, thread, requester, text, now):
        with self.transaction() as db:
            if db.execute("SELECT 1 FROM envelopes WHERE id=?", (envelope,)).fetchone():
                return
            db.execute("INSERT INTO envelopes VALUES (?)", (envelope,))
            if self._seen_event(db, event):
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

    def accept_chat(self, envelope, event, thread, requester, prompt, now):
        with self.transaction() as db:
            if db.execute("SELECT 1 FROM envelopes WHERE id=?", (envelope,)).fetchone():
                return
            db.execute("INSERT INTO envelopes VALUES (?)", (envelope,))
            if self._seen_event(db, event):
                return
            pending = db.execute(
                "SELECT count(*) FROM chat_turns WHERE state='pending'").fetchone()[0]
            if pending >= 20:
                raise Refused()
            db.execute(
                "INSERT INTO chat_turns(id,thread,requester,mode,received,prompt) "
                "VALUES (?,?,?,'conversation',?,?)", (event, thread, requester, now, prompt))

    def pending_chat(self):
        with self.lock:
            return self.db.execute(
                "SELECT * FROM chat_turns WHERE state='pending' ORDER BY rowid LIMIT 1").fetchone()

    def chat_turn(self, event):
        with self.lock:
            return self.db.execute("SELECT * FROM chat_turns WHERE id=?", (event,)).fetchone()

    def expire_chats(self, now):
        with self.transaction() as db:
            db.execute("UPDATE chat_turns SET state='expired',prompt=NULL,reply=NULL "
                       "WHERE state='pending' AND received<=?", (now - 600,))
            db.execute("UPDATE chat_turns SET prompt=NULL,reply=NULL "
                       "WHERE sent<=? AND (prompt IS NOT NULL OR reply IS NOT NULL)",
                       (now - 86400,))

    def begin_chat(self, event, now):
        with self.transaction() as db:
            row = db.execute("SELECT * FROM chat_turns WHERE id=? AND state='pending'",
                             (event,)).fetchone()
            if row is None:
                return None
            if row["received"] <= now - 600:
                db.execute("UPDATE chat_turns SET state='expired',prompt=NULL WHERE id=?", (event,))
                return None
            hourly = db.execute(
                "SELECT count(*) FROM chat_turns WHERE attempted>?", (now - 3600,)).fetchone()[0]
            daily = db.execute(
                "SELECT count(*) FROM chat_turns WHERE attempted>?", (now - 86400,)).fetchone()[0]
            personal = db.execute(
                "SELECT count(*) FROM chat_turns WHERE requester=? AND attempted>?",
                (row["requester"], now - 3600)).fetchone()[0]
            if personal >= 10 or hourly >= 30 or daily >= 100:
                db.execute("UPDATE chat_turns SET state='rate_limited',prompt=NULL WHERE id=?",
                           (event,))
                return None
            # Commit an attempt before RPC. Raw request is now memory-only until
            # a confirmed SENT reply qualifies the pair for temporary history.
            db.execute("UPDATE chat_turns SET state='generating',prompt=NULL,attempted=? WHERE id=?",
                       (now, event))
            return row

    def finish_chat(self, event, state):
        with self.transaction() as db:
            db.execute("UPDATE chat_turns SET state=?,prompt=NULL,reply=NULL "
                       "WHERE id=? AND state!='sent'", (state, event))

    def chat_sent(self, event, prompt, reply, now):
        with self.transaction() as db:
            db.execute("UPDATE chat_turns SET state='sent',prompt=?,reply=?,sent=? "
                       "WHERE id=? AND state='generating' AND EXISTS "
                       "(SELECT 1 FROM deliveries WHERE id=? AND state='sent')",
                       (prompt, reply, now, event, "chat:" + event))

    def chat_history(self, thread, members, now, own_mention=""):
        with self.lock:
            rows = self.db.execute(
                "SELECT * FROM chat_turns WHERE thread=? AND state='sent' AND sent>? "
                "ORDER BY sent DESC,rowid DESC", (thread, now - 86400)).fetchall()
        # Later replies may quote earlier contributors: if ANY unexpired SENT
        # contributor departed, do not replay even indirectly derived history.
        contributors = frozenset(row["requester"] for row in rows)
        if not contributors <= members:
            return [], frozenset()
        # Fence publication with the SAME full set, including contributors of
        # older/oversized pairs omitted from the bounded RPC history.
        pairs, chars, size = [], 0, 0
        for row in rows:
            if not isinstance(row["prompt"], str) or not isinstance(row["reply"], str):
                continue
            prompt = row["prompt"].replace(own_mention, "").strip() if own_mention else row["prompt"]
            reply = row["reply"].replace(own_mention, "").strip() if own_mention else row["reply"]
            if not prompt or not reply:
                continue
            pair_chars = len(prompt) + len(reply)
            pair_size = len((prompt + reply).encode("utf-8"))
            if chars + pair_chars > 6000 or size + pair_size > 24000:
                continue
            pairs.append([{"role": "user", "content": prompt},
                          {"role": "assistant", "content": reply}])
            chars, size = chars + pair_chars, size + pair_size
            if len(pairs) == 3:
                break
        return [message for pair in reversed(pairs) for message in pair], contributors

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

    def delivery_state(self, key):
        with self.lock:
            row = self.db.execute("SELECT state FROM deliveries WHERE id=?", (key,)).fetchone()
            return row["state"] if row is not None else None

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

import sqlite3
import threading
from datetime import datetime, timezone

DB_PATH = "leads.db"
_lock = threading.Lock()


def init_db():
    with _lock:
        conn = sqlite3.connect(DB_PATH, timeout=30.0)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS leads (
                leadgen_id TEXT PRIMARY KEY,
                status TEXT DEFAULT 'pending',
                retry_count INTEGER DEFAULT 0,
                error TEXT,
                created_at TEXT
            )
            """
        )
        conn.commit()
        conn.close()


def enqueue_lead(leadgen_id: str) -> bool:
    """Insert a new lead record. Returns False if it already exists (dedup),
    so the same lead is never processed / messaged twice."""
    with _lock:
        conn = sqlite3.connect(DB_PATH, timeout=30.0)
        try:
            conn.execute(
                "INSERT INTO leads (leadgen_id, status, created_at) VALUES (?, 'pending', ?)",
                (leadgen_id, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()


def mark_status(leadgen_id: str, status: str, error: str = None):
    with _lock:
        conn = sqlite3.connect(DB_PATH, timeout=30.0)
        conn.execute(
            "UPDATE leads SET status = ?, error = ? WHERE leadgen_id = ?",
            (status, error, leadgen_id),
        )
        conn.commit()
        conn.close()


def increment_retry(leadgen_id: str) -> int:
    with _lock:
        conn = sqlite3.connect(DB_PATH, timeout=30.0)
        conn.execute(
            "UPDATE leads SET retry_count = retry_count + 1 WHERE leadgen_id = ?",
            (leadgen_id,),
        )
        conn.commit()
        row = conn.execute(
            "SELECT retry_count FROM leads WHERE leadgen_id = ?", (leadgen_id,)
        ).fetchone()
        conn.close()
        return row[0] if row else 0


def get_unfinished_leads(max_retries: int):
    """Leads that never finished successfully — used on startup to recover
    from a crash or restart without losing anything."""
    with _lock:
        conn = sqlite3.connect(DB_PATH, timeout=30.0)
        rows = conn.execute(
            "SELECT leadgen_id FROM leads WHERE status != 'done' AND retry_count < ?",
            (max_retries,),
        ).fetchall()
        conn.close()
        return [r[0] for r in rows]

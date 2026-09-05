import sqlite3
import threading
import logging
from datetime import datetime, timezone
from config import settings

logger = logging.getLogger("db")
DB_PATH = "leads.db"
_lock = threading.Lock()


def _get_connection():
    if settings.DATABASE_URL:
        try:
            import psycopg2
            url = settings.DATABASE_URL
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql://", 1)
            return ("postgres", psycopg2.connect(url))
        except Exception as e:
            logger.error(f"Failed to connect to Postgres DATABASE_URL ({e}). Falling back to local SQLite.")

    return ("sqlite", sqlite3.connect(DB_PATH, timeout=30.0))


def _execute(conn_tuple, sql, params=()):
    db_type, conn = conn_tuple
    try:
        cursor = conn.cursor()
        if db_type == "postgres":
            pg_sql = sql.replace("?", "%s")
            cursor.execute(pg_sql, params)
        else:
            cursor.execute(sql, params)
        conn.commit()
        return cursor
    except Exception:
        conn.rollback()
        raise


def init_db():
    with _lock:
        db_type, conn = _get_connection()
        try:
            _execute(
                (db_type, conn),
                """
                CREATE TABLE IF NOT EXISTS leads (
                    leadgen_id TEXT PRIMARY KEY,
                    status TEXT DEFAULT 'pending',
                    retry_count INTEGER DEFAULT 0,
                    error TEXT,
                    created_at TEXT
                )
                """,
            )
        finally:
            conn.close()


def enqueue_lead(leadgen_id: str) -> bool:
    """Insert a new lead record. Returns False if it already exists (dedup),
    so the same lead is never processed / messaged twice."""
    with _lock:
        db_type, conn = _get_connection()
        try:
            _execute(
                (db_type, conn),
                "INSERT INTO leads (leadgen_id, status, created_at) VALUES (?, 'pending', ?)",
                (str(leadgen_id), datetime.now(timezone.utc).isoformat()),
            )
            return True
        except Exception as err:
            # Handles duplicate key / integrity errors cleanly
            if "unique" in str(err).lower() or "integrity" in str(err).lower() or "duplicate" in str(err).lower():
                return False
            logger.warning(f"Error enqueuing lead {leadgen_id}: {err}")
            return False
        finally:
            conn.close()


def mark_status(leadgen_id: str, status: str, error: str = None):
    with _lock:
        db_type, conn = _get_connection()
        try:
            _execute(
                (db_type, conn),
                "UPDATE leads SET status = ?, error = ? WHERE leadgen_id = ?",
                (status, error, str(leadgen_id)),
            )
        finally:
            conn.close()


def increment_retry(leadgen_id: str) -> int:
    with _lock:
        db_type, conn = _get_connection()
        try:
            _execute(
                (db_type, conn),
                "UPDATE leads SET retry_count = retry_count + 1 WHERE leadgen_id = ?",
                (str(leadgen_id),),
            )
            cursor = _execute(
                (db_type, conn),
                "SELECT retry_count FROM leads WHERE leadgen_id = ?",
                (str(leadgen_id),),
            )
            row = cursor.fetchone()
            return row[0] if row else 0
        finally:
            conn.close()


def get_unfinished_leads(max_retries: int):
    """Leads that never finished successfully — used on startup to recover
    from a crash or restart without losing anything."""
    with _lock:
        db_type, conn = _get_connection()
        try:
            cursor = _execute(
                (db_type, conn),
                "SELECT leadgen_id FROM leads WHERE status != 'done' AND retry_count < ?",
                (max_retries,),
            )
            rows = cursor.fetchall()
            return [r[0] for r in rows]
        finally:
            conn.close()


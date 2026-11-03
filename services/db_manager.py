"""
services/db_manager.py - Local SQLite storage for art scheduling queue and Facebook IDs
"""
import sqlite3
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pathlib import Path
from config import DB_PATH

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes tables and indexes."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_dir TEXT UNIQUE NOT NULL,
                category TEXT NOT NULL, -- 'evergreen' or 'timely'
                title TEXT,
                image_path TEXT NOT NULL,
                caption TEXT NOT NULL,
                scheduled_timestamp INTEGER NOT NULL,
                scheduled_iso TEXT NOT NULL,
                meta_fbid TEXT,
                status TEXT NOT NULL, -- 'pending', 'scheduled', 'published', 'failed'
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_status ON scheduled_posts(status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sched_time ON scheduled_posts(scheduled_timestamp);")
        conn.commit()

def is_post_processed(post_dir: str) -> bool:
    """Checks if a post directory has already been processed or scheduled."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM scheduled_posts WHERE post_dir = ? AND status IN ('scheduled', 'published')", (post_dir,))
        return cursor.fetchone() is not None

def get_latest_scheduled_timestamp() -> Optional[int]:
    """Returns the latest scheduled Unix timestamp currently in the queue, or None if empty."""
    now_ts = int(datetime.now(timezone.utc).timestamp())
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT MAX(scheduled_timestamp) FROM scheduled_posts 
            WHERE status = 'scheduled' AND scheduled_timestamp > ?
        """, (now_ts,))
        row = cursor.fetchone()
        return row[0] if row and row[0] else None

def get_scheduled_timestamps_for_date(date_str: str) -> List[int]:
    """Returns all scheduled timestamps for a given UTC date (YYYY-MM-DD)."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT scheduled_timestamp FROM scheduled_posts
            WHERE status = 'scheduled' AND scheduled_iso LIKE ?
        """, (f"{date_str}%",))
        return [row[0] for row in cursor.fetchall()]

def record_scheduled_post(
    post_dir: str,
    category: str,
    title: str,
    image_path: str,
    caption: str,
    scheduled_timestamp: int,
    meta_fbid: str,
    status: str = "scheduled",
    error_message: Optional[str] = None
) -> int:
    """Records a newly scheduled post package."""
    now_iso = datetime.now(timezone.utc).isoformat()
    sched_iso = datetime.fromtimestamp(scheduled_timestamp, tz=timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO scheduled_posts (
                post_dir, category, title, image_path, caption,
                scheduled_timestamp, scheduled_iso, meta_fbid, status,
                error_message, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(post_dir) DO UPDATE SET
                scheduled_timestamp = excluded.scheduled_timestamp,
                scheduled_iso = excluded.scheduled_iso,
                meta_fbid = excluded.meta_fbid,
                status = excluded.status,
                error_message = excluded.error_message,
                updated_at = excluded.updated_at
        """, (
            post_dir, category, title, image_path, caption,
            scheduled_timestamp, sched_iso, meta_fbid, status,
            error_message, now_iso, now_iso
        ))
        conn.commit()
        return cursor.lastrowid

def list_active_schedule() -> List[Dict[str, Any]]:
    """Returns all upcoming scheduled posts sorted chronologically."""
    now_ts = int(datetime.now(timezone.utc).timestamp())
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM scheduled_posts
            WHERE status = 'scheduled' AND scheduled_timestamp > ?
            ORDER BY scheduled_timestamp ASC
        """, (now_ts,))
        return [dict(row) for row in cursor.fetchall()]

# Initialize on import
init_db()

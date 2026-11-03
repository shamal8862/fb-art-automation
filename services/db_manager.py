"""
services/db_manager.py - Resilient SQLite State Manager for Art Scheduling
Provides two-phase idempotency, simulation isolation, and reconciliation tracking.
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
    """Initializes tables and indexes with simulation isolation."""
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
                is_simulation INTEGER NOT NULL DEFAULT 0, -- 1 = dry-run, 0 = live
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_status_sim ON scheduled_posts(status, is_simulation);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sched_time ON scheduled_posts(scheduled_timestamp);")
        conn.commit()

def is_post_processed(post_dir: str, include_simulated: bool = False) -> bool:
    """
    Checks if a post directory has already been scheduled or published.
    When include_simulated=False, simulated runs NEVER block a live schedule.
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        if include_simulated:
            cursor.execute("SELECT id FROM scheduled_posts WHERE post_dir = ? AND status IN ('pending', 'scheduled', 'published')", (post_dir,))
        else:
            cursor.execute("SELECT id FROM scheduled_posts WHERE post_dir = ? AND status IN ('pending', 'scheduled', 'published') AND is_simulation = 0", (post_dir,))
        return cursor.fetchone() is not None

def record_pending_post(
    post_dir: str,
    category: str,
    title: str,
    image_path: str,
    caption: str,
    scheduled_timestamp: int,
    is_simulation: bool = False
) -> int:
    """Phase 1: Records a pending post before transmitting to Facebook."""
    now_iso = datetime.now(timezone.utc).isoformat()
    sched_iso = datetime.fromtimestamp(scheduled_timestamp, tz=timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO scheduled_posts (
                post_dir, category, title, image_path, caption,
                scheduled_timestamp, scheduled_iso, meta_fbid, status,
                is_simulation, error_message, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 'pending', ?, NULL, ?, ?)
            ON CONFLICT(post_dir) DO UPDATE SET
                scheduled_timestamp = excluded.scheduled_timestamp,
                scheduled_iso = excluded.scheduled_iso,
                status = 'pending',
                is_simulation = excluded.is_simulation,
                error_message = NULL,
                updated_at = excluded.updated_at
        """, (
            post_dir, category, title, image_path, caption,
            scheduled_timestamp, sched_iso, 1 if is_simulation else 0,
            now_iso, now_iso
        ))
        conn.commit()
        return cursor.lastrowid

def confirm_post_scheduled(post_dir: str, meta_fbid: str, final_image_path: str, cdn_image_url: Optional[str] = None, ig_status: str = "scheduled"):
    """Phase 2: Confirms successful scheduling with Facebook's returned ID, CDN URL, and updated path."""
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE scheduled_posts
            SET status = 'scheduled',
                meta_fbid = ?,
                image_path = ?,
                cdn_image_url = COALESCE(?, cdn_image_url),
                ig_status = COALESCE(?, ig_status),
                updated_at = ?
            WHERE post_dir = ?
        """, (meta_fbid, final_image_path, cdn_image_url, ig_status, now_iso, post_dir))
        conn.commit()

def mark_post_failed(post_dir: str, error_message: str):
    """Marks a post as failed so it can be diagnosed."""
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE scheduled_posts
            SET status = 'failed',
                error_message = ?,
                updated_at = ?
            WHERE post_dir = ?
        """, (error_message, now_iso, post_dir))
        conn.commit()

def get_pending_posts(include_simulated: bool = False) -> List[Dict[str, Any]]:
    """Returns any posts left in 'pending' status for crash reconciliation."""
    with get_connection() as conn:
        cursor = conn.cursor()
        if include_simulated:
            cursor.execute("SELECT * FROM scheduled_posts WHERE status = 'pending'")
        else:
            cursor.execute("SELECT * FROM scheduled_posts WHERE status = 'pending' AND is_simulation = 0")
        return [dict(row) for row in cursor.fetchall()]

def get_latest_scheduled_timestamp(category: Optional[str] = None) -> Optional[int]:
    """Returns the latest scheduled Unix timestamp for the given category (or overall)."""
    now_ts = int(datetime.now(timezone.utc).timestamp())
    with get_connection() as conn:
        cursor = conn.cursor()
        if category:
            cursor.execute("""
                SELECT MAX(scheduled_timestamp) FROM scheduled_posts 
                WHERE status = 'scheduled' AND scheduled_timestamp > ? AND category = ? AND is_simulation = 0
            """, (now_ts, category))
        else:
            cursor.execute("""
                SELECT MAX(scheduled_timestamp) FROM scheduled_posts 
                WHERE status = 'scheduled' AND scheduled_timestamp > ? AND is_simulation = 0
            """, (now_ts,))
        row = cursor.fetchone()
        return row[0] if row and row[0] else None

def get_scheduled_posts_for_date(date_str: str, category: Optional[str] = None) -> List[Dict[str, Any]]:
    """Returns all active scheduled posts for a given UTC date."""
    with get_connection() as conn:
        cursor = conn.cursor()
        if category:
            cursor.execute("""
                SELECT * FROM scheduled_posts
                WHERE status = 'scheduled' AND scheduled_iso LIKE ? AND category = ? AND is_simulation = 0
            """, (f"{date_str}%", category))
        else:
            cursor.execute("""
                SELECT * FROM scheduled_posts
                WHERE status = 'scheduled' AND scheduled_iso LIKE ? AND is_simulation = 0
            """, (f"{date_str}%",))
        return [dict(row) for row in cursor.fetchall()]

def is_timestamp_occupied(target_timestamp: int, tolerance_minutes: int = 15) -> bool:
    """Checks if a target timestamp is already occupied within the given tolerance."""
    window = tolerance_minutes * 60
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id FROM scheduled_posts
            WHERE status = 'scheduled' 
              AND is_simulation = 0
              AND scheduled_timestamp BETWEEN ? AND ?
        """, (target_timestamp - window, target_timestamp + window))
        return cursor.fetchone() is not None

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

# Auto-initialize
init_db()

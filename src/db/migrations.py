"""
DB 스키마 확장 — monitoring_events, notifications, monitor_cursors 테이블 추가
앱 시작 시 init_db_extensions() 한 번 호출
"""

import sqlite3
import os

DB_PATH = os.getenv("DB_PATH", "./sns_management.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db_extensions():
    """기존 approval_queue/publish_log 유지, 신규 테이블 3개 추가 + WAL 모드 활성화."""
    with get_conn() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS approval_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                topic TEXT,
                ko_text TEXT NOT NULL,
                ko_hashtags TEXT,
                en_text TEXT NOT NULL,
                en_hashtags TEXT,
                brand_safety_score REAL NOT NULL,
                approved INTEGER DEFAULT 0,
                rejection_reason TEXT,
                scheduled_at TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                reviewed_at TEXT,
                reviewed_by TEXT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS publish_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                queue_id INTEGER REFERENCES approval_queue(id),
                platform TEXT NOT NULL,
                platform_post_id TEXT,
                status TEXT NOT NULL,
                error_message TEXT,
                published_at TEXT DEFAULT (datetime('now'))
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS monitoring_events (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                platform     TEXT NOT NULL,
                event_type   TEXT NOT NULL,
                external_id  TEXT,
                author       TEXT,
                text         TEXT NOT NULL,
                sentiment    TEXT,
                severity     TEXT DEFAULT 'info',
                raw_json     TEXT,
                url          TEXT,
                detected_at  TEXT DEFAULT (datetime('now')),
                UNIQUE(platform, external_id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                type             TEXT NOT NULL,
                title            TEXT NOT NULL,
                body             TEXT,
                severity         TEXT DEFAULT 'info',
                related_event_id INTEGER REFERENCES monitoring_events(id),
                related_queue_id INTEGER REFERENCES approval_queue(id),
                read_at          TEXT,
                created_at       TEXT DEFAULT (datetime('now'))
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS monitor_cursors (
                platform      TEXT PRIMARY KEY,
                last_since_id TEXT,
                last_run_at   TEXT,
                last_error    TEXT
            )
        """)

        conn.execute("INSERT OR IGNORE INTO monitor_cursors (platform) VALUES ('x')")
        conn.execute("INSERT OR IGNORE INTO monitor_cursors (platform) VALUES ('facebook')")
        conn.execute("INSERT OR IGNORE INTO monitor_cursors (platform) VALUES ('instagram')")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS account_snapshots (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                platform     TEXT NOT NULL,
                followers    INTEGER DEFAULT 0,
                following    INTEGER DEFAULT 0,
                post_count   INTEGER DEFAULT 0,
                extra_json   TEXT,
                captured_at  TEXT DEFAULT (datetime('now'))
            )
        """)

        conn.commit()

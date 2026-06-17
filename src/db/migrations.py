"""
DB 스키마 초기화 — PostgreSQL (Neon) 버전
앱 시작 시 init_db_extensions() 한 번 호출
"""

from src.db.db import db_cursor


def init_db_extensions():
    """전체 테이블 생성 (IF NOT EXISTS). PostgreSQL Neon 대상."""
    with db_cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS approval_queue (
                id                 SERIAL PRIMARY KEY,
                platform           TEXT NOT NULL,
                topic              TEXT,
                ko_text            TEXT NOT NULL,
                ko_hashtags        TEXT,
                en_text            TEXT NOT NULL,
                en_hashtags        TEXT,
                brand_safety_score REAL NOT NULL,
                approved           INTEGER DEFAULT 0,
                rejection_reason   TEXT,
                scheduled_at       TEXT,
                created_at         TIMESTAMP DEFAULT NOW(),
                reviewed_at        TIMESTAMP,
                reviewed_by        TEXT
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS publish_log (
                id               SERIAL PRIMARY KEY,
                queue_id         INTEGER REFERENCES approval_queue(id),
                platform         TEXT NOT NULL,
                platform_post_id TEXT,
                status           TEXT NOT NULL,
                error_message    TEXT,
                published_at     TIMESTAMP DEFAULT NOW()
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS monitoring_events (
                id          SERIAL PRIMARY KEY,
                platform    TEXT NOT NULL,
                event_type  TEXT NOT NULL,
                external_id TEXT,
                author      TEXT,
                text        TEXT NOT NULL,
                sentiment   TEXT,
                severity    TEXT DEFAULT 'info',
                raw_json    TEXT,
                url         TEXT,
                detected_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(platform, external_id)
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id               SERIAL PRIMARY KEY,
                type             TEXT NOT NULL,
                title            TEXT NOT NULL,
                body             TEXT,
                severity         TEXT DEFAULT 'info',
                related_event_id INTEGER REFERENCES monitoring_events(id),
                related_queue_id INTEGER REFERENCES approval_queue(id),
                read_at          TIMESTAMP,
                created_at       TIMESTAMP DEFAULT NOW()
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS monitor_cursors (
                platform      TEXT PRIMARY KEY,
                last_since_id TEXT,
                last_run_at   TIMESTAMP,
                last_error    TEXT
            )
        """)

        cur.execute("INSERT INTO monitor_cursors (platform) VALUES ('x')          ON CONFLICT (platform) DO NOTHING")
        cur.execute("INSERT INTO monitor_cursors (platform) VALUES ('facebook')   ON CONFLICT (platform) DO NOTHING")
        cur.execute("INSERT INTO monitor_cursors (platform) VALUES ('instagram')  ON CONFLICT (platform) DO NOTHING")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS account_snapshots (
                id          SERIAL PRIMARY KEY,
                platform    TEXT NOT NULL,
                followers   INTEGER DEFAULT 0,
                following   INTEGER DEFAULT 0,
                post_count  INTEGER DEFAULT 0,
                extra_json  TEXT,
                captured_at TIMESTAMP DEFAULT NOW()
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS credentials (
                key        TEXT PRIMARY KEY,
                value      TEXT NOT NULL,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)

"""
monitoring_events, notifications, monitor_cursors CRUD
"""

import sqlite3
import json
import os

DB_PATH = os.getenv("DB_PATH", "./sns_management.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def insert_event(event: dict) -> int | None:
    """중복 external_id는 무시 (UNIQUE 제약). 반환값: 삽입된 id 또는 None."""
    try:
        with get_conn() as conn:
            cur = conn.execute("""
                INSERT OR IGNORE INTO monitoring_events
                  (platform, event_type, external_id, author, text,
                   sentiment, severity, raw_json, url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event["platform"],
                event.get("event_type", "mention"),
                event.get("external_id"),
                event.get("author"),
                event["text"],
                event.get("sentiment", "neutral"),
                event.get("severity", "info"),
                json.dumps(event.get("raw", {}), ensure_ascii=False),
                event.get("url"),
            ))
            conn.commit()
            return cur.lastrowid if cur.lastrowid else None
    except sqlite3.IntegrityError:
        return None


def get_event(event_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM monitoring_events WHERE id = ?", (event_id,)
        ).fetchone()
        return dict(row) if row else None


def list_events(limit: int = 100, severity: str = None) -> list:
    with get_conn() as conn:
        if severity:
            rows = conn.execute(
                "SELECT * FROM monitoring_events WHERE severity = ? ORDER BY detected_at DESC LIMIT ?",
                (severity, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM monitoring_events ORDER BY detected_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]


def count_events_by_severity() -> dict:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT severity, COUNT(*) as cnt FROM monitoring_events GROUP BY severity"
        ).fetchall()
        return {r["severity"]: r["cnt"] for r in rows}


def insert_notification(
    title: str,
    body: str = None,
    type_: str = "monitor_alert",
    severity: str = "info",
    event_id: int = None,
    queue_id: int = None,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO notifications (type, title, body, severity, related_event_id, related_queue_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (type_, title, body, severity, event_id, queue_id),
        )
        conn.commit()
        return cur.lastrowid


def list_notifications(limit: int = 100, unread_only: bool = False) -> list:
    with get_conn() as conn:
        if unread_only:
            rows = conn.execute(
                "SELECT * FROM notifications WHERE read_at IS NULL ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM notifications ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]


def count_unread() -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM notifications WHERE read_at IS NULL"
        ).fetchone()
        return row[0]


def mark_read(notif_id: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE notifications SET read_at = datetime('now') WHERE id = ?",
            (notif_id,),
        )
        conn.commit()


def mark_all_read():
    with get_conn() as conn:
        conn.execute(
            "UPDATE notifications SET read_at = datetime('now') WHERE read_at IS NULL"
        )
        conn.commit()


def get_cursor(platform: str) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM monitor_cursors WHERE platform = ?", (platform,)
        ).fetchone()
        return dict(row) if row else {"platform": platform, "last_since_id": None, "last_run_at": None, "last_error": None}


def get_account_stats() -> list:
    """플랫폼별 최신 스냅샷 + 7일 전 스냅샷을 묶어 변화량 계산."""
    with get_conn() as conn:
        platforms = ["x", "facebook", "instagram"]
        result = []
        for p in platforms:
            rows = conn.execute(
                "SELECT * FROM account_snapshots WHERE platform = ? ORDER BY captured_at DESC LIMIT 2",
                (p,),
            ).fetchall()
            if not rows:
                continue
            now = dict(rows[0])
            now["extra"] = json.loads(now.get("extra_json") or "{}")
            prev = dict(rows[1]) if len(rows) > 1 else None
            if prev:
                prev["extra"] = json.loads(prev.get("extra_json") or "{}")
                now["followers_delta"] = now["followers"] - prev["followers"]
            else:
                now["followers_delta"] = 0
            result.append(now)
        return result


def update_cursor(platform: str, last_since_id: str = None, error: str = None):
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE monitor_cursors
            SET last_since_id = COALESCE(?, last_since_id),
                last_run_at   = datetime('now'),
                last_error    = ?
            WHERE platform = ?
            """,
            (last_since_id, error, platform),
        )
        conn.commit()

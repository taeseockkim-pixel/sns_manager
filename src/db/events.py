"""
monitoring_events, notifications, monitor_cursors CRUD — PostgreSQL 버전
"""

import json

from src.db.db import db_cursor


def _row(r):
    """RealDictRow → plain dict, datetime → ISO 문자열."""
    if r is None:
        return None
    d = dict(r)
    for k, v in d.items():
        if hasattr(v, "strftime"):
            d[k] = v.strftime("%Y-%m-%d %H:%M:%S")
    return d


def insert_event(event: dict) -> int | None:
    """중복 (platform, external_id) 는 무시. 삽입된 id 반환, 중복이면 None."""
    with db_cursor() as cur:
        cur.execute("""
            INSERT INTO monitoring_events
              (platform, event_type, external_id, author, text,
               sentiment, severity, raw_json, url)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (platform, external_id) DO NOTHING
            RETURNING id
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
        row = cur.fetchone()
        return row["id"] if row else None


def get_event(event_id: int) -> dict | None:
    with db_cursor() as cur:
        cur.execute("SELECT * FROM monitoring_events WHERE id = %s", (event_id,))
        return _row(cur.fetchone())


def list_events(limit: int = 100, severity: str = None) -> list:
    with db_cursor() as cur:
        if severity:
            cur.execute(
                "SELECT * FROM monitoring_events WHERE severity = %s ORDER BY detected_at DESC LIMIT %s",
                (severity, limit),
            )
        else:
            cur.execute(
                "SELECT * FROM monitoring_events ORDER BY detected_at DESC LIMIT %s",
                (limit,),
            )
        return [_row(r) for r in cur.fetchall()]


def count_events_by_severity() -> dict:
    with db_cursor() as cur:
        cur.execute("SELECT severity, COUNT(*) as cnt FROM monitoring_events GROUP BY severity")
        return {r["severity"]: r["cnt"] for r in cur.fetchall()}


def insert_notification(
    title: str,
    body: str = None,
    type_: str = "monitor_alert",
    severity: str = "info",
    event_id: int = None,
    queue_id: int = None,
) -> int:
    with db_cursor() as cur:
        cur.execute("""
            INSERT INTO notifications (type, title, body, severity, related_event_id, related_queue_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (type_, title, body, severity, event_id, queue_id))
        return cur.fetchone()["id"]


def list_notifications(limit: int = 100, unread_only: bool = False) -> list:
    with db_cursor() as cur:
        if unread_only:
            cur.execute(
                "SELECT * FROM notifications WHERE read_at IS NULL ORDER BY created_at DESC LIMIT %s",
                (limit,),
            )
        else:
            cur.execute(
                "SELECT * FROM notifications ORDER BY created_at DESC LIMIT %s",
                (limit,),
            )
        return [_row(r) for r in cur.fetchall()]


def count_unread() -> int:
    with db_cursor() as cur:
        cur.execute("SELECT COUNT(*) as cnt FROM notifications WHERE read_at IS NULL")
        return cur.fetchone()["cnt"]


def mark_read(notif_id: int):
    with db_cursor() as cur:
        cur.execute("UPDATE notifications SET read_at = NOW() WHERE id = %s", (notif_id,))


def mark_all_read():
    with db_cursor() as cur:
        cur.execute("UPDATE notifications SET read_at = NOW() WHERE read_at IS NULL")


def get_cursor(platform: str) -> dict:
    """monitor_cursors 테이블에서 플랫폼 커서 정보 조회."""
    with db_cursor() as cur:
        cur.execute("SELECT * FROM monitor_cursors WHERE platform = %s", (platform,))
        row = cur.fetchone()
        return _row(row) if row else {"platform": platform, "last_since_id": None, "last_run_at": None, "last_error": None}


def get_account_stats() -> list:
    """플랫폼별 최신 스냅샷 + 이전 스냅샷으로 변화량 계산."""
    with db_cursor() as cur:
        result = []
        for p in ["x", "facebook", "instagram"]:
            cur.execute(
                "SELECT * FROM account_snapshots WHERE platform = %s ORDER BY captured_at DESC LIMIT 2",
                (p,),
            )
            rows = cur.fetchall()
            if not rows:
                continue
            now = _row(rows[0])
            now["extra"] = json.loads(now.get("extra_json") or "{}")
            prev = _row(rows[1]) if len(rows) > 1 else None
            if prev:
                prev["extra"] = json.loads(prev.get("extra_json") or "{}")
                now["followers_delta"] = now["followers"] - prev["followers"]
            else:
                now["followers_delta"] = 0
            result.append(now)
        return result


def save_account_snapshot(platform: str, followers: int = 0, following: int = 0, post_count: int = 0, extra: dict = None) -> None:
    """플랫폼 계정 통계 스냅샷 저장 (hourly_monitor_job에서 호출)."""
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO account_snapshots (platform, followers, following, post_count, extra_json) VALUES (%s, %s, %s, %s, %s)",
            (platform, followers, following, post_count, json.dumps(extra or {})),
        )


def save_reply_draft(event_id: int, draft: str) -> None:
    with db_cursor() as cur:
        cur.execute(
            "UPDATE monitoring_events SET reply_draft = %s WHERE id = %s",
            (draft, event_id),
        )


def update_cursor(platform: str, last_since_id: str = None, error: str = None):
    with db_cursor() as cur:
        cur.execute("""
            UPDATE monitor_cursors
            SET last_since_id = COALESCE(%s, last_since_id),
                last_run_at   = NOW(),
                last_error    = %s
            WHERE platform = %s
        """, (last_since_id, error, platform))

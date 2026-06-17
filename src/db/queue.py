"""
H-12: 승인 대기 콘텐츠를 PostgreSQL approval_queue 테이블에 저장/관리
CLI 사용: python src/db/queue.py [list|approve <id>|reject <id> "이유"]
"""

import json
import sys
from datetime import datetime

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


def enqueue(content: dict) -> int:
    with db_cursor() as cur:
        cur.execute("""
            INSERT INTO approval_queue
              (platform, topic, ko_text, ko_hashtags, en_text, en_hashtags,
               brand_safety_score, scheduled_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            content["platform"],
            content.get("topic", ""),
            content["ko"]["text"],
            json.dumps(content["ko"].get("hashtags", []), ensure_ascii=False),
            content["en"]["text"],
            json.dumps(content["en"].get("hashtags", []), ensure_ascii=False),
            content["brand_safety_score"],
            content.get("scheduled_at"),
        ))
        return cur.fetchone()["id"]


def list_pending():
    with db_cursor() as cur:
        cur.execute(
            "SELECT * FROM approval_queue WHERE approved = 0 AND rejection_reason IS NULL ORDER BY created_at"
        )
        return [_row(r) for r in cur.fetchall()]


def approve(queue_id: int, reviewer: str = "manual"):
    """H-01: 사람이 직접 호출하는 승인 함수."""
    with db_cursor() as cur:
        cur.execute("""
            UPDATE approval_queue
            SET approved = 1, reviewed_at = NOW(), reviewed_by = %s
            WHERE id = %s
        """, (reviewer, queue_id))


def reject(queue_id: int, reason: str, reviewer: str = "manual"):
    with db_cursor() as cur:
        cur.execute("""
            UPDATE approval_queue
            SET rejection_reason = %s, reviewed_at = NOW(), reviewed_by = %s
            WHERE id = %s
        """, (reason, reviewer, queue_id))


def list_all(status: str = None) -> list:
    """status: 'pending' | 'approved' | 'rejected' | None (전체)."""
    with db_cursor() as cur:
        if status == "pending":
            cur.execute(
                "SELECT * FROM approval_queue WHERE approved = 0 AND rejection_reason IS NULL ORDER BY created_at DESC"
            )
        elif status == "approved":
            cur.execute(
                "SELECT * FROM approval_queue WHERE approved = 1 ORDER BY reviewed_at DESC"
            )
        elif status == "rejected":
            cur.execute(
                "SELECT * FROM approval_queue WHERE rejection_reason IS NOT NULL ORDER BY reviewed_at DESC"
            )
        else:
            cur.execute("SELECT * FROM approval_queue ORDER BY created_at DESC")
        return [_row(r) for r in cur.fetchall()]


def get(queue_id: int) -> dict | None:
    with db_cursor() as cur:
        cur.execute("SELECT * FROM approval_queue WHERE id = %s", (queue_id,))
        return _row(cur.fetchone())


def count_by_status() -> dict:
    with db_cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) as cnt FROM approval_queue WHERE approved = 0 AND rejection_reason IS NULL"
        )
        pending = cur.fetchone()["cnt"]
        cur.execute("SELECT COUNT(*) as cnt FROM approval_queue WHERE approved = 1")
        approved = cur.fetchone()["cnt"]
        cur.execute("SELECT COUNT(*) as cnt FROM approval_queue WHERE rejection_reason IS NOT NULL")
        rejected = cur.fetchone()["cnt"]
        return {"pending": pending, "approved": approved, "rejected": rejected}


def list_publish_log(limit: int = 100) -> list:
    with db_cursor() as cur:
        cur.execute("""
            SELECT pl.*, aq.platform as queue_platform, aq.topic, aq.brand_safety_score,
                   aq.reviewed_by, aq.ko_text
            FROM publish_log pl
            LEFT JOIN approval_queue aq ON pl.queue_id = aq.id
            ORDER BY pl.published_at DESC LIMIT %s
        """, (limit,))
        return [_row(r) for r in cur.fetchall()]


def count_published_today() -> int:
    with db_cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) as cnt FROM publish_log WHERE published_at::date = CURRENT_DATE AND status = 'success'"
        )
        return cur.fetchone()["cnt"]


def log_publish(queue_id: int, platform: str, platform_post_id: str = None, status: str = "success", error: str = None):
    with db_cursor() as cur:
        cur.execute("""
            INSERT INTO publish_log (queue_id, platform, platform_post_id, status, error_message)
            VALUES (%s, %s, %s, %s, %s)
        """, (queue_id, platform, platform_post_id, status, error))


def _print_pending():
    items = list_pending()
    if not items:
        print("승인 대기 중인 콘텐츠가 없습니다.")
        return
    print(f"\n{'='*60}")
    print(f"승인 대기 목록 ({len(items)}건)")
    print(f"{'='*60}")
    for item in items:
        print(f"\n[ID: {item['id']}] {item['platform'].upper()} | 점수: {item['brand_safety_score']}/100")
        print(f"주제: {item['topic']}")
        print(f"국문: {item['ko_text'][:80]}{'...' if len(item['ko_text']) > 80 else ''}")
        print(f"영문: {item['en_text'][:80]}{'...' if len(item['en_text']) > 80 else ''}")
        print(f"등록: {item['created_at']}")
        print(f"  승인: python src/db/queue.py approve {item['id']}")
        print(f"  반려: python src/db/queue.py reject {item['id']} \"반려 이유\"")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"

    if cmd == "list":
        _print_pending()
    elif cmd == "approve" and len(sys.argv) >= 3:
        approve(int(sys.argv[2]))
    elif cmd == "reject" and len(sys.argv) >= 4:
        reject(int(sys.argv[2]), sys.argv[3])
    else:
        print("사용법: python src/db/queue.py [list | approve <id> | reject <id> \"이유\"]")

"""
H-12: 승인 대기 중인 콘텐츠를 SQLite approval_queue 테이블에 저장/관리
CLI 사용: python src/db/queue.py [list|approve <id>|reject <id> "이유"]
"""

import sqlite3
import json
import os
import sys
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "./sns_management.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
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
        conn.commit()
    print(f"DB initialized: {DB_PATH}")


def enqueue(content: dict) -> int:
    with get_conn() as conn:
        cursor = conn.execute("""
            INSERT INTO approval_queue
              (platform, topic, ko_text, ko_hashtags, en_text, en_hashtags,
               brand_safety_score, scheduled_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
        conn.commit()
        return cursor.lastrowid


def list_pending():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM approval_queue WHERE approved = 0 AND rejection_reason IS NULL ORDER BY created_at"
        ).fetchall()
        return [dict(r) for r in rows]


def approve(queue_id: int, reviewer: str = "manual"):
    """H-01: 사람이 직접 호출하는 승인 함수."""
    with get_conn() as conn:
        conn.execute("""
            UPDATE approval_queue
            SET approved = 1, reviewed_at = datetime('now'), reviewed_by = ?
            WHERE id = ?
        """, (reviewer, queue_id))
        conn.commit()
    print(f"✅ ID {queue_id} 승인 완료 (by {reviewer})")


def reject(queue_id: int, reason: str, reviewer: str = "manual"):
    with get_conn() as conn:
        conn.execute("""
            UPDATE approval_queue
            SET rejection_reason = ?, reviewed_at = datetime('now'), reviewed_by = ?
            WHERE id = ?
        """, (reason, reviewer, queue_id))
        conn.commit()
    print(f"❌ ID {queue_id} 반려 완료: {reason}")


def list_all(status: str = None) -> list:
    """status: 'pending' | 'approved' | 'rejected' | None (전체)."""
    with get_conn() as conn:
        if status == "pending":
            rows = conn.execute(
                "SELECT * FROM approval_queue WHERE approved = 0 AND rejection_reason IS NULL ORDER BY created_at DESC"
            ).fetchall()
        elif status == "approved":
            rows = conn.execute(
                "SELECT * FROM approval_queue WHERE approved = 1 ORDER BY reviewed_at DESC"
            ).fetchall()
        elif status == "rejected":
            rows = conn.execute(
                "SELECT * FROM approval_queue WHERE rejection_reason IS NOT NULL ORDER BY reviewed_at DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM approval_queue ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]


def get(queue_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM approval_queue WHERE id = ?", (queue_id,)
        ).fetchone()
        return dict(row) if row else None


def count_by_status() -> dict:
    with get_conn() as conn:
        pending = conn.execute(
            "SELECT COUNT(*) FROM approval_queue WHERE approved = 0 AND rejection_reason IS NULL"
        ).fetchone()[0]
        approved = conn.execute(
            "SELECT COUNT(*) FROM approval_queue WHERE approved = 1"
        ).fetchone()[0]
        rejected = conn.execute(
            "SELECT COUNT(*) FROM approval_queue WHERE rejection_reason IS NOT NULL"
        ).fetchone()[0]
        return {"pending": pending, "approved": approved, "rejected": rejected}


def list_publish_log(limit: int = 100) -> list:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT pl.*, aq.platform as queue_platform, aq.topic, aq.brand_safety_score,
                   aq.reviewed_by, aq.ko_text
            FROM publish_log pl
            LEFT JOIN approval_queue aq ON pl.queue_id = aq.id
            ORDER BY pl.published_at DESC LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]


def count_published_today() -> int:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM publish_log WHERE date(published_at) = date('now') AND status = 'success'"
        ).fetchone()
        return row[0]


def log_publish(queue_id: int, platform: str, platform_post_id: str = None, status: str = "success", error: str = None):
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO publish_log (queue_id, platform, platform_post_id, status, error_message)
            VALUES (?, ?, ?, ?, ?)
        """, (queue_id, platform, platform_post_id, status, error))
        conn.commit()


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
    init_db()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"

    if cmd == "list":
        _print_pending()
    elif cmd == "approve" and len(sys.argv) >= 3:
        approve(int(sys.argv[2]))
    elif cmd == "reject" and len(sys.argv) >= 4:
        reject(int(sys.argv[2]), sys.argv[3])
    else:
        print("사용법: python src/db/queue.py [list | approve <id> | reject <id> \"이유\"]")

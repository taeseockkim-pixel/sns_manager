"""
DB 기반 자격증명 저장소 — Vercel 서버리스 환경에서 .env 대체
credentials 테이블에 key/value로 저장, 앱 시작 시 os.environ에 로드
"""

import os

from src.db.db import db_cursor


def get(key: str) -> str | None:
    with db_cursor() as cur:
        cur.execute("SELECT value FROM credentials WHERE key = %s", (key,))
        row = cur.fetchone()
        return row["value"] if row else None


def upsert(key: str, value: str) -> None:
    with db_cursor() as cur:
        cur.execute(
            """
            INSERT INTO credentials (key, value, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
            """,
            (key, value),
        )
    os.environ[key] = value


def load_all_to_env() -> None:
    """앱 시작 시 DB 자격증명을 os.environ에 로드 (이미 설정된 env 값 우선)."""
    try:
        with db_cursor() as cur:
            cur.execute("SELECT key, value FROM credentials")
            for row in cur.fetchall():
                if not os.environ.get(row["key"]):
                    os.environ[row["key"]] = row["value"]
    except Exception:
        pass

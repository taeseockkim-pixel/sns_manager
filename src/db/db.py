"""
PostgreSQL 공통 커넥션 헬퍼 — Vercel 서버리스 환경에서 매 요청마다 연결 생성/종료
"""

import os
from contextlib import contextmanager

import psycopg2
import psycopg2.extras


@contextmanager
def db_cursor():
    conn = psycopg2.connect(os.environ["DATABASE_URL"], cursor_factory=psycopg2.extras.RealDictCursor)
    cur = conn.cursor()
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

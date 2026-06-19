"""
PostgreSQL 커넥션 풀 헬퍼 — ThreadedConnectionPool로 TLS 핸드셰이크 재사용
"""

import os
import threading
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
import psycopg2.pool


_pool: "psycopg2.pool.ThreadedConnectionPool | None" = None
_pool_lock = threading.Lock()


def _get_pool() -> "psycopg2.pool.ThreadedConnectionPool":
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = psycopg2.pool.ThreadedConnectionPool(
                    minconn=1,
                    maxconn=5,
                    dsn=os.environ["DATABASE_URL"],
                )
    return _pool


def warm_up() -> None:
    """시작 시 첫 번째 DB 연결을 미리 수립해 첫 요청 지연을 제거한다."""
    pool = _get_pool()
    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        conn.commit()
    finally:
        pool.putconn(conn)


@contextmanager
def db_cursor():
    pool = _get_pool()
    conn = pool.getconn()
    conn.autocommit = True
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield cur
    except Exception:
        raise
    finally:
        cur.close()
        conn.autocommit = False
        pool.putconn(conn)

"""
asyncio.Queue 기반 pub/sub 버스
APScheduler 스레드 → FastAPI asyncio 루프 thread-safe 전달
"""

import asyncio
import uuid
from typing import Dict

_subscribers: Dict[str, asyncio.Queue] = {}
_loop: asyncio.AbstractEventLoop = None


def set_loop(loop: asyncio.AbstractEventLoop):
    """FastAPI lifespan 시작 시 현재 이벤트 루프 등록."""
    global _loop
    _loop = loop


def subscribe() -> tuple[str, asyncio.Queue]:
    client_id = str(uuid.uuid4())
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    _subscribers[client_id] = q
    return client_id, q


def unsubscribe(client_id: str):
    _subscribers.pop(client_id, None)


def publish(event: dict):
    """스레드 안전 발행 — APScheduler 스레드에서도 호출 가능."""
    if not _loop or not _subscribers:
        return
    for q in list(_subscribers.values()):
        try:
            _loop.call_soon_threadsafe(q.put_nowait, event)
        except asyncio.QueueFull:
            pass

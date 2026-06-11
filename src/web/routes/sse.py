"""
SSE (Server-Sent Events) 엔드포인트 — 브라우저에 실시간 이벤트 푸시
"""

import asyncio
import json
import time

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from src.notify import bus
from src.db import events as events_db

router = APIRouter()

_MAX_CONNECTION_SECONDS = 3600  # 1시간 후 자동 종료 → 클라이언트가 재연결


@router.get("/events")
async def sse_events(request: Request):
    client_id, queue = bus.subscribe()

    async def event_generator():
        deadline = time.monotonic() + _MAX_CONNECTION_SECONDS
        try:
            unread = events_db.count_unread()
            yield f"event: init\ndata: {json.dumps({'unread_count': unread})}\n\n"

            while time.monotonic() < deadline:
                # 끊김 먼저 확인 (Starlette is_disconnected는 논블로킹)
                if await request.is_disconnected():
                    break

                try:
                    event = await asyncio.wait_for(queue.get(), timeout=5)
                except asyncio.TimeoutError:
                    # 5초마다 끊김 재확인 후 keepalive
                    if await request.is_disconnected():
                        break
                    yield ": keepalive\n\n"
                    continue

                # 이벤트 수신 직후에도 끊김 확인
                if await request.is_disconnected():
                    break

                if event.get("type") == "notification.new":
                    event["unread_count"] = events_db.count_unread()
                yield f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

        finally:
            bus.unsubscribe(client_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

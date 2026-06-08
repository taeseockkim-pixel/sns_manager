"""
SSE (Server-Sent Events) 엔드포인트 — 브라우저에 실시간 이벤트 푸시
"""

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from src.notify import bus
from src.db import events as events_db

router = APIRouter()


@router.get("/events")
async def sse_events(request: Request):
    client_id, queue = bus.subscribe()

    async def event_generator():
        try:
            # 초기 연결 시 미열람 알림 수 전송
            unread = events_db.count_unread()
            yield f"event: init\ndata: {json.dumps({'unread_count': unread})}\n\n"

            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=25)
                    # notification.new 이벤트에 최신 미열람 수 추가
                    if event.get("type") == "notification.new":
                        event["unread_count"] = events_db.count_unread()
                    yield f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
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

"""
POST 액션 라우터 — 승인/반려/게시/알림 읽음 처리
H-01: 모든 게시 전 DB에서 approved=1 재확인
"""

import asyncio
import json
import os
import subprocess
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.db import queue as queue_db
from src.db import events as events_db
from src.notify import bus
from src.web.auth import verify_credentials

router = APIRouter()

_TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATE_DIR))

_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent


@router.post("/queue/{queue_id}/approve", response_class=HTMLResponse)
async def approve_content(
    request: Request,
    queue_id: int,
    reviewer: str = Depends(verify_credentials),
):
    queue_db.approve(queue_id, reviewer=reviewer)
    events_db.insert_notification(
        title=f"콘텐츠 승인됨 (ID: {queue_id})",
        type_="queue_new",
        severity="success",
        queue_id=queue_id,
    )
    bus.publish({"type": "queue.updated", "id": queue_id, "status": "approved"})

    item = queue_db.get(queue_id)
    return templates.TemplateResponse(request, "partials/queue_row.html", {"item": item})


@router.post("/queue/{queue_id}/reject", response_class=HTMLResponse)
async def reject_content(
    request: Request,
    queue_id: int,
    hx_prompt: str = Header(default="", alias="HX-Prompt"),
    reviewer: str = Depends(verify_credentials),
):
    reason = hx_prompt.strip() if hx_prompt.strip() else "사유 미입력"
    queue_db.reject(queue_id, reason=reason, reviewer=reviewer)
    bus.publish({"type": "queue.updated", "id": queue_id, "status": "rejected"})

    item = queue_db.get(queue_id)
    return templates.TemplateResponse(request, "partials/queue_row.html", {"item": item})


@router.post("/publish/{queue_id}", response_class=HTMLResponse)
async def publish_content(
    request: Request,
    queue_id: int,
    reviewer: str = Depends(verify_credentials),
):
    item = queue_db.get(queue_id)
    if not item:
        return HTMLResponse("<tr><td colspan='6' class='text-red-600 p-4'>항목을 찾을 수 없습니다.</td></tr>")
    if not item.get("approved"):
        return HTMLResponse("<tr><td colspan='6' class='text-red-600 p-4'>H-01: 승인되지 않은 콘텐츠입니다.</td></tr>")

    api_mode = os.getenv("API_MODE", "mock").lower()
    try:
        if api_mode == "mock":
            mock_post_id = f"mock-{item['platform']}-{uuid.uuid4().hex[:8]}"
            queue_db.log_publish(queue_id, item["platform"], platform_post_id=mock_post_id, status="success")
            events_db.insert_notification(
                title=f"[MOCK] 게시 완료 (ID: {queue_id})",
                body=f"Mock 게시 ID: {mock_post_id}",
                type_="publish_success",
                severity="success",
                queue_id=queue_id,
            )
            bus.publish({"type": "queue.updated", "id": queue_id, "status": "published"})
        else:
            post_id = _publish_live(item)
            queue_db.log_publish(queue_id, item["platform"], platform_post_id=post_id, status="success")
            events_db.insert_notification(
                title=f"게시 완료 (ID: {queue_id})",
                type_="publish_success",
                severity="success",
                queue_id=queue_id,
            )
            bus.publish({"type": "queue.updated", "id": queue_id, "status": "published"})
    except Exception as exc:
        error_msg = str(exc)[:300]
        queue_db.log_publish(queue_id, item["platform"], status="error", error=error_msg)
        events_db.insert_notification(
            title=f"게시 오류 (ID: {queue_id})",
            body=error_msg,
            type_="api_error",
            severity="critical",
        )

    item = queue_db.get(queue_id)
    return templates.TemplateResponse(request, "partials/queue_row.html", {"item": item})


def _publish_live(item: dict) -> str:
    """H-01: 승인된 콘텐츠를 실제 플랫폼에 게시. 플랫폼별 클라이언트 호출."""
    platform = item["platform"]
    text = item.get("ko_text", "")

    if platform == "x":
        from src.api.x_client import post_tweet
        result = post_tweet(text)
        return result.get("id", "")
    elif platform == "facebook":
        from src.api.meta_client import post_to_page
        result = post_to_page(text)
        return result.get("id", "")
    elif platform == "instagram":
        from src.api.meta_client import post_to_instagram
        image_url = item.get("image_url", "")
        if not image_url:
            raise ValueError("Instagram 게시에는 image_url이 필요합니다.")
        result = post_to_instagram(image_url=image_url, caption=text)
        return result.get("id", "")
    else:
        raise ValueError(f"지원하지 않는 플랫폼: {platform}")


@router.patch("/notifications/{notif_id}/read", response_class=HTMLResponse)
async def mark_notification_read(notif_id: int):
    events_db.mark_read(notif_id)
    return HTMLResponse("")


@router.post("/notifications/read-all", response_class=HTMLResponse)
async def mark_all_read():
    events_db.mark_all_read()
    bus.publish({"type": "notification.new", "unread_count": 0})
    return HTMLResponse('<span id="notif-count-wrapper"></span>')


@router.get("/partial/monitor-event/{event_id}", response_class=HTMLResponse)
async def partial_monitor_event(request: Request, event_id: int):
    event = events_db.get_event(event_id)
    if not event:
        return HTMLResponse("")
    return templates.TemplateResponse(request, "partials/monitor_event_row.html", {"event": event})

"""
GET 페이지 라우터 — 6개 페이지 렌더링
"""

import os
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates

from src.db import queue as queue_db
from src.db import events as events_db

router = APIRouter()

_TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATE_DIR))

_DELIVERABLES_DIR = Path(__file__).parent.parent.parent.parent / "deliverables"


def _next_monitor_info() -> dict:
    try:
        from src.scheduler.runner import scheduler
        job = scheduler.get_job("hourly_monitor")
        if job and job.next_run_time:
            nrt = job.next_run_time
            now = datetime.now(nrt.tzinfo)
            diff = int((nrt - now).total_seconds())
            minutes = diff // 60
            seconds = diff % 60
            return {
                "next_run": nrt.strftime("%H:%M"),
                "remaining": f"{minutes}분 {seconds}초",
                "remaining_seconds": diff,
            }
    except Exception:
        pass
    return {"next_run": "-", "remaining": "-", "remaining_seconds": 0}


def _last_monitor_info() -> str:
    try:
        x_cursor = events_db.get_cursor("x")
        return x_cursor.get("last_run_at") or "아직 실행 전"
    except Exception:
        return "-"


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    counts = queue_db.count_by_status()
    today_published = queue_db.count_published_today()
    recent_queue = queue_db.list_all("pending")[:3]
    recent_events = events_db.list_events(limit=5)
    unread_count = events_db.count_unread()
    event_counts = events_db.count_events_by_severity()
    monitor_info = _next_monitor_info()
    last_run = _last_monitor_info()
    api_mode = "live" if os.getenv("ANTHROPIC_API_KEY") else "mock"
    account_stats = events_db.get_account_stats()

    return templates.TemplateResponse(request, "dashboard.html", {
        "page": "dashboard",
        "counts": counts,
        "today_published": today_published,
        "recent_queue": recent_queue,
        "recent_events": recent_events,
        "unread_count": unread_count,
        "event_counts": event_counts,
        "monitor_info": monitor_info,
        "last_run": last_run,
        "api_mode": api_mode,
        "account_stats": account_stats,
    })


@router.get("/queue", response_class=HTMLResponse)
async def queue_page(request: Request, status: str = Query(default="pending")):
    valid = {"pending", "approved", "rejected", "all"}
    if status not in valid:
        status = "pending"
    items = queue_db.list_all(None if status == "all" else status)
    counts = queue_db.count_by_status()
    unread_count = events_db.count_unread()

    return templates.TemplateResponse(request, "queue.html", {
        "page": "queue",
        "items": items,
        "status": status,
        "counts": counts,
        "unread_count": unread_count,
    })


@router.get("/monitoring", response_class=HTMLResponse)
async def monitoring_page(request: Request, severity: str = Query(default="")):
    events = events_db.list_events(limit=100, severity=severity or None)
    event_counts = events_db.count_events_by_severity()
    monitor_info = _next_monitor_info()
    last_run = _last_monitor_info()
    unread_count = events_db.count_unread()
    account_stats = events_db.get_account_stats()

    return templates.TemplateResponse(request, "monitoring.html", {
        "page": "monitoring",
        "events": events,
        "event_counts": event_counts,
        "severity_filter": severity,
        "monitor_info": monitor_info,
        "last_run": last_run,
        "unread_count": unread_count,
        "account_stats": account_stats,
    })


@router.get("/notifications", response_class=HTMLResponse)
async def notifications_page(request: Request):
    notifications = events_db.list_notifications(limit=100)
    unread_count = events_db.count_unread()

    return templates.TemplateResponse(request, "notifications.html", {
        "page": "notifications",
        "notifications": notifications,
        "unread_count": unread_count,
    })


@router.get("/publish-log", response_class=HTMLResponse)
async def publish_log_page(request: Request):
    logs = queue_db.list_publish_log(limit=100)
    unread_count = events_db.count_unread()

    return templates.TemplateResponse(request, "publish_log.html", {
        "page": "publish_log",
        "logs": logs,
        "unread_count": unread_count,
    })


@router.get("/deliverables", response_class=HTMLResponse)
async def deliverables_page(request: Request):
    files = []
    if _DELIVERABLES_DIR.exists():
        for md_file in sorted(_DELIVERABLES_DIR.glob("*.md")):
            stat = md_file.stat()
            files.append({
                "name": md_file.name,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            })

    unread_count = events_db.count_unread()
    return templates.TemplateResponse(request, "deliverables.html", {
        "page": "deliverables",
        "files": files,
        "unread_count": unread_count,
    })


@router.get("/deliverables/view/{filename}", response_class=HTMLResponse)
async def view_deliverable(request: Request, filename: str):
    import markdown as md_lib
    safe_name = Path(filename).name
    file_path = _DELIVERABLES_DIR / safe_name
    if not file_path.exists() or file_path.suffix != ".md":
        return HTMLResponse("<p>파일을 찾을 수 없습니다.</p>", status_code=404)

    content_md = file_path.read_text(encoding="utf-8")
    content_html = md_lib.markdown(content_md, extensions=["tables", "fenced_code"])
    unread_count = events_db.count_unread()

    return templates.TemplateResponse(request, "deliverable_view.html", {
        "page": "deliverables",
        "filename": safe_name,
        "content_html": content_html,
        "unread_count": unread_count,
    })


@router.get("/deliverables/download/{filename}")
async def download_deliverable(filename: str):
    safe_name = Path(filename).name
    file_path = _DELIVERABLES_DIR / safe_name
    if not file_path.exists() or file_path.suffix != ".md":
        return HTMLResponse("파일을 찾을 수 없습니다.", status_code=404)
    return FileResponse(str(file_path), filename=safe_name, media_type="text/markdown")

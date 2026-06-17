"""
Vercel Cron Jobs 엔드포인트 — APScheduler 대체
CRON_SECRET 환경변수로 무단 호출 방지 (Vercel이 Authorization: Bearer <CRON_SECRET> 헤더 자동 첨부)
"""

import os

from fastapi import APIRouter, Header, HTTPException

router = APIRouter()


def _verify(authorization: str):
    secret = os.environ.get("CRON_SECRET", "")
    if not secret or authorization != f"Bearer {secret}":
        raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/cron/hourly-monitor")
async def cron_hourly_monitor(authorization: str = Header("")):
    _verify(authorization)
    from src.scheduler.jobs import hourly_monitor_job
    hourly_monitor_job()
    return {"ok": True, "job": "hourly_monitor"}


@router.post("/cron/daily-meta-token")
async def cron_daily_meta_token(authorization: str = Header("")):
    _verify(authorization)
    from src.scheduler.jobs import daily_meta_token_check
    daily_meta_token_check()
    return {"ok": True, "job": "daily_meta_token"}


@router.post("/cron/daily-threads-token")
async def cron_daily_threads_token(authorization: str = Header("")):
    _verify(authorization)
    from src.scheduler.jobs import daily_threads_token_check
    daily_threads_token_check()
    return {"ok": True, "job": "daily_threads_token"}

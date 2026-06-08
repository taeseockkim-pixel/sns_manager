"""
APScheduler BackgroundScheduler 초기화 및 등록
"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.scheduler.jobs import hourly_monitor_job

scheduler = BackgroundScheduler(timezone="Asia/Seoul")

scheduler.add_job(
    hourly_monitor_job,
    trigger=IntervalTrigger(hours=1),
    id="hourly_monitor",
    coalesce=True,
    max_instances=1,
    misfire_grace_time=300,
)

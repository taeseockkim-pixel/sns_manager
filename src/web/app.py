"""
FastAPI 앱 — lifespan, 라우터 마운트, 정적 파일
"""

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.db.migrations import init_db_extensions
from src.db.seed import seed_mock_data
from src.notify import bus
from src.scheduler import runner
from src.web.routes import dashboard, actions, sse


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db_extensions()
    seed_mock_data()
    bus.set_loop(asyncio.get_event_loop())
    runner.scheduler.start()
    yield
    runner.scheduler.shutdown(wait=False)


app = FastAPI(
    title="CIMON SNS Manager",
    lifespan=lifespan,
)

_STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

app.include_router(dashboard.router)
app.include_router(actions.router)
app.include_router(sse.router)

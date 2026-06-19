"""
FastAPI 앱 — lifespan, 라우터 마운트, 정적 파일
"""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parent.parent.parent / "config" / ".env"
load_dotenv(_ENV_PATH, override=True)

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from src.db.migrations import init_db_extensions
from src.notify import bus
from src.web.routes import dashboard, actions, sse, generate, setup, cron


@asynccontextmanager
async def lifespan(app: FastAPI):
    import os
    from src.db import creds as creds_db
    from src.db.db import warm_up
    init_db_extensions()
    creds_db.load_all_to_env()
    if os.getenv("WIPE_MOCK_ON_START") == "true":
        from src.db.migrations import wipe_mock_events
        wipe_mock_events()
    warm_up()
    bus.set_loop(asyncio.get_running_loop())
    yield


app = FastAPI(
    title="CIMON SNS Manager",
    lifespan=lifespan,
)

@app.get("/ping")
def ping():
    return PlainTextResponse("pong")

_STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

app.include_router(dashboard.router)
app.include_router(actions.router)
app.include_router(sse.router)
app.include_router(generate.router)
app.include_router(setup.router)
app.include_router(cron.router)

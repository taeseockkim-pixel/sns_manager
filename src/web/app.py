"""
FastAPI 앱 — lifespan, 라우터 마운트, 정적 파일
"""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parent.parent.parent / "config" / ".env"
load_dotenv(_ENV_PATH, override=True)

from fastapi import FastAPI, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from src.db.migrations import init_db_extensions
from src.db.seed import seed_mock_data
from src.notify import bus
from src.web.routes import dashboard, actions, sse, generate, setup, cron


@asynccontextmanager
async def lifespan(app: FastAPI):
    from src.db import creds as creds_db
    creds_db.load_all_to_env()
    init_db_extensions()
    seed_mock_data()
    bus.set_loop(asyncio.get_running_loop())
    yield


app = FastAPI(
    title="CIMON SNS Manager",
    lifespan=lifespan,
)


@app.middleware("http")
async def force_utf8_charset(request: Request, call_next) -> Response:
    response = await call_next(request)
    ct = response.headers.get("content-type", "")
    if "text/html" in ct and "charset" not in ct:
        response.headers["content-type"] = "text/html; charset=utf-8"
    return response

_STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

app.include_router(dashboard.router)
app.include_router(actions.router)
app.include_router(sse.router)
app.include_router(generate.router)
app.include_router(setup.router)
app.include_router(cron.router)

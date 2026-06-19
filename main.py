"""
uvicorn 진입점 — python main.py 로 실행
"""

import sys
import os
import asyncio

# Windows: ProactorEventLoop은 uvicorn HTTP 응답 전송에 문제가 있으므로 SelectorEventLoop 강제 지정
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Windows 콘솔 인코딩을 UTF-8로 강제 설정 (한글 깨짐 방지)
if sys.stdout and hasattr(sys.stdout, 'encoding') and sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, 'encoding') and sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from dotenv import load_dotenv

load_dotenv("config/.env")

import uvicorn
from src.web.app import app

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run("src.web.app:app", host=host, port=port, reload=False)

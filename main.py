"""
uvicorn 진입점 — python main.py 로 실행
"""

import sys
import os

# Windows 콘솔 인코딩을 UTF-8로 강제 설정 (한글 깨짐 방지)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

load_dotenv("config/.env")

import uvicorn
from src.web.app import app

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run("src.web.app:app", host=host, port=port, reload=False)

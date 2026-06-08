"""
uvicorn 진입점 — python main.py 로 실행
"""

import os
from dotenv import load_dotenv

load_dotenv("config/.env")

import uvicorn
from src.web.app import app

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port, reload=False)

"""
HTTP Basic 인증 — 모든 POST 엔드포인트에 적용
H-01: reviewed_by에 인증된 사용자명 기록하여 감사 추적 완성
"""

import os
import secrets

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials

security = HTTPBasic()


def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    """인증 성공 시 username 반환 (reviewed_by DB 기록용)."""
    username_ok = secrets.compare_digest(
        credentials.username, os.getenv("DASHBOARD_USERNAME", "cimon")
    )
    password_ok = secrets.compare_digest(
        credentials.password, os.getenv("DASHBOARD_PASSWORD", "cimon2024")
    )
    if not (username_ok and password_ok):
        raise HTTPException(
            status_code=401,
            detail="인증 실패",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

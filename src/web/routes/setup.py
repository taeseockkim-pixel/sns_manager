"""
API 자격증명 설정 및 OAuth 흐름 관리
"""

import os
import secrets
import time
from pathlib import Path

import requests
from fastapi import APIRouter, Depends

from src.api._ssl import ssl_verify
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.web.auth import verify_credentials

router = APIRouter(prefix="/setup", tags=["setup"])

_TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATE_DIR))

_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

# CSRF 방지용 일회성 state (PoC — 재시작 시 초기화)
_threads_oauth_state: str | None = None


def _update_env(updates: dict) -> None:
    """config/.env 특정 키 값 업데이트 및 os.environ 즉시 반영."""
    env_path = _PROJECT_ROOT / "config" / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines()
    written = set()

    new_lines = []
    for line in lines:
        stripped = line.strip()
        if "=" in stripped and not stripped.startswith("#"):
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}")
                os.environ[key] = str(updates[key])
                written.add(key)
                continue
        new_lines.append(line)

    for key, val in updates.items():
        if key not in written:
            new_lines.append(f"{key}={val}")
            os.environ[key] = str(val)

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def _cred_status() -> dict:
    keys = [
        "META_APP_ID", "META_APP_SECRET", "META_PAGE_ACCESS_TOKEN",
        "META_PAGE_ID", "META_IG_USER_ID",
        "THREADS_APP_ID", "THREADS_APP_SECRET", "THREADS_USER_ID", "THREADS_ACCESS_TOKEN",
        "X_API_KEY", "X_ACCESS_TOKEN",
        "ANTHROPIC_API_KEY",
    ]
    return {k: bool(os.environ.get(k)) for k in keys}


@router.get("", response_class=HTMLResponse)
async def setup_page(request: Request):
    return templates.TemplateResponse(
        request, "setup.html", {"creds": _cred_status(), "page": "setup"}
    )


@router.get("/instagram", response_class=HTMLResponse)
async def fetch_instagram_id(request: Request):
    """Page Access Token으로 IG Business Account ID를 자동 조회해 .env에 저장."""
    token = os.environ.get("META_PAGE_ACCESS_TOKEN", "")
    page_id = os.environ.get("META_PAGE_ID", "")

    if not token or not page_id:
        return templates.TemplateResponse(
            request, "setup.html",
            {"creds": _cred_status(), "page": "setup",
             "error": "META_PAGE_ACCESS_TOKEN 또는 META_PAGE_ID가 설정되지 않았습니다."}
        )

    try:
        resp = requests.get(
            f"https://graph.facebook.com/v19.0/{page_id}",
            params={"fields": "instagram_business_account", "access_token": token},
            timeout=10,
            verify=ssl_verify(),
        )
        if not resp.ok:
            raise RuntimeError(resp.text[:300])

        ig_id = resp.json().get("instagram_business_account", {}).get("id", "")
        if ig_id:
            _update_env({"META_IG_USER_ID": ig_id, "CIMON_IG_USER_ID": ig_id})
            msg = f"Instagram User ID 저장 완료: {ig_id}"
        else:
            msg = "페이지에 연결된 Instagram Business 계정이 없습니다. Meta Business Suite에서 Instagram 계정을 연결해 주세요."

        return templates.TemplateResponse(
            request, "setup.html",
            {"creds": _cred_status(), "page": "setup", "success": msg}
        )
    except Exception as exc:
        return templates.TemplateResponse(
            request, "setup.html",
            {"creds": _cred_status(), "page": "setup", "error": f"Instagram 조회 실패: {exc}"}
        )


@router.get("/threads/auth")
async def threads_auth_redirect():
    """Threads OAuth 인증 URL로 리다이렉트."""
    global _threads_oauth_state
    app_id = os.environ.get("THREADS_APP_ID", "")
    if not app_id:
        return HTMLResponse("THREADS_APP_ID가 설정되지 않았습니다.", status_code=400)

    _threads_oauth_state = secrets.token_urlsafe(16)
    redirect_uri = "http://localhost:8000/setup/threads/callback"
    auth_url = (
        f"https://threads.net/oauth/authorize"
        f"?client_id={app_id}"
        f"&redirect_uri={redirect_uri}"
        f"&scope=threads_basic,threads_content_publish,threads_read_replies"
        f"&response_type=code"
        f"&state={_threads_oauth_state}"
    )
    return RedirectResponse(auth_url)


@router.get("/threads/callback", response_class=HTMLResponse)
async def threads_auth_callback(
    request: Request,
    code: str = None,
    state: str = None,
    error: str = None,
):
    """Threads OAuth 콜백 — code를 장기 액세스 토큰으로 교환."""
    global _threads_oauth_state

    if error:
        return templates.TemplateResponse(
            request, "setup.html",
            {"creds": _cred_status(), "page": "setup", "error": f"Threads 인증 취소: {error}"}
        )

    if not code:
        return templates.TemplateResponse(
            request, "setup.html",
            {"creds": _cred_status(), "page": "setup", "error": "인증 코드가 없습니다."}
        )

    if state != _threads_oauth_state:
        return templates.TemplateResponse(
            request, "setup.html",
            {"creds": _cred_status(), "page": "setup",
             "error": "State 불일치 — 다시 시도해 주세요."}
        )
    _threads_oauth_state = None

    app_id = os.environ.get("THREADS_APP_ID", "")
    app_secret = os.environ.get("THREADS_APP_SECRET", "")
    redirect_uri = "http://localhost:8000/setup/threads/callback"

    try:
        # Step 1: 단기 액세스 토큰 교환
        token_resp = requests.post(
            "https://graph.threads.net/oauth/access_token",
            data={
                "client_id": app_id,
                "client_secret": app_secret,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
                "code": code,
            },
            timeout=15,
            verify=ssl_verify(),
        )
        if not token_resp.ok:
            raise RuntimeError(f"단기 토큰 교환 실패: {token_resp.text[:300]}")

        token_data = token_resp.json()
        short_token = token_data.get("access_token", "")
        user_id = str(token_data.get("user_id", ""))

        # Step 2: 장기 액세스 토큰 교환 (60일)
        long_resp = requests.get(
            "https://graph.threads.net/access_token",
            params={
                "grant_type": "th_exchange_token",
                "client_secret": app_secret,
                "access_token": short_token,
            },
            timeout=15,
            verify=ssl_verify(),
        )
        long_token = long_resp.json().get("access_token", short_token) if long_resp.ok else short_token

        _update_env({
            "THREADS_USER_ID": user_id,
            "THREADS_ACCESS_TOKEN": long_token,
            "THREADS_TOKEN_REFRESHED_AT": str(int(time.time())),
        })

        return templates.TemplateResponse(
            request, "setup.html",
            {"creds": _cred_status(), "page": "setup",
             "success": f"Threads 인증 완료! User ID: {user_id} (장기 토큰 60일 유효)"}
        )
    except Exception as exc:
        return templates.TemplateResponse(
            request, "setup.html",
            {"creds": _cred_status(), "page": "setup", "error": str(exc)}
        )

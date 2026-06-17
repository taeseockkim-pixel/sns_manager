"""
API 자격증명 설정 및 OAuth 흐름 관리
자격증명은 Neon PostgreSQL credentials 테이블에 저장 (Vercel 서버리스 호환)
"""

import os
import secrets
import time
from pathlib import Path

import requests
from fastapi import APIRouter
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.api._ssl import ssl_verify

router = APIRouter(prefix="/setup", tags=["setup"])

_TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATE_DIR))

_threads_oauth_state: str | None = None


def _cred_status() -> dict:
    keys = [
        "META_APP_ID", "META_APP_SECRET", "META_PAGE_ACCESS_TOKEN",
        "META_PAGE_ID", "META_IG_USER_ID",
        "THREADS_APP_ID", "THREADS_APP_SECRET", "THREADS_USER_ID", "THREADS_ACCESS_TOKEN",
        "X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET", "X_BEARER_TOKEN",
        "ANTHROPIC_API_KEY",
    ]
    return {k: bool(os.environ.get(k)) for k in keys}


@router.get("", response_class=HTMLResponse)
async def setup_page(request: Request):
    return templates.TemplateResponse(
        request, "setup.html", {"creds": _cred_status(), "page": "setup"}
    )


@router.post("/creds", response_class=HTMLResponse)
async def save_creds(request: Request):
    from src.db import creds as creds_db
    form = await request.form()
    for key, value in form.items():
        v = str(value).strip()
        if v:
            creds_db.upsert(key, v)
    return RedirectResponse("/setup", status_code=303)


@router.get("/instagram", response_class=HTMLResponse)
async def fetch_instagram_id(request: Request):
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
            from src.db import creds as creds_db
            creds_db.upsert("META_IG_USER_ID", ig_id)
            creds_db.upsert("CIMON_IG_USER_ID", ig_id)
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
async def threads_auth_redirect(request: Request):
    global _threads_oauth_state
    app_id = os.environ.get("THREADS_APP_ID", "")
    if not app_id:
        return HTMLResponse("THREADS_APP_ID가 설정되지 않았습니다.", status_code=400)

    _threads_oauth_state = secrets.token_urlsafe(16)
    base_url = str(request.base_url).rstrip("/")
    redirect_uri = f"{base_url}/setup/threads/callback"
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
    base_url = str(request.base_url).rstrip("/")
    redirect_uri = f"{base_url}/setup/threads/callback"

    try:
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

        from src.db import creds as creds_db
        creds_db.upsert("THREADS_USER_ID", user_id)
        creds_db.upsert("THREADS_ACCESS_TOKEN", long_token)
        creds_db.upsert("THREADS_TOKEN_REFRESHED_AT", str(int(time.time())))

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

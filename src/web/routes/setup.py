"""
API 자격증명 설정 및 OAuth 흐름 관리
자격증명은 Neon PostgreSQL credentials 테이블에 저장 (Vercel 서버리스 호환)
"""

import os
import secrets
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

_fb_oauth_state: str | None = None


def _cred_status() -> dict:
    keys = [
        "META_APP_ID", "META_APP_SECRET", "META_PAGE_ACCESS_TOKEN",
        "META_PAGE_ID", "META_IG_USER_ID",
        "X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET", "X_BEARER_TOKEN",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GROQ_API_KEY",
    ]
    return {k: bool(os.environ.get(k)) for k in keys}


def _profile_values() -> dict:
    """회사 프로필 및 SNS 채널 URL의 현재 값 반환."""
    keys = [
        "COMPANY_DESCRIPTION", "COMPANY_PRODUCTS", "COMPANY_SELLING_POINTS",
        "COMPANY_TARGET", "COMPANY_TONE",
        "SNS_URL_X", "SNS_URL_FACEBOOK", "SNS_URL_INSTAGRAM",
        "META_PAGE_ID", "META_IG_USER_ID",
    ]
    return {k: os.environ.get(k, "") for k in keys}


@router.get("", response_class=HTMLResponse)
async def setup_page(request: Request):
    return templates.TemplateResponse(
        request, "setup.html", {
            "creds": _cred_status(),
            "profile": _profile_values(),
            "page": "setup",
        }
    )


@router.post("/creds", response_class=HTMLResponse)
async def save_creds(request: Request):
    from src.db import creds as creds_db
    form = await request.form()
    saved_keys = []
    has_page_token = False

    for key, value in form.items():
        v = str(value).strip()
        if v:
            creds_db.upsert(key, v)
            os.environ[key] = v
            saved_keys.append(key)
            if key == "META_PAGE_ACCESS_TOKEN":
                has_page_token = True

    # META_PAGE_ACCESS_TOKEN 저장 시 즉시 영구 페이지 토큰으로 자동 변환
    if has_page_token:
        app_id = os.environ.get("META_APP_ID", "")
        app_secret = os.environ.get("META_APP_SECRET", "")
        if app_id and app_secret:
            try:
                from src.api.meta_token import refresh_token, check_token_expiry
                refresh_token()
                status = check_token_expiry()
                days = status.get("days_left")
                msg = "영구 페이지 토큰으로 자동 변환 완료" if days is None else f"60일 장기 토큰으로 변환 완료 ({days}일 남음)"
                return templates.TemplateResponse(
                    request, "setup.html",
                    {"creds": _cred_status(), "profile": _profile_values(), "page": "setup",
                     "success": f"자격증명 저장 완료. {msg}"}
                )
            except Exception as exc:
                return templates.TemplateResponse(
                    request, "setup.html",
                    {"creds": _cred_status(), "profile": _profile_values(), "page": "setup",
                     "error": f"토큰 저장됐지만 영구 변환 실패: {exc}. META_APP_ID / META_APP_SECRET이 올바른지 확인하세요."}
                )

    return RedirectResponse("/setup", status_code=303)


@router.post("/company-profile", response_class=HTMLResponse)
async def save_company_profile(request: Request):
    from src.db import creds as creds_db
    form = await request.form()
    keys = ["COMPANY_DESCRIPTION", "COMPANY_PRODUCTS", "COMPANY_SELLING_POINTS",
            "COMPANY_TARGET", "COMPANY_TONE"]
    for key in keys:
        v = str(form.get(key, "")).strip()
        creds_db.upsert(key, v)
    return templates.TemplateResponse(
        request, "setup.html", {
            "creds": _cred_status(),
            "profile": _profile_values(),
            "page": "setup",
            "success": "회사/제품 프로필이 저장됐습니다.",
        }
    )


@router.post("/sns-urls", response_class=HTMLResponse)
async def save_sns_urls(request: Request):
    from src.db import creds as creds_db
    form = await request.form()
    keys = ["SNS_URL_X", "SNS_URL_FACEBOOK", "SNS_URL_INSTAGRAM"]
    for key in keys:
        v = str(form.get(key, "")).strip()
        creds_db.upsert(key, v)
    return templates.TemplateResponse(
        request, "setup.html", {
            "creds": _cred_status(),
            "profile": _profile_values(),
            "page": "setup",
            "success": "SNS 채널 링크가 저장됐습니다.",
        }
    )


@router.post("/meta/token-status", response_class=HTMLResponse)
async def meta_token_status(request: Request):
    from src.api.meta_token import check_token_expiry
    result = check_token_expiry()
    if not result.get("valid"):
        err = result.get("error", "알 수 없는 오류")
        return HTMLResponse(
            f'<span class="text-red-600 font-semibold">만료됨 — {err}. '
            f'<a href="https://developers.facebook.com/tools/explorer/" target="_blank" '
            f'class="underline">Graph Explorer</a>에서 새 토큰을 발급 후 위에 붙여넣으세요.</span>'
        )
    days = result.get("days_left")
    if days is None:
        return HTMLResponse('<span class="text-green-600 font-semibold">영구 토큰 (만료 없음)</span>')
    color = "green" if days > 14 else "amber" if days > 7 else "red"
    return HTMLResponse(f'<span class="text-{color}-600 font-semibold">유효 — 잔여 {days}일 ({result.get("expiry_dt","")[:10]})</span>')


@router.post("/meta/refresh-token", response_class=HTMLResponse)
async def meta_refresh_token(request: Request):
    from src.api.meta_token import check_and_refresh_if_needed
    from src.db import creds as creds_db
    result = check_and_refresh_if_needed()
    if result["action"] == "refreshed":
        # DB에도 갱신된 토큰 저장
        new_token = os.environ.get("META_PAGE_ACCESS_TOKEN", "")
        if new_token:
            creds_db.upsert("META_PAGE_ACCESS_TOKEN", new_token)
        return HTMLResponse('<span class="text-green-600 font-semibold">갱신 완료 — 60일 연장됨</span>')
    elif result["action"] == "ok":
        return HTMLResponse(f'<span class="text-green-600">이미 유효합니다: {result["message"]}</span>')
    else:
        return HTMLResponse(
            f'<span class="text-red-600 font-semibold">갱신 실패: {result["message"][:200]} '
            f'— <a href="https://developers.facebook.com/tools/explorer/" target="_blank" '
            f'class="underline">Graph Explorer</a>에서 새 토큰 발급 후 직접 입력하세요.</span>'
        )


@router.get("/instagram", response_class=HTMLResponse)
async def fetch_instagram_id(request: Request):
    token = os.environ.get("META_PAGE_ACCESS_TOKEN", "")
    page_id = os.environ.get("META_PAGE_ID", "")

    if not token or not page_id:
        return templates.TemplateResponse(
            request, "setup.html",
            {"creds": _cred_status(), "profile": _profile_values(), "page": "setup",
             "error": "META_PAGE_ACCESS_TOKEN 또는 META_PAGE_ID가 설정되지 않았습니다."}
        )

    try:
        resp = requests.get(
            f"https://graph.facebook.com/v19.0/{page_id}",
            params={
                "fields": "instagram_business_account,connected_instagram_account",
                "access_token": token,
            },
            timeout=10,
            verify=ssl_verify(),
        )
        if not resp.ok:
            raise RuntimeError(resp.text[:300])

        data = resp.json()
        ig_id = (
            data.get("instagram_business_account", {}).get("id")
            or data.get("connected_instagram_account", {}).get("id")
            or ""
        )
        if ig_id:
            from src.db import creds as creds_db
            creds_db.upsert("META_IG_USER_ID", ig_id)
            os.environ["META_IG_USER_ID"] = ig_id
            msg = f"Instagram User ID 저장 완료: {ig_id}"
        else:
            raw_keys = list(data.keys())
            msg = (
                "페이지에 연결된 Instagram 계정 ID를 가져올 수 없습니다. "
                f"(API 응답 필드: {raw_keys})\n\n"
                "해결 방법:\n"
                "① Graph API Explorer에서 아래 쿼리 실행 → 반환된 id를 아래 수동 입력란에 붙여넣기:\n"
                f"  /{page_id}?fields=instagram_business_account,connected_instagram_account\n\n"
                "② 또는 Meta Developer Console → CIMON_SNS 앱 → 제품 추가(Add Product) → "
                "Instagram Graph API → Set Up 클릭 후 다시 시도."
            )

        return templates.TemplateResponse(
            request, "setup.html",
            {"creds": _cred_status(), "profile": _profile_values(), "page": "setup",
             "success": msg if ig_id else None,
             "error": msg if not ig_id else None}
        )
    except Exception as exc:
        return templates.TemplateResponse(
            request, "setup.html",
            {"creds": _cred_status(), "profile": _profile_values(), "page": "setup",
             "error": f"Instagram 조회 실패: {exc}"}
        )


@router.get("/facebook/auth")
async def facebook_auth_redirect(request: Request):
    global _fb_oauth_state
    app_id = os.environ.get("META_APP_ID", "")
    if not app_id:
        return templates.TemplateResponse(
            request, "setup.html",
            {"creds": _cred_status(), "profile": _profile_values(), "page": "setup",
             "error": "META_APP_ID가 설정되지 않았습니다. 먼저 저장해 주세요."}
        )
    _fb_oauth_state = secrets.token_urlsafe(16)
    base_url = str(request.base_url).rstrip("/")
    redirect_uri = f"{base_url}/setup/facebook/callback"
    scope = ",".join([
        "pages_show_list",
        "pages_read_engagement",
        "pages_manage_posts",
        "pages_manage_engagement",
        "pages_manage_metadata",
        "instagram_manage_comments",
        "read_insights",
    ])
    auth_url = (
        f"https://www.facebook.com/v19.0/dialog/oauth"
        f"?client_id={app_id}"
        f"&redirect_uri={redirect_uri}"
        f"&scope={scope}"
        f"&response_type=code"
        f"&state={_fb_oauth_state}"
    )
    return RedirectResponse(auth_url)


@router.get("/facebook/callback", response_class=HTMLResponse)
async def facebook_auth_callback(
    request: Request,
    code: str = None,
    state: str = None,
    error: str = None,
):
    global _fb_oauth_state

    if error:
        return templates.TemplateResponse(
            request, "setup.html",
            {"creds": _cred_status(), "profile": _profile_values(), "page": "setup",
             "error": f"Facebook 인증 취소: {error}"}
        )
    if not code:
        return templates.TemplateResponse(
            request, "setup.html",
            {"creds": _cred_status(), "profile": _profile_values(), "page": "setup",
             "error": "인증 코드가 없습니다."}
        )
    if state != _fb_oauth_state:
        return templates.TemplateResponse(
            request, "setup.html",
            {"creds": _cred_status(), "profile": _profile_values(), "page": "setup",
             "error": "State 불일치 — 다시 시도해 주세요."}
        )
    _fb_oauth_state = None

    app_id = os.environ.get("META_APP_ID", "")
    app_secret = os.environ.get("META_APP_SECRET", "")
    page_id = os.environ.get("META_PAGE_ID", "").strip()
    base_url = str(request.base_url).rstrip("/")
    redirect_uri = f"{base_url}/setup/facebook/callback"

    try:
        # Step 1: 단기 사용자 토큰
        token_resp = requests.get(
            "https://graph.facebook.com/v19.0/oauth/access_token",
            params={
                "client_id": app_id,
                "client_secret": app_secret,
                "redirect_uri": redirect_uri,
                "code": code,
            },
            timeout=15, verify=ssl_verify(),
        )
        if not token_resp.ok:
            raise RuntimeError(f"단기 토큰 교환 실패: {token_resp.text[:300]}")
        short_token = token_resp.json().get("access_token", "")

        # Step 2: 60일 장기 사용자 토큰
        long_resp = requests.get(
            "https://graph.facebook.com/v19.0/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": app_id,
                "client_secret": app_secret,
                "fb_exchange_token": short_token,
            },
            timeout=15, verify=ssl_verify(),
        )
        long_token = long_resp.json().get("access_token", short_token) if long_resp.ok else short_token

        # Step 3: /me/accounts → 영구 페이지 토큰 (장기 사용자 토큰 기반 = 만료 없음)
        accounts_resp = requests.get(
            "https://graph.facebook.com/v19.0/me/accounts",
            params={"access_token": long_token, "limit": 50},
            timeout=15, verify=ssl_verify(),
        )
        pages = accounts_resp.json().get("data", []) if accounts_resp.ok else []
        page_token = ""
        found_page_id = page_id
        for pg in pages:
            if not page_id or pg.get("id") == page_id:
                page_token = pg.get("access_token", "")
                found_page_id = pg.get("id", page_id)
                break
        if not page_token and pages:
            page_token = pages[0].get("access_token", "")
            found_page_id = pages[0].get("id", "")

        final_token = page_token or long_token

        from src.db import creds as creds_db
        creds_db.upsert("META_PAGE_ACCESS_TOKEN", final_token)
        os.environ["META_PAGE_ACCESS_TOKEN"] = final_token
        if found_page_id:
            creds_db.upsert("META_PAGE_ID", found_page_id)
            os.environ["META_PAGE_ID"] = found_page_id

        # Step 4: IG User ID 자동 조회
        ig_id = ""
        if found_page_id:
            ig_resp = requests.get(
                f"https://graph.facebook.com/v19.0/{found_page_id}",
                params={
                    "fields": "instagram_business_account,connected_instagram_account",
                    "access_token": final_token,
                },
                timeout=10, verify=ssl_verify(),
            )
            if ig_resp.ok:
                ig_data = ig_resp.json()
                ig_id = (
                    ig_data.get("instagram_business_account", {}).get("id")
                    or ig_data.get("connected_instagram_account", {}).get("id")
                    or ""
                )
                if ig_id:
                    creds_db.upsert("META_IG_USER_ID", ig_id)
                    os.environ["META_IG_USER_ID"] = ig_id

        token_type = "영구 페이지 토큰 (만료 없음)" if page_token else "60일 장기 토큰"
        ig_msg = f" | Instagram ID 자동 저장: {ig_id}" if ig_id else ""
        return templates.TemplateResponse(
            request, "setup.html",
            {"creds": _cred_status(), "profile": _profile_values(), "page": "setup",
             "success": f"Facebook 인증 완료! {token_type}{ig_msg}"}
        )
    except Exception as exc:
        return templates.TemplateResponse(
            request, "setup.html",
            {"creds": _cred_status(), "profile": _profile_values(), "page": "setup",
             "error": f"Facebook 인증 실패: {exc}"}
        )



"""
Meta 액세스 토큰 만료 자동 체크 및 갱신
- /debug_token으로 만료일 확인
- 7일 이내 만료 예정이면 fb_exchange_token으로 갱신
- config/.env 자동 업데이트
"""
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

from src.api._ssl import ssl_verify

_PROJECT_ROOT = Path(__file__).parent.parent.parent


def _update_env_token(key: str, value: str) -> None:
    env_path = _PROJECT_ROOT / "config" / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines()
    new_lines = []
    written = False
    for line in lines:
        stripped = line.strip()
        if "=" in stripped and not stripped.startswith("#"):
            k = stripped.split("=", 1)[0].strip()
            if k == key:
                new_lines.append(f"{key}={value}")
                os.environ[key] = value
                written = True
                continue
        new_lines.append(line)
    if not written:
        new_lines.append(f"{key}={value}")
        os.environ[key] = value
    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def check_token_expiry() -> dict:
    """토큰 만료일 확인. 반환: {valid, days_left, expiry_dt}"""
    app_id = os.environ.get("META_APP_ID", "")
    app_secret = os.environ.get("META_APP_SECRET", "")
    token = os.environ.get("META_PAGE_ACCESS_TOKEN", "")

    if not all([app_id, app_secret, token]):
        return {"valid": False, "error": "자격증명 미설정"}

    resp = requests.get(
        "https://graph.facebook.com/debug_token",
        params={
            "input_token": token,
            "access_token": f"{app_id}|{app_secret}",
        },
        timeout=10,
        verify=ssl_verify(),
    )

    if not resp.ok:
        return {"valid": False, "error": resp.text[:200]}

    data = resp.json().get("data", {})
    if not data.get("is_valid", False):
        return {"valid": False, "error": "토큰 무효 또는 만료됨"}

    expires_at = data.get("expires_at", 0)
    if expires_at == 0:
        return {"valid": True, "days_left": None, "message": "영구 토큰 (만료 없음)"}

    expiry_dt = datetime.fromtimestamp(expires_at, tz=timezone.utc)
    days_left = (expiry_dt - datetime.now(tz=timezone.utc)).days
    return {"valid": True, "days_left": days_left, "expiry_dt": expiry_dt.isoformat()}


def refresh_token() -> str:
    """현재 토큰을 장기 토큰(60일)으로 갱신하고 .env에 저장. 새 토큰 반환."""
    app_id = os.environ.get("META_APP_ID", "")
    app_secret = os.environ.get("META_APP_SECRET", "")
    token = os.environ.get("META_PAGE_ACCESS_TOKEN", "")

    resp = requests.get(
        "https://graph.facebook.com/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": token,
        },
        timeout=15,
        verify=ssl_verify(),
    )

    if not resp.ok:
        raise RuntimeError(f"토큰 갱신 실패: {resp.text[:300]}")

    new_token = resp.json().get("access_token")
    if not new_token:
        raise RuntimeError("갱신된 토큰이 응답에 없습니다.")

    _update_env_token("META_PAGE_ACCESS_TOKEN", new_token)
    return new_token


def check_and_refresh_if_needed() -> dict:
    """
    만료 7일 전이면 자동 갱신.
    반환: {"action": "refreshed"|"ok"|"expired"|"error", "message": str}
    """
    status = check_token_expiry()

    if not status.get("valid"):
        return {
            "action": "expired",
            "message": f"토큰 만료/무효 — 수동 재발급 필요: {status.get('error', '')}",
        }

    days_left = status.get("days_left")

    if days_left is None:
        return {"action": "ok", "message": "영구 토큰 (만료 없음)"}

    if days_left > 7:
        return {"action": "ok", "message": f"토큰 유효 ({days_left}일 남음)"}

    try:
        refresh_token()
        return {
            "action": "refreshed",
            "message": f"Meta 토큰 자동 갱신 완료 (잔여 {days_left}일 → 60일 연장)",
        }
    except Exception as exc:
        return {"action": "error", "message": str(exc)}

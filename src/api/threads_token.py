"""
Threads 액세스 토큰 자동 갱신
- 토큰은 60일 유효, 30일마다 갱신하여 항상 여유 있게 유지
- config/.env 자동 업데이트
"""
import os
import time
from pathlib import Path

import requests

from src.api._ssl import ssl_verify

_PROJECT_ROOT = Path(__file__).parent.parent.parent


def _update_env_token(updates: dict) -> None:
    env_path = _PROJECT_ROOT / "config" / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines()
    written = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if "=" in stripped and not stripped.startswith("#"):
            k = stripped.split("=", 1)[0].strip()
            if k in updates:
                new_lines.append(f"{k}={updates[k]}")
                os.environ[k] = str(updates[k])
                written.add(k)
                continue
        new_lines.append(line)
    for k, v in updates.items():
        if k not in written:
            new_lines.append(f"{k}={v}")
            os.environ[k] = str(v)
    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def check_and_refresh_if_needed() -> dict:
    """
    Threads 토큰 만료 체크 및 자동 갱신.
    - 토큰 없으면 OAuth 연결 필요 알림
    - 마지막 갱신 후 30일 경과 시 갱신 (60일 토큰을 절반 주기로 유지)
    반환: {"action": "refreshed"|"ok"|"no_token"|"error", "message": str}
    """
    token = os.environ.get("THREADS_ACCESS_TOKEN", "")
    if not token:
        return {"action": "no_token", "message": "Threads 토큰 없음 — /setup에서 OAuth 연결 필요"}

    # DB에서 타임스탬프 조회 (Vercel 서버리스에서 env 미영속 대비)
    from src.db import creds as creds_db
    refreshed_at_db = creds_db.get("THREADS_TOKEN_REFRESHED_AT") or "0"
    last_refresh_ts = int(os.environ.get("THREADS_TOKEN_REFRESHED_AT") or refreshed_at_db or "0")
    days_since = (time.time() - last_refresh_ts) / 86400

    if days_since < 30:
        days_left = int(60 - days_since)
        return {"action": "ok", "message": f"Threads 토큰 유효 (약 {days_left}일 남음)"}

    try:
        resp = requests.get(
            "https://graph.threads.net/refresh_access_token",
            params={"grant_type": "th_refresh_token", "access_token": token},
            timeout=15,
            verify=ssl_verify(),
        )
        if not resp.ok:
            raise RuntimeError(f"Threads 토큰 갱신 실패: {resp.text[:300]}")

        new_token = resp.json().get("access_token")
        if not new_token:
            raise RuntimeError("갱신된 Threads 토큰이 응답에 없습니다.")

        new_ts = str(int(time.time()))
        _update_env_token({"THREADS_ACCESS_TOKEN": new_token, "THREADS_TOKEN_REFRESHED_AT": new_ts})
        # Vercel 서버리스 영속을 위해 DB에도 저장
        from src.db import creds as creds_db
        creds_db.upsert("THREADS_ACCESS_TOKEN", new_token)
        creds_db.upsert("THREADS_TOKEN_REFRESHED_AT", new_ts)
        return {"action": "refreshed", "message": "Threads 토큰 자동 갱신 완료 (60일 연장)"}

    except Exception as exc:
        return {"action": "error", "message": str(exc)}

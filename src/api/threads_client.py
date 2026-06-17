"""
Threads Graph API 클라이언트
H-04: API 실패 시 재시도 없이 즉시 에스컬레이션
H-05: 플랫폼 격리 — 이 모듈은 Threads만 담당
"""

import os
import requests

from src.api._ssl import ssl_verify

BASE_URL = "https://graph.threads.net/v1.0"


def _user_id() -> str:
    return os.environ["THREADS_USER_ID"]


def _token() -> str:
    return os.environ["THREADS_ACCESS_TOKEN"]


def post_to_threads(text: str) -> dict:
    """
    Threads에 텍스트 게시 (2단계: 컨테이너 생성 → 게시).
    H-01: 반드시 승인된 콘텐츠에만 호출.
    """
    user_id = _user_id()
    token = _token()

    # Step 1: 미디어 컨테이너 생성
    container_resp = requests.post(
        f"{BASE_URL}/{user_id}/threads",
        params={"media_type": "TEXT", "text": text, "access_token": token},
        timeout=15,
        verify=ssl_verify(),
    )
    if not container_resp.ok:
        raise RuntimeError(f"Threads container error {container_resp.status_code}: {container_resp.text}")
    container_id = container_resp.json()["id"]

    # Step 2: 게시
    publish_resp = requests.post(
        f"{BASE_URL}/{user_id}/threads_publish",
        params={"creation_id": container_id, "access_token": token},
        timeout=15,
        verify=ssl_verify(),
    )
    if not publish_resp.ok:
        raise RuntimeError(f"Threads publish error {publish_resp.status_code}: {publish_resp.text}")
    return publish_resp.json()


def get_threads_replies(since_timestamp: str = None) -> list:
    """내 Threads 게시물에 달린 최근 답글 수집 (모니터링용, threads_read_replies 권한 필요)."""
    user_id = _user_id()
    token = _token()

    params = {
        "fields": "id,text,timestamp,username",
        "access_token": token,
    }
    if since_timestamp:
        params["since"] = since_timestamp

    resp = requests.get(
        f"{BASE_URL}/{user_id}/replies",
        params=params,
        timeout=10,
        verify=ssl_verify(),
    )
    if not resp.ok:
        raise RuntimeError(f"Threads API error {resp.status_code}: {resp.text}")
    return resp.json().get("data", [])

"""
Meta (Facebook/Instagram) Graph API 클라이언트
H-04: API 실패 시 재시도 없이 즉시 에스컬레이션
H-05: 플랫폼 격리 — 이 모듈은 Meta 계열만 담당
참고: pages_manage_posts App Review 통과 후 사용 가능 (5-10일 소요)
"""

import os
import requests

from src.api._ssl import ssl_verify

BASE_URL = "https://graph.facebook.com/v19.0"


def _token() -> str:
    return os.environ["META_PAGE_ACCESS_TOKEN"]


def post_to_page(message: str) -> dict:
    """
    Facebook 페이지에 포스트 게시.
    H-01: 반드시 승인된 콘텐츠에만 호출.
    """
    page_id = os.environ["META_PAGE_ID"]
    resp = requests.post(
        f"{BASE_URL}/{page_id}/feed",
        json={"message": message, "access_token": _token()},
        timeout=10,
        verify=ssl_verify(),
    )
    if not resp.ok:
        raise RuntimeError(f"Meta API error {resp.status_code}: {resp.text}")
    return resp.json()


def post_to_instagram(image_url: str, caption: str) -> dict:
    """
    Instagram 게시. 2단계 프로세스:
    1. 미디어 컨테이너 생성
    2. 컨테이너 게시
    H-01: 반드시 승인된 콘텐츠에만 호출.
    """
    ig_user_id = os.environ["META_IG_USER_ID"]
    token = _token()

    # Step 1: 미디어 컨테이너 생성
    container_resp = requests.post(
        f"{BASE_URL}/{ig_user_id}/media",
        json={"image_url": image_url, "caption": caption, "access_token": token},
        timeout=15,
        verify=ssl_verify(),
    )
    if not container_resp.ok:
        raise RuntimeError(f"IG container error {container_resp.status_code}: {container_resp.text}")
    container_id = container_resp.json()["id"]

    # Step 2: 게시
    publish_resp = requests.post(
        f"{BASE_URL}/{ig_user_id}/media_publish",
        json={"creation_id": container_id, "access_token": token},
        timeout=15,
        verify=ssl_verify(),
    )
    if not publish_resp.ok:
        raise RuntimeError(f"IG publish error {publish_resp.status_code}: {publish_resp.text}")
    return publish_resp.json()


def get_page_comments(since_timestamp: str = None) -> list:
    """페이지 댓글 수집 (모니터링용)."""
    page_id = os.environ["META_PAGE_ID"]
    params = {
        "fields": "message,from,created_time",
        "access_token": _token(),
    }
    if since_timestamp:
        params["since"] = since_timestamp

    resp = requests.get(f"{BASE_URL}/{page_id}/feed", params=params, timeout=10, verify=ssl_verify())
    if not resp.ok:
        raise RuntimeError(f"Meta API error {resp.status_code}: {resp.text}")
    return resp.json().get("data", [])

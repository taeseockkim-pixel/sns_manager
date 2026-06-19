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
IG_BASE_URL = "https://graph.instagram.com"


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


def get_page_stats() -> dict:
    """Facebook 페이지 팔로워 + 최근 10개 게시물 좋아요/댓글 평균."""
    page_id = os.environ["META_PAGE_ID"]
    token = _token()

    resp = requests.get(
        f"{BASE_URL}/{page_id}",
        params={"fields": "fan_count", "access_token": token},
        timeout=10, verify=ssl_verify(),
    )
    if not resp.ok:
        raise RuntimeError(f"Meta API error {resp.status_code}: {resp.text}")
    followers = resp.json().get("fan_count", 0)

    likes_avg: int = 0
    comments_avg: int = 0
    engagement_rate: str = "0.00"
    try:
        posts_resp = requests.get(
            f"{BASE_URL}/{page_id}/posts",
            params={
                "fields": "reactions.summary(true),comments.summary(true)",
                "limit": 10,
                "access_token": token,
            },
            timeout=10, verify=ssl_verify(),
        )
        if posts_resp.ok:
            posts = posts_resp.json().get("data", [])
            if posts:
                reactions = [p.get("reactions", {}).get("summary", {}).get("total_count", 0) for p in posts]
                comments  = [p.get("comments",  {}).get("summary", {}).get("total_count", 0) for p in posts]
                likes_avg    = sum(reactions) // len(reactions)
                comments_avg = sum(comments)  // len(comments)
                if followers > 0:
                    eng = (sum(reactions) + sum(comments)) / len(posts) / followers * 100
                    engagement_rate = f"{eng:.2f}"
    except Exception:
        pass

    return {
        "followers":  followers,
        "following":  0,
        "post_count": 0,
        "extra": {
            "likes_avg":       likes_avg,
            "comments_avg":    comments_avg,
            "engagement_rate": engagement_rate,
        },
    }


def _get_ig_user_id() -> str:
    """META_IG_USER_ID 환경변수 우선 사용, 없으면 Facebook 페이지에서 자동 조회.
    instagram_business_account → connected_instagram_account 순서로 시도."""
    ig_id = os.environ.get("META_IG_USER_ID", "").strip()
    if ig_id:
        return ig_id
    page_id = os.environ["META_PAGE_ID"]
    token = _token()
    # 두 필드 동시 요청 (권한에 따라 하나만 응답될 수 있음)
    resp = requests.get(
        f"{BASE_URL}/{page_id}",
        params={
            "fields": "instagram_business_account,connected_instagram_account",
            "access_token": token,
        },
        timeout=10, verify=ssl_verify(),
    )
    if not resp.ok:
        raise RuntimeError(f"Meta API error {resp.status_code}: {resp.text}")
    data = resp.json()
    ig_id = (
        data.get("instagram_business_account", {}).get("id")
        or data.get("connected_instagram_account", {}).get("id")
        or ""
    )
    if not ig_id:
        raise RuntimeError(
            "Facebook 페이지에 연결된 Instagram 계정을 찾을 수 없습니다. "
            "토큰에 instagram_basic 권한이 필요합니다."
        )
    return ig_id


def get_instagram_stats() -> dict:
    """Instagram 통계 — INSTAGRAM_ACCESS_TOKEN 우선, 없으면 Facebook Page token 폴백."""
    ig_token = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "").strip()

    followers: int = 0
    following: int = 0
    post_count: int = 0
    likes_avg: int = 0
    comments_avg: int = 0
    engagement_rate: str = "—"

    if ig_token:
        try:
            resp = requests.get(
                f"{IG_BASE_URL}/me",
                params={"fields": "followers_count,following_count,media_count", "access_token": ig_token},
                timeout=10, verify=ssl_verify(),
            )
            if resp.ok:
                data = resp.json()
                followers  = data.get("followers_count", 0) or 0
                following  = data.get("following_count", 0) or 0
                post_count = data.get("media_count",     0) or 0
        except Exception:
            pass

        try:
            media_resp = requests.get(
                f"{IG_BASE_URL}/me/media",
                params={"fields": "like_count,comments_count", "limit": 10, "access_token": ig_token},
                timeout=10, verify=ssl_verify(),
            )
            if media_resp.ok:
                media = media_resp.json().get("data", [])
                if media:
                    likes    = [m.get("like_count",     0) for m in media]
                    comments = [m.get("comments_count", 0) for m in media]
                    likes_avg    = sum(likes)    // len(likes)
                    comments_avg = sum(comments) // len(comments)
                    if followers > 0:
                        eng = (sum(likes) + sum(comments)) / len(media) / followers * 100
                        engagement_rate = f"{eng:.2f}"
        except Exception:
            pass
    else:
        ig_user_id = _get_ig_user_id()
        token = _token()

        try:
            resp = requests.get(
                f"{BASE_URL}/{ig_user_id}",
                params={"fields": "followers_count,following_count,media_count", "access_token": token},
                timeout=10, verify=ssl_verify(),
            )
            if resp.ok:
                data = resp.json()
                followers  = data.get("followers_count", 0) or 0
                following  = data.get("following_count", 0) or 0
                post_count = data.get("media_count",     0) or 0
        except Exception:
            pass

        try:
            media_resp = requests.get(
                f"{BASE_URL}/{ig_user_id}/media",
                params={"fields": "like_count,comments_count", "limit": 10, "access_token": token},
                timeout=10, verify=ssl_verify(),
            )
            if media_resp.ok:
                media = media_resp.json().get("data", [])
                if media:
                    likes    = [m.get("like_count",     0) for m in media]
                    comments = [m.get("comments_count", 0) for m in media]
                    likes_avg    = sum(likes)    // len(likes)
                    comments_avg = sum(comments) // len(comments)
                    if followers > 0:
                        eng = (sum(likes) + sum(comments)) / len(media) / followers * 100
                        engagement_rate = f"{eng:.2f}"
        except Exception:
            pass

    return {
        "followers":  followers,
        "following":  following,
        "post_count": post_count,
        "extra": {
            "likes_avg":       likes_avg,
            "comments_avg":    comments_avg,
            "engagement_rate": engagement_rate,
        },
    }


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

"""
X (Twitter) API v2 클라이언트
H-04: API 실패 시 재시도 없이 즉시 에스컬레이션
H-05: 플랫폼 격리 — 이 모듈은 X만 담당
"""

import os
import requests
from requests_oauthlib import OAuth1


BASE_URL = "https://api.twitter.com/2"


def _auth() -> OAuth1:
    return OAuth1(
        os.environ["X_API_KEY"],
        os.environ["X_API_SECRET"],
        os.environ["X_ACCESS_TOKEN"],
        os.environ["X_ACCESS_TOKEN_SECRET"],
    )


def post_tweet(text: str) -> dict:
    """
    트윗 게시. H-01: 이 함수는 반드시 승인된 콘텐츠에만 호출해야 함.
    성공 시 {"id": "...", "text": "..."} 반환.
    실패 시 예외 발생 (H-04: 재시도 없음).
    """
    resp = requests.post(
        f"{BASE_URL}/tweets",
        json={"text": text},
        auth=_auth(),
        timeout=10,
    )
    if not resp.ok:
        raise RuntimeError(f"X API error {resp.status_code}: {resp.text}")
    return resp.json().get("data", {})


def delete_tweet(tweet_id: str) -> bool:
    """트윗 삭제. 긴급 리스크 대응용."""
    resp = requests.delete(
        f"{BASE_URL}/tweets/{tweet_id}",
        auth=_auth(),
        timeout=10,
    )
    return resp.ok


def get_mentions(since_id: str = None) -> list:
    """멘션 수집 (댓글 모니터링용)."""
    params = {"expansions": "author_id", "tweet.fields": "created_at,text"}
    if since_id:
        params["since_id"] = since_id

    resp = requests.get(
        f"{BASE_URL}/tweets/search/recent",
        params={"query": f"to:{_get_username()} -is:retweet", **params},
        auth=_auth(),
        timeout=10,
    )
    if not resp.ok:
        raise RuntimeError(f"X API error {resp.status_code}: {resp.text}")
    return resp.json().get("data", [])


def _get_username() -> str:
    resp = requests.get(f"{BASE_URL}/users/me", auth=_auth(), timeout=10)
    return resp.json()["data"]["username"]

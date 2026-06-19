"""
X (Twitter) API v2 클라이언트
H-04: API 실패 시 재시도 없이 즉시 에스컬레이션
H-05: 플랫폼 격리 — 이 모듈은 X만 담당
"""

import os
import requests
from requests_oauthlib import OAuth1

from src.api._ssl import ssl_verify


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
        verify=ssl_verify(),
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
        verify=ssl_verify(),
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
        verify=ssl_verify(),
    )
    if not resp.ok:
        raise RuntimeError(f"X API error {resp.status_code}: {resp.text}")
    return resp.json().get("data", [])


def get_account_stats() -> dict:
    """팔로워·팔로잉·트윗 수 + 최근 10개 트윗 좋아요/댓글 평균 조회."""
    auth = _auth()
    me_resp = requests.get(
        f"{BASE_URL}/users/me",
        params={"user.fields": "public_metrics"},
        auth=auth, timeout=10, verify=ssl_verify(),
    )
    if not me_resp.ok:
        raise RuntimeError(f"X API error {me_resp.status_code}: {me_resp.text}")
    me_data = me_resp.json().get("data", {})
    metrics = me_data.get("public_metrics", {})
    followers = metrics.get("followers_count", 0)

    likes_avg: int = 0
    comments_avg: int = 0
    engagement_rate: str = "0.00"
    try:
        user_id = me_data.get("id")
        tweets_resp = requests.get(
            f"{BASE_URL}/users/{user_id}/tweets",
            params={"max_results": 10, "tweet.fields": "public_metrics"},
            auth=auth, timeout=10, verify=ssl_verify(),
        )
        if tweets_resp.ok:
            tweets = tweets_resp.json().get("data", [])
            if tweets:
                pm = [t.get("public_metrics", {}) for t in tweets]
                like_counts    = [p.get("like_count", 0)  for p in pm]
                reply_counts   = [p.get("reply_count", 0) for p in pm]
                likes_avg    = sum(like_counts)  // len(like_counts)
                comments_avg = sum(reply_counts) // len(reply_counts)
                if followers > 0:
                    eng = (sum(like_counts) + sum(reply_counts)) / len(tweets) / followers * 100
                    engagement_rate = f"{eng:.2f}"
    except Exception:
        pass

    return {
        "followers":  followers,
        "following":  metrics.get("following_count", 0),
        "post_count": metrics.get("tweet_count", 0),
        "extra": {
            "likes_avg":       likes_avg,
            "comments_avg":    comments_avg,
            "engagement_rate": engagement_rate,
        },
    }


def _get_username() -> str:
    resp = requests.get(f"{BASE_URL}/users/me", auth=_auth(), timeout=10, verify=ssl_verify())
    return resp.json()["data"]["username"]

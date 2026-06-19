"""
1시간 SNS 모니터링 작업 — APScheduler가 호출하는 순수 함수
H-04: 오류 발생 시 재시도 없이 notifications 테이블에 기록
H-05: 플랫폼 독립 실행
"""

import os
from datetime import datetime

from src.db import events as events_db
from src.notify import bus
from src.monitor.comment_monitor import NEGATIVE_KEYWORDS, IPO_SENSITIVE_KEYWORDS


def _classify_event(text: str) -> tuple[str, str]:
    """(sentiment, severity) 반환."""
    text_lower = text.lower()
    neg_hit = any(kw in text_lower for kw in NEGATIVE_KEYWORDS)
    ipo_hit = any(kw in text_lower for kw in IPO_SENSITIVE_KEYWORDS)

    if neg_hit:
        return "negative", "critical"
    if ipo_hit:
        return "ipo_sensitive", "warning"
    return "neutral", "info"


def _has_x_creds() -> bool:
    return all(os.getenv(k) for k in ["X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET"])


def _has_fb_creds() -> bool:
    return all(os.getenv(k) for k in ["META_PAGE_ACCESS_TOKEN", "META_PAGE_ID"])


def _has_threads_creds() -> bool:
    return all(os.getenv(k) for k in ["THREADS_ACCESS_TOKEN", "THREADS_USER_ID"])


def _process_live_x_event(mention: dict) -> dict:
    text = mention.get("text", "")
    sentiment, severity = _classify_event(text)
    return {
        "platform": "x",
        "event_type": "mention",
        "external_id": mention.get("id"),
        "author": mention.get("author_id", "unknown"),
        "text": text,
        "sentiment": sentiment,
        "severity": severity,
        "url": f"https://twitter.com/i/status/{mention.get('id')}",
        "raw": mention,
    }


def _process_live_fb_event(comment: dict) -> dict:
    text = comment.get("message", "")
    sentiment, severity = _classify_event(text)
    cursor_val = None
    created_time = comment.get("created_time", "")
    if created_time:
        try:
            from datetime import datetime, timezone
            dt = datetime.fromisoformat(created_time.replace("Z", "+00:00"))
            cursor_val = str(int(dt.timestamp()) + 1)  # +1: 동일 시각 재수집 방지
        except Exception:
            pass

    # Facebook 댓글 URL: comment.id는 "post_id_comment_id" 형식
    fb_url = None
    comment_id = comment.get("id", "")
    page_id = os.getenv("META_PAGE_ID", "")
    if page_id and comment_id:
        post_part = comment_id.split("_")[0] if "_" in comment_id else comment_id
        fb_url = f"https://www.facebook.com/{page_id}/posts/{post_part}"

    return {
        "platform": "facebook",
        "event_type": "comment",
        "external_id": comment_id,
        "author": comment.get("from", {}).get("name", "unknown"),
        "text": text,
        "sentiment": sentiment,
        "severity": severity,
        "url": fb_url,
        "raw": comment,
        "_cursor": cursor_val,
    }


def _process_live_threads_event(reply: dict) -> dict:
    text = reply.get("text", "")
    sentiment, severity = _classify_event(text)
    return {
        "platform": "threads",
        "event_type": "reply",
        "external_id": reply.get("id"),
        "author": reply.get("username", "unknown"),
        "text": text,
        "sentiment": sentiment,
        "severity": severity,
        "url": None,
        "raw": reply,
    }


def hourly_monitor_job():
    """
    1시간마다 X + Facebook + Threads SNS 폴링.
    자격증명이 설정되지 않은 플랫폼은 건너뜀.
    오류 발생 시 재시도 없이 notifications DB에 기록 (H-04).
    """
    platforms = []
    if _has_x_creds():
        platforms.append(("x", _fetch_x_events))
    if _has_fb_creds():
        platforms.append(("facebook", _fetch_fb_events))
    if _has_threads_creds():
        platforms.append(("threads", _fetch_threads_events))

    for platform, fetcher in platforms:
        try:
            cursor_info = events_db.get_cursor(platform)
            since_id = cursor_info.get("last_since_id")
            new_events = fetcher(since_id)

            latest_id = None
            for ev in new_events:
                event_id = events_db.insert_event(ev)
                if event_id and ev.get("severity") in ("critical", "warning"):
                    notif_id = events_db.insert_notification(
                        title=f"[{platform.upper()}] {ev['sentiment'].upper()} 이벤트 감지",
                        body=ev["text"][:200],
                        type_="monitor_alert",
                        severity=ev["severity"],
                        event_id=event_id,
                    )
                    bus.publish({"type": "notification.new", "id": notif_id, "severity": ev["severity"]})
                    bus.publish({"type": "monitor.event", "id": event_id, "platform": platform})
                # Facebook은 _cursor(Unix timestamp), 나머지는 external_id 사용
                latest_id = ev.get("_cursor") or ev.get("external_id") or latest_id

            events_db.update_cursor(platform, last_since_id=latest_id)

        except Exception as exc:
            notif_id = events_db.insert_notification(
                title=f"[{platform.upper()}] API 오류 발생",
                body=str(exc)[:500],
                type_="api_error",
                severity="critical",
            )
            bus.publish({"type": "notification.new", "id": notif_id, "severity": "critical"})
            events_db.update_cursor(platform, error=str(exc))

    _save_platform_stats()


def _fetch_x_events(since_id: str = None) -> list:
    from src.api.x_client import get_mentions
    raw = get_mentions(since_id=since_id)
    return [_process_live_x_event(m) for m in raw]


def _fetch_fb_events(since_id: str = None) -> list:
    from src.api.meta_client import get_page_comments
    # Facebook since 파라미터는 Unix 타임스탬프여야 함 — mock ID나 post ID는 무시
    valid_since = None
    if since_id:
        try:
            ts = int(since_id)
            if 1_000_000_000 < ts < 9_999_999_999:
                valid_since = since_id
        except (ValueError, TypeError):
            pass
    raw = get_page_comments(since_timestamp=valid_since)
    return [_process_live_fb_event(c) for c in raw]


def _fetch_threads_events(since_id: str = None) -> list:
    from src.api.threads_client import get_threads_replies
    raw = get_threads_replies(since_timestamp=since_id)
    return [_process_live_threads_event(r) for r in raw]


def _save_platform_stats() -> None:
    """각 플랫폼 계정 통계 스냅샷 저장 — H-04: 실패해도 조용히 무시."""
    # X
    if _has_x_creds():
        try:
            from src.api.x_client import get_account_stats as _x_stats
            events_db.save_account_snapshot("x", **_x_stats())
        except Exception:
            pass

    # Facebook
    if _has_fb_creds():
        try:
            from src.api.meta_client import get_page_stats
            events_db.save_account_snapshot("facebook", **get_page_stats())
        except Exception:
            pass

    # Instagram — META_IG_USER_ID 없으면 Facebook 페이지에서 자동 조회
    if os.getenv("META_PAGE_ACCESS_TOKEN") and os.getenv("META_PAGE_ID"):
        try:
            from src.api.meta_client import get_instagram_stats
            events_db.save_account_snapshot("instagram", **get_instagram_stats())
        except Exception:
            pass

    # Threads
    if _has_threads_creds():
        try:
            from src.api.threads_client import get_account_stats as _t_stats
            events_db.save_account_snapshot("threads", **_t_stats())
        except Exception:
            pass


def daily_meta_token_check():
    """
    매일 Meta 토큰 만료일 확인 — 14일 이내이면 자동 갱신.
    H-04: 갱신 실패 시 재시도 없이 critical 알림.
    """
    from src.api.meta_token import check_and_refresh_if_needed
    result = check_and_refresh_if_needed()

    if result["action"] == "refreshed":
        from src.db import creds as creds_db
        creds_db.load_all_to_env()
        notif_id = events_db.insert_notification(
            title="[META] 액세스 토큰 자동 갱신 완료",
            body=result["message"],
            type_="system_info",
            severity="info",
        )
        bus.publish({"type": "notification.new", "id": notif_id, "severity": "info"})

    elif result["action"] in ("expired", "error"):
        notif_id = events_db.insert_notification(
            title="[META] 토큰 갱신 실패 — 수동 재발급 필요",
            body=result["message"],
            type_="api_error",
            severity="critical",
        )
        bus.publish({"type": "notification.new", "id": notif_id, "severity": "critical"})


def daily_threads_token_check():
    """
    매일 Threads 토큰 체크 — 마지막 갱신 후 30일 경과 시 자동 갱신.
    H-04: 갱신 실패 시 재시도 없이 critical 알림.
    """
    from src.api.threads_token import check_and_refresh_if_needed
    result = check_and_refresh_if_needed()

    if result["action"] == "refreshed":
        notif_id = events_db.insert_notification(
            title="[THREADS] 액세스 토큰 자동 갱신 완료",
            body=result["message"],
            type_="system_info",
            severity="info",
        )
        bus.publish({"type": "notification.new", "id": notif_id, "severity": "info"})

    elif result["action"] == "error":
        notif_id = events_db.insert_notification(
            title="[THREADS] 토큰 갱신 실패 — OAuth 재연결 필요",
            body=result["message"],
            type_="api_error",
            severity="critical",
        )
        bus.publish({"type": "notification.new", "id": notif_id, "severity": "critical"})

    if result["action"] == "refreshed":
        from src.db import creds as creds_db
        creds_db.load_all_to_env()

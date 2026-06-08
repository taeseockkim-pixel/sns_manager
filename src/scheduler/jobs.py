"""
1시간 SNS 모니터링 작업 — APScheduler가 호출하는 순수 함수
H-04: 오류 발생 시 재시도 없이 notifications 테이블에 기록
H-05: 플랫폼 독립 실행
"""

import os
import random
import uuid
from datetime import datetime

from src.db import events as events_db
from src.notify import bus
from src.monitor.comment_monitor import _is_negative, NEGATIVE_KEYWORDS, IPO_SENSITIVE_KEYWORDS


_MOCK_X_EVENTS = [
    {"text": "CIMON 로봇 팔 정말 인상적이네요! 제조 현장에서 활용하고 싶습니다.", "sentiment": "neutral", "severity": "info", "author": "@mfg_engineer_kr"},
    {"text": "CIMON 주가 얼마나 오를까요? 상장 일정 아시는 분?", "sentiment": "ipo_sensitive", "severity": "warning", "author": "@stock_watcher"},
    {"text": "cimon 제품 사기 아닌가요? 실제로 써보니 광고랑 다름", "sentiment": "negative", "severity": "critical", "author": "@disgruntled_user"},
    {"text": "CIMON AI 비전 기술 데모 봤는데 대단하던데요 #AI #Manufacturing", "sentiment": "neutral", "severity": "info", "author": "@tech_investor"},
    {"text": "내부자 정보 없나요? CIMON 실적 어떤지", "sentiment": "ipo_sensitive", "severity": "warning", "author": "@insider_hunter"},
]

_MOCK_FB_EVENTS = [
    {"text": "CIMON 제품 문의드립니다. 납기 일정이 어떻게 되나요?", "sentiment": "neutral", "severity": "info", "author": "제조업 담당자"},
    {"text": "협업 로봇 결함 있다는 소문 사실인가요?", "sentiment": "negative", "severity": "warning", "author": "익명"},
    {"text": "CES에서 CIMON 부스 정말 좋았습니다! 기술력이 대단하네요.", "sentiment": "neutral", "severity": "info", "author": "전시회 방문객"},
]


def _mock_events(platform: str) -> list:
    """Mock 이벤트 1-2개 생성 (API_MODE=mock 전용)."""
    pool = _MOCK_X_EVENTS if platform == "x" else _MOCK_FB_EVENTS
    sample = random.sample(pool, k=min(2, len(pool)))
    events = []
    for item in sample:
        events.append({
            "platform": platform,
            "event_type": "mention" if platform == "x" else "comment",
            "external_id": f"mock-{platform}-{uuid.uuid4().hex[:8]}",
            "author": item["author"],
            "text": item["text"],
            "sentiment": item["sentiment"],
            "severity": item["severity"],
            "url": None,
        })
    return events


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
    return {
        "platform": "facebook",
        "event_type": "comment",
        "external_id": comment.get("id"),
        "author": comment.get("from", {}).get("name", "unknown"),
        "text": text,
        "sentiment": sentiment,
        "severity": severity,
        "url": None,
        "raw": comment,
    }


def hourly_monitor_job():
    """
    1시간마다 X + Facebook SNS 폴링.
    API_MODE=mock 이면 가상 이벤트 사용.
    오류 발생 시 재시도 없이 notifications DB에 기록 (H-04).
    """
    api_mode = os.getenv("API_MODE", "mock").lower()
    platforms = [
        ("x", _fetch_x_events if api_mode != "mock" else None),
        ("facebook", _fetch_fb_events if api_mode != "mock" else None),
    ]

    for platform, fetcher in platforms:
        try:
            cursor_info = events_db.get_cursor(platform)
            since_id = cursor_info.get("last_since_id")

            if api_mode == "mock":
                new_events = _mock_events(platform)
            else:
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
                if ev.get("external_id"):
                    latest_id = ev["external_id"]

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


def _fetch_x_events(since_id: str = None) -> list:
    from src.api.x_client import get_mentions
    raw = get_mentions(since_id=since_id)
    return [_process_live_x_event(m) for m in raw]


def _fetch_fb_events(since_id: str = None) -> list:
    from src.api.meta_client import get_page_comments
    raw = get_page_comments(since_timestamp=since_id)
    return [_process_live_fb_event(c) for c in raw]

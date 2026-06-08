"""
댓글·반응 모니터링 — 부정적 반응 감지 시 즉시 알림
H-04: 에러 발생 시 재시도 없이 에스컬레이션
"""

import os
import time
import json
import smtplib
import requests
from email.mime.text import MIMEText

from src.api.x_client import get_mentions


NEGATIVE_KEYWORDS = [
    "사기", "거짓", "fake", "fraud", "scam", "위험", "danger",
    "리콜", "recall", "부도", "파산", "문제", "하자", "결함",
    "불만", "환불", "소송", "피해", "손해",
]

IPO_SENSITIVE_KEYWORDS = [
    "실적", "매출", "영업이익", "적자", "흑자", "주가", "상장",
    "공모가", "증자", "유증", "insider", "내부자",
]


def _is_negative(text: str) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in NEGATIVE_KEYWORDS + IPO_SENSITIVE_KEYWORDS)


def _send_alert(message: str):
    """이슈 알림 발송 (Slack 우선, 없으면 이메일)."""
    slack_url = os.getenv("SLACK_WEBHOOK_URL")
    if slack_url:
        requests.post(slack_url, json={"text": f"🚨 SNS 이슈 감지:\n{message}"}, timeout=5)
        return

    email = os.getenv("ALERT_EMAIL", "taeseock.kim@cimon.com")
    print(f"[ALERT] {email}: {message}")


def check_once_x(since_id: str = None) -> list:
    """
    X 멘션을 한 번만 수집하여 반환. APScheduler 호출용.
    반환: [{"text": ..., "id": ..., "author_id": ...}, ...]
    """
    return get_mentions(since_id=since_id)


def monitor_x(poll_interval_sec: int = 300):
    """X 멘션 폴링 모니터링 (5분 간격)."""
    since_id = None
    print(f"X 모니터링 시작 (간격: {poll_interval_sec}초)")

    while True:
        try:
            mentions = get_mentions(since_id=since_id)
            for m in mentions:
                text = m.get("text", "")
                if _is_negative(text):
                    _send_alert(f"부정적 X 멘션 감지:\n{text}\n\nURL: https://twitter.com/i/status/{m['id']}")
                since_id = m["id"]
        except Exception as e:
            _send_alert(f"X 모니터링 오류 (재시도 없음): {e}")

        time.sleep(poll_interval_sec)


if __name__ == "__main__":
    monitor_x()

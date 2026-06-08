"""
Mock 데이터 시드 — API_MODE=mock 시 DB가 비어 있으면 샘플 데이터 삽입
"""

import json
import os

from src.db import queue as queue_db
from src.db import events as events_db


_MOCK_QUEUE_ITEMS = [
    {
        "platform": "x",
        "topic": "자율주행 소프트웨어 v3.2 업데이트",
        "ko": {
            "text": "CIMON의 자율주행 소프트웨어 v3.2가 출시되었습니다. 장애물 감지 정확도 98.7%, 반응 속도 15% 향상으로 더욱 안전한 현장 자동화를 실현합니다. #CIMON #자율주행 #스마트팩토리",
            "hashtags": ["CIMON", "자율주행", "스마트팩토리"],
        },
        "en": {
            "text": "CIMON's Autonomous Software v3.2 is now live. With 98.7% obstacle detection accuracy and 15% faster response time, we're setting new standards in safe factory automation. #CIMON #AutonomousDriving #SmartFactory",
            "hashtags": ["CIMON", "AutonomousDriving", "SmartFactory"],
        },
        "brand_safety_score": 94.5,
        "scheduled_at": None,
    },
    {
        "platform": "facebook",
        "topic": "CES 2025 참가 안내",
        "ko": {
            "text": "CIMON이 CES 2025에 참가합니다! 1월 7-10일 라스베이거스 컨벤션 센터 Booth #3421에서 최신 AI 로봇 솔루션을 직접 경험해 보세요. 사전 미팅 신청은 링크를 통해 진행해 주세요.",
            "hashtags": ["CES2025", "CIMON", "AI로봇"],
        },
        "en": {
            "text": "CIMON is heading to CES 2025! Visit us at Booth #3421, Las Vegas Convention Center, January 7-10. Experience our cutting-edge AI robotics solutions firsthand. Schedule a meeting via the link below.",
            "hashtags": ["CES2025", "CIMON", "AIRobotics"],
        },
        "brand_safety_score": 88.0,
        "scheduled_at": None,
    },
    {
        "platform": "x",
        "topic": "스마트팩토리 도입 고객사 사례",
        "ko": {
            "text": "국내 대형 자동차 부품사 A사가 CIMON의 협동로봇을 도입한 후 생산 효율 32% 향상, 불량률 0.3% 달성에 성공했습니다. 스마트팩토리의 가능성을 함께 만들어가겠습니다. #CIMON #협동로봇 #제조혁신",
            "hashtags": ["CIMON", "협동로봇", "제조혁신"],
        },
        "en": {
            "text": "Auto parts manufacturer A achieved 32% productivity gain and 0.3% defect rate after deploying CIMON's collaborative robots. Together, we're building the future of smart manufacturing. #CIMON #Cobot #Manufacturing",
            "hashtags": ["CIMON", "Cobot", "Manufacturing"],
        },
        "brand_safety_score": 91.2,
        "scheduled_at": None,
    },
]

_MOCK_EVENTS = [
    {
        "platform": "x",
        "event_type": "mention",
        "external_id": "mock-x-001",
        "author": "@mfg_engineer_kr",
        "text": "CIMON 로봇 팔 실제로 써봤는데 정말 인상적이네요! 자동차 부품 라인에 도입 검토 중입니다.",
        "sentiment": "neutral",
        "severity": "info",
        "url": "https://twitter.com/i/status/mock001",
    },
    {
        "platform": "x",
        "event_type": "mention",
        "external_id": "mock-x-002",
        "author": "@stock_analyst_99",
        "text": "CIMON 상장 일정이랑 공모가 정보 아시는 분 계신가요? 실적 궁금한데",
        "sentiment": "ipo_sensitive",
        "severity": "warning",
        "url": "https://twitter.com/i/status/mock002",
    },
    {
        "platform": "x",
        "event_type": "mention",
        "external_id": "mock-x-003",
        "author": "@industrial_critic",
        "text": "cimon 제품 사기 아닌가요? 광고랑 실제가 다르다는 후기가 있던데. 결함 있다는 소문도",
        "sentiment": "negative",
        "severity": "critical",
        "url": "https://twitter.com/i/status/mock003",
    },
    {
        "platform": "facebook",
        "event_type": "comment",
        "external_id": "mock-fb-001",
        "author": "김제조 팀장",
        "text": "CES 2025 부스 미팅 신청하고 싶습니다. 연락처를 남겨주세요.",
        "sentiment": "neutral",
        "severity": "info",
        "url": None,
    },
    {
        "platform": "facebook",
        "event_type": "comment",
        "external_id": "mock-fb-002",
        "author": "익명",
        "text": "협업 로봇에 하자가 있다는 소문이 있는데 사실인가요? 환불이나 보상 가능한지요",
        "sentiment": "negative",
        "severity": "warning",
        "url": None,
    },
]

_MOCK_NOTIFICATIONS = [
    {
        "type": "monitor_alert",
        "title": "[X] NEGATIVE 이벤트 감지",
        "body": "cimon 제품 사기 아닌가요? 광고랑 실제가 다르다는 후기가 있던데...",
        "severity": "critical",
    },
    {
        "type": "monitor_alert",
        "title": "[X] IPO_SENSITIVE 이벤트 감지",
        "body": "CIMON 상장 일정이랑 공모가 정보 아시는 분 계신가요?",
        "severity": "warning",
    },
    {
        "type": "queue_new",
        "title": "새 콘텐츠 승인 대기",
        "body": "자율주행 소프트웨어 v3.2 업데이트 (X, 점수: 94.5)",
        "severity": "info",
    },
]


def seed_mock_data():
    """DB가 비어 있을 때만 Mock 데이터 삽입."""
    if os.getenv("API_MODE", "mock").lower() != "mock":
        return

    from src.db.migrations import get_conn
    with get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM approval_queue").fetchone()[0]
    if count > 0:
        return

    for item in _MOCK_QUEUE_ITEMS:
        queue_db.enqueue(item)

    for ev in _MOCK_EVENTS:
        events_db.insert_event(ev)

    for notif in _MOCK_NOTIFICATIONS:
        events_db.insert_notification(
            title=notif["title"],
            body=notif["body"],
            type_=notif["type"],
            severity=notif["severity"],
        )

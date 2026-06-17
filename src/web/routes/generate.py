"""
콘텐츠 생성 라우터
Mock 모드: 템플릿 기반 즉시 생성
Live 모드: Claude API 호출 (ANTHROPIC_API_KEY 필요)
H-01: 생성만 함 — 게시는 반드시 사람 승인 후
"""

import json
import os
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.db import events as events_db
from src.db import queue as queue_db
from src.notify import bus
from src.web.auth import verify_credentials

router = APIRouter()
_TEMPLATE_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATE_DIR))

_MOCK_TEMPLATES = {
    "x": {
        "ko": "CIMON의 {topic} 소식을 전합니다. 스마트팩토리 혁신을 위한 끊임없는 노력으로 제조 현장의 가능성을 확장하겠습니다. #CIMON #스마트팩토리 #제조혁신",
        "en": "Exciting news about {topic} from CIMON. We continue to push the boundaries of smart manufacturing innovation. #CIMON #SmartFactory #Manufacturing",
        "hashtags_ko": ["CIMON", "스마트팩토리", "제조혁신"],
        "hashtags_en": ["CIMON", "SmartFactory", "Manufacturing"],
        "score": 88.0,
    },
    "instagram": {
        "ko": "{topic}\n\nCIMON이 만들어가는 스마트 제조의 미래.\n자동화와 AI 기술로 현장을 혁신합니다.\n\n#CIMON #스마트팩토리 #제조혁신 #협동로봇 #AI #자동화",
        "en": "{topic}\n\nThe future of smart manufacturing, powered by CIMON.\nTransforming the factory floor with automation and AI.\n\n#CIMON #SmartFactory #Manufacturing #Cobot #AI #Automation",
        "hashtags_ko": ["CIMON", "스마트팩토리", "제조혁신", "협동로봇", "AI", "자동화"],
        "hashtags_en": ["CIMON", "SmartFactory", "Manufacturing", "Cobot", "AI", "Automation"],
        "score": 86.0,
    },
    "facebook": {
        "ko": "📢 {topic}\n\nCIMON은 국내 제조 산업의 디지털 전환을 이끌고 있습니다.\n\n협동로봇과 AI 비전 솔루션으로 생산 현장의 효율성을 극대화하고 작업자의 안전을 보장합니다. 더 자세한 내용은 CIMON 공식 홈페이지를 방문해 주세요.\n\n#CIMON #제조혁신 #협동로봇 #스마트팩토리",
        "en": "📢 {topic}\n\nCIMON is leading the digital transformation of Korean manufacturing.\n\nOur collaborative robots and AI vision solutions maximize production efficiency while ensuring worker safety. Visit CIMON's official website for more information.\n\n#CIMON #Manufacturing #Cobot #SmartFactory",
        "hashtags_ko": ["CIMON", "제조혁신", "협동로봇", "스마트팩토리"],
        "hashtags_en": ["CIMON", "Manufacturing", "Cobot", "SmartFactory"],
        "score": 87.0,
    },
    "threads": {
        "ko": "CIMON의 {topic} 소식을 전합니다. 스마트 제조의 혁신을 함께 만들어갑니다. #CIMON #스마트팩토리 #제조혁신",
        "en": "Latest update from CIMON on {topic}. Building the future of smart manufacturing together. #CIMON #SmartFactory",
        "hashtags_ko": ["CIMON", "스마트팩토리", "제조혁신"],
        "hashtags_en": ["CIMON", "SmartFactory"],
        "score": 87.0,
    },
}


def _generate_mock(platform: str, topic: str) -> dict:
    tpl = _MOCK_TEMPLATES.get(platform, _MOCK_TEMPLATES["x"])
    return {
        "platform": platform,
        "topic": topic,
        "ko": {"text": tpl["ko"].format(topic=topic), "hashtags": tpl["hashtags_ko"]},
        "en": {"text": tpl["en"].format(topic=topic), "hashtags": tpl["hashtags_en"]},
        "brand_safety_score": tpl["score"],
    }


def _generate_live(platform: str, topic: str) -> dict:
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    platform_guide = {
        "x": "280자 이내, 간결하게, 해시태그 2-3개",
        "instagram": "캡션 스타일, 줄바꿈 활용, 해시태그 5-6개",
        "facebook": "자연스러운 문체, 이모지 1-2개, 해시태그 3-4개",
        "threads": "500자 이내, 간결하게, 해시태그 2-3개",
    }.get(platform, "280자 이내")

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": (
                f"CIMON(스마트팩토리 로봇·AI 솔루션 회사, IPO 준비 중) SNS 게시물 생성.\n"
                f"플랫폼: {platform} ({platform_guide})\n"
                f"주제: {topic}\n\n"
                f"JSON으로만 응답 (다른 텍스트 없이):\n"
                f'{{\"ko_text\": \"한국어 본문\", \"ko_hashtags\": [\"태그1\"], '
                f'\"en_text\": \"English text\", \"en_hashtags\": [\"tag1\"], '
                f'\"brand_safety_score\": 0~100}}\n\n'
                f"IPO 민감 정보(주가, 공모가, 상장 일정, 내부 정보 등) 절대 포함 금지."
            ),
        }],
    )

    data = json.loads(msg.content[0].text)
    return {
        "platform": platform,
        "topic": topic,
        "ko": {"text": data["ko_text"], "hashtags": data.get("ko_hashtags", [])},
        "en": {"text": data["en_text"], "hashtags": data.get("en_hashtags", [])},
        "brand_safety_score": float(data.get("brand_safety_score", 80)),
    }


@router.post("/generate", response_class=HTMLResponse)
async def generate_content(
    request: Request,
    topic: str = Form(...),
    platforms: list[str] = Form(...),
    reviewer: str = Depends(verify_credentials),
):
    use_mock = not os.getenv("ANTHROPIC_API_KEY")

    results = []
    errors = []

    for platform in platforms:
        try:
            content = _generate_mock(platform, topic) if use_mock else _generate_live(platform, topic)

            if content["brand_safety_score"] < 80:
                errors.append(f"{platform.upper()}: 브랜드 안전 점수 미달 ({content['brand_safety_score']:.0f}점, 기준 80점)")
                continue

            queue_id = queue_db.enqueue(content)
            events_db.insert_notification(
                title=f"새 콘텐츠 생성 [{platform.upper()}]",
                body=f"{topic} (점수: {content['brand_safety_score']:.0f})",
                type_="queue_new",
                severity="info",
                queue_id=queue_id,
            )
            bus.publish({"type": "queue.new", "id": queue_id, "platform": platform})
            results.append(platform.upper())
        except Exception as exc:
            errors.append(f"{platform.upper()}: {str(exc)[:120]}")

    pending_items = queue_db.list_all("pending")
    return templates.TemplateResponse(
        request,
        "partials/generate_result.html",
        {"results": results, "errors": errors, "topic": topic, "items": pending_items},
    )

"""
콘텐츠 생성 라우터 — 제품/회사 홍보물 생성
Live 모드 전용: Claude API 호출 (ANTHROPIC_API_KEY 필수)
H-01: 생성만 함 — 게시는 반드시 사람 승인 후
"""

import json
import os
import re
from datetime import datetime
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
_DELIVERABLES_DIR = Path(__file__).resolve().parents[3] / "deliverables"
templates = Jinja2Templates(directory=str(_TEMPLATE_DIR))


def _has_cjk(text: str) -> bool:
    """한자·일본어·중국어 문자(CJK) 포함 여부 검사. 한글·영문·숫자·이모지는 허용."""
    for ch in text:
        cp = ord(ch)
        if (0x4E00 <= cp <= 0x9FFF   # CJK 통합 한자
                or 0x3400 <= cp <= 0x4DBF   # CJK 확장 A
                or 0xF900 <= cp <= 0xFAFF   # CJK 호환 한자
                or 0x3040 <= cp <= 0x30FF): # 히라가나·가타카나
            return True
    return False


def _build_prompt(platform: str, platform_guide: str, profile_ctx: str, topic: str, points_ctx: str) -> str:
    return (
        f"[필수 언어 규칙] ko_text 필드는 반드시 순수 한글(가나다라마바사...)만 사용하세요. "
        f"한자(漢字), 일본어, 중국어 문자는 단 한 글자도 허용되지 않습니다. "
        f"예: 企業→기업, 仕樣→사양, 技術→기술 으로 반드시 한글로 변환하세요.\n\n"
        f"{profile_ctx}\n"
        f"위 회사 정보를 바탕으로 SNS 홍보 게시물을 작성해 주세요.\n"
        f"플랫폼: {platform} ({platform_guide})\n"
        f"주제: {topic}{points_ctx}\n\n"
        f"JSON으로만 응답 (다른 텍스트 없이, 마크다운 코드블록 없이):\n"
        f'{{\"ko_text\": \"한국어 본문\", \"ko_hashtags\": [\"태그1\"], '
        f'\"en_text\": \"English text\", \"en_hashtags\": [\"tag1\"], '
        f'\"brand_safety_score\": 0~100}}\n\n'
        f"주의: IPO, 주가, 상장, 공모가 등 투자 관련 내용은 절대 포함하지 마세요."
    )


def _parse_response(response_text: str) -> dict:
    clean = response_text.strip()
    if clean.startswith("```"):
        clean = clean.split("```", 2)[-1] if clean.count("```") >= 2 else clean
        clean = clean.lstrip("json").strip().rstrip("```").strip()
    return json.loads(clean)


def _generate_live(platform: str, topic: str, points: str = "") -> dict:
    from src.ai.client import call_ai

    platform_guide = {
        "x": "280자 이내, 간결하게, 해시태그 2-3개",
        "instagram": "캡션 스타일, 줄바꿈 활용, 이모지 적절히, 해시태그 5-6개",
        "facebook": "자연스러운 문체, 이모지 1-2개, 해시태그 3-4개",
        "threads": "500자 이내, 간결하게, 해시태그 2-3개",
    }.get(platform, "280자 이내")

    company_desc = os.getenv("COMPANY_DESCRIPTION", "스마트팩토리 솔루션 전문기업")
    products = os.getenv("COMPANY_PRODUCTS", "")
    selling_points = os.getenv("COMPANY_SELLING_POINTS", "")
    target = os.getenv("COMPANY_TARGET", "산업 자동화 분야 엔지니어 및 기업 담당자")
    tone = os.getenv("COMPANY_TONE", "전문적")

    profile_ctx = f"회사: CIMON\n회사 소개: {company_desc}\n타겟 고객: {target}\n브랜드 톤: {tone}\n"
    if products:
        profile_ctx += f"주요 제품/서비스: {products}\n"
    if selling_points:
        profile_ctx += f"핵심 셀링 포인트: {selling_points}\n"

    points_ctx = f"\n홍보 포인트 (강조할 내용):\n{points.strip()}" if points.strip() else ""

    prompt = _build_prompt(platform, platform_guide, profile_ctx, topic, points_ctx)
    data = _parse_response(call_ai(prompt, max_tokens=1024))

    # 한자 감지 시 1회 재시도
    if _has_cjk(data.get("ko_text", "")):
        retry_prompt = prompt + "\n\n[경고] 이전 응답에 한자가 포함되었습니다. ko_text에 한자가 전혀 없도록 다시 작성하세요."
        data = _parse_response(call_ai(retry_prompt, max_tokens=1024))
        if _has_cjk(data.get("ko_text", "")):
            raise RuntimeError("AI가 한자를 포함한 텍스트를 반복 생성했습니다. 잠시 후 다시 시도해 주세요.")

    return {
        "platform": platform,
        "topic": topic,
        "ko": {"text": data["ko_text"], "hashtags": data.get("ko_hashtags", [])},
        "en": {"text": data["en_text"], "hashtags": data.get("en_hashtags", [])},
        "brand_safety_score": float(data.get("brand_safety_score", 80)),
    }


def _save_promo_file(topic: str, generated_items: list) -> str:
    """생성된 홍보물을 deliverables/ 디렉토리에 Markdown 파일로 저장."""
    _DELIVERABLES_DIR.mkdir(exist_ok=True)
    slug = re.sub(r"[^\w\s-]", "", topic)[:30].strip().replace(" ", "_")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"promo_{slug}_{ts}.md"

    lines = [
        f"# 홍보물 — {topic}\n\n",
        f"생성일: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n",
        "---\n\n",
    ]
    for item in generated_items:
        p = item["platform"].upper()
        lines.append(f"## {p}\n\n")
        lines.append(f"### 국문\n\n{item['ko']['text']}\n\n")
        if item["ko"]["hashtags"]:
            lines.append("**해시태그:** " + " ".join(f"#{t}" for t in item["ko"]["hashtags"]) + "\n\n")
        lines.append(f"### 영문\n\n{item['en']['text']}\n\n")
        if item["en"]["hashtags"]:
            lines.append("**Hashtags:** " + " ".join(f"#{t}" for t in item["en"]["hashtags"]) + "\n\n")
        lines.append("---\n\n")

    (_DELIVERABLES_DIR / filename).write_text("".join(lines), encoding="utf-8")
    return filename


@router.post("/generate", response_class=HTMLResponse)
async def generate_content(
    request: Request,
    topic: str = Form(...),
    points: str = Form(default=""),
    platforms: list[str] = Form(...),
    reviewer: str = Depends(verify_credentials),
):
    pending_items = queue_db.list_all("pending")

    if not os.getenv("GROQ_API_KEY") and not os.getenv("GEMINI_API_KEY") and not os.getenv("ANTHROPIC_API_KEY"):
        return templates.TemplateResponse(
            request,
            "partials/generate_result.html",
            {
                "results": [],
                "errors": [
                    "AI API 키가 설정되지 않았습니다. "
                    "설정 페이지에서 GEMINI_API_KEY(무료) 또는 ANTHROPIC_API_KEY를 등록해 주세요."
                ],
                "topic": topic,
                "items": pending_items,
                "saved_filename": None,
            },
        )

    results = []
    generated_items = []
    errors = []

    for platform in platforms:
        try:
            content = _generate_live(platform, topic, points)

            if content["brand_safety_score"] < 80:
                errors.append(
                    f"{platform.upper()}: 브랜드 안전 점수 미달 "
                    f"({content['brand_safety_score']:.0f}점, 기준 80점)"
                )
                continue

            queue_id = queue_db.enqueue(content)
            events_db.insert_notification(
                title=f"새 홍보물 생성 [{platform.upper()}]",
                body=f"{topic} (점수: {content['brand_safety_score']:.0f})",
                type_="queue_new",
                severity="info",
                queue_id=queue_id,
            )
            bus.publish({"type": "queue.new", "id": queue_id, "platform": platform})
            results.append(platform.upper())
            generated_items.append(content)
        except Exception as exc:
            errors.append(f"{platform.upper()}: {str(exc)[:120]}")

    saved_filename = None
    if generated_items:
        try:
            saved_filename = _save_promo_file(topic, generated_items)
        except Exception:
            pass

    pending_items = queue_db.list_all("pending")
    return templates.TemplateResponse(
        request,
        "partials/generate_result.html",
        {
            "results": results,
            "errors": errors,
            "topic": topic,
            "items": pending_items,
            "saved_filename": saved_filename,
        },
    )

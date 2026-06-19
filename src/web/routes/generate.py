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
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
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

_MAX_UPLOAD_BYTES = 4 * 1024 * 1024  # 4 MB
_SUPPORTED_EXTS = (".pdf", ".docx", ".txt", ".png", ".jpg", ".jpeg", ".gif", ".webp")


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


# ── 파일 텍스트 추출 ────────────────────────────────────────────

def _extract_text_from_file(file_bytes: bytes, filename: str) -> str:
    """업로드된 파일에서 텍스트 추출. 지원: PDF, DOCX, TXT, 이미지."""
    name = filename.lower()

    if name.endswith(".pdf"):
        import io
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        pages = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                pages.append(t.strip())
        if not pages:
            raise ValueError("PDF에서 텍스트를 추출할 수 없습니다. 스캔 이미지 PDF라면 PNG/JPG로 첨부해 주세요.")
        return "\n\n".join(pages)

    elif name.endswith(".docx"):
        import io
        import docx
        doc = docx.Document(io.BytesIO(file_bytes))
        paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
        if not paragraphs:
            raise ValueError("DOCX에서 텍스트를 추출할 수 없습니다.")
        return "\n".join(paragraphs)

    elif name.endswith(".txt"):
        for enc in ("utf-8", "cp949", "euc-kr"):
            try:
                return file_bytes.decode(enc)
            except UnicodeDecodeError:
                continue
        return file_bytes.decode("utf-8", errors="replace")

    elif name.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
        return _extract_image_text(file_bytes, name)

    raise ValueError(f"지원하지 않는 파일 형식입니다. 지원: PDF, DOCX, TXT, PNG, JPG")


def _extract_image_text(file_bytes: bytes, filename: str) -> str:
    """Vision AI(Anthropic 또는 Gemini)로 이미지에서 텍스트·정보 추출."""
    import base64

    ext = filename.rsplit(".", 1)[-1].lower()
    mime_map = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "gif": "image/gif", "webp": "image/webp"}
    mime = mime_map.get(ext, "image/jpeg")

    question = "이 이미지/문서에서 제품명, 주요 기능, 사양, 홍보 포인트 등 모든 텍스트 정보를 자세히 추출해 주세요."

    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()

    if anthropic_key:
        import anthropic
        import httpx
        b64 = base64.standard_b64encode(file_bytes).decode()
        client = anthropic.Anthropic(api_key=anthropic_key, http_client=httpx.Client(verify=False))
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}},
                {"type": "text", "text": question},
            ]}],
        )
        return msg.content[0].text

    elif gemini_key:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=gemini_key)
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=types.Content(
                role="user",
                parts=[
                    types.Part.from_bytes(data=file_bytes, mime_type=mime),
                    types.Part.from_text(question),
                ],
            ),
        )
        return response.text

    raise RuntimeError("이미지 분석에는 ANTHROPIC_API_KEY 또는 GEMINI_API_KEY가 필요합니다.")


def _analyze_document(extracted_text: str) -> dict:
    """AI로 문서 텍스트에서 SNS 홍보용 주제·포인트·핵심특징 추출."""
    from src.ai.client import call_ai
    prompt = (
        "아래 문서 내용에서 SNS 홍보물 작성에 필요한 정보를 추출하세요.\n\n"
        f"문서:\n{extracted_text[:3000]}\n\n"
        "[필수 언어 규칙] 모든 텍스트는 순수 한글만 사용하세요. 한자/일본어 절대 금지.\n"
        "JSON으로만 응답 (마크다운 코드블록 없이):\n"
        '{"topic": "홍보 주제 한 줄 (순수 한글)", '
        '"points": "- 포인트1\\n- 포인트2\\n- 포인트3 (순수 한글)", '
        '"key_features": ["특징1", "특징2", "특징3"]}\n'
        "key_features 는 최대 5개 배열. 모두 순수 한글로."
    )
    try:
        response = call_ai(prompt, max_tokens=512)
        return _parse_response(response)
    except Exception:
        return {"topic": "", "points": "", "key_features": []}


def _generate_image_prompt(topic: str, key_features: list) -> str:
    """SNS 홍보 이미지용 생성 프롬프트 (Midjourney/Canva/DALL-E 등에서 사용)."""
    features = ", ".join(key_features[:3]) if key_features else "industrial automation, smart factory"
    return (
        f"Professional promotional banner for CIMON, Korean smart factory HMI software company. "
        f"Subject: {topic}. Key features: {features}. "
        f"Modern corporate design, blue and white color scheme (#1d4ed8 primary), "
        f"industrial HMI interface visuals, clean minimalist layout, "
        f"no text overlay, photorealistic, 16:9 aspect ratio."
    )


def _render_pamphlet(topic: str, gen_date: str, key_features: list, items: list, image_prompt: str = "") -> str:
    """Jinja2 템플릿으로 HTML 팜플렛 렌더링."""
    tmpl = templates.get_template("partials/pamphlet.html")
    return tmpl.render(topic=topic, gen_date=gen_date, key_features=key_features, items=items, image_prompt=image_prompt)


# ── SNS 콘텐츠 생성 ─────────────────────────────────────────────

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


# ── 메인 엔드포인트 ─────────────────────────────────────────────

@router.post("/generate", response_class=HTMLResponse)
async def generate_content(
    request: Request,
    topic: str = Form(default=""),
    points: str = Form(default=""),
    platforms: list[str] = Form(...),
    attachment: Optional[UploadFile] = File(default=None),
    reviewer: str = Depends(verify_credentials),
):
    pending_items = queue_db.list_all("pending")
    results: list[str] = []
    generated_items: list[dict] = []
    errors: list[str] = []
    key_features: list[str] = []

    if not os.getenv("GROQ_API_KEY") and not os.getenv("GEMINI_API_KEY") and not os.getenv("ANTHROPIC_API_KEY"):
        return templates.TemplateResponse(
            request,
            "partials/generate_result.html",
            {
                "results": [], "errors": [
                    "AI API 키가 설정되지 않았습니다. "
                    "설정 페이지에서 GEMINI_API_KEY(무료) 또는 ANTHROPIC_API_KEY를 등록해 주세요."
                ],
                "topic": topic, "items": pending_items,
                "saved_filename": None, "pamphlet_html": None, "pamphlet_b64": None,
            },
        )

    # ── 첨부 파일 처리 ──
    if attachment and attachment.filename:
        fname = attachment.filename
        ext = Path(fname).suffix.lower()
        if ext not in _SUPPORTED_EXTS:
            errors.append(f"지원하지 않는 파일 형식입니다 ({ext}). PDF, DOCX, TXT, PNG, JPG 파일을 첨부해 주세요.")
        else:
            file_bytes = await attachment.read()
            if len(file_bytes) > _MAX_UPLOAD_BYTES:
                errors.append(f"파일 크기 초과 ({len(file_bytes) // 1024}KB). 최대 4MB까지 가능합니다.")
            else:
                try:
                    extracted_text = _extract_text_from_file(file_bytes, fname)
                    doc_info = _analyze_document(extracted_text)
                    # 사용자가 입력하지 않은 항목만 파일에서 자동 보완
                    if not topic.strip() and doc_info.get("topic"):
                        topic = doc_info["topic"]
                    if not points.strip() and doc_info.get("points"):
                        points = doc_info["points"]
                    key_features = [f for f in doc_info.get("key_features", []) if f]
                except Exception as exc:
                    errors.append(f"파일 분석 오류: {str(exc)[:150]}")

    if not topic.strip():
        errors.append("주제를 입력하거나 제품 자료 파일을 첨부해 주세요.")
        return templates.TemplateResponse(
            request,
            "partials/generate_result.html",
            {"results": [], "errors": errors, "topic": topic, "items": pending_items,
             "saved_filename": None, "pamphlet_html": None, "pamphlet_b64": None},
        )

    # ── 플랫폼별 SNS 콘텐츠 생성 ──
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
    pamphlet_html = None
    pamphlet_b64 = None
    if generated_items:
        try:
            saved_filename = _save_promo_file(topic, generated_items)
        except Exception:
            pass
        try:
            import base64 as _b64
            gen_date = datetime.now().strftime("%Y-%m-%d %H:%M")
            image_prompt = _generate_image_prompt(topic, key_features)
            pamphlet_html = _render_pamphlet(topic, gen_date, key_features, generated_items, image_prompt)
            pamphlet_b64 = _b64.b64encode(pamphlet_html.encode("utf-8")).decode()
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
            "pamphlet_html": pamphlet_html,
            "pamphlet_b64": pamphlet_b64,
        },
    )

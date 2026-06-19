"""
공통 AI 클라이언트.
우선순위: GROQ_API_KEY(무료) → GEMINI_API_KEY(무료) → ANTHROPIC_API_KEY(유료)
"""

import os


def call_ai(prompt: str, max_tokens: int = 1024) -> str:
    """설정된 AI 키 순서대로 시도하여 텍스트를 반환."""
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip()

    if groq_key:
        return _call_groq(groq_key, prompt, max_tokens)
    elif gemini_key:
        return _call_gemini(gemini_key, prompt, max_tokens)
    elif anthropic_key:
        return _call_anthropic(anthropic_key, prompt, max_tokens)
    else:
        raise RuntimeError(
            "AI API 키가 설정되지 않았습니다. "
            "설정 페이지에서 GROQ_API_KEY(무료) 또는 GEMINI_API_KEY를 등록해 주세요."
        )


def _call_groq(api_key: str, prompt: str, max_tokens: int) -> str:
    import httpx
    from groq import Groq

    client = Groq(api_key=api_key, http_client=httpx.Client(verify=False))
    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
    )
    return completion.choices[0].message.content


def _call_gemini(api_key: str, prompt: str, max_tokens: int) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
        config=types.GenerateContentConfig(max_output_tokens=max_tokens),
    )
    return response.text


def _call_anthropic(api_key: str, prompt: str, max_tokens: int) -> str:
    import anthropic
    import httpx

    client = anthropic.Anthropic(
        api_key=api_key,
        http_client=httpx.Client(verify=False),
    )
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text

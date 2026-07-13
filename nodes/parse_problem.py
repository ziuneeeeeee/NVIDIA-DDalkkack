"""
nodes/parse_problem.py
───────────────────────
문제/답안을 텍스트로 정제하는 노드. (실제 GPT-4o Vision 연결)

MD 섹션 3.3:
  - 텍스트 입력: 그대로 통과
  - 이미지 URL 입력: GPT-4o Vision OCR → 텍스트 추출

우선순위 (MD 16):
  타이핑 입력 지원이 기본, 이미지 파싱은 스트레치 골
"""

from __future__ import annotations

import base64
import os

from core.clients import get_openai_client
from core.state import GradingState

MODEL = "gpt-4o"

PARSE_SYSTEM = """
당신은 시험 문제 파싱 전문가입니다.
이미지에서 문제와 보기를 정확하게 텍스트로 추출하세요.
수식은 LaTeX로, 코드는 코드블록으로, 표는 마크다운 테이블로 재현하세요.
"""


def _is_image_path(text: str) -> bool:
    """문자열이 이미지 파일 경로인지 판단."""
    ext = os.path.splitext(text.strip().lower())[1]
    return ext in {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def _is_url(text: str) -> bool:
    return text.strip().startswith(("http://", "https://"))


def _parse_image(image_source: str) -> str:
    """GPT-4o Vision으로 이미지에서 문제 텍스트 추출."""
    print(f"[parse_problem] GPT-4o Vision OCR 중...")
    client = get_openai_client()

    if _is_url(image_source):
        # URL 이미지
        content = [
            {"type": "image_url", "image_url": {"url": image_source}},
            {"type": "text", "text": "이 이미지에서 시험 문제 텍스트를 정확하게 추출하세요."},
        ]
    elif _is_image_path(image_source) and os.path.exists(image_source):
        # 로컬 파일 → base64 인코딩
        with open(image_source, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        ext = os.path.splitext(image_source)[1].lstrip(".").replace("jpg", "jpeg")
        content = [
            {"type": "image_url", "image_url": {"url": f"data:image/{ext};base64,{b64}"}},
            {"type": "text", "text": "이 이미지에서 시험 문제 텍스트를 정확하게 추출하세요."},
        ]
    else:
        return image_source  # 파싱 불가 → 원본 반환

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": PARSE_SYSTEM},
            {"role": "user",   "content": content},
        ],
        max_tokens=1024,
    )
    return response.choices[0].message.content or image_source


def parse_problem(state: GradingState) -> dict:
    """
    문제 텍스트화.
    - 일반 텍스트: 그대로 통과
    - 이미지 URL / 파일 경로: GPT-4o Vision OCR
    """
    problem = state["problem"]
    question = problem.question.strip()

    if not question:
        print("[parse_problem] 빈 문제 — 스킵")
        return {"problem": problem}

    # 이미지 소스인지 확인
    if _is_url(question) or _is_image_path(question):
        parsed_text = _parse_image(question)
        problem = problem.model_copy(update={"question": parsed_text})
        print(f"[parse_problem] Vision 파싱 완료: {parsed_text[:60]}...")
    else:
        print(f"[parse_problem] 텍스트 입력 — 파싱 스킵")

    return {"problem": problem}

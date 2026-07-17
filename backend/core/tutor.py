import os
from openai import OpenAI
from .grading import grade_answer
from .mcq import resolve_mcq_answer

_client = None
_PLACEHOLDER_PREFIX = "sk-여기에"


def _get_client():
    global _client
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key or api_key.startswith(_PLACEHOLDER_PREFIX):
        return None
    if _client is None:
        _client = OpenAI(api_key=api_key)
    return _client


def _meta(model, prompt=None, response=None, usage=None):
    """관리자 페이지의 토큰 집계/대화 로그용 호출 메타데이터."""
    return {
        "model": model,
        "prompt": prompt,
        "response": response,
        "prompt_tokens": getattr(usage, "prompt_tokens", 0) if usage else 0,
        "completion_tokens": getattr(usage, "completion_tokens", 0) if usage else 0,
    }


def grade_with_ai(question_text, user_answer, answer_text):
    """returns (is_correct, meta)"""
    resolved_answer = resolve_mcq_answer(question_text, user_answer)

    client = _get_client()
    if client is None or not str(resolved_answer or "").strip():
        result = grade_answer(resolved_answer, answer_text)
        return result, _meta("fallback", response="CORRECT" if result else "INCORRECT")

    prompt = (
        f"문제: {question_text or '(문제 텍스트 없음)'}\n"
        f"정답/풀이: {answer_text}\n"
        f"학생 답안: {resolved_answer}\n\n"
        f"학생 답안이 이 문제의 정답과 수학적으로 같은 의미인지 판단하세요. "
        f"표기 방식(분수/소수, 기호 순서, 공백, 단위 표기 등)이 달라도 값이 같으면 정답으로 인정하세요. "
        f"반드시 CORRECT 또는 INCORRECT 한 단어로만 답하세요."
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "당신은 수학 답안 채점자입니다. CORRECT 또는 INCORRECT로만 답합니다."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=5,
        )
        verdict = resp.choices[0].message.content.strip().upper()
        return verdict.startswith("CORRECT"), _meta("gpt-4o-mini", prompt, verdict, resp.usage)
    except Exception:
        result = grade_answer(resolved_answer, answer_text)
        return result, _meta("fallback", prompt, "CORRECT" if result else "INCORRECT")


def _fallback_explanation(answer_text, mastery_score):
    if mastery_score < 0.4:
        level = "초보자"
    elif mastery_score < 0.7:
        level = "중급자"
    else:
        level = "고급자"
    return f"[{level} 맞춤 설명]\n이 문제의 정답과 풀이는 다음과 같습니다:\n{answer_text}"


def explain_solution(answer_text, mastery_score, question_text=None):
    """returns (explanation, meta)"""
    client = _get_client()
    if client is None:
        text = _fallback_explanation(answer_text, mastery_score)
        return text, _meta("fallback", response=text)

    if mastery_score < 0.4:
        level_desc = "수학을 어려워하는 초보자입니다. 아주 쉬운 말과 비유를 사용해서 단계 하나하나를 자세히 설명해주세요."
    elif mastery_score < 0.7:
        level_desc = "기본기는 있는 중급자입니다. 핵심 개념과 풀이 흐름 위주로 설명해주세요."
    else:
        level_desc = "실력이 좋은 고급자입니다. 핵심 포인트만 간결하게 짚어주세요."

    prompt = (
        f"학생이 다음 수학 문제를 틀렸습니다.\n"
        f"문제: {question_text or '(문제 텍스트 없음)'}\n"
        f"정답/풀이: {answer_text}\n\n"
        f"학생은 {level_desc}\n"
        f"학생의 눈높이에 맞춰 이 문제를 다시 설명해주세요. 친근한 말투를 쓰고, 300자 이내로 작성해주세요."
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "당신은 친절한 수학 과외 선생님 '수달이'입니다."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.5,
            max_tokens=500,
        )
        text = resp.choices[0].message.content.strip()
        return text, _meta("gpt-4o-mini", prompt, text, resp.usage)
    except Exception:
        text = _fallback_explanation(answer_text, mastery_score)
        return text, _meta("fallback", prompt, text)


def _fallback_hints(answer_text):
    if not answer_text:
        answer_text = "정답 정보가 없습니다."
    preview_len = min(10, len(answer_text))
    return [
        "1단계 힌트: 문제의 요구사항을 다시 한 번 파악해보세요.",
        "2단계 힌트: 문제에 주어진 조건과 관련 공식을 떠올려보세요.",
        f"3단계 힌트: 정답에 가까워지는 단서입니다. ({answer_text[:preview_len]}...)",
    ]


def generate_hints(answer_text, question_text=None):
    """returns (hints, meta)"""
    client = _get_client()
    if client is None:
        hints = _fallback_hints(answer_text)
        return hints, _meta("fallback", response="\n".join(hints))

    prompt = (
        f"다음 수학 문제의 힌트를 정확히 3단계로 만들어주세요. 정답을 직접 말하지 말고 점점 더 구체적으로 힌트를 주세요.\n"
        f"문제: {question_text or '(문제 텍스트 없음)'}\n"
        f"정답/풀이(참고용, 학생에게 그대로 노출 금지): {answer_text}\n\n"
        f"정확히 3줄로, 번호나 기호 없이 힌트 문장만 한 줄씩 출력하세요. "
        f"1번째 줄은 가장 추상적인 힌트, 3번째 줄은 정답에 가장 가까운 힌트여야 합니다."
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "당신은 친절한 수학 과외 선생님 '수달이'입니다. 힌트만 주고 정답은 알려주지 않습니다."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.6,
            max_tokens=300,
        )
        raw = resp.choices[0].message.content.strip()
        lines = [l.strip("-•0123456789. ").strip() for l in raw.split("\n") if l.strip()]
        if len(lines) < 3:
            hints = _fallback_hints(answer_text)
            return hints, _meta("gpt-4o-mini", prompt, raw, resp.usage)
        hints = [f"{i + 1}단계 힌트: {line}" for i, line in enumerate(lines[:3])]
        return hints, _meta("gpt-4o-mini", prompt, raw, resp.usage)
    except Exception:
        hints = _fallback_hints(answer_text)
        return hints, _meta("fallback", prompt, "\n".join(hints))

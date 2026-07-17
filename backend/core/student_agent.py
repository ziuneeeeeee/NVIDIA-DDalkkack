"""LLM 학생 에이전트.

확률 시뮬레이터와 달리 문제 텍스트를 실제로 읽고, 페르소나(실력 수준)에 맞는
풀이 행동으로 답안 텍스트를 생성한다. 생성된 답안은 실제 채점 파이프라인
(grade_with_ai)을 그대로 통과하므로 채점기 품질까지 함께 검증된다.

틀린 뒤 받은 해설은 memory에 쌓여 다음 답변 프롬프트에 포함된다 — 에이전트가
"배운 내용을 다음 풀이에 반영"하는 학습 루프.
"""
from .tutor import _get_client, _meta
from .mcq import extract_mcq_options


def persona_description(ability: float) -> str:
    if ability < 0.4:
        return (
            "수학을 어려워하는 하위권 학생입니다. 개념 이해가 얕고 계산 실수(특히 부호 실수)가 잦습니다. "
            "기초 문제는 풀 수 있지만 두 단계 이상 계산이 필요한 문제는 대부분 틀립니다."
        )
    if ability < 0.7:
        return (
            "기본기는 있는 중위권 학생입니다. 표준적인 문제는 대체로 풀지만 "
            "응용 문제나 여러 단계 계산에서 종종 실수합니다."
        )
    return (
        "실력이 좋은 상위권 학생입니다. 대부분의 문제를 정확히 풀지만 "
        "아주 어려운 문제나 함정이 있는 문제에서 가끔 실수합니다."
    )


def is_available() -> bool:
    return _get_client() is not None


def answer_question(question: dict, ability: float, memory: list[str] | None = None):
    """returns (answer_text, meta). LLM을 쓸 수 없으면 (None, None)."""
    client = _get_client()
    if client is None:
        return None, None

    qtext = question.get('question_text') or ''
    options = extract_mcq_options(qtext)
    guide = (
        "객관식 문제입니다. 최종 답으로 보기 번호 숫자 하나만 출력하세요."
        if options else
        "최종 답만 짧게 출력하세요. 풀이 과정은 출력하지 마세요."
    )

    memo = ""
    if memory:
        memo = "\n\n최근에 선생님께 배운 내용(다음 풀이에 참고):\n" + "\n".join(f"- {m}" for m in memory[-5:])

    prompt = (
        f"[학생 특성] {persona_description(ability)}{memo}\n\n"
        f"다음 수학 문제를 위 학생이 직접 푼다고 생각하고, 그 학생이 실제로 제출할 답을 작성하세요. "
        f"학생 수준에서 틀릴 만한 문제라면, 그 학생이 저지를 법한 실수가 반영된 오답을 제출하세요. "
        f"학생 수준에서 충분히 풀 수 있는 문제라면 정확한 답을 제출하세요.\n\n"
        f"문제: {qtext}\n\n{guide}"
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "당신은 주어진 특성의 학생을 연기하는 시뮬레이터입니다. 학생이 제출할 최종 답만 출력합니다."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=60,
        )
        ans = resp.choices[0].message.content.strip()
        return ans, _meta("gpt-4o-mini", prompt, ans, resp.usage)
    except Exception:
        return None, None

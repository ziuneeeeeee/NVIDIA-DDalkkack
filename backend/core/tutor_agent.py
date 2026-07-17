"""적응형 학습의 '다음에 뭘 줄까' 결정을, 규칙 대신 LLM 에이전트가 내리게 한다.

기존 adaptive.next_difficulty()는 정답/오답만 보고 ±1(가속 시 ±2)로 난이도를
움직이는 맹목적 규칙이다. 이 에이전트는 그 규칙에 더해:
  - 학생의 개념별 이해도 전체(취약한 순)
  - 최근 풀이 이력(어떤 개념을, 어떤 난이도로, 맞았는지)
  - 지금 개념에서의 연속 정답/오답, 힌트 사용 여부
까지 보고 다음 난이도와, 필요하면 다른(관련된 더 취약한) 개념으로의 전환까지
판단한다. LLM을 못 쓰거나 실패하면 규칙 기반으로 조용히 폴백한다 — 이 프로젝트의
다른 LLM 기능(채점/해설/힌트)과 동일한 패턴.
"""
import json

from .tutor import _get_client, _meta
from .adaptive import AdaptiveLearning

_rule_based = AdaptiveLearning()


def _format_profile(topic_report):
    if not topic_report:
        return "(아직 다른 개념 기록 없음)"
    lines = []
    for r in sorted(topic_report, key=lambda x: x['mastery'])[:8]:
        lines.append(
            f"- {r['topic_key']} (분류: {r.get('sector2') or r.get('sector1') or '?'}): "
            f"이해도 {round(r['mastery'] * 100)}%, 시도 {r['attempt_count']}회"
        )
    return "\n".join(lines)


def _format_recent(recent_attempts):
    if not recent_attempts:
        return "(최근 풀이 기록 없음)"
    lines = []
    for a in recent_attempts:
        mark = "O" if a['is_correct'] else "X"
        hint = " (힌트 사용)" if a['hint_used'] else ""
        lines.append(f"- {a['topic_key']} 난이도{a['difficulty']} {mark}{hint}")
    return "\n".join(lines)


def next_difficulty_fallback(current_difficulty, is_correct, streak):
    return _rule_based.next_difficulty(current_difficulty, is_correct, streak=streak)


def decide_next(question, is_correct, current_difficulty, streak,
                 topic_report, recent_attempts, hint_used):
    """returns (decision, meta).

    decision: {"next_difficulty": int, "next_topic": str|None, "reasoning": str} 또는
    None (LLM을 못 썼거나 실패 - 호출자가 규칙 기반으로 폴백해야 함).
    """
    client = _get_client()
    if client is None:
        return None, None

    topic = question.get('topic_name') or question.get('sector2') or '기타'
    prompt = (
        f"당신은 중고등학생 수학 학습을 돕는 AI 튜터입니다. 방금 학생이 문제를 풀었고, "
        f"다음 문제를 어떤 난이도·개념으로 줄지 결정해야 합니다.\n\n"
        f"[방금 푼 문제] 개념: {topic}, 난이도: {question.get('difficulty')}, "
        f"결과: {'정답' if is_correct else '오답'}{'(힌트 사용함)' if hint_used else ''}\n"
        f"[이 개념에서의 연속 기록] {streak} (양수=연속 정답 횟수, 음수=연속 오답 횟수)\n\n"
        f"[이 학생의 개념별 이해도, 낮은 순]\n{_format_profile(topic_report)}\n\n"
        f"[최근 풀이 이력, 최신순]\n{_format_recent(recent_attempts)}\n\n"
        f"판단 기준:\n"
        f"- 연속 정답이 이어지면 난이도를 올리고 연속 오답이면 낮추세요 (1~5 범위 정수).\n"
        f"- 같은 개념에서 2번 이상 연속으로 틀렸다면, 그 개념을 계속 붙잡기보다 위 목록에서 "
        f"관련되고(같은 분류) 더 취약한 다른 개념으로 잠깐 돌리는 것도 고려하세요. "
        f"이런 경우가 아니면 next_topic은 반드시 null로 두고 원래 개념을 유지하세요.\n"
        f"- reasoning은 학생에게 보여줄 한국어 한 문장으로, 20자 이내로 아주 짧게 쓰세요.\n\n"
        f'다음 JSON 형식으로만 답하세요: '
        f'{{"next_difficulty": 1~5 사이 정수, "next_topic": "개념명 또는 null", "reasoning": "짧은 이유"}}'
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "당신은 학생 맞춤형 학습 경로를 설계하는 AI 튜터 에이전트입니다. 반드시 JSON만 출력합니다."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=150,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content.strip()
        parsed = json.loads(raw)

        difficulty = int(parsed.get("next_difficulty", current_difficulty))
        difficulty = max(1, min(5, difficulty))

        next_topic = parsed.get("next_topic")
        if not next_topic or str(next_topic).lower() == "null" or next_topic == topic:
            next_topic = None

        # 위 개념 목록에 실제로 없는 이름을 지어내면(환각) 검색이 아예 안 걸리니 무시한다.
        if next_topic and topic_report and next_topic not in {r['topic_key'] for r in topic_report}:
            next_topic = None

        reasoning = str(parsed.get("reasoning") or "").strip()[:60]

        decision = {"next_difficulty": difficulty, "next_topic": next_topic, "reasoning": reasoning}
        return decision, _meta("gpt-4o-mini", prompt, raw, resp.usage)
    except Exception:
        return None, None

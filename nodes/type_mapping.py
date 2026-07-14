"""
type_mapping.py
──────────────
[팀원 1: 개념 추출] -> [팀원 2: 유형/난이도 매핑] -> [팀원 3/4: 문제/루브릭 생성]
파이프라인에서 팀원 2 담당 단계.

concept_bank.json (팀원 1 산출물)을 입력받아, 각 개념에
  - mapped_category: CALCULATION / MULTIPLE_CHOICE / TRUE_FALSE / DESCRIPTIVE
  - difficulty: 쉬움 / 보통 / 어려움
을 매핑하고 mapped_concepts.json 형태로 반환한다.

설계 방식 (팀 회의 피드백 반영):
  - 유형/난이도 모두 "비율 고정" 없이, 개념 하나하나의 내용 특성에 가장
    적합한 값을 그대로 채택한다 (LLM이 매긴 적합도 점수 중 최고점).
  - 문제 총 개수는 min(핵심개념 수, 20). 핵심개념이 20개를 넘으면
    '핵심도(importance_score)' 상위 20개만 선택하고, 20개 이하면 있는
    만큼 전부 사용한다 (억지로 20개를 채우지 않음).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

from core.clients import get_openai_client

MODEL = "gpt-4o"

MappedCategory = Literal["CALCULATION", "MULTIPLE_CHOICE", "TRUE_FALSE", "DESCRIPTIVE"]
Difficulty = Literal["쉬움", "보통", "어려움"]

MAX_TOTAL = 20             # 시험 문제 상한. 핵심개념이 이보다 적으면 있는 만큼만 사용.
CONFIDENCE_MARGIN = 15      # 1순위-2순위 점수 차가 이 미만이면 confidence="low"

# 한 번의 LLM 호출로 채점하기에 안전한 최대 개념 수 (컨텍스트/출력 신뢰도 확보용)
CHUNK_SIZE = 25

SCORING_SYSTEM_PROMPT = """\
너는 교육용 문제 매핑 전문가이다. 각 개념의 '정보 구성 특징'을 분석하여,
아래 4개 문제 유형과 3개 난이도 각각에 그 개념이 얼마나 적합한지, 그리고
이 개념이 시험에 출제될 만큼 핵심적인지 0~100점으로 점수를 매겨라.
최종 유형/난이도는 네가 매긴 점수 중 가장 높은 것으로 그대로 채택되므로,
비율을 맞추려 하지 말고 오직 '이 개념 하나에만' 가장 적합한 게 무엇인지
정확하게 판단하라.

# [문제 유형 점수 기준]
- calculation_score: 구체적인 수치, 공식, 변수(예: ms, Burst Time 등), 예시 데이터
  표(Table)가 텍스트에 실제로 있을 때만 높게. 계산할 근거가 텍스트에 없다면
  반드시 낮은 점수(20 이하)를 줘라. calc_eligible이 false이면 이 문제는 계산형으로
  절대 출제될 수 없다는 뜻이니 신중하게 판단하라.
- multiple_choice_score: 하나의 주제 아래 여러 특징/종류가 나열되어 비교 대조가
  가능할 때 높게.
- true_false_score: 텍스트가 2~3줄 이하로 짧고 단순 정의·사실 전달 위주일 때 높게.
- descriptive_score: 인과관계 설명이 필요하거나 여러 메커니즘이 순차적으로
  맞물려 일어나는 복잡한 작동 이론일 때 높게.

# [난이도 점수 기준]
- easy_score: 강의자료의 핵심 키워드·정의를 정확히 기억하고 있는지만 확인하면
  되는 단순한 개념일 때 높게.
- medium_score: 이론의 메커니즘이나 인과관계를 이해하고 적용할 수 있는지
  평가해야 하는 개념일 때 높게.
- hard_score: 여러 개념을 복합적으로 활용해야 하거나 예외 상황을 해결해야
  하는, 변별력이 필요한 개념일 때 높게.

# [핵심도 점수 기준]
- importance_score: 이 개념이 강의의 핵심 주제를 대표하는지, 시험에 출제될
  만큼 중요한지, 다른 개념을 이해하기 위한 전제가 되는지를 고려해 평가하라.
  지엽적이거나 부가적인 설명일수록 낮게 줘라.

모든 reasoning 텍스트(mapping_reason, difficulty_reason)는 반드시 한국어로 작성하라.
입력으로 주어진 모든 concept_id에 대해 빠짐없이 점수를 반환하라.
"""


class ConceptScore(BaseModel):
    concept_id: str
    calc_eligible: bool
    calculation_score: int
    multiple_choice_score: int
    true_false_score: int
    descriptive_score: int
    mapping_reason: str
    easy_score: int
    medium_score: int
    hard_score: int
    difficulty_reason: str
    importance_score: int


class BatchScoreResult(BaseModel):
    scores: list[ConceptScore]


def _build_user_prompt(concepts: list[dict]) -> str:
    lines = [f"개념 총 {len(concepts)}개. 각각에 점수를 매겨라.\n"]
    for c in concepts:
        lines.append(
            f"- concept_id: {c['concept_id']}\n"
            f"  concept_name: {c['concept_name']}\n"
            f"  concept_summary: {c.get('concept_summary', '')}\n"
            f"  source_context: {c.get('source_context', '')}\n"
        )
    return "\n".join(lines)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=20))
def _score_chunk(chunk: list[dict]) -> list[ConceptScore]:
    """API 호출 실패(rate limit, 타임아웃 등) 시 최대 3회, 지수 백오프로 재시도한다."""
    client = get_openai_client()
    response = client.beta.chat.completions.parse(
        model=MODEL,
        messages=[
            {"role": "system", "content": SCORING_SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(chunk)},
        ],
        response_format=BatchScoreResult,
    )
    return response.choices[0].message.parsed.scores


def _score_all_concepts(concepts: list[dict]) -> dict[str, ConceptScore]:
    """개념이 많을 경우 CHUNK_SIZE 단위로 나눠 여러 번 호출해 컨텍스트/출력
    신뢰도 문제를 피한다."""
    scores: dict[str, ConceptScore] = {}
    for i in range(0, len(concepts), CHUNK_SIZE):
        chunk = concepts[i:i + CHUNK_SIZE]
        for s in _score_chunk(chunk):
            scores[s.concept_id] = s

    missing = [c["concept_id"] for c in concepts if c["concept_id"] not in scores]
    if missing:
        raise ValueError(f"LLM이 다음 concept_id에 대한 점수를 반환하지 않았습니다: {missing}")
    return scores


REQUIRED_CONCEPT_FIELDS = ("concept_id", "concept_name")


def _validate_concepts(concepts: list[dict]) -> None:
    """팀원 1 산출물(concept_bank.json)이 필수 필드를 갖췄고 concept_id가
    중복되지 않는지 먼저 검증한다. 여기서 걸러야 이후 단계에서 애매한
    KeyError 대신 어떤 개념이 문제인지 바로 알 수 있다."""
    seen_ids: set[str] = set()
    for i, c in enumerate(concepts):
        missing = [f for f in REQUIRED_CONCEPT_FIELDS if not c.get(f)]
        if missing:
            raise ValueError(f"concept_bank[{i}]에 필수 필드가 없습니다: {missing} (concept={c!r})")
        cid = c["concept_id"]
        if cid in seen_ids:
            raise ValueError(f"concept_id가 중복되었습니다: '{cid}'")
        seen_ids.add(cid)


# ── 순수 함수 (LLM 호출 없음 -> 테스트 용이) ──────────────────────

def select_concepts(
    concepts: list[dict],
    scores: dict[str, ConceptScore],
    max_total: int = MAX_TOTAL,
) -> list[dict]:
    """핵심개념이 max_total개를 넘으면 importance_score 상위 max_total개만
    선택한다. max_total 이하면 전부 그대로 사용한다 (원래 순서 유지)."""
    if len(concepts) <= max_total:
        return list(concepts)
    top_ids = {
        c["concept_id"]
        for c in sorted(concepts, key=lambda c: scores[c["concept_id"]].importance_score, reverse=True)[:max_total]
    }
    return [c for c in concepts if c["concept_id"] in top_ids]


def pick_category(score: ConceptScore) -> tuple[MappedCategory, MappedCategory, str]:
    """4개 유형 중 점수가 가장 높은 것을 채택한다. calc_eligible이 False면
    계산형은 원천적으로 후보에서 제외(0점 처리)한다.
    반환값: (채택된 유형, 2순위 유형, confidence)"""
    candidate_scores: dict[MappedCategory, int] = {
        "MULTIPLE_CHOICE": score.multiple_choice_score,
        "TRUE_FALSE": score.true_false_score,
        "DESCRIPTIVE": score.descriptive_score,
        "CALCULATION": score.calculation_score if score.calc_eligible else 0,
    }
    ranked = sorted(candidate_scores.items(), key=lambda kv: kv[1], reverse=True)
    best_label, best_score = ranked[0]
    runner_up_label, runner_up_score = ranked[1]
    confidence = "high" if (best_score - runner_up_score) >= CONFIDENCE_MARGIN else "low"
    return best_label, runner_up_label, confidence


def pick_difficulty(score: ConceptScore) -> Difficulty:
    """3개 난이도 중 점수가 가장 높은 것을 채택한다."""
    candidate_scores: dict[Difficulty, int] = {
        "쉬움": score.easy_score,
        "보통": score.medium_score,
        "어려움": score.hard_score,
    }
    return max(candidate_scores, key=lambda k: candidate_scores[k])


def map_concepts_to_types(concepts: list[dict], max_total: int = MAX_TOTAL) -> list[dict]:
    """concept_bank.json의 개념 리스트를 받아 mapped_category/difficulty가
    추가된 mapped_concepts 리스트를 반환한다. (팀원 3/4에게 그대로 전달되는 포맷)

    - 비율 고정 없음: 유형/난이도 모두 개념별로 가장 적합한 값을 그대로 채택.
    - 총 개수는 min(len(concepts), max_total). max_total(기본 20)을 넘으면
      핵심도(importance_score) 상위 max_total개만 선택한다.
    """
    if not concepts:
        return []

    _validate_concepts(concepts)
    scores = _score_all_concepts(concepts)
    selected = select_concepts(concepts, scores, max_total)

    mapped_concepts = []
    for c in selected:
        s = scores[c["concept_id"]]
        category, runner_up_category, confidence = pick_category(s)
        difficulty = pick_difficulty(s)

        entry = {
            **c,
            "mapped_category": category,
            "mapping_reason": s.mapping_reason,
            "confidence": confidence,
            "difficulty": difficulty,
            "difficulty_reason": s.difficulty_reason,
            "importance_score": s.importance_score,
        }
        if confidence == "low":
            entry["runner_up_category"] = runner_up_category
        mapped_concepts.append(entry)

    return mapped_concepts

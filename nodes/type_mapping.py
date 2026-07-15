"""
type_mapping.py
──────────────
[팀원 1: 핵심개념 추출·선별] -> [팀원 2: 문제유형 매핑] -> [팀원 3/4: 문제/루브릭 생성]
파이프라인에서 팀원 2 담당 단계.

concept_bank.json (팀원 1 산출물)을 입력받아, 각 개념에
  - mapped_category: CALCULATION / MULTIPLE_CHOICE / TRUE_FALSE / DESCRIPTIVE
를 매핑하고 mapped_concepts.json 형태로 반환한다.

역할 분담 (팀 회의 확정):
  - 핵심개념 선별(중요도 판단, 최대 20개 제한)은 팀원 1이 담당한다.
    팀원 1이 넘겨주는 concept_bank.json은 이미 출제할 개념만 담겨 있으므로,
    팀원 2는 여기서 개수를 다시 자르거나 순위를 매기지 않고 주어진
    개념을 있는 그대로 전부 매핑한다.
  - 난이도 판정은 팀원 2의 책임 범위가 아니다 (다루지 않음).
  - 유형은 비율을 고정하지 않고, 개념 하나하나의 내용 특성에 가장 적합한
    값을 그대로 채택한다 (LLM이 매긴 적합도 점수 중 최고점).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

from core.clients import get_openai_client

MODEL = "gpt-4o"

MappedCategory = Literal["CALCULATION", "MULTIPLE_CHOICE", "TRUE_FALSE", "DESCRIPTIVE"]

CONFIDENCE_MARGIN = 15      # 1순위-2순위 점수 차가 이 미만이면 confidence="low"

# 한 번의 LLM 호출로 채점하기에 안전한 최대 개념 수 (컨텍스트/출력 신뢰도 확보용)
CHUNK_SIZE = 25

SCORING_SYSTEM_PROMPT = """\
너는 교육용 문제 매핑 전문가이다. 각 개념의 '정보 구성 특징'을 분석하여,
아래 4개 문제 유형 각각에 그 개념이 얼마나 적합한지 0~100점으로 점수를
매겨라. 최종 유형은 네가 매긴 점수 중 가장 높은 것으로 그대로 채택되므로,
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

모든 reasoning 텍스트(mapping_reason)는 반드시 한국어로 작성하라.
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


class BatchScoreResult(BaseModel):
    scores: list[ConceptScore]


def _build_user_prompt(concepts: list[dict]) -> str:
    lines = [f"개념 총 {len(concepts)}개. 각각에 점수를 매겨라.\n"]
    for c in concepts:
        line = (
            f"- concept_id: {c['concept_id']}\n"
            f"  concept_name: {c['concept_name']}\n"
            f"  concept_summary: {c.get('concept_summary', '')}\n"
            f"  source_context: {c.get('source_context', '')}\n"
        )
        # 확장 필드(팀원1 산출물에 있으면 분류 근거로 함께 활용, 없으면 생략)
        if c.get("key_facts"):
            line += f"  key_facts: {'; '.join(c['key_facts'])}\n"
        if c.get("learning_objectives"):
            line += f"  learning_objectives: {'; '.join(c['learning_objectives'])}\n"
        lines.append(line)
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


def pick_category(score: ConceptScore) -> tuple[MappedCategory, MappedCategory, str]:
    """4개 유형 중 점수가 가장 높은 것을 채택한다 (LLM 호출 없는 순수 함수 ->
    테스트 용이). calc_eligible이 False면 계산형은 원천적으로 후보에서
    제외(0점 처리)한다.
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


def map_concepts_to_types(concepts: list[dict]) -> list[dict]:
    """concept_bank.json의 개념 리스트를 받아 mapped_category가 추가된
    mapped_concepts 리스트를 반환한다. (팀원 3/4에게 그대로 전달되는 포맷)

    팀원 1이 이미 출제 대상(최대 20개)을 선별해 넘겨준다는 전제이므로,
    여기서는 개수를 자르거나 순위를 매기지 않고 주어진 개념을 전부 매핑한다.
    유형 비율도 고정하지 않고, 개념별로 가장 적합한 값을 그대로 채택한다.
    """
    if not concepts:
        return []

    _validate_concepts(concepts)
    scores = _score_all_concepts(concepts)

    mapped_concepts = []
    for c in concepts:
        s = scores[c["concept_id"]]
        category, runner_up_category, confidence = pick_category(s)

        entry = {
            **c,
            "mapped_category": category,
            "mapping_reason": s.mapping_reason,
            "confidence": confidence,
        }
        if confidence == "low":
            entry["runner_up_category"] = runner_up_category
        mapped_concepts.append(entry)

    return mapped_concepts

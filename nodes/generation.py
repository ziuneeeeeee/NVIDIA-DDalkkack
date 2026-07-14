import json
import uuid
from typing import Literal
from pydantic import BaseModel
from core.state import GenerationState
from core.models import Problem
from core.clients import get_openai_client

MODEL = "gpt-4o"

class DraftProblem(BaseModel):
    type: Literal["참거짓", "객관식", "단답형", "서술형", "코딩형"]
    question: str
    answer: str | None = None
    model_answer: str | None = None

class TypeClassification(BaseModel):
    question_type: Literal["참거짓", "객관식", "단답형", "서술형", "코딩형"]
    reasoning: str

class VerificationResult(BaseModel):
    is_valid: bool
    feedback: str

class DifficultyResult(BaseModel):
    estimated_difficulty: Literal["하", "중", "상"]
    feedback: str

class ConclusionResult(BaseModel):
    is_accepted: bool
    final_feedback: str

TYPE_MAPPING_GUIDE = """
[참거짓] 대상: 단일 정의, 명확한 수치, 절대적인 인과관계, 포함 관계가 뚜렷한 개념.
예: OS의 '인터럽트 정의', 네트워크의 'OSI 7계층 각각의 명칭'.

[객관식] (4지선다) 대상: 하나의 대주제 아래에 여러 개의 하위 종류나 특징이 나열되는 개념
(비교/대조군이 확실한 것).
예: CPU 스케줄링 알고리즘들의 장단점 비교, 데이터베이스 인덱스의 종류별 특징.

[서술형] (단답/주관식) 대상: 메커니즘의 작동 과정 기술, 예외 상황에 대한 대처법,
특정 설계 조건을 만족해야 하는 복합 이론.
예: 데드락(Deadlock)의 4가지 발생 조건과 해결 방안 서술.

[코딩형] 위 세 기준에 해당하지 않고, 개념이 코드 작성/구현을 직접 요구할 때만 선택.
[단답형] 서술형과 대상은 유사하나 한두 단어/짧은 문장으로 답이 확정되는 경우에 선택.
"""

def classify_question_type_node(state: GenerationState) -> dict:
    """강의자료에서 추출된 개념을 위 매핑 가이드라인에 따라 문제 유형으로 분류한다."""
    client = get_openai_client()
    prompt = f"""
개념: {state['concept']}

강의자료 내용 (Context):
{state['context']}

아래 분류 기준에 따라 이 개념에 가장 적합한 문제 유형을 하나만 선택하세요.
{TYPE_MAPPING_GUIDE}
위 개념이 어느 유형에 가장 부합하는지 판단하고, 판단 근거를 간단히 설명하세요.
"""
    print(f"\n[Type Classification AI] '{state['concept']}' 개념 유형 분류 중...")
    response = client.beta.chat.completions.parse(
        model=MODEL,
        messages=[
            {"role": "system", "content": "당신은 개념을 시험 문제 유형으로 분류하는 출제 설계 전문가입니다."},
            {"role": "user", "content": prompt}
        ],
        response_format=TypeClassification,
    )
    res = response.choices[0].message.parsed
    print(f"  -> {res.question_type} ({res.reasoning})")
    return {"question_type": res.question_type}

def generate_problem_node(state: GenerationState) -> dict:
    client = get_openai_client()
    question_type = state.get("question_type") or "객관식"
    prompt = f"""
강의자료 내용 (Context):
{state['context']}

위 강의자료를 바탕으로 '{state['concept']}' 개념에 대한 문제를 하나 생성하세요.
목표 난이도는 '{state['target_difficulty']}' 입니다.
문제 유형은 반드시 '{question_type}'이어야 합니다. (참거짓/객관식/단답형/서술형/코딩형 중 다른 유형으로 바꾸지 마세요.)
모든 문제는 **10점 만점**을 기준으로 출제되며, 문제 끝에 "(10점)"을 표기해 주세요.
참거짓/객관식/단답형인 경우 'answer' 필드에 정답을 반드시 기입하고, 서술형이나 코딩형인 경우 'model_answer' 필드에 모범 답안을 작성하세요.
참거짓 유형은 'answer' 필드에 "참" 또는 "거짓"만 기입하세요.
만약 이전 피드백이 있다면, 피드백을 반영하여 수정하세요.
이전 검증 피드백 이력:
{chr(10).join(state.get('validation_history', [])) or '없음'}

이전 난이도 피드백 이력:
{chr(10).join(state.get('difficulty_history', [])) or '없음'}

위 이력에서 지적된 문제를 모두 피해서 새로 작성하세요. 이전과 동일한 실수를 반복하지 마세요.
"""
    print(f"\n[Generation AI] '{state['concept']}' 개념 문제 초안 생성 중... (유형: {question_type})")
    response = client.beta.chat.completions.parse(
        model=MODEL,
        messages=[
            {"role": "system", "content": "당신은 우수한 시험 출제자입니다."},
            {"role": "user", "content": prompt}
        ],
        response_format=DraftProblem,
    )
    draft = response.choices[0].message.parsed
    draft_dict = draft.model_dump()
    draft_dict["type"] = question_type   # 분류 노드 판정을 최종 근거로 고정
    return {"draft_problem": draft_dict, "retry_count": state.get("retry_count", 0) + 1}

def verify_problem_node(state: GenerationState) -> dict:
    client = get_openai_client()
    draft = state["draft_problem"]
    prompt = f"""
강의자료 내용 (Context):
{state['context']}

생성된 문제 초안:
{json.dumps(draft, ensure_ascii=False, indent=2)}

생성된 문제가 강의자료의 내용과 사실적으로 일치하는지, 그리고 명확하게 출제되었는지 검증하세요.
"""
    print("[Verification AI] 문제 내용 검증 중...")
    response = client.beta.chat.completions.parse(
        model=MODEL,
        messages=[
            {"role": "system", "content": "당신은 엄격한 문제 검수자입니다."},
            {"role": "user", "content": prompt}
        ],
        response_format=VerificationResult,
    )
    res = response.choices[0].message.parsed
    feedback_str = ("✅ 통과: " if res.is_valid else "❌ 반려: ") + res.feedback
    print(f"  -> {feedback_str}")
    return {"validation_history": state.get("validation_history", []) + [feedback_str]}

def judge_difficulty_node(state: GenerationState) -> dict:
    client = get_openai_client()
    draft = state["draft_problem"]
    prompt = f"""
생성된 문제 초안:
{json.dumps(draft, ensure_ascii=False, indent=2)}

목표 난이도는 '{state['target_difficulty']}' 입니다.
현재 문제의 체감 난이도를 '하', '중', '상' 중 하나로 평가하고 이유를 설명하세요.
"""
    print("[Difficulty AI] 문제 난이도 측정 중...")
    response = client.beta.chat.completions.parse(
        model=MODEL,
        messages=[
            {"role": "system", "content": "당신은 난이도 조절 전문가입니다."},
            {"role": "user", "content": prompt}
        ],
        response_format=DifficultyResult,
    )
    res = response.choices[0].message.parsed
    feedback_str = f"측정된 난이도: {res.estimated_difficulty}. {res.feedback}"
    print(f"  -> {feedback_str}")
    return {"difficulty_history": state.get("difficulty_history", []) + [feedback_str]}

def conclude_problem_node(state: GenerationState) -> dict:
    target_diff = state["target_difficulty"]
    validation = state["validation_history"][-1]   # 최신 피드백
    difficulty = state["difficulty_history"][-1]

    client = get_openai_client()
    prompt = f"""
강의자료 원문 (Context):
{state['context']}

생성된 문제:
{json.dumps(state['draft_problem'], ensure_ascii=False, indent=2)}

목표 난이도: {target_diff}
검증 AI 피드백: {validation}
난이도 AI 평가: {difficulty}

당신은 위 두 AI의 판정에만 의존하지 말고, 강의자료 원문과 문제를 직접 대조하여
사실관계 오류가 있는지도 스스로 확인한 뒤 최종 판정하세요.
문제가 오류 없이 명확하며, 측정된 난이도가 목표 난이도와 일치하면 승인(is_accepted=True) 하세요.
"""
    print("[Conclusion AI] 최종 판정 중...")
    response = client.beta.chat.completions.parse(
        model=MODEL,
        messages=[
            {"role": "system", "content": "당신은 최종 결정권자입니다."},
            {"role": "user", "content": prompt}
        ],
        response_format=ConclusionResult,
    )
    res = response.choices[0].message.parsed

    print(f"  -> 최종 결과: {'승인 ✅' if res.is_accepted else '반려 🔄'} ({res.final_feedback})")

    if res.is_accepted:
        draft = state["draft_problem"]
        problem = Problem(
            problem_id=f"gen_{uuid.uuid4().hex[:8]}",
            type=draft["type"],
            question=draft["question"],
            answer=draft.get("answer"),
            model_answer=draft.get("model_answer"),
        )
        return {"is_accepted": True, "final_problem": problem}
    else:
        return {"is_accepted": False}

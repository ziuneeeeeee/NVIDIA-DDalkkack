from pydantic import BaseModel
from typing import List, Optional
import concurrent.futures

from core.models import Problem, GradeResult
from core.clients import get_openai_client
from nodes.retrieve import get_topic_overview
from main import run_generation, run_grading

class MockExamResult(BaseModel):
    total_score: float
    max_score: float = 100.0
    comprehensive_feedback: str
    results: List[GradeResult]

class ConceptList(BaseModel):
    concepts: List[str]

def orchestrate_exam_concepts(topic_range: str, num_questions: int) -> List[str]:
    """주어진 범위 내에서 중복되지 않는 N개의 세부 개념 추출 (Orchestrator)"""
    reference_text = get_topic_overview(topic_range, top_k=15)

    client = get_openai_client()
    response = client.beta.chat.completions.parse(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "당신은 모의고사 출제 매니저입니다. 반드시 주어진 발췌문에 실제로 등장하는 개념만 선정하고, 개념 중복을 방지해야 합니다. 발췌문에 없는 개념은 절대로 만들어내지 마세요. 출력은 반드시 한국어로 작성하세요."},
            {"role": "user", "content": f"발췌문:\n{reference_text}\n\n출제 범위: {topic_range}\n필요한 문제 수: {num_questions}개\n\n위 발췌문 내에서 서로 중복되지 않는 핵심 세부 개념 {num_questions}개를 추출하세요. 발췌문에 없는 개념은 만들지 마세요."}
        ],
        response_format=ConceptList,
    )
    return response.choices[0].message.parsed.concepts

def generate_mock_exam(topic_range: str, num_questions: int, difficulty: str = "중") -> List[Problem]:
    """비동기 병렬 처리로 여러 문제를 생성"""
    concepts = orchestrate_exam_concepts(topic_range, num_questions)
    problems = []
    
    print(f"\n[Mock Exam] '{topic_range}' 범위에서 {num_questions}문제 병렬 생성 시작...")
    
    # ThreadPoolExecutor를 사용한 병렬 생성
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(num_questions, 5)) as executor:
        futures = {executor.submit(run_generation, c, difficulty): c for c in concepts}
        for future in concurrent.futures.as_completed(futures):
            res = future.result()
            if res:
                problems.append(res)
                
    print(f"\n[Mock Exam] {len(problems)}/{num_questions} 문제 생성 완료.")
    return problems

def grade_mock_exam(problems: List[Problem], student_answers: List[str]) -> MockExamResult:
    """비동기 병렬 처리로 모의고사 전체 문항 채점 및 배점 스케일링, 종합 리포트 생성"""
    num_questions = len(problems)
    if num_questions == 0:
        return MockExamResult(total_score=0, comprehensive_feedback="문제가 없습니다.", results=[])
        
    score_per_q = 100.0 / num_questions
    raw_results = []
    
    print(f"\n[Mock Exam] {num_questions}문제 병렬 채점 시작...")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(num_questions, 5)) as executor:
        futures = {executor.submit(run_grading, p, a): i for i, (p, a) in enumerate(zip(problems, student_answers))}
        for future in concurrent.futures.as_completed(futures):
            idx = futures[future]
            res = future.result()
            raw_results.append((idx, res))
            
    # 결과를 원래 문제 순서대로 정렬
    raw_results.sort(key=lambda x: x[0])
    grade_results = [r.get("grade_result") for idx, r in raw_results if r.get("grade_result") is not None]
    
    total_scaled_score = 0.0
    report_prompt = f"학생이 총 {num_questions}문제의 모의고사를 풀었습니다. 각 문제는 10점 만점 기준에서 {score_per_q}점으로 환산됩니다.\n결과는 다음과 같습니다:\n"
    
    for idx, (p, gr) in enumerate(zip(problems, grade_results)):
        score = gr.final_score
        scaled = (score / 10.0) * score_per_q
        total_scaled_score += scaled
        report_prompt += f"Q{idx+1}. [{p.type}] {p.question}\n-> 채점 결과: {score}/10점 (환산 {scaled:.1f}점)\n"
        
    report_prompt += f"\n모의고사 총점: {total_scaled_score:.1f}/100점. 위 결과를 바탕으로 취약점과 우수한 점을 분석하여 종합 성적표(피드백)를 3~4문장으로 작성해주세요. 반드시 한국어(Korean)로 작성하세요."
    
    print("\n[Mock Exam] 종합 성적 리포트 생성 중...")
    client = get_openai_client()
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "당신은 학생의 모의고사 성적을 분석하는 따뜻하고 꼼꼼한 AI 튜터입니다."},
            {"role": "user", "content": report_prompt}
        ]
    )
    feedback = response.choices[0].message.content
    
    return MockExamResult(
        total_score=round(total_scaled_score, 1),
        comprehensive_feedback=feedback,
        results=grade_results
    )

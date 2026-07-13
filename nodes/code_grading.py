from __future__ import annotations
import os
import re
import subprocess
import sys
import tempfile
from core.state import GradingState
from core.models import GradeResult

CODE_TIMEOUT = 5   # 초

def _extract_func_name(code: str) -> str | None:
    """학생 코드에서 첫 번째 def 함수명 추출."""
    m = re.search(r"def\s+(\w+)\s*\(", code)
    return m.group(1) if m else None

def _run_code_sandbox(code: str, test_cases: list[dict]) -> list[dict]:
    """
    subprocess로 학생 코드 실행 + TC 통과 여부 반환.
    함수명은 코드에서 자동 추출.
    타임아웃: 5초
    """
    func_name = _extract_func_name(code)
    results = []

    for tc in test_cases:
        inp = tc.get("input", [])
        expected = tc.get("expected")

        if func_name:
            if isinstance(inp, list):
                args_str = ", ".join(repr(a) for a in inp)
            else:
                args_str = repr(inp)
            harness = f"{code}\n\nprint(repr({func_name}({args_str})))"
        else:
            harness = code

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(harness)
            tmp_path = f.name

        try:
            proc = subprocess.run(
                [sys.executable, tmp_path],
                capture_output=True,
                text=True,
                timeout=CODE_TIMEOUT,
            )
            actual_raw = proc.stdout.strip()
            try:
                actual = eval(actual_raw)
            except Exception:
                actual = actual_raw
            passed = actual == expected
        except subprocess.TimeoutExpired:
            actual = f"TIMEOUT ({CODE_TIMEOUT}s 초과)"
            passed = False
        except Exception as e:
            actual = f"ERROR: {e}"
            passed = False
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

        results.append({
            "input":    inp,
            "expected": expected,
            "actual":   actual,
            "passed":   passed,
        })

    return results

def grade_code(state: GradingState) -> dict:
    """
    코딩형: subprocess 실행 기반 TC 통과율 채점.
    """
    problem = state["problem"]
    test_cases = problem.test_cases or []
    max_score = 10.0

    print(f"[grade_code] {len(test_cases)}개 TC 실행 중...")
    results = _run_code_sandbox(state["student_answer"], test_cases)

    passed_count = sum(1 for r in results if r["passed"])
    score = (passed_count / len(test_cases)) * max_score if test_cases else 0.0

    for r in results:
        status = "✅" if r["passed"] else "❌"
        print(f"  {status} input={r['input']} | expected={r['expected']} | actual={r['actual']}")

    formatted_results = []
    for i, r in enumerate(results):
        formatted_results.append({
            "point_name": f"Test Case {i+1}",
            "earned_score": (max_score / len(test_cases)) if r["passed"] else 0.0,
            "reason": f"입력: {r['input']} | 기대값: {r['expected']} | 실제값: {r['actual']}"
        })

    result = GradeResult(
        final_score=score,
        max_score=max_score,
        per_criterion=formatted_results,
        confidence="high",
        needs_human_review=False,
        grader_agreement=f"TC {passed_count}/{len(test_cases)} 통과 (실행 기반 채점)",
    )
    return {"grade_result": result, "critiques": []}

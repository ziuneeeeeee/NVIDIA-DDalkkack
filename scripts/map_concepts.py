"""
map_concepts.py
────────────────
팀원 1이 넘겨준 concept_bank.json을 읽어 각 개념에 문제 유형
(CALCULATION / MULTIPLE_CHOICE / TRUE_FALSE / DESCRIPTIVE)과 난이도
(쉬움/보통/어려움)를 매핑하고 mapped_concepts.json으로 저장한다.
(팀원 3/4의 입력 파일)

비율은 고정하지 않고 개념별 내용에 가장 적합한 값을 그대로 채택한다.
문제 총 개수는 min(핵심개념 수, 20) — 20개를 넘으면 핵심도 상위 20개만 선택.

사용법:
  python scripts/map_concepts.py --input data/concept_bank.sample.json --output mapped_concepts.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nodes.type_mapping import MAX_TOTAL, map_concepts_to_types


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="팀원 1의 concept_bank.json 경로")
    parser.add_argument("--output", default="mapped_concepts.json", help="출력 파일 경로")
    args = parser.parse_args()

    with open(args.input, encoding="utf-8") as f:
        concepts = json.load(f)

    mapped = map_concepts_to_types(concepts)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump({"mapped_concepts": mapped}, f, ensure_ascii=False, indent=2)

    total = len(mapped)
    category_counts = Counter(c["mapped_category"] for c in mapped)
    difficulty_counts = Counter(c["difficulty"] for c in mapped)
    low_confidence = [c for c in mapped if c.get("confidence") == "low"]

    dropped = len(concepts) - total
    print(f"입력 개념 {len(concepts)}개 중 {total}개 채택 -> {args.output}")
    if dropped > 0:
        print(f"  (핵심개념이 {MAX_TOTAL}개를 초과해 핵심도 상위 {MAX_TOTAL}개만 선택, {dropped}개 제외)")
    print("[유형 분포]")
    for category, count in category_counts.most_common():
        print(f"  {category}: {count}개 ({count / total:.0%})")
    print("[난이도 분포]")
    for difficulty in ("쉬움", "보통", "어려움"):
        count = difficulty_counts.get(difficulty, 0)
        print(f"  {difficulty}: {count}개 ({count / total:.0%})")
    if low_confidence:
        print(f"[경계 케이스: 확신도 낮음 {len(low_confidence)}개]")
        for c in low_confidence:
            print(f"  {c['concept_id']} ({c['concept_name']}): {c['mapped_category']} (차점: {c['runner_up_category']})")


if __name__ == "__main__":
    main()

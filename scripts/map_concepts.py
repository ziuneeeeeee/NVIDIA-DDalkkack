"""
map_concepts.py
────────────────
팀원 1이 넘겨준 concept_bank.json을 읽어 각 개념에 문제 유형
(CALCULATION / MULTIPLE_CHOICE / TRUE_FALSE / DESCRIPTIVE)을 매핑하고,
mapped_concepts.json으로 저장한다. (팀원 3/4의 입력 파일)

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

from nodes.type_mapping import map_concepts_to_types


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

    counts = Counter(c["mapped_category"] for c in mapped)
    total = len(mapped)
    print(f"총 {total}개 개념 매핑 완료 -> {args.output}")
    for category, count in counts.most_common():
        print(f"  {category}: {count}개 ({count / total:.0%})")


if __name__ == "__main__":
    main()

# 수강 과목 학습 도우미 (Study Helper) v2

> **LangGraph 기반 멀티에이전트 문제 생성 · 교차 채점 · 종합 모의고사 시스템**
>
> 사용자가 입력한 학습 개념에 대해 강의자료(RAG)를 검색하여 실시간으로 문제를 출제하고, 다수의 AI 채점관이 교차 채점하여 피드백과 오답 진단을 제공하는 지능형 학습 보조 웹 애플리케이션입니다.

---

## 🚀 주요 기능

### 1. 📖 RAG 기반 강의자료 검색 (Hybrid Search)
- 사용자의 강의자료 PDF를 미리 인덱싱하여 **벡터 DB(Chroma)**와 **키워드 DB(BM25)**에 적재합니다.
- AI는 문제 출제 및 채점 시 절대로 사전지식(환각)에만 의존하지 않고, 반드시 검색된 **실제 강의자료 내용에 근거**하여 동작합니다.

### 2. 📝 4-에이전트 문제 생성 (Generation Phase)
사용자가 학습할 "개념"을 입력하면 `generation_graph`를 통해 4명의 독립된 AI가 토론하며 고품질의 문제를 만듭니다.
1. **Generator**: 목표 난이도에 맞춰 10점 만점의 문제 초안 생성
2. **Validator**: 생성된 문제가 실제 강의자료 내용에 부합하는지 팩트체크
3. **Difficulty Assessor**: 문제의 실제 난이도를 체감하여 측정
4. **Concluder**: 검증·난이도 평가를 종합하여 최종 **승인(✅)** 혹은 **반려(❌)** 후 재시도 지시 (최대 3회)

### 3. ⚖️ 3-채점관 교차 채점 (Grading Phase)
학생이 답안을 제출하면 문제 유형에 맞게 자동 라우팅되어 채점이 진행됩니다(`grading_graph`).
- **단답형/객관식**: 정답과 직접 대조하는 정규화 기반 자동 채점 (LLM 불필요)
- **코딩형**: 백그라운드 파이썬 서브프로세스를 통한 샌드박스 테스트케이스 검증
- **서술형 (3-에이전트 교차 검증)**:
  - 문제에 맞는 10점 만점 **채점 기준표(루브릭)**를 GPT-4o로 먼저 생성
  - **Strict (깐깐함)**: 용어와 근거에 완벽히 부합해야 점수 부여
  - **Lenient (관대함)**: 문맥상 의미만 맞으면 점수 부여
  - **Keyword (핵심어)**: 필수 키워드 유무 위주로 신속 평가
  - **Judge (최종 판정)**: 3명의 점수 중앙값을 채택, 편차가 클 경우 Human Review 경고

### 4. 🗒️ 종합 모의고사 모드 (Mock Exam)
- 사용자가 **출제 범위**와 **문제 수**를 지정하면 Orchestrator AI가 개념 중복 없이 세부 주제를 선정합니다.
- `ThreadPoolExecutor`로 여러 문제를 **비동기 병렬 출제**하여 대기 시간을 최소화합니다.
- 전체 답안 제출 시 역시 병렬 채점 후, 각 문항 배점을 **100점 만점**으로 자동 스케일링합니다.
- AI 튜터가 전체 결과를 종합 분석하여 **성적 리포트 피드백**을 생성합니다.

### 5. 🌐 웹 애플리케이션 UI
- **React (Vite) + Inter 폰트** 기반의 프리미엄 다크 UI
- 오로라 블롭 배경 애니메이션 + Glassmorphism 카드
- [단건 학습] / [종합 모의고사] 모드 탭 전환
- 항목별 채점 근거, 점수 바, 오답 진단, 다음 추천 학습 시각화

### 6. 🧩 팀 협업 파이프라인: 개념 → 문제유형 매핑 (concept_bank → mapped_concepts)

팀원1(개념 추출) → **팀원2(유형/난이도 매핑)** → 팀원3(문제 생성) / 팀원4(루브릭 생성)으로 이어지는
20문제 고정 시험지 조립 파이프라인의 중간 단계입니다. `nodes/type_mapping.py`가 담당합니다.

**입력** — 팀원1 산출물 `concept_bank.json` (리스트):
```json
{
  "concept_id": "concept_h001",
  "concept_name": "Heap의 정의와 heap property",
  "concept_summary": "...",
  "source_title": "Heap",
  "source_pages": [3],
  "source_context": "..."
}
```
`concept_id`, `concept_name`은 필수. 누락되거나 `concept_id`가 중복되면 즉시 에러로 알려줍니다.

**출력** — `mapped_concepts.json`. 원본 필드에 아래가 추가됩니다:

| 필드 | 값 | 설명 |
|---|---|---|
| `mapped_category` | `CALCULATION`/`MULTIPLE_CHOICE`/`TRUE_FALSE`/`DESCRIPTIVE` | 문제 유형 |
| `mapping_reason` | 한국어 문자열 | 유형 판단 근거 |
| `difficulty` | `쉬움`/`보통`/`어려움` | 난이도 |
| `difficulty_reason` | 한국어 문자열 | 난이도 판단 근거 |
| `confidence` | `high`/`low` | `low`면 점수 1순위 유형과 실제 배정이 다른 경계 케이스 |
| `runner_up_category` | (confidence가 low일 때만) | 차점 유형 |

**목표 비율은 20문제 고정 기준으로 코드가 강제합니다** (LLM은 적합도 점수만 매기고,
실제 개수 배정은 결정론적 로직이 수행 — 개념 수가 20이 아니면 동일 비율로 자동 스케일링):
- 유형: 객관식 8 / 참거짓 6 / 서술형+계산형 6 (40% / 30% / 30%)
- 난이도: 쉬움 6 / 보통 10 / 어려움 4 (30% / 50% / 20%)

**실행**:
```bash
python scripts/map_concepts.py --input concept_bank.json --output mapped_concepts.json
```

---

## 📂 디렉터리 아키텍처

```text
study_helper_web/
├── main.py                  # CLI 환경 실행 진입점
├── api.py                   # FastAPI 서버 (프론트엔드 ↔ 백엔드 브릿지)
├── test_exam.py             # 모의고사 파이프라인 디버그 스크립트
├── .env                     # 환경변수 (OPENAI_API_KEY, LANGSMITH 설정)
├── requirements.txt         # Python 의존성 패키지
│
├── core/                    # 공통 핵심 계층
│   ├── clients.py           # OpenAI 클라이언트 초기화 및 LangSmith 래퍼
│   ├── models.py            # Pydantic 스키마 (Problem, GradeResult, RubricCriterion 등)
│   ├── state.py             # LangGraph 상태 딕셔너리 (GradingState, GenerationState)
│   └── exam.py              # 모의고사 Orchestrator: 병렬 출제·채점·스케일링·피드백
│
├── graphs/                  # 파이프라인 조립 계층
│   ├── generation_graph.py  # 문제 생성 플로우 (생성 → 검증 → 판정 루프)
│   └── grading_graph.py     # 채점 플로우 (루브릭 → 분기 → 교차채점 → 진단)
│
├── nodes/                   # 개별 AI 에이전트 및 기능 노드
│   ├── retrieve.py          # 하이브리드 RAG 검색 (Vector + BM25)
│   ├── generation.py        # 문제 생성 4-에이전트 (Generator/Validator/Difficulty/Concluder)
│   ├── type_mapping.py      # [팀원2] concept_bank -> mapped_concepts 배치 유형/난이도 매핑
│   ├── rubric.py            # 루브릭 생성(GPT-4o) + 4종 검증 에이전트
│   ├── essay_grading.py     # 서술형 채점 3-에이전트 (Strict/Lenient/Keyword)
│   ├── objective_grading.py # 객관식·단답형 정규화 자동 채점
│   ├── code_grading.py      # 코딩형 샌드박스 실행 채점
│   ├── judge.py             # 채점자 편차 조율 및 최종 점수 종합 (중앙값)
│   ├── diagnose.py          # 오답 원인 4유형 진단
│   ├── adapt.py             # 다음 문제 난이도 상하향 조절
│   ├── recommend.py         # 다음 추천 개념 생성
│   └── parse_problem.py     # 이미지 URL → GPT-4o Vision 전처리 (OCR 확장 예정)
│
├── scripts/
│   ├── ingest.py            # PDF 강의자료 → ChromaDB + BM25 인덱싱
│   └── map_concepts.py      # [팀원2] concept_bank.json -> mapped_concepts.json CLI
│
└── frontend/                # React (Vite) 프론트엔드
    ├── src/
    │   ├── App.tsx          # 메인 UI (단건 학습 / 종합 모의고사 모드)
    │   └── index.css        # 전체 디자인 시스템 (오로라 BG, 다크 테마)
    ├── package.json
    └── vite.config.ts
```

---

## ⚙️ 설치 및 실행 방법

### 1. Python 패키지 설치
```bash
pip install -r requirements.txt
```

### 2. 환경변수 설정
프로젝트 최상단에 `.env` 파일을 생성합니다.
```env
OPENAI_API_KEY="your-api-key"

# (선택) LangSmith 트레이싱 활성화 시
LANGCHAIN_TRACING_V2=true
LANGCHAIN_ENDPOINT="https://api.smith.langchain.com"
LANGCHAIN_API_KEY="your-langsmith-api-key"
LANGCHAIN_PROJECT="study_helper_v2"
```

### 3. 강의자료 인덱싱 (최초 1회 필수)
`data/rag.pdf` 경로에 강의자료 PDF를 넣은 뒤 실행합니다.
```bash
python scripts/ingest.py
```

### 4. 백엔드 서버 실행
```bash
uvicorn api:app --reload
# → http://localhost:8000 에서 API 서버 기동
```

### 5. 프론트엔드 개발 서버 실행 (별도 터미널)
```bash
cd frontend
npm install    # 최초 1회
npm run dev
# → http://localhost:5173 에서 웹 앱 접속
```

### 6. (선택) CLI 모드 실행
```bash
python main.py
# 터미널에서 개념 입력 → 문제 생성 → 답안 입력 → 채점 세션 시작
```

---

## 🔗 관련 문서

| 문서 | 설명 |
|---|---|
| [버전2.md](버전2.md) | v1 → v2 아키텍처 전환 명세 및 변경 이력 |
| [파일서술.md](파일서술.md) | 각 파일 및 디렉터리의 상세 역할 설명 |
| [보완방안.md](보완방안.md) | 현재 한계점 분석 및 향후 개선 로드맵 (PDF/Word 내보내기, OCR 채점 등) |

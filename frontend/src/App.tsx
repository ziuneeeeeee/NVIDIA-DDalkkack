import { useState } from 'react';
import './index.css';

/* ─── Types ───────────────────────────────────────── */
interface Problem { problem_id: string; type: string; question: string; }
interface GradeDetail { point_name: string; earned_score: number; reason: string; }
interface GradeResult {
  final_score: number; max_score: number; confidence: string;
  needs_human_review: boolean; grader_agreement: string; per_criterion: GradeDetail[];
}
interface Diagnosis { error_type: string; weak_concept: string; detail: string; }
interface GradingResponse {
  grade_result: GradeResult; diagnosis?: Diagnosis; next_concept?: string; next_difficulty?: string;
}
interface MockExamResult {
  total_score: number; max_score: number; comprehensive_feedback: string; results: GradeResult[];
}

/* ─── Helpers ─────────────────────────────────────── */
function typeBadgeClass(t: string) {
  if (t === '서술형') return 'problem-type-badge badge-essay';
  if (t === '객관식' || t === '단답형') return 'problem-type-badge badge-obj';
  if (t === '코딩형') return 'problem-type-badge badge-code';
  return 'problem-type-badge badge-generic';
}

function ScoreBar({ score, max }: { score: number; max: number }) {
  const pct = Math.min(100, max > 0 ? (score / max) * 100 : 0);
  return (
    <div className="sbar-track">
      <div className="sbar-fill" style={{ width: `${pct}%` }} />
    </div>
  );
}

/* ─── App ─────────────────────────────────────────── */
export default function App() {
  const [mode, setMode] = useState<'single' | 'mock'>('single');

  /* single */
  const [concept, setConcept]           = useState('');
  const [difficulty, setDifficulty]     = useState('중');
  const [loadingQ, setLoadingQ]         = useState(false);
  const [problem, setProblem]           = useState<Problem | null>(null);
  const [answer, setAnswer]             = useState('');
  const [loadingG, setLoadingG]         = useState(false);
  const [gradeData, setGradeData]       = useState<GradingResponse | null>(null);

  /* mock */
  const [mockRange, setMockRange]       = useState('');
  const [mockN, setMockN]               = useState(2);
  const [loadingMQ, setLoadingMQ]       = useState(false);
  const [mockProblems, setMockProblems] = useState<Problem[] | null>(null);
  const [mockAnswers, setMockAnswers]   = useState<string[]>([]);
  const [loadingMG, setLoadingMG]       = useState(false);
  const [mockResult, setMockResult]     = useState<MockExamResult | null>(null);

  /* ── API calls ── */
  const generateSingle = async () => {
    if (!concept) return;
    setLoadingQ(true); setProblem(null); setGradeData(null); setAnswer('');
    try {
      const r = await fetch('http://localhost:8000/generate_problem', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ concept, target_difficulty: difficulty }),
      });
      const d = await r.json();
      if (r.ok) setProblem(d.problem); else alert(d.detail || '문제 생성 실패');
    } catch { alert('서버 연결 오류'); }
    finally { setLoadingQ(false); }
  };

  const gradeSingle = async () => {
    if (!answer || !problem) return;
    setLoadingG(true); setGradeData(null);
    try {
      const r = await fetch('http://localhost:8000/grade_answer', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ problem, student_answer: answer }),
      });
      const d = await r.json();
      if (r.ok) setGradeData(d.result); else alert(d.detail || '채점 실패');
    } catch { alert('서버 연결 오류'); }
    finally { setLoadingG(false); }
  };

  const generateMock = async () => {
    if (!mockRange) return;
    setLoadingMQ(true); setMockProblems(null); setMockResult(null); setMockAnswers([]);
    try {
      const r = await fetch('http://localhost:8000/generate_mock_exam', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic_range: mockRange, num_questions: mockN, target_difficulty: difficulty }),
      });
      const d = await r.json();
      if (r.ok) { setMockProblems(d.problems); setMockAnswers(new Array(d.problems.length).fill('')); }
      else alert(d.detail || '모의고사 생성 실패');
    } catch { alert('서버 연결 오류'); }
    finally { setLoadingMQ(false); }
  };

  const gradeMock = async () => {
    if (!mockProblems) return;
    setLoadingMG(true); setMockResult(null);
    try {
      const r = await fetch('http://localhost:8000/grade_mock_exam', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ problems: mockProblems, student_answers: mockAnswers }),
      });
      const d = await r.json();
      if (r.ok) setMockResult(d.result); else alert(d.detail || '채점 실패');
    } catch { alert('서버 연결 오류'); }
    finally { setLoadingMG(false); }
  };

  /* ─── Render ─── */
  return (
    <div className="app-root">

      {/* Aurora */}
      <div className="bg-aurora">
        <div className="aurora-blob" />
        <div className="aurora-blob" />
        <div className="aurora-blob" />
        <div className="aurora-blob" />
      </div>

      {/* Header */}
      <header className="site-header">
        <div className="eyebrow"><span className="dot" />Multi-Agent AI System</div>
        <h1>AI 학습 도우미</h1>
        <p className="sub">강의자료 기반 문제 생성 · 3-채점관 교차 검증 · 오답 진단</p>
      </header>

      <div className="main-wrap">

        {/* Mode Tabs */}
        <div className="mode-tabs">
          <button className={`mode-tab ${mode === 'single' ? 'active' : ''}`} onClick={() => setMode('single')}>
            단건 학습
          </button>
          <button className={`mode-tab ${mode === 'mock' ? 'active' : ''}`} onClick={() => setMode('mock')}>
            종합 모의고사
          </button>
        </div>

        {/* ══════════ SINGLE ══════════ */}
        {mode === 'single' && <>

          {/* Input */}
          <div className="panel">
            <label className="field-label">학습할 개념</label>
            <div className="input-row">
              <input
                className="text-input"
                type="text"
                placeholder="예: 데이터베이스 트랜잭션, 파이썬 제너레이터…"
                value={concept}
                onChange={e => setConcept(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && generateSingle()}
              />
              <select className="select-input" value={difficulty} onChange={e => setDifficulty(e.target.value)}>
                <option value="상">난이도 상</option>
                <option value="중">난이도 중</option>
                <option value="하">난이도 하</option>
              </select>
              <button className="btn-primary" onClick={generateSingle} disabled={loadingQ || !concept}>
                {loadingQ ? <span className="spin" /> : '문제 생성'}
              </button>
            </div>
            <p className="hint">RAG 검색 → Generator → Validator → Difficulty → Concluder 순서로 4-에이전트가 출제합니다.</p>
          </div>

          {/* Problem */}
          {problem && (
            <div className="panel enter">
              <span className={typeBadgeClass(problem.type)}>{problem.type}</span>
              <div className="problem-body">{problem.question}</div>

              <label className="field-label mt-m">내 답안</label>
              <textarea
                className="textarea-input"
                rows={5}
                placeholder="답변을 입력하세요…"
                value={answer}
                onChange={e => setAnswer(e.target.value)}
              />
              <button className="btn-primary btn-full" onClick={gradeSingle} disabled={loadingG || !answer}>
                {loadingG ? <><span className="spin" />&nbsp;채점 중…</> : '답안 제출 및 채점 →'}
              </button>
            </div>
          )}

          {/* Grade Result */}
          {gradeData?.grade_result && (() => {
            const g = gradeData.grade_result;
            return (
              <div className="panel result-panel enter">
                <div className="score-hero">
                  <span className="score-num">{g.final_score.toFixed(1)}</span>
                  <span className="score-denom">/ {g.max_score.toFixed(0)}점</span>
                </div>
                <ScoreBar score={g.final_score} max={g.max_score} />

                <div className="meta-row">
                  <div className="meta-chip">
                    <span className="mc-label">신뢰도</span>
                    <span className="mc-value">{g.confidence === 'high' ? '높음 ✓' : '낮음'}</span>
                  </div>
                  <div className={`meta-chip ${g.needs_human_review ? 'warn' : ''}`}>
                    <span className="mc-label">채점단 상태</span>
                    <span className="mc-value">{g.needs_human_review ? '⚠ 편차 큼' : '합의됨'}</span>
                  </div>
                </div>

                {gradeData.diagnosis && (
                  <div className="diagnosis-panel">
                    <div className="dp-title">오답 진단</div>
                    <p><strong>오류 유형:</strong> {gradeData.diagnosis.error_type}</p>
                    <p><strong>부족한 개념:</strong> {gradeData.diagnosis.weak_concept}</p>
                    <p>{gradeData.diagnosis.detail}</p>
                  </div>
                )}

                {g.per_criterion?.length > 0 && (
                  <>
                    <div className="section-divider"><span>항목별 평가</span></div>
                    {g.per_criterion.map((c, i) => (
                      <div key={i} className="crit-row">
                        <div className="crit-top">
                          <span className="crit-name">{c.point_name}</span>
                          <span className={`crit-tag ${c.earned_score > 0 ? 'pos' : 'neg'}`}>
                            {c.earned_score > 0 ? `+${c.earned_score}점` : '0점'}
                          </span>
                        </div>
                        <div className="crit-reason">{c.reason}</div>
                      </div>
                    ))}
                  </>
                )}

                <div className="recommend-panel">
                  <div className="rp-title">다음 추천 학습</div>
                  <p>개념 <strong>{gradeData.next_concept || '—'}</strong>&ensp;·&ensp;난이도 <strong>{gradeData.next_difficulty || '—'}</strong></p>
                </div>
              </div>
            );
          })()}
        </>}

        {/* ══════════ MOCK EXAM ══════════ */}
        {mode === 'mock' && <>

          {/* Setup */}
          <div className="panel">
            <label className="field-label">출제 범위</label>
            <div className="input-row">
              <input
                className="text-input"
                type="text"
                placeholder="예: 자료구조 1~3단원, 운영체제 전반…"
                value={mockRange}
                onChange={e => setMockRange(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && generateMock()}
              />
              <select className="select-input" value={mockN} onChange={e => setMockN(+e.target.value)}>
                <option value={2}>2문제</option>
                <option value={3}>3문제</option>
                <option value={5}>5문제</option>
                <option value={10}>10문제</option>
              </select>
              <select className="select-input" value={difficulty} onChange={e => setDifficulty(e.target.value)}>
                <option value="상">상</option>
                <option value="중">중</option>
                <option value="하">하</option>
              </select>
              <button className="btn-primary" onClick={generateMock} disabled={loadingMQ || !mockRange}>
                {loadingMQ ? <span className="spin" /> : '출제'}
              </button>
            </div>
            <p className="hint">Orchestrator AI가 개념 중복 없이 세부 주제를 선정 후 병렬 출제합니다. (1~3분 소요)</p>
          </div>

          {/* Questions */}
          {mockProblems && !mockResult && (
            <div className="panel enter">
              <p className="panel-title">{mockProblems.length}문항 모의고사</p>

              {mockProblems.map((p, i) => (
                <div key={i} className="q-block">
                  <div className="q-num">Q{i + 1}</div>
                  <span className={typeBadgeClass(p.type)}>{p.type}</span>
                  <div className="problem-body" style={{ marginBottom: '0.9rem' }}>{p.question}</div>
                  <label className="field-label">답안</label>
                  <textarea
                    className="textarea-input"
                    rows={3}
                    placeholder="답변을 입력하세요…"
                    value={mockAnswers[i] ?? ''}
                    onChange={e => { const a = [...mockAnswers]; a[i] = e.target.value; setMockAnswers(a); }}
                  />
                </div>
              ))}

              <button
                className="btn-primary btn-full"
                onClick={gradeMock}
                disabled={loadingMG || mockAnswers.some(a => !a?.trim())}
              >
                {loadingMG
                  ? <><span className="spin" />&nbsp;일괄 채점 중…</>
                  : `전체 ${mockProblems.length}문항 제출 →`}
              </button>
            </div>
          )}

          {/* Mock Result */}
          {mockResult && (
            <div className="panel result-panel enter">
              <div className="total-score-card">
                <div className="ts-num">{mockResult.total_score.toFixed(1)}</div>
                <div className="ts-label">/ {mockResult.max_score.toFixed(0)}점 만점</div>
                <div style={{ marginTop: '1.2rem', maxWidth: 300, margin: '1.2rem auto 0' }}>
                  <ScoreBar score={mockResult.total_score} max={mockResult.max_score} />
                </div>
              </div>

              <div className="recommend-panel" style={{ marginBottom: '1.6rem' }}>
                <div className="rp-title">AI 튜터 종합 피드백</div>
                <p>{mockResult.comprehensive_feedback}</p>
              </div>

              <div className="section-divider"><span>문항별 채점 결과</span></div>

              {mockResult.results.map((gr, i) => {
                const prob = mockProblems![i];
                const perQ = 100 / mockProblems!.length;
                const scaled = (gr.final_score / 10) * perQ;
                const pct = Math.round((scaled / perQ) * 100);
                return (
                  <div key={i} className="crit-row">
                    <div className="crit-top">
                      <span className="crit-name">Q{i + 1}. {prob.type}</span>
                      <span className={`crit-tag ${scaled >= perQ * 0.5 ? 'pos' : 'neg'}`}>
                        {scaled.toFixed(1)} / {perQ.toFixed(1)}점 ({pct}%)
                      </span>
                    </div>
                    <div className="crit-reason" style={{ marginBottom: '0.5rem' }}>{prob.question}</div>
                    <ScoreBar score={scaled} max={perQ} />
                  </div>
                );
              })}

              <button
                className="btn-ghost btn-full"
                onClick={() => { setMockResult(null); setMockProblems(null); setMockAnswers([]); setMockRange(''); }}
                style={{ marginTop: '1.5rem' }}
              >
                새 모의고사 시작
              </button>
            </div>
          )}
        </>}

      </div>
    </div>
  );
}

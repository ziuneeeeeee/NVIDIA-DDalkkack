import { useState, useEffect } from 'react';
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
interface IngestSummary {
  source_type: string; source_path: string; page_count: number; chunk_count: number;
  collection: string; concept_count?: number; new_concept_count?: number; total_concept_count?: number;
}
interface RoomSummary {
  room_id: string; name: string; created_at: string; updated_at: string;
  upload_count: number; concept_count: number;
}
interface MappedConcept {
  concept_id: string; concept_name: string; concept_summary?: string;
  importance?: string; mapped_category: string; mapping_reason: string; confidence: string;
}
interface UploadRecord { filename: string; source_type: string; page_count: number; chunk_count: number; new_concept_count: number; }
interface RoomDetail {
  room_id: string; name: string; created_at: string; updated_at: string;
  uploads: UploadRecord[]; concept_bank: unknown[]; mapped_concepts: MappedConcept[];
}

/* ─── Helpers ─────────────────────────────────────── */
const CATEGORY_LABEL: Record<string, string> = {
  MULTIPLE_CHOICE: '객관식', TRUE_FALSE: '참거짓', DESCRIPTIVE: '서술형', CALCULATION: '단답형',
};

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
  const [view, setView] = useState<'rooms' | 'freeform'>('rooms');

  /* rooms: list & create */
  const [roomList, setRoomList]           = useState<RoomSummary[]>([]);
  const [loadingRoomList, setLoadingRoomList] = useState(false);
  const [newRoomName, setNewRoomName]     = useState('');
  const [creatingRoom, setCreatingRoom]   = useState(false);

  /* rooms: detail */
  const [currentRoom, setCurrentRoom]     = useState<RoomDetail | null>(null);
  const [renaming, setRenaming]           = useState(false);
  const [roomNameDraft, setRoomNameDraft] = useState('');

  /* rooms: upload */
  const [roomFile, setRoomFile]                 = useState<File | null>(null);
  const [roomUploading, setRoomUploading]       = useState(false);
  const [roomUploadResult, setRoomUploadResult] = useState<IngestSummary | null>(null);
  const [roomUploadError, setRoomUploadError]   = useState<string | null>(null);

  /* rooms: quiz */
  const [roomDifficulty, setRoomDifficulty]     = useState('중');
  const [loadingRoomQ, setLoadingRoomQ]         = useState<'simple' | 'mock' | null>(null);
  const [roomProblems, setRoomProblems]         = useState<Problem[] | null>(null);
  const [roomAnswers, setRoomAnswers]           = useState<string[]>([]);
  const [loadingRoomG, setLoadingRoomG]         = useState(false);
  const [roomResult, setRoomResult]             = useState<MockExamResult | null>(null);

  /* upload */
  const [uploadFile, setUploadFile]     = useState<File | null>(null);
  const [uploading, setUploading]       = useState(false);
  const [uploadResult, setUploadResult] = useState<IngestSummary | null>(null);
  const [uploadError, setUploadError]   = useState<string | null>(null);

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

  /* ── Room API calls ── */
  const loadRooms = async () => {
    setLoadingRoomList(true);
    try {
      const r = await fetch('http://localhost:8000/rooms');
      const d = await r.json();
      if (r.ok) setRoomList(d.rooms);
    } catch { /* ignore */ }
    finally { setLoadingRoomList(false); }
  };

  useEffect(() => { if (view === 'rooms' && !currentRoom) loadRooms(); }, [view, currentRoom]);

  const createRoom = async () => {
    if (!newRoomName.trim()) return;
    setCreatingRoom(true);
    try {
      const r = await fetch('http://localhost:8000/rooms', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newRoomName }),
      });
      const d = await r.json();
      if (r.ok) { setNewRoomName(''); await enterRoom(d.room_id); }
      else alert(d.detail || '방 생성 실패');
    } catch { alert('서버 연결 오류'); }
    finally { setCreatingRoom(false); }
  };

  const enterRoom = async (roomId: string) => {
    setRoomProblems(null); setRoomResult(null); setRoomAnswers([]);
    setRoomUploadResult(null); setRoomUploadError(null); setRoomFile(null); setRenaming(false);
    try {
      const r = await fetch(`http://localhost:8000/rooms/${roomId}`);
      const d = await r.json();
      if (r.ok) { setCurrentRoom(d); setRoomNameDraft(d.name); }
      else alert(d.detail || '방 조회 실패');
    } catch { alert('서버 연결 오류'); }
  };

  const exitRoom = () => { setCurrentRoom(null); };

  const submitRename = async () => {
    if (!currentRoom || !roomNameDraft.trim()) return;
    try {
      const r = await fetch(`http://localhost:8000/rooms/${currentRoom.room_id}`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: roomNameDraft }),
      });
      const d = await r.json();
      if (r.ok) { setCurrentRoom(d); setRenaming(false); }
      else alert(d.detail || '이름 변경 실패');
    } catch { alert('서버 연결 오류'); }
  };

  const uploadToRoom = async () => {
    if (!roomFile || !currentRoom) return;
    setRoomUploading(true); setRoomUploadResult(null); setRoomUploadError(null);
    try {
      const formData = new FormData();
      formData.append('file', roomFile);
      const r = await fetch(`http://localhost:8000/rooms/${currentRoom.room_id}/ingest`, { method: 'POST', body: formData });
      const d = await r.json();
      if (r.ok) { setRoomUploadResult(d); setRoomFile(null); await enterRoom(currentRoom.room_id); }
      else setRoomUploadError(d.detail || '업로드 실패');
    } catch { setRoomUploadError('서버 연결 오류'); }
    finally { setRoomUploading(false); }
  };

  const startRoomQuiz = async (kind: 'simple' | 'mock') => {
    if (!currentRoom) return;
    setLoadingRoomQ(kind); setRoomProblems(null); setRoomResult(null); setRoomAnswers([]);
    try {
      const endpoint = kind === 'simple' ? 'simple_check' : 'mock_exam';
      const r = await fetch(`http://localhost:8000/rooms/${currentRoom.room_id}/${endpoint}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_difficulty: roomDifficulty }),
      });
      const d = await r.json();
      if (r.ok) { setRoomProblems(d.problems); setRoomAnswers(new Array(d.problems.length).fill('')); }
      else alert(d.detail || '문제 생성 실패');
    } catch { alert('서버 연결 오류'); }
    finally { setLoadingRoomQ(null); }
  };

  const gradeRoomAnswers = async () => {
    if (!roomProblems) return;
    setLoadingRoomG(true); setRoomResult(null);
    try {
      const r = await fetch('http://localhost:8000/grade_mock_exam', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ problems: roomProblems, student_answers: roomAnswers }),
      });
      const d = await r.json();
      if (r.ok) setRoomResult(d.result); else alert(d.detail || '채점 실패');
    } catch { alert('서버 연결 오류'); }
    finally { setLoadingRoomG(false); }
  };

  /* ── API calls ── */
  const uploadMaterial = async () => {
    if (!uploadFile) return;
    setUploading(true); setUploadResult(null); setUploadError(null);
    try {
      const formData = new FormData();
      formData.append('file', uploadFile);
      const r = await fetch('http://localhost:8000/ingest', { method: 'POST', body: formData });
      const d = await r.json();
      if (r.ok) setUploadResult(d); else setUploadError(d.detail || '업로드 실패');
    } catch { setUploadError('서버 연결 오류'); }
    finally { setUploading(false); }
  };

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

        {/* Top-level view toggle */}
        <div className="mode-tabs">
          <button className={`mode-tab ${view === 'rooms' ? 'active' : ''}`} onClick={() => setView('rooms')}>방</button>
          <button className={`mode-tab ${view === 'freeform' ? 'active' : ''}`} onClick={() => setView('freeform')}>자유 입력</button>
        </div>

        {/* ══════════ ROOMS: LIST ══════════ */}
        {view === 'rooms' && !currentRoom && <>
          <div className="panel">
            <label className="field-label">새 방 만들기</label>
            <div className="input-row">
              <input
                className="text-input"
                type="text"
                placeholder="방 이름 (예: 알고리즘 중간고사 대비)"
                value={newRoomName}
                onChange={e => setNewRoomName(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && createRoom()}
              />
              <button className="btn-primary" onClick={createRoom} disabled={creatingRoom || !newRoomName.trim()}>
                {creatingRoom ? <span className="spin" /> : '방 만들기'}
              </button>
            </div>
          </div>

          <div className="panel">
            <p className="panel-title">내 방 목록</p>
            {loadingRoomList && <p className="hint">불러오는 중…</p>}
            {!loadingRoomList && roomList.length === 0 && (
              <p className="hint">아직 만든 방이 없습니다. 위에서 새 방을 만들어보세요.</p>
            )}
            {roomList.map(room => (
              <div
                key={room.room_id}
                className="q-block"
                style={{ cursor: 'pointer' }}
                onClick={() => enterRoom(room.room_id)}
              >
                <div className="crit-top">
                  <span className="crit-name">{room.name}</span>
                  <span className="crit-tag pos">{room.concept_count}개 개념</span>
                </div>
                <div className="crit-reason">
                  업로드 {room.upload_count}건 · 마지막 수정 {new Date(room.updated_at).toLocaleString()}
                </div>
              </div>
            ))}
          </div>
        </>}

        {/* ══════════ ROOMS: DETAIL ══════════ */}
        {view === 'rooms' && currentRoom && <>
          <div className="panel">
            <button className="btn-ghost" onClick={exitRoom} style={{ marginBottom: '0.8rem' }}>← 방 목록으로</button>
            {!renaming ? (
              <div className="input-row">
                <p className="panel-title" style={{ margin: 0, flex: 1 }}>{currentRoom.name}</p>
                <button className="btn-ghost" onClick={() => setRenaming(true)}>이름 변경</button>
              </div>
            ) : (
              <div className="input-row">
                <input
                  className="text-input"
                  value={roomNameDraft}
                  onChange={e => setRoomNameDraft(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && submitRename()}
                />
                <button className="btn-primary" onClick={submitRename}>저장</button>
                <button className="btn-ghost" onClick={() => { setRenaming(false); setRoomNameDraft(currentRoom.name); }}>취소</button>
              </div>
            )}
          </div>

          <div className="panel">
            <label className="field-label">강의자료 업로드 (PDF · 녹음파일 · 녹화강의 영상)</label>
            <div className="input-row">
              <input
                className="text-input"
                type="file"
                accept=".pdf,.mp3,.mpeg,.mpga,.m4a,.wav,.mp4,.mov,.mkv,.avi,.webm"
                onChange={e => {
                  setRoomFile(e.target.files?.[0] ?? null);
                  setRoomUploadResult(null); setRoomUploadError(null);
                }}
              />
              <button className="btn-primary" onClick={uploadToRoom} disabled={roomUploading || !roomFile}>
                {roomUploading ? <span className="spin" /> : '업로드 및 분석'}
              </button>
            </div>
            <p className="hint">
              업로드하면 이 방의 인덱스에 이어붙이고, 개념을 이름 기준으로 병합·중복제거한 뒤
              문제 유형까지 자동으로 다시 매핑합니다. 여러 파일을 계속 추가할 수 있습니다.
            </p>
            {roomUploadResult && (
              <div className="meta-row" style={{ marginTop: '0.8rem' }}>
                <div className="meta-chip">
                  <span className="mc-label">파일</span>
                  <span className="mc-value">{roomUploadResult.source_path}</span>
                </div>
                <div className="meta-chip">
                  <span className="mc-label">새로 추가된 개념</span>
                  <span className="mc-value">{roomUploadResult.new_concept_count}개 (총 {roomUploadResult.total_concept_count}개)</span>
                </div>
              </div>
            )}
            {roomUploadError && <p className="hint" style={{ color: '#e0685a' }}>⚠ {roomUploadError}</p>}
          </div>

          {currentRoom.mapped_concepts.length > 0 && (
            <div className="panel">
              <p className="panel-title">핵심개념 {currentRoom.mapped_concepts.length}개</p>
              <div>
                {currentRoom.mapped_concepts.map(c => (
                  <span
                    key={c.concept_id}
                    className={typeBadgeClass(CATEGORY_LABEL[c.mapped_category] || c.mapped_category)}
                    title={c.mapping_reason}
                    style={{ marginRight: '0.4rem', marginBottom: '0.4rem', display: 'inline-block' }}
                  >
                    {c.concept_name} · {CATEGORY_LABEL[c.mapped_category] || c.mapped_category}
                  </span>
                ))}
              </div>
            </div>
          )}

          {currentRoom.mapped_concepts.length > 0 && !roomProblems && !roomResult && (
            <div className="panel">
              <label className="field-label">난이도</label>
              <div className="input-row">
                <select className="select-input" value={roomDifficulty} onChange={e => setRoomDifficulty(e.target.value)}>
                  <option value="상">상</option>
                  <option value="중">중</option>
                  <option value="하">하</option>
                </select>
                <button className="btn-primary" onClick={() => startRoomQuiz('simple')} disabled={loadingRoomQ !== null}>
                  {loadingRoomQ === 'simple' ? <span className="spin" /> : `단순 개념 확인 (${currentRoom.mapped_concepts.length}문제)`}
                </button>
                <button className="btn-primary" onClick={() => startRoomQuiz('mock')} disabled={loadingRoomQ !== null}>
                  {loadingRoomQ === 'mock' ? <span className="spin" /> : `모의고사 (${Math.min(currentRoom.mapped_concepts.length, 20)}문제)`}
                </button>
              </div>
              <p className="hint">문제 개수는 핵심개념 수 기준으로 자동 결정됩니다 (직접 선택 없음).</p>
            </div>
          )}

          {currentRoom.mapped_concepts.length === 0 && (
            <p className="hint" style={{ padding: '0 0.2rem' }}>
              아직 분석된 핵심개념이 없습니다. 위에서 강의자료를 먼저 업로드하세요.
            </p>
          )}

          {/* Room quiz questions */}
          {roomProblems && !roomResult && (
            <div className="panel enter">
              <p className="panel-title">{roomProblems.length}문항</p>
              {roomProblems.map((p, i) => (
                <div key={i} className="q-block">
                  <div className="q-num">Q{i + 1}</div>
                  <span className={typeBadgeClass(p.type)}>{p.type}</span>
                  <div className="problem-body" style={{ marginBottom: '0.9rem' }}>{p.question}</div>
                  <label className="field-label">답안</label>
                  <textarea
                    className="textarea-input"
                    rows={3}
                    placeholder="답변을 입력하세요…"
                    value={roomAnswers[i] ?? ''}
                    onChange={e => { const a = [...roomAnswers]; a[i] = e.target.value; setRoomAnswers(a); }}
                  />
                </div>
              ))}
              <button
                className="btn-primary btn-full"
                onClick={gradeRoomAnswers}
                disabled={loadingRoomG || roomAnswers.some(a => !a?.trim())}
              >
                {loadingRoomG ? <><span className="spin" />&nbsp;일괄 채점 중…</> : `전체 ${roomProblems.length}문항 제출 →`}
              </button>
            </div>
          )}

          {/* Room quiz result */}
          {roomResult && (
            <div className="panel result-panel enter">
              <div className="total-score-card">
                <div className="ts-num">{roomResult.total_score.toFixed(1)}</div>
                <div className="ts-label">/ {roomResult.max_score.toFixed(0)}점 만점</div>
                <div style={{ marginTop: '1.2rem', maxWidth: 300, margin: '1.2rem auto 0' }}>
                  <ScoreBar score={roomResult.total_score} max={roomResult.max_score} />
                </div>
              </div>

              <div className="recommend-panel" style={{ marginBottom: '1.6rem' }}>
                <div className="rp-title">AI 튜터 종합 피드백</div>
                <p>{roomResult.comprehensive_feedback}</p>
              </div>

              <div className="section-divider"><span>문항별 채점 결과</span></div>

              {roomResult.results.map((gr, i) => {
                const prob = roomProblems![i];
                const perQ = 100 / roomProblems!.length;
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
                onClick={() => { setRoomResult(null); setRoomProblems(null); setRoomAnswers([]); }}
                style={{ marginTop: '1.5rem' }}
              >
                다시 풀기
              </button>
            </div>
          )}
        </>}

        {/* ══════════ FREEFORM (기존 자유 입력 플로우) ══════════ */}
        {view === 'freeform' && <>

        {/* Upload lecture material */}
        <div className="panel">
          <label className="field-label">강의자료 업로드 (PDF · 녹음파일 · 녹화강의 영상)</label>
          <div className="input-row">
            <input
              className="text-input"
              type="file"
              accept=".pdf,.mp3,.mpeg,.mpga,.m4a,.wav,.mp4,.mov,.mkv,.avi,.webm"
              onChange={e => {
                setUploadFile(e.target.files?.[0] ?? null);
                setUploadResult(null); setUploadError(null);
              }}
            />
            <button className="btn-primary" onClick={uploadMaterial} disabled={uploading || !uploadFile}>
              {uploading ? <span className="spin" /> : '인덱싱'}
            </button>
          </div>
          <p className="hint">
            업로드하면 이 자료로 RAG 인덱스를 새로 구축합니다 (기존 인덱스는 대체됨).
            PDF는 핵심 개념도 함께 자동 추출합니다. 영상은 오디오만 자동 추출해 녹음파일처럼
            처리하고, 녹음/영상은 Whisper 전사 때문에 시간이 더 걸릴 수 있습니다. 각 25MB 이하 권장.
          </p>
          {uploadResult && (
            <div className="meta-row" style={{ marginTop: '0.8rem' }}>
              <div className="meta-chip">
                <span className="mc-label">파일</span>
                <span className="mc-value">{uploadResult.source_path}</span>
              </div>
              <div className="meta-chip">
                <span className="mc-label">인덱싱 완료</span>
                <span className="mc-value">{uploadResult.page_count}구간 · {uploadResult.chunk_count}청크</span>
              </div>
              {uploadResult.concept_count !== undefined && (
                <div className="meta-chip">
                  <span className="mc-label">핵심 개념 추출</span>
                  <span className="mc-value">{uploadResult.concept_count}개</span>
                </div>
              )}
            </div>
          )}
          {uploadError && <p className="hint" style={{ color: '#e0685a' }}>⚠ {uploadError}</p>}
        </div>

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
                <option value={20}>20문제</option>
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

        </>}

      </div>
    </div>
  );
}

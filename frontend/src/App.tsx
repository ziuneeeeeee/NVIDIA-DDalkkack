import { useState, useEffect } from 'react';
import './index.css';

/* ─── Types ───────────────────────────────────────── */
interface Problem {
  problem_id: string; type: string; question: string;
  answer?: string | null; model_answer?: string | null;
}
interface GradeDetail { point_name: string; earned_score: number; reason: string; }
interface GradeResult {
  final_score: number; max_score: number; confidence: string;
  needs_human_review: boolean; grader_agreement: string; per_criterion: GradeDetail[];
}
interface MockExamResult {
  total_score: number; max_score: number; comprehensive_feedback: string; results: GradeResult[];
}
interface IngestSummary {
  source_type: string; source_path: string; page_count: number; chunk_count: number;
  collection: string; new_concept_count?: number; total_concept_count?: number;
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
interface Attempt {
  attempt_id: string; mode: string; target_difficulty: string; submitted_at: string;
  problems: Problem[]; student_answers: string[]; grade_result: MockExamResult;
}

/* ─── Helpers ─────────────────────────────────────── */
const CATEGORY_LABEL: Record<string, string> = {
  MULTIPLE_CHOICE: '객관식', TRUE_FALSE: '참거짓', DESCRIPTIVE: '서술형', CALCULATION: '단답형',
};
const MODE_LABEL: Record<string, string> = { simple: '단순 개념 확인', mock: '모의고사' };

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

/** 채점 결과 하나를 문제/내 답안/채점 기준까지 직관적으로 펼쳐 보여주는 뷰.
 * 방금 채점한 결과와, 오답노트에서 다시 열어본 과거 시도 양쪽에서 재사용한다. */
function GradedExamView({
  problems, answers, result, onClose, closeLabel,
}: {
  problems: Problem[]; answers: string[]; result: MockExamResult;
  onClose: () => void; closeLabel: string;
}) {
  return (
    <div className="panel result-panel enter">
      <div className="total-score-card">
        <div className="ts-num">{result.total_score.toFixed(1)}</div>
        <div className="ts-label">/ {result.max_score.toFixed(0)}점 만점</div>
        <div style={{ marginTop: '1.2rem', maxWidth: 300, margin: '1.2rem auto 0' }}>
          <ScoreBar score={result.total_score} max={result.max_score} />
        </div>
      </div>

      <div className="recommend-panel" style={{ marginBottom: '1.6rem' }}>
        <div className="rp-title">AI 튜터 종합 피드백</div>
        <p>{result.comprehensive_feedback}</p>
      </div>

      <div className="section-divider"><span>문항별 상세 (문제 · 내 답안 · 채점 근거)</span></div>

      {result.results.map((gr, i) => {
        const prob = problems[i];
        const perQ = 100 / problems.length;
        const scaled = (gr.final_score / 10) * perQ;
        const pct = Math.round((scaled / perQ) * 100);
        const correctAnswer = prob.answer || prob.model_answer;
        return (
          <div key={i} className="q-block">
            <div className="crit-top">
              <span className="crit-name">Q{i + 1}. <span className={typeBadgeClass(prob.type)} style={{ marginLeft: '0.3rem' }}>{prob.type}</span></span>
              <span className={`crit-tag ${scaled >= perQ * 0.5 ? 'pos' : 'neg'}`}>
                {scaled.toFixed(1)} / {perQ.toFixed(1)}점 ({pct}%)
              </span>
            </div>

            <div className="problem-body" style={{ margin: '0.6rem 0' }}>{prob.question}</div>
            <ScoreBar score={scaled} max={perQ} />

            <div style={{ marginTop: '0.8rem' }}>
              <div className="hint" style={{ marginBottom: '0.2rem' }}>내가 쓴 답안</div>
              <div className="crit-reason" style={{ background: 'rgba(255,255,255,0.04)', padding: '0.6rem 0.8rem', borderRadius: '8px' }}>
                {answers[i] || '(답안 없음)'}
              </div>
            </div>

            {correctAnswer && (
              <div style={{ marginTop: '0.6rem' }}>
                <div className="hint" style={{ marginBottom: '0.2rem' }}>정답 / 모범답안</div>
                <div className="crit-reason" style={{ background: 'rgba(120,200,150,0.08)', padding: '0.6rem 0.8rem', borderRadius: '8px' }}>
                  {correctAnswer}
                </div>
              </div>
            )}

            {gr.per_criterion?.length > 0 && (
              <div style={{ marginTop: '0.6rem' }}>
                <div className="hint" style={{ marginBottom: '0.3rem' }}>채점 기준별 근거</div>
                {gr.per_criterion.map((c, ci) => (
                  <div key={ci} className="crit-row" style={{ padding: '0.5rem 0' }}>
                    <div className="crit-top">
                      <span className="crit-name">{c.point_name}</span>
                      <span className={`crit-tag ${c.earned_score > 0 ? 'pos' : 'neg'}`}>
                        {c.earned_score > 0 ? `+${c.earned_score}점` : '0점'}
                      </span>
                    </div>
                    <div className="crit-reason">{c.reason}</div>
                  </div>
                ))}
              </div>
            )}

            {gr.needs_human_review && (
              <p className="hint" style={{ color: '#e0a85a', marginTop: '0.5rem' }}>
                ⚠ 채점자 간 편차가 커서 사람 검토를 권장합니다 ({gr.grader_agreement})
              </p>
            )}
          </div>
        );
      })}

      <button className="btn-ghost btn-full" onClick={onClose} style={{ marginTop: '1.5rem' }}>
        {closeLabel}
      </button>
    </div>
  );
}

/* ─── App ─────────────────────────────────────────── */
export default function App() {
  /* rooms: list & create */
  const [roomList, setRoomList]               = useState<RoomSummary[]>([]);
  const [loadingRoomList, setLoadingRoomList]  = useState(false);
  const [newRoomName, setNewRoomName]          = useState('');
  const [creatingRoom, setCreatingRoom]        = useState(false);

  /* rooms: detail */
  const [currentRoom, setCurrentRoom]     = useState<RoomDetail | null>(null);
  const [renaming, setRenaming]           = useState(false);
  const [roomNameDraft, setRoomNameDraft] = useState('');

  /* rooms: upload (여러 파일 순차 업로드) */
  const [roomFiles, setRoomFiles]               = useState<File[]>([]);
  const [fileInputKey, setFileInputKey]         = useState(0);
  const [roomUploading, setRoomUploading]       = useState(false);
  const [roomUploadProgress, setRoomUploadProgress] = useState<{ done: number; total: number } | null>(null);
  const [roomUploadResult, setRoomUploadResult] = useState<IngestSummary | null>(null);
  const [roomUploadError, setRoomUploadError]   = useState<string | null>(null);

  /* rooms: quiz */
  const [roomDifficulty, setRoomDifficulty]     = useState('중');
  const [loadingRoomQ, setLoadingRoomQ]         = useState<'simple' | 'mock' | null>(null);
  const [lastQuizKind, setLastQuizKind]         = useState<'simple' | 'mock'>('mock');
  const [roomProblems, setRoomProblems]         = useState<Problem[] | null>(null);
  const [roomAnswers, setRoomAnswers]           = useState<string[]>([]);
  const [loadingRoomG, setLoadingRoomG]         = useState(false);
  const [roomResult, setRoomResult]             = useState<MockExamResult | null>(null);

  /* rooms: 오답노트 */
  const [roomAttempts, setRoomAttempts]     = useState<Attempt[]>([]);
  const [showAttempts, setShowAttempts]     = useState(false);
  const [viewingAttempt, setViewingAttempt] = useState<Attempt | null>(null);

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

  useEffect(() => { if (!currentRoom) loadRooms(); }, [currentRoom]);

  const loadAttempts = async (roomId: string) => {
    try {
      const r = await fetch(`http://localhost:8000/rooms/${roomId}/attempts`);
      const d = await r.json();
      if (r.ok) setRoomAttempts(d.attempts);
    } catch { /* ignore */ }
  };

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
    setRoomUploadResult(null); setRoomUploadError(null); setRoomFiles([]); setRenaming(false);
    setShowAttempts(false); setViewingAttempt(null);
    try {
      const r = await fetch(`http://localhost:8000/rooms/${roomId}`);
      const d = await r.json();
      if (r.ok) { setCurrentRoom(d); setRoomNameDraft(d.name); await loadAttempts(roomId); }
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
    if (roomFiles.length === 0 || !currentRoom) return;
    setRoomUploading(true); setRoomUploadResult(null); setRoomUploadError(null);
    let lastSummary: IngestSummary | null = null;

    for (let i = 0; i < roomFiles.length; i++) {
      setRoomUploadProgress({ done: i, total: roomFiles.length });
      const file = roomFiles[i];
      try {
        const formData = new FormData();
        formData.append('file', file);
        const r = await fetch(`http://localhost:8000/rooms/${currentRoom.room_id}/ingest`, { method: 'POST', body: formData });
        const d = await r.json();
        if (r.ok) { lastSummary = d; }
        else { setRoomUploadError(`${file.name}: ${d.detail || '업로드 실패'}`); break; }
      } catch { setRoomUploadError(`${file.name}: 서버 연결 오류`); break; }
    }

    setRoomUploadProgress(null);
    setRoomUploadResult(lastSummary);
    setRoomFiles([]);
    setFileInputKey(k => k + 1);
    await enterRoom(currentRoom.room_id);
    setRoomUploading(false);
  };

  const startRoomQuiz = async (kind: 'simple' | 'mock') => {
    if (!currentRoom) return;
    setLoadingRoomQ(kind); setRoomProblems(null); setRoomResult(null); setRoomAnswers([]);
    setLastQuizKind(kind);
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
    if (!roomProblems || !currentRoom) return;
    setLoadingRoomG(true); setRoomResult(null);
    try {
      const r = await fetch(`http://localhost:8000/rooms/${currentRoom.room_id}/grade`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          problems: roomProblems, student_answers: roomAnswers,
          mode: lastQuizKind, target_difficulty: roomDifficulty,
        }),
      });
      const d = await r.json();
      if (r.ok) { setRoomResult(d.result); await loadAttempts(currentRoom.room_id); }
      else alert(d.detail || '채점 실패');
    } catch { alert('서버 연결 오류'); }
    finally { setLoadingRoomG(false); }
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

        {/* ══════════ ROOM LIST ══════════ */}
        {!currentRoom && <>
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

        {/* ══════════ ROOM DETAIL ══════════ */}
        {currentRoom && <>
          <div className="panel">
            <div className="input-row" style={{ marginBottom: '0.8rem' }}>
              <button className="btn-ghost" onClick={exitRoom}>← 방 목록으로</button>
              <span style={{ flex: 1 }} />
              <button
                className={`btn-ghost ${showAttempts ? 'active' : ''}`}
                onClick={() => { setShowAttempts(s => !s); setViewingAttempt(null); }}
              >
                오답노트 {roomAttempts.length > 0 ? `(${roomAttempts.length})` : ''}
              </button>
            </div>
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

          {/* ══════════ 오답노트 ══════════ */}
          {showAttempts && !viewingAttempt && (
            <div className="panel">
              <p className="panel-title">오답노트 — 이 방에서 채점한 시도들</p>
              {roomAttempts.length === 0 && <p className="hint">아직 채점한 기록이 없습니다.</p>}
              {roomAttempts.map(a => (
                <div
                  key={a.attempt_id}
                  className="q-block"
                  style={{ cursor: 'pointer' }}
                  onClick={() => setViewingAttempt(a)}
                >
                  <div className="crit-top">
                    <span className="crit-name">{MODE_LABEL[a.mode] || a.mode} · 난이도 {a.target_difficulty}</span>
                    <span className={`crit-tag ${a.grade_result.total_score >= 50 ? 'pos' : 'neg'}`}>
                      {a.grade_result.total_score.toFixed(1)}점
                    </span>
                  </div>
                  <div className="crit-reason">
                    {a.problems.length}문항 · {new Date(a.submitted_at).toLocaleString()}
                  </div>
                </div>
              ))}
            </div>
          )}

          {viewingAttempt && (
            <GradedExamView
              problems={viewingAttempt.problems}
              answers={viewingAttempt.student_answers}
              result={viewingAttempt.grade_result}
              onClose={() => setViewingAttempt(null)}
              closeLabel="← 오답노트 목록으로"
            />
          )}

          {/* ══════════ 업로드 / 개념 / 퀴즈 (오답노트를 보고 있지 않을 때만) ══════════ */}
          {!showAttempts && <>
            <div className="panel">
              <label className="field-label">강의자료 업로드 (PDF · 녹음파일 · 녹화강의 영상, 여러 개 선택 가능)</label>
              <div className="input-row">
                <input
                  key={fileInputKey}
                  className="text-input"
                  type="file"
                  multiple
                  accept=".pdf,.mp3,.mpeg,.mpga,.m4a,.wav,.mp4,.mov,.mkv,.avi,.webm"
                  onChange={e => {
                    setRoomFiles(Array.from(e.target.files ?? []));
                    setRoomUploadResult(null); setRoomUploadError(null);
                  }}
                />
                <button className="btn-primary" onClick={uploadToRoom} disabled={roomUploading || roomFiles.length === 0}>
                  {roomUploading
                    ? <span className="spin" />
                    : roomFiles.length > 1 ? `업로드 및 분석 (${roomFiles.length}개)` : '업로드 및 분석'}
                </button>
              </div>
              <p className="hint">
                여러 파일을 한 번에 선택하면 순서대로 이 방의 인덱스에 이어붙이고, 개념을 이름
                기준으로 병합·중복제거한 뒤 문제 유형까지 자동으로 다시 매핑합니다. 나중에 파일을
                더 추가로 업로드할 수도 있습니다.
              </p>
              {roomUploadProgress && (
                <p className="hint">업로드 중… ({roomUploadProgress.done + 1}/{roomUploadProgress.total})</p>
              )}
              {roomUploadResult && (
                <div className="meta-row" style={{ marginTop: '0.8rem' }}>
                  <div className="meta-chip">
                    <span className="mc-label">마지막 파일</span>
                    <span className="mc-value">{roomUploadResult.source_path}</span>
                  </div>
                  <div className="meta-chip">
                    <span className="mc-label">누적 개념</span>
                    <span className="mc-value">{roomUploadResult.total_concept_count}개</span>
                  </div>
                </div>
              )}
              {roomUploadError && <p className="hint" style={{ color: '#e0685a' }}>⚠ {roomUploadError}</p>}
            </div>

            {currentRoom.uploads.length > 0 && (
              <div className="panel">
                <p className="panel-title">업로드된 자료 {currentRoom.uploads.length}건</p>
                {currentRoom.uploads.map((u, i) => (
                  <div key={i} className="meta-chip" style={{ marginRight: '0.5rem', marginBottom: '0.5rem', display: 'inline-flex' }}>
                    <span className="mc-label">{u.source_type}</span>
                    <span className="mc-value">{u.filename} (+{u.new_concept_count}개)</span>
                  </div>
                ))}
              </div>
            )}

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
                <p className="hint">
                  문제 개수는 핵심개념 수 기준으로 자동 결정됩니다 (직접 선택 없음).
                  단순 개념 확인은 객관식·참거짓(OX)로만, 모의고사는 개념 성격에 맞는 다양한
                  유형(서술형·계산형 포함)으로 출제되어 서로 성격이 다릅니다.
                </p>
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

            {/* Room quiz result — 방금 채점한 결과를 문제/내 답안/채점 근거까지 바로 보여줌 */}
            {roomResult && roomProblems && (
              <GradedExamView
                problems={roomProblems}
                answers={roomAnswers}
                result={roomResult}
                onClose={() => { setRoomResult(null); setRoomProblems(null); setRoomAnswers([]); }}
                closeLabel="다시 풀기"
              />
            )}
          </>}
        </>}

      </div>
    </div>
  );
}

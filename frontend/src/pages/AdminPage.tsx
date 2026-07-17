import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { X } from 'lucide-react';
import { API_BASE } from '../config';

type Tab = 'overview' | 'users' | 'persona';

const GRADE_OPTIONS = [
  { value: 'P3', label: '초등 3학년' },
  { value: 'P4', label: '초등 4학년' },
  { value: 'P5', label: '초등 5학년' },
  { value: 'P6', label: '초등 6학년' },
  { value: 'M1', label: '중학 1학년' },
  { value: 'M2', label: '중학 2학년' },
  { value: 'M3', label: '중학 3학년' },
  { value: 'H', label: '고등 공통수학' },
];

const ABILITY_PRESETS = [
  { label: '하위권 (0.3)', value: 0.3 },
  { label: '중위권 (0.5)', value: 0.5 },
  { label: '상위권 (0.8)', value: 0.8 },
];

const fmtTime = (ts: number) => new Date(ts * 1000).toLocaleString('ko-KR');

const AdminPage: React.FC = () => {
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>('overview');

  const [overview, setOverview] = useState<any>(null);
  const [users, setUsers] = useState<any[]>([]);
  // 같은 닉네임도 학년이 다르면 별개 기록이라 user_id 하나만으로는 못 고른다.
  const [selectedUser, setSelectedUser] = useState<{ user_id: string; grade: string } | null>(null);
  const [logs, setLogs] = useState<any[]>([]);
  const [examSessions, setExamSessions] = useState<any[]>([]);
  const [personas, setPersonas] = useState<any[]>([]);

  const [pName, setPName] = useState('중위권-학생A');
  const [pAbility, setPAbility] = useState(0.5);
  const [pGrade, setPGrade] = useState('M1');
  const [pCount, setPCount] = useState(20);
  const [pMode, setPMode] = useState<'simulated' | 'llm'>('simulated');
  const [running, setRunning] = useState(false);
  const [runResult, setRunResult] = useState<any>(null);

  const refresh = () => {
    axios.get(`${API_BASE}/admin/overview`).then(r => setOverview(r.data)).catch(console.error);
    axios.get(`${API_BASE}/admin/users`).then(r => setUsers(r.data.users)).catch(console.error);
    axios.get(`${API_BASE}/admin/personas`).then(r => setPersonas(r.data.personas)).catch(console.error);
  };

  useEffect(() => { refresh(); }, []);

  useEffect(() => {
    if (!selectedUser) return;
    // LLM 로그는 학년으로 안 쪼갠다 — 토큰/대화 품질 확인용이라 학년 구분 실익이 적다.
    axios.get(`${API_BASE}/admin/llm-logs`, { params: { user_id: selectedUser.user_id, limit: 50 } })
      .then(r => setLogs(r.data.logs)).catch(console.error);
    // 점수 추이는 같은 학년끼리만 비교해야 의미가 있으므로 grade를 반드시 넘긴다.
    axios.get(`${API_BASE}/admin/exam-sessions`, { params: { user_id: selectedUser.user_id, grade: selectedUser.grade } })
      .then(r => setExamSessions(r.data.sessions)).catch(console.error);
  }, [selectedUser]);

  const handleRunPersona = async () => {
    setRunning(true);
    setRunResult(null);
    try {
      const res = await axios.post(`${API_BASE}/admin/persona/run`, {
        name: pName,
        ability: pAbility,
        grade: pGrade,
        learning_count: pCount,
        mode: pMode,
      }, { timeout: 600000 });
      setRunResult(res.data);
      refresh();
    } catch (err) {
      console.error(err);
    }
    setRunning(false);
  };

  return (
    <div className="card card-exam">
      <button type="button" className="close-btn" onClick={() => navigate('/')} aria-label="처음으로">
        <X size={20} />
      </button>
      <h2>🛠️ 관리자</h2>

      <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1.5rem' }}>
        <button className={tab === 'overview' ? 'btn-primary' : 'btn-secondary'} type="button" onClick={() => { setTab('overview'); refresh(); }}>📈 개요</button>
        <button className={tab === 'users' ? 'btn-primary' : 'btn-secondary'} type="button" onClick={() => setTab('users')}>👥 사용자 & 로그</button>
        <button className={tab === 'persona' ? 'btn-primary' : 'btn-secondary'} type="button" onClick={() => setTab('persona')}>🧪 페르소나 실험</button>
      </div>

      {tab === 'overview' && overview && (
        <div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
            <div className="question-box" style={{ margin: 0, textAlign: 'center' }}>
              <div style={{ fontSize: '1.6rem', fontWeight: 700 }}>{(overview.total_prompt_tokens + overview.total_completion_tokens).toLocaleString()}</div>
              <div style={{ color: 'var(--ink-soft)' }}>총 토큰</div>
            </div>
            <div className="question-box" style={{ margin: 0, textAlign: 'center' }}>
              <div style={{ fontSize: '1.6rem', fontWeight: 700 }}>${overview.estimated_cost_usd}</div>
              <div style={{ color: 'var(--ink-soft)' }}>추정 비용 (USD)</div>
            </div>
            <div className="question-box" style={{ margin: 0, textAlign: 'center' }}>
              <div style={{ fontSize: '1.6rem', fontWeight: 700 }}>{overview.user_count}</div>
              <div style={{ color: 'var(--ink-soft)' }}>사용자 수</div>
            </div>
            <div className="question-box" style={{ margin: 0, textAlign: 'center' }}>
              <div style={{ fontSize: '1.6rem', fontWeight: 700 }}>{overview.total_attempts}</div>
              <div style={{ color: 'var(--ink-soft)' }}>총 풀이 수</div>
            </div>
          </div>

          <div className="tutor-box" style={{ marginBottom: '1.5rem' }}>
            <h3 style={{ marginTop: 0 }}>🤖 튜터 에이전트가 실제로 판단한 횟수</h3>
            {overview.tutor_agent?.total_calls > 0 ? (
              <p style={{ margin: 0 }}>
                지금까지 <strong>{overview.tutor_agent.total_calls}번</strong> 채점 후 다음 문제를 에이전트가 판단했고,
                그중 <strong>{overview.tutor_agent.topic_switches}번</strong>은 다른(더 취약한) 개념으로 전환을 추천했어요.
              </p>
            ) : (
              <p style={{ margin: 0, color: 'var(--ink-soft)' }}>
                아직 에이전트가 판단한 기록이 없어요. 학습모드에서 문제를 풀면(OPENAI_API_KEY 설정 필요) 여기 숫자가 올라가요.
              </p>
            )}
          </div>

          <h3>기능별 LLM 사용량</h3>
          {overview.usage_by_kind.length === 0 ? (
            <p style={{ color: 'var(--ink-soft)' }}>아직 LLM 호출 기록이 없어요.</p>
          ) : (
            <ul className="result-list">
              {overview.usage_by_kind.map((u: any, i: number) => (
                <li key={i}>
                  <span>{u.kind} ({u.model})</span>
                  <span>{u.calls}회 · 입력 {(u.prompt_tokens || 0).toLocaleString()} / 출력 {(u.completion_tokens || 0).toLocaleString()} 토큰</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {tab === 'users' && (
        <div>
          <h3>사용자 목록</h3>
          {users.length === 0 ? (
            <p style={{ color: 'var(--ink-soft)' }}>아직 기록이 없어요.</p>
          ) : (
            <ul className="result-list">
              {users.map((u) => {
                const isSelected = selectedUser?.user_id === u.user_id && selectedUser?.grade === u.grade;
                return (
                  <li key={`${u.user_id}::${u.grade}`} style={{ cursor: 'pointer', background: isSelected ? 'var(--bg)' : undefined }}
                      onClick={() => setSelectedUser({ user_id: u.user_id, grade: u.grade })}>
                    <span>
                      {u.persona_name ? `🧪 ${u.persona_name}` : `👤 ${u.user_id}`}
                      <span style={{ color: 'var(--ink-soft)', fontSize: '0.8rem' }}> · {u.grade}</span>
                    </span>
                    <span style={{ color: 'var(--ink-soft)', fontSize: '0.85rem' }}>
                      풀이 {u.attempt_count} · 정답률 {u.attempt_count ? Math.round((u.correct_count / u.attempt_count) * 100) : 0}%
                      {u.avg_mastery != null && ` · 평균 이해도 ${Math.round(u.avg_mastery * 100)}%`}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}

          {selectedUser && (
            <div style={{ marginTop: '1.5rem' }}>
              <h3>모의고사 점수 추이 ({selectedUser.user_id} · {selectedUser.grade})</h3>
              {examSessions.length === 0 ? (
                <p style={{ color: 'var(--ink-soft)' }}>모의고사 기록이 없어요.</p>
              ) : (
                <p style={{ fontSize: '1.2rem', fontWeight: 600 }}>
                  {examSessions.map(s => `${s.score}점`).join(' → ')}
                </p>
              )}

              <h3 style={{ marginTop: '1.5rem' }}>LLM 대화 로그 ({selectedUser.user_id}, 전체 학년, 최신순)</h3>
              {logs.length === 0 ? (
                <p style={{ color: 'var(--ink-soft)' }}>LLM 호출 기록이 없어요.</p>
              ) : (
                logs.map((l) => {
                  const isAgent = l.kind === 'tutor_agent';
                  let agentDecision: any = null;
                  if (isAgent) {
                    try { agentDecision = JSON.parse(l.response); } catch { agentDecision = null; }
                  }
                  return (
                    <div key={l.id} className="question-box" style={{ marginBottom: '1rem', borderLeft: isAgent ? '4px solid var(--coral)' : undefined }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem', fontSize: '0.85rem', color: 'var(--ink-soft)' }}>
                        <span>{isAgent ? '🤖 튜터 에이전트 판단' : `[${l.kind}]`} · {l.model} · {l.prompt_tokens}/{l.completion_tokens} 토큰</span>
                        <span>{fmtTime(l.created_at)}</span>
                      </div>
                      {l.prompt && (
                        <details>
                          <summary style={{ cursor: 'pointer', color: 'var(--ink-soft)' }}>프롬프트 보기</summary>
                          <pre style={{ whiteSpace: 'pre-wrap', fontSize: '0.8rem', background: 'var(--bg)', padding: '0.75rem', borderRadius: '8px' }}>{l.prompt}</pre>
                        </details>
                      )}
                      {isAgent && agentDecision ? (
                        <p style={{ margin: '0.5rem 0 0' }}>
                          난이도 → <strong>{agentDecision.next_difficulty}</strong>
                          {agentDecision.next_topic && <> · 개념 전환 → <strong>{agentDecision.next_topic}</strong></>}
                          {agentDecision.reasoning && <> · "{agentDecision.reasoning}"</>}
                        </p>
                      ) : (
                        <pre style={{ whiteSpace: 'pre-wrap', fontSize: '0.85rem', margin: '0.5rem 0 0' }}>{l.response}</pre>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          )}
        </div>
      )}

      {tab === 'persona' && (
        <div>
          <h3>새 페르소나 실험</h3>
          <p style={{ color: 'var(--ink-soft)', fontSize: '0.9rem' }}>
            가상 학생이 모의고사 → 학습모드 {pCount}문제 → 모의고사를 자동으로 진행하고 점수 변화를 기록해요.
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', marginBottom: '1rem' }}>
            <input type="text" value={pName} onChange={(e) => setPName(e.target.value)} placeholder="페르소나 이름" style={{ flex: '1 1 160px' }} />
            <select aria-label="실력" value={pAbility} onChange={(e) => setPAbility(Number(e.target.value))}>
              {ABILITY_PRESETS.map(a => <option key={a.value} value={a.value}>{a.label}</option>)}
            </select>
            <select aria-label="학년" value={pGrade} onChange={(e) => setPGrade(e.target.value)}>
              {GRADE_OPTIONS.map(g => <option key={g.value} value={g.value}>{g.label}</option>)}
            </select>
            <input type="number" min={5} max={100} value={pCount} onChange={(e) => setPCount(Number(e.target.value))} style={{ width: '90px' }} title="학습 문제 수" />
            <select aria-label="모드" value={pMode} onChange={(e) => { const m = e.target.value as 'simulated' | 'llm'; setPMode(m); setPCount(m === 'llm' ? 10 : 20); }}>
              <option value="simulated">⚡ 빠른 시뮬레이션 (확률 모델, 즉시)</option>
              <option value="llm">🤖 LLM 학생 에이전트 (문제를 실제로 풀어요, 수 분 소요)</option>
            </select>
          </div>
          {pMode === 'llm' && (
            <p style={{ color: 'var(--coral-deep)', fontSize: '0.85rem' }}>
              🤖 LLM 학생이 문제를 직접 읽고 답을 작성하며, 틀리면 튜터의 해설을 기억해서 다음 풀이에 반영해요.
              문제당 LLM 호출이 발생해 시간과 토큰이 소모됩니다. (API 키가 없으면 자동으로 빠른 모드로 실행)
            </p>
          )}
          <button className="btn-primary" type="button" onClick={handleRunPersona} disabled={running || !pName.trim()}>
            {running ? (pMode === 'llm' ? '🤖 LLM 학생이 문제를 풀고 있어요... (수 분 소요)' : '⏳ 시뮬레이션 중...') : '▶️ 실험 실행'}
          </button>

          {runResult && (
            <div className="tutor-box" style={{ marginTop: '1.5rem' }}>
              <h3>실행 결과: {runResult.name}</h3>
              <p style={{ fontSize: '1.3rem', fontWeight: 700 }}>
                {runResult.score_before}점 → {runResult.score_after}점
                <span style={{ color: runResult.score_delta >= 0 ? 'var(--mint-deep)' : 'var(--coral-deep)', marginLeft: '0.5rem' }}>
                  ({runResult.score_delta >= 0 ? '+' : ''}{runResult.score_delta}점)
                </span>
              </p>
              <p style={{ color: 'var(--ink-soft)' }}>
                {runResult.mode === 'llm' ? '🤖 LLM 학생 에이전트' : '⚡ 확률 시뮬레이션'} ·
                학습 {runResult.learning_count}문제
                {runResult.mode === 'llm' && ` · 해설로 배운 내용 ${runResult.lessons_learned}개`}
              </p>
              <p style={{ color: 'var(--ink-soft)' }}>
                난이도 궤적: {runResult.difficulty_trajectory.join(' → ')}
              </p>
            </div>
          )}

          <h3 style={{ marginTop: '2rem' }}>지난 실험 결과</h3>
          {personas.length === 0 ? (
            <p style={{ color: 'var(--ink-soft)' }}>아직 실험 기록이 없어요.</p>
          ) : (
            <ul className="result-list">
              {personas.map((p) => {
                const scores = p.exam_sessions.map((s: any) => s.score);
                const delta = scores.length >= 2 ? scores[scores.length - 1] - scores[0] : null;
                return (
                  <li key={p.user_id}>
                    <span>🧪 {p.name} (실력 {p.ability})</span>
                    <span>
                      {scores.length ? scores.map((s: number) => `${s}점`).join(' → ') : '기록 없음'}
                      {delta != null && (
                        <strong style={{ color: delta >= 0 ? 'var(--mint-deep)' : 'var(--coral-deep)', marginLeft: '0.5rem' }}>
                          ({delta >= 0 ? '+' : ''}{Math.round(delta * 10) / 10})
                        </strong>
                      )}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
};

export default AdminPage;

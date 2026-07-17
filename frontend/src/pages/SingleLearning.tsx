import React, { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { X } from 'lucide-react';
import { API_BASE } from '../config';
import MathText from '../components/MathText';
import { isMultiPartQuestion } from '../utils/question';
import { getNickname } from '../utils/userId';

const CIRCLED_DIGITS = ['①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧', '⑨'];
const STORAGE_KEY = 'sudal:single-learning';

interface Entry {
  entryId: string;
  question: any;
  focusTopic: string | null;
  difficultyAtStart: number;
  answer: string;
  hints: string[];
  hintIndex: number;
  hintLoading: boolean;
  grading: boolean;
  result: any | null;
  explanation: string | null;
  explaining: boolean;
}

const makeEntryId = () => `${Date.now()}-${Math.random().toString(16).slice(2)}`;

const SingleLearning: React.FC = () => {
  const { state } = useLocation();
  const navigate = useNavigate();
  // 모듈 최상단에서 읽으면 앱 부팅 시점 값(닉네임 입력 전 = 없음)이 박제되므로 렌더마다 읽는다.
  const userId = getNickname();

  const [entries, setEntries] = useState<Entry[]>([]);
  const [mastery, setMastery] = useState(0.5);
  const [difficulty, setDifficulty] = useState(state?.difficulty || 3);
  // 사용자가 입력한 개념(state.topic)과 달리, AI 튜터 에이전트가 "이 개념 대신 저걸로
  // 돌리자"고 판단하면 여기가 갱신된다. 다음 문제를 뽑을 때는 항상 이 값을 쓴다.
  const [effectiveTopic, setEffectiveTopic] = useState<string | null>(state?.topic || null);
  const [loadingNext, setLoadingNext] = useState(true);
  const [showReport, setShowReport] = useState(false);
  const feedEndRef = useRef<HTMLDivElement>(null);
  const hasFetchedInitial = useRef(false);

  const appendNextQuestion = async (currentDifficulty: number) => {
    setLoadingNext(true);
    try {
      const res = await axios.post(`${API_BASE}/single_learning/next`, {
        grade: state.grade,
        topic_name: effectiveTopic,
        current_difficulty: currentDifficulty,
        user_id: userId,
        focus_weak: !!state.focusWeak
      });
      if (res.data.question) {
        // 표시되는 이해도는 항상 "지금 푸는 개념"의 DB 누적값 하나로 통일한다.
        setMastery(res.data.topic_mastery ?? 0.5);
        setEntries(prev => [...prev, {
          entryId: makeEntryId(),
          question: res.data.question,
          focusTopic: res.data.focus_topic || null,
          difficultyAtStart: currentDifficulty,
          answer: '',
          hints: [],
          hintIndex: 0,
          hintLoading: false,
          grading: false,
          result: null,
          explanation: null,
          explaining: false,
        }]);
      }
    } catch (err) {
      console.error(err);
    }
    setLoadingNext(false);
  };

  useEffect(() => {
    if (!state || !userId) {
      navigate('/');
      return;
    }

    const saved = sessionStorage.getItem(STORAGE_KEY);
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        if (
          parsed.grade === state.grade &&
          parsed.topic === (state.topic || null) &&
          Array.isArray(parsed.entries) &&
          parsed.entries.length > 0
        ) {
          setEntries(parsed.entries);
          setMastery(parsed.mastery ?? 0.5);
          setDifficulty(parsed.difficulty ?? (state.difficulty || 3));
          setEffectiveTopic(parsed.effectiveTopic ?? (state.topic || null));
          setLoadingNext(false);
          return;
        }
      } catch {
        // ignore malformed saved state
      }
    }

    if (hasFetchedInitial.current) return;
    hasFetchedInitial.current = true;
    appendNextQuestion(difficulty);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state, navigate, userId]);

  useEffect(() => {
    if (!state || entries.length === 0) return;
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
      grade: state.grade,
      topic: state.topic || null,
      entries, mastery, difficulty, effectiveTopic
    }));
  }, [state, entries, mastery, difficulty, effectiveTopic]);

  useEffect(() => {
    feedEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [entries.length, loadingNext]);

  const updateEntry = (entryId: string, patch: Partial<Entry>) => {
    setEntries(prev => prev.map(e => (e.entryId === entryId ? { ...e, ...patch } : e)));
  };

  const handleGrade = async (entry: Entry) => {
    if (!entry.answer.trim()) return;
    updateEntry(entry.entryId, { grading: true });
    try {
      const res = await axios.post(`${API_BASE}/single_learning/grade`, {
        user_answer: entry.answer,
        correct_answer: entry.question.answer_text,
        current_mastery: mastery,
        current_difficulty: entry.difficultyAtStart,
        question_text: entry.question.question_text,
        question_id: entry.question.id,
        grade: entry.question.grade || state.grade,
        topic_name: entry.question.topic_name,
        sector1: entry.question.sector1,
        sector2: entry.question.sector2,
        hint_used: entry.hintIndex > 0,
        user_id: userId
      });

      updateEntry(entry.entryId, { result: res.data, grading: false });
      setDifficulty(res.data.next_difficulty);
      setMastery(res.data.topic_mastery ?? res.data.new_mastery);
      // AI 튜터 에이전트가 다른 개념으로 돌리라고 판단했으면 다음 문제부터 반영한다.
      if (res.data.next_topic) {
        setEffectiveTopic(res.data.next_topic);
      }

      if (!res.data.is_correct) {
        updateEntry(entry.entryId, { explaining: true });
        try {
          const explainRes = await axios.post(`${API_BASE}/single_learning/explain`, {
            correct_answer: entry.question.answer_text,
            current_mastery: mastery,
            question_text: entry.question.question_text,
            user_id: userId
          });
          updateEntry(entry.entryId, { explanation: explainRes.data.explanation, explaining: false });
        } catch (err) {
          console.error(err);
          updateEntry(entry.entryId, { explaining: false });
        }
      }
    } catch (err) {
      console.error(err);
      updateEntry(entry.entryId, { grading: false });
    }
  };

  const handleNext = () => {
    appendNextQuestion(difficulty);
  };

  const handleGetHint = async (entry: Entry) => {
    if (entry.hints.length === 0) {
      updateEntry(entry.entryId, { hintLoading: true });
      try {
        const res = await axios.get(`${API_BASE}/single_learning/hint?answer_text=${encodeURIComponent(entry.question.answer_text)}&question_text=${encodeURIComponent(entry.question.question_text || '')}&user_id=${encodeURIComponent(userId ?? '')}`);
        updateEntry(entry.entryId, { hints: res.data.hints, hintIndex: 1, hintLoading: false });
      } catch (err) {
        console.error(err);
        updateEntry(entry.entryId, { hintLoading: false });
      }
    } else if (entry.hintIndex < entry.hints.length) {
      updateEntry(entry.entryId, { hintIndex: entry.hintIndex + 1 });
    }
  };

  const handleStop = () => {
    sessionStorage.removeItem(STORAGE_KEY);
    navigate('/');
  };

  if (entries.length === 0 && loadingNext) {
    return <div className="card"><h2>문제를 불러오는 중...</h2></div>;
  }
  if (entries.length === 0) {
    return (
      <div className="card">
        <h2>더 이상 문제가 없습니다.</h2>
        <button className="btn-primary" onClick={handleStop}>처음으로</button>
      </div>
    );
  }

  const answeredEntries = entries.filter(e => e.result);
  const correctCount = answeredEntries.filter(e => e.result.is_correct).length;
  const accuracy = answeredEntries.length ? Math.round((correctCount / answeredEntries.length) * 100) : 0;
  const topicBreakdown = answeredEntries.reduce((acc: Record<string, { correct: number; total: number }>, e) => {
    const key = e.question.topic_name || e.question.sector2 || '기타';
    if (!acc[key]) acc[key] = { correct: 0, total: 0 };
    acc[key].total += 1;
    if (e.result.is_correct) acc[key].correct += 1;
    return acc;
  }, {});

  return (
    <div className="card card-exam">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h2>학습모드</h2>
        <span className="badge">
          현재 난이도: {difficulty} | 이 개념 이해도: {Math.round(mastery * 100)}%
        </span>
      </div>

      <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1.5rem' }}>
        <button className="btn-secondary" type="button" onClick={() => setShowReport(true)}>
          📊 학습 리포트
        </button>
        <button className="btn-secondary" type="button" onClick={handleStop}>
          🛑 학습 중지
        </button>
      </div>

      <div className="chat-feed">
        {entries.map((entry, idx) => {
          const isLast = idx === entries.length - 1;
          return (
            <div key={entry.entryId} className={`chat-entry ${entry.result ? 'answered' : ''}`}>
              <div className="chat-entry-meta">
                {idx + 1}번째 문제 · 난이도 {entry.question.difficulty}
                {entry.focusTopic && ` · 🎯 취약 개념 집중: ${entry.focusTopic}`}
              </div>

              <div className="question-box">
                <img
                  src={`${API_BASE}/images/${entry.question.id}.png`}
                  alt={entry.question.question_text || '문제'}
                  className="question-image"
                />
              </div>

              {!entry.result ? (
                <>
                  {entry.question.options ? (
                    <div className="mcq-options">
                      {entry.question.options.map(([num, text]: [number, string]) => (
                        <button
                          key={num}
                          type="button"
                          className={`mcq-option ${entry.answer === String(num) ? 'selected' : ''}`}
                          onClick={() => updateEntry(entry.entryId, { answer: String(num) })}
                        >
                          <span className="mcq-radio" />
                          <span className="mcq-num">{CIRCLED_DIGITS[num - 1] || num}</span>
                          <MathText text={text} style={{ display: 'inline' }} />
                        </button>
                      ))}
                    </div>
                  ) : (
                    <div className="input-group">
                      {isMultiPartQuestion(entry.question.question_text) && (
                        <p className="input-hint">📝 답이 여러 개인 문제예요. "(1) 정답1 (2) 정답2"처럼 번호를 붙여서 입력해주세요.</p>
                      )}
                      <input
                        type="text"
                        placeholder={isMultiPartQuestion(entry.question.question_text) ? '예: (1) 6  (2) 10' : '정답을 입력하세요'}
                        value={entry.answer}
                        onChange={(e) => updateEntry(entry.entryId, { answer: e.target.value })}
                      />
                    </div>
                  )}

                  <div style={{ display: 'flex', gap: '1rem' }}>
                    <button className="btn-primary" onClick={() => handleGrade(entry)} disabled={entry.grading || !entry.answer.trim()}>
                      {entry.grading ? '⏳ 채점중입니다...' : '✅ 정답 제출'}
                    </button>
                    <button className="btn-secondary" onClick={() => handleGetHint(entry)} disabled={entry.hintLoading || (entry.hintIndex >= 3 && entry.hints.length > 0)}>
                      {entry.hintLoading ? '💭 힌트 만드는 중...' : entry.hints.length === 0 ? '💡 힌트 보기' : `💡 힌트 보기 (${entry.hintIndex}/3)`}
                    </button>
                  </div>

                  {(entry.hintLoading || (entry.hintIndex > 0 && entry.hints.length > 0)) && (
                    <div className="hint-box">
                      {entry.hintLoading ? (
                        <p>🦦 수달이가 힌트를 만들고 있어요...</p>
                      ) : (
                        entry.hints.slice(0, entry.hintIndex).map((h, i) => (
                          <MathText key={i} text={h} style={{ marginBottom: '0.5rem' }} />
                        ))
                      )}
                    </div>
                  )}
                </>
              ) : (
                <>
                  <div className={`result-banner ${entry.result.is_correct ? 'correct' : 'incorrect'}`}>
                    {entry.result.is_correct ? '🦦 정답입니다! 잘 하셨어요.' : '아쉽지만 오답입니다.'}
                  </div>

                  {entry.result.used_agent ? (
                    <>
                      {entry.result.agent_reasoning && (
                        <p style={{ margin: '0.5rem 0', fontWeight: 600, color: 'var(--coral-deep)' }}>
                          🤖 {entry.result.agent_reasoning}
                        </p>
                      )}
                      {entry.result.next_topic && (
                        <p style={{ margin: '0.5rem 0', fontSize: '0.85rem', color: 'var(--ink-soft)' }}>
                          🔀 다음 문제부터 "{entry.result.next_topic}" 개념으로 바꿔서 추천할게요.
                        </p>
                      )}
                    </>
                  ) : (
                    <>
                      {typeof entry.result.streak === 'number' && entry.result.streak >= 3 && (
                        <p style={{ margin: '0.5rem 0', fontWeight: 600, color: 'var(--coral-deep)' }}>
                          🔥 {entry.result.streak}연속 정답! 난이도를 한 단계 더 올려볼게요.
                        </p>
                      )}
                      {typeof entry.result.streak === 'number' && entry.result.streak <= -3 && (
                        <p style={{ margin: '0.5rem 0', fontWeight: 600, color: 'var(--ink-soft)' }}>
                          🌊 이 개념이 계속 헷갈리는군요. 난이도를 크게 낮춰서 기초부터 다시 짚어볼게요.
                        </p>
                      )}
                    </>
                  )}

                  {!entry.result.is_correct && (entry.explaining || entry.explanation) && (
                    <div className="tutor-box">
                      <h3>💬 AI 튜터 맞춤 설명</h3>
                      {entry.explaining ? (
                        <p>🦦 수달이가 맞춤 해설을 준비하고 있어요...</p>
                      ) : (
                        <MathText text={entry.explanation || ''} />
                      )}
                    </div>
                  )}

                  {isLast && (
                    <button className="btn-primary" style={{ marginTop: '1.5rem' }} onClick={handleNext} disabled={loadingNext}>
                      {loadingNext ? '⏳ 다음 문제 불러오는 중...' : `다음 문제 풀기 (난이도 ${difficulty})`}
                    </button>
                  )}
                </>
              )}
            </div>
          );
        })}
        <div ref={feedEndRef} />
      </div>

      {showReport && (
        <div className="report-overlay" onClick={() => setShowReport(false)}>
          <div className="report-panel" onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h2 style={{ margin: 0 }}>📊 학습 리포트</h2>
              <button type="button" className="close-btn" style={{ position: 'static' }} onClick={() => setShowReport(false)} aria-label="닫기">
                <X size={20} />
              </button>
            </div>

            <p>
              이번 세션에서 <strong>{answeredEntries.length}문제</strong> 중 <strong>{correctCount}문제</strong> 맞혔어요.
              (정답률 {accuracy}%)
            </p>
            <p>
              지금 푸는 개념 이해도: <strong>{Math.round(mastery * 100)}%</strong> · 현재 난이도: <strong>{difficulty}</strong>
            </p>

            <div style={{ margin: '1.25rem 0' }}>
              <h3>난이도 변화</h3>
              <p style={{ color: 'var(--ink-soft)', margin: 0 }}>
                {answeredEntries.length ? answeredEntries.map(e => e.question.difficulty).join(' → ') : '아직 푼 문제가 없어요.'}
              </p>
            </div>

            <div>
              <h3>개념별 정답 현황</h3>
              {Object.keys(topicBreakdown).length === 0 ? (
                <p style={{ color: 'var(--ink-soft)' }}>아직 푼 문제가 없어요.</p>
              ) : (
                <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                  {Object.entries(topicBreakdown).map(([topic, stat]) => (
                    <li key={topic} style={{ display: 'flex', justifyContent: 'space-between', padding: '0.4rem 0' }}>
                      <span>{topic}</span>
                      <span>{stat.correct}/{stat.total}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <button
              className="btn-secondary"
              style={{ marginTop: '1.5rem', width: '100%' }}
              onClick={() => navigate('/wrong-notes', { state: { grade: state.grade } })}
            >
              📒 전체 학습 기록 보기
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default SingleLearning;

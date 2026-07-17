import React, { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { X } from 'lucide-react';
import { API_BASE } from '../config';
import MathText from '../components/MathText';
import { getNickname } from '../utils/userId';

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

const masteryColor = (mastery: number) => {
  if (mastery >= 0.65) return '#63C9A0';
  if (mastery >= 0.4) return '#F3C255';
  return '#E9683F';
};

const WrongNotes: React.FC = () => {
  const navigate = useNavigate();
  const { state } = useLocation();
  // 모듈 최상단이 아니라 렌더 시점에 읽어야 닉네임 입력 직후에도 올바른 값이 잡힌다.
  const userId = getNickname();
  const [grade, setGrade] = useState(() => state?.grade || localStorage.getItem('sudal:last-input:grade') || 'M1');
  const [topics, setTopics] = useState<any[]>([]);
  const [dueTopics, setDueTopics] = useState<any[]>([]);
  const [wrongQuestions, setWrongQuestions] = useState<any[]>([]);
  const [explanations, setExplanations] = useState<Record<string, string>>({});
  const [explainingId, setExplainingId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // 닉네임이 없으면 학습 기록도 있을 수 없으므로 랜딩으로 돌려보낸다(주소창 직접 진입 대비).
    if (!userId) {
      navigate('/');
      return;
    }

    let cancelled = false;
    setLoading(true);
    Promise.all([
      axios.get(`${API_BASE}/report/topic-mastery`, { params: { user_id: userId, grade } }),
      axios.get(`${API_BASE}/review/due`, { params: { user_id: userId, grade } }),
      axios.get(`${API_BASE}/review/wrong-questions`, { params: { user_id: userId, grade } }),
    ]).then(([topicRes, dueRes, wrongRes]) => {
      if (cancelled) return;
      setTopics(topicRes.data.topics || []);
      setDueTopics(dueRes.data.topics || []);
      setWrongQuestions(wrongRes.data.questions || []);
    }).catch(err => console.error(err))
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [grade, userId, navigate]);

  const handlePractice = (topicName?: string | null) => {
    navigate('/single-learning', { state: { grade, topic: topicName || '', difficulty: 2, focusWeak: !topicName } });
  };

  const handleExplain = async (q: any) => {
    if (explanations[q.id] || explainingId === q.id) return;
    setExplainingId(q.id);
    try {
      const res = await axios.post(`${API_BASE}/single_learning/explain`, {
        correct_answer: q.answer_text,
        current_mastery: 0.5,
        question_text: q.question_text,
        user_id: userId,
      });
      setExplanations(prev => ({ ...prev, [q.id]: res.data.explanation }));
    } catch (err) {
      console.error(err);
    }
    setExplainingId(null);
  };

  return (
    <div className="card card-exam">
      <button type="button" className="close-btn" onClick={() => navigate('/')} aria-label="처음으로">
        <X size={20} />
      </button>
      <h2>오답노트 & 취약점 리포트</h2>

      <div className="input-card" style={{ marginBottom: '1.5rem' }}>
        <select aria-label="학년 선택" value={grade} onChange={(e) => setGrade(e.target.value)}>
          {GRADE_OPTIONS.map((g) => (
            <option key={g.value} value={g.value}>{g.label}</option>
          ))}
        </select>
      </div>

      {loading ? (
        <p>불러오는 중...</p>
      ) : (
        <>
          {dueTopics.length > 0 && (
            <div style={{ marginBottom: '2rem' }}>
              <h3>🔔 지금 복습하면 좋은 개념</h3>
              <ul className="result-list">
                {dueTopics.map((t) => (
                  <li key={t.topic_key}>
                    <span>{t.topic_key} <span style={{ color: 'var(--ink-soft)', fontSize: '0.85rem' }}>(이해도 {Math.round(t.mastery * 100)}%)</span></span>
                    <button className="mini-btn" type="button" onClick={() => handlePractice(t.topic_key)}>복습하기</button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div style={{ marginBottom: '2rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3>개념별 이해도</h3>
              <button className="btn-secondary" type="button" onClick={() => handlePractice(null)}>
                🎯 약점 집중 학습 시작
              </button>
            </div>
            {topics.length === 0 ? (
              <p style={{ color: 'var(--ink-soft)' }}>아직 쌓인 학습 기록이 없어요. 문제를 몇 개 풀어보면 여기에 나타나요.</p>
            ) : (
              <ul className="result-list" style={{ listStyle: 'none', padding: 0 }}>
                {topics.map((t) => (
                  <li key={t.topic_key} style={{ display: 'block', padding: '0.6rem 0' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.3rem' }}>
                      <span>{t.topic_key}</span>
                      <span>{Math.round(t.mastery * 100)}% ({t.correct_count}/{t.attempt_count})</span>
                    </div>
                    <div style={{ background: '#eee', borderRadius: '6px', height: '8px', overflow: 'hidden' }}>
                      <div style={{
                        width: `${Math.round(t.mastery * 100)}%`,
                        background: masteryColor(t.mastery),
                        height: '100%',
                      }} />
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div>
            <h3>오답노트</h3>
            {wrongQuestions.length === 0 ? (
              <p style={{ color: 'var(--ink-soft)' }}>아직 틀린 문제가 없어요. 잘하고 있어요!</p>
            ) : (
              wrongQuestions.map((q, idx) => (
                <div key={q.id} className="question-box" style={{ marginTop: idx === 0 ? 0 : '1.5rem' }}>
                  <div style={{ marginBottom: '1rem', fontWeight: 600, display: 'flex', justifyContent: 'space-between' }}>
                    <span>{q.topic_name} (난이도: {q.difficulty})</span>
                    <button className="mini-btn" type="button" onClick={() => handlePractice(q.topic_name)}>비슷한 문제 풀기</button>
                  </div>
                  <img
                    src={`${API_BASE}/images/${q.id}.png`}
                    alt={q.question_text || '문제'}
                    className="question-image"
                    style={{ marginBottom: '1rem' }}
                  />
                  <div className="tutor-box">
                    <h3>💬 풀이</h3>
                    <MathText text={q.answer_text} />
                  </div>
                  <button className="btn-secondary" style={{ marginTop: '1rem' }} type="button" onClick={() => handleExplain(q)}>
                    🦦 맞춤 설명 보기
                  </button>
                  {(explanations[q.id] || explainingId === q.id) && (
                    <div className="tutor-box" style={{ marginTop: '1rem' }}>
                      <h3>🦦 AI 튜터 맞춤 설명</h3>
                      {explanations[q.id] ? (
                        <MathText text={explanations[q.id]} />
                      ) : (
                        <p>🦦 수달이가 맞춤 해설을 준비하고 있어요...</p>
                      )}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </>
      )}
    </div>
  );
};

export default WrongNotes;

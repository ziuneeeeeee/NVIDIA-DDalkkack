import React, { useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { X } from 'lucide-react';
import { API_BASE } from '../config';
import MathText from '../components/MathText';

const CIRCLED_DIGITS = ['①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧', '⑨'];

const ResultReport: React.FC = () => {
  const { state } = useLocation();
  const navigate = useNavigate();
  const [showReview, setShowReview] = useState(false);
  const [reviewLoaded, setReviewLoaded] = useState(false);
  const [explanations, setExplanations] = useState<Record<string, string>>({});
  const [explainingId, setExplainingId] = useState<string | null>(null);

  if (!state || !state.results) {
    return <div className="card">결과가 없습니다.</div>;
  }

  const { score, results, questions, grade, answers } = state;

  const handleStartSingleLearning = () => {
    // topic을 비워서 백엔드가 이번 모의고사에서 쌓인 취약 개념(topic_mastery)에
    // 가중치를 두고 다음 문제를 골라주도록 한다.
    navigate('/single-learning', { state: { grade, topic: '', difficulty: 2, focusWeak: true } });
  };

  const handleToggleReview = async () => {
    const next = !showReview;
    setShowReview(next);
    if (!next || reviewLoaded) return;
    setReviewLoaded(true);

    const wrongQuestions = questions.filter((q: any) => {
      const r = results.find((x: any) => x.question_id === q.id);
      return r && !r.is_correct;
    });

    for (const q of wrongQuestions) {
      setExplainingId(q.id);
      try {
        const res = await axios.post(`${API_BASE}/single_learning/explain`, {
          correct_answer: q.answer_text,
          current_mastery: 0.5,
          question_text: q.question_text
        });
        setExplanations(prev => ({ ...prev, [q.id]: res.data.explanation }));
      } catch (err) {
        console.error(err);
      }
    }
    setExplainingId(null);
  };

  return (
    <div className="card card-exam">
      <button type="button" className="close-btn" onClick={() => navigate('/')} aria-label="처음으로">
        <X size={20} />
      </button>
      <h2>모의고사 결과 리포트</h2>

      <div style={{ textAlign: 'center', margin: '2rem 0' }}>
        <h1 style={{ fontSize: '4rem', margin: 0, color: 'var(--coral-deep)' }}>{score}점</h1>
        <p style={{ color: 'var(--ink-soft)' }}>100점 만점</p>
      </div>

      <div style={{ marginBottom: '2rem' }}>
        <h3>문항별 결과</h3>
        <ul className="result-list">
          {results.map((r: any, idx: number) => {
            const q = questions.find((x: any) => x.id === r.question_id);
            return (
              <li key={r.question_id}>
                <span>{idx + 1}번 문항 (난이도: {q?.difficulty})</span>
                <span className={r.is_correct ? 'result-correct' : 'result-incorrect'}>
                  {r.is_correct ? '정답' : '오답'}
                </span>
              </li>
            );
          })}
        </ul>
      </div>

      <div className="btn-row">
        <button className="btn-secondary" onClick={handleToggleReview}>
          🔍 {showReview ? '다시보기 닫기' : '다시보기'}
        </button>
        <button className="btn-primary" onClick={handleStartSingleLearning}>
          🎚️ 취약개념 맞춤 학습모드 시작
        </button>
        <button className="btn-secondary" onClick={() => navigate('/wrong-notes', { state: { grade } })}>
          📒 오답노트 전체보기
        </button>
      </div>

      {showReview && (
        <div style={{ marginTop: '2rem' }}>
          {questions.map((q: any, idx: number) => {
            const r = results.find((x: any) => x.question_id === q.id);
            const userAnswer = answers?.[q.id];
            return (
              <div key={q.id} className="question-box" style={{ marginTop: idx === 0 ? 0 : '1.5rem' }}>
                <div style={{ marginBottom: '1rem', fontWeight: 600, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span>{idx + 1}번 (난이도: {q.difficulty})</span>
                  <span className={r?.is_correct ? 'result-correct' : 'result-incorrect'}>
                    {r?.is_correct ? '정답' : '오답'}
                  </span>
                </div>

                <img
                  src={`${API_BASE}/images/${q.id}.png`}
                  alt={q.question_text || `문항 ${idx + 1}`}
                  className="question-image"
                  style={{ marginBottom: '1rem' }}
                />

                {userAnswer && (
                  <p style={{ marginBottom: '1rem', color: 'var(--ink-soft)' }}>
                    제출한 답: {q.options ? (CIRCLED_DIGITS[Number(userAnswer) - 1] || userAnswer) : userAnswer}
                  </p>
                )}

                <div className="tutor-box">
                  <h3>💬 풀이</h3>
                  <MathText text={q.answer_text} />
                </div>

                {!r?.is_correct && (explanations[q.id] || explainingId === q.id) && (
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
            );
          })}
        </div>
      )}
    </div>
  );
};

export default ResultReport;

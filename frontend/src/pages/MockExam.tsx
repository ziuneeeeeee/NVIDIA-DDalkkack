import React, { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { X } from 'lucide-react';
import { API_BASE } from '../config';
import MathText from '../components/MathText';
import { isMultiPartQuestion } from '../utils/question';
import { getNickname } from '../utils/userId';

const CIRCLED_DIGITS = ['①', '②', '③', '④', '⑤', '⑥', '⑦', '⑧', '⑨'];
const STORAGE_KEY = 'sudal:mock-exam';

const MockExam: React.FC = () => {
  const { state } = useLocation();
  const navigate = useNavigate();
  const [questions, setQuestions] = useState<any[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!state) {
      navigate('/');
      return;
    }

    const saved = sessionStorage.getItem(STORAGE_KEY);
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        if (parsed.grade === state.grade && parsed.topic === (state.topic || null)) {
          setQuestions(parsed.questions || []);
          setAnswers(parsed.answers || {});
          setLoading(false);
          return;
        }
      } catch {
        // ignore malformed saved state
      }
    }

    axios.post(`${API_BASE}/mock_exam/generate`, {
      grade: state.grade,
      topic_name: state.topic || null
    }).then(res => {
      setQuestions(res.data.questions);
      setLoading(false);
    }).catch(err => {
      console.error(err);
      setLoading(false);
    });
  }, [state, navigate]);

  useEffect(() => {
    if (!state || questions.length === 0) return;
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
      grade: state.grade,
      topic: state.topic || null,
      questions, answers
    }));
  }, [state, questions, answers]);

  const handleSubmit = async () => {
    const formattedAnswers = questions.map((q: any) => ({
      question_id: q.id,
      user_answer: answers[q.id] || '',
      correct_answer: q.answer_text,
      question_text: q.question_text
    }));

    try {
      const res = await axios.post(`${API_BASE}/mock_exam/grade`, {
        answers: formattedAnswers,
        user_id: getNickname(),
        grade: state.grade
      });
      sessionStorage.removeItem(STORAGE_KEY);
      navigate('/result-report', { state: { ...state, results: res.data.results, score: res.data.score, questions, answers } });
    } catch(err) {
      console.error(err);
    }
  };

  if (loading) return <div className="card"><h2>문제를 구성하고 있습니다...</h2></div>;

  return (
    <div className="card card-exam">
      <button type="button" className="close-btn" onClick={() => { sessionStorage.removeItem(STORAGE_KEY); navigate('/'); }} aria-label="처음으로">
        <X size={20} />
      </button>
      <h2>모의고사 (10문항)</h2>
      {questions.map((q, idx) => (
        <div key={q.id} className="question-box">
          <div style={{ marginBottom: '1rem', fontWeight: 600 }}>
            {idx + 1}번
            <span style={{ fontSize: '0.875rem', color: 'var(--ink-soft)', marginLeft: '1rem' }}>
              (난이도: {q.difficulty})
            </span>
          </div>
          <img
            src={`${API_BASE}/images/${q.id}.png`}
            alt={q.question_text || `문항 ${idx + 1}`}
            className="question-image"
            style={{ marginBottom: '1rem' }}
          />
          {q.options ? (
            <div className="mcq-options">
              {q.options.map(([num, text]: [number, string]) => (
                <button
                  key={num}
                  type="button"
                  className={`mcq-option ${answers[q.id] === String(num) ? 'selected' : ''}`}
                  onClick={() => setAnswers({ ...answers, [q.id]: String(num) })}
                >
                  <span className="mcq-radio" />
                  <span className="mcq-num">{CIRCLED_DIGITS[num - 1] || num}</span>
                  <MathText text={text} style={{ display: 'inline' }} />
                </button>
              ))}
            </div>
          ) : (
            <>
              {isMultiPartQuestion(q.question_text) && (
                <p className="input-hint">📝 답이 여러 개인 문제예요. "(1) 정답1 (2) 정답2"처럼 번호를 붙여서 입력해주세요.</p>
              )}
              <input
                type="text"
                placeholder={isMultiPartQuestion(q.question_text) ? '예: (1) 6  (2) 10' : '정답을 입력하세요'}
                value={answers[q.id] || ''}
                onChange={(e) => setAnswers({ ...answers, [q.id]: e.target.value })}
              />
            </>
          )}
        </div>
      ))}
      
      <button className="btn-primary" onClick={handleSubmit}>
        ✅ 채점하기
      </button>
    </div>
  );
};

export default MockExam;

import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { X } from 'lucide-react';
import { API_BASE } from '../config';
import { getNickname, setNickname as saveNickname, validateNickname, MAX_NICKNAME_LENGTH } from '../utils/userId';

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

const STORAGE_KEY = 'sudal:last-input';

const InputForm: React.FC = () => {
  const [grade, setGrade] = useState(() => localStorage.getItem(`${STORAGE_KEY}:grade`) || 'M1');
  const [topic, setTopic] = useState(() => localStorage.getItem(`${STORAGE_KEY}:topic`) || '');
  const [checking, setChecking] = useState(false);
  const [topicWarning, setTopicWarning] = useState<'exam' | 'single' | null>(null);
  const [dueTopics, setDueTopics] = useState<any[]>([]);
  const [nickname, setNicknameState] = useState<string | null>(() => getNickname());

  // 닉네임이 없으면 닫을 수 없는 게이트로 뜬다. 닉네임이 생긴 뒤(변경 목적)엔 닫을 수 있다.
  const [showModal, setShowModal] = useState(() => !getNickname());
  const [modalNickname, setModalNickname] = useState(() => getNickname() ?? '');
  const [modalGrade, setModalGrade] = useState(() => localStorage.getItem(`${STORAGE_KEY}:grade`) || 'M1');
  const [modalError, setModalError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    localStorage.setItem(`${STORAGE_KEY}:grade`, grade);
  }, [grade]);

  useEffect(() => {
    localStorage.setItem(`${STORAGE_KEY}:topic`, topic);
  }, [topic]);

  useEffect(() => {
    if (!nickname) {
      setDueTopics([]);
      return;
    }
    axios.get(`${API_BASE}/review/due`, { params: { user_id: nickname, grade } })
      .then(res => setDueTopics(res.data.topics || []))
      .catch(() => setDueTopics([]));
  }, [grade, nickname]);

  // 랜딩 진입 시 게이트를 통과해야만 여기까지 오므로 닉네임은 항상 있다고 봐도 된다.
  const proceed = (action: 'exam' | 'single') => {
    if (action === 'exam') {
      navigate('/mock-exam', { state: { grade, topic } });
    } else {
      navigate('/single-learning', { state: { grade, topic, difficulty: 3 } });
    }
  };

  const attemptStart = async (action: 'exam' | 'single') => {
    setTopicWarning(null);
    if (!topic.trim()) {
      proceed(action);
      return;
    }

    setChecking(true);
    try {
      const res = await axios.post(`${API_BASE}/topic/check`, { grade, topic_name: topic });
      if (res.data.matched) {
        proceed(action);
      } else {
        setTopicWarning(action);
      }
    } catch (err) {
      console.error(err);
      proceed(action); // don't block the student over a network hiccup
    }
    setChecking(false);
  };

  const openChangeModal = () => {
    setModalNickname(nickname ?? '');
    setModalGrade(grade);
    setModalError(null);
    setShowModal(true);
  };

  const handleModalSubmit = () => {
    const error = validateNickname(modalNickname);
    if (error) {
      setModalError(error);
      return;
    }
    const name = modalNickname.trim();
    const changed = name !== nickname || modalGrade !== grade;

    saveNickname(name);
    setNicknameState(name);
    setGrade(modalGrade);

    // 신원이 실제로 바뀐 경우에만 진행 중이던 화면 상태를 버린다. 서버의 학습 기록은
    // 그대로 남아서, 같은 닉네임으로 다시 들어오면 이어서 공부할 수 있다.
    if (changed) {
      sessionStorage.removeItem('sudal:single-learning');
      sessionStorage.removeItem('sudal:mock-exam');
      setTopic('');
      setTopicWarning(null);
    }
    setShowModal(false);
  };

  return (
    <>
      {showModal && (
        <div className="report-overlay" onClick={() => { if (nickname) setShowModal(false); }}>
          <div className="report-panel" style={{ maxWidth: '380px' }} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
              <h2 style={{ margin: 0 }}>{nickname ? '🦦 내 정보 바꾸기' : '🦦 반가워요!'}</h2>
              {/* 첫 방문(닉네임 없음)엔 닫기 없이 반드시 입력받고, 변경 목적일 때만 닫을 수 있다. */}
              {nickname && (
                <button type="button" className="close-btn" style={{ position: 'static' }} onClick={() => setShowModal(false)} aria-label="닫기">
                  <X size={20} />
                </button>
              )}
            </div>
            <p style={{ color: 'var(--ink-soft)', fontSize: '0.9rem' }}>
              {nickname
                ? '이름이나 학년을 바꾸면 지금 보던 화면은 초기화돼요. 학습 기록은 그대로 남아있어요.'
                : '학습 기록을 저장하려면 이름이 필요해요. 다음에 같은 이름으로 오면 이어서 공부할 수 있어요.'}
            </p>

            <label htmlFor="nickname-input" style={{ fontSize: '0.85rem', color: 'var(--ink-soft)' }}>닉네임</label>
            <input
              id="nickname-input"
              type="text"
              autoFocus
              value={modalNickname}
              maxLength={MAX_NICKNAME_LENGTH}
              onChange={(e) => { setModalNickname(e.target.value); setModalError(null); }}
              onKeyDown={(e) => { if (e.key === 'Enter') handleModalSubmit(); }}
              placeholder="닉네임을 입력해주세요"
              style={{ width: '100%' }}
            />

            <label htmlFor="grade-select" style={{ fontSize: '0.85rem', color: 'var(--ink-soft)', display: 'block', marginTop: '1rem' }}>학년</label>
            <select
              id="grade-select"
              value={modalGrade}
              onChange={(e) => setModalGrade(e.target.value)}
              style={{ width: '100%' }}
            >
              {GRADE_OPTIONS.map((g) => (
                <option key={g.value} value={g.value}>{g.label}</option>
              ))}
            </select>

            {modalError && (
              <p style={{ color: 'var(--coral-deep)', fontSize: '0.85rem', margin: '0.5rem 0 0' }}>{modalError}</p>
            )}
            <button className="btn-primary" style={{ marginTop: '1.25rem', width: '100%' }} type="button" onClick={handleModalSubmit}>
              {nickname ? '저장하기' : '시작하기'}
            </button>
          </div>
        </div>
      )}

      <header className="landing-header">
        <div className="landing-logo"><span className="logo-dot"></span>수달이</div>
        <nav className="landing-nav">
          <a href="#modes">시작하기</a>
          <a href="#flow">어떻게 도와줘요?</a>
          <a href="/wrong-notes" onClick={(e) => { e.preventDefault(); navigate('/wrong-notes', { state: { grade } }); }}>오답노트</a>
          {nickname && (
            <a href="#change" onClick={(e) => { e.preventDefault(); openChangeModal(); }}>
              🦦 {nickname} · {GRADE_OPTIONS.find((g) => g.value === grade)?.label ?? grade} (변경)
            </a>
          )}
        </nav>
      </header>

      <section className="hero">
        <span className="hero-badge">🦦 오늘도 한 문제, 수달이랑</span>

        <h1 className="hero-title">수달이</h1>
        <p className="hero-tagline">헤엄치듯 가볍게, 수학의 달인이 되는 길</p>

        <div className="mascot-wrap">
          <svg className="mascot-float" viewBox="0 0 300 300" xmlns="http://www.w3.org/2000/svg">
            {/* tail - thick, tapering, curled behind the body like a real otter's */}
            <path d="M 198 232 C 230 246 262 240 272 208 C 278 187 268 168 250 168 C 238 168 232 180 237 195 C 242 210 232 224 208 222 Z" fill="#C98B5B" />
            <path d="M 246 182 C 256 190 260 202 256 214" stroke="#B27C4D" strokeWidth="3" fill="none" strokeLinecap="round" opacity="0.45" />

            {/* body - sleeker, tapered at the shoulders, wider sitting base (not a bear-round blob) */}
            <path d="M 150 148 C 188 148 214 176 213 214 C 212 253 186 278 150 278 C 114 278 88 253 87 214 C 86 176 112 148 150 148 Z" fill="#C98B5B" />
            <ellipse cx="150" cy="222" rx="44" ry="48" fill="#FBE7CE" />

            {/* arms holding the book */}
            <ellipse cx="103" cy="204" rx="17" ry="23" fill="#C98B5B" transform="rotate(-12 103 204)" />
            <ellipse cx="197" cy="204" rx="17" ry="23" fill="#C98B5B" transform="rotate(12 197 204)" />
            <ellipse cx="99" cy="221" rx="10" ry="9" fill="#EFC79A" />
            <ellipse cx="201" cy="221" rx="10" ry="9" fill="#EFC79A" />

            <g transform="translate(112,182) rotate(-6)">
              <rect x="0" y="0" width="76" height="52" rx="5" fill="#FF8961" />
              <rect x="4" y="4" width="34" height="44" rx="3" fill="#FFF6EF" />
              <rect x="40" y="4" width="34" height="44" rx="3" fill="#FFEAE0" />
              <line x1="38" y1="4" x2="38" y2="48" stroke="#E9683F" strokeWidth="2" />
              <line x1="10" y1="15" x2="30" y2="15" stroke="#F3C9AE" strokeWidth="2" strokeLinecap="round" />
              <line x1="10" y1="23" x2="26" y2="23" stroke="#F3C9AE" strokeWidth="2" strokeLinecap="round" />
            </g>

            {/* head - flatter and wider than a bear's, true to an otter's broad face */}
            <path d="M 150 58 C 194 58 217 90 214 120 C 211 154 183 172 150 172 C 117 172 89 154 86 120 C 83 90 106 58 150 58 Z" fill="#C98B5B" />

            {/* ears - small and set low on the sides, like a real otter */}
            <circle cx="97" cy="90" r="13" fill="#C98B5B" />
            <circle cx="203" cy="90" r="13" fill="#C98B5B" />
            <circle cx="97" cy="90" r="6.5" fill="#EFC79A" />
            <circle cx="203" cy="90" r="6.5" fill="#EFC79A" />

            {/* wide pale muzzle / face mask */}
            <path d="M 150 98 C 180 98 197 116 193 138 C 189 160 172 170 150 170 C 128 170 111 160 107 138 C 103 116 120 98 150 98 Z" fill="#FBE7CE" />

            <circle cx="114" cy="132" r="11" fill="#FFC9B0" opacity="0.75" />
            <circle cx="186" cy="132" r="11" fill="#FFC9B0" opacity="0.75" />

            <circle cx="131" cy="116" r="7" fill="#1F3B4D" />
            <circle cx="169" cy="116" r="7" fill="#1F3B4D" />
            <circle cx="133.5" cy="113" r="2.2" fill="#fff" />
            <circle cx="171.5" cy="113" r="2.2" fill="#fff" />

            {/* small flat otter nose */}
            <path d="M 143 132 Q 150 126 157 132 Q 157 139 150 141 Q 143 139 143 132 Z" fill="#1F3B4D" />
            <path d="M 150 141 L 150 146 M 150 146 Q 143 152 137 148 M 150 146 Q 157 152 163 148" stroke="#1F3B4D" strokeWidth="2.2" fill="none" strokeLinecap="round" />

            <line x1="106" y1="128" x2="74" y2="122" stroke="#1F3B4D" strokeWidth="1.6" opacity="0.5" />
            <line x1="106" y1="137" x2="74" y2="139" stroke="#1F3B4D" strokeWidth="1.6" opacity="0.5" />
            <line x1="194" y1="128" x2="226" y2="122" stroke="#1F3B4D" strokeWidth="1.6" opacity="0.5" />
            <line x1="194" y1="137" x2="226" y2="139" stroke="#1F3B4D" strokeWidth="1.6" opacity="0.5" />

            <g transform="translate(192,150) rotate(35)">
              <rect x="0" y="0" width="10" height="46" fill="#63C9A0" />
              <polygon points="0,46 10,46 5,58" fill="#4C6B78" />
              <rect x="0" y="0" width="10" height="8" fill="#FF8961" />
            </g>
          </svg>
        </div>

        <div className="input-card">
          <input
            type="text"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="배우고 싶은 개념을 입력해봐요 (예: 최대공약수)"
          />
        </div>

        {dueTopics.length > 0 && !topicWarning && (
          <div className="input-card" style={{ flexDirection: 'column', alignItems: 'stretch', gap: '12px' }}>
            <p style={{ margin: 0, color: 'var(--ink-soft)', fontSize: '0.9rem' }}>
              🔔 "{dueTopics[0].topic_key}" 등 복습하면 좋은 개념이 {dueTopics.length}개 있어요.
            </p>
            <button className="btn-primary" type="button" onClick={() => navigate('/single-learning', { state: { grade, topic: '', difficulty: 2, focusWeak: true } })}>
              🎯 취약 개념 복습하기
            </button>
          </div>
        )}

        {topicWarning && (
          <div className="input-card" style={{ flexDirection: 'column', alignItems: 'stretch', gap: '12px' }}>
            <p style={{ margin: 0, color: 'var(--ink-soft)', fontSize: '0.9rem' }}>
              🦦 "{topic}"과 정확히 맞는 문제를 찾지 못했어요. 다른 키워드로 다시 써보거나, 무작위 문제로 진행할 수 있어요.
            </p>
            <div className="btn-row">
              <button className="btn-secondary" type="button" onClick={() => setTopicWarning(null)}>
                다른 키워드 입력할게요
              </button>
              <button className="btn-primary" type="button" onClick={() => proceed(topicWarning)}>
                무작위로 진행할게요
              </button>
            </div>
          </div>
        )}

        <div className="cta-row">
          <button className="btn-primary" type="button" onClick={() => attemptStart('single')} disabled={checking}>
            {checking ? '⏳ 확인 중...' : '🖊️ 문제 하나 풀어볼래요'}
          </button>
          <button className="btn-secondary" type="button" onClick={() => attemptStart('exam')} disabled={checking}>
            {checking ? '⏳ 확인 중...' : '🧭 내 실력 진단받기'}
          </button>
        </div>
        <p className="hero-note">난이도는 안 골라도 돼요 — 수달이가 알아서 맞춰줘요</p>

        <svg className="river" viewBox="0 0 1440 70" preserveAspectRatio="none">
          <path d="M0,30 C 200,60 400,0 600,25 C 800,50 1000,5 1200,30 C 1320,45 1400,20 1440,30 L1440,70 L0,70 Z" fill="#BEE6E6" />
        </svg>
      </section>

      <section className="flow" id="flow">
        <div className="flow-heading">
          <h2>수달이는 이렇게 도와줘요</h2>
          <p>문제를 만들어내지 않고, 검증된 문제 중에서 딱 맞는 걸 찾아드려요</p>
        </div>

        <div className="flow-grid">
          <div className="flow-card">
            <div className="flow-icon icon-bank">📚</div>
            <h3>문제은행에서 쏙</h3>
            <p>이미 검증된 8만 여 개 문제 중에서 지금 배우는 개념에 딱 맞는 걸 찾아와요.</p>
          </div>
          <div className="flow-card">
            <div className="flow-icon icon-dial">🎚️</div>
            <h3>속도에 맞춰 조절</h3>
            <p>연속으로 맞히면 조금 더 어렵게, 틀리면 눈높이를 낮춰서 다음 문제를 골라요.</p>
          </div>
          <div className="flow-card">
            <div className="flow-icon icon-hint">💡</div>
            <h3>막히면 힌트를 한 걸음씩</h3>
            <p>정답을 바로 주지 않고, 풀이를 단계별로 나눠서 필요한 만큼만 보여줘요.</p>
          </div>
          <div className="flow-card">
            <div className="flow-icon icon-chat">💬</div>
            <h3>눈높이에 맞는 재설명</h3>
            <p>틀렸을 땐 지금 실력에 맞춰 풀이를 쉽게 풀어서 다시 설명해줘요.</p>
          </div>
        </div>
      </section>

      <section className="modes" id="modes">
        <h2>뭐부터 해볼까요?</h2>
        <div className="mode-grid">
          <div className="mode-card single">
            <span className="mode-tag">학습모드</span>
            <h3>한 문제씩, 차근차근</h3>
            <p>중간 난이도부터 시작해서, 풀수록 나에게 맞는 속도를 찾아가요. 막히면 힌트, 틀리면 다시 설명까지.</p>
            <button className="mini-btn" type="button" onClick={() => attemptStart('single')} disabled={checking}>학습모드 시작</button>
          </div>
          <div className="mode-card exam">
            <span className="mode-tag">모의고사</span>
            <h3>내 실력, 한 번에 진단</h3>
            <p>10문항(하 3 · 중 5 · 상 2)으로 지금 수준을 확인하고, 약한 개념을 딱 짚어드려요.</p>
            <button className="mini-btn" type="button" onClick={() => attemptStart('exam')} disabled={checking}>모의고사 응시</button>
          </div>
        </div>
      </section>

      <footer className="landing-footer">
        🦦 수달이 — 수학의 달인 · 문제는 만들지 않아요, 딱 맞는 걸 찾아드려요
      </footer>
    </>
  );
};

export default InputForm;

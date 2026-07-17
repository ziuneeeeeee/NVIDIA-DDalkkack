// 로그인이 없는 대신 닉네임을 사용자 식별자로 쓴다. 이 값이 그대로 DB의 user_id가 된다.
// 예전 UUID 방식이 쓰던 키('sudal:user-id')와 다른 키를 써서, 남아있던 UUID는 자연히 무시된다.
const STORAGE_KEY = 'sudal:nickname';

export const MAX_NICKNAME_LENGTH = 20;

export function getNickname(): string | null {
  const value = localStorage.getItem(STORAGE_KEY);
  return value && value.trim() ? value : null;
}

export function setNickname(name: string): void {
  localStorage.setItem(STORAGE_KEY, name.trim());
}

/** 문제가 있으면 사용자에게 보여줄 메시지를, 괜찮으면 null을 반환한다. */
export function validateNickname(raw: string): string | null {
  const name = raw.trim();
  if (!name) return '닉네임을 입력해주세요.';
  if (name.length > MAX_NICKNAME_LENGTH) return `${MAX_NICKNAME_LENGTH}자 이내로 입력해주세요.`;
  // 페르소나 실험용 user_id(persona:이름-시각)와 서버 폴백 값이 섞이지 않도록 막는다.
  if (name.startsWith('persona:') || name === 'anonymous') return '사용할 수 없는 닉네임이에요.';
  return null;
}

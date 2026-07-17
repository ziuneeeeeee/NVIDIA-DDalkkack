export const isMultiPartQuestion = (questionText?: string | null): boolean => {
  if (!questionText) return false;
  return /\(1\)/.test(questionText) && /\(2\)/.test(questionText);
};

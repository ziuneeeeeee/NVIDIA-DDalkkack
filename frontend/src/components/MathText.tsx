import React, { useEffect, useRef } from 'react';
import renderMathInElement from 'katex/contrib/auto-render';

const DELIMITERS = [
  { left: '$$', right: '$$', display: true },
  { left: '\\[', right: '\\]', display: true },
  { left: '\\(', right: '\\)', display: false },
  { left: '$', right: '$', display: false },
];

interface MathTextProps {
  text: string;
  className?: string;
  style?: React.CSSProperties;
}

const MathText: React.FC<MathTextProps> = ({ text, className, style }) => {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.textContent = text || '';
    renderMathInElement(el, { delimiters: DELIMITERS, throwOnError: false });
  }, [text]);

  return <div ref={ref} className={className} style={{ whiteSpace: 'pre-wrap', ...style }} />;
};

export default MathText;

// 巨型渐变字标：填色渐变 + 极细描边，用作背景层。
// 不依赖 TextHoverEffect（那个只做描边）。渐变从 neon-tokens.css 的 --grad-a/b/c 取。
import React, { useId } from 'react';

export function GradientWord({
  text,
  className = '',
  vertical = false,
}: {
  text: string;
  className?: string;
  vertical?: boolean;
}) {
  const id = useId().replace(/:/g, '');
  const gradient = vertical ? (
    <linearGradient id={`${id}-g`} x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stopColor="var(--grad-a)" stopOpacity=".92" />
      <stop offset=".48" stopColor="var(--grad-b)" stopOpacity=".5" />
      <stop offset="1" stopColor="var(--grad-c)" stopOpacity=".06" />
    </linearGradient>
  ) : (
    <linearGradient id={`${id}-g`} x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stopColor="var(--grad-b)" stopOpacity=".18" />
      <stop offset=".22" stopColor="var(--grad-a)" stopOpacity=".62" />
      <stop offset=".5" stopColor="var(--grad-b)" stopOpacity=".4" />
      <stop offset=".78" stopColor="var(--grad-a)" stopOpacity=".3" />
      <stop offset="1" stopColor="var(--grad-c)" stopOpacity="0" />
    </linearGradient>
  );

  return (
    <svg
      className={`gradient-word ${className}`}
      viewBox="0 0 1200 200"
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label={text}
    >
      <defs>{gradient}</defs>
      <text
        className="gradient-word__text"
        x="50%"
        y="50%"
        textAnchor="middle"
        dominantBaseline="central"
        textLength="1160"
        lengthAdjust="spacingAndGlyphs"
        fill={`url(#${id}-g)`}
      >
        {text}
      </text>
    </svg>
  );
}

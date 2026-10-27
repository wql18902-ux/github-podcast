// Project adapter of Aceternity UI TextHoverEffect. Upstream retained in vendor/aceternity/originals.
import React, { useId, useRef, useState } from 'react';
import { motion } from 'motion/react';
import { useReducedMotion } from '../vendor/lwq/useReducedMotion';

export function TextHoverEffect({ text, duration = .2 }: { text: string; duration?: number }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const id = useId().replace(/:/g, '');
  const reduced = useReducedMotion();
  const [hovered, setHovered] = useState(false);
  const [position, setPosition] = useState({ cx: '50%', cy: '50%' });
  const shared = { x: '50%', y: '52%', textAnchor: 'middle' as const, dominantBaseline: 'middle' as const, textLength: 1160, lengthAdjust: 'spacingAndGlyphs' as const };
  return <svg ref={svgRef} className="text-hover-effect" data-component="TextHoverEffect" data-hovered={hovered} viewBox="0 0 1200 180" role="img" aria-label={text} onPointerEnter={() => setHovered(true)} onPointerLeave={() => setHovered(false)} onPointerMove={event => {
    if (reduced || event.pointerType === 'touch') return;
    const rect = svgRef.current!.getBoundingClientRect();
    setPosition({ cx: `${(event.clientX - rect.left) / rect.width * 100}%`, cy: `${(event.clientY - rect.top) / rect.height * 100}%` });
  }}>
    <defs>
      <linearGradient id={`${id}-ink`} x1="0" x2="100%"><stop offset="0" stopColor="var(--beam-5)"/><stop offset=".3" stopColor="var(--beam-4)"/><stop offset=".55" stopColor="var(--beam-3)"/><stop offset=".75" stopColor="var(--beam-2)"/><stop offset="1" stopColor="var(--beam-1)"/></linearGradient>
      <motion.radialGradient id={`${id}-reveal`} gradientUnits="userSpaceOnUse" r="24%" initial={false} animate={reduced ? { cx: '50%', cy: '50%' } : position} transition={{ duration, ease: 'easeOut' }}><stop offset="0" stopColor="white"/><stop offset="1" stopColor="black"/></motion.radialGradient>
      <mask id={`${id}-mask`}><rect width="100%" height="100%" fill={`url(#${id}-reveal)`}/></mask>
    </defs>
    <text {...shared} className="hover-text-base">{text}</text>
    <motion.text {...shared} className="hover-text-trace" initial={reduced ? false : { strokeDashoffset: 1200, strokeDasharray: 1200 }} animate={{ strokeDashoffset: 0 }} transition={{ duration: reduced ? 0 : 1.6, ease: 'easeInOut' }}>{text}</motion.text>
    <text {...shared} className="hover-text-color" stroke={`url(#${id}-ink)`} mask={`url(#${id}-mask)`} style={{ opacity: hovered || reduced ? 1 : .5 }}>{text}</text>
  </svg>;
}

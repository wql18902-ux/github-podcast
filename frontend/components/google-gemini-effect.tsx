// Aceternity's five original path geometries, with Sourcecast labels and scoped filters.
import React, { useId } from 'react';
import { motion, type MotionValue } from 'motion/react';
import { GEMINI_PATHS } from './gemini-paths';

export function GoogleGeminiEffect({ pathLengths, staticFrame = false }: { pathLengths: MotionValue<number>[]; staticFrame?: boolean }) {
  const id = useId().replace(/:/g, '');
  return <svg className="gemini-effect" data-component="GoogleGeminiEffect" viewBox="0 280 1440 470" preserveAspectRatio="none" fill="none" aria-hidden="true">
    <defs><filter id={`${id}-glow`} x="-20%" y="-100%" width="140%" height="300%"><feGaussianBlur stdDeviation="7"/></filter></defs>
    <g opacity=".25" filter={`url(#${id}-glow)`}>{GEMINI_PATHS.map((d, index) => <path key={index} d={d} stroke={`var(--beam-${index + 1})`} strokeWidth="8"/>)}</g>
    {GEMINI_PATHS.map((d, index) => <path key={'base' + index} d={d} stroke={`var(--beam-${index + 1})`} strokeWidth="1.2" opacity=".12"/>)}
    {GEMINI_PATHS.map((d, index) => <motion.path key={index} d={d} data-gemini-path={index} stroke={`var(--beam-${index + 1})`} strokeWidth="2.4" strokeLinecap="round" style={{ pathLength: staticFrame ? 1 : pathLengths[index] }} transition={{ duration: 0, ease: 'linear' }}/>) }
  </svg>;
}

// Aceternity 3DMarquee geometry and alternating columns; local assets and lifecycle controls.
import React, { useEffect, useRef, useState } from 'react';
import { animate, motion, useInView, useMotionValue } from 'motion/react';
import { useReducedMotion } from '../vendor/lwq/useReducedMotion';

function Column({ images, index, running }: { images: string[]; index: number; running: boolean }) {
  const y = useMotionValue(0);
  const controls = useRef<ReturnType<typeof animate> | null>(null);
  useEffect(() => {
    controls.current = animate(y, [0, index % 2 === 0 ? 100 : -100], { duration: index % 2 === 0 ? 10 : 15, repeat: Infinity, repeatType: 'reverse', ease: 'easeInOut' });
    if (!running) controls.current.pause();
    return () => controls.current?.stop();
  }, []);
  useEffect(() => { running ? controls.current?.play() : controls.current?.pause(); }, [running]);
  return <motion.div className="marquee-column" data-marquee-column={index} style={{ y }}><i className="marquee-guide" aria-hidden="true"/>{images.map((image, i) => <div key={image + i} className="marquee-item"><motion.img src={image} width="970" height="700" loading="lazy" decoding="async" alt="页声功能示例展示" whileHover={running ? { y: -10 } : undefined} transition={{ duration: .3, ease: 'easeOut' }}/></div>)}</motion.div>;
}

export function ThreeDMarquee({ images, paused, onToggle }: { images: string[]; paused: boolean; onToggle: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { amount: .08 });
  const reduced = useReducedMotion();
  const [visible, setVisible] = useState(document.visibilityState === 'visible');
  useEffect(() => { const update = () => setVisible(document.visibilityState === 'visible'); document.addEventListener('visibilitychange', update); return () => document.removeEventListener('visibilitychange', update); }, []);
  const running = inView && visible && !paused && !reduced;
  const chunk = Math.ceil(images.length / 4);
  return <div ref={ref} className="three-d-marquee" data-component="ThreeDMarquee" data-running={running}>
    <div className="marquee-center" aria-hidden="true"><div className="marquee-scale"><div className="marquee-grid">{Array.from({ length: 4 }, (_, index) => <Column key={index} index={index} images={images.slice(index * chunk, (index + 1) * chunk)} running={running}/>)}</div></div></div>
    <div className="marquee-shade" aria-hidden="true"/>
    <button type="button" className="marquee-pause" aria-pressed={paused} onClick={onToggle} disabled={reduced}>{reduced ? '已遵循减少动态偏好' : paused ? '继续动效 ▷' : '暂停动效 Ⅱ'}</button>
  </div>;
}

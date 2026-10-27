import React, { useEffect, useRef, useState } from 'react';
import { ArrowUpRight, ArrowRight, BookOpen, FileText, CodeXml, AudioLines, NotebookPen, Network, Play, Pause, Plus, Minus, SunMoon, HelpCircle } from 'lucide-react';
import { useReducedMotion } from './vendor/lwq/useReducedMotion';
import { books, papers, repos, featuredEpisodes, stats, audition, needs, sampleEpisode } from './content';

/** Griffin reference mechanisms are documented in design-research/griffin-20261025.
 * Original Sourcecast implementation; no Griffin brand, images or proprietary fonts.
 * Keep the native workbench's start/demo/audio contracts as the only action owners.
 *
 * 2026-10-27：介绍页讲「先说出需求 → 找到对得上的那一期 → 看清它能帮你什么」。
 * 每一块都接到同一份数据上：needs / sampleEpisode 来自 content.ts，期号与日期照 data.js 抄。
 */
const demo = (view = 'notes') => window.dispatchEvent(new CustomEvent('sourcecast:demo', { detail: view }));
const start = (mode: string) => window.dispatchEvent(new CustomEvent('sourcecast:start', { detail: mode }));
const Arrow = () => <ArrowUpRight size={15} aria-hidden="true" />;
const openEpisode = (event: React.MouseEvent<HTMLAnchorElement>, no: number) => {
  const native = window as Window & { LIB?: { episodes: Array<{ no: number; slug: string }> }; Sourcecast?: { openEpisode: (slug: string) => void } };
  const episode = native.LIB?.episodes.find(episode => episode.no === no);
  if (episode && native.Sourcecast?.openEpisode) { event.preventDefault(); native.Sourcecast.openEpisode(episode.slug); }
};

function Brand() {
  return <a href="#welcome" className="gfn-brand" aria-label="页声首页"><span className="gfn-mark" aria-hidden="true"><i /><i /><i /></span><b>页声</b><span>Sourcecast</span></a>;
}

function CharacterField({ reduced }: { reduced: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [paused] = useState(false);
  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return;
    let frame = 0, width = 0, height = 0, last = 0, visible = true, time = 0;
    let pointer = 0;
    const draw = () => {
      ctx.clearRect(0, 0, width, height);
      ctx.font = '12px monospace';
      ctx.textAlign = 'center';
      ctx.fillStyle = getComputedStyle(canvas).getPropertyValue('--gfn-ink').trim();
      const cols = Math.ceil(width / 12), rows = Math.ceil(height / 14);
      for (let y = 0; y < rows; y++) {
        for (let x = 0; x < cols; x++) {
          const nx = x / cols;
          const ny = y / rows;
          const wave = Math.sin(nx * 15 + time * .22) * .18 + Math.cos(nx * 8 - time * .14) * .16;
          const contour = Math.sin((ny + wave + pointer * .035) * 27 + Math.sin(nx * 31) * 1.4);
          const hash = Math.abs(Math.sin(x * 127.1 + y * 311.7));
          const fade = Math.min(1, ny * 6) * Math.min(1, (1 - ny) * 5);
          ctx.globalAlpha = (contour > .8 ? .64 : contour > .35 ? .29 : .07) * fade;
          ctx.fillText(contour > .87 && hash > .82 ? '+' : contour > .76 && hash < .12 ? '/' : '·', x * 12 + 6, y * 14 + 10);
        }
      }
      ctx.globalAlpha = 1;
    };
    const tick = (now: number) => {
      frame = 0;
      if (!visible || document.hidden || reduced || paused) return;
      if (now - last > 60) { time += .06; draw(); last = now; }
      frame = requestAnimationFrame(tick);
    };
    const sync = () => {
      cancelAnimationFrame(frame); frame = 0;
      draw();
      if (visible && !document.hidden && !reduced && !paused) frame = requestAnimationFrame(tick);
    };
    const resize = () => {
      const box = canvas.getBoundingClientRect();
      width = box.width; height = box.height;
      const dpr = Math.min(devicePixelRatio || 1, 2);
      canvas.width = width * dpr; canvas.height = height * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0); sync();
    };
    const move = (event: PointerEvent) => { pointer = event.offsetX / Math.max(width, 1) - .5; };
    const resizeObserver = new ResizeObserver(resize);
    const intersection = new IntersectionObserver(entries => { visible = entries[0].isIntersecting; sync(); });
    const themeObserver = new MutationObserver(draw);
    resizeObserver.observe(canvas); intersection.observe(canvas);
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    canvas.addEventListener('pointermove', move);
    document.addEventListener('visibilitychange', sync);
    resize();
    return () => { cancelAnimationFrame(frame); resizeObserver.disconnect(); intersection.disconnect(); themeObserver.disconnect(); canvas.removeEventListener('pointermove', move); document.removeEventListener('visibilitychange', sync); };
  }, [reduced, paused]);
  return <div className="gfn-field"><canvas ref={canvasRef} aria-hidden="true" /><div className="gfn-field__caption"><span>ONE QUESTION · ONE EPISODE · ONE JUDGEMENT</span></div></div>;
}

function Orbit({ reduced }: { reduced: boolean }) {
  const ref = useRef<HTMLSpanElement>(null);
  const [running, setRunning] = useState(false);
  useEffect(() => {
    const orbit = ref.current;
    if (!orbit) return;
    let visible = false;
    const sync = () => setRunning(visible && !document.hidden && !reduced);
    const observer = new IntersectionObserver(entries => { visible = entries[0].isIntersecting; sync(); });
    observer.observe(orbit);
    document.addEventListener('visibilitychange', sync);
    return () => { observer.disconnect(); document.removeEventListener('visibilitychange', sync); };
  }, [reduced]);
  return <span ref={ref} className="gfn-orbit" data-running={running} aria-hidden="true"><span className="gfn-orbit__rings"><i /><i /><i /></span><span className="gfn-orbit__path"><b /></span></span>;
}

function Opening({ reduced }: { reduced: boolean }) {
  return <>
    <section className="gfn-hero gfn-container" aria-labelledby="gfn-title">
      <div className="gfn-hero__main"><span className="gfn-label">START WITH WHAT YOU NEED</span><h1 id="gfn-title">先说你要什么，<br />这里大概有一期，<br />是替它拆的。</h1><p>这里的每一期都不是追热点追出来的，是从一个具体的问题拆出来的。<br className="gfn-desktop-break" />拆完留下的不是摘要，是能拿走、也能回去查的判断。</p><div className="gfn-actions"><button className="gfn-button" onClick={() => start('问题')}>说说我正琢磨的事 <Arrow /></button><a className="gfn-text-button" href="#welcome-workflow">怎么用，三步 <ArrowRight size={15} /></a></div></div>
      <aside className="gfn-hero__aside"><Orbit reduced={reduced} /><p className="gfn-english">One question.<br />One episode.</p><span className="gfn-label">39 期堆在这里，<br />都在等一个问题。</span></aside>
    </section>
    <CharacterField reduced={reduced} />
    <div className="gfn-proof gfn-container" aria-label="内容存档规模"><span className="gfn-label">每一期都追得回一份原稿</span><a href="#welcome-needs"><b>{stats.episodes}</b> 期深读</a><a href="#judgments"><b>{stats.judgments}</b> 条判断</a><a href="#welcome-sources"><b>{stats.repos}</b> 个拆过的项目</a><span><b>{(stats.chars / 10000).toFixed(1)}万</b> 字的积累</span></div>
  </>;
}

const steps = [
  { n: '01', title: '说出你的需求', text: '一句话就够了，不用组织得漂亮。你现在卡在哪、想弄明白什么，比你想要什么更有用。', tags: ['一句话就行', '不用准备材料', '说人话'], icon: HelpCircle },
  { n: '02', title: '找到对得上的那一期', text: '这里的期次按「你会遇到的问题」归档，不按项目火不火。先看哪一条像你现在的处境。', tags: ['按问题归档', '不按热度', '39 期里挑'], icon: Network },
  { n: '03', title: '拿走一条能用的判断', text: '每期的判断都是逐字从原稿里摘的，带着来源期次和日期。可以当真用，也可以顺着期号回去查。', tags: ['逐字摘录', '带期号与日期', '能回去查'], icon: NotebookPen },
];

function Steps() {
  return <section id="welcome-workflow" className="gfn-materials gfn-container" aria-labelledby="gfn-workflow-title">
    <header className="gfn-section-head"><div><span className="gfn-label">01 / HOW IT WORKS</span><h2 id="gfn-workflow-title">三步，就够了。</h2></div><p>不用先想清楚怎么问，<br />也不用挑工具。带一句话来就行。</p></header>
    <div className="gfn-material-grid gfn-trio">{steps.map(({ n, title, text, tags, icon: Icon }) => <article key={title} className="gfn-material"><header><span className="gfn-label">{n} / STEP</span><Icon size={18} aria-hidden="true" /></header><h3>{title}</h3><p>{text}</p><ul>{tags.map(tag => <li key={tag}>{tag}</li>)}</ul></article>)}</div>
  </section>;
}

function Needs() {
  return <section id="welcome-needs" className="gfn-needs gfn-container" aria-labelledby="gfn-needs-title">
    <header className="gfn-section-head"><div><span className="gfn-label">02 / FIND THE EPISODE BY YOUR NEED</span><h2 id="gfn-needs-title">你在琢磨什么，<br />就从那个问题进去。</h2></div><p>九条线，九句你会问自己的话。<br />点一条，直接打开这条线上最有代表性的那一期。</p></header>
    <div className="gfn-source-grid">{needs.map((need, i) => <a key={need.series} href="#episodes" onClick={event => openEpisode(event, need.pick.no)} className="gfn-source-card gfn-need"><header><span className="gfn-label">需求 {String(i + 1).padStart(2, '0')}</span><span>{need.label || need.series} · {need.count} 期</span></header><h3>「{need.question}」</h3><p>{need.help}</p><footer className="gfn-need__meta"><span>EP.{need.pick.no} · {need.pick.date}</span><span>打开这一期 →</span></footer></a>)}</div>
  </section>;
}

function Anatomy() {
  return <section id="welcome-anatomy" className="gfn-anatomy gfn-container" aria-labelledby="gfn-anatomy-title">
    <div className="gfn-anatomy__copy"><span className="gfn-label">03 / WHAT ONE EPISODE GIVES YOU</span><h2 id="gfn-anatomy-title">一期给你的，<br />是三样东西。</h2><p>三条判断、一句能带走的话、一处能回去查的出处。</p><p>判断全部逐字摘自原稿，不改写成更好听的版本，也不替你总结。每条挂着期号与日期，点得回去。</p><p>判断从哪来？从真的读过的东西里来：别人的源码、文档、论文与书。下面这一期，是从两个仓库里读出来的。</p></div>
    <article className="gfn-sheet" aria-label="一期样本">
      <header className="gfn-sheet__head"><span>EP.{sampleEpisode.no} / {sampleEpisode.series}</span><time dateTime={sampleEpisode.date}>{sampleEpisode.date}</time></header>
      <h3>{sampleEpisode.title}</h3>
      <p className="gfn-sheet__line">「{sampleEpisode.oneLiner}」<small>一句话带走 · 摘自本期原稿</small></p>
      <ol aria-label="本期三条判断">{sampleEpisode.judgments.map(judgment => <li key={judgment}>{judgment}</li>)}</ol>
      <div className="gfn-sheet__foot"><span>出处：{sampleEpisode.repos.join(' · ')}<br />原稿日期 {sampleEpisode.date}</span><a className="gfn-small-button" href="#episodes" onClick={event => openEpisode(event, sampleEpisode.no)}>打开这一期 <Arrow /></a></div>
    </article>
  </section>;
}

function Sources() {
  const [tab, setTab] = useState<'paper' | 'repo' | 'book'>('paper');
  const rows = tab === 'paper' ? papers : tab === 'repo' ? repos : books;
  const [expanded, setExpanded] = useState(false);
  const tabs: Array<{ id: typeof tab; label: string; icon: typeof FileText; count: number }> = [{ id: 'paper', label: '论文', icon: FileText, count: papers.length }, { id: 'repo', label: '开源项目', icon: CodeXml, count: repos.length }, { id: 'book', label: '书籍', icon: BookOpen, count: books.length }];
  const change = (id: typeof tab) => { setTab(id); setExpanded(false); };
  return <section id="welcome-sources" className="gfn-sources gfn-container" aria-labelledby="gfn-sources-title"><header className="gfn-section-head"><div><span className="gfn-label">04 / WHAT THESE EPISODES WERE READ FROM</span><h2 id="gfn-sources-title">每一期背后，<br />都有真的读过的东西。</h2></div><p>书、论文、仓库——它们不是装饰，<br />是某一期里一个具体判断的来处。</p></header><div className="gfn-tabs" role="tablist" aria-label="拆过的来源">{tabs.map(({ id, label, icon: Icon, count }, i) => <button key={id} id={`gfn-source-tab-${id}`} role="tab" tabIndex={tab === id ? 0 : -1} aria-selected={tab === id} aria-controls="gfn-source-panel" onClick={() => change(id)} onKeyDown={event => { const delta = { ArrowRight: 1, ArrowLeft: -1 }[event.key]; if (delta || event.key === 'Home' || event.key === 'End') { event.preventDefault(); const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (i + delta! + tabs.length) % tabs.length; change(tabs[next].id); document.getElementById(`gfn-source-tab-${tabs[next].id}`)?.focus(); } }}><Icon size={16} />{label}<small>{count}</small></button>)}</div><div id="gfn-source-panel" role="tabpanel" aria-labelledby={`gfn-source-tab-${tab}`} className="gfn-source-grid">{(expanded ? rows : rows.slice(0, 4)).map(row => <a key={row.title} href="#episodes" onClick={event => openEpisode(event, row.episode)} className="gfn-source-card"><header><span className="gfn-label">{tab === 'paper' ? 'PAPER' : tab === 'repo' ? 'OPEN SOURCE' : 'BOOK'} / EP.{row.episode}</span><Arrow /></header><h3>{row.title}</h3><p>{row.note}</p><footer><span>{row.tags.slice(0, 2).join(' · ')}</span><time dateTime={row.date}>{row.date}</time></footer></a>)}</div>{rows.length > 4 && <button className="gfn-text-button gfn-source-more" onClick={() => setExpanded(!expanded)} aria-expanded={expanded} aria-controls="gfn-source-panel">{expanded ? '收起条目' : `查看全部 ${rows.length} 个条目`}{expanded ? <Minus size={14} /> : <Plus size={14} />}</button>}</section>;
}

function Recent() {
  return <section id="welcome-recent" className="gfn-recent gfn-container" aria-labelledby="gfn-recent-title"><header className="gfn-section-head"><div><span className="gfn-label">05 / THE LATEST CHAPTERS</span><h2 id="gfn-recent-title">最近拆完的几期。</h2><p>先看这几个，也许就有对得上你的那条。</p></div><a className="gfn-small-button" href="#episodes">全部 {stats.episodes} 期<Arrow /></a></header><div className="gfn-episode-grid">{[...featuredEpisodes].sort((a, b) => b.no - a.no).slice(0, 3).map((ep, i) => <a href={ep.url} onClick={event => openEpisode(event, ep.no)} key={ep.no} className="gfn-episode"><div className={`gfn-episode-art gfn-episode-art--${i}`} aria-hidden="true"><span>{String(ep.no).padStart(2, '0')}</span><svg viewBox="0 0 400 210">{Array.from({ length: 13 }, (_, n) => i === 0 ? <path key={n} d={`M${30 + n * 27} -20L${160 + n * 16} 240`} /> : i === 1 ? <ellipse key={n} cx="200" cy="105" rx={30 + n * 18} ry={16 + n * 12} /> : <path key={n} d={`M-10 ${30 + n * 18}Q200 ${180 - n * 9} 410 ${20 + n * 18}`} />)}</svg><span>FIELD NOTES / SOURCECAST</span></div><div className="gfn-episode-meta"><span>EP.{ep.no}</span><time dateTime={ep.date}>{ep.date}</time><Arrow /></div><h3>{ep.title}</h3><p>{ep.oneLiner}</p></a>)}</div></section>;
}

function Listening() {
  const [audioState, setAudioState] = useState({ playing: false, source: '', time: 0 });
  useEffect(() => {
    const audio = document.getElementById('studioAudio') as HTMLAudioElement | null;
    if (!audio) return;
    const update = () => setAudioState({ playing: !audio.paused && !audio.ended, source: audio.currentSrc || audio.src, time: audio.currentTime });
    const events = ['play', 'pause', 'ended', 'timeupdate', 'loadedmetadata', 'emptied'];
    events.forEach(event => audio.addEventListener(event, update)); update();
    return () => events.forEach(event => audio.removeEventListener(event, update));
  }, []);
  return <section id="welcome-listen" className="gfn-listen gfn-container" aria-labelledby="gfn-listen-title"><div><span className="gfn-label">06 / THE SAME JUDGEMENT, IN TWO VOICES</span><h2 id="gfn-listen-title">判断可以读，<br />也可以听。</h2><p>一期四五十分钟，路上、散步、做饭都能听。<br />先用半分钟，听听哪一种你愿意听下去。</p><span className="gfn-ai-note"><span className="gfn-status-dot" />两种 AI 设计音色 · 不是真人录音</span></div><div className="gfn-auditions">{audition.map((sample, i) => { const id = i === 0 ? 'mimo-warm' : 'mimo-clear'; const active = audioState.source.includes(id); const playing = active && audioState.playing; return <button key={sample.name} className="gfn-audition" aria-label={`${playing ? '暂停' : '试听'}${sample.name}`} aria-pressed={playing} onClick={() => (window as any).Sourcecast?.playAudition(id)}><span className="gfn-play-circle">{playing ? <Pause size={17} /> : <Play size={17} />}</span><span className="gfn-audition-info"><b>{sample.name}</b><small>{sample.subtitle}</small></span><span className="gfn-audition-wave" aria-hidden="true">{Array.from({ length: 28 }, (_, n) => <i key={n} style={{ '--height': `${6 + Math.abs(Math.sin(n * .8 + i)) * 23}px` } as React.CSSProperties} />)}</span><span className="gfn-audition-time">{active && audioState.time > 0 ? `${Math.floor(audioState.time)} / ` : ''}{Math.round(sample.seconds)}s</span></button>; })}<a className="gfn-text-button" href="#studio" onClick={() => setTimeout(() => document.getElementById('tabVoice')?.click(), 0)}>用自己的文字试一段 <Arrow /></a><p className="gfn-audition-note">这两段是预生成的样音，AI 合成，不是真人录音；自己生成才用你自己的账号。</p></div></section>;
}

export function NeonLanding() {
  const [active, setActive] = useState(document.body.classList.contains('is-welcome'));
  const [menuOpen, setMenuOpen] = useState(false);
  const reduced = useReducedMotion();
  useEffect(() => { const update = () => { setActive(document.body.classList.contains('is-welcome')); setMenuOpen(false); }; window.addEventListener('sourcecast:navigate', update); return () => window.removeEventListener('sourcecast:navigate', update); }, []);
  useEffect(() => {
    if (!active || !location.hash.startsWith('#welcome-')) return;
    const frame = requestAnimationFrame(() => document.querySelector(location.hash)?.scrollIntoView({ block: 'start' }));
    return () => cancelAnimationFrame(frame);
  }, [active]);
  if (!active) return null;
  return <div className="gfn-landing" data-reduced={reduced}><header className="gfn-nav gfn-container"><Brand /><nav id="gfn-site-nav" aria-label="了解页声" data-open={menuOpen} onKeyDown={event => { if (event.key === 'Escape') { setMenuOpen(false); (document.querySelector('.gfn-menu-toggle') as HTMLButtonElement)?.focus(); } }}><a href="#welcome-workflow" onClick={() => setMenuOpen(false)}>怎么用</a><a href="#welcome-needs" onClick={() => setMenuOpen(false)}>按需求找期</a><a href="#welcome-anatomy" onClick={() => setMenuOpen(false)}>一期里有什么</a><a href="#welcome-sources" onClick={() => setMenuOpen(false)}>拆过的来源</a><a href="#welcome-recent" onClick={() => setMenuOpen(false)}>最近几期</a><a href="#welcome-listen" onClick={() => setMenuOpen(false)}>试听</a></nav><div className="gfn-nav__actions"><button className="gfn-theme" aria-label="切换明暗" onClick={() => document.getElementById('toggleTheme')?.click()}><SunMoon size={17} /></button><a className="gfn-small-button" href="#home">我的工作室<Arrow /></a><button className="gfn-menu-toggle" aria-label={menuOpen ? '关闭导航' : '打开导航'} aria-expanded={menuOpen} aria-controls="gfn-site-nav" onClick={() => setMenuOpen(!menuOpen)} onKeyDown={event => { if (event.key === 'Escape') setMenuOpen(false); }}>{menuOpen ? <Minus size={20} /> : <Plus size={20} />}</button></div></header><Opening reduced={reduced} /><Steps /><Needs /><Anatomy /><Sources /><Recent /><Listening /><section className="gfn-closing gfn-container"><span className="gfn-label">ONE QUESTION IS ENOUGH</span><h2>说说你正在琢磨的那件事，<br />这里会有一期替你拆过。</h2><button className="gfn-button" onClick={() => start('问题')}>说说我正琢磨的事<Arrow /></button><p>39 期，50 条判断，都可以从你这句话开始找。</p></section><footer className="gfn-footer gfn-container"><div><Brand /><p>从一个问题，找到对得上的那一期。<br />看完，带走一条能用的判断。</p><span className="gfn-label">NO FEED. NO HOT TAKES. ONLY JUDGEMENTS.</span></div><div><span className="gfn-label">找期</span><a href="#welcome-needs">按需求找期<Arrow /></a><a href="#episodes">全部 {stats.episodes} 期<Arrow /></a><a href="#welcome-listen">试听<Arrow /></a></div><div><span className="gfn-label">你的东西</span><button onClick={() => demo('notes')}>笔记示例<Arrow /></button><button onClick={() => demo('mindmap')}>思维导图<Arrow /></button><button onClick={() => demo('connections')}>双向连接<Arrow /></button></div><div><span className="gfn-label">工作室</span><a href="#home">我的工作室<Arrow /></a><a href="#settings">设置自己的模型服务<Arrow /></a><a href="#integrate">带走与备份<Arrow /></a><span className="gfn-footer-note">笔记与材料保存在你自己的浏览器里。<br />自己不接模型服务，也照样能看完整个站。</span></div><div className="gfn-footer-bottom"><span>页声 Sourcecast</span><span>{stats.span} · {stats.episodes} 期阅读存档</span><span className="gfn-footer-credit">声音与模型：<a href="https://platform.xiaomimimo.com/" target="_blank" rel="noopener noreferrer">MiMo</a>（目前免费）</span><a href="#welcome">回到顶部 ↑</a></div></footer></div>;
}

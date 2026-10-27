import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { ArrowUpRight, BookOpen, FileText, CodeXml, AudioLines, NotebookPen, Network, SunMoon } from 'lucide-react';
import { Button } from './vendor/lwq/Button';
import { useReducedMotion } from './vendor/lwq/useReducedMotion';
import { GradientWord } from './components/gradient-word';
import { books, papers, repos, featuredEpisodes, stats, audition } from './content';

/**
 * 页声 Sourcecast · 画幅构成
 *
 * 汇流图的连线不是装饰：每条线用 getBoundingClientRect 从左侧卡片的右缘中点，
 * 真正画到中心圆、再从中心圆画到右侧卡片的左缘中点。窗口变化会重算。
 */

const demo = (view = 'notes') => window.dispatchEvent(new CustomEvent('sourcecast:demo', { detail: view }));
const start = (mode: string) => window.dispatchEvent(new CustomEvent('sourcecast:start', { detail: mode }));

function Brand() {
  return (
    <a className="fmt-brand" href="#welcome" aria-label="页声首页">
      <span className="fmt-brand__mark" aria-hidden="true">
        <i /><i /><i /><i />
      </span>
      <b>页声</b>
      <span>SOURCECAST</span>
    </a>
  );
}

/* ── 首屏：巨型字母背景 + 分层统计卡 ───────────────────────── */

function Opening() {
  return (
    <section className="fmt-opening" aria-labelledby="fmt-title">
      <div className="fmt-hero-word" aria-hidden="true">
        <GradientWord text="SOURCECAST" />
      </div>
      <div className="fmt-opening__caption">
        <span className="fmt-index">(01 — OPENING)</span>
        <h1 id="fmt-title">
          让所有好奇，
          <br />
          <span>在这里相遇。</span>
        </h1>
        <p>
          书籍、论文、开源项目。
          <br />
          汇成能听、能记、能连接的知识。
        </p>
        <div className="fmt-opening__actions">
          <Button asChild variant="default" className="fmt-btn">
            <a href="#studio">
              进入工作室 <ArrowUpRight size={16} aria-hidden="true" />
            </a>
          </Button>
          <button className="fmt-quiet" onClick={() => demo('notes')}>
            先看示例
          </button>
        </div>
      </div>

      <article className="fmt-plate fmt-plate--vertical" aria-labelledby="fmt-stats-title">
        <div className="fmt-plate__body">
          <span className="fmt-index">(Scale)</span>
          <h2 id="fmt-stats-title">三十九期。</h2>
          <dl className="fmt-spec">
            <div><dt>{stats.episodes}</dt><dd>期节目</dd></div>
            <div><dt>{stats.judgments}</dt><dd>条判断</dd></div>
            <div><dt>{stats.repos}</dt><dd>个开源项目</dd></div>
            <div><dt>{Math.round(stats.chars / 10000)}万</dt><dd>汉字讲稿</dd></div>
          </dl>
          <p className="fmt-plate__note">{stats.span}</p>
        </div>
      </article>
    </section>
  );
}

/* ── 汇流：连线连到卡片，再连到中心 ─────────────────────────── */

type Pt = { x: number; y: number };

function Fusion({ reduced }: { reduced: boolean }) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const coreRef = useRef<HTMLDivElement>(null);
  const inRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const outRefs = useRef<Array<HTMLElement | null>>([]);
  const [paths, setPaths] = useState<string[]>([]);
  const [size, setSize] = useState({ w: 0, h: 0 });

  const inputs = [
    { label: '论文', meta: `${papers.length} 篇在册`, icon: FileText, mode: '论文' },
    { label: '开源项目', meta: `${stats.repos} 个仓库`, icon: CodeXml, mode: '开源项目' },
    { label: '问题', meta: '从困惑本身开始', icon: BookOpen, mode: '问题' },
  ];
  const outputs = [
    { label: '听成播客', icon: AudioLines, href: '#studio' },
    { label: '留下笔记', icon: NotebookPen, action: () => demo('notes') },
    { label: '展开导图', icon: Network, action: () => demo('mindmap') },
  ];

  const measure = React.useCallback(() => {
    const wrap = wrapRef.current;
    const core = coreRef.current;
    if (!wrap || !core) return;
    const wb = wrap.getBoundingClientRect();
    const cb = core.getBoundingClientRect();
    const midY = cb.top - wb.top + cb.height / 2;
    const coreLeft: Pt = { x: cb.left - wb.left, y: midY };
    const coreRight: Pt = { x: cb.right - wb.left, y: midY };
    const next: string[] = [];

    /* 左卡右缘中点 → 中心圆左缘；三次贝塞尔，控制点横向各走 55% */
    inRefs.current.forEach(el => {
      if (!el) return;
      const r = el.getBoundingClientRect();
      const from: Pt = { x: r.right - wb.left, y: r.top - wb.top + r.height / 2 };
      const dx = Math.max(40, (coreLeft.x - from.x) * 0.55);
      next.push(`M ${from.x} ${from.y} C ${from.x + dx} ${from.y}, ${coreLeft.x - dx} ${coreLeft.y}, ${coreLeft.x} ${coreLeft.y}`);
    });

    /* 中心圆右缘 → 右卡左缘中点 */
    outRefs.current.forEach(el => {
      if (!el) return;
      const r = el.getBoundingClientRect();
      const to: Pt = { x: r.left - wb.left, y: r.top - wb.top + r.height / 2 };
      const dx = Math.max(40, (to.x - coreRight.x) * 0.55);
      next.push(`M ${coreRight.x} ${coreRight.y} C ${coreRight.x + dx} ${coreRight.y}, ${to.x - dx} ${to.y}, ${to.x} ${to.y}`);
    });

    setPaths(next);
    setSize({ w: wb.width, h: wb.height });
  }, []);

  useLayoutEffect(() => {
    measure();
  }, [measure, reduced]);

  useEffect(() => {
    const ro = new ResizeObserver(() => measure());
    if (wrapRef.current) ro.observe(wrapRef.current);
    window.addEventListener('resize', measure);
    if (document.fonts?.ready) document.fonts.ready.then(() => measure());
    const t = window.setTimeout(measure, 350);
    return () => { ro.disconnect(); window.removeEventListener('resize', measure); window.clearTimeout(t); };
  }, [measure]);

  const inCount = inputs.length;

  return (
    <section className="fmt-fusion" id="welcome-workflow" aria-labelledby="fusion-title">
      <header className="fmt-head">
        <div>
          <span className="fmt-index">(02 — CONNECT)</span>
          <h2 id="fusion-title">不同的输入。<br /><span>同一片知识宇宙。</span></h2>
        </div>
        <p className="fmt-head__note">
          一篇论文的发现，一个开源项目的实现，一个还没想明白的问题。
          <br />
          在这里，找到它们之间的联系。
        </p>
      </header>

      <div className="fmt-diagram" ref={wrapRef}>
        <svg
          className="fmt-wires"
          viewBox={`0 0 ${size.w || 1} ${size.h || 1}`}
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          <defs>
            <linearGradient id="fmt-wire-in" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0" stopColor="var(--grad-line-a)" stopOpacity=".3" />
              <stop offset=".55" stopColor="var(--grad-line-b)" stopOpacity=".85" />
              <stop offset="1" stopColor="var(--grad-line-c)" stopOpacity="1" />
            </linearGradient>
            <linearGradient id="fmt-wire-out" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0" stopColor="var(--grad-line-c)" stopOpacity="1" />
              <stop offset=".45" stopColor="var(--grad-line-b)" stopOpacity=".85" />
              <stop offset="1" stopColor="var(--grad-line-a)" stopOpacity=".3" />
            </linearGradient>
          </defs>
          {paths.map((d, i) => (
            <path
              key={i}
              d={d}
              fill="none"
              stroke={i < inCount ? 'url(#fmt-wire-in)' : 'url(#fmt-wire-out)'}
              strokeWidth="1.5"
              strokeLinecap="round"
              vectorEffect="non-scaling-stroke"
            />
          ))}
        </svg>

        <div className="fmt-col fmt-col--in">
          {inputs.map(({ label, meta, icon: Icon, mode }, i) => (
            <button
              key={label}
              ref={el => { inRefs.current[i] = el; }}
              className="fmt-node fmt-node--in"
              onClick={() => start(mode)}
            >
              <span className="fmt-node__icon"><Icon size={18} aria-hidden="true" /></span>
              <span className="fmt-node__text">
                <b>{label}</b>
                <small>{meta}</small>
              </span>
              <ArrowUpRight size={14} aria-hidden="true" />
            </button>
          ))}
        </div>

        <div className="fmt-core" ref={coreRef}>
          <span className="fmt-core__glow" aria-hidden="true" />
          <b>你的知识</b>
          <small>CONNECTED.</small>
        </div>

        <div className="fmt-col fmt-col--out">
          {outputs.map(({ label, icon: Icon, href, action }, i) => {
            const setRef = (el: HTMLElement | null) => { outRefs.current[i] = el; };
            return href ? (
              <a key={label} ref={setRef as React.Ref<HTMLAnchorElement>} className="fmt-node fmt-node--out" href={href}>
                <Icon size={17} aria-hidden="true" />
                <span>{label}</span>
              </a>
            ) : (
              <button key={label} ref={setRef as React.Ref<HTMLButtonElement>} className="fmt-node fmt-node--out" onClick={action}>
                <Icon size={17} aria-hidden="true" />
                <span>{label}</span>
              </button>
            );
          })}
        </div>
      </div>
    </section>
  );
}

/* ── 来源表 ───────────────────────────────────────────────── */

function Sources() {
  const [tab, setTab] = useState<'paper' | 'repo' | 'book'>('paper');
  const rows = tab === 'paper' ? papers : tab === 'repo' ? repos : books;
  return (
    <section className="fmt-sources" id="welcome-sources" aria-labelledby="sources-title">
      <header className="fmt-head">
        <div>
          <span className="fmt-index">(03 — SOURCES)</span>
          <h2 id="sources-title">每一期，<br /><span>都读到了具体的东西。</span></h2>
        </div>
        <p className="fmt-head__note">
          不是「读过很多」。
          <br />
          是哪一篇、哪个仓库、哪一行写了什么。
        </p>
      </header>

      <div className="fmt-tabs" role="tablist" aria-label="来源类型">
        <button role="tab" id="fmt-tab-paper" aria-controls="fmt-panel-sources"
          aria-selected={tab === 'paper'} onClick={() => setTab('paper')}>
          论文 <small>{papers.length}</small>
        </button>
        <button role="tab" id="fmt-tab-repo" aria-controls="fmt-panel-sources"
          aria-selected={tab === 'repo'} onClick={() => setTab('repo')}>
          开源项目 <small>{repos.length}</small>
        </button>
        <button role="tab" id="fmt-tab-book" aria-controls="fmt-panel-sources"
          aria-selected={tab === 'book'} onClick={() => setTab('book')}>
          书籍 <small>{books.length}</small>
        </button>
        <span className="fmt-tabs__hint">真实条目 · 可回溯到期页</span>
      </div>

      <div className="fmt-table" id="fmt-panel-sources" role="tabpanel" aria-labelledby={`fmt-tab-${tab}`}>
        {rows.map((row, i) => (
          <article key={row.title} className="fmt-row">
            <span className="fmt-row__no">{String(i + 1).padStart(2, '0')}</span>
            <div className="fmt-row__main">
              <h3>{row.title}</h3>
              <p className="fmt-row__by">{row.byline}</p>
              <p className="fmt-row__note">{row.note}</p>
            </div>
            <div className="fmt-row__tags">
              {row.tags.map(tag => <span key={tag}>{tag}</span>)}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

/* ── 最近几期 ─────────────────────────────────────────────── */

function Recent() {
  return (
    <section className="fmt-recent" id="welcome-recent" aria-labelledby="recent-title">
      <header className="fmt-head">
        <div>
          <span className="fmt-index">(04 — RECENT)</span>
          <h2 id="recent-title">每一期，<br /><span>只留一句话。</span></h2>
        </div>
        <a className="fmt-quiet" href="#episodes">
          全部三十九期 <ArrowUpRight size={14} aria-hidden="true" />
        </a>
      </header>

      <div className="fmt-list">
        {featuredEpisodes.map(ep => (
          <a key={ep.no} className="fmt-ep" href={ep.url}>
            <span className="fmt-ep__no">{String(ep.no).padStart(2, '0')}</span>
            <div className="fmt-ep__main">
              <h3>{ep.title}</h3>
              <p>{ep.oneLiner}</p>
            </div>
            <div className="fmt-ep__meta">
              <time dateTime={ep.date}>{ep.date.slice(5)}</time>
              <span>{ep.minutes} 分钟</span>
              <span>{ep.series}</span>
            </div>
            <ArrowUpRight className="fmt-ep__arrow" size={16} aria-hidden="true" />
          </a>
        ))}
      </div>
    </section>
  );
}

/* ── 试听 ─────────────────────────────────────────────────── */

function Listening() {
  return (
    <section className="fmt-listen plate" aria-labelledby="listen-title">
      <div className="plate__copy">
        <span className="fmt-index">(05 — LISTEN)</span>
        <h2 id="listen-title">先听见，<br />再决定。</h2>
        <p>
          同一段文字，两种声音。
          <br />
          都是 AI 合成，不是真人录音。
        </p>
        <a className="fmt-quiet" href="#studio">
          去声音工作室 <ArrowUpRight size={14} aria-hidden="true" />
        </a>
      </div>
      <div className="plate__list">
        {audition.map(a => (
          <article key={a.name} className="fmt-audition">
            <div className="fmt-audition__head">
              <b>{a.name}</b>
              <span>{a.seconds.toFixed(2)}s</span>
            </div>
            <p>{a.subtitle}</p>
            <p className="fmt-audition__dir">{a.direction}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

/* ── 收尾 ─────────────────────────────────────────────────── */

function Closing() {
  return (
    <section className="fmt-closing plate" aria-labelledby="closing-title">
      <div className="fmt-closing__word" aria-hidden="true">
        <GradientWord text="CONNECT" />
      </div>
      <span className="fmt-index">(06 — NEXT)</span>
      <h2 id="closing-title">下一次理解，<br />从这里开始。</h2>
      <div className="fmt-closing__actions">
        <Button asChild variant="default" className="fmt-btn fmt-btn--ink">
          <a href="#studio">
            开始创作 <ArrowUpRight size={16} aria-hidden="true" />
          </a>
        </Button>
        <button className="fmt-quiet" onClick={() => demo('connections')}>
          先看看示例
        </button>
      </div>
      <p className="fmt-closing__note">
        笔记与导图在本机使用。AI 生成使用你连接的服务与额度。
        <br />
        全站 {stats.episodes} 期 · {stats.repos} 个仓库 · {Math.round(stats.chars / 10000)} 万字，全部来自本机归档。
      </p>
    </section>
  );
}

export function NeonLanding() {
  const [active, setActive] = useState(document.body.classList.contains('is-welcome'));
  const reduced = useReducedMotion();

  useEffect(() => {
    const update = () => setActive(document.body.classList.contains('is-welcome'));
    window.addEventListener('sourcecast:navigate', update);
    return () => window.removeEventListener('sourcecast:navigate', update);
  }, []);

  useEffect(() => {
    if (!active || !location.hash.startsWith('#welcome-')) return;
    const frame = requestAnimationFrame(() =>
      document.querySelector(location.hash)?.scrollIntoView({ block: 'start' })
    );
    return () => cancelAnimationFrame(frame);
  }, [active]);

  if (!active) return null;

  return (
    <div className="fmt-landing" data-reduced={reduced}>
      <header className="fmt-nav">
        <Brand />
        <nav aria-label="了解页声">
          <a href="#welcome-workflow">知识汇流</a>
          <a href="#welcome-sources">读到了什么</a>
          <a href="#welcome-recent">最近几期</a>
        </nav>
        <div className="fmt-nav__side">
          <button className="fmt-theme" aria-label="切换明暗"
            onClick={() => document.getElementById('toggleTheme')?.click()}>
            <SunMoon size={16} />
          </button>
          <a className="fmt-quiet" href="#studio">
            进入工作室 <ArrowUpRight size={14} aria-hidden="true" />
          </a>
        </div>
      </header>

      <div className="fmt-canvas">
        <Opening />
        <Fusion reduced={reduced} />
        <Sources />
        <Recent />
        <Listening />
        <Closing />
      </div>

      <footer className="fmt-footer">
        <Brand />
        <span>让好奇，产生连接。</span>
        <a href="sourcecast-source.zip" download>
          下载源码 <ArrowUpRight size={13} aria-hidden="true" />
        </a>
      </footer>
    </div>
  );
}

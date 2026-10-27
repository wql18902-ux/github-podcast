/**
 * frontend/content.test.mjs — content.ts 的反虚构守卫
 *
 * 本仓红线是不编造：书、论文、仓库、日期、判断，每一样都要能追到文件。
 * 这支脚本把 content.ts 里的每一条拿回磁盘逐条核对，查不过就 exit 1。
 * 只用 node 内置能力（node:fs / node:path / node:url），不引任何框架。
 *
 *   node frontend/content.test.mjs
 *
 * 检查 13 组：
 *   1. content.ts 能被求值（剥掉类型注解后当 JS 跑），六个导出都在
 *   2. 零 import、无 default export
 *   3. 每条 KnowledgeSource：title / byline / note / tags 非空，kind 合法
 *   4. episode 真实存在；date 与 episodes.json 那一期完全一致
 *   5. title 全局唯一（书 + 论文 + 仓库三类合并）
 *   6. 每条 source 文件真实存在
 *   7. 每条 note 能在它自己标的 source 文件里【逐字】找到（不是七成重合，是原文）
 *   8. repos 与 episodes.json 的去重仓库集合一一对应，数量 === repo_count
 *   9. 书 / 论文的期号真的引了它（反向核对，拦张冠李戴）
 *  10. stats 六项与 episodes.json 相同
 *  11. featuredEpisodes：6 期、= 最近 6 期、字段与 minutes 口径
 *  12. audition：条数与 seconds 与 auditions.js 一致，且标注 aiGenerated
 *  13. needs / sampleEpisode（2026-10-27 介绍页新增）：主题线、期号、标题、日期、
 *      判断、一句话、仓库全部回源到 episodes.json 与 data.js，一字不改
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(here, '..');

const read = (p) => fs.readFileSync(path.join(ROOT, p), 'utf8');
const exists = (p) => fs.existsSync(path.join(ROOT, p));

const failures = [];
let checks = 0;
function ok(cond, label, detail) {
  checks += 1;
  if (!cond) failures.push(detail ? `${label} — ${detail}` : label);
  return Boolean(cond);
}

/* ── 真实数据 ─────────────────────────────────────────────────────────── */

const lib = JSON.parse(read('web/library/data/episodes.json'));
const curated = JSON.parse(read('web/library/data/curated.json'));
const auditions = JSON.parse(
  read('web/library/data/auditions.js').replace(/^window\.AUDITIONS\s*=\s*/, '').replace(/;\s*$/, '')
);

const library = JSON.parse(
  read('web/library/data.js').replace(/^[\s\S]*?window\.LIB\s*=\s*/, '').replace(/;?\s*$/, '')
);

const eps = lib.episodes;
const byNo = new Map(eps.map((e) => [e.no, e]));
const uniqueRepos = [...new Set(eps.flatMap((e) => e.repos))];

/* ── 1. 求值 content.ts（剥类型注解，纯数据模块可以直接跑） ────────────── */

const ts = read('frontend/content.ts');

function evaluate(tsSource) {
  let js = tsSource.replace(/\/\*[\s\S]*?\*\//g, '');
  js = js.replace(/^\s*export\s+type\s+[\s\S]*?;\s*$/gm, '');
  // export interface X { … }（花括号配平后整块删）
  for (;;) {
    const m = js.match(/^\s*export\s+interface\s+\w+\s*\{/m);
    if (!m) break;
    let depth = 0;
    let i = js.indexOf('{', m.index);
    for (; i < js.length; i += 1) {
      if (js[i] === '{') depth += 1;
      else if (js[i] === '}' && --depth === 0) {
        i += 1;
        break;
      }
    }
    js = js.slice(0, m.index) + js.slice(i);
  }
  // const stats: { … } = {   ← 多行对象类型
  js = js.replace(/(export\s+const\s+\w+)\s*:\s*\{[\s\S]*?\}\s*=\s*\{/g, '$1 = {');
  // 其余 const x: T =  /  const x: T[] = [
  js = js.replace(/(export\s+const\s+\w+)\s*:\s*[^=]+=\s*/g, '$1 = ');
  js = js.replace(/export\s+const\s+(\w+)/g, 'globalThis.$1');
  return new Function(js + '\nreturn globalThis;')();
}

let content;
try {
  content = evaluate(ts);
  ok(true, 'content.ts 可被求值');
} catch (err) {
  console.error('✗ content.ts 无法求值：', err.message);
  process.exit(1);
}

const { books, papers, repos, featuredEpisodes, stats, audition, CHARS_PER_MINUTE, needs, sampleEpisode } = content;

/* ── 2. 导出形状 / 零依赖 ─────────────────────────────────────────────── */

for (const [name, value, isArray] of [
  ['books', books, true],
  ['papers', papers, true],
  ['repos', repos, true],
  ['featuredEpisodes', featuredEpisodes, true],
  ['audition', audition, true],
  ['needs', needs, true],
  ['stats', stats, false],
  ['sampleEpisode', sampleEpisode, false],
]) {
  ok(value != null && (isArray ? Array.isArray(value) && value.length > 0 : typeof value === 'object'), `${name} 已导出且非空`);
}
ok(!ts.includes('export default'), '没有 default export');
ok(!/^\s*import\s/m.test(ts), '没有 import（保持零依赖，可被 Vite 直接编译）');
ok(typeof CHARS_PER_MINUTE === 'number' && CHARS_PER_MINUTE === 175, 'CHARS_PER_MINUTE === 175', String(CHARS_PER_MINUTE));

/* ── 3. 从源码抓「source 注释 + 条目字段」配对 ─────────────────────────
   形如
     {
     // source: output/episodes/ep12-…/page.md + …
       kind: 'repo',
       title: '…',
   ─────────────────────────────────────────────────────────────────── */

function parseEntries(blockName) {
  const start = ts.indexOf(`export const ${blockName}`);
  if (start < 0) return [];
  const open = ts.indexOf('[', start);
  const close = ts.indexOf('\n];', open);
  const body = ts.slice(open, close);
  const entries = [];
  const re = /\{\s*\n\s*\/\/\s*source:\s*([^\n]+)\n([\s\S]*?)\n\s{2}\},?/g;
  let m;
  while ((m = re.exec(body))) {
    const obj = m[2];
    const str = (k) => {
      const mm = obj.match(new RegExp(`${k}:\\s*'((?:[^'\\\\]|\\\\.)*)'`));
      return mm ? mm[1].replace(/\\'/g, "'").replace(/\\\\/g, '\\') : null;
    };
    const num = (k) => {
      const mm = obj.match(new RegExp(`${k}:\\s*(-?\\d+(?:\\.\\d+)?)`));
      return mm ? Number(mm[1]) : null;
    };
    // tags 数组（单引号字符串数组）
    const tagsRaw = obj.match(/tags:\s*\[([^\]]*)\]/);
    const tags = tagsRaw
      ? [...tagsRaw[1].matchAll(/'((?:[^'\\]|\\.)*)'/g)].map((x) => x[1])
      : [];
    entries.push({
      source: m[1].trim(),
      kind: str('kind'),
      title: str('title'),
      byline: str('byline'),
      note: str('note'),
      episode: num('episode'),
      date: str('date'),
      tags,
    });
  }
  return entries;
}

const groups = {
  books: parseEntries('books'),
  papers: parseEntries('papers'),
  repos: parseEntries('repos'),
};

for (const [name, list] of Object.entries(groups)) {
  ok(list.length > 0, `${name}: 解析到条目`, `实际 ${list.length}`);
  ok(
    list.length === (name === 'books' ? books.length : name === 'papers' ? papers.length : repos.length),
    `${name}: 源码条目数与数组长度一致`,
    `${list.length} vs ${name === 'books' ? books.length : name === 'papers' ? papers.length : repos.length}`
  );
}

/* ── 4. 字段 / 期号 / 日期 ────────────────────────────────────────────── */

const all = [
  ...groups.books.map((x) => ({ ...x, group: 'books' })),
  ...groups.papers.map((x) => ({ ...x, group: 'papers' })),
  ...groups.repos.map((x) => ({ ...x, group: 'repos' })),
];

for (const e of all) {
  const label = `${e.group} · ${e.title || '(无标题)'}`;
  ok(typeof e.title === 'string' && e.title.trim().length > 0, `${label}: title 非空`);
  ok(typeof e.byline === 'string' && e.byline.trim().length > 0, `${label}: byline 非空`);
  ok(typeof e.note === 'string' && e.note.trim().length > 0, `${label}: note 非空`);
  ok(e.tags.length > 0, `${label}: tags 非空`);
  ok(['book', 'paper', 'repo'].includes(e.kind), `${label}: kind 合法`, String(e.kind));
  const known = Number.isInteger(e.episode) && byNo.has(e.episode);
  ok(known, `${label}: 期号在 episodes.json 里`, `episode=${e.episode}`);
  if (known) ok(e.date === byNo.get(e.episode).date, `${label}: date 与那一期一致`, `${e.date} vs ${byNo.get(e.episode).date}`);
}

/* ── 5. title 全局唯一 ───────────────────────────────────────────────── */

{
  const seen = new Map();
  for (const e of all) {
    if (seen.has(e.title)) ok(false, `title 重复：${e.title}`, `${seen.get(e.title)} 与 ${e.group}`);
    else seen.set(e.title, e.group);
  }
  ok(true, 'title 唯一性已检查', `${seen.size} 个 title`);
}

/* ── 6+7. source 文件存在，且 note 能在里面逐字找到 ─────────────────────
   note 的生成方式就是「从源文件里抄一句」，所以这里做严格子串比对（去掉
   markdown 记号与空白后）。找不到 = 不是抄的 = 编的。
   ─────────────────────────────────────────────────────────────────── */

const strip = (x) =>
  String(x)
    .replace(/[`*_]/g, '')
    .replace(/\s+/g, '')
    .replace(/[。；，、！？：]$/, '');

const cache = new Map();
function textOf(rel) {
  if (!cache.has(rel)) cache.set(rel, exists(rel) ? strip(read(rel)) : null);
  return cache.get(rel);
}

let verbatim = 0;
for (const e of all) {
  const label = `${e.group} · ${e.title || '(无标题)'}`;
  const files = e.source.split('+').map((s) => s.trim()).filter(Boolean);
  ok(files.length > 0, `${label}: source 注释里有路径`);

  let allExist = true;
  for (const f of files) {
    if (!exists(f)) {
      allExist = false;
      ok(false, `${label}: source 文件不存在`, f);
    }
  }
  ok(allExist, `${label}: source 文件都存在`);

  const needle = strip(e.note);
  const found = files.some((f) => {
    const t = textOf(f);
    return t !== null && t.includes(needle);
  });
  if (found) verbatim += 1;
  ok(found, `${label}: note 在 source 文件里逐字找到`, `note 开头「${(e.note || '').slice(0, 40)}…」`);
}

/* ── 8. repos 与 episodes.json 完全对应 ─────────────────────────────── */

{
  const want = new Set(uniqueRepos);
  const got = new Set(groups.repos.map((r) => r.title));
  ok(got.size === groups.repos.length, 'repos 内部无重复', `${got.size} vs ${groups.repos.length}`);
  ok(got.size === want.size, 'repos 数量 === episodes.json 去重仓库数', `${got.size} vs ${want.size}`);
  const missing = [...want].filter((r) => !got.has(r));
  const extra = [...got].filter((r) => !want.has(r));
  ok(missing.length === 0, 'repos 覆盖了全部仓库', missing.slice(0, 3).join(', '));
  ok(extra.length === 0, 'repos 没有多余仓库', extra.slice(0, 3).join(', '));
  ok(got.size === lib.repo_count, 'repos 数量 === repo_count', `${got.size} vs ${lib.repo_count}`);
}

/* ── 9. 反向核对：书 / 论文的期号真的引了它 ─────────────────────────── */

function episodeCorpus(no) {
  const ep = byNo.get(no);
  if (!ep) return '';
  const dir = `output/episodes/${ep.slug}`;
  // 早期几期的正文在 output/ 下（ep1 的稿子），标题里能读出来但目录里没有
  const parts = [];
  if (exists(`${dir}/page.md`)) parts.push(read(`${dir}/page.md`));
  if (exists(dir)) {
    for (const f of fs.readdirSync(path.join(ROOT, dir))) {
      if (/\.md$/.test(f)) parts.push(read(`${dir}/${f}`));
    }
  }
  return strip(parts.join('\n'));
}

for (const e of [...groups.books, ...groups.papers]) {
  const hay = episodeCorpus(e.episode);
  const bare = e.title.split(/（|\(/)[0].trim();
  // 论文的题名往往只在 README / CITATION.bib 里出现（例如 SWE-smith、OSWorld、
  // Hypothesis 的正式标题），而那一期页面是用**系统名**指代它的。所以这里同时
  // 接受「冒号前的系统名」与「中文书名 / 期刊名」作为探针。
  const system = (bare.split(':')[0] || '').trim();
  const latin = (bare.match(/[A-Za-z][A-Za-z0-9+._-]{3,}/g) || []).sort((a, b) => b.length - a.length)[0];
  const cjk = (bare.match(/[\u4e00-\u9fa5]{2,}/g) || []).join('');
  const probes = [
    strip(bare),
    system.length >= 3 ? strip(system) : null,
    latin ? strip(latin) : null,
    cjk.length >= 4 ? cjk.slice(0, 8) : null,
  ].filter((x) => x && x.length >= 2);
  const found = probes.some((p) => hay.includes(p));
  ok(
    found,
    `ep${e.episode} 真的引了「${e.title.slice(0, 40)}」`,
    `试过 ${probes.map((x) => `「${x}」`).join(' / ')}`
  );
}

/* ── 10. stats 与 episodes.json 一致 ────────────────────────────────── */

ok(stats.episodes === lib.count, 'stats.episodes === count', `${stats.episodes} vs ${lib.count}`);
ok(stats.judgments === lib.judgment_count, 'stats.judgments === judgment_count', `${stats.judgments} vs ${lib.judgment_count}`);
ok(stats.repos === lib.repo_count, 'stats.repos === repo_count', `${stats.repos} vs ${lib.repo_count}`);
ok(stats.chars === lib.chars_total, 'stats.chars === chars_total', `${stats.chars} vs ${lib.chars_total}`);
ok(
  Math.abs(stats.audioHours - Math.round((lib.audio_minutes / 60) * 10) / 10) < 1e-9,
  'stats.audioHours === audio_minutes ÷ 60（一位小数）',
  `${stats.audioHours} vs ${lib.audio_minutes}/60`
);
ok(stats.span === `${lib.first_date} — ${lib.last_date}`, 'stats.span === first_date — last_date', stats.span);

/* ── 11. featuredEpisodes ───────────────────────────────────────────── */

{
  const withOneLiner = eps.filter((e) => e.one_liner && e.one_liner.trim());
  const want = withOneLiner.slice(-6).map((e) => e.no);
  ok(featuredEpisodes.length === 6, 'featuredEpisodes 恰好 6 期', `实际 ${featuredEpisodes.length}`);
  ok(
    featuredEpisodes.every((f, i) => f.no === want[i]),
    'featuredEpisodes === 有 one_liner 的那 20 期里最近 6 期',
    `实际 ${featuredEpisodes.map((f) => f.no).join(',')} 期望 ${want.join(',')}`
  );
  for (const f of featuredEpisodes) {
    const ep = byNo.get(f.no);
    if (!ok(Boolean(ep), `featured ep${f.no} 在 episodes.json 里`)) continue;
    ok(f.title === ep.title, `featured ep${f.no} title 一致`);
    ok(f.date === ep.date, `featured ep${f.no} date 一致`);
    ok(f.chars === ep.chars, `featured ep${f.no} chars 一致`);
    ok(f.series === ep.series, `featured ep${f.no} series 一致`);
    ok(f.oneLiner === ep.one_liner, `featured ep${f.no} oneLiner 与 episodes.json 一致`);
    ok(f.minutes === Math.round(ep.chars / 175), `featured ep${f.no} minutes === round(chars/175)`, `${f.minutes}`);
    ok(typeof f.url === 'string' && f.url.startsWith('#'), `featured ep${f.no} 有站内 url`, String(f.url));
    const c = curated[String(f.no)];
    if (ok(Boolean(c), `curated.json 有 ep${f.no} 精修层`)) {
      ok(c.one_liner === f.oneLiner, `ep${f.no} oneLiner 与 curated.json 一致`);
    }
  }
}

/* ── 12. audition ──────────────────────────────────────────────────── */

{
  ok(audition.length === auditions.items.length, 'audition 条数 === auditions.js items', `${audition.length} vs ${auditions.items.length}`);
  for (let i = 0; i < audition.length; i += 1) {
    const a = audition[i];
    const b = auditions.items[i];
    ok(a.name === b.name, `audition[${i}] name 一致`);
    ok(a.subtitle === b.subtitle, `audition[${i}] subtitle 一致`);
    ok(a.seconds === b.seconds, `audition[${i}] seconds 一致`, `${a.seconds} vs ${b.seconds}`);
    ok(a.direction === b.direction, `audition[${i}] direction 一致`);
  }
  ok(auditions.aiGenerated === true, 'auditions.js 标了 aiGenerated = true（页面上必须写明 AI 合成）');
}

/* ── 13. 介绍页「按需求找期」与样本期 ────────────────────────────────
   needs 的每一条都必须能回到 episodes.json：主题线真实存在、条数对得上、
   点开的那一期期号 / 标题 / 日期一字不差。sampleEpisode 的三条判断、一句话、
   仓库都要在 data.js 的 window.LIB 里逐字找到（这是页面上「逐字摘自原稿」的凭据）。
   ─────────────────────────────────────────────────────────────────── */

{
  const series = new Set(eps.map((e) => e.series));
  const seriesCount = (name) => eps.filter((e) => e.series === name).length;
  ok(needs.length === series.size, `needs 覆盖全部主题线`, `${needs.length} vs ${series.size}`);
  const seen = new Set();
  for (const need of needs) {
    ok(series.has(need.series), `needs「${need.series}」是 episodes.json 里的主题线`);
    ok(!seen.has(need.series), `needs「${need.series}」只出现一次`);
    seen.add(need.series);
    ok(need.count === seriesCount(need.series), `needs「${need.series}」期数与 episodes.json 一致`, `${need.count} vs ${seriesCount(need.series)}`);
    const pick = byNo.get(need.pick.no);
    ok(Boolean(pick), `needs「${need.series}」的期号 EP${need.pick.no} 真实存在`);
    if (pick) {
      ok(pick.series === need.series, `needs「${need.series}」点开的那一期确实属于这条线`, `EP${pick.no} 是 ${pick.series}`);
      ok(pick.title === need.pick.title, `needs EP${need.pick.no} 标题一字不差`, `${pick.title} vs ${need.pick.title}`);
      ok(pick.date === need.pick.date, `needs EP${need.pick.no} 日期一字不差`, `${pick.date} vs ${need.pick.date}`);
    }
    ok(typeof need.question === 'string' && need.question.trim().length > 0, `needs「${need.series}」问题非空`);
    ok(typeof need.help === 'string' && need.help.trim().length > 0, `needs「${need.series}」文案非空`);
  }
  const sample = library.episodes.find((e) => e.no === sampleEpisode.no);
  ok(Boolean(sample), `sampleEpisode EP${sampleEpisode.no} 真实存在`);
  if (sample) {
    ok(sample.title === sampleEpisode.title, 'sampleEpisode 标题一字不差', `${sample.title} vs ${sampleEpisode.title}`);
    ok(sample.date === sampleEpisode.date, 'sampleEpisode 日期一字不差', `${sample.date} vs ${sampleEpisode.date}`);
    ok(sample.series === sampleEpisode.series, 'sampleEpisode 主题线一字不差', `${sample.series} vs ${sampleEpisode.series}`);
    ok(sample.one_liner === sampleEpisode.oneLiner, 'sampleEpisode 一句话一字不差', `${sample.one_liner} vs ${sampleEpisode.oneLiner}`);
    ok(sample.judgments.length === sampleEpisode.judgments.length, 'sampleEpisode 判断条数一致', `${sample.judgments.length} vs ${sampleEpisode.judgments.length}`);
    sampleEpisode.judgments.forEach((judgment, i) => {
      ok(sample.judgments[i] === judgment, `sampleEpisode 第 ${i + 1} 条判断逐字一致`, `${sample.judgments[i]} vs ${judgment}`);
    });
    ok(JSON.stringify(sample.repos) === JSON.stringify(sampleEpisode.repos), 'sampleEpisode 仓库列表一字不差', `${sample.repos.join(',')} vs ${sampleEpisode.repos.join(',')}`);
  }
}

/* ── 报告 ─────────────────────────────────────────────────────────── */

const line = '─'.repeat(50);
console.log('\n页声 Sourcecast · content.ts 内容核对');
console.log(line);
console.log(`书籍              ${String(groups.books.length).padStart(4)} 条`);
console.log(`论文 / 期刊       ${String(groups.papers.length).padStart(4)} 条`);
console.log(`开源项目          ${String(groups.repos.length).padStart(4)} 条`);
console.log(`最近六期          ${String(featuredEpisodes.length).padStart(4)} 期  (${featuredEpisodes.map((f) => 'EP' + f.no).join(' ')})`);
console.log(`真实试听          ${String(audition.length).padStart(4)} 段`);
console.log(`按需求找期        ${String(needs.length).padStart(4)} 条（覆盖 ${new Set(needs.map((n) => n.series)).size} 条主题线）`);
console.log(`样本期            EP${sampleEpisode.no} · ${sampleEpisode.judgments.length} 条判断 + 1 句话`);
console.log(line);
console.log(`逐字回源          ${String(verbatim).padStart(4)} / ${all.length} 条 note 在它标的文件里找到原文`);
console.log(`全库统计          ${stats.episodes} 期 · ${stats.judgments} 条判断 · ${stats.repos} 个仓库 · ${stats.chars} 汉字`);
console.log(`音频时长          ${stats.audioHours} 小时（episodes.json 的 ${lib.audio_minutes} 分钟）`);
console.log(`跨期              ${stats.span}`);
const bookEps = [...new Set(groups.books.map((b) => b.episode))].sort((a, b) => a - b);
const paperEps = [...new Set(groups.papers.map((p) => p.episode))].sort((a, b) => a - b);
console.log(`书的期号          ${bookEps.map((n) => 'EP' + n).join(' ') || '（无）'}`);
console.log(`论文的期号        ${paperEps.map((n) => 'EP' + n).join(' ') || '（无）'}`);
console.log(line);

if (failures.length) {
  console.error(`\n✗ ${failures.length} 项不通过（共 ${checks} 项检查）：`);
  for (const f of failures.slice(0, 40)) console.error('  - ' + f);
  if (failures.length > 40) console.error(`  …还有 ${failures.length - 40} 项`);
  process.exit(1);
}
console.log(`\n✓ 全部 ${checks} 项通过：标题、期号、日期、统计、试听都对得上，每条 note 都能回源到原文。`);
process.exit(0);

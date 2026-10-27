/* 页声 · Sourcecast v2 —— 前端（零框架、零外链、零追踪）
   数据：window.LIB（期次/判断）+ window.STYLES/VOICES（创作台内容）
   语音生成仅使用访客自己填写的 API Key；本页没有作者额度或本机桥接入口。 */
(() => {
  "use strict";

  const LIB = window.LIB || { episodes: [], series_meta: [] };
  const EPS = (LIB.episodes || []).slice();
  const STYLES = window.STYLES || [];
  const VOICES = window.VOICES || [];

  const SAVE_KEY = "zhizhan.saved.v2";
  const THEME_KEY = document.documentElement.dataset.sourcecast === "neon" ? "sourcecast.neon.theme.v1" : "zhizhan.theme";
  const PAGE = 12;

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

  const ALL = [];
  EPS.forEach((ep) => (ep.judgments || []).forEach((t, i) => ALL.push({ text: t, ep, i })));

  const SERIES_COLOR = {};
  (LIB.series_meta || []).forEach((m) => { SERIES_COLOR[m.name] = m.color; });
  const colorOf = (ep) => ep.color || SERIES_COLOR[ep.series] || "#9a978e";

  const state = {
    q: "",
    series: "",
    expanded: false,
    saved: new Set(load(SAVE_KEY, [])),
    style: STYLES[0],
    voice: null,
    mem: load("sourcecast.memory.terms.v1", null),
    graph: null,
  };

  /* ── 小工具 ─────────────────────────────────── */

  function load(k, d) {
    try { const v = JSON.parse(localStorage.getItem(k)); return v == null ? d : v; }
    catch { return d; }
  }
  function save(k, v) {
    try { localStorage.setItem(k, JSON.stringify(v)); } catch {}
  }
  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function mark(text, q) {
    const safe = esc(text);
    if (!q) return safe;
    const words = q.split(/\s+/).filter(Boolean).map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
    if (!words.length) return safe;
    try { return safe.replace(new RegExp(`(${words.join("|")})`, "gi"), "<mark>$1</mark>"); }
    catch { return safe; }
  }
  const epLabel = (ep) => `ep${ep.no}`;
  const epShort = (ep) => {
    const t = ep.title || ep.slug;
    return t.length > 24 ? t.slice(0, 23) + "…" : t;
  };

  let toastTimer = null;
  function toast(msg) {
    const el = $("#toast");
    el.textContent = msg;
    el.classList.add("is-on");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("is-on"), 2200);
  }

  async function copyText(text, okMsg) {
    try { await navigator.clipboard.writeText(text); toast(okMsg || "已复制"); }
    catch { toast("这个浏览器不让写剪贴板"); }
  }

  function download(name, text, mime) {
    const blob = new Blob([text], { type: mime || "text/plain;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2500);
  }

  /* ── 判断库 ─────────────────────────────────── */

  function matchJ(j, q) {
    if (!q) return true;
    const hay = `${j.text} ${epShort(j.ep)} ${j.ep.series || ""}`.toLowerCase();
    return q.toLowerCase().split(/\s+/).filter(Boolean).every((w) => hay.includes(w.toLowerCase()));
  }

  function filtered() {
    return ALL.filter((j) => (!state.series || j.ep.series === state.series) && matchJ(j, state.q));
  }

  function renderFilters() {
    const host = $("#seriesFilters");
    const counts = {};
    EPS.forEach((ep) => { counts[ep.series] = (counts[ep.series] || 0) + 1; });
    const items = [["", "全部"]].concat(Object.keys(counts).map((s) => [s, s]));
    host.innerHTML = items.map(([k, label]) => {
      const n = k ? counts[k] : EPS.length;
      const dot = k ? `<i class="dot" style="--sc:${esc(SERIES_COLOR[k] || "#9a978e")}"></i>` : "";
      return `<button class="chip ${state.series === k ? "is-on" : ""}" data-series="${esc(k)}" aria-pressed="${state.series === k}">${dot}${esc(label)}<span class="n">${n}</span></button>`;
    }).join("");
  }

  function renderJudgments() {
    const list = filtered();
    const host = $("#jgrid");
    const limit = state.expanded || state.q || state.series ? list.length : Math.min(PAGE, list.length);
    const shown = list.slice(0, limit);

    $("#resultCount").textContent = `${list.length} 条`;
    $("#jempty").hidden = list.length > 0;
    if (!list.length) {
      $("#jempty").innerHTML = state.q
        ? `没搜到「<b>${esc(state.q)}</b>」。换个词试试：备份 · 过期 · 模型 · 交接 · 静默`
        : `这条主题线暂时没有判断。点「全部」看五十条。`;
    }

    host.innerHTML = shown.map((j) => {
      const id = `${j.ep.slug}#${j.i}`;
      const on = state.saved.has(id);
      return `<article class="jcard" style="--sc:${esc(colorOf(j.ep))}">
        <p class="jcard__text" data-open="${esc(j.ep.slug)}">${mark(j.text, state.q)}</p>
        <div class="jcard__foot">
          <button class="jcard__ep" data-open="${esc(j.ep.slug)}">${epLabel(j.ep)}</button>
          <span>${esc(j.ep.series || "—")}</span>
          <button class="save ${on ? "is-on" : ""}" data-save="${esc(id)}" aria-pressed="${on}">
            <svg width="11" height="11" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M4 2.5h8v11l-4-2.6-4 2.6z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg>
            ${on ? "已收" : "收藏"}
          </button>
        </div>
      </article>`;
    }).join("");

    $$("[data-open]", host).forEach((b) => b.addEventListener("click", () => openEp(b.dataset.open)));
    $$("[data-save]", host).forEach((b) => b.addEventListener("click", () => toggleSave(b.dataset.save)));

    const more = $("#expandJudgments");
    const rest = list.length - shown.length;
    more.hidden = rest <= 0;
    $("#moreCount").textContent = rest > 0 ? `（还有 ${rest} 条）` : "";
  }

  /* ── 收藏 ───────────────────────────────────── */

  function toggleSave(id) {
    if (state.saved.has(id)) { state.saved.delete(id); toast("已从清单移除"); }
    else { state.saved.add(id); toast("已收进清单 · 右上角书签查看"); }
    save(SAVE_KEY, Array.from(state.saved));
    syncSaved();
  }

  function savedEntries() {
    return Array.from(state.saved).map((id) => {
      const [slug, idx] = id.split("#");
      const ep = EPS.find((e) => e.slug === slug);
      const text = ep && ep.judgments[Number(idx)];
      return text ? { id, text, ep } : null;
    }).filter(Boolean);
  }

  function syncSaved() {
    const n = state.saved.size;
    const badge = $("#savedCount");
    badge.textContent = String(n);
    badge.classList.toggle("is-on", n > 0);
    $$("[data-save]").forEach((b) => {
      const on = state.saved.has(b.dataset.save);
      b.classList.toggle("is-on", on);
      b.setAttribute("aria-pressed", String(on));
      if (b.lastChild && b.lastChild.nodeType === 3) b.lastChild.textContent = on ? "已收" : "收藏";
    });
    if ($("#mydrawer").classList.contains("is-open")) renderSaved();
  }

  function renderSaved() {
    const rows = savedEntries();
    const body = $("#myBody");
    if (!rows.length) {
      body.innerHTML = `<div class="empty">清单还是空的。<br>在判断库里点 <b>收藏</b>，把要带走的那几句攒起来。</div>`;
      return;
    }
    body.innerHTML = `
      <p class="drawer__sub" style="margin-top:0">${rows.length} 条 · 存在这台设备的浏览器里，不上传任何地方。</p>
      <div class="mylist">${rows.map((r) => `
        <div class="myitem">
          <div>
            <div class="myitem__t">「${esc(r.text)}」</div>
            <div class="myitem__m">${epLabel(r.ep)} · ${esc(epShort(r.ep))}${r.ep.series ? " · " + esc(r.ep.series) : ""}</div>
          </div>
          <button class="save is-on" data-rm="${esc(r.id)}" aria-label="移除">
            <svg width="11" height="11" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M3 3l10 10M13 3L3 13" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>
          </button>
        </div>`).join("")}
      </div>
      <div class="exportbar">
        <button class="btn btn--ink" id="copyMd">复制 Markdown</button>
        <button class="btn btn--line" id="dlMd">下载 .md</button>
        <button class="btn btn--line" id="clearAll">清空</button>
      </div>`;

    $$("[data-rm]", body).forEach((b) => b.addEventListener("click", () => {
      state.saved.delete(b.dataset.rm);
      save(SAVE_KEY, Array.from(state.saved));
      syncSaved();
      renderSaved();
    }));
    $("#copyMd").addEventListener("click", () => copyText(toMarkdown(rows), "已复制，可以直接粘到笔记里"));
    $("#dlMd").addEventListener("click", () => {
      download("我的判断清单.md", toMarkdown(rows), "text/markdown;charset=utf-8");
      toast("已下载");
    });
    $("#clearAll").addEventListener("click", () => {
      state.saved.clear();
      save(SAVE_KEY, []);
      syncSaved();
      renderSaved();
      toast("清单已清空");
    });
  }

  function toMarkdown(rows) {
    const d = new Date();
    const stamp = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    return [
      "# 我的判断清单",
      "",
      `> 摘自《页声 · Sourcecast》· ${EPS.length} 期 AI 技术播客 · 导出于 ${stamp}`,
      "",
      ...rows.map((r, i) => `${i + 1}. 「${r.text}」\n   —— ${epLabel(r.ep)} ${epShort(r.ep)}${r.ep.series ? " · " + r.ep.series : ""}`),
      "",
    ].join("\n");
  }

  /* ── 期次 ───────────────────────────────────── */

  function renderEpisodes() {
    const host = $("#eplist");
    const list = EPS.filter((ep) => !state.series || ep.series === state.series).slice().reverse();
    let lastMonth = "";
    host.innerHTML = list.map((ep) => {
      const monthHead = ep.month && ep.month !== lastMonth
        ? `<div class="month"><span>${esc(ep.month.replace("-", " 年 "))} 月</span><i></i></div>`
        : "";
      lastMonth = ep.month || lastMonth;
      const tags = [
        ep.judgments.length ? `<span class="tag tag--judge">${ep.judgments.length} 条</span>` : "",
        ep.series ? `<span class="tag">${esc(ep.series)}</span>` : "",
      ].join("");
      const desc = ep.one_liner || ep.subtitle || (ep.repos.length ? ep.repos.join(" · ") : "—");
      return `${monthHead}<button class="eprow" data-open="${esc(ep.slug)}" style="--sc:${esc(colorOf(ep))}">
        <span class="eprow__no"><i class="dot"></i>${String(ep.no).padStart(2, "0")}</span>
        <span class="eprow__main">
          <span class="eprow__t">${esc(ep.title || ep.slug)}<span class="date">${esc(ep.date || "")}</span></span>
          <span class="eprow__s">${esc(desc)}</span>
        </span>
        <span class="eprow__tags">${tags}</span>
        <span class="eprow__go" aria-hidden="true">→</span>
      </button>`;
    }).join("");
    $$("[data-open]", host).forEach((b) => b.addEventListener("click", () => openEp(b.dataset.open)));
  }

  /* ── 抽屉 ───────────────────────────────────── */

  let lastFocus = null;

  function openEp(slug) {
    const ep = EPS.find((e) => e.slug === slug);
    if (!ep) return;
    lastFocus = document.activeElement;
    $("#dNo").textContent = `EP ${String(ep.no).padStart(2, "0")}`;

    const finished = (window.FINISHED_AUDIO?.items || []).find(x => x.slug === ep.slug);
    const audio = `<div class="dhead">收听</div>
         ${finished
           ? `<button class="btn btn--ink" data-play-ep="${esc(finished.id)}">播放这一期 · ${esc(finished.meta)}</button>
              <p class="player__cap">成品音频，点开即播；不调用生成服务，也不消耗额度。</p>`
           : `<p class="player__cap">这一期只有文字，还没有上传音频。内容与判断都保留在这里。</p>`}`;

    const judges = ep.judgments.length
      ? `<div class="dhead">这一期能带走的判断</div>
         <div class="jlist">${ep.judgments.map((t, i) => `
            <div class="jitem">
              <span class="jitem__i">${String(i + 1).padStart(2, "0")}</span>
              <span class="jitem__t">${esc(t)}</span>
              <button class="save ${state.saved.has(`${ep.slug}#${i}`) ? "is-on" : ""}" data-save="${esc(ep.slug)}#${i}" aria-label="收藏">
                <svg width="11" height="11" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M4 2.5h8v11l-4-2.6-4 2.6z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg>
              </button>
            </div>`).join("")}
         </div>`
      : `<div class="dhead">这一期能带走的判断</div>
         <p class="player__cap">这一期的页面里没有单独提炼判断——前十期记的是细节台账，判断是从第 20 期起才单独立成一节。</p>`;

    const repos = ep.repos.length
      ? `<div class="dhead">讲过的仓库</div><div class="ep-repos">${ep.repos.map((r) => `<span>${esc(r)}</span>`).join("")}</div>`
      : "";

    const rel = ep.related && ep.related.length
      ? `<div class="dhead">相关期次</div><div class="rel">${ep.related.map((s) => {
          const t = EPS.find((e) => e.slug === s);
          return `<button data-goto="${esc(s)}">${t ? `${epLabel(t)} · ${esc(epShort(t))}` : esc(s)}</button>`;
        }).join("")}</div>`
      : "";

    $("#drawer").style.setProperty("--sc", colorOf(ep));
    $("#dBody").innerHTML = `
      <h2 id="dTitle">${esc(ep.title || ep.slug)}</h2>
      ${ep.subtitle ? `<p class="drawer__sub">${esc(ep.subtitle)}</p>` : ""}
      <div class="drawer__meta">
        ${ep.date ? `<span class="tag">${esc(ep.date)}</span>` : ""}
        ${ep.series ? `<span class="tag">${esc(ep.series)}</span>` : ""}
        ${ep.question ? `<span class="tag">${esc(ep.question)}</span>` : ""}
      </div>
      ${ep.one_liner ? `<blockquote class="oneliner">${esc(ep.one_liner)}</blockquote>` : ""}
      ${audio}${judges}${repos}${rel}`;

    $$("[data-save]", $("#dBody")).forEach((b) => b.addEventListener("click", () => toggleSave(b.dataset.save)));
    $$("[data-goto]", $("#dBody")).forEach((b) => b.addEventListener("click", () => openEp(b.dataset.goto)));
    $$("[data-play-ep]", $("#dBody")).forEach((b) => b.addEventListener("click", () => {
      hideDrawers();
      if (window.Sourcecast?.playItem) window.Sourcecast.playItem(b.dataset.playEp);
    }));
    showDrawer("#drawer");
  }

  function showDrawer(sel) {
    $$(".drawer").forEach(d=>{d.classList.remove("is-open");d.setAttribute("aria-hidden","true");});
    lastFocus = document.activeElement;
    $("main").inert = true; $(".sidebar").inert = true; $(".workspace-bar").inert = true;
    $("#scrim").classList.add("is-open");
    $(sel).classList.add("is-open");
    $(sel).setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
    const first = $(sel).querySelector("button, a, input, textarea");
    if (first) setTimeout(() => first.focus({ preventScroll: true }), 60);
  }

  function hideDrawers() {
    ["#drawer", "#mydrawer", "#clonedrawer"].forEach((s) => {
      $(s).classList.remove("is-open");
      $(s).setAttribute("aria-hidden", "true");
    });
    $("#scrim").classList.remove("is-open");
    document.body.style.overflow = "";
    $("main").inert = false; $(".sidebar").inert = false; $(".workspace-bar").inert = false;
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  $("#scrim").addEventListener("click", hideDrawers);
  $("#dClose").addEventListener("click", hideDrawers);
  $("#myClose").addEventListener("click", hideDrawers);
  $("#cloneClose").addEventListener("click", hideDrawers);
  $("#openSaved").addEventListener("click", () => { renderSaved(); showDrawer("#mydrawer"); });

  /* ── 今日一条 / 随机 ─────────────────────────── */

  function dailyPick() {
    if (!ALL.length) return null;
    const d = new Date();
    return ALL[(d.getFullYear() * 10000 + (d.getMonth() + 1) * 100 + d.getDate()) % ALL.length];
  }

  function renderDaily(j, animate) {
    const host = $("#daily");
    if (!j) { host.hidden = true; return; }
    host.hidden = false;
    const id = `${j.ep.slug}#${j.i}`;
    const on = state.saved.has(id);
    host.innerHTML = `
      <span class="daily__tag">今日一条</span>
      <p class="daily__q">${esc(j.text)}</p>
      <div class="daily__meta">
        <a href="#" data-open="${esc(j.ep.slug)}">${epLabel(j.ep)} · ${esc(epShort(j.ep))}</a>
        <span>${esc(j.ep.series || "")}</span>
        <span>${esc(j.ep.date || "")}</span>
        <span class="daily__acts">
          <button class="minibtn ${on ? "is-on" : ""}" data-save="${esc(id)}">${on ? "已收" : "收藏"}</button>
          <button class="minibtn" id="nextDaily">换一条</button>
        </span>
      </div>`;
    $$("[data-save]", host).forEach((b) => b.addEventListener("click", () => toggleSave(b.dataset.save)));
    $("#nextDaily", host).addEventListener("click", rollOne);
    $$("[data-open]", host).forEach((b) => b.addEventListener("click", (e) => { e.preventDefault(); openEp(b.dataset.open); }));

    if (animate) {
      $(".daily__q", host).animate(
        [{ opacity: 0, transform: "translateY(6px)" }, { opacity: 1, transform: "none" }],
        { duration: 320, easing: "cubic-bezier(.2,.7,.2,1)" }
      );
    }
  }

  function rollOne() {
    if (!ALL.length) return;
    renderDaily(ALL[Math.floor(Math.random() * ALL.length)], true);
    toast("换了一条");
  }
  $("#rollBtn")?.addEventListener("click", rollOne);
  $("#dailyRoll").addEventListener("click", () => {
    $("#daily").scrollIntoView({ behavior: "smooth", block: "center" });
    setTimeout(rollOne, 240);
  });

  /* ── 形状条 ─────────────────────────────────── */

  function renderSpine() {
    const host = $("#spine");
    const max = Math.max(...EPS.map((e) => e.chars || 0), 1);
    host.innerHTML = EPS.map((ep) => {
      const h = Math.max(4, Math.round(((ep.chars || 0) / max) * 100));
      const label = `ep${ep.no} · ${ep.title || ep.slug} · ${(ep.chars || 0).toLocaleString()} 字`;
      return `<button class="spine__b" role="listitem" data-open="${esc(ep.slug)}" data-tip="${esc(label)}"
        style="--h:${h}%;--sc:${esc(colorOf(ep))}" aria-label="${esc(label)}"></button>`;
    }).join("");

    const tip = document.createElement("div");
    tip.className = "tip";
    document.body.appendChild(tip);
    const showTip = (b) => {
      tip.textContent = b.dataset.tip;
      tip.classList.add("is-on");
      const r = b.getBoundingClientRect();
      tip.style.left = `${Math.min(Math.max(r.left + r.width / 2, 90), innerWidth - 90)}px`;
      tip.style.top = `${r.top + scrollY - 10}px`;
    };
    const hideTip = () => tip.classList.remove("is-on");

    $$(".spine__b", host).forEach((b) => {
      b.addEventListener("mouseenter", () => showTip(b));
      b.addEventListener("focus", () => showTip(b));
      b.addEventListener("mouseleave", hideTip);
      b.addEventListener("blur", hideTip);
      b.addEventListener("click", () => { hideTip(); openEp(b.dataset.open); });
    });
  }

  /* ── 阅读进度 / 顶栏 ─────────────────────────── */

  function bindScroll() {
    const bar = $("#progress");
    const top = $("#topbar");
    const upd = () => {
      const max = document.documentElement.scrollHeight - innerHeight;
      bar.style.width = `${max > 0 ? Math.min(100, (scrollY / max) * 100) : 0}%`;
      top.classList.toggle("is-stuck", scrollY > 8);
    };
    addEventListener("scroll", upd, { passive: true });
    addEventListener("resize", upd);
    upd();
  }

  /* ── 搜索 ───────────────────────────────────── */

  const qEl = $("#q");
  let qt = null;
  qEl.addEventListener("input", () => {
    clearTimeout(qt);
    qt = setTimeout(() => {
      state.q = qEl.value.trim();
      state.expanded = false;
      renderJudgments();
      if (state.q) $("#judgments").scrollIntoView({ behavior: "smooth", block: "start" });
    }, 120);
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Tab") {
      const drawer = $(".drawer.is-open");
      if(drawer){const focusable=$$("button,a[href],input,textarea,select",drawer).filter(el=>!el.disabled && el.offsetParent!==null);const first=focusable[0],last=focusable.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus();}}
    }
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
    if (e.key === "/" && !typing) { e.preventDefault(); qEl.focus(); qEl.select(); }
    if (e.key === "Escape") {
      const open = $$(".drawer.is-open").length > 0;
      if (open) hideDrawers();
      else if (typing) document.activeElement.blur();
    }
  });

  /* ── 主题 ───────────────────────────────────── */

  const savedTheme = load(THEME_KEY, null) || (document.documentElement.dataset.sourcecast === "neon" || matchMedia("(prefers-color-scheme: dark)").matches ? "night" : "day");
  document.documentElement.setAttribute("data-theme", savedTheme);
  $("#toggleTheme").addEventListener("click", () => {
    const next = document.documentElement.getAttribute("data-theme") === "night" ? "day" : "night";
    document.documentElement.setAttribute("data-theme", next);
    save(THEME_KEY, next);
    if (state.graph) state.graph.theme();
  });

  /* ── 创作台：风格 ───────────────────────────── */

  const STOP = new Set(("我们 你们 他们 自己 这个 那个 这些 那些 这样 那样 这种 那种 什么 怎么 就是 不是 可以 不能 没有 已经 还是 或者 因为 所以 但是 如果 虽然 然后 而且 以及 对于 关于 通过 由于 除了 只是 还有 一样 一些 有点 之后 之前 之间 里面 出来 起来 下来 过去 回来 时候 问题 东西 事情 需要 应该 能够 可能 一定 非常 真的 其实 现在 目前 一个 一次 一直 不会 这一 那一 上面 下面 前面 后面 第一 第二 第三 每个 任何 所有 同时 进行 使用 采用 包括 例如 比如 也就是 的话 来看 看看 说的 写到 看上 上面 下来 一起").split(/\s+/));

  /** 把一段文字量成六个数字。同一个函数服务「风格样例」和「用户上传的逐字稿」。 */
  function analyzeText(text) {
    const t = String(text || "").replace(/\r/g, "");
    const chars = (t.match(/[\u4e00-\u9fff]/g) || []).length || 1;
    const sentences = t.split(/[。！？!?…\n]+/).map((s) => s.trim()).filter((s) => s.length > 1);
    const n = sentences.length || 1;

    const lens = sentences.map((s) => (s.match(/[\u4e00-\u9fff]/g) || []).length);
    const avgLen = lens.reduce((a, b) => a + b, 0) / n;
    const shortRatio = lens.filter((l) => l <= 12).length / n;
    const qRatio = (t.match(/[？?]/g) || []).length / n;
    const iPer = ((t.match(/我/g) || []).length / chars) * 1000;
    const youPer = ((t.match(/你/g) || []).length / chars) * 1000;
    const numPer = ((t.match(/\d+/g) || []).length / chars) * 1000;
    const metaPer = ((t.match(/就像|好比|相当于|像是|打个比方|好比说/g) || []).length / chars) * 1000;
    const turnPer = ((t.match(/但是|不过|其实|反过来|问题是|可是/g) || []).length / chars) * 1000;

    // 口头禅：2–4 字片段按出现次数排
    const freq = new Map();
    const clean = t.replace(/[^\u4e00-\u9fff]+/g, " ");
    for (let len = 2; len <= 4; len++) {
      for (let i = 0; i + len <= clean.length; i++) {
        const g = clean.slice(i, i + len);
        if (g.includes(" ")) continue;
        if (STOP.has(g)) continue;
        if (/^[要是的有和与或就也都还很再又只才更最把被给对从向到为以于关不没这那其]/.test(g)) continue;
        if (/[的了吗呢吧啊呀嘛着过]$/.test(g)) continue;
        freq.set(g, (freq.get(g) || 0) + 1);
      }
    }
    const words = [...freq.entries()]
      .filter(([, c]) => c >= 2)
      .sort((a, b) => b[1] - a[1] || b[0].length - a[0].length)
      .filter(([w], i, arr) => !arr.some(([o]) => o !== w && o.includes(w) && o.length > w.length))
      .slice(0, 8)
      .map(([w, c]) => ({ w, c }));

    const firstLine = (t.split(/\n/).find((l) => l.trim()) || "").trim().slice(0, 16);
    const lines = t.split(/\n/).map((l) => l.trim()).filter(Boolean);
    const lastLine = (lines[lines.length - 1] || "").slice(-16);

    const norm = (v, lo, hi) => Math.max(0, Math.min(1, (v - lo) / (hi - lo)));

    return {
      chars, sentences: n,
      avgLen, shortRatio, qRatio, iPer, youPer, numPer, metaPer, turnPer,
      words, firstLine, lastLine,
      bars: [
        { label: "句长", v: norm(avgLen, 5, 45), text: `${avgLen.toFixed(1)} 字` },
        { label: "短句", v: shortRatio, text: `${Math.round(shortRatio * 100)}%` },
        { label: "问句", v: norm(qRatio, 0, 0.5), text: `${Math.round(qRatio * 100)}%` },
        { label: "第一人称", v: norm(iPer, 0, 40), text: `${iPer.toFixed(1)}‰` },
        { label: "类比", v: norm(metaPer, 0, 10), text: `${metaPer.toFixed(1)}‰` },
        { label: "转折", v: norm(turnPer, 0, 12), text: `${turnPer.toFixed(1)}‰` },
      ],
    };
  }

  function renderStyles() {
    $("#styleGrid").innerHTML = STYLES.map((s) => `
      <button class="stylecard ${s.id === state.style.id ? "is-on" : ""}" role="radio"
        aria-checked="${s.id === state.style.id}" tabindex="${s.id === state.style.id ? 0 : -1}" data-style="${esc(s.id)}">
        <b>${esc(s.name)}<i>${esc(s.en)}</i></b>
        <span>${esc(s.one)}</span>
      </button>`).join("");
    $$("[data-style]").forEach((b) => b.addEventListener("click", () => {
      state.style = STYLES.find((s) => s.id === b.dataset.style);
      renderStyles();
      renderStyleDetail();
      window.dispatchEvent(new CustomEvent("sourcecast:style", {detail:state.style.id}));
      $(`[data-style="${state.style.id}"]`).focus({preventScroll:true});
    }));
    $$("[data-style]").forEach((b) => b.addEventListener("keydown", e => {
      const key = e.key;
      if (!["ArrowUp","ArrowDown","ArrowLeft","ArrowRight","Home","End"].includes(key)) return;
      e.preventDefault();
      const i = STYLES.findIndex(s => s.id === state.style.id);
      const next = key === "Home" ? 0 : key === "End" ? STYLES.length - 1 : (i + (["ArrowUp","ArrowLeft"].includes(key) ? -1 : 1) + STYLES.length) % STYLES.length;
      $(`[data-style="${STYLES[next].id}"]`).click();
      $(`[data-style="${STYLES[next].id}"]`).scrollIntoView({block:"nearest",inline:"nearest",behavior:"instant"});
    }));
    renderStyleDetail();
  }

  function renderStyleDetail() {
    const s = state.style;
    const a = analyzeText(s.sample);
    $("#styleName").textContent = s.name;
    $("#styleOne").textContent = s.one;
    $("#styleTag").textContent = s.tag;
    $("#styleWhen").textContent = s.when;

    const isDuo = s.id === "duo";
    $("#styleSample").innerHTML = isDuo
      ? s.sample.split("\n").map((line) => {
          const m = line.match(/^([AB])：(.+)$/);
          return m ? `<span class="turn"><span class="who">${m[1]}</span>${esc(m[2])}</span>` : `<span class="turn">${esc(line)}</span>`;
        }).join("")
      : esc(s.sample);

    $("#styleSkel").innerHTML = s.skeleton.map((x) => `<li>${esc(x)}</li>`).join("");
    $("#styleMetrics").innerHTML = a.bars.map((b) => `
      <div class="metric"><span>${b.label}</span><b><i style="--p:${Math.round(b.v * 100)}%"></i></b><em>${b.text}</em></div>`).join("");
    $("#stylePrompt").textContent = s.prompt;
  }

  /* ── 创作台：复刻 ───────────────────────────── */

  function openClone() {
    lastFocus = document.activeElement;
    $("#cloneBody").innerHTML = `
      <div class="clonebox">
        <p class="drawer__sub">把他的逐字稿贴进来，至少三段（合计 300 字以上，建议 800 字）。越像本人越好：不要摘要，要原话。</p>
        <textarea id="cloneInput" placeholder="第一段…&#10;&#10;第二段…&#10;&#10;第三段…"></textarea>
        <div class="clonebar">
          <span class="clonecount" id="cloneCount">0 字</span>
          <button class="btn btn--ink" id="cloneRun">提取风格指纹</button>
        </div>
        <div id="cloneResult" style="margin-top:26px"></div>
      </div>`;
    showDrawer("#clonedrawer");

    const ta = $("#cloneInput");
    ta.addEventListener("input", () => {
      $("#cloneCount").textContent = `${(ta.value.match(/[\u4e00-\u9fff]/g) || []).length} 字`;
    });
    $("#cloneRun").addEventListener("click", () => {
      const text = ta.value.trim();
      if ((text.match(/[\u4e00-\u9fff]/g) || []).length < 300) {
        toast("再贴一点，至少 300 字才量得准");
        return;
      }
      const fp = analyzeText(text);
      $("#cloneResult").innerHTML = fingerprintHTML(fp, "他的指纹");
      renderClonePreview(fp);
      save("sourcecast.customStyle.v1", clonePrompt(fp));
      window.dispatchEvent(new CustomEvent("sourcecast:fingerprint", {detail:clonePrompt(fp)}));
      toast("量完了 · 原文没有离开这台机器");
    });
    setTimeout(() => ta.focus(), 80);
  }

  function fingerprintHTML(fp, title) {
    return `
      <div class="fp">
        <h4 class="h4">${esc(title)}</h4>
        ${fp.bars.map((b) => `<div class="fp__row"><span>${b.label}</span><b><i style="--p:${Math.round(b.v * 100)}%"></i></b><em>${b.text}</em></div>`).join("")}
        ${fp.words.length ? `<div class="fp__words">${fp.words.map((w) => `<span>${esc(w.w)} ×${w.c}</span>`).join("")}</div>` : ""}
        <p class="micro micro--dim" style="margin-top:10px">开场：${esc(fp.firstLine || "—")} ｜ 收尾：${esc(fp.lastLine || "—")}</p>
        <div class="promptbox" style="margin-top:16px">
          <div class="promptbox__bar"><span>按这份指纹写稿</span><button class="linkbtn" data-copy="clonePrompt">复制提示词</button></div>
          <pre class="clone-prompt">${esc(clonePrompt(fp))}</pre>
        </div>
      </div>`;
  }

  function clonePrompt(fp) {
    const w = fp.words.slice(0, 5).map((x) => x.w).join("、") || "（没有明显口头禅）";
    return [
      "你要模仿一位中文作者的行文习惯，写一段口播稿。",
      `他的句子平均 ${fp.avgLen.toFixed(1)} 个字，短句（12 字以内）占 ${Math.round(fp.shortRatio * 100)}%，问句占 ${Math.round(fp.qRatio * 100)}%。`,
      `每千字里出现「我」${fp.iPer.toFixed(1)} 次、「你」${fp.youPer.toFixed(1)} 次、数字 ${fp.numPer.toFixed(1)} 处、类比 ${fp.metaPer.toFixed(1)} 处。`,
      `他常用的口头片段：${w}。请自然地用上，不要堆砌。`,
      `开场习惯：「${fp.firstLine}」这类起手；收尾习惯：「${fp.lastLine}」这类落点。`,
      "不要模仿他的观点，只模仿句子的呼吸。写完后自查：随便挑三句，像不像他说话。",
    ].join("\n");
  }

  function renderClonePreview(fp) {
    const host = $("#clonePreview");
    host.innerHTML = fingerprintHTML(fp, "刚刚量出来的");
    const cp = $("#cloneCopy", host);
    if (cp) cp.addEventListener("click", () => copyText(clonePrompt(fp), "提示词已复制，拿去喂你的模型"));
  }

  $("#openClone").addEventListener("click", openClone);

  /* ── 创作台：音色 ───────────────────────────── */

  function renderVoices() {
    $("#voicePick").innerHTML = VOICES.map((v) => `<option value="${esc(v.id)}">${esc(v.name)} · ${esc(v.fit)}</option>`).join("");
  }

  async function decodeAudioFile(file) {
    if (file.size > 8 * 1024 * 1024) throw new Error("请选择 8 MB 以内的音频");
    const buf = await file.arrayBuffer();
    let dataUrl = null;
    if (file.size <= 8 * 1024 * 1024) {
      const b64 = await new Promise((res) => {
        const fr = new FileReader();
        fr.onload = () => res(String(fr.result).split(",")[1] || "");
        fr.readAsDataURL(file);
      });
      dataUrl = b64 ? `data:${file.type || "audio/wav"};base64,${b64}` : null;
    }
    const AC = window.AudioContext || window.webkitAudioContext;
    const ac = new AC();
    const audio = await ac.decodeAudioData(buf);
    if (audio.duration > 60) { await ac.close(); throw new Error("请选择 60 秒以内的音频，建议 10–30 秒"); }
    const ch = audio.getChannelData(0);
    let peak = 0, sum = 0, silent = 0;
    const step = Math.max(1, Math.floor(ch.length / 200000));
    let count = 0;
    for (let i = 0; i < ch.length; i += step) {
      const v = Math.abs(ch[i]);
      if (v > peak) peak = v;
      sum += v * v;
      if (v < 0.01) silent++;
      count++;
    }
    const rms = Math.sqrt(sum / count);
    const silence = silent / count;

    // 基频：降采样后自相关
    const target = 16000;
    const ratio = Math.max(1, Math.floor(audio.sampleRate / target));
    const ds = [];
    for (let i = 0; i < ch.length; i += ratio) ds.push(ch[i]);
    const win = 1024, hop = 2048, pitches = [];
    for (let i = 0; i + win < ds.length && pitches.length < 60; i += hop) {
      const seg = ds.slice(i, i + win);
      let energy = 0;
      for (const v of seg) energy += v * v;
      if (Math.sqrt(energy / win) < 0.02) continue;
      const sr = audio.sampleRate / ratio;
      const lo = Math.floor(sr / 400), hi = Math.floor(sr / 70);
      let best = -1, bestLag = 0;
      for (let lag = lo; lag <= hi; lag++) {
        let s = 0;
        for (let j = 0; j < win - lag; j += 2) s += seg[j] * seg[j + lag];
        if (s > best) { best = s; bestLag = lag; }
      }
      if (bestLag) pitches.push(sr / bestLag);
    }
    pitches.sort((a, b) => a - b);
    const f0 = pitches.length ? pitches[Math.floor(pitches.length / 2)] : 0;

    ac.close();

    const seconds = audio.duration;
    let score = 0;
    const tips = [];
    if (seconds >= 10 && seconds <= 30) score += 34;
    else if (seconds >= 6) { score += 20; tips.push("时长最好在 10–30 秒"); }
    else { score += 6; tips.push("太短了，10 秒以上才够建模"); }

    if (silence < 0.2) score += 24;
    else if (silence < 0.4) { score += 12; tips.push("静音偏多，剪掉头尾的空拍"); }
    else tips.push("一半以上是静音，换一段"); 

    if (peak < 0.99) score += 18;
    else tips.push("有削波，降一点录音音量");

    if (rms > 0.02) score += 12;
    else tips.push("整体偏轻，离麦克风近一点");

    if (pitches.length > 10) score += 12;
    else tips.push("有效语音太少，听不清音高");

    // Convert every accepted browser format to mono PCM WAV for the clone service.
    const wavSamples = audio.getChannelData(0);
    const targetRate = Math.min(24000, audio.sampleRate);
    const wavLength = Math.floor(wavSamples.length * targetRate / audio.sampleRate);
    const wav = new ArrayBuffer(44 + wavLength * 2), view = new DataView(wav);
    const str = (off,t) => [...t].forEach((c,i)=>view.setUint8(off+i,c.charCodeAt(0)));
    str(0,"RIFF");view.setUint32(4,36+wavLength*2,true);str(8,"WAVE");str(12,"fmt ");view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);view.setUint32(24,targetRate,true);view.setUint32(28,targetRate*2,true);view.setUint16(32,2,true);view.setUint16(34,16,true);str(36,"data");view.setUint32(40,wavLength*2,true);
    for(let i=0;i<wavLength;i++){ const v=Math.max(-1,Math.min(1,wavSamples[Math.floor(i*audio.sampleRate/targetRate)]));view.setInt16(44+i*2,v<0?v*32768:v*32767,true); }
    dataUrl = await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=reject;reader.readAsDataURL(new Blob([wav],{type:"audio/wav"}));});
    return {
      name: file.name.replace(/\.[^.]+$/, ""),
      dataUrl,
      seconds, peak, rms, silence, f0,
      score: Math.min(100, score),
      tips,
      wave: Array.from({ length: 56 }, (_, i) => {
        const a = Math.floor((i / 56) * ch.length);
        const b = Math.floor(((i + 1) / 56) * ch.length);
        let m = 0;
        for (let j = a; j < b; j += 17) m = Math.max(m, Math.abs(ch[j] || 0));
        return m;
      }),
    };
  }

  function renderVoiceCard(v) {
    const host = $("#voiceCard");
    host.hidden = false;
    host.innerHTML = `
      <h5>${esc(v.name)}<span class="score">${v.seconds.toFixed(1)} 秒</span></h5>
      <div class="wavelet">${v.wave.map((x) => `<i style="height:${Math.max(2, Math.round(x * 32))}px"></i>`).join("")}</div>
      <div class="fp">
        <div class="fp__row"><span>时长</span><b><i style="--p:${Math.min(100, (v.seconds / 30) * 100)}%"></i></b><em>${v.seconds.toFixed(1)}s</em></div>
        <div class="fp__row"><span>基频</span><b><i style="--p:${Math.min(100, (v.f0 / 300) * 100)}%"></i></b><em>${v.f0 ? Math.round(v.f0) + "Hz" : "—"}</em></div>
        <div class="fp__row"><span>静音</span><b><i style="--p:${Math.round(v.silence * 100)}%"></i></b><em>${Math.round(v.silence * 100)}%</em></div>
        <div class="fp__row"><span>峰值</span><b><i style="--p:${Math.round(v.peak * 100)}%"></i></b><em>${v.peak.toFixed(2)}</em></div>
      </div>
      ${v.tips.length ? `<p class="micro" style="margin-top:12px">${v.tips.map((t) => "· " + esc(t)).join("<br>")}</p>` : `<p class="micro" style="margin-top:12px">未检出明显削波或低音量。请试听确认是清楚的单人语音，没有背景音乐。</p>`}
      <p class="micro micro--dim" style="margin-top:8px">音频分析在浏览器内完成。点击「用我的 API 生成」后，参考音会发送到你填写的语音服务。</p>`;
  }

  $("#voiceFile").addEventListener("change", async (e) => {
    const f = e.target.files && e.target.files[0];
    if (!f) return;
    try {
      const v = await decodeAudioFile(f);
      state.voice = v;
      window.dispatchEvent(new CustomEvent("sourcecast:voice",{detail:v}));
      renderVoiceCard(v);
      updateGenBtn();
      toast("量完了 · 这段音频没有离开浏览器");
    } catch (err) {
      console.error(err);
      toast(err.message || "这个格式解不开，试试 wav / mp3 / m4a");
    }
  });

  const drop = $("#voiceDrop");
  drop.addEventListener("click", (e) => { if (e.target !== $("#voiceFile")) { e.preventDefault(); $("#voiceFile").click(); } });
  drop.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("#voiceFile").click(); } });
  ["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("is-over"); }));
  ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("is-over"); }));
  drop.addEventListener("drop", async (e) => {
    const f = e.dataTransfer.files && e.dataTransfer.files[0];
    if (!f) return;
    try {
      const v = await decodeAudioFile(f);
      state.voice = v;
      window.dispatchEvent(new CustomEvent("sourcecast:voice",{detail:v}));
      renderVoiceCard(v);
      updateGenBtn();
    } catch { toast("这个格式解不开"); }
  });

  /* Voice mode UI. All synthesis is owned by the visitor's explicit API key. */
  function updateGenBtn() {
    const cloning = $("#voiceMode").value === "clone";
    $("#voiceDrop").hidden = !cloning;
    $("#voiceCard").hidden = !cloning || !state.voice;
    $("#ttsHint").textContent = "仅使用你在设置中填写的语音 API Key。本站不提供作者的调用额度。";
  }
  $("#ttsText").addEventListener("input", updateGenBtn);
  $("#voiceMode").addEventListener("change", updateGenBtn);

  /* ── 记忆网络 ───────────────────────────────── */

  function buildGraph() {
    const nodes = [];
    const edges = [];
    const bySlug = new Map();

    (LIB.series_meta || []).forEach((m, i) => {
      nodes.push({ id: `s:${m.name}`, kind: "series", label: m.name, color: m.color, r: 8, ring: i });
    });

    EPS.forEach((ep) => {
      const n = { id: `e:${ep.slug}`, kind: "ep", label: epShort(ep), ep, color: colorOf(ep), r: 5.2 };
      bySlug.set(ep.slug, n);
      nodes.push(n);
      if (ep.series) edges.push({ a: `e:${ep.slug}`, b: `s:${ep.series}`, kind: "es" });
    });

    EPS.forEach((ep) => {
      ep.judgments.forEach((t, i) => {
        nodes.push({ id: `j:${ep.slug}#${i}`, kind: "judgment", label: t, ep, text: t, color: colorOf(ep), r: 2.1 });
        edges.push({ a: `j:${ep.slug}#${i}`, b: `e:${ep.slug}`, kind: "je" });
      });
    });

    const repoSeen = new Set();
    EPS.forEach((ep) => ep.repos.forEach((r) => {
      if (!repoSeen.has(r)) {
        repoSeen.add(r);
        nodes.push({ id: `r:${r}`, kind: "repo", label: r, color: "#8f8d84", r: 1.7 });
      }
      edges.push({ a: `r:${r}`, b: `e:${ep.slug}`, kind: "re" });
    }));

    (LIB.episodes || []).forEach((ep) => {
      (ep.related || []).forEach((s) => {
        if (bySlug.has(s) && ep.slug < s) edges.push({ a: `e:${ep.slug}`, b: `e:${s}`, kind: "ee" });
      });
    });

    return { nodes, edges };
  }

  function Graph(canvas, data) {
    const ctx = canvas.getContext("2d");
    const parent = canvas.parentElement;
    let W = 0, H = 0, dpr = Math.min(2, devicePixelRatio || 1);
    let nodes = data.nodes, edges = data.edges;
    let alpha = 1;
    let hover = null, drag = null;
    const view = { x: 0, y: 0, k: 1 };
    let running = true;

    const index = new Map(nodes.map((n) => [n.id, n]));
    const adj = new Map();
    edges.forEach((e) => {
      if (!adj.has(e.a)) adj.set(e.a, []);
      if (!adj.has(e.b)) adj.set(e.b, []);
      adj.get(e.a).push(e);
      adj.get(e.b).push(e);
    });

    function resize() {
      const r = parent.getBoundingClientRect();
      if (!r.width || !r.height) return;
      const previousW=W, previousH=H;
      W = r.width; H = r.height;
      if (previousW && previousH) { nodes.forEach(n=>{n.x*=W/previousW;n.y*=H/previousH;}); }
      else { nodes.forEach(n=>{n.x=null;n.y=null;}); }
      seed(); alpha=Math.max(alpha,0.6);
      canvas.width = W * dpr;
      canvas.height = H * dpr;
      canvas.style.width = W + "px";
      canvas.style.height = H + "px";
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function seed() {
      const series = nodes.filter((n) => n.kind === "series");
      const R = Math.min(W * 0.42, H * 0.38);
      series.forEach((n, i) => {
        const a = (i / series.length) * Math.PI * 2 - Math.PI / 2;
        n.hx = W / 2 + Math.cos(a) * R;
        n.hy = H / 2 + Math.sin(a) * R;
        n.x = n.hx;
        n.y = n.hy;
        n.vx = n.vy = 0;
        n.angle = a;
      });
      nodes.forEach((n) => {
        if (n.x != null) return;
        n.x = W / 2 + (Math.random() - 0.5) * W * 0.7;
        n.y = H / 2 + (Math.random() - 0.5) * H * 0.7;
        n.vx = n.vy = 0;
      });
    }

    function step() {
      if (alpha <= 0.006) return;
      const A = alpha;
      for (let i = 0; i < nodes.length; i++) {
        const a = nodes[i];
        for (let j = i + 1; j < nodes.length; j++) {
          const b = nodes[j];
          let dx = b.x - a.x, dy = b.y - a.y;
          let d2 = dx * dx + dy * dy;
          if (d2 < 1) d2 = 1;
          if (d2 > 90000) continue;
          const f = (185 * A) / d2;
          const d = Math.sqrt(d2);
          dx /= d; dy /= d;
          a.vx -= dx * f; a.vy -= dy * f;
          b.vx += dx * f; b.vy += dy * f;
        }
      }
      edges.forEach((e) => {
        const a = index.get(e.a), b = index.get(e.b);
        if (!a || !b) return;
        const len = e.kind === "es" ? 62 : e.kind === "ee" ? 132 : 30;
        const dx = b.x - a.x, dy = b.y - a.y;
        const d = Math.hypot(dx, dy) || 1;
        const f = ((d - len) / d) * (e.kind === "es" ? 0.075 : 0.1) * A;
        a.vx += dx * f; a.vy += dy * f;
        b.vx -= dx * f; b.vy -= dy * f;
      });
      const cx = W / 2, cy = H / 2;
      nodes.forEach((n) => {
        if (n.kind === "series") {
          n.x += (n.hx - n.x) * 0.18;
          n.y += (n.hy - n.y) * 0.18;
          n.vx = n.vy = 0;
          return;
        }
        n.vx += (cx - n.x) * 0.0011 * A;
        n.vy += (cy - n.y) * 0.0011 * A;
        if (n === drag) { n.vx = n.vy = 0; return; }
        n.vx *= 0.86; n.vy *= 0.86;
        n.x += n.vx; n.y += n.vy;
        n.x = Math.max(14, Math.min(W - 14, n.x));
        n.y = Math.max(14, Math.min(H - 14, n.y));
      });
      alpha *= 0.985;
    }

    const isDark = () => document.documentElement.getAttribute("data-theme") === "night";

    function draw() {
      ctx.clearRect(0, 0, W, H);
      ctx.save();
      ctx.translate(view.x, view.y);
      ctx.scale(view.k, view.k);

      const active = hover ? new Set([hover.id, ...(adj.get(hover.id) || []).map((e) => (e.a === hover.id ? e.b : e.a))]) : null;

      edges.forEach((e) => {
        const a = index.get(e.a), b = index.get(e.b);
        if (!a || !b || a.hidden || b.hidden) return;
        const hot = active && (e.a === hover.id || e.b === hover.id);
        ctx.beginPath();
        const mx = (a.x + b.x) / 2 + (b.y - a.y) * 0.06;
        const my = (a.y + b.y) / 2 - (b.x - a.x) * 0.06;
        ctx.moveTo(a.x, a.y);
        ctx.quadraticCurveTo(mx, my, b.x, b.y);
        if (hot) {
          ctx.strokeStyle = "rgba(131,192,164,.55)";
          ctx.lineWidth = 0.9;
        } else {
          ctx.strokeStyle = `rgba(236,234,225,${active ? 0.035 : e.kind === "es" ? 0.13 : e.kind === "ee" ? 0.09 : 0.05})`;
          ctx.lineWidth = e.kind === "es" ? 0.7 : 0.5;
        }
        ctx.stroke();
      });

      nodes.forEach((n) => {
        if (n.hidden) return;
        const dim = active && !active.has(n.id);
        const r = n.r * (n.kind === "series" ? 1 : view.k > 1.2 ? 1.05 : 1);
        if (n.kind === "series") {
          const g = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, r * 3.4);
          g.addColorStop(0, hexA(n.color, dim ? 0.18 : 0.5));
          g.addColorStop(1, hexA(n.color, 0));
          ctx.fillStyle = g;
          ctx.beginPath();
          ctx.arc(n.x, n.y, r * 3.4, 0, Math.PI * 2);
          ctx.fill();
        }
        ctx.beginPath();
        ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
        ctx.fillStyle = hexA(n.kind === "series" ? n.color : n.color, dim ? 0.16 : n.kind === "judgment" ? 0.55 : 0.9);
        ctx.fill();

        if (n.kind === "series") {
          const out = 1.2;
          const lx = W / 2 + (n.x - W / 2) * out;
          const ly = H / 2 + (n.y - H / 2) * out;
          ctx.fillStyle = dim ? "rgba(236,234,225,.22)" : "rgba(236,234,225,.6)";
          ctx.font = "10px ui-monospace, Menlo, monospace";
          ctx.textAlign = n.x >= W / 2 ? "left" : "right";
          ctx.fillText(n.label, n.x + (n.x >= W / 2 ? 13 : -13), n.y + 3);
        } else if (hover && hover.id === n.id) {
          ctx.fillStyle = "rgba(236,234,225,.8)";
          ctx.font = "10px ui-monospace, Menlo, monospace";
          ctx.textAlign = "center";
          ctx.fillText(n.label.slice(0, 20), n.x, n.y - r - 8);
        }
      });

      ctx.restore();
    }

    function hexA(hex, a) {
      if (!hex || hex[0] !== "#") return `rgba(154,151,142,${a})`;
      const h = hex.replace("#", "");
      const v = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
      const r = parseInt(v.slice(0, 2), 16), g = parseInt(v.slice(2, 4), 16), b = parseInt(v.slice(4, 6), 16);
      return `rgba(${r},${g},${b},${a})`;
    }

    function loop() {
      if (!running) return;
      if (parent.offsetWidth && document.visibilityState === "visible" && alpha > 0.006) { step(); draw(); }
      requestAnimationFrame(loop);
    }

    function hit(x, y) {
      const wx = (x - view.x) / view.k, wy = (y - view.y) / view.k;
      let best = null, bestD = 14;
      nodes.forEach((n) => {
        if (n.hidden) return;
        const d = Math.hypot(n.x - wx, n.y - wy);
        if (d < Math.max(10, n.r + 5) && d < bestD) { best = n; bestD = d; }
      });
      return best;
    }

    canvas.addEventListener("pointermove", (e) => {
      const r = canvas.getBoundingClientRect();
      const x = e.clientX - r.left, y = e.clientY - r.top;
      if (drag) {
        drag.x = (x - view.x) / view.k;
        drag.y = (y - view.y) / view.k;
        alpha = Math.max(alpha, 0.12);
        return;
      }
      const h = hit(x, y);
      if (h !== hover) {
        hover = h;
        canvas.style.cursor = h ? "pointer" : "grab";
        draw();
      }
    });

    canvas.addEventListener("pointerdown", (e) => {
      const r = canvas.getBoundingClientRect();
      const h = hit(e.clientX - r.left, e.clientY - r.top);
      if (!h) return;
      drag = h;
      canvas.classList.add("is-drag");
      canvas.setPointerCapture(e.pointerId);
      alpha = Math.max(alpha, 0.18);
    });

    canvas.addEventListener("pointerup", (e) => {
      const r = canvas.getBoundingClientRect();
      const x = e.clientX - r.left, y = e.clientY - r.top;
      const moved = drag && (Math.abs(drag.x * view.k + view.x - x) > 3 || Math.abs(drag.y * view.k + view.y - y) > 3);
      if (drag && !moved) {
        const n = drag;
        if (n.kind === "ep" || (n.kind === "judgment" && n.ep)) openEp((n.ep || n).slug);
        else if (n.kind === "series") focusSeries(n.label);
      }
      drag = null;
      canvas.classList.remove("is-drag");
    });

    canvas.addEventListener("wheel", (e) => {
      e.preventDefault();
      const r = canvas.getBoundingClientRect();
      const mx = e.clientX - r.left, my = e.clientY - r.top;
      const k2 = Math.max(0.45, Math.min(2.6, view.k * (e.deltaY > 0 ? 0.92 : 1.08)));
      view.x = mx - ((mx - view.x) / view.k) * k2;
      view.y = my - ((my - view.y) / view.k) * k2;
      view.k = k2;
      draw();
    }, { passive: false });

    canvas.addEventListener("pointerleave", () => { hover = null; draw(); });

    function focusSeries(name) {
      const s = nodes.find((n) => n.kind === "series" && n.label === name);
      if (!s) return;
      view.k = 1.5;
      view.x = W / 2 - s.x * view.k;
      view.y = H / 2 - s.y * view.k;
      draw();
    }

    function reset() {
      view.x = 0; view.y = 0; view.k = 1;
      alpha = 0.9;
      seed();
      draw();
    }

    function addMemory(terms, hits) {
      const color = "#e0a06a";
      terms.forEach((t, i) => {
        const id = `m:${t.term}`;
        if (index.has(id)) return;
        const n = {
          id, kind: "memory", label: t.term, color, r: 4.2,
          x: W / 2 + Math.cos(i * 1.7) * 60 + (Math.random() - 0.5) * 40,
          y: H / 2 + Math.sin(i * 1.7) * 60 + (Math.random() - 0.5) * 40,
          vx: 0, vy: 0,
        };
        nodes.push(n);
        index.set(id, n);
        adj.set(id, []);
      });
      hits.forEach(({ term, slug }) => {
        const a = `m:${term}`, b = `e:${slug}`;
        if (!index.has(a) || !index.has(b)) return;
        const e = { a, b, kind: "me" };
        edges.push(e);
        adj.get(a).push(e);
        adj.get(b) && adj.get(b).push(e);
      });
      alpha = 0.9;
      draw();
      return nodes.filter((n) => n.kind === "memory").length;
    }

    resize();
    seed();
    loop();
    addEventListener("resize", () => { resize(); draw(); });
    new ResizeObserver(()=>{if(parent.offsetWidth){resize();draw();}}).observe(parent);

    return {
      reset, addMemory,
      theme: draw,
      setLayer(kind, on) {
        nodes.forEach((n) => { if (n.kind === kind) n.hidden = !on; });
        draw();
      },
      counts: () => ({
        ep: nodes.filter((n) => n.kind === "ep").length,
        judgment: nodes.filter((n) => n.kind === "judgment").length,
        repo: nodes.filter((n) => n.kind === "repo").length,
        series: nodes.filter((n) => n.kind === "series").length,
        memory: nodes.filter((n) => n.kind === "memory").length,
      }),
    };
  }

  function mountGraph() {
    const data = buildGraph();
    const g = Graph($("#graph"), data);
    state.graph = g;
    if (state.mem && state.mem.terms) { g.addMemory(state.mem.terms, state.mem.hits || []); $("#memStats").textContent = `已恢复本机 ${state.mem.terms.length} 个记忆主题。`; }
    const c = g.counts();
    $("#graphStat").textContent = `${Object.values(c).reduce((a,b)=>a+b,0)} 节点`;

    const legend = [
      ["series", "主题线", "#1c5b46"],
      ["ep", "期次", "#a4472b"],
      ["judgment", "判断", "#8a6a24"],
      ["repo", "仓库", "#8f8d84"],
    ];
    $("#legend").innerHTML = legend.map(([k, label, color]) => `
      <span data-layer="${k}" style="cursor:pointer"><i style="background:${color}"></i>${label}</span>`).join("")
      + `<span><i style="background:#e0a06a"></i>你的记忆</span>`;

    let repoOn = false;
    g.setLayer("repo", false);
    const repoLegend = $('#legend [data-layer="repo"]');
    if (repoLegend) repoLegend.style.opacity = ".45";
    $$("#legend [data-layer]").forEach((el) => el.addEventListener("click", () => {
      const k = el.dataset.layer;
      if (k === "repo") {
        repoOn = !repoOn;
        g.setLayer("repo", repoOn);
        el.style.opacity = repoOn ? "1" : ".45";
      } else {
        const on = el.style.opacity !== ".45";
        el.style.opacity = on ? ".45" : "1";
        g.setLayer(k, !on);
      }
    }));

    $("#graphReset").addEventListener("click", () => g.reset());
    $("#graphExport").addEventListener("click", exportMemory);
  }

  /* ── 记忆导入 ───────────────────────────────── */

  function extractTerms(items, limit) {
    const df = new Map(), recent = new Map();
    const now = Date.now();
    items.forEach((f) => {
      if (!f.text) return;
      const seen = new Set();
      const clean = f.text.replace(/[^\u4e00-\u9fff]+/g, " ");
      for (let len = 2; len <= 4; len++) {
        for (let i = 0; i + len <= clean.length; i++) {
          const g = clean.slice(i, i + len);
          if (g.includes(" ")) continue;
          if (STOP.has(g)) continue;
          if (/^[要是的有和与或就也都还很再又只才更最把被给对从向到为以于关不没这那其]/.test(g)) continue;
          if (/[的了吗呢吧啊呀嘛着过]$/.test(g)) continue;
          seen.add(g);
        }
      }
      const isRecent = f.mtime && now - f.mtime < 30 * 864e5;
      seen.forEach((g) => {
        df.set(g, (df.get(g) || 0) + 1);
        if (isRecent) recent.set(g, (recent.get(g) || 0) + 1);
      });
    });

    let rows = [...df.entries()]
      .filter(([, n]) => n >= Math.max(1, Math.floor(items.length * 0.04)))
      .map(([term, files]) => ({ term, files, recent: recent.get(term) || 0 }));

    rows.sort((a, b) => b.term.length - a.term.length || b.files - a.files);
    const kept = [];
    rows.forEach((r) => {
      if (kept.some((k) => k.term.includes(r.term) && k.files >= r.files * 0.85)) return;
      kept.push(r);
    });
    kept.sort((a, b) => b.files - a.files);
    return kept.slice(0, limit || 14);
  }

  function corpus() {
    const out = [];
    EPS.forEach((ep) => {
      out.push({
        slug: ep.slug,
        text: [ep.title, ep.subtitle, ep.question, ep.one_liner, (ep.judgments || []).join(""), (ep.repos || []).join(" ")].filter(Boolean).join(" "),
      });
    });
    return out;
  }

  function handleMemoryFiles(items) {
    const terms = extractTerms(items, 12);
    if (!terms.length) { toast("没读到能用的主题词，换个目录试试"); return; }

    const corpusItems = corpus();
    const hits = [];
    terms.forEach((t) => {
      corpusItems.forEach((c) => {
        if (c.text.includes(t.term)) hits.push({ term: t.term, slug: c.slug });
      });
    });

    const memCount = state.graph.addMemory(terms, hits);
    state.mem = { items: items.length, terms, hits };
    save("sourcecast.memory.terms.v1", state.mem);

    $("#memStats").innerHTML =
      `读了 <b>${items.length}</b> 份，抽出 <b>${terms.length}</b> 个主题，接上 <b>${new Set(hits.map((h) => h.slug)).size}</b> 期<br>` +
      `图上新增 <b>${memCount}</b> 个记忆节点 · 共 <b>${hits.length}</b> 条连接<br>` +
      `最高频：${terms.slice(0, 4).map((t) => esc(t.term) + "×" + t.files).join("、")}`;
    $("#graphStat").textContent = `${Object.values(state.graph.counts()).reduce((a,b)=>a+b,0)} 节点`;
    window.dispatchEvent(new Event("sourcecast:memory"));
    toast("记忆主题已连接到相关节目，关联按关键词计算。");
  }

  async function readFiles(fileList) {
    const out = [];
    for (const f of fileList) {
      if (!/\.(md|txt|json|markdown)$/i.test(f.name)) continue;
      out.push({ name: f.name, size: f.size, mtime: f.lastModified, text: await f.text() });
    }
    return out;
  }

  async function walkEntry(entry, out, depth) {
    if (out.length > 400 || depth > 6) return;
    if (entry.isFile) {
      if (/\.(md|txt|json|markdown)$/i.test(entry.name)) {
        const f = await new Promise((res, rej) => entry.file(res, rej));
        out.push({ name: entry.fullPath.replace(/^\//, ""), size: f.size, mtime: f.lastModified, text: await f.text() });
      }
      return;
    }
    const reader = entry.createReader();
    const entries = await new Promise((res) => reader.readEntries(res, () => res([])));
    for (const e of entries) await walkEntry(e, out, depth + 1);
  }

  async function readZip(file) {
    const buf = new Uint8Array(await file.arrayBuffer());
    const view = new DataView(buf.buffer);
    let eocd = -1;
    for (let i = buf.length - 22; i >= Math.max(0, buf.length - 65558); i--) {
      if (view.getUint32(i, true) === 0x06054b50) { eocd = i; break; }
    }
    if (eocd < 0) throw new Error("不是有效的 zip");
    const total = view.getUint16(eocd + 10, true);
    let ptr = view.getUint32(eocd + 16, true);
    const out = [];
    const dec = new TextDecoder("utf-8");
    for (let i = 0; i < total && out.length < 400; i++) {
      if (view.getUint32(ptr, true) !== 0x02014b50) break;
      const method = view.getUint16(ptr + 10, true);
      const compSize = view.getUint32(ptr + 20, true);
      const nameLen = view.getUint16(ptr + 28, true);
      const extraLen = view.getUint16(ptr + 30, true);
      const commentLen = view.getUint16(ptr + 32, true);
      const localOff = view.getUint32(ptr + 42, true);
      const name = dec.decode(buf.subarray(ptr + 46, ptr + 46 + nameLen));
      ptr += 46 + nameLen + extraLen + commentLen;
      if (!/\.(md|txt|json|markdown)$/i.test(name) || name.endsWith("/")) continue;
      const lNameLen = view.getUint16(localOff + 26, true);
      const lExtraLen = view.getUint16(localOff + 28, true);
      const dataStart = localOff + 30 + lNameLen + lExtraLen;
      const chunk = buf.subarray(dataStart, dataStart + compSize);
      let plain;
      if (method === 0) plain = chunk;
      else if (method === 8) {
        const stream = new Blob([chunk]).stream().pipeThrough(new DecompressionStream("deflate-raw"));
        plain = new Uint8Array(await new Response(stream).arrayBuffer());
      } else continue;
      out.push({ name, size: plain.length, mtime: file.lastModified, text: new TextDecoder("utf-8").decode(plain) });
    }
    return out;
  }

  const memDrop = $("#memDrop");
  memDrop.addEventListener("click", () => $("#memFiles").click());
  $("#memFiles").addEventListener("change", async (e) => {
    const items = await readFiles(e.target.files);
    if (items.length) handleMemoryFiles(items);
  });
  ["dragenter", "dragover"].forEach((ev) => memDrop.addEventListener(ev, (e) => { e.preventDefault(); memDrop.classList.add("is-over"); }));
  ["dragleave", "drop"].forEach((ev) => memDrop.addEventListener(ev, (e) => { e.preventDefault(); memDrop.classList.remove("is-over"); }));
  memDrop.addEventListener("drop", async (e) => {
    const dt = e.dataTransfer;
    const entries = [];
    for (const item of dt.items || []) {
      const entry = item.webkitGetAsEntry && item.webkitGetAsEntry();
      if (entry) entries.push(entry);
    }
    let items = [];
    if (entries.length) {
      for (const en of entries) await walkEntry(en, items, 0);
    } else if (dt.files.length) {
      const f = dt.files[0];
      if (/\.zip$/i.test(f.name)) {
        try { items = await readZip(f); } catch (err) { toast("解压失败：" + err.message); return; }
      } else items = await readFiles(dt.files);
    }
    if (!items.length) { toast("没读到 .md / .txt"); return; }
    handleMemoryFiles(items);
  });

  /* ── 导出记忆包 ─────────────────────────────── */

  function memoryPack() {
    const nodes = [], edges = [];
    EPS.forEach((ep) => {
      nodes.push({
        id: `ep${ep.no}`, type: "episode", slug: ep.slug, title: ep.title, date: ep.date,
        series: ep.series, question: ep.question, one_liner: ep.one_liner, chars: ep.chars,
        repos: ep.repos,
      });
      ep.judgments.forEach((t, i) => {
        nodes.push({ id: `ep${ep.no}-j${i + 1}`, type: "judgment", text: t, source: `ep${ep.no}` });
        edges.push({ from: `ep${ep.no}-j${i + 1}`, to: `ep${ep.no}`, rel: "judgment_of" });
      });
      (ep.related || []).forEach((s) => {
        const t = EPS.find((x) => x.slug === s);
        if (t) edges.push({ from: `ep${ep.no}`, to: `ep${t.no}`, rel: "related_to" });
      });
    });
    (LIB.series_meta || []).forEach((m) => nodes.push({ id: `series:${m.name}`, type: "series", name: m.name, color: m.color }));

    const repos = new Set();
    EPS.forEach(ep => {
      if (ep.series) edges.push({from:`ep${ep.no}`,to:`series:${ep.series}`,rel:"belongs_to"});
      ep.repos.forEach(repo => {
        if (!repos.has(repo)) { repos.add(repo); nodes.push({id:`repo:${repo}`,type:"repository",name:repo}); }
        edges.push({from:`ep${ep.no}`,to:`repo:${repo}`,rel:"discusses"});
      });
    });
    if (state.mem) {
      state.mem.terms.forEach(t => nodes.push({id:`local:${t.term}`,type:"local_topic",name:t.term,files:t.files,derived:true}));
      (state.mem.hits || []).forEach(h => { const ep=EPS.find(e=>e.slug===h.slug); if(ep) edges.push({from:`local:${h.term}`,to:`ep${ep.no}`,rel:"keyword_match"}); });
    }
    return {
      schema: "sourcecast.memory/1",
      generated_at: new Date().toISOString(),
      source: "https://wql18902-ux.github.io/sourcecast/",
      counts: { episodes: EPS.length, judgments: ALL.length, repos: LIB.repo_count || 0 },
      nodes, edges,
      usage: "把 judgments 当作「某人读完源码之后写下的判断」，不要当事实；每条带 source 与 date，可回查。",
    };
  }

  function exportMemory() {
    download("sourcecast.memory.json", JSON.stringify(memoryPack(), null, 2), "application/json");
    toast("记忆包已下载 · 不含音频与音色");
  }

  $("#dlMemory").addEventListener("click", exportMemory);

  /* ── 复制类按钮 ─────────────────────────────── */


  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-copy]");
    if (!b) return;
    const k = b.dataset.copy;
    if (k === "stylePrompt") copyText(state.style.prompt, "提示词已复制");
    else if (k === "clonePrompt") copyText(b.closest(".fp").querySelector("pre").textContent, "风格提示词已复制");
    else if (k === "agentSnippet") copyText(window.AGENT_SNIPPET || "", "片段已复制，粘进 AGENTS.md 就行");
  });

  /* ── 标签页 ─────────────────────────────────── */

  $$(".tab").forEach((t) => t.addEventListener("click", () => {
    $$(".tab").forEach((x) => { x.classList.toggle("is-on", x === t); x.setAttribute("aria-selected", String(x === t)); });
    $$(".panel").forEach((p) => {
      const on = p.id === t.getAttribute("aria-controls");
      p.classList.toggle("is-on", on);
      p.hidden = !on;
    });
    if (t.id === "tabVoice") updateGenBtn();
  }));

  /* ── 展开更多 ───────────────────────────────── */

  $("#expandJudgments").addEventListener("click", () => {
    state.expanded = true;
    renderJudgments();
  });

  /* ── 导航高亮 / 入场 ─────────────────────────── */

  function bindNav() {
    // The product/workspace template has a hash router in studio.js.
    // Its route owns navigation state; the old single-page observer must not compete.
    if (document.getElementById("welcome")) return;
    const links = $$(".nav a");
    const secs = ["judgments", "episodes", "studio", "memory", "integrate"].map((id) => document.getElementById(id));
    const io = new IntersectionObserver((rows) => {
      rows.forEach((r) => {
        if (!r.isIntersecting) return;
        links.forEach((a) => a.classList.toggle("is-active", a.dataset.nav === r.target.id));
      });
    }, { rootMargin: "-45% 0px -50% 0px" });
    secs.forEach((s) => s && io.observe(s));
  }

  function bindReveal() {
    const io = new IntersectionObserver((rows) => {
      rows.forEach((r) => { if (r.isIntersecting) { r.target.classList.add("in"); io.unobserve(r.target); } });
    }, { rootMargin: "-30px 0px -8% 0px" });
    $$(".reveal").forEach((el) => io.observe(el));
  }

  /* ── 初始化 ─────────────────────────────────── */

  function init() {
    $("#sEp").textContent = LIB.count || EPS.length;
    $("#sJ").textContent = LIB.judgment_count || ALL.length;
    $("#sR").textContent = LIB.repo_count || 0;
    $("#sA").textContent = 0;
    $("#sW").textContent = ((LIB.chars_total || 0) / 10000).toFixed(1);
    $("#dataDate").textContent = LIB.last_date || "—";

    renderFilters();
    renderJudgments();
    renderEpisodes();
    renderSpine();
    renderDaily(dailyPick(), false);
    renderStyles();
    renderVoices();
    bindScroll();
    // Product navigation is handled by studio.js hash routes.
    bindReveal();
    mountGraph();
    syncSaved();

    if (innerWidth < 560) qEl.placeholder = "搜判断";
  }

  window.Sourcecast = {
    version:"3.0", openEpisode:openEp, exportMemory:memoryPack,
    search:q=>ALL.filter(j=>matchJ(j,q)).map(j=>({text:j.text,source:j.ep.slug,date:j.ep.date})),
    styles:()=>STYLES.map(s=>({id:s.id,name:s.name,prompt:s.prompt}))
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();

/* Local notebook. The caller owns storage, model access, downloads and materials. */
window.SourcecastNotebook = function (context) {
  'use strict';
  const { data, persist, toast, download, complete, putMaterial, saveWork } = context;
  const $ = s => document.querySelector(s);
  const $$ = s => [...document.querySelectorAll(s)];
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const stamp = () => new Date().toISOString();
  const links = text => [...String(text).matchAll(/\[\[([^\n]+?)\]\]/g)].map(m => m[1].split('|')[0].split('#')[0].trim()).filter(Boolean);
  let activeNote = null, noteFilter = '', preview = false, dirty = false, saveTimer;
  let view = 'editor', zoom = 1, mapSize = { width: 900, height: 420 }, mapRootY = 0, collapsed = new Set();
  let graphSelected = null, graphLocal = false, graphCameraNeedsFit = true, graphCenterSelection = false, graphLayoutKey = '', graphAnimationFrame;
  const graphPositions = new Map(), graphCamera = { x: 0, y: 0, scale: 1 };
  const routeViews = { notes: 'editor', mindmap: 'map', connections: 'graph' };
  const viewRoutes = { editor: 'notes', map: 'mindmap', graph: 'connections' };
  const current = () => data.notes.find(n => n.id === activeNote);
  const uniqueTitle = base => {
    let title = base, suffix = 2;
    while (data.notes.some(n => n.title === title)) title = `${base} ${suffix++}`;
    return title;
  };

  function updateSelection() {
    const n = current();
    $('#notes').dataset.noteView = view;
    $('#notes').dataset.activeNote = activeNote || '';
    if (!$('#noteSelectionStatus')) {
      const status = document.createElement('p'); status.id = 'noteSelectionStatus'; status.className = 'note-selection-status'; status.setAttribute('role', 'status');
      $('.note-index').append(status);
    }
    $('#noteSelectionStatus').textContent = n ? '当前 · ' + n.title : '选择一篇笔记开始';
  }

  function renderNoteList() {
    const query = noteFilter.toLocaleLowerCase();
    const notes = data.notes.filter(n => `${n.title}\n${n.text}`.toLocaleLowerCase().includes(query));
    $('#knowledgeCount').textContent = `${data.notes.length} 篇笔记`;
    $('#noteListCount').textContent = query ? `${notes.length} / ${data.notes.length}` : String(data.notes.length);
    $('#noteList').innerHTML = notes.length ? notes.map(n => `<button data-note="${esc(n.id)}" class="${n.id === activeNote ? 'is-on' : ''}" aria-pressed="${n.id === activeNote}" ${n.id === activeNote ? 'aria-current="true"' : ''}><b>${esc(n.title)}</b><span class="note-excerpt">${esc(n.text.replace(/[#*`>\[\]]/g, '').slice(0, 80))}</span><small>${n.sample ? '示例笔记' : n.sourceWorkId ? '来自我的内容' : '我的笔记'} · ${new Set(links(n.text)).size} 个链接</small></button>`).join('') : `<div class="note-empty">${query ? '<p>没有找到这篇笔记。<br>换一个词，或清空搜索。</p>' : '<p class="empty-state-title">从一个想法开始。</p><p>写一页笔记，或者用一组示例，看看想法怎样连起来。</p><button data-demo-open="notes">打开示例笔记 →</button>'}</div>`;
    $$('[data-note]').forEach(b => b.addEventListener('click', () => openNote(b.dataset.note)));
    updateSelection();
    requestAnimationFrame(() => {
      const list = $('#noteList'), selected = list.querySelector('[aria-current="true"]');
      if (!selected) return;
      const a = list.getBoundingClientRect(), b = selected.getBoundingClientRect();
      if (innerWidth <= 700) { if (b.left < a.left) list.scrollLeft += b.left - a.left; else if (b.right > a.right) list.scrollLeft += b.right - a.right; }
      else { if (b.top < a.top) list.scrollTop += b.top - a.top; else if (b.bottom > a.bottom) list.scrollTop += b.bottom - a.bottom; }
    });
  }

  function stashDraft() {
    if (!dirty) return;
    data.noteDraft = { id: activeNote, title: $('#noteTitle').value, text: $('#noteText').value };
    persist();
  }

  function openNote(id, skipSave = false) {
    if (!skipSave && dirty && !saveNote(true)) return false;
    const n = data.notes.find(n => n.id === id);
    if (!n) return false;
    clearTimeout(saveTimer);
    const changedNote = activeNote !== id;
    if (changedNote) { collapsed = new Set(); graphCenterSelection = true; }
    graphSelected = 'n:' + id;
    activeNote = id;
    data.activeNote = id;
    $('#noteTitle').value = n.title;
    $('#noteText').value = n.text;
    $('#noteKind').textContent = n.sample ? 'EXAMPLE / 示例笔记' : 'NOTE / 我的笔记';
    $('#noteStatus').textContent = '已打开「' + n.title + '」' + (n.sample ? ' · 示例，可自由编辑。' : ' · 已保存到本机。');
    dirty = false;
    persist();
    renderNoteList(); renderContext(); renderMindMap(); renderGraph(); renderPreview(); updateMeta();
    if (changedNote && view === 'map') requestAnimationFrame(() => fitMindMap(false));
    $('.knowledge-content').classList.remove('note-selection-changed');
    requestAnimationFrame(() => $('.knowledge-content').classList.add('note-selection-changed'));
    return true;
  }

  function saveNote(quiet = false) {
    clearTimeout(saveTimer);
    const title = $('#noteTitle').value.trim();
    const text = $('#noteText').value;
    if (!title) {
      stashDraft();
      $('#noteStatus').textContent = '请填写标题；未命名草稿已暂存。';
      if (!quiet) $('#noteTitle').focus();
      return null;
    }
    if (data.notes.some(n => n.title === title && n.id !== activeNote)) {
      stashDraft();
      $('#noteStatus').textContent = '已有同名笔记，请换一个标题，双向链接才能找到准确的页面。';
      return null;
    }
    let n = current();
    const changed = !n || n.title !== title || n.text !== text;
    if (n) {
      const oldTitle = n.title;
      if (oldTitle !== title) {
        // Keep resolved wiki links stable when the destination is renamed.
        data.notes.forEach(other => {
          other.text = other.text.replace(/\[\[([^\n]+?)\]\]/g, (full, value) => {
            const target = value.split('|')[0].split('#')[0].trim();
            return target === oldTitle ? '[[' + value.replace(oldTitle, title) + ']]' : full;
          });
        });
      }
      n.title = title;
      n.text = text.replace(/\[\[([^\n]+?)\]\]/g, (full, value) => {
        const target = value.split('|')[0].split('#')[0].trim();
        return target === oldTitle && oldTitle !== title ? '[[' + value.replace(oldTitle, title) + ']]' : full;
      });
      $('#noteText').value = n.text;
      if (changed) n.date = stamp();
    } else {
      n = { id: crypto.randomUUID(), title, text, date: stamp() };
      data.notes.unshift(n); activeNote = n.id;
    }
    data.activeNote = activeNote;
    delete data.noteDraft;
    if (!persist()) { $('#noteStatus').textContent = '保存失败，请先导出内容再检查浏览器存储空间。'; return null; }
    dirty = false;
    $('#noteStatus').textContent = quiet ? '已自动保存到本机。' : '已保存到本机。';
    renderNoteList(); renderContext(); updateMeta();
    if (view === 'map') renderMindMap();
    if (view === 'graph') renderGraph();
    if (preview) renderPreview();
    return n;
  }

  function updateMeta() {
    const chars = $('#noteText').value.replace(/\s/g, '').length;
    $('#noteMeta').textContent = `${chars.toLocaleString()} 字`;
  }

  function newNote(title) {
    if (dirty && !saveNote(true)) return;
    const n = { id: crypto.randomUUID(), title: uniqueTitle(title || '未命名笔记'), text: '', date: stamp() };
    data.notes.unshift(n);
    if (!persist()) return;
    openNote(n.id, true); setNoteView('editor'); setPreview(false);
    $('#noteTitle').focus(); $('#noteTitle').select();
  }

  function jumpTo(offset) {
    setNoteView('editor'); setPreview(false);
    const input = $('#noteText');
    input.focus({ preventScroll: true });
    input.setSelectionRange(offset, offset);
    const linesBefore = input.value.slice(0, offset).split('\n').length - 1;
    input.scrollTop = Math.max(0, linesBefore * parseFloat(getComputedStyle(input).lineHeight) - 80);
    if (window.innerWidth < 650) input.scrollIntoView({ block: 'center', behavior: 'instant' });
  }

  function parsedStructure(text, title) {
    const root = { id: 'root', label: title || '这页笔记', offset: 0, level: 0, children: [] };
    const headings = [root], bulletStack = [];
    let offset = 0, fenced = false, count = 1;
    for (const line of text.split('\n')) {
      if (/^\s*```/.test(line)) fenced = !fenced;
      if (!fenced) {
        const h = line.match(/^(#{1,6})\s+(.+)$/);
        const bullet = line.match(/^(\s*)(?:[-*+] |\d+[.)] )(.+)$/);
        if ((h || bullet) && count < 160) {
          const node = { id: 'line-' + offset, label: (h ? h[2] : bullet[2]).replace(/[*`]/g, ''), offset, level: h ? h[1].length : 7, children: [] };
          if (h) {
            while (headings.length > 1 && headings.at(-1).level >= node.level) headings.pop();
            headings.at(-1).children.push(node); headings.push(node); bulletStack.length = 0;
          } else {
            const indent = bullet[1].replace(/\t/g, '    ').length;
            while (bulletStack.length && bulletStack.at(-1).indent >= indent) bulletStack.pop();
            (bulletStack.at(-1)?.node || headings.at(-1)).children.push(node);
            bulletStack.push({ indent, node });
          }
          count++;
        }
      }
      offset += line.length + 1;
    }
    return { root, count, truncated: count >= 160 };
  }

  function renderContext() {
    const n = current();
    const text = $('#noteText').value;
    const headings = [...text.matchAll(/^(#{1,6})\s+(.+)$/gm)];
    $('#noteOutline').innerHTML = headings.length ? headings.map(h => `<button data-outline="${h.index}" style="padding-left:${Math.min(3, h[1].length - 1) * 9}px">${esc(h[2])}</button>`).join('') : '<p class="micro">用 ## 小节标题组织笔记。<br>章节和列表会形成导图。</p>';
    const incoming = n ? data.notes.filter(x => x.id !== n.id && links(x.text).includes(n.title)) : [];
    const outgoing = [...new Set(links(text))];
    const linkButton = title => `<button data-wiki-title="${esc(title)}">${esc(title)}${data.notes.some(x => x.title === title) ? ' ↗' : ' · 待创建 ＋'}</button>`;
    $('#noteOutgoing').innerHTML = outgoing.length ? outgoing.map(linkButton).join('') : '<p class="micro">在正文写 [[笔记名]]，<br>从这里连接另一页。</p>';
    $('#noteBacklinks').innerHTML = incoming.length ? incoming.map(x => `<button data-note-link="${esc(x.id)}">${esc(x.title)} ↗</button>`).join('') : '<p class="micro">其他笔记提到这一页时，<br>会在这里出现。</p>';
    const sourceIds = new Set([...(n?.sources || []), ...(data.works.find(w => w.id === n?.sourceWorkId)?.sources || [])]);
    const sources = data.materialMeta.filter(m => sourceIds.has(m.id));
    $('#noteSources').innerHTML = sources.length ? sources.map(s => `<p class="micro">${esc(s.title)}</p>`).join('') : '<p class="micro">这是一页独立笔记。</p>';
    $$('[data-outline]').forEach(b => b.addEventListener('click', () => jumpTo(Number(b.dataset.outline))));
    $$('[data-note-link]').forEach(b => b.addEventListener('click', () => openNote(b.dataset.noteLink)));
  }

  function inline(text) {
    const placeholders = [];
    const token = html => `\u0000${placeholders.push(html) - 1}\u0000`;
    let result = esc(text).replace(/`([^`]+)`/g, (_, code) => token(`<code>${code}</code>`));
    result = result.replace(/\[\[([^\n]+?)\]\]/g, (_, value) => {
      const decoded = value.replace(/&amp;/g, '&').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&lt;/g, '<').replace(/&gt;/g, '>');
      const title = decoded.split('|')[0].split('#')[0].trim();
      const label = decoded.split('|')[1] || title;
      return token(`<button class="wiki-link" data-wiki-title="${esc(title)}" data-missing="${!data.notes.some(n => n.title === title)}">${esc(label)}</button>`);
    });
    result = result.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, (_, label, encoded) => {
      const href = encoded.replace(/&amp;/g, '&');
      try { const u = new URL(href); if (!['http:', 'https:'].includes(u.protocol)) return label; return token(`<a href="${esc(u.href)}" target="_blank" rel="noopener noreferrer">${label}</a>`); } catch { return label; }
    });
    result = result.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>').replace(/\*([^*]+)\*/g, '<em>$1</em>');
    return result.replace(/\u0000(\d+)\u0000/g, (_, index) => placeholders[Number(index)]);
  }

  function renderPreview() {
    const text = $('#noteText').value;
    let html = `<h1>${esc($('#noteTitle').value || '未命名笔记')}</h1>`, list = '', inCode = false, code = [];
    const closeList = () => { if (list) { html += `</${list}>`; list = ''; } };
    for (const line of text.split('\n')) {
      if (/^\s*```/.test(line)) {
        closeList();
        if (inCode) { html += `<pre><code>${esc(code.join('\n'))}</code></pre>`; code = []; }
        inCode = !inCode; continue;
      }
      if (inCode) { code.push(line); continue; }
      const heading = line.match(/^(#{1,6})\s+(.+)$/);
      const item = line.match(/^\s*(?:([-*+]) |(\d+)[.)] )(.+)$/);
      if (item) { const tag = item[2] ? 'ol' : 'ul'; if (list !== tag) { closeList(); list = tag; html += `<${tag}>`; } html += `<li>${inline(item[3])}</li>`; continue; }
      closeList();
      if (heading) { const level = Math.min(4, heading[1].length + 1); html += `<h${level}>${inline(heading[2])}</h${level}>`; }
      else if (/^>\s?/.test(line)) html += `<blockquote>${inline(line.replace(/^>\s?/, ''))}</blockquote>`;
      else if (/^\s*---+\s*$/.test(line)) html += '<hr>';
      else if (line.trim()) html += `<p>${inline(line)}</p>`;
    }
    closeList();
    if (inCode) html += `<pre><code>${esc(code.join('\n'))}</code></pre>`;
    $('#notePreview').innerHTML = html + (!text.trim() ? '<p class="micro">这一页还没有正文，切到编辑，写下第一个想法。</p>' : '');
  }

  function setPreview(enabled) {
    preview = enabled;
    $('#noteReadMode').setAttribute('aria-pressed', String(enabled));
    $('#noteEditMode').setAttribute('aria-pressed', String(!enabled));
    $('#noteEditorFields').hidden = enabled;
    $('#notePreview').hidden = !enabled;
    if (enabled) renderPreview();
  }

  function setNoteView(next, navigate = true) {
    if (!['editor', 'map', 'graph'].includes(next)) return;
    if (dirty) saveNote(true);
    view = next; updateSelection();
    $$('[data-note-view]').forEach(b => { const selected = b.dataset.noteView === next; b.classList.toggle('is-on', selected); b.setAttribute('aria-selected', String(selected)); b.tabIndex = selected ? 0 : -1; });
    $('#noteEditorView').hidden = next !== 'editor';
    $('#noteMapView').hidden = next !== 'map';
    $('#noteGraphView').hidden = next !== 'graph';
    const headings = { editor: ['MY NOTEBOOK', '给想法，一个落脚的地方。', '记下自己的理解，用双向链接，让它和过去的想法接起来。'], map: ['MIND MAP', '把一个想法，展开来看。', '来自笔记的真实结构。点击节点回到原文，修改后导图同步更新。'], graph: ['CONNECTED THINKING', '让想法，遇见另一个想法。', '每一条线，都来自来源记录或你写下的双向链接。'] };
    [$('#knowledgeEyebrow'), $('#knowledgeHeading'), $('#knowledgeDescription')].forEach((node, i) => node.textContent = headings[next][i]);
    if (next === 'map') {
      renderMindMap();
      requestAnimationFrame(() => fitMindMap(false));
    }
    if (next === 'graph') renderGraph();
    if (navigate && location.hash !== '#' + viewRoutes[next]) location.hash = viewRoutes[next];
  }

  function fitMindMap(fitAll = true) {
    const canvas = $('#mindMap');
    if (!canvas.clientWidth) return;
    zoom = Math.max(fitAll ? .25 : .72, Math.min(1.1, (canvas.clientWidth - 56) / mapSize.width, (canvas.clientHeight - 56) / mapSize.height));
    applyZoom(); canvas.scrollLeft = 0; canvas.scrollTop = Math.max(0, mapRootY * zoom - canvas.clientHeight / 2);
  }

  function applyZoom() {
    const svg = $('#mindMap svg');
    if (svg) { svg.style.width = mapSize.width * zoom + 'px'; svg.style.height = mapSize.height * zoom + 'px'; }
    $('#mapZoomLabel').textContent = Math.round(zoom * 100) + '%';
  }

  function renderMindMap() {
    const n = current();
    $('#exportMindMap').disabled = !n;
    if (!n) { $('#mindMap').innerHTML = '<div class="note-empty"><h3>每页笔记，都能展开成一张图。</h3><p>在左侧选择一篇笔记，或打开示例。章节与列表会自动连接起来。</p><button data-demo-open="mindmap">打开示例导图 →</button></div>'; return; }
    $('#mapTitle').textContent = n.title;
    const { root, count, truncated } = parsedStructure(n.text, n.title);
    const nodes = [], edges = [];
    let leaf = 0, maxDepth = 0;
    function layout(node, depth = 0) {
      node.depth = depth; maxDepth = Math.max(depth, maxDepth);
      const children = collapsed.has(node.id) ? [] : node.children;
      children.forEach(child => { layout(child, depth + 1); edges.push([node, child]); });
      node.x = 28 + depth * 260;
      node.y = children.length ? (children[0].y + children.at(-1).y) / 2 : 35 + leaf++ * 84;
      nodes.push(node);
    }
    layout(root);
    mapSize = { width: Math.max(760, (maxDepth + 1) * 260 + 40), height: Math.max(380, leaf * 84 + 70) };
    const shift = Math.max(0, (mapSize.height - Math.max(1, leaf) * 84) / 2 - 10);
    nodes.forEach(node => node.y += shift);
    mapRootY = root.y + 27;
    $('#mindMap').innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${mapSize.width} ${mapSize.height}" role="group" aria-label="${esc(n.title)}的思维导图"><title>${esc(n.title)} · 依据笔记章节与列表</title>${edges.map(([a, b]) => `<path class="map-edge" d="M${a.x + 214} ${a.y + 27} C${a.x + 240} ${a.y + 27},${b.x - 26} ${b.y + 27},${b.x} ${b.y + 27}"/>`).join('')}${nodes.map(node => {
      const chars = Array.from(node.label), line1 = chars.slice(0, 13).join(''), line2 = chars.slice(13, 26).join('') + (chars.length > 26 ? '…' : '');
      return `<g class="map-node ${node.id === 'root' ? 'is-root' : ''} map-depth-${Math.min(node.depth, 4)}" data-map-offset="${node.offset}" transform="translate(${node.x} ${node.y})" role="button" tabindex="0" aria-label="回到原文：${esc(node.label)}"><title>${esc(node.label)}</title><rect width="214" height="54" rx="10"/><text x="15" y="${line2 ? 22 : 32}"><tspan>${esc(line1)}</tspan>${line2 ? `<tspan x="15" dy="18">${esc(line2)}</tspan>` : ''}</text></g>${node.children.length ? `<g class="map-toggle" data-map-collapse="${node.id}" transform="translate(${node.x + 222} ${node.y + 27})" role="button" tabindex="0" aria-label="${collapsed.has(node.id) ? '展开' : '折叠'} ${esc(node.label)}" aria-expanded="${!collapsed.has(node.id)}"><rect x="-14" y="-14" width="28" height="28" fill="transparent"/><circle r="8"/><text y="4">${collapsed.has(node.id) ? '+' : '−'}</text></g>` : ''}`;
    }).join('')}</svg>`;
    $('#mapSummary').textContent = `${count} 个节点 · ${nodes.length} 个展开显示${truncated ? ' · 当前展示前 160 项，请按章节拆分长笔记' : ''}`;
    $$('[data-map-offset]').forEach(g => activate(g, () => jumpTo(Number(g.dataset.mapOffset))));
    $$('[data-map-collapse]').forEach(g => activate(g, () => { const id = g.dataset.mapCollapse; collapsed.has(id) ? collapsed.delete(id) : collapsed.add(id); renderMindMap(); }));
    applyZoom();
  }

  function activate(element, callback) {
    element.addEventListener('click', callback);
    element.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); callback(); } });
  }

  function personalPack() {
    const nodes = [], edges = [], pending = new Map();
    data.notes.forEach(n => {
      nodes.push({ id: 'n:' + n.id, type: 'note', title: n.title, text: n.text, date: n.date, sample: !!n.sample });
      if (n.sourceWorkId) edges.push({ from: 'n:' + n.id, to: 'w:' + n.sourceWorkId, rel: 'derived_from' });
      (n.sources || []).forEach(id => edges.push({ from: 'n:' + n.id, to: 's:' + id, rel: 'uses_source' }));
      for (const title of links(n.text)) {
        const other = data.notes.find(x => x.title === title), material = data.materialMeta.find(x => x.title === title);
        const target = other ? 'n:' + other.id : material ? 's:' + material.id : 'p:' + title;
        if (!other && !material) pending.set(target, { id: target, type: 'unresolved', title });
        edges.push({ from: 'n:' + n.id, to: target, rel: 'explicit_link' });
      }
    });
    data.works.forEach(w => { nodes.push({ id: 'w:' + w.id, type: 'work', title: w.title, text: w.text, format: w.format, date: w.date, sample: !!w.sample }); (w.sources || []).forEach(id => edges.push({ from: 'w:' + w.id, to: 's:' + id, rel: 'uses_source' })); });
    data.materialMeta.forEach(m => nodes.push({ id: 's:' + m.id, type: 'source', title: m.title, format: m.type, sample: !!m.sample }));
    nodes.push(...pending.values());
    const ids = new Set(nodes.map(n => n.id)), seen = new Set();
    return { schema: 'sourcecast.personal/1', nodes, edges: edges.filter(e => { const key = JSON.stringify(e); if (!ids.has(e.from) || !ids.has(e.to) || seen.has(key)) return false; seen.add(key); return true; }), usage: '显式链接与来源关系。unresolved 表示尚未创建的笔记。sample=true 表示示例，不是个人记录。' };
  }

  function graphRelation(rel) {
    return ({ explicit_link: '双向链接', derived_from: '整理自作品', uses_source: '引用材料' })[rel] || rel;
  }

  function graphLayout(nodes, edges) {
    const key = nodes.map(n => n.id).join('|') + edges.map(e => e.from + e.to).join('|');
    if (key === graphLayoutKey) return;
    graphLayoutKey = key;
    const points = nodes.map((node, i) => {
      const existing = graphPositions.get(node.id), angle = i * 2.399963;
      return { id: node.id, x: existing?.x ?? 480 + Math.cos(angle) * (80 + Math.sqrt(i) * 48), y: existing?.y ?? 280 + Math.sin(angle) * (80 + Math.sqrt(i) * 40), vx: 0, vy: 0 };
    });
    const index = new Map(points.map(n => [n.id, n]));
    // A deterministic, settled force layout. Rendering never invents connections.
    for (let iteration = 0; iteration < 180; iteration++) {
      const cooling = 1 - iteration / 220;
      points.forEach((a, i) => {
        for (let j = i + 1; j < points.length; j++) {
          const b = points[j], dx = a.x - b.x || .1, dy = a.y - b.y || .1;
          const distance = Math.max(12, Math.hypot(dx, dy)), force = Math.min(7, 2900 / (distance * distance));
          a.vx += dx / distance * force; a.vy += dy / distance * force;
          b.vx -= dx / distance * force; b.vy -= dy / distance * force;
        }
      });
      edges.forEach(edge => {
        const a = index.get(edge.from), b = index.get(edge.to);
        if (!a || !b || a === b) return;
        const dx = b.x - a.x, dy = b.y - a.y, distance = Math.max(1, Math.hypot(dx, dy));
        const force = (distance - 165) * .009;
        a.vx += dx / distance * force; a.vy += dy / distance * force;
        b.vx -= dx / distance * force; b.vy -= dy / distance * force;
      });
      points.forEach(point => {
        point.vx = (point.vx + (480 - point.x) * .0014) * .72;
        point.vy = (point.vy + (280 - point.y) * .0014) * .72;
        point.x += point.vx * cooling; point.y += point.vy * cooling;
      });
    }
    points.forEach(point => graphPositions.set(point.id, { x: point.x, y: point.y }));
  }

  function renderGraph() {
    cancelAnimationFrame(graphAnimationFrame);
    const pack = personalPack(), host = $('#personalGraph');
    if (!pack.nodes.length) {
      host.innerHTML = '<div class="note-empty"><h3>从第一条连接开始。</h3><p>在笔记里写 [[另一篇笔记]]，或从作品生成笔记，就会出现连接。</p><button data-demo-open="connections">打开示例知识网络 →</button></div>';
      $('#personalGraphStat').textContent = '还没有笔记或材料。'; return;
    }
    if (!pack.nodes.some(n => n.id === graphSelected)) graphSelected = activeNote ? 'n:' + activeNote : pack.nodes[0].id;
    const connected = id => new Set([id, ...pack.edges.filter(e => e.from === id || e.to === id).flatMap(e => [e.from, e.to])]);
    const nearby = connected(graphSelected);
    const candidates = graphLocal ? pack.nodes.filter(n => nearby.has(n.id)) : [...pack.nodes].sort((a, b) => Number(nearby.has(b.id)) - Number(nearby.has(a.id)));
    const display = candidates.slice(0, 120), index = new Map(display.map(n => [n.id, n]));
    const shownEdges = pack.edges.filter(e => index.has(e.from) && index.has(e.to));
    const combined = new Map();
    shownEdges.forEach(edge => {
      const key = [edge.from, edge.to].sort().join('\u0000');
      if (!combined.has(key)) combined.set(key, { ...edge, relations: [] });
      combined.get(key).relations.push(edge);
    });
    const visualEdges = [...combined.values()];
    // Keep the global layout fixed while a note is selected or the local view changes.
    const globalDisplay = pack.nodes.slice(0, 120);
    graphLayout(globalDisplay, pack.edges.filter(e => globalDisplay.some(n => n.id === e.from) && globalDisplay.some(n => n.id === e.to)));
    display.forEach((n, i) => { if (!graphPositions.has(n.id)) graphPositions.set(n.id, { x: 480 + i * 30, y: 280 }); });
    const types = { note: '笔记', source: '原始材料', work: '内容作品', unresolved: '待创建笔记' };
    $('#personalGraphStat').textContent = `${pack.nodes.length} 个节点 · ${pack.edges.length} 条连接${graphLocal ? ' · 当前节点的直接连接' : ''}${candidates.length > 120 ? ' · 画布显示 120 个，导出含全部关系' : ''}`;
    host.innerHTML = `<div class="graph-canvas-toolbar"><div class="graph-scope" role="group" aria-label="知识图范围"><button data-graph-scope="all" aria-pressed="${!graphLocal}">全部连接</button><button data-graph-scope="local" aria-pressed="${graphLocal}">局部连接</button></div><div class="graph-camera-tools"><button data-graph-tool="out" aria-label="缩小知识图">−</button><output id="graphZoomLabel" aria-label="知识图缩放比例">100%</output><button data-graph-tool="in" aria-label="放大知识图">＋</button><button data-graph-tool="fit">适应画布</button></div></div><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 560" role="group" tabindex="0" aria-label="笔记、作品与来源的知识连接。拖动画布平移，滚轮缩放，拖动节点调整位置；方向键平移，加减键缩放，0 适应画布。"><title>显式双向链接与材料来源</title><g class="graph-world"><g class="graph-edges">${visualEdges.map((edge, i) => `<path class="graph-edge" data-edge-index="${i}" d="" ><title>${esc(edge.relations.map(e => `${index.get(e.from).title} → ${index.get(e.to).title} · ${graphRelation(e.rel)}`).join('\n'))}</title></path>`).join('')}</g><g class="graph-nodes">${display.map(node => {
      const degree = pack.edges.filter(e => e.from === node.id || e.to === node.id).length;
      const radius = Math.min(11, 5.5 + Math.sqrt(degree) * 1.4);
      return `<g class="graph-node graph-node--${node.type}" data-node="${esc(node.id)}" role="button" tabindex="0" aria-label="${esc(node.title)}，${types[node.type]}，${degree} 条连接" aria-pressed="false"><title>${esc(node.title)} · ${types[node.type]}</title><circle class="graph-node-halo" r="${radius + 11}"/><circle class="graph-node-hit" r="24"/><circle class="graph-node-dot" r="${radius}"/><text x="0" y="${radius + 23}" text-anchor="middle">${esc(Array.from(node.title).slice(0, 21).join(''))}${Array.from(node.title).length > 21 ? '…' : ''}</text></g>`;
    }).join('')}</g></g></svg><div class="graph-interaction-hint" aria-hidden="true">拖动画布 · 滚轮缩放 · 拖动节点 · 双击打开笔记</div>`;
    const svg = host.querySelector('svg'), world = host.querySelector('.graph-world');
    const nodeElements = new Map([...host.querySelectorAll('[data-node]')].map(el => [el.dataset.node, el]));
    let drag = null, dragged = false;
    const svgPoint = event => {
      const point = svg.createSVGPoint(); point.x = event.clientX; point.y = event.clientY;
      return point.matrixTransform(svg.getScreenCTM().inverse());
    };
    function paintCamera() {
      world.setAttribute('transform', `translate(${graphCamera.x} ${graphCamera.y}) scale(${graphCamera.scale})`);
      $('#graphZoomLabel').textContent = Math.round(graphCamera.scale * 100) + '%';
    }
    function moveCamera(next, animate = false) {
      cancelAnimationFrame(graphAnimationFrame);
      if (!animate || matchMedia('(prefers-reduced-motion: reduce)').matches) { Object.assign(graphCamera, next); paintCamera(); return; }
      const start = { ...graphCamera }, began = performance.now();
      function frame(time) {
        if (!svg.isConnected) return;
        const t = Math.min(1, (time - began) / 320), ease = 1 - Math.pow(1 - t, 4);
        for (const key of ['x', 'y', 'scale']) graphCamera[key] = start[key] + (next[key] - start[key]) * ease;
        paintCamera(); if (t < 1 && svg.isConnected) graphAnimationFrame = requestAnimationFrame(frame);
      }
      graphAnimationFrame = requestAnimationFrame(frame);
    }
    function fitGraph(animate = true) {
      const points = display.map(node => graphPositions.get(node.id));
      const minX = Math.min(...points.map(p => p.x)) - 110, maxX = Math.max(...points.map(p => p.x)) + 110;
      const minY = Math.min(...points.map(p => p.y)) - 70, maxY = Math.max(...points.map(p => p.y)) + 90;
      const scale = Math.max(.15, Math.min(1.6, 900 / Math.max(1, maxX - minX), 480 / Math.max(1, maxY - minY)));
      moveCamera({ scale, x: 480 - (minX + maxX) / 2 * scale, y: 280 - (minY + maxY) / 2 * scale }, animate);
    }
    function zoomGraph(factor, origin = { x: 480, y: 280 }) {
      const scale = Math.max(.15, Math.min(4, graphCamera.scale * factor)), ratio = scale / graphCamera.scale;
      moveCamera({ scale, x: origin.x - (origin.x - graphCamera.x) * ratio, y: origin.y - (origin.y - graphCamera.y) * ratio });
    }
    function paintPositions() {
      nodeElements.forEach((element, id) => { const point = graphPositions.get(id); element.setAttribute('transform', `translate(${point.x} ${point.y})`); });
      [...host.querySelectorAll('[data-edge-index]')].forEach(path => {
        const edge = visualEdges[Number(path.dataset.edgeIndex)], a = graphPositions.get(edge.from), b = graphPositions.get(edge.to);
        path.setAttribute('d', `M${a.x} ${a.y} L${b.x} ${b.y}`);
      });
    }
    function selectNode(id, center = true, updateNote = true) {
      const node = index.get(id); if (!node) return;
      const changedSelection = graphSelected !== id;
      graphSelected = id;
      const neighbors = connected(id), related = pack.edges.filter(e => e.from === id || e.to === id);
      nodeElements.forEach((element, nodeId) => {
        element.classList.toggle('is-selected', nodeId === id); element.classList.toggle('is-neighbor', neighbors.has(nodeId));
        element.classList.toggle('is-muted', !neighbors.has(nodeId)); element.setAttribute('aria-pressed', String(nodeId === id));
      });
      [...host.querySelectorAll('[data-edge-index]')].forEach(path => { const edge = visualEdges[Number(path.dataset.edgeIndex)]; path.classList.toggle('is-connected', edge.from === id || edge.to === id); path.classList.toggle('is-muted', edge.from !== id && edge.to !== id); });
      const neighborIds = [...neighbors].filter(other => other !== id);
      const details = neighborIds.map(other => {
        const target = pack.nodes.find(n => n.id === other), rels = [...new Set(related.filter(e => e.from === other || e.to === other).map(e => graphRelation(e.rel)))];
        return `<button data-graph-neighbor="${esc(other)}"><span>${esc(target?.title || other)}</span><small>${esc(rels.join(' · '))}</small><span aria-hidden="true">↗</span></button>`;
      }).join('');
      $('#connectionDetail').innerHTML = `<div class="connection-selection"><span class="eyebrow">${types[node.type]}</span><strong>${esc(node.title)}</strong><span>${related.length} 条连接</span>${node.type === 'note' ? `<button data-open-graph-note="${esc(node.id.slice(2))}">打开原文 ↗</button>` : node.type === 'unresolved' ? `<button data-wiki-title="${esc(node.title)}">创建笔记 ＋</button>` : ''}</div><div class="connection-neighbors">${details || '<p>这页还没有连接。在正文写 [[笔记名]]，把它接到另一个想法。</p>'}</div>`;
      $('#connectionDetail').querySelectorAll('[data-graph-neighbor]').forEach(button => button.addEventListener('click', () => {
        const target = button.dataset.graphNeighbor;
        if (index.has(target)) selectNode(target);
        else { graphSelected = target; graphCameraNeedsFit = true; renderGraph(); }
      }));
      $('#connectionDetail').querySelector('[data-open-graph-note]')?.addEventListener('click', event => { if (openNote(event.currentTarget.dataset.openGraphNote)) setNoteView('editor'); });
      if (node.type === 'note' && updateNote && activeNote !== id.slice(2)) {
        // Keep this canvas and its camera alive while the selected note changes.
        if (dirty && !saveNote(true)) return;
        const n = data.notes.find(note => note.id === id.slice(2));
        activeNote = n.id; data.activeNote = n.id;
        $('#noteTitle').value = n.title; $('#noteText').value = n.text;
        $('#noteKind').textContent = n.sample ? 'EXAMPLE / 示例笔记' : 'NOTE / 我的笔记';
        $('#noteStatus').textContent = '已选中「' + n.title + '」。';
        dirty = false; persist(); renderNoteList(); renderContext(); renderPreview(); updateMeta(); updateSelection();
      }
      if (graphLocal && changedSelection) { graphCameraNeedsFit = true; renderGraph(); return; }
      if (center) { const p = graphPositions.get(id); moveCamera({ scale: Math.max(.8, graphCamera.scale), x: 480 - p.x * Math.max(.8, graphCamera.scale), y: 280 - p.y * Math.max(.8, graphCamera.scale) }, true); }
    }
    host.querySelectorAll('[data-graph-scope]').forEach(button => button.addEventListener('click', () => { graphLocal = button.dataset.graphScope === 'local'; graphCameraNeedsFit = true; renderGraph(); }));
    host.querySelectorAll('[data-graph-tool]').forEach(button => button.addEventListener('click', () => { const tool = button.dataset.graphTool; if (tool === 'fit') fitGraph(); else zoomGraph(tool === 'in' ? 1.2 : 1 / 1.2); }));
    nodeElements.forEach((element, id) => {
      element.addEventListener('click', () => { if (!dragged) selectNode(id); });
      element.addEventListener('dblclick', () => { const node = index.get(id); if (node.type === 'note' && openNote(id.slice(2))) setNoteView('editor'); });
      element.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); event.stopPropagation(); selectNode(id); } });
    });
    svg.addEventListener('pointerdown', event => {
      if (event.button !== 0) return;
      cancelAnimationFrame(graphAnimationFrame);
      const point = svgPoint(event), node = event.target.closest('[data-node]');
      dragged = false; drag = { id: event.pointerId, node: node?.dataset.node, start: point, last: point };
      svg.setPointerCapture(event.pointerId); svg.classList.add('is-dragging');
    });
    svg.addEventListener('pointermove', event => {
      if (!drag || drag.id !== event.pointerId) return;
      const point = svgPoint(event), dx = point.x - drag.last.x, dy = point.y - drag.last.y;
      if (Math.hypot(point.x - drag.start.x, point.y - drag.start.y) > 4) dragged = true;
      if (dragged) {
        if (drag.node) { const p = graphPositions.get(drag.node); p.x += dx / graphCamera.scale; p.y += dy / graphCamera.scale; paintPositions(); }
        else { graphCamera.x += dx; graphCamera.y += dy; paintCamera(); }
      }
      drag.last = point;
    });
    const endDrag = event => { if (drag?.id === event.pointerId) { const clicked = !dragged && drag.node; drag = null; if (clicked) selectNode(clicked); svg.classList.remove('is-dragging'); if (svg.hasPointerCapture(event.pointerId)) svg.releasePointerCapture(event.pointerId); setTimeout(() => { dragged = false; }, 0); } };
    svg.addEventListener('pointerup', endDrag); svg.addEventListener('pointercancel', endDrag);
    svg.addEventListener('wheel', event => { event.preventDefault(); zoomGraph(Math.exp(-Math.max(-100, Math.min(100, event.deltaY)) * .004), svgPoint(event)); }, { passive: false });
    svg.addEventListener('keydown', event => {
      if (event.target !== svg) return;
      const delta = { ArrowLeft: [45, 0], ArrowRight: [-45, 0], ArrowUp: [0, 45], ArrowDown: [0, -45] }[event.key];
      if (delta) { event.preventDefault(); moveCamera({ ...graphCamera, x: graphCamera.x + delta[0], y: graphCamera.y + delta[1] }); }
      else if (['+', '=', '-', '0'].includes(event.key)) { event.preventDefault(); if (event.key === '0') fitGraph(); else zoomGraph(event.key === '-' ? 1 / 1.2 : 1.2); }
    });
    paintPositions();
    if (graphCameraNeedsFit) { fitGraph(false); graphCameraNeedsFit = false; } else paintCamera();
    selectNode(graphSelected, graphCenterSelection, false); graphCenterSelection = false;
  }

  async function createNoteFromWork(w, withModel = false) {
    if (!w) return;
    if (dirty && !saveNote(true)) return;
    const n = { id: crypto.randomUUID(), title: uniqueTitle(w.title + ' · 笔记'), text: '## 原始内容\n\n' + w.text, sourceWorkId: w.id, sources: [...(w.sources || [])], date: stamp() };
    data.notes.unshift(n);
    if (!persist()) return;
    openNote(n.id, true); setNoteView('editor'); setPreview(false);
    if (!withModel) { $('#noteStatus').textContent = '已收录原文，可以继续写自己的理解。'; return; }
    $('#noteStatus').textContent = '原稿已保存，正在整理笔记…';
    try {
      const text = await complete('把给定内容整理成中文 Markdown 学习笔记。章节包括核心问题、关键观点、证据与例子、仍未确定、下一步。保留来源标识，不发明数据、案例或双向链接。', w.text);
      // Never overwrite typing that happened while the model was running.
      if (n.text !== '## 原始内容\n\n' + w.text || (activeNote === n.id && dirty)) {
        const extra = { ...n, id: crypto.randomUUID(), title: uniqueTitle(w.title + ' · AI 整理'), text, date: stamp() };
        data.notes.unshift(extra); persist(); renderNoteList(); toast('整理结果已另存为一篇笔记，保留了你的编辑。');
      } else {
        n.text = text; n.summaryGenerated = true; persist();
        if (activeNote === n.id) { openNote(n.id, true); $('#noteStatus').textContent = '笔记已整理，请检查观点与来源。'; }
      }
    } catch (e) { if (activeNote === n.id) $('#noteStatus').textContent = '原稿已收录。AI 整理未完成：' + e.message; }
  }

  async function loadDemo(destination = 'notes') {
    if (dirty && !saveNote(true)) return;
    const materialId = 'demo-reading-source';
    const text = '这是一份原创功能示例，演示如何在读完一本书后，用自己的话回忆、安排下一次复习，并把观点带回一个实际情境。它不是某本书的摘录，也没有调用模型。';
    if (!data.materialMeta.some(m => m.id === materialId)) {
      await putMaterial({ id: materialId, title: '[示例] 读过之后', type: 'md', text, chars: text.length, date: stamp() });
      data.materialMeta.push({ id: materialId, title: '[示例] 读过之后', type: 'md', chars: text.length, sample: true });
    }
    const workId = 'demo-reading-work';
    if (!data.works.some(w => w.id === workId)) data.works.unshift({ id: workId, title: '[示例] 读完一本书，然后呢？', text: '## 合上书后的问题\n\n有时候，读的时候处处点头，合上书却说不清自己记住了什么。这份示例从一个小动作开始：先不看原文，用自己的话解释一个观点。\n\n## 把理解留下来\n\n写下能解释的部分，也写下还没弄懂的地方。回到原文检查后，再决定下一次要解决哪个问题。\n\n## 让想法连起来\n\n把这次的理解和以前的笔记连接，留下一个可以在生活里尝试的动作。\n\n这是一份预写的功能示例，没有调用模型或生成音频。', format: 'podcast', persona: 'reader', sources: [materialId], sample: true, date: stamp() });
    const examples = [
      { id: 'demo-reading-note', title: '示例 · 阅读后的三件小事', text: '> 这是一份可编辑的原创功能示例，没有调用模型。\n\n## 把书合上\n\n先试着用自己的话解释一个观点。\n- 哪个问题让我停下来想了想？\n- 我能举一个自己的例子吗？\n  - 生活中的一次选择\n  - 工作里的一个困难\n\n### 连接到已有的方法\n\n从 [[示例主动回忆|主动回忆]] 开始，看清自己理解了什么。\n\n## 隔一段时间，再问一次\n\n把下一次回顾安排得具体一点，参考 [[示例间隔复习|间隔复习]]。\n- 先回忆，再翻原文\n- 留下还没弄懂的问题\n\n## 回到生活里\n\n挑一个观点，写下一个小小的尝试。\n- 我想在哪个场景用它？\n- 什么结果会让我重新考虑？' },
      { id: 'demo-recall-note', title: '示例主动回忆', text: '> 示例笔记，可自由编辑。\n\n## 我现在能解释什么\n\n先离开原文，用自己的话说明一个观点，再检查遗漏和误解。\n\n## 一个具体动作\n\n- 合上书\n- 写三句话\n- 回到原文核对\n\n## 接回阅读笔记\n\n回到 [[示例阅读入口|阅读后的三件小事]]，把这个动作放进真实阅读中。' },
      { id: 'demo-spacing-note', title: '示例间隔复习', text: '> 示例笔记，不是固定的学习处方。\n\n## 过一段时间再看\n\n试着先回忆，再打开旧笔记。记录哪些仍然清楚，哪些需要重新理解。\n\n## 和主动回忆一起用\n\n连接 [[示例主动回忆|主动回忆]]，让回顾从一个问题开始。\n- 哪个概念已经能解释？\n- 哪个例子还需要核对？' },
    ];
    const existingRoot = data.notes.find(n => n.id === 'demo-reading-note');
    const rootTitle = existingRoot?.title || examples[0].title;
    examples[1].text = examples[1].text.replace('[[示例阅读入口|阅读后的三件小事]]', `[[${rootTitle}|阅读后的三件小事]]`);
    for (const example of examples) {
      if (!data.notes.some(n => n.id === example.id)) data.notes.push({ ...example, title: uniqueTitle(example.title), sources: [materialId], sourceWorkId: example.id === 'demo-reading-note' ? workId : undefined, sample: true, date: stamp() });
    }
    if (!persist()) return;
    openNote('demo-reading-note', true);
    setNoteView(routeViews[destination] || 'editor', false);
    window.dispatchEvent(new Event('sourcecast:works-changed'));
    location.hash = ['home', 'notes', 'mindmap', 'connections'].includes(destination) ? destination : 'notes';
    toast('已打开示例。内容可编辑，没有调用模型。');
  }

  $('#saveNote').addEventListener('click', () => saveNote());
  $('#newNote').addEventListener('click', () => newNote());
  $('#exportNote').addEventListener('click', () => { const n = saveNote(); if (n) download(n.title + '.md', '# ' + n.title + '\n\n' + n.text); });
  $('#draftToNote').addEventListener('click', () => { const w = saveWork(true); if (w) createNoteFromWork(w, true); });
  $('#noteReadMode').addEventListener('click', () => setPreview(true));
  $('#noteEditMode').addEventListener('click', () => setPreview(false));
  ['#noteTitle', '#noteText'].forEach(id => $(id).addEventListener('input', () => {
    dirty = true; updateMeta(); renderContext();
    $('#noteStatus').textContent = '正在编辑…';
    clearTimeout(saveTimer); saveTimer = setTimeout(() => saveNote(true), 700);
  }));
  $$('[data-note-view]').forEach((b, i, buttons) => {
    b.addEventListener('click', () => setNoteView(b.dataset.noteView));
    b.addEventListener('keydown', e => { const direction = { ArrowRight: 1, ArrowLeft: -1 }[e.key]; if (direction) { e.preventDefault(); const next = buttons[(i + direction + buttons.length) % buttons.length]; next.click(); next.focus(); } });
  });
  document.addEventListener('click', e => {
    const button = e.target.closest('[data-wiki-title]');
    if (button) { const title = button.dataset.wikiTitle; const note = data.notes.find(n => n.title === title); if (note) { if (openNote(note.id)) setNoteView('editor'); } else newNote(title); }
  });
  document.addEventListener('input', e => { if (e.target.matches('[data-note-search]')) { noteFilter = e.target.value; renderNoteList(); } });
  window.addEventListener('sourcecast:note-search', e => { noteFilter = e.detail; renderNoteList(); });
  window.addEventListener('sourcecast:navigate', e => { if (dirty) saveNote(true); if (routeViews[e.detail.view]) setNoteView(routeViews[e.detail.view], false); });
  window.addEventListener('sourcecast:demo', e => { loadDemo(e.detail || 'notes').catch(() => toast('示例未保存，请检查浏览器本机存储。')); });
  document.addEventListener('keydown', e => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's' && !$('#notes').hidden) { e.preventDefault(); saveNote(); } });
  window.addEventListener('pagehide', () => { if (dirty) saveNote(true); });
  const mapCanvas = $('#mindMap');
  mapCanvas.tabIndex = 0;
  mapCanvas.setAttribute('role', 'region');
  mapCanvas.setAttribute('aria-label', '思维导图画布。拖动空白处平移，按加减键缩放，0 适应画布。点击节点回到笔记原文。');
  let mapDrag = null;
  mapCanvas.addEventListener('pointerdown', event => {
    if (event.button !== 0 || event.target.closest('[data-map-offset], [data-map-collapse], button')) return;
    mapDrag = { id: event.pointerId, x: event.clientX, y: event.clientY, left: mapCanvas.scrollLeft, top: mapCanvas.scrollTop };
    mapCanvas.setPointerCapture(event.pointerId); mapCanvas.classList.add('is-dragging');
  });
  mapCanvas.addEventListener('pointermove', event => {
    if (mapDrag?.id !== event.pointerId) return;
    mapCanvas.scrollLeft = mapDrag.left - event.clientX + mapDrag.x;
    mapCanvas.scrollTop = mapDrag.top - event.clientY + mapDrag.y;
  });
  const endMapDrag = event => { if (mapDrag?.id === event.pointerId) { mapDrag = null; mapCanvas.classList.remove('is-dragging'); if (mapCanvas.hasPointerCapture(event.pointerId)) mapCanvas.releasePointerCapture(event.pointerId); } };
  mapCanvas.addEventListener('pointerup', endMapDrag); mapCanvas.addEventListener('pointercancel', endMapDrag);
  mapCanvas.addEventListener('keydown', event => {
    if (event.target !== mapCanvas || !['+', '=', '-', '0'].includes(event.key)) return;
    event.preventDefault();
    if (event.key === '0') fitMindMap();
    else { zoom = Math.max(.25, Math.min(2, zoom + (event.key === '-' ? -.15 : .15))); applyZoom(); }
  });
  $('#noteMapView .map-foot > span:last-child').textContent = '拖动空白平移 · 点击节点回原文 · 圆点折叠分支';
  $('#mapZoomIn').addEventListener('click', () => { zoom = Math.min(2, zoom + .15); applyZoom(); });
  $('#mapZoomOut').addEventListener('click', () => { zoom = Math.max(.25, zoom - .15); applyZoom(); });
  $('#mapFit').addEventListener('click', () => fitMindMap());
  $('#exportMindMap').addEventListener('click', () => {
    const svg = $('#mindMap svg')?.cloneNode(true); if (!svg) return;
    const computed = getComputedStyle(document.documentElement);
    const color = name => computed.getPropertyValue('--' + name).trim();
    const style = document.createElementNS('http://www.w3.org/2000/svg', 'style');
    const neon = document.documentElement.dataset.sourcecast === 'neon';
    style.textContent = `.map-edge{fill:none;stroke:${color('rule-strong')};stroke-width:1.4}.map-node rect{fill:${color('surface')};stroke:${color('rule')};stroke-width:1}.map-node text{fill:${color('ink-2')};font:13px sans-serif}.map-node.is-root rect{fill:${color(neon?'paper-3':'accent')};stroke:${color('accent')}}.map-node.is-root text{fill:${color(neon?'ink':'accent-ink')};font:15px ${neon?'sans-serif':'serif'}}.map-toggle circle{fill:${color('surface')};stroke:${color('accent')}}.map-toggle text{fill:${color('accent')};font:13px sans-serif;text-anchor:middle}`;
    svg.prepend(style); svg.removeAttribute('style'); svg.setAttribute('width', mapSize.width); svg.setAttribute('height', mapSize.height);
    svg.querySelectorAll('[tabindex]').forEach(n => n.removeAttribute('tabindex'));
    download((current()?.title || '笔记') + '-思维导图.svg', new XMLSerializer().serializeToString(svg), 'image/svg+xml;charset=utf-8');
  });

  const initial = data.notes.find(n => n.id === data.activeNote) || data.notes[0];
  if (initial) openNote(initial.id, true);
  if (data.noteDraft) { activeNote = data.noteDraft.id; $('#noteTitle').value = data.noteDraft.title; $('#noteText').value = data.noteDraft.text; dirty = true; $('#noteStatus').textContent = '已恢复未保存的草稿，请检查标题后保存。'; }
  setNoteView(routeViews[location.hash.slice(1)] || 'editor', false);
  renderNoteList(); renderContext(); updateMeta();
  return { renderNoteList, openNote, renderMindMap, renderGraph, createNoteFromWork, personalPack, setNoteView, loadDemo };
};

/* Sourcecast · Listening Room: navigation, continuous playback and a real writing flow. */
(() => {
  'use strict';
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => [...document.querySelectorAll(s)];
  const episodes = window.LIB.episodes;
  const auditions = window.AUDITIONS?.items || [];
  // 已完成的节目优先占据「现在试听」；音色样本留给声音工作室做描述参考。
  const finished = window.FINISHED_AUDIO?.items || [];
  const shelf = finished.length ? finished : auditions;
  const styles = window.STYLES;
  const STORAGE = 'sourcecast.studio.draft.v1';
  const esc = s => String(s || '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let messageTimer;
  const toast = text => { $('#toast').textContent = text; $('#toast').classList.add('is-on'); clearTimeout(messageTimer); messageTimer = setTimeout(() => $('#toast').classList.remove('is-on'), 3500); };
  const download = (name, text, type = 'text/plain;charset=utf-8') => { const url = URL.createObjectURL(new Blob([text], {type})); const a = document.createElement('a'); a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 3000); };
  const names = {welcome:'先说你要什么',home:'我的工作室',studio:'开始创作',roles:'角色与声音',notes:'我的笔记',mindmap:'思维导图',connections:'知识连接',settings:'服务设置',episodes:'全部节目',judgments:'判断与收藏',memory:'记忆网络',integrate:'带走与接入',pipeline:'播客产线',about:'关于页声'};
  function scrollWorkspaceTop(){
    if(!document.body.classList.contains('is-welcome'))document.getElementById('top').scrollTo({top:0,behavior:'instant'});
    window.scrollTo({top:0,behavior:'instant'});
  }
  function route() {
    const id = location.hash.slice(1) || 'welcome';
    const anchorId = id.startsWith('welcome-') ? id : null;
    const active = names[id] ? id : 'welcome';
    const section = ['mindmap','connections'].includes(active) ? 'notes' : active;
    Object.keys(names).forEach(name => { const node = document.getElementById(name); if (node) node.hidden = name !== section; });
    document.body.classList.toggle('is-welcome', active === 'welcome');
    document.title = `${names[active]} · 页声 Sourcecast`;
    $('#archiveStats').hidden = active !== 'judgments';
    $$('.nav a').forEach(a => { a.classList.toggle('is-active', a.dataset.nav === active); if (a.dataset.nav === active) a.setAttribute('aria-current','page'); else a.removeAttribute('aria-current'); });
    $('#currentView').textContent = names[active];
    requestAnimationFrame(() => anchorId ? document.getElementById(anchorId)?.scrollIntoView({block:'start'}) : scrollWorkspaceTop());
    window.dispatchEvent(new CustomEvent('sourcecast:navigate', {detail:{view:active}}));
    if (active === 'memory') requestAnimationFrame(() => window.dispatchEvent(new Event('resize')));
  }
  window.addEventListener('hashchange', route);
  $('#q').addEventListener('input', () => { if ($('#q').value.trim() && location.hash !== '#judgments') location.hash = 'judgments'; });
  route();
  $('#toggleThemeMobile').addEventListener('click',()=>$('#toggleTheme').click());
  let featured = shelf[0];
  const clock = s => { const n = Math.max(0, Math.round(Number(s) || 0)); return `${Math.floor(n/60)}:${String(n%60).padStart(2,'0')}`; };
  const shortClock = s => { const n = Math.max(0, Math.round(Number(s) || 0)); return n >= 60 ? `${Math.floor(n/60)}′${String(n%60).padStart(2,'0')}″` : `${n}″`; };
  const words = () => finished.length ? { play: '播放节目', pause: '暂停播放' } : { play: '播放试听', pause: '暂停试听' };
  function renderFeatured() {
    if (!featured) { $('#featurePlay').disabled = true; $('#featureTitle').textContent = '等待你的第一段声音'; return; }
    $('#featureSeries').textContent = featured.label || featured.name;
    $('#featureTitle').textContent = featured.title;
    $('#featureDesc').textContent = featured.desc || (featured.kind ? (featured.subtitle || '') : '一段关于阅读与好奇的原创试听，由同一段文字生成。');
    $('#featureMeta').textContent = featured.meta || `MiMo · AI 合成 · ${Math.round(featured.seconds)} 秒`;
    const cap = $('#listenCaptionNo');
    if (cap) cap.textContent = featured.catalog || 'NO. 039';
    const shelfLabel = $('#shelfLabel');
    if (shelfLabel) shelfLabel.textContent = finished.length ? '节目' : '声音';
    const playingNow = !$('#studioAudio').paused && !$('#studioAudio').ended;
    if (!playingNow) $('#featurePlay').textContent = words().play;
    const adopt = $('#useAuditionDirection');
    if (featured.direction) { adopt.hidden = false; adopt.textContent = `采用${featured.name}的描述，读我的文字 ↗`; }
    else adopt.hidden = true;
    $('#featureDetail').textContent = featured.kind ? '本期简介' : '逐字稿';
  }
  renderFeatured();
  $('#featureDetail').addEventListener('click', () => {
    if (!featured) return;
    $('#auditionTranscriptKind').textContent = featured.label || 'MiMo · 原创试听文本';
    $('#auditionTranscriptTitle').textContent = featured.title || '把一本书，听成自己的问题';
    $('#auditionTranscriptText').textContent = featured.summary || featured.text || '';
    $('#auditionTranscript').showModal();
  });
  $('#closeAuditionTranscript').addEventListener('click',()=>$('#auditionTranscript').close());
  $('#useAuditionDirection').addEventListener('click',()=>{
    if(!featured?.direction) return;
    $('#voiceMode').value='design';
    $('#voiceDescription').value=featured.direction;
    $('#voiceMode').dispatchEvent(new Event('change'));
    $('#voiceDescription').focus({preventScroll:true});
    $('#auditionStatus').textContent = `已采用${featured.name}的描述，可在下面继续修改。`;
  });
  $('#episodeShelf').innerHTML = shelf.map((a,i) => `<button class="voice-option" data-audition="${esc(a.id)}" aria-label="播放 ${esc(a.label || a.name)}" aria-pressed="${i===0}"><span>${esc(a.name)}</span><small>${shortClock(a.seconds)}</small></button>`).join('');
  const preview = $('.sound-preview');
  if (preview) preview.hidden = !auditions.length;
  $('#voiceAuditions').innerHTML = auditions.map(a=>`<button data-audition="${esc(a.id)}" aria-pressed="false"><span class="audition-play" aria-hidden="true">▶</span><span><b>${esc(a.name)}</b><small>${esc(a.subtitle)}</small></span><span>${shortClock(a.seconds)}</span></button>`).join('');
  $('#homeQuote').textContent = '从一页材料，到一段对话，再到一条自己的判断。';

  function renderLatestIssue() {
    const ep = episodes.slice().sort((a, b) => (b.no || 0) - (a.no || 0))[0];
    if (!ep) return;
    const judgments = (ep.judgments || []).length;
    $('#mastheadIssue').textContent = `第 ${ep.no} 期 · ${ep.date || ''}`;
    $('#latestIssue').innerHTML = `<a class="issue-cover" href="#episodes" style="--cover:${esc(ep.color || 'var(--accent)')}"><b>${String(ep.no).padStart(2, '0')}</b><small>${esc(ep.series || 'SOURCECAST')}</small></a><div class="issue-copy"><div class="issue-meta"><span>${esc(ep.date || '')}</span><span>${judgments} 条判断</span></div><h3>${esc(ep.title || ep.slug)}</h3><p>${esc(ep.one_liner || ep.subtitle || (ep.repos || []).join(' · ') || '—')}</p><div class="issue-actions"><a class="quiet-link" href="#episodes">打开这一期 <span aria-hidden="true">→</span></a><span class="micro">${ep.chars ? ep.chars.toLocaleString() + ' 字' : ''}</span></div></div>`;
  }
  renderLatestIssue();

  const setupVoice = $('#setupVoice');
  if (setupVoice) setupVoice.addEventListener('click', () => $('#tabVoice').click());

  // A single audio element survives view changes and drawer closure.
  const audio = $('#studioAudio');
  let track = null;
  let context, analyser, waveformFrame;
  const canvas = $('#soundWave'), pen = canvas.getContext('2d');
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const dock = $('#listeningDock');
  const playerIcon = name => `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><use href="#i-${name}"/></svg>`;
  const dockState = document.createElement('span');
  dockState.className = 'dock-state';
  dockState.setAttribute('role', 'status');
  dockState.textContent = '准备播放';
  $('#dockTitle').before(dockState);
  $('#dockPlay').innerHTML = playerIcon('play');
  $('#skipBack').innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 8a8 8 0 1 1-1 8M5 3v5h5"/></svg><small>10</small>';
  $('#skipForward').innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M19 8a8 8 0 1 0 1 8m-1-13v5h-5"/></svg><small>10</small>';
  $('#dockClose').innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m7 7 10 10M17 7 7 17"/></svg>';
  $('#dockClose').title = '收起播放器并暂停';
  $('#dockSpeed').title = '切换播放速度';
  let motionPaused = reducedMotion.matches;
  try { motionPaused = reducedMotion.matches || localStorage.getItem('sourcecast.motionPaused') === 'true'; } catch {}
  function syncMotion() {
    document.body.classList.toggle('motion-paused', motionPaused);
    // 访客不需要开发者式的动效开关；只跟随系统的「减弱动态」设置。
    $('#recordStatus').textContent = !audio.paused && !audio.ended ? '正在播放' : audio.ended ? '播放结束' : track ? '已暂停' : '点击播放';
  }
  syncMotion();
  reducedMotion.addEventListener('change',()=>{motionPaused=reducedMotion.matches;syncMotion();});
  function drawWave() {
    pen.clearRect(0,0,canvas.width,canvas.height);
    const data = new Uint8Array(128);
    if (analyser && !audio.paused) analyser.getByteFrequencyData(data);
    pen.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim();
    for (let i=0;i<60;i++) {
      const height = Math.max(3, data[Math.floor(i*1.5)] / 255 * 62);
      pen.fillRect(i*12+3,(70-height)/2,4,height);
    }
    if (!audio.paused && !reducedMotion.matches && !$('#panelVoice').hidden && location.hash==='#studio' && document.visibilityState==='visible') waveformFrame=requestAnimationFrame(drawWave);
  }
  function connectMeter() {
    try {
      if (!context) { context=new AudioContext(); analyser=context.createAnalyser(); analyser.fftSize=256; context.createMediaElementSource(audio).connect(analyser); analyser.connect(context.destination); }
      context.resume().catch(()=>{});
    } catch { /* Native playback remains usable if Web Audio is unavailable. */ }
  }
  const time = s => `${Math.floor((Number(s)||0)/60)}:${String(Math.floor((Number(s)||0)%60)).padStart(2,'0')}`;
  $('#auditionDur').textContent = time(featured?.seconds || 0);
  $('#auditionSeek').setAttribute('aria-valuetext', `0:00 / ${time(featured?.seconds || 0)}`);
  async function startAudio() { try { connectMeter(); await audio.play(); } catch { toast('播放没有开始，请点播放重试。'); } }
  // 线上网关不透传 Range（Range 请求仍回 200 全量），<audio> 无法随机访问，一拖就回 0。
  // 先把整段下成 Blob 再交给播放器：播放与拖动都在本地缓存里完成，同一 src 只下载一次。
  const audioBlobs = new Map(), pendingLoads = new Map();
  function localSrc(sample) {
    if (audioBlobs.has(sample.src)) return Promise.resolve(audioBlobs.get(sample.src));
    if (pendingLoads.has(sample.src)) return pendingLoads.get(sample.src);
    const job = fetch(sample.src, { cache: 'force-cache' })
      .then(async res => {
        if (!res.ok) throw new Error('音频下载失败');
        const url = URL.createObjectURL(await res.blob());
        audioBlobs.set(sample.src, url);
        pendingLoads.delete(sample.src);
        return url;
      })
      .catch(err => { pendingLoads.delete(sample.src); throw err; });
    pendingLoads.set(sample.src, job);
    return job;
  }
  async function playAudition(sample) {
    if (!sample) return;
    if (track === sample.id && !audio.paused) { audio.pause(); return; }
    const switching = track !== sample.id;
    if (switching) {
      track = sample.id; featured = sample; renderFeatured();
      $('#dockTitle').textContent = sample.title;
      $('#dockTitle').title = `${sample.name} · ${sample.title}`;
      $('#dockCaption').textContent = sample.kind ? `${sample.label || sample.name} · AI 合成` : `${sample.name} · MiMo · AI 合成`;
      $('#auditionNow').textContent = '0:00';
      $('#auditionDur').textContent = time(sample.seconds);
      $('#dockDuration').textContent = time(sample.seconds);
      $('#auditionSeek').value = '0';
      $('#auditionStatus').textContent = '正在准备音频…';
      dockState.textContent = '正在准备音频';
      syncProgress();
    }
    $('#listeningDock').hidden = false; document.body.classList.add('has-player');
    try {
      const src = await localSrc(sample);
      if (track !== sample.id) return;
      if (audio.getAttribute('src') !== src) audio.src = src;
      await startAudio();
    } catch {
      $('#auditionStatus').textContent = '音频没有下载成功';
      dockState.textContent = '音频下载失败';
      toast('音频没有下载成功，请检查网络后重试。');
    }
  }
  const playable = id => [...finished, ...auditions].find(a => a.id === id);
  $$('[data-audition]').forEach(b=>b.addEventListener('click',()=>playAudition(playable(b.dataset.audition))));
  ['#homeVoiceStudio','#tryOwnVoice'].forEach(id=>{const el=$(id); if(el) el.addEventListener('click',()=>$('#tabVoice').click());});
  function startFromMode(mode) {
    location.hash='studio';$('#tabCompose').click();
    document.querySelector(`#panelCompose [data-source-mode="${mode}"]`)?.click();
    requestAnimationFrame(()=>$('#draftTopic').focus({preventScroll:true}));
  }
  $$('[data-start-mode]').forEach(button=>button.addEventListener('click',()=>startFromMode(button.dataset.startMode)));
  window.addEventListener('sourcecast:start',event=>startFromMode(event.detail));
  $('#featurePlay').addEventListener('click', () => playAudition(featured));
  $('#dockPlay').addEventListener('click', () => { if (audio.paused) startAudio(); else audio.pause(); });
  function syncPlayback() {
    const playing=!audio.paused && !audio.ended;
    document.body.classList.toggle('is-playing',playing);
    $('#dockPlay').innerHTML=playerIcon(playing?'pause':'play'); $('#dockPlay').setAttribute('aria-label',playing?'暂停':'播放'); $('#dockPlay').setAttribute('aria-pressed',String(playing)); $('#dockPlay').title=playing?'暂停播放':'继续播放';
    dock.dataset.state=playing?'playing':audio.ended?'ended':'paused';
    dockState.textContent=playing?'正在播放':audio.ended?'播放结束':'已暂停';
    const featureButton=$('#featurePlay'), word=words(); featureButton.textContent=playing?word.pause:word.play; featureButton.setAttribute('aria-label',playing?word.pause:word.play); featureButton.setAttribute('aria-pressed',String(playing));
    $$('[data-audition]').forEach(b=>{const selected=b.classList.contains('voice-option')?b.dataset.audition===featured?.id:playing&&b.dataset.audition===track;b.setAttribute('aria-pressed',String(selected));const icon=b.querySelector('.audition-play');if(icon)icon.textContent=playing&&b.dataset.audition===track?'Ⅱ':'▶';});
    $('#auditionStatus').textContent=track?`${featured.name} · ${playing?'正在播放':audio.ended?'播放结束':'已暂停'} · AI 合成`:'尚未播放 · AI 合成试听';
    cancelAnimationFrame(waveformFrame);drawWave();syncMotion();
  }
  audio.addEventListener('play',syncPlayback); audio.addEventListener('pause',syncPlayback); audio.addEventListener('ended',syncPlayback);
  drawWave();
  const refreshMeter=()=>{cancelAnimationFrame(waveformFrame);drawWave();};
  $$('.tab').forEach(tab=>tab.addEventListener('click',()=>requestAnimationFrame(refreshMeter)));
  window.addEventListener('hashchange',()=>requestAnimationFrame(refreshMeter));
  document.addEventListener('visibilitychange',refreshMeter);
  // 拖动期间不让 timeupdate 抢写滑块，否则手指还没松开就被弹回旧位置。
  let scrubbing = false;
  ['#auditionSeek','#dockSeek'].forEach(sel => {
    const el = $(sel);
    if (!el) return;
    el.addEventListener('pointerdown', () => { scrubbing = true; });
    ['pointerup','pointercancel','blur'].forEach(ev => el.addEventListener(ev, () => { scrubbing = false; }));
    el.addEventListener('keydown', () => { scrubbing = true; });
    el.addEventListener('keyup', () => { scrubbing = false; });
  });
  function syncProgress() {
    const now = time(audio.currentTime);
    const total = Number.isFinite(audio.duration) ? time(audio.duration) : ($('#auditionDur').textContent || '0:00');
    $('#dockTime').textContent = now;
    const dockRatio = Number.isFinite(audio.duration) && audio.duration > 0 ? audio.currentTime / audio.duration : 0;
    const seek = $('#auditionSeek');
    const ratio = audio.duration ? audio.currentTime / audio.duration : 0;
    if (!scrubbing) {
      $('#dockSeek').value = dockRatio * 100;
      $('#dockSeek').style.setProperty('--dock-seek', `${(dockRatio * 100).toFixed(2)}%`);
      $('#dockSeek').setAttribute('aria-valuetext', `${now} / ${total}`);
      seek.value = String(Math.round(ratio * 1000));
      seek.style.setProperty('--seek', `${(ratio * 100).toFixed(2)}%`);
      seek.setAttribute('aria-valuetext', `${now} / ${total}`);
    }
    $('#auditionNow').textContent = now;
    $('#auditionDur').textContent = total;
  }
  audio.addEventListener('timeupdate', syncProgress);
  audio.addEventListener('loadedmetadata', () => { $('#dockDuration').textContent = time(audio.duration); syncProgress(); });
  audio.addEventListener('error', () => toast('音频暂时无法加载，请稍后重试。'));
  audio.addEventListener('playing', () => $$('audio:not(#studioAudio)').forEach(a => a.pause()));
  document.addEventListener('play', e => { if (e.target.tagName === 'AUDIO' && e.target !== audio) audio.pause(); }, true);
  $('#dockSeek').addEventListener('input', e => { if (Number.isFinite(audio.duration)) audio.currentTime = Number(e.target.value)/100*audio.duration; });
  $('#auditionSeek').addEventListener('input', e => { if (Number.isFinite(audio.duration)) audio.currentTime = Number(e.target.value)/1000*audio.duration; });
  $('#skipBack').addEventListener('click', () => audio.currentTime = Math.max(0,audio.currentTime-10));
  $('#skipForward').addEventListener('click', () => { if (Number.isFinite(audio.duration)) audio.currentTime = Math.min(audio.duration,audio.currentTime+10); });
  $('#dockSpeed').addEventListener('click', () => { const speeds = [1,1.25,1.5,2]; audio.playbackRate = speeds[(speeds.indexOf(audio.playbackRate)+1)%speeds.length]; $('#dockSpeed').textContent = `${audio.playbackRate}×`; });
  $('#dockClose').addEventListener('click', () => { audio.pause(); $('#listeningDock').hidden = true; document.body.classList.remove('has-player'); });
  window.Sourcecast.playEpisode = slug => {
    const hit = finished.find(x => x.slug === slug);
    if (hit) { playAudition(hit); return true; }
    toast('这一期只有文字，音频还没有上传。');
    return false;
  };
  window.Sourcecast.playItem = id => { const hit = playable(id); if (hit) playAudition(hit); };
  window.Sourcecast.finishedAudio = finished;
  window.Sourcecast.playAudition = id => playAudition(playable(id));

  // Local drafts and style selection only. Generation goes to the reader's own model service
  // (Settings → 接自己的模型服务), or by task-sheet handoff on their own computer. No cloud SDK.
  $('#draftStyle').innerHTML = styles.map(s => `<option value="${s.id}">${esc(s.name)}${s.id === 'duo' ? ' · 播客对话' : ''}</option>`).join('');
  let saved = {}; try { saved = JSON.parse(localStorage.getItem(STORAGE) || '{}'); } catch {}
  $('#draftTopic').value = saved.topic || ''; $('#draftSources').value = saved.sources || ''; $('#draftOutput').value = saved.text || '';
  if (styles.some(s => s.id === saved.style)) $('#draftStyle').value = saved.style;
  let customStyle = null;
  try { const prompt = JSON.parse(localStorage.getItem('sourcecast.customStyle.v1') || 'null'); if (prompt) { customStyle={id:'custom',name:'我的博主风格',prompt}; $('#draftStyle').add(new Option('我的博主风格 · 已保存','custom')); if(saved.style==='custom') $('#draftStyle').value='custom'; } } catch {}
  const selectedStyle = () => $('#draftStyle').value === 'custom' && customStyle ? customStyle : styles.find(s => s.id === $('#draftStyle').value) || styles[0];
  function saveDraft() {
    const text = $('#draftOutput').value;
    $('#draftCount').textContent = `${[...text].length} 字`;
    try { localStorage.setItem(STORAGE, JSON.stringify({topic:$('#draftTopic').value,sources:$('#draftSources').value,style:$('#draftStyle').value,text})); $('#draftSaveStatus').textContent = text ? '已保存在这台设备' : '尚未写入内容'; }
    catch { $('#draftSaveStatus').textContent = '存储空间不足，请导出稿子'; }
  }
  ['#draftTopic','#draftSources','#draftOutput','#draftStyle'].forEach(id => $(id).addEventListener('input', saveDraft));
  saveDraft();
  $('#inspectStyle').addEventListener('click', () => { const s = selectedStyle(); const b = document.querySelector(`[data-style="${s.id}"]`); if (b) b.click(); $('#tabStyle').click(); });
  $('#useSelectedStyle').addEventListener('click',()=>{$('#tabCompose').click();$('#draftTopic').focus({preventScroll:true});scrollWorkspaceTop();});
  window.addEventListener('sourcecast:style', e => { $('#draftStyle').value = e.detail; saveDraft(); });
  window.addEventListener('sourcecast:fingerprint', e => { customStyle = {id:'custom', name:'我的博主风格', prompt:e.detail}; if (!$('#draftStyle option[value="custom"]')) $('#draftStyle').add(new Option('我的博主风格 · 本次提取','custom')); $('#draftStyle').value = 'custom'; $('#draftStatus').textContent = '已采用刚提取的表达特征，回到「写下想法」即可生成。'; saveDraft(); });
  function brief() { return `# 播客创作任务\n\n主题：${$('#draftTopic').value.trim() || '请填写主题'}\n\n## 表达方式\n${selectedStyle().prompt}\n\n## 参考素材\n${$('#draftSources').value.trim() || '暂无素材。请先检索可靠原始来源，不编造事实、数字和引语。'}\n\n## 交付\n输出可直接朗读的中文口播稿。用具体例子解释概念；引用素材中的事实，未知处标为待核实；结尾给一条判断标准。不声称自己是风格参考的博主。\n\n本任务未包含用户本地记忆或音色。`;
  }
  async function exportAgentBrief() {
    if (!$('#draftTopic').value.trim()) { $('#draftStatus').textContent='先写一个主题，再准备任务书。'; $('#draftTopic').focus(); return; }
    const instruction=window.PersonalStudio ? await window.PersonalStudio.buildBrief(brief()) : brief();
    download('sourcecast-agent-task.md',instruction+'\n\n## 返回本工作室\n完成后把正文保存为 Markdown（.md）或纯文本（.txt），在页声创作台点击「导入做好的正文」。正文里不要带任务书原文，也不要带任何 Key。\n');
    $('#draftStatus').textContent='任务书已下载。在你自己的电脑上做好后，点「导入做好的正文」继续。';
    toast('任务书已准备好，做好后把正文导回来就行。');
  }
  $('#exportBrief').addEventListener('click',()=>exportAgentBrief().catch(error=>{ $('#draftStatus').textContent=error.message; }));
  async function importAgentResult(event) {
    const file=event.target.files[0];if(!file)return;
    try {
      if(file.size>2*1024*1024)throw new Error('正文请控制在 2 MB 以内。');
      if(!/\.(md|txt)$/i.test(file.name))throw new Error('请选择 Markdown 或 TXT 正文。');
      const text=await file.text();if(!text.trim())throw new Error('文件里没有读到正文。');
      // Never replace an existing draft silently; keep both pieces for review.
      const prior=$('#draftOutput').value.trim();
      $('#draftOutput').value=prior ? prior+'\n\n---\n\n'+text : text;
      if(!$('#draftTopic').value.trim())$('#draftTopic').value=file.name.replace(/\.(md|txt)$/i,'').slice(0,180);
      saveDraft();location.hash='studio';$('#tabCompose').click();
      $('#draftStatus').textContent=prior?'正文已追加在原稿后面，核对一下再改。':'正文已导入，保存在这台设备上，可以继续编辑、记笔记或试听。';
    }catch(error){toast(error.message);$('#modelConnection').textContent=error.message;}
    finally{event.target.value='';}
  }
  ['agentResultFile','agentDraftResult'].forEach(id=>document.getElementById(id).addEventListener('change',importAgentResult));
  $('#downloadDraft').addEventListener('click', () => { if (!$('#draftOutput').value.trim()) return toast('先写几句，或生成初稿后再导出。'); download('sourcecast-draft.md',`# ${$('#draftTopic').value || '播客初稿'}\n\n${$('#draftOutput').value}`); });
  $('#draftToVoice').addEventListener('click', () => { const text = $('#draftOutput').value.trim(); if (!text) return toast('先完成一段稿子，再去试听。'); $('#ttsText').value = text.slice(0,400); $('#ttsText').dispatchEvent(new Event('input')); $('#tabVoice').click(); });
  let controller = null;
  $('#writeDraft').addEventListener('click', async () => {
    if (controller) { controller.abort(); return; }
    if(window.PersonalStudio?.modelRoute()==='agent'){await exportAgentBrief().catch(error=>{ $('#draftStatus').textContent=error.message; });return;}
    if (!$('#draftTopic').value.trim()) { $('#draftStatus').textContent = '先给这一期一个主题。'; $('#draftTopic').focus(); return; }
    if ($('#draftOutput').value.trim()) { $('#draftStatus').textContent = '编辑区已有稿子。请先导出保存，清空编辑区后再生成新稿。'; return; }
    controller = new AbortController(); const signal = controller.signal; const timer = setTimeout(()=>controller?.abort(),120000);
    $('#writeDraft').textContent = '停止生成'; $('#draftStatus').textContent = '正在连接模型…'; $('#draftOutput').setAttribute('aria-busy','true');
    try {
      const {cloud,id} = await window.PersonalStudio.getModel();
      if (signal.aborted) throw new DOMException('Aborted','AbortError');
      $('#draftStatus').textContent = `正在写稿 · ${selectedStyle().name}`;
      const stream = await cloud.llm.chat.completions.create({model:id,stream:true,signal,temperature:0.75,messages:[{role:'system',content:window.PersonalStudio.editorSystem()},{role:'user',content:await window.PersonalStudio.buildBrief(brief())}]});
      let text = '';
      for await (const chunk of stream) { if (signal.aborted) break; const delta = chunk.choices?.[0]?.delta?.content || ''; text += delta; $('#draftOutput').value = text; saveDraft(); }
      if (!text.trim() && !signal.aborted) throw new Error('模型没有返回正文');
      $('#draftStatus').textContent = signal.aborted ? '已停止，已生成的文字已保留。' : '初稿已保存。读一遍，补足待核实的地方，再去试听。';
    } catch (e) {
      $('#draftStatus').textContent = signal.aborted ? '已停止，已收到的文字已保留。' : `这次没写成：${e.message}。可以再试一次，或者改成在自己的电脑上做。`;
    } finally { clearTimeout(timer); controller = null; $('#writeDraft').textContent = '生成我的内容 ↗'; window.PersonalStudio?.syncModelRoute(); $('#draftOutput').removeAttribute('aria-busy'); saveDraft(); }
  });
  // Roving keyboard controls for the studio steps.
  $$('.tabs .tab').forEach((tab,i,all) => {
    tab.tabIndex = tab.classList.contains('is-on') ? 0 : -1;
    tab.addEventListener('click', () => all.forEach(b => b.tabIndex = b === tab ? 0 : -1));
    tab.addEventListener('keydown', e => { let next; if (e.key === 'ArrowRight') next = (i+1)%all.length; if (e.key === 'ArrowLeft') next = (i+all.length-1)%all.length; if (e.key === 'Home') next = 0; if (e.key === 'End') next = all.length-1; if (next !== undefined) { e.preventDefault(); all[next].click(); all[next].focus(); } });
  });
  // The public browser API reads explicit local state. It does not expose voices or credentials.
  window.Sourcecast.getDraft = () => ({topic:$('#draftTopic').value,text:$('#draftOutput').value,style:selectedStyle().id});
  window.Sourcecast.getStyle = () => ({...selectedStyle()});
  window.Sourcecast.composeBrief=brief;
  function memoryList() {
    const query = $('#memorySearch').value.trim().toLowerCase();
    const pack=window.Sourcecast.exportMemory();
    const matches=pack.nodes.filter(n => ['episode','local_topic'].includes(n.type) && JSON.stringify(n).toLowerCase().includes(query)).slice(0,10);
    $('#memoryResultCount').textContent = `${matches.length} 个关联条目 · 关系按来源与关键词建立`;
    $('#memoryResults').innerHTML = matches.length ? matches.map(n => `<div class="memory-result"><span>${n.type==='episode'?'EP '+n.id.slice(2):'本地主题'}</span>${n.slug?`<button data-memory-ep="${esc(n.slug)}">${esc(n.title)}</button>`:`<b>${esc(n.name)}</b>`}<small>${esc(n.series || '仅在这台设备保存')}</small></div>`).join('') : '<p class="micro">没有找到相关条目，换个词或导入自己的笔记。</p>';
    $$('[data-memory-ep]').forEach(b=>b.addEventListener('click',()=>window.Sourcecast.openEpisode(b.dataset.memoryEp)));
  }
  $('#memorySearch').addEventListener('input',memoryList);window.addEventListener('sourcecast:memory',memoryList);memoryList();
  // On supported browsers, agents can discover read-only tools directly.
  if(navigator.modelContext?.registerTool) {
    try { navigator.modelContext.registerTool({name:'sourcecast_search',description:'Search sourced podcast judgments in this local Sourcecast library.',inputSchema:{type:'object',properties:{query:{type:'string'}},required:['query']},execute:async ({query})=>({content:[{type:'text',text:JSON.stringify(window.Sourcecast.search(query))}]})}); } catch {}
  }
})();

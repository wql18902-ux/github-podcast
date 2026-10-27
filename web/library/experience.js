/* Product introduction is a real route; demos are explicitly user-initiated. */
(() => {
  document.querySelector('.skip-link').addEventListener('click', event => {
    event.preventDefault();
    document.getElementById('mainContent').focus();
  });
  const tabs = [...document.querySelectorAll('[data-feature-tab]')];
  const panels = { listen: 'featureListenPanel', note: 'featureNotePanel', map: 'featureMapPanel' };
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => {
      tabs.forEach(other => { const selected = other === tab; other.setAttribute('aria-selected', String(selected)); other.tabIndex = selected ? 0 : -1; document.getElementById(panels[other.dataset.featureTab]).hidden = !selected; });
    });
    tab.addEventListener('keydown', event => {
      const direction = { ArrowDown: 1, ArrowUp: -1, ArrowRight: 1, ArrowLeft: -1 }[event.key];
      if (direction) { event.preventDefault(); const next = tabs[(index + direction + tabs.length) % tabs.length]; next.click(); next.focus(); }
      if (event.key === 'Home' || event.key === 'End') { event.preventDefault(); const next = tabs[event.key === 'Home' ? 0 : tabs.length - 1]; next.click(); next.focus(); }
    });
  });
  document.addEventListener('click', event => {
    const target = event.target.closest('[data-demo-open]');
    if (target) window.dispatchEvent(new CustomEvent('sourcecast:demo', { detail: target.dataset.demoOpen }));
  });
})();

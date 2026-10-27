/* 侧边栏图标栏：收起 / 展开状态机
 *
 * 行为（对应 Aceternity Sidebar 的 open/setOpen 语义）：
 * - 默认收起成图标栏
 * - 鼠标进入栏体 → 展开；离开 → 收起
 * - 点击 #railToggle → 按当前开合状态立即切换；主动收起优先于悬停和焦点
 * - 键盘 Tab 进入栏体 → 展开（focus-within），离开 → 收起
 * - 收起时把每个 label 从 tab 顺序里摘掉，但仍通过 title / aria-label 可读
 * 状态写在 <html> 的 .rail-open（视觉）与 .rail-pinned（是否钉住）上，CSS 只读它。
 */
(function () {
  var html = document.documentElement;
  var rail = document.getElementById('rail');
  var toggle = document.getElementById('railToggle');
  if (!rail || !toggle) return;

  var pinned = false;
  var hovered = false;
  var focused = false;
  // A deliberate close wins over the pointer/focus that is still on the button.
  var manuallyClosed = false;
  var releaseTimer = 0;

  function sync() {
    var open = pinned || (!manuallyClosed && (hovered || focused));
    html.classList.toggle('rail-open', open);
    html.classList.toggle('rail-pinned', pinned);
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', open ? '收起导航' : '展开导航');
    toggle.setAttribute('title', open ? '收起导航' : '展开导航');
    var text = toggle.querySelector('[data-rail-text]');
    if (text) text.textContent = open ? '收起导航' : '展开导航';
  }

  /* 收起态：label 不可聚焦、不进读屏的文字流（链接本身仍有 aria-label/title） */
  function syncLabels() {
    var open = html.classList.contains('rail-open');
    var wide = window.matchMedia('(max-width: 760px)').matches;
    rail.querySelectorAll('.rail-label').forEach(function (el) {
      if (open || wide) {
        el.removeAttribute('aria-hidden');
      } else {
        el.setAttribute('aria-hidden', 'true');
      }
    });
  }

  function releaseSoon() {
    window.clearTimeout(releaseTimer);
    releaseTimer = window.setTimeout(function () {
      if (!pinned && !hovered && !focused) { sync(); syncLabels(); }
    }, 120);
  }

  rail.addEventListener('pointerenter', function (e) {
    if (e.pointerType === 'touch') return;
    hovered = true;
    // An explicit close stays closed when click targeting moves back into the rail.
    // The toggle (or keyboard focus on a navigation item) can open it again.
    sync(); syncLabels();
  });
  rail.addEventListener('pointerleave', function (e) {
    if (e.pointerType === 'touch') return;
    hovered = false;
    releaseSoon();
  });
  rail.addEventListener('focusin', function (e) {
    focused = true;
    if (e.target !== toggle) manuallyClosed = false;
    sync(); syncLabels();
  });
  rail.addEventListener('focusout', function () {
    focused = false;
    releaseSoon();
  });

  toggle.addEventListener('click', function () {
    var wasOpen = html.classList.contains('rail-open');
    pinned = !wasOpen;
    manuallyClosed = wasOpen;
    sync(); syncLabels();
  });

  /* Esc 取消钉住 */
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && html.classList.contains('rail-open')) {
      pinned = false;
      manuallyClosed = true;
      sync(); syncLabels();
      toggle.focus();
    }
  });

  /* 点导航后（移动端或已钉住时）收起，回到浏览状态 */
  rail.addEventListener('click', function (e) {
    var link = e.target.closest && e.target.closest('a[data-nav]');
    if (!link) return;
    if (window.matchMedia('(max-width: 760px)').matches) return;
    if (!pinned) { hovered = false; manuallyClosed = true; sync(); syncLabels(); }
  });

  window.addEventListener('resize', function () { sync(); syncLabels(); });

  sync();
  syncLabels();
})();

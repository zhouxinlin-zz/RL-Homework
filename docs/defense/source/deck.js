(() => {
  const slides = [...document.querySelectorAll('#deck > .slide')];
  const deck = document.getElementById('deck');
  const overview = document.getElementById('overview');
  const nav = document.getElementById('nav');
  const controls = document.querySelector('.nav-buttons');
  let brief = new URLSearchParams(location.search).get('mode') === 'brief';
  const fullRoute = slides.map((_, index) => index);
  const briefRoute = fullRoute.filter(index => slides[index].dataset.brief === 'true');
  let route = brief ? briefRoute : fullRoute;
  const indexButtons = [];
  let current = 0;
  let lastWheel = 0;
  let touchStart = null;
  try { document.body.classList.toggle('low-power', localStorage.getItem('lane-deck-static') !== 'false'); } catch { document.body.classList.add('low-power'); }
  const buttons = slides.map((slide, i) => {
    const b = document.createElement('button');
    b.className = 'dot';
    b.title = (i + 1) + '. ' + slide.dataset.title;
    b.setAttribute('aria-label', b.title);
    b.onclick = () => go(i);
    nav.append(b);
    const index = document.createElement('button');
    index.textContent = String(i + 1).padStart(2, '0') + ' / ' + slide.dataset.title;
    index.onclick = () => { setOverview(false); go(i); };
    overview.querySelector('.index-list').append(index);
    indexButtons.push(index);
    return b;
  });
  function setOverview(open) {
    overview.hidden = !open;
    deck.inert = nav.inert = controls.inert = open;
    (open ? document.getElementById('close-index') : document.getElementById('contents')).focus();
  }
  function setMode(short) {
    brief = short;
    route = brief ? briefRoute : fullRoute;
    buttons.forEach((button, index) => { button.hidden = !route.includes(index); });
    indexButtons.forEach((button, index) => { button.hidden = !route.includes(index); });
    document.getElementById('mode-full').setAttribute('aria-pressed', String(!brief));
    document.getElementById('mode-brief').setAttribute('aria-pressed', String(brief));
    document.querySelector('.mode-description').textContent = brief
      ? '8 页重点内容。按右键依次播放；回答追问时可切回完整版本。'
      : '12 页正文与 2 页备答。前 12 页完成主线，最后两页按提问展开。';
    go(current);
  }
  function go(index) {
    const requested = Number.isFinite(index) ? Math.trunc(index) : 0;
    current = route.filter(value => value <= requested).at(-1) ?? route[0];
    deck.style.transform = 'translateX(-' + (current * 100) + 'vw)';
    slides.forEach((s, i) => s.setAttribute('aria-hidden', String(i !== current)));
    buttons.forEach((b, i) => { b.classList.toggle('active', i === current); b.setAttribute('aria-current', i === current ? 'page' : 'false'); });
    const active = slides[current];
    document.body.classList.toggle('dark-bg', active.classList.contains('dark') || active.classList.contains('accent'));
    document.body.classList.toggle('split-bg', active.classList.contains('split'));
    document.getElementById('prev').disabled = current === route[0];
    document.getElementById('next').disabled = current === route.at(-1);
    document.getElementById('hint').textContent =
      (brief ? '精简 ' + (route.indexOf(current) + 1) + ' / ' + route.length + ' · ' : '') +
      '← → 翻页 · F 全屏 · Esc 目录 · B 静态';
    document.querySelectorAll('[data-page-number]').forEach(marker => {
      const index = Number(marker.dataset.pageNumber) - 1;
      marker.textContent = brief && route.includes(index)
        ? String(route.indexOf(index) + 1).padStart(2, '0') + ' / ' + String(route.length).padStart(2, '0')
        : String(index + 1).padStart(2, '0') + ' / ' + String(slides.length).padStart(2, '0');
    });
    const url = new URL(location.href);
    if (brief) url.searchParams.set('mode', 'brief');
    else url.searchParams.delete('mode');
    url.hash = String(current + 1);
    try { history.replaceState(null, '', url.href); } catch {}
    if (!document.body.classList.contains('low-power')) {
      const recipe = active.dataset.animate;
      active.querySelectorAll('[data-anim]').forEach((node, i) => {
        const frames = recipe === 'h-bar' && node.classList.contains('row-fill')
          ? [{ transform: 'scaleX(0)', transformOrigin: 'left' }, { transform: 'scaleX(1)', transformOrigin: 'left' }]
          : [{ opacity: .35, transform: 'translateY(8px)' }, { opacity: 1, transform: 'translateY(0)' }];
        node.animate(frames, { duration: 350, delay: i * 40, fill: 'backwards' });
      });
    }
  }
  function move(direction) {
    const next = Math.max(0, Math.min(route.length - 1, route.indexOf(current) + direction));
    go(route[next]);
  }
  document.addEventListener('keydown', (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === 'Escape') { e.preventDefault(); setOverview(overview.hidden); return; }
    if (!overview.hidden) {
      if (e.key === 'Tab') {
        const items = [...overview.querySelectorAll('button:not([hidden])')];
        const first = items[0], last = items.at(-1);
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
      return;
    }
    if (e.target instanceof HTMLElement && e.target.matches('input,textarea,select,[contenteditable="true"]')) return;
    if (e.key === ' ' && e.target instanceof HTMLElement && e.target.closest('button,a,summary')) return;
    if (['ArrowRight','ArrowDown','PageDown',' '].includes(e.key)) { e.preventDefault(); move(1); }
    if (['ArrowLeft','ArrowUp','PageUp'].includes(e.key)) { e.preventDefault(); move(-1); }
    if (e.key === 'Home') { e.preventDefault(); go(route[0]); }
    if (e.key === 'End') { e.preventDefault(); go(route.at(-1)); }
    if (e.key.toLowerCase() === 'f') {
      const operation = document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen();
      operation?.catch(() => {});
    }
    if (e.key.toLowerCase() === 'b') {
      const staticMode = document.body.classList.toggle('low-power');
      if (staticMode) document.getAnimations().forEach(animation => animation.cancel());
      try { localStorage.setItem('lane-deck-static', String(staticMode)); } catch {}
    }
  });
  document.addEventListener('wheel', (e) => {
    if (!overview.hidden || Math.abs(e.deltaY) < 12 || performance.now() - lastWheel < 650) return;
    lastWheel = performance.now(); move(Math.sign(e.deltaY));
  }, { passive: true });
  document.addEventListener('touchstart', (e) => { touchStart = e.touches[0].clientX; }, { passive: true });
  document.addEventListener('touchend', (e) => {
    if (!overview.hidden || touchStart === null) return;
    const delta = touchStart - e.changedTouches[0].clientX;
    if (Math.abs(delta) > 70) move(Math.sign(delta));
    touchStart = null;
  }, { passive: true });
  document.getElementById('prev').onclick = () => move(-1);
  document.getElementById('next').onclick = () => move(1);
  document.getElementById('contents').onclick = () => setOverview(overview.hidden);
  document.getElementById('close-index').onclick = () => setOverview(false);
  document.getElementById('mode-full').onclick = () => setMode(false);
  document.getElementById('mode-brief').onclick = () => setMode(true);
  window.goToSlide = (oneBased) => go(oneBased - 1);
  window.setDeckMode = setMode;
  const fromHash = Number(location.hash.slice(1));
  setMode(brief);
  go(Number.isFinite(fromHash) && fromHash > 0 ? fromHash - 1 : 0);
  window.addEventListener('hashchange', () => go(Number(location.hash.slice(1)) - 1));
  document.querySelectorAll('canvas.ascii-bg').forEach((canvas) => {
    const draw = () => {
      const rect = canvas.getBoundingClientRect();
      canvas.width = Math.max(1, rect.width); canvas.height = Math.max(1, rect.height);
      const ctx = canvas.getContext('2d');
      ctx.font = '12px Consolas'; ctx.fillStyle = 'rgba(255,255,255,.12)';
      for (let y = 20; y < canvas.height; y += 30) for (let x = canvas.width * .63; x < canvas.width; x += 22) {
        if ((Math.floor(x / 22) + Math.floor(y / 30)) % 3 === 0) ctx.fillText('+', x, y);
      }
    };
    draw(); window.addEventListener('resize', draw);
  });
})();

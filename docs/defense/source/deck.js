(() => {
  const slides = [...document.querySelectorAll('#deck > .slide')];
  const deck = document.getElementById('deck');
  const overview = document.getElementById('overview');
  const nav = document.getElementById('nav');
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
    index.onclick = () => { overview.hidden = true; go(i); };
    overview.querySelector('.index-list').append(index);
    return b;
  });
  function go(index) {
    current = Math.max(0, Math.min(slides.length - 1, index));
    deck.style.transform = 'translateX(-' + (current * 100) + 'vw)';
    slides.forEach((s, i) => s.setAttribute('aria-hidden', String(i !== current)));
    buttons.forEach((b, i) => { b.classList.toggle('active', i === current); b.setAttribute('aria-current', i === current ? 'page' : 'false'); });
    const active = slides[current];
    document.body.classList.toggle('dark-bg', active.classList.contains('dark') || active.classList.contains('accent'));
    document.body.classList.toggle('split-bg', active.classList.contains('split'));
    try { history.replaceState(null, '', '#' + (current + 1)); } catch {}
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
  document.addEventListener('keydown', (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === 'Escape') { overview.hidden = !overview.hidden; return; }
    if (!overview.hidden) return;
    if (['ArrowRight','ArrowDown','PageDown',' '].includes(e.key)) { e.preventDefault(); go(current + 1); }
    if (['ArrowLeft','ArrowUp','PageUp'].includes(e.key)) { e.preventDefault(); go(current - 1); }
    if (e.key === 'Home') go(0);
    if (e.key === 'End') go(slides.length - 1);
    if (e.key.toLowerCase() === 'f') {
      const operation = document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen();
      operation?.catch(() => {});
    }
    if (e.key.toLowerCase() === 'b') {
      const staticMode = document.body.classList.toggle('low-power');
      try { localStorage.setItem('lane-deck-static', String(staticMode)); } catch {}
    }
  });
  document.addEventListener('wheel', (e) => {
    if (!overview.hidden || Math.abs(e.deltaY) < 12 || performance.now() - lastWheel < 650) return;
    lastWheel = performance.now(); go(current + Math.sign(e.deltaY));
  }, { passive: true });
  document.addEventListener('touchstart', (e) => { touchStart = e.touches[0].clientX; }, { passive: true });
  document.addEventListener('touchend', (e) => {
    if (!overview.hidden || touchStart === null) return;
    const delta = touchStart - e.changedTouches[0].clientX;
    if (Math.abs(delta) > 70) go(current + Math.sign(delta));
    touchStart = null;
  }, { passive: true });
  document.getElementById('prev').onclick = () => go(current - 1);
  document.getElementById('next').onclick = () => go(current + 1);
  document.getElementById('contents').onclick = () => { overview.hidden = !overview.hidden; };
  document.getElementById('close-index').onclick = () => { overview.hidden = true; };
  window.goToSlide = (oneBased) => go(oneBased - 1);
  const fromHash = Number(location.hash.slice(1));
  go(Number.isFinite(fromHash) && fromHash > 0 ? fromHash - 1 : 0);
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

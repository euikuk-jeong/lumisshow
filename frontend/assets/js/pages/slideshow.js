import { shareApi, ShareAuthError } from '../api.js';
import { esc } from '../utils.js';

const TRANS_MS = 700;
const KB_CLASSES = ['kb-tl','kb-tr','kb-bl','kb-br','kb-t','kb-b','kb-l','kb-r'];
// Keep in sync with EFFECTS in album-view.js (excluding 'random')
const EFFECTS = ['fade','slide-left','slide-right','slide-up','zoom-in','zoom-out','flip-h','blur','dissolve'];

const DEFAULT_SETTINGS = { interval: 5, order: 'sequential', music: true, volume: 60, effect: 'random' };

function loadSettings() {
  try {
    const s = { ...DEFAULT_SETTINGS, ...JSON.parse(localStorage.getItem('slideshow_settings') || '{}') };
    if (!['sequential', 'random'].includes(s.order)) s.order = DEFAULT_SETTINGS.order;
    if (s.effect !== 'random' && !EFFECTS.includes(s.effect)) s.effect = DEFAULT_SETTINGS.effect;
    return s;
  } catch { return { ...DEFAULT_SETTINGS }; }
}

function buildOrder(total, order, startIdx) {
  const seq = Array.from({ length: total }, (_, i) => i);
  if (order === 'random') {
    for (let i = seq.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [seq[i], seq[j]] = [seq[j], seq[i]];
    }
    const p = seq.indexOf(startIdx);
    if (p > 0) [seq[0], seq[p]] = [seq[p], seq[0]];
    return seq;
  }
  // Sequential: rotate so startIdx is first
  return [...seq.slice(startIdx), ...seq.slice(0, startIdx)];
}

export async function renderSlideshow(token) {
  const app = document.getElementById('app');
  app.innerHTML = '<div class="loading" style="height:100vh"></div>';

  // Cleanup previous page (e.g. prior slideshow)
  window._pageCleanup?.();
  window._pageCleanup = null;

  let album, photosData;
  try {
    [album, photosData] = await Promise.all([
      shareApi.get(`/api/share/${token}/album`),
      shareApi.get(`/api/share/${token}/photos`),
    ]);
  } catch (e) {
    if (e instanceof ShareAuthError || /404|not found/i.test(e.message)) {
      window.navigate(`/s/${token}`, true);
      return;
    }
    app.innerHTML = `<div style="padding:40px;color:var(--error)">${esc(e.message)}</div>`;
    return;
  }

  const photos = photosData.photos;
  if (!photos.length) {
    app.innerHTML = '<div style="padding:40px;text-align:center;color:var(--muted)">사진이 없습니다.</div>';
    return;
  }

  const cfg = loadSettings();
  const rawI = parseInt(new URLSearchParams(location.search).get('i') ?? '0', 10);
  const startIdx = isNaN(rawI) ? 0 : Math.max(0, Math.min(photos.length - 1, rawI));
  const displayOrder = buildOrder(photos.length, cfg.order, startIdx);

  // ── Mutable state ────────────────────────────────────────────
  let pos = 0;
  let activeSlot = 'a';
  let playing = true;
  let transitioning = false;
  let timer = null;
  let transTimer = null;
  const preloadCache = {};

  // ── Audio ────────────────────────────────────────────────────
  let audio = null;
  let musicOn = cfg.music && album.has_music;
  if (album.has_music) {
    audio = new Audio(`/music/${token}`);
    audio.loop = true;
    audio.volume = cfg.volume / 100;
  }

  // ── Render HTML ──────────────────────────────────────────────
  const musicHtml = album.has_music ? `
    <button class="ss-tb-btn" id="ss-music-btn" title="음악 끄기">♫</button>
    <input type="range" id="ss-vol" class="ss-vol" min="0" max="100" value="${cfg.volume}" title="음량">
  ` : '';

  app.innerHTML = `
    <div class="ss-wrap" id="ss-wrap">
      <div class="ss-slot" id="ss-slot-a">
        <img class="ss-img" id="ss-img-a" alt="">
      </div>
      <div class="ss-slot" id="ss-slot-b">
        <img class="ss-img" id="ss-img-b" alt="">
      </div>
      <button class="ss-arrow ss-arrow-prev" id="ss-arr-prev">&#8249;</button>
      <button class="ss-arrow ss-arrow-next" id="ss-arr-next">&#8250;</button>
      <div class="ss-toolbar">
        <button class="ss-tb-btn" id="ss-pause-btn" title="일시정지">&#9646;&#9646;</button>
        <button class="ss-tb-btn" id="ss-prev-btn" title="이전">&#9664;</button>
        <span class="ss-counter" id="ss-counter">1 / ${photos.length}</span>
        <button class="ss-tb-btn" id="ss-next-btn" title="다음">&#9654;</button>
        <a class="ss-tb-btn" id="ss-dl-btn" title="현재 사진 다운로드" download>&#8595;</a>
        ${musicHtml}
        <button class="ss-tb-btn" id="ss-close-btn" title="닫기">&#215;</button>
      </div>
    </div>`;

  const slotEls = { a: document.getElementById('ss-slot-a'), b: document.getElementById('ss-slot-b') };
  const imgEls  = { a: document.getElementById('ss-img-a'),  b: document.getElementById('ss-img-b') };

  // Active slot is on top
  slotEls.a.style.zIndex = 2;
  slotEls.b.style.zIndex = 1;

  // ── Helpers ──────────────────────────────────────────────────

  function photoAt(p) {
    return photos[displayOrder[((p % photos.length) + photos.length) % photos.length]];
  }

  function preload(p) {
    const idx = displayOrder[((p % photos.length) + photos.length) % photos.length];
    if (!preloadCache[idx]) {
      const img = new Image();
      img.src = photos[idx].thumb_medium_url;
      preloadCache[idx] = img;
    }
  }

  function unload(p) {
    const idx = displayOrder[((p % photos.length) + photos.length) % photos.length];
    if (preloadCache[idx]) { preloadCache[idx].src = ''; delete preloadCache[idx]; }
  }

  function startKenBurns(slot) {
    const el = slotEls[slot];
    el.classList.remove(...KB_CLASSES);
    void el.offsetWidth; // force reflow to restart animation
    const cls = KB_CLASSES[Math.floor(Math.random() * KB_CLASSES.length)];
    el.style.setProperty('--kb-dur', cfg.interval + 's');
    el.classList.add(cls);
  }

  function updateUI() {
    const photo = photoAt(pos);
    const dlBtn = document.getElementById('ss-dl-btn');
    dlBtn.href = photo.url;
    dlBtn.download = photo.url.split('/').pop().split('?')[0] || 'photo.jpg';
    document.getElementById('ss-counter').textContent = `${pos + 1} / ${photos.length}`;
    const pauseBtn = document.getElementById('ss-pause-btn');
    pauseBtn.innerHTML = playing ? '&#9646;&#9646;' : '&#9654;';
    pauseBtn.title = playing ? '일시정지' : '재개';
  }

  function scheduleNext() {
    clearTimeout(timer);
    if (playing && !transitioning) {
      timer = setTimeout(() => advance(1), cfg.interval * 1000);
    }
  }

  function advance(dir) {
    if (transitioning) return;
    clearTimeout(timer);

    const nextPos = ((pos + dir) % photos.length + photos.length) % photos.length;
    const incoming = activeSlot === 'a' ? 'b' : 'a';

    // Pick effect
    let eff = cfg.effect === 'random'
      ? EFFECTS[Math.floor(Math.random() * EFFECTS.length)]
      : cfg.effect;

    // Set next image in incoming slot
    imgEls[incoming].src = photoAt(nextPos).thumb_medium_url;

    // incoming on top
    slotEls[incoming].style.zIndex = 3;
    slotEls[activeSlot].style.zIndex = 2;

    // Start Ken Burns on incoming
    startKenBurns(incoming);

    // Apply transition animations
    transitioning = true;
    slotEls[activeSlot].classList.add(`ss-out-${eff}`);
    slotEls[incoming].classList.add(`ss-in-${eff}`);

    transTimer = setTimeout(() => {
      // Remove transition classes
      slotEls[activeSlot].classList.remove(`ss-out-${eff}`);
      slotEls[incoming].classList.remove(`ss-in-${eff}`);
      // Remove KB from outgoing
      slotEls[activeSlot].classList.remove(...KB_CLASSES);
      // Settle z-index: new active = 2, old active = 1
      slotEls[activeSlot].style.zIndex = 1;
      slotEls[incoming].style.zIndex = 2;

      activeSlot = incoming;
      pos = nextPos;
      transitioning = false;

      // Preload ahead, release old
      preload(pos + 1);
      preload(pos + 2);
      unload(pos - 3);

      updateUI();
      scheduleNext();
    }, TRANS_MS);
  }

  // ── Cleanup (registered early so navigation during init is safe) ──
  function cleanup() {
    clearTimeout(timer);
    clearTimeout(transTimer);
    document.removeEventListener('keydown', handleKeydown);
    if (audio) { audio.pause(); audio.src = ''; }
  }
  window._pageCleanup = cleanup;

  // ── Initial display ──────────────────────────────────────────
  imgEls.a.src = photoAt(0).thumb_medium_url;
  startKenBurns('a');
  preload(1);
  preload(2);
  updateUI();
  scheduleNext();

  // ── Music ────────────────────────────────────────────────────
  if (audio && musicOn) {
    audio.play().catch(() => {
      musicOn = false;
      const btn = document.getElementById('ss-music-btn');
      if (btn) { btn.textContent = '♫'; btn.style.opacity = '0.4'; btn.title = '음악 켜기'; }
    });
  }

  // ── Button events ────────────────────────────────────────────
  document.getElementById('ss-pause-btn').addEventListener('click', () => {
    playing = !playing;
    if (playing) scheduleNext(); else clearTimeout(timer);
    updateUI();
  });

  document.getElementById('ss-prev-btn').addEventListener('click', () => advance(-1));
  document.getElementById('ss-next-btn').addEventListener('click', () => advance(1));
  document.getElementById('ss-arr-prev').addEventListener('click', () => advance(-1));
  document.getElementById('ss-arr-next').addEventListener('click', () => advance(1));

  function closeSlideshow() {
    cleanup();
    window.navigate(`/s/${token}/view`, true);
  }
  document.getElementById('ss-close-btn').addEventListener('click', closeSlideshow);

  if (album.has_music) {
    const musicBtn = document.getElementById('ss-music-btn');
    const volSlider = document.getElementById('ss-vol');

    musicBtn.addEventListener('click', () => {
      if (!audio) return;
      musicOn = !musicOn;
      if (musicOn) {
        audio.play().catch(() => { musicOn = false; musicBtn.style.opacity = '0.4'; musicBtn.title = '음악 켜기'; });
        musicBtn.style.opacity = '1'; musicBtn.title = '음악 끄기';
      } else {
        audio.pause();
        musicBtn.style.opacity = '0.4'; musicBtn.title = '음악 켜기';
      }
    });

    volSlider.addEventListener('input', (e) => {
      if (audio) audio.volume = parseInt(e.target.value, 10) / 100;
    });
  }

  // ── Keyboard ─────────────────────────────────────────────────
  function handleKeydown(e) {
    switch (e.key) {
      case 'ArrowRight': case 'ArrowDown':  advance(1);  break;
      case 'ArrowLeft':  case 'ArrowUp':    advance(-1); break;
      case ' ':
        e.preventDefault();
        playing = !playing;
        if (playing) scheduleNext(); else clearTimeout(timer);
        updateUI();
        break;
      case 'Escape': closeSlideshow(); break;
    }
  }
  document.addEventListener('keydown', handleKeydown);

  // ── Touch swipe ──────────────────────────────────────────────
  let touchX = 0, touchY = 0;
  const wrap = document.getElementById('ss-wrap');
  wrap.addEventListener('touchstart', (e) => {
    touchX = e.touches[0].clientX;
    touchY = e.touches[0].clientY;
  }, { passive: true });
  wrap.addEventListener('touchend', (e) => {
    const dx = e.changedTouches[0].clientX - touchX;
    const dy = e.changedTouches[0].clientY - touchY;
    if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 50) advance(dx < 0 ? 1 : -1);
  }, { passive: true });

}

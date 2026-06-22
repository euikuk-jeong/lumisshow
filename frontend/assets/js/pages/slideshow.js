import { shareApi, ShareAuthError } from '../api.js';
import { esc } from '../utils.js';
import { EFFECTS, DEFAULT_SETTINGS, loadSlideshowSettings, saveSlideshowSettings } from '../slideshow-config.js';

const TRANS_MS = 700;
const KB_CLASSES = ['kb-tl','kb-tr','kb-bl','kb-br','kb-t','kb-b','kb-l','kb-r'];

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

  const PAGE_SIZE = 50;
  let album, firstPage;
  try {
    [album, firstPage] = await Promise.all([
      shareApi.get(`/api/share/${token}/album`),
      shareApi.get(`/api/share/${token}/photos?size=${PAGE_SIZE}`),
    ]);
  } catch (e) {
    if (e instanceof ShareAuthError || /404|not found/i.test(e.message)) {
      window.navigate(`/s/${token}`, true);
      return;
    }
    app.innerHTML = `<div style="padding:40px;color:var(--error)">${esc(e.message)}</div>`;
    return;
  }

  const totalPhotos = firstPage.total;
  if (!totalPhotos) {
    app.innerHTML = '<div style="padding:40px;text-align:center;color:var(--muted)">사진이 없습니다.</div>';
    return;
  }

  // photos는 희소 배열: 로드된 항목만 채워짐. 나머지는 undefined.
  const photos = new Array(totalPhotos);
  firstPage.photos.forEach((p, i) => { photos[i] = p; });

  const cfg = loadSlideshowSettings(album.slideshow_defaults || {}, token);
  const rawI = parseInt(new URLSearchParams(location.search).get('i') ?? '', 10);
  const urlIdx = isNaN(rawI) ? null : Math.max(0, Math.min(totalPhotos - 1, rawI));
  const startIdx = urlIdx ?? 0;

  // Remove ?i=N from URL — it was only needed to pick the start photo
  if (urlIdx !== null) {
    const url = new URL(location.href);
    url.searchParams.delete('i');
    history.replaceState(null, '', url.pathname + (url.search || ''));
  }

  // startIdx가 첫 페이지 범위(0~PAGE_SIZE-1)를 벗어나면 해당 페이지를 즉시 로드
  if (!photos[startIdx]) {
    const pageNum = Math.floor(startIdx / PAGE_SIZE) + 1;
    try {
      const data = await shareApi.get(`/api/share/${token}/photos?page=${pageNum}&size=${PAGE_SIZE}`);
      const offset = (pageNum - 1) * PAGE_SIZE;
      data.photos.forEach((photo, i) => { photos[offset + i] = photo; });
    } catch (_) {}
  }

  const displayOrder = buildOrder(totalPhotos, cfg.order, startIdx);

  // 나머지 페이지 백그라운드 로드
  let bgLoadAborted = false;
  (async () => {
    const totalPages = Math.ceil(totalPhotos / PAGE_SIZE);
    for (let p = 2; p <= totalPages; p++) {
      if (bgLoadAborted) break;
      try {
        const data = await shareApi.get(`/api/share/${token}/photos?page=${p}&size=${PAGE_SIZE}`);
        const offset = (p - 1) * PAGE_SIZE;
        data.photos.forEach((photo, i) => { photos[offset + i] = photo; });
      } catch (_) { break; }
    }
  })();

  // ── Mutable state ────────────────────────────────────────────
  let pos = 0;
  let activeSlot = 'a';
  let playing = true;
  let transitioning = false;
  let timer = null;
  let transTimer = null;
  let hideTimer = null;
  const preloadCache = {};

  // ── Audio ────────────────────────────────────────────────────
  const musicCount = album.music_count || 0;
  let audio = null;
  let musicOn = cfg.music && musicCount > 0;
  let musicTrackIdx = 0;

  if (musicCount > 0) {
    audio = new Audio(`/music/${token}?index=0`);
    audio.volume = cfg.volume / 100;
    if (musicCount === 1) {
      audio.loop = true;
    } else {
      audio.addEventListener('ended', () => {
        musicTrackIdx = (musicTrackIdx + 1) % musicCount;
        audio.src = `/music/${token}?index=${musicTrackIdx}`;
        if (musicOn) audio.play().catch(() => {});
      });
    }
  }

  function loadTrack(idx) {
    if (!audio) return;
    musicTrackIdx = ((idx % musicCount) + musicCount) % musicCount;
    audio.src = `/music/${token}?index=${musicTrackIdx}`;
    if (musicOn) {
      audio.play().catch(() => {});
      showMusicToast();
    }
    refreshInfoPanel();
  }

  // ── Render HTML ──────────────────────────────────────────────
  const prevNextTrackHtml = musicCount > 1 ? `
    <button class="ss-tb-btn" id="ss-prev-track" title="이전 곡">&#9198;</button>
    <button class="ss-tb-btn" id="ss-next-track" title="다음 곡">&#9197;</button>
  ` : '';
  const musicHtml = musicCount > 0 ? `
    <div class="ss-music-group">
      <button class="ss-tb-btn" id="ss-music-btn" title="음악 끄기">&#9835;</button>
      ${prevNextTrackHtml}
      <input type="range" id="ss-vol" class="ss-vol" min="0" max="100" value="${cfg.volume}" title="음량">
    </div>
  ` : '<div class="ss-music-group"></div>';

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
        ${musicHtml}
        <div class="ss-toolbar-spacer"></div>
        <div class="ss-speed-group">
          <button class="ss-tb-btn" id="ss-speed-down" title="느리게">&#8722;</button>
          <span class="ss-speed-label" id="ss-speed-label">${cfg.interval}s</span>
          <button class="ss-tb-btn" id="ss-speed-up" title="빠르게">&#43;</button>
        </div>
        <button class="ss-tb-btn" id="ss-pause-btn" title="일시정지">&#9646;&#9646;</button>
        <button class="ss-tb-btn" id="ss-prev-btn" title="이전">&#9664;</button>
        <span class="ss-counter" id="ss-counter">1 / ${photos.length}</span>
        <button class="ss-tb-btn" id="ss-next-btn" title="다음">&#9654;</button>
        <a class="ss-tb-btn" id="ss-dl-btn" title="현재 사진 다운로드" download>&#8595;</a>
        <button class="ss-tb-btn ss-info-btn-icon" id="ss-info-btn" title="정보">i</button>
        <button class="ss-tb-btn" id="ss-fs-btn" title="전체화면">&#x26F6;</button>
        <button class="ss-tb-btn" id="ss-close-btn" title="닫기">&#215;</button>
      </div>
      <div class="ss-music-toast" id="ss-music-toast">
        <span class="ss-music-toast-icon">&#9835;</span>
        <span id="ss-music-toast-name"></span>
      </div>
      <div class="ss-loop-toast" id="ss-loop-toast"></div>
      <div class="ss-info" id="ss-info" style="display:none"></div>
      <div class="ss-tap-hint ss-tap-hint-prev">&#8249;</div>
      <div class="ss-tap-hint ss-tap-hint-next">&#8250;</div>
    </div>`;

  const slotEls = { a: document.getElementById('ss-slot-a'), b: document.getElementById('ss-slot-b') };
  const imgEls  = { a: document.getElementById('ss-img-a'),  b: document.getElementById('ss-img-b') };

  // Active slot is on top
  slotEls.a.style.zIndex = 2;
  slotEls.b.style.zIndex = 1;

  // ── Helpers ──────────────────────────────────────────────────

  function photoAt(p) {
    return photos[displayOrder[((p % totalPhotos) + totalPhotos) % totalPhotos]];
  }

  function preload(p) {
    const idx = displayOrder[((p % totalPhotos) + totalPhotos) % totalPhotos];
    const photo = photos[idx];
    if (photo && !preloadCache[idx]) {
      const img = new Image();
      img.src = photo.url;
      preloadCache[idx] = img;
    }
  }

  function unload(p) {
    const idx = displayOrder[((p % totalPhotos) + totalPhotos) % totalPhotos];
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

  let infoVisible = false;

  function formatInfo(photo) {
    const rows = [];
    const add = (label, value) => { if (value != null && value !== '') rows.push([label, String(value)]); };

    add('Filename', photo.filename);
    if (photo.taken_at) {
      const d = new Date(photo.taken_at);
      const pad = n => String(n).padStart(2, '0');
      add('Date', `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`);
    }
    if (photo.width && photo.height) add('Resolution', `${photo.width} × ${photo.height}`);
    add('Make', photo.make);
    add('Camera', photo.camera);
    add('Software', photo.software);
    add('Shoot Mode', photo.shoot_mode);
    add('Exposure', photo.shutter);
    add('Aperture', photo.aperture);
    add('ISO', photo.iso);
    add('Focal Length', photo.focal_length);
    add('Flash', photo.flash);
    add('Metering', photo.metering);
    add('Exposure Mode', photo.exposure_mode);

    return rows.map(([l, v]) =>
      `<div class="ss-info-row"><span class="ss-info-label">${esc(l)}</span><span class="ss-info-value">${esc(v)}</span></div>`
    ).join('');
  }

  function renderInfoContent() {
    const photo = photoAt(pos);
    const photoHtml = photo ? formatInfo(photo) : '';
    if (!audio || !musicOn) return photoHtml;

    const names = album.music_names || [];
    const raw = names[musicTrackIdx] || `트랙 ${musicTrackIdx + 1}`;
    const rows = [];
    rows.push(['파일', raw.replace(/\.[^.]+$/, '')]);
    if (musicCount > 1) rows.push(['트랙', `${musicTrackIdx + 1} / ${musicCount}`]);
    const musicHtml = rows.map(([l, v]) =>
      `<div class="ss-info-row"><span class="ss-info-label">${esc(l)}</span><span class="ss-info-value">${esc(v)}</span></div>`
    ).join('');

    return `${photoHtml}<div class="ss-info-divider"></div><div class="ss-info-section">&#9835; 재생 중</div>${musicHtml}`;
  }

  function refreshInfoPanel() {
    const infoEl = document.getElementById('ss-info');
    if (infoEl && infoVisible) infoEl.innerHTML = renderInfoContent();
  }

  function updateUI() {
    const photo = photoAt(pos);
    const dlBtn = document.getElementById('ss-dl-btn');
    if (photo) {
      dlBtn.href = photo.url;
      dlBtn.download = photo.filename || 'photo.jpg';
    }
    document.getElementById('ss-counter').textContent = `${pos + 1} / ${totalPhotos}`;
    const pauseBtn = document.getElementById('ss-pause-btn');
    pauseBtn.innerHTML = playing ? '&#9646;&#9646;' : '&#9654;';
    pauseBtn.title = playing ? '일시정지' : '재개';
    refreshInfoPanel();
  }

  function scheduleNext() {
    clearTimeout(timer);
    if (playing && !transitioning) {
      if (!cfg.loop && pos === totalPhotos - 1) {
        timer = setTimeout(() => {
          playing = false;
          updateUI();
          showLoopToast('슬라이드쇼가 종료되었습니다', 10000);
        }, cfg.interval * 1000);
        return;
      }
      timer = setTimeout(() => advance(1), cfg.interval * 1000);
    }
  }

  function advance(dir) {
    if (transitioning) return;
    if (!cfg.loop && ((dir < 0 && pos === 0) || (dir > 0 && pos === totalPhotos - 1))) return;
    clearTimeout(timer);

    const nextPos = ((pos + dir) % totalPhotos + totalPhotos) % totalPhotos;
    const wrapped = cfg.loop && dir > 0 && pos === totalPhotos - 1 && nextPos === 0;
    const incoming = activeSlot === 'a' ? 'b' : 'a';

    const nextPhoto = photoAt(nextPos);
    if (!nextPhoto) {
      // 아직 백그라운드 로드 중 — 200ms 후 재시도
      timer = setTimeout(() => advance(dir), 200);
      return;
    }

    // Pick effect
    let eff = cfg.effect === 'random'
      ? EFFECTS[Math.floor(Math.random() * EFFECTS.length)]
      : cfg.effect;

    // Set next image in incoming slot
    imgEls[incoming].src = nextPhoto.url;
    slotEls[incoming].style.setProperty('--ss-bg-img', `url("${nextPhoto.thumb_medium_url}")`);

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
      if (wrapped) showLoopToast('🔁 처음부터 다시 재생');
    }, TRANS_MS);
  }

  // ── Loop toast ───────────────────────────────────────────────
  let loopToastTimer = null;

  function showLoopToast(msg, duration = 3000) {
    const toast = document.getElementById('ss-loop-toast');
    if (!toast) return;
    toast.textContent = msg;
    toast.classList.add('visible');
    clearTimeout(loopToastTimer);
    loopToastTimer = setTimeout(() => toast.classList.remove('visible'), duration);
  }

  // ── Music toast ──────────────────────────────────────────────
  let musicToastTimer = null;

  function showMusicToast() {
    const toast = document.getElementById('ss-music-toast');
    if (!toast) return;
    const names = album.music_names || [];
    const raw = names[musicTrackIdx] || `트랙 ${musicTrackIdx + 1}`;
    document.getElementById('ss-music-toast-name').textContent = raw.replace(/\.[^.]+$/, '');
    toast.classList.add('visible');
    clearTimeout(musicToastTimer);
    musicToastTimer = setTimeout(() => toast.classList.remove('visible'), 3000);
  }

  // ── Cleanup (registered early so navigation during init is safe) ──
  function cleanup() {
    bgLoadAborted = true;
    clearTimeout(timer);
    clearTimeout(transTimer);
    clearTimeout(musicToastTimer);
    clearTimeout(loopToastTimer);
    clearTimeout(hideTimer);
    document.removeEventListener('keydown', handleKeydown);
    document.removeEventListener('fullscreenchange', handleFSChange);
    if (audio) { audio.pause(); audio.src = ''; }
    screen.orientation?.unlock();
  }
  window._pageCleanup = cleanup;

  // ── Initial display ──────────────────────────────────────────
  imgEls.a.src = photoAt(0).url;
  slotEls.a.style.setProperty('--ss-bg-img', `url("${photoAt(0).thumb_medium_url}")`);
  startKenBurns('a');
  preload(1);
  preload(2);
  updateUI();
  scheduleNext();

  // ── Music ────────────────────────────────────────────────────
  function updateMusicBtn() {
    const btn = document.getElementById('ss-music-btn');
    if (!btn) return;
    btn.style.opacity = musicOn ? '1' : '0.4';
    btn.title = musicOn ? '음악 끄기' : '음악 켜기';
  }

  if (audio && musicOn) {
    audio.play().then(() => showMusicToast()).catch(() => {
      musicOn = false;
      updateMusicBtn();
    });
  }
  updateMusicBtn();

  // ── Button events ────────────────────────────────────────────
  document.getElementById('ss-pause-btn').addEventListener('click', () => {
    playing = !playing;
    if (playing) scheduleNext(); else clearTimeout(timer);
    updateUI();
  });

  const SPEED_STEPS = [2, 3, 5, 8, 10, 15, 20, 30];
  function changeSpeed(delta) {
    const idx = SPEED_STEPS.reduce((best, s, i) =>
      Math.abs(s - cfg.interval) < Math.abs(SPEED_STEPS[best] - cfg.interval) ? i : best, 0);
    cfg.interval = SPEED_STEPS[Math.max(0, Math.min(SPEED_STEPS.length - 1, idx + delta))];
    document.getElementById('ss-speed-label').textContent = cfg.interval + 's';
    saveSlideshowSettings(token, cfg);
    clearTimeout(timer);
    scheduleNext();
  }
  document.getElementById('ss-speed-down').addEventListener('click', () => changeSpeed(-1));
  document.getElementById('ss-speed-up').addEventListener('click', () => changeSpeed(1));

  document.getElementById('ss-prev-btn').addEventListener('click', () => advance(-1));
  document.getElementById('ss-next-btn').addEventListener('click', () => advance(1));
  document.getElementById('ss-arr-prev').addEventListener('click', () => advance(-1));
  document.getElementById('ss-arr-next').addEventListener('click', () => advance(1));

  function closeSlideshow() {
    if (document.fullscreenElement) document.exitFullscreen();
    cleanup();
    window.navigate(`/s/${token}/view`, true);
  }
  document.getElementById('ss-close-btn').addEventListener('click', closeSlideshow);

  document.getElementById('ss-info-btn').addEventListener('click', () => {
    infoVisible = !infoVisible;
    const infoEl = document.getElementById('ss-info');
    const btn = document.getElementById('ss-info-btn');
    if (infoVisible) {
      infoEl.innerHTML = renderInfoContent();
      infoEl.style.display = 'block';
      btn.style.background = 'rgba(255,255,255,0.35)';
    } else {
      infoEl.style.display = 'none';
      btn.style.background = '';
    }
  });

  if (musicCount > 0) {
    document.getElementById('ss-music-btn').addEventListener('click', () => {
      if (!audio) return;
      musicOn = !musicOn;
      if (musicOn) {
        audio.play().then(() => showMusicToast()).catch(() => { musicOn = false; updateMusicBtn(); });
      } else {
        audio.pause();
      }
      updateMusicBtn();
      refreshInfoPanel();
    });

    document.getElementById('ss-vol')?.addEventListener('input', e => {
      if (audio) audio.volume = parseInt(e.target.value, 10) / 100;
    });

    if (musicCount > 1) {
      document.getElementById('ss-prev-track').addEventListener('click', () => loadTrack(musicTrackIdx - 1));
      document.getElementById('ss-next-track').addEventListener('click', () => loadTrack(musicTrackIdx + 1));
    }
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

  // ── Touch tap zones (좌35% = 이전, 우35% = 다음, 중앙 = 툴바 토글) ──
  const wrap = document.getElementById('ss-wrap');
  let tStart = null;
  wrap.addEventListener('touchstart', (e) => {
    tStart = { x: e.touches[0].clientX, y: e.touches[0].clientY, t: Date.now() };
  }, { passive: true });
  wrap.addEventListener('touchend', (e) => {
    if (!tStart) return;
    const dx = Math.abs(e.changedTouches[0].clientX - tStart.x);
    const dy = Math.abs(e.changedTouches[0].clientY - tStart.y);
    const dt = Date.now() - tStart.t;
    tStart = null;
    if (dx < 15 && dy < 15 && dt < 300) {
      const rect = wrap.getBoundingClientRect();
      const relX = (e.changedTouches[0].clientX - rect.left) / rect.width;
      if (relX < 0.35) { advance(-1); showUI(); }
      else if (relX > 0.65) { advance(1); showUI(); }
      else toggleUI();
    }
  }, { passive: true });

  // ── 모바일: 자동 전체화면 + orientation lock ─────────────────
  if (window.matchMedia('(pointer: coarse) and (hover: none)').matches) {
    document.documentElement.requestFullscreen?.()
      .then(() => screen.orientation?.lock('landscape').catch(() => {}))
      .catch(() => {});
  }

  // ── UI auto-hide ─────────────────────────────────────────────
  function showUI() {
    wrap.classList.remove('ss-ui-hidden');
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => wrap.classList.add('ss-ui-hidden'), 3000);
  }
  function toggleUI() {
    if (wrap.classList.contains('ss-ui-hidden')) {
      showUI();
    } else {
      clearTimeout(hideTimer);
      wrap.classList.add('ss-ui-hidden');
    }
  }
  if (!window.matchMedia('(pointer: coarse) and (hover: none)').matches) {
    wrap.addEventListener('mousemove', showUI);
  }
  showUI();

  // ── Fullscreen ───────────────────────────────────────────────
  function handleFSChange() {
    const btn = document.getElementById('ss-fs-btn');
    if (btn) btn.innerHTML = document.fullscreenElement ? '&#x22A1;' : '&#x26F6;';
  }
  document.addEventListener('fullscreenchange', handleFSChange);
  document.getElementById('ss-fs-btn').addEventListener('click', () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen()
        .then(() => screen.orientation?.lock('landscape').catch(() => {}))
        .catch(() => {});
    } else {
      document.exitFullscreen();
    }
  });

}

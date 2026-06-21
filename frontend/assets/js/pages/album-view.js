import { shareApi, ShareAuthError } from '../api.js';
import { esc, getVersion } from '../utils.js';
import { EFFECTS, EFFECT_LABELS, loadSlideshowSettings } from '../slideshow-config.js';

function saveSettings(token, s) {
  localStorage.setItem(`slideshow_settings_${token}`, JSON.stringify(s));
}

function formatDateInTZ(isoString, offsetMinutes) {
  const utcMs = new Date(isoString).getTime();
  const tzDate = new Date(utcMs + offsetMinutes * 60 * 1000);
  const y = tzDate.getUTCFullYear();
  const m = tzDate.getUTCMonth() + 1;
  const d = tzDate.getUTCDate();
  return `${y}. ${m}. ${d}.`;
}

export async function renderAlbumView(token) {
  const app = document.getElementById('app');
  app.innerHTML = '<div class="loading"></div>';

  let album, photosData;
  try {
    [album, photosData] = await Promise.all([
      shareApi.get(`/api/share/${token}/album`),
      shareApi.get(`/api/share/${token}/photos`),
    ]);
  } catch (e) {
    if (e instanceof ShareAuthError) {
      window.navigate(`/s/${token}`, true);
      return;
    }
    app.innerHTML = `<div style="padding:40px;color:var(--error)">${esc(e.message)}</div>`;
    return;
  }

  // 앨범에 설정된 테마를 뷰어에 적용 (localStorage 개인 설정과 별개)
  document.documentElement.dataset.theme = album.ui_theme || 'dark';

  const photos = photosData.photos;
  const coverPhoto = album.cover_index != null ? photos[album.cover_index] : photos[0];
  const coverUrl = coverPhoto ? coverPhoto.thumb_medium_url : null;

  const tzOffset = album.timezone_offset ?? 0;
  const expiryHtml = album.expires_at
    ? `<span>⏰ 만료: ${formatDateInTZ(album.expires_at, tzOffset)}</span>`
    : '';

  app.innerHTML = `
    <div class="viewer-page">
      ${coverUrl ? `<div class="viewer-cover"><img src="${coverUrl}" alt="커버"></div>` : ''}
      <div class="viewer-body">
        <h1 class="viewer-title">${esc(album.album_name)}</h1>
        ${album.description ? `<p class="viewer-desc text-muted">${esc(album.description)}</p>` : ''}
        <div class="viewer-meta">
          <span>📷 ${album.photo_count}장</span>
          <span>📅 ${new Date(album.created_at).toLocaleDateString('ko-KR')}</span>
          ${expiryHtml}
          ${album.has_music ? '<span>🎵 음악 있음</span>' : ''}
        </div>
        <div class="viewer-actions">
          <button class="btn btn-primary btn-lg" id="btn-slideshow">▶ 슬라이드쇼</button>
          <button class="btn btn-ghost btn-lg" id="btn-settings">⚙ 설정</button>
        </div>
        <a class="btn btn-ghost w-full viewer-download"
           ${photos.length > 0 ? `href="/api/share/${token}/download"` : 'aria-disabled="true" tabindex="-1" style="opacity:0.4;pointer-events:none;cursor:not-allowed"'}>⬇ 전체 다운로드 (ZIP)</a>
        ${photos.length > 0 ? `
          <div class="viewer-grid" id="thumb-grid">
            ${photos.map((p, i) => `
              <div class="viewer-thumb" data-idx="${i}">
                <img src="${p.thumb_small_url}" alt="" loading="lazy">
              </div>`).join('')}
          </div>` : ''}
        <div class="viewer-version" id="viewer-version"></div>
      </div>
    </div>
    <div class="settings-overlay" id="settings-overlay" style="display:none">
      <div class="settings-panel">
        <h2 class="settings-title">슬라이드쇼 설정</h2>
        <div class="form-group">
          <label class="form-label">전환 시간 (초)</label>
          <input type="number" id="s-interval" min="2" max="60" class="form-input" style="width:100px">
        </div>
        <div class="form-group">
          <label class="form-label">순서</label>
          <div class="settings-radios">
            <label><input type="radio" name="s-order" value="sequential"> 순서대로</label>
            <label><input type="radio" name="s-order" value="random"> 랜덤</label>
          </div>
        </div>
        <div class="form-group">
          <label class="form-label">배경음악</label>
          <div class="settings-radios">
            <label><input type="radio" name="s-music" value="on"> ON</label>
            <label><input type="radio" name="s-music" value="off"> OFF</label>
          </div>
        </div>
        <div class="form-group">
          <label class="form-label">반복 재생</label>
          <div class="settings-radios">
            <label><input type="radio" name="s-loop" value="on"> 켜기</label>
            <label><input type="radio" name="s-loop" value="off"> 끄기</label>
          </div>
        </div>
        <div class="form-group" id="s-volume-group">
          <label class="form-label">음량 <span id="s-volume-label">25%</span></label>
          <input type="range" id="s-volume" min="0" max="100" class="w-full">
        </div>
        <div class="form-group">
          <label class="form-label">전환 효과</label>
          <select id="s-effect" class="form-select">
            ${['random', ...EFFECTS].map(e => `<option value="${e}">${EFFECT_LABELS[e]}</option>`).join('')}
          </select>
        </div>
        <div class="settings-actions">
          <button class="btn btn-ghost" id="btn-cancel">취소</button>
          <button class="btn btn-primary" id="btn-start">▶ 시작</button>
        </div>
      </div>
    </div>`;

  _initSettingsPanel(token, album);
  getVersion().then(v => {
    const el = document.getElementById('viewer-version');
    if (el) el.textContent = `LumisShow ${v} · Made by Ekjeong`;
  });

  document.getElementById('btn-slideshow').addEventListener('click', () => {
    window.navigate(`/s/${token}/slideshow`);
  });
  document.getElementById('btn-settings').addEventListener('click', () => {
    document.getElementById('settings-overlay').style.display = 'flex';
  });

  document.getElementById('thumb-grid')?.addEventListener('click', (e) => {
    const thumb = e.target.closest('.viewer-thumb');
    if (thumb) _openSharePhotoViewer(photos, parseInt(thumb.dataset.idx, 10));
  });
}

function _openSharePhotoViewer(photos, startIdx) {
  let idx = startIdx;
  let infoVisible = false;
  let zoom = 1;
  let panX = 0;
  let panY = 0;
  const MIN_ZOOM = 1;
  const MAX_ZOOM = 4;

  const overlay = document.createElement('div');
  overlay.className = 'spv-overlay';
  overlay.innerHTML = `
    <button class="spv-close" title="닫기">✕</button>
    <div class="spv-body">
      <button class="spv-nav spv-prev">‹</button>
      <img class="spv-img" src="" alt="">
      <div class="spv-info" style="display:none"></div>
      <button class="spv-nav spv-next">›</button>
    </div>
    <div class="spv-footer">
      <div class="spv-caption">
        <span class="spv-filename"></span>
        <span class="spv-counter"></span>
      </div>
      <div class="spv-actions">
        <a class="spv-btn" download>⬇ 다운로드</a>
        <button class="spv-btn spv-info-btn">i 정보</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);

  const imgEl      = overlay.querySelector('.spv-img');
  const bodyEl     = overlay.querySelector('.spv-body');
  const prevBtn    = overlay.querySelector('.spv-prev');
  const nextBtn    = overlay.querySelector('.spv-next');
  const filenameEl = overlay.querySelector('.spv-filename');
  const counterEl  = overlay.querySelector('.spv-counter');
  const dlBtn      = overlay.querySelector('.spv-btn[download]');
  const infoBtnEl  = overlay.querySelector('.spv-info-btn');
  const infoEl     = overlay.querySelector('.spv-info');

  // ── Zoom & Pan ──────────────────────────────────────────────

  function clampPan() {
    const maxX = Math.max(0, (imgEl.offsetWidth * zoom - bodyEl.offsetWidth) / 2);
    const maxY = Math.max(0, (imgEl.offsetHeight * zoom - bodyEl.offsetHeight) / 2);
    panX = Math.max(-maxX, Math.min(maxX, panX));
    panY = Math.max(-maxY, Math.min(maxY, panY));
  }

  function applyTransform() {
    imgEl.style.transform = zoom > 1 ? `translate(${panX}px, ${panY}px) scale(${zoom})` : '';
    imgEl.style.cursor = zoom > 1 ? 'grab' : '';
    prevBtn.style.visibility = (zoom <= 1 && idx > 0) ? 'visible' : 'hidden';
    nextBtn.style.visibility = (zoom <= 1 && idx < photos.length - 1) ? 'visible' : 'hidden';
  }

  function resetZoom() {
    zoom = MIN_ZOOM; panX = 0; panY = 0;
    applyTransform();
  }

  // Zoom toward screen point (ox, oy) = offset from body center in screen px
  function changeZoom(factor, ox = 0, oy = 0) {
    const newZoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, zoom * factor));
    if (newZoom === zoom) return;
    const scale = newZoom / zoom;
    panX = ox * (1 - scale) + panX * scale;
    panY = oy * (1 - scale) + panY * scale;
    zoom = newZoom;
    if (zoom <= MIN_ZOOM) { panX = 0; panY = 0; }
    clampPan();
    applyTransform();
  }

  // ── Middle click: reset zoom ────────────────────────────────
  bodyEl.addEventListener('mousedown', (e) => {
    if (e.button === 1) { e.preventDefault(); resetZoom(); }
  });

  // ── Mouse wheel zoom ────────────────────────────────────────
  bodyEl.addEventListener('wheel', (e) => {
    e.preventDefault();
    const rect = bodyEl.getBoundingClientRect();
    const ox = e.clientX - (rect.left + rect.width / 2);
    const oy = e.clientY - (rect.top + rect.height / 2);
    changeZoom(e.deltaY < 0 ? 1.2 : 1 / 1.2, ox, oy);
  }, { passive: false });

  // ── Double-click: toggle 2× / reset ────────────────────────
  imgEl.addEventListener('dblclick', (e) => {
    if (zoom > 1) {
      resetZoom();
    } else {
      const rect = bodyEl.getBoundingClientRect();
      const ox = e.clientX - (rect.left + rect.width / 2);
      const oy = e.clientY - (rect.top + rect.height / 2);
      changeZoom(2, ox, oy);
    }
  });

  // ── Mouse drag (pan when zoomed) ────────────────────────────
  let dragging = false;
  let dragPrev = null;

  imgEl.addEventListener('mousedown', (e) => {
    if (zoom <= 1) return;
    dragging = true;
    dragPrev = { x: e.clientX, y: e.clientY };
    imgEl.style.cursor = 'grabbing';
    e.preventDefault();
  });

  function onMouseMove(e) {
    if (!dragging) return;
    panX += e.clientX - dragPrev.x;
    panY += e.clientY - dragPrev.y;
    dragPrev = { x: e.clientX, y: e.clientY };
    clampPan();
    applyTransform();
  }

  function onMouseUp() {
    if (!dragging) return;
    dragging = false;
    dragPrev = null;
    if (zoom > 1) imgEl.style.cursor = 'grab';
  }

  document.addEventListener('mousemove', onMouseMove);
  document.addEventListener('mouseup', onMouseUp);

  // ── Touch: pinch zoom + single-finger pan ───────────────────
  let lastPinchDist = null;
  let lastPinchMid  = null;
  let lastTouchPos  = null;

  bodyEl.addEventListener('touchstart', (e) => {
    if (e.touches.length === 2) {
      lastPinchDist = Math.hypot(
        e.touches[0].clientX - e.touches[1].clientX,
        e.touches[0].clientY - e.touches[1].clientY
      );
      lastPinchMid = {
        x: (e.touches[0].clientX + e.touches[1].clientX) / 2,
        y: (e.touches[0].clientY + e.touches[1].clientY) / 2,
      };
      lastTouchPos = null;
    } else if (e.touches.length === 1 && zoom > 1) {
      lastTouchPos = { x: e.touches[0].clientX, y: e.touches[0].clientY };
      lastPinchDist = null;
    }
  }, { passive: true });

  bodyEl.addEventListener('touchmove', (e) => {
    if (e.touches.length === 2 && lastPinchDist !== null) {
      e.preventDefault();
      const dist = Math.hypot(
        e.touches[0].clientX - e.touches[1].clientX,
        e.touches[0].clientY - e.touches[1].clientY
      );
      const mid = {
        x: (e.touches[0].clientX + e.touches[1].clientX) / 2,
        y: (e.touches[0].clientY + e.touches[1].clientY) / 2,
      };
      const rect = bodyEl.getBoundingClientRect();
      const ox = mid.x - (rect.left + rect.width / 2);
      const oy = mid.y - (rect.top + rect.height / 2);
      changeZoom(dist / lastPinchDist, ox, oy);
      // Additional pan with midpoint translation
      panX += mid.x - lastPinchMid.x;
      panY += mid.y - lastPinchMid.y;
      clampPan();
      applyTransform();
      lastPinchDist = dist;
      lastPinchMid  = mid;
    } else if (e.touches.length === 1 && zoom > 1 && lastTouchPos) {
      e.preventDefault();
      panX += e.touches[0].clientX - lastTouchPos.x;
      panY += e.touches[0].clientY - lastTouchPos.y;
      lastTouchPos = { x: e.touches[0].clientX, y: e.touches[0].clientY };
      clampPan();
      applyTransform();
    }
  }, { passive: false });

  bodyEl.addEventListener('touchend', (e) => {
    if (e.touches.length < 2) { lastPinchDist = null; lastPinchMid = null; }
    if (e.touches.length === 0) lastTouchPos = null;
  }, { passive: true });

  // ── EXIF info formatter ─────────────────────────────────────

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

  // ── Photo display ───────────────────────────────────────────

  function show(i) {
    idx = i;
    const photo = photos[idx];
    imgEl.style.opacity = '0.4';
    imgEl.onload = () => { imgEl.style.opacity = '1'; };
    imgEl.src = photo.thumb_medium_url;
    filenameEl.textContent = photo.filename || '';
    counterEl.textContent = `${idx + 1} / ${photos.length}`;
    dlBtn.href = photo.url;
    dlBtn.download = photo.filename || 'photo.jpg';
    resetZoom();
    if (infoVisible) infoEl.innerHTML = formatInfo(photo);
  }

  function close() {
    document.removeEventListener('keydown', onKey);
    document.removeEventListener('mousemove', onMouseMove);
    document.removeEventListener('mouseup', onMouseUp);
    overlay.remove();
  }

  function onKey(e) {
    if (e.key === 'Escape') { close(); return; }
    if (zoom <= 1) {
      if (e.key === 'ArrowLeft'  && idx > 0) show(idx - 1);
      if (e.key === 'ArrowRight' && idx < photos.length - 1) show(idx + 1);
    }
    if (e.key === '+' || e.key === '=') changeZoom(1.3);
    if (e.key === '-') changeZoom(1 / 1.3);
    if (e.key === '0') resetZoom();
  }

  overlay.querySelector('.spv-close').addEventListener('click', close);
  prevBtn.addEventListener('click', () => show(idx - 1));
  nextBtn.addEventListener('click', () => show(idx + 1));
  document.addEventListener('keydown', onKey);

  infoBtnEl.addEventListener('click', () => {
    infoVisible = !infoVisible;
    if (infoVisible) {
      infoEl.innerHTML = formatInfo(photos[idx]);
      infoEl.style.display = 'flex';
      infoBtnEl.classList.add('active');
    } else {
      infoEl.style.display = 'none';
      infoBtnEl.classList.remove('active');
    }
  });

  show(startIdx);
}

function _initSettingsPanel(token, album) {
  const s = loadSlideshowSettings(album.slideshow_defaults || {}, token);

  document.getElementById('s-interval').value = s.interval;
  document.querySelector(`input[name="s-order"][value="${s.order}"]`).checked = true;
  document.querySelector(`input[name="s-music"][value="${s.music ? 'on' : 'off'}"]`).checked = true;
  document.querySelector(`input[name="s-loop"][value="${s.loop ? 'on' : 'off'}"]`).checked = true;
  document.getElementById('s-volume').value = s.volume;
  document.getElementById('s-volume-label').textContent = `${s.volume}%`;
  document.getElementById('s-effect').value = s.effect;

  document.getElementById('s-volume').addEventListener('input', (e) => {
    document.getElementById('s-volume-label').textContent = `${e.target.value}%`;
  });

  document.getElementById('btn-cancel').addEventListener('click', () => {
    document.getElementById('settings-overlay').style.display = 'none';
  });

  document.getElementById('btn-start').addEventListener('click', () => {
    saveSettings(token, {
      interval: parseInt(document.getElementById('s-interval').value, 10) || 5,
      order: document.querySelector('input[name="s-order"]:checked').value,
      music: document.querySelector('input[name="s-music"]:checked').value === 'on',
      loop: document.querySelector('input[name="s-loop"]:checked').value === 'on',
      volume: parseInt(document.getElementById('s-volume').value, 10),
      effect: document.getElementById('s-effect').value,
    });
    document.getElementById('settings-overlay').style.display = 'none';
    window.navigate(`/s/${token}/slideshow`);
  });

  document.getElementById('settings-overlay').addEventListener('click', (e) => {
    if (e.target === e.currentTarget) e.currentTarget.style.display = 'none';
  });
}

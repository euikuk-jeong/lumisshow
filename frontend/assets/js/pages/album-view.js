import { shareApi, ShareAuthError } from '../api.js';
import { esc, getVersion } from '../utils.js';
import { EFFECTS, EFFECT_LABELS, loadSlideshowSettings } from '../slideshow-config.js';
import { startedInEdgeZone, resolveSwipeDirection, clampDragOffset } from '../touch-gesture.js';

function saveSettings(token, s) {
  localStorage.setItem(`slideshow_settings_${token}`, JSON.stringify(s));
}

// "간단히 보기" 체크박스는 기억되는 설정이 아니라 뷰 화면 진입할 때마다 항상
// 언체크로 시작하는 1회성 선택 — 체크 상태를 슬라이드쇼 URL에 실어 보내기만 한다.
function withLowPower(path) {
  const checked = document.getElementById('chk-lowpower')?.checked;
  if (!checked) return path;
  return path + (path.includes('?') ? '&' : '?') + 'lp=1';
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
          <span>📷 ${album.photo_count.toLocaleString()}장</span>
          <span>📅 ${new Date(album.created_at).toLocaleDateString('ko-KR')}</span>
          ${expiryHtml}
          ${album.has_music ? '<span>🎵 음악 있음</span>' : ''}
        </div>
        <div class="viewer-actions">
          <button class="btn btn-primary btn-lg" id="btn-slideshow">▶ 슬라이드쇼</button>
          <button class="btn btn-ghost btn-lg" id="btn-settings">⚙ 설정</button>
          <label class="viewer-lowpower-check" title="느리거나 오래된 TV 등에서 재생이 버벅일 때 체크하세요.">
            <input type="checkbox" id="chk-lowpower">
            간단히 보기
          </label>
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
    window.navigate(withLowPower(`/s/${token}/slideshow`));
  });
  document.getElementById('btn-settings').addEventListener('click', () => {
    document.getElementById('settings-overlay').style.display = 'flex';
  });

  document.getElementById('thumb-grid')?.addEventListener('click', (e) => {
    const thumb = e.target.closest('.viewer-thumb');
    if (thumb) _openSharePhotoViewer(token, photos, parseInt(thumb.dataset.idx, 10));
  });
}

function _openSharePhotoViewer(token, photos, startIdx) {
  let idx = startIdx;
  let infoVisible = false;
  let zoom = 1;
  let panX = 0;
  let panY = 0;
  let swipeX = 0;     // 스와이프 드래그 중 현재 사진의 X 오프셋(px)
  let settling = false; // 스와이프 완료/취소 애니메이션 진행 중 여부
  const MIN_ZOOM = 1;
  const MAX_ZOOM = 4;

  const overlay = document.createElement('div');
  overlay.className = 'spv-overlay';
  overlay.innerHTML = `
    <button class="spv-close" title="닫기">✕</button>
    <div class="spv-body">
      <button class="spv-nav spv-prev">‹</button>
      <img class="spv-peek-img spv-peek-prev" alt="">
      <img class="spv-img" src="" alt="">
      <img class="spv-peek-img spv-peek-next" alt="">
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
        <button class="spv-btn spv-ss-btn">▶ 슬라이드쇼</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);

  const imgEl      = overlay.querySelector('.spv-img');
  const peekPrevEl = overlay.querySelector('.spv-peek-prev');
  const peekNextEl = overlay.querySelector('.spv-peek-next');
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
    imgEl.style.transform = zoom > 1
      ? `translate(-50%, -50%) translate(${panX}px, ${panY}px) scale(${zoom})`
      : `translate(-50%, -50%) translateX(${swipeX}px)`;
    imgEl.style.cursor = zoom > 1 ? 'grab' : '';
    updatePeekTransforms();
    prevBtn.style.visibility = (zoom <= 1 && idx > 0) ? 'visible' : 'hidden';
    nextBtn.style.visibility = (zoom <= 1 && idx < photos.length - 1) ? 'visible' : 'hidden';
  }

  // 이전/다음 미리보기 이미지를 화면 밖(±bodyWidth)에 대기시켜 두었다가
  // swipeX만큼 같이 이동시켜 드래그를 따라오는 것처럼 보이게 한다.
  function updatePeekTransforms() {
    const bodyWidth = bodyEl.offsetWidth;
    peekPrevEl.style.transform = `translate(-50%, -50%) translateX(${swipeX - bodyWidth}px)`;
    peekNextEl.style.transform = `translate(-50%, -50%) translateX(${swipeX + bodyWidth}px)`;
  }

  function resetZoom() {
    zoom = MIN_ZOOM; panX = 0; panY = 0; swipeX = 0;
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

  // ── Touch: pinch zoom + single-finger pan + swipe navigate (zoom=1) ──
  // 스와이프는 화면 가장자리(SWIPE_EDGE_EXCLUDE_PX 이내)에서 시작하면 무시한다.
  // iOS는 그 영역을 뒤로가기 제스처 전용으로 예약해 두어 preventDefault로도 못 막으므로,
  // 해당 영역 밖에서 시작한 좌우 드래그만 이전/다음 사진 이동으로 처리한다.
  let lastPinchDist = null;
  let lastPinchMid  = null;
  let lastTouchPos  = null;
  let swipeStart    = null;

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
      swipeStart = null;
    } else if (e.touches.length === 1 && zoom > 1) {
      lastTouchPos = { x: e.touches[0].clientX, y: e.touches[0].clientY };
      lastPinchDist = null;
      swipeStart = null;
    } else if (e.touches.length === 1 && !settling) {
      const rect = bodyEl.getBoundingClientRect();
      swipeStart = {
        x: e.touches[0].clientX,
        y: e.touches[0].clientY,
        t: Date.now(),
        // 시작 시점에 한 번만 판정 — 가장자리에서 시작한 드래그는 따라오는 시늉조차 하지 않는다.
        // (도중에만 취소되면 끝까지 드래그해도 항상 스냅백되는 것처럼 보여 혼란스럽다)
        edge: startedInEdgeZone(e.touches[0].clientX, rect.left, rect.right),
      };
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
    } else if (e.touches.length === 1 && zoom <= 1 && swipeStart && !settling && !swipeStart.edge) {
      const dx = e.touches[0].clientX - swipeStart.x;
      swipeX = clampDragOffset(dx, { hasPrev: idx > 0, hasNext: idx < photos.length - 1 });
      applyTransform();
    }
  }, { passive: false });

  bodyEl.addEventListener('touchend', (e) => {
    if (e.touches.length < 2) { lastPinchDist = null; lastPinchMid = null; }
    if (e.touches.length === 0) lastTouchPos = null;

    if (swipeStart && e.touches.length === 0 && zoom <= 1) {
      const endTouch = e.changedTouches[0];
      const dx = endTouch.clientX - swipeStart.x;
      const dy = endTouch.clientY - swipeStart.y;
      let dir = resolveSwipeDirection({ dx, dy, startedInEdge: swipeStart.edge });
      if (dir === 1 && idx >= photos.length - 1) dir = 0;
      if (dir === -1 && idx <= 0) dir = 0;
      settleSwipe(dir);
    }
    swipeStart = null;
  }, { passive: true });

  // 스와이프 판정(dir: 1=다음, -1=이전, 0=취소) 이후 화면 밖까지 슬라이드하거나
  // 원위치로 되돌아가는 애니메이션을 재생한 뒤 실제 사진 전환을 적용한다.
  function settleSwipe(dir) {
    const bodyWidth = bodyEl.offsetWidth;
    const targetX = dir === 1 ? -bodyWidth : dir === -1 ? bodyWidth : 0;
    if (Math.round(swipeX) === Math.round(targetX)) {
      finishSwipe(dir);
      return;
    }
    settling = true;
    const els = [imgEl, peekPrevEl, peekNextEl];
    els.forEach(el => el.classList.add('spv-snapping'));
    swipeX = targetX;
    applyTransform();

    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      clearTimeout(fallbackTimer);
      imgEl.removeEventListener('transitionend', onTransitionEnd);
      els.forEach(el => el.classList.remove('spv-snapping'));
      settling = false;
      finishSwipe(dir);
    };
    // transitionend는 opacity/transform 등 속성별로 각각 발생하므로 transform 전환이
    // imgEl에서 끝난 경우만 받는다 — 그렇지 않으면 슬라이드가 끝나기 전에 조기 커밋된다.
    const onTransitionEnd = (e) => {
      if (e.target !== imgEl || e.propertyName !== 'transform') return;
      finish();
    };
    imgEl.addEventListener('transitionend', onTransitionEnd);
    // 탭 백그라운드 등으로 transitionend가 아예 발생하지 않는 경우를 대비한 안전망
    // (없으면 settling이 true로 고정돼 이후 스와이프가 영구히 먹통이 된다)
    const fallbackTimer = setTimeout(finish, 350);
  }

  // 스와이프로 완료된 사진 전환: 새 이미지가 실제로 로드된 뒤에만 swipeX를 되돌린다.
  // 다음/이전 사진은 이미 peek 이미지로 화면에 보이고 있으므로, 로드 전에 먼저
  // 위치를 리셋해버리면 아직 안 뜬 이전 사진이 잠깐 다시 보이는 깜빡임이 생긴다.
  function commitSwipe(newIdx) {
    const photo = photos[newIdx];
    imgEl.addEventListener('load', () => {
      idx = newIdx;
      swipeX = 0;
      zoom = MIN_ZOOM; panX = 0; panY = 0;
      applyTransform();
      peekPrevEl.src = idx > 0 ? photos[idx - 1].url : '';
      peekNextEl.src = idx < photos.length - 1 ? photos[idx + 1].url : '';
      filenameEl.textContent = photo.filename || '';
      counterEl.textContent = `${(idx + 1).toLocaleString()} / ${photos.length.toLocaleString()}`;
      dlBtn.href = photo.url;
      dlBtn.download = photo.filename || 'photo.jpg';
      if (infoVisible) infoEl.innerHTML = formatInfo(photo);
    }, { once: true });
    imgEl.src = photo.url;
  }

  function finishSwipe(dir) {
    if (dir === 1 && idx < photos.length - 1) commitSwipe(idx + 1);
    else if (dir === -1 && idx > 0) commitSwipe(idx - 1);
    else { swipeX = 0; applyTransform(); }
  }

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
    imgEl.src = photo.url;
    peekPrevEl.src = idx > 0 ? photos[idx - 1].url : '';
    peekNextEl.src = idx < photos.length - 1 ? photos[idx + 1].url : '';
    filenameEl.textContent = photo.filename || '';
    counterEl.textContent = `${(idx + 1).toLocaleString()} / ${photos.length.toLocaleString()}`;
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
    if (window._pageCleanup === close) window._pageCleanup = null;
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
  // SPA 네비게이션 시 뷰어가 닫히지 않고 잔존하는 문제 방지 (router.js renderRoute)
  window._pageCleanup = close;

  overlay.querySelector('.spv-ss-btn').addEventListener('click', () => {
    close();
    window.navigate(withLowPower(`/s/${token}/slideshow?i=${idx}`));
  });

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

  function resetToSaved() {
    document.getElementById('s-interval').value = s.interval;
    document.querySelector(`input[name="s-order"][value="${s.order}"]`).checked = true;
    document.querySelector(`input[name="s-music"][value="${s.music ? 'on' : 'off'}"]`).checked = true;
    document.querySelector(`input[name="s-loop"][value="${s.loop ? 'on' : 'off'}"]`).checked = true;
    document.getElementById('s-volume').value = s.volume;
    document.getElementById('s-volume-label').textContent = `${s.volume}%`;
    document.getElementById('s-effect').value = s.effect;
  }

  document.getElementById('btn-cancel').addEventListener('click', () => {
    resetToSaved();
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
    window.navigate(withLowPower(`/s/${token}/slideshow`));
  });

  document.getElementById('settings-overlay').addEventListener('click', (e) => {
    if (e.target === e.currentTarget) {
      resetToSaved();
      e.currentTarget.style.display = 'none';
    }
  });
}

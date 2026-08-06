import { shareApi, ShareAuthError } from '../api.js';
import { esc, getVersion, getSiteTitle } from '../utils.js';
import { EFFECTS, EFFECT_LABELS, loadSlideshowSettings } from '../slideshow-config.js';
import { createPhotoZoomViewer } from '../photo-zoom-viewer.js';

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
  Promise.all([getSiteTitle(), getVersion()]).then(([title, v]) => {
    const el = document.getElementById('viewer-version');
    if (el) el.textContent = `${title} ${v} · Made by Ekjeong`;
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

  // ── 확대/이동/스와이프 (Admin 라이트박스와 공용 — photo-zoom-viewer.js) ──
  const zoomViewer = createPhotoZoomViewer({
    bodyEl, imgEl, peekPrevEl, peekNextEl,
    getUrl: i => photos[i] ? photos[i].url : null,
    getCount: () => photos.length,
    getIndex: () => idx,
    onIndexChanged: afterShow,
    // 확대 중에는 이전/다음 버튼이 팬 조작을 가리지 않도록 숨긴다(기존 공유뷰어 동작 유지)
    onZoomChange: zoom => {
      zoomedIn = zoom > 1;
      prevBtn.style.visibility = (zoom <= 1 && idx > 0) ? 'visible' : 'hidden';
      nextBtn.style.visibility = (zoom <= 1 && idx < photos.length - 1) ? 'visible' : 'hidden';
    },
  });

  // ── EXIF info formatter ─────────────────────────────────────

  function rowsToHtml(rows) {
    return rows.map(([l, v]) =>
      `<div class="ss-info-row"><span class="ss-info-label">${esc(l)}</span><span class="ss-info-value">${esc(v)}</span></div>`
    ).join('');
  }

  function formatInfo(photo) {
    const exifRows = [];
    const add = (label, value) => { if (value != null && value !== '') exifRows.push([label, String(value)]); };
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

    // 태그 — 백엔드가 뷰어별로 노출 가능한 source만 채워 보내므로(공유 링크는
    // person_tags/location_tags가 항상 빈 배열) 프론트에서 재분기하지 않는다.
    const tagRows = [];
    const addList = (label, list) => { if (list && list.length) tagRows.push([label, list.join(', ')]); };
    addList('인물', photo.person_tags);
    addList('위치', photo.location_tags);
    addList('태그', photo.ai_tags);
    addList('폴더명', photo.path_tags);
    addList('직접 추가', photo.manual_tags);

    const exifHtml = rowsToHtml(exifRows);
    if (!tagRows.length) return exifHtml;
    return `${exifHtml}<div class="ss-info-divider"></div><div class="ss-info-section">🏷 태그</div>${rowsToHtml(tagRows)}`;
  }

  // ── Photo display ───────────────────────────────────────────

  // 이미지 로드 완료 후 photo-zoom-viewer.js가 호출 — 캡션/버튼/정보패널 등 idx 종속 UI 갱신
  function afterShow(i) {
    idx = i;
    const photo = photos[idx];
    filenameEl.textContent = photo.filename || '';
    counterEl.textContent = `${(idx + 1).toLocaleString()} / ${photos.length.toLocaleString()}`;
    dlBtn.href = photo.url;
    dlBtn.download = photo.filename || 'photo.jpg';
    if (infoVisible) infoEl.innerHTML = formatInfo(photo);
  }

  const show = i => zoomViewer.goTo(i);

  // 확대 중에는 화살표 키 이동을 막는다(먼저 줌을 리셋해야 넘어감) — onZoomChange에서 갱신
  let zoomedIn = false;

  function close() {
    document.removeEventListener('keydown', onKey);
    overlay.remove();
    if (window._pageCleanup === close) window._pageCleanup = null;
  }

  function onKey(e) {
    if (e.key === 'Escape') { close(); return; }
    if (e.target.closest('input, textarea') || e.isComposing) return;
    if (!zoomedIn) {
      if (e.key === 'ArrowLeft'  && idx > 0) show(idx - 1);
      if (e.key === 'ArrowRight' && idx < photos.length - 1) show(idx + 1);
    }
    if (e.key === '+' || e.key === '=') zoomViewer.changeZoom(1.3);
    if (e.key === '-') zoomViewer.changeZoom(1 / 1.3);
    if (e.key === '0') zoomViewer.resetZoom();
    if (e.key === 'i' || e.key === 'I') infoBtnEl.click();
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

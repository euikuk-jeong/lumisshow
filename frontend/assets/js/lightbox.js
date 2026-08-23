/**
 * options (모두 선택적):
 *   isCover(path)          → boolean   현재 커버 여부
 *   onSetCover(path)       → Promise   커버 설정 콜백
 *   onDelete(path)         → Promise   삭제 콜백 (라이트박스 내 사진 제거)
 *   deleteLabel            → string    삭제 버튼 텍스트 (기본 '앨범에서 삭제')
 *   deleteConfirmMsg       → string    삭제 확인 메시지 (기본 '이 사진을 앨범에서 제외하시겠습니까?')
 *   getSelectionState(path)→ { isSelected, selectedCount, totalCount }
 *   onToggleSelect(path)   → void      선택 토글 콜백
 *   extraAction            → { label, onClick(path) }  범용 추가 버튼(삭제/커버가 아닌
 *                             동작용, 예: 태그 관리 화면의 "+ 태그 추가"). onClick은
 *                             자체적으로 로딩/에러 처리를 책임진다(delete/cover처럼
 *                             공통 disable·에러 alert 래핑을 하지 않음 — 버튼을 다시
 *                             누를 수 있는 채로 두는 게 태그 추가 같은 반복 동작에 더 맞음).
 */
import { api } from './api.js';
import { createPhotoZoomViewer } from './photo-zoom-viewer.js';
import { esc } from './utils.js';
import { EXIF_LABELS } from './exif-labels.js';

// backend/services/thumbnail.py의 VIDEO_EXTENSIONS와 동기 유지 필요(컨테이너 분리로
// 코드 공유 불가 — admin_browse.py의 _AUDIO_EXTENSIONS와 동일한 이유).
const VIDEO_EXTENSIONS = new Set(['.mp4', '.mov', '.webm', '.m4v']);

function isVideoPath(path) {
  const dot = path.lastIndexOf('.');
  if (dot === -1) return false;
  return VIDEO_EXTENSIONS.has(path.slice(dot).toLowerCase());
}

export function openLightbox(paths, startIdx, options = {}) {
  const localPaths = [...paths];
  let idx = startIdx;
  let currentIsVideo = false;

  const hasSelection = !!options.getSelectionState;

  const overlay = document.createElement('div');
  overlay.className = 'lightbox-overlay';
  overlay.innerHTML = `
    <button class="lightbox-close" title="닫기">✕</button>
    <div class="lightbox-body">
      <button class="lightbox-nav lightbox-prev">‹</button>
      <img class="lightbox-peek-img lightbox-peek-prev" alt="">
      <img class="lightbox-img" src="" alt="">
      <video class="lightbox-video" controls style="display:none"></video>
      <img class="lightbox-peek-img lightbox-peek-next" alt="">
      <div class="lightbox-info" id="lb-info" style="display:none"></div>
      <button class="lightbox-nav lightbox-next">›</button>
    </div>
    <div class="lightbox-footer">
      <div class="lightbox-caption"></div>
      ${hasSelection ? `<div class="lightbox-sel-area">
        <button class="lightbox-action-btn" id="lb-btn-select"></button>
        <span class="lb-sel-count" id="lb-sel-count"></span>
      </div>` : ''}
      <div class="lightbox-actions">
        <button class="lightbox-action-btn" id="lb-btn-info">정보보기</button>
        ${options.onSetCover  ? '<button class="lightbox-action-btn" id="lb-btn-cover">커버로 설정</button>' : ''}
        ${options.extraAction ? `<button class="lightbox-action-btn" id="lb-btn-extra">${options.extraAction.label}</button>` : ''}
        ${options.onDelete    ? `<button class="lightbox-action-btn lightbox-action-danger" id="lb-btn-delete">${options.deleteLabel || '앨범에서 삭제'}</button>` : ''}
      </div>
    </div>`;
  document.body.appendChild(overlay);

  const bodyEl     = overlay.querySelector('.lightbox-body');
  const imgEl      = overlay.querySelector('.lightbox-img');
  const videoEl    = overlay.querySelector('.lightbox-video');
  const peekPrevEl = overlay.querySelector('.lightbox-peek-prev');
  const peekNextEl = overlay.querySelector('.lightbox-peek-next');
  const captionEl  = overlay.querySelector('.lightbox-caption');
  const infoBtn    = overlay.querySelector('#lb-btn-info');
  const infoEl     = overlay.querySelector('#lb-info');

  // ── 정보 패널 (정보보기 버튼: EXIF·태그, person/location 포함 — Admin 전용) ──
  // 매번 새로 조회한다(캐싱 안 함) — admin-tags.js의 "+ 태그 추가"(extraAction)로
  // 패널이 열린 채 태그를 바꿀 수 있어, 캐시를 두면 갱신 후에도 이전 태그 목록이
  // 계속 보이는 문제가 생긴다.
  let infoVisible = false;

  function rowsToHtml(rows) {
    return rows.map(([l, v]) =>
      `<div class="lightbox-info-row"><span class="lightbox-info-label">${esc(l)}</span><span class="lightbox-info-value">${esc(v)}</span></div>`
    ).join('');
  }

  function formatInfo(info, path) {
    const exifRows = [];
    const add = (label, value) => { if (value != null && value !== '') exifRows.push([label, String(value)]); };

    add(EXIF_LABELS.filename, info.filename);
    const slashIdx = path.lastIndexOf('/');
    if (slashIdx > 0) add('경로', path.slice(0, slashIdx));
    if (info.taken_at) {
      const d = new Date(info.taken_at);
      const pad = n => String(n).padStart(2, '0');
      add(EXIF_LABELS.date, `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`);
    }
    if (info.width && info.height) add(EXIF_LABELS.resolution, `${info.width} × ${info.height}`);
    add(EXIF_LABELS.make, info.make);
    add(EXIF_LABELS.camera, info.camera);
    add(EXIF_LABELS.software, info.software);
    add(EXIF_LABELS.shootMode, info.shoot_mode);
    add(EXIF_LABELS.exposure, info.shutter);
    add(EXIF_LABELS.aperture, info.aperture);
    add(EXIF_LABELS.iso, info.iso);
    add(EXIF_LABELS.focalLength, info.focal_length);
    add(EXIF_LABELS.flash, info.flash);
    add(EXIF_LABELS.metering, info.metering);
    add(EXIF_LABELS.exposureMode, info.exposure_mode);

    const tagRows = [];
    const addList = (label, list) => { if (list && list.length) tagRows.push([label, list.join(', ')]); };
    addList('인물', info.person_tags);
    addList('위치', info.location_tags);
    addList('태그', info.ai_tags);
    addList('폴더명', info.path_tags);
    addList('직접 추가', info.manual_tags);

    const exifHtml = rowsToHtml(exifRows);
    if (!tagRows.length) return exifHtml;
    return `${exifHtml}<div class="lightbox-info-divider"></div><div class="lightbox-info-section">🏷 태그</div>${rowsToHtml(tagRows)}`;
  }

  async function refreshInfoPanel() {
    if (!infoVisible) return;
    const path = localPaths[idx];
    infoEl.innerHTML = '<div class="lightbox-info-loading">불러오는 중…</div>';
    try {
      const info = await api.get(`/api/admin/photo-info?path=${encodeURIComponent(path)}`);
      if (!infoVisible || localPaths[idx] !== path) return; // 패널이 닫혔거나 다른 사진으로 이동한 뒤 도착한 응답은 버림
      infoEl.innerHTML = formatInfo(info, path);
    } catch (err) {
      if (!infoVisible || localPaths[idx] !== path) return;
      infoEl.innerHTML = '<div class="lightbox-info-error">정보를 불러오지 못했습니다.</div>';
    }
  }

  infoBtn.addEventListener('click', () => {
    infoVisible = !infoVisible;
    infoEl.style.display = infoVisible ? 'block' : 'none';
    infoBtn.classList.toggle('lb-selected', infoVisible);
    if (infoVisible) refreshInfoPanel();
  });

  // ── 확대/이동/스와이프 (공유뷰어와 공용 — photo-zoom-viewer.js) ──
  const zoomViewer = createPhotoZoomViewer({
    bodyEl, imgEl, peekPrevEl, peekNextEl,
    getUrl: i => localPaths[i] != null ? `/api/admin/photo?path=${encodeURIComponent(localPaths[i])}` : null,
    getCount: () => localPaths.length,
    getIndex: () => idx,
    onIndexChanged: afterShow,
    scrollableSelector: '.lightbox-info',
    // 동영상 표시 중엔 줌/팬/스와이프 제스처 엔진을 끈다(동영상은 대상 아님 —
    // photo-zoom-viewer.js 헤더 주석 참고).
    isEnabled: () => !currentIsVideo,
  });

  const prevBtn   = overlay.querySelector('.lightbox-prev');
  const nextBtn   = overlay.querySelector('.lightbox-next');
  const coverBtn  = overlay.querySelector('#lb-btn-cover');
  const deleteBtn = overlay.querySelector('#lb-btn-delete');
  const extraBtn  = overlay.querySelector('#lb-btn-extra');
  const selBtn    = overlay.querySelector('#lb-btn-select');
  const selCountEl = overlay.querySelector('#lb-sel-count');

  function updateSelectionUI() {
    if (!selBtn || !options.getSelectionState) return;
    const { isSelected, selectedCount, totalCount } = options.getSelectionState(localPaths[idx]);
    selBtn.textContent = isSelected ? '✓ 선택됨' : '선택';
    selBtn.classList.toggle('lb-selected', isSelected);
    if (selCountEl) selCountEl.textContent = `(${selectedCount.toLocaleString()}/${totalCount.toLocaleString()})`;
  }

  // 이미지 로드 완료 후 photo-zoom-viewer.js가 호출 — 캡션/버튼 등 idx 종속 UI 갱신
  function afterShow(i) {
    idx = i;
    captionEl.textContent = `${localPaths[i].split('/').pop()}  (${(i + 1).toLocaleString()} / ${localPaths.length.toLocaleString()})`;
    prevBtn.style.visibility = i > 0 ? 'visible' : 'hidden';
    nextBtn.style.visibility = i < localPaths.length - 1 ? 'visible' : 'hidden';
    if (coverBtn && options.isCover) {
      // 동영상은 커버(정적 이미지)로 지정할 수 없다 — album_photos.media_type이
      // 'video'인 경로가 albums.cover_path에 들어가면 공유뷰어 cover_index 계산이
      // (사진만 대상) 매칭 실패해 첫 번째 사진으로 조용히 폴백해버리는 문제가 있었음.
      coverBtn.style.display = currentIsVideo ? 'none' : '';
      if (!currentIsVideo) {
        const isCurrent = options.isCover(localPaths[i]);
        coverBtn.textContent = isCurrent ? '현재 커버' : '커버로 설정';
        coverBtn.disabled = isCurrent;
      }
    }
    updateSelectionUI();
    refreshInfoPanel();
  }

  function show(i) {
    const path = localPaths[i];
    if (isVideoPath(path)) {
      currentIsVideo = true;
      imgEl.style.display = 'none';
      if (peekPrevEl) peekPrevEl.style.display = 'none';
      if (peekNextEl) peekNextEl.style.display = 'none';
      videoEl.style.display = '';
      videoEl.src = `/api/admin/photo?path=${encodeURIComponent(path)}`;
      idx = i;
      afterShow(i);
      return;
    }
    if (currentIsVideo) {
      currentIsVideo = false;
      videoEl.pause();
      videoEl.removeAttribute('src');
      videoEl.load();
      videoEl.style.display = 'none';
      imgEl.style.display = '';
      if (peekPrevEl) peekPrevEl.style.display = '';
      if (peekNextEl) peekNextEl.style.display = '';
    }
    zoomViewer.goTo(i);
  }

  let closed = false;
  function close() {
    if (closed) return;
    closed = true;
    videoEl.pause();
    document.removeEventListener('keydown', onKey);
    overlay.remove();
    if (window._pageCleanup === close) window._pageCleanup = null;
  }

  function onKey(e) {
    if (e.key === 'Escape') { close(); return; }
    if (e.target.closest('input, textarea') || e.isComposing) return;
    if (e.key === 'ArrowLeft'  && idx > 0) show(idx - 1);
    if (e.key === 'ArrowRight' && idx < localPaths.length - 1) show(idx + 1);
    if (e.key === '+' || e.key === '=') zoomViewer.changeZoom(1.3);
    if (e.key === '-') zoomViewer.changeZoom(1 / 1.3);
    if (e.key === '0') zoomViewer.resetZoom();
    if (e.key === 'i' || e.key === 'I') infoBtn.click();
  }

  overlay.querySelector('.lightbox-close').addEventListener('click', close);
  prevBtn.addEventListener('click', () => show(idx - 1));
  nextBtn.addEventListener('click', () => show(idx + 1));
  document.addEventListener('keydown', onKey);
  // SPA 네비게이션 시 라이트박스가 닫히지 않고 잔존하는 문제 방지 (router.js renderRoute)
  window._pageCleanup = close;

  if (selBtn && options.onToggleSelect) {
    selBtn.addEventListener('click', () => {
      options.onToggleSelect(localPaths[idx]);
      updateSelectionUI();
    });
  }

  if (coverBtn) {
    coverBtn.addEventListener('click', async () => {
      coverBtn.disabled = true;
      try {
        await options.onSetCover(localPaths[idx]);
        if (options.isCover) {
          coverBtn.textContent = options.isCover(localPaths[idx]) ? '현재 커버' : '커버로 설정';
          coverBtn.disabled = options.isCover(localPaths[idx]);
        }
      } catch (err) {
        alert(err.message);
        coverBtn.disabled = false;
      }
    });
  }

  if (deleteBtn) {
    deleteBtn.addEventListener('click', async () => {
      if (!confirm(options.deleteConfirmMsg || '이 사진을 앨범에서 제외하시겠습니까?')) return;
      deleteBtn.disabled = true;
      const path = localPaths[idx];
      try {
        await options.onDelete(path);
        localPaths.splice(idx, 1);
        if (localPaths.length === 0) {
          close();
        } else {
          if (idx >= localPaths.length) idx = localPaths.length - 1;
          show(idx);
          deleteBtn.disabled = false;
        }
      } catch (err) {
        alert(err.message);
        deleteBtn.disabled = false;
      }
    });
  }

  if (extraBtn) {
    extraBtn.addEventListener('click', () => options.extraAction.onClick(localPaths[idx]));
  }

  show(startIdx);
}

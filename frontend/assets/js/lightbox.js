/**
 * options (모두 선택적):
 *   isCover(path)          → boolean   현재 커버 여부
 *   onSetCover(path)       → Promise   커버 설정 콜백
 *   onDelete(path)         → Promise   삭제 콜백 (라이트박스 내 사진 제거)
 *   getSelectionState(path)→ { isSelected, selectedCount, totalCount }
 *   onToggleSelect(path)   → void      선택 토글 콜백
 */
export function openLightbox(paths, startIdx, options = {}) {
  const localPaths = [...paths];
  let idx = startIdx;

  const hasActions   = options.onSetCover || options.onDelete;
  const hasSelection = !!options.getSelectionState;
  const hasFooter    = hasActions || hasSelection;

  const overlay = document.createElement('div');
  overlay.className = 'lightbox-overlay';
  overlay.innerHTML = `
    <button class="lightbox-close" title="닫기">✕</button>
    <button class="lightbox-nav lightbox-prev">‹</button>
    <div class="lightbox-body">
      <img class="lightbox-img" src="" alt="">
      <div class="lightbox-caption"></div>
      ${hasFooter ? `<div class="lightbox-footer">
        ${hasSelection ? `<div class="lightbox-sel-area">
          <button class="lightbox-action-btn" id="lb-btn-select"></button>
          <span class="lb-sel-count" id="lb-sel-count"></span>
        </div>` : '<div></div>'}
        ${hasActions ? `<div class="lightbox-actions">
          ${options.onSetCover ? '<button class="lightbox-action-btn" id="lb-btn-cover">커버로 설정</button>' : ''}
          ${options.onDelete   ? '<button class="lightbox-action-btn lightbox-action-danger" id="lb-btn-delete">앨범에서 삭제</button>' : ''}
        </div>` : ''}
      </div>` : ''}
    </div>
    <button class="lightbox-nav lightbox-next">›</button>`;
  document.body.appendChild(overlay);

  const imgEl     = overlay.querySelector('.lightbox-img');
  const captionEl = overlay.querySelector('.lightbox-caption');
  const prevBtn   = overlay.querySelector('.lightbox-prev');
  const nextBtn   = overlay.querySelector('.lightbox-next');
  const coverBtn  = overlay.querySelector('#lb-btn-cover');
  const deleteBtn = overlay.querySelector('#lb-btn-delete');
  const selBtn    = overlay.querySelector('#lb-btn-select');
  const selCountEl = overlay.querySelector('#lb-sel-count');

  function updateSelectionUI() {
    if (!selBtn || !options.getSelectionState) return;
    const { isSelected, selectedCount, totalCount } = options.getSelectionState(localPaths[idx]);
    selBtn.textContent = isSelected ? '✓ 선택됨' : '선택';
    selBtn.classList.toggle('lb-selected', isSelected);
    if (selCountEl) selCountEl.textContent = `(${selectedCount}/${totalCount})`;
  }

  function show(i) {
    idx = i;
    imgEl.style.opacity = '0.4';
    imgEl.onload = () => { imgEl.style.opacity = '1'; };
    imgEl.src = `/api/admin/thumb?path=${encodeURIComponent(localPaths[i])}&size=medium`;
    captionEl.textContent = `${localPaths[i].split('/').pop()}  (${i + 1} / ${localPaths.length})`;
    prevBtn.style.visibility = i > 0 ? 'visible' : 'hidden';
    nextBtn.style.visibility = i < localPaths.length - 1 ? 'visible' : 'hidden';
    if (coverBtn && options.isCover) {
      const isCurrent = options.isCover(localPaths[i]);
      coverBtn.textContent = isCurrent ? '현재 커버' : '커버로 설정';
      coverBtn.disabled = isCurrent;
    }
    updateSelectionUI();
  }

  let closed = false;
  function close() {
    if (closed) return;
    closed = true;
    document.removeEventListener('keydown', onKey);
    overlay.remove();
  }

  function onKey(e) {
    if (e.key === 'Escape') close();
    if (e.key === 'ArrowLeft'  && idx > 0) show(idx - 1);
    if (e.key === 'ArrowRight' && idx < localPaths.length - 1) show(idx + 1);
  }

  overlay.querySelector('.lightbox-close').addEventListener('click', close);
  overlay.addEventListener('click', e => { if (e.target === overlay) close(); });
  prevBtn.addEventListener('click', () => show(idx - 1));
  nextBtn.addEventListener('click', () => show(idx + 1));
  document.addEventListener('keydown', onKey);

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
      if (!confirm('이 사진을 앨범에서 제외하시겠습니까?')) return;
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

  show(startIdx);
}

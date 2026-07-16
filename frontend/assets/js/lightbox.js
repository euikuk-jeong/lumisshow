/**
 * options (모두 선택적):
 *   isCover(path)          → boolean   현재 커버 여부
 *   onSetCover(path)       → Promise   커버 설정 콜백
 *   onDelete(path)         → Promise   삭제 콜백 (라이트박스 내 사진 제거)
 *   deleteLabel            → string    삭제 버튼 텍스트 (기본 '앨범에서 삭제')
 *   deleteConfirmMsg       → string    삭제 확인 메시지 (기본 '이 사진을 앨범에서 제외하시겠습니까?')
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
          ${options.onDelete   ? `<button class="lightbox-action-btn lightbox-action-danger" id="lb-btn-delete">${options.deleteLabel || '앨범에서 삭제'}</button>` : ''}
        </div>` : ''}
      </div>` : ''}
    </div>
    <button class="lightbox-nav lightbox-next">›</button>`;
  document.body.appendChild(overlay);

  const imgEl     = overlay.querySelector('.lightbox-img');
  const captionEl = overlay.querySelector('.lightbox-caption');

  // ── 확대/이동 (wheel 줌, 드래그 팬, 더블클릭 토글) ──
  let scale = 1, tx = 0, ty = 0;

  function applyTransform() {
    imgEl.style.transform = scale === 1 ? '' : `translate(${tx}px, ${ty}px) scale(${scale})`;
    imgEl.style.cursor = scale > 1 ? 'grab' : '';
  }

  function resetZoom() {
    scale = 1; tx = 0; ty = 0;
    applyTransform();
  }

  // 커서 위치 고정 줌: transform-origin이 중앙이므로 중앙→커서 벡터가 k배 되는 만큼 보정
  function zoomAt(clientX, clientY, newScale) {
    const k = newScale / scale;
    const rect = imgEl.getBoundingClientRect();
    const dx = clientX - (rect.left + rect.width / 2);
    const dy = clientY - (rect.top + rect.height / 2);
    tx += dx * (1 - k);
    ty += dy * (1 - k);
    scale = newScale;
    if (scale === 1) { tx = 0; ty = 0; }
    applyTransform();
  }

  imgEl.addEventListener('wheel', e => {
    e.preventDefault();
    const next = Math.min(6, Math.max(1, scale * (e.deltaY < 0 ? 1.2 : 1 / 1.2)));
    zoomAt(e.clientX, e.clientY, next);
  }, { passive: false });

  imgEl.addEventListener('dblclick', e => {
    if (scale > 1) resetZoom();
    else zoomAt(e.clientX, e.clientY, 2.5);
  });

  let dragging = null;
  let pinch = null;
  const activePointers = new Map();

  function pointDist(a, b) { return Math.hypot(a.x - b.x, a.y - b.y); }
  function pointMid(a, b) { return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }; }

  imgEl.addEventListener('pointerdown', e => {
    activePointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (e.pointerType === 'touch') imgEl.setPointerCapture(e.pointerId);

    if (activePointers.size >= 2) {
      e.preventDefault();
      dragging = null;
      const [p1, p2] = [...activePointers.values()];
      pinch = { startDist: pointDist(p1, p2), startScale: scale, lastMid: pointMid(p1, p2) };
      return;
    }
    if (scale === 1) return;
    e.preventDefault();
    dragging = { x: e.clientX, y: e.clientY };
    imgEl.setPointerCapture(e.pointerId);
    imgEl.style.cursor = 'grabbing';
  });
  imgEl.addEventListener('pointermove', e => {
    if (!activePointers.has(e.pointerId)) return;
    activePointers.set(e.pointerId, { x: e.clientX, y: e.clientY });

    if (pinch && activePointers.size >= 2) {
      const [p1, p2] = [...activePointers.values()];
      const mid = pointMid(p1, p2);
      tx += mid.x - pinch.lastMid.x;
      ty += mid.y - pinch.lastMid.y;
      pinch.lastMid = mid;
      const dist = pointDist(p1, p2);
      const newScale = Math.min(6, Math.max(1, pinch.startScale * (dist / pinch.startDist)));
      zoomAt(mid.x, mid.y, newScale);
      return;
    }

    if (!dragging) return;
    tx += e.clientX - dragging.x;
    ty += e.clientY - dragging.y;
    dragging = { x: e.clientX, y: e.clientY };
    applyTransform();
  });
  function endPointer(e) {
    activePointers.delete(e.pointerId);
    if (activePointers.size < 2) pinch = null;
    if (activePointers.size === 1 && scale > 1) {
      const [p] = [...activePointers.values()];
      dragging = { x: p.x, y: p.y };
    } else {
      dragging = null;
    }
    applyTransform();
  }
  imgEl.addEventListener('pointerup', endPointer);
  imgEl.addEventListener('pointercancel', endPointer);
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
    resetZoom();
    imgEl.style.opacity = '0.4';
    imgEl.onload = () => { imgEl.style.opacity = '1'; };
    imgEl.src = `/api/admin/photo?path=${encodeURIComponent(localPaths[i])}`;
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

  show(startIdx);
}

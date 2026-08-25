/**
 * Admin 라이트박스(lightbox.js)와 공유뷰어(album-view.js) 전체화면 사진 보기가
 * 공유하는 줌/팬/핀치/스와이프 제스처 엔진.
 *
 * 이미지 로드와 인덱스 이동까지 이 모듈이 소유한다 — 스와이프 커밋 시 새 이미지가
 * 실제로 로드된 뒤에만 idx를 갱신해야 peek 이미지가 슬라이드로 화면 중앙에 도착한
 * 시점과 실제 이미지 교체 시점이 어긋나지 않는다(먼저 갱신하면 완료 애니메이션이
 * 끝나기도 전에 원본 이미지가 깜빡인다).
 *
 * options:
 *   bodyEl, imgEl               필수. 제스처가 바인딩되는 컨테이너/이미지 엘리먼트
 *   peekPrevEl, peekNextEl      선택. 있으면 스와이프 중 이전/다음 사진이 옆에서 따라오는
 *                               슬라이드 애니메이션이 활성화된다(없으면 즉시 전환)
 *   maxZoom                     기본 6
 *   dblClickZoom                기본 2 (더블클릭 시 도달하는 배율)
 *   getUrl(idx)                 idx의 이미지 URL. 범위 밖이면 null
 *   getCount()                  전체 장수
 *   getIndex()                  현재 idx (모듈은 idx를 직접 소유하지 않는다)
 *   onIndexChanged(idx)         새 이미지 로드 완료 후 호출 — 캡션/카운터/정보패널 등 갱신
 *   scrollableSelector          이 셀렉터 안에서 시작한 wheel은 확대/축소하지 않고 무시
 *                               (예: 라이트박스 정보 패널의 자체 스크롤을 보존)
 *   isEnabled()                 기본 true. false를 반환하는 동안 줌/팬/스와이프 제스처를
 *                               전부 무시한다 — 동영상(혼합 그리드의 라이트박스 등)처럼
 *                               이 엔진의 대상이 아닌 슬라이드를 보여주는 중일 때 사용.
 *
 * 반환: { goTo(idx, opts), resetZoom(), changeZoom(factor), destroy() }
 */
import { startedInEdgeZone, resolveSwipeDirection, clampDragOffset } from './touch-gesture.js';

const MIN_ZOOM = 1;

export function createPhotoZoomViewer({
  bodyEl,
  imgEl,
  peekPrevEl = null,
  peekNextEl = null,
  maxZoom = 6,
  dblClickZoom = 2,
  getUrl,
  getCount,
  getIndex,
  onIndexChanged,
  onZoomChange = null,
  scrollableSelector = null,
  isEnabled = () => true,
}) {
  let zoom = MIN_ZOOM;
  let panX = 0, panY = 0;
  let swipeX = 0;
  let settling = false;

  const hasPrev = () => getIndex() > 0;
  const hasNext = () => getIndex() < getCount() - 1;

  function clampPan() {
    const maxX = Math.max(0, (imgEl.offsetWidth * zoom - bodyEl.offsetWidth) / 2);
    const maxY = Math.max(0, (imgEl.offsetHeight * zoom - bodyEl.offsetHeight) / 2);
    panX = Math.max(-maxX, Math.min(maxX, panX));
    panY = Math.max(-maxY, Math.min(maxY, panY));
  }

  function updatePeekTransforms() {
    if (!peekPrevEl || !peekNextEl) return;
    const bodyWidth = bodyEl.offsetWidth;
    peekPrevEl.style.transform = `translate(-50%, -50%) translateX(${swipeX - bodyWidth}px)`;
    peekNextEl.style.transform = `translate(-50%, -50%) translateX(${swipeX + bodyWidth}px)`;
  }

  function applyTransform() {
    imgEl.style.transform = zoom > 1
      ? `translate(-50%, -50%) translate(${panX}px, ${panY}px) scale(${zoom})`
      : `translate(-50%, -50%) translateX(${swipeX}px)`;
    imgEl.style.cursor = zoom > 1 ? 'grab' : '';
    updatePeekTransforms();
    if (onZoomChange) onZoomChange(zoom);
  }

  function resetZoom() {
    zoom = MIN_ZOOM; panX = 0; panY = 0; swipeX = 0;
    applyTransform();
  }

  // factor 기준 상대 줌 — 커서/핀치 중심점(ox, oy = 컨테이너 중심 기준 오프셋)을 고정한다
  function changeZoom(factor, ox = 0, oy = 0) {
    const newZoom = Math.max(MIN_ZOOM, Math.min(maxZoom, zoom * factor));
    if (newZoom === zoom) return;
    const scale = newZoom / zoom;
    panX = ox * (1 - scale) + panX * scale;
    panY = oy * (1 - scale) + panY * scale;
    zoom = newZoom;
    if (zoom <= MIN_ZOOM) { panX = 0; panY = 0; }
    clampPan();
    applyTransform();
  }

  // ── 화면 회전/리사이즈: peek 이미지 위치·팬 범위 재계산 ──────
  // peek 엘리먼트는 bodyEl.offsetWidth(px)로 화면 밖 위치를 고정하는데, 리사이즈만
  // 발생하고 goTo/zoom 등 applyTransform 재호출이 없으면 옛 너비 기준 오프셋이 남아
  // 회전 직후 이전/다음 사진이 화면에 걸쳐 보인다. iOS는 orientationchange 시점에
  // offsetWidth가 아직 회전 전 값일 수 있어 rAF 한 틱 미뤄서 읽는다.
  let resizeRaf = null;
  const onResize = () => {
    if (resizeRaf != null) return;
    resizeRaf = requestAnimationFrame(() => {
      resizeRaf = null;
      clampPan();
      applyTransform();
    });
  };
  window.addEventListener('resize', onResize);
  function destroy() {
    window.removeEventListener('resize', onResize);
    if (resizeRaf != null) cancelAnimationFrame(resizeRaf);
  }

  // ── 마우스 가운데 버튼: 줌 리셋 ──────────────────────────
  bodyEl.addEventListener('mousedown', e => {
    if (!isEnabled()) return;
    if (scrollableSelector && e.target.closest(scrollableSelector)) return;
    if (e.button === 1) { e.preventDefault(); resetZoom(); }
  });

  // ── 휠 줌 (정보 패널 등 자체 스크롤 영역은 제외) ──────────
  bodyEl.addEventListener('wheel', e => {
    if (!isEnabled()) return;
    if (scrollableSelector && e.target.closest(scrollableSelector)) return;
    e.preventDefault();
    const rect = bodyEl.getBoundingClientRect();
    const ox = e.clientX - (rect.left + rect.width / 2);
    const oy = e.clientY - (rect.top + rect.height / 2);
    changeZoom(e.deltaY < 0 ? 1.2 : 1 / 1.2, ox, oy);
  }, { passive: false });

  // ── 더블클릭: 확대 ↔ 리셋 토글 ─────────────────────────────
  // bodyEl에 바인딩(imgEl 아님, wheel/가운데버튼과 동일한 범위) — 확대 중에는
  // 드래그 팬이 bodyEl에서 포인터를 capture하는데, dblclick을 imgEl에 두면
  // 캡처가 이벤트 타깃을 bodyEl로 바꿔버려 리셋 더블클릭이 씹힐 수 있다.
  bodyEl.addEventListener('dblclick', e => {
    if (!isEnabled()) return;
    if (scrollableSelector && e.target.closest(scrollableSelector)) return;
    if (zoom > 1) {
      resetZoom();
    } else {
      const rect = bodyEl.getBoundingClientRect();
      const ox = e.clientX - (rect.left + rect.width / 2);
      const oy = e.clientY - (rect.top + rect.height / 2);
      changeZoom(dblClickZoom, ox, oy);
    }
  });

  // ── Pointer Events 통합: 드래그 팬(줌 시) + 핀치 줌 + 스와이프 넘기기(터치 전용) ──
  let dragging = null;
  let pinch = null;
  let swipeStart = null;
  const activePointers = new Map();

  const pointDist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
  const pointMid  = (a, b) => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });

  bodyEl.addEventListener('pointerdown', e => {
    if (!isEnabled()) return;
    if (scrollableSelector && e.target.closest(scrollableSelector)) return;
    // 마우스 가운데/오른쪽 버튼은 팬 대상이 아니다 — 이 핸들러가 관여하면
    // preventDefault·setPointerCapture가 걸려 가운데버튼 줌 리셋(mousedown)이 씹힌다
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    activePointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (e.pointerType === 'touch') bodyEl.setPointerCapture(e.pointerId);

    if (activePointers.size >= 2) {
      e.preventDefault();
      dragging = null;
      swipeStart = null;
      const [p1, p2] = [...activePointers.values()];
      pinch = { lastDist: pointDist(p1, p2), lastMid: pointMid(p1, p2) };
      return;
    }
    if (zoom === MIN_ZOOM) {
      // 스와이프 넘기기는 터치 전용 — 마우스 드래그로는 넘기지 않는다(기존 두 뷰어 모두 동일)
      if (e.pointerType === 'touch' && !settling) {
        const rect = bodyEl.getBoundingClientRect();
        swipeStart = { x: e.clientX, y: e.clientY, edge: startedInEdgeZone(e.clientX, rect.left, rect.right) };
      }
      return;
    }
    e.preventDefault();
    dragging = { x: e.clientX, y: e.clientY };
    bodyEl.setPointerCapture(e.pointerId);
    imgEl.style.cursor = 'grabbing';
  });

  bodyEl.addEventListener('pointermove', e => {
    if (!activePointers.has(e.pointerId)) return;
    activePointers.set(e.pointerId, { x: e.clientX, y: e.clientY });

    if (pinch && activePointers.size >= 2) {
      e.preventDefault();
      const [p1, p2] = [...activePointers.values()];
      const dist = pointDist(p1, p2);
      const mid = pointMid(p1, p2);
      const rect = bodyEl.getBoundingClientRect();
      const ox = mid.x - (rect.left + rect.width / 2);
      const oy = mid.y - (rect.top + rect.height / 2);
      changeZoom(dist / pinch.lastDist, ox, oy);
      panX += mid.x - pinch.lastMid.x;
      panY += mid.y - pinch.lastMid.y;
      clampPan();
      applyTransform();
      pinch.lastDist = dist;
      pinch.lastMid = mid;
      return;
    }

    if (dragging) {
      e.preventDefault();
      panX += e.clientX - dragging.x;
      panY += e.clientY - dragging.y;
      dragging = { x: e.clientX, y: e.clientY };
      clampPan();
      applyTransform();
      return;
    }

    if (swipeStart && !swipeStart.edge && !settling) {
      const dx = e.clientX - swipeStart.x;
      swipeX = clampDragOffset(dx, { hasPrev: hasPrev(), hasNext: hasNext() });
      applyTransform();
    }
  });

  function endPointer(e) {
    activePointers.delete(e.pointerId);
    if (activePointers.size < 2) pinch = null;

    if (swipeStart && activePointers.size === 0) {
      const dx = e.clientX - swipeStart.x;
      const dy = e.clientY - swipeStart.y;
      let dir = resolveSwipeDirection({ dx, dy, startedInEdge: swipeStart.edge });
      if (dir === 1 && !hasNext()) dir = 0;
      if (dir === -1 && !hasPrev()) dir = 0;
      settleSwipe(dir);
    }
    swipeStart = null;

    if (activePointers.size === 1 && zoom > 1) {
      const [p] = [...activePointers.values()];
      dragging = { x: p.x, y: p.y };
    } else {
      dragging = null;
      if (zoom > 1) imgEl.style.cursor = 'grab';
    }
  }
  bodyEl.addEventListener('pointerup', endPointer);
  bodyEl.addEventListener('pointercancel', endPointer);

  // 스와이프 판정(dir: 1=다음, -1=이전, 0=취소) 이후 화면 밖까지 슬라이드하거나
  // 원위치로 되돌아가는 애니메이션을 재생한 뒤 실제 사진 전환(goTo)을 적용한다.
  function settleSwipe(dir) {
    if (!peekPrevEl || !peekNextEl) { finishSwipe(dir); return; }
    const bodyWidth = bodyEl.offsetWidth;
    const targetX = dir === 1 ? -bodyWidth : dir === -1 ? bodyWidth : 0;
    if (Math.round(swipeX) === Math.round(targetX)) {
      finishSwipe(dir);
      return;
    }
    settling = true;
    const els = [imgEl, peekPrevEl, peekNextEl];
    els.forEach(el => el.classList.add('pv-snapping'));
    swipeX = targetX;
    applyTransform();

    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      clearTimeout(fallbackTimer);
      imgEl.removeEventListener('transitionend', onTransitionEnd);
      els.forEach(el => el.classList.remove('pv-snapping'));
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

  function finishSwipe(dir) {
    const idx = getIndex();
    if (dir === 1 && idx < getCount() - 1) goTo(idx + 1, { fade: false });
    else if (dir === -1 && idx > 0) goTo(idx - 1, { fade: false });
    else { swipeX = 0; applyTransform(); }
  }

  // 버튼 클릭 · 키보드 · 스와이프 커밋이 모두 거치는 단일 이동 경로.
  // 새 이미지가 실제로 로드된 뒤에만 idx를 갱신한다(스와이프 중 깜빡임 방지).
  let pendingUrl = null;
  function goTo(idx, { fade = true } = {}) {
    const url = getUrl(idx);
    if (url == null) return;
    pendingUrl = url;
    if (fade) imgEl.style.opacity = '0.4';
    const onLoad = () => {
      imgEl.removeEventListener('load', onLoad);
      // 로드 중 더 최신 goTo가 호출됐으면 이 응답은 버린다 — 연타 시 순서가 뒤엉켜
      // 이전 idx로 되돌아가는 것을 방지한다.
      if (pendingUrl !== url) return;
      imgEl.style.opacity = '1';
      resetZoom();
      if (peekPrevEl) peekPrevEl.src = idx > 0 ? (getUrl(idx - 1) || '') : '';
      if (peekNextEl) peekNextEl.src = idx < getCount() - 1 ? (getUrl(idx + 1) || '') : '';
      onIndexChanged(idx);
    };
    imgEl.addEventListener('load', onLoad);
    imgEl.src = url;
  }

  return { goTo, resetZoom, changeZoom, destroy };
}

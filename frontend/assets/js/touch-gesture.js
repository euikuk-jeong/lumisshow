/**
 * 슬라이드쇼/전체 사진 보기/라이트박스에서 공용으로 쓰는 좌우 스와이프 판정 로직.
 * DOM에 의존하지 않는 순수 함수만 모아 unit test가 가능하게 분리했다.
 */

export const SWIPE_EDGE_EXCLUDE_PX = 28;
export const SWIPE_THRESHOLD_PX = 50;

/**
 * 시작 지점이 화면 가장자리(edgePx 이내)인지 여부.
 * iOS는 이 영역을 뒤로가기 제스처 전용으로 예약해 두어 preventDefault로도 못 막으므로,
 * 이 영역에서 시작한 터치는 스와이프 후보에서 제외한다.
 */
export function startedInEdgeZone(startX, rectLeft, rectRight, edgePx = SWIPE_EDGE_EXCLUDE_PX) {
  return (startX - rectLeft) < edgePx || (rectRight - startX) < edgePx;
}

/**
 * 좌우 스와이프 방향 판정.
 * 반환값: 1 = 다음, -1 = 이전, 0 = 스와이프 아님(무시)
 */
export function resolveSwipeDirection({ dx, dy, startedInEdge, threshold = SWIPE_THRESHOLD_PX }) {
  if (startedInEdge) return 0;
  if (Math.abs(dx) <= threshold) return 0;
  if (Math.abs(dx) <= Math.abs(dy)) return 0;
  return dx < 0 ? 1 : -1;
}

/** 탭(짧은 움직임 + 빠른 시간) 여부 */
export function isTap(dx, dy, dt, { moveThreshold = 15, timeThreshold = 300 } = {}) {
  return Math.abs(dx) < moveThreshold && Math.abs(dy) < moveThreshold && dt < timeThreshold;
}

/** 이웃 사진이 없는 방향으로 드래그하면 화면이 따라가지 않도록 오프셋을 0으로 고정 */
export function clampDragOffset(dx, { hasPrev, hasNext }) {
  if (dx < 0 && !hasNext) return 0;
  if (dx > 0 && !hasPrev) return 0;
  return dx;
}

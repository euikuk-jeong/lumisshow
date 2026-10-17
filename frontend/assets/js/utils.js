export function esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// 썸네일 그리드 로딩 스켈레톤(admin.css의 .thumb-loading 셰이머) 공용 헬퍼.
// 컨테이너(.photo-thumb/.photo-list-thumb/.face-card/.person-cover)에 'thumb-loading'
// 클래스를 붙여둔 상태로 이 <img>를 넣으면 로드/에러 시 알아서 클래스를 뗀다.
export function thumbImg(url, errOpacity = 0.2) {
  return `<img src="${url}" alt="" loading="lazy" onload="this.parentElement.classList.remove('thumb-loading')" onerror="this.style.opacity='${errOpacity}';this.parentElement.classList.remove('thumb-loading')">`;
}

// 앨범 커버 세로 표시 영역(albums.cover_position) → CSS object-position.
// 'auto'는 기존 고정값(상단 20% 기준) 그대로 — 값이 없는 기존 앨범도 'auto'로 취급.
// Admin 편집 화면 미리보기(admin-album-edit.js)와 공유뷰어 커버(album-view.js) 공용.
export const COVER_POSITIONS = [
  { id: 'auto',   label: '자동',  objectPosition: '50% 20%' },
  { id: 'top',    label: '상단',  objectPosition: '50% 0%' },
  { id: 'center', label: '중앙',  objectPosition: '50% 50%' },
  { id: 'bottom', label: '하단',  objectPosition: '50% 100%' },
];
export function coverObjectPosition(position) {
  return (COVER_POSITIONS.find(p => p.id === position) || COVER_POSITIONS[0]).objectPosition;
}

let _infoCache = null;
async function _fetchInfo() {
  if (_infoCache) return _infoCache;
  try {
    const res = await fetch('/version');
    if (res.ok) _infoCache = await res.json();
  } catch {}
  return _infoCache ?? {};
}
export async function getVersion() {
  const info = await _fetchInfo();
  return info.version ?? 'dev';
}
export async function getSiteTitle() {
  const info = await _fetchInfo();
  return info.site_title ?? 'LumisShow';
}
export function invalidateSiteInfo() {
  _infoCache = null;
}

export function formatPlayTime(totalSeconds) {
  const total = Math.max(0, Math.round(totalSeconds));
  const m = Math.floor(total / 60);
  const s = total % 60;
  if (m === 0) return `${s}초`;
  if (s === 0) return `${m}분`;
  return `${m}분 ${s}초`;
}

export function esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// 썸네일 그리드 로딩 스켈레톤(admin.css의 .thumb-loading 셰이머) 공용 헬퍼.
// 컨테이너(.photo-thumb/.photo-list-thumb/.face-card/.person-cover)에 'thumb-loading'
// 클래스를 붙여둔 상태로 이 <img>를 넣으면 로드/에러 시 알아서 클래스를 뗀다.
export function thumbImg(url, errOpacity = 0.2) {
  return `<img src="${url}" alt="" loading="lazy" onload="this.parentElement.classList.remove('thumb-loading')" onerror="this.style.opacity='${errOpacity}';this.parentElement.classList.remove('thumb-loading')">`;
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

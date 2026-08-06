export function esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
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

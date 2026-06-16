export function esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

let _versionCache = null;
export async function getVersion() {
  if (_versionCache) return _versionCache;
  try {
    const res = await fetch('/version');
    if (res.ok) _versionCache = (await res.json()).version;
  } catch {}
  return _versionCache ?? 'dev';
}

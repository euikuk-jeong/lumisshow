import { api } from '../api.js';
import { renderAdminShell } from '../layout.js';
import { esc } from '../utils.js';

let _albumsCache = null;

export async function renderAdminAlbums() {
  renderAdminShell(`
    <div class="page-header">
      <div>
        <h1 class="page-title">앨범</h1>
        <p class="page-subtitle">앨범을 관리하고 공유 링크를 생성합니다</p>
      </div>
      <a href="/admin/albums/new" class="btn btn-primary" data-link>+ 새 앨범</a>
    </div>
    <div id="albums-content">${_albumsCache ? '' : '<div class="loading"></div>'}</div>
  `, '/admin');

  await loadAlbums();
}

function _renderAlbums(el, albums) {
  if (!albums.length) {
    el.innerHTML = `
      <div class="empty-state">
        <h3>앨범이 없습니다</h3>
        <p>새 앨범 버튼을 눌러 첫 앨범을 만들어보세요</p>
      </div>`;
    return;
  }
  el.innerHTML = `<div class="album-grid">${albums.map(a => albumCard(a)).join('')}</div>`;
  el.querySelectorAll('.album-card').forEach((card, i) => {
    card.addEventListener('click', () => window.navigate(`/admin/albums/${albums[i].id}`));
  });
}

async function loadAlbums() {
  const el = document.getElementById('albums-content');
  if (_albumsCache !== null) {
    _renderAlbums(el, _albumsCache);
  }
  try {
    const albums = await api.get('/api/admin/albums');
    _albumsCache = albums;
    _renderAlbums(el, albums);
  } catch (e) {
    if (_albumsCache === null) {
      el.innerHTML = `<div class="alert alert-error">${esc(e.message)}</div>`;
    }
  }
}

function albumCard(album) {
  const coverPath = album.cover_path || album.first_photo_path;
  const cover = coverPath
    ? `<img src="/api/admin/thumb?path=${encodeURIComponent(coverPath)}&size=small" alt="" loading="lazy">`
    : '🖼';
  const createdDate = new Date(album.created_at).toLocaleDateString('ko-KR');
  const expiresDate = album.next_expires_at ? new Date(album.next_expires_at).toLocaleDateString('ko-KR') : null;
  return `
    <div class="album-card">
      <div class="album-cover">${cover}</div>
      <div class="album-info">
        <div class="album-name" title="${esc(album.name)}">${esc(album.name)}</div>
        <div class="album-meta">
          <div class="album-meta-row">
            <span>📷 ${album.photo_count.toLocaleString()}장</span>
            ${album.video_count > 0 ? `<span>🎬 ${album.video_count.toLocaleString()}개</span>` : ''}
            <span>👁 ${(album.view_count ?? 0).toLocaleString()}회</span>
            <span>🔗 ${(album.active_link_count ?? 0).toLocaleString()}개</span>
          </div>
          <div class="album-meta-row">
            <span>${createdDate} 생성</span>
            ${expiresDate ? `<span>· ${expiresDate} 만료</span>` : ''}
          </div>
        </div>
      </div>
    </div>`;
}

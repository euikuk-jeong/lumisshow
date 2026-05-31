import { api } from '../api.js';
import { getToken } from '../auth.js';
import { renderAdminShell } from '../layout.js';
import { esc } from '../utils.js';

export async function renderAdminAlbums() {
  renderAdminShell(`
    <div class="page-header">
      <div>
        <h1 class="page-title">앨범</h1>
        <p class="page-subtitle">앨범을 관리하고 공유 링크를 생성합니다</p>
      </div>
      <a href="/admin/albums/new" class="btn btn-primary" data-link>+ 새 앨범</a>
    </div>
    <div id="albums-content"><div class="loading"></div></div>
  `, '/admin');

  await loadAlbums();
}

async function loadAlbums() {
  const el = document.getElementById('albums-content');
  try {
    const albums = await api.get('/api/admin/albums');
    if (albums.length === 0) {
      el.innerHTML = `
        <div class="empty-state">
          <h3>앨범이 없습니다</h3>
          <p>새 앨범 버튼을 눌러 첫 앨범을 만들어보세요</p>
        </div>`;
      return;
    }
    const token = getToken();
    el.innerHTML = `<div class="album-grid">${albums.map(a => albumCard(a, token)).join('')}</div>`;
    el.querySelectorAll('.album-card').forEach((card, i) => {
      card.addEventListener('click', () => window.navigate(`/admin/albums/${albums[i].id}`));
    });
  } catch (e) {
    el.innerHTML = `<div class="alert alert-error">${esc(e.message)}</div>`;
  }
}

function albumCard(album, token) {
  const cover = album.cover_path
    ? `<img src="/api/admin/thumb?path=${encodeURIComponent(album.cover_path)}&size=small&token=${token}" alt="" loading="lazy">`
    : '🖼';
  const date = new Date(album.created_at).toLocaleDateString('ko-KR');
  return `
    <div class="album-card">
      <div class="album-cover">${cover}</div>
      <div class="album-info">
        <div class="album-name" title="${esc(album.name)}">${esc(album.name)}</div>
        <div class="album-meta">
          <span>📷 ${album.photo_count}장</span>
          <span>${date}</span>
        </div>
      </div>
    </div>`;
}

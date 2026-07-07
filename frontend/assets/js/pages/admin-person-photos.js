import { api } from '../api.js';
import { renderAdminShell } from '../layout.js';
import { esc } from '../utils.js';
import { openLightbox } from '../lightbox.js';

// 인물 전체 사진 (/admin/people/{id}/photos) — 확정·추정 얼굴이 포함된 사진 그리드
export async function renderAdminPersonPhotos(personId) {
  const people = await api.get('/api/admin/people');
  const person = people.find(p => p.id === Number(personId));
  if (!person) {
    window.navigate('/admin/people', true);
    return;
  }
  const { photos } = await api.get(`/api/admin/people/${personId}/photos`);

  renderAdminShell(`
    <div class="page-header">
      <div>
        <h1 class="page-title">${esc(person.name)} — 전체 사진</h1>
        <p class="page-subtitle">확정·추정 얼굴이 포함된 사진 ${photos.length}장</p>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <a href="/admin/people/${personId}" class="btn btn-ghost" data-link>← 인물 상세</a>
        <button class="btn btn-primary" id="btn-slideshow" ${photos.length ? '' : 'disabled'}>▶ 슬라이드쇼</button>
      </div>
    </div>
    <div id="photos-content"></div>
  `, '/admin/people');

  document.getElementById('btn-slideshow').addEventListener('click', () => {
    window.navigate(`/admin/people/${personId}/slideshow`);
  });

  const el = document.getElementById('photos-content');
  if (!photos.length) {
    el.innerHTML = `
      <div class="empty-state">
        <h3>사진이 없습니다</h3>
        <p>확정 또는 추정 얼굴이 있는 사진이 여기에 표시됩니다</p>
      </div>`;
    return;
  }

  el.innerHTML = `<div class="photo-grid">${photos.map((p, i) => `
    <div class="photo-thumb" data-idx="${i}" title="${esc(p)}">
      <img src="/api/admin/thumb?path=${encodeURIComponent(p)}&size=small" alt="" loading="lazy" onerror="this.style.opacity='0.3'">
    </div>`).join('')}</div>`;

  el.querySelector('.photo-grid').addEventListener('click', e => {
    const item = e.target.closest('.photo-thumb[data-idx]');
    if (item) openLightbox(photos, Number(item.dataset.idx));
  });
}

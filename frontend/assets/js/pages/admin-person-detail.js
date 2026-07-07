import { api } from '../api.js';
import { renderAdminShell } from '../layout.js';
import { esc } from '../utils.js';

export async function renderAdminPersonDetail(personId) {
  const people = await api.get('/api/admin/people');
  const person = people.find(p => p.id === Number(personId));
  if (!person) {
    window.navigate('/admin/people', true);
    return;
  }

  renderAdminShell(`
    <div class="page-header">
      <div>
        <h1 class="page-title">${esc(person.name)}
          <button class="btn btn-ghost btn-sm" id="btn-rename" title="이름 변경">✎</button>
        </h1>
        <p class="page-subtitle">확정 ${person.labeled_count} · 추정 ${person.matched_count}</p>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <a href="/admin/people" class="btn btn-ghost" data-link>← 인물 목록</a>
        <button class="btn btn-primary" id="btn-make-album">이 인물로 앨범 만들기</button>
        <button class="btn btn-ghost" id="btn-delete" style="color:var(--error)">삭제</button>
      </div>
    </div>

    <h3 class="section-title">추정 얼굴 <span class="text-muted">— 자동 매칭 결과를 확인해 주세요</span></h3>
    <div id="matched-content"><div class="loading"></div></div>

    <h3 class="section-title" style="margin-top:28px">확정 얼굴</h3>
    <div id="labeled-content"><div class="loading"></div></div>
  `, '/admin/people');

  document.getElementById('btn-rename').addEventListener('click', async () => {
    const name = prompt('새 이름', person.name);
    if (!name?.trim() || name.trim() === person.name) return;
    try {
      await api.put(`/api/admin/people/${personId}`, { name: name.trim() });
      renderAdminPersonDetail(personId);
    } catch (e) { alert(e.message); }
  });

  document.getElementById('btn-delete').addEventListener('click', async () => {
    if (!confirm(`'${person.name}' 인물을 삭제할까요?\n(얼굴 라벨도 함께 삭제되며 사진 원본은 영향 없음)`)) return;
    try {
      await api.delete(`/api/admin/people/${personId}`);
      window.navigate('/admin/people');
    } catch (e) { alert(e.message); }
  });

  document.getElementById('btn-make-album').addEventListener('click', async () => {
    try {
      const { photos } = await api.get(`/api/admin/people/${personId}/photos`);
      if (!photos.length) { alert('이 인물의 사진이 없습니다.'); return; }
      const name = prompt(`사진 ${photos.length}장으로 앨범을 만듭니다.\n앨범 이름:`, person.name);
      if (!name?.trim()) return;
      const album = await api.post('/api/admin/albums', {
        name: name.trim(),
        description: `${person.name} 인물 앨범 (AI 자동 분류)`,
        photo_paths: photos,
      });
      window.navigate(`/admin/albums/${album.id}`);
    } catch (e) { alert(e.message); }
  });

  await Promise.all([
    loadFaces(personId, 'matched', document.getElementById('matched-content')),
    loadFaces(personId, 'labeled', document.getElementById('labeled-content')),
  ]);
}

async function loadFaces(personId, source, el) {
  try {
    const { faces } = await api.get(
      `/api/admin/people/${personId}/faces?source=${source}&limit=200`);
    if (!faces.length) {
      el.innerHTML = `<p class="text-muted">${
        source === 'matched' ? '추정 얼굴이 없습니다.' : '확정된 얼굴이 없습니다. 미분류 얼굴에서 지정하세요.'
      }</p>`;
      return;
    }
    el.innerHTML = `<div class="face-grid">${faces.map(f => faceCard(f, source)).join('')}</div>`;
    el.querySelectorAll('.face-card').forEach((card, i) => {
      const face = faces[i];
      card.querySelector('[data-act="ok"]')?.addEventListener('click', async (e) => {
        e.stopPropagation();
        await labelFace(face.face_id, Number(personId), personId);
      });
      card.querySelector('[data-act="no"]')?.addEventListener('click', async (e) => {
        e.stopPropagation();
        await labelFace(face.face_id, null, personId);
      });
      card.querySelector('[data-act="undo"]')?.addEventListener('click', async (e) => {
        e.stopPropagation();
        try { await api.delete(`/api/admin/faces/${face.face_id}/label`); } catch (err) { alert(err.message); return; }
        renderAdminPersonDetail(personId);
      });
    });
  } catch (e) {
    el.innerHTML = `<div class="alert alert-error">${esc(e.message)}</div>`;
  }
}

async function labelFace(faceId, personIdOrNull, pageId) {
  try {
    await api.post(`/api/admin/faces/${faceId}/label`, { person_id: personIdOrNull });
    renderAdminPersonDetail(pageId);
  } catch (e) { alert(e.message); }
}

function faceCard(f, source) {
  const actions = source === 'matched'
    ? `<button class="btn btn-sm btn-primary" data-act="ok" title="이 인물이 맞음">✓</button>
       <button class="btn btn-sm btn-ghost" data-act="no" title="이 인물이 아님">✕</button>`
    : `<button class="btn btn-sm btn-ghost" data-act="undo" title="확정 해제">↩</button>`;
  const score = f.score != null
    ? `<span class="face-score">${Math.round(f.score * 100)}%</span>` : '';
  return `
    <div class="face-card" title="${esc(f.photo_path)}">
      <img src="/api/admin/faces/${f.face_id}/crop" alt="" loading="lazy">
      ${score}
      <div class="face-actions">${actions}</div>
    </div>`;
}

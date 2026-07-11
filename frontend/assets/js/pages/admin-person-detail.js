import { api } from '../api.js';
import { renderAdminShell } from '../layout.js';
import { esc } from '../utils.js';

let _matchedSelected = new Set();

export async function renderAdminPersonDetail(personId) {
  _matchedSelected = new Set();
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
        <a href="/admin/people/${personId}/photos" class="btn btn-ghost" data-link>전체 사진</a>
        <a href="/admin/people/${personId}/slideshow" class="btn btn-ghost" data-link>▶ 슬라이드쇼</a>
        <button class="btn btn-primary" id="btn-make-album">이 인물로 앨범 만들기</button>
        <button class="btn btn-ghost" id="btn-delete" style="color:var(--error)">삭제</button>
      </div>
    </div>

    <h3 class="section-title">추정 얼굴 <span class="text-muted">— 틀린 것만 선택 해제한 뒤 확정하세요</span></h3>
    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:10px">
      <button class="btn btn-ghost btn-sm" id="btn-select-all">전체 선택</button>
      <button class="btn btn-ghost btn-sm" id="btn-select-none">전체 해제</button>
      <button class="btn btn-primary btn-sm" id="btn-confirm-selected" disabled>선택 확정</button>
      <span style="flex:1"></span>
      <input type="number" id="confirm-threshold" class="form-input" style="width:64px" min="0" max="100" value="70">
      <span class="text-muted" style="font-size:13px">% 이상</span>
      <button class="btn btn-ghost btn-sm" id="btn-confirm-threshold" disabled>자동 확정</button>
    </div>
    <div id="matched-content"><div class="loading"></div></div>

    <h3 class="section-title" style="margin-top:28px">확정 얼굴</h3>
    <div id="labeled-content"><div class="loading"></div></div>
  `, '/admin/people');

  document.getElementById('btn-select-all').addEventListener('click', () => setAllMatchedSelected(true));
  document.getElementById('btn-select-none').addEventListener('click', () => setAllMatchedSelected(false));
  document.getElementById('btn-confirm-selected').addEventListener('click', () => confirmSelected(personId));
  document.getElementById('btn-confirm-threshold').addEventListener('click', () => confirmByThreshold(personId));

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
    loadMatchedFaces(personId),
    loadLabeledFaces(personId),
  ]);
}

// ── 추정 얼굴: 기본 전체 선택, 틀린 것만 클릭해 제외 후 일괄 확정 ─────────

async function loadMatchedFaces(personId) {
  const el = document.getElementById('matched-content');
  try {
    const { faces } = await api.get(`/api/admin/people/${personId}/faces?source=matched&limit=200`);
    document.getElementById('btn-confirm-threshold').disabled = faces.length === 0;
    if (!faces.length) {
      el.innerHTML = '<p class="text-muted">추정 얼굴이 없습니다.</p>';
      updateMatchedToolbar();
      return;
    }
    el.innerHTML = `<div class="face-grid">${faces.map(matchedFaceCard).join('')}</div>`;
    el.querySelectorAll('.face-card').forEach(card => {
      const id = Number(card.dataset.face);
      _matchedSelected.add(id);  // 기본 전체 선택
      card.addEventListener('click', () => {
        if (_matchedSelected.has(id)) { _matchedSelected.delete(id); card.classList.remove('selected'); }
        else                          { _matchedSelected.add(id);    card.classList.add('selected'); }
        updateMatchedToolbar();
      });
    });
    updateMatchedToolbar();
  } catch (e) {
    el.innerHTML = `<div class="alert alert-error">${esc(e.message)}</div>`;
  }
}

function matchedFaceCard(f) {
  const score = f.score != null
    ? `<span class="face-score">${Math.round(f.score * 100)}%</span>` : '';
  return `
    <div class="face-card selected" data-face="${f.face_id}" title="${esc(f.photo_path)}">
      <img src="/api/admin/faces/${f.face_id}/crop" alt="" loading="lazy">
      ${score}
    </div>`;
}

function setAllMatchedSelected(on) {
  document.querySelectorAll('#matched-content .face-card').forEach(card => {
    const id = Number(card.dataset.face);
    if (on) { _matchedSelected.add(id); card.classList.add('selected'); }
    else    { _matchedSelected.delete(id); card.classList.remove('selected'); }
  });
  updateMatchedToolbar();
}

function updateMatchedToolbar() {
  const n = _matchedSelected.size;
  const btn = document.getElementById('btn-confirm-selected');
  btn.disabled = n === 0;
  btn.textContent = n ? `선택 확정 (${n})` : '선택 확정';
}

async function confirmSelected(personId) {
  const ids = [..._matchedSelected];
  if (!ids.length) return;
  try {
    await api.post('/api/admin/faces/batch-label', { face_ids: ids, person_id: Number(personId) });
    renderAdminPersonDetail(personId);
  } catch (e) { alert(e.message); }
}

async function confirmByThreshold(personId) {
  const pct = Number(document.getElementById('confirm-threshold').value);
  if (!Number.isFinite(pct) || pct < 0 || pct > 100) { alert('0~100 사이 값을 입력하세요'); return; }
  try {
    const r = await api.post(`/api/admin/people/${personId}/confirm-matched`, { min_score: pct / 100 });
    alert(`${r.count}장을 확정했습니다.`);
    if (r.count > 0) renderAdminPersonDetail(personId);
  } catch (e) { alert(e.message); }
}

// ── 확정 얼굴: 목록 + 확정 해제 ────────────────────────────────────────

async function loadLabeledFaces(personId) {
  const el = document.getElementById('labeled-content');
  try {
    const { faces } = await api.get(`/api/admin/people/${personId}/faces?source=labeled&limit=200`);
    if (!faces.length) {
      el.innerHTML = '<p class="text-muted">확정된 얼굴이 없습니다. 미분류 얼굴에서 지정하세요.</p>';
      return;
    }
    el.innerHTML = `<div class="face-grid">${faces.map(labeledFaceCard).join('')}</div>`;
    el.querySelectorAll('.face-card').forEach((card, i) => {
      card.querySelector('[data-act="undo"]').addEventListener('click', async (e) => {
        e.stopPropagation();
        try { await api.delete(`/api/admin/faces/${faces[i].face_id}/label`); } catch (err) { alert(err.message); return; }
        renderAdminPersonDetail(personId);
      });
    });
  } catch (e) {
    el.innerHTML = `<div class="alert alert-error">${esc(e.message)}</div>`;
  }
}

function labeledFaceCard(f) {
  return `
    <div class="face-card" title="${esc(f.photo_path)}">
      <img src="/api/admin/faces/${f.face_id}/crop" alt="" loading="lazy">
      <div class="face-actions">
        <button class="btn btn-sm btn-ghost" data-act="undo" title="확정 해제">↩</button>
      </div>
    </div>`;
}

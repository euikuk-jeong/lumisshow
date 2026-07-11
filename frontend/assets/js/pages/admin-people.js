import { api } from '../api.js';
import { renderAdminShell } from '../layout.js';
import { esc } from '../utils.js';

// ── 인물 목록 (/admin/people) ─────────────────────────────────────────

export async function renderAdminPeople() {
  renderAdminShell(`
    <div class="page-header">
      <div>
        <h1 class="page-title">인물</h1>
        <p class="page-subtitle" id="ai-status-line">AI 분석 상태 불러오는 중…</p>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <a href="/admin/people/unassigned" class="btn btn-ghost" data-link>미분류 얼굴</a>
        <button class="btn btn-ghost" id="btn-scan">지금 스캔</button>
        <button class="btn btn-ghost" id="btn-rematch">재매칭</button>
        <button class="btn btn-primary" id="btn-new-person">+ 새 인물</button>
      </div>
    </div>
    <div id="people-content"><div class="loading"></div></div>
  `, '/admin/people');

  document.getElementById('btn-new-person').addEventListener('click', async () => {
    const name = prompt('인물 이름을 입력하세요');
    if (!name?.trim()) return;
    try {
      const p = await api.post('/api/admin/people', { name: name.trim() });
      window.navigate(`/admin/people/${p.id}`);
    } catch (e) { alert(e.message); }
  });
  document.getElementById('btn-scan').addEventListener('click', () => triggerJob('scan'));
  document.getElementById('btn-rematch').addEventListener('click', () => triggerJob('rematch'));

  await Promise.all([loadPeople(), loadAiStatus()]);
}

async function triggerJob(type) {
  const label = type === 'scan' ? '스캔' : '재매칭';
  try {
    const r = await api.post('/api/admin/ai/jobs', { type });
    alert(r.duplicated
      ? `이미 대기/실행 중인 ${label} 작업이 있습니다 (#${r.id})`
      : `${label} 작업을 요청했습니다 (#${r.id}). AI 워커가 곧 처리합니다.`);
    loadAiStatus();
  } catch (e) { alert(e.message); }
}

async function loadAiStatus() {
  const el = document.getElementById('ai-status-line');
  if (!el) return;
  try {
    const s = await api.get('/api/admin/ai/status');
    const active = s.recent_jobs
      .filter(j => j.status === 'running' || j.status === 'pending')
      .sort((a, b) => (a.status === b.status ? 0 : a.status === 'running' ? -1 : 1));
    const activeText = active
      .map(j => `${j.type} 작업 ${j.status === 'running' ? '실행 중' : '대기 중'}`)
      .join(', ');
    el.textContent =
      `분석 사진 ${s.photos.toLocaleString()}장 · 얼굴 ${s.faces.toLocaleString()}개 · 라벨 ${s.labels.toLocaleString()}개`
      + (s.errors ? ` · 오류 ${s.errors}장` : '')
      + (activeText ? ` · ${activeText}` : '');
  } catch {
    el.textContent = 'AI 분석 데이터가 아직 없습니다 (워커 첫 스캔 전)';
  }
}

async function loadPeople() {
  const el = document.getElementById('people-content');
  try {
    const people = await api.get('/api/admin/people');
    if (!people.length) {
      el.innerHTML = `
        <div class="empty-state">
          <h3>등록된 인물이 없습니다</h3>
          <p>"+ 새 인물"로 인물을 만들고, "미분류 얼굴"에서 얼굴을 지정하세요</p>
        </div>`;
      return;
    }
    el.innerHTML = `
      <input type="search" id="people-search" class="form-input" placeholder="🔍 인물 이름 검색"
             style="max-width:260px;margin-bottom:14px">
      <div id="people-grid-wrap"></div>`;

    const wrap = document.getElementById('people-grid-wrap');
    function renderGrid(list) {
      if (!list.length) {
        wrap.innerHTML = '<p class="text-muted">검색 결과가 없습니다.</p>';
        return;
      }
      wrap.innerHTML = `<div class="people-grid">${list.map(personCard).join('')}</div>`;
      wrap.querySelectorAll('.person-card').forEach(card => {
        card.addEventListener('click', () => window.navigate(`/admin/people/${card.dataset.id}`));
      });
    }
    renderGrid(people);

    document.getElementById('people-search').addEventListener('input', e => {
      const q = e.target.value.trim().toLowerCase();
      renderGrid(q ? people.filter(p => p.name.toLowerCase().includes(q)) : people);
    });
  } catch (e) {
    el.innerHTML = `<div class="alert alert-error">${esc(e.message)}</div>`;
  }
}

function personCard(p) {
  const cover = p.cover_face_id
    ? `<img src="/api/admin/faces/${p.cover_face_id}/crop" alt="" loading="lazy">`
    : '👤';
  return `
    <div class="person-card" data-id="${p.id}">
      <div class="person-cover">${cover}</div>
      <div class="person-info">
        <div class="person-name" title="${esc(p.name)}">${esc(p.name)}</div>
        <div class="person-meta">확정 ${p.labeled_count} · 추정 ${p.matched_count}</div>
      </div>
    </div>`;
}

// ── 미분류 얼굴 (/admin/people/unassigned) ────────────────────────────

const PAGE_SIZE = 100;
let _selected = new Set();
let _mode = 'default';       // 'default' | 'similar'
let _similarSeed = null;     // { faceId, photoPath } — 'similar' 모드에서 기준 얼굴
let _offset = 0;

export async function renderUnassignedFaces() {
  _selected = new Set();
  _mode = 'default';
  _similarSeed = null;
  _offset = 0;

  renderAdminShell(`
    <div class="page-header">
      <div>
        <h1 class="page-title">미분류 얼굴</h1>
        <p class="page-subtitle">얼굴을 클릭해 선택한 뒤 인물을 지정하거나 무시 처리합니다. 카드에 🔍를 누르면 비슷한 얼굴순으로 다시 정렬됩니다</p>
      </div>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <select id="assign-person" class="form-input" style="width:auto"></select>
        <button class="btn btn-primary" id="btn-assign" disabled>선택 지정</button>
        <button class="btn btn-ghost" id="btn-ignore" disabled>선택 무시</button>
      </div>
    </div>
    <div id="similar-banner" style="display:none;margin-bottom:10px"></div>
    <div id="faces-content"><div class="loading"></div></div>
    <div style="margin-top:16px;text-align:center">
      <button class="btn btn-ghost" id="btn-more" style="display:none">더 보기</button>
    </div>
  `, '/admin/people');

  await loadPeopleOptions();

  document.getElementById('btn-assign').addEventListener('click', handleAssignClick);
  document.getElementById('btn-ignore').addEventListener('click', () => labelSelected(null));

  document.getElementById('btn-more').addEventListener('click', () => { _offset += PAGE_SIZE; loadFaces(); });
  await loadFaces();
}

async function loadPeopleOptions(selectPersonId) {
  const select = document.getElementById('assign-person');
  try {
    const people = await api.get('/api/admin/people');
    select.innerHTML = [
      `<option value="__new__">+ 새 인물 생성</option>`,
      ...people.map(p => `<option value="${p.id}">${esc(p.name)} (${p.labeled_count}/${p.matched_count})</option>`),
    ].join('');
    if (selectPersonId != null) select.value = String(selectPersonId);
  } catch (e) { alert(e.message); }
}

async function handleAssignClick() {
  const select = document.getElementById('assign-person');
  if (select.value === '__new__') {
    const name = prompt('생성할 인물 이름을 입력하세요');
    if (!name?.trim()) return;
    let person;
    try {
      person = await api.post('/api/admin/people', { name: name.trim() });
    } catch (e) { alert(e.message); return; }
    await loadPeopleOptions(person.id);
    await labelSelected(person.id);
    return;
  }
  const pid = Number(select.value);
  if (pid) await labelSelected(pid);
}

function enterSimilarMode(faceId, photoPath) {
  _mode = 'similar';
  _similarSeed = { faceId, photoPath };
  _selected.clear();
  renderSimilarBanner();
  loadFaces();
}

function enterDefaultMode() {
  _mode = 'default';
  _similarSeed = null;
  _offset = 0;
  _selected.clear();
  renderSimilarBanner();
  loadFaces();
}

function renderSimilarBanner() {
  const el = document.getElementById('similar-banner');
  if (_mode !== 'similar') { el.style.display = 'none'; el.innerHTML = ''; return; }
  el.style.display = '';
  el.innerHTML = `
    <div class="alert" style="display:flex;justify-content:space-between;align-items:center;gap:8px">
      <span>선택한 얼굴과 비슷한 순서로 정렬 중 — <span class="text-muted">${esc(_similarSeed.photoPath)}</span></span>
      <button class="btn btn-ghost btn-sm" id="btn-exit-similar">기본 목록으로</button>
    </div>`;
  document.getElementById('btn-exit-similar').addEventListener('click', enterDefaultMode);
}

async function loadFaces() {
  const el = document.getElementById('faces-content');
  try {
    const { faces } = _mode === 'similar'
      ? await api.get(`/api/admin/faces/${_similarSeed.faceId}/similar?limit=200`)
      : await api.get(`/api/admin/faces/unassigned?limit=${PAGE_SIZE}&offset=${_offset}`);

    if (_mode === 'similar' || _offset === 0) {
      el.innerHTML = faces.length
        ? `<div class="face-grid" id="face-grid"></div>`
        : `<div class="empty-state"><h3>미분류 얼굴이 없습니다</h3>
           <p>모든 얼굴이 인물에 지정됐거나, 아직 스캔 전입니다</p></div>`;
    }
    const grid = document.getElementById('face-grid');
    if (grid) {
      grid.insertAdjacentHTML('beforeend', faces.map(faceCard).join(''));
      grid.querySelectorAll('.face-card:not([data-bound])').forEach(card => {
        card.dataset.bound = '1';
        const id = Number(card.dataset.face);
        card.addEventListener('click', (e) => {
          if (e.target.closest('[data-act="similar"]')) return;
          if (_selected.has(id)) { _selected.delete(id); card.classList.remove('selected'); }
          else                   { _selected.add(id);    card.classList.add('selected');    }
          updateToolbar();
        });
        card.querySelector('[data-act="similar"]').addEventListener('click', (e) => {
          e.stopPropagation();
          enterSimilarMode(id, card.dataset.photo);
        });
      });
    }
    document.getElementById('btn-more').style.display =
      (_mode === 'default' && faces.length === PAGE_SIZE) ? '' : 'none';
  } catch (e) {
    el.innerHTML = `<div class="alert alert-error">${esc(e.message)}</div>`;
  }
}

function faceCard(f) {
  const score = f.score != null
    ? `<span class="face-score">${Math.round(f.score * 100)}%</span>` : '';
  return `
    <div class="face-card" data-face="${f.face_id}" data-photo="${esc(f.photo_path)}" title="${esc(f.photo_path)}">
      <img src="/api/admin/faces/${f.face_id}/crop" alt="" loading="lazy">
      ${score}
      <div class="face-actions">
        <button class="btn btn-sm btn-ghost" data-act="similar" title="비슷한 얼굴 찾기">🔍</button>
      </div>
    </div>`;
}

function updateToolbar() {
  const n = _selected.size;
  document.getElementById('btn-assign').disabled = n === 0;
  document.getElementById('btn-ignore').disabled = n === 0;
  document.getElementById('btn-assign').textContent = n ? `선택 지정 (${n})` : '선택 지정';
  document.getElementById('btn-ignore').textContent = n ? `선택 무시 (${n})` : '선택 무시';
}

async function labelSelected(personId) {
  const ids = [..._selected];
  if (!ids.length) return;
  try {
    await api.post('/api/admin/faces/batch-label', { face_ids: ids, person_id: personId });
    ids.forEach(id => document.querySelector(`.face-card[data-face="${id}"]`)?.remove());
    _selected.clear();
    updateToolbar();
  } catch (e) { alert(e.message); }
}

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
    const running = s.recent_jobs.find(j => j.status === 'running' || j.status === 'pending');
    el.textContent =
      `분석 사진 ${s.photos.toLocaleString()}장 · 얼굴 ${s.faces.toLocaleString()}개 · 라벨 ${s.labels.toLocaleString()}개`
      + (s.errors ? ` · 오류 ${s.errors}장` : '')
      + (running ? ` · ${running.type} 작업 ${running.status === 'running' ? '실행 중' : '대기 중'}` : '');
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
    el.innerHTML = `<div class="people-grid">${people.map(personCard).join('')}</div>`;
    el.querySelectorAll('.person-card').forEach((card, i) => {
      card.addEventListener('click', () => window.navigate(`/admin/people/${people[i].id}`));
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
    <div class="person-card">
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

export async function renderUnassignedFaces() {
  _selected = new Set();
  renderAdminShell(`
    <div class="page-header">
      <div>
        <h1 class="page-title">미분류 얼굴</h1>
        <p class="page-subtitle">얼굴을 클릭해 선택한 뒤 인물을 지정하거나 무시 처리합니다</p>
      </div>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <select id="assign-person" class="form-input" style="width:auto"></select>
        <button class="btn btn-primary" id="btn-assign" disabled>선택 지정</button>
        <button class="btn btn-ghost" id="btn-ignore" disabled>선택 무시</button>
      </div>
    </div>
    <div id="faces-content"><div class="loading"></div></div>
    <div style="margin-top:16px;text-align:center">
      <button class="btn btn-ghost" id="btn-more" style="display:none">더 보기</button>
    </div>
  `, '/admin/people');

  const select = document.getElementById('assign-person');
  try {
    const people = await api.get('/api/admin/people');
    select.innerHTML = people.length
      ? people.map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join('')
      : '<option value="">인물 없음 — 먼저 인물을 만드세요</option>';
  } catch (e) { alert(e.message); }

  document.getElementById('btn-assign').addEventListener('click', () => {
    const pid = Number(select.value);
    if (pid) labelSelected(pid);
  });
  document.getElementById('btn-ignore').addEventListener('click', () => labelSelected(null));

  let offset = 0;
  const moreBtn = document.getElementById('btn-more');
  moreBtn.addEventListener('click', () => { offset += PAGE_SIZE; loadFaces(offset); });
  await loadFaces(0);
}

async function loadFaces(offset) {
  const el = document.getElementById('faces-content');
  try {
    const { faces } = await api.get(`/api/admin/faces/unassigned?limit=${PAGE_SIZE}&offset=${offset}`);
    if (offset === 0) {
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
        card.addEventListener('click', () => {
          const id = Number(card.dataset.face);
          if (_selected.has(id)) { _selected.delete(id); card.classList.remove('selected'); }
          else                   { _selected.add(id);    card.classList.add('selected');    }
          updateToolbar();
        });
      });
    }
    document.getElementById('btn-more').style.display =
      faces.length === PAGE_SIZE ? '' : 'none';
  } catch (e) {
    el.innerHTML = `<div class="alert alert-error">${esc(e.message)}</div>`;
  }
}

function faceCard(f) {
  return `
    <div class="face-card" data-face="${f.face_id}" title="${esc(f.photo_path)}">
      <img src="/api/admin/faces/${f.face_id}/crop" alt="" loading="lazy">
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
  try {
    for (const id of ids) {
      await api.post(`/api/admin/faces/${id}/label`, { person_id: personId });
      document.querySelector(`.face-card[data-face="${id}"]`)?.remove();
    }
    _selected.clear();
    updateToolbar();
  } catch (e) { alert(e.message); }
}

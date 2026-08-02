import { api } from '../api.js';
import { renderAdminShell } from '../layout.js';
import { esc } from '../utils.js';
import { openLightbox } from '../lightbox.js';

const SOURCE_LABELS = { ai: 'AI', manual: '직접추가', path: '폴더명', location: '위치' };
const EDITABLE_SOURCES = new Set(['ai', 'manual', 'path']);

// ── 태그 목록 (/admin/tags) ────────────────────────────────────────────

export async function renderAdminTags() {
  renderAdminShell(`
    <div class="page-header">
      <div>
        <h1 class="page-title">태그</h1>
        <p class="page-subtitle" id="tags-status-line">불러오는 중...</p>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <button class="btn btn-ghost" id="btn-tag-backfill">AI 태그 재계산</button>
      </div>
    </div>
    <div style="display:flex;gap:14px;align-items:center;flex-wrap:wrap;margin-bottom:14px">
      <input type="search" id="tags-search" class="form-input" placeholder="🔍 태그 검색" style="max-width:260px">
      <div class="view-toggle" id="tags-source-filter">
        <button type="button" class="btn btn-ghost btn-sm active" data-source="all">전체</button>
        <button type="button" class="btn btn-ghost btn-sm" data-source="ai">AI</button>
        <button type="button" class="btn btn-ghost btn-sm" data-source="manual">직접추가</button>
        <button type="button" class="btn btn-ghost btn-sm" data-source="path">폴더명</button>
        <button type="button" class="btn btn-ghost btn-sm" data-source="location">위치</button>
      </div>
    </div>
    <div id="tags-content"><div class="loading"></div></div>
  `, '/admin/tags');

  document.getElementById('btn-tag-backfill').addEventListener('click', triggerTagBackfill);
  loadAiStatusLine();

  const wrap = document.getElementById('tags-content');
  let tags = [];
  try {
    ({ tags } = await api.get('/api/admin/tags'));
  } catch (e) {
    wrap.innerHTML = `<div class="alert alert-error">${esc(e.message)}</div>`;
    return;
  }

  let sourceFilter = 'all';

  function renderGrid(list) {
    if (!list.length) {
      wrap.innerHTML = `
        <div class="empty-state">
          <h3>태그가 없습니다</h3>
          <p>AI 야간 스캔이 진행되면 자동으로 태그가 채워집니다</p>
        </div>`;
      return;
    }
    wrap.innerHTML = `<div class="people-grid">${list.map(tagCard).join('')}</div>`;
    wrap.querySelectorAll('.person-card[data-tag]').forEach(card => {
      card.addEventListener('click', () => {
        const tag = card.dataset.tag, source = card.dataset.source;
        window.navigate(`/admin/tags/photos?tag=${encodeURIComponent(tag)}&source=${source}`);
      });
    });
  }

  function applyFilters() {
    const q = document.getElementById('tags-search').value.trim().toLowerCase();
    let list = tags;
    if (sourceFilter !== 'all') list = list.filter(t => t.source === sourceFilter);
    if (q) list = list.filter(t => t.tag.toLowerCase().includes(q));
    renderGrid(list);
  }

  document.getElementById('tags-search').addEventListener('input', applyFilters);
  document.getElementById('tags-source-filter').addEventListener('click', e => {
    const btn = e.target.closest('[data-source]');
    if (!btn) return;
    document.querySelectorAll('#tags-source-filter [data-source]').forEach(b => b.classList.toggle('active', b === btn));
    sourceFilter = btn.dataset.source;
    applyFilters();
  });

  applyFilters();
}

function tagCard(t) {
  const cover = t.sample_path
    ? `<img src="/api/admin/thumb?path=${encodeURIComponent(t.sample_path)}&size=small" alt="" loading="lazy">`
    : '🏷️';
  return `
    <div class="person-card" data-tag="${esc(t.tag)}" data-source="${t.source}">
      <div class="person-cover">${cover}</div>
      <div class="person-info">
        <div class="person-name" title="${esc(t.tag)}">${esc(t.tag)}</div>
        <div class="person-meta">${SOURCE_LABELS[t.source] || t.source} · ${t.count.toLocaleString()}장</div>
      </div>
    </div>`;
}

async function loadAiStatusLine() {
  const el = document.getElementById('tags-status-line');
  if (!el) return;
  try {
    const s = await api.get('/api/admin/ai/status');
    const active = s.recent_jobs.find(
      j => j.type === 'tag_backfill' && (j.status === 'running' || j.status === 'pending')
    );
    el.textContent = active
      ? `AI 태그 재계산 ${active.status === 'running' ? '실행 중' : '대기 중'}…`
      : '어휘·threshold를 바꾼 뒤에는 "AI 태그 재계산"을 다시 실행하세요';
  } catch {
    el.textContent = 'AI 분석 데이터가 아직 없습니다 (워커 첫 스캔 전)';
  }
}

async function triggerTagBackfill() {
  try {
    const r = await api.post('/api/admin/ai/jobs', { type: 'tag_backfill' });
    alert(r.duplicated
      ? `이미 대기/실행 중인 재계산 작업이 있습니다 (#${r.id})`
      : `AI 태그 재계산을 요청했습니다 (#${r.id}). AI 워커가 곧 처리합니다.`);
    loadAiStatusLine();
  } catch (e) { alert(e.message); }
}

// ── 태그별 사진 그리드 (/admin/tags/photos?tag=...&source=...) ─────────

export async function renderAdminTagPhotos() {
  const params = new URLSearchParams(location.search);
  const tag = params.get('tag');
  const source = params.get('source');
  if (!tag || !source) { window.navigate('/admin/tags', true); return; }

  renderAdminShell(`
    <div class="page-header">
      <div>
        <h1 class="page-title">${esc(tag)}</h1>
        <p class="page-subtitle" id="tag-photos-subtitle">불러오는 중...</p>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        ${EDITABLE_SOURCES.has(source) ? '<button class="btn btn-ghost" id="btn-rename-tag">이름 변경</button>' : ''}
        <a href="/admin/tags" class="btn btn-ghost" data-link>← 태그 목록</a>
      </div>
    </div>
    <div id="tag-photos-content"><div class="loading"></div></div>
  `, '/admin/tags');

  const contentEl = document.getElementById('tag-photos-content');
  let photos = [];
  try {
    const res = await api.get(`/api/admin/tags/${encodeURIComponent(tag)}/photos?source=${source}`);
    photos = res.photos;
  } catch (e) {
    contentEl.innerHTML = `<div class="alert alert-error">${esc(e.message)}</div>`;
    return;
  }

  const subtitle = document.getElementById('tag-photos-subtitle');
  const setSubtitle = () => {
    subtitle.textContent = `${SOURCE_LABELS[source] || source} · ${photos.length.toLocaleString()}장`;
  };
  setSubtitle();

  const renameBtn = document.getElementById('btn-rename-tag');
  if (renameBtn) {
    renameBtn.addEventListener('click', async () => {
      const newTag = prompt('새 태그 이름을 입력하세요', tag);
      if (!newTag?.trim() || newTag.trim() === tag) return;
      try {
        await api.put(`/api/admin/tags/${encodeURIComponent(tag)}/rename`, {
          new_tag: newTag.trim(), source,
        });
        window.navigate(`/admin/tags/photos?tag=${encodeURIComponent(newTag.trim())}&source=${source}`, true);
      } catch (e) { alert(e.message); }
    });
  }

  function refresh() {
    if (!photos.length) {
      contentEl.className = '';
      contentEl.innerHTML = `<div class="empty-state"><h3>사진이 없습니다</h3></div>`;
      return;
    }
    contentEl.className = 'photo-grid';
    contentEl.innerHTML = photos.map((p, i) => `
      <div class="photo-thumb" data-idx="${i}" title="${esc(p.file_path)}">
        <img src="${p.thumb_small_url}" alt="" loading="lazy" onerror="this.style.opacity='0.3'">
      </div>`).join('');
  }

  contentEl.addEventListener('click', e => {
    const item = e.target.closest('[data-idx]');
    if (!item) return;
    const lightboxOptions = {
      extraAction: {
        label: '+ 태그 추가',
        onClick: path => openAddTagModal(path),
      },
    };
    if (EDITABLE_SOURCES.has(source)) {
      lightboxOptions.deleteLabel = '태그 삭제';
      lightboxOptions.deleteConfirmMsg = '이 사진에서 이 태그를 삭제할까요?';
      lightboxOptions.onDelete = async path => {
        await api.delete(
          `/api/admin/tags/${encodeURIComponent(tag)}/photo?path=${encodeURIComponent(path)}&source=${source}`
        );
        photos = photos.filter(p => p.file_path !== path);
        setSubtitle();
        refresh();
      };
    }
    openLightbox(photos.map(p => p.file_path), Number(item.dataset.idx), lightboxOptions);
  });

  refresh();
}

// ── 수동 태그 추가 모달 ──────────────────────────────────────────────────

async function openAddTagModal(photoPath) {
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  // 라이트박스(.lightbox-overlay, z-index:500)가 열린 채로 이 모달이 뜨므로
  // .modal-overlay의 기본 z-index(300)로는 라이트박스 뒤에 가려 보이지도, 클릭도
  // 안 된다 — 인라인으로 라이트박스보다 높게 지정.
  overlay.style.zIndex = '600';
  overlay.innerHTML = `
    <div class="modal" style="max-width:360px">
      <p class="modal-title">태그 추가</p>
      <p class="text-muted text-sm" style="margin:0 0 10px">${esc(photoPath)}</p>
      <select id="add-tag-select" class="form-input"><option>불러오는 중...</option></select>
      <div class="modal-actions">
        <button class="btn btn-ghost" id="modal-cancel">취소</button>
        <button class="btn btn-primary" id="modal-confirm">추가</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);
  // 라이트박스의 document 레벨 keydown 리스너(화살표=사진 이동, Esc=닫기)가
  // select 조작 중에도 함께 반응하지 않도록 이 오버레이에서 전파를 막는다.
  overlay.addEventListener('keydown', e => e.stopPropagation());
  overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });
  overlay.querySelector('#modal-cancel').addEventListener('click', () => overlay.remove());

  overlay.querySelector('#modal-confirm').addEventListener('click', async () => {
    const tag = overlay.querySelector('#add-tag-select').value;
    if (!tag) return;
    try {
      const r = await api.post('/api/admin/tags/manual', { photo_path: photoPath, tag });
      overlay.remove();
      alert(r.added ? `"${tag}" 태그를 추가했습니다.` : `이미 "${tag}" 태그가 있습니다.`);
    } catch (e) { alert(e.message); }
  });

  try {
    const { vocab } = await api.get('/api/admin/tags/vocab');
    const select = document.getElementById('add-tag-select');
    if (select) {
      select.innerHTML = vocab.map(t => `<option value="${esc(t)}">${esc(t)}</option>`).join('');
    }
  } catch (e) {
    const select = document.getElementById('add-tag-select');
    if (select) select.innerHTML = `<option value="">불러오기 실패</option>`;
  }
}

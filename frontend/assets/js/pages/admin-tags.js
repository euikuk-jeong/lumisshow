import { api } from '../api.js';
import { renderAdminShell } from '../layout.js';
import { esc } from '../utils.js';
import { openLightbox } from '../lightbox.js';
import { openAddTagModal, deleteTagFromPhotos } from '../tag-modal.js';

const SOURCE_LABELS = { ai: 'AI', manual: '직접추가', path: '폴더명', location: '위치' };
const EDITABLE_SOURCES = new Set(['ai', 'manual', 'path']);

// 태그 목록 검색어·소스 필터 — 태그별 사진 화면에서 돌아왔을 때 복원하기 위해
// 모듈 스코프에 보존한다(admin-people.js의 _mode/_offset과 동일한 패턴).
let _tagsSearch = '';
let _tagsSourceFilter = 'all';

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
        <button class="btn btn-ghost" id="btn-path-tag-reset">폴더 태그 재계산</button>
        <button class="btn btn-ghost" id="btn-location-tag-reset">위치 태그 한글 재번역</button>
      </div>
    </div>
    <div style="display:flex;gap:14px;align-items:center;flex-wrap:wrap;margin-bottom:14px">
      <input type="search" id="tags-search" class="form-input" placeholder="🔍 태그 검색" style="max-width:260px" value="${esc(_tagsSearch)}">
      <div class="view-toggle" id="tags-source-filter">
        <button type="button" class="btn btn-ghost btn-sm${_tagsSourceFilter === 'all' ? ' active' : ''}" data-source="all">전체</button>
        <button type="button" class="btn btn-ghost btn-sm${_tagsSourceFilter === 'ai' ? ' active' : ''}" data-source="ai">AI</button>
        <button type="button" class="btn btn-ghost btn-sm${_tagsSourceFilter === 'manual' ? ' active' : ''}" data-source="manual">직접추가</button>
        <button type="button" class="btn btn-ghost btn-sm${_tagsSourceFilter === 'path' ? ' active' : ''}" data-source="path">폴더명</button>
        <button type="button" class="btn btn-ghost btn-sm${_tagsSourceFilter === 'location' ? ' active' : ''}" data-source="location">위치</button>
      </div>
    </div>
    <div id="tags-content"><div class="loading"></div></div>
  `, '/admin/tags');

  document.getElementById('btn-tag-backfill').addEventListener('click', triggerTagBackfill);
  document.getElementById('btn-path-tag-reset').addEventListener('click', triggerPathTagReset);
  document.getElementById('btn-location-tag-reset').addEventListener('click', triggerLocationTagReset);
  loadAiStatusLine();

  const wrap = document.getElementById('tags-content');
  let tags = [];
  try {
    ({ tags } = await api.get('/api/admin/tags'));
  } catch (e) {
    wrap.innerHTML = `<div class="alert alert-error">${esc(e.message)}</div>`;
    return;
  }

  // ai.db 미구성 등으로 설정 조회가 실패해도 태그 목록 자체는 정상 표시해야 함
  // (fail-open — 카테고리 전부 켜진 것으로 취급, admin-people.js와 동일 원칙).
  let disabledSources = new Set();
  try {
    const settings = await api.get('/api/admin/ai/settings');
    if (settings.ai_tag_enabled === false) disabledSources.add('ai');
    if (settings.path_enabled === false) disabledSources.add('path');
    if (settings.location_enabled === false) disabledSources.add('location');
  } catch { /* fail-open */ }
  // 꺼진 카테고리는 DB에 남아있어도 태그 탭에서 제외(pill도 비활성화, 아래 참고)
  tags = tags.filter(t => !disabledSources.has(t.source));
  document.querySelectorAll('#tags-source-filter [data-source]').forEach(btn => {
    if (disabledSources.has(btn.dataset.source)) btn.disabled = true;
  });

  let sourceFilter = _tagsSourceFilter;

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
    _tagsSearch = document.getElementById('tags-search').value;
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
    sourceFilter = _tagsSourceFilter = btn.dataset.source;
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
    const isActive = j => j.status === 'running' || j.status === 'pending';
    const activeBackfill = s.recent_jobs.find(j => j.type === 'tag_backfill' && isActive(j));
    const activePathReset = s.recent_jobs.find(j => j.type === 'path_tag_reset' && isActive(j));
    const activeLocationReset = s.recent_jobs.find(j => j.type === 'location_tag_reset' && isActive(j));
    if (activeBackfill) {
      el.textContent = `AI 태그 재계산 ${activeBackfill.status === 'running' ? '실행 중' : '대기 중'}…`;
    } else if (activePathReset) {
      el.textContent = `폴더 태그 재계산 ${activePathReset.status === 'running' ? '실행 중' : '대기 중'}…`;
    } else if (activeLocationReset) {
      el.textContent = `위치 태그 한글 재번역 ${activeLocationReset.status === 'running' ? '실행 중' : '대기 중'}…`;
    } else {
      el.textContent = '어휘·threshold를 바꾼 뒤에는 "AI 태그 재계산"을 다시 실행하세요';
    }
  } catch {
    el.textContent = 'AI 분석 데이터가 아직 없습니다 (워커 첫 스캔 전)';
  }
}

async function triggerPathTagReset() {
  if (!confirm('기존 폴더명 태그를 모두 지우고 처음부터 다시 계산할까요?\n(Kiwi 사전/로직이 바뀐 경우에만 필요합니다)')) return;
  try {
    const r = await api.post('/api/admin/ai/jobs', { type: 'path_tag_reset' });
    alert(r.duplicated
      ? `이미 대기/실행 중인 재계산 작업이 있습니다 (#${r.id})`
      : `폴더 태그 재계산을 요청했습니다 (#${r.id}). AI 워커가 곧 처리합니다.`);
    loadAiStatusLine();
  } catch (e) { alert(e.message); }
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

async function triggerLocationTagReset() {
  try {
    const r = await api.post('/api/admin/ai/jobs', { type: 'location_tag_reset' });
    alert(r.duplicated
      ? `이미 대기/실행 중인 재계산 작업이 있습니다 (#${r.id})`
      : `위치 태그 한글 재번역을 요청했습니다 (#${r.id}). AI 워커가 곧 처리합니다.`);
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
    <div class="browse-selection-bar" id="tag-selection-bar">
      <span id="tag-selection-count">0개 선택됨</span>
      <div style="display:flex;gap:8px">
        <button class="btn btn-primary" id="btn-bulk-add-tag">+ 태그 추가</button>
        ${source === 'manual' ? '<button class="btn btn-ghost" id="btn-bulk-delete-tag">태그 삭제</button>' : ''}
      </div>
    </div>
  `, '/admin/tags');

  const contentEl = document.getElementById('tag-photos-content');
  const subtitle = document.getElementById('tag-photos-subtitle');
  const state = { selected: new Set() };
  let photos = [];

  const setSubtitle = () => {
    subtitle.textContent = `${SOURCE_LABELS[source] || source} · ${photos.length.toLocaleString()}장`;
  };

  function updateSelectionBar() {
    const count = state.selected.size;
    document.getElementById('tag-selection-count').textContent = `${count.toLocaleString()}개 선택됨`;
    document.getElementById('tag-selection-bar').classList.toggle('visible', count > 0);
  }

  function refresh() {
    if (!photos.length) {
      contentEl.className = '';
      contentEl.innerHTML = `<div class="empty-state"><h3>사진이 없습니다</h3></div>`;
      return;
    }
    contentEl.className = 'photo-grid';
    contentEl.innerHTML = photos.map((p, i) => `
      <div class="photo-thumb selectable${state.selected.has(p.file_path) ? ' selected' : ''}"
           data-idx="${i}" data-path="${esc(p.file_path)}" title="${esc(p.file_path)}">
        <img src="${p.thumb_small_url}" alt="" loading="lazy" onerror="this.style.opacity='0.3'">
        <input type="checkbox" ${state.selected.has(p.file_path) ? 'checked' : ''}>
      </div>`).join('');
  }

  async function loadPhotos() {
    const res = await api.get(`/api/admin/tags/${encodeURIComponent(tag)}/photos?source=${source}`);
    photos = res.photos;
    state.selected.clear();
    updateSelectionBar();
    setSubtitle();
    refresh();
  }

  try {
    await loadPhotos();
  } catch (e) {
    contentEl.innerHTML = `<div class="alert alert-error">${esc(e.message)}</div>`;
    return;
  }

  document.getElementById('btn-bulk-add-tag').addEventListener('click', () => {
    if (!state.selected.size) return;
    openAddTagModal(Array.from(state.selected), {
      onDone: ({ tag: newTag, success, fail, firstError }) => {
        state.selected.clear();
        updateSelectionBar();
        refresh();
        alert(fail
          ? `"${newTag}" ${success}장 추가, ${fail}장 실패${firstError ? `\n(${firstError})` : ''}`
          : `"${newTag}" ${success}장에 추가했습니다.`);
      },
    });
  });

  const bulkDeleteBtn = document.getElementById('btn-bulk-delete-tag');
  if (bulkDeleteBtn) {
    bulkDeleteBtn.addEventListener('click', async () => {
      const paths = Array.from(state.selected);
      if (!paths.length) return;
      if (!confirm(`선택한 ${paths.length.toLocaleString()}장에서 "${tag}" 태그를 삭제할까요?`)) return;
      bulkDeleteBtn.disabled = true;
      try {
        const { success, fail, firstError } = await deleteTagFromPhotos(paths, tag, source, {
          onProgress: (i, total) => { bulkDeleteBtn.textContent = `삭제 중... (${i}/${total})`; },
        });
        await loadPhotos();
        alert(fail
          ? `${success}장 삭제, ${fail}장 실패${firstError ? `\n(${firstError})` : ''}`
          : `${success}장에서 태그를 삭제했습니다.`);
      } catch (e) {
        alert(e.message);
      } finally {
        bulkDeleteBtn.disabled = false;
        bulkDeleteBtn.textContent = '태그 삭제';
      }
    });
  }

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

  function toggleSelect(path) {
    if (state.selected.has(path)) state.selected.delete(path);
    else state.selected.add(path);
    updateSelectionBar();
    const item = contentEl.querySelector(`.selectable[data-path="${CSS.escape(path)}"]`);
    if (item) {
      item.classList.toggle('selected', state.selected.has(path));
      const cb = item.querySelector('input[type=checkbox]');
      if (cb) cb.checked = state.selected.has(path);
    }
  }

  contentEl.addEventListener('click', e => {
    // 체크박스 클릭 → 선택 토글만 하고 라이트박스는 열지 않는다.
    if (e.target.type === 'checkbox') {
      const item = e.target.closest('.selectable[data-path]');
      if (item) toggleSelect(item.dataset.path);
      return;
    }

    const item = e.target.closest('[data-idx]');
    if (!item) return;
    const lightboxOptions = {
      extraAction: {
        label: '+ 태그 추가',
        onClick: path => openAddTagModal([path]),
      },
      getSelectionState: path => ({
        isSelected: state.selected.has(path),
        selectedCount: state.selected.size,
        totalCount: photos.length,
      }),
      onToggleSelect: path => toggleSelect(path),
    };
    if (EDITABLE_SOURCES.has(source)) {
      lightboxOptions.deleteLabel = '태그 삭제';
      lightboxOptions.deleteConfirmMsg = '이 사진에서 이 태그를 삭제할까요?';
      lightboxOptions.onDelete = async path => {
        await api.delete(
          `/api/admin/tags/${encodeURIComponent(tag)}/photo?path=${encodeURIComponent(path)}&source=${source}`
        );
        photos = photos.filter(p => p.file_path !== path);
        state.selected.delete(path);
        updateSelectionBar();
        setSubtitle();
        refresh();
      };
    }
    openLightbox(photos.map(p => p.file_path), Number(item.dataset.idx), lightboxOptions);
  });
}

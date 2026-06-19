import { api } from '../api.js';
import { renderAdminShell } from '../layout.js';
import { esc } from '../utils.js';
import { openLightbox } from '../lightbox.js';

export async function renderAdminBrowse() {
  const params  = new URLSearchParams(location.search);
  const albumId = params.get('album_id');
  const backUrl = albumId ? `/admin/albums/${albumId}` : '/admin';

  renderAdminShell(`
    <a href="${backUrl}" class="page-back" data-link>← ${albumId ? '앨범으로 돌아가기' : '앨범 목록'}</a>
    <div class="page-header">
      <h1 class="page-title">사진 탐색${albumId ? ' — 추가할 사진 선택' : ''}</h1>
    </div>
    <div class="browse-toolbar">
      <input id="search-input" type="text" class="form-input browse-search" placeholder="파일명으로 검색...">
      <button class="btn btn-ghost btn-sm" id="btn-search">검색</button>
      <button class="btn btn-ghost btn-sm" id="btn-clear-search" style="display:none">초기화</button>
      <div class="browse-toolbar-right">
        <select id="sort-select" class="form-input" style="width:auto">
          <option value="name-asc">파일명 ↑</option>
          <option value="name-desc">파일명 ↓</option>
          <option value="date-asc">날짜 ↑</option>
          <option value="date-desc">날짜 ↓</option>
        </select>
        <div class="view-toggle">
          <button id="btn-view-grid" class="btn btn-ghost btn-sm active" title="그리드 보기">⊞</button>
          <button id="btn-view-list" class="btn btn-ghost btn-sm" title="리스트 보기">☰</button>
        </div>
      </div>
    </div>
    <div id="browse-content"><div class="loading"></div></div>
    <div class="browse-selection-bar" id="selection-bar">
      <span id="selection-count">0개 선택됨</span>
      <button class="btn btn-primary" id="btn-add-selected" ${!albumId ? 'disabled' : ''}>
        ${albumId ? '선택 사진 추가' : '앨범을 선택해 사진 추가'}
      </button>
    </div>
  `, '/admin/browse');

  const state = {
    path: '',
    selected: new Set(),
    viewMode: 'grid',
    sortBy: 'name-asc',
    lastFolders: [],
    lastPhotos: [],
    lastPath: null,
  };

  // 폴더/브레드크럼/사진 이벤트 위임
  document.getElementById('browse-content').addEventListener('click', e => {
    const folder = e.target.closest('.folder-item');
    if (folder) { loadBrowse(state, folder.dataset.path); return; }
    const crumb = e.target.closest('[data-nav-path]');
    if (crumb) { e.preventDefault(); loadBrowse(state, crumb.dataset.navPath); return; }
    if (e.target.closest('#btn-select-all')) { selectAll(state); return; }
    if (e.target.closest('#btn-deselect-all')) { deselectAll(state); return; }

    // 체크박스 클릭 → 선택 토글
    if (e.target.type === 'checkbox') {
      const selectable = e.target.closest('.selectable[data-path]');
      if (selectable) toggleSelect(selectable, state);
      return;
    }

    // 그 외(이미지 영역) → 라이트박스
    const selectable = e.target.closest('.selectable[data-path]');
    if (selectable) {
      const allPaths = [...document.querySelectorAll('#browse-content .selectable[data-path]')]
        .map(el => el.dataset.path);
      const idx = allPaths.indexOf(selectable.dataset.path);
      if (idx !== -1) openLightbox(allPaths, idx, {
        getSelectionState: path => ({
          isSelected: state.selected.has(path),
          selectedCount: state.lastPhotos.filter(p => state.selected.has(p.path)).length,
          totalCount: state.lastPhotos.length,
        }),
        onToggleSelect: path => {
          if (state.selected.has(path)) {
            state.selected.delete(path);
          } else {
            state.selected.add(path);
          }
          updateSelectionBar(state.selected.size);
          updatePhotoCount(state);
          const item = document.querySelector(`#browse-content .selectable[data-path="${CSS.escape(path)}"]`);
          if (item) {
            item.classList.toggle('selected', state.selected.has(path));
            const cb = item.querySelector('input[type=checkbox]');
            if (cb) cb.checked = state.selected.has(path);
          }
        },
      });
    }
  });

  document.getElementById('search-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') doSearch(state);
  });
  document.getElementById('btn-search').addEventListener('click', () => doSearch(state));
  document.getElementById('btn-clear-search').addEventListener('click', () => {
    document.getElementById('search-input').value = '';
    document.getElementById('btn-clear-search').style.display = 'none';
    loadBrowse(state, state.path);
  });

  document.getElementById('sort-select').addEventListener('change', e => {
    state.sortBy = e.target.value;
    renderBrowseResult(state);
  });
  document.getElementById('btn-view-grid').addEventListener('click', () => setViewMode(state, 'grid'));
  document.getElementById('btn-view-list').addEventListener('click', () => setViewMode(state, 'list'));

  if (albumId) {
    document.getElementById('btn-add-selected').addEventListener('click', () => addSelected(albumId, state, backUrl));
  }

  await loadBrowse(state, '');
}

async function loadBrowse(state, path) {
  state.path = path;
  const el = document.getElementById('browse-content');
  el.innerHTML = '<div class="loading"></div>';
  try {
    const data = await api.get(`/api/admin/browse?path=${encodeURIComponent(path)}`);
    state.lastFolders = data.folders;
    state.lastPhotos  = data.photos;
    state.lastPath    = path;
    renderBrowseResult(state);
  } catch (e) {
    el.innerHTML = `<div class="alert alert-error">${esc(e.message)}</div>`;
  }
}

async function doSearch(state) {
  const q = document.getElementById('search-input').value.trim();
  if (!q) return;
  document.getElementById('btn-clear-search').style.display = 'inline-flex';
  const el = document.getElementById('browse-content');
  el.innerHTML = '<div class="loading"></div>';
  try {
    const data = await api.get(`/api/admin/search?q=${encodeURIComponent(q)}&size=200`);
    state.lastFolders = [];
    state.lastPhotos  = data.items;
    state.lastPath    = null;
    renderBrowseResult(state);
  } catch (e) {
    el.innerHTML = `<div class="alert alert-error">${esc(e.message)}</div>`;
  }
}

function sortPhotos(photos, sortBy) {
  const [field, dir] = sortBy.split('-');
  return [...photos].sort((a, b) => {
    const av = field === 'name' ? a.name.toLowerCase() : (a.taken_at || '');
    const bv = field === 'name' ? b.name.toLowerCase() : (b.taken_at || '');
    if (av < bv) return dir === 'asc' ? -1 : 1;
    if (av > bv) return dir === 'asc' ? 1 : -1;
    return 0;
  });
}

function setViewMode(state, mode) {
  state.viewMode = mode;
  document.getElementById('btn-view-grid').classList.toggle('active', mode === 'grid');
  document.getElementById('btn-view-list').classList.toggle('active', mode === 'list');
  renderBrowseResult(state);
}

function renderBrowseResult(state) {
  const { lastFolders: folders, lastPhotos: photos, lastPath: currentPath } = state;
  const el    = document.getElementById('browse-content');
  const sorted = sortPhotos(photos, state.sortBy);

  const breadcrumbHTML = currentPath !== null ? buildBreadcrumb(currentPath) : '';
  const foldersHTML = folders.length
    ? `<div class="folder-list">${folders.map(f =>
        `<div class="folder-item" data-path="${esc(f.path)}">📁 ${esc(f.name)} <span class="text-muted text-sm">(${f.child_count})</span></div>`
      ).join('')}</div>`
    : '';

  let photosHTML;
  if (!sorted.length) {
    photosHTML = '<p class="text-muted text-sm">사진이 없습니다</p>';
  } else if (state.viewMode === 'list') {
    photosHTML = `<div class="photo-list">${sorted.map(p => photoListItem(p, state.selected.has(p.path))).join('')}</div>`;
  } else {
    photosHTML = `<div class="photo-grid">${sorted.map(p => selectableThumb(p, state.selected.has(p.path))).join('')}</div>`;
  }

  const selectedInView = sorted.filter(p => state.selected.has(p.path)).length;
  const headerHTML = sorted.length
    ? `<div class="browse-photos-header">
        <span class="text-muted text-sm" id="browse-photo-count">${selectedInView} / ${sorted.length} 선택</span>
        <div style="display:flex;gap:6px">
          <button id="btn-select-all" class="btn btn-ghost btn-sm">전체 선택</button>
          <button id="btn-deselect-all" class="btn btn-ghost btn-sm">전체 해제</button>
        </div>
       </div>`
    : '';

  el.innerHTML = `
    ${breadcrumbHTML ? `<div class="breadcrumb">${breadcrumbHTML}</div>` : ''}
    ${foldersHTML}
    ${headerHTML}
    ${photosHTML}
  `;
}

function selectAll(state) {
  state.lastPhotos.forEach(p => state.selected.add(p.path));
  renderBrowseResult(state);
  updateSelectionBar(state.selected.size);
}

function deselectAll(state) {
  state.lastPhotos.forEach(p => state.selected.delete(p.path));
  renderBrowseResult(state);
  updateSelectionBar(state.selected.size);
}

function toggleSelect(thumb, state) {
  const path = thumb.dataset.path;
  const cb   = thumb.querySelector('input[type=checkbox]');
  if (state.selected.has(path)) {
    state.selected.delete(path);
    thumb.classList.remove('selected');
    if (cb) cb.checked = false;
  } else {
    state.selected.add(path);
    thumb.classList.add('selected');
    if (cb) cb.checked = true;
  }
  updateSelectionBar(state.selected.size);
  updatePhotoCount(state);
}

function updatePhotoCount(state) {
  const el = document.getElementById('browse-photo-count');
  if (!el) return;
  const selectedInView = state.lastPhotos.filter(p => state.selected.has(p.path)).length;
  el.textContent = `${selectedInView} / ${state.lastPhotos.length} 선택`;
}

function updateSelectionBar(count) {
  document.getElementById('selection-count').textContent = `${count}개 선택됨`;
  document.getElementById('selection-bar').classList.toggle('visible', count > 0);
}

async function addSelected(albumId, state, backUrl) {
  if (state.selected.size === 0) return;
  const btn = document.getElementById('btn-add-selected');
  btn.disabled = true;
  btn.textContent = '추가 중...';
  try {
    await api.post(`/api/admin/albums/${albumId}/photos`, {
      photo_paths: Array.from(state.selected),
    });
    window.navigate(backUrl);
  } catch (err) {
    alert(err.message);
    btn.disabled = false;
    btn.textContent = '선택 사진 추가';
  }
}

function buildBreadcrumb(currentPath) {
  if (!currentPath) return '<span>루트</span>';
  const parts = currentPath.split('/').filter(Boolean);
  let html = `<a href="#" data-nav-path="">루트</a>`;
  let cumPath = '';
  for (let i = 0; i < parts.length; i++) {
    cumPath += '/' + parts[i];
    html += `<span class="breadcrumb-sep">/</span>`;
    if (i === parts.length - 1) {
      html += `<span>${esc(parts[i])}</span>`;
    } else {
      html += `<a href="#" data-nav-path="${esc(cumPath)}">${esc(parts[i])}</a>`;
    }
  }
  return html;
}

function selectableThumb(photo, isSelected) {
  const thumbUrl = photo.thumb_url || '';
  return `
    <div class="photo-thumb selectable${isSelected ? ' selected' : ''}" data-path="${esc(photo.path)}">
      ${thumbUrl ? `<img src="${thumbUrl}" alt="" loading="lazy" onerror="this.style.opacity='0.2'">` : ''}
      <input type="checkbox" ${isSelected ? 'checked' : ''}>
    </div>`;
}

function photoListItem(photo, isSelected) {
  const thumbUrl = photo.thumb_url || '';
  const date = photo.taken_at ? new Date(photo.taken_at).toLocaleDateString('ko-KR') : '—';
  const dims = photo.width && photo.height ? `${photo.width}×${photo.height}` : '';
  return `
    <div class="photo-list-item selectable${isSelected ? ' selected' : ''}" data-path="${esc(photo.path)}">
      <input type="checkbox" ${isSelected ? 'checked' : ''}>
      <div class="photo-list-thumb">
        ${thumbUrl ? `<img src="${thumbUrl}" alt="" loading="lazy" onerror="this.style.opacity='0.2'">` : ''}
      </div>
      <span class="photo-list-name" title="${esc(photo.path)}">${esc(photo.name)}</span>
      <div class="photo-list-meta">
        <span>${date}</span>
        ${dims ? `<span>${dims}</span>` : ''}
        <span>${formatSize(photo.size)}</span>
      </div>
    </div>`;
}

function formatSize(bytes) {
  if (!bytes) return '—';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(0) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

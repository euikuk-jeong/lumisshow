import { api } from '../api.js';
import { getToken } from '../auth.js';
import { renderAdminShell } from '../layout.js';
import { esc } from '../utils.js';

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
    </div>
    <div id="browse-content"><div class="loading"></div></div>
    <div class="browse-selection-bar" id="selection-bar">
      <span id="selection-count">0개 선택됨</span>
      <button class="btn btn-primary" id="btn-add-selected" ${!albumId ? 'disabled' : ''}>
        ${albumId ? '선택 사진 추가' : '앨범을 선택해 사진 추가'}
      </button>
    </div>
  `, '/admin/browse');

  const state = { path: '', selected: new Set() };

  // 폴더/브레드크럼 이벤트 위임
  document.getElementById('browse-content').addEventListener('click', e => {
    const folder = e.target.closest('.folder-item');
    if (folder) { loadBrowse(state, folder.dataset.path); return; }
    const crumb = e.target.closest('[data-nav-path]');
    if (crumb) { e.preventDefault(); loadBrowse(state, crumb.dataset.navPath); }
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
    renderBrowseResult(state, data.folders, data.photos, path);
  } catch (e) {
    el.innerHTML = `<div class="alert alert-error">${e.message}</div>`;
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
    renderBrowseResult(state, [], data.items, null);
  } catch (e) {
    el.innerHTML = `<div class="alert alert-error">${e.message}</div>`;
  }
}

function renderBrowseResult(state, folders, photos, currentPath) {
  const el    = document.getElementById('browse-content');
  const token = getToken();

  const breadcrumbHTML = currentPath !== null ? buildBreadcrumb(currentPath) : '';
  const foldersHTML = folders.length
    ? `<div class="folder-list">${folders.map(f =>
        `<div class="folder-item" data-path="${esc(f.path)}">📁 ${esc(f.name)} <span class="text-muted text-sm">(${f.child_count})</span></div>`
      ).join('')}</div>`
    : '';

  const photosHTML = photos.length
    ? `<div class="photo-grid">${photos.map(p => selectableThumb(p, state.selected.has(p.path), token)).join('')}</div>`
    : '<p class="text-muted text-sm">사진이 없습니다</p>';

  el.innerHTML = `
    ${breadcrumbHTML ? `<div class="breadcrumb">${breadcrumbHTML}</div>` : ''}
    ${foldersHTML}
    ${photosHTML}
  `;

  el.querySelectorAll('.photo-thumb.selectable').forEach(thumb => {
    thumb.addEventListener('click', () => toggleSelect(thumb, state));
  });
}

function toggleSelect(thumb, state) {
  const path = thumb.dataset.path;
  const cb   = thumb.querySelector('input[type=checkbox]');
  if (state.selected.has(path)) {
    state.selected.delete(path);
    thumb.classList.remove('selected');
    cb.checked = false;
  } else {
    state.selected.add(path);
    thumb.classList.add('selected');
    cb.checked = true;
  }
  updateSelectionBar(state.selected.size);
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

function selectableThumb(photo, isSelected, token) {
  const thumbUrl = photo.thumb_url ? `${photo.thumb_url}&token=${token}` : '';
  // stopPropagation 없이 체크박스 클릭도 부모의 toggleSelect로 위임
  return `
    <div class="photo-thumb selectable${isSelected ? ' selected' : ''}" data-path="${esc(photo.path)}">
      ${thumbUrl ? `<img src="${thumbUrl}" alt="" loading="lazy" onerror="this.style.opacity='0.2'">` : ''}
      <input type="checkbox" ${isSelected ? 'checked' : ''}>
    </div>`;
}

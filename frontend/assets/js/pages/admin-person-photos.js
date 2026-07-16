import { api } from '../api.js';
import { renderAdminShell } from '../layout.js';
import { esc } from '../utils.js';
import { openLightbox } from '../lightbox.js';

const PAGE_SIZE = 500;

// 인물 전체 사진 (/admin/people/{id}/photos) — 확정(라벨) 얼굴이 포함된 사진만 표시
export async function renderAdminPersonPhotos(personId) {
  let person;
  try {
    person = await api.get(`/api/admin/people/${personId}`);
  } catch {
    window.navigate('/admin/people', true);
    return;
  }

  renderAdminShell(`
    <div class="page-header">
      <div>
        <h1 class="page-title">${esc(person.name)} — 전체 사진</h1>
        <p class="page-subtitle" id="photos-subtitle">확정 얼굴이 포함된 사진 불러오는 중...</p>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <a href="/admin/people/${personId}" class="btn btn-ghost" data-link>← 인물 상세</a>
        <button class="btn btn-primary" id="btn-slideshow" disabled>▶ 슬라이드쇼</button>
      </div>
    </div>
    <div class="flex gap-2 items-center" style="justify-content:flex-end;margin-bottom:12px">
      <div class="photo-sort-wrap">
        <button type="button" class="btn btn-ghost btn-sm" id="btn-photo-sort">정렬: 파일명 ↑</button>
        <div class="photo-sort-popover" id="photo-sort-popover" style="display:none">
          <div>
            <p class="sort-group-label">정렬 기준</p>
            <div class="settings-radios" style="gap:12px;font-size:13px">
              <label><input type="radio" name="pp-by" value="filename" checked> 파일명</label>
              <label><input type="radio" name="pp-by" value="taken_at"> 촬영일</label>
            </div>
          </div>
          <div>
            <p class="sort-group-label">방향</p>
            <div class="settings-radios" style="gap:12px;font-size:13px">
              <label><input type="radio" name="pp-dir" value="asc" checked> 오름차순</label>
              <label><input type="radio" name="pp-dir" value="desc"> 내림차순</label>
            </div>
          </div>
        </div>
      </div>
      <div class="view-toggle">
        <button type="button" id="btn-view-grid" class="btn btn-ghost btn-sm active" title="그리드 보기">⊞</button>
        <button type="button" id="btn-view-list" class="btn btn-ghost btn-sm" title="리스트 보기">☰</button>
        <button type="button" id="btn-view-date" class="btn btn-ghost btn-sm" title="날짜별 보기">📅</button>
      </div>
    </div>
    <div id="photos-content"><div class="loading"></div></div>
  `, '/admin/people');

  document.getElementById('btn-slideshow').addEventListener('click', () => {
    window.navigate(`/admin/people/${personId}/slideshow`);
  });

  const state = { viewMode: 'grid', sortBy: 'filename', sortDir: 'asc', photos: [] };
  let displayed = [];

  // ── 확정 사진 전체 로드 (페이지네이션 순회) ──────────────────────────
  const subtitle = document.getElementById('photos-subtitle');
  try {
    let page = 1, total = 0;
    do {
      const res = await api.get(
        `/api/admin/people/${personId}/photos-detail?source=labeled&page=${page}&size=${PAGE_SIZE}`
      );
      total = res.total;
      state.photos = state.photos.concat(res.photos);
      if (!document.getElementById('photos-content')) return; // 페이지 이탈
      subtitle.textContent = `확정 얼굴이 포함된 사진 불러오는 중... (${state.photos.length}/${total})`;
      if (!res.photos.length) break;
      page++;
    } while (state.photos.length < total);
  } catch (e) {
    document.getElementById('photos-content').innerHTML =
      `<div class="alert alert-error">${esc(e.message)}</div>`;
    return;
  }

  subtitle.textContent = `확정 얼굴이 포함된 사진 ${state.photos.length}장`;
  document.getElementById('btn-slideshow').disabled = !state.photos.length;

  // ── 정렬 ─────────────────────────────────────────────────────────────
  function sortPhotos(photos) {
    return [...photos].sort((a, b) => {
      if (state.sortBy === 'taken_at') {
        // 촬영일 없는 사진은 방향과 무관하게 항상 뒤로
        if (!a.taken_at && !b.taken_at) return a.file_path.localeCompare(b.file_path);
        if (!a.taken_at) return 1;
        if (!b.taken_at) return -1;
        const cmp = a.taken_at < b.taken_at ? -1 : a.taken_at > b.taken_at ? 1 : 0;
        return state.sortDir === 'desc' ? -cmp : cmp;
      }
      const cmp = a.file_path.localeCompare(b.file_path);
      return state.sortDir === 'desc' ? -cmp : cmp;
    });
  }

  function sortLabel() {
    const by  = state.sortBy === 'taken_at' ? '촬영일' : '파일명';
    const dir = state.sortDir === 'desc' ? '↓' : '↑';
    return `정렬: ${by} ${dir}`;
  }

  // ── 렌더 ─────────────────────────────────────────────────────────────
  function photoCard(p, idx) {
    return `
      <div class="photo-thumb" data-idx="${idx}" title="${esc(p.file_path)}">
        <img src="${p.thumb_small_url}" alt="" loading="lazy" onerror="this.style.opacity='0.3'">
      </div>`;
  }

  function photoListItem(p, idx) {
    const taken = p.taken_at ? p.taken_at.slice(0, 16).replace('T', ' ') : '—';
    return `
      <div class="photo-list-item" data-idx="${idx}" title="${esc(p.file_path)}">
        <div class="photo-list-thumb">
          <img src="${p.thumb_small_url}" alt="" loading="lazy" onerror="this.style.opacity='0.3'">
        </div>
        <span class="photo-list-name">${esc(p.filename || '')}</span>
        <div class="photo-list-meta"><span>촬영: ${taken}</span></div>
      </div>`;
  }

  function groupByDate(photos) {
    // 정렬 순서를 유지한 채 날짜(taken_at)가 바뀌는 지점마다 구간을 나눈다.
    const groups = [];
    for (const p of photos) {
      const key = p.taken_at ? p.taken_at.slice(0, 10) : '';
      const last = groups[groups.length - 1];
      if (last && last.key === key) last.photos.push(p);
      else groups.push({ key, label: key || '날짜 정보 없음', photos: [p] });
    }
    return groups;
  }

  function refresh() {
    const el = document.getElementById('photos-content');
    displayed = sortPhotos(state.photos);
    el.className = state.viewMode === 'list' ? 'photo-list'
      : state.viewMode === 'date' ? 'photo-date-groups'
      : 'photo-grid';
    if (!displayed.length) {
      el.className = '';
      el.innerHTML = `
        <div class="empty-state">
          <h3>사진이 없습니다</h3>
          <p>확정된 얼굴이 있는 사진이 여기에 표시됩니다</p>
        </div>`;
      return;
    }
    if (state.viewMode === 'date') {
      let idx = 0;
      el.innerHTML = groupByDate(displayed).map(g => `
        <div class="date-group">
          <div class="date-group-header">${esc(g.label)} <span class="text-muted text-sm">(${g.photos.length}장)</span></div>
          <div class="photo-grid">${g.photos.map(p => photoCard(p, idx++)).join('')}</div>
        </div>`).join('');
    } else {
      el.innerHTML = displayed.map((p, i) =>
        state.viewMode === 'list' ? photoListItem(p, i) : photoCard(p, i)
      ).join('');
    }
  }

  // ── 보기 모드 ────────────────────────────────────────────────────────
  function setViewMode(mode) {
    state.viewMode = mode;
    document.getElementById('btn-view-grid').classList.toggle('active', mode === 'grid');
    document.getElementById('btn-view-list').classList.toggle('active', mode === 'list');
    document.getElementById('btn-view-date').classList.toggle('active', mode === 'date');

    // 날짜별 보기는 촬영일 정렬 전제 — 파일명 정렬 비활성화
    const filenameRadio = document.querySelector('input[name="pp-by"][value="filename"]');
    filenameRadio.disabled = mode === 'date';
    if (mode === 'date' && state.sortBy === 'filename') {
      state.sortBy = 'taken_at';
      document.querySelector('input[name="pp-by"][value="taken_at"]').checked = true;
      document.getElementById('btn-photo-sort').textContent = sortLabel();
    }
    refresh();
  }

  document.getElementById('btn-view-grid').addEventListener('click', () => setViewMode('grid'));
  document.getElementById('btn-view-list').addEventListener('click', () => setViewMode('list'));
  document.getElementById('btn-view-date').addEventListener('click', () => setViewMode('date'));

  // ── 정렬 팝오버 ──────────────────────────────────────────────────────
  const sortBtn = document.getElementById('btn-photo-sort');
  const popover = document.getElementById('photo-sort-popover');
  sortBtn.addEventListener('click', e => {
    e.stopPropagation();
    popover.style.display = popover.style.display === 'none' ? 'flex' : 'none';
  });
  document.addEventListener('click', e => {
    if (!popover.contains(e.target) && e.target !== sortBtn) popover.style.display = 'none';
  });
  popover.addEventListener('change', () => {
    state.sortBy  = document.querySelector('input[name="pp-by"]:checked').value;
    state.sortDir = document.querySelector('input[name="pp-dir"]:checked').value;
    sortBtn.textContent = sortLabel();
    refresh();
  });

  // ── 라이트박스 ───────────────────────────────────────────────────────
  document.getElementById('photos-content').addEventListener('click', e => {
    const item = e.target.closest('[data-idx]');
    if (!item) return;
    openLightbox(displayed.map(p => p.file_path), Number(item.dataset.idx), {
      deleteLabel: '확정 해제',
      deleteConfirmMsg: '이 사진에서 인물 확정을 해제할까요?',
      onDelete: async path => {
        await api.delete(`/api/admin/people/${personId}/photo-label?path=${encodeURIComponent(path)}`);
        state.photos = state.photos.filter(p => p.file_path !== path);
        subtitle.textContent = `확정 얼굴이 포함된 사진 ${state.photos.length}장`;
        document.getElementById('btn-slideshow').disabled = !state.photos.length;
        refresh();
      },
    });
  });

  refresh();
}

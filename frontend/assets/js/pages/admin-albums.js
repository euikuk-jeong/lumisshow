import { api } from '../api.js';
import { renderAdminShell } from '../layout.js';
import { esc } from '../utils.js';

const PAGE_SIZE = 24;
const SEARCH_DEBOUNCE_MS = 300;
const LIST_CACHE_MAX = 30;
const DATE_MODES = [
  { id: 'all',   label: '전체 기간' },
  { id: 'year',  label: '년' },
  { id: 'month', label: '년·월' },
  { id: 'range', label: '기간 지정' },
];

// 목록 응답 캐시 — 키: API 쿼리스트링. 재방문 시 즉시 표시 후 갱신
const _listCache = new Map();
let _facets = { years: [] };
let _state = null;
let _listSeq = 0;
let _facetSeq = 0;

export async function renderAdminAlbums() {
  _state = _stateFromUrl();

  renderAdminShell(`
    <div class="page-header">
      <div>
        <h1 class="page-title">앨범</h1>
        <p class="page-subtitle">앨범을 관리하고 공유 링크를 생성합니다</p>
      </div>
      <a href="/admin/albums/new" class="btn btn-primary" data-link>+ 새 앨범</a>
    </div>
    <div class="album-search">
      <div class="album-search-row">
        <input type="search" id="album-q" class="form-input album-search-q"
               placeholder="🔍 앨범 이름·설명 검색" maxlength="200" value="${esc(_state.q)}">
        <select id="album-date-mode" class="form-select album-search-mode">
          ${DATE_MODES.map(m => `<option value="${m.id}" ${m.id === _state.mode ? 'selected' : ''}>${m.label}</option>`).join('')}
        </select>
        <div id="album-date-inputs" class="album-search-dates"></div>
      </div>
      <div class="album-search-row album-search-status">
        <span id="album-result-info" class="text-muted"></span>
        <button class="btn btn-ghost btn-sm" id="album-search-reset" style="display:none">초기화</button>
      </div>
    </div>
    <div id="albums-content"><div class="loading"></div></div>
  `, '/admin');

  _bindToolbar();
  _renderDateInputs();
  await Promise.all([_loadFacets(), _loadAlbums()]);
}

/* ── URL 상태 ─────────────────────────────────────────── */

function _stateFromUrl() {
  const p = new URLSearchParams(location.search);
  const mode = DATE_MODES.some(m => m.id === p.get('mode')) ? p.get('mode') : 'all';
  return {
    q: p.get('q') ?? '',
    mode,
    y: p.get('y') ? parseInt(p.get('y'), 10) || null : null,
    m: p.get('m') ? parseInt(p.get('m'), 10) || null : null,
    from: p.get('from') ?? '',
    to: p.get('to') ?? '',
    page: Math.max(1, parseInt(p.get('page'), 10) || 1),
  };
}

function _syncUrl() {
  const s = _state;
  const p = new URLSearchParams();
  if (s.q.trim()) p.set('q', s.q.trim());
  if (s.mode !== 'all') p.set('mode', s.mode);
  if ((s.mode === 'year' || s.mode === 'month') && s.y) p.set('y', s.y);
  if (s.mode === 'month' && s.m) p.set('m', s.m);
  if (s.mode === 'range') {
    if (s.from) p.set('from', s.from);
    if (s.to) p.set('to', s.to);
  }
  if (s.page > 1) p.set('page', s.page);
  const qs = p.toString();
  // replaceState: 입력마다 히스토리를 쌓지 않되, 상세 화면에서 뒤로 오면 이 상태로 복원
  history.replaceState(null, '', qs ? `${location.pathname}?${qs}` : location.pathname);
}

function _hasFilter() {
  const s = _state;
  return !!s.q.trim() || s.mode !== 'all';
}

/** 선택된 날짜 모드 → API date_from/date_to (서버 timezone 기준 날짜, 양 끝 포함). */
function _dateRange() {
  const s = _state;
  const pad = n => String(n).padStart(2, '0');
  if (s.mode === 'year' && s.y) return { from: `${s.y}-01-01`, to: `${s.y}-12-31` };
  if (s.mode === 'month' && s.y && s.m) {
    const lastDay = new Date(Date.UTC(s.y, s.m, 0)).getUTCDate();
    return { from: `${s.y}-${pad(s.m)}-01`, to: `${s.y}-${pad(s.m)}-${pad(lastDay)}` };
  }
  if (s.mode === 'range') return { from: s.from, to: s.to };
  return { from: '', to: '' };
}

/* ── 툴바 ─────────────────────────────────────────────── */

function _bindToolbar() {
  const qInput = document.getElementById('album-q');
  let timer = null;
  let composing = false;
  const scheduleSearch = () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      _state.q = qInput.value;
      _state.page = 1;
      _loadFacets();
      _loadAlbums();
    }, SEARCH_DEBOUNCE_MS);
  };
  // 한글 IME 조합 중에는 요청하지 않음 — 조합 완료(compositionend) 시점에 검색
  qInput.addEventListener('compositionstart', () => { composing = true; });
  qInput.addEventListener('compositionend', () => { composing = false; scheduleSearch(); });
  qInput.addEventListener('input', () => { if (!composing) scheduleSearch(); });
  window._pageCleanup = () => clearTimeout(timer);

  document.getElementById('album-date-mode').addEventListener('change', e => {
    _state.mode = e.target.value;
    const latest = _facets.years[0];
    if ((_state.mode === 'year' || _state.mode === 'month') && !_state.y) {
      _state.y = latest?.year ?? new Date().getFullYear();
    }
    if (_state.mode === 'month' && !_state.m) {
      _state.m = _facets.years.find(y => y.year === _state.y)?.months[0]?.month ?? new Date().getMonth() + 1;
    }
    _state.page = 1;
    _renderDateInputs();
    _loadAlbums();
  });

  document.getElementById('album-search-reset').addEventListener('click', () => {
    clearTimeout(timer);
    _state = { q: '', mode: 'all', y: null, m: null, from: '', to: '', page: 1 };
    qInput.value = '';
    document.getElementById('album-date-mode').value = 'all';
    _renderDateInputs();
    _loadFacets();
    _loadAlbums();
  });
}

function _renderDateInputs() {
  const el = document.getElementById('album-date-inputs');
  if (!el) return;
  const s = _state;
  if (s.mode === 'year' || s.mode === 'month') {
    const years = [..._facets.years];
    // 검색어 때문에 facet에서 빠진 선택 년도도 옵션에 유지
    if (s.y && !years.some(y => y.year === s.y)) years.push({ year: s.y, count: 0, months: [] });
    years.sort((a, b) => b.year - a.year);
    let html = `<select id="album-date-y" class="form-select">
      ${years.map(y => `<option value="${y.year}" ${y.year === s.y ? 'selected' : ''}>${y.year}년 (${y.count})</option>`).join('')}
    </select>`;
    if (s.mode === 'month') {
      const months = years.find(y => y.year === s.y)?.months ?? [];
      const countOf = m => months.find(x => x.month === m)?.count ?? 0;
      html += `<select id="album-date-m" class="form-select">
        ${Array.from({ length: 12 }, (_, i) => i + 1).map(m =>
          `<option value="${m}" ${m === s.m ? 'selected' : ''}>${m}월 (${countOf(m)})</option>`).join('')}
      </select>`;
    }
    el.innerHTML = html;
    document.getElementById('album-date-y').addEventListener('change', e => {
      _state.y = parseInt(e.target.value, 10);
      _state.page = 1;
      _renderDateInputs();
      _loadAlbums();
    });
    document.getElementById('album-date-m')?.addEventListener('change', e => {
      _state.m = parseInt(e.target.value, 10);
      _state.page = 1;
      _loadAlbums();
    });
  } else if (s.mode === 'range') {
    el.innerHTML = `
      <input type="date" id="album-date-from" class="form-input" value="${esc(s.from)}" ${s.to ? `max="${esc(s.to)}"` : ''}>
      <span class="text-muted">~</span>
      <input type="date" id="album-date-to" class="form-input" value="${esc(s.to)}" ${s.from ? `min="${esc(s.from)}"` : ''}>`;
    const fromEl = document.getElementById('album-date-from');
    const toEl = document.getElementById('album-date-to');
    const onChange = () => {
      _state.from = fromEl.value;
      _state.to = toEl.value;
      toEl.min = fromEl.value;
      fromEl.max = toEl.value;
      _state.page = 1;
      _loadAlbums();
    };
    fromEl.addEventListener('change', onChange);
    toEl.addEventListener('change', onChange);
  } else {
    el.innerHTML = '';
  }
}

/* ── 데이터 로드 ──────────────────────────────────────── */

async function _loadFacets() {
  const seq = ++_facetSeq;
  const q = _state.q.trim();
  try {
    const data = await api.get(`/api/admin/albums/date-facets${q ? `?q=${encodeURIComponent(q)}` : ''}`);
    if (seq !== _facetSeq) return;
    _facets = data;
    if (_state.mode === 'year' || _state.mode === 'month') _renderDateInputs();
  } catch { /* facet 실패는 목록 표시를 막지 않음 */ }
}

async function _loadAlbums() {
  const el = document.getElementById('albums-content');
  if (!el) return;  // 다른 화면으로 이동한 뒤 남은 호출 — URL을 덮어쓰지 않음
  _syncUrl();
  const { from, to } = _dateRange();
  if (from && to && from > to) {
    el.innerHTML = '<div class="alert alert-error">시작일이 종료일보다 늦습니다</div>';
    _renderStatus(null);
    return;
  }
  const p = new URLSearchParams({ page: _state.page, size: PAGE_SIZE });
  if (_state.q.trim()) p.set('q', _state.q.trim());
  if (from) p.set('date_from', from);
  if (to) p.set('date_to', to);
  const key = p.toString();

  const seq = ++_listSeq;
  if (_listCache.has(key)) _renderAlbums(el, _listCache.get(key));
  try {
    const data = await api.get(`/api/admin/albums?${key}`);
    if (seq !== _listSeq || !el.isConnected) return;  // 늦게 도착한 이전 요청 응답은 무시
    const lastPage = Math.max(1, Math.ceil(data.total / PAGE_SIZE));
    if (!data.items.length && data.total > 0 && _state.page > lastPage) {
      _state.page = lastPage;
      return _loadAlbums();
    }
    // 검색어를 칠 때마다 키가 늘어나므로 최근 항목만 유지 (Map은 삽입 순서 = 가장 오래된 것부터)
    _listCache.delete(key);
    _listCache.set(key, data);
    if (_listCache.size > LIST_CACHE_MAX) _listCache.delete(_listCache.keys().next().value);
    _renderAlbums(el, data);
  } catch (e) {
    if (seq === _listSeq && !_listCache.has(key)) {
      el.innerHTML = `<div class="alert alert-error">${esc(e.message)}</div>`;
    }
  }
}

/* ── 렌더링 ───────────────────────────────────────────── */

function _renderStatus(data) {
  const info = document.getElementById('album-result-info');
  const reset = document.getElementById('album-search-reset');
  if (!info) return;
  reset.style.display = _hasFilter() ? '' : 'none';
  if (!data || !data.total) { info.textContent = ''; return; }
  const start = (data.page - 1) * data.size + 1;
  const end = start + data.items.length - 1;
  info.textContent = `${data.total.toLocaleString()}개 중 ${start.toLocaleString()}–${end.toLocaleString()}`;
}

function _renderAlbums(el, data) {
  _renderStatus(data);
  if (!data.items.length) {
    el.innerHTML = _hasFilter()
      ? `<div class="empty-state">
           <h3>검색 결과가 없습니다</h3>
           <p>검색어나 기간을 바꾸거나 초기화해 보세요</p>
         </div>`
      : `<div class="empty-state">
           <h3>앨범이 없습니다</h3>
           <p>새 앨범 버튼을 눌러 첫 앨범을 만들어보세요</p>
         </div>`;
    return;
  }
  el.innerHTML = `
    <div class="album-grid">${data.items.map(a => albumCard(a, data.timezone_offset)).join('')}</div>
    ${_paginationHtml(data)}`;
  el.querySelectorAll('.album-card').forEach((card, i) => {
    card.addEventListener('click', () => window.navigate(`/admin/albums/${data.items[i].id}`));
  });
  el.querySelectorAll('.pagination [data-page]').forEach(btn => {
    btn.addEventListener('click', () => {
      _state.page = parseInt(btn.dataset.page, 10);
      window.scrollTo({ top: 0 });
      _loadAlbums();
    });
  });
}

function _paginationHtml(data) {
  const last = Math.max(1, Math.ceil(data.total / data.size));
  if (last <= 1) return '';
  const cur = data.page;
  const pages = new Set([1, last]);
  for (let p = cur - 2; p <= cur + 2; p++) if (p >= 1 && p <= last) pages.add(p);
  const sorted = [...pages].sort((a, b) => a - b);

  const btn = (page, label, { active = false, disabled = false, aria = '' } = {}) =>
    `<button class="btn btn-sm ${active ? 'btn-primary' : 'btn-ghost'}"
       ${disabled || active ? 'disabled' : `data-page="${page}"`}
       ${aria ? `aria-label="${aria}"` : ''} ${active ? 'aria-current="page"' : ''}>${label}</button>`;

  let html = btn(cur - 1, '‹', { disabled: cur === 1, aria: '이전 페이지' });
  sorted.forEach((p, i) => {
    if (i > 0 && p - sorted[i - 1] > 1) html += '<span class="pagination-gap">…</span>';
    html += btn(p, p, { active: p === cur });
  });
  html += btn(cur + 1, '›', { disabled: cur === last, aria: '다음 페이지' });
  return `<nav class="pagination" aria-label="앨범 페이지">${html}</nav>`;
}

/** API의 UTC datetime(Z 없는 naive 문자열 포함)을 서버 timezone 기준 날짜로 표시. */
function formatDateInTZ(value, offsetMinutes) {
  const iso = /(Z|[+-]\d\d:?\d\d)$/.test(value) ? value : `${value}Z`;
  const tzDate = new Date(new Date(iso).getTime() + offsetMinutes * 60 * 1000);
  return `${tzDate.getUTCFullYear()}. ${tzDate.getUTCMonth() + 1}. ${tzDate.getUTCDate()}.`;
}

function albumCard(album, tzOffset) {
  const coverPath = album.cover_path || album.first_photo_path;
  const cover = coverPath
    ? `<img src="/api/admin/thumb?path=${encodeURIComponent(coverPath)}&size=small" alt="" loading="lazy">`
    : '🖼';
  const createdDate = formatDateInTZ(album.created_at, tzOffset);
  const expiresDate = album.next_expires_at ? formatDateInTZ(album.next_expires_at, tzOffset) : null;
  return `
    <div class="album-card">
      <div class="album-cover">${cover}</div>
      <div class="album-info">
        <div class="album-name" title="${esc(album.name)}">${esc(album.name)}</div>
        <div class="album-meta">
          <div class="album-meta-row">
            <span>📷 ${album.photo_count.toLocaleString()}장</span>
            ${album.video_count > 0 ? `<span>🎬 ${album.video_count.toLocaleString()}개</span>` : ''}
            <span>👁 ${(album.view_count ?? 0).toLocaleString()}회</span>
            <span>🔗 ${(album.active_link_count ?? 0).toLocaleString()}개</span>
          </div>
          <div class="album-meta-row">
            <span>${createdDate} 생성</span>
            ${expiresDate ? `<span>· ${expiresDate} 만료</span>` : ''}
          </div>
        </div>
      </div>
    </div>`;
}

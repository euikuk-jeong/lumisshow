import { api } from '../api.js';
import { renderAdminShell } from '../layout.js';
import { esc } from '../utils.js';
import { openLightbox } from '../lightbox.js';
import { THEMES } from '../theme.js';
import { EFFECTS, EFFECT_LABELS } from '../slideshow-config.js';

export async function renderAdminAlbumEdit(albumId) {
  const isNew = !albumId;
  const title = isNew ? '새 앨범' : '앨범 편집';

  renderAdminShell(`
    <a href="/admin" class="page-back" data-link>← 앨범 목록</a>
    <div class="page-header">
      <h1 class="page-title">${title}</h1>
      ${!isNew ? `
        <div style="display:flex;gap:8px">
          <button class="btn btn-secondary btn-sm" id="btn-duplicate">복제</button>
          <button class="btn btn-danger btn-sm" id="btn-delete">삭제</button>
        </div>
      ` : ''}
    </div>
    <div id="edit-content"><div class="loading"></div></div>
  `, '/admin');

  if (isNew) {
    renderCreateForm();
  } else {
    await loadAlbum(albumId);
  }
}

/* ── Create form ─────────────────────────────────────────── */
function renderCreateForm() {
  const el = document.getElementById('edit-content');
  el.innerHTML = `
    <div style="max-width:540px">
      <div id="form-error" class="alert alert-error" style="display:none"></div>
      <form id="album-form" class="flex-col gap-3">
        <div class="form-group">
          <label class="form-label">앨범 이름 *</label>
          <input id="f-name" type="text" class="form-input" placeholder="예: 2024 제주도 여행" required>
        </div>
        <div class="form-group">
          <label class="form-label">설명</label>
          <textarea id="f-desc" class="form-textarea" placeholder="앨범 설명 (선택)"></textarea>
        </div>
        <div class="flex gap-2 mt-2">
          <button type="submit" class="btn btn-primary" id="btn-create">앨범 생성</button>
          <a href="/admin" class="btn btn-ghost" data-link>취소</a>
        </div>
      </form>
    </div>
  `;

  const errEl = document.getElementById('form-error');
  document.getElementById('album-form').addEventListener('submit', async e => {
    e.preventDefault();
    errEl.style.display = 'none';
    const btn = document.getElementById('btn-create');
    btn.disabled = true;
    btn.textContent = '생성 중...';
    try {
      const album = await api.post('/api/admin/albums', {
        name:        document.getElementById('f-name').value.trim(),
        description: document.getElementById('f-desc').value.trim() || null,
        photo_paths: [],
      });
      window.navigate(`/admin/albums/${album.id}`);
    } catch (err) {
      errEl.textContent = err.message;
      errEl.style.display = 'block';
      btn.disabled = false;
      btn.textContent = '앨범 생성';
    }
  });
}

/* ── Edit form ───────────────────────────────────────────── */
async function loadAlbum(albumId) {
  const el = document.getElementById('edit-content');
  try {
    const [album, links, settings] = await Promise.all([
      api.get(`/api/admin/albums/${albumId}`),
      api.get(`/api/admin/albums/${albumId}/links`),
      api.get('/api/admin/settings').catch(() => ({ timezone_offset: 0 })),
    ]);
    renderEditForm(album, links, settings.timezone_offset ?? 0, settings.ui_theme ?? 'dark');
    bindDuplicateAlbum(albumId, album.name);
    bindDeleteAlbum(albumId);
  } catch (e) {
    el.innerHTML = `<div class="alert alert-error">${esc(e.message)}</div>`;
  }
}

function renderEditForm(album, links, tzOffset, serverTheme = 'dark') {
  const el    = document.getElementById('edit-content');
  const ss    = album; // slideshow fields are on album object
  el.innerHTML = `
    <div class="album-edit-layout">
      <!-- Info -->
      <div class="card aei-info">
          <p class="section-title">기본 정보</p>
          <div id="info-error" class="alert alert-error" style="display:none"></div>
          <form id="info-form" class="flex-col gap-3">
            <div class="form-group">
              <label class="form-label">앨범 이름</label>
              <input id="f-name" type="text" class="form-input" value="${esc(album.name)}" required>
            </div>
            <div class="form-group">
              <label class="form-label">설명</label>
              <textarea id="f-desc" class="form-textarea">${esc(album.description || '')}</textarea>
            </div>
            <div class="form-group">
              <label class="form-label">배경음악</label>
              <div id="music-list" class="music-list"></div>
              <button type="button" class="btn btn-ghost btn-sm" id="btn-browse-music">+ 음악 파일 선택</button>
            </div>
            <div>
              <button type="submit" class="btn btn-primary btn-sm" id="btn-save">저장</button>
              <span id="save-ok" class="text-success text-sm mt-1" style="display:none;margin-left:8px">저장됨 ✓</span>
            </div>
          </form>
          <hr class="divider" style="margin:12px 0">
          <div class="flex items-center gap-2">
            <span class="form-label" style="margin:0">조회 수</span>
            <span id="view-count-value">${album.view_count ?? 0}회</span>
            <button type="button" class="btn btn-ghost btn-sm" id="btn-reset-views">초기화</button>
          </div>
        </div>

      <!-- Slideshow defaults -->
      <div class="card aei-ss">
          <p class="section-title">슬라이드쇼 기본 설정</p>
          <div id="ss-error" class="alert alert-error" style="display:none"></div>
          <form id="ss-form" class="flex-col gap-3">
            <div class="form-group">
              <label class="form-label">앨범 테마</label>
              <div class="theme-picker" id="album-theme-picker"></div>
              <input type="hidden" id="ss-ui-theme" value="${album.ui_theme || ''}">
            </div>
            <div class="form-group">
              <label class="form-label">전환 시간 (초)</label>
              <input id="ss-interval" type="number" min="2" max="60" class="form-input" style="width:100px"
                     value="${ss.slideshow_interval ?? 5}">
            </div>
            <div class="form-group">
              <label class="form-label">재생 순서</label>
              <div class="settings-radios">
                <label><input type="radio" name="ss-order" value="sequential" ${(ss.slideshow_order ?? 'sequential') === 'sequential' ? 'checked' : ''}> 순서대로</label>
                <label><input type="radio" name="ss-order" value="random" ${(ss.slideshow_order ?? '') === 'random' ? 'checked' : ''}> 랜덤</label>
              </div>
            </div>
            <div class="form-group">
              <label class="form-label">전환 효과</label>
              <select id="ss-effect" class="form-select">
                ${['random', ...EFFECTS].map(e => `<option value="${e}" ${(ss.slideshow_effect ?? 'random') === e ? 'selected' : ''}>${EFFECT_LABELS[e]}</option>`).join('')}
              </select>
            </div>
            <div class="form-group">
              <label class="form-label">배경음악</label>
              <div class="settings-radios">
                <label><input type="radio" name="ss-music" value="on"  ${ss.slideshow_music !== false ? 'checked' : ''}> ON</label>
                <label><input type="radio" name="ss-music" value="off" ${ss.slideshow_music === false ? 'checked' : ''}> OFF</label>
              </div>
            </div>
            <div class="form-group">
              <label class="form-label">음량 <span id="ss-vol-label">${ss.slideshow_volume ?? 25}%</span></label>
              <input id="ss-volume" type="range" min="0" max="100" value="${ss.slideshow_volume ?? 25}" class="w-full">
            </div>
            <div class="form-group">
              <label class="form-label">반복 재생</label>
              <div class="settings-radios">
                <label><input type="radio" name="ss-loop" value="on"  ${ss.slideshow_loop !== false ? 'checked' : ''}> 켜기</label>
                <label><input type="radio" name="ss-loop" value="off" ${ss.slideshow_loop === false ? 'checked' : ''}> 끄기</label>
              </div>
            </div>
            <div>
              <button type="submit" class="btn btn-primary btn-sm" id="btn-ss-save">저장</button>
              <span id="ss-save-ok" class="text-success text-sm mt-1" style="display:none;margin-left:8px">저장됨 ✓</span>
            </div>
          </form>
        </div>

      <!-- Photos -->
      <div class="card aei-photos">
          <div class="flex items-center justify-between" style="margin-bottom:12px">
            <p class="section-title" style="margin:0">사진 (<span id="photo-count-label">${album.photos.length}</span>장)</p>
            <div class="flex gap-2 items-center" id="photo-normal-controls">
              <button type="button" class="btn btn-warning btn-sm" id="btn-repair-paths" style="display:none">경로 복구</button>
              <div class="photo-sort-wrap">
                <button type="button" class="btn btn-ghost btn-sm" id="btn-photo-sort">정렬: ${photoSortLabel(album.photo_sort_by, album.photo_sort_dir)}</button>
                <div class="photo-sort-popover" id="photo-sort-popover" style="display:none">
                  <div>
                    <p class="sort-group-label">정렬 기준</p>
                    <div class="settings-radios" style="gap:12px;font-size:13px">
                      <label><input type="radio" name="ps-by" value="filename" ${(album.photo_sort_by || 'filename') === 'filename' ? 'checked' : ''}> 파일명</label>
                      <label><input type="radio" name="ps-by" value="taken_at" ${album.photo_sort_by === 'taken_at' ? 'checked' : ''}> 촬영일</label>
                    </div>
                  </div>
                  <div>
                    <p class="sort-group-label">방향</p>
                    <div class="settings-radios" style="gap:12px;font-size:13px">
                      <label><input type="radio" name="ps-dir" value="asc" ${(album.photo_sort_dir || 'asc') !== 'desc' ? 'checked' : ''}> 오름차순</label>
                      <label><input type="radio" name="ps-dir" value="desc" ${album.photo_sort_dir === 'desc' ? 'checked' : ''}> 내림차순</label>
                    </div>
                  </div>
                  <button type="button" class="btn btn-primary btn-sm" id="btn-sort-apply">적용</button>
                </div>
              </div>
              <div class="view-toggle">
                <button type="button" id="btn-photo-view-grid" class="btn btn-ghost btn-sm active" title="그리드 보기">⊞</button>
                <button type="button" id="btn-photo-view-list" class="btn btn-ghost btn-sm" title="리스트 보기">☰</button>
              </div>
              <a href="/admin/browse?album_id=${album.id}" class="btn btn-ghost btn-sm" data-link>+ 사진 추가</a>
              <button type="button" class="btn btn-danger btn-sm" id="btn-enter-remove-mode">사진 제외</button>
            </div>
            <div class="flex gap-2 items-center" id="photo-remove-controls" style="display:none">
              <button type="button" class="btn btn-ghost btn-sm" id="btn-select-all-remove">전체 선택</button>
              <span class="text-muted text-sm" id="remove-count-label">0개 선택됨</span>
              <button type="button" class="btn btn-ghost btn-sm" id="btn-cancel-remove">취소</button>
              <button type="button" class="btn btn-danger btn-sm" id="btn-confirm-remove" disabled>제외</button>
            </div>
          </div>
          <div id="photo-grid" class="photo-grid">
            ${album.photos.map(p => photoThumb(p, album.cover_path)).join('') || '<p class="text-muted text-sm">사진이 없습니다</p>'}
          </div>
      </div>

      <!-- Share links -->
      <div class="aei-links">
        <div class="card">
          <p class="section-title">공유 링크</p>
          <div id="links-container">${renderLinks(links, tzOffset)}</div>
          <hr class="divider">
          <button class="btn btn-ghost btn-sm w-full" id="btn-new-link">+ 새 링크 생성</button>
          <div id="link-form-area" style="display:none">
            ${renderLinkForm()}
          </div>
        </div>
      </div>
    </div>
  `;

  initAlbumThemePicker(album.ui_theme, serverTheme);

  let musicPaths = [...(album.music_paths || [])];

  function refreshMusicList() {
    const listEl = document.getElementById('music-list');
    if (!listEl) return;
    if (!musicPaths.length) {
      listEl.innerHTML = '<p class="text-muted text-sm" style="margin:4px 0">음악 없음</p>';
      return;
    }

    listEl.innerHTML = musicPaths.map((p, i) => `
      <div class="music-item" draggable="true" data-index="${i}">
        <span class="music-item-drag" title="드래그하여 순서 변경">⠿</span>
        <span class="music-item-name">${esc(p.split(/[\\/]/).pop())}</span>
        <button type="button" class="music-item-remove" data-index="${i}" title="제거">✕</button>
      </div>`).join('');

    listEl.querySelectorAll('.music-item-remove').forEach(btn => {
      btn.addEventListener('click', () => {
        musicPaths.splice(parseInt(btn.dataset.index, 10), 1);
        refreshMusicList();
      });
    });

    // ── Drag-and-drop reorder ────────────────────────────────
    let dragSrcIdx = null;

    listEl.querySelectorAll('.music-item').forEach(item => {
      const idx = parseInt(item.dataset.index, 10);

      item.addEventListener('dragstart', e => {
        dragSrcIdx = idx;
        e.dataTransfer.effectAllowed = 'move';
        // setTimeout 으로 ghost 캡처 후 스타일 적용 (즉시 적용 시 ghost도 반투명해짐)
        setTimeout(() => item.classList.add('dragging'), 0);
      });

      item.addEventListener('dragend', () => {
        item.classList.remove('dragging');
        listEl.querySelectorAll('.music-item').forEach(el => el.classList.remove('drag-over'));
      });

      item.addEventListener('dragover', e => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        if (dragSrcIdx !== idx) {
          listEl.querySelectorAll('.music-item').forEach(el => el.classList.remove('drag-over'));
          item.classList.add('drag-over');
        }
      });

      item.addEventListener('dragleave', e => {
        // 자식 요소로 이동할 때는 highlight 유지
        if (!item.contains(e.relatedTarget)) item.classList.remove('drag-over');
      });

      item.addEventListener('drop', e => {
        e.preventDefault();
        if (dragSrcIdx === null || dragSrcIdx === idx) return;
        const moved = musicPaths.splice(dragSrcIdx, 1)[0];
        // 원소 제거 후 인덱스 보정: 앞에서 뒤로 이동 시 target이 한 칸 당겨짐
        musicPaths.splice(dragSrcIdx < idx ? idx - 1 : idx, 0, moved);
        refreshMusicList();
      });
    });
  }
  refreshMusicList();

  document.getElementById('btn-browse-music').addEventListener('click', () => {
    openMusicModal(musicPaths, selected => { musicPaths = selected; refreshMusicList(); });
  });

  document.getElementById('ss-volume').addEventListener('input', e => {
    document.getElementById('ss-vol-label').textContent = `${e.target.value}%`;
  });

  const photoState = { viewMode: 'grid', coverPath: album.cover_path, photos: [...album.photos], removeMode: false, removeSelected: new Set() };
  let brokenDetected = false;

  function onPhotoLoadError() {
    if (brokenDetected) return;
    brokenDetected = true;
    const btn = document.getElementById('btn-repair-paths');
    if (btn) btn.style.display = '';
  }

  function attachImageErrorTracking() {
    document.querySelectorAll('#photo-grid img').forEach(img => {
      if (img._repairTracked) return;
      img._repairTracked = true;
      img.addEventListener('error', onPhotoLoadError, { once: true });
    });
  }

  function refreshPhotoGrid() {
    const el = document.getElementById('photo-grid');
    el.className = photoState.viewMode === 'list' ? 'photo-list' : 'photo-grid';
    if (photoState.removeMode) el.classList.add('remove-mode');
    el.innerHTML = photoState.photos.length
      ? photoState.photos.map(p =>
          photoState.viewMode === 'list'
            ? photoListItemEdit(p, photoState.coverPath, photoState.removeMode, photoState.removeSelected.has(p.file_path))
            : photoThumb(p, photoState.coverPath, photoState.removeMode, photoState.removeSelected.has(p.file_path))
        ).join('')
      : '<p class="text-muted text-sm">사진이 없습니다</p>';
    attachImageErrorTracking();
    const countEl = document.getElementById('photo-count-label');
    if (countEl) countEl.textContent = photoState.photos.length;
  }

  document.getElementById('btn-photo-view-grid').addEventListener('click', () => {
    photoState.viewMode = 'grid';
    document.getElementById('btn-photo-view-grid').classList.add('active');
    document.getElementById('btn-photo-view-list').classList.remove('active');
    refreshPhotoGrid();
  });
  document.getElementById('btn-photo-view-list').addEventListener('click', () => {
    photoState.viewMode = 'list';
    document.getElementById('btn-photo-view-grid').classList.remove('active');
    document.getElementById('btn-photo-view-list').classList.add('active');
    refreshPhotoGrid();
  });

  bindInfoForm(album.id, () => musicPaths);
  bindViewCountReset(album.id);
  bindSlideshowForm(album.id);
  bindPhotoRemoveMode(album.id, photoState, refreshPhotoGrid);
  bindCoverSet(album.id, photoState, refreshPhotoGrid);
  bindPhotoSort(album.id, photoState, refreshPhotoGrid);
  bindPhotoPreview(album.id, photoState, refreshPhotoGrid);
  bindRepairPaths(album.id, photoState, refreshPhotoGrid, () => { brokenDetected = false; });
  bindLinkActions(album.id, links, tzOffset);
  attachImageErrorTracking();
}

function bindSlideshowForm(albumId) {
  const errEl = document.getElementById('ss-error');
  const okEl  = document.getElementById('ss-save-ok');
  document.getElementById('ss-form').addEventListener('submit', async e => {
    e.preventDefault();
    errEl.style.display = 'none';
    okEl.style.display = 'none';
    const btn = document.getElementById('btn-ss-save');
    btn.disabled = true;
    try {
      await api.put(`/api/admin/albums/${albumId}`, {
        slideshow_interval: parseInt(document.getElementById('ss-interval').value, 10) || 5,
        slideshow_order:    document.querySelector('input[name="ss-order"]:checked').value,
        slideshow_effect:   document.getElementById('ss-effect').value,
        slideshow_music:    document.querySelector('input[name="ss-music"]:checked').value === 'on',
        slideshow_volume:   parseInt(document.getElementById('ss-volume').value, 10),
        slideshow_loop:     document.querySelector('input[name="ss-loop"]:checked').value === 'on',
        ui_theme:           document.getElementById('ss-ui-theme').value || null,
      });
      okEl.style.display = 'inline';
      setTimeout(() => { okEl.style.display = 'none'; }, 2000);
    } catch (err) {
      errEl.textContent = err.message;
      errEl.style.display = 'block';
    } finally {
      btn.disabled = false;
    }
  });
}

function bindViewCountReset(albumId) {
  document.getElementById('btn-reset-views').addEventListener('click', async () => {
    if (!confirm('조회 수를 0으로 초기화하시겠습니까?')) return;
    try {
      await api.delete(`/api/admin/albums/${albumId}/view-count`);
      document.getElementById('view-count-value').textContent = '0회';
    } catch (e) {
      alert(e.message);
    }
  });
}

function bindInfoForm(albumId, getMusicPaths) {
  const errEl = document.getElementById('info-error');
  const okEl  = document.getElementById('save-ok');
  document.getElementById('info-form').addEventListener('submit', async e => {
    e.preventDefault();
    errEl.style.display = 'none';
    okEl.style.display = 'none';
    const btn = document.getElementById('btn-save');
    btn.disabled = true;
    try {
      await api.put(`/api/admin/albums/${albumId}`, {
        name:        document.getElementById('f-name').value.trim(),
        description: document.getElementById('f-desc').value.trim() || null,
        music_paths: getMusicPaths(),
      });
      okEl.style.display = 'inline';
      setTimeout(() => { okEl.style.display = 'none'; }, 2000);
    } catch (err) {
      errEl.textContent = err.message;
      errEl.style.display = 'block';
    } finally {
      btn.disabled = false;
    }
  });
}

async function openMusicModal(currentPaths, onConfirm) {
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal" style="max-width:480px">
      <p class="modal-title">음악 파일 선택</p>
      <div id="music-modal-body"><div class="loading"></div></div>
      <div class="modal-actions">
        <button class="btn btn-ghost" id="modal-cancel">취소</button>
        <button class="btn btn-primary" id="modal-confirm">확인</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);
  overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });
  document.getElementById('modal-cancel').addEventListener('click', () => overlay.remove());

  let selected = new Set(currentPaths);

  // confirm 리스너를 API 호출 전에 등록 (API 응답 전 클릭해도 동작)
  overlay.querySelector('#modal-confirm').addEventListener('click', () => {
    onConfirm(Array.from(selected));
    overlay.remove();
  });

  try {
    const { files } = await api.get('/api/admin/music');
    const body = document.getElementById('music-modal-body');
    if (!files.length) {
      body.innerHTML = `<p class="text-muted text-sm" style="padding:12px 0">
        음악 파일이 없습니다.<br>서버의 <code>data/music/</code> 폴더에 mp3 등을 추가하세요.</p>`;
    } else {
      body.innerHTML = `<div class="music-file-list">${files.map(f => `
        <div class="music-file-item${selected.has(f.path) ? ' selected' : ''}" data-path="${esc(f.path)}">
          <input type="checkbox" ${selected.has(f.path) ? 'checked' : ''}>
          <div style="overflow:hidden;min-width:0">
            <div class="music-file-name">${esc(f.name)}</div>
            ${f.rel !== f.name ? `<div class="music-file-rel">${esc(f.rel)}</div>` : ''}
          </div>
        </div>`).join('')}</div>`;

      body.querySelectorAll('.music-file-item').forEach(item => {
        const cb = item.querySelector('input[type=checkbox]');

        // change 이벤트가 selected Set의 단일 진실 공급원
        cb.addEventListener('change', () => {
          if (cb.checked) { selected.add(item.dataset.path); item.classList.add('selected'); }
          else            { selected.delete(item.dataset.path); item.classList.remove('selected'); }
        });

        // 체크박스 외 영역 클릭 시 cb.click()으로 위임 → change 이벤트 발생
        item.addEventListener('click', e => {
          if (e.target !== cb) cb.click();
        });
      });
    }
  } catch (e) {
    document.getElementById('music-modal-body').innerHTML =
      `<div class="alert alert-error">${esc(e.message)}</div>`;
  }
}

function bindCoverSet(albumId, photoState, refresh) {
  document.getElementById('photo-grid').addEventListener('click', async e => {
    const btn = e.target.closest('.photo-set-cover');
    if (!btn) return;
    const filePath = btn.dataset.path;
    try {
      await api.put(`/api/admin/albums/${albumId}`, { cover_path: filePath });
      photoState.coverPath = filePath;
      refresh();
    } catch (err) {
      alert(err.message);
    }
  });
}

function bindPhotoRemoveMode(albumId, photoState, refresh) {
  const enterBtn   = document.getElementById('btn-enter-remove-mode');
  const cancelBtn  = document.getElementById('btn-cancel-remove');
  const confirmBtn = document.getElementById('btn-confirm-remove');
  const selectAll  = document.getElementById('btn-select-all-remove');
  const normalCtrl = document.getElementById('photo-normal-controls');
  const removeCtrl = document.getElementById('photo-remove-controls');
  const countLabel = document.getElementById('remove-count-label');

  function updateCount() {
    const n = photoState.removeSelected.size;
    countLabel.textContent = `${n}개 선택됨`;
    confirmBtn.disabled = n === 0;
  }

  function enterMode() {
    photoState.removeMode = true;
    photoState.removeSelected.clear();
    normalCtrl.style.display = 'none';
    removeCtrl.style.display = '';
    refresh();
    updateCount();
  }

  function exitMode() {
    photoState.removeMode = false;
    photoState.removeSelected.clear();
    normalCtrl.style.display = '';
    removeCtrl.style.display = 'none';
    refresh();
  }

  enterBtn.addEventListener('click', enterMode);
  cancelBtn.addEventListener('click', exitMode);

  selectAll.addEventListener('click', () => {
    photoState.photos.forEach(p => photoState.removeSelected.add(p.file_path));
    refresh();
    updateCount();
  });

  confirmBtn.addEventListener('click', async () => {
    const paths = Array.from(photoState.removeSelected);
    if (!paths.length) return;
    if (!confirm(`선택한 ${paths.length}장을 앨범에서 제외하시겠습니까?`)) return;
    confirmBtn.disabled = true;
    try {
      await api.delete(`/api/admin/albums/${albumId}/photos`, { photo_paths: paths });
      photoState.photos = photoState.photos.filter(p => !photoState.removeSelected.has(p.file_path));
      exitMode();
    } catch (err) {
      alert(err.message);
      updateCount();
    }
  });

  document.getElementById('photo-grid').addEventListener('click', e => {
    if (!photoState.removeMode) return;
    const cb = e.target.closest('input.remove-check');
    if (!cb) {
      // 체크박스 외 영역 클릭 시 토글
      const item = e.target.closest('[data-path]');
      if (!item || e.target.closest('button')) return;
      const path = item.dataset.path;
      if (photoState.removeSelected.has(path)) {
        photoState.removeSelected.delete(path);
        item.classList.remove('remove-selected');
        const itemCb = item.querySelector('input.remove-check');
        if (itemCb) itemCb.checked = false;
      } else {
        photoState.removeSelected.add(path);
        item.classList.add('remove-selected');
        const itemCb = item.querySelector('input.remove-check');
        if (itemCb) itemCb.checked = true;
      }
      updateCount();
      return;
    }
    const item = cb.closest('[data-path]');
    if (!item) return;
    const path = item.dataset.path;
    if (cb.checked) {
      photoState.removeSelected.add(path);
      item.classList.add('remove-selected');
    } else {
      photoState.removeSelected.delete(path);
      item.classList.remove('remove-selected');
    }
    updateCount();
  });
}

function bindDuplicateAlbum(albumId, albumName) {
  document.getElementById('btn-duplicate')?.addEventListener('click', async () => {
    const newName = prompt('새 앨범 이름을 입력하세요:', `${albumName} (복사본)`);
    if (!newName) return;
    try {
      const newAlbum = await api.post(`/api/admin/albums/${albumId}/duplicate`, { name: newName });
      window.navigate(`/admin/albums/${newAlbum.id}`);
    } catch (err) {
      alert(err.message);
    }
  });
}

function bindDeleteAlbum(albumId) {
  document.getElementById('btn-delete')?.addEventListener('click', async () => {
    if (!confirm('앨범을 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.')) return;
    try {
      await api.delete(`/api/admin/albums/${albumId}`);
      window.navigate('/admin');
    } catch (err) {
      alert(err.message);
    }
  });
}

function bindLinkActions(albumId, links, tzOffset) {
  const formArea    = document.getElementById('link-form-area');
  const linksContainer = document.getElementById('links-container');

  document.getElementById('btn-new-link').addEventListener('click', () => {
    formArea.style.display = formArea.style.display === 'none' ? 'block' : 'none';
  });

  // 복사 버튼 이벤트 위임 (links-container가 innerHTML 교체되어도 컨테이너는 유지됨)
  linksContainer.addEventListener('click', e => {
    const copyBtn = e.target.closest('.btn-copy-link');
    if (copyBtn) navigator.clipboard.writeText(copyBtn.dataset.url).catch(() => {});
  });

  bindDatePicker();

  document.getElementById('link-form-area').addEventListener('submit', async e => {
    e.preventDefault();
    const pwd     = document.getElementById('lf-password').value || null;
    const dateVal = document.getElementById('lf-expires').value;
    const expires = dateVal ? buildExpiresAt(dateVal, tzOffset) : null;
    const btn     = document.getElementById('btn-create-link');
    btn.disabled  = true;
    try {
      const link = await api.post(`/api/admin/albums/${albumId}/links`, {
        password:   pwd || null,
        expires_at: expires,
      });
      links.push(link);
      document.getElementById('links-container').innerHTML = renderLinks(links, tzOffset);
      document.getElementById('lf-password').value = '';
      document.getElementById('lf-expires').value = '';
      formArea.style.display = 'none';
      bindLinkDeactivate(albumId);
      bindLinkDelete(albumId, links);
    } catch (err) {
      alert(err.message);
    } finally {
      btn.disabled = false;
    }
  });

  bindLinkDeactivate(albumId);
  bindLinkDelete(albumId, links);
}

function bindLinkDeactivate(albumId) {
  // links-container 범위로 한정
  document.getElementById('links-container').querySelectorAll('.btn-deactivate-link').forEach(btn => {
    btn.addEventListener('click', async () => {
      if (!confirm('이 공유 링크를 비활성화하시겠습니까?')) return;
      const linkId = btn.dataset.id;
      try {
        await api.patch(`/api/admin/albums/${albumId}/links/${linkId}`, { is_active: false });
        btn.closest('.link-item').querySelector('.badge').className = 'badge badge-inactive';
        btn.closest('.link-item').querySelector('.badge').textContent = '비활성';
        btn.closest('.link-item').querySelector('.btn-delete-link')?.setAttribute('data-active', 'false');
        btn.remove();
      } catch (err) {
        alert(err.message);
      }
    });
  });
}

function bindLinkDelete(albumId, links) {
  document.getElementById('links-container').querySelectorAll('.btn-delete-link').forEach(btn => {
    btn.addEventListener('click', async () => {
      if (!confirm('이 공유 링크를 삭제하시겠습니까? 삭제 후 복구할 수 없습니다.')) return;
      const linkId = parseInt(btn.dataset.id, 10);
      const isActive = btn.dataset.active === 'true';
      btn.disabled = true;
      try {
        if (isActive) {
          await api.patch(`/api/admin/albums/${albumId}/links/${linkId}`, { is_active: false });
        }
        await api.delete(`/api/admin/albums/${albumId}/links/${linkId}`);
        const idx = links.findIndex(l => l.id === linkId);
        if (idx !== -1) links.splice(idx, 1);
        btn.closest('.link-item').remove();
      } catch (err) {
        alert(err.message);
        btn.disabled = false;
      }
    });
  });
}

/* ── Render helpers ─────────────────────────────────────── */
function renderLinks(links, tzOffset = 0) {
  if (!links.length) return '<p class="text-muted text-sm">링크가 없습니다</p>';
  return `<div class="link-list">${links.map(l => renderLinkItem(l, tzOffset)).join('')}</div>`;
}

function renderLinkItem(link, tzOffset = 0) {
  const isExpired = link.expires_at && new Date(link.expires_at) < new Date();
  const expires = link.expires_at
    ? `만료: ${formatDateInTZ(link.expires_at, tzOffset)}`
    : '만료 없음';
  const isEffectivelyActive = link.is_active && !isExpired;
  const badgeClass = !link.is_active ? 'badge badge-inactive' : isExpired ? 'badge badge-expired' : 'badge badge-active';
  const badgeText  = !link.is_active ? '비활성' : isExpired ? '만료됨' : '활성';
  return `
    <div class="link-item">
      <div class="link-url">${esc(link.share_url)}</div>
      <div class="link-meta">
        <span class="${badgeClass}">${badgeText}</span>
        <span>${expires}</span>
        <span>${link.has_password ? '🔒 비밀번호' : '🔓 공개'}</span>
      </div>
      <div class="link-actions">
        <button class="btn btn-ghost btn-sm btn-copy-link" data-url="${esc(link.share_url)}">복사</button>
        ${isEffectivelyActive ? `<button class="btn btn-danger btn-sm btn-deactivate-link" data-id="${link.id}">비활성화</button>` : ''}
        <button class="btn btn-danger btn-sm btn-delete-link" data-id="${link.id}" data-active="${isEffectivelyActive}">삭제</button>
      </div>
    </div>`;
}

function formatDateInTZ(isoString, offsetMinutes) {
  // API가 반환한 UTC datetime(Z suffix)을 지정 timezone 기준 날짜로 변환
  const utcMs = new Date(isoString).getTime();
  const tzDate = new Date(utcMs + offsetMinutes * 60 * 1000);
  const y = tzDate.getUTCFullYear();
  const m = tzDate.getUTCMonth() + 1;
  const d = tzDate.getUTCDate();
  return `${y}. ${m}. ${d}.`;
}

function buildExpiresAt(dateVal, offsetMinutes) {
  const sign = offsetMinutes >= 0 ? '+' : '-';
  const abs  = Math.abs(offsetMinutes);
  const hh   = String(Math.floor(abs / 60)).padStart(2, '0');
  const mm   = String(abs % 60).padStart(2, '0');
  return `${dateVal}T23:59:59${sign}${hh}:${mm}`;
}

function renderLinkForm() {
  return `
    <div class="link-form mt-3">
      <form id="new-link-form">
        <div class="flex-col gap-3">
          <div class="form-group">
            <label class="form-label">비밀번호 (선택)</label>
            <input id="lf-password" type="password" class="form-input" placeholder="없으면 공개 링크">
          </div>
          <div class="form-group">
            <label class="form-label">만료일 (선택)</label>
            <div class="date-row">
              <input id="lf-expires" type="date" class="form-input">
              <button type="button" id="btn-clear-date" class="btn btn-ghost btn-sm">지우기</button>
            </div>
          </div>
          <div class="flex gap-2">
            <button type="submit" class="btn btn-primary btn-sm" id="btn-create-link">링크 생성</button>
          </div>
        </div>
      </form>
    </div>`;
}

function bindDatePicker() {
  document.getElementById('btn-clear-date').addEventListener('click', () => {
    document.getElementById('lf-expires').value = '';
  });
}

function photoListItemEdit(photo, coverPath, removeMode = false, isSelected = false) {
  const thumbUrl = `/api/admin/thumb?path=${encodeURIComponent(photo.file_path)}&size=small`;
  const isCover  = photo.file_path === coverPath;
  const name     = photo.file_path.split(/[\\/]/).pop();
  const addedAt  = photo.added_at
    ? new Date(photo.added_at).toLocaleDateString('ko-KR')
    : '—';
  return `
    <div class="photo-list-item${isCover ? ' is-cover' : ''}${isSelected ? ' remove-selected' : ''}" data-path="${esc(photo.file_path)}">
      <input type="checkbox" class="remove-check" ${isSelected ? 'checked' : ''}>
      <div class="photo-list-thumb">
        <img src="${thumbUrl}" alt="" loading="lazy" onerror="this.style.opacity='0.3'">
      </div>
      <span class="photo-list-name" title="${esc(photo.file_path)}">${esc(name)}</span>
      ${isCover ? '<span class="cover-badge" style="position:static;font-size:11px;padding:2px 6px">커버</span>' : ''}
      <div class="photo-list-meta"><span>추가: ${addedAt}</span></div>
      <div class="photo-list-actions">
        ${!isCover ? `<button class="photo-set-cover btn btn-ghost btn-sm" data-path="${esc(photo.file_path)}">커버로 설정</button>` : ''}
      </div>
    </div>`;
}

function photoSortLabel(sortBy, sortDir) {
  const by  = sortBy  === 'taken_at' ? '촬영일' : '파일명';
  const dir = sortDir === 'desc'     ? '↓'     : '↑';
  return `${by} ${dir}`;
}

function bindPhotoSort(albumId, photoState, refresh) {
  const btn     = document.getElementById('btn-photo-sort');
  const popover = document.getElementById('photo-sort-popover');
  if (!btn || !popover) return;

  btn.addEventListener('click', e => {
    e.stopPropagation();
    const open = popover.style.display !== 'none';
    popover.style.display = open ? 'none' : 'flex';
  });

  document.addEventListener('click', e => {
    if (!popover.contains(e.target) && e.target !== btn) {
      popover.style.display = 'none';
    }
  });

  document.getElementById('btn-sort-apply').addEventListener('click', async () => {
    const sortBy  = document.querySelector('input[name="ps-by"]:checked').value;
    const sortDir = document.querySelector('input[name="ps-dir"]:checked').value;
    popover.style.display = 'none';
    const applyBtn = document.getElementById('btn-sort-apply');
    applyBtn.disabled = true;
    try {
      await api.put(`/api/admin/albums/${albumId}`, {
        photo_sort_by: sortBy,
        photo_sort_dir: sortDir,
      });
      const updated = await api.get(`/api/admin/albums/${albumId}`);
      btn.textContent = `정렬: ${photoSortLabel(sortBy, sortDir)}`;
      photoState.photos = updated.photos;
      photoState.coverPath = updated.cover_path;
      refresh();
    } catch (err) {
      alert(err.message);
    } finally {
      applyBtn.disabled = false;
    }
  });
}

function bindPhotoPreview(albumId, photoState, refresh) {
  document.getElementById('photo-grid').addEventListener('click', e => {
    if (photoState.removeMode) return;
    if (e.target.closest('button')) return;
    const item = e.target.closest('.photo-thumb[data-path], .photo-list-item[data-path]');
    if (!item) return;
    const filePath = item.dataset.path;
    const allPaths = [
      ...document.querySelectorAll('#photo-grid .photo-thumb[data-path], #photo-grid .photo-list-item[data-path]'),
    ].map(el => el.dataset.path);
    const idx = allPaths.indexOf(filePath);
    if (idx === -1) return;
    openLightbox(allPaths, idx, {
      isCover: path => photoState.coverPath === path,
      onSetCover: async path => {
        await api.put(`/api/admin/albums/${albumId}`, { cover_path: path });
        photoState.coverPath = path;
        refresh();
      },
      onDelete: async path => {
        await api.delete(`/api/admin/albums/${albumId}/photos`, { photo_paths: [path] });
        photoState.photos = photoState.photos.filter(p => p.file_path !== path);
        refresh();
      },
    });
  });
}

function initAlbumThemePicker(currentTheme, serverTheme = 'dark') {
  const container = document.getElementById('album-theme-picker');
  if (!container) return;

  const isServerDefault = !currentTheme;
  const serverData = THEMES.find(t => t.id === serverTheme) || THEMES[0];

  const defaultSwatch = `
    <div class="theme-swatch${isServerDefault ? ' active' : ''}" data-theme-id="" title="서버 설정의 기본 테마 사용 (현재: ${serverData.label})">
      <div class="theme-swatch-colors">
        <div class="theme-swatch-bg" style="background:${serverData.bg}"></div>
        <div class="theme-swatch-accent" style="background:${serverData.accent}"></div>
        <span class="theme-swatch-server-badge">서버</span>
      </div>
      <span class="theme-swatch-label">서버 기본</span>
    </div>`;

  const themeSwatches = THEMES.map(t => `
    <div class="theme-swatch${t.id === currentTheme ? ' active' : ''}" data-theme-id="${t.id}" title="${t.label}">
      <div class="theme-swatch-colors">
        <div class="theme-swatch-bg" style="background:${t.bg}"></div>
        <div class="theme-swatch-accent" style="background:${t.accent}"></div>
      </div>
      <span class="theme-swatch-label">${t.label}</span>
    </div>`).join('');

  container.innerHTML = defaultSwatch + themeSwatches;

  container.querySelectorAll('.theme-swatch').forEach(el => {
    el.addEventListener('click', () => {
      document.getElementById('ss-ui-theme').value = el.dataset.themeId;
      container.querySelectorAll('.theme-swatch').forEach(s => s.classList.remove('active'));
      el.classList.add('active');
    });
  });
}

function photoThumb(photo, coverPath, removeMode = false, isSelected = false) {
  const thumbUrl = `/api/admin/thumb?path=${encodeURIComponent(photo.file_path)}&size=small`;
  const isCover  = photo.file_path === coverPath;
  return `
    <div class="photo-thumb${isCover ? ' is-cover' : ''}${isSelected ? ' remove-selected' : ''}" data-path="${esc(photo.file_path)}">
      <img src="${thumbUrl}" alt="" loading="lazy" onerror="this.style.opacity='0.3'">
      ${isCover ? '<span class="cover-badge">커버</span>' : ''}
      <input type="checkbox" class="remove-check" ${isSelected ? 'checked' : ''}>
      <button class="photo-set-cover" data-path="${esc(photo.file_path)}">커버로 설정</button>
    </div>`;
}

function bindRepairPaths(albumId, photoState, refresh, resetBroken) {
  const btn = document.getElementById('btn-repair-paths');
  if (!btn) return;
  btn.addEventListener('click', async () => {
    btn.disabled = true;
    btn.textContent = '복구 중...';
    try {
      const result = await api.post(`/api/admin/albums/${albumId}/repair-paths`);
      const { fixed, ambiguous, not_found } = result;

      const updated = await api.get(`/api/admin/albums/${albumId}`);
      photoState.photos = updated.photos;
      photoState.coverPath = updated.cover_path;
      resetBroken();
      btn.style.display = 'none';
      refresh();

      const parts = [];
      if (fixed.length)     parts.push(`${fixed.length}건 복구됨`);
      if (ambiguous.length) parts.push(`${ambiguous.length}건 후보 여러 개 (수동 확인 필요)`);
      if (not_found.length) parts.push(`${not_found.length}건 파일 없음`);
      alert(parts.length ? parts.join('\n') : '복구할 경로가 없습니다.');
    } catch (err) {
      alert(err.message);
      btn.disabled = false;
      btn.textContent = '경로 복구';
    }
  });
}

import { api } from '../api.js';
import { renderAdminShell } from '../layout.js';
import { esc, thumbImg } from '../utils.js';
import { openLightbox } from '../lightbox.js';
import { THEMES } from '../theme.js';
import { TITLE_FONTS, ensureTitleFontsLoaded, applyTitleFont } from '../title-fonts.js';
import { EFFECTS, EFFECT_LABELS } from '../slideshow-config.js';
import { initDateScrollIndicator } from '../date-scroll-indicator.js';

const BUNDLED_MUSIC_DIR_PREFIX = 'bundled/';
const BUNDLED_MUSIC_CREDITS = [
  { mood: '잔잔한', title: 'Calm Piano', artist: 'alex-morgan', file: 'alex-morgan-calm-piano-541028.mp3' },
  { mood: '잔잔한', title: 'Evening Calm Piano', artist: 'andriih', file: 'andriih-evening-calm-piano-580085.mp3' },
  { mood: '감성적', title: 'Emotional', artist: 'PaulYudin', file: 'paulyudin-emotional-emotional-music-573976.mp3' },
  { mood: '감성적', title: 'Emotional', artist: 'alex-morgan', file: 'alex-morgan-emotional-545518.mp3' },
  { mood: '경쾌한', title: 'Summer Pop', artist: 'JonasBlakewood', file: 'jonasblakewood-summer-pop-546980.mp3' },
  { mood: '경쾌한', title: 'Positive Dream Upbeat Pop', artist: 'LightBeatsMusic', file: 'lightbeatsmusic-positive-dream-upbeat-pop-513937.mp3' },
  { mood: '따뜻한·노스탤직', title: 'Warm Nostalgic Sentimental Music', artist: 'andriig', file: 'andriig-warm-nostalgic-sentimental-music-471262.mp3' },
  { mood: '따뜻한·노스탤직', title: 'Nostalgic Acoustic Guitar', artist: 'Tunetank', file: 'tunetank-nostalgic-acoustic-guitar-348939.mp3' },
  { mood: '웅장한', title: 'Epic Piano', artist: 'PaulYudin', file: 'paulyudin-epic-piano-154655.mp3' },
  { mood: '웅장한', title: 'Majestic Triumphant Epic Music', artist: 'alex-morgan', file: 'alex-morgan-majestic-triumphant-epic-music-583277.mp3' },
];

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
            <div class="form-group" id="ai-suggest-area"></div>
            <div>
              <span id="save-ok" class="text-success text-sm" style="display:none">저장됨 ✓</span>
            </div>
          </form>
          <div class="form-group">
            <label class="form-label">커버</label>
            <div id="cover-preview-wrap">${coverPreviewHtml(album.photos, album.cover_path)}</div>
          </div>
          <div class="flex items-center gap-2">
            <span class="form-label" style="margin:0">조회 수</span>
            <span id="view-count-value">${(album.view_count ?? 0).toLocaleString()}회</span>
            <button type="button" class="btn btn-ghost btn-sm" id="btn-reset-views">초기화</button>
          </div>
          <hr class="divider" style="margin:12px 0">
          <div id="style-error" class="alert alert-error" style="display:none"></div>
          <form id="style-form" class="flex-col gap-3">
            <div class="form-group">
              <label style="display:flex;align-items:center;gap:6px;font-size:14px">
                <input type="checkbox" id="f-show-all-tags" ${album.show_all_tags ? 'checked' : ''}>
                태그 모두 표시
              </label>
              <p class="text-muted text-sm" style="margin:4px 0 0">인물 등 개인 정보가 포함된 모든 태그가 표시됩니다</p>
            </div>
            <div class="form-group">
              <label class="form-label">앨범 테마</label>
              <div class="theme-picker" id="album-theme-picker"></div>
              <input type="hidden" id="f-ui-theme" value="${album.ui_theme || ''}">
            </div>
            <div class="form-group">
              <label class="form-label">폰트</label>
              <select id="f-title-font" class="form-select">
                <option value="">시스템 기본</option>
                ${TITLE_FONTS.map(f => `<option value="${f.id}" ${album.title_font === f.id ? 'selected' : ''}>${esc(f.label)}</option>`).join('')}
              </select>
              <p class="title-font-preview" id="title-font-preview"></p>
              <p class="text-muted title-font-note" id="title-font-note"></p>
            </div>
            <div class="form-group">
              <label class="form-label">배경음악</label>
              <div id="music-list" class="music-list"></div>
              <button type="button" class="btn btn-ghost btn-sm" id="btn-browse-music">+ 음악 파일 선택</button>
              <p class="music-copyright-notice">저작권을 확인한 음원만 사용하세요. 저작권 문제는 사용자 책임입니다. 저작권 무료 음악은 <a href="https://pixabay.com/music/" target="_blank" rel="noopener noreferrer">Pixabay Music</a> 등에서 구할 수 있습니다.</p>
              <details class="bundled-music-info">
                <summary>기본 제공 음원 ${BUNDLED_MUSIC_CREDITS.length}곡 (무료, 저장소에 번들됨)</summary>
                <ul>
                  ${BUNDLED_MUSIC_CREDITS.map(t => `<li>${esc(t.mood)} — ${esc(t.title)} <span class="text-muted">(${esc(t.artist)})</span></li>`).join('')}
                </ul>
                <p class="text-muted">위 "+ 음악 파일 선택" 목록의 <code>bundled/</code> 폴더 안에서 바로 선택할 수 있습니다.</p>
              </details>
            </div>
            <div>
              <span id="style-save-ok" class="text-success text-sm" style="display:none">저장됨 ✓</span>
            </div>
          </form>
        </div>

      <!-- Slideshow defaults -->
      <div class="card aei-ss">
          <p class="section-title">슬라이드쇼 기본 설정</p>
          <div id="ss-error" class="alert alert-error" style="display:none"></div>
          <form id="ss-form" class="flex-col gap-3">
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
              <span id="ss-save-ok" class="text-success text-sm" style="display:none">저장됨 ✓</span>
            </div>
          </form>
        </div>

      <!-- Photos -->
      <div class="card aei-photos">
          <div class="flex items-center justify-between" style="margin-bottom:12px">
            <p class="section-title" style="margin:0">사진 (<span id="photo-count-label">${album.photos.length.toLocaleString()}</span>장)</p>
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
                      <label><input type="radio" name="ps-dir" value="asc" ${album.photo_sort_dir === 'asc' ? 'checked' : ''}> 오름차순</label>
                      <label><input type="radio" name="ps-dir" value="desc" ${(album.photo_sort_dir || 'desc') !== 'asc' ? 'checked' : ''}> 내림차순</label>
                    </div>
                  </div>
                  <button type="button" class="btn btn-primary btn-sm" id="btn-sort-apply">적용</button>
                </div>
              </div>
              <div class="view-toggle">
                <button type="button" id="btn-photo-view-grid" class="btn btn-ghost btn-sm active" title="그리드 보기">⊞</button>
                <button type="button" id="btn-photo-view-list" class="btn btn-ghost btn-sm" title="리스트 보기">☰</button>
                <button type="button" id="btn-photo-view-date" class="btn btn-ghost btn-sm" title="날짜별 보기">📅</button>
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
          <div class="date-scroll-indicator" id="date-scroll-indicator"></div>
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

  let musicPaths = [...(album.music_paths || [])];
  bindInfoForm(album.id);
  const scheduleStyleSave = bindStyleForm(album.id, () => musicPaths);
  document.getElementById('f-show-all-tags').addEventListener('change', scheduleStyleSave);
  const scheduleSsSave    = bindSlideshowForm(album.id);

  initAlbumThemePicker(album.ui_theme, serverTheme, scheduleStyleSave);
  initTitleFontPicker(scheduleStyleSave);

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
        scheduleStyleSave();
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
        scheduleStyleSave();
      });
    });
  }
  refreshMusicList();

  document.getElementById('btn-browse-music').addEventListener('click', () => {
    openMusicModal(musicPaths, selected => { musicPaths = selected; refreshMusicList(); scheduleStyleSave(); });
  });

  bindStyleSuggest(album.id, {
    setMusicPaths: paths => { musicPaths = paths; refreshMusicList(); },
  }, scheduleStyleSave);

  document.getElementById('ss-volume').addEventListener('input', e => {
    document.getElementById('ss-vol-label').textContent = `${e.target.value}%`;
    scheduleSsSave();
  });

  document.getElementById('ss-interval').addEventListener('input', scheduleSsSave);
  document.getElementById('ss-effect').addEventListener('change', scheduleSsSave);
  ['ss-order', 'ss-music', 'ss-loop'].forEach(name =>
    document.querySelectorAll(`input[name="${name}"]`).forEach(el => el.addEventListener('change', scheduleSsSave))
  );

  const photoState = { viewMode: 'grid', coverPath: album.cover_path, photos: [...album.photos], removeMode: false, removeSelected: new Set() };
  photoState.recomputeDateOffsets = initDateScrollIndicator(
    'date-scroll-indicator', '#photo-grid', () => photoState.viewMode === 'date'
  );
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
    el.className = photoState.viewMode === 'list' ? 'photo-list'
      : photoState.viewMode === 'date' ? 'photo-date-groups'
      : 'photo-grid';
    if (photoState.removeMode) el.classList.add('remove-mode');
    if (!photoState.photos.length) {
      el.innerHTML = '<p class="text-muted text-sm">사진이 없습니다</p>';
    } else if (photoState.viewMode === 'date') {
      el.innerHTML = groupPhotosByDate(photoState.photos).map(g => `
        <div class="date-group">
          <div class="date-group-header" data-key="${esc(g.key)}">${esc(g.label)} <span class="text-muted text-sm">(${g.photos.length.toLocaleString()}장)</span></div>
          <div class="photo-grid">${g.photos.map(p =>
            photoThumb(p, photoState.coverPath, photoState.removeMode, photoState.removeSelected.has(p.file_path))
          ).join('')}</div>
        </div>`).join('');
    } else {
      el.innerHTML = photoState.photos.map(p =>
        photoState.viewMode === 'list'
          ? photoListItemEdit(p, photoState.coverPath, photoState.removeMode, photoState.removeSelected.has(p.file_path))
          : photoThumb(p, photoState.coverPath, photoState.removeMode, photoState.removeSelected.has(p.file_path))
      ).join('');
    }
    attachImageErrorTracking();
    photoState.recomputeDateOffsets();
    const countEl = document.getElementById('photo-count-label');
    if (countEl) countEl.textContent = photoState.photos.length.toLocaleString();
    const coverEl = document.getElementById('cover-preview-wrap');
    if (coverEl) coverEl.innerHTML = coverPreviewHtml(photoState.photos, photoState.coverPath);
  }

  function setPhotoViewMode(mode) {
    photoState.viewMode = mode;
    document.getElementById('btn-photo-view-grid').classList.toggle('active', mode === 'grid');
    document.getElementById('btn-photo-view-list').classList.toggle('active', mode === 'list');
    document.getElementById('btn-photo-view-date').classList.toggle('active', mode === 'date');

    const filenameRadio = document.querySelector('input[name="ps-by"][value="filename"]');
    if (filenameRadio) {
      filenameRadio.disabled = mode === 'date';
      if (mode === 'date' && filenameRadio.checked) {
        const takenAtRadio = document.querySelector('input[name="ps-by"][value="taken_at"]');
        if (takenAtRadio) takenAtRadio.checked = true;
      }
    }

    refreshPhotoGrid();
  }

  document.getElementById('btn-photo-view-grid').addEventListener('click', () => setPhotoViewMode('grid'));
  document.getElementById('btn-photo-view-list').addEventListener('click', () => setPhotoViewMode('list'));
  document.getElementById('btn-photo-view-date').addEventListener('click', () => setPhotoViewMode('date'));

  bindViewCountReset(album.id);
  bindPhotoRemoveMode(album.id, photoState, refreshPhotoGrid);
  bindCoverSet(album.id, photoState, refreshPhotoGrid);
  bindPhotoSort(album.id, photoState, refreshPhotoGrid);
  bindPhotoPreview(album.id, photoState, refreshPhotoGrid);
  bindRepairPaths(album.id, photoState, refreshPhotoGrid, () => { brokenDetected = false; });
  bindLinkActions(album.id, links, tzOffset);
  attachImageErrorTracking();
}

function bindSlideshowForm(albumId) {
  document.getElementById('ss-form').addEventListener('submit', e => e.preventDefault());

  return createAutosave(() => api.put(`/api/admin/albums/${albumId}`, {
    slideshow_interval: parseInt(document.getElementById('ss-interval').value, 10) || 5,
    slideshow_order:    document.querySelector('input[name="ss-order"]:checked').value,
    slideshow_effect:   document.getElementById('ss-effect').value,
    slideshow_music:    document.querySelector('input[name="ss-music"]:checked').value === 'on',
    slideshow_volume:   parseInt(document.getElementById('ss-volume').value, 10),
    slideshow_loop:     document.querySelector('input[name="ss-loop"]:checked').value === 'on',
  }), 'ss-error', 'ss-save-ok');
}

/* ── Autosave: debounce field changes, coalesce saves that land while a
   request is in flight so the field's own latest value is never lost ── */
function createAutosave(saveFn, errElId, okElId) {
  let timer = null;
  let isSaving = false;
  let pending = false;

  async function runSave() {
    isSaving = true;
    const errEl = document.getElementById(errElId);
    const okEl  = document.getElementById(okElId);
    do {
      pending = false;
      errEl.style.display = 'none';
      okEl.textContent = '저장 중...';
      okEl.style.display = 'inline';
      try {
        await saveFn();
      } catch (err) {
        isSaving = false;
        okEl.style.display = 'none';
        errEl.textContent = err.message;
        errEl.style.display = 'block';
        return;
      }
    } while (pending);
    isSaving = false;
    okEl.textContent = '저장됨 ✓';
    setTimeout(() => { if (!isSaving) okEl.style.display = 'none'; }, 2000);
  }

  return function scheduleSave() {
    const okEl = document.getElementById(okElId);
    if (okEl) okEl.style.display = 'none';
    clearTimeout(timer);
    timer = setTimeout(() => {
      if (isSaving) pending = true;
      else runSave();
    }, 600);
  };
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

function bindInfoForm(albumId) {
  document.getElementById('info-form').addEventListener('submit', e => e.preventDefault());

  const scheduleSave = createAutosave(() => {
    const name = document.getElementById('f-name').value.trim();
    if (!name) return Promise.reject(new Error('앨범 이름을 입력하세요'));
    return api.put(`/api/admin/albums/${albumId}`, {
      name,
      description: document.getElementById('f-desc').value.trim() || null,
    });
  }, 'info-error', 'save-ok');

  document.getElementById('f-name').addEventListener('input', () => {
    updateTitleFontPreview();
    scheduleSave();
  });
  document.getElementById('f-desc').addEventListener('input', scheduleSave);

  return scheduleSave;
}

function bindStyleForm(albumId, getMusicPaths) {
  document.getElementById('style-form').addEventListener('submit', e => e.preventDefault());

  return createAutosave(() => api.put(`/api/admin/albums/${albumId}`, {
    ui_theme:   document.getElementById('f-ui-theme').value || null,
    title_font: document.getElementById('f-title-font').value || null,
    music_paths: getMusicPaths(),
    show_all_tags: document.getElementById('f-show-all-tags').checked,
  }), 'style-error', 'style-save-ok');
}

/* AI 스타일 추천(LLM) — 앨범 이름·설명만 전송, 사진/EXIF/태그는 절대 보내지 않음.
   버튼은 항상 보이되, 설정(Admin 설정 화면)에서 provider+API 키가 등록돼 있지 않으면
   비활성화하고 버튼 아래 안내 문구로 "설정에서 등록하라"고 알려준다. */
async function bindStyleSuggest(albumId, musicCtl, scheduleStyleSave) {
  const area = document.getElementById('ai-suggest-area');
  if (!area) return;

  area.innerHTML = `
    <button type="button" class="btn btn-ghost btn-sm" id="btn-ai-suggest" disabled>✨ AI 스타일 추천 받기</button>
    <p class="text-muted text-sm" id="ai-suggest-hint" style="margin:4px 0 0">불러오는 중...</p>
    <div id="ai-suggest-card" style="display:none"></div>`;
  const btn = document.getElementById('btn-ai-suggest');
  const hint = document.getElementById('ai-suggest-hint');

  let cfg = null;
  try {
    cfg = await api.get('/api/admin/llm/settings');
  } catch {
    cfg = null; // 조회 실패(권한 등) — 미설정과 동일하게 처리(버튼 비활성 유지)
  }

  // await 동안 다른 앨범으로 이동했을 수 있음(lightbox.js의 photo-info 응답과 동일한 stale 가드) —
  // 같은 id로 다시 조회해 그 사이 DOM이 사라졌거나 다른 화면으로 교체되지 않았는지 확인.
  if (document.getElementById('ai-suggest-area') !== area) return;

  const configured = !!(cfg && cfg.provider && cfg.api_key_set);
  if (!configured) {
    hint.innerHTML = `AI가 앨범 이름·설명을 보고 배경음악·테마·폰트를 추천해줘요.
      <a href="/admin/settings" data-link>설정</a>에서 키를 등록하면 이용할 수 있습니다.`;
    return;
  }

  btn.disabled = false;
  hint.textContent = '앨범 이름·설명만 AI에 전송됩니다 (사진은 보내지 않음)';

  btn.addEventListener('click', async () => {
    const cardEl = document.getElementById('ai-suggest-card');
    const name = document.getElementById('f-name').value.trim();
    if (!name) { alert('앨범 이름을 먼저 입력하세요'); return; }
    btn.disabled = true;
    btn.textContent = '추천 받는 중...';
    cardEl.style.display = 'none';
    try {
      const suggestion = await api.post('/api/admin/llm/suggest-style', {
        name,
        description: document.getElementById('f-desc').value.trim() || null,
      });
      renderSuggestCard(cardEl, suggestion, musicCtl, scheduleStyleSave);
    } catch (e) {
      alert(e.message);
    } finally {
      btn.disabled = false;
      btn.textContent = '✨ AI 스타일 추천 받기';
    }
  });
}

function renderSuggestCard(cardEl, suggestion, musicCtl, scheduleStyleSave) {
  const { music_path, ui_theme, title_font, reason } = suggestion;
  // 음악 목록 모달(openMusicModal)과 동일하게 파일명이 아니라 큐레이션 라벨("무드 — 곡명")로 표시 —
  // 매칭 안 되면(번들 곡 신설 등으로 크레딧 목록이 아직 안 따라온 경우) 파일명으로 폴백.
  const musicFile = music_path ? music_path.split(/[\\/]/).pop() : null;
  const musicCredit = musicFile && BUNDLED_MUSIC_CREDITS.find(c => c.file === musicFile);
  const musicLabel = musicCredit ? `${musicCredit.mood} — ${musicCredit.title}` : musicFile;
  const themeData  = THEMES.find(t => t.id === ui_theme);
  const fontData   = TITLE_FONTS.find(f => f.id === title_font);
  const hasAny = musicLabel || themeData || fontData;

  cardEl.innerHTML = `
    <div class="ai-suggest-card">
      ${reason ? `<p class="ai-suggest-reason">"${esc(reason)}"</p>` : ''}
      <ul class="ai-suggest-list">
        ${musicLabel ? `<li>🎵 배경음악 — ${esc(musicLabel)}</li>` : ''}
        ${themeData  ? `<li>🎨 테마 — ${esc(themeData.label)}</li>` : ''}
        ${fontData   ? `<li>🔤 폰트 — ${esc(fontData.label)}</li>` : ''}
        ${hasAny ? '' : '<li class="text-muted">추천할 항목을 찾지 못했습니다</li>'}
      </ul>
      ${musicLabel ? '<p class="text-muted text-sm">적용하면 기존 배경음악 목록을 대체합니다</p>' : ''}
      <div class="settings-actions">
        ${hasAny ? '<button type="button" class="btn btn-primary btn-sm" id="btn-ai-suggest-apply">적용</button>' : ''}
        <button type="button" class="btn btn-ghost btn-sm" id="btn-ai-suggest-dismiss">닫기</button>
      </div>
    </div>`;
  cardEl.style.display = '';

  document.getElementById('btn-ai-suggest-dismiss').addEventListener('click', () => {
    cardEl.style.display = 'none';
    cardEl.innerHTML = '';
  });

  document.getElementById('btn-ai-suggest-apply')?.addEventListener('click', () => {
    if (music_path) musicCtl.setMusicPaths([music_path]);
    if (ui_theme) {
      document.getElementById('f-ui-theme').value = ui_theme;
      document.getElementById('album-theme-picker')?.querySelectorAll('.theme-swatch').forEach(s =>
        s.classList.toggle('active', s.dataset.themeId === ui_theme));
    }
    if (title_font) {
      document.getElementById('f-title-font').value = title_font;
      updateTitleFontPreview();
    }
    scheduleStyleSave();
    cardEl.style.display = 'none';
    cardEl.innerHTML = '';
  });
}

/* 앨범 이름 + 선택된 폰트로 실제 Google Fonts 렌더링 미리보기 (드롭다운 변경·이름 입력 시 즉시 갱신) */
function updateTitleFontPreview() {
  const previewEl = document.getElementById('title-font-preview');
  const noteEl = document.getElementById('title-font-note');
  const nameEl = document.getElementById('f-name');
  if (!previewEl || !nameEl) return;
  const fontId = document.getElementById('f-title-font').value || null;
  previewEl.textContent = nameEl.value.trim() || '앨범 이름';
  applyTitleFont(previewEl, fontId);
  if (noteEl) {
    const font = TITLE_FONTS.find(f => f.id === fontId);
    noteEl.textContent = font ? font.note : '시스템 기본 폰트를 사용해요';
  }
}

function initTitleFontPicker(onChange) {
  ensureTitleFontsLoaded();
  updateTitleFontPreview();
  document.getElementById('f-title-font').addEventListener('change', () => {
    updateTitleFontPreview();
    onChange();
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
      // 번들 기본 음원은 항상 최상단에, 큐레이션 순서(BUNDLED_MUSIC_CREDITS)대로 표시
      const bundledOrder = BUNDLED_MUSIC_CREDITS.map(c => c.file);
      const bundledFiles = files
        .filter(f => f.rel.startsWith(BUNDLED_MUSIC_DIR_PREFIX))
        .sort((a, b) => bundledOrder.indexOf(a.name) - bundledOrder.indexOf(b.name));
      const otherFiles = files.filter(f => !f.rel.startsWith(BUNDLED_MUSIC_DIR_PREFIX));

      const renderItem = f => {
        const credit = bundledOrder.includes(f.name) && BUNDLED_MUSIC_CREDITS.find(c => c.file === f.name);
        const label = credit ? `${credit.mood} — ${credit.title}` : f.name;
        const sub = credit ? `${credit.artist} · Pixabay Music` : (f.rel !== f.name ? f.rel : '');
        return `
        <div class="music-file-item${selected.has(f.path) ? ' selected' : ''}" data-path="${esc(f.path)}">
          <input type="checkbox" ${selected.has(f.path) ? 'checked' : ''}>
          <div style="overflow:hidden;min-width:0">
            <div class="music-file-name">${esc(label)}</div>
            ${sub ? `<div class="music-file-rel">${esc(sub)}</div>` : ''}
          </div>
        </div>`;
      };

      const bundledSection = bundledFiles.length ? `
        <p class="music-file-group-label">기본 제공 음원</p>
        <div class="music-file-list">${bundledFiles.map(renderItem).join('')}</div>` : '';
      const otherSection = otherFiles.length ? `
        ${bundledFiles.length ? '<p class="music-file-group-label">내가 추가한 음악</p>' : ''}
        <div class="music-file-list">${otherFiles.map(renderItem).join('')}</div>` : '';

      body.innerHTML = `<div class="music-file-scroll">${bundledSection}${otherSection}</div>`;

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
    countLabel.textContent = `${n.toLocaleString()}개 선택됨`;
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
    if (!confirm(`선택한 ${paths.length.toLocaleString()}장을 앨범에서 제외하시겠습니까?`)) return;
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
      <div class="photo-list-thumb thumb-loading">
        ${thumbImg(thumbUrl, 0.3)}
      </div>
      <span class="photo-list-name" title="${esc(photo.file_path)}">${esc(name)}</span>
      ${isCover ? '<span class="cover-badge" style="position:static;font-size:11px;padding:2px 6px">커버</span>' : ''}
      <div class="photo-list-meta"><span>추가: ${addedAt}</span></div>
      <div class="photo-list-actions">
        ${!isCover ? `<button class="photo-set-cover btn btn-ghost btn-sm" data-path="${esc(photo.file_path)}">커버로 설정</button>` : ''}
      </div>
    </div>`;
}

function coverPreviewHtml(photos, coverPath) {
  const cover = photos.find(p => p.file_path === coverPath) || photos[0];
  if (!cover) return '';
  const thumbUrl = `/api/admin/thumb?path=${encodeURIComponent(cover.file_path)}&size=medium`;
  return `
    <div class="aei-cover-preview">
      <img src="${thumbUrl}" alt="커버 미리보기">
    </div>
    <p class="text-muted text-sm" style="margin:6px 0 12px">공유 앨범 화면 상단에 이렇게 표시됩니다</p>`;
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

function initAlbumThemePicker(currentTheme, serverTheme = 'dark', onChange = () => {}) {
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
      document.getElementById('f-ui-theme').value = el.dataset.themeId;
      container.querySelectorAll('.theme-swatch').forEach(s => s.classList.remove('active'));
      el.classList.add('active');
      onChange();
    });
  });
}

function groupPhotosByDate(photos) {
  // 현재 정렬 순서를 그대로 유지한 채 날짜(taken_at)가 바뀌는 지점마다 구간을 나눈다.
  const groups = [];
  for (const p of photos) {
    const key = p.taken_at ? p.taken_at.slice(0, 10) : '';
    const last = groups[groups.length - 1];
    if (last && last.key === key) {
      last.photos.push(p);
    } else {
      groups.push({ key, label: key || '날짜 정보 없음', photos: [p] });
    }
  }
  return groups;
}

function photoThumb(photo, coverPath, removeMode = false, isSelected = false) {
  const thumbUrl = `/api/admin/thumb?path=${encodeURIComponent(photo.file_path)}&size=small`;
  const isCover  = photo.file_path === coverPath;
  const isVideo  = photo.media_type === 'video';
  return `
    <div class="photo-thumb thumb-loading${isCover ? ' is-cover' : ''}${isSelected ? ' remove-selected' : ''}" data-path="${esc(photo.file_path)}">
      ${thumbImg(thumbUrl, 0.3)}
      ${isVideo ? '<span class="media-video-badge"></span>' : ''}
      ${isCover ? '<span class="cover-badge">커버</span>' : ''}
      <input type="checkbox" class="remove-check" ${isSelected ? 'checked' : ''}>
      ${isVideo ? '' : `<button class="photo-set-cover" data-path="${esc(photo.file_path)}">커버로 설정</button>`}
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
      if (fixed.length)     parts.push(`${fixed.length.toLocaleString()}건 복구됨`);
      if (ambiguous.length) parts.push(`${ambiguous.length.toLocaleString()}건 후보 여러 개 (수동 확인 필요)`);
      if (not_found.length) parts.push(`${not_found.length.toLocaleString()}건 파일 없음`);
      alert(parts.length ? parts.join('\n') : '복구할 경로가 없습니다.');
    } catch (err) {
      alert(err.message);
      btn.disabled = false;
      btn.textContent = '경로 복구';
    }
  });
}

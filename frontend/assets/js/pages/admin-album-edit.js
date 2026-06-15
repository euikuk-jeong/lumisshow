import { api } from '../api.js';
import { getToken } from '../auth.js';
import { renderAdminShell } from '../layout.js';
import { esc } from '../utils.js';

export async function renderAdminAlbumEdit(albumId) {
  const isNew = !albumId;
  const title = isNew ? '새 앨범' : '앨범 편집';

  renderAdminShell(`
    <a href="/admin" class="page-back" data-link>← 앨범 목록</a>
    <div class="page-header">
      <h1 class="page-title">${title}</h1>
      ${!isNew ? `<button class="btn btn-danger btn-sm" id="btn-delete">삭제</button>` : ''}
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
    const [album, links] = await Promise.all([
      api.get(`/api/admin/albums/${albumId}`),
      api.get(`/api/admin/albums/${albumId}/links`),
    ]);
    renderEditForm(album, links);
    bindDeleteAlbum(albumId);
  } catch (e) {
    el.innerHTML = `<div class="alert alert-error">${esc(e.message)}</div>`;
  }
}

function renderEditForm(album, links) {
  const el    = document.getElementById('edit-content');
  const token = getToken();
  el.innerHTML = `
    <div class="album-edit-layout">
      <!-- Left: Info + Photos -->
      <div class="flex-col gap-4">
        <!-- Info -->
        <div class="card">
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
        </div>

        <!-- Photos -->
        <div class="card">
          <div class="flex items-center justify-between" style="margin-bottom:12px">
            <p class="section-title" style="margin:0">사진 (${album.photos.length}장)</p>
            <a href="/admin/browse?album_id=${album.id}" class="btn btn-ghost btn-sm" data-link>+ 사진 추가</a>
          </div>
          <div id="photo-grid" class="photo-grid">
            ${album.photos.map(p => photoThumb(p, token)).join('') || '<p class="text-muted text-sm">사진이 없습니다</p>'}
          </div>
        </div>
      </div>

      <!-- Right: Share links -->
      <div>
        <div class="card">
          <p class="section-title">공유 링크</p>
          <div id="links-container">${renderLinks(links)}</div>
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

  bindInfoForm(album.id, () => musicPaths);
  bindPhotoRemove(album.id);
  bindLinkActions(album.id, links);
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

function bindPhotoRemove(albumId) {
  document.getElementById('photo-grid').addEventListener('click', async e => {
    const btn = e.target.closest('.photo-remove');
    if (!btn) return;
    const filePath = btn.dataset.path;
    if (!confirm('이 사진을 앨범에서 제외하시겠습니까?')) return;
    btn.disabled = true;
    try {
      await api.delete(`/api/admin/albums/${albumId}/photos`, { photo_paths: [filePath] });
      btn.closest('.photo-thumb').remove();
    } catch (err) {
      alert(err.message);
      btn.disabled = false;
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

function bindLinkActions(albumId, links) {
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

  document.getElementById('link-form-area').addEventListener('submit', async e => {
    e.preventDefault();
    const pwd     = document.getElementById('lf-password').value || null;
    const expires = document.getElementById('lf-expires').value || null;
    const btn     = document.getElementById('btn-create-link');
    btn.disabled  = true;
    try {
      const link = await api.post(`/api/admin/albums/${albumId}/links`, {
        password:   pwd || null,
        expires_at: expires || null,
      });
      links.push(link);
      document.getElementById('links-container').innerHTML = renderLinks(links);
      document.getElementById('lf-password').value = '';
      document.getElementById('lf-expires').value = '';
      formArea.style.display = 'none';
      bindLinkDeactivate(albumId);
    } catch (err) {
      alert(err.message);
    } finally {
      btn.disabled = false;
    }
  });

  bindLinkDeactivate(albumId);
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
        btn.remove();
      } catch (err) {
        alert(err.message);
      }
    });
  });
}

/* ── Render helpers ─────────────────────────────────────── */
function renderLinks(links) {
  if (!links.length) return '<p class="text-muted text-sm">링크가 없습니다</p>';
  return `<div class="link-list">${links.map(renderLinkItem).join('')}</div>`;
}

function renderLinkItem(link) {
  const expires = link.expires_at
    ? `만료: ${new Date(link.expires_at).toLocaleDateString('ko-KR')}`
    : '만료 없음';
  const badgeClass = link.is_active ? 'badge badge-active' : 'badge badge-inactive';
  const badgeText  = link.is_active ? '활성' : '비활성';
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
        ${link.is_active ? `<button class="btn btn-danger btn-sm btn-deactivate-link" data-id="${link.id}">비활성화</button>` : ''}
      </div>
    </div>`;
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
            <input id="lf-expires" type="datetime-local" class="form-input">
          </div>
          <div class="flex gap-2">
            <button type="submit" class="btn btn-primary btn-sm" id="btn-create-link">링크 생성</button>
          </div>
        </div>
      </form>
    </div>`;
}

function photoThumb(photo, token) {
  const thumbUrl = `/api/admin/thumb?path=${encodeURIComponent(photo.file_path)}&size=small&token=${token}`;
  return `
    <div class="photo-thumb">
      <img src="${thumbUrl}" alt="" loading="lazy" onerror="this.style.opacity='0.3'">
      <button class="photo-remove" data-path="${esc(photo.file_path)}" title="제외">✕</button>
    </div>`;
}

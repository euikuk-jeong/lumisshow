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
    el.innerHTML = `<div class="alert alert-error">${e.message}</div>`;
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
              <label class="form-label">배경음악 경로</label>
              <input id="f-music" type="text" class="form-input" value="${esc(album.music_path || '')}" placeholder="/mnt/photos/music/song.mp3">
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

  bindInfoForm(album.id);
  bindPhotoRemove(album.id);
  bindLinkActions(album.id, links);
}

function bindInfoForm(albumId) {
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
        music_path:  document.getElementById('f-music').value.trim() || null,
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
        await api.put(`/api/admin/albums/${albumId}/links/${linkId}`, { is_active: false });
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

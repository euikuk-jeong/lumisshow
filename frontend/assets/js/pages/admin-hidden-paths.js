import { api } from '../api.js';
import { renderAdminShell } from '../layout.js';
import { esc } from '../utils.js';

export async function renderAdminHiddenPaths() {
  renderAdminShell(`
    <a href="/admin/settings" class="page-back" data-link>← 설정</a>
    <div class="page-header">
      <h1 class="page-title">탐색기 숨김 경로</h1>
    </div>
    <div id="hp-content"><div class="loading"></div></div>
  `, '/admin/settings');

  try {
    const settings = await api.get('/api/admin/settings');
    renderPage(settings.browse_hidden_paths || []);
  } catch (e) {
    document.getElementById('hp-content').innerHTML =
      `<div class="alert alert-error">${esc(e.message)}</div>`;
  }
}

function normalizePath(p) {
  return p.trim().replace(/\\/g, '/').replace(/^\/+|\/+$/g, '');
}

let _paths = [];

function renderPage(initialPaths) {
  _paths = [...initialPaths];

  document.getElementById('hp-content').innerHTML = `
    <div class="card" style="max-width:640px">
      <p class="text-muted text-sm" style="margin-bottom:16px">
        사진 탐색 화면에서 숨길 폴더를 지정합니다.<br>
        PHOTO_ROOT 기준 상대 경로로 입력하세요 (예: <code>private/family</code>).
      </p>

      <div id="hp-list" class="hidden-paths-list"></div>

      <div class="hidden-path-add-row" style="margin-top:12px">
        <input id="hp-input" type="text" class="form-input" placeholder="폴더 경로 입력...">
        <button class="btn btn-secondary btn-sm" id="btn-hp-add">추가</button>
      </div>
      <div id="hp-error" class="text-error text-sm" style="display:none;margin-top:6px"></div>

      <div class="settings-actions" style="margin-top:20px">
        <button class="btn btn-primary btn-sm" id="btn-hp-save">저장</button>
        <span id="hp-ok" class="text-success text-sm" style="display:none">저장됨 ✓</span>
      </div>
    </div>
  `;

  renderList();
  bindHandlers();
}

function renderList() {
  const el = document.getElementById('hp-list');
  if (!_paths.length) {
    el.innerHTML = '<p class="text-muted text-sm">숨김 경로 없음</p>';
    return;
  }
  el.innerHTML = _paths.map((p, i) =>
    `<div class="hidden-path-item">
      <span class="hidden-path-value">${esc(p)}</span>
      <button class="btn btn-ghost btn-sm btn-icon hidden-path-delete" data-index="${i}" title="삭제">✕</button>
    </div>`
  ).join('');
  el.querySelectorAll('.hidden-path-delete').forEach(btn => {
    btn.addEventListener('click', () => {
      _paths.splice(parseInt(btn.dataset.index, 10), 1);
      renderList();
    });
  });
}

function showError(msg) {
  const el = document.getElementById('hp-error');
  el.textContent = msg;
  el.style.display = 'block';
}

function clearError() {
  document.getElementById('hp-error').style.display = 'none';
}

function bindHandlers() {
  const input = document.getElementById('hp-input');

  async function addPath() {
    const val = normalizePath(input.value);
    clearError();

    if (!val) {
      showError('경로를 입력해 주세요.');
      return;
    }
    if (_paths.includes(val)) {
      showError('이미 추가된 경로입니다.');
      return;
    }

    const btn = document.getElementById('btn-hp-add');
    btn.disabled = true;
    btn.textContent = '확인 중...';
    try {
      const res = await api.get(`/api/admin/path-exists?path=${encodeURIComponent(val)}`);
      if (!res.exists) {
        showError('경로가 존재하지 않습니다. PHOTO_ROOT 기준 상대 경로를 확인해 주세요.');
        return;
      }
      _paths.push(val);
      input.value = '';
      renderList();
    } catch (e) {
      showError(e.message);
    } finally {
      btn.disabled = false;
      btn.textContent = '추가';
    }
  }

  document.getElementById('btn-hp-add').addEventListener('click', addPath);
  input.addEventListener('keydown', e => { if (e.key === 'Enter') addPath(); });
  input.addEventListener('input', clearError);

  document.getElementById('btn-hp-save').addEventListener('click', async () => {
    const btn = document.getElementById('btn-hp-save');
    btn.disabled = true;
    try {
      await api.patch('/api/admin/settings', { browse_hidden_paths: _paths });
      const okEl = document.getElementById('hp-ok');
      okEl.style.display = 'inline';
      setTimeout(() => { okEl.style.display = 'none'; }, 2000);
    } catch (e) {
      alert(e.message);
    } finally {
      btn.disabled = false;
    }
  });
}

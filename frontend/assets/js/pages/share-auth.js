import { shareApi } from '../api.js';
import { esc, getSiteTitle } from '../utils.js';

export async function renderShareAuth(token) {
  const app = document.getElementById('app');
  app.innerHTML = '<div class="loading"></div>';

  let linkInfo;
  try {
    linkInfo = await shareApi.get(`/api/share/${token}`);
  } catch (e) {
    _renderError(app, e.message);
    return;
  }

  if (!linkInfo.requires_password) {
    try {
      await shareApi.post(`/api/share/${token}/auth`, {});
      window.navigate(`/s/${token}/view`, true);
    } catch (e) {
      _renderError(app, e.message);
    }
    return;
  }

  app.innerHTML = `
    <div class="viewer-center">
      <div class="viewer-auth-card">
        <div class="viewer-icon">🔒</div>
        <h1 class="viewer-auth-title" id="auth-site-title">LumisShow</h1>
        <p class="viewer-auth-desc text-muted">패스워드를 입력하세요</p>
        <div id="auth-error" class="alert alert-error" style="display:none"></div>
        <form id="auth-form" style="margin-top:16px">
          <input type="password" id="auth-pw" class="form-input" placeholder="패스워드"
                 autocomplete="current-password" autofocus>
          <button type="submit" class="btn btn-primary w-full" style="margin-top:10px">확인</button>
        </form>
      </div>
    </div>`;

  getSiteTitle().then(t => {
    const el = document.getElementById('auth-site-title');
    if (el) el.textContent = t;
  });

  document.getElementById('auth-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const pw = document.getElementById('auth-pw').value;
    const errEl = document.getElementById('auth-error');
    const btn = e.target.querySelector('button[type="submit"]');
    btn.disabled = true;
    errEl.style.display = 'none';

    try {
      await shareApi.post(`/api/share/${token}/auth`, { password: pw });
      window.navigate(`/s/${token}/view`, true);
    } catch (err) {
      errEl.textContent = err.message || '패스워드가 올바르지 않습니다.';
      errEl.style.display = 'block';
      btn.disabled = false;
    }
  });
}

function _renderError(app, message) {
  const isExpired = /expired|만료/.test(message);
  app.innerHTML = `
    <div class="viewer-center">
      <div class="viewer-auth-card">
        <div class="viewer-icon">${isExpired ? '⏰' : '🔗'}</div>
        <h1 class="viewer-auth-title">${isExpired ? '링크가 만료되었습니다' : '유효하지 않은 링크입니다'}</h1>
        <p class="viewer-auth-desc text-muted">${esc(message)}</p>
      </div>
    </div>`;
}

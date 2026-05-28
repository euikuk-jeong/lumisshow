import { api } from '../api.js';
import { setToken } from '../auth.js';

export async function renderAdminLogin() {
  const app = document.getElementById('app');
  app.innerHTML = `
    <div class="login-page">
      <div class="login-card card">
        <h1>LumisShow</h1>
        <p>관리자 비밀번호를 입력하세요</p>
        <div id="login-error" class="alert alert-error" style="display:none"></div>
        <form id="login-form" class="flex-col gap-3">
          <div class="form-group">
            <label class="form-label" for="password">비밀번호</label>
            <input
              id="password"
              type="password"
              class="form-input"
              placeholder="••••••••"
              autocomplete="current-password"
              required
            >
          </div>
          <button type="submit" class="btn btn-primary w-full" id="login-btn">
            로그인
          </button>
        </form>
      </div>
    </div>
  `;

  const form   = document.getElementById('login-form');
  const errEl  = document.getElementById('login-error');
  const btn    = document.getElementById('login-btn');
  const pwdEl  = document.getElementById('password');

  pwdEl.focus();

  form.addEventListener('submit', async e => {
    e.preventDefault();
    errEl.style.display = 'none';
    btn.disabled = true;
    btn.textContent = '로그인 중...';
    try {
      const { access_token } = await api.post('/api/auth/login', { password: pwdEl.value });
      setToken(access_token);
      window.navigate('/admin');
    } catch (err) {
      errEl.textContent = err.message === '오류 401' ? '비밀번호가 올바르지 않습니다.' : err.message;
      errEl.style.display = 'block';
      btn.disabled = false;
      btn.textContent = '로그인';
      pwdEl.select();
    }
  });
}

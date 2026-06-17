import { clearToken } from './auth.js';
import { getVersion } from './utils.js';

export function renderAdminShell(mainHTML, activePath = '') {
  const app = document.getElementById('app');
  app.innerHTML = `
    <div class="admin-shell">
      <nav class="admin-nav">
        <a href="/admin" class="nav-brand" data-link>
          LumisShow <span class="nav-version" id="nav-version"></span>
        </a>
        <div class="nav-links">
          <a href="/admin" class="${activePath === '/admin' ? 'active' : ''}" data-link>앨범</a>
          <a href="/admin/browse" class="${activePath === '/admin/browse' ? 'active' : ''}" data-link>사진 탐색</a>
          <a href="/admin/settings" class="${activePath === '/admin/settings' ? 'active' : ''}" data-link>설정</a>
          <button class="btn btn-ghost btn-sm" id="btn-logout">로그아웃</button>
        </div>
      </nav>
      <main class="admin-main">
        ${mainHTML}
      </main>
    </div>
  `;
  document.getElementById('btn-logout').addEventListener('click', () => {
    clearToken();
    window.navigate('/admin/login');
  });
  getVersion().then(v => {
    const el = document.getElementById('nav-version');
    if (el) el.textContent = `${v} · Made by Ekjeong`;
  });
}

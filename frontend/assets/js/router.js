import { getToken } from './auth.js';
import { esc } from './utils.js';
import { renderAdminLogin } from './pages/admin-login.js';
import { renderAdminAlbums } from './pages/admin-albums.js';
import { renderAdminAlbumEdit } from './pages/admin-album-edit.js';
import { renderAdminBrowse } from './pages/admin-browse.js';
import { renderAdminSettings } from './pages/admin-settings.js';
import { renderAdminHiddenPaths } from './pages/admin-hidden-paths.js';
import { renderShareAuth } from './pages/share-auth.js';
import { renderAlbumView } from './pages/album-view.js';
import { renderSlideshow } from './pages/slideshow.js';

const ROUTES = [
  { path: '/admin/login',     render: () => renderAdminLogin(),         public: true  },
  { path: '/admin',           render: () => renderAdminAlbums(),        public: false },
  { path: '/admin/',          render: () => renderAdminAlbums(),        public: false },
  { path: '/admin/browse',    render: () => renderAdminBrowse(),        public: false },
  { path: '/admin/settings',      render: () => renderAdminSettings(),      public: false },
  { path: '/admin/hidden-paths',  render: () => renderAdminHiddenPaths(),   public: false },
  { path: '/admin/albums/new',render: () => renderAdminAlbumEdit(null), public: false },
];

const DYNAMIC_ROUTES = [
  { pattern: /^\/admin\/albums\/(\d+)$/,  render: (m) => renderAdminAlbumEdit(m[1]), public: false },
  { pattern: /^\/s\/([^/]+)\/view$/,      render: (m) => renderAlbumView(m[1]),      public: true  },
  { pattern: /^\/s\/([^/]+)\/slideshow$/, render: (m) => renderSlideshow(m[1]), public: true },
  { pattern: /^\/s\/([^/]+)$/,            render: (m) => renderShareAuth(m[1]),      public: true  },
];

let _renderGen = 0;

function navigate(path, replace = false) {
  if (replace) history.replaceState(null, '', path);
  else         history.pushState(null, '', path);
  renderRoute();
}

window.navigate = navigate;

async function renderRoute() {
  window._pageCleanup?.();
  window._pageCleanup = null;

  const gen  = ++_renderGen;
  const path = location.pathname;
  const app  = document.getElementById('app');
  const authed = !!getToken();

  let renderFn = null;
  let isPublic = false;

  for (const r of ROUTES) {
    if (r.path === path) { renderFn = r.render; isPublic = r.public; break; }
  }
  if (!renderFn) {
    for (const dr of DYNAMIC_ROUTES) {
      const m = path.match(dr.pattern);
      if (m) { renderFn = () => dr.render(m); isPublic = dr.public; break; }
    }
  }

  if (!renderFn) {
    navigate(authed ? '/admin' : '/admin/login', true);
    return;
  }
  if (!isPublic && !authed) { navigate('/admin/login', true); return; }
  if (isPublic  &&  authed && path === '/admin/login') { navigate('/admin', true); return; }

  // Admin 페이지로 돌아올 때 개인 테마(localStorage) 복원
  // 뷰어에서 앨범 테마를 적용했더라도 admin UI는 개인 설정을 따름
  if (path.startsWith('/admin')) {
    document.documentElement.dataset.theme =
      localStorage.getItem('lumisshow_theme') || 'dark';
  }

  app.innerHTML = '<div class="loading"></div>';
  try {
    await renderFn();
    // 더 최신 render가 시작됐으면 이 결과를 버린다
    if (gen !== _renderGen) return;
  } catch (e) {
    if (gen !== _renderGen) return;
    app.innerHTML = `<div style="padding:40px;color:var(--error)">오류: ${esc(e.message)}</div>`;
  }
}

document.addEventListener('click', e => {
  const a = e.target.closest('a[data-link]');
  if (a) { e.preventDefault(); navigate(a.getAttribute('href')); }
});

window.addEventListener('popstate', renderRoute);
renderRoute();

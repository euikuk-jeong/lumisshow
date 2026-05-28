import { getToken, clearToken } from './auth.js';

async function request(method, path, body) {
  const token = getToken();
  const headers = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  const res = await fetch(path, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    credentials: 'include',
  });

  if (res.status === 401) {
    clearToken();
    if (location.pathname !== '/admin/login') window.navigate('/admin/login');
    throw new Error('인증이 만료되었습니다.');
  }

  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || `오류 ${res.status}`);
  }

  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  get:    (path)        => request('GET',    path),
  post:   (path, body)  => request('POST',   path, body),
  put:    (path, body)  => request('PUT',    path, body),
  delete: (path, body)  => request('DELETE', path, body),
};

export class ShareAuthError extends Error {
  constructor(msg) { super(msg); this.name = 'ShareAuthError'; }
}

// Share viewer용: admin Bearer 토큰 불첨부, 401 시 ShareAuthError 발생
async function shareRequest(method, path, body) {
  const headers = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';

  const res = await fetch(path, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    credentials: 'include',
  });

  if (res.status === 401) {
    const data = await res.json().catch(() => ({}));
    throw new ShareAuthError(data.detail || '인증이 필요합니다.');
  }

  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || `오류 ${res.status}`);
  }

  if (res.status === 204) return null;
  return res.json();
}

export const shareApi = {
  get:  (path)       => shareRequest('GET',  path),
  post: (path, body) => shareRequest('POST', path, body),
};

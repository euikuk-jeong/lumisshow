import { shareApi, ShareAuthError } from '../api.js';
import { esc, getVersion } from '../utils.js';

const EFFECTS = ['random', 'fade', 'slide-left', 'slide-right', 'slide-up',
                 'zoom-in', 'zoom-out', 'flip-h', 'blur', 'dissolve'];
const EFFECT_LABELS = {
  random: '랜덤', fade: 'Fade', 'slide-left': 'Slide Left',
  'slide-right': 'Slide Right', 'slide-up': 'Slide Up',
  'zoom-in': 'Zoom In', 'zoom-out': 'Zoom Out',
  'flip-h': 'Flip H', blur: 'Blur', dissolve: 'Dissolve',
};
const DEFAULT_SETTINGS = { interval: 5, order: 'sequential', music: true, volume: 25, effect: 'random', loop: true };

function loadSettingsForViewer(albumDefaults = {}, token = '') {
  // 앨범 DB 기본값 + 로컬 사용자 변경 오버라이드 (토큰별 localStorage)
  const base = { ...DEFAULT_SETTINGS, ...albumDefaults };
  try {
    const local = JSON.parse(localStorage.getItem(`slideshow_settings_${token}`) || '{}');
    const s = { ...base, ...local };
    if (!['sequential', 'random'].includes(s.order)) s.order = base.order;
    if (!EFFECTS.includes(s.effect)) s.effect = base.effect;
    return s;
  } catch { return { ...base }; }
}

function saveSettings(token, s) {
  localStorage.setItem(`slideshow_settings_${token}`, JSON.stringify(s));
}

function formatDateInTZ(isoString, offsetMinutes) {
  const utcMs = new Date(isoString).getTime();
  const tzDate = new Date(utcMs + offsetMinutes * 60 * 1000);
  const y = tzDate.getUTCFullYear();
  const m = tzDate.getUTCMonth() + 1;
  const d = tzDate.getUTCDate();
  return `${y}. ${m}. ${d}.`;
}

export async function renderAlbumView(token) {
  const app = document.getElementById('app');
  app.innerHTML = '<div class="loading"></div>';

  let album, photosData;
  try {
    [album, photosData] = await Promise.all([
      shareApi.get(`/api/share/${token}/album`),
      shareApi.get(`/api/share/${token}/photos`),
    ]);
  } catch (e) {
    if (e instanceof ShareAuthError) {
      window.navigate(`/s/${token}`, true);
      return;
    }
    app.innerHTML = `<div style="padding:40px;color:var(--error)">${esc(e.message)}</div>`;
    return;
  }

  const photos = photosData.photos;
  const coverPhoto = album.cover_index != null ? photos[album.cover_index] : photos[0];
  const coverUrl = coverPhoto ? coverPhoto.thumb_medium_url : null;

  const tzOffset = album.timezone_offset ?? 0;
  const expiryHtml = album.expires_at
    ? `<span>⏰ 만료: ${formatDateInTZ(album.expires_at, tzOffset)}</span>`
    : '';

  app.innerHTML = `
    <div class="viewer-page">
      ${coverUrl ? `<div class="viewer-cover"><img src="${coverUrl}" alt="커버"></div>` : ''}
      <div class="viewer-body">
        <h1 class="viewer-title">${esc(album.album_name)}</h1>
        ${album.description ? `<p class="viewer-desc text-muted">${esc(album.description)}</p>` : ''}
        <div class="viewer-meta">
          <span>📷 ${album.photo_count}장</span>
          <span>📅 ${new Date(album.created_at).toLocaleDateString('ko-KR')}</span>
          ${expiryHtml}
          ${album.has_music ? '<span>🎵 음악 있음</span>' : ''}
        </div>
        <div class="viewer-actions">
          <button class="btn btn-primary btn-lg" id="btn-slideshow">▶ 슬라이드쇼</button>
          <button class="btn btn-ghost btn-lg" id="btn-settings">⚙ 설정</button>
        </div>
        <a class="btn btn-ghost w-full viewer-download"
           href="/api/share/${token}/download">⬇ 전체 다운로드 (ZIP)</a>
        ${photos.length > 0 ? `
          <div class="viewer-grid" id="thumb-grid">
            ${photos.map((p, i) => `
              <div class="viewer-thumb" data-idx="${i}">
                <img src="${p.thumb_small_url}" alt="" loading="lazy">
              </div>`).join('')}
          </div>` : ''}
        <div class="viewer-version" id="viewer-version"></div>
      </div>
    </div>
    <div class="settings-overlay" id="settings-overlay" style="display:none">
      <div class="settings-panel">
        <h2 class="settings-title">슬라이드쇼 설정</h2>
        <div class="form-group">
          <label class="form-label">전환 시간 (초)</label>
          <input type="number" id="s-interval" min="2" max="60" class="form-input" style="width:100px">
        </div>
        <div class="form-group">
          <label class="form-label">순서</label>
          <div class="settings-radios">
            <label><input type="radio" name="s-order" value="sequential"> 순서대로</label>
            <label><input type="radio" name="s-order" value="random"> 랜덤</label>
          </div>
        </div>
        <div class="form-group">
          <label class="form-label">배경음악</label>
          <div class="settings-radios">
            <label><input type="radio" name="s-music" value="on"> ON</label>
            <label><input type="radio" name="s-music" value="off"> OFF</label>
          </div>
        </div>
        <div class="form-group">
          <label class="form-label">반복 재생</label>
          <div class="settings-radios">
            <label><input type="radio" name="s-loop" value="on"> 켜기</label>
            <label><input type="radio" name="s-loop" value="off"> 끄기</label>
          </div>
        </div>
        <div class="form-group" id="s-volume-group">
          <label class="form-label">음량 <span id="s-volume-label">25%</span></label>
          <input type="range" id="s-volume" min="0" max="100" class="w-full">
        </div>
        <div class="form-group">
          <label class="form-label">전환 효과</label>
          <select id="s-effect" class="form-select">
            ${EFFECTS.map(e => `<option value="${e}">${EFFECT_LABELS[e]}</option>`).join('')}
          </select>
        </div>
        <div class="settings-actions">
          <button class="btn btn-ghost" id="btn-cancel">취소</button>
          <button class="btn btn-primary" id="btn-start">▶ 시작</button>
        </div>
      </div>
    </div>`;

  _initSettingsPanel(token, album);
  getVersion().then(v => {
    const el = document.getElementById('viewer-version');
    if (el) el.textContent = `LumisShow ${v} · Made by Ekjeong`;
  });

  document.getElementById('btn-slideshow').addEventListener('click', () => {
    window.navigate(`/s/${token}/slideshow`);
  });
  document.getElementById('btn-settings').addEventListener('click', () => {
    document.getElementById('settings-overlay').style.display = 'flex';
  });

  document.getElementById('thumb-grid')?.addEventListener('click', (e) => {
    const thumb = e.target.closest('.viewer-thumb');
    if (thumb) window.navigate(`/s/${token}/slideshow?i=${thumb.dataset.idx}`);
  });
}

function _initSettingsPanel(token, album) {
  const s = loadSettingsForViewer(album.slideshow_defaults || {}, token);

  document.getElementById('s-interval').value = s.interval;
  document.querySelector(`input[name="s-order"][value="${s.order}"]`).checked = true;
  document.querySelector(`input[name="s-music"][value="${s.music ? 'on' : 'off'}"]`).checked = true;
  document.querySelector(`input[name="s-loop"][value="${s.loop ? 'on' : 'off'}"]`).checked = true;
  document.getElementById('s-volume').value = s.volume;
  document.getElementById('s-volume-label').textContent = `${s.volume}%`;
  document.getElementById('s-effect').value = s.effect;

  document.getElementById('s-volume').addEventListener('input', (e) => {
    document.getElementById('s-volume-label').textContent = `${e.target.value}%`;
  });

  document.getElementById('btn-cancel').addEventListener('click', () => {
    document.getElementById('settings-overlay').style.display = 'none';
  });

  document.getElementById('btn-start').addEventListener('click', () => {
    saveSettings(token, {
      interval: parseInt(document.getElementById('s-interval').value, 10) || 5,
      order: document.querySelector('input[name="s-order"]:checked').value,
      music: document.querySelector('input[name="s-music"]:checked').value === 'on',
      loop: document.querySelector('input[name="s-loop"]:checked').value === 'on',
      volume: parseInt(document.getElementById('s-volume').value, 10),
      effect: document.getElementById('s-effect').value,
    });
    document.getElementById('settings-overlay').style.display = 'none';
    window.navigate(`/s/${token}/slideshow`);
  });

  document.getElementById('settings-overlay').addEventListener('click', (e) => {
    if (e.target === e.currentTarget) e.currentTarget.style.display = 'none';
  });
}

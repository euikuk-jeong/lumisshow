import { api } from '../api.js';
import { renderAdminShell } from '../layout.js';
import { esc } from '../utils.js';

const EFFECTS = ['fade','slide-left','slide-right','slide-up','zoom-in','zoom-out','flip-h','blur','dissolve'];

const TIMEZONES = [
  // UTC+12 ~ UTC+14
  { offset:  840, label: 'LINT (라인 제도 표준시): UTC+14' },
  { offset:  780, label: 'TOT (통가 표준시): UTC+13 (누쿠알로파)' },
  { offset:  720, label: 'NZST (뉴질랜드 표준시): UTC+12 (오클랜드, 웰링턴)' },
  // UTC+9 ~ UTC+11
  { offset:  660, label: 'SBT (솔로몬 제도 표준시): UTC+11 (호니아라)' },
  { offset:  600, label: 'AEST (호주 동부 표준시): UTC+10 (시드니, 멜버른)' },
  { offset:  570, label: 'ACST (호주 중부 표준시): UTC+9:30 (애들레이드)' },
  { offset:  540, label: 'KST (한국 표준시): UTC+9 (서울)' },
  { offset:  540, label: 'JST (일본 표준시): UTC+9 (도쿄)' },
  // UTC+8
  { offset:  480, label: 'CST (중국 표준시): UTC+8 (베이징, 상하이)' },
  { offset:  480, label: 'AWST (서호주 표준시): UTC+8 (퍼스)' },
  { offset:  480, label: 'HKT (홍콩 표준시): UTC+8 (홍콩)' },
  { offset:  480, label: 'SGT (싱가포르 표준시): UTC+8 (싱가포르)' },
  { offset:  480, label: 'MYT (말레이시아 표준시): UTC+8 (쿠알라룸푸르)' },
  { offset:  480, label: 'PHT (필리핀 표준시): UTC+8 (마닐라)' },
  // UTC+7
  { offset:  420, label: 'ICT (인도차이나 표준시): UTC+7 (방콕, 하노이)' },
  { offset:  420, label: 'WIB (서인도네시아 표준시): UTC+7 (자카르타)' },
  // UTC+5:30 ~ UTC+6
  { offset:  360, label: 'BST (방글라데시 표준시): UTC+6 (다카)' },
  { offset:  330, label: 'IST (인도 표준시): UTC+5:30 (뭄바이, 델리, 콜카타)' },
  { offset:  300, label: 'PKT (파키스탄 표준시): UTC+5 (카라치, 이슬라마바드)' },
  // UTC+3 ~ UTC+4:30
  { offset:  270, label: 'AFT (아프가니스탄 표준시): UTC+4:30 (카불)' },
  { offset:  240, label: 'GST (걸프 표준시): UTC+4 (두바이, 아부다비)' },
  { offset:  210, label: 'IRST (이란 표준시): UTC+3:30 (테헤란)' },
  { offset:  180, label: 'MSK (모스크바 표준시): UTC+3 (모스크바)' },
  { offset:  180, label: 'AST (아라비아 표준시): UTC+3 (리야드, 쿠웨이트)' },
  { offset:  180, label: 'EAT (동아프리카 표준시): UTC+3 (나이로비, 아디스아바바)' },
  // UTC+1 ~ UTC+2
  { offset:  120, label: 'EET (동유럽 표준시): UTC+2 (아테네, 헬싱키, 카이로)' },
  { offset:  120, label: 'CAT (중앙아프리카 표준시): UTC+2 (요하네스버그, 하라레)' },
  { offset:   60, label: 'CET (중부유럽 표준시): UTC+1 (파리, 베를린, 로마, 마드리드)' },
  { offset:   60, label: 'WAT (서아프리카 표준시): UTC+1 (라고스)' },
  // UTC+0
  { offset:    0, label: 'UTC (협정 세계시): UTC+0' },
  { offset:    0, label: 'GMT (그리니치 평균시): UTC+0 (런던, 더블린)' },
  { offset:    0, label: 'WET (서유럽 표준시): UTC+0 (리스본)' },
  // UTC-1 ~ UTC-3:30
  { offset:  -60, label: 'CVT (카보베르데 표준시): UTC-1' },
  { offset: -150, label: 'NST (뉴펀들랜드 표준시): UTC-3:30 (세인트존스)' },
  { offset: -180, label: 'BRT (브라질리아 표준시): UTC-3 (상파울루)' },
  { offset: -180, label: 'ART (아르헨티나 표준시): UTC-3 (부에노스아이레스)' },
  { offset: -180, label: 'UYT (우루과이 표준시): UTC-3 (몬테비데오)' },
  // UTC-4 ~ UTC-5
  { offset: -240, label: 'AST (대서양 표준시): UTC-4 (핼리팩스, 산후안)' },
  { offset: -240, label: 'VET (베네수엘라 표준시): UTC-4 (카라카스)' },
  { offset: -300, label: 'EST (미국 동부 표준시): UTC-5 (뉴욕, 마이애미, 워싱턴)' },
  { offset: -300, label: 'COT (콜롬비아 표준시): UTC-5 (보고타)' },
  { offset: -300, label: 'PET (페루 표준시): UTC-5 (리마)' },
  // UTC-6 ~ UTC-7
  { offset: -360, label: 'CST (미국 중부 표준시): UTC-6 (시카고, 달라스, 휴스턴)' },
  { offset: -360, label: 'MEX (멕시코 중부 표준시): UTC-6 (멕시코시티)' },
  { offset: -420, label: 'MST (미국 산악 표준시): UTC-7 (덴버, 피닉스, 솔트레이크)' },
  // UTC-8 ~ UTC-10
  { offset: -480, label: 'PST (미국 태평양 표준시): UTC-8 (로스앤젤레스, 시애틀, 밴쿠버)' },
  { offset: -540, label: 'AKST (알래스카 표준시): UTC-9 (앵커리지)' },
  { offset: -600, label: 'HAST (하와이 표준시): UTC-10 (호놀룰루)' },
  { offset: -660, label: 'SST (사모아 표준시): UTC-11 (팡오팡오)' },
  { offset: -720, label: 'BIT (베이커 섬 표준시): UTC-12' },
];

export async function renderAdminSettings() {
  renderAdminShell(`
    <div class="page-header">
      <h1 class="page-title">설정</h1>
    </div>
    <div id="settings-content"><div class="loading"></div></div>
  `, '/admin/settings');

  try {
    const settings = await api.get('/api/admin/settings');
    renderSettingsForm(settings);
  } catch (e) {
    document.getElementById('settings-content').innerHTML =
      `<div class="alert alert-error">${esc(e.message)}</div>`;
  }
}

function normalizePath(p) {
  return p.trim().replace(/\\/g, '/').replace(/^\/+|\/+$/g, '');
}

function renderSettingsForm(settings) {
  const el = document.getElementById('settings-content');
  el.innerHTML = `
    <div class="settings-page">

      <!-- 서버 타임존 -->
      <div class="settings-section card">
        <div class="settings-section-header">
          <p class="section-title">서버 타임존</p>
          <p class="text-muted text-sm">공유 링크 만료일의 기준 타임존</p>
        </div>
        <div class="settings-group">
          <div class="settings-item">
            <label class="settings-label">타임존</label>
            <div class="tz-select" id="tz-select-container">
              <input type="text" id="s-timezone-input" class="form-input settings-select"
                placeholder="타임존 검색..." autocomplete="off">
              <div class="tz-dropdown" id="tz-dropdown"></div>
            </div>
            <input type="hidden" id="s-timezone-offset" value="${settings.timezone_offset}">
            <input type="hidden" id="s-timezone-label" value="${esc(settings.timezone_label)}">
          </div>
        </div>
        <div class="settings-actions">
          <button class="btn btn-primary btn-sm" id="btn-save-timezone">저장</button>
          <span id="tz-ok" class="text-success text-sm" style="display:none">저장됨 ✓</span>
        </div>
      </div>

      <!-- 탐색기 숨김 경로 -->
      <div class="settings-section card">
        <div class="settings-section-header">
          <p class="section-title">탐색기 숨김 경로</p>
          <p class="text-muted text-sm">사진 탐색 화면에서 표시하지 않을 폴더 (PHOTO_ROOT 기준 상대 경로)</p>
        </div>
        <div class="settings-group">
          <div id="hidden-paths-list" class="hidden-paths-list"></div>
          <div class="hidden-path-add-row">
            <input id="s-hidden-path-input" type="text" class="form-input" placeholder="예: private/family">
            <button class="btn btn-ghost btn-sm" id="btn-add-hidden-path">추가</button>
          </div>
        </div>
        <div class="settings-actions">
          <button class="btn btn-primary btn-sm" id="btn-save-hidden-paths">저장</button>
          <span id="hp-ok" class="text-success text-sm" style="display:none">저장됨 ✓</span>
        </div>
      </div>

      <!-- 슬라이드쇼 기본값 -->
      <div class="settings-section card">
        <div class="settings-section-header">
          <p class="section-title">슬라이드쇼 기본값</p>
          <p class="text-muted text-sm">공유 링크 뷰어의 슬라이드쇼 초기 설정</p>
        </div>
        <div class="settings-group">
          <div class="settings-item">
            <label class="settings-label">전환 간격</label>
            <div class="settings-input-row">
              <input id="s-ss-interval" type="number" min="1" max="60" class="form-input settings-num" value="${settings.slideshow_interval}">
              <span class="text-muted text-sm">초</span>
            </div>
          </div>
          <div class="settings-item">
            <label class="settings-label">재생 순서</label>
            <select id="s-ss-order" class="form-input settings-select">
              <option value="sequential"${settings.slideshow_order === 'sequential' ? ' selected' : ''}>순서대로</option>
              <option value="random"${settings.slideshow_order === 'random' ? ' selected' : ''}>랜덤</option>
            </select>
          </div>
          <div class="settings-item">
            <label class="settings-label">전환 효과</label>
            <select id="s-ss-effect" class="form-input settings-select">
              <option value="random"${settings.slideshow_effect === 'random' ? ' selected' : ''}>랜덤</option>
              ${EFFECTS.map(e => `<option value="${e}"${settings.slideshow_effect === e ? ' selected' : ''}>${e}</option>`).join('')}
            </select>
          </div>
          <div class="settings-item">
            <label class="settings-label">배경음악 기본값</label>
            <select id="s-ss-music" class="form-input settings-select">
              <option value="true"${settings.slideshow_music ? ' selected' : ''}>켬</option>
              <option value="false"${!settings.slideshow_music ? ' selected' : ''}>끔</option>
            </select>
          </div>
          <div class="settings-item">
            <label class="settings-label">초기 볼륨</label>
            <div class="settings-input-row">
              <input id="s-ss-volume" type="number" min="0" max="100" class="form-input settings-num" value="${settings.slideshow_volume}">
              <span class="text-muted text-sm">%</span>
            </div>
          </div>
          <div class="settings-item">
            <label class="settings-label">반복 재생</label>
            <select id="s-ss-loop" class="form-input settings-select">
              <option value="true"${settings.slideshow_loop ? ' selected' : ''}>켬</option>
              <option value="false"${!settings.slideshow_loop ? ' selected' : ''}>끔</option>
            </select>
          </div>
        </div>
        <div class="settings-actions">
          <button class="btn btn-primary btn-sm" id="btn-save-slideshow">저장</button>
          <span id="ss-ok" class="text-success text-sm" style="display:none">저장됨 ✓</span>
        </div>
      </div>

    </div>
  `;

  initTimezoneSelect(settings.timezone_label);
  initHiddenPaths(settings.browse_hidden_paths || []);
  bindSaveHandlers();
}

/* ── Hidden paths ───────────────────────────────────────── */
let _hiddenPaths = [];

function initHiddenPaths(paths) {
  _hiddenPaths = [...paths];
  renderHiddenPathsList();
}

function renderHiddenPathsList() {
  const el = document.getElementById('hidden-paths-list');
  if (!_hiddenPaths.length) {
    el.innerHTML = '<p class="text-muted text-sm" style="margin:4px 0">숨김 경로 없음</p>';
    return;
  }
  el.innerHTML = _hiddenPaths.map((p, i) =>
    `<div class="hidden-path-item">
      <span class="hidden-path-value">${esc(p)}</span>
      <button class="btn btn-ghost btn-sm btn-icon hidden-path-delete" data-index="${i}" title="삭제">✕</button>
    </div>`
  ).join('');
  el.querySelectorAll('.hidden-path-delete').forEach(btn => {
    btn.addEventListener('click', () => {
      _hiddenPaths.splice(parseInt(btn.dataset.index, 10), 1);
      renderHiddenPathsList();
    });
  });
}

/* ── Timezone searchable select ─────────────────────────── */
function initTimezoneSelect(currentLabel) {
  const input    = document.getElementById('s-timezone-input');
  const dropdown = document.getElementById('tz-dropdown');
  const hidOff   = document.getElementById('s-timezone-offset');
  const hidLbl   = document.getElementById('s-timezone-label');

  input.value = currentLabel;

  function renderOptions(zones) {
    if (!zones.length) {
      dropdown.innerHTML = '<div class="tz-no-result">검색 결과 없음</div>';
      return;
    }
    dropdown.innerHTML = zones.map(z =>
      `<div class="tz-option${z.label === input.value ? ' selected' : ''}" data-offset="${z.offset}" data-label="${esc(z.label)}">${esc(z.label)}</div>`
    ).join('');
    dropdown.querySelectorAll('.tz-option').forEach(opt => {
      opt.addEventListener('mousedown', e => {
        e.preventDefault();
        input.value    = opt.dataset.label;
        hidOff.value   = opt.dataset.offset;
        hidLbl.value   = opt.dataset.label;
        dropdown.classList.remove('open');
      });
    });
  }

  input.addEventListener('focus', () => {
    renderOptions(TIMEZONES);
    dropdown.classList.add('open');
  });

  input.addEventListener('input', () => {
    const q = input.value.trim().toLowerCase();
    const filtered = q
      ? TIMEZONES.filter(z => z.label.toLowerCase().includes(q))
      : TIMEZONES;
    renderOptions(filtered);
    dropdown.classList.add('open');
  });

  input.addEventListener('blur', () => {
    setTimeout(() => {
      dropdown.classList.remove('open');
      // 입력값이 목록에 없으면 이전 선택값으로 복원
      const match = TIMEZONES.find(z => z.label === input.value);
      if (!match) {
        input.value = hidLbl.value;
      }
    }, 150);
  });
}

/* ── Save handlers ──────────────────────────────────────── */
function bindSaveHandlers() {
  document.getElementById('btn-add-hidden-path').addEventListener('click', () => {
    const input = document.getElementById('s-hidden-path-input');
    const val = normalizePath(input.value);
    if (!val) return;
    if (!_hiddenPaths.includes(val)) {
      _hiddenPaths.push(val);
      renderHiddenPathsList();
    }
    input.value = '';
  });

  document.getElementById('s-hidden-path-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') document.getElementById('btn-add-hidden-path').click();
  });

  document.getElementById('btn-save-hidden-paths').addEventListener('click', async () => {
    const btn = document.getElementById('btn-save-hidden-paths');
    btn.disabled = true;
    try {
      await api.patch('/api/admin/settings', { browse_hidden_paths: _hiddenPaths });
      showOk('hp-ok');
    } catch (e) {
      alert(e.message);
    } finally {
      btn.disabled = false;
    }
  });

  document.getElementById('btn-save-timezone').addEventListener('click', async () => {
    const btn = document.getElementById('btn-save-timezone');
    btn.disabled = true;
    try {
      await api.patch('/api/admin/settings', {
        timezone_offset: parseInt(document.getElementById('s-timezone-offset').value, 10),
        timezone_label:  document.getElementById('s-timezone-label').value,
      });
      showOk('tz-ok');
    } catch (e) {
      alert(e.message);
    } finally {
      btn.disabled = false;
    }
  });

  document.getElementById('btn-save-slideshow').addEventListener('click', async () => {
    const btn = document.getElementById('btn-save-slideshow');
    btn.disabled = true;
    try {
      await api.patch('/api/admin/settings', {
        slideshow_interval: parseInt(document.getElementById('s-ss-interval').value, 10),
        slideshow_order:    document.getElementById('s-ss-order').value,
        slideshow_effect:   document.getElementById('s-ss-effect').value,
        slideshow_music:    document.getElementById('s-ss-music').value === 'true',
        slideshow_volume:   parseInt(document.getElementById('s-ss-volume').value, 10),
        slideshow_loop:     document.getElementById('s-ss-loop').value === 'true',
      });
      showOk('ss-ok');
    } catch (e) {
      alert(e.message);
    } finally {
      btn.disabled = false;
    }
  });
}

function showOk(id) {
  const el = document.getElementById(id);
  el.style.display = 'inline';
  setTimeout(() => { el.style.display = 'none'; }, 2000);
}

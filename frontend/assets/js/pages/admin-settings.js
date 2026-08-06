import { api } from '../api.js';
import { renderAdminShell } from '../layout.js';
import { esc, invalidateSiteInfo } from '../utils.js';
import { THEMES, getTheme, setTheme } from '../theme.js';
import { EFFECTS } from '../slideshow-config.js';

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

function renderSettingsForm(settings) {
  const hiddenCount = (settings.browse_hidden_paths || []).length;
  const el = document.getElementById('settings-content');
  el.innerHTML = `
    <div class="settings-page">

      <!-- 타이틀 -->
      <div class="settings-section card">
        <div class="settings-section-header">
          <p class="section-title">타이틀</p>
          <p class="text-muted text-sm">로그인 화면·상단바·공유 앨범 등에 표시되는 서비스 이름</p>
        </div>
        <div class="settings-group">
          <div class="settings-item">
            <label class="settings-label">타이틀</label>
            <div class="settings-input-row" id="site-title-view">
              <span id="site-title-text">${esc(settings.site_title)}</span>
              <button type="button" class="btn btn-ghost btn-sm" id="btn-edit-title">편집</button>
              <span id="site-title-ok" class="text-success text-sm" style="display:none">저장됨 ✓</span>
            </div>
            <div class="settings-input-row" id="site-title-edit" style="display:none">
              <input id="s-site-title" type="text" class="form-input settings-select" maxlength="60" value="${esc(settings.site_title)}">
              <button type="button" class="btn btn-primary btn-sm" id="btn-save-title">저장</button>
              <button type="button" class="btn btn-ghost btn-sm" id="btn-cancel-title">취소</button>
            </div>
          </div>
        </div>
      </div>

      <!-- 테마 -->
      <div class="settings-section card">
        <div class="settings-section-header">
          <p class="section-title">테마</p>
          <p class="text-muted text-sm">Admin UI 테마 · 신규 앨범의 기본 테마로도 사용됨 · 변경 즉시 적용</p>
        </div>
        <div class="theme-picker" id="theme-picker"></div>
      </div>

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
        <div class="settings-nav-row">
          <div>
            <p class="section-title">탐색기 숨김 경로 <span class="badge-count">${hiddenCount}</span></p>
            <p class="text-muted text-sm">사진 탐색 화면에서 표시하지 않을 폴더</p>
          </div>
          <a href="/admin/hidden-paths" class="btn btn-ghost btn-sm" data-link>관리 →</a>
        </div>
      </div>

      <!-- AI 인식 카테고리 on/off -->
      <div class="settings-section card" id="ai-category-section" style="display:none">
        <div class="settings-section-header">
          <p class="section-title">AI 인식 카테고리</p>
          <p class="text-muted text-sm">끄면 다음 스캔부터 해당 카테고리를 새로 생성하지 않음(기존 데이터는 삭제되지 않고 그대로 조회 가능) · 위치·사물은 다시 켠 뒤 "태그 관리" 화면의 AI 태그 재계산으로 밀린 부분을 소급 반영할 수 있음 · 얼굴 인식은 재계산 기능이 없어 꺼져 있는 동안 스캔된 사진은 다시 켜도 자동으로 소급 인식되지 않음(해당 사진이 재스캔 대상이 될 때만 인식됨)</p>
        </div>
        <div class="settings-group">
          <div class="settings-item">
            <label class="settings-label">얼굴 인식</label>
            <div class="settings-input-row">
              <select id="s-ai-face-enabled" class="form-input settings-select">
                <option value="true">켬</option>
                <option value="false">끔</option>
              </select>
              <button type="button" class="btn btn-danger btn-sm" id="btn-purge-face" disabled>DB 삭제</button>
            </div>
          </div>
          <div class="settings-item">
            <label class="settings-label">장소(위치) 인식</label>
            <div class="settings-input-row">
              <select id="s-ai-location-enabled" class="form-input settings-select">
                <option value="true">켬</option>
                <option value="false">끔</option>
              </select>
              <button type="button" class="btn btn-danger btn-sm" id="btn-purge-location" disabled>DB 삭제</button>
            </div>
          </div>
          <div class="settings-item">
            <label class="settings-label">폴더명 태깅</label>
            <div class="settings-input-row">
              <select id="s-ai-path-enabled" class="form-input settings-select">
                <option value="true">켬</option>
                <option value="false">끔</option>
              </select>
              <button type="button" class="btn btn-danger btn-sm" id="btn-purge-path" disabled>DB 삭제</button>
            </div>
          </div>
          <div class="settings-item">
            <label class="settings-label">사물 인식(AI 태그)</label>
            <div class="settings-input-row">
              <select id="s-ai-tag-enabled" class="form-input settings-select">
                <option value="true">켬</option>
                <option value="false">끔</option>
              </select>
              <button type="button" class="btn btn-danger btn-sm" id="btn-purge-ai_tag" disabled>DB 삭제</button>
            </div>
          </div>
        </div>
        <p class="text-muted text-sm">DB 삭제 버튼은 해당 카테고리가 "끔" 상태로 저장되어 있을 때만 활성화됩니다.</p>
        <div class="settings-actions">
          <button class="btn btn-primary btn-sm" id="btn-save-ai-category">저장</button>
          <span id="ai-category-ok" class="text-success text-sm" style="display:none">저장됨 ✓</span>
        </div>
      </div>

      <!-- AI 야간 스캔 -->
      <div class="settings-section card" id="ai-scan-section" style="display:none">
        <div class="settings-section-header">
          <p class="section-title">AI 야간 스캔</p>
          <p class="text-muted text-sm">얼굴 인식 워커의 자동 증분 스캔 시각 · 변경은 워커 폴링 주기(기본 30초) 내 반영</p>
        </div>
        <div class="settings-group">
          <div class="settings-item">
            <label class="settings-label">스캔 시각</label>
            <select id="s-ai-scan-hour" class="form-input settings-select">
              <option value="">미설정 (환경변수 AI_SCAN_HOUR, 기본 02시)</option>
              ${Array.from({ length: 24 }, (_, h) =>
                `<option value="${h}">${String(h).padStart(2, '0')}:00</option>`).join('')}
            </select>
          </div>
        </div>
        <div class="settings-actions">
          <button class="btn btn-primary btn-sm" id="btn-save-ai-scan">저장</button>
          <span id="ai-scan-ok" class="text-success text-sm" style="display:none">저장됨 ✓</span>
        </div>
      </div>

      <!-- AI 태그 인식 -->
      <div class="settings-section card" id="ai-tag-section" style="display:none">
        <div class="settings-section-header">
          <p class="section-title">AI 태그 인식</p>
          <p class="text-muted text-sm">CLIP 태그 부여 임계값(0~1, 낮을수록 태그가 더 많이 붙음) · 미설정 시 환경변수 AI_TAG_THRESHOLD(기본 0.24) 사용 · 변경은 다음 스캔부터 반영, 이미 분석된 사진에 소급 적용하려면 태그 관리 화면에서 재계산 실행 필요</p>
        </div>
        <div class="settings-group">
          <div class="settings-item">
            <label class="settings-label">인식 민감도</label>
            <div class="settings-input-row">
              <input id="s-ai-tag-threshold" type="number" min="0" max="1" step="0.01"
                     class="form-input settings-num" placeholder="0.24">
            </div>
          </div>
        </div>
        <div class="settings-actions">
          <button class="btn btn-primary btn-sm" id="btn-save-tag-threshold">저장</button>
          <span id="tag-threshold-ok" class="text-success text-sm" style="display:none">저장됨 ✓</span>
        </div>
      </div>

      <!-- XMP 내보내기 -->
      <div class="settings-section card" id="xmp-export-section" style="display:none">
        <div class="settings-section-header">
          <p class="section-title">XMP 메타데이터 내보내기</p>
          <p class="text-muted text-sm">태그·인물·위치 정보를 사진별 .xmp 사이드카로 묶어 ZIP 다운로드 (원본과 동일한 폴더 구조 유지, 원본 사진은 수정하지 않음)</p>
        </div>
        <div class="settings-actions">
          <a href="/api/admin/tags/xmp-export" class="btn btn-ghost btn-sm" download>⬇ XMP 전체 내보내기</a>
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

  if (settings.ui_theme) setTheme(settings.ui_theme);
  initThemePicker();
  initTimezoneSelect(settings.timezone_label);
  initSiteTitle(settings);
  bindSaveHandlers();
  initAiScanSection();
}

/* ── 타이틀 (편집 토글) ─────────────────────────────────── */
function initSiteTitle(settings) {
  const viewRow  = document.getElementById('site-title-view');
  const editRow  = document.getElementById('site-title-edit');
  const textEl   = document.getElementById('site-title-text');
  const input    = document.getElementById('s-site-title');

  document.getElementById('btn-edit-title').addEventListener('click', () => {
    input.value = settings.site_title;
    viewRow.style.display = 'none';
    editRow.style.display = '';
    input.focus();
  });

  document.getElementById('btn-cancel-title').addEventListener('click', () => {
    editRow.style.display = 'none';
    viewRow.style.display = '';
  });

  document.getElementById('btn-save-title').addEventListener('click', async () => {
    const value = input.value.trim();
    if (!value) { alert('타이틀을 입력하세요'); return; }
    const btn = document.getElementById('btn-save-title');
    btn.disabled = true;
    try {
      await api.patch('/api/admin/settings', { site_title: value });
      settings.site_title = value;
      textEl.textContent = value;
      invalidateSiteInfo();
      const navTitleEl = document.getElementById('nav-title');
      if (navTitleEl) navTitleEl.textContent = value;
      document.title = value;
      editRow.style.display = 'none';
      viewRow.style.display = '';
      showOk('site-title-ok');
    } catch (e) {
      alert(e.message);
    } finally {
      btn.disabled = false;
    }
  });
}

/* ── AI 야간 스캔 시각 (+ AI 인식 카테고리·AI 태그 인식·XMP 내보내기 섹션도
   같은 ai.db 가용성 조건으로 노출) ── */
async function initAiScanSection() {
  const categorySection = document.getElementById('ai-category-section');
  const section = document.getElementById('ai-scan-section');
  const tagSection = document.getElementById('ai-tag-section');
  const xmpSection = document.getElementById('xmp-export-section');
  let current;
  try {
    current = await api.get('/api/admin/ai/settings');
  } catch {
    return; // ai.db 미구성 등 — 네 섹션 모두 숨김 유지
  }
  const select = document.getElementById('s-ai-scan-hour');
  if (current.scan_hour != null) select.value = String(current.scan_hour);
  const thresholdInput = document.getElementById('s-ai-tag-threshold');
  if (current.tag_threshold != null) thresholdInput.value = String(current.tag_threshold);

  const CATEGORY_FIELDS = [
    ['s-ai-face-enabled', 'face_enabled', 'face'],
    ['s-ai-location-enabled', 'location_enabled', 'location'],
    ['s-ai-path-enabled', 'path_enabled', 'path'],
    ['s-ai-tag-enabled', 'ai_tag_enabled', 'ai_tag'],
  ];
  for (const [id, key] of CATEGORY_FIELDS) {
    document.getElementById(id).value = String(current[key] !== false);
  }
  const resyncPurgeButtons = bindPurgeButtons(CATEGORY_FIELDS, current);

  categorySection.style.display = '';
  section.style.display = '';
  tagSection.style.display = '';
  xmpSection.style.display = '';

  document.getElementById('btn-save-ai-category').addEventListener('click', async () => {
    const btn = document.getElementById('btn-save-ai-category');
    btn.disabled = true;
    try {
      const body = {};
      for (const [id, key] of CATEGORY_FIELDS) {
        body[key] = document.getElementById(id).value === 'true';
      }
      await api.patch('/api/admin/ai/settings', body);
      Object.assign(current, body);
      resyncPurgeButtons();
      showOk('ai-category-ok');
    } catch (e) {
      alert(e.message);
    } finally {
      btn.disabled = false;
    }
  });

  document.getElementById('btn-save-ai-scan').addEventListener('click', async () => {
    const btn = document.getElementById('btn-save-ai-scan');
    if (select.value === '') { alert('스캔 시각을 선택하세요'); return; }
    btn.disabled = true;
    try {
      await api.patch('/api/admin/ai/settings', { scan_hour: parseInt(select.value, 10) });
      showOk('ai-scan-ok');
    } catch (e) {
      alert(e.message);
    } finally {
      btn.disabled = false;
    }
  });

  document.getElementById('btn-save-tag-threshold').addEventListener('click', async () => {
    const btn = document.getElementById('btn-save-tag-threshold');
    const value = parseFloat(thresholdInput.value);
    if (Number.isNaN(value) || value < 0 || value > 1) { alert('0~1 사이 값을 입력하세요'); return; }
    btn.disabled = true;
    try {
      await api.patch('/api/admin/ai/settings', { tag_threshold: value });
      showOk('tag-threshold-ok');
    } catch (e) {
      alert(e.message);
    } finally {
      btn.disabled = false;
    }
  });
}

const PURGE_LABELS = {
  face: '얼굴 인식',
  location: '장소(위치) 인식',
  path: '폴더명 태깅',
  ai_tag: '사물 인식(AI 태그)',
};

// 얼굴은 위치/사물/폴더명과 달리 재활성화 후 자동 소급 인식이 없어(ai-category-section
// 안내문구 참고) 별도 경고를 덧붙인다.
const PURGE_EXTRA_WARNING = {
  face: '\n\n⚠ 삭제 후 얼굴 인식을 다시 켜도 기존 사진은 자동으로 재인식되지 않습니다(해당 사진이 재스캔 대상이 될 때만 인식됩니다).',
};

// 활성화 조건은 select의 즉석 값이 아니라 "저장된" current[key] 기준 —
// 저장 전에 드롭다운만 '끔'으로 바꿔도 버튼이 눌리지 않게 해 저장 안 한 상태에서
// 클릭했을 때 서버 409("먼저 꺼주세요")가 나는 혼란을 막는다. 저장 성공 시
// current를 갱신한 뒤 이 함수를 다시 불러 동기화한다(호출자가 resync 함수를 보관).
function bindPurgeButtons(categoryFields, current) {
  const resync = () => {
    for (const [, key, category] of categoryFields) {
      document.getElementById(`btn-purge-${category}`).disabled = current[key] !== false;
    }
  };
  resync();

  for (const [, , category] of categoryFields) {
    const btn = document.getElementById(`btn-purge-${category}`);
    btn.addEventListener('click', async () => {
      const label = PURGE_LABELS[category];
      const warning = PURGE_EXTRA_WARNING[category] || '';
      const ok = confirm(
        `"${label}" 카테고리의 DB 데이터를 전부 삭제하시겠습니까?${warning}\n\n되돌릴 수 없습니다.`
      );
      if (!ok) return;
      btn.disabled = true;
      try {
        await api.post(`/api/admin/ai/categories/${category}/purge`);
        alert(`"${label}" 데이터를 삭제했습니다.`);
      } catch (e) {
        alert(e.message);
      } finally {
        resync();
      }
    });
  }
  return resync;
}

/* ── Theme Picker ───────────────────────────────────────── */
function initThemePicker() {
  const container = document.getElementById('theme-picker');
  const current = getTheme();

  container.innerHTML = THEMES.map(t => `
    <div class="theme-swatch${t.id === current ? ' active' : ''}" data-theme-id="${t.id}" title="${t.label}">
      <div class="theme-swatch-colors">
        <div class="theme-swatch-bg" style="background:${t.bg}"></div>
        <div class="theme-swatch-accent" style="background:${t.accent}"></div>
      </div>
      <span class="theme-swatch-label">${t.label}</span>
    </div>
  `).join('');

  container.querySelectorAll('.theme-swatch').forEach(el => {
    el.addEventListener('click', () => {
      const themeId = el.dataset.themeId;
      setTheme(themeId);
      container.querySelectorAll('.theme-swatch').forEach(s => s.classList.remove('active'));
      el.classList.add('active');
      // 서버에도 저장 → 신규 앨범 생성 시 기본 테마로 사용
      api.patch('/api/admin/settings', { ui_theme: themeId }).catch(() => {});
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
      const match = TIMEZONES.find(z => z.label === input.value);
      if (!match) input.value = hidLbl.value;
    }, 150);
  });
}

/* ── Save handlers ──────────────────────────────────────── */
function bindSaveHandlers() {
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

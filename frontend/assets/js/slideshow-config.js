// Canonical slideshow effect list — 'random' is a meta-option handled by callers, not a real CSS effect.
export const EFFECTS = ['fade','slide-left','slide-right','slide-up','zoom-in','zoom-out','flip-h','blur','dissolve'];

export const EFFECT_LABELS = {
  random: '랜덤', fade: 'Fade', 'slide-left': 'Slide Left', 'slide-right': 'Slide Right',
  'slide-up': 'Slide Up', 'zoom-in': 'Zoom In', 'zoom-out': 'Zoom Out',
  'flip-h': 'Flip H', blur: 'Blur', dissolve: 'Dissolve',
};

export const DEFAULT_SETTINGS = { interval: 5, order: 'sequential', music: true, volume: 25, effect: 'random', loop: true };

// 기기(브라우저)별 저장 — 앨범/토큰과 무관. 옛날 TV 등에서 뷰어 화면의 "간단히 보기"
// 버튼으로 켜두면 그 기기에서 재생하는 모든 슬라이드쇼에 적용된다.
export const LOW_POWER_KEY = 'slideshow_low_power';

export function loadSlideshowSettings(albumDefaults = {}, token = '') {
  const base = { ...DEFAULT_SETTINGS, ...albumDefaults };
  try {
    const local = JSON.parse(localStorage.getItem(`slideshow_settings_${token}`) || '{}');
    const s = { ...base, ...local };
    if (!['sequential', 'random'].includes(s.order)) s.order = base.order;
    // 'random' is a valid effect value; only reject unknown real effect names
    if (s.effect !== 'random' && !EFFECTS.includes(s.effect)) s.effect = base.effect;
    return s;
  } catch { return { ...base }; }
}

export function saveSlideshowSettings(token, s) {
  localStorage.setItem(`slideshow_settings_${token}`, JSON.stringify(s));
}

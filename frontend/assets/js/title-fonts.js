// 공유 앨범 히어로 타이틀(.viewer-title)에 적용 가능한 display 폰트.
// Google Fonts CDN, 한글 지원 필수 — album-view.js(뷰어 적용)와 admin-album-edit.js(미리보기) 공용.
export const TITLE_FONTS = [
  { id: 'gowun-batang', label: '명조체 (Gowun Batang)', family: "'Gowun Batang', serif", weight: 700, google: 'Gowun+Batang:wght@400;700' },
  { id: 'nanum-pen', label: '손글씨체 (Nanum Pen Script)', family: "'Nanum Pen Script', cursive", weight: 400, google: 'Nanum+Pen+Script' },
  { id: 'jua', label: '고딕체 (Jua)', family: "'Jua', sans-serif", weight: 400, google: 'Jua' },
];

const GOOGLE_FONTS_HREF = `https://fonts.googleapis.com/css2?${TITLE_FONTS.map(f => `family=${f.google}`).join('&')}&display=swap`;
const LINK_ID = 'title-fonts-link';

export function ensureTitleFontsLoaded() {
  if (document.getElementById(LINK_ID)) return;
  const link = document.createElement('link');
  link.id = LINK_ID;
  link.rel = 'stylesheet';
  link.href = GOOGLE_FONTS_HREF;
  document.head.appendChild(link);
}

export function applyTitleFont(el, fontId) {
  const f = TITLE_FONTS.find(t => t.id === fontId);
  if (!f) {
    el.style.fontFamily = '';
    el.style.fontWeight = '';
    return;
  }
  el.style.fontFamily = f.family;
  el.style.fontWeight = String(f.weight);
}

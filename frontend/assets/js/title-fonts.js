// 공유 앨범 히어로 타이틀(.viewer-title)에 적용 가능한 display 폰트.
// Google Fonts CDN, 한글 지원 필수 — album-view.js(뷰어 적용)와 admin-album-edit.js(미리보기) 공용.
// 5종으로 확장(그릴링으로 카테고리별 인기 후보 3종 중 확정) — 손글씨체 대표 폰트가
// nanum-pen → gaegu로 교체됨(id 변경, DB 마이그레이션은 backend/models/database.py 참고).
export const TITLE_FONTS = [
  { id: 'gowun-batang', label: '명조체 (Gowun Batang)', family: "'Gowun Batang', serif", weight: 700, google: 'Gowun+Batang:wght@400;700',
    note: '차분하고 격식 있는 세리프 — 팔순잔치·웨딩·추모처럼 무게감 있는 자리에 어울려요' },
  { id: 'gaegu', label: '손글씨체 (Gaegu)', family: "'Gaegu', cursive", weight: 700, google: 'Gaegu:wght@700',
    note: '통통하고 손으로 쓴 듯한 캐주얼체 — 가족 여행·일상 스냅처럼 편안한 앨범에 어울려요' },
  { id: 'jua', label: '고딕체 (Jua)', family: "'Jua', sans-serif", weight: 400, google: 'Jua',
    note: '둥글둥글 밝고 힘 있는 산세리프 — 캠핑·파티처럼 활기찬 앨범에 어울려요' },
  { id: 'gamja-flower', label: '귀엽다·상큼체 (Gamja Flower)', family: "'Gamja Flower', cursive", weight: 400, google: 'Gamja+Flower',
    note: '손으로 그린 듯 장난스러운 필기체 — 아기 돌잔치·반려동물처럼 사랑스러운 앨범에 어울려요' },
  { id: 'poor-story', label: '레트로·빈티지 (Poor Story)', family: "'Poor Story', cursive", weight: 400, google: 'Poor+Story',
    note: '만화 말풍선 같은 손글씨, 옛 감성 — 오래된 사진첩·학창시절 추억 앨범에 어울려요' },
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

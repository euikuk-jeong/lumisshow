// 날짜별 보기 스크롤 중 우측에 년/월/일 배지를 잠깐 보여주는 인디케이터.
// containerSelector 안의 `.date-group-header[data-key]`(YYYY-MM-DD) 위치를 기준으로 계산한다.
export function initDateScrollIndicator(indicatorId, containerSelector, isDateMode) {
  let offsets = null;
  let hideTimer = null;
  let ticking = false;

  function formatBadge(key) {
    if (!key) return null;
    const [y, m, d] = key.split('-').map(Number);
    return `<span class="dsi-year">${y}</span><span class="dsi-day">${m}월 ${d}일</span>`;
  }

  function onScroll() {
    const indicator = document.getElementById(indicatorId);
    if (!indicator) { window.removeEventListener('scroll', onScroll); return; }
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(() => {
      ticking = false;
      if (!isDateMode() || !offsets || !offsets.length) {
        indicator.classList.remove('visible');
        return;
      }
      const y = window.scrollY + 70;
      let current = offsets[0];
      for (const o of offsets) {
        if (o.top <= y) current = o; else break;
      }
      if (!current.label) { indicator.classList.remove('visible'); return; }
      indicator.innerHTML = current.label;
      const maxScroll = document.documentElement.scrollHeight - window.innerHeight;
      const frac = maxScroll > 0 ? window.scrollY / maxScroll : 0;
      const h = indicator.offsetHeight || 44;
      indicator.style.top = `${frac * (window.innerHeight - h - 20) + 10}px`;
      indicator.classList.add('visible');
      clearTimeout(hideTimer);
      hideTimer = setTimeout(() => indicator.classList.remove('visible'), 900);
    });
  }

  window.addEventListener('scroll', onScroll, { passive: true });

  // 날짜별 보기 렌더 직후 호출 — 날짜 그룹 헤더 위치를 다시 계산한다.
  return function recomputeDateOffsets() {
    if (!isDateMode()) { offsets = null; return; }
    offsets = Array.from(document.querySelectorAll(`${containerSelector} .date-group-header`)).map(h => ({
      top: h.getBoundingClientRect().top + window.scrollY,
      label: formatBadge(h.dataset.key),
    }));
  };
}

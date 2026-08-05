// 수동 태그 추가 모달 + 순차 일괄 적용/삭제 헬퍼.
// admin-tags.js(라이트박스 "+ 태그 추가", 그리드 일괄 추가/삭제)와
// admin-browse.js(그리드 일괄 추가)가 공용으로 사용한다.

import { api } from './api.js';
import { esc } from './utils.js';

// photoPaths: string[] (1장이면 length 1). onDone({tag, success, fail})로 결과 통지.
export async function openAddTagModal(photoPaths, { onDone } = {}) {
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  // 라이트박스(.lightbox-overlay, z-index:500)가 열린 채로 이 모달이 뜰 수 있어
  // .modal-overlay의 기본 z-index(300)로는 가려진다 — 인라인으로 라이트박스보다 높게.
  overlay.style.zIndex = '600';
  const subtitle = photoPaths.length === 1
    ? esc(photoPaths[0])
    : `${photoPaths.length.toLocaleString()}장 선택됨`;
  overlay.innerHTML = `
    <div class="modal" style="max-width:360px">
      <p class="modal-title">태그 추가</p>
      <p class="text-muted text-sm" style="margin:0 0 10px">${subtitle}</p>
      <input id="add-tag-input" class="form-input" list="add-tag-vocab" placeholder="태그 입력" autocomplete="off">
      <datalist id="add-tag-vocab"></datalist>
      <div class="modal-actions">
        <button class="btn btn-ghost" id="modal-cancel">취소</button>
        <button class="btn btn-primary" id="modal-confirm">추가</button>
      </div>
    </div>`;
  document.body.appendChild(overlay);
  // 라이트박스의 document 레벨 keydown 리스너(화살표=사진 이동, Esc=닫기)가
  // input 조작 중에도 함께 반응하지 않도록 이 오버레이에서 전파를 막는다.
  overlay.addEventListener('keydown', e => e.stopPropagation());
  overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });
  overlay.querySelector('#modal-cancel').addEventListener('click', () => overlay.remove());

  const input = overlay.querySelector('#add-tag-input');
  const confirmBtn = overlay.querySelector('#modal-confirm');
  input.focus();
  input.addEventListener('keydown', e => { if (e.key === 'Enter') confirmBtn.click(); });

  confirmBtn.addEventListener('click', async () => {
    const tag = input.value.trim();
    if (!tag) return;
    confirmBtn.disabled = true;
    try {
      const { success, fail, firstError } = await applyTagToPhotos(photoPaths, tag, {
        onProgress: (i, total) => {
          if (total > 1) confirmBtn.textContent = `추가 중... (${i}/${total})`;
        },
      });
      overlay.remove();
      onDone?.({ tag, success, fail, firstError });
    } catch (e) {
      alert(e.message);
      confirmBtn.disabled = false;
      confirmBtn.textContent = '추가';
    }
  });

  try {
    const [{ vocab }, { tags }] = await Promise.all([
      api.get('/api/admin/tags/vocab'),
      api.get('/api/admin/tags'),
    ]);
    const merged = [...new Set([...vocab, ...tags.map(t => t.tag)])].sort();
    overlay.querySelector('#add-tag-vocab').innerHTML =
      merged.map(t => `<option value="${esc(t)}"></option>`).join('');
  } catch (e) {
    // 자동완성 제안 로드 실패는 자유 입력 자체를 막지 않으므로 조용히 무시.
  }
}

// 순차 POST — 하나 실패해도 나머지는 계속 진행(멱등 API라 재호출 안전).
// 검증 실패(예: 빈 태그, "/" 포함)는 모든 항목에서 동일하게 실패하므로 firstError로
// 이유를 담아 반환한다 — 그냥 실패 개수만 세면 사용자가 원인을 알 방법이 없다.
export async function applyTagToPhotos(photoPaths, tag, { onProgress } = {}) {
  let success = 0, fail = 0, firstError = null;
  for (let i = 0; i < photoPaths.length; i++) {
    try {
      await api.post('/api/admin/tags/manual', { photo_path: photoPaths[i], tag });
      success++;
    } catch (e) {
      fail++;
      firstError ??= e.message;
    }
    onProgress?.(i + 1, photoPaths.length);
  }
  return { success, fail, firstError };
}

// 순차 DELETE — 위와 동일하게 실패해도 계속 진행.
export async function deleteTagFromPhotos(photoPaths, tag, source, { onProgress } = {}) {
  let success = 0, fail = 0, firstError = null;
  for (let i = 0; i < photoPaths.length; i++) {
    try {
      await api.delete(`/api/admin/tags/${encodeURIComponent(tag)}/photo?path=${encodeURIComponent(photoPaths[i])}&source=${source}`);
      success++;
    } catch (e) {
      fail++;
      firstError ??= e.message;
    }
    onProgress?.(i + 1, photoPaths.length);
  }
  return { success, fail, firstError };
}

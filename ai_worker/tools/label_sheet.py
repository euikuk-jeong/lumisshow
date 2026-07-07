"""얼굴 라벨링 HTML 시트 생성 (M1 정답 셋 구축 보조).

미라벨 얼굴을 cosine similarity로 greedy 클러스터링해 HTML 시트로 만든다.
브라우저에서 열어 클러스터별 이름 입력(타인 묶음은 '-') → [CSV 내보내기]
→ 받은 labels.csv를 label_helper import로 반영.

  python -m ai_worker.tools.label_sheet [--threshold 0.5] [--min-size 2]

출력: $DATA_DIR/label_sheet.html (얼굴 크롭을 faces/ 상대 경로로 참조)
"""

import argparse
import html
import os

import numpy as np

from ai_worker import config, db, matcher


def greedy_cluster(embeddings: np.ndarray, threshold: float) -> list[list[int]]:
    """정규화된 (n, 512) 임베딩을 centroid 기반 greedy 클러스터링.

    각 얼굴을 기존 클러스터 centroid와 비교해 threshold 이상이면 편입,
    아니면 새 클러스터 생성. 인덱스 리스트의 리스트를 반환 (크기 내림차순).
    """
    centroids: list[np.ndarray] = []  # 정규화된 centroid
    sums: list[np.ndarray] = []
    members: list[list[int]] = []
    for i, vec in enumerate(embeddings):
        if centroids:
            sims = np.stack(centroids) @ vec
            best = int(np.argmax(sims))
            if sims[best] >= threshold:
                members[best].append(i)
                sums[best] = sums[best] + vec
                centroids[best] = sums[best] / np.linalg.norm(sums[best])
                continue
        centroids.append(vec.copy())
        sums.append(vec.copy())
        members.append([i])
    return sorted(members, key=len, reverse=True)


_PAGE = """<!doctype html><meta charset="utf-8">
<title>얼굴 라벨링 시트</title>
<style>
 body {{ font-family: sans-serif; margin: 16px; background: #f5f5f5; }}
 .cluster {{ background: #fff; border-radius: 8px; padding: 10px; margin-bottom: 12px; }}
 .cluster input[type=text] {{ font-size: 15px; padding: 4px 8px; width: 160px; }}
 .faces {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }}
 .faces label {{ position: relative; display: block; }}
 .faces img {{ width: 80px; height: 80px; object-fit: cover; border-radius: 4px; display: block; }}
 .faces input:checked + img {{ opacity: 0.25; outline: 3px solid #e33; }}
 .faces input {{ position: absolute; top: 2px; left: 2px; z-index: 1; }}
 #bar {{ position: sticky; top: 0; background: #fff; padding: 10px; border-radius: 8px;
        margin-bottom: 12px; box-shadow: 0 1px 4px rgba(0,0,0,.15); }}
 button {{ font-size: 15px; padding: 6px 14px; }}
</style>
<div id="bar">
 <b>사용법</b>: 클러스터마다 인물 이름 입력 (등록 안 할 타인 묶음은 <code>-</code>,
 모를/무시할 클러스터는 빈칸). 잘못 섞인 얼굴은 체크박스로 제외.
 <button onclick="exportCsv()">CSV 내보내기 (labels.csv)</button>
 <span id="stat"></span>
</div>
{clusters}
<script>
function exportCsv() {{
  const rows = [["face_id", "person"]];
  document.querySelectorAll(".cluster").forEach(c => {{
    const name = c.querySelector("input[type=text]").value.trim();
    if (!name) return;
    c.querySelectorAll(".faces input").forEach(cb => {{
      if (!cb.checked) rows.push([cb.dataset.face, name]);
    }});
  }});
  const csv = "\\ufeff" + rows.map(r => r.join(",")).join("\\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], {{type: "text/csv"}}));
  a.download = "labels.csv";
  a.click();
  document.getElementById("stat").textContent = ` ${{rows.length - 1}}개 라벨 내보냄`;
}}
</script>
"""


def generate(threshold: float, min_size: int) -> str:
    conn = db.connect()
    rows = conn.execute(
        """SELECT f.id, f.embedding FROM faces f
           LEFT JOIN face_labels fl ON fl.face_id = f.id
           WHERE fl.face_id IS NULL ORDER BY f.det_score DESC"""
    ).fetchall()
    if not rows:
        raise SystemExit("미라벨 얼굴이 없습니다. 먼저 scan을 실행하세요.")
    face_ids = [row["id"] for row in rows]
    embs = matcher._normalize(
        np.stack([matcher.blob_to_embedding(row["embedding"]) for row in rows])
    )
    clusters = greedy_cluster(embs, threshold)

    parts = []
    for k, idxs in enumerate(clusters):
        if len(idxs) < min_size:
            continue
        imgs = "".join(
            f'<label><input type="checkbox" data-face="{face_ids[i]}">'
            f'<img src="faces/{face_ids[i]}.jpg" loading="lazy" '
            f'title="face {face_ids[i]}"></label>'
            for i in idxs
        )
        parts.append(
            f'<div class="cluster"><input type="text" placeholder="이름 (타인: -)"> '
            f'<span>#{k + 1} · {len(idxs)}개 얼굴</span>'
            f'<div class="faces">{imgs}</div></div>'
        )
    skipped = sum(1 for idxs in clusters if len(idxs) < min_size)
    parts.append(
        f"<p>{html.escape(f'{min_size}개 미만 소형 클러스터 {skipped}개는 생략됨')}</p>"
    )

    out_path = os.path.join(config.data_dir(), "label_sheet.html")
    with open(out_path, "w", encoding="utf-8") as fp:
        fp.write(_PAGE.format(clusters="\n".join(parts)))
    print(f"얼굴 {len(face_ids)}개 → 클러스터 {len(clusters)}개 "
          f"(표시 {len(clusters) - skipped}개) → {out_path}")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(prog="label_sheet")
    parser.add_argument("--threshold", type=float, default=0.5,
                        help="클러스터 편입 유사도 (기본 0.5)")
    parser.add_argument("--min-size", type=int, default=2,
                        help="이 크기 미만 클러스터는 시트에서 생략 (기본 2)")
    args = parser.parse_args()
    generate(args.threshold, args.min_size)


if __name__ == "__main__":
    main()

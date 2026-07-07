"""정답 셋 라벨링 보조 도구 (M1).

  python -m ai_worker.tools.label_helper export labels.csv
      → 미라벨 얼굴 목록을 CSV로 내보냄 (face_id, crop, photo_path, person 빈칸)
        crop 열의 DATA_DIR/faces/{face_id}.jpg를 보면서 person 열에 이름 기입.
        등록 인물이 아닌 얼굴(타인)은 person에 '-' 기입.

  python -m ai_worker.tools.label_helper import labels.csv
      → person 열이 채워진 행을 persons/face_labels에 반영
        ('-'는 person_id NULL 라벨 = 무시 처리, 빈칸은 건너뜀)
"""

import argparse
import csv
import os
import sys

from ai_worker import config, db


def export_csv(out_path: str) -> None:
    conn = db.connect()
    rows = conn.execute(
        """SELECT f.id, f.photo_path FROM faces f
           LEFT JOIN face_labels fl ON fl.face_id = f.id
           WHERE fl.face_id IS NULL ORDER BY f.photo_path"""
    ).fetchall()
    with open(out_path, "w", newline="", encoding="utf-8-sig") as fp:
        writer = csv.writer(fp)
        writer.writerow(["face_id", "crop", "photo_path", "person"])
        for row in rows:
            crop = os.path.join(config.faces_dir(), f"{row['id']}.jpg")
            writer.writerow([row["id"], crop, row["photo_path"], ""])
    print(f"{len(rows)}개 미라벨 얼굴 → {out_path}")


def import_csv(in_path: str) -> None:
    conn = db.connect()
    person_ids: dict[str, int] = {
        row["name"]: row["id"] for row in conn.execute("SELECT id, name FROM persons")
    }
    labeled = skipped = 0
    with open(in_path, newline="", encoding="utf-8-sig") as fp:
        for row in csv.DictReader(fp):
            name = (row.get("person") or "").strip()
            if not name:
                skipped += 1
                continue
            if name == "-":
                pid = None
            else:
                if name not in person_ids:
                    cur = conn.execute(
                        "INSERT INTO persons (name) VALUES (?)", (name,)
                    )
                    person_ids[name] = cur.lastrowid
                pid = person_ids[name]
            conn.execute(
                """INSERT INTO face_labels (face_id, person_id) VALUES (?, ?)
                   ON CONFLICT(face_id) DO UPDATE SET
                     person_id=excluded.person_id, labeled_at=CURRENT_TIMESTAMP""",
                (int(row["face_id"]), pid),
            )
            labeled += 1
    conn.commit()
    print(f"{labeled}개 라벨 반영, {skipped}개 빈칸 건너뜀")


def main() -> None:
    parser = argparse.ArgumentParser(prog="label_helper")
    parser.add_argument("command", choices=["export", "import"])
    parser.add_argument("csv_path")
    args = parser.parse_args()
    if args.command == "export":
        export_csv(args.csv_path)
    else:
        if not os.path.exists(args.csv_path):
            sys.exit(f"파일 없음: {args.csv_path}")
        import_csv(args.csv_path)


if __name__ == "__main__":
    main()

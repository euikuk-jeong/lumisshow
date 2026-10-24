"""dev 서버 test 모드용 샘플 사진 생성.

외부 이미지 없이 Pillow로 단색 그라데이션 JPEG를 만들고 EXIF(촬영일시·제조사·모델)를 넣는다.
촬영일은 폴더별로 다른 연·월에 흩어 두어 정렬·날짜 표시를 확인할 수 있게 한다.

사용: .venv/bin/python scripts/make-test-photos.py [출력 폴더]   (기본: testdata/photos)
이미 있는 파일은 건드리지 않는다.
"""
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image, ImageDraw

_EXIF_IFD = 0x8769
_TAG_MAKE, _TAG_MODEL = 0x010F, 0x0110
_TAG_DATETIME_ORIGINAL = 0x9003

# (폴더, 첫 촬영일, 장수, 세로 사진 비율)
_SETS = [
    ("2024/봄 여행", datetime(2024, 4, 6, 9, 0), 12, 0.3),
    ("2024/여름 바다", datetime(2024, 8, 2, 14, 0), 10, 0.2),
    ("2025/가족 모임", datetime(2025, 1, 1, 12, 0), 8, 0.5),
    ("2025/가을 산책", datetime(2025, 10, 18, 16, 0), 10, 0.4),
    ("2026/일상", datetime(2026, 3, 9, 8, 30), 10, 0.3),
]


def _make(path: Path, taken: datetime, portrait: bool, rng: random.Random) -> None:
    w, h = (900, 1200) if portrait else (1200, 900)
    c1 = tuple(rng.randint(30, 220) for _ in range(3))
    c2 = tuple(rng.randint(30, 220) for _ in range(3))
    img = Image.new("RGB", (w, h))
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = y / (h - 1)
        draw.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(c1, c2)))
    draw.text((40, 40), f"{path.parent.name}\n{path.name}\n{taken:%Y-%m-%d %H:%M}", fill=(255, 255, 255))

    exif = Image.Exif()
    exif[_TAG_MAKE] = "LumisShow"
    exif[_TAG_MODEL] = "TestCam"
    exif.get_ifd(_EXIF_IFD)[_TAG_DATETIME_ORIGINAL] = taken.strftime("%Y:%m:%d %H:%M:%S")
    img.save(path, "JPEG", quality=85, exif=exif)


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "testdata/photos")
    rng = random.Random(42)  # 매번 같은 결과
    created = 0
    for folder, start, count, portrait_ratio in _SETS:
        d = out / folder
        d.mkdir(parents=True, exist_ok=True)
        for i in range(count):
            p = d / f"IMG_{i + 1:04d}.jpg"
            portrait = rng.random() < portrait_ratio
            taken = start + timedelta(hours=i * 3, minutes=rng.randint(0, 59))
            if p.exists():
                continue
            _make(p, taken, portrait, rng)
            created += 1
    print(f"{out}: 새로 만든 사진 {created}장")


if __name__ == "__main__":
    main()

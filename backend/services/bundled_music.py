"""번들 기본 음원(frontend/assets/music/bundled/) → DATA_DIR/music/bundled/ 동기화.

Admin 음악 선택 UI(GET /api/admin/music)와 재생 엔드포인트(/music/{token})는
DATA_DIR/music/ 하위 파일만 다루도록 되어 있다(경로 containment 검사).
이 구조를 그대로 재사용하기 위해 이미지에 포함된 번들 음원을 서버 시작 시
DATA_DIR로 복사해둔다 — 별도 허용 경로를 추가하지 않는다.
"""

import logging
import os
import shutil
from pathlib import Path

_logger = logging.getLogger(__name__)

_BUNDLED_SOURCE_DIR = Path(__file__).parent.parent.parent / "frontend" / "assets" / "music" / "bundled"


def sync_bundled_music() -> None:
    if not _BUNDLED_SOURCE_DIR.is_dir():
        return

    target_dir = Path(os.getenv("DATA_DIR", "./testdata/data")) / "music" / "bundled"
    target_dir.mkdir(parents=True, exist_ok=True)

    source_names = {f.name for f in _BUNDLED_SOURCE_DIR.iterdir() if f.is_file()}
    for fname in source_names:
        shutil.copy2(_BUNDLED_SOURCE_DIR / fname, target_dir / fname)

    for existing in target_dir.iterdir():
        if existing.is_file() and existing.name not in source_names:
            existing.unlink()

    _logger.info("번들 음원 동기화 완료: %d개 (%s)", len(source_names), target_dir)

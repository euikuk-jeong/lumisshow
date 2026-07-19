"""backend/models/schemas.py 순수 헬퍼 테스트."""

from backend.models.schemas import build_slideshow_defaults

_SV = {
    "slideshow_interval": 5,
    "slideshow_order": "sequential",
    "slideshow_effect": "random",
    "slideshow_music": True,
    "slideshow_volume": 25,
    "slideshow_loop": True,
}


def test_build_slideshow_defaults_no_overrides_uses_global_settings():
    result = build_slideshow_defaults({}, _SV)
    assert result == {
        "interval": 5,
        "order": "sequential",
        "effect": "random",
        "music": True,
        "volume": 25,
        "loop": True,
    }


def test_build_slideshow_defaults_album_overrides_win():
    overrides = {
        "interval": 10,
        "order": "random",
        "effect": "fade",
        "music": 0,  # SQLite에서 오는 정수 — bool로 강제 변환돼야 함
        "volume": 80,
        "loop": 1,
    }
    result = build_slideshow_defaults(overrides, _SV)
    assert result["interval"] == 10
    assert result["order"] == "random"
    assert result["effect"] == "fade"
    assert result["music"] is False
    assert result["volume"] == 80
    assert result["loop"] is True


def test_build_slideshow_defaults_sqlite_bool_coerced_not_int():
    """SQLite는 boolean을 0/1 정수로 반환 — music/loop는 반드시 실제 bool이어야 한다
    (1 == True는 파이썬에서 참이라 타입 회귀가 값 비교 테스트로는 안 잡힘)."""
    result = build_slideshow_defaults({"music": 1, "loop": 0}, _SV)
    assert result["music"] is True
    assert result["loop"] is False


def test_build_slideshow_defaults_person_forces_music_off():
    """인물 슬라이드쇼는 앨범이 없어 음악이 없다 — music=False를 명시적으로 넘겨야
    전역 기본값(slideshow_music=True)으로 폴백되지 않는다."""
    result = build_slideshow_defaults({"music": False}, _SV)
    assert result["music"] is False
    assert result["interval"] == 5  # 나머지는 전역 설정 그대로
    assert result["loop"] is True


def test_build_slideshow_defaults_none_override_falls_back():
    result = build_slideshow_defaults({"interval": None, "volume": None}, _SV)
    assert result["interval"] == 5
    assert result["volume"] == 25

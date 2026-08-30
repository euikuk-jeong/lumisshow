"""LLM 스타일 추천(음악/테마/폰트) 프롬프트·검증용 후보 vocab — 프론트 전용 모듈의 백엔드 미러.

무드-곡 매핑은 frontend/assets/js/pages/admin-album-edit.js의 BUNDLED_MUSIC_CREDITS,
테마는 frontend/assets/js/theme.js의 THEMES, 폰트는 frontend/assets/js/title-fonts.js의
TITLE_FONTS를 복제한다 — LLM 프롬프트 구성과 응답 allowlist 검증이 백엔드에서 이뤄져야
하는데 저 목록들은 전부 프론트 전용 모듈이라 그대로 import할 수 없다(tag_vocab.py와
동일한 "레이어 분리로 인한 의도적 중복" 패턴). 프론트 쪽 값이 바뀌면 이 파일도 함께
갱신해야 한다.
"""

BUNDLED_MUSIC_CREDITS: list[dict] = [
    {"mood": "잔잔한", "title": "Calm Piano", "artist": "alex-morgan", "file": "alex-morgan-calm-piano-541028.mp3"},
    {"mood": "잔잔한", "title": "Evening Calm Piano", "artist": "andriih", "file": "andriih-evening-calm-piano-580085.mp3"},
    {"mood": "감성적", "title": "Emotional", "artist": "PaulYudin", "file": "paulyudin-emotional-emotional-music-573976.mp3"},
    {"mood": "감성적", "title": "Emotional", "artist": "alex-morgan", "file": "alex-morgan-emotional-545518.mp3"},
    {"mood": "경쾌한", "title": "Summer Pop", "artist": "JonasBlakewood", "file": "jonasblakewood-summer-pop-546980.mp3"},
    {"mood": "경쾌한", "title": "Positive Dream Upbeat Pop", "artist": "LightBeatsMusic", "file": "lightbeatsmusic-positive-dream-upbeat-pop-513937.mp3"},
    {"mood": "따뜻한·노스탤직", "title": "Warm Nostalgic Sentimental Music", "artist": "andriig", "file": "andriig-warm-nostalgic-sentimental-music-471262.mp3"},
    {"mood": "따뜻한·노스탤직", "title": "Nostalgic Acoustic Guitar", "artist": "Tunetank", "file": "tunetank-nostalgic-acoustic-guitar-348939.mp3"},
    {"mood": "웅장한", "title": "Epic Piano", "artist": "PaulYudin", "file": "paulyudin-epic-piano-154655.mp3"},
    {"mood": "웅장한", "title": "Majestic Triumphant Epic Music", "artist": "alex-morgan", "file": "alex-morgan-majestic-triumphant-epic-music-583277.mp3"},
]

THEME_OPTIONS: list[dict] = [
    {"id": "dark", "label": "Dark (어두운 기본)"},
    {"id": "oled", "label": "OLED Black (완전한 검정)"},
    {"id": "slate", "label": "Slate (차분한 남색조)"},
    {"id": "warm", "label": "Warm Dark (따뜻한 어두운 톤)"},
    {"id": "light", "label": "Light (밝은 기본)"},
    {"id": "sepia", "label": "Sepia (세피아, 옛날 사진첩 느낌)"},
    {"id": "sky", "label": "Sky (밝은 하늘색)"},
    {"id": "rose", "label": "Rose (밝은 로즈핑크)"},
]

TITLE_FONT_OPTIONS: list[dict] = [
    {"id": "gowun-batang", "label": "명조체",
     "note": "차분하고 격식 있는 세리프 — 팔순잔치·웨딩·추모처럼 무게감 있는 자리에 어울려요"},
    {"id": "gaegu", "label": "손글씨체",
     "note": "통통하고 손으로 쓴 듯한 캐주얼체 — 가족 여행·일상 스냅처럼 편안한 앨범에 어울려요"},
    {"id": "jua", "label": "고딕체",
     "note": "둥글둥글 밝고 힘 있는 산세리프 — 캠핑·파티처럼 활기찬 앨범에 어울려요"},
    {"id": "gamja-flower", "label": "귀엽다·상큼체",
     "note": "손으로 그린 듯 장난스러운 필기체 — 아기 돌잔치·반려동물처럼 사랑스러운 앨범에 어울려요"},
    {"id": "poor-story", "label": "레트로·빈티지",
     "note": "만화 말풍선 같은 손글씨, 옛 감성 — 오래된 사진첩·학창시절 추억 앨범에 어울려요"},
]

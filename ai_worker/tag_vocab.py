"""CLIP zero-shot 태그 어휘. 표준 데이터셋(ImageNet 등) 번역이 아니라, 가족 앨범에
실제 나올 법한 개념 위주로 직접 큐레이션했다(총 80개, 10개 카테고리 — 2026-08-02
`doc/tagging_requirement.md` 확정 82개에서, 실사진 검증 중 "추석"/"설날" 프롬프트가
체계적으로 오탐(야외 단체사진을 명절로 오인)해 2026-08-02 제외해 80개로 조정).
`prompt`(영어)는 CLIP 텍스트 인코더 입력,
`label`(한국어)은 화면 표시용이며 `photo_tags.tag` 값으로 그대로 저장된다.

어휘 추가는 이 리스트에 항목만 더하면 된다 — CLIP 텍스트 임베딩은 스캔마다
런타임에 계산하므로(재학습·별도 재생성 스텝 불필요), 다음 스캔부터 바로 반영된다.
다만 이미 분석된 사진에는 다음 증분 스캔이 적용되지 않으므로(신규/변경 사진만
재채점) 기존 사진에 소급 적용하려면 Phase 4의 tag-backfill이 필요하다.
"""

TAG_VOCAB: list[dict[str, str]] = [
    # 사람/구도 (7) — 특정 인물이 아니라 구도/상황만 다룸. 인물 식별은 얼굴 인식
    # (source='person')이 이미 담당.
    {"prompt": "a photo of a baby", "label": "아기"},
    {"prompt": "a photo of a child", "label": "어린이"},
    {"prompt": "a photo of a couple", "label": "커플"},
    {"prompt": "a group photo of people", "label": "단체사진"},
    {"prompt": "a selfie photo", "label": "셀카"},
    {"prompt": "a photo of a person from behind", "label": "뒷모습"},
    {"prompt": "a close-up photo of a smiling face", "label": "웃는얼굴"},
    # 동물 (6)
    {"prompt": "a photo of a dog", "label": "강아지"},
    {"prompt": "a photo of a cat", "label": "고양이"},
    {"prompt": "a photo of a bird", "label": "새"},
    {"prompt": "a photo of a fish", "label": "물고기"},
    {"prompt": "a photo of an insect", "label": "곤충"},
    {"prompt": "a photo taken at a zoo", "label": "동물원"},
    # 음식 (10)
    {"prompt": "a photo of a birthday cake", "label": "생일케이크"},
    {"prompt": "a photo of a cup of coffee", "label": "커피"},
    {"prompt": "a photo of alcoholic drinks", "label": "술"},
    {"prompt": "a photo of fruit", "label": "과일"},
    {"prompt": "a photo of a barbecue", "label": "고기굽기"},
    {"prompt": "a photo of ice cream", "label": "아이스크림"},
    {"prompt": "a photo of bread and bakery items", "label": "빵"},
    {"prompt": "a photo of a lunch box", "label": "도시락"},
    {"prompt": "a photo of a noodle dish", "label": "면요리"},
    {"prompt": "a photo of a group dinner at a restaurant", "label": "회식"},
    # 탈것 (6)
    {"prompt": "a photo of a car", "label": "자동차"},
    {"prompt": "a photo of a bicycle", "label": "자전거"},
    {"prompt": "a photo of a train", "label": "기차"},
    {"prompt": "a photo of an airplane", "label": "비행기"},
    {"prompt": "a photo of a boat", "label": "배"},
    {"prompt": "a photo of a motorcycle", "label": "오토바이"},
    # 생활용품/사물 (8)
    {"prompt": "a photo of toys", "label": "장난감"},
    {"prompt": "a photo of books", "label": "책"},
    {"prompt": "a photo of a laptop computer", "label": "노트북"},
    {"prompt": "a photo of a camera", "label": "카메라"},
    {"prompt": "a photo of an umbrella", "label": "우산"},
    {"prompt": "a photo of a christmas tree", "label": "크리스마스트리"},
    {"prompt": "a photo of a wrapped gift box", "label": "선물상자"},
    {"prompt": "a photo of balloons", "label": "풍선"},
    # 자연/장소(실외) (13)
    {"prompt": "a photo of the sea", "label": "바다"},
    {"prompt": "a photo of a mountain", "label": "산"},
    {"prompt": "a photo of a river", "label": "강"},
    {"prompt": "a photo of a lake", "label": "호수"},
    {"prompt": "a photo of a forest", "label": "숲"},
    {"prompt": "a photo of snow", "label": "눈"},
    {"prompt": "a photo of cherry blossoms", "label": "벚꽃"},
    {"prompt": "a photo of autumn foliage", "label": "단풍"},
    {"prompt": "a photo of a sunset", "label": "노을"},
    {"prompt": "a photo of a park", "label": "공원"},
    {"prompt": "a photo of a playground", "label": "놀이터"},
    {"prompt": "a photo of a campsite", "label": "캠핑장"},
    {"prompt": "a photo of a flower field", "label": "꽃밭"},
    # 장소(실내) (7)
    {"prompt": "a photo of a kitchen", "label": "부엌"},
    {"prompt": "a photo of a living room", "label": "거실"},
    {"prompt": "a photo of a bedroom", "label": "침실"},
    {"prompt": "a photo of a classroom", "label": "교실"},
    {"prompt": "a photo of an office", "label": "사무실"},
    {"prompt": "a photo of a cafe interior", "label": "카페"},
    {"prompt": "a photo of a restaurant interior", "label": "식당"},
    # 날씨/시간대 (6)
    {"prompt": "a photo taken in the rain", "label": "비"},
    {"prompt": "a photo of a sunrise", "label": "일출"},
    {"prompt": "a photo of a city skyline at night", "label": "야경"},
    {"prompt": "a photo of a rainbow", "label": "무지개"},
    {"prompt": "a photo of clouds in the sky", "label": "구름"},
    {"prompt": "a photo of a foggy scene", "label": "안개"},
    # 이벤트/행사 (12) — "추석"/"설날"은 실사진 검증 중 오탐이 심해 제외(위 docstring 참고)
    {"prompt": "a photo of a birthday party", "label": "생일파티"},
    {"prompt": "a photo of a christmas celebration", "label": "크리스마스"},
    {"prompt": "a photo of a wedding ceremony", "label": "결혼식"},
    {"prompt": "a photo of a Korean first birthday celebration", "label": "돌잔치"},
    {"prompt": "a photo of a graduation ceremony", "label": "졸업식"},
    {"prompt": "a photo of a school sports day", "label": "운동회"},
    {"prompt": "a photo of a picnic outing", "label": "소풍"},
    {"prompt": "a photo taken while traveling", "label": "여행"},
    {"prompt": "a photo of camping", "label": "캠핑"},
    {"prompt": "a photo of fireworks", "label": "불꽃놀이"},
    {"prompt": "a photo of a concert or live performance", "label": "콘서트"},
    {"prompt": "a photo of watching a sports game", "label": "스포츠경기 관람"},
    # 액티비티/스포츠 (5)
    {"prompt": "a photo of swimming", "label": "수영"},
    {"prompt": "a photo of hiking on a mountain trail", "label": "등산"},
    {"prompt": "a photo of fishing", "label": "낚시"},
    {"prompt": "a photo of skiing or snowboarding", "label": "스키"},
    {"prompt": "a photo of riding a bicycle", "label": "자전거타기"},
]

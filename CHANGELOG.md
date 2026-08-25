# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.17.7] - 2026-08-25

### Fixed
- **공유 앨범/Admin 사진 단독 보기가 전체화면으로 표시되지 않음**: footer 바가 세로 공간을
  차지하고 이미지 좌우 120px 여백이 있어 슬라이드쇼보다 사진이 작게 보이던 문제. footer/nav를
  이미지 위 반투명 오버레이로 변경, 이미지는 여백 없이 화면 전체를 채우도록 수정(슬라이드쇼
  `.ss-img`와 동일 edge-to-edge 방식) (`viewer.css`의 `.spv-*`, `admin.css`의 `.lightbox-*`)

## [2.17.6] - 2026-08-24

### Fixed
- **음악이 자동으로 다음 곡 넘어갈 때 재생 정보(토스트·정보 패널) 표시 안 됨**: 이전/다음 버튼
  클릭 시에만 `showMusicToast()`/`refreshInfoPanel()`를 호출하고 `ended` 이벤트(자동 전환)에는
  누락돼 있던 것을 동일하게 호출하도록 수정 (`slideshow.js`)
- **모바일 전체화면에서 이전/다음 곡·전체화면 버튼이 항상 숨겨짐**: 좁은 화면(≤640px)·터치 단말
  미디어쿼리 양쪽에서 `#ss-prev-track`/`#ss-next-track`/`#ss-fs-btn`을 숨기던 규칙을 제거해
  핵심 버튼(음악 On/Off·이전/다음 곡·일시정지·전체화면·다운로드·닫기)에 포함 (`slideshow.css`)

## [2.17.5] - 2026-08-24

### Added
- **기본 제공 배경음악 무드별 2곡으로 확장**: 무드당 1곡뿐이던 번들 음원을 Pixabay Music에서
  추가 선정해 총 10곡(무드당 2곡)으로 확장. 신규 5곡에 ID3 태그(제목/아티스트/앨범="Pixabay
  Music"/커버 이미지)를 삽입 (`admin-album-edit.js`의 `BUNDLED_MUSIC_CREDITS`)

## [2.17.4] - 2026-08-24

### Added
- **앨범 타이틀 폰트 5종으로 확장**: 기존 4종(명조체/손글씨체/고딕체/시스템 기본)에서 귀엽다·상큼체
  (Gamja Flower)/레트로·빈티지(Poor Story) 2종을 추가. 손글씨체 대표 폰트는 나눔펜스크립트에서
  개구체(Gaegu)로 교체 — 카테고리별 인기 후보 3종씩 실제 앨범명 예시로 비교해 확정
  (`title-fonts.js`)
- **타이틀 폰트 선택 시 어울리는 스타일 안내**: Admin 앨범 편집 화면에서 폰트 선택 즉시 "이런
  앨범에 어울려요" 한 줄 설명을 미리보기 아래 표시 (`admin-album-edit.js`)

### Changed
- **기존 앨범의 손글씨체 폰트 id 자동 마이그레이션**: `title_font='nanum-pen'`으로 저장된 앨범을
  서버 기동 시 `'gaegu'`로 일괄 변환 (`database.py`의 `_migrate_legacy_title_font()`)

## [2.17.3] - 2026-08-23

### Fixed
- **Admin 앨범 편집 "기본 정보" 카드 수평선 중복**: 조회 수 위/아래로 두 개 있던 구분선을
  조회 수와 앨범 테마 사이 하나로 정리 (`admin-album-edit.js`)
- **Admin 앨범 편집 커버 미리보기 크롭이 실제 공유 화면과 다르게 보임**: 고정
  `height:180px`+그라데이션 고정 54px 조합이 실제 뷰어(900px 폭/400px 높이)와 종횡비가
  달라 크롭 영역이 어긋나던 것을, `aspect-ratio: 900/400`+그라데이션 `height:30%`로 변경해
  실제 화면과 동일한 크롭·그라데이션 비율을 재현 (`admin.css`)
- **공유 앨범 화면 브라우저 탭 타이틀이 앨범 이름을 반영하지 않음**: 앨범 로드 후
  `document.title`을 앨범 이름으로 설정 (`album-view.js`)

## [2.17.2] - 2026-08-23

### Fixed
- **Admin 앨범 편집 커버 미리보기가 실제 공유 화면과 다르게 보임**: 커버 이미지 하단
  그라데이션 오버레이가 미리보기에는 없어 실제 뷰어(`.viewer-cover::after`)와 다르게
  보이던 것을 동일한 방식으로 추가 (`admin.css`)

### Changed
- **Admin 앨범 편집 "기본 정보" 카드 필드 순서 조정**: 앨범 이름 → 설명 → 커버 → 조회 수 →
  앨범 테마 → 폰트 → 배경음악 순으로 재배치해 커버가 이름·설명 바로 아래, 조회 수 바로 위에
  오도록 변경 (`admin-album-edit.js`)

### Added
- **공유 앨범 타이틀 폰트 적용 범위 확대**: 기존 히어로 타이틀(`.viewer-title`)에만 적용되던
  `title_font`를 앨범 설명(`.viewer-desc`)과 사진/동영상 섹션 타이틀(`.viewer-section-title`)
  에도 함께 적용 (`album-view.js`)

## [2.17.1] - 2026-08-23

### Fixed
- **공유 앨범 히어로 커버 크롭 시 인물 잘림**: v2.16.5에서 도입한 `object-position: 50% 20%`
  고정 크롭만으로는 사진마다 인물 위치가 달라 여전히 잘리는 사례가 있어, 커버 높이를
  300px→400px(모바일 200px→260px)로 확대하고 하단에 배경색 그라데이션 오버레이를 추가해
  잘림 경계를 완화 (`viewer.css`)
- **공유 앨범 사진 전체 다운로드 버튼이 좁은 보조 버튼으로 축소된 문제**: v2.16.5에서
  `width: fit-content`로 줄였던 것을 이전처럼 전체 폭 버튼으로 복귀 (`viewer.css`)

### Added
- **Admin 앨범 편집 화면 커버 미리보기**: "기본 정보" 카드 상단에 실제 공유 뷰어와 동일한
  크롭으로 현재 설정된 커버를 표시. 그리드·라이트박스 어디서 커버를 변경해도 즉시 갱신
  (`admin-album-edit.js`, `admin.css`)
- **공유 앨범 구역 구분선**: 앨범 정보/사진/동영상 구역 사이에 구분선을 추가해 화면 구성을
  명확히 구별 (`album-view.js`)

## [2.17.0] - 2026-08-23

### Added
- **공유 앨범 타이틀 폰트 커스터마이징**: 앨범 히어로 타이틀(`.viewer-title`)에 한글 지원
  Google Fonts 3종(명조체 Gowun Batang / 손글씨체 Nanum Pen Script / 고딕체 Jua) 또는
  시스템 기본 중 앨범별로 선택 적용 가능. `albums.title_font` 컬럼 추가(nullable, 기존
  앨범은 시스템 기본 유지). Admin 앨범 편집 화면에서 드롭다운 + 앨범 이름 실시간 미리보기로
  선택(`frontend/assets/js/title-fonts.js`). Google Fonts는 필요한 경우에만 로드 —
  공유뷰어는 폰트를 지정한 앨범만, Admin은 앨범 편집 화면에서만 요청이 발생하고 나머지
  화면은 외부 요청 없이 유지

### Changed
- **Admin 앨범 편집 "기본 정보" 카드 재구성**: 이름/설명 → 조회수 → 앨범 테마/폰트/배경음악
  순서로 재배치. 기존 "슬라이드쇼 기본 설정" 폼에 있던 앨범 테마 선택을 이쪽으로 이동
  (`frontend/assets/js/pages/admin-album-edit.js`)

## [2.16.5] - 2026-08-23

### Fixed
- **EXIF 정보 패널 라벨 한/영 혼용 통일**: Admin 라이트박스와 공유 슬라이드쇼 정보 패널의
  `Filename`/`Date`/`Resolution` 등 영어 라벨을 공용 딕셔너리(`frontend/assets/js/exif-labels.js`)
  기반 한글 라벨로 통일 (`lightbox.js`, `pages/slideshow.js`)
- **사진 그리드 로딩 중 빈 칸 노출**: 썸네일 on-demand 생성 중 아무 표시 없는 빈 박스만
  보이던 문제를 로딩 shimmer 스켈레톤으로 개선. 공용 헬퍼 `thumbImg()`(`utils.js`)와
  `.thumb-loading` 클래스(`admin.css`)를 사진 탐색기·인물·태그·앨범 편집 등 전체
  Admin 그리드에 적용
- **공유 앨범 히어로 커버 크롭 시 인물 잘림 위험**: `.viewer-cover img`에
  `object-position: 50% 20%`를 적용해 세로 인물샷 크롭 시 얼굴이 잘리는 문제 완화

### Changed
- **공유 앨범 버튼 시각적 위계 개선**: "슬라이드쇼" 주 액션 버튼을 ZIP 다운로드 버튼보다
  앞에 배치하고, ZIP 다운로드는 전체 폭 버튼에서 중앙정렬된 보조 버튼으로 축소
  (`pages/album-view.js`, `viewer.css`)

## [2.16.4] - 2026-08-21

### Fixed
- **AI 워커 폴더명 태깅이 신규 사진 분석 다음날에야 반영되던 문제**: `run_scan()`에서
  폴더명(Kiwi) 태깅 호출이 얼굴/위치/AI태그 분석 루프보다 먼저 실행되어, 이번 스캔에서
  처음 분석되는 사진은 아직 `photos_analyzed`에 행이 없어 폴더 태깅 대상에서 빠지고
  다음날 스캔에야 반영되었음. 호출 순서를 분석 루프 뒤로 옮겨 같은 스캔 안에서
  바로 처리되도록 수정 (`ai_worker/main.py`)

## [2.16.3] - 2026-08-21

### Changed
- **사진 정렬 기본값 재조정**: 촬영일 오래된 순(오름차순)으로 재변경.
  앨범 사진 DB 디폴트/앨범 편집/사진 탐색/공유 앨범 뷰어는 `taken_at asc`로,
  인물 전체 사진은 기존 `taken_at desc` 유지
  (`backend/models/schemas.py`, `backend/routers/admin_albums.py`,
  `frontend/assets/js/pages/admin-browse.js`)

## [2.16.2] - 2026-08-21

### Changed
- **공유 앨범 사진/동영상 구역 명확히 분리**: 요약 영역의 사진/동영상 카운트는
  순수 정보 텍스트로 정리하고, 각 구역 헤딩(사진/동영상)에 상대 구역이 있을
  때만 노출되는 점프 버튼을 배치. 사진 구역도 동영상과 동일하게 헤딩+장수를
  표시하고, "전체 다운로드 (ZIP)"는 "사진 전체 다운로드 (ZIP)"로 명확화.
  슬라이드쇼는 사진 전용이라 슬라이드쇼/설정/간단히 보기 버튼을 사진 구역의
  다운로드 버튼 바로 아래로 이동. 사진 또는 동영상이 0건이면 해당 구역
  전체(헤딩·다운로드·그리드)를 표시하지 않음
  (`frontend/assets/js/pages/album-view.js`, `viewer.css`)

## [2.16.1] - 2026-08-21

### Changed
- **공유 앨범 동영상 존재 알림 개선**: 사진 그리드 아래 멀리 있는 동영상 섹션을
  처음 보는 사람은 존재를 알아차리기 어려운 문제 개선. 상단 메타 영역의 동영상
  개수 표시를 클릭 가능한 배지로 바꾸고, 클릭 시 동영상 섹션으로 스크롤 이동
  (`frontend/assets/js/pages/album-view.js`, `viewer.css`)

## [2.16.0] - 2026-08-21

### Added
- **앨범 내 동영상 공유 갤러리**: 앨범에 동영상(`.mp4`/`.mov`/`.webm`/`.m4v`)을 사진과
  함께 추가할 수 있으며, 공유 뷰어에서는 사진 그리드와 분리된 "동영상" 섹션으로 노출.
  ffmpeg `thumbnail` 필터로 대표 프레임 썸네일을 생성하고(시킹 폴백 포함), ffprobe로
  재생시간·해상도를 추출(`backend/services/thumbnail.py`). 클릭 시 라이트박스형
  오버레이에서 네이티브 `<video controls>`로 인라인 재생(줌/팬 제스처는 미적용) —
  Admin 라이트박스(`lightbox.js`)와 공유뷰어(`album-view.js`) 양쪽 모두 지원
- **동영상 전체 다운로드**: 기존 사진 ZIP과는 별도로 동영상만 모은 ZIP 다운로드
  엔드포인트 추가(`GET /api/share/{token}/download-videos`)
- **Admin 탐색기·앨범편집 그리드 재생 아이콘**: 동영상 항목에 재생 아이콘 오버레이
  표시, "커버로 설정" 버튼은 숨김(동영상은 정적 커버 이미지로 지정 불가)
- **앨범 카드 표시 개선**: 동영상 개수(🎬)와 다가오는 공유 링크 만료일을 앨범 카드에
  추가, 메타 정보를 2줄 고정 레이아웃으로 정리(`admin-albums.js`)

### Fixed
- **동영상을 커버로 지정 시 첫 사진으로 조용히 폴백되던 문제**: 공유뷰어의
  `cover_index` 계산이 사진만 대상으로 하다 보니 동영상 경로가 매칭되지 않아 발생.
  `PUT /api/admin/albums/{id}`에서 동영상 `cover_path` 지정을 400으로 거부하도록
  API 레벨 가드 추가(`backend/routers/admin_albums.py`)

### Changed
- **Dockerfile에 ffmpeg 설치**: 동영상 썸네일·메타 추출용 의존성 추가(Debian 공식
  패키지, GPL 2+ — 별도 프로세스 호출 방식이라 백엔드 코드에 라이센스 전파 없음,
  `docker/CLAUDE.md`에 근거 기록)

## [2.15.4] - 2026-08-20

### Changed
- **앨범 편집 설정 자동저장으로 전환**: 앨범 편집 화면의 "기본 정보"(이름·설명·음악)/
  "슬라이드쇼 기본 설정" 저장 버튼을 없애고, 필드 변경 시 600ms debounce 후 자동
  저장하도록 변경. 저장 중 추가 변경이 들어오면 완료 후 최신 값으로 한 번 더 저장해
  유실 방지(`frontend/assets/js/pages/admin-album-edit.js`)

## [2.15.3] - 2026-08-20

### Changed
- **사진 정렬 기본값을 최신순으로 변경**: 앨범 사진 정렬(신규 앨범)·앨범 편집 화면·
  인물 전체 사진·공유 앨범 뷰어는 촬영일 내림차순(taken_at desc), 사진 탐색기
  (Admin Browse)는 파일명 내림차순(name desc)이 기본값이 되도록 변경
  (`backend/routers/admin_albums.py`, `backend/models/schemas.py`,
  `frontend/assets/js/pages/admin-album-edit.js`, `admin-browse.js`,
  `admin-person-photos.js`)

## [2.15.2] - 2026-08-09

### Changed
- **음악 커버 이미지 크기 체계화**: 슬라이드쇼 음악 토스트 커버 26px → 32px,
  정보패널 커버 56px → 64px, Admin 브랜드 아이콘(상단바/로그인) 28px → 32px로
  조정해 표시 크기를 32/64px 2단계로 구분(`slideshow.css`, `admin.css`)
- **`default-music-cover.png` 축소**: 1254×1254 원본을 실제 표시 크기(최대 64px)에
  맞춰 128×128로 축소(레티나 2배 여유). 원본은 `default-music-cover-original.png`로
  별도 보존

## [2.15.1] - 2026-08-09

### Fixed
- **Admin 브랜드 아이콘 정렬**: 전역 `img{display:block}` 리셋으로 `.brand-icon`이
  블록화되어 타이틀이 아래줄로 밀리던 문제 수정. 아이콘 크기도 20px → 28px로
  확대(`frontend/assets/css/admin.css`)

## [2.15.0] - 2026-08-09

### Added
- **FLAC/OGG/Opus 음악 파일 텍스트 태그 지원**: 배경음악 태그 표시가 기존
  ID3(MP3/WAV)만 읽던 것에서 Vorbis Comment(FLAC/OGG/Opus, `title`/`artist`/`album`)
  까지 확장. 커버 이미지는 이미 FLAC까지 지원하고 있었음
  (`backend/services/music_tags.py`)
- **Admin 브랜드 아이콘 추가**: 로그인 화면 타이틀과 Admin 좌상단 타이틀 앞에
  `default-music-cover.png`를 아이콘으로 표시(`.brand-icon`, `admin.css`)

## [2.14.1] - 2026-08-09

### Changed
- **슬라이드쇼 정보패널 음악 커버 레이아웃 변경**: 커버 이미지가 텍스트 위에
  왼쪽 정렬로 쌓여 트랙마다 박스 너비가 바뀔 때 이미지 위치가 흔들리던 문제를
  개선. 커버(고정 56px)를 왼쪽 열, 제목/아티스트/앨범/트랙 텍스트를 오른쪽
  열로 분리해 박스 너비 변화와 무관하게 이미지 위치 고정
  (`frontend/assets/js/pages/slideshow.js`, `frontend/assets/css/slideshow.css`)
- 기본 커버 이미지(`default-music-cover.png`) 교체

## [2.14.0] - 2026-08-09

### Added
- **음악 커버 이미지 기본값 지원**: ID3 태그에 임베디드 커버가 없는 트랙도 음악
  토스트·정보 패널에 정적 기본 이미지(`frontend/assets/images/default-music-cover.png`)를
  표시. `has_cover`가 true일 때만 실제 커버 URL을 쓰고, 그 외에는 이 기본 이미지로
  대체(`frontend/assets/js/pages/slideshow.js`의 `trackDisplay()`)

## [2.13.0] - 2026-08-09

### Added
- **공유 앨범 슬라이드쇼 음악 정보 ID3 태그 기반 표시**: 재생 중 음악 토스트·정보
  패널이 파일명 대신 ID3 태그(제목/아티스트/앨범)와 임베디드 커버 이미지를 표시.
  `backend/services/music_tags.py`(mutagen)가 음악 파일을 1회 열람해 태그+커버
  유무를 함께 읽고, 태그가 없으면 예외 없이 파일명으로 폴백. `GET
  /music/{token}/cover?index=N` 신규 엔드포인트로 커버 이미지 서빙
- 번들 배경음악 5곡에 Pixabay 트랙 페이지의 커버 이미지를 ID3 APIC로 추가 삽입
  (오디오 데이터·재생시간 불변)

## [2.12.2] - 2026-08-09

### Changed
- **번들 배경음악 5곡에 ID3 태그 추가**: `frontend/assets/music/bundled/`의 곡들에
  제목·아티스트·앨범(`Pixabay Music`) ID3v2.3 태그를 심음. 오디오 데이터·재생
  시간은 변경 없음. ID3 태그 기반 슬라이드쇼 음악 정보 표시는 별도 세션에서 진행 예정

## [2.12.1] - 2026-08-09

### Changed
- **음악 선택 모달 — 번들 음원 상단 고정 + 출처 표시**: 기본 제공 음원 5곡이
  `DATA_DIR/music/` 스캔 순서(폴더명 알파벳순)에 좌우되지 않고 항상 "기본 제공
  음원" 섹션으로 최상단에 표시되며, 파일명 대신 "무드 — 곡명" 라벨과
  "아티스트 · Pixabay Music" 출처를 보여줌. 사용자 추가 음악은 그 아래 "내가
  추가한 음악" 섹션에 기존 방식대로 노출. 두 섹션은 하나의 스크롤 영역으로 통합
  (`frontend/assets/js/pages/admin-album-edit.js`, `frontend/assets/css/admin.css`)

## [2.12.0] - 2026-08-09

### Added
- **무드별 기본 배경음악 5곡 번들**: 잔잔한/감성적/경쾌한/따뜻한·노스탤직/웅장한
  5개 무드의 저작권 무료 음원(Pixabay Music)을 저장소에 번들
  (`frontend/assets/music/bundled/`). 서버 시작 시 `DATA_DIR/music/bundled/`로
  자동 동기화(`backend/services/bundled_music.py`의 `sync_bundled_music`)해,
  기존 음악 선택 UI·재생 경로(`/api/admin/music`, `/music/{token}`) 변경 없이
  Admin 앨범 편집 화면에서 바로 선택 가능. README·Admin 화면에 곡 크레딧
  (곡명·아티스트) 표시

## [2.11.0] - 2026-08-07

### Added
- **앨범 목록에 활성 공유 링크 수 표시**: Admin 앨범 카드 하단 메타 정보에
  활성화된(is_active + 미만료) 공유 링크 개수를 🔗 아이콘과 함께 노출
  (`backend/routers/admin_albums.py`의 `active_link_count` 서브쿼리,
  `frontend/assets/js/pages/admin-albums.js`)

## [2.10.0] - 2026-08-06

### Added
- **태그/인물 목록 필터 상태 유지**: 태그 탭에서 특정 태그의 사진을 보고 목록으로
  돌아오면 검색어·소스 필터(전체/AI/직접추가/폴더명/위치)가 초기화되던 문제,
  인물 탭에서 인물 상세를 보고 돌아오면 "추정 있는 인물만 보기" 체크박스가
  풀리던 문제를 각각 모듈 스코프 상태로 보존해 해결
  (`frontend/assets/js/pages/admin-tags.js`, `frontend/assets/js/pages/admin-people.js`)

## [2.9.0] - 2026-08-06

### Added
- **서비스 타이틀 커스터마이징**: 설정 화면 최상단에 "타이틀" 카드 신설(기본값
  "LumisShow", 편집 버튼으로 인라인 수정). 저장한 값이 Admin 로그인 화면, 상단바
  좌측, 공유 앨범 패스워드 입력 화면(신규 노출), 공유 앨범 최하단 푸터, 브라우저
  탭 제목까지 전부 일괄 반영된다(`backend/services/settings.py`의 `site_title`
  키, 공개 엔드포인트 `GET /version`이 함께 반환해 로그인 전 화면에서도 사용,
  `frontend/assets/js/router.js`에서 탭 제목 갱신 1곳 처리)

## [2.8.0] - 2026-08-06

### Added
- **AI 인식 카테고리 on/off 시 UX 개선**: v2.1.0에서 도입한 얼굴/위치/폴더명/사물 인식
  카테고리별 on/off가 지금까지는 "이후 신규 스캔만 막고 기존 DB는 그대로 조회"였는데,
  꺼진 카테고리의 기존 데이터가 화면에 계속 보여 혼란을 줄 수 있었다. 카테고리를 끄면
  DB에 데이터가 남아있어도 사진 정보 보기·검색·태그 탭에서 제외하도록 변경
  (`backend/services/photo_tags.py`의 `enabled_sources`, `admin_browse.py`/`share.py`/
  `admin_people.py` 3개 정보 패널 경로 전부 적용, `frontend/assets/js/pages/admin-tags.js`)
- **얼굴 인식 꺼짐 안내**: 인물 탭 진입 시 얼굴 인식이 꺼져 있으면 스캔/재매칭 등 컨트롤
  대신 "기능을 사용하려면 설정에서 AI 인식 카테고리에서 얼굴 인식을 켜 주세요" 안내
  문구만 표시 (`frontend/assets/js/pages/admin-people.js`)
- **AI 인식 카테고리별 DB 삭제**: 설정 화면에 카테고리별 "DB 삭제" 버튼 추가. 해당
  카테고리가 꺼진 상태에서만 활성화되고, 2차 확인 대화상자에 삭제 대상과 되돌릴 수
  없다는 경고를 표시한다. 얼굴 인식은 위치·사물과 달리 재활성화 후 자동으로 소급
  재인식되지 않는다는 점을 별도로 경고한다. 얼굴 삭제 시에도 인물 프로필(이름)은
  유지해 나중에 재스캔하면 같은 인물과 다시 매칭할 수 있게 했다
  (`backend/routers/admin_people.py`의 `POST /api/admin/ai/categories/{category}/purge`,
  `frontend/assets/js/pages/admin-settings.js`)

## [2.7.3] - 2026-08-06

### Fixed
- **Admin 라이트박스 정보 버튼 클릭 불가 문제**: 좌상단에 떠있던 [i] 아이콘이 `.lightbox-body`가
  DOM 순서상 나중에 렌더링되어 stacking에서 위를 덮어 클릭이 가로채지고 있었다. 하단 액션 바로
  이동해 "정보보기" 텍스트 버튼으로 변경했다(단축키 `i`는 그대로 유지)
  (`frontend/assets/js/lightbox.js`, `frontend/assets/css/admin.css`)

### Added
- **슬라이드쇼 정보 패널 단축키(`i`)**: 라이트박스·공유뷰어는 이미 지원하던 단축키를 슬라이드쇼에도
  등록해 정보 패널을 키보드로 토글할 수 있게 했다 (`frontend/assets/js/pages/slideshow.js`)

## [2.7.2] - 2026-08-05

### Security
- **`admin_img_session` 쿠키 SameSite를 Lax에서 Strict로 강화**: 이 쿠키로 인증하는
  `/thumb`, `/photo`, `/faces/{id}/crop`, `/api/admin/tags/xmp-export`는 전부 GET
  엔드포인트인데, Lax는 크로스사이트 최상위 GET 네비게이션에도 쿠키를 실어 보내
  로그인된 관리자가 외부 링크를 클릭하면 인증된 상태로 강제 다운로드가 발생할 수
  있었다. 이 쿠키는 항상 같은 오리진(Admin SPA)에서만 쓰여 Strict로 좁혀도 기능
  영향은 없다 (`backend/routers/auth.py`)

## [2.7.1] - 2026-08-05

### Fixed
- **확대 상태에서 마우스 가운데 버튼 줌 리셋 안 되는 문제**: v2.6.0에서 라이트박스·공유뷰어 제스처를
  `photo-zoom-viewer.js` 공용 모듈로 통합하며 pointerdown 핸들러가 마우스 버튼 구분 없이
  zoom>1이면 preventDefault·setPointerCapture를 걸었고, 이로 인해 뒤이어 발생해야 할
  mousedown(가운데 버튼 줌 리셋 핸들러)이 억제되어 라이트박스·공유뷰어 양쪽 모두 확대 중
  가운데 버튼 리셋이 동작하지 않았다. 마우스 비-좌클릭 버튼을 pointerdown 팬 로직에서 제외
  (`frontend/assets/js/photo-zoom-viewer.js`)

## [2.7.0] - 2026-08-05

### Added
- **수동 태그 자유 텍스트 입력**: 태그 추가 모달의 고정 어휘(vocab) 드롭다운을 텍스트 입력창으로
  바꿔 목록에 없는 태그도 직접 입력할 수 있게 했다. 기존 vocab과 실제 사용 중인 태그를 합쳐
  자동완성 제안으로 보여준다. 백엔드는 trim/빈 값/50자 초과/`/` 포함(다른 라우트에서 태그가
  경로 파라미터로도 쓰여 조회·삭제·이름변경이 막히는 문제 방지)만 검증하고 나머지는 자유롭게 허용
  (`backend/routers/admin_ai_tags.py`, `frontend/assets/js/tag-modal.js`)
- **여러 장 사진에 태그 일괄 적용/삭제**: 사진 탐색·태그 메뉴의 사진 그리드에 다중선택(체크박스)을
  추가해 선택한 여러 장에 한 번에 태그를 추가할 수 있다. 태그 메뉴의 "직접추가" 필터에서는 선택한
  사진에서 태그를 일괄 삭제하는 기능도 제공한다(AI/폴더명 태그의 개별 삭제는 기존과 동일하게 유지).
  순차 API 호출이라 일부 실패해도 나머지는 계속 진행하고 실패 개수와 사유를 알려준다
  (`frontend/assets/js/pages/admin-tags.js`, `frontend/assets/js/pages/admin-browse.js`)

## [2.6.0] - 2026-08-05

### Changed
- **전체화면 사진 뷰어 제스처를 공용 모듈로 통합**: Admin 라이트박스와 공유뷰어가 줌/팬/핀치/스와이프를
  각자 따로 구현해 최대 줌(4x/6x)·더블클릭 배율(2x/2.5x) 등 동작이 미묘하게 달랐다.
  `photo-zoom-viewer.js` 공용 모듈로 통합해 Pointer Events로 마우스·터치 제스처를 함께 처리하고,
  최대 줌 6x·더블클릭 2x로 통일. 스와이프 시 이전/다음 사진이 옆에서 따라오는 peek 슬라이드
  애니메이션과 마우스 가운데 버튼 줌 리셋을 라이트박스에도 적용. 라이트박스의 배경 클릭 닫기는
  제거(양쪽 다 ✕/ESC만 닫힘), +/-/0 줌 단축키와 i 정보 단축키를 라이트박스에 추가
  (`frontend/assets/js/photo-zoom-viewer.js`, `frontend/assets/js/lightbox.js`,
  `frontend/assets/js/pages/album-view.js`, `frontend/assets/css/admin.css`)

## [2.5.0] - 2026-08-05

### Changed
- **AI 워커 얼굴 인식 실패 재시도 주기 30일로 연장 + 재시도 동기화**: 손상된
  사진 파일(`broken data stream`, `UnidentifiedImageError` 등)은 원본을
  교체하지 않는 한 재시도해도 계속 실패하는데, 기존 7일 주기로는 재시도가
  너무 잦았다. 주기를 30일로 늘리고, 실패 시점이 제각각인 여러 파일이 각자
  다른 날 재시도되며 에러 알림이 산발적으로 발생하지 않도록 가장 오래된
  error가 주기를 넘기면 나머지 error 사진도 함께 재시도하도록 변경(한 번
  같이 재시도되면 이후 주기도 자동으로 계속 동기화됨) (`ai_worker/scanner.py`)

## [2.4.1] - 2026-08-05

### Added
- **Admin 라이트박스 정보 패널에 파일 경로 표시**: EXIF 정보 확인 시 사진이 어느
  폴더에 있는지 알 수 없어 불편하다는 피드백에 따라, Filename 아래 소속 디렉토리
  경로를 표시. 라이트박스는 EXIF 조회 시점에 파일 경로를 이미 알고 있어 백엔드
  변경 없이 프론트에서만 처리 (`frontend/assets/js/lightbox.js`)

## [2.4.0] - 2026-08-05

### Added
- **위치 태그 도시명 한글 번역**: GPS 역지오코딩(`reverse_geocoder`, GeoNames 기반)이
  주는 로마자 도시명(예: `Santyoku`, `Gaigeturi`)이 검색·직관성을 해친다는 피드백에
  따라, 국가명과 동일한 방식(`geocoder._CITY_NAMES_KO` 정적 매핑)으로 도시명도
  한글로 번역(매핑에 없는 지명은 로마자 그대로 폴백). 국내 47개 + 해외(베트남·가나·
  일본) 8개 지명을 실사용 데이터 기준으로 큐레이션. 이미 분석된 사진에 소급
  반영하기 위한 `location_tag_reset` 배치도 추가 — 재지오코딩 없이 DB 값만
  재번역해 가벼움. CLI(`python -m ai_worker.main location-tag-reset`) 또는
  Admin '태그' 화면 "위치 태그 한글 재번역" 버튼으로 트리거, 완료 시 Discord 알림
  (`ai_worker/geocoder.py`, `ai_worker/main.py`, `ai_worker/daemon.py`,
  `ai_worker/notify.py`, `backend/routers/admin_people.py`,
  `frontend/assets/js/pages/admin-tags.js`)

## [2.3.1] - 2026-08-04

### Fixed
- **얼굴 인식 실패 시 로그 없음 + 영구 재시도 안 되는 문제**: `analyze_and_store()`가
  얼굴 검출 실패를 예외를 삼킨 채 `status='error'`로만 기록해 원인 파악을 위해
  `ai.db`를 직접 SELECT해야 했고, `pending_photos()`가 mtime 일치 여부로만
  재분석 대상을 골라 파일이 안 바뀌면 실패한 사진이 영원히 재시도되지 않았음.
  실패 시 `_logger.exception`으로 트레이스백을 로그에 남기고, `status='error'`
  사진은 7일(`_ERROR_RETRY_DAYS`) 넘게 지나면 mtime 불변이어도 재분석 대상에
  포함하도록 수정. 매 스캔 무조건 재시도하지 않는 이유는 지속 실패 파일이 있을
  때 `run_scan()`이 매일 밤 모델(buffalo_l/CLIP)을 로딩하고 "증분 없으면 스킵"
  게이팅을 무력화해 Discord 알림이 매번 발송되는 걸 막기 위함
  (`ai_worker/pipeline.py`, `ai_worker/scanner.py`)
- **GPS EXIF 깨진 값(분모 0)으로 역지오코딩 반복 실패**: Pillow `IFDRational`이
  EXIF 분수 필드의 분모가 0이면 예외 없이 `nan`을 반환해, 위경도가 그대로
  `geocoder.reverse_geocode()` → `cKDTree.query()`로 들어가 `ValueError`가
  반복 발생하며 위치 태그도 붙지 않았음. `_extract_gps()`가 계산된 위경도를
  `math.isfinite()`로 검증 후 아니면 `None`을 반환하도록 수정 (`ai_worker/pipeline.py`)

## [2.3.0] - 2026-08-04

### Added
- **Admin 라이트박스 사진 정보(i 버튼)**: Admin 화면에서 사진을 전체크기로 보는
  모든 지점(사진 탐색기·앨범 편집·태그 화면·인물 상세·인물 사진)이 공용으로
  쓰는 라이트박스(`lightbox.js`)에 i 버튼을 추가해 EXIF와 태그를 확인할 수
  있게 함. 슬라이드쇼의 정보 패널과 달리 라이트박스는 사진 경로만 들고 열리므로,
  새 `GET /api/admin/photo-info`로 사진 1장분의 EXIF·태그를 그때그때 조회.
  Admin 전용 화면이라 인물·위치 태그도 함께 노출 (`backend/routers/admin_browse.py`,
  `backend/models/schemas.py`, `frontend/assets/js/lightbox.js`,
  `frontend/assets/css/admin.css`)

## [2.2.0] - 2026-08-04

### Added
- **폴더 태그(Kiwi) 전체 재계산 Admin 버튼**: `path_tag_done` 플래그 도입(v2.1.1)
  이후 한 번 시도한 사진은 커버리지 대상에서 영구히 빠져, Kiwi 사전/명사 추출
  로직이 바뀌어도 기존 태그를 다시 계산할 방법이 없었음. Admin '태그' 화면에
  "폴더 태그 재계산" 버튼 추가 — `photo_tags(source='path')` 전체 삭제 +
  `path_tag_done` 전체 리셋 후 기존 커버리지 로직을 재실행. `tag_backfill`과
  동일한 일반 잡 생성·중복방지 경로(`POST /api/admin/ai/jobs` `{"type":
  "path_tag_reset"}`)로 처리하며 완료 시 Discord 알림 발송
  (`ai_worker/main.py`, `ai_worker/daemon.py`, `ai_worker/notify.py`,
  `backend/routers/admin_people.py`, `frontend/assets/js/pages/admin-tags.js`)

## [2.1.1] - 2026-08-04

### Fixed
- **폴더명(Kiwi) 태깅, 명사 없는 폴더 사진이 매 스캔 재시도되던 문제 수정**: 순수
  영문/숫자 폴더명처럼 명사가 하나도 안 나오는 사진은 태그 행이 생기지 않아
  커버리지 조건(`photo_tags`에 `source='path'` 행 존재 여부)을 계속 만족시켜
  매 스캔 재시도되고, 그때마다 Discord 알림의 `path_tagged` 건수가 실제 신규
  작업 없이 부풀려졌음. `photos_analyzed`에 `path_tag_done` 플래그를 추가해
  시도 여부를 직접 기록하는 방식으로 전환 — 결과(태그 생성 여부)와 무관하게
  한 번 시도한 사진은 재시도하지 않음. 경로복구 승인(rename) 시에는 플래그를
  0으로 되돌려 새 폴더명으로 다시 태깅되게 함 (`ai_worker/db.py`,
  `ai_worker/scanner.py`, `backend/models/ai_database.py`,
  `backend/routers/admin_people.py`)
  - **배포 직후 1회성 안내**: 기존 DB는 마이그레이션으로 전체 사진의
    `path_tag_done`이 0부터 시작하므로, 배포 후 첫 스캔은 그동안 재시도되며
    쌓여있던 전체 대상을 다시 훑어 큰 `path_tagged` 수치(수만 건)와 함께 알림이
    한 번 발송됨 — 정상. 그 다음 날 스캔부터 신규 사진이 없으면 알림이 오지
    않는 것으로 정상 동작을 확인할 수 있음.
  - **동작 변경 참고**: `source='path'` 태그를 Admin이 수동으로 지운 경우, 과거엔
    다음 스캔이 다시 채웠으나 이제는 `path_tag_done=1`로 남아있어 재생성되지
    않음(의도된 변경).

## [2.1.0] - 2026-08-04

### Added
- **AI 태그(CLIP) 인식 민감도 Admin 설정**: `AI_TAG_THRESHOLD` 환경변수(컨테이너
  재기동 필요) 없이 Admin 설정 화면에서 CLIP 태그 부여 임계값을 조정 가능
  (`GET/PATCH /api/admin/ai/settings`의 `tag_threshold`)
- **AI 인식 카테고리별(얼굴/위치/폴더명/사물) on/off 설정**: 4개 카테고리를
  각각 독립적으로 켜고 끌 수 있는 설정 추가. 끄면 다음 스캔부터 새로 생성하지
  않되 기존 데이터는 삭제되지 않고 그대로 유지되며, 위치·사물은 다시 켠 뒤
  기존 "AI 태그 재계산"으로 밀린 분량을 소급 반영할 수 있음(얼굴 인식은 대칭
  메커니즘이 없어 꺼져 있던 동안 스캔된 사진은 재스캔 전까지 인식되지 않는
  제한을 가짐) (`ai_worker/pipeline.py`, `ai_worker/main.py`)

## [2.0.2] - 2026-08-03

### Fixed
- **전체 사진 보기(라이트박스) 정보 패널에 태그 정보 누락**: EXIF만 표시되고
  인물/위치/태그/폴더명/직접 추가 태그가 표시되지 않던 문제 수정. 슬라이드쇼
  정보 패널과 동일하게 태그 섹션 추가 (`frontend/assets/js/pages/album-view.js`)

### Changed
- **정보 패널 EXIF/태그 영역 시각 분리**: 전체 사진 보기·슬라이드쇼 양쪽
  정보 패널에서 EXIF와 태그를 구분선으로 나눠 표시 — 슬라이드쇼의 EXIF/음악
  구분과 동일한 패턴 적용 (`frontend/assets/js/pages/album-view.js`,
  `frontend/assets/js/pages/slideshow.js`)

## [2.0.1] - 2026-08-03

### Fixed
- **AI 스캔 결과 Discord 알림, 증분 있을 때만 발송**: 매 스캔 완료 시 무조건
  전송해 증분 없는 날도 pending 누적 총건수가 그대로 오던 소음 문제 수정 —
  이번 스캔의 신규 처리량이나 경로 변경·삭제 승인 대기 누적치가 직전 발송
  시점과 달라졌을 때만 발송. 얼굴 인식과 함께 처리되는 GPS 위치·CLIP AI
  태그·폴더명 태깅 결과도 알림에 함께 노출 (`ai_worker/notify.py`)

## [2.0.0] - 2026-08-02

AI 태그/위치/장면 인식 관리 기능. 사진 속 사물·장면을 CLIP zero-shot으로 자동
인식해 태그를 붙이고, GPS·폴더명 기반 위치·이벤트 태그를 자동 기록하며,
Admin이 태그를 관리하고 슬라이드쇼 정보 패널·사진 탐색 검색·XMP 사이드카
내보내기에서 활용할 수 있게 되었다.

### Added
- **CLIP 기반 사물·장면 자동 태깅**: `clip-vit-base-patch32`(ONNX, zero-shot
  멀티라벨)로 사진 분석 시마다 82개 수동 큐레이션 어휘(사람/구도·동물·음식·
  탈것·생활용품·자연/실외·실내장소·날씨·이벤트·액티비티 10개 카테고리) 중
  임계값 이상 매칭되는 태그를 자동 부여. 이미지 임베딩을 `photo_embeddings`에
  캐시해 어휘·임계값이 바뀌어도 전체 재분석 없이 벡터 비교만으로 소급 적용
  가능 (`ai_worker/tagger.py`, `ai_worker/tag_vocab.py`)
- **GPS 위치 자동 태깅**: EXIF GPS를 오프라인 리버스 지오코딩(`reverse_geocoder`)
  으로 도시/국가로 변환해 `photo_locations`에 기록 (`ai_worker/geocoder.py`)
- **폴더명 기반 자유 텍스트 태깅**: 상위 폴더명을 한국어 형태소분석기(Kiwi,
  오프라인)로 분석해 지명·활동명 등을 자동 태깅 — GPS 유무와 무관하게 항상
  실행돼 GPS 있는 사진도 폴더명의 이벤트 정보(생일파티·가족여행 등)가 함께
  붙는다 (`ai_worker/scanner.py`)
- **기존 사진 소급 재계산(`tag-backfill`)**: CLI
  (`python -m ai_worker.main tag-backfill`)와 Admin 설정 화면 버튼으로 이미
  분석된 사진 전체에 태그·위치·폴더명 태깅을 소급 적용 — 어휘/임계값 변경
  후에도 기존 사진에 반영 가능 (`ai_worker/main.py`)
- **Admin 태그 관리 화면** (`/admin/tags`): 태그 목록(source별 필터·검색),
  태그별 사진 그리드, 개별 삭제, 이름 일괄 변경, 수동 태그 추가(자유 텍스트가
  아닌 어휘 목록 중 선택) (`admin_ai_tags.py`, `admin-tags.js`)
- **정보 패널(i 버튼) 태그 노출**: 슬라이드쇼 EXIF 정보 패널에 인물·위치·태그·
  폴더명·직접 추가 태그를 표시 — 공유 링크는 AI/폴더명/수동 태그만, Admin은
  위치·확정 인물명까지 전체 노출(오매칭·프라이버시 이슈로 얼굴 인식과 동일한
  경계 유지) (`services/photo_tags.py`, `slideshow.js`)
- **XMP 사이드카 export**: Admin 설정 화면에서 태그·위치·확정 인물 전체를
  사진별 `.xmp` 사이드카로 묶어 원본과 동일한 폴더 구조의 ZIP으로 스트리밍
  다운로드 — Lightroom·digiKam 등 외부 툴이 읽을 수 있는 XMP/MWG 표준 필드
  (`dc:subject`/`mwg-rs:RegionList`/`Iptc4xmpExt:LocationCreated`)로 매핑,
  원본 사진은 절대 수정하지 않음 (`services/xmp_export.py`)
- **사진 탐색 검색에 태그 매칭 추가**: 파일명 검색에 더해 태그(인물·위치·AI·
  수동·폴더명 전체)로도 검색 가능 (`admin_browse.py`)
- **인물 라벨 ↔ 태그 자동 동기화**: 얼굴 인물 확정/이름 변경/삭제 시
  `photo_tags(source='person')`가 자동으로 함께 갱신 (`admin_people.py`)
- **`AI_TAG_THRESHOLD` 환경변수 추가**: CLIP 태그 부여 cosine 임계값(기본
  `0.24`), Admin 설정 화면에서도 조정 가능

## [1.16.1] - 2026-08-02

### Added
- **전체 사진 보기(공유 뷰어) 스와이프에 드래그 추적 슬라이드 효과 추가**: 손가락
  이동에 맞춰 이전/다음 사진이 실시간으로 따라 들어오는 캐러셀 효과. 임계값을
  넘겨 손을 떼면 끝까지 슬라이드 후 전환, 못 넘기면 원위치로 스냅백(0.25s).
  슬라이드쇼는 대상에서 제외(기존 탭존 유지), admin 라이트박스는 레이아웃
  구조(shrink-wrap) 문제로 이번엔 제외 (`album-view.js`, `touch-gesture.js`,
  `touch-gesture.test.js`, `viewer.css`)

### Fixed
- **가장자리(28px) 시작 드래그가 끝까지 드래그해도 항상 스냅백되던 문제**:
  가장자리 판정을 touchend 시점이 아닌 touchstart 시점에 하도록 변경 —
  실기기 브라우저 테스트 중 발견 (`album-view.js`)

## [1.16.0] - 2026-08-02

### Added
- **슬라이드쇼/전체 사진 보기/라이트박스에 좌우 스와이프 제스처 추가**: 화면 가장자리
  (~28px) 시작 터치는 스와이프 후보에서 제외해 iOS 뒤로가기 시스템 제스처와 충돌하지
  않도록 함. 기존 탭존(슬라이드쇼)·버튼 내비게이션은 그대로 유지. 판정 로직은
  `touch-gesture.js`로 분리해 세 화면이 공유하고 node 내장 테스트러너로 unit test 작성
  (`slideshow.js`, `album-view.js`, `lightbox.js`, `touch-gesture.js`,
  `touch-gesture.test.js`, `viewer.css`, `frontend/package.json`)

### Fixed
- **iPhone에서 슬라이드쇼 진입 시 툴바 자동 숨김·전체화면 버튼이 동작하지 않던 문제**:
  `requestFullscreen?.().then(...)` 체인이 Fullscreen API 미지원 브라우저(iPhone Safari)에서
  TypeError를 던져 이후 UI 초기화 코드가 스킵되던 버그 수정 (`slideshow.js`)

## [1.15.4] - 2026-07-29

### Changed
- **화면 전반 숫자 표시에 1000단위 구분 기호 적용**: 인물 목록/상세의 확정·추정 얼굴 수를
  포함해 앨범/폴더/사진 수, 조회수, 선택 개수, 슬라이드쇼·라이트박스·공유뷰어 인덱스,
  경로 복구·파일정리 대기 건수, 앨범에 사진 추가 결과 등 자릿수가 커질 수 있는 숫자 표시를
  `toLocaleString()`으로 통일. 음악 트랙 수·숨김 경로 수처럼 항상 작은 값만 갖는 카운터는
  제외 (`admin-people.js`, `admin-person-detail.js`, `admin-person-photos.js`,
  `admin-albums.js`, `admin-album-edit.js`, `admin-browse.js`, `album-view.js`,
  `slideshow.js`, `lightbox.js`)

## [1.15.3] - 2026-07-29

### Changed
- **Admin 인물 페이지 AI 요약 문구 개편**: "분석 사진 x장 · 얼굴 x개 · 라벨 x개"에서
  "인물 x명, 얼굴 x개(미분류 얼굴 x개), 분석 사진 x장(오류 x장)" 형식으로 변경 —
  인물 수와 미분류(라벨·매칭 모두 없는) 얼굴 수를 바로 확인 가능. `/api/admin/ai/status`
  응답에 `unassigned` 필드 추가 (`admin_people.py`, `admin-people.js`)

## [1.15.2] - 2026-07-29

### Changed
- **"간단히 보기"를 기억되는 설정에서 1회성 체크박스로 변경**: 공유 뷰어 화면의
  버튼 순서를 [슬라이드쇼] [설정] [ ] 간단히 보기로 재배치하고 버튼 대신
  체크박스로 바꿈. `localStorage` 저장을 제거해 뷰 화면에 진입할 때마다 항상
  언체크 상태로 시작하도록 변경 — 체크 상태는 슬라이드쇼 진입 시 `?lp=1` URL
  파라미터로만 1회 전달(기존 `?i=` 시작 인덱스 파라미터와 공존)
  (`album-view.js`, `slideshow.js`, `slideshow-config.js`, `viewer.css`)

## [1.15.1] - 2026-07-29

### Changed
- **슬라이드쇼 저사양 모드 토글 위치를 슬라이드쇼 내부에서 뷰어 화면으로 이동**: 리모컨
  (방향키)만 있는 TV에서 슬라이드쇼 재생 도중 토글에 접근하기 번거로웠던 문제 —
  공유 뷰어(`/s/{token}`) 화면의 "슬라이드쇼" 버튼 옆에 "간단히 보기" 버튼을 두어
  시작 전에 미리 켜두는 방식으로 변경. 기기별 `localStorage` 저장은 그대로 유지
  (`album-view.js`, `slideshow.js`, `slideshow-config.js`)

## [1.15.0] - 2026-07-29

### Added
- **슬라이드쇼 저사양 모드**: 옛날/저사양 TV 등에서 재생이 버벅이는 문제 대응. 툴바에
  "저사양" 토글 추가(기기별 `localStorage` 저장, 앨범·공유링크와 무관) — 평소엔 원본
  화질을 유지하고, 켰을 때만 원본 대신 large(1920×1080) 썸네일을 쓰고 Ken Burns 확대
  애니메이션·전체화면 blur 배경 레이어를 생략하며 전환 효과를 fade로 고정
  (`slideshow.js`, `slideshow.css`, `thumbnail.py`, `schemas.py`, `share.py`,
  `admin_people.py`, `admin_browse.py`)

### Fixed
- **방향키 입력 시 슬라이드쇼 툴바 자동 숨김 타이머가 리셋되지 않던 문제**: 리모컨
  (방향키)만 쓰는 기기에서 3초 후 툴바가 숨으면 다시 꺼낼 방법이 없어 저사양 버튼
  등에 접근할 수 없었다. `handleKeydown`에서 `showUI()` 호출 추가
- **large 썸네일 생성 시 원본 대비 크기차가 작으면 JPEG draft가 축소 스케일을 못
  찾아 풀해상도로 디코딩되던 문제**: draft 마진을 large만 1배로 낮춰 수정
  (실측 3배 개선)

## [1.14.0] - 2026-07-25

### Added
- **AI 스캔/재매칭 완료 Discord webhook 알림**: daemon 모드(jobs 트리거 + 야간 자동 스캔)에서
  scan/rematch 완료 후 `AI_DISCORD_WEBHOOK_URL`로 결과 요약(사진/얼굴/에러 수, 경로 변경·삭제
  승인 대기 총 건수, `BASE_URL` 기반 `/admin/people` 링크)을 전송. 미설정 시 알림 스킵,
  전송 실패는 최대 3회 재시도 후 로그만 남기고 daemon 루프에 영향 없음. urllib 기본
  User-Agent를 Discord(Cloudflare)가 403으로 차단하는 문제를 발견해 커스텀 헤더로 우회
  (`ai_worker/notify.py`, `ai_worker/config.py`, `ai_worker/main.py`, `ai_worker/daemon.py`)

## [1.13.0] - 2026-07-24

### Added
- **날짜별 보기 스크롤 위치 인디케이터**: 인물 전체 사진 / 사진 탐색기 / 앨범 편집,
  세 화면의 날짜별 보기(📅)에서 스크롤 중 우측에 년/월/일 배지가 잠깐 나타났다
  사라짐(스크롤 정지 후 자동 페이드아웃). 배지 세로 위치도 전체 스크롤 진행률에
  비례해 이동. 공통 로직은 `date-scroll-indicator.js`로 분리해 세 화면에서 재사용

## [1.12.0] - 2026-07-24

### Added
- **인물 커버 사진 직접 지정**: 인물 상세의 확정 얼굴 그리드/리스트에서 ★ 버튼으로
  커버 사진을 지정할 수 있음(`PUT /api/admin/people/{id}/cover`). 지정하지 않으면
  기존처럼 가장 먼저 확정된 얼굴을 자동 커버로 사용. `persons.cover_face_id`는
  FK 없이 조회 시점에 유효성(그 얼굴이 여전히 이 인물의 확정 얼굴인지)을 검사해
  재라벨/라벨 해제 시 자동으로 원래 방식(자동 선택)으로 되돌아감

### Changed
- **인물 상세 얼굴 그리드 터치 사용성 개선**: 얼굴 타일 크기를 일반 앨범 사진
  그리드와 동일하게 확대(90px→120px). 확정 해제 버튼이 `opacity:0`으로만
  숨겨져 있어 터치 기기에서 이미지를 탭하려다 보이지 않는 버튼이 눌리던 문제를
  `display:none`(앨범 커버 버튼과 동일 패턴)으로 교체해 수정

## [1.11.3] - 2026-07-23

### Fixed
- **`repair-paths` 재실행 시 이미 대기 중인 제안이 응답에서 누락되던 문제**:
  `old_path` UNIQUE 충돌로 `INSERT OR IGNORE`가 조용히 무시되면 `proposed`
  배열에서 빠져 admin이 "못 찾았다"로 오해할 수 있었다. 충돌 시 기존 pending
  row를 조회해 실제 대기 중인 id/new_path로 응답에 포함하도록 수정

## [1.11.2] - 2026-07-23

### Fixed
- **경로 복구 제안 거부(reject) 시 되돌릴 수 없던 문제**: `status='rejected'`로
  영구 고정하던 방식이 `old_path` UNIQUE 제약에 걸려 다음 스캔이 같은 rename을
  재제안하지 못했고, 그 사이 `new_path`가 일반 스캔으로 별개 사진 분석돼버리면
  승인 시도해도 409로 영영 되돌릴 수 없었다. 거부를 dismiss(제안 row 삭제)로
  바꿔 재스캔 시 조건이 같으면 다시 제안되거나, `new_path`가 이미 소진됐으면
  `old_path`가 not_found(orphan-cleanup 제안)로 재분류되도록 수정. 과거 버전에서
  쌓인 rejected row 정리 마이그레이션 포함

## [1.11.1] - 2026-07-23

### Fixed
- **`photo_meta_cache` mtime 무효화 부재로 EXIF 수정 후에도 옛 날짜가 표시되던 문제**:
  외부 앱으로 사진 촬영일(EXIF)을 고쳐도 캐시가 파일 변경을 감지하지 못해 옛 날짜가
  영구히 반환되던 버그 수정. `photo_meta_cache`에 `mtime` 컬럼을 추가하고
  `load_photo_meta()`가 캐시 히트여도 파일의 현재 mtime을 비교해 다르면 다시 읽도록
  변경(`cache_version` 3→4, 기존 캐시 전체 재구축)
- **`dated_admin_client` 테스트 픽스처의 DB 커넥션 풀 미정리**: `close_db_pool()` 누락으로
  해당 픽스처 기반 테스트를 단독 실행하면 프로세스가 종료되지 않던 문제 수정

### Added
- **완전 삭제(orphan) 정리 승인 대기열**: 파일이 실제로 사라졌고 rename 후보도 없는
  사진을 `pending_orphan_cleanups` 큐에 제안(야간 자동 스캔/수동 스캔 공통), admin이
  Admin People 화면(또는 `GET/POST /api/admin/people/orphan-cleanups*`)에서 승인해야
  `ai.db`(`photos_analyzed`/`faces`, FK로 `face_labels`/`face_matches`도 연쇄 삭제)와
  `photo_meta_cache`를 함께 정리 — EXIF 수정 시 원본 대신 별도 사본을 만들었다가
  지우는 경우처럼 중복 데이터가 남는 상황을 위해 추가

## [1.11.0] - 2026-07-22

### Added
- **AI 얼굴 인식 경로 rename/move 자동 복구 (admin 승인 큐)**: 사진 폴더명 변경 시
  `ai.db`의 `photos_analyzed`/`faces` 경로가 orphan(404)으로 남고 라벨이 소실되던
  문제 해결. 야간 자동 스캔(`ai_worker/scanner.py`)과 수동 스캔
  (`POST /api/admin/people/repair-paths`) 둘 다 basename 1:1 유일 매칭 후보를
  `pending_path_repairs` 큐에 제안만 쌓고, admin이 Admin People 화면(또는
  `GET/POST /api/admin/people/path-repairs*`)에서 승인해야 실제 반영됨(face_id
  유지 → 기존 확정 라벨 보존). 승인 대기 중인 사진은 재분석 대상에서 제외

## [1.10.1] - 2026-07-22

### Fixed
- **미분류 얼굴 페이지에 인물 목록 복귀 버튼 누락**: 무시된 얼굴 페이지와
  동일하게 "← 인물 목록" 버튼 추가 (`admin-people.js`)

## [1.10.0] - 2026-07-22

### Added
- **무시된 얼굴 재검토 기능**: 인물 상세 페이지에서 "무시 얼굴에서 이 인물 찾기"
  버튼으로 해당 인물 1명만 대상으로 '무시' 라벨된 얼굴을 재매칭하는 비동기
  job(`review_ignored`)을 큐잉. 기존 전체 재매칭(`rematch_all`)과 분리된 경량
  경로로, 후보는 확정(기존 batch-label API 재사용)/숨기기(클라이언트 로컬)로
  처리 (`ai_worker/matcher.py`의 `match_ignored_for_person()`, 신규 API
  `GET /people/{id}/ignored-candidates`, `GET /people/{id}/review-ignored-status`,
  `admin-person-detail.js`)

## [1.9.2] - 2026-07-19

### Added
- **미분류/무시된 얼굴 페이지 전체 선택·해제 버튼**: 인물 상세의 추정 얼굴
  선택 UX와 동일한 패턴으로, 다수 얼굴을 한 번에 선택·해제할 수 있도록 추가
  (`admin-people.js`)

## [1.9.1] - 2026-07-19

### Added
- **`GET /api/admin/people/{id}/slideshow-meta`**: 인물 슬라이드쇼 진입 화면(loadAlbum)용
  메타 엔드포인트 — 앨범이 없는 인물 슬라이드쇼도 앨범 슬라이드쇼와 동일한
  `build_slideshow_defaults()` 규칙(전역 설정 폴백)을 공유 (`admin_people.py`)

### Fixed
- **인물 사진(photos-detail) 페이지네이션 밀림 방지**: 슬라이드쇼 재생 중 다른 얼굴이
  라벨링/재매칭돼도 이미 시작된 세션의 페이지 순서·개수가 흔들리지 않도록 snapshot
  토큰 도입 — 최초 요청에서 photo_path 전체 순서를 고정해 이후 페이지는 그 목록만
  슬라이스 (`admin_people.py`, `slideshow.js`, `admin-person-photos.js`)
- **slideshow_defaults 조립 로직 이중화 제거**: `share.py`(서버)와
  `slideshow.js renderPersonSlideshow`(클라이언트)에 각각 있던 필드 매핑·폴백 로직을
  `build_slideshow_defaults()` 공용 헬퍼(`schemas.py`)로 통합

### Changed
- **라우터 간 크로스 임포트 정리**: `admin_browse`/`admin_albums`/`admin_people`/
  `share`/`media` 라우터가 서로를 직접 import하던 헬퍼(`load_photo_meta`,
  `_admin_image_auth`, `resolve_abs`/`assert_within_photo_root`, `get_settings`)를
  `backend/services/photo_meta.py`, `paths.py`, `settings.py`, `auth.py`로 이동 —
  라우터는 서비스 레이어만 참조하도록 구조 정리 (동작 변경 없음)

## [1.9.0] - 2026-07-19

### Added
- **비-root 컨테이너 실행 지원 (PUID/PGID)**: 환경변수 `PUID`/`PGID` 설정 시
  entrypoint(`docker/entrypoint.sh`)가 `DATA_DIR` 소유권을 맞추고 `setpriv`로
  권한을 하강시켜 실행 — 미설정 시 기존 root 동작 100% 유지(하위 호환).
  `lumisshow`/`lumisshow-ai`는 `/data`를 공유하므로 두 서비스에 동일한 값을
  사용해야 함 (`docker/Dockerfile`, `docker/Dockerfile.ai`, `docker/CLAUDE.md`)

## [1.8.7] - 2026-07-17

### Changed
- **얼굴 무시 해제 batch API를 POST로 전환**: `DELETE /api/admin/faces/batch-unlabel`
  → `POST /api/admin/faces/batch-unlabel` (프록시 이식성 위해 body가 있는
  DELETE 제거, `admin_people.py`, `admin-people.js`, `admin-person-detail.js`)

### Fixed
- **persons.name 중복 방지**: UNIQUE 인덱스 추가 + create/rename 양쪽에 애플리케이션
  레벨 중복 검사 — 기존에는 create만 검사(레이스 있음), rename은 검사 자체 없었음.
  인덱스 생성이 기존 중복 데이터로 실패해도 애플리케이션 레벨 체크가 계속 동작하도록
  이중 방어 (`ai_database.py`, `ai_worker/db.py`, `admin_people.py`)
- **batch-label/unlabel face_ids 무제한 입력 방지**: `Field(max_length=5000)` 추가
  (`schemas.py`)
- **share_spa 광역 예외 무음 처리 개선**: OG 메타 조회 실패 시 로그 기록 (`main.py`)
- **불필요한 Docker 빌드 의존성 제거**: Pillow는 manylinux wheel을 사용해
  `libjpeg-dev`/`libpng-dev` 헤더가 불필요 — 이미지 크기 절감 (`Dockerfile`)

## [1.8.6] - 2026-07-17

### Security
- **공유 링크 브루트포스 잠금 IP+token 복합 키**: token 단독 키였던 잠금을
  IP+token 조합으로 변경 — 공격자가 일부러 5회 오입력해 정상 사용자까지
  15분 차단시키는 것을 방지 (관리자 로그인 잠금과 동일한 패턴, `share.py`)
- **PHOTO_ROOT 경로 이탈 차단 (og-image, ZIP 다운로드)**: `media.py`와
  동일한 realpath 기반 containment 검사를 추가 — `album_photos.file_path`가
  상대경로 이탈("..")을 포함해도 서빙 단계에서 403 (`share.py`)
- **공유 토큰 enumeration 방어**: 토큰 존재 여부를 노출하는 공개 GET
  (`/api/share/{token}`, `/og-image`)에 속도 제한 추가. 존재하지 않는
  토큰(404) 조회만 카운트하며 정상 조회(200)는 잠금에 영향 없음 —
  IP당 60초 30회 초과 시 429 (`share.py`)
- **응답 보안 헤더 추가**: `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy` 미들웨어 (`main.py`)
- **bcrypt 논블로킹화**: 관리자 로그인 검증, 공유 링크 패스워드 검증·해싱
  총 4곳의 동기 bcrypt 호출을 `asyncio.to_thread`로 감싸 이벤트 루프
  블로킹 방지 (`auth.py`, `share.py`, `admin_links.py`)

## [1.8.5] - 2026-07-17

### Changed
- **SQLite 커넥션 풀 도입**: `/api/*` 요청마다 새 연결을 열고 PRAGMA를 3회
  재실행하던 것을 크기 5(`DB_POOL_SIZE`) 커넥션 풀로 교체 — 연결·PRAGMA 오버헤드를
  앱 시작 시점으로 옮김. 반환 시 `rollback()`을 호출해 커밋 전 예외로 남은
  미완료 트랜잭션이 다음 요청으로 전파되지 않도록 함 (`database.py`)
- **공유 뷰어 사진 목록 페이지네이션 SQL화**: `/api/share/{token}/photos`가
  전체 사진을 fetch한 뒤 Python에서 슬라이싱하던 것을 `COUNT(*)` +
  `LIMIT/OFFSET` 쿼리로 교체 (`share.py`)
- **썸네일 응답 캐시 헤더 추가**: 썸네일은 사실상 불변이므로 매 요청 재검증을
  피하도록 `Cache-Control: private, max-age=86400` 추가 (`media.py`, `admin_browse.py`)
- **rematch_all 임베딩 배치 스트리밍**: 미분류 얼굴 전체 임베딩을 `fetchall()`로
  한 번에 적재하던 것을 `fetchmany(2000)` 배치 스트리밍으로 교체 — 얼굴 수가
  많을수록 커지던 피크 메모리 사용량 절감 (`ai_worker/matcher.py`)

## [1.8.4] - 2026-07-17

### Changed
- **인물 화면 리스트 보기 썸네일 확대**: 인물 상세/전체 사진 리스트 보기의
  얼굴·사진 썸네일을 40px → 72px로 확대해 식별이 쉽도록 개선 (`admin.css`)
- **similar_faces 후보 임베딩 LIMIT 적용**: 미분류 얼굴이 매우 많을 경우 매
  요청마다 전체를 np.stack하던 메모리 부담을 `SIMILAR_FACES_CANDIDATE_LIMIT`
  (기본 20000)로 제한. 후보에서 밀려나도 기준 얼굴 자신은 항상 결과 최상단에
  포함되도록 별도 보장 (`admin_people.py`)

### Fixed
- **`_thumb_locks` dict 무한 증가 방지**: 썸네일 생성 완료 후 경로별 락을 dict에서
  제거 — 장기 운영 시 앨범 내 사진 경로 수만큼 무한히 쌓이던 문제 (`thumbnail.py`)
- **라이트박스/공유 뷰어 오버레이 SPA 네비게이션 잔존**: 확대 보기 중 다른
  페이지로 이동해도 오버레이와 keydown 리스너가 정리되지 않던 문제 —
  `window._pageCleanup`에 close 등록 (`lightbox.js`, `album-view.js`)

## [1.8.3] - 2026-07-17

### Changed
- **썸네일 생성 동시성 제한 + JPEG draft 디코딩**: 그리드 첫 로딩 시 대형 원본
  디코딩이 한꺼번에 몰려 NAS 메모리가 스파이크하지 않도록
  `THUMB_MAX_CONCURRENCY`(기본 4) 세마포어 적용. JPEG는 `img.draft()`로 목표
  크기에 가까운 스케일로 디코딩해 풀해상도 디코딩 대비 속도·메모리 절감
  (`thumbnail.py`)
- **search 전체 트리 walk 캐싱 + EXIF 읽기 동시성 제한**: `/api/admin/search`가
  매 요청마다 PHOTO_ROOT 전체를 재순회하던 것을 30초 TTL 캐시로 교체 —
  검색어만 바뀌는 반복 호출에서도 NAS 재순회 없음. 날짜 필터 시 캐시 미스
  EXIF 읽기를 `EXIF_READ_CONCURRENCY`(기본 8) 세마포어로 제한해 대량 미스가
  한꺼번에 NAS I/O를 몰아붙이지 않도록 함 (`load_photo_meta` 전역 적용)
  (`admin_browse.py`)

### Security
- **패스워드 보호 앨범 커버 이미지 노출 차단**: 링크만 알면 패스워드 없이도
  카카오톡 등 SNS 미리보기의 커버 이미지(og-image)를 얻을 수 있던 문제 —
  제목·설명(사진 수)은 미리보기 편의를 위해 유지하되 커버 이미지만 404 차단
  (`main.py`, `share.py`)

## [1.8.2] - 2026-07-16

### Fixed
- **EXIF 촬영일 없는 사진의 날짜별 보기**: 앨범·인물 전체보기의 날짜별 그룹에서
  EXIF `DateTimeOriginal`/`DateTime`이 없는 사진이 전부 "날짜 정보 없음"으로
  묶이던 문제 — EXIF 촬영일이 없으면 파일 mtime을 `taken_at`으로 대체 (`thumbnail.py`).
  `photo_meta_cache` 버전 v2→v3로 올려 기존 캐시 재계산 유도 (`database.py`)

## [1.8.1] - 2026-07-16

### Changed
- **앨범 taken_at 정렬이 photo_meta_cache 사용**: 사진 추가·정렬 변경 시 앨범 전체
  사진의 EXIF를 매번 원본 파일에서 직접 읽던 것을 `load_photo_meta()` 캐시 조회로
  교체 — 캐시 워밍 후 NAS 파일 접근 0회 (`admin_albums.py`)
- **ai.db person_id 인덱스 추가**: `face_matches(person_id)`,
  `face_labels(person_id)` — 인물 목록 등 인물별 집계 쿼리의 풀스캔 제거.
  기존 DB는 다음 컨테이너 기동 시 자동 생성 (`ai_database.py`, `ai_worker/db.py`)

## [1.8.0] - 2026-07-16

### Added
- **인물 상세 얼굴 리스트 보기**: 추정/확정 얼굴 섹션에 그리드⊞/리스트☰ 보기 토글
  추가. 리스트는 체크박스·얼굴 썸네일·사진 경로·매칭율 컬럼으로 구성. 확정 얼굴
  리스트는 체크박스로 여러 개 선택해 기존 batch-unlabel API로 일괄 확정 해제 가능
  (개별 ↩ 버튼도 유지) (`admin-person-detail.js`)
- **전체 사진 라이트박스 확정 해제 버튼**: 인물의 전체 사진 페이지에서 라이트박스로
  사진을 확대했을 때 하단에 '확정 해제' 버튼 추가 — 새
  `DELETE /api/admin/people/{id}/photo-label` 엔드포인트로 해당 사진의 이 인물
  라벨만 제거 (`admin_people.py`, `admin-person-photos.js`)

### Changed
- `lightbox.js`의 삭제 버튼 텍스트·확인 문구를 옵션으로 분리해 '앨범에서 삭제'와
  '확정 해제' 양쪽에서 재사용

## [1.7.1] - 2026-07-16

### Added
- **얼굴 무시 해제 batch API**: `DELETE /api/admin/faces/batch-unlabel` 추가 —
  무시된 얼굴을 여러 개 선택해 해제할 때 얼굴별 DELETE를 병렬로 여러 번 호출하던
  것을 단일 요청으로 교체 (`admin_people.py`, `admin-people.js`)

## [1.7.0] - 2026-07-16

### Added
- **라이트박스 터치 핀치 줌**: 두 손가락으로 확대/축소, 중점 이동으로 팬 처리 —
  기존 마우스 휠·더블클릭·드래그 확대와 동일한 화면에 터치 제스처 추가.
  확대 중 손가락 하나를 떼도 남은 손가락으로 팬이 끊김 없이 이어짐 (`lightbox.js`)

### Fixed
- **인물 슬라이드쇼·"이 인물로 앨범 만들기" 사진 목록 불일치**: 전체 사진 페이지는
  확정(라벨) 얼굴 사진만 보여주는데, 인물 슬라이드쇼와 앨범 생성은 확정+추정 사진을
  섞어 써서 전체 사진 페이지에서 특정 사진을 눌러 슬라이드쇼로 진입하면 다른 사진이
  뜰 수 있었던 문제 — 셋 다 확정(`source=labeled`) 기준으로 통일
  (`admin_people.py`, `slideshow.js`, `admin-person-detail.js`)

### Changed
- `.gitignore`에 `.coverage` 추가

## [1.6.2] - 2026-07-12

### Fixed
- **인물 지정 select 가나다순 정렬**: 미분류 얼굴·무시된 얼굴의 인물 지정 select와
  인물 상세 "다른 인물로 지정" select가 확정+추정 많은 순으로 표시되어 이름 찾기
  어려웠던 문제 — 이름 가나다순으로 정렬 (`admin-people.js`, `admin-person-detail.js`).
  인물 목록 그리드는 기존 정렬(확정 많은 순) 유지

## [1.6.1] - 2026-07-12

### Fixed
- **재매칭 중 얼굴 확정 500 오류**: `rematch_all`이 `DELETE`부터 `commit`까지 단일
  쓰기 트랜잭션 안에서 수만 얼굴 매칭 계산을 수행해 쓰기 락을 수 분간 유지 —
  그 동안 추정 얼굴 일괄 확정(`batch-label`) 등 face_labels 쓰기가
  `database is locked`로 실패하던 문제. 매칭 계산을 트랜잭션 밖으로 이동해
  락 유지 시간을 1초 미만으로 단축 (`ai_worker/matcher.py`)
- **ai.db busy_timeout 상향**: backend 연결 5초 → 15초 (`ai_database.py`)

## [1.6.0] - 2026-07-12

### Added
- **라이트박스 확대/이동**: 마우스 휠(커서 위치 기준 줌, 1~6배), 확대 상태 드래그 이동,
  더블클릭 2.5× 확대/복귀 토글 — 사진 이동 시 줌 자동 리셋. 앨범 편집·탐색기·인물 사진 등
  라이트박스 전체 화면에 공통 적용 (`lightbox.js`, `admin.css`)
- **확정 얼굴 전체 화면 보기**: 인물 상세 화면 확정 얼굴 카드 클릭 시 원본 사진을
  라이트박스로 표시 (`admin-person-detail.js`)
- **추정 얼굴 다른 인물로 지정**: 인물 상세 추정 얼굴 툴바에 인물 선택 + "다른 인물로 지정"
  버튼 추가 — 선택한 얼굴을 다른 인물의 확정 라벨로 일괄 이동 (`batch-label` 재사용)
- **무시된 얼굴 목록·복구**: '등록 인물 아님'으로 무시 처리한 얼굴을 모아 보는 화면 신설
  (`/admin/people/ignored`, 최근 무시 순) — 실수로 무시한 얼굴을 선택해 무시 해제(미분류 복귀)
  하거나 인물로 재지정 가능 (`GET /api/admin/faces/ignored`, `admin-people.js`)

## [1.5.0] - 2026-07-12

### Added
- **추정 얼굴 점수(%) 임계값 미리보기**: 인물 상세 화면에서 "N% 이하부터 보기"를
  입력하면 해당 점수 이하 추정 얼굴부터 바로 확인 가능 — 자동 확정 임계값을
  정하기 전 후보를 검토하는 용도. 이후 "더 보기"로 200장씩 이어서 로드
  (`GET /people/{id}/faces?max_score=`, `admin-person-detail.js`)
- **확정 얼굴 페이지네이션**: 확정 얼굴 목록도 "더 보기"로 200장씩 이어서 로드
  (기존 200장 고정 표시 → 5,000장 이상인 인물도 전체 열람 가능)
- **추정 얼굴 선택 무시**: 인물 상세 화면 추정 얼굴 선택 영역에 "선택 무시" 버튼
  추가 — 선택한 얼굴을 일괄로 '등록 인물 아님' 처리
- **인물 목록 필터**: "추정 있는 인물만 보기" 체크박스 추가 (이름 검색과 동시 적용)

### Fixed
- **미분류 얼굴 툴바 줄바꿈 버그(재발)**: 인물 선택 `<select>` 폭이 이름 길이에
  따라 늘어나며 '선택 무시' 버튼이 다음 줄로 밀리던 문제 — `.page-header`에
  `flex-wrap` 허용, select에 `max-width` 지정 (`admin.css`, `admin-people.js`)

## [1.4.0] - 2026-07-11

### Added
- **인물 전체 사진 보기 모드·정렬**: 그리드/리스트/날짜별(📅) 보기 토글과
  파일명/촬영일 × 오름/내림차순 정렬 추가 — 앨범 편집 화면과 동일한 UX
  (`admin-person-photos.js`)
- **인물 목록 이름 검색**: 인물 목록 상단 검색창에서 이름 부분 일치로 즉시 필터
  (`admin-people.js`)

### Changed
- **인물 전체 사진은 확정 얼굴만 표시**: 확정+추정을 모두 보여주던 것을 확정(라벨)
  얼굴이 포함된 사진만 표시하도록 변경 — `photos-detail`에 `source=all|labeled`
  파라미터 추가, Admin 응답에만 `file_path` 포함(공유 링크에는 미노출)
  (`admin_people.py`, `schemas.py`)

### Fixed
- **미분류 얼굴 툴바 줄바꿈 버그**: 얼굴 선택 시 버튼 텍스트에 "(N)"이 붙으며 폭이
  변해 '선택 무시' 버튼이 다음 줄로 밀리던 문제 — 버튼 텍스트 고정, 선택 개수는
  고정 폭 라벨로 분리 (`admin-people.js`)

## [1.3.0] - 2026-07-11

### Added
- **AI 야간 스캔 시각 Admin 설정**: 설정 페이지 "AI 야간 스캔" 카드에서 자동 증분 스캔
  시각(00~23시)을 변경 — ai.db `ai_settings` 테이블 신설(LumisShow 쓰기·워커 읽기),
  워커 daemon이 매 폴링 루프에서 반영하므로 컨테이너 재생성 불필요
  (`GET/PATCH /api/admin/ai/settings`, 미설정 시 기존 `AI_SCAN_HOUR` 환경변수 폴백)

### Fixed
- **AI 상태줄 실행 중 잡 표시 누락**: running/pending 잡을 하나만 표시하던 것을
  전체 나열(running 우선)로 수정 — scan 실행 중에 rematch 대기가 더 최근이면
  실행 중인 scan이 안 보이던 문제 (`admin-people.js`)

## [1.2.0] - 2026-07-11

### Added
- **인물 추정 얼굴 일괄 확정**: 기본 전체 선택 → 틀린 것만 클릭 해제 → 한 번에 확정하는 방식으로 변경,
  지정 점수 이상 전체를 서버에서 바로 확정하는 "자동 확정" 버튼 추가
  (`POST /api/admin/faces/batch-label`, `POST /api/admin/people/{id}/confirm-matched`)
- **미분류 얼굴 유사도 검색**: 얼굴 카드의 🔍 클릭 시 그 얼굴과 임베딩 코사인 유사도가 높은 순으로
  미분류 목록을 재정렬 — 신규 인물의 첫 얼굴들을 검출 신뢰도순 대량 목록에서 찾던 어려움 해소
  (`GET /api/admin/faces/{id}/similar`)
- **미분류 얼굴 화면에서 신규 인물 즉시 생성**: 인물 선택 드롭다운 최상단 "+ 새 인물 생성"에서
  이름 입력 후 바로 선택한 얼굴 지정까지 이어짐. 드롭다운에 인물별 확정/추정 수도 함께 표시

### Changed
- **미분류 얼굴 지정/무시 일괄 처리**: 선택한 얼굴 수만큼 반복하던 개별 API 호출을
  batch-label 한 번 호출로 교체 — 대량 선택 시 응답 속도 개선

## [1.1.0] - 2026-07-11

### Added
- **사진 탐색기·앨범 편집 날짜별 보기**: 기존 그리드/리스트 보기에 이어 촬영일(EXIF) 기준으로
  묶어 보는 날짜별 보기(📅) 추가 (`admin-browse.js`, `admin-album-edit.js`)
  - 날짜별 보기 진입 시 파일명 정렬은 비활성화되고 촬영일 정렬로 전환

### Changed
- **앨범 상세 응답에 촬영일 포함**: `AlbumPhotoResponse`에 `taken_at` 필드 추가 —
  앨범 편집 화면에서도 사진별 EXIF 촬영일을 사용할 수 있도록 `get_album`에서
  `photo_meta_cache`를 enrich (`schemas.py`, `admin_albums.py`)

## [1.0.3] - 2026-07-10

### Changed
- **AI 워커 이미지 크기 최적화** (`docker/Dockerfile.ai`): 압축 기준 약 586MB → 대폭 절감
  - wheel 설치를 `COPY --from=builder` 대신 `RUN --mount=type=bind`로 교체 —
    설치 후 삭제해도 이미지에 남던 237.9MB wheels 레이어 제거
  - insightface가 의존하는 full `opencv-python` wheel 제거 — `opencv-python-headless`와
    동일한 cv2 중복 설치 해소 (`--no-deps` 설치, 의존성 트리는 pip wheel이 수집)
  - full opencv 제거로 불필요해진 `libgl1` 런타임 패키지 제거

### Added
- **CI AI 이미지 smoke test** (`docker-build-check.yml`): 빌드된 워커 이미지에서
  `import cv2, insightface`를 실제 실행해 검증 — v1.0.2 cv2 ImportError처럼
  배포 후에야 드러나는 런타임 오류를 빌드 단계에서 차단

## [1.0.2] - 2026-07-09

### Fixed
- **AI 워커 컨테이너 cv2 ImportError 수정**: NAS 첫 스캔 잡이 `libxcb.so.1`/`libGL.so.1`
  누락으로 실패하던 문제 — 런타임 이미지에 `libxcb1`, `libgl1` 추가 (`docker/Dockerfile.ai`)
  - `libxcb1`: opencv-python-headless 4.13.0.90+ 의 headless regression
    ([opencv-python#1183](https://github.com/opencv/opencv-python/issues/1183))
  - `libgl1`: insightface가 full `opencv-python`을 직접 의존해 cv2가 libGL 요구

### Changed
- **nas-update.sh**: `compose down` 실패 시 fallback 강제 중지 대상에 `lumisshow-ai` 포함

## [1.0.1] - 2026-07-09

### Added
- **Admin 인물 슬라이드쇼**: 인물 상세 화면에서 해당 인물 사진 전체를 앨범 생성 없이
  바로 슬라이드쇼로 재생 (`slideshow.js`, `admin-person-detail.js`)
- **인물 전체 사진 보기**: 인물별 사진을 페이지네이션 그리드로 조회하는 화면 추가
  (`admin-person-photos.js`, `/api/admin/people/{id}/photos-detail`)

### Changed
- **nas-update.sh**: 구버전 이미지 정리 대상에 `lumisshow-ai` 이미지 포함
- **README**: Phase 2 AI 얼굴 인식 내용 추가

### Fixed
- 코드 리뷰 반영 — 인물 슬라이드쇼 안정화 및 서버/클라이언트 중복 로직 제거

## [1.0.0] - 2026-07-07

Phase 2 — AI 얼굴 인식 스마트 앨범. NAS 로컬 AI(InsightFace)로 사진 속 인물을
자동 분류하고, 인물별 사진으로 앨범을 만드는 기능이 추가되었다.

### Added
- **AI 얼굴 인식 워커 (`lumisshow-ai` 컨테이너 신설)**: PHOTO_ROOT 증분 스캔 →
  InsightFace buffalo_l(SCRFD 검출 + ArcFace 512차원 임베딩) → 등록 인물 cosine 매칭 →
  `ai.db` 기록. 사진 1장=1커밋으로 중단 후 재개 가능 (`ai_worker/`)
  - 데몬 모드: 매일 `AI_SCAN_HOUR`(기본 02:00, Asia/Seoul) 자동 증분 스캔 + Admin 수동
    트리거(jobs 큐) 폴링, 비정상 종료 잡 자동 복구
  - 검증 정확도: 정답 셋 44명/1,235라벨 기준 threshold 0.45에서 precision 99.9% / recall 97.9%
  - 모델 가중치(non-commercial)는 이미지에 미포함 — 첫 실행 시 `$DATA_DIR/models/`로 자동 다운로드
- **Admin '인물(People)' 화면**: 인물 목록(AI 분석 상태·스캔/재매칭 트리거), 인물 상세
  (추정 얼굴 맞음/아님 교정 — 교정할수록 정확도 향상), 미분류 얼굴 다중 선택 지정/무시
- **인물 앨범 생성 도우미**: 인물 상세에서 해당 인물 사진 전체를 기존 앨범으로 생성
  (공유 링크·슬라이드쇼·ZIP 등 기존 기능 그대로 사용)
- **People API** (`/api/admin/people`, `/api/admin/faces/*`, `/api/admin/ai/*`):
  인물 CRUD, 얼굴 라벨 교정, 크롭 서빙, AI 상태 조회/잡 트리거 (`admin_people.py`)
- **라벨링 도구**: 유사 얼굴 클러스터링 HTML 시트(`label_sheet.py`), CSV 라벨
  import/export(`label_helper.py`), threshold별 precision/recall 평가(`eval.py`)
- **CI 빌드 검증**: 개발 브랜치 push 시 두 Docker 이미지 빌드 확인 (`docker-build-check.yml`)

### Changed
- **릴리즈 파이프라인**: 태그 push 시 `lumisshow`와 `lumisshow-ai` 이미지를 함께 GHCR에
  빌드·배포 (`release.yml`)
- **docker-compose**: `lumisshow-ai` 서비스 추가 (`mem_limit 2g`, 사진 볼륨 읽기 전용 공유)

## [0.9.5] - 2026-07-03

### Changed
- **배경음악 저작권 안내 문구 추가**: 앨범 편집 화면 음악 파일 선택 버튼 하단에 저작권 주의 문구와 Pixabay Music 링크 안내 추가 (`admin-album-edit.js`, `admin.css`)

## [0.9.4] - 2026-06-28

### Fixed
- **슬라이드쇼 툴바 좁은 화면 버튼 겹침 수정**: 화면 너비 640px 이하에서 버튼이 겹쳐 일부 제어가 불가하던 문제 수정 — 좁은 화면에서는 핵심 4개 버튼(음악 On/Off · 일시정지 · 다운로드 · 닫기)만 표시 (`slideshow.css`)

## [0.9.3] - 2026-06-28

### Fixed
- **SQLite `database is locked` 에러 수정**: 슬라이드쇼 로딩 시 브라우저가 `/album`과 `/photos`를 동시에 요청할 때 커넥션 간 쓰기 충돌로 발생하던 문제 수정 — WAL 모드(`journal_mode=WAL`) 적용으로 동시 읽기 허용, `busy_timeout=5000ms`로 lock 경합 시 즉시 실패 대신 재시도 (`database.py`)

## [0.9.2] - 2026-06-28

### Changed
- **앨범 편집 사진 제외 UI 개선**: 개별 ✕ 버튼 제거 → 헤더 "사진 제외" 버튼으로 체크박스 다중선택 모드 진입
  - 전체 선택 버튼, 선택 수 표시, 제외 확인·취소 컨트롤 지원
  - 그리드·리스트 양쪽 뷰 모두 지원
  - 제외 모드 중 라이트박스 비활성화 (단일 삭제는 크게보기에서 유지)

## [0.9.1] - 2026-06-28

### Added
- **앨범 사진 경로 자동 복구**: 폴더명 변경 등으로 깨진 사진 경로를 파일명 기반으로 자동 탐색·수정 (`POST /api/admin/albums/{id}/repair-paths`)
  - 1:1 매칭 시 자동 수정, 동명 파일 여러 개일 경우 `ambiguous` 목록으로 반환
  - `album_photos.file_path`와 `albums.cover_path` 모두 수정
- **앨범 편집 화면 경로 복구 버튼**: 썸네일 로드 실패 감지 시 사진 섹션에 "경로 복구" 버튼 자동 표시, 클릭 시 복구 후 결과 요약 알림

## [0.9.0] - 2026-06-28

### Added
- **Open Graph 메타 태그 서버사이드 주입**: 공유 링크 SPA 라우트(`/s/{token}`)를 동적 렌더링으로 교체 — DB에서 앨범명·설명·사진 수를 조회해 `og:title`, `og:description`, `og:type`, `og:site_name` 태그를 `</head>` 직전에 주입 (`main.py`)
- **OG 커버 이미지 공개 엔드포인트**: `GET /api/share/{token}/og-image` 신규 추가 — 세션 쿠키 없이 SNS 크롤러가 접근 가능, 앨범 커버 미지정 시 정렬 기준 첫 번째 사진으로 자동 대체, `medium`(800×600) 썸네일 반환 (`share.py`)
- **BASE_URL 조건부 주입**: `BASE_URL` 환경변수가 설정된 경우에만 `og:image`, `og:image:width`, `og:image:height`, `og:url` 절대 URL 태그를 추가해 크롤러가 상대경로를 사용하는 문제 방지

## [0.8.6] - 2026-06-23

### Changed
- **README 프로젝트명 유래 추가**: LumisShow 이름 결정 배경 (Lumis 충돌 → LumisShow 확정) 문서화
- **테스트 커버리지 대폭 확대**: 181개 → 192개 (E2E 4개 → 11개, Unit/API 177개 → 181개)
  - E2E 신규: ZIP 실제 파일 다운로드, 중복 파일명 ZIP 처리, 앨범 커버 인덱스 정합성, 멀티트랙 음악 인덱스 네비게이션, health/version/SPA 라우트, Admin 설정→뷰어 기본값 전파, 날짜 필터 검색
  - Unit 신규: `ADMIN_PASSWORD_HASH` bcrypt 인증, non-admin JWT 거부, 절대경로 admin thumb/photo

## [0.8.4] - 2026-06-23

### Fixed
- **슬라이드쇼 시작 위치와 커버 설정 분리**: 앨범 커버를 지정하면 슬라이드쇼가 커버 이미지 위치부터 재생되던 문제 수정 — 슬라이드쇼는 항상 sort_order 기준 첫 번째 사진부터 시작하며, 커버 이미지는 앨범 뷰 표지 표시에만 사용 (`slideshow.js`)

## [0.8.3] - 2026-06-23

### Fixed
- **슬라이드쇼 시작 시 crash 수정**: 앨범 커버 또는 `?i=N` 시작 인덱스가 첫 페이지(50장) 범위를 초과할 때 `Cannot read properties of undefined (reading 'url')` 오류 발생 — 해당 페이지를 렌더링 전에 즉시 로드하도록 수정 (`slideshow.js`)

## [0.8.2] - 2026-06-23

### Fixed
- **세션 메모리 누수 수정**: 공유 링크 조회수 중복 방지용 `_counted_sessions` dict가 만료된 항목을 정리하지 않아 장시간 실행 컨테이너에서 무한 증가하던 문제 수정 — 각 요청 전 TTL 만료 항목 자동 퇴거 추가 (`share.py`)

### Security
- **Admin 로그인 무차별 대입 방지**: 동일 IP에서 5회 연속 로그인 실패 시 15분 잠금 적용 — `share_link_failures` 테이블 `admin:{ip}` 키 재사용으로 컨테이너 재시작 후에도 잠금 상태 유지 (`auth.py`)

## [0.8.1] - 2026-06-22

### Fixed
- **슬라이드쇼 사진 품질 저하 수정**: 슬라이드쇼가 원본 대신 800×600 JPEG 썸네일(`thumb_medium_url`)을 표시하던 문제 수정 — `photo.url`(원본)로 교체. 초기 표시·전환·프리로드 모두 수정 (`slideshow.js`)
- **공유 뷰어 사진 단독 보기 품질 저하 수정**: 썸네일 클릭 시 나타나는 단독 보기 화면도 동일하게 썸네일이 표시되던 문제 수정 (`album-view.js`)
- **Admin 라이트박스 품질 저하 수정**: 앨범 편집·탐색기 라이트박스가 medium 썸네일을 표시하던 문제 수정 — `GET /api/admin/photo` 엔드포인트 신규 추가하여 원본 직접 서빙 (`lightbox.js`, `admin_browse.py`)

## [0.8.0] - 2026-06-22

### Performance
- **슬라이드쇼 진보적 로딩**: 첫 50장을 즉시 시작 후 나머지를 백그라운드에서 로드 — 대용량 앨범(500장+)에서 진입 지연 대폭 감소 (`slideshow.js`)
- **photo_meta_cache 전체 EXIF 저장**: `taken_at`·`width`·`height` 3개 → `make`·`camera`·`shutter`·`aperture`·`iso` 등 15개 컬럼으로 확장, `cache_version` 마킹으로 구 캐시 자동 무효화 (`database.py`, `admin_browse.py`, `share.py`)
- **N+1 DB 쿼리 제거**: `_enrich_photos()`에서 사진별 개별 쿼리 → `WHERE file_path IN (?, ...)` 단일 쿼리 (청크 900) (`admin_browse.py`)
- **검색 전량 enrich 제거**: 날짜 필터 없을 때 해당 페이지 사진만 EXIF enrich — 10,000장 중 20장 요청 시에도 전량 처리하던 구조 개선 (`admin_browse.py`)
- **썸네일 앨범 검증 쿼리 감소**: 토큰별 30초 TTL 인메모리 캐시로 그리드 100장 로드 시 DB 쿼리 100회 → 1회 (`media.py`)
- **서브폴더 child_count 산출 개선**: `os.scandir()` → `os.listdir()`로 불필요한 stat 오버헤드 제거 (`admin_browse.py`)
- **`_photo_root()` 중복 계산 제거**: 각 핸들러에서 요청당 1회 계산 후 하위 함수에 전달 (`admin_browse.py`, `media.py`)

### Added
- **사진 목록 페이지네이션**: `GET /api/share/{token}/photos?page=N&size=N` 파라미터 추가 — 기본(size=0)은 전체 반환으로 하위 호환 (`share.py`, `schemas.py`)

### Fixed
- **슬라이드쇼 info 패널 EXIF 미표시**: 기존 `photo_meta_cache` 행에 신규 EXIF 컬럼이 NULL로 남아 info 패널이 비던 문제 — `cache_version < 1` 행을 앱 기동 시 자동 삭제 후 재캐싱 (`database.py`)
- **썸네일 동시 생성 레이스 컨디션**: 존재 체크와 생성 사이 동시 요청 시 중복 생성 시도 가능하던 문제 — per-path `threading.Lock` 적용 (`thumbnail.py`)

### Security
- **브루트포스 잠금 DB 저장**: `_fail_registry` 메모리 dict → `share_link_failures` SQLite 테이블로 교체 — 컨테이너 재시작 후에도 잠금 상태 유지 (`share.py`, `database.py`)

## [0.7.0] - 2026-06-22

### Added
- **공유 뷰어 사진 확대 중 슬라이드쇼 바로 시작**: 사진 단독 확대 보기 하단에 "▶ 슬라이드쇼" 버튼 추가 — 현재 보고 있는 사진 인덱스 기준으로 슬라이드쇼 즉시 진입 (`album-view.js`)

### Fixed
- **설정 패널 취소 시 DOM 롤백**: 값 변경 후 취소(버튼·백드롭 클릭 모두)하면 다음 번 패널 열 때 저장된 값으로 복원됨 (`album-view.js`)
- **사진 추가 중복 피드백**: 탐색기에서 이미 앨범에 있는 사진 추가 시 "N장 추가됨, M장 중복 제외" alert 표시 — `POST /api/admin/albums/{id}/photos` 응답에 `added`/`skipped` 건수 추가 (`admin_albums.py`, `admin-browse.js`)

### Changed
- **앨범 목록 로딩 깜빡임 개선**: 재방문 시 이전 결과를 즉시 표시 후 백그라운드 갱신 (모듈 캐시 적용) (`admin-albums.js`)
- **Unit Test 커버리지 확대**: 158개 → 159개 — `POST /photos` 빈 경로 목록·중복 건수 반환 테스트 추가

## [0.6.1] - 2026-06-22

### Fixed
- **라이트박스 키보드 이벤트 리스너 누적 방지**: `close()` 함수에 `closed` 플래그 추가 — 비동기 삭제 중 Escape 등 중복 호출 경로에서 `removeEventListener`가 항상 정확히 1회 실행됨 (`lightbox.js`)
- **비루프 슬라이드쇼 경계값 오동작 수정**: `loop=false`일 때 첫 사진에서 역방향(←) 이동 시 마지막 사진으로 이동하던 모듈로 연산 오류 수정 — 경계에서 `advance()` 호출 차단 (`slideshow.js`)
- **공유 링크 메모리 무한 누적 방지**: `_fail_registry`에 `recorded_at` 타임스탬프 추가, `_counted_sessions`를 `set` → `dict[cookie, expires_at]`으로 변경 — `_purge_stale()` 기회적 정리로 장기 운영 시 메모리 누수 해소 (`share.py`)

### Changed
- **Unit Test 커버리지 확대**: 기존 53개 → 158개 (105개 추가)
  - `test_admin_settings.py` 신규 (11개): GET 기본값, PATCH 각 필드, 인증 검증
  - `test_admin_albums.py` 추가 (9개): 앨범 복제(`duplicate_album`) 5개, 조회수 리셋(`reset_view_count`) 3개, 인증 1개
  - `test_share.py` 추가 (2개): 조회수 첫 접속 증가, 동일 세션 중복 방지
  - `test_browse.py` 추가 (5개): `list_music` 빈 폴더·오디오 반환·비오디오 필터·rel 경로·인증

## [0.6.0] - 2026-06-22

### Added
- **슬라이드쇼 속도 즉시 조절**: 툴바에 −/Ns/+ 버튼 추가 — 재생 중 전환 간격을 2·3·5·8·10·15·20·30초 프리셋으로 즉시 변경, localStorage 저장
- **앨범 복제**: 앨범 편집 페이지 우상단 "복제" 버튼 — 앨범 설정(테마·슬라이드쇼·음악)과 사진 목록 전체를 새 앨범으로 복사 (`POST /api/admin/albums/{id}/duplicate`)

### Changed
- **슬라이드쇼 사진 비율 개선**: `object-fit: cover` → `contain`으로 변경, 남는 여백을 동일 사진의 블러 버전으로 채워 사진 전체 구도가 잘리지 않고 표시됨
- **앨범 편집 모바일 섹션 순서 변경**: `grid-template-areas` 적용 — 모바일(768px 이하)에서 기본 정보 → 슬라이드쇼 기본 설정 → 공유 링크 → 사진 순으로 재배치

## [0.5.2] - 2026-06-22

### Fixed
- Admin 설정 페이지 진입 시 서버의 `ui_theme` 값을 localStorage에 동기화 — 한 기기에서 테마를 변경한 뒤 다른 기기에서 설정 페이지를 열면 변경된 테마가 즉시 반영됨

## [0.5.1] - 2026-06-22

### Changed
- 슬라이드쇼 툴바 배경 완전 투명화: 모든 디바이스에서 하단 버튼 영역 그라디언트·블러 제거
- 모바일 중앙 탭 동작 변경: 툴바 표시 → 즉시 숨김 토글 (`toggleUI`)
- 모바일에서 `mousemove` 리스너 미등록: 터치 후 브라우저가 생성하는 합성 mousemove 이벤트로 툴바가 다시 표시되던 문제 수정

## [0.5.0] - 2026-06-21

### Added
- **사진 단독 확대 보기**: 공유 앨범 화면에서 썸네일 클릭 시 슬라이드쇼 대신 해당 사진만 전체화면으로 확대 표시
  - 하단에 파일명 · 현재 번호/전체 수 표시
  - 다운로드 버튼 및 EXIF 정보 보기 버튼 (슬라이드쇼와 동일 기능)
  - 좌우 화살표 버튼 및 키보드(←/→/Esc) 탐색
- **줌인/아웃**: 확대 보기 화면에서 다양한 방법으로 사진 확대/축소
  - 마우스 휠: 커서 위치 기준 확대/축소
  - 더블클릭: 클릭 위치 기준 2× 확대 / 원래 크기 복귀 토글
  - 드래그: 확대 상태에서 이미지 패닝
  - 핀치 제스처 (모바일): 두 손가락 핀치로 줌인/아웃 + 패닝
  - 키보드 `+`/`-`: 1.3× 단계 줌인/아웃, `0`: 리셋
  - 마우스 가운데 버튼: 줌 즉시 초기화

## [0.4.3] - 2026-06-21

### Changed
- 슬라이드쇼 전환 효과 목록(`EFFECTS`), 라벨, 기본 설정, `loadSlideshowSettings` 함수를 `slideshow-config.js` 공유 모듈로 추출 — 4개 파일에 분산되어 있던 중복 정의 제거
- 슬라이드쇼 시작 시 `?i=N` URL 파라미터 제거 (`history.replaceState`) — 특정 사진에서 시작 후 URL이 깔끔하게 정리됨

## [0.4.2] - 2026-06-21

### Fixed
- 사진이 없는 앨범의 공유 뷰어에서 전체 다운로드 버튼 비활성화 처리

## [0.4.1] - 2026-06-21

### Changed
- 신규 앨범 생성 시 기본 테마를 서버 기본(`null`)으로 설정 — 서버 테마 변경 시 기본값 앨범 전체에 자동 반영

## [0.4.0] - 2026-06-21

### Added
- **멀티 테마 시스템**: 8종 테마 지원 — Dark / OLED Black / Slate / Warm Dark / Light / Sepia / Sky / Rose
- **Glassmorphism UI**: 네비게이션 바·모달·뷰어 설정 패널·슬라이드쇼 툴바에 `backdrop-filter: blur()` frosted glass 적용
- **Liquid Glass 요소**: Primary 버튼 hover glow, ghost 버튼 반투명 배경, 선택 상태 glow outline
- **Elevation 시스템**: 그림자 대신 lightness 기반 4단계 표면 계층 + 카드 상단 inset highlight
- **앨범별 테마 설정**: 앨범 편집 화면에서 각 앨범에 독립 테마 지정 가능
- **서버 기본 테마 옵션**: 앨범 테마를 '서버 기본'으로 설정하면 Admin 설정의 기본 테마를 자동 적용
- **Admin 테마 서버 저장**: Admin 설정에서 테마 변경 시 서버에도 저장 → 신규 앨범 생성 시 해당 테마가 기본값으로 적용
- **테마 모듈** (`theme.js`): 테마 목록·색상 정의, localStorage 기반 개인 설정 관리
- **FOUC 방지**: `<head>` 인라인 스크립트로 페이지 렌더 전 `data-theme` 즉시 설정

### Changed
- Admin UI 테마가 뷰어에서 앨범 테마로 변경된 뒤 Admin 페이지로 돌아올 때 개인 테마(localStorage)로 자동 복원
- `AlbumResponse.ui_theme = null`은 서버 기본 테마 사용을 의미 (기존 앨범은 null → 서버 기본값 적용)

## [0.3.8] - 2026-06-21

### Added
- 탐색기 숨김 경로 설정 기능: Admin 설정에서 사진 탐색 화면에 표시하지 않을 폴더를 관리 (PHOTO_ROOT 기준 상대 경로)
- 숨김 경로 전용 관리 화면 (`/admin/hidden-paths`): 목록 조회·추가·삭제·저장, 설정 페이지에 개수 배지 표시
- 경로 추가 시 서버에서 실제 폴더 존재 여부를 사전 검증하여 오입력 방지 (`GET /api/admin/path-exists`)

## [0.3.7] - 2026-06-20

### Added
- 앨범 편집 화면 공유 링크에 삭제 버튼 추가: 활성 링크는 비활성화 후 삭제, 비활성/만료 링크는 바로 삭제

### Fixed
- 공유 링크 삭제 후 새 링크 생성 시 삭제된 링크가 목록에 다시 표시되던 버그 수정

## [0.3.6] - 2026-06-20

### Added
- NAS 원클릭 배포 스크립트 추가 (`scripts/nas-update.sh`): pull → 중지 → 재시작 → 구버전 이미지 정리를 SSH 커맨드 하나로 수행

### Fixed
- 공유 링크 토큰 길이 복원: `token_urlsafe(16)` (22자) → `token_hex(5)` (10자). 속도 제한(5회 실패 → 15분 잠금)으로 충분한 보안 수준 유지

## [0.3.5] - 2026-06-20

### Security
- Admin 썸네일 URL에서 JWT 노출 제거: `?token=` 쿼리 파라미터 방식을 httpOnly 쿠키(`admin_img_session`) 방식으로 교체하여 nginx 로그·브라우저 히스토리에 8h admin JWT가 노출되지 않도록 수정

## [0.3.4] - 2026-06-19

### Changed
- 모바일 슬라이드쇼 툴바 버튼 크기 확대: 터치 타겟 ~32px → ~40px (font-size 16→18px, 수직 패딩 8→11px)

## [0.3.3] - 2026-06-19

### Fixed
- 슬라이드쇼 정보 패널 EXIF 미표시 문제: `share.py`에서 상대 경로를 절대 경로로 변환하지 않아 PIL이 파일을 찾지 못하던 버그 수정
- ZIP 다운로드 시 상대 경로를 절대 경로로 변환하지 않아 파일이 포함되지 않던 버그 수정

## [0.3.2] - 2026-06-19

### Security
- 공유 링크 토큰 강도 강화: `secrets.token_hex(5)` (40비트) → `secrets.token_urlsafe(16)` (128비트)
- `album_photos.file_path` 절대 경로 → PHOTO_ROOT 기준 상대 경로 저장 (서버 파일시스템 구조 노출 방지)

### Fixed
- ZIP 다운로드가 전체 아카이브를 메모리에 올리던 문제 수정: `zipstream-ng` 청크 스트리밍으로 교체
- 탐색기(`/browse`, `/search`) 요청마다 PIL로 EXIF 재읽기 하던 성능 문제: `photo_meta_cache` 테이블 캐싱 추가
- DB 마이그레이션 예외 처리 범위 축소: `except Exception` → `except OperationalError` (실제 오류 은폐 방지)
- 테스트 13건 오류 수정 (PUT/PATCH 메서드 불일치, 토큰 길이, EXIF 필드수, Windows 경로 구분자)

## [0.3.1] - 2026-06-18

### Added
- 사진 탐색 화면 개선
  - Synology NAS 시스템 폴더 자동 숨김 (`@eaDir`, `#recycle`, `@tmp`, `#snapshot` 등)
  - 리스트 보기 / 그리드 보기 토글 (⊞/☰)
  - 정렬 옵션 추가: 파일명 오름차순/내림차순, 날짜 오름차순/내림차순
  - 전체 선택 / 전체 해제 버튼 항상 표시
  - 사진 클릭 시 라이트박스 확대 보기 (체크박스로 선택)
  - 라이트박스 하단에 선택 상태 표시 (선택/✓ 선택됨 + 현재 선택 수/전체 수)
- 앨범 편집 화면 개선
  - 사진 썸네일 클릭 시 라이트박스 확대 보기
  - 리스트 보기 / 그리드 보기 토글 (⊞/☰)
  - 라이트박스 하단에 "커버로 설정" / "앨범에서 삭제" 액션 버튼

### Fixed
- 앨범 편집 리스트 보기에서 "커버로 설정" 버튼이 보이지 않던 문제 수정

## [0.3.0] - 2026-06-18

### Added
- 모바일 슬라이드쇼 탭존 내비게이션: 스와이프 제스처 대신 화면 좌(35%)/우(35%) 탭으로 이전/다음 이동
  - 중앙(30%) 탭 시 툴바 표시/숨김 토글
  - 탭존 힌트 화살표(‹ ›) 툴바와 연동하여 자동 페이드
- 모바일 슬라이드쇼 진입 시 자동 전체화면 + orientation lock 시도

### Changed
- 모바일 Portrait 처리: CSS 90도 회전 방식 → 16:9 letterbox 방식으로 교체
  - 전체화면에서도 letterbox 유지 (`document.documentElement` 기준 fullscreen)
- 모바일 감지 기준: `max-width: 600px` → `(pointer: coarse) and (hover: none)` 미디어쿼리

### Fixed
- 핀치줌/더블탭 줌으로 슬라이드쇼 레이아웃 깨지는 문제: `user-scalable=no` + `touch-action: none`
- iOS 뒤로가기 스와이프와 슬라이드쇼 스와이프 충돌: 탭존 방식으로 전환해 충돌 원천 차단
- favicon.ico 404 로그 제거: `<link rel="icon" href="data:,">` 추가

## [0.2.6] - 2026-06-18

### Added
- 앨범 커버 미지정 시 정렬 기준 첫 번째 사진 자동 표시 (DB 저장 없음, `first_photo_path` API 응답 추가)
- 앨범 조회수 기능: 슬라이드쇼 접속 시 +1 누적, 앨범 목록 카드 및 편집 화면 기본 정보에 표시
  - 앨범 편집 기본 정보에 조회수 + 초기화 버튼 추가
  - 동일 세션(쿠키) 기준 새로고침 중복 카운트 방지

## [0.2.5] - 2026-06-18

### Added
- 앨범 사진 정렬 기능: 앨범 편집 화면 사진 섹션에 정렬 버튼 추가 ("+사진 추가" 왼쪽)
  - 정렬 기준: 파일명 / 촬영일(EXIF 기반), 기본값: 촬영일 오름차순
  - 방향: 오름차순 / 내림차순
  - 적용 시 album_photos.sort_order 실체화 → 슬라이드쇼·공유 뷰어 자동 반영
  - 사진 추가 시에도 앨범 sort 설정에 맞게 자동 재정렬
  - 촬영일 EXIF 없는 사진은 파일명으로 tiebreak

## [0.2.4] - 2026-06-17

### Added
- Admin 설정 메뉴 추가 (사진 탐색 · 로그아웃 사이에 배치)
  - 서버 타임존 설정: 검색 가능한 드롭다운, 49개 글로벌 타임존 지원
  - 슬라이드쇼 전역 기본값 설정 (전환 시간·순서·효과·음악·음량·반복)
- 앨범별 슬라이드쇼 기본 설정: 앨범 편집 화면에 "슬라이드쇼 기본 설정" 섹션 추가
  - 앨범마다 개별 슬라이드쇼 설정을 DB에 저장
  - 신규 앨범 생성 시 서버 전역 설정값으로 자동 초기화
- 공유 링크 뷰어에 앨범별 기본 설정 적용: 뷰어 진입 시 앨범 DB 설정값 사용
  - 뷰어에서 변경한 설정은 로컬(localStorage, 토큰별)에만 저장되고 DB는 변경되지 않음

### Fixed
- 공유 링크 만료일 처리 버그 수정
  - 타임존 오프셋이 포함된 만료일을 UTC로 정규화하여 SQLite에 저장
  - 음수 UTC 오프셋(예: EST UTC-5)에서 만료 비교가 잘못되던 문제 해결
  - Admin UI에서 만료된 링크를 "활성" 으로 잘못 표시하던 버그 수정 ("만료됨" 배지 추가)
- 만료일 표시를 서버 타임존 기준으로 변환하여 정확하게 표시

## [0.2.3] - 2026-06-17

### Changed
- 크레딧 표기 변경: `© euikuk.jeong` → `Made by Ekjeong`

## [0.2.2] - 2026-06-17

### Fixed
- 버전 표시 이중 `v` 접두사 제거 (`vv0.2.1` → `v0.2.1`)

### Changed
- Admin 네비바 및 뷰어 하단에 `© euikuk.jeong` copyright 추가

## [0.2.1] - 2026-06-17

### Added
- Admin 네비바 및 뷰어 하단에 버전 정보 표시 (`GET /version` 공개 엔드포인트)
- `localtest.sh` 추가 (Git Bash용, git tag 기준 버전 자동 감지)

### Fixed
- `localtest.bat` 콘솔 한글 깨짐 → 영문으로 변경
- `localtest.bat`에서 APP_VERSION git tag 자동 설정 (CMD에서 동작 안 하는 문제)

### Changed
- Dockerfile에 `ARG/ENV APP_VERSION` 추가, 릴리즈 시 git tag 자동 주입

## [0.2.0] - 2026-06-17

### Added
- 풀스크린 버튼 추가 (⛶ / ⊡ 토글, `requestFullscreen` API)
- 반복 재생 설정 옵션 (켜기: 순환 / 끄기: 마지막 사진에서 정지)
- 반복 완료 토스트: 사이클 종료 시 '🔁 처음부터 다시 재생' 3초 표시
- 종료 토스트: 마지막 사진 인터벌 후 '슬라이드쇼가 종료되었습니다' 10초 표시
- `localtest.bat`: LAN IP 자동 감지 포함 로컬 개발 서버 실행 스크립트

### Changed
- 모바일 반응형 레이아웃: 화살표·볼륨 슬라이더·info 버튼 숨김, 툴바 버튼 축소
- landscape 강제 고정: CSS `rotate(90deg)` (portrait 미디어쿼리) + `screen.orientation.lock` 병행
- 터치 스와이프 좌표 보정: portrait CSS 회전 시 축 매핑 처리
- UI 자동 숨김: 마우스/탭 없을 시 3초 후 툴바·화살표 페이드 아웃
- 음량 기본값 60% → 25%

## [0.1.0] - 2026-06-16

### Added
- 앨범 관리 (생성/편집/삭제, 사진 추가·제외, 앨범 커버 설정)
- 공유 링크 생성 (비밀번호·만료일 설정, UUID 토큰 방식)
- 슬라이드쇼 전환 효과 9종 + Ken Burns 효과 (8방향 랜덤 Pan·Zoom)
- 배경음악 다중 트랙 지원 (선택 UI, 드래그앤드롭 순서 변경, 이전/다음 곡)
- EXIF 메타데이터 전체 표시 (셔터·조리개·ISO·초점거리·플래시 등)
- 이미지 프리로드 (N+1, N+2 미리 로드, 메모리 자동 해제)
- 관리자 bcrypt 패스워드 해시 지원 (`ADMIN_PASSWORD_HASH`)
- Brute-force 방어 (5회 실패 시 15분 잠금)
- ZIP 다운로드 (앨범 전체 스트리밍)
- Docker 단일 컨테이너 구성 (FastAPI + Vanilla JS)

[Unreleased]: https://github.com/euikuk-jeong/lumisshow/compare/v2.17.7...HEAD
[2.17.7]: https://github.com/euikuk-jeong/lumisshow/compare/v2.17.6...v2.17.7
[2.17.6]: https://github.com/euikuk-jeong/lumisshow/compare/v2.17.5...v2.17.6
[2.17.5]: https://github.com/euikuk-jeong/lumisshow/compare/v2.17.4...v2.17.5
[2.17.4]: https://github.com/euikuk-jeong/lumisshow/compare/v2.17.3...v2.17.4
[2.17.3]: https://github.com/euikuk-jeong/lumisshow/compare/v2.17.2...v2.17.3
[2.17.2]: https://github.com/euikuk-jeong/lumisshow/compare/v2.17.1...v2.17.2
[2.17.1]: https://github.com/euikuk-jeong/lumisshow/compare/v2.17.0...v2.17.1
[2.17.0]: https://github.com/euikuk-jeong/lumisshow/compare/v2.16.5...v2.17.0
[2.16.5]: https://github.com/euikuk-jeong/lumisshow/compare/v2.16.4...v2.16.5
[2.16.4]: https://github.com/euikuk-jeong/lumisshow/compare/v2.16.3...v2.16.4
[2.16.3]: https://github.com/euikuk-jeong/lumisshow/compare/v2.16.2...v2.16.3
[2.16.2]: https://github.com/euikuk-jeong/lumisshow/compare/v2.16.1...v2.16.2
[2.16.1]: https://github.com/euikuk-jeong/lumisshow/compare/v2.16.0...v2.16.1
[2.16.0]: https://github.com/euikuk-jeong/lumisshow/compare/v2.15.4...v2.16.0
[2.15.4]: https://github.com/euikuk-jeong/lumisshow/compare/v2.15.3...v2.15.4
[2.15.3]: https://github.com/euikuk-jeong/lumisshow/compare/v2.15.2...v2.15.3
[2.15.2]: https://github.com/euikuk-jeong/lumisshow/compare/v2.15.1...v2.15.2
[2.15.1]: https://github.com/euikuk-jeong/lumisshow/compare/v2.15.0...v2.15.1
[2.15.0]: https://github.com/euikuk-jeong/lumisshow/compare/v2.14.1...v2.15.0
[2.14.1]: https://github.com/euikuk-jeong/lumisshow/compare/v2.14.0...v2.14.1
[2.14.0]: https://github.com/euikuk-jeong/lumisshow/compare/v2.13.0...v2.14.0
[2.13.0]: https://github.com/euikuk-jeong/lumisshow/compare/v2.12.2...v2.13.0
[2.12.2]: https://github.com/euikuk-jeong/lumisshow/compare/v2.12.1...v2.12.2
[2.12.1]: https://github.com/euikuk-jeong/lumisshow/compare/v2.12.0...v2.12.1
[2.12.0]: https://github.com/euikuk-jeong/lumisshow/compare/v2.11.0...v2.12.0
[2.11.0]: https://github.com/euikuk-jeong/lumisshow/compare/v2.10.0...v2.11.0
[2.10.0]: https://github.com/euikuk-jeong/lumisshow/compare/v2.9.0...v2.10.0
[2.9.0]: https://github.com/euikuk-jeong/lumisshow/compare/v2.8.0...v2.9.0
[2.8.0]: https://github.com/euikuk-jeong/lumisshow/compare/v2.7.3...v2.8.0
[2.7.3]: https://github.com/euikuk-jeong/lumisshow/compare/v2.7.2...v2.7.3
[2.7.2]: https://github.com/euikuk-jeong/lumisshow/compare/v2.7.1...v2.7.2
[2.7.1]: https://github.com/euikuk-jeong/lumisshow/compare/v2.7.0...v2.7.1
[2.7.0]: https://github.com/euikuk-jeong/lumisshow/compare/v2.6.0...v2.7.0
[2.6.0]: https://github.com/euikuk-jeong/lumisshow/compare/v2.5.0...v2.6.0
[2.5.0]: https://github.com/euikuk-jeong/lumisshow/compare/v2.4.1...v2.5.0
[2.4.1]: https://github.com/euikuk-jeong/lumisshow/compare/v2.4.0...v2.4.1
[2.4.0]: https://github.com/euikuk-jeong/lumisshow/compare/v2.3.1...v2.4.0
[2.3.1]: https://github.com/euikuk-jeong/lumisshow/compare/v2.3.0...v2.3.1
[2.3.0]: https://github.com/euikuk-jeong/lumisshow/compare/v2.2.0...v2.3.0
[2.2.0]: https://github.com/euikuk-jeong/lumisshow/compare/v2.1.1...v2.2.0
[2.1.1]: https://github.com/euikuk-jeong/lumisshow/compare/v2.1.0...v2.1.1
[2.1.0]: https://github.com/euikuk-jeong/lumisshow/compare/v2.0.2...v2.1.0
[2.0.2]: https://github.com/euikuk-jeong/lumisshow/compare/v2.0.1...v2.0.2
[2.0.1]: https://github.com/euikuk-jeong/lumisshow/compare/v2.0.0...v2.0.1
[2.0.0]: https://github.com/euikuk-jeong/lumisshow/compare/v1.16.1...v2.0.0
[1.16.1]: https://github.com/euikuk-jeong/lumisshow/compare/v1.16.0...v1.16.1
[1.16.0]: https://github.com/euikuk-jeong/lumisshow/compare/v1.15.4...v1.16.0
[1.15.4]: https://github.com/euikuk-jeong/lumisshow/compare/v1.15.3...v1.15.4
[1.15.3]: https://github.com/euikuk-jeong/lumisshow/compare/v1.15.2...v1.15.3
[1.15.2]: https://github.com/euikuk-jeong/lumisshow/compare/v1.15.1...v1.15.2
[1.15.1]: https://github.com/euikuk-jeong/lumisshow/compare/v1.15.0...v1.15.1
[1.15.0]: https://github.com/euikuk-jeong/lumisshow/compare/v1.14.0...v1.15.0
[1.14.0]: https://github.com/euikuk-jeong/lumisshow/compare/v1.13.0...v1.14.0
[1.13.0]: https://github.com/euikuk-jeong/lumisshow/compare/v1.12.0...v1.13.0
[1.12.0]: https://github.com/euikuk-jeong/lumisshow/compare/v1.11.3...v1.12.0
[1.11.3]: https://github.com/euikuk-jeong/lumisshow/compare/v1.11.2...v1.11.3
[1.11.2]: https://github.com/euikuk-jeong/lumisshow/compare/v1.11.1...v1.11.2
[1.11.1]: https://github.com/euikuk-jeong/lumisshow/compare/v1.11.0...v1.11.1
[1.11.0]: https://github.com/euikuk-jeong/lumisshow/compare/v1.10.1...v1.11.0
[1.10.1]: https://github.com/euikuk-jeong/lumisshow/compare/v1.10.0...v1.10.1
[1.10.0]: https://github.com/euikuk-jeong/lumisshow/compare/v1.9.2...v1.10.0
[1.9.2]: https://github.com/euikuk-jeong/lumisshow/compare/v1.9.1...v1.9.2
[1.9.1]: https://github.com/euikuk-jeong/lumisshow/compare/v1.9.0...v1.9.1
[1.9.0]: https://github.com/euikuk-jeong/lumisshow/compare/v1.8.7...v1.9.0
[1.8.7]: https://github.com/euikuk-jeong/lumisshow/compare/v1.8.6...v1.8.7
[1.8.6]: https://github.com/euikuk-jeong/lumisshow/compare/v1.8.5...v1.8.6
[1.8.5]: https://github.com/euikuk-jeong/lumisshow/compare/v1.8.4...v1.8.5
[1.8.4]: https://github.com/euikuk-jeong/lumisshow/compare/v1.8.3...v1.8.4
[1.8.3]: https://github.com/euikuk-jeong/lumisshow/compare/v1.8.2...v1.8.3
[1.8.2]: https://github.com/euikuk-jeong/lumisshow/compare/v1.8.1...v1.8.2
[1.8.1]: https://github.com/euikuk-jeong/lumisshow/compare/v1.8.0...v1.8.1
[1.8.0]: https://github.com/euikuk-jeong/lumisshow/compare/v1.7.1...v1.8.0
[1.7.1]: https://github.com/euikuk-jeong/lumisshow/compare/v1.7.0...v1.7.1
[1.7.0]: https://github.com/euikuk-jeong/lumisshow/compare/v1.6.2...v1.7.0
[1.6.2]: https://github.com/euikuk-jeong/lumisshow/compare/v1.6.1...v1.6.2
[1.6.1]: https://github.com/euikuk-jeong/lumisshow/compare/v1.6.0...v1.6.1
[1.6.0]: https://github.com/euikuk-jeong/lumisshow/compare/v1.5.0...v1.6.0
[1.5.0]: https://github.com/euikuk-jeong/lumisshow/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/euikuk-jeong/lumisshow/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/euikuk-jeong/lumisshow/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/euikuk-jeong/lumisshow/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/euikuk-jeong/lumisshow/compare/v1.0.3...v1.1.0
[1.0.3]: https://github.com/euikuk-jeong/lumisshow/compare/v1.0.2...v1.0.3
[1.0.2]: https://github.com/euikuk-jeong/lumisshow/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/euikuk-jeong/lumisshow/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/euikuk-jeong/lumisshow/compare/v0.9.5...v1.0.0
[0.9.5]: https://github.com/euikuk-jeong/lumisshow/compare/v0.9.4...v0.9.5
[0.9.4]: https://github.com/euikuk-jeong/lumisshow/compare/v0.9.3...v0.9.4
[0.9.3]: https://github.com/euikuk-jeong/lumisshow/compare/v0.9.2...v0.9.3
[0.9.2]: https://github.com/euikuk-jeong/lumisshow/compare/v0.9.1...v0.9.2
[0.9.1]: https://github.com/euikuk-jeong/lumisshow/compare/v0.9.0...v0.9.1
[0.9.0]: https://github.com/euikuk-jeong/lumisshow/compare/v0.8.6...v0.9.0
[0.8.6]: https://github.com/euikuk-jeong/lumisshow/compare/v0.8.5...v0.8.6
[0.8.5]: https://github.com/euikuk-jeong/lumisshow/compare/v0.8.4...v0.8.5
[0.8.4]: https://github.com/euikuk-jeong/lumisshow/compare/v0.8.3...v0.8.4
[0.8.3]: https://github.com/euikuk-jeong/lumisshow/compare/v0.8.2...v0.8.3
[0.8.2]: https://github.com/euikuk-jeong/lumisshow/compare/v0.8.1...v0.8.2
[0.8.1]: https://github.com/euikuk-jeong/lumisshow/compare/v0.8.0...v0.8.1
[0.8.0]: https://github.com/euikuk-jeong/lumisshow/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/euikuk-jeong/lumisshow/compare/v0.6.1...v0.7.0
[0.6.1]: https://github.com/euikuk-jeong/lumisshow/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/euikuk-jeong/lumisshow/compare/v0.5.2...v0.6.0
[0.5.2]: https://github.com/euikuk-jeong/lumisshow/compare/v0.5.1...v0.5.2
[0.5.1]: https://github.com/euikuk-jeong/lumisshow/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/euikuk-jeong/lumisshow/compare/v0.4.3...v0.5.0
[0.4.3]: https://github.com/euikuk-jeong/lumisshow/compare/v0.4.2...v0.4.3
[0.4.2]: https://github.com/euikuk-jeong/lumisshow/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/euikuk-jeong/lumisshow/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/euikuk-jeong/lumisshow/compare/v0.3.8...v0.4.0
[0.3.8]: https://github.com/euikuk-jeong/lumisshow/compare/v0.3.7...v0.3.8
[0.3.7]: https://github.com/euikuk-jeong/lumisshow/compare/v0.3.6...v0.3.7
[0.3.6]: https://github.com/euikuk-jeong/lumisshow/compare/v0.3.5...v0.3.6
[0.3.5]: https://github.com/euikuk-jeong/lumisshow/compare/v0.3.4...v0.3.5
[0.3.4]: https://github.com/euikuk-jeong/lumisshow/compare/v0.3.3...v0.3.4
[0.3.3]: https://github.com/euikuk-jeong/lumisshow/compare/v0.3.2...v0.3.3
[0.3.2]: https://github.com/euikuk-jeong/lumisshow/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/euikuk-jeong/lumisshow/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/euikuk-jeong/lumisshow/compare/v0.2.6...v0.3.0
[0.2.6]: https://github.com/euikuk-jeong/lumisshow/compare/v0.2.5...v0.2.6
[0.2.5]: https://github.com/euikuk-jeong/lumisshow/compare/v0.2.4...v0.2.5
[0.2.4]: https://github.com/euikuk-jeong/lumisshow/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/euikuk-jeong/lumisshow/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/euikuk-jeong/lumisshow/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/euikuk-jeong/lumisshow/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/euikuk-jeong/lumisshow/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/euikuk-jeong/lumisshow/releases/tag/v0.1.0

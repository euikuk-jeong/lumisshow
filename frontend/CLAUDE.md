# frontend/CLAUDE.md

프론트엔드 상세 컨텍스트. 루트 → [`/CLAUDE.md`](../CLAUDE.md)

---

## 현재 구현 상태

별도 빌드 도구 없음. FastAPI가 `/assets/*`를 `StaticFiles`로 서빙하고 `/`, `/s/{token}/*`는 `index.html`을 반환한다 — `backend/main.py` 참고.

---

## 파일 구조

```
index.html                        # SPA 진입점, 클라이언트 라우팅
assets/js/
  router.js                       # URL 기반 페이지 전환
  api.js                          # fetch 래퍼 (admin Bearer / share 쿠키)
  auth.js                         # JWT 로컬스토리지, 쿠키 관리
  layout.js                       # admin shell 렌더 헬퍼
  utils.js                        # esc() HTML 이스케이프 등
  date-scroll-indicator.js        # 날짜별 보기 스크롤 중 년/월/일 배지 표시 (browse/album-edit/person-photos 공용)
  lightbox.js                     # Admin 전체크기 사진 뷰어 (openLightbox, browse/album-edit/tags/person-detail/person-photos 공용). 하단 "정보보기" 버튼으로 EXIF·태그 정보 패널(GET /api/admin/photo-info) 조회
  photo-zoom-viewer.js            # Admin 라이트박스·공유뷰어(album-view.js) 공용 줌/팬/핀치/스와이프 제스처 엔진 (createPhotoZoomViewer)
  tag-modal.js                    # Phase 9: 수동 태그 추가 모달(openAddTagModal, 자유 텍스트 입력+datalist 자동완성) + 일괄 적용/삭제 순차 헬퍼(applyTagToPhotos/deleteTagFromPhotos). admin-tags.js·admin-browse.js 공용
  pages/
    admin-login.js                # 로그인 폼
    admin-albums.js               # 앨범 목록
    admin-album-edit.js           # 앨범 편집 (사진·음악·공유링크)
    admin-browse.js               # 사진 탐색기 (폴더 트리, 다중 선택). Phase 8: 검색창이 파일명/태그 겸용(플레이스홀더만 변경, 매칭 로직은 백엔드)
    admin-people.js               # Phase 2: 인물 목록·미분류 얼굴 지정·AI 잡 트리거
    admin-person-detail.js        # Phase 2: 인물 상세 (추정 얼굴 교정, 인물 앨범 생성)
    admin-person-photos.js        # Phase 2: 인물 전체 사진 — 확정 얼굴만, 그리드/리스트/날짜별 보기·정렬 (라이트박스·슬라이드쇼 진입)
    admin-tags.js                  # Phase 5: 태그 목록(source별 필터·검색)·태그별 사진 그리드·AI 태그 재계산/폴더 태그 재계산 트리거. Phase 9: 그리드 다중선택(체크박스)+일괄 태그 추가/삭제(직접추가 소스만), 태그 추가 모달은 tag-modal.js 공용 모듈 사용
    album-view.js                 # 공유 링크 뷰어 메인
    share-auth.js                 # 공유 링크 패스워드 입력
    slideshow.js                  # 슬라이드쇼 엔진 (데이터 소스 provider: 공유 링크 / Admin 인물)
assets/css/
  base.css                        # 공통 변수·리셋·버튼·폼
  admin.css                       # Admin UI (앨범·탐색기·모달·음악 목록)
  viewer.css                      # 공유 뷰어
  slideshow.css                   # 슬라이드쇼 전환·Ken Burns·툴바·토스트
```

---

## 핵심 설계 결정

### 슬라이드쇼 전환 효과
CSS animation 우선(GPU 가속). `EFFECTS` 배열에서 랜덤 선택. 수동 이동(화살표/키보드/스와이프)도 동일한 효과 경로를 통과한다 — 별도 분기 없음.

### Ken Burns 효과
8개 방향 CSS `@keyframes` 사전 정의(`slideshow.css`), JS에서 랜덤 클래스 부착. `animation-duration`을 슬라이드 전환 시간과 동일하게 동적 설정. `scale` 범위: 1.08 → 1.15.

### 이미지 프리로드
현재 index N 표시 중 N+1, N+2 미리 로드. N-3 이전 `img.src = ''`으로 메모리 해제.

### 배경음악 플레이어 (다중 트랙)
- `album.music_count`, `album.music_names`, `album.music_tags` — ShareAlbumResponse에서 수신
- `GET /music/{token}?index=N` — 곡 인덱스로 스트리밍 요청
- 단일 트랙: `audio.loop = true`
- 복수 트랙: `ended` 이벤트로 자동 다음 곡, 이전/다음 버튼 표시
- 브라우저 정책: 첫 사용자 제스처(슬라이드쇼 시작) 이후 `audio.play()` 호출
- 음악 On/Off 상태는 `localStorage`의 `slideshow_settings`에 저장

### 트랙 표시 정보 (ID3 태그)
`trackDisplay(idx)` — `album.music_tags[idx]`(백엔드가 mutagen으로 읽은 title/artist/album/has_cover, `backend/services/music_tags.py`)를 우선 사용하고, 태그가 없거나 값이 비어 있으면 `music_names[idx]`(파일명, 확장자 제거)로 폴백한다. 커버 이미지는 `has_cover`가 true면 `GET /music/{token}/cover?index=N`(`media.py`), false면 정적 기본 이미지(`DEFAULT_MUSIC_COVER_URL = /assets/images/default-music-cover.png`)를 가리키는 URL을 만들어 넘긴다 — Admin 인물 슬라이드쇼는 음악 자체가 없어 `src.musicCoverUrl`이 정의되지 않으므로 이 경우만 `coverUrl`이 `null`(옵셔널 체이닝 가드). 음악 토스트(`showMusicToast()`)와 정보 패널(`renderInfoContent()`) 양쪽이 이 헬퍼 하나를 공유해 표시 로직이 갈라지지 않는다.

### 브랜드 아이콘
같은 `default-music-cover.png`를 Admin 로그인 화면 타이틀(`admin-login.js` `#login-title`)과 Admin 좌상단 타이틀(`layout.js` `.nav-brand`) 앞에도 로고처럼 재사용한다(`.brand-icon` 클래스, `admin.css`). 별도 로고 파일을 새로 만들지 않고 기존 자산을 공유.

### 슬라이드쇼 툴바 레이아웃
```
[음악그룹: On/Off | 이전곡 | 다음곡 | 볼륨] [spacer:flex-1] [일시정지 | ◀ | 1/N | ▶ | ↓ | i | ✕]
```
`.ss-music-group` 왼쪽 고정, `.ss-toolbar-spacer`(flex:1)로 재생 컨트롤 오른쪽 정렬.

### 음악 토스트
트랙 변경/재생 시작 시 `.ss-music-toast`에 `trackDisplay()` 결과(제목, 있으면 "제목 · 아티스트") 표시. 커버 이미지가 있으면 `#ss-music-toast-cover`(`<img>`, 태그 없을 땐 `display:none`)를 보이고 음표 아이콘(`#ss-music-toast-icon`)을 숨기는 식으로 서로 토글 — 두 엘리먼트 모두 정적 마크업에 미리 넣어두고 `style.display`만 바꾼다(런타임 DOM 생성 없음). 3초 후 `visible` 클래스 제거로 페이드 아웃. `clearTimeout`으로 중복 호출 시 타이머 리셋.

### 정보 패널 (i 버튼)
`renderInfoContent()` — 사진 EXIF 정보 + 태그(Phase 6) + (음악 재생 중이면) 구분선 + 음악 섹션(`trackDisplay()` 기반 제목/아티스트/앨범/트랙 번호 행 + 커버 이미지 `.ss-info-music-cover`). 트랙 변경·음악 토글 시 `refreshInfoPanel()`로 실시간 갱신.

태그 5개 행(인물/위치/태그/폴더명/직접 추가)은 `SharePhotoItem`의 `person_tags`/`location_tags`/`ai_tags`/`path_tags`/`manual_tags`를 그대로 표시 — 뷰어별 노출 범위(공유 링크는 기본적으로 person/location 비노출, 단 앨범 설정의 "태그 모두 표시"를 켜면 해당 앨범만 person/location도 포함)는 백엔드(`services/photo_tags.py`, `routers/share.py`의 `albums.show_all_tags` 분기)가 이미 걸러 보내므로 프론트에서 재분기하지 않는다.

**Admin 라이트박스(`lightbox.js`)의 "정보보기" 버튼**(하단 액션 바, `#lb-btn-info`): 슬라이드쇼와 달리 라이트박스는 사진 목록을 경로 문자열 배열로만 받아(EXIF·태그 미포함) 열리므로, 버튼 클릭 시 `GET /api/admin/photo-info?path=`로 사진 1장분을 그때그때 조회한다. 원래 뷰포트 좌상단 플로팅 아이콘이었으나 `.lightbox-body`가 stacking 순서상 위에 그려져 클릭이 막혀(2026-08) 하단 액션 버튼으로 이동함 — 단축키 `i`는 유지. 캐싱은 하지 않는다 — admin-tags.js의 "+ 태그 추가"(`extraAction`)로 패널이 열린 채 태그가 바뀔 수 있어, 캐시를 두면 갱신 후에도 이전 태그 목록이 남아있는 문제가 생긴다. 응답이 도착했을 때 패널이 이미 닫혔거나 다른 사진으로 넘어갔으면(`localPaths[idx] !== path`) 버린다. Admin 전용이라 `person_tags`/`location_tags`도 함께 채워져 인물 태그가 표시된다(백엔드 `ADMIN_INFO_PANEL_SOURCES`) — 단, 설정에서 AI 인식 카테고리를 꺼두면(v2.1.0+) DB에 남아있어도 해당 source는 백엔드가 제외하고 보낸다(`enabled_sources()`).

### 음악 파일 선택 모달 (Admin)
- `GET /api/admin/music` → 서버 목록 로드
- `checkbox change` 이벤트를 단일 진실 공급원으로 사용 (stopPropagation 미사용)
- `confirm` 버튼 리스너는 API 호출 전 등록 (await 전)
- `onConfirm` 콜백으로 `musicPaths` 배열 교체 후 `refreshMusicList()`

### 음악 목록 드래그앤드롭
HTML5 DnD (`draggable="true"` + `dragstart/dragover/dragleave/drop/dragend`). `dragstart`에서 `setTimeout` 지연으로 ghost 이미지 캡처 후 `.dragging` 스타일 적용. 인덱스 보정: 앞→뒤 이동 시 `splice` 후 `idx - 1`에 삽입.

### 앨범 편집 설정 자동저장 (`admin-album-edit.js`, `createAutosave()`)
"기본 정보" 카드 안에 폼이 두 개(`info-form`: 이름·설명 / `style-form`: 태그 모두 표시·앨범 테마·폰트·배경음악) + "슬라이드쇼 기본 설정" 카드의 `ss-form`(전환시간·재생순서·전환효과·배경음악 ON/OFF·음량·반복재생), 총 3개 폼 모두 저장 버튼 없이 필드 변경 시 자동 저장(`PUT /api/admin/albums/{id}`, 3개 폼 동일 endpoint). 필드 변경마다 600ms debounce 후 저장, 진행 중 다시 필드가 바뀌면(`pending` 플래그) 현재 요청 끝난 뒤 최신 값으로 한 번 더 저장 — 재귀 호출 대신 `do…while(pending)` 루프로 처리(재귀 시 `finally`가 중첩 호출보다 먼저 실행돼 `isSaving` 상태가 꼬이는 문제 있었음). 폼 하나당 자동저장 트리거 함수 하나(`scheduleInfoSave`/`scheduleStyleSave`/`scheduleSsSave`)를 상위 스코프에서 만들어 음악 리스트 추가·삭제·재정렬, 테마 스와치 클릭, 폰트 드롭다운 변경 등 폼 외부 이벤트에서도 재사용한다. `ui_theme`은 원래 `ss-form`에 있었으나(2026-08) "화면이 어떻게 보일지"를 고르는 시각적 설정이라는 이유로 폰트 신설과 함께 `style-form`으로 이동했다.

### 앨범 타이틀 폰트 (`title-fonts.js`, `.viewer-title` 전용)
공유 앨범 히어로 타이틀(`.viewer-title`, `album-view.js`)에만 적용되는 display 폰트 — Admin 화면·슬라이드쇼는 대상이 아니다. `TITLE_FONTS`(한글 지원 Google Fonts 5종 고정: 명조체 Gowun Batang/손글씨체 Gaegu/고딕체 Jua/귀엽다·상큼체 Gamja Flower/레트로·빈티지 Poor Story — 그릴링으로 카테고리별 인기 후보 3종 중 확정, 각 항목의 `note` 필드가 어떤 스타일에 어울리는지 한 줄 설명) + `ensureTitleFontsLoaded()`(idempotent `<link>` 동적 삽입) + `applyTitleFont(el, fontId)`(인라인 `font-family`/`font-weight` 적용, 폰트별 실제 지원 weight만 사용 — 단일 weight 폰트에 700을 강제하면 브라우저가 synthetic bold를 그려 특히 손글씨체가 어색해짐)를 `album-view.js`(뷰어)와 `admin-album-edit.js`(편집 화면 미리보기)가 공용한다. 앨범 값(`album.title_font`, nullable = "시스템 기본")은 `admin-album-edit.js`의 `style-form`에서 드롭다운으로 고른다. 손글씨체 대표 폰트가 기존 `nanum-pen`에서 `gaegu`로 교체됨에 따라 id 자체가 바뀌었고, DB에 남은 구 값은 `backend/models/database.py`의 `_migrate_legacy_title_font()`가 기동 시 일괄 변환한다.

- **뷰어**: `album.title_font`가 설정된 앨범만 `ensureTitleFontsLoaded()` 호출 — 시스템 기본을 쓰는 앨범 방문자는 Google Fonts CDN 요청이 아예 발생하지 않는다.
- **Admin 편집 화면**: 드롭다운으로 5종 중 아무거나 골라볼 수 있어야 하므로 화면 진입 시 무조건 `ensureTitleFontsLoaded()` 호출 — 이 화면에 한해서만 admin이 외부 CDN 요청을 만든다(다른 admin 화면은 여전히 0건 유지). 미리보기(`#title-font-preview`)는 앨범 이름 입력값을 실시간으로 반영하고, 바로 아래 `#title-font-note`가 선택된 폰트의 `note`(어떤 스타일에 어울리는지)를 표시한다(`updateTitleFontPreview()`, 이름 입력·폰트 선택 양쪽에서 즉시 갱신, 저장 debounce와 무관). 드롭다운 옵션 텍스트 자체는 "명조체 (Gowun Batang)"처럼 짧게 유지하고 설명은 이 note 영역에만 둔다 — `<option>`은 긴 문장을 담기에 부적합하다는 판단.

### 앨범 스타일 AI 추천 버튼 (`admin-album-edit.js`, `bindStyleSuggest`)
"기본 정보" 카드의 이름/설명 필드 바로 아래(`#ai-suggest-area`)에 배치. **버튼은 항상 렌더링** — 화면 진입 시 `GET /api/admin/llm/settings`로 provider+API 키 등록 여부를 조회하는 동안은 `disabled` + "불러오는 중..." 문구, 조회 결과 미설정이면 계속 `disabled` + 버튼 바로 아래(`#ai-suggest-hint`)에 "설정에서 키를 등록하면 이용할 수 있습니다" 안내(설정 화면 링크 포함), 설정되어 있으면 버튼 활성화 + 안내 문구를 전송 범위 고지("사진은 보내지 않음")로 교체한다 — 버튼 자체를 통째로 숨기지 않는 이유는 "기능이 있다는 것"을 항상 보여주고 왜 못 쓰는지를 그 자리에서 설명하기 위해서다. 클릭 시 그 시점의 이름/설명 입력값(아직 저장 안 됐어도 무방 — 저장된 앨범 값이 아니라 필드 자체를 읽음)을 `POST /api/admin/llm/suggest-style`로 보내고, 결과를 제안 카드(`renderSuggestCard`, `.ai-suggest-card`)로 표시한다. 백엔드 설계는 [`backend/CLAUDE.md`](../backend/CLAUDE.md)의 "앨범 스타일 AI 추천" 항목 참고.

- **"적용" 버튼은 3개 필드를 한 번에 반영**: 음악은 `musicCtl.setMusicPaths([music_path])`로 기존 목록을 통째로 교체(추가 아님, 카드 문구로 명시), 테마는 `#f-ui-theme` 히든 입력값 갱신 + `#album-theme-picker`의 `.theme-swatch.active` 클래스를 직접 토글(테마 피커는 자기 자신의 클릭 핸들러로만 active를 관리하므로 값만 바꿔서는 하이라이트가 안 움직인다), 폰트는 `#f-title-font` 값 갱신 후 `updateTitleFontPreview()` 재호출. 셋 다 반영한 뒤 `scheduleStyleSave()` 한 번만 호출해 기존 자동저장 debounce 경로를 그대로 탄다. `null`로 온 필드(후보 목록에 없어 서버가 걸러낸 값)는 건드리지 않아 사용자가 이미 골라둔 값이 지워지지 않는다. 음악 라벨은 파일명이 아니라 `BUNDLED_MUSIC_CREDITS`로 찾은 "무드 — 곡명"(음악 선택 모달과 동일 표기, 매칭 실패 시 파일명 폴백). `bindStyleSuggest`가 provider 조회 `await` 중 다른 화면으로 이동했을 수 있어 재개 직후 `#ai-suggest-area`가 여전히 같은 DOM인지 확인 후 진행(lightbox.js의 photo-info stale 응답 가드와 동일 패턴). 실브라우저에서 `fetch` 스텁으로 제안 카드 렌더링→적용→새로고침 후 서버 반영까지 확인 완료.
- **버튼 노출 여부는 매 진입마다 재조회** — 캐시하지 않음. 설정 화면에서 방금 키를 등록했어도 이 화면은 별도 페이지 로드이므로 새로 물어본다.

### 전체화면 사진 뷰어 제스처 (`photo-zoom-viewer.js`)
Admin 라이트박스(`lightbox.js`)와 공유뷰어(`album-view.js`의 `_openSharePhotoViewer`)가 휠 줌·더블클릭 줌·핀치 줌·드래그 팬·스와이프 넘기기·마우스 가운데 버튼 리셋을 공용 모듈로 공유한다(슬라이드쇼는 대상 아님 — Ken Burns 자동 효과만 있고 사용자 줌이 없음).

- **Pointer Events 통합**: mousedown/touchstart 등을 따로 두지 않고 pointerdown/move/up/cancel 하나로 마우스·터치를 함께 처리한다. `bodyEl`(뷰어 뷰포트)에 바인딩 — `imgEl`에 바인딩하면 letterbox 여백에서 제스처가 씹힌다.
- **이미지 로드·인덱스 이동을 모듈이 소유**: 버튼 클릭·키보드·스와이프 커밋이 모두 `goTo(idx)` 한 경로를 통과하고, 새 이미지의 `load` 이벤트가 발생한 뒤에만 idx를 갱신한다. 스와이프 커밋 시 이 순서를 지키지 않으면 peek 이미지가 슬라이드로 도착하는 시점과 실제 이미지 교체 시점이 어긋나 깜빡임이 생긴다. 캡션·카운터·정보패널 등 idx 종속 UI 갱신은 `onIndexChanged(idx)` 콜백으로 호출자에게 위임한다.
- **peek 슬라이드 애니메이션**: `peekPrevEl`/`peekNextEl`을 넘기면 스와이프 중 이전/다음 사진이 화면 밖에서 따라오다 완료 시 제자리로 스냅한다(`.pv-snapping`, `base.css`). 넘기지 않으면 스와이프 시 즉시 전환.
- **줌 배율**: 최대 6×, 더블클릭 시 2×(양쪽 동일). 스와이프 넘기기는 터치 전용 — 마우스 드래그로는 넘기지 않는다.
- **휠 줌 예외 영역**: `scrollableSelector` 옵션으로 지정한 셀렉터(예: `.lightbox-info`) 안에서는 휠이 확대/축소 대신 그 요소 자체 스크롤로 동작한다.
- **모듈이 관여하지 않는 것**: 배경 클릭 닫기(양쪽 다 없음 — 2026-08 통일 시 제거), 확대 중 이전/다음 버튼 숨김(`onZoomChange` 콜백으로 각 뷰어가 직접 결정 — 공유뷰어만 적용, 라이트박스는 원래부터 없던 동작이라 유지), 확대 중 화살표 키 이동 가능 여부(공유뷰어는 막고 라이트박스는 허용 — 기존 동작 유지, 리팩터링 시 의도적으로 통일하지 않음).

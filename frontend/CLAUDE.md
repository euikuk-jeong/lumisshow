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
  pages/
    admin-login.js                # 로그인 폼
    admin-albums.js               # 앨범 목록
    admin-album-edit.js           # 앨범 편집 (사진·음악·공유링크)
    admin-browse.js               # 사진 탐색기 (폴더 트리, 다중 선택)
    admin-people.js               # Phase 2: 인물 목록·미분류 얼굴 지정·AI 잡 트리거
    admin-person-detail.js        # Phase 2: 인물 상세 (추정 얼굴 교정, 인물 앨범 생성)
    admin-person-photos.js        # Phase 2: 인물 전체 사진 — 확정 얼굴만, 그리드/리스트/날짜별 보기·정렬 (라이트박스·슬라이드쇼 진입)
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
- `album.music_count`, `album.music_names` — ShareAlbumResponse에서 수신
- `GET /music/{token}?index=N` — 곡 인덱스로 스트리밍 요청
- 단일 트랙: `audio.loop = true`
- 복수 트랙: `ended` 이벤트로 자동 다음 곡, 이전/다음 버튼 표시
- 브라우저 정책: 첫 사용자 제스처(슬라이드쇼 시작) 이후 `audio.play()` 호출
- 음악 On/Off 상태는 `localStorage`의 `slideshow_settings`에 저장

### 슬라이드쇼 툴바 레이아웃
```
[음악그룹: On/Off | 이전곡 | 다음곡 | 볼륨] [spacer:flex-1] [일시정지 | ◀ | 1/N | ▶ | ↓ | i | ✕]
```
`.ss-music-group` 왼쪽 고정, `.ss-toolbar-spacer`(flex:1)로 재생 컨트롤 오른쪽 정렬.

### 음악 토스트
트랙 변경/재생 시작 시 `.ss-music-toast`에 파일명(확장자 제거) 표시 → 3초 후 `visible` 클래스 제거로 페이드 아웃. `clearTimeout`으로 중복 호출 시 타이머 리셋.

### 정보 패널 (i 버튼)
`renderInfoContent()` — 사진 EXIF 정보 + (음악 재생 중이면) 구분선 + 음악 섹션. 트랙 변경·음악 토글 시 `refreshInfoPanel()`로 실시간 갱신.

### 음악 파일 선택 모달 (Admin)
- `GET /api/admin/music` → 서버 목록 로드
- `checkbox change` 이벤트를 단일 진실 공급원으로 사용 (stopPropagation 미사용)
- `confirm` 버튼 리스너는 API 호출 전 등록 (await 전)
- `onConfirm` 콜백으로 `musicPaths` 배열 교체 후 `refreshMusicList()`

### 음악 목록 드래그앤드롭
HTML5 DnD (`draggable="true"` + `dragstart/dragover/dragleave/drop/dragend`). `dragstart`에서 `setTimeout` 지연으로 ghost 이미지 캡처 후 `.dragging` 스타일 적용. 인덱스 보정: 앞→뒤 이동 시 `splice` 후 `idx - 1`에 삽입.

# ai_worker/CLAUDE.md

AI 얼굴 인식 워커 상세 컨텍스트. 루트 → [`/CLAUDE.md`](../CLAUDE.md), 설계 → `doc/design-phase2.md` (로컬 전용)

---

## 역할

별도 컨테이너(`lumisshow-ai`)로 실행되는 배치 워커. PHOTO_ROOT를 증분 스캔해
InsightFace(buffalo_l: SCRFD 검출 + ArcFace 512-d 임베딩)로 얼굴을 추출하고,
등록(enrollment)된 인물과 cosine similarity로 매칭해 `$DATA_DIR/db/ai.db`에 기록한다.
LumisShow 본체는 ai.db를 읽어 인물 앨범 기능을 제공한다 (M3).

## 실행

```bash
pip install -r ai_worker/requirements.txt

# 환경변수: PHOTO_ROOT, DATA_DIR (LumisShow와 동일 값 공유)
python -m ai_worker.main scan      # 증분 스캔 → 분석 → 매칭 (1회)
python -m ai_worker.main rematch   # 등록 셋 변경 후 전체 재매칭

# 라벨링/평가 (M1 정답 셋)
python -m ai_worker.tools.label_sheet             # $DATA_DIR/label_sheet.html 생성
#   → 브라우저에서 클러스터별 이름 입력 → labels.csv 다운로드
python -m ai_worker.tools.label_helper import labels.csv
python -m ai_worker.tools.eval --enroll 10

# CSV 직접 라벨링 (시트 없이)
python -m ai_worker.tools.label_helper export labels.csv
```

## 파일 구조

```
config.py    # 환경변수 (AI_MATCH_THRESHOLD, AI_DET_SIZE, AI_SCAN_HOUR...)
daemon.py    # 데몬 모드: 야간 자동 스캔 + jobs 큐 폴링, stale 잡 복구
db.py        # ai.db 스키마/연결 (sqlite3 동기, WAL)
scanner.py   # PHOTO_ROOT 증분 스캔 (path+mtime, @eaDir 제외)
pipeline.py  # InsightFace lazy 로드, 사진 1장 분석→기록 (1장=1커밋, resumable)
matcher.py   # cosine 매칭 (numpy brute-force), 임베딩 BLOB 변환
notify.py    # Discord webhook 알림 (AI_DISCORD_WEBHOOK_URL)
main.py      # CLI: scan(--limit) | rematch | daemon
tools/       # label_helper.py (CSV 라벨링), eval.py (precision/recall)
```

## 핵심 설계 결정

### ai.db 쓰기 주체 분리 (SQLite 동시성 회피)
- **워커가 쓰는 테이블**: `photos_analyzed`, `faces`, `face_matches` (+`jobs.status` 갱신)
- **LumisShow가 쓰는 테이블**: `persons`, `face_labels`, `jobs`, `ai_settings`
- 유효 인물 판정: `face_labels` 있으면 그 값(사람 확정), 없으면 `face_matches`
- `face_labels.person_id = NULL`은 "등록 인물 아님(무시)" 라벨
- **예외**: `backend/routers/admin_people.py`의
  `POST /api/admin/people/path-repairs/{id}/approve`(-all)는 on-demand·저빈도 관리자
  액션이라 예외적으로 `photos_analyzed.path`/`faces.photo_path`를 직접 UPDATE한다
  (admin이 승인한 rename/move 제안 반영, WAL+busy_timeout으로 워커와의 동시 쓰기 직렬화)

### 경로 rename/move 복구 — 제안 후 admin 승인
`scanner.pending_photos()`가 매 스캔(야간/수동)마다 같은 walk 결과로
`queue_rename_proposals()`를 실행해 사라진 경로를 basename 1:1 매칭만 탐지, `pending_path_repairs`
테이블에 제안으로 쌓는다(`source='scan'`). **즉시 UPDATE하지 않는다** — admin이
Admin People 화면(또는 `GET/POST /api/admin/people/path-repairs*`)에서 승인해야
`photos_analyzed.path`/`faces.photo_path`가 실제로 바뀐다(face_id 유지 → `face_labels` 보존).
승인 대기 중인 new_path는 `pending_photos()`가 분석 대상에서 제외해 "신규 사진"으로
오분석되지 않도록 막는다. PHOTO_ROOT가 언마운트 등으로 완전히 비어 보이면(walk 결과
0건 + 기존 분석 데이터 있음) 전체 삭제로 오인하지 않도록 그 스캔 자체를 스킵한다.
동명 파일 등 후보가 2개 이상이면 제안하지 않고 orphan으로 남기며, 이 경우 admin이
`POST /api/admin/people/repair-paths`로 즉시 재스캔하거나 not_found/ambiguous 현황을
확인할 수 있다. 제안 거부(dismiss)는 `pending_path_repairs` row 자체를 삭제한다 —
`status='rejected'`로 영구 고정하면 `old_path` UNIQUE 제약 때문에 다음 스캔이 같은
rename을 재제안할 수 없고, 그 사이 new_path가 일반 스캔으로 별개 사진 분석돼버리면
승인 시도해도 409(이미 분석됨)로 되돌릴 방법이 없었다. row를 지우면 다음 스캔에서
조건이 같으면 다시 제안되거나, new_path가 이미 분석돼버렸으면 old_path는 not_found로
재분류돼 orphan-cleanup 제안으로 넘어간다.

### 완전 삭제(orphan) 정리 — 제안 후 admin 승인
rename 후보가 전혀 없는(basename이 현재 PHOTO_ROOT 어디에도 없는) 경로는 "파일이 진짜로
사라졌다"고 보고 `scanner.queue_orphan_proposals()`(야간 스캔) 또는 수동 `repair-paths`
스캔이 `pending_orphan_cleanups`에 삭제 제안으로 쌓는다(`old_path`/`new_path` 개념이
없어 `pending_path_repairs`와는 별도 테이블). rename과 동일하게 **즉시 삭제하지 않는다**
— admin이 `GET/POST /api/admin/people/orphan-cleanups*`에서 승인해야
`photos_analyzed`/`faces`(ai.db, `faces` 삭제는 FK CASCADE로 `face_labels`/`face_matches`도
함께 삭제)와 `photo_meta_cache`(app.db, EXIF 캐시)가 함께 삭제된다. 승인 시점에 파일이
다시 나타났으면(레이스) 409로 거부하고 제안을 그대로 남긴다. 후보가 2개 이상(ambiguous)인
경로는 orphan 삭제 제안 대상이 아니다 — 어디로 옮겨갔는지 불확실한 상태에서 삭제를
제안하면 안 되기 때문. 이 기능은 EXIF를 별도 파일(사본)로 저장하는 외부 앱을 쓰다가
그 사본을 지운 경우처럼, AI가 사본을 별개 사진으로 분석해버려 인물 사진 목록에
중복 항목이 남는 상황을 정리하기 위해 추가됐다.

### Discord 알림 (daemon 모드 전용)
`AI_DISCORD_WEBHOOK_URL` 설정 시 scan/rematch 완료 후 `notify.py`가 webhook으로 요약을
전송한다(사진 수/얼굴 수/에러 수/경로 변경·삭제 승인 대기 건수/소요시간 + `BASE_URL`로
만든 `/admin/people` 링크). daemon.py의 jobs 트리거 처리와 야간 자동 스캔 양쪽에서
호출되며, `python -m ai_worker.main scan` CLI 직접 실행은 알림 대상이 아니다
(터미널로 직접 결과를 보는 상황이라 불필요). 전송 실패는 로그만 남기고 삼켜 daemon
루프에 영향 주지 않는다. `run_scan()`이 리포트하는 경로 변경/삭제 건수는 "이번 스캔의
신규 발생분"이 아니라 `pending_path_repairs`/`pending_orphan_cleanups`의
`status='pending'` **전체 누적 건수**다 — 두 테이블 모두 admin이 승인/거부하기 전까지
ai.db에 영구 보관되므로 별도 이력 저장 없이 그대로 조회하면 된다(과거 스캔에서 쌓이고
아직 처리 안 된 것도 포함).
Discord 일반 메시지 본문은 `[텍스트](url)` 마크다운 링크를 렌더링하지 않음(임베드 전용) —
raw URL을 그대로 붙여 자동 링크화에 의존한다.
urllib 기본 User-Agent(`Python-urllib/x.x`)는 Discord(Cloudflare)가 403으로 차단하므로
`notify.py`에서 커스텀 User-Agent 헤더를 명시한다.
전송 실패 시 최대 3회 시도(2초 간격 고정 딜레이), 3회 모두 실패하면 로그만 남기고
포기한다(daemon 루프를 막지 않기 위해 예외를 밖으로 던지지 않음).

### photo_tags — 워커·백엔드 상시 동시 쓰기 첫 테이블
사물/장면/위치/폴더명/인물 태그(`doc/tagging_requirement.md`). 기존 테이블은 전부
워커 전용/백엔드 전용으로 쓰기 주체가 나뉘어 있었으나(예외는 path-repair 승인뿐),
`photo_tags`는 워커가 야간 스캔 중 `ai`/`path`/`location`을 상시 쓰고 백엔드는 얼굴
라벨링 시 `person`(+수동 태깅 시 `manual`)을 상시 쓰는 첫 상시 동시 쓰기 테이블이다.
기존과 동일하게 WAL + busy_timeout으로 직렬화한다. `UNIQUE(photo_path, tag, source)` —
source를 키에 포함해 서로 다른 source의 동일 텍스트가 별개 행으로 공존 가능(예:
GPS `location='서울'` + 폴더명 `path='서울'`).

`source='person'` 동기화(`backend/routers/admin_people.py`의 `_sync_person_tag`)는
확정 라벨(`face_labels`)에만 반응한다 — `face_matches`(AI 추정)는 반영하지 않는다
(승인 큐 취지와 충돌 방지). face_labels를 쓰는 모든 지점(단건/배치 라벨링·해제,
사진 단위 해제, 점수 기준 일괄 확정)과 인물 삭제·이름변경, 경로 복구
(`_apply_path_repair`)·orphan 정리(`_apply_orphan_cleanup`)가 전부 이 헬퍼 또는
직접 UPDATE/DELETE를 거쳐야 한다 — 헬퍼 미경유 시 태그가 stale하게 남거나 조기
삭제될 수 있다. 기존(이 컬럼 도입 이전) face_labels 분은 `init_ai_db()`의
`INSERT ... ON CONFLICT DO NOTHING` 소급 쿼리로 1회성 backfill한다(매 시작마다
실행해도 idempotent).

### 경로 규약
`faces.photo_path`, `photos_analyzed.path`는 **PHOTO_ROOT 상대 경로 + `/` 구분자**
(backend의 `photo_meta_cache.file_path` 관례와 동일).

### resumable 파이프라인
사진 1장 = 1 트랜잭션 커밋. 중단 후 재실행하면 `photos_analyzed`에 없는(또는
mtime이 바뀐) 사진만 다시 처리한다. EXIF 회전 보정 후 분석하며, 실패한 사진은
`status='error'`로 기록해 무한 재시도를 막는다.

### 모델/의존성 lazy import
`insightface`는 `pipeline.py` 안에서만 import. scanner/matcher/db 단위 테스트는
모델 설치 없이 실행 가능 (`tests/test_ai_worker_*.py`).

### 라이선스 주의
buffalo_l 사전학습 가중치는 **non-commercial** — 본 프로젝트는 개인/가족용으로 확정.
공개 배포 이미지에 가중치를 포함하지 말 것 (첫 실행 시 자동 다운로드 방식 유지).

## Phase 2 마일스톤 현황

- [x] M1 뼈대: 스캔→검출→임베딩→매칭 파이프라인 + 라벨링/평가 도구
- [x] M1 검증: 샘플 1,000장·정답 셋 44명/1,235라벨 — **threshold 0.45에서 precision 99.9%/recall 97.9%**
      (타인 음성 샘플은 미측정 → 운영 교정 로그로 보완 예정)
- [x] M2 구현: daemon 모드(야간 스케줄+jobs 폴링), Dockerfile.ai, compose 서비스, release.yml 워커 이미지
- [ ] M2 배포: NAS 컨테이너 기동 + 초기 전체 인덱싱 (5만 장, 야간 배치 며칠)
- [x] M3: backend `admin_people.py`(인물 CRUD·라벨 교정·크롭 서빙·잡 트리거) +
      Admin 'People' UI(목록/상세 교정/미분류 지정/인물 앨범 생성)
- [ ] M4: 실사용 튜닝 (교정 로그 지표, 시간 기반 후처리)

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
python -m ai_worker.main scan          # 증분 스캔 → 분석 → 매칭 (1회)
python -m ai_worker.main rematch       # 등록 셋 변경 후 전체 재매칭
python -m ai_worker.main tag-backfill  # AI 태그/위치 재계산 (어휘·threshold 변경 후,
                                        # 또는 이 기능 도입 이전 사진 소급 적용)

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
config.py     # 환경변수 (AI_MATCH_THRESHOLD, AI_DET_SIZE, AI_SCAN_HOUR...)
daemon.py     # 데몬 모드: 야간 자동 스캔 + jobs 큐 폴링, stale 잡 복구
db.py         # ai.db 스키마/연결 (sqlite3 동기, WAL)
scanner.py    # PHOTO_ROOT 증분 스캔(path+mtime, @eaDir 제외) + 폴더명 Kiwi 태깅(커버리지 방식)
pipeline.py   # InsightFace lazy 로드, 사진 1장 분석→기록(1장=1커밋, resumable), GPS EXIF 추출
geocoder.py   # GPS→(도시,국가) 역지오코딩(reverse_geocoder, 오프라인), photo_tags(location) 동기화
tagger.py     # CLIP zero-shot 이미지/텍스트 인코딩(onnxruntime+tokenizers), 모델 자동 다운로드
tag_vocab.py  # CLIP 태그 어휘(80개, {prompt: 영어, label: 한국어})
matcher.py    # cosine 매칭 (numpy brute-force), 임베딩 BLOB 변환
notify.py     # Discord webhook 알림 (AI_DISCORD_WEBHOOK_URL)
main.py       # CLI: scan(--limit) | rematch | daemon
tools/        # label_helper.py (CSV 라벨링), eval.py (precision/recall)
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
전송한다(사진 수/얼굴 수/위치·태그 반영 건수/폴더명 태깅 건수/에러 수/경로 변경·삭제
승인 대기 건수/소요시간 + `BASE_URL`로 만든 `/admin/people` 링크). scan()은 얼굴 인식과
GPS 위치·CLIP AI 태그·폴더명(Kiwi) 태깅을 사진 1장 단위로 함께 처리하는 단일 파이프라인
(`pipeline.analyze_and_store()`)이라, 알림 요약도 얼굴 결과만이 아니라 이 값들을 전부
포함한다. daemon.py의 jobs 트리거 처리와 야간 자동 스캔 양쪽에서 호출되며,
`python -m ai_worker.main scan` CLI 직접 실행은 알림 대상이 아니다(터미널로 직접 결과를
보는 상황이라 불필요). 전송 실패는 로그만 남기고 삼켜 daemon 루프에 영향 주지 않는다.
`run_scan()`이 리포트하는 경로 변경/삭제 건수는 "이번 스캔의 신규 발생분"이 아니라
`pending_path_repairs`/`pending_orphan_cleanups`의 `status='pending'` **전체 누적
건수**다 — 두 테이블 모두 admin이 승인/거부하기 전까지 ai.db에 영구 보관되므로 별도
이력 저장 없이 그대로 조회하면 된다(과거 스캔에서 쌓이고 아직 처리 안 된 것도 포함).

`notify_scan_result()`는 **증분이 있을 때만** 전송한다(2026-08-02 사용자 피드백 — 매
스캔 무조건 전송하면 증분 없는 날도 pending 누적치가 그대로 와서 소음이 됨). 이번
스캔에서 새로 처리한 사진이 있거나(`photos`/`path_tagged` > 0) 경로 변경·삭제 승인
대기 누적 건수가 직전 발송 시점과 달라졌을 때만 보낸다. 직전 발송값은 `ai_settings`가
아니라 `$DATA_DIR/notify_state.json`에 저장한다 — `ai_settings`는 LumisShow 전용
쓰기 영역(아래 "ai.db 쓰기 주체 분리" 참고)이라 워커 내부 상태를 거기 쓰면 안 된다.
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

`photo_embeddings`(CLIP 이미지 벡터, Phase 3)도 같은 예외 패턴을 따른다 — 워커가
매 스캔 `INSERT/UPDATE`하는 기본 소유자지만, `admin_people.py`의 경로복구 승인
(`_apply_path_repair`, `UPDATE photo_path`)과 orphan 정리 승인(`_apply_orphan_cleanup`,
`DELETE`)이 path-repair와 동일한 저빈도 관리자 액션 근거로 backend에서도 건드린다.
`photo_tags`처럼 상시 동시 쓰기는 아니고, 기존 path-repair 예외의 연장선.

### GPS 위치 태깅 (`geocoder.py`) — 오프라인, 도시는 영문·국가만 한국어
`pipeline.FacePipeline.analyze()`가 `ImageOps.exif_transpose()` 호출 **전**
원본 이미지에서 GPS EXIF를 읽는다(transpose 이후 이미지는 exif가 유실될 수 있음).
좌표가 있으면 `geocoder.reverse_geocode()`(reverse_geocoder, GeoNames 기반 오프라인
KD-tree)로 (도시, 국가)를 얻어 `photo_locations`(정본)에 기록하고,
`geocoder.sync_location_tag()`가 `photo_tags(source='location')`에 city/country를
각각 별도 행으로 복제한다(하나로 합치면 "서울" 단독 검색이 안 됨). GPS가 없거나
역지오코딩이 실패하면(둘 다 best-effort — 얼굴 분석 성공 여부에 영향 없음)
`photo_locations` 행을 지운다.

도시명은 reverse_geocoder가 주는 로마자(예: "Seoul") 그대로 쓴다 — 오프라인으로
한국어 도시명을 구할 저비용 방법이 없다(2026-08-02 확인). 국가는 ISO 3166-1
alpha-2 코드를 `geocoder._COUNTRY_NAMES_KO` 정적 매핑으로 한국어 국가명으로
바꾼다(매핑에 없으면 코드 그대로 폴백).

`RGeocoder`는 인스턴스 생성마다 ~30MB CSV를 다시 읽고 KD-tree를 재구축하므로
(`reverse_geocoder.search()`가 매 호출 새 인스턴스를 만듦) 모듈 전역에 1회만
만들어 재사용한다(`_get_geocoder()`). `mode=1`(단일 스레드)을 써서 `mode=2`가
요구하는 `if __name__ == "__main__":` 가드 없이도 워커 루프 안에서 안전하게 호출한다.

### 폴더명 태깅 (Kiwi, `scanner.py`) — 커버리지 방식, mtime과 무관
`scanner.tag_paths_from_folder_names()`는 `photo_tags`에 `source='path'` 행이
하나도 없는 `photos_analyzed` 사진만 골라 바로 위 폴더명 1단계를 Kiwi 형태소
분석기(명사 NNG/NNP만, 1음절은 접미 파편으로 보고 제외)로 분석해 태깅한다.
`pending_photos()`(mtime 기반)와 완전히 독립적으로 동작 — 이 기능 도입 이전
사진(기존 4.5만 장)이나 경로복구 승인 이후(아래 참고) new_path도 다음 스캔에서
자연히 채워진다. 같은 폴더는 1회만 Kiwi를 실행해 재사용(폴더 단위 캐싱).
명사가 하나도 안 나오는 폴더(순수 영문/숫자 등)의 사진은 태그가 영원히 안
생겨 매 스캔 재시도되는데, Kiwi 호출 자체가 저렴해 감수하기로 함(최적화 보류).

`admin_people.py`의 `_apply_path_repair`(경로복구 승인)는 `source='path'` 태그를
new_path로 갱신하지 않고 **지우기만** 한다 — Kiwi는 워커 전용 무거운 의존성이라
backend에서 재계산할 수 없기 때문. 지운 뒤 다음 워커 스캔의 커버리지 로직이
new_path 폴더명으로 다시 채운다. `location`/`ai`/`manual`/`person` 태그와
`photo_embeddings`는 사진 콘텐츠 자체 정보라 경로가 바뀌어도 유효하므로 그대로
`UPDATE`한다.

### 사물/장면 태깅 (CLIP, `tagger.py`/`tag_vocab.py`) — scan()은 신규/변경 사진만
`pipeline.analyze_and_store()`가 얼굴 검출과 같은 이미지(이미 exif_transpose까지
끝난 것)로 CLIP 이미지 임베딩을 계산해 `photo_embeddings`에 캐시하고,
`tag_vocab.TAG_VOCAB`(80개, 텍스트 임베딩은 `run_scan()`에서 스캔당 1회만 계산해
재사용) 대비 코사인 유사도가 threshold 이상인 태그를 `photo_tags(source='ai')`에
기록한다. 재분석 시 기존 'ai' 태그는 지우고 현재 어휘/threshold로 재채점.

**Kiwi/GPS와 달리 커버리지 방식이 아니다** — `pending_photos()`(mtime 기반)에
걸린 사진만 처리한다. CLIP 추론은 사진 1장에 대략 수십~100ms+가 들어(Kiwi의
폴더명 파싱이나 GPS의 KD-tree 조회와 비교가 안 되는 비용) 이미 분석된 기존
4.5만 장까지 매 스캔 조용히 재인코딩하면 "가벼운 증분 스캔"이 예측 불가능하게
느려진다. 기존 물량 소급 처리와, `tag_vocab.py`/threshold 변경 후 재채점은
아래 `tag-backfill`(전용 CLI + Admin 잡)이 담당한다 — `scan()`(daemon 야간
자동 스캔 포함)만으로는 이 기능 도입 이전 사진에 `source='ai'` 태그가 영원히
안 생긴다.

CLIP 모델(`Xenova/clip-vit-base-patch32`, transformers.js용 ONNX 변환본,
openai/clip-vit-base-patch32와 동일 MIT 라이선스)은 8-bit 양자화판(vision+text
합쳐 ~154MB, fp32 605MB 대비 가볍고 NAS 추론도 빠름)을 쓴다. insightface와
동일하게 워커 최초 실행 시 `$DATA_DIR/models/clip/`에 자동 다운로드(`main`이
아니라 특정 커밋 sha로 고정 — 제3자가 강제 push해도 이미 캐시된
`photo_embeddings`와 다른 가중치를 조용히 받지 않도록). 다운로드는
Content-Length와 실제 수신 바이트 수를 비교해 불완전 응답을 잡고, 실패 시
`.part` 임시 파일을 지워 다음 실행이 재시도할 수 있게 한다.

텍스트 인코딩에 PyTorch/transformers 없이 `onnxruntime`(이미 의존성) +
`tokenizers`(HF 경량 BPE 토크나이저, ~26MB, torch 없음)만 쓴다 — 이미지
인코더만 배포하고 텍스트 임베딩을 오프라인에서 미리 계산해 넣는 방식도
검토했으나, 실측으로 `tokenizers`+`text_model.onnx` 조합이 문제없이 동작함을
확인해 기각(어휘 추가가 `tag_vocab.py` 수정만으로 다음 스캔부터 바로 반영되는
게 더 단순함). threshold 기본값(`AI_TAG_THRESHOLD=0.24`)은 정식 eval 없이
(`doc/tagging_requirement.md` 결정) 실사진 15장(`testdata/photos`) 정성
검증으로 잡음 — 82개 어휘 기준 평균 4.4개 태그/사진, 누락 0건. 같은 검증에서
"추석"/"설날" 프롬프트(문장이 너무 길어 CLIP이 구체화하지 못하고 "야외
단체사진" 방향으로 수렴)가 무관한 야외 사진에서도 반복적으로 상위 태그로
발화해 2026-08-02 어휘에서 제외(82→80개) — 프롬프트를 더 구체적인 장면
묘사로 재작성해 재검증하기 전까지는 tag_vocab.py에 다시 넣지 않는다.
CLIP 로딩(모델 다운로드 포함) 실패는 얼굴 인식과 무관한 별도 기능이라 그
스캔은 얼굴 인식만 수행하고 계속 진행한다(best-effort, `run_scan()`에서
예외를 삼킴).

### AI 태그 재계산 (`tag-backfill`) — CLIP/위치 소급 처리 전용 배치
`python -m ai_worker.main tag-backfill` (`main.run_tag_backfill()`) 또는
Admin이 `POST /api/admin/ai/jobs`에 `{"type": "tag_backfill"}`을 큐잉하면
daemon이 폴링해 실행한다 — `scan`/`rematch`와 동일한 일반 잡 생성·중복방지·
`GET /ai/status`의 `recent_jobs` 경로를 그대로 타므로 `admin_ai_tags.py` 같은
전용 라우터가 필요 없었다(`_JOB_TYPES`에 `tag_backfill` 추가만으로 충분).

`scan()`의 `pending_photos()`(mtime 기반)와 달리 `photos_analyzed`
**전체**(`status='done'`, 얼굴 분석 자체가 실패한 `error` 행은 같은 파일을
CLIP도 못 열 가능성이 높아 제외)를 대상으로 하는 명시적 배치 작업이다 —
admin이 어휘/threshold를 바꾼 뒤, 또는 이 기능 도입 이전 사진에 소급
적용하고 싶을 때 의도적으로 실행한다. 사진마다:

- `photo_embeddings`가 있으면 `pipeline.rescore_ai_tags_from_cache()`로
  **재인코딩 없이** 캐시된 벡터만 재사용해 현재 어휘/threshold로 재채점 —
  이게 `photo_embeddings`를 캐시해두는 핵심 이유(어휘 확장이 전체 재인코딩
  없이 벡터 비교만으로 끝남). 이미지 파일을 열지 않는다.
- `photo_embeddings`/`photo_locations` 중 하나라도 없으면 그때만
  `pipeline.backfill_photo()`가 파일을 1번 열어 부족한 것만 채운다(둘 다
  있으면 파일에 아예 접근하지 않음).
- 폴더명(Kiwi) 태깅은 이미 커버리지 방식이라 `scan()`에서 이미 다루지만,
  `scan` 없이 `tag-backfill`만 단독 실행할 가능성을 대비해 여기서도
  `scanner.tag_paths_from_folder_names()`를 호출한다(idempotent).

`scan()`의 `pending_photos()`는 walk 결과가 0인데 과거 분석 이력이 있으면
마운트 해제로 보고 스캔 전체를 건너뛴다. `tag-backfill`은 walk 없이
`photos_analyzed`를 그대로 신뢰하므로, 같은 상황에서 대상 전부가
`Image.open()` 예외로 떨어져 로그를 뒤덮는 것을 막기 위해 대상 목록을 구한
직후 `PHOTO_ROOT`가 존재하고 비어있지 않은지 확인하고, 아니면 즉시 건너뛴다
(CLIP 모델도 로딩하지 않음).

완료 시 `notify.notify_tag_backfill_result()`로 Discord 알림(신규 임베딩/
재채점/위치보완/에러 건수 + 폴더명 태깅 건수 + 소요시간). Admin UI 버튼은
아직 없음(Admin 태그 관리 화면과 함께 후속 phase 예정) — 지금은 CLI 또는
`POST /api/admin/ai/jobs`를 직접 호출해야 한다.

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

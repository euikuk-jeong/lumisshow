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
python -m ai_worker.tools.label_helper export labels.csv
python -m ai_worker.tools.label_helper import labels.csv
python -m ai_worker.tools.eval --enroll 10
```

## 파일 구조

```
config.py    # 환경변수 (AI_MATCH_THRESHOLD, AI_DET_SIZE, AI_MIN_DET_SCORE)
db.py        # ai.db 스키마/연결 (sqlite3 동기, WAL)
scanner.py   # PHOTO_ROOT 증분 스캔 (path+mtime, @eaDir 제외)
pipeline.py  # InsightFace lazy 로드, 사진 1장 분석→기록 (1장=1커밋, resumable)
matcher.py   # cosine 매칭 (numpy brute-force), 임베딩 BLOB 변환
main.py      # CLI: scan | rematch
tools/       # label_helper.py (CSV 라벨링), eval.py (precision/recall)
```

## 핵심 설계 결정

### ai.db 쓰기 주체 분리 (SQLite 동시성 회피)
- **워커가 쓰는 테이블**: `photos_analyzed`, `faces`, `face_matches` (+`jobs.status` 갱신)
- **LumisShow가 쓰는 테이블**: `persons`, `face_labels`, `jobs`
- 유효 인물 판정: `face_labels` 있으면 그 값(사람 확정), 없으면 `face_matches`
- `face_labels.person_id = NULL`은 "등록 인물 아님(무시)" 라벨

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
- [ ] M1 검증: PC에서 샘플 인덱싱, 정답 셋 300~500장, recall 90%+/precision 95%+
- [ ] M2: Dockerfile.ai, 야간 스케줄(02:00), jobs 큐 폴링 데몬, NAS 초기 인덱싱
- [ ] M3: backend `admin_people.py` + Admin 'People' UI (등록/교정/필터/앨범 생성)
- [ ] M4: 실사용 튜닝 (교정 로그 지표, 시간 기반 후처리)

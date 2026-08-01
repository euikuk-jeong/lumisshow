"""CLIP zero-shot 멀티라벨 사물/장면 태깅.

이미지와 태그 후보 텍스트(`tag_vocab.py`)를 같은 512차원 벡터 공간으로 인코딩해
코사인 유사도가 threshold를 넘는 태그를 전부 부여한다(bbox 없음 — "있다/없다"만
필요). 모델은 openai/clip-vit-base-patch32(MIT)의 커뮤니티 ONNX 변환본
(Xenova/clip-vit-base-patch32, transformers.js용 export)을 쓴다 — 8-bit 양자화판
기준 image+text 합쳐 ~154MB로 fp32(605MB) 대비 가볍고 NAS CPU 추론도 더 빠르다
(정성적 zero-shot 판별 용도라 fp32 대비 정밀도 손실은 감내 가능 — doc의 "정식 eval
생략" 결정과 같은 기조). insightface와 동일하게 가중치는 이미지에 포함하지 않고
워커 최초 실행 시 `$DATA_DIR/models/clip/`에 자동 다운로드한다.

onnxruntime/tokenizers는 무거운 의존성이라 ClipTagger.__init__ 안에서만 lazy
import — tag_vocab 검증, 전처리 등 다른 로직은 이 패키지들 설치 없이도 테스트 가능.
"""

import logging
import os
import sqlite3
import urllib.request
from dataclasses import dataclass

import numpy as np
from PIL import Image

from ai_worker import config

_logger = logging.getLogger(__name__)

# main이 아니라 특정 커밋을 고정 — 제3자가 main을 force-push하면 이미 캐시된
# photo_embeddings와 다른 가중치를 조용히 받아오게 되는 걸 막기 위함.
_HF_REVISION = "d15189d7028b43f1d3e65039190477f6af591c2a"
_HF_BASE = f"https://huggingface.co/Xenova/clip-vit-base-patch32/resolve/{_HF_REVISION}"
_VISION_FILE = "vision_model_quantized.onnx"
_TEXT_FILE = "text_model_quantized.onnx"
_TOKENIZER_FILE = "tokenizer.json"
_MODEL_FILES = {
    _VISION_FILE: f"{_HF_BASE}/onnx/{_VISION_FILE}",
    _TEXT_FILE: f"{_HF_BASE}/onnx/{_TEXT_FILE}",
    _TOKENIZER_FILE: f"{_HF_BASE}/{_TOKENIZER_FILE}",
}

# preprocessor_config.json(Xenova/clip-vit-base-patch32) 값과 동일.
_IMG_MEAN = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
_IMG_STD = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)
_IMG_SIZE = 224
_CONTEXT_LEN = 77


def _clip_model_dir() -> str:
    return os.path.join(config.model_root(), "clip")


def _download(url: str, dest: str) -> None:
    """청크 스트리밍 다운로드 후 Content-Length와 실제 수신 바이트 수를 비교해
    불완전한 응답을 잡아낸다 — urlretrieve만 쓰면 NAS의 불안정한 연결에서 잘린
    파일이 예외 없이 완료되어 그대로 실제 파일명으로 승격될 수 있다. 실패 시
    임시 파일(.part)을 지워 다음 실행이 이어서 재시도할 수 있게 한다."""
    tmp = dest + ".part"
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            expected = resp.headers.get("Content-Length")
            expected = int(expected) if expected is not None else None
            written = 0
            with open(tmp, "wb") as f:
                while True:
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
                    written += len(chunk)
        if expected is not None and written != expected:
            raise OSError(
                f"{url} 다운로드 불완전: {written} bytes 수신 (기대 {expected} bytes)"
            )
        os.replace(tmp, dest)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def _ensure_models() -> str:
    """모델/토크나이저 파일이 없으면 다운로드하고 저장 디렉터리를 반환."""
    d = _clip_model_dir()
    os.makedirs(d, exist_ok=True)
    for filename, url in _MODEL_FILES.items():
        dest = os.path.join(d, filename)
        if os.path.exists(dest):
            continue
        _logger.info("CLIP 모델 다운로드 중: %s", filename)
        _download(url, dest)
    return d


def _preprocess_image(img: Image.Image) -> np.ndarray:
    """CLIP 전처리: 짧은 변 224로 bicubic 리사이즈 → 224x224 중앙크롭 → [0,1] 스케일
    → CLIP mean/std 정규화 → NCHW. 얼굴 인식 파이프라인이 이미 exif_transpose까지
    끝낸 이미지를 그대로 받는다(다시 파일을 열지 않음)."""
    img = img.convert("RGB")
    w, h = img.size
    scale = _IMG_SIZE / min(w, h)
    img = img.resize((round(w * scale), round(h * scale)), Image.BICUBIC)
    w, h = img.size
    left, top = (w - _IMG_SIZE) // 2, (h - _IMG_SIZE) // 2
    img = img.crop((left, top, left + _IMG_SIZE, top + _IMG_SIZE))
    arr = np.asarray(img).astype(np.float32) / 255.0
    arr = (arr - _IMG_MEAN) / _IMG_STD
    return arr.transpose(2, 0, 1)[None, ...].astype(np.float32)


class ClipTagger:
    def __init__(self) -> None:
        import onnxruntime as ort  # lazy import
        from tokenizers import Tokenizer  # lazy import

        d = _ensure_models()
        self._vision = ort.InferenceSession(os.path.join(d, _VISION_FILE))
        self._text = ort.InferenceSession(os.path.join(d, _TEXT_FILE))
        self._tokenizer = Tokenizer.from_file(os.path.join(d, _TOKENIZER_FILE))
        eot_id = self._tokenizer.token_to_id("<|endoftext|>")
        self._tokenizer.enable_padding(length=_CONTEXT_LEN, pad_id=eot_id)
        self._tokenizer.enable_truncation(max_length=_CONTEXT_LEN)

    def embed_image(self, img: Image.Image) -> np.ndarray:
        """L2-정규화된 512차원 이미지 임베딩(float32) 1개."""
        pixel_values = _preprocess_image(img)
        out = self._vision.run(["image_embeds"], {"pixel_values": pixel_values})[0][0]
        norm = np.linalg.norm(out)
        return out / norm if norm else out

    def embed_texts(self, prompts: list[str]) -> np.ndarray:
        """L2-정규화된 (len(prompts), 512) 텍스트 임베딩 행렬."""
        encs = self._tokenizer.encode_batch(prompts)
        input_ids = np.array([e.ids for e in encs], dtype=np.int64)
        out = self._text.run(["text_embeds"], {"input_ids": input_ids})[0]
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return out / norms


@dataclass
class ClipTaggingContext:
    """스캔 1회 동안 재사용하는 CLIP 태깅 상태. 어휘 텍스트 임베딩은 사진마다 다시
    계산할 필요가 없어(고정 어휘) run_scan()에서 1번만 만들어 넘긴다."""

    tagger: ClipTagger
    text_embeds: np.ndarray  # (len(tag_vocab.TAG_VOCAB), 512), L2-정규화됨
    threshold: float


def tag_threshold_setting(conn: sqlite3.Connection) -> float:
    """ai_settings의 tag_threshold(Admin 설정, Phase 4 예정)가 있으면 우선,
    없으면 환경변수(daemon.scan_hour_setting과 동일 패턴)."""
    row = conn.execute(
        "SELECT value FROM ai_settings WHERE key = 'tag_threshold'"
    ).fetchone()
    if row is not None:
        try:
            return float(row["value"])
        except ValueError:
            pass
    return config.tag_threshold()

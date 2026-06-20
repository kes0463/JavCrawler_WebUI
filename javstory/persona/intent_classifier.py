"""메시지 의도 분류기 — 임베딩 기반 (nomic-embed-text / Ollama) + 키워드 폴백.

의도 라벨:
  shame_tension     수치·부끄러움 계열 톤 요청
  intense_sensual   강한 관능·롤플레이 요청
  recommendation    추천 요청
  factual_search    검색·사실 정보 요청
  general_analysis  분석·취향 대화 (기본)
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

_CACHE_PATH = Path(__file__).resolve().parents[2] / "data" / "cache" / "intent_embeddings.json"

INTENT_EXAMPLES: Dict[str, List[str]] = {
    "shame_tension": [
        "수치플레이 해줘",
        "더 부끄럽게 해줘",
        "수치스럽게 만들어줘",
        "창피하게 해줘",
        "들킨 취향 느낌으로 말해줘",
        "부끄러운 기분 들게 해줘",
        "수치 느낌으로 분석해줘",
        "심리적 수치감 표현해줘",
    ],
    "intense_sensual": [
        "더 야하게 해줘",
        "롤플레이 해봐",
        "더 강하게 말해줘",
        "더 세게 해줘",
        "더 도발적으로 얘기해줘",
        "역할극 해줘",
        "조교해줘",
        "유혹해줘",
        "더 자극적으로 표현해줘",
        "애태워줘",
        "끝까지 몰입해봐",
    ],
    "recommendation": [
        "비슷한 작품 추천해줘",
        "이런 취향으로 뭐 볼까",
        "추천해줘",
        "뭐 볼만한 거 있어",
        "비슷한 거 있어",
        "이 느낌 다른 작품 있어",
        "골라줘",
        "추천 좀 해봐",
        "취향에 맞는 거 알려줘",
    ],
    "factual_search": [
        "이 작품 줄거리 뭐야",
        "품번으로 찾아줘",
        "정보 알려줘",
        "어떤 내용이야",
        "어떤 작품이야",
        "시놉시스 알려줘",
        "제목 뭐야",
        "목록 알려줘",
        "작품 검색해줘",
    ],
    "general_analysis": [
        "내 취향 분석해줘",
        "왜 이 장면이 끌릴까",
        "어떤 패턴이 있어",
        "내 취향은 어때",
        "분위기 얘기해줘",
        "관계성이 좋아",
        "텐션 있는 장면이 좋아",
        "어떤 요소가 나한테 맞아",
        "왜 이게 끌리는 거야",
    ],
}

# 임베딩 기반 분류를 스킵할 의도 (키워드 매칭이 더 신뢰할 수 있는 경우)
_KEYWORD_OVERRIDE: Dict[str, tuple[str, ...]] = {
    "shame_tension": ("수치플레이", "수치", "부끄럽게", "수치스럽게", "창피하게"),
    "intense_sensual": ("롤플레이", "역할극", "더 야하게", "야하게", "더 세게", "조교", "유혹", "애태"),
    "factual_search": ("품번", "제목", "목록", "찾아", "검색"),
}


def _examples_hash() -> str:
    raw = json.dumps(INTENT_EXAMPLES, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(x * x for x in b))
    return dot / mag if mag else 0.0


class IntentClassifier:
    def __init__(
        self,
        *,
        model: str = "nomic-embed-text",
        base_url: str = "http://localhost:11434",
        threshold: float = 0.38,
    ) -> None:
        self.model = model
        self.base_url = base_url
        self.threshold = threshold
        self._example_embeddings: Optional[Dict[str, List[List[float]]]] = None
        self._unavailable = False  # Ollama 연결 실패 시 빠른 폴백용

    # ------------------------------------------------------------------
    # 임베딩 호출
    # ------------------------------------------------------------------

    def _embed(self, text: str) -> Optional[List[float]]:
        if self._unavailable:
            return None
        try:
            import httpx

            r = httpx.post(
                f"{self.base_url.rstrip('/')}/api/embeddings",
                json={"model": self.model, "prompt": text},
                timeout=8.0,
            )
            r.raise_for_status()
            emb = r.json().get("embedding")
            if isinstance(emb, list) and emb:
                return [float(x) for x in emb]
        except Exception:
            self._unavailable = True
        return None

    # ------------------------------------------------------------------
    # 예시 임베딩 초기화
    # ------------------------------------------------------------------

    def _load_cache(self) -> bool:
        try:
            if not _CACHE_PATH.is_file():
                return False
            data = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
            if data.get("hash") != _examples_hash() or data.get("model") != self.model:
                return False
            embs = data.get("embeddings") or {}
            if not embs:
                return False
            self._example_embeddings = {k: [[float(x) for x in v] for v in vs] for k, vs in embs.items()}
            return True
        except Exception:
            return False

    def _build_and_cache(self) -> bool:
        embeddings: Dict[str, List[List[float]]] = {}
        for intent, phrases in INTENT_EXAMPLES.items():
            vecs: List[List[float]] = []
            for phrase in phrases:
                v = self._embed(phrase)
                if v:
                    vecs.append(v)
            embeddings[intent] = vecs

        if not any(embeddings.values()):
            return False

        try:
            _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            _CACHE_PATH.write_text(
                json.dumps({"hash": _examples_hash(), "model": self.model, "embeddings": embeddings}, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

        self._example_embeddings = embeddings
        return True

    def _ensure_examples(self, *, allow_build: bool = False) -> bool:
        """캐시가 있으면 로드. allow_build=True일 때만 신규 빌드 허용 (프리웜 전용)."""
        if self._example_embeddings is not None:
            return True
        if self._unavailable:
            return False
        if self._load_cache():
            return True
        if allow_build:
            return self._build_and_cache()
        return False  # 캐시 없음 → 호출부에서 키워드 폴백

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def classify(self, text: str) -> Optional[str]:
        """
        텍스트를 의도 라벨로 분류.
        예시 캐시 미빌드 · 임베딩 실패 · threshold 미만이면 None 반환 → 키워드 폴백.
        채팅 경로에서는 절대 블로킹 빌드를 하지 않는다.
        """
        if not self._ensure_examples(allow_build=False):
            return None

        msg_vec = self._embed(text)
        if msg_vec is None:
            return None

        best_label: Optional[str] = None
        best_score = -1.0
        for label, example_vecs in (self._example_embeddings or {}).items():
            if not example_vecs:
                continue
            score = max(_cosine(msg_vec, ev) for ev in example_vecs)
            if score > best_score:
                best_score = score
                best_label = label

        if best_score < self.threshold:
            return None
        return best_label


# ------------------------------------------------------------------
# 모듈 수준 싱글턴 + per-turn 캐시
# ------------------------------------------------------------------

_classifier: Optional[IntentClassifier] = None
_turn_cache: Dict[str, Optional[str]] = {}
_TURN_CACHE_MAX = 32


def _get_classifier() -> IntentClassifier:
    global _classifier
    if _classifier is None:
        try:
            from javstory.config.app_config import OLLAMA_BASE_URL

            base_url = OLLAMA_BASE_URL
        except Exception:
            base_url = "http://localhost:11434"
        try:
            from javstory.library.embeddings.pipeline import embeddings_ollama_model_from_env

            model = embeddings_ollama_model_from_env()
        except Exception:
            model = "nomic-embed-text"
        _classifier = IntentClassifier(model=model, base_url=base_url)
    return _classifier


def classify_intent(text: str) -> Optional[str]:
    """
    메시지를 의도 라벨로 분류.

    먼저 키워드 오버라이드를 확인(명시적 표현은 오탐 없이 처리),
    그 다음 임베딩 분류기로 분류,
    실패 시 None 반환.
    """
    # 키워드 오버라이드 — 명시적 표현은 임베딩 없이 즉시 반환
    lowered = (text or "").lower()
    for label, kws in _KEYWORD_OVERRIDE.items():
        if any(kw in lowered for kw in kws):
            return label

    # per-turn 캐시
    key = hashlib.sha1(text.encode()).hexdigest()[:12]
    if key in _turn_cache:
        return _turn_cache[key]

    result = _get_classifier().classify(text)

    if len(_turn_cache) >= _TURN_CACHE_MAX:
        _turn_cache.clear()
    _turn_cache[key] = result
    return result


def prewarm_intent_classifier() -> None:
    """앱 시작 시 예시 임베딩을 미리 빌드해 첫 분류 지연을 없앤다.
    채팅 경로와 달리 블로킹 빌드를 허용한다 (백그라운드 스레드에서만 호출)."""
    try:
        classifier = _get_classifier()
        if not classifier._load_cache():
            ok = classifier._build_and_cache()
            print("[IntentClassifier] 예시 임베딩 빌드 완료" if ok else "[IntentClassifier] 빌드 실패 — Ollama 미연결 (키워드 폴백 유지)")
        else:
            print("[IntentClassifier] 예시 임베딩 캐시 로드 완료")
    except Exception as exc:
        print(f"[IntentClassifier] 프리웜 실패 (무시): {exc}")

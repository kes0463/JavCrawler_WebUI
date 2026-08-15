"""
검색 쿼리 → 임베딩 입력 포맷.

e5-mistral-instruct 계열은 문서(passage)는 그대로, 쿼리만 Instruct/Query 형식을 써야
검색 공간이 맞게 정렬된다.

개념(concept) 커버리지는 분위기·장소·장르 동의어로 코사인 점수를 보정한다.
알 수 없는 조사·필러 토큰은 개념으로 세지 않아 과도 감점을 줄인다.
"""

from __future__ import annotations

import math
import os
import re
import threading
import time
from typing import Iterable, List, Mapping

_DEFAULT_E5_TASK = (
    "Given a search query, retrieve relevant adult video descriptions that match "
    "the mood, setting, weather, location, or scene."
)

_TOKEN_RE = re.compile(r"[A-Za-z0-9가-힣ぁ-んァ-ン一-龥]{2,}")

_lexicon_lock = threading.Lock()
_lexicon_cache: tuple[float, dict[str, tuple[str, ...]]] | None = None
_LEXICON_TTL_ENV = "JAVSTORY_EMBEDDING_CONCEPT_CACHE_TTL"


def _model_name_hints(model: str | None) -> str:
    name = (model or "").strip().lower()
    if not name:
        for key in ("JAVSTORY_EMBEDDINGS_MODEL", "JAVSTORY_EMBEDDINGS_OLLAMA_MODEL"):
            name = (os.environ.get(key, "") or "").strip().lower()
            if name:
                break
    gguf = (os.environ.get("JAVSTORY_EMBEDDINGS_LLAMACPP_GGUF", "") or "").strip().lower()
    return f"{name} {gguf}"


def is_e5_mistral_model(model: str | None = None) -> bool:
    hints = _model_name_hints(model)
    return "e5" in hints and "mistral" in hints


def is_e5_family_model(model: str | None = None) -> bool:
    hints = _model_name_hints(model)
    return "e5" in hints or "multilingual-e5" in hints


def format_search_query_for_embedding(query: str, *, model: str | None = None) -> str:
    """
    검색용 쿼리 텍스트를 모델에 맞게 변환.
    문서 인덱싱 텍스트는 변환하지 않는다(문서=원문).
    """
    q = (query or "").strip()
    if not q:
        return q

    explicit = (os.environ.get("JAVSTORY_EMBEDDING_QUERY_TEMPLATE", "") or "").strip()
    if explicit:
        return explicit.replace("{query}", q).replace("{QUERY}", q)

    if is_e5_mistral_model(model):
        task = (os.environ.get("JAVSTORY_EMBEDDING_E5_TASK", "") or "").strip() or _DEFAULT_E5_TASK
        prefix = f"Instruct: {task}\nQuery: "
        try:
            from javstory.llm.llamacpp_embeddings import embedding_max_input_chars

            room = max(64, embedding_max_input_chars() - len(prefix))
            if len(q) > room:
                q = q[:room]
        except Exception:
            pass
        return f"{prefix}{q}"

    if is_e5_family_model(model):
        return f"query: {q}"

    return q


# 분위기·장소 검색에서 자주 쓰는 동의어 (개념 단위)
_SETTING_CONCEPTS: dict[str, tuple[str, ...]] = {
    "비오는": ("비오는", "비 오", "비가 오", "빗속", "빗소리", "장마", "雨", "雨宿", "rainy", "rain"),
    "비": ("비오는", "비 오", "비가", "빗속", "빗소리", "장마", "雨", "rainy", "rain"),
    "사무실": ("사무실", "오피스", "オフィス", "office", "会社", "ol", "ＯＬ"),
    "오피스": ("사무실", "오피스", "オフィス", "office", "ol"),
    "학교": ("학교", "교내", "학원", "学園", "school", "교실", "教室"),
    "온천": ("온천", "温泉", "노천탕", "혼탕", "노천"),
    "호텔": ("호텔", "ホテル", "hotel", "러브호텔", "ラブホ"),
    "기차": ("기차", "전철", "전차", "電車", "열차", "train", "subway"),
    "버스": ("버스", "バス", "bus"),
    "풀장": ("풀장", "수영장", "プール", "pool"),
    "실외": ("실외", "야외", "屋外", "outdoor", "밖에서", "노상"),
    "야외": ("실외", "야외", "屋外", "outdoor", "밖에서"),
    "실내": ("실내", "屋内", "indoor"),
    "밤": ("밤", "야간", "야밤", "深夜", "night", "nightlife"),
    "야간": ("밤", "야간", "深夜", "night"),
    "해변": ("해변", "바닷가", "海水浴", "beach", "바다"),
    "도서관": ("도서관", "図書館", "library"),
    "편의점": ("편의점", "コンビニ", "convenience store"),
    "카페": ("카페", "カフェ", "cafe", "커피숍"),
    "차량": ("차량", "차안", "車内", "자동차", "car", "드라이브"),
    "차안": ("차량", "차안", "車内", "car"),
}

# 장르·직업·상황 검색어 → 메타/본문에 자주 나오는 표기
_GENRE_CONCEPTS: dict[str, tuple[str, ...]] = {
    "마사지": ("마사지", "マッサージ", "massage", "에스테", "オイル", "oil"),
    "유부녀": ("유부녀", "人妻", "married", "아내", "와이프"),
    "여교사": ("여교사", "女教師", "교사", "선생님", "teacher"),
    "간호사": ("간호사", "ナース", "nurse"),
    "메이드": ("메이드", "メイド", "maid"),
    "비서": ("비서", "秘書", "secretary"),
    "교복": ("교복", "制服", "세일러복", "교복차림"),
    "수영복": ("수영복", "競泳", "スク水", "swimsuit", "비키니", "bikini"),
    "중출": ("중출", "中出し", "nakadashi", "creampie"),
    "질내사정": ("질내사정", "중출", "中出し", "nakadashi", "creampie"),
    "네토라레": ("네토라레", "ntr", "寝取", "네토레"),
    "ntr": ("ntr", "네토라레", "寝取", "네토레"),
    "치한": ("치한", "痴漢", "추행", "groping"),
    "노출": ("노출", "露出", "야외노출", "exhibition"),
    "안경": ("안경", "メガネ", "glasses"),
    "거유": ("거유", "巨乳", "큰가슴", "big breasts", "huge breasts"),
    "빈유": ("빈유", "貧乳", "작은가슴"),
    "미인": ("미인", "美女", "미소녀", "beautiful"),
    "미소녀": ("미소녀", "美少女", "미인"),
    "숙녀": ("숙녀", "熟女", "milf"),
    "미망인": ("미망인", "未亡人", "widow"),
    "자매": ("자매", "姉妹", "sister"),
    "모녀": ("모녀", "母娘"),
    "남편": ("남편", "亭主", "husband"),
    "불륜": ("불륜", "不倫", "외도", "affair"),
    "강간": ("강간", "レイプ", "rape"),
    "협박": ("협박", "脅迫", "blackmail"),
    "감금": ("감금", "監禁", "confinement"),
    "노예": ("노예", "奴隷", "slave"),
    "조교": ("조교", "調教", "training"),
    "스왑": ("스왑", "スワップ", "swap", "교환"),
    "쓰리섬": ("쓰리섬", "3p", "三人", "threesome"),
    "레즈": ("레즈", "レズ", "lesbian", "백합"),
    "동성": ("동성", "ホモ", "gay"),
    "아날": ("아날", "アナル", "anal"),
    "페라": ("페라", "フェラ", "oral", "블로우"),
    "얼굴사정": ("얼굴사정", "顔射", "facial"),
    "촬영회": ("촬영회", "撮影会", "业余", "아마추어"),
    "아마추어": ("아마추어", "素人", "amateur"),
    "도모다찌": ("도모다찌", "友達", "친구", "friend"),
    "이웃": ("이웃", "隣人", "neighbor"),
    "시아버지": ("시아버지", "義父", "father in law"),
    "시어머니": ("시어머니", "義母"),
    "오빠": ("오빠", "兄", "brother"),
    "여동생": ("여동생", "妹", "sister"),
    "처형": ("처형", "義姉"),
    "올케": ("올케", "義理"),
    "수면": ("수면", "睡眠", "잠든", "sleeping"),
    "만취": ("만취", "酔い", "drunk", "취한"),
    "에스더": ("에스더", "媚薬", "최음", "aphrodisiac"),
    "최음제": ("최음제", "媚薬", "aphrodisiac"),
    "몰카": ("몰카", "盗撮", "voyeur", "몰래카메라"),
    "도촬": ("도촬", "盗撮", "voyeur"),
    "변태": ("변태", "変態", "pervert"),
    "수치": ("수치", "羞恥", "부끄", "shame"),
    "공개": ("공개", "公開", "public"),
    "복수": ("복수", "復讐", "revenge"),
    "유혹": ("유혹", "誘惑", "seduce", "seduction"),
    "봉사": ("봉사", "奉仕", "service"),
    "목욕": ("목욕", "風呂", "入浴", "bath", "샤워", "shower"),
    "샤워": ("샤워", "シャワー", "shower", "목욕"),
    "침실": ("침실", "ベッド", "bed", "bedroom"),
    "주방": ("주방", "キッチン", "kitchen"),
    "거실": ("거실", "リビング", "living"),
}

# 하위 호환: 기존 테스트·호출부가 참조할 수 있는 통합 테이블
_CONCEPT_SYNONYMS: dict[str, tuple[str, ...]] = {
    **_SETTING_CONCEPTS,
    **_GENRE_CONCEPTS,
}


def _unique_forms(forms: Iterable[str]) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in forms:
        s = str(raw or "").strip().lower()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return tuple(out)


def _index_concept_groups(groups: Mapping[str, tuple[str, ...]]) -> dict[str, tuple[str, ...]]:
    """동의어 묶음의 모든 표기를 lookup key로 역인덱스한다."""
    indexed: dict[str, tuple[str, ...]] = {}
    for canonical, syns in groups.items():
        bundle = _unique_forms((canonical, *syns))
        if not bundle:
            continue
        for form in bundle:
            prev = indexed.get(form)
            if prev is None or len(bundle) >= len(prev):
                indexed[form] = bundle
    return indexed


def _lexicon_ttl_sec(default: float = 600.0) -> float:
    raw = (os.environ.get(_LEXICON_TTL_ENV, "") or "").strip()
    if not raw:
        return default
    try:
        return max(30.0, min(86_400.0, float(raw)))
    except Exception:
        return default


def _load_live_genre_concepts() -> dict[str, tuple[str, ...]]:
    """라이브러리 genres_ko/genres에 실제 등장하는 장르명을 개념으로 등록."""
    try:
        from sqlalchemy import and_, or_

        from javstory.harvest.database import JAVMetadata, get_db_session_ctx

        with get_db_session_ctx() as db:
            rows = (
                db.query(JAVMetadata.genres_ko, JAVMetadata.genres, JAVMetadata.genres_ja)
                .filter(
                    or_(
                        and_(
                            JAVMetadata.genres_ko.isnot(None),
                            JAVMetadata.genres_ko != "",
                        ),
                        and_(
                            JAVMetadata.genres.isnot(None),
                            JAVMetadata.genres != "",
                        ),
                        and_(
                            JAVMetadata.genres_ja.isnot(None),
                            JAVMetadata.genres_ja != "",
                        ),
                    )
                )
                .all()
            )
    except Exception:
        return {}

    counts: dict[str, int] = {}
    for ko, legacy, ja in rows:
        for raw in (ko, legacy, ja):
            for part in str(raw or "").replace("、", ",").split(","):
                name = part.strip()
                if len(name) < 2:
                    continue
                key = name.lower()
                counts[key] = counts.get(key, 0) + 1

    # 상위 장르만 인덱싱 (희귀 노이즈·메모리 절약)
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:400]
    out: dict[str, tuple[str, ...]] = {}
    for key, _n in ranked:
        out[key] = (key,)
    return out


def clear_concept_lexicon_cache() -> None:
    global _lexicon_cache
    with _lexicon_lock:
        _lexicon_cache = None


def _concept_lexicon() -> dict[str, tuple[str, ...]]:
    """정적 동의어 + 라이브 장르가 합쳐진 lookup 테이블."""
    global _lexicon_cache
    now = time.time()
    ttl = _lexicon_ttl_sec()
    with _lexicon_lock:
        if _lexicon_cache is not None and (now - _lexicon_cache[0]) < ttl:
            return _lexicon_cache[1]

    static_groups = {**_SETTING_CONCEPTS, **_GENRE_CONCEPTS}
    live = _load_live_genre_concepts()
    for key, bundle in live.items():
        if key in static_groups:
            static_groups[key] = _unique_forms((*static_groups[key], *bundle))
        else:
            static_groups[key] = bundle

    indexed = _index_concept_groups(static_groups)
    with _lexicon_lock:
        _lexicon_cache = (now, indexed)
        return indexed


def _resolve_concept(
    token: str,
    lexicon: Mapping[str, tuple[str, ...]],
) -> tuple[str, tuple[str, ...]] | None:
    tok = (token or "").strip().lower()
    if not tok:
        return None
    syns = lexicon.get(tok)
    if syns is not None:
        return tok, syns

    # 복합 토큰(마사지받는장면) / 부분 일치
    best_key = ""
    best_syns: tuple[str, ...] | None = None
    for key, bundle in lexicon.items():
        if len(key) < 2:
            continue
        if key in tok or tok in key:
            if best_syns is None or len(key) > len(best_key):
                best_key = key
                best_syns = bundle
    if best_syns is None:
        return None
    return best_key, best_syns


def expand_query_concepts(query: str) -> List[List[str]]:
    """
    쿼리에서 알려진 분위기·장소·장르 개념만 추출한다.
    매칭 시 묶음 중 하나만 있어도 해당 개념은 충족.
    미등록 필러 토큰은 개념으로 세지 않는다.
    """
    lexicon = _concept_lexicon()
    tokens = [m.group(0).lower() for m in _TOKEN_RE.finditer(query or "")]
    concepts: List[List[str]] = []
    seen: set[str] = set()
    for tok in tokens:
        resolved = _resolve_concept(tok, lexicon)
        if resolved is None:
            continue
        key, syns = resolved
        # 동일 동의어 묶음은 한 번만 (대표키 = 정렬된 첫 표기)
        group_id = syns[0] if syns else key
        if group_id in seen:
            continue
        seen.add(group_id)
        concepts.append([s.lower() for s in syns])
    return concepts


def concept_coverage(text: str, concepts: List[List[str]]) -> float:
    """텍스트가 쿼리 개념을 얼마나 충족하는지 0~1."""
    if not concepts:
        return 0.0
    blob = (text or "").lower()
    if not blob:
        return 0.0
    hits = 0
    for syns in concepts:
        if any(s in blob for s in syns):
            hits += 1
    return hits / float(len(concepts))


def blend_embedding_lexical_score(
    cosine: float,
    coverage: float,
    *,
    concept_n: int,
) -> float:
    """
    코사인 × 개념 커버리지.
    개념이 2개 이상일 때(예: 비오는+사무실) 한쪽만 맞으면 강하게 감점.
    """
    if not math.isfinite(float(cosine)):
        return float("-inf")
    if concept_n <= 0:
        return float(cosine)
    if concept_n == 1:
        return float(cosine) * (0.85 + 0.15 * float(coverage))
    return float(cosine) * (0.35 + 0.65 * float(coverage))

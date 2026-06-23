"""Actress name resolution and filmography retrieval for Persona Chat."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence

from javstory.harvest.database import Actress, JAVMetadata, get_db_session_ctx
from javstory.persona.library_search import (
    _attach_user_watch_signals,
    normalize_product_code,
    row_to_search_result,
    split_query_terms,
)
from javstory.utils.actress_profile import (
    fetch_actress_library_works,
    get_actress_context,
    resolve_actress_by_name,
)

_LEADING_FILLERS_RE = re.compile(
    r"^(?:나는|저는|내가|나|제가|요즘|오늘|그냥|좀|혹시|만약|정말|진짜|please|i\s+like)\s+",
    re.IGNORECASE,
)
_RECOMMENDATION_TAIL_RE = re.compile(
    r"(?:의\s*)?(?:작품|영상|출연작|동영상|av|AV)"
    r"(?:\s*(?:추천|골라|찾아|알려|보여|줘|주세요|해\s*줘|해줘).*)?$|"
    r"(?:추천|골라\s*줘|찾아\s*줘|알려\s*줘|보여\s*줘).*$",
    re.IGNORECASE,
)
_AFFINITY_TAIL_RE = re.compile(
    r"(?:이?가\s*)?(?:좋아|좋아해|좋아요|취향|팬이야|팬입니다|최애|좋던데|맘에|사랑해).*$",
    re.IGNORECASE,
)
_TRAILING_PARTICLES = (
    "에게",
    "한테",
    "께서",
    "이라고",
    "라고",
    "가",
    "는",
    "을",
    "를",
    "이",
    "의",
    "와",
    "과",
    "도",
    "만",
)


def actress_name_span_candidates(message: str) -> List[str]:
    """Heuristic actress-name spans from a free-form user message."""
    raw = str(message or "").strip()
    if not raw:
        return []

    core = _LEADING_FILLERS_RE.sub("", raw).strip()
    core = _RECOMMENDATION_TAIL_RE.sub("", core).strip()
    core = _AFFINITY_TAIL_RE.sub("", core).strip()
    core = core.strip(" .,!?…")

    out: List[str] = []

    def add(value: str) -> None:
        text = str(value or "").strip()
        if len(text) < 2:
            return
        if text not in out:
            out.append(text)

    trimmed = core
    for _ in range(5):
        add(trimmed)
        changed = False
        for particle in _TRAILING_PARTICLES:
            if trimmed.endswith(particle) and len(trimmed) > len(particle) + 1:
                trimmed = trimmed[: -len(particle)].strip()
                changed = True
                break
        if not changed:
            break

    return sorted(out, key=len, reverse=True)


def resolve_actresses_from_message(
    message: str,
    *,
    extra_names: Sequence[str] | None = None,
    limit: int = 3,
) -> List[Dict[str, Any]]:
    """Resolve actress profile dicts mentioned in the user message."""
    msg = str(message or "").strip()
    if not msg:
        return []

    seen_ids: set[int] = set()
    resolved: List[Dict[str, Any]] = []

    def append_ctx(ctx: Dict[str, Any]) -> None:
        aid = int(ctx.get("id") or 0)
        if aid > 0:
            if aid in seen_ids:
                return
            seen_ids.add(aid)
        elif not ctx.get("name"):
            return
        resolved.append(ctx)

    for name in sorted({str(n or "").strip() for n in (extra_names or []) if str(n or "").strip()}, key=len, reverse=True):
        if name not in msg:
            continue
        ctx = get_actress_context_by_name_safe(name)
        if ctx:
            append_ctx(ctx)

    for span in actress_name_span_candidates(msg):
        aid = resolve_actress_by_name(span)
        if not aid:
            continue
        ctx = get_actress_context(aid)
        if ctx:
            append_ctx(ctx)
        if len(resolved) >= limit:
            break

    return resolved[:limit]


def get_actress_context_by_name_safe(name: str) -> Dict[str, Any]:
    from javstory.utils.actress_profile import get_actress_context_by_name

    return get_actress_context_by_name(name) or {}


def is_actress_work_request(user_message: str) -> bool:
    text = str(user_message or "").lower()
    return any(hint in text for hint in ("작품", "출연", "필모", "영상", "추천", "골라", "찾아", "볼만"))


def actress_filter_dict(actress_ctx: Dict[str, Any]) -> Dict[str, Any]:
    names: List[str] = []
    for key in ("name", "name_ja", "name_en", "romaji"):
        value = str(actress_ctx.get(key) or "").strip()
        if value and value not in names:
            names.append(value)
    for alias in list(actress_ctx.get("aliases") or []):
        value = str(alias or "").strip()
        if value and value not in names:
            names.append(value)
    return {
        "actress_id": int(actress_ctx.get("id") or 0),
        "name": str(actress_ctx.get("name") or ""),
        "name_ja": str(actress_ctx.get("name_ja") or ""),
        "match_names": names,
    }


def actor_list_matches_actress(actors: Any, actress_filter: Dict[str, Any]) -> bool:
    match_names = [str(n or "").strip() for n in (actress_filter.get("match_names") or []) if str(n or "").strip()]
    if not match_names:
        return True
    actor_texts = [str(a or "").strip() for a in (actors if isinstance(actors, list) else []) if str(a or "").strip()]
    if not actor_texts:
        return False
    for actor in actor_texts:
        actor_cf = actor.casefold()
        for name in match_names:
            name_cf = name.casefold()
            if name_cf == actor_cf or name_cf in actor_cf or actor_cf in name_cf:
                return True
    return False


def filter_results_for_actress(
    results: Sequence[Dict[str, Any]],
    actress_filter: Dict[str, Any],
) -> List[Dict[str, Any]]:
    if not actress_filter or not int(actress_filter.get("actress_id") or 0):
        return list(results)
    return [item for item in results if actor_list_matches_actress(item.get("actors"), actress_filter)]


def build_actress_work_library_search(
    user_message: str,
    actress_ctx: Dict[str, Any],
    *,
    limit: int = 24,
) -> Dict[str, Any]:
    """Build library_search.results from actress_works index only."""
    aid = int(actress_ctx.get("id") or 0)
    actress_name = str(actress_ctx.get("name") or actress_ctx.get("name_ja") or "").strip()
    actress_filter = actress_filter_dict(actress_ctx)
    empty: Dict[str, Any] = {
        "query": user_message,
        "terms": split_query_terms(user_message),
        "strict_title_terms": [],
        "strict_title_contains": False,
        "source_policy": {
            "mode": "actress_works",
            "primary_source": "actress_works",
            "allowed_candidate_sources": ["actress_works"],
            "use_db_metadata": True,
            "use_synopsis": True,
            "use_grok": False,
            "use_embedding": False,
            "hard_constraints": [
                f"후보는 배우 '{actress_name}'의 라이브러리 출연작만 사용한다.",
                "다른 배우 작품이나 DB에 없는 품번은 추천하지 않는다.",
            ],
        },
        "actress_filter": actress_filter,
        "product_codes": [],
        "fallback_seed_codes": [],
        "results": [],
    }
    if aid <= 0:
        return empty

    adapted: List[Dict[str, Any]] = []
    with get_db_session_ctx() as session:
        actress_row = session.query(Actress).filter_by(id=aid).first()
        if not actress_row:
            return empty
        works = fetch_actress_library_works(session, actress_row, max_items=max(limit * 2, 24))
        codes = [
            normalize_product_code(str(item.get("product_code") or ""))
            for item in works
            if normalize_product_code(str(item.get("product_code") or ""))
        ]
        row_by_code: Dict[str, JAVMetadata] = {}
        if codes:
            for row in session.query(JAVMetadata).filter(JAVMetadata.product_code.in_(codes)).all():
                row_by_code[str(row.product_code or "").strip().upper()] = row

    for idx, work in enumerate(works[:limit]):
        pc = normalize_product_code(str(work.get("product_code") or ""))
        if not pc:
            continue
        row = row_by_code.get(pc)
        if row:
            item = row_to_search_result(row, source="actress_works", score=max(0.5, 1.0 - idx * 0.01))
        else:
            item = {
                "product_code": pc,
                "title_ko": str(work.get("title_ko") or work.get("titleKo") or ""),
                "title_ja": "",
                "actors": [
                    part.strip()
                    for part in str(work.get("actors_ko") or work.get("actorsKo") or "").replace("、", ",").split(",")
                    if part.strip()
                ],
                "genres": [
                    part.strip()
                    for part in str(work.get("genres_ko") or "").replace("、", ",").split(",")
                    if part.strip()
                ],
                "maker": "",
                "release_date": str(work.get("release_date") or ""),
                "synopsis": "",
                "favorite_score": int(work.get("favorite_score") or 0),
                "folder_path": "",
                "source": "actress_works",
                "score": max(0.5, 1.0 - idx * 0.01),
            }
        adapted.append(item)

    _attach_user_watch_signals(adapted)
    empty["results"] = adapted
    return empty


def actress_work_pool_items(
    actress_id: int,
    *,
    limit: int = 24,
    exclude_codes: Sequence[str] | None = None,
) -> List[Dict[str, Any]]:
    """Recommendation-pool channel rows for a specific actress."""
    ctx = get_actress_context(int(actress_id))
    if not ctx:
        return []
    exclude = {
        normalize_product_code(code)
        for code in (exclude_codes or [])
        if normalize_product_code(code)
    }
    search = build_actress_work_library_search("", ctx, limit=limit)
    out: List[Dict[str, Any]] = []
    for item in search.get("results") or []:
        pc = normalize_product_code(str(item.get("product_code") or ""))
        if not pc or pc in exclude:
            continue
        out.append(
            {
                "id": pc,
                "product_code": pc,
                "title": str(item.get("title_ko") or item.get("title_ja") or ""),
                "score": float(item.get("score") or 0.9),
                "source": "actress_works",
            }
        )
    return out

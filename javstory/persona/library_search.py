"""Library search layer for Persona Chat."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

from sqlalchemy import or_

from javstory.harvest.database import JAVMetadata, get_db_session_ctx

_PRODUCT_CODE_RE = re.compile(r"(?<![A-Z0-9])([A-Z]{1,8})[-_\s]?(\d{2,7})(?![A-Z0-9])", re.IGNORECASE)
_MULTI_PART_PRODUCT_CODE_RE = re.compile(
    r"(?<![A-Z0-9])([A-Z0-9]*\d[A-Z0-9]*[-_][A-Z0-9]{1,8})[-_\s](\d{2,7})(?![A-Z0-9])",
    re.IGNORECASE,
)
_QUERY_STOPWORDS = {
    "작품",
    "품번",
    "검색",
    "정보",
    "내용",
    "줄거리",
    "알려줘",
    "알려줘라",
    "알려달라",
    "알려달라고",
    "찾아줘",
    "찾아봐",
    "추천",
    "비슷한",
}
_QUERY_STOPWORD_PREFIXES = ("검색", "알려", "찾아", "추천")
_STRICT_TITLE_PATTERNS = (
    re.compile(r"(?:제목|타이틀|작품명)\s*에\s*[\"'“”‘’]?(.+?)[\"'“”‘’]?\s*(?:이|가)?\s*(?:들어|포함)", re.IGNORECASE),
    re.compile(r"(?:제목|타이틀|작품명)\s*(?:포함|검색)\s*[\"'“”‘’]?(.+?)[\"'“”‘’]?\s*(?:작품|추천|찾)", re.IGNORECASE),
    re.compile(r"[\"'“”‘’](.+?)[\"'“”‘’]\s*(?:이|가)?\s*(?:제목|타이틀|작품명)\s*에\s*(?:들어|포함)", re.IGNORECASE),
)
_SIMILAR_HINTS = ("비슷", "유사", "같은 느낌", "같은 분위기", "다음", "취향", "이어", "대체")
_SCENE_HINTS = ("장면", "상황", "분위기", "전개", "관계", "톤", "태그", "스토리", "흐름", "느낌")
_SYNOPSIS_HINTS = ("줄거리", "시놉", "내용", "설정", "무슨 내용", "어떤 내용")


def normalize_product_code(value: str | None) -> str:
    text = (value or "").strip().upper()
    if not text:
        return ""
    match = _MULTI_PART_PRODUCT_CODE_RE.search(text) or _PRODUCT_CODE_RE.search(text)
    if not match:
        return text
    prefix = match.group(1).upper().replace("_", "-")
    number = match.group(2)
    if len(prefix) == 1 and prefix.isalpha():
        return f"{prefix}{number}"
    return f"{prefix}-{number}"


def product_code_variants(value: str | None) -> List[str]:
    pc = normalize_product_code(value)
    if not pc:
        return []
    variants = [pc]
    match = _PRODUCT_CODE_RE.search(pc)
    if match:
        prefix = match.group(1).upper().replace("_", "-")
        number = match.group(2)
        compact = f"{prefix}{number}"
        hyphenated = f"{prefix}-{number}"
        for item in (compact, hyphenated):
            if item not in variants:
                variants.append(item)
    return variants


def extract_product_codes(text: str, *, limit: int = 5) -> List[str]:
    out: List[str] = []
    matches = list(_MULTI_PART_PRODUCT_CODE_RE.finditer(text or "")) + list(_PRODUCT_CODE_RE.finditer(text or ""))
    matches.sort(key=lambda m: (m.start(), -(m.end() - m.start())))
    used_spans: List[tuple[int, int]] = []
    for match in matches:
        span = match.span()
        if any(not (span[1] <= used[0] or span[0] >= used[1]) for used in used_spans):
            continue
        used_spans.append(span)
        pc = normalize_product_code(match.group(0))
        if pc not in out:
            out.append(pc)
        if len(out) >= limit:
            break
    return out


def split_query_terms(text: str, *, limit: int = 8) -> List[str]:
    strict_title_terms = set(extract_strict_title_terms(text))
    cleaned = re.sub(r"[^\w가-힣ぁ-んァ-ン一-龥\-]+", " ", text or "", flags=re.UNICODE)
    out: List[str] = []
    for token in cleaned.split():
        t = token.strip()
        if len(t) < 2:
            continue
        if t in {"제목", "타이틀", "작품명"} or t.startswith(("제목에", "타이틀에", "작품명에")):
            continue
        if t.startswith(("들어", "포함")):
            continue
        if _PRODUCT_CODE_RE.fullmatch(t) or _MULTI_PART_PRODUCT_CODE_RE.fullmatch(t):
            continue
        if t in _QUERY_STOPWORDS or any(t.startswith(prefix) for prefix in _QUERY_STOPWORD_PREFIXES):
            continue
        if any(term in t or t in term for term in strict_title_terms):
            continue
        if t not in out:
            out.append(t)
        if len(out) >= limit:
            break
    return out


def extract_strict_title_terms(text: str, *, limit: int = 3) -> List[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    out: List[str] = []
    for pattern in _STRICT_TITLE_PATTERNS:
        for match in pattern.finditer(raw):
            chunk = str(match.group(1) or "").strip()
            chunk = re.sub(r"(?:인\s*)?(?:작품|영상|동영상|추천|찾아줘|알려줘).*$", "", chunk).strip()
            chunk = chunk.strip(" \"'“”‘’.,，。")
            if len(chunk) >= 2 and chunk not in _QUERY_STOPWORDS and chunk not in out:
                out.append(chunk)
            if len(out) >= limit:
                return out
    return out


def _contains_any(text: str, hints: Iterable[str]) -> bool:
    return any(hint in text for hint in hints)


def detect_source_policy(
    query: str,
    *,
    product_codes: List[str] | None = None,
    strict_title_terms: List[str] | None = None,
) -> Dict[str, Any]:
    text = str(query or "").lower()
    codes = list(product_codes or [])
    strict_terms = list(strict_title_terms or [])

    if strict_terms:
        return {
            "mode": "exact_title",
            "primary_source": "db_title",
            "allowed_candidate_sources": ["title_exact"],
            "use_db_metadata": True,
            "use_synopsis": False,
            "use_grok": False,
            "use_embedding": False,
            "hard_constraints": [
                "추천 후보의 제목 필드(title_ko/title_ja/original_title/title_en/title_zh)에 strict_title_terms가 실제로 포함되어야 한다.",
                "조건을 만족하지 않는 분위기/장르/태그 유사 후보는 추천하지 않는다.",
            ],
        }

    if codes and _contains_any(text, _SIMILAR_HINTS):
        return {
            "mode": "similar_by_work",
            "primary_source": "embedding",
            "allowed_candidate_sources": ["product_code", "embedding", "grok", "db_text"],
            "use_db_metadata": True,
            "use_synopsis": True,
            "use_grok": True,
            "use_embedding": True,
            "hard_constraints": [
                "언급된 품번을 기준점으로 삼고 임베딩 유사작을 우선 후보로 본다.",
                "추천 이유는 DB/Grok/시놉시스 근거와 함께 설명한다.",
            ],
        }

    if codes:
        return {
            "mode": "exact_product",
            "primary_source": "db_product_code",
            "allowed_candidate_sources": ["product_code"],
            "use_db_metadata": True,
            "use_synopsis": True,
            "use_grok": True,
            "use_embedding": False,
            "hard_constraints": [
                "사용자가 언급한 품번의 DB 메타데이터를 최우선으로 답한다.",
                "비슷한 작품을 명시적으로 요청하지 않았다면 임베딩 유사작을 후보로 섞지 않는다.",
            ],
        }

    if _contains_any(text, _SYNOPSIS_HINTS):
        return {
            "mode": "synopsis",
            "primary_source": "db_synopsis",
            "allowed_candidate_sources": ["db_synopsis"],
            "use_db_metadata": True,
            "use_synopsis": True,
            "use_grok": False,
            "use_embedding": False,
            "hard_constraints": [
                "줄거리/설정 질문은 시놉시스 필드에 근거한다.",
                "장면 태그나 임베딩만 맞는 작품은 핵심 후보로 추천하지 않는다.",
            ],
        }

    if _contains_any(text, _SCENE_HINTS):
        return {
            "mode": "scene_or_mood",
            "primary_source": "grok",
            "allowed_candidate_sources": ["grok", "db_text"],
            "use_db_metadata": True,
            "use_synopsis": True,
            "use_grok": True,
            "use_embedding": False,
            "hard_constraints": [
                "장면/분위기/관계성 질문은 Grok 장면 요약과 태그를 우선 근거로 삼는다.",
                "임베딩 유사도만으로 후보를 확정하지 않는다.",
            ],
        }

    if _contains_any(text, _SIMILAR_HINTS):
        return {
            "mode": "taste_recommendation",
            "primary_source": "persona_and_grok",
            "allowed_candidate_sources": ["db_text", "grok"],
            "use_db_metadata": True,
            "use_synopsis": True,
            "use_grok": True,
            "use_embedding": False,
            "hard_constraints": [
                "특정 기준 품번이 없으면 임베딩보다 DB/Grok/취향 프로필 근거를 우선한다.",
                "추천 이유에는 확인된 메타데이터나 Grok 근거를 붙인다.",
            ],
        }

    return {
        "mode": "general",
        "primary_source": "db_text",
        "allowed_candidate_sources": ["db_text", "grok"],
        "use_db_metadata": True,
        "use_synopsis": True,
        "use_grok": True,
        "use_embedding": False,
        "hard_constraints": [
            "정확 조건이 없을 때만 DB 텍스트/Grok/시놉시스를 함께 참고한다.",
            "검색 결과가 부족하면 추측으로 꾸미지 않는다.",
        ],
    }


def _split_csv(text: str | None) -> List[str]:
    if not text:
        return []
    return [v.strip() for v in text.replace("、", ",").split(",") if v.strip()]


def row_to_search_result(row: JAVMetadata, *, source: str, score: float = 1.0) -> Dict[str, Any]:
    return {
        "product_code": row.product_code or "",
        "title_ko": row.title_ko or "",
        "title_ja": row.title_ja or row.original_title or "",
        "actors": _split_csv(row.actors_ko or row.actors_ja or row.actors or ""),
        "genres": _split_csv(row.genres_ko or row.genres or ""),
        "maker": row.maker_ko or row.maker_ja or row.maker or "",
        "release_date": row.release_date or "",
        "synopsis": (row.synopsis_ko or row.synopsis_ja or row.synopsis or "")[:500],
        "favorite_score": int(row.favorite_score or 0),
        "folder_path": row.folder_path or "",
        "source": source,
        "score": round(float(score), 4),
    }


def _merge_result(results: List[Dict[str, Any]], item: Dict[str, Any]) -> None:
    pc = str(item.get("product_code") or "").strip().upper()
    if not pc:
        return
    for existing in results:
        if str(existing.get("product_code") or "").strip().upper() == pc:
            sources = set(str(existing.get("source") or "").split("+"))
            sources.update(str(item.get("source") or "").split("+"))
            existing["source"] = "+".join(sorted(s for s in sources if s))
            existing["score"] = max(float(existing.get("score") or 0), float(item.get("score") or 0))
            return
    results.append(item)


def _load_grok_summary(product_code: str) -> Dict[str, Any]:
    try:
        from javstory.translation.story_grok_module import load_cached_grok_json_flexible

        grok = load_cached_grok_json_flexible(product_code)
    except Exception:
        return {}
    if not grok or grok.get("verification_ok") is False or grok.get("code_mismatch"):
        return {}

    tags: List[str] = []
    tones: List[str] = []
    labels: List[str] = []
    for scene in grok.get("scenes") or []:
        if not isinstance(scene, dict):
            continue
        for tag in scene.get("key_tags") or []:
            if isinstance(tag, str) and tag.strip() and tag.strip() not in tags:
                tags.append(tag.strip())
        tone = str(scene.get("tone") or "").strip()
        if tone and tone not in tones:
            tones.append(tone)
        label = str(scene.get("scene_label") or "").strip()
        if label and label not in labels:
            labels.append(label)
    return {
        "summary": (grok.get("overall_summary") or grok.get("synopsis_short") or "")[:700],
        "tags": tags[:12],
        "tones": tones[:8],
        "labels": labels[:8],
        "scene_count": len(grok.get("scenes") or []),
    }


def _matches_grok(grok: Dict[str, Any], terms: Iterable[str]) -> bool:
    haystack = " ".join(
        [
            str(grok.get("summary") or ""),
            " ".join(grok.get("tags") or []),
            " ".join(grok.get("tones") or []),
            " ".join(grok.get("labels") or []),
        ]
    ).lower()
    return any(term.lower() in haystack for term in terms)


@dataclass
class PersonaLibrarySearch:
    limit: int = 8

    def search(
        self,
        query: str,
        *,
        product_codes: List[str] | None = None,
        fallback_seed_codes: List[str] | None = None,
    ) -> Dict[str, Any]:
        terms = split_query_terms(query)
        strict_title_terms = extract_strict_title_terms(query)
        codes = list(product_codes or extract_product_codes(query, limit=5))
        fallback_codes = [
            normalize_product_code(code)
            for code in list(fallback_seed_codes or [])
            if normalize_product_code(code)
        ]
        source_policy = detect_source_policy(
            query,
            product_codes=codes,
            strict_title_terms=strict_title_terms,
        )
        code_variants: List[str] = []
        for code in codes:
            for variant in product_code_variants(code):
                if variant not in code_variants:
                    code_variants.append(variant)
        results: List[Dict[str, Any]] = []

        with get_db_session_ctx() as session:
            if code_variants:
                rows = session.query(JAVMetadata).filter(JAVMetadata.product_code.in_(code_variants)).all()
                for row in rows:
                    item = row_to_search_result(row, source="product_code", score=1.0)
                    if source_policy.get("use_grok"):
                        item["grok"] = _load_grok_summary(item["product_code"])
                    _merge_result(results, item)

            if strict_title_terms:
                clauses = []
                for term in strict_title_terms:
                    like = f"%{term}%"
                    clauses.extend(
                        [
                            JAVMetadata.title_ko.ilike(like),
                            JAVMetadata.title_ja.ilike(like),
                            JAVMetadata.original_title.ilike(like),
                            JAVMetadata.title_en.ilike(like),
                            JAVMetadata.title_zh_cn.ilike(like),
                            JAVMetadata.title_zh_tw.ilike(like),
                        ]
                    )
                rows = (
                    session.query(JAVMetadata)
                    .filter(or_(*clauses))
                    .order_by(JAVMetadata.favorite_score.desc(), JAVMetadata.updated_at.desc())
                    .limit(self.limit)
                    .all()
                )
                for row in rows:
                    item = row_to_search_result(row, source="title_exact", score=0.98)
                    item["matched_title_terms"] = [
                        term
                        for term in strict_title_terms
                        if term.lower()
                        in " ".join(
                            [
                                str(row.title_ko or ""),
                                str(row.title_ja or ""),
                                str(row.original_title or ""),
                                str(row.title_en or ""),
                                str(row.title_zh_cn or ""),
                                str(row.title_zh_tw or ""),
                            ]
                        ).lower()
                    ]
                    if source_policy.get("use_grok"):
                        item["grok"] = _load_grok_summary(item["product_code"])
                    _merge_result(results, item)

            if terms and not strict_title_terms:
                clauses = []
                for term in terms:
                    like = f"%{term}%"
                    if source_policy.get("mode") == "synopsis":
                        clauses.extend(
                            [
                                JAVMetadata.title_ko.ilike(like),
                                JAVMetadata.title_ja.ilike(like),
                                JAVMetadata.original_title.ilike(like),
                                JAVMetadata.synopsis_ko.ilike(like),
                                JAVMetadata.synopsis_ja.ilike(like),
                                JAVMetadata.synopsis.ilike(like),
                            ]
                        )
                    else:
                        clauses.extend(
                            [
                                JAVMetadata.product_code.ilike(like),
                                JAVMetadata.title_ko.ilike(like),
                                JAVMetadata.title_ja.ilike(like),
                                JAVMetadata.original_title.ilike(like),
                                JAVMetadata.actors_ko.ilike(like),
                                JAVMetadata.actors_ja.ilike(like),
                                JAVMetadata.genres_ko.ilike(like),
                                JAVMetadata.genres_ja.ilike(like),
                                JAVMetadata.maker_ko.ilike(like),
                                JAVMetadata.maker_ja.ilike(like),
                                JAVMetadata.synopsis_ko.ilike(like),
                                JAVMetadata.synopsis_ja.ilike(like),
                                JAVMetadata.synopsis.ilike(like),
                            ]
                        )
                rows = (
                    session.query(JAVMetadata)
                    .filter(or_(*clauses))
                    .order_by(JAVMetadata.favorite_score.desc(), JAVMetadata.updated_at.desc())
                    .limit(self.limit * 3)
                    .all()
                )
                for row in rows:
                    source = "db_synopsis" if source_policy.get("mode") == "synopsis" else "db_text"
                    score = 0.82 if source == "db_synopsis" else 0.75
                    item = row_to_search_result(row, source=source, score=score)
                    grok = _load_grok_summary(item["product_code"]) if source_policy.get("use_grok") else {}
                    if grok:
                        item["grok"] = grok
                        if _matches_grok(grok, terms):
                            item["source"] = "db_text+grok"
                            item["score"] = 0.86
                    _merge_result(results, item)

        if source_policy.get("use_grok") and terms and not strict_title_terms and len(results) < self.limit:
            self._search_grok_cache(terms, results)

        if source_policy.get("use_embedding") and codes and not strict_title_terms:
            self._search_embedding_similar(codes[0], results)

        if not strict_title_terms and len(results) < self.limit:
            for seed_code in fallback_codes:
                if seed_code in codes:
                    continue
                self._search_embedding_similar(seed_code, results, top_k=max(10, self.limit))
                if len(results) >= self.limit:
                    break

        results.sort(key=lambda x: (float(x.get("score") or 0), int(x.get("favorite_score") or 0)), reverse=True)
        return {
            "query": query,
            "terms": terms,
            "strict_title_terms": strict_title_terms,
            "strict_title_contains": bool(strict_title_terms),
            "source_policy": source_policy,
            "product_codes": codes,
            "fallback_seed_codes": fallback_codes,
            "results": results[: self.limit],
        }

    def _search_grok_cache(self, terms: List[str], results: List[Dict[str, Any]]) -> None:
        try:
            from javstory.config.app_config import DATA_ROOT
        except Exception:
            return

        cache_dir = DATA_ROOT / "cache" / "story_context"
        if not cache_dir.is_dir():
            return

        for path in sorted(cache_dir.glob("*.json")):
            if len(results) >= self.limit:
                return
            pc = normalize_product_code(path.stem.split("_", 1)[0])
            if not pc:
                continue
            grok = _load_grok_summary(pc)
            if not grok or not _matches_grok(grok, terms):
                continue
            with get_db_session_ctx() as session:
                row = session.query(JAVMetadata).filter_by(product_code=pc).first()
                if row:
                    item = row_to_search_result(row, source="grok", score=0.82)
                else:
                    item = {"product_code": pc, "source": "grok", "score": 0.82}
                item["grok"] = grok
                _merge_result(results, item)

    def _search_embedding_similar(
        self,
        product_code: str,
        results: List[Dict[str, Any]],
        *,
        top_k: int | None = None,
    ) -> None:
        try:
            from javstory.library.embeddings.pipeline import (
                embeddings_enabled_from_env,
                embeddings_ollama_model_from_env,
            )
            from javstory.library.embeddings.similarity import find_similar_products
        except Exception:
            return

        if not embeddings_enabled_from_env():
            return

        model = embeddings_ollama_model_from_env()
        similar = find_similar_products(product_code, model=model, top_k=top_k or self.limit)
        if not similar:
            return

        codes = [item.product_code for item in similar]
        with get_db_session_ctx() as session:
            meta = {
                row.product_code: row
                for row in session.query(JAVMetadata).filter(JAVMetadata.product_code.in_(codes)).all()
            }
        for item in similar:
            row = meta.get(item.product_code)
            if row:
                result = row_to_search_result(row, source="embedding", score=item.score)
            else:
                result = {"product_code": item.product_code, "source": "embedding", "score": item.score}
            result["match_reasons"] = list(item.match_reasons or [])
            _merge_result(results, result)

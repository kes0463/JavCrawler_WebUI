"""라이브러리 목록 검색·월 필터·시청 피드백 헬퍼."""

from __future__ import annotations

import datetime
import re
from pathlib import Path
from typing import Any


def norm_token(s: str) -> str:
    return (s or "").strip().lower()


def tokenize_search_expr(q: str) -> list[str]:
    out: list[str] = []
    buf: list[str] = []
    in_quote = False
    for ch in q or "":
        if ch == '"':
            in_quote = not in_quote
            continue
        if ch.isspace() and not in_quote:
            if buf:
                out.append("".join(buf))
                buf = []
            continue
        buf.append(ch)
    if buf:
        out.append("".join(buf))
    return [t for t in out if t]


def parse_search_expr(q: str) -> tuple[list[list[str]], set[str], list[str]]:
    and_groups: list[list[str]] = []
    excludes: set[str] = set()
    text_terms: list[str] = []
    for tok in tokenize_search_expr(q):
        t = tok.strip()
        if not t:
            continue
        if t.startswith("-"):
            rest = t[1:]
            if rest.startswith("#"):
                rest = rest[1:]
            if rest:
                excludes.add(norm_token(rest))
            continue
        if t.startswith("#"):
            parts = [p for p in t.split("|") if p.strip()]
            group: list[str] = []
            for p in parts:
                p = p.strip()
                if p.startswith("#"):
                    p = p[1:]
                if p:
                    group.append(norm_token(p))
            if group:
                and_groups.append(group)
            continue
        text_terms.append(norm_token(t))
    return and_groups, excludes, text_terms


def summary_genre_set(s: Any) -> set[str]:
    raw = getattr(s, "genres_ko", None) or ""
    return {norm_token(g) for g in str(raw).split(",") if g and g.strip()}


def summary_text_blob(s: Any) -> str:
    pc = getattr(s, "product_code", "") or ""
    tk = getattr(s, "title_ko", "") or ""
    tj = getattr(s, "title_ja", "") or ""
    ak = getattr(s, "actors_ko", "") or ""
    gk = getattr(s, "genres_ko", None) or ""
    mk = getattr(s, "maker_ko", None) or ""
    return f"{pc} {tk} {tj} {ak} {gk} {mk}".lower()


def match_summary(
    s: Any,
    genre_groups: list[list[str]],
    excludes: set[str],
    text_terms: list[str],
) -> bool:
    if genre_groups or excludes:
        gset = summary_genre_set(s)
        for group in genre_groups:
            if not any(g in gset for g in group):
                return False
        if excludes and (excludes & gset):
            return False
    if text_terms:
        blob = summary_text_blob(s)
        for term in text_terms:
            if term and term not in blob:
                return False
    return True


_RE_MONTH = re.compile(r"^\s*(\d{4})[-/.](\d{2})")


def release_month_key(release_date: Any) -> str:
    s = str(release_date or "").strip()
    if not s:
        return "unknown"
    m = _RE_MONTH.match(s)
    if not m:
        return "unknown"
    y = m.group(1)
    mm = m.group(2)
    try:
        mi = int(mm)
        if mi < 1 or mi > 12:
            return "unknown"
    except Exception:
        return "unknown"
    return f"{y}-{mm}"


def build_watch_feedback_by_base() -> dict[str, dict]:
    out: dict[str, dict] = {}
    try:
        from javstory.harvest.database import WatchHistory, get_db_session_ctx
        from javstory.utils.product_code import strip_split_suffixes

        with get_db_session_ctx() as session:
            rows = session.query(WatchHistory).all()

        mn = datetime.datetime.min.replace(tzinfo=None)
        for wh in rows:
            raw = (wh.product_code or "").strip().upper()
            if not raw:
                continue
            try:
                base = strip_split_suffixes(raw) or raw
            except Exception:
                base = raw
            rating = int(wh.rating or 0)
            liked = bool(wh.liked)
            watch_later = bool(getattr(wh, "watch_later", False))
            ua = getattr(wh, "updated_at", None) or mn
            wla = getattr(wh, "watch_later_added_at", None) or mn

            rec = out.get(base)
            if not rec:
                out[base] = {
                    "rating": rating,
                    "liked": liked,
                    "watch_later": watch_later,
                    "watch_later_added_at": wla,
                    "updated_at": ua,
                }
            else:
                rec["rating"] = max(int(rec.get("rating") or 0), rating)
                rec["liked"] = bool(rec.get("liked")) or liked
                rec["watch_later"] = bool(rec.get("watch_later")) or watch_later
                if wla > (rec.get("watch_later_added_at") or mn):
                    rec["watch_later_added_at"] = wla
                if ua > (rec.get("updated_at") or mn):
                    rec["updated_at"] = ua

        for _, rec in out.items():
            ua = rec.get("updated_at") or mn
            if ua and ua != mn:
                try:
                    rec["feedback_iso"] = ua.replace(microsecond=0).isoformat(sep=" ")
                except Exception:
                    rec["feedback_iso"] = ""
            else:
                rec["feedback_iso"] = ""
            wla = rec.get("watch_later_added_at") or mn
            if wla and wla != mn:
                try:
                    rec["watch_later_added_iso"] = wla.replace(microsecond=0).isoformat(sep=" ")
                except Exception:
                    rec["watch_later_added_iso"] = ""
            else:
                rec["watch_later_added_iso"] = ""
    except Exception:
        return {}
    return out


def preview_path_for(
    pc: str,
    e_root: Path | None,
    legacy_root: Path | None,
) -> str:
    code = (pc or "").strip().upper()
    if not code:
        return ""
    cand: list[Path] = []
    if e_root:
        cand.append(Path(e_root) / code / "Preview" / "preview.webp")
    if legacy_root:
        cand.append(Path(legacy_root) / code / "Preview" / "preview.webp")
    for p in cand:
        try:
            if p.is_file() and p.stat().st_size > 0:
                return str(p.resolve())
        except Exception:
            continue
    return ""

from javstory.harvest.database import get_db_session, Actress, commit_with_retry
from javstory.utils.actress_profile import (
    _build_actress_name_index,
    _ensure_alias,
    _has_hangul,
    _looks_like_ja,
    _resolve_actress_id_in_session,
    normalize_actor_name_key,
)
from javstory.utils.common import dedupe_preserve_order


def _display_names_from_row(row: Actress, crawled_name: str) -> tuple[str, str, str]:
    """프로필 표시명 — DB에 저장된 이름 우선, 크롬 원문은 보조."""
    ja = (row.name_ja or row.japanese or "").strip() or (crawled_name or "").strip()
    ko = (row.name_ko or row.korean or "").strip()
    if not ko:
        ko = ja
    ro = (row.romaji or row.name_en or "").strip() or ja
    return ja, ko, ro


def _resolve_actress_row_in_session(
    session,
    name: str,
    *,
    name_index: dict[str, list[int]],
) -> tuple[Actress | None, int | None]:
    actress_id = _resolve_actress_id_in_session(session, name)
    if not actress_id:
        key = normalize_actor_name_key(name)
        if key:
            ids = name_index.get(key) or []
            actress_id = int(ids[0]) if ids else None
    if not actress_id:
        return None, None
    row = session.query(Actress).filter_by(id=actress_id).first()
    if not row:
        return None, None
    return row, int(row.id)


def _link_ja_crawl_to_seen_actress(
    session,
    ja_name: str,
    seen_actress_ids: set[int],
) -> Actress | None:
    """123av 한글명 + njav 일본어 표기 등 이중 크롤을 같은 배우 프로필로 연결."""
    if len(seen_actress_ids) != 1:
        return None
    ja_name = (ja_name or "").strip()
    if not ja_name or not _looks_like_ja(ja_name) or _has_hangul(ja_name):
        return None
    aid = next(iter(seen_actress_ids))
    row = session.query(Actress).filter_by(id=aid).first()
    if not row:
        return None
    _ensure_alias(session, aid, ja_name, alias_type="crawl_ja")
    if not (row.name_ja or row.japanese or "").strip():
        row.name_ja = ja_name
        row.japanese = ja_name
    commit_with_retry(session)
    return row


def collapse_actor_name_lists(
    ja_list: list[str],
    ko_list: list[str],
    ro_list: list[str],
    *,
    actress_ids: list[int | None] | None = None,
) -> tuple[list[str], list[str], list[str]]:
    """동일 배우 중복 제거 — actress_id 우선, 한국어 표시명 우선."""
    n = min(len(ja_list), len(ko_list), len(ro_list))
    if n == 0:
        return [], [], []

    ids = (actress_ids or [])[:n]
    if len(ids) < n:
        ids = ids + [None] * (n - len(ids))

    triples = list(zip(ids, ja_list[:n], ko_list[:n], ro_list[:n]))
    has_hangul_ko = any(_has_hangul(ko) for _, _, ko, _ in triples)

    ja_out: list[str] = []
    ko_out: list[str] = []
    ro_out: list[str] = []
    seen_ids: set[int] = set()
    seen_ko: set[str] = set()

    for aid, ja, ko, ro in triples:
        ja = (ja or "").strip()
        ko = (ko or "").strip()
        ro = (ro or "").strip()
        if not ko:
            continue
        if aid is not None and int(aid) in seen_ids:
            continue
        ko_key = normalize_actor_name_key(ko)
        if ko_key in seen_ko:
            continue
        if has_hangul_ko and _looks_like_ja(ko) and not _has_hangul(ko):
            ja_key = normalize_actor_name_key(ja)
            if any(
                _has_hangul(k)
                and normalize_actor_name_key(j) == ja_key
                for _, j, k, _ in triples
            ):
                continue
        if aid is not None:
            seen_ids.add(int(aid))
        seen_ko.add(ko_key)
        ja_out.append(ja or ko)
        ko_out.append(ko)
        ro_out.append(ro or ko)

    return ja_out, ko_out, ro_out


def dedupe_crawled_actor_names(session, names: list[str]) -> list[str]:
    """크롤 직후 — DB 프로필·별명(합치기) 기준 dedupe."""
    from javstory.utils.actress_profile import dedupe_crawled_actor_tokens

    return dedupe_crawled_actor_tokens(names, session=session)


def lookup_actress_display_names(name: str, session=None) -> tuple[str, str, str] | None:
    """이름·별명으로 배우 프로필 조회. 없으면 None (신규 생성 없음)."""
    name = (name or "").strip()
    if not name:
        return None
    close_session = False
    if session is None:
        session = get_db_session()
        close_session = True
    try:
        name_index = _build_actress_name_index(session)
        row, _aid = _resolve_actress_row_in_session(session, name, name_index=name_index)
        if not row:
            return None
        return _display_names_from_row(row, name)
    finally:
        if close_session:
            session.close()


class ActressResolver:
    """
    메인 DB(actresses)에서 배우 JA/KO/로마자 이름을 매핑한다.
    별명(actress_aliases)과 name_ko/name_ja 컬럼까지 조회한다.
    """

    def __init__(self):
        pass

    def resolve_names(self, japanese_names: list[str] | str) -> dict[str, list[str]]:
        """
        일본어/한글 크롤 이름 리스트를 받아 각 언어별 리스트로 반환.
        123av(한글) + njav(일본어) 이중 표기는 같은 배우로 병합한다.
        """
        if isinstance(japanese_names, str):
            japanese_names = [n.strip() for n in japanese_names.split(",") if n.strip()]
        japanese_names = dedupe_preserve_order(
            [str(n).strip() for n in japanese_names if str(n).strip()],
            key=normalize_actor_name_key,
        )

        if not japanese_names:
            return {"ja": [], "ko": [], "romaji": [], "zh_cn": [], "zh_tw": []}

        ja_list: list[str] = []
        ko_list: list[str] = []
        ro_list: list[str] = []
        actress_ids: list[int | None] = []
        deferred_ja: list[str] = []

        session = get_db_session()
        try:
            name_index = _build_actress_name_index(session)
            seen_actress_ids: set[int] = set()

            for name in japanese_names:
                name = name.strip()
                if not name:
                    continue

                row, actress_id = _resolve_actress_row_in_session(
                    session, name, name_index=name_index
                )
                if row and actress_id is not None:
                    if actress_id in seen_actress_ids:
                        continue
                    ja_val, ko_val, ro_val = _display_names_from_row(row, name)
                    seen_actress_ids.add(actress_id)
                    ja_list.append(ja_val)
                    ko_list.append(ko_val)
                    ro_list.append(ro_val)
                    actress_ids.append(actress_id)
                    continue

                if _looks_like_ja(name) and not _has_hangul(name):
                    deferred_ja.append(name)
                    continue

                new_actress = Actress(
                    japanese=name,
                    name_ja=name,
                    korean=None,
                    romaji=None,
                    needs_review=True,
                )
                session.add(new_actress)
                commit_with_retry(session)
                name_index = _build_actress_name_index(session)
                actress_id = int(new_actress.id)
                seen_actress_ids.add(actress_id)
                ja_list.append(name)
                ko_list.append(name)
                ro_list.append(name)
                actress_ids.append(actress_id)

            for ja_name in deferred_ja:
                row = _link_ja_crawl_to_seen_actress(session, ja_name, seen_actress_ids)
                if row is None:
                    row, actress_id = _resolve_actress_row_in_session(
                        session, ja_name, name_index=name_index
                    )
                if row is None:
                    new_actress = Actress(
                        japanese=ja_name,
                        name_ja=ja_name,
                        korean=None,
                        romaji=None,
                        needs_review=True,
                    )
                    session.add(new_actress)
                    commit_with_retry(session)
                    name_index = _build_actress_name_index(session)
                    actress_id = int(new_actress.id)
                    seen_actress_ids.add(actress_id)
                    ja_list.append(ja_name)
                    ko_list.append(ja_name)
                    ro_list.append(ja_name)
                    actress_ids.append(actress_id)
                    continue

                actress_id = int(row.id)
                if actress_id in seen_actress_ids:
                    continue
                ja_val, ko_val, ro_val = _display_names_from_row(row, ja_name)
                seen_actress_ids.add(actress_id)
                ja_list.append(ja_val)
                ko_list.append(ko_val)
                ro_list.append(ro_val)
                actress_ids.append(actress_id)
        except Exception as e:
            print(f"[ActressResolver] Error: {e}")
            return {
                "ja": japanese_names,
                "ko": japanese_names,
                "romaji": japanese_names,
                "zh_cn": japanese_names,
                "zh_tw": japanese_names,
            }
        finally:
            session.close()

        ja_list, ko_list, ro_list = collapse_actor_name_lists(
            ja_list, ko_list, ro_list, actress_ids=actress_ids
        )
        zh_cn_list = list(ro_list)
        zh_tw_list = list(ro_list)

        return {
            "ja": ja_list,
            "ko": ko_list,
            "romaji": ro_list,
            "zh_cn": zh_cn_list,
            "zh_tw": zh_tw_list,
        }


if __name__ == "__main__":
    resolver = ActressResolver()
    test_names = ["三上悠亜", "白石茉莉奈"]
    result = resolver.resolve_names(test_names)
    print(f"매핑 결과: {result}")

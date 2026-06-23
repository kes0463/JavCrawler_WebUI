from javstory.harvest.database import get_db_session, Actress
from javstory.utils.actress_profile import resolve_actress_by_name


def _display_names_from_row(row: Actress, crawled_name: str) -> tuple[str, str, str]:
    """프로필 행에서 JA/KO/로마자 표시명 추출. KO는 name_ko 우선(합치기·별명 반영)."""
    ja = (crawled_name or row.name_ja or row.japanese or "").strip() or crawled_name
    ko = (row.name_ko or row.korean or "").strip()
    ro = (row.romaji or "").strip()
    if not ko:
        ko = ja
    if not ro:
        ro = ja
    return ja, ko, ro


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
        actress_id = resolve_actress_by_name(name)
        if not actress_id:
            return None
        row = session.query(Actress).filter_by(id=actress_id).first()
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
        일본어 이름 리스트(또는 쉼표 구분 문자열)를 받아 각 언어별 리스트로 반환.
        매핑 데이터가 없으면 원본 일본어 이름을 보관하여 추후 수동 수정을 지원함.
        """
        if isinstance(japanese_names, str):
            japanese_names = [n.strip() for n in japanese_names.split(",") if n.strip()]

        ja_list: list[str] = []
        ko_list: list[str] = []
        ro_list: list[str] = []
        zh_cn_list: list[str] = []
        zh_tw_list: list[str] = []

        if not japanese_names:
            return {"ja": [], "ko": [], "romaji": [], "zh_cn": [], "zh_tw": []}

        session = get_db_session()
        try:
            for name in japanese_names:
                name = name.strip()
                if not name:
                    continue

                row = None
                actress_id = resolve_actress_by_name(name)
                if actress_id:
                    row = session.query(Actress).filter_by(id=actress_id).first()

                if row:
                    ja_val, ko_val, ro_val = _display_names_from_row(row, name)
                else:
                    new_actress = Actress(
                        japanese=name,
                        name_ja=name,
                        korean=None,
                        romaji=None,
                        needs_review=True,
                    )
                    session.add(new_actress)
                    session.commit()
                    ja_val, ko_val, ro_val = name, name, name

                ja_list.append(ja_val)
                ko_list.append(ko_val)
                ro_list.append(ro_val)
                zh_cn_list.append(ro_val)
                zh_tw_list.append(ro_val)
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

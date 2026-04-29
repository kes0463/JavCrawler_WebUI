import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from javstory.harvest.database import get_db_session_ctx, JAVMetadata, Actress, Genre, Maker
from javstory.utils.common import tagify as _tagify


def resync_all_metadata(product_codes=None, logger_func=None) -> dict:
    """
    jav_metadata 테이블을 마스터 테이블(actresses/genres/makers) 기준으로 재동기화.
    GUI 버튼에서 직접 호출. AI 번역 없음 -- 마스터 테이블에 입력된 값만 전파.

    Args:
        product_codes: None이면 전체 처리. 리스트 지정 시 해당 품번만 처리.
        logger_func: GUI 로그 콜백 (없으면 print).

    Returns:
        dict with keys: updated, still_pending, skipped, errors
    """
    log = logger_func if logger_func else print
    log("[Resync] 메타데이터 재동기화 시작...")

    stats = {"updated": 0, "still_pending": 0, "skipped": 0, "errors": 0}

    with get_db_session_ctx() as session:
        query = session.query(JAVMetadata)
        if product_codes:
            codes_upper = [c.upper() for c in product_codes]
            query = query.filter(JAVMetadata.product_code.in_(codes_upper))
        rows = query.all()
        total = len(rows)
        log(f"[Resync] 처리 대상: {total}건")

        for i, row in enumerate(rows, 1):
            code = row.product_code
            try:
                changed = False

                # ── 1. 배우 (actors_ja 기준 재매핑) ──────────────────────
                actors_ja_raw = row.actors_ja or row.actors or ""
                if actors_ja_raw:
                    ja_names = [n.strip() for n in actors_ja_raw.split(",") if n.strip()]
                    ko_list, ro_list, pending_count = [], [], 0
                    for name in ja_names:
                        a = session.query(Actress).filter_by(japanese=name).first()
                        if a and a.korean:
                            ko_list.append(a.korean)
                            ro_list.append(a.romaji or a.korean)
                        else:
                            ko_list.append(name)
                            ro_list.append(name)
                            pending_count += 1
                    new_ko = _tagify(ko_list)
                    new_ro = _tagify(ro_list)
                    if row.actors_ko != new_ko or row.actors_romaji != new_ro:
                        row.actors_ko = new_ko
                        row.actors_romaji = new_ro
                        row.actors_zh_cn = new_ro
                        row.actors_zh_tw = new_ro
                        row.actors = actors_ja_raw
                        changed = True
                    if pending_count > 0:
                        stats["still_pending"] += pending_count
                        log(f"[Resync]   배우 {pending_count}명 아직 미입력: {code}")
                else:
                    stats["skipped"] += 1

                # ── 2. 장르 (genres_ja 기준 재매핑) ──────────────────────
                genres_ja_raw = row.genres_ja or row.genres or ""
                if genres_ja_raw:
                    ja_genres = [g.strip() for g in genres_ja_raw.split(",") if g.strip()]
                    ko_list, en_list = [], []
                    for name in ja_genres:
                        g = session.query(Genre).filter_by(japanese=name).first()
                        if g and g.korean:
                            ko_list.append(g.korean)
                            en_list.append(g.english or g.korean)
                        else:
                            ko_list.append(name)
                            en_list.append(name)
                            stats["still_pending"] += 1
                    new_ko = _tagify(ko_list)
                    new_en = _tagify(en_list)
                    if row.genres_ko != new_ko or row.genres_en != new_en:
                        row.genres_ko = new_ko
                        row.genres_en = new_en
                        row.genres_zh_cn = new_en
                        row.genres_zh_tw = new_en
                        row.genres = new_ko
                        changed = True

                # ── 3. 제작사 (maker_ja 기준 재매핑) ─────────────────────
                maker_ja_raw = row.maker_ja or row.maker or ""
                if maker_ja_raw:
                    m = session.query(Maker).filter_by(japanese=maker_ja_raw.strip()).first()
                    if m and m.korean:
                        new_ko = m.korean
                        new_en = m.english or m.korean
                    else:
                        new_ko = maker_ja_raw
                        new_en = maker_ja_raw
                        stats["still_pending"] += 1
                    if row.maker_ko != new_ko or row.maker_en != new_en:
                        row.maker_ko = new_ko
                        row.maker_en = new_en
                        row.maker_zh_cn = new_en
                        row.maker_zh_tw = new_en
                        row.maker = new_ko
                        changed = True

                if changed:
                    session.commit()
                    stats["updated"] += 1
                    log(f"[Resync]   갱신 완료: {code} ({i}/{total})")

            except Exception as e:
                try:
                    session.rollback()
                except Exception:
                    pass
                stats["errors"] += 1
                log(f"[Resync]   오류: {code} - {e}")

    log(
        f"[Resync] 완료 -- 갱신: {stats['updated']}건 | "
        f"미완료: {stats['still_pending']}건 | "
        f"건너뜀: {stats['skipped']}건 | "
        f"오류: {stats['errors']}건"
    )
    return stats


def get_pending_items(logger_func=None) -> dict:
    """
    마스터 테이블에서 아직 번역 미입력(needs_review=True 또는 korean=None) 항목 조회.
    GUI 확인 필요 목록 표시 용도.

    Returns:
        dict: {actresses: [...], genres: [...], makers: [...]}
        각 항목은 {"id": int, "japanese": str}
    """
    log = logger_func if logger_func else print
    with get_db_session_ctx() as session:
        pending_actresses = [
            {"id": r.id, "japanese": r.japanese}
            for r in session.query(Actress).filter(
                (Actress.needs_review == True) | (Actress.korean == None)
            ).all()
        ]
        pending_genres = [
            {"id": r.id, "japanese": r.japanese}
            for r in session.query(Genre).filter(
                (Genre.needs_review == True) | (Genre.korean == None)
            ).all()
        ]
        pending_makers = [
            {"id": r.id, "japanese": r.japanese}
            for r in session.query(Maker).filter(
                (Maker.needs_review == True) | (Maker.korean == None)
            ).all()
        ]
        result = {
            "actresses": pending_actresses,
            "genres": pending_genres,
            "makers": pending_makers,
        }
        total = len(pending_actresses) + len(pending_genres) + len(pending_makers)
        log(
            f"[Resync] 확인 필요 -- 배우: {len(pending_actresses)}명 | "
            f"장르: {len(pending_genres)}개 | "
            f"제작사: {len(pending_makers)}개 (합계: {total})"
        )
        return result


if __name__ == "__main__":
    result = resync_all_metadata()
    print(f"\n결과: {result}")
    pending = get_pending_items()
    for cat, items in pending.items():
        names = [x["japanese"] for x in items]
        print(f"{cat}: {names}")

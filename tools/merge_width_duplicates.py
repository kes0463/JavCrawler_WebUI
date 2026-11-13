"""반각/전각·대소문자만 다른 중복 행 정리 (actresses / genres / makers).

기본은 **미리보기(읽기 전용)** — DB 를 열기만 하고 아무것도 쓰지 않는다.
    python tools/merge_width_duplicates.py            # 미리보기 + 보고서 파일
    python tools/merge_width_duplicates.py --apply    # 백업 → 한 트랜잭션으로 적용 → 검증

정리 범위 (보수적)
- actresses: 그룹마다 남길 행(keeper) 하나에 actress_works / actress_images / actress_aliases 를
  옮기고, 지워지는 행의 이름은 keeper 의 별명(alias_type='other')으로 남긴다. keeper 의 빈
  칸만 지워지는 행 값으로 채운다(덮어쓰지 않음). work_count 는 옮긴 뒤 다시 센다.
- genres / makers: 마스터 표의 중복 행만 삭제. keeper 에 번역이 없으면 지워지는 행의 번역을
  옮긴다.
- 건드리지 않음: jav_metadata 의 작품별 텍스트(actors_*, genres_*, maker_*), user_preferences.
  (작품별 텍스트는 작품마다 따로 저장된 값이라 마스터 정리와 무관하다.)

keeper 선택 규칙: ① 반각 가나 없는 표기 ② (장르/메이커) 번역 있음 / (배우) 사용자 데이터·연결
많음 ③ 대문자 많은 표기(123av 가 'AIKA'→'Aika' 처럼 바꿔 줌) ④ id 작은 것.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "db" / "jav_database.db"
BACKUP_DIR = None  # 대상 DB 옆 backups/ (main 에서 결정)
REPORT_DIR = ROOT / "logs"

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

_HALF_KANA = re.compile(r"[｡-ﾟ]")
_ACTRESS_USER_COLS = ("is_favorite", "user_score", "memo", "favorite_intensity", "strong_reaction_count", "watch_count")
# keeper 가 비어 있을 때만 채우는 칼럼
_ACTRESS_FILL_COLS = (
    "korean", "romaji", "name_ja", "name_ko", "name_en", "profile_image_url", "genres", "user_score",
    "profile_text", "birth_date", "height", "bust", "waist", "hip", "cup_size", "debut_date", "agency",
    "is_favorite", "favorite_intensity", "strong_reaction_count", "watch_count", "last_watched", "memo",
    "translation_note",
)


def width_key(s: str | None) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s or "")).strip().casefold()


def _empty(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip()) or v == 0


def _upper_count(s: str) -> int:
    return sum(1 for c in s if c.isupper())


def _groups(con: sqlite3.Connection, table: str) -> list[list[dict]]:
    g: dict[str, list[dict]] = {}
    for r in con.execute(f"SELECT * FROM {table} WHERE japanese IS NOT NULL AND TRIM(japanese) != ''"):
        g.setdefault(width_key(r["japanese"]), []).append(dict(r))
    return [sorted(v, key=lambda x: x["id"]) for v in g.values() if len(v) > 1]


# ---------------------------------------------------------------- 계획 수립


def plan_actresses(con: sqlite3.Connection) -> list[dict]:
    works = dict(con.execute("SELECT actress_id, COUNT(*) FROM actress_works GROUP BY actress_id").fetchall())
    imgs = dict(con.execute("SELECT actress_id, COUNT(*) FROM actress_images GROUP BY actress_id").fetchall())
    als = dict(con.execute("SELECT actress_id, COUNT(*) FROM actress_aliases GROUP BY actress_id").fetchall())
    plans = []
    for rows in _groups(con, "actresses"):
        for r in rows:
            r["_works"], r["_imgs"], r["_als"] = works.get(r["id"], 0), imgs.get(r["id"], 0), als.get(r["id"], 0)
            r["_user"] = [c for c in _ACTRESS_USER_COLS if not _empty(r.get(c))]

        def rank(r):
            return (
                bool(_HALF_KANA.search(r["japanese"])),
                -len(r["_user"]),
                -(r["_works"] + r["_imgs"] + r["_als"]),
                -_upper_count(r["japanese"]),
                r["id"],
            )

        ordered = sorted(rows, key=rank)
        keeper, losers = ordered[0], ordered[1:]
        fills = {}
        for c in _ACTRESS_FILL_COLS:
            if _empty(keeper.get(c)):
                for lo in losers:
                    if not _empty(lo.get(c)):
                        v = lo[c]
                        # 일본어 이름 칸은 반각 표기로 채우지 않는다
                        fills[c] = unicodedata.normalize("NFKC", v) if c == "name_ja" and isinstance(v, str) else v
                        break
        plans.append({"keeper": keeper, "losers": losers, "fills": fills})
    return plans


def load_overrides(path: Path | None) -> dict[str, str]:
    """`일본어<TAB>남길 한국어` 형식(# 주석 가능). 키는 표기 폭 무관하게 대조한다."""
    out: dict[str, str] = {}
    if not path:
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "\t" not in line:
            continue
        ja, ko = line.split("\t", 1)
        if ja.strip() and ko.strip():
            out[width_key(ja)] = ko.strip()
    return out


def plan_master(con: sqlite3.Connection, table: str, overrides: dict[str, str] | None = None) -> list[dict]:
    plans = []
    for rows in _groups(con, table):
        def rank(r):
            return (
                bool(_HALF_KANA.search(r["japanese"])),
                _empty(r.get("korean")),
                -_upper_count(r["japanese"]),
                r["id"],
            )

        ordered = sorted(rows, key=rank)
        keeper, losers = ordered[0], ordered[1:]
        fills = {}
        for c in ("korean", "english") + (("slug",) if table == "makers" else ()):
            if _empty(keeper.get(c)):
                for lo in losers:
                    if not _empty(lo.get(c)):
                        fills[c] = lo[c]
                        break
        ov = (overrides or {}).get(width_key(keeper["japanese"]))
        if ov and ov != (keeper.get("korean") or ""):
            fills["korean"] = ov
            # 영어도 같은 행(지워지는 쪽)에서 왔다면 같이 가져온다
            src = next((lo for lo in losers if (lo.get("korean") or "") == ov), None)
            if src is not None and not _empty(src.get("english")):
                fills["english"] = src["english"]
        if fills.get("korean") and keeper.get("needs_review"):
            fills["needs_review"] = 0
        plans.append({"keeper": keeper, "losers": losers, "fills": fills, "override": bool(ov)})
    return plans


# ---------------------------------------------------------------- 보고서


def render_report(actress_plans, genre_plans, maker_plans) -> str:
    out: list[str] = []
    w = out.append
    w(f"# 반각/전각 중복 정리 미리보기  ({dt.datetime.now():%Y-%m-%d %H:%M})")
    w(f"DB: {DB_PATH}")
    n_al = sum(len(p["losers"]) for p in actress_plans)
    w("")
    w(f"배우 {len(actress_plans)}그룹 (삭제될 행 {n_al}) / 장르 {len(genre_plans)}그룹 / 메이커 {len(maker_plans)}그룹")
    w("작품별 텍스트(jav_metadata)와 취향 점수(user_preferences)는 변경하지 않음.")

    w("\n## 배우  [남김 ← 합쳐짐]")
    for p in actress_plans:
        k = p["keeper"]
        w(f"- 남김 #{k['id']} {k['japanese']} / {k.get('korean') or '-'}  (작품 {k['_works']}, 이미지 {k['_imgs']}, 별명 {k['_als']}{', 사용자데이터 ' + ','.join(k['_user']) if k['_user'] else ''})")
        for lo in p["losers"]:
            ko_note = "" if (lo.get("korean") or "") == (k.get("korean") or "") else f"  ※ 한국어명 다름 → '{lo.get('korean')}' 은 별명으로"
            w(f"    ← #{lo['id']} {lo['japanese']} / {lo.get('korean') or '-'}  (작품 {lo['_works']}, 이미지 {lo['_imgs']}, 별명 {lo['_als']}{', 사용자데이터 ' + ','.join(lo['_user']) if lo['_user'] else ''}){ko_note}")
        if p["fills"]:
            w(f"    빈 칸 채움: {', '.join(f'{c}={str(v)[:30]}' for c, v in p['fills'].items())}")

    for title, plans in (("장르", genre_plans), ("메이커", maker_plans)):
        diff = [p for p in plans if len({(r.get("korean") or "") for r in [p["keeper"], *p["losers"]] if r.get("korean")}) > 1]
        w(f"\n## {title}  — 번역이 서로 다른 {len(diff)}그룹 (남는 번역 확인 필요)")
        for p in diff:
            k = p["keeper"]
            others = ", ".join(f"{lo['japanese']}→{lo.get('korean') or '-'}" for lo in p["losers"])
            final = p["fills"].get("korean") or k.get("korean") or "-"
            mark = f"  ★지정: '{k.get('korean')}' 대신 '{final}'" if p.get("override") else ""
            w(f"- 남김: {k['japanese']} → {final}    | 삭제: {others}{mark}")
        w(f"\n## {title}  — 번역 같거나 한쪽만 있는 {len(plans) - len(diff)}그룹")
        for p in plans:
            if p in diff:
                continue
            k = p["keeper"]
            fill = f"  (번역 옮김: {p['fills'].get('korean')})" if p["fills"].get("korean") else ""
            w(f"- 남김: {k['japanese']} → {k.get('korean') or p['fills'].get('korean') or '-'}    | 삭제: {', '.join(lo['japanese'] for lo in p['losers'])}{fill}")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- 적용


def backup(src: sqlite3.Connection, db_path: Path) -> Path:
    bdir = db_path.parent / "backups"
    bdir.mkdir(parents=True, exist_ok=True)
    dst_path = bdir / f"jav_database.before_width_merge.{dt.datetime.now():%Y%m%d-%H%M%S}.db"
    dst = sqlite3.connect(dst_path)
    try:
        src.backup(dst)  # WAL 포함 일관된 스냅샷
    finally:
        dst.close()
    chk = sqlite3.connect(f"file:{dst_path}?mode=ro", uri=True)
    try:
        ok = chk.execute("PRAGMA integrity_check").fetchone()[0]
        n = chk.execute("SELECT COUNT(*) FROM jav_metadata").fetchone()[0]
    finally:
        chk.close()
    if ok != "ok":
        raise RuntimeError(f"백업 무결성 검사 실패: {ok}")
    print(f"[백업] {dst_path}  (integrity ok, jav_metadata {n}건)")
    return dst_path


def _set_fields(cur, table: str, row_id: int, fields: dict) -> None:
    if not fields:
        return
    cols = ", ".join(f"{c} = ?" for c in fields)
    cur.execute(f"UPDATE {table} SET {cols} WHERE id = ?", [*fields.values(), row_id])


def apply(con: sqlite3.Connection, actress_plans, genre_plans, maker_plans) -> dict:
    cur = con.cursor()
    stats = {"actress_rows_deleted": 0, "works_moved": 0, "works_dup_dropped": 0, "images_moved": 0,
             "aliases_moved": 0, "aliases_added": 0, "genre_rows_deleted": 0, "maker_rows_deleted": 0}
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for p in actress_plans:
        kid = p["keeper"]["id"]
        # 지워지는 행 이름(일본어·한국어)을 먼저 별명으로 — 이름이 비면 같은 문자열은 건너뜀
        existing = {r[0] for r in cur.execute("SELECT alias_name FROM actress_aliases WHERE actress_id = ?", (kid,))}
        existing |= {p["keeper"]["japanese"], p["keeper"].get("korean") or ""}
        for lo in p["losers"]:
            lid = lo["id"]
            before = cur.execute("SELECT COUNT(*) FROM actress_works WHERE actress_id = ?", (lid,)).fetchone()[0]
            cur.execute(
                "INSERT OR IGNORE INTO actress_works (actress_id, product_code, match_source, matched_token, updated_at) "
                "SELECT ?, product_code, match_source, matched_token, updated_at FROM actress_works WHERE actress_id = ?",
                (kid, lid),
            )
            moved = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
            cur.execute("DELETE FROM actress_works WHERE actress_id = ?", (lid,))
            stats["works_moved"] += moved
            stats["works_dup_dropped"] += before - moved
            cur.execute("UPDATE actress_images SET actress_id = ? WHERE actress_id = ?", (kid, lid))
            stats["images_moved"] += cur.rowcount
            # 별명 이동 (keeper 에 이미 같은 이름이 있으면 지워지는 쪽 별명은 버림)
            for alias_id, name in cur.execute("SELECT alias_id, alias_name FROM actress_aliases WHERE actress_id = ?", (lid,)).fetchall():
                if name in existing:
                    cur.execute("DELETE FROM actress_aliases WHERE alias_id = ?", (alias_id,))
                else:
                    cur.execute("UPDATE actress_aliases SET actress_id = ? WHERE alias_id = ?", (kid, alias_id))
                    existing.add(name)
                    stats["aliases_moved"] += 1
            for name in (lo["japanese"], lo.get("korean") or ""):
                if name and name not in existing:
                    cur.execute(
                        "INSERT INTO actress_aliases (actress_id, alias_name, alias_type, is_primary, created_at) VALUES (?, ?, 'other', 0, ?)",
                        (kid, name, now),
                    )
                    existing.add(name)
                    stats["aliases_added"] += 1
            cur.execute("DELETE FROM actresses WHERE id = ?", (lid,))
            stats["actress_rows_deleted"] += 1
        _set_fields(cur, "actresses", kid, p["fills"])
        cur.execute(
            "UPDATE actresses SET work_count = (SELECT COUNT(*) FROM actress_works WHERE actress_id = ?), updated_at = ? WHERE id = ?",
            (kid, now, kid),
        )
    for table, plans, key in (("genres", genre_plans, "genre_rows_deleted"), ("makers", maker_plans, "maker_rows_deleted")):
        for p in plans:
            for lo in p["losers"]:
                cur.execute(f"DELETE FROM {table} WHERE id = ?", (lo["id"],))
                stats[key] += 1
            _set_fields(cur, table, p["keeper"]["id"], p["fills"])
    return stats


def verify(con: sqlite3.Connection) -> list[str]:
    problems = []
    for t in ("actresses", "genres", "makers"):
        if _groups(con, t):
            problems.append(f"{t}: 아직 중복 그룹 남음")
    for t, col in (("actress_works", "actress_id"), ("actress_images", "actress_id"), ("actress_aliases", "actress_id")):
        n = con.execute(f"SELECT COUNT(*) FROM {t} WHERE {col} IS NOT NULL AND {col} NOT IN (SELECT id FROM actresses)").fetchone()[0]
        if n:
            problems.append(f"{t}: 고아 행 {n}건")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="백업 후 실제 적용 (없으면 미리보기만)")
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--overrides", type=Path, default=None,
                    help="장르/메이커에서 남길 한국어 번역 지정 파일 (일본어<TAB>한국어)")
    args = ap.parse_args()
    overrides = load_overrides(args.overrides)
    db = Path(args.db)
    if not db.exists():
        print(f"DB 없음: {db}")
        return 1

    uri = f"file:{db.as_posix()}" + ("" if args.apply else "?mode=ro")
    con = sqlite3.connect(uri, uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    try:
        a, g, m = plan_actresses(con), plan_master(con, "genres", overrides), plan_master(con, "makers", overrides)
        report = render_report(a, g, m)
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        rp = REPORT_DIR / f"width_merge_{'applied' if args.apply else 'preview'}_{dt.datetime.now():%Y%m%d-%H%M%S}.md"
        rp.write_text(report, encoding="utf-8")
        print(report if not args.apply else report.split("\n## ")[0])
        print(f"[보고서] {rp}")
        if not args.apply:
            print("\n미리보기만 했습니다 (DB 변경 없음). 적용하려면 --apply")
            return 0
        if not (a or g or m):
            print("정리할 중복이 없습니다.")
            return 0

        backup(con, db)
        counts_before = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("jav_metadata", "user_preferences", "actress_works")}
        con.execute("BEGIN IMMEDIATE")  # 다른 쓰기와 겹치면 여기서 즉시 실패 → 아무것도 안 바뀜
        try:
            stats = apply(con, a, g, m)
            problems = verify(con)
            counts_after = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("jav_metadata", "user_preferences")}
            for t in ("jav_metadata", "user_preferences"):
                if counts_before[t] != counts_after[t]:
                    problems.append(f"{t} 행 수 변함 {counts_before[t]}→{counts_after[t]}")
            if problems:
                raise RuntimeError("검증 실패: " + "; ".join(problems))
            con.commit()
        except Exception:
            con.rollback()
            print("[롤백] 오류로 모든 변경을 취소했습니다 (DB 는 적용 전 상태).")
            raise
        print("[적용 완료]", ", ".join(f"{k}={v}" for k, v in stats.items()))
        print(f"  actress_works {counts_before['actress_works']} → {con.execute('SELECT COUNT(*) FROM actress_works').fetchone()[0]} (중복 연결 정리)")
        print(f"  jav_metadata / user_preferences 행 수 변화 없음 ({counts_before['jav_metadata']} / {counts_before['user_preferences']})")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())

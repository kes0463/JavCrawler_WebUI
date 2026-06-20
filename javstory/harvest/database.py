from sqlalchemy import (
    Column,
    DateTime,
    Boolean,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.pool import NullPool
from contextlib import contextmanager
import datetime
import shutil
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from javstory.config.app_config import DB_PATH as _CFG_DB_PATH

Base = declarative_base()

# DB 스키마/마이그레이션 가드 버전.
# - SQLite `PRAGMA user_version`에 저장한다.
# - 테이블/컬럼 마이그레이션 로직을 변경하면 이 값을 올려서 1회 재실행되게 한다.
# - v9+ 스키마는 Alembic only — `upgrade_alembic_head()` (init_db 이후 호출)
_APP_DB_SCHEMA_VERSION = 12
_ALEMBIC_HEAD_REVISION = "0001_stamp_v8"
_SCHEMA_USER_VERSION_ALEMBIC = 9

_db_boot_mode: Literal["ok", "read_only"] = "ok"
_last_boot_result: "DbBootResult | None" = None


class DbUpgradeError(Exception):
    """Alembic upgrade failed (strict callers)."""


class DbReadOnlyError(Exception):
    """DB writes blocked after failed migration."""


@dataclass(frozen=True)
class DbBootResult:
    ok: bool
    read_only: bool
    message: str
    backup_path: str | None = None
    recovery_log: str | None = None


def is_db_read_only() -> bool:
    return _db_boot_mode == "read_only"


def get_last_db_boot_result() -> DbBootResult | None:
    return _last_boot_result


def assert_db_writable(context: str = "") -> None:
    if is_db_read_only():
        hint = (_last_boot_result.message if _last_boot_result else "") or "See logs/db_upgrade_recovery.txt"
        raise DbReadOnlyError(
            f"Database is read-only{f' ({context})' if context else ''}. {hint}"
        )

class JAVMetadata(Base):
    """
    JAV 작품의 메타데이터를 저장하는 메인 테이블 (스키마 v9.0)
    언어별(KO, JA, EN, ZH) 제목, 시놉시스, 배우 정보를 관리합니다.
    """
    __tablename__ = 'jav_metadata'
    
    # [1] 핵심 식별 및 인물 정보
    id = Column(Integer, primary_key=True)
    product_code = Column(String(50), unique=True, index=True)
    
    actors_ko = Column(Text, nullable=True)
    actors_ja = Column(Text, nullable=True)
    actors_romaji = Column(Text, nullable=True)
    actors_en = Column(Text, nullable=True)
    actors_zh_cn = Column(Text, nullable=True)
    actors_zh_tw = Column(Text, nullable=True)
    
    # [2] 다국어 제목 정보
    title_ko = Column(Text, nullable=True)
    title_ja = Column(Text, nullable=True)
    title_en = Column(Text, nullable=True)
    title_zh_cn = Column(Text, nullable=True)
    title_zh_tw = Column(Text, nullable=True)
    original_title = Column(String(500), nullable=True)
    
    # [3] 다국어 시놉시스 정보
    synopsis_ko = Column(Text, nullable=True)
    synopsis_ja = Column(Text, nullable=True)
    synopsis_en = Column(Text, nullable=True)
    synopsis_zh_cn = Column(Text, nullable=True)
    synopsis_zh_tw = Column(Text, nullable=True)
    
    # [4] 분류 및 제작 정보
    genres_ko = Column(Text, nullable=True)
    genres_ja = Column(Text, nullable=True)
    genres_en = Column(Text, nullable=True)
    genres_zh_cn = Column(Text, nullable=True)
    genres_zh_tw = Column(Text, nullable=True)
    
    maker_ko = Column(String(200), nullable=True)
    maker_ja = Column(String(200), nullable=True)
    maker_en = Column(String(200), nullable=True)
    maker_zh_cn = Column(String(200), nullable=True)
    maker_zh_tw = Column(String(200), nullable=True)
    
    # [5] 자산 및 상태 정보
    cover_image_url = Column(String(1000), nullable=True)
    cover_image_local_path = Column(String(1000), nullable=True)
    thumb_image_local_path = Column(String(1000), nullable=True)
    release_date = Column(String(100), nullable=True)
    analysis_status = Column(Text, nullable=True)
    is_hardcoded = Column(Boolean, default=False)
    is_mopa = Column(Boolean, default=False)
    folder_path = Column(String(1000), nullable=True)
    
    created_at = Column(DateTime, default=datetime.datetime.now)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)

    # 레거시 호환 필드
    title = Column(String(500), nullable=True)
    synopsis = Column(Text, nullable=True)
    actors = Column(Text, nullable=True)
    genres = Column(Text, nullable=True)
    maker = Column(String(200), nullable=True)

    # v4: 인기도 점수
    favorite_score   = Column(Integer, default=0)
    favorite_sources = Column(Text, nullable=True)  # "123av:634,missav123:102"
    # v5: 좋아요 전용 크롤 실패 시각 — 일정 기간 재시도 스킵용 (`JAVSTORY_FAV_CRAWL_FAIL_COOLDOWN_HOURS`)
    favorite_crawl_failed_at = Column(DateTime, nullable=True)

class Actress(Base):
    """배우 정보 테이블 (actresses)"""
    __tablename__ = 'actresses'
    id = Column(Integer, primary_key=True)
    japanese = Column(String(100), unique=True, index=True)
    korean = Column(String(100), nullable=True)   # None = 아직 미입력
    romaji = Column(String(100), nullable=True)   # None = 아직 미입력
    needs_review = Column(Boolean, default=True)  # True = 수동 확인 대기 중
    # 배우 단위 번역 노트 — 같은 배우의 모든 작품에 공통 적용되는 페르소나/말투/표기 가이드.
    # Gemini 번역 프롬프트의 {{note}}에 작품 노트·전역 노트와 함께 합쳐 주입된다.
    translation_note = Column(Text, nullable=True)

class Genre(Base):
    """장르 정보 테이블 (genres)"""
    __tablename__ = 'genres'
    id = Column(Integer, primary_key=True)
    japanese = Column(String(100), unique=True, index=True)
    korean = Column(String(100), nullable=True)
    english = Column(String(100), nullable=True)
    needs_review = Column(Boolean, default=True)

class Maker(Base):
    """제작사 정보 테이블 (makers)"""
    __tablename__ = 'makers'
    id = Column(Integer, primary_key=True)
    japanese = Column(String(200), unique=True, index=True)
    korean = Column(String(200), nullable=True)
    english = Column(String(200), nullable=True)
    slug = Column(String(200), nullable=True)
    needs_review = Column(Boolean, default=True)


class BackgroundCache(Base):
    """작품 단위 LLM 배경(컨텍스트) 캐시 — meta_hash로 jav_metadata 변경 시 무효화."""
    __tablename__ = "background_cache"

    product_code = Column(String(50), primary_key=True)
    background_json = Column(Text, nullable=False)
    meta_hash = Column(String(64), nullable=False)
    model_id = Column(String(200), nullable=True)
    prompt_version = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.now)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)
    expires_at = Column(DateTime, nullable=True)

class WatchHistory(Base):
    """사용자 시청 이력 및 행동 데이터 (Telemetry)"""
    __tablename__ = "watch_history"
    id = Column(Integer, primary_key=True)
    product_code = Column(String(50), index=True)
    watch_duration = Column(Integer, default=0)  # 누적 시청 시간(초) — 재생 중 업데이트
    total_duration = Column(Integer, default=0)  # 영상 전체 길이(초)
    last_position = Column(Integer, default=0)   # 마지막 시청 위치(ms) — 레거시·최근 세션
    last_positions_json = Column(Text, nullable=True)  # 파트별 위치 {"정규화경로": ms}
    repeat_segments = Column(Text, nullable=True) # 반복 시청 구간 (JSON)
    skip_count = Column(Integer, default=0)       # 스킵 횟수 (앞으로 5초 이상 점프)
    session_count = Column(Integer, default=0)    # 총 재생 세션 수
    is_completed = Column(Boolean, default=False)
    rating = Column(Integer, default=0)           # 사용자 별점 (0~5)
    liked = Column(Boolean, default=False)        # 좋아요 여부
    disliked = Column(Boolean, default=False)     # 싫어요 여부
    watch_later = Column(Boolean, default=False)  # 나중에 볼 큐 포함 여부
    watch_later_added_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.now)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)

class FavoriteScoreHistory(Base):
    """사이트 좋아요(♥) 점수 스냅샷 — 기간 증감(Δ) 계산용."""

    __tablename__ = "favorite_score_history"
    id = Column(Integer, primary_key=True, autoincrement=True)
    product_code = Column(String(50), nullable=False, index=True)
    observed_at = Column(DateTime, nullable=False, index=True)
    total_score = Column(Integer, nullable=False)
    sources = Column(Text, nullable=True)


class UserPreference(Base):
    """배우, 장르별 선호도 가중치 점수 (시간대 분리 지원)"""
    __tablename__ = "user_preferences"
    id = Column(Integer, primary_key=True)
    category_type = Column(String(20), index=True)  # 'actor', 'genre', 'maker'
    category_value = Column(String(100), index=True)
    score = Column(Integer, default=0)              # 통합 선호도 점수
    recent_score = Column(Integer, default=0)       # 최근 7일 가중 점수
    time_slot = Column(String(20), default='all')   # 'morning','afternoon','night','all'
    last_watched_at = Column(DateTime, default=datetime.datetime.now)


class FileFlagCache(Base):
    """작품 파일 상태 캐시 — 앱 시작 시 HDD I/O 없이 라이브러리 목록 렌더링용."""

    __tablename__ = "file_flag_cache"

    product_code  = Column(String(50), primary_key=True)
    has_video     = Column(Integer, nullable=False, default=0)
    video_path    = Column(Text, nullable=True)
    lamp_stt      = Column(Integer, nullable=False, default=0)
    lamp_sub      = Column(Integer, nullable=False, default=0)
    has_canonical = Column(Integer, nullable=False, default=0)
    has_story     = Column(Integer, nullable=False, default=0)
    scanned_at    = Column(Text, nullable=True)


class Product(Base):
    """품번 단위 식별·폴더 바인딩 (jav_metadata 1:1, DB v2 P2)."""

    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    sku = Column(String(50), unique=True, nullable=False, index=True)
    jav_metadata_id = Column(Integer, ForeignKey("jav_metadata.id"), unique=True, nullable=True)
    folder_path = Column(String(1000), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.now)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)

    jav_metadata = relationship("JAVMetadata", backref="product", uselist=False)
    video_files = relationship("VideoFile", back_populates="product", cascade="all, delete-orphan")


class VideoFile(Base):
    """품번당 로컬 영상 파트 (folder_path 기준 상대 경로)."""

    __tablename__ = "video_files"
    __table_args__ = (
        UniqueConstraint("product_id", "part_order", name="uq_video_files_product_order"),
        UniqueConstraint("product_id", "video_relpath", name="uq_video_files_product_relpath"),
    )

    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    part_order = Column(Integer, nullable=False, default=0)
    video_relpath = Column(Text, nullable=False)
    duration_sec = Column(Float, nullable=True)
    file_size = Column(Integer, nullable=True)
    fingerprint = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.now)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)

    product = relationship("Product", back_populates="video_files")


# DB 연결 및 세션 관리 — `data/db/jav_database.db`
_DB = Path(_CFG_DB_PATH).resolve()
_DB.parent.mkdir(parents=True, exist_ok=True)
DB_PATH = str(_DB)

# SQLite 동시성 튜닝:
# - WAL: read/write 동시성 개선
# - timeout: write lock 대기(기본 5s는 동시 Harvest에서 부족할 수 있음)
# - NullPool: 워커/스레드 환경에서 커넥션 재사용으로 인한 잠금 잔류를 줄임
# - check_same_thread: 다중 스레드(Worker) 사용 시 안정성
engine = create_engine(
    f"sqlite:///{_DB.as_posix()}",
    connect_args={"check_same_thread": False, "timeout": 60},
    poolclass=NullPool,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@event.listens_for(engine, "connect")
def _sqlite_on_connect(dbapi_connection, connection_record):  # type: ignore[no-redef]
    try:
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA synchronous=NORMAL;")
        cur.execute("PRAGMA temp_store=MEMORY;")
        # write lock 대기(밀리초). connect_args.timeout과 별개로 PRAGMA도 명시해 둔다.
        cur.execute("PRAGMA busy_timeout=60000;")
        # WAL에서 체크포인트 과도 누적 방지(기본값도 있지만 명시)
        cur.execute("PRAGMA wal_autocheckpoint=1000;")
        cur.close()
    except Exception:
        pass

def get_db_session():
    return SessionLocal()

@contextmanager
def get_db_session_ctx():
    """
    세션 컨텍스트 매니저.
    - 예외 시 rollback
    - 항상 close
    - commit은 호출자가 명시적으로 하거나, 컨텍스트에서 직접 호출할 수 있음
    """
    session = SessionLocal()
    try:
        yield session
    except Exception:
        try:
            session.rollback()
        except Exception:
            pass
        raise
    finally:
        session.close()


def fav_crawl_cooldown_hours() -> float:
    """좋아요 전용 크롤 재시도 간격(시간). `JAVSTORY_FAV_CRAWL_FAIL_COOLDOWN_HOURS`, 0=쿨다운 비활성."""
    import os

    raw = (os.environ.get("JAVSTORY_FAV_CRAWL_FAIL_COOLDOWN_HOURS", "24") or "").strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 24.0


def favorite_crawl_failure_cutoff() -> datetime.datetime | None:
    """
    SQL 필터 기준 시각: 이 시각 **이전**에 실패 기록된 행만 재시도 대상.
    None이면 쿨다운 비활성(favorite_crawl_failed_at 조건 없음).
    """
    h = fav_crawl_cooldown_hours()
    if h <= 0:
        return None
    return datetime.datetime.now() - datetime.timedelta(hours=h)


def record_favorite_crawl_failed(product_code: str) -> None:
    """좋아요 전용 크롤이 실패한 시각을 기록한다."""
    pc = (product_code or "").strip().upper()
    if not pc:
        return
    try:
        with get_db_session_ctx() as session:
            row = session.query(JAVMetadata).filter_by(product_code=pc).first()
            if row:
                row.favorite_crawl_failed_at = datetime.datetime.now()
                session.commit()
    except Exception:
        pass


def record_favorite_score_snapshot(product_code: str, total_score: int, sources: str | None = None) -> None:
    """좋아요 전용 크롤 등 성공 시 스냅샷 한 건 추가."""
    pc = (product_code or "").strip().upper()
    if not pc:
        return
    try:
        ts = int(total_score)
    except Exception:
        return
    try:
        with get_db_session_ctx() as session:
            session.add(
                FavoriteScoreHistory(
                    product_code=pc,
                    observed_at=datetime.datetime.now(),
                    total_score=max(0, ts),
                    sources=(s if (s := (sources or "").strip()) else None),
                )
            )
            session.commit()
    except Exception:
        pass


def favorite_score_deltas_for_period(
    *,
    meta_scores_by_code: dict[str, int],
    period_days: int,
    now: datetime.datetime | None = None,
) -> dict[str, int | None]:
    """
    jav_metadata 행별 product_code 기준 Δ.
    Δ = (기간 종료 시점 근처 점수) − (기간 시작 시점 이전 또는 첫 진입값).
    해당 품번에 스냅샷이 한 건도 없으면 None.
    meta_scores_by_code: product_code.upper() → 현재 favorite_score (종료값 폴백).
    """
    if period_days <= 0 or not meta_scores_by_code:
        return {}

    now = now or datetime.datetime.now()
    t_end = now
    t_start = now - datetime.timedelta(days=int(period_days))

    pcs = sorted({str(k or "").strip().upper() for k in meta_scores_by_code.keys() if str(k or "").strip()})

    snapshots: dict[str, list[tuple[datetime.datetime, int]]] = {p: [] for p in pcs}
    try:
        with get_db_session_ctx() as session:
            rows = (
                session.query(FavoriteScoreHistory)
                .filter(FavoriteScoreHistory.product_code.in_(pcs))
                .order_by(FavoriteScoreHistory.product_code, FavoriteScoreHistory.observed_at)
                .all()
            )
        for r in rows:
            pc = (r.product_code or "").strip().upper()
            if pc not in snapshots:
                snapshots[pc] = []
            if r.observed_at is None:
                continue
            snapshots[pc].append((r.observed_at, int(r.total_score or 0)))
    except Exception:
        return {p: None for p in pcs}

    out: dict[str, int | None] = {}
    for pc in pcs:
        rows_pc = snapshots.get(pc) or []
        if not rows_pc:
            out[pc] = None
            continue
        fb_end = int(meta_scores_by_code.get(pc, 0) or 0)

        def _score_at_or_before(t: datetime.datetime) -> int | None:
            v: int | None = None
            for dt, sc in rows_pc:
                if dt <= t:
                    v = sc
                else:
                    continue
            return v

        def _first_strictly_after(t: datetime.datetime) -> int | None:
            for dt, sc in rows_pc:
                if dt > t:
                    return sc
            return None

        start_val = _score_at_or_before(t_start)
        if start_val is None:
            start_val = _first_strictly_after(t_start)
        if start_val is None:
            start_val = 0

        end_val = _score_at_or_before(t_end)
        if end_val is None:
            end_val = fb_end

        out[pc] = int(end_val) - int(start_val)
    return out


def favorite_score_delta_one(
    product_code: str,
    period_days: int,
    *,
    fallback_score: int,
    now: datetime.datetime | None = None,
) -> int | None:
    """단일 품번에 대한 기간 ♥ 증감. 스냅샷 없으면 None."""
    pc = (product_code or "").strip().upper()
    if not pc or period_days <= 0:
        return None
    return favorite_score_deltas_for_period(
        meta_scores_by_code={pc: int(fallback_score or 0)},
        period_days=int(period_days),
        now=now,
    ).get(pc)


def clear_favorite_crawl_failed(product_code: str) -> None:
    """수집 성공(점수 갱신 또는 0점 확정) 시 실패 기록을 지운다."""
    pc = (product_code or "").strip().upper()
    if not pc:
        return
    try:
        with get_db_session_ctx() as session:
            row = session.query(JAVMetadata).filter_by(product_code=pc).first()
            if row and getattr(row, "favorite_crawl_failed_at", None) is not None:
                row.favorite_crawl_failed_at = None
                session.commit()
    except Exception:
        pass


def init_db():
    """테이블 생성 및 기존 DB 컬럼 자동 마이그레이션"""
    _DB.parent.mkdir(parents=True, exist_ok=True)
    import sqlite3

    print(f"[DB] Using database at: {DB_PATH}")

    # 이미 마이그레이션이 적용된 DB면 앱 시작 시점에서 불필요한 PRAGMA/ALTER를 피한다.
    try:
        if Path(DB_PATH).is_file() and Path(DB_PATH).stat().st_size > 0:
            with sqlite3.connect(DB_PATH) as conn:
                cur = conn.cursor()
                cur.execute("PRAGMA user_version;")
                row = cur.fetchone()
                user_ver = int(row[0] if row and row[0] is not None else 0)
                cur.close()
            if user_ver >= _APP_DB_SCHEMA_VERSION:
                return
    except Exception:
        # 가드 확인 실패 시에는 안전하게 초기화 경로로 진행
        pass

    print("[DB] Initializing tables (create_all)...")
    # v9+ (`products`, `video_files`)는 Alembic만 생성 — P2 중복 CREATE 방지
    _v8_tables = [
        JAVMetadata.__table__,
        Actress.__table__,
        Genre.__table__,
        Maker.__table__,
        BackgroundCache.__table__,
        WatchHistory.__table__,
        FavoriteScoreHistory.__table__,
        UserPreference.__table__,
        FileFlagCache.__table__,
    ]
    Base.metadata.create_all(bind=engine, tables=_v8_tables)
    print("[DB] Running migration checks...")
    _migrate_add_needs_review_columns()
    _migrate_v3_analytics_columns()
    _migrate_v4_favorite_columns()
    _migrate_v5_favorite_crawl_failed_at()
    _migrate_v6_actress_translation_note()
    _migrate_v7_favorite_score_history()
    _migrate_v8_watch_history_part_positions()
    _migrate_v11_watch_later_columns()
    _migrate_v12_file_flag_cache()
    _ensure_indexes_and_optimize()
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(f"PRAGMA user_version={_APP_DB_SCHEMA_VERSION};")
            conn.commit()
    except Exception:
        pass
    print("[DB] Database initialization complete.")


def get_schema_user_version() -> int:
    """SQLite PRAGMA user_version (0 if DB missing)."""
    import sqlite3

    p = Path(DB_PATH)
    if not p.is_file() or p.stat().st_size == 0:
        return 0
    try:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute("PRAGMA user_version").fetchone()
            return int(row[0] if row and row[0] is not None else 0)
    except Exception:
        return 0


def _alembic_revision_label() -> str:
    import sqlite3

    p = Path(DB_PATH)
    if not p.is_file():
        return "unknown"
    try:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
            if row and row[0]:
                return str(row[0])
    except Exception:
        pass
    return "unknown"


def _backup_database(reason: str) -> Path | None:
    src = Path(DB_PATH)
    if not src.is_file() or src.stat().st_size == 0:
        return None
    dest_dir = src.parent / "backups"
    dest_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = dest_dir / f"jav_database_{reason}_{ts}.db"
    shutil.copy2(src, dest)
    return dest


def _write_db_recovery_artifact(exc: BaseException, backup: Path | None) -> Path:
    logs_dir = _ROOT / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    path = logs_dir / "db_upgrade_recovery.txt"
    backup_line = str(backup) if backup else "(no backup — DB file missing)"
    body = f"""JAVSTORY database migration failed
================================

The app started in READ-ONLY mode so your existing data is not corrupted further.

Automatic backup:
  {backup_line}

Recovery steps:
  1. Close JAVSTORY completely.
  2. Copy the backup file over the active DB if you need to roll back:
       {DB_PATH}
  3. Ensure Alembic is installed in the app venv:
       pip install -r requirements.txt
  4. From the project root, try:
       python -c "from javstory.harvest.database import init_db, upgrade_alembic_head; init_db(); upgrade_alembic_head(strict=True)"
  5. If migration still fails, keep the backup and report the traceback below.

Manual hydrate (after migration succeeds):
  python tools/hydrate_products_v2.py

Traceback:
{traceback.format_exc()}
"""
    path.write_text(body, encoding="utf-8")
    return path


def _handle_upgrade_failure(exc: BaseException) -> DbBootResult:
    global _db_boot_mode, _last_boot_result

    backup = _backup_database("pre_upgrade_failed")
    recovery = _write_db_recovery_artifact(exc, backup)
    _db_boot_mode = "read_only"

    try:
        from javstory.utils.structured_log import log_event

        log_event(
            "ERROR",
            "boot_db_upgrade_failed",
            str(exc),
            db_path=DB_PATH,
            backup_path=str(backup) if backup else None,
            recovery_log=str(recovery),
            traceback=traceback.format_exc(),
        )
    except Exception:
        pass

    msg = (
        "DB migration (Alembic) failed. The app will open in read-only mode.\n\n"
        f"Backup: {backup or 'n/a'}\n"
        f"Details: {recovery}\n\n"
        "Close the app, fix the migration (see recovery file), then restart."
    )
    result = DbBootResult(
        ok=False,
        read_only=True,
        message=msg,
        backup_path=str(backup) if backup else None,
        recovery_log=str(recovery),
    )
    _last_boot_result = result
    print(f"[DB] Alembic upgrade failed — read-only mode. Recovery: {recovery}")
    return result


def upgrade_alembic_head(*, strict: bool = False) -> bool:
    """
    init_db() 이후 호출 — v9+ Alembic revision 적용.
    Returns True on success. On failure: backup + recovery log; raises if strict=True.
    """
    ini_path = _ROOT / "alembic.ini"
    if not ini_path.is_file():
        print("[DB] alembic.ini not found — skipping Alembic upgrade")
        return True
    try:
        from alembic import command
        from alembic.config import Config

        cfg = Config(str(ini_path))
        command.upgrade(cfg, "head")
        rev = _alembic_revision_label()
        print(f"[DB] Alembic upgrade head ({rev}) complete.")
        return True
    except Exception as e:
        print(f"[DB] Alembic upgrade failed: {e}")
        _handle_upgrade_failure(e)
        if strict:
            raise DbUpgradeError(str(e)) from e
        return False


def init_and_upgrade_db() -> DbBootResult:
    """레거시 v0–v8 초기화 후 Alembic head 적용. 실패 시 읽기 전용.

    P2 hydrate(maybe_hydrate_products_v2)는 UI 블로킹 방지를 위해
    호출 측에서 백그라운드 스레드로 별도 실행한다.
    """
    global _db_boot_mode, _last_boot_result

    _db_boot_mode = "ok"
    init_db()
    if not upgrade_alembic_head():
        return _last_boot_result or DbBootResult(
            ok=False,
            read_only=True,
            message="DB migration failed.",
        )
    if is_db_read_only():
        return _last_boot_result or DbBootResult(ok=False, read_only=True, message="read-only")

    result = DbBootResult(ok=True, read_only=False, message="")
    _last_boot_result = result
    return result


def _migrate_add_needs_review_columns():
    """기존 DB에 needs_review 컬럼이 없으면 자동으로 추가 (ALTER TABLE)"""
    import sqlite3
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            for table in ("actresses", "genres", "makers"):
                cols = [row[1] for row in cursor.execute(f"PRAGMA table_info({table})")]
                if "needs_review" not in cols:
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN needs_review INTEGER DEFAULT 1")
                    print(f"[DB Migration] {table}.needs_review 컬럼 추가 완료")
            
            # jav_metadata.is_hardcoded 컬럼 추가
            cols_meta = [row[1] for row in cursor.execute("PRAGMA table_info(jav_metadata)")]
            if "is_hardcoded" not in cols_meta:
                cursor.execute("ALTER TABLE jav_metadata ADD COLUMN is_hardcoded INTEGER DEFAULT 0")
                print("[DB Migration] jav_metadata.is_hardcoded 컬럼 추가 완료")

            # jav_metadata.is_mopa 컬럼 추가
            cols_meta = [row[1] for row in cursor.execute("PRAGMA table_info(jav_metadata)")]
            if "is_mopa" not in cols_meta:
                cursor.execute("ALTER TABLE jav_metadata ADD COLUMN is_mopa INTEGER DEFAULT 0")
                print("[DB Migration] jav_metadata.is_mopa 컬럼 추가 완료")
                
            # jav_metadata.folder_path 컬럼 추가
            if "folder_path" not in cols_meta:
                cursor.execute("ALTER TABLE jav_metadata ADD COLUMN folder_path TEXT")
                print("[DB Migration] jav_metadata.folder_path 컬럼 추가 완료")

            cols_meta = [row[1] for row in cursor.execute("PRAGMA table_info(jav_metadata)")]
            if "actors_en" not in cols_meta:
                cursor.execute("ALTER TABLE jav_metadata ADD COLUMN actors_en TEXT")
                print("[DB Migration] jav_metadata.actors_en 컬럼 추가 완료")

            conn.commit()
    except Exception as e:
        print(f"[DB Migration] 마이그레이션 실패: {e}")


def _migrate_v3_analytics_columns():
    """v3: WatchHistory·UserPreference 취향 분석 컬럼 추가"""
    import sqlite3
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()

            # WatchHistory 신규 컬럼
            wh_cols = [row[1] for row in cursor.execute("PRAGMA table_info(watch_history)")]
            wh_migrations = [
                ("skip_count",    "ALTER TABLE watch_history ADD COLUMN skip_count INTEGER DEFAULT 0"),
                ("session_count", "ALTER TABLE watch_history ADD COLUMN session_count INTEGER DEFAULT 0"),
                ("liked",         "ALTER TABLE watch_history ADD COLUMN liked INTEGER DEFAULT 0"),
                ("disliked",      "ALTER TABLE watch_history ADD COLUMN disliked INTEGER DEFAULT 0"),
            ]
            for col, stmt in wh_migrations:
                if col not in wh_cols:
                    cursor.execute(stmt)
                    print(f"[DB Migration v3] watch_history.{col} 컬럼 추가 완료")

            # UserPreference 신규 컬럼
            up_cols = [row[1] for row in cursor.execute("PRAGMA table_info(user_preferences)")]
            up_migrations = [
                ("recent_score", "ALTER TABLE user_preferences ADD COLUMN recent_score INTEGER DEFAULT 0"),
                ("time_slot",    "ALTER TABLE user_preferences ADD COLUMN time_slot TEXT DEFAULT 'all'"),
            ]
            for col, stmt in up_migrations:
                if col not in up_cols:
                    cursor.execute(stmt)
                    print(f"[DB Migration v3] user_preferences.{col} 컬럼 추가 완료")

            conn.commit()
    except Exception as e:
        print(f"[DB Migration v3] 실패: {e}")


def _migrate_v4_favorite_columns():
    """v4: jav_metadata.favorite_score / favorite_sources 컬럼 추가"""
    import sqlite3
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cols = [row[1] for row in cursor.execute("PRAGMA table_info(jav_metadata)")]
            for col, typedef in [
                ("favorite_score",   "INTEGER DEFAULT 0"),
                ("favorite_sources", "TEXT"),
            ]:
                if col not in cols:
                    cursor.execute(f"ALTER TABLE jav_metadata ADD COLUMN {col} {typedef}")
                    print(f"[DB Migration v4] jav_metadata.{col} 컬럼 추가 완료")
            conn.commit()
    except Exception as e:
        print(f"[DB Migration v4] 실패: {e}")


def _migrate_v5_favorite_crawl_failed_at():
    """v5: jav_metadata.favorite_crawl_failed_at — 좋아요 크롤 실패 후 쿨다운 기록"""
    import sqlite3
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cols = [row[1] for row in cursor.execute("PRAGMA table_info(jav_metadata)")]
            if "favorite_crawl_failed_at" not in cols:
                cursor.execute(
                    "ALTER TABLE jav_metadata ADD COLUMN favorite_crawl_failed_at DATETIME"
                )
                print("[DB Migration v5] jav_metadata.favorite_crawl_failed_at 컬럼 추가 완료")
            conn.commit()
    except Exception as e:
        print(f"[DB Migration v5] 실패: {e}")


def _migrate_v7_favorite_score_history():
    """v7: favorite_score_history — 사이트 ♥ 스냅샷 시계열"""
    import sqlite3

    try:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS favorite_score_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                    product_code VARCHAR(50) NOT NULL,
                    observed_at DATETIME NOT NULL,
                    total_score INTEGER NOT NULL,
                    sources TEXT
                )
                """
            )
            conn.commit()
            print("[DB Migration v7] favorite_score_history 준비 완료")
    except Exception as e:
        print(f"[DB Migration v7] 실패: {e}")


def _migrate_v8_watch_history_part_positions():
    """v8: watch_history.last_positions_json — 파트(파일)별 이어보기 위치"""
    import sqlite3

    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cols = [row[1] for row in cursor.execute("PRAGMA table_info(watch_history)")]
            if "last_positions_json" not in cols:
                cursor.execute(
                    "ALTER TABLE watch_history ADD COLUMN last_positions_json TEXT"
                )
                print("[DB Migration v8] watch_history.last_positions_json 컬럼 추가 완료")
            conn.commit()
    except Exception as e:
        print(f"[DB Migration v8] 실패: {e}")


def _migrate_v11_watch_later_columns():
    """v11: watch_history에 나중에 볼 큐 상태 추가."""
    import sqlite3

    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cols = [row[1] for row in cursor.execute("PRAGMA table_info(watch_history)")]
            migrations = [
                ("watch_later", "ALTER TABLE watch_history ADD COLUMN watch_later INTEGER DEFAULT 0"),
                ("watch_later_added_at", "ALTER TABLE watch_history ADD COLUMN watch_later_added_at DATETIME"),
            ]
            for col, stmt in migrations:
                if col not in cols:
                    cursor.execute(stmt)
                    print(f"[DB Migration v11] watch_history.{col} 컬럼 추가 완료")
            conn.commit()
    except Exception as e:
        print(f"[DB Migration v11] 실패: {e}")


def _migrate_v12_file_flag_cache():
    """v12: file_flag_cache 테이블 생성 — 라이브러리 목록 로딩 시 HDD I/O 제거용."""
    import sqlite3

    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS file_flag_cache (
                    product_code  TEXT PRIMARY KEY,
                    has_video     INTEGER NOT NULL DEFAULT 0,
                    video_path    TEXT,
                    lamp_stt      INTEGER NOT NULL DEFAULT 0,
                    lamp_sub      INTEGER NOT NULL DEFAULT 0,
                    has_canonical INTEGER NOT NULL DEFAULT 0,
                    has_story     INTEGER NOT NULL DEFAULT 0,
                    scanned_at    TEXT
                )
                """
            )
            conn.commit()
            print("[DB Migration v12] file_flag_cache 테이블 생성 완료")
    except Exception as e:
        print(f"[DB Migration v12] 실패: {e}")


def _migrate_v6_actress_translation_note():
    """v6: actresses.translation_note — 배우 단위 번역 노트(페르소나/말투/표기 가이드)"""
    import sqlite3
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cols = [row[1] for row in cursor.execute("PRAGMA table_info(actresses)")]
            if "translation_note" not in cols:
                cursor.execute("ALTER TABLE actresses ADD COLUMN translation_note TEXT")
                print("[DB Migration v6] actresses.translation_note 컬럼 추가 완료")
            conn.commit()
    except Exception as e:
        print(f"[DB Migration v6] 실패: {e}")


def _ensure_indexes_and_optimize() -> None:
    """
    조회 핫패스용 인덱스/옵션을 보장한다.
    - 이미 있으면 NO-OP (IF NOT EXISTS)
    - SQLite는 가벼운 인덱스 추가만으로도 목록/대기큐/정렬 성능이 크게 개선된다.
    """
    import sqlite3

    stmts = [
        # 라이브러리 목록 정렬(최신 갱신순)
        "CREATE INDEX IF NOT EXISTS idx_jav_metadata_updated_at ON jav_metadata(updated_at);",
        # 대시보드 pending 큐
        "CREATE INDEX IF NOT EXISTS idx_jav_metadata_analysis_status ON jav_metadata(analysis_status);",
        # 날짜 정렬
        "CREATE INDEX IF NOT EXISTS idx_jav_metadata_release_date ON jav_metadata(release_date);",
        # 폴더 바인딩 조회/필터
        "CREATE INDEX IF NOT EXISTS idx_jav_metadata_folder_path ON jav_metadata(folder_path);",
        # 인기도 정렬
        "CREATE INDEX IF NOT EXISTS idx_jav_favorite_score ON jav_metadata(favorite_score);",
        "CREATE INDEX IF NOT EXISTS idx_fav_hist_pc_time ON favorite_score_history(product_code, observed_at);",
        "CREATE INDEX IF NOT EXISTS idx_watch_history_watch_later ON watch_history(watch_later, watch_later_added_at);",
    ]
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            for s in stmts:
                try:
                    cur.execute(s)
                except Exception:
                    pass
            try:
                cur.execute("PRAGMA optimize;")
            except Exception:
                pass
            cur.close()
            conn.commit()
    except Exception:
        return

def upsert_jav_metadata(session, product_code, merge_empty_only=False, **kwargs):
    """기록이 있으면 업데이트, 없으면 삽입"""
    row = session.query(JAVMetadata).filter_by(product_code=product_code).one_or_none()
    
    if not row:
        row = JAVMetadata(product_code=product_code)
        session.add(row)
    
    def _script_counts(s: str) -> dict[str, int]:
        txt = (s or "").strip()
        return {
            "hangul": sum(1 for ch in txt if 0xAC00 <= ord(ch) <= 0xD7A3),
            "hiragana": sum(1 for ch in txt if 0x3040 <= ord(ch) <= 0x309F),
            "katakana": sum(1 for ch in txt if 0x30A0 <= ord(ch) <= 0x30FF),
            "cjk": sum(1 for ch in txt if 0x4E00 <= ord(ch) <= 0x9FFF),
        }

    def _looks_like_ko(s: str, min_hangul: int = 1) -> bool:
        return _script_counts(s).get("hangul", 0) >= int(min_hangul)

    def _looks_like_ja(s: str) -> bool:
        c = _script_counts(s)
        return (c["hiragana"] + c["katakana"]) > 0
    
    for key, value in kwargs.items():
        if hasattr(row, key):
            if merge_empty_only:
                # favorite 필드는 항상 최신값으로 덮어씀 (비어있음 여부 무관)
                if key in {"favorite_score", "favorite_sources"}:
                    setattr(row, key, value)
                    continue
                existing_val = getattr(row, key)
                empty_like = (not existing_val) or (isinstance(existing_val, str) and not existing_val.strip())

                # [언어 정합성] KO 필드가 채워져 있어도 한국어가 아니면(일본어/무한글) 덮어쓴다.
                if (not empty_like) and key in {"title_ko", "synopsis_ko", "actors_ko", "maker_ko", "genres_ko"}:
                    ex = str(existing_val or "")
                    newv = str(value or "")
                    ex_bad_lang = (not _looks_like_ko(ex, 1)) and (_looks_like_ja(ex) or _script_counts(ex)["hangul"] == 0)
                    new_good_lang = _looks_like_ko(newv, 1)
                    if ex_bad_lang and new_good_lang:
                        empty_like = True

                if empty_like:
                    setattr(row, key, value)
            else:
                setattr(row, key, value)
            
    # 레거시 필드 자동 동기화
    if 'title_ko' in kwargs:
        if not (merge_empty_only and row.title and row.title.strip()):
            row.title = kwargs['title_ko']
    if 'synopsis_ko' in kwargs:
        if not (merge_empty_only and row.synopsis and row.synopsis.strip()):
            row.synopsis = kwargs['synopsis_ko']
    if 'actors_ja' in kwargs:
        if not (merge_empty_only and row.actors and row.actors.strip()):
            row.actors = kwargs['actors_ja']
        
    # 트랜잭션 경계는 호출자가 책임진다. (여기서는 PK 할당 등 필요 시 flush만)
    session.flush()
    return row

def is_metadata_complete(product_code: str) -> bool:
    """핵심 4종 세트(품번, KO제목, 시놉시스, 장르)가 모두 존재하면 True 반환"""
    session = get_db_session()
    try:
        row = session.query(JAVMetadata).filter_by(product_code=product_code.upper()).first()
        if not row: return False
        
        # 품번은 이미 테이블에 있으므로, 나머지 3종 체크
        # title_ko, synopsis_ko, genres_ko가 모두 비어 있지 않은지 확인
        checks = [
            row.title_ko and row.title_ko.strip(),
            row.synopsis_ko and row.synopsis_ko.strip(),
            (row.genres_ko and row.genres_ko.strip()) or (row.genres and row.genres.strip())
        ]
        return all(checks)
    except Exception:
        return False
    finally:
        session.close()

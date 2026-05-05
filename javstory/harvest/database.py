from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from contextlib import contextmanager
import datetime
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from javstory.config.app_config import DB_PATH as _CFG_DB_PATH

Base = declarative_base()

# DB 스키마/마이그레이션 가드 버전.
# - SQLite `PRAGMA user_version`에 저장한다.
# - 테이블/컬럼 마이그레이션 로직을 변경하면 이 값을 올려서 1회 재실행되게 한다.
_APP_DB_SCHEMA_VERSION = 6

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
    last_position = Column(Integer, default=0)   # 마지막 시청 위치(ms)
    repeat_segments = Column(Text, nullable=True) # 반복 시청 구간 (JSON)
    skip_count = Column(Integer, default=0)       # 스킵 횟수 (앞으로 5초 이상 점프)
    session_count = Column(Integer, default=0)    # 총 재생 세션 수
    is_completed = Column(Boolean, default=False)
    rating = Column(Integer, default=0)           # 사용자 별점 (0~5)
    liked = Column(Boolean, default=False)        # 좋아요 여부
    disliked = Column(Boolean, default=False)     # 싫어요 여부
    created_at = Column(DateTime, default=datetime.datetime.now)
    updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)

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
    Base.metadata.create_all(bind=engine)
    print("[DB] Running migration checks...")
    _migrate_add_needs_review_columns()
    _migrate_v3_analytics_columns()
    _migrate_v4_favorite_columns()
    _migrate_v5_favorite_crawl_failed_at()
    _migrate_v6_actress_translation_note()
    _ensure_indexes_and_optimize()
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(f"PRAGMA user_version={_APP_DB_SCHEMA_VERSION};")
            conn.commit()
    except Exception:
        pass
    print("[DB] Database initialization complete.")

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

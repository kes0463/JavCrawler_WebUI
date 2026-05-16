# Alembic 도입 마일스톤

**상태**: P1·P2 완료 (`0001_stamp_v8`, `0002_add_products_video_files`, `product_repository`)  
**DB v2 설계**: [DB_V2_DESIGN.md](DB_V2_DESIGN.md)  
**데이터 SoT**: [DATA_SOT_LAYERS.md](DATA_SOT_LAYERS.md)

현재 [`javstory/harvest/database.py`](../javstory/harvest/database.py)는 `PRAGMA user_version`과 `_migrate_v1` … `_migrate_v8`(실질 v3–v8 + 초기 마이그레이션)로 스키마를 관리합니다.

---

## 1. 범위

| 항목 | 정책 |
|------|------|
| **유지** | `user_version` ≤ 8 인 DB는 기존 `_migrate_*` 체인으로만 업그레이드 (**동결**) |
| **신규** | `user_version` ≥ 9 컬럼·테이블 변경은 **Alembic revision만** |
| **금지** | 기존 사용자 DB destructive reset / `DROP jav_metadata` |
| **방향** | forward-only migration |

---

## 2. 버전 경계

| SQLite `user_version` | 관리 주체 | 비고 |
|----------------------|-----------|------|
| 0–8 | `database.py` — `init_db()`, `_migrate_*`, `_ensure_indexes_and_optimize` | 코드 변경 시 버전 상향 **금지** (동결) |
| 9 | Alembic `0001_stamp_v8` | 스키마 변경 없음, stamp만 |
| 10+ | Alembic `0002_*` … | 예: `products`, `video_files` ([DB_V2_DESIGN.md](DB_V2_DESIGN.md) P2) |

### 2.1 `init_db()`와의 관계

`user_version >= 8`이면 `init_db()`는 **즉시 return**한다.  
→ v9+ 객체는 **`alembic upgrade head` 없이는 기존 DB에 생성되지 않음**.

**권장 부트 순서 (구현 시)**:

```text
1. init_db()           # v0–v8까지 (신규 DB만)
2. alembic upgrade head   # v9+
3. 앱 로직 시작
```

---

## 3. 착수 전제

- [x] [DATA_SOT_LAYERS.md](DATA_SOT_LAYERS.md) — L2/L4 역할 합의
- [x] [DB_V2_DESIGN.md](DB_V2_DESIGN.md) — 2차 `products`/`video_files`, 씬 L4 SoT
- [x] `alembic.ini` + `javstory/harvest/migrations/` 초기 revision `0001_stamp_v8`
- [x] P1 DoD: `tests/unit/test_alembic_stamp.py` — 빈 DB·v8 DB upgrade 후 v8 테이블 유지, `user_version` 9

---

## 4. 디렉터리 구조 (가칭)

```text
alembic.ini                          # script_location, sqlalchemy.url → DB_PATH
javstory/harvest/migrations/
  env.py                             # engine from app_config.DB_PATH
  script.py.mako
  versions/
    0001_stamp_v8.py                 # user_version 8 → 9, DDL 없음 또는 no-op
    0002_add_products_video_files.py # P2
```

**`env.py` 요구**:

- `target_metadata = Base.metadata` (`database.py`와 동일 Base)
- 오프라인/온라인 모드 지원
- Windows 경로: `sqlite:///` + `Path.as_posix()`

---

## 5. Revision `0001_stamp_v8` — v8 동등성

### 5.1 목적

- Alembic `alembic_version` 테이블 도입
- `PRAGMA user_version = 9` 설정 (또는 revision 메타만 9, user_version 병행 — **구현 시 하나로 통일**)

### 5.2 v8 스냅샷 체크리스트 (수동·스크립트)

**테이블 존재** (8개):

- [ ] `jav_metadata`
- [ ] `actresses`, `genres`, `makers`
- [ ] `background_cache`
- [ ] `watch_history`
- [ ] `favorite_score_history`
- [ ] `user_preferences`

**`jav_metadata` 필수 컬럼** (발췌 — 전체는 [DB_V2_DESIGN.md §2.3](DB_V2_DESIGN.md)):

- [ ] `product_code`, `folder_path`, `favorite_score`, `favorite_sources`, `favorite_crawl_failed_at`
- [ ] `is_hardcoded`, `is_mopa`
- [ ] 다국어 `title_*`, `synopsis_*`, `actors_*`, `genres_*`, `maker_*`

**`watch_history` v8**:

- [ ] `last_positions_json`

**인덱스**:

- [ ] `idx_jav_metadata_updated_at`, `analysis_status`, `release_date`, `folder_path`, `favorite_score`
- [ ] `idx_fav_hist_pc_time`

**자동 diff 스크립트**: P1 구현 시 `tools/db_snapshot_v8.py` (후속) — 본 마일스톤에서는 **수동 체크리스트로 대체**.

---

## 6. P2 revision `0002_add_products_video_files` (예정)

[DB_V2_DESIGN.md §4](DB_V2_DESIGN.md) DDL 참고.

- `CREATE TABLE products ...`
- `CREATE TABLE video_files ...`
- **데이터**: 별도 hydrate 스크립트 `tools/hydrate_products_v2.py` (후속) — revision은 스키마만

---

## 7. 운영 절차

### 7.1 개발자 로컬

```bat
copy data\db\jav_database.db data\db\jav_database.db.bak
venv\Scripts\activate
alembic upgrade head
```

### 7.2 실패 시

- `.bak`으로 복원
- `alembic downgrade -1` (down revision 작성된 경우만)

### 7.3 앱 배포

- 설치/업데이트 스크립트에 `alembic upgrade head` 포함 (또는 `main.py` 부트 전 1회)
- **사용자 DB 백업 권장** (설치 문서 [INSTALL.md](../INSTALL.md)에 링크)

---

## 8. CI

| 항목 | 정책 |
|------|------|
| [`requirements-ci.txt`](../requirements-ci.txt) | Alembic **미포함** (unit·import smoke만) |
| optional job (후속) | 임시 SQLite v8 fixture → `alembic upgrade head` → 테이블 assert |

---

## 9. 참고 구현 패턴

| 파일 | 용도 |
|------|------|
| [`javstory/harvest/migrate_master_tables.py`](../javstory/harvest/migrate_master_tables.py) | `ATTACH DATABASE`로 `actresses`/`genres`/`makers` 병합 — bulk hydrate 참고 |
| [`javstory/harvest/database.py`](../javstory/harvest/database.py) | `upsert_jav_metadata`, `init_db` |

---

## 10. Phase DoD 요약

| Phase | DoD |
|-------|-----|
| P1 | `alembic upgrade head` 후 v8 테이블·컬럼·인덱스 목록 동일; `user_version`≥9 |
| P2 | `products`/`video_files` 존재; hydrate N품번 L4 parts와 order 일치 |
| P3 | 읽기 플래그 on/off 시 재생·목록 동일; unit 테스트 통과 |

---

## 변경 이력

| 날짜 | 내용 |
|------|------|
| 2026-05-16 | P0 확장 — 체크리스트·디렉터리·운영 절차 |

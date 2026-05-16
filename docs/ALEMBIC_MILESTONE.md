# Alembic 도입 마일스톤 (장기)

현재 `javstory/harvest/database.py`는 `PRAGMA user_version`과 `_migrate_v1` … `_migrate_v8`로 스키마를 관리합니다.

## 범위

- **유지**: user_version ≤ 8 까지의 기존 DB는 현재 체인으로만 업그레이드
- **신규**: v9 이상 컬럼·테이블 변경은 Alembic revision으로 추가
- **금지**: 기존 사용자 DB에 대한 destructive reset 없이 forward-only

## 착수 전제

1. `docs/DATA_SOT_LAYERS.md` 팀 합의
2. DB v2 테이블 설계 확정 (`db_schema_v2_proposal.md`)
3. `alembic.ini` + `javstory/harvest/migrations/` 초기 revision이 v8 스냅샷과 일치

## 참고 구현 패턴

- `javstory/harvest/migrate_master_tables.py` — 단계적 테이블 이행 예시

이 문서는 계획서 Phase 4(P3) 마일스톤용이며, Alembic 패키지는 아직 저장소에 포함하지 않습니다.

# JAVSTORY 데이터 단일 진실 소스(SoT) 계층

DB v2·Alembic 전면 이행 전, **어느 저장소가 무엇을 담당하는지** 합의용 1페이지 요약입니다.

| 계층 | 위치 | 담당 데이터 | 비고 |
|------|------|-------------|------|
| L1 | 디스크 영상·SRT·스틸 | 원본 미디어·자막 파일 | 절대 경로는 DB/JSON에 최소화, 폴더 바인딩 기준 |
| L2 | `data/db/jav_database.db` (`jav_metadata` 등) | 수집 메타·폴더 경로·즐겨찾기·시청 기록 | `harvest/database.py` PRAGMA v8까지 인라인 마이그레이션 |
| L3 | `data/cache/story_context/{품번}_grok.json` | Grok 스토리 맥락 JSON | `story_grok_module.story_context_cache_dir()` SoT; 레거시 `Transcription/story_context_cache/` 읽기 폴백 |
| L4 | `{library_root}/{품번}/library_state.json` | 편집 가능 canonical(씬·`media.parts`) | Grok JSON과 동기화·잠금 필드 |

## 중복 방지 원칙

- **품번·폴더 경로**: L2가 운영 SoT, L4는 편집·씬·분할 파트 순서
- **스토리 톤·씬 요약**: L3 생성 → L4에 병합 저장; UI 편집은 L4 우선
- **재생 순서**: L4 `media.parts`가 있으면 L1 탐색보다 우선 (`media_parts.py`)

## 장기 마일스톤 (별도 착수)

- **DB v2**: `products` / `video_files` / `scenes` 분리 — `db_schema_v2_proposal.md` 참고
- **Alembic**: v9 이후 스키마 변경만 Alembic; v1~v8은 기존 `_migrate_v*` 유지

자세한 마이그레이션 절차는 `docs/ALEMBIC_MILESTONE.md`를 참고하세요.

# JAVSTORY 데이터 단일 진실 소스(SoT) 계층

DB v2·Alembic 이행 전·후, **어느 저장소가 무엇을 담당하는지** 합의용 1페이지 요약입니다.

| 계층 | 위치 | 담당 데이터 | 비고 |
|------|------|-------------|------|
| L1 | 디스크 영상·SRT·스틸 | 원본 미디어·자막 파일 | 절대 경로는 DB/JSON에 최소화, 폴더 바인딩 기준 |
| L2 | `data/db/jav_database.db` | 수집 메타·폴더 경로·즐겨찾기·시청 기록 | `jav_metadata` + `products` / `video_files` — [DB_V2_DESIGN.md](DB_V2_DESIGN.md) |
| L3 | `data/cache/story_context/{품번}_grok.json` | Grok 스토리 맥락 JSON | `story_grok_module.story_context_cache_dir()` SoT; 레거시 `Transcription/story_context_cache/` 읽기 폴백 |
| L4 | `{library_root}/{품번}/library_state.json` | 편집 가능 canonical(**씬**·`media.parts`) | Grok JSON과 동기화·잠금 필드 — **씬 SoT는 L4 전용** (DB `scenes` 없음) |

## 중복 방지 원칙

- **품번·폴더 경로**: L2가 운영 SoT, L4는 편집·씬·분할 파트 순서
- **스토리 톤·씬 요약**: L3 생성 → L4에 병합 저장; UI 편집은 L4 우선
- **재생 순서**: L4 `media.parts` > L2 `video_files` (`JAVSTORY_DB_V2_READ=1`) > L1 탐색 — `product_repository.resolve_video_paths_for_playback`

## 장기 마일스톤

| 항목 | 문서 |
|------|------|
| **DB v2** (2차: `products` / `video_files`, 씬은 L4 유지) | [DB_V2_DESIGN.md](DB_V2_DESIGN.md) |
| **Alembic** (v9+ revision) | [ALEMBIC_MILESTONE.md](ALEMBIC_MILESTONE.md) |
| ER 참고 초안 | [db_schema_v2_proposal.md](../db_schema_v2_proposal.md) |

구현은 P0 설계 합의 후 단계별 착수(P1 Alembic stamp → P2 테이블·hydrate).

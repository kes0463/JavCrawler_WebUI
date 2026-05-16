# P3 수동 검증 체크리스트 (`JAVSTORY_DB_V2_READ=1`)

P3는 **L4 `media.parts` → L2 `video_files` → L1 `video_discovery`** 순으로 재생·STT 경로를 해석합니다.  
기본값은 `0`(L2 읽기 비활성). 안정화 확인 후 `1` 권장.

## 준비

1. `.env` 또는 환경 변수: `JAVSTORY_DB_V2_READ=1`
2. P2 hydrate 완료 (`products` 테이블에 행 존재). 미완이면:
   - 부트에서 자동 backfill 대기, 또는
   - `JAVSTORY_SKIP_BOOT_HYDRATE=1` 로 부트 스킵 후 `python tools/hydrate_products_v2.py`
3. 단위 테스트: `pytest tests/unit -q`

## 체크리스트 (약 30분)

| # | 시나리오 | 기대 결과 |
|---|----------|-----------|
| 1 | 폴더 바인딩된 **멀티파트** 작품 상세 열기 | `video_paths` 순서가 L4 `library_state.json` `media.parts`와 동일 |
| 2 | L4 `media.parts` 없고 DB에 `video_files`만 있는 작품 | `video_files.part_index` 순으로 재생·STT 큐 구성 |
| 3 | L4·L2 모두 없는 작품 (폴더만 바인딩) | 기존처럼 디스크 탐색(`video_discovery`)으로 1개 이상 경로 |
| 4 | 플레이어에서 1·2·3번 각각 재생 | 잘못된 파트 순서·누락 없음 |
| 5 | STT(자막) 큐에 멀티파트 추가 | 파트 순서가 UI 목록과 일치 |
| 6 | `JAVSTORY_DB_V2_READ=0` 으로 되돌린 뒤 동일 작품 | L4 parts 있으면 동일 동작; L2-only 작품은 L1 폴백 가능 |

## 회귀 시 확인

- `gui/library_data.resolve_video_paths` / `find_all_video_paths_for_product` 위임 경로
- `tests/unit/test_resolve_video_paths_p3.py` 실패 여부

## 관련 문서

- [DB_V2_DESIGN.md](DB_V2_DESIGN.md) §6 P3
- [INSTALL.md](../INSTALL.md) — DB v2 환경 변수

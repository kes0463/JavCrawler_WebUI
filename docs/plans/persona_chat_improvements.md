# 페르소나 챗 개선 제안 정리

페르소나 챗 분석 결과 도출된 개선안을 3개 그룹으로 정리한다.

## 핵심 관련 파일

- 챗 서비스/프롬프트/랭킹: `javstory/persona/persona_chat.py`
- 컨텍스트/검색 조립: `javstory/persona/erotic_persona_engine.py`
- 의도 분류: `javstory/persona/intent_classifier.py`
- 평점 목록: `javstory/persona/user_rating_list.py`
- 추천 후보 통합: `javstory/persona/recommendation_pool.py`
- UI: `gui/qml/components/PersonaChatWidget.qml`, `gui/qml/views/PersonaChatView.qml`

---

## 그룹 A. 기능/UX 개선

| 순위 | 항목 | 효과 | 난이도 |
|------|------|------|--------|
| 1 | 품번 링크 → 상세 이동 | ★★★★★ | 낮음 |
| 2 | 의도별 경량 모드 | ★★★★☆ | 중간 |
| 3 | 톤 프리셋 토글 | ★★★★☆ | 낮음 |
| 4 | degraded mode | ★★★☆☆ | 중간 |
| 5 | 추천 소스 통일 | ★★★☆☆ | 중간 |
| 6 | 메모리 가시화/편집 | ★★★☆☆ | 중간 |

---

## 그룹 B. 추천 다양성 개선

| 우선 | 방법 | 효과 |
|------|------|------|
| ★★★ | 모든 추천 요청에 최근 추천 품번 하드 제외 기본 적용 | 반복 제거 |
| ★★★ | 상위 N개 약한 무작위 샘플링/재랭킹 | 1~3위 고정 깨기 |
| ★★☆ | 검색 쿼리에 회전 시드(최근 추천 코드 부정) | 후보 풀 다양화 |
| ★★☆ | Hidden Gems/드리프트 신호 후보 혼합 | 탐색성 |
| ★☆☆ | recent_recommended_codes 메모리 기록 신뢰성 | 감점 누락 방지 |

---

## 그룹 C. 평점 목록 의도 신설

| 우선 | 방법 |
|------|------|
| ★★★ | `user_rating_list` 의도 추가 |
| ★★★ | `WatchHistory` 직접 조회 → 평점 내림차순 |
| ★★☆ | factual grounding 고정 주입 |
| ★★☆ | 0건 시 정직한 빈 응답 |

---

## 권장 진행 순서

1. C 그룹 (평점 목록 정확성)
2. B1, B2 (추천 다양성)
3. A1, A3 (저난도 고효용 UX)
4. 이후 A2/A4/A5/A6, B3/B4/B5

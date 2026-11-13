# Persona Chat 웹 확장 검토

웹 Persona Chat(`frontend/src/views/PersonaChatView.tsx`)이 신규 추가된 뒤, 데스크톱 QML
버전(`gui/qml/components/PersonaChatWidget.qml`) 및 백엔드(`javstory/persona/*`)와 비교해
"백엔드/데스크톱엔 있는데 웹엔 없는 것", "계산은 되는데 안 쓰이는 신호", "진입점 부재"를
중심으로 확장 가능한 항목을 정리한다. 기존 `persona_chat_improvements.md`(그룹 A/B/C)는
주로 챗 로직·랭킹 품질 개선안이고, 이 문서는 **웹 UI 관점의 확장/이식** 항목을 다룬다.

## 핵심 관련 파일

- 웹 챗 화면: `frontend/src/views/PersonaChatView.tsx`
- 웹 챗 API: `frontend/src/api/personaChat.ts`, `frontend/src/api/personaChatSessions.ts`
- 웹 라우트/스키마: `webapi/routes/persona_chat.py`, `webapi/schemas.py` (`PersonaChatMessageRequest` 등)
- 챗 서비스/톤/메모리: `javstory/persona/persona_chat.py`, `javstory/persona/persona_memory.py`
- 세션 저장: `javstory/persona/chat_sessions.py`
- 추천 피드백 루프: `javstory/persona/recommendation_feedback.py`
- 데스크톱 대조군: `gui/qml/components/PersonaChatWidget.qml`, `gui/models/insight_model.py`
- Insight 페르소나 카드: `frontend/src/components/insight/PersonaCardPanel.tsx`, `javstory/analytics/persona_card.py`

---

## 그룹 A. 이식(porting) — 백엔드/데스크톱엔 이미 있음, 웹만 안 씀

가장 낮은 리스크. 새 로직을 만들 필요 없이 기존 것을 웹에 연결만 하면 된다.

| 순위 | 항목 | 근거 | 난이도 |
|------|------|------|--------|
| 1 | ✅ 세션 이름 변경 UI | `renamePersonaChatSession()`(`personaChatSessions.ts`)·PATCH 라우트는 존재하지만 `PersonaChatView.tsx` 사이드바엔 삭제 버튼만 있고 이름 변경 트리거가 없음 — 사실상 데드 코드. **완료**: 사이드바에 연필 아이콘(호버 노출) 추가, 클릭 시 인라인 입력으로 전환, Enter/블러 저장·Esc 취소 | 낮음 |
| 2 | 톤 프리셋 토글 (분석/추천/도발) | `PersonaChatService.tone_preset` + `_tone_style_for_preset()` 로직은 이미 있고 QML `toneCombo`가 노출 중. 웹 `PersonaChatMessageRequest`엔 `tone_preset` 필드 자체가 없음 | 낮음~중간 |
| 3 | ✅ 메모리 가시화/편집 패널 | `EnhancedPersonaMemory.memory_snapshot_for_ui()` / `remove_note()` 구현 완료, QML `memoryPanel`이 이미 사용 중. 웹엔 이 메모리를 읽거나 지우는 REST 엔드포인트 자체가 없음 (`webapi/routes/persona_chat.py`는 메시지/세션 CRUD만 존재). **완료**: `GET /api/persona-chat/memory`, `DELETE /api/persona-chat/memory/{category}/{index}` 라우트 추가(`PersonaChatMemorySnapshot` 스키마), 헤더에 "기억 보기" 토글 + 카테고리별 노트 목록·삭제·최근 추천 품번 칩 패널 추가, 매 턴 완료 시 패널이 열려 있으면 자동 새로고침 | 중간 |
| 4 | ✅ 작품 컨텍스트(product_code) 전달 | `PersonaChatMessageRequest.product_code` 필드는 있고 백엔드도 이를 받아 컨텍스트에 반영하지만, `handleSend()`는 항상 `undefined`로 고정 전송 — 진입점 자체가 없음(그룹 C-7과 연결). **완료(1차)**: 메시지에 품번이 직접 언급되면 그 코드를, 없으면 현재 열려 있는 라이브러리 상세 패널(`detailCode`)의 작품을 자동으로 `product_code`로 전달. 입력창 위에 "OOO-000 기준으로 답변" 칩으로 컨텍스트를 보여주고 X로 해제 가능. 다른 화면(라이브러리/배우 상세)에서 곧바로 진입하는 딥링크는 C-7에서 별도 진행 | 낮음 |

---

## 그룹 B. 계산은 되지만 클라이언트로 안 나가는 신호

| 순위 | 항목 | 근거 | 난이도 |
|------|------|------|--------|
| 5 | ✅ 추천 근거 구조화 노출 | `_score_recommendation_item()`이 계산하는 `ranking_reasons`, `matched_seed_title/score`, `matched_query_terms`, `matched_genre_terms`는 지금 프롬프트 텍스트로만 녹아 들어가고, SSE 이벤트는 `token/reasoning/done/error`뿐이라 클라이언트가 구조화된 근거를 받을 수 없음. **완료**: `stream_chat()`이 응답 종료 직전 `_structured_recommendation_items()`로 (프롬프트 그라운딩에 쓰였던 `_recommendation_candidates_from_payload` 결과 중) 실제 답변에 언급된 품번만 골라 `type: "recommendations"` SSE 이벤트로 전송(`_sse_gen`은 이미 임의 이벤트를 그대로 통과시켜서 라우트 변경 불필요). 웹은 각 후보를 포스터(`coverUrl`)+매치 점수+매칭 배지(장르/쿼리/취향 키워드)+"«유사 시드작»과 비슷해서" 카드로 렌더링 | 중간~높음 |
| 6 | ✅ 추천→시청 피드백 루프 가시화 | `recommendation_feedback.sync_recommendation_watch_feedback()`가 매 대화 호출마다 백그라운드로 24시간 내 시청/평점을 보고 강한반응/부정피드백 노트를 자동 갱신하지만 사용자에겐 전혀 안 보임 — 그룹 A-3 메모리 패널이나 페르소나 카드에 "최근 추천 중 실제로 보신 작품" 한 줄만 있어도 신뢰도 상승. **완료**: `memory_snapshot_for_ui()`에 `pending_recommendation_outcomes`(반응 대기 중인 추천 품번) 노출 추가, `GET /memory`가 응답 전 `sync_recommendation_watch_feedback()`을 한 번 더 돌려서 패널을 열 때 최신 상태 반영. A-3 패널에 "추천 후 반응 확인 중" 칩 행 추가 + 시청/평점으로 자동 기록된 노트(`source: implicit_watch/post_rec_rating`)에 "👁 자동 감지" 배지로 사용자가 직접 말한 것과 구분 | 낮음 (A-3 선행 시) |

---

## 그룹 C. 진입점 확장

| 순위 | 항목 | 근거 | 난이도 |
|------|------|------|--------|
| 7 | ✅ 라이브러리/배우 상세 → 페르소나챗 딥링크 | `PosterCardContextMenu`, `LibraryDetailPanel`, `ActressDetailPanel` 어디에도 "이 작품/배우 페르소나챗에서 얘기하기" 항목이 없음. A-4의 product_code 지원과 묶으면 `source_policy: similar_by_work` 모드(이미 백엔드에 있음)를 바로 트리거하는 세션을 열 수 있음. **완료**: `NavigationContext`에 `openPersonaChat({ productCode?, prefillMessage? })` + `personaChatEntry`(1회 소비) 추가. Persona Chat 탭은 이 값을 받아 A-4의 `detailCode` 컨텍스트로 연결하고 입력창을 미리 채운다. 진입점 3곳 추가: 라이브러리 상세 패널 "페르소나챗에서 물어보기" 버튼, 포스터 카드 우클릭 메뉴(단일 선택 시), 배우 상세 패널 헤더 아이콘 버튼(배우 취향 프리필). 백엔드 변경 없음(A-4가 이미 처리) | 중간 |
| 8 | ✅ Insight 페르소나 카드 → Persona Chat 연결 | `PersonaCardPanel`은 요약/성향 태그 표시만 하고 끝. "이 성향 더 파고들기" 버튼으로 Persona Chat 탭에 프리필 메시지를 넘기면 Insight ↔ Persona Chat이 실질적으로 연동됨(현재는 모델 피커만 공유, 데이터는 안 이어짐). **완료**: C-7의 `openPersonaChat()`을 재사용해 카드 하단에 "이 성향 더 파고들기" 버튼 추가 — `persona_type` + `turn_ons`(부족하면 `affinities`로 보강) 상위 3개를 엮어 구체적인 프리필 메시지를 만들어 넘김. 백엔드 변경 없음 | 낮음~중간 |

---

## 그룹 D. 신규 UX (데스크톱에도 없는 아이디어)

| 순위 | 항목 | 비고 |
|------|------|------|
| 9 | ✅ 에러 응답 재시도 버튼 | 현재는 실패 시 토스트만 뜨고 재입력해야 함. **완료**: 실패한 답변 아래 "다시 시도" 버튼 → 같은 사용자 메시지·이전 히스토리로 같은 자리에 재스트리밍(`runTurn` 공유 실행부로 리팩터링). 실패한 턴은 애초에 서버에 저장 안 되므로 truncate 불필요 |
| 10 | ✅ 마지막 사용자 메시지 edit & resend | 오타/조건 수정 후 재전송. **완료**: 가장 최근 사용자 메시지에만 호버 시 연필 아이콘 → 인라인 편집(Enter 저장/Esc 취소) → 그 메시지 이후(원래 답변 포함)를 로컬에서 제거하고 새 턴 전송. 서버 세션 파일도 `POST /sessions/{id}/truncate`(신규, `keep_count`만큼만 남김)로 같은 지점까지 잘라서, 다른 대화로 갔다 돌아와도 옛 턴이 되살아나지 않게 함 — 실패/중지로 저장 안 된 턴이 있어도 개수가 어긋나지 않도록 메시지별 `persisted` 플래그로 실제 저장된 (user,assistant) 쌍만 센다 |
| 11 | ✅ 세션 검색/필터 | 세션이 쌓이면 사이드바에서 찾기 어려움. **완료**: 세션이 5개 넘으면 사이드바에 검색창 노출, 제목 부분일치로 필터링 |
| 12 | ✅ 대화 내보내기(마크다운) | 추천 리스트 저장/공유 용도. **완료**: 헤더에 다운로드 버튼 → 현재 대화를 `# 제목` + 화자별 문단의 마크다운으로 만들어 `.md` 파일로 다운로드(Blob) |

---

## 권장 진행 순서

1. A-3 (세션 이름 변경) — 반나절 이내, 위험 거의 없음 — ✅ 완료
2. A-1 / A-2 (톤 프리셋 + 메모리 패널) — 기존 `persona_chat_improvements.md` 그룹 A-6과도 겹치는 항목 — A-3(메모리 패널) ✅ 완료, A-2(톤 프리셋)는 미착수
3. C-7 (작품 상세 딥링크, A-4 선행) — ✅ 완료 (A-4 포함)
4. B-5 (추천 근거 카드) — 프론트 렌더링 작업 비중이 커서 뒤로 — ✅ 완료
5. 이후 B-6, C-8, D 그룹 — ✅ 전부 완료

## 진행 현황

완료: A-1, A-3, A-4, B-5, B-6, C-7, C-8, D-9, D-10, D-11, D-12
미착수: A-2(톤 프리셋 토글) — 유일하게 남은 항목. `PersonaChatService.tone_preset` + `_tone_style_for_preset()`는 이미 있으므로 `PersonaChatMessageRequest`에 `tone_preset` 필드 추가 + 작은 토글 UI만 남음.

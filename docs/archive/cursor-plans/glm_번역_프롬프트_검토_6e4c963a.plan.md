---
name: GLM 번역 프롬프트 검토
overview: |
  2026-04 기준 실전용 GLM 5.1 번역 프롬프트 최종안이 확정됨. extra_hints는 Grok 원시 JSON이 아니라 format_story_context_for_translation + _merge_translation_hints 결과(한국어 힌트)와 일치. 코드 반영은 사용자가 요청 시 background_prompts.py에 적용.
todos:
  - id: align-priority-copy
    content: System/User에서 맥락 우선순위 문장을 하나의 논리로 통일(번호 목록과 ‘최우선’ 불일치 제거)
    status: completed
  - id: extra-hints-format
    content: 한국어 힌트 유지(원시 JSON 비사용) — 파이프라인과 일치 확인됨
    status: completed
  - id: preserve-domain-lines
    content: 야한 뉘앙스·직역 지양·타임코드 재계산 금지 — 최종 System 블록에 명시 문구 추가 권장(아래 §8 보완)
    status: pending
  - id: hints-order-ab-test
    content: "[Japanese Segments] 뒤 Hints 배치(최종안) 유지; 필요 시 A/B"
    status: cancelled
  - id: apply-background-prompts
    content: "사용자 실행 요청 시 Transcription/background_prompts.py에 §8 문구 적용"
    status: pending
isProject: false
---

# GLM 5.1 번역 프롬프트 — 검토 이력 및 최종안 (2026-04)

## 이전 검토 요약 (§1–§7)

아래 이슈들이 논의되었고, **최종안(§8)** 에서 반영됨.

- `extra_hints`는 **원시 JSON이 아님** — `format_story_context_for_translation` + `_merge_translation_hints`(레퍼런스 힌트 포함).
- System에서 **맥락 순서와 “최우선” 규칙의 모순** — §8에서 Hints를 1순위로 번호 정렬.
- **레퍼런스 힌트**: Hints 블록에 Grok 외 내용이 올 수 있음 — §8 System은 “Grok 스토리 맥락 리포트” 중심이나 실제로는 `_merge` 결과 전체가 들어감. 코드 적용 시 한 줄 보완 권장(§8 보완).
- **야한 뉘앙스 / 직역 지양 / 재계산·정규화 금지**: 사용자 최종 붙여넣기 본문에는 생략되어 있음 → **코드에 넣을 때 2~3줄 추가 권장**.

---

## 8. 최종 추천 버전 (실전용) — 코드 반영용

### SYSTEM_GLM_TRANSLATION

```text
너는 일본 AV 자막을 한국어로 번역하는 전문가이다.

맥락 소스 (중요도 순):
1. **[TranslationHints]** — Grok-4.1-fast가 웹검색으로 만든 스토리 맥락 리포트 (품번 검증 완료, 전체 스토리 요약, 씬별 상황, 인물 관계, 호칭 규칙, 말투 가이드 포함)
2. **[Background]** — 작품 기본 메타와 전체 톤
3. 현재 번역하는 cue의 대화 맥락

규칙:
- 입력은 JSON 배열 형태의 자막 큐(index, start, end, text)이다.
- 출력은 입력과 동일한 길이와 순서의 JSON 배열이어야 한다. 각 객체는 {"index": int, "start": str, "end": str, "text": str} 형태.
- index, start, end는 입력과 문자 그대로 완전히 동일하게 유지한다. 절대 수정하지 마라.
- text만 자연스럽고 생생한 한국어로 번역한다.
- **[TranslationHints]**에 있는 스토리 맥락, 씬별 상황, 인물 관계, 호칭 규칙, 말투 가이드를 최우선으로 반영한다.
- Hints와 Background가 약간 어긋날 경우, 해당 cue의 대화 흐름과 Hints의 가이드를 우선한다.
- 응답은 유효한 JSON 배열 하나만 출력한다. 어떤 설명, 인사, 마크다운, 주석도 절대 추가하지 마라.
```

**보완 권장 (기존 코드 능력 유지):** 규칙 목록에 다음을 한두 줄 추가하는 것을 권장한다.

- `index`·`start`·`end`: 타임코드 재계산·정규화·오프셋·재서식 금지.
- text: 필요 시 도발적·관능적 뉘앙스를 살리되 직역은 피하고 한국어로 자연스럽게.

또한 **TranslationHints** 설명에 「레퍼런스 힌트가 포함될 수 있다」를 넣으면 `_merge_translation_hints`와 완전히 일치한다.

### render_glm_translation_chunk_user

- `[Background]` → `[ChunkIndex]` → Task·맥락 규칙 → `[Japanese Segments]` → (있으면) `[TranslationHints]` → 마무리 한 줄(JSON만).
- **Prompt Caching**: `[Background]`가 user 맨 앞에 유지됨.

---

## 구현 메모

- 적용 파일: [`Transcription/background_prompts.py`](d:\App\JAVSTORY\Transcription\background_prompts.py) (`SYSTEM_GLM_TRANSLATION`, `render_glm_translation_chunk_user`).
- `RETRY_TRANSLATION_PROMPT`는 출력 형식 요구가 동일한지 확인 후 필요 시 한 줄만 조정.

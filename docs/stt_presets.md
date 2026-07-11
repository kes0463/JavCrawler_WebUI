# STT 프리셋 비교 노트

JAVSTORY WebUI / Processing 큐 STT는 `JAVSTORY_STT_ENGINE` 환경 변수(설정 → 전사)로 선택합니다.

## 프리셋 요약

| 프리셋 | env 값 | 백엔드 | 모델 | 특징 |
|--------|--------|--------|------|------|
| Stable TS | `stable_ts` | PyTorch | `JAVSTORY_WHISPER_MODEL` (기본 large-v2) | 현행 경로, VAD·regroup·싱크 보정 |
| Stable TS + FW | `stable_ts_fw` | CTranslate2 | `JAVSTORY_FASTER_WHISPER_MODEL` (기본 kotoba-v2.0-faster) | GPU 메모리·속도 유리, stable-ts 후처리 동일 |
| Anime-Whisper | `anime_whisper` | HF + stable-ts | `JAVSTORY_HF_WHISPER_MODEL` (기본 litagin/anime-whisper) | 일본어 연기·감정 대사 인식 강점 |
| WhisperX | `whisperx` | — | — | **미구현** (forced alignment 전용, stable-ts와 중복) |

## 공통 후처리

모든 프리셋은 **한 번의 transcribe** 안에서 stable-ts가 다음을 수행합니다.

- VAD (`JAVSTORY_VAD_THRESHOLD`, 대사만 모드 시 최소 0.45)
- `split_by_length` / `split_by_duration` / `merge_by_gap`
- **긴 단문 헛자막** (`JAVSTORY_STT_FIX_STICKY_HALLUCINATION=1`, 기본): 1s~17s처럼 짧은 텍스트에 긴 end가 붙은 초반 환각 제거
- **대사만 모드** (`JAVSTORY_STT_DIALOGUE_ONLY=1`): `dialogue_filter`로 신음·헛자막 세그먼트 제거

## 벤치마크 (로컬 GPU 환경에서 직접 측정 권장)

| 항목 | stable_ts | stable_ts_fw | anime_whisper |
|------|-----------|--------------|---------------|
| VRAM | 높음 (large-v2 FP16) | 중~낮 (CT2 float16) | 중 (HF + FP16) |
| 속도 | 기준 | 보통 2~4× 빠름 (GPU·모델 의존) | kotoba 계열 대비 도메인 특화 |
| 대사 정확도 | 일반 | kotoba 계열 JA 우수 | 연기·감정 JA 우수 |
| 헛자막 | VAD 의존 | VAD 의존 | VAD + **대사만 필터** 권장 |

측정 방법: 동일 영상 1편에 대해 Processing STT 큐 실행 후 로그의 `[P:*] 전사` 구간 시간·`.ja.srt` 세그먼트 수 비교.

## 관련 env

```
JAVSTORY_STT_ENGINE=stable_ts|stable_ts_fw|anime_whisper
JAVSTORY_WHISPER_MODEL=large-v2
JAVSTORY_FASTER_WHISPER_MODEL=kotoba-tech/kotoba-whisper-v2.0-faster
JAVSTORY_HF_WHISPER_MODEL=litagin/anime-whisper
JAVSTORY_VAD_THRESHOLD=0.35
JAVSTORY_STT_DIALOGUE_ONLY=1
JAVSTORY_STT_FIX_STICKY_HALLUCINATION=1
JAVSTORY_STT_DROP_EARLY_STICKY=1
```

Web UI: **설정 → 전사 (STT)** 또는 `GET/PATCH /api/settings/stt`

# 테스트 가이드

프로젝트 루트에서 실행합니다. 가상환경 활성화 후 `pip install -r requirements-dev.txt` 권장.

## 자동 단위 테스트 (pytest)

```text
python -m pytest Test/unit -q
```

- 설정: [`pytest.ini`](pytest.ini) — `testpaths = Test/unit` 만 수집합니다.
- `Test/manual/`·`Test/cli/`의 `test_*.py` 이름을 피해 수동 스크립트와 충돌하지 않게 했습니다(번역 스모크는 `smoke_ko_translation_pipeline.py`).
- `Test/unit/conftest.py`가 프로젝트 루트를 `sys.path`에 넣습니다.

## 수동 스모크·GUI (`Test/manual/`)

| 스크립트 | 설명 |
|----------|------|
| [`Test/manual/smoke_ko_translation_pipeline.py`](Test/manual/smoke_ko_translation_pipeline.py) | KO 번역 파이프라인 스모크 (API 키·모델·`.env` 등 사전 조건은 파일 상단 docstring) |
| [`Test/manual/subtitle_pipeline_test_gui.py`](Test/manual/subtitle_pipeline_test_gui.py) | 자막 파이프라인 Tkinter GUI |
| [`Test/manual/transcription_workflow_test_gui.py`](Test/manual/transcription_workflow_test_gui.py) | STT 워크플로 Tkinter GUI |

예:

```text
python Test\manual\smoke_ko_translation_pipeline.py --help
```

## CLI 검증 (`Test/cli/`)

| 스크립트 | 설명 |
|----------|------|
| [`Test/cli/multipart_merge_timeline.py`](Test/cli/multipart_merge_timeline.py) | 멀티파트 영상 경로들 → 논리 타임라인 합본 SRT (파트별 동명 `.ja.srt`/`.srt`, **ffmpeg/ffprobe** 필요) |

예:

```text
python Test\cli\multipart_merge_timeline.py -o out.ja.srt part1.mp4 part2.mp4
```

## 기능 ↔ 테스트 매핑 (요약)

| 영역 | 단위 테스트 파일 |
|------|------------------|
| canonical JSON | `Test/unit/test_canonical_schema.py` |
| Grok 병합 | `Test/unit/test_grok_merge.py` |
| time_range 파싱 | `Test/unit/test_stills.py` |
| 동영상 확장자 | `Test/unit/test_video_ext_and_queue_utils.py` |
| export 지문 | `Test/unit/test_export_fingerprints.py` |
| export 경로 | `Test/unit/test_export_bundle_paths.py` |
| 멀티파트·합본 SRT | `Test/unit/test_multipart.py` |
| 파이프라인 상태 | `Test/unit/test_pipeline_status.py` |

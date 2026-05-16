# JAVSTORY 진입점 · UI 스택

**운영 UI는 PySide6 + QML 하나만 사용합니다.**  
신규 화면·버튼·상태는 `gui/qml/` 및 `gui/models/`(PySide6 `QObject`)에만 추가합니다.

파이프라인·단계별 모듈 경로: [`WORKFLOW_PIPELINES.md`](../../WORKFLOW_PIPELINES.md)  
파이프라인 상세: [`WORKFLOW_PIPELINES.md`](../../WORKFLOW_PIPELINES.md) · (아카이브) [`jav_story_workflow.md`](../archive/agent/jav_story_workflow.md)

---

## 운영 (Production)

| 항목 | 경로 |
|------|------|
| 진입점 | [`main.py`](../../main.py) |
| QML 엔진·모델 등록 | [`gui/app.py`](../../gui/app.py) → `create_engine()` |
| 화면 | [`gui/qml/main.qml`](../../gui/qml/main.qml), [`gui/qml/views/`](../../gui/qml/views/) |
| 런처 (Windows) | [`start.bat`](../../start.bat) → `python main.py` |
| 설치 | [`INSTALL.md`](../../INSTALL.md), [`setup.bat`](../../setup.bat) |
| 부트 크래시 로그 | `logs/crash_report.txt`, `logs/javstory.jsonl` (`boot_crash`) |
| 파이프라인 실패 | `data/error/04_ERROR/` + jsonl `pipeline_error` |
| 파이프라인 실패 큐 | `data/error/04_ERROR/` ([`javstory/utils/error_recovery.py`](../../javstory/utils/error_recovery.py)) |

### 부트 시퀀스

```
main.py
  ├─ javstory.transcription.venv_bootstrap
  ├─ javstory.utils.dll_patcher / ffmpeg_path
  ├─ PySide6.QtWidgets.QApplication
  └─ gui.app.create_engine(app)
       ├─ javstory.harvest.database.init_db
       ├─ QQmlApplicationEngine + gui/qml/
       └─ LibraryModel, ProcessingModel, SettingsModel, … (context 등록)
```

---

## 레거시 (Deprecated — 수정·신규 기능 금지)

| 항목 | 경로 | 비고 |
|------|------|------|
| PyQt6 Fluent 메인 | [`gui/main_window.py`](../../gui/main_window.py) | `main.py`에서 **호출하지 않음** |
| 위젯 뷰 5종 | [`gui/views/`](../../gui/views/) | Dashboard / Harvest / Processing / Library / Settings |
| PyQt6 전용 위젯 | [`gui/components/`](../../gui/components/) 중 `PyQt6` import 파일 | QML 미사용 |
| 테마 (PyQt6) | [`gui/theme_manager.py`](../../gui/theme_manager.py) | Fluent 전용 |

상세: [`gui/views/README.md`](../../gui/views/README.md)

---

## 동결 (Frozen — non-production)

**결정**: [ADR 0001 — QML 단일 스택](../adr/0001-ui-stack-qml-only.md) (2026-05-16).  
아래는 **신규 기능·버그 수정 대상 아님**. 삭제는 동결 6~12개월 후 검토.

| 항목 | 경로 | 비고 |
|------|------|------|
| React + Electron | [`frontend/`](../../frontend/) | [`frontend/README.md`](../../frontend/README.md) |
| HTTP API | [`api/main.py`](../../api/main.py) | [`api/README.md`](../../api/README.md) |

---

## CLI

| 역할 | 경로 |
|------|------|
| 품번 파이프라인 | [`scripts/run_product_pipeline.py`](../../scripts/run_product_pipeline.py) |

---

## 제거된·존재하지 않는 진입점 (문서만 남은 경우)

- `gui_main_v2.py` — 삭제됨. `main.py` 사용.
- `core/scene_analysis_v2/` — 본 저장소에 없음 (별도 플랜/실험 참고).
- 루트 `config.json`, `javstory_player.ini` — 미사용. [`docs/deprecated/`](../deprecated/README.md) 로 이전.

문서에서 위 이름이 보이면 **이 파일 기준으로 수정**하세요.

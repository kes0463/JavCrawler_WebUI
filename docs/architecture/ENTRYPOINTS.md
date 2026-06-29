# JAVSTORY 진입점 · UI 스택

**데스크톱 운영 UI는 PySide6 + QML**입니다.  
**WebUI**(브라우저)는 2차 진입점 — [ADR 0002](../adr/0002-webui-secondary-entrypoint.md).

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

## WebUI (2차 진입점)

| 항목 | 경로 |
|------|------|
| HTTP API | [`webapi/main.py`](../../webapi/main.py) |
| React UI | [`frontend/`](../../frontend/) |
| 서비스 레이어 | [`javstory/services/`](../../javstory/services/) |
| 런처 (Windows) | [`start_web.bat`](../../start_web.bat) |
| 의존성 | [`requirements-web.txt`](../../requirements-web.txt) |

---

## 동결 (Frozen — non-production)

**결정**: [ADR 0001](../adr/0001-ui-stack-qml-only.md).  
**레거시 HTTP** [`api/`](../../api/) — WebUI는 [`webapi/`](../../webapi/) 사용.

| 항목 | 경로 | 비고 |
|------|------|------|
| 레거시 React+Electron 실험 | [`frontend/`](../frontend/) 일부 | WebUI로 **재활용** (ADR 0002) |
| 동결 HTTP API | [`api/main.py`](../../api/main.py) | 확장 금지 |

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

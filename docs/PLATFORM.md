# 플랫폼 · 크로스 플랫폼

## 지원 정책

| 수준 | 플랫폼 | 설명 |
|------|--------|------|
| **공식** | Windows 10/11 64-bit | `start.bat`, Mica, 전체 GUI |
| **실험** | Linux / macOS | UI·Mica 미지원 구간 있음. CI·헤드리스·스크립트 위주 |

운영 UI는 PySide6 + QML ([ENTRYPOINTS.md](architecture/ENTRYPOINTS.md)).

---

## Windows 전용 요소

| 항목 | 위치 | 비-Windows 동작 |
|------|------|-----------------|
| `win32mica` | `requirements.txt` (조건부 설치) | 미설치 — Mica 스킵 |
| Mica 적용 | `gui/app.py` `_apply_mica` | `sys.platform != "win32"` 시 return |
| 런처 | `start.bat`, `setup.bat` | `scripts/start.sh` 참고 |
| `JAVSTORY_DISABLE_MICA` | env | Windows에서만 의미 |

`pip install -r requirements.txt` 는 Linux/macOS에서도 **win32mica 없이** 진행됩니다 (`sys_platform == "win32"` 마커).

---

## Linux / macOS에서 시도할 때

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# GPU: requirements-torch.txt (CUDA는 NVIDIA Linux만)
export JAVSTORY_DISABLE_MICA=1
python main.py
```

또는 [`scripts/start.sh`](../scripts/start.sh).

제한:

- Fluent/Mica·일부 경로 다이얼로그는 Windows에서만 검증됨
- Playwright·Chrome 드라이버는 OS별 설치 필요
- STT GPU는 해당 OS CUDA 스택 필요

---

## 로그 위치 (공통)

| 종류 | 경로 |
|------|------|
| 부트 크래시 (텍스트) | `logs/crash_report.txt` |
| 구조화 이벤트 | `logs/javstory.jsonl` |
| 파이프라인 실패 큐 | `data/error/04_ERROR/<STAGE>/*.json` |

[REPO_LAYOUT.md](REPO_LAYOUT.md), [ISSUES_STATUS.md](ISSUES_STATUS.md)

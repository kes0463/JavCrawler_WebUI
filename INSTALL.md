# JAVSTORY 설치 가이드

데스크톱 앱(Windows) 기준입니다. 운영 UI는 **PySide6 + QML** (`main.py` → `start.bat`).

---

## 요구 사항

| 항목 | 권장 |
|------|------|
| OS | Windows 10/11 (64-bit) — [docs/PLATFORM.md](docs/PLATFORM.md) (Linux/macOS 실험) |
| Python | **3.10 ~ 3.12** (`python --version`) |
| GPU (선택) | NVIDIA + CUDA 12 드라이버 (STT GPU 가속) |
| FFmpeg | PATH에 `ffmpeg` / `ffprobe` (또는 앱이 찾는 경로에 배치) |
| 디스크 | venv + 모델 캐시 수 GB 여유 |

---

## 빠른 설치 (Windows)

```bat
setup.bat
start.bat
```

`setup.bat`은 `venv` 생성 후 다음 순서로 설치합니다.

1. `requirements.txt` — GUI·Harvest·자막·DB 등
2. `requirements-torch.txt` — PyTorch + CUDA 12 wheel

---

## 수동 설치

저장소 루트에서:

```bat
python -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-torch.txt
```

실행:

```bat
python main.py
```

`main.py`는 Windows에서 프로젝트 `venv\Scripts\python.exe`가 있으면 자동으로 그 인터프리터로 재실행합니다 (`javstory.transcription.venv_bootstrap`).

---

## 의존성 파일

| 파일 | 용도 |
|------|------|
| [`requirements.txt`](requirements.txt) | 앱 본체 (PySide6, Whisper/stable-ts, LLM, DB, …) |
| [`requirements-torch.txt`](requirements-torch.txt) | **PyTorch + CUDA 12** (GPU STT) |
| [`requirements-ci.txt`](requirements-ci.txt) | GitHub Actions — unit 테스트·import smoke (GPU·Qt 없음) |

- CUDA **12만** (`requirements-torch.txt`). cu11 패키지는 추가하지 않습니다.
- `openai-whisper`는 requirements에 없음 — `stable-ts` transitive.
- 이슈 대조표: [`docs/ISSUES_STATUS.md`](docs/ISSUES_STATUS.md)

---

## PyTorch: GPU vs CPU

### NVIDIA GPU (기본·`setup.bat`과 동일)

```bat
pip install -r requirements-torch.txt
```

`nvidia-cublas-cu12`, `nvidia-cudnn-cu12`와 함께 CUDA 12용 `torch` wheel이 설치됩니다.

### CPU만 (GPU 없음 / 드라이버 미설치)

`requirements-torch.txt`의 **nvidia-* 줄은 설치하지 마세요.** CPU wheel만 설치합니다.

```bat
pip install -r requirements.txt
pip install torch torchaudio torchvision --index-url https://download.pytorch.org/whl/cpu
```

버전은 `requirements-torch.txt`의 핀(`>=2.4,<2.6` 등)에 맞춰 조정할 수 있습니다.

### 이미 잘못된 torch가 깔린 경우

```bat
pip uninstall -y torch torchaudio torchvision nvidia-cublas-cu12 nvidia-cudnn-cu12
```

이후 위 GPU 또는 CPU 절차를 다시 실행합니다.

---

## API 키·설정

- **OpenRouter 등**: 프로젝트 루트 `.env` 또는 앱 설정 화면 → Windows **자격 증명 관리자(keyring)**  
  (`javstory/config/secrets_manager.py`, `javstory/config/app_config.py`)
- 루트 `config.json` / `javstory_player.ini` — **미사용** (예시는 `docs/deprecated/`)

대용량 작품 데이터는 기본적으로 `E:\App\JAVSTORY\data\` 레이아웃을 가정합니다. 경로는 `app_config.py` 및 `.env`로 조정합니다.

---

## 데이터베이스 마이그레이션 (Alembic)

앱 부트 시 `init_db()`(v0–v8) 후 `alembic upgrade head`(v9+)가 자동 실행됩니다.

**마이그레이션 실패 시**: 앱은 종료하지 않고 **읽기 전용**으로 UI를 띄웁니다. 자동 백업은 `data/db/backups/jav_database_pre_upgrade_failed_*.db`, 복구 절차·트레이스백은 `logs/db_upgrade_recovery.txt`, 구조화 로그는 `logs/javstory.jsonl` (`boot_db_upgrade_failed`)입니다. 수집·DB 쓰기는 차단되며 라이브러리 조회는 가능합니다.

수동 적용:

```bat
copy data\db\jav_database.db data\db\jav_database.db.bak
venv\Scripts\activate
alembic upgrade head
```

P1(`0001_stamp_v8`)은 **스키마 변경 없음** — `user_version` 8→9.  
P2(`0002_add_products_video_files`)는 `products` / `video_files` 테이블 추가 (`user_version` 10).  
수동 backfill: `python tools/hydrate_products_v2.py`  

P3 읽기 경로: 환경변수 `JAVSTORY_DB_V2_READ=1` 시 재생·목록에서 L4 `media.parts` → L2 `video_files` → L1 탐색 순으로 해석 (`gui/library_data`, `LibraryDetailService`).  

자세한 내용: [`docs/ALEMBIC_MILESTONE.md`](docs/ALEMBIC_MILESTONE.md), [`docs/DB_V2_DESIGN.md`](docs/DB_V2_DESIGN.md)

---

## FFmpeg

STT·스틸 추출·하이라이트에 필요합니다.

- [ffmpeg.org](https://ffmpeg.org/download.html) Windows 빌드를 받아 `bin`을 PATH에 추가하거나
- 앱이 탐색하는 고정 경로에 배치 (`javstory.utils.ffmpeg_path`)

---

## DB v2 (P2–P3)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `JAVSTORY_DB_V2_READ` | `0` | `1`이면 재생·목록에 L2 `video_files` 사용 (L4 `media.parts` 우선) |
| `JAVSTORY_SKIP_BOOT_HYDRATE` | `0` | `1`이면 앱 부트 시 `products` backfill 생략 |
| `JAVSTORY_HYDRATE_PROGRESS_EVERY` | `100` | 부트/수동 hydrate 시 N품번마다 진행 로그 |

첫 실행 시 `products`가 비어 있으면 **jav_metadata 전건 + 폴더별 디스크 스캔**으로 수 분~수십 분 걸릴 수 있습니다. 콘솔에 `[DB] P2 hydrate progress: …` 로그가 출력됩니다.

- 밤에만 backfill: `set JAVSTORY_SKIP_BOOT_HYDRATE=1` 후 앱 실행, 이어서 `python tools/hydrate_products_v2.py`
- 완료 마커: `data/db/.products_v2_hydrate_done` (hydrate 성공 시 생성)

P3 수동 검증: [`docs/P3_VERIFY.md`](docs/P3_VERIFY.md). 안정화 후 `JAVSTORY_DB_V2_READ=1` 권장.

---

## CI (개발자)

GitHub Actions: [`.github/workflows/ci.yml`](.github/workflows/ci.yml)

```bash
pip install -r requirements-ci.txt
pytest tests/unit -q --ignore=tests/unit/test_import_smoke.py
pytest tests/unit/test_import_smoke.py -q
```

GPU·Whisper·PySide6 없이 핵심 로직·import만 검증합니다.

---

## 문제 해결

| 증상 | 확인 |
|------|------|
| CUDA unavailable / CPU만 사용 | `venv` 활성화 여부, `pip show torch` 버전, CPU wheel vs CUDA wheel |
| `setup.bat` 실패 | Python PATH, `pip install` 로그, 방화벽/프록시 |
| 앱 즉시 종료 | `logs/crash_report.txt`, `logs/javstory.jsonl` |
| Ollama 로컬 번역 모델 | `config/ollama/README.md`, `scripts/ollama_create_model.bat` |
| 부트 시 Alembic 후 오래 멈춤 | P2 hydrate 진행 중 — 로그 `P2 hydrate progress` 확인; 급하면 `JAVSTORY_SKIP_BOOT_HYDRATE=1` + `tools/hydrate_products_v2.py` |
| 시작 시 "DB 마이그레이션 실패 (읽기 전용)" | `logs/db_upgrade_recovery.txt` 따라 `alembic upgrade head` 수동 실행; 필요 시 `data/db/backups/` 백업으로 `data/db/jav_database.db` 복원 |
| LLM 전 구간 실패 | `docs/llm_troubleshooting.md`, OpenRouter 키·티어 |

진입점·UI 스택: [`docs/architecture/ENTRYPOINTS.md`](docs/architecture/ENTRYPOINTS.md)

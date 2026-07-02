"""운영 GUI — QML 엔진 초기화 및 PySide6 모델 등록 (`main.py` → `create_engine`).

PyQt6 Fluent (`gui/main_window.py`) 는 사용하지 않음. → `docs/architecture/ENTRYPOINTS.md`
"""

from __future__ import annotations

import os
import sys
import atexit
import subprocess
import threading
from pathlib import Path

import shutil
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtQml import QQmlApplicationEngine

_QML_DIR = Path(__file__).resolve().parent / "qml"
_OLLAMA_SERVE_LOG_PATH: Path | None = None
_OLLAMA_SERVE_PROC: subprocess.Popen | None = None


def _ollama_base_url() -> str:
    try:
        from javstory.config.app_config import OLLAMA_BASE_URL

        return (os.environ.get("JAVSTORY_OLLAMA_URL", "") or "").strip() or OLLAMA_BASE_URL
    except Exception:
        return (os.environ.get("JAVSTORY_OLLAMA_URL", "") or "").strip() or "http://localhost:11434"


def _should_auto_start_ollama() -> bool:
    raw = (os.environ.get("JAVSTORY_AUTO_OLLAMA_SERVE", "") or "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    # 번역 프로필/설정이 Ollama를 쓰는 경우에만 자동 실행(기본)
    try:
        from javstory.config.app_config import resolve_translation_llm_tier

        tier = resolve_translation_llm_tier()
        return str(tier.get("provider") or "").lower() == "ollama"
    except Exception:
        return False


def _ollama_is_responding(base_url: str) -> bool:
    try:
        import httpx

        url = base_url.rstrip("/") + "/api/version"
        r = httpx.get(url, timeout=httpx.Timeout(0.6, connect=0.4))
        return r.status_code >= 200 and r.status_code < 500
    except Exception:
        return False


def _find_ollama_exe() -> str | None:
    exe = shutil.which("ollama")
    if exe:
        return exe
    # Windows 기본 설치 경로(사용자별 설치)
    try:
        if sys.platform == "win32":
            local = os.environ.get("LOCALAPPDATA", "") or ""
            if local:
                p = Path(local) / "Programs" / "Ollama" / "ollama.exe"
                if p.is_file():
                    return str(p)
    except Exception:
        pass
    return None


def _ollama_log_path() -> Path | None:
    """
    자동 실행 로그 파일 경로.
    작업 디렉터리/패키징 환경과 무관하게 쓰기 가능한 위치(LOCALAPPDATA)를 우선한다.
    """
    try:
        base = (os.environ.get("LOCALAPPDATA", "") or "").strip()
        if not base:
            return None
        d = Path(base) / "JAVSTORY" / "logs"
        d.mkdir(parents=True, exist_ok=True)
        return d / "ollama-serve.log"
    except Exception:
        return None


def _cleanup_ollama_child() -> None:
    global _OLLAMA_SERVE_PROC
    p = _OLLAMA_SERVE_PROC
    _OLLAMA_SERVE_PROC = None
    if not p:
        return
    try:
        if p.poll() is None:
            try:
                p.terminate()
            except Exception:
                pass
            try:
                p.wait(timeout=2.0)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
    except Exception:
        pass


def _maybe_start_ollama_serve(app) -> None:
    """
    로컬 Ollama 사용 설정이면 앱 시작 시 `ollama serve`를 자동으로 띄운다.
    - 이미 떠 있으면 아무것도 하지 않는다.
    - 실행한 프로세스는 앱 종료 시 함께 종료(자식 프로세스)한다.
    """
    global _OLLAMA_SERVE_PROC
    if _OLLAMA_SERVE_PROC is not None:
        return
    if not _should_auto_start_ollama():
        # 자동 실행이 안 되는 이유가 가장 흔히 'provider가 ollama가 아님'이라,
        # 디버깅을 위해 최소한의 힌트를 남긴다.
        try:
            from javstory.config.app_config import resolve_translation_llm_tier

            tier = resolve_translation_llm_tier()
            prov = str(tier.get("provider") or "")
        except Exception:
            prov = "unknown"
        forced = (os.environ.get("JAVSTORY_AUTO_OLLAMA_SERVE", "") or "").strip()
        if forced:
            print(f"[UI] Ollama 자동 실행 스킵: JAVSTORY_AUTO_OLLAMA_SERVE={forced!r} (truthy 아님)")
        else:
            print(f"[UI] Ollama 자동 실행 스킵: translation provider={prov!r} (ollama가 아님)")
        return

    base_url = _ollama_base_url()
    if _ollama_is_responding(base_url):
        return

    exe = _find_ollama_exe()
    if not exe:
        print("[UI] Ollama 자동 실행 실패: PATH에서 `ollama` 실행 파일을 찾지 못했습니다.")
        return

    try:
        # 로그를 파일로 남겨 자동 실행 실패/즉시 종료 원인을 볼 수 있게 한다.
        global _OLLAMA_SERVE_LOG_PATH
        _OLLAMA_SERVE_LOG_PATH = _ollama_log_path()

        stdout = stderr = subprocess.DEVNULL
        if _OLLAMA_SERVE_LOG_PATH:
            try:
                logf = open(_OLLAMA_SERVE_LOG_PATH, "a", encoding="utf-8")  # noqa: SIM115
                stdout = logf
                stderr = logf
            except Exception:
                stdout = stderr = subprocess.DEVNULL

        _OLLAMA_SERVE_PROC = subprocess.Popen(
            [exe, "serve"],
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
        )
        atexit.register(_cleanup_ollama_child)
        try:
            # Qt 앱 종료 시 함께 내리기
            app.aboutToQuit.connect(_cleanup_ollama_child)
        except Exception:
            pass
        if _OLLAMA_SERVE_LOG_PATH:
            print(
                f"[UI] Ollama 자동 실행: {exe} serve (base_url={base_url}, log={_OLLAMA_SERVE_LOG_PATH})"
            )
        else:
            print(f"[UI] Ollama 자동 실행: {exe} serve (base_url={base_url})")
        # 백그라운드에서 잠깐 기다렸다가 살아있는지 체크(로그는 과도하게 남기지 않음)
        QTimer.singleShot(
            900,
            lambda: (
                None
                if _ollama_is_responding(base_url)
                else print("[UI] Ollama 자동 실행: 아직 응답 없음(초기 구동/모델 로딩일 수 있음)")
            ),
        )
        # 프로세스가 즉시 종료되는 케이스(포트 충돌/권한 등)면 힌트를 남긴다.
        def _check_exit() -> None:
            p = _OLLAMA_SERVE_PROC
            if not p:
                return
            code = p.poll()
            if code is not None and not _ollama_is_responding(base_url):
                tail = ""
                if _OLLAMA_SERVE_LOG_PATH and _OLLAMA_SERVE_LOG_PATH.is_file():
                    try:
                        # 마지막 일부만 읽기(너무 길어질 수 있음)
                        txt = _OLLAMA_SERVE_LOG_PATH.read_text(encoding="utf-8", errors="ignore")
                        tail = txt[-1200:].strip()
                    except Exception:
                        tail = ""
                msg = f"[UI] Ollama 자동 실행 실패: 프로세스가 즉시 종료됨(exit={code})."
                if _OLLAMA_SERVE_LOG_PATH:
                    msg += f" 로그: {_OLLAMA_SERVE_LOG_PATH}"
                print(msg)
                if tail:
                    print("[UI] Ollama 로그(마지막 일부):")
                    print(tail)

        QTimer.singleShot(1200, _check_exit)
    except Exception as e:
        _OLLAMA_SERVE_PROC = None
        print(f"[UI] Ollama 자동 실행 실패: {e}")


def _start_db_hydrate_background() -> None:
    """P2 hydrate(products 백필)를 백그라운드 스레드에서 실행한다.

    DB init/migration 완료 후 호출해야 하며, UI 스레드를 블로킹하지 않는다.
    """
    def _run() -> None:
        try:
            from javstory.harvest.product_repository import maybe_hydrate_products_v2
            maybe_hydrate_products_v2()
        except Exception as e:
            print(f"[DB] P2 hydrate (background) skipped: {e}")

    threading.Thread(target=_run, daemon=True, name="db-hydrate").start()


def _prewarm_llamacpp_server_bg(delay_seconds: float = 180.0) -> None:
    """앱 시작 후 llama-server 기동 + persona context 계산을 병렬로 미리 수행해
    페르소나 카드 재생성 대기 시간을 줄인다.
    기본 180초 지연으로 라이브러리 로딩 완료 후 시작 (JAVSTORY_LLAMACPP_PREWARM_DELAY로 조정 가능)."""
    raw = (os.environ.get("JAVSTORY_LLAMACPP_PREWARM", "0") or "0").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return

    try:
        delay_seconds = float(os.environ.get("JAVSTORY_LLAMACPP_PREWARM_DELAY", str(delay_seconds)) or delay_seconds)
    except (TypeError, ValueError):
        pass

    def _run() -> None:
        import time
        time.sleep(delay_seconds)
        from javstory.analytics.persona_card import persona_card_model_from_env
        model = persona_card_model_from_env()
        print(f"[Prewarm] 시작 (server preset={model}, context 병렬 계산)")

        def _server() -> None:
            try:
                from javstory.llm.llamacpp_backend import (
                    ensure_llamacpp_server_ready,
                    llamacpp_idle_shutdown_enabled,
                )

                if llamacpp_idle_shutdown_enabled():
                    print("[Prewarm] idle shutdown 활성 — llama-server 선기동 생략 (호출 시 기동)")
                    return
                ensure_llamacpp_server_ready({"model": model})
                print("[Prewarm] llama-server 준비 완료")
            except Exception as exc:
                print(f"[Prewarm] llama-server 실패 (무시): {exc}")

        def _context() -> None:
            try:
                from javstory.analytics.persona_card import prewarm_persona_context
                prewarm_persona_context()
            except Exception as exc:
                print(f"[Prewarm] persona context 실패 (무시): {exc}")

        def _intent() -> None:
            try:
                from javstory.persona.intent_classifier import prewarm_intent_classifier
                prewarm_intent_classifier()
            except Exception as exc:
                print(f"[Prewarm] intent classifier 실패 (무시): {exc}")

        t_srv = threading.Thread(target=_server, daemon=True, name="prewarm-server")
        t_ctx = threading.Thread(target=_context, daemon=True, name="prewarm-context")
        t_int = threading.Thread(target=_intent, daemon=True, name="prewarm-intent")
        t_srv.start()
        t_ctx.start()
        t_int.start()

    threading.Thread(target=_run, daemon=True, name="llamacpp-prewarm").start()


def create_engine(app) -> QQmlApplicationEngine:
    """QQmlApplicationEngine을 생성하고 Python 모델을 context에 등록한다."""
    from javstory.harvest.database import init_and_upgrade_db

    db_boot = init_and_upgrade_db()
    if not db_boot.read_only:
        _start_db_hydrate_background()

    if db_boot.read_only:
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.warning(
            None,
            "DB 마이그레이션 실패 (읽기 전용)",
            db_boot.message,
        )
    try:
        from javstory.translation.story_grok_module import migrate_story_context_cache_files
        migrate_story_context_cache_files()
    except Exception:
        pass

    _font_path = Path(__file__).resolve().parent / "fonts" / "MaterialSymbolsRounded.ttf"
    if _font_path.is_file():
        from PySide6.QtGui import QFontDatabase
        fid = QFontDatabase.addApplicationFont(str(_font_path))
        if fid >= 0:
            families = QFontDatabase.applicationFontFamilies(fid)
            print(f"[UI] Material Symbols font registered: {families}")
        else:
            print("[UI] Material Symbols font registration failed")

    engine = QQmlApplicationEngine()

    engine.addImportPath(str(_QML_DIR))

    from gui.models.dashboard_model import DashboardModel
    from gui.models.harvest_model import HarvestModel
    from gui.models.processing_model import ProcessingModel
    from gui.models.library_model import LibraryModel
    from gui.models.highlight_queue_model import HighlightQueueController
    from gui.models.preview_queue_model import PreviewQueueController
    from gui.models.montage_queue_model import MontageQueueController
    from gui.models.embedding_queue_model import EmbeddingQueueController
    from gui.models.settings_model import SettingsModel
    from gui.models.folder_explorer_model import FolderExplorerModel
    from gui.models.translation_queue_model import TranslationQueueController
    from gui.models.player_model import PlayerModel
    from gui.models.insight_model import InsightModel
    from gui.models.actress_model import ActressModel
    from gui.folder_binding_inbox_store import FolderBindingInboxStore

    ctx = engine.rootContext()

    print("[UI] Initializing DashboardModel...")
    dashboard = DashboardModel(parent=app)
    print("[UI] Initializing HarvestModel...")
    harvest = HarvestModel(parent=app)
    print("[UI] Initializing ProcessingModel...")
    processing = ProcessingModel(parent=app)
    print("[UI] Initializing LibraryModel...")
    library = LibraryModel(parent=app)
    print("[UI] Initializing HighlightQueueController...")
    highlight_queue = HighlightQueueController(parent=app)
    print("[UI] Initializing PreviewQueueController...")
    preview_queue = PreviewQueueController(parent=app)
    print("[UI] Initializing MontageQueueController...")
    montage_queue = MontageQueueController(parent=app)
    print("[UI] Initializing EmbeddingQueueController...")
    embedding_queue = EmbeddingQueueController(parent=app)
    print("[UI] Initializing SettingsModel...")
    settings = SettingsModel(parent=app)
    print("[UI] Initializing FolderExplorerModel...")
    folder_explorer = FolderExplorerModel(parent=app)
    print("[UI] Initializing TranslationQueueController...")
    translation_queue = TranslationQueueController(parent=app)
    print("[UI] Initializing PlayerModel...")
    player_model = PlayerModel(parent=app)
    print("[UI] Initializing InsightModel...")
    insight_model = InsightModel(parent=app)
    print("[UI] Initializing ActressModel...")
    actress_model = ActressModel(parent=app)
    folder_binding_inbox_store = FolderBindingInboxStore(parent=app)

    # llama-server는 LLM 작업 시에만 기동 (JAVSTORY_LLAMACPP_PREWARM=1 일 때만 선기동)
    _prewarm_llamacpp_server_bg()

    # 로컬 번역(Ollama) 설정이면 앱 시작 시 `ollama serve` 자동 실행
    # (앱/엔진 초기화 타이밍 이슈를 피하려고 다음 이벤트 루프로 지연)
    QTimer.singleShot(0, lambda: _maybe_start_ollama_serve(app))

    print("[UI] Registering context properties...")
    ctx.setContextProperty("DashboardModel", dashboard)
    ctx.setContextProperty("HarvestModel", harvest)
    ctx.setContextProperty("ProcessingModel", processing)
    ctx.setContextProperty("LibraryModel", library)
    ctx.setContextProperty("HighlightQueue", highlight_queue)
    ctx.setContextProperty("PreviewQueue", preview_queue)
    ctx.setContextProperty("MontageQueue", montage_queue)
    ctx.setContextProperty("EmbeddingQueue", embedding_queue)
    ctx.setContextProperty("SettingsModel", settings)
    ctx.setContextProperty("FolderExplorerModel", folder_explorer)
    ctx.setContextProperty("ActressModel", actress_model)
    ctx.setContextProperty("TranslationQueue", translation_queue)
    ctx.setContextProperty("FolderBindingInboxStore", folder_binding_inbox_store)
    ctx.setContextProperty("PlayerModel", player_model)
    ctx.setContextProperty("InsightModel", insight_model)
    ctx.setContextProperty("dbReadOnly", bool(db_boot.read_only))
    ctx.setContextProperty("dbBootMessage", db_boot.message or "")

    # Settings ↔ Harvest 옵션 동기화 (특히 Grok 스토리 맥락)
    try:
        harvest.grokEnabled = bool(settings.grokEnabled)
        # 설정 → 수집
        settings.grokEnabledChanged.connect(
            lambda: setattr(harvest, "grokEnabled", bool(settings.grokEnabled))
        )
        # 수집 → 설정 (양방향)
        harvest.grokEnabledChanged.connect(
            lambda: setattr(settings, "grokEnabled", bool(harvest.grokEnabled))
        )
    except Exception:
        pass

    try:
        harvest.productHarvested.connect(library.refreshAddedProduct)
    except Exception:
        pass

    # 라이브러리 탭 진입 전에도 백그라운드에서 목록 로드를 시작한다.
    QTimer.singleShot(0, library.reload)

    from gui.folder_watch_service import FolderMoveWatchService

    folder_watch = FolderMoveWatchService(library, parent=app)
    library.summariesReloaded.connect(folder_watch.refresh_paths_from_db)
    QTimer.singleShot(2500, folder_watch.refresh_paths_from_db)
    ctx.setContextProperty("FolderWatchService", folder_watch)

    # Harvest 수집/크롤링 로그를 실행 CMD(터미널)에도 출력 (QML 로그와 동일 내용)
    try:
        harvest.logMessage.connect(lambda msg: print(msg, flush=True))
    except Exception:
        pass

    # 하이라이트 큐 로그를 실행 터미널에 출력
    try:
        highlight_queue.logMessage.connect(lambda msg: print(msg, flush=True))
    except Exception:
        pass

    # 프리뷰 큐 로그를 실행 터미널에 출력
    try:
        preview_queue.logMessage.connect(lambda msg: print(msg, flush=True))
    except Exception:
        pass

    # 몽타주 큐 로그를 실행 터미널에 출력
    try:
        montage_queue.logMessage.connect(lambda msg: print(msg, flush=True))
    except Exception:
        pass

    # 임베딩 큐 로그를 실행 터미널에 출력
    try:
        embedding_queue.logMessage.connect(lambda msg: print(msg, flush=True))
    except Exception:
        pass

    print(f"[UI] Loading QML from: {_QML_DIR / 'main.qml'}")
    engine.load(QUrl.fromLocalFile(str(_QML_DIR / "main.qml")))

    if not engine.rootObjects():
        print("[FATAL] main.qml 로드 실패", file=sys.stderr)
        sys.exit(1)

    # Mica 효과 (Windows 11)
    # 일부 환경에서 즉시 적용 시 창 표시 전에 멈추는 경우가 있어, 이벤트 루프 이후로 지연한다.
    QTimer.singleShot(0, lambda: _apply_mica(engine))

    def _flush_queue_states() -> None:
        for obj in (
            translation_queue,
            highlight_queue,
            preview_queue,
            montage_queue,
            embedding_queue,
        ):
            try:
                fn = getattr(obj, "flushQueueState", None)
                if callable(fn):
                    fn()
            except Exception:
                pass

    app.aboutToQuit.connect(_flush_queue_states)

    # 5분마다 취향 분석 배치 자동 실행 (앱 유휴 시)
    _batch_timer = QTimer(app)
    _batch_timer.setInterval(5 * 60 * 1000)  # 5분
    _batch_timer.setSingleShot(False)

    def _run_batch_if_idle():
        if insight_model.isBatchRunning:
            return
        try:
            from javstory.analytics.batch_worker import run_batch_in_thread
            run_batch_in_thread(done_callback=lambda r: print(
                f"[Analytics] 배치 동기화 완료: {r.get('synced', 0)}건"
            ) if not r.get("skipped") else None)
        except Exception as e:
            print(f"[Analytics] 배치 실패: {e}")

    _batch_timer.timeout.connect(_run_batch_if_idle)
    # 앱 시작 10분 후 첫 배치 실행
    QTimer.singleShot(10 * 60 * 1000, _batch_timer.start)

    # InsightModel 로그 → 터미널
    try:
        insight_model.logMessage.connect(lambda msg: print(msg))
    except Exception:
        pass

    return engine


def _apply_mica(engine: QQmlApplicationEngine) -> None:
    if sys.platform != "win32":
        return
    if os.environ.get("JAVSTORY_DISABLE_MICA", "").strip().lower() in {"1", "true", "yes"}:
        print("[UI] Mica 비활성화: JAVSTORY_DISABLE_MICA")
        return
    try:
        import win32mica
        import darkdetect

        root = engine.rootObjects()[0]
        hwnd = int(root.winId())
        mode = (
            win32mica.MicaTheme.DARK
            if darkdetect.isDark()
            else win32mica.MicaTheme.LIGHT
        )
        win32mica.ApplyMica(hwnd, mode)
    except Exception as exc:
        print(f"[UI] Mica 효과 적용 실패 (무시됨): {exc}")

"""운영 GUI — QML 엔진 초기화 및 PySide6 모델 등록 (`main.py` → `create_engine`).

PyQt6 Fluent (`gui/main_window.py`) 는 사용하지 않음. → `docs/architecture/ENTRYPOINTS.md`
"""

from __future__ import annotations

import os
import re
import sys
import atexit
import subprocess
from pathlib import Path

import shutil
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtQml import QQmlApplicationEngine

_QML_DIR = Path(__file__).resolve().parent / "qml"

_OLLAMA_SERVE_PROC: subprocess.Popen | None = None
_OLLAMA_SERVE_LOG_PATH: Path | None = None

# job_id가 파일명 기반이면 ')'가 포함될 수 있어, 마지막 '(job=...)'를 통째로 잡는다.
_RE_MOSAIC_JOB = re.compile(r"\(job=(.+)\)\s*$")


class _MosaicConsoleRenderer:
    """모자이크 큐 로그를 터미널에 job별 1줄로 갱신 출력하는 렌더러."""

    def __init__(self) -> None:
        self._lines: dict[str, str] = {}
        self._order: list[str] = []
        self._last_render_n = 0
        raw = (os.environ.get("JAVSTORY_MOSAIC_CONSOLE_OVERWRITE", "1") or "1").strip().lower()
        self._overwrite = raw not in {"0", "false", "no", "off"}

        # Windows 콘솔 ANSI(VT) 활성화 시도 (실패해도 일반 출력은 동작)
        try:
            if sys.platform == "win32":
                os.system("")
        except Exception:
            pass

    def update(self, job_id: str, text: str) -> None:
        if job_id not in self._lines:
            self._order.append(job_id)
        self._lines[job_id] = text
        self.render()

    def render(self) -> None:
        try:
            cols, _ = shutil.get_terminal_size((120, 30))
            max_w = max(40, cols - 1)
            n = len(self._order)

            # n==1이면 단일 작업 — 같은 줄을 \r로 갱신
            if n == 1:
                jid = self._order[0]
                line = self._lines.get(jid, "") or ""
                content = _RE_MOSAIC_JOB.sub("", line).strip()
                tag = f" [{jid[-8:]}]"
                display_line = content[:max(10, max_w - len(tag))] + tag
                if self._overwrite:
                    sys.stdout.write(f"\x1b[2K\r{display_line}")
                    sys.stdout.flush()
                else:
                    sys.stdout.write(line + "\n")
                    sys.stdout.flush()
                self._last_render_n = 1
                return

            # 다중 작업: 이전 렌더 라인 수만큼 커서를 위로 이동
            if self._last_render_n > 0:
                sys.stdout.write(f"\x1b[{self._last_render_n}F")
            for jid in self._order:
                line = self._lines.get(jid, "") or ""
                content = _RE_MOSAIC_JOB.sub("", line).strip()
                tag = f" [{jid[-8:]}]"
                display_line = content[:max(10, max_w - len(tag))] + tag
                sys.stdout.write(f"\x1b[2K\r{display_line}\n")
            sys.stdout.flush()
            self._last_render_n = n
        except Exception:
            try:
                for jid in self._order:
                    print(self._lines.get(jid, ""))
            except Exception:
                pass


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


def create_engine(app) -> QQmlApplicationEngine:
    """QQmlApplicationEngine을 생성하고 Python 모델을 context에 등록한다."""
    from javstory.harvest.database import init_and_upgrade_db

    db_boot = init_and_upgrade_db()
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
    from gui.models.mosaic_queue_model import MosaicQueueController
    from gui.models.settings_model import SettingsModel
    from gui.models.folder_explorer_model import FolderExplorerModel
    from gui.models.translation_queue_model import TranslationQueueController
    from gui.models.player_model import PlayerModel
    from gui.models.insight_model import InsightModel
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
    print("[UI] Initializing MosaicQueueController...")
    mosaic_queue = MosaicQueueController(parent=app)
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
    folder_binding_inbox_store = FolderBindingInboxStore(parent=app)

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
    ctx.setContextProperty("MosaicQueue", mosaic_queue)
    ctx.setContextProperty("SettingsModel", settings)
    ctx.setContextProperty("FolderExplorerModel", folder_explorer)
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

    # 모자이크 제거 큐 로그를 실행 터미널에 출력
    try:
        _mosaic_renderer = _MosaicConsoleRenderer()

        def _on_mosaic_log(msg: str) -> None:
            s = str(msg or "")
            if s.startswith("[LADA]"):
                return
            m = _RE_MOSAIC_JOB.search(s)
            if not m:
                # started/done/error 로그는 "job=..."로 들어오므로 별도 파싱
                m2 = re.search(r"\bjob=(.+)\s*$", s)
                if m2:
                    jid2 = m2.group(1).strip()
                    _mosaic_renderer.update(
                        jid2, s if f"(job={jid2})" in s else f"{s} (job={jid2})"
                    )
                    return
                print(s, flush=True)
                return
            _mosaic_renderer.update(m.group(1), s)

        mosaic_queue.logMessage.connect(_on_mosaic_log)
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
            mosaic_queue,
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
            ))
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

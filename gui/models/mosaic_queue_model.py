"""모자이크 제거(Mosaic Removal) 전역 큐 모델 (LADA-CLI 연동 대기)."""

from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import (
    QObject,
    Property,
    Signal,
    Slot,
    QAbstractListModel,
    QCoreApplication,
    QModelIndex,
    Qt,
    QThread,
    QTimer,
)
from gui.utils.queue_persistence import clear_queue_state, load_queue_state, save_queue_state
from javstory.utils.ffmpeg_path import get_ffprobe

PERSIST_NAME = "mosaic"


def _ascii_bar(pct: int, width: int = 12) -> str:
    p = max(0, min(100, int(pct)))
    f = int(round(width * p / 100.0))
    f = min(width, max(0, f))
    return "[" + ("=" * f) + (" " * (width - f)) + f"]{p:3d}%"


def _pipe_bar(pct: int, width: int = 20) -> str:
    """터미널 0%|     | 스타일 바."""
    p = max(0, min(100, int(pct)))
    f = int(round(width * p / 100.0))
    f = min(width, max(0, f))
    return ("█" * f) + (" " * (width - f))


def _format_hms(sec: float) -> str:
    s = int(max(0.0, sec + 0.5))
    h, r = divmod(s, 3600)
    m, s2 = divmod(r, 60)
    if h:
        return f"{h:d}:{m:02d}:{s2:02d}"
    return f"{m:02d}:{s2:02d}"


def _parse_hmsish_to_seconds(s: str) -> float | None:
    """'00:12:34', '0:12', '12.5' 등을 초로."""
    t = (s or "").strip()
    if not t:
        return None
    try:
        if re.match(r"^[0-9]+(\.[0-9]+)?$", t):
            return float(t)
    except Exception:
        pass
    parts = t.replace(",", ".").split(":")
    try:
        if len(parts) == 1:
            return float(parts[0])
        if len(parts) == 2:
            return int(parts[0]) * 60.0 + float(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600.0 + int(parts[1]) * 60.0 + float(parts[2])
    except Exception:
        return None
    return None


def _estimate_remaining_seconds(
    fcur: int | None,
    ftotal: int | None,
    fps: str,
    elapsed_s: float,
) -> float | None:
    if fcur is None or ftotal is None or ftotal <= 0:
        return None
    rem_f = float(ftotal - fcur)
    if rem_f <= 0:
        return 0.0
    try:
        if fps and float(fps) > 1e-6:
            return rem_f / float(fps)
    except Exception:
        pass
    if fcur > 0 and elapsed_s > 0.1:
        return (rem_f / float(fcur)) * float(elapsed_s)
    return None


def _ffprobe_path() -> str:
    return get_ffprobe()


def _probe_video_duration_sec(path: str) -> float | None:
    """ffprobe로 재생 길이(초). LADA 로그에 time=만 있을 때 진행률 계산에 사용."""
    p = (path or "").strip()
    if not p or not Path(p).is_file():
        return None
    exe = _ffprobe_path()
    try:
        kw: dict = {"capture_output": True, "text": True, "timeout": 60}
        if os.name == "nt":
            kw["creationflags"] = subprocess.CREATE_NO_WINDOW
        r = subprocess.run(
            [
                exe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                p,
            ],
            **kw,
        )
        if r.returncode != 0:
            return None
        raw = (r.stdout or "").strip()
        if not raw:
            return None
        line = raw.splitlines()[-1].strip()
        v = float(line)
        if 0.05 < v < 86400.0 * 7:
            return v
    except Exception:
        return None
    return None


def _parse_lada_ffmpeg_line(s: str) -> dict:
    """LADA(tqdm·ffmpeg) 진행 줄 — 공백/콜론 변형, UTF-8 터지지 않는 느슨한 파싱."""
    t = s or ""
    d: dict = {
        "fcur": None,
        "ftotal": None,
        "fps": "",
        "speed": "",
        "pos_sec": None,
        "eta_str": "",
        "tqdm_rem": None,  # tqdm `<` 뒤 원문
    }
    m = re.search(r"(?i)frame\s*[=:：]\s*(\d+)\s*[/／]\s*(\d+)", t)
    if m:
        d["fcur"], d["ftotal"] = int(m.group(1)), int(m.group(2))
    else:
        m = re.search(r"(?i)frame\s*[=:：]\s*(\d+)", t)
        if m:
            d["fcur"] = int(m.group(1))
    m = re.search(
        r"(?i)(time|out_time|OUT_TIME)\s*=\s*(\d+):(\d+):([0-9.]+)", t
    )
    if m:
        d["pos_sec"] = int(m.group(2)) * 3600 + int(m.group(3)) * 60 + float(m.group(4))
    m = re.search(r"(?i)\bout_time_ms\s*=\s*(\d+)", t)
    if m and m.group(1).isdigit():
        v = int(m.group(1))
        w = v / 1_000_000.0 if v > 1_000_000 else v / 1000.0
        if d["pos_sec"] is None:
            d["pos_sec"] = float(w)
    m = re.search(r"(?i)fps\s*[=:：\s]+([0-9.]+)", t)
    if m:
        d["fps"] = m.group(1).strip()
    m = re.search(r"(?i)speed\s*[=:：\s]+([0-9.]+)\s*x", t) or re.search(
        r"(?i)\bspeed\s*[=:：\s]+([0-9.]+)(?=\s|$|speed)", t
    )
    if m:
        d["speed"] = m.group(1).strip()
    m = re.search(
        r"(?i)(?<![0-9a-zA-Z/])eta\s*[=:：\s]+([0-9:.\-]+)", t
    )
    if m:
        d["eta_str"] = m.group(1).strip()
    m = re.search(
        r"\[([0-9:./+hms\-]{1,32})\s*<\s*([0-9:./+hms\-]{1,32})(?:,|\])", t, re.I
    )
    if m:
        d["tqdm_rem"] = m.group(2).strip()
    if d.get("fcur") is None and d.get("ftotal") is None:
        m = re.search(
            r"(\d+)\s*/\s*(\d+)\s+\[[0-9:./+hms.\- ]{0,64}<\s*",
            t,
        )
        if m:
            d["fcur"], d["ftotal"] = int(m.group(1)), int(m.group(2))
    return d


def _lada_line_looks_like_progress(s: str) -> bool:
    t = s or ""
    if re.search(r"(?i)frame\s*=", t):
        return True
    if re.search(
        r"(?i)(time|out_time|out_time_ms|fps|speed|eta|bitrate|Lsize|size=)\s*=",
        t,
    ):
        return True
    if re.search(r"(?i)eta\s*=", t) or re.search(
        r"(?i)\[([^\]]*)\s*<", t
    ):
        return True
    if re.search(r"(?i)\d+\s*%\s*\|", t):
        return True
    if re.search(r"(?i)(?:\d+|\d+:\d+:\d+)[<]\s*[\d:./+hms]", t):
        return True
    if re.search(r"(?i)(?:\d+\s*/\s*\d+\s+\[|it/s|iter/s)", t):
        return True
    return False


def _parsed_has_core_fields(d: dict) -> bool:
    return bool(
        d.get("fcur") is not None
        or d.get("ftotal") is not None
        or d.get("pos_sec") is not None
        or (d.get("fps") or "").strip()
        or (d.get("speed") or "").strip()
        or (d.get("eta_str") or "").strip()
        or d.get("tqdm_rem")
    )


def _lada_cli_export_args() -> tuple[str, str, str]:
    """
    lada-cli: --encoder 또는 --encoder-options가 있으면 --encoding-preset은 적용되지 않음.
    NVENC/H264 NVENC는 `--encoding-preset`만 전달하고, AMD `hevc_amf`만 encoder+options.
    반환: (encoder, encoder_options, encoding_preset)
    """
    raw_e = (os.environ.get("JAVSTORY_LADA_ENCODER", "hevc_nvenc") or "hevc_nvenc").strip()
    enc = (raw_e or "hevc_nvenc").lower()
    pr = (os.environ.get("JAVSTORY_LADA_ENCODING_PRESET", "hevc-nvidia-gpu-balanced") or "hevc-nvidia-gpu-balanced").strip()

    if enc == "hevc_amf":
        if pr == "hevc-nvidia-gpu-uhq" or "uhq" in pr:
            opts = "-usage high_quality -rc hqvbr -qvbr_quality_level 22"
        elif pr == "h264-nvidia-gpu-fast":
            opts = "-usage transcoding -rc qvbr -qvbr_quality_level 32"
        else:
            opts = "-usage transcoding -rc qvbr -qvbr_quality_level 28"
        return "hevc_amf", opts, ""

    if enc == "h264_nvenc":
        if pr == "h264-nvidia-gpu-fast":
            return "", "", "h264-nvidia-gpu-fast"
        if pr == "hevc-nvidia-gpu-uhq":
            return "", "", "h264-cpu-uhq"
        return "", "", "h264-nvidia-gpu-fast"

    if not pr.startswith("hevc-"):
        pr = "hevc-nvidia-gpu-balanced"
    return "", "", pr


@dataclass
class _Job:
    job_id: str
    product_code: str
    video_path: str
    output_dir: str
    status: str  # queued|running|done|error
    progress: int
    message: str
    created_at_ms: int


class MosaicQueueListModel(QAbstractListModel):
    JobIdRole = Qt.ItemDataRole.UserRole + 1
    ProductCodeRole = Qt.ItemDataRole.UserRole + 2
    VideoNameRole = Qt.ItemDataRole.UserRole + 3
    StatusRole = Qt.ItemDataRole.UserRole + 4
    ProgressRole = Qt.ItemDataRole.UserRole + 5
    MessageRole = Qt.ItemDataRole.UserRole + 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[_Job] = []

    def roleNames(self):
        return {
            self.JobIdRole: b"jobId",
            self.ProductCodeRole: b"productCode",
            self.VideoNameRole: b"videoName",
            self.StatusRole: b"status",
            self.ProgressRole: b"progress",
            self.MessageRole: b"message",
        }

    def rowCount(self, parent=QModelIndex()):
        return len(self._items)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        it = self._items[index.row()]
        if role == self.JobIdRole:
            return it.job_id
        if role == self.ProductCodeRole:
            return it.product_code
        if role == self.VideoNameRole:
            return os.path.basename(it.video_path)
        if role == self.StatusRole:
            return it.status
        if role == self.ProgressRole:
            return int(it.progress)
        if role == self.MessageRole:
            return it.message
        return None

    def _append(self, job: _Job) -> None:
        start = len(self._items)
        self.beginInsertRows(QModelIndex(), start, start)
        self._items.append(job)
        self.endInsertRows()

    def _update_by_id(self, job_id: str, **kwargs) -> None:
        for i, it in enumerate(self._items):
            if it.job_id == job_id:
                for k, v in kwargs.items():
                    if hasattr(it, k):
                        setattr(it, k, v)
                idx = self.index(i, 0)
                self.dataChanged.emit(idx, idx)
                return

    def _remove_by_id(self, job_id: str) -> bool:
        for i, it in enumerate(self._items):
            if it.job_id == job_id:
                self.beginRemoveRows(QModelIndex(), i, i)
                self._items.pop(i)
                self.endRemoveRows()
                return True
        return False

    def _clear_finished(self) -> int:
        to_del = []
        for i, it in enumerate(self._items):
            if it.status in {"done", "error"}:
                to_del.append(i)
        if not to_del:
            return 0
        count = 0
        for i in sorted(to_del, reverse=True):
            self.beginRemoveRows(QModelIndex(), i, i)
            self._items.pop(i)
            self.endRemoveRows()
            count += 1
        return count

    def _all(self) -> list:
        return list(self._items)

    def _replace_all(self, jobs) -> None:
        self.beginResetModel()
        self._items = list(jobs)
        self.endResetModel()


class MosaicQueueController(QObject):
    _instance = None

    @staticmethod
    def instance() -> "MosaicQueueController | None":
        return MosaicQueueController._instance

    queueCountChanged = Signal()
    runningCountChanged = Signal()
    pendingCountChanged = Signal()
    toastMessage = Signal(str, str)
    logMessage = Signal(str)
    queueChanged = Signal()
    # 큐에 넣기만 하고 "시작" 누르기 전에는 _pump 하지 않음
    processingEnabledChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        MosaicQueueController._instance = self
        self._model = MosaicQueueListModel(self)
        self._running: Dict[str, object] = {}
        self._processing_enabled: bool = False
        self._job_mono_t0: Dict[str, float] = {}
        raw = (os.environ.get("JAVSTORY_LADA_PARALLEL", "") or "").strip()
        try:
            n = int(raw) if raw else 2
        except ValueError:
            n = 2
        self._max_parallel = max(1, min(3, n))
        self._last_progress_log: Dict[str, int] = {}
        # tqdm 원문 진행 로그를 너무 자주 emit하면 터미널/복사 시 "주르륵" 쌓여 보인다 → job별 throttling
        self._last_raw_emit_ms: Dict[str, int] = {}
        # job_id -> ffprobe duration(초); time= 기반 진행률 / 멀티패스 구간
        self._job_duration_sec: Dict[str, float] = {}
        self._job_pass: Dict[str, tuple[int, int]] = {}  # (현재 pass, 총 pass)
        self._persist_timer = QTimer(self)
        self._persist_timer.setSingleShot(True)
        self._persist_timer.setInterval(350)
        self._persist_timer.timeout.connect(self._flush_persist)
        QTimer.singleShot(0, self, self._load_persisted)

    @Property(QObject, constant=True)
    def queue(self):
        return self._model

    @Property(int, notify=queueCountChanged)
    def queueCount(self) -> int:
        return self._model.rowCount()

    @Property(int, notify=runningCountChanged)
    def runningCount(self) -> int:
        return len(self._running)

    @Property(int, notify=pendingCountChanged)
    def pendingCount(self) -> int:
        n = 0
        for it in self._model._items:
            if it.status in {"queued", "running"}:
                n += 1
        return n

    @Property(int, notify=queueChanged)
    def notStartedCount(self) -> int:
        return sum(1 for it in self._model._items if it.status == "queued")

    @Property(bool, notify=processingEnabledChanged)
    def processingEnabled(self) -> bool:
        return bool(self._processing_enabled)

    def _emit_counts(self) -> None:
        self.queueCountChanged.emit()
        self.runningCountChanged.emit()
        self.pendingCountChanged.emit()
        self.queueChanged.emit()
        self._schedule_persist()

    def _schedule_persist(self) -> None:
        app = QCoreApplication.instance()
        if app and QThread.currentThread() is not app.thread():
            QTimer.singleShot(0, self, self._schedule_persist)
            return
        self._persist_timer.start()

    def _flush_persist(self) -> None:
        try:
            rows: List[Dict[str, Any]] = []
            for it in self._model._all():
                if (it.status or "") not in {"queued", "running"}:
                    continue
                d = asdict(it)
                d["status"] = "queued" if d.get("status") == "running" else d.get("status", "queued")
                rows.append(d)
            if not rows:
                clear_queue_state(PERSIST_NAME)
                return
            save_queue_state(PERSIST_NAME, {"items": rows})
        except Exception as e:
            self.logMessage.emit(f"[MosaicQueue] persist failed: {e}")

    def flushQueueState(self) -> None:
        self._flush_persist()

    def _load_persisted(self) -> None:
        try:
            data = load_queue_state(PERSIST_NAME)
            if not data:
                return
            raw = data.get("items")
            if not isinstance(raw, list) or not raw:
                return
            jobs: list[_Job] = []
            for it in raw:
                if not isinstance(it, dict) or (it.get("status") or "") == "error":
                    continue
                pc = (it.get("product_code") or "").strip().upper()
                vp = (it.get("video_path") or "").strip()
                if not pc or not vp:
                    try:
                        pc2 = Path(vp).stem.strip().upper()
                    except Exception:
                        pc2 = ""
                    if pc2:
                        pc = pc2
                    if not pc or not vp:
                        continue
                jid = str(it.get("job_id") or "").strip() or f"mopa_{pc}_{it.get('created_at_ms', 0)}"
                odir = (it.get("output_dir") or "").strip() or str(Path(vp).parent)
                jobs.append(
                    _Job(
                        job_id=str(jid)[:200],
                        product_code=pc,
                        video_path=vp,
                        output_dir=odir,
                        status="queued",
                        progress=0,
                        message="이어서 하기 — 대시보드에서 시작",
                        created_at_ms=int(it.get("created_at_ms") or 0) or int(time.time() * 1000),
                    )
                )
            if not jobs:
                return
            self._processing_enabled = False
            self._model._replace_all(jobs)
            self._emit_counts()
            self.toastMessage.emit(
                f"[모자이크 제거] {len(jobs)}건 복원됨. '이어서 하기'로 처리를 시작하세요.",
                "info",
            )
            self.logMessage.emit(
                f"[MosaicQueue] restored {len(jobs)} job(s) from disk (이어서 하기로 진행)"
            )
        except Exception as e:
            self.logMessage.emit(f"[MosaicQueue] load persisted failed: {e}")

    @Slot()
    def resume(self) -> None:
        """저장된 모자이크 대기를 이어서 처리(시작과 동일)."""
        for it in self._model._all():
            if it.status == "running" and it.job_id not in self._running:
                self._model._update_by_id(
                    it.job_id, status="queued", message="이어서 하기", progress=0
                )
        self.startQueue()

    def _sync_processing_idle(self) -> None:
        if self._running:
            return
        if any(it.status == "queued" for it in self._model._items):
            return
        if not self._processing_enabled:
            return
        self._processing_enabled = False
        self.processingEnabledChanged.emit()

    @Slot()
    def startQueue(self) -> None:
        if not any(it.status == "queued" for it in self._model._items):
            self.toastMessage.emit("[모자이크 제거] 대기 중인 항목이 없습니다.", "info")
            return
        if not self._processing_enabled:
            self._processing_enabled = True
            self.processingEnabledChanged.emit()
        self._pump()

    @Slot(str, str)
    def enqueue(self, product_code: str, video_path: str) -> None:
        from javstory.utils.product_code import resolve_product_code_for_video

        pc = resolve_product_code_for_video(video_path, product_code)
        vp = (video_path or "").strip()
        if not vp:
            return

        if not pc:
            pc = resolve_product_code_for_video(vp, None) or "FILE"
        
        # 동일 파일이 queued/running이면 중복 등록 방지
        try:
            for it in reversed(self._model._items):
                if (it.video_path or "").strip().lower() == vp.lower() and it.status in {"queued", "running"}:
                    self.toastMessage.emit(f"[모자이크 제거] 이미 대기/진행 중입니다: {os.path.basename(vp)}", "info")
                    return
        except Exception:
            pass

        job_id = f"mopa_{pc}_{int(time.time() * 1000)}"
        job = _Job(
            job_id=job_id,
            product_code=pc,
            video_path=vp,
            output_dir=str(Path(vp).parent),
            status="queued",
            progress=0,
            message="대기 중",
            created_at_ms=int(time.time() * 1000),
        )
        self._model._append(job)
        self._emit_counts()
        self.toastMessage.emit(f"[모자이크 제거] 큐에 추가됨: {pc} (대시보드에서 '시작'을 눌러 실행)", "success")
        self.logMessage.emit(f"[MosaicQueue] enqueued: {pc} | {os.path.basename(vp)}")
        if self._processing_enabled:
            self._pump()

    def _sync_parallel(self) -> None:
        raw = (os.environ.get("JAVSTORY_LADA_PARALLEL", "") or "").strip()
        try:
            n = int(raw) if raw else self._max_parallel
        except ValueError:
            n = self._max_parallel
        n = max(1, min(3, n))
        if n != self._max_parallel:
            self._max_parallel = n

    def _pump(self) -> None:
        if not self._processing_enabled:
            return
        self._sync_parallel()
        if len(self._running) >= self._max_parallel:
            return
        for it in list(self._model._items):
            if len(self._running) >= self._max_parallel:
                break
            if it.status != "queued":
                continue
            self._start_job(it)

    def _build_output_path(self, source_path: str) -> str:
        p = Path(source_path)
        base = p.with_suffix("")
        out = Path(str(base) + " [모자이크 제거]" + p.suffix)
        if not out.exists():
            return str(out)
        # 중복 시 _1, _2...
        n = 1
        while True:
            cand = Path(str(base) + f" [모자이크 제거]_{n}" + p.suffix)
            if not cand.exists():
                return str(cand)
            n += 1

    def _get_lada_passes(self) -> list[dict]:
        def _env(key: str, default: str) -> str:
            v = (os.environ.get(key, default) or default).strip()
            return v

        def _env_int(key: str, default: int) -> int:
            try:
                return int((os.environ.get(key, str(int(default))) or "").strip())
            except Exception:
                return int(default)

        def _env_bool(key: str, default: bool) -> bool:
            try:
                raw = os.environ.get(key, "1" if default else "0")
                v = (raw or "").strip().lower()
                return v in ("1", "true", "yes", "on")
            except Exception:
                return bool(default)

        passes = max(1, min(3, _env_int("JAVSTORY_LADA_PASSES", 2)))
        out = []
        for i in range(1, passes + 1):
            out.append(
                {
                    "det_model": _env(f"JAVSTORY_LADA_PASS{i}_DET_MODEL", "v4-fast"),
                    "rest_model": _env(f"JAVSTORY_LADA_PASS{i}_REST_MODEL", "basicvsrpp-v1.2"),
                    "max_clip_length": max(20, min(400, _env_int(f"JAVSTORY_LADA_PASS{i}_MAX_CLIP_LENGTH", 180))),
                    "detect_face": _env_bool(f"JAVSTORY_LADA_PASS{i}_DETECT_FACE", False),
                }
            )
        return out

    def _start_job(self, job: _Job) -> None:
        try:
            from gui.workers.mosaic_worker import LadaPassConfig, MosaicRemovalWorker
        except Exception as e:
            self._model._update_by_id(job.job_id, status="error", message=f"워커 로드 실패: {e}")
            self._emit_counts()
            return

        src = (job.video_path or "").strip()
        out_path = self._build_output_path(src)
        passes_raw = self._get_lada_passes()
        passes = [
            LadaPassConfig(
                det_model=str(p.get("det_model") or "v4-fast"),
                rest_model=str(p.get("rest_model") or "basicvsrpp-v1.2"),
                max_clip_length=int(p.get("max_clip_length") or 180),
                detect_face=bool(p.get("detect_face") is True),
            )
            for p in (passes_raw or [])
        ]
        lada_enc, lada_enc_opts, lada_preset = _lada_cli_export_args()
        fp16_raw = (os.environ.get("JAVSTORY_LADA_FP16", "1") or "1").strip().lower()
        fp16 = fp16_raw in ("1", "true", "yes", "on")

        n_passes = max(1, len(passes))
        du = _probe_video_duration_sec(src)
        self._job_duration_sec[job.job_id] = float(du) if du else 0.0
        self._job_pass[job.job_id] = (1, n_passes)

        # 0%면 QML이 indeterminate로만 보이므로, 착수 직후부터 1%로 둬 바가 움직이기 시작한 것처럼 보이게 함
        self._model._update_by_id(job.job_id, status="running", progress=1, message="시작 중...")
        self._job_mono_t0[job.job_id] = time.monotonic()
        self._emit_counts()

        worker = MosaicRemovalWorker(
            source_path=src,
            output_path=out_path,
            passes=passes,
            encoder=lada_enc,
            encoder_options=lada_enc_opts,
            encoding_preset=lada_preset,
            fp16=fp16,
        )
        self._running[job.job_id] = worker
        self._last_progress_log[job.job_id] = -1

        worker.logEmitted.connect(lambda s, jid=job.job_id: self._on_log(jid, s))
        worker.passStarted.connect(lambda cur, total, jid=job.job_id: self._on_pass_started(jid, cur, total))
        worker.finished.connect(lambda ok, msg, outp, jid=job.job_id: self._on_finished(jid, ok, msg, outp))
        worker.start()
        self.logMessage.emit(f"[MosaicQueue] 시작: job={job.job_id}")
        self._emit_counts()

    def _normalize_url_or_path(self, s: str) -> str:
        raw = (s or "").strip()
        if not raw:
            return ""
        # QML DropArea urls: file:///C:/...
        if raw.startswith("file:///"):
            try:
                import urllib.parse

                raw = urllib.parse.unquote(raw.replace("file:///", "", 1))
            except Exception:
                raw = raw.replace("file:///", "", 1)
        return raw

    def _is_video_file(self, p: Path) -> bool:
        ext = (p.suffix or "").lower()
        return ext in {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".m4v", ".ts"}

    @Slot(str)
    def enqueueUrl(self, url_or_path: str) -> None:
        p = self._normalize_url_or_path(url_or_path)
        if not p:
            return
        pp = Path(p)
        if pp.is_dir():
            self.enqueueFolder(str(pp), True)
            return
        if pp.is_file() and self._is_video_file(pp):
            self.enqueue("", str(pp))

    @Slot(str, bool)
    def enqueueFolder(self, folder_path: str, recursive: bool = True) -> None:
        base = Path(self._normalize_url_or_path(folder_path))
        if not base.is_dir():
            self.toastMessage.emit(f"[모자이크 제거] 폴더가 아닙니다: {folder_path}", "warning")
            return
        added = 0
        try:
            it = base.rglob("*") if bool(recursive) else base.glob("*")
            for p in it:
                try:
                    if not p.is_file():
                        continue
                    if not self._is_video_file(p):
                        continue
                    self.enqueue("", str(p))
                    added += 1
                except Exception:
                    continue
        except Exception as e:
            self.toastMessage.emit(f"[모자이크 제거] 폴더 스캔 실패: {e}", "error")
            return

        if added > 0:
            self.toastMessage.emit(
                f"[모자이크 제거] 폴더에서 {added}건 큐에 추가됨 (대시보드에서 '시작'을 눌러 실행)", "success"
            )
        else:
            self.toastMessage.emit("[모자이크 제거] 폴더에서 동영상 파일을 찾지 못했습니다.", "info")

    def _on_log(self, job_id: str, line: str) -> None:
        # LADA 진행 로그는 좌/우 공백을 의미로 쓰는 경우가 있어 strip() 금지
        s = (line or "").rstrip("\r\n")
        if not s or s.startswith(">"):
            return

        # LADA(tqdm) 진행 줄을 "있는 그대로" 터미널에 보여준다.
        # 파싱 실패 시에도 사용자는 원문에서 ETA/프레임을 확인할 수 있어야 한다.
        looks_like_tqdm = ("|" in s and "%" in s) or ("it/s" in s) or ("iter/s" in s)
        if looks_like_tqdm:
            # lada-cli 내부에서 출력하는 '영상 처리 중: ' 접두어 제거 및 공백 정리
            s_clean = s.replace("영상 처리 중:", "").replace("처리 중:", "").strip()
            # UI용 요약
            ui = s_clean
            if len(ui) > 220:
                ui = ui[:220] + "…"
            self._model._update_by_id(job_id, message=ui)
            self._emit_counts()

            now_ms = int(time.time() * 1000)
            last_ms = int(self._last_raw_emit_ms.get(job_id, 0) or 0)
            if now_ms - last_ms >= 250:
                self._last_raw_emit_ms[job_id] = now_ms
                # 터미널용: 너무 길면 자르고, job_id는 식별 가능한 수준으로만 (app.py에서 어차피 또 붙임)
                # app.py의 _on_mosaic_log가 (job=...)를 파싱하므로 형식은 유지
                self.logMessage.emit(f"{s_clean[:120]} (job={job_id})")
            return

        p = _parse_lada_ffmpeg_line(s)
        if not _lada_line_looks_like_progress(s) and not _parsed_has_core_fields(p):
            self.logMessage.emit(f"[LADA] {s}")
            return
        try:
            fcur, ftotal = p.get("fcur"), p.get("ftotal")
            fps, speed = (p.get("fps") or "").strip(), (p.get("speed") or "").strip()
            pos_sec: float | None = p.get("pos_sec")

            t0 = self._job_mono_t0.get(job_id, time.monotonic())
            el_s = time.monotonic() - t0
            elapsed = _format_hms(el_s)

            eta: str = (p.get("eta_str") or "").strip()
            if not eta and p.get("tqdm_rem"):
                tsec = _parse_hmsish_to_seconds(str(p.get("tqdm_rem")).strip())
                if tsec is not None and 0.0 <= tsec < 86400 * 7:
                    eta = _format_hms(tsec)
            if not eta:
                est = _estimate_remaining_seconds(
                    fcur, ftotal, p.get("fps") or "", el_s
                )
                if est is not None and 0.0 <= est < 86400 * 7:
                    eta = f"{_format_hms(est)} (추정)"

            out_pos = ""
            if pos_sec is not None and pos_sec >= 0.0:
                out_pos = _format_hms(float(pos_sec))

            bar_pct = 1
            for it2 in self._model._items:
                if it2.job_id == job_id:
                    bar_pct = max(1, int(it2.progress or 1))
                    break
            dur = float(self._job_duration_sec.get(job_id) or 0.0)
            pc, pt = self._job_pass.get(job_id, (1, 1))
            pt = max(1, int(pt))
            pc = min(pt, max(1, int(pc)))
            if fcur is not None and ftotal and ftotal > 0:
                r = 100.0 * float(fcur) / float(ftotal)
                bar_pct = max(1, min(99, int(round(r))))
            elif dur > 0.05 and pos_sec is not None:
                frac = min(1.0, max(0.0, float(pos_sec) / dur))
                overall = (pc - 1) / float(pt) + (1.0 / float(pt)) * frac
                bar_pct = max(1, min(99, int(round(100.0 * overall))))
            elif fcur is not None and fcur > 0 and (not ftotal) and dur <= 0.0:
                t = 1.0 - 1.0 / (1.0 + float(fcur) / 4000.0)
                bar_pct = max(1, min(95, 1 + int(94.0 * t)))

            parts_ui: list[str] = []
            if fcur is not None and ftotal:
                parts_ui.append(f"{fcur}/{ftotal}f")
            elif fcur is not None:
                parts_ui.append(f"{fcur:,}f")
            if fps:
                parts_ui.append(f"{fps}fps")
            if speed:
                parts_ui.append(f"{speed}x")
            if out_pos:
                parts_ui.append(f"재생 {out_pos}")
            if fcur is not None and ftotal and ftotal > 0 and fcur < ftotal:
                parts_ui.append(f"잔여프레임 {ftotal - fcur}")
            if eta:
                parts_ui.append(f"남은 {eta}")
            msg = " · ".join(parts_ui) if parts_ui else "처리 중..."

            # 터미널 로그: 요청 포맷으로 1줄 진행 표시 (진행률 변화 시에만 출력)
            rem_f: int | None = None
            if ftotal and fcur is not None and isinstance(ftotal, int) and ftotal > 0:
                rf = int(ftotal - fcur)
                if rf >= 0:
                    rem_f = rf
            done_time = out_pos or elapsed
            eta_disp = eta or "-"
            fps_disp = fps
            if not fps_disp and fcur is not None and el_s > 0.1:
                try:
                    fps_disp = f"{(float(fcur) / float(el_s)):.1f}"
                except Exception:
                    fps_disp = ""

            line_cmd = (
                f"[{int(bar_pct):3d}%]|{_pipe_bar(bar_pct, width=20)}| "
                f"경과: {elapsed} | 남음: {eta_disp} | 속도: {fps_disp or '-'}fps"
                f" (job={job_id})"
            )

            self._model._update_by_id(job_id, message=msg, progress=bar_pct)
            self._emit_counts()
            step = int(bar_pct)
            last = int(self._last_progress_log.get(job_id, -1))
            if step != last:
                self._last_progress_log[job_id] = step
                self.logMessage.emit(line_cmd)
        except Exception:
            self.logMessage.emit(f"[LADA] {s}")

    def _on_pass_started(self, job_id: str, current_pass: int, total_passes: int) -> None:
        try:
            cur = int(current_pass)
            total = max(1, int(total_passes))
        except Exception:
            cur, total = 1, 1
        base = int((cur - 1) / total * 100) if total else 0
        # Pass 1/2 같은 경우 base가 0이라 UI가 '안 차는' 것처럼 보일 수 있어 최소 1%를 부여
        if base <= 0 and total > 0:
            base = 1
        t0 = self._job_mono_t0.get(job_id, time.monotonic())
        elapsed = _format_hms(time.monotonic() - t0)
        bar = _ascii_bar(base, width=14)
        self._model._update_by_id(job_id, progress=base, message=f"Pass {cur}/{total} 실행 중")
        self._job_pass[job_id] = (cur, total)
        self.logMessage.emit(
            f"Pass {cur}/{total} 시작 | 경과: {elapsed} (job={job_id})"
        )
        self._emit_counts()

    def _on_finished(self, job_id: str, success: bool, message: str, output_path: str) -> None:
        # job snapshot (DB 업데이트/라이브러리 갱신용)
        job_pc = ""
        try:
            for it in list(self._model._items):
                if it.job_id == job_id:
                    job_pc = (it.product_code or "").strip().upper()
                    break
        except Exception:
            job_pc = ""

        worker = self._running.pop(job_id, None)
        self._last_progress_log.pop(job_id, None)
        self._last_raw_emit_ms.pop(job_id, None)
        self._job_mono_t0.pop(job_id, None)
        self._job_duration_sec.pop(job_id, None)
        self._job_pass.pop(job_id, None)
        try:
            if worker:
                worker.deleteLater()
        except Exception:
            pass

        if success:
            self._model._update_by_id(job_id, status="done", progress=100, message=message or "완료")
            self.logMessage.emit(f"[MosaicQueue] done: job={job_id} | out={output_path}")

            # 라이브러리 하이라이트(lampMopa)는 DB의 jav_metadata.is_mopa를 사용하므로,
            # 성공 시 해당 품번의 is_mopa를 True로 업데이트하여 즉시 표시되게 한다.
            if job_pc:
                try:
                    from javstory.harvest.database import get_db_session, JAVMetadata

                    session = get_db_session()
                    try:
                        row = session.query(JAVMetadata).filter_by(product_code=job_pc).first()
                        if row:
                            row.is_mopa = True
                            session.commit()
                    finally:
                        try:
                            session.close()
                        except Exception:
                            pass
                except Exception as e:
                    self.logMessage.emit(f"[MosaicQueue] DB is_mopa update failed: {job_pc} | {e}")

                # UI 갱신 (목록/상세)
                try:
                    from gui.models.library_model import LibraryModel

                    lib = LibraryModel.instance()
                    if lib:
                        lib.refreshProduct(job_pc)
                        lib.summariesReloaded.emit()
                except Exception:
                    pass
        else:
            self._model._update_by_id(job_id, status="error", message=message or "실패")
            self.logMessage.emit(f"[MosaicQueue] error: job={job_id} | {message}")
        self._emit_counts()
        self._pump()
        self._sync_processing_idle()

    @Slot(str)
    def removeJob(self, job_id: str) -> None:
        worker = self._running.pop(job_id, None)
        if worker:
            try:
                # MosaicRemovalWorker.stop()
                if hasattr(worker, "stop"):
                    worker.stop()
                worker.terminate()
                worker.wait()
            except Exception:
                pass
            self.logMessage.emit(f"[MosaicQueue] terminated worker: job={job_id}")

        if self._model._remove_by_id(job_id):
            self._job_mono_t0.pop(job_id, None)
            self._job_duration_sec.pop(job_id, None)
            self._job_pass.pop(job_id, None)
            self._emit_counts()
            self._pump()
            self._sync_processing_idle()

    @Slot()
    def clearFinished(self) -> None:
        if self._model._clear_finished() > 0:
            self._emit_counts()

from __future__ import annotations

import codecs
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Signal

from gui.workers.cancellable_thread import CancellableQThread


@dataclass
class LadaPassConfig:
    det_model: str
    rest_model: str
    max_clip_length: int
    detect_face: bool


class MosaicRemovalWorker(CancellableQThread):
    logEmitted = Signal(str)
    passStarted = Signal(int, int)  # current_pass, total_passes
    finished = Signal(bool, str, str)  # success, message, output_path

    def __init__(
        self,
        *,
        source_path: str,
        output_path: str,
        passes: list[LadaPassConfig],
        encoder: str = "",
        encoder_options: str = "",
        encoding_preset: str = "",
        fp16: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self.source_path = str(source_path or "").strip()
        self.output_path = str(output_path or "").strip()
        self.passes = list(passes or [])
        self.encoder = str(encoder or "").strip()
        self.encoder_options = str(encoder_options or "").strip()
        self.encoding_preset = str(encoding_preset or "").strip()
        self.fp16 = bool(fp16)

    def _popen_and_stream(self, cmd: list[str]) -> int:
        self.logEmitted.emit(f"> {' '.join(cmd)}")
        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        # LADA 로그는 환경에 따라 UTF-8/CP949가 섞일 수 있어 기본은 auto로 둔다.
        log_enc = (os.environ.get("JAVSTORY_LADA_LOG_ENCODING", "") or "").strip() or ("auto" if os.name == "nt" else "utf-8")
        self._set_active_proc(
            subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=False,  # tqdm/ffmpeg 진행 줄(\r) 스트리밍을 위해 바이트로 즉시 읽는다
                **kwargs,
            )
        )

        assert self._proc is not None
        assert self._proc.stdout is not None
        out = self._proc.stdout  # bytes stream

        ansi_re = re.compile(rb"\x1b\[[0-9;?]*[ -/]*[@-~]")  # CSI
        buf = b""

        def _decode_line(b: bytes) -> str:
            raw = b or b""
            pref = (log_enc or "auto").strip().lower()
            if pref and pref != "auto":
                try:
                    return raw.decode(pref, errors="replace")
                except Exception:
                    return raw.decode("utf-8", errors="replace")
            # auto: utf-8 먼저, 깨짐(�)이 많으면 cp949로 폴백
            s1 = raw.decode("utf-8", errors="replace")
            bad1 = s1.count("\ufffd")
            if bad1 == 0:
                return s1
            try:
                s2 = raw.decode("cp949", errors="replace")
                bad2 = s2.count("\ufffd")
                return s2 if bad2 < bad1 else s1
            except Exception:
                return s1

        # tqdm·ffmpeg는 진행 줄을 \r만으로 갱신하는 경우가 많다. \n만 기다리면 UI/파싱에 안 올라갈 수 있어
        # \r/\n 둘 다 구분해 '줄' 단위로 방출한다.
        while not self.is_cancelled():
            chunk = out.read1(8192) if hasattr(out, "read1") else out.read(8192)
            if not chunk:
                break
            chunk = ansi_re.sub(b"", chunk)
            buf += chunk
            while True:
                i_n = buf.find(b"\n")
                i_r = buf.find(b"\r")
                cut = -1
                if i_n >= 0:
                    cut = i_n
                if i_r >= 0 and (cut < 0 or i_r < cut):
                    cut = i_r
                if cut < 0:
                    break
                part_b = buf[:cut]
                buf = buf[cut + 1 :]
                s = _decode_line(part_b)
                if (s or "").strip():
                    self.logEmitted.emit(s)

        if not self.is_cancelled():
            tail = _decode_line(buf)
            if (tail or "").strip():
                self.logEmitted.emit(tail)

        try:
            self._proc.stdout.close()
        except Exception:
            pass
        code = int(self._proc.wait())
        self._clear_active_proc()
        return code

    def run(self) -> None:
        try:
            src = self.source_path
            if not src or not Path(src).is_file():
                self.finished.emit(False, "입력 파일이 없습니다.", "")
                return

            if not self.passes:
                self.finished.emit(False, "PASS 설정이 비어 있습니다.", "")
                return

            final_out = Path(self.output_path)
            try:
                final_out.parent.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass

            tmp_paths: list[str] = []

            # multi-pass: each pass output becomes next pass input
            input_file = src
            total = len(self.passes)
            for idx, cfg in enumerate(self.passes):
                if self.is_cancelled():
                    self.finished.emit(False, "작업이 중단되었습니다.", "")
                    return

                pass_num = idx + 1
                self.passStarted.emit(pass_num, total)

                if pass_num == total:
                    out_file = str(final_out)
                else:
                    # intermediate output in same directory
                    stem = final_out.stem
                    out_file = str(final_out.with_name(f"{stem}__temp_pass{pass_num}{final_out.suffix}"))
                    tmp_paths.append(out_file)

                # Windows에서는 PATH에 없을 수 있어 프로젝트 내 tools/lada를 우선 사용
                lada_exe = "lada-cli"
                try:
                    base_dir = Path(__file__).resolve().parents[2]  # .../App/JAVSTORY
                    cand = base_dir / "tools" / "lada" / ("lada-cli.exe" if os.name == "nt" else "lada-cli")
                    if cand.exists():
                        lada_exe = str(cand)
                except Exception:
                    lada_exe = "lada-cli"

                cmd = [
                    lada_exe,
                    "--input",
                    input_file,
                    "--output",
                    out_file,
                    "--mosaic-detection-model",
                    str(cfg.det_model),
                    "--mosaic-restoration-model",
                    str(cfg.rest_model),
                    "--max-clip-length",
                    str(int(cfg.max_clip_length)),
                ]
                if bool(cfg.detect_face):
                    cmd.append("--detect-face-mosaics")

                cmd.append("--fp16" if self.fp16 else "--no-fp16")

                # lada-cli: --encoder 또는 --encoder-options가 있으면 --encoding-preset은 **무시**됨.
                # NVENC: --encoding-preset만. AMD hevc_amf: --encoder + --encoder-options.
                if (self.encoder or "").strip() and (self.encoder_options or "").strip():
                    cmd.extend(["--encoder", (self.encoder or "").strip()])
                    cmd.extend(["--encoder-options", (self.encoder_options or "").strip()])
                elif (self.encoding_preset or "").strip():
                    cmd.extend(["--encoding-preset", (self.encoding_preset or "").strip()])
                elif (self.encoder or "").strip():
                    cmd.extend(["--encoder", (self.encoder or "").strip()])

                rc = self._popen_and_stream(cmd)
                if self.is_cancelled():
                    self.finished.emit(False, "작업이 중단되었습니다.", "")
                    return
                if rc != 0:
                    self.finished.emit(False, f"lada-cli 실패 (code={rc})", "")
                    return

                input_file = out_file

            # cleanup intermediates
            for p in tmp_paths:
                try:
                    Path(p).unlink(missing_ok=True)  # type: ignore[arg-type]
                except TypeError:
                    try:
                        pp = Path(p)
                        if pp.exists():
                            pp.unlink()
                    except Exception:
                        pass
                except Exception:
                    pass

            self.finished.emit(True, "모든 작업 완료!", str(final_out))
        except Exception as e:
            self.finished.emit(False, str(e), "")


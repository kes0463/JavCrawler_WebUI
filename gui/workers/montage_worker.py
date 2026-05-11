from __future__ import annotations

import os
import random
import subprocess
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal as pyqtSignal

from javstory.utils.ffmpeg_path import get_ffmpeg


def _startupinfo_hidden() -> object | None:
    if os.name != "nt":
        return None
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return si


class MontageWorker(QThread):
    """선택된 여러 작품의 하이라이트를 합쳐 몽타주(mp4) 생성."""

    resultReady = pyqtSignal(bool, str, str)  # success, message, output_path
    progressUpdated = pyqtSignal(int, str)  # 0~100 퍼센트 진행률, 상세 메시지

    def __init__(self, product_codes: list[str], output_path: str):
        super().__init__()
        self.product_codes = [(pc or "").strip().upper() for pc in (product_codes or []) if (pc or "").strip()]
        self.output_path = Path(output_path)

    def run(self):
        success = False
        msg = ""
        out_path = ""
        try:
            self.progressUpdated.emit(0, "준비 중...")
            pcs = [pc for pc in self.product_codes if pc]
            if len(pcs) < 2:
                success = False
                msg = "몽타주는 2개 이상의 작품이 필요합니다."
                return

            from javstory.config.app_config import E_MEDIA_ROOT, E_DATA_ROOT, DATA_ROOT

            self.progressUpdated.emit(5, "하이라이트 영상 탐색 중...")
            e_root = Path(E_MEDIA_ROOT)
            legacy_root = Path(DATA_ROOT) / "media"

            highlight_paths: list[Path] = []
            skipped: list[str] = []
            for pc in pcs:
                cand = [
                    e_root / pc / "Highlight" / "highlight.mp4",
                    Path(E_DATA_ROOT) / pc / "Highlight" / "highlight.mp4",
                    Path(E_DATA_ROOT) / "media" / pc / "Highlight" / "highlight.mp4",
                    legacy_root / pc / "Highlight" / "highlight.mp4",
                ]
                hp = next((p for p in cand if p.is_file()), None)
                if hp:
                    highlight_paths.append(hp)
                else:
                    skipped.append(pc)

            if len(highlight_paths) < 2:
                success = False
                msg = "하이라이트가 있는 작품이 2개 미만이라 몽타주를 만들 수 없습니다."
                return

            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            self.progressUpdated.emit(10, "배경음악 선택 중...")

            # BGM 랜덤 선택
            bgm_dir = Path(E_DATA_ROOT) / "bgm"
            bgm_files = []
            try:
                if bgm_dir.is_dir():
                    for ext in ("*.mp3", "*.wav", "*.flac"):
                        bgm_files.extend(list(bgm_dir.glob(ext)))
            except Exception:
                bgm_files = []
            bgm = random.choice(bgm_files) if bgm_files else None

            from javstory.utils.process_limit import ffmpeg_semaphore
            self.progressUpdated.emit(15, "리소스 확보 대기 중...")
            
            with ffmpeg_semaphore:
                with tempfile.TemporaryDirectory(prefix="javstory_montage_") as td:
                    tdir = Path(td)
                    concat_list = tdir / "concat.txt"
                    lines = []
                    for p in highlight_paths:
                        s = str(p).replace("'", r"'\''")
                        lines.append(f"file '{s}'")
                    concat_list.write_text("\n".join(lines) + "\n", encoding="utf-8")

                    self.progressUpdated.emit(20, "FFmpeg 병합 명령어 준비 중...")

                    if bgm:
                        cmd = [
                            get_ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
                            "-stream_loop", "-1", "-i", str(bgm),
                            "-filter_complex", "[0:a]volume=0.30[a0];[1:a]volume=0.75[bgm];[a0][bgm]amix=inputs=2:duration=first:dropout_transition=2[a]",
                            "-map", "0:v:0", "-map", "[a]",
                            "-c:v", "h264_nvenc", "-preset", "p6", "-rc", "vbr_hq", "-cq", "21",
                            "-b:v", "0", "-profile:v", "high", "-pix_fmt", "yuv420p",
                            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                            str(self.output_path),
                        ]
                    else:
                        cmd = [
                            get_ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
                            "-filter:a", "volume=0.30",
                            "-c:v", "h264_nvenc", "-preset", "p6", "-rc", "vbr_hq", "-cq", "21",
                            "-b:v", "0", "-profile:v", "high", "-pix_fmt", "yuv420p",
                            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                            str(self.output_path),
                        ]

                    self.progressUpdated.emit(45, "영상 인코딩 중 (NVENC 가속)...")
                    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, startupinfo=_startupinfo_hidden(), check=False)

            self.progressUpdated.emit(100, "완료!")

            if self.output_path.is_file() and self.output_path.stat().st_size > 0:
                success = True
                msg = "몽타주가 생성되었습니다!"
                if skipped:
                    msg += f" (제외 {len(skipped)}개: 하이라이트 없음)"
                out_path = str(self.output_path.resolve())
            else:
                success = False
                msg = "몽타주 생성에 실패했습니다."
        except Exception as e:
            success = False
            msg = f"에러 발생: {e}"
            out_path = ""
        
        # 종료 직전 시그널 전송
        self.resultReady.emit(success, msg, out_path)


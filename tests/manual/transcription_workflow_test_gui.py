"""
Transcription(STT) 워크플로 테스트용 Tkinter GUI.

stable-ts 단일 경로: ffmpeg 16k mono → Whisper 전사 → 후처리 → `{영상명}.ja.srt`
(`Transcription.engine.process_video_to_segments`)

실행 (프로젝트 루트):

  .\\venv\\Scripts\\python.exe Test\\manual\\transcription_workflow_test_gui.py
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import threading
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from javstory.config import secrets_manager


def _browse_video(var: tk.StringVar) -> None:
    p = filedialog.askopenfilename(
        title="비디오 파일 선택",
        filetypes=[("비디오", "*.mp4 *.mkv *.webm *.avi *.mov"), ("모든 파일", "*.*")],
    )
    if p:
        var.set(p)


def _browse_dir(var: tk.StringVar) -> None:
    p = filedialog.askdirectory(title="작업 폴더 (임시 WAV·중간 SRT)")
    if p:
        var.set(p)


class TranscriptionTestApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("JAVSTORY Transcription 테스트 (stable-ts)")
        self.geometry("900x680")
        self.minsize(620, 480)

        self._cancel_event = threading.Event()
        self._run_lock = threading.Lock()

        secrets_manager.apply_env_to_os()

        self.var_video = tk.StringVar()
        self.var_work = tk.StringVar()
        self.var_model = tk.StringVar(value=os.environ.get("JAVSTORY_WHISPER_MODEL", "large-v2"))
        self.var_download_root = tk.StringVar(value=os.environ.get("JAVSTORY_WHISPER_DOWNLOAD_ROOT", ""))
        self.var_force_rerun = tk.BooleanVar(value=False)
        self.var_copy_std_srt = tk.BooleanVar(value=True)

        pad = {"padx": 8, "pady": 4}

        frm = ttk.LabelFrame(self, text="입력")
        frm.pack(fill=tk.X, **pad)

        r = 0
        ttk.Label(frm, text="비디오 파일").grid(row=r, column=0, sticky=tk.W, **pad)
        row_v = ttk.Frame(frm)
        row_v.grid(row=r, column=1, sticky=tk.EW, **pad)
        ttk.Entry(row_v, textvariable=self.var_video, width=56).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row_v, text="찾기…", command=lambda: _browse_video(self.var_video)).pack(side=tk.LEFT, padx=(6, 0))
        r += 1

        ttk.Label(frm, text="작업 폴더 (비우면 영상 옆 stt_work)").grid(row=r, column=0, sticky=tk.NW, **pad)
        row_w = ttk.Frame(frm)
        row_w.grid(row=r, column=1, sticky=tk.EW, **pad)
        ttk.Entry(row_w, textvariable=self.var_work, width=48).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row_w, text="찾기…", command=lambda: _browse_dir(self.var_work)).pack(side=tk.LEFT, padx=(6, 0))
        r += 1

        ttk.Label(frm, text="Whisper 모델명 (JAVSTORY_WHISPER_MODEL)").grid(row=r, column=0, sticky=tk.W, **pad)
        ttk.Entry(frm, textvariable=self.var_model, width=56).grid(row=r, column=1, sticky=tk.EW, **pad)
        r += 1

        ttk.Label(frm, text="모델 다운로드 루트 (선택)").grid(row=r, column=0, sticky=tk.W, **pad)
        ttk.Entry(frm, textvariable=self.var_download_root, width=56).grid(row=r, column=1, sticky=tk.EW, **pad)
        frm.columnconfigure(1, weight=1)

        opt = ttk.LabelFrame(self, text="옵션")
        opt.pack(fill=tk.X, **pad)
        ttk.Checkbutton(
            opt,
            text="기존 .ja.srt가 있어도 삭제 후 다시 전사 (강제 재실행)",
            variable=self.var_force_rerun,
        ).pack(anchor=tk.W, **pad)
        ttk.Checkbutton(
            opt,
            text="완료 후 동일 이름 .srt 복사 (다른 단계 호환용)",
            variable=self.var_copy_std_srt,
        ).pack(anchor=tk.W, **pad)
        ttk.Label(
            opt,
            text="VAD·beam 등은 환경변수 JAVSTORY_VAD_THRESHOLD, JAVSTORY_WHISPER_BEAM_SIZE 등으로 조절합니다.",
            wraplength=840,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, **pad)

        btn = ttk.Frame(self)
        btn.pack(fill=tk.X, **pad)
        self.btn_run = ttk.Button(btn, text="전사 실행", command=self._on_run)
        self.btn_run.pack(side=tk.LEFT, **pad)
        self.btn_stop = ttk.Button(btn, text="중단", command=self._on_stop, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, **pad)

        prog_fr = ttk.Frame(self)
        prog_fr.pack(fill=tk.X, **pad)
        self.var_prog_label = tk.StringVar(value="대기 중")
        ttk.Label(prog_fr, textvariable=self.var_prog_label).pack(anchor=tk.W)
        self.prog = ttk.Progressbar(prog_fr, mode="determinate", maximum=100)
        self.prog.pack(fill=tk.X, pady=(4, 0))

        log_fr = ttk.LabelFrame(self, text="로그")
        log_fr.pack(fill=tk.BOTH, expand=True, **pad)
        self.txt_log = scrolledtext.ScrolledText(log_fr, height=20, state=tk.DISABLED, wrap=tk.WORD, font=("Consolas", 9))
        self.txt_log.pack(fill=tk.BOTH, expand=True, **pad)

        self._log_line("stable-ts STT 테스트 창입니다. 비디오를 선택한 뒤 실행하세요.")

    def _log_line(self, msg: str) -> None:
        def _append() -> None:
            self.txt_log.configure(state=tk.NORMAL)
            self.txt_log.insert(tk.END, msg + "\n")
            self.txt_log.see(tk.END)
            self.txt_log.configure(state=tk.DISABLED)

        self.after(0, _append)

    def _set_progress(self, pct: int, msg: str) -> None:
        p = max(0, min(100, int(pct)))

        def _upd() -> None:
            self.prog["value"] = p
            self.var_prog_label.set(f"{p}% — {msg}")

        self.after(0, _upd)

    def _on_stop(self) -> None:
        self._cancel_event.set()
        self._log_line("[GUI] 중단 요청됨.")

    def _resolve_work_dir(self, video_path: Path) -> Path:
        w = (self.var_work.get() or "").strip()
        if w:
            return Path(w).expanduser().resolve()
        return (video_path.parent / "stt_work").resolve()

    def _on_run(self) -> None:
        if not self._run_lock.acquire(blocking=False):
            messagebox.showinfo("실행 중", "이미 전사가 진행 중입니다.")
            return

        vp = (self.var_video.get() or "").strip()
        if not vp:
            messagebox.showerror("입력 오류", "비디오 파일을 선택하세요.")
            self._run_lock.release()
            return

        video_path = Path(vp).expanduser().resolve()
        if not video_path.is_file():
            messagebox.showerror("입력 오류", f"파일이 없습니다:\n{video_path}")
            self._run_lock.release()
            return

        ja_srt = video_path.with_suffix(".ja.srt")
        if self.var_force_rerun.get() and ja_srt.is_file():
            if not messagebox.askyesno(
                "강제 재실행",
                f"다음 파일을 삭제하고 다시 전사합니다:\n{ja_srt}\n계속할까요?",
            ):
                self._run_lock.release()
                return

        self._cancel_event.clear()
        self.btn_run.configure(state=tk.DISABLED)
        self.btn_stop.configure(state=tk.NORMAL)
        self._set_progress(0, "시작…")

        work_dir = self._resolve_work_dir(video_path)
        model = (self.var_model.get() or "").strip()
        dl_root = (self.var_download_root.get() or "").strip()

        def _worker() -> None:
            from javstory.transcription.engine import clear_vram, process_video_to_segments
            from javstory.transcription.stt_types import STTCancelled, STTProgressEvent

            env_backup: dict[str, str | None] = {}
            for key in ("JAVSTORY_WHISPER_MODEL", "JAVSTORY_WHISPER_DOWNLOAD_ROOT"):
                env_backup[key] = os.environ.get(key)

            try:
                if model:
                    os.environ["JAVSTORY_WHISPER_MODEL"] = model
                if dl_root:
                    os.environ["JAVSTORY_WHISPER_DOWNLOAD_ROOT"] = dl_root

                if self.var_force_rerun.get() and ja_srt.is_file():
                    try:
                        ja_srt.unlink()
                        self._log_line(f"[GUI] 삭제함: {ja_srt.name}")
                    except OSError as e:
                        self._log_line(f"[GUI] .ja.srt 삭제 실패: {e}")
                        self.after(
                            0,
                            lambda err=str(e): messagebox.showerror("오류", f".ja.srt 삭제 실패:\n{err}"),
                        )
                        return

                last_pct = 0

                def log_bridge(msg: str) -> None:
                    nonlocal last_pct
                    try:
                        m = re.search(r"\[P:(\d+)\]", msg)
                        if m:
                            p = int(m.group(1))
                            last_pct = max(last_pct, max(0, min(100, p)))
                            msg = re.sub(r"\[P:\d+\]\s*", "", msg)
                    except Exception:
                        pass
                    self._log_line(msg)
                    self._set_progress(last_pct, msg[:120])

                def progress_bridge(ev: STTProgressEvent) -> None:
                    nonlocal last_pct
                    try:
                        p = int(getattr(ev, "percent", last_pct))
                    except Exception:
                        p = last_pct
                    p = max(0, min(100, p))
                    last_pct = max(last_pct, p)
                    stage = (getattr(ev, "stage", "") or "").strip()
                    lab = {
                        "init": "초기화",
                        "extract": "오디오 추출",
                        "whisper": "전사",
                        "post": "후처리",
                        "write": "저장",
                        "done": "완료",
                    }.get(stage, stage)
                    m = getattr(ev, "message", "") or ""
                    line = f"[{lab}] {m}" if lab else m
                    self._log_line(line)
                    self._set_progress(last_pct, line[:120])

                segments = process_video_to_segments(
                    video_path=str(video_path),
                    output_dir=str(work_dir),
                    skip_vocal_sep=False,
                    with_llm=False,
                    logger_func=log_bridge,
                    progress_callback=progress_bridge,
                    should_cancel=lambda: self._cancel_event.is_set(),
                )

                base = os.path.splitext(str(video_path))[0]
                ja_out = base + ".ja.srt"
                std_srt = base + ".srt"

                if self.var_copy_std_srt.get() and os.path.exists(ja_out) and not os.path.exists(std_srt):
                    shutil.copy2(ja_out, std_srt)
                    self._log_line(f"[GUI] 복사: {os.path.basename(std_srt)} ← {os.path.basename(ja_out)}")

                self._set_progress(100, "완료")
                self._log_line(f"[GUI] 완료 — 세그먼트 {len(segments)}개 | {ja_out}")

            except STTCancelled:
                self._log_line("[GUI] 사용자 중단.")
                self._set_progress(0, "중단됨")
            except Exception as e:
                self._log_line(f"[GUI] 오류: {e!r}")
                self.after(0, lambda err=str(e): messagebox.showerror("오류", err))
            finally:
                for key, val in env_backup.items():
                    if val is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = val
                try:
                    clear_vram()
                except Exception:
                    pass
                self.after(0, self._run_finished)

        threading.Thread(target=_worker, daemon=True).start()

    def _run_finished(self) -> None:
        self.btn_run.configure(state=tk.NORMAL)
        self.btn_stop.configure(state=tk.DISABLED)
        try:
            self._run_lock.release()
        except RuntimeError:
            pass


def main() -> None:
    app = TranscriptionTestApp()
    app.mainloop()


if __name__ == "__main__":
    main()

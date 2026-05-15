"""
자막 파이프라인 테스트용 Tkinter GUI.

워크플로: get_or_build_background → JA 교정(선택) → KO 번역 (Grok JSON은 캐시에서도 로드 가능)

- KO 번역 프로필: `JAVSTORY_TRANSLATION_PROFILE`와 동일(내부 키: env | default | keeper | deepseek_chat | budget | qwen35 | qwen3_14 | gemma3_12).
- Grok 스토리 맥락 모델: `story_context_tier`(OpenRouter).

실행 (프로젝트 루트에서):

  .\\venv\\Scripts\\python.exe Test\\manual\\subtitle_pipeline_test_gui.py
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
import threading
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from javstory.config import secrets_manager
from javstory.llm.engine import MultiTierRouter

# (표시 라벨, 내부 프로필 키) — `JAVSTORY_TRANSLATION_PROFILE`와 동일
KO_TRANSLATION_PROFILE_ROWS: tuple[tuple[str, str], ...] = (
    ("환경변수 (.env 따름)", "env"),
    ("DeepSeek V3.2", "default"),
    ("GLM5.1", "keeper"),
    ("DeepSeek V3 Chat", "deepseek_chat"),
    ("Gemma4-E4B", "budget"),
    ("Qwen3.5-9B", "qwen35"),
    ("Qwen3-14B", "qwen3_14"),
    ("Gemma3-12B", "gemma3_12"),
)
KO_PROFILE_LABEL_TO_KEY: dict[str, str] = dict(KO_TRANSLATION_PROFILE_ROWS)


def _gui_env_snapshot(keys: tuple[str, ...]) -> dict[str, str | None]:
    return {k: os.environ.get(k) for k in keys}


def _gui_env_restore(snap: dict[str, str | None]) -> None:
    for k, v in snap.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _gui_resolve_translation_tier(*, profile: str, provider_override: str | None) -> dict:
    """
    GUI에서 선택한 프로필·provider를 `resolve_translation_llm_tier`에 반영한다.
    profile: env | default | keeper | deepseek_chat | budget | qwen35 | qwen3_14 | gemma3_12 (core.app_config 의 JAVSTORY_TRANSLATION_PROFILE 과 동일)
    provider_override: None 또는 openrouter | ollama (JAVSTORY_TRANSLATION_PROVIDER 강제)
    """
    from javstory.config.app_config import resolve_translation_llm_tier

    keys = ("JAVSTORY_TRANSLATION_PROFILE", "JAVSTORY_TRANSLATION_PROVIDER")
    snap = {k: os.environ.get(k) for k in keys}
    try:
        if profile != "env":
            os.environ["JAVSTORY_TRANSLATION_PROFILE"] = profile
            if provider_override not in ("openrouter", "ollama"):
                if profile in (
                    "default",
                    "keeper",
                    "budget",
                    "deepseek_chat",
                    "qwen35",
                    "qwen3_14",
                    "gemma3_12",
                ):
                    os.environ.pop("JAVSTORY_TRANSLATION_PROVIDER", None)
        tp = provider_override if provider_override in ("openrouter", "ollama") else None
        return resolve_translation_llm_tier(translation_provider=tp)
    finally:
        for k in keys:
            v = snap[k]
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _browse_file(var: tk.StringVar, *, title: str) -> None:
    p = filedialog.askopenfilename(title=title, filetypes=[("SRT", "*.srt"), ("모든 파일", "*.*")])
    if p:
        var.set(p)


def _browse_dir(var: tk.StringVar, *, title: str) -> None:
    p = filedialog.askdirectory(title=title)
    if p:
        var.set(p)


class SubtitlePipelineTestApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("JAVSTORY 자막 파이프라인 테스트 (배경 · 교정 · KO)")
        self.geometry("920x820")
        self.minsize(640, 480)

        self._cancel_event = threading.Event()
        self._run_lock = threading.Lock()
        self._worker: threading.Thread | None = None

        secrets_manager.apply_env_to_os()

        # --- 변수 ---
        self.var_product = tk.StringVar(value="TEST-001")
        self.var_work_dir = tk.StringVar()
        self.var_ja_srt = tk.StringVar()
        self.var_translate_ja = tk.StringVar()
        self.var_ja_corrected = tk.StringVar()
        self.var_ko_srt = tk.StringVar()
        self.var_grok_conv = tk.StringVar()
        self.var_translation_profile = tk.StringVar(value=KO_TRANSLATION_PROFILE_ROWS[0][0])
        self.var_translation_provider = tk.StringVar(value="(따름)")
        self.var_force_rebuild = tk.BooleanVar(value=False)
        self.var_skip_correction = tk.BooleanVar(value=False)
        self.var_speaker_prefix = tk.StringVar(value="off")
        self.var_enable_story_context = tk.BooleanVar(value=True)
        self.var_log_story_grok = tk.BooleanVar(value=True)
        self.var_log_glm_full = tk.BooleanVar(value=True)
        self.var_story_context_model = tk.StringVar(value="env")

        pad = {"padx": 8, "pady": 4}

        frm = ttk.LabelFrame(self, text="입력")
        frm.pack(fill=tk.X, **pad)

        r = 0
        ttk.Label(frm, text="품번 (product_code)").grid(row=r, column=0, sticky=tk.W, **pad)
        ttk.Entry(frm, textvariable=self.var_product, width=56).grid(row=r, column=1, sticky=tk.EW, **pad)
        r += 1

        ttk.Label(frm, text="작업 폴더 (work_dir)").grid(row=r, column=0, sticky=tk.W, **pad)
        row_wd = ttk.Frame(frm)
        row_wd.grid(row=r, column=1, sticky=tk.EW, **pad)
        ttk.Entry(row_wd, textvariable=self.var_work_dir, width=48).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row_wd, text="찾기…", command=lambda: _browse_dir(self.var_work_dir, title="작업 폴더")).pack(
            side=tk.LEFT, padx=(6, 0)
        )
        r += 1

        ttk.Label(frm, text="일본어 SRT (ja_srt_path)").grid(row=r, column=0, sticky=tk.NW, **pad)
        row_ja = ttk.Frame(frm)
        row_ja.grid(row=r, column=1, sticky=tk.EW, **pad)
        ttk.Entry(row_ja, textvariable=self.var_ja_srt, width=48).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row_ja, text="찾기…", command=lambda: _browse_file(self.var_ja_srt, title="일본어 SRT")).pack(
            side=tk.LEFT, padx=(6, 0)
        )
        r += 1

        ttk.Label(frm, text="번역 입력 SRT (선택, 교정 우회 시)").grid(row=r, column=0, sticky=tk.NW, **pad)
        row_tj = ttk.Frame(frm)
        row_tj.grid(row=r, column=1, sticky=tk.EW, **pad)
        ttk.Entry(row_tj, textvariable=self.var_translate_ja, width=48).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row_tj, text="찾기…", command=lambda: _browse_file(self.var_translate_ja, title="번역용 JA SRT")).pack(
            side=tk.LEFT, padx=(6, 0)
        )
        r += 1

        ttk.Label(frm, text="교정 출력 SRT (선택)").grid(row=r, column=0, sticky=tk.NW, **pad)
        row_jc = ttk.Frame(frm)
        row_jc.grid(row=r, column=1, sticky=tk.EW, **pad)
        ttk.Entry(row_jc, textvariable=self.var_ja_corrected, width=48).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row_jc, text="찾기…", command=lambda: _browse_file(self.var_ja_corrected, title="교정 SRT 저장 경로")).pack(
            side=tk.LEFT, padx=(6, 0)
        )
        r += 1

        ttk.Label(frm, text="한국어 출력 SRT (선택)").grid(row=r, column=0, sticky=tk.NW, **pad)
        row_ko = ttk.Frame(frm)
        row_ko.grid(row=r, column=1, sticky=tk.EW, **pad)
        ttk.Entry(row_ko, textvariable=self.var_ko_srt, width=48).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row_ko, text="찾기…", command=lambda: _browse_file(self.var_ko_srt, title="KO SRT 저장 경로")).pack(
            side=tk.LEFT, padx=(6, 0)
        )
        r += 1

        ttk.Label(frm, text="Grok conv id (선택)").grid(row=r, column=0, sticky=tk.W, **pad)
        ttk.Entry(frm, textvariable=self.var_grok_conv, width=56).grid(row=r, column=1, sticky=tk.EW, **pad)
        frm.columnconfigure(1, weight=1)

        opt = ttk.LabelFrame(self, text="옵션")
        opt.pack(fill=tk.X, **pad)

        orow = ttk.Frame(opt)
        orow.pack(fill=tk.X, **pad)
        ttk.Label(orow, text="KO 번역 프로필").pack(side=tk.LEFT)
        ttk.Combobox(
            orow,
            textvariable=self.var_translation_profile,
            values=[row[0] for row in KO_TRANSLATION_PROFILE_ROWS],
            state="readonly",
            width=28,
        ).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(
            orow,
            text="(번역: OpenRouter·Ollama 공통 Non-Thinking)",
            font=("TkDefaultFont", 8),
        ).pack(side=tk.LEFT, padx=(6, 0))

        orow2 = ttk.Frame(opt)
        orow2.pack(fill=tk.X, **pad)
        ttk.Label(orow2, text="provider 강제(선택)").pack(side=tk.LEFT)
        ttk.Combobox(
            orow2,
            textvariable=self.var_translation_provider,
            values=["(따름)", "openrouter", "ollama"],
            state="readonly",
            width=14,
        ).pack(side=tk.LEFT, padx=(8, 0))

        orow3 = ttk.Frame(opt)
        orow3.pack(fill=tk.X, **pad)
        ttk.Label(orow3, text="Grok 스토리 모델").pack(side=tk.LEFT)
        ttk.Combobox(
            orow3,
            textvariable=self.var_story_context_model,
            values=[
                "env",
                "x-ai/grok-4.3:online",
                "x-ai/grok-4-fast:online",
                "grok-4-fast:online",
            ],
            state="readonly",
            width=28,
        ).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Label(orow3, text="= .env | OpenRouter Grok (:online)", font=("TkDefaultFont", 8)).pack(
            side=tk.LEFT, padx=(6, 0)
        )

        ttk.Checkbutton(opt, text="배경 JSON 강제 재생성 (force_rebuild)", variable=self.var_force_rebuild).pack(
            anchor=tk.W, **pad
        )
        ttk.Checkbutton(
            opt,
            text="일본어 교정 건너뛰기 (ja_srt 무시 · 아래 ‘번역 입력 SRT’ 필수)",
            variable=self.var_skip_correction,
        ).pack(anchor=tk.W, padx=(0, 0), pady=(0, 4))

        ttk.Label(opt, text="로그 (테스트용 상세)", font=("TkDefaultFont", 9, "bold")).pack(anchor=tk.W, **pad)
        ttk.Checkbutton(
            opt,
            text="Grok 스토리 맥락(웹검색) 사용 — TranslationHints 주입",
            variable=self.var_enable_story_context,
        ).pack(anchor=tk.W, **pad)
        ttk.Checkbutton(
            opt,
            text="Grok 응답 로그 — 원시 JSON + 포맷된 한국어 힌트 본문",
            variable=self.var_log_story_grok,
        ).pack(anchor=tk.W, **pad)
        ttk.Checkbutton(
            opt,
            text="번역 LLM 상세 로그 — system/user 전체 프롬프트 + 모델 응답 본문",
            variable=self.var_log_glm_full,
        ).pack(anchor=tk.W, **pad)

        sprow = ttk.Frame(opt)
        sprow.pack(fill=tk.X, **pad)
        ttk.Label(sprow, text="화자 접두어 (교정)").pack(side=tk.LEFT)
        ttk.Combobox(
            sprow,
            textvariable=self.var_speaker_prefix,
            values=["off", "on"],
            state="readonly",
            width=8,
        ).pack(side=tk.LEFT, padx=(8, 0))

        info = (
            "KO 번역: app_config와 동일 프로필. OpenRouter는 API 키, Ollama는 로컬. "
            "Grok 스토리: 품번 웹검색·캐시 JSON."
        )
        ttk.Label(opt, text=info, wraplength=860, justify=tk.LEFT).pack(anchor=tk.W, **pad)

        btn = ttk.Frame(self)
        btn.pack(fill=tk.X, **pad)
        self.btn_run = ttk.Button(btn, text="실행 (배경 → 교정 → KO 번역)", command=self._on_run)
        self.btn_run.pack(side=tk.LEFT, **pad)
        self.btn_stop = ttk.Button(btn, text="중단 요청", command=self._on_stop, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, **pad)

        log_fr = ttk.LabelFrame(self, text="로그")
        log_fr.pack(fill=tk.BOTH, expand=True, **pad)
        self.txt_log = scrolledtext.ScrolledText(log_fr, height=22, state=tk.DISABLED, wrap=tk.WORD, font=("Consolas", 9))
        self.txt_log.pack(fill=tk.BOTH, expand=True, **pad)

        self._log_line("준비됨. 품번·작업 폴더를 채우고 SRT 경로를 지정한 뒤 실행하세요.")

    def _log_line(self, msg: str) -> None:
        def _append() -> None:
            self.txt_log.configure(state=tk.NORMAL)
            self.txt_log.insert(tk.END, msg + "\n")
            self.txt_log.see(tk.END)
            self.txt_log.configure(state=tk.DISABLED)

        self.after(0, _append)

    def _on_stop(self) -> None:
        self._cancel_event.set()
        self._log_line("[GUI] 중단 요청됨 (다음 should_cancel 시점 이후 반영).")

    def _on_run(self) -> None:
        if not self._run_lock.acquire(blocking=False):
            messagebox.showinfo("실행 중", "이미 파이프라인이 실행 중입니다.")
            return

        pc = (self.var_product.get() or "").strip()
        wd = (self.var_work_dir.get() or "").strip()
        ja = (self.var_ja_srt.get() or "").strip()
        tja = (self.var_translate_ja.get() or "").strip()
        skip = self.var_skip_correction.get()

        if not pc:
            messagebox.showerror("입력 오류", "품번(product_code)을 입력하세요.")
            self._run_lock.release()
            return
        if not wd:
            messagebox.showerror("입력 오류", "작업 폴더(work_dir)를 지정하세요.")
            self._run_lock.release()
            return

        work_path = Path(wd).expanduser().resolve()
        work_path.mkdir(parents=True, exist_ok=True)

        if skip:
            if not tja:
                messagebox.showerror(
                    "입력 오류",
                    "교정을 건너뛸 때는 ‘번역 입력 SRT’ 경로가 필요합니다.",
                )
                self._run_lock.release()
                return
            if not Path(tja).is_file():
                messagebox.showerror("입력 오류", f"번역 입력 파일이 없습니다:\n{tja}")
                self._run_lock.release()
                return
        else:
            if not ja:
                messagebox.showerror("입력 오류", "일본어 SRT 경로를 입력하거나, ‘교정 건너뛰기’를 사용하세요.")
                self._run_lock.release()
                return
            if not Path(ja).is_file():
                messagebox.showerror("입력 오류", f"일본어 SRT 파일이 없습니다:\n{ja}")
                self._run_lock.release()
                return

        self._cancel_event.clear()
        self.btn_run.configure(state=tk.DISABLED)
        self.btn_stop.configure(state=tk.NORMAL)

        kwargs = self._build_kwargs(work_path, ja, tja, skip)

        def _worker() -> None:
            env_snap = _gui_env_snapshot(())
            try:
                api_key = secrets_manager.get_openrouter_api_key() or ""
                prof_raw = (self.var_translation_profile.get() or "").strip()
                prof = KO_PROFILE_LABEL_TO_KEY.get(prof_raw, prof_raw or "env")
                pov = self.var_translation_provider.get()
                pov_norm = pov if pov in ("openrouter", "ollama") else None
                tier = _gui_resolve_translation_tier(profile=prof, provider_override=pov_norm)
                kwargs["translation_tier"] = tier

                from javstory.config.app_config import story_context_llm_tier
                from javstory.translation.story_grok_module import story_context_cache_path_grok

                scm = (self.var_story_context_model.get() or "env").strip()
                if scm and scm != "env":
                    kwargs["story_context_tier"] = {**story_context_llm_tier(), "model": scm}

                if tier.get("provider") == "openrouter" and not api_key:
                    self._log_line("[GUI] 경고: OpenRouter API 키가 없습니다. budget 프로필·Ollama 또는 키를 설정하세요.")

                safe_pc = re.sub(r"[^\w\-.]", "_", pc, flags=re.ASCII) or "product"
                sc_raw = kwargs.get("story_context_tier")
                if isinstance(sc_raw, dict) and sc_raw:
                    sc_tier = {**story_context_llm_tier(), **sc_raw}
                else:
                    sc_tier = story_context_llm_tier()
                cache_json = story_context_cache_path_grok(pc)
                self._log_line(f"[GUI] 품번={pc!r} | 작업 폴더={work_path}")
                self._log_line(
                    f"[GUI] KO 번역 티어: provider={tier.get('provider')} | model={tier.get('model')} | name={tier.get('name')}"
                )
                self._log_line(f"[GUI] Grok 스토리 모델: {sc_tier.get('model')}")
                self._log_line(f"[GUI] 스토리 캐시(JSON) 경로: {cache_json}")
                if self.var_enable_story_context.get():
                    self._log_line(
                        f"[GUI] 작업 폴더 저장(스토리 사용 시): "
                        f"{work_path / f'{safe_pc}_story_context.json'} | "
                        f"{work_path / f'{safe_pc}_translation_hints.ko.txt'}"
                    )

                router = MultiTierRouter(api_key=api_key, logger_func=self._log_line)
                from javstory.translation.subtitle_pipeline_orchestrator import SubtitlePipelineOrchestrator

                orch = SubtitlePipelineOrchestrator(router)

                async def _run() -> None:
                    try:
                        await orch.run_for_product(pc, **kwargs)
                    finally:
                        await router.close()

                asyncio.run(_run())
                self._log_line("[GUI] 파이프라인 정상 종료.")
            except Exception as e:
                self._log_line(f"[GUI] 오류: {e!r}")
                err_text = f"{type(e).__name__}: {e}"
                self.after(0, lambda msg=err_text: messagebox.showerror("오류", msg))
            finally:
                _gui_env_restore(env_snap)
                self.after(0, self._run_finished)

        self._worker = threading.Thread(target=_worker, daemon=True)
        self._worker.start()

    def _build_kwargs(self, work_path: Path, ja: str, tja: str, skip_correction: bool) -> dict:
        kwargs: dict = {
            "work_dir": str(work_path),
            "logger_func": self._log_line,
            "should_cancel": lambda: self._cancel_event.is_set(),
            "force_rebuild": self.var_force_rebuild.get(),
            "speaker_prefix_mode": self.var_speaker_prefix.get(),
        }
        gc = (self.var_grok_conv.get() or "").strip()
        if gc:
            kwargs["grok_conv_id"] = gc

        jcor = (self.var_ja_corrected.get() or "").strip()
        if jcor:
            kwargs["ja_corrected_srt_path"] = jcor

        kos = (self.var_ko_srt.get() or "").strip()
        if kos:
            kwargs["ko_srt_path"] = kos

        kwargs["enable_story_context"] = self.var_enable_story_context.get()
        kwargs["log_story_context_report"] = self.var_log_story_grok.get()
        kwargs["log_full_translation_prompt"] = self.var_log_glm_full.get()

        if skip_correction:
            kwargs["translate_ja_srt_path"] = tja
        else:
            kwargs["ja_srt_path"] = ja
            if tja:
                kwargs["translate_ja_srt_path"] = tja

        return kwargs

    def _run_finished(self) -> None:
        self.btn_run.configure(state=tk.NORMAL)
        self.btn_stop.configure(state=tk.DISABLED)
        try:
            self._run_lock.release()
        except RuntimeError:
            pass


def main() -> None:
    app = SubtitlePipelineTestApp()
    app.mainloop()


if __name__ == "__main__":
    main()

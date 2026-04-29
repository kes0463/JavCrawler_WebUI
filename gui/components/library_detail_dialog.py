"""작품 상세 — Harvest 메타 + canonical 씬 목록."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout
from qfluentwidgets import (
    CaptionLabel,
    PrimaryPushButton,
    PushButton,
    StrongBodyLabel,
    SubtitleLabel,
    TextEdit,
    TitleLabel,
    InfoBar,
    InfoBarPosition,
    CardWidget,
    ProgressBar,
    FluentIcon as FIF,
)

from gui.library_data import LibraryWorkSummary, canonical_quick_stats
from javstory.library.canonical.store import load_library_state
from javstory.library.paths import library_state_path, work_library_dir


class LibraryDetailDialog(QDialog):
    def __init__(self, summary: LibraryWorkSummary, parent=None):
        super().__init__(parent)
        self._summary = summary
        self.setWindowTitle(f"라이브러리 — {summary.product_code}")
        self.setMinimumSize(520, 560)
        self.resize(600, 640)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        layout.addWidget(TitleLabel(summary.product_code, self))
        ko = summary.title_ko or "(한글 제목 없음)"
        layout.addWidget(StrongBodyLabel(ko, self))
        if summary.title_ja:
            layout.addWidget(CaptionLabel(f"JA: {summary.title_ja}", self))

        meta = SubtitleLabel(
            f"배우: {summary.actors_ko or '-'}  ·  메이커: {summary.maker_ko or '-'}  ·  발매: {summary.release_date or '-'}",
            self,
        )
        meta.setWordWrap(True)
        layout.addWidget(meta)

        if summary.genres_ko:
            layout.addWidget(CaptionLabel(f"장르: {summary.genres_ko}", self))

        syn = TextEdit(self)
        syn.setReadOnly(True)
        syn.setPlaceholderText("시놉시스 없음")
        syn.setPlainText((summary.synopsis_ko or "").strip())
        syn.setMinimumHeight(100)
        layout.addWidget(SubtitleLabel("Harvest 시놉시스", self))
        layout.addWidget(syn)

        self._build_pipeline_status(layout, summary)

        has_c, n_sc, n_st, prev = canonical_quick_stats(summary.product_code)
        canon_header = QHBoxLayout()
        canon_header.addWidget(SubtitleLabel("Canonical (library_state.json)", self))
        canon_header.addStretch()
        self.lbl_canon_stat = CaptionLabel(
            f"씬 {n_sc} · 스틸 {n_st} · {'저장됨' if has_c else '없음'}",
            self,
        )
        canon_header.addWidget(self.lbl_canon_stat)
        layout.addLayout(canon_header)

        self.canon_body = TextEdit(self)
        self.canon_body.setReadOnly(True)
        self.canon_body.setMinimumHeight(140)
        layout.addWidget(self.canon_body)

        path_row = QHBoxLayout()
        self.path_label = CaptionLabel("", self)
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.path_label.setWordWrap(True)
        path_row.addWidget(self.path_label, stretch=1)
        self.btn_open = PushButton("작품 폴더", self)
        self.btn_open.clicked.connect(self._open_work_dir)
        path_row.addWidget(self.btn_open)
        layout.addLayout(path_row)

        self._fill_canonical_text()

        action_row = QHBoxLayout()
        btn_grok = PushButton(FIF.UPDATE, "Grok 병합", self)
        btn_grok.setToolTip("Grok 스토리 JSON을 canonical에 머지")
        btn_grok.clicked.connect(self._on_merge_grok)
        action_row.addWidget(btn_grok)

        btn_export = PushButton(FIF.SAVE, "Export", self)
        btn_export.setToolTip("master_db.js + story JSON 내보내기")
        btn_export.clicked.connect(self._on_export)
        action_row.addWidget(btn_export)

        btn_stills = PushButton(FIF.PHOTO, "스틸 새로고침", self)
        btn_stills.setToolTip("씬별 스틸 프레임 재추출")
        btn_stills.clicked.connect(self._on_refresh_stills)
        action_row.addWidget(btn_stills)

        action_row.addStretch()
        layout.addLayout(action_row)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = PrimaryPushButton("닫기", self)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _build_pipeline_status(self, layout: QVBoxLayout, summary: LibraryWorkSummary) -> None:
        layout.addWidget(SubtitleLabel("파이프라인 상태", self))
        card = CardWidget(self)
        card_lay = QHBoxLayout(card)
        card_lay.setSpacing(18)

        try:
            from javstory.pipeline.orchestrator import get_pipeline_status
            from gui.library_data import guess_video_path_for_product
            vp = guess_video_path_for_product(summary.product_code)
            status = get_pipeline_status(
                product_code=summary.product_code,
                video_path=str(vp) if vp else None,
            )
        except Exception:
            status = None

        stages = [
            ("Harvest", status.harvest_in_db if status else False),
            ("STT (.ja.srt)", status.ja_srt_exists if status else False),
            ("Subtitle (.ko.srt)", status.ko_srt_exists if status else False),
        ]
        for name, done in stages:
            col = QVBoxLayout()
            label = CaptionLabel(name, self)
            col.addWidget(label)
            state_label = CaptionLabel("완료" if done else "미완료", self)
            state_label.setStyleSheet(
                "color: #4CAF50; font-weight: bold;" if done
                else "color: #FF9800; font-weight: bold;"
            )
            col.addWidget(state_label)
            card_lay.addLayout(col)

        card_lay.addStretch()

        btn_run = PushButton(FIF.PLAY, "A축 실행", self)
        btn_run.setToolTip("Harvest→STT→Subtitle 원스톱 실행")
        btn_run.clicked.connect(self._on_run_pipeline)
        card_lay.addWidget(btn_run)

        layout.addWidget(card)

    def _on_run_pipeline(self) -> None:
        from gui.workers.pipeline_worker import PipelineWorker
        from gui.library_data import guess_video_path_for_product

        pc = self._summary.product_code
        vp = guess_video_path_for_product(pc)

        self._pipeline_worker = PipelineWorker(
            pc,
            str(vp) if vp else None,
            stages="all",
            parent=self,
        )
        self._pipeline_worker.progress.connect(self._on_pipeline_progress)
        self._pipeline_worker.finished.connect(self._on_pipeline_finished)
        self._pipeline_worker.start()
        InfoBar.info("파이프라인", f"{pc} A축 실행을 시작합니다.", parent=self,
                     duration=2500, position=InfoBarPosition.TOP)

    def _on_pipeline_progress(self, stage, msg, pct):
        main_win = self.parent()
        if main_win and hasattr(main_win, 'log_drawer'):
            main_win.log_drawer.append_log(f"[{self._summary.product_code}] [{stage}] {msg}")

    def _on_pipeline_finished(self, success, summary):
        level = InfoBar.success if success else InfoBar.warning
        level("파이프라인", summary, parent=self,
              duration=5000, position=InfoBarPosition.TOP)

    def _on_merge_grok(self) -> None:
        try:
            from javstory.library.service import merge_grok_into_work
            result = merge_grok_into_work(self._summary.product_code)
            if result:
                InfoBar.success("Grok 병합", "canonical에 Grok 데이터가 병합되었습니다.", parent=self,
                                duration=3000, position=InfoBarPosition.TOP)
                self._fill_canonical_text()
            else:
                InfoBar.info("Grok 병합", "병합할 Grok 데이터가 없습니다.", parent=self,
                             duration=3000, position=InfoBarPosition.TOP)
        except Exception as e:
            InfoBar.warning("Grok 병합", f"오류: {e}", parent=self,
                            duration=5000, position=InfoBarPosition.TOP)

    def _on_export(self) -> None:
        try:
            from javstory.library.service import run_export
            run_export(self._summary.product_code)
            InfoBar.success("Export", "master_db.js + story JSON 내보내기 완료", parent=self,
                            duration=3000, position=InfoBarPosition.TOP)
        except Exception as e:
            InfoBar.warning("Export", f"오류: {e}", parent=self,
                            duration=5000, position=InfoBarPosition.TOP)

    def _on_refresh_stills(self) -> None:
        try:
            from javstory.library.service import refresh_stills
            refresh_stills(self._summary.product_code)
            InfoBar.success("스틸", "씬별 스틸 프레임 추출 완료", parent=self,
                            duration=3000, position=InfoBarPosition.TOP)
        except Exception as e:
            InfoBar.warning("스틸", f"오류: {e}", parent=self,
                            duration=5000, position=InfoBarPosition.TOP)

    def _fill_canonical_text(self) -> None:
        pc = self._summary.product_code
        p = library_state_path(pc)
        self.path_label.setText(str(p))
        if not p.is_file():
            self.canon_body.setPlainText("(library_state.json 없음 — 수집·Grok 후 생성됩니다.)")
            return
        try:
            state = load_library_state(p)
        except Exception as e:
            self.canon_body.setPlainText(f"로드 실패: {e}")
            return
        lines: list[str] = []
        if (state.overall_summary or "").strip():
            lines.append("[전체 요약]")
            lines.append(state.overall_summary.strip())
            lines.append("")
        lines.append("[씬]")
        for s in state.scenes:
            tr = s.time_range or ""
            lines.append(f"• {s.scene_id}  {s.scene_label or ''}  {tr}")
            if (s.scene_summary or "").strip():
                snip = s.scene_summary.strip().replace("\n", " ")
                lines.append(f"  {snip[:240]}{'…' if len(snip) > 240 else ''}")
        self.canon_body.setPlainText("\n".join(lines) if lines else "(씬 없음)")

    def _open_work_dir(self) -> None:
        d = work_library_dir(self._summary.product_code)
        d.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(d.resolve())))

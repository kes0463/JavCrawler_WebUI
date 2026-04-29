"""멀티파트 영상 — 파트 순 정렬·논리 타임라인 SRT(합본) 생성."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QListWidget,
    QMessageBox,
    QVBoxLayout,
)
from qfluentwidgets import (
    CaptionLabel,
    PrimaryPushButton,
    PushButton,
    StrongBodyLabel,
    TextEdit,
    FluentIcon as FIF,
)

from javstory.library.multipart import (
    build_logical_merged_srt,
    prepare_ordered_videos,
    suggest_groups_in_directories,
)


class MultiPartMergeDialog(QDialog):
    """
    파트별로 이미 생성된 `영상명.ja.srt`(또는 `.srt`)를 읽어,
    앞선 파트 길이만큼 오프셋을 더한 **합본 SRT**를 만든다 (번역·참고용).
    플레이어 재생용은 파트마다 동명 SRT를 그대로 쓴다.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("멀티파트 — 논리 타임라인 SRT 합성")
        self.resize(640, 480)
        self._paths: list[Path] = []

        lay = QVBoxLayout(self)
        lay.addWidget(StrongBodyLabel("영상 파일 (파트 순은 아래 정렬로 맞춤)", self))
        lay.addWidget(
            CaptionLabel(
                "각 영상 옆에 동명 자막(.ja.srt 우선, 없으면 .srt)이 있어야 합니다. "
                "STT로 파트마다 먼저 뽑은 뒤 이 도구를 쓰세요.",
                self,
            )
        )

        btn_row = QHBoxLayout()
        self.btn_add = PushButton(FIF.FOLDER, "영상 추가", self)
        self.btn_add.clicked.connect(self._add_videos)
        self.btn_sort = PushButton(FIF.SYNC, "파트 순 자동 정렬", self)
        self.btn_sort.clicked.connect(self._auto_sort)
        self.btn_suggest = PushButton(FIF.INFO, "같은 폴더 그룹 힌트", self)
        self.btn_suggest.clicked.connect(self._show_suggestions)
        btn_row.addWidget(self.btn_add)
        btn_row.addWidget(self.btn_sort)
        btn_row.addWidget(self.btn_suggest)
        lay.addLayout(btn_row)

        self.list_w = QListWidget(self)
        self.list_w.setMinimumHeight(180)
        lay.addWidget(self.list_w)

        out_row = QHBoxLayout()
        self.btn_out = PushButton(FIF.SAVE, "합본 저장 위치…", self)
        self.btn_out.clicked.connect(self._pick_out)
        self.lbl_out = CaptionLabel("(미선택)", self)
        self.lbl_out.setWordWrap(True)
        out_row.addWidget(self.btn_out)
        out_row.addWidget(self.lbl_out, stretch=1)
        lay.addLayout(out_row)

        self._out_path: Path | None = None

        self.log = TextEdit(self)
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(120)
        lay.addWidget(self.log)

        run_row = QHBoxLayout()
        run_row.addStretch()
        self.btn_run = PrimaryPushButton(FIF.ACCEPT, "합성 실행", self)
        self.btn_run.clicked.connect(self._run_merge)
        close = PushButton(FIF.CLOSE, "닫기", self)
        close.clicked.connect(self.reject)
        run_row.addWidget(close)
        run_row.addWidget(self.btn_run)
        lay.addLayout(run_row)

    def _add_videos(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "멀티파트 영상 선택",
            "",
            "Video (*.mp4 *.mkv *.avi *.mov *.webm *.m4v);;All (*.*)",
        )
        if not files:
            return
        seen = {str(p).lower() for p in self._paths}
        for f in files:
            p = Path(f).resolve()
            k = str(p).lower()
            if k not in seen:
                seen.add(k)
                self._paths.append(p)
        self._refresh_list()

    def _refresh_list(self) -> None:
        self.list_w.clear()
        for i, p in enumerate(self._paths, start=1):
            self.list_w.addItem(f"{i}. {p.name}  →  {p}")

    def _auto_sort(self) -> None:
        if len(self._paths) < 2:
            QMessageBox.information(self, "멀티파트", "영상을 2개 이상 추가하세요.")
            return
        self._paths = prepare_ordered_videos(self._paths)
        self._refresh_list()
        self.log.append("파트 순 자동 정렬 적용 (파일명 패턴: part/cd/disc/上巻 등)")

    def _show_suggestions(self) -> None:
        if len(self._paths) < 2:
            QMessageBox.information(self, "힌트", "영상을 2개 이상 추가하세요.")
            return
        sug = suggest_groups_in_directories(self._paths)
        if not sug:
            self.log.append("같은 폴더에 2개 이상인 그룹이 없습니다.")
            return
        lines = []
        for g in sug:
            lines.append(f"{g.directory}:\n  " + "\n  ".join(x.name for x in g.video_paths))
        self.log.append("같은 폴더 후보:\n" + "\n\n".join(lines))

    def _pick_out(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "합본 SRT 저장",
            str(Path.home() / "merged_logic.ja.srt"),
            "Subtitles (*.srt *.ja.srt)",
        )
        if path:
            self._out_path = Path(path)
            self.lbl_out.setText(str(self._out_path))

    def _run_merge(self) -> None:
        if len(self._paths) < 2:
            QMessageBox.warning(self, "멀티파트", "영상을 2개 이상 추가하세요.")
            return
        if self._out_path is None:
            QMessageBox.warning(self, "멀티파트", "저장 위치를 먼저 선택하세요.")
            return
        ok, msg = build_logical_merged_srt(self._paths, self._out_path)
        if ok:
            self.log.append(msg)
            QMessageBox.information(self, "완료", msg)
        else:
            self.log.append(f"실패: {msg}")
            QMessageBox.critical(self, "실패", msg)

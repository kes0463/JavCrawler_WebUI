"""
Deprecated — PyQt6 Fluent Harvest 뷰.

운영 UI: gui/qml/views/HarvestView.qml
→ gui/views/README.md
"""
import os
import time
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QFileDialog, QMessageBox, QInputDialog,
)
from PyQt6.QtCore import pyqtSlot
from qfluentwidgets import (
    TitleLabel, SubtitleLabel, PushButton, ProgressBar,
    setFont, CardWidget, InfoBar, InfoBarPosition,
    StrongBodyLabel, ListWidget, FluentIcon as FIF,
    SearchLineEdit, FlowLayout, PrimaryPushButton, SwitchButton,
    CaptionLabel,
)
import re
from javstory.harvest.database import get_db_session, JAVMetadata
from javstory.config.app_config import MEDIA_ROOT

from gui.workers.harvest_worker import HarvestWorker
from gui.components.harvest_card import HarvestCard
from javstory.harvest.folder_harvest import (
    plan_folder_paths,
    plan_parent_folder,
    plan_single_folder,
    planned_to_worker_entries,
)

class HarvestView(QWidget):
    """
    Stage 1 (수집), Stage 2 (한국어 로컬라이징)을 관장하는 화면입니다.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HarvestView")
        
        # 메인 레이아웃
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(30, 30, 30, 30)
        self.layout.setSpacing(20)
        
        # 1. 상단 타이틀 및 검색/입력
        self._init_header()
        
        # 2. 수집 작업 현황판 (Scroll Area)
        self._init_status_board()
        
        # 워커 및 카드 관리
        self.workers: dict[str, HarvestWorker] = {}
        self.cards: dict[str, HarvestCard] = {}
        self._active_threads = []   # 강력 참조용 리스트 (GC 방지)
        self._finished_workers = [] # [안정화] 종료된 워커 지연 해제용 리스트

    def _init_header(self):
        header_layout = QHBoxLayout()
        
        title_layout = QVBoxLayout()
        title = TitleLabel("수집 및 현지화 (Harvest)", self)
        desc = SubtitleLabel("Stage 1-2: 신규 작품 검색, 크롤링 및 한국어 메타데이터 세공", self)
        setFont(title, 28, weight=700)
        title_layout.addWidget(title)
        title_layout.addWidget(desc)
        
        header_layout.addLayout(title_layout)
        header_layout.addStretch()

        self.layout.addLayout(header_layout)
        
        # 검색창 및 수동 추가 영역
        search_layout = QHBoxLayout()
        self.search_edit = SearchLineEdit(self)
        self.search_edit.setPlaceholderText("품번(SKU) 입력 (예: STAR-471, MIDE-123)")
        self.search_edit.setFixedWidth(400)
        self.search_edit.searchButton.clicked.connect(self._on_search_clicked)
        self.search_edit.returnPressed.connect(self._on_search_clicked)
        
        search_layout.addWidget(self.search_edit)
        
        # 일괄 수집 버튼
        self.batch_button = PrimaryPushButton("목록으로 일괄 수집", self)
        self.batch_button.clicked.connect(self._on_batch_collect)
        search_layout.addWidget(self.batch_button)

        self.layout.addLayout(search_layout)

        folder_row = QHBoxLayout()
        self.btn_folder_single = PushButton(FIF.FOLDER, "작품 폴더에서 수집", self)
        self.btn_folder_single.setToolTip("폴더 **이름**에서 품번 추출 → 직하위 동영상(1개 우선)과 연결해 크롤")
        self.btn_folder_single.clicked.connect(self._on_harvest_single_folder)
        folder_row.addWidget(self.btn_folder_single)

        self.btn_folder_parent = PushButton(FIF.FOLDER_ADD, "상위 폴더(하위 작품 일괄)", self)
        self.btn_folder_parent.setToolTip("선택한 폴더의 **직하위 하위 폴더**마다 품번 추출 후 일괄 수집 (재귀 없음)")
        self.btn_folder_parent.clicked.connect(self._on_harvest_parent_folder)
        folder_row.addWidget(self.btn_folder_parent)

        self.btn_folder_multi = PushButton(FIF.DOCUMENT, "폴더 여러 개 연속 추가", self)
        self.btn_folder_multi.setToolTip("폴더를 고를 때마다 목록에 쌓인 뒤, 한 번에 일괄 수집")
        self.btn_folder_multi.clicked.connect(self._on_harvest_multi_folders_pick)
        folder_row.addWidget(self.btn_folder_multi)

        folder_row.addStretch()

        grok_label = CaptionLabel("Grok 스토리:", self)
        folder_row.addWidget(grok_label)
        self.grok_switch = SwitchButton(self)
        grok_enabled = os.environ.get("JAVSTORY_STORY_ANALYSIS_ENABLED", "1").strip().lower()
        self.grok_switch.setChecked(grok_enabled in ("1", "true", "yes", "on"))
        self.grok_switch.checkedChanged.connect(self._on_grok_toggled)
        folder_row.addWidget(self.grok_switch)

        self.layout.addLayout(folder_row)

    def _init_status_board(self):
        # 스크롤 영역 설정
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        self.container = QWidget()
        self.container.setObjectName("HarvestContainer")
        self.container.setStyleSheet("#HarvestContainer { background: transparent; }")
        
        # FlowLayout: 카드가 창 너비에 맞춰 자동 재배치됨
        self.flow_layout = FlowLayout(self.container)
        self.flow_layout.setContentsMargins(0, 0, 0, 0)
        self.flow_layout.setSpacing(15)
        
        self.scroll_area.setWidget(self.container)
        self.layout.addWidget(self.scroll_area)

    def _on_search_clicked(self):
        text = self.search_edit.text().strip()
        if not text:
            return
            
        # 1. 쉼표(,), 세미콜론(;), 줄바꿈(\n), 공백(\s)으로 품번 분리
        skus = re.split(r'[,\s;\n]+', text)
        
        # 2. 공백 제거 및 중복 제거
        clean_skus = []
        seen = set()
        for s in skus:
            s_clean = s.strip().upper()
            if s_clean and s_clean not in seen:
                clean_skus.append(s_clean)
                seen.add(s_clean)
        
        # 3. 중복 수집 체크 (DB 및 로컬 JSON 캐시)
        session = get_db_session()
        final_skus = []
        try:
            for sku in clean_skus:
                # DB 존재 여부 확인
                exists = session.query(JAVMetadata).filter_by(product_code=sku).one_or_none()
                if exists and exists.title_ko and exists.cover_image_local_path:
                    InfoBar.warning("중복 항목", f"{sku}는 이미 수집되었습니다.", duration=2000, position=InfoBarPosition.BOTTOM_RIGHT, parent=self.window())
                    continue
                
                # 로컬 JSON 캐시 존재 여부 확인
                if (MEDIA_ROOT / sku / "metadata.json").exists():
                    InfoBar.info("캐시 발견", f"{sku}의 로컬 캐시가 있습니다. (즉시 복구 예정)", duration=2000, position=InfoBarPosition.BOTTOM_RIGHT, parent=self.window())
                
                final_skus.append(sku)
        finally:
            session.close()

        if not final_skus:
            self.search_edit.clear()
            return

        # 4. 각 품번별로 개별 수집 작업 추가
        for sku in final_skus:
            self._add_harvest_task(sku, is_path=False)
            
        self.search_edit.clear()

    def _on_batch_collect(self):
        """다중 품번을 한번에 입력받아 일괄 크롤."""
        text, ok = QInputDialog.getMultiLineText(
            self,
            "일괄 수집",
            "품번 목록을 입력하세요 (줄바꿈, 쉼표, 공백으로 구분):",
            "",
        )
        if not ok or not text.strip():
            return
        skus = re.split(r'[,\s;\n]+', text)
        clean = list(dict.fromkeys(s.strip().upper() for s in skus if s.strip()))
        if not clean:
            return
        for sku in clean:
            self._add_harvest_task(sku, is_path=False)
        InfoBar.success(
            "일괄 수집",
            f"{len(clean)}건 수집을 시작했습니다.",
            duration=2500,
            position=InfoBarPosition.BOTTOM_RIGHT,
            parent=self.window(),
        )

    def _run_planned_jobs(self, jobs, warnings: list[str], *, batch_label: str) -> None:
        win = self.window()
        for w in warnings:
            InfoBar.warning("Harvest", w, duration=4500, position=InfoBarPosition.BOTTOM_RIGHT, parent=win)
        if not jobs:
            InfoBar.info(
                "Harvest",
                "실행할 작업이 없습니다.",
                duration=2500,
                position=InfoBarPosition.BOTTOM_RIGHT,
                parent=win,
            )
            return
        entries = planned_to_worker_entries(jobs)
        key = jobs[0].product_code if len(jobs) == 1 else f"BATCH_{time.time_ns()}"
        self._launch_worker(key, entries)
        InfoBar.success(
            "Harvest",
            f"{len(jobs)}건 수집을 시작했습니다. ({batch_label})",
            duration=2200,
            position=InfoBarPosition.BOTTOM_RIGHT,
            parent=win,
        )

    def _on_harvest_single_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "작품 폴더 선택 (폴더명에 품번 포함)")
        if not d:
            return
        jobs, warns = plan_single_folder(Path(d))
        self._run_planned_jobs(jobs, warns, batch_label=Path(d).name)

    def _on_harvest_parent_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "상위 폴더 선택 (직하위 각 폴더 = 작품 1건)")
        if not d:
            return
        jobs, warns = plan_parent_folder(Path(d))
        self._run_planned_jobs(jobs, warns, batch_label=f"하위일괄:{Path(d).name}")

    def _on_harvest_multi_folders_pick(self) -> None:
        paths: list[Path] = []
        while True:
            d = QFileDialog.getExistingDirectory(self, "폴더 선택 (취소로 목록 확정)", str(Path.home()))
            if not d:
                break
            paths.append(Path(d))
            ret = QMessageBox.question(
                self,
                "폴더 추가",
                f"선택됨:\n{d}\n\n다른 폴더를 더 추가할까요?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if ret != QMessageBox.StandardButton.Yes:
                break
        if not paths:
            return
        jobs, warns = plan_folder_paths(paths)
        self._run_planned_jobs(jobs, warns, batch_label=f"{len(paths)}개 폴더")

    def _add_harvest_task(self, sku, is_path=False):
        """새로운 수집 작업을 추가하고 워커를 실행합니다."""
        # 1. 카드 UI 생성 (중복 체크 포함)
        self._create_card_only(sku)
        
        # 2. 워커 실행
        self._launch_worker(sku, [(sku, is_path, None)])

    def _create_card_only(self, sku):
        """카드 UI만 생성합니다. 이미 있으면 생성하지 않습니다."""
        if sku in self.cards:
            return
            
        card = HarvestCard(sku, self.container)
        self.cards[sku] = card
        self.flow_layout.addWidget(card)
        card.close_btn.clicked.connect(lambda: self._remove_card(sku))

    def _launch_worker(self, key: str, entries: list[tuple[str, bool, str | None]]):
        """실제 워커 스레드를 할당하고 실행합니다. `entries`: (target, is_path, product_code)."""
        # 기존 워커 정리
        if key in self.workers:
            old = self.workers.pop(key)
            if old in self._active_threads: self._active_threads.remove(old)
            old.stop(); old.wait(); old.deleteLater()

        # [수정] parent=self 를 전달하여 소유권 관계 명시
        worker = HarvestWorker(entries, parent=self)
        worker.progress.connect(self._on_worker_progress)
        worker.task_finished.connect(self._on_worker_finished)
        
        # [안정화] QThread 네이티브 종료 시점(OS 스레드 탈출)에 객체 파괴를 늦춤
        worker.finished.connect(lambda: self._on_worker_stopped(worker))
        
        self.workers[key] = worker
        self._active_threads.append(worker) # 강력 참조 (GC 방지)
        worker.start()

    def _remove_card(self, sku):
        if sku in self.cards:
            card = self.cards.pop(sku)
            self.flow_layout.removeWidget(card)
            card.deleteLater()
        
        # 워커도 함께 정리 (진행 중인 경우)
        if sku in self.workers:
            worker = self.workers.pop(sku)
            if worker in self._active_threads: 
                self._active_threads.remove(worker)
            worker.stop()
            # [안정화] 즉시 삭제 대신 지연 목록으로 이동
            self._finished_workers.append(worker)
            worker.deleteLater()

    @pyqtSlot(str, str, int)
    def _on_worker_progress(self, sku, message, percentage):
        # 카드가 없으면 UI만 생성 (워커 중복 실행 방지)
        if sku not in self.cards:
            self._create_card_only(sku)
            
        if sku in self.cards:
            self.cards[sku].update_status(message, percentage)
            
        # 로그 드로어에 기록
        main_win = self.window()
        if hasattr(main_win, 'log_drawer'):
            main_win.log_drawer.append_log(f"[{sku}] {message}")

    @pyqtSlot(str, bool, str)
    def _on_worker_finished(self, sku, success, message):
        """작업 완료 후 워커 정리 - QThread Destroyed 방지를 위해 지연 해제 도입"""
        # self.workers 키는 품번이 아닐 수 있음(BATCH_… 등) → 제거는 _on_worker_stopped에서 처리

        if sku in self.cards:
            self.cards[sku].update_status("수집 완료" if success else f"에러: {message}", 100 if success else 0)
            if not success:
                self.cards[sku].setStyleSheet("background: rgba(255, 59, 48, 0.1); border-left: 4px solid #FF3B30;")
                
        # 로그 드로어에 완료 기록
        main_win = self.window()
        if hasattr(main_win, 'log_drawer'):
            status_text = "성공" if success else f"실패 ({message})"
            main_win.log_drawer.append_log(f"[{sku}] 수집 공정 종료: {status_text}")

    def _on_worker_stopped(self, worker):
        """워커 스레드가 OS 레벨에서 완전히 종료된 후 호출됨"""
        if worker in self._active_threads:
            self._active_threads.remove(worker)

        for k, w in list(self.workers.items()):
            if w is worker:
                self.workers.pop(k, None)
                break
        
        # 완충 리스트에 보관하여 가비지 컬렉터의 급격한 수거 방어
        self._finished_workers.append(worker)
        worker.deleteLater()
        
        if len(self._finished_workers) > 30:
            self._finished_workers.pop(0)

    def _on_grok_toggled(self, checked):
        os.environ["JAVSTORY_STORY_ANALYSIS_ENABLED"] = "1" if checked else "0"

    def closeEvent(self, event):
        """화면 종료 시 모든 작업 안전하게 정지"""
        for worker in self._active_threads[:]:
            worker.stop()
            worker.wait()
        self._active_threads.clear()
        super().closeEvent(event)

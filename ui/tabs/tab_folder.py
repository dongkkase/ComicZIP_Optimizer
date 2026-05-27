import os
import sys
import subprocess
import traceback
import shutil
import csv
import zipfile
import xml.etree.ElementTree as ET
import hashlib
import difflib
import re
import time
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTreeView, 
    QTableView, QListView, QLabel, QPushButton, QSlider, QFrame, QMenu, QMessageBox,
    QHeaderView, QAbstractItemView, QSizePolicy, QDialog, QListWidget, QListWidgetItem, 
    QCheckBox, QDialogButtonBox, QStyledItemDelegate, QStackedWidget, QInputDialog, QToolButton, QStyleFactory,
    QComboBox, QStyle, QLineEdit, QFileDialog, QRubberBand, QTextBrowser, QProgressBar, QScrollArea, QLayout, QGridLayout
)

from PyQt6.QtGui import QFileSystemModel, QAction, QPixmap, QPainter, QColor, QFont, QKeySequence, QShortcut, QImage, QPixmapCache, QLinearGradient
from PyQt6.QtCore import Qt, QDir, QAbstractTableModel, QModelIndex, QSize, QByteArray, QItemSelectionModel, QItemSelection, QStandardPaths, QFileSystemWatcher, QTimer, QMimeData, QUrl, QThread, pyqtSignal, QRect, QPoint, QCoreApplication, QEventLoop

from config import get_resource_path, save_config
from core.library_db import db
from .tab_folder_threads import DupScanThread, IndexSyncThread, DupMatchThread, MemoryExtractThread, FolderScanThread, MissingCheckThread
from .tab_folder_models import CustomHeaderView, CustomTableView, ThumbnailDelegate, ColumnSelectDialog, LibraryTableModel
from .tab_folder_ui import GlowCard, FlowLayout, DetailBackgroundWidget
from ui.widgets import DimOverlay

from collections import defaultdict

# ==========================================
# [핵심 수정] i18n.py 구조에 맞춘 완벽한 다국어 처리 로직
# ==========================================
from core.i18n import get_i18n

_TRANSLATIONS = get_i18n()
_CURRENT_LANG = "ko"

def set_language(lang_code):
    global _CURRENT_LANG
    if lang_code in _TRANSLATIONS:
        _CURRENT_LANG = lang_code

def _(key):
    # 현재 언어의 딕셔너리에서 키를 찾고, 없으면 한국어에서 찾고, 그래도 없으면 키값 자체를 반환
    return _TRANSLATIONS.get(_CURRENT_LANG, _TRANSLATIONS["ko"]).get(key, key)




# ==========================================
# 탭 폴더 메인 클래스
# ==========================================
class TabFolder(QWidget):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.config = main_window.config
        
        # [핵심 추가] 초기 언어 설정 (config에서 불러옴)
        lang = self.config.get("language", self.config.get("lang", "ko"))
        set_language(lang)
        
        QPixmapCache.setCacheLimit(102400)
        
        self.scan_thread = None
        self.extract_thread = None
        self.force_update_flag = False
        
        self.file_data_cache = []
        self.file_data_map = {} 
        
        self.current_sort_key = self.config.get("folder_sort_key", "name")
        sort_order_int = self.config.get("folder_sort_order", 0) # 0: 오름차순, 1: 내림차순
        self.current_sort_order = Qt.SortOrder.AscendingOrder if sort_order_int == 0 else Qt.SortOrder.DescendingOrder
        self.current_group_key = "none"
        
        self.folder_watcher = QFileSystemWatcher(self)
        self.current_watched_folder = ""
        self.current_selected_path = ""

        self.sync_total_tasks = 0
        self.sync_completed_tasks = 0
        self.is_syncing = False
        self.is_force_syncing = False

        self.scroll_timer = QTimer()
        self.scroll_timer.setSingleShot(True)
        self.scroll_timer.timeout.connect(self._do_background_load)
        
        self.grouping_timer = QTimer()
        self.grouping_timer.setSingleShot(True)
        self.grouping_timer.timeout.connect(self.apply_grouping_and_sorting)
        self.folder_scan_cache = {}

        # --- [추가됨] 중복 검사용 캐시 및 스레드 변수 ---
        self.b_folder_cache = []
        self.dup_matches = {}
        self.dup_scan_thread = None
        self.dup_match_thread = None
        self.scan_overlay = None
        self._has_shown_global_missing_toast = False
        self._db_upsert_buffer = []
        # ----------------------------------------------

        self.main_status_label = None
        self.main_optimize_btn = None

        self.thumb_dir = os.path.join(get_resource_path("data"), "thumbnails")
        if not os.path.exists(self.thumb_dir):
            os.makedirs(self.thumb_dir, exist_ok=True)

        self.setup_ui()
        self.setup_menus()
        self.setup_hotkeys()
        
        QTimer.singleShot(100, self.load_initial_layout)
        QTimer.singleShot(500, self.find_main_window_elements)
        QTimer.singleShot(1000, self.start_dup_scan)

        # 시작 시 인덱스 감시기 설정 및 무결성 검사 예약
        self.setup_index_watcher()
        QTimer.singleShot(2000, self.start_index_update_task)

    def setup_index_watcher(self):
        """B 폴더 실시간 감시 설정 (디바운싱 적용)"""
        self.index_watcher = QFileSystemWatcher(self)
        self.index_debounce_timer = QTimer(self)
        self.index_debounce_timer.setSingleShot(True)
        self.index_debounce_timer.setInterval(5000) # 5초 디바운싱 (이벤트 종료 후 5초 뒤 1번 실행)
        self.index_debounce_timer.timeout.connect(self.start_index_update_task)
        self.index_watcher.directoryChanged.connect(self._on_index_dir_changed)

    def _on_index_dir_changed(self, path):
        # 앱 내부 삭제 작업 시엔 락이 걸려있으므로 트리거 무시
        if getattr(self, '_internal_action_lock', False): return
        self.index_debounce_timer.start()

    def start_index_update_task(self, force_rescan=False):
        """mtime 기반으로 변경사항이 있을 때만 하드를 읽고 인덱스를 갱신"""
        dup_folders = self.config.get("dup_check_folders", [])
        
        # 감시 대상 폴더 업데이트
        if hasattr(self, 'index_watcher'):
            if self.index_watcher.directories():
                self.index_watcher.removePaths(self.index_watcher.directories())
            for f in dup_folders:
                if os.path.exists(f): self.index_watcher.addPath(f)
                
        if not dup_folders: return

        needs_update = False
        last_mtimes = self.config.get("index_last_mtimes", {})
        current_mtimes = {}

        for folder in dup_folders:
            if os.path.exists(folder):
                mtime = os.stat(folder).st_mtime
                current_mtimes[folder] = mtime
                if force_rescan or mtime != last_mtimes.get(folder):
                    needs_update = True

        if needs_update:
            self.config["index_last_mtimes"] = current_mtimes
            save_config(self.config)
            
            target_exts = ('.zip', '.cbz', '.cbr', '.rar', '.7z')
            # 무거운 UI 스캔을 방해하지 않는 백그라운드 전용 스레드 가동
            self.index_sync_thread = IndexSyncThread(dup_folders, target_exts)
            self.index_sync_thread.start()
        else:
            if force_rescan:
                print("[LOG] 강제 갱신 요청됨")
            else:
                print("[LOG] 변경사항 없음. 디스크 스캔 건너뜀.")

    
    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent, Qt
        
        try:
            # C++ 객체가 메모리에서 이미 삭제되었는지 확인
            if not hasattr(self, 'table_view') or self.table_view is None:
                return super().eventFilter(obj, event)

            if obj is self.table_view and event.type() == QEvent.Type.Resize:
                if hasattr(self, 'dim_overlay'):
                    self.dim_overlay.resize(self.table_view.size())
        
            # [추가] 폴더 스캔 로딩 오버레이 크기 조절
            if obj is self.right_top_panel and event.type() == QEvent.Type.Resize:
                if hasattr(self, 'scan_overlay') and self.scan_overlay.isVisible():
                    self.scan_overlay.resize(self.right_top_panel.size())
                        
                # 헤더 영역의 마우스 커서 동적 변경
                header = self.table_view.horizontalHeader()
                
                # [핵심] header 자체뿐만 아니라 이벤트가 실제로 발생하는 viewport()까지 반드시 검사
                if obj is header or (header.viewport() and obj is header.viewport()):
                    
                    if event.type() in (QEvent.Type.MouseMove, QEvent.Type.HoverMove):
                        pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
                        idx = header.logicalIndexAt(pos)
                        if idx >= 0:
                            section_x = header.sectionViewportPosition(idx)
                            section_width = header.sectionSize(idx)
                            
                            # 우측 끝 영역(5px)은 컬럼 크기 조절을 위해 기본 커서 유지
                            if pos.x() >= section_x + section_width - 5:
                                cursor = Qt.CursorShape.SplitHCursor
                                header.setCursor(cursor)
                                if header.viewport(): header.viewport().setCursor(cursor)
                            
                            # 그립 아이콘 영역(좌측 25픽셀 이내)은 Grab(펼친 손) 커서
                            elif pos.x() - section_x <= 25:
                                cursor = Qt.CursorShape.OpenHandCursor
                                header.setCursor(cursor)
                                if header.viewport(): header.viewport().setCursor(cursor)
                                
                            # 나머지 텍스트 영역은 Pointer(클릭 손) 커서
                            else:
                                cursor = Qt.CursorShape.PointingHandCursor
                                header.setCursor(cursor)
                                if header.viewport(): header.viewport().setCursor(cursor)
                                
                    elif event.type() == QEvent.Type.Leave:
                        header.unsetCursor()
                        if header.viewport(): header.viewport().unsetCursor()
                        
                    elif event.type() == QEvent.Type.MouseButtonPress:
                        pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
                        idx = header.logicalIndexAt(pos)
                        if idx >= 0:
                            section_x = header.sectionViewportPosition(idx)
                            # 아이콘 영역 클릭 시 Grabbing(움켜쥔 손) 커서로 피드백
                            if pos.x() - section_x <= 25:
                                cursor = Qt.CursorShape.ClosedHandCursor
                                header.setCursor(cursor)
                                if header.viewport(): header.viewport().setCursor(cursor)
                                
                    elif event.type() == QEvent.Type.MouseButtonRelease:
                        pos = event.position().toPoint() if hasattr(event, 'position') else event.pos()
                        idx = header.logicalIndexAt(pos)
                        if idx >= 0:
                            section_x = header.sectionViewportPosition(idx)
                            if pos.x() - section_x <= 25:
                                cursor = Qt.CursorShape.OpenHandCursor
                            else:
                                cursor = Qt.CursorShape.PointingHandCursor
                            header.setCursor(cursor)
                            if header.viewport(): header.viewport().setCursor(cursor)
        
        except RuntimeError:
            # 객체가 이미 삭제된 상태에서 이벤트가 들어오는 경우 무시
            return False
            
        return super().eventFilter(obj, event)
    
    # --- [추가됨] 백그라운드 스레드 제어 메서드 ---
    def start_dup_scan(self):
        t = time.time()
        print(f"[LOG] start_dup_scan 진입: {time.time()-t:.3f}s")
        
        dup_folders = self.config.get("dup_check_folders", [])
        if not dup_folders: return
        target_exts = ('.zip', '.cbz', '.cbr', '.rar', '.7z')
        
        if self.dup_scan_thread and self.dup_scan_thread.isRunning():
            print(f"[LOG] 기존 DupScanThread 대기 중...")
            self.dup_scan_thread.cancel()
            self.dup_scan_thread.wait()
            print(f"[LOG] 기존 DupScanThread 종료 완료: {time.time()-t:.3f}s")
            
        self.lbl_tree_status.setText(_("dup_scan_start"))

        # [추가] 자세히 보기 모드일 때 리스트 패널 비활성화
        if self.view_stack.currentIndex() == 0 and self.btn_dup_check.isChecked():
            self.dim_overlay.show()
            
        self.dup_scan_thread = DupScanThread(dup_folders, target_exts)
        self.dup_scan_thread.progress_updated.connect(self.on_dup_scan_progress)
        self.dup_scan_thread.scan_finished.connect(self.on_dup_scan_finished)
        self.dup_scan_thread.start()
        print(f"[LOG] DupScanThread 시작 완료: {time.time()-t:.3f}s")

    def on_dup_scan_progress(self, match_count, total_scanned):
        msg = _("dup_scan_progress").format(total_scanned, match_count)
        self.lbl_tree_status.setText(msg)

    def on_dup_scan_finished(self, b_cache):
        self.b_folder_cache = b_cache
        
        msg = _("dup_scan_complete").format(len(b_cache))
        self.lbl_tree_status.setText(msg) # i18n 적용
        
        try:
            from ui.widgets import Toast
            Toast.show(self.main_window, msg)
        except:
            pass

        if self.file_data_cache:
            self.start_dup_match()
        else:
            # [추가] 매칭할 파일 데이터가 없어서 진행되지 않는 경우 오버레이 해제
            self.dim_overlay.hide()

        # [추가] 인덱싱(중복 스캔) 작업 완료 시 탐색기 패널의 선택된 폴더로 스크롤 포커싱
        target_path = getattr(self, 'current_watched_folder', None)
        if not target_path:
            target_path = self.config.get("folder_last_path", "")
            
        if target_path and os.path.exists(target_path):
            self._start_queued_scroll(target_path)

    # 중복 검사 토글 이벤트 처리
    def on_dup_check_toggled(self, checked):
        import time
        print(f"\n[LOG] =================================")
        print(f"[LOG] 중복 검사 버튼 토글 (checked={checked})")
        self.btn_dup_check.setText(_("folder_dup_check_on") if checked else _("folder_dup_check_off"))
        
        if checked:
            if not hasattr(self, 'b_folder_cache') or not self.b_folder_cache:
                print(f"[LOG] b_folder_cache 없음, start_dup_scan 호출")
                self.start_dup_scan()
            else:
                print(f"[LOG] b_folder_cache 존재, start_dup_match 호출")
                self.start_dup_match()
        else:
            print(f"[LOG] 버튼 OFF, 스레드 취소 및 렌더링 복구 시작")
            if hasattr(self, 'dup_match_thread') and self.dup_match_thread.isRunning():
                self.dup_match_thread.cancel()
                self.dup_match_thread.wait()
            # [추가] 버튼 OFF 시 즉시 활성화 복원
            self.dim_overlay.hide()
            self.apply_grouping_and_sorting()
            self.lbl_tree_status.setText(_("folder_ready"))

    def start_dup_match(self):
        import time
        t = time.time()
        print(f"[LOG] start_dup_match 진입: {time.time()-t:.3f}s")
        
        if not self.btn_dup_check.isChecked(): return
        if not hasattr(self, 'b_folder_cache') or not self.b_folder_cache: return
        if not hasattr(self, 'file_data_cache') or not self.file_data_cache: return
        
        current_a_paths = tuple(f.get("full_path") for f in self.file_data_cache)
        if hasattr(self, 'last_matched_a_paths') and self.last_matched_a_paths == current_a_paths:
            print(f"[LOG] 동일 데이터 감지, 캐시된 결과로 UI 갱신 시작")
            self.apply_grouping_and_sorting()
            count = sum(len(v) for v in getattr(self, 'dup_matches', {}).values())
            self.lbl_tree_status.setText(_("dup_match_found").format(count) if count > 0 else _("dup_match_none"))
            return
            
        self.last_matched_a_paths = current_a_paths
        
        # 이전 스레드 안전하게 종료
        if self.dup_match_thread and self.dup_match_thread.isRunning():
            self.dup_match_thread.cancel()
            self.dup_match_thread.wait()
            
        self.lbl_tree_status.setText(_("dup_match_start"))

        # 자세히 보기 모드일 때 리스트 패널 비활성화
        if self.view_stack.currentIndex() == 0:
            self.dim_overlay.show()
            
        self.dup_match_thread = DupMatchThread(self.file_data_cache, self.b_folder_cache)
        self.dup_match_thread.match_progress.connect(self.on_dup_match_progress)
        self.dup_match_thread.match_finished.connect(self.on_dup_match_finished)
        self.dup_match_thread.start()
        print(f"[LOG] DupMatchThread 시작 완료: {time.time()-t:.3f}s")
        

    # 매칭 진행 상황 표시
    def on_dup_match_progress(self, current, total):
        msg = _("dup_match_progress").format(current, total)
        self.lbl_tree_status.setText(msg)

    def on_dup_match_finished(self, matches):
        self.dup_matches = matches
        self.apply_grouping_and_sorting()
        
        count = sum(len(v) for v in matches.values())
        if count > 0:
            msg = _("dup_match_found").format(count)
        else:
            msg = _("dup_match_none")
            
        self.lbl_tree_status.setText(msg)
    # ----------------------------------------------


    def hideEvent(self, event):
        super().hideEvent(event)
        if hasattr(self, 'main_optimize_btn') and self.main_optimize_btn:
            self.main_optimize_btn.show()

    def find_main_window_elements(self):
        for lbl in self.main_window.findChildren(QLabel):
            if lbl.text() in ["대기 중...", "Ready", "待機中..."] or "대기 중" in lbl.text():
                self.main_status_label = lbl
                break
                
        for btn in self.main_window.findChildren(QPushButton):
            if "최적화" in btn.text() or "Optimize" in btn.text() or "最適化" in btn.text():
                self.main_optimize_btn = btn
                if self.isVisible(): 
                    self.main_optimize_btn.hide()
                break

    def get_active_view(self):
        return self.table_view if self.view_stack.currentIndex() == 0 else self.list_view

    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)

        splitter_style = """
            QSplitter::handle {
                background-color: #333333;
                border-radius: 2px;
                margin: 2px;
            }
            QSplitter::handle:horizontal {
                width: 4px;
                border-left: 1px dashed #666;
            }
            QSplitter::handle:vertical {
                height: 4px;
                border-top: 1px dashed #666;
            }
            QSplitter::handle:hover {
                background-color: #3498DB;
            }
        """
        self.main_splitter.setStyleSheet(splitter_style)
        self.main_splitter.setHandleWidth(8)

        toggle_btn_style = """
            QPushButton {
                background-color: #3a3a3a;
                color: #cccccc;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 5px 10px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
                color: white;
            }
            QPushButton:checked {
                background-color: #3498DB;
                color: white;
                border: 1px solid #2980B9;
                font-weight: bold;
            }
        """

        self.left_panel = QFrame()
        self.left_panel.setStyleSheet("QFrame { background-color: #2b2b2b; border-radius: 5px; border: 1px solid #444; }")
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(5, 5, 5, 5)
        
        expanding_policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.btn_subfolders = QPushButton(_("folder_inc_sub_off"))
        self.btn_subfolders.setCheckable(True)
        self.btn_subfolders.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_subfolders.setStyleSheet(toggle_btn_style)
        self.btn_subfolders.setSizePolicy(expanding_policy) 
        
        self.btn_dup_check = QPushButton(_("folder_dup_check_off"))
        self.btn_dup_check.setCheckable(True)
        self.btn_dup_check.setChecked(False)
        self.btn_dup_check.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_dup_check.setStyleSheet(toggle_btn_style)
        self.btn_dup_check.setSizePolicy(expanding_policy) 

        self.btn_refresh_tree = QPushButton(_("folder_refresh_tree"))
        self.btn_refresh_tree.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh_tree.setStyleSheet(toggle_btn_style)
        self.btn_refresh_tree.setSizePolicy(expanding_policy) 

        row1_layout = QHBoxLayout()
        row1_layout.setSpacing(5) 
        row1_layout.addWidget(self.btn_subfolders)
        row1_layout.addWidget(self.btn_dup_check)
        left_layout.addLayout(row1_layout)

        row2_layout = QHBoxLayout()
        row2_layout.addWidget(self.btn_refresh_tree)
        left_layout.addLayout(row2_layout)

        self.combo_quick_access = QComboBox()
        self.combo_quick_access.setStyleSheet("""
            QComboBox { background-color: #3a3a3a; color: white; border: 1px solid #555; border-radius: 4px; padding: 4px; margin-bottom: 5px; }
            QComboBox::drop-down { border: none; }
        """) 
        self.combo_quick_access.setCursor(Qt.CursorShape.PointingHandCursor)
        self.populate_quick_access()
        
        left_layout.addWidget(self.combo_quick_access)

        self.dir_model = QFileSystemModel()
        self.dir_model.setFilter(QDir.Filter.NoDotAndDotDot | QDir.Filter.AllDirs)
        self.dir_model.setRootPath("") 
        
        self.tree_view = QTreeView()
        self.tree_view.setModel(self.dir_model)
        self.tree_view.setRootIndex(self.dir_model.index(""))
        self.tree_view.setHeaderHidden(True)
        self.tree_view.setAnimated(True)
        self.tree_view.setIndentation(15)
        
        # 텍스트 말줄임표 처리 방지 및 가로 스크롤 활성화
        self.tree_view.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.tree_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        # 마지막 열이 뷰포트 너비에 맞춰 강제로 늘어나는 기본 동작 해제 (가로 스크롤을 위해 필수)
        self.tree_view.header().setStretchLastSection(False)
        self.tree_view.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)

        self.tree_view.setStyle(QStyleFactory.create("Fusion"))
        self.tree_view.setStyleSheet("""
            QTreeView { border: none; background-color: transparent; outline: none; color: white; } 
            QTreeView::item:hover { background-color: #3a3a3a; } 
            QTreeView::item:selected { background-color: #3a7ebf; color: white; }
        """)
        for i in range(1, 4): self.tree_view.hideColumn(i)
        left_layout.addWidget(self.tree_view)

        self.btn_check_missing = QPushButton(_("tf_btn_check_missing"))
        self.btn_check_missing.setStyleSheet(toggle_btn_style)
        self.btn_check_missing.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_check_missing.clicked.connect(self.show_missing_volumes_dialog)
        left_layout.addWidget(self.btn_check_missing)

        self.right_splitter = QSplitter(Qt.Orientation.Vertical)
        self.right_splitter.setStyleSheet(splitter_style)
        self.right_splitter.setHandleWidth(8)
        
        self.right_top_panel = QFrame()
        self.right_top_panel.setObjectName("RightTopPanel")
        self.right_top_panel.installEventFilter(self)
        self.right_top_panel.setStyleSheet("QFrame#RightTopPanel { background-color: #2b2b2b; border-radius: 5px; border: 1px solid #444; }")
        right_top_layout = QVBoxLayout(self.right_top_panel)
        right_top_layout.setContentsMargins(5, 5, 5, 5)

        list_toolbar = QHBoxLayout()
        
        self.btn_sidebar = QPushButton(_("folder_sidebar_on"))
        self.btn_sidebar.setCheckable(True)
        self.btn_sidebar.setChecked(True)
        self.btn_sidebar.setStyleSheet(toggle_btn_style)
        
        menu_btn_style = """
            QToolButton { background-color: transparent; color: white; padding: 5px; font-weight: bold; border: none; }
            QToolButton:hover { color: #3498DB; }
            QToolButton::menu-indicator { image: none; }
        """
        
        self.btn_views = QToolButton()
        self.btn_views.setText(_("folder_views"))
        self.btn_views.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_views.setStyleSheet(menu_btn_style)
        
        self.btn_grouped = QToolButton()
        self.btn_grouped.setText(_("folder_grouped"))
        self.btn_grouped.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_grouped.setStyleSheet(menu_btn_style)

        self.btn_filter = QToolButton()
        self.btn_filter.setText(_("folder_filter"))
        self.btn_filter.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_filter.setStyleSheet(menu_btn_style)

        self.btn_sorted = QToolButton()
        self.btn_sorted.setText(_("folder_sorted"))
        self.btn_sorted.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_sorted.setStyleSheet(menu_btn_style)

        self.btn_layouts = QToolButton()
        self.btn_layouts.setText(_("folder_layouts"))
        self.btn_layouts.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_layouts.setStyleSheet(menu_btn_style)
        
        self.btn_export = QPushButton(_("folder_export_csv"))
        self.btn_export.setStyleSheet(toggle_btn_style)
        
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText(_("folder_search_ph"))
        self.search_bar.setClearButtonEnabled(True)
        self.search_bar.setFixedWidth(220)
        self.search_bar.setStyleSheet("""
            QLineEdit { background-color: #1e1e1e; color: white; border: 1px solid #555; border-radius: 12px; padding: 4px 10px; }
            QLineEdit:focus { border: 1px solid #3498DB; }
        """)
        
        self.btn_refresh_list = QPushButton(_("folder_refresh_list"))
        self.btn_refresh_list.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.btn_sidebar.setCursor(Qt.CursorShape.PointingHandCursor)
        list_toolbar.addWidget(self.btn_sidebar)
        
        for btn in [self.btn_views, self.btn_grouped, self.btn_filter, self.btn_sorted, self.btn_layouts, self.btn_export]:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            list_toolbar.addWidget(btn)
            
        list_toolbar.addStretch()
        list_toolbar.addWidget(self.search_bar)
        list_toolbar.addWidget(self.btn_refresh_list)
        right_top_layout.addLayout(list_toolbar)

        self.view_stack = QStackedWidget()
        self.table_model = LibraryTableModel(thumb_dir=self.thumb_dir)
        self.item_delegate = ThumbnailDelegate(self.view_stack, self.thumb_dir)
        
        self.table_view = CustomTableView()
        # [추가] 커스텀 헤더 뷰 장착
        self.table_view.setHorizontalHeader(CustomHeaderView(Qt.Orientation.Horizontal, self.table_view))
        self.table_view.setModel(self.table_model)
        self.table_view.installEventFilter(self)
        self.table_view.setItemDelegate(self.item_delegate)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table_view.verticalHeader().hide()
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setSortingEnabled(False) 
        self.table_view.horizontalHeader().setSortIndicatorShown(True)
        self.table_view.horizontalHeader().setSectionsMovable(True)
        
        self.table_model.table_view = self.table_view
        
        header = self.table_view.horizontalHeader()
        
        # (기존에 있던 header.setIconSize(QSize(1000, 60)) 코드는 삭제합니다)
        
        # 헤더와 뷰포트 양쪽에 이벤트 필터와 마우스 트래킹 동시 적용
        header.setMouseTracking(True)
        header.installEventFilter(self)
        if header.viewport():
            header.viewport().setMouseTracking(True)
            header.viewport().installEventFilter(self)
        
        self.table_view.setStyleSheet("""
            QTableView { 
                border: none; 
                background-color: transparent; 
                color: white; 
            }
            QHeaderView::section {
                background-color: #2b2b2b;
                padding: 4px 8px;
                border: 1px solid #444;
                border-radius: 4px;
                margin:2px 1px;
            }
            QHeaderView::section:hover {
                background-color: #3a3a3a; 
            }
            QHeaderView::section:pressed {
                background-color: #4a4a4a;
            }
        """)

        self.table_view.setDragEnabled(False)
        self.table_view.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self.table_view.verticalHeader().setDefaultSectionSize(64) 
        self.table_view.setIconSize(QSize(45, 60)) 
        
        self.dim_overlay = DimOverlay(self.table_view)

        self.list_view = QListView()
        self.list_view.setModel(self.table_model)
        self.list_view.setItemDelegate(self.item_delegate)
        self.list_view.setViewMode(QListView.ViewMode.IconMode)
        self.list_view.setResizeMode(QListView.ResizeMode.Adjust)
        self.list_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_view.setSelectionRectVisible(True)
        # 기존 10이었던 마진을 0으로 줄임
        self.list_view.setSpacing(0)
        self.list_view.setWordWrap(True)
        self.list_view.setStyleSheet("QListView { border: none; background-color: transparent;  color: white; }")
        self.list_view.setDragEnabled(False)
        self.list_view.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        
        # 아이템 호버 효과를 위해 마우스 트래킹 켜기 (확대 애니메이션 연동)
        self.list_view.setMouseTracking(True)
        self.list_view.entered.connect(self.list_view.viewport().update)

        self.table_view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table_view.verticalScrollBar().setSingleStep(15)
        self.list_view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list_view.verticalScrollBar().setSingleStep(15)

        self.view_stack.addWidget(self.table_view)
        self.view_stack.addWidget(self.list_view)
        self.view_stack.hide() # 초기에 데이터가 없을 때는 숨김 처리
        right_top_layout.addWidget(self.view_stack)

        # --- [추가] 빈 상태 표시 라벨 ---
        self.lbl_empty_state = QLabel(_("t3_no_data"))
        self.lbl_empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_empty_state.setStyleSheet(f"color: #888888; font-size: {self.config.get('s16', 16)}px; font-weight: bold;")
        self.lbl_empty_state.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        right_top_layout.addWidget(self.lbl_empty_state)
        # ------------------------------
        
        # --- [추가] 폴더 스캔 로딩 오버레이 ---
        self.scan_overlay = DimOverlay(self.right_top_panel, show_spinner=True, text=_("folder_scan_prep"))
        self.scan_overlay.setStyleSheet("QLabel { border: none; background-color: transparent; }")
        self.scan_overlay.hide()
        # ------------------------------------

        # ---------------- 네이티브 디자인 레이아웃 적용 (우측 하단 패널) ----------------
        # from ui.widgets import DetailBackgroundWidget
        self.right_bottom_panel = DetailBackgroundWidget()
        self.right_bottom_panel.setObjectName("RightBottomPanel")

        outer = QHBoxLayout(self.right_bottom_panel)
        outer.setContentsMargins(28, 22, 28, 22)
        outer.setSpacing(28)

        # ── 커버 이미지 컬럼 ─────────────────────────────────────────
        cover_col = QVBoxLayout()
        cover_col.setContentsMargins(0, 0, 0, 0)
        cover_col.setSpacing(0)

        self.lbl_cover = QLabel(_("folder_cover_img"))
        # self.lbl_cover = CoverLabel(_("folder_cover_img"))

        self.lbl_cover.setFixedSize(220, 310)
        self.lbl_cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_cover.setStyleSheet(
            "background-color: #1a1a1a; border: 1px solid #3a3a3a;"
            "border-radius: 10px; color: #666666;"
        )
        cover_col.addWidget(self.lbl_cover)
        cover_col.addStretch()
        outer.addLayout(cover_col)

        # ── 우측 전체: 스크롤 ────────────────────────────────────────
        self.info_scroll = QScrollArea()
        self.info_scroll.setWidgetResizable(True)
        self.info_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.info_scroll.setStyleSheet(
            "QScrollArea { background-color: transparent; border: none; }"
        )
        self.info_scroll.viewport().setStyleSheet("background-color: transparent;")

        self.info_content = QWidget()
        self.info_content.setObjectName("info_content")
        self.info_content.setStyleSheet("QWidget#info_content { background-color: transparent; }")

        self.info_layout = QVBoxLayout(self.info_content)
        self.info_layout.setContentsMargins(0, 0, 0, 0)
        self.info_layout.setSpacing(10)

        # 시리즈명
        self.lbl_series_info = QLabel()
        self.lbl_series_info.setStyleSheet(
            f"color: #E8A020; font-size: {self.config['s16']}px; font-weight: bold; background: transparent;margin-bottom:-3px"
        )
        self.lbl_series_info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        # 제목
        self.lbl_info_title = QLabel()
        self.lbl_info_title.setStyleSheet(
            f"color: #FFFFFF; font-size: {self.config['s30']}px; font-weight: bold; background: transparent;"
        )
        self.lbl_info_title.setWordWrap(True)
        self.lbl_info_title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)



        # 태그 FlowLayout
        self.tag_container = QWidget()
        self.tag_container.setStyleSheet("background: transparent;")
        self.tag_container.setContentsMargins(0, 0, 0, 0)
        self.tag_layout = FlowLayout(self.tag_container, margin=0, spacing=6)

        self.info_layout.addWidget(self.lbl_series_info)
        self.info_layout.addWidget(self.lbl_info_title)
        self.info_layout.addSpacing(0)
        self.info_layout.addWidget(self.tag_container)

        # ── 단일 큰 카드: 메타(좌) + 줄거리&추가정보(우) ────────────
        # big_card = QWidget()
        big_card = GlowCard()
        big_card.setObjectName("big_card")
        big_card.setStyleSheet(
            "QWidget#big_card {"
            "  background-color: rgba(40, 40, 40, 0.75);"
            "  border: 1px solid rgba(255,255,255,0.08);"
            "  border-radius: 12px;"
            "  margin-top:0px;"
            "}"
        )

        card_hbox = QHBoxLayout(big_card)
        card_hbox.setContentsMargins(0, 0, 0, 0)
        card_hbox.setSpacing(0)

        # 좌: 메타 1열 리스트
        meta_widget = QWidget()
        meta_widget.setObjectName("meta_widget")
        meta_widget.setStyleSheet("QWidget#meta_widget { background: transparent; }")
        meta_vbox = QVBoxLayout(meta_widget)
        meta_vbox.setContentsMargins(15, 10, 15, 10)
        meta_vbox.setSpacing(0)

        self.meta_grid_widget = QWidget()
        self.meta_grid_widget.setStyleSheet("background: transparent;")
        self.meta_grid_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)  # ← 추가
        self.meta_grid = QGridLayout(self.meta_grid_widget)
        self.meta_grid.setContentsMargins(0, 0, 0, 0)
        self.meta_grid.setHorizontalSpacing(16)
        self.meta_grid.setVerticalSpacing(0)
        self.meta_grid.setColumnStretch(0, 1)

        meta_vbox.addWidget(self.meta_grid_widget)
        meta_vbox.addStretch()

        # 세로 구분선
        vline = QWidget()
        vline.setFixedWidth(1)
        vline.setStyleSheet("background-color: rgba(255,255,255,0.05);")

        # 우: 줄거리 + 추가정보
        right_widget = QWidget()
        right_widget.setObjectName("right_widget")
        right_widget.setStyleSheet("QWidget#right_widget { background: transparent; }")
        right_vbox = QVBoxLayout(right_widget)
        right_vbox.setContentsMargins(20, 18, 20, 18)
        right_vbox.setSpacing(8)

        # 줄거리 헤더
        self.summary_title_widget = QWidget()
        self.summary_title_widget.setStyleSheet("background: transparent;")
        self.summary_title_layout = QHBoxLayout(self.summary_title_widget)
        self.summary_title_layout.setContentsMargins(0, 0, 0, 0)
        self.summary_title_layout.setSpacing(6)

        self.lbl_summary_icon = QLabel()
        self.lbl_summary_title = QLabel(_("col_summary"))
        self.lbl_summary_title.setStyleSheet(
            f"color: #E8A020; font-weight: bold; font-size: {self.config['s12']}px; background: transparent;"
        )
        self.summary_title_layout.addWidget(self.lbl_summary_icon)
        self.summary_title_layout.addWidget(self.lbl_summary_title)
        self.summary_title_layout.addStretch()

        # 줄거리 본문
        self.lbl_summary = QLabel()
        self.lbl_summary.setStyleSheet(
            f"color: #cccccc; font-size: {self.config['s12']}px; background: transparent; line-height: 1.6;"
        )
        self.lbl_summary.setWordWrap(True)
        self.lbl_summary.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.lbl_summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        right_vbox.addWidget(self.summary_title_widget)
        right_vbox.addWidget(self.lbl_summary)

        # 추가정보 동적 레이아웃 (스토리아크 / 등장인물 / 링크)
        self.extra_layout = QVBoxLayout()
        self.extra_layout.setContentsMargins(0, 10, 0, 0)
        self.extra_layout.setSpacing(1)
        right_vbox.addLayout(self.extra_layout)
        right_vbox.addStretch()

        card_hbox.addWidget(meta_widget, 5)
        card_hbox.addWidget(vline)
        card_hbox.addWidget(right_widget, 6)

        self.info_layout.addWidget(big_card, 1)
        self.info_layout.addStretch()

        self.info_scroll.setWidget(self.info_content)
        outer.addWidget(self.info_scroll, 1)

        self.right_splitter.addWidget(self.right_top_panel)
        self.right_splitter.addWidget(self.right_bottom_panel)
        self.right_splitter.setStretchFactor(0, 3)
        self.right_splitter.setStretchFactor(1, 1)

        self.right_bottom_panel.hide()
        # ------------------------------------------------


        self.main_splitter.addWidget(self.left_panel)
        self.main_splitter.addWidget(self.right_splitter)
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 4)
        self.main_layout.addWidget(self.main_splitter, 1)

        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(5, 0, 5, 0)
        
        self.lbl_tree_status = QLabel(_("folder_ready"))
        self.lbl_tree_status.setStyleSheet(f"color: #aaaaaa; font-size: {self.config['s12']}px;")
        bottom_bar.addWidget(self.lbl_tree_status)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(12)
        self.progress_bar.setFixedWidth(150)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{ border: 1px solid #444; border-radius: 6px; background-color: #2b2b2b; }}
            QProgressBar::chunk {{ background-color: #3498DB; border-radius: 5px; }}
        """)
        self.progress_bar.hide()
        bottom_bar.addWidget(self.progress_bar)
        
        bottom_bar.addStretch()
        
        self.slider_item_size = QSlider(Qt.Orientation.Horizontal)
        self.slider_item_size.setRange(80, 300)
        self.slider_item_size.setValue(120)
        self.slider_item_size.setFixedWidth(200)
        bottom_bar.addWidget(QLabel(_("folder_item_size")))
        bottom_bar.addWidget(self.slider_item_size)
        
        self.main_layout.addLayout(bottom_bar)
        
        self.btn_sidebar.toggled.connect(self.toggle_sidebar)
        self.btn_sidebar.toggled.connect(lambda checked: self.btn_sidebar.setText(_("folder_sidebar_on") if checked else _("folder_sidebar_off")))
        self.btn_refresh_tree.clicked.connect(self.refresh_tree)
        self.btn_refresh_list.clicked.connect(self.refresh_list)
        self.btn_subfolders.toggled.connect(self.refresh_list)
        self.btn_subfolders.toggled.connect(lambda checked: self.btn_subfolders.setText(_("folder_inc_sub_on") if checked else _("folder_inc_sub_off")))

        self.btn_dup_check.toggled.connect(self.on_dup_check_toggled)
        
        self.slider_item_size.valueChanged.connect(self.on_size_changed)
        self.tree_view.selectionModel().selectionChanged.connect(self.on_tree_selection_changed)
        self.table_view.selectionModel().selectionChanged.connect(self.on_file_selection_changed)
        self.list_view.selectionModel().selectionChanged.connect(self.on_file_selection_changed)
        self.table_view.horizontalHeader().sectionMoved.connect(self.save_current_layout_state)
        self.table_view.horizontalHeader().sectionClicked.connect(self.on_header_clicked)
        self.combo_quick_access.currentIndexChanged.connect(self.on_quick_access_changed)

        self.table_view.horizontalHeader().sectionClicked.connect(
            lambda: self.table_model.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, len(self.table_model.active_columns) - 1)
        )

        self.folder_watcher.directoryChanged.connect(self.on_watched_folder_changed)
        self.search_bar.textChanged.connect(self.on_search_text_changed)
        self.table_view.doubleClicked.connect(self.open_viewer)
        self.list_view.doubleClicked.connect(self.open_viewer)
        self.main_splitter.splitterMoved.connect(self.save_splitter_states)
        self.right_splitter.splitterMoved.connect(self.save_splitter_states)
        self.btn_export.clicked.connect(self.export_csv)
        
        self.table_view.verticalScrollBar().valueChanged.connect(lambda: self.scroll_timer.start(100))
        self.list_view.verticalScrollBar().valueChanged.connect(lambda: self.scroll_timer.start(100))
        self.view_stack.currentChanged.connect(lambda: self.scroll_timer.start(50))

    def _requires_full_metadata(self):
        return self.current_group_key in ["series", "writer"] or self.current_sort_key in ["series", "writer", "title"]

    def _do_background_load(self):
        if self.is_force_syncing:
            return

        if self.extract_thread and self.extract_thread.isRunning():
            return

        view = self.get_active_view()
        rect = view.viewport().rect()
        target_exts = ('.zip', '.cbz', '.cbr', '.rar', '.7z')
        
        selected_paths = set(self.get_selected_files())
        visible_tasks = []
        hidden_tasks = []
        
        for r in self.table_model._data:
            # [수정됨] 그룹 헤더뿐만 아니라 중복 파일 표기용 가짜 행들도 추출 스캔 대상에서 완벽히 스킵합니다.
            if r.get("is_group") or r.get("is_dup_folder") or r.get("is_dup_child"): continue
            
            fp = r.get("full_path", "")
            if not fp.lower().endswith(target_exts): continue
            
            has_img = r.get("thumb_processed")
            has_meta = r.get("meta_processed")
            has_res = bool(r.get("res"))
            
            if has_img and has_meta and has_res: continue
            if has_img and has_meta: continue
            
            disp_idx = r.get("display_index", -1)
            if disp_idx >= 0:
                idx = self.table_model.index(disp_idx, 0)
                is_visible = view.visualRect(idx).intersects(rect) and view.visualRect(idx).isValid()
            else:
                is_visible = False
                
            is_selected = fp in selected_paths
            needs_img = not has_img or not has_res
            needs_img = not has_img
            needs_meta = not has_meta
            
            thumb_path = os.path.join(self.thumb_dir, f"{r.get('hash', '')}.webp")
            task = (fp, needs_img, needs_meta, thumb_path)
            
            if is_visible or is_selected:
                visible_tasks.append(task)
            else:
                hidden_tasks.append(task)
                
        if not visible_tasks and not hidden_tasks:
            self.is_syncing = False
            self.progress_bar.hide()
            if hasattr(self, 'main_status_label') and self.main_status_label:
                self.main_status_label.setText(self.i18n.get("folder_ready", "Ready") if hasattr(self, 'i18n') else "Ready")
            return

        tasks = (visible_tasks + hidden_tasks)[:50] 
        real_heavy_tasks_count = sum(1 for t in tasks if t[2] or (t[1] and not os.path.exists(t[3])))
        
        if not self.is_syncing and real_heavy_tasks_count > 0:
            total_heavy = sum(1 for r in self.table_model._data if not r.get("is_group") and not r.get("is_dup_folder") and not r.get("is_dup_child") and not r.get("meta_processed") and r.get("full_path", "").lower().endswith(target_exts))
            self.sync_total_tasks = total_heavy
            self.sync_completed_tasks = 0
            self.is_syncing = True

        seven_zip_path = get_resource_path('7za.exe')
        self.extract_thread = MemoryExtractThread(tasks, seven_zip_path)
        self.extract_thread.show_progress = (real_heavy_tasks_count > 0)
        self.extract_thread.data_extracted.connect(self.on_metadata_extracted)
        self.extract_thread.progress_updated.connect(self.on_extract_progress)
        self.extract_thread.finished.connect(self._on_extract_thread_finished)
        self.extract_thread.start()

    def on_extract_progress(self, count):
        if not self.is_syncing and not self.is_force_syncing: return
        
        self.sync_completed_tasks += count
        if self.sync_completed_tasks > self.sync_total_tasks:
            self.sync_completed_tasks = self.sync_total_tasks

        self.progress_bar.show()
        self.progress_bar.setMaximum(self.sync_total_tasks)
        self.progress_bar.setValue(self.sync_completed_tasks)
        
        status_text = _("folder_optimizing").format(self.sync_completed_tasks, self.sync_total_tasks)
        if hasattr(self, 'main_status_label') and self.main_status_label:
            self.main_status_label.setText(status_text)
            
        if self.sync_completed_tasks >= self.sync_total_tasks:
            self.progress_bar.hide()
            self.is_syncing = False
            self.is_force_syncing = False
            if hasattr(self, 'main_status_label') and self.main_status_label:
                self.main_status_label.setText(_("folder_ready"))

    def force_update_selected_files(self):
        paths = self.get_selected_files()
        if not paths: return
        
        target_exts = ('.zip', '.cbz', '.cbr', '.rar', '.7z')
        tasks = []
        
        for fp in paths:
            row = self.file_data_map.get(fp)
            if row and fp.lower().endswith(target_exts):
                file_hash = row.get("hash", "")
                if file_hash:
                    thumb_path = os.path.join(self.thumb_dir, f"{file_hash}.webp")
                    if os.path.exists(thumb_path):
                        try: os.remove(thumb_path)
                        except: pass
                    QPixmapCache.remove(file_hash)
                
                row["meta_processed"] = False
                row["thumb_processed"] = False
                row["res"] = ""
                row["full_meta"] = {}
                
                tasks.append((fp, True, True, thumb_path))
                
        if not tasks: return

        if self.extract_thread and self.extract_thread.isRunning():
            self.extract_thread.cancel()
            self.extract_thread.wait()
            self.extract_thread = None
            
        self.scroll_timer.stop()
        self.is_force_syncing = True 
        self.is_syncing = False 

        self.sync_total_tasks = len(tasks)
        self.sync_completed_tasks = 0
        
        self.apply_grouping_and_sorting()
        
        seven_zip_path = get_resource_path('7za.exe')
        self.extract_thread = MemoryExtractThread(tasks, seven_zip_path)
        self.extract_thread.show_progress = True
        self.extract_thread.data_extracted.connect(self.on_metadata_extracted)
        self.extract_thread.progress_updated.connect(self.on_extract_progress)
        self.extract_thread.finished.connect(self._flush_db_buffer)
        self.extract_thread.start()

    def export_csv(self):
        if not self.table_model._data:
            QMessageBox.information(self, "Export", _("dlg_exp_no_data"))
            return
            
        filepath, _ = QFileDialog.getSaveFileName(self, _("dlg_exp_title"), "My_Library_Export.csv", "CSV Files (*.csv)")
        if not filepath:
            return
            
        try:
            header = self.table_view.horizontalHeader()
            visual_cols = []
            for i in range(header.count()):
                logical_idx = header.logicalIndex(i)
                visual_cols.append(self.table_model.active_columns[logical_idx])

            with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                headers = [self.table_model.ALL_COLUMNS[col] for col in visual_cols]
                writer.writerow(headers)
                
                for row in self.table_model._data:
                    if row.get("is_group"): continue
                    row_data = [str(row.get(col, "")) for col in visual_cols]
                    writer.writerow(row_data)
                    
            QMessageBox.information(self, "Export", _("dlg_exp_done"))
        except Exception as e:
            QMessageBox.critical(self, "Export Error", _("dlg_err_occurred").format(e))

    def save_splitter_states(self, pos=0, index=0):
        self.config["folder_main_splitter"] = self.main_splitter.saveState().toHex().data().decode()
        self.config["folder_right_splitter"] = self.right_splitter.saveState().toHex().data().decode()
        save_config(self.config)

    def on_search_text_changed(self, text):
        self.apply_grouping_and_sorting()

    def on_watched_folder_changed(self, path):
        if getattr(self, '_internal_action_lock', False): return
        
        # --- [추가] 캐시 무효화 ---
        for sub_included in [True, False]:
            cache_key = (path, sub_included)
            if cache_key in self.folder_scan_cache:
                del self.folder_scan_cache[cache_key]
        # ------------------------

        if self.current_watched_folder == path:
            self.refresh_list(force_update=False)

    def populate_quick_access(self):
        self.combo_quick_access.blockSignals(True)
        self.combo_quick_access.clear()
        self.combo_quick_access.addItem(_("folder_quick_access"), "")
        paths = [
            (_("folder_desktop"), QStandardPaths.StandardLocation.DesktopLocation),
            (_("folder_docs"), QStandardPaths.StandardLocation.DocumentsLocation),
            (_("folder_downloads"), QStandardPaths.StandardLocation.DownloadLocation),
            (_("folder_home"), QStandardPaths.StandardLocation.HomeLocation),
        ]
        for name, loc in paths:
            path = QStandardPaths.writableLocation(loc)
            if path: self.combo_quick_access.addItem(name, path)

        lib_folders = self.config.get("dup_check_folders", [])
        if lib_folders:
            self.combo_quick_access.insertSeparator(self.combo_quick_access.count())
            for folder in lib_folders:
                folder_name = os.path.basename(folder)
                if not folder_name: folder_name = folder
                self.combo_quick_access.addItem(f"📚 {folder_name}", folder)

        custom_favs = self.config.get("folder_favorites", [])
        if custom_favs:
            self.combo_quick_access.insertSeparator(self.combo_quick_access.count())
            for fav in custom_favs:
                fav_name = fav.get("name", os.path.basename(fav["path"]))
                if not fav_name: fav_name = fav["path"]
                self.combo_quick_access.addItem(f"📌 {fav_name}", fav["path"])

        self.combo_quick_access.blockSignals(False)

    def add_to_favorites(self, path):
        custom_favs = self.config.get("folder_favorites", [])
        if not any(f["path"] == path for f in custom_favs):
            name = os.path.basename(path)
            if not name: name = path
            custom_favs.append({"name": name, "path": path})
            self.config["folder_favorites"] = custom_favs
            save_config(self.config)
            self.populate_quick_access()

    def remove_from_favorites(self, path):
        custom_favs = self.config.get("folder_favorites", [])
        custom_favs = [f for f in custom_favs if f["path"] != path]
        self.config["folder_favorites"] = custom_favs
        save_config(self.config)
        self.populate_quick_access()

    def on_quick_access_changed(self, index):
        path = self.combo_quick_access.itemData(index)
        if path and os.path.exists(path):
            idx = self.dir_model.index(path)
            self.tree_view.setCurrentIndex(idx)
            self.tree_view.scrollTo(idx)
            self.tree_view.expand(idx)
            self.refresh_list()

    def setup_menus(self):
        self.menu_views = QMenu(self)
        self.menu_views.addAction(_("menu_detail"), lambda: self.set_view_mode("detail"))
        self.menu_views.addAction(_("menu_thumbnail"), lambda: self.set_view_mode("thumbnail"))
        self.menu_views.addAction(_("menu_tile"), lambda: self.set_view_mode("tile"))
        self.btn_views.setMenu(self.menu_views)

        self.menu_grouped = QMenu(self)
        self.menu_grouped.addAction(_("menu_none"), lambda: self.set_grouping("none"))
        self.menu_grouped.addAction(_("menu_folder"), lambda: self.set_grouping("path"))
        self.menu_grouped.addAction(_("col_ext"), lambda: self.set_grouping("ext"))
        self.menu_grouped.addAction(_("col_series"), lambda: self.set_grouping("series"))
        self.menu_grouped.addAction(_("col_writer"), lambda: self.set_grouping("writer"))
        self.btn_grouped.setMenu(self.menu_grouped)

        self.menu_filter = QMenu(self)
        self.action_filter_no_meta = QAction(_("filter_no_meta"), self, checkable=True)
        self.action_filter_no_meta.toggled.connect(self._on_filter_toggled)
        self.menu_filter.addAction(self.action_filter_no_meta)
        self.btn_filter.setMenu(self.menu_filter)

        self.menu_sorted = QMenu(self)
        self.menu_sorted.addAction(_("col_name"), lambda: self.set_sorting("name"))
        self.menu_sorted.addAction(_("col_size"), lambda: self.set_sorting("size"))
        self.menu_sorted.addAction(_("col_mtime"), lambda: self.set_sorting("mtime"))
        self.menu_sorted.addAction(_("col_ext"), lambda: self.set_sorting("ext"))
        self.menu_sorted.addAction(_("col_series"), lambda: self.set_sorting("series"))
        self.menu_sorted.addAction(_("col_title"), lambda: self.set_sorting("title"))
        self.menu_sorted.addAction(_("col_writer"), lambda: self.set_sorting("writer"))
        self.menu_sorted.addSeparator()
        self.menu_sorted.addAction(_("menu_toggle_order"), self.toggle_sort_order)
        self.btn_sorted.setMenu(self.menu_sorted)

        self.menu_layouts = QMenu(self)
        self.btn_layouts.setMenu(self.menu_layouts)
        self.update_layouts_menu()

        self.tree_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_view.customContextMenuRequested.connect(self.show_tree_context_menu)
        self.table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(self.show_list_context_menu)
        self.list_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_view.customContextMenuRequested.connect(self.show_list_context_menu)

    def setup_hotkeys(self):
        QShortcut(QKeySequence("F5"), self).activated.connect(self.refresh_tree)
        QShortcut(QKeySequence("Ctrl+A"), self).activated.connect(self.select_all_files)
        # F1~F3은 탭 전송으로 통일
        QShortcut(QKeySequence("F1"), self).activated.connect(self.send_to_tab1)
        QShortcut(QKeySequence("F2"), self).activated.connect(self.send_to_tab2)
        QShortcut(QKeySequence("F3"), self).activated.connect(self.send_to_tab3)
        QShortcut(QKeySequence("Del"), self).activated.connect(self.delete_selected)
        # Shift+R 핫키를 포커스에 따라 다르게 작동하도록 연결
        QShortcut(QKeySequence("Shift+R"), self).activated.connect(self.hotkey_shift_r)
        QShortcut(QKeySequence("Ctrl+Z"), self).activated.connect(self.action_undo_rename)

        QShortcut(QKeySequence("Ctrl+G"), self).activated.connect(self.show_goto_dialog)

    def _update_button_active_style(self, button, is_active):
        if is_active:
            button.setStyleSheet("""
                QToolButton { background-color: #2980B9; color: white; padding: 5px; font-weight: bold; border-radius: 4px; }
                QToolButton::menu-indicator { image: none; }
            """)
        else:
            button.setStyleSheet("""
                QToolButton { background-color: transparent; color: white; padding: 5px; font-weight: bold; border: none; }
                QToolButton:hover { color: #3498DB; }
                QToolButton::menu-indicator { image: none; }
            """)

    def _on_filter_toggled(self, checked):
        self._update_button_active_style(self.btn_filter, checked)
        self.apply_grouping_and_sorting()

    def hotkey_shift_r(self):
        # 탐색기 패널에 포커스가 있으면 폴더 이름 변경, 리스트에 있으면 다중 파일 이름 변경
        if self.tree_view.hasFocus():
            self.rename_folder()
        else:
            self.action_multi_rename()

    def hotkey_f3(self): # F2였던 메서드명을 논리에 맞게 변경
        if self.tree_view.hasFocus():
            self.rename_folder()
        else:
            self.send_to_tab3()

    def rename_folder(self, index=None):
        if not index:
            index = self.tree_view.currentIndex()
        if not index.isValid(): return
        
        old_path = self.dir_model.filePath(index)
        old_name = os.path.basename(old_path)
        
        new_name, ok = QInputDialog.getText(self, _("dlg_ren_folder_title"), _("dlg_ren_folder_msg"), text=old_name)
        if ok and new_name and new_name != old_name:
            new_path = os.path.join(os.path.dirname(old_path), new_name)
            try:
                os.rename(old_path, new_path)
                favs = self.config.get("folder_favorites", [])
                for fav in favs:
                    if fav["path"] == old_path:
                        fav["path"] = new_path
                        fav["name"] = new_name
                self.config["folder_favorites"] = favs
                save_config(self.config)
                self.populate_quick_access()
                
                if self.current_watched_folder == old_path:
                    self.folder_watcher.removePath(old_path)
                    self.folder_watcher.addPath(new_path)
                    self.current_watched_folder = new_path
            except Exception as e:
                QMessageBox.critical(self, _("dlg_err"), _("dlg_err_ren_folder").format(e))

    def delete_selected(self):
        from PyQt6.QtCore import QFile, QTimer

        if self.table_view.hasFocus() or self.list_view.hasFocus():
            files = self.get_selected_files()
            if not files: return
            
            reply = QMessageBox.question(self, _("dlg_del_file_title"), _("dlg_del_file_msg").format(len(files)), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                # [핵심] 삭제 작업 중 발생하는 OS 폴더 변경 이벤트를 무시하여 자동 재스캔을 방지
                self._internal_action_lock = True  
                
                successfully_deleted = set()
                for f in files:
                    try: 
                        # os.remove(f) 완전 삭제 대신 휴지통으로 이동
                        if QFile.moveToTrash(f) or not os.path.exists(f):
                            successfully_deleted.add(f)
                    except Exception as e: print(f"Delete error: {e}")
                
                if successfully_deleted:
                    # 1. 메모리 캐시에서 삭제된 파일 즉각 제거
                    self.file_data_cache = [row for row in self.file_data_cache if row.get("full_path") not in successfully_deleted]
                    
                    # 2. 파일 매핑 및 중복 해시 캐시에서도 제거 (재스캔/매칭 대기 시간 완전 제거)
                    for f in successfully_deleted:
                        if f in self.file_data_map:
                            del self.file_data_map[f]
                        if hasattr(self, 'dup_matches') and f in self.dup_matches:
                            del self.dup_matches[f]

                    # 3. 전체 로드 없이 그룹 및 정렬만 다시 적용하여 0.1초만에 UI 갱신
                    self.apply_grouping_and_sorting()
                    
                    # 4. 폴더 감지 기준 시간 갱신 (재스캔 트리거 방어)
                    try: self.last_folder_mtime = os.stat(self.current_watched_folder).st_mtime
                    except: pass
                
                # OS 파일 이벤트 처리가 끝날 즈음(1.5초 후) 감지기 락 해제
                QTimer.singleShot(1500, lambda: setattr(self, '_internal_action_lock', False))
                
        elif self.tree_view.hasFocus():
            index = self.tree_view.currentIndex()
            if not index.isValid(): return
            path = self.dir_model.filePath(index)
            
            reply = QMessageBox.question(self, _("dlg_del_folder_title"), _("dlg_del_folder_msg").format(os.path.basename(path)), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                try:
                    shutil.rmtree(path)
                    self.remove_from_favorites(path)
                except Exception as e:
                    QMessageBox.critical(self, _("dlg_err"), _("dlg_del_err").format(e))

    def load_initial_layout(self):
        view_mode = self.config.get("folder_view_mode", "detail")
        self.set_view_mode(view_mode)
        
        active_cols = self.config.get("folder_active_columns", ["cover", "name", "size", "mtime", "series", "title", "writer"])
        self.table_model.set_columns(active_cols)
        
        header_state_hex = self.config.get("folder_header_state", "")
        if header_state_hex:
            self.table_view.horizontalHeader().restoreState(QByteArray.fromHex(header_state_hex.encode()))
            
        if self.current_sort_key in self.table_model.active_columns:
            idx = self.table_model.active_columns.index(self.current_sort_key)
            self.table_view.horizontalHeader().setSortIndicator(idx, self.current_sort_order)
            
        main_spl = self.config.get("folder_main_splitter", "")

        if main_spl:
            self.main_splitter.restoreState(QByteArray.fromHex(main_spl.encode()))
            
        right_spl = self.config.get("folder_right_splitter", "")
        if right_spl:
            self.right_splitter.restoreState(QByteArray.fromHex(right_spl.encode()))
            
        last_path = self.config.get("folder_last_path", "")
        if last_path and os.path.exists(last_path):
            self.pending_scroll_path = last_path
            # 프로그램 시작 직후 능동형 큐 스크롤 가동
            QTimer.singleShot(200, lambda: self._start_queued_scroll(last_path))

    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, 'main_optimize_btn') and self.main_optimize_btn:
            self.main_optimize_btn.hide()
            
        path = getattr(self, 'pending_scroll_path', None) or getattr(self, 'current_watched_folder', None)
        if path:
            self.pending_scroll_path = None
            QTimer.singleShot(100, lambda: self._start_queued_scroll(path))

    def _start_queued_scroll(self, path):
        if not path or not os.path.exists(path): return
        
        qt_path = QDir.fromNativeSeparators(os.path.abspath(path))
        
        # 1. 루트(드라이브)부터 최종 목적지까지의 경로를 순서대로 큐에 담음
        self._pending_expand_queue = []
        curr = qt_path
        while curr:
            self._pending_expand_queue.insert(0, curr)
            parent = QDir.fromNativeSeparators(os.path.dirname(curr))
            if parent == curr or not parent: break
            curr = parent
            
        # 2. 능동형 감시 타이머 시작 (Qt의 불확실한 시그널 누락 완벽 회피)
        if hasattr(self, '_queue_timer') and self._queue_timer.isActive():
            self._queue_timer.stop()
            
        self._queue_timer = QTimer(self)
        self._queue_timer.timeout.connect(self._process_next_queue_step)
        self._queue_timer.start(50) # 0.05초 단위의 아주 빠른 속도로 상태 검사
        self._queue_retries = 100 # 각 폴더 스텝당 최대 5초 대기 (HDD 스핀업 고려)

    def _process_next_queue_step(self):
        if not hasattr(self, '_pending_expand_queue') or not self._pending_expand_queue:
            self._queue_timer.stop()
            return
            
        self._queue_retries -= 1
        if self._queue_retries <= 0:
            self._queue_timer.stop()
            return

        current_target = self._pending_expand_queue[0]
        idx = self.dir_model.index(current_target)

        if idx.isValid():
            # 3. 목표 폴더가 유효(로딩 완료)해졌다면 큐에서 제거하고 전개
            self._pending_expand_queue.pop(0)
            self.tree_view.expand(idx)
            self._queue_retries = 100 # 다음 요소를 위해 타임아웃 초기화
            
            if not self._pending_expand_queue:
                # 4. 목적지 최종 도달 완료
                self._queue_timer.stop()
                self.tree_view.setCurrentIndex(idx)
                self.tree_view.setFocus()
                QTimer.singleShot(50, lambda: self._do_final_scroll(idx))
        else:
            # 5. 아직 로딩 전이라면? 부모 폴더를 적극적으로 찔러서 로딩(fetchMore) 강제 유도!
            parent_path = QDir.fromNativeSeparators(os.path.dirname(current_target))
            # 드라이브 최상위(C:/ 등)인 경우 안전하게 빈 문자열(Root)을 부모로 취급
            if parent_path == current_target or not parent_path:
                parent_idx = self.dir_model.index(self.dir_model.rootPath())
            else:
                parent_idx = self.dir_model.index(parent_path)
                if not parent_idx.isValid():
                    parent_idx = self.dir_model.index(self.dir_model.rootPath())
            
            # Qt 내부 백그라운드 스레드에게 지금 당장 이 경로를 하드에서 읽어오라고 직접 명령
            if parent_idx.isValid():
                self.tree_view.expand(parent_idx)
                if self.dir_model.canFetchMore(parent_idx):
                    self.dir_model.fetchMore(parent_idx)

    def _do_final_scroll(self, idx):
        # 뷰포트 바깥에 숨겨진 영역을 먼저 렌더링 범위로 끌어온 뒤 중앙 정렬
        self.tree_view.scrollTo(idx, QAbstractItemView.ScrollHint.EnsureVisible)
        self.tree_view.scrollTo(idx, QAbstractItemView.ScrollHint.PositionAtCenter)
        self.tree_view.horizontalScrollBar().setValue(0)

    def _process_next_queue_step(self):
        if not self._pending_expand_queue:
            return # 큐가 비었으면 작업 종료
            
        current_target = self._pending_expand_queue[0]
        idx = self.dir_model.index(current_target)
        
        if idx.isValid():
            # 3. 현재 뎁스의 폴더가 로딩되어 있다면: 큐에서 빼고 폴더를 엽니다.
            self._pending_expand_queue.pop(0)
            self.tree_view.expand(idx)
            
            if not self._pending_expand_queue:
                # 4. 큐가 완전히 비워졌다 = 최종 목적지에 도달했다!
                self.tree_view.setCurrentIndex(idx)
                self.tree_view.setFocus()
                
                # 렌더링에 필요한 최소한의 시간(50ms)만 준 뒤 최종 스크롤 확정
                QTimer.singleShot(50, lambda: self._do_final_scroll(idx))
            else:
                # 다음 하위 폴더 처리를 위해 곧바로 재귀 호출 (이벤트 루프가 막히지 않게 타이머 사용)
                QTimer.singleShot(10, self._process_next_queue_step)
        else:
            # 아직 로딩되지 않았다면? 
            # 여기서 while문으로 기다리는 것이 아니라 그냥 함수를 '종료'해 버립니다!
            # (백그라운드에서 로딩이 끝나면 아래의 _on_directory_loaded_step 가 알아서 깨워줍니다)
            pass

    def _on_directory_loaded_step(self, loaded_path):
        # QFileSystemModel이 "폴더 하나 읽기 끝났어!" 라고 신호를 보낼 때마다
        # 큐에 남은 작업이 있다면 다음 스텝을 밟아보라고 툭 쳐줍니다.
        if hasattr(self, '_pending_expand_queue') and self._pending_expand_queue:
            self._process_next_queue_step()

    def _do_final_scroll(self, idx):
        # 가려져 있던 UI가 펴지면서 발생하는 미세한 픽셀 오차를 방지하기 위해 EnsureVisible 후 Center
        self.tree_view.scrollTo(idx, QAbstractItemView.ScrollHint.EnsureVisible)
        self.tree_view.scrollTo(idx, QAbstractItemView.ScrollHint.PositionAtCenter)
        self.tree_view.horizontalScrollBar().setValue(0)

    def _start_path_scroll(self, path):
        if not path or not os.path.exists(path): return
        
        self._target_scroll_path = QDir.fromNativeSeparators(os.path.abspath(path))
        self._scroll_retries = 100  # 외부 HDD 절전모드 해제 및 스핀업 고려 (최대 10초 대기)
        
        if hasattr(self, '_scroll_timer') and self._scroll_timer.isActive():
            self._scroll_timer.stop()
            
        self._scroll_timer = QTimer(self)
        self._scroll_timer.timeout.connect(self._process_path_scroll)
        self._scroll_timer.start(100) # 0.1초마다 백그라운드에서 로딩 완료 여부 조용히 감시

    def _process_path_scroll(self):
        target = getattr(self, '_target_scroll_path', None)
        if not target:
            self._scroll_timer.stop()
            return
            
        idx = self.dir_model.index(target)
        
        # 1. 인덱스가 아직 로딩되지 않았을 때 (기다림 단계)
        if not idx.isValid():
            self._scroll_retries -= 1
            if self._scroll_retries <= 0:
                self._scroll_timer.stop()
                return
                
            # 역추적하며 유효한 상위 폴더를 찾아 강제로 펼치며 하위 로딩 유도
            curr = target
            while curr:
                p_idx = self.dir_model.index(curr)
                if p_idx.isValid():
                    self.tree_view.expand(p_idx)
                    if self.dir_model.canFetchMore(p_idx):
                        self.dir_model.fetchMore(p_idx)
                    break
                
                parent = QDir.fromNativeSeparators(os.path.dirname(curr))
                if parent == curr or not parent: break
                curr = parent
            return # 아직 로딩 중이므로 다음 감시 틱(100ms 후)으로 넘김

        # 2. 인덱스 로딩이 100% 완료된 시점 (사용자 요구사항 완벽 충족)
        self._scroll_timer.stop()
        self._target_scroll_path = None
        
        # 최상위 부모부터 순서대로 폴더 열기
        parents = []
        p = idx.parent()
        while p.isValid():
            parents.insert(0, p)
            p = p.parent()
            
        for p in parents:
            self.tree_view.expand(p)
            
        # 목표 폴더 열기, 선택 및 확실한 활성화(포커스 지정)
        self.tree_view.expand(idx)
        self.tree_view.setCurrentIndex(idx)
        self.tree_view.setFocus()
        
        # 레이아웃이 화면에 그려질 틈을 아주 약간 주고 단 한 번만 깔끔하게 스크롤 이동
        def final_scroll():
            self.tree_view.scrollTo(idx, QAbstractItemView.ScrollHint.PositionAtCenter)
            self.tree_view.horizontalScrollBar().setValue(0)
            
        QTimer.singleShot(100, final_scroll)

    def _on_dir_loaded_for_scroll(self, path):
        # 폴더가 하나 로딩 완료될 때마다 목표에 도달했는지 확인
        if getattr(self, '_target_scroll_path', None):
            self._check_and_scroll()

    def _check_and_scroll(self):
        target = getattr(self, '_target_scroll_path', None)
        if not target: return
        
        idx = self.dir_model.index(target)
        
        # 1. 목표 경로가 아직 로딩되지 않았을 때 (기다림 단계)
        if not idx.isValid():
            curr = target
            while curr:
                p_idx = self.dir_model.index(curr)
                if p_idx.isValid():
                    # 유효한 부모를 열어 로딩을 유도. 로딩이 끝나면 _on_dir_loaded_for_scroll이 자동으로 다시 불립니다.
                    self.tree_view.expand(p_idx)
                    if self.dir_model.canFetchMore(p_idx):
                        self.dir_model.fetchMore(p_idx)
                    break
                parent = QDir.fromNativeSeparators(os.path.dirname(curr))
                if parent == curr or not parent:
                    root_idx = self.dir_model.index(self.dir_model.rootPath())
                    self.tree_view.expand(root_idx)
                    break
                curr = parent
            return # 로딩 신호가 올 때까지 함수 종료 및 대기

        # 2. 모든 로딩이 끝난 시점 (사용자 요청 사항 완벽 적용)
        self._target_scroll_path = None # 추적 종료
        
        parents = []
        p = idx.parent()
        while p.isValid():
            parents.insert(0, p)
            p = p.parent()
            
        for p in parents:
            self.tree_view.expand(p)
            
        self.tree_view.expand(idx)
        self.tree_view.setCurrentIndex(idx)
        self.tree_view.setFocus()
        
        # 로딩이 100% 보장된 상태이므로 단 한 번의 깔끔한 스크롤만 수행
        def final_scroll():
            self.tree_view.scrollTo(idx, QAbstractItemView.ScrollHint.PositionAtCenter)
            self.tree_view.horizontalScrollBar().setValue(0)
            
        QTimer.singleShot(100, final_scroll)

    def save_current_layout_state(self):
        state = self.table_view.horizontalHeader().saveState().toHex().data().decode()

    def save_current_layout_state(self):
        state = self.table_view.horizontalHeader().saveState().toHex().data().decode()
        self.config["folder_header_state"] = state
        self.config["folder_active_columns"] = self.table_model.active_columns
        save_config(self.config)

    def update_layouts_menu(self):
        self.menu_layouts.clear()
        self.menu_layouts.addAction(_("menu_edit_layout"), self.open_layout_editor)
        self.menu_layouts.addAction(_("menu_save_layout"), self.save_named_layout)
        self.menu_layouts.addAction(_("menu_del_layout"), self.delete_named_layout)
        self.menu_layouts.addSeparator()
        
        saved_layouts = self.config.get("saved_list_layouts", {})
        for name in saved_layouts.keys():
            action = self.menu_layouts.addAction(name)
            action.triggered.connect(lambda checked, n=name: self.apply_named_layout(n))

    def open_layout_editor(self):
        dlg = ColumnSelectDialog(self, self.table_model.active_columns, self.table_model.ALL_COLUMNS)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_cols = dlg.get_selected()
            if new_cols:
                self.table_model.set_columns(new_cols)
                self.save_current_layout_state()
                self.apply_grouping_and_sorting()

    def save_named_layout(self):
        name, ok = QInputDialog.getText(self, _("menu_save_layout"), _("dlg_save_lay_msg"))
        if ok and name:
            state = self.table_view.horizontalHeader().saveState().toHex().data().decode()
            saved_layouts = self.config.get("saved_list_layouts", {})
            saved_layouts[name] = {"columns": self.table_model.active_columns, "state": state}
            self.config["saved_list_layouts"] = saved_layouts
            save_config(self.config)
            self.update_layouts_menu()

    def delete_named_layout(self):
        saved_layouts = self.config.get("saved_list_layouts", {})
        if not saved_layouts: return
        name, ok = QInputDialog.getItem(self, _("menu_del_layout"), _("dlg_del_lay_msg"), list(saved_layouts.keys()), 0, False)
        if ok and name:
            del saved_layouts[name]
            self.config["saved_list_layouts"] = saved_layouts
            save_config(self.config)
            self.update_layouts_menu()

    def apply_named_layout(self, name):
        layout = self.config.get("saved_list_layouts", {}).get(name)
        if layout:
            self.table_model.set_columns(layout["columns"])
            self.table_view.horizontalHeader().restoreState(QByteArray.fromHex(layout["state"].encode()))
            self.save_current_layout_state()
            self.apply_grouping_and_sorting()

    def set_view_mode(self, mode):
        self.config["folder_view_mode"] = mode
        save_config(self.config)
        self._update_button_active_style(self.btn_views, mode != "detail")
        
        if mode == "detail":
            self.view_stack.setCurrentIndex(0)
            self.item_delegate.view_mode = "detail"
            
            # 자세히 보기 모드일 때의 높이(행 크기) 복원 (기본값 120)
            saved_size = self.config.get("folder_item_size_detail", 120)
            self.slider_item_size.blockSignals(True)
            self.slider_item_size.setValue(saved_size)
            self.slider_item_size.blockSignals(False)
            
            # 테이블(Detail) 뷰에 맞게 row 높이 및 아이콘 크기 적용
            table_row_height = max(36, int(saved_size * 0.6))
            self.table_view.verticalHeader().setDefaultSectionSize(table_row_height)
            icon_h = table_row_height - 4
            icon_w = int(icon_h * 0.75)
            self.table_view.setIconSize(QSize(icon_w, icon_h))
            
        else:
            self.view_stack.setCurrentIndex(1)
            self.item_delegate.view_mode = mode
            
            # 모드별 저장된 썸네일/타일 크기 복원 (기본값: 썸네일 240, 타일 300)
            default_size = 240 if mode == "thumbnail" else 300
            saved_size = self.config.get(f"folder_item_size_{mode}", default_size)
            
            self.slider_item_size.blockSignals(True)
            self.slider_item_size.setValue(saved_size)
            self.item_delegate.item_size = saved_size
            self.slider_item_size.blockSignals(False)
            
            self.list_view.setGridSize(QSize()) 
            self.list_view.doItemsLayout()
            
        self.table_model.layoutChanged.emit()
        self.apply_grouping_and_sorting()

    def on_size_changed(self, value):
        mode = self.item_delegate.view_mode
        
        if mode in ["thumbnail", "tile"]:
            self.item_delegate.item_size = value
            self.config[f"folder_item_size_{mode}"] = value
            self.table_model.layoutChanged.emit()
            self.list_view.doItemsLayout()
        else:
            # detail 뷰 모드일 때는 행 높이로 사용
            self.config["folder_item_size_detail"] = value
            table_row_height = max(36, int(value * 0.6))
            self.table_view.verticalHeader().setDefaultSectionSize(table_row_height)
            icon_h = table_row_height - 4
            icon_w = int(icon_h * 0.75)
            self.table_view.setIconSize(QSize(icon_w, icon_h))
            
        save_config(self.config)

    def toggle_sidebar(self, checked):
        self.left_panel.setVisible(checked)

    def set_grouping(self, key):
        self.current_group_key = key
        self._update_button_active_style(self.btn_grouped, key != "none")
        self.apply_grouping_and_sorting()

    def _save_sort_state(self):
        self.config["folder_sort_key"] = self.current_sort_key
        self.config["folder_sort_order"] = 0 if self.current_sort_order == Qt.SortOrder.AscendingOrder else 1
        save_config(self.config)

    def set_sorting(self, key):
        if self.current_sort_key == key:
            self.toggle_sort_order()
            return
            
        self.current_sort_key = key
        self.current_sort_order = Qt.SortOrder.AscendingOrder
        
        if key in self.table_model.active_columns:
            idx = self.table_model.active_columns.index(key)
            self.table_view.horizontalHeader().setSortIndicator(idx, self.current_sort_order)
        else:
            self.table_view.horizontalHeader().clearIndicator()
            
        self._save_sort_state()
        self.apply_grouping_and_sorting()

    def on_header_clicked(self, logicalIndex):
        key = self.table_model.active_columns[logicalIndex]
        if self.current_sort_key == key:
            self.current_sort_order = Qt.SortOrder.DescendingOrder if self.current_sort_order == Qt.SortOrder.AscendingOrder else Qt.SortOrder.AscendingOrder
        else:
            self.current_sort_key = key
            self.current_sort_order = Qt.SortOrder.AscendingOrder
        
        self.table_view.horizontalHeader().setSortIndicator(logicalIndex, self.current_sort_order)
        self._save_sort_state()
        self.apply_grouping_and_sorting()

    def toggle_sort_order(self):
        self.current_sort_order = Qt.SortOrder.DescendingOrder if self.current_sort_order == Qt.SortOrder.AscendingOrder else Qt.SortOrder.AscendingOrder
        if self.current_sort_key in self.table_model.active_columns:
            idx = self.table_model.active_columns.index(self.current_sort_key)
            self.table_view.horizontalHeader().setSortIndicator(idx, self.current_sort_order)
        self._save_sort_state()
        self.apply_grouping_and_sorting()

    def apply_grouping_and_sorting(self):
        # [추가] 새로운 폴더 스캔이 진행 중일 때는 과거 스레드(중복 검사 등)의 간섭으로 인한 '데이터 없음' 표시를 원천 차단
        if hasattr(self, 'scan_thread') and self.scan_thread and self.scan_thread.isRunning():
            return
            
        import time
        from collections import Counter
        t0 = time.time()
        print(f"\n[LOG] 1. apply_grouping_and_sorting 시작")
        
        # [최적화] 극심한 프리징을 유발하는 원인 1: clearSpans 제거 (update_data 호출 시 자동 초기화됨)
        # self.table_view.clearSpans() 
        
        search_query = self.search_bar.text().strip().lower()
        filter_no_meta = hasattr(self, 'action_filter_no_meta') and self.action_filter_no_meta.isChecked()
        
        # --- [추가] 빈 상태 메시지 동적 결정 ---
        empty_text = _("t3_no_data")
        if search_query:
            empty_text = _("t3_msg_no_search_result")
        elif filter_no_meta:
            empty_text = "조건에 맞는 파일이 없습니다.\n\n(상단의 '필터 ▼' 메뉴에서 '메타데이터가 없는 파일만 보기'가 켜져 있습니다)"
        elif getattr(self, 'current_watched_folder', None) and os.path.exists(self.current_watched_folder):
            if not self.btn_subfolders.isChecked():
                try:
                    for entry in os.scandir(self.current_watched_folder):
                        if entry.is_dir():
                            empty_text = "현재 폴더에 압축 파일이 없습니다.\n\n(하위 폴더의 파일을 보려면 상단의 '☑ 하위 폴더 포함'을 켜주세요)"
                            break
                except Exception:
                    pass
        # --------------------------------------

        data = []
        for row in self.file_data_cache:
            if filter_no_meta:
                has_meta = False
                fm = row.get("full_meta", {})
                for k in ["title", "series", "writer", "publisher", "volume_count", "summary", "tags"]:
                    if fm.get(k):
                        has_meta = True
                        break
                if has_meta: continue

            if search_query:
                search_target = f"{row.get('name','')} {row.get('title','')} {row.get('series','')} {row.get('writer','')}".lower()
                if search_query not in search_target: continue
            data.append(row)

        print(f"[LOG] 2. 검색 필터링 완료: {time.time()-t0:.3f}s")

        if not data:
            self.table_model.update_data([])
            self.view_stack.hide()
            self.lbl_empty_state.setText(empty_text)
            self.lbl_empty_state.show()
            return

        col_id = self.current_sort_key
        reverse = (self.current_sort_order == Qt.SortOrder.DescendingOrder)
        
        def safe_get(row, key):
            if key == "size": return row.get("raw_size", 0)
            if key == "mtime": return row.get("raw_mtime", 0)
            if key == "ctime": return row.get("raw_ctime", 0)
            
            if key in row and row[key] != "":
                val = row[key]
            else:
                val = row.get("full_meta", {}).get(key, "")
            
            if isinstance(val, str): return val.lower()
            return val if val is not None else ""

        print(f"[LOG] 3. 정렬 중...")
        if self.current_group_key != "none":
            data.sort(key=lambda x: safe_get(x, col_id), reverse=reverse)
            data.sort(key=lambda x: safe_get(x, self.current_group_key), reverse=False) 
        else:
            data.sort(key=lambda x: safe_get(x, col_id), reverse=reverse)
            
        print(f"[LOG] 4. 정렬 완료: {time.time()-t0:.3f}s")
            
        display_data = []
        
        if self.current_group_key != "none":
            from collections import defaultdict
            import re
            
            group_counts = Counter((safe_get(r, self.current_group_key) or _("folder_unknown")) for r in data)
            
            # 그룹별로 속한 파일 데이터 모으기
            group_rows = defaultdict(list)
            for r in data:
                g_val = safe_get(r, self.current_group_key) or _("folder_unknown")
                group_rows[g_val].append(r)
                
            # 파일명에서 실제 권/화 번호만 영리하게 추출하는 함수
            def extract_vol_numbers(name, series_name=""):
                name = re.sub(r'(?i)\b(1080p|720p|480p|1440p|4k|2k|x264|x265)\b', '', name)
                name = re.sub(r'\[19\d{2}\]|\[20\d{2}\]|\(19\d{2}\)|\(20\d{2}\)', '', name)
                
                # 1. 001화~009화 같은 패턴 (단위가 양쪽에 다 있는 경우)
                range_match = re.search(r'(\d+(?:\.\d+)?)\s*(권|화|장|편|부)\s*[~-]\s*(\d+(?:\.\d+)?)\s*(권|화|장|편|부)', name, re.IGNORECASE)
                if range_match:
                    try:
                        start = int(float(range_match.group(1)))
                        end = int(float(range_match.group(3)))
                        if start <= end and end - start < 150:
                            return list(range(start, end + 1))
                    except ValueError:
                        pass

                # 2. 일반적인 패턴 (단위가 뒤에 있는 경우: 13권, 13~14권)
                vol_match = re.search(r'(?:제|v|vol\.?\s*)?(\d+(?:\.\d+)?(?:\s*[~-]\s*\d+(?:\.\d+)?)?)\s*(권|화|장|편|부)', name, re.IGNORECASE)
                if vol_match:
                    num_str = vol_match.group(1)
                else:
                    # 단위가 앞에 있는 경우: vol 13, 제 13, ch 13
                    pre_match = re.search(r'(?i)(?:vol|v|권|화|제|chapter|ch|#)\s*\.?\s*(\d+(?:\.\d+)?(?:\s*[~-]\s*\d+(?:\.\d+)?)?)', name)
                    if pre_match:
                        num_str = pre_match.group(1)
                    else:
                        # 3. 단위가 없는 경우 마지막 숫자 그룹 추출
                        clean_for_nums = re.sub(r'\[.*?\]|\(.*?\)', '', name)
                        if series_name:
                            safe_series = r'\s*'.join(re.escape(word) for word in series_name.split())
                            clean_for_nums = re.sub(f'(?i){safe_series}', '', clean_for_nums)
                        matches = re.findall(r'\d+(?:\.\d+)?(?:\s*[~-]\s*\d+(?:\.\d+)?)?', clean_for_nums)
                        if matches:
                            num_str = matches[-1]
                        else:
                            return []

                # 추출된 숫자 문자열 파싱
                if '~' in num_str or '-' in num_str:
                    parts = re.split(r'\s*[~-]\s*', num_str)
                    if len(parts) >= 2:
                        try:
                            start = int(float(parts[0]))
                            end = int(float(parts[1]))
                            if start <= end and end - start < 150:
                                return list(range(start, end + 1))
                            else:
                                return [start]
                        except ValueError:
                            pass
                
                try:
                    return [int(float(num_str))]
                except ValueError:
                    return []

            current_group = object()
            for loop_idx, row in enumerate(data):
                if loop_idx % 50 == 0:
                    QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
                
                g_val = safe_get(row, self.current_group_key) or _("folder_unknown")
                
                if g_val != current_group:
                    count = group_counts[g_val]
                    
                    # 그룹 내 파일들의 번호를 수집하여 누락 확인
                    vols = set()
                    from core.parser import extract_core_title
                    for gr_idx, gr in enumerate(group_rows[g_val]):
                        if gr_idx % 20 == 0:
                            QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
                        if gr.get("is_folder"): continue
                        s_name = safe_get(gr, "series") or gr.get("full_meta", {}).get("series", "")
                        if not s_name:
                            s_name = extract_core_title(os.path.splitext(gr.get("name", ""))[0]).strip()
                        v_nums = extract_vol_numbers(gr.get("name", ""), s_name)
                        for v in v_nums:
                            vols.add(v)
                    
                    missing = []
                    if vols:
                        min_v, max_v = min(vols), max(vols)
                        # 오탐지를 막기 위해 첫권과 끝권의 차이가 150권 이하일 때만 검사
                        if max_v - min_v < 150: 
                            missing = [str(i) for i in range(min_v, max_v) if i not in vols]

                    display_data.append({"is_group": True, "name": g_val, "count": count, "missing": missing})
                    current_group = g_val
                display_data.append(row)
        else:
            display_data = data
            
        print(f"[LOG] 5. 그룹화 배열 생성 완료: {time.time()-t0:.3f}s")

        final_data = []
        is_detail_view = (self.view_stack.currentIndex() == 0)
        show_dup = is_detail_view and self.btn_dup_check.isChecked()

        for loop_idx, row in enumerate(display_data):
            if loop_idx % 50 == 0:
                QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
            final_data.append(row)
            if not row.get("is_group") and show_dup:
                fp = row.get("full_path")
                if hasattr(self, 'dup_matches') and fp in self.dup_matches:
                    sorted_b_folders = sorted(self.dup_matches[fp].items(), key=lambda x: max([m["ratio"] for m in x[1]]), reverse=True)
                    for b_folder, matched_files in sorted_b_folders:
                        matched_files.sort(key=lambda x: x["ratio"], reverse=True)
                        max_ratio = matched_files[0]["ratio"]
                        
                        final_data.append({
                            "is_dup_folder": True,
                            "path": b_folder,
                            "max_ratio": max_ratio
                        })
                        for m in matched_files:
                            final_data.append({
                                "is_dup_child": True,
                                "name": m["b_file"]["name"],
                                "size_str": self.format_size(m["b_file"]["size"]),
                                "ratio": m["ratio"],
                                "full_path": m["b_file"]["full_path"]
                            })

        print(f"[LOG] 6. 중복 파일 인젝션 완료: {time.time()-t0:.3f}s")

        self.file_data_map = {}
        idx_counter = 0
        for loop_idx, row in enumerate(final_data):
            if loop_idx % 100 == 0:
                QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
            row["display_index"] = idx_counter
            if not row.get("is_group") and not row.get("is_dup_folder") and not row.get("is_dup_child"):
                self.file_data_map[row.get("full_path")] = row
            idx_counter += 1
            
        print(f"[LOG] 7. Map 재생성 완료: {time.time()-t0:.3f}s")
        
        self.table_view.setUpdatesEnabled(False)

        self.table_view.clearSpans()

        t_model = time.time()
        self.table_model.update_data(final_data)
        
        if not final_data:
            self.view_stack.hide()
            self.lbl_empty_state.setText(empty_text)
            self.lbl_empty_state.show()
        else:
            self.view_stack.show()
            self.lbl_empty_state.hide()
            
        print(f"[LOG] 8. TableModel 내부 업데이트 (Qt 엔진 렌더링 계산): {time.time()-t_model:.3f}s")

        col_count = self.table_model.columnCount()

        span_targets = []
        for i, row in enumerate(final_data):
            if i % 200 == 0:
                QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
            if row.get("is_group") or row.get("is_dup_folder") or row.get("is_dup_child"):
                span_targets.append(i)

        print(f"[LOG] 9. 병합(Span) 타겟 추출 완료 ({len(span_targets)}건): {time.time()-t0:.3f}s")

        from PyQt6.QtCore import QTimer

        self._span_task_id = getattr(self, '_span_task_id', 0) + 1
        current_task_id = self._span_task_id

        def apply_spans_chunk(targets, chunk_size=200):
            if getattr(self, '_span_task_id', 0) != current_task_id:
                return

            if not hasattr(self, '_span_start_time'):
                self._span_start_time = time.time()

            if not targets:
                self.table_view.setUpdatesEnabled(True)
                # [추가] span 적용 완료 후 리스트 패널 활성화
                self.dim_overlay.hide()
                print(f"[LOG] 10. 모든 Span 비동기 적용 및 UI 렌더링 재개 완료: {time.time()-self._span_start_time:.3f}s")
                del self._span_start_time
                return
                
            chunk = targets[:chunk_size]
            next_targets = targets[chunk_size:]
            
            for i in chunk:
                self.table_view.setSpan(i, 0, 1, col_count)
                self.table_view.setRowHeight(i, 35)
                
            QTimer.singleShot(1, lambda: apply_spans_chunk(next_targets, chunk_size))

        apply_spans_chunk(span_targets)

    def format_size(self, size):
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0: return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"

    def on_scan_progress(self, count):
        self.lbl_tree_status.setText(_("folder_scanning").format(count))
        if self.scan_overlay and self.scan_overlay.isVisible():
            self.scan_overlay.text = _("folder_scanning").format(count)

    def _show_missing_toast_delayed(self):
        self._waiting_for_dialog = False
        
        if getattr(self, '_cached_missing_data', None) is None:
            if not hasattr(self, 'toast_check_thread') or not self.toast_check_thread.isRunning():
                dup_folders = self.config.get("dup_check_folders", [])
                self.toast_check_thread = MissingCheckThread(dup_folders, getattr(self, 'file_data_cache', []), is_toast=True)
                self.toast_check_thread.finished_signal.connect(self._on_missing_data_ready)
                self.toast_check_thread.start()
        else:
            current_series = set()
            from core.parser import extract_core_title
            for row in getattr(self, 'file_data_cache', []):
                if row.get("is_folder") or row.get("is_dup_folder") or row.get("is_dup_child"): continue
                s_name = row.get("series") or row.get("full_meta", {}).get("series", "")
                if not s_name:
                    s_name = extract_core_title(os.path.splitext(row.get("name", ""))[0]).strip()
                if not s_name:
                    s_name = os.path.basename(os.path.dirname(row.get("full_path", "")))
                if s_name:
                    current_series.add(s_name)
                    
            local_missing = [item for item in self._cached_missing_data if item['series'] in current_series]
            
            if local_missing:
                try:
                    from ui.widgets import Toast
                    Toast.show(self.main_window, _("tf_local_missing_alert").format(len(local_missing)))
                except Exception: pass
            
    def on_scan_finished(self, folder_path, file_data_cache, total_size):
        # [추가] 빠른 폴더 이동 시 발생하는 캐시 덮어쓰기(데이터 증발) 버그 방어
        if folder_path != getattr(self, 'current_watched_folder', None):
            return

        self.scan_overlay.hide()

        self.is_syncing = False
        self.sync_total_tasks = 0
        self.sync_completed_tasks = 0
        
        # 오프라인 방어 체크
        if not os.path.exists(self.current_watched_folder):
            if hasattr(self, 'main_status_label') and self.main_status_label:
                self.main_status_label.setText(_("folder_ready"))
            self.lbl_tree_status.setText("Network Drive Offline / 경로를 찾을 수 없습니다.")
            self.lbl_empty_state.setText("경로를 찾을 수 없습니다.")
            return

        self.file_data_cache = file_data_cache
        for row in self.file_data_cache:
            row["size"] = self.format_size(row["raw_size"])

        # --- [추가] 스캔 결과를 메모리 캐시에 저장 (비어있을 땐 캐시 제외하여 HDD 스핀업 지연 방어) ---
        folder_path = self.current_watched_folder
        if folder_path and file_data_cache:
            include_sub = self.btn_subfolders.isChecked()
            cache_key = (folder_path, include_sub)
            try:
                mtime = os.stat(folder_path).st_mtime
            except:
                mtime = 0
            self.folder_scan_cache[cache_key] = (file_data_cache, total_size, mtime)

        self.apply_grouping_and_sorting()

        QTimer.singleShot(1000, self._show_missing_toast_delayed)

        folder_path = self.current_watched_folder
        if folder_path:
            self.lbl_tree_status.setText(_("folder_status_sel").format(os.path.basename(folder_path), len(self.file_data_cache), self.format_size(total_size)))
            
        self.scroll_timer.start(100)
        self.start_dup_match()
        
        # [수정] 폴더 스캔 및 UI 렌더링이 완료된 후 첫 번째 항목 자동 선택
        if self.table_model.rowCount() > 0:
            active_view = self.get_active_view()
            first_idx = self.table_model.index(0, 0)
            
            # SelectionModel을 통해 첫 번째 행 선택 (이 동작이 on_file_selection_changed를 호출함)
            active_view.selectionModel().select(
                first_idx, 
                QItemSelectionModel.SelectionFlag.ClearAndSelect | QItemSelectionModel.SelectionFlag.Rows
            )
            active_view.setCurrentIndex(first_idx)

    def refresh_tree(self):
        idx = self.tree_view.currentIndex()
        self.dir_model.setRootPath(QDir.rootPath()) 
        self.dir_model.setRootPath("") 
        if idx.isValid(): self.tree_view.setCurrentIndex(idx)
        self.refresh_list()

    def refresh_list(self, force_update=False):
        self.right_bottom_panel.hide()
        index = self.tree_view.currentIndex()
        if not index.isValid(): return
        
        folder_path = self.dir_model.filePath(index)
        if not os.path.isdir(folder_path): return
        
        # --- [추가] 캐시 확인 및 사용 로직 ---
        include_sub = self.btn_subfolders.isChecked()
        cache_key = (folder_path, include_sub)
        if not force_update and cache_key in self.folder_scan_cache:
            cached_file_data, cached_total_size, cached_mtime = self.folder_scan_cache[cache_key]
            try:
                current_mtime = os.stat(folder_path).st_mtime
            except:
                current_mtime = 0

            # 루트 폴더의 mtime이 변경되지 않았다면 캐시 사용 (하위 폴더 변경은 file watcher/nas poller가 캐시를 지워주는 것을 신뢰)
            if abs(current_mtime - cached_mtime) < 2.0:
                if self.current_watched_folder != folder_path:
                    if self.current_watched_folder:
                        self.folder_watcher.removePath(self.current_watched_folder)
                    self.folder_watcher.addPath(folder_path)
                    self.current_watched_folder = folder_path
                    self.config["folder_last_path"] = folder_path
                    save_config(self.config)
                
                self.on_scan_finished(folder_path, list(cached_file_data), cached_total_size)
                return

        self.force_update_flag = force_update

        if self.current_watched_folder != folder_path:
            if self.current_watched_folder:
                self.folder_watcher.removePath(self.current_watched_folder)
            self.folder_watcher.addPath(folder_path)
            self.current_watched_folder = folder_path
            self.config["folder_last_path"] = folder_path
            save_config(self.config)
            
            # --- [추가됨] NAS 하이브리드 폴링 구동부 ---
            if not hasattr(self, 'nas_poll_timer'):
                self.nas_poll_timer = QTimer(self)
                self.nas_poll_timer.setInterval(10000) # 10초 주기
                self.nas_poll_timer.timeout.connect(self.check_nas_folder_mtime)
            
            try: self.last_folder_mtime = os.stat(folder_path).st_mtime
            except: self.last_folder_mtime = 0
            
            self.nas_poll_timer.start()
            # ------------------------------------------
        
        include_sub = self.btn_subfolders.isChecked()
        target_exts = ('.zip', '.cbz', '.cbr', '.rar', '.7z')
        
        self.is_force_syncing = False
        
        if self.scan_thread and self.scan_thread.isRunning():
            self.scan_thread.cancel()
            self.scan_thread.wait()
            self.scan_thread = None
            
        if self.extract_thread and self.extract_thread.isRunning():
            self.extract_thread.cancel()
            self.extract_thread.wait()
            try:
                self.extract_thread.data_extracted.disconnect()
                self.extract_thread.progress_updated.disconnect()
            except TypeError: pass
            self.extract_thread = None
            
        self.file_data_cache.clear()
        self.file_data_map.clear()
        # --- [수정됨] 삭제 및 새로고침 시 UI 잔상(깨짐) 방지 ---
        self.table_view.setUpdatesEnabled(False)
        self.table_view.clearSpans()
        # [수정] 로딩 오버레이를 위해 기존 UI 요소들을 숨깁니다.
        self.view_stack.hide()
        self.lbl_empty_state.hide()
        
        if hasattr(self, 'scan_overlay') and self.scan_overlay:
            self.scan_overlay.text = _("folder_scan_prep")
            self.scan_overlay.resize(self.right_top_panel.size())
            self.scan_overlay.show()
        
        self.table_view.setUpdatesEnabled(True)
        # --------------------------------------------------------
        self.lbl_tree_status.setText(_("folder_scan_prep"))
        self.is_syncing = False
        if hasattr(self, 'main_status_label') and self.main_status_label:
            self.main_status_label.setText(_("folder_ready"))
        self.progress_bar.hide()
        
        # --- [수정됨] force_update 플래그 전달 ---
        self.scan_thread = FolderScanThread(folder_path, include_sub, target_exts, self.thumb_dir, self.force_update_flag)
        self.scan_thread.progress_updated.connect(self.on_scan_progress)
        self.scan_thread.scan_finished.connect(self.on_scan_finished)
        self.scan_thread.start()

    def on_metadata_extracted(self, filepath, meta_dict, has_img_out):
        row = self.file_data_map.get(filepath)
        if not row: return

        if has_img_out:
            row["thumb_processed"] = True

        was_meta_already_processed = row.get("meta_processed", False)
        
        new_res = meta_dict.get("resolution", "") if meta_dict else ""
        if new_res:
            row["res"] = new_res
            
        if not was_meta_already_processed or new_res:
            row["meta_processed"] = True 
            if meta_dict is None: meta_dict = {}
            
            title = meta_dict.get("title", row.get("title", ""))
            series = meta_dict.get("series", row.get("series", ""))
            vol = meta_dict.get("volume", row.get("vol", ""))
            num = meta_dict.get("number", row.get("num", ""))
            writer = meta_dict.get("writer", row.get("writer", ""))
            
            row.update({
                "title": title,
                "series": series,
                "vol": vol,
                "num": num,
                "writer": writer
            })
            
            if "full_meta" not in row:
                row["full_meta"] = {}
            row["full_meta"].update(meta_dict)
            
            try:
                creators_list = []
                _writer = row["full_meta"].get("writer")
                if _writer: creators_list.append(_writer)
                for role in ['penciller', 'inker', 'colorist', 'letterer', 'cover_artist', 'editor']:
                    val = row["full_meta"].get(role)
                    if val: creators_list.append(val)
                creators_str = " / ".join(creators_list) if creators_list else ""
                
                y, m, d = row["full_meta"].get("year", ""), row["full_meta"].get("month", ""), row["full_meta"].get("day", "")
                publish_date_str = f"{y}-{m}-{d}".strip('-')
                if publish_date_str == "--": publish_date_str = ""
                
                self._db_upsert_buffer.append((
                    filepath, row.get("raw_mtime", 0), row.get("raw_size", 0), row.get("ext", ""),
                    row.get("res", ""), row["full_meta"].get("title", ""), row["full_meta"].get("series", ""),
                    row["full_meta"].get("series_group", ""), row["full_meta"].get("volume", ""), row["full_meta"].get("number", ""),
                    row["full_meta"].get("writer", ""), creators_str, row["full_meta"].get("publisher", ""), row["full_meta"].get("imprint", ""), 
                    row["full_meta"].get("genre", ""), row["full_meta"].get("volume_count", ""), row["full_meta"].get("page_count", ""), 
                    row["full_meta"].get("format", ""), row["full_meta"].get("manga", ""), row["full_meta"].get("language", ""),
                    row["full_meta"].get("rating", ""), row["full_meta"].get("age_rating", ""), publish_date_str, row["full_meta"].get("summary", ""), 
                    row["full_meta"].get("characters", ""), row["full_meta"].get("teams", ""), row["full_meta"].get("locations", ""), 
                    row["full_meta"].get("story_arc", ""), row["full_meta"].get("tags", ""), row["full_meta"].get("notes", ""), row["full_meta"].get("web", ""), ""
                ))
                
                # 50개가 모일 때마다 1번씩 벌크 인서트 진행
                if len(self._db_upsert_buffer) >= 50:
                    self._flush_db_buffer()
            except Exception as e: print(f"DB Upsert Error: {e}")

        disp_idx = row.get("display_index")
        if disp_idx is not None:
            idx1 = self.table_model.index(disp_idx, 0)
            idx2 = self.table_model.index(disp_idx, self.table_model.columnCount()-1)
            self.table_model.dataChanged.emit(idx1, idx2)

        if self.current_selected_path == filepath:
            self.update_info_panel(filepath, row.get("full_meta", {}))

    def _flush_db_buffer(self):
        """메모리에 쌓인 파일 데이터들을 DB에 한 번에 일괄 저장합니다."""
        if not getattr(self, '_db_upsert_buffer', None):
            return
        try:
            # 벌크 저장 메서드가 DB에 구현되어 있다면 사용, 없다면 안전하게 1개씩 저장 (하위호환)
            if hasattr(db, 'upsert_file_info_bulk'):
                db.upsert_file_info_bulk(self._db_upsert_buffer)
            else:
                for record in self._db_upsert_buffer:
                    db.upsert_file_info(*record)
        except Exception as e:
            print(f"DB Bulk Upsert Error: {e}")
        finally:
            self._db_upsert_buffer.clear()

    def _on_extract_thread_finished(self):
        self._flush_db_buffer()
        self.scroll_timer.start(10)

        # 필터가 켜져 있을 때 백그라운드 스캔으로 메타가 채워지면 리스트에서 즉시 숨기도록 디바운스 타이머 호출
        if hasattr(self, 'action_filter_no_meta') and self.action_filter_no_meta.isChecked():
            if not self.grouping_timer.isActive():
                self.grouping_timer.start(500)

    def on_tree_selection_changed(self):
        self.refresh_list()

    def get_selected_files(self):
        view = self.get_active_view()
        paths = []
        for idx in view.selectionModel().selectedIndexes():
            if idx.column() == 0:
                path = self.table_model.data(idx, Qt.ItemDataRole.UserRole)
                if path: paths.append(path)
        return paths

    def clear_tags(self):
        if hasattr(self, 'tag_layout'):
            while self.tag_layout.count():
                item = self.tag_layout.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.deleteLater()

    def on_file_selection_changed(self):
        view = self.get_active_view()
        indexes = [idx for idx in view.selectionModel().selectedIndexes() if idx.column() == 0]
        
        if not indexes:
            self.lbl_cover.clear()
            self.lbl_cover.setText(_("folder_cover_img"))
            if hasattr(self.right_bottom_panel, 'set_cover_image'):
                self.right_bottom_panel.set_cover_image(None)
                
            self.lbl_series_info.setText("")
            self.lbl_info_title.setText("")
            self.clear_tags()
            
            for i in reversed(range(self.meta_grid.count())):
                w = self.meta_grid.itemAt(i).widget()
                if w: w.deleteLater()
                
            self.lbl_summary.setText("")
            
            while self.extra_layout.count():
                item = self.extra_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            
            index = self.tree_view.currentIndex()

            if index.isValid():
                folder_path = self.dir_model.filePath(index)
                self.lbl_tree_status.setText(_("folder_status_sel").format(os.path.basename(folder_path), len(self.file_data_cache), "0 B"))
            self.right_bottom_panel.hide()
            self.current_selected_path = ""
            return

        last_index = indexes[-1]
        full_path = self.table_model.data(last_index, Qt.ItemDataRole.UserRole)
        
        if not full_path:
            self.right_bottom_panel.hide()
            return

        self.current_selected_path = full_path
        self.right_bottom_panel.show()
        
        sizes = self.right_splitter.sizes()
        if len(sizes) >= 2 and sizes[1] == 0:
            total = sum(sizes)
            if total > 0:
                self.right_splitter.setSizes([int(total * 0.65), int(total * 0.35)])
            else:
                self.right_splitter.setSizes([700, 300])
        
        try:
            stat = os.stat(full_path)
            size_str = self.format_size(stat.st_size)
            self.lbl_tree_status.setText(_("folder_status_file").format(full_path, size_str))
        except: pass
        
        row = self.file_data_map.get(full_path)
        if row:
            if row.get("full_meta"):
                self.update_info_panel(full_path, row["full_meta"])
                
                if not row.get("thumb_processed"):
                    file_hash = row.get("hash", "")
                    thumb_path = os.path.join(self.thumb_dir, f"{file_hash}.webp")
                    seven_zip_path = get_resource_path('7za.exe')
                    
                    if self.extract_thread and self.extract_thread.isRunning():
                        self.extract_thread.cancel()
                        self.extract_thread.wait()
                        try:
                            self.extract_thread.data_extracted.disconnect()
                            self.extract_thread.progress_updated.disconnect()
                        except TypeError: pass
                        
                    from core.parser import MemoryExtractThread
                    self.extract_thread = MemoryExtractThread([(full_path, True, False, thumb_path)], seven_zip_path)
                    self.extract_thread.data_extracted.connect(self.on_metadata_extracted)
                    self.extract_thread.start()
                    
                return
        
        self.update_info_panel(full_path, {})

    def update_info_panel(self, full_path, meta_dict):
        from PyQt6.QtCore import Qt
        import qtawesome as qta

        self.lbl_cover.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        # ── 커버 이미지 ───────────────────────────────────────────────
        def get_covered_pixmap(pm, w=220, h=310, radius=10):
            from PyQt6.QtGui import QPixmap, QPainter, QPainterPath
            scaled = pm.scaled(
                w, h,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            crop_x = (scaled.width() - w) // 2
            cropped = scaled.copy(crop_x, 0, w, h)
            rounded = QPixmap(w, h)
            rounded.fill(Qt.GlobalColor.transparent)
            painter = QPainter(rounded)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            path = QPainterPath()
            path.addRoundedRect(0, 0, w, h, radius, radius)
            painter.setClipPath(path)
            painter.drawPixmap(0, 0, cropped)
            painter.end()
            return rounded

        row = self.file_data_map.get(full_path)
        if row:
            file_hash = row.get("hash", "")
            thumb_path = os.path.join(self.thumb_dir, f"{file_hash}.webp")
            cached_pix = QPixmapCache.find(file_hash) if file_hash else None
            if cached_pix is not None and not cached_pix.isNull():
                self.lbl_cover.setPixmap(get_covered_pixmap(cached_pix))
                if hasattr(self.right_bottom_panel, 'set_cover_image'):
                    self.right_bottom_panel.set_cover_image(cached_pix)
            elif os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
                from PyQt6.QtGui import QPixmap
                pixmap = QPixmap(thumb_path)
                if not pixmap.isNull():
                    QPixmapCache.insert(file_hash, pixmap)
                    self.lbl_cover.setPixmap(get_covered_pixmap(pixmap))
                    if hasattr(self.right_bottom_panel, 'set_cover_image'):
                        self.right_bottom_panel.set_cover_image(pixmap)
                else:
                    self.lbl_cover.setText(_("folder_no_cover"))
                    if hasattr(self.right_bottom_panel, 'set_cover_image'):
                        self.right_bottom_panel.set_cover_image(None)
            else:
                self.lbl_cover.setText(_("folder_no_cover"))
                if hasattr(self.right_bottom_panel, 'set_cover_image'):
                    self.right_bottom_panel.set_cover_image(None)
        else:
            self.lbl_cover.setText(_("folder_no_cover"))
            if hasattr(self.right_bottom_panel, 'set_cover_image'):
                self.right_bottom_panel.set_cover_image(None)

        # ── 시리즈 / 제목 ─────────────────────────────────────────────
        title = meta_dict.get("title") or os.path.basename(full_path)
        series = meta_dict.get("series") or _("info_no_series")
        series_group = meta_dict.get("series_group") or ""
        series_info = f"{series} / {series_group}" if series_group else series
        self.lbl_series_info.setText(series_info)
        self.lbl_info_title.setText(title)

        # ── 태그 뱃지 ─────────────────────────────────────────────────
        self.clear_tags()
        genre_raw = meta_dict.get("genre") or ""
        tags_raw  = meta_dict.get("tags")  or ""
        tag_list  = []
        if genre_raw and genre_raw != "-":
            tag_list.extend([g.strip() for g in genre_raw.split(',') if g.strip()])
        if tags_raw and tags_raw != "-":
            tag_list.extend([t.strip() for t in tags_raw.split(',') if t.strip()])
        seen, combined_tags = set(), []
        for t in tag_list:
            if t not in seen:
                seen.add(t)
                combined_tags.append(t)

        fs = self.config.get('s11', 11)
        for tag in combined_tags:
            lbl = QLabel(f"{tag}")
            lbl.setStyleSheet(f"""
                QLabel {{
                    background-color: rgba(255,255,255,0.08);
                    color: rgba(210,210,210,0.95);
                    border: 1px solid rgba(255,255,255,0.05);
                    border-radius: 5px;
                    padding: 3px 3px;
                    font-size: {fs}px;
                }}
            """)
            self.tag_layout.addWidget(lbl)

        # ── 메타 그리드 — 1열 리스트, 행마다 [아이콘+라벨 | 값] ──────
        for i in reversed(range(self.meta_grid.count())):
            w = self.meta_grid.itemAt(i).widget()
            if w:
                w.deleteLater()

        creators_list = []
        writer = meta_dict.get("writer")
        if writer:
            creators_list.append(writer)
        for role in ['penciller', 'inker', 'colorist', 'letterer', 'cover_artist', 'editor']:
            v = meta_dict.get(role)
            if v:
                creators_list.append(v)
        creators = " / ".join(creators_list) if creators_list else "-"
        if meta_dict.get("creators"):
            creators = meta_dict.get("creators")

        publisher    = meta_dict.get("publisher") or "-"
        imprint      = meta_dict.get("imprint") or ""
        pub_full     = f"{publisher} / {imprint}" if imprint else publisher
        volume_count = meta_dict.get("volume_count") or meta_dict.get("volume") or "-"
        page_count   = meta_dict.get("page_count") or "-"
        format_val   = meta_dict.get("format") or "-"
        manga        = meta_dict.get("manga") or "-"
        rating       = meta_dict.get("rating") or "-"
        age_rating   = meta_dict.get("age_rating") or "-"

        publish_date = meta_dict.get("publish_date")
        if not publish_date:
            y = meta_dict.get("year", "")
            m = meta_dict.get("month", "")
            d = meta_dict.get("day", "")
            publish_date = f"{y}-{m}-{d}".strip('-') or "-"

        fs_lbl = self.config.get('s11', 11)
        fs_val = self.config.get('s12', 12)

        # 평점 값: 별 아이콘 + 숫자 (목표 이미지처럼)
        rating_str = str(rating)

        grid_items = [
            ('fa5s.user-edit',    _('col_creators'),                   creators),
            ('fa5s.building',     _('col_publisher'),                   pub_full),
            ('fa5s.file-alt',     _('col_page_count'),                  str(page_count)),
            ('fa5s.layer-group',  _('col_vol_count'),                   str(volume_count)),
            ('fa5s.book-open',    f"{_('col_format')}/{_('col_manga')}", f"{format_val} / {manga}"),
            ('fa5s.star',         _('col_rating'),                      rating_str),
            ('fa5s.child',        _('col_age_rating'),                  str(age_rating)),
            ('fa5s.calendar-alt', _('col_pub_date'),                    str(publish_date)),
        ]

        for row_i, (icon_name, lbl_text, val_text) in enumerate(grid_items):
            cell_col = QVBoxLayout()
            cell_col.setContentsMargins(0, 0, 0, 0)
            cell_col.setSpacing(0)

            row_w = QWidget()
            row_w.setStyleSheet("background: transparent;")
            row_h = QHBoxLayout(row_w)
            row_h.setContentsMargins(0, 7, 0, 7)
            row_h.setSpacing(10)

            i_lbl = QLabel()
            i_lbl.setPixmap(qta.icon(icon_name, color='#ffffff').pixmap(13, 13))  # 아이콘 흰색
            i_lbl.setFixedWidth(16)
            i_lbl.setStyleSheet("background: transparent;padding-left:5px")

            k_lbl = QLabel(lbl_text)
            k_lbl.setFixedWidth(90)
            k_lbl.setStyleSheet(
                f"color: #dadcde; font-size: {fs_lbl}px; font-weight: bold; background: transparent;"  # bold 추가
            )

            if icon_name == 'fa5s.star' and val_text not in ("-", ""):
                val_widget = QWidget()
                val_widget.setStyleSheet("background: transparent;")
                val_h = QHBoxLayout(val_widget)
                val_h.setContentsMargins(0, 0, 0, 0)
                val_h.setSpacing(4)
                star_lbl = QLabel()
                star_lbl.setPixmap(qta.icon('fa5s.star', color='#F5A623').pixmap(12, 12))
                star_lbl.setStyleSheet("background: transparent;")
                num_lbl = QLabel(val_text)
                num_lbl.setStyleSheet(
                    f"color: #cccccc; font-size: {fs_val}px; font-weight: 500; background: transparent;"  # ← #cccccc
                )
                val_h.addWidget(star_lbl)
                val_h.addWidget(num_lbl)
                val_h.addStretch()
                row_h.addWidget(i_lbl)
                row_h.addWidget(k_lbl)
                row_h.addWidget(val_widget, 1)
            else:
                v_lbl = QLabel(val_text)
                v_lbl.setStyleSheet(
                    f"color: #bbbbbb; font-size: {fs_val}px;background: transparent;"  # ← #cccccc
                )
                v_lbl.setWordWrap(True)
                v_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                row_h.addWidget(i_lbl)
                row_h.addWidget(k_lbl)
                row_h.addWidget(v_lbl, 1)

            cell_col.addWidget(row_w)

            if row_i < len(grid_items) - 1:
                sep = QWidget()
                sep.setFixedHeight(1)
                sep.setStyleSheet("background-color: rgba(255,255,255,0.07);")
                cell_col.addWidget(sep)

            wrapper = QWidget()
            wrapper.setStyleSheet("background: transparent;")
            wrapper.setLayout(cell_col)
            wrapper.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            self.meta_grid.addWidget(wrapper, row_i, 0)

        # ── 줄거리 ────────────────────────────────────────────────────
        self.lbl_summary_icon.setPixmap(
            qta.icon('fa5s.play-circle', color='#E8A020').pixmap(13, 13)
        )
        summary = meta_dict.get("summary") or _("info_no_summary")
        self.lbl_summary.setText(summary)

        # ── 추가정보 (스토리아크 / 등장인물 / 링크) ───────────────────
        while self.extra_layout.count():
            item = self.extra_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        characters = meta_dict.get("characters") or "-"
        teams      = meta_dict.get("teams")      or "-"
        locations  = meta_dict.get("locations")  or "-"
        story_arc  = meta_dict.get("story_arc")  or "-"
        link       = meta_dict.get("web")        or "-"
        link_html  = (
            f'<a href="{link}" style="color:#3498DB;text-decoration:none;">{link}</a>'
            if link != "-" else "-"
        )

        extra_items = [
            ('fa5s.map-marker-alt', _('info_arc_team_loc'),
            f"{story_arc} / {teams} / {locations}"),
            ('fa5s.user-friends', _('col_characters'), characters),
            ('fa5s.link',         _('col_web'),        link_html),
        ]

        for icon_name, lbl_text, val_text in extra_items:
            is_link = icon_name == 'fa5s.link'  # ← 링크 여부 판별

            w = QWidget()
            w.setStyleSheet("background: transparent;")
            ly = QHBoxLayout(w)
            ly.setContentsMargins(0, 4, 0, 4)
            ly.setSpacing(8)

            icon_color = '#E8A020' if is_link else '#ffffff'  # ← 링크면 주황, 아니면 흰색
            i_lbl = QLabel()
            i_lbl.setPixmap(qta.icon(icon_name, color=icon_color).pixmap(13, 13))
            i_lbl.setFixedWidth(16)
            i_lbl.setStyleSheet("background: transparent;")

            k_lbl = QLabel(lbl_text)
            k_lbl.setFixedWidth(90)
            lbl_color = '#E8A020' if is_link else '#dadcde'   # ← 링크면 주황, 아니면 #dadcde
            k_lbl.setStyleSheet(
                f"color: {lbl_color}; font-size: {fs_lbl}px; font-weight: bold; background: transparent;"
            )

            v_lbl = QLabel(val_text)
            val_color = '#3498DB' if is_link else '#cccccc'   # ← 링크값은 파란색, 나머지 #ccc
            v_lbl.setStyleSheet(
                f"color: {val_color}; font-size: {fs_val}px; background: transparent;"
            )
            v_lbl.setWordWrap(True)
            v_lbl.setOpenExternalLinks(True)
            v_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)

            ly.addWidget(i_lbl)
            ly.addWidget(k_lbl)
            ly.addWidget(v_lbl, 1)
            self.extra_layout.addWidget(w)

    def show_tree_context_menu(self, position):
        index = self.tree_view.indexAt(position)
        if not index.isValid(): return
        path = self.dir_model.filePath(index)
        menu = QMenu()
        
        # 단축키 표시용 헬퍼 함수
        def add_menu_action(text, shortcut, slot):
            from PyQt6.QtGui import QAction
            action = QAction(text, self)
            if shortcut:
                action.setShortcut(shortcut)
            action.triggered.connect(slot)
            menu.addAction(action)
            return action
        
        custom_favs = self.config.get("folder_favorites", [])
        is_fav = any(f["path"] == path for f in custom_favs)
        
        if is_fav:
            add_menu_action(_("action_fav_rem"), None, lambda: self.remove_from_favorites(path))
        else:
            add_menu_action(_("action_fav_add"), None, lambda: self.add_to_favorites(path))
            
        menu.addSeparator()
        add_menu_action(_("action_open_exp"), None, lambda: self.open_in_explorer(path))
        add_menu_action(_("action_ren_folder"), "Shift+R", lambda: self.rename_folder(index))
        
        # F1~F3 메뉴 기능 추가
        menu.addSeparator()
        add_menu_action(_("action_flatten_structure"), "F1", self.send_to_tab1)
        add_menu_action(_("action_inner_ren"), "F2", self.send_to_tab2)
        add_menu_action(_("action_meta_edit"), "F3", self.send_to_tab3)
        
        menu.addSeparator()
        add_menu_action(_("action_del_folder"), "Del", self.delete_selected)
        add_menu_action(_("action_refresh"), "F5", self.refresh_tree)
        
        menu.exec(self.tree_view.viewport().mapToGlobal(position))

    def show_list_context_menu(self, position):
        view = self.get_active_view()
        if not view.selectionModel().hasSelection(): return
        
        if not self.get_selected_files(): return
        
        menu = QMenu()
        
        def add_menu_action(text, shortcut, slot):
            action = QAction(text, self)
            if shortcut:
                action.setShortcut(shortcut)
            action.triggered.connect(slot)
            menu.addAction(action)
            return action

        add_menu_action(_("action_view"), None, self.open_viewer)
        
        add_menu_action(_("action_flatten_structure"), "F1", self.send_to_tab1)
        add_menu_action(_("action_inner_ren"), "F2", self.send_to_tab2)
        add_menu_action(_("action_meta_edit"), "F3", self.send_to_tab3)
        
        add_menu_action(_("action_update_files"), None, self.force_update_selected_files)
        menu.addSeparator()
        
        # 새롭게 추가된 기능: 책 제목 기반 시리즈 분류
        add_menu_action(_("action_group_by_series"), None, self.action_group_by_series)
        menu.addSeparator()

        add_menu_action(_("action_del_files"), "Del", self.delete_selected)
        
        add_menu_action(_("tf_menu_rename_multi"), "Shift+R", self.action_multi_rename)
        
        history_file = os.path.join(os.getcwd(), "rename_history.json")
        if os.path.exists(history_file):
            add_menu_action(_("tf_undo_rename"), "Ctrl+Z", self.action_undo_rename)
        
        add_menu_action(_("action_open_exp"), None, self.open_selected_in_explorer)
        menu.addSeparator()
        add_menu_action(_("action_sel_all"), "Ctrl+A", self.select_all_files)
        add_menu_action(_("action_inv_sel"), None, self.invert_selection)
        add_menu_action(_("action_refresh"), "F5", self.refresh_list)
        
        menu.exec(view.viewport().mapToGlobal(position))

    # [신규] 최근 이름 변경을 복구하는 Undo 로직
    def action_undo_rename(self):
        import json
        history_file = os.path.join(os.getcwd(), "rename_history.json")
        if not os.path.exists(history_file): return
        
        try:
            with open(history_file, "r", encoding="utf-8") as f:
                history = json.load(f)
                
            if not history: 
                QMessageBox.warning(self, "Undo", _("tf_undo_fail"))
                return
                
            last_record = history.pop() # 가장 최근 기록 꺼내기
            mapping = last_record.get("mapping", {})
            success_count = 0
            
            for current_path, old_path in mapping.items():
                if os.path.exists(current_path) and not os.path.exists(old_path):
                    try:
                        os.rename(current_path, old_path)
                        success_count += 1
                    except Exception as e: print(e)
                    
            # 남은 기록 다시 저장
            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
                
            from ui.widgets import Toast
            Toast.show(self.main_window, _("tf_undo_success") + f" ({success_count} files)")
            self.refresh_list()
            
        except Exception as e:
            QMessageBox.critical(self, "Undo Error", str(e))

    def action_multi_rename(self):
        """일괄 이름 바꾸기 실행 로직"""
        selected_files = self.get_selected_files()
        if not selected_files: return
        
        from ui.dialogs import MultiRenameDialog
        from core.i18n import get_i18n
        
        # 현재 활성화된 언어 사전 가져오기
        current_i18n = get_i18n().get(_CURRENT_LANG, get_i18n()["ko"])
        
        dialog = MultiRenameDialog(selected_files, current_i18n, self)
        if dialog.exec():
            self.refresh_list()
            
            rename_map = dialog.get_rename_map()
            if not rename_map: return
            
            success_count = 0
            errors = []
            
            for old_path, new_path in rename_map.items():
                try:
                    if os.path.exists(new_path) and old_path.lower() != new_path.lower():
                        errors.append(f"중복 발생: {os.path.basename(new_path)}")
                        continue
                        
                    os.rename(old_path, new_path)
                    success_count += 1
                except Exception as e:
                    errors.append(f"{os.path.basename(old_path)}: {str(e)}")
            
            self.refresh_list() 
            
            if errors:
                QMessageBox.warning(self, current_i18n.get("msg_notice", "알림"), f"{success_count}개 변경 성공\n오류:\n" + "\n".join(errors))
            else:
                from ui.widgets import Toast
                Toast.show(self.main_window, f"{success_count}개의 파일 이름을 변경했습니다.")

    def select_all_files(self):
        self.get_active_view().selectAll()

    def invert_selection(self):
        view = self.get_active_view()
        model = view.model()
        selection_model = view.selectionModel()
        selection = QItemSelection(model.index(0, 0), model.index(model.rowCount() - 1, model.columnCount() - 1))
        selection_model.select(selection, QItemSelectionModel.SelectionFlag.Toggle)

    def hotkey_f2(self):
        if self.tree_view.hasFocus():
            self.rename_folder()
        else:
            self.send_to_tab3()

    def open_viewer(self):
        viewer_path = self.config.get("viewer_path", "")
        if not viewer_path or not os.path.exists(viewer_path):
            QMessageBox.warning(self, _("dlg_warn"), _("dlg_warn_viewer"))
            return
        files = self.get_selected_files()
        if files: subprocess.Popen([viewer_path, files[0]])

    def open_in_explorer(self, path):
        if os.name == 'nt': os.startfile(path)
        else: subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', path])

    def open_selected_in_explorer(self):
        files = self.get_selected_files()
        if files: self.open_in_explorer(os.path.dirname(files[0]))

    def show_goto_dialog(self):
        dialog = QDialog(self)
        # self.i18n.get 대신 글로벌 번역 함수 _() 사용
        dialog.setWindowTitle(_("fm_title"))
        dialog.resize(400, 100)
        dialog.setStyleSheet("QDialog { background-color: #2b2b2b; color: white; } QLabel { color: white; }")
        
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(_("fm_dsc")))
        
        input_line = QLineEdit()
        input_line.setText(self.current_watched_folder)
        input_line.setStyleSheet("""
            QLineEdit { background-color: #1e1e1e; color: white; border: 1px solid #555; border-radius: 4px; padding: 4px 10px; }
            QLineEdit:focus { border: 1px solid #3498DB; }
        """)
        layout.addWidget(input_line)
        
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_ok = btn_box.button(QDialogButtonBox.StandardButton.Ok)
        btn_cancel = btn_box.button(QDialogButtonBox.StandardButton.Cancel)
        
        # 공통 키워드 사용
        btn_ok.setText(_("btn_ok"))
        btn_cancel.setText(_("btn_cancel"))
        
        btn_primary_color = self.config.get("btn_primary", "#0078d7")
        
        btn_ok.setStyleSheet(f"""
            QPushButton {{
                background-color: {btn_primary_color};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 5px 15px;
            }}
            QPushButton:hover {{ background-color: #3a7ebf; }}
        """)
        
        btn_cancel.setStyleSheet("""
            QPushButton {{
                background-color: #555555;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 5px 15px;
            }}
            QPushButton:hover {{ background-color: #666666; }}
        """)
        
        btn_box.accepted.connect(dialog.accept)
        btn_box.rejected.connect(dialog.reject)
        layout.addWidget(btn_box)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            path = input_line.text().strip()
            if os.path.exists(path) and os.path.isdir(path):
                self._start_queued_scroll(path)
            else:
                QMessageBox.warning(self, _("fm_error"), _("fm_error_desc"))

    def send_to_tab1(self):
        if self.tree_view.hasFocus():
            idx = self.tree_view.currentIndex()
            files = [self.dir_model.filePath(idx)] if idx.isValid() else []
        else:
            files = self.get_selected_files()
            
        if files and hasattr(self.main_window, 'tab1'):
            self.main_window.tabs.setCurrentWidget(self.main_window.tab1)
            self.main_window.process_paths(files)

    def send_to_tab2(self):
        if self.tree_view.hasFocus():
            idx = self.tree_view.currentIndex()
            files = [self.dir_model.filePath(idx)] if idx.isValid() else []
        else:
            files = self.get_selected_files()
            
        if files and hasattr(self.main_window, 'tab2'):
            self.main_window.tabs.setCurrentWidget(self.main_window.tab2)
            if hasattr(self.main_window.tab2, 'process_paths'): self.main_window.tab2.process_paths(files)

    def send_to_tab3(self):
        if self.tree_view.hasFocus():
            idx = self.tree_view.currentIndex()
            files = [self.dir_model.filePath(idx)] if idx.isValid() else []
        else:
            files = self.get_selected_files()
            
        if files and hasattr(self.main_window, 'tab3'):
            self.main_window.tabs.setCurrentWidget(self.main_window.tab3)
            if hasattr(self.main_window.tab3, 'process_paths'): self.main_window.tab3.process_paths(files)

    def get_missing_volumes_data(self):
        import os, re
        from collections import defaultdict
        from core.library_db import db
        from core.parser import extract_core_title

        def extract_vol_numbers(name, series_name=""):
            name = re.sub(r'(?i)\b(1080p|720p|480p|1440p|4k|2k|x264|x265)\b', '', name)
            name = re.sub(r'\[19\d{2}\]|\[20\d{2}\]|\(19\d{2}\)|\(20\d{2}\)', '', name)
            
            range_match = re.search(r'(\d+(?:\.\d+)?)\s*(권|화|장|편|부)\s*[~-]\s*(\d+(?:\.\d+)?)\s*(권|화|장|편|부)', name, re.IGNORECASE)
            if range_match:
                try:
                    start = int(float(range_match.group(1)))
                    end = int(float(range_match.group(3)))
                    if start <= end and end - start < 150:
                        return list(range(start, end + 1))
                except ValueError:
                    pass

            vol_match = re.search(r'(?:제|v|vol\.?\s*)?(\d+(?:\.\d+)?(?:\s*[~-]\s*\d+(?:\.\d+)?)?)\s*(권|화|장|편|부)', name, re.IGNORECASE)
            if vol_match:
                num_str = vol_match.group(1)
            else:
                pre_match = re.search(r'(?i)(?:vol|v|권|화|제|chapter|ch|#)\s*\.?\s*(\d+(?:\.\d+)?(?:\s*[~-]\s*\d+(?:\.\d+)?)?)', name)
                if pre_match:
                    num_str = pre_match.group(1)
                else:
                    clean_for_nums = re.sub(r'\[.*?\]|\(.*?\)', '', name)
                    if series_name:
                        safe_series = r'\s*'.join(re.escape(word) for word in series_name.split())
                        clean_for_nums = re.sub(f'(?i){safe_series}', '', clean_for_nums)
                    matches = re.findall(r'\d+(?:\.\d+)?(?:\s*[~-]\s*\d+(?:\.\d+)?)?(?![가-힣a-zA-Z])', clean_for_nums)
                    if matches:
                        num_str = matches[-1]
                    else:
                        return []

            if '~' in num_str or '-' in num_str:
                parts = re.split(r'\s*[~-]\s*', num_str)
                if len(parts) >= 2:
                    try:
                        start = int(float(parts[0]))
                        end = int(float(parts[1]))
                        if start <= end and end - start < 150:
                            return list(range(start, end + 1))
                        else:
                            return [start]
                    except ValueError:
                        pass
            
            try:
                return [int(float(num_str))]
            except ValueError:
                return []

        series_map = defaultdict(list)
        dup_folders = self.config.get("dup_check_folders", [])

        # [핵심] 1. 설정에 등록된 '중복 검사 대상 폴더(메인 라이브러리)'의 전체 DB 인덱스를 활용
        if dup_folders:
            for folder in dup_folders:
                if not os.path.exists(folder): continue
                records = db.get_target_index(folder)
                if not records: continue

                for record in records:
                    if isinstance(record, dict):
                        fp = record.get("full_path", "")
                        name = record.get("name", "")
                    else:
                        fp = record[0]
                        name = record[2]

                    if not fp or not name: continue

                    series_name = extract_core_title(os.path.splitext(name)[0]).strip()
                    if not series_name: 
                        series_name = os.path.basename(os.path.dirname(fp))

                    series_map[series_name].append({
                        "name": name,
                        "folder_path": os.path.dirname(fp),
                        "series_name": series_name
                    })
        else:
            # 2. 설정된 메인 라이브러리가 없다면 기존처럼 현재 화면의 데이터를 활용 (Fallback)
            for row in getattr(self, 'file_data_cache', []):
                if row.get("is_folder") or row.get("is_dup_folder") or row.get("is_dup_child"): continue
                
                series_name = row.get("series") or row.get("full_meta", {}).get("series", "")
                if not series_name:
                    series_name = extract_core_title(os.path.splitext(row.get("name", ""))[0]).strip()
                if not series_name:
                    series_name = os.path.basename(os.path.dirname(row.get("full_path", "")))
                    
                if series_name:
                    series_map[series_name].append({
                        "name": row.get("name", ""),
                        "folder_path": os.path.dirname(row.get("full_path", "")),
                        "series_name": series_name
                    })

        missing_data = []
        for s_name, items in series_map.items():
            vols = set()
            folder_paths = set()
            for item in items:
                v_nums = extract_vol_numbers(item["name"], item["series_name"])
                for v in v_nums:
                    vols.add(v)
                folder_paths.add(item["folder_path"])
                    
            if vols:
                min_v, max_v = min(vols), max(vols)
                # 오탐지 방지: 첫 권과 끝 권의 차이가 150 이하일 때만 검사
                if max_v - min_v < 150:
                    missing = [str(i) for i in range(min_v, max_v) if i not in vols]
                    
                    if missing:
                        missing_data.append({
                            "series": s_name,
                            "missing": missing,
                            "folder_path": list(folder_paths)[0] 
                        })
                        
        # UI에서 찾기 쉽도록 시리즈 이름 가나다 순으로 정렬
        missing_data.sort(key=lambda x: x["series"])
        return missing_data

    def show_missing_volumes_dialog(self):
        # 1. 이미 토스트 알림용으로 분석된 데이터가 있다면 즉시 팝업 표시 (로딩 0초)
        if getattr(self, '_cached_missing_data', None) is not None:
            self._build_and_show_missing_dialog(self._cached_missing_data)
            return

        # 2. 만약 폴더에 들어오자마자 빛의 속도로 버튼을 눌러서 백그라운드 분석이 덜 끝났다면 대기
        if hasattr(self, 'toast_check_thread') and self.toast_check_thread.isRunning():
            self.btn_check_missing.setEnabled(False)
            self.btn_check_missing.setText(_("tf_btn_check_missing") + " (분석 중...)")
            self._waiting_for_dialog = True 
            return

        # 3. 예외 상황 (스레드 단독 실행)
        if hasattr(self, 'missing_check_thread') and self.missing_check_thread.isRunning():
            return
            
        self.btn_check_missing.setEnabled(False)
        self.btn_check_missing.setText(_("tf_btn_check_missing") + " (분석 중...)")
        
        dup_folders = self.config.get("dup_check_folders", [])
        self.missing_check_thread = MissingCheckThread(dup_folders, getattr(self, 'file_data_cache', []), is_toast=False)
        self.missing_check_thread.finished_signal.connect(self._on_missing_data_ready)
        self.missing_check_thread.start()

    def _on_missing_data_ready(self, missing_data, is_toast):
        # 백그라운드 분석이 완료되면 무조건 캐시에 결과 저장
        self._cached_missing_data = missing_data
        
        base_text = _("tf_btn_check_missing")
        badge_text = f"{base_text}  🔴 {len(missing_data)}" if missing_data else base_text
        badge_text = f"{base_text}  🔔 {len(missing_data)}" if missing_data else base_text
        self.btn_check_missing.setText(badge_text)
        
        if is_toast:
            if not getattr(self, '_has_shown_global_missing_toast', False):
                self._has_shown_global_missing_toast = True
                if missing_data:
                    try:
                        from ui.widgets import Toast
                        Toast.show(self.main_window, _("tf_toast_missing").format(len(missing_data)))
                    except Exception: pass
            else:
                self._show_missing_toast_delayed()
                
            if getattr(self, '_waiting_for_dialog', False):
                self._waiting_for_dialog = False
                self.btn_check_missing.setEnabled(True)
                self._build_and_show_missing_dialog(missing_data)
            return

        self.btn_check_missing.setEnabled(True)
        self._build_and_show_missing_dialog(missing_data)
        
    def _build_and_show_missing_dialog(self, missing_data):
        if not missing_data:
            QMessageBox.information(self, _("tf_dlg_missing_title"), "누락된 권수가 없습니다.")
            return
            
        dialog = QDialog(self)
        dialog.setWindowTitle(_("tf_dlg_missing_title"))
        dialog.resize(550, 450)
        dialog.setStyleSheet("QDialog { background-color: #2b2b2b; color: white; }")
        
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(_("tf_dlg_missing_desc")))
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: 1px solid #444; background: #1e1e1e; }")
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        
        for item in missing_data:
            row_w = QWidget()
            row_w.setStyleSheet("border-bottom: 1px solid #333;")
            row_ly = QHBoxLayout(row_w)
            row_ly.setContentsMargins(5, 5, 5, 5)
            
            lbl_s = QLabel(f"<b>{item['series']}</b>")
            lbl_s.setStyleSheet("color: #E8A020; border: none;")
            lbl_s.setFixedWidth(150)
            
            missing_str = ", ".join(item['missing'])
            if len(item['missing']) > 8:
                missing_str = ", ".join(item['missing'][:8]) + f" ... (총 {len(item['missing'])}권)"
            lbl_m = QLabel(f"누락: {missing_str}")
            lbl_m.setStyleSheet("color: #E74C3C; border: none;")
            lbl_m.setWordWrap(True)
            
            btn_go = QPushButton(_("tf_btn_move"))
            btn_go.setStyleSheet("background-color: #3498DB; color: white; border-radius: 4px; padding: 4px 12px; border: none;")
            btn_go.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_go.clicked.connect(lambda checked, path=item['folder_path']: self._goto_missing_folder(path, dialog))
            
            row_ly.addWidget(lbl_s)
            row_ly.addWidget(lbl_m, 1)
            row_ly.addWidget(btn_go)
            content_layout.addWidget(row_w)
            
        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll)
        
        dialog.exec()
        
    def _goto_missing_folder(self, folder_path, dialog):
        dialog.accept()
        self._start_queued_scroll(folder_path)
        self.set_grouping("path")

    def check_nas_folder_mtime(self):
        # 내가 프로그램 내부에서 파일을 지웠을 때는 NAS 폴링 변화 감지 무시
        if getattr(self, '_internal_action_lock', False): return
        
        if not self.current_watched_folder or not os.path.exists(self.current_watched_folder):
            return
        try:
            current_mtime = os.stat(self.current_watched_folder).st_mtime
            if current_mtime != getattr(self, 'last_folder_mtime', 0):
                # --- [추가] 캐시 무효화 ---
                include_sub = self.btn_subfolders.isChecked()
                cache_key = (self.current_watched_folder, include_sub)
                if cache_key in self.folder_scan_cache:
                    del self.folder_scan_cache[cache_key]
                # ------------------------

                self.last_folder_mtime = current_mtime
                self.refresh_list(force_update=False)
        except Exception:
            pass

    def action_group_by_series(self):
        import os
        import shutil
        import re
        from core.parser import extract_core_title
        
        selected_files = self.get_selected_files()
        if not selected_files: return
        
        success_count = 0
        
        # 파일 조작 시 자동 새로고침 및 UI 충돌을 방지하기 위해 락 활성화
        self._internal_action_lock = True
        
        for fp in selected_files:
            base_name = os.path.basename(fp)
            name_no_ext = os.path.splitext(base_name)[0]
            
            core_title = extract_core_title(name_no_ext).strip()
            if not core_title:
                core_title = name_no_ext
            
            # 폴더명에 사용할 수 없는 특수문자 안전하게 치환
            core_title = re.sub(r'[\\/:*?"<>|]', '_', core_title)
            
            current_dir = os.path.dirname(fp)
            current_folder_name = os.path.basename(current_dir)
            
            # 현재 파일이 위치한 폴더명이 이미 책 제목과 같다면 이동 생략
            if current_folder_name.lower() == core_title.lower():
                continue
                
            target_dir = os.path.join(current_dir, core_title)
            target_path = os.path.join(target_dir, base_name)
            
            if not os.path.exists(target_dir):
                try:
                    os.makedirs(target_dir, exist_ok=True)
                except Exception: 
                    continue
                
            if not os.path.exists(target_path):
                try:
                    shutil.move(fp, target_path)
                    success_count += 1
                    
                    # 이동 완료 후 현재 메모리 맵에서 해당 데이터 제거
                    if fp in self.file_data_map:
                        del self.file_data_map[fp]
                except Exception as e:
                    print(f"Move error: {e}")
                    
        self._internal_action_lock = False
        
        # 이동 성공한 항목이 있다면 UI 상태 업데이트
        if success_count > 0:
            self.file_data_cache = [row for row in self.file_data_cache if row.get("full_path") in self.file_data_map]
            self.apply_grouping_and_sorting()
            
            try:
                from ui.widgets import Toast
                Toast.show(self.main_window, _("msg_series_grouped").format(success_count))
            except Exception:
                pass
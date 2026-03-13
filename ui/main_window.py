import os
import threading
import webbrowser
from pathlib import Path

from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QProgressBar, QComboBox, QLineEdit, QFrame, QFileDialog, QMessageBox, QTableWidgetItem, QTreeWidgetItem, QAbstractItemView, QHeaderView, QTextBrowser, QSizePolicy, QTabWidget, QTableWidget, QTabWidget, QTableWidget
from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QImage, QPixmap, QPainter, QPainterPath, QIcon, QColor

from config import load_config, save_config, get_resource_path, CURRENT_VERSION
from utils import play_complete_sound, natural_keys
from ui.signals import WorkerSignals
from ui.widgets import ArchiveTableWidget, OrgTreeWidget
from ui.dialogs import LogDialog, SettingsDialog
from tasks.update_task import VersionCheckTask, ReleaseNotesTask
from tasks.load_task import OrganizerLoadTask, FileLoadTask
from tasks.organize_task import OrganizerProcessTask
from tasks.rename_task import RenameTask
from core.archive_utils import bg_load_image

class RenamerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.config = load_config()
        self.lang = self.config.get("lang", "ko")
        
        self.signals = WorkerSignals()
        self.signals.progress.connect(self.update_progress)
        self.signals.load_done.connect(self.on_renamer_loaded)
        self.signals.rename_done.connect(self.finish_process_rename)
        self.signals.org_load_done.connect(self.on_organizer_loaded)
        self.signals.org_process_done.connect(self.finish_process_org)
        self.signals.image_loaded.connect(self.render_image)
        self.signals.version_checked.connect(self.on_version_checked)
        self.signals.release_notes_loaded.connect(self.on_release_notes_loaded)
        
        self.is_processing = False
        self.active_task = None
        self.latest_version_found = None 
        self.latest_version_url = "https://github.com/dongkkase/ComicZIP_Optimizer/releases"
        
        self.all_checked_org = True
        self.all_checked_ren = True
        
        self.org_data = {}      
        self.archive_data = {}  
        self.current_archive_path = None
        self.seven_zip_path = get_resource_path('7za.exe')
        self.format_keys = ["none", "zip", "cbz", "cbr", "7z"]
        
        window_width = self.config.get("width", 1150)
        window_height = self.config.get("height", 800)
        self.setWindowTitle(f"ComicZIP Optimizer v{CURRENT_VERSION}")
        self.setMinimumSize(1100, 750) 
        self.resize(window_width, window_height)
        if self.config.get("is_maximized", False): self.showMaximized()
        
        icon_path = get_resource_path('app.ico')
        if os.path.exists(icon_path): self.setWindowIcon(QIcon(icon_path))
        
        from config import get_safe_thread_limits
        total_c, safe_c, _ = get_safe_thread_limits()
        self.i18n = {
            "ko": {
                "title": f"ComicZIP Optimizer v{CURRENT_VERSION}",
                "tab1": "압축 파일 구조 정리(평탄화)", "tab2": "내부 파일명 변경", "tab3": "릴리스 노트",
                "cover_preview": "📚 표지 미리보기", "inner_preview": "🖼️ 내부 파일 미리보기",
                "add_folder": "📂 폴더 추가", "add_file": "📄 파일 추가",
                "remove_sel": "🗑️ 선택 삭제", "clear_all": "🧹 전체 비우기",
                "toggle_all": "☑ 전체 선택/해제",
                "settings_btn": "⚙️ 환경 설정", "settings_title": "환경 설정",
                "lang_lbl": "🌐 언어 (Language) :", "format_lbl": "📦 변환 포맷 :",
                "play_sound": "작업 완료 알림음 재생", 
                "backup": "원본 백업 (bak 폴더 생성)",
                "flatten": "폴더 구조 평탄화 (하위 폴더 제거)",
                "flatten_desc": "압축 파일 내의 폴더를 모두 무시하고 이미지를 최상단으로 꺼냅니다.",
                "webp": "모든 이미지를 WebP로 일괄 변환",
                "webp_desc": "모든 이미지를 고효율 WebP 포맷으로 변환하여 확장자 통일성을 보장합니다.",
                "webp_quality": "WebP 품질 (Quality) :", "max_threads": "다중 스레드 (Threads) :",
                "threads_desc": f"⚠️ 수치가 높을수록 변환 속도가 빨라지지만 PC가 느려질 수 있습니다.\n시스템 안정을 위해 전체 {total_c}코어 중 여유분을 남긴 안전 수치({safe_c}코어)까지만 올릴 수 있습니다.",
                "btn_save": "저장", "btn_cancel": "취소", "btn_close": "닫기",
                "btn_continue_tab2": "🚀 내부 파일명 변경 (Tab 2) 이어서 하기",
                "log_title": "상세 작업 결과 로그",
                "pattern_lbl": "💡 파일명 패턴 :",
                "target_lbl": " 대상 압축파일 (ZIP, CBZ, CBR, 7Z 지원) ",
                "inner_lbl": " 내부 파일 리스트 (패턴 실시간 미리보기) ",
                "col_org_name": "작업 대상 및 구조", "col_org_path": "완료 저장 경로 (직접 수정 가능)", "col_org_count": "항목수", "col_org_size": "용량",
                "batch_default": "일괄 기본값", "batch_title": "일괄 책제목",
                "col_name": "파일명 (포맷 변경 반영)", "col_count": "항목 수", "col_size": "용량 (MB)",
                "col_old": "원본 파일명", "col_new": "변경될 파일명", "col_fsize": "크기",
                "drag_drop": "📂 폴더나 파일을 여기로 드래그 앤 드롭하세요",
                "run_btn": "🚀 최적화 실행", "cancel_btn": "🛑 작업 중단",
                "cancel_wait": "⏳ 중단 처리 중...", "status_wait": "대기 중...",
                "no_preview": "미리보기 없음", "no_image": "미리볼 수 없는 이미지입니다.",
                "total_files": "총 {count}개 리스트",
                "format_opts": ["변경없음", "zip", "cbz", "cbr", "7z"],
                "patterns": ["기본 숫자 패딩 (000, 001...)", "영문 도서 스타일 (Cover, Page_001...)",
                             "압축파일명 동기화 (파일명_000...)", "압축파일명 + 도서 (파일명_Cover...) - 추천", "사용자 정의 (직접입력_000...)"]
            },
            "en": {
                "title": f"ComicZIP Optimizer v{CURRENT_VERSION}",
                "tab1": "Archive Organizer", "tab2": "Inner Renamer", "tab3": "Release Notes",
                "cover_preview": "📚 Cover Preview", "inner_preview": "🖼️ Inner Preview",
                "add_folder": "📂 Add Folder", "add_file": "📄 Add File",
                "remove_sel": "🗑️ Remove Sel", "clear_all": "🧹 Clear All",
                "toggle_all": "☑ Toggle All",
                "settings_btn": "⚙️ Settings", "settings_title": "Preferences",
                "lang_lbl": "🌐 Language :", "format_lbl": "📦 Output Format :",
                "play_sound": "Play completion sound",  
                "backup": "Backup Original (bak folder)",
                "flatten": "Flatten Folders (Remove Sub-folders)",
                "flatten_desc": "Extracts all images to the root, ignoring folders.",
                "webp": "Convert all images to WebP",
                "webp_desc": "Converts all images strictly to WebP format.",
                "webp_quality": "WebP Quality :", "max_threads": "Multi-threads :",
                "threads_desc": f"⚠️ Higher values increase speed but consume more CPU.\nFor system stability, the maximum is capped at {safe_c} cores (Total: {total_c}).",
                "btn_save": "Save", "btn_cancel": "Cancel", "btn_close": "Close",
                "btn_continue_tab2": "🚀 Continue to Inner Renamer (Tab 2)",
                "log_title": "Detailed Job Log",
                "pattern_lbl": "💡 Naming Pattern :",
                "target_lbl": " Target Archives (ZIP, CBZ, CBR, 7Z) ",
                "inner_lbl": " Inner Files (Real-time Preview) ",
                "col_org_name": "Original Name & Structure", "col_org_path": "Output Save Path", "col_org_count": "Items", "col_org_size": "Size",
                "batch_default": "Batch Default", "batch_title": "Batch Title",
                "col_name": "File Name", "col_count": "Items", "col_size": "Size",
                "col_old": "Original Name", "col_new": "New Name", "col_fsize": "Size",
                "drag_drop": "📂 Drag and drop folders or files here",
                "run_btn": "🚀 Execute Process", "cancel_btn": "🛑 Cancel Process",
                "cancel_wait": "⏳ Cancelling...", "status_wait": "Waiting...",
                "no_preview": "No Preview", "no_image": "Cannot preview this image.",
                "total_files": "Total {count} items",
                "format_opts": ["No Change", "zip", "cbz", "cbr", "7z"],
                "patterns": ["Basic Number Padding (000, 001...)", "English Book Style (Cover, Page_001...)",
                             "Sync with Archive Name (File_000...)", "Archive + Book (File_Cover...) - Recommended", "Custom (Input_000...)"]
            }
        }

        self.archive_timer = QTimer()
        self.archive_timer.setSingleShot(True)
        self.archive_timer.timeout.connect(self._process_archive_select)

        self.inner_timer = QTimer()
        self.inner_timer.setSingleShot(True)
        self.inner_timer.timeout.connect(self._process_inner_select)

        self.setup_ui()
        self.apply_language()
        self.apply_dark_theme()
        
        self.setAcceptDrops(True)
        self.check_for_updates()
        threading.Thread(target=ReleaseNotesTask(self.signals).run, daemon=True).start()

    def update_progress(self, percent, msg):
        self.progress_bar.setValue(percent)
        self.lbl_status.setText(msg)

    def on_version_checked(self, latest_version):
        self.latest_version_found = latest_version
        self.update_version_button_ui()

    def on_release_notes_loaded(self, markdown):
        self.browser_release.setMarkdown(markdown)

    def finish_process_rename(self, stats, new_archive_data, was_cancelled):
        self.is_processing = False
        self.toggle_ui_elements(is_processing=False)

        self.btn_run.clicked.disconnect()
        self.btn_run.clicked.connect(self.start_process)
        self.btn_run.setObjectName("actionBtn") 
        self.btn_run.setText(self.i18n[self.lang]["run_btn"])
        self.btn_run.setEnabled(True)
        self.btn_run.setStyleSheet(self.styleSheet())
        
        for old_fp, new_fp in new_archive_data.items():
            if old_fp != new_fp:
                if old_fp in self.archive_data: del self.archive_data[old_fp]
                self.load_archive_info(new_fp)
                self.current_archive_path = new_fp 
            else:
                self.force_reload_archive(new_fp)
        self.refresh_archive_list()
        if getattr(self, 'current_archive_path', None) and self.current_archive_path in self.archive_data:
            for row in range(self.table_archives.rowCount()):
                if self.table_archives.item(row, 0).data(Qt.ItemDataRole.UserRole) == self.current_archive_path:
                    self.table_archives.selectRow(row)
                    break

        if was_cancelled:
            self.safe_finish_ui_reset()
            QMessageBox.warning(self, "Cancelled", "사용자에 의해 작업이 중단되었습니다." if self.lang == "ko" else "Process cancelled by user.")
        else:
            if self.config.get("play_sound", True): 
                play_complete_sound()
            self.progress_bar.hide()
            self.progress_bar.setValue(0)
            if self.lang == "ko": msg_str = f"작업 완료! (성공: {len(stats['success'])}건 / 스킵: {len(stats['skip'])}건 / 오류: {len(stats['error'])}건)"
            else: msg_str = f"Done! (Success: {len(stats['success'])} / Skip: {len(stats['skip'])} / Error: {len(stats['error'])})"
            self.lbl_status.setText(msg_str)
        
        log_dlg = LogDialog(self, stats, self.i18n[self.lang], show_continue_btn=False)
        log_dlg.setStyleSheet(self.styleSheet())
        log_dlg.exec()

    def finish_process_org(self, stats, new_fps, was_cancelled):
        self.is_processing = False
        self.toggle_ui_elements(is_processing=False)

        self.btn_run.clicked.disconnect()
        self.btn_run.clicked.connect(self.start_process)
        self.btn_run.setObjectName("actionBtn") 
        self.btn_run.setText(self.i18n[self.lang]["run_btn"])
        self.btn_run.setEnabled(True)
        self.btn_run.setStyleSheet(self.styleSheet())
        
        self.org_data.clear()
        self.refresh_org_list()
        
        self.progress_bar.hide()
        self.progress_bar.setValue(0)

        if was_cancelled:
            self.lbl_status.setText(self.i18n[self.lang]["status_wait"])
            QMessageBox.warning(self, "Cancelled", "사용자에 의해 작업이 중단되었습니다." if self.lang == "ko" else "Process cancelled by user.")
            log_dlg = LogDialog(self, stats, self.i18n[self.lang], show_continue_btn=False)
            log_dlg.setStyleSheet(self.styleSheet())
            log_dlg.exec()
        else:
            if self.config.get("play_sound", True): 
                play_complete_sound()
            if self.lang == "ko": msg_str = f"작업 완료! (성공: {len(stats['success'])}건 / 스킵: {len(stats['skip'])}건 / 오류: {len(stats['error'])}건)"
            else: msg_str = f"Done! (Success: {len(stats['success'])} / Skip: {len(stats['skip'])} / Error: {len(stats['error'])})"
            self.lbl_status.setText(msg_str)
            
            valid_fps = [fp for fp in new_fps if os.path.exists(fp)]
            show_cont = len(valid_fps) > 0
            
            log_dlg = LogDialog(self, stats, self.i18n[self.lang], show_continue_btn=show_cont)
            log_dlg.setStyleSheet(self.styleSheet())
            
            # 🌟 [버그 수정] PyQt6에서는 exec()가 숫자(int)를 반환하므로 int로 감싸서 비교해야 완벽히 작동합니다.
            from PyQt6.QtWidgets import QDialog
            if log_dlg.exec() == int(QDialog.DialogCode.Accepted):
                self.tabs.setCurrentIndex(1)
                self.process_paths(valid_fps)

    def check_for_updates(self):
        threading.Thread(target=VersionCheckTask(self.signals).run, daemon=True).start()

    def update_version_button_ui(self):
        if self.latest_version_found:
            update_msg = f"🎉 Update Available: v{CURRENT_VERSION} ➔ v{self.latest_version_found}" if self.lang == "en" else f"🎉 업데이트 가능: v{CURRENT_VERSION} ➔ v{self.latest_version_found}"
            self.btn_version.setText(update_msg)
            self.btn_version.setObjectName("versionBtnUpdate")
            self.btn_version.setStyleSheet(self.styleSheet()) 
            self.latest_version_url = f"https://github.com/dongkkase/ComicZIP_Optimizer/releases/download/v{self.latest_version_found}/ComicZIP_Optimizer.zip"
        else:
            latest_msg = f"✅ v{CURRENT_VERSION} (Latest)" if self.lang == "en" else f"✅ v{CURRENT_VERSION} (최신 버전)"
            self.btn_version.setText(latest_msg)
            self.btn_version.setObjectName("versionBtn")
            self.btn_version.setStyleSheet(self.styleSheet())
            self.latest_version_url = "https://github.com/dongkkase/ComicZIP_Optimizer/releases"

    def open_update_link(self):
        if getattr(self, 'latest_version_url', None):
            webbrowser.open(self.latest_version_url)

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)

        toolbar_layout = QHBoxLayout()
        self.btn_add_folder = QPushButton()
        self.btn_add_folder.setCursor(Qt.CursorShape.PointingHandCursor) 
        self.btn_add_folder.clicked.connect(self.add_folder)
        
        self.btn_add_file = QPushButton()
        self.btn_add_file.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_file.clicked.connect(self.add_file)
        
        self.btn_remove_sel = QPushButton()
        self.btn_remove_sel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_remove_sel.setObjectName("dangerBtn")
        self.btn_remove_sel.clicked.connect(self.remove_selected)
        
        self.btn_clear_all = QPushButton()
        self.btn_clear_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_all.setObjectName("dangerBtn")
        self.btn_clear_all.clicked.connect(self.clear_list)

        self.btn_toggle_all = QPushButton()
        self.btn_toggle_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_all.clicked.connect(self.toggle_all_checkboxes)

        toolbar_layout.addWidget(self.btn_add_folder)
        toolbar_layout.addWidget(self.btn_add_file)
        toolbar_layout.addWidget(self.btn_remove_sel)
        toolbar_layout.addWidget(self.btn_clear_all)
        toolbar_layout.addWidget(self.btn_toggle_all)
        toolbar_layout.addStretch()

        self.btn_version = QPushButton()
        self.btn_version.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_version.setObjectName("versionBtn")
        self.btn_version.clicked.connect(self.open_update_link)
        toolbar_layout.addWidget(self.btn_version)

        self.btn_settings = QPushButton()
        self.btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_settings.setObjectName("settingsBtn")
        self.btn_settings.clicked.connect(self.open_settings)
        toolbar_layout.addWidget(self.btn_settings)

        main_layout.addLayout(toolbar_layout)

        self.tabs = QTabWidget()
        self.tab1 = QWidget() 
        self.tab2 = QWidget() 
        self.tab3 = QWidget() 
        
        self.tabs.addTab(self.tab1, "")
        self.tabs.addTab(self.tab2, "")
        self.tabs.addTab(self.tab3, "")
        self.tabs.currentChanged.connect(self.on_tab_changed)
        main_layout.addWidget(self.tabs, 1)

        self.setup_tab1_organizer()
        self.setup_tab2_renamer()

        t3_layout = QVBoxLayout(self.tab3)
        self.browser_release = QTextBrowser()
        self.browser_release.setOpenExternalLinks(True)
        t3_layout.addWidget(self.browser_release)

        bottom_layout = QHBoxLayout()
        self.lbl_status = QLabel()
        self.lbl_status.setObjectName("statusLabel")
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(10)
        self.progress_bar.hide() 

        status_v_layout = QVBoxLayout()
        status_v_layout.addWidget(self.lbl_status)
        status_v_layout.addWidget(self.progress_bar)

        self.btn_run = QPushButton()
        self.btn_run.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_run.setObjectName("actionBtn")
        self.btn_run.setFixedHeight(45)
        self.btn_run.clicked.connect(self.start_process)

        bottom_layout.addLayout(status_v_layout)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.btn_run)
        main_layout.addLayout(bottom_layout)

    def setup_tab1_organizer(self):
        layout = QVBoxLayout(self.tab1)
        
        ctrl_layout = QHBoxLayout()
        self.btn_toggle_expand = QPushButton()
        self.btn_toggle_expand.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_expand.clicked.connect(self.toggle_org_expand)
        ctrl_layout.addWidget(self.btn_toggle_expand)
        
        self.btn_batch_default = QPushButton()
        self.btn_batch_default.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_batch_default.clicked.connect(self.batch_set_default)
        self.btn_batch_title = QPushButton()
        self.btn_batch_title.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_batch_title.clicked.connect(self.batch_set_title)
        
        ctrl_layout.addWidget(self.btn_batch_default)
        ctrl_layout.addWidget(self.btn_batch_title)
        ctrl_layout.addStretch()
        layout.addLayout(ctrl_layout)
        
        self.tree_org = OrgTreeWidget()
        self.tree_org.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree_org.setHeaderLabels(["", "", "", ""])
        self.tree_org.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree_org.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch) 
        self.tree_org.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.tree_org.setColumnWidth(2, 70)
        self.tree_org.header().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.tree_org.setColumnWidth(3, 80)
        
        self.tree_org.itemChanged.connect(self.on_org_item_changed)
        self.tree_org.delete_pressed.connect(self.remove_highlighted)
        
        self.lbl_org_count = QLabel()
        self.lbl_org_count.setObjectName("infoLabel")
        
        layout.addWidget(self.tree_org, 1)
        layout.addWidget(self.lbl_org_count, alignment=Qt.AlignmentFlag.AlignCenter)

    def toggle_org_expand(self):
        if self.tree_org.topLevelItemCount() == 0: return
        is_currently_expanded = self.tree_org.topLevelItem(0).isExpanded()
        self.is_org_expanded = not is_currently_expanded
        for i in range(self.tree_org.topLevelItemCount()):
            self.tree_org.topLevelItem(i).setExpanded(self.is_org_expanded)

    def update_out_path(self, fp, text):
        if fp in self.org_data:
            self.org_data[fp]['out_path'] = text

    def set_single_path(self, fp, path):
        if fp in self.org_data and 'le_path' in self.org_data[fp]:
            self.org_data[fp]['le_path'].setText(path)

    def batch_set_default(self):
        for fp, data in self.org_data.items():
            if data.get('checked', False) and 'le_path' in data:
                data['le_path'].setText(os.path.dirname(fp))

    def batch_set_title(self):
        for fp, data in self.org_data.items():
            if data.get('checked', False) and 'le_path' in data:
                if data['clean_title'] == "제목없음":
                    data['le_path'].setText(os.path.join(os.path.dirname(fp), "제목없음_수정필요"))
                else:
                    data['le_path'].setText(os.path.join(os.path.dirname(fp), data['clean_title']))

    def setup_tab2_renamer(self):
        layout = QHBoxLayout(self.tab2)
        left_frame = QFrame()
        left_layout = QVBoxLayout(left_frame)
        left_frame.setFixedWidth(280) 
        left_frame.setObjectName("panelFrame")

        self.lbl_cover_title = QLabel()
        self.lbl_cover_title.setObjectName("titleLabel")
        self.lbl_cover_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_cover_img = QLabel()
        self.lbl_cover_img.setObjectName("imageLabel")
        self.lbl_cover_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_cover_img.setMinimumHeight(250)
        self.lbl_cover_img.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.lbl_inner_title = QLabel()
        self.lbl_inner_title.setObjectName("titleLabel")
        self.lbl_inner_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_inner_img = QLabel()
        self.lbl_inner_img.setObjectName("imageLabel")
        self.lbl_inner_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_inner_img.setMinimumHeight(250)
        self.lbl_inner_img.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setObjectName("divider")

        left_layout.addWidget(self.lbl_cover_title)
        left_layout.addWidget(self.lbl_cover_img, alignment=Qt.AlignmentFlag.AlignCenter)
        left_layout.addSpacing(5)
        left_layout.addWidget(divider)
        left_layout.addSpacing(5)
        left_layout.addWidget(self.lbl_inner_title)
        left_layout.addWidget(self.lbl_inner_img, alignment=Qt.AlignmentFlag.AlignCenter)
        left_layout.addStretch()

        right_frame = QFrame()
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(0,0,0,0)
        
        options_frame = QFrame()
        options_frame.setObjectName("optionsFrame")
        options_layout = QHBoxLayout(options_frame)
        self.lbl_pattern = QLabel()
        self.lbl_pattern.setObjectName("boldLabel")
        self.cb_pattern = QComboBox()
        self.cb_pattern.setCursor(Qt.CursorShape.PointingHandCursor) 
        self.cb_pattern.currentTextChanged.connect(self.on_pattern_change)
        self.entry_custom = QLineEdit()
        self.entry_custom.setEnabled(False)
        self.entry_custom.textChanged.connect(self.update_inner_preview_list)
        
        options_layout.addWidget(self.lbl_pattern)
        options_layout.addWidget(self.cb_pattern, 1)
        options_layout.addWidget(self.entry_custom)
        right_layout.addWidget(options_frame)

        self.lbl_target = QLabel()
        self.lbl_target.setObjectName("boldLabel")
        right_layout.addWidget(self.lbl_target)

        self.table_archives = ArchiveTableWidget(0, 3)
        self.table_archives.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_archives.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_archives.verticalHeader().setVisible(False) 
        
        self.table_archives.itemSelectionChanged.connect(self.on_ren_archive_select)
        self.table_archives.itemChanged.connect(self.on_ren_table_item_changed)
        self.table_archives.delete_pressed.connect(self.remove_highlighted)
        
        header_arch = self.table_archives.horizontalHeader()
        header_arch.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header_arch.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table_archives.setColumnWidth(1, 90)
        header_arch.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table_archives.setColumnWidth(2, 90)
        
        self.table_archives.setMinimumHeight(150)
        right_layout.addWidget(self.table_archives, 1) 

        self.lbl_total_count = QLabel()
        self.lbl_total_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_total_count.setObjectName("infoLabel")
        right_layout.addWidget(self.lbl_total_count)

        self.lbl_inner = QLabel()
        self.lbl_inner.setObjectName("boldLabel")
        right_layout.addWidget(self.lbl_inner)

        self.table_inner = QTableWidget(0, 3)
        self.table_inner.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_inner.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_inner.verticalHeader().setVisible(False)
        
        header_inner = self.table_inner.horizontalHeader()
        header_inner.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header_inner.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header_inner.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table_inner.setColumnWidth(2, 90)
        
        self.table_inner.setMinimumHeight(150)
        self.table_inner.itemSelectionChanged.connect(self.on_inner_select)
        right_layout.addWidget(self.table_inner, 1)

        layout.addWidget(left_frame)
        layout.addWidget(right_frame, 1)

    def apply_dark_theme(self):
        style = """
        QMainWindow, QDialog { background-color: #1e1e1e; }
        QFrame#panelFrame { background-color: #2b2b2b; border-radius: 10px; }
        QFrame#optionsFrame { background-color: #2b2b2b; border-radius: 8px; }
        QFrame#divider { background-color: #444444; }
        QLabel { color: #ffffff; font-family: '맑은 고딕', 'Segoe UI Emoji'; }
        QLabel#titleLabel { font-size: 14px; font-weight: bold; margin-bottom: 5px; }
        QLabel#boldLabel { font-size: 12px; font-weight: bold; margin-top: 5px; }
        QLabel#langLabel { font-size: 12px; font-weight: bold; }
        QLabel#statusLabel { color: #3498DB; font-weight: bold; font-size: 12px; }
        QLabel#infoLabel { color: #aaaaaa; font-size: 11px; }
        QLabel#imageLabel { background-color: #1a1a1a; border-radius: 8px; }
        
        QTabWidget::pane { border: 1px solid #444; border-radius: 5px; top: -1px; background: #1e1e1e; }
        QTabBar::tab { background: #2b2b2b; color: #888; border: 1px solid #444; padding: 10px 20px; margin-right: 2px; border-top-left-radius: 5px; border-top-right-radius: 5px; font-weight: bold; }
        QTabBar::tab:selected { background: #3a7ebf; color: #fff; }
        QTabBar::tab:hover:!selected { background: #3a3a3a; color: #fff; }

        QProgressBar { background-color: #3a3a3a; border: none; border-radius: 5px; }
        QProgressBar::chunk { background-color: #3498DB; border-radius: 5px; }
        
        QPushButton { background-color: #3a3a3a; color: white; border-radius: 6px; padding: 8px 12px; font-family: '맑은 고딕', 'Segoe UI Emoji'; font-weight: bold; }
        QPushButton:hover { background-color: #4a4a4a; }
        
        QPushButton#versionBtn { background-color: #2b2b2b; color: #cccccc; border: 1px solid #555; }
        QPushButton#versionBtn:hover { background-color: #3a3a3a; color: #ffffff; border: 1px solid #777; }
        QPushButton#versionBtnUpdate { background-color: #27AE60; color: #ffffff; font-weight: bold; border: 1px solid #2ECC71; }
        QPushButton#versionBtnUpdate:hover { background-color: #2ECC71; border: 1px solid #27AE60; }
        
        QPushButton#settingsBtn { background-color: #2b2b2b; border: 1px solid #555; }
        QPushButton#settingsBtn:hover { background-color: #3a3a3a; }
        
        QPushButton#dangerBtn:enabled { background-color: #D32F2F; color: #FFFFFF; border: none; }
        QPushButton#dangerBtn:hover:enabled { background-color: #B71C1C; }
        
        QPushButton#actionBtn { background-color: #0078D7; font-size: 14px; padding: 10px 20px; border: none; }
        QPushButton#actionBtn:hover { background-color: #005A9E; }
        QPushButton#actionBtnCancel { background-color: #E74C3C; font-size: 14px; padding: 10px 20px; border: none; }
        QPushButton#actionBtnCancel:hover { background-color: #C0392B; }
        
        QPushButton:disabled { background-color: #555555; color: #888888; border: 1px solid #444; }
        
        QTableWidget, QTreeWidget, QTextBrowser { background-color: #2b2b2b; color: white; border: 1px solid #444; border-radius: 8px; gridline-color: #3a3a3a; outline: none; }
        QHeaderView::section { background-color: #1f1f1f; color: white; padding: 5px; border: none; font-weight: bold; }
        QTableWidget::item:selected, QTreeWidget::item:selected { background-color: #3a7ebf; }
        QTableWidget::indicator, QTreeWidget::indicator { width: 18px; height: 18px; }
        
        QSlider::groove:horizontal { border-radius: 4px; height: 8px; background: #3a3a3a; }
        QSlider::handle:horizontal { background: #3498DB; width: 16px; height: 16px; margin: -4px 0; border-radius: 8px; }
        QSlider::handle:horizontal:hover { background: #5DADE2; }
        
        QComboBox, QLineEdit { background-color: #3a3a3a; color: white; border: 1px solid #555; border-radius: 4px; padding: 4px; }
        """
        self.setStyleSheet(style)

    def apply_language(self):
        t = self.i18n[self.lang]
        self.setWindowTitle(t["title"])
        self.tabs.setTabText(0, t["tab1"])
        self.tabs.setTabText(1, t["tab2"])
        self.tabs.setTabText(2, t["tab3"])
        
        self.lbl_cover_title.setText(t["cover_preview"])
        self.lbl_inner_title.setText(t["inner_preview"])
        self.btn_add_folder.setText(t["add_folder"])
        self.btn_add_file.setText(t["add_file"])
        self.btn_remove_sel.setText(t["remove_sel"])
        self.btn_clear_all.setText(t["clear_all"])
        self.btn_toggle_all.setText(t["toggle_all"])
        self.btn_settings.setText(t["settings_btn"]) 
        self.lbl_pattern.setText(t["pattern_lbl"])

        self.btn_toggle_expand.setText("↕ 전체 펼치기 / 접기" if self.lang == "ko" else "↕ Expand / Collapse All")
        self.btn_batch_default.setText(t["batch_default"])
        self.btn_batch_title.setText(t["batch_title"])
        
        self.cb_pattern.blockSignals(True)
        self.cb_pattern.clear()
        self.cb_pattern.addItems(t["patterns"])
        self.cb_pattern.blockSignals(False)
        self.cb_pattern.setCurrentIndex(0)
        
        self.lbl_target.setText(t["target_lbl"])
        self.lbl_inner.setText(t["inner_lbl"])
        
        self.tree_org.setHeaderLabels([t["col_org_name"], t["col_org_path"], t["col_org_count"], t["col_org_size"]])
        self.table_archives.setHorizontalHeaderLabels([t["col_name"], t["col_count"], t["col_size"]])
        self.table_inner.setHorizontalHeaderLabels([t["col_old"], t["col_new"], t["col_fsize"]])
        
        if self.btn_run.objectName() == "actionBtn": self.btn_run.setText(t["run_btn"])
        else: self.btn_run.setText(t["cancel_btn"])
        
        if not self.lbl_status.text() or self.lbl_status.text() in [self.i18n["ko"]["status_wait"], self.i18n["en"]["status_wait"]]:
            self.lbl_status.setText(t["status_wait"])
            
        self.refresh_archive_list()
        self.refresh_org_list()
        self.update_version_button_ui()
        
        if not getattr(self, 'current_archive_path', None):
            self.render_image("cover", None)
            self.render_image("inner", None)

    def on_tab_changed(self, index):
        enabled = (index != 2) and not self.is_processing
        self.btn_add_folder.setEnabled(enabled)
        self.btn_add_file.setEnabled(enabled)
        self.btn_remove_sel.setEnabled(enabled)
        self.btn_clear_all.setEnabled(enabled)
        self.btn_toggle_all.setEnabled(enabled)
        self.btn_run.setEnabled(enabled)

    def toggle_ui_elements(self, is_processing):
        enabled = not is_processing
        self.btn_add_folder.setEnabled(enabled)
        self.btn_add_file.setEnabled(enabled)
        self.btn_remove_sel.setEnabled(enabled)
        self.btn_clear_all.setEnabled(enabled)
        self.btn_toggle_all.setEnabled(enabled)
        
        if hasattr(self, 'btn_toggle_expand'):
            self.btn_toggle_expand.setEnabled(enabled)
            self.btn_batch_default.setEnabled(enabled)
            self.btn_batch_title.setEnabled(enabled)
            
        self.btn_settings.setEnabled(enabled)
        self.btn_version.setEnabled(enabled) 
        self.cb_pattern.setEnabled(enabled)
        self.table_archives.setEnabled(enabled)
        self.table_inner.setEnabled(enabled)
        self.tree_org.setEnabled(enabled)
        self.setAcceptDrops(enabled) 

        if is_processing:
            self.entry_custom.setEnabled(False)
        else:
            self.on_pattern_change(self.cb_pattern.currentText())

    def open_settings(self):
        dlg = SettingsDialog(self, self.config, self.format_keys, self.i18n)
        dlg.setStyleSheet(self.styleSheet()) 
        # 🌟 [버그 수정] PyQt6 환경에 맞게 결과값을 int(숫자)로 변환하여 정확히 인식하도록 수정
        from PyQt6.QtWidgets import QDialog
        if dlg.exec() == int(QDialog.DialogCode.Accepted):
            new_data = dlg.get_data()
            self.config.update(new_data)
            self.lang = self.config["lang"]
            save_config(self.config)
            self.apply_language()
            self.update_inner_preview_list()

    def dragEnterEvent(self, event):
        if self.tabs.currentIndex() == 2: event.ignore(); return
        if event.mimeData().hasUrls(): event.acceptProposedAction()
        else: event.ignore()

    def dropEvent(self, event):
        event.acceptProposedAction()
        if self.is_processing: return
        files = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if files:
            QTimer.singleShot(10, lambda: self.process_paths(files))

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Directory", options=QFileDialog.Option.DontUseNativeDialog)
        if folder: self.process_paths([folder])

    def add_file(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select Archives", "", "Archive files (*.zip *.cbz *.cbr *.7z *.rar)", options=QFileDialog.Option.DontUseNativeDialog)
        if files: self.process_paths(files)

    def process_paths(self, paths):
        if self.is_processing: return
        self.is_processing = True
        self.toggle_ui_elements(is_processing=True)
        self.progress_bar.show()
        self.progress_bar.setValue(0)
        self.lbl_status.setText("목록을 불러오는 중입니다..." if self.lang == "ko" else "Loading files...")
        
        if self.tabs.currentIndex() == 0:
            task = OrganizerLoadTask(paths, self.seven_zip_path, self.lang, self.signals)
        else:
            task = FileLoadTask(paths, self.seven_zip_path, self.lang, self.signals)
            
        self.active_task = task
        threading.Thread(target=task.run, daemon=True).start()

    def on_organizer_loaded(self, new_data, skipped_files):
        for fp, data in new_data.items():
            if fp not in self.org_data:
                self.org_data[fp] = data
                
        self.is_org_expanded = True
        self.refresh_org_list()
        self.safe_finish_ui_reset()
        
        if skipped_files:
            msg = "다음 파일은 내부에 폴더 구조가 없어 1차 정리가 완료된 것으로 판단, 목록에서 자동으로 제외되었습니다:\n\n" if self.lang == "ko" else "The following files have no inner folders and were skipped:\n\n"
            msg += "\n".join(skipped_files[:5])
            if len(skipped_files) > 5:
                msg += f"\n...외 {len(skipped_files)-5}개" if self.lang == "ko" else f"\n...and {len(skipped_files)-5} more"
            
            QMessageBox.information(self, "알림" if self.lang == "ko" else "Information", msg)

    def on_renamer_loaded(self, new_data, nested_files, unsupported_files):
        added = False
        for fp, data in new_data.items():
            if fp not in self.archive_data:
                self.archive_data[fp] = data
                added = True

        self.refresh_archive_list()
        if added and self.table_archives.rowCount() > 0:
            self.table_archives.selectRow(self.table_archives.rowCount()-1)

        self.safe_finish_ui_reset()
        
        if unsupported_files:
            msg = "다음 파일은 지원하지 않는 형식이므로 제외되었습니다:\n" + "\n".join(unsupported_files[:5]) if self.lang == "ko" else "Unsupported files skipped:\n" + "\n".join(unsupported_files[:5])
            if len(unsupported_files) > 5: msg += f"\n...외 {len(unsupported_files)-5}개"
            QMessageBox.warning(self, "Warning", msg)
        if nested_files:
            msg = "다음 파일은 내부에 압축파일이 포함되어 제외되었습니다:\n" + "\n".join(nested_files[:5]) if self.lang == "ko" else "Skipped due to nested archives:\n" + "\n".join(nested_files[:5])
            if len(nested_files) > 5: msg += f"\n...외 {len(nested_files)-5}개"
            QMessageBox.warning(self, "Warning", msg)

    def safe_finish_ui_reset(self):
        self.is_processing = False
        self.toggle_ui_elements(is_processing=False)
        self.lbl_status.setText(self.i18n[self.lang]["status_wait"])
        QTimer.singleShot(300, self._actual_hide)

    def _actual_hide(self):
        self.progress_bar.hide()
        self.progress_bar.setValue(0)

    def on_org_item_changed(self, item, col):
        if col == 0 and item.parent() is None:
            fp = item.data(0, Qt.ItemDataRole.UserRole)
            if fp in self.org_data:
                self.org_data[fp]['checked'] = (item.checkState(0) == Qt.CheckState.Checked)

    def refresh_org_list(self):
        self.tree_org.setUpdatesEnabled(False)
        self.tree_org.blockSignals(True)
        self.tree_org.clear()
        
        target_ext = f".{self.config.get('target_format', 'zip')}" if self.config.get("target_format", "none") != "none" else ""
        
        items_to_add = []
        widgets_to_set = []
        
        for fp, data in self.org_data.items():
            root_item = QTreeWidgetItem()
            root_item.setData(0, Qt.ItemDataRole.UserRole, fp)
            root_item.setFlags(root_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            root_item.setCheckState(0, Qt.CheckState.Checked if data.get('checked', True) else Qt.CheckState.Unchecked)
            root_item.setSizeHint(0, QSize(0, 36)) 
            
            root_item.setText(0, f"📦 {data['name']}")
            vol_count_text = f"{len(data['volumes'])} Items" if self.lang == 'en' else f"{len(data['volumes'])} 권/화"
            root_item.setText(2, vol_count_text) 
            root_item.setText(3, f"{data['size_mb']:.1f} MB") 
            
            path_widget = QWidget()
            path_layout = QHBoxLayout(path_widget)
            path_layout.setContentsMargins(5, 2, 5, 2)
            path_layout.setSpacing(5)
            
            le_path = QLineEdit()
            default_path = os.path.dirname(fp)
            
            if data['clean_title'] == "제목없음":
                title_path = os.path.join(default_path, "제목없음_수정필요")
            else:
                title_path = os.path.join(default_path, data['clean_title'])
            
            if 'out_path' not in data:
                data['out_path'] = default_path
            le_path.setText(data['out_path'])
            
            le_path.textChanged.connect(lambda text, key=fp: self.update_out_path(key, text))
            data['le_path'] = le_path 
            
            btn_def = QPushButton("기본값" if self.lang == "ko" else "Default")
            btn_def.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_def.clicked.connect(lambda _, key=fp, p=default_path: self.set_single_path(key, p))
            
            btn_tit = QPushButton("책제목" if self.lang == "ko" else "Title")
            btn_tit.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_tit.clicked.connect(lambda _, key=fp, p=title_path: self.set_single_path(key, p))
            
            btn_style = "QPushButton { padding: 4px 8px; font-size: 11px; border-radius: 4px; background-color: #4a4a4a; } QPushButton:hover { background-color: #5a5a5a; }"
            btn_def.setStyleSheet(btn_style)
            btn_tit.setStyleSheet(btn_style)
            le_path.setStyleSheet("padding: 4px; font-size: 11px;")
            
            path_layout.addWidget(le_path, 1)
            path_layout.addWidget(btn_def)
            path_layout.addWidget(btn_tit)
            
            for vol in data['volumes']:
                child = QTreeWidgetItem(root_item)
                icon_txt = "📦" if vol.get('type') == 'archive' else "📁"
                
                final_ext = target_ext
                if not final_ext:
                    final_ext = Path(vol.get('inner_path', '')).suffix if vol.get('type') == 'archive' else ".zip"
                if not final_ext: final_ext = ".zip"
                
                child.setText(0, f"  ↳ {icon_txt} {vol['new_name']}{final_ext}")
                child.setForeground(0, QColor("#aaaaaa"))
                
            items_to_add.append(root_item)
            widgets_to_set.append((root_item, path_widget)) 
            
        self.tree_org.addTopLevelItems(items_to_add)
        
        for item, widget in widgets_to_set:
            self.tree_org.setItemWidget(item, 1, widget)
        
        current_expand_state = getattr(self, 'is_org_expanded', True)
        for i in range(self.tree_org.topLevelItemCount()):
            self.tree_org.topLevelItem(i).setExpanded(current_expand_state)
            
        self.tree_org.blockSignals(False)
        self.tree_org.setUpdatesEnabled(True)
        self.lbl_org_count.setText(self.i18n[self.lang]["total_files"].format(count=len(self.org_data)))

    def on_ren_table_item_changed(self, item):
        if item.column() == 0:
            fp = item.data(Qt.ItemDataRole.UserRole)
            if fp in self.archive_data:
                self.archive_data[fp]['checked'] = (item.checkState() == Qt.CheckState.Checked)

    def refresh_archive_list(self):
        self.table_archives.setUpdatesEnabled(False)
        self.table_archives.blockSignals(True)
        self.table_archives.clearContents()
        self.table_archives.setRowCount(0)
        
        fmt_key = self.config.get("target_format", "none")
        webp_on = self.config.get("webp_conversion", False)
        
        for row, (fp, data) in enumerate(self.archive_data.items()):
            self.table_archives.insertRow(row)
            name = data['name']
            ext = data['ext'].lower().replace('.', '')
            
            badges = []
            if fmt_key != "none" and ext != fmt_key: badges.append(fmt_key.upper())
            if webp_on: badges.append("WEBP")
            if badges: name += f" 🔄 ({'+'.join(badges)})"
                
            chk_item = QTableWidgetItem(name)
            chk_item.setData(Qt.ItemDataRole.UserRole, fp) 
            chk_item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            chk_item.setCheckState(Qt.CheckState.Checked if data['checked'] else Qt.CheckState.Unchecked)
            
            c_item = QTableWidgetItem(str(len(data['entries'])))
            c_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            s_item = QTableWidgetItem(f"{data['size_mb']:.1f}")
            s_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            
            self.table_archives.setItem(row, 0, chk_item)
            self.table_archives.setItem(row, 1, c_item)
            self.table_archives.setItem(row, 2, s_item)
            
        self.table_archives.blockSignals(False)
        self.table_archives.setUpdatesEnabled(True)
        self.lbl_total_count.setText(self.i18n[self.lang]["total_files"].format(count=len(self.archive_data)))

    def update_inner_preview_list(self):
        if not getattr(self, 'current_archive_path', None) or self.current_archive_path not in self.archive_data: return
        self.table_inner.setUpdatesEnabled(False)
        self.table_inner.blockSignals(True)
        self.table_inner.clearContents()
        self.table_inner.setRowCount(0)
        
        entries = self.archive_data[self.current_archive_path]['entries'].copy()
        cover = next((e for e in entries if os.path.basename(e['filename']).lower().startswith('cover')), None)
        if cover: entries.remove(cover); entries.insert(0, cover)

        total = len(entries)
        stem = Path(self.current_archive_path).stem
        pat_idx = self.cb_pattern.currentIndex()
        cust_txt = self.entry_custom.text()
        flatten = self.config.get("flatten_folders", False)
        webp_on = self.config.get("webp_conversion", False)

        for idx, e in enumerate(entries):
            old = e['filename']
            ext = ".webp" if webp_on else (os.path.splitext(old)[1] or ".jpg")
            
            pad = 2 if total < 100 else (3 if total < 1000 else 4)
            
            if pat_idx == 1: new = f"Cover{ext}" if idx==0 else f"Page_{idx:0{pad}d}{ext}"
            elif pat_idx == 2: new = f"{stem.replace(' ','_')}_{idx:0{pad}d}{ext}"
            elif pat_idx == 3: new = f"{stem.replace(' ','_')}_Cover{ext}" if idx==0 else f"{stem.replace(' ','_')}_Page_{idx:0{pad}d}{ext}"
            elif pat_idx == 4: new = f"{cust_txt.strip() or 'Custom'}_{idx:0{pad}d}{ext}"
            else: new = f"{idx:0{pad}d}{ext}"

            dir_name = os.path.dirname(old)
            if not flatten and dir_name: new = os.path.join(dir_name, new).replace('\\', '/')

            self.table_inner.insertRow(idx)
            i1 = QTableWidgetItem(os.path.basename(old) if flatten else old)
            i1.setData(Qt.ItemDataRole.UserRole, e['original_name']) 
            i2 = QTableWidgetItem(new)
            i3 = QTableWidgetItem(f"{e['file_size']/1024:.1f} KB")
            i3.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table_inner.setItem(idx, 0, i1); self.table_inner.setItem(idx, 1, i2); self.table_inner.setItem(idx, 2, i3)
            
        self.table_inner.blockSignals(False)
        self.table_inner.setUpdatesEnabled(True)

    def on_ren_archive_select(self): self.archive_timer.start(150) 
    def on_inner_select(self): self.inner_timer.start(150)

    def _process_archive_select(self):
        selected = self.table_archives.selectedItems()
        if not selected: return
        fp = self.table_archives.item(selected[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        if not fp or fp not in self.archive_data: return 
        
        self.current_archive_path = fp
        self.update_inner_preview_list()
        if self.table_inner.rowCount() > 0: self.table_inner.selectRow(0)

        entries = self.archive_data[fp]['entries'].copy()
        img_exts = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'}
        cover = next((e for e in entries if os.path.basename(e['filename']).lower().startswith('cover') and Path(e['filename']).suffix.lower() in img_exts), None)
        if cover: entries.remove(cover); entries.insert(0, cover)
        target = next((e for e in entries if Path(e['filename']).suffix.lower() in img_exts), None)
        
        if target: threading.Thread(target=bg_load_image, args=(fp, target['original_name'], self.archive_data[fp]['ext'], "cover", self.seven_zip_path, self.signals), daemon=True).start()
        else: self.render_image("cover", None)

    def _process_inner_select(self):
        selected = self.table_inner.selectedItems()
        if not selected or not getattr(self, 'current_archive_path', None): return
        orig_fp = self.table_inner.item(selected[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        ext = self.archive_data[self.current_archive_path]['ext']
        threading.Thread(target=bg_load_image, args=(self.current_archive_path, orig_fp, ext, "inner", self.seven_zip_path, self.signals), daemon=True).start()

    def render_image(self, target_id, img_data):
        label_widget = self.lbl_cover_img if target_id == "cover" else self.lbl_inner_img
        
        cw = max(200, label_widget.width() - 10)
        ch = max(250, label_widget.height() - 10)
        
        if not img_data:
            p = get_resource_path("previewframe.png")
            if os.path.exists(p):
                try:
                    with open(p, "rb") as f: img_data = f.read()
                except: pass
        if not img_data:
            label_widget.setText(self.i18n[self.lang]["no_preview"] if target_id == "cover" else self.i18n[self.lang]["no_image"])
            return

        try:
            image = QImage.fromData(img_data)
            if image.isNull(): raise Exception()
            pixmap = QPixmap.fromImage(image).scaled(QSize(cw, ch), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            target = QPixmap(pixmap.size()); target.fill(Qt.GlobalColor.transparent)
            painter = QPainter(target); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            path = QPainterPath(); path.addRoundedRect(0, 0, target.width(), target.height(), 10, 10)
            painter.setClipPath(path); painter.drawPixmap(0, 0, pixmap); painter.end()
            label_widget.setPixmap(target)
        except:
            label_widget.setText(self.i18n[self.lang]["no_image"])

    def toggle_all_checkboxes(self):
        if self.tabs.currentIndex() == 0:
            self.all_checked_org = not self.all_checked_org
            for fp in self.org_data: self.org_data[fp]['checked'] = self.all_checked_org
            self.refresh_org_list()
        elif self.tabs.currentIndex() == 1:
            self.all_checked_ren = not self.all_checked_ren
            for fp in self.archive_data: self.archive_data[fp]['checked'] = self.all_checked_ren
            self.refresh_archive_list()

    def remove_selected(self):
        if self.tabs.currentIndex() == 0:
            fps_to_remove = [fp for fp, data in self.org_data.items() if data.get('checked', False)]
            if not fps_to_remove: return
            for fp in fps_to_remove:
                if fp in self.org_data: del self.org_data[fp]
            self.refresh_org_list()
            
        elif self.tabs.currentIndex() == 1:
            self.archive_timer.stop()
            self.inner_timer.stop()
            fps_to_remove = [fp for fp, data in self.archive_data.items() if data.get('checked', False)]
            if not fps_to_remove: return
            for fp in fps_to_remove:
                if fp in self.archive_data: del self.archive_data[fp]
            self.refresh_archive_list()
            if self.table_archives.rowCount() > 0: self.table_archives.selectRow(0) 
            else: 
                self.table_inner.setRowCount(0); self.render_image("cover", None); self.render_image("inner", None)
                self.current_archive_path = None

    def remove_highlighted(self):
        if self.tabs.currentIndex() == 0:
            selected_items = self.tree_org.selectedItems()
            if not selected_items: return
            
            top_level_indices = []
            fps_to_remove = []
            for item in selected_items:
                parent = item.parent() if item.parent() else item
                idx = self.tree_org.indexOfTopLevelItem(parent)
                top_level_indices.append(idx)
                
                fp = parent.data(0, Qt.ItemDataRole.UserRole)
                if fp and fp not in fps_to_remove: 
                    fps_to_remove.append(fp)
                    
            if not fps_to_remove: return
            next_select_row = sorted(top_level_indices)[0]  
            
            for fp in fps_to_remove:
                if fp in self.org_data: del self.org_data[fp]
            self.refresh_org_list()
            
            total_rows = self.tree_org.topLevelItemCount()
            if total_rows > 0:
                row_to_select = min(next_select_row, total_rows - 1)
                self.tree_org.topLevelItem(row_to_select).setSelected(True)

        elif self.tabs.currentIndex() == 1:
            self.archive_timer.stop()
            self.inner_timer.stop()
            
            selected_items = self.table_archives.selectedItems()
            if not selected_items: return
            
            rows_to_remove = set([item.row() for item in selected_items])
            next_select_row = sorted(list(rows_to_remove))[0]
            
            fps_to_remove = []
            for row in rows_to_remove:
                item = self.table_archives.item(row, 0)
                if item:
                    fp = item.data(Qt.ItemDataRole.UserRole)
                    if fp: fps_to_remove.append(fp)
                    
            if not fps_to_remove: return
            for fp in fps_to_remove:
                if fp in self.archive_data: del self.archive_data[fp]
                    
            self.refresh_archive_list()
            
            total_rows = self.table_archives.rowCount()
            if total_rows > 0: 
                row_to_select = min(next_select_row, total_rows - 1)
                self.table_archives.selectRow(row_to_select) 
            else: 
                self.table_inner.setRowCount(0); self.render_image("cover", None); self.render_image("inner", None)
                self.current_archive_path = None

    def clear_list(self):
        if self.tabs.currentIndex() == 0:
            self.org_data.clear()
            self.refresh_org_list()
        elif self.tabs.currentIndex() == 1:
            self.archive_timer.stop()
            self.inner_timer.stop()
            self.archive_data.clear()
            self.refresh_archive_list()
            self.table_inner.setRowCount(0)
            self.render_image("cover", None); self.render_image("inner", None)
            self.current_archive_path = None

    def on_pattern_change(self, value):
        t = self.i18n[self.lang]["patterns"]
        if value == t[4]: self.entry_custom.setEnabled(True); self.entry_custom.setFocus()
        else: self.entry_custom.setEnabled(False)
        self.update_inner_preview_list()

    def start_process(self):
        if self.is_processing: return
        
        if self.tabs.currentIndex() == 0:
            targets = [fp for fp, d in self.org_data.items() if d.get('checked', False)]
            if not targets:
                QMessageBox.warning(self, "Warning", "체크(☑)된 작업 대상이 없습니다." if self.lang == "ko" else "No checked targets.")
                return
                
            self.archive_timer.stop()
            self.inner_timer.stop()
            self.archive_data.clear()
            self.refresh_archive_list()
            self.table_inner.setRowCount(0)
            self.render_image("cover", None)
            self.render_image("inner", None)
            self.current_archive_path = None
            
            self.is_processing = True
            self.toggle_ui_elements(is_processing=True)
            self.btn_run.clicked.disconnect()
            self.btn_run.clicked.connect(self.cancel_process)
            self.btn_run.setObjectName("actionBtnCancel")
            self.btn_run.setText(self.i18n[self.lang]["cancel_btn"])
            self.btn_run.setStyleSheet(self.styleSheet()) 
            self.progress_bar.show(); self.progress_bar.setValue(0)
            
            task = OrganizerProcessTask(targets, self.config, self.org_data, self.seven_zip_path, self.signals)
            self.active_task = task
            threading.Thread(target=task.run, daemon=True).start()
            
        elif self.tabs.currentIndex() == 1:
            targets = [fp for fp, d in self.archive_data.items() if d.get('checked', False)]
            if not targets:
                QMessageBox.warning(self, "Warning", "체크(☑)된 작업 대상이 없습니다." if self.lang == "ko" else "No checked targets.")
                return
                
            self.org_data.clear()
            self.refresh_org_list()
            
            self.is_processing = True
            self.toggle_ui_elements(is_processing=True)
            self.btn_run.clicked.disconnect()
            self.btn_run.clicked.connect(self.cancel_process)
            self.btn_run.setObjectName("actionBtnCancel")
            self.btn_run.setText(self.i18n[self.lang]["cancel_btn"])
            self.btn_run.setStyleSheet(self.styleSheet()) 
            self.progress_bar.show(); self.progress_bar.setValue(0)
            
            task = RenameTask(targets, self.config, self.archive_data, self.i18n, self.cb_pattern.currentText(), self.entry_custom.text(), self.seven_zip_path, self.signals)
            self.active_task = task
            threading.Thread(target=task.run, daemon=True).start()

    def cancel_process(self):
        self.btn_run.setText(self.i18n[self.lang]["cancel_wait"])
        self.btn_run.setEnabled(False)
        if hasattr(self, 'active_task') and self.active_task and hasattr(self.active_task, 'cancel'):
            self.active_task.cancel()

    def load_archive_info(self, filepath, batch_mode=False):
        try:
            size_mb = os.path.getsize(filepath) / (1024 * 1024)
            ext = Path(filepath).suffix.lower()
            if ext in ['.zip', '.cbz']:
                with zipfile.ZipFile(filepath, 'r') as zf:
                    entries = sorted([{
                        'original_name': info.filename,
                        'filename': info.filename.replace('\\', '/'),
                        'file_size': info.file_size
                    } for info in zf.infolist() if not info.is_dir()], key=lambda x: natural_keys(x['filename']))
            else:
                if not os.path.exists(self.seven_zip_path): return False
                task = FileLoadTask([], self.seven_zip_path, self.lang, self.signals)
                entries = sorted(task.get_7z_entries(filepath), key=lambda x: natural_keys(x['filename']))

            image_exts = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'}
            img_entries = [e for e in entries if Path(e['filename']).suffix.lower() in image_exts]
            
            if not img_entries:
                return False 

            nested_exts = {'.zip', '.cbz', '.cbr', '.7z', '.rar', '.alz', '.egg'}
            if any(Path(e['filename']).suffix.lower() in nested_exts for e in entries):
                if not batch_mode:
                    msg = f"[{os.path.basename(filepath)}]\n내부에 압축 파일이 포함되어 제외됩니다." if self.lang == "ko" else f"[{os.path.basename(filepath)}]\nContains nested archives. Skipped."
                    QMessageBox.warning(self, "Warning", msg)
                return "nested"

            self.archive_data[filepath] = {
                'checked': True,
                'entries': img_entries, 'size_mb': size_mb, 'name': os.path.basename(filepath), 'ext': ext
            }
            return True
        except: return False

    def force_reload_archive(self, filepath):
        if filepath in self.archive_data: del self.archive_data[filepath]
        self.load_archive_info(filepath)

    def closeEvent(self, event):
        self.config["width"] = self.normalGeometry().width()
        self.config["height"] = self.normalGeometry().height()
        self.config["is_maximized"] = self.isMaximized()
        save_config(self.config)
        event.accept()
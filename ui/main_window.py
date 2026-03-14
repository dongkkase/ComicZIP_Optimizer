import os
import threading
import webbrowser
from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, 
    QProgressBar, QFileDialog, QMessageBox, QTextBrowser, QTabWidget
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon

from config import load_config, save_config, get_resource_path, CURRENT_VERSION
from utils import play_complete_sound
from ui.signals import WorkerSignals
from ui.dialogs import LogDialog, SettingsDialog
from tasks.update_task import VersionCheckTask, ReleaseNotesTask
from tasks.load_task import OrganizerLoadTask, FileLoadTask
from tasks.organize_task import OrganizerProcessTask
from tasks.rename_task import RenameTask

# 🌟 각 탭을 모듈로 깔끔하게 불러옵니다!
from ui.tabs.tab1_organizer import Tab1Organizer
from ui.tabs.tab2_renamer import Tab2Renamer
from ui.tabs.tab3_metadata import Tab3Metadata

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
        self.signals.version_checked.connect(self.on_version_checked)
        self.signals.release_notes_loaded.connect(self.on_release_notes_loaded)
        
        # 🌟 [이미지 렌더링 라우팅] 백그라운드에서 이미지가 오면, 현재 켜져있는 탭으로 보내줍니다.
        self.signals.image_loaded.connect(self.route_image_loaded)
        
        self.is_processing = False
        self.active_task = None
        self.latest_version_found = None 
        self.latest_version_url = "https://github.com/dongkkase/ComicZIP_Optimizer/releases"
        
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
                "tab1": "압축 파일 구조 정리(평탄화)", "tab2": "내부 파일명 변경", 
                "tab3": "메타데이터 관리", "tab4": "릴리스 노트",
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
                "tab1": "Archive Organizer", "tab2": "Inner Renamer", 
                "tab3": "Metadata Management", "tab4": "Release Notes",
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

        self.setup_ui()
        self.apply_language()
        self.apply_dark_theme()
        
        self.setAcceptDrops(True)
        self.check_for_updates()
        threading.Thread(target=ReleaseNotesTask(self.signals).run, daemon=True).start()

    def route_image_loaded(self, target_id, img_data):
        current_tab = self.tabs.currentWidget()
        if hasattr(current_tab, 'render_image'):
            current_tab.render_image(target_id, img_data)

    def check_for_updates(self):
        threading.Thread(target=VersionCheckTask(self.signals).run, daemon=True).start()

    def update_progress(self, percent, msg):
        self.progress_bar.setValue(percent)
        self.lbl_status.setText(msg)

    def on_version_checked(self, latest_version):
        self.latest_version_found = latest_version
        self.update_version_button_ui()

    def on_release_notes_loaded(self, markdown):
        self.browser_release.setMarkdown(markdown)

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
        self.tab1 = Tab1Organizer(self)
        self.tab2 = Tab2Renamer(self)
        self.tab3 = Tab3Metadata(self)
        self.tab4 = QWidget() 
        
        self.tabs.addTab(self.tab1, "")
        self.tabs.addTab(self.tab2, "")
        self.tabs.addTab(self.tab3, "")
        self.tabs.addTab(self.tab4, "")
        self.tabs.currentChanged.connect(self.on_tab_changed)
        main_layout.addWidget(self.tabs, 1)

        t4_layout = QVBoxLayout(self.tab4)
        self.browser_release = QTextBrowser()
        self.browser_release.setOpenExternalLinks(True)
        t4_layout.addWidget(self.browser_release)

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
        
        QComboBox, QLineEdit, QTextEdit { background-color: #3a3a3a; color: white; border: 1px solid #555; border-radius: 4px; padding: 4px; }
        """
        self.setStyleSheet(style)

    def apply_language(self):
        t = self.i18n[self.lang]
        self.setWindowTitle(t["title"])
        self.tabs.setTabText(0, t["tab1"])
        self.tabs.setTabText(1, t["tab2"])
        self.tabs.setTabText(2, t["tab3"])
        self.tabs.setTabText(3, t["tab4"])
        
        self.btn_add_folder.setText(t["add_folder"])
        self.btn_add_file.setText(t["add_file"])
        self.btn_remove_sel.setText(t["remove_sel"])
        self.btn_clear_all.setText(t["clear_all"])
        self.btn_toggle_all.setText(t["toggle_all"])
        self.btn_settings.setText(t["settings_btn"]) 
        
        # 🌟 탭 파일 안의 글자들도 업데이트하라고 각 객체에 위임합니다!
        if hasattr(self.tab1, 'retranslate_ui'): self.tab1.retranslate_ui(t, self.lang)
        if hasattr(self.tab2, 'retranslate_ui'): self.tab2.retranslate_ui(t, self.lang)
        if hasattr(self.tab3, 'retranslate_ui'): self.tab3.retranslate_ui(t, self.lang)
        
        if self.btn_run.objectName() == "actionBtn": self.btn_run.setText(t["run_btn"])
        else: self.btn_run.setText(t["cancel_btn"])
        
        if not self.lbl_status.text() or self.lbl_status.text() in [self.i18n["ko"]["status_wait"], self.i18n["en"]["status_wait"]]:
            self.lbl_status.setText(t["status_wait"])
            
        self.update_version_button_ui()

    def on_tab_changed(self, index):
        enabled = (index in [0, 1, 2]) and not self.is_processing
        self.btn_add_folder.setEnabled(enabled)
        self.btn_add_file.setEnabled(enabled)
        self.btn_remove_sel.setEnabled(enabled)
        self.btn_clear_all.setEnabled(enabled)
        self.btn_toggle_all.setEnabled(enabled)
        self.btn_run.setEnabled(index in [0, 1] and not self.is_processing)

    def toggle_ui_elements(self, is_processing):
        enabled = not is_processing
        current_tab = self.tabs.currentIndex()
        top_btn_enabled = enabled if current_tab in [0, 1, 2] else False
        
        self.btn_add_folder.setEnabled(top_btn_enabled)
        self.btn_add_file.setEnabled(top_btn_enabled)
        self.btn_remove_sel.setEnabled(top_btn_enabled)
        self.btn_clear_all.setEnabled(top_btn_enabled)
        self.btn_toggle_all.setEnabled(top_btn_enabled)
        self.btn_settings.setEnabled(enabled)
        self.btn_version.setEnabled(enabled) 
        self.setAcceptDrops(enabled) 
        
        if hasattr(self.tab1, 'btn_toggle_expand'):
            self.tab1.btn_toggle_expand.setEnabled(enabled)
            self.tab1.btn_batch_default.setEnabled(enabled)
            self.tab1.btn_batch_title.setEnabled(enabled)
            
        if hasattr(self.tab2, 'cb_pattern'):
            self.tab2.cb_pattern.setEnabled(enabled)
            if is_processing:
                self.tab2.entry_custom.setEnabled(False)
            else:
                self.tab2.on_pattern_change(self.tab2.cb_pattern.currentText())

    def open_settings(self):
        dlg = SettingsDialog(self, self.config, self.format_keys, self.i18n)
        dlg.setStyleSheet(self.styleSheet()) 
        from PyQt6.QtWidgets import QDialog
        if dlg.exec() == int(QDialog.DialogCode.Accepted):
            new_data = dlg.get_data()
            self.config.update(new_data)
            self.lang = self.config["lang"]
            save_config(self.config)
            self.apply_language()
            if hasattr(self.tab2, 'update_inner_preview_list'):
                self.tab2.update_inner_preview_list() 

    def dragEnterEvent(self, event):
        if self.tabs.currentIndex() == 3: event.ignore(); return
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

    # 🌟 [공용 버튼 라우팅] 메인 창에서 버튼을 누르면 활성화된 탭으로 명령을 보냅니다.
    def toggle_all_checkboxes(self):
        current = self.tabs.currentWidget()
        if hasattr(current, 'toggle_all_checkboxes'): current.toggle_all_checkboxes()

    def remove_selected(self):
        current = self.tabs.currentWidget()
        if hasattr(current, 'remove_selected'): current.remove_selected()

    def clear_list(self):
        current = self.tabs.currentWidget()
        if hasattr(current, 'clear_list'): current.clear_list()

    def process_paths(self, paths):
        if self.is_processing: return
        
        if self.tabs.currentIndex() == 2:
            QMessageBox.information(self, "알림", "메타데이터 탭 화면 설계 대기 중입니다.")
            return
            
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

    # 🌟 [데이터 소유권 분리] 백그라운드 작업이 완료되면 알맞은 탭의 변수에 저장합니다.
    def on_organizer_loaded(self, new_data, skipped_files):
        for fp, data in new_data.items():
            if fp not in self.tab1.org_data:
                self.tab1.org_data[fp] = data
                
        self.tab1.is_expanded = True
        self.tab1.refresh_list()
        self.safe_finish_ui_reset()
        
        if skipped_files:
            msg = "다음 파일은 내부에 폴더 구조가 없어 자동으로 제외되었습니다:\n\n" + "\n".join(skipped_files[:5])
            if len(skipped_files) > 5: msg += f"\n...외 {len(skipped_files)-5}개"
            QMessageBox.information(self, "알림", msg)

    def on_renamer_loaded(self, new_data, nested_files, unsupported_files):
        added = False
        for fp, data in new_data.items():
            if fp not in self.tab2.archive_data:
                self.tab2.archive_data[fp] = data
                added = True

        self.tab2.refresh_list()
        if added and self.tab2.table_archives.rowCount() > 0:
            self.tab2.table_archives.selectRow(self.tab2.table_archives.rowCount()-1)

        self.safe_finish_ui_reset()
        
        if unsupported_files:
            msg = "지원하지 않는 형식 제외:\n" + "\n".join(unsupported_files[:5])
            QMessageBox.warning(self, "Warning", msg)
        if nested_files:
            msg = "내부 압축파일 포함 제외:\n" + "\n".join(nested_files[:5])
            QMessageBox.warning(self, "Warning", msg)

    def start_process(self):
        if self.is_processing: return
        
        if self.tabs.currentIndex() == 0:
            targets = self.tab1.get_targets()
            if not targets:
                QMessageBox.warning(self, "Warning", "체크(☑)된 작업 대상이 없습니다." if self.lang == "ko" else "No checked targets.")
                return
            
            self.tab2.clear_list()
            self.is_processing = True
            self.toggle_ui_elements(is_processing=True)
            self.btn_run.clicked.disconnect()
            self.btn_run.clicked.connect(self.cancel_process)
            self.btn_run.setObjectName("actionBtnCancel")
            self.btn_run.setText(self.i18n[self.lang]["cancel_btn"])
            self.btn_run.setStyleSheet(self.styleSheet()) 
            self.progress_bar.show(); self.progress_bar.setValue(0)
            
            task = OrganizerProcessTask(targets, self.config, self.tab1.org_data, self.seven_zip_path, self.signals)
            self.active_task = task
            threading.Thread(target=task.run, daemon=True).start()
            
        elif self.tabs.currentIndex() == 1:
            targets = self.tab2.get_targets()
            if not targets:
                QMessageBox.warning(self, "Warning", "체크(☑)된 작업 대상이 없습니다." if self.lang == "ko" else "No checked targets.")
                return
                
            self.tab1.clear_list()
            self.is_processing = True
            self.toggle_ui_elements(is_processing=True)
            self.btn_run.clicked.disconnect()
            self.btn_run.clicked.connect(self.cancel_process)
            self.btn_run.setObjectName("actionBtnCancel")
            self.btn_run.setText(self.i18n[self.lang]["cancel_btn"])
            self.btn_run.setStyleSheet(self.styleSheet()) 
            self.progress_bar.show(); self.progress_bar.setValue(0)
            
            task = RenameTask(targets, self.config, self.tab2.archive_data, self.i18n, self.tab2.get_pattern(), self.tab2.get_custom_text(), self.seven_zip_path, self.signals)
            self.active_task = task
            threading.Thread(target=task.run, daemon=True).start()

    def cancel_process(self):
        self.btn_run.setText(self.i18n[self.lang]["cancel_wait"])
        self.btn_run.setEnabled(False)
        if hasattr(self, 'active_task') and self.active_task and hasattr(self.active_task, 'cancel'):
            self.active_task.cancel()

    def finish_process_org(self, stats, new_fps, was_cancelled):
        self.is_processing = False
        self.toggle_ui_elements(is_processing=False)

        self.btn_run.clicked.disconnect()
        self.btn_run.clicked.connect(self.start_process)
        self.btn_run.setObjectName("actionBtn") 
        self.btn_run.setText(self.i18n[self.lang]["run_btn"])
        self.btn_run.setEnabled(True)
        self.btn_run.setStyleSheet(self.styleSheet())
        
        self.tab1.clear_list()
        self.progress_bar.hide()
        self.progress_bar.setValue(0)

        if was_cancelled:
            self.lbl_status.setText(self.i18n[self.lang]["status_wait"])
            QMessageBox.warning(self, "Cancelled", "사용자에 의해 작업이 중단되었습니다." if self.lang == "ko" else "Process cancelled by user.")
            log_dlg = LogDialog(self, stats, self.i18n[self.lang], show_continue_btn=False)
            log_dlg.setStyleSheet(self.styleSheet())
            log_dlg.exec()
        else:
            if self.config.get("play_sound", True): play_complete_sound()
            if self.lang == "ko": msg_str = f"작업 완료! (성공: {len(stats['success'])}건 / 스킵: {len(stats['skip'])}건 / 오류: {len(stats['error'])}건)"
            else: msg_str = f"Done! (Success: {len(stats['success'])} / Skip: {len(stats['skip'])} / Error: {len(stats['error'])})"
            self.lbl_status.setText(msg_str)
            
            valid_fps = [fp for fp in new_fps if os.path.exists(fp)]
            show_cont = len(valid_fps) > 0
            
            log_dlg = LogDialog(self, stats, self.i18n[self.lang], show_continue_btn=show_cont)
            log_dlg.setStyleSheet(self.styleSheet())
            
            from PyQt6.QtWidgets import QDialog
            if log_dlg.exec() == int(QDialog.DialogCode.Accepted):
                self.tabs.setCurrentIndex(1)
                self.process_paths(valid_fps)

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
                if old_fp in self.tab2.archive_data: del self.tab2.archive_data[old_fp]
                self.tab2.load_archive_info(new_fp)
                self.tab2.current_archive_path = new_fp 
            else:
                self.tab2.load_archive_info(new_fp)
        self.tab2.refresh_list()
        
        if getattr(self.tab2, 'current_archive_path', None) and self.tab2.current_archive_path in self.tab2.archive_data:
            for row in range(self.tab2.table_archives.rowCount()):
                if self.tab2.table_archives.item(row, 0).data(Qt.ItemDataRole.UserRole) == self.tab2.current_archive_path:
                    self.tab2.table_archives.selectRow(row)
                    break

        if was_cancelled:
            self.safe_finish_ui_reset()
            QMessageBox.warning(self, "Cancelled", "사용자에 의해 작업이 중단되었습니다." if self.lang == "ko" else "Process cancelled by user.")
        else:
            if self.config.get("play_sound", True): play_complete_sound()
            self.progress_bar.hide()
            self.progress_bar.setValue(0)
            if self.lang == "ko": msg_str = f"작업 완료! (성공: {len(stats['success'])}건 / 스킵: {len(stats['skip'])}건 / 오류: {len(stats['error'])}건)"
            else: msg_str = f"Done! (Success: {len(stats['success'])} / Skip: {len(stats['skip'])} / Error: {len(stats['error'])})"
            self.lbl_status.setText(msg_str)
        
        log_dlg = LogDialog(self, stats, self.i18n[self.lang], show_continue_btn=False)
        log_dlg.setStyleSheet(self.styleSheet())
        log_dlg.exec()

    def safe_finish_ui_reset(self):
        self.is_processing = False
        self.toggle_ui_elements(is_processing=False)
        self.lbl_status.setText(self.i18n[self.lang]["status_wait"])
        QTimer.singleShot(300, self._actual_hide)

    def _actual_hide(self):
        self.progress_bar.hide()
        self.progress_bar.setValue(0)

    def closeEvent(self, event):
        self.config["width"] = self.normalGeometry().width()
        self.config["height"] = self.normalGeometry().height()
        self.config["is_maximized"] = self.isMaximized()
        save_config(self.config)
        event.accept()
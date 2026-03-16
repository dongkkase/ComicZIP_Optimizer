from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton, 
    QFormLayout, QComboBox, QSlider, QFrame, QCheckBox, QDialogButtonBox,
    QTabWidget, QWidget, QLineEdit, QMessageBox
)
from PyQt6.QtCore import Qt

class LogDialog(QDialog):
    def __init__(self, parent, stats, i18n, show_continue_btn=False):
        super().__init__(parent)
        self.setWindowTitle(i18n["log_title"])
        self.resize(550, 400)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        layout = QVBoxLayout(self)
        lbl_summary = QLabel(f"✅ Success: {len(stats['success'])}  |  ⏩ Skip: {len(stats['skip'])}  |  ❌ Error: {len(stats['error'])}")
        lbl_summary.setStyleSheet("font-weight: bold; font-size: 14px; margin-bottom: 10px;")
        layout.addWidget(lbl_summary)
        
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setStyleSheet("background-color: #1a1a1a; color: #e0e0e0; font-family: Consolas, monospace; padding: 10px;")
        
        log_content = ""
        if stats['error']: log_content += "❌ [ERRORS]\n" + "\n".join(stats['error']) + "\n\n"
        if stats['success']: log_content += "✅ [SUCCESS]\n" + "\n".join(stats['success']) + "\n\n"
        if stats['skip']: log_content += "⏩ [SKIPPED]\n" + "\n".join(stats['skip']) + "\n"
        self.text_edit.setText(log_content)
        layout.addWidget(self.text_edit)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        if show_continue_btn:
            btn_cont = QPushButton(i18n.get("btn_continue_tab2", "Continue"))
            btn_cont.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_cont.setStyleSheet("background-color: #27AE60; color: white; font-weight: bold; padding: 8px 15px; border-radius: 4px; border: none;")
            btn_cont.clicked.connect(self.accept)
            btn_layout.addWidget(btn_cont)
        btn_close = QPushButton(i18n["btn_close"])
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setStyleSheet("padding: 8px 15px;")
        btn_close.clicked.connect(self.reject)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)


class SettingsDialog(QDialog):
    def __init__(self, parent, config, format_keys, i18n):
        super().__init__(parent)
        self.config = config
        self.i18n = i18n[config["lang"]]
        self.setWindowTitle(self.i18n.get("settings_title", "환경 설정"))
        self.setFixedSize(480, 680) 
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        
        self.tabs = QTabWidget()
        
        # --- 첫 번째 탭: 기본 설정 ---
        self.tab_basic = QWidget()
        basic_layout = QVBoxLayout(self.tab_basic)
        basic_layout.setContentsMargins(15, 15, 15, 15)
        basic_layout.setSpacing(15)
        
        form_layout = QFormLayout()
        form_layout.setSpacing(15)

        self.cb_lang = QComboBox()
        self.cb_lang.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cb_lang.addItems(["한국어", "English"])
        self.cb_lang.setCurrentText("한국어" if config["lang"] == "ko" else "English")
        form_layout.addRow(self.i18n.get("lang_lbl", "언어:"), self.cb_lang)

        self.cb_format = QComboBox()
        self.cb_format.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cb_format.addItems(self.i18n.get("format_opts", ["None"]))
        try: fmt_idx = format_keys.index(config["target_format"])
        except ValueError: fmt_idx = 0
        self.cb_format.setCurrentIndex(fmt_idx)
        form_layout.addRow(self.i18n.get("format_lbl", "포맷:"), self.cb_format)

        from config import get_safe_thread_limits
        total_cores, safe_max, default_threads = get_safe_thread_limits()
        self.slider_threads = QSlider(Qt.Orientation.Horizontal)
        self.slider_threads.setRange(1, safe_max)
        self.slider_threads.setValue(config.get("max_threads", default_threads))
        self.slider_threads.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_threads_val = QLabel(f"{self.slider_threads.value()} 코어" if config["lang"]=="ko" else f"{self.slider_threads.value()} Cores")
        self.lbl_threads_val.setFixedWidth(60)
        
        th_layout = QHBoxLayout()
        th_layout.addWidget(self.slider_threads)
        th_layout.addWidget(self.lbl_threads_val)
        self.slider_threads.valueChanged.connect(lambda v: self.lbl_threads_val.setText(f"{v} 코어" if config["lang"]=="ko" else f"{v} Cores"))
        
        lbl_threads_desc = QLabel(self.i18n.get("threads_desc", ""))
        lbl_threads_desc.setWordWrap(True)
        lbl_threads_desc.setStyleSheet("color: #E74C3C; font-size: 11px; margin-top: 5px;")
        form_layout.addRow(self.i18n.get("max_threads", "스레드:"), th_layout)
        form_layout.addRow("", lbl_threads_desc)
        basic_layout.addLayout(form_layout)

        line = QFrame(); line.setFrameShape(QFrame.Shape.HLine); line.setObjectName("divider")
        basic_layout.addWidget(line)

        opt_layout = QVBoxLayout(); opt_layout.setSpacing(5)
        self.chk_sound = QCheckBox(self.i18n.get("play_sound", "Play completion sound"))
        self.chk_sound.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_sound.setChecked(config.get("play_sound", True))
        opt_layout.addWidget(self.chk_sound)
        opt_layout.addSpacing(15)

        self.chk_backup = QCheckBox(self.i18n.get("backup", "Backup"))
        self.chk_backup.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_backup.setChecked(config.get("backup_on", False))
        opt_layout.addWidget(self.chk_backup)

        opt_layout.addSpacing(15)
        self.chk_flatten = QCheckBox(self.i18n.get("flatten", "Flatten"))
        self.chk_flatten.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_flatten.setChecked(config.get("flatten_folders", False))
        lbl_flatten_desc = QLabel(self.i18n.get("flatten_desc", ""))
        lbl_flatten_desc.setWordWrap(True)
        lbl_flatten_desc.setStyleSheet("color: #aaaaaa; font-size: 11px; margin-left: 25px;")
        opt_layout.addWidget(self.chk_flatten)
        opt_layout.addWidget(lbl_flatten_desc)

        opt_layout.addSpacing(15)
        self.chk_webp = QCheckBox(self.i18n.get("webp", "WebP"))
        self.chk_webp.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_webp.setChecked(config.get("webp_conversion", False))
        lbl_webp_desc = QLabel(self.i18n.get("webp_desc", ""))
        lbl_webp_desc.setWordWrap(True)
        lbl_webp_desc.setStyleSheet("color: #aaaaaa; font-size: 11px; margin-left: 25px;") 
        opt_layout.addWidget(self.chk_webp)
        opt_layout.addWidget(lbl_webp_desc)

        self.slider_quality = QSlider(Qt.Orientation.Horizontal)
        self.slider_quality.setRange(1, 100)
        self.slider_quality.setValue(config.get("webp_quality", 100))
        self.slider_quality.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_quality_val = QLabel()
        self.lbl_quality_val.setFixedWidth(90)
        
        qual_layout = QHBoxLayout()
        qual_layout.setContentsMargins(25, 5, 0, 0)
        lbl_qual_title = QLabel(self.i18n.get("webp_quality", "Quality"))
        qual_layout.addWidget(lbl_qual_title)
        qual_layout.addWidget(self.slider_quality)
        qual_layout.addWidget(self.lbl_quality_val)
        
        def update_qual_label(v):
            txt = f"{v}%"
            if v == 100: txt += " (Lossless)"
            self.lbl_quality_val.setText(txt)
        self.slider_quality.valueChanged.connect(update_qual_label)
        update_qual_label(self.slider_quality.value())

        self.chk_webp.toggled.connect(self.slider_quality.setEnabled)
        self.chk_webp.toggled.connect(self.lbl_quality_val.setEnabled)
        self.chk_webp.toggled.connect(lbl_qual_title.setEnabled)
        self.slider_quality.setEnabled(self.chk_webp.isChecked())
        self.lbl_quality_val.setEnabled(self.chk_webp.isChecked())
        lbl_qual_title.setEnabled(self.chk_webp.isChecked())

        opt_layout.addLayout(qual_layout)
        basic_layout.addLayout(opt_layout)
        basic_layout.addStretch()

        # --- 두 번째 탭: API 검색 설정 ---
        self.tab_api = QWidget()
        api_layout = QFormLayout(self.tab_api)
        api_layout.setSpacing(20)
        api_layout.setContentsMargins(20, 25, 20, 20)
        
        # 🌟 API 매뉴얼 버튼 추가
        api_header_layout = QHBoxLayout()
        api_header_layout.addStretch()
        self.btn_api_manual = QPushButton(self.i18n.get("btn_api_manual", "❓ API 발급 매뉴얼"))
        self.btn_api_manual.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_api_manual.setStyleSheet("background-color: #2b5797; color: white; padding: 6px 12px; border-radius: 4px; font-weight: bold;")
        self.btn_api_manual.clicked.connect(self.show_api_manual)
        api_header_layout.addWidget(self.btn_api_manual)
        
        api_layout.addRow(api_header_layout)
        
        api_keys = config.get("api_keys", {})
        
        self.le_aladin_key = QLineEdit(api_keys.get("aladin", ""))
        self.le_aladin_key.setPlaceholderText("알라딘 OpenAPI TTBKey를 입력하세요")
        self.le_aladin_key.setStyleSheet("padding: 5px;")
        api_layout.addRow("알라딘 TTBKey:", self.le_aladin_key)
        
        self.le_vine_key = QLineEdit(api_keys.get("vine", ""))
        self.le_vine_key.setPlaceholderText("Comic Vine API Key를 입력하세요")
        self.le_vine_key.setStyleSheet("padding: 5px;")
        api_layout.addRow("Comic Vine API:", self.le_vine_key)
        
        self.le_google_key = QLineEdit(api_keys.get("google", ""))
        self.le_google_key.setPlaceholderText("Google Books API Key를 입력하세요")
        self.le_google_key.setStyleSheet("padding: 5px;")
        api_layout.addRow("Google Books API:", self.le_google_key)
        
        api_layout.addRow(QLabel(" "))
        cb_label = QLabel("코믹박스 (Comicbox) 설정")
        cb_label.setStyleSheet("font-weight: bold; color: #3498DB;")
        api_layout.addRow(cb_label)

        self.le_comicbox_url = QLineEdit(api_keys.get("comicbox_url", ""))
        self.le_comicbox_url.setPlaceholderText("예: http://192.168.1.100:8080")
        self.le_comicbox_url.setStyleSheet("padding: 5px;")
        api_layout.addRow("코믹박스 URL:", self.le_comicbox_url)
        
        self.le_comicbox_token = QLineEdit(api_keys.get("comicbox_token", ""))
        self.le_comicbox_token.setPlaceholderText("API Token 또는 비밀번호")
        self.le_comicbox_token.setStyleSheet("padding: 5px;")
        self.le_comicbox_token.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        api_layout.addRow("코믹박스 Token:", self.le_comicbox_token)
        
        api_notice = QLabel("※ API 키가 없는 서비스는 검색이 제한될 수 있습니다.\n※ 각 서비스 홈페이지에서 무료로 발급받아 사용할 수 있습니다.")
        api_notice.setStyleSheet("color: #aaa; font-size: 12px; margin-top: 15px;")
        api_layout.addRow(api_notice)

        self.tabs.addTab(self.tab_basic, self.i18n.get("tab_basic", "기본 설정"))
        self.tabs.addTab(self.tab_api, self.i18n.get("tab_api", "API 검색 설정"))
        
        main_layout.addWidget(self.tabs)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setText(self.i18n.get("btn_save", "저장"))
        btn_box.button(QDialogButtonBox.StandardButton.Cancel).setText(self.i18n.get("btn_cancel", "취소"))
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setCursor(Qt.CursorShape.PointingHandCursor)
        btn_box.button(QDialogButtonBox.StandardButton.Cancel).setCursor(Qt.CursorShape.PointingHandCursor)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        main_layout.addWidget(btn_box)

    # 🌟 API 매뉴얼 팝업 함수
    def show_api_manual(self):
        msg = QMessageBox(self)
        msg.setWindowTitle(self.i18n.get("api_manual_title", "API 발급 매뉴얼"))
        
        if self.config.get("lang") == "en":
            text = (
                "<b>[ Aladin ]</b><br>"
                "1. Visit <a href='https://blog.aladin.co.kr/openapi' style='color:#3498DB;'>Aladin OpenAPI</a> and login.<br>"
                "2. Apply for a 'TTBKey' in the menu.<br><br>"
                "<b>[ Comic Vine ]</b><br>"
                "1. Visit <a href='https://comicvine.gamespot.com/api/' style='color:#3498DB;'>Comic Vine API</a> and sign in.<br>"
                "2. Copy the API Key from your developer page.<br><br>"
                "<b>[ Google Books ]</b><br>"
                "1. Visit <a href='https://console.cloud.google.com/' style='color:#3498DB;'>Google Cloud Console</a>.<br>"
                "2. Create a project and enable 'Google Books API'.<br>"
                "3. Generate an API Key under 'Credentials'.<br><br>"
                "<b>[ Comicbox ]</b><br>"
                "1. Enter your self-hosted server URL (e.g., http://192.168.x.x:8080)<br>"
                "2. Enter the API Token or password."
            )
        else:
            text = (
                "<b>[ 알라딘 (Aladin) ]</b><br>"
                "1. <a href='https://blog.aladin.co.kr/openapi' style='color:#3498DB;'>알라딘 OpenAPI 홈페이지</a> 접속 및 로그인<br>"
                "2. 'TTBKey 발급 신청' 메뉴에서 발급<br><br>"
                "<b>[ Comic Vine ]</b><br>"
                "1. <a href='https://comicvine.gamespot.com/api/' style='color:#3498DB;'>Comic Vine API 홈페이지</a> 가입 및 로그인<br>"
                "2. 개발자 페이지에서 API Key 복사<br><br>"
                "<b>[ Google Books ]</b><br>"
                "1. <a href='https://console.cloud.google.com/' style='color:#3498DB;'>Google Cloud Console</a> 접속<br>"
                "2. 새 프로젝트 생성 후 'Google Books API' 사용 설정<br>"
                "3. '사용자 인증 정보' 메뉴에서 API Key 생성<br><br>"
                "<b>[ 코믹박스 (Comicbox) ]</b><br>"
                "1. 본인이 구축한 서버 주소 (예: http://192.168.x.x:8080)<br>"
                "2. 서버에 설정된 API Token 또는 접속 비밀번호 입력"
            )
            
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setText(text)
        msg.exec()

    def get_data(self):
        format_keys = ["none", "zip", "cbz", "cbr", "7z"]
        return {
            "lang": "ko" if self.cb_lang.currentText() == "한국어" else "en",
            "target_format": format_keys[self.cb_format.currentIndex()],
            "backup_on": self.chk_backup.isChecked(),
            "flatten_folders": self.chk_flatten.isChecked(),
            "webp_conversion": self.chk_webp.isChecked(),
            "webp_quality": self.slider_quality.value(),
            "max_threads": self.slider_threads.value(),
            "play_sound": self.chk_sound.isChecked(),
            
            "api_keys": {
                "aladin": self.le_aladin_key.text().strip(),
                "vine": self.le_vine_key.text().strip(),
                "google": self.le_google_key.text().strip(),
                "comicbox_url": self.le_comicbox_url.text().strip(),
                "comicbox_token": self.le_comicbox_token.text().strip()
            }
        }
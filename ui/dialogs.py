import sqlite3
import qtawesome as qta
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton, 
    QFormLayout, QComboBox, QSlider, QFrame, QCheckBox, QDialogButtonBox,
    QTabWidget, QWidget, QLineEdit, QMessageBox, QGroupBox
)
from PyQt6.QtCore import Qt
from ui.widgets import Toast

class LogDialog(QDialog):
    def __init__(self, parent, stats, i18n, show_continue_btn=False, continue_key="btn_continue_tab2"):
        super().__init__(parent)
        self.setWindowTitle(i18n["log_title"])
        self.resize(550, 400)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        
        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; color: #ffffff; font-family: '맑은 고딕', 'Segoe UI Emoji'; }
            QLabel { color: #ffffff; }
        """)
        
        layout = QVBoxLayout(self)
        lbl_summary = QLabel(f"Success: {len(stats['success'])}  |  Skip: {len(stats['skip'])}  |  Error: {len(stats['error'])}")
        lbl_summary.setStyleSheet("font-weight: bold; font-size: 14px; margin-bottom: 10px; color: #ffffff;")
        layout.addWidget(lbl_summary)
        
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setStyleSheet("background-color: #1a1a1a; color: #e0e0e0; font-family: Consolas, monospace; padding: 10px; border: 1px solid #444; border-radius: 4px;")
        
        log_content = ""
        if stats['error']: log_content += "[ERRORS]\n" + "\n".join(stats['error']) + "\n\n"
        if stats['success']: log_content += "[SUCCESS]\n" + "\n".join(stats['success']) + "\n\n"
        if stats['skip']: log_content += "[SKIPPED]\n" + "\n".join(stats['skip']) + "\n"
        self.text_edit.setText(log_content)
        layout.addWidget(self.text_edit)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        if show_continue_btn:
            btn_cont = QPushButton(i18n.get(continue_key, "Continue"))
            btn_cont.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_cont.setStyleSheet("background-color: #27AE60; color: white; font-weight: bold; padding: 8px 15px; border-radius: 4px; border: none;")
            btn_cont.clicked.connect(self.accept)
            btn_layout.addWidget(btn_cont)
            
        btn_close = QPushButton(i18n["btn_close"])
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setStyleSheet("background-color: #555; color: white; font-weight: bold; padding: 8px 15px; border-radius: 4px; border: none;")
        btn_close.clicked.connect(self.reject)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

class SettingsDialog(QDialog):
    def __init__(self, parent, config, format_keys, i18n):
        super().__init__(parent)
        self.config = config
        self.i18n = i18n[config["lang"]]
        self.setWindowTitle(self.i18n.get("settings_title", "환경 설정"))
        self.setFixedSize(500, 750) 
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        # 🌟 탭 내부 영역까지 모두 하얀색 글자와 어두운 배경이 적용되도록 강력한 CSS 주입
        self.setStyleSheet("""
            QDialog, QWidget { background-color: #1e1e1e; color: #ffffff; font-family: '맑은 고딕', 'Segoe UI Emoji'; }
            QLabel, QCheckBox { background-color: transparent; color: #ffffff; color:pointer}
            
            QTabWidget::pane { border: 1px solid #444; border-radius: 5px; background: #1e1e1e; }
            
            QTabBar::tab { background: #2b2b2b; color: #888; border: 1px solid #444; padding: 8px 20px; font-weight: bold; }
            QTabBar::tab:selected { background: #3a7ebf; color: #ffffff; }
            
            QGroupBox { border: 1px solid #555; border-radius: 6px; margin-top: 15px; padding-top: 15px; font-weight: bold; color: #ffffff; background-color: transparent; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; color: #3498DB; }
            
            QComboBox, QLineEdit, QTextEdit { background-color: #3a3a3a; color: #ffffff; border: 1px solid #555; border-radius: 4px; padding: 5px; }
            QPushButton { background-color: #3a3a3a; color: white; border-radius: 4px; padding: 6px 12px; font-weight: bold; border: 1px solid #555; }
            QPushButton:hover { background-color: #4a4a4a; }
            
            QSlider::groove:horizontal { border-radius: 4px; height: 8px; background: #3a3a3a; }
            QSlider::handle:horizontal { background: #3498DB; width: 16px; height: 16px; margin: -4px 0; border-radius: 8px; }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        
        self.tabs = QTabWidget()
        
        self.tab_basic = QWidget()
        basic_layout = QVBoxLayout(self.tab_basic)
        basic_layout.setContentsMargins(15, 15, 15, 15)
        basic_layout.setSpacing(15)
        
        form_layout = QFormLayout()
        form_layout.setSpacing(15)

        self.cb_lang = QComboBox()
        self.cb_lang.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cb_lang.addItems(["한국어", "English", "日本語"])
        
        if config["lang"] == "ko": lang_text = "한국어"
        elif config["lang"] == "ja": lang_text = "日本語"
        else: lang_text = "English"
        self.cb_lang.setCurrentText(lang_text)
        
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
        
        if config["lang"] == "ko": th_lbl_txt = f"{self.slider_threads.value()} 코어"
        elif config["lang"] == "ja": th_lbl_txt = f"{self.slider_threads.value()} コア"
        else: th_lbl_txt = f"{self.slider_threads.value()} Cores"
        
        self.lbl_threads_val = QLabel(th_lbl_txt)
        self.lbl_threads_val.setFixedWidth(60)
        
        th_layout = QHBoxLayout()
        th_layout.addWidget(self.slider_threads)
        th_layout.addWidget(self.lbl_threads_val)
        
        def update_th_label(v):
            if config["lang"] == "ko": txt = f"{v} 코어"
            elif config["lang"] == "ja": txt = f"{v} コア"
            else: txt = f"{v} Cores"
            self.lbl_threads_val.setText(txt)
            
        self.slider_threads.valueChanged.connect(update_th_label)
        
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

        self.tab_api = QWidget()
        api_layout = QFormLayout(self.tab_api)
        api_layout.setSpacing(12)
        api_layout.setContentsMargins(20, 20, 20, 20)
        
        api_keys = config.get("api_keys", {})
        
        def _make_pw_field(value, placeholder):
            w = QWidget()
            ly = QHBoxLayout(w)
            ly.setContentsMargins(0, 0, 0, 0)
            ly.setSpacing(5)
            
            le = QLineEdit(value)
            le.setPlaceholderText(placeholder)
            le.setEchoMode(QLineEdit.EchoMode.Password)
            
            btn = QPushButton()
            btn.setIcon(qta.icon('fa5s.eye', color='#dddddd'))
            btn.setFixedSize(28, 28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            
            def toggle_visibility():
                if le.echoMode() == QLineEdit.EchoMode.Password:
                    le.setEchoMode(QLineEdit.EchoMode.Normal)
                    btn.setIcon(qta.icon('fa5s.eye-slash', color='white'))
                    btn.setStyleSheet("background-color: #3498DB; border: 1px solid #3498DB; border-radius: 4px;")
                else:
                    le.setEchoMode(QLineEdit.EchoMode.Password)
                    btn.setIcon(qta.icon('fa5s.eye', color='#dddddd'))
                    btn.setStyleSheet("background-color: #3a3a3a; border: 1px solid #555; border-radius: 4px;")
            
            btn.clicked.connect(toggle_visibility)
            ly.addWidget(le)
            ly.addWidget(btn)
            return w, le
        
        ai_group = QGroupBox(self.i18n.get("ai_trans_group", "AI 검색어 최적화"))
        ai_group_layout = QFormLayout(ai_group)
        ai_group_layout.setContentsMargins(10, 15, 10, 10)
        ai_group_layout.setSpacing(10)

        self.chk_ai_trans = QCheckBox(self.i18n.get("ai_trans_enable", "AI를 활용한 공식 영문명 변환 사용"))
        self.chk_ai_trans.setChecked(api_keys.get("ai_trans_enabled", False))
        self.chk_ai_trans.setCursor(Qt.CursorShape.PointingHandCursor)
        ai_group_layout.addRow(self.chk_ai_trans)

        self.cb_ai_provider = QComboBox()
        self.cb_ai_provider.addItems(["Gemini", "OpenAI"])
        self.cb_ai_provider.setCurrentText(api_keys.get("ai_provider", "Gemini"))
        self.cb_ai_provider.setCursor(Qt.CursorShape.PointingHandCursor)
        ai_group_layout.addRow(self.i18n.get("ai_provider", "AI 모델 선택:"), self.cb_ai_provider)

        self.ai_key_widget, self.le_ai_key = _make_pw_field(api_keys.get("ai_key", ""), "API Key")
        ai_group_layout.addRow(self.i18n.get("ai_api_key", "API Key:"), self.ai_key_widget)

        lbl_ai_notice = QLabel(self.i18n.get("ai_notice", "해외 DB 검색 시 정확도를 대폭 높입니다."))
        lbl_ai_notice.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        lbl_ai_notice.setWordWrap(True)
        ai_group_layout.addRow(lbl_ai_notice)

        def toggle_ai_inputs(checked):
            self.cb_ai_provider.setEnabled(checked)
            self.ai_key_widget.setEnabled(checked)
            
        self.chk_ai_trans.toggled.connect(toggle_ai_inputs)
        toggle_ai_inputs(self.chk_ai_trans.isChecked())

        api_layout.addRow(ai_group)
        
        api_header_layout = QHBoxLayout()
        api_header_layout.addStretch()
        self.btn_api_manual = QPushButton(self.i18n.get("btn_api_manual", "API 발급 매뉴얼"))
        self.btn_api_manual.setIcon(qta.icon('fa5s.book-open', color='white'))
        self.btn_api_manual.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_api_manual.setStyleSheet("background-color: #2b5797; color: white; padding: 6px 12px; border-radius: 4px; font-weight: bold; border: none;")
        self.btn_api_manual.clicked.connect(self.show_api_manual)
        api_header_layout.addWidget(self.btn_api_manual)
        
        api_layout.addRow(api_header_layout)
        
        self.aladin_widget, self.le_aladin_key = _make_pw_field(api_keys.get("aladin", ""), "Aladin TTBKey")
        api_layout.addRow("Aladin TTBKey:", self.aladin_widget)
        
        self.google_widget, self.le_google_key = _make_pw_field(api_keys.get("google", ""), "Google Books API Key")
        api_layout.addRow("Google Books API:", self.google_widget)
        
        self.vine_widget, self.le_vine_key = _make_pw_field(api_keys.get("vine", ""), "Comic Vine API Key")
        api_layout.addRow("Comic Vine API:", self.vine_widget)
        
        tag_group = QGroupBox(self.i18n.get("tag_rules_group", "태그 표준화 규칙"))
        tag_group_layout = QVBoxLayout(tag_group)
        tag_group_layout.setContentsMargins(10, 15, 10, 10)
        
        lbl_tag_notice = QLabel(self.i18n.get("tag_rules_desc", "치환할 태그를 '기존태그 -> 새태그' 형식으로 입력하세요."))
        lbl_tag_notice.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        lbl_tag_notice.setWordWrap(True)
        tag_group_layout.addWidget(lbl_tag_notice)
        
        self.te_tag_rules = QTextEdit()
        self.te_tag_rules.setFixedHeight(70)
        self.te_tag_rules.setPlaceholderText("Shounen, 소년만화 -> 소년\nAction -> 액션")
        self.te_tag_rules.setPlainText(api_keys.get("tag_rules", ""))
        tag_group_layout.addWidget(self.te_tag_rules)
        
        api_layout.addRow(tag_group)
        
        cache_layout = QHBoxLayout()
        cache_layout.addStretch()
        self.btn_clear_cache = QPushButton(self.i18n.get("btn_clear_cache", "검색 캐시 비우기"))
        self.btn_clear_cache.setIcon(qta.icon('fa5s.trash-alt', color='white'))
        self.btn_clear_cache.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_cache.setStyleSheet("background-color: #E74C3C; color: white; padding: 6px 12px; border-radius: 4px; font-weight: bold; border: none;")
        self.btn_clear_cache.clicked.connect(self.action_clear_cache)
        cache_layout.addWidget(self.btn_clear_cache)
        api_layout.addRow(cache_layout)

        self.tabs.addTab(self.tab_basic, self.i18n.get("tab_basic", "기본 설정"))
        self.tabs.addTab(self.tab_api, self.i18n.get("tab_api", "API 검색 설정"))
        
        main_layout.addWidget(self.tabs)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setText(self.i18n.get("btn_save", "저장"))
        btn_box.button(QDialogButtonBox.StandardButton.Cancel).setText(self.i18n.get("btn_cancel", "취소"))
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setCursor(Qt.CursorShape.PointingHandCursor)
        btn_box.button(QDialogButtonBox.StandardButton.Cancel).setCursor(Qt.CursorShape.PointingHandCursor)
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setStyleSheet("background-color: #3498DB; color: white; font-weight: bold;")
        
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        main_layout.addWidget(btn_box)

    def action_clear_cache(self):
        try:
            with sqlite3.connect(".api_cache.db", timeout=10) as conn:
                c = conn.cursor()
                c.execute("DELETE FROM search_cache")
                c.execute("DELETE FROM img_cache")
                c.execute("DELETE FROM trans_cache")
                conn.commit()
            Toast.show(self.parent(), self.i18n.get("msg_cache_cleared", "캐시가 초기화되었습니다."))
        except Exception as e:
            pass

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
                "3. Generate an API Key under 'Credentials'."
            )
        elif self.config.get("lang") == "ja":
            text = (
                "<b>[ Aladin ]</b><br>"
                "1. <a href='https://blog.aladin.co.kr/openapi' style='color:#3498DB;'>Aladin OpenAPI</a> に接続してログイン<br>"
                "2. 'TTBKey 発行申請' メニューから発行<br><br>"
                "<b>[ Comic Vine ]</b><br>"
                "1. <a href='https://comicvine.gamespot.com/api/' style='color:#3498DB;'>Comic Vine API</a> にサインイン<br>"
                "2. 開発者ページから API Key をコピー<br><br>"
                "<b>[ Google Books ]</b><br>"
                "1. <a href='https://console.cloud.google.com/' style='color:#3498DB;'>Google Cloud Console</a> に接続<br>"
                "2. プロジェクトを作成し 'Google Books API' を有効化<br>"
                "3. '認証情報' メニューから API Key を作成"
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
                "3. '사용자 인증 정보' 메뉴에서 API Key 생성"
            )
            
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setText(text)
        msg.exec()

    def get_data(self):
        format_keys = ["none", "zip", "cbz", "cbr", "7z"]
        
        lang_text = self.cb_lang.currentText()
        if lang_text == "한국어": lang_val = "ko"
        elif lang_text == "日本語": lang_val = "ja"
        else: lang_val = "en"
        
        return {
            "lang": lang_val,
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
                
                "ai_trans_enabled": self.chk_ai_trans.isChecked(),
                "ai_provider": self.cb_ai_provider.currentText(),
                "ai_key": self.le_ai_key.text().strip(),
                
                "tag_rules": self.te_tag_rules.toPlainText()
            }
        }
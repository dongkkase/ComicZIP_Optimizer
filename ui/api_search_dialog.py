import difflib
import requests
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, 
    QWidget, QFormLayout, QComboBox, QSplitter, QScrollArea, QFrame,
    QListWidget, QListWidgetItem, QSizePolicy
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap, QPainter, QPainterPath

from core.api_fetcher import MetaApiFetcher

def similar(a, b): return difflib.SequenceMatcher(None, a, b).ratio()

_active_image_threads = []

class ImageLoadThread(QThread):
    finished_data = pyqtSignal(bytes, str)
    def __init__(self, url):
        super().__init__()
        self.url = url
        _active_image_threads.append(self)
        self.finished.connect(self._cleanup)
    def run(self):
        try:
            if self.url:
                resp = requests.get(self.url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
                if resp.status_code == 200:
                    self.finished_data.emit(resp.content, self.url)
                    return
        except: pass
        self.finished_data.emit(b"", self.url)
    def _cleanup(self):
        if self in _active_image_threads: _active_image_threads.remove(self)

class SearchResultWidget(QWidget):
    def __init__(self, data, parent=None):
        super().__init__(parent)
        self.cover_url = data.get("CoverUrl", "")
        
        self.setStyleSheet("background-color: transparent;")
        # 🌟 리스트 아이템 전체 영역에 손가락 커서 적용
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 10, 20, 10)
        layout.setSpacing(15)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop) 
        
        self.lbl_thumb = QLabel()
        self.lbl_thumb.setFixedSize(45, 64)
        self.lbl_thumb.setStyleSheet("background-color: #333; border-radius: 5px;")
        self.lbl_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_thumb, alignment=Qt.AlignmentFlag.AlignTop)
        
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)
        info_layout.setAlignment(Qt.AlignmentFlag.AlignTop) 
        
        self.lbl_title = QLabel(data.get("Title", ""))
        self.lbl_title.setWordWrap(True)
        self.lbl_title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.lbl_title.setStyleSheet("font-weight: bold; font-size: 14px; color: #EAEAEA; background-color: transparent; border: none; outline: none;")
        info_layout.addWidget(self.lbl_title)
        
        raw_summary = data.get("Summary", "")
        clean_summary = raw_summary.replace("\n", " ").replace("\r", "").strip() if raw_summary else ""
        
        if len(clean_summary) > 38:
            clean_summary = clean_summary[:38] + "..."
            
        self.lbl_summary = QLabel(clean_summary)
        self.lbl_summary.setWordWrap(False) 
        self.lbl_summary.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.lbl_summary.setStyleSheet("color: #999999; font-size: 12px; background-color: transparent; border: none; outline: none;")
        
        if clean_summary:
            info_layout.addWidget(self.lbl_summary)
        
        meta_layout = QHBoxLayout()
        meta_layout.setSpacing(8)
        meta_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        
        writer = data.get("Writer", "")
        pub = data.get("Publisher", "")
        rating = str(data.get("RatingScore", "")).strip()
        
        def add_meta_item(text, color):
            lbl = QLabel(text)
            lbl.setStyleSheet(f"color: {color}; font-size: 11px; background-color: transparent; border: none; outline: none;")
            meta_layout.addWidget(lbl)
            
        def add_divider():
            lbl = QLabel("|")
            lbl.setStyleSheet("color: rgba(255, 255, 255, 0.3); font-size: 9px; background-color: transparent; border: none; outline: none;")
            meta_layout.addWidget(lbl)

        items_added = 0
        if writer:
            add_meta_item(writer, "#AAAAAA")
            items_added += 1
            
        if pub:
            if items_added > 0: add_divider()
            add_meta_item(pub, "#AAAAAA")
            items_added += 1
            
        if rating and rating != "-":
            if items_added > 0: add_divider()
            add_meta_item(f"⭐ {rating}", "#F1C40F")
            
        meta_layout.addStretch()
        info_layout.addLayout(meta_layout)
        info_layout.addStretch() 
        
        layout.addLayout(info_layout)
        
        if self.cover_url:
            self.thread = ImageLoadThread(self.cover_url)
            self.thread.finished_data.connect(self.on_image_loaded)
            self.thread.start()
            
    def on_image_loaded(self, img_data, url):
        try:
            if getattr(self, "lbl_thumb", None) is None: return
            if url == self.cover_url and img_data:
                image = QImage.fromData(img_data)
                if not image.isNull():
                    scaled_pixmap = QPixmap.fromImage(image).scaled(
                        45, 64, 
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding, 
                        Qt.TransformationMode.SmoothTransformation
                    )
                    
                    crop_x = (scaled_pixmap.width() - 45) // 2
                    crop_y = (scaled_pixmap.height() - 64) // 2
                    cropped_pixmap = scaled_pixmap.copy(crop_x, crop_y, 45, 64)
                    
                    rounded_pixmap = QPixmap(45, 64)
                    rounded_pixmap.fill(Qt.GlobalColor.transparent)
                    
                    painter = QPainter(rounded_pixmap)
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                    
                    path = QPainterPath()
                    path.addRoundedRect(0, 0, 45, 64, 5, 5) 
                    
                    painter.setClipPath(path)
                    painter.drawPixmap(0, 0, cropped_pixmap)
                    painter.end()
                    
                    self.lbl_thumb.setPixmap(rounded_pixmap)
        except RuntimeError: pass


class ApiSearchDialog(QDialog):
    def __init__(self, api_name, query, h1_text, parent=None, t=None):
        super().__init__(parent)
        self.current_api = api_name
        self.current_query = query
        self.h1_text = h1_text
        self.t = t if t else {}
        self.api_keys = parent.main_app.config.get("api_keys", {}) if parent and hasattr(parent, "main_app") else {}
        
        self.search_results = []
        self.selected_raw_data = None  
        self.translated_data = None 
        self.is_translated = False
        self.current_cover_url = None
        
        # 🌟 다국어: 창 제목
        self.setWindowTitle(self.t.get("meta_search_title", "메타데이터 검색"))
        self.resize(1050, 750)
        self.setup_ui()
        self.perform_search()

    def setup_ui(self):
        self.setStyleSheet("""
            QScrollBar:vertical { border: none; background-color: #2b2b2b; width: 10px; border-radius: 5px; }
            QScrollBar::handle:vertical { background-color: #555; border-radius: 5px; min-height: 20px; }
            QScrollBar::handle:vertical:hover { background-color: #777; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background-color: transparent; }
            QScrollBar:horizontal { border: none; background-color: #2b2b2b; height: 10px; border-radius: 5px; }
            QScrollBar::handle:horizontal { background-color: #555; border-radius: 5px; min-width: 20px; }
            QScrollBar::handle:horizontal:hover { background-color: #777; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background-color: transparent; }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15); main_layout.setContentsMargins(20, 20, 20, 20)
        
        header_layout = QHBoxLayout()
        self.lbl_h1 = QLabel(f"<h1 style='margin:0; color:#3498DB;'>{self.h1_text}</h1>")
        header_layout.addWidget(self.lbl_h1); header_layout.addStretch()
        
        self.cb_api = QComboBox()
        self.cb_api.addItems(["리디북스", "알라딘", "코믹박스", "Google Books", "Anilist", "Vine"])
        self.cb_api.setCurrentText(self.current_api); self.cb_api.setFixedWidth(130)
        self.cb_api.setStyleSheet("padding: 6px; border: 1px solid #555; border-radius: 4px; background-color: #2b2b2b;")
        # 🌟 손가락 커서
        self.cb_api.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.le_query = QLineEdit(self.current_query)
        self.le_query.setFixedWidth(200)
        self.le_query.setStyleSheet("padding: 7px; border: 1px solid #555; border-radius: 4px; background-color: #2b2b2b;")
        self.le_query.returnPressed.connect(self.action_manual_search)
        
        # 🌟 다국어: 검색 버튼
        self.btn_search = QPushButton(self.t.get("btn_search", "검색"))
        self.btn_search.setStyleSheet("background-color: #444; color: white; border: 1px solid #555; padding: 7px 20px; border-radius: 4px; font-weight: bold;")
        self.btn_search.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_search.clicked.connect(self.action_manual_search)
        
        header_layout.addWidget(self.cb_api); header_layout.addWidget(self.le_query); header_layout.addWidget(self.btn_search)
        main_layout.addLayout(header_layout)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        left_pane = QWidget()
        left_pane.setStyleSheet("QWidget { background-color: #444; border: 1px solid #444; border-radius: 6px; }")
        left_layout = QVBoxLayout(left_pane)
        left_layout.setContentsMargins(2, 2, 2, 5) 
        
        self.list_widget = QListWidget()
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list_widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list_widget.setStyleSheet("""
            QListWidget { background-color: transparent; border: none; outline: none; }
            QListWidget::item { border-bottom: 1px solid #555; outline: none; }
            QListWidget::item:selected { background-color: #2980b9; border-radius: 4px; border: none; outline: none; }
            QListWidget::item:focus { outline: none; border: none; }
        """)
        # 🌟 리스트 위젯 영역 커서
        self.list_widget.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        self.list_widget.itemSelectionChanged.connect(self.on_item_selected)
        left_layout.addWidget(self.list_widget)
        
        # 🌟 다국어: 검색 결과 수
        self.lbl_result_count = QLabel(f"{self.t.get('search_result_prefix', '검색 결과:')} 0{self.t.get('search_result_suffix', '건')}")
        self.lbl_result_count.setStyleSheet("color: #aaa; font-size: 12px; margin-top: 5px; border: none; outline: none;")
        self.lbl_result_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(self.lbl_result_count)
        
        splitter.addWidget(left_pane)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: 1px solid #444; border-radius: 6px; background-color: #444; }")
        
        scroll_content = QWidget()
        scroll_content.setStyleSheet("background-color: #444; border: none;") 
        detail_layout = QVBoxLayout(scroll_content)
        detail_layout.setContentsMargins(15, 15, 15, 15)
        
        title_layout = QHBoxLayout()
        self.lbl_detail_title = QLabel("-")
        self.lbl_detail_title.setStyleSheet("font-size: 20px; font-weight: bold; color: white; padding-bottom: 5px;")
        self.lbl_detail_title.setWordWrap(True)
        self.lbl_detail_title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl_detail_title.setCursor(Qt.CursorShape.IBeamCursor)
        
        # 🌟 다국어: 번역 버튼
        self.btn_translate = QPushButton(self.t.get("btn_translate_web", "🌐 번역"))
        self.btn_translate.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_translate.setStyleSheet("background-color: #27AE60; color: white; padding: 5px 15px; border-radius: 4px; font-weight: bold;")
        self.btn_translate.clicked.connect(self.action_translate)
        self.btn_translate.hide()
        
        title_layout.addWidget(self.lbl_detail_title, 1) 
        title_layout.addWidget(self.btn_translate)
        detail_layout.addLayout(title_layout)
        
        line1 = QFrame(); line1.setFrameShape(QFrame.Shape.HLine); line1.setStyleSheet("color: #666;")
        detail_layout.addWidget(line1)
        
        info_layout = QHBoxLayout()
        # 🌟 다국어: 이미지 없음
        self.lbl_cover = QLabel(self.t.get("no_image", "이미지 없음"))
        self.lbl_cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_cover.setFixedSize(160, 240)
        self.lbl_cover.setStyleSheet("background-color: transparent; color: #555;")
        info_layout.addWidget(self.lbl_cover, alignment=Qt.AlignmentFlag.AlignTop)
        
        self.form_layout = QFormLayout()
        self.form_layout.setContentsMargins(15, 0, 0, 0); self.form_layout.setSpacing(10)
        
        self.detail_labels = {}
        # 🌟 다국어: 필드 라벨들
        fields_to_show = [
            ("Writer", self.t.get("meta_writer", "작가")), 
            ("Publisher", self.t.get("meta_publisher", "출판사")), 
            ("Genre", self.t.get("meta_genre", "장르")), 
            ("Count", self.t.get("meta_count", "전체권수")), 
            ("Rating", self.t.get("meta_rating", "평점")), 
            ("AgeRating", self.t.get("meta_age_rating", "연령등급")), 
            ("PubDate", self.t.get("meta_pub_date", "출간일"))
        ]
        for key, label_text in fields_to_show:
            lbl_val = QLabel("-")
            lbl_val.setWordWrap(True)
            lbl_val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            lbl_val.setStyleSheet("color: #ddd; font-size: 13px;")
            lbl_val.setCursor(Qt.CursorShape.IBeamCursor)
            
            lbl_title = QLabel(f"{label_text}")
            lbl_title.setStyleSheet("font-weight: bold; color: #aaa;")
            self.form_layout.addRow(lbl_title, lbl_val)
            self.detail_labels[key] = lbl_val
            
        info_layout.addLayout(self.form_layout)
        detail_layout.addLayout(info_layout)
        
        line2 = QFrame(); line2.setFrameShape(QFrame.Shape.HLine); line2.setStyleSheet("color: #666;")
        detail_layout.addWidget(line2)
        
        def _add_bottom_section(title):
            lbl_t = QLabel(f"{title}")
            lbl_t.setStyleSheet("font-weight: bold; color: #aaa; margin-top: 10px;")
            lbl_v = QLabel("-")
            lbl_v.setWordWrap(True)
            lbl_v.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            lbl_v.setOpenExternalLinks(True)
            lbl_v.setStyleSheet("color: #ddd; font-size: 13px; line-height: 1.5;")
            lbl_v.setCursor(Qt.CursorShape.IBeamCursor)
            
            detail_layout.addWidget(lbl_t); detail_layout.addWidget(lbl_v)
            return lbl_v

        # 🌟 다국어: 하단 라벨
        self.lbl_summary = _add_bottom_section(self.t.get("meta_summary", "줄거리"))
        self.lbl_tags = _add_bottom_section(self.t.get("meta_tags", "태그"))
        self.lbl_web = _add_bottom_section(self.t.get("meta_link", "링크"))
        
        detail_layout.addStretch()
        self.scroll_area.setWidget(scroll_content)
        splitter.addWidget(self.scroll_area)
        
        splitter.setSizes([450, 600]) 
        main_layout.addWidget(splitter, 1)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        # 🌟 다국어: 닫기 / 선택 버튼
        self.btn_close = QPushButton(self.t.get("btn_close", "닫기"))
        self.btn_close.setStyleSheet("background-color: #555; color: white; padding: 8px 25px; border-radius: 4px; font-weight: bold;")
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self.reject)
        
        self.btn_select = QPushButton(self.t.get("btn_select", "선택"))
        self.btn_select.setStyleSheet("background-color: #3498DB; color: white; padding: 8px 25px; border-radius: 4px; font-weight: bold;")
        self.btn_select.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_select.clicked.connect(self.action_apply)
        
        btn_layout.addWidget(self.btn_close); btn_layout.addWidget(self.btn_select)
        main_layout.addLayout(btn_layout)

    def action_manual_search(self):
        self.current_api = self.cb_api.currentText()
        self.current_query = self.le_query.text().strip()
        self.perform_search()

    def perform_search(self):
        raw_results = MetaApiFetcher.search(self.current_api, self.current_query, getattr(self, 'api_keys', {}))
        self.search_results = sorted(raw_results, key=lambda x: similar(self.current_query.lower(), x.get("Title", "").lower()), reverse=True)
        
        self.list_widget.clear()
        
        count = len(self.search_results)
        # 🌟 다국어: 카운트 갱신
        self.lbl_result_count.setText(f"{self.t.get('search_result_prefix', '검색 결과:')} {count}{self.t.get('search_result_suffix', '건')}")
        
        for data in self.search_results:
            item = QListWidgetItem(self.list_widget)
            widget = SearchResultWidget(data)
            item.setSizeHint(widget.sizeHint())
            self.list_widget.setItemWidget(item, widget)
            
        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def on_item_selected(self):
        selected_items = self.list_widget.selectedItems()
        if not selected_items: return
        
        row = self.list_widget.row(selected_items[0])
        self.selected_raw_data = self.search_results[row].copy()
        
        self.is_translated = False
        self.btn_translate.setText(self.t.get("btn_translate_web", "🌐 번역"))
        self.btn_translate.setStyleSheet("background-color: #27AE60; color: white; padding: 5px 15px; border-radius: 4px; font-weight: bold;")
        
        if self.current_api in ["Anilist", "Vine"]: self.btn_translate.show()
        else: self.btn_translate.hide()
            
        self.update_detail_panel()

    def update_detail_panel(self):
        if not self.selected_raw_data: return
        
        data = self.translated_data if self.is_translated else self.selected_raw_data
        
        self.lbl_detail_title.setText(data.get("Title", "-"))
        
        for key, lbl_widget in self.detail_labels.items():
            val = data.get(key, "")
            lbl_widget.setText(val if val else "-")
            
        self.lbl_summary.setText(data.get("Summary", "-") or "-")
        self.lbl_tags.setText(data.get("Tags", "-") or "-")
        
        web_link = data.get("Web", "")
        if web_link:
            self.lbl_web.setText(f"<a href='{web_link}' style='color: #3498DB;'>{web_link}</a>")
        else:
            self.lbl_web.setText("-")
        
        cover_url = data.get("CoverUrl", "")
        self.current_cover_url = cover_url 
        if cover_url:
            self.lbl_cover.setText(self.t.get("loading", "로딩 중..."))
            thread = ImageLoadThread(cover_url)
            thread.finished_data.connect(self._on_cover_loaded)
            thread.start()
        else:
            self.lbl_cover.setText(self.t.get("no_image", "이미지 없음"))
            self.lbl_cover.setPixmap(QPixmap())

    def _on_cover_loaded(self, img_data, url):
        try:
            if getattr(self, "lbl_cover", None) is None or self.current_cover_url != url: return
            if img_data:
                image = QImage.fromData(img_data)
                if not image.isNull():
                    scaled_pixmap = QPixmap.fromImage(image).scaled(
                        160, 240, 
                        Qt.AspectRatioMode.KeepAspectRatio, 
                        Qt.TransformationMode.SmoothTransformation
                    )
                    
                    rounded_pixmap = QPixmap(scaled_pixmap.size())
                    rounded_pixmap.fill(Qt.GlobalColor.transparent)
                    
                    painter = QPainter(rounded_pixmap)
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                    
                    path = QPainterPath()
                    path.addRoundedRect(0, 0, scaled_pixmap.width(), scaled_pixmap.height(), 5, 5)
                    
                    painter.setClipPath(path)
                    painter.drawPixmap(0, 0, scaled_pixmap)
                    painter.end()
                    
                    self.lbl_cover.setPixmap(rounded_pixmap)
                    return
            self.lbl_cover.setText(self.t.get("no_image", "이미지 없음"))
        except RuntimeError: pass

    def action_translate(self):
        if not self.selected_raw_data: return
        self.is_translated = not self.is_translated
        
        if self.is_translated:
            # 🌟 다국어: 원문 보기 버튼
            self.btn_translate.setText(self.t.get("btn_original_web", "🌐 원문"))
            self.btn_translate.setStyleSheet("background-color: #E67E22; color: white; padding: 5px 15px; border-radius: 4px; font-weight: bold;")
            
            self.translated_data = self.selected_raw_data.copy()
            translate_fields = ["Title", "LocalizedSeries", "Writer", "Penciller", "Publisher", "Genre", "Tags", "Summary", "Characters"]
            
            for field in translate_fields:
                if self.translated_data.get(field):
                    # 🌟 다국어: [번역됨] 접두어
                    self.translated_data[field] = f"[{self.t.get('translated_prefix', '번역됨')}] {self.translated_data[field]}"
        else:
            self.btn_translate.setText(self.t.get("btn_translate_web", "🌐 번역"))
            self.btn_translate.setStyleSheet("background-color: #27AE60; color: white; padding: 5px 15px; border-radius: 4px; font-weight: bold;")
            
        self.update_detail_panel()

    def action_apply(self):
        if not self.selected_raw_data: return
        result_data = self.translated_data if self.is_translated else self.selected_raw_data
        self.selected_raw_data = result_data
        self.accept()

    def get_selected_data(self): return self.selected_raw_data
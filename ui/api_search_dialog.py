import difflib
import requests
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, 
    QLabel, QLineEdit, QPushButton, QHeaderView, QWidget, 
    QAbstractItemView, QFormLayout, QComboBox, QSplitter, QScrollArea, QFrame
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap

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

class ApiSearchDialog(QDialog):
    def __init__(self, api_name, query, h1_text, parent=None, t=None):
        super().__init__(parent)
        self.current_api = api_name; self.current_query = query
        self.h1_text = h1_text; self.t = t if t else {}
        self.search_results = []; self.selected_raw_data = None  
        self.translated_data = None 
        self.is_translated = False; self.current_cover_url = None
        self.setWindowTitle("메타데이터 검색"); self.resize(1050, 750)
        self.setup_ui(); self.perform_search()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15); main_layout.setContentsMargins(20, 20, 20, 20)
        
        # --- 1. 최상단 헤더 ---
        header_layout = QHBoxLayout()
        # 🌟 전달받은 고정 타이틀(h1_text)을 표시
        self.lbl_h1 = QLabel(f"<h1 style='margin:0; color:#3498DB;'>{self.h1_text}</h1>")
        header_layout.addWidget(self.lbl_h1); header_layout.addStretch()
        
        self.cb_api = QComboBox()
        self.cb_api.addItems(["리디북스", "알라딘", "코믹박스", "Google Books", "Anilist", "Vine"])
        self.cb_api.setCurrentText(self.current_api); self.cb_api.setFixedWidth(130)
        self.cb_api.setStyleSheet("padding: 6px; border: 1px solid #555; border-radius: 4px; background-color: #2b2b2b;")
        
        self.le_query = QLineEdit(self.current_query)
        self.le_query.setFixedWidth(200)
        self.le_query.setStyleSheet("padding: 7px; border: 1px solid #555; border-radius: 4px; background-color: #2b2b2b;")
        self.le_query.returnPressed.connect(self.action_manual_search)
        
        self.btn_search = QPushButton("검색")
        self.btn_search.setStyleSheet("background-color: #444; color: white; border: 1px solid #555; padding: 7px 20px; border-radius: 4px; font-weight: bold;")
        self.btn_search.clicked.connect(self.action_manual_search)
        
        header_layout.addWidget(self.cb_api); header_layout.addWidget(self.le_query); header_layout.addWidget(self.btn_search)
        main_layout.addLayout(header_layout)

        # --- 2. 분할 영역 ---
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["제목", "작가", "출판사", "평점"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self.on_item_selected)
        self.table.setStyleSheet("QTableWidget { background-color: #444; border: 1px solid #444; border-radius: 6px; }")
        splitter.addWidget(self.table)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: 1px solid #444; border-radius: 6px; background-color: #444; }")
        
        scroll_content = QWidget()
        scroll_content.setStyleSheet("background-color: #444;")
        detail_layout = QVBoxLayout(scroll_content)
        detail_layout.setContentsMargins(15, 15, 15, 15)
        
        title_layout = QHBoxLayout()
        self.lbl_detail_title = QLabel("-")
        self.lbl_detail_title.setStyleSheet("font-size: 20px; font-weight: bold; color: white; padding-bottom: 5px;")
        self.lbl_detail_title.setWordWrap(True)
        self.lbl_detail_title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        
        self.btn_translate = QPushButton("🌐 번역")
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
        self.lbl_cover = QLabel("이미지 없음")
        self.lbl_cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_cover.setFixedSize(160, 240)
        self.lbl_cover.setStyleSheet("background-color: #2b2b2b; border: 1px solid #555; color: #888; border-radius: 4px;")
        info_layout.addWidget(self.lbl_cover, alignment=Qt.AlignmentFlag.AlignTop)
        
        self.form_layout = QFormLayout()
        self.form_layout.setContentsMargins(15, 0, 0, 0); self.form_layout.setSpacing(10)
        
        self.detail_labels = {}
        fields_to_show = [
            ("Writer", "작가"), ("Publisher", "출판사"), ("Genre", "장르"), 
            ("Count", "전체권수"), ("Rating", "평점"), ("AgeRating", "연령등급"), ("PubDate", "출간일")
        ]
        for key, label_text in fields_to_show:
            lbl_val = QLabel("-")
            lbl_val.setWordWrap(True); lbl_val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            lbl_val.setStyleSheet("color: #ddd; font-size: 13px;")
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
            lbl_v.setWordWrap(True); lbl_v.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            lbl_v.setStyleSheet("color: #ddd; font-size: 13px; line-height: 1.5;")
            detail_layout.addWidget(lbl_t); detail_layout.addWidget(lbl_v)
            return lbl_v

        self.lbl_summary = _add_bottom_section("줄거리")
        self.lbl_tags = _add_bottom_section("태그")
        self.lbl_web = _add_bottom_section("링크")
        
        self.lbl_web.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.lbl_web.setOpenExternalLinks(True)
        
        detail_layout.addStretch()
        self.scroll_area.setWidget(scroll_content)
        splitter.addWidget(self.scroll_area)
        
        splitter.setSizes([450, 600]) 
        main_layout.addWidget(splitter, 1)

        # --- 3. 하단 버튼 ---
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.btn_close = QPushButton("닫기")
        self.btn_close.setStyleSheet("background-color: #555; color: white; padding: 8px 25px; border-radius: 4px; font-weight: bold;")
        self.btn_close.clicked.connect(self.reject)
        self.btn_select = QPushButton("선택")
        self.btn_select.setStyleSheet("background-color: #3498DB; color: white; padding: 8px 25px; border-radius: 4px; font-weight: bold;")
        self.btn_select.clicked.connect(self.action_apply)
        btn_layout.addWidget(self.btn_close); btn_layout.addWidget(self.btn_select)
        main_layout.addLayout(btn_layout)

    def action_manual_search(self):
        self.current_api = self.cb_api.currentText()
        self.current_query = self.le_query.text().strip()
        
        # 🌟 수동 검색 시 타이틀(H1)을 검색어로 덮어쓰던 로직을 제거했습니다!
        # 이제 처음 설정된 h1_text(시리즈명 혹은 파일명)가 계속 유지됩니다.
        
        self.perform_search()

    def perform_search(self):
        raw_results = MetaApiFetcher.search(self.current_api, self.current_query)
        self.search_results = sorted(raw_results, key=lambda x: similar(self.current_query.lower(), x.get("Title", "").lower()), reverse=True)
        self.table.setRowCount(0)
        for row, data in enumerate(self.search_results):
            self.table.insertRow(row)
            
            item_title = QTableWidgetItem(data.get("Title", ""))
            
            item_writer = QTableWidgetItem(data.get("Writer", ""))
            item_writer.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            
            item_pub = QTableWidgetItem(data.get("Publisher", ""))
            item_pub.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            
            # 🌟 리스트의 평점은 RatingScore 값(예: "4.7")만 가져오도록 맵핑 유지
            item_rating = QTableWidgetItem(str(data.get("RatingScore", "")))
            item_rating.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            
            self.table.setItem(row, 0, item_title)
            self.table.setItem(row, 1, item_writer)
            self.table.setItem(row, 2, item_pub)
            self.table.setItem(row, 3, item_rating)
            
        if self.table.rowCount() > 0: self.table.selectRow(0)

    def on_item_selected(self):
        selected = self.table.selectedItems()
        if not selected: return
        
        self.selected_raw_data = self.search_results[selected[0].row()].copy()
        self.is_translated = False
        self.btn_translate.setText("🌐 번역")
        self.btn_translate.setStyleSheet("background-color: #27AE60; color: white; padding: 5px 15px; border-radius: 4px; font-weight: bold;")
        
        if self.current_api in ["Anilist", "Vine"]: 
            self.btn_translate.show()
        else: 
            self.btn_translate.hide()
            
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
            self.lbl_cover.setText("로딩 중...")
            thread = ImageLoadThread(cover_url)
            thread.finished_data.connect(self._on_cover_loaded)
            thread.start()
        else:
            self.lbl_cover.setText("이미지 없음")
            self.lbl_cover.setPixmap(QPixmap())

    def _on_cover_loaded(self, img_data, url):
        try:
            if getattr(self, "lbl_cover", None) is None or self.current_cover_url != url: return
            if img_data:
                image = QImage.fromData(img_data)
                if not image.isNull():
                    pixmap = QPixmap.fromImage(image).scaled(160, 240, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    self.lbl_cover.setPixmap(pixmap)
                    return
            self.lbl_cover.setText("이미지 없음")
        except RuntimeError: pass

    def action_translate(self):
        if not self.selected_raw_data: return
        
        self.is_translated = not self.is_translated
        
        if self.is_translated:
            self.btn_translate.setText("🌐 원문")
            self.btn_translate.setStyleSheet("background-color: #E67E22; color: white; padding: 5px 15px; border-radius: 4px; font-weight: bold;")
            
            self.translated_data = self.selected_raw_data.copy()
            translate_fields = ["Title", "LocalizedSeries", "Writer", "Penciller", "Publisher", "Genre", "Tags", "Summary", "Characters"]
            
            for field in translate_fields:
                if self.translated_data.get(field):
                    self.translated_data[field] = f"[번역됨] {self.translated_data[field]}"
        else:
            self.btn_translate.setText("🌐 번역")
            self.btn_translate.setStyleSheet("background-color: #27AE60; color: white; padding: 5px 15px; border-radius: 4px; font-weight: bold;")
            
        self.update_detail_panel()

    def action_apply(self):
        if not self.selected_raw_data: return
        result_data = self.translated_data if self.is_translated else self.selected_raw_data
        self.selected_raw_data = result_data
        self.accept()

    def get_selected_data(self): return self.selected_raw_data
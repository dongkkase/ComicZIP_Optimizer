import difflib
import requests
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, 
    QLabel, QLineEdit, QPushButton, QHeaderView, QWidget, 
    QAbstractItemView, QFormLayout, QComboBox, QSplitter, QScrollArea
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap

from core.api_fetcher import MetaApiFetcher

def similar(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio()

# 🌟 실행 중인 스레드가 강제 종료(Destroyed)되지 않도록 참조를 유지하는 전역 리스트
_active_image_threads = []

class ImageLoadThread(QThread):
    # 🌟 어떤 이미지의 결과인지 식별하기 위해 url도 함께 반환
    finished_data = pyqtSignal(bytes, str)
    
    def __init__(self, url):
        super().__init__()
        self.url = url
        _active_image_threads.append(self)
        self.finished.connect(self._cleanup)
        
    def run(self):
        try:
            if self.url:
                headers = {"User-Agent": "Mozilla/5.0"}
                resp = requests.get(self.url, headers=headers, timeout=5)
                if resp.status_code == 200:
                    self.finished_data.emit(resp.content, self.url)
                    return
        except Exception:
            pass
        self.finished_data.emit(b"", self.url)

    def _cleanup(self):
        # 다운로드가 끝나면 리스트에서 조용히 자신을 삭제
        if self in _active_image_threads:
            _active_image_threads.remove(self)

class ApiSearchDialog(QDialog):
    def __init__(self, api_name, query, h1_text, parent=None, t=None):
        super().__init__(parent)
        self.current_api = api_name
        self.current_query = query
        self.h1_text = h1_text
        self.t = t if t else {}
        self.search_results = []
        self.selected_raw_data = None  
        self.is_translated = False
        self.current_cover_url = None # 🌟 현재 보여줘야 할 표지 URL
        
        self.setWindowTitle("메타데이터 검색")
        self.resize(1000, 700)
        self.setup_ui()
        self.perform_search()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        header_layout = QHBoxLayout()
        self.lbl_h1 = QLabel(f"<h1 style='margin:0; color:#3498DB;'>{self.h1_text}</h1>")
        header_layout.addWidget(self.lbl_h1)
        header_layout.addStretch()
        
        self.cb_api = QComboBox()
        self.cb_api.addItems(["리디북스", "알라딘", "코믹박스", "Google Books", "Anilist", "Vine"])
        self.cb_api.setCurrentText(self.current_api)
        self.cb_api.setFixedWidth(130)
        self.cb_api.setStyleSheet("padding: 6px; border: 1px solid #555; border-radius: 4px; background-color: #2b2b2b;")
        
        self.le_query = QLineEdit(self.current_query)
        self.le_query.setFixedWidth(200)
        self.le_query.setStyleSheet("padding: 7px; border: 1px solid #555; border-radius: 4px; background-color: #2b2b2b; font-size: 13px;")
        self.le_query.returnPressed.connect(self.action_manual_search)
        
        self.btn_search = QPushButton("검색")
        self.btn_search.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_search.setStyleSheet("background-color: #444; color: white; border: 1px solid #555; padding: 7px 20px; border-radius: 4px; font-weight: bold;")
        self.btn_search.clicked.connect(self.action_manual_search)
        
        header_layout.addWidget(self.cb_api)
        header_layout.addWidget(self.le_query)
        header_layout.addWidget(self.btn_search)
        main_layout.addLayout(header_layout)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["제목", "작가", "출판사", "연도"])
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
        detail_layout.setSpacing(15)
        
        top_right_layout = QHBoxLayout()
        top_right_layout.addStretch()
        self.btn_translate = QPushButton("🌐 한국어로 번역")
        self.btn_translate.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_translate.setStyleSheet("background-color: #27AE60; color: white; padding: 5px 15px; border-radius: 4px; font-weight: bold;")
        self.btn_translate.clicked.connect(self.action_translate)
        self.btn_translate.hide()
        top_right_layout.addWidget(self.btn_translate)
        detail_layout.addLayout(top_right_layout)

        info_layout = QHBoxLayout()
        info_layout.setSpacing(15)
        
        self.lbl_cover = QLabel("이미지 없음")
        self.lbl_cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_cover.setFixedSize(160, 240)
        self.lbl_cover.setStyleSheet("background-color: #2b2b2b; border: 1px solid #555; color: #888; border-radius: 4px;")
        info_layout.addWidget(self.lbl_cover, alignment=Qt.AlignmentFlag.AlignTop)
        
        self.form_layout = QFormLayout()
        self.form_layout.setContentsMargins(0, 0, 0, 0)
        self.form_layout.setSpacing(12)
        
        self.detail_labels = {}
        fields_to_show = [
            ("Title", "제목"), ("Series", "시리즈"), ("Writer", "작가"), 
            ("Penciller", "그림"), ("Publisher", "출판사"), ("Year", "출판연도"),
            ("Genre", "장르"), ("Tags", "태그"), ("Characters", "등장인물")
        ]
        
        for key, label_text in fields_to_show:
            lbl_val = QLabel("-")
            lbl_val.setWordWrap(True)
            lbl_val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            lbl_val.setStyleSheet("color: #ddd; font-size: 13px;")
            
            lbl_title = QLabel(f"{label_text}:")
            lbl_title.setStyleSheet("font-weight: bold; color: #aaa;")
            self.form_layout.addRow(lbl_title, lbl_val)
            self.detail_labels[key] = lbl_val
            
        info_layout.addLayout(self.form_layout)
        detail_layout.addLayout(info_layout)
        
        lbl_summary_title = QLabel("줄거리:")
        lbl_summary_title.setStyleSheet("font-weight: bold; color: #aaa; margin-top: 10px;")
        detail_layout.addWidget(lbl_summary_title)
        
        self.lbl_summary = QLabel("-")
        self.lbl_summary.setWordWrap(True)
        self.lbl_summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl_summary.setStyleSheet("color: #ddd; font-size: 13px; line-height: 1.5;")
        detail_layout.addWidget(self.lbl_summary)
        
        detail_layout.addStretch()
        self.scroll_area.setWidget(scroll_content)
        splitter.addWidget(self.scroll_area)
        
        splitter.setSizes([450, 550])
        main_layout.addWidget(splitter, 1)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.btn_close = QPushButton("닫기")
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.setStyleSheet("background-color: #555; color: white; padding: 8px 25px; border-radius: 4px; font-weight: bold;")
        self.btn_close.clicked.connect(self.reject)
        
        self.btn_select = QPushButton("선택")
        self.btn_select.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_select.setStyleSheet("background-color: #3498DB; color: white; padding: 8px 25px; border-radius: 4px; font-weight: bold;")
        self.btn_select.clicked.connect(self.action_apply)
        
        btn_layout.addWidget(self.btn_close)
        btn_layout.addWidget(self.btn_select)
        main_layout.addLayout(btn_layout)

    def action_manual_search(self):
        self.current_api = self.cb_api.currentText()
        self.current_query = self.le_query.text().strip()
        self.is_translated = False
        self.lbl_h1.setText(f"<h1 style='margin:0; color:#3498DB;'>{self.current_query}</h1>")
        self.perform_search()

    def perform_search(self):
        raw_results = MetaApiFetcher.search(self.current_api, self.current_query)
        
        self.search_results = sorted(
            raw_results, 
            key=lambda x: similar(self.current_query.lower(), x.get("Title", "").lower()), 
            reverse=True
        )
        
        self.table.setRowCount(0)
        for row, data in enumerate(self.search_results):
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(data.get("Title", "")))
            self.table.setItem(row, 1, QTableWidgetItem(data.get("Writer", "")))
            self.table.setItem(row, 2, QTableWidgetItem(data.get("Publisher", "")))
            self.table.setItem(row, 3, QTableWidgetItem(data.get("Year", "")))
            
        if self.table.rowCount() > 0:
            self.table.selectRow(0)

    def on_item_selected(self):
        selected = self.table.selectedItems()
        if not selected: return
        row = selected[0].row()
        
        self.selected_raw_data = self.search_results[row].copy()
        
        if self.current_api in ["Anilist", "Vine"]:
            self.btn_translate.show()
        else:
            self.btn_translate.hide()
            
        self.update_detail_panel()

    def update_detail_panel(self):
        if not self.selected_raw_data: return
        data = self.selected_raw_data
        
        for key, lbl_widget in self.detail_labels.items():
            val = data.get(key, "")
            lbl_widget.setText(val if val else "-")
            
        summary = data.get("Summary", "")
        self.lbl_summary.setText(summary if summary else "줄거리 정보가 없습니다.")
        
        cover_url = data.get("CoverUrl", "")
        self.current_cover_url = cover_url # 🌟 현재 선택된 URL 저장
        
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
            # 🌟 이미 창이 닫혀서 UI 객체가 파괴되었다면 무시
            if getattr(self, "lbl_cover", None) is None:
                return
                
            # 🌟 사용자가 다른 책을 클릭해서 현재 봐야 할 URL이 달라졌다면 무시 (레이스 컨디션 방어)
            if self.current_cover_url != url:
                return
                
            if img_data:
                image = QImage.fromData(img_data)
                if not image.isNull():
                    pixmap = QPixmap.fromImage(image).scaled(
                        160, 240, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                    )
                    self.lbl_cover.setPixmap(pixmap)
                    return
            self.lbl_cover.setText("이미지 없음")
        except RuntimeError:
            pass # C++ 객체 삭제 오류 방어

    def action_translate(self):
        if not self.selected_raw_data or self.is_translated: return
        
        translate_fields = ["Writer", "Penciller", "Publisher", "Genre", "Tags", "Summary", "Characters"]
        for field in translate_fields:
            if self.selected_raw_data.get(field):
                original_text = self.selected_raw_data[field]
                self.selected_raw_data[field] = f"[번역됨] {original_text}"
                
        self.is_translated = True
        self.update_detail_panel()

    def action_apply(self):
        if not self.selected_raw_data: return
        self.accept()

    def get_selected_data(self):
        return self.selected_raw_data
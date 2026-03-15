import os
import re
import tempfile
import subprocess
import zipfile
import threading
import xml.etree.ElementTree as ET
import concurrent.futures
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit, 
    QFrame, QSizePolicy, QTreeWidgetItem, QStackedWidget, QGroupBox,
    QTextEdit, QComboBox, QGridLayout, QScrollArea, QMessageBox, QCheckBox, QLayout, QSpacerItem
)
from PyQt6.QtCore import Qt, QTimer, QSize, QRect, QPoint, QThread, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap, QPainter, QPainterPath, QColor

from utils import natural_keys
from config import get_resource_path
from ui.widgets import OrgTreeWidget

# =========================================================
# 커스텀 UI: 칩/태그 박스 레이아웃 (자동 줄바꿈)
# =========================================================
class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=4, spacing=4):
        super().__init__(parent)
        if parent is not None: self.setContentsMargins(margin, margin, margin, margin)
        self.itemList = []
        self.setSpacing(spacing)
    def __del__(self):
        item = self.takeAt(0)
        while item: item = self.takeAt(0)
    def addItem(self, item): self.itemList.append(item)
    def count(self): return len(self.itemList)
    def itemAt(self, index):
        if 0 <= index < len(self.itemList): return self.itemList[index]
        return None
    def takeAt(self, index):
        if 0 <= index < len(self.itemList): return self.itemList.pop(index)
        return None
    def expandingDirections(self): return Qt.Orientation(0)
    def hasHeightForWidth(self): return True
    def heightForWidth(self, width): return self.doLayout(QRect(0, 0, width, 0), True)
    def setGeometry(self, rect):
        super().setGeometry(rect)
        self.doLayout(rect, False)
    def sizeHint(self): return self.minimumSize()
    def minimumSize(self):
        size = QSize()
        for item in self.itemList: size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size
    def doLayout(self, rect, testOnly):
        margins = self.contentsMargins()
        effective_rect = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        
        x = effective_rect.x()
        y = effective_rect.y()
        lineHeight = 0
        spacing = self.spacing()
        
        for item in self.itemList:
            nextX = x + item.sizeHint().width() + spacing
            
            if nextX - spacing > effective_rect.right() and lineHeight > 0:
                x = effective_rect.x()
                y = y + lineHeight + spacing
                nextX = x + item.sizeHint().width() + spacing
                lineHeight = 0
                
            if not testOnly: 
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
                
            x = nextX
            lineHeight = max(lineHeight, item.sizeHint().height())
            
        return y + lineHeight - rect.y() + margins.bottom()

class TagWidget(QFrame):
    def __init__(self, text, remove_cb):
        super().__init__()
        self.text_val = text
        self.setStyleSheet("""
            QFrame { background-color: #3a7ebf; border-radius: 4px; }
            QLabel { color: white; padding: 4px 2px 4px 6px; border: none; background: transparent; font-weight: bold; font-size: 11px; }
            QPushButton { border: none; background: transparent; color: white; padding: 4px 6px 4px 2px; font-weight: bold; }
            QPushButton:hover { color: #ffcccc; }
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        lbl = QLabel(text)
        btn = QPushButton("×")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda: remove_cb(self))
        layout.addWidget(lbl)
        layout.addWidget(btn)

class TagLineEdit(QLineEdit):
    def __init__(self, parent_area, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parent_area = parent_area

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Backspace and not self.text():
            self.parent_area.remove_last_tag()
        super().keyPressEvent(event)

class TagInputArea(QFrame):
    def __init__(self, on_change_cb=None):
        super().__init__()
        self.tags = []
        self.on_change_cb = on_change_cb
        
        self.setMinimumHeight(45)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.setStyleSheet("TagInputArea { background-color: #1a1a1a; border: 1px solid #555; border-radius: 4px; }")
        
        self.flow_layout = FlowLayout(self, margin=10, spacing=8)
        
        self.line_edit = TagLineEdit(self)
        self.line_edit.setStyleSheet("background: transparent; border: none; color: white; padding-left: 2px;")
        self.line_edit.setMinimumWidth(80)
        self.line_edit.setPlaceholderText("입력 후 Enter...")
        self.line_edit.returnPressed.connect(self.add_tag_from_input)
        self.line_edit.editingFinished.connect(self.add_tag_from_input)
        self.flow_layout.addWidget(self.line_edit)

    def mousePressEvent(self, event):
        self.line_edit.setFocus()

    def add_tag_from_input(self):
        text = self.line_edit.text().strip()
        if text:
            for t in text.split(','):
                t = t.strip()
                if t and t not in self.tags: self._add_tag_ui(t)
        self.line_edit.clear()

    def _add_tag_ui(self, text):
        if text in self.tags: return
        self.tags.append(text)
        tag_widget = TagWidget(text, self.remove_tag)
        self.flow_layout.removeWidget(self.line_edit)
        self.flow_layout.addWidget(tag_widget)
        self.flow_layout.addWidget(self.line_edit)
        if self.on_change_cb: self.on_change_cb()

    def remove_tag(self, tag_widget):
        if tag_widget.text_val in self.tags:
            self.tags.remove(tag_widget.text_val)
        self.flow_layout.removeWidget(tag_widget)
        tag_widget.deleteLater()
        if self.on_change_cb: self.on_change_cb()

    def remove_last_tag(self):
        if self.tags:
            last_tag = self.tags[-1]
            for i in reversed(range(self.flow_layout.count())):
                w = self.flow_layout.itemAt(i).widget()
                if isinstance(w, TagWidget) and w.text_val == last_tag:
                    self.remove_tag(w)
                    break

    def set_tags(self, text_list):
        for i in reversed(range(self.flow_layout.count())):
            w = self.flow_layout.itemAt(i).widget()
            if w != self.line_edit:
                self.flow_layout.removeWidget(w)
                w.deleteLater()
        self.tags.clear()
        for t in text_list:
            if t: self._add_tag_ui(t)
        if self.on_change_cb: self.on_change_cb()

    def text(self): return ", ".join(self.tags)
    
    def setText(self, txt): 
        temp_cb = self.on_change_cb
        self.on_change_cb = None
        self.set_tags([x.strip() for x in txt.split(',') if x.strip()])
        self.on_change_cb = temp_cb
        if self.on_change_cb: self.on_change_cb()

# =========================================================
# 🌟 [최적화] 저장 전용 백그라운드 Worker 스레드
# =========================================================
class SaveWorker(QThread):
    progress = pyqtSignal(int, int)          
    finished_all = pyqtSignal(int, int)      
    finished_single = pyqtSignal(bool, str)  

    def __init__(self, target_dict, tab_instance, is_single=False, max_threads=4):
        super().__init__()
        self.target_dict = target_dict
        self.tab = tab_instance
        self.is_single = is_single
        self.max_threads = max_threads

    def run(self):
        if self.is_single:
            fp, data = list(self.target_dict.items())[0]
            xml_str = self.tab._create_comicinfo_xml(data)
            success, msg = self.tab._inject_xml_to_archive(fp, xml_str)
            self.finished_single.emit(success, msg)
        else:
            success_count, fail_count = 0, 0
            total = len(self.target_dict)
            current = 0
            
            def process_file(fp, data):
                xml_str = self.tab._create_comicinfo_xml(data)
                return self.tab._inject_xml_to_archive(fp, xml_str)

            # 🌟 다중 코어 활용 병렬 저장
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_threads) as executor:
                futures = {executor.submit(process_file, fp, data): fp for fp, data in self.target_dict.items()}
                for future in concurrent.futures.as_completed(futures):
                    success, _ = future.result()
                    if success: success_count += 1
                    else: fail_count += 1
                    current += 1
                    self.progress.emit(current, total)
                    
            self.finished_all.emit(success_count, fail_count)

# =========================================================
# 메인 탭 3 클래스
# =========================================================
class Tab3Metadata(QWidget):
    def __init__(self, main_app):
        super().__init__()
        self.main_app = main_app
        
        self.meta_data = {}  
        self.book_meta = {}  
        
        self.current_meta_file = None
        self.save_worker = None
        self.dynamic_series_btns = []
        
        self.cover_timer = QTimer()
        self.cover_timer.setSingleShot(True)
        self.cover_timer.timeout.connect(self._process_cover_load)
        
        self.setup_ui()

    def setup_ui(self):
        t = self.main_app.i18n[self.main_app.lang]
        
        self.meta_stacked = QStackedWidget()
        tab3_main_layout = QVBoxLayout(self)
        tab3_main_layout.setContentsMargins(0, 0, 0, 0)
        tab3_main_layout.addWidget(self.meta_stacked)

        # --- [페이지 0] 빈 화면 ---
        page_empty = QWidget()
        layout_empty = QVBoxLayout(page_empty)
        self.lbl_empty = QLabel(t["t3_empty"])
        self.lbl_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_empty.setStyleSheet("color: #aaaaaa; font-size: 16px; font-weight: bold;")
        layout_empty.addWidget(self.lbl_empty)
        self.meta_stacked.addWidget(page_empty)

        # --- [페이지 1] 메인 콘텐츠 화면 ---
        page_content = QWidget()
        layout_content = QHBoxLayout(page_content)
        layout_content.setContentsMargins(5, 5, 5, 5)

        # (좌측 패널)
        left_frame = QFrame()
        left_frame.setFixedWidth(280)
        left_frame.setObjectName("panelFrame")
        left_layout = QVBoxLayout(left_frame)

        self.lbl_meta_cover = QLabel(t["t3_cover"])
        self.lbl_meta_cover.setObjectName("imageLabel")
        self.lbl_meta_cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_meta_cover.setFixedHeight(350)
        self.lbl_meta_cover.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.tree_meta_files = OrgTreeWidget()
        self.tree_meta_files.setHeaderHidden(True)
        self.tree_meta_files.setIndentation(10) 
        self.tree_meta_files.itemSelectionChanged.connect(self.on_tree_select)
        self.tree_meta_files.delete_pressed.connect(self.remove_selected)
        
        left_layout.addWidget(self.lbl_meta_cover)
        left_layout.addWidget(self.tree_meta_files)

        # (우측 패널)
        self.right_frame = QFrame()
        right_layout = QVBoxLayout(self.right_frame)
        right_layout.setContentsMargins(10, 0, 0, 0)

        self.right_overlay = QWidget(self.right_frame)
        self.right_overlay.setStyleSheet("background: rgba(0, 0, 0, 80);")
        def overlay_click(event):
            t_now = self.main_app.i18n[self.main_app.lang]
            QMessageBox.information(self, t_now["msg_notice"], t_now["t3_msg_sel"])
            event.accept()
        self.right_overlay.mousePressEvent = overlay_click
        
        def right_frame_resize(event):
            QFrame.resizeEvent(self.right_frame, event)
            self.right_overlay.setGeometry(self.right_frame.rect())
        self.right_frame.resizeEvent = right_frame_resize

        # 1. 상단 검색 영역
        search_layout = QHBoxLayout()
        self.lbl_search_api = QLabel(t["t3_search_api"])
        search_layout.addWidget(self.lbl_search_api)
        
        self.cb_meta_api = QComboBox()
        self.cb_meta_api.addItems(["리디북스", "알라딘", "코믹박스", "Google Books"])
        self.cb_meta_api.setStyleSheet("padding: 5px; border: 1px solid #555; border-radius: 4px; background-color: #2b2b2b;")
        search_layout.addWidget(self.cb_meta_api)
        
        self.lbl_search_query = QLabel(t["t3_search_query"])
        search_layout.addWidget(self.lbl_search_query)
        
        self.le_meta_search = QLineEdit()
        self.le_meta_search.setPlaceholderText(t["t3_search_ph"])
        self.le_meta_search.setStyleSheet("padding: 6px; border: 1px solid #555; border-radius: 4px; background-color: #2b2b2b;")
        search_layout.addWidget(self.le_meta_search, 1)
        
        self.btn_meta_search = QPushButton(t["t3_btn_search"])
        self.btn_meta_search.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_meta_search.setStyleSheet("QPushButton { padding: 6px 14px; font-size: 12px; background-color: #333333; color: white; border: 1px solid #555; border-radius: 4px; } QPushButton:hover { background-color: #444444; }")
        search_layout.addWidget(self.btn_meta_search)
        right_layout.addLayout(search_layout)

        # 🌟 버튼 사전 생성 (AttributeError 방지)
        self.btn_goto_basic = QPushButton(t["t3_nav_basic"])
        self.btn_goto_crew = QPushButton(t["t3_nav_crew"])
        self.btn_goto_publish = QPushButton(t["t3_nav_publish"])
        self.btn_goto_genre = QPushButton(t["t3_nav_genre"])
        self.btn_goto_etc = QPushButton(t["t3_nav_etc"])
        
        self.btn_prev_vol = QPushButton(t["t3_btn_prev"])
        self.btn_next_vol = QPushButton(t["t3_btn_next"])
        self.btn_apply_all = QPushButton(t["t3_btn_apply_all"])
        self.btn_apply_series = QPushButton(t["t3_btn_apply_series"])

        # 🌟 툴팁 설정
        self.btn_apply_all.setToolTip(t["t3_tt_apply_all"])
        self.btn_apply_series.setToolTip(t["t3_tt_apply_series"])

        # 🌟 CSS 제너레이터: margin-top: 10px 추가
        def set_segmented_btn_style(btn, pos, is_primary=False):
            bg = "#2b5797" if is_primary else "#333333"
            hover_bg = "#366cb5" if is_primary else "#444444"
            border = "#555555"
            text_color = "#ffffff" if is_primary else "#dddddd"
            radius = "5px"
            
            style = f"""
                QPushButton {{
                    background-color: {bg};
                    color: {text_color};
                    border: 1px solid {border};
                    padding: 7px 12px;
                    font-size: 12px;
                    border-radius: 0px;
                    margin-top: 10px;
                    {'font-weight: bold;' if is_primary else ''}
                }}
                QPushButton:hover {{
                    background-color: {hover_bg};
                }}
            """
            
            if pos == "left_end":
                style += f"QPushButton {{ border-top-left-radius: {radius}; border-bottom-left-radius: {radius}; }}"
            elif pos == "right_end":
                style += f"QPushButton {{ border-top-right-radius: {radius}; border-bottom-right-radius: {radius}; }}"
            elif pos == "middle":
                style += "QPushButton { border-left: none; }"
                
            btn.setStyleSheet(style)

        # 2. 내비게이션 컨트롤 영역
        nav_layout = QHBoxLayout()
        nav_layout.setSpacing(12) 
        
        # [그룹 1] 섹션 이동 버튼
        group1_layout = QHBoxLayout()
        group1_layout.setSpacing(0)
        
        section_btns = [self.btn_goto_basic, self.btn_goto_crew, self.btn_goto_publish, self.btn_goto_genre, self.btn_goto_etc]
        for i, b in enumerate(section_btns):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            if i == 0: set_segmented_btn_style(b, "left_end")
            elif i == len(section_btns) - 1: set_segmented_btn_style(b, "right_end")
            else: set_segmented_btn_style(b, "middle")
            group1_layout.addWidget(b)
        
        # [그룹 2] 이전/다음 권 버튼 (2px 여백)
        group2_layout = QHBoxLayout()
        group2_layout.setSpacing(2)
        
        self.btn_prev_vol.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_next_vol.setCursor(Qt.CursorShape.PointingHandCursor)
        
        set_segmented_btn_style(self.btn_prev_vol, "left_end")
        set_segmented_btn_style(self.btn_next_vol, "right_end")
        
        self.btn_prev_vol.clicked.connect(self.action_prev_vol)
        self.btn_next_vol.clicked.connect(self.action_next_vol)
        group2_layout.addWidget(self.btn_prev_vol)
        group2_layout.addWidget(self.btn_next_vol)
        
        # [그룹 3] 전체 적용 버튼 (2px 여백)
        group3_layout = QHBoxLayout()
        group3_layout.setSpacing(2)
        
        self.btn_apply_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_apply_series.setCursor(Qt.CursorShape.PointingHandCursor)
        
        set_segmented_btn_style(self.btn_apply_all, "left_end")
        set_segmented_btn_style(self.btn_apply_series, "right_end", is_primary=True)
        
        self.btn_apply_all.clicked.connect(self.action_apply_all)
        self.btn_apply_series.clicked.connect(self.action_apply_series)
        group3_layout.addWidget(self.btn_apply_all)
        group3_layout.addWidget(self.btn_apply_series)

        # 레이아웃 조립
        nav_layout.addLayout(group1_layout)
        nav_layout.addStretch()
        nav_layout.addLayout(group2_layout)
        nav_layout.addStretch()
        nav_layout.addLayout(group3_layout)

        right_layout.addLayout(nav_layout)

        # 3. 메타데이터 스크롤 폼
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        scroll_layout = QVBoxLayout(self.scroll_content)
        scroll_layout.setContentsMargins(0, 0, 10, 0)
        scroll_layout.setSpacing(20)

        self.meta_ui_fields = {}

        def create_group_box(title):
            group = QGroupBox(title)
            group.setStyleSheet("QGroupBox { font-weight: bold; border: 1px solid #555; border-radius: 6px; margin-top: 15px; padding-top: 20px; background-color: #2b2b2b; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; color: #3498DB; }")
            layout = QGridLayout(group)
            layout.setContentsMargins(10, 15, 10, 10)
            layout.setSpacing(10)
            return group, layout

        def create_number_input(is_date=False, date_type=None):
            widget = QWidget()
            h_layout = QHBoxLayout(widget)
            h_layout.setContentsMargins(0,0,0,0)
            h_layout.setSpacing(2)
            
            le_num = QLineEdit()
            le_num.setAlignment(Qt.AlignmentFlag.AlignCenter)
            btn_minus = QPushButton("-")
            btn_minus.setFixedWidth(30)
            btn_plus = QPushButton("+")
            btn_plus.setFixedWidth(30)
            
            h_layout.addWidget(le_num, 1)
            h_layout.addWidget(btn_minus)
            h_layout.addWidget(btn_plus)

            def get_current():
                now = datetime.now()
                if date_type == 'Y': return now.year
                if date_type == 'M': return now.month
                if date_type == 'D': return now.day
                return 0
            def clamp(val):
                if date_type == 'Y': return max(1800, min(2100, val))
                if date_type == 'M': return max(1, min(12, val))
                if date_type == 'D': return max(1, min(31, val))
                return max(0, val)
            def decrease():
                txt = le_num.text().strip()
                val = get_current() if not txt and is_date else (int(txt) if txt else 0)
                le_num.setText(str(clamp(val - 1)))
            def increase():
                txt = le_num.text().strip()
                val = get_current() if not txt and is_date else (int(txt) if txt else 0)
                le_num.setText(str(clamp(val + 1)))
            def strip_zeros():
                txt = le_num.text().strip()
                if txt.isdigit(): le_num.setText(str(clamp(int(txt))))
                else: le_num.setText("")
                
            btn_minus.clicked.connect(decrease)
            btn_plus.clicked.connect(increase)
            le_num.editingFinished.connect(strip_zeros)
            return widget, le_num

        def add_row(layout, row, key, t_key, is_num=False, is_text=False, is_date=False, date_type=None, combo_items=None, editable_combo=False):
            lbl_widget = QLabel(t[t_key])
            lbl_widget.setAlignment(Qt.AlignmentFlag.AlignRight | (Qt.AlignmentFlag.AlignTop if is_text else Qt.AlignmentFlag.AlignVCenter))
            layout.addWidget(lbl_widget, row, 0)
            
            if is_text:
                le_my = QTextEdit(); le_my.setMinimumHeight(80)
                le_res = QTextEdit(); le_res.setMinimumHeight(80)
                
                def sync_resize():
                    h1 = le_my.document().size().height()
                    h2 = le_res.document().size().height()
                    max_h = max(80, min(500, int(max(h1, h2)) + 12))
                    le_my.setMinimumHeight(max_h)
                    le_my.setMaximumHeight(max_h)
                    le_res.setMinimumHeight(max_h)
                    le_res.setMaximumHeight(max_h)
                    
                le_my.textChanged.connect(sync_resize)
                le_res.textChanged.connect(sync_resize)
                
            elif is_num:
                le_my_widget, le_my = create_number_input(is_date=is_date, date_type=date_type)
                le_res = QLineEdit()
            elif combo_items is not None:
                le_my_widget = le_my = QComboBox()
                le_my.setEditable(editable_combo)
                le_my.addItem("", "") 
                for k, v in combo_items.items(): le_my.addItem(v, k) 
                le_res = QLineEdit()
            else:
                le_my_widget = le_my = QLineEdit()
                le_res = QLineEdit()
                
            if not is_num: le_my_widget = le_my
                
            if isinstance(le_res, QLineEdit) or isinstance(le_res, QTextEdit):
                le_res.setStyleSheet("background-color: #1a1a1a; color: #888888;")
                
            btn_map = QPushButton("<")
            btn_map.setFixedWidth(35)
            
            def do_map(checked=False):
                val = le_res.toPlainText() if it else le_res.text()
                if inum and val.isdigit(): val = str(int(val))
                
                if icombo:
                    if iedit: m.setCurrentText(val)
                    else:
                        idx = m.findText(val)
                        if idx >= 0: m.setCurrentIndex(idx)
                        else: m.setCurrentIndex(0)
                elif it: m.setPlainText(val)
                else: m.setText(val)
                
            btn_map.clicked.connect(do_map)

            layout.addWidget(le_my_widget, row, 1)
            layout.addWidget(btn_map, row, 2, alignment=Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(le_res, row, 3)
            
            self.meta_ui_fields[key] = {'my': le_my, 'res': le_res, 'is_text': is_text, 'is_combo': combo_items is not None, 'lbl': lbl_widget, 't_key': t_key}

        def add_checkbox_group(layout, start_row, key, t_key, items_dict):
            lbl_widget = QLabel(f"<b>{t[t_key]}</b>")
            lbl_widget.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
            layout.addWidget(lbl_widget, start_row, 0)
            
            cb_container = QWidget()
            cb_layout = QGridLayout(cb_container)
            cb_layout.setContentsMargins(0, 0, 0, 5)
            cb_layout.setSpacing(5)
            checkboxes = {}
            r, c = 0, 0
            
            for orig, loc in items_dict.items():
                cb = QCheckBox(loc)
                checkboxes[loc] = cb
                cb_layout.addWidget(cb, r, c)
                c += 1
                if c >= 5: 
                    c = 0; r += 1
            
            layout.addWidget(cb_container, start_row, 1, 1, 3) 
            start_row += 1
            
            le_my = TagInputArea()
            
            btn_map = QPushButton("<")
            btn_map.setFixedWidth(35)
            
            le_res = QTextEdit()
            le_res.setMaximumHeight(80)
            le_res.setStyleSheet("background-color: #1a1a1a; color: #888888;")
            
            layout.addWidget(le_my, start_row, 1)
            layout.addWidget(btn_map, start_row, 2, alignment=Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(le_res, start_row, 3)
            
            start_row += 1
            
            btn_series = QPushButton(t["t3_btn_apply_series_tag"])
            btn_series.setStyleSheet("background-color: #3a3a3a; color: #dddddd; padding: 6px; border-radius: 4px; border: 1px solid #555; font-weight: bold;")
            btn_series.setCursor(Qt.CursorShape.PointingHandCursor)
            layout.addWidget(btn_series, start_row, 1)
            self.dynamic_series_btns.append(btn_series)

            start_row += 1
            layout.addItem(QSpacerItem(10, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed), start_row, 1)

            def on_cb_changed():
                current_tags = le_my.tags.copy()
                checked_texts = [txt for txt, cb in checkboxes.items() if cb.isChecked()]
                unchecked_texts = [txt for txt, cb in checkboxes.items() if not cb.isChecked()]
                
                new_tags = []
                for tg in current_tags:
                    if tg in unchecked_texts: continue
                    if tg not in new_tags: new_tags.append(tg)
                for tg in checked_texts:
                    if tg not in new_tags: new_tags.append(tg)

                le_my.on_change_cb = None 
                le_my.set_tags(new_tags)
                le_my.on_change_cb = on_tag_changed

            def on_tag_changed():
                current_tags = le_my.tags
                for txt_loc, cb in checkboxes.items():
                    cb.blockSignals(True)
                    cb.setChecked(txt_loc in current_tags)
                    cb.blockSignals(False)

            for cb in checkboxes.values(): cb.stateChanged.connect(on_cb_changed)
            le_my.on_change_cb = on_tag_changed
            
            def do_map(checked=False):
                le_my.setText(le_res.toPlainText())
            btn_map.clicked.connect(do_map)
            
            def apply_to_series():
                if not self.current_meta_file: return
                val = le_my.text().strip()
                parent_dir = str(Path(self.current_meta_file).parent)
                if parent_dir not in self.meta_data: return
                count = 0
                for f in self.meta_data[parent_dir]:
                    fp = str(f)
                    if fp in self.book_meta:
                        self.book_meta[fp][key] = val
                        count += 1
                t_now = self.main_app.i18n[self.main_app.lang]
                QMessageBox.information(self, t_now["msg_done"], t_now["t3_msg_applied_series_tag"].format(count=count))
                
            btn_series.clicked.connect(apply_to_series)
            
            self.meta_ui_fields[key] = {'my': le_my, 'res': le_res, 'is_text': False, 'is_combo': False, 'is_tag': True, 'lbl': lbl_widget, 't_key': t_key, 'is_cb': True}
            return start_row + 1

        # =========================================================
        # 1. [기본 정보]
        # =========================================================
        self.group_basic, gl_basic = create_group_box(t["t3_nav_basic"])
        self.lbl_col_orig = QLabel(f"<b>{t['t3_col_orig']}</b>")
        self.lbl_col_res = QLabel(f"<b>{t['t3_col_res']}</b>")
        gl_basic.addWidget(self.lbl_col_orig, 0, 1, alignment=Qt.AlignmentFlag.AlignCenter)
        gl_basic.addWidget(self.lbl_col_res, 0, 3, alignment=Qt.AlignmentFlag.AlignCenter)

        add_row(gl_basic, 1, 'Title', 't3_f_title')
        add_row(gl_basic, 2, 'Series', 't3_f_series')
        add_row(gl_basic, 3, 'SeriesGroup', 't3_f_sgroup')
        add_row(gl_basic, 4, 'Count', 't3_f_count', is_num=True)
        add_row(gl_basic, 5, 'Volume', 't3_f_vol', is_num=True)
        add_row(gl_basic, 6, 'Number', 't3_f_num', is_num=True)
        add_row(gl_basic, 7, 'PageCount', 't3_f_page', is_num=True)
        add_row(gl_basic, 8, 'Summary', 't3_f_sum', is_text=True)
        scroll_layout.addWidget(self.group_basic)

        # =========================================================
        # 2. [작가 및 제작진]
        # =========================================================
        self.group_crew, gl_crew = create_group_box(t["t3_nav_crew"])
        add_row(gl_crew, 0, 'Writer', 't3_f_writer')
        add_row(gl_crew, 1, 'Penciller', 't3_f_pen')
        add_row(gl_crew, 2, 'Inker', 't3_f_inker')
        add_row(gl_crew, 3, 'Colorist', 't3_f_color')
        add_row(gl_crew, 4, 'Letterer', 't3_f_letter')
        add_row(gl_crew, 5, 'CoverArtist', 't3_f_cover')
        add_row(gl_crew, 6, 'Editor', 't3_f_editor')
        scroll_layout.addWidget(self.group_crew)

        # =========================================================
        # 3. [출판 정보]
        # =========================================================
        self.group_publish, gl_publish = create_group_box(t["t3_nav_publish"])
        add_row(gl_publish, 0, 'Publisher', 't3_f_pub')
        add_row(gl_publish, 1, 'Imprint', 't3_f_imp')
        add_row(gl_publish, 2, 'Web', 't3_f_web')
        add_row(gl_publish, 3, 'Format', 't3_f_format', combo_items=t.get("meta_formats", {}), editable_combo=True)
        add_row(gl_publish, 4, 'Year', 't3_f_year', is_num=True, is_date=True, date_type='Y')
        add_row(gl_publish, 5, 'Month', 't3_f_month', is_num=True, is_date=True, date_type='M')
        add_row(gl_publish, 6, 'Day', 't3_f_day', is_num=True, is_date=True, date_type='D')
        scroll_layout.addWidget(self.group_publish)

        # =========================================================
        # 4. [장르/태그/등장인물]
        # =========================================================
        self.group_genre_tags, gl_genre_tags = create_group_box(t["t3_nav_genre"])
        r = 0
        r = add_checkbox_group(gl_genre_tags, r, 'Genre', 't3_f_genre', t.get("meta_genres", {}))
        r = add_checkbox_group(gl_genre_tags, r, 'Tags', 't3_f_tags', t.get("meta_tags", {}))
        
        lbl_char = QLabel(t['t3_f_char'])
        lbl_char.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        gl_genre_tags.addWidget(lbl_char, r, 0)
        
        le_char_my = TagInputArea()
        
        le_char_res = QTextEdit()
        le_char_res.setMaximumHeight(80)
        le_char_res.setStyleSheet("background-color: #1a1a1a; color: #888888;")
        
        btn_char_map = QPushButton("<")
        btn_char_map.setFixedWidth(35)
        
        gl_genre_tags.addWidget(le_char_my, r, 1)
        gl_genre_tags.addWidget(btn_char_map, r, 2, alignment=Qt.AlignmentFlag.AlignCenter)
        gl_genre_tags.addWidget(le_char_res, r, 3)
        
        r += 1
        btn_char_series = QPushButton(t["t3_btn_apply_series_tag"])
        btn_char_series.setStyleSheet("background-color: #3a3a3a; color: #dddddd; padding: 6px; border-radius: 4px; border: 1px solid #555; font-weight: bold;")
        btn_char_series.setCursor(Qt.CursorShape.PointingHandCursor)
        gl_genre_tags.addWidget(btn_char_series, r, 1)
        self.dynamic_series_btns.append(btn_char_series)
        
        r += 1
        gl_genre_tags.addItem(QSpacerItem(10, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed), r, 1)
        
        btn_char_map.clicked.connect(lambda _, m=le_char_my, res=le_char_res: m.setText(res.toPlainText()))
        
        def apply_char_to_series():
            if not self.current_meta_file: return
            val = le_char_my.text().strip()
            parent_dir = str(Path(self.current_meta_file).parent)
            if parent_dir not in self.meta_data: return
            count = 0
            for f in self.meta_data[parent_dir]:
                fp = str(f)
                if fp in self.book_meta:
                    self.book_meta[fp]['Characters'] = val
                    count += 1
            t_now = self.main_app.i18n[self.main_app.lang]
            QMessageBox.information(self, t_now["msg_done"], t_now["t3_msg_applied_char_series"].format(count=count))
            
        btn_char_series.clicked.connect(apply_char_to_series)
        
        self.meta_ui_fields['Characters'] = {'my': le_char_my, 'res': le_char_res, 'is_text': False, 'is_combo': False, 'is_tag': True, 'lbl': lbl_char, 't_key': 't3_f_char'}
        scroll_layout.addWidget(self.group_genre_tags)

        # =========================================================
        # 5. [기타 정보]
        # =========================================================
        self.group_etc, gl_etc = create_group_box(t["t3_nav_etc"])
        add_row(gl_etc, 0, 'AgeRating', 't3_f_age', combo_items=t.get("meta_age", {}), editable_combo=False)
        add_row(gl_etc, 1, 'CommunityRating', 't3_f_rate') 
        add_row(gl_etc, 2, 'LanguageISO', 't3_f_iso')
        add_row(gl_etc, 3, 'Manga', 't3_f_dir', combo_items=t.get("meta_manga", {}), editable_combo=False)
        scroll_layout.addWidget(self.group_etc)
        
        scroll_layout.addStretch() 
        self.scroll_area.setWidget(self.scroll_content)
        right_layout.addWidget(self.scroll_area, 1)

        def scroll_to(w): self.scroll_area.verticalScrollBar().setValue(w.pos().y() - 10)
        self.btn_goto_basic.clicked.connect(lambda: scroll_to(self.group_basic))
        self.btn_goto_crew.clicked.connect(lambda: scroll_to(self.group_crew))
        self.btn_goto_publish.clicked.connect(lambda: scroll_to(self.group_publish))
        self.btn_goto_genre.clicked.connect(lambda: scroll_to(self.group_genre_tags))
        self.btn_goto_etc.clicked.connect(lambda: scroll_to(self.group_etc))

        # 하단 액션 버튼
        bottom_btn_layout = QHBoxLayout()
        self.btn_auto_vol = QPushButton(t["t3_auto_vol"])
        self.btn_auto_chap = QPushButton(t["t3_auto_chap"])
        self.btn_auto_pages = QPushButton(t["t3_auto_pages"])
        self.btn_meta_save = QPushButton(t["t3_save"])
        self.btn_meta_save_all = QPushButton(t["t3_save_all"])

        # 🌟 툴팁 설정
        self.btn_auto_vol.setToolTip(t["t3_tt_auto_vol"])
        self.btn_auto_chap.setToolTip(t["t3_tt_auto_chap"])
        self.btn_auto_pages.setToolTip(t["t3_tt_auto_pages"])
        self.btn_meta_save.setToolTip(t["t3_tt_save"])
        self.btn_meta_save_all.setToolTip(t["t3_tt_save_all"])
        
        for btn in [self.btn_auto_vol, self.btn_auto_chap, self.btn_auto_pages, self.btn_meta_save, self.btn_meta_save_all]:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_meta_save_all.setStyleSheet("background-color: #27AE60; color: white; font-weight: bold;")
        self.btn_meta_save.setStyleSheet("background-color: #3498DB; color: white; font-weight: bold;")
        
        self.btn_auto_vol.clicked.connect(self.action_auto_volume)
        self.btn_auto_chap.clicked.connect(self.action_auto_chapter)
        self.btn_auto_pages.clicked.connect(self.action_auto_pages)
        self.btn_meta_save.clicked.connect(self.action_save_single)
        self.btn_meta_save_all.clicked.connect(self.action_save_all)
        
        bottom_btn_layout.addWidget(self.btn_auto_vol)
        bottom_btn_layout.addWidget(self.btn_auto_chap)
        bottom_btn_layout.addWidget(self.btn_auto_pages)
        bottom_btn_layout.addStretch()
        bottom_btn_layout.addWidget(self.btn_meta_save)
        bottom_btn_layout.addWidget(self.btn_meta_save_all)
        
        right_layout.addLayout(bottom_btn_layout)

        layout_content.addWidget(left_frame)
        layout_content.addWidget(self.right_frame, 1)
        self.meta_stacked.addWidget(page_content)
        self.meta_stacked.setCurrentIndex(0)
        
        self.set_right_panel_active(False)

    def retranslate_ui(self, t, lang):
        self.lbl_empty.setText(t["t3_empty"])
        if not self.current_meta_file: self.lbl_meta_cover.setText(t["t3_cover"])
        self.lbl_search_api.setText(t["t3_search_api"])
        self.lbl_search_query.setText(t["t3_search_query"])
        self.le_meta_search.setPlaceholderText(t["t3_search_ph"])
        self.btn_meta_search.setText(t["t3_btn_search"])
        
        self.btn_goto_basic.setText(t["t3_nav_basic"])
        self.btn_goto_crew.setText(t["t3_nav_crew"])
        self.btn_goto_publish.setText(t["t3_nav_publish"])
        self.btn_goto_genre.setText(t["t3_nav_genre"])
        self.btn_goto_etc.setText(t["t3_nav_etc"])
        
        self.btn_apply_all.setText(t["t3_btn_apply_all"])
        self.btn_apply_series.setText(t["t3_btn_apply_series"])
        
        self.lbl_col_orig.setText(f"<b>{t['t3_col_orig']}</b>")
        self.lbl_col_res.setText(f"<b>{t['t3_col_res']}</b>")
        
        self.group_basic.setTitle(t["t3_nav_basic"])
        self.group_crew.setTitle(t["t3_nav_crew"])
        self.group_publish.setTitle(t["t3_nav_publish"])
        self.group_genre_tags.setTitle(t["t3_nav_genre"])
        self.group_etc.setTitle(t["t3_nav_etc"])
        
        self.btn_auto_vol.setText(t["t3_auto_vol"])
        self.btn_auto_chap.setText(t["t3_auto_chap"])
        self.btn_auto_pages.setText(t["t3_auto_pages"])
        self.btn_meta_save.setText(t["t3_save"])
        self.btn_meta_save_all.setText(t["t3_save_all"])
        
        # 🌟 다국어 툴팁 및 버튼 재설정
        self.btn_apply_all.setToolTip(t["t3_tt_apply_all"])
        self.btn_apply_series.setToolTip(t["t3_tt_apply_series"])
        self.btn_auto_vol.setToolTip(t["t3_tt_auto_vol"])
        self.btn_auto_chap.setToolTip(t["t3_tt_auto_chap"])
        self.btn_auto_pages.setToolTip(t["t3_tt_auto_pages"])
        self.btn_meta_save.setToolTip(t["t3_tt_save"])
        self.btn_meta_save_all.setToolTip(t["t3_tt_save_all"])
        
        for b in getattr(self, 'dynamic_series_btns', []):
            b.setText(t["t3_btn_apply_series_tag"])

        for key, field in self.meta_ui_fields.items():
            if field.get('is_cb'):
                field['lbl'].setText(f"<b>{t[field['t_key']]}</b>")
            else:
                field['lbl'].setText(t[field['t_key']])

    def set_right_panel_active(self, active):
        self.scroll_area.setEnabled(active)
        self.cb_meta_api.setEnabled(active)
        self.le_meta_search.setEnabled(active)
        self.btn_meta_search.setEnabled(active)
        for b in [self.btn_auto_vol, self.btn_auto_chap, self.btn_auto_pages, self.btn_meta_save, self.btn_meta_save_all]:
            b.setEnabled(active)
            
        if active: self.right_overlay.hide()
        else:
            self.right_overlay.show()
            self.right_overlay.raise_()

    def action_prev_vol(self):
        current = self.tree_meta_files.currentItem()
        if not current: return
        parent = current.parent()
        if parent:
            idx = parent.indexOfChild(current)
            if idx > 0:
                self.tree_meta_files.setCurrentItem(parent.child(idx - 1))

    def action_next_vol(self):
        current = self.tree_meta_files.currentItem()
        if not current: return
        parent = current.parent()
        if parent:
            idx = parent.indexOfChild(current)
            if idx < parent.childCount() - 1:
                self.tree_meta_files.setCurrentItem(parent.child(idx + 1))

    def load_paths(self, paths):
        t = self.main_app.i18n[self.main_app.lang]
        self.main_app.progress_bar.show()
        self.main_app.progress_bar.setRange(0, 0)
        self.main_app.lbl_status.setText(t["t3_msg_analyzing"])
        threading.Thread(target=self._bg_load_paths, args=(paths,), daemon=True).start()

    def _bg_load_paths(self, paths):
        exts = {'.zip', '.cbz', '.cbr', '.7z', '.rar'}
        scanned_files = []
        for p in paths:
            path_obj = Path(p)
            if path_obj.is_file() and path_obj.suffix.lower() in exts:
                scanned_files.append(path_obj)
            elif path_obj.is_dir():
                for sub in path_obj.rglob('*'):
                    if sub.is_file() and sub.suffix.lower() in exts and 'bak' not in sub.parts:
                        scanned_files.append(sub)

        for f in scanned_files:
            parent = str(f.parent)
            if parent not in self.meta_data:
                self.meta_data[parent] = []
            if f not in self.meta_data[parent]:
                self.meta_data[parent].append(f)
                
            fp = str(f)
            if fp not in self.book_meta:
                self.book_meta[fp] = {key: "" for key in self.meta_ui_fields.keys()}
                self.book_meta[fp]['Title'] = f.stem
                
                xml_data = self._read_xml_from_archive(fp)
                if xml_data:
                    for k, v in xml_data.items():
                        if k in self.book_meta[fp] or k in ['ComicZipAddedDate', 'ComicZipModifiedDate']:
                            self.book_meta[fp][k] = v

        QTimer.singleShot(0, self._on_bg_load_finished)

    def _on_bg_load_finished(self):
        self.main_app.progress_bar.hide()
        self.main_app.progress_bar.setRange(0, 100)
        self.main_app.lbl_status.setText(self.main_app.i18n[self.main_app.lang]["status_wait"])
        self.refresh_tree()

    def _read_xml_from_archive(self, fp):
        ext = Path(fp).suffix.lower()
        xml_str = None
        if ext in ['.zip', '.cbz']:
            try:
                with zipfile.ZipFile(fp, 'r') as zf:
                    target = next((n for n in zf.namelist() if n.lower() == 'comicinfo.xml'), None)
                    if target: xml_str = zf.read(target).decode('utf-8')
            except: pass
        else:
            try:
                cmd = [self.main_app.seven_zip_path, 'e', fp, 'ComicInfo.xml', '-so']
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
                if res.returncode == 0: xml_str = res.stdout.decode('utf-8', errors='ignore')
            except: pass

        if xml_str:
            try:
                root = ET.fromstring(xml_str)
                return {child.tag: child.text for child in root if child.text}
            except: pass
        return None

    def refresh_tree(self):
        t = self.main_app.i18n[self.main_app.lang]
        self.tree_meta_files.clear()
        if not self.meta_data:
            self.meta_stacked.setCurrentIndex(0)
            self.set_right_panel_active(False)
            return
            
        self.meta_stacked.setCurrentIndex(1)
        self.set_right_panel_active(False)
        
        for folder_path, files in self.meta_data.items():
            folder_name = os.path.basename(folder_path) or folder_path
            root_item = QTreeWidgetItem([f"📁 {folder_name}"])
            self.tree_meta_files.addTopLevelItem(root_item)
            
            sorted_files = sorted(files, key=lambda x: natural_keys(x.name))
            
            for f in sorted_files:
                fp = str(f)
                b_meta = self.book_meta.get(fp, {})
                
                # 🌟 파일명으로 표기 
                title = f.name 
                mod_date = b_meta.get('ComicZipModifiedDate')
                
                child_item = QTreeWidgetItem()
                child_item.setData(0, Qt.ItemDataRole.UserRole, fp)
                child_item.setToolTip(0, title) 
                root_item.addChild(child_item)
                
                item_widget = QWidget()
                item_widget.setStyleSheet("background: transparent;")
                item_layout = QVBoxLayout(item_widget)
                item_layout.setContentsMargins(4, 2, 4, 2)
                item_layout.setSpacing(1)
                
                lbl_title = QLabel(f"📄 {title}")
                lbl_title.setStyleSheet("color: #ffffff; font-size: 13px; margin-bottom:0;")
                lbl_title.setWordWrap(True) 
                
                date_str = f"🕒 {mod_date}" if mod_date else t["t3_no_data"]
                lbl_date = QLabel(date_str)
                lbl_date.setStyleSheet("color: #aaaaaa; font-size: 10px; margin-left:20px; margin-top:0;") 
                
                item_layout.addWidget(lbl_title)
                item_layout.addWidget(lbl_date)
                
                child_item.setSizeHint(0, QSize(200, 48))
                self.tree_meta_files.setItemWidget(child_item, 0, item_widget)
                
        self.tree_meta_files.expandAll()
        
        if self.tree_meta_files.topLevelItemCount() > 0:
            first_root = self.tree_meta_files.topLevelItem(0)
            if first_root.childCount() > 0:
                self.tree_meta_files.setCurrentItem(first_root.child(0))

    def on_tree_select(self):
        self._save_ui_to_dict()
        selected = self.tree_meta_files.selectedItems()
        if not selected: 
            self.set_right_panel_active(False)
            return
            
        fp = selected[0].data(0, Qt.ItemDataRole.UserRole)
        if not fp: 
            self.set_right_panel_active(False)
            return
        
        self.set_right_panel_active(True)
        self.current_meta_file = fp
        self._load_dict_to_ui(fp)
        self.cover_timer.start(150)

    def _process_cover_load(self):
        if not self.current_meta_file: return
        fp = self.current_meta_file
        target_img = None
        ext = Path(fp).suffix.lower()
        
        if ext in ['.zip', '.cbz']:
            try:
                with zipfile.ZipFile(fp, 'r') as zf:
                    entries = [info.filename for info in zf.infolist() if not info.is_dir() and Path(info.filename).suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}]
                    entries.sort(key=natural_keys)
                    cover = next((e for e in entries if os.path.basename(e).lower().startswith('cover')), None)
                    target_img = cover if cover else (entries[0] if entries else None)
            except: pass
        else:
            try:
                from tasks.load_task import FileLoadTask
                task = FileLoadTask([], self.main_app.seven_zip_path, self.main_app.lang, self.main_app.signals)
                entries = [e['filename'] for e in task.get_7z_entries(fp) if Path(e['filename']).suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}]
                entries.sort(key=natural_keys)
                cover = next((e for e in entries if os.path.basename(e).lower().startswith('cover')), None)
                target_img = cover if cover else (entries[0] if entries else None)
            except: pass
            
        if target_img:
            from core.archive_utils import bg_load_image
            threading.Thread(target=bg_load_image, args=(fp, target_img, ext, "cover", self.main_app.seven_zip_path, self.main_app.signals), daemon=True).start()
        else:
            self.render_image("cover", None)

    def render_image(self, target_id, img_data):
        label_widget = self.lbl_meta_cover
        cw = max(200, label_widget.width() - 10)
        ch = 340
        t = self.main_app.i18n[self.main_app.lang]
        
        if not img_data:
            p = get_resource_path("previewframe.png")
            if os.path.exists(p):
                try:
                    with open(p, "rb") as f: img_data = f.read()
                except: pass
        if not img_data:
            label_widget.setText(t["no_preview"])
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
            label_widget.setText(t["no_image"])

    def _save_ui_to_dict(self):
        if self.current_meta_file and self.current_meta_file in self.book_meta:
            for key, field in self.meta_ui_fields.items():
                if field.get('is_combo'): val = field['my'].currentText()
                elif field.get('is_text'): val = field['my'].toPlainText()
                elif field.get('is_tag'): val = field['my'].text()
                else: val = field['my'].text()
                self.book_meta[self.current_meta_file][key] = val

    def _load_dict_to_ui(self, fp):
        data = self.book_meta.get(fp, {})
        for key, field in self.meta_ui_fields.items():
            val = data.get(key, "")
            if field.get('is_combo'):
                if field['my'].isEditable(): field['my'].setCurrentText(val)
                else:
                    idx = field['my'].findText(val)
                    if idx >= 0: field['my'].setCurrentIndex(idx)
                    else: field['my'].setCurrentIndex(0)
            elif field.get('is_text'): field['my'].setPlainText(val)
            elif field.get('is_tag'): field['my'].setText(val)
            else: field['my'].setText(val)

    def action_apply_all(self):
        for key, field in self.meta_ui_fields.items():
            res_widget = field['res']
            val = res_widget.toPlainText() if isinstance(res_widget, QTextEdit) else res_widget.text()
            val = val.strip()
            
            if val: 
                if field.get('is_combo'):
                    if field['my'].isEditable(): field['my'].setCurrentText(val)
                    else:
                        idx = field['my'].findText(val)
                        if idx >= 0: field['my'].setCurrentIndex(idx)
                elif field.get('is_text'): field['my'].setPlainText(val)
                elif field.get('is_tag'): field['my'].setText(val)
                else: field['my'].setText(val)

    def action_apply_series(self):
        t = self.main_app.i18n[self.main_app.lang]
        if not self.current_meta_file: return
        self._save_ui_to_dict() 
        
        parent_dir = str(Path(self.current_meta_file).parent)
        if parent_dir not in self.meta_data: return
        
        exclude_keys = {'Volume', 'Number', 'PageCount'}
        results_to_copy = {}
        for key, field in self.meta_ui_fields.items():
            if key not in exclude_keys:
                res_widget = field['res']
                val = res_widget.toPlainText() if isinstance(res_widget, QTextEdit) else res_widget.text()
                val = val.strip()
                if val: 
                    results_to_copy[key] = val
                
        if not results_to_copy:
            QMessageBox.information(self, t["msg_notice"], t["t3_msg_no_data_copy"])
            return

        files_in_series = self.meta_data[parent_dir]
        for f in files_in_series:
            fp = str(f)
            if fp in self.book_meta:
                for k, v in results_to_copy.items():
                    self.book_meta[fp][k] = v
                    
        self._load_dict_to_ui(self.current_meta_file)
        QMessageBox.information(self, t["msg_done"], t["t3_msg_applied_series_all"])

    def action_auto_volume(self):
        t = self.main_app.i18n[self.main_app.lang]
        if not self.current_meta_file: return
        parent_dir = str(Path(self.current_meta_file).parent)
        for f in self.meta_data.get(parent_dir, []):
            fp = str(f)
            title = f.name
            match = re.search(r'(?i)(?:vol\.|v\.|권)\s*(\d+)', title) or re.search(r'(\d+)\s*권', title) or re.search(r'\b(\d+)\s*$', title.strip())
            if match: self.book_meta[fp]['Volume'] = str(int(match.group(1)))
        self._load_dict_to_ui(self.current_meta_file)
        QMessageBox.information(self, t["msg_done"], t["t3_msg_auto_vol_done"])

    def action_auto_chapter(self):
        t = self.main_app.i18n[self.main_app.lang]
        if not self.current_meta_file: return
        parent_dir = str(Path(self.current_meta_file).parent)
        for f in self.meta_data.get(parent_dir, []):
            fp = str(f)
            title = f.name
            match = re.search(r'(?i)(?:ch\.|chapter|화)\s*(\d+)', title) or re.search(r'(\d+)\s*화', title)
            if match: self.book_meta[fp]['Number'] = str(int(match.group(1)))
        self._load_dict_to_ui(self.current_meta_file)
        QMessageBox.information(self, t["msg_done"], t["t3_msg_auto_chap_done"])

    def action_auto_pages(self):
        t = self.main_app.i18n[self.main_app.lang]
        if not self.current_meta_file: return
        parent_dir = str(Path(self.current_meta_file).parent)
        for f in self.meta_data.get(parent_dir, []):
            fp = str(f)
            ext = f.suffix.lower()
            img_count = 0
            if ext in ['.zip', '.cbz']:
                try:
                    with zipfile.ZipFile(fp, 'r') as zf:
                        img_count = sum(1 for info in zf.infolist() if not info.is_dir() and Path(info.filename).suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp', '.bmp'})
                except: pass
            if img_count > 0:
                self.book_meta[fp]['PageCount'] = str(img_count)
                
        self._load_dict_to_ui(self.current_meta_file)
        QMessageBox.information(self, t["msg_done"], t["t3_msg_auto_pages_done"])

    def remove_selected(self):
        selected_items = self.tree_meta_files.selectedItems()
        if not selected_items: return
        
        first_selected = selected_items[0]
        parent = first_selected.parent() or first_selected
        top_idx = self.tree_meta_files.indexOfTopLevelItem(parent)
        child_idx = parent.indexOfChild(first_selected) if first_selected.parent() else 0
        
        fps_to_remove = set()
        for item in selected_items:
            fp = item.data(0, Qt.ItemDataRole.UserRole)
            if fp: fps_to_remove.add(fp)
            else: 
                for i in range(item.childCount()):
                    child_fp = item.child(i).data(0, Qt.ItemDataRole.UserRole)
                    if child_fp: fps_to_remove.add(child_fp)
                    
        if not fps_to_remove: return
        
        for fp in fps_to_remove:
            parent_dir = str(Path(fp).parent)
            if parent_dir in self.meta_data:
                self.meta_data[parent_dir] = [x for x in self.meta_data[parent_dir] if str(x) != fp]
                if not self.meta_data[parent_dir]:
                    del self.meta_data[parent_dir]
            if fp in self.book_meta:
                del self.book_meta[fp]
                
        if self.current_meta_file in fps_to_remove:
            self.current_meta_file = None
            self.lbl_meta_cover.setPixmap(QPixmap())
            self.lbl_meta_cover.setText(self.main_app.i18n[self.main_app.lang]["t3_cover"])
            for key, field in self.meta_ui_fields.items():
                if field.get('is_combo'): field['my'].setCurrentText("")
                elif field.get('is_text'): field['my'].setPlainText("")
                elif field.get('is_tag'): field['my'].setText("")
                else: field['my'].setText("")
            self.set_right_panel_active(False)
                
        self.refresh_tree()
        
        total_top = self.tree_meta_files.topLevelItemCount()
        if total_top > 0:
            valid_top_idx = min(top_idx, total_top - 1)
            new_parent = self.tree_meta_files.topLevelItem(valid_top_idx)
            
            if new_parent.childCount() > 0:
                valid_child_idx = min(child_idx, new_parent.childCount() - 1)
                self.tree_meta_files.setCurrentItem(new_parent.child(valid_child_idx))
            else:
                self.tree_meta_files.setCurrentItem(new_parent)

    def clear_list(self):
        self.meta_data.clear()
        self.book_meta.clear()
        self.current_meta_file = None
        self.lbl_meta_cover.setPixmap(QPixmap())
        self.lbl_meta_cover.setText(self.main_app.i18n[self.main_app.lang]["t3_cover"])
        self.refresh_tree()
        self.set_right_panel_active(False)

    def _create_comicinfo_xml(self, data):
        root = ET.Element('ComicInfo', attrib={'xmlns:xsi': 'http://www.w3.org/2001/XMLSchema-instance', 'xmlns:xsd': 'http://www.w3.org/2001/XMLSchema'})
        for k, v in data.items():
            if v and k not in ['ComicZipAddedDate', 'ComicZipModifiedDate']:
                ET.SubElement(root, k).text = str(v)
                
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if 'ComicZipAddedDate' not in data or not data['ComicZipAddedDate']:
            ET.SubElement(root, 'ComicZipAddedDate').text = now_str
        else:
            ET.SubElement(root, 'ComicZipAddedDate').text = data['ComicZipAddedDate']
        ET.SubElement(root, 'ComicZipModifiedDate').text = now_str
        
        data['ComicZipAddedDate'] = ET.SubElement(root, 'ComicZipAddedDate').text
        data['ComicZipModifiedDate'] = now_str

        return '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding='utf-8').decode('utf-8')

    # 🌟 속도 개선: 7z에 -mx=0 옵션 추가
    def _inject_xml_to_archive(self, archive_path, xml_str):
        t = self.main_app.i18n[self.main_app.lang]
        ext = Path(archive_path).suffix.lower()
        if ext not in ['.zip', '.cbz', '.7z']: return False, t["t3_msg_unsupported_format"]
            
        with tempfile.TemporaryDirectory() as tmp_dir:
            xml_path = os.path.join(tmp_dir, "ComicInfo.xml")
            with open(xml_path, "w", encoding="utf-8") as f:
                f.write(xml_str)
            cmd = [self.main_app.seven_zip_path, 'u', archive_path, "ComicInfo.xml", "-mx=0"]
            try:
                res = subprocess.run(cmd, cwd=tmp_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
                if res.returncode == 0: return True, t["msg_success"]
                else: return False, t["t3_msg_7z_error"]
            except Exception as e: return False, str(e)

    # 🌟 속도 개선: 단일/모두 저장 백그라운드 Worker 연결
    def action_save_single(self):
        t = self.main_app.i18n[self.main_app.lang]
        if not self.current_meta_file: return
        self._save_ui_to_dict()
        fp = self.current_meta_file

        self.set_right_panel_active(False)
        self.main_app.progress_bar.show()
        self.main_app.progress_bar.setRange(0, 0)
        self.main_app.lbl_status.setText(t["t3_msg_saving"])

        targets = {fp: self.book_meta[fp]}
        self.save_worker = SaveWorker(targets, self, is_single=True)
        self.save_worker.finished_single.connect(self._on_save_single_finished)
        self.save_worker.start()

    def _on_save_single_finished(self, success, msg):
        t = self.main_app.i18n[self.main_app.lang]
        self.main_app.progress_bar.hide()
        self.main_app.lbl_status.setText(t["status_wait"])
        
        if success: 
            QMessageBox.information(self, t["msg_done"], t["t3_msg_save_single_done"])
            self.refresh_tree() 
        else: 
            QMessageBox.warning(self, t["msg_failed"], t["t3_msg_save_failed_reason"].format(msg=msg))
            self.set_right_panel_active(True)

    def action_save_all(self):
        t = self.main_app.i18n[self.main_app.lang]
        self._save_ui_to_dict()
        
        targets = {fp: data for fp, data in self.book_meta.items() if os.path.exists(fp)}
        if not targets:
            QMessageBox.information(self, t["msg_notice"], t["t3_msg_no_data_copy"])
            return

        self.set_right_panel_active(False)
        self.main_app.progress_bar.show()
        self.main_app.progress_bar.setRange(0, len(targets))
        self.main_app.progress_bar.setValue(0)
        self.main_app.lbl_status.setText(t["t3_msg_saving"])

        max_threads = self.main_app.config.get("max_threads", 4)
        self.save_worker = SaveWorker(targets, self, is_single=False, max_workers=max_threads)
        self.save_worker.progress.connect(self._on_save_progress)
        self.save_worker.finished_all.connect(self._on_save_all_finished)
        self.save_worker.start()

    def _on_save_progress(self, current, total):
        self.main_app.progress_bar.setValue(current)

    def _on_save_all_finished(self, success_count, fail_count):
        t = self.main_app.i18n[self.main_app.lang]
        self.main_app.progress_bar.hide()
        self.main_app.lbl_status.setText(t["status_wait"])
        
        msg = t["t3_msg_save_all_done"].format(success_count=success_count, fail_count=fail_count)
        QMessageBox.information(self, t["t3_msg_save_all_title"], msg)
        self.refresh_tree()
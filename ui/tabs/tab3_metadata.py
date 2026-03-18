import os
import re
import tempfile
import subprocess
import zipfile
import threading
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from ui.api_search_dialog import ApiSearchDialog

import qtawesome as qta

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit, 
    QFrame, QSizePolicy, QTreeWidgetItem, QStackedWidget, QGroupBox,
    QTextEdit, QComboBox, QGridLayout, QScrollArea, QMessageBox, QCheckBox, 
    QSpacerItem, QApplication, QAbstractItemView
)
from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QImage, QPixmap, QPainter, QPainterPath, QKeySequence, QShortcut

from utils import natural_keys
from config import get_resource_path
from ui.widgets import OrgTreeWidget, Toast
from core.api_fetcher import MetaApiFetcher

from ui.tag_widgets import TagInputArea
from tasks.save_task import SaveWorker

class Tab3Metadata(QWidget):
    def __init__(self, main_app):
        super().__init__()
        self.main_app = main_app
        self.meta_data = {}  
        self.book_meta = {}  
        self.current_meta_file = None
        self.dynamic_series_btns = [] 
        self.save_worker = None
        
        self.cover_timer = QTimer()
        self.cover_timer.setSingleShot(True)
        self.cover_timer.timeout.connect(self._process_cover_load)
        
        self.setup_ui()

    def update_icons(self, is_dark):
        icon_color = 'white' if is_dark else '#1F2937'
        empty_c = "#aaaaaa" if is_dark else "#9CA3AF"
        
        self.icon_empty_meta.setPixmap(qta.icon('fa5s.folder-open', color=empty_c).pixmap(64, 64))
        self.btn_meta_search.setIcon(qta.icon('fa5s.search', color='white'))
        self.btn_prev_vol.setIcon(qta.icon('fa5s.caret-left', color=icon_color))
        self.btn_next_vol.setIcon(qta.icon('fa5s.caret-right', color=icon_color))
        
        self.btn_reset_series.setIcon(qta.icon('fa5s.undo', color=icon_color))
        self.btn_copy_orig.setIcon(qta.icon('fa5s.copy', color=icon_color))
        self.btn_apply_all.setIcon(qta.icon('fa5s.check', color=icon_color))
        self.btn_apply_series.setIcon(qta.icon('fa5s.layer-group', color='white')) 
        
        self.btn_auto_match.setIcon(qta.icon('fa5s.magic', color='white'))
        self.btn_meta_save.setIcon(qta.icon('fa5s.save', color='white'))
        self.btn_meta_save_all.setIcon(qta.icon('fa5s.save', color='white'))
        
        self.update_nav_buttons_state(self._current_active_nav_btn)

        
    def update_theme(self):
        self.update_nav_buttons_state(self._current_active_nav_btn)

    def setup_ui(self):
        t = self.main_app.i18n[self.main_app.lang]
        
        self.meta_stacked = QStackedWidget()
        tab3_main_layout = QVBoxLayout(self)
        tab3_main_layout.setContentsMargins(0, 0, 0, 0)
        tab3_main_layout.addWidget(self.meta_stacked)

        self._setup_empty_page(t)
        self._setup_content_page(t)
        
        self.meta_stacked.setCurrentIndex(0)
        self.set_right_panel_active(False)
        self._setup_shortcuts()

    def _setup_empty_page(self, t):
        page_empty = QWidget()
        layout_empty = QVBoxLayout(page_empty)
        self.icon_empty_meta = QLabel()
        self.icon_empty_meta.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_empty = QLabel(t.get("t3_empty", "폴더 및 파일을 이 화면으로 드래그 앤 드롭하세요"))
        self.lbl_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_empty.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout_empty.addStretch()
        layout_empty.addWidget(self.icon_empty_meta)
        layout_empty.addWidget(self.lbl_empty)
        layout_empty.addStretch()
        self.meta_stacked.addWidget(page_empty)

    def _setup_content_page(self, t):
        page_content = QWidget()
        layout_content = QHBoxLayout(page_content)
        layout_content.setContentsMargins(5, 5, 5, 5)

        self._setup_left_panel(layout_content, t)
        
        self.right_frame = QFrame()
        right_layout = QVBoxLayout(self.right_frame)
        right_layout.setContentsMargins(10, 0, 0, 0)

        self.right_overlay = QWidget(self.right_frame)
        self.right_overlay.setStyleSheet("background: rgba(0, 0, 0, 80);")
        self.right_overlay.mousePressEvent = lambda e: (QMessageBox.information(self, t.get("msg_notice", "안내"), t.get("t3_msg_sel", "왼쪽 리스트에서 작업할 책을 선택해주세요.")), e.accept())
        
        def right_frame_resize(event):
            QFrame.resizeEvent(self.right_frame, event)
            self.right_overlay.setGeometry(self.right_frame.rect())
        self.right_frame.resizeEvent = right_frame_resize

        self._setup_search_panel(right_layout, t)
        self._setup_nav_panel(right_layout, t)
        self._setup_scroll_area(right_layout, t)
        self._setup_bottom_buttons(right_layout, t)

        layout_content.addWidget(self.right_frame, 1)
        self.meta_stacked.addWidget(page_content)

    def _setup_left_panel(self, layout_content, t):
        left_frame = QFrame()
        left_frame.setFixedWidth(280)
        left_frame.setObjectName("panelFrame")
        left_layout = QVBoxLayout(left_frame)

        self.lbl_meta_cover = QLabel(t.get("t3_cover", "표지 미리보기"))
        self.lbl_meta_cover.setObjectName("imageLabel")
        self.lbl_meta_cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_meta_cover.setFixedHeight(350)
        self.lbl_meta_cover.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.tree_meta_files = OrgTreeWidget()
        self.tree_meta_files.setHeaderHidden(True)
        self.tree_meta_files.setIndentation(10) 
        self.tree_meta_files.itemSelectionChanged.connect(self.on_tree_select)
        self.tree_meta_files.delete_pressed.connect(self.remove_selected)
        self.tree_meta_files.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.tree_meta_files.verticalScrollBar().setSingleStep(15)
        
        left_layout.addWidget(self.lbl_meta_cover)
        left_layout.addWidget(self.tree_meta_files)
        layout_content.addWidget(left_frame)

    def _setup_search_panel(self, right_layout, t):
        search_layout = QHBoxLayout()
        self.lbl_search_api = QLabel(t.get("t3_search_api", "검색 API :"))
        search_layout.addWidget(self.lbl_search_api)
        
        self.cb_meta_api = QComboBox()
        self.cb_meta_api.addItems(["리디북스", "알라딘", "Google Books", "Anilist", "Vine"])
        last_api = self.main_app.config.get("last_meta_api", "리디북스")
        idx = self.cb_meta_api.findText(last_api)
        if idx >= 0: self.cb_meta_api.setCurrentIndex(idx)
        
        def on_meta_api_changed(text):
            self.main_app.config["last_meta_api"] = text
            try:
                from config import save_config
                save_config(self.main_app.config)
            except: pass
        self.cb_meta_api.currentTextChanged.connect(on_meta_api_changed)

        search_layout.addWidget(self.cb_meta_api)
        self.lbl_search_query = QLabel(t.get("t3_search_query", "검색어 :"))
        search_layout.addWidget(self.lbl_search_query)
        
        self.le_meta_search = QLineEdit()
        self.le_meta_search.setPlaceholderText(t.get("t3_search_ph", "작품 제목을 입력하세요..."))
        search_layout.addWidget(self.le_meta_search, 1)
        
        self.btn_meta_search = QPushButton(f" {t.get('btn_search', '검색')} (S)")
        self.btn_meta_search.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_meta_search.setObjectName("actionBtnBlue") 
        search_layout.addWidget(self.btn_meta_search)
        self.btn_meta_search.clicked.connect(self.action_search_api) 
        self.le_meta_search.returnPressed.connect(self.action_search_api)
        right_layout.addLayout(search_layout)

    def _setup_nav_panel(self, right_layout, t):
        self.btn_goto_basic = QPushButton(t.get("t3_nav_basic", "기본\n정보"))
        self.btn_goto_crew = QPushButton(t.get("t3_nav_crew", "작가 및\n제작진"))
        self.btn_goto_publish = QPushButton(t.get("t3_nav_publish", "출판\n정보"))
        self.btn_goto_genre = QPushButton(t.get("t3_nav_genre", "장르/태그\n등장인물"))
        self.btn_goto_etc = QPushButton(t.get("t3_nav_etc", "기타\n정보"))
        
        self.btn_prev_vol = QPushButton(t.get("t3_btn_prev", "이전 권"))
        self.btn_next_vol = QPushButton(t.get("t3_btn_next", "다음 권"))
        self.btn_next_vol.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        
        self.btn_reset_series = QPushButton(t.get("t3_btn_reset_series", "시리즈\n초기화"))
        self.btn_copy_orig = QPushButton(t.get("t3_btn_copy_orig", "원본\n카피 편집"))
        self.btn_apply_all = QPushButton(t.get("t3_btn_apply_all", "편집\n적용"))
        self.btn_apply_series = QPushButton(f"{t.get('t3_btn_apply_series', '시리즈\n편집 적용')} (C)")
        self.btn_apply_series.setObjectName("actionBtnBlue")

        self.btn_reset_series.setToolTip(t.get("t3_tt_reset_series", ""))
        self.btn_copy_orig.setToolTip(t.get("t3_tt_copy_orig", ""))
        self.btn_apply_all.setToolTip(t.get("t3_tt_apply_all", ""))
        self.btn_apply_series.setToolTip(t.get("t3_tt_apply_series", ""))

        def set_segmented_btn_style(btn, pos, is_primary=False, is_active=False):
            is_dark = getattr(self.main_app, 'is_dark_mode', True)
            if is_dark:
                bg = "#3498DB" if is_active else ("#2b5797" if is_primary else "#374151")
                hover_bg = "#2980B9" if is_active else ("#366cb5" if is_primary else "#4B5563")
                border = "#4B5563"
                text_color = "#ffffff" if (is_primary or is_active) else "#E5E7EB"
            else:
                bg = "#3498DB" if is_active else ("#2b5797" if is_primary else "#FFFFFF")
                hover_bg = "#2980B9" if is_active else ("#366cb5" if is_primary else "#F3F4F6")
                border = "#D1D5DB"
                text_color = "#ffffff" if (is_primary or is_active) else "#374151"
                
            radius = "5px"
            style = f"QPushButton {{ background-color: {bg}; color: {text_color}; border: 1px solid {border}; padding: 5px 8px; font-size: 11px; border-radius: 0px; margin-top: 10px; {'font-weight: bold;' if (is_primary or is_active) else ''} }} QPushButton:hover {{ background-color: {hover_bg}; }}"
            if pos == "left_end": style += f"QPushButton {{ border-top-left-radius: {radius}; border-bottom-left-radius: {radius}; }}"
            elif pos == "right_end": style += f"QPushButton {{ border-top-right-radius: {radius}; border-bottom-right-radius: {radius}; }}"
            elif pos == "middle": style += "QPushButton { border-left: none; }"
            btn.setStyleSheet(style)
            
        self.set_segmented_btn_style = set_segmented_btn_style

        nav_layout = QHBoxLayout(); nav_layout.setSpacing(12) 
        group1_layout = QHBoxLayout(); group1_layout.setSpacing(0)
        
        self.section_btns = [self.btn_goto_basic, self.btn_goto_crew, self.btn_goto_publish, self.btn_goto_genre, self.btn_goto_etc]
        for b in self.section_btns:
            b.setCursor(Qt.CursorShape.PointingHandCursor); group1_layout.addWidget(b)
            
        self._current_active_nav_btn = None
        def update_nav_buttons_state(active_btn):
            if getattr(self, '_current_active_nav_btn', None) == active_btn: return
            self._current_active_nav_btn = active_btn
            for i, b in enumerate(self.section_btns):
                is_active = (b == active_btn); pos = "middle"
                if i == 0: pos = "left_end"
                elif i == len(self.section_btns) - 1: pos = "right_end"
                self.set_segmented_btn_style(b, pos, is_active=is_active)
                
        self.update_nav_buttons_state = update_nav_buttons_state
        self.update_nav_buttons_state(self.btn_goto_basic)
        
        group2_layout = QHBoxLayout(); group2_layout.setSpacing(2)
        self.btn_prev_vol.setCursor(Qt.CursorShape.PointingHandCursor); self.btn_next_vol.setCursor(Qt.CursorShape.PointingHandCursor)
        self.set_segmented_btn_style(self.btn_prev_vol, "left_end"); self.set_segmented_btn_style(self.btn_next_vol, "right_end")
        self.btn_prev_vol.clicked.connect(self.action_prev_vol); self.btn_next_vol.clicked.connect(self.action_next_vol)
        group2_layout.addWidget(self.btn_prev_vol); group2_layout.addWidget(self.btn_next_vol)
        
        group3_layout = QHBoxLayout(); group3_layout.setSpacing(2)
        self.btn_reset_series.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy_orig.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_apply_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_apply_series.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.set_segmented_btn_style(self.btn_reset_series, "left_end")
        self.set_segmented_btn_style(self.btn_copy_orig, "middle")
        self.set_segmented_btn_style(self.btn_apply_all, "middle")
        self.set_segmented_btn_style(self.btn_apply_series, "right_end", is_primary=True)
        
        self.btn_reset_series.clicked.connect(self.action_reset_series)
        self.btn_copy_orig.clicked.connect(self.action_copy_orig)
        self.btn_apply_all.clicked.connect(self.action_apply_all)
        self.btn_apply_series.clicked.connect(self.action_apply_series)
        
        group3_layout.addWidget(self.btn_reset_series); group3_layout.addWidget(self.btn_copy_orig); group3_layout.addWidget(self.btn_apply_all); group3_layout.addWidget(self.btn_apply_series)
        nav_layout.addLayout(group1_layout); nav_layout.addStretch(); nav_layout.addLayout(group2_layout); nav_layout.addStretch(); nav_layout.addLayout(group3_layout)
        right_layout.addLayout(nav_layout)

    def _create_group_box(self, title):
        group = QGroupBox(title)
        layout = QGridLayout(group)
        layout.setContentsMargins(10, 15, 10, 10)
        layout.setSpacing(10)
        return group, layout

    def _create_number_input(self, is_date=False, date_type=None):
        widget = QWidget(); h_layout = QHBoxLayout(widget)
        h_layout.setContentsMargins(0,0,0,0); h_layout.setSpacing(2)
        le_num = QLineEdit(); le_num.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 다크/라이트 테마에 따른 아이콘 색상 설정
        is_dark = getattr(self.main_app, 'is_dark_mode', True)
        icon_c = 'white' if is_dark else '#1F2937'
        
        btn_minus = QPushButton()
        btn_minus.setIcon(qta.icon('fa5s.minus', color=icon_c))
        btn_minus.setFixedWidth(30)
        btn_minus.setObjectName("smallBtn")
        btn_minus.setCursor(Qt.CursorShape.PointingHandCursor)
        
        btn_plus = QPushButton()
        btn_plus.setIcon(qta.icon('fa5s.plus', color=icon_c))
        btn_plus.setFixedWidth(30)
        btn_plus.setObjectName("smallBtn")
        btn_plus.setCursor(Qt.CursorShape.PointingHandCursor)
        
        h_layout.addWidget(le_num, 1); h_layout.addWidget(btn_minus); h_layout.addWidget(btn_plus)
        def get_current(): return datetime.now().year if date_type == 'Y' else (datetime.now().month if date_type == 'M' else (datetime.now().day if date_type == 'D' else 0))
        def clamp(val):
            if date_type == 'Y': return max(1800, min(2100, val))
            if date_type == 'M': return max(1, min(12, val))
            if date_type == 'D': return max(1, min(31, val))
            return max(0, val)
        def change(delta):
            txt = le_num.text().strip()
            val = get_current() if not txt and is_date else (int(txt) if txt else 0)
            le_num.setText(str(clamp(val + delta)))
        def strip_zeros():
            txt = le_num.text().strip()
            if txt.isdigit(): le_num.setText(str(clamp(int(txt))))
            else: le_num.setText("")
        btn_minus.clicked.connect(lambda: change(-1)); btn_plus.clicked.connect(lambda: change(1))
        le_num.editingFinished.connect(strip_zeros)
        return widget, le_num

    def _add_row(self, layout, row, key, t_key, t_dict, is_num=False, is_text=False, is_date=False, date_type=None, combo_items=None, editable_combo=False):
        lbl_widget = QLabel(t_dict.get(t_key, t_key))
        lbl_widget.setAlignment(Qt.AlignmentFlag.AlignRight | (Qt.AlignmentFlag.AlignTop if is_text else Qt.AlignmentFlag.AlignVCenter))
        layout.addWidget(lbl_widget, row, 0)
        if is_text:
            le_my = QTextEdit(); le_my.setMinimumHeight(80); le_res = QTextEdit(); le_res.setMinimumHeight(80)
            def sync_resize():
                max_h = max(80, min(500, int(max(le_my.document().size().height(), le_res.document().size().height())) + 12))
                le_my.setMinimumHeight(max_h); le_my.setMaximumHeight(max_h); le_res.setMinimumHeight(max_h); le_res.setMaximumHeight(max_h)
            le_my.textChanged.connect(sync_resize); le_res.textChanged.connect(sync_resize)
        elif is_num:
            le_my_widget, le_my = self._create_number_input(is_date=is_date, date_type=date_type); le_res = QLineEdit()
        elif combo_items is not None:
            le_my_widget = le_my = QComboBox(); le_my.setEditable(editable_combo); le_my.addItem("", "")
            le_res = QComboBox(); le_res.setEditable(editable_combo); le_res.addItem("", "")
            for k, v in combo_items.items(): 
                le_my.addItem(v, k)
                le_res.addItem(v, k)
        else:
            le_my_widget = le_my = QLineEdit(); le_res = QLineEdit()
            
        if not is_num: le_my_widget = le_my
        
        is_dark = getattr(self.main_app, 'is_dark_mode', True)
        icon_c = 'white' if is_dark else '#1F2937'
        
        btn_map = QPushButton()
        btn_map.setIcon(qta.icon('fa5s.angle-left', color=icon_c))
        btn_map.setFixedWidth(35)
        btn_map.setObjectName("smallBtn")
        btn_map.setCursor(Qt.CursorShape.PointingHandCursor)
        
        def do_map():
            if combo_items is not None:
                val = le_res.currentText()
                if editable_combo: le_my.setCurrentText(val)
                else:
                    idx = le_my.findText(val)
                    if idx < 0: idx = le_my.findData(val)
                    if idx >= 0: le_my.setCurrentIndex(idx)
                    else: le_my.setCurrentIndex(0)
            else:
                val = le_res.toPlainText() if is_text else le_res.text()
                if is_num and val.isdigit(): val = str(int(val))
                if is_text: le_my.setPlainText(val)
                else: le_my.setText(val)
        btn_map.clicked.connect(do_map)
        layout.addWidget(le_my_widget, row, 1); layout.addWidget(btn_map, row, 2, alignment=Qt.AlignmentFlag.AlignCenter); layout.addWidget(le_res, row, 3)
        self.meta_ui_fields[key] = {'my': le_my, 'res': le_res, 'is_text': is_text, 'is_combo': combo_items is not None, 'lbl': lbl_widget, 't_key': t_key}

    def _add_checkbox_group(self, layout, start_row, key, t_key, items_dict, t_dict):
        lbl_widget = QLabel(f"<b>{t_dict.get(t_key, t_key)}</b>"); lbl_widget.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        layout.addWidget(lbl_widget, start_row, 0)
        cb_container = QWidget(); cb_layout = QGridLayout(cb_container); cb_layout.setContentsMargins(0, 0, 0, 5); cb_layout.setSpacing(5)
        checkboxes = {}; r, c = 0, 0
        for orig, loc in items_dict.items():
            cb = QCheckBox(loc); checkboxes[loc] = cb; cb_layout.addWidget(cb, r, c); c += 1
            if c >= 5: c = 0; r += 1
        layout.addWidget(cb_container, start_row, 1, 1, 3); start_row += 1
        
        le_my = TagInputArea(t_dict)
        
        is_dark = getattr(self.main_app, 'is_dark_mode', True)
        icon_c = 'white' if is_dark else '#1F2937'
        
        btn_map = QPushButton()
        btn_map.setIcon(qta.icon('fa5s.angle-left', color=icon_c))
        btn_map.setFixedWidth(35)
        btn_map.setObjectName("smallBtn")
        btn_map.setCursor(Qt.CursorShape.PointingHandCursor)
        
        le_res = QTextEdit(); le_res.setMaximumHeight(80); le_res.setObjectName("readOnlyText")
        layout.addWidget(le_my, start_row, 1); layout.addWidget(btn_map, start_row, 2, alignment=Qt.AlignmentFlag.AlignCenter); layout.addWidget(le_res, start_row, 3); start_row += 1
        btn_series = QPushButton(t_dict.get("t3_btn_apply_series_tag", ""))
        btn_series.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(btn_series, start_row, 1)
        self.dynamic_series_btns.append(btn_series); start_row += 1
        layout.addItem(QSpacerItem(10, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed), start_row, 1)
        def on_cb_changed():
            cur = le_my.tags.copy(); chk = [txt for txt, cb in checkboxes.items() if cb.isChecked()]
            un = [txt for txt, cb in checkboxes.items() if not cb.isChecked()]
            new = [tg for tg in cur if tg not in un]
            for tg in chk:
                if tg not in new: new.append(tg)
            le_my.on_change_cb = None; le_my.set_tags(new); le_my.on_change_cb = on_tag_changed
        def on_tag_changed():
            for txt_loc, cb in checkboxes.items():
                cb.blockSignals(True); cb.setChecked(txt_loc in le_my.tags); cb.blockSignals(False)
        for cb in checkboxes.values(): cb.stateChanged.connect(on_cb_changed)
        le_my.on_change_cb = on_tag_changed; btn_map.clicked.connect(lambda: le_my.setText(le_res.toPlainText()))
        def apply_to_series():
            if not self.current_meta_file: return
            val = le_my.text().strip(); parent_dir = str(Path(self.current_meta_file).parent)
            if parent_dir not in self.meta_data: return
            count = 0
            for f in self.meta_data[parent_dir]:
                fp = str(f)
                if fp in self.book_meta: self.book_meta[fp][key] = val; count += 1
            Toast.show(self.main_app, self.main_app.i18n[self.main_app.lang].get("t3_msg_applied_char_series", "").format(count=count))
        btn_series.clicked.connect(apply_to_series)
        self.meta_ui_fields[key] = {'my': le_my, 'res': le_res, 'is_text': False, 'is_combo': False, 'is_tag': True, 'lbl': lbl_widget, 't_key': t_key, 'is_cb': True}
        return start_row + 1

    def _setup_scroll_area(self, right_layout, t):
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QWidget()
        
        scroll_layout = QVBoxLayout(self.scroll_content)
        scroll_layout.setContentsMargins(0, 0, 10, 0); scroll_layout.setSpacing(20)

        self.meta_ui_fields = {}

        self.group_basic, gl_basic = self._create_group_box(t.get("t3_nav_basic", "").replace("\n"," "))
        self.lbl_col_orig = QLabel(t.get('t3_col_orig', '원본')); self.lbl_col_res = QLabel(t.get('t3_col_res', '일괄 편집'))
        gl_basic.addWidget(self.lbl_col_orig, 0, 1, alignment=Qt.AlignmentFlag.AlignCenter)
        gl_basic.addWidget(self.lbl_col_res, 0, 3, alignment=Qt.AlignmentFlag.AlignCenter)
        
        
        self._add_row(gl_basic, 1, 'Title', 't3_f_title', t); self._add_row(gl_basic, 2, 'Series', 't3_f_series', t); self._add_row(gl_basic, 3, 'SeriesGroup', 't3_f_sgroup', t)
        self._add_row(gl_basic, 4, 'Count', 't3_f_count', t, is_num=True); self._add_row(gl_basic, 5, 'Volume', 't3_f_vol', t, is_num=True); self._add_row(gl_basic, 6, 'Number', 't3_f_num', t, is_num=True)
        self._add_row(gl_basic, 7, 'PageCount', 't3_f_page', t, is_num=True); self._add_row(gl_basic, 8, 'Summary', 't3_f_sum', t, is_text=True); scroll_layout.addWidget(self.group_basic)

        self.group_crew, gl_crew = self._create_group_box(t.get("t3_nav_crew", "").replace("\n"," "))
        self._add_row(gl_crew, 0, 'Writer', 't3_f_writer', t); self._add_row(gl_crew, 1, 'Penciller', 't3_f_pen', t); self._add_row(gl_crew, 2, 'Inker', 't3_f_inker', t); self._add_row(gl_crew, 3, 'Colorist', 't3_f_color', t)
        self._add_row(gl_crew, 4, 'Letterer', 't3_f_letter', t); self._add_row(gl_crew, 5, 'CoverArtist', 't3_f_cover', t); self._add_row(gl_crew, 6, 'Editor', 't3_f_editor', t); scroll_layout.addWidget(self.group_crew)

        self.group_publish, gl_publish = self._create_group_box(t.get("t3_nav_publish", "").replace("\n"," "))
        self._add_row(gl_publish, 0, 'Publisher', 't3_f_pub', t); self._add_row(gl_publish, 1, 'Imprint', 't3_f_imp', t)
        self._add_row(gl_publish, 2, 'Web', 't3_f_web', t, is_text=True)
        self._add_row(gl_publish, 3, 'Format', 't3_f_format', t, combo_items=t.get("meta_formats", {}), editable_combo=True)
        self._add_row(gl_publish, 4, 'Year', 't3_f_year', t, is_num=True, is_date=True, date_type='Y'); self._add_row(gl_publish, 5, 'Month', 't3_f_month', t, is_num=True, is_date=True, date_type='M')
        self._add_row(gl_publish, 6, 'Day', 't3_f_day', t, is_num=True, is_date=True, date_type='D'); scroll_layout.addWidget(self.group_publish)

        self.group_genre_tags, gl_genre_tags = self._create_group_box(t.get("t3_nav_genre", "").replace("\n",""))
        r = self._add_checkbox_group(gl_genre_tags, 0, 'Genre', 't3_f_genre', t.get("meta_genres", {}), t)
        r = self._add_checkbox_group(gl_genre_tags, r, 'Tags', 't3_f_tags_lbl', t.get("meta_tags", {}), t)
        lbl_char = QLabel(t.get('t3_f_char', '')); lbl_char.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop); gl_genre_tags.addWidget(lbl_char, r, 0)
        
        le_char_my = TagInputArea(t); le_char_res = QTextEdit(); le_char_res.setMaximumHeight(80)
        btn_char_map = QPushButton("<"); btn_char_map.setFixedWidth(35); gl_genre_tags.addWidget(le_char_my, r, 1); gl_genre_tags.addWidget(btn_char_map, r, 2, alignment=Qt.AlignmentFlag.AlignCenter); gl_genre_tags.addWidget(le_char_res, r, 3)
        r += 1
        btn_char_series = QPushButton(t.get("t3_btn_apply_series_tag", ""))
        btn_char_series.setCursor(Qt.CursorShape.PointingHandCursor); gl_genre_tags.addWidget(btn_char_series, r, 1); self.dynamic_series_btns.append(btn_char_series)
        r += 1; gl_genre_tags.addItem(QSpacerItem(10, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed), r, 1)
        btn_char_map.clicked.connect(lambda _, m=le_char_my, res=le_char_res: m.setText(res.toPlainText()))
        def apply_char_to_series():
            if not self.current_meta_file: return
            val = le_char_my.text().strip(); parent_dir = str(Path(self.current_meta_file).parent)
            if parent_dir not in self.meta_data: return
            count = 0
            for f in self.meta_data[parent_dir]:
                fp = str(f)
                if fp in self.book_meta: self.book_meta[fp]['Characters'] = val; count += 1
            Toast.show(self.main_app, self.main_app.i18n[self.main_app.lang].get("t3_msg_applied_char_series", "").format(count=count))
        btn_char_series.clicked.connect(apply_char_to_series)
        self.meta_ui_fields['Characters'] = {'my': le_char_my, 'res': le_char_res, 'is_text': False, 'is_combo': False, 'is_tag': True, 'lbl': lbl_char, 't_key': 't3_f_char', 'is_cb': True}
        scroll_layout.addWidget(self.group_genre_tags)

        self.group_etc, gl_etc = self._create_group_box(t.get("t3_nav_etc", "").replace("\n"," "))
        self._add_row(gl_etc, 0, 'AgeRating', 't3_f_age', t, combo_items=t.get("meta_age", {}), editable_combo=False); self._add_row(gl_etc, 1, 'CommunityRating', 't3_f_rate', t) 
        self._add_row(gl_etc, 2, 'LanguageISO', 't3_f_iso', t); self._add_row(gl_etc, 3, 'Manga', 't3_f_dir', t, combo_items=t.get("meta_manga", {}), editable_combo=False)
        scroll_layout.addWidget(self.group_etc)
        
        scroll_layout.addStretch(); self.scroll_area.setWidget(self.scroll_content); right_layout.addWidget(self.scroll_area, 1)

        def scroll_to(w): self.scroll_area.verticalScrollBar().setValue(w.pos().y() - 10)
        self.btn_goto_basic.clicked.connect(lambda: scroll_to(self.group_basic)); self.btn_goto_crew.clicked.connect(lambda: scroll_to(self.group_crew))
        self.btn_goto_publish.clicked.connect(lambda: scroll_to(self.group_publish)); self.btn_goto_genre.clicked.connect(lambda: scroll_to(self.group_genre_tags))
        self.btn_goto_etc.clicked.connect(lambda: scroll_to(self.group_etc))

        def on_scroll(value):
            if not hasattr(self, 'group_basic'): return
            groups = [(self.group_basic, self.btn_goto_basic), (self.group_crew, self.btn_goto_crew), (self.group_publish, self.btn_goto_publish), (self.group_genre_tags, self.btn_goto_genre), (self.group_etc, self.btn_goto_etc)]
            active_btn = self.btn_goto_basic
            for group, btn in groups:
                if group.pos().y() <= value + 80: active_btn = btn
            self.update_nav_buttons_state(active_btn)
            
        self.scroll_area.verticalScrollBar().valueChanged.connect(on_scroll)

    def _setup_bottom_buttons(self, right_layout, t):
        bottom_btn_layout = QHBoxLayout()
        self.btn_auto_title = QPushButton(t.get("t3_auto_title", ""))
        self.btn_auto_vol = QPushButton(t.get("t3_auto_vol", ""))
        self.btn_auto_chap = QPushButton(t.get("t3_auto_chap", ""))
        self.btn_auto_pages = QPushButton(t.get("t3_auto_pages", ""))
        
        self.btn_auto_match = QPushButton(t.get("t3_auto_match", "시리즈 자동 매칭"))
        self.btn_auto_match.setToolTip(t.get("t3_tt_auto_match", ""))
        self.btn_auto_match.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_auto_match.setObjectName("actionBtnOrange")
        self.btn_auto_match.clicked.connect(self.action_auto_match_series)
        self.btn_auto_match.setStyleSheet('font-size:11px; padding: 5px 8px;')
        
        self.btn_meta_save = QPushButton(t.get("t3_save", ""))
        self.btn_meta_save_all = QPushButton(t.get("t3_save_all", ""))

        self.btn_auto_title.setToolTip(t.get("t3_tt_auto_title", ""))
        self.btn_auto_vol.setToolTip(t.get("t3_tt_auto_vol", ""))
        self.btn_auto_chap.setToolTip(t.get("t3_tt_auto_chap", ""))
        self.btn_auto_pages.setToolTip(t.get("t3_tt_auto_pages", ""))
        self.btn_meta_save.setToolTip(t.get("t3_tt_save", ""))
        self.btn_meta_save_all.setToolTip(t.get("t3_tt_save_all", ""))
        
        for btn in [self.btn_auto_title, self.btn_auto_vol, self.btn_auto_chap, self.btn_auto_pages]:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("font-size: 11px; padding: 5px 8px;")
            
        self.btn_meta_save_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_meta_save_all.setObjectName("actionBtn") # 🌟 모두 저장: 파란색 테마
        self.btn_meta_save_all.setStyleSheet("background-color: #0078d7;")
        self.btn_meta_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_meta_save.setObjectName("actionBtnGreen") # 🌟 저장: 초록색 테마
        self.btn_meta_save.setStyleSheet("background-color: #27ae60;")
        
        self.btn_auto_title.clicked.connect(self.action_auto_title)
        self.btn_auto_vol.clicked.connect(self.action_auto_volume)
        self.btn_auto_chap.clicked.connect(self.action_auto_chapter)
        self.btn_auto_pages.clicked.connect(self.action_auto_pages)
        self.btn_meta_save.clicked.connect(self.action_save_single)
        self.btn_meta_save_all.clicked.connect(self.action_save_all)
        
        bottom_btn_layout.addWidget(self.btn_auto_match)
        bottom_btn_layout.addWidget(self.btn_auto_title); bottom_btn_layout.addWidget(self.btn_auto_vol)
        bottom_btn_layout.addWidget(self.btn_auto_chap); bottom_btn_layout.addWidget(self.btn_auto_pages)
        bottom_btn_layout.addStretch(); bottom_btn_layout.addWidget(self.btn_meta_save); bottom_btn_layout.addWidget(self.btn_meta_save_all)
        right_layout.addLayout(bottom_btn_layout)

    def _setup_shortcuts(self):
        # 🌟 단축키 S 예외 처리: 현재 텍스트 입력창이 포커스 된 경우를 제외하고 어디서든 작동
        self.shortcut_s = QShortcut(QKeySequence(Qt.Key.Key_S), self)
        self.shortcut_s.activated.connect(self._trigger_s)
        self.shortcut_s.setContext(Qt.ShortcutContext.WindowShortcut)

        self.shortcut_c = QShortcut(QKeySequence(Qt.Key.Key_C), self)
        self.shortcut_c.activated.connect(self._trigger_c)
        self.shortcut_c.setContext(Qt.ShortcutContext.WindowShortcut)

    def _trigger_s(self):
        focus_widget = QApplication.focusWidget()
        # 입력창에서 타이핑 중이면 단축키(S)를 가로채지 않고 무시합니다.
        if isinstance(focus_widget, (QLineEdit, QTextEdit, QComboBox)): return
        
        if self.btn_meta_search.isEnabled():
            self.action_search_api()

    def _trigger_c(self):
        focus_widget = QApplication.focusWidget()
        if isinstance(focus_widget, (QLineEdit, QTextEdit, QComboBox)): return
        
        if getattr(self, 'btn_apply_series', None) and self.btn_apply_series.isEnabled():
            self.action_apply_series()

    def retranslate_ui(self, t, lang):
        self.lbl_empty.setText(t.get("t3_empty", ""))
        if not self.current_meta_file: self.lbl_meta_cover.setText(t.get("t3_cover", ""))
        self.lbl_search_api.setText(t.get("t3_search_api", ""))
        self.lbl_search_query.setText(t.get("t3_search_query", ""))
        self.le_meta_search.setPlaceholderText(t.get("t3_search_ph", ""))
        
        self.btn_meta_search.setText(f" {t.get('btn_search', '검색')} (S)")
        self.btn_goto_basic.setText(t.get("t3_nav_basic", ""))
        self.btn_goto_crew.setText(t.get("t3_nav_crew", ""))
        self.btn_goto_publish.setText(t.get("t3_nav_publish", ""))
        self.btn_goto_genre.setText(t.get("t3_nav_genre", ""))
        self.btn_goto_etc.setText(t.get("t3_nav_etc", ""))
        self.btn_copy_orig.setText(t.get("t3_btn_copy_orig", ""))
        self.btn_apply_all.setText(t.get("t3_btn_apply_all", ""))
        
        self.btn_reset_series.setText(t.get("t3_btn_reset_series", "시리즈\n초기화"))
        self.btn_apply_series.setText(f"{t.get('t3_btn_apply_series', '시리즈\n편집 적용')} (C)")
        
        self.lbl_col_orig.setText(t.get('t3_col_orig', '원본'))
        self.lbl_col_res.setText(t.get('t3_col_res', '일괄 편집'))
        
        self.group_basic.setTitle(t.get("t3_nav_basic", "").replace("\n"," "))
        self.group_crew.setTitle(t.get("t3_nav_crew", "").replace("\n"," "))
        self.group_publish.setTitle(t.get("t3_nav_publish", "").replace("\n"," "))
        self.group_genre_tags.setTitle(t.get("t3_nav_genre", "").replace("\n",""))
        self.group_etc.setTitle(t.get("t3_nav_etc", "").replace("\n"," "))
        
        self.btn_auto_match.setText(t.get("t3_auto_match", "🤖 시리즈 자동 매칭"))
        self.btn_auto_match.setToolTip(t.get("t3_tt_auto_match", ""))
        
        self.btn_auto_title.setText(t.get("t3_auto_title", ""))
        self.btn_auto_vol.setText(t.get("t3_auto_vol", ""))
        self.btn_auto_chap.setText(t.get("t3_auto_chap", ""))
        self.btn_auto_pages.setText(t.get("t3_auto_pages", ""))
        self.btn_meta_save.setText(t.get("t3_save", ""))
        self.btn_meta_save_all.setText(t.get("t3_save_all", ""))
        
        self.btn_prev_vol.setText(t.get("t3_btn_prev", "이전 권"))
        self.btn_next_vol.setText(t.get("t3_btn_next", "다음 권"))
        
        self.btn_reset_series.setToolTip(t.get("t3_tt_reset_series", ""))
        self.btn_copy_orig.setToolTip(t.get("t3_tt_copy_orig", ""))
        self.btn_apply_all.setToolTip(t.get("t3_tt_apply_all", ""))
        self.btn_apply_series.setToolTip(t.get("t3_tt_apply_series", ""))
        self.btn_auto_title.setToolTip(t.get("t3_tt_auto_title", ""))
        self.btn_auto_vol.setToolTip(t.get("t3_tt_auto_vol", ""))
        self.btn_auto_chap.setToolTip(t.get("t3_tt_auto_chap", ""))
        self.btn_auto_pages.setToolTip(t.get("t3_tt_auto_pages", ""))
        self.btn_meta_save.setToolTip(t.get("t3_tt_save", ""))
        self.btn_meta_save_all.setToolTip(t.get("t3_tt_save_all", ""))

        for b in getattr(self, 'dynamic_series_btns', []):
            b.setText(t.get("t3_btn_apply_series_tag", ""))
            
        for key, field in self.meta_ui_fields.items():
            if field.get('is_cb'): field['lbl'].setText(f"<b>{t.get(field['t_key'], field['t_key'])}</b>")
            else: field['lbl'].setText(t.get(field['t_key'], field['t_key']))
            
            if isinstance(field.get('my'), TagInputArea):
                field['my'].update_i18n(t)

    def set_right_panel_active(self, active):
        self.scroll_area.setEnabled(active); self.cb_meta_api.setEnabled(active)
        self.le_meta_search.setEnabled(active); self.btn_meta_search.setEnabled(active)
        for b in [self.btn_auto_match, self.btn_auto_title, self.btn_auto_vol, self.btn_auto_chap, self.btn_auto_pages, self.btn_meta_save, self.btn_meta_save_all]: b.setEnabled(active)
        if active: self.right_overlay.hide()
        else: self.right_overlay.show(); self.right_overlay.raise_()

    # 🌟 기능: 시리즈 초기화 (원본 카피본으로 되돌리기)
    def action_reset_series(self):
        t = self.main_app.i18n[self.main_app.lang]
        if not self.current_meta_file: return
        parent_dir = str(Path(self.current_meta_file).parent)
        if parent_dir not in self.meta_data: return

        reply = QMessageBox.question(
            self, "안내" if self.main_app.lang == "ko" else "Notice", 
            "현재 책이 속한 시리즈 전체의 메타데이터를 저장 전 원본 상태로 되돌리시겠습니까?" if self.main_app.lang == "ko" else "Are you sure you want to reset metadata for this entire series to its original state?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes: return

        self.main_app.progress_bar.show()
        self.main_app.progress_bar.setRange(0, 0)
        self.main_app.lbl_status.setText("초기화 중..." if self.main_app.lang == "ko" else "Resetting...")
        threading.Thread(target=self._bg_reset_series, args=(parent_dir,), daemon=True).start()

    def _bg_reset_series(self, parent_dir):
        files = self.meta_data[parent_dir]
        for f in files:
            fp = str(f)
            self.book_meta[fp] = {key: "" for key in self.meta_ui_fields.keys()}
            self.book_meta[fp]['Title'] = f.stem
            xml_data = self._read_xml_from_archive(fp)
            if xml_data:
                for k, v in xml_data.items():
                    if k in self.book_meta[fp] or k in ['ComicZipAddedDate', 'ComicZipModifiedDate']:
                        self.book_meta[fp][k] = v
        QTimer.singleShot(0, self._on_reset_series_finished)

    def _on_reset_series_finished(self):
        self.main_app.progress_bar.hide()
        self.main_app.lbl_status.setText(self.main_app.i18n[self.main_app.lang].get("status_wait", ""))
        if self.current_meta_file:
            self._load_dict_to_ui(self.current_meta_file)
        Toast.show(self.main_app, "시리즈 데이터가 초기화되었습니다." if self.main_app.lang == "ko" else "Series reset complete.")

    def action_auto_match_series(self):
        t = self.main_app.i18n[self.main_app.lang]
        if not self.current_meta_file: return
        parent_dir = str(Path(self.current_meta_file).parent)
        folder_name = os.path.basename(parent_dir)
        
        self.main_app.lbl_status.setText("🤖 시리즈 메타데이터 자동 매칭 중...")
        QApplication.processEvents()
        
        api_name = self.cb_meta_api.currentText()
        api_keys = self.main_app.config.get("api_keys", {})
        
        results, _ = MetaApiFetcher.search(api_name, folder_name, api_keys, 1)
        self.main_app.lbl_status.setText(t.get("status_wait", "대기 중..."))
        
        if not results or results == "RATE_LIMIT":
            Toast.show(self.main_app, t.get("t3_msg_no_search_result", "검색 결과가 없습니다."))
            return
            
        best_match = results[0]
        
        tag_rules = {}
        rules_text = api_keys.get("tag_rules", "")
        if rules_text:
            for line in rules_text.split('\n'):
                if '->' in line:
                    srcs, dst = line.split('->')
                    dst = dst.strip()
                    for src in srcs.split(','):
                        tag_rules[src.strip().lower()] = dst

        def apply_rules(text):
            if not text or not tag_rules: return text
            items = [x.strip() for x in text.split(',')]
            new_items = []
            for item in items:
                l_item = item.lower()
                if l_item in tag_rules:
                    mapped = tag_rules[l_item]
                    if mapped and mapped not in new_items: new_items.append(mapped)
                else:
                    if item and item not in new_items: new_items.append(item)
            return ", ".join(new_items)
            
        def parse_val(val):
            if val is None or val == "" or val == "-": return ""
            if isinstance(val, list): return ", ".join(str(x) for x in val)
            if isinstance(val, str):
                v_str = val.strip()
                if v_str.startswith('[') and v_str.endswith(']'):
                    import ast
                    try:
                        parsed = ast.literal_eval(v_str)
                        if isinstance(parsed, list): return ", ".join(str(x) for x in parsed)
                    except:
                        try:
                            import json
                            parsed = json.loads(v_str)
                            if isinstance(parsed, list): return ", ".join(str(x) for x in parsed)
                        except: pass
            return str(val)
        
        parsed_match = {k: parse_val(v) for k, v in best_match.items()}
        parsed_match['Genre'] = apply_rules(parsed_match.get('Genre', ''))
        parsed_match['Tags'] = apply_rules(parsed_match.get('Tags', ''))
        
        if 'Summary' in parsed_match:
            parsed_match['Summary'] = parsed_match['Summary'].replace("<책소개>", "").replace("&lt;책소개&gt;", "")
            parsed_match['Summary'] = re.sub(r'\n{2,}', '\n', parsed_match['Summary']).strip()
            
        exclude_keys = {'Volume', 'Number', 'PageCount'}
        count = 0
        for f in self.meta_data[parent_dir]:
            fp = str(f)
            if fp in self.book_meta:
                for k, v in parsed_match.items():
                    if k not in exclude_keys and k in self.meta_ui_fields:
                        self.book_meta[fp][k] = v
                count += 1
                
        self._load_dict_to_ui(self.current_meta_file)
        Toast.show(self.main_app, t.get("t3_msg_auto_match_done", "시리즈 자동 매칭이 완료되었습니다."))

    def action_prev_vol(self):
        current = self.tree_meta_files.currentItem()
        if current and current.parent():
            idx = current.parent().indexOfChild(current)
            if idx > 0: self.tree_meta_files.setCurrentItem(current.parent().child(idx - 1))

    def action_next_vol(self):
        current = self.tree_meta_files.currentItem()
        if current and current.parent():
            idx = current.parent().indexOfChild(current)
            if idx < current.parent().childCount() - 1: self.tree_meta_files.setCurrentItem(current.parent().child(idx + 1))

    def action_copy_orig(self):
        if not self.current_meta_file: return
        exclude_keys = {'Volume', 'Number', 'PageCount'}
        
        for key, field in self.meta_ui_fields.items():
            if key in exclude_keys: continue
            
            val = None
            if field.get('is_combo'):
                if field['my'].isEditable(): val = field['my'].currentText()
                else: val = field['my'].currentData()
            elif field.get('is_text'):
                val = field['my'].toPlainText()
            elif field.get('is_tag'):
                val = field['my'].text()
            else:
                val = field['my'].text()
                
            res_widget = field['res']
            if isinstance(res_widget, QComboBox):
                if res_widget.isEditable():
                    res_widget.setCurrentText(val)
                else:
                    idx = res_widget.findData(val)
                    if idx >= 0: res_widget.setCurrentIndex(idx)
                    else: res_widget.setCurrentIndex(0)
            elif isinstance(res_widget, QTextEdit):
                res_widget.setPlainText(val)
            else:
                res_widget.setText(val)

    def load_paths(self, paths):
        t = self.main_app.i18n[self.main_app.lang]
        self.main_app.progress_bar.show(); self.main_app.progress_bar.setRange(0, 0)
        self.main_app.lbl_status.setText(t.get("t3_msg_analyzing", ""))
        threading.Thread(target=self._bg_load_paths, args=(paths,), daemon=True).start()

    def _bg_load_paths(self, paths):
        exts = {'.zip', '.cbz', '.cbr', '.7z', '.rar'}; scanned_files = []
        for p in paths:
            path_obj = Path(p)
            if path_obj.is_file() and path_obj.suffix.lower() in exts: scanned_files.append(path_obj)
            elif path_obj.is_dir():
                for sub in path_obj.rglob('*'):
                    if sub.is_file() and sub.suffix.lower() in exts and 'bak' not in sub.parts: scanned_files.append(sub)

        for f in scanned_files:
            parent = str(f.parent)
            if parent not in self.meta_data: self.meta_data[parent] = []
            if f not in self.meta_data[parent]: self.meta_data[parent].append(f)
            fp = str(f)
            if fp not in self.book_meta:
                self.book_meta[fp] = {key: "" for key in self.meta_ui_fields.keys()}; self.book_meta[fp]['Title'] = f.stem
                xml_data = self._read_xml_from_archive(fp)
                if xml_data:
                    for k, v in xml_data.items():
                        if k in self.book_meta[fp] or k in ['ComicZipAddedDate', 'ComicZipModifiedDate']: self.book_meta[fp][k] = v
        QTimer.singleShot(0, self._on_bg_load_finished)

    def _on_bg_load_finished(self):
        self.main_app.progress_bar.hide(); self.main_app.progress_bar.setRange(0, 100)
        self.main_app.lbl_status.setText(self.main_app.i18n[self.main_app.lang].get("status_wait", ""))
        self.refresh_tree()

    def _read_xml_from_archive(self, fp):
        ext = Path(fp).suffix.lower(); xml_str = None
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
                root = ET.fromstring(xml_str); return {child.tag: child.text for child in root if child.text}
            except: pass
        return None

    def refresh_tree(self):
        t = self.main_app.i18n[self.main_app.lang]
        saved_selection = self.current_meta_file
        
        self.tree_meta_files.clear()
        if not self.meta_data:
            self.meta_stacked.setCurrentIndex(0); self.set_right_panel_active(False); return
            
        self.meta_stacked.setCurrentIndex(1); self.set_right_panel_active(False)
        target_item_to_select = None
        
        for folder_path, files in self.meta_data.items():
            folder_name = os.path.basename(folder_path) or folder_path
            root_item = QTreeWidgetItem([folder_name])
            root_item.setIcon(0, qta.icon('fa5s.folder-open', color='#F39C12'))
            self.tree_meta_files.addTopLevelItem(root_item)
            sorted_files = sorted(files, key=lambda x: natural_keys(x.name))
            
            for f in sorted_files:
                fp = str(f); b_meta = self.book_meta.get(fp, {})
                title = f.name 
                mod_date = b_meta.get('ComicZipModifiedDate')
                
                child_item = QTreeWidgetItem()
                child_item.setData(0, Qt.ItemDataRole.UserRole, fp)
                child_item.setToolTip(0, title)
                root_item.addChild(child_item)
                
                if fp == saved_selection:
                    target_item_to_select = child_item
                    
                item_widget = QWidget(); item_widget.setStyleSheet("background: transparent;")
                item_layout = QVBoxLayout(item_widget); item_layout.setContentsMargins(4, 2, 4, 2); item_layout.setSpacing(1)
                
                title_layout = QHBoxLayout()
                title_layout.setContentsMargins(0, 0, 0, 0)
                icon_lbl = QLabel()
                icon_lbl.setPixmap(qta.icon('fa5s.file-alt', color='#bdc3c7').pixmap(12, 12))
                lbl_title = QLabel(title)
                lbl_title.setStyleSheet("font-size: 13px; margin-bottom:0;")
                lbl_title.setWordWrap(True) 
                title_layout.addWidget(icon_lbl)
                title_layout.addWidget(lbl_title, 1)
                
                date_str = mod_date if mod_date else t.get("t3_no_data", "")
                
                date_layout = QHBoxLayout()
                date_layout.setContentsMargins(0, 0, 0, 0)
                clock_lbl = QLabel()
                clock_lbl.setPixmap(qta.icon('fa5s.clock', color='#7f8c8d').pixmap(10, 10))
                lbl_date = QLabel(date_str)
                lbl_date.setStyleSheet("color: #aaaaaa; font-size: 10px; margin-top:0;") 
                
                date_layout.addSpacing(18)
                date_layout.addWidget(clock_lbl)
                date_layout.addWidget(lbl_date, 1)
                
                item_layout.addLayout(title_layout)
                item_layout.addLayout(date_layout)
                
                child_item.setSizeHint(0, QSize(200, 48)); self.tree_meta_files.setItemWidget(child_item, 0, item_widget)
                
        self.tree_meta_files.expandAll()
        
        if target_item_to_select:
            self.tree_meta_files.setCurrentItem(target_item_to_select)
        elif self.tree_meta_files.topLevelItemCount() > 0:
            first_root = self.tree_meta_files.topLevelItem(0)
            if first_root.childCount() > 0: self.tree_meta_files.setCurrentItem(first_root.child(0))

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
        
        title = Path(fp).stem
        import re
        clean_title = re.sub(r'^\[.*?\]\s*', '', title)
        clean_title = re.sub(r'^\(.*?\)\s*', '', clean_title)
        
        series_name = re.sub(r'\s*제?\d+\s*(?:권|화|편).*$', '', clean_title)
        series_name = re.sub(r'(?i)\s*(?:vol\.|v\.|ch\.|chapter)\s*\d+.*$', '', series_name)
        series_name = re.sub(r'\s*(?:-\s*)?\d+\s*$', '', series_name)
        
        series_name = series_name.strip()
        if series_name:
            self.le_meta_search.setText(series_name)

    def _process_cover_load(self):
        if not self.current_meta_file: return
        fp = self.current_meta_file; target_img = None; ext = Path(fp).suffix.lower()
        if ext in ['.zip', '.cbz']:
            try:
                with zipfile.ZipFile(fp, 'r') as zf:
                    entries = [info.filename for info in zf.infolist() if not info.is_dir() and Path(info.filename).suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}]
                    entries.sort(key=natural_keys); cover = next((e for e in entries if os.path.basename(e).lower().startswith('cover')), None)
                    target_img = cover if cover else (entries[0] if entries else None)
            except: pass
        else:
            try:
                from tasks.load_task import FileLoadTask
                task = FileLoadTask([], self.main_app.seven_zip_path, self.main_app.lang, self.main_app.signals)
                entries = [e['filename'] for e in task.get_7z_entries(fp) if Path(e['filename']).suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}]
                entries.sort(key=natural_keys); cover = next((e for e in entries if os.path.basename(e).lower().startswith('cover')), None)
                target_img = cover if cover else (entries[0] if entries else None)
            except: pass
            
        if target_img:
            from core.archive_utils import bg_load_image
            threading.Thread(target=bg_load_image, args=(fp, target_img, ext, "cover", self.main_app.seven_zip_path, self.main_app.signals), daemon=True).start()
        else: self.render_image("cover", fp, None)

    def render_image(self, target_id, arc_path, img_data):
        if arc_path and getattr(self, 'current_meta_file', None) != arc_path:
            return
            
        label_widget = self.lbl_meta_cover; cw = max(200, label_widget.width() - 10); ch = 340
        t = self.main_app.i18n[self.main_app.lang]
        if not img_data:
            p = get_resource_path("previewframe.png")
            if os.path.exists(p):
                try:
                    with open(p, "rb") as f: img_data = f.read()
                except: pass
        if not img_data: label_widget.setText(t.get("no_preview", "")); return
        try:
            image = QImage.fromData(img_data)
            if image.isNull(): raise Exception()
            pixmap = QPixmap.fromImage(image).scaled(QSize(cw, ch), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            target = QPixmap(pixmap.size()); target.fill(Qt.GlobalColor.transparent); painter = QPainter(target)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing); path = QPainterPath(); path.addRoundedRect(0, 0, target.width(), target.height(), 10, 10)
            painter.setClipPath(path); painter.drawPixmap(0, 0, pixmap); painter.end(); label_widget.setPixmap(target)
        except Exception: 
            label_widget.setText(t.get("no_image", ""))

    def _save_ui_to_dict(self):
        if self.current_meta_file and self.current_meta_file in self.book_meta:
            for key, field in self.meta_ui_fields.items():
                if field.get('is_combo'):
                    if field['my'].isEditable(): val = field['my'].currentText()
                    else: val = field['my'].currentData()
                elif field.get('is_text'):
                    val = field['my'].toPlainText()
                elif field.get('is_tag'):
                    val = field['my'].text()
                else:
                    val = field['my'].text()
                    
                if key == 'Web':
                    val = ','.join([x.strip() for x in val.split('\n') if x.strip()])
                    
                self.book_meta[self.current_meta_file][key] = val

    def _load_dict_to_ui(self, fp):
        data = self.book_meta.get(fp, {})
        for key, field in self.meta_ui_fields.items():
            val = data.get(key, "")
            
            if key == 'Web':
                val = '\n'.join([x.strip() for x in val.split(',') if x.strip()])
                
            if field.get('is_combo'):
                if field['my'].isEditable():
                    field['my'].setCurrentText(val)
                else:
                    idx = field['my'].findData(val)
                    if idx >= 0: field['my'].setCurrentIndex(idx)
                    else: field['my'].setCurrentIndex(0)
            elif field.get('is_text'): field['my'].setPlainText(val)
            elif field.get('is_tag'): field['my'].setText(val)
            else: field['my'].setText(val)

    def action_apply_all(self):
        for key, field in self.meta_ui_fields.items():
            res_widget = field['res']
            
            if field.get('is_combo'):
                if res_widget.isEditable():
                    val = res_widget.currentText().strip()
                    if val: field['my'].setCurrentText(val)
                else:
                    val = res_widget.currentData()
                    if val:
                        idx = field['my'].findData(val)
                        if idx >= 0: field['my'].setCurrentIndex(idx)
            elif field.get('is_text'):
                val = res_widget.toPlainText().strip()
                if val: field['my'].setPlainText(val)
            elif field.get('is_tag'):
                val = res_widget.toPlainText().strip()
                if val: field['my'].setText(val)
            else:
                val = res_widget.text().strip()
                if val: field['my'].setText(val)

    def action_apply_series(self):
        t = self.main_app.i18n[self.main_app.lang]
        if not self.current_meta_file: return
        self._save_ui_to_dict(); parent_dir = str(Path(self.current_meta_file).parent)
        if parent_dir not in self.meta_data: return
        exclude_keys = {'Volume', 'Number', 'PageCount'}; results_to_copy = {}
        for key, field in self.meta_ui_fields.items():
            if key not in exclude_keys:
                res_widget = field['res']
                
                if field.get('is_combo'):
                    if res_widget.isEditable():
                        val = res_widget.currentText().strip()
                    else:
                        val = res_widget.currentData()
                elif isinstance(res_widget, QTextEdit):
                    val = res_widget.toPlainText().strip()
                else:
                    val = res_widget.text().strip()
                    
                if val: 
                    if key == 'Web':
                        val = ','.join([x.strip() for x in val.split('\n') if x.strip()])
                    results_to_copy[key] = val
                    
        if not results_to_copy: 
            Toast.show(self.main_app, t.get("t3_msg_no_data_copy", ""))
            return
            
        for f in self.meta_data[parent_dir]:
            fp = str(f)
            if fp in self.book_meta:
                for k, v in results_to_copy.items(): self.book_meta[fp][k] = v
                
        self.action_auto_title(show_toast=False)
        self.action_auto_volume(show_toast=False)
        self.action_auto_chapter(show_toast=False)
        self.action_auto_pages(show_toast=False)
                
        self._load_dict_to_ui(self.current_meta_file)
        Toast.show(self.main_app, t.get("t3_msg_applied_series_all", ""))

    def action_auto_title(self, show_toast=True):
        t = self.main_app.i18n[self.main_app.lang]
        if not self.current_meta_file: return
        parent_dir = str(Path(self.current_meta_file).parent)
        
        import re
        for f in self.meta_data.get(parent_dir, []):
            fp = str(f); title = f.stem
            
            clean_title = re.sub(r'^\[.*?\]\s*|^\(.*?\)\s*', '', title).strip()
            
            v_match = re.search(r'(?i)(?:^|\s|_|-)(?:vol\.?|v)\s*(\d+)', title) or re.search(r'제?\s*(\d+)\s*권', title) or re.search(r'\b(\d+)\s*$', title.strip())
            c_match = re.search(r'(?i)(?:^|\s|_|-)(?:ch\.?|chapter|c)\s*(\d+)', title) or re.search(r'제?\s*(\d+)\s*화', title)
            
            series_name = re.sub(r'\s*제?\d+\s*(?:권|화|편).*$', '', clean_title)
            series_name = re.sub(r'(?i)(?:\s|_|-)*(?:vol\.?|v|ch\.?|chapter|c)\s*\d+.*$', '', series_name)
            series_name = re.sub(r'\s*(?:-\s*)?\d+\s*$', '', series_name)
            
            final_title = clean_title
            lang = getattr(self.main_app, 'lang', 'ko')
            
            if v_match:
                vol_str = v_match.group(1) 
                if lang == 'en':
                    final_title = f"{series_name} Vol. {vol_str}"
                else:
                    final_title = f"{series_name} {vol_str}권"
            elif c_match:
                ch_str = c_match.group(1)
                if lang == 'en':
                    final_title = f"{series_name} Ch. {ch_str}"
                else:
                    final_title = f"{series_name} {ch_str}화"
            
            if final_title: self.book_meta[fp]['Title'] = final_title
            if series_name: self.book_meta[fp]['Series'] = series_name 
            
            if v_match: self.book_meta[fp]['Volume'] = str(int(v_match.group(1)))
            if c_match: self.book_meta[fp]['Number'] = str(int(c_match.group(1)))
            
        self._load_dict_to_ui(self.current_meta_file)
        if show_toast: Toast.show(self.main_app, t.get("t3_msg_auto_title_done", ""))

    def action_auto_volume(self, show_toast=True):
        t = self.main_app.i18n[self.main_app.lang]
        if not self.current_meta_file: return
        parent_dir = str(Path(self.current_meta_file).parent)
        for f in self.meta_data.get(parent_dir, []):
            fp = str(f); title = f.name
            match = re.search(r'(?i)(?:vol\.|v\.|권)\s*(\d+)', title) or re.search(r'제?\s*(\d+)\s*권', title) or re.search(r'\b(\d+)\s*$', title.strip())
            if match: self.book_meta[fp]['Volume'] = str(int(match.group(1)))
        self._load_dict_to_ui(self.current_meta_file)
        if show_toast: Toast.show(self.main_app, t.get("t3_msg_auto_vol_done", ""))

    def action_auto_chapter(self, show_toast=True):
        t = self.main_app.i18n[self.main_app.lang]
        if not self.current_meta_file: return
        parent_dir = str(Path(self.current_meta_file).parent)
        for f in self.meta_data.get(parent_dir, []):
            fp = str(f); title = f.name
            match = re.search(r'(?i)(?:ch\.|chapter|화)\s*(\d+)', title) or re.search(r'제?\s*(\d+)\s*화', title)
            if match: self.book_meta[fp]['Number'] = str(int(match.group(1)))
        self._load_dict_to_ui(self.current_meta_file)
        if show_toast: Toast.show(self.main_app, t.get("t3_msg_auto_chap_done", ""))

    def action_auto_pages(self, show_toast=True):
        t = self.main_app.i18n[self.main_app.lang]
        if not self.current_meta_file: return
        parent_dir = str(Path(self.current_meta_file).parent)
        for f in self.meta_data.get(parent_dir, []):
            fp = str(f); ext = f.suffix.lower(); img_count = 0
            if ext in ['.zip', '.cbz']:
                try:
                    with zipfile.ZipFile(fp, 'r') as zf:
                        img_count = sum(1 for info in zf.infolist() if not info.is_dir() and Path(info.filename).suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp', '.bmp'})
                except: pass
            if img_count > 0: self.book_meta[fp]['PageCount'] = str(img_count)
        self._load_dict_to_ui(self.current_meta_file)
        if show_toast: Toast.show(self.main_app, t.get("t3_msg_auto_pages_done", ""))

    def remove_selected(self):
        selected_items = self.tree_meta_files.selectedItems()
        if not selected_items: return
        first_selected = selected_items[0]; parent = first_selected.parent() or first_selected
        top_idx = self.tree_meta_files.indexOfTopLevelItem(parent); child_idx = parent.indexOfChild(first_selected) if first_selected.parent() else 0
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
                if not self.meta_data[parent_dir]: del self.meta_data[parent_dir]
            if fp in self.book_meta: del self.book_meta[fp]
        if self.current_meta_file in fps_to_remove:
            self.current_meta_file = None; self.lbl_meta_cover.setPixmap(QPixmap()); self.lbl_meta_cover.setText(self.main_app.i18n[self.main_app.lang].get("t3_cover", ""))
            for key, field in self.meta_ui_fields.items():
                if field.get('is_combo'): field['my'].setCurrentText("")
                elif field.get('is_text'): field['my'].setPlainText("")
                elif field.get('is_tag'): field['my'].setText("")
                else: field['my'].setText("")
            self.set_right_panel_active(False)
        self.refresh_tree()
        total_top = self.tree_meta_files.topLevelItemCount()
        if total_top > 0:
            valid_top_idx = min(top_idx, total_top - 1); new_parent = self.tree_meta_files.topLevelItem(valid_top_idx)
            if new_parent.childCount() > 0:
                valid_child_idx = min(child_idx, new_parent.childCount() - 1); self.tree_meta_files.setCurrentItem(new_parent.child(valid_child_idx))
            else: self.tree_meta_files.setCurrentItem(new_parent)

    def clear_list(self):
        self.meta_data.clear(); self.book_meta.clear(); self.current_meta_file = None
        self.lbl_meta_cover.setPixmap(QPixmap()); self.lbl_meta_cover.setText(self.main_app.i18n[self.main_app.lang].get("t3_cover", ""))
        self.refresh_tree(); self.set_right_panel_active(False)

    def _create_comicinfo_xml(self, data):
        root = ET.Element('ComicInfo', attrib={'xmlns:xsi': 'http://www.w3.org/2001/XMLSchema-instance', 'xmlns:xsd': 'http://www.w3.org/2001/XMLSchema'})
        for k, v in data.items():
            if v and k not in ['ComicZipAddedDate', 'ComicZipModifiedDate']: ET.SubElement(root, k).text = str(v)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if 'ComicZipAddedDate' not in data or not data['ComicZipAddedDate']: ET.SubElement(root, 'ComicZipAddedDate').text = now_str
        else: ET.SubElement(root, 'ComicZipAddedDate').text = data['ComicZipAddedDate']
        ET.SubElement(root, 'ComicZipModifiedDate').text = now_str
        data['ComicZipAddedDate'] = ET.SubElement(root, 'ComicZipAddedDate').text; data['ComicZipModifiedDate'] = now_str
        return '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding='utf-8').decode('utf-8')

    def _inject_xml_to_archive(self, archive_path, xml_str):
        t = self.main_app.i18n[self.main_app.lang]
        ext = Path(archive_path).suffix.lower()
        if ext not in ['.zip', '.cbz', '.7z', '.rar', '.cbr']: 
            return False, t.get("t3_msg_unsupported_format", "미지원 포맷입니다.")
            
        if ext in ['.zip', '.cbz']:
            try:
                has_xml = False
                with zipfile.ZipFile(archive_path, 'r') as zf:
                    has_xml = any(name.lower() == 'comicinfo.xml' for name in zf.namelist())

                if not has_xml:
                    with zipfile.ZipFile(archive_path, 'a', compression=zipfile.ZIP_DEFLATED) as zf:
                        zf.writestr('ComicInfo.xml', xml_str)
                    return True, t.get("msg_success", "성공")
            except Exception:
                pass 

        winrar_paths = [
            r"C:\Program Files\WinRAR\WinRAR.exe",
            r"C:\Program Files (x86)\WinRAR\WinRAR.exe"
        ]
        winrar_exe = next((p for p in winrar_paths if os.path.exists(p)), None)

        if ext in ['.rar', '.cbr'] and not winrar_exe:
            error_msg = "RAR/CBR 파일에 메타데이터를 저장하려면 PC에 WinRAR가 설치되어 있어야 합니다.\n(안정성을 위해 CBZ 포맷으로 변환 후 사용을 권장합니다.)" if self.main_app.lang == "ko" else "WinRAR is required to update RAR/CBR files.\n(Converting to CBZ format is highly recommended.)"
            return False, error_msg

        temp_ssd_dir = tempfile.gettempdir() 
        with tempfile.TemporaryDirectory() as tmp_dir:
            xml_path = os.path.join(tmp_dir, "ComicInfo.xml")
            with open(xml_path, "w", encoding="utf-8") as f:
                f.write(xml_str)
            
            if winrar_exe and ext != '.7z':
                cmd_rar = [winrar_exe, 'u', '-ibck', '-inul', '-m0', '-ep', archive_path, "ComicInfo.xml"]
                try:
                    res = subprocess.run(cmd_rar, cwd=tmp_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
                    if res.returncode == 0:
                        return True, t.get("msg_success", "성공")
                except Exception:
                    pass 

            if ext in ['.zip', '.cbz', '.7z']:
                cmd_7z = [
                    self.main_app.seven_zip_path, 'u', archive_path, "ComicInfo.xml", 
                    "-mx=0", 
                    f"-w{temp_ssd_dir}", 
                    "-mmt=on"
                ]
                try:
                    res = subprocess.run(cmd_7z, cwd=tmp_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
                    if res.returncode == 0: 
                        return True, t.get("msg_success", "성공")
                    else: 
                        return False, t.get("t3_msg_7z_error", "7z 에러 발생")
                except Exception as e: 
                    return False, str(e)
            
            return False, "업데이트에 실패했습니다."

    def action_save_single(self):
        t = self.main_app.i18n[self.main_app.lang]
        if not self.current_meta_file: return
        
        if hasattr(self.main_app, 'tab1'): self.main_app.tab1.clear_list()
        if hasattr(self.main_app, 'tab2'): self.main_app.tab2.clear_list()
        
        self._save_ui_to_dict(); fp = self.current_meta_file
        
        self.set_right_panel_active(False)
        self.main_app.progress_bar.show()
        self.main_app.progress_bar.setRange(0, 0)
        
        winrar_paths = [r"C:\Program Files\WinRAR\WinRAR.exe", r"C:\Program Files (x86)\WinRAR\WinRAR.exe"]
        has_winrar = any(os.path.exists(p) for p in winrar_paths)
        ext = Path(fp).suffix.lower()
        engine = "7z" if ext == '.7z' or not has_winrar else "WinRAR"
        
        self.main_app.lbl_status.setText(f'{t.get("t3_msg_saving", "저장 중...")} [{engine}]')
        
        targets = {fp: self.book_meta[fp]}
        self.save_worker = SaveWorker(targets, self, is_single=True)
        self.save_worker.finished_single.connect(self._on_save_single_finished)
        self.save_worker.start()

    def _on_save_single_finished(self, success, msg):
        t = self.main_app.i18n[self.main_app.lang]
        self.main_app.progress_bar.hide()
        self.main_app.lbl_status.setText(t.get("status_wait", ""))
        
        if success: 
            Toast.show(self.main_app, t.get("t3_msg_save_single_done", ""))
            self.refresh_tree() 
        else: 
            QMessageBox.warning(self, t.get("msg_failed", ""), t.get("t3_msg_save_failed_reason", "").format(msg=msg))
            self.set_right_panel_active(True)

    def action_save_all(self):
        t = self.main_app.i18n[self.main_app.lang]
        
        if hasattr(self.main_app, 'tab1'): self.main_app.tab1.clear_list()
        if hasattr(self.main_app, 'tab2'): self.main_app.tab2.clear_list()
        
        self._save_ui_to_dict()
        
        targets = {fp: data for fp, data in self.book_meta.items() if os.path.exists(fp)}
        if not targets:
            Toast.show(self.main_app, t.get("t3_msg_no_data_copy", ""))
            return

        self.set_right_panel_active(False)
        self.main_app.progress_bar.show()
        self.main_app.progress_bar.setRange(0, len(targets))
        self.main_app.progress_bar.setValue(0)
        
        winrar_paths = [r"C:\Program Files\WinRAR\WinRAR.exe", r"C:\Program Files (x86)\WinRAR\WinRAR.exe"]
        has_winrar = any(os.path.exists(p) for p in winrar_paths)
        engine = "WinRAR" if has_winrar else "7z"
        
        self.main_app.lbl_status.setText(f'{t.get("t3_msg_saving", "저장 중...")} [{engine}]')

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
        self.main_app.lbl_status.setText(t.get("status_wait", ""))
        
        msg = t.get("t3_msg_save_all_done", "").format(success_count=success_count, fail_count=fail_count)
        Toast.show(self.main_app, msg)
        self.refresh_tree()

    def action_search_api(self):
        t = self.main_app.i18n[self.main_app.lang]
        api_name = self.cb_meta_api.currentText()
        query = self.le_meta_search.text().strip()
        
        if not query:
            Toast.show(self.main_app, "검색어를 입력해주세요." if self.main_app.lang == "ko" else "Please enter a search keyword.")
            return
            
        series_val = self.meta_ui_fields['Series']['my'].text().strip()
        h1_text = series_val if series_val else query
            
        dialog = ApiSearchDialog(api_name, query, h1_text, self, t)
        if dialog.exec():
            result_data = dialog.get_selected_data()
            if result_data:
                self._apply_api_data_to_res(result_data)

    def _apply_api_data_to_res(self, data):
        if 'Summary' in data and data['Summary']:
            import re
            summary = data['Summary']
            summary = summary.replace("<책소개>", "").replace("&lt;책소개&gt;", "")
            summary = re.sub(r'\n{2,}', '\n', summary)
            data['Summary'] = summary.strip()

        for d_key, field in self.meta_ui_fields.items():
            res_widget = field['res']
            val = data.get(d_key, "")
            
            if not val or val == "-":
                val = ""
                
            if hasattr(res_widget, "setCurrentText") and res_widget.isEditable():
                res_widget.setCurrentText(str(val))
            elif hasattr(res_widget, "findText"):
                if val:
                    idx = res_widget.findText(str(val))
                    if idx >= 0: res_widget.setCurrentIndex(idx)
                    else: res_widget.setCurrentIndex(0)
                else:
                    res_widget.setCurrentIndex(0) 
            elif hasattr(res_widget, "setPlainText"):
                res_widget.setPlainText(str(val))
            elif hasattr(res_widget, "setText"):
                res_widget.setText(str(val))
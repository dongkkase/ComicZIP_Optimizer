import os
import threading
import zipfile
from pathlib import Path
import qtawesome as qta
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QComboBox, QLineEdit, QFrame, QTableWidgetItem, QAbstractItemView, QHeaderView, QSizePolicy, QTableWidget, QMessageBox, QStackedWidget, QCheckBox)
from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QImage, QPixmap, QPainter, QPainterPath, QColor, QIntValidator

from ui.widgets import ArchiveTableWidget
from utils import natural_keys
from config import get_resource_path
from core.archive_utils import bg_load_image
from tasks.load_task import FileLoadTask

class Tab2Renamer(QWidget):
    def __init__(self, main_app):
        super().__init__()
        self.main_app = main_app
        self.archive_data = {}
        self.current_archive_path = None
        self.all_checked = True
        
        self.archive_timer = QTimer()
        self.archive_timer.setSingleShot(True)
        self.archive_timer.timeout.connect(self._process_archive_select)

        self.inner_timer = QTimer()
        self.inner_timer.setSingleShot(True)
        self.inner_timer.timeout.connect(self._process_inner_select)
        
        self.setup_ui()

    def update_icons(self, is_dark):
        empty_c = "#aaaaaa" if is_dark else "#9CA3AF"
        self.icon_empty_arch.setPixmap(qta.icon('fa5s.folder-open', color=empty_c).pixmap(64, 64))
        
        icon_c = 'white' if is_dark else '#1F2937'
        if hasattr(self, 'btn_minus_num'):
            self.btn_minus_num.setIcon(qta.icon('fa5s.minus', color=icon_c))
            self.btn_plus_num.setIcon(qta.icon('fa5s.plus', color=icon_c))

    def setup_ui(self):
        t = self.main_app.i18n[self.main_app.lang]
        layout = QHBoxLayout(self)
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
        
        # 🌟 시작 번호 라벨
        self.lbl_start_num = QLabel(t.get("tab2_start_num", "시작 번호:"))
        self.lbl_start_num.setObjectName("boldLabel")
        
        # 🌟 시작 번호 인풋 (숫자만 입력 가능)
        self.le_start_num = QLineEdit("0")
        self.le_start_num.setFixedWidth(50)
        self.le_start_num.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.le_start_num.setValidator(QIntValidator(0, 999999))
        
        is_dark = getattr(self.main_app, 'is_dark_mode', True)
        icon_c = 'white' if is_dark else '#1F2937'
        
        # 🌟 - 버튼 (어썸 폰트 적용)
        self.btn_minus_num = QPushButton()
        self.btn_minus_num.setIcon(qta.icon('fa5s.minus', color=icon_c))
        self.btn_minus_num.setFixedWidth(28)
        self.btn_minus_num.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # 🌟 + 버튼 (어썸 폰트 적용)
        self.btn_plus_num = QPushButton()
        self.btn_plus_num.setIcon(qta.icon('fa5s.plus', color=icon_c))
        self.btn_plus_num.setFixedWidth(28)
        self.btn_plus_num.setCursor(Qt.CursorShape.PointingHandCursor)

        # 시작 번호 증감 함수
        def change_num(delta):
            try:
                val = int(self.le_start_num.text() or 0)
            except ValueError:
                val = 0
            new_val = max(0, val + delta)
            self.le_start_num.setText(str(new_val))
            self.update_inner_preview_list()

        self.btn_minus_num.clicked.connect(lambda: change_num(-1))
        self.btn_plus_num.clicked.connect(lambda: change_num(1))
        self.le_start_num.textChanged.connect(self.update_inner_preview_list)
        
        # '내부 파일명 유지' 체크박스
        self.chk_keep_name = QCheckBox(t.get("tab2_keep_name", "내부 파일명 유지"))
        self.chk_keep_name.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_keep_name.setStyleSheet("font-weight: bold; color: #E67E22;")
        self.chk_keep_name.toggled.connect(self.on_keep_name_toggled)
        
        options_layout.addWidget(self.lbl_pattern)
        options_layout.addWidget(self.cb_pattern, 1)
        options_layout.addWidget(self.entry_custom)
        
        # 🌟 순서대로 배치: 라벨 -> 입력창 -> 마이너스 -> 플러스
        options_layout.addWidget(self.lbl_start_num)
        options_layout.addWidget(self.le_start_num)
        options_layout.addWidget(self.btn_minus_num)
        options_layout.addWidget(self.btn_plus_num)
        
        options_layout.addWidget(self.chk_keep_name)
        right_layout.addWidget(options_frame)

        self.lbl_target = QLabel()
        self.lbl_target.setObjectName("boldLabel")
        right_layout.addWidget(self.lbl_target)

        self.stacked_archives = QStackedWidget()
        page_empty = QWidget()
        layout_empty = QVBoxLayout(page_empty)
        
        self.icon_empty_arch = QLabel()
        self.icon_empty_arch.setPixmap(qta.icon('fa5s.folder-open', color='#aaaaaa').pixmap(64, 64))
        self.icon_empty_arch.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.lbl_empty_arch = QLabel(t.get("drag_drop", ""))
        self.lbl_empty_arch.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_empty_arch.setStyleSheet("color: #aaaaaa; font-size: 16px; font-weight: bold;")
        
        layout_empty.addStretch()
        layout_empty.addWidget(self.icon_empty_arch)
        layout_empty.addWidget(self.lbl_empty_arch)
        layout_empty.addStretch()
        self.stacked_archives.addWidget(page_empty)

        self.table_archives = ArchiveTableWidget(0, 3)
        self.table_archives.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_archives.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_archives.verticalHeader().setVisible(False) 
        
        self.table_archives.itemSelectionChanged.connect(self.on_archive_select)
        self.table_archives.itemChanged.connect(self.on_table_item_changed)
        self.table_archives.delete_pressed.connect(self.remove_highlighted)
        self.stacked_archives.addWidget(self.table_archives)
        
        header_arch = self.table_archives.horizontalHeader()
        header_arch.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header_arch.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table_archives.setColumnWidth(1, 90)
        header_arch.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table_archives.setColumnWidth(2, 90)
        self.table_archives.setMinimumHeight(150)
        
        right_layout.addWidget(self.stacked_archives, 1) 

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

    def retranslate_ui(self, t, lang):
        self.lbl_cover_title.setText(t["cover_preview"])
        self.lbl_inner_title.setText(t["inner_preview"])
        self.lbl_pattern.setText(t["pattern_lbl"])
        self.lbl_empty_arch.setText(t.get("drag_drop", ""))
        self.chk_keep_name.setText(t.get("tab2_keep_name", "내부 파일명 유지"))
        self.lbl_start_num.setText(t.get("tab2_start_num", "시작 번호:"))
        
        self.cb_pattern.blockSignals(True)
        self.cb_pattern.clear()
        self.cb_pattern.addItems(t["patterns"])
        self.cb_pattern.blockSignals(False)
        self.cb_pattern.setCurrentIndex(0)
        
        self.lbl_target.setText(t["target_lbl"])
        self.lbl_inner.setText(t["inner_lbl"])
        self.table_archives.setHorizontalHeaderLabels([t["col_name"], t["col_count"], t["col_size"]])
        self.table_inner.setHorizontalHeaderLabels([t["col_old"], t["col_new"], t["col_fsize"]])
        self.lbl_total_count.setText(t["total_files"].format(count=len(self.archive_data)))
        
        if not self.current_archive_path:
            self.render_image("cover", None, None)
            self.render_image("inner", None, None)

    def on_pattern_change(self, value):
        t = self.main_app.i18n[self.main_app.lang]["patterns"]
        if value == t[4]: self.entry_custom.setEnabled(True); self.entry_custom.setFocus()
        else: self.entry_custom.setEnabled(False)
        self.update_inner_preview_list()

    def on_keep_name_toggled(self, checked):
        self.cb_pattern.setEnabled(not checked)
        self.le_start_num.setEnabled(not checked)
        self.btn_minus_num.setEnabled(not checked)
        self.btn_plus_num.setEnabled(not checked)
        if checked:
            self.entry_custom.setEnabled(False)
        else:
            self.on_pattern_change(self.cb_pattern.currentText())
        self.update_inner_preview_list()

    def on_table_item_changed(self, item):
        if item.column() == 0:
            fp = item.data(Qt.ItemDataRole.UserRole)
            if fp in self.archive_data:
                self.archive_data[fp]['checked'] = (item.checkState() == Qt.CheckState.Checked)

    def refresh_list(self):
        if not self.archive_data:
            self.stacked_archives.setCurrentIndex(0)
            self.table_inner.setRowCount(0)
            self.lbl_image = self.lbl_cover_img
            self.render_image("cover", None, None)
            self.render_image("inner", None, None)
            self.lbl_total_count.setText(self.main_app.i18n[self.main_app.lang]["total_files"].format(count=0))
            return
            
        self.stacked_archives.setCurrentIndex(1)
        self.table_archives.setUpdatesEnabled(False)
        self.table_archives.blockSignals(True)
        self.table_archives.clearContents()
        self.table_archives.setRowCount(0)
        
        fmt_key = self.main_app.config.get("target_format", "none")
        webp_on = self.main_app.config.get("webp_conversion", False)
        
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
        self.lbl_total_count.setText(self.main_app.i18n[self.main_app.lang]["total_files"].format(count=len(self.archive_data)))

    def update_inner_preview_list(self):
        if not self.current_archive_path or self.current_archive_path not in self.archive_data: return
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
        flatten = self.main_app.config.get("flatten_folders", False)
        webp_on = self.main_app.config.get("webp_conversion", False)
        keep_name = self.chk_keep_name.isChecked()
        
        # 🌟 시작 번호 가져오기
        try:
            start_num = int(self.le_start_num.text() or 0)
        except ValueError:
            start_num = 0

        for idx, e in enumerate(entries):
            old = e['filename']
            ext = ".webp" if webp_on else (os.path.splitext(old)[1] or ".jpg")
            pad = 2 if total < 100 else (3 if total < 1000 else 4)
            
            # 🌟 현재 인덱스에 시작 번호를 더해서 오프셋 적용
            n = start_num + idx
            
            if keep_name: new = os.path.splitext(os.path.basename(old))[0] + ext
            elif pat_idx == 1: new = f"Cover{ext}" if idx==0 else f"Page_{n:0{pad}d}{ext}"
            elif pat_idx == 2: new = f"{stem.replace(' ','_')}_{n:0{pad}d}{ext}"
            elif pat_idx == 3: new = f"{stem.replace(' ','_')}_Cover{ext}" if idx==0 else f"{stem.replace(' ','_')}_Page_{n:0{pad}d}{ext}"
            elif pat_idx == 4: new = f"{cust_txt.strip() or 'Custom'}_{n:0{pad}d}{ext}"
            else: new = f"{n:0{pad}d}{ext}"

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

    def on_archive_select(self): self.archive_timer.start(150) 
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
        
        if target: 
            threading.Thread(target=bg_load_image, args=(fp, target['original_name'], self.archive_data[fp]['ext'], "cover", self.main_app.seven_zip_path, self.main_app.signals), daemon=True).start()
        else: self.render_image("cover", fp, None)

    def _process_inner_select(self):
        selected = self.table_inner.selectedItems()
        if not selected or not getattr(self, 'current_archive_path', None): return
        orig_fp = self.table_inner.item(selected[0].row(), 0).data(Qt.ItemDataRole.UserRole)
        ext = self.archive_data[self.current_archive_path]['ext']
        threading.Thread(target=bg_load_image, args=(self.current_archive_path, orig_fp, ext, "inner", self.main_app.seven_zip_path, self.main_app.signals), daemon=True).start()

    def render_image(self, target_id, arc_path, img_data):
        if arc_path and getattr(self, 'current_archive_path', None) != arc_path:
            return

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
            label_widget.setText(self.main_app.i18n[self.main_app.lang]["no_preview"] if target_id == "cover" else self.main_app.i18n[self.main_app.lang]["no_image"])
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
        except Exception:
            label_widget.setText(self.main_app.i18n[self.main_app.lang]["no_image"])

    def toggle_all_checkboxes(self):
        self.all_checked = not self.all_checked
        for fp in self.archive_data: self.archive_data[fp]['checked'] = self.all_checked
        self.refresh_list()

    def remove_selected(self):
        self.archive_timer.stop()
        self.inner_timer.stop()
        fps_to_remove = [fp for fp, data in self.archive_data.items() if data.get('checked', False)]
        for fp in fps_to_remove: del self.archive_data[fp]
        self.refresh_list()
        if self.table_archives.rowCount() > 0: self.table_archives.selectRow(0) 
        else: 
            self.table_inner.setRowCount(0); self.render_image("cover", None, None); self.render_image("inner", None, None)
            self.current_archive_path = None

    def remove_highlighted(self):
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
        for fp in fps_to_remove: del self.archive_data[fp]
        self.refresh_list()
        
        total_rows = self.table_archives.rowCount()
        if total_rows > 0: self.table_archives.selectRow(min(next_select_row, total_rows - 1)) 
        else: 
            self.table_inner.setRowCount(0); self.render_image("cover", None, None); self.render_image("inner", None, None)
            self.current_archive_path = None

    def clear_list(self):
        self.archive_timer.stop()
        self.inner_timer.stop()
        self.archive_data.clear()
        self.refresh_list()
        self.table_inner.setRowCount(0)
        self.render_image("cover", None, None); self.render_image("inner", None, None)
        self.current_archive_path = None

    def get_targets(self):
        return [fp for fp, d in self.archive_data.items() if d.get('checked', False)]

    def get_pattern(self):
        if self.chk_keep_name.isChecked():
            return "__KEEP_NAME__"
        return self.cb_pattern.currentText()

    def get_custom_text(self):
        return self.entry_custom.text()

    # 🌟 메인 작업 객체(RenameTask)에 값을 전달하기 위한 함수
    def get_start_num(self):
        try:
            return int(self.le_start_num.text() or 0)
        except ValueError:
            return 0
        
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
                if not os.path.exists(self.main_app.seven_zip_path): return False
                task = FileLoadTask([], self.main_app.seven_zip_path, self.main_app.lang, self.main_app.signals)
                entries = sorted(task.get_7z_entries(filepath), key=lambda x: natural_keys(x['filename']))

            image_exts = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'}
            img_entries = [e for e in entries if Path(e['filename']).suffix.lower() in image_exts]
            if not img_entries: return False 

            nested_exts = {'.zip', '.cbz', '.cbr', '.7z', '.rar', '.alz', '.egg'}
            if any(Path(e['filename']).suffix.lower() in nested_exts for e in entries):
                if not batch_mode:
                    msg = f"[{os.path.basename(filepath)}]\n내부에 압축 파일이 포함되어 제외됩니다." if self.main_app.lang == "ko" else f"[{os.path.basename(filepath)}]\nContains nested archives. Skipped."
                    QMessageBox.warning(self, "Warning", msg)
                return "nested"

            self.archive_data[filepath] = {
                'checked': True,
                'entries': img_entries, 'size_mb': size_mb, 'name': os.path.basename(filepath), 'ext': ext
            }
            return True
        except: return False
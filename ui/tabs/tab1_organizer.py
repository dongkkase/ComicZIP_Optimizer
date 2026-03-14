import os
from pathlib import Path
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QLineEdit, QAbstractItemView, QHeaderView, QTreeWidgetItem)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QColor

from ui.widgets import OrgTreeWidget

class Tab1Organizer(QWidget):
    def __init__(self, main_app):
        super().__init__()
        self.main_app = main_app
        self.org_data = {}
        self.all_checked = True
        self.is_expanded = True
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        ctrl_layout = QHBoxLayout()
        self.btn_toggle_expand = QPushButton()
        self.btn_toggle_expand.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_expand.clicked.connect(self.toggle_expand)
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
        
        self.tree_org.itemChanged.connect(self.on_item_changed)
        self.tree_org.delete_pressed.connect(self.remove_highlighted)
        
        self.lbl_count = QLabel()
        self.lbl_count.setObjectName("infoLabel")
        
        layout.addWidget(self.tree_org, 1)
        layout.addWidget(self.lbl_count, alignment=Qt.AlignmentFlag.AlignCenter)

    def retranslate_ui(self, t, lang):
        self.btn_toggle_expand.setText("↕ 전체 펼치기 / 접기" if lang == "ko" else "↕ Expand / Collapse All")
        self.btn_batch_default.setText(t["batch_default"])
        self.btn_batch_title.setText(t["batch_title"])
        self.tree_org.setHeaderLabels([t["col_org_name"], t["col_org_path"], t["col_org_count"], t["col_org_size"]])
        self.lbl_count.setText(t["total_files"].format(count=len(self.org_data)))

    def toggle_expand(self):
        if self.tree_org.topLevelItemCount() == 0: return
        self.is_expanded = not self.tree_org.topLevelItem(0).isExpanded()
        for i in range(self.tree_org.topLevelItemCount()):
            self.tree_org.topLevelItem(i).setExpanded(self.is_expanded)

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

    def on_item_changed(self, item, col):
        if col == 0 and item.parent() is None:
            fp = item.data(0, Qt.ItemDataRole.UserRole)
            if fp in self.org_data:
                self.org_data[fp]['checked'] = (item.checkState(0) == Qt.CheckState.Checked)

    def refresh_list(self):
        self.tree_org.setUpdatesEnabled(False)
        self.tree_org.blockSignals(True)
        self.tree_org.clear()
        
        target_ext = f".{self.main_app.config.get('target_format', 'zip')}" if self.main_app.config.get("target_format", "none") != "none" else ""
        items_to_add = []
        widgets_to_set = []
        
        for fp, data in self.org_data.items():
            root_item = QTreeWidgetItem()
            root_item.setData(0, Qt.ItemDataRole.UserRole, fp)
            root_item.setFlags(root_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            root_item.setCheckState(0, Qt.CheckState.Checked if data.get('checked', True) else Qt.CheckState.Unchecked)
            root_item.setSizeHint(0, QSize(0, 36)) 
            
            root_item.setText(0, f"📦 {data['name']}")
            vol_count_text = f"{len(data['volumes'])} Items" if self.main_app.lang == 'en' else f"{len(data['volumes'])} 권/화"
            root_item.setText(2, vol_count_text) 
            root_item.setText(3, f"{data['size_mb']:.1f} MB") 
            
            path_widget = QWidget()
            path_layout = QHBoxLayout(path_widget)
            path_layout.setContentsMargins(5, 2, 5, 2)
            path_layout.setSpacing(5)
            
            le_path = QLineEdit()
            default_path = os.path.dirname(fp)
            title_path = os.path.join(default_path, "제목없음_수정필요" if data['clean_title'] == "제목없음" else data['clean_title'])
            
            if 'out_path' not in data:
                data['out_path'] = default_path
            le_path.setText(data['out_path'])
            le_path.textChanged.connect(lambda text, key=fp: self.update_out_path(key, text))
            data['le_path'] = le_path 
            
            btn_def = QPushButton("기본값" if self.main_app.lang == "ko" else "Default")
            btn_def.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_def.clicked.connect(lambda _, key=fp, p=default_path: self.set_single_path(key, p))
            
            btn_tit = QPushButton("책제목" if self.main_app.lang == "ko" else "Title")
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
                final_ext = target_ext if target_ext else (Path(vol.get('inner_path', '')).suffix if vol.get('type') == 'archive' else ".zip")
                if not final_ext: final_ext = ".zip"
                
                child.setText(0, f"  ↳ {icon_txt} {vol['new_name']}{final_ext}")
                child.setForeground(0, QColor("#aaaaaa"))
                
            items_to_add.append(root_item)
            widgets_to_set.append((root_item, path_widget)) 
            
        self.tree_org.addTopLevelItems(items_to_add)
        for item, widget in widgets_to_set:
            self.tree_org.setItemWidget(item, 1, widget)
        
        for i in range(self.tree_org.topLevelItemCount()):
            self.tree_org.topLevelItem(i).setExpanded(self.is_expanded)
            
        self.tree_org.blockSignals(False)
        self.tree_org.setUpdatesEnabled(True)
        self.lbl_count.setText(self.main_app.i18n[self.main_app.lang]["total_files"].format(count=len(self.org_data)))

    def toggle_all_checkboxes(self):
        self.all_checked = not self.all_checked
        for fp in self.org_data:
            self.org_data[fp]['checked'] = self.all_checked
        self.refresh_list()

    def remove_selected(self):
        fps_to_remove = [fp for fp, data in self.org_data.items() if data.get('checked', False)]
        for fp in fps_to_remove: del self.org_data[fp]
        self.refresh_list()

    def remove_highlighted(self):
        selected_items = self.tree_org.selectedItems()
        if not selected_items: return
        top_level_indices = []
        fps_to_remove = []
        for item in selected_items:
            parent = item.parent() if item.parent() else item
            idx = self.tree_org.indexOfTopLevelItem(parent)
            top_level_indices.append(idx)
            fp = parent.data(0, Qt.ItemDataRole.UserRole)
            if fp and fp not in fps_to_remove: fps_to_remove.append(fp)
                
        if not fps_to_remove: return
        next_select_row = sorted(top_level_indices)[0]  
        for fp in fps_to_remove: del self.org_data[fp]
        self.refresh_list()
        
        total_rows = self.tree_org.topLevelItemCount()
        if total_rows > 0:
            self.tree_org.topLevelItem(min(next_select_row, total_rows - 1)).setSelected(True)

    def clear_list(self):
        self.org_data.clear()
        self.refresh_list()

    def get_targets(self):
        return [fp for fp, d in self.org_data.items() if d.get('checked', False)]
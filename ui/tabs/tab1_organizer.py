import os
import re
import html
from pathlib import Path
import qtawesome as qta
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLabel, QLineEdit, QAbstractItemView, QHeaderView, QTreeWidgetItem, QStackedWidget,
                             QMenu, QDialog, QDialogButtonBox,
                             QStyledItemDelegate, QStyle, QApplication
                             )
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QColor,QTextDocument, QAbstractTextDocumentLayout

from ui.widgets import OrgTreeWidget

class RichTextDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        text = index.data(Qt.ItemDataRole.DisplayRole)
        
        if text and "||" in text:
            options = option
            self.initStyleOption(options, index)
            options.text = ""
            
            style = options.widget.style() if options.widget else QApplication.style()
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, options, painter, options.widget)
            
            parts = text.split("||")
            main_text = html.escape(parts[0])
            orig_text = html.escape(parts[1]) if len(parts) > 1 else ""
            is_spinoff = len(parts) > 2 and parts[2] == "SPINOFF"
            
            # 부모(루트) 아이템인지 자식 아이템인지 판별
            is_parent = not index.parent().isValid()
            
            if is_parent:
                main_color = "rgba(255, 255, 255, 1)"
                orig_color = "rgba(255, 255, 255, 0.5)"
            else:
                main_color = "rgba(255, 255, 255, 0.8)"
                orig_color = "rgba(255, 255, 255, 0.5)"
            
            warning_icon = "<span style='color: #f1c40f; font-family: \"Font Awesome 5 Free Solid\", \"FontAwesome\", sans-serif;'>&#xf071;</span> " if is_spinoff else ""
            
            # 원본 파일명이 있을 경우 탭 2개 적용
            spacer = "\t\t" if orig_text else ""
            
            html_str = f"<span style='color: {main_color}; white-space: pre;'>{main_text}</span>{warning_icon}<span style='color: {orig_color}; white-space: pre;'>{spacer}({orig_text})</span>"
            doc = QTextDocument()
            doc.setHtml(html_str)
            doc.setDefaultFont(options.font)
            
            # 탭 사이즈 강제 지정 (HTML 환경에서 \t가 무시되는 현상 방지)
            option_text = doc.defaultTextOption()
            option_text.setTabStopDistance(30.0)
            doc.setDefaultTextOption(option_text)
            
            painter.save()
            textRect = style.subElementRect(QStyle.SubElement.SE_ItemViewItemText, options)
            painter.translate(textRect.left(), textRect.top() + 2)
            ctx = QAbstractTextDocumentLayout.PaintContext()
            doc.documentLayout().draw(painter, ctx)
            painter.restore()
        else:
            super().paint(painter, option, index)

    def sizeHint(self, option, index):
        text = index.data(Qt.ItemDataRole.DisplayRole)
        
        if text and "||" in text:
            options = option
            self.initStyleOption(options, index)
            parts = text.split("||")
            main_text = html.escape(parts[0])
            orig_text = html.escape(parts[1]) if len(parts) > 1 else ""
            is_spinoff = len(parts) > 2 and parts[2] == "SPINOFF"
            
            warning_icon = "<span style='font-family: \"Font Awesome 5 Free Solid\", \"FontAwesome\", sans-serif;'>&#xf071;</span> " if is_spinoff else ""
            spacer = "\t\t" if orig_text else ""
            
            doc = QTextDocument()
            doc.setHtml(f"<span style='white-space: pre;font-weight: bold;'>{main_text}</span>{warning_icon}<span style='white-space: pre;'>{spacer}({orig_text})</span>")
            doc.setDefaultFont(options.font)
            
            option_text = doc.defaultTextOption()
            option_text.setTabStopDistance(30.0)
            doc.setDefaultTextOption(option_text)
            
            return QSize(int(doc.idealWidth()), int(doc.size().height()) + 0)
            
        return super().sizeHint(option, index)

class Tab1Organizer(QWidget):
    def __init__(self, main_app):
        super().__init__()
        self.main_app = main_app
        self.org_data = {}
        self.all_checked = True
        self.is_expanded = True
        self.setup_ui()

    def batch_change_unit(self, fp, target_unit):
        """특정 부모(fp) 하위의 모든 자식 아이템의 이름을 지정된 단위(권/화)로 일괄 변경합니다."""
        if fp not in self.org_data: return
        
        for vol in self.org_data[fp]['volumes']:
            old_name = vol.get('new_name', '')
            
            # 기존 단위(권, 화, Vol, Ch 등)가 끝에 있으면 제거
            clean_name = re.sub(r'\s*(권|화|Vol|Ch|Volume|Chapter)\.?$', '', old_name, flags=re.IGNORECASE).strip()
            
            # 영문 단위일 경우 앞에 공백 추가, 한글은 붙여서 씀
            if target_unit in ['Vol', 'Ch']:
                vol['new_name'] = f"{clean_name} {target_unit}"
            else:
                vol['new_name'] = f"{clean_name}{target_unit}"
                
        self.refresh_list()

    def setup_ui(self):
        t = self.main_app.i18n[self.main_app.lang]
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
        
        self.stacked_org = QStackedWidget()
        page_empty = QWidget()
        layout_empty = QVBoxLayout(page_empty)
        
        self.icon_empty_org = QLabel()
        self.icon_empty_org.setPixmap(qta.icon('fa5s.folder-open', color='#aaaaaa').pixmap(64, 64))
        self.icon_empty_org.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.lbl_empty_org = QLabel(t.get("drag_drop", ""))
        self.lbl_empty_org.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_empty_org.setStyleSheet("color: #aaaaaa; font-size: 16px; font-weight: bold;")
        
        layout_empty.addStretch()
        layout_empty.addWidget(self.icon_empty_org)
        layout_empty.addWidget(self.lbl_empty_org)
        layout_empty.addStretch()
        self.stacked_org.addWidget(page_empty)

        self.tree_org = OrgTreeWidget()
        self.tree_org.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree_org.setHeaderLabels(["", "", "", ""])
        
        self.tree_org.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.tree_org.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.tree_org.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.tree_org.header().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.tree_org.header().setStretchLastSection(False) 
        
        self.tree_org.setTextElideMode(Qt.TextElideMode.ElideNone)
        
        # 🌟 긴 파일명이 오면 잘리지 않고 여러 줄로 표시되도록 줄바꿈 허용
        self.tree_org.setWordWrap(True)
        
        self.tree_org.itemChanged.connect(self.on_item_changed)
        self.tree_org.delete_pressed.connect(self.remove_highlighted)
        
        # [기능추가] 더블 클릭 및 우클릭(컨텍스트 메뉴) 이벤트 연결
        self.tree_org.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.tree_org.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_org.customContextMenuRequested.connect(self.show_context_menu)
        
        self.stacked_org.addWidget(self.tree_org)
        
        self.lbl_count = QLabel()
        self.lbl_count.setObjectName("infoLabel")
        
        layout.addWidget(self.stacked_org, 1)
        layout.addWidget(self.lbl_count, alignment=Qt.AlignmentFlag.AlignCenter)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.adjust_columns()

    def adjust_columns(self):
        if not hasattr(self, 'tree_org'): return
        total_w = self.tree_org.viewport().width()
        if total_w <= 0: return
        
        # 항목수와 용량은 80px 고정
        col2_w = 80
        col3_w = 80
        # 경로는 전체 크기의 40% 차지
        col1_w = int(total_w * 0.4)
        # 파일명 컬럼은 남은 공간 모두 차지
        col0_w = max(50, total_w - col1_w - col2_w - col3_w)
        
        self.tree_org.setColumnWidth(0, col0_w)
        self.tree_org.setColumnWidth(1, col1_w)
        self.tree_org.setColumnWidth(2, col2_w)
        self.tree_org.setColumnWidth(3, col3_w)

    def retranslate_ui(self, t, lang):
        self.btn_toggle_expand.setText("↕ 전체 펼치기 / 접기" if lang == "ko" else "↕ Expand / Collapse All")
        self.btn_batch_default.setText(t["batch_default"])
        self.btn_batch_title.setText(t["batch_title"])
        self.lbl_empty_org.setText(t.get("drag_drop", ""))
        self.tree_org.setHeaderLabels([t["col_org_name"], t["col_org_path"], t["col_org_count"], t["col_org_size"]])
        
        # 헤더 텍스트 우측 정렬
        self.tree_org.headerItem().setTextAlignment(2, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.tree_org.headerItem().setTextAlignment(3, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
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
        from PyQt6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem
        
        if not hasattr(self, '_no_check_delegate'):
            class NoCheckDelegate(QStyledItemDelegate):
                def initStyleOption(self, option, index):
                    super().initStyleOption(option, index)
                    option.features &= ~QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator
            
            self._no_check_delegate = NoCheckDelegate(self.tree_org)
            self.tree_org.setItemDelegateForColumn(1, self._no_check_delegate)
            self.tree_org.setItemDelegateForColumn(2, self._no_check_delegate)
            self.tree_org.setItemDelegateForColumn(3, self._no_check_delegate)

        saved_scroll_pos = self.tree_org.verticalScrollBar().value()
        
        if not self.org_data:
            self.stacked_org.setCurrentIndex(0)
            self.lbl_count.setText(self.main_app.i18n[self.main_app.lang]["total_files"].format(count=0))
            return
            
        self.stacked_org.setCurrentIndex(1)
        self.tree_org.setUpdatesEnabled(False)
        self.tree_org.blockSignals(True)
        
        saved_expanded_states = {}
        for i in range(self.tree_org.topLevelItemCount()):
            item = self.tree_org.topLevelItem(i)
            fp = item.data(0, Qt.ItemDataRole.UserRole)
            if fp:
                saved_expanded_states[fp] = item.isExpanded()

        self.tree_org.clear()

        if getattr(self, '_delegate_applied', None) is None:
            self.tree_org.setItemDelegateForColumn(0, RichTextDelegate(self.tree_org))
            self._delegate_applied = True
        
        target_ext = f".{self.main_app.config.get('target_format', 'zip')}" if self.main_app.config.get("target_format", "none") != "none" else ""
        items_to_add = []
        root_widgets_to_set = []
        
        for fp, data in self.org_data.items():
            root_item = QTreeWidgetItem()
            root_item.setData(0, Qt.ItemDataRole.UserRole, fp)
            
            root_item.setCheckState(0, Qt.CheckState.Checked if data.get('checked', True) else Qt.CheckState.Unchecked)
            root_item.setSizeHint(0, QSize(0, 36)) 
            
            root_item.setText(0, f"📦 {data['clean_title']}||{data['name']}") 
            
            vol_count_text = f"{len(data['volumes'])} Items" if self.main_app.lang == 'en' else f"{len(data['volumes'])} 권/화"
            
            root_item.setText(2, vol_count_text) 
            root_item.setText(3, f"{data['size_mb']:.1f} MB")
            
            root_item.setTextAlignment(2, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            root_item.setTextAlignment(3, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            
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
            btn_def.clicked.connect(lambda _, key=fp, p=default_path: self.set_single_path(key, p))
            btn_tit = QPushButton("책제목" if self.main_app.lang == "ko" else "Title")
            btn_tit.clicked.connect(lambda _, key=fp, p=title_path: self.set_single_path(key, p))
            
            # 🌟 [추가됨] 일괄: 권 / 일괄: 화 버튼
            btn_vol = QPushButton("일괄: 권" if self.main_app.lang == "ko" else "All Vol")
            btn_vol.clicked.connect(lambda _, key=fp: self.batch_change_unit(key, "권" if self.main_app.lang == "ko" else "Vol"))
            btn_ch = QPushButton("일괄: 화" if self.main_app.lang == "ko" else "All Ch")
            btn_ch.clicked.connect(lambda _, key=fp: self.batch_change_unit(key, "화" if self.main_app.lang == "ko" else "Ch"))
            
            btn_style = "QPushButton { padding: 4px 8px; font-size: 11px; border-radius: 4px; background-color: #4a4a4a; } QPushButton:hover { background-color: #5a5a5a; }"
            btn_def.setStyleSheet(btn_style)
            btn_tit.setStyleSheet(btn_style)
            btn_vol.setStyleSheet(btn_style)
            btn_ch.setStyleSheet(btn_style)
            le_path.setStyleSheet("padding: 4px; font-size: 11px;")
            
            path_layout.addWidget(le_path, 1)
            path_layout.addWidget(btn_def)
            path_layout.addWidget(btn_tit)
            path_layout.addWidget(btn_vol)  # 추가
            path_layout.addWidget(btn_ch)   # 추가
            
            for vol in data['volumes']:
                child = QTreeWidgetItem(root_item)
                icon_txt = "📦" if vol.get('type') == 'archive' else "📁"
                final_ext = target_ext if target_ext else (Path(vol.get('inner_path', '')).suffix if vol.get('type') == 'archive' else ".zip")
                if not final_ext: final_ext = ".zip"
                
                orig_name = vol.get('original_basename', "")
                spinoff_folder = vol.get('spinoff_folder')
                
                orig_path = vol.get('original_path', '')
                path_parts = Path(orig_path).parts
                prefix = ""
                if len(path_parts) > 1:
                    parent_folder = path_parts[-2]
                    match = re.search(r'(\d+\s*부|제\s*\d+\s*부|시즌\s*\d+|season\s*\d+|part\s*\d+)', parent_folder, re.IGNORECASE)
                    prefix = f"[{match.group(1).strip()}] " if match else f"[{parent_folder}] "
                
                new_display = f"{prefix}{vol['new_name']}{final_ext}"

                spinoff_flag = "SPINOFF" if spinoff_folder else ""
                child.setText(0, f"  ↳ {icon_txt} {new_display}||{orig_name}||{spinoff_flag}")
                child.setToolTip(0, f"{new_display} ({orig_name})")
                
            items_to_add.append(root_item)
            root_widgets_to_set.append((root_item, path_widget)) 
            
        self.tree_org.addTopLevelItems(items_to_add)
        for item, widget in root_widgets_to_set: self.tree_org.setItemWidget(item, 1, widget)
            
        for i in range(self.tree_org.topLevelItemCount()):
            top_item = self.tree_org.topLevelItem(i)
            fp = top_item.data(0, Qt.ItemDataRole.UserRole)
            
            should_expand = saved_expanded_states.get(fp, getattr(self, 'is_expanded', True))
            top_item.setExpanded(should_expand)
            
            for j in range(top_item.childCount()):
                top_item.child(j).setFirstColumnSpanned(True)
                
        self.adjust_columns()
        self.tree_org.blockSignals(False)
        self.tree_org.setUpdatesEnabled(True)
        self.lbl_count.setText(self.main_app.i18n[self.main_app.lang]["total_files"].format(count=len(self.org_data)))

        self.tree_org.verticalScrollBar().setValue(saved_scroll_pos)

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
    
    def on_item_double_clicked(self, item, col):
        """더블 클릭 시 커스텀 팝업 호출"""
        self.edit_child_filename(item)

    def show_context_menu(self, pos):
        """우클릭 시 파일명 변경 컨텍스트 메뉴 표시"""
        item = self.tree_org.itemAt(pos)
        # 선택된 아이템이 2뎁스(자식 아이템)가 아니면 무시
        if not item or not item.parent():
            return

        menu = QMenu(self)
        is_ko = self.main_app.lang == "ko"
        action_rename = menu.addAction("파일 이름 변경" if is_ko else "Rename File")

        # 마우스 위치에 메뉴 표시
        action = menu.exec(self.tree_org.viewport().mapToGlobal(pos))
        if action == action_rename:
            self.edit_child_filename(item)

    def edit_child_filename(self, item):
        """수동 수정 팝업 후 리스트 갱신 대응"""
        parent = item.parent()
        if not parent: return
        fp = parent.data(0, Qt.ItemDataRole.UserRole)
        if fp not in self.org_data: return

        child_idx = parent.indexOfChild(item)
        vol_data = self.org_data[fp]['volumes'][child_idx]
        current_name = vol_data.get('new_name', '')

        is_ko = self.main_app.lang == "ko"
        dialog = QDialog(self)
        dialog.setWindowTitle("파일명 수정" if is_ko else "Edit Filename")
        dialog.setFixedSize(580, 290)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("새 파일명을 입력하세요:" if is_ko else "Enter new filename:"))

        input_field = QLineEdit(current_name)
        font = input_field.font(); font.setPointSize(font.pointSize() + 2)
        input_field.setFont(font); input_field.setMinimumHeight(40)
        layout.addWidget(input_field)
        layout.addStretch()

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(dialog.accept); btn_box.rejected.connect(dialog.reject)
        layout.addWidget(btn_box)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_name = input_field.text().strip()
            if new_name:
                vol_data['new_name'] = new_name
                # 수정 후 UI 업데이트를 위해 refresh_list 호출 (일관성 유지)
                self.refresh_list()

                target_ext = f".{self.main_app.config.get('target_format', 'zip')}" if self.main_app.config.get("target_format", "none") != "none" else ""
                icon_txt = "📦" if vol_data.get('type') == 'archive' else "📁"
                final_ext = target_ext if target_ext else (Path(vol_data.get('inner_path', '')).suffix if vol_data.get('type') == 'archive' else ".zip")
                if not final_ext: final_ext = ".zip"

                orig_path = vol_data.get('original_path', '')
                orig_name = vol_data.get('original_basename', os.path.basename(orig_path.replace('\\', '/')))
                prefix = ""
                
                path_parts = Path(orig_path).parts
                if len(path_parts) > 1:
                    parent_folder = path_parts[-2]
                    match = re.search(r'(\d+\s*부|제\s*\d+\s*부|시즌\s*\d+|season\s*\d+|part\s*\d+)', parent_folder, re.IGNORECASE)
                    if match:
                        prefix = f"[{match.group(1).strip()}] "
                    else:
                        prefix = f"[{parent_folder}] "

                new_display = f"{prefix}{new_name}{final_ext}"
                spinoff_flag = "SPINOFF" if vol_data.get('spinoff_folder') else ""
                
                item.setText(0, f"  ↳ {icon_txt} {new_display}||{orig_name}||{spinoff_flag}")
                item.setToolTip(0, f"{new_display} ({orig_name})")
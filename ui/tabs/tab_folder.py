import os
import sys
import subprocess
import traceback
import shutil
import csv
import zipfile
import xml.etree.ElementTree as ET
import hashlib
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTreeView, 
    QTableView, QListView, QLabel, QPushButton, QSlider, QFrame, QMenu, QMessageBox,
    QHeaderView, QAbstractItemView, QSizePolicy, QDialog, QListWidget, QListWidgetItem, 
    QCheckBox, QDialogButtonBox, QStyledItemDelegate, QStackedWidget, QInputDialog, QToolButton, QStyleFactory,
    QComboBox, QStyle, QLineEdit, QFileDialog, QRubberBand, QTextBrowser, QProgressBar
)
from PyQt6.QtGui import QFileSystemModel, QAction, QPixmap, QPainter, QColor, QFont, QKeySequence, QShortcut, QImage, QPixmapCache
from PyQt6.QtCore import Qt, QDir, QAbstractTableModel, QModelIndex, QSize, QByteArray, QItemSelectionModel, QItemSelection, QStandardPaths, QFileSystemWatcher, QTimer, QMimeData, QUrl, QThread, pyqtSignal, QRect, QPoint

from config import get_resource_path, save_config
from core.library_db import db

# ==========================================
# 스마트 인메모리 스레드
# ==========================================
class MemoryExtractThread(QThread):
    data_extracted = pyqtSignal(str, dict, bool) 
    progress_updated = pyqtSignal(int)
    
    def __init__(self, tasks, seven_zip_path):
        super().__init__()
        self.current_tasks = tasks
        self.seven_zip_path = seven_zip_path
        self.is_cancelled = False
        self.show_progress = False

    def cancel(self):
        self.is_cancelled = True

    def run(self):
        for task in self.current_tasks:
            if self.is_cancelled: return
            
            filepath, needs_img, needs_meta, thumb_path = task
            meta_dict = {}
            img_bytes = b""
            has_img_out = False

            # 1. 썸네일 캐시가 이미 있는지 확인
            if needs_img and thumb_path and os.path.exists(thumb_path):
                # [핵심 방어] 0바이트 파일은 "이미지 없음"으로 판정하고 무한루프 방지
                if os.path.getsize(thumb_path) > 0:
                    qimg = QImage()
                    qimg.load(thumb_path)
                    if not qimg.isNull():
                        has_img_out = True
                        needs_img = False 
                else:
                    has_img_out = True
                    needs_img = False

            if needs_meta or needs_img:
                ext = os.path.splitext(filepath)[1].lower()
                try:
                    if ext in ['.zip', '.cbz']:
                        with zipfile.ZipFile(filepath, 'r') as zf:
                            namelist = zf.namelist()
                            if needs_meta:
                                xml_name = next((f for f in namelist if f.lower() == 'comicinfo.xml'), None)
                                if xml_name:
                                    xml_data = zf.read(xml_name).decode('utf-8', errors='ignore')
                                    meta_dict = self._parse_xml(xml_data)
                            if needs_img:
                                img_files = [f for f in namelist if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.bmp'))]
                                if img_files:
                                    img_files.sort()
                                    img_bytes = zf.read(img_files[0]) 
                    else:
                        cmd_l = [self.seven_zip_path, 'l', '-slt', filepath]
                        res_l = subprocess.run(cmd_l, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
                        lines = res_l.stdout.splitlines()
                        
                        has_xml = False
                        img_candidates = []
                        for line in lines:
                            if line.startswith("Path = "):
                                fname = line.replace("Path = ", "").strip()
                                if fname.lower() == 'comicinfo.xml':
                                    has_xml = True
                                elif needs_img and fname.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.bmp')):
                                    img_candidates.append(fname)
                                    
                        if needs_meta and has_xml:
                            cmd_x = [self.seven_zip_path, 'e', filepath, 'ComicInfo.xml', '-so']
                            res_x = subprocess.run(cmd_x, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                            if res_x.returncode == 0:
                                meta_dict = self._parse_xml(res_x.stdout.decode('utf-8', errors='ignore'))
                                
                        if needs_img and img_candidates:
                            img_candidates.sort()
                            cmd_e = [self.seven_zip_path, 'e', filepath, img_candidates[0], '-so']
                            res_e = subprocess.run(cmd_e, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                            if res_e.returncode == 0:
                                img_bytes = res_e.stdout 
                except Exception:
                    pass

            # 2. 이미지 처리 및 해상도 추출
            if img_bytes and not has_img_out:
                qimg = QImage()
                qimg.loadFromData(img_bytes)
                if not qimg.isNull():
                    meta_dict["resolution"] = f"{qimg.width()} x {qimg.height()}"
                    qimg = qimg.scaled(400, 400, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    if thumb_path:
                        qimg.save(thumb_path, "WEBP", 85)
                    has_img_out = True
                else:
                    # [핵심 방어] 이미지가 손상되었을 경우 0바이트 캐시 생성
                    if thumb_path: open(thumb_path, 'wb').close()
                    has_img_out = True
            elif needs_img and not has_img_out and not img_bytes:
                # [핵심 방어] 압축 파일 내부에 이미지가 아예 없는 경우 0바이트 캐시 생성 (무한 루프 원천 차단)
                if thumb_path: open(thumb_path, 'wb').close()
                has_img_out = True

            self.data_extracted.emit(filepath, meta_dict, has_img_out)
            
            if self.show_progress:
                self.progress_updated.emit(1)
            
    def _parse_xml(self, xml_data):
        meta = {}
        try:
            root = ET.fromstring(xml_data)
            meta["title"] = root.findtext("Title", "")
            meta["series"] = root.findtext("Series", "")
            meta["series_group"] = root.findtext("SeriesGroup", "")
            meta["volume"] = root.findtext("Volume", "")
            meta["number"] = root.findtext("Number", "")
            meta["writer"] = root.findtext("Writer", "")
            meta["penciller"] = root.findtext("Penciller", "")
            meta["inker"] = root.findtext("Inker", "")
            meta["colorist"] = root.findtext("Colorist", "")
            meta["letterer"] = root.findtext("Letterer", "")
            meta["cover_artist"] = root.findtext("CoverArtist", "")
            meta["editor"] = root.findtext("Editor", "")
            meta["publisher"] = root.findtext("Publisher", "")
            meta["imprint"] = root.findtext("Imprint", "")
            meta["genre"] = root.findtext("Genre", "")
            meta["volume_count"] = root.findtext("VolumeCount", "")
            meta["page_count"] = root.findtext("PageCount", "")
            meta["format"] = root.findtext("Format", "")
            meta["manga"] = root.findtext("Manga", "")
            meta["language"] = root.findtext("LanguageISO", "")
            meta["rating"] = root.findtext("CommunityRating") or root.findtext("Rating", "")
            meta["age_rating"] = root.findtext("AgeRating", "")
            meta["year"] = root.findtext("Year", "")
            meta["month"] = root.findtext("Month", "")
            meta["day"] = root.findtext("Day", "")
            meta["summary"] = root.findtext("Summary", "")
            meta["characters"] = root.findtext("Characters", "")
            meta["teams"] = root.findtext("Teams", "")
            meta["locations"] = root.findtext("Locations", "")
            meta["story_arc"] = root.findtext("StoryArc", "")
            meta["tags"] = root.findtext("Tags", "")
            meta["notes"] = root.findtext("Notes", "")
            meta["web"] = root.findtext("Web", "")
        except: pass
        return meta

# ==========================================
# 커스텀 테이블 뷰
# ==========================================
class CustomTableView(QTableView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rubber_band = None
        self._origin = QPoint()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self.indexAt(event.pos()).isValid():
            if not self._rubber_band:
                self._rubber_band = QRubberBand(QRubberBand.Shape.Rectangle, self.viewport())
            self._origin = event.pos()
            self._rubber_band.setGeometry(QRect(self._origin, QSize()))
            self._rubber_band.show()
            
            if not (event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)):
                self.clearSelection()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._rubber_band and self._rubber_band.isVisible():
            rect = QRect(self._origin, event.pos()).normalized()
            self._rubber_band.setGeometry(rect)
            
            row_count = self.model().rowCount()
            if row_count > 0:
                selection = QItemSelection()
                for r in range(row_count):
                    row_rect = self.visualRect(self.model().index(r, 0))
                    row_rect.setWidth(self.viewport().width())
                    
                    if row_rect.intersects(rect):
                        selection.select(self.model().index(r, 0), self.model().index(r, self.model().columnCount() - 1))
                
                if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                    self.selectionModel().select(selection, QItemSelectionModel.SelectionFlag.ClearAndSelect)
                else:
                    self.selectionModel().select(selection, QItemSelectionModel.SelectionFlag.Select)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._rubber_band and self._rubber_band.isVisible():
            self._rubber_band.hide()
            return
        super().mouseReleaseEvent(event)

# ==========================================
# 백그라운드 폴더 스캔 스레드
# ==========================================
class FolderScanThread(QThread):
    progress_updated = pyqtSignal(int)
    scan_finished = pyqtSignal(list, float)
    
    def __init__(self, folder_path, include_sub, target_exts, thumb_dir):
        super().__init__()
        self.folder_path = folder_path
        self.include_sub = include_sub
        self.target_exts = tuple(target_exts)
        self.thumb_dir = thumb_dir
        self.is_cancelled = False

    def run(self):
        paths_to_scan = []
        try:
            if self.include_sub:
                for root, dirs, files in os.walk(self.folder_path):
                    if self.is_cancelled: return
                    for file in files:
                        if file.lower().endswith(self.target_exts):
                            paths_to_scan.append(os.path.join(root, file))
            else:
                for file in os.listdir(self.folder_path):
                    if self.is_cancelled: return
                    if file.lower().endswith(self.target_exts):
                        paths_to_scan.append(os.path.join(self.folder_path, file))
        except Exception:
            pass

        file_data_cache = []
        total_size = 0

        for i, full_path in enumerate(paths_to_scan):
            if self.is_cancelled: return
            try:
                stat = os.stat(full_path)
                mtime = stat.st_mtime
                ctime = stat.st_ctime
                
                file_hash = hashlib.md5(f"{full_path}_{mtime}".encode()).hexdigest()
                thumb_path = os.path.join(self.thumb_dir, f"{file_hash}.webp")
                has_thumb = os.path.exists(thumb_path)
                
                row_dict = {
                    "full_path": full_path, 
                    "hash": file_hash,
                    "name": os.path.basename(full_path),
                    "path": os.path.dirname(full_path), 
                    "ext": os.path.splitext(full_path)[1].lower(), 
                    "raw_size": stat.st_size,
                    "raw_mtime": mtime,
                    "raw_ctime": ctime,
                    "ctime": datetime.fromtimestamp(ctime).strftime('%Y-%m-%d %H:%M'),
                    "mtime": datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M'),
                    "thumb_processed": has_thumb, 
                    "meta_processed": False, 
                    "full_meta": {},
                    "res": "", "series": "", "title": "", "vol": "", "num": "", "writer": "",
                    "display_index": -1 
                }
                file_data_cache.append(row_dict)
                total_size += stat.st_size
                
                if i % 1000 == 0:
                    self.progress_updated.emit(i)
            except Exception: pass

        self.scan_finished.emit(file_data_cache, total_size)

    def cancel(self):
        self.is_cancelled = True

# ==========================================
# 썸네일/타일 뷰용 델리게이트
# ==========================================
class ThumbnailDelegate(QStyledItemDelegate):
    def __init__(self, parent=None, thumb_dir=""):
        super().__init__(parent)
        self.view_mode = "thumbnail"
        self.item_size = 120
        self.thumb_dir = thumb_dir

    def paint(self, painter, option, index):
        if not index.isValid(): return
        
        row_data = index.model()._data[index.row()]
        
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if row_data.get("is_group"):
            painter.fillRect(option.rect, QColor("#2b2b2b"))
            painter.setPen(QColor("#3498DB"))
            font = QFont("맑은 고딕", 11, QFont.Weight.Bold)
            painter.setFont(font)
            text = f"📂 {row_data['name']} ({row_data['count']} 항목)"
            flags = Qt.AlignmentFlag.AlignLeft.value | Qt.AlignmentFlag.AlignVCenter.value
            painter.drawText(option.rect.adjusted(10, 0, -10, -5), flags, text)
            
            painter.setPen(QColor("#555555"))
            painter.drawLine(option.rect.left() + 5, option.rect.bottom() - 2, option.rect.right() - 5, option.rect.bottom() - 2)
            painter.restore()
            return
        
        file_name = row_data.get("name", "")
        file_hash = row_data.get("hash", "")
        
        pixmap = QPixmap()
        if file_hash:
            cached_pixmap = QPixmapCache.find(file_hash)
            if cached_pixmap is not None and not cached_pixmap.isNull():
                pixmap = cached_pixmap
            else:
                thumb_path = os.path.join(self.thumb_dir, f"{file_hash}.webp")
                if row_data.get("thumb_processed") and os.path.exists(thumb_path):
                    # [방어막] 0바이트 파일은 렌더링 시도하지 않음
                    if os.path.getsize(thumb_path) > 0:
                        pixmap.load(thumb_path)
                        if not pixmap.isNull():
                            QPixmapCache.insert(file_hash, pixmap)
        
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor("#3a7ebf"))
            painter.setPen(QColor("white"))
        else:
            painter.setPen(QColor("#cccccc"))
            
        rect = option.rect
        
        if self.view_mode == "thumbnail":
            img_size = self.item_size - 40
            if not pixmap.isNull():
                pw, ph = pixmap.width(), pixmap.height()
                if pw > 0 and ph > 0:
                    ratio = min(img_size / pw, img_size / ph)
                    nw, nh = int(pw * ratio), int(ph * ratio)
                    x = rect.x() + (rect.width() - nw) // 2
                    y = rect.y() + 5
                    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
                    painter.drawPixmap(x, y, nw, nh, pixmap)
            
            font = QFont("맑은 고딕", 9)
            painter.setFont(font)
            text_rect = rect.adjusted(5, img_size + 10, -5, -5)
            flags = Qt.AlignmentFlag.AlignHCenter.value | Qt.TextFlag.TextWordWrap.value
            painter.drawText(text_rect, flags, file_name)
            
        elif self.view_mode == "tile":
            img_size = self.item_size - 10
            if not pixmap.isNull():
                pw, ph = pixmap.width(), pixmap.height()
                if pw > 0 and ph > 0:
                    ratio = min(img_size / pw, img_size / ph)
                    nw, nh = int(pw * ratio), int(ph * ratio)
                    x = rect.x() + 5
                    y = rect.y() + (rect.height() - nh) // 2
                    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
                    painter.drawPixmap(x, y, nw, nh, pixmap)
            
            font = QFont("맑은 고딕", 10, QFont.Weight.Bold)
            painter.setFont(font)
            text_rect = rect.adjusted(img_size + 15, 10, -5, -5)
            flags = Qt.AlignmentFlag.AlignLeft.value | Qt.AlignmentFlag.AlignTop.value | Qt.TextFlag.TextWordWrap.value
            painter.drawText(text_rect, flags, file_name)
            
        painter.restore()

    def sizeHint(self, option, index):
        row_data = index.model()._data[index.row()]
        if row_data.get("is_group"):
            width = self.parent().viewport().width() if hasattr(self.parent(), 'viewport') else 800
            return QSize(width - 20, 35)

        if self.view_mode == "thumbnail":
            return QSize(self.item_size, self.item_size + 30)
        elif self.view_mode == "tile":
            return QSize(self.item_size * 2, self.item_size)
        return super().sizeHint(option, index)

# ==========================================
# 컬럼 편집 다이얼로그
# ==========================================
class ColumnSelectDialog(QDialog):
    def __init__(self, parent, current_columns, all_columns):
        super().__init__(parent)
        self.setWindowTitle("Edit List Layout")
        self.setFixedSize(320, 500)
        self.setStyleSheet("background-color: #2b2b2b; color: white;")
        self.selected_columns = list(current_columns)
        self.all_columns = all_columns
        self.checkboxes = {}
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("표시할 컬럼을 선택하세요:"))
        
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet("background-color: #1e1e1e; border: 1px solid #444;")
        for col_id, col_name in self.all_columns.items():
            item = QListWidgetItem(self.list_widget)
            chk = QCheckBox(col_name)
            chk.setChecked(col_id in self.selected_columns)
            self.checkboxes[col_id] = chk
            self.list_widget.setItemWidget(item, chk)
            
        layout.addWidget(self.list_widget)
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def get_selected(self):
        return [col_id for col_id, chk in self.checkboxes.items() if chk.isChecked()]

# ==========================================
# 메인 테이블 모델
# ==========================================
class LibraryTableModel(QAbstractTableModel):
    def __init__(self, data=None):
        super().__init__()
        self._data = data or []
        self.ALL_COLUMNS = {
            "name": "파일명", "size": "용량", "res": "해상도", "mtime": "수정일", "ctime": "생성일", 
            "path": "파일경로", "ext": "확장자", "series": "시리즈", "title": "제목", 
            "vol": "권", "num": "화", "writer": "작가",
            "series_group": "시리즈 그룹", "creators": "제작진", "publisher": "출판사", "imprint": "임프린트",
            "genre": "장르", "volume_count": "전체권수", "page_count": "페이지수", "format": "포맷",
            "manga": "망가(방향)", "language": "언어", "rating": "평점", "age_rating": "연령등급", 
            "publish_date": "출간일", "summary": "줄거리", "characters": "등장인물", 
            "teams": "팀", "locations": "장소", "story_arc": "스토리 아크", 
            "tags": "태그", "notes": "메모", "web": "링크"
        }
        self.active_columns = ["name", "size", "mtime", "series", "title", "writer"]

    def set_columns(self, columns):
        self.beginResetModel()
        self.active_columns = [c for c in columns if c in self.ALL_COLUMNS]
        self.endResetModel()

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._data): return None
        row_data = self._data[index.row()]

        if row_data.get("is_group"):
            if role == Qt.ItemDataRole.DisplayRole and index.column() == 0:
                return f"📁 {row_data['name']} ({row_data['count']} 항목)"
            elif role == Qt.ItemDataRole.BackgroundRole:
                return QColor("#222222")
            elif role == Qt.ItemDataRole.ForegroundRole:
                return QColor("#3498DB")
            elif role == Qt.ItemDataRole.FontRole:
                font = QFont()
                font.setBold(True)
                return font
            return None

        if role == Qt.ItemDataRole.TextAlignmentRole:
            col_id = self.active_columns[index.column()]
            if col_id in ["res", "vol", "num", "size", "mtime", "ctime", "volume_count", "page_count", "rating", "age_rating", "publish_date"]:
                return Qt.AlignmentFlag.AlignCenter.value
            return Qt.AlignmentFlag.AlignLeft.value | Qt.AlignmentFlag.AlignVCenter.value

        if role == Qt.ItemDataRole.DisplayRole:
            col_id = self.active_columns[index.column()]
            if col_id in row_data and row_data[col_id] != "":
                val = row_data[col_id]
            else:
                val = row_data.get("full_meta", {}).get(col_id, "")
            return str(val) if val is not None else ""
            
        elif role == Qt.ItemDataRole.UserRole:
            return row_data.get("full_path", "")
        return None

    def flags(self, index):
        flags = super().flags(index)
        if not index.isValid(): return flags
        if self._data[index.row()].get("is_group"):
            flags &= ~Qt.ItemFlag.ItemIsSelectable 
        return flags

    def mimeTypes(self):
        return ["text/uri-list"]

    def mimeData(self, indexes):
        mime_data = QMimeData()
        urls = []
        processed_rows = set()
        for index in indexes:
            row = index.row()
            if row in processed_rows:
                continue
            processed_rows.add(row)
            
            if not self._data[row].get("is_group"):
                path = self._data[row].get("full_path")
                if path and os.path.exists(path):
                    urls.append(QUrl.fromLocalFile(path))
        
        mime_data.setUrls(urls)
        return mime_data

    def rowCount(self, parent=QModelIndex()):
        return len(self._data)

    def columnCount(self, parent=QModelIndex()):
        return len(self.active_columns)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            col_id = self.active_columns[section]
            return self.ALL_COLUMNS.get(col_id, "")
        return None

    def update_data(self, new_data):
        self.beginResetModel()
        self._data = new_data
        self.endResetModel()

# ==========================================
# 탭 폴더 메인 클래스
# ==========================================
class TabFolder(QWidget):
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.config = main_window.config
        
        QPixmapCache.setCacheLimit(102400)
        
        self.scan_thread = None
        self.extract_thread = None
        self.force_update_flag = False
        
        self.file_data_cache = []
        self.file_data_map = {} 
        
        self.current_sort_key = "name"
        self.current_sort_order = Qt.SortOrder.AscendingOrder
        self.current_group_key = "none"
        
        self.folder_watcher = QFileSystemWatcher(self)
        self.current_watched_folder = ""
        self.current_selected_path = ""

        self.sync_total_tasks = 0
        self.sync_completed_tasks = 0
        self.is_syncing = False

        self.scroll_timer = QTimer()
        self.scroll_timer.setSingleShot(True)
        self.scroll_timer.timeout.connect(self._do_background_load)
        
        self.grouping_timer = QTimer()
        self.grouping_timer.setSingleShot(True)
        self.grouping_timer.timeout.connect(self.apply_grouping_and_sorting)

        self.main_status_label = None
        self.main_optimize_btn = None

        self.thumb_dir = os.path.join(get_resource_path("data"), "thumbnails")
        if not os.path.exists(self.thumb_dir):
            os.makedirs(self.thumb_dir, exist_ok=True)

        self.setup_ui()
        self.setup_menus()
        self.setup_hotkeys()
        
        QTimer.singleShot(100, self.load_initial_layout)
        QTimer.singleShot(500, self.find_main_window_elements)

    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, 'main_optimize_btn') and self.main_optimize_btn:
            self.main_optimize_btn.hide()
        if hasattr(self, 'main_status_label') and self.main_status_label:
            self.main_status_label.setText("대기 중...")

    def hideEvent(self, event):
        super().hideEvent(event)
        if hasattr(self, 'main_optimize_btn') and self.main_optimize_btn:
            self.main_optimize_btn.show()

    def find_main_window_elements(self):
        for lbl in self.main_window.findChildren(QLabel):
            if lbl.text() == "대기 중..." or "대기 중" in lbl.text():
                self.main_status_label = lbl
                break
                
        for btn in self.main_window.findChildren(QPushButton):
            if "최적화 실행" in btn.text():
                self.main_optimize_btn = btn
                if self.isVisible(): 
                    self.main_optimize_btn.hide()
                break

    def get_active_view(self):
        return self.table_view if self.view_stack.currentIndex() == 0 else self.list_view

    def setup_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)

        splitter_style = """
            QSplitter::handle {
                background-color: #333333;
                border-radius: 2px;
                margin: 2px;
            }
            QSplitter::handle:horizontal {
                width: 4px;
                border-left: 1px dashed #666;
            }
            QSplitter::handle:vertical {
                height: 4px;
                border-top: 1px dashed #666;
            }
            QSplitter::handle:hover {
                background-color: #3498DB;
            }
        """
        self.main_splitter.setStyleSheet(splitter_style)
        self.main_splitter.setHandleWidth(8)

        toggle_btn_style = """
            QPushButton {
                background-color: #3a3a3a;
                color: #cccccc;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 5px 10px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
                color: white;
            }
            QPushButton:checked {
                background-color: #3498DB;
                color: white;
                border: 1px solid #2980B9;
                font-weight: bold;
            }
        """

        self.left_panel = QFrame()
        self.left_panel.setStyleSheet("QFrame { background-color: #2b2b2b; border-radius: 5px; border: 1px solid #444; }")
        left_layout = QVBoxLayout(self.left_panel)
        left_layout.setContentsMargins(5, 5, 5, 5)
        
        left_toolbar = QHBoxLayout()
        self.btn_subfolders = QPushButton("☐ Include Subfolders")
        self.btn_subfolders.setCheckable(True)
        self.btn_subfolders.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_subfolders.setStyleSheet(toggle_btn_style)
        
        self.btn_refresh_tree = QPushButton("Refresh (F5)")
        self.btn_refresh_tree.setCursor(Qt.CursorShape.PointingHandCursor)
        left_toolbar.addWidget(self.btn_subfolders)
        left_toolbar.addStretch()
        left_toolbar.addWidget(self.btn_refresh_tree)
        left_layout.addLayout(left_toolbar)

        self.combo_quick_access = QComboBox()
        self.combo_quick_access.setStyleSheet("""
            QComboBox { background-color: #3a3a3a; color: white; border: 1px solid #555; border-radius: 4px; padding: 4px; margin-bottom: 5px; }
            QComboBox::drop-down { border: none; }
        """)
        self.combo_quick_access.setCursor(Qt.CursorShape.PointingHandCursor)
        self.populate_quick_access()
        left_layout.addWidget(self.combo_quick_access)

        self.dir_model = QFileSystemModel()
        self.dir_model.setFilter(QDir.Filter.NoDotAndDotDot | QDir.Filter.AllDirs)
        self.dir_model.setRootPath("") 
        
        self.tree_view = QTreeView()
        self.tree_view.setModel(self.dir_model)
        self.tree_view.setRootIndex(self.dir_model.index(""))
        self.tree_view.setHeaderHidden(True)
        self.tree_view.setAnimated(True)
        self.tree_view.setIndentation(15)
        self.tree_view.setStyle(QStyleFactory.create("Fusion"))
        self.tree_view.setStyleSheet("""
            QTreeView { border: none; background-color: transparent; outline: none; } 
            QTreeView::item:hover { background-color: #3a3a3a; } 
            QTreeView::item:selected { background-color: #3a7ebf; color: white; }
        """)
        for i in range(1, 4): self.tree_view.hideColumn(i)
        left_layout.addWidget(self.tree_view)

        self.right_splitter = QSplitter(Qt.Orientation.Vertical)
        self.right_splitter.setStyleSheet(splitter_style)
        self.right_splitter.setHandleWidth(8)
        
        self.right_top_panel = QFrame()
        self.right_top_panel.setStyleSheet("QFrame { background-color: #2b2b2b; border-radius: 5px; border: 1px solid #444; }")
        right_top_layout = QVBoxLayout(self.right_top_panel)
        right_top_layout.setContentsMargins(5, 5, 5, 5)

        list_toolbar = QHBoxLayout()
        
        self.btn_sidebar = QPushButton("☑ Sidebar")
        self.btn_sidebar.setCheckable(True)
        self.btn_sidebar.setChecked(True)
        self.btn_sidebar.setStyleSheet(toggle_btn_style)
        
        menu_btn_style = """
            QToolButton { background-color: transparent; color: white; padding: 5px; font-weight: bold; border: none; }
            QToolButton:hover { color: #3498DB; }
            QToolButton::menu-indicator { image: none; }
        """
        
        self.btn_views = QToolButton()
        self.btn_views.setText("Views ▼")
        self.btn_views.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_views.setStyleSheet(menu_btn_style)
        
        self.btn_grouped = QToolButton()
        self.btn_grouped.setText("Grouped ▼")
        self.btn_grouped.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_grouped.setStyleSheet(menu_btn_style)

        self.btn_sorted = QToolButton()
        self.btn_sorted.setText("Sorted ▼")
        self.btn_sorted.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_sorted.setStyleSheet(menu_btn_style)

        self.btn_layouts = QToolButton()
        self.btn_layouts.setText("Manage List Layouts ▼")
        self.btn_layouts.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_layouts.setStyleSheet(menu_btn_style)
        
        self.btn_export = QPushButton("Export CSV")
        self.btn_export.setStyleSheet(toggle_btn_style)
        
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("검색 (제목, 작가, 파일명 등)...")
        self.search_bar.setClearButtonEnabled(True)
        self.search_bar.setFixedWidth(220)
        self.search_bar.setStyleSheet("""
            QLineEdit { background-color: #1e1e1e; color: white; border: 1px solid #555; border-radius: 12px; padding: 4px 10px; }
            QLineEdit:focus { border: 1px solid #3498DB; }
        """)
        
        self.btn_refresh_list = QPushButton("Refresh")
        
        self.btn_sidebar.setCursor(Qt.CursorShape.PointingHandCursor)
        list_toolbar.addWidget(self.btn_sidebar)
        
        for btn in [self.btn_views, self.btn_grouped, self.btn_sorted, self.btn_layouts, self.btn_export]:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            list_toolbar.addWidget(btn)
            
        list_toolbar.addStretch()
        list_toolbar.addWidget(self.search_bar)
        list_toolbar.addWidget(self.btn_refresh_list)
        right_top_layout.addLayout(list_toolbar)

        self.view_stack = QStackedWidget()
        self.table_model = LibraryTableModel()
        
        self.table_view = CustomTableView()
        self.table_view.setModel(self.table_model)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table_view.verticalHeader().hide()
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setSortingEnabled(False) 
        self.table_view.horizontalHeader().setSortIndicatorShown(True)
        self.table_view.horizontalHeader().setSectionsMovable(True)
        self.table_view.setStyleSheet("QTableView { border: none; background-color: transparent; }")
        self.table_view.setDragEnabled(False)
        self.table_view.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self.table_view.verticalHeader().setDefaultSectionSize(36)
        
        self.list_view = QListView()
        self.list_view.setModel(self.table_model)
        self.item_delegate = ThumbnailDelegate(self.list_view, self.thumb_dir)
        self.list_view.setItemDelegate(self.item_delegate)
        self.list_view.setViewMode(QListView.ViewMode.IconMode)
        self.list_view.setResizeMode(QListView.ResizeMode.Adjust)
        self.list_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_view.setSelectionRectVisible(True)
        self.list_view.setSpacing(10)
        self.list_view.setWordWrap(True)
        self.list_view.setStyleSheet("QListView { border: none; background-color: transparent; }")
        self.list_view.setDragEnabled(False)
        self.list_view.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)

        self.view_stack.addWidget(self.table_view)
        self.view_stack.addWidget(self.list_view)
        right_top_layout.addWidget(self.view_stack)

        self.right_bottom_panel = QFrame()
        self.right_bottom_panel.setStyleSheet("QFrame { background-color: #2b2b2b; border-radius: 5px; border: 1px solid #444; }")
        right_bottom_layout = QHBoxLayout(self.right_bottom_panel)
        right_bottom_layout.setContentsMargins(15, 15, 15, 15)
        
        self.lbl_cover = QLabel("Cover Image")
        self.lbl_cover.setFixedSize(220, 310) 
        self.lbl_cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_cover.setStyleSheet("border: 1px solid #555; background-color: #1a1a1a; border-radius: 4px;")
        right_bottom_layout.addWidget(self.lbl_cover)

        self.info_browser = QTextBrowser()
        self.info_browser.setOpenExternalLinks(True) 
        self.info_browser.setStyleSheet("QTextBrowser { background-color: transparent; border: none; color: white; }")
        right_bottom_layout.addWidget(self.info_browser, 1)

        self.right_splitter.addWidget(self.right_top_panel)
        self.right_splitter.addWidget(self.right_bottom_panel)
        self.right_splitter.setStretchFactor(0, 3)
        self.right_splitter.setStretchFactor(1, 1)
        
        self.right_bottom_panel.hide()

        self.main_splitter.addWidget(self.left_panel)
        self.main_splitter.addWidget(self.right_splitter)
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 4)
        self.main_layout.addWidget(self.main_splitter, 1)

        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(5, 0, 5, 0)
        
        self.lbl_tree_status = QLabel("Ready")
        self.lbl_tree_status.setStyleSheet("color: #aaaaaa; font-size: 12px;")
        bottom_bar.addWidget(self.lbl_tree_status)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(12)
        self.progress_bar.setFixedWidth(150)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar { border: 1px solid #444; border-radius: 6px; background-color: #2b2b2b; }
            QProgressBar::chunk { background-color: #3498DB; border-radius: 5px; }
        """)
        self.progress_bar.hide()
        bottom_bar.addWidget(self.progress_bar)
        
        bottom_bar.addStretch()
        
        self.slider_item_size = QSlider(Qt.Orientation.Horizontal)
        self.slider_item_size.setRange(80, 300)
        self.slider_item_size.setValue(120)
        self.slider_item_size.setFixedWidth(200)
        bottom_bar.addWidget(QLabel("Item Size:"))
        bottom_bar.addWidget(self.slider_item_size)
        
        self.main_layout.addLayout(bottom_bar)
        
        self.btn_sidebar.toggled.connect(self.toggle_sidebar)
        self.btn_sidebar.toggled.connect(lambda checked: self.btn_sidebar.setText("☑ Sidebar" if checked else "☐ Sidebar"))
        self.btn_refresh_tree.clicked.connect(self.refresh_tree)
        self.btn_refresh_list.clicked.connect(self.refresh_list)
        self.btn_subfolders.toggled.connect(self.refresh_list)
        self.btn_subfolders.toggled.connect(lambda checked: self.btn_subfolders.setText("☑ Include Subfolders" if checked else "☐ Include Subfolders"))
        
        self.slider_item_size.valueChanged.connect(self.on_size_changed)
        self.tree_view.selectionModel().selectionChanged.connect(self.on_tree_selection_changed)
        self.table_view.selectionModel().selectionChanged.connect(self.on_file_selection_changed)
        self.list_view.selectionModel().selectionChanged.connect(self.on_file_selection_changed)
        self.table_view.horizontalHeader().sectionMoved.connect(self.save_current_layout_state)
        self.table_view.horizontalHeader().sectionClicked.connect(self.on_header_clicked)
        self.combo_quick_access.currentIndexChanged.connect(self.on_quick_access_changed)
        self.folder_watcher.directoryChanged.connect(self.on_watched_folder_changed)
        self.search_bar.textChanged.connect(self.on_search_text_changed)
        self.table_view.doubleClicked.connect(self.open_viewer)
        self.list_view.doubleClicked.connect(self.open_viewer)
        self.main_splitter.splitterMoved.connect(self.save_splitter_states)
        self.right_splitter.splitterMoved.connect(self.save_splitter_states)
        self.btn_export.clicked.connect(self.export_csv)
        
        self.table_view.verticalScrollBar().valueChanged.connect(lambda: self.scroll_timer.start(100))
        self.list_view.verticalScrollBar().valueChanged.connect(lambda: self.scroll_timer.start(100))
        self.view_stack.currentChanged.connect(lambda: self.scroll_timer.start(50))

    def _requires_full_metadata(self):
        return self.current_group_key in ["series", "writer"] or self.current_sort_key in ["series", "writer", "title"]

    # [수정] 무한 로딩 방지 및 강제 갱신 시 전체 파일 백그라운드 처리 보장
    def _do_background_load(self):
        if self.extract_thread and self.extract_thread.isRunning():
            return

        view = self.get_active_view()
        rect = view.viewport().rect()
        target_exts = ('.zip', '.cbz', '.cbr', '.rar', '.7z')
        
        # [핵심 1] 단일 파일이 아닌, 사용자가 선택한 '모든' 파일 목록을 가져옵니다.
        selected_paths = set(self.get_selected_files())
        
        visible_tasks = []
        hidden_tasks = []
        
        for r in self.table_model._data:
            if r.get("is_group"): continue
            
            fp = r.get("full_path", "")
            if not fp.lower().endswith(target_exts): continue
            
            has_img = r.get("thumb_processed")
            has_meta = r.get("meta_processed")
            
            # 처리가 완전히 끝났으면 패스
            if has_img and has_meta: continue
            
            disp_idx = r.get("display_index", -1)
            if disp_idx >= 0:
                idx = self.table_model.index(disp_idx, 0)
                is_visible = view.visualRect(idx).intersects(rect) and view.visualRect(idx).isValid()
            else:
                is_visible = False
                
            # [핵심 2] 현재 파일이 '다중 선택된 파일' 그룹에 속해있는지 확인합니다.
            is_selected = fp in selected_paths
            
            needs_img = not has_img
            needs_meta = not has_meta
            
            thumb_path = os.path.join(self.thumb_dir, f"{r.get('hash', '')}.webp")
            task = (fp, needs_img, needs_meta, thumb_path)
            
            # 우선순위: 화면에 보이거나, 강제로 선택된 파일들을 최우선 큐에 배정
            if is_visible or is_selected:
                visible_tasks.append(task)
            else:
                # [핵심 3] 화면 밖의 파일도 버리지 않고 무조건 대기열에 넣어 완벽한 전체 동기화 보장
                hidden_tasks.append(task)
                
        if not visible_tasks and not hidden_tasks:
            self.is_syncing = False
            self.progress_bar.hide()
            if hasattr(self, 'main_status_label') and self.main_status_label:
                self.main_status_label.setText("대기 중...")
            return

        tasks = (visible_tasks + hidden_tasks)[:50] 
        real_heavy_tasks_count = sum(1 for t in tasks if t[2] or (t[1] and not os.path.exists(t[3])))
        
        # 총 작업량 카운팅
        if not self.is_syncing and real_heavy_tasks_count > 0:
            total_unprocessed = sum(1 for r in self.table_model._data if not r.get("is_group") and (not r.get("meta_processed") or not r.get("thumb_processed")) and r.get("full_path", "").lower().endswith(target_exts))
            self.sync_total_tasks = total_unprocessed
            self.sync_completed_tasks = 0
            self.is_syncing = True

        if self.extract_thread and self.extract_thread.isRunning():
            current_paths = [t[0] for t in getattr(self.extract_thread, 'current_tasks', [])]
            interrupt_needed = any(vt[0] not in current_paths for vt in visible_tasks)
            if interrupt_needed:
                self.extract_thread.cancel()
                try:
                    self.extract_thread.data_extracted.disconnect()
                    self.extract_thread.progress_updated.disconnect()
                    self.extract_thread.finished.disconnect()
                except TypeError: pass
                self.extract_thread = None
            else:
                return 

        seven_zip_path = get_resource_path('7za.exe')
        self.extract_thread = MemoryExtractThread(tasks, seven_zip_path)
        self.extract_thread.show_progress = (real_heavy_tasks_count > 0)
        self.extract_thread.data_extracted.connect(self.on_metadata_extracted)
        self.extract_thread.progress_updated.connect(self.on_extract_progress)
        self.extract_thread.finished.connect(lambda: self.scroll_timer.start(10))
        self.extract_thread.start()

    def on_extract_progress(self, count):
        if not self.is_syncing: return
        
        self.sync_completed_tasks += count
        if self.sync_completed_tasks > self.sync_total_tasks:
            self.sync_completed_tasks = self.sync_total_tasks

        self.progress_bar.show()
        self.progress_bar.setMaximum(self.sync_total_tasks)
        self.progress_bar.setValue(self.sync_completed_tasks)
        
        status_text = f"메타데이터 최적화 중... ({self.sync_completed_tasks}/{self.sync_total_tasks})"
        if hasattr(self, 'main_status_label') and self.main_status_label:
            self.main_status_label.setText(status_text)
            
        if self.sync_completed_tasks >= self.sync_total_tasks:
            self.progress_bar.hide()
            self.is_syncing = False
            if hasattr(self, 'main_status_label') and self.main_status_label:
                self.main_status_label.setText("대기 중...")

    # [핵심 추가] 우클릭 컨텍스트 메뉴에서 사용하는 "Update files (강제 추출)" 기능
    def force_update_selected_files(self):
        paths = self.get_selected_files()
        if not paths: return
        
        for fp in paths:
            row = self.file_data_map.get(fp)
            if row:
                # 1. 로컬 캐시 삭제
                file_hash = row.get("hash", "")
                if file_hash:
                    thumb_path = os.path.join(self.thumb_dir, f"{file_hash}.webp")
                    if os.path.exists(thumb_path):
                        try: os.remove(thumb_path)
                        except: pass
                    QPixmapCache.remove(file_hash)
                
                # 2. 메타데이터 마커 초기화 (강제 재추출을 위함)
                row["meta_processed"] = False
                row["thumb_processed"] = False
                row["res"] = ""
                row["full_meta"] = {}
                
        # 3. 화면 갱신 및 백그라운드 강제 로딩 시작
        self.apply_grouping_and_sorting()
        self.is_syncing = False # 진행률 바를 리셋하기 위해 강제 false 처리
        self._do_background_load()

    def export_csv(self):
        if not self.table_model._data:
            QMessageBox.information(self, "Export", "내보낼 데이터가 없습니다.")
            return
            
        filepath, _ = QFileDialog.getSaveFileName(self, "소장 목록 CSV 저장", "My_Library_Export.csv", "CSV Files (*.csv)")
        if not filepath:
            return
            
        try:
            header = self.table_view.horizontalHeader()
            visual_cols = []
            for i in range(header.count()):
                logical_idx = header.logicalIndex(i)
                visual_cols.append(self.table_model.active_columns[logical_idx])

            with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                headers = [self.table_model.ALL_COLUMNS[col] for col in visual_cols]
                writer.writerow(headers)
                
                for row in self.table_model._data:
                    if row.get("is_group"): continue
                    row_data = [str(row.get(col, "")) for col in visual_cols]
                    writer.writerow(row_data)
                    
            QMessageBox.information(self, "Export", "CSV 데이터 내보내기가 완료되었습니다.")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"오류가 발생했습니다:\n{e}")

    def save_splitter_states(self, pos=0, index=0):
        self.config["folder_main_splitter"] = self.main_splitter.saveState().toHex().data().decode()
        self.config["folder_right_splitter"] = self.right_splitter.saveState().toHex().data().decode()
        save_config(self.config)

    def on_search_text_changed(self, text):
        self.apply_grouping_and_sorting()

    def on_watched_folder_changed(self, path):
        if self.current_watched_folder == path:
            self.refresh_list(force_update=False)

    def populate_quick_access(self):
        self.combo_quick_access.blockSignals(True)
        self.combo_quick_access.clear()
        self.combo_quick_access.addItem("📁 빠른 이동 (Quick Access)...", "")
        paths = [
            ("바탕화면 (Desktop)", QStandardPaths.StandardLocation.DesktopLocation),
            ("문서 (Documents)", QStandardPaths.StandardLocation.DocumentsLocation),
            ("다운로드 (Downloads)", QStandardPaths.StandardLocation.DownloadLocation),
            ("홈 (Home)", QStandardPaths.StandardLocation.HomeLocation),
        ]
        for name, loc in paths:
            path = QStandardPaths.writableLocation(loc)
            if path: self.combo_quick_access.addItem(f"⭐ {name}", path)

        custom_favs = self.config.get("folder_favorites", [])
        if custom_favs:
            self.combo_quick_access.insertSeparator(self.combo_quick_access.count())
            for fav in custom_favs:
                fav_name = fav.get("name", os.path.basename(fav["path"]))
                if not fav_name: fav_name = fav["path"]
                self.combo_quick_access.addItem(f"📌 {fav_name}", fav["path"])

        self.combo_quick_access.blockSignals(False)

    def add_to_favorites(self, path):
        custom_favs = self.config.get("folder_favorites", [])
        if not any(f["path"] == path for f in custom_favs):
            name = os.path.basename(path)
            if not name: name = path
            custom_favs.append({"name": name, "path": path})
            self.config["folder_favorites"] = custom_favs
            save_config(self.config)
            self.populate_quick_access()

    def remove_from_favorites(self, path):
        custom_favs = self.config.get("folder_favorites", [])
        custom_favs = [f for f in custom_favs if f["path"] != path]
        self.config["folder_favorites"] = custom_favs
        save_config(self.config)
        self.populate_quick_access()

    def on_quick_access_changed(self, index):
        path = self.combo_quick_access.itemData(index)
        if path and os.path.exists(path):
            idx = self.dir_model.index(path)
            self.tree_view.setCurrentIndex(idx)
            self.tree_view.scrollTo(idx)
            self.tree_view.expand(idx)
            self.refresh_list()

    def setup_menus(self):
        self.menu_views = QMenu(self)
        self.menu_views.addAction("Detail", lambda: self.set_view_mode("detail"))
        self.menu_views.addAction("Thumbnail", lambda: self.set_view_mode("thumbnail"))
        self.menu_views.addAction("Tile", lambda: self.set_view_mode("tile"))
        self.btn_views.setMenu(self.menu_views)

        self.menu_grouped = QMenu(self)
        self.menu_grouped.addAction("None", lambda: self.set_grouping("none"))
        self.menu_grouped.addAction("폴더 (Folder)", lambda: self.set_grouping("path"))
        self.menu_grouped.addAction("확장자 (Extension)", lambda: self.set_grouping("ext"))
        self.menu_grouped.addAction("시리즈 (Series)", lambda: self.set_grouping("series"))
        self.menu_grouped.addAction("작가 (Writer)", lambda: self.set_grouping("writer"))
        self.btn_grouped.setMenu(self.menu_grouped)

        self.menu_sorted = QMenu(self)
        self.menu_sorted.addAction("파일명 (Name)", lambda: self.set_sorting("name"))
        self.menu_sorted.addAction("용량 (Size)", lambda: self.set_sorting("size"))
        self.menu_sorted.addAction("수정일 (Date Modified)", lambda: self.set_sorting("mtime"))
        self.menu_sorted.addAction("확장자 (Extension)", lambda: self.set_sorting("ext"))
        self.menu_sorted.addAction("시리즈 (Series)", lambda: self.set_sorting("series"))
        self.menu_sorted.addAction("제목 (Title)", lambda: self.set_sorting("title"))
        self.menu_sorted.addAction("작가 (Writer)", lambda: self.set_sorting("writer"))
        self.menu_sorted.addSeparator()
        self.menu_sorted.addAction("오름차순/내림차순 전환 (Toggle Order)", self.toggle_sort_order)
        self.btn_sorted.setMenu(self.menu_sorted)

        self.menu_layouts = QMenu(self)
        self.btn_layouts.setMenu(self.menu_layouts)
        self.update_layouts_menu()

        self.tree_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_view.customContextMenuRequested.connect(self.show_tree_context_menu)
        self.table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table_view.customContextMenuRequested.connect(self.show_list_context_menu)
        self.list_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_view.customContextMenuRequested.connect(self.show_list_context_menu)

    def setup_hotkeys(self):
        QShortcut(QKeySequence("F5"), self).activated.connect(self.refresh_tree)
        QShortcut(QKeySequence("Ctrl+A"), self).activated.connect(self.select_all_files)
        QShortcut(QKeySequence("F2"), self).activated.connect(self.hotkey_f2)
        QShortcut(QKeySequence("F3"), self).activated.connect(self.send_to_tab2)
        QShortcut(QKeySequence("Del"), self).activated.connect(self.delete_selected)

    def rename_folder(self, index=None):
        if not index:
            index = self.tree_view.currentIndex()
        if not index.isValid(): return
        
        old_path = self.dir_model.filePath(index)
        old_name = os.path.basename(old_path)
        
        new_name, ok = QInputDialog.getText(self, "폴더 이름 변경", "새 폴더 이름을 입력하세요:", text=old_name)
        if ok and new_name and new_name != old_name:
            new_path = os.path.join(os.path.dirname(old_path), new_name)
            try:
                os.rename(old_path, new_path)
                favs = self.config.get("folder_favorites", [])
                for fav in favs:
                    if fav["path"] == old_path:
                        fav["path"] = new_path
                        fav["name"] = new_name
                self.config["folder_favorites"] = favs
                save_config(self.config)
                self.populate_quick_access()
                
                if self.current_watched_folder == old_path:
                    self.folder_watcher.removePath(old_path)
                    self.folder_watcher.addPath(new_path)
                    self.current_watched_folder = new_path
            except Exception as e:
                QMessageBox.critical(self, "오류", f"폴더 이름을 변경할 수 없습니다:\n{e}")

    def delete_selected(self):
        if self.table_view.hasFocus() or self.list_view.hasFocus():
            files = self.get_selected_files()
            if not files: return
            
            reply = QMessageBox.question(self, "파일 삭제", f"선택한 {len(files)}개의 파일을 정말 삭제하시겠습니까?\n(휴지통으로 이동하지 않고 영구 삭제됩니다)", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                for f in files:
                    try: os.remove(f)
                    except Exception as e: print(f"Delete error: {e}")
                self.refresh_list(force_update=True)
                
        elif self.tree_view.hasFocus():
            index = self.tree_view.currentIndex()
            if not index.isValid(): return
            path = self.dir_model.filePath(index)
            
            reply = QMessageBox.question(self, "폴더 삭제", f"'{os.path.basename(path)}' 폴더와 내부의 모든 파일을 삭제하시겠습니까?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                try:
                    shutil.rmtree(path)
                    self.remove_from_favorites(path)
                except Exception as e:
                    QMessageBox.critical(self, "오류", f"폴더를 삭제할 수 없습니다:\n{e}")

    def load_initial_layout(self):
        view_mode = self.config.get("folder_view_mode", "detail")
        self.set_view_mode(view_mode)
        
        active_cols = self.config.get("folder_active_columns", ["name", "size", "mtime", "series", "title", "writer"])
        self.table_model.set_columns(active_cols)
        
        header_state_hex = self.config.get("folder_header_state", "")
        if header_state_hex:
            self.table_view.horizontalHeader().restoreState(QByteArray.fromHex(header_state_hex.encode()))
            
        main_spl = self.config.get("folder_main_splitter", "")
        if main_spl:
            self.main_splitter.restoreState(QByteArray.fromHex(main_spl.encode()))
            
        right_spl = self.config.get("folder_right_splitter", "")
        if right_spl:
            self.right_splitter.restoreState(QByteArray.fromHex(right_spl.encode()))
            
        last_path = self.config.get("folder_last_path", "")
        if last_path and os.path.exists(last_path):
            idx = self.dir_model.index(last_path)
            self.tree_view.setCurrentIndex(idx)
            self.tree_view.scrollTo(idx)
            self.tree_view.expand(idx)

    def save_current_layout_state(self):
        state = self.table_view.horizontalHeader().saveState().toHex().data().decode()
        self.config["folder_header_state"] = state
        self.config["folder_active_columns"] = self.table_model.active_columns
        save_config(self.config)

    def update_layouts_menu(self):
        self.menu_layouts.clear()
        self.menu_layouts.addAction("Edit List Layout", self.open_layout_editor)
        self.menu_layouts.addAction("Save List Layout", self.save_named_layout)
        self.menu_layouts.addAction("Edit Layouts (Delete)", self.delete_named_layout)
        self.menu_layouts.addSeparator()
        
        saved_layouts = self.config.get("saved_list_layouts", {})
        for name in saved_layouts.keys():
            action = self.menu_layouts.addAction(name)
            action.triggered.connect(lambda checked, n=name: self.apply_named_layout(n))

    def open_layout_editor(self):
        dlg = ColumnSelectDialog(self, self.table_model.active_columns, self.table_model.ALL_COLUMNS)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_cols = dlg.get_selected()
            if new_cols:
                self.table_model.set_columns(new_cols)
                self.save_current_layout_state()
                self.apply_grouping_and_sorting()

    def save_named_layout(self):
        name, ok = QInputDialog.getText(self, "Save Layout", "저장할 레이아웃 이름을 입력하세요:")
        if ok and name:
            state = self.table_view.horizontalHeader().saveState().toHex().data().decode()
            saved_layouts = self.config.get("saved_list_layouts", {})
            saved_layouts[name] = {"columns": self.table_model.active_columns, "state": state}
            self.config["saved_list_layouts"] = saved_layouts
            save_config(self.config)
            self.update_layouts_menu()

    def delete_named_layout(self):
        saved_layouts = self.config.get("saved_list_layouts", {})
        if not saved_layouts: return
        name, ok = QInputDialog.getItem(self, "Delete Layout", "삭제할 레이아웃 선택:", list(saved_layouts.keys()), 0, False)
        if ok and name:
            del saved_layouts[name]
            self.config["saved_list_layouts"] = saved_layouts
            save_config(self.config)
            self.update_layouts_menu()

    def apply_named_layout(self, name):
        layout = self.config.get("saved_list_layouts", {}).get(name)
        if layout:
            self.table_model.set_columns(layout["columns"])
            self.table_view.horizontalHeader().restoreState(QByteArray.fromHex(layout["state"].encode()))
            self.save_current_layout_state()
            self.apply_grouping_and_sorting()

    def set_view_mode(self, mode):
        self.config["folder_view_mode"] = mode
        save_config(self.config)
        
        if mode == "detail":
            self.view_stack.setCurrentIndex(0)
        else:
            self.view_stack.setCurrentIndex(1)
            self.item_delegate.view_mode = mode
            self.item_delegate.item_size = self.slider_item_size.value()
            self.list_view.setGridSize(QSize()) 
            self.table_model.layoutChanged.emit()
            self.list_view.doItemsLayout()

    def on_size_changed(self, value):
        self.item_delegate.item_size = value
        self.table_model.layoutChanged.emit()
        self.list_view.doItemsLayout()
        
        table_row_height = max(24, int(value * 0.3))
        self.table_view.verticalHeader().setDefaultSectionSize(table_row_height)

    def toggle_sidebar(self, checked):
        self.left_panel.setVisible(checked)

    def set_grouping(self, key):
        self.current_group_key = key
        self.apply_grouping_and_sorting()
        if self._requires_full_metadata():
            self.scroll_timer.start(100)

    def set_sorting(self, key):
        if self.current_sort_key == key:
            self.toggle_sort_order()
            return
            
        self.current_sort_key = key
        self.current_sort_order = Qt.SortOrder.AscendingOrder
        
        if key in self.table_model.active_columns:
            idx = self.table_model.active_columns.index(key)
            self.table_view.horizontalHeader().setSortIndicator(idx, self.current_sort_order)
        else:
            self.table_view.horizontalHeader().clearIndicator()
            
        self.apply_grouping_and_sorting()
        if self._requires_full_metadata():
            self.scroll_timer.start(100)

    def on_header_clicked(self, logicalIndex):
        key = self.table_model.active_columns[logicalIndex]
        if self.current_sort_key == key:
            self.current_sort_order = Qt.SortOrder.DescendingOrder if self.current_sort_order == Qt.SortOrder.AscendingOrder else Qt.SortOrder.AscendingOrder
        else:
            self.current_sort_key = key
            self.current_sort_order = Qt.SortOrder.AscendingOrder
        
        self.table_view.horizontalHeader().setSortIndicator(logicalIndex, self.current_sort_order)
        self.apply_grouping_and_sorting()
        if self._requires_full_metadata():
            self.scroll_timer.start(100)

    def toggle_sort_order(self):
        self.current_sort_order = Qt.SortOrder.DescendingOrder if self.current_sort_order == Qt.SortOrder.AscendingOrder else Qt.SortOrder.AscendingOrder
        if self.current_sort_key in self.table_model.active_columns:
            idx = self.table_model.active_columns.index(self.current_sort_key)
            self.table_view.horizontalHeader().setSortIndicator(idx, self.current_sort_order)
        self.apply_grouping_and_sorting()

    def apply_grouping_and_sorting(self):
        self.table_view.clearSpans()
        search_query = self.search_bar.text().strip().lower()
        
        data = []
        for row in self.file_data_cache:
            if search_query:
                search_target = f"{row.get('name','')} {row.get('title','')} {row.get('series','')} {row.get('writer','')}".lower()
                if search_query not in search_target: continue
            data.append(row)

        if not data:
            self.table_model.update_data([])
            return

        col_id = self.current_sort_key
        reverse = (self.current_sort_order == Qt.SortOrder.DescendingOrder)
        
        def safe_get(row, key):
            if key == "size": return row.get("raw_size", 0)
            if key == "mtime": return row.get("raw_mtime", 0)
            if key == "ctime": return row.get("raw_ctime", 0)
            
            if key in row and row[key] != "":
                val = row[key]
            else:
                val = row.get("full_meta", {}).get(key, "")
            
            if isinstance(val, str): return val.lower()
            return val if val is not None else ""

        if self.current_group_key != "none":
            data.sort(key=lambda x: safe_get(x, col_id), reverse=reverse)
            data.sort(key=lambda x: safe_get(x, self.current_group_key), reverse=False) 
        else:
            data.sort(key=lambda x: safe_get(x, col_id), reverse=reverse)
            
        display_data = []
        
        if self.current_group_key != "none":
            current_group = object()
            for row in data:
                g_val = safe_get(row, self.current_group_key)
                if not g_val: g_val = "분류 없음 (Unknown)"
                
                if g_val != current_group:
                    count = sum(1 for r in data if (safe_get(r, self.current_group_key) or "분류 없음 (Unknown)") == g_val)
                    display_data.append({"is_group": True, "name": g_val, "count": count})
                    current_group = g_val
                display_data.append(row)
        else:
            display_data = data
            
        self.file_data_map = {}
        for i, row in enumerate(display_data):
            row["display_index"] = i
            if not row.get("is_group"):
                self.file_data_map[row.get("full_path")] = row
                
        self.table_model.update_data(display_data)
        
        if self.current_group_key != "none":
            for i, row in enumerate(display_data):
                if row.get("is_group"):
                    self.table_view.setSpan(i, 0, 1, self.table_model.columnCount())

    def format_size(self, size):
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0: return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"

    def on_scan_progress(self, count):
        self.lbl_tree_status.setText(f"📁 폴더 스캔 중... ({count}개 항목 확인됨)")

    def on_scan_finished(self, file_data_cache, total_size):
        self.is_syncing = False
        self.sync_total_tasks = 0
        self.sync_completed_tasks = 0
        
        self.file_data_cache = file_data_cache
        for row in self.file_data_cache:
            row["size"] = self.format_size(row["raw_size"])
            fp = row["full_path"]
            mtime = row["raw_mtime"]
            
            try:
                cached = db.get_file_info(fp)
                if cached and len(cached) >= 32 and abs(float(cached[1]) - float(mtime)) < 2.0 and not self.force_update_flag:
                    row.update({
                        "res": cached[4], "title": cached[5], "series": cached[6],
                        "vol": cached[8], "num": cached[9], "writer": cached[10],
                        "meta_processed": True 
                    })
                    
                    row["full_meta"] = {
                        "resolution": cached[4], "title": cached[5], "series": cached[6], "series_group": cached[7],
                        "volume": cached[8], "number": cached[9], "writer": cached[10], "creators": cached[11], 
                        "publisher": cached[12], "imprint": cached[13], "genre": cached[14], "volume_count": cached[15], 
                        "page_count": cached[16], "format": cached[17], "manga": cached[18], "language": cached[19],
                        "rating": cached[20], "age_rating": cached[21], "publish_date": cached[22], 
                        "summary": cached[23], "characters": cached[24], "teams": cached[25], "locations": cached[26], 
                        "story_arc": cached[27], "tags": cached[28], "notes": cached[29], "web": cached[30]
                    }
            except Exception as e:
                print(f"DB Load Error: {e}")

        self.apply_grouping_and_sorting()
        
        folder_path = self.current_watched_folder
        if folder_path:
            self.lbl_tree_status.setText(f"선택: {os.path.basename(folder_path)} | 항목: {len(self.file_data_cache)}개 | 총 용량: {self.format_size(total_size)}")
            
        self.scroll_timer.start(100)

    def refresh_tree(self):
        idx = self.tree_view.currentIndex()
        self.dir_model.setRootPath(QDir.rootPath()) 
        self.dir_model.setRootPath("") 
        if idx.isValid(): self.tree_view.setCurrentIndex(idx)
        self.refresh_list()

    def refresh_list(self, force_update=False):
        self.right_bottom_panel.hide()
        index = self.tree_view.currentIndex()
        if not index.isValid(): return
        
        folder_path = self.dir_model.filePath(index)
        if not os.path.isdir(folder_path): return
        
        self.force_update_flag = force_update
        
        if self.current_watched_folder != folder_path:
            if self.current_watched_folder:
                self.folder_watcher.removePath(self.current_watched_folder)
            self.folder_watcher.addPath(folder_path)
            self.current_watched_folder = folder_path
            self.config["folder_last_path"] = folder_path
            save_config(self.config)
        
        include_sub = self.btn_subfolders.isChecked()
        target_exts = ('.zip', '.cbz', '.cbr', '.rar', '.7z')
        
        if self.scan_thread and self.scan_thread.isRunning():
            self.scan_thread.cancel()
            self.scan_thread.wait()
            self.scan_thread = None
            
        if self.extract_thread and self.extract_thread.isRunning():
            self.extract_thread.cancel()
            try:
                self.extract_thread.data_extracted.disconnect()
                self.extract_thread.progress_updated.disconnect()
            except TypeError: pass
            self.extract_thread = None
            
        self.file_data_cache.clear()
        self.file_data_map.clear()
        self.table_model.update_data([])
        self.lbl_tree_status.setText("📁 폴더 스캔 준비 중...")
        self.is_syncing = False
        if hasattr(self, 'main_status_label') and self.main_status_label:
            self.main_status_label.setText("대기 중...")
        self.progress_bar.hide()
        
        self.scan_thread = FolderScanThread(folder_path, include_sub, target_exts, self.thumb_dir)
        self.scan_thread.progress_updated.connect(self.on_scan_progress)
        self.scan_thread.scan_finished.connect(self.on_scan_finished)
        self.scan_thread.start()

    # [핵심 수정] 해상도가 뒤늦게 확보되어도 DB에 완벽히 덮어쓰도록 조건 해제
    def on_metadata_extracted(self, filepath, meta_dict, has_img_out):
        row = self.file_data_map.get(filepath)
        if not row: return

        if has_img_out:
            row["thumb_processed"] = True

        was_meta_already_processed = row.get("meta_processed", False)
        if meta_dict is None: meta_dict = {}

        # 1. 방금 이미지를 추출해서 해상도를 알아냈다면 덮어씌움
        new_res = meta_dict.get("resolution", "")
        if new_res:
            row["res"] = new_res
            row["full_meta"]["resolution"] = new_res

        # 2. 메타데이터가 아예 없었던 경우 업데이트
        if not was_meta_already_processed:
            row["meta_processed"] = True 
            row.update({
                "res": meta_dict.get("resolution", row.get("res", "")),
                "title": meta_dict.get("title", ""),
                "series": meta_dict.get("series", ""),
                "vol": meta_dict.get("volume", ""),
                "num": meta_dict.get("number", ""),
                "writer": meta_dict.get("writer", "")
            })
            for k, v in meta_dict.items():
                row["full_meta"][k] = v
                
        # 3. 새로 알아낸 메타데이터가 있거나, 해상도를 뒤늦게 알아낸 경우 무조건 DB에 덮어씀
        if not was_meta_already_processed or new_res:
            try:
                md = row["full_meta"]
                creators_list = []
                writer = md.get("writer")
                if writer: creators_list.append(writer)
                for role in ['penciller', 'inker', 'colorist', 'letterer', 'cover_artist', 'editor']:
                    val = md.get(role)
                    if val: creators_list.append(val)
                creators_str = " / ".join(creators_list) if creators_list else ""
                
                y, m, d = md.get("year", ""), md.get("month", ""), md.get("day", "")
                publish_date_str = f"{y}-{m}-{d}".strip('-')
                if publish_date_str == "--": publish_date_str = ""
                
                db.upsert_file_info(
                    filepath, row.get("raw_mtime", 0), row.get("raw_size", 0), row.get("ext", ""),
                    md.get("resolution", ""), md.get("title", ""), md.get("series", ""),
                    md.get("series_group", ""), md.get("volume", ""), md.get("number", ""),
                    md.get("writer", ""), creators_str, md.get("publisher", ""), md.get("imprint", ""), 
                    md.get("genre", ""), md.get("volume_count", ""), md.get("page_count", ""), 
                    md.get("format", ""), md.get("manga", ""), md.get("language", ""),
                    md.get("rating", ""), md.get("age_rating", ""), publish_date_str, md.get("summary", ""), 
                    md.get("characters", ""), md.get("teams", ""), md.get("locations", ""), 
                    md.get("story_arc", ""), md.get("tags", ""), md.get("notes", ""), md.get("web", ""), ""
                )
            except Exception as e: print(f"DB Upsert Error: {e}")

        disp_idx = row.get("display_index")
        if disp_idx is not None:
            idx1 = self.table_model.index(disp_idx, 0)
            idx2 = self.table_model.index(disp_idx, self.table_model.columnCount()-1)
            self.table_model.dataChanged.emit(idx1, idx2)

        if self.current_selected_path == filepath:
            self.update_info_panel(filepath, row.get("full_meta", {}))

    def on_tree_selection_changed(self):
        self.refresh_list()

    def get_selected_files(self):
        view = self.get_active_view()
        paths = []
        for idx in view.selectionModel().selectedIndexes():
            if idx.column() == 0:
                path = self.table_model.data(idx, Qt.ItemDataRole.UserRole)
                if path: paths.append(path)
        return paths

    def on_file_selection_changed(self):
        view = self.get_active_view()
        indexes = [idx for idx in view.selectionModel().selectedIndexes() if idx.column() == 0]
        
        if not indexes:
            self.lbl_cover.clear()
            self.info_browser.setHtml("")
            index = self.tree_view.currentIndex()
            if index.isValid():
                folder_path = self.dir_model.filePath(index)
                self.lbl_tree_status.setText(f"선택: {os.path.basename(folder_path)} | 항목: {len(self.file_data_cache)}개")
            self.right_bottom_panel.hide()
            self.current_selected_path = ""
            return

        last_index = indexes[-1]
        full_path = self.table_model.data(last_index, Qt.ItemDataRole.UserRole)
        
        if not full_path:
            self.right_bottom_panel.hide()
            return

        self.current_selected_path = full_path
        self.right_bottom_panel.show()
        
        sizes = self.right_splitter.sizes()
        if len(sizes) >= 2 and sizes[1] == 0:
            total = sum(sizes)
            if total > 0:
                self.right_splitter.setSizes([int(total * 0.7), int(total * 0.3)])
            else:
                self.right_splitter.setSizes([700, 300])
        
        try:
            stat = os.stat(full_path)
            size_str = self.format_size(stat.st_size)
            self.lbl_tree_status.setText(f"경로: {full_path} | 용량: {size_str}")
        except: pass
        
        row = self.file_data_map.get(full_path)
        if row:
            if row.get("full_meta"):
                self.update_info_panel(full_path, row["full_meta"])
                
                if not row.get("thumb_processed"):
                    file_hash = row.get("hash", "")
                    thumb_path = os.path.join(self.thumb_dir, f"{file_hash}.webp")
                    seven_zip_path = get_resource_path('7za.exe')
                    
                    if self.extract_thread and self.extract_thread.isRunning():
                        self.extract_thread.cancel()
                        try:
                            self.extract_thread.data_extracted.disconnect()
                            self.extract_thread.progress_updated.disconnect()
                        except TypeError: pass
                        
                    self.extract_thread = MemoryExtractThread([(full_path, True, False, thumb_path)], seven_zip_path)
                    self.extract_thread.data_extracted.connect(self.on_metadata_extracted)
                    self.extract_thread.start()
                    
                return
        
        self.update_info_panel(full_path, {})

    def update_info_panel(self, full_path, meta_dict):
        row = self.file_data_map.get(full_path)
        if row:
            file_hash = row.get("hash", "")
            thumb_path = os.path.join(self.thumb_dir, f"{file_hash}.webp")
            
            cached_pix = QPixmapCache.find(file_hash) if file_hash else None
            
            if cached_pix is not None and not cached_pix.isNull():
                self.lbl_cover.setPixmap(cached_pix.scaled(220, 310, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            elif os.path.exists(thumb_path):
                if os.path.getsize(thumb_path) > 0:
                    pixmap = QPixmap(thumb_path)
                    if not pixmap.isNull():
                        QPixmapCache.insert(file_hash, pixmap)
                        self.lbl_cover.setPixmap(pixmap.scaled(220, 310, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                    else:
                        self.lbl_cover.setText("No Cover Image")
                else:
                    self.lbl_cover.setText("No Cover Image")
            else:
                self.lbl_cover.setText("No Cover Image")
        else:
            self.lbl_cover.setText("No Cover Image")

        title = meta_dict.get("title") or os.path.basename(full_path)
        series = meta_dict.get("series") or "시리즈 정보 없음"
        series_group = meta_dict.get("series_group") or ""
        series_info = f"{series} / {series_group}" if series_group else series
        
        creators_list = []
        writer = meta_dict.get("writer")
        if writer: creators_list.append(writer)
        for role in ['penciller', 'inker', 'colorist', 'letterer', 'cover_artist', 'editor']:
            val = meta_dict.get(role)
            if val: creators_list.append(val)
        creators = " / ".join(creators_list) if creators_list else "-"
        if meta_dict.get("creators"): creators = meta_dict.get("creators")
        
        publisher = meta_dict.get("publisher") or "-"
        imprint = meta_dict.get("imprint") or ""
        pub_full = f"{publisher} / {imprint}" if imprint else publisher

        genre = meta_dict.get("genre") or "-"
        volume_count = meta_dict.get("volume_count") or meta_dict.get("volume") or "-"
        page_count = meta_dict.get("page_count") or "-"
        format_val = meta_dict.get("format") or "-"
        manga = meta_dict.get("manga") or "-"
        rating = meta_dict.get("rating") or "-"
        age_rating = meta_dict.get("age_rating") or "-"
        
        publish_date = meta_dict.get("publish_date")
        if not publish_date:
            y, m, d = meta_dict.get("year", ""), meta_dict.get("month", ""), meta_dict.get("day", "")
            publish_date = f"{y}-{m}-{d}".strip('-') or "-"

        summary = meta_dict.get("summary") or "줄거리 정보가 없습니다."
        characters = meta_dict.get("characters") or "-"
        teams = meta_dict.get("teams") or "-"
        locations = meta_dict.get("locations") or "-"
        story_arc = meta_dict.get("story_arc") or "-"
        tags = meta_dict.get("tags") or "-"
        notes = meta_dict.get("notes") or "-"
        
        link = meta_dict.get("web") or "-"
        link_html = f'<a href="{link}" style="color: #3498DB; text-decoration: none;">{link}</a>' if link != "-" else "-"

        info_html = f"""
        <div style="font-family: '맑은 고딕', sans-serif;">
            <h2 style="margin: 0px 0px 5px 0px; color: #ffffff; font-size: 18pt;">{title}</h2>
            <h4 style="margin: 0px 0px 20px 0px; color: #cccccc; font-size: 12pt; font-weight: normal;">{series_info}</h4>
            
            <table width="100%" cellpadding="0" cellspacing="0" border="0" style="font-size: 10pt;">
                <tr>
                    <td width="45%" valign="top" style="padding-right: 20px;">
                        <table width="100%" cellpadding="4" cellspacing="0" border="0">
                            <tr><td width="80" valign="top" style="color: #aaaaaa;">제작진</td><td valign="top" style="color: #ffffff;">{creators}</td></tr>
                            <tr><td valign="top" style="color: #aaaaaa;">출판사</td><td valign="top" style="color: #ffffff;">{pub_full}</td></tr>
                            <tr><td valign="top" style="color: #aaaaaa;">장르</td><td valign="top" style="color: #ffffff;">{genre}</td></tr>
                            <tr><td valign="top" style="color: #aaaaaa;">페이지수</td><td valign="top" style="color: #ffffff;">{page_count}</td></tr>
                            <tr><td valign="top" style="color: #aaaaaa;">전체권수</td><td valign="top" style="color: #ffffff;">{volume_count}</td></tr>
                            <tr><td valign="top" style="color: #aaaaaa;">포맷/망가</td><td valign="top" style="color: #ffffff;">{format_val} / {manga}</td></tr>
                            <tr><td valign="top" style="color: #aaaaaa;">평점</td><td valign="top" style="color: #ffffff;">{rating}</td></tr>
                            <tr><td valign="top" style="color: #aaaaaa;">연령등급</td><td valign="top" style="color: #ffffff;">{age_rating}</td></tr>
                            <tr><td valign="top" style="color: #aaaaaa;">출간일</td><td valign="top" style="color: #ffffff;">{publish_date}</td></tr>
                        </table>
                    </td>
                    <td width="55%" valign="top">
                        <div style="color: #aaaaaa; margin-bottom: 4px;">줄거리</div>
                        <div style="margin-bottom: 15px; color: #dddddd; line-height: 1.5;">{summary}</div>
                        
                        <div style="color: #aaaaaa; margin-bottom: 4px;">스토리 아크 / 팀 / 장소</div>
                        <div style="margin-bottom: 15px; color: #dddddd;">{story_arc} / {teams} / {locations}</div>
                        
                        <div style="color: #aaaaaa; margin-bottom: 4px;">등장인물</div>
                        <div style="margin-bottom: 15px; color: #dddddd;">{characters}</div>
                        
                        <div style="color: #aaaaaa; margin-bottom: 4px;">태그</div>
                        <div style="margin-bottom: 15px; color: #dddddd;">{tags}</div>
                        
                        <div style="color: #aaaaaa; margin-bottom: 4px;">링크</div>
                        <div style="margin-bottom: 15px;">{link_html}</div>
                    </td>
                </tr>
            </table>
        </div>
        """
        self.info_browser.setHtml(info_html)

    def show_tree_context_menu(self, position):
        index = self.tree_view.indexAt(position)
        if not index.isValid(): return
        path = self.dir_model.filePath(index)
        menu = QMenu()
        
        custom_favs = self.config.get("folder_favorites", [])
        is_fav = any(f["path"] == path for f in custom_favs)
        
        if is_fav:
            menu.addAction("Favorites Remove", lambda: self.remove_from_favorites(path))
        else:
            menu.addAction("Favorites Add", lambda: self.add_to_favorites(path))
            
        menu.addSeparator()
        menu.addAction("Open in Explorer", lambda: self.open_in_explorer(path))
        menu.addAction("Rename Folder", lambda: self.rename_folder(index))
        menu.addAction("Delete Folder (Del)", self.delete_selected)
        menu.addAction("Refresh", self.refresh_tree)
        menu.exec(self.tree_view.viewport().mapToGlobal(position))

    def show_list_context_menu(self, position):
        view = self.get_active_view()
        if not view.selectionModel().hasSelection(): return
        
        if not self.get_selected_files(): return
        
        menu = QMenu()
        menu.addAction("View", self.open_viewer)
        menu.addAction("Metadata edit (F2)", self.send_to_tab3)
        menu.addAction("Inner Renamer (F3)", self.send_to_tab2)
        # [핵심 추가] Update files 기능 재정의
        menu.addAction("Update files", self.force_update_selected_files)
        menu.addSeparator()
        menu.addAction("Delete Files (Del)", self.delete_selected)
        menu.addAction("Open in Explorer", self.open_selected_in_explorer)
        menu.addSeparator()
        menu.addAction("Select All (Ctrl+A)", self.select_all_files)
        menu.addAction("Invert Selection", self.invert_selection)
        menu.addAction("Refresh", self.refresh_list)
        menu.exec(view.viewport().mapToGlobal(position))

    def force_update_selected_files(self):
        paths = self.get_selected_files()
        if not paths: return
        
        for fp in paths:
            row = self.file_data_map.get(fp)
            if row:
                row["meta_processed"] = False
                row["thumb_processed"] = False
                row["res"] = ""
                row["full_meta"] = {}
                
                file_hash = row.get("hash", "")
                if file_hash:
                    thumb_path = os.path.join(self.thumb_dir, f"{file_hash}.webp")
                    if os.path.exists(thumb_path):
                        try: os.remove(thumb_path)
                        except: pass
                    QPixmapCache.remove(file_hash)
                    
        self.apply_grouping_and_sorting()
        self.is_syncing = False 
        self._do_background_load() 

    def select_all_files(self):
        self.get_active_view().selectAll()

    def invert_selection(self):
        view = self.get_active_view()
        model = view.model()
        selection_model = view.selectionModel()
        selection = QItemSelection(model.index(0, 0), model.index(model.rowCount() - 1, model.columnCount() - 1))
        selection_model.select(selection, QItemSelectionModel.SelectionFlag.Toggle)

    def hotkey_f2(self):
        if self.tree_view.hasFocus():
            self.rename_folder()
        else:
            self.send_to_tab3()

    def open_viewer(self):
        viewer_path = self.config.get("viewer_path", "")
        if not viewer_path or not os.path.exists(viewer_path):
            QMessageBox.warning(self, "Warning", "환경 설정에서 뷰어 프로그램을 지정해주세요.")
            return
        files = self.get_selected_files()
        if files: subprocess.Popen([viewer_path, files[0]])

    def open_in_explorer(self, path):
        if os.name == 'nt': os.startfile(path)
        else: subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', path])

    def open_selected_in_explorer(self):
        files = self.get_selected_files()
        if files: self.open_in_explorer(os.path.dirname(files[0]))

    def send_to_tab2(self):
        files = self.get_selected_files()
        if files and hasattr(self.main_window, 'tab2'):
            self.main_window.tabs.setCurrentWidget(self.main_window.tab2)
            if hasattr(self.main_window.tab2, 'process_paths'): self.main_window.tab2.process_paths(files)

    def send_to_tab3(self):
        files = self.get_selected_files()
        if files and hasattr(self.main_window, 'tab3'):
            self.main_window.tabs.setCurrentWidget(self.main_window.tab3)
            if hasattr(self.main_window.tab3, 'process_paths'): self.main_window.tab3.process_paths(files)
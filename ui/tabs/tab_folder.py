import os
import sys
import subprocess
import traceback
import shutil
import csv
import zipfile
import xml.etree.ElementTree as ET
import hashlib
import difflib
import re
import time
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QTreeView, 
    QTableView, QListView, QLabel, QPushButton, QSlider, QFrame, QMenu, QMessageBox,
    QHeaderView, QAbstractItemView, QSizePolicy, QDialog, QListWidget, QListWidgetItem, 
    QCheckBox, QDialogButtonBox, QStyledItemDelegate, QStackedWidget, QInputDialog, QToolButton, QStyleFactory,
    QComboBox, QStyle, QLineEdit, QFileDialog, QRubberBand, QTextBrowser, QProgressBar
)
from PyQt6.QtGui import QFileSystemModel, QAction, QPixmap, QPainter, QColor, QFont, QKeySequence, QShortcut, QImage, QPixmapCache
from PyQt6.QtCore import Qt, QDir, QAbstractTableModel, QModelIndex, QSize, QByteArray, QItemSelectionModel, QItemSelection, QStandardPaths, QFileSystemWatcher, QTimer, QMimeData, QUrl, QThread, pyqtSignal, QRect, QPoint, QCoreApplication

from config import get_resource_path, save_config
from core.library_db import db

# ==========================================
# [핵심 수정] i18n.py 구조에 맞춘 완벽한 다국어 처리 로직
# ==========================================
from core.i18n import get_i18n

_TRANSLATIONS = get_i18n()
_CURRENT_LANG = "ko"

def set_language(lang_code):
    global _CURRENT_LANG
    if lang_code in _TRANSLATIONS:
        _CURRENT_LANG = lang_code

def _(key):
    # 현재 언어의 딕셔너리에서 키를 찾고, 없으면 한국어에서 찾고, 그래도 없으면 키값 자체를 반환
    return _TRANSLATIONS.get(_CURRENT_LANG, _TRANSLATIONS["ko"]).get(key, key)


# ==========================================
# [추가됨] 중복 검사용 B폴더 스캔 스레드
# ==========================================
class DupScanThread(QThread):
    scan_finished = pyqtSignal(list)
    progress_updated = pyqtSignal(int, int) # 매칭된 압축파일 수, 전체 스캔한 파일 수

    def __init__(self, dup_folders, target_exts):
        super().__init__()
        self.dup_folders = dup_folders
        self.target_exts = tuple(target_exts)
        self.is_cancelled = False

    def cancel(self):
        self.is_cancelled = True

    def run(self):
        from core.library_db import db
        b_cache = []
        match_count = 0
        total_scanned = 0

        for folder in self.dup_folders:
            if self.is_cancelled: return
            if not os.path.exists(folder): continue
            
            # 1. DB에서 즉시 조회 시도 (초고속 캐시 히트)
            like_path = folder + '%'
            try:
                # 파일 경로(0)와 크기(2) 정보만 빠르게 가져옴
                cursor = db.conn.execute("SELECT * FROM files WHERE filepath LIKE ?", (like_path,))
                rows = cursor.fetchall()
            except Exception as e:
                rows = []

            if rows:
                # DB에 정보가 있다면 물리적 디스크 스캔을 완전히 스킵합니다.
                for row in rows:
                    if self.is_cancelled: return
                    fp = row[0]
                    size = row[2]
                    
                    name = os.path.basename(fp)
                    if name.lower().endswith(self.target_exts):
                        b_cache.append({
                            "name": name,
                            "path": os.path.dirname(fp),
                            "full_path": fp,
                            "size": size,
                            "name_no_ext": os.path.splitext(name)[0].lower()
                        })
                        match_count += 1
                        total_scanned += 1
                        
                # UI 업데이트 (프리징 방지)
                self.progress_updated.emit(match_count, total_scanned)

            else:
                # 2. DB에 없는 폴더인 경우 os.scandir로 물리 스캔 (기존 os.walk 대비 3~5배 빠름)
                def fast_scan(scan_path):
                    nonlocal match_count, total_scanned
                    if self.is_cancelled: return
                    try:
                        with os.scandir(scan_path) as it:
                            for entry in it:
                                if self.is_cancelled: return
                                
                                if entry.is_dir(follow_symlinks=False):
                                    fast_scan(entry.path)
                                elif entry.is_file(follow_symlinks=False):
                                    total_scanned += 1
                                    name = entry.name
                                    
                                    if name.lower().endswith(self.target_exts):
                                        b_cache.append({
                                            "name": name,
                                            "path": scan_path,
                                            "full_path": entry.path,
                                            "size": entry.stat().st_size,
                                            "name_no_ext": os.path.splitext(name)[0].lower()
                                        })
                                        match_count += 1
                                    
                                    if total_scanned % 500 == 0:
                                        self.progress_updated.emit(match_count, total_scanned)
                    except Exception: pass

                fast_scan(folder)
                        
        self.progress_updated.emit(match_count, total_scanned)
        self.scan_finished.emit(b_cache)

class DupMatchThread(QThread):
    match_finished = pyqtSignal(dict)
    match_progress = pyqtSignal(int, int)

    def __init__(self, a_files, b_cache):
        super().__init__()
        self.a_files = a_files
        self.b_cache = b_cache
        self.is_cancelled = False

    def cancel(self):
        self.is_cancelled = True

    def extract_series_and_nums(self, name):
        from core.parser import extract_core_title
        
        core_title = extract_core_title(name).lower()
        
        bundle_pattern = r'(?:v|vol|c|ch|chapter|제)?\.?\s*(\d+(?:\.\d+)?)\s*[~-]\s*(\d+(?:\.\d+)?)\s*(?:권|화|장|편|부)?'
        bundle_match = re.search(bundle_pattern, name, re.IGNORECASE)
        if bundle_match:
            return core_title, [float(bundle_match.group(1)), float(bundle_match.group(2))], True

        if re.search(r'완결|합본|전권|시리즈|\(완\)', name):
            return core_title, [], True
            
        ko_single = re.search(r'(\d+(?:\.\d+)?)\s*(?:권|화|장|편|부)', name, re.IGNORECASE)
        if ko_single:
            return core_title, [float(ko_single.group(1))], False

        en_single = re.search(r'(?:v|vol|c|ch|chapter|제)\.?\s*(\d+(?:\.\d+)?)', name, re.IGNORECASE)
        if en_single:
            return core_title, [float(en_single.group(1))], False
            
        clean_name = re.sub(r'\[.*?\]|\(.*?\)', '', name)
        nums = re.findall(r'\d+(?:\.\d+)?', clean_name)
        if nums:
            return core_title, [float(nums[-1])], False
            
        return core_title, [], False

    # 동의어 사전: 번역어/표기 변형 정규화
    SYNONYMS = {
        '블랙': '검은', 'black': '검은',
        '화이트': '흰', 'white': '흰',
        '레드': '빨간', 'red': '빨간',
        '블루': '파란', 'blue': '파란',
        '그린': '녹색', 'green': '녹색',
        'love': '사랑',
        'hell': '지옥',
        'hero': '영웅', 'heroes': '영웅',
        'king': '왕',
        'god': '신',
        'dark': '어둠', '다크': '어둠',
        'new': '새로운',
        'super': '슈퍼',
        'dragon': '드래곤',
        'hunter': '헌터',
        'master': '마스터',
        'legend': '전설',
        'world': '세계',
        'sword': '검',
    }

    def jamo_decompose(self, text):
        result = []
        for ch in text:
            code = ord(ch)
            if 0xAC00 <= code <= 0xD7A3:
                code -= 0xAC00
                result.append(chr(0x1100 + code // 588))
                result.append(chr(0x1161 + (code % 588) // 28))
                jong = code % 28
                if jong: result.append(chr(0x11A7 + jong))
            else:
                result.append(ch)
        return ''.join(result)

    def check_similarity(self, a_core, b_core):
        STOPWORDS = {
            '만화책', '만화', '코믹스', 'e북', 'ebook', '완결', '합본',
            '웹툰', '단행본', '시리즈', '총집편', '풀컬러',
            'in', 'the', 'of', 'a', 'an',
            '미완',
        }

        def normalize(text):
            text = text.lower()
            for k, v in DupMatchThread.SYNONYMS.items():
                text = re.sub(r'\b' + re.escape(k) + r'\b', v, text)
            return text

        def tokenize(text):
            text = normalize(text)
            ko = re.findall(r'[가-힣]{2,}', text)
            en = re.findall(r'[a-z]{3,}', text)
            return [t for t in ko + en if t not in STOPWORDS]

        def char_sim(a, b):
            ac = re.sub(r'[^가-힣a-z0-9]', '', normalize(a))
            bc = re.sub(r'[^가-힣a-z0-9]', '', normalize(b))
            if not ac or not bc: return 0.0
            return difflib.SequenceMatcher(None, ac, bc).ratio()

        def token_sim(ta, tb):
            if ta == tb: return 1.0
            ka = bool(re.search(r'[가-힣]', ta))
            kb = bool(re.search(r'[가-힣]', tb))
            if ka and kb:
                s = difflib.SequenceMatcher(None, self.jamo_decompose(ta), self.jamo_decompose(tb)).ratio()
                # 2글자 한글 토큰은 오탐 방지를 위해 엄격하게
                if min(len(ta), len(tb)) <= 2:
                    return s if s >= 0.90 else 0.0
                return s
            if not ka and not kb:
                return difflib.SequenceMatcher(None, ta, tb).ratio()
            return 0.0

        tok_a = tokenize(a_core)
        tok_b = tokenize(b_core)

        # 토큰화 실패 시 문자 수준 유사도로 fallback
        if not tok_a or not tok_b:
            s = char_sim(a_core, b_core)
            return s >= 0.75, round(s * 100, 1)

        # 각 토큰의 상대방 내 최고 유사도
        a_scores = [max(token_sim(ta, tb) for tb in tok_b) for ta in tok_a]
        b_scores = [max(token_sim(tb, ta) for ta in tok_a) for tb in tok_b]

        # 부분집합 방향 모두 허용 (A⊂B, B⊂A)
        best = max(sum(a_scores) / len(a_scores), sum(b_scores) / len(b_scores))

        # 고유사도 토큰 존재 시 보너스
        exact_count = sum(1 for ta in tok_a for tb in tok_b if token_sim(ta, tb) >= 0.85)
        if exact_count > 0:
            best = min(1.0, best + 0.15)

        # 문자 수준 유사도 보조 (토큰 분리 케이스 구제: 슬램덩크/슬램 덩크 등)
        cs = char_sim(a_core, b_core)
        if cs >= 0.80 and best < 0.70:
            best = max(best, cs * 0.85)

        return best >= 0.70, round(best * 100, 1)

    def run(self):
        import time # 스레드 내부에서 사용할 time 모듈
        
        matches = {}
        total_a = len(self.a_files)
        
        a_data = []
        for idx, a_file in enumerate(self.a_files):
            if self.is_cancelled: return
            if idx % 50 == 0: time.sleep(0.001) # [추가] UI 스레드에 GIL 양보
            
            if "name" in a_file:
                raw_name = os.path.splitext(a_file["name"])[0]
                core_title, nums, is_bundle = self.extract_series_and_nums(raw_name)
                if not core_title: core_title = raw_name.lower()
                a_data.append((a_file, core_title, nums, is_bundle))

        # B 폴더 그룹화 및 캐싱 (사전 작업)
        b_folders = {}
        for idx, b_file in enumerate(self.b_cache):
            if self.is_cancelled: return
            if idx % 50 == 0: time.sleep(0.001) # [추가] UI 스레드에 GIL 양보
            
            bp = b_file["path"]
            if bp not in b_folders:
                folder_name = os.path.basename(bp)
                f_core, _, _ = self.extract_series_and_nums(folder_name) if folder_name else ("", [], False)
                b_folders[bp] = {
                    "name": folder_name,
                    "core_title": f_core if f_core else folder_name.lower(),
                    "size": 0,
                    "files": []
                }
            
            if "core_title" not in b_file:
                raw_name = os.path.splitext(b_file["name"])[0]
                core_title, nums, is_bundle = self.extract_series_and_nums(raw_name)
                b_file["core_title"] = core_title if core_title else raw_name.lower()
                b_file["nums"] = nums
                b_file["is_bundle"] = is_bundle
                
            b_folders[bp]["files"].append(b_file)
            b_folders[bp]["size"] += b_file.get("size", 0)

        for i, (a_file, a_core, a_nums, a_is_bundle) in enumerate(a_data):
            if self.is_cancelled: return
            
            if i % 10 == 0: time.sleep(0.001) # [핵심 추가] 매칭 연산 중 주기적으로 UI에 제어권 양보
            
            file_matches = []
            a_path = os.path.normcase(os.path.normpath(a_file.get("full_path", "")))
            a_dir_norm = os.path.dirname(a_path)
            
            for bp, b_folder in b_folders.items():
                if self.is_cancelled: return
                
                bp_norm = os.path.normcase(os.path.normpath(bp))
                
                # 1. 폴더 단위 매칭 (A파일의 부모 폴더가 자기 자신인 경우는 제외)
                if a_dir_norm != bp_norm:
                    is_folder_match, ratio = self.check_similarity(a_core, b_folder["core_title"])
                    if is_folder_match:
                        # 폴더 전체가 매칭되면 내부 파일 검사 스킵
                        dummy_b_file = {
                            "name": "(폴더 전체 매칭)",
                            "size": b_folder["size"],
                            "full_path": bp,
                            "path": bp
                        }
                        file_matches.append({"b_file": dummy_b_file, "ratio": ratio})
                        continue
                        
                # 2. 폴더 매칭 실패 시 내부 개별 파일 매칭 진행
                for b_file in b_folder["files"]:
                    if self.is_cancelled: return
                    
                    b_full_path = os.path.normcase(os.path.normpath(b_file.get("full_path", "")))
                    if a_path == b_full_path: continue
                    
                    number_match = False
                    if a_is_bundle or b_file["is_bundle"]:
                        number_match = True
                    else:
                        if a_nums == b_file["nums"]:
                            number_match = True
                            
                    if not number_match: continue
                    
                    is_file_match, f_ratio = self.check_similarity(a_core, b_file["core_title"])
                    if is_file_match:
                        file_matches.append({"b_file": b_file, "ratio": f_ratio})
                        
            if file_matches:
                grouped = {}
                for m in file_matches:
                    bp = m["b_file"]["path"]
                    if bp not in grouped: grouped[bp] = []
                    grouped[bp].append(m)
                matches[a_file["full_path"]] = grouped
                
            if total_a > 0 and i % max(1, total_a // 20) == 0:
                self.match_progress.emit(i + 1, total_a)
                
        self.match_finished.emit(matches)

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

            if needs_img and thumb_path and os.path.exists(thumb_path):
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
                    if thumb_path: open(thumb_path, 'wb').close()
                    has_img_out = True
            elif needs_img and not has_img_out and not img_bytes:
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


class DimOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.hide()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 178))  # rgba(0,0,0,0.7)
        painter.end()

    def showEvent(self, event):
        self.raise_()
        self.resize(self.parent().size())
        super().showEvent(event)
# ==========================================
# 커스텀 테이블 뷰
# ==========================================
class CustomTableView(QTableView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rubber_band = None
        self._origin = QPoint()

    def mousePressEvent(self, event):
        index = self.indexAt(event.pos())
        if index.isValid() and event.button() == Qt.MouseButton.LeftButton:
            row_data = self.model()._data[index.row()]
            if row_data.get("is_dup_folder"):
                from PyQt6.QtGui import QFont, QFontMetrics
                
                text = f"📁 {row_data.get('path', '')} - ~{int(row_data.get('max_ratio', 0))}%"
                font = QFont("맑은 고딕", 10, QFont.Weight.Bold)
                fm = QFontMetrics(font)
                text_width = fm.horizontalAdvance(text)
                
                rect = self.visualRect(index)
                btn_rect = QRect(rect.left() + 20 + text_width + 15, rect.top() + 5, 90, 24)
                
                if btn_rect.contains(event.pos()):
                    path = row_data.get("path")
                    if os.name == 'nt': os.startfile(path)
                    else: subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', path])
                    return # 이벤트 소비

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
    
    def __init__(self, folder_path, include_sub, target_exts, thumb_dir, force_update=False):
        super().__init__()
        self.folder_path = folder_path
        self.include_sub = include_sub
        self.target_exts = tuple(target_exts)
        self.thumb_dir = thumb_dir
        self.force_update = force_update
        self.is_cancelled = False

    def run(self):
        # 1. 오프라인 방어 로직 (NAS 연결 끊김 등)
        if not os.path.exists(self.folder_path):
            self.scan_finished.emit([], 0)
            return

        # 2. 백그라운드 DB 일괄 캐싱 & WAL 모드 활성화 (UI 프리징 방지)
        from core.library_db import db
        cache_dict = {}
        try:
            db.conn.execute("PRAGMA journal_mode=WAL;")
            db.conn.commit()
            
            like_path = self.folder_path + '%' if self.include_sub else self.folder_path + '/%'
            cursor = db.conn.execute("SELECT * FROM files WHERE filepath LIKE ?", (like_path,))
            for row in cursor.fetchall():
                cache_dict[row[0]] = row
        except Exception as e:
            print(f"DB Bulk Load Error: {e}")

        file_data_cache = []
        total_size = 0
        count = 0

        # 3. os.scandir 기반 초고속 파일 시스템 순회
        def scan_dir(path):
            nonlocal total_size, count
            if self.is_cancelled: return
            try:
                with os.scandir(path) as it:
                    for entry in it:
                        if self.is_cancelled: break
                        
                        if entry.is_dir(follow_symlinks=False):
                            if self.include_sub:
                                scan_dir(entry.path)
                        elif entry.is_file(follow_symlinks=False):
                            name = entry.name
                            if name.lower().endswith(self.target_exts):
                                full_path = entry.path
                                stat = entry.stat()
                                mtime = stat.st_mtime
                                ctime = stat.st_ctime
                                size = stat.st_size
                                
                                cached = cache_dict.get(full_path)
                                meta_processed = False
                                full_meta = {}
                                res, title, series, vol, num, writer = "", "", "", "", "", ""
                                
                                # DB 정보와 mtime 대조
                                if cached and len(cached) >= 32 and abs(float(cached[1]) - float(mtime)) < 2.0 and not self.force_update:
                                    meta_processed = True
                                    res, title, series = cached[4], cached[5], cached[6]
                                    vol, num, writer = cached[8], cached[9], cached[10]
                                    
                                    full_meta = {
                                        "resolution": cached[4], "title": cached[5], "series": cached[6], "series_group": cached[7],
                                        "volume": cached[8], "number": cached[9], "writer": cached[10], "creators": cached[11], 
                                        "publisher": cached[12], "imprint": cached[13], "genre": cached[14], "volume_count": cached[15], 
                                        "page_count": cached[16], "format": cached[17], "manga": cached[18], "language": cached[19],
                                        "rating": cached[20], "age_rating": cached[21], "publish_date": cached[22], 
                                        "summary": cached[23], "characters": cached[24], "teams": cached[25], "locations": cached[26], 
                                        "story_arc": cached[27], "tags": cached[28], "notes": cached[29], "web": cached[30]
                                    }

                                file_hash = hashlib.md5(f"{full_path}_{mtime}".encode()).hexdigest()
                                thumb_path = os.path.join(self.thumb_dir, f"{file_hash}.webp")
                                has_thumb = os.path.exists(thumb_path)
                                
                                from datetime import datetime
                                row_dict = {
                                    "full_path": full_path, 
                                    "hash": file_hash,
                                    "name": name,
                                    "path": path, 
                                    "ext": os.path.splitext(name)[1].lower(), 
                                    "raw_size": size,
                                    "raw_mtime": mtime,
                                    "raw_ctime": ctime,
                                    "ctime": datetime.fromtimestamp(ctime).strftime('%Y-%m-%d %H:%M'),
                                    "mtime": datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M'),
                                    "thumb_processed": has_thumb, 
                                    "meta_processed": meta_processed, 
                                    "full_meta": full_meta,
                                    "res": res, "series": series, "title": title, "vol": vol, "num": num, "writer": writer,
                                    "display_index": -1 
                                }
                                file_data_cache.append(row_dict)
                                total_size += size
                                count += 1
                                
                                if count % 1000 == 0:
                                    self.progress_updated.emit(count)
            except Exception: pass

        scan_dir(self.folder_path)
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
            text = _("group_header").format(row_data['name'], row_data['count'])
            flags = Qt.AlignmentFlag.AlignLeft.value | Qt.AlignmentFlag.AlignVCenter.value
            painter.drawText(option.rect.adjusted(10, 0, -10, -5), flags, text)
            
            painter.setPen(QColor("#555555"))
            painter.drawLine(option.rect.left() + 5, option.rect.bottom() - 2, option.rect.right() - 5, option.rect.bottom() - 2)
            painter.restore()
            return
        
        # --- [수정됨] 중복 정보 (폴더 단위) ---
        if row_data.get("is_dup_folder"):
            painter.fillRect(option.rect, QColor("#1e1e1e"))
            painter.setPen(QColor("#e67e22"))
            font = QFont("맑은 고딕", 10, QFont.Weight.Bold)
            painter.setFont(font)
            text = f"📁 {row_data['path']} - ~{int(row_data['max_ratio'])}%"
            
            flags = Qt.AlignmentFlag.AlignLeft.value | Qt.AlignmentFlag.AlignVCenter.value
            painter.drawText(option.rect.adjusted(20, 0, 0, 0), flags, text)
            
            fm = painter.fontMetrics()
            text_width = fm.horizontalAdvance(text)
            
            # 텍스트 바로 옆에 '폴더 열기' 버튼 그리기
            btn_rect = QRect(option.rect.left() + 20 + text_width + 15, option.rect.top() + 5, 90, 24)
            painter.fillRect(btn_rect, QColor("#3a3a3a"))
            painter.setPen(QColor("#ffffff"))
            painter.drawRect(btn_rect)
            flags_center = Qt.AlignmentFlag.AlignCenter.value
            painter.drawText(btn_rect, flags_center, _("btn_open_folder"))
            painter.restore()
            return

        # --- [수정됨] 중복 정보 (파일 단위) ---
        if row_data.get("is_dup_child"):
            painter.fillRect(option.rect, QColor("#1e1e1e"))
            painter.setPen(QColor("#aaaaaa"))
            font = QFont("맑은 고딕", 9)
            painter.setFont(font)
            text = f"      └ 📦 {row_data['name']} ({row_data['size_str']}) - {int(row_data['ratio'])}%"
            flags = Qt.AlignmentFlag.AlignLeft.value | Qt.AlignmentFlag.AlignVCenter.value
            painter.drawText(option.rect.adjusted(20, 0, -10, 0), flags, text)
            painter.restore()
            return
            
        if self.view_mode == "detail":
            col_id = index.model().active_columns[index.column()]
            if col_id == "cover":
                file_hash = row_data.get("hash", "")
                pixmap = QPixmap()
                if file_hash:
                    cached_pixmap = QPixmapCache.find(file_hash)
                    if cached_pixmap is not None and not cached_pixmap.isNull():
                        pixmap = cached_pixmap
                    else:
                        thumb_path = os.path.join(self.thumb_dir, f"{file_hash}.webp")
                        if row_data.get("thumb_processed") and os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
                            pixmap.load(thumb_path)
                            if not pixmap.isNull():
                                QPixmapCache.insert(file_hash, pixmap)
                
                if option.state & QStyle.StateFlag.State_Selected:
                    painter.fillRect(option.rect, QColor("#3a7ebf"))
                    
                if not pixmap.isNull():
                    rect = option.rect
                    target_rect = rect.adjusted(2, 2, -2, -2)
                    scaled_pixmap = pixmap.scaled(
                        target_size:=target_rect.size(),
                        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                        Qt.TransformationMode.SmoothTransformation
                    )
                    crop_x = (scaled_pixmap.width() - target_rect.width()) // 2
                    crop_y = (scaled_pixmap.height() - target_rect.height()) // 2
                    cropped_pixmap = scaled_pixmap.copy(crop_x, crop_y, target_rect.width(), target_rect.height())
                    painter.drawPixmap(target_rect.topLeft(), cropped_pixmap)
                painter.restore()
                return 
            else:
                super().paint(painter, option, index)
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
        # is_dup_folder, is_dup_child 도 동일한 행 높이 사용
        if row_data.get("is_group") or row_data.get("is_dup_folder") or row_data.get("is_dup_child"):
            width = self.parent().viewport().width() if hasattr(self.parent(), 'viewport') else 800
            return QSize(width - 20, 35)
        
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
        self.setWindowTitle(_("dlg_edit_lay_title"))
        self.setFixedSize(320, 500)
        self.setStyleSheet("background-color: #2b2b2b; color: white;")
        self.selected_columns = list(current_columns)
        self.all_columns = all_columns
        self.checkboxes = {}
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(_("dlg_edit_lay_msg")))
        
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
    def __init__(self, data=None, thumb_dir=""):
        super().__init__()
        self._data = data or []
        self.thumb_dir = thumb_dir
        self.ALL_COLUMNS = {
            "cover": _("col_cover"),
            "name": _("col_name"), "size": _("col_size"), "res": _("col_res"), "mtime": _("col_mtime"), "ctime": _("col_ctime"), 
            "path": _("col_path"), "ext": _("col_ext"), "series": _("col_series"), "title": _("col_title"), 
            "vol": _("col_vol"), "num": _("col_num"), "writer": _("col_writer"),
            "series_group": _("col_series_group"), "creators": _("col_creators"), "publisher": _("col_publisher"), "imprint": _("col_imprint"),
            "genre": _("col_genre"), "volume_count": _("col_vol_count"), "page_count": _("col_page_count"), "format": _("col_format"),
            "manga": _("col_manga"), "language": _("col_language"), "rating": _("col_rating"), "age_rating": _("col_age_rating"), 
            "publish_date": _("col_pub_date"), "summary": _("col_summary"), "characters": _("col_characters"), 
            "teams": _("col_teams"), "locations": _("col_locations"), "story_arc": _("col_story_arc"), 
            "tags": _("col_tags"), "notes": _("col_notes"), "web": _("col_web")
        }
        self.active_columns = ["cover", "name", "size", "mtime", "series", "title", "writer"]

    def set_columns(self, columns):
        self.beginResetModel()
        self.active_columns = [c for c in columns if c in self.ALL_COLUMNS]
        self.endResetModel()

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._data): return None
        row_data = self._data[index.row()]

        if row_data.get("is_group"):
            if role == Qt.ItemDataRole.DisplayRole and index.column() == 0:
                return _("group_header").format(row_data['name'], row_data['count'])
            elif role == Qt.ItemDataRole.BackgroundRole:
                return QColor("#222222")
            elif role == Qt.ItemDataRole.ForegroundRole:
                return QColor("#3498DB")
            elif role == Qt.ItemDataRole.FontRole:
                font = QFont()
                font.setBold(True)
                return font
            return None

        col_id = self.active_columns[index.column()]

        if col_id == "cover" and role == Qt.ItemDataRole.DisplayRole:
            return None 

        if role == Qt.ItemDataRole.TextAlignmentRole:
            if col_id in ["res", "vol", "num", "size", "mtime", "ctime", "volume_count", "page_count", "rating", "age_rating", "publish_date"]:
                return Qt.AlignmentFlag.AlignCenter.value
            return Qt.AlignmentFlag.AlignLeft.value | Qt.AlignmentFlag.AlignVCenter.value

        if role == Qt.ItemDataRole.DisplayRole:
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
        row_data = self._data[index.row()]
        # 중복행들도 클릭(선택)이 안되도록 처리
        if row_data.get("is_group") or row_data.get("is_dup_folder") or row_data.get("is_dup_child"):
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
        
        # [핵심 추가] 초기 언어 설정 (config에서 불러옴)
        lang = self.config.get("language", self.config.get("lang", "ko"))
        set_language(lang)
        
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
        self.is_force_syncing = False

        self.scroll_timer = QTimer()
        self.scroll_timer.setSingleShot(True)
        self.scroll_timer.timeout.connect(self._do_background_load)
        
        self.grouping_timer = QTimer()
        self.grouping_timer.setSingleShot(True)
        self.grouping_timer.timeout.connect(self.apply_grouping_and_sorting)

        # --- [추가됨] 중복 검사용 캐시 및 스레드 변수 ---
        self.b_folder_cache = []
        self.dup_matches = {}
        self.dup_scan_thread = None
        self.dup_match_thread = None
        # ----------------------------------------------

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
        QTimer.singleShot(1000, self.start_dup_scan)

    
    def eventFilter(self, obj, event):
        if obj is self.table_view and event.type() == event.Type.Resize:
            if hasattr(self, 'dim_overlay'):
                self.dim_overlay.resize(self.table_view.size())
        return super().eventFilter(obj, event)
    
    # --- [추가됨] 백그라운드 스레드 제어 메서드 ---
    def start_dup_scan(self):
        t = time.time()
        print(f"[LOG] start_dup_scan 진입: {time.time()-t:.3f}s")
        
        dup_folders = self.config.get("dup_check_folders", [])
        if not dup_folders: return
        target_exts = ('.zip', '.cbz', '.cbr', '.rar', '.7z')
        
        if self.dup_scan_thread and self.dup_scan_thread.isRunning():
            print(f"[LOG] 기존 DupScanThread 대기 중...")
            self.dup_scan_thread.cancel()
            self.dup_scan_thread.wait()
            print(f"[LOG] 기존 DupScanThread 종료 완료: {time.time()-t:.3f}s")
            
        self.lbl_tree_status.setText(_("dup_scan_start"))

        # [추가] 자세히 보기 모드일 때 리스트 패널 비활성화
        if self.view_stack.currentIndex() == 0:
            self.dim_overlay.show()
            
        self.dup_scan_thread = DupScanThread(dup_folders, target_exts)
        self.dup_scan_thread.progress_updated.connect(self.on_dup_scan_progress)
        self.dup_scan_thread.scan_finished.connect(self.on_dup_scan_finished)
        self.dup_scan_thread.start()
        print(f"[LOG] DupScanThread 시작 완료: {time.time()-t:.3f}s")

    def on_dup_scan_progress(self, match_count, total_scanned):
        msg = _("dup_scan_progress").format(total_scanned, match_count)
        self.lbl_tree_status.setText(msg)

    def on_dup_scan_finished(self, b_cache):
        self.b_folder_cache = b_cache
        
        msg = _("dup_scan_complete").format(len(b_cache))
        self.lbl_tree_status.setText(msg) # i18n 적용
        
        try:
            from ui.widgets import Toast
            Toast.show(self.main_window, msg)
        except:
            pass

        if self.file_data_cache:
            self.start_dup_match()

    # 중복 검사 토글 이벤트 처리
    def on_dup_check_toggled(self, checked):
        import time
        print(f"\n[LOG] =================================")
        print(f"[LOG] 중복 검사 버튼 토글 (checked={checked})")
        self.btn_dup_check.setText(_("folder_dup_check_on") if checked else _("folder_dup_check_off"))
        
        if checked:
            if not hasattr(self, 'b_folder_cache') or not self.b_folder_cache:
                print(f"[LOG] b_folder_cache 없음, start_dup_scan 호출")
                self.start_dup_scan()
            else:
                print(f"[LOG] b_folder_cache 존재, start_dup_match 호출")
                self.start_dup_match()
        else:
            print(f"[LOG] 버튼 OFF, 스레드 취소 및 렌더링 복구 시작")
            if hasattr(self, 'dup_match_thread') and self.dup_match_thread.isRunning():
                self.dup_match_thread.cancel()
            # [추가] 버튼 OFF 시 즉시 활성화 복원
            self.dim_overlay.hide()
            self.apply_grouping_and_sorting()
            self.lbl_tree_status.setText(_("folder_ready"))

    def start_dup_match(self):
        import time
        t = time.time()
        print(f"[LOG] start_dup_match 진입: {time.time()-t:.3f}s")
        
        if not self.btn_dup_check.isChecked(): return
        if not hasattr(self, 'b_folder_cache') or not self.b_folder_cache: return
        if not hasattr(self, 'file_data_cache') or not self.file_data_cache: return
        
        current_a_paths = tuple(f.get("full_path") for f in self.file_data_cache)
        if hasattr(self, 'last_matched_a_paths') and self.last_matched_a_paths == current_a_paths:
            print(f"[LOG] 동일 데이터 감지, 캐시된 결과로 UI 갱신 시작")
            self.apply_grouping_and_sorting()
            count = sum(len(v) for v in getattr(self, 'dup_matches', {}).values())
            self.lbl_tree_status.setText(_("dup_match_found").format(count) if count > 0 else _("dup_match_none"))
            return
            
        self.last_matched_a_paths = current_a_paths
        
        if self.dup_match_thread and self.dup_match_thread.isRunning():
            self.dup_match_thread.cancel()
            self.dup_match_thread.wait()
            
        self.lbl_tree_status.setText(_("dup_match_start"))

        # [추가] 자세히 보기 모드일 때 리스트 패널 비활성화
        if self.view_stack.currentIndex() == 0:
            self.dim_overlay.show()
            
        self.dup_match_thread = DupMatchThread(self.file_data_cache, self.b_folder_cache)
        self.dup_match_thread.match_progress.connect(self.on_dup_match_progress)
        self.dup_match_thread.match_finished.connect(self.on_dup_match_finished)
        self.dup_match_thread.start()
        print(f"[LOG] DupMatchThread 시작 완료: {time.time()-t:.3f}s")
            
        self.last_matched_a_paths = current_a_paths
        
        if self.dup_match_thread and self.dup_match_thread.isRunning():
            self.dup_match_thread.cancel()
            self.dup_match_thread.wait()
            
        self.lbl_tree_status.setText(_("dup_match_start"))
            
        self.dup_match_thread = DupMatchThread(self.file_data_cache, self.b_folder_cache)
        self.dup_match_thread.match_progress.connect(self.on_dup_match_progress)
        self.dup_match_thread.match_finished.connect(self.on_dup_match_finished)
        self.dup_match_thread.start()

    # 매칭 진행 상황 표시
    def on_dup_match_progress(self, current, total):
        msg = _("dup_match_progress").format(current, total)
        self.lbl_tree_status.setText(msg)

    def on_dup_match_finished(self, matches):
        self.dup_matches = matches
        self.apply_grouping_and_sorting()
        
        count = sum(len(v) for v in matches.values())
        if count > 0:
            msg = _("dup_match_found").format(count)
        else:
            msg = _("dup_match_none")
            
        self.lbl_tree_status.setText(msg)
    # ----------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, 'main_optimize_btn') and self.main_optimize_btn:
            self.main_optimize_btn.hide()
        if hasattr(self, 'main_status_label') and self.main_status_label:
            self.main_status_label.setText(_("folder_ready"))

    def hideEvent(self, event):
        super().hideEvent(event)
        if hasattr(self, 'main_optimize_btn') and self.main_optimize_btn:
            self.main_optimize_btn.show()

    def find_main_window_elements(self):
        for lbl in self.main_window.findChildren(QLabel):
            if lbl.text() in ["대기 중...", "Ready", "待機中..."] or "대기 중" in lbl.text():
                self.main_status_label = lbl
                break
                
        for btn in self.main_window.findChildren(QPushButton):
            if "최적화" in btn.text() or "Optimize" in btn.text() or "最適化" in btn.text():
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
        
        # --- 가로로 꽉 차게 늘어나도록 Expanding 정책 설정 ---
        expanding_policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self.btn_subfolders = QPushButton(_("folder_inc_sub_off"))
        self.btn_subfolders.setCheckable(True)
        self.btn_subfolders.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_subfolders.setStyleSheet(toggle_btn_style)
        self.btn_subfolders.setSizePolicy(expanding_policy) # 50% 확장을 위해 변경
        
        self.btn_dup_check = QPushButton(_("folder_dup_check_off"))
        self.btn_dup_check.setCheckable(True)
        self.btn_dup_check.setChecked(False)
        self.btn_dup_check.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_dup_check.setStyleSheet(toggle_btn_style)
        self.btn_dup_check.setSizePolicy(expanding_policy) # 50% 확장을 위해 변경

        self.btn_refresh_tree = QPushButton(_("folder_refresh_tree"))
        self.btn_refresh_tree.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh_tree.setStyleSheet(toggle_btn_style)
        self.btn_refresh_tree.setSizePolicy(expanding_policy) # 100% 확장을 위해 변경

        # --- [1번째 줄] 하위 폴더 포함 (50%) / 중복 검사 (50%) ---
        row1_layout = QHBoxLayout()
        row1_layout.setSpacing(5) # 버튼 사이 여백
        row1_layout.addWidget(self.btn_subfolders)
        row1_layout.addWidget(self.btn_dup_check)
        # addStretch()를 제거하여 남는 공간 없이 꽉 채우도록 함
        left_layout.addLayout(row1_layout)

        # --- [2번째 줄] 새로고침 (100%) ---
        row2_layout = QHBoxLayout()
        row2_layout.addWidget(self.btn_refresh_tree)
        # addStretch()를 제거하여 남는 공간 없이 꽉 채우도록 함
        left_layout.addLayout(row2_layout)

        # --- [3번째 줄] 빠른 이동 (콤보박스) ---
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
            QTreeView { border: none; background-color: transparent; outline: none; color: white; } 
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
        
        self.btn_sidebar = QPushButton(_("folder_sidebar_on"))
        self.btn_sidebar.setCheckable(True)
        self.btn_sidebar.setChecked(True)
        self.btn_sidebar.setStyleSheet(toggle_btn_style)
        
        menu_btn_style = """
            QToolButton { background-color: transparent; color: white; padding: 5px; font-weight: bold; border: none; }
            QToolButton:hover { color: #3498DB; }
            QToolButton::menu-indicator { image: none; }
        """
        
        self.btn_views = QToolButton()
        self.btn_views.setText(_("folder_views"))
        self.btn_views.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_views.setStyleSheet(menu_btn_style)
        
        self.btn_grouped = QToolButton()
        self.btn_grouped.setText(_("folder_grouped"))
        self.btn_grouped.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_grouped.setStyleSheet(menu_btn_style)

        self.btn_sorted = QToolButton()
        self.btn_sorted.setText(_("folder_sorted"))
        self.btn_sorted.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_sorted.setStyleSheet(menu_btn_style)

        self.btn_layouts = QToolButton()
        self.btn_layouts.setText(_("folder_layouts"))
        self.btn_layouts.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.btn_layouts.setStyleSheet(menu_btn_style)
        
        self.btn_export = QPushButton(_("folder_export_csv"))
        self.btn_export.setStyleSheet(toggle_btn_style)
        
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText(_("folder_search_ph"))
        self.search_bar.setClearButtonEnabled(True)
        self.search_bar.setFixedWidth(220)
        self.search_bar.setStyleSheet("""
            QLineEdit { background-color: #1e1e1e; color: white; border: 1px solid #555; border-radius: 12px; padding: 4px 10px; }
            QLineEdit:focus { border: 1px solid #3498DB; }
        """)
        
        self.btn_refresh_list = QPushButton(_("folder_refresh_list"))
        
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
        self.table_model = LibraryTableModel(thumb_dir=self.thumb_dir)
        self.item_delegate = ThumbnailDelegate(self.view_stack, self.thumb_dir)
        
        self.table_view = CustomTableView()
        self.table_view.setModel(self.table_model)
        self.table_view.installEventFilter(self)
        self.table_view.setItemDelegate(self.item_delegate)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table_view.verticalHeader().hide()
        self.table_view.setAlternatingRowColors(True)
        self.table_view.setSortingEnabled(False) 
        self.table_view.horizontalHeader().setSortIndicatorShown(True)
        self.table_view.horizontalHeader().setSectionsMovable(True)
        self.table_view.setStyleSheet("QTableView { border: none; background-color: transparent; color: white; }")
        self.table_view.setDragEnabled(False)
        self.table_view.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self.table_view.verticalHeader().setDefaultSectionSize(64) 
        self.table_view.setIconSize(QSize(45, 60)) 
        
        self.dim_overlay = DimOverlay(self.table_view)

        self.list_view = QListView()
        self.list_view.setModel(self.table_model)
        self.list_view.setItemDelegate(self.item_delegate)
        self.list_view.setViewMode(QListView.ViewMode.IconMode)
        self.list_view.setResizeMode(QListView.ResizeMode.Adjust)
        self.list_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_view.setSelectionRectVisible(True)
        self.list_view.setSpacing(10)
        self.list_view.setWordWrap(True)
        self.list_view.setStyleSheet("QListView { border: none; background-color: transparent;  color: white; }")
        self.list_view.setDragEnabled(False)
        self.list_view.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)

        self.table_view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table_view.verticalScrollBar().setSingleStep(15)
        self.list_view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list_view.verticalScrollBar().setSingleStep(15)

        self.view_stack.addWidget(self.table_view)
        self.view_stack.addWidget(self.list_view)
        right_top_layout.addWidget(self.view_stack)

        self.right_bottom_panel = QFrame()
        self.right_bottom_panel.setStyleSheet("QFrame { background-color: #2b2b2b; border-radius: 5px; border: 1px solid #444; }")
        right_bottom_layout = QHBoxLayout(self.right_bottom_panel)
        right_bottom_layout.setContentsMargins(15, 15, 15, 15)
        
        self.lbl_cover = QLabel(_("folder_cover_img"))
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
        
        self.lbl_tree_status = QLabel(_("folder_ready"))
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
        bottom_bar.addWidget(QLabel(_("folder_item_size")))
        bottom_bar.addWidget(self.slider_item_size)
        
        self.main_layout.addLayout(bottom_bar)
        
        self.btn_sidebar.toggled.connect(self.toggle_sidebar)
        self.btn_sidebar.toggled.connect(lambda checked: self.btn_sidebar.setText(_("folder_sidebar_on") if checked else _("folder_sidebar_off")))
        self.btn_refresh_tree.clicked.connect(self.refresh_tree)
        self.btn_refresh_list.clicked.connect(self.refresh_list)
        self.btn_subfolders.toggled.connect(self.refresh_list)
        self.btn_subfolders.toggled.connect(lambda checked: self.btn_subfolders.setText(_("folder_inc_sub_on") if checked else _("folder_inc_sub_off")))

        self.btn_dup_check.toggled.connect(self.on_dup_check_toggled)
        
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

    def _do_background_load(self):
        if self.is_force_syncing:
            return

        if self.extract_thread and self.extract_thread.isRunning():
            return

        view = self.get_active_view()
        rect = view.viewport().rect()
        target_exts = ('.zip', '.cbz', '.cbr', '.rar', '.7z')
        
        selected_paths = set(self.get_selected_files())
        visible_tasks = []
        hidden_tasks = []
        
        for r in self.table_model._data:
            # [수정됨] 그룹 헤더뿐만 아니라 중복 파일 표기용 가짜 행들도 추출 스캔 대상에서 완벽히 스킵합니다.
            if r.get("is_group") or r.get("is_dup_folder") or r.get("is_dup_child"): continue
            
            fp = r.get("full_path", "")
            if not fp.lower().endswith(target_exts): continue
            
            has_img = r.get("thumb_processed")
            has_meta = r.get("meta_processed")
            
            if has_img and has_meta: continue
            
            disp_idx = r.get("display_index", -1)
            if disp_idx >= 0:
                idx = self.table_model.index(disp_idx, 0)
                is_visible = view.visualRect(idx).intersects(rect) and view.visualRect(idx).isValid()
            else:
                is_visible = False
                
            is_selected = fp in selected_paths
            needs_img = not has_img
            needs_meta = not has_meta
            
            thumb_path = os.path.join(self.thumb_dir, f"{r.get('hash', '')}.webp")
            task = (fp, needs_img, needs_meta, thumb_path)
            
            if is_visible or is_selected:
                visible_tasks.append(task)
            else:
                hidden_tasks.append(task)
                
        if not visible_tasks and not hidden_tasks:
            self.is_syncing = False
            self.progress_bar.hide()
            if hasattr(self, 'main_status_label') and self.main_status_label:
                self.main_status_label.setText(self.i18n.get("folder_ready", "Ready") if hasattr(self, 'i18n') else "Ready")
            return

        tasks = (visible_tasks + hidden_tasks)[:50] 
        real_heavy_tasks_count = sum(1 for t in tasks if t[2] or (t[1] and not os.path.exists(t[3])))
        
        if not self.is_syncing and real_heavy_tasks_count > 0:
            total_heavy = sum(1 for r in self.table_model._data if not r.get("is_group") and not r.get("is_dup_folder") and not r.get("is_dup_child") and not r.get("meta_processed") and r.get("full_path", "").lower().endswith(target_exts))
            self.sync_total_tasks = total_heavy
            self.sync_completed_tasks = 0
            self.is_syncing = True

        seven_zip_path = get_resource_path('7za.exe')
        self.extract_thread = MemoryExtractThread(tasks, seven_zip_path)
        self.extract_thread.show_progress = (real_heavy_tasks_count > 0)
        self.extract_thread.data_extracted.connect(self.on_metadata_extracted)
        self.extract_thread.progress_updated.connect(self.on_extract_progress)
        self.extract_thread.finished.connect(lambda: self.scroll_timer.start(10))
        self.extract_thread.start()

    def on_extract_progress(self, count):
        if not self.is_syncing and not self.is_force_syncing: return
        
        self.sync_completed_tasks += count
        if self.sync_completed_tasks > self.sync_total_tasks:
            self.sync_completed_tasks = self.sync_total_tasks

        self.progress_bar.show()
        self.progress_bar.setMaximum(self.sync_total_tasks)
        self.progress_bar.setValue(self.sync_completed_tasks)
        
        status_text = _("folder_optimizing").format(self.sync_completed_tasks, self.sync_total_tasks)
        if hasattr(self, 'main_status_label') and self.main_status_label:
            self.main_status_label.setText(status_text)
            
        if self.sync_completed_tasks >= self.sync_total_tasks:
            self.progress_bar.hide()
            self.is_syncing = False
            self.is_force_syncing = False
            if hasattr(self, 'main_status_label') and self.main_status_label:
                self.main_status_label.setText(_("folder_ready"))

    def force_update_selected_files(self):
        paths = self.get_selected_files()
        if not paths: return
        
        target_exts = ('.zip', '.cbz', '.cbr', '.rar', '.7z')
        tasks = []
        
        for fp in paths:
            row = self.file_data_map.get(fp)
            if row and fp.lower().endswith(target_exts):
                file_hash = row.get("hash", "")
                if file_hash:
                    thumb_path = os.path.join(self.thumb_dir, f"{file_hash}.webp")
                    if os.path.exists(thumb_path):
                        try: os.remove(thumb_path)
                        except: pass
                    QPixmapCache.remove(file_hash)
                
                row["meta_processed"] = False
                row["thumb_processed"] = False
                row["res"] = ""
                row["full_meta"] = {}
                
                tasks.append((fp, True, True, thumb_path))
                
        if not tasks: return

        if self.extract_thread and self.extract_thread.isRunning():
            self.extract_thread.cancel()
            self.extract_thread.wait()
            self.extract_thread = None
            
        self.scroll_timer.stop()
        self.is_force_syncing = True 
        self.is_syncing = False 

        self.sync_total_tasks = len(tasks)
        self.sync_completed_tasks = 0
        
        self.apply_grouping_and_sorting()
        
        seven_zip_path = get_resource_path('7za.exe')
        self.extract_thread = MemoryExtractThread(tasks, seven_zip_path)
        self.extract_thread.show_progress = True
        self.extract_thread.data_extracted.connect(self.on_metadata_extracted)
        self.extract_thread.progress_updated.connect(self.on_extract_progress)
        self.extract_thread.start()

    def export_csv(self):
        if not self.table_model._data:
            QMessageBox.information(self, "Export", _("dlg_exp_no_data"))
            return
            
        filepath, _ = QFileDialog.getSaveFileName(self, _("dlg_exp_title"), "My_Library_Export.csv", "CSV Files (*.csv)")
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
                    
            QMessageBox.information(self, "Export", _("dlg_exp_done"))
        except Exception as e:
            QMessageBox.critical(self, "Export Error", _("dlg_err_occurred").format(e))

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
        self.combo_quick_access.addItem(_("folder_quick_access"), "")
        paths = [
            (_("folder_desktop"), QStandardPaths.StandardLocation.DesktopLocation),
            (_("folder_docs"), QStandardPaths.StandardLocation.DocumentsLocation),
            (_("folder_downloads"), QStandardPaths.StandardLocation.DownloadLocation),
            (_("folder_home"), QStandardPaths.StandardLocation.HomeLocation),
        ]
        for name, loc in paths:
            path = QStandardPaths.writableLocation(loc)
            if path: self.combo_quick_access.addItem(name, path)

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
        self.menu_views.addAction(_("menu_detail"), lambda: self.set_view_mode("detail"))
        self.menu_views.addAction(_("menu_thumbnail"), lambda: self.set_view_mode("thumbnail"))
        self.menu_views.addAction(_("menu_tile"), lambda: self.set_view_mode("tile"))
        self.btn_views.setMenu(self.menu_views)

        self.menu_grouped = QMenu(self)
        self.menu_grouped.addAction(_("menu_none"), lambda: self.set_grouping("none"))
        self.menu_grouped.addAction(_("menu_folder"), lambda: self.set_grouping("path"))
        self.menu_grouped.addAction(_("col_ext"), lambda: self.set_grouping("ext"))
        self.menu_grouped.addAction(_("col_series"), lambda: self.set_grouping("series"))
        self.menu_grouped.addAction(_("col_writer"), lambda: self.set_grouping("writer"))
        self.btn_grouped.setMenu(self.menu_grouped)

        self.menu_sorted = QMenu(self)
        self.menu_sorted.addAction(_("col_name"), lambda: self.set_sorting("name"))
        self.menu_sorted.addAction(_("col_size"), lambda: self.set_sorting("size"))
        self.menu_sorted.addAction(_("col_mtime"), lambda: self.set_sorting("mtime"))
        self.menu_sorted.addAction(_("col_ext"), lambda: self.set_sorting("ext"))
        self.menu_sorted.addAction(_("col_series"), lambda: self.set_sorting("series"))
        self.menu_sorted.addAction(_("col_title"), lambda: self.set_sorting("title"))
        self.menu_sorted.addAction(_("col_writer"), lambda: self.set_sorting("writer"))
        self.menu_sorted.addSeparator()
        self.menu_sorted.addAction(_("menu_toggle_order"), self.toggle_sort_order)
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
        QShortcut(QKeySequence("F1"), self).activated.connect(self.send_to_tab1)
        QShortcut(QKeySequence("F2"), self).activated.connect(self.send_to_tab2)
        QShortcut(QKeySequence("F3"), self).activated.connect(self.hotkey_f3)
        QShortcut(QKeySequence("Del"), self).activated.connect(self.delete_selected)

    def hotkey_f3(self): # F2였던 메서드명을 논리에 맞게 변경
        if self.tree_view.hasFocus():
            self.rename_folder()
        else:
            self.send_to_tab3()

    def rename_folder(self, index=None):
        if not index:
            index = self.tree_view.currentIndex()
        if not index.isValid(): return
        
        old_path = self.dir_model.filePath(index)
        old_name = os.path.basename(old_path)
        
        new_name, ok = QInputDialog.getText(self, _("dlg_ren_folder_title"), _("dlg_ren_folder_msg"), text=old_name)
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
                QMessageBox.critical(self, _("dlg_err"), _("dlg_err_ren_folder").format(e))

    def delete_selected(self):
        from PyQt6.QtCore import QFile

        if self.table_view.hasFocus() or self.list_view.hasFocus():
            files = self.get_selected_files()
            if not files: return
            
            reply = QMessageBox.question(self, _("dlg_del_file_title"), _("dlg_del_file_msg").format(len(files)), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                for f in files:
                    try: 
                        # os.remove(f) 완전 삭제 대신 휴지통으로 이동
                        QFile.moveToTrash(f)
                    except Exception as e: print(f"Delete error: {e}")
                self.refresh_list(force_update=True)
                
        elif self.tree_view.hasFocus():
            index = self.tree_view.currentIndex()
            if not index.isValid(): return
            path = self.dir_model.filePath(index)
            
            reply = QMessageBox.question(self, _("dlg_del_folder_title"), _("dlg_del_folder_msg").format(os.path.basename(path)), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                try:
                    shutil.rmtree(path)
                    self.remove_from_favorites(path)
                except Exception as e:
                    QMessageBox.critical(self, _("dlg_err"), _("dlg_del_err").format(e))

    def load_initial_layout(self):
        view_mode = self.config.get("folder_view_mode", "detail")
        self.set_view_mode(view_mode)
        
        active_cols = self.config.get("folder_active_columns", ["cover", "name", "size", "mtime", "series", "title", "writer"])
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
        self.menu_layouts.addAction(_("menu_edit_layout"), self.open_layout_editor)
        self.menu_layouts.addAction(_("menu_save_layout"), self.save_named_layout)
        self.menu_layouts.addAction(_("menu_del_layout"), self.delete_named_layout)
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
        name, ok = QInputDialog.getText(self, _("menu_save_layout"), _("dlg_save_lay_msg"))
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
        name, ok = QInputDialog.getItem(self, _("menu_del_layout"), _("dlg_del_lay_msg"), list(saved_layouts.keys()), 0, False)
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
            self.item_delegate.view_mode = "detail"
        else:
            self.view_stack.setCurrentIndex(1)
            self.item_delegate.view_mode = mode
            self.item_delegate.item_size = self.slider_item_size.value()
            self.list_view.setGridSize(QSize()) 
            self.list_view.doItemsLayout()
        self.table_model.layoutChanged.emit()
        self.apply_grouping_and_sorting()

    def on_size_changed(self, value):
        self.item_delegate.item_size = value
        self.table_model.layoutChanged.emit()
        self.list_view.doItemsLayout()
        
        table_row_height = max(36, int(value * 0.6))
        self.table_view.verticalHeader().setDefaultSectionSize(table_row_height)
        
        icon_h = table_row_height - 4
        icon_w = int(icon_h * 0.75)
        self.table_view.setIconSize(QSize(icon_w, icon_h))

    def toggle_sidebar(self, checked):
        self.left_panel.setVisible(checked)

    def set_grouping(self, key):
        self.current_group_key = key
        self.apply_grouping_and_sorting()

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

    def on_header_clicked(self, logicalIndex):
        key = self.table_model.active_columns[logicalIndex]
        if self.current_sort_key == key:
            self.current_sort_order = Qt.SortOrder.DescendingOrder if self.current_sort_order == Qt.SortOrder.AscendingOrder else Qt.SortOrder.AscendingOrder
        else:
            self.current_sort_key = key
            self.current_sort_order = Qt.SortOrder.AscendingOrder
        
        self.table_view.horizontalHeader().setSortIndicator(logicalIndex, self.current_sort_order)
        self.apply_grouping_and_sorting()

    def toggle_sort_order(self):
        self.current_sort_order = Qt.SortOrder.DescendingOrder if self.current_sort_order == Qt.SortOrder.AscendingOrder else Qt.SortOrder.AscendingOrder
        if self.current_sort_key in self.table_model.active_columns:
            idx = self.table_model.active_columns.index(self.current_sort_key)
            self.table_view.horizontalHeader().setSortIndicator(idx, self.current_sort_order)
        self.apply_grouping_and_sorting()

    def apply_grouping_and_sorting(self):
        import time
        from collections import Counter
        t0 = time.time()
        print(f"\n[LOG] 1. apply_grouping_and_sorting 시작")
        
        # [최적화] 극심한 프리징을 유발하는 원인 1: clearSpans 제거 (update_data 호출 시 자동 초기화됨)
        # self.table_view.clearSpans() 
        
        search_query = self.search_bar.text().strip().lower()
        
        data = []
        for row in self.file_data_cache:
            if search_query:
                search_target = f"{row.get('name','')} {row.get('title','')} {row.get('series','')} {row.get('writer','')}".lower()
                if search_query not in search_target: continue
            data.append(row)

        print(f"[LOG] 2. 검색 필터링 완료: {time.time()-t0:.3f}s")

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

        print(f"[LOG] 3. 정렬 중...")
        if self.current_group_key != "none":
            data.sort(key=lambda x: safe_get(x, col_id), reverse=reverse)
            data.sort(key=lambda x: safe_get(x, self.current_group_key), reverse=False) 
        else:
            data.sort(key=lambda x: safe_get(x, col_id), reverse=reverse)
            
        print(f"[LOG] 4. 정렬 완료: {time.time()-t0:.3f}s")
            
        display_data = []
        
        if self.current_group_key != "none":
            # [최적화] 극심한 프리징을 유발하는 원인 2: O(N^2) 그룹 카운팅 병목을 Counter(O(N))로 해결
            group_counts = Counter((safe_get(r, self.current_group_key) or _("folder_unknown")) for r in data)
            
            current_group = object()
            for row in data:
                g_val = safe_get(row, self.current_group_key)
                if not g_val: g_val = _("folder_unknown")
                
                if g_val != current_group:
                    count = group_counts[g_val]
                    display_data.append({"is_group": True, "name": g_val, "count": count})
                    current_group = g_val
                display_data.append(row)
        else:
            display_data = data
            
        print(f"[LOG] 5. 그룹화 배열 생성 완료: {time.time()-t0:.3f}s")

        final_data = []
        is_detail_view = (self.view_stack.currentIndex() == 0)
        show_dup = is_detail_view and self.btn_dup_check.isChecked()

        for row in display_data:
            final_data.append(row)
            if not row.get("is_group") and show_dup:
                fp = row.get("full_path")
                if hasattr(self, 'dup_matches') and fp in self.dup_matches:
                    sorted_b_folders = sorted(self.dup_matches[fp].items(), key=lambda x: max([m["ratio"] for m in x[1]]), reverse=True)
                    for b_folder, matched_files in sorted_b_folders:
                        matched_files.sort(key=lambda x: x["ratio"], reverse=True)
                        max_ratio = matched_files[0]["ratio"]
                        
                        final_data.append({
                            "is_dup_folder": True,
                            "path": b_folder,
                            "max_ratio": max_ratio
                        })
                        for m in matched_files:
                            final_data.append({
                                "is_dup_child": True,
                                "name": m["b_file"]["name"],
                                "size_str": self.format_size(m["b_file"]["size"]),
                                "ratio": m["ratio"],
                                "full_path": m["b_file"]["full_path"]
                            })

        print(f"[LOG] 6. 중복 파일 인젝션 완료: {time.time()-t0:.3f}s")

        self.file_data_map = {}
        idx_counter = 0
        for row in final_data:
            row["display_index"] = idx_counter
            if not row.get("is_group") and not row.get("is_dup_folder") and not row.get("is_dup_child"):
                self.file_data_map[row.get("full_path")] = row
            idx_counter += 1
            
        print(f"[LOG] 7. Map 재생성 완료: {time.time()-t0:.3f}s")
        
        self.table_view.setUpdatesEnabled(False)

        self.table_view.clearSpans()

        t_model = time.time()
        self.table_model.update_data(final_data)
        print(f"[LOG] 8. TableModel 내부 업데이트 (Qt 엔진 렌더링 계산): {time.time()-t_model:.3f}s")

        col_count = self.table_model.columnCount()

        span_targets = []
        for i, row in enumerate(final_data):
            if row.get("is_group") or row.get("is_dup_folder") or row.get("is_dup_child"):
                span_targets.append(i)

        print(f"[LOG] 9. 병합(Span) 타겟 추출 완료 ({len(span_targets)}건): {time.time()-t0:.3f}s")

        from PyQt6.QtCore import QTimer

        self._span_task_id = getattr(self, '_span_task_id', 0) + 1
        current_task_id = self._span_task_id

        def apply_spans_chunk(targets, chunk_size=200):
            if getattr(self, '_span_task_id', 0) != current_task_id:
                return

            if not hasattr(self, '_span_start_time'):
                self._span_start_time = time.time()

            if not targets:
                self.table_view.setUpdatesEnabled(True)
                # [추가] span 적용 완료 후 리스트 패널 활성화
                self.dim_overlay.hide()
                print(f"[LOG] 10. 모든 Span 비동기 적용 및 UI 렌더링 재개 완료: {time.time()-self._span_start_time:.3f}s")
                del self._span_start_time
                return
                
            chunk = targets[:chunk_size]
            next_targets = targets[chunk_size:]
            
            for i in chunk:
                self.table_view.setSpan(i, 0, 1, col_count)
                self.table_view.setRowHeight(i, 35)
                
            QTimer.singleShot(1, lambda: apply_spans_chunk(next_targets, chunk_size))

        apply_spans_chunk(span_targets)

    def format_size(self, size):
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0: return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"

    def on_scan_progress(self, count):
        self.lbl_tree_status.setText(_("folder_scanning").format(count))

    def on_scan_finished(self, file_data_cache, total_size):
        self.is_syncing = False
        self.sync_total_tasks = 0
        self.sync_completed_tasks = 0
        
        # 오프라인 방어 체크
        if not os.path.exists(self.current_watched_folder):
            if hasattr(self, 'main_status_label') and self.main_status_label:
                self.main_status_label.setText(_("folder_ready"))
            self.lbl_tree_status.setText("Network Drive Offline / 경로를 찾을 수 없습니다.")
            return

        self.file_data_cache = file_data_cache
        for row in self.file_data_cache:
            row["size"] = self.format_size(row["raw_size"])

        self.apply_grouping_and_sorting()

        folder_path = self.current_watched_folder
        if folder_path:
            self.lbl_tree_status.setText(_("folder_status_sel").format(os.path.basename(folder_path), len(self.file_data_cache), self.format_size(total_size)))
            
        self.scroll_timer.start(100)
        self.start_dup_match()
        
        if folder_path:
            self.lbl_tree_status.setText(_("folder_status_sel").format(os.path.basename(folder_path), len(self.file_data_cache), self.format_size(total_size)))
            
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
            
            # --- [추가됨] NAS 하이브리드 폴링 구동부 ---
            if not hasattr(self, 'nas_poll_timer'):
                self.nas_poll_timer = QTimer(self)
                self.nas_poll_timer.setInterval(10000) # 10초 주기
                self.nas_poll_timer.timeout.connect(self.check_nas_folder_mtime)
            
            try: self.last_folder_mtime = os.stat(folder_path).st_mtime
            except: self.last_folder_mtime = 0
            
            self.nas_poll_timer.start()
            # ------------------------------------------
        
        include_sub = self.btn_subfolders.isChecked()
        target_exts = ('.zip', '.cbz', '.cbr', '.rar', '.7z')
        
        self.is_force_syncing = False
        
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
        # --- [수정됨] 삭제 및 새로고침 시 UI 잔상(깨짐) 방지 ---
        self.table_view.setUpdatesEnabled(False)
        self.table_view.clearSpans()
        self.table_model.update_data([])
        self.table_view.setUpdatesEnabled(True)
        # --------------------------------------------------------
        self.lbl_tree_status.setText(_("folder_scan_prep"))
        self.is_syncing = False
        if hasattr(self, 'main_status_label') and self.main_status_label:
            self.main_status_label.setText(_("folder_ready"))
        self.progress_bar.hide()
        
        # --- [수정됨] force_update 플래그 전달 ---
        self.scan_thread = FolderScanThread(folder_path, include_sub, target_exts, self.thumb_dir, self.force_update_flag)
        self.scan_thread.progress_updated.connect(self.on_scan_progress)
        self.scan_thread.scan_finished.connect(self.on_scan_finished)
        self.scan_thread.start()

    def on_metadata_extracted(self, filepath, meta_dict, has_img_out):
        row = self.file_data_map.get(filepath)
        if not row: return

        if has_img_out:
            row["thumb_processed"] = True

        was_meta_already_processed = row.get("meta_processed", False)
        
        if not was_meta_already_processed:
            row["meta_processed"] = True 
            if meta_dict is None: meta_dict = {}
            row.update({
                "res": meta_dict.get("resolution", ""), "title": meta_dict.get("title", ""),
                "series": meta_dict.get("series", ""), "vol": meta_dict.get("volume", ""),
                "num": meta_dict.get("number", ""), "writer": meta_dict.get("writer", ""),
                "full_meta": meta_dict
            })
            
            try:
                creators_list = []
                writer = meta_dict.get("writer")
                if writer: creators_list.append(writer)
                for role in ['penciller', 'inker', 'colorist', 'letterer', 'cover_artist', 'editor']:
                    val = meta_dict.get(role)
                    if val: creators_list.append(val)
                creators_str = " / ".join(creators_list) if creators_list else ""
                
                y, m, d = meta_dict.get("year", ""), meta_dict.get("month", ""), meta_dict.get("day", "")
                publish_date_str = f"{y}-{m}-{d}".strip('-')
                if publish_date_str == "--": publish_date_str = ""
                
                db.upsert_file_info(
                    filepath, row.get("raw_mtime", 0), row.get("raw_size", 0), row.get("ext", ""),
                    meta_dict.get("resolution", ""), meta_dict.get("title", ""), meta_dict.get("series", ""),
                    meta_dict.get("series_group", ""), meta_dict.get("volume", ""), meta_dict.get("number", ""),
                    meta_dict.get("writer", ""), creators_str, meta_dict.get("publisher", ""), meta_dict.get("imprint", ""), 
                    meta_dict.get("genre", ""), meta_dict.get("volume_count", ""), meta_dict.get("page_count", ""), 
                    meta_dict.get("format", ""), meta_dict.get("manga", ""), meta_dict.get("language", ""),
                    meta_dict.get("rating", ""), meta_dict.get("age_rating", ""), publish_date_str, meta_dict.get("summary", ""), 
                    meta_dict.get("characters", ""), meta_dict.get("teams", ""), meta_dict.get("locations", ""), 
                    meta_dict.get("story_arc", ""), meta_dict.get("tags", ""), meta_dict.get("notes", ""), meta_dict.get("web", ""), ""
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
                self.lbl_tree_status.setText(_("folder_status_sel").format(os.path.basename(folder_path), len(self.file_data_cache), "0 B"))
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
            self.lbl_tree_status.setText(_("folder_status_file").format(full_path, size_str))
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
                        self.lbl_cover.setText(_("folder_no_cover"))
                else:
                    self.lbl_cover.setText(_("folder_no_cover"))
            else:
                self.lbl_cover.setText(_("folder_no_cover"))
        else:
            self.lbl_cover.setText(_("folder_no_cover"))

        title = meta_dict.get("title") or os.path.basename(full_path)
        series = meta_dict.get("series") or _("info_no_series")
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

        summary = meta_dict.get("summary") or _("info_no_summary")
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
                            <tr><td width="80" valign="top" style="color: #aaaaaa;">{_('col_creators')}</td><td valign="top" style="color: #ffffff;">{creators}</td></tr>
                            <tr><td valign="top" style="color: #aaaaaa;">{_('col_publisher')}</td><td valign="top" style="color: #ffffff;">{pub_full}</td></tr>
                            <tr><td valign="top" style="color: #aaaaaa;">{_('col_genre')}</td><td valign="top" style="color: #ffffff;">{genre}</td></tr>
                            <tr><td valign="top" style="color: #aaaaaa;">{_('col_page_count')}</td><td valign="top" style="color: #ffffff;">{page_count}</td></tr>
                            <tr><td valign="top" style="color: #aaaaaa;">{_('col_vol_count')}</td><td valign="top" style="color: #ffffff;">{volume_count}</td></tr>
                            <tr><td valign="top" style="color: #aaaaaa;">{_('col_format')}/{_('col_manga')}</td><td valign="top" style="color: #ffffff;">{format_val} / {manga}</td></tr>
                            <tr><td valign="top" style="color: #aaaaaa;">{_('col_rating')}</td><td valign="top" style="color: #ffffff;">{rating}</td></tr>
                            <tr><td valign="top" style="color: #aaaaaa;">{_('col_age_rating')}</td><td valign="top" style="color: #ffffff;">{age_rating}</td></tr>
                            <tr><td valign="top" style="color: #aaaaaa;">{_('col_pub_date')}</td><td valign="top" style="color: #ffffff;">{publish_date}</td></tr>
                        </table>
                    </td>
                    <td width="55%" valign="top">
                        <div style="color: #aaaaaa; margin-bottom: 4px;">{_('col_summary')}</div>
                        <div style="margin-bottom: 15px; color: #dddddd; line-height: 1.5;">{summary}</div>
                        
                        <div style="color: #aaaaaa; margin-bottom: 4px;">{_('info_arc_team_loc')}</div>
                        <div style="margin-bottom: 15px; color: #dddddd;">{story_arc} / {teams} / {locations}</div>
                        
                        <div style="color: #aaaaaa; margin-bottom: 4px;">{_('col_characters')}</div>
                        <div style="margin-bottom: 15px; color: #dddddd;">{characters}</div>
                        
                        <div style="color: #aaaaaa; margin-bottom: 4px;">{_('col_tags')}</div>
                        <div style="margin-bottom: 15px; color: #dddddd;">{tags}</div>
                        
                        <div style="color: #aaaaaa; margin-bottom: 4px;">{_('col_web')}</div>
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
            menu.addAction(_("action_fav_rem"), lambda: self.remove_from_favorites(path))
        else:
            menu.addAction(_("action_fav_add"), lambda: self.add_to_favorites(path))
            
        menu.addSeparator()
        menu.addAction(_("action_open_exp"), lambda: self.open_in_explorer(path))
        menu.addAction(_("action_ren_folder"), lambda: self.rename_folder(index))
        menu.addAction(_("action_del_folder"), self.delete_selected)
        menu.addAction(_("action_refresh"), self.refresh_tree)
        menu.exec(self.tree_view.viewport().mapToGlobal(position))

    def show_list_context_menu(self, position):
        view = self.get_active_view()
        if not view.selectionModel().hasSelection(): return
        
        if not self.get_selected_files(): return
        
        menu = QMenu()
        menu.addAction(_("action_view"), self.open_viewer)
        
        menu.addAction(_("action_flatten_structure") + " (F1)", self.send_to_tab1)
        menu.addAction(_("action_inner_ren") + " (F2)", self.send_to_tab2)
        menu.addAction(_("action_meta_edit") + " (F3)", self.send_to_tab3)
        
        menu.addAction(_("action_update_files"), self.force_update_selected_files)
        menu.addSeparator()
        menu.addAction(_("action_del_files"), self.delete_selected)
        menu.addAction(_("action_open_exp"), self.open_selected_in_explorer)
        menu.addSeparator()
        menu.addAction(_("action_sel_all"), self.select_all_files)
        menu.addAction(_("action_inv_sel"), self.invert_selection)
        menu.addAction(_("action_refresh"), self.refresh_list)
        menu.exec(view.viewport().mapToGlobal(position))

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
            QMessageBox.warning(self, _("dlg_warn"), _("dlg_warn_viewer"))
            return
        files = self.get_selected_files()
        if files: subprocess.Popen([viewer_path, files[0]])

    def open_in_explorer(self, path):
        if os.name == 'nt': os.startfile(path)
        else: subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', path])

    def open_selected_in_explorer(self):
        files = self.get_selected_files()
        if files: self.open_in_explorer(os.path.dirname(files[0]))

    def send_to_tab1(self):
        files = self.get_selected_files()
        if files and hasattr(self.main_window, 'tab1'):
            self.main_window.tabs.setCurrentWidget(self.main_window.tab1)
            self.main_window.process_paths(files)

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

    def check_nas_folder_mtime(self):
        if not self.current_watched_folder or not os.path.exists(self.current_watched_folder):
            return
        try:
            current_mtime = os.stat(self.current_watched_folder).st_mtime
            if current_mtime != getattr(self, 'last_folder_mtime', 0):
                self.last_folder_mtime = current_mtime
                self.refresh_list(force_update=False)
        except Exception:
            pass
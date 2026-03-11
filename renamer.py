import os
import sys
import zipfile
import subprocess
import threading
import shutil
import io
import json
import locale
import re
import concurrent.futures
from pathlib import Path

# PyQt6 라이브러리
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, 
    QCheckBox, QComboBox, QLineEdit, QFrame, QAbstractItemView, QMessageBox, QFileDialog,
    QDialog, QFormLayout, QDialogButtonBox, QProgressBar, QTextEdit, QSlider
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import QImage, QPixmap, QPainter, QPainterPath, QIcon, QColor

# 이미지 처리를 위한 PIL
from PIL import Image

CREATE_NO_WINDOW = 0x08000000

def get_config_path():
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, 'config.json')

CONFIG_FILE = get_config_path()

def get_system_language():
    try:
        lang_code, _ = locale.getdefaultlocale()
        if lang_code and lang_code.startswith('ko'):
            return 'ko'
    except: pass
    return 'en' 

def get_safe_thread_limits():
    total_cores = os.cpu_count() or 4
    safe_max = max(1, total_cores - 1) if total_cores <= 4 else max(1, total_cores - 2)
    default_threads = max(1, int(total_cores * 0.5))
    return total_cores, safe_max, default_threads

def load_config():
    sys_lang = get_system_language()
    total_cores, safe_max, default_threads = get_safe_thread_limits()
    
    default_config = {
        "lang": sys_lang, "target_format": "none", "backup_on": False,
        "flatten_folders": False, "webp_conversion": False,
        "webp_quality": 100, "max_threads": default_threads
    }
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                saved_config = json.load(f)
                default_config.update(saved_config)
                default_config["max_threads"] = min(default_config["max_threads"], safe_max)
                return default_config
    except: pass
    return default_config

def save_config(config_data):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=4)
    except: pass

def get_resource_path(filename):
    paths_to_check = []
    if getattr(sys, 'frozen', False):
        paths_to_check.append(os.path.join(os.path.dirname(sys.executable), filename))
        paths_to_check.append(os.path.join(sys._MEIPASS, filename))
    else:
        paths_to_check.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), filename))
    paths_to_check.append(os.path.join(os.path.abspath("."), filename))
    for p in paths_to_check:
        if os.path.exists(p): return p
    return filename

def natural_keys(text):
    parts = str(text).replace('\\', '/').split('/')
    result = []
    for part in parts:
        result.append([int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', part)])
    return result

class LogDialog(QDialog):
    def __init__(self, parent, stats, i18n):
        super().__init__(parent)
        self.setWindowTitle(i18n["log_title"])
        self.resize(500, 400)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        
        layout = QVBoxLayout(self)
        
        lbl_summary = QLabel(f"✅ Success: {len(stats['success'])}  |  ⏩ Skip: {len(stats['skip'])}  |  ❌ Error: {len(stats['error'])}")
        lbl_summary.setStyleSheet("font-weight: bold; font-size: 14px; margin-bottom: 10px;")
        layout.addWidget(lbl_summary)
        
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setStyleSheet("background-color: #1a1a1a; color: #e0e0e0; font-family: Consolas, monospace; padding: 10px;")
        
        log_content = ""
        if stats['error']:
            log_content += "❌ [ERRORS]\n" + "\n".join(stats['error']) + "\n\n"
        if stats['success']:
            log_content += "✅ [SUCCESS]\n" + "\n".join(stats['success']) + "\n\n"
        if stats['skip']:
            log_content += "⏩ [SKIPPED]\n" + "\n".join(stats['skip']) + "\n"
            
        self.text_edit.setText(log_content)
        layout.addWidget(self.text_edit)
        
        btn_close = QPushButton(i18n["btn_close"])
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

class SettingsDialog(QDialog):
    def __init__(self, parent, config, format_keys, i18n):
        super().__init__(parent)
        self.i18n = i18n[config["lang"]]
        self.setWindowTitle(self.i18n["settings_title"])
        self.setFixedSize(480, 640) 
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        form_layout = QFormLayout()
        form_layout.setSpacing(15)

        self.cb_lang = QComboBox()
        self.cb_lang.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cb_lang.addItems(["한국어", "English"])
        self.cb_lang.setCurrentText("한국어" if config["lang"] == "ko" else "English")
        form_layout.addRow(self.i18n["lang_lbl"], self.cb_lang)

        self.cb_format = QComboBox()
        self.cb_format.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cb_format.addItems(self.i18n["format_opts"])
        try:
            fmt_idx = format_keys.index(config["target_format"])
        except ValueError:
            fmt_idx = 0
        self.cb_format.setCurrentIndex(fmt_idx)
        form_layout.addRow(self.i18n["format_lbl"], self.cb_format)

        total_cores, safe_max, default_threads = get_safe_thread_limits()
        
        self.slider_threads = QSlider(Qt.Orientation.Horizontal)
        self.slider_threads.setRange(1, safe_max)
        self.slider_threads.setValue(config.get("max_threads", default_threads))
        self.slider_threads.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.lbl_threads_val = QLabel(f"{self.slider_threads.value()} 코어" if config["lang"]=="ko" else f"{self.slider_threads.value()} Cores")
        self.lbl_threads_val.setFixedWidth(60)
        
        th_layout = QHBoxLayout()
        th_layout.addWidget(self.slider_threads)
        th_layout.addWidget(self.lbl_threads_val)
        
        self.slider_threads.valueChanged.connect(lambda v: self.lbl_threads_val.setText(f"{v} 코어" if config["lang"]=="ko" else f"{v} Cores"))
        
        lbl_threads_desc = QLabel(self.i18n["threads_desc"])
        lbl_threads_desc.setWordWrap(True)
        lbl_threads_desc.setStyleSheet("color: #E74C3C; font-size: 11px; margin-top: 5px;")
        
        form_layout.addRow(self.i18n["max_threads"], th_layout)
        form_layout.addRow("", lbl_threads_desc)

        main_layout.addLayout(form_layout)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName("divider")
        main_layout.addWidget(line)

        opt_layout = QVBoxLayout()
        opt_layout.setSpacing(5)

        self.chk_backup = QCheckBox(self.i18n["backup"])
        self.chk_backup.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_backup.setChecked(config["backup_on"])
        opt_layout.addWidget(self.chk_backup)

        opt_layout.addSpacing(15)

        self.chk_flatten = QCheckBox(self.i18n["flatten"])
        self.chk_flatten.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_flatten.setChecked(config.get("flatten_folders", False))
        
        lbl_flatten_desc = QLabel(self.i18n["flatten_desc"])
        lbl_flatten_desc.setWordWrap(True)
        lbl_flatten_desc.setStyleSheet("color: #aaaaaa; font-size: 11px; margin-left: 25px;")
        opt_layout.addWidget(self.chk_flatten)
        opt_layout.addWidget(lbl_flatten_desc)

        opt_layout.addSpacing(15)

        self.chk_webp = QCheckBox(self.i18n["webp"])
        self.chk_webp.setCursor(Qt.CursorShape.PointingHandCursor)
        self.chk_webp.setChecked(config.get("webp_conversion", False))
        
        lbl_webp_desc = QLabel(self.i18n["webp_desc"])
        lbl_webp_desc.setWordWrap(True)
        lbl_webp_desc.setStyleSheet("color: #aaaaaa; font-size: 11px; margin-left: 25px;") 
        opt_layout.addWidget(self.chk_webp)
        opt_layout.addWidget(lbl_webp_desc)

        self.slider_quality = QSlider(Qt.Orientation.Horizontal)
        self.slider_quality.setRange(1, 100)
        self.slider_quality.setValue(config.get("webp_quality", 100))
        self.slider_quality.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self.lbl_quality_val = QLabel()
        self.lbl_quality_val.setFixedWidth(90)
        
        qual_layout = QHBoxLayout()
        qual_layout.setContentsMargins(25, 5, 0, 0)
        
        lbl_qual_title = QLabel(self.i18n["webp_quality"])
        qual_layout.addWidget(lbl_qual_title)
        qual_layout.addWidget(self.slider_quality)
        qual_layout.addWidget(self.lbl_quality_val)
        
        def update_qual_label(v):
            txt = f"{v}%"
            if v == 100: txt += " (Lossless)"
            self.lbl_quality_val.setText(txt)
            
        self.slider_quality.valueChanged.connect(update_qual_label)
        update_qual_label(self.slider_quality.value())

        self.chk_webp.toggled.connect(self.slider_quality.setEnabled)
        self.chk_webp.toggled.connect(self.lbl_quality_val.setEnabled)
        self.chk_webp.toggled.connect(lbl_qual_title.setEnabled)
        self.slider_quality.setEnabled(self.chk_webp.isChecked())
        self.lbl_quality_val.setEnabled(self.chk_webp.isChecked())
        lbl_qual_title.setEnabled(self.chk_webp.isChecked())

        opt_layout.addLayout(qual_layout)
        main_layout.addLayout(opt_layout)

        main_layout.addStretch()

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setText(self.i18n["btn_save"])
        btn_box.button(QDialogButtonBox.StandardButton.Cancel).setText(self.i18n["btn_cancel"])
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setCursor(Qt.CursorShape.PointingHandCursor)
        btn_box.button(QDialogButtonBox.StandardButton.Cancel).setCursor(Qt.CursorShape.PointingHandCursor)
        
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        main_layout.addWidget(btn_box)

    def get_data(self):
        return {
            "lang": "ko" if self.cb_lang.currentText() == "한국어" else "en",
            "target_format_idx": self.cb_format.currentIndex(), # UI 인덱스 반환
            "backup_on": self.chk_backup.isChecked(),
            "flatten_folders": self.chk_flatten.isChecked(),
            "webp_conversion": self.chk_webp.isChecked(),
            "webp_quality": self.slider_quality.value(),
            "max_threads": self.slider_threads.value()
        }

class ArchiveTableWidget(QTableWidget):
    delete_pressed = pyqtSignal()
    def __init__(self, rows, cols, parent=None):
        super().__init__(rows, cols, parent)
        self.placeholder_text = ""
    def setPlaceholderText(self, text):
        self.placeholder_text = text
        self.viewport().update()
    def paintEvent(self, event):
        super().paintEvent(event)
        if self.rowCount() == 0 and self.placeholder_text:
            painter = QPainter(self.viewport())
            painter.setPen(QColor("#888888"))
            font = painter.font()
            font.setFamily('맑은 고딕')
            font.setPointSize(13)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(self.viewport().rect(), Qt.AlignmentFlag.AlignCenter, self.placeholder_text)
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete:
            self.delete_pressed.emit()
        else:
            super().keyPressEvent(event)

class CellCheckBox(QWidget):
    toggled_signal = pyqtSignal(bool, str)
    def __init__(self, fp, checked):
        super().__init__()
        self.fp = fp
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.checkbox = QCheckBox()
        self.checkbox.setChecked(checked)
        self.checkbox.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.layout.addWidget(self.checkbox)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            new_state = not self.checkbox.isChecked()
            self.checkbox.setChecked(new_state)
            self.toggled_signal.emit(new_state, self.fp)
        super().mousePressEvent(event)

class DummyInfo:
    def __init__(self, name, size):
        self.original_name = name  
        self.filename = name.replace('\\', '/')  
        self.file_size = int(size) if str(size).isdigit() else 0
        self.is_dir = False

class RenameWorker(QThread):
    progress_signal = pyqtSignal(int, str) 
    finished_signal = pyqtSignal(dict, dict)

    def __init__(self, targets, config, archive_data, i18n_dict, pattern_val, custom_text, seven_z_exe):
        super().__init__()
        self.targets = targets
        self.backup_on = config.get("backup_on", False)
        self.flatten_folders = config.get("flatten_folders", False)
        self.webp_conversion = config.get("webp_conversion", False)
        self.target_format = config.get("target_format", "none")
        self.webp_quality = config.get("webp_quality", 100) 
        self.max_threads = config.get("max_threads", max(1, os.cpu_count() or 4)) 
        self.lang = config.get("lang", "ko")
        
        self.archive_data = archive_data
        self.i18n = i18n_dict
        self.pattern_val = pattern_val
        self.custom_text = custom_text
        self.seven_z_exe = seven_z_exe
        
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def generate_new_name(self, index, ext, total_count, stem_name):
        pad = 4 if total_count >= 1000 else 3
        t_patterns = self.i18n[self.lang]["patterns"]
        
        if self.webp_conversion:
            ext = ".webp" 

        if self.pattern_val == t_patterns[1]: 
            if index == 0: return f"Cover{ext}"
            else: return f"Page_{index:0{pad}d}{ext}"
        elif self.pattern_val == t_patterns[2]: 
            safe_stem = stem_name.replace(' ', '_')
            return f"{safe_stem}_{index:0{pad}d}{ext}"
        elif self.pattern_val == t_patterns[3]: 
            safe_stem = stem_name.replace(' ', '_')
            if index == 0: return f"{safe_stem}_Cover{ext}"
            else: return f"{safe_stem}_Page_{index:0{pad}d}{ext}"
        elif self.pattern_val == t_patterns[4]: 
            custom = self.custom_text.strip()
            if not custom: custom = "Custom"
            return f"{custom}_{index:0{pad}d}{ext}"
        else: 
            return f"{index:0{pad}d}{ext}"

    def _convert_single_image(self, temp_dir, old_n, new_n):
        if self._is_cancelled: return False
        
        old_path = os.path.join(temp_dir, old_n)
        new_path = os.path.join(temp_dir, new_n)
        
        if not os.path.exists(old_path): return False
        os.makedirs(os.path.dirname(new_path), exist_ok=True)
        
        is_already_webp = old_n.lower().endswith('.webp')
        
        if self.webp_conversion and not is_already_webp:
            try:
                with Image.open(old_path) as img:
                    if img.mode not in ('RGB', 'RGBA'):
                        img = img.convert('RGBA')
                    temp_save_path = new_path + ".tmp"
                    
                    if self.webp_quality == 100:
                        img.save(temp_save_path, 'WEBP', lossless=True, method=4)
                    else:
                        img.save(temp_save_path, 'WEBP', quality=self.webp_quality, method=4)
                
                os.remove(old_path)
                os.rename(temp_save_path, new_path)
            except Exception:
                old_ext = os.path.splitext(old_n)[1]
                fallback_n = os.path.splitext(new_path)[0] + old_ext
                os.rename(old_path, fallback_n) 
        else:
            os.rename(old_path, new_path)
        return True

    def run(self):
        stats = {'success': [], 'skip': [], 'error': []} 
        total = len(self.targets)
        new_archive_data = {} 
        
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        for idx, file_path in enumerate(self.targets):
            if self._is_cancelled:
                stats['skip'].append(f"{os.path.basename(file_path)} (Cancelled)")
                break

            filename = os.path.basename(file_path)
            msg = f"[{idx+1}/{total}] 처리 중: {filename}" if self.lang == "ko" else f"[{idx+1}/{total}] Processing: {filename}"
            self.progress_signal.emit(int((idx / total) * 100), msg)

            try:
                if self.backup_on:
                    bak_dir = os.path.join(os.path.dirname(file_path), 'bak')
                    os.makedirs(bak_dir, exist_ok=True)
                    shutil.copy2(file_path, os.path.join(bak_dir, filename))

                data = self.archive_data[file_path]
                entries = data['entries'].copy() 
                ext_type = data['ext'].lower()
                
                if self.target_format == 'none':
                    target_ext = ext_type
                    archive_type = '-t7z' if ext_type == '.7z' else '-tzip'
                else:
                    target_ext = f".{self.target_format}"
                    archive_type = '-t7z' if self.target_format == '7z' else '-tzip'

                cover_entry = next((e for e in entries if os.path.basename(e.filename).lower().startswith('cover')), None)
                if cover_entry:
                    entries.remove(cover_entry)
                    entries.insert(0, cover_entry)

                rename_args = []
                total_count = len(entries)
                stem_name = Path(file_path).stem

                has_non_webp = any(not e.original_name.lower().endswith('.webp') for e in entries)
                actual_webp_needed = self.webp_conversion and has_non_webp

                for count, entry in enumerate(entries):
                    old_name = entry.original_name
                    dir_name = os.path.dirname(entry.filename)
                    ext = os.path.splitext(entry.filename)[1]
                    if not ext: ext = ".jpg" 
                    
                    if self.webp_conversion:
                        ext = ".webp"
                    
                    new_basename = self.generate_new_name(count, ext, total_count, stem_name)
                    
                    if self.flatten_folders:
                        new_name = new_basename
                    else:
                        new_name = os.path.join(dir_name, new_basename).replace('\\', '/') if dir_name else new_basename

                    if old_name != new_name or actual_webp_needed:
                        rename_args.append((old_name, new_name))

                format_changed = (target_ext != ext_type)
                needs_rename = len(rename_args) > 0
                
                must_extract = actual_webp_needed or format_changed or self.flatten_folders or (ext_type not in ['.zip', '.cbz'])

                if not needs_rename and not must_extract:
                    stats['skip'].append(filename)
                    new_archive_data[file_path] = file_path 
                    continue

                if not must_extract:
                    flat_args = []
                    for old_n, new_n in rename_args:
                        flat_args.extend([old_n, new_n])
                        
                    for i in range(0, len(flat_args), 80):
                        if self._is_cancelled: break
                        chunk = flat_args[i:i + 80]
                        cmd = [self.seven_z_exe, 'rn', str(file_path)] + chunk
                        subprocess.run(cmd, startupinfo=startupinfo, creationflags=CREATE_NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                    
                    if not self._is_cancelled:
                        stats['success'].append(filename)
                        new_archive_data[file_path] = file_path
                else: 
                    temp_dir = os.path.join(os.path.dirname(file_path), f".tmp_{filename}")
                    if os.path.exists(temp_dir): shutil.rmtree(temp_dir, ignore_errors=True)
                    os.makedirs(temp_dir, exist_ok=True)
                    
                    cmd_ext = [self.seven_z_exe, 'x', str(file_path), f'-o{temp_dir}', '-y']
                    subprocess.run(cmd_ext, startupinfo=startupinfo, creationflags=CREATE_NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                    
                    if rename_args:
                        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_threads) as executor:
                            futures = []
                            for old_n, new_n in rename_args:
                                futures.append(executor.submit(self._convert_single_image, temp_dir, old_n, new_n))
                            
                            for i, future in enumerate(concurrent.futures.as_completed(futures)):
                                if self._is_cancelled: break 
                                
                                if i % max(1, len(rename_args) // 20) == 0:
                                    sub_prog = int((idx / total) * 100) + int((i / len(rename_args)) * (100 / total))
                                    prog_msg = f"Converting ({self.max_threads} Threads): {filename} ({i}/{len(rename_args)})" if self.lang == "en" else f"다중 코어 변환 중 ({self.max_threads} 스레드): {filename} ({i}/{len(rename_args)})"
                                    self.progress_signal.emit(sub_prog, prog_msg)

                    if self._is_cancelled:
                        shutil.rmtree(temp_dir, ignore_errors=True)
                        break

                    if self.flatten_folders:
                        for dirpath, dirnames, filenames in os.walk(temp_dir, topdown=False):
                            for d in dirnames:
                                dp = os.path.join(dirpath, d)
                                try:
                                    if not os.listdir(dp):
                                        os.rmdir(dp)
                                except: pass

                    self.progress_signal.emit(int(((idx + 0.9) / total) * 100), f"Re-archiving: {filename}")
                            
                    target_final_path = str(Path(file_path).with_suffix(target_ext))
                    temp_archive = os.path.join(os.path.dirname(file_path), f".tmp_archive_{filename}{target_ext}")
                    
                    if os.path.exists(temp_archive):
                        os.remove(temp_archive)
                        
                    cmd_zip = [self.seven_z_exe, 'a', archive_type, temp_archive, os.path.join(temp_dir, '*'), '-mx=0']
                    subprocess.run(cmd_zip, startupinfo=startupinfo, creationflags=CREATE_NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                    
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    
                    if os.path.normcase(os.path.abspath(file_path)) == os.path.normcase(os.path.abspath(target_final_path)):
                        os.remove(file_path)
                    else:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                        if os.path.exists(target_final_path):
                            os.remove(target_final_path)
                            
                    os.rename(temp_archive, target_final_path)
                            
                    stats['success'].append(filename)
                    new_archive_data[file_path] = target_final_path 
            except Exception as e:
                stats['error'].append(f"{filename} - {str(e)}")

        if self._is_cancelled:
            self.progress_signal.emit(0, "Cancelled" if self.lang == "en" else "작업 중단됨")
        else:
            self.progress_signal.emit(100, "Done!" if self.lang == "en" else "작업 완료!")
            
        self.finished_signal.emit(stats, new_archive_data)

class RenamerApp(QMainWindow):
    image_loaded_signal = pyqtSignal(object, object) 

    def __init__(self):
        super().__init__()
        self.image_loaded_signal.connect(self.render_image)

        self.config = load_config()
        self.lang = self.config["lang"]
        
        window_width = self.config.get("width", 1150)
        window_height = self.config.get("height", 800)
        is_maximized = self.config.get("is_maximized", False)
        
        self.all_checked = True
        self.format_keys = ["none", "zip", "cbz", "cbr", "7z"]
        
        total_c, safe_c, _ = get_safe_thread_limits()
        
        self.i18n = {
            "ko": {
                "title": "ComicZIP Optimizer v1.5.1",
                "cover_preview": "📚 표지 미리보기",
                "inner_preview": "🖼️ 내부 파일 미리보기",
                "add_folder": "📂 폴더 추가",
                "add_file": "📄 파일 추가",
                "remove_sel": "🗑️ 선택 삭제",
                "clear_all": "🧹 전체 비우기",
                "settings_btn": "⚙️ 환경 설정",
                "settings_title": "환경 설정",
                "lang_lbl": "🌐 언어 (Language) :",
                "format_lbl": "📦 변환 포맷 :",
                "backup": "원본 백업 (bak 폴더 생성)",
                "flatten": "폴더 구조 평탄화 (하위 폴더 제거)",
                "flatten_desc": "압축 파일 내의 폴더를 모두 무시하고 이미지를 최상단으로 꺼냅니다.\n(경로 인식형 자연 정렬로 이름 꼬임 방지됨)",
                "webp": "모든 이미지를 WebP로 일괄 변환",
                "webp_desc": "모든 이미지를 고효율 WebP 포맷으로 변환하여 확장자 통일성을 보장합니다.",
                "webp_quality": "WebP 품질 (Quality) :",
                "max_threads": "다중 스레드 (Threads) :",
                "threads_desc": f"⚠️ 수치가 높을수록 변환 속도가 빨라지지만 PC가 느려질 수 있습니다.\n시스템 안정을 위해 전체 {total_c}코어 중 여유분을 남긴 안전 수치({safe_c}코어)까지만 올릴 수 있습니다.",
                "btn_save": "저장",
                "btn_cancel": "취소",
                "btn_close": "닫기",
                "log_title": "상세 작업 결과 로그",
                "pattern_lbl": "💡 파일명 패턴 :",
                "target_lbl": " 대상 압축파일 (ZIP, CBZ, CBR, 7Z 지원) ",
                "inner_lbl": " 내부 파일 리스트 (패턴 실시간 미리보기) ",
                "col_name": "파일명 (선택 포맷 자동 변환)", "col_count": "이미지 수", "col_size": "용량 (MB)",
                "col_old": "원본 파일명", "col_new": "변경될 파일명", "col_fsize": "크기",
                "drag_drop": "📂 폴더나 파일을 여기로 드래그 앤 드롭하세요",
                "run_btn": "🚀 최적화 실행",
                "cancel_btn": "🛑 작업 중단",
                "cancel_wait": "⏳ 중단 처리 중...",
                "status_wait": "대기 중...",
                "no_preview": "미리보기 없음",
                "no_image": "미리볼 수 없는 이미지입니다.",
                "total_files": "총 {count}개 파일",
                "format_opts": ["변경없음", "zip", "cbz", "cbr", "7z"],
                "patterns": [
                    "기본 숫자 패딩 (000, 001...)", "영문 도서 스타일 (Cover, Page_001...)",
                    "압축파일명 동기화 (파일명_000...)", "압축파일명 + 도서 (파일명_Cover...) - 추천", "사용자 정의 (직접입력_000...)"
                ]
            },
            "en": {
                "title": "ComicZIP Optimizer v1.5.1",
                "cover_preview": "📚 Cover Preview",
                "inner_preview": "🖼️ Inner Preview",
                "add_folder": "📂 Add Folder",
                "add_file": "📄 Add File",
                "remove_sel": "🗑️ Remove Sel",
                "clear_all": "🧹 Clear All",
                "settings_btn": "⚙️ Settings",
                "settings_title": "Preferences",
                "lang_lbl": "🌐 Language :",
                "format_lbl": "📦 Output Format :",
                "backup": "Backup Original (bak folder)",
                "flatten": "Flatten Folders (Remove Sub-folders)",
                "flatten_desc": "Extracts all images to the root, ignoring folders.\n(Conflicts resolved using smart natural sort).",
                "webp": "Convert all images to WebP",
                "webp_desc": "Converts all images strictly to WebP format.",
                "webp_quality": "WebP Quality :",
                "max_threads": "Multi-threads :",
                "threads_desc": f"⚠️ Higher values increase speed but consume more CPU.\nFor system stability, the maximum is capped at {safe_c} cores (Total: {total_c}).",
                "btn_save": "Save",
                "btn_cancel": "Cancel",
                "btn_close": "Close",
                "log_title": "Detailed Job Log",
                "pattern_lbl": "💡 Naming Pattern :",
                "target_lbl": " Target Archives (ZIP, CBZ, CBR, 7Z) ",
                "inner_lbl": " Inner Files (Real-time Preview) ",
                "col_name": "File Name (Auto-converts to target)", "col_count": "Images", "col_size": "Size (MB)",
                "col_old": "Original Name", "col_new": "New Name", "col_fsize": "Size",
                "drag_drop": "📂 Drag and drop folders or files here",
                "run_btn": "🚀 Execute Optimizer",
                "cancel_btn": "🛑 Cancel Process",
                "cancel_wait": "⏳ Cancelling...",
                "status_wait": "Waiting...",
                "no_preview": "No Preview",
                "no_image": "Cannot preview this image.",
                "total_files": "Total {count} files",
                "format_opts": ["No Change", "zip", "cbz", "cbr", "7z"],
                "patterns": [
                    "Basic Number Padding (000, 001...)", "English Book Style (Cover, Page_001...)",
                    "Sync with Archive Name (File_000...)", "Archive + Book (File_Cover...) - Recommended", "Custom (Input_000...)"
                ]
            }
        }
        
        self.setWindowTitle(self.i18n[self.lang]["title"])
        self.setMinimumSize(1050, 750) 
        
        self.resize(window_width, window_height)
        if is_maximized:
            self.showMaximized()

        self.setAcceptDrops(True) 
        
        icon_path = get_resource_path('app.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
            
        self.archive_data = {} 
        self.current_archive_path = None
        self.seven_zip_path = get_resource_path('7za.exe')

        self.archive_timer = QTimer()
        self.archive_timer.setSingleShot(True)
        self.archive_timer.timeout.connect(self._process_archive_select)

        self.inner_timer = QTimer()
        self.inner_timer.setSingleShot(True)
        self.inner_timer.timeout.connect(self._process_inner_select)

        self.setup_ui()
        self.apply_language()
        self.apply_dark_theme()

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(25, 25, 25, 25)
        main_layout.setSpacing(20)

        left_frame = QFrame()
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(15, 15, 15, 15)
        left_frame.setFixedWidth(300) 
        left_frame.setObjectName("panelFrame")

        self.lbl_cover_title = QLabel()
        self.lbl_cover_title.setObjectName("titleLabel")
        self.lbl_cover_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.lbl_cover_img = QLabel()
        self.lbl_cover_img.setObjectName("imageLabel")
        self.lbl_cover_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_cover_img.setFixedSize(260, 300) 

        self.lbl_inner_title = QLabel()
        self.lbl_inner_title.setObjectName("titleLabel")
        self.lbl_inner_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.lbl_inner_img = QLabel()
        self.lbl_inner_img.setObjectName("imageLabel")
        self.lbl_inner_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_inner_img.setFixedSize(260, 300) 

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setObjectName("divider")

        left_layout.addWidget(self.lbl_cover_title)
        left_layout.addWidget(self.lbl_cover_img, alignment=Qt.AlignmentFlag.AlignCenter)
        left_layout.addSpacing(10)
        left_layout.addWidget(divider)
        left_layout.addSpacing(10)
        left_layout.addWidget(self.lbl_inner_title)
        left_layout.addWidget(self.lbl_inner_img, alignment=Qt.AlignmentFlag.AlignCenter)
        left_layout.addStretch()

        main_layout.addWidget(left_frame)

        right_frame = QFrame()
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        toolbar_layout = QHBoxLayout()
        self.btn_add_folder = QPushButton()
        self.btn_add_folder.setCursor(Qt.CursorShape.PointingHandCursor) 
        self.btn_add_folder.clicked.connect(self.add_folder)
        
        self.btn_add_file = QPushButton()
        self.btn_add_file.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add_file.clicked.connect(self.add_file)
        
        self.btn_remove_sel = QPushButton()
        self.btn_remove_sel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_remove_sel.setObjectName("dangerBtn")
        self.btn_remove_sel.clicked.connect(self.remove_selected)
        
        self.btn_clear_all = QPushButton()
        self.btn_clear_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_all.setObjectName("dangerBtn")
        self.btn_clear_all.clicked.connect(self.clear_list)

        toolbar_layout.addWidget(self.btn_add_folder)
        toolbar_layout.addWidget(self.btn_add_file)
        toolbar_layout.addWidget(self.btn_remove_sel)
        toolbar_layout.addWidget(self.btn_clear_all)
        toolbar_layout.addStretch()

        self.btn_settings = QPushButton()
        self.btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_settings.setObjectName("settingsBtn")
        self.btn_settings.clicked.connect(self.open_settings)
        toolbar_layout.addWidget(self.btn_settings)

        right_layout.addLayout(toolbar_layout)

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
        
        options_layout.addWidget(self.lbl_pattern)
        options_layout.addWidget(self.cb_pattern, 1)
        options_layout.addWidget(self.entry_custom)
        right_layout.addWidget(options_frame)

        self.lbl_target = QLabel()
        self.lbl_target.setObjectName("boldLabel")
        right_layout.addWidget(self.lbl_target)

        self.table_archives = ArchiveTableWidget(0, 4)
        self.table_archives.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_archives.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_archives.verticalHeader().setVisible(False) 
        self.table_archives.delete_pressed.connect(self.remove_selected)
        
        header_arch = self.table_archives.horizontalHeader()
        header_arch.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table_archives.setColumnWidth(0, 45) 
        header_arch.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header_arch.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table_archives.setColumnWidth(2, 90)
        header_arch.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table_archives.setColumnWidth(3, 90)
        
        self.table_archives.setMinimumHeight(150)
        self.table_archives.itemSelectionChanged.connect(self.on_archive_select)
        
        self.header_cb = QCheckBox(self.table_archives.horizontalHeader())
        self.header_cb.setFixedSize(24, 24)
        self.header_cb.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header_cb.setStyleSheet("background: transparent; margin: 0px; padding: 0px;")
        self.header_cb.clicked.connect(self.on_header_checkbox_toggled)
        
        def update_cb_pos(*args):
            x = header_arch.sectionPosition(0) + (header_arch.sectionSize(0) - 24) // 2
            y = (header_arch.height() - 24) // 2
            self.header_cb.move(x, y)
            
        header_arch.sectionResized.connect(update_cb_pos)
        header_arch.geometriesChanged.connect(update_cb_pos)
        QTimer.singleShot(0, update_cb_pos) 
        
        right_layout.addWidget(self.table_archives, 1) 

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

        bottom_layout = QHBoxLayout()
        self.lbl_status = QLabel()
        self.lbl_status.setObjectName("statusLabel")
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(10)
        self.progress_bar.hide() 

        status_v_layout = QVBoxLayout()
        status_v_layout.addWidget(self.lbl_status)
        status_v_layout.addWidget(self.progress_bar)

        self.btn_run = QPushButton()
        self.btn_run.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_run.setObjectName("actionBtn")
        self.btn_run.setFixedHeight(45)
        self.btn_run.clicked.connect(self.start_process)

        bottom_layout.addLayout(status_v_layout)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.btn_run)
        right_layout.addLayout(bottom_layout)

        main_layout.addWidget(right_frame, 1)

        self.render_image(self.lbl_cover_img, None)
        self.render_image(self.lbl_inner_img, None)

    def apply_dark_theme(self):
        style = """
        QMainWindow, QDialog { background-color: #1e1e1e; }
        QFrame#panelFrame { background-color: #2b2b2b; border-radius: 10px; }
        QFrame#optionsFrame { background-color: #2b2b2b; border-radius: 8px; }
        QFrame#divider { background-color: #444444; }
        QLabel { color: #ffffff; font-family: '맑은 고딕', 'Segoe UI Emoji'; }
        QLabel#titleLabel { font-size: 14px; font-weight: bold; margin-bottom: 5px; }
        QLabel#boldLabel { font-size: 12px; font-weight: bold; margin-top: 5px; }
        QLabel#langLabel { font-size: 12px; font-weight: bold; }
        QLabel#statusLabel { color: #3498DB; font-weight: bold; font-size: 12px; }
        QLabel#infoLabel { color: #aaaaaa; font-size: 11px; }
        QLabel#imageLabel { background-color: #1a1a1a; border-radius: 8px; }
        
        QProgressBar { background-color: #3a3a3a; border: none; border-radius: 5px; }
        QProgressBar::chunk { background-color: #3498DB; border-radius: 5px; }
        
        QPushButton { background-color: #3a3a3a; color: white; border-radius: 6px; padding: 8px 12px; font-family: '맑은 고딕', 'Segoe UI Emoji'; font-weight: bold; }
        QPushButton:hover { background-color: #4a4a4a; }
        QPushButton#settingsBtn { background-color: #2b2b2b; border: 1px solid #555; }
        QPushButton#settingsBtn:hover { background-color: #3a3a3a; }
        QPushButton#dangerBtn { background-color: #D32F2F; color: #FFFFFF; }
        QPushButton#dangerBtn:hover { background-color: #B71C1C; }
        
        QPushButton#actionBtn { background-color: #0078D7; font-size: 14px; padding: 10px 20px; }
        QPushButton#actionBtn:hover { background-color: #005A9E; }
        QPushButton#actionBtnCancel { background-color: #E74C3C; font-size: 14px; padding: 10px 20px; }
        QPushButton#actionBtnCancel:hover { background-color: #C0392B; }
        
        QPushButton:disabled { background-color: #555555; color: #888888; }
        
        QTableWidget { background-color: #2b2b2b; color: white; border: 1px solid #444; border-radius: 8px; gridline-color: #3a3a3a; }
        QHeaderView::section { background-color: #1f1f1f; color: white; padding: 5px; border: none; font-weight: bold; }
        QTableWidget::item:selected { background-color: #3a7ebf; }
        
        QSlider::groove:horizontal { border-radius: 4px; height: 8px; background: #3a3a3a; }
        QSlider::handle:horizontal { background: #3498DB; width: 16px; height: 16px; margin: -4px 0; border-radius: 8px; }
        QSlider::handle:horizontal:hover { background: #5DADE2; }
        
        QCheckBox { color: white; }
        QComboBox, QLineEdit { background-color: #3a3a3a; color: white; border: 1px solid #555; border-radius: 4px; padding: 4px; }
        """
        self.setStyleSheet(style)

    # 🌟 UI 요소를 일괄 잠금/해제 하는 헬퍼 함수
    def toggle_ui_elements(self, is_processing):
        enabled = not is_processing
        
        self.btn_add_folder.setEnabled(enabled)
        self.btn_add_file.setEnabled(enabled)
        self.btn_remove_sel.setEnabled(enabled)
        self.btn_clear_all.setEnabled(enabled)
        self.btn_settings.setEnabled(enabled)
        self.cb_pattern.setEnabled(enabled)
        self.table_archives.setEnabled(enabled)
        self.table_inner.setEnabled(enabled)
        self.header_cb.setEnabled(enabled)
        self.setAcceptDrops(enabled) # 드래그 앤 드롭 잠금 적용

        if is_processing:
            self.entry_custom.setEnabled(False)
        else:
            self.on_pattern_change(self.cb_pattern.currentText())

    def open_settings(self):
        dlg = SettingsDialog(self, self.config, self.format_keys, self.i18n)
        dlg.setStyleSheet(self.styleSheet()) 
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_data = dlg.get_data()
            
            # 🌟 [버그 수정 완료]: config 저장을 위한 올바른 키 매핑
            self.config["lang"] = new_data["lang"]
            self.config["target_format"] = self.format_keys[new_data["target_format_idx"]]
            self.config["backup_on"] = new_data["backup_on"]
            self.config["flatten_folders"] = new_data["flatten_folders"]
            self.config["webp_conversion"] = new_data["webp_conversion"]
            self.config["webp_quality"] = new_data["webp_quality"]
            self.config["max_threads"] = new_data["max_threads"]
            
            self.lang = self.config["lang"]
            save_config(self.config)

            self.apply_language()
            self.update_inner_preview_list() 
            self.refresh_archive_list()

    def apply_language(self):
        t = self.i18n[self.lang]
        self.setWindowTitle(t["title"])
        self.lbl_cover_title.setText(t["cover_preview"])
        self.lbl_inner_title.setText(t["inner_preview"])
        self.btn_add_folder.setText(t["add_folder"])
        self.btn_add_file.setText(t["add_file"])
        self.btn_remove_sel.setText(t["remove_sel"])
        self.btn_clear_all.setText(t["clear_all"])
        self.btn_settings.setText(t["settings_btn"]) 
        self.lbl_pattern.setText(t["pattern_lbl"])
        
        self.cb_pattern.blockSignals(True)
        self.cb_pattern.clear()
        self.cb_pattern.addItems(t["patterns"])
        self.cb_pattern.blockSignals(False)
        self.cb_pattern.setCurrentIndex(0)
        
        self.lbl_target.setText(t["target_lbl"])
        self.lbl_inner.setText(t["inner_lbl"])
        
        self.table_archives.setPlaceholderText(t["drag_drop"])
        self.table_archives.setHorizontalHeaderLabels(["", t["col_name"], t["col_count"], t["col_size"]])
        self.table_inner.setHorizontalHeaderLabels([t["col_old"], t["col_new"], t["col_fsize"]])
        
        if self.btn_run.objectName() == "actionBtn":
            self.btn_run.setText(t["run_btn"])
        else:
            self.btn_run.setText(t["cancel_btn"])
        
        if not self.lbl_status.text() or self.lbl_status.text() in [self.i18n["ko"]["status_wait"], self.i18n["en"]["status_wait"]]:
            self.lbl_status.setText(t["status_wait"])
            
        self.refresh_archive_list()
        
        if not self.current_archive_path:
            self.render_image(self.lbl_cover_img, None)
            self.render_image(self.lbl_inner_img, None)

    def on_pattern_change(self, value):
        t = self.i18n[self.lang]["patterns"]
        if value == t[4]: 
            self.entry_custom.setEnabled(True)
            self.entry_custom.setFocus()
        else:
            self.entry_custom.setEnabled(False)
        self.update_inner_preview_list()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls(): 
            event.acceptProposedAction()
        else: 
            event.ignore()

    def dropEvent(self, event):
        event.acceptProposedAction()
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        QTimer.singleShot(0, lambda: self.process_paths(files))

    def add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Directory")
        if folder: self.process_paths([folder])

    def add_file(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select Archives", "", "Archive files (*.zip *.cbz *.cbr *.7z)")
        if files: self.process_paths(files)

    def process_paths(self, paths):
        exts = {'.zip', '.cbz', '.cbr', '.7z'}
        added = False
        nested_files = [] 
        unsupported_files = []

        for p in paths:
            path_obj = Path(p)
            if path_obj.is_file():
                if path_obj.suffix.lower() in exts:
                    if str(p) not in self.archive_data:
                        res = self.load_archive_info(str(p), batch_mode=True)
                        if res == True: added = True
                        elif res == "nested": nested_files.append(path_obj.name)
                else:
                    unsupported_files.append(path_obj.name)
            elif path_obj.is_dir():
                for sub in path_obj.rglob('*'):
                    if sub.is_file() and sub.suffix.lower() in exts:
                        if 'bak' not in sub.parts and str(sub) not in self.archive_data:
                            res = self.load_archive_info(str(sub), batch_mode=True)
                            if res == True: added = True
                            elif res == "nested": nested_files.append(sub.name)
            
            QApplication.processEvents()
        
        self.refresh_archive_list()
        self.update_header_checkbox_state()

        if added and self.table_archives.rowCount() > 0:
            self.table_archives.selectRow(self.table_archives.rowCount()-1)
            
        if unsupported_files:
            if self.lang == "ko":
                msg = "다음 파일은 지원하지 않는 형식이므로 제외되었습니다:\n" + "\n".join(unsupported_files[:5])
                if len(unsupported_files) > 5: msg += f"\n...외 {len(unsupported_files)-5}개"
            else:
                msg = "Unsupported file formats skipped:\n" + "\n".join(unsupported_files[:5])
                if len(unsupported_files) > 5: msg += f"\n...and {len(unsupported_files)-5} more"
            QMessageBox.warning(self, "Warning", msg)
            
        if nested_files:
            if self.lang == "ko":
                msg = "다음 파일은 내부에 압축파일이 포함되어 제외되었습니다:\n" + "\n".join(nested_files[:5])
                if len(nested_files) > 5: msg += f"\n...외 {len(nested_files)-5}개"
            else:
                msg = "Skipped due to nested archives:\n" + "\n".join(nested_files[:5])
                if len(nested_files) > 5: msg += f"\n...and {len(nested_files)-5} more"
            QMessageBox.warning(self, "Warning", msg)

    def get_7z_entries(self, filepath):
        cmd = [self.seven_zip_path, 'l', '-slt', '-ba', str(filepath)]
        result = subprocess.run(cmd, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW, encoding='utf-8', errors='ignore')
        entries = []
        current_entry = {}
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                if current_entry and 'Path' in current_entry and not current_entry.get('Attributes', '').startswith('D'):
                    entries.append(DummyInfo(current_entry['Path'], current_entry.get('Size', '0')))
                current_entry = {}
            elif '=' in line:
                k, v = line.split('=', 1)
                current_entry[k.strip()] = v.strip()
        if current_entry and 'Path' in current_entry and not current_entry.get('Attributes', '').startswith('D'):
            entries.append(DummyInfo(current_entry['Path'], current_entry.get('Size', '0')))
        return entries

    def load_archive_info(self, filepath, batch_mode=False):
        try:
            size_mb = os.path.getsize(filepath) / (1024 * 1024)
            ext = Path(filepath).suffix.lower()
            if ext in ['.zip', '.cbz']:
                with zipfile.ZipFile(filepath, 'r') as zf:
                    entries = sorted([DummyInfo(info.filename, info.file_size) for info in zf.infolist() if not info.is_dir()], key=lambda x: natural_keys(x.filename))
            else:
                if not os.path.exists(self.seven_zip_path): return False
                entries = sorted(self.get_7z_entries(filepath), key=lambda x: natural_keys(x.filename))

            image_exts = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'}
            img_entries = [e for e in entries if Path(e.filename).suffix.lower() in image_exts]
            
            if not img_entries:
                return False 

            nested_exts = {'.zip', '.cbz', '.cbr', '.7z', '.rar', '.alz', '.egg'}
            if any(Path(e.filename).suffix.lower() in nested_exts for e in entries):
                if not batch_mode:
                    msg = f"[{os.path.basename(filepath)}]\n내부에 압축 파일이 포함되어 제외됩니다." if self.lang == "ko" else f"[{os.path.basename(filepath)}]\nContains nested archives. Skipped."
                    QMessageBox.warning(self, "Warning", msg)
                return "nested"

            self.archive_data[filepath] = {
                'checked': True,
                'entries': img_entries, 'size_mb': size_mb, 'name': os.path.basename(filepath), 'ext': ext
            }
            return True
        except: return False

    def force_reload_archive(self, filepath):
        if filepath in self.archive_data: del self.archive_data[filepath]
        self.load_archive_info(filepath)

    def on_individual_checkbox_toggled(self, state, fp):
        if fp in self.archive_data:
            self.archive_data[fp]['checked'] = state
        self.update_header_checkbox_state()

    def on_header_checkbox_toggled(self, checked):
        self.all_checked = checked
        for fp in self.archive_data:
            self.archive_data[fp]['checked'] = self.all_checked
        
        for row in range(self.table_archives.rowCount()):
            widget = self.table_archives.cellWidget(row, 0)
            if isinstance(widget, CellCheckBox):
                widget.checkbox.setChecked(self.all_checked)

    def update_header_checkbox_state(self):
        if not self.archive_data:
            self.all_checked = False
        else:
            self.all_checked = all(data['checked'] for data in self.archive_data.values())
        
        self.header_cb.blockSignals(True)
        self.header_cb.setChecked(self.all_checked)
        self.header_cb.blockSignals(False)

    def refresh_archive_list(self):
        self.table_archives.blockSignals(True)
        self.table_archives.setRowCount(0)
        row = 0
        
        fmt_key = self.config.get("target_format", "none")
        webp_on = self.config.get("webp_conversion", False)
        
        for fp, data in self.archive_data.items():
            self.table_archives.insertRow(row)
            
            chk_widget = CellCheckBox(fp, data['checked'])
            chk_widget.toggled_signal.connect(self.on_individual_checkbox_toggled)
            self.table_archives.setCellWidget(row, 0, chk_widget)
            
            hidden_item = QTableWidgetItem()
            hidden_item.setData(Qt.ItemDataRole.UserRole, fp) 
            self.table_archives.setItem(row, 0, hidden_item)
            
            name = data['name']
            ext = data['ext'].lower().replace('.', '')
            
            # 🌟 선택 포맷과 WebP 뱃지를 동적으로 결합하여 직관적인 피드백 제공
            badges = []
            if fmt_key != "none" and ext != fmt_key:
                badges.append(fmt_key.upper())
            if webp_on:
                badges.append("WEBP")
                
            if badges:
                badge_str = "+".join(badges)
                addon = f" 🔄 ({badge_str} 변환)" if self.lang == "ko" else f" 🔄 ({badge_str} conv)"
                name += addon
                
            name_item = QTableWidgetItem(name)
            count_item = QTableWidgetItem(str(len(data['entries'])))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            size_item = QTableWidgetItem(f"{data['size_mb']:.1f}")
            size_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            
            self.table_archives.setItem(row, 1, name_item)
            self.table_archives.setItem(row, 2, count_item)
            self.table_archives.setItem(row, 3, size_item)
            row += 1
            
        self.table_archives.blockSignals(False)
        self.table_archives.viewport().update() 
        
        if self.archive_data:
            self.lbl_total_count.setText(self.i18n[self.lang]["total_files"].format(count=len(self.archive_data)))
        else:
            self.lbl_total_count.setText("")

    def on_archive_cell_clicked(self, row, col):
        if col == 0:
            item = self.table_archives.item(row, 0)
            fp = item.data(Qt.ItemDataRole.UserRole)
            self.archive_data[fp]['checked'] = (item.checkState() == Qt.CheckState.Checked)

    def on_archive_select(self):
        self.archive_timer.start(150) 

    def _process_archive_select(self):
        selected = self.table_archives.selectedItems()
        if not selected: return
        
        row = selected[0].row()
        item = self.table_archives.item(row, 0)
        if not item: return
        
        fp = item.data(Qt.ItemDataRole.UserRole)
        if fp not in self.archive_data: return 
        
        self.current_archive_path = fp
        data = self.archive_data[fp]

        self.update_inner_preview_list()

        if self.table_inner.rowCount() > 0:
            self.table_inner.selectRow(0)

        entries = data['entries'].copy()
        img_exts = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'}
        cover = next((e for e in entries if os.path.basename(e.filename).lower().startswith('cover') and Path(e.filename).suffix.lower() in img_exts), None)
        if cover:
            entries.remove(cover)
            entries.insert(0, cover)

        target = next((e for e in entries if Path(e.filename).suffix.lower() in img_exts), None)
        if target:
            threading.Thread(target=self._bg_load_image, args=(fp, target.original_name, data['ext'], self.lbl_cover_img), daemon=True).start()
        else:
            self.render_image(self.lbl_cover_img, None)

    def update_inner_preview_list(self):
        if not self.current_archive_path: return
        self.table_inner.blockSignals(True)
        self.table_inner.setRowCount(0)
        
        data = self.archive_data[self.current_archive_path]
        entries = data['entries'].copy()
        cover = next((e for e in entries if os.path.basename(e.filename).lower().startswith('cover')), None)
        if cover:
            entries.remove(cover)
            entries.insert(0, cover)

        total = len(entries)
        stem = Path(self.current_archive_path).stem
        t_patterns = self.i18n[self.lang]["patterns"]
        pattern = self.cb_pattern.currentText()
        custom_txt = self.entry_custom.text()
        
        flatten = self.config.get("flatten_folders", False)
        webp_on = self.config.get("webp_conversion", False)

        for idx, e in enumerate(entries):
            old = e.filename
            ext = ".webp" if webp_on else (os.path.splitext(old)[1] or ".jpg")
            
            pad = 4 if total >= 1000 else 3
            if pattern == t_patterns[1]: new = f"Cover{ext}" if idx==0 else f"Page_{idx:0{pad}d}{ext}"
            elif pattern == t_patterns[2]: new = f"{stem.replace(' ','_')}_{idx:0{pad}d}{ext}"
            elif pattern == t_patterns[3]: new = f"{stem.replace(' ','_')}_Cover{ext}" if idx==0 else f"{stem.replace(' ','_')}_Page_{idx:0{pad}d}{ext}"
            elif pattern == t_patterns[4]: new = f"{custom_txt.strip() or 'Custom'}_{idx:0{pad}d}{ext}"
            else: new = f"{idx:0{pad}d}{ext}"

            dir_name = os.path.dirname(old)
            if not flatten and dir_name:
                new = os.path.join(dir_name, new).replace('\\', '/')

            self.table_inner.insertRow(idx)
            i1 = QTableWidgetItem(os.path.basename(old) if flatten else old)
            i1.setData(Qt.ItemDataRole.UserRole, e.original_name) 
            i2 = QTableWidgetItem(new)
            i3 = QTableWidgetItem(f"{e.file_size/1024:.1f} KB")
            i3.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            
            self.table_inner.setItem(idx, 0, i1)
            self.table_inner.setItem(idx, 1, i2)
            self.table_inner.setItem(idx, 2, i3)
            
        self.table_inner.blockSignals(False)

    def on_inner_select(self):
        self.inner_timer.start(150)

    def _process_inner_select(self):
        selected = self.table_inner.selectedItems()
        if not selected or not self.current_archive_path: return
        row = selected[0].row()
        
        item = self.table_inner.item(row, 0)
        if not item: return
        
        orig_fp = item.data(Qt.ItemDataRole.UserRole)
        ext = self.archive_data[self.current_archive_path]['ext']
        threading.Thread(target=self._bg_load_image, args=(self.current_archive_path, orig_fp, ext, self.lbl_inner_img), daemon=True).start()

    def _bg_load_image(self, arc_path, inner_path, ext, target_label):
        img_data = self.get_preview_image_data(arc_path, inner_path, ext)
        self.image_loaded_signal.emit(target_label, img_data)

    def get_preview_image_data(self, filepath, target_filename, ext):
        try:
            if ext in ['.zip', '.cbz']:
                with zipfile.ZipFile(filepath, 'r') as zf:
                    for info in zf.infolist():
                        if info.filename == target_filename:
                            return zf.read(info.filename)
                    return None
            else:
                cmd = [self.seven_zip_path, 'e', '-so', str(filepath), target_filename]
                res = subprocess.run(cmd, capture_output=True, creationflags=CREATE_NO_WINDOW)
                if res.returncode == 0 and res.stdout:
                    return res.stdout
                return None
        except:
            return None

    def render_image(self, label_widget, img_data):
        cw, ch = 260, 300 

        if not img_data:
            path = get_resource_path("previewframe.png")
            if os.path.exists(path):
                try:
                    with open(path, "rb") as f: img_data = f.read()
                except: img_data = None
            
        if not img_data:
            label_widget.setText(self.i18n[self.lang]["no_preview"] if label_widget == self.lbl_cover_img else self.i18n[self.lang]["no_image"])
            return

        try:
            image = QImage.fromData(img_data)
            if image.isNull(): raise Exception("Invalid image")
            
            pixmap = QPixmap.fromImage(image)
            scaled_pixmap = pixmap.scaled(QSize(cw, ch), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            
            target = QPixmap(scaled_pixmap.size())
            target.fill(Qt.GlobalColor.transparent)
            
            painter = QPainter(target)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            path = QPainterPath()
            path.addRoundedRect(0, 0, target.width(), target.height(), 10, 10)
            painter.setClipPath(path)
            painter.drawPixmap(0, 0, scaled_pixmap)
            painter.end()
            
            label_widget.setPixmap(target)
        except:
            label_widget.setText(self.i18n[self.lang]["no_image"])

    def remove_selected(self):
        selected_items = self.table_archives.selectedItems()
        if not selected_items:
            return
            
        self.archive_timer.stop()
        self.inner_timer.stop()
            
        rows_to_remove = set()
        for item in selected_items:
            rows_to_remove.add(item.row())
            
        if not rows_to_remove: return
        min_row = min(rows_to_remove) 
            
        fps_to_remove = []
        for row in rows_to_remove:
            item = self.table_archives.item(row, 0)
            if item:
                fp = item.data(Qt.ItemDataRole.UserRole)
                fps_to_remove.append(fp)
                
        for fp in fps_to_remove:
            if fp in self.archive_data: 
                del self.archive_data[fp]
                
        self.refresh_archive_list()
        self.update_header_checkbox_state()
        
        new_count = self.table_archives.rowCount()
        if new_count > 0:
            next_row = min_row
            if next_row >= new_count:
                next_row = new_count - 1
            self.table_archives.selectRow(next_row) 
        else: 
            self.table_inner.setRowCount(0)
            self.render_image(self.lbl_cover_img, None)
            self.render_image(self.lbl_inner_img, None)
            self.current_archive_path = None

    def clear_list(self):
        self.archive_timer.stop()
        self.inner_timer.stop()
        self.archive_data.clear()
        self.refresh_archive_list()
        self.update_header_checkbox_state()
        self.table_inner.setRowCount(0)
        self.render_image(self.lbl_cover_img, None)
        self.render_image(self.lbl_inner_img, None)
        self.current_archive_path = None

    def start_process(self):
        targets = [fp for fp, d in self.archive_data.items() if d['checked']]
        if not targets:
            msg = "체크(☑)된 작업 대상이 없습니다." if self.lang == "ko" else "No checked targets."
            QMessageBox.warning(self, "Warning", msg)
            return

        self.toggle_ui_elements(is_processing=True)

        self.btn_run.clicked.disconnect()
        self.btn_run.clicked.connect(self.cancel_process)
        self.btn_run.setObjectName("actionBtnCancel")
        self.btn_run.setText(self.i18n[self.lang]["cancel_btn"])
        self.btn_run.setStyleSheet(self.styleSheet()) 

        self.progress_bar.show() 
        self.progress_bar.setValue(0)
        
        self.worker = RenameWorker(
            targets, self.config, self.archive_data, 
            self.i18n, self.cb_pattern.currentText(), 
            self.entry_custom.text(), self.seven_zip_path
        )
        self.worker.progress_signal.connect(self.update_status_msg)
        self.worker.finished_signal.connect(self.finish_process)
        self.worker.start()

    def cancel_process(self):
        self.btn_run.setText(self.i18n[self.lang]["cancel_wait"])
        self.btn_run.setEnabled(False)
        self.worker.cancel()

    def update_status_msg(self, percent, msg):
        self.lbl_status.setText(msg)
        self.progress_bar.setValue(percent)

    def finish_process(self, stats, new_archive_data):
        self.toggle_ui_elements(is_processing=False)

        self.btn_run.clicked.disconnect()
        self.btn_run.clicked.connect(self.start_process)
        self.btn_run.setObjectName("actionBtn") 
        self.btn_run.setText(self.i18n[self.lang]["run_btn"])
        self.btn_run.setEnabled(True)
        self.btn_run.setStyleSheet(self.styleSheet())
        self.progress_bar.hide()

        for old_fp, new_fp in new_archive_data.items():
            if old_fp != new_fp:
                if old_fp in self.archive_data: del self.archive_data[old_fp]
                self.load_archive_info(new_fp)
                self.current_archive_path = new_fp 
            else:
                self.force_reload_archive(new_fp)
                
        self.refresh_archive_list()
        self.update_header_checkbox_state()

        if self.current_archive_path and self.current_archive_path in self.archive_data:
            for row in range(self.table_archives.rowCount()):
                if self.table_archives.item(row, 0).data(Qt.ItemDataRole.UserRole) == self.current_archive_path:
                    self.table_archives.selectRow(row)
                    break
                    
        if self.worker._is_cancelled:
            self.lbl_status.setText("Cancelled" if self.lang == "en" else "작업 중단됨")
            QMessageBox.warning(self, "Cancelled", "사용자에 의해 작업이 중단되었습니다." if self.lang == "ko" else "Process cancelled by user.")
        else:
            if self.lang == "ko":
                msg_str = f"작업 완료! (성공: {len(stats['success'])}건 / 스킵: {len(stats['skip'])}건 / 오류: {len(stats['error'])}건)"
            else:
                msg_str = f"Done! (Success: {len(stats['success'])} / Skip: {len(stats['skip'])} / Error: {len(stats['error'])})"
            self.lbl_status.setText(msg_str)
        
        log_dlg = LogDialog(self, stats, self.i18n[self.lang])
        log_dlg.setStyleSheet(self.styleSheet())
        log_dlg.exec()

    def closeEvent(self, event):
        self.config["width"] = self.normalGeometry().width()
        self.config["height"] = self.normalGeometry().height()
        self.config["is_maximized"] = self.isMaximized()
        save_config(self.config)
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = RenamerApp()
    window.show()
    sys.exit(app.exec())
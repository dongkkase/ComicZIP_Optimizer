import os
import zipfile
import subprocess
from pathlib import Path
import re

from utils import natural_keys
from core.parser import is_garbage_folder_name, resolve_titles, format_leaf_name

CREATE_NO_WINDOW = 0x08000000

class OrganizerLoadTask:
    def __init__(self, paths, seven_z_exe, lang, signals):
        self.paths = paths
        self.seven_z_exe = seven_z_exe
        self.lang = lang
        self.signals = signals

    def run(self):
        try:
            exts = {'.zip', '.cbz', '.cbr', '.7z', '.rar'}
            img_exts = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'}
            all_files = []
            new_data = {}
            skipped_files = [] 
            
            for p in self.paths:
                path_obj = Path(p)
                if path_obj.is_file() and path_obj.suffix.lower() in exts:
                    all_files.append(path_obj)
                elif path_obj.is_dir():
                    for sub in path_obj.rglob('*'):
                        if sub.is_file() and sub.suffix.lower() in exts and 'bak' not in sub.parts:
                            all_files.append(sub)

            total = len(all_files)
            if total == 0:
                self.signals.org_load_done.emit({}, [])
                return

            for idx, path_obj in enumerate(all_files):
                filepath = str(path_obj)
                filename = path_obj.name
                
                if idx % max(1, total // 50) == 0 or idx == total - 1:
                    msg = f"[{idx+1}/{total}] 구조 분석 중: {filename}" if self.lang == 'ko' else f"[{idx+1}/{total}] Analyzing: {filename}"
                    self.signals.progress.emit(int((idx / total) * 100), msg)

                size_mb = os.path.getsize(filepath) / (1024 * 1024)
                image_paths = []
                requires_processing = False 
                
                def scan_zip(zf_path, prefix=""):
                    nonlocal requires_processing
                    try:
                        with zipfile.ZipFile(zf_path, 'r') as zf:
                            for info in zf.infolist():
                                fn_lower = info.filename.lower()
                                
                                if info.is_dir() or '/' in info.filename.replace('\\', '/'):
                                    requires_processing = True
                                    
                                if fn_lower.endswith(('.zip', '.cbz', '.cbr', '.rar', '.7z')):
                                    requires_processing = True
                                    try:
                                        with zf.open(info.filename) as nested_zf:
                                            scan_zip(nested_zf, prefix + info.filename + "/")
                                    except: pass
                                elif fn_lower.endswith(('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif')):
                                    image_paths.append(prefix + info.filename)
                    except:
                        if isinstance(zf_path, (str, Path)):
                            res = subprocess.run([self.seven_z_exe, 'l', '-slt', '-ba', str(zf_path)], capture_output=True, text=True, errors='ignore', creationflags=CREATE_NO_WINDOW)
                            for line in res.stdout.splitlines():
                                if line.startswith("Path = "):
                                    p = line[7:].replace('\\', '/')
                                    if '/' in p:
                                        requires_processing = True
                                    if p.lower().endswith(('.zip', '.cbz', '.cbr', '.rar', '.7z')):
                                        requires_processing = True
                                    if p.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif')):
                                        image_paths.append(prefix + p)

                scan_zip(filepath)
                if not image_paths: continue

                if not requires_processing:
                    skipped_files.append(filename)
                    continue

                # 🌟 5. 하위 폴더 51개 분할 방지! 최상위(Top-Level) 기준으로 14개로 묶어냅니다.
                leaf_folders = set()
                root_images = []
                for p in image_paths:
                    dirname = os.path.dirname(p)
                    if dirname:
                        top_folder = dirname.split('/')[0] # '내 이야기 01권.zip' 등으로 묶임
                        leaf_folders.add(top_folder)
                    else:
                        root_images.append(p)
                        
                if root_images:
                    leaf_folders.add('')
                    
                leaf_folders = sorted(list(leaf_folders), key=natural_keys)

                inner_meaningful_name = ""
                if leaf_folders:
                    for leaf in leaf_folders:
                        if leaf:
                            clean_p = re.sub(r'\.(zip|cbz|cbr|rar|7z)$', '', leaf, flags=re.IGNORECASE)
                            if not is_garbage_folder_name(clean_p) and re.search(r'[가-힣a-zA-Z]', clean_p):
                                inner_meaningful_name = clean_p
                                break

                display_title, core_title = resolve_titles(filepath, inner_meaningful_name)
                parsed_vols = []
                
                if not leaf_folders or (len(leaf_folders) == 1 and leaf_folders[0] == ''):
                    vol_name = format_leaf_name(core_title, filename, 0, 1, self.lang)
                    parsed_vols.append({'original_path': '', 'new_name': vol_name, 'type': 'archive'})
                else:
                    for v_idx, leaf in enumerate(leaf_folders):
                        if not leaf: 
                            vol_name = format_leaf_name(core_title, filename, v_idx, len(leaf_folders), self.lang)
                            parsed_vols.append({'original_path': '', 'new_name': vol_name, 'type': 'folder'})
                        else:
                            vol_name = format_leaf_name(core_title, leaf, v_idx, len(leaf_folders), self.lang)
                            parsed_vols.append({'original_path': leaf, 'new_name': vol_name, 'type': 'folder'})

                new_data[filepath] = {
                    'checked': True,
                    'name': filename,
                    'size_mb': size_mb,
                    'clean_title': display_title,
                    'volumes': parsed_vols
                }

            self.signals.progress.emit(100, "분석 완료" if self.lang == 'ko' else "Analysis Done")
            self.signals.org_load_done.emit(new_data, skipped_files) 

        except Exception as e:
            self.signals.progress.emit(100, f"Error: {e}")
            self.signals.org_load_done.emit({}, [])

class FileLoadTask:
    def __init__(self, paths, seven_z_exe, lang, signals):
        self.paths = paths
        self.seven_z_exe = seven_z_exe
        self.lang = lang
        self.signals = signals

    def get_7z_entries(self, filepath):
        cmd = [self.seven_z_exe, 'l', '-slt', '-ba', str(filepath)]
        result = subprocess.run(cmd, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW, encoding='utf-8', errors='ignore')
        entries = []
        current_entry = {}
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                if current_entry and 'Path' in current_entry and not current_entry.get('Attributes', '').startswith('D'):
                    entries.append({
                        'original_name': current_entry['Path'],
                        'filename': current_entry['Path'].replace('\\', '/'),
                        'file_size': int(current_entry.get('Size', '0')) if str(current_entry.get('Size', '0')).isdigit() else 0
                    })
                current_entry = {}
            elif '=' in line:
                k, v = line.split('=', 1)
                current_entry[k.strip()] = v.strip()
        if current_entry and 'Path' in current_entry and not current_entry.get('Attributes', '').startswith('D'):
            entries.append({
                'original_name': current_entry['Path'],
                'filename': current_entry['Path'].replace('\\', '/'),
                'file_size': int(current_entry.get('Size', '0')) if str(current_entry.get('Size', '0')).isdigit() else 0
            })
        return entries

    def run(self):
        try:
            exts = {'.zip', '.cbz', '.cbr', '.7z'}
            all_files = []
            new_data = {}
            nested_files = []
            unsupported_files = []
            
            for p in self.paths:
                path_obj = Path(p)
                if path_obj.is_file():
                    all_files.append(path_obj)
                elif path_obj.is_dir():
                    for sub in path_obj.rglob('*'):
                        if sub.is_file() and 'bak' not in sub.parts:
                            all_files.append(sub)

            total = len(all_files)
            if total == 0:
                self.signals.load_done.emit({}, [], [])
                return

            for idx, path_obj in enumerate(all_files):
                filepath = str(path_obj)
                filename = path_obj.name
                ext = path_obj.suffix.lower()

                if idx % max(1, total // 100) == 0 or idx == total - 1:
                    msg = f"[{idx+1}/{total}] 파일 분석 중: {filename}" if self.lang == 'ko' else f"[{idx+1}/{total}] Analyzing: {filename}"
                    self.signals.progress.emit(int((idx / total) * 100), msg)

                if ext not in exts:
                    unsupported_files.append(filename)
                    continue

                try:
                    size_mb = os.path.getsize(filepath) / (1024 * 1024)
                    if ext in ['.zip', '.cbz']:
                        with zipfile.ZipFile(filepath, 'r') as zf:
                            entries = sorted([{
                                'original_name': info.filename,
                                'filename': info.filename.replace('\\', '/'),
                                'file_size': info.file_size
                            } for info in zf.infolist() if not info.is_dir()], key=lambda x: natural_keys(x['filename']))
                    else:
                        if not os.path.exists(self.seven_z_exe): continue
                        entries = sorted(self.get_7z_entries(filepath), key=lambda x: natural_keys(x['filename']))

                    image_exts = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'}
                    img_entries = [e for e in entries if Path(e['filename']).suffix.lower() in image_exts]
                    
                    if not img_entries: continue 

                    nested_exts = {'.zip', '.cbz', '.cbr', '.7z', '.rar', '.alz', '.egg'}
                    if any(Path(e['filename']).suffix.lower() in nested_exts for e in entries):
                        nested_files.append(filename)
                        continue

                    new_data[filepath] = {
                        'checked': True,
                        'entries': img_entries, 'size_mb': size_mb, 'name': filename, 'ext': ext
                    }
                except: pass

            self.signals.progress.emit(100, "분석 완료" if self.lang == 'ko' else "Analysis Done")
            self.signals.load_done.emit(new_data, nested_files, unsupported_files)

        except Exception as e:
            self.signals.progress.emit(100, f"Error: {e}")
            self.signals.load_done.emit({}, [], [])
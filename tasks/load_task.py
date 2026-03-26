import os
import zipfile
import subprocess
from pathlib import Path
import re
import tempfile
import uuid
import shutil

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
                
                sys_temp = tempfile.gettempdir()
                safe_id = uuid.uuid4().hex[:6]
                temp_base = os.path.join(sys_temp, f"ComicZIP_Load_{safe_id}_{filename}")
                if os.path.exists(temp_base): shutil.rmtree(temp_base, ignore_errors=True)
                os.makedirs(temp_base, exist_ok=True)
                
                try:
                    def extract_all(src_path, dest_dir):
                        subprocess.run([self.seven_z_exe, 'x', src_path, f'-o{dest_dir}', '-y'], stdout=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW, check=False)
                        while True:
                            found_archives = []
                            for root_dir, _, files in os.walk(dest_dir):
                                for f in files:
                                    if f.lower().endswith(('.zip', '.cbz', '.rar', '.7z')):
                                        found_archives.append(os.path.join(root_dir, f))
                            if not found_archives: break
                            for arch in found_archives:
                                arch_dir = os.path.splitext(arch)[0] 
                                os.makedirs(arch_dir, exist_ok=True)
                                subprocess.run([self.seven_z_exe, 'x', arch, f'-o{arch_dir}', '-y'], stdout=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
                                os.remove(arch)

                    extract_all(filepath, temp_base)

                    # 🌟 [핵심 개선] 껍데기 폴더를 삼킬 때, 의미 있는 이름(예: 단다단 19권)을 절대 잃어버리지 않고 기억(swallowed_name)해 둡니다.
                    def get_actual_root(curr_dir):
                        swallowed_name = ""
                        while True:
                            items = os.listdir(curr_dir)
                            subdirs = [i for i in items if os.path.isdir(os.path.join(curr_dir, i))]
                            images = [i for i in items if i.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'))]
                            
                            if len(subdirs) == 1 and len(images) == 0:
                                subdir_name = subdirs[0]
                                if not is_garbage_folder_name(subdir_name):
                                    swallowed_name = subdir_name
                                curr_dir = os.path.join(curr_dir, subdir_name)
                            else:
                                break
                        return curr_dir, swallowed_name

                    actual_root, swallowed_name = get_actual_root(temp_base)

                    volume_groups = {}
                    root_images = []
                    total_images = 0
                    
                    for root_dir, _, files in os.walk(actual_root):
                        for f in files:
                            if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif')):
                                total_images += 1
                                img_path = os.path.join(root_dir, f)
                                rel_path = os.path.relpath(img_path, actual_root)
                                parts = Path(rel_path).parts
                                if len(parts) == 1:
                                    root_images.append(img_path)
                                else:
                                    top_folder = parts[0]
                                    if top_folder not in volume_groups:
                                        volume_groups[top_folder] = []
                                    volume_groups[top_folder].append(img_path)
                                    
                    if total_images == 0:
                        skipped_files.append(filename)
                        continue

                    if root_images:
                        if volume_groups:
                            pass 
                        else:
                            volume_groups['Root_Files'] = root_images
                            
                    group_names = sorted(list(volume_groups.keys()), key=natural_keys)

                    inner_meaningful_name = ""
                    if group_names:
                        for leaf in group_names:
                            if leaf and leaf != 'Root_Files':
                                clean_p = re.sub(r'\.(zip|cbz|cbr|rar|7z)$', '', leaf, flags=re.IGNORECASE)
                                if not is_garbage_folder_name(clean_p) and re.search(r'[가-힣a-zA-Z]', clean_p):
                                    inner_meaningful_name = clean_p
                                    break

                    # 🌟 삼켰던 의미 있는 폴더명이 있다면 여기서 복구하여 파싱에 넘겨줍니다!
                    if not inner_meaningful_name and swallowed_name:
                        inner_meaningful_name = re.sub(r'\.(zip|cbz|cbr|rar|7z)$', '', swallowed_name, flags=re.IGNORECASE)

                    display_title, core_title = resolve_titles(filepath, inner_meaningful_name)
                    parsed_vols = []
                    
                    if len(group_names) == 1 and group_names[0] == 'Root_Files':
                        vol_name = format_leaf_name(core_title, inner_meaningful_name or filename, 0, 1, self.lang)
                        parsed_vols.append({'original_path': '', 'new_name': vol_name, 'type': 'archive'})
                    else:
                        for v_idx, leaf in enumerate(group_names):
                            vol_name = format_leaf_name(core_title, leaf, v_idx, len(group_names), self.lang)
                            parsed_vols.append({'original_path': leaf, 'new_name': vol_name, 'type': 'folder'})

                    new_data[filepath] = {
                        'checked': True,
                        'name': filename,
                        'size_mb': size_mb,
                        'clean_title': display_title,
                        'volumes': parsed_vols
                    }

                except Exception as e:
                    skipped_files.append(f"{filename} (Error: {str(e)})")
                finally:
                    shutil.rmtree(temp_base, ignore_errors=True)

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
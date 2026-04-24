import os
import zipfile
import subprocess
import sys
from pathlib import Path
import re
import tempfile
import uuid
import shutil

from utils import natural_keys
from core.parser import is_garbage_folder_name, resolve_titles, format_leaf_name, extract_core_title, fix_encoding

CREATE_NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0

def _subprocess_kwargs():
    if sys.platform == 'win32':
        return {'creationflags': CREATE_NO_WINDOW}
    return {}


def _list_entries(seven_z_exe, filepath):
    cmd = [seven_z_exe, 'l', '-slt', '-ba', str(filepath)]
    try:
        result = subprocess.run(
            cmd, capture_output=True,
            **_subprocess_kwargs()
        )
        # Windows에서 한글 인코딩 자동 감지
        raw = result.stdout
        for enc in ('utf-8', 'cp949', 'euc-kr', 'utf-8-sig'):
            try:
                stdout = raw.decode(enc)
                break
            except (UnicodeDecodeError, LookupError):
                continue
        else:
            stdout = raw.decode('utf-8', errors='ignore')
    except Exception:
        return [], False

    nested_exts = {'.zip', '.cbz', '.cbr', '.7z', '.rar'}
    img_exts = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'}
    entries = []
    has_nested = False
    current = {}

    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            if current.get('Path'):
                is_dir = current.get('Attributes', '').startswith('D')
                path_str = current['Path'].replace('\\', '/')
                size = int(current['Size']) if current.get('Size', '').isdigit() else 0
                ext = Path(path_str).suffix.lower()
                entries.append({
                    'path': path_str,
                    'is_dir': is_dir,
                    'size': size,
                    'is_img': not is_dir and ext in img_exts,
                    'is_nested': not is_dir and ext in nested_exts,
                })
                if not is_dir and ext in nested_exts:
                    has_nested = True
            current = {}
        elif '=' in line:
            k, v = line.split('=', 1)
            current[k.strip()] = v.strip()

    if current.get('Path'):
        is_dir = current.get('Attributes', '').startswith('D')
        path_str = current['Path'].replace('\\', '/')
        size = int(current['Size']) if current.get('Size', '').isdigit() else 0
        ext = Path(path_str).suffix.lower()
        entries.append({
            'path': path_str,
            'is_dir': is_dir,
            'size': size,
            'is_img': not is_dir and ext in img_exts,
            'is_nested': not is_dir and ext in nested_exts,
        })
        if not is_dir and ext in nested_exts:
            has_nested = True

    return entries, has_nested


def _analyze_from_entries(entries, filepath, lang):
    img_exts = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'}
    img_entries = [e for e in entries if e['is_img']]
    if not img_entries:
        return None, '', '', None

    swallowed_name = ''
    top_level_folders = set()
    for e in img_entries:
        parts = Path(e['path']).parts
        if len(parts) > 1:
            top_level_folders.add(parts[0])

    all_under_one = len(top_level_folders) == 1
    if all_under_one:
        single_top = list(top_level_folders)[0]
        sub_folders = set()
        root_imgs = []
        for e in img_entries:
            parts = Path(e['path']).parts
            if len(parts) == 2:
                root_imgs.append(e)
            elif len(parts) > 2:
                sub_folders.add(parts[1])
        if not root_imgs and not is_garbage_folder_name(single_top):
            swallowed_name = single_top
            img_entries = [
                {**e, 'path': '/'.join(Path(e['path']).parts[1:])}
                for e in img_entries
            ]

    volume_groups = {}
    root_images = []

    for e in img_entries:
        parts = Path(e['path']).parts
        if len(parts) == 1:
            root_images.append(e['path'])
        else:
            top_folder_name = parts[0]
            p0 = top_folder_name.lower()
            is_part_folder = bool(re.search(r'(\d+\s*부|제\s*\d+\s*부|시즌|season|part)', p0))
            if is_part_folder and len(parts) > 2:
                top_folder = top_folder_name + '/' + parts[1]
            else:
                top_folder = top_folder_name
            if top_folder not in volume_groups:
                volume_groups[top_folder] = []
            volume_groups[top_folder].append(e['path'])

    if root_images and not volume_groups:
        volume_groups['Root_Files'] = root_images

    # ── 화 단위 감지: 전체 경로의 모든 파트에서 검사 ──
    force_unit = None
    ch_pattern = re.compile(r'\d+(?:\.\d+)?\s*화')

    # volume_groups 키 검사
    all_leaf_names = [k for k in volume_groups.keys() if k != 'Root_Files']
    found_ch = any(ch_pattern.search(leaf) for leaf in all_leaf_names)

    # 못찾으면 img_entries의 전체 경로 파트 검사 (제목 포함 폴더명 커버)
    if not found_ch:
        for e in img_entries:
            full_path_str = e['path']
            if ch_pattern.search(full_path_str):
                found_ch = True
                break

    if found_ch:
        force_unit = '화'

    inner_meaningful_name = ''
    group_names = sorted(list(volume_groups.keys()), key=natural_keys)
    for leaf in group_names:
        if leaf and leaf != 'Root_Files':
            clean_p = re.sub(r'\.(zip|cbz|cbr|rar|7z)$', '', leaf, flags=re.IGNORECASE)
            if not is_garbage_folder_name(clean_p) and re.search(r'[가-힣a-zA-Z]', clean_p):
                inner_meaningful_name = clean_p
                break

    if not inner_meaningful_name and swallowed_name:
        inner_meaningful_name = re.sub(r'\.(zip|cbz|cbr|rar|7z)$', '', swallowed_name, flags=re.IGNORECASE)

    return volume_groups, inner_meaningful_name, swallowed_name, force_unit


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
                    msg = (
                        f"[{idx+1}/{total}] 구조 분석 중: {filename}"
                        if self.lang == 'ko'
                        else f"[{idx+1}/{total}] Analyzing: {filename}"
                    )
                    self.signals.progress.emit(int((idx / total) * 100), msg)

                size_mb = os.path.getsize(filepath) / (1024 * 1024)

                try:
                    # ── 핵심 변경: 실제 압축 해제 대신 목록 조회 ──
                    entries, has_nested = _list_entries(self.seven_z_exe, filepath)

                    if has_nested:
                        volume_groups, inner_meaningful_name, swallowed_name, force_unit = \
                            self._fallback_extract(filepath, filename)
                    else:
                        volume_groups, inner_meaningful_name, swallowed_name, force_unit = \
                            _analyze_from_entries(entries, filepath, self.lang)

                    if volume_groups is None:
                        skipped_files.append(filename)
                        continue

                    display_title, core_title = resolve_titles(filepath, inner_meaningful_name)
                    parsed_vols = []
                    
                    # 단위 판별
                    unit_counts = {'권': 0, '화': 0}
                    for leaf in group_names:
                        if '화' in leaf: unit_counts['화'] += 1
                        if '권' in leaf: unit_counts['권'] += 1
                    prevalent_unit = '화' if unit_counts['화'] > unit_counts['권'] else '권'

                    def fix_encoding(text):
                        try: return text.encode('cp949').decode('utf-8')
                        except UnicodeError:
                            try: return text.encode('cp437').decode('cp949')
                            except UnicodeError: return text

                    def detect_spinoff(main_title, leaf_name):
                        leaf_core = extract_core_title(leaf_name)
                        if not leaf_core or leaf_core == main_title: return None, main_title
                        
                        main_clean = main_title.replace(" ", "")
                        leaf_clean = leaf_core.replace(" ", "")
                        
                        # 오리지널 폴더/파일명이 메인 제목과 다르면 외전으로 판별
                        if (main_clean in leaf_clean and len(leaf_clean) > len(main_clean)) or \
                           re.search(r'(외전|특별편|단편|스핀오프|ss|ex)', leaf_name, re.IGNORECASE):
                            return leaf_core, leaf_core
                        return None, main_title

                    for v_idx, leaf in enumerate(group_names):
                        # 한글 깨짐 복구 적용
                        leaf_basename = fix_encoding(os.path.basename(leaf.replace('\\', '/')) if leaf != 'Root_Files' else filename)
                        spinoff_folder, effective_core = detect_spinoff(core_title, leaf_basename)
                        
                        vol_name = format_leaf_name(effective_core, leaf_basename, v_idx, len(group_names), self.lang, prevalent_unit)
                        
                        parsed_vols.append({
                            'original_path': leaf if leaf != 'Root_Files' else '', 
                            'original_basename': leaf_basename,
                            'new_name': vol_name, 
                            'spinoff_folder': spinoff_folder,
                            'type': 'archive' if leaf == 'Root_Files' else 'folder'
                        })

                    new_data[filepath] = {
                        'checked': True,
                        'name': filename,
                        'size_mb': size_mb,
                        'clean_title': display_title,
                        'volumes': parsed_vols
                    }

                except Exception as e:
                    skipped_files.append(f"{filename} (Error: {str(e)})")

            self.signals.progress.emit(
                100,
                "분석 완료" if self.lang == 'ko' else "Analysis Done"
            )
            self.signals.org_load_done.emit(new_data, skipped_files)

        except Exception as e:
            self.signals.progress.emit(100, f"Error: {e}")
            self.signals.org_load_done.emit({}, [])

    def _fallback_extract(self, filepath, filename):
        """
        중첩 압축이 있는 경우에만 사용하는 기존 방식 (실제 압축 해제).
        기존 OrganizerLoadTask 로직을 그대로 유지.
        """
        safe_id = uuid.uuid4().hex[:6]
        sys_temp = tempfile.gettempdir()
        temp_base = os.path.join(sys_temp, f"ComicZIP_Load_{safe_id}_{filename}")
        if os.path.exists(temp_base):
            shutil.rmtree(temp_base, ignore_errors=True)
        os.makedirs(temp_base, exist_ok=True)

        try:
            def extract_all(src_path, dest_dir):
                subprocess.run(
                    [self.seven_z_exe, 'x', src_path, f'-o{dest_dir}', '-y'],
                    stdout=subprocess.DEVNULL,
                    **_subprocess_kwargs(),
                    check=False
                )
                while True:
                    found = []
                    for root_dir, _, files in os.walk(dest_dir):
                        for f in files:
                            if f.lower().endswith(('.zip', '.cbz', '.rar', '.7z')):
                                found.append(os.path.join(root_dir, f))
                    if not found:
                        break
                    for arch in found:
                        arch_dir = os.path.splitext(arch)[0]
                        os.makedirs(arch_dir, exist_ok=True)
                        subprocess.run(
                            [self.seven_z_exe, 'x', arch, f'-o{arch_dir}', '-y'],
                            stdout=subprocess.DEVNULL,
                            **_subprocess_kwargs()
                        )
                        os.remove(arch)

            extract_all(filepath, temp_base)

            def get_actual_root(curr_dir):
                swallowed_name = ''
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
                            top_folder_name = parts[0]
                            p0 = top_folder_name.lower()
                            is_part_folder = bool(re.search(r'(\d+\s*부|제\s*\d+\s*부|시즌|season|part)', p0))
                            if is_part_folder and len(parts) > 2:
                                top_folder = os.path.join(top_folder_name, parts[1])
                            else:
                                top_folder = top_folder_name
                            if top_folder not in volume_groups:
                                volume_groups[top_folder] = []
                            volume_groups[top_folder].append(img_path)

            if total_images == 0:
                return None, '', ''

            if root_images and not volume_groups:
                volume_groups['Root_Files'] = root_images

            group_names = sorted(list(volume_groups.keys()), key=natural_keys)
            inner_meaningful_name = ''
            for leaf in group_names:
                if leaf and leaf != 'Root_Files':
                    clean_p = re.sub(r'\.(zip|cbz|cbr|rar|7z)$', '', leaf, flags=re.IGNORECASE)
                    if not is_garbage_folder_name(clean_p) and re.search(r'[가-힣a-zA-Z]', clean_p):
                        inner_meaningful_name = clean_p
                        break

            if not inner_meaningful_name and swallowed_name:
                inner_meaningful_name = re.sub(r'\.(zip|cbz|cbr|rar|7z)$', '', swallowed_name, flags=re.IGNORECASE)

            force_unit = None
            ch_pattern = re.compile(r'\d+(?:\.\d+)?\s*화')
            all_leaf_names = [k for k in volume_groups.keys() if k != 'Root_Files']
            if not any(ch_pattern.search(leaf) for leaf in all_leaf_names):
                for root_dir, _, files in os.walk(actual_root):
                    rel = os.path.relpath(root_dir, actual_root)
                    if ch_pattern.search(rel):
                        force_unit = '화'
                        break
            else:
                force_unit = '화'

            return volume_groups, inner_meaningful_name, swallowed_name, force_unit

        finally:
            shutil.rmtree(temp_base, ignore_errors=True)


class FileLoadTask:
    def __init__(self, paths, seven_z_exe, lang, signals):
        self.paths = paths
        self.seven_z_exe = seven_z_exe
        self.lang = lang
        self.signals = signals

    def get_7z_entries(self, filepath):
        cmd = [self.seven_z_exe, 'l', '-slt', '-ba', str(filepath)]
        result = subprocess.run(
            cmd, capture_output=True,
            **_subprocess_kwargs()
        )
        raw = result.stdout
        for enc in ('utf-8', 'cp949', 'euc-kr', 'utf-8-sig'):
            try:
                stdout = raw.decode(enc)
                break
            except (UnicodeDecodeError, LookupError):
                continue
        else:
            stdout = raw.decode('utf-8', errors='ignore')

        entries = []
        current_entry = {}
        for line in stdout.splitlines():
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
                    msg = (
                        f"[{idx+1}/{total}] 파일 분석 중: {filename}"
                        if self.lang == 'ko'
                        else f"[{idx+1}/{total}] Analyzing: {filename}"
                    )
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
                        if not os.path.exists(self.seven_z_exe):
                            continue
                        entries = sorted(self.get_7z_entries(filepath), key=lambda x: natural_keys(x['filename']))

                    image_exts = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'}
                    img_entries = [e for e in entries if Path(e['filename']).suffix.lower() in image_exts]

                    if not img_entries:
                        continue

                    nested_exts = {'.zip', '.cbz', '.cbr', '.7z', '.rar', '.alz', '.egg'}
                    if any(Path(e['filename']).suffix.lower() in nested_exts for e in entries):
                        nested_files.append(filename)
                        continue

                    new_data[filepath] = {
                        'checked': True,
                        'entries': img_entries,
                        'size_mb': size_mb,
                        'name': filename,
                        'ext': ext
                    }
                except Exception:
                    pass

            self.signals.progress.emit(
                100,
                "분석 완료" if self.lang == 'ko' else "Analysis Done"
            )
            self.signals.load_done.emit(new_data, nested_files, unsupported_files)

        except Exception as e:
            self.signals.progress.emit(100, f"Error: {e}")
            self.signals.load_done.emit({}, [], [])
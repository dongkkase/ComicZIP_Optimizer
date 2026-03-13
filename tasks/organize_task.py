import os
import shutil
import uuid
import tempfile
import subprocess
import re
from pathlib import Path

from utils import natural_keys
from core.parser import extract_core_title, get_similarity, is_garbage_folder_name

CREATE_NO_WINDOW = 0x08000000

class OrganizerProcessTask:
    def __init__(self, targets, config, org_data, seven_z_exe, signals):
        self.targets = targets
        self.backup_on = config.get("backup_on", False)
        self.target_format = config.get("target_format", "none")
        self.lang = config.get("lang", "ko")
        self.org_data = org_data
        self.seven_z_exe = seven_z_exe
        self.signals = signals
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        stats = {'success': [], 'skip': [], 'error': []}
        created_zips = [] 
        
        try:
            total = len(self.targets)
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
                msg = f"[{idx+1}/{total}] 구조 재배치 중: {filename}" if self.lang == "ko" else f"[{idx+1}/{total}] Reorganizing: {filename}"
                self.signals.progress.emit(int((idx / total) * 100), msg)

                # 🌟 [버그 수정 및 안전장치 완벽화]
                # 분석/압축해제를 시작하기도 전에, 일단 원본 압축파일을 무조건 .tmp로 피신시킵니다!
                # 새 파일이 생성될 때 원본과 이름이 겹쳐서 발생하는 모든 충돌 버그를 원천 차단합니다.
                original_tmp = file_path + ".tmp"

                try:
                    if self.backup_on:
                        bak_dir = os.path.join(os.path.dirname(file_path), 'bak')
                        os.makedirs(bak_dir, exist_ok=True)
                        shutil.copy2(file_path, os.path.join(bak_dir, filename))

                    if os.path.exists(original_tmp): 
                        os.remove(original_tmp)
                    os.rename(file_path, original_tmp)

                    data = self.org_data[file_path]
                    clean_title = data['clean_title']
                    
                    base_out_dir = data.get('out_path', os.path.dirname(file_path))
                    
                    safe_id = uuid.uuid4().hex[:6]
                    sys_temp = tempfile.gettempdir()
                    temp_base = os.path.join(sys_temp, f"ComicZIP_{safe_id}_{filename}")
                    
                    if os.path.exists(temp_base): shutil.rmtree(temp_base, ignore_errors=True)
                    os.makedirs(temp_base, exist_ok=True)

                    def extract_all(src_path, dest_dir):
                        subprocess.run([self.seven_z_exe, 'x', src_path, f'-o{dest_dir}', '-y'], stdout=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW, check=True)
                        while True:
                            found_archives = []
                            for root, dirs, files in os.walk(dest_dir):
                                for f in files:
                                    if f.lower().endswith(('.zip', '.cbz', '.rar', '.7z')):
                                        found_archives.append(os.path.join(root, f))
                            if not found_archives: break
                            
                            for arch in found_archives:
                                arch_dir = os.path.splitext(arch)[0] 
                                os.makedirs(arch_dir, exist_ok=True)
                                subprocess.run([self.seven_z_exe, 'x', arch, f'-o{arch_dir}', '-y'], stdout=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
                                os.remove(arch)

                    # 피신시켜둔 .tmp 파일의 압축을 풉니다.
                    extract_all(original_tmp, temp_base)

                    leaf_folders = set()
                    for root, dirs, files in os.walk(temp_base):
                        for f in files:
                            if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif')):
                                leaf_folders.add(root)
                                
                    if len(leaf_folders) > 1 and temp_base in leaf_folders:
                        leaf_folders.remove(temp_base)
                        
                    leaf_folders = sorted(list(leaf_folders), key=natural_keys)
                    target_ext = f".{self.target_format}" if self.target_format != "none" else ".zip"
                    archive_type = '-t7z' if target_ext == '.7z' else '-tzip'

                    for v_idx, leaf in enumerate(leaf_folders):
                        if self._is_cancelled: break
                        
                        sub_prog = int((idx / total) * 100) + int((v_idx / len(leaf_folders)) * (100 / total))
                        self.signals.progress.emit(sub_prog, f"{msg} ({v_idx+1}/{len(leaf_folders)})")

                        if v_idx < len(data['volumes']):
                            vol_base = data['volumes'][v_idx]['new_name']
                        else:
                            pad = 4 if len(leaf_folders) >= 1000 else (2 if len(leaf_folders) < 100 else 3)
                            if self.lang == 'en': vol_base = f"{clean_title} v{v_idx+1:0{pad}d}"
                            else: vol_base = f"{clean_title} {v_idx+1:0{pad}d}권"
                            
                        vol_name = f"{vol_base}{target_ext}"
                        rel_path = os.path.relpath(leaf, temp_base)
                        
                        if rel_path == '.':
                            out_dir = base_out_dir
                        else:
                            parts = Path(rel_path).parts
                            valid_parts = []
                            for p in parts[:-1]: 
                                cp = re.sub(r'\[.*?\]|\(.*?\)|<.*?>', '', p).strip()
                                cp = re.sub(r'[-_+]+', ' ', cp).strip()
                                
                                is_garbage = (len(p) > 15 and bool(re.match(r'^[a-fA-F0-9\-_]+$', p))) or bool(re.match(r'^\d+$', cp))
                                if not is_garbage and cp:
                                    p_core = extract_core_title(p)
                                    c_core = extract_core_title(clean_title)
                                    if p_core and c_core and get_similarity(p_core, c_core) >= 0.5:
                                        continue
                                    valid_parts.append(cp if cp else p)
                                    
                            rel_dir = os.path.join(*valid_parts) if valid_parts else ''
                            out_dir = os.path.join(base_out_dir, rel_dir) if rel_dir else base_out_dir

                        os.makedirs(out_dir, exist_ok=True)
                        target_path = os.path.join(out_dir, vol_name)

                        temp_archive = os.path.join(sys_temp, f"ComicZIP_Done_{safe_id}_{uuid.uuid4().hex[:4]}_{vol_name}")
                        if os.path.exists(temp_archive): os.remove(temp_archive)
                        
                        subprocess.run([self.seven_z_exe, 'a', archive_type, temp_archive, '*', '-mx=0'], cwd=leaf, stdout=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW, check=True)
                        
                        if os.path.exists(target_path): 
                            os.remove(target_path)
                        shutil.move(temp_archive, target_path)
                        
                        created_zips.append(target_path)

                    shutil.rmtree(temp_base, ignore_errors=True)
                    
                    if not self._is_cancelled:
                        # 🌟 작업이 완벽히 끝난 후, 피신시켜둔 구버전 .tmp 파일 영구 삭제
                        if os.path.exists(original_tmp):
                            os.remove(original_tmp)
                            
                        stats['success'].append(filename)
                        try:
                            parent_dir = os.path.dirname(file_path)
                            if os.path.exists(parent_dir) and not os.listdir(parent_dir):
                                os.rmdir(parent_dir)
                        except: pass
                    else:
                        # 🚨 유저가 취소를 눌렀다면 .tmp를 원본 이름으로 원상 복구!
                        if os.path.exists(original_tmp):
                            os.rename(original_tmp, file_path)

                except Exception as e:
                    # 🚨 에러가 발생해서 튕겼다면 .tmp를 원본 이름으로 원상 복구!
                    if os.path.exists(original_tmp):
                        if os.path.exists(file_path): 
                            os.remove(file_path)
                        os.rename(original_tmp, file_path)
                    stats['error'].append(f"{filename} - {str(e)}")

            if self._is_cancelled:
                self.signals.progress.emit(0, "Cancelled" if self.lang == "en" else "작업 중단됨")
            else:
                self.signals.progress.emit(100, "Done!" if self.lang == "en" else "작업 완료!")
                
            self.signals.org_process_done.emit(stats, created_zips, self._is_cancelled)

        except Exception as e:
            self.signals.progress.emit(100, f"Critical Error: {e}")
            stats['error'].append(str(e))
            self.signals.org_process_done.emit(stats, created_zips, True)
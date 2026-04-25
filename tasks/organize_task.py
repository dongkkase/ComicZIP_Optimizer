import os
import shutil
import uuid
import tempfile
import subprocess
import re
import concurrent.futures
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

                original_tmp = file_path + ".tmp"
                current_target_created_zips = []

                try:
                    if self.backup_on:
                        bak_dir = os.path.join(os.path.dirname(file_path), 'bak')
                        os.makedirs(bak_dir, exist_ok=True)
                        shutil.copy2(file_path, os.path.join(bak_dir, filename))

                    if os.path.exists(original_tmp): 
                        os.remove(original_tmp)
                    os.rename(file_path, original_tmp)

                    data = self.org_data[file_path]
                    
                    # 볼륨 제목 정제
                    clean_title = data['clean_title']
                    clean_title = re.sub(r'^[._\-\s]+', '', clean_title)
                    
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

                    extract_all(original_tmp, temp_base)

                    def get_actual_root(curr_dir):
                        while True:
                            items = os.listdir(curr_dir)
                            subdirs = [i for i in items if os.path.isdir(os.path.join(curr_dir, i))]
                            images = [i for i in items if i.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'))]
                            if len(subdirs) == 1 and len(images) == 0:
                                curr_dir = os.path.join(curr_dir, subdirs[0])
                            else:
                                break
                        return curr_dir

                    actual_root = get_actual_root(temp_base)

                    leaf_folders = set()
                    root_images = []
                    total_extracted_images = 0

                    for root_dir, _, files in os.walk(actual_root):
                        for f in files:
                            if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif')):
                                total_extracted_images += 1
                                rel_path = os.path.relpath(root_dir, actual_root)
                                if rel_path == '.':
                                    root_images.append(os.path.join(root_dir, f))
                                else:
                                    parts = Path(rel_path).parts
                                    top_folder_name = parts[0]
                                    
                                    # '부', '시즌' 등의 그룹핑 폴더인지 확인
                                    p0 = top_folder_name.lower()
                                    is_part_folder = bool(re.search(r'(\d+\s*부|제\s*\d+\s*부|시즌|season|part)', p0))
                                    
                                    # 그룹핑 폴더이고 하위 폴더(권)가 존재하면 한 단계 더 깊이 탐색
                                    if is_part_folder and len(parts) > 1:
                                        top_folder = os.path.join(top_folder_name, parts[1])
                                    else:
                                        top_folder = top_folder_name
                                        
                                    leaf_folders.add(os.path.join(actual_root, top_folder))
                                    
                    if total_extracted_images == 0:
                        raise Exception("이미지 파일이 없거나 압축을 풀 수 없습니다.")

                    deleted_root_images = []
                    if root_images:
                        if leaf_folders:
                            for img_path in root_images:
                                deleted_root_images.append(os.path.basename(img_path))
                                os.remove(img_path)
                                total_extracted_images -= 1 
                        else:
                            # 🌟 [버그 수정 완료] 파일을 Root_Files로 이사시키지 않고, 진짜 폴더(actual_root) 그대로 작업 목록에 추가합니다.
                            leaf_folders.add(actual_root)
                            
                    leaf_folders = sorted(list(leaf_folders), key=natural_keys)
                    target_ext = f".{self.target_format}" if self.target_format != "none" else ".zip"
                    archive_type = '-t7z' if target_ext == '.7z' else '-tzip'

                    total_packed_images = 0
                    pack_tasks = []

                    # 1단계: 각 권/화별 출력 경로 및 7za 명령어 세팅 (실행은 아직 안 함)
                    for v_idx, leaf in enumerate(leaf_folders):
                        if self._is_cancelled: break

                        img_count = sum(1 for r, _, fs in os.walk(leaf) for f in fs if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif')))
                        total_packed_images += img_count

                        if v_idx < len(data['volumes']):
                            vol_info = data['volumes'][v_idx]
                            vol_base = vol_info['new_name']
                            spinoff_folder = vol_info.get('spinoff_folder')
                        else:
                            pad = max(2, len(str(len(leaf_folders))))
                            if self.lang == 'en': vol_base = f"{clean_title} v{v_idx+1:0{pad}d}"
                            else: vol_base = f"{clean_title} {v_idx+1:0{pad}d}권"
                            spinoff_folder = None
                            
                        vol_base = re.sub(r'^[._\-\s]+', '', vol_base)
                        vol_name = f"{vol_base}{target_ext}"
                        
                        rel_path = os.path.relpath(leaf, actual_root)
                        
                        if rel_path == '.' or rel_path == 'Root_Files':
                            out_dir = os.path.join(base_out_dir, spinoff_folder) if spinoff_folder else base_out_dir
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
                                        if not bool(re.search(r'(\d+\s*부|제\s*\d+\s*부|시즌|season|part)', p.lower())):
                                            continue
                                    valid_parts.append(cp if cp else p)
                                    
                            rel_dir = os.path.join(*valid_parts) if valid_parts else ''
                            out_dir = os.path.join(base_out_dir, spinoff_folder) if spinoff_folder else (os.path.join(base_out_dir, rel_dir) if rel_dir else base_out_dir)

                        os.makedirs(out_dir, exist_ok=True)
                        out_filepath = os.path.join(out_dir, vol_name)
                        
                        # 🌟 개선 1: -mx=0 옵션을 추가하여 무압축(Store) 모드로 속도 극대화
                        cmd = [self.seven_z_exe, 'a', out_filepath, os.path.join(leaf, '*'), archive_type, '-mx=0']
                        pack_tasks.append(cmd)
                        current_target_created_zips.append(out_filepath)

                    # 2단계: 스레드풀을 이용한 병렬 패킹 실행
                    if pack_tasks and not self._is_cancelled:
                        def run_7z(command):
                            subprocess.run(command, stdout=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)

                        # 🌟 개선 2: CPU 코어 수에 맞춰 병렬 처리 (디스크 I/O 고려 최대 4개 제한)
                        max_workers = min(4, os.cpu_count() or 2)
                        completed_tasks = 0
                        
                        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                            futures = [executor.submit(run_7z, cmd) for cmd in pack_tasks]
                            
                            for future in concurrent.futures.as_completed(futures):
                                if self._is_cancelled:
                                    executor.shutdown(wait=False, cancel_futures=True)
                                    break
                                    
                                completed_tasks += 1
                                sub_prog = int((idx / total) * 100) + int((completed_tasks / len(pack_tasks)) * (100 / total))
                                self.signals.progress.emit(sub_prog, f"{msg} ({completed_tasks}/{len(pack_tasks)})")

                    shutil.rmtree(temp_base, ignore_errors=True)
                    
                    if not self._is_cancelled:
                        if total_extracted_images != total_packed_images:
                            raise Exception(f"이미지 유실 징후 포착 및 복구! (원본: {total_extracted_images}장 / 압축됨: {total_packed_images}장)")

                        if os.path.exists(original_tmp):
                            os.remove(original_tmp)
                            
                        created_zips.extend(current_target_created_zips)
                        
                        if deleted_root_images:
                            del_msg = f" 🗑️(불필요 커버 {len(deleted_root_images)}개 제거됨)" if self.lang == "ko" else f" 🗑️({len(deleted_root_images)} covers removed)"
                            stats['success'].append(f"{filename}{del_msg}")
                        else:
                            stats['success'].append(filename)
                        
                        try:
                            parent_dir = os.path.dirname(file_path)
                            if os.path.exists(parent_dir) and not os.listdir(parent_dir):
                                os.rmdir(parent_dir)
                        except: pass
                    else:
                        for z in current_target_created_zips:
                            if os.path.exists(z): os.remove(z)
                        if os.path.exists(original_tmp):
                            os.rename(original_tmp, file_path)

                except Exception as e:
                    for z in current_target_created_zips:
                        if os.path.exists(z): os.remove(z)
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
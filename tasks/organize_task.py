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

                # 🌟 [버그 수정 및 안전장치 1] 원본 압축파일 .tmp 피신
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

                    extract_all(original_tmp, temp_base)

                    # 🌟 [유실 방지용 변수] 해제된 원본 전체 이미지 수 카운트
                    total_extracted_images = 0
                    leaf_folders = set()
                    root_images = []

                    for root, dirs, files in os.walk(temp_base):
                        for f in files:
                            if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif')):
                                total_extracted_images += 1
                                leaf_folders.add(root)
                                if root == temp_base:
                                    root_images.append(os.path.join(root, f))
                                    
                    if total_extracted_images == 0:
                        raise Exception("이미지 파일이 없거나 압축을 풀 수 없습니다.")

                    # 🌟 [안전장치 2] 최상위에 흩어진 고아 이미지 영구 삭제 방지 대피소
                    if len(leaf_folders) > 1 and temp_base in leaf_folders:
                        safe_root_dir = os.path.join(temp_base, "Root_Files")
                        os.makedirs(safe_root_dir, exist_ok=True)
                        for img_path in root_images:
                            shutil.move(img_path, os.path.join(safe_root_dir, os.path.basename(img_path)))
                        leaf_folders.remove(temp_base)
                        leaf_folders.add(safe_root_dir)
                        
                    leaf_folders = sorted(list(leaf_folders), key=natural_keys)
                    target_ext = f".{self.target_format}" if self.target_format != "none" else ".zip"
                    archive_type = '-t7z' if target_ext == '.7z' else '-tzip'

                    # 🌟 [유실 방지용 변수] 재압축된 이미지 수 카운트
                    total_packed_images = 0

                    # 🌟 [요청 기능] 총 폴더(파일) 개수의 자릿수만큼 동적 패딩 설정 (최소 2자리 보장)
                    # 예: 폴더가 9개면 len("9")=1 -> max(2,1)=2 (01)
                    # 예: 폴더가 250개면 len("250")=3 -> max(2,3)=3 (001)
                    pad = max(2, len(str(len(leaf_folders))))

                    for v_idx, leaf in enumerate(leaf_folders):
                        if self._is_cancelled: break
                        
                        sub_prog = int((idx / total) * 100) + int((v_idx / len(leaf_folders)) * (100 / total))
                        self.signals.progress.emit(sub_prog, f"{msg} ({v_idx+1}/{len(leaf_folders)})")

                        # 해당 폴더 내 이미지 개수 카운트
                        img_count = len([f for f in os.listdir(leaf) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'))])
                        total_packed_images += img_count

                        if v_idx < len(data['volumes']):
                            vol_base = data['volumes'][v_idx]['new_name']
                        else:
                            # 동적 패딩을 적용하여 파일 이름 생성
                            if self.lang == 'en': vol_base = f"{clean_title} v{v_idx+1:0{pad}d}"
                            else: vol_base = f"{clean_title} {v_idx+1:0{pad}d}권"
                            
                        vol_name = f"{vol_base}{target_ext}"
                        rel_path = os.path.relpath(leaf, temp_base)
                        
                        if rel_path == '.' or rel_path == 'Root_Files':
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
                        
                        # 🌟 [안전장치 3] 중복 파일명으로 덮어쓰기 대참사 원천 차단 (숫자 증가)
                        base_target_path = os.path.join(out_dir, vol_name)
                        target_path = base_target_path
                        base_name, ext = os.path.splitext(vol_name)
                        counter = 1
                        while os.path.exists(target_path):
                            target_path = os.path.join(out_dir, f"{base_name}_{counter}{ext}")
                            counter += 1

                        temp_archive = os.path.join(sys_temp, f"ComicZIP_Done_{safe_id}_{uuid.uuid4().hex[:4]}_{os.path.basename(target_path)}")
                        if os.path.exists(temp_archive): os.remove(temp_archive)
                        
                        subprocess.run([self.seven_z_exe, 'a', archive_type, temp_archive, '*', '-mx=0'], cwd=leaf, stdout=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW, check=True)
                        
                        shutil.move(temp_archive, target_path)
                        current_target_created_zips.append(target_path)

                    shutil.rmtree(temp_base, ignore_errors=True)
                    
                    if not self._is_cancelled:
                        # 🌟 [최종 방어 검증] 풀린 이미지 개수와 다시 묶인 이미지 개수가 다르면 강제 에러!
                        if total_extracted_images != total_packed_images:
                            raise Exception(f"이미지 누락 방지 발동! (원본: {total_extracted_images}장 / 묶임: {total_packed_images}장)")

                        # 검증이 완벽히 끝난 후에만 피신시켜둔 구버전 .tmp 파일 영구 삭제
                        if os.path.exists(original_tmp):
                            os.remove(original_tmp)
                            
                        created_zips.extend(current_target_created_zips)
                        stats['success'].append(filename)
                        try:
                            parent_dir = os.path.dirname(file_path)
                            if os.path.exists(parent_dir) and not os.listdir(parent_dir):
                                os.rmdir(parent_dir)
                        except: pass
                    else:
                        # 🚨 유저가 취소했다면 생성된 거 지우고 .tmp 원상복구
                        for z in current_target_created_zips:
                            if os.path.exists(z): os.remove(z)
                        if os.path.exists(original_tmp):
                            os.rename(original_tmp, file_path)

                except Exception as e:
                    # 🚨 에러가 발생해서 튕겼다면 생성된 거 지우고 .tmp 원상복구! (절대 유실 금지)
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
import os
import shutil
import uuid
import tempfile
import subprocess
import concurrent.futures
from pathlib import Path
from PIL import Image

from config import TOOL_CWEBP, TOOL_PNGQUANT, TOOL_JPEGTRAN

CREATE_NO_WINDOW = 0x08000000

class RenameTask:
    def __init__(self, targets, config, archive_data, i18n_dict, pattern_val, custom_text, start_num, seven_z_exe, signals):
        self.targets = targets
        self.backup_on = config.get("backup_on", False)
        self.flatten_folders = config.get("flatten_folders", False)
        self.webp_conversion = config.get("webp_conversion", False)
        self.target_format = config.get("target_format", "none")
        self.img_quality = config.get("img_quality", 100) # 통합된 압축 품질
        self.max_threads = config.get("max_threads", max(1, os.cpu_count() or 4)) 
        self.lang = config.get("lang", "ko")
        self.pass_skip_meta = config.get("pass_skip_meta", False)
        self.archive_data = archive_data
        self.i18n = i18n_dict
        self.pattern_val = pattern_val
        self.custom_text = custom_text
        self.start_num = start_num 
        self.seven_z_exe = seven_z_exe
        self.signals = signals
        self._is_cancelled = False

    def cancel(self): self._is_cancelled = True

    def generate_new_name(self, index, ext, total_count, stem_name):
        pad = 2 if total_count < 100 else (3 if total_count < 1000 else 4)
        t_patterns = self.i18n[self.lang]["patterns"]
        if self.webp_conversion: ext = ".webp" 
        
        n = self.start_num + index

        if self.pattern_val == t_patterns[1]: 
            if index == 0: return f"Cover{ext}"
            else: return f"Page_{n:0{pad}d}{ext}"
        elif self.pattern_val == t_patterns[2]: 
            safe_stem = stem_name.replace(' ', '_')
            return f"{safe_stem}_{n:0{pad}d}{ext}"
        elif self.pattern_val == t_patterns[3]: 
            safe_stem = stem_name.replace(' ', '_')
            if index == 0: return f"{safe_stem}_Cover{ext}"
            else: return f"{safe_stem}_Page_{n:0{pad}d}{ext}"
        elif self.pattern_val == t_patterns[4]: 
            custom = self.custom_text.strip() or "Custom"
            return f"{custom}_{n:0{pad}d}{ext}"
        else: 
            return f"{n:0{pad}d}{ext}"

    # 🌟 [수정됨] UI에서 넘겨받은 cap_opt, exif_opt 인자 추가
    # 🌟 [수정됨] 모든 이미지 확장자 대응 및 무한 화질 손상 방지 로직
    def _phase1_convert(self, temp_dir, old_n, tmp_n, cap_opt, exif_opt):
        if self._is_cancelled: return None, False
        
        old_path = os.path.join(temp_dir, old_n)
        tmp_path = os.path.join(temp_dir, tmp_n)
        orig_ext = os.path.splitext(old_n)[1].lower()
        
        # 🌟 개선: except 블록에서 참조 오류가 나지 않도록 최상단에서 미리 정의
        actual_tmp = os.path.splitext(tmp_path)[0] + orig_ext 
        
        if not os.path.exists(old_path): return None, False
        os.makedirs(os.path.dirname(tmp_path), exist_ok=True)
        
        orig_size = os.path.getsize(old_path)
        is_already_webp = (orig_ext == '.webp')
        
        needs_processing = (self.webp_conversion and not is_already_webp) or cap_opt or exif_opt
        if not needs_processing:
            os.rename(old_path, actual_tmp)
            return actual_tmp, False

        # 🌟 개선: 투명도를 흰색 배경으로 안전하게 바꿔주는 헬퍼 함수
        def safe_rgb_convert(image):
            if image.mode in ('RGBA', 'LA') or (image.mode == 'P' and 'transparency' in image.info):
                alpha = image.convert('RGBA')
                bg = Image.new('RGBA', alpha.size, (255, 255, 255, 255))
                return Image.alpha_composite(bg, alpha).convert('RGB')
            return image.convert('RGB') if image.mode != 'RGB' else image

        try:
            quality_val = int(self.img_quality)

            # ---------------------------------------------------------
            # 1. WebP 일괄 변환 모드 (WebP가 켜져 있으면 여기서 무조건 끝냄)
            # ---------------------------------------------------------
            if self.webp_conversion and not is_already_webp:
                if TOOL_CWEBP:
                    cmd = [TOOL_CWEBP, old_path, '-q', str(quality_val)]
                    if not exif_opt: cmd.extend(['-metadata', 'all'])
                    cmd.extend(['-o', tmp_path])
                    subprocess.run(cmd, creationflags=CREATE_NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    with Image.open(old_path) as img:
                        # 🌟 WinError 32 방지 및 투명 배경 방어
                        rgb_img = safe_rgb_convert(img)
                        rgb_img.save(tmp_path, 'WEBP', quality=quality_val, method=4)
                
                # 가드: 용량이 더 커졌다면 원본 파일 그대로 반환하고 종료 (Fall-through 방지)
                if os.path.exists(tmp_path) and os.path.getsize(tmp_path) >= orig_size:
                    os.remove(tmp_path)
                    os.rename(old_path, actual_tmp)
                    return actual_tmp, False
                else:
                    os.remove(old_path)
                    return tmp_path, True

            # ---------------------------------------------------------
            # 2. 용량 최적화 모드 (WebP가 꺼져있을 때 각각의 포맷 유지)
            # ---------------------------------------------------------
            if orig_ext == '.png':
                if cap_opt and TOOL_PNGQUANT:
                    cmd = [TOOL_PNGQUANT, '--force', '--quality', f"40-{quality_val}"]
                    if exif_opt: cmd.append('--strip')
                    cmd.extend([old_path, '-o', actual_tmp])
                    subprocess.run(cmd, creationflags=CREATE_NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                # 🌟 개선: Pillow의 살인적인 PNG 최적화 속도를 피하기 위해, 외부 툴이 실패하거나 없을 때 단순 저장만 수행
                if not os.path.exists(actual_tmp) and exif_opt:
                    with Image.open(old_path) as img:
                        img.save(actual_tmp, format='PNG')

            elif orig_ext in ['.jpg', '.jpeg']:
                if quality_val == 100:
                    if (cap_opt or exif_opt) and TOOL_JPEGTRAN:
                        cmd = [TOOL_JPEGTRAN, '-optimize']
                        cmd.extend(['-copy', 'none'] if exif_opt else ['-copy', 'all'])
                        cmd.extend(['-outfile', actual_tmp, old_path])
                        subprocess.run(cmd, creationflags=CREATE_NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    with Image.open(old_path) as img:
                        # 🌟 WinError 32 방지
                        rgb_img = safe_rgb_convert(img)
                        rgb_img.save(actual_tmp, format='JPEG', optimize=True, quality=quality_val)

            # ---------------------------------------------------------
            # 🌟 3. 공통 가드 (결과물이 원본보다 99% 이상 크면 원본 유지)
            # ---------------------------------------------------------
            if os.path.exists(actual_tmp):
                new_size = os.path.getsize(actual_tmp)
                if new_size >= orig_size * 0.99:
                    os.remove(actual_tmp)
                else:
                    if os.path.exists(old_path): os.remove(old_path)
                    return actual_tmp, True

            if not os.path.exists(actual_tmp):
                os.rename(old_path, actual_tmp)
            return actual_tmp, False

        except Exception as e:
            # 🌟 에러 발생 시 쓰레기 파일 정리 및 안전하게 원본 유지
            if os.path.exists(actual_tmp): os.remove(actual_tmp)
            if os.path.exists(tmp_path): os.remove(tmp_path)
            if os.path.exists(old_path): os.rename(old_path, actual_tmp)
            return actual_tmp, False

    def run(self):
        stats = {'success': [], 'skip': [], 'error': []} 
        new_archive_data = {} 
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
                msg = f"[{idx+1}/{total}] 처리 중: {filename}" if self.lang == "ko" else f"[{idx+1}/{total}] Processing: {filename}"
                self.signals.progress.emit(int((idx / total) * 100), msg)

                try:
                    if self.backup_on:
                        bak_dir = os.path.join(os.path.dirname(file_path), 'bak')
                        os.makedirs(bak_dir, exist_ok=True)
                        shutil.copy2(file_path, os.path.join(bak_dir, filename))

                    data = self.archive_data[file_path]
                    
                    # 🌟 [수정됨] UI에서 선택된 옵션값 가져오기
                    cap_opt = data.get('cap_opt', False)
                    exif_opt = data.get('exif_opt', True)
                    
                    entries = data['entries'].copy() 
                    ext_type = data['ext'].lower()
                    
                    tf = str(self.target_format).lower()
                    target_ext = ext_type if tf == 'none' else f".{tf}"
                    archive_type = '-t7z' if target_ext == '.7z' else '-tzip'

                    cover_entry = next((e for e in entries if os.path.basename(e['filename']).lower().startswith('cover')), None)
                    if cover_entry:
                        entries.remove(cover_entry)
                        entries.insert(0, cover_entry)

                    rename_args = []
                    total_count = len(entries)
                    stem_name = Path(file_path).stem

                    has_non_webp = any(not e['original_name'].lower().endswith('.webp') for e in entries)
                    actual_webp_needed = self.webp_conversion and has_non_webp
                    
                    is_flatten_setting = (str(self.flatten_folders).lower() == 'true')
                    is_already_flat = all('/' not in e['filename'] and '\\' not in e['filename'] for e in entries)
                    is_flatten_needed = is_flatten_setting and not is_already_flat

                    for count, entry in enumerate(entries):
                        old_name = entry['original_name']
                        dir_name = os.path.dirname(entry['filename'])
                        ext = os.path.splitext(entry['filename'])[1] or ".jpg" 
                        if self.webp_conversion: ext = ".webp"
                        
                        if self.pattern_val == "__KEEP_NAME__":
                            new_basename = os.path.splitext(os.path.basename(old_name))[0] + ext
                        else:
                            new_basename = self.generate_new_name(count, ext, total_count, stem_name)
                            
                        new_name = new_basename if is_flatten_needed else os.path.join(dir_name, new_basename).replace('\\', '/')

                        safe_old = os.path.normpath(old_name).replace('\\', '/').lower()
                        safe_new = os.path.normpath(new_name).replace('\\', '/').lower()
                        
                        if safe_old != safe_new or actual_webp_needed:
                            rename_args.append((old_name, new_name))

                    format_changed = (target_ext != ext_type)
                    needs_rename = len(rename_args) > 0
                    
                    # 🌟 [수정됨] 색상 최적화나 EXIF 제거가 체크되어 있으면 강제로 압축을 풀어야 함 (must_extract 트리거)
                    must_extract = actual_webp_needed or format_changed or is_flatten_needed or (ext_type not in ['.zip', '.cbz']) or cap_opt or exif_opt

                    if not needs_rename and not must_extract:
                        stats['skip'].append(filename)
                        if self.pass_skip_meta:
                            new_archive_data[file_path] = file_path
                        continue

                    if not must_extract:
                        flat_args = []
                        for old_n, new_n in rename_args: flat_args.extend([old_n, new_n])
                        
                        safe_id = uuid.uuid4().hex[:6]
                        sys_temp = tempfile.gettempdir()
                        temp_rn_archive = os.path.join(sys_temp, f"ComicZIP_RN_{safe_id}_{filename}")
                        shutil.copy2(file_path, temp_rn_archive)
                        
                        rename_success = True
                        for i in range(0, len(flat_args), 40):
                            if self._is_cancelled: break
                            try:
                                res = subprocess.run([self.seven_z_exe, 'rn', temp_rn_archive] + flat_args[i:i + 40], startupinfo=startupinfo, creationflags=CREATE_NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                if res.returncode not in (0, 1):
                                    rename_success = False
                                    break
                            except Exception:
                                rename_success = False
                                break
                                
                        if rename_success and not self._is_cancelled:
                            tmp_backup_path = file_path + ".tmp"
                            if os.path.exists(tmp_backup_path):
                                os.remove(tmp_backup_path)
                            os.rename(file_path, tmp_backup_path)

                            try:
                                shutil.move(temp_rn_archive, file_path)
                                os.remove(tmp_backup_path)
                            except Exception as e:
                                if os.path.exists(file_path):
                                    os.remove(file_path)
                                os.rename(tmp_backup_path, file_path)
                                raise e
                                
                            stats['success'].append(filename)
                            new_archive_data[file_path] = file_path
                        else:
                            if os.path.exists(temp_rn_archive): os.remove(temp_rn_archive)
                            must_extract = True

                    if must_extract and not self._is_cancelled:
                        safe_id = uuid.uuid4().hex[:6]
                        sys_temp = tempfile.gettempdir()
                        temp_dir = os.path.join(sys_temp, f"ComicZIP_{safe_id}_{filename}")
                        
                        if os.path.exists(temp_dir): shutil.rmtree(temp_dir, ignore_errors=True)
                        os.makedirs(temp_dir, exist_ok=True)
                        
                        res_x = subprocess.run([self.seven_z_exe, 'x', str(file_path), f'-o{temp_dir}', '-y'], startupinfo=startupinfo, creationflags=CREATE_NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        if res_x.returncode not in (0, 1):
                            raise Exception(f"7-Zip Extraction Error (Code: {res_x.returncode})")
                        
                        # rename_args가 없는 경우(단순 EXIF제거 등)를 위해 temp_rename_mapping을 전체 파일 기준으로 갱신
                        temp_rename_mapping = []
                        if rename_args:
                            for old_n, new_n in rename_args:
                                tmp_n = old_n + ".rn." + uuid.uuid4().hex[:8] + ".tmp"
                                temp_rename_mapping.append((old_n, tmp_n, new_n))
                        else:
                            for entry in entries:
                                old_n = entry['original_name']
                                tmp_n = old_n + ".rn." + uuid.uuid4().hex[:8] + ".tmp"
                                temp_rename_mapping.append((old_n, tmp_n, old_n))

                        actual_tmp_results = {}
                        
                        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_threads) as executor:
                            # 🌟 [수정됨] 스레드 풀에 cap_opt와 exif_opt 인자 전달
                            future_to_args = {executor.submit(self._phase1_convert, temp_dir, old_n, tmp_n, cap_opt, exif_opt): (tmp_n, new_n, old_n) for old_n, tmp_n, new_n in temp_rename_mapping}
                            for i, future in enumerate(concurrent.futures.as_completed(future_to_args)):
                                if self._is_cancelled: break 
                                tmp_n, new_n, old_n = future_to_args[future]
                                try:
                                    res = future.result()
                                    if res and res[0]:
                                        actual_tmp_results[tmp_n] = res 
                                except: pass
                                
                                if i % max(1, len(temp_rename_mapping) // 20) == 0:
                                    p_msg = f"Converting ({self.max_threads} Threads): {filename}" if self.lang == "en" else f"다중 코어 변환 중 ({self.max_threads} 스레드): {filename}"
                                    self.signals.progress.emit(int((idx / total) * 100) + int((i / len(temp_rename_mapping)) * (100 / total)), p_msg)

                        if not self._is_cancelled:
                            for old_n, tmp_n, new_n in temp_rename_mapping:
                                res = actual_tmp_results.get(tmp_n)
                                if not res: continue
                                actual_tmp, converted = res
                                
                                new_path = os.path.join(temp_dir, new_n)
                                os.makedirs(os.path.dirname(new_path), exist_ok=True)
                                
                                # WebP 변환 옵션이 켜져 있으나, 원본이 이미 webp였거나 변환되지 않은 경우 처리
                                if self.webp_conversion and not converted and not old_n.lower().endswith('.webp'):
                                    old_ext = os.path.splitext(old_n)[1]
                                    new_path = os.path.splitext(new_path)[0] + old_ext
                                    
                                if os.path.exists(new_path):
                                    os.remove(new_path)
                                os.rename(actual_tmp, new_path)

                        if self._is_cancelled:
                            shutil.rmtree(temp_dir, ignore_errors=True)
                            break

                        if self.flatten_folders:
                            for dirpath, dirnames, filenames in os.walk(temp_dir, topdown=False):
                                for d in dirnames:
                                    try: os.rmdir(os.path.join(dirpath, d))
                                    except: pass

                        self.signals.progress.emit(int(((idx + 0.9) / total) * 100), f"Re-archiving: {filename}")
                                
                        target_final_path = str(Path(file_path).with_suffix(target_ext))
                        temp_archive = os.path.join(sys_temp, f"ComicZIP_Done_{safe_id}_{filename}{target_ext}")
                        
                        if os.path.exists(temp_archive): os.remove(temp_archive)
                        
                        res_a = subprocess.run([self.seven_z_exe, 'a', archive_type, temp_archive, '*', '-mx=0'], cwd=temp_dir, startupinfo=startupinfo, creationflags=CREATE_NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        if res_a.returncode not in (0, 1):
                            raise Exception(f"7-Zip Archiving Error (Code: {res_a.returncode})")
                            
                        shutil.rmtree(temp_dir, ignore_errors=True)
                        
                        tmp_backup_path = file_path + ".tmp"
                        if os.path.exists(tmp_backup_path):
                            os.remove(tmp_backup_path)
                        os.rename(file_path, tmp_backup_path)
                        
                        try:
                            if os.path.exists(target_final_path):
                                os.remove(target_final_path)
                            
                            shutil.move(temp_archive, target_final_path)
                            os.remove(tmp_backup_path)
                        except Exception as e:
                            if os.path.exists(target_final_path):
                                os.remove(target_final_path)
                            os.rename(tmp_backup_path, file_path) 
                            raise e
                                
                        stats['success'].append(filename)
                        new_archive_data[file_path] = target_final_path 

                except Exception as e:
                    stats['error'].append(f"{filename} - {str(e)}")

            if self._is_cancelled:
                self.signals.progress.emit(0, "Cancelled" if self.lang == "en" else "작업 중단됨")
            else:
                self.signals.progress.emit(100, "Done!" if self.lang == "en" else "작업 완료!")
                
            self.signals.rename_done.emit(stats, new_archive_data, self._is_cancelled)

        except Exception as e:
            self.signals.progress.emit(100, f"Critical Error: {e}")
            stats['error'].append(str(e))
            self.signals.rename_done.emit(stats, new_archive_data, True)
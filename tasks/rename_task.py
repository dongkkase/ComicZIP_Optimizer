import os
import shutil
import uuid
import tempfile
import subprocess
import concurrent.futures
from pathlib import Path
from PIL import Image

CREATE_NO_WINDOW = 0x08000000

class RenameTask:
    def __init__(self, targets, config, archive_data, i18n_dict, pattern_val, custom_text, seven_z_exe, signals):
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
        self.signals = signals
        self._is_cancelled = False

    def cancel(self): self._is_cancelled = True

    def generate_new_name(self, index, ext, total_count, stem_name):
        pad = 2 if total_count < 100 else (3 if total_count < 1000 else 4)
        t_patterns = self.i18n[self.lang]["patterns"]
        if self.webp_conversion: ext = ".webp" 

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
            custom = self.custom_text.strip() or "Custom"
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
                    if img.mode not in ('RGB', 'RGBA'): img = img.convert('RGBA')
                    temp_save_path = new_path + ".tmp"
                    if self.webp_quality == 100: img.save(temp_save_path, 'WEBP', lossless=True, method=4)
                    else: img.save(temp_save_path, 'WEBP', quality=self.webp_quality, method=4)
                os.remove(old_path)
                os.rename(temp_save_path, new_path)
            except:
                old_ext = os.path.splitext(old_n)[1]
                os.rename(old_path, os.path.splitext(new_path)[0] + old_ext) 
        else:
            os.rename(old_path, new_path)
        return True

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
                    entries = data['entries'].copy() 
                    ext_type = data['ext'].lower()
                    target_ext = ext_type if self.target_format == 'none' else f".{self.target_format}"
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

                    for count, entry in enumerate(entries):
                        old_name = entry['original_name']
                        dir_name = os.path.dirname(entry['filename'])
                        ext = os.path.splitext(entry['filename'])[1] or ".jpg" 
                        if self.webp_conversion: ext = ".webp"
                        
                        # 🌟 원본 파일명을 그대로 유지할 때의 처리
                        if self.pattern_val == "__KEEP_NAME__":
                            new_basename = os.path.splitext(os.path.basename(old_name))[0] + ext
                        else:
                            new_basename = self.generate_new_name(count, ext, total_count, stem_name)
                            
                        new_name = new_basename if self.flatten_folders else os.path.join(dir_name, new_basename).replace('\\', '/')

                        if old_name != new_name or actual_webp_needed:
                            rename_args.append((old_name, new_name))

                    format_changed = (target_ext != ext_type)
                    needs_rename = len(rename_args) > 0
                    must_extract = actual_webp_needed or format_changed or self.flatten_folders or (ext_type not in ['.zip', '.cbz'])

                    if not needs_rename and not must_extract:
                        stats['skip'].append(filename)
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
                                # 🌟 파이썬 zipfile 모듈 수정으로 인해 7z에서 발생하는 Warning(코드 1)을 무시하도록 수정
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
                        
                        # 🌟 7z Warning(코드 1) 무시 처리 적용
                        res_x = subprocess.run([self.seven_z_exe, 'x', str(file_path), f'-o{temp_dir}', '-y'], startupinfo=startupinfo, creationflags=CREATE_NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        if res_x.returncode not in (0, 1):
                            raise Exception(f"7-Zip Extraction Error (Code: {res_x.returncode})")
                        
                        if rename_args:
                            with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_threads) as executor:
                                futures = [executor.submit(self._convert_single_image, temp_dir, old_n, new_n) for old_n, new_n in rename_args]
                                for i, future in enumerate(concurrent.futures.as_completed(futures)):
                                    if self._is_cancelled: break 
                                    if i % max(1, len(rename_args) // 20) == 0:
                                        p_msg = f"Converting ({self.max_threads} Threads): {filename}" if self.lang == "en" else f"다중 코어 변환 중 ({self.max_threads} 스레드): {filename}"
                                        self.signals.progress.emit(int((idx / total) * 100) + int((i / len(rename_args)) * (100 / total)), p_msg)

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
                        
                        # 🌟 7z Warning(코드 1) 무시 처리 적용
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
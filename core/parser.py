import re
import difflib
from pathlib import Path

def clean_display_title(text):
    cleaned = str(text)
    cleaned = re.sub(r'[\[\(](번외편?|외전|스핀오프|특별편?|단편|합본)[\]\)]', r' \1 ', cleaned) 
    cleaned = re.sub(r'[\[\(].*?[\]\)]', ' ', cleaned) 
    cleaned = re.sub(r'\.(zip|cbz|cbr|rar|7z)$', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\d{4}-\d{2}-\d{2}', '', cleaned)
    cleaned = re.sub(r'\d{4}년\s*\d{1,2}월\s*\d{1,2}일', '', cleaned)
    cleaned = re.sub(r'업로드\s*$', '', cleaned)
    cleaned = re.sub(r'\+\s*\d+\s*$', '', cleaned)
    cleaned = re.sub(r'(?:\s|^)[가-힣a-zA-Z]+\s*(?:원작|그림|지음|글|작화|스토리|번역)(?=\s|$)', ' ', cleaned)
    cleaned = re.sub(r'\d{3,4}\s*px', ' ', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\d+(?:\.\d+)?\s*[~-]\s*\d+(?:\.\d+)?\s*(?:권|화|장|편|부)?', ' ', cleaned)
    cleaned = re.sub(r'\d+(?:\.\d+)?\s*(?:권|화|장|편|부)', ' ', cleaned)
    cleaned = re.sub(r'[-_+,]+', ' ', cleaned)
    return re.sub(r'\s+', ' ', cleaned).strip()

def extract_core_title(text):
    cleaned = clean_display_title(text)
    delimiter_regex = re.compile(r'(\d{3,4}\s*px|\d+\s*(?:권|화|부(?!터))?\s*[~-]\s*\d+|\d+\s*(?:권|화|부(?!터)|화씩)|완결|\s완(\s|$))', re.IGNORECASE)
    match = delimiter_regex.search(cleaned)
    if match and match.start() > 0:
        cleaned = cleaned[:match.start()]
        
    cleaned = re.sub(r'e-?book|e북|完', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'지원\s사격|지원사격|완결은\s무료', '', cleaned)
    cleaned = re.sub(r'\s외\s\d+편', '', cleaned)
    cleaned = re.sub(r'19\)|19금|19\+|15\)|15금|15\+|N새글|고화질|저화질|무료|워터마크없음|워터마크|고화질판|저화질판|단권|연재본|화질보정|확인불가', '', cleaned)
    cleaned = re.sub(r'스캔 단면|스캔단면|스캔 양면|스캔양면|스캔본|스캔판|단편 만화|단편만화|단편|단행본', '', cleaned)
    cleaned = re.sub(r'번외편?|외전|스핀오프|특별편?|합본', '', cleaned)
    cleaned = re.sub(r'권\~', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\d+\s*[~-]\s*\d+', ' ', cleaned)
    cleaned = re.sub(r'[：:—\-\/,]', ' ', cleaned)
    cleaned = re.sub(r'\d+\s*(?:권|화)', ' ', cleaned)
    cleaned = re.sub(r'완결[!?.~]*', ' ', cleaned)
    cleaned = re.sub(r'\s+(완|화|권)[!?.~]*(?=\s|$)', ' ', cleaned)
    cleaned = re.sub(r'\<\s\>', '', cleaned)
    cleaned = re.sub(r'[-_+]+', ' ', cleaned)
    return re.sub(r'\s+', ' ', cleaned).strip()

def get_similarity(a, b):
    a_comp = re.sub(r'[a-zA-Z]', '', re.sub(r'[\[\(].*?[\]\)]', '', a)).replace(" ", "")
    b_comp = re.sub(r'[a-zA-Z]', '', re.sub(r'[\[\(].*?[\]\)]', '', b)).replace(" ", "")
    if not a_comp or not b_comp:
        a_comp = a.replace(" ", "")
        b_comp = b.replace(" ", "")
    if not a_comp or not b_comp: return 0.0
    return difflib.SequenceMatcher(None, a_comp, b_comp).ratio()

def is_garbage_folder_name(text):
    text_lower = text.lower()
    if 'gigafile' in text_lower or 'down' in text_lower: return True
    if len(text) > 20 and bool(re.match(r'^[a-zA-Z0-9\-_]+$', text)): return True
    if len(text) > 15 and bool(re.match(r'^[a-fA-F0-9\-_]+$', text)): return True
    if bool(re.match(r'^\d+$', re.sub(r'[\[\(].*?[\]\)]', '', text).strip())): return True
    return False

def resolve_titles(filepath, inner_name=""):
    p = Path(filepath)
    file_stem = p.stem
    parent_name = p.parent.name
    grandparent_name = p.parents[1].name if len(p.parents) > 1 else ""
    
    file_disp = clean_display_title(file_stem)
    file_core = extract_core_title(file_stem)
    if not file_core: file_core = file_stem
    
    parent_disp = clean_display_title(parent_name)
    parent_core = extract_core_title(parent_name)
    grandparent_disp = clean_display_title(grandparent_name)
    grandparent_core = extract_core_title(grandparent_name)
    
    generic_folders = ['temp', 'downloads', '다운로드', '새 폴더', 'new folder', 'tmp', '새폴더', 'desktop', '바탕 화면', '바탕화면']
    
    if is_garbage_folder_name(file_stem) or not re.search(r'[가-힣a-zA-Z]', file_stem):
        inner_disp, inner_core = "", ""
        if inner_name and not is_garbage_folder_name(inner_name) and re.search(r'[가-힣a-zA-Z]', inner_name):
            inner_disp = clean_display_title(inner_name)
            inner_core = extract_core_title(inner_name)
            
        parent_is_generic = parent_name.lower() in generic_folders or parent_disp.lower() in generic_folders or is_garbage_folder_name(parent_name)
        
        if not parent_is_generic and inner_core:
            if parent_core.replace(" ", "") in inner_core.replace(" ", "") or get_similarity(parent_core, inner_core) >= 0.4:
                return parent_disp, parent_core
            else:
                return inner_disp, inner_core
                
        if inner_core: return inner_disp, inner_core
        if not parent_is_generic: return parent_disp, parent_core
        if grandparent_name and grandparent_name.lower() not in generic_folders and not is_garbage_folder_name(grandparent_name):
            return grandparent_disp, grandparent_core
            
        return "제목없음", "제목없음"
        
    if parent_core and get_similarity(file_core, parent_core) >= 0.5:
        return parent_disp, parent_core
    if grandparent_core and get_similarity(file_core, grandparent_core) >= 0.5:
        return grandparent_disp, grandparent_core
        
    if parent_core and not re.search(r'[가-힣a-zA-Z]', file_core):
        if is_garbage_folder_name(parent_name) and grandparent_name:
            return grandparent_disp, grandparent_core
        return parent_disp, parent_core
        
    return file_disp, file_core

def fix_encoding(text):
    try:
        # UTF-8이 CP949로 잘못 읽힌 경우 복구
        return text.encode('cp949').decode('utf-8')
    except UnicodeError:
        try:
            # CP437이 CP949로 잘못 읽힌 경우 (Zip 기본) 복구
            return text.encode('cp437').decode('cp949')
        except UnicodeError:
            return text

def format_leaf_name(parent_core, leaf_name, index, total_items, lang='ko', prevalent_unit='권'):
    pad = max(2, len(str(total_items)))
    leaf_clean = re.sub(r'\.(zip|cbz|cbr|rar|7z)$', '', str(leaf_name), flags=re.IGNORECASE).strip()
    
    vol_match = re.search(r'(?:제|v|vol\.?\s*)?(\d+(?:\.\d+)?(?:[~-]\d+(?:\.\d+)?)?)\s*(권|화|장|편|부)?', leaf_clean, re.IGNORECASE)
    
    target_num = vol_match.group(1) if vol_match else None
    target_unit = vol_match.group(2) if vol_match else None

    if not target_num:
        nums = re.findall(r'\d+(?:\.\d+)?', re.sub(r'[\[\(].*?[\]\)]', '', leaf_clean))
        target_num = nums[-1] if nums else str(index + 1)
            
    if not target_unit:
        target_unit = prevalent_unit if prevalent_unit else ('권' if lang == 'ko' else 'v')
        
    rem_num_str = target_num
    if '-' in rem_num_str and '~' not in rem_num_str:
        # 🌟 22-1화 -> 22.1화
        parts = rem_num_str.split('-')
        padded_num = f"{parts[0].strip().zfill(pad)}.{parts[1].strip()}"
        unit_str = f"{padded_num}{target_unit}"
    elif '~' in rem_num_str:
        # 🌟 004~009화 -> 004화 ~ 009화
        parts = rem_num_str.split('~')
        unit_str = f"{parts[0].strip().zfill(pad)}{target_unit} ~ {parts[1].strip().zfill(pad)}{target_unit}"
    else:
        padded_num = f"{rem_num_str.split('.')[0].zfill(pad)}.{rem_num_str.split('.')[1]}" if '.' in rem_num_str else rem_num_str.zfill(pad)
        unit_str = f"{padded_num}{target_unit}" if lang == 'ko' else f"v{padded_num}"

    base_name = re.sub(r'^[._\-\s]+', '', parent_core)
    return f"{base_name} {unit_str}".strip()
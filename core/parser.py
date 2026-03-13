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
    a_comp = a.replace(" ", "")
    b_comp = b.replace(" ", "")
    if not a_comp or not b_comp: return 0.0
    return difflib.SequenceMatcher(None, a_comp, b_comp).ratio()

def is_garbage_folder_name(text):
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
        
        if inner_name and not is_garbage_folder_name(inner_name) and re.search(r'[가-힣a-zA-Z]', inner_name):
            inner_disp = clean_display_title(inner_name)
            inner_core = extract_core_title(inner_name)
            return inner_disp if inner_disp else inner_name, inner_core if inner_core else inner_name
            
        if parent_name.lower() in generic_folders or parent_disp.lower() in generic_folders:
            if grandparent_name and grandparent_name.lower() not in generic_folders and not is_garbage_folder_name(grandparent_name):
                return grandparent_disp, grandparent_core
            return "제목없음", "제목없음"
            
        if is_garbage_folder_name(parent_name) and grandparent_name:
            return grandparent_disp if grandparent_disp else parent_disp, grandparent_core if grandparent_core else parent_core
            
        return parent_disp if parent_disp else file_disp, parent_core if parent_core else file_core
        
    if parent_core and get_similarity(file_core, parent_core) >= 0.5:
        return parent_disp, parent_core
    if grandparent_core and get_similarity(file_core, grandparent_core) >= 0.5:
        return grandparent_disp, grandparent_core
        
    if parent_core and not re.search(r'[가-힣a-zA-Z]', file_core):
        if is_garbage_folder_name(parent_name) and grandparent_name:
            return grandparent_disp, grandparent_core
        return parent_disp, parent_core
        
    return file_disp, file_core

def format_leaf_name(parent_core, leaf_name, index, total_items, lang='ko'):
    pad = 2 if total_items < 100 else (3 if total_items < 1000 else 4)
    leaf_clean = re.sub(r'\.(zip|cbz|cbr|rar|7z)$', '', str(leaf_name), flags=re.IGNORECASE).strip()
    
    is_hash = len(leaf_clean) > 25 and bool(re.match(r'^[a-fA-F0-9\-_]+$', leaf_clean))
    if is_hash or not re.search(r'[가-힣a-zA-Z]', leaf_clean):
        nums = re.findall(r'\d+(?:\.\d+)?', leaf_clean)
        if nums and not is_hash:
            num_val = nums[-1]
            num_str = f"{num_val.split('.')[0].zfill(pad)}.{num_val.split('.')[1]}" if '.' in num_val else num_val.zfill(pad)
        else:
            num_str = f"{index+1:0{pad}d}"
            
        base_num = re.sub(r'\D', '', parent_core)
        rem_num = re.sub(r'\D', '', num_str)
        if base_num and base_num == rem_num and not re.search(r'[가-힣a-zA-Z]', parent_core):
            if lang == 'en': return f"v{num_str}"
            else: return f"{num_str}권"
            
        if lang == 'en': return f"{parent_core} v{num_str}".strip()
        else: return f"{parent_core} {num_str}권".strip()

    child_core = extract_core_title(leaf_clean)
    if child_core:
        safe_core = "".join([re.escape(c) + r'[\s\-_+,:.]*' for c in child_core.replace(" ", "")])
        remainder = re.sub(safe_core, '', leaf_clean, flags=re.IGNORECASE).strip()
    else: remainder = leaf_clean
        
    remainder = re.sub(r'\d+(?:\.\d+)?\s*[~-]\s*\d+(?:\.\d+)?\s*(?:권|화|장|편|부)?', '', remainder).strip()
    remainder = re.sub(r'[\[\(].*?[\]\)]', '', remainder).strip()
    remainder = re.sub(r'^[-_+,]+|[-_+,]+$', '', remainder).strip()
    
    if not remainder:
        nums = re.findall(r'\d+(?:\.\d+)?', leaf_clean)
        if nums:
            num_val = nums[-1]
            num_str = f"{num_val.split('.')[0].zfill(pad)}.{num_val.split('.')[1]}" if '.' in num_val else num_val.zfill(pad)
        else:
            num_str = f"{index+1:0{pad}d}"
        if lang == 'en': remainder = f"v{num_str}"
        else: remainder = f"{num_str}권"
    else:
        if lang == 'en':
            if re.search(r'프롤로그|prologue', remainder, re.IGNORECASE): return f"{parent_core} Prologue"
            if re.search(r'에필로그|epilogue', remainder, re.IGNORECASE): return f"{parent_core} Epilogue"
            remainder = re.sub(r'외전\s*(\d+)?', lambda m: f"Side Story{m.group(1).zfill(2) if m.group(1) else '01'}", remainder)
            remainder = re.sub(r'특별편\s*(\d+)?', lambda m: f"Special{m.group(1).zfill(2) if m.group(1) else '01'}", remainder)
            remainder = re.sub(r'(\d+(?:\.\d+)?(?:[~-]\d+(?:\.\d+)?)?)\s*권', lambda m: f"v{m.group(1).zfill(2)}", remainder)
            remainder = re.sub(r'(\d+(?:\.\d+)?(?:[~-]\d+(?:\.\d+)?)?)\s*[화장]', lambda m: f"c{m.group(1).zfill(pad)}", remainder)
            remainder = re.sub(r'(\d+(?:\.\d+)?(?:[~-]\d+(?:\.\d+)?)?)\s*[편부]', lambda m: f"Part {m.group(1).zfill(2)}", remainder)
            remainder = re.sub(r'완전판?', 'Complete Edition', remainder)
            remainder = re.sub(r'신장판?', 'Deluxe Edition', remainder)
            remainder = re.sub(r'개정판?', 'Revised Edition', remainder)
            if re.search(r'\d', remainder) and not re.search(r'(v|c|Part|Side|Special)', remainder, re.IGNORECASE):
                if re.match(r'^\d+(?:\.\d+)?(?:[~-]\d+(?:\.\d+)?)?$', remainder):
                    remainder = f"v{remainder.zfill(2)}"
                else:
                    remainder = re.sub(r'(\d+(?:\.\d+)?(?:[~-]\d+(?:\.\d+)?)?)', lambda m: f"v{m.group(1).zfill(2)}", remainder, count=1)
        else:
            if re.search(r'프롤로그|prologue', remainder, re.IGNORECASE): return f"{parent_core} 프롤로그"
            if re.search(r'에필로그|epilogue', remainder, re.IGNORECASE): return f"{parent_core} 에필로그"
            if re.search(r'\d', remainder) and not re.search(r'(권|화|장|편|부|외전|특별편)', remainder):
                remainder = re.sub(r'(\d+)\s*\.\s*(\d+)', r'\1.\2', remainder)
                remainder = re.sub(r'(\d+(?:\.\d+)?)', r'\1권', remainder, count=1)
            else:
                remainder = re.sub(r'(\d+)\s*\.\s*(\d+)', r'\1.\2', remainder)
            
    has_text = re.search(r'[가-힣a-zA-Z]', child_core)
    
    parent_text = re.sub(r'(?:[\s\-_]+)?0*\d+(?:\.\d+)?$', '', parent_core).strip()
    child_text = re.sub(r'(?:[\s\-_]+)?0*\d+(?:\.\d+)?$', '', child_core).strip()
    
    if child_core and parent_core != child_core and parent_text == child_text and parent_text:
        base_name = parent_text
    elif not has_text or (child_core and get_similarity(child_core, parent_core) >= 0.5):
        base_name = parent_core
    else:
        base_name = child_core if child_core else parent_core
        
    rem_num_match = re.search(r'\d+(?:\.\d+)?', remainder)
    if rem_num_match:
        rem_num_str = rem_num_match.group(0)
        if '.' in rem_num_str:
            val_str = str(float(rem_num_str))
            val_str = val_str.rstrip('0').rstrip('.') if '.' in val_str else val_str
        else:
            val_str = str(int(rem_num_str))
            
        pattern = r'(.*?)(?:[\s\-_]+)?0*' + re.escape(val_str) + r'(?:\.0+)?$'
        match = re.search(pattern, base_name)
        
        if match:
            base_name_candidate = match.group(1).strip()
            if base_name_candidate:
                base_name = base_name_candidate
            elif not re.search(r'[가-힣a-zA-Z]', base_name):
                return remainder.strip()
                
    return f"{base_name} {remainder}".strip()
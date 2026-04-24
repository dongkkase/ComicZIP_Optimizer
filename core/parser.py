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

def format_leaf_name(parent_core, leaf_name, index, total_items, lang='ko', force_unit=None):
    pad = max(2, len(str(total_items)))
    leaf_clean = re.sub(r'\.(zip|cbz|cbr|rar|7z)$', '', str(leaf_name), flags=re.IGNORECASE).strip()
    needs_warning = False

    # ── 패턴 4: `20-3 [20.5화]` 형태 ──
    bracket_ch = re.search(r'(\d+(?:\.\d+)?)\s*[-]\s*(\d+)\s*\[(\d+(?:\.\d+)?)화\]', leaf_clean)
    if bracket_ch:
        a_int, a_dec, b = bracket_ch.group(1), bracket_ch.group(2), bracket_ch.group(3)
        left = f"{a_int}.{a_dec}화"
        right = f"{b}화"
        base = re.sub(r'^[._\-\s]+', '', parent_core)
        return f"{base} {left} ~ {right}", False

    # ── 패턴 3: `07-1화` 형태 (숫자-숫자화) ──
    dash_ch = re.search(r'^(\d+)-(\d+)화$', leaf_clean.strip())
    if dash_ch:
        result_num = f"{dash_ch.group(1)}.{dash_ch.group(2)}화"
        base = re.sub(r'^[._\-\s]+', '', parent_core)
        return f"{base} {result_num}", False

    # ── 패턴 2: `004~009화` 범위 형태 ──
    range_ch = re.search(r'(\d+(?:\.\d+)?)\s*[~]\s*(\d+(?:\.\d+)?)\s*(화|권|장|편|부)?', leaf_clean)
    if range_ch:
        unit = range_ch.group(3) or (force_unit if force_unit else '권')
        start_p = range_ch.group(1).zfill(pad)
        end_p = range_ch.group(2).zfill(pad)
        base = re.sub(r'^[._\-\s]+', '', parent_core)
        return f"{base} {start_p}~{end_p}{unit}", False

    def pad_match(val):
        if '~' in val or '-' in val:
            sep = '~' if '~' in val else '-'
            parts = val.split(sep)
            return f"{parts[0].strip().zfill(pad)}{sep}{parts[1].strip().zfill(pad)}"
        if '.' in val:
            return f"{val.split('.')[0].zfill(pad)}.{val.split('.')[1]}"
        return val.zfill(pad)

    is_hash = len(leaf_clean) > 25 and bool(re.match(r'^[a-fA-F0-9\-_]+$', leaf_clean))
    if is_hash or not re.search(r'[가-힣a-zA-Z]', leaf_clean):
        clean_for_nums = re.sub(r'[\[\(].*?[\]\)]', '', leaf_clean)
        nums = re.findall(r'\d+(?:\.\d+)?', clean_for_nums)
        if nums and not is_hash:
            target_num = nums[-1]
        else:
            target_num = str(index + 1)
        padded_num = pad_match(target_num)
        base = re.sub(r'^[._\-\s]+', '', parent_core)

        # force_unit 적용 (화 단위 강제)
        unit = force_unit if force_unit else ('v' if lang == 'en' else '권')
        if lang == 'en' and not force_unit:
            return f"{base} v{padded_num}", False
        return f"{base} {padded_num}{unit}", False

    clean_no_brackets = re.sub(r'[\[\(].*?[\]\)]', '', leaf_clean)
    vol_match = re.search(r'(?:제|v|vol\.?\s*)?(\d+(?:\.\d+)?(?:[~-]\d+(?:\.\d+)?)?)\s*(권|화|장|편|부)', leaf_clean, re.IGNORECASE)

    target_num = None
    target_unit = None
    if vol_match:
        target_num = vol_match.group(1)
        target_unit = vol_match.group(2)
    else:
        nums = re.findall(r'\d+(?:\.\d+)?', clean_no_brackets)
        if nums:
            target_num = nums[-1]
        else:
            all_nums = re.findall(r'\d+(?:\.\d+)?', leaf_clean)
            if all_nums:
                target_num = all_nums[-1]

    # force_unit 적용
    if force_unit and target_unit is None:
        target_unit = force_unit

    # 특수 키워드 (외전 등) → needs_warning
    special_suffix = ""
    if re.search(r'프롤로그|prologue', leaf_clean, re.IGNORECASE):
        special_suffix = " Prologue" if lang == 'en' else " 프롤로그"
    elif re.search(r'에필로그|epilogue', leaf_clean, re.IGNORECASE):
        special_suffix = " Epilogue" if lang == 'en' else " 에필로그"
    elif re.search(r'특별편|special|특장판', leaf_clean, re.IGNORECASE):
        special_suffix = " Special" if lang == 'en' else " 특별편"
    elif re.search(r'외전|side\s*story|번외', leaf_clean, re.IGNORECASE):
        special_suffix = " Side Story" if lang == 'en' else " 외전"
        needs_warning = True
    elif re.search(r'단편|short', leaf_clean, re.IGNORECASE):
        special_suffix = " Short Story" if lang == 'en' else " 단편"
        needs_warning = True
    elif re.search(r'한정판|limited', leaf_clean, re.IGNORECASE):
        special_suffix = " Limited Edition" if lang == 'en' else " 한정판"

    # 책제목과 다른 제목인지 확인 → needs_warning
    if not needs_warning and re.search(r'[가-힣a-zA-Z]', leaf_clean):
        leaf_core = extract_core_title(leaf_clean)
        parent_core_clean = extract_core_title(parent_core)
        if leaf_core and parent_core_clean:
            sim = get_similarity(leaf_core, parent_core_clean)
            if sim < 0.4 and not special_suffix:
                needs_warning = True

    base_name = re.sub(r'^[._\-\s]+', '', parent_core)

    if not target_num:
        if special_suffix:
            return f"{base_name}{special_suffix}", needs_warning
        else:
            target_num = str(index + 1)

    padded_num = pad_match(target_num)

    rem_num_str = target_num
    if '~' in rem_num_str: rem_num_str = rem_num_str.split('~')[0]
    if '-' in rem_num_str: rem_num_str = rem_num_str.split('-')[0]

    if '.' in rem_num_str:
        val_str = str(float(rem_num_str))
        val_str = val_str.rstrip('0').rstrip('.') if '.' in val_str else val_str
    elif rem_num_str.isdigit():
        val_str = str(int(rem_num_str))
    else:
        val_str = rem_num_str

    pattern = r'(.*?)(?:[\s\-_]+)0*' + re.escape(val_str) + r'(?:\.0+)?$'
    match = re.search(pattern, base_name)
    if match:
        base_name_candidate = match.group(1).strip()
        if base_name_candidate:
            base_name = base_name_candidate

    if not target_unit:
        target_unit = force_unit if force_unit else ('권' if lang == 'ko' else 'v')

    unit_str = ""
    if lang == 'en':
        if target_unit == '부': unit_str = f"Part {padded_num}"
        elif target_unit == '화': unit_str = f"Ch {padded_num}"
        else: unit_str = f"v{padded_num}"
    else:
        unit_str = f"{padded_num}{target_unit}" if target_unit in ['권', '화', '장', '편', '부'] else f"{padded_num}권"

    if special_suffix:
        return f"{base_name} {unit_str}{special_suffix}", needs_warning
    else:
        return f"{base_name} {unit_str}", needs_warning
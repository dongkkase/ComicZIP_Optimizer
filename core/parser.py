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
    # 🌟 괄호, 영문 등 모든 잡음 텍스트를 걷어내고 순수 제목(한글 위주)만으로 극한의 유사도 검사
    a_comp = re.sub(r'[a-zA-Z]', '', re.sub(r'[\[\(].*?[\]\)]', '', a)).replace(" ", "")
    b_comp = re.sub(r'[a-zA-Z]', '', re.sub(r'[\[\(].*?[\]\)]', '', b)).replace(" ", "")
    
    if not a_comp or not b_comp:
        a_comp = a.replace(" ", "")
        b_comp = b.replace(" ", "")
        
    if not a_comp or not b_comp: return 0.0
    return difflib.SequenceMatcher(None, a_comp, b_comp).ratio()

def is_garbage_folder_name(text):
    text_lower = text.lower()
    
    # 🌟 [해결 1] gigafile 등 명백한 다운로드 찌꺼기 문자열 원천 차단
    if 'gigafile' in text_lower or 'down' in text_lower: return True
    
    # 🌟 띄어쓰기 없이 영문+숫자가 너무 길게 나열된 경우 해시값으로 간주하여 강력 차단
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
            # 🌟 [해결 2] 부모 폴더명(아름다운 초저녁달)이 정상적이고 자식 이름(아름다운 초저녁달 6)에 포함되어 있다면
            # 군말 없이 깨끗한 부모 폴더명을 최우선 진짜 책 제목으로 확정!
            if parent_core.replace(" ", "") in inner_core.replace(" ", "") or get_similarity(parent_core, inner_core) >= 0.4:
                return parent_disp, parent_core
            else:
                return inner_disp, inner_core
                
        if inner_core:
            return inner_disp, inner_core
            
        if not parent_is_generic:
            return parent_disp, parent_core
            
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

def format_leaf_name(parent_core, leaf_name, index, total_items, lang='ko'):
    # 전체 파일 수에 비례하되 최소 2자리(01, 02)로 패딩 설정
    pad = max(2, len(str(total_items)))
    
    leaf_clean = re.sub(r'\.(zip|cbz|cbr|rar|7z)$', '', str(leaf_name), flags=re.IGNORECASE).strip()
    clean_for_nums = re.sub(r'[\[\(].*?[\]\)]', '', leaf_clean)
    
    # 숫자 패딩을 안전하게 처리해주는 헬퍼 함수
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
        nums = re.findall(r'\d+(?:\.\d+)?', clean_for_nums)
        if nums and not is_hash:
            num_str = pad_match(nums[-1])
        else:
            num_str = f"{index+1:0{pad}d}"
            
        base_num = re.sub(r'\D', '', parent_core)
        rem_num = re.sub(r'\D', '', num_str)
        if base_num and base_num == rem_num and not re.search(r'[가-힣a-zA-Z]', parent_core):
            return f"v{num_str}" if lang == 'en' else f"{num_str}권"
            
        return f"{parent_core} v{num_str}".strip() if lang == 'en' else f"{parent_core} {num_str}권".strip()

    child_core = extract_core_title(leaf_clean)
    
    parent_comp = re.sub(r'[a-zA-Z\[\(].*?[\]\)]', '', parent_core).replace(" ", "").lower()
    child_comp = re.sub(r'[a-zA-Z\[\(].*?[\]\)]', '', child_core).replace(" ", "").lower()
    
    if not parent_comp: parent_comp = parent_core.replace(" ", "").lower()
    if not child_comp: child_comp = child_core.replace(" ", "").lower()

    if parent_comp in child_comp or child_comp in parent_comp or get_similarity(parent_comp, child_comp) > 0.4:
        if child_core:
            safe_core = "".join([re.escape(c) + r'[\s\-_+,:.]*' for c in child_core.replace(" ", "")])
            remainder = re.sub(safe_core, '', leaf_clean, flags=re.IGNORECASE).strip()
        else:
            remainder = re.sub(r'^[가-힣a-zA-Z\s\-_\[\]\(\)]+', '', leaf_clean) 
    else:
        if child_core:
            safe_core = "".join([re.escape(c) + r'[\s\-_+,:.]*' for c in child_core.replace(" ", "")])
            remainder = re.sub(safe_core, '', leaf_clean, flags=re.IGNORECASE).strip()
        else: 
            remainder = leaf_clean
            
    remainder = re.sub(r'\d+(?:\.\d+)?\s*[~-]\s*\d+(?:\.\d+)?\s*(?:권|화|장|편|부)?', '', remainder).strip()
    
    # 🌟 [해결 3] 사용자의 요청대로 (한정판) 같은 괄호 태그 및 불순물을 자비 없이 전부 날려버림
    remainder = re.sub(r'[\[\(].*?[\]\)]', '', remainder).strip()
    remainder = re.sub(r'^[-_+,]+|[-_+,]+$', '', remainder).strip()
    
    nums = re.findall(r'\d+(?:\.\d+)?', clean_for_nums)
    target_num = nums[-1] if nums else str(index + 1)
    padded_num = pad_match(target_num)

    # 불순물을 날리고 남은게 타겟 숫자뿐이거나 비어있다면, 깔끔하게 0패딩 권수만 붙임!
    if not remainder or remainder == target_num or remainder.isdigit():
        remainder = f"v{padded_num}" if lang == 'en' else f"{padded_num}권"
    else:
        if re.search(r'(?<!\d)' + re.escape(target_num) + r'(?!\d)', remainder):
            if lang == 'en':
                remainder = re.sub(r'(?<!\d)' + re.escape(target_num) + r'(?!\d)(?:\s*권|\s*화)?', f"v{padded_num}", remainder, count=1)
            else:
                remainder = re.sub(r'(?<!\d)' + re.escape(target_num) + r'(?!\d)(?:\s*권|\s*화)?', f"{padded_num}권", remainder, count=1)
        else:
            if lang == 'en':
                remainder = f"v{padded_num} {remainder}"
            else:
                remainder = f"{padded_num}권 {remainder}"

        if lang == 'en':
            remainder = re.sub(r'프롤로그|prologue', 'Prologue', remainder, flags=re.IGNORECASE)
            remainder = re.sub(r'에필로그|epilogue', 'Epilogue', remainder, flags=re.IGNORECASE)
            remainder = re.sub(r'외전', 'Side Story', remainder)
            remainder = re.sub(r'특별편', 'Special', remainder)
        else:
            remainder = re.sub(r'prologue', '프롤로그', remainder, flags=re.IGNORECASE)
            remainder = re.sub(r'epilogue', '에필로그', remainder, flags=re.IGNORECASE)

    base_name = parent_core
        
    pattern = r'(.*?)(?:[\s\-_]+)?0*' + re.escape(target_num) + r'(?:\.0+)?$'
    match = re.search(pattern, base_name)
    if match:
        base_name_candidate = match.group(1).strip()
        if base_name_candidate:
            base_name = base_name_candidate
        elif not re.search(r'[가-힣a-zA-Z]', base_name):
            return remainder.strip()
                
    return f"{base_name} {remainder}".strip()
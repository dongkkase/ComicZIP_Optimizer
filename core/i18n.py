from config import CURRENT_VERSION, get_safe_thread_limits

def get_i18n():
    """다국어 및 메타데이터 선택지 딕셔너리를 반환합니다."""
    total_c, safe_c, _ = get_safe_thread_limits()
    
    ko_formats = {
        "Tankobon": "단행본", "Bunkoban": "문고판", "Kanzenban": "완전판",
        "Aizoban": "애장판", "Shinsoban": "신장판", "Omnibus": "합본",
        "Deluxe": "디럭스판", "SpecialEdition": "특별판", "LimitedEdition": "한정판",
        "CollectorEdition": "컬렉터 에디션", "Hardcover": "하드커버",
        "TradePaperback": "트레이드 페이퍼백", "GraphicNovel": "그래픽 노블",
        "Webtoon": "웹툰", "WebComic": "웹코믹", "Digital": "디지털판"
    }
    en_formats = {k: k for k in ko_formats.keys()}

    ko_genres = {
        "Action": "액션", "Adventure": "모험", "Comedy": "코미디", "Drama": "드라마",
        "Fantasy": "판타지", "Sci-Fi": "SF", "Mystery": "미스터리", "Horror": "공포",
        "Thriller": "스릴러", "Psychological": "심리", "Romance": "로맨스",
        "Slice of Life": "일상", "School": "학원", "Sports": "스포츠",
        "Historical": "역사", "Military": "군사", "Crime": "범죄", "Detective": "추리",
        "Supernatural": "초자연", "Magic": "마법", "Isekai": "이세계",
        "Post-Apocalyptic": "포스트 아포칼립스", "Cyberpunk": "사이버펑크", "Mecha": "메카",
        "Martial Arts": "무협", "Samurai": "사무라이", "Ninja": "닌자",
        "Cooking": "요리", "Medical": "의료", "Music": "음악", "Game": "게임",
        "Gambling": "도박", "Survival": "생존", "Tragedy": "비극", "Parody": "패러디",
        "Satire": "풍자"
    }
    en_genres = {k: k for k in ko_genres.keys()}

    ko_tags = {
        "Revenge": "복수", "Tournament": "토너먼트", "Quest": "퀘스트", "Journey": "여행",
        "Investigation": "수사", "Heist": "범죄 작전", "Survival": "생존",
        "Time Travel": "시간 여행", "Time Loop": "타임 루프", "Parallel World": "평행세계",
        "Reincarnation": "환생", "Regression": "회귀", "Possession": "빙의",
        "Anti-Hero": "안티히어로", "Villain Protagonist": "악역 주인공",
        "Genius Protagonist": "천재 주인공", "Strong Protagonist": "먼치킨",
        "Underdog": "약자 성장형", "Chosen One": "선택받은 자", "Mentor": "스승",
        "Rivalry": "라이벌", "Teamwork": "팀워크", "Brotherhood": "의형제",
        "Family": "가족", "Magic System": "마법 체계", "Guild": "길드",
        "Dungeon": "던전", "Academy": "아카데미", "Kingdom": "왕국", "Empire": "제국",
        "Cultivation": "수련", "Martial World": "무림", "Post-Apocalypse": "멸망 세계",
        "Cybernetics": "사이보그", "Space Travel": "우주 여행", "Friendship": "우정",
        "Betrayal": "배신", "Love Triangle": "삼각관계", "Unrequited Love": "짝사랑"
    }
    en_tags = {k: k for k in ko_tags.keys()}

    ko_age = {
        "All Ages": "전체이용가",
        "Kids / Children": "12세 이상 이용가",
        "Young Adult / Teen": "15세 이상 이용가",
        "Older Teen / Mature": "18세(또는 19세) 이상 이용가",
        "Adult / Mature Audiences": "성인 이용가"
    }
    en_age = {
        "All Ages": "All Ages",
        "Kids / Children": "Kids / Children",
        "Young Adult / Teen": "Young Adult / Teen",
        "Older Teen / Mature": "Older Teen / Mature",
        "Adult / Mature Audiences": "Adult / Mature Audiences"
    }

    ko_manga = {
        "No": "일반(No)",
        "Yes": "만화(Yes)",
        "YesAndRightToLeft": "일본식 우→좌(YesAndRightToLeft)"
    }
    en_manga = {
        "No": "No", "Yes": "Yes", "YesAndRightToLeft": "YesAndRightToLeft"
    }

    return {
        "ko": {
            "title": f"ComicZIP Optimizer v{CURRENT_VERSION}",
            "tab1": "압축 파일 구조 정리(평탄화)", "tab2": "내부 파일명 변경", 
            "tab3": "메타데이터 관리", "tab4": "릴리스 노트",
            "cover_preview": "📚 표지 미리보기", "inner_preview": "🖼️ 내부 파일 미리보기",
            "add_folder": "📂 폴더 추가", "add_file": "📄 파일 추가",
            "remove_sel": "🗑️ 선택 삭제", "clear_all": "🧹 전체 비우기",
            "toggle_all": "☑ 전체 선택/해제",
            "settings_btn": "⚙️ 환경 설정", "settings_title": "환경 설정",
            "lang_lbl": "🌐 언어 (Language) :", "format_lbl": "📦 변환 포맷 :",
            "play_sound": "작업 완료 알림음 재생", 
            "backup": "원본 백업 (bak 폴더 생성)",
            "flatten": "폴더 구조 평탄화 (하위 폴더 제거)",
            "flatten_desc": "압축 파일 내의 폴더를 모두 무시하고 이미지를 최상단으로 꺼냅니다.",
            "webp": "모든 이미지를 WebP로 일괄 변환",
            "webp_desc": "모든 이미지를 고효율 WebP 포맷으로 변환하여 확장자 통일성을 보장합니다.",
            "webp_quality": "WebP 품질 (Quality) :", "max_threads": "다중 스레드 (Threads) :",
            "threads_desc": f"⚠️ 수치가 높을수록 변환 속도가 빨라지지만 PC가 느려질 수 있습니다.\n시스템 안정을 위해 전체 {total_c}코어 중 여유분을 남긴 안전 수치({safe_c}코어)까지만 올릴 수 있습니다.",
            "btn_save": "저장", "btn_cancel": "취소", "btn_close": "닫기",
            "btn_continue_tab2": "🚀 내부 파일명 변경 (Tab 2) 이어서 하기",
            "log_title": "상세 작업 결과 로그",
            "pattern_lbl": "💡 파일명 패턴 :",
            "target_lbl": " 대상 압축파일 (ZIP, CBZ, CBR, 7Z 지원) ",
            "inner_lbl": " 내부 파일 리스트 (패턴 실시간 미리보기) ",
            "col_org_name": "작업 대상 및 구조", "col_org_path": "완료 저장 경로 (직접 수정 가능)", "col_org_count": "항목수", "col_org_size": "용량",
            "batch_default": "일괄 기본값", "batch_title": "일괄 책제목",
            "col_name": "파일명 (포맷 변경 반영)", "col_count": "항목 수", "col_size": "용량 (MB)",
            "col_old": "원본 파일명", "col_new": "변경될 파일명", "col_fsize": "크기",
            "drag_drop": "📂 폴더나 파일을 여기로 드래그 앤 드롭하세요",
            "run_btn": "🚀 최적화 실행", "cancel_btn": "🛑 작업 중단",
            "cancel_wait": "⏳ 중단 처리 중...", "status_wait": "대기 중...",
            "no_preview": "미리보기 없음", "no_image": "미리볼 수 없는 이미지입니다.",
            "total_files": "총 {count}개 리스트",
            "format_opts": ["변경없음", "zip", "cbz", "cbr", "7z"],
            "patterns": ["기본 숫자 패딩 (000, 001...)", "영문 도서 스타일 (Cover, Page_001...)",
                         "압축파일명 동기화 (파일명_000...)", "압축파일명 + 도서 (파일명_Cover...) - 추천", "사용자 정의 (직접입력_000...)"],
            
            "meta_formats": ko_formats, "meta_genres": ko_genres, "meta_tags": ko_tags,
            "meta_age": ko_age, "meta_manga": ko_manga,
            
            "t3_empty": "📂 폴더 및 파일을 이 화면으로 드래그 앤 드롭하세요",
            "t3_cover": "표지 미리보기",
            "t3_search_api": "검색 API :", "t3_search_query": "검색어 :",
            "t3_search_ph": "작품 제목을 입력하세요...", "t3_btn_search": "🔍 검색",
            
            "t3_nav_basic": "기본\n정보",
            "t3_nav_crew": "작가 및\n제작진",
            "t3_nav_publish": "출판\n정보",
            "t3_nav_genre": "장르/태그\n등장인물",
            "t3_nav_etc": "기타\n정보",
            
            "t3_btn_prev": "◁ 이전 권",
            "t3_btn_next": "다음 권 ▷",
            "t3_btn_copy_orig": "원본 카피 편집",
            "t3_btn_apply_all": "편집 적용",
            "t3_btn_apply_series": "시리즈 편집 적용",
            "t3_col_orig": "원본", "t3_col_res": "일괄 편집",
            "t3_cb_ph": "선택 시 자동 추가되며, 쉼표(,)로 직접 입력할 수 있습니다.",
            "t3_auto_vol": "자동 권수 입력",
            "t3_auto_chap": "자동 화 입력",
            "t3_auto_pages": "자동 페이지 수 입력",
            "t3_save": "저장", "t3_save_all": "모두 저장",
            
            "t3_tt_copy_orig": "원본의 데이터를 일괄 편집 칸으로 복사합니다.\n(권, 화, 페이지수 제외)",
            "t3_tt_apply_all": "일괄 편집에서 작성된 내용이 원본 값으로 카피됩니다.",
            "t3_tt_apply_series": "일괄 편집에서 작성된 내용이 해당 시리즈의 모든 책의 원본 값으로 카피됩니다.",
            "t3_tt_auto_vol": "해당 시리즈에 포함된 모든 책에서 제목의 권수를 추출하여 숫자만 입력됩니다.",
            "t3_tt_auto_chap": "해당 시리즈에 포함된 모든 책에서 제목의 화를 추출하여 숫자만 입력됩니다.",
            "t3_tt_auto_pages": "해당 시리즈에 포함된 모든 책의 이미지 개수를 추출하여 입력됩니다.",
            "t3_tt_save": "작성된 메타데이터를 comicinfo.xml로 저장합니다.",
            "t3_tt_save_all": "각 책의 메타데이터를 comicinfo.xml로 저장합니다.",
            
            "t3_f_title": "제목", "t3_f_series": "시리즈", "t3_f_sgroup": "시리즈 그룹\n(세계관 묶기 등)",
            "t3_f_count": "전체권수", "t3_f_vol": "권", "t3_f_num": "화", "t3_f_page": "페이지수", "t3_f_sum": "줄거리",
            "t3_f_writer": "작가", "t3_f_pen": "그림 작가", "t3_f_inker": "잉크 작업", "t3_f_color": "채색 작가",
            "t3_f_letter": "글자 작업", "t3_f_cover": "표지 작가", "t3_f_editor": "편집자",
            "t3_f_pub": "출판사", "t3_f_imp": "출판 레이블", "t3_f_web": "웹사이트", "t3_f_format": "포맷",
            "t3_f_year": "년", "t3_f_month": "월", "t3_f_day": "일",
            "t3_f_genre": "장르", "t3_f_tags": "태그", "t3_f_char": "등장인물",
            "t3_f_age": "연령 등급", "t3_f_rate": "커뮤니티 평점", "t3_f_iso": "언어 코드 (ISO)", "t3_f_dir": "읽기 방향",
            
            "t3_msg_sel": "왼쪽 리스트에서 작업할 책을 선택해주세요.",
            "t3_btn_apply_series_tag": "시리즈 전체 일괄 덮어쓰기",
            "t3_msg_applied_series_tag": "입력된 값이 시리즈 내 {count}권에 일괄 적용되었습니다.",
            "t3_msg_applied_char_series": "입력된 등장인물이 시리즈 내 {count}권에 일괄 적용되었습니다.",
            "t3_msg_analyzing": "메타데이터 분석 중...",
            "t3_msg_saving": "저장 중...",
            "t3_msg_no_data_copy": "복사할 일괄 편집 데이터가 없습니다.",
            "t3_msg_applied_series_all": "일괄 편집 결과가 시리즈 내의 모든 책에 일괄 적용되었습니다.",
            "t3_msg_auto_vol_done": "시리즈의 모든 책에 자동 권수가 입력되었습니다.",
            "t3_msg_auto_chap_done": "시리즈의 모든 책에 자동 화가 입력되었습니다.",
            "t3_msg_auto_pages_done": "시리즈의 모든 책에 자동 페이지 수가 입력되었습니다.",
            "t3_msg_save_single_done": "ComicInfo.xml 저장 성공.",
            "t3_msg_save_all_done": "총 {success_count}건 성공, {fail_count}건 실패.",
            "t3_msg_save_all_title": "일괄 저장 완료",
            "t3_msg_save_failed_reason": "실패 사유: {msg}",
            "t3_msg_unsupported_format": "지원되지 않는 포맷",
            "t3_msg_7z_error": "7z 오류",
            "t3_no_data": "(데이터 없음)",
            "msg_done": "완료", "msg_notice": "안내", "msg_failed": "실패", "msg_success": "성공",
            "enter_after_input":"입력 후 Enter...",
        },
        "en": {
            "title": f"ComicZIP Optimizer v{CURRENT_VERSION}",
            "tab1": "Archive Organizer", "tab2": "Inner Renamer", 
            "tab3": "Metadata Management", "tab4": "Release Notes",
            "cover_preview": "📚 Cover Preview", "inner_preview": "🖼️ Inner Preview",
            "add_folder": "📂 Add Folder", "add_file": "📄 Add File",
            "remove_sel": "🗑️ Remove Sel", "clear_all": "🧹 Clear All",
            "toggle_all": "☑ Toggle All",
            "settings_btn": "⚙️ Settings", "settings_title": "Preferences",
            "lang_lbl": "🌐 Language :", "format_lbl": "📦 Output Format :",
            "play_sound": "Play completion sound",  
            "backup": "Backup Original (bak folder)",
            "flatten": "Flatten Folders (Remove Sub-folders)",
            "flatten_desc": "Extracts all images to the root, ignoring folders.",
            "webp": "Convert all images to WebP",
            "webp_desc": "Converts all images strictly to WebP format.",
            "webp_quality": "WebP Quality :", "max_threads": "Multi-threads :",
            "threads_desc": f"⚠️ Higher values increase speed but consume more CPU.\nFor system stability, the maximum is capped at {safe_c} cores (Total: {total_c}).",
            "btn_save": "Save", "btn_cancel": "Cancel", "btn_close": "Close",
            "btn_continue_tab2": "🚀 Continue to Inner Renamer (Tab 2)",
            "log_title": "Detailed Job Log",
            "pattern_lbl": "💡 Naming Pattern :",
            "target_lbl": " Target Archives (ZIP, CBZ, CBR, 7Z) ",
            "inner_lbl": " Inner Files (Real-time Preview) ",
            "col_org_name": "Original Name & Structure", "col_org_path": "Output Save Path", "col_org_count": "Items", "col_org_size": "Size",
            "batch_default": "Batch Default", "batch_title": "Batch Title",
            "col_name": "File Name", "col_count": "Items", "col_size": "Size",
            "col_old": "Original Name", "col_new": "New Name", "col_fsize": "Size",
            "drag_drop": "📂 Drag and drop folders or files here",
            "run_btn": "🚀 Execute Process", "cancel_btn": "🛑 Cancel Process",
            "cancel_wait": "⏳ Cancelling...", "status_wait": "Waiting...",
            "no_preview": "No Preview", "no_image": "Cannot preview this image.",
            "total_files": "Total {count} items",
            "format_opts": ["No Change", "zip", "cbz", "cbr", "7z"],
            "patterns": ["Basic Number Padding (000, 001...)", "English Book Style (Cover, Page_001...)",
                         "Sync with Archive Name (File_000...)", "Archive + Book (File_Cover...) - Recommended", "Custom (Input_000...)"],
            
            "meta_formats": en_formats, "meta_genres": en_genres, "meta_tags": en_tags,
            "meta_age": en_age, "meta_manga": en_manga,

            "t3_empty": "📂 Drag and drop folders or files to this screen",
            "t3_cover": "Cover Preview",
            "t3_search_api": "Search API :", "t3_search_query": "Search :",
            "t3_search_ph": "Enter title to search...", "t3_btn_search": "🔍 Search",
            
            "t3_nav_basic": "Basic\nInfo",
            "t3_nav_crew": "Crew\nInfo",
            "t3_nav_publish": "Publish\nInfo",
            "t3_nav_genre": "Genre/Tags\nCharacters",
            "t3_nav_etc": "Etc\nInfo",
            
            "t3_btn_prev": "◁ Prev Vol",
            "t3_btn_next": "Next Vol ▷",
            "t3_btn_copy_orig": "Copy Original",
            "t3_btn_apply_all": "Apply Edit",
            "t3_btn_apply_series": "Apply Edit to Series",
            "t3_col_orig": "Original", "t3_col_res": "Batch Edit",
            "t3_cb_ph": "Checked items added automatically, or type with commas (,)",
            "t3_auto_vol": "Auto Vol.", "t3_auto_chap": "Auto Chap.", "t3_auto_pages": "Auto Pages",
            "t3_save": "Save", "t3_save_all": "Save All",
            
            "t3_tt_copy_orig": "Copies original data to the batch edit fields.\n(Excludes Vol, Chap, Pages)",
            "t3_tt_apply_all": "Copies the content from the batch edit to the original values.",
            "t3_tt_apply_series": "Copies the content from the batch edit to the original values of all books in the series.",
            "t3_tt_auto_vol": "Extracts the volume number from the titles of all books in the series and inputs only the number.",
            "t3_tt_auto_chap": "Extracts the chapter number from the titles of all books in the series and inputs only the number.",
            "t3_tt_auto_pages": "Extracts and inputs the image count for all books in the series.",
            "t3_tt_save": "Saves the written metadata to comicinfo.xml.",
            "t3_tt_save_all": "Saves the metadata of each book to comicinfo.xml.",
            
            "t3_f_title": "Title", "t3_f_series": "Series", "t3_f_sgroup": "Series Group\n(Universe)",
            "t3_f_count": "Total Vol.", "t3_f_vol": "Volume", "t3_f_num": "Chapter", "t3_f_page": "Page Count", "t3_f_sum": "Summary",
            "t3_f_writer": "Writer", "t3_f_pen": "Penciller", "t3_f_inker": "Inker", "t3_f_color": "Colorist",
            "t3_f_letter": "Letterer", "t3_f_cover": "Cover Artist", "t3_f_editor": "Editor",
            "t3_f_pub": "Publisher", "t3_f_imp": "Imprint", "t3_f_web": "Website", "t3_f_format": "Format",
            "t3_f_year": "Year", "t3_f_month": "Month", "t3_f_day": "Day",
            "t3_f_genre": "Genre", "t3_f_tags": "Tags", "t3_f_char": "Characters",
            "t3_f_age": "Age Rating", "t3_f_rate": "Community Rating", "t3_f_iso": "Language (ISO)", "t3_f_dir": "Reading Dir.",
            
            "t3_msg_sel": "Please select a book from the left list.",
            "t3_btn_apply_series_tag": "Apply to Series",
            "t3_msg_applied_series_tag": "Applied to {count} books in the series.",
            "t3_msg_applied_char_series": "Characters applied to {count} books in the series.",
            "t3_msg_analyzing": "Analyzing metadata...", "t3_msg_saving": "Saving...",
            "t3_msg_no_data_copy": "No batch edit data to copy.",
            "t3_msg_applied_series_all": "Batch edit results applied to all books in the series.",
            "t3_msg_auto_vol_done": "Auto volume applied to all books in the series.",
            "t3_msg_auto_chap_done": "Auto chapter applied to all books in the series.",
            "t3_msg_auto_pages_done": "Auto page count applied to all books in the series.",
            "t3_msg_save_single_done": "Saved ComicInfo.xml successfully.",
            "t3_msg_save_all_done": "{success_count} succeeded, {fail_count} failed.",
            "t3_msg_save_all_title": "Save All Complete",
            "t3_msg_save_failed_reason": "Reason: {msg}",
            "t3_msg_unsupported_format": "Unsupported format", "t3_msg_7z_error": "7z error",
            "t3_no_data": "(No Data)", "msg_done": "Done", "msg_notice": "Notice", "msg_failed": "Failed", "msg_success": "Success",
            "enter_after_input":"Type and press Enter...",
        }
    }
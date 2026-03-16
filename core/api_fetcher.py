import os
import json
import sqlite3
import requests
import re
import urllib.parse
from pathlib import Path
from datetime import datetime

DB_PATH = ".api_cache.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS search_cache (
                api TEXT, query TEXT, results TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (api, query)
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS img_cache (
                url TEXT PRIMARY KEY, 
                data BLOB
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS trans_cache (
                original TEXT PRIMARY KEY, 
                translated TEXT
            )
        ''')
        conn.commit()

init_db()

class MetaApiFetcher:
    
    @staticmethod
    def _translate_ko_to_en(text, api_keys=None):
        if not api_keys: api_keys = {}
        if not re.search(r'[가-힣]', text):
            return text 
            
        ai_enabled = api_keys.get("ai_trans_enabled", False)
        ai_provider = api_keys.get("ai_provider", "Gemini")
        ai_key = api_keys.get("ai_key", "").strip()

        if ai_enabled and ai_key:
            prompt = f"다음 한국어 만화/코믹스 제목을 미국 Comic Vine이나 해외 DB에서 검색하기 가장 좋은 공식 영문 발매명(Official English Title) 딱 1개만 출력해. 부가 설명, 마침표, 특수기호 없이 오직 영어 제목만 출력할 것. 입력: {text}"
            
            try:
                if ai_provider == "OpenAI":
                    url = "https://api.openai.com/v1/chat/completions"
                    headers = {"Authorization": f"Bearer {ai_key}", "Content-Type": "application/json"}
                    payload = {
                        "model": "gpt-4o-mini",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.3
                    }
                    resp = requests.post(url, headers=headers, json=payload, timeout=7)
                    if resp.status_code == 200:
                        res_text = resp.json()["choices"][0]["message"]["content"].strip().strip('"').strip("'")
                        print(f"🧠 [OpenAI 변환] '{text}' -> '{res_text}'")
                        return res_text

                elif ai_provider == "Gemini":
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={ai_key}"
                    headers = {"Content-Type": "application/json"}
                    payload = {
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {"temperature": 0.3}
                    }
                    resp = requests.post(url, headers=headers, json=payload, timeout=7)
                    if resp.status_code == 200:
                        res_text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip().strip('"').strip("'")
                        print(f"🧠 [Gemini 변환] '{text}' -> '{res_text}'")
                        return res_text
            except Exception as e:
                print(f"⚠️ [AI 변환 실패, 일반 번역으로 대체] {e}")

        try:
            url = "https://translate.googleapis.com/translate_a/single"
            params = {"client": "gtx", "sl": "ko", "tl": "en", "dt": "t", "q": text}
            resp = requests.get(url, params=params, timeout=5)
            if resp.status_code == 200:
                translated = resp.json()[0][0][0]
                print(f"🔄 [일반 번역] '{text}' -> '{translated}'")
                return translated
        except: pass
        return text

    @staticmethod
    def search(api_name, query, api_keys=None, page=1):
        if not query: return [], query
        if api_keys is None: api_keys = {}
        
        actual_query = query
        # 🌟 Anilist도 해외 DB이므로 AI 스마트 번역 로직을 동일하게 적용
        if api_name in ["Vine", "Anilist"]:
            actual_query = MetaApiFetcher._translate_ko_to_en(query, api_keys)
            
        cache_query = f"{query}::p{page}"
            
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("SELECT results, updated_at FROM search_cache WHERE api=? AND query=?", (api_name, cache_query))
            row = c.fetchone()
            if row:
                try:
                    updated_at_str = row[1]
                    updated_at = datetime.strptime(updated_at_str, "%Y-%m-%d %H:%M:%S")
                    
                    if (datetime.now() - updated_at).total_seconds() < 604800:
                        print(f"[{api_name}] '{cache_query}' - ⚡ DB 캐시에서 데이터를 불러옵니다. (업데이트: {updated_at_str})")
                        return json.loads(row[0]), actual_query
                    else:
                        print(f"[{api_name}] '{cache_query}' - ⏳ 캐시가 만료되었습니다. 새로 요청합니다.")
                except Exception as e:
                    print(f"Cache Load Error: {e}")
        
        print(f"[{api_name}] '{cache_query}' - 🌐 API 서버로 요청을 보냅니다.")
        results = []
        
        if api_name == "리디북스":
            results = MetaApiFetcher._search_ridibooks(query, page)
        elif api_name == "알라딘":
            ttbkey = api_keys.get("aladin", "")
            results = MetaApiFetcher._search_aladin(query, ttbkey, page)
        elif api_name == "Google Books":
            google_key = api_keys.get("google", "")
            results = MetaApiFetcher._search_google_books(query, google_key, page)
        elif api_name == "Anilist":
            results = MetaApiFetcher._search_anilist(actual_query, page)
        elif api_name == "Vine":
            vine_key = api_keys.get("vine", "")
            results = MetaApiFetcher._search_vine(actual_query, vine_key, page)
            
        if results:
            with sqlite3.connect(DB_PATH) as conn:
                c = conn.cursor()
                c.execute("""
                    INSERT OR REPLACE INTO search_cache (api, query, results, updated_at) 
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """, (api_name, cache_query, json.dumps(results, ensure_ascii=False)))
                conn.commit()
                
        return results, actual_query

    # 🌟 Anilist GraphQL 기반 검색 연동 추가
    @staticmethod
    def _search_anilist(query, page=1):
        url = "https://graphql.anilist.co"
        graphql_query = """
        query ($page: Int, $perPage: Int, $search: String) {
          Page (page: $page, perPage: $perPage) {
            media (search: $search, type: MANGA) {
              title { romaji english native }
              description(asHtml: false)
              coverImage { extraLarge }
              staff { edges { role node { name { full } } } }
              genres
              tags { name }
              volumes
              chapters
              averageScore
              startDate { year month day }
            }
          }
        }
        """
        variables = {
            "search": query,
            "page": page,
            "perPage": 20
        }
        results = []
        try:
            resp = requests.post(url, json={"query": graphql_query, "variables": variables}, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                print(f"[Anilist] API 응답 성공! 파싱된 데이터: {len(data.get('data', {}).get('Page', {}).get('media', []))}개")
                items = data.get("data", {}).get("Page", {}).get("media", [])
                
                for item in items:
                    title_dict = item.get("title", {})
                    title = title_dict.get("english") or title_dict.get("romaji") or title_dict.get("native") or ""
                    loc_series = title_dict.get("native", title)
                    
                    desc = item.get("description", "")
                    if desc: desc = re.sub(r'<[^>]+>', '', desc).strip()
                    
                    cover = item.get("coverImage", {}).get("extraLarge", "")
                    
                    genres = ", ".join(item.get("genres", []))
                    tags = ", ".join([t.get("name", "") for t in item.get("tags", [])])
                    
                    staff_edges = item.get("staff", {}).get("edges", [])
                    writer = []
                    penciller = []
                    for edge in staff_edges:
                        role = edge.get("role", "").lower()
                        name = edge.get("node", {}).get("name", {}).get("full", "")
                        if "story" in role or "writer" in role: writer.append(name)
                        if "art" in role or "illustrator" in role: penciller.append(name)
                        
                    writer_str = ", ".join(writer)
                    penciller_str = ", ".join(penciller)
                    
                    vols = str(item.get("volumes") or "")
                    chaps = str(item.get("chapters") or "")
                    count = vols if vols else chaps
                    
                    score = item.get("averageScore")
                    rating_score = str(score / 10.0) if score else "-"
                    rating_detail = f"⭐ {rating_score} / 10.0" if score else "-"
                    
                    start_date = item.get("startDate", {})
                    y = start_date.get("year"); m = start_date.get("month"); d = start_date.get("day")
                    year = str(y) if y else ""
                    pub_date = f"{y}-{m:02d}-{d:02d}" if y and m and d else year

                    results.append({
                        "Title": title, "Writer": writer_str, "Penciller": penciller_str, "Publisher": "", 
                        "Summary": desc, "Series": title, "Web": "", 
                        "CoverUrl": cover, "Tags": tags, "Genre": genres, 
                        "LocalizedSeries": loc_series,
                        "Count": count, "Rating": rating_detail, "RatingScore": rating_score, "AgeRating": "", 
                        "PubDate": pub_date, "Year": year, 
                        "Volume": "", "Number": "", "Characters": ""
                    })
        except Exception as e:
            print(f"[Anilist] API Error: {e}")
        return results

    # 🌟 Google Books API 검색 연동 추가
    @staticmethod
    def _search_google_books(query, api_key, page=1):
        if not api_key: return []
        url = "https://www.googleapis.com/books/v1/volumes"
        params = {
            "q": query,
            "key": api_key,
            "startIndex": str((page - 1) * 20),
            "maxResults": "20"
        }
        results = []
        try:
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                for item in items:
                    v_info = item.get("volumeInfo", {})
                    title = v_info.get("title", "")
                    authors = ", ".join(v_info.get("authors", []))
                    publisher = v_info.get("publisher", "")
                    pub_date = v_info.get("publishedDate", "")
                    year = pub_date[:4] if pub_date else ""
                    
                    desc = v_info.get("description", "")
                    if desc: desc = re.sub(r'<[^>]+>', '', desc).strip()
                        
                    cover = v_info.get("imageLinks", {}).get("thumbnail", "").replace("http:", "https:")
                    categories = ", ".join(v_info.get("categories", []))
                    page_count = str(v_info.get("pageCount", ""))
                    web_url = v_info.get("infoLink", "")
                    
                    results.append({
                        "Title": title, "Writer": authors, "Publisher": publisher, 
                        "Summary": desc, "Series": title, "Web": web_url, 
                        "CoverUrl": cover, "Tags": categories, "Genre": categories, 
                        "LocalizedSeries": title,
                        "Count": "", "Rating": "-", "RatingScore": "-", "AgeRating": "", 
                        "PubDate": pub_date, "Year": year, 
                        "Volume": "", "Number": "", "Characters": "", "PageCount": page_count
                    })
        except Exception as e:
            print(f"[Google Books] API Error: {e}")
        return results

    @staticmethod
    def _search_vine(query, api_key, page=1):
        if not api_key: return []

        url = "https://comicvine.gamespot.com/api/search/"
        headers = {"User-Agent": "ComicZIP_Optimizer_App/1.0"}
        
        params = {
            "api_key": api_key, "format": "json", "resources": "volume",
            "query": query, "limit": "20",
            "page": str(page) 
        }
        
        results = []
        try:
            response = requests.get(url, params=params, headers=headers, timeout=15)
            if response.status_code == 200:
                data = response.json()
                items = data.get("results", [])
                
                print(f"[Vine] API 응답 성공! 파싱된 데이터: {len(items)}개")
                
                for item in items:
                    title = item.get("name", "")
                    pub_obj = item.get("publisher")
                    publisher = pub_obj.get("name", "") if isinstance(pub_obj, dict) else ""
                    year = str(item.get("start_year", ""))
                    synopsis = item.get("description", "")
                    if synopsis: synopsis = re.sub(r'<[^>]+>', '', synopsis).strip()
                    web_url = item.get("site_detail_url", "")
                    
                    cover_obj = item.get("image", {})
                    cover = cover_obj.get("medium_url", "") if isinstance(cover_obj, dict) else ""
                    count = str(item.get("count_of_issues", ""))

                    results.append({
                        "Title": title, "Writer": "", "Publisher": publisher, 
                        "Summary": synopsis, "Series": title, "Web": web_url, 
                        "CoverUrl": cover, "Tags": "", "Genre": "", 
                        "LocalizedSeries": title,
                        "Count": count, "Rating": "-", "RatingScore": "-", "AgeRating": "", 
                        "PubDate": year, "Year": year, 
                        "Volume": "", "Number": "", "Characters": ""
                    })
            else:
                print(f"[Vine] 에러 발생: HTTP {response.status_code} - {response.text}")
        except Exception as e:
            print(f"[Vine] 통신 중 예외 발생: {e}")
        return results

    @staticmethod
    def _search_aladin(query, ttbkey, page=1):
        if not ttbkey: return []

        url = "http://www.aladin.co.kr/ttb/api/ItemSearch.aspx"
        params = {
            "ttbkey": ttbkey, "Query": query, "QueryType": "Keyword",
            "MaxResults": "20", "start": str(page), "SearchTarget": "Book",
            "output": "js", "Version": "20131101", "Cover": "Big", 
            "OptResult": "categoryId,Story" 
        }
        
        results = []
        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                items = data.get("item", [])
                
                for item in items:
                    title = item.get("title", "")
                    author = item.get("author", "")
                    publisher = item.get("publisher", "")
                    pub_date = item.get("pubDate", "")
                    year = pub_date[:4] if pub_date else ""
                    
                    synopsis = item.get("description", "")
                    if synopsis: synopsis = re.sub(r'<[^>]+>', '', synopsis).strip()
                        
                    web_url = item.get("link", "")
                    cover = item.get("cover", "")
                    
                    category = item.get("categoryName", "")
                    genre = category.split(">")[-1] if category else ""
                    
                    r_score = item.get("customerReviewRank", 0)
                    rating_score = str(r_score / 2.0) if r_score else "-"
                    rating_detail = f"⭐ {rating_score} / 5.0" if r_score else "-"

                    results.append({
                        "Title": title, "Writer": author, "Publisher": publisher, 
                        "Summary": synopsis, "Series": title, "Web": web_url, 
                        "CoverUrl": cover, "Tags": genre, "Genre": genre, 
                        "LocalizedSeries": title,
                        "Count": "", "Rating": rating_detail, "RatingScore": rating_score, "AgeRating": "", 
                        "PubDate": pub_date, "Year": year, 
                        "Volume": "", "Number": "", "Characters": ""
                    })
        except Exception as e: pass
        return results

    @staticmethod
    def _search_ridibooks(query, page=1):
        url = "https://ridibooks.com/apps/search/search"
        params = [
            ("keyword", query), ("adult_exclude", "n"), ("where", "book"), 
            ("where", "author"), ("what", "instant"), 
            ("size", "20"), ("page", str(page)), ("site", "ridi-store")
        ]
        encoded_query = urllib.parse.quote_plus(query)
        referer = f"https://ridibooks.com/search?q={encoded_query}&adult_exclude=n&tab=COMIC&page={page}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
            "Referer": referer
        }
        
        results = []
        try:
            response = requests.get(url, params=params, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                books = data.get("book", {}).get("books", [])
                
                for b in books:
                    b_id = b.get("b_id", ""); title = b.get("title", "")
                    author = b.get("author", "")
                    if isinstance(author, list): author = ", ".join([str(a.get("name", a)) if isinstance(a, dict) else str(a) for a in author])
                    publisher = b.get("publisher", "")
                    synopsis = b.get("desc", b.get("synopsis", ""))
                    if synopsis: synopsis = re.sub(r'<[^>]+>', '', str(synopsis)).strip()
                    web_url = f"https://ridibooks.com/books/{b_id}" if b_id else ""
                    cover_obj = b.get("cover", {})
                    cover = cover_obj.get("xxlarge", "") if isinstance(cover_obj, dict) else str(cover_obj)
                    tags_info = b.get("tags_info", [])
                    tags = ", ".join([t.get("tag_name", "") for t in tags_info if isinstance(t, dict) and t.get("tag_name")])
                    cat1 = b.get("category_name", ""); cat2 = b.get("category_name2", "")
                    genre = ", ".join([c for c in [cat1, cat2] if c])
                    authors_info = b.get("authors_info", [])
                    alias_name = authors_info[0].get("alias_name", "") if authors_info and isinstance(authors_info, list) else ""
                    loc_series = f"{title}, {alias_name}" if alias_name else title
                    count = str(b.get("book_count", ""))
                    r_score = b.get("buyer_rating_score"); r_count = b.get("buyer_rating_count")
                    rating_score = str(r_score) if r_score is not None else "-"
                    rating_detail = f"⭐ {r_score} / 5.0 ({r_count})" if r_score is not None and r_count is not None else "-"
                    age_rating = "19세 이상" if b.get("is_adult_only") else str(b.get("age_limit", "전체 이용가"))
                    pub_date = b.get("web_title_pub_date", "") or b.get("publication_date", "")

                    results.append({
                        "Title": title, "Writer": author, "Publisher": publisher, 
                        "Summary": synopsis, "Series": title, "Web": web_url, 
                        "CoverUrl": cover, "Tags": tags, "Genre": genre, 
                        "LocalizedSeries": loc_series,
                        "Count": count, "Rating": rating_detail, "RatingScore": rating_score, "AgeRating": age_rating, 
                        "PubDate": pub_date, "Year": pub_date[:4] if pub_date else "", 
                        "Volume": "", "Number": "", "Characters": ""
                    })
        except Exception as e: pass
        return results
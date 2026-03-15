import os
import json
import sqlite3
import requests
import re
import urllib.parse
from pathlib import Path

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
        conn.commit()

init_db()

class MetaApiFetcher:
    @staticmethod
    def search(api_name, query):
        if not query: return []
            
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("SELECT results FROM search_cache WHERE api=? AND query=?", (api_name, query))
            row = c.fetchone()
            if row:
                try:
                    print(f"[{api_name}] '{query}' - ⚡ DB 캐시에서 데이터를 불러옵니다.")
                    return json.loads(row[0])
                except Exception as e:
                    print(f"Cache Load Error: {e}")
        
        print(f"[{api_name}] '{query}' - 🌐 API 서버로 요청을 보냅니다.")
        results = []
        if api_name == "리디북스":
            results = MetaApiFetcher._search_ridibooks(query)
            
        if results:
            with sqlite3.connect(DB_PATH) as conn:
                c = conn.cursor()
                c.execute("""
                    INSERT OR REPLACE INTO search_cache (api, query, results, updated_at) 
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """, (api_name, query, json.dumps(results, ensure_ascii=False)))
                conn.commit()
                
        return results

    @staticmethod
    def _search_ridibooks(query):
        url = "https://ridibooks.com/apps/search/search"
        
        params = [
            ("keyword", query),
            ("adult_exclude", "n"),
            ("where", "book"),
            ("where", "author"),
            ("what", "instant"),
            ("size", "5"),
            ("site", "ridi-store")
        ]
        
        encoded_query = urllib.parse.quote_plus(query)
        referer = f"https://ridibooks.com/search?q={encoded_query}&adult_exclude=n&tab=COMIC&page=1"
        
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
                    b_id = b.get("b_id", "")
                    title = b.get("title", "")
                    
                    author = b.get("author", "")
                    if isinstance(author, list):
                        author = ", ".join([str(a.get("name", a)) if isinstance(a, dict) else str(a) for a in author])
                    
                    publisher = b.get("publisher", "")
                    
                    synopsis = b.get("desc", b.get("synopsis", ""))
                    if synopsis:
                        synopsis = re.sub(r'<[^>]+>', '', str(synopsis)).strip()
                        
                    web_url = f"https://ridibooks.com/books/{b_id}" if b_id else ""
                    
                    cover_obj = b.get("cover", {})
                    cover = cover_obj.get("xxlarge", "") if isinstance(cover_obj, dict) else str(cover_obj)
                    
                    tags_info = b.get("tags_info", [])
                    tags = ", ".join([t.get("tag_name", "") for t in tags_info if isinstance(t, dict) and t.get("tag_name")])
                    
                    cat1 = b.get("category_name", "")
                    cat2 = b.get("category_name2", "")
                    genre = ", ".join([c for c in [cat1, cat2] if c])
                    
                    authors_info = b.get("authors_info", [])
                    alias_name = authors_info[0].get("alias_name", "") if authors_info and isinstance(authors_info, list) else ""
                    loc_series = f"{title}, {alias_name}" if alias_name else title
                    
                    count = str(b.get("book_count", ""))
                    
                    # 🌟 리스트용 평점(단일 숫자)과 상세보기용 평점(별+숫자+리뷰수) 분리
                    r_score = b.get("buyer_rating_score")
                    r_count = b.get("buyer_rating_count")
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
        except Exception as e:
            print(f"[리디북스] 통신 중 예외 발생: {e}")
            
        return results
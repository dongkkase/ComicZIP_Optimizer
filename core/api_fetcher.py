# core/api_fetcher.py

import os
import json
import sqlite3
import requests
import re
from pathlib import Path

# 캐시 DB 파일 경로 설정
DB_PATH = "api_cache.db"

def init_db():
    """앱 실행 시 캐시용 데이터베이스 테이블을 초기화합니다."""
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS search_cache (
                api TEXT,
                query TEXT,
                results TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (api, query)
            )
        ''')
        conn.commit()

init_db()

class MetaApiFetcher:
    """각종 도서/만화 메타데이터 API 검색 및 캐싱을 처리하는 클래스입니다."""
    
    @staticmethod
    def search(api_name, query):
        if not query:
            return []
            
        # 1. DB(캐시)에서 먼저 검색
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
        
        # 2. 캐시에 없으면 실제 API 서버로 요청
        print(f"[{api_name}] '{query}' - 🌐 API 서버로 요청을 보냅니다.")
        results = []
        if api_name == "리디북스":
            results = MetaApiFetcher._search_ridibooks(query)
        # TODO: 알라딘, 코믹박스 등 다른 API는 여기에 분기 추가
        
        # 3. 받아온 결과가 정상적이면 DB에 캐싱
        if results:
            with sqlite3.connect(DB_PATH) as conn:
                c = conn.cursor()
                c.execute("""
                    INSERT OR REPLACE INTO search_cache (api, query, results, updated_at) 
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """, (api_name, query, json.dumps(results, ensure_ascii=False)))
                conn.commit()
                print(f"[{api_name}] '{query}' - 💾 검색 결과를 DB에 캐싱했습니다.")
                
        return results

    @staticmethod
    def _search_ridibooks(query):
        """리디북스 비공식 검색 API를 호출하고 데이터를 파싱합니다."""
        
        # 🌟 공유해주신 정확한 엔드포인트 적용
        url = "https://ridibooks.com/apps/search/search"
        
        # 🌟 중복된 키(where)를 전송하기 위해 딕셔너리가 아닌 리스트-튜플 형태 사용
        params = [
            ("keyword", query),
            ("adult_exclude", "n"),
            ("where", "book"),
            ("where", "author"),
            ("what", "instant"),
            ("size", "20"), # 결과 개수를 넉넉하게 20개로 지정 (원하시면 5로 변경 가능)
            ("site", "ridi-store")
        ]
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://ridibooks.com/"
        }
        
        results = []
        try:
            response = requests.get(url, params=params, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                # 공유해주신 스펙대로 book > books 구조 탐색
                books = data.get("book", {}).get("books", [])
                
                print(f"[리디북스] API 통신 성공! 검색된 도서 수: {len(books)}개")
                
                for b in books:
                    b_id = b.get("b_id", "")
                    title = b.get("title", "")
                    
                    # 작가명 파싱 (리디북스는 객체 형태일 수 있음)
                    author = b.get("author", "")
                    if isinstance(author, list):
                        author = ", ".join([str(a.get("name", a)) if isinstance(a, dict) else str(a) for a in author])
                    
                    publisher = b.get("publisher", "")
                    synopsis = b.get("synopsis", "")
                    
                    # 표지 이미지 주소
                    cover = b.get("cover", "")
                    
                    # Synopsis의 HTML 태그 제거
                    if synopsis:
                        synopsis = re.sub(r'<[^>]+>', '', synopsis).strip()
                        
                    web_url = f"https://ridibooks.com/books/{b_id}" if b_id else ""
                    
                    results.append({
                        "Title": title,
                        "Writer": author,
                        "Publisher": publisher,
                        "Summary": synopsis,
                        "Series": title,
                        "Web": web_url,
                        "CoverUrl": cover,
                        
                        "Year": "", "Genre": "", "Tags": "", "Characters": "", "Volume": "", "Number": ""
                    })
            else:
                print(f"[리디북스] 에러 발생: HTTP {response.status_code}")
                print(f"응답 내용: {response.text[:200]}")
                
        except Exception as e:
            print(f"[리디북스] 통신 중 예외 발생: {e}")
            
        return results
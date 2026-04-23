import sqlite3
import os
import threading
import sys
import json

def get_project_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_db_path():
    db_dir = os.path.join(get_project_root(), "data")
    if not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    return os.path.join(db_dir, "library.db")

def get_thumb_dir():
    thumb_dir = os.path.join(get_project_root(), "data", "thumbnails")
    if not os.path.exists(thumb_dir):
        os.makedirs(thumb_dir, exist_ok=True)
    return thumb_dir

class LibraryDB:
    def __init__(self):
        self.db_path = get_db_path()
        self.lock = threading.Lock()
        print(f"[DB System] 데이터베이스 타겟 경로: {self.db_path}")
        self.init_db()

    def get_connection(self):
        is_new = not os.path.exists(self.db_path)
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        if is_new:
            self._create_tables(conn)
        return conn

    def _create_tables(self, conn):
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS files (
                path TEXT PRIMARY KEY,
                mtime REAL,
                size REAL,
                ext TEXT,
                resolution TEXT,
                title TEXT,
                series TEXT,
                series_group TEXT,
                volume TEXT,
                number TEXT,
                writer TEXT,
                creators TEXT,
                publisher TEXT,
                imprint TEXT,
                genre TEXT,
                volume_count TEXT,
                page_count TEXT,
                format TEXT,
                manga TEXT,
                language TEXT,
                rating TEXT,
                age_rating TEXT,
                publish_date TEXT,
                summary TEXT,
                characters TEXT,
                teams TEXT,
                locations TEXT,
                story_arc TEXT,
                tags TEXT,
                notes TEXT,
                web TEXT,
                thumb_path TEXT
            )
        ''')
        
        # 중복 검사 결과 캐싱용 테이블 신설
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS dup_cache (
                a_path TEXT PRIMARY KEY,
                match_data TEXT
            )
        ''')
        conn.commit()

    def init_db(self):
        with self.lock:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            cursor = conn.cursor()
            
            cursor.execute("PRAGMA table_info(files)")
            columns = cursor.fetchall()
            if columns and len(columns) < 32:
                print(f"[DB System] 구버전 테이블 감지 (컬럼수: {len(columns)}). 마이그레이션을 위해 초기화합니다.")
                cursor.execute("DROP TABLE IF EXISTS files")
            
            self._create_tables(conn)
            conn.close()

    def upsert_file_info(self, path, mtime, size, ext, resolution, title, series, series_group, volume, number, 
                         writer, creators, publisher, imprint, genre, volume_count, page_count, format_val, manga, 
                         language, rating, age_rating, publish_date, summary, characters, teams, locations, 
                         story_arc, tags, notes, web, thumb_path):
        with self.lock:
            try:
                conn = self.get_connection()
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO files 
                    (path, mtime, size, ext, resolution, title, series, series_group, volume, number, writer, 
                     creators, publisher, imprint, genre, volume_count, page_count, format, manga, language, 
                     rating, age_rating, publish_date, summary, characters, teams, locations, story_arc, 
                     tags, notes, web, thumb_path)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (path, mtime, size, ext, resolution, title, series, series_group, volume, number, writer, 
                      creators, publisher, imprint, genre, volume_count, page_count, format_val, manga, language, 
                      rating, age_rating, publish_date, summary, characters, teams, locations, story_arc, 
                      tags, notes, web, thumb_path))
                conn.commit()
            except Exception as e:
                print(f"DB 저장 오류: {e}")
            finally:
                if 'conn' in locals():
                    conn.close()

    def get_file_info(self, path):
        with self.lock:
            try:
                conn = self.get_connection()
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM files WHERE path = ?', (path,))
                result = cursor.fetchone()
                return result
            except Exception as e:
                print(f"DB 로드 오류: {e}")
                return None
            finally:
                if 'conn' in locals():
                    conn.close()

    # --- 추가된 중복 검사 캐시 관련 메서드 ---
    def save_dup_match(self, a_path, match_data):
        with self.lock:
            try:
                conn = self.get_connection()
                cursor = conn.cursor()
                json_data = json.dumps(match_data, ensure_ascii=False)
                cursor.execute('''
                    INSERT OR REPLACE INTO dup_cache (a_path, match_data)
                    VALUES (?, ?)
                ''', (a_path, json_data))
                conn.commit()
            except Exception as e:
                print(f"DB 중복 캐시 저장 오류: {e}")
            finally:
                if 'conn' in locals():
                    conn.close()

    def get_dup_match(self, a_path):
        with self.lock:
            try:
                conn = self.get_connection()
                cursor = conn.cursor()
                cursor.execute('SELECT match_data FROM dup_cache WHERE a_path = ?', (a_path,))
                result = cursor.fetchone()
                if result:
                    return json.loads(result[0])
                return None
            except Exception as e:
                print(f"DB 중복 캐시 로드 오류: {e}")
                return None
            finally:
                if 'conn' in locals():
                    conn.close()

    def clear_dup_cache(self):
        with self.lock:
            try:
                conn = self.get_connection()
                cursor = conn.cursor()
                cursor.execute('DELETE FROM dup_cache')
                conn.commit()
            except Exception as e:
                print(f"DB 중복 캐시 초기화 오류: {e}")
            finally:
                if 'conn' in locals():
                    conn.close()

db = LibraryDB()
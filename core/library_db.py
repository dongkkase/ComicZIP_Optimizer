import sqlite3
import os
import threading
import json

def get_project_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_db_path():
    db_dir = os.path.join(get_project_root(), "data")
    if not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    return os.path.join(db_dir, "library.db")

class LibraryDB:
    def __init__(self):
        self.db_path = get_db_path()
        self.lock = threading.Lock()
        self.init_db()

    def get_connection(self):
        is_new = not os.path.exists(self.db_path)
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        if is_new:
            self._create_tables(conn)
        return conn

    def _create_tables(self, conn):
        cursor = conn.cursor()
        
        # 기존 메타데이터 테이블
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
        
        # [신규] 1. 최종 중복 매칭 결과 캐시 테이블
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS dup_cache (
                a_path TEXT PRIMARY KEY,
                match_data TEXT
            )
        ''')
        
        # [신규] 2. 대상 폴더(B) 고속 스캔 인덱싱 테이블
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS dup_target_index (
                full_path TEXT PRIMARY KEY,
                target_folder TEXT,
                name TEXT,
                size REAL
            )
        ''')
        conn.commit()

    def init_db(self):
        with self.lock:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._create_tables(conn)
            conn.close()

    # --- 기존 메타데이터 메서드 ---
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
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (path, mtime, size, ext, resolution, title, series, series_group, volume, number, writer, 
                      creators, publisher, imprint, genre, volume_count, page_count, format_val, manga, language, 
                      rating, age_rating, publish_date, summary, characters, teams, locations, story_arc, 
                      tags, notes, web, thumb_path))
                conn.commit()
            except Exception as e: print(e)
            finally: 
                if 'conn' in locals(): conn.close()

    def get_file_info(self, path):
        with self.lock:
            try:
                conn = self.get_connection()
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM files WHERE path = ?', (path,))
                return cursor.fetchone()
            except Exception as e: return None
            finally: 
                if 'conn' in locals(): conn.close()

    # --- [신규] 중복 검사 인덱싱 (dup_target_index) 메서드 ---
    def save_target_index(self, records):
        with self.lock:
            try:
                conn = self.get_connection()
                cursor = conn.cursor()
                cursor.executemany('''
                    INSERT OR REPLACE INTO dup_target_index (full_path, target_folder, name, size)
                    VALUES (?, ?, ?, ?)
                ''', records)
                conn.commit()
            except Exception as e: print(e)
            finally: 
                if 'conn' in locals(): conn.close()

    def get_target_index(self, target_folder):
        with self.lock:
            try:
                conn = self.get_connection()
                cursor = conn.cursor()
                cursor.execute('SELECT full_path, name, size FROM dup_target_index WHERE target_folder = ?', (target_folder,))
                rows = cursor.fetchall()
                if not rows: return None
                
                result = []
                for row in rows:
                    result.append({
                        "full_path": row[0],
                        "path": os.path.dirname(row[0]),
                        "name": row[1],
                        "size": row[2]
                    })
                return result
            except Exception as e: return None
            finally: 
                if 'conn' in locals(): conn.close()

    # --- [신규] 중복 매칭 결과 캐시 (dup_cache) 메서드 ---
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
            except Exception as e: print(e)
            finally: 
                if 'conn' in locals(): conn.close()

    def get_dup_match(self, a_path):
        with self.lock:
            try:
                conn = self.get_connection()
                cursor = conn.cursor()
                cursor.execute('SELECT match_data FROM dup_cache WHERE a_path = ?', (a_path,))
                result = cursor.fetchone()
                return json.loads(result[0]) if result else None
            except Exception as e: return None
            finally: 
                if 'conn' in locals(): conn.close()

db = LibraryDB()
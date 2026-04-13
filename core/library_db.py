# core/library_db.py (신규 생성)
import sqlite3
import os
import json
from pathlib import Path

def get_db_path():
    # 실행 파일 또는 스크립트 위치 기준
    base_dir = Path(__file__).parent.parent
    cache_dir = base_dir / "cache"
    cache_dir.mkdir(exist_ok=True)
    return str(cache_dir / "library.db")

class LibraryDB:
    def __init__(self):
        self.db_path = get_db_path()
        self.init_db()

    def init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            # 파일 메타데이터 테이블
            c.execute('''
                CREATE TABLE IF NOT EXISTS file_meta (
                    filepath TEXT PRIMARY KEY,
                    mtime REAL,
                    ctime REAL,
                    filesize INTEGER,
                    resolution TEXT,
                    title TEXT,
                    series TEXT,
                    volume TEXT,
                    number TEXT,
                    writer TEXT,
                    thumb_path TEXT
                )
            ''')
            # 리스트 레이아웃 설정 테이블
            c.execute('''
                CREATE TABLE IF NOT EXISTS list_layouts (
                    layout_name TEXT PRIMARY KEY,
                    columns_json TEXT,
                    sort_column TEXT,
                    is_descending INTEGER
                )
            ''')
            conn.commit()

    def get_file_info(self, filepath):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM file_meta WHERE filepath=?", (filepath,))
            return c.fetchone()

    def save_file_info(self, filepath, data):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute('''
                INSERT OR REPLACE INTO file_meta 
                (filepath, mtime, ctime, filesize, resolution, title, series, volume, number, writer, thumb_path)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                filepath, data.get('mtime'), data.get('ctime'), data.get('filesize'),
                data.get('resolution'), data.get('title'), data.get('series'),
                data.get('volume'), data.get('number'), data.get('writer'), data.get('thumb_path')
            ))
            conn.commit()
            
    def get_layouts(self):
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT layout_name, columns_json FROM list_layouts")
            return c.fetchall()
            
db = LibraryDB()
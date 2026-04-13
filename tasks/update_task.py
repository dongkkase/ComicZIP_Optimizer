import urllib.request
import ssl
import json
from config import CURRENT_VERSION

class VersionCheckTask:
    def __init__(self, signals): self.signals = signals
    def run(self):
        try:
            url = "https://raw.githubusercontent.com/dongkkase/ComicZIP_Optimizer/main/version.json"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            context = ssl._create_unverified_context()
            with urllib.request.urlopen(req, timeout=3, context=context) as response:
                data = json.loads(response.read().decode('utf-8'))
                latest_ver = data.get("latest_version", "")
                curr_parts = [int(x) for x in CURRENT_VERSION.split('.')]
                latest_parts = [int(x) for x in latest_ver.split('.')]
                if latest_parts > curr_parts:
                    self.signals.version_checked.emit(latest_ver)
        except: pass

class ReleaseNotesTask:
    def __init__(self, signals): self.signals = signals
    def run(self):
        try:
            # 단일 latest 대신 목록 API를 호출하고 10개만 가져오도록 파라미터 지정
            url = "https://api.github.com/repos/dongkkase/ComicZIP_Optimizer/releases?per_page=10"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            context = ssl._create_unverified_context()
            with urllib.request.urlopen(req, timeout=5, context=context) as response:
                data = json.loads(response.read().decode('utf-8'))
                
                full_md = ""
                if isinstance(data, list):
                    for release in data:
                        name = release.get("name", release.get("tag_name", "업데이트"))
                        body = release.get("body", "릴리즈 내용이 없습니다.")
                        date_str = release.get("published_at", "")
                        
                        # T, Z가 포함된 ISO 시간 포맷에서 날짜(YYYY-MM-DD)만 추출
                        if date_str:
                            date_str = date_str.split("T")[0]
                            
                        full_md += f"# {name} ({date_str})\n\n{body}\n\n &nbsp; \n\n &nbsp; \n\n---\n\n &nbsp; \n\n"
                else:
                    full_md = "릴리즈 노트를 불러올 수 없습니다."
                    
                self.signals.release_notes_loaded.emit(full_md)
        except Exception as e:
            self.signals.release_notes_loaded.emit(f"인터넷 연결 오류 또는 깃허브 API 제한입니다.\n\n{e}")
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
        import urllib.request
        import ssl
        import json
        import markdown
        try:
            url = "https://api.github.com/repos/dongkkase/ComicZIP_Optimizer/releases?per_page=10"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            context = ssl._create_unverified_context()
            with urllib.request.urlopen(req, timeout=5, context=context) as response:
                data = json.loads(response.read().decode('utf-8'))
                
                parsed_releases = []
                if isinstance(data, list):
                    for release in data:
                        name = release.get("name", release.get("tag_name", "업데이트"))
                        date_str = release.get("published_at", "")
                        if date_str: date_str = date_str.split("T")[0]
                        body = release.get("body", "릴리즈 내용이 없습니다.")
                        
                        # 🌟 마크다운을 HTML(Rich Text)로 변환하여 메인 UI로 전달
                        body_html = markdown.markdown(body, extensions=['nl2br', 'extra', 'fenced_code'])
                        
                        parsed_releases.append({
                            "name": name,
                            "date": date_str,
                            "body": body_html
                        })
                
                self.signals.release_notes_loaded.emit(parsed_releases)
        except Exception as e:
            print(f"Release Notes Error: {e}")
            self.signals.release_notes_loaded.emit([])
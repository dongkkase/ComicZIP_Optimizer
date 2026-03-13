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
            url = "https://api.github.com/repos/dongkkase/ComicZIP_Optimizer/releases/latest"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            context = ssl._create_unverified_context()
            with urllib.request.urlopen(req, timeout=5, context=context) as response:
                data = json.loads(response.read().decode('utf-8'))
                body = data.get("body", "릴리스 노트를 불러올 수 없습니다.")
                name = data.get("name", "")
                full_md = f"# {name}\n\n{body}"
                self.signals.release_notes_loaded.emit(full_md)
        except Exception as e:
            self.signals.release_notes_loaded.emit(f"인터넷 연결 오류 또는 깃허브 API 제한입니다.\n\n{e}")
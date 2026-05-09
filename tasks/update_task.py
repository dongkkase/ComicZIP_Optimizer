# update_task.py

import urllib.request
import ssl
import json
import markdown
# 🌟 load_config를 추가로 임포트합니다.
from config import CURRENT_VERSION, load_config

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
    # tasks/update_task.py 

    def run(self):
        try:
            config = load_config()
            # 🌟 config에 없을 경우를 대비한 기본값도 따옴표를 포함해 작성합니다.
            font_str = config.get('font_family_str', "'Jua', 'Noto Sans KR', sans-serif")
            
            url = "https://api.github.com/repos/dongkkase/ComicZIP_Optimizer/releases?per_page=10"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            context = ssl._create_unverified_context()
            with urllib.request.urlopen(req, timeout=5, context=context) as response:
                data = json.loads(response.read().decode('utf-8'))
                
                html_template = f"""
                <!DOCTYPE html>
                <html>
                <head>
                <style>
                    @import url('https://fonts.googleapis.com/css2?family=Jua&family=Noto+Sans+KR:wght@400;700&display=swap');
                    /* 🌟 작은따옴표 제거 및 font_str 직접 주입 */
                    body {{ background-color: #1e1e1e; color: #e0e0e0; font-family: {font_str}, sans-serif; padding: 10px 20px; margin: 0; }}
                    
                    ::-webkit-scrollbar {{ width: 10px; }}
                    ::-webkit-scrollbar-track {{ background: #1e1e1e; }}
                    ::-webkit-scrollbar-thumb {{ background: #555; border-radius: 5px; }}
                    ::-webkit-scrollbar-thumb:hover {{ background: #777; }}
                    
                    .release-card {{ background-color: #2b2b2b; border: 1px solid #444; border-radius: 20px; padding: 25px; margin-bottom: 25px; box-shadow: 0 4px 10px rgba(0, 0, 0, 0.4); }}
                    .release-title {{ color: #3498DB; margin-top: 0; margin-bottom: 15px; font-size: 24px; border-bottom: 1px solid #444; padding-bottom: 10px; }}
                    .release-date {{ color: #aaaaaa; font-size: 14px; font-weight: normal; margin-left: 8px; }}
                    .release-body {{ line-height: 1.6; font-size: 15px; }}
                    
                    a {{ color: #3498DB; text-decoration: none; }}
                    a:hover {{ text-decoration: underline; }}
                    
                    /* 🌟 여기도 작은따옴표 제거 */
                    code {{ background-color: #1a1a1a; padding: 2px 6px; border-radius: 4px; font-family: {font_str}, Consolas, monospace; }}
                    pre {{ background-color: #1a1a1a; padding: 15px; border-radius: 8px; overflow-x: auto; }}
                    blockquote {{ border-left: 4px solid #3498DB; margin: 0; padding-left: 15px; color: #aaaaaa; }}
                </style>
                </head>
                <body>
                """
                # (이하 코드 동일)
                
                if isinstance(data, list):
                    for release in data:
                        name = release.get("name", release.get("tag_name", "업데이트"))
                        body = release.get("body", "릴리즈 내용이 없습니다.")
                        date_str = release.get("published_at", "")
                        
                        if date_str:
                            date_str = date_str.split("T")[0]
                            
                        body_html = markdown.markdown(body, extensions=['nl2br', 'extra', 'fenced_code'])
                        
                        html_template += f"""
                        <div class="release-card">
                            <h3 class="release-title">📦 {name} <span class="release-date">({date_str})</span></h3>
                            <div class="release-body">{body_html}</div>
                        </div>
                        """
                else:
                    html_template += "<p>릴리즈 노트를 불러올 수 없습니다.</p>"
                    
                html_template += "</body></html>"
                
                # 순수 HTML 텍스트를 메인 창으로 전달
                self.signals.release_notes_loaded.emit(html_template)
                
        except Exception as e:
            print(f"Release Notes Error: {e}")
            pass
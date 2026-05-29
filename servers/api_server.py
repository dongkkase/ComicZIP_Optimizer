import http.server
import socketserver
import json
import socket
from .base import BaseServerThread

class APIServerThread(BaseServerThread):
    """
    YACReader 또는 자체 클라이언트를 지원하기 위한 REST API(JSON) 제공 서버입니다.
    """
    def __init__(self, port=8081, root_path=""):
        super().__init__(port, root_path)
        self.httpd = None

    def _start_server(self):
        server_thread = self
        
        class APIHandler(http.server.SimpleHTTPRequestHandler):
            # 접속 시 지연을 유발하는 역방향 DNS 조회 무시
            def address_string(self):
                return self.client_address[0]
                
            # 멀티스레딩 병목을 유발하는 파이썬 기본 콘솔 로깅 비활성화
            def log_message(self, format, *args):
                pass
                
            def do_GET(self):
                if self.path.startswith("/api/"):
                    server_thread.log_signal.emit(f"[API] 앱 접근: {self.path} ({self.client_address[0]})")
                    
                    self.send_response(200)
                    self.send_header("Content-type", "application/json; charset=utf-8")
                    self.end_headers()
                    
                    # 상태 반환 (향후 DB 조회 후 JSON 리턴으로 고도화)
                    response = {"status": "success", "message": "ComicZIP API is running."}
                    self.wfile.write(json.dumps(response).encode('utf-8'))
                else:
                    # 허용되지 않은 경로 요청 시 디스크 스캔을 방지하고 즉각 404 반환
                    self.send_error(404, "Invalid API Endpoint")

        # 포트 변경 및 재시작 시 발생하는 Address already in use 에러 방지
        class ReusableTCPServer(socketserver.ThreadingTCPServer):
            allow_reuse_address = True

        try:
            # 멀티 스레드 및 포트 재사용 서버 적용
            self.httpd = ReusableTCPServer(("", self.port), APIHandler)
            self.httpd.daemon_threads = True
            
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
                s.close()
            except Exception:
                local_ip = "127.0.0.1"
                
            self.log_signal.emit(f"[API] Server listening at http://{local_ip}:{self.port}/api")
            self.httpd.serve_forever()
        except Exception as e:
            self.error_signal.emit(f"[API] Error: {str(e)}")

    def _stop_server(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
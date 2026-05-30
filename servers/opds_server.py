import os
from .base import BaseServerThread
from core.library_db import db

class OPDSServerThread(BaseServerThread):
    def __init__(self, port: int, root_path: str):
        super().__init__(port, root_path)
        self.server = None

    def _start_server(self):
        try:
            import uvicorn
            from fastapi import FastAPI, Response
        except ImportError:
            self.error_signal.emit("FastAPI 및 Uvicorn 패키지가 설치되지 않았습니다. 명령 프롬프트(터미널)에서 'pip install fastapi uvicorn'을 실행해 주세요.")
            return

        app = FastAPI(title="ComicZIP OPDS Server")

        @app.get("/opds")
        async def opds_catalog():
            # TODO: 추후 DB(self.root_path 등)를 연동하여 실제 라이브러리 목록을 동적으로 생성하도록 확장합니다.
            # 현재는 서버 구동 테스트를 위한 기본 OPDS Root 피드입니다.
            opds_xml = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opds="http://opds-spec.org/2010/catalog">
  <id>urn:comiczip:opds:root</id>
  <title>ComicZIP Library</title>
  <updated>2024-01-01T00:00:00Z</updated>
  <author>
    <name>ComicZIP Optimizer</name>
  </author>
  <link rel="self" href="/opds" type="application/atom+xml;profile=opds-catalog;kind=navigation"/>
  <link rel="start" href="/opds" type="application/atom+xml;profile=opds-catalog;kind=navigation"/>
  
  <entry>
    <title>All Comics (Test)</title>
    <link rel="subsection" href="/opds/all" type="application/atom+xml;profile=opds-catalog;kind=acquisition"/>
    <id>urn:comiczip:opds:all</id>
    <content type="text">Explore all optimized comics</content>
  </entry>
</feed>"""
            return Response(content=opds_xml, media_type="application/atom+xml")

        # Uvicorn 설정: QThread 내부 실행이므로 시그널 핸들러를 끄고 블로킹 방식으로 실행
        config = uvicorn.Config(
            app, host="0.0.0.0", port=self.port, 
            log_level="warning", access_log=False
        )
        self.server = uvicorn.Server(config)
        
        import socket
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
        except Exception:
            local_ip = "127.0.0.1"
            
        self.log_signal.emit(f"OPDS 서버가 성공적으로 시작되었습니다: http://{local_ip}:{self.port}/opds")
        
        # run()은 self.server.should_exit가 True가 되기 전까지 스레드를 유지(Blocking)합니다.
        self.server.run()

    def _stop_server(self):
        if self.server:
            self.server.should_exit = True
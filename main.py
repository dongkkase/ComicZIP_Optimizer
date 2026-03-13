import sys
import ctypes
import traceback
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QSharedMemory
from ui.main_window import RenamerApp

# 🌟 [강제 종료 방지 훅] PyQt6 내부에서 에러가 발생해도 0xc0000409로 튕기지 않게 방어합니다.
def exception_hook(exctype, value, tb):
    traceback.print_exception(exctype, value, tb)
    # 콘솔에 에러 내용만 출력하고 프로그램은 계속 살려둡니다.

sys.excepthook = exception_hook

if __name__ == "__main__":
    try:
        # 작업 표시줄 아이콘 그룹화 분리용 앱 ID 설정
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('dongkkase.comiczip.optimizer.1')
    except Exception: 
        pass
    
    app = QApplication(sys.argv)
    
    # 중복 실행 방지
    shared_memory = QSharedMemory("ComicZIP_Optimizer_SingleInstance")
    if shared_memory.attach():
        sys.exit(0)
    shared_memory.create(1) 
    
    window = RenamerApp()
    window.show()
    
    sys.exit(app.exec())
import sys
import ctypes
import traceback
import os

os.environ["QT_LOGGING_RULES"] = "qt.gui.icc.warning=false"

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QSharedMemory
from ui.main_window import RenamerApp

def exception_hook(exctype, value, tb):
    traceback.print_exception(exctype, value, tb)

sys.excepthook = exception_hook

if __name__ == "__main__":
    # OS 종속성 방어 (Windows에서만 작업 표시줄 그룹화 적용)
    import sys
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('dongkkase.comiczip.optimizer.1')
        except Exception:
            pass

    app = QApplication(sys.argv)
    
    # 🌟 중복 실행 방지 및 고스트 락(Ghost Lock) 해결
    from PyQt6.QtCore import QSharedMemory
    shared_memory = QSharedMemory("ComicZIP_Optimizer_SingleInstance")
    if shared_memory.attach():
        # 강제 종료로 인한 찌꺼기 메모리일 수 있으므로 우선 해제 시도
        shared_memory.detach()
        
    # 진짜로 실행 중인 앱이 있다면 여기서 무조건 False를 반환함
    if not shared_memory.create(1):
        sys.exit(0)

    from ui.main_window import RenamerApp
    window = RenamerApp()
    window.show()

    sys.exit(app.exec())
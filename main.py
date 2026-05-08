import sys
import ctypes
import traceback
import os

os.environ["QT_LOGGING_RULES"] = "qt.gui.icc.warning=false"
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
os.environ["QT_SCALE_FACTOR_ROUNDING_POLICY"] = "PassThrough"

if sys.platform == 'win32':
    os.environ["QT_FONT_DPI"] = "96"

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QSharedMemory, Qt
from PyQt6.QtGui import QFontDatabase, QFont
from ui.main_window import RenamerApp
from config import get_font_path


def exception_hook(exctype, value, tb):
    traceback.print_exception(exctype, value, tb)

sys.excepthook = exception_hook


def register_custom_fonts(app):
    """fonts/ 폴더의 TTF를 Qt에 등록하고 앱 기본 폰트를 설정 (Windows/Mac 크로스플랫폼)"""
    from PyQt6.QtGui import QFontDatabase, QFont
    from config import get_font_path, load_config
    
    config = load_config()
    # 설정된 배율(scale) 가져오기
    scale = config.get("font_scale", 100) / 100.0
    # 기본 10pt에 배율 적용
    base_size = int(10 * scale)

    font_files = {
        "Jua":        "Jua-Regular.ttf",
        "NotoSansKR": "NotoSansKR-Regular.ttf",
    }
    loaded = []
    for family, filename in font_files.items():
        path = get_font_path(filename)
        if path:
            fid = QFontDatabase.addApplicationFont(path)
            if fid != -1:
                loaded.append(family)
            else:
                print(f"[Font] 로드 실패: {path}")
        else:
            print(f"[Font] 파일 없음: {filename}")

    # 환경 설정의 글꼴 가져오기
    ff = config.get("font_family", "Default")
    if ff == "Default":
        family = "Jua" if "Jua" in loaded else "Noto Sans KR" if "NotoSansKR" in loaded else None
    else:
        family = ff

    if family:
        font = QFont(family, base_size) # 계산된 base_size 적용
        # 부드러운 렌더링 핵심 설정
        font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        font.setStyleStrategy(
            QFont.StyleStrategy.PreferAntialias | QFont.StyleStrategy.PreferQuality
        )
        app.setFont(font)


if __name__ == "__main__":
    # OS 종속성 방어 (Windows에서만 작업 표시줄 그룹화 적용)
    if sys.platform == 'win32':
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                'dongkkase.comiczip.optimizer.1')
            # ClearType(서브픽셀) 렌더링 활성화
            ctypes.windll.gdi32.SetFontSmoothing(True)
        except Exception:
            pass

    app = QApplication(sys.argv)

    register_custom_fonts(app)

    # 중복 실행 방지 및 고스트 락(Ghost Lock) 해결
    shared_memory = QSharedMemory("ComicZIP_Optimizer_SingleInstance")
    if shared_memory.attach():
        # 강제 종료로 인한 찌꺼기 메모리일 수 있으므로 우선 해제 시도
        shared_memory.detach()
    # 진짜로 실행 중인 앱이 있다면 여기서 무조건 False를 반환함
    if not shared_memory.create(1):
        sys.exit(0)

    window = RenamerApp()
    window.show()
    sys.exit(app.exec())
@echo off
setlocal
set CURRENT_DIR=%~dp0

:: 1. version.json 파일에서 최신 버전 자동 추출 (PowerShell 활용)
for /f "usebackq tokens=*" %%a in (`powershell -NoProfile -Command "(Get-Content '%CURRENT_DIR%version.json' | ConvertFrom-Json).latest_version"`) do set EXTRACTED_VERSION=%%a

:: --- 설정 영역 ---
set APP_NAME=ComicZIP_Optimizer
set APP_VERSION=v%EXTRACTED_VERSION%
set ZIP_NAME=ComicZIP_Optimizer_%APP_VERSION%.zip
set MAIN_SCRIPT=renamer.py
:: ----------------

echo [정보] version.json에서 읽어온 타겟 버전: %APP_VERSION%
echo [1/2] PyInstaller 빌드 시작...

:: 🌟 -y 옵션 추가 (묻지 않고 덮어쓰기) 및 app.ico 데이터 포함
pyinstaller -y -w -D --icon=app.ico -n "%APP_NAME%" ^
    --add-data "app.ico;." ^
    --add-data "7za.exe;." ^
    --add-data "previewframe.png;." ^
    --add-data "version.json;." ^
    --exclude-module PyQt6.QtNetwork ^
    --exclude-module PyQt6.QtSql ^
    --exclude-module PyQt6.QtWebEngine ^
    --exclude-module PyQt6.QtWebEngineCore ^
    --exclude-module PyQt6.QtWebEngineWidgets ^
    --exclude-module PyQt6.QtQml ^
    --exclude-module PyQt6.QtQuick ^
    --exclude-module PyQt6.QtBluetooth ^
    --exclude-module PyQt6.QtMultimedia ^
    --exclude-module PyQt6.QtMultimediaWidgets ^
    --exclude-module PyQt6.QtDBus ^
    --exclude-module PyQt6.QtDesigner ^
    --exclude-module PyQt6.QtOpenGL ^
    --exclude-module PyQt6.QtOpenGLWidgets ^
    --exclude-module PyQt6.QtPrintSupport ^
    --exclude-module PyQt6.QtSvg ^
    --exclude-module PyQt6.QtTest ^
    --exclude-module PyQt6.QtXml ^
    --exclude-module tkinter ^
    --exclude-module pydoc ^
    --exclude-module xmlrpc ^
    --upx-dir=. "%MAIN_SCRIPT%"

:: 빌드 실패 시 중단하고 에러 메시지 확인
if %errorlevel% neq 0 (
    echo [!오류] 빌드 중 문제가 발생했습니다. 창을 닫으려면 아무 키나 누르세요.
    pause
    exit /b %errorlevel%
)

echo.
echo [2/2] ZIP 압축 중...
if exist "%ZIP_NAME%" del /q /f "%ZIP_NAME%"
powershell -Command "Compress-Archive -Path 'dist\%APP_NAME%\*' -DestinationPath '%ZIP_NAME%' -Force"

echo.
echo ==========================================
echo 모든 작업 완료! [%ZIP_NAME%] 생성 완료
echo 3초 후 창이 자동으로 닫힙니다.
echo ==========================================

timeout /t 3

endlocal
exit
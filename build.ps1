$ErrorActionPreference = "Stop"

# --- 설정 영역 ---
$APP_NAME = "ComicZIP_Optimizer"
$ZIP_NAME = "ComicZIP_Optimizer.zip"
$MAIN_SCRIPT = "renamer.py"
# ----------------

Write-Host "[1/2] PyInstaller 빌드 시작..." -ForegroundColor Cyan

# 파워쉘은 백틱(`)을 사용하여 안전하게 줄바꿈을 지원합니다.
pyinstaller -y -w -D --icon=app.ico -n "$APP_NAME" `
    --add-data "app.ico;." `
    --add-data "7za.exe;." `
    --add-data "previewframe.png;." `
    --add-data "version.json;." `
    --exclude-module PyQt6.QtNetwork `
    --exclude-module PyQt6.QtSql `
    --exclude-module PyQt6.QtWebEngine `
    --exclude-module PyQt6.QtWebEngineCore `
    --exclude-module PyQt6.QtWebEngineWidgets `
    --exclude-module PyQt6.QtQml `
    --exclude-module PyQt6.QtQuick `
    --exclude-module PyQt6.QtBluetooth `
    --exclude-module PyQt6.QtMultimedia `
    --exclude-module PyQt6.QtMultimediaWidgets `
    --exclude-module PyQt6.QtDBus `
    --exclude-module PyQt6.QtDesigner `
    --exclude-module PyQt6.QtOpenGL `
    --exclude-module PyQt6.QtOpenGLWidgets `
    --exclude-module PyQt6.QtPrintSupport `
    --exclude-module PyQt6.QtSvg `
    --exclude-module PyQt6.QtTest `
    --exclude-module PyQt6.QtXml `
    --exclude-module tkinter `
    --exclude-module pydoc `
    --exclude-module xmlrpc `
    --upx-dir=. "$MAIN_SCRIPT"

Write-Host "`n[2/2] ZIP 압축 중..." -ForegroundColor Cyan

# 묻지 않고 기존 압축 파일 강제 삭제
if (Test-Path "$ZIP_NAME") {
    Remove-Item "$ZIP_NAME" -Force
}

# 새롭게 압축 실행
Compress-Archive -Path "dist\$APP_NAME\*" -DestinationPath "$ZIP_NAME" -Force

Write-Host "`n==========================================" -ForegroundColor Green
Write-Host "모든 작업 완료! [$ZIP_NAME] 생성 완료" -ForegroundColor Yellow
Write-Host "==========================================" -ForegroundColor Green

Start-Sleep -Seconds 3
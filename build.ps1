# 파라미터 정의 (반드시 스크립트 최상단에 위치해야 합니다)
param (
    [switch]$DevMode
)

$ErrorActionPreference = "Stop"

# --- 설정 영역 ---
$APP_NAME = "ComicZIP_Optimizer"
$ZIP_NAME = "ComicZIP_Optimizer.zip"
$MAIN_SCRIPT = "renamer.py"
# ----------------

# --- 기존 실행 중인 프로세스 강제 종료 ---
if (Get-Process -Name $APP_NAME -ErrorAction SilentlyContinue) {
    Write-Host "🚨 [$APP_NAME.exe] 프로세스가 실행 중입니다. 강제 종료를 시도합니다..." -ForegroundColor Yellow
    Stop-Process -Name $APP_NAME -Force
    Start-Sleep -Seconds 2  # 프로세스가 완전히 종료되고 파일 잠금이 풀릴 때까지 대기
}
# -----------------------------------------

Write-Host "`n[1/2] PyInstaller 빌드 시작..." -ForegroundColor Cyan

# 파워쉘은 백틱(`)을 사용하여 안전하게 줄바꿈을 지원합니다.
pyinstaller -y -w -D --icon=app.ico -n "$APP_NAME" `
    --add-data "app.ico;." `
    --add-data "7za.exe;." `
    --add-data "previewframe.png;." `
    --add-data "version.json;." `
    --add-data "sounds\complete.wav;." `
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

# --- 개발 모드 여부에 따른 압축 처리 ---
if (-not $DevMode) {
    Write-Host "`n[2/2] ZIP 압축 중..." -ForegroundColor Cyan

    # 묻지 않고 기존 압축 파일 강제 삭제
    if (Test-Path "$ZIP_NAME") {
        Remove-Item "$ZIP_NAME" -Force
    }

    # 새롭게 압축 실행
    Compress-Archive -Path "dist\$APP_NAME\*" -DestinationPath "$ZIP_NAME" -Force
    
    $FinalMessage = "모든 작업 완료! [$ZIP_NAME] 생성 완료"
} else {
    Write-Host "`n[2/2] 🛠️ 개발 모드(-DevMode) 감지: ZIP 압축을 생략합니다." -ForegroundColor Cyan
    $FinalMessage = "빌드 완료! (압축 생략됨)"
}
# ----------------------------------------

Write-Host "`n==========================================" -ForegroundColor Green
Write-Host $FinalMessage -ForegroundColor Yellow
Write-Host "==========================================" -ForegroundColor Green

# --- 완료 알림음 (윈도우 기본 미디어의 듣기 좋은 소리 사용) ---
$sound = New-Object System.Media.SoundPlayer
$sound.SoundLocation = ".\sounds\complete.wav" # "tada.wav" 로 변경하시면 짜잔~ 하는 소리가 납니다.
$sound.Play()

# --- 개발 모드일 경우 프로그램 자동 실행 ---
if ($DevMode) {
    $exePath = "dist\$APP_NAME\$APP_NAME.exe"
    if (Test-Path $exePath) {
        Write-Host "🚀 개발 모드: 빌드된 프로그램을 자동으로 실행합니다..." -ForegroundColor Cyan
        Start-Process -FilePath $exePath
    } else {
        Write-Host "⚠️ 실행 파일을 찾을 수 없습니다: $exePath" -ForegroundColor Red
    }
}

Start-Sleep -Seconds 3
# 📚 ComicZIP Optimizer

[English](#-english) | [한국어](#-한국어)

---
<kbd>![Demo](https://raw.githubusercontent.com/dongkkase/ComicZIP_Optimizer/main/video/demo.gif)</kbd>
---

<a id="-english"></a>
## 🇬🇧 English
<kbd>![image](https://raw.githubusercontent.com/dongkkase/ComicZIP_Optimizer/main/video/demo1.png)</kbd>

**ComicZIP Optimizer** is a powerful and smart GUI tool designed for comic/manga collectors and e-book reader users (Plex, Kavita, YACReader, etc.). It automatically renames inner images, flattens nested folders, and converts images to WebP to save disk space—all without manually extracting the archives.

<p align="center">
  </p>

### ✨ Key Features

* **🔄 Smart Batch Renaming**
  * Renames inner images systematically (e.g., `001.jpg`, `Cover.jpg`, `Filename_001.jpg`).
  * Processes directly within the archive without manual extraction.
* **📂 Folder Flattening (Remove Sub-folders)**
  * Removes annoying nested folders inside archives, moving all images to the root.
  * Uses the **Natural Sort** algorithm to prevent naming conflicts and order mix-ups.
* **⚡ Multi-threaded WebP Conversion**
  * Converts bulky PNG/JPG images to a highly efficient WebP format.
  * Utilizes Multi-threading for ultra-fast conversion.
  * Includes an adjustable WebP Quality Slider (supports 100% Lossless mode).
* **📦 Format Conversion**
  * Easily convert between ZIP, CBZ, CBR, and 7Z formats.
* **🔒 Safe & Smart Processing**
  * **Auto Update Check**: Automatically checks for the latest version via GitHub Releases.
  * Smart Thread Limit to prevent PC freezing during multi-core processing.
  * UI lock and Instant Cancel (🛑) feature during processing.
  * "Backup Original" option available.

### 🚀 How to Run

1. Go to the [Releases](https://github.com/dongkkase/ComicZIP_Optimizer/releases) page.
2. Download the latest `ComicZIP_Optimizer.zip` file.
3. Extract the ZIP file and run the executable (`.exe`). No installation is required!

### 🛠️ Tech Stack
* Python 3
* PyQt6 (GUI Framework)
* Pillow (Image Processing)
* 7-Zip (`7za.exe` for robust archive handling)

### 📝 License
This project is licensed under the **[MIT License](LICENSE)**.
* **7-Zip**: This application bundles `7za.exe` (7-Zip standalone console version), which is licensed under the GNU LGPL and unRAR restriction. For more info, visit [7-zip.org](https://www.7-zip.org/).

<br>

---

<a id="-한국어"></a>
## 🇰🇷 한국어
<kbd>![image](https://raw.githubusercontent.com/dongkkase/ComicZIP_Optimizer/main/video/demo2.png)</kbd>
ComicZIP Optimizer(코믹집 옵티마이저)는 만화/코믹스 수집가 및 e-book 리더기(Kavita, Plex, YACReader 등) 사용자를 위한 강력한 GUI 최적화 툴입니다. 
압축 파일을 일일이 풀지 않고도 내부 이미지 파일명 일괄 변경, 폴더 구조 평탄화, 다중 코어 WebP 변환을 지원하여 관리 편의성과 용량 다이어트를 동시에 제공합니다.

<p align="center">
  </p>

### ✨ 주요 기능

* **🔄 스마트 파일명 일괄 변경**
  * 난잡한 내부 이미지 이름을 규칙에 맞게 일괄 정리합니다. (예: `기본 숫자 패딩`, `영문 도서 스타일`, `압축파일명 동기화` 등 지원)
  * 압축 해제 없이 파일 내부에서 직접 고속으로 처리됩니다.
* **📂 폴더 구조 평탄화 (하위 폴더 제거)**
  * e-book 리더기에서 인식 오류를 일으키는 불필요한 이중/삼중 폴더를 제거하고 이미지를 최상단으로 끌어올립니다.
  * **경로 인식형 자연 정렬(Natural Sort)** 알고리즘을 적용하여 폴더 뎁스와 파일 순서가 절대 꼬이지 않습니다.
* **⚡ 초고속 다중 스레드 WebP 변환**
  * 무거운 JPG/PNG 이미지를 고효율 WebP 포맷으로 일괄 변환하여 디스크 용량을 획기적으로 절약합니다.
  * 다중 코어(Multi-threading)를 100% 활용해 변환 속도를 극대화했습니다.
  * 화질 조절 슬라이더 제공 (100% 무손실 압축 지원).
* **📦 포맷 자동 변환**
  * ZIP, CBZ, CBR, 7Z 파일 간의 포맷을 클릭 한 번으로 자유롭게 변환합니다.
* **🔒 시스템 안전 장치 및 편의성**
  * **자동 업데이트 알림**: 프로그램 실행 시 깃허브와 연동하여 새로운 버전이 있는지 확인하고 알려줍니다.
  * 작업 중 PC가 멈추지 않도록 CPU 여유 코어를 강제로 남겨두는 안전 제한(Safe Limit) 기능.
  * 데이터 꼬임 방지를 위한 작업 중 UI 잠금 및 즉각적인 작업 중단(Cancel) 기능.
  * 원본 백업(bak 폴더 생성) 지원.

### 🚀 실행 방법

1. [Releases](https://github.com/dongkkase/ComicZIP_Optimizer/releases) 페이지로 이동합니다.
2. 최신 버전의 `ComicZIP_Optimizer.zip` 파일을 다운로드합니다.
3. 압축을 풀고 안에 있는 실행 파일(`.exe`)을 바로 실행하세요. (별도의 설치가 필요 없는 포터블 버전입니다.)

### 🛠️ 사용 기술
* Python 3
* PyQt6 (UI 프레임워크)
* Pillow (이미지 처리)
* 7-Zip (`7za.exe` 압축 엔진)

### 📝 라이선스 (License)
이 프로젝트는 **[MIT License](LICENSE)** 를 따릅니다. 누구나 자유롭게 사용, 수정, 배포할 수 있습니다.
* **7-Zip**: 본 프로그램은 파일 압축/해제를 위해 `7za.exe`를 내부적으로 사용하며, 해당 파일은 GNU LGPL 라이선스를 따릅니다. 자세한 정보는 [7-zip.org](https://www.7-zip.org/)에서 확인할 수 있습니다.
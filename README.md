# 📚 ComicZIP Optimizer

[English](#-english) | [한국어](#-한국어)

---
<kbd>![Demo](https://raw.githubusercontent.com/dongkkase/ComicZIP_Optimizer/main/demo/demo.gif)</kbd>
---

<a id="-english"></a>
## 🇬🇧 English
<kbd>![image](https://raw.githubusercontent.com/dongkkase/ComicZIP_Optimizer/main/demo/demo1_en.png)</kbd>
<kbd>![image](https://raw.githubusercontent.com/dongkkase/ComicZIP_Optimizer/main/demo/demo2_en.png)</kbd>

**ComicZIP Optimizer** is a powerful and smart GUI tool designed for comic/manga collectors and e-book reader users (Plex, Kavita, YACReader, etc.). It automatically renames inner images, flattens nested folders, and converts images to WebP to save disk space—all without manually extracting the archives.

<p align="center">
  </p>

### ✨ Key Features

**🚀 [NEW] Smart Archive Reorganization (Split & Merge)**
* Scans integrated archives containing multiple volumes, then intelligently separates, merges, and repackages them into clean, individual volume archives.
* Provides an intuitive Tree-view preview with an 'Expand/Collapse All' function to easily grasp the internal structure at a glance.
* High-speed In-Memory scanning previews massive files without extracting them to disk, automatically skipping already organized files.

**🧠 Intelligent Title & Volume Extraction Engine (Deep Scan Parser)**
* Ignores meaningless Hash folder names (25+ characters) or generic shells (like `temp`). It deep-scans the archive in reverse to extract the real comic titles.
* Automatically cleans up bracket tags (e.g., `[High Quality]`) and smartly appends volume identifiers (e.g., 'v') to folders named only with numbers.

**🔄 Batch Inner Renaming & Output Path Control**
* Uniformly renames messy inner image files according to preset rules (e.g., Number padding, English book style, Sync with archive name).
* Easily control the output destination paths for processed files individually via text input, or batch-change them with a single click.

**📂 Folder Flattening & Perfect Natural Sort**
* Removes unnecessary nested folders (double/triple depths) that cause reading errors in e-book readers, pulling all images to the root.
* Employs an improved slash-based Natural Sort algorithm, ensuring folder depth and file order perfectly match Windows File Explorer.

**⚡ Ultra-fast Multi-threaded WebP Conversion**
* Batch-converts heavy JPG/PNG images to the highly efficient WebP format, drastically saving disk space.
* Maximizes conversion speed by utilizing 100% of CPU Multi-threading. Includes a quality slider (supports 100% lossless compression).

**📦 Auto Format Conversion**
* Freely convert between ZIP, CBZ, CBR, and 7Z formats with a single click.

**🔒 Maximized System Stability & Convenience**
* **Rock-solid Stability:** Handles thousands of drag-and-dropped files without freezing, completely preventing Windows 11 Explorer crash bugs.
* **Safe Temp Operations:** Uses unique UUIDs in the system temp folder, preventing write errors and leftover debris even when working directly on Network Drives (NAS).
* **Convenience:** Smart list auto-selection (enables continuous keyboard deletion), Completion sound toggle, Auto-update notifications, CPU safe limits, and Original backup (.bak) support.

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
<kbd>![image](https://raw.githubusercontent.com/dongkkase/ComicZIP_Optimizer/main/demo/demo1_ko.png)</kbd>
<kbd>![image](https://raw.githubusercontent.com/dongkkase/ComicZIP_Optimizer/main/demo/demo2_ko.png)</kbd>
ComicZIP Optimizer(코믹집 옵티마이저)는 만화/코믹스 수집가 및 e-book 리더기(Kavita, Plex, YACReader 등) 사용자를 위한 강력한 GUI 최적화 툴입니다. 
압축 파일을 일일이 풀지 않고도 내부 이미지 파일명 일괄 변경, 폴더 구조 평탄화, 다중 코어 WebP 변환을 지원하여 관리 편의성과 용량 다이어트를 동시에 제공합니다.

<p align="center">
  </p>

### ✨ 주요 기능

**🚀 [NEW] 압축 파일 구조 일괄 정리 (분리 및 병합)**
* 내부에 여러 권의 책이 섞여 있는 통합 압축파일을 스캔하여, 각 권별로 깔끔하게 분리 및 병합한 후 재압축합니다.
* 직관적인 트리(Tree) 형태의 미리보기와 '전체 펼치기/접기' 기능을 지원하여 내부 구조를 한눈에 파악할 수 있습니다.
* 디스크에 압축을 풀지 않는 고속 In-Memory 스캔을 지원하며, 이미 정리가 완료된 파일은 지능적으로 건너뜁니다(Skip).

**🧠 지능형 타이틀 & 볼륨 추출 엔진 (Deep Scan 파서)**
* 다운로더가 생성한 무의미한 25자 이상의 해시(Hash) 폴더명이나 껍데기 폴더(`temp` 등)를 무시하고, 내부 가장 깊은 곳을 역탐색하여 진짜 책 제목을 구출해 냅니다.
* `(미완)`, `[고화질]` 등 불필요한 태그를 자동 정제하며, 단순 숫자 폴더(`01`, `02`)도 자동으로 '권/화' 단위로 스마트하게 네이밍합니다.

**🔄 스마트 내부 파일명 변경 & 출력 경로 제어**
* 난잡한 내부 이미지 이름을 규칙에 맞게 일괄 정리합니다. (예: 기본 숫자 패딩, 영문 도서 스타일, 압축파일명 동기화 등 지원)
* 완료된 파일이 저장될 출력 경로를 개별 텍스트 필드로 직접 제어하거나, 체크된 항목을 원클릭으로 일괄 변경(기본값/책제목)할 수 있습니다.

**📂 하위 폴더 평탄화 & 완벽한 자연 정렬 (Natural Sort)**
* e-book 리더기에서 인식 오류를 일으키는 불필요한 이중/삼중 폴더를 제거하고 이미지를 최상단으로 끌어올립니다.
* 슬래시(`/`) 기반의 뎁스 인식형 자연 정렬 알고리즘을 적용하여, 폴더 계층과 파일 순서가 윈도우 탐색기와 완벽하게 동일하게 정렬됩니다.

**⚡ 초고속 다중 스레드 WebP 변환**
* 무거운 JPG/PNG 이미지를 고효율 WebP 포맷으로 일괄 변환하여 디스크 용량을 획기적으로 절약합니다.
* 다중 코어(Multi-threading)를 100% 활용해 변환 속도를 극대화했으며, 화질 조절 슬라이더(100% 무손실 압축 포함)를 제공합니다.

**📦 포맷 자동 변환**
* ZIP, CBZ, CBR, 7Z 파일 간의 포맷을 클릭 한 번으로 자유롭게 변환합니다.

**🔒 극대화된 시스템 안정성 및 편의성**
* **메모리 안정성 보장:** 수천 개의 파일을 드래그 앤 드롭해도 뻗지 않으며, 윈도우 11 파일 탐색기 충돌(튕김) 현상을 원천 차단했습니다.
* **안전한 임시 폴더 운용:** 시스템 임시 폴더에 고유 식별자(UUID)를 부여해 작업하므로, 네트워크 드라이브(NAS) 작업 시에도 쓰기 오류나 잔여 찌꺼기가 남지 않습니다.
* **사용자 편의성:** 스마트 리스트 자동 선택(마우스 없이 연속 삭제 가능), 작업 완료 알림음(On/Off), 자동 업데이트 알림, CPU 안전 제한(Safe Limit), 원본 백업(bak)을 완벽 지원합니다.

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
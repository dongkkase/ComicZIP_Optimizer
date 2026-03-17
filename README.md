# 📚 ComicZIP Optimizer

[English](#-english) | [한국어](#-한국어)

---
<kbd>![Demo](https://raw.githubusercontent.com/dongkkase/ComicZIP_Optimizer/main/demo/demo.gif?v=2)</kbd>
---

<a id="-english"></a>
## 🇬🇧 English
<kbd>![image](https://raw.githubusercontent.com/dongkkase/ComicZIP_Optimizer/main/demo/demo1_en.png)</kbd>
<kbd>![image](https://raw.githubusercontent.com/dongkkase/ComicZIP_Optimizer/main/demo/demo2_en.png)</kbd>
<kbd>![image](https://raw.githubusercontent.com/dongkkase/ComicZIP_Optimizer/main/demo/demo3_en.png)</kbd>
<kbd>![image](https://raw.githubusercontent.com/dongkkase/ComicZIP_Optimizer/main/demo/demo4_en.png)</kbd>
<kbd>![image](https://raw.githubusercontent.com/dongkkase/ComicZIP_Optimizer/main/demo/demo5_en.png)</kbd>

**ComicZIP Optimizer** is a smart GUI tool designed for comic/manga collectors and e-book reader users (Plex, Kavita, YACReader, Komga, etc.). It helps you easily rename inner images, flatten nested folders, convert images to WebP, and manage metadata—all without manually extracting the archives.

<p align="center">
</p>

### ✨ Key Features

**🚀 Metadata Auto-Match & High Search Accuracy**
* **Enhanced Search Rate:** Supports 5 major databases (Ridibooks, Aladin, Comic Vine, Anilist, Google Books) to provide highly accurate search results for both local and foreign comics.
* **Series Auto-Match:** Scans folder names to fetch and apply the best metadata to all books in a series with a single click.
* Edits and saves standard `ComicInfo.xml` metadata inside archives (ZIP, CBZ, 7Z, RAR, CBR).

**🌐 Multi-API Search & Smart AI Translation**
* **AI Smart Translation:** Utilizes OpenAI/Gemini to translate Korean titles to official English release names, greatly improving search success rates on foreign DBs.
* **Tag Standardization:** Define custom rules (e.g., `Shounen -> Boy`) to unify tags across different APIs.
* **Multilingual UI:** Supports English, Korean, and Japanese seamlessly.

**🎨 Remastered UX/UI & Workflow Automation**
* Features crisp vector icons powered by FontAwesome (`qtawesome`).
* Non-intrusive **Toast Notifications** prevent workflow interruption.
* **Scroll Spy Navigation:** The side menu dynamically highlights sections as you scroll through the metadata fields.
* **Auto Workflow Transfer:** Transfers processed files from the Renamer tab (Tab 2) directly to the Metadata tab (Tab 3) for a smooth workflow.

**🚀 Smart Archive Reorganization**
* Scans integrated archives containing multiple volumes, separating, merging, and repackaging them into clean, individual volume archives.
* High-speed In-Memory scanning previews massive files without extracting them to disk.

**🧠 Intelligent Title & Volume Extraction**
* Ignores meaningless Hash folder names and extracts real comic titles by scanning the archive.
* Cleans up bracket tags and extracts volume/chapter numbers smartly.

**🔄 Batch Inner Renaming & Folder Flattening**
* Uniformly renames inner image files according to preset rules.
* Removes unnecessary nested folders (double depths) that cause reading errors in e-book readers, pulling all images to the root.

**⚡ Multi-threaded WebP Conversion**
* Batch-converts JPG/PNG images to the highly efficient WebP format, saving disk space utilizing CPU Multi-threading.

**🔒 System Stability**
* Improved SQLite concurrency handling and API Rate Limit (429) protections.
* Password masking for API keys to enhance security.
* Safe Temp Operations with unique UUIDs prevent write errors on Network Drives (NAS).

### 🚀 How to Run

1. Go to the [Releases](https://github.com/dongkkase/ComicZIP_Optimizer/releases) page.
2. Download the latest `ComicZIP_Optimizer.zip` file.
3. Extract the ZIP file and run the executable (`.exe`). No installation is required!

### 🛠️ Tech Stack
* Python 3
* PyQt6 (GUI Framework)
* QtAwesome (Vector Icons)
* Pillow (Image Processing)
* 7-Zip (`7za.exe` for archive handling)

### 📝 License
This project is licensed under the **[MIT License](LICENSE)**.
* **7-Zip**: This application bundles `7za.exe`, licensed under the GNU LGPL and unRAR restriction. Visit [7-zip.org](https://www.7-zip.org/).

<br>

---

<a id="-한국어"></a>
## 🇰🇷 한국어
<kbd>![image](https://raw.githubusercontent.com/dongkkase/ComicZIP_Optimizer/main/demo/demo1_ko.png)</kbd>
<kbd>![image](https://raw.githubusercontent.com/dongkkase/ComicZIP_Optimizer/main/demo/demo2_ko.png)</kbd>
<kbd>![image](https://raw.githubusercontent.com/dongkkase/ComicZIP_Optimizer/main/demo/demo3_ko.png)</kbd>
<kbd>![image](https://raw.githubusercontent.com/dongkkase/ComicZIP_Optimizer/main/demo/demo4_ko.png)</kbd>
<kbd>![image](https://raw.githubusercontent.com/dongkkase/ComicZIP_Optimizer/main/demo/demo5_ko.png)</kbd>

**ComicZIP Optimizer(코믹집 옵티마이저)**는 만화/코믹스 수집가 및 e-book 리더기(Kavita, Plex, YACReader, Komga 등) 사용자를 위한 GUI 기반 라이브러리 최적화 툴입니다. 
압축 파일을 풀지 않고도 내부 이미지 파일명 일괄 변경, 폴더 구조 평탄화, 다중 코어 WebP 변환, 그리고 메타데이터(`ComicInfo.xml`) 관리까지 간편하게 처리할 수 있습니다.

<p align="center">
</p>

### ✨ 주요 기능

**🚀 뛰어난 검색률과 메타데이터 자동 매칭**
* **높은 검색 정확도:** 리디북스, 알라딘, Comic Vine, Anilist(GraphQL), Google Books 등 5개의 주요 API를 지원하여 국내외 도서의 메타데이터 검색 성공률을 크게 높였습니다.
* **시리즈 자동 매칭:** 폴더(시리즈) 이름을 기반으로 최적의 메타데이터를 검색하여, 폴더 내 모든 책에 일괄 적용해 줍니다.
* 압축 파일(ZIP, CBZ, 7Z, RAR, CBR) 내부에 범용 규격인 `ComicInfo.xml` 메타데이터를 직접 편집하고 저장합니다.

**🌐 다중 DB 검색 및 AI 스마트 번역**
* **AI 스마트 번역:** OpenAI 및 Gemini API를 활용하여 해외 DB 검색 시 한글 제목을 공식 영문 발매명으로 치환하여 검색 정확도를 한층 더 끌어올렸습니다.
* **태그 표준화 규칙:** 사용자 환경설정에서 나만의 치환 규칙(예: `Shounen, 소년만화 -> 소년`)을 등록하여 각기 다른 API의 태그를 일관성 있게 통일할 수 있습니다.
* **다국어 UI 지원:** 한국어, 영어에 더해 **일본어(日本語)** 환경을 지원합니다.

**🎨 직관적인 UX/UI 및 워크플로우 자동화**
* FontAwesome(`qtawesome`) 벡터 아이콘을 도입하여 깔끔한 디자인을 제공합니다.
* **토스트(Toast) 알림:** 작업 흐름을 방해하던 중앙 팝업창 대신, 화면 하단에서 부드럽게 나타나는 토스트 알림을 적용했습니다.
* **스크롤 스파이(Scroll Spy):** 메타데이터 상세 폼에서 스크롤을 내리면, 우측 내비게이션 메뉴가 현재 위치에 맞춰 실시간으로 강조됩니다.
* **작업 목록 자동 전달:** 탭 2(파일명 변경)에서 최적화 작업이 완료되면, 추가 확인 팝업 없이 탭 3(메타데이터 관리)으로 이동하며 작업 목록을 자연스럽게 전달합니다.

**📦 압축 파일 구조 일괄 정리 (분리 및 병합)**
* 내부에 여러 권의 책이 섞여 있는 통합 압축파일을 스캔하여, 각 권별로 분리 및 병합한 후 재압축합니다.
* 디스크에 압축을 풀지 않는 In-Memory 스캔을 지원하며, 트리(Tree) 형태의 미리보기를 제공합니다.

**🧠 지능형 타이틀 & 볼륨 추출 엔진**
* 의미 없는 긴 해시(Hash) 폴더명 등을 무시하고 압축 파일 스캔을 통해 실제 책 제목을 추출합니다.
* 불필요한 태그를 정제하고, 권/화(Volume/Chapter) 번호를 지능적으로 분석합니다.

**🔄 내부 파일명 변경 & 하위 폴더 평탄화**
* 난잡한 내부 이미지 이름을 규칙에 맞게 일괄 정리합니다.
* e-book 리더기에서 인식 오류를 일으키는 불필요한 하위 폴더를 제거하여 이미지를 최상단으로 정리합니다.

**⚡ 다중 스레드 WebP 변환**
* 용량이 큰 JPG/PNG 이미지를 고효율 WebP 포맷으로 변환하여 디스크 공간을 절약합니다. (CPU 다중 코어 활용)

**🔒 시스템 안정성**
* SQLite 다중 스레드 동시성 에러(Lock) 방지 및 API 과부하(Rate Limit) 대응 로직을 적용했습니다.
* API Key 입력 란에 패스워드 마스킹 및 토글 버튼을 추가하여 보안성을 개선했습니다.

### 🚀 실행 방법

1. [Releases](https://github.com/dongkkase/ComicZIP_Optimizer/releases) 페이지로 이동합니다.
2. 최신 버전의 `ComicZIP_Optimizer.zip` 파일을 다운로드합니다.
3. 압축을 풀고 안에 있는 실행 파일(`.exe`)을 실행하세요. (별도 설치 불필요)

### 🛠️ 사용 기술
* Python 3
* PyQt6 (UI 프레임워크)
* QtAwesome (벡터 아이콘)
* Pillow (이미지 처리)
* 7-Zip (`7za.exe` 압축 엔진)

### 📝 라이선스 (License)
이 프로젝트는 **[MIT License](LICENSE)** 를 따릅니다.
* **7-Zip**: 본 프로그램은 파일 압축/해제를 위해 `7za.exe`를 내부적으로 사용하며, 해당 파일은 GNU LGPL 라이선스를 따릅니다. 자세한 정보는 [7-zip.org](https://www.7-zip.org/)에서 확인할 수 있습니다.

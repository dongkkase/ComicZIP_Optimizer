# ComicZIP Optimizer

**This program supports `Korean`, `English`, `Japanese`.**

**The program description on the wiki page is only available in `Korean`. Please use Chrome's translation feature.**

**ComicZIP Optimizer**는 만화 및 코믹스 압축 파일(ZIP, CBZ, CBR, 7Z)을 가장 효율적으로 관리하고 최적화할 수 있는 **올인원 라이브러리 도구**입니다. 

클릭 몇 번만으로 복잡한 압축 파일의 내부 구조를 정리하고, 이미지 파일명을 나만의 규칙대로 일괄 수정할 수 있습니다. 특히 리디북스, 알라딘, Google Books, AniList, Comic Vine 등 다양한 국내외 API와 연동하여 글로벌 표준인 `ComicInfo.xml` 메타데이터를 손쉽게 구축할 수 있습니다. 

이를 통해 **Kavita, YACReader, Komga, Panels** 등 다양한 만화 관리 서버 및 뷰어에서 가장 완벽하고 쾌적한 독서 환경을 경험해 보세요!


<div align="center">

[![Issues](https://img.shields.io/badge/Issues-질문,%20의견,%20버그%20제보-D21F3C?style=for-the-badge&logo=github)](https://github.com/dongkkase/ComicZIP_Optimizer/issues)
[![Wiki](https://img.shields.io/badge/Wiki-상세한%20설명-1F425F?style=for-the-badge&logo=read-the-docs)](https://github.com/dongkkase/ComicZIP_Optimizer/wiki)
[![Download](https://img.shields.io/badge/Download-최신버전%20다운로드-238636?style=for-the-badge&logo=github)](https://github.com/dongkkase/ComicZIP_Optimizer/releases)

</div>

<kbd>![image](https://raw.githubusercontent.com/dongkkase/ComicZIP_Optimizer/main/demo/demo3.png)</kbd>
<kbd>![image](https://raw.githubusercontent.com/dongkkase/ComicZIP_Optimizer/main/demo/demo4.png)</kbd>
<kbd>![image](https://raw.githubusercontent.com/dongkkase/ComicZIP_Optimizer/main/demo/demo5.png)</kbd>
<kbd>![image](https://raw.githubusercontent.com/dongkkase/ComicZIP_Optimizer/main/demo/demo6.png)</kbd>
<kbd>![image](https://raw.githubusercontent.com/dongkkase/ComicZIP_Optimizer/main/demo/demo7.png)</kbd>
<kbd>![image](https://raw.githubusercontent.com/dongkkase/ComicZIP_Optimizer/main/demo/demo1.png)</kbd>

---

## ✨ 핵심 기능 (Key Features)

### 1. 직관적인 탐색 및 스마트 필터링
* **메타데이터 스캔:** 수많은 압축 파일 중 `ComicInfo.xml`이 적용된 파일과 누락된 파일을 한눈에 필터링하고 쉽게 수정할 수 있습니다.
* **초고속 워크플로우:** 작업하려는 파일을 선택하고 단축키(`F1`, `F2`, `F3`)를 누르면 즉시 '최적화' 및 '메타데이터 편집' 탭으로 전송되어 빠르게 작업할 수 있습니다.
* **스마트 중복 검사:** 미리 설정한 디렉터리와 파일명을 비교하여 중복 여부를 체크합니다. 제목이 비슷하더라도 일치율, 파일 용량 등을 대조하여 정확한 중복 판별이 가능합니다.

### 2. 압축 파일 구조 평탄화 (Flattening)
* **이중 폴더 제거:** 압축 파일 내부에 뷰어 인식을 방해하는 복잡한 다중 폴더 구조를 감지하여, 모든 이미지를 최상단(Root)으로 꺼내어 재배치합니다.
* **스마트 폴더명 추출:** 폴더를 제거할 때 기존 폴더명에 포함된 중요한 정보(`[시즌1]`, `[1권]` 등)를 파일명 접두어로 자동 보존하여 정보 유실을 막습니다.
* **권/화(Vol/Ch) 수정:** 단행본의 권수(Volume)나 챕터(Chapter) 정보를 직관적으로 손쉽게 변경할 수 있습니다.

### 3. 이미지 최적화 및 일괄 리네임
* **표준 넘버링 리네임:** 뒤죽박죽 섞인 내부 이미지 파일명을 사용자가 지정한 도서 스타일 패턴(`Cover`, `Page_001`, `002` 등)으로 깔끔하게 일괄 변경합니다.
* **강력한 용량 압축 & WebP 변환:** 압축 파일 내부의 모든 이미지를 고효율 **WebP** 포맷으로 강제 변환하거나, 환경 설정에서 지정한 압축률(%)에 따라 크기를 줄여 저장 공간을 획기적으로 확보합니다.
* **EXIF 데이터 제거:** 이미지 파일에 포함된 불필요한 EXIF 메타 정보를 제거하여 추가적인 용량 최적화를 수행합니다.
* **순서 재배치:** 압축 파일 내부 이미지들의 순서가 잘못된 경우, 프로그램 내에서 드래그하여 올바른 순서로 바로잡을 수 있습니다.

### 4. AI 기반 스마트 메타데이터 관리 (`ComicInfo.xml`)
* **다중 API 검색 지원:** 리디북스, 알라딘, Google Books, AniList, Comic Vine 등 국내외 주요 도서/코믹스 DB에서 정보를 검색하고 일괄 적용합니다.
* **AI 검색어 최적화:** Gemini 및 OpenAI API와 연동하여, 해외 DB 검색 시 한글 제목을 '공식 영문 발매명'으로 자동 치환하여 검색 성공률을 극대화합니다.
* **시리즈 자동 매칭 & 일괄 적용:** 폴더명만으로 작품을 인식하여, 1권부터 100권까지의 전체 시리즈에 동일한 메타데이터와 태그를 원클릭으로 자동 주입합니다.

### 5. 다중 스레드 성능 & 다국어 지원
* **안전한 병렬 처리(Multi-threading):** 사용자의 PC 스펙을 자동으로 분석하여, 시스템에 과부하를 주지 않는 '안전 코어 수' 한도 내에서 빠르고 쾌적하게 다중 작업을 수행합니다.
* **다국어 UI:** 글로벌 사용자들을 위해 한국어, 영어, 일본어를 기본 지원합니다.

---

## 설치 및 실행 (Installation)

본 프로그램은 빌드된 파일을 직접 실행하거나, 파이썬 소스 코드로 직접 실행 및 빌드 스크립트를 통해 단일 실행 파일(`.exe`)로 만들 수 있습니다.
1. [Releases](https://github.com/dongkkase/ComicZIP_Optimizer/releases) 페이지로 이동합니다.
2. 최신 버전의 `ComicZIP_Optimizer.zip` 파일을 다운로드합니다.
3. 압축을 풀고 안에 있는 실행 파일(`.exe`)을 실행하세요. (별도 설치 불필요)

---
## 상세 사용 가이드 (Wiki)
각 기능별 상세한 사용법과 설정 방법은 공식 [Wiki](https://github.com/dongkkase/ComicZIP_Optimizer/wiki)를 참조해 주세요.

---
### 사용 기술
- **Python 3**
- **PyQt6** (UI 프레임워크)
- **QtAwesome** (벡터 아이콘)
- **Pillow** (파이썬 이미지 처리 라이브러리)
- **7-Zip** (`7za.exe` 고속 파일 압축/해제 엔진)
- **libjpeg-turbo** (`jpegtran.exe` JPEG 무손실/손실 최적화 엔진)
- **pngquant** (`pngquant.exe` PNG 색상 손실 압축 엔진)
- **WebP** (`cwebp.exe` WebP 이미지 변환 엔진)

---
## 라이선스 (License)

이 프로젝트는 [MIT License](https://github.com/dongkkase/ComicZIP_Optimizer/blob/main/LICENSE)를 따릅니다. 

본 프로그램은 원활한 파일 처리 및 이미지 최적화를 위해 아래의 외부 도구(바이너리)를 내부적으로 포함하여 사용하고 있으며, 각 도구는 해당 프로젝트의 라이선스 규정을 따릅니다.

- **7-Zip (`7za.exe`)**: GNU LGPL 라이선스를 따릅니다. ([7-zip.org](https://www.7-zip.org/))
- **libjpeg-turbo (`jpegtran.exe`)**: IJG License, Modified BSD, zlib License를 따릅니다. ([libjpeg-turbo.org](https://libjpeg-turbo.org/))
- **pngquant (`pngquant.exe`)**: GPLv3 라이선스를 따릅니다. ([pngquant.org](https://pngquant.org/))
- **WebP (`cwebp.exe`)**: Google의 WebP BSD 라이선스를 따릅니다. ([developers.google.com/speed/webp](https://developers.google.com/speed/webp/))


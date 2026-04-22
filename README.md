# ComicZIP Optimizer

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) [![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/) [![PyQt6](https://img.shields.io/badge/UI-PyQt6-green.svg)](https://www.riverbankcomputing.com/software/pyqt/)

**ComicZIP Optimizer**는 압축 파일(ZIP, CBZ, CBR, 7Z)을 위한 올인원 라이브러리 메타데이터 최적화 도구입니다. 

파일을 한 번에 정리하고, 이미지 파일명을 표준화하며, 글로벌 표준 `ComicInfo.xml` 메타데이터를 기입하여 **Kavita, Komga, Panels**와 같은 스마트 코믹 뷰어에서 최고의 독서 환경을 구축할 수 있도록 돕습니다.


<kbd>![image](https://raw.githubusercontent.com/dongkkase/ComicZIP_Optimizer/main/demo/demo1.png)</kbd>
<kbd>![image](https://raw.githubusercontent.com/dongkkase/ComicZIP_Optimizer/main/demo/demo2.png)</kbd>
<kbd>![image](https://raw.githubusercontent.com/dongkkase/ComicZIP_Optimizer/main/demo/demo3.png)</kbd>
<kbd>![image](https://raw.githubusercontent.com/dongkkase/ComicZIP_Optimizer/main/demo/demo4.png)</kbd>
<kbd>![image](https://raw.githubusercontent.com/dongkkase/ComicZIP_Optimizer/main/demo/demo5.png)</kbd>
<kbd>![image](https://raw.githubusercontent.com/dongkkase/ComicZIP_Optimizer/main/demo/demo6.png)</kbd>
<kbd>![image](https://raw.githubusercontent.com/dongkkase/ComicZIP_Optimizer/main/demo/demo7.png)</kbd>

---

## 핵심 기능

### 1. 폴더 탐색기 및 메타데이터 필터링
* **메타데이터 스캔**: 수많은 압축 파일 중 `ComicInfo.xml`이 적용된 파일과 누락된 파일을 한눈에 식별합니다.
* **스마트 워크플로우**: 누락된 파일을 선택하고 단축키(`F2`, `F3`)를 누르면 즉시 최적화 및 메타데이터 편집 탭으로 전송됩니다.

### 2. 압축 파일 구조 평탄화 (Folder Flattening)
* **하위 폴더 제거**: 압축 파일 내부에 복잡하게 얽힌 다중 폴더 구조를 감지하여, 모든 이미지를 최상단(Root)으로 꺼내어 뷰어 인식 오류를 해결합니다.
* **스마트 폴더명 추출**: 기존 폴더명에 있던 `[시즌1]`, `[1권]` 등의 중요 정보를 파일명 접두어로 자동 보존합니다.

### 3. 내부 파일명 일괄 변경 & WebP 포맷 최적화
* **표준 넘버링 규칙**: 뒤죽박죽인 이미지 파일명을 `Cover`, `Page_001`, `002` 등 사용자가 지정한 깔끔한 도서 스타일 패턴으로 일괄 변경합니다.
* **일괄 WebP 변환**: 압축 파일 내부의 모든 이미지를 고효율 WebP 포맷으로 강제 변환하여, 화질 저하 없이 디스크 용량을 획기적으로 줄입니다.

### 4. 스마트 메타데이터 관리 (ComicInfo.xml)
* **다중 API 검색 지원**: 리디북스, 알라딘, Google Books, Anilist, Comic Vine에서 도서 정보를 검색하고 일괄 적용합니다.
* **🤖 AI 검색어 최적화**: Gemini 및 OpenAI API를 연동하여, 해외 DB(Vine, Anilist 등) 검색 시 한글 제목을 '공식 영문 발매명'으로 자동 치환하여 검색 성공률을 극대화합니다.
* **시리즈 자동 매칭**: 폴더명만으로 작품을 인식해 시리즈 전체(1권~100권)에 동일한 메타데이터와 태그를 원클릭으로 자동 주입합니다.

### 5. 다중 스레드 성능 & 다국어 UI
* **안전한 병렬 처리**: 사용자의 PC 스펙을 자동으로 분석하여, 시스템이 멈추지 않는 '안전 코어 수' 한도 내에서 초고속 다중 스레드 작업을 수행합니다.
* **다국어 지원**: 한국어, 영어, 일본어 UI를 완벽하게 지원합니다.

---

## 🛠️ 설치 및 실행 (Installation)

본 프로그램은 빌드된 파일을 직접 실행하거나, 파이썬 소스 코드로 직접 실행 및 빌드 스크립트를 통해 단일 실행 파일(`.exe`)로 만들 수 있습니다.
1. [Releases](https://github.com/dongkkase/ComicZIP_Optimizer/releases) 페이지로 이동합니다.
2. 최신 버전의 `ComicZIP_Optimizer.zip` 파일을 다운로드합니다.
3. 압축을 풀고 안에 있는 실행 파일(`.exe`)을 실행하세요. (별도 설치 불필요)

---
## 상세 사용 가이드 (Wiki)
각 기능별 상세한 사용법과 설정 방법은 공식 [Wiki](https://github.com/dongkkase/ComicZIP_Optimizer/wiki)를 참조해 주세요.

---
### 사용 기술
- Python 3
- PyQt6 (UI 프레임워크)
- QtAwesome (벡터 아이콘)
- Pillow (이미지 처리)
- 7-Zip (`7za.exe` 압축 엔진)

---
## 라이선스 (License)

이 프로젝트는  [MIT License](https://github.com/dongkkase/ComicZIP_Optimizer/blob/main/LICENSE)를 따릅니다. 
- **7-Zip**: 본 프로그램은 파일 압축/해제를 위해 `7za.exe`를 내부적으로 사용하며, 해당 파일은 GNU LGPL 라이선스를 따릅니다. 자세한 정보는 [7-zip.org](https://www.7-zip.org/)에서 확인할 수 있습니다.


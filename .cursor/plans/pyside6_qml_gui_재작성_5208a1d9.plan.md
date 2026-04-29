---
name: PySide6 QML GUI 재작성
overview: 현재 PyQt6+FluentWidgets 기반 GUI를 PySide6+QML(Glassmorphism) 디자인으로 전면 재작성. 5대 뷰(Dashboard, Harvest, Processing, Library, Settings) 전체를 QML로 구현하고, Python 백엔드 모델과 워커를 PySide6 호환으로 전환.
todos:
  - id: phase0
    content: "Phase 0: PySide6 의존성 전환 + 워커 4개 Signal 변환"
    status: completed
  - id: phase1
    content: "Phase 1: Theme.qml + GlassCard + NavSidebar + main.qml 네비게이션 셸"
    status: completed
  - id: phase2
    content: "Phase 2: Python 백엔드 모델 5개 (dashboard, harvest, processing, library, settings)"
    status: completed
  - id: phase3
    content: "Phase 3: DashboardView.qml (GPU/CPU 모니터 + 파이프라인 현황 + 큐)"
    status: completed
  - id: phase4
    content: "Phase 4: HarvestView.qml (검색 + 폴더/INBOX 스캔 + 카드 그리드)"
    status: completed
  - id: phase5
    content: "Phase 5: ProcessingView.qml (STT 큐 + 자막 워커 연결 + 진행률)"
    status: completed
  - id: phase6
    content: "Phase 6: LibraryView.qml + LibraryDetail.qml (포스터 그리드 + 상세 + 필터)"
    status: completed
  - id: phase7
    content: "Phase 7: SettingsView.qml (API/경로/테마/모델/옵션 + DPI 우회 실제 연결)"
    status: completed
isProject: false
---

# PySide6 + QML Glassmorphism GUI 전면 재작성

## 핵심 결정

- **PyQt6 + FluentWidgets 제거** -> **PySide6 + 순수 QML** 전환
- PySide6는 Qt 공식 Python 바인딩으로 QML 지원이 우수
- Glassmorphism, Neon Glow, 애니메이션은 QML 네이티브로 구현
- Python 워커(QThread) 로직은 Signal/Slot만 PySide6로 변환, 비즈니스 로직 유지
- `javstory.*` 백엔드 패키지는 변경 없음

## 새 디렉터리 구조

```
gui/
├── __init__.py
├── app.py                          # QGuiApplication + QQmlEngine 진입
├── models/                         # Python QObject/QAbstractListModel
│   ├── dashboard_model.py          #   GPU/CPU/큐 데이터
│   ├── harvest_model.py            #   수집 태스크 목록
│   ├── processing_model.py         #   STT 큐/진행률
│   ├── library_model.py            #   작품 목록 + 필터/정렬
│   ├── settings_model.py           #   설정 값 읽기/쓰기
│   └── pipeline_status_model.py    #   파이프라인 단계별 상태
├── workers/                        # QThread 워커 (PySide6 Signal)
│   ├── harvest_worker.py
│   ├── stt_worker.py
│   ├── pipeline_worker.py
│   └── subtitle_worker.py
└── qml/                            # 순수 QML UI
    ├── main.qml                    #   SplitView: Sidebar + StackView
    ├── Theme.qml                   #   디자인 토큰 (색상/폰트/간격)
    ├── views/
    │   ├── DashboardView.qml
    │   ├── HarvestView.qml
    │   ├── ProcessingView.qml
    │   ├── LibraryView.qml
    │   ├── LibraryDetail.qml
    │   └── SettingsView.qml
    └── components/
        ├── GlassCard.qml           #   Glassmorphism 카드
        ├── ActionButton.qml        #   Neon Glow 버튼
        ├── NavSidebar.qml          #   좌측 네비게이션
        ├── PipelineStage.qml       #   파이프라인 단계 표시
        ├── PosterCard.qml          #   작품 포스터 카드
        ├── SearchBar.qml           #   검색창
        ├── StatusBadge.qml         #   상태 배지 (Ready/Skipped/Error)
        ├── ProgressIndicator.qml   #   원형/선형 진행률
        ├── LogPanel.qml            #   로그 표시 패널
        └── ToastNotification.qml   #   토스트 알림
```

---

## Phase 0: 기반 전환

### 의존성 변경

- `requirements.txt`에서 `PyQt6`, `PyQt6-Fluent-Widgets` 제거
- `PySide6` 추가
- `win32mica`, `darkdetect` 유지 (Mica 효과용)
- `customtkinter`, `tkinterdnd2` 제거 (미사용)

### 진입점 변경 ([gui_main_v2.py](gui_main_v2.py))

```python
from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QQmlApplicationEngine
from gui.app import register_models, setup_engine
```

### 워커 Signal 전환

4개 워커 파일에서:
- `from PyQt6.QtCore import QThread, pyqtSignal` -> `from PySide6.QtCore import QThread, Signal`
- `pyqtSignal(...)` -> `Signal(...)`
- 나머지 비즈니스 로직은 그대로 유지

---

## Phase 1: 디자인 시스템 + 네비게이션 셸

### Theme.qml - 디자인 토큰

[GUI.md](GUI.md)의 색상 팔레트를 QML singleton으로 구현:

- Light/Dark 모드 자동 전환
- `primaryBlue`, `accentNeon`, `background`, `surface`, `glassBorder`
- 폰트: Pretendard (fallback: Noto Sans KR) - `heading`, `body`, `caption` 사전 정의
- 간격: `spacingSm(8)`, `spacingMd(16)`, `spacingLg(24)`, `spacingXl(32)`
- 반경: `radiusSm(8)`, `radiusMd(16)`, `radiusLg(24)`

### GlassCard.qml - 핵심 컴포넌트

```qml
Rectangle {
    color: Qt.rgba(15/255, 20/255, 40/255, 0.85)
    border.color: Qt.rgba(100/255, 180/255, 255/255, 0.35)
    border.width: 1
    radius: 16
    layer.enabled: true
    layer.effect: GaussianBlur { radius: 32; samples: 64 }
}
```

### main.qml - 네비게이션 구조

```
SplitView (horizontal)
├── NavSidebar (고정 280px, 축소 시 72px)
│   ├── 로고 + 앱 이름
│   ├── NavItem: Dashboard (아이콘 + 텍스트)
│   ├── NavItem: Harvest
│   ├── NavItem: Processing
│   ├── NavItem: Library
│   ├── 스페이서
│   └── NavItem: Settings (하단)
└── StackView
    └── 활성 뷰 (전환 애니메이션: push/pop fade)
```

### NavSidebar.qml

- 아이콘: Qt Material Icons 또는 커스텀 SVG
- 활성 항목: accentNeon 하이라이트 + 좌측 바 인디케이터
- hover 시 subtle glow 애니메이션
- 축소 토글: 아이콘만 / 아이콘+텍스트

---

## Phase 2: Python 백엔드 모델

### 모델 패턴

모든 모델은 `QObject`에 `Property`/`Signal`을 노출하고, QML에서 `rootContext.setContextProperty()`로 바인딩.

```python
from PySide6.QtCore import QObject, Property, Signal, Slot, QAbstractListModel, QModelIndex, Qt
```

### dashboard_model.py

- `gpuUsage`, `gpuTotal`, `cpuPercent`, `memPercent` (Property)
- `pendingQueue` (QAbstractListModel: 품번, 상태)
- 내부 QTimer(3초)로 `nvidia-smi` / `psutil` 폴링
- 기존 [gui/views/dashboard.py](gui/views/dashboard.py) 로직을 모델로 이동

### harvest_model.py

- `tasks` (QAbstractListModel: sku, status, progress, message)
- `@Slot(str)` `addTask(query)` - 품번 추가
- `@Slot(str)` `addFolder(path)` - 폴더 스캔
- `@Slot()` `scanInbox()` - INBOX 스캔
- `grokEnabled` (Property, 양방향)
- HarvestWorker 시그널 연결은 이 모델 내부에서 처리

### processing_model.py

- `queue` (QAbstractListModel: 파일명, 체크 여부, 상태)
- `currentFile`, `progressPercent`, `progressMessage` (Property)
- `isRunning` (Property)
- `@Slot(list)` `addFiles(paths)` - 파일 추가
- `@Slot()` `startStt()` / `stopStt()`
- STTWorker 연결 내부 처리

### library_model.py - 가장 복잡

- `works` (QAbstractListModel)
  - Roles: `productCode`, `titleKo`, `titleJa`, `actresses`, `coverPath`, `sceneCount`, `pipelineStage`, `releaseDate`, `canonicalBadge`
- `searchQuery` (Property, 양방향) - 180ms 디바운스 필터
- `sortMode` (Property) - 품번순/날짜순/씬수순
- `@Slot(str)` `loadDetail(productCode)` -> `currentDetail` (Property, QObject)
- `currentDetail`: Harvest 메타 + Grok JSON + 파이프라인 상태 + 스틸 목록
- 기존 [gui/library_data.py](gui/library_data.py)의 `load_library_summaries_from_session` + `filter_summaries` 활용

### settings_model.py

- 기존 [gui/views/settings.py](gui/views/settings.py)의 환경변수/secrets_manager 로직을 모델로 이동
- 각 설정값을 Property로 노출 (양방향 바인딩)
- `@Slot()` `saveApiKey()`, `savePaths()`, `saveOptions()`
- DPI 우회 스위치를 실제 `BypassManager`에 연결 (현재 미배선 수정)

---

## Phase 3: Dashboard 뷰

```
DashboardView.qml
├── 헤더: "JAVSTORY Pro" + 서브타이틀
├── Row
│   ├── GlassCard [GPU 모니터]
│   │   ├── VRAM 사용량 원형 게이지 (ProgressIndicator)
│   │   └── GPU 이름 + 온도
│   └── GlassCard [시스템 모니터]
│       ├── CPU 사용률 바
│       └── 메모리 사용률 바
├── GlassCard [A축 파이프라인 현황]
│   ├── 3단계 수평 표시: Harvest -> STT -> Subtitle
│   │   각 PipelineStage 컴포넌트 (아이콘+상태+진행률)
│   └── 원스톱 실행 ActionButton (Neon Glow)
├── GlassCard [작업 큐]
│   └── ListView: 대기 중인 품번 목록 (DB pending)
└── GlassCard [최근 로그]
    └── LogPanel (스크롤, 타임스탬프)
```

- PipelineStage 간 화살표: `Canvas`로 연결선 + 완료 시 accentNeon 색상 전환 애니메이션
- GPU 게이지: `Canvas`로 원형 아크 그리기, 값에 따라 색상 그라데이션 (녹/주/빨)

---

## Phase 4: Harvest 뷰

```
HarvestView.qml
├── 헤더: "수집 (Harvest)" + Grok 토글 스위치
├── SearchBar (다중 품번 지원, 엔터/붙여넣기)
├── Row [빠른 액션]
│   ├── ActionButton "폴더 수집"
│   ├── ActionButton "INBOX 스캔"
│   └── ActionButton "일괄 입력"
├── GridView / Flow [수집 카드 목록]
│   └── HarvestCard.qml (반복)
│       ├── 품번 텍스트 (Bold)
│       ├── 상태 StatusBadge
│       ├── ProgressIndicator (선형)
│       ├── 메시지 텍스트
│       └── 닫기 버튼 (hover 시 표시)
└── LogPanel [수집 로그]
```

- 카드 등장 애니메이션: opacity 0->1 + y 오프셋 (spring 효과)
- 완료 시 카드 테두리 accentNeon glow
- 에러 시 빨간 StatusBadge + shake 애니메이션
- 기존 harvest 뷰의 폴더/INBOX/다중 SKU 로직을 `harvest_model.py`로 이전

---

## Phase 5: Processing 뷰

```
ProcessingView.qml
├── 헤더: "전사 & 자막 (Processing)"
├── Row
│   ├── GlassCard [파일 선택 영역]
│   │   ├── "영상 파일 선택" ActionButton
│   │   ├── 현재 파일명 표시
│   │   └── DnD 드롭 영역
│   └── GlassCard [멀티파트]
│       └── "멀티파트 병합" ActionButton
├── GlassCard [전사 큐]
│   └── ListView (체크박스 행: 파일명, 상태 배지, DnD 정렬)
├── Row [컨트롤]
│   ├── ActionButton "STT 시작" (Primary)
│   ├── ActionButton "자막 생성" (Secondary) -- SubtitleWorker 연결
│   └── PushButton "중지"
├── GlassCard [진행률]
│   ├── 전체 ProgressIndicator
│   ├── 단계 표시: 오디오 추출 -> 전사 -> 후처리
│   └── 현재 단계 메시지
└── LogPanel
```

**핵심 개선**: 현재 미배선인 `SubtitleWorker`를 Processing 뷰에 연결.
- STT 완료 후 자동으로 "자막 생성" 버튼 활성화
- 자막 생성 클릭 시 `SubtitleWorker` 실행
- 진행률 패널에 STT/교정/번역 단계 구분 표시

---

## Phase 6: Library 뷰

```
LibraryView.qml
├── 헤더: "라이브러리"
├── Row [필터바]
│   ├── SearchBar (품번/제목/배우 통합 검색, 180ms 디바운스)
│   ├── ComboBox [정렬: 품번순/날짜(신)/날짜(구)/씬수]
│   └── ToggleGroup [뷰 모드: Grid / List]
├── GridView [작품 카드 그리드] (또는 ListView)
│   └── PosterCard.qml (반복)
│       ├── 커버 이미지 (hover: scale 1.05 + shadow 강화)
│       ├── 품번 (accentNeon)
│       ├── 제목 (1줄 말줄임)
│       ├── 배우명
│       ├── 파이프라인 StatusBadge 행 (H/S/T 아이콘)
│       └── 씬 수 배지
└── (클릭 시) LibraryDetail.qml (StackView push 또는 오버레이)

LibraryDetail.qml
├── Hero Section
│   ├── 커버 이미지 (height: 520, PreserveAspectCrop)
│   ├── Glass 오버레이
│   ├── 품번 (52px, ExtraBold, accentNeon + Glow)
│   ├── 제목 (KO/JA)
│   └── 배우 / 장르 / 메이커 / 발매일
├── GlassCard [파이프라인 상태]
│   ├── 3개 PipelineStage 수평 (Harvest / STT / Subtitle)
│   └── "A축 실행" ActionButton
├── GlassCard [시놉시스]
│   └── 접기/펼치기 가능한 텍스트
├── GlassCard [Grok 스토리 컨텍스트]
│   └── Grok JSON 요약 표시 (있으면)
├── GlassCard [스틸 갤러리]
│   └── Flow: 스틸 이미지 썸네일 (클릭 시 확대)
└── Row [액션]
    ├── ActionButton "Export 번들"
    ├── ActionButton "Grok 병합"
    └── ActionButton "폴더 열기"
```

**핵심 개선**:
- `library_data.py`의 `filter_summaries` / `sort_summaries` 를 모델에서 활용 (현재 미사용 중복 해소)
- Canonical 데이터 기반 필터 UI 추가 (씬 수 범위, 파이프라인 완료 여부)
- PosterCard hover 시 비디오 미리보기 (미래 확장 포인트)

---

## Phase 7: Settings 뷰

```
SettingsView.qml
├── 헤더: "설정"
├── ScrollView
│   ├── GlassCard [API 설정]
│   │   ├── PasswordField "OpenRouter API 키"
│   │   ├── TextField "Ollama URL"
│   │   └── ActionButton "저장"
│   ├── GlassCard [데이터 경로]
│   │   ├── PathField "INBOX 폴더" + 찾아보기
│   │   ├── PathField "미디어 루트" + 찾아보기
│   │   └── ActionButton "저장"
│   ├── GlassCard [외관]
│   │   └── SegmentedControl [Win11 / Light / Dark]
│   ├── GlassCard [STT]
│   │   └── ComboBox "Whisper 모델"
│   ├── GlassCard [번역]
│   │   └── ComboBox "번역 프로필"
│   └── GlassCard [기타]
│       ├── Switch "Grok 스토리 맥락"
│       └── Switch "DPI 우회" -- BypassManager 실제 연결
└── 하단 앱 버전 정보
```

**핵심 개선**: DPI 우회 스위치를 `javstory.utils.bypass_manager.BypassManager`에 실제 연결

---

## 구현 순서 요약

```
Phase 0  의존성 전환 + 워커 Signal 변환           (1일)
Phase 1  Theme + GlassCard + NavSidebar + main.qml (2일)
Phase 2  Python 백엔드 모델 5개                    (2일)
Phase 3  Dashboard 뷰                             (1일)
Phase 4  Harvest 뷰                               (2일)
Phase 5  Processing 뷰 + SubtitleWorker 배선       (2일)
Phase 6  Library 뷰 + Detail                      (3일)
Phase 7  Settings 뷰                              (1일)
```

## 주요 기술 참고

- QML 타입 등록: `qmlRegisterType` 또는 `@QmlElement` 데코레이터
- 리스트 모델: `QAbstractListModel` + `roleNames()` 오버라이드
- 이미지 로딩: QML `Image { source: "file:///" + model.coverPath }`
- 비동기: 워커는 기존과 동일하게 `QThread`, 시그널로 모델 업데이트
- Mica 효과: `win32mica`는 `QWindow` 핸들에 적용 (PySide6에서도 동일)

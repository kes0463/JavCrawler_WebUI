# JAVSTORY v2 Pro — PySide6 + QML UI 구현 스펙

## 1. 전체 디자인 시스템 (Design Tokens)

### 색상 팔레트

| 용도 | Light Theme | Dark Theme (Glassmorphism) | 비고 |
|------|-------------|---------------------------|------|
| Primary Blue | #0066FF | #00A8FF | 헤더, 주요 버튼 |
| Accent Neon | #00CCFF | #00E0FF | Glow, Hover 효과 |
| Background | #F8FAFC | #0F1321 | 메인 배경 |
| Surface / Card | #FFFFFF | rgba(15, 20, 40, 0.85) | Glass 카드 |
| Glass Border | #E2E8F0 | rgba(100, 180, 255, 0.35) | Glass 효과 테두리 |
| Text Primary | #1E2937 | #F1F5F9 | 주요 텍스트 |
| Text Secondary | #64748B | #94A3B8 | 보조 텍스트 |
| Status Ready | #10B981 | #10B981 | 완료 |
| Status Skipped | #F59E0B | #F59E0B | 스킵 |

### 글씨체 (Font)

- 기본 폰트: **Pretendard** (또는 Noto Sans KR)
- 품번: ExtraBold, 48~52px
- 제목: Bold, 24~28px
- 본문: Medium, 15px
- 보조 텍스트: Regular, 13px

### Glassmorphism 효과 (Dark Theme 전용)

```qml
background: Rectangle {
    color: "transparent"
    border.color: "#00A8FF"
    border.width: 1
    radius: 16
    layer.enabled: true
    layer.effect: GaussianBlur { radius: 32; samples: 64 }
}
```

---

## 2. 공통 컴포넌트 (Reusable Components)

| 컴포넌트 | 역할 |
|----------|------|
| `GlassCard.qml` | 모든 카드에 사용 |
| `ActionButton.qml` | 네온 Glow + Hover 애니메이션 |
| `PipelineStage.qml` | 워크플로우 단계 표시 |
| `PosterCard.qml` | 포스터 카드 (Hover Video Preview 포함) |
| `MasonryGallery.qml` | Pinterest 스타일 갤러리 |
| `SceneSummaryCard.qml` | 씬별 스토리 요약 카드 |

### ActionButton 예시

```qml
Button {
    scale: hovered ? 1.08 : (pressed ? 0.95 : 1.0)
    Behavior on scale { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }

    background: Rectangle {
        radius: 12
        color: hovered ? "#00A8FF" : "#0066FF"
        layer.enabled: true
        layer.effect: DropShadow {
            color: "#00E0FF"
            radius: hovered ? 25 : 12
            opacity: 0.6
        }
    }
}
```

---

## 3. 화면별 상세 스펙

### 3.1 워크플로우 & 파이프라인 대시보드 (`WorkflowDashboard.qml`)

**레이아웃**

- Left Sidebar (고정 너비 280px)
- Main Area (ColumnLayout)
  - 상단: A축 / B축 파이프라인 카드 (2열)
  - 중간: 배치 워치독 패널 (INBOX, PROCESSING, COMPLETED, ERROR)
  - 중앙: 큰 원스톱 실행 버튼
  - 하단: 최근 로그 패널

**주요 크기**

| 요소 | 크기 |
|------|------|
| A축 / B축 카드 | 너비 `parent.width * 0.48`, 높이 280px |
| Phase 카드 | 너비 180px, 높이 240px |
| 원스톱 버튼 | 너비 520px, 높이 120px |

**애니메이션**

- 단계 화살표: 선이 그려지는 `PathAnimation`
- 상태 등장: `Opacity + YAnimator` (Spring 효과)

---

### 3.2 작품 아카이브 화면 (`ArchiveList.qml`)

**Masonry Layout 구현**

```qml
Flow {
    anchors.fill: parent
    spacing: 24
    Repeater {
        model: archiveModel
        PosterCard {
            width: 280
            // height는 모델에서 aspectRatio로 동적 계산
        }
    }
}
```

**PosterCard Hover 효과**

- Scale: 1.08 + DropShadow 강도 증가
- Video Preview: 3초 루프 Video (opacity fade)

**상단 툴바**

- 검색창: 너비 520px
- View Toggle: Grid / List / Masonry (활성화 시 Neon Glow)

---

### 3.3 작품 상세 화면 (`WorkDetail.qml`)

**메인 구조**

```qml
ScrollView {
    ColumnLayout {
        // 1. Hero Section (대형 표지 이미지 + Glass 오버레이)
        // 2. Metadata 정보
        // 3. Pipeline Status Bar (4개 GlassCard 가로 배치)
        // 4. 씬별 스토리 요약
        // 5. 전체 스냅샷 Masonry Gallery
    }
}
```

**Hero Section**

- 표지 이미지 높이: 520px
- 품번 텍스트: 52px, ExtraBold, `#00E0FF` + Glow

**Pipeline Status Bar**

- Harvest / STT / Subtitle / 장면 분석 v2.1
- 각 카드에 진행바 + "재실행" 버튼

### FullscreenViewer.qml (별도 Window)

- FullScreen 모드
- 마우스 휠 줌 (`scale` 속성)
- 키보드 좌우 화살표 지원
- 타임코드 점프 버튼 → Python으로 video seek

---

## 4. Python ↔ QML 데이터 바인딩 예시

```python
engine = QQmlApplicationEngine()

rootContext = engine.rootContext()
rootContext.setContextProperty("archiveModel", archiveListModel)
rootContext.setContextProperty("currentWork", workDetailModel)

class WorkDetailModel(QObject):
    @Slot(str)
    def runPipelineStage(self, stage: str):
        # javstory/pipeline/orchestrator.py 호출
        pass
```

---

## 5. 추천 프로젝트 폴더 구조

```
JAVSTORY/
├── qml/
│   ├── main.qml                    # 메인 윈도우 + Splitter
│   ├── WorkflowDashboard.qml
│   ├── ArchiveList.qml
│   ├── WorkDetail.qml
│   ├── FullscreenViewer.qml
│   └── components/
│       ├── GlassCard.qml
│       ├── ActionButton.qml
│       ├── PosterCard.qml
│       ├── PipelineStage.qml
│       └── MasonryGallery.qml
├── main.py                         # 운영 진입점 (PySide6 + QML)
└── gui/
    ├── app.py                      # create_engine()
    ├── qml/                        # 운영 UI
    ├── models/                     # PySide6 QObject
    └── views/                      # [deprecated] PyQt6 Fluent
```

운영·레거시 구분: [`docs/architecture/ENTRYPOINTS.md`](docs/architecture/ENTRYPOINTS.md), [`gui/DEPRECATED_PYQT6.md`](gui/DEPRECATED_PYQT6.md)

---

## 6. 추가 구현 팁

- **테마 전환**: `Material.theme` 또는 커스텀 속성으로 Light/Dark 전환
- **Command Palette (Ctrl+K)**: `Popup + TextField + ListView`
- **Hover Video Preview**: `Video + MouseArea + OpacityAnimator`
- **Masonry Gallery**: `Flow + 동적 height 계산`
- **성능 최적화**: 스냅샷이 많을 때 `DelegateModel` 또는 Cache 사용

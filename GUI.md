(기준: 이전에 제가 생성한 3개 화면 — 워크플로우 대시보드, 작품 아카이브, 작품 상세 화면)
QML은 선언형이라 코드 몇 줄로 Glassmorphism, Neon Glow, Masonry, Hover Video Preview 등을 미친듯이 예쁘게 만들 수 있습니다. 아래는 실제 구현 가능한 수준의 상세 스펙입니다.
1. 전체 디자인 시스템 (Design Tokens)
색상 팔레트 (Hex + Alpha)


용도,Light Theme,Dark Theme (Glassmorphism),비고
Primary Blue,#0066FF,#00A8FF,"헤더, 버튼"
Accent Neon,#00CCFF,#00E0FF,"Glow, hover"
Background,#F8FAFC,#0F1321,메인 bg
Surface / Card,#FFFFFF,"rgba(15,20,40,0.85)",Glass
Glass Border,#E2E8F0,"rgba(100,180,255,0.35)",blur + border
Text Primary,#1E2937,#F1F5F9,-
Text Secondary,#64748B,#94A3B8,-
Status Ready,#10B981,#10B981,녹색
Status Skipped,#F59E0B,#F59E0B,주황






























































용도Light ThemeDark Theme (Glassmorphism)비고Primary Blue#0066FF#00A8FF헤더, 버튼Accent Neon#00CCFF#00E0FFGlow, hoverBackground#F8FAFC#0F1321메인 bgSurface / Card#FFFFFFrgba(15,20,40,0.85)GlassGlass Border#E2E8F0rgba(100,180,255,0.35)blur + borderText Primary#1E2937#F1F5F9-Text Secondary#64748B#94A3B8-Status Ready#10B981#10B981녹색Status Skipped#F59E0B#F59E0B주황
Glassmorphism 효과 (Dark 전용)
qmlbackground: Rectangle {
    color: "transparent"
    border.color: "#00A8FF"
    border.width: 1
    radius: 16
    layer.enabled: true
    layer.effect: GaussianBlur { radius: 32; samples: 64 }
    // + DropShadow { color: "#00E0FF"; radius: 20; opacity: 0.3 }
}
글씨체 (Font)

메인 폰트: Pretendard (또는 Noto Sans KR Bold/Medium/Regular) — Qt에서 FontLoader로 로드 추천
품번: font.weight: Font.ExtraBold, font.pixelSize: 48
제목: Bold 24~28px
본문: Medium 15px
작은 텍스트: Regular 13px
모든 텍스트에 font.kerning: true + renderType: Text.QtRendering

창 크기 추천

MainWindow: width: 1680, height: 960 (16:9 비율, 4K에서도 예쁨)

2. 공통 컴포넌트 (재사용 추천)

GlassCard.qml (모든 카드에 사용)
ActionButton.qml (네온 glow + scale 애니메이션)
PipelineStage.qml (워크플로우 단계)
PosterCard.qml (호버 시 비디오 미리보기)
MasonryGallery.qml (Flow + Repeater)
SceneSummaryCard.qml

ActionButton 예시 (QML)
qmlButton {
    id: btn
    text: "1-Stop 실행"
    background: Rectangle {
        radius: 12
        color: btn.hovered ? "#00A8FF" : "#0066FF"
        layer.enabled: true
        layer.effect: DropShadow { color: "#00E0FF"; radius: btn.hovered ? 25 : 12; opacity: 0.6 }
    }
    contentItem: Text { ... }
    
    // 애니메이션
    scale: btn.pressed ? 0.95 : (btn.hovered ? 1.08 : 1.0)
    Behavior on scale { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
}
3. 화면 별 상세 스펙 & QML 구조
화면 1. 워크플로우 & 파이프라인 대시보드 (WorkflowDashboard.qml)
레이아웃 구조

Left Sidebar (고정 280px)
Main Area: ColumnLayout
상단 Header (두 개의 큰 카드: A축 / B축)
중간: 배치 워치독 패널 (INBOX, PROCESSING 등)
중앙 큰 버튼: “발한영 기원” (원스톱 실행)
하단: 로그 패널


주요 컴포넌트 좌표/크기 (anchors 기준)

A축 카드: width: parent.width * 0.48, height: 280
B축 4-Phase: RowLayout, 각 Phase width: 180, height: 240
큰 실행 버튼: width: 520, height: 120, 중앙 정렬

애니메이션

단계별 화살표: SequentialAnimation으로 선이 그려지는 효과 (PathAnimation 또는 Rectangle + scale)
Ready 상태 등장: OpacityAnimator + YAnimator (spring 0.8)

화면 2. 작품 아카이브 (ArchiveList.qml)
Masonry Layout 구현
qmlFlow {
    anchors.fill: parent
    spacing: 24
    Repeater {
        model: archiveModel  // Python에서 ListModel 또는 QObjectList
        PosterCard {
            width: 280
            // height는 모델의 aspectRatio로 동적 계산
        }
    }
}
PosterCard hover 효과

Scale: 1.08 + DropShadow radius 증가
Video Preview: Video 컴포넌트 (3초 루프, opacity 0 → 1)

상단 툴바

검색창: TextField width 520px, 중앙
View Toggle (Grid/List/Masonry): 3개의 RoundButton (활성화 시 neon glow)

화면 3. 작품 상세 화면 (WorkDetail.qml)
메인 구조
qmlScrollView {
    ColumnLayout {
        // 1. Hero Section (표지 이미지 + 오버레이 Glass 패널)
        // 2. Metadata Row
        // 3. Pipeline Status Bar (4개의 GlassCard 가로 나열)
        // 4. 씬별 스토리 요약 (Row + Repeater)
        // 5. Masonry Snapshot Gallery
    }
}
Hero Section 상세

표지 이미지: Image fillMode: Image.PreserveAspectCrop, height: 520
오버레이 Glass: anchors.fill: image, radius: 20, color: rgba(15,20,40,0.75)
품번: Text { font.pixelSize: 52; font.weight: Font.ExtraBold; color: "#00E0FF" } + subtle glow

Pipeline Status Bar (가장 중요)

4개의 GlassCard 가로 배치
각 카드 안에 진행바 + “재실행” 버튼
Harvest / STT / Subtitle / 장면 분석 v2.1 상태 아이콘 (✓ / ⏳)

FullscreenViewer.qml (별도 Window)

Window { visibility: Window.FullScreen }
Image + MouseArea로 휠 줌 (scale property)
키보드: Keys.onLeftPressed, Keys.onRightPressed
타임코드 점프 버튼: Button → Python으로 video seek 시그널

4. Python ↔ QML 데이터 바인딩 (main.py 예시)
Pythonengine = QQmlApplicationEngine()
rootContext = engine.rootContext()

# Master DB + 파이프라인 상태
rootContext.setContextProperty("archiveModel", archiveListModel)  # QObjectListModel
rootContext.setContextProperty("currentWork", workDetailModel)    # QObject with properties

# 시그널
class WorkDetailModel(QObject):
    @Slot(str)
    def runPipelineStage(self, stage):
        # pipeline/orchestrator.py 호출
        pass
5. 추천 프로젝트 구조 (바로 복사해서 사용)
text/qml
├── main.qml                  # SplitView (Sidebar + StackView)
├── WorkflowDashboard.qml
├── ArchiveList.qml
├── WorkDetail.qml
├── components/
│   ├── GlassCard.qml
│   ├── ActionButton.qml
│   ├── PosterCard.qml
│   ├── PipelineStage.qml
│   └── MasonryGallery.qml
└── FullscreenViewer.qml
PySide6 main.py 핵심
Pythonif __name__ == "__main__":
    app = QApplication(sys.argv)
    engine = QQmlApplicationEngine()
    engine.load(QUrl.fromLocalFile("qml/main.qml"))
    # ... 기존 gui_main_v2.py 로직 그대로 유지

이 스펙대로 만들면 원본 JAVSTORY v2 Pro와 완벽 통일되면서도 프리미엄 QML 느낌이 제대로 납니다.
원하시면:

특정 화면 하나만 완전한 QML 코드 전체 드릴까요?
GlassCard.qml + PosterCard.qml + MasonryGallery.qml 실제 파일 형태로 만들어 드릴까요?
또는 테마 전환 버튼 + Command Palette (Ctrl+K)까지 추가 스펙 드릴까요?

말씀만 해 주세요. 바로 다음 단계로 넘어가겠습니다!4.2초전문가마크다운 문법으로 써줘아래는 PySide6 + QML로 구현하기 위한 상세 UI 스펙을 마크다운 문법으로 깔끔하게 정리한 버전입니다.

JAVSTORY v2 Pro - PySide6 + QML UI 구현 스펙
1. 전체 디자인 시스템 (Design Tokens)
색상 팔레트

































































용도Light ThemeDark Theme (Glassmorphism)비고Primary Blue#0066FF#00A8FF헤더, 주요 버튼Accent Neon#00CCFF#00E0FFGlow, Hover 효과Background#F8FAFC#0F1321메인 배경Surface / Card#FFFFFFrgba(15, 20, 40, 0.85)Glass 카드Glass Border#E2E8F0rgba(100, 180, 255, 0.35)Glass 효과 테두리Text Primary#1E2937#F1F5F9주요 텍스트Text Secondary#64748B#94A3B8보조 텍스트Status Ready#10B981#10B981완료Status Skipped#F59E0B#F59E0B스킵
글씨체 (Font)

기본 폰트: Pretendard (또는 Noto Sans KR)
Bold / Medium / Regular

품번: ExtraBold, 48~52px
제목: Bold, 24~28px
본문: Medium, 15px
보조 텍스트: Regular, 13px

Glassmorphism 효과 (Dark Theme 전용)
qmlbackground: Rectangle {
    color: "transparent"
    border.color: "#00A8FF"
    border.width: 1
    radius: 16
    layer.enabled: true
    layer.effect: GaussianBlur { radius: 32; samples: 64 }
}

2. 공통 컴포넌트 (Reusable Components)

GlassCard.qml — 모든 카드에 사용
ActionButton.qml — 네온 Glow + Hover 애니메이션
PipelineStage.qml — 워크플로우 단계 표시
PosterCard.qml — 포스터 카드 (Hover Video Preview 포함)
MasonryGallery.qml — Pinterest 스타일 갤러리
SceneSummaryCard.qml — 씬별 스토리 요약 카드

ActionButton 예시
qmlButton {
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

3. 화면 별 상세 스펙
3.1 워크플로우 & 파이프라인 대시보드 (WorkflowDashboard.qml)
레이아웃

Left Sidebar (고정 너비 280px)
Main Area (ColumnLayout)
상단: A축 / B축 파이프라인 카드 (2열)
중간: 배치 워치독 패널 (INBOX, PROCESSING, COMPLETED, ERROR)
중앙: 큰 “발한영 기원” (원스톱 실행) 버튼
하단: 최근 로그 패널


주요 크기

A축 / B축 카드: 너비 parent.width * 0.48, 높이 280px
Phase 카드: 너비 180px, 높이 240px
원스톱 버튼: 너비 520px, 높이 120px

애니메이션

단계 화살표: 선이 그려지는 PathAnimation
상태 등장: Opacity + YAnimator (Spring 효과)

3.2 작품 아카이브 화면 (ArchiveList.qml)
Masonry Layout 구현
qmlFlow {
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
PosterCard Hover 효과

Scale: 1.08 + DropShadow 강도 증가
Video Preview: 3초 루프 Video (opacity fade)

상단 툴바

검색창: 너비 520px
View Toggle: Grid / List / Masonry (활성화 시 Neon Glow)

3.3 작품 상세 화면 (WorkDetail.qml)
메인 구조
qmlScrollView {
    ColumnLayout {
        // 1. Hero Section (대형 표지 이미지 + Glass 오버레이)
        // 2. Metadata 정보
        // 3. Pipeline Status Bar (4개 GlassCard 가로 배치)
        // 4. 씬별 스토리 요약
        // 5. 전체 스냅샷 Masonry Gallery
    }
}
Hero Section

표지 이미지 높이: 520px
품번 텍스트: 52px, ExtraBold, #00E0FF + Glow

Pipeline Status Bar

Harvest / STT / Subtitle / 장면 분석 v2.1
각 카드에 진행바 + “재실행” 버튼

FullscreenViewer.qml (별도 Window)

FullScreen 모드
마우스 휠 줌 (scale 속성)
키보드 좌우 화살표 지원
타임코드 점프 버튼 → Python으로 video seek


4. Python ↔ QML 데이터 바인딩 예시
Pythonengine = QQmlApplicationEngine()

rootContext = engine.rootContext()
rootContext.setContextProperty("archiveModel", archiveListModel)
rootContext.setContextProperty("currentWork", workDetailModel)

# 시그널 연결 예시
class WorkDetailModel(QObject):
    @Slot(str)
    def runPipelineStage(self, stage: str):
        # pipeline/orchestrator.py 호출
        pass

5. 추천 프로젝트 폴더 구조
textJAVSTORY/
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
├── main.py                         # QQmlApplicationEngine 로드
└── gui/v2/                         # 기존 PyQt6 로직

6. 추가 추천 기능 구현 팁

테마 전환 — Material.theme 또는 커스텀 속성으로 Light/Dark 전환
Command Palette (Ctrl+K) — Popup + TextField + ListView
Hover Video Preview — Video + MouseArea + OpacityAnimator
Masonry Gallery — Flow + 동적 height 계산
성능 최적화 — 스냅샷이 많을 때 DelegateModel 또는 Cache 사용
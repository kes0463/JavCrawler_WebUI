pragma Singleton
import QtQuick

QtObject {
    id: theme

    // ── 테마 상태 ────────────────────────────────────
    readonly property int mode: SettingsModel.themeMode // 0=Win11, 1=Light, 2=Dark
    readonly property bool isDark: mode === 2 || (mode === 0 && SettingsModel.isSystemDark)

    // ── 색상 팔레트 ──────────────────────────────────
    readonly property color bgPrimary: {
        if (mode === 0) return "transparent" // Mica 효과를 위해 투명화
        return isDark ? "#0A0E1A" : "#F3F4F6"
    }
    readonly property color bgSecondary:     isDark ? "#101828" : "#FFFFFF"
    readonly property color surface:         isDark ? Qt.rgba(15/255, 20/255, 40/255, mode === 0 ? 0.35 : 0.85) : Qt.rgba(255/255, 255/255, 255/255, mode === 0 ? 0.35 : 0.80)
    readonly property color surfaceLight:    isDark ? Qt.rgba(30/255, 40/255, 70/255, mode === 0 ? 0.20 : 0.65) : Qt.rgba(0, 0, 0, mode === 0 ? 0.02 : 0.05)
    
    readonly property color glassBorder:     isDark ? Qt.rgba(100/255, 180/255, 255/255, mode === 0 ? 0.15 : 0.35) : Qt.rgba(0, 0, 0, mode === 0 ? 0.06 : 0.12)
    readonly property color glassBorderHover:isDark ? Qt.rgba(130/255, 210/255, 255/255, mode === 0 ? 0.30 : 0.55) : Qt.rgba(0, 0, 0, mode === 0 ? 0.10 : 0.20)
    readonly property color divider:         isDark ? Qt.rgba(255/255, 255/255, 255/255, 0.08) : Qt.rgba(0, 0, 0, 0.08)
    readonly property color rowHover:        isDark ? Qt.rgba(255/255, 255/255, 255/255, 0.05) : Qt.rgba(0, 0, 0, 0.035)
    readonly property color progressTrack:   isDark ? Qt.rgba(255/255, 255/255, 255/255, 0.10) : Qt.rgba(0, 0, 0, 0.10)

    readonly property color primaryBlue:     "#0088FF"
    readonly property color accentNeon:      {
        if (mode === 0 && !isDark) return "#0078D4" // Windows 11 기본 파란색
        return isDark ? "#00E5FF" : "#00A8CC"
    }
    readonly property color accentGlow:      {
        if (mode === 0 && !isDark) return Qt.rgba(0, 120/255, 212/255, 0.2)
        return isDark ? Qt.rgba(0, 229/255, 255/255, 0.4) : Qt.rgba(0, 168/255, 204/255, 0.2)
    }

    readonly property color textPrimary:     isDark ? "#F0F4FF" : "#111827"
    readonly property color textSecondary:   isDark ? Qt.rgba(240/255, 244/255, 255/255, 0.65) : "#4B5563"
    readonly property color textMuted:       isDark ? Qt.rgba(240/255, 244/255, 255/255, 0.40) : "#9CA3AF"

    readonly property color success:         "#10B981"
    readonly property color warning:         "#F59E0B"
    readonly property color error:           "#EF4444"

    readonly property color navBg:           {
        if (mode === 0) return "transparent" // 사이드바도 투명화하여 Mica 노출
        return isDark ? Qt.rgba(8/255, 12/255, 24/255, 0.92) : Qt.rgba(255/255, 255/255, 255/255, 0.90)
    }
    readonly property color navActive:       isDark ? Qt.rgba(0, 136/255, 255/255, 0.18) : Qt.rgba(0, 120/255, 212/255, 0.15)
    readonly property color navHover:        isDark ? Qt.rgba(255/255, 255/255, 255/255, 0.06) : Qt.rgba(0, 0, 0, 0.04)

    // ── 간격 ──────────────────────────────────────────
    readonly property int spacingXs:  6
    readonly property int spacingSm:  10
    readonly property int spacingMd: 18
    readonly property int spacingLg: 28
    readonly property int spacingXl: 36

    // ── 반경 ──────────────────────────────────────────
    readonly property int radiusSm:   8
    readonly property int radiusMd:  16
    readonly property int radiusLg:  24

    // ── 대시보드/큐 레이아웃 ──────────────────────────
    readonly property int queueCardHeaderHeight: 60
    readonly property int queueCardExpandedHeight: 420
    readonly property int queueRowHeight: 44
    /** 큐 카드 헤더 우측 영역(액션+토글) 고정 폭: 카드마다 위치 통일 */
    readonly property int queueHeaderRightWidth: 640
    /** 큐 카드 헤더 좌측 영역(제목+배지) 고정 폭: 액션 시작점 통일 */
    readonly property int queueHeaderLeftWidth: 360
    /** 큐 카드 헤더: 제목 컬럼 고정 폭 */
    readonly property int queueHeaderTitleWidth: 220
    /** 큐 카드 헤더: 배지 컬럼 고정 폭 */
    readonly property int queueHeaderBadgeWidth: 170
    /** 큐 카드 헤더: 액션 버튼 최소 폭 (… 금지 정책용) */
    readonly property int queueHeaderButtonMinWidth: 110

    // ── 폰트 크기 ────────────────────────────────────
    readonly property int fontCaption:  13
    readonly property int fontBody:     16
    readonly property int fontSubtitle: 20
    readonly property int fontTitle:    28
    readonly property int fontDisplay:  38

    // ── 애니메이션 ───────────────────────────────────
    readonly property int animFast:   150
    readonly property int animNormal: 250
    readonly property int animSlow:   400

    // ── 스크롤 물리 ──────────────────────────────────
    readonly property real flickDeceleration: 12000
    readonly property real maxVelocity: 2500
    readonly property int boundsBehavior: Flickable.StopAtBounds

    // ── 시스템 폰트 ──────────────────────────────────
    readonly property string fontFamily: "Segoe UI, Malgun Gothic, sans-serif"
    readonly property string iconFont: "Material Symbols Rounded"

    // ── 헬퍼 함수 ────────────────────────────────────
    function pathToUrl(path) {
        if (!path) return "";
        var parts = String(path).split(/[\\/]/);
        for (var i = 0; i < parts.length; i++) {
            if (i === 0 && parts[i].length === 2 && parts[i].charAt(1) === ":") continue; // 드라이브 문자(예: C:)
            parts[i] = encodeURIComponent(parts[i]);
        }
        var joined = parts.join("/");
        if (joined.length > 1 && joined.charAt(1) === ":") return "file:///" + joined;
        if (joined.charAt(0) === "/") return "file://" + joined;
        return "file:///" + joined;
    }
}
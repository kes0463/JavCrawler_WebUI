import QtQuick
import QtQuick.Controls
import Qt5Compat.GraphicalEffects
import ".."

Button {
    id: root

    property bool primary: true
    property bool neonGlow: false
    property bool danger: false   // true 이면 error(red) 계열 색상으로 표시
    property string iconSource: ""
    // 대시보드 헤더처럼 폭을 고정해야 하는 경우 사용
    property bool fixedWidthMode: false
    property int fixedWidth: 0

    font.pixelSize: Theme.fontBody
    font.weight: Font.DemiBold
    horizontalPadding: Theme.spacingLg
    // 일부 이모지(🖼️ 등)는 글리프 바운딩이 커서 부모가 clip일 때 윗/아랫부분이 잘릴 수 있어
    // 기본 세로 패딩을 넉넉히 둔다.
    verticalPadding: Theme.spacingSm + 4

    // press 시 살짝 축소
    scale: root.pressed ? 0.96 : 1.0
    Behavior on scale { NumberAnimation { duration: 80; easing.type: Easing.OutCubic } }

    // primary/danger 버튼 글로우
    readonly property color _activeColor: root.danger ? Theme.error : Theme.accentNeon
    property real _glowR: root.hovered ? 14 : 7
    property real _glowA: (root.primary || root.danger) && root.enabled ? (root.hovered ? 0.32 : 0.16) : 0
    Behavior on _glowR { NumberAnimation { duration: Theme.animFast } }
    Behavior on _glowA { NumberAnimation { duration: Theme.animFast } }

    layer.enabled: (root.primary || root.danger) && root.enabled
    layer.effect: DropShadow {
        transparentBorder: true
        horizontalOffset: 0
        verticalOffset: root.pressed ? 1 : (root.hovered ? 4 : 2)
        radius: root._glowR
        samples: 17
        color: Qt.rgba(root._activeColor.r, root._activeColor.g, root._activeColor.b, root._glowA)
    }

    implicitWidth: (root.fixedWidthMode && root.fixedWidth > 0)
        ? root.fixedWidth
        : (row.implicitWidth + horizontalPadding * 2)

    contentItem: Item {
        id: contentRoot
        anchors.fill: parent
        clip: true

        Row {
            id: row
            spacing: Theme.spacingSm
            anchors.centerIn: parent
            height: parent.height

            Text {
                id: iconText
                text: root.iconSource
                font.pixelSize: Theme.fontBody + 2
                color: (root.primary || root.danger) ? (Theme.isDark ? "#0A0E1A" : "#FFFFFF") : Theme.textPrimary
                visible: root.iconSource !== ""
                anchors.verticalCenter: parent.verticalCenter
                verticalAlignment: Text.AlignVCenter
                lineHeightMode: Text.ProportionalHeight
                lineHeight: 1.15
            }

            Text {
                id: labelText
                text: root.text
                font: root.font
                color: (root.primary || root.danger) ? (Theme.isDark ? "#0A0E1A" : "#FFFFFF") : Theme.textPrimary
                anchors.verticalCenter: parent.verticalCenter
                verticalAlignment: Text.AlignVCenter
                lineHeightMode: Text.ProportionalHeight
                lineHeight: 1.15
                wrapMode: Text.NoWrap
                horizontalAlignment: Text.AlignHCenter
                // 고정폭 모드에서는 버튼 안에서 가운데 정렬/클립되도록 폭을 부모 기준으로 계산
                width: root.fixedWidthMode
                    ? Math.max(
                        0,
                        contentRoot.width
                        - Theme.spacingSm * 2
                        - (iconText.visible ? (iconText.implicitWidth + row.spacing) : 0)
                    )
                    : implicitWidth
            }
        }
    }

    background: Rectangle {
        id: bg
        radius: Theme.radiusSm
        color: {
            if (!root.enabled)
                return Theme.surfaceLight;
            if (root.danger) {
                if (root.pressed) return Qt.darker(root._activeColor, 1.3);
                if (root.hovered) return Qt.lighter(root._activeColor, 1.15);
                return root._activeColor;
            }
            if (root.pressed)
                return root.primary ? Qt.darker(Theme.accentNeon, 1.3) : Theme.surfaceLight;
            if (root.hovered)
                return root.primary ? Qt.lighter(Theme.accentNeon, 1.15) : Theme.navHover;
            if (root.activeFocus && !root.primary)
                return Theme.navHover;
            return root.primary ? Theme.accentNeon : Theme.surface;
        }
        border.color: {
            if (root.neonGlow && root.hovered) return Theme.accentNeon;
            if (root.activeFocus && root.enabled)
                return root.danger ? Qt.lighter(root._activeColor, 1.35)
                     : root.primary ? Qt.lighter(Theme.accentNeon, 1.35) : Theme.accentNeon;
            if (root.danger) return "transparent";
            if (!root.primary) return Theme.glassBorderHover;
            return "transparent";
        }
        border.width: {
            if (root.activeFocus && root.enabled) return root.primary ? 3 : 2;
            if (!root.primary || root.neonGlow) return 1;
            return 0;
        }

        Behavior on color { ColorAnimation { duration: Theme.animFast } }
    }
}
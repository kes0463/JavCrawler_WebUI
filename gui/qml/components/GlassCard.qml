import QtQuick
import QtQuick.Controls
import Qt5Compat.GraphicalEffects
import ".."

Rectangle {
    id: root

    property alias contentItem: contentLoader.item
    default property alias content: contentArea.data

    property bool hoverGlow: false
    property int contentMargins: Theme.spacingMd
    /** true면 내부 content 크기로 implicitHeight를 계산(자동 높이). anchors.fill 기반 콘텐츠가 있으면 루프가 날 수 있어 기본은 false. */
    property bool autoSize: false

    // 그림자 애니메이션용 중간 속성
    property real _shadowR: (hoverArea.containsMouse && hoverGlow) ? 22 : 9
    property real _shadowY: (hoverArea.containsMouse && hoverGlow) ? 6 : 2
    property real _shadowA: (hoverArea.containsMouse && hoverGlow) ? 0.42 : 0.20

    Behavior on _shadowR { NumberAnimation { duration: Theme.animNormal; easing.type: Easing.OutCubic } }
    Behavior on _shadowY { NumberAnimation { duration: Theme.animNormal; easing.type: Easing.OutCubic } }
    Behavior on _shadowA { NumberAnimation { duration: Theme.animNormal } }

    color: Theme.surface
    border.color: hoverArea.containsMouse && hoverGlow
                  ? Theme.glassBorderHover : Theme.glassBorder
    border.width: 1
    radius: Theme.radiusMd

    Behavior on border.color { ColorAnimation { duration: Theme.animFast } }

    implicitHeight: root.autoSize ? (contentArea.childrenRect.height + root.contentMargins * 2) : 0
    implicitWidth: 300

    layer.enabled: true
    layer.effect: DropShadow {
        transparentBorder: true
        horizontalOffset: 0
        verticalOffset: root._shadowY
        radius: root._shadowR
        samples: 25
        color: Qt.rgba(0, 0, 0, Theme.isDark ? root._shadowA : root._shadowA * 0.5)
    }

    MouseArea {
        id: hoverArea
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.NoButton
        propagateComposedEvents: true
    }

    Loader { id: contentLoader; active: false }

    Item {
        id: contentArea
        anchors {
            fill: root.autoSize ? undefined : parent
            left: root.autoSize ? parent.left : undefined
            right: root.autoSize ? parent.right : undefined
            top: root.autoSize ? parent.top : undefined
            margins: root.contentMargins
        }
        // autoSize=true일 때는 childrenRect로만 implicitHeight 계산(높이를 강제하지 않음)
    }
}
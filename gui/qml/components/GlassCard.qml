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
    property bool autoSize: false
    property string title: ""

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

    // 선택적 타이틀 (title 프로퍼티가 비어 있으면 렌더링 안 함)
    Text {
        id: titleLabel
        visible: root.title !== ""
        text: root.title
        color: Theme.textSecondary
        font.pixelSize: 12
        font.weight: Font.Medium
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.margins: root.contentMargins
    }

    Item {
        id: contentArea
        // fill + 개별 undefined 혼용 시 undefined가 fill을 override해 width/height=0이 되는 Qt 버그 방지.
        // 개별 앵커만 명시적으로 사용.
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.leftMargin: root.contentMargins
        anchors.rightMargin: root.contentMargins
        anchors.top: root.title !== "" ? titleLabel.bottom : parent.top
        anchors.topMargin: root.title !== "" ? Theme.spacingSm : root.contentMargins
        anchors.bottom: root.autoSize ? undefined : parent.bottom
        anchors.bottomMargin: root.autoSize ? 0 : root.contentMargins
    }
}
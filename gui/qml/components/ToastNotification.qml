import QtQuick
import Qt5Compat.GraphicalEffects
import ".."

Rectangle {
    id: root

    property string message: ""
    property string level: "info"  // info, success, warning, error
    property int duration: 3000
    property real _slideY: 0

    signal dismissed()

    width: toastText.implicitWidth + Theme.spacingLg * 2 + 8
    height: 44
    radius: Theme.radiusSm + 2
    opacity: 0
    visible: opacity > 0

    transform: Translate { y: root._slideY }

    color: {
        switch (level) {
        case "success": return Qt.rgba(52/255, 211/255, 153/255, 0.92);
        case "warning": return Qt.rgba(251/255, 191/255, 36/255, 0.92);
        case "error":   return Qt.rgba(248/255, 113/255, 113/255, 0.92);
        default:        return Qt.rgba(0, 136/255, 1, 0.92);
        }
    }

    layer.enabled: true
    layer.effect: DropShadow {
        transparentBorder: true
        horizontalOffset: 0
        verticalOffset: 4
        radius: 16
        samples: 25
        color: Qt.rgba(0, 0, 0, 0.28)
    }

    Text {
        id: toastText
        anchors.centerIn: parent
        text: root.message
        font.pixelSize: Theme.fontBody
        font.weight: Font.Medium
        color: (root.level === "warning" || root.level === "success") ? "#0A0E1A" : "#FFFFFF"
    }

    function show(msg, lvl) {
        root.message = msg;
        root.level = lvl || "info";
        showAnim.start();
        hideTimer.restart();
    }

    Timer {
        id: hideTimer
        interval: root.duration
        onTriggered: hideAnim.start()
    }

    ParallelAnimation {
        id: showAnim
        NumberAnimation { target: root; property: "opacity";  from: 0;  to: 1;  duration: Theme.animFast; easing.type: Easing.OutCubic }
        NumberAnimation { target: root; property: "_slideY";  from: 12; to: 0;  duration: Theme.animNormal; easing.type: Easing.OutCubic }
    }

    NumberAnimation {
        id: hideAnim
        target: root; property: "opacity"
        from: 1; to: 0; duration: Theme.animNormal
        onFinished: root.dismissed()
    }
}
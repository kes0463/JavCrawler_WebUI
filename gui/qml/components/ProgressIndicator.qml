import QtQuick
import ".."

Item {
    id: root

    property real value: 0          // 0.0 ~ 1.0
    property bool indeterminate: false
    property bool circular: false
    property int barHeight: 4
    property color barColor: Theme.accentNeon
    property color trackColor: Qt.rgba(255/255, 255/255, 255/255, 0.08)

    implicitWidth: circular ? 48 : 200
    implicitHeight: circular ? 48 : barHeight

    // ── 선형 프로그래스 바 ───────────────────────────
    Rectangle {
        id: track
        visible: !root.circular
        anchors.fill: parent
        radius: root.barHeight / 2
        color: root.trackColor

        Rectangle {
            id: fill
            height: parent.height
            radius: parent.radius
            color: root.barColor
            width: root.indeterminate ? parent.width * 0.3 : parent.width * root.value

            Behavior on width {
                enabled: !root.indeterminate
                NumberAnimation { duration: Theme.animNormal; easing.type: Easing.OutCubic }
            }

            SequentialAnimation on x {
                running: root.indeterminate && !root.circular
                loops: Animation.Infinite
                NumberAnimation {
                    from: -fill.width
                    to: track.width
                    duration: 1200
                    easing.type: Easing.InOutQuad
                }
            }
        }
    }

    // ── 원형 프로그래스 ──────────────────────────────
    Canvas {
        id: circleCanvas
        visible: root.circular
        anchors.fill: parent

        property real animatedValue: root.value
        Behavior on animatedValue { NumberAnimation { duration: Theme.animNormal } }

        onAnimatedValueChanged: requestPaint()
        Component.onCompleted: requestPaint()

        onPaint: {
            var ctx = getContext("2d");
            ctx.reset();
            var cx = width / 2, cy = height / 2;
            var r = Math.max(1, Math.min(cx, cy) - 4);
            var lineW = 4;

            // Track
            ctx.beginPath();
            ctx.arc(cx, cy, r, 0, 2 * Math.PI);
            ctx.strokeStyle = root.trackColor.toString();
            ctx.lineWidth = lineW;
            ctx.stroke();

            // Fill
            var startAngle = -Math.PI / 2;
            var endAngle = startAngle + 2 * Math.PI * animatedValue;
            ctx.beginPath();
            ctx.arc(cx, cy, r, startAngle, endAngle);
            ctx.strokeStyle = root.barColor.toString();
            ctx.lineWidth = lineW;
            ctx.lineCap = "round";
            ctx.stroke();
        }
    }

    // 중앙 퍼센트 텍스트 (원형 모드)
    Text {
        visible: root.circular
        anchors.centerIn: parent
        text: Math.round(root.value * 100) + "%"
        font.pixelSize: Theme.fontCaption
        font.weight: Font.Bold
        color: Theme.textPrimary
    }
}
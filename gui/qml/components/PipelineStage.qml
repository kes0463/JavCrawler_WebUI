import QtQuick
import ".."

Item {
    id: root

    property string stageName: ""
    property string status: "pending"   // pending, running, done, error, skipped
    property real progress: 0           // 0.0 ~ 1.0
    property bool clickable: false

    signal clicked()

    implicitWidth: contentRow.width
    implicitHeight: 32

    MouseArea {
        anchors.fill: parent
        enabled: root.clickable
        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: root.clicked()
    }

    Row {
        id: contentRow
        spacing: Theme.spacingSm
        anchors.verticalCenter: parent.verticalCenter

        Rectangle {
            width: 32; height: 32; radius: 16
            color: {
                switch (root.status) {
                case "done":    return Theme.success;
                case "running": return Theme.accentNeon;
                case "error":   return Theme.error;
                case "skipped": return Theme.textMuted;
                default:        return Theme.surfaceLight;
                }
            }

            Behavior on color { ColorAnimation { duration: Theme.animNormal } }

            Text {
                anchors.centerIn: parent
                font.pixelSize: 14
                font.weight: Font.Bold
                color: root.status === "pending" ? Theme.textMuted : Theme.bgPrimary
                text: {
                    switch (root.status) {
                    case "done":    return "\u2713";
                    case "running": return "\u25B6";
                    case "error":   return "!";
                    case "skipped": return "\u2014";
                    default:        return root.stageName.charAt(0).toUpperCase();
                    }
                }
            }
        }

        Column {
            anchors.verticalCenter: parent.verticalCenter
            spacing: 2

            Text {
                text: root.stageName
                font.pixelSize: Theme.fontBody
                font.weight: Font.DemiBold
                color: root.status === "done" ? Theme.success
                     : root.status === "running" ? Theme.accentNeon
                     : Theme.textSecondary
            }

            ProgressIndicator {
                visible: root.status === "running"
                width: 80
                value: root.progress
                barHeight: 3
            }
        }
    }
}
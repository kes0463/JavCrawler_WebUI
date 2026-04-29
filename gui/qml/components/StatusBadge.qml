import QtQuick
import ".."

Rectangle {
    id: root

    property string status: "none"  // none, queued, harvest, transcription, translation, canonical, error, running
    property string label: ""

    width: badgeRow.implicitWidth + Theme.spacingSm * 2
    height: 22
    radius: 11
    color: {
        switch (status) {
        case "queued":        return Qt.rgba(251/255, 191/255, 36/255, 0.12);
        case "canonical":     return Qt.rgba(52/255, 211/255, 153/255, 0.20);
        case "translation":   return Qt.rgba(0, 136/255, 1, 0.20);
        case "transcription": return Qt.rgba(0, 229/255, 1, 0.20);
        case "harvest":       return Qt.rgba(251/255, 191/255, 36/255, 0.20);
        case "error":         return Qt.rgba(248/255, 113/255, 113/255, 0.20);
        case "running":       return Qt.rgba(0, 229/255, 1, 0.15);
        default:              return Qt.rgba(255, 255, 255, 0.08);
        }
    }
    border.color: {
        switch (status) {
        case "queued":        return Qt.rgba(251/255, 191/255, 36/255, 0.28);
        case "canonical":     return Qt.rgba(52/255, 211/255, 153/255, 0.32);
        case "translation":   return Qt.rgba(0, 136/255, 1, 0.32);
        case "transcription": return Qt.rgba(0, 229/255, 1, 0.32);
        case "harvest":       return Qt.rgba(251/255, 191/255, 36/255, 0.28);
        case "error":         return Qt.rgba(248/255, 113/255, 113/255, 0.32);
        case "running":       return Qt.rgba(0, 229/255, 1, 0.40);
        default:              return Theme.glassBorder;
        }
    }
    border.width: 1

    Row {
        id: badgeRow
        anchors.centerIn: parent
        spacing: 4

        Rectangle {
            id: dot
            width: 6; height: 6; radius: 3
            anchors.verticalCenter: parent.verticalCenter
            color: {
                switch (root.status) {
                case "queued":        return Theme.warning;
                case "canonical":     return Theme.success;
                case "translation":   return Theme.primaryBlue;
                case "transcription": return Theme.accentNeon;
                case "harvest":       return Theme.warning;
                case "error":         return Theme.error;
                case "running":       return Theme.accentNeon;
                default:              return Theme.textMuted;
                }
            }

            SequentialAnimation on opacity {
                running: root.status === "running"
                loops: Animation.Infinite
                NumberAnimation { to: 0.20; duration: 650; easing.type: Easing.InOutSine }
                NumberAnimation { to: 1.0;  duration: 650; easing.type: Easing.InOutSine }
            }
        }

        Text {
            text: root.label || root.status
            font.pixelSize: Theme.fontCaption - 1
            font.weight: Font.Medium
            color: Theme.textSecondary
            anchors.verticalCenter: parent.verticalCenter
        }
    }
}
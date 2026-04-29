import QtQuick
import QtQuick.Layouts
import ".."

Rectangle {
    id: root

    property string codeText: ""
    property string titleText: ""
    property real progressValue: -1 // <0: hidden, else 0..1
    property bool progressIndeterminate: false
    property string progressText: ""
    property bool highlightCode: true
    property bool showDelete: true

    signal deleteClicked()

    height: Theme.queueRowHeight
    radius: Theme.radiusSm
    color: rowMouse.containsMouse ? Theme.rowHover : "transparent"
    border.color: rowMouse.containsMouse ? Theme.glassBorderHover : "transparent"
    border.width: rowMouse.containsMouse ? 1 : 0

    Behavior on color { ColorAnimation { duration: Theme.animFast } }
    Behavior on border.color { ColorAnimation { duration: Theme.animFast } }

    // hover 시 좌측 액센트 바
    Rectangle {
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        width: rowMouse.containsMouse ? 3 : 0
        height: 18
        radius: 2
        color: Theme.accentNeon
        opacity: 0.55
        Behavior on width { NumberAnimation { duration: Theme.animFast; easing.type: Easing.OutCubic } }
    }

    MouseArea {
        id: rowMouse
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.NoButton
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.spacingMd
        anchors.rightMargin: Theme.spacingMd
        spacing: Theme.spacingSm

        Text {
            Layout.preferredWidth: 112
            text: root.codeText
            font.pixelSize: Theme.fontCaption
            font.weight: Font.Bold
            color: root.highlightCode ? Theme.accentNeon : Theme.textSecondary
            elide: Text.ElideRight
            verticalAlignment: Text.AlignVCenter
        }

        Text {
            Layout.fillWidth: true
            text: root.titleText
            font.pixelSize: Theme.fontCaption
            color: Theme.textSecondary
            elide: Text.ElideMiddle
            verticalAlignment: Text.AlignVCenter
        }

        ProgressIndicator {
            visible: root.progressValue >= 0 || root.progressIndeterminate
            Layout.preferredWidth: 132
            Layout.preferredHeight: 4
            value: Math.max(0, Math.min(1, root.progressValue))
            indeterminate: root.progressIndeterminate
            barColor: Theme.primaryBlue
            trackColor: Theme.progressTrack
        }

        Text {
            visible: root.progressValue >= 0 && (root.progressText || "").length > 0
            text: root.progressText
            font.pixelSize: Theme.fontCaption - 2
            color: Theme.textMuted
            elide: Text.ElideRight
            // 프레임·남은시간 등 (모자이크) 한 줄이 길어 120에서 잘림
            Layout.preferredWidth: 320
            Layout.minimumWidth: 200
            verticalAlignment: Text.AlignVCenter
        }

        Item { Layout.preferredWidth: Theme.spacingSm; visible: root.showDelete }

        Item {
            visible: root.showDelete
            Layout.preferredWidth: 24
            Layout.preferredHeight: 24

            Rectangle {
                anchors.fill: parent
                radius: 6
                color: delMouse.containsMouse ? Qt.rgba(Theme.error.r, Theme.error.g, Theme.error.b, 0.10) : "transparent"

                Text {
                    anchors.centerIn: parent
                    text: "✕"
                    font.pixelSize: 14
                    color: delMouse.containsMouse ? Theme.error : Theme.textMuted
                }
            }

            MouseArea {
                id: delMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.deleteClicked()
            }
        }
    }
}
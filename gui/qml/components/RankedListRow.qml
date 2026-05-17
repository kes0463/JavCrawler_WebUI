import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

Item {
    id: rowRoot

    property int rowIndex: 0
    property var rowData: null
    property string mode: "rank"
    property int maxScore: 1
    property var colorFn: null

    property real itemScore: rowData ? (rowData.score || 0) : 0
    property string itemName: rowData ? (rowData.name || "") : ""
    property real barRatio: Math.min(1.0, rowRoot.itemScore / Math.max(1, rowRoot.maxScore))
    property color accent: rowRoot.barColor(rowRoot.rowIndex)

    implicitHeight: 36

    function barColor(idx) {
        if (rowRoot.mode === "color" && rowRoot.colorFn)
            return rowRoot.colorFn(idx)
        return Theme.accentNeon
    }

    function rankBadgeColor(idx) {
        if (idx === 0) return "#FFD700"
        if (idx === 1) return "#C0C0C0"
        if (idx === 2) return "#CD7F32"
        return Theme.surfaceLight
    }

    Rectangle {
        anchors.fill: parent
        radius: 6
        color: rowMa.containsMouse ? Qt.rgba(1, 1, 1, 0.07) : "transparent"
    }

    RowLayout {
        anchors {
            left: parent.left
            right: parent.right
            verticalCenter: parent.verticalCenter
            leftMargin: 4
            rightMargin: 4
        }
        spacing: Theme.spacingSm

        Rectangle {
            visible: rowRoot.mode === "rank"
            width: 28
            height: 28
            radius: 14
            color: rowRoot.rankBadgeColor(rowRoot.rowIndex)
            Text {
                anchors.centerIn: parent
                text: rowRoot.rowIndex + 1
                font.pixelSize: 12
                font.weight: Font.Bold
                color: rowRoot.rowIndex < 3 ? "#000" : Theme.textMuted
            }
        }

        Rectangle {
            visible: rowRoot.mode === "color"
            width: 10
            height: 10
            radius: 5
            color: rowRoot.accent
            Layout.alignment: Qt.AlignVCenter
        }

        Text {
            text: rowRoot.itemName
            font.pixelSize: Theme.fontCaption
            color: rowMa.containsMouse ? rowRoot.accent : Theme.textPrimary
            elide: Text.ElideRight
            Layout.maximumWidth: Math.max(80, rowRoot.width * 0.35)
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.minimumWidth: 60
            height: 8
            radius: 4
            color: Theme.progressTrack
            Layout.alignment: Qt.AlignVCenter

            Rectangle {
                width: parent.width * rowRoot.barRatio
                height: parent.height
                radius: 4
                color: rowRoot.accent
                Behavior on width {
                    NumberAnimation { duration: 500; easing.type: Easing.OutCubic }
                }
            }
        }

        Text {
            text: rowRoot.itemScore
            font.pixelSize: Theme.fontCaption
            color: Theme.textSecondary
            Layout.preferredWidth: 44
            horizontalAlignment: Text.AlignRight

            ToolTip {
                visible: scoreMa.containsMouse
                text: "누적 취향 점수"
                delay: 400
            }

            MouseArea {
                id: scoreMa
                anchors.fill: parent
                hoverEnabled: true
                acceptedButtons: Qt.NoButton
            }
        }
    }

    MouseArea {
        id: rowMa
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: {
            if (rowRoot.itemName)
                window.navigateToLibrarySearch(rowRoot.itemName)
        }
    }
}

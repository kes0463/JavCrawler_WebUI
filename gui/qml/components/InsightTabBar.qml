import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

RowLayout {
    id: root
    Layout.fillWidth: true
    spacing: Theme.spacingXs

    property int currentIndex: 0
    property var labels: ["개요", "추이", "추천", "컬렉션"]

    signal tabActivated(int index)

    Repeater {
        model: root.labels.length

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 40
            radius: Theme.radiusSm
            color: root.currentIndex === index
                ? Qt.rgba(Theme.accentNeon.r, Theme.accentNeon.g, Theme.accentNeon.b, 0.15)
                : "transparent"
            border.color: root.currentIndex === index ? Theme.accentNeon : Theme.glassBorder
            border.width: 1

            Text {
                anchors.centerIn: parent
                text: root.labels[index]
                font.pixelSize: Theme.fontCaption
                font.weight: root.currentIndex === index ? Font.DemiBold : Font.Normal
                color: root.currentIndex === index ? Theme.accentNeon : Theme.textSecondary
            }

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.tabActivated(index)
            }
        }
    }
}

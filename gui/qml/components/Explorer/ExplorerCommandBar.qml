import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../../"

Rectangle {
    id: root
    height: 48
    color: "transparent"
    
    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 8
        anchors.rightMargin: 8
        spacing: 4

        ToolbarButton {
            icon: "plus"
            text: "새로 만들기"
            Layout.alignment: Qt.AlignVCenter
            onClicked: {} // Not implemented
        }

        Rectangle { width: 1; height: 24; color: Theme.glassBorder; Layout.margins: 4 }

        ToolbarButton {
            icon: "sort"
            text: "정렬"
            Layout.alignment: Qt.AlignVCenter
            onClicked: {} // Not implemented
        }

        ToolbarButton {
            icon: FolderExplorerModel.viewMode === 0 ? "view-list" : "view-grid"
            text: FolderExplorerModel.viewMode === 0 ? "목록" : "그리드"
            Layout.alignment: Qt.AlignVCenter
            onClicked: FolderExplorerModel.viewMode = (FolderExplorerModel.viewMode === 0 ? 1 : 0)
        }

        Item { Layout.fillWidth: true }
    }

    // 내부 버튼 컴포넌트
    component ToolbarButton : Item {
        property string icon: ""
        property string text: ""
        signal clicked()

        width: btnContent.implicitWidth + 24
        height: 36

        Rectangle {
            anchors.fill: parent
            radius: 4
            color: btnMouse.containsMouse ? Theme.navHover : "transparent"
            Behavior on color { ColorAnimation { duration: Theme.animFast } }
        }

        RowLayout {
            id: btnContent
            anchors.centerIn: parent
            spacing: 8
            
            FluentIcon {
                type: parent.parent.icon
                size: 16
                color: Theme.textPrimary
            }

            Text {
                text: parent.parent.text
                color: Theme.textPrimary
                font.pixelSize: Theme.fontCaption + 1
            }
        }

        MouseArea {
            id: btnMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: parent.clicked()
        }
    }
}
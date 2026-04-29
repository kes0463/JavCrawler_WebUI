import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../../"

Item {
    id: root
    width: 220
    Layout.fillHeight: true

    // 배경 (약간 다른 계조)
    Rectangle {
        anchors.fill: parent
        color: Theme.isDark ? Qt.rgba(1,1,1,0.02) : Qt.rgba(0,0,0,0.02)
    }

    AppScrollView {
        anchors.fill: parent
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        
        Column {
            id: sidebarColumn
            width: root.width
            spacing: 2
            topPadding: 8
            bottomPadding: 8

            // ── 홈 (Home) ─────────────────────────────
            SidebarHeader { text: "홈" }
            
            Repeater {
                model: FolderExplorerModel.favorites
                delegate: SidebarItem {
                    text: modelData.name
                    iconType: modelData.name.toLowerCase()
                    isActive: FolderExplorerModel.currentPath === modelData.path
                    onClicked: FolderExplorerModel.cdInto(modelData.path)
                }
            }

            Item { width: 1; height: 12 }

            // ── 내 PC (This PC) ────────────────────────
            SidebarHeader { text: "내 PC" }

            Repeater {
                model: FolderExplorerModel.drives
                delegate: SidebarItem {
                    text: modelData.name
                    iconType: "drive"
                    isActive: FolderExplorerModel.currentPath.startsWith(modelData.path)
                    onClicked: FolderExplorerModel.cdInto(modelData.path)
                }
            }
        }
    }

    // 내부 컴포넌트: SidebarHeader
    component SidebarHeader : Item {
        property string text: ""
        width: parent.width; height: 32
        Text {
            text: parent.text
            color: Theme.textPrimary
            font.pixelSize: Theme.fontCaption
            font.weight: Font.DemiBold
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left
            anchors.leftMargin: 12
        }
    }

    // 내부 컴포넌트: SidebarItem
    component SidebarItem : Item {
        property string text: ""
        property string iconType: ""
        property bool isActive: false
        signal clicked()

        width: parent.width; height: 34

        Rectangle {
            anchors.fill: parent
            anchors.margins: 2
            anchors.leftMargin: 8
            anchors.rightMargin: 8
            radius: 5
            color: isActive ? Theme.navActive : (mouse.containsMouse ? Theme.navHover : "transparent")
            Behavior on color { ColorAnimation { duration: Theme.animFast } }
        }

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 20
            spacing: 12
            
            FluentIcon {
                type: parent.parent.iconType
                size: 16
                color: parent.parent.isActive ? Theme.accentNeon : Theme.textPrimary
            }

            Text {
                text: parent.parent.text
                color: parent.parent.isActive ? Theme.textPrimary : Theme.textSecondary
                font.pixelSize: Theme.fontCaption + 1
                Layout.fillWidth: true
                elide: Text.ElideRight
            }
        }

        MouseArea {
            id: mouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: parent.clicked()
        }
    }
}
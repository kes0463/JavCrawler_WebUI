import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../../"

Item {
    id: root
    clip: true

    // ── 그리드 뷰 (Grid Mode) ─────────────────────────
    GridView {
        boundsBehavior: Theme.boundsBehavior
        id: gridView
        anchors.fill: parent
        anchors.margins: 12
        cellWidth: 120
        cellHeight: 140
        model: FolderExplorerModel.folderModel
        visible: FolderExplorerModel.viewMode === 0

        delegate: Item {
            width: gridView.cellWidth
            height: gridView.cellHeight

            Rectangle {
                anchors.fill: parent
                anchors.margins: 4
                radius: 6
                color: model.isSelected ? Theme.navActive : (gridMouse.containsMouse ? Theme.navHover : "transparent")
                border.color: model.isSelected ? Theme.accentNeon : "transparent"
                border.width: 1

                Column {
                    anchors.centerIn: parent
                    spacing: 12
                    width: parent.width - 16

                    FluentIcon {
                        type: "folder"
                        size: 48
                        color: "#EBC44F" // Windows 11 Folder Yellow
                        anchors.horizontalCenter: parent.horizontalCenter
                    }

                    Text {
                        text: model.name
                        width: parent.width
                        color: Theme.textPrimary
                        font.pixelSize: Theme.fontCaption
                        horizontalAlignment: Text.AlignHCenter
                        elide: Text.ElideMiddle
                        maximumLineCount: 2
                        wrapMode: Text.Wrap
                    }
                }

                // 체크박스 (Native Style)
                Rectangle {
                    width: 18; height: 18
                    radius: 3
                    anchors.top: parent.top; anchors.left: parent.left
                    anchors.margins: 6
                    color: model.isSelected ? Theme.accentNeon : "transparent"
                    border.color: model.isSelected ? "transparent" : Theme.textMuted
                    border.width: model.isSelected ? 0 : 1
                    visible: model.isSelected || gridMouse.containsMouse

                    FluentIcon {
                        type: "check"
                        size: 12
                        color: "white"
                        anchors.centerIn: parent
                        visible: model.isSelected
                    }

                    MouseArea {
                        anchors.fill: parent
                        onClicked: FolderExplorerModel.toggleSelection(index)
                    }
                }

                MouseArea {
                    id: gridMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    onClicked: FolderExplorerModel.cdInto(model.path)
                }
            }
        }
    }

    // ── 리스트 뷰 (Details/List Mode) ──────────────────
    ListView {
        boundsBehavior: Flickable.StopAtBounds
        id: listView
        anchors.fill: parent
        anchors.topMargin: 40 // 헤더 공간
        model: FolderExplorerModel.folderModel
        visible: FolderExplorerModel.viewMode === 1
        clip: true

        // 목록 헤더
        header: Rectangle {
            width: listView.width; height: 32
            z: 2
            color: Theme.surface
            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.glassBorder }
            Row {
                anchors.fill: parent; anchors.leftMargin: 48; spacing: 0
                ListHeaderItem { text: "이름"; width: parent.width * 0.6 }
                ListHeaderItem { text: "수정한 날짜"; width: parent.width * 0.4 }
            }
        }

        delegate: Rectangle {
            width: listView.width
            height: 36
            color: model.isSelected ? Theme.navActive : (listMouse.containsMouse ? Theme.navHover : "transparent")
            
            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 8
                spacing: 12

                // 체크박스
                Rectangle {
                    width: 18; height: 18
                    radius: 3
                    color: model.isSelected ? Theme.accentNeon : "transparent"
                    border.color: model.isSelected ? "transparent" : Theme.textMuted
                    border.width: model.isSelected ? 0 : 1
                    visible: model.isSelected || listMouse.containsMouse

                    FluentIcon {
                        type: "check"
                        size: 10
                        color: "white"
                        anchors.centerIn: parent
                        visible: model.isSelected
                    }

                    MouseArea {
                        anchors.fill: parent
                        onClicked: FolderExplorerModel.toggleSelection(index)
                    }
                }

                FluentIcon {
                    type: "folder"
                    size: 16
                    color: "#EBC44F"
                    visible: !model.isSelected && !listMouse.containsMouse
                }
                
                Item { width: 16; visible: model.isSelected || listMouse.containsMouse }

                Text {
                    text: model.name
                    color: Theme.textPrimary
                    font.pixelSize: Theme.fontCaption + 1
                    Layout.fillWidth: true
                    Layout.preferredWidth: parent.width * 0.6
                    elide: Text.ElideRight
                }

                Text {
                    text: model.modified
                    color: Theme.textSecondary
                    font.pixelSize: Theme.fontCaption
                    Layout.preferredWidth: parent.width * 0.4
                    elide: Text.ElideRight
                }
            }

            MouseArea {
                id: listMouse
                anchors.fill: parent
                hoverEnabled: true
                onClicked: FolderExplorerModel.cdInto(model.path)
            }
        }
    }

    // 내부 헤더 아이템
    component ListHeaderItem : Item {
        property string text: ""
        height: parent.height
        Text {
            text: parent.text
            color: Theme.textSecondary
            font.pixelSize: Theme.fontCaption
            font.weight: Font.DemiBold
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left; anchors.leftMargin: 8
        }
    }

    // 데이터가 없을 때 메시지
    Text {
        text: "이 폴더는 비어 있습니다."
        anchors.centerIn: parent
        color: Theme.textMuted
        font.pixelSize: Theme.fontBody
        visible: (FolderExplorerModel.viewMode === 0 ? gridView.count : listView.count) === 0
    }
}
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
        anchors.rightMargin: 12
        spacing: 8

        // ── 네비게이션 버튼 (Fluent Style) ────────────────
        Row {
            spacing: 2
            Layout.alignment: Qt.AlignVCenter
            
            NavBtn { icon: "back"; isBtnEnabled: FolderExplorerModel.canGoBack; onClicked: FolderExplorerModel.goBack() }
            NavBtn { icon: "forward"; isBtnEnabled: FolderExplorerModel.canGoForward; onClicked: FolderExplorerModel.goForward() }
            NavBtn { icon: "up"; isBtnEnabled: true; onClicked: FolderExplorerModel.goUp() }
        }

        // ── 브레드크럼 주소창 (Native Appearance) ─────────
        Rectangle {
            Layout.fillWidth: true
            height: 34
            radius: 6
            color: Theme.surfaceLight
            border.color: Theme.glassBorder
            border.width: 1
            clip: true

            AppScrollView {
                anchors.fill: parent
                anchors.leftMargin: 8
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                clip: true

                Row {
                    id: breadcrumbRow
                    height: parent.height
                    width: availableWidth
                    spacing: 0

                    Repeater {
                        model: {
                            let path = FolderExplorerModel.currentPath;
                            let parts = path.split(/[\\\/]/).filter(p => p !== "");
                            if (path.indexOf(":") === 1) {
                                let drive = path.substring(0, 2);
                                parts[0] = drive;
                            }
                            return parts;
                        }

                        delegate: Row {
                            height: 34
                            
                            // 브레드크럼 버튼
                            Rectangle {
                                height: 26
                                width: partText.implicitWidth + 16
                                radius: 4
                                color: partMouse.containsMouse ? Theme.navHover : "transparent"
                                anchors.verticalCenter: parent.verticalCenter
                                
                                Text {
                                    id: partText
                                    text: modelData
                                    color: Theme.textPrimary
                                    font.pixelSize: Theme.fontCaption + 1
                                    anchors.centerIn: parent
                                }
                                
                                MouseArea {
                                    id: partMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    onClicked: {
                                        let currentPath = FolderExplorerModel.currentPath;
                                        let isWindows = currentPath.indexOf(":") === 1;
                                        let parts = currentPath.split(/[\\\/]/).filter(p => p !== "");
                                        let pathTotal = isWindows ? parts[0] + "\\" : "/";
                                        for (let j = 1; j <= index; j++) {
                                            pathTotal += parts[j] + (isWindows ? "\\" : "/");
                                        }
                                        FolderExplorerModel.cdInto(pathTotal);
                                    }
                                }
                            }

                            // 화살표
                            Item {
                                width: 20; height: 34
                                visible: index < (breadcrumbRow.count - 1)
                                
                                FluentIcon {
                                    type: "chevron-right"
                                    size: 10
                                    color: Theme.textMuted
                                    anchors.centerIn: parent
                                }
                            }
                        }
                    }
                }
            }
        }

        // ── 검색창 (Native Rounded Style) ───────────────
        Rectangle {
            width: 220
            height: 34
            radius: 6
            color: Theme.surfaceLight
            border.color: Theme.glassBorder
            border.width: 1

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 10
                spacing: 8
                FluentIcon { type: "home"; size: 14; color: Theme.textMuted; opacity: 0.6 }
                Text {
                    text: {
                        let p = FolderExplorerModel.currentPath;
                        let parts = p.split(/[\\\/]/).filter(s => s !== "");
                        let name = parts.length > 0 ? parts[parts.length - 1] : "Folders";
                        return "Search " + name;
                    }
                    color: Theme.textMuted
                    font.pixelSize: Theme.fontCaption
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }
            }
        }
    }

    // 내부 컴포넌트: NavBtn
    component NavBtn : Rectangle {
        property string icon: ""
        property bool isBtnEnabled: true
        signal clicked()

        width: 32; height: 32
        radius: 5
        color: mouse.containsMouse && isBtnEnabled ? Theme.navHover : "transparent"
        opacity: isBtnEnabled ? 1.0 : 0.4
        Behavior on color { ColorAnimation { duration: Theme.animFast } }

        FluentIcon {
            type: parent.icon
            size: 16
            color: Theme.textPrimary
            anchors.centerIn: parent
        }

        MouseArea {
            id: mouse
            anchors.fill: parent
            enabled: parent.isBtnEnabled
            hoverEnabled: true
            onClicked: parent.clicked()
        }
    }
}
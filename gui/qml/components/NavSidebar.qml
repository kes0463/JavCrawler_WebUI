import QtQuick
import QtQuick.Controls
import ".."

Rectangle {
    id: root

    property int currentIndex: 0
    property bool collapsed: false
    /** 폴더 연결 알림 대기 건수 (사이드바 배지) */
    property int folderAlertCount: 0
    signal navigate(int index)
    signal openFolderAlerts()

    width: collapsed ? 72 : 260
    Behavior on width { NumberAnimation { duration: Theme.animNormal; easing.type: Easing.OutCubic } }

    color: Theme.navBg
    border.color: Theme.glassBorder
    border.width: 0

    // 우측 경계선
    Rectangle {
        anchors.right: parent.right
        width: 1; height: parent.height
        color: Theme.glassBorder
    }

    // ── 상단: 로고 + 네비게이션 ────────────────────
    Column {
        id: topNav
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        spacing: 0

        Item {
            width: parent.width
            height: 72

            Row {
                anchors.centerIn: parent
                spacing: Theme.spacingSm

                Text {
                    text: "⭐"
                    font.pixelSize: 22
                    anchors.verticalCenter: parent.verticalCenter
                }

                Text {
                    visible: !root.collapsed
                    text: "JAVSTORY"
                    font.pixelSize: Theme.fontSubtitle
                    font.weight: Font.ExtraBold
                    font.letterSpacing: 1.5
                    color: Theme.mode === 0 ? Theme.textPrimary : Theme.accentNeon
                    anchors.verticalCenter: parent.verticalCenter
                }
            }

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.collapsed = !root.collapsed
            }
        }

        Rectangle { width: parent.width; height: 1; color: Theme.glassBorder }

        Repeater {
            model: ListModel {
                ListElement { label: "대시보드";     icon: "🏠" }
                ListElement { label: "수집";        icon: "🔍" }
                ListElement { label: "전사·자막";   icon: "🎤" }
                ListElement { label: "모자이크";     icon: "🧩" }
                ListElement { label: "라이브러리";   icon: "📚" }
                ListElement { label: "인사이트";     icon: "📊" }
                ListElement { label: "페르소나 챗";  icon: "💬" }
            }

            delegate: Rectangle {
                width: root.width
                height: 48
                color: root.currentIndex === index ? Theme.navActive : "transparent"

                Behavior on color { ColorAnimation { duration: Theme.animFast } }

                // hover 그라디언트 오버레이
                Rectangle {
                    anchors.fill: parent
                    visible: root.currentIndex !== index
                    opacity: navMouse.containsMouse ? 1 : 0
                    Behavior on opacity { NumberAnimation { duration: Theme.animFast } }
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0.0; color: Qt.rgba(Theme.accentNeon.r, Theme.accentNeon.g, Theme.accentNeon.b, 0.07) }
                        GradientStop { position: 0.5; color: Qt.rgba(0, 0, 0, 0) }
                    }
                }

                // 활성 인디케이터 (애니메이션)
                Rectangle {
                    anchors.left: parent.left
                    anchors.verticalCenter: parent.verticalCenter
                    width: 3
                    radius: 2
                    color: Theme.accentNeon
                    height: root.currentIndex === index ? 22 : 8
                    opacity: root.currentIndex === index ? 1 : 0
                    Behavior on height  { NumberAnimation { duration: Theme.animNormal; easing.type: Easing.OutBack } }
                    Behavior on opacity { NumberAnimation { duration: Theme.animFast } }
                }

                Row {
                    anchors.left: parent.left
                    anchors.leftMargin: Theme.spacingMd
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: Theme.spacingSm + 4

                    Text {
                        text: model.icon
                        font.pixelSize: 18
                        anchors.verticalCenter: parent.verticalCenter
                    }

                    Text {
                        visible: !root.collapsed
                        text: model.label
                        font.pixelSize: Theme.fontBody
                        font.weight: root.currentIndex === index ? Font.DemiBold : Font.Normal
                        color: root.currentIndex === index ? Theme.textPrimary : Theme.textSecondary
                        anchors.verticalCenter: parent.verticalCenter
                        Behavior on color { ColorAnimation { duration: Theme.animFast } }
                    }
                }

                MouseArea {
                    id: navMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        root.currentIndex = index;
                        root.navigate(index);
                    }
                }
            }
        }
    }

    // ── 하단: 알림 + 설정 ────────────────────────────
    Column {
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        spacing: 0

        Rectangle { width: parent.width; height: 1; color: Theme.glassBorder }

        // 폴더 연결 알림 인박스
        Rectangle {
            width: root.width
            height: 48
            color: "transparent"

            Rectangle {
                anchors.fill: parent
                opacity: folderBellMouse.containsMouse ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: Theme.animFast } }
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: Qt.rgba(Theme.accentNeon.r, Theme.accentNeon.g, Theme.accentNeon.b, 0.07) }
                    GradientStop { position: 0.5; color: Qt.rgba(0, 0, 0, 0) }
                }
            }

            Row {
                anchors.left: parent.left
                anchors.leftMargin: Theme.spacingMd
                anchors.verticalCenter: parent.verticalCenter
                spacing: Theme.spacingSm + 4

                Item {
                    width: 28
                    height: 28
                    anchors.verticalCenter: parent.verticalCenter

                    Text {
                        anchors.centerIn: parent
                        text: "🔔"
                        font.pixelSize: 18
                    }

                    Rectangle {
                        visible: root.folderAlertCount > 0
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.rightMargin: -4
                        anchors.topMargin: -4
                        width: Math.max(18, badgeLabel.implicitWidth + 6)
                        height: 18
                        radius: 9
                        color: Theme.error

                        Label {
                            id: badgeLabel
                            anchors.centerIn: parent
                            text: root.folderAlertCount > 99 ? "99+" : root.folderAlertCount
                            color: "#FFFFFF"
                            font.pixelSize: 11
                            font.bold: true
                        }
                    }
                }

                Text {
                    visible: !root.collapsed
                    text: "폴더 알림"
                    font.pixelSize: Theme.fontBody
                    font.weight: Font.Normal
                    color: Theme.textSecondary
                    anchors.verticalCenter: parent.verticalCenter
                }
            }

            MouseArea {
                id: folderBellMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.openFolderAlerts()
            }
        }

        Rectangle {
            width: root.width
            height: 48
            color: root.currentIndex === 7 ? Theme.navActive : "transparent"

            Behavior on color { ColorAnimation { duration: Theme.animFast } }

            // hover 그라디언트 오버레이
            Rectangle {
                anchors.fill: parent
                visible: root.currentIndex !== 7
                opacity: settingsMouse.containsMouse ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: Theme.animFast } }
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: Qt.rgba(Theme.accentNeon.r, Theme.accentNeon.g, Theme.accentNeon.b, 0.07) }
                    GradientStop { position: 0.5; color: Qt.rgba(0, 0, 0, 0) }
                }
            }

            // 활성 인디케이터
            Rectangle {
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                width: 3; radius: 2; color: Theme.accentNeon
                height: root.currentIndex === 7 ? 22 : 8
                opacity: root.currentIndex === 7 ? 1 : 0
                Behavior on height  { NumberAnimation { duration: Theme.animNormal; easing.type: Easing.OutBack } }
                Behavior on opacity { NumberAnimation { duration: Theme.animFast } }
            }

            Row {
                anchors.left: parent.left
                anchors.leftMargin: Theme.spacingMd
                anchors.verticalCenter: parent.verticalCenter
                spacing: Theme.spacingSm + 4

                Text {
                    text: "⚙️"
                    font.pixelSize: 18
                    anchors.verticalCenter: parent.verticalCenter
                }

                Text {
                    visible: !root.collapsed
                    text: "설정"
                    font.pixelSize: Theme.fontBody
                    font.weight: root.currentIndex === 7 ? Font.DemiBold : Font.Normal
                    color: root.currentIndex === 7 ? Theme.textPrimary : Theme.textSecondary
                    anchors.verticalCenter: parent.verticalCenter
                    Behavior on color { ColorAnimation { duration: Theme.animFast } }
                }
            }

            MouseArea {
                id: settingsMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                    root.currentIndex = 7;
                    root.navigate(7);
                }
            }
        }
    }
}

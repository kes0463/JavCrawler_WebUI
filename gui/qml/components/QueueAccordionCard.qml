import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import ".."

GlassCard {
    id: root
    autoSize: false

    property string title: ""
    property string badgeStatus: "none"
    property string badgeLabel: ""
    property bool expanded: false
    property int collapsedHeight: Theme.queueCardHeaderHeight
    property int expandedHeight: Theme.queueCardExpandedHeight

    property var model: null
    property Component delegate: null
    property string emptyText: "항목이 없습니다."

    property bool showDivider: true

    default property alias actions: actionSlot.data

    contentMargins: 0
    clip: true

    Layout.fillWidth: true
    Layout.preferredHeight: root.expanded ? root.expandedHeight : root.collapsedHeight

    Behavior on Layout.preferredHeight {
        NumberAnimation { duration: Theme.animNormal; easing.type: Easing.OutCubic }
    }

    Item {
        id: header
        width: parent.width
        height: root.collapsedHeight

        Item {
            anchors.fill: parent
            anchors.leftMargin: Theme.spacingMd
            anchors.rightMargin: Theme.spacingMd

            RowLayout {
                anchors.fill: parent
                anchors.topMargin: 0
                anchors.bottomMargin: 0
                spacing: Theme.spacingMd

                // 좌측: 제목 + 칩 — 클릭 시 펼침(우측 액션/토글은 MouseArea 밖)
                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    RowLayout {
                        id: leftSection
                        anchors.fill: parent
                        spacing: Theme.spacingMd

                        Text {
                            text: root.title
                            font.pixelSize: Theme.fontSubtitle
                            font.weight: Font.DemiBold
                            color: Theme.textPrimary
                            elide: Text.ElideRight
                            Layout.alignment: Qt.AlignVCenter
                            // 배지가 제목 바로 옆에 붙도록, 타이틀은 남는 폭을 독점하지 않는다.
                            Layout.fillWidth: false
                            Layout.preferredWidth: Theme.queueHeaderTitleWidth
                            Layout.maximumWidth: Theme.queueHeaderTitleWidth
                        }

                        StatusBadge {
                            status: root.badgeStatus
                            label: root.badgeLabel
                            Layout.alignment: Qt.AlignVCenter
                        }

                        // 남는 공간 흡수
                        Item { Layout.fillWidth: true }
                    }
                    MouseArea {
                        anchors.fill: parent
                        onClicked: root.expanded = !root.expanded
                    }
                }

                // 우측: (액션들) [토글] — 토글은 맨 오른쪽 고정, 액션은 토글 바로 왼쪽에 붙여 오른쪽 정렬
                Item {
                    id: rightSection
                    Layout.preferredWidth: Theme.queueHeaderRightWidth
                    Layout.fillHeight: true

                    RowLayout {
                        anchors.fill: parent
                        spacing: Theme.spacingSm

                        Item { Layout.fillWidth: true } // 액션을 우측으로 밀기(모든 카드 동일 선 정렬)

                        RowLayout {
                            id: actionSlot
                            spacing: Theme.spacingSm
                            Layout.alignment: Qt.AlignVCenter
                            Layout.fillWidth: false
                            layoutDirection: Qt.RightToLeft
                        }

                        Item {
                            Layout.alignment: Qt.AlignVCenter
                            width: 28
                            Layout.fillHeight: true
                            Text {
                                id: chevronText
                                anchors.centerIn: parent
                                text: "▼"
                                font.pixelSize: 10
                                color: root.expanded ? Theme.accentNeon : Theme.textMuted
                                rotation: root.expanded ? 180 : 0
                                transformOrigin: Item.Center
                                Behavior on rotation { NumberAnimation { duration: Theme.animNormal; easing.type: Easing.OutCubic } }
                                Behavior on color    { ColorAnimation  { duration: Theme.animFast } }
                            }
                            MouseArea {
                                anchors.fill: parent
                                onClicked: root.expanded = !root.expanded
                            }
                        }
                    }
                }
            }
        }
    }

    Rectangle {
        visible: root.showDivider && root.expanded
        anchors.top: header.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        height: 1
        color: Theme.divider
        opacity: 0.6
    }

    Item {
        id: body
        anchors.top: header.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: Theme.spacingMd
        anchors.topMargin: root.showDivider ? Theme.spacingSm : 0
        visible: root.expanded
        opacity: root.expanded ? 1 : 0

        Behavior on opacity { NumberAnimation { duration: Theme.animFast } }

        ListView {
            boundsBehavior: Theme.boundsBehavior
            id: list
            anchors.fill: parent
            clip: true
            model: root.model
            delegate: root.delegate
            maximumFlickVelocity: Theme.maxVelocity
            flickDeceleration: Theme.flickDeceleration
            spacing: Theme.spacingSm

            ScrollBar.vertical: ScrollBar {
                policy: ScrollBar.AsNeeded
            }
        }

        Text {
            visible: list.count === 0
            anchors.centerIn: parent
            text: root.emptyText
            font.pixelSize: Theme.fontBody
            color: Theme.textMuted
        }
    }
}
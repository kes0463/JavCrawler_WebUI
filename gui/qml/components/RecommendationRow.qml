import QtQuick
import QtQuick.Controls
import ".."

Item {
    id: root
    implicitHeight: root.cardHeight
    implicitWidth: root.useCompactLayout ? root.contentWidth : 0

    property var items: []
    property int maxItems: 6
    property int cardWidth: 150
    property int cardHeight: 280
    property int coverHeight: 200
    property bool showGemBadge: false
    property bool showReason: false
    property int compactThreshold: 3

    readonly property var displayItems: (root.items || []).slice(0, root.maxItems)
    readonly property int itemCount: root.displayItems.length
    readonly property bool useCompactLayout: root.itemCount > 0 && root.itemCount < root.compactThreshold
    readonly property int contentWidth: root.itemCount > 0
        ? root.itemCount * root.cardWidth + (root.itemCount - 1) * Theme.spacingMd
        : 0

    readonly property Flickable flickable: scrollHost.visible ? scrollView.contentItem : null
    readonly property bool overflowHorizontal: scrollHost.visible && root.flickable
        && root.flickable.contentWidth > root.flickable.width + 2
    readonly property bool showRightFade: root.overflowHorizontal
        && root.flickable.contentX + root.flickable.width < root.flickable.contentWidth - 2
    readonly property bool showLeftFade: root.overflowHorizontal && root.flickable.contentX > 2

    Component {
        id: posterCardComponent

        Rectangle {
            id: cardRoot
            property var itemData

            width: root.cardWidth
            height: root.cardHeight
            radius: Theme.radiusMd
            color: Theme.surface
            border.color: cardMa.containsMouse ? Theme.glassBorderHover : Theme.glassBorder
            border.width: 1
            clip: true
            scale: cardMa.containsMouse ? 1.04 : 1.0
            Behavior on scale {
                NumberAnimation { duration: Theme.animFast; easing.type: Easing.OutCubic }
            }

            Column {
                anchors.fill: parent
                spacing: 0

                Rectangle {
                    width: parent.width
                    height: root.coverHeight
                    color: Theme.bgSecondary

                    Image {
                        anchors.fill: parent
                        source: cardRoot.itemData && cardRoot.itemData.cover_path
                            ? "file:///" + cardRoot.itemData.cover_path : ""
                        fillMode: Image.PreserveAspectCrop
                        asynchronous: true
                    }

                    Rectangle {
                        visible: root.showGemBadge
                        anchors.top: parent.top
                        anchors.left: parent.left
                        anchors.margins: 6
                        height: 22
                        radius: 11
                        width: gemLbl.implicitWidth + 12
                        color: cardRoot.itemData && cardRoot.itemData.gem_type === "underrated"
                            ? Qt.rgba(1, 180/255, 80/255, 0.92)
                            : Qt.rgba(0.45, 0.75, 1, 0.92)
                        Text {
                            id: gemLbl
                            anchors.centerIn: parent
                            text: cardRoot.itemData && cardRoot.itemData.gem_type === "underrated"
                                ? "재평가" : "미감상"
                            font.pixelSize: 10
                            font.weight: Font.Bold
                            color: "#000"
                        }
                    }

                    Rectangle {
                        anchors.top: parent.top
                        anchors.right: parent.right
                        anchors.margins: 6
                        width: 48
                        height: 22
                        radius: 11
                        color: Qt.rgba(0, 229/255, 255/255, 0.9)
                        Text {
                            anchors.centerIn: parent
                            text: cardRoot.itemData
                                ? Math.round((cardRoot.itemData.rec_score || 0) * 100) + "%" : ""
                            font.pixelSize: 11
                            font.weight: Font.Bold
                            color: "#000"
                        }
                    }

                    Text {
                        anchors.centerIn: parent
                        text: cardRoot.itemData ? (cardRoot.itemData.product_code || "") : ""
                        font.pixelSize: 14
                        font.weight: Font.Bold
                        color: Theme.textMuted
                        visible: !(cardRoot.itemData && cardRoot.itemData.cover_path)
                    }
                }

                Column {
                    width: parent.width
                    padding: 8
                    spacing: 3
                    Text {
                        text: cardRoot.itemData ? (cardRoot.itemData.product_code || "") : ""
                        font.pixelSize: 11
                        font.weight: Font.Bold
                        color: Theme.accentNeon
                        width: parent.width - 16
                        elide: Text.ElideRight
                    }
                    Text {
                        text: cardRoot.itemData ? (cardRoot.itemData.title_ko || "제목 없음") : ""
                        font.pixelSize: 11
                        color: Theme.textPrimary
                        width: parent.width - 16
                        elide: Text.ElideRight
                        maximumLineCount: 2
                        wrapMode: Text.WordWrap
                    }
                    Text {
                        visible: cardRoot.itemData && !!cardRoot.itemData.actors_ko
                        text: cardRoot.itemData ? (cardRoot.itemData.actors_ko || "") : ""
                        font.pixelSize: 10
                        color: Theme.textSecondary
                        width: parent.width - 16
                        elide: Text.ElideRight
                    }
                    Text {
                        visible: root.showReason && cardRoot.itemData && !!cardRoot.itemData.reason
                        text: cardRoot.itemData.reason || ""
                        font.pixelSize: 10
                        color: Theme.textSecondary
                        width: parent.width - 16
                        wrapMode: Text.WordWrap
                        maximumLineCount: 2
                    }
                }
            }

            MouseArea {
                id: cardMa
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                    if (cardRoot.itemData && cardRoot.itemData.product_code)
                        window.navigateToLibraryDetail(cardRoot.itemData.product_code)
                }
            }
        }
    }

    // ── 소량: 중앙 정렬, 스크롤 없음 ─────────────────────────────────
    Item {
        visible: root.useCompactLayout
        anchors.fill: parent
        height: root.cardHeight

        Item {
            width: root.contentWidth
            height: root.cardHeight
            anchors.horizontalCenter: parent.horizontalCenter

            Repeater {
                model: root.displayItems
                delegate: Loader {
                    required property int index
                    required property var modelData
                    x: index * (root.cardWidth + Theme.spacingMd)
                    width: root.cardWidth
                    height: root.cardHeight
                    sourceComponent: posterCardComponent
                    onLoaded: if (item) item.itemData = modelData
                    onItemChanged: if (item) item.itemData = modelData
                }
            }
        }
    }

    // ── 다량: 가로 스크롤 + 스크롤바·그라데이션 힌트 ─────────────────
    Item {
        id: scrollHost
        visible: !root.useCompactLayout && root.itemCount > 0
        anchors.fill: parent
        height: root.cardHeight

        AppScrollView {
            id: scrollView
            anchors.fill: parent
            clip: true
            contentWidth: root.contentWidth
            ScrollBar.horizontal.policy: root.overflowHorizontal ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff
            ScrollBar.vertical.policy: ScrollBar.AlwaysOff

            Row {
                height: root.cardHeight
                spacing: Theme.spacingMd

                Repeater {
                    model: root.displayItems
                    delegate: Loader {
                        required property var modelData
                        width: root.cardWidth
                        height: root.cardHeight
                        sourceComponent: posterCardComponent
                        onLoaded: if (item) item.itemData = modelData
                        onItemChanged: if (item) item.itemData = modelData
                    }
                }
            }
        }

        Rectangle {
            z: 2
            visible: root.showRightFade
            anchors.right: parent.right
            anchors.top: parent.top
            height: parent.height
            width: 48
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: "transparent" }
                GradientStop { position: 1.0; color: Theme.surface }
            }
        }

        Rectangle {
            z: 2
            visible: root.showLeftFade
            anchors.left: parent.left
            anchors.top: parent.top
            height: parent.height
            width: 48
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0.0; color: Theme.surface }
                GradientStop { position: 1.0; color: "transparent" }
            }
        }
    }
}

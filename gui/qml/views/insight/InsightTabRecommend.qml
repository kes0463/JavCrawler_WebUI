import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../../components"
import "../.."

ColumnLayout {
    id: tab
    width: parent ? parent.width : 0
    spacing: Theme.spacingLg

    property var nextWatch: []
    property var hiddenGems: []
    property var favoriteActorPicks: []
    property var recs: []

    property int segmentIndex: 0

    readonly property var segmentLabels: ["다음에 볼", "놓친 보석", "오늘"]
    readonly property var segmentItems: [tab.nextWatch, tab.hiddenGems, tab.recs]
    readonly property var currentItems: tab.segmentItems[tab.segmentIndex] || []
    readonly property string segmentSubtitle: {
        if (tab.segmentIndex === 0)
            return tab.nextWatch.length > 0 && tab.nextWatch[0].source === "embedding"
                ? "임베딩 기반 추천" : "취향 점수 기반 (규칙)"
        if (tab.segmentIndex === 1)
            return "미감상·저평가인데 취향과 잘 맞는 작품"
        return "규칙 기반 빠른 추천"
    }
    readonly property string emptyMessage: {
        if (tab.segmentIndex === 0)
            return "아직 충분한 취향 데이터가 없습니다.\n영상을 시청하고 별점을 남기면 추천이 시작됩니다."
        if (tab.segmentIndex === 1)
            return "취향 데이터가 쌓이면 미감상·저평가 작품 중\n취향과 잘 맞는 보석을 찾아 드립니다."
        return "오늘의 추천이 없습니다."
    }

    GlassCard {
        id: recommendCard
        Layout.fillWidth: true
        Layout.bottomMargin: Theme.spacingLg
        autoSize: true

        ColumnLayout {
            width: parent.width
            spacing: Theme.spacingMd

            InsightSectionHeader {
                Layout.fillWidth: true
                icon: "🎯"
                title: "추천"
                subtitle: tab.segmentSubtitle
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.spacingXs
                Repeater {
                    model: tab.segmentLabels.length
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 32
                        radius: Theme.radiusSm
                        color: tab.segmentIndex === index
                            ? Qt.rgba(Theme.accentNeon.r, Theme.accentNeon.g, Theme.accentNeon.b, 0.12)
                            : Theme.surfaceLight
                        border.color: tab.segmentIndex === index ? Theme.accentNeon : Theme.glassBorder
                        border.width: 1
                        Text {
                            anchors.centerIn: parent
                            text: tab.segmentLabels[index]
                            font.pixelSize: Theme.fontCaption
                            font.weight: tab.segmentIndex === index ? Font.DemiBold : Font.Normal
                            color: tab.segmentIndex === index ? Theme.accentNeon : Theme.textSecondary
                        }
                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: tab.segmentIndex = index
                        }
                    }
                }
            }

            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.glassBorder }

            RecommendationRow {
                Layout.fillWidth: true
                visible: tab.segmentIndex !== 2 && tab.currentItems.length > 0
                items: tab.currentItems
                maxItems: tab.segmentIndex === 1 ? 6 : 5
                cardHeight: tab.segmentIndex === 1 ? 300 : 280
                coverHeight: 200
                showGemBadge: tab.segmentIndex === 1
                showReason: tab.segmentIndex === 1
            }

            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: todayFlow.visible ? todayFlow.height : 0
                visible: tab.segmentIndex === 2 && tab.recs.length > 0

                Flow {
                    id: todayFlow
                    width: parent.width
                    spacing: Theme.spacingSm
                    Repeater {
                        model: tab.recs.slice(0, 6)
                        Rectangle {
                            radius: Theme.radiusSm
                            color: Theme.surfaceLight
                            border.color: Theme.glassBorder
                            height: 28
                            width: recChipText.implicitWidth + 16
                            Text {
                                id: recChipText
                                anchors.centerIn: parent
                                text: (modelData.product_code || "") + " "
                                    + Math.round((modelData.rec_score || 0) * 100) + "%"
                                font.pixelSize: Theme.fontCaption
                                color: Theme.textPrimary
                            }
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: window.navigateToLibraryDetail(modelData.product_code)
                            }
                        }
                    }
                }
            }

            EmptyInsightHint {
                visible: tab.currentItems.length === 0
                icon: tab.segmentIndex === 1 ? "💎" : "🎯"
                message: tab.emptyMessage.split("\n")[0]
                hint: tab.emptyMessage.indexOf("\n") >= 0
                    ? tab.emptyMessage.split("\n").slice(1).join("\n") : ""
            }
        }
    }

    Item { Layout.preferredHeight: Theme.spacingLg }

    GlassCard {
        Layout.fillWidth: true
        Layout.bottomMargin: Theme.spacingLg
        autoSize: true
        visible: tab.favoriteActorPicks.length > 0

        ColumnLayout {
            width: parent.width
            spacing: Theme.spacingMd

            InsightSectionHeader {
                Layout.fillWidth: true
                icon: "⭐"
                title: "좋아하는 배우의 추천작"
                subtitle: "즐겨찾는 배우의 미시청 작품 중 취향에 맞는 작품"
            }

            RecommendationRow {
                Layout.fillWidth: true
                items: tab.favoriteActorPicks
                maxItems: 6
                cardHeight: 300
                coverHeight: 200
                showReason: true
            }
        }
    }

    Item { Layout.preferredHeight: Theme.spacingLg }
}

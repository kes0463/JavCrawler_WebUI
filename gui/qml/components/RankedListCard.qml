import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

GlassCard {
    id: root
    autoSize: true
    Layout.fillWidth: true
    Layout.bottomMargin: Theme.spacingLg

    property string title: ""
    property string icon: ""
    property string subtitle: "누적 취향 점수"
    property var items: []
    property int maxItems: 5
    property string mode: "rank"
    property var colorFn: null

    readonly property var displayItems: (root.items || []).slice(0, root.maxItems)
    readonly property int itemCount: root.displayItems.length
    readonly property int maxScore: root.itemCount > 0 ? (root.displayItems[0].score || 1) : 1
    readonly property bool needsScroll: root.itemCount >= 8
    readonly property int rowStride: 40
    readonly property int listBodyHeight: root.itemCount * root.rowStride

    ColumnLayout {
        width: parent.width
        spacing: Theme.spacingSm

        InsightSectionHeader {
            Layout.fillWidth: true
            icon: root.icon
            title: root.title
            subtitle: root.subtitle
        }

        Rectangle {
            Layout.fillWidth: true
            height: 1
            color: Theme.glassBorder
            visible: root.itemCount > 0
        }

        Item {
            id: listHost
            Layout.fillWidth: true
            Layout.preferredHeight: root.itemCount > 0
                ? (root.needsScroll ? Math.min(280, root.listBodyHeight) : root.listBodyHeight)
                : 0
            visible: root.itemCount > 0

            AppScrollView {
                anchors.fill: parent
                clip: true
                visible: root.needsScroll
                contentWidth: availableWidth
                ScrollBar.vertical.policy: ScrollBar.AsNeeded
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                Column {
                    id: scrollColumn
                    width: parent.width
                    spacing: 4
                    Repeater {
                        model: root.itemCount
                        delegate: RankedListRow {
                            width: scrollColumn.width
                            rowIndex: index
                            rowData: root.displayItems[index]
                            mode: root.mode
                            maxScore: root.maxScore
                            colorFn: root.colorFn
                        }
                    }
                }
            }

            Column {
                id: plainColumn
                width: parent.width
                spacing: 4
                visible: !root.needsScroll
                Repeater {
                    model: root.itemCount
                    delegate: RankedListRow {
                        width: plainColumn.width
                        rowIndex: index
                        rowData: root.displayItems[index]
                        mode: root.mode
                        maxScore: root.maxScore
                        colorFn: root.colorFn
                    }
                }
            }
        }

        EmptyInsightHint {
            Layout.fillWidth: true
            visible: root.itemCount === 0
            icon: root.icon
            message: root.title + " 데이터가 없습니다."
            hint: "영상을 시청하면 자동으로 분석됩니다."
        }
    }
}

import QtQuick
import QtQuick.Layouts
import ".."

Item {
    id: root
    Layout.fillWidth: true
    implicitHeight: grid.implicitHeight

    property var stats: ({})

    readonly property var kpiModel: [
        { label: "전체 작품", value: (root.stats.total || 0) + "편", icon: "📚" },
        { label: "시청 완료", value: (root.stats.completed || 0) + "편", icon: "✅" },
        { label: "완독률", value: Math.round((root.stats.completion_rate || 0) * 100) + "%", icon: "📈" },
        { label: "평균 별점", value: (root.stats.avg_rating || 0).toFixed(1) + "★", icon: "⭐" },
        { label: "총 시청", value: (root.stats.total_watch_hours || 0) + "시간", icon: "⏱" },
    ]

    GridLayout {
        id: grid
        anchors.fill: parent
        columns: root.width < 900 ? 2 : 5
        rowSpacing: Theme.spacingMd
        columnSpacing: Theme.spacingMd

        Repeater {
            model: root.kpiModel

            GlassCard {
                autoSize: false
                Layout.fillWidth: true
                Layout.preferredHeight: 90

                ColumnLayout {
                    anchors.centerIn: parent
                    spacing: 4
                    Text {
                        text: modelData.icon + " " + modelData.label
                        font.pixelSize: Theme.fontCaption
                        color: Theme.textSecondary
                        Layout.alignment: Qt.AlignHCenter
                    }
                    Text {
                        text: modelData.value
                        font.pixelSize: Theme.fontSubtitle
                        font.weight: Font.ExtraBold
                        color: Theme.accentNeon
                        Layout.alignment: Qt.AlignHCenter
                    }
                }
            }
        }
    }
}

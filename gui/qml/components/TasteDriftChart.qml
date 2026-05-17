import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import ".."

Item {
    id: root

    property var timeline: ({})
    property bool hasData: timeline.has_data === true
    property var legend: timeline.legend || []
    property var series: timeline.series || []
    property string driftNote: timeline.drift_note || ""

    readonly property int barWidth: 52
    readonly property int barGap: Theme.spacingSm
    readonly property int barHeight: 120
    readonly property int _chartWidth: Math.max(barWidth, series.length * (barWidth + barGap) - barGap)

    implicitWidth: _chartWidth
    implicitHeight: barHeight + 28 + (driftNote ? 36 : 0)

    function segmentColor(colorIndex, name) {
        if (name === "기타" || colorIndex < 0)
            return Qt.rgba(1, 1, 1, 0.14)
        var palette = [
            Theme.accentNeon,
            Qt.rgba(1, 120/255, 180/255, 0.88),
            Qt.rgba(140/255, 1, 120/255, 0.85),
            Qt.rgba(255/255, 200/255, 80/255, 0.9),
            Qt.rgba(160/255, 140/255, 1, 0.88),
            Qt.rgba(80/255, 220/255, 255/255, 0.88),
            Qt.rgba(255/255, 140/255, 100/255, 0.88),
            Qt.rgba(200/255, 200/255, 200/255, 0.75)
        ]
        return palette[Math.abs(colorIndex) % palette.length]
    }

    function legendColorIndex(name) {
        for (var i = 0; i < legend.length; i++) {
            if (legend[i].name === name)
                return legend[i].color_index !== undefined ? legend[i].color_index : i
        }
        return -1
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.spacingSm

        Text {
            Layout.fillWidth: true
            visible: !root.hasData
            text: timeline.empty_message || "시청 데이터가 없습니다."
            font.pixelSize: Theme.fontCaption
            color: Theme.textMuted
            wrapMode: Text.Wrap
        }

        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: root.barHeight + 24
            visible: root.hasData

            Row {
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: root.barGap
                bottomPadding: 22

                Repeater {
                    model: root.series

                    Item {
                        width: root.barWidth
                        height: root.barHeight + 22

                        Column {
                            anchors.bottom: parent.bottom
                            anchors.horizontalCenter: parent.horizontalCenter
                            width: root.barWidth
                            spacing: 0

                            Repeater {
                                model: {
                                    var s = modelData.stacks || []
                                    var out = []
                                    for (var i = s.length - 1; i >= 0; i--)
                                        out.push(s[i])
                                    return out
                                }

                                Rectangle {
                                    width: root.barWidth
                                    height: root.barHeight * Math.max(0, (modelData.pct || 0) / 100)
                                    color: root.segmentColor(
                                        root.legendColorIndex(modelData.name),
                                        modelData.name
                                    )
                                    border.width: 1
                                    border.color: Qt.rgba(0, 0, 0, 0.25)
                                }
                            }
                        }

                        Text {
                            anchors.bottom: parent.bottom
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: modelData.label || modelData.period || ""
                            font.pixelSize: 10
                            color: Theme.textMuted
                        }

                        ToolTip {
                            visible: barMa.containsMouse
                            delay: 300
                            text: {
                                var lines = [modelData.label || modelData.period || ""]
                                var stacks = modelData.stacks || []
                                for (var i = 0; i < stacks.length; i++)
                                    lines.push(stacks[i].name + " " + (stacks[i].pct || 0) + "%")
                                return lines.join("\n")
                            }
                        }

                        MouseArea {
                            id: barMa
                            anchors.fill: parent
                            hoverEnabled: true
                            acceptedButtons: Qt.NoButton
                        }
                    }
                }
            }
        }

        Flow {
            Layout.fillWidth: true
            spacing: Theme.spacingSm
            visible: root.hasData && root.legend.length > 0

            Repeater {
                model: root.legend

                Row {
                    spacing: 4
                    Rectangle {
                        width: 10
                        height: 10
                        radius: 2
                        anchors.verticalCenter: parent.verticalCenter
                        color: root.segmentColor(
                            modelData.color_index !== undefined ? modelData.color_index : index,
                            modelData.name
                        )
                    }
                    Text {
                        text: modelData.name || ""
                        font.pixelSize: 10
                        color: Theme.textSecondary
                    }
                }
            }
        }

        Text {
            Layout.fillWidth: true
            visible: root.hasData && root.driftNote.length > 0
            text: root.driftNote
            font.pixelSize: Theme.fontCaption
            color: Theme.textSecondary
            wrapMode: Text.Wrap
        }
    }
}

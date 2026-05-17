import QtQuick
import QtQuick.Layouts
import ".."

Item {
    id: root
    property var days: ({})
    property int year: new Date().getFullYear()
    property int cellSize: 11
    property int cellGap: 3
    /** 섹션 제목이 밖에 있으면 false */
    property bool showYearLabel: false

    readonly property int _rows: 7
    readonly property int _weekCols: 53
    readonly property real _gridW: _weekCols * (cellSize + cellGap)
    readonly property real _gridH: _rows * (cellSize + cellGap)

    implicitWidth: _gridW
    implicitHeight: (showYearLabel ? 22 : 0) + _gridH + 4

    onDaysChanged: heatCanvas.requestPaint()
    onYearChanged: heatCanvas.requestPaint()
    onCellSizeChanged: heatCanvas.requestPaint()
    onCellGapChanged: heatCanvas.requestPaint()
    onWidthChanged: heatCanvas.requestPaint()

    function _maxCount() {
        var m = 0
        for (var k in days) {
            if (days[k] > m) m = days[k]
        }
        return m
    }

    function _level(count) {
        var mx = _maxCount()
        if (!count || mx <= 0) return 0
        var r = count / mx
        if (r <= 0.25) return 1
        if (r <= 0.5) return 2
        if (r <= 0.75) return 3
        return 4
    }

    function _color(level) {
        if (level <= 0) return Qt.rgba(1, 1, 1, 0.06)
        if (level === 1) return Qt.rgba(0, 229/255, 255/255, 0.25)
        if (level === 2) return Qt.rgba(0, 229/255, 255/255, 0.45)
        if (level === 3) return Qt.rgba(0, 229/255, 255/255, 0.65)
        return Theme.accentNeon
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.spacingXs

        Text {
            Layout.fillWidth: true
            visible: root.showYearLabel
            text: root.year + "년 감상"
            font.pixelSize: Theme.fontCaption
            color: Theme.textSecondary
        }

        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: root._gridH
            Layout.minimumHeight: root._gridH

            Canvas {
                id: heatCanvas
                anchors.verticalCenter: parent.verticalCenter
                width: root._gridW
                height: root._gridH
                x: Math.max(0, (parent.width - root._gridW) / 2)

                onPaint: {
                    var ctx = getContext("2d")
                    ctx.reset()
                    var start = new Date(root.year, 0, 1)
                    var dow = start.getDay()
                    var col = 0
                    var row = dow === 0 ? 6 : dow - 1
                    var d = new Date(start.getTime())
                    var sz = root.cellSize
                    var gap = root.cellGap
                    var offsetX = 0

                    while (d.getFullYear() === root.year) {
                        var key = d.getFullYear() + "-" +
                            ("0" + (d.getMonth() + 1)).slice(-2) + "-" +
                            ("0" + d.getDate()).slice(-2)
                        var cnt = root.days[key] || 0
                        var lv = root._level(cnt)
                        ctx.fillStyle = root._color(lv)
                        var x = offsetX + col * (sz + gap)
                        var y = row * (sz + gap)
                        ctx.fillRect(x, y, sz, sz)
                        d.setDate(d.getDate() + 1)
                        row++
                        if (row > 6) { row = 0; col++ }
                    }
                }
            }
        }
    }
}

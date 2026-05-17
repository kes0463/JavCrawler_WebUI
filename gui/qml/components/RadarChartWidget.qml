import QtQuick
import ".."

Canvas {
    id: root
    property var axes: []  // [{label, value}, ...]
    property color strokeColor: Theme.accentNeon
    property color fillColor: Qt.rgba(0, 229/255, 255/255, 0.18)

    implicitWidth: 280
    implicitHeight: 280

    onAxesChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()

    onPaint: {
        var ctx = getContext("2d")
        ctx.reset()
        var w = width
        var h = height
        if (w <= 0 || h <= 0)
            return
        var cx = w / 2
        var cy = h / 2
        var radius = Math.min(w, h) * 0.36
        var n = axes.length
        if (n < 3)
            return

        function pointAt(i, scale) {
            var angle = -Math.PI / 2 + (2 * Math.PI * i / n)
            var r = radius * scale
            return { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) }
        }

        ctx.strokeStyle = Qt.rgba(1, 1, 1, 0.12)
        ctx.lineWidth = 1
        for (var ring = 1; ring <= 4; ring++) {
            ctx.beginPath()
            for (var ri = 0; ri < n; ri++) {
                var p = pointAt(ri, ring / 4)
                if (ri === 0) ctx.moveTo(p.x, p.y)
                else ctx.lineTo(p.x, p.y)
            }
            ctx.closePath()
            ctx.stroke()
        }

        for (var li = 0; li < n; li++) {
            var lp = pointAt(li, 1)
            ctx.beginPath()
            ctx.moveTo(cx, cy)
            ctx.lineTo(lp.x, lp.y)
            ctx.stroke()
        }

        ctx.beginPath()
        for (var vi = 0; vi < n; vi++) {
            var v = Math.max(0, Math.min(1, axes[vi].value || 0))
            var vp = pointAt(vi, v)
            if (vi === 0) ctx.moveTo(vp.x, vp.y)
            else ctx.lineTo(vp.x, vp.y)
        }
        ctx.closePath()
        ctx.fillStyle = fillColor
        ctx.fill()
        ctx.strokeStyle = strokeColor
        ctx.lineWidth = 2
        ctx.stroke()

        ctx.fillStyle = Theme.textSecondary
        ctx.font = "11px sans-serif"
        for (var ti = 0; ti < n; ti++) {
            var tp = pointAt(ti, 1.18)
            var label = axes[ti].label || ""
            var tw = ctx.measureText(label).width
            ctx.fillText(label, tp.x - tw / 2, tp.y + 4)
        }
    }
}

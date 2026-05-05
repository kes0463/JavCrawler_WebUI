import QtQuick

Canvas {
    id: root

    property rect videoRect: Qt.rect(0, 0, 0, 0)
    property var cues: []
    property real currentPositionMs: 0
    property real fontSizeScale: 1.0

    onCuesChanged: requestPaint()
    onCurrentPositionMsChanged: requestPaint()
    onVideoRectChanged: requestPaint()
    onFontSizeScaleChanged: requestPaint()

    onPaint: {
        var ctx = getContext("2d")
        ctx.clearRect(0, 0, width, height)
        if (!videoRect.width || !videoRect.height) return
        for (var ci = 0; ci < cues.length; ci++)
            _drawCue(ctx, cues[ci])
    }

    function _argbToRgba(argb) {
        if (!argb || argb.length < 7) return "rgba(255,255,255,1)"
        var s = argb.replace(/^#/, "")
        if (s.length === 8) {
            var a = parseInt(s.substring(0, 2), 16)
            var r = parseInt(s.substring(2, 4), 16)
            var g = parseInt(s.substring(4, 6), 16)
            var b = parseInt(s.substring(6, 8), 16)
            return "rgba(" + r + "," + g + "," + b + "," + (a / 255).toFixed(3) + ")"
        }
        return "rgba(255,255,255,1)"
    }

    function _buildFont(font, px) {
        var s = (font.italic ? "italic " : "") + (font.bold ? "bold " : "")
        return s + px + "px \"" + (font.family || "Arial") + "\""
    }

    // Parse subset SVG path (M, L, C, Z only) into active canvas path.
    function _traceSvgPath(ctx, d) {
        var tokens = d.match(/[MLCZmlcz]|-?\d+(?:\.\d+)?/g)
        if (!tokens) return
        ctx.beginPath()
        var i = 0, x1, y1, x2, y2, ex, ey
        while (i < tokens.length) {
            var cmd = tokens[i++]
            if (cmd === "M" || cmd === "m") {
                ctx.moveTo(parseFloat(tokens[i++]), parseFloat(tokens[i++]))
            } else if (cmd === "L" || cmd === "l") {
                ctx.lineTo(parseFloat(tokens[i++]), parseFloat(tokens[i++]))
            } else if (cmd === "C" || cmd === "c") {
                x1 = parseFloat(tokens[i++]); y1 = parseFloat(tokens[i++])
                x2 = parseFloat(tokens[i++]); y2 = parseFloat(tokens[i++])
                ex = parseFloat(tokens[i++]); ey = parseFloat(tokens[i++])
                ctx.bezierCurveTo(x1, y1, x2, y2, ex, ey)
            } else if (cmd === "Z" || cmd === "z") {
                ctx.closePath()
            }
        }
    }

    function _computeFadeAlpha(line, cue) {
        var alpha = 1.0
        var fadeIn  = line.fade_in_ms  || 0
        var fadeOut = line.fade_out_ms || 0
        if (fadeIn > 0) {
            var elapsed = currentPositionMs - cue.start_ms
            if (elapsed < fadeIn) alpha = Math.min(alpha, elapsed / fadeIn)
        }
        if (fadeOut > 0) {
            var remaining = cue.end_ms - currentPositionMs
            if (remaining < fadeOut) alpha = Math.min(alpha, remaining / fadeOut)
        }
        return Math.max(0, Math.min(1, alpha))
    }

    function _drawCue(ctx, cue) {
        if (!cue || !cue.ass) return
        var ass    = cue.ass
        var pResX  = ass.play_res_x || 640
        var pResY  = ass.play_res_y || 480
        var sx     = videoRect.width  / pResX
        var sy     = videoRect.height / pResY
        var ox     = videoRect.x
        var oy     = videoRect.y
        var lines  = ass.lines || []
        for (var li = 0; li < lines.length; li++)
            _drawLine(ctx, lines[li], sx, sy, ox, oy, cue)
    }

    function _drawLine(ctx, line, sx, sy, ox, oy, cue) {
        var runs = line.runs || []
        if (runs.length === 0) return

        var fadeAlpha = _computeFadeAlpha(line, cue)
        if (fadeAlpha <= 0) return

        ctx.save()
        ctx.globalAlpha = fadeAlpha

        var vw = videoRect.width
        var vh = videoRect.height
        var an       = line.an       || 2
        var marginL  = (line.margin_l || 10) * sx
        var marginR  = (line.margin_r || 10) * sx
        var marginV  = (line.margin_v || 10) * sy

        // an layout:  7 8 9 / 4 5 6 / 1 2 3
        var col = (an - 1) % 3               // 0=left 1=center 2=right
        var row = Math.floor((an - 1) / 3)   // 0=bottom 1=middle 2=top

        // ── first pass: measure widths ────────────────────────
        var totalW = 0
        var runM   = []
        for (var ri = 0; ri < runs.length; ri++) {
            var run = runs[ri]
            var rw, rh
            if (run.kind === "text") {
                var fsz = (run.font.size || 20) * sy * root.fontSizeScale
                ctx.font = _buildFont(run.font, fsz)
                rw = ctx.measureText(run.text).width
                rh = fsz
            } else {
                rw = run.bbox[2] * sx
                rh = run.bbox[3] * sy
            }
            runM.push({ w: rw, h: rh })
            totalW += rw
        }

        // ── anchor point ──────────────────────────────────────
        var anchorX, anchorY
        if (line.pos) {
            anchorX = ox + line.pos[0] * sx
            anchorY = oy + line.pos[1] * sy
        } else {
            anchorX = (col === 0) ? ox + marginL
                    : (col === 1) ? ox + vw / 2
                    :               ox + vw - marginR
            anchorY = (row === 0) ? oy + vh - marginV
                    : (row === 1) ? oy + vh / 2
                    :               oy + marginV
        }

        var startX = (col === 0) ? anchorX
                   : (col === 1) ? anchorX - totalW / 2
                   :               anchorX - totalW

        // Canvas textBaseline aligns with the anchor Y
        var baseline = (row === 0) ? "bottom"
                     : (row === 1) ? "middle"
                     :               "top"
        ctx.textBaseline = baseline
        var baselineY = anchorY

        // ── second pass: draw ─────────────────────────────────
        var curX  = startX
        var scale = Math.min(sx, sy)
        for (var ri2 = 0; ri2 < runs.length; ri2++) {
            var run2 = runs[ri2]
            var rm   = runM[ri2]

            if (run2.kind === "text") {
                var fsz2 = (run2.font.size || 20) * sy * root.fontSizeScale
                ctx.font = _buildFont(run2.font, fsz2)
                var bord = (run2.bord || 0) * scale
                var shad = (run2.shad || 0) * scale

                if (shad > 0) {
                    ctx.fillStyle = _argbToRgba(run2.shadow)
                    ctx.fillText(run2.text, curX + shad, baselineY + shad)
                }
                if (bord > 0) {
                    ctx.strokeStyle  = _argbToRgba(run2.outline)
                    ctx.lineWidth    = bord * 2
                    ctx.lineJoin     = "round"
                    ctx.strokeText(run2.text, curX, baselineY)
                }
                ctx.fillStyle = _argbToRgba(run2.primary)
                ctx.fillText(run2.text, curX, baselineY)

            } else if (run2.kind === "drawing") {
                // Vertical origin: same logic as textBaseline
                var drawY = (row === 0) ? baselineY - rm.h
                          : (row === 1) ? baselineY - rm.h / 2
                          :               baselineY

                ctx.save()
                ctx.translate(curX - run2.bbox[0] * sx, drawY - run2.bbox[1] * sy)
                ctx.scale(sx, sy)
                _traceSvgPath(ctx, run2.path)
                if ((run2.stroke_w || 0) > 0) {
                    ctx.strokeStyle = _argbToRgba(run2.stroke)
                    ctx.lineWidth   = run2.stroke_w * 2
                    ctx.lineJoin    = "round"
                    ctx.stroke()
                }
                ctx.fillStyle = _argbToRgba(run2.fill)
                ctx.fill()
                ctx.restore()
            }

            curX += rm.w
        }

        ctx.restore()
    }
}

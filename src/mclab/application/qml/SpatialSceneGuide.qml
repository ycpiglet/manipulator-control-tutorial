import QtQuick
import QtQuick.Controls

Item {
    id: guide
    property bool compact: false
    property string lab: backend.selectedScenario.lab || ""
    property bool isTracking: lab === "lab03" && !backend.selectedScenario.spatialMotion
    property bool isTwoLink: lab === "lab03" && backend.selectedScenario.spatialMotion
    property bool isPanda: lab === "lab04"
    property bool isWall: backend.selectedScenario.showWall || false
    property real handX: Number(backend.telemetry.hand_x || backend.telemetry.position || 0)
    property real handY: Number(backend.telemetry.hand_y || 0)
    property real targetX: Number(backend.telemetry.target_x
                                  || backend.telemetry.target_position || 0)
    property real targetY: Number(backend.telemetry.target_y || 0)
    property real appliedForce: Number(backend.telemetry.wall_force_x
                                       || backend.telemetry.force || 0)
    property real labelScale: compact ? 1.0
                                      : Math.max(1.0, Math.min(1.25, width / 1280.0))
    property real sceneTop: compact ? 56 : 78
    property real floorLineY: height - (compact ? 40 : 58)
    property real trackingRailY: floorLineY - (compact ? 23 : 34)
    property real markerDeltaX: Math.max(-0.7, Math.min(0.7, targetX - handX))
    property real markerDeltaY: Math.max(-0.7, Math.min(0.7, targetY - handY))
    property real currentMarkerX: isTracking ? width * 0.47
                                             : isTwoLink ? width * 0.61 : width * 0.59
    property real currentMarkerY: isTracking ? trackingRailY - 31
                                             : isTwoLink
                                               ? sceneTop + (floorLineY - sceneTop) * 0.60
                                               : sceneTop + (floorLineY - sceneTop) * 0.35
    property real targetMarkerX: isTracking
                                 ? width * 0.67
                                   + Math.max(-0.8, Math.min(0.8, targetX - handX))
                                     * width * 0.10
                                 : width * (isTwoLink ? 0.70 : 0.68)
                                   + markerDeltaX * width * 0.10
    property real targetMarkerY: isTracking ? trackingRailY - 31
                                 : sceneTop
                                   + (floorLineY - sceneTop) * (isTwoLink ? 0.22 : 0.17)
                                   - markerDeltaY * height * 0.10
    visible: backend.safeMode && (lab === "lab03" || lab === "lab04")

    onHandXChanged: drawing.requestPaint()
    onHandYChanged: drawing.requestPaint()
    onTargetXChanged: drawing.requestPaint()
    onTargetYChanged: drawing.requestPaint()
    onAppliedForceChanged: drawing.requestPaint()
    onWidthChanged: drawing.requestPaint()
    onHeightChanged: drawing.requestPaint()

    function line(ctx, x1, y1, x2, y2, color, width) {
        ctx.strokeStyle = color
        ctx.lineWidth = width
        ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke()
    }

    function circle(ctx, x, y, radius, color) {
        ctx.fillStyle = color
        ctx.beginPath(); ctx.arc(x, y, radius, 0, Math.PI * 2); ctx.fill()
    }

    function diamond(ctx, x, y, radius, color) {
        ctx.fillStyle = color
        ctx.save(); ctx.translate(x, y); ctx.rotate(Math.PI / 4)
        ctx.fillRect(-radius, -radius, radius * 2, radius * 2); ctx.restore()
    }

    function dashedLink(ctx, x1, y1, x2, y2) {
        ctx.strokeStyle = "#C084FC"
        ctx.lineWidth = compact ? 2 : 3 * labelScale
        ctx.setLineDash([6 * labelScale, 5 * labelScale])
        ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke()
        ctx.setLineDash([])
    }

    Canvas {
        id: drawing
        anchors.fill: parent
        Accessible.ignored: true

        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            var top = guide.sceneTop
            var floorY = guide.floorLineY

            ctx.fillStyle = "#D7DEE8"
            ctx.fillRect(0, floorY, width, height - floorY)
            guide.line(ctx, 8, floorY, width - 8, floorY, "#94A3B8", 2)
            ctx.strokeStyle = "#B8C4D4"
            ctx.lineWidth = 1
            for (var tick = 1; tick < 7; ++tick) {
                var gridX = width * tick / 7
                ctx.beginPath(); ctx.moveTo(gridX, floorY)
                ctx.lineTo(gridX - 14, height); ctx.stroke()
            }

            if (guide.isTracking) {
                var railY = guide.trackingRailY
                var currentX = guide.currentMarkerX
                var targetX = guide.targetMarkerX
                guide.line(ctx, 32, railY, width - 38, railY, "#64748B", guide.compact ? 4 : 6)
                for (var railTick = 0; railTick < 7; ++railTick) {
                    var markX = 38 + (width - 82) * railTick / 6
                    guide.line(ctx, markX, railY - 6, markX, railY + 7, "#94A3B8", 1)
                }
                guide.dashedLink(ctx, currentX, railY - 12, targetX, railY - 12)
                ctx.fillStyle = "#22D3EE"
                ctx.fillRect(currentX - 22, railY - 25, 44, 25)
                guide.circle(ctx, currentX, railY - 31, guide.compact ? 5 : 7, "#22D3EE")
                guide.diamond(ctx, targetX, railY - 31, guide.compact ? 7 : 9, "#C084FC")
                return
            }

            if (guide.isTwoLink) {
                var baseX = width * 0.27
                var baseY = floorY - 3
                var elbowX = width * 0.45
                var elbowY = top + (floorY - top) * 0.30
                var handX = guide.currentMarkerX
                var handY = guide.currentMarkerY
                var goalX = guide.targetMarkerX
                var goalY = guide.targetMarkerY
                ctx.strokeStyle = "#386BAD"
                ctx.lineWidth = guide.compact ? 2 : 3
                ctx.beginPath(); ctx.arc(baseX, baseY, width * 0.39, Math.PI * 1.08, Math.PI * 1.92)
                ctx.stroke()
                guide.line(ctx, baseX, baseY, elbowX, elbowY, "#3B82F6", guide.compact ? 12 : 18)
                guide.line(ctx, elbowX, elbowY, handX, handY, "#F59E42", guide.compact ? 11 : 17)
                guide.circle(ctx, baseX, baseY, guide.compact ? 10 : 14, "#172033")
                guide.circle(ctx, elbowX, elbowY, guide.compact ? 9 : 13, "#172033")
                ctx.fillStyle = "#FFFFFF"
                ctx.font = "bold " + (guide.compact ? 11 : 15) + "px 'Noto Sans KR'"
                ctx.textAlign = "center"; ctx.textBaseline = "middle"
                ctx.fillText("1", baseX, baseY); ctx.fillText("2", elbowX, elbowY)
                guide.dashedLink(ctx, handX, handY, goalX, goalY)
                guide.circle(ctx, handX, handY, guide.compact ? 6 : 8, "#22D3EE")
                guide.diamond(ctx, goalX, goalY, guide.compact ? 7 : 10, "#C084FC")
                return
            }

            var pandaBaseX = width * 0.22
            var pandaBaseY = floorY
            var pandaPoints = [
                [pandaBaseX, pandaBaseY],
                [width * 0.27, floorY - (guide.compact ? 35 : 58)],
                [width * 0.39, top + (floorY - top) * 0.15],
                [width * 0.50, top + (floorY - top) * 0.48],
                [width * 0.59, top + (floorY - top) * 0.35]
            ]
            for (var segment = 0; segment < pandaPoints.length - 1; ++segment) {
                var start = pandaPoints[segment]
                var end = pandaPoints[segment + 1]
                guide.line(ctx, start[0], start[1], end[0], end[1], "#475569", guide.compact ? 16 : 23)
                guide.line(ctx, start[0], start[1], end[0], end[1], "#F1F5F9", guide.compact ? 11 : 17)
                guide.circle(ctx, start[0], start[1], guide.compact ? 6 : 9, "#64748B")
            }
            var pandaHandX = guide.currentMarkerX
            var pandaHandY = guide.currentMarkerY
            var pandaGoalX = guide.targetMarkerX
            var pandaGoalY = guide.targetMarkerY
            guide.dashedLink(ctx, pandaHandX, pandaHandY, pandaGoalX, pandaGoalY)
            guide.circle(ctx, pandaHandX, pandaHandY, guide.compact ? 6 : 9, "#22D3EE")
            guide.diamond(ctx, pandaGoalX, pandaGoalY, guide.compact ? 7 : 10, "#C084FC")

            if (guide.isWall) {
                var wallX = width * 0.72
                ctx.strokeStyle = "#FBBF24"
                ctx.lineWidth = guide.compact ? 2 : 3
                for (var wallLine = 0; wallLine < 6; ++wallLine) {
                    var wallGridX = wallX + wallLine * (guide.compact ? 8 : 13)
                    guide.line(ctx, wallGridX, top, wallGridX, floorY, "#FBBF24", guide.compact ? 2 : 3)
                }
                for (var row = 0; row < 4; ++row) {
                    var rowY = top + (floorY - top) * row / 3
                    guide.line(ctx, wallX, rowY, wallX + (guide.compact ? 40 : 65), rowY, "#FBBF24", 2)
                }
                if (Math.abs(guide.appliedForce) > 0.05) {
                    guide.line(ctx, pandaHandX, pandaHandY - 12, pandaHandX - 42,
                               pandaHandY - 12, "#FB7185", guide.compact ? 5 : 7)
                }
            }
        }
    }

    component SceneLabel: Rectangle {
        required property string labelText
        required property color accent
        property bool emphasized: false
        height: guide.compact ? 20 : 26 * guide.labelScale
        width: sceneText.implicitWidth + (guide.compact ? 12 : 18 * guide.labelScale)
        radius: height / 2
        color: "#ED111827"
        border.color: accent
        border.width: emphasized && !guide.compact ? 3 : 1
        Accessible.role: Accessible.StaticText
        Accessible.name: labelText
        Label {
            id: sceneText
            anchors.centerIn: parent
            text: parent.labelText
            color: parent.accent
            font.pixelSize: guide.compact ? 10 : Math.round(12 * guide.labelScale)
            font.bold: true
            Accessible.ignored: true
        }
    }

    SceneLabel {
        visible: guide.isTwoLink
        labelText: backend.localizedText(backend.language, "scene.joints")
        accent: "#E2E8F0"
        x: guide.compact ? 20 : guide.width * 0.45 - width / 2
        y: guide.compact ? 54
                         : guide.sceneTop + (guide.floorLineY - guide.sceneTop) * 0.30
                           - height - 14
    }
    SceneLabel {
        visible: guide.isTwoLink
        labelText: backend.localizedText(backend.language, "legend.workspace")
        accent: "#8BB8F4"
        x: guide.compact ? guide.width * 0.50 : guide.width * 0.28
        y: guide.compact ? guide.height - 58 : guide.sceneTop + 10
    }
    SceneLabel {
        visible: guide.isPanda
        labelText: backend.localizedText(backend.language, "scene.panda_arm")
        accent: "#E2E8F0"
        x: guide.compact ? 20 : guide.width * 0.22 - width / 2
        y: guide.compact ? 54 : guide.floorLineY + 14
    }
    SceneLabel {
        visible: guide.isPanda && guide.isWall
        labelText: backend.localizedText(backend.language, "legend.wall")
        accent: "#FBBF24"
        x: Math.min(guide.width - width - 8, guide.width * 0.70)
        y: guide.compact ? guide.height - 58 : guide.floorLineY - height + 4
    }
    SceneLabel {
        visible: !guide.compact && (guide.isTwoLink || guide.isPanda)
        labelText: backend.localizedText(backend.language, "scene.current_hand")
        accent: "#22D3EE"
        emphasized: true
        x: Math.min(guide.width - width - 8, guide.currentMarkerX + 14)
        y: Math.min(guide.floorLineY - height - 8, guide.currentMarkerY + 12)
    }
    SceneLabel {
        visible: !guide.compact && (guide.isTwoLink || guide.isPanda)
        labelText: backend.localizedText(backend.language, "scene.target_hand")
        accent: "#C084FC"
        emphasized: true
        x: guide.isWall ? Math.max(8, guide.targetMarkerX - width - 14)
                        : Math.min(guide.width - width - 8, guide.targetMarkerX + 14)
        y: Math.max(guide.sceneTop + 4, guide.targetMarkerY - height - 12)
    }
}

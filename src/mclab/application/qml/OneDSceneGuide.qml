import QtQuick
import QtQuick.Controls

Item {
    id: guide
    property bool compact: false
    property bool isOneDimensional: backend.selectedScenario.lab === "lab01"
                                      || backend.selectedScenario.lab === "lab02"
    property real position: Number(backend.telemetry.position || 0)
    property real force: Number(backend.telemetry.force || 0)
    property real sceneScale: compact ? 1.0
                                      : Math.max(1.0, Math.min(
                                                     1.6,
                                                     Math.min(width / 1000.0,
                                                              height / 520.0)))
    property real floorLineY: Math.min(
                                  height - (compact ? 38 : 54 * sceneScale),
                                  height * 0.72)
    property real massMidY: floorLineY - (compact ? 29 : 40 * sceneScale)
    property real massWidth: compact ? 56 : 82 * sceneScale
    property real massHeight: compact ? 42 : 58 * sceneScale
    property real plantLeft: compact ? 22 : 42 * sceneScale
    property real anchorX: plantLeft + (compact ? 12 : 18 * sceneScale)
    property real boundedPosition: Math.max(-0.75, Math.min(0.75, position))
    property real massCenterX: width * 0.57
                               + boundedPosition * width * (compact ? 0.17 : 0.14)
    property real massLeft: massCenterX - massWidth / 2
    visible: isOneDimensional

    onPositionChanged: schematic.requestPaint()
    onForceChanged: schematic.requestPaint()
    onWidthChanged: schematic.requestPaint()
    onHeightChanged: schematic.requestPaint()

    Canvas {
        id: schematic
        anchors.fill: parent
        visible: backend.safeMode
        Accessible.ignored: true

        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            var sceneScale = guide.sceneScale
            var floorY = guide.floorLineY
            var midY = guide.massMidY
            var left = guide.plantLeft
            var anchorX = guide.anchorX
            var blockCenter = guide.massCenterX
            var blockWidth = guide.massWidth
            var blockHeight = guide.massHeight
            var blockLeft = blockCenter - blockWidth / 2
            var springEnd = blockLeft - 3
            var equilibriumX = width * 0.72

            ctx.fillStyle = "#D7DEE8"
            ctx.fillRect(0, floorY, width, height - floorY)
            ctx.strokeStyle = "#94A3B8"
            ctx.lineWidth = 2
            ctx.beginPath(); ctx.moveTo(8, floorY); ctx.lineTo(width - 8, floorY); ctx.stroke()
            ctx.strokeStyle = "#64748B"
            ctx.lineWidth = guide.compact ? 2 : 3 * sceneScale
            ctx.beginPath(); ctx.moveTo(left, midY + blockHeight / 2 + 5)
            ctx.lineTo(width - left, midY + blockHeight / 2 + 5); ctx.stroke()

            ctx.fillStyle = "#475569"
            ctx.fillRect(anchorX - (guide.compact ? 8 : 8 * sceneScale),
                         midY - blockHeight * 0.72,
                         guide.compact ? 12 : 12 * sceneScale,
                         blockHeight * 1.46)
            ctx.strokeStyle = "#FBBF24"
            ctx.lineWidth = guide.compact ? 3 : 4 * sceneScale
            var springOffsetY = guide.compact ? 7 : 7 * sceneScale
            var springAmplitude = guide.compact ? 10 : 10 * sceneScale
            ctx.beginPath(); ctx.moveTo(anchorX + 4 * sceneScale, midY - springOffsetY)
            var coils = guide.compact ? 9 : Math.round(12 * Math.sqrt(sceneScale))
            for (var index = 1; index <= coils; ++index) {
                var springX = anchorX + 4 * sceneScale
                              + (springEnd - anchorX - 4 * sceneScale) * index / coils
                var springY = midY - springOffsetY
                              + (index % 2 ? -springAmplitude : springAmplitude)
                ctx.lineTo(springX, springY)
            }
            ctx.lineTo(springEnd, midY - springOffsetY); ctx.stroke()

            var damperY = midY + (guide.compact ? 17 : 17 * sceneScale)
            var damperBodyEnd = anchorX + (springEnd - anchorX) * 0.58
            ctx.strokeStyle = "#CBD5E1"
            ctx.lineWidth = guide.compact ? 8 : 11 * sceneScale
            ctx.beginPath(); ctx.moveTo(anchorX + 4 * sceneScale, damperY)
            ctx.lineTo(damperBodyEnd, damperY); ctx.stroke()
            ctx.strokeStyle = "#64748B"
            ctx.lineWidth = guide.compact ? 2 : 3 * sceneScale
            ctx.strokeRect(anchorX + 4 * sceneScale,
                           damperY - (guide.compact ? 7 : 9 * sceneScale),
                           damperBodyEnd - anchorX - 4 * sceneScale,
                           guide.compact ? 14 : 18 * sceneScale)
            ctx.strokeStyle = "#F8FAFC"
            ctx.lineWidth = guide.compact ? 4 : 5 * sceneScale
            ctx.beginPath(); ctx.moveTo(damperBodyEnd, damperY)
            ctx.lineTo(springEnd, damperY); ctx.stroke()

            ctx.fillStyle = "#22D3EE"
            ctx.fillRect(blockLeft, midY - blockHeight / 2, blockWidth, blockHeight)
            ctx.strokeStyle = "#0E7490"
            ctx.lineWidth = guide.compact ? 2 : 2 * sceneScale
            ctx.strokeRect(blockLeft, midY - blockHeight / 2, blockWidth, blockHeight)

            ctx.strokeStyle = "#C084FC"
            ctx.lineWidth = guide.compact ? 3 : 3 * sceneScale
            ctx.setLineDash([6 * sceneScale, 5 * sceneScale])
            ctx.beginPath(); ctx.moveTo(equilibriumX, midY - blockHeight * 0.8)
            ctx.lineTo(equilibriumX, floorY + 2); ctx.stroke()
            ctx.setLineDash([])
            ctx.save(); ctx.translate(equilibriumX, midY); ctx.rotate(Math.PI / 4)
            var targetRadius = guide.compact ? 7 : 7 * sceneScale
            ctx.strokeRect(-targetRadius, -targetRadius,
                           targetRadius * 2, targetRadius * 2); ctx.restore()

            ctx.fillStyle = "#22D3EE"
            ctx.beginPath(); ctx.arc(
                blockCenter,
                midY - blockHeight / 2 - (guide.compact ? 7 : 7 * sceneScale),
                guide.compact ? 5 : 5 * sceneScale,
                0,
                Math.PI * 2
            )
            ctx.fill()

            if (Math.abs(guide.force) > 0.05) {
                var direction = guide.force > 0 ? 1 : -1
                var startX = blockCenter + direction * blockWidth * 0.35
                var endX = startX + direction * Math.min(
                    width * 0.18,
                    (35 + Math.abs(guide.force) * 0.35) * sceneScale
                )
                var arrowY = midY - blockHeight * 0.72
                ctx.strokeStyle = "#FB7185"; ctx.fillStyle = "#FB7185"
                ctx.lineWidth = guide.compact ? 5 : 5 * sceneScale
                ctx.beginPath(); ctx.moveTo(startX, arrowY); ctx.lineTo(endX, arrowY); ctx.stroke()
                var arrowHeadX = guide.compact ? 12 : 12 * sceneScale
                var arrowHeadY = guide.compact ? 7 : 7 * sceneScale
                ctx.beginPath(); ctx.moveTo(endX, arrowY)
                ctx.lineTo(endX - direction * arrowHeadX, arrowY - arrowHeadY)
                ctx.lineTo(endX - direction * arrowHeadX, arrowY + arrowHeadY)
                ctx.closePath(); ctx.fill()
            }

            ctx.strokeStyle = "#64748B"; ctx.lineWidth = 2
            for (var tick = 0; tick < 5; ++tick) {
                var tickX = left + (width - left * 2) * tick / 4
                ctx.beginPath(); ctx.moveTo(tickX, floorY); ctx.lineTo(tickX, floorY + 6); ctx.stroke()
            }
        }
    }

    component SceneLabel: Rectangle {
        required property string labelText
        required property color accent
        height: guide.compact ? 20 : 26 * guide.sceneScale
        width: sceneText.implicitWidth + (guide.compact ? 12 : 18 * guide.sceneScale)
        radius: height / 2
        color: "#ED111827"
        border.color: accent
        border.width: 1
        Accessible.role: Accessible.StaticText
        Accessible.name: labelText
        Label {
            id: sceneText
            anchors.centerIn: parent
            text: parent.labelText
            color: parent.accent
            font.pixelSize: guide.compact ? 10 : Math.round(12 * guide.sceneScale)
            font.bold: true
            Accessible.ignored: true
        }
    }

    SceneLabel {
        labelText: backend.localizedText(backend.language, "scene.spring")
        accent: "#FBBF24"
        x: guide.compact ? 20 : guide.anchorX + 8 * guide.sceneScale
        y: guide.compact ? 54
                         : guide.massMidY - guide.massHeight / 2 - height
                           - 14 * guide.sceneScale
    }
    SceneLabel {
        labelText: backend.localizedText(backend.language, "scene.damper")
        accent: "#E2E8F0"
        x: guide.compact ? 76
                         : guide.anchorX + (guide.massLeft - guide.anchorX) * 0.32
                           - width / 2
        y: guide.compact ? guide.height - 58
                         : guide.floorLineY + 16 * guide.sceneScale
    }
    SceneLabel {
        labelText: backend.localizedText(backend.language, "scene.mass_block")
        accent: "#22D3EE"
        x: guide.massCenterX - width / 2
        y: guide.compact ? 54
                         : guide.massMidY - guide.massHeight / 2 - height
                           - 14 * guide.sceneScale
    }
    SceneLabel {
        labelText: backend.localizedText(backend.language, "scene.equilibrium")
        accent: "#D8A7FF"
        x: Math.min(guide.width - width - 8, guide.width * 0.72 + 8)
        y: guide.compact ? guide.height - 58
                         : guide.floorLineY + 16 * guide.sceneScale
    }
}

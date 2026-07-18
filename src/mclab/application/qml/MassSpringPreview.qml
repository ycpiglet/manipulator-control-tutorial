import QtQuick
import QtQuick.Controls

Rectangle {
    id: preview
    implicitWidth: 228
    implicitHeight: 116
    radius: 12
    color: "#111827"
    border.color: "#334155"
    Accessible.name: backend.language === "ko" ? "질량 스프링 감쇠 실험 미리보기" : "Mass spring damper experiment preview"

    Canvas {
        id: drawing
        anchors.fill: parent
        anchors.margins: 10
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            var mid = height * 0.55
            ctx.lineWidth = 3
            ctx.strokeStyle = "#64748B"
            ctx.beginPath(); ctx.moveTo(8, mid + 26); ctx.lineTo(width - 8, mid + 26); ctx.stroke()
            ctx.fillStyle = "#FBBF24"
            ctx.fillRect(8, mid - 36, 9, 70)
            ctx.strokeStyle = "#FBBF24"
            ctx.lineWidth = 3
            ctx.beginPath(); ctx.moveTo(17, mid)
            var end = width * 0.60
            for (var i = 1; i <= 10; ++i) {
                var x = 17 + (end - 17) * i / 10
                var y = mid + (i % 2 ? -12 : 12)
                ctx.lineTo(x, y)
            }
            ctx.lineTo(end, mid); ctx.stroke()
            ctx.fillStyle = "#22D3EE"
            ctx.fillRect(end, mid - 27, 56, 54)
            ctx.fillStyle = "#C084FC"
            ctx.save(); ctx.translate(width * 0.82, mid); ctx.rotate(Math.PI / 4)
            ctx.fillRect(-8, -8, 16, 16); ctx.restore()
            ctx.strokeStyle = "#FB7185"
            ctx.lineWidth = 5
            ctx.beginPath(); ctx.moveTo(end + 62, mid - 34); ctx.lineTo(width - 15, mid - 34); ctx.stroke()
            ctx.fillStyle = "#FB7185"
            ctx.beginPath(); ctx.moveTo(width - 8, mid - 34); ctx.lineTo(width - 20, mid - 42); ctx.lineTo(width - 20, mid - 26); ctx.closePath(); ctx.fill()
        }
    }
    Label {
        anchors.left: parent.left; anchors.top: parent.top; anchors.margins: 10
        text: backend.language === "ko" ? "힘을 주면 모양도 움직입니다" : "The scene moves with the force"
        color: "#FFFFFF"
        font.pixelSize: 13
        font.bold: true
    }
}

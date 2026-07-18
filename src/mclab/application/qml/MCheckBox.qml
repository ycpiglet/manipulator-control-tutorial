import QtQuick
import QtQuick.Controls

CheckBox {
    id: control
    implicitHeight: 44
    implicitWidth: Math.max(44, contentItem.implicitWidth + rightPadding)
    spacing: 10
    rightPadding: 4
    focusPolicy: Qt.StrongFocus
    font.pixelSize: 15
    Accessible.name: text
    Accessible.role: Accessible.CheckBox

    indicator: Rectangle {
        implicitWidth: 28
        implicitHeight: 28
        x: control.leftPadding
        y: Math.round((control.height - height) / 2)
        radius: 4
        color: control.checked ? "#2563EB" : "#FFFFFF"
        border.width: 2
        border.color: control.enabled ? "#64748B" : "#94A3B8"
        Text {
            anchors.centerIn: parent
            visible: control.checked
            text: "✓"
            color: "#FFFFFF"
            font.pixelSize: 20
            font.bold: true
            Accessible.ignored: true
        }
    }

    contentItem: Text {
        leftPadding: control.indicator.width + control.spacing
        text: control.text
        color: control.enabled ? "#172033" : "#64748B"
        font: control.font
        verticalAlignment: Text.AlignVCenter
        wrapMode: Text.NoWrap
        Accessible.ignored: true
    }

    FocusRing { anchors.fill: parent; shown: control.activeFocus }
}

import QtQuick
import QtQuick.Controls

Button {
    id: control
    property bool secondary: false
    property bool danger: false
    property bool wrapText: false
    property real minimumButtonWidth: 124
    property string accessibleName: text
    property string accessibleDescription: ""
    implicitHeight: 48
    implicitWidth: Math.max(minimumButtonWidth, buttonMetrics.advanceWidth(text) + 36)
    focusPolicy: Qt.StrongFocus
    font.pixelSize: 16
    font.weight: Font.Bold
    Accessible.name: accessibleName
    Accessible.description: accessibleDescription
    Accessible.role: Accessible.Button
    Keys.onReturnPressed: event => {
        if (control.enabled)
            control.clicked()
        event.accepted = true
    }
    Keys.onEnterPressed: event => {
        if (control.enabled)
            control.clicked()
        event.accepted = true
    }

    FontMetrics { id: buttonMetrics; font: control.font }

    background: Rectangle {
        radius: 8
        color: !control.enabled ? "#E2E8F0"
             : control.danger ? (control.down ? "#7A271A" : control.hovered ? "#912018" : "#B42318")
             : control.secondary ? (control.down ? "#D6E4FF" : control.hovered ? "#EAF1FF" : "#FFFFFF")
             : control.down ? "#1E40AF" : control.hovered ? "#1D4ED8" : "#2563EB"
        border.width: control.activeFocus ? 4 : !control.enabled ? 2 : control.secondary ? 2 : 0
        border.color: control.activeFocus ? "#FFDD00" : !control.enabled ? "#64748B"
                     : control.secondary ? "#64748B" : "transparent"
        Rectangle {
            anchors.fill: parent
            anchors.margins: control.activeFocus ? 2 : 0
            radius: 6
            color: "transparent"
            border.width: control.activeFocus ? 2 : 0
            border.color: "#000000"
        }
    }
    contentItem: Text {
        text: control.text
        color: !control.enabled ? "#475569"
             : control.secondary && !control.danger ? "#1D4ED8" : "#FFFFFF"
        font: control.font
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        wrapMode: control.wrapText ? Text.WordWrap : Text.NoWrap
        elide: Text.ElideNone
    }
}

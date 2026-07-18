import QtQuick
import QtQuick.Controls

ComboBox {
    id: control
    objectName: "playbackSpeedSelector"
    property var speedValues: [0.25, 0.5, 1.0, 2.0]
    model: ["0.25×", "0.5×", "1×", "2×"]
    currentIndex: Math.max(0, speedValues.indexOf(Number(backend.telemetry.playback_speed || 1.0)))
    implicitWidth: 92
    implicitHeight: 48
    leftPadding: 12
    rightPadding: 28
    font.pixelSize: 15
    font.weight: Font.Bold
    focusPolicy: Qt.StrongFocus
    Accessible.name: backend.language === "ko" ? "재생 속도" : "Playback speed"
    Accessible.description: backend.language === "ko"
                            ? "현재 " + displayText + ". 위/아래 화살표로 0.25배, 0.5배, 1배, 2배 중에서 선택합니다."
                            : "Current " + displayText + ". Use Up/Down arrows to choose 0.25, 0.5, 1, or 2 times speed."
    onActivated: backend.setSpeed(speedValues[currentIndex])

    contentItem: Text {
        text: control.displayText
        color: "#172033"
        font: control.font
        verticalAlignment: Text.AlignVCenter
    }
    indicator: Text {
        anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter
        text: "▼"; color: "#172033"; font.pixelSize: 11; font.bold: true
    }
    background: Rectangle {
        radius: 8
        color: control.down ? "#EAF1FF" : "#FFFFFF"
        border.width: control.activeFocus ? 4 : 2
        border.color: control.activeFocus ? "#FFDD00" : "#64748B"
        Rectangle {
            anchors.fill: parent; anchors.margins: 3
            radius: 5; color: "transparent"
            border.width: control.activeFocus ? 2 : 0
            border.color: "#000000"
        }
    }
    delegate: ItemDelegate {
        width: control.width; height: 44
        text: modelData
        font: control.font
        highlighted: control.highlightedIndex === index
        contentItem: Text { text: parent.text; color: "#172033"; font: parent.font; verticalAlignment: Text.AlignVCenter }
        background: Rectangle { color: parent.highlighted ? "#DBEAFE" : "#FFFFFF" }
    }
    popup: Popup {
        y: control.height + 4; width: control.width
        implicitHeight: contentItem.implicitHeight + 8; padding: 4
        contentItem: ListView {
            clip: true; implicitHeight: contentHeight
            model: control.popup.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
        }
        background: Rectangle { color: "#FFFFFF"; radius: 8; border.color: "#64748B"; border.width: 2 }
    }
}

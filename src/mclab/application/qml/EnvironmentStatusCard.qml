import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: card
    property bool compact: width < 820

    Layout.fillWidth: true
    Layout.preferredHeight: content.implicitHeight + (compact ? 20 : 32)
    radius: 12
    color: backend.setupStatus.ready ? "#F0FDF4" : "#FFF7E6"
    border.color: backend.setupStatus.ready ? "#86C9A9" : "#E7B34A"
    border.width: 1

    RowLayout {
        id: content
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.margins: card.compact ? 10 : 16
        spacing: 14
        Rectangle {
            width: 44
            height: 44
            radius: 22
            color: backend.setupStatus.ready ? "#16794B" : "#9A6700"
            Label {
                anchors.centerIn: parent
                text: backend.setupStatus.ready ? "✓" : "!"
                color: "#FFFFFF"
                font.pixelSize: 24
                font.bold: true
                Accessible.ignored: true
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 4
            Label {
                text: backend.localizedText(backend.language, "home.environment")
                      + " · " + backend.setupStatus.title
                color: backend.setupStatus.ready ? "#14532D" : "#704000"
                font.pixelSize: 18
                font.bold: true
                Layout.fillWidth: true
            }
            Label {
                text: backend.setupStatus.detail
                color: "#172033"
                font.pixelSize: 15
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Label {
                visible: !backend.setupStatus.ready || !card.compact
                text: backend.setupStatus.action
                color: "#475569"
                font.pixelSize: 13
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }
        MButton {
            visible: !backend.setupStatus.ready
            secondary: true
            minimumButtonWidth: 104
            text: backend.localizedText(backend.language, "setup.review")
            onClicked: backend.navigate("explore")
        }
    }
}

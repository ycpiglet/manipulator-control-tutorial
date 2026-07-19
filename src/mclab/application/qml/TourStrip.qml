import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: strip
    property bool compact: width < 820
    signal dismissRequested()

    function focusSkip() {
        skipButton.forceActiveFocus()
    }

    implicitHeight: compact ? 68 : 76
    radius: 12
    color: "#FFFFFF"
    border.color: "#CBD5E1"
    border.width: 1

    RowLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: compact ? 6 : 14
        Label {
            visible: !compact
            text: backend.language === "ko" ? "3단계 둘러보기" : "3-step tour"
            color: "#172033"
            font.pixelSize: 16
            font.bold: true
        }
        Repeater {
            model: compact
                   ? [backend.localizedText(backend.language, "tour.start_short"), backend.localizedText(backend.language, "tour.change_short"), backend.localizedText(backend.language, "tour.replay_short")]
                   : [backend.localizedText(backend.language, "tour.start"), backend.localizedText(backend.language, "tour.change"), backend.localizedText(backend.language, "tour.replay")]
            RowLayout {
                Layout.fillWidth: true
                spacing: 6
                Rectangle {
                    width: 30; height: 30; radius: 15; color: "#2563EB"
                    Label { anchors.centerIn: parent; text: index + 1; color: "#FFFFFF"; font.bold: true }
                }
                Label {
                    text: modelData
                    color: "#172033"
                    font.pixelSize: compact ? 13 : 14
                    font.bold: true
                    Layout.fillWidth: strip.compact
                    elide: Text.ElideNone
                }
                Rectangle {
                    visible: !strip.compact && index < 2
                    Layout.fillWidth: true
                    Layout.minimumWidth: 24
                    implicitHeight: 2
                    Layout.alignment: Qt.AlignVCenter
                    color: "#4F8FF7"
                }
            }
        }
        MButton {
            id: skipButton
            secondary: true
            minimumButtonWidth: compact ? 90 : 124
            text: compact ? backend.localizedText(backend.language, "tour.skip_short") : backend.localizedText(backend.language, "tour.skip")
            accessibleDescription: backend.localizedText(backend.language, "tour.skip_help")
            onClicked: strip.dismissRequested()
        }
    }
}

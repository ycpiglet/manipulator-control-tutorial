import QtQuick
import QtQuick.Controls

Rectangle {
    id: hud
    required property bool compact
    required property bool cameraFocused
    required property string legendDescription
    property string markerPrefix: backend.language === "ko" ? "장면 표시: " : "Scene markers: "
    property string fullKeyboardHelp: backend.localizedText(
                                          backend.language,
                                          "control.camera_keyboard_short")
    property string microKeyboardHelp: backend.localizedText(
                                           backend.language,
                                           "control.camera_keyboard_micro")

    width: Math.min(parent.width - 16,
                    hudContent.implicitWidth + (compact ? 14 : 24))
    height: compact ? 28 : 38
    radius: 8
    color: "#E6111827"
    Accessible.role: Accessible.StaticText
    Accessible.name: markerPrefix + legendDescription
                     + (cameraFocused ? ". " + fullKeyboardHelp : "")

    Row {
        id: hudContent
        anchors.centerIn: parent
        spacing: hud.cameraFocused ? (hud.compact ? 4 : 10) : 0

        Row {
            id: legendRow
            spacing: hud.compact ? (hud.cameraFocused ? 4 : 7) : 16
            Label {
                text: "● " + backend.localizedText(backend.language, "legend.current")
                color: "#22D3EE"
                font.bold: true
                font.pixelSize: hud.compact ? 10 : 13
                Accessible.ignored: true
            }
            Label {
                text: "◆ " + backend.localizedText(backend.language, "legend.target")
                color: "#D8A7FF"
                font.bold: true
                font.pixelSize: hud.compact ? 10 : 13
                Accessible.ignored: true
            }
            Label {
                visible: backend.selectedScenario.showWorkspace || false
                text: "◯ " + backend.localizedText(backend.language, "legend.workspace")
                color: "#8BB8F4"
                font.bold: true
                font.pixelSize: hud.compact ? 10 : 13
                Accessible.ignored: true
            }
            Label {
                visible: backend.selectedScenario.showSingularity || false
                text: "◎ " + backend.localizedText(backend.language, "legend.singularity")
                color: "#FF8FA3"
                font.bold: true
                font.pixelSize: hud.compact ? 10 : 13
                Accessible.ignored: true
            }
            Label {
                visible: backend.selectedScenario.showForce || false
                text: "➜ " + backend.localizedText(backend.language, "legend.force")
                color: "#FF8FA3"
                font.bold: true
                font.pixelSize: hud.compact ? 10 : 13
                Accessible.ignored: true
            }
            Label {
                visible: backend.selectedScenario.showWall || false
                text: "▨ " + backend.localizedText(backend.language, "legend.wall")
                color: "#FFD56A"
                font.bold: true
                font.pixelSize: hud.compact ? 10 : 13
                Accessible.ignored: true
            }
        }
        Label {
            visible: hud.cameraFocused
            text: "·"
            color: "#CBD5E1"
            font.bold: true
            font.pixelSize: hud.compact ? 10 : 13
            Accessible.ignored: true
        }
        Label {
            id: keyboardCameraHelp
            visible: hud.cameraFocused
            text: hud.compact ? hud.microKeyboardHelp : hud.fullKeyboardHelp
            color: "#FFFFFF"
            font.bold: true
            font.pixelSize: hud.compact ? 10 : 13
            Accessible.ignored: true
        }
    }
}

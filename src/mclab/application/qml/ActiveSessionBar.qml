import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: bar
    property bool ending: backend.sessionState === "completed"
                          || backend.sessionState === "error"
    property bool pausing: backend.sessionState === "running"
                           || backend.sessionState === "replaying"
    property bool replay: backend.hasReplay

    visible: backend.hasActiveExperiment && backend.page !== "experiment"
    Layout.fillWidth: true
    Layout.preferredHeight: content.implicitHeight + 20
    radius: 12
    color: ending ? "#FFF7E6" : "#EAF1FF"
    border.width: 1
    border.color: ending ? "#E7B34A" : "#93B4F4"

    RowLayout {
        id: content
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.margins: 10
        spacing: 10

        Rectangle {
            width: 44
            height: 44
            radius: 22
            color: bar.ending ? "#9A6700" : "#2563EB"
            Label {
                anchors.centerIn: parent
                text: bar.ending ? "…" : "Ⅱ"
                color: "#FFFFFF"
                font.pixelSize: 19
                font.bold: true
                Accessible.ignored: true
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            Label {
                Layout.fillWidth: true
                text: bar.ending
                      ? backend.localizedText(backend.language, "active.saving_title")
                      : bar.pausing
                        ? backend.localizedText(backend.language, "active.pausing_title")
                        : bar.replay
                          ? backend.localizedText(backend.language, "active.replay_paused_title")
                          : backend.localizedText(backend.language, "active.paused_title")
                color: bar.ending ? "#704000" : "#173E77"
                font.pixelSize: 16
                font.bold: true
                wrapMode: Text.WordWrap
            }
            Label {
                Layout.fillWidth: true
                text: (bar.ending
                       ? backend.localizedText(backend.language, "active.saving_detail")
                       : bar.replay
                         ? backend.localizedText(backend.language, "active.replay_paused_detail")
                         : backend.localizedText(backend.language, "active.paused_detail"))
                      + " · " + (backend.selectedScenario.displayTitle
                                 || backend.selectedScenario.title || "MCLab")
                color: bar.ending ? "#704000" : "#334155"
                font.pixelSize: 13
                maximumLineCount: 2
                elide: Text.ElideRight
                wrapMode: Text.WordWrap
            }
        }
        MButton {
            visible: !bar.ending
            minimumButtonWidth: 142
            text: bar.replay
                  ? backend.localizedText(backend.language, "active.return_replay")
                  : backend.localizedText(backend.language, "active.return")
            accessibleDescription: backend.localizedText(
                                       backend.language, "active.return_help")
            onClicked: backend.returnToActiveExperiment()
        }
        MButton {
            visible: !bar.ending
            secondary: true
            minimumButtonWidth: 112
            text: bar.replay
                  ? backend.localizedText(backend.language, "active.close_replay")
                  : backend.localizedText(backend.language, "active.stop")
            accessibleDescription: bar.replay
                                   ? backend.localizedText(
                                         backend.language, "active.close_replay_help")
                                   : backend.localizedText(
                                         backend.language, "active.stop_help")
            onClicked: backend.stopActiveExperiment()
        }
    }
}

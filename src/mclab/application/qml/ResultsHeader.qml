import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

RowLayout {
    id: header
    property int runCount: 0
    property bool batchRunning: false
    property string nextScenarioId: ""
    spacing: 10
    Label {
        text: backend.localizedText(backend.language, "nav.results")
        color: "#172033"
        font.pixelSize: 30
        font.bold: true
        Layout.fillWidth: true
    }
    MButton {
        visible: header.runCount > 0
        text: backend.localizedText(backend.language, "path.start_next")
        accessibleDescription: header.batchRunning
                               ? backend.localizedText(backend.language, "batch.launch_blocked")
                               : backend.localizedText(backend.language, "results.start_help")
        enabled: header.nextScenarioId !== "" && !header.batchRunning
                 && (!backend.hasActiveExperiment
                     || backend.sessionState !== "completed")
        onClicked: backend.startScenario(header.nextScenarioId)
    }
}

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: card
    property var scenario
    property bool launchBlocked: false
    property bool inlineAction: width >= 560
    property string launchBlockedDescription: backend.localizedText(
                                                  backend.language,
                                                  "active.launch_blocked")
    signal startRequested(string scenarioId)
    signal focusRevealRequested(var control)
    implicitHeight: inlineAction ? 128 : 154
    radius: 12
    color: scenario.ready === false ? "#FFF7E6" : "#FFFFFF"
    border.color: scenario.ready === false ? "#E7B34A" : "#DCE2EC"
    border.width: 1

    GridLayout {
        anchors.fill: parent
        anchors.margins: 16
        columns: card.inlineAction ? 2 : 1
        columnSpacing: 12
        rowSpacing: 8
        RowLayout {
            Layout.fillWidth: true
            Layout.columnSpan: card.inlineAction ? 2 : 1
            Label {
                text: (scenario.step ? scenario.step + ". " : "")
                      + (scenario.displayTitle || scenario.title || "")
                color: "#172033"
                font.pixelSize: 18
                font.bold: true
                Layout.fillWidth: true
                elide: Text.ElideRight
            }
            Label {
                text: (scenario.completed ? backend.localizedText(backend.language, "path.completed") + " · " : scenario.isNext ? backend.localizedText(backend.language, "path.next") + " · " : "") + (scenario.difficulty || "") + " · " + (scenario.minutes || 0) + " " + backend.localizedText(backend.language, "scenario.minutes")
                color: "#475569"
                font.pixelSize: 14
            }
        }
        Label {
            text: scenario.ready === false
                  ? backend.localizedText(backend.language, "setup.attention") + " · " + scenario.readinessDetail
                  : (scenario.purpose || "")
            color: scenario.ready === false ? "#704000" : "#475569"
            font.pixelSize: 15
            wrapMode: Text.WordWrap
            maximumLineCount: 2
            elide: Text.ElideRight
            Layout.fillWidth: true
            Layout.fillHeight: true
            verticalAlignment: Text.AlignVCenter
        }
        MButton {
            text: backend.localizedText(backend.language, "scenario.start")
            accessibleName: text + ": " + (scenario.displayTitle || scenario.title || "")
            accessibleDescription: scenario.ready === false
                                   ? scenario.readinessDetail + " " + scenario.readinessAction
                                   : card.launchBlocked
                                     ? card.launchBlockedDescription
                                     : (scenario.purpose || "")
            enabled: scenario.ready !== false && !card.launchBlocked
            Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
            onClicked: card.startRequested(scenario.id)
            onActiveFocusChanged: {
                if (activeFocus)
                    card.focusRevealRequested(card)
            }
        }
    }
}

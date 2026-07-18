import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: workflow
    property bool compact: false
    property string compactActionPrompt: ""
    property string workflowPrompt: ""
    property bool liveEditable: false
    property bool needsEvidenceRetry: backend.sessionState === "completed"
                                      && !backend.hasReplay
                                      && backend.selectedScenario.requiresEvidence
                                      && !backend.hasObservation
    property string predictionPrompt: backend.selectedScenario.predictionPrompt
                                      || backend.localizedText(backend.language, "evidence.prediction_placeholder")
    signal revealRequested(var control)
    signal predictionCommitted()
    signal observationCommitted()
    function focusPrediction() {
        if (predictionEditor.visible && predictionEditor.enabled)
            predictionEditor.forceInputFocus()
    }

    Layout.fillWidth: true
    Layout.preferredHeight: content.implicitHeight + (compact ? 14 : 16)
    radius: 10
    color: backend.hasObservation ? "#ECFDF5"
         : backend.hasLearnerAction ? "#FFF7ED" : "#EFF6FF"
    border.width: 1
    border.color: backend.hasObservation ? "#6EE7B7"
                : backend.hasLearnerAction ? "#FDBA74" : "#93C5FD"
    Accessible.role: Accessible.StaticText
    Accessible.name: workflow.workflowPrompt
    Accessible.ignored: !compact || backend.hasPrediction

    ColumnLayout {
        id: content
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: compact ? 7 : 8
        spacing: compact ? 4 : 6

        Label {
            text: workflow.needsEvidenceRetry
                  ? backend.localizedText(backend.language, "evidence.restart_first")
                  : !backend.hasPrediction
                  ? backend.localizedText(backend.language, "evidence.predict_title")
                  : !backend.hasLearnerAction
                    ? backend.localizedText(backend.language, "evidence.control_title")
                    : !backend.hasObservation
                      ? backend.localizedText(backend.language, "evidence.observe_title")
                      : backend.localizedText(backend.language, "evidence.saved")
            color: backend.hasObservation ? "#166534" : "#172033"
            font.pixelSize: compact ? 13 : 15
            font.bold: true
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        Label {
            visible: !compact && !backend.hasPrediction
            text: workflow.predictionPrompt
            color: "#334155"
            font.pixelSize: compact ? 11 : 12
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
        EvidenceTextArea {
            id: predictionEditor
            visible: !backend.hasPrediction
            Layout.preferredHeight: 52
            compact: workflow.compact
            editable: workflow.liveEditable
            maximumLength: 240
            inputObjectName: "predictionInput"
            scrollerObjectName: "predictionScroller"
            scrollBarObjectName: "predictionVerticalScrollBar"
            placeholder: workflow.predictionPrompt
            accessibleName: backend.localizedText(backend.language, "experiment.predict")
            accessibleDescription: workflow.predictionPrompt + " "
                                   + backend.localizedText(backend.language, "evidence.predict_hint")
            tabTarget: savePredictionButton
            onRevealRequested: controlItem => workflow.revealRequested(controlItem)
        }
        MButton {
            id: savePredictionButton
            objectName: "savePredictionButton"
            visible: !backend.hasPrediction
            enabled: workflow.liveEditable && predictionEditor.text.trim().length >= 3
            minimumButtonWidth: 92
            text: backend.localizedText(backend.language, "evidence.save_prediction")
            Layout.fillWidth: true
            onClicked: {
                backend.savePrediction(predictionEditor.text)
                workflow.predictionCommitted()
            }
            onActiveFocusChanged: {
                if (activeFocus)
                    workflow.revealRequested(savePredictionButton)
            }
        }
        Label {
            visible: !compact && backend.hasPrediction && !backend.hasLearnerAction
                     && !backend.hasObservation
                     && !workflow.needsEvidenceRetry
            text: backend.localizedText(backend.language, "evidence.prediction_saved")
                  + " · " + backend.predictionText
            color: "#1E3A5F"
            font.pixelSize: compact ? 11 : 12
            wrapMode: Text.WordWrap
            maximumLineCount: 2
            elide: Text.ElideRight
            Layout.fillWidth: true
        }
        Label {
            visible: backend.hasPrediction && !backend.hasLearnerAction
                     && !workflow.needsEvidenceRetry
            text: compact && workflow.compactActionPrompt
                  ? workflow.compactActionPrompt
                  : backend.localizedText(backend.language, "evidence.control_hint")
            color: "#334155"
            font.pixelSize: compact ? 11 : 12
            wrapMode: Text.WordWrap
            maximumLineCount: compact ? 1 : 2
            elide: Text.ElideRight
            Layout.fillWidth: true
            Accessible.name: compact && workflow.compactActionPrompt
                             ? backend.localizedText(backend.language, "experiment.now")
                               + ": " + workflow.compactActionPrompt
                             : text
        }
        EvidenceTextArea {
            id: observationEditor
            visible: backend.hasLearnerAction && !backend.hasObservation
                     && !workflow.needsEvidenceRetry
            Layout.preferredHeight: 44
            compact: workflow.compact
            editable: workflow.liveEditable
            maximumLength: 300
            inputObjectName: "observationInput"
            scrollerObjectName: "observationScroller"
            scrollBarObjectName: "observationVerticalScrollBar"
            placeholder: backend.localizedText(backend.language, "evidence.observation_placeholder")
            accessibleName: backend.localizedText(backend.language, "experiment.observe")
            accessibleDescription: backend.localizedText(backend.language, "evidence.observe_hint")
            tabTarget: outcomeSelector
            onRevealRequested: controlItem => workflow.revealRequested(controlItem)
        }
        GridLayout {
            visible: backend.hasLearnerAction && !backend.hasObservation
                     && !workflow.needsEvidenceRetry
            Layout.fillWidth: true
            columns: 2
            columnSpacing: 6
            rowSpacing: 6
            ComboBox {
                id: outcomeSelector
                objectName: "outcomeSelector"
                enabled: workflow.liveEditable
                Layout.fillWidth: true
                Layout.preferredHeight: 44
                leftPadding: 8
                rightPadding: 22
                font.pixelSize: compact ? 11 : 13
                font.weight: Font.Bold
                model: [
                    backend.localizedText(
                        backend.language,
                        compact ? "evidence.outcome_select_short" : "evidence.outcome_select"
                    ),
                    backend.localizedText(backend.language, "evidence.outcome.matched"),
                    backend.localizedText(backend.language, "evidence.outcome.partly"),
                    backend.localizedText(backend.language, "evidence.outcome.surprised")
                ]
                Accessible.name: backend.localizedText(backend.language, "evidence.outcome_label")
                Accessible.description: currentIndex === 0
                                        ? backend.localizedText(backend.language, "evidence.outcome_required")
                                        : displayText
                onActiveFocusChanged: {
                    if (activeFocus)
                        workflow.revealRequested(outcomeSelector)
                }
                contentItem: Text {
                    text: outcomeSelector.displayText
                    color: "#172033"
                    font: outcomeSelector.font
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                    Accessible.ignored: true
                }
                indicator: Text {
                    anchors.right: parent.right
                    anchors.rightMargin: 7
                    anchors.verticalCenter: parent.verticalCenter
                    text: "▼"
                    color: "#172033"
                    font.pixelSize: 9
                    font.bold: true
                    Accessible.ignored: true
                }
                background: Rectangle {
                    radius: 7
                    color: outcomeSelector.down ? "#EAF1FF" : "#FFFFFF"
                    border.width: outcomeSelector.activeFocus ? 4 : 2
                    border.color: outcomeSelector.activeFocus ? "#FFDD00" : "#64748B"
                    Rectangle {
                        anchors.fill: parent; anchors.margins: 3; radius: 4
                        color: "transparent"
                        border.width: outcomeSelector.activeFocus ? 2 : 0
                        border.color: "#000000"
                    }
                }
                delegate: ItemDelegate {
                    width: outcomeSelector.width
                    height: 44
                    text: modelData
                    highlighted: outcomeSelector.highlightedIndex === index
                    contentItem: Text {
                        text: parent.text
                        color: "#172033"
                        verticalAlignment: Text.AlignVCenter
                        Accessible.ignored: true
                    }
                    background: Rectangle {
                        color: parent.highlighted ? "#DBEAFE" : "#FFFFFF"
                    }
                }
                popup: Popup {
                    y: outcomeSelector.height + 4
                    width: Math.max(outcomeSelector.width, compact ? 150 : outcomeSelector.width)
                    implicitHeight: contentItem.implicitHeight + 8
                    padding: 4
                    contentItem: ListView {
                        clip: true
                        implicitHeight: contentHeight
                        model: outcomeSelector.popup.visible ? outcomeSelector.delegateModel : null
                        currentIndex: outcomeSelector.highlightedIndex
                    }
                    background: Rectangle {
                        color: "#FFFFFF"; radius: 8
                        border.color: "#64748B"; border.width: 2
                    }
                }
                FocusRing { anchors.fill: parent; shown: outcomeSelector.activeFocus }
            }
            MButton {
                id: saveObservationButton
                objectName: "saveObservationButton"
                enabled: workflow.liveEditable
                         && observationEditor.text.trim().length >= 3
                         && outcomeSelector.currentIndex > 0
                minimumButtonWidth: compact ? 80 : 92
                text: backend.localizedText(
                    backend.language,
                    compact ? "evidence.save_observation_short" : "evidence.save_observation"
                )
                accessibleName: backend.localizedText(
                    backend.language, "evidence.save_observation"
                )
                Layout.fillWidth: true
                onClicked: {
                    var outcomes = ["", "Matched", "Partly matched", "Surprised"]
                    backend.saveObservation(observationEditor.text, outcomes[outcomeSelector.currentIndex])
                    workflow.observationCommitted()
                }
                onActiveFocusChanged: {
                    if (activeFocus)
                        workflow.revealRequested(saveObservationButton)
                }
            }
        }
        Label {
            visible: backend.hasObservation
            text: backend.localizedText(backend.language, "evidence.saved_hint")
            color: "#166534"
            font.pixelSize: compact ? 11 : 12
            font.bold: true
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }
}

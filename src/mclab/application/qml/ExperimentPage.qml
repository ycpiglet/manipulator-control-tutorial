import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: page
    objectName: "experimentPage"
    property bool compact: width < 900 || height < 500
    property bool needsEvidenceRetry: backend.sessionState === "completed"
                                       && !backend.hasReplay
                                       && backend.selectedScenario.requiresEvidence
                                       && !backend.hasObservation
    property int activeStage: backend.hasReplay ? 4
                              : backend.sessionState === "completed"
                                && (!backend.selectedScenario.requiresEvidence
                                    || backend.hasObservation) ? 4
                              : !backend.selectedScenario.requiresEvidence ? 2
                              : !backend.hasPrediction ? 1
                              : !backend.hasLearnerAction ? 2
                              : !backend.hasObservation ? 3 : 4
    property bool previousPredictionWait: false
    property string previousSessionState: ""
    focus: true
    Keys.onSpacePressed: backend.togglePause()
    Keys.onRightPressed: backend.stepOnce()
    function focusExperiment() {
        if (!visible)
            return
        if (backend.waitingForPrediction)
            controls.focusEvidence()
        else if (!backend.hasReplay && backend.selectedScenario.startsPaused
                 && backend.sessionState === "paused"
                 && Number(backend.telemetry.time || 0) <= 0.0001)
            controls.focusFirstExperimentControl()
        else
            transport.focusPrimary()
    }
    function focusSavedResults() {
        if (savedResultsButton.visible && savedResultsButton.enabled)
            savedResultsButton.forceActiveFocus()
    }
    function focusCompletedPrimary() {
        if (startNextButton.visible && startNextButton.enabled)
            startNextButton.forceActiveFocus()
        else
            focusSavedResults()
    }
    function focusAfterEvidenceSaved() {
        controls.showEvidenceComplete()
        if (backend.sessionState === "completed" && !backend.hasReplay
                && !page.needsEvidenceRetry)
            focusCompletedPrimary()
        else
            transport.focusPrimary()
    }
    Component.onCompleted: {
        previousPredictionWait = backend.waitingForPrediction
        previousSessionState = backend.sessionState
        Qt.callLater(focusExperiment)
    }
    onVisibleChanged: Qt.callLater(focusExperiment)
    Connections {
        target: backend
        function onEvidence_changed() {
            var waiting = backend.waitingForPrediction
            if (waiting !== page.previousPredictionWait) {
                page.previousPredictionWait = waiting
                if (waiting)
                    Qt.callLater(controls.focusEvidence)
                else if (backend.hasReplay)
                    Qt.callLater(transport.focusPrimary)
                else
                    Qt.callLater(controls.focusFirstExperimentControl)
            }
        }
        function onState_changed() {
            var state = backend.sessionState
            if (state !== page.previousSessionState) {
                page.previousSessionState = state
                if (backend.waitingForPrediction)
                    Qt.callLater(controls.focusEvidence)
                else if (state === "paused" && !backend.hasReplay
                        && backend.selectedScenario.startsPaused
                        && Number(backend.telemetry.time || 0) <= 0.0001)
                    Qt.callLater(controls.focusFirstExperimentControl)
                else if (state === "completed") {
                    if (page.needsEvidenceRetry)
                        Qt.callLater(transport.focusPrimary)
                    else if (!backend.hasReplay)
                        Qt.callLater(page.focusCompletedPrimary)
                }
            }
        }
    }

    function motionLabel() {
        var velocity = Number(backend.telemetry.velocity || 0)
        if (Math.abs(velocity) < 0.005) return "● " + backend.localizedText(backend.language, "motion.stationary")
        if (backend.selectedScenario.spatialMotion) return "↗ " + backend.localizedText(backend.language, "motion.moving")
        return velocity > 0 ? "→ " + backend.localizedText(backend.language, "motion.right") : "← " + backend.localizedText(backend.language, "motion.left")
    }

    function legendDescription() {
        var labels = [backend.localizedText(backend.language, "legend.current"), backend.localizedText(backend.language, "legend.target")]
        if (backend.selectedScenario.showWorkspace) labels.push(backend.localizedText(backend.language, "legend.workspace"))
        if (backend.selectedScenario.showSingularity) labels.push(backend.localizedText(backend.language, "legend.singularity"))
        if (backend.selectedScenario.showForce) labels.push(backend.localizedText(backend.language, "legend.force"))
        if (backend.selectedScenario.showWall) labels.push(backend.localizedText(backend.language, "legend.wall"))
        return labels.join(", ")
    }

    function stageKey(index) {
        return ["experiment.goal", "experiment.predict", "experiment.try", "experiment.observe", "experiment.review"][index]
    }

    function nowPrompt() {
        if (backend.hasReplay)
            return backend.localizedText(backend.language, "experiment.review") + ": "
                   + backend.localizedText(backend.language, "experiment.prompt_replay")
        if (page.needsEvidenceRetry)
            return backend.localizedText(backend.language, "experiment.now") + ": "
                   + backend.localizedText(backend.language, "evidence.restart_first")
        if (backend.sessionState === "completed" && !backend.hasReplay)
            return backend.localizedText(backend.language, "experiment.review") + ": "
                   + backend.localizedText(backend.language, "experiment.complete_hint")
        if (backend.selectedScenario.requiresEvidence && !backend.hasPrediction)
            return backend.localizedText(backend.language, "experiment.now") + ": "
                   + backend.localizedText(backend.language, "experiment.prompt_predict")
        if (backend.selectedScenario.requiresEvidence && backend.hasLearnerAction && !backend.hasObservation)
            return backend.localizedText(backend.language, "experiment.now") + ": "
                   + backend.localizedText(backend.language, "experiment.prompt_save_observation")
        if (backend.selectedScenario.requiresEvidence && backend.hasObservation)
            return backend.localizedText(backend.language, "experiment.now") + ": "
                   + backend.localizedText(backend.language, "experiment.prompt_evidence_saved")
        return backend.localizedText(backend.language, "experiment.now") + ": "
               + (backend.selectedScenario.nowPrompt || backend.selectedScenario.purpose || "")
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: compact ? 5 : 8
        RowLayout {
            visible: !compact
            Layout.fillWidth: true
            Repeater {
                model: ["experiment.goal", "experiment.predict", "experiment.try", "experiment.observe", "experiment.review"]
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 38
                    radius: 8
                    color: index === page.activeStage ? "#2563EB"
                          : index < page.activeStage ? "#DBEAFE" : "#E9EDF3"
                    Label {
                        anchors.centerIn: parent
                        text: backend.localizedText(backend.language, modelData)
                        color: index === page.activeStage ? "#FFFFFF" : "#26334D"
                        font.pixelSize: 14
                        font.bold: true
                    }
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: compact ? 42 : 48
            spacing: 8
            Rectangle {
                visible: compact
                implicitWidth: compactStage.implicitWidth + 20
                height: 32; radius: 16; color: "#DBEAFE"
                Label {
                    id: compactStage
                    anchors.centerIn: parent
                    text: (page.activeStage + 1) + "/5 · "
                          + backend.localizedText(backend.language, page.stageKey(page.activeStage))
                    color: "#1D4ED8"; font.pixelSize: 13; font.bold: true
                }
            }
            Label {
                text: (backend.selectedScenario.displayTitle
                       || backend.selectedScenario.title || "MCLab") + " · "
                      + (backend.waitingForPrediction
                         ? backend.localizedText(backend.language, "evidence.waiting_status")
                         : backend.localizedText(backend.language, "status." + backend.sessionState))
                color: "#172033"
                font.pixelSize: compact ? 17 : 22
                font.bold: true
                Layout.fillWidth: true
                elide: Text.ElideRight
            }
            MButton {
                id: startNextButton
                objectName: "startNextButton"
                visible: backend.sessionState === "completed" && !backend.hasReplay
                         && !page.needsEvidenceRetry && backend.nextScenarioId !== ""
                enabled: !backend.hasActiveExperiment
                minimumButtonWidth: compact ? 82 : 124
                text: backend.localizedText(backend.language, "path.start_next")
                accessibleDescription: enabled
                                       ? backend.localizedText(backend.language, "results.start_help")
                                       : backend.localizedText(backend.language, "active.saving_title")
                onClicked: backend.startScenario(backend.nextScenarioId)
            }
            MButton {
                id: savedResultsButton
                objectName: "savedResultsButton"
                minimumButtonWidth: compact ? 82 : 124
                secondary: !(backend.sessionState === "completed"
                             && !backend.hasReplay && !page.needsEvidenceRetry
                             && backend.nextScenarioId === "")
                text: backend.sessionState === "completed" && !backend.hasReplay
                      ? backend.localizedText(backend.language, "experiment.saved_results")
                      : "← " + backend.localizedText(backend.language, "nav.home")
                accessibleDescription: page.needsEvidenceRetry
                                       ? backend.localizedText(backend.language, "evidence.restart_first")
                                       : backend.sessionState === "completed" && !backend.hasReplay
                                         ? backend.localizedText(backend.language, "experiment.complete_hint") : ""
                onClicked: backend.navigate(backend.sessionState === "completed" && !backend.hasReplay
                                            ? "results" : "home")
            }
        }
        Label {
            visible: !compact && backend.sessionState === "completed" && !backend.hasReplay
            text: backend.localizedText(
                      backend.language,
                      page.needsEvidenceRetry ? "evidence.restart_first" : "experiment.complete_hint"
                  )
            color: "#704000"
            font.pixelSize: compact ? 12 : 14
            font.bold: true
            Layout.fillWidth: true
            elide: compact ? Text.ElideRight : Text.ElideNone
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: compact ? 6 : 12
            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: "#111827"
                radius: 12
                clip: true
                Image {
                    anchors.fill: parent
                    source: backend.frameSource
                    fillMode: page.compact ? Image.PreserveAspectCrop : Image.PreserveAspectFit
                    cache: false
                    Accessible.ignored: true
                }
                OneDSceneGuide {
                    anchors.fill: parent
                    compact: page.compact
                }
                SpatialSceneGuide {
                    anchors.fill: parent
                    compact: page.compact
                }
                MouseArea {
                    id: sceneCameraArea
                    objectName: "sceneCameraArea"
                    anchors.fill: parent
                    activeFocusOnTab: true
                    enabled: backend.hasReplay || backend.sessionState === "ready"
                             || backend.sessionState === "running"
                             || backend.sessionState === "paused"
                    acceptedButtons: Qt.LeftButton | Qt.RightButton
                    hoverEnabled: true
                    cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                    Accessible.name: backend.language === "ko"
                                     ? "MuJoCo 실험 장면" : "MuJoCo experiment scene"
                    Accessible.role: Accessible.Graphic
                    Accessible.description: (backend.selectedScenario.purpose || "")
                                            + " "
                                            + (backend.language === "ko" ? "장면 표시: " : "Scene markers: ")
                                            + page.legendDescription() + ". "
                                            + backend.localizedText(backend.language, "control.camera_help")
                    property real previousX
                    property real previousY
                    function keyboardDrag(dx, dy, event) {
                        backend.cameraDrag(dx, dy, Boolean(event.modifiers & Qt.ShiftModifier))
                        event.accepted = true
                    }
                    onPressed: mouse => {
                        forceActiveFocus()
                        previousX = mouse.x
                        previousY = mouse.y
                    }
                    onPositionChanged: mouse => {
                        if (!pressed) return
                        backend.cameraDrag(mouse.x - previousX, mouse.y - previousY, pressedButtons & Qt.RightButton)
                        previousX = mouse.x; previousY = mouse.y
                    }
                    onWheel: wheel => backend.cameraZoom(wheel.angleDelta.y)
                    Keys.onLeftPressed: event => keyboardDrag(-12, 0, event)
                    Keys.onRightPressed: event => keyboardDrag(12, 0, event)
                    Keys.onUpPressed: event => keyboardDrag(0, -12, event)
                    Keys.onDownPressed: event => keyboardDrag(0, 12, event)
                    Keys.onPressed: event => {
                        if (event.key === Qt.Key_Plus || event.key === Qt.Key_Equal) {
                            backend.cameraZoom(120)
                            event.accepted = true
                        } else if (event.key === Qt.Key_Minus || event.key === Qt.Key_Underscore) {
                            backend.cameraZoom(-120)
                            event.accepted = true
                        } else if (event.key === Qt.Key_0) {
                            backend.applyAction("reset_camera")
                            event.accepted = true
                        }
                    }
                }
                FocusRing {
                    anchors.fill: parent
                    anchors.margins: 2
                    shown: sceneCameraArea.activeFocus
                }
                Rectangle {
                    visible: !compact
                    anchors.left: parent.left; anchors.top: parent.top
                    anchors.margins: compact ? 7 : 12
                    width: parent.width - (compact ? 14 : 24)
                    height: compact ? 52 : 56
                    radius: 8; color: "#E6111827"
                    Label {
                        id: nowText
                        objectName: "nowPrompt"
                        anchors.fill: parent
                        anchors.margins: compact ? 7 : 9
                        text: page.nowPrompt()
                        color: "#FFFFFF"
                        font.pixelSize: compact ? 12 : 14
                        font.bold: true
                        wrapMode: Text.WordWrap
                        maximumLineCount: compact ? 2 : 3
                        elide: compact ? Text.ElideRight : Text.ElideNone
                        verticalAlignment: Text.AlignVCenter
                    }
                }
                Rectangle {
                    anchors.left: compact ? parent.left : undefined
                    anchors.right: compact ? undefined : parent.right
                    anchors.top: parent.top
                    anchors.leftMargin: compact ? 7 : 0
                    anchors.rightMargin: compact ? 7 : 12
                    anchors.topMargin: compact ? 7 : 72
                    width: motionText.implicitWidth + 24
                    height: compact ? 34 : 40
                    radius: 20; color: "#E6111827"
                    border.color: "#22D3EE"; border.width: 2
                    Label {
                        id: motionText
                        anchors.centerIn: parent
                        text: page.motionLabel()
                        color: "#FFFFFF"
                        font.pixelSize: compact ? 12 : 14
                        font.bold: true
                    }
                }
                SceneHud {
                    anchors.bottom: parent.bottom; anchors.horizontalCenter: parent.horizontalCenter; anchors.bottomMargin: 10
                    compact: page.compact
                    cameraFocused: sceneCameraArea.activeFocus
                    legendDescription: page.legendDescription()
                }
            }
            ExperimentControls {
                id: controls
                compact: page.compact
                scenario: backend.selectedScenario
                compactActionPrompt: backend.selectedScenario.nowPrompt || ""
                workflowPrompt: page.nowPrompt()
                Layout.preferredWidth: page.compact
                                       ? 220 : Math.min(360, Math.max(310, page.width * 0.28))
                Layout.fillHeight: true
                onEvidenceSaved: Qt.callLater(page.focusAfterEvidenceSaved)
            }
        }
        TransportBar {
            id: transport
            compact: page.compact
            Layout.fillWidth: true
            Layout.preferredHeight: implicitHeight
        }
    }
}

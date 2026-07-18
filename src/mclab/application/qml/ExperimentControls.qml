import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: panel
    signal evidenceSaved()
    property bool compact: false
    property var scenario: ({})
    property string compactActionPrompt: ""
    property string workflowPrompt: ""
    property bool liveEditable: backend.sessionState === "ready"
                                || backend.sessionState === "running"
                                || backend.sessionState === "paused"
    property bool evidenceWorkflow: !backend.hasReplay && (scenario.requiresEvidence || false)
    property bool needsEvidenceRetry: evidenceWorkflow
                                      && backend.sessionState === "completed"
                                      && !backend.hasObservation

    function revealControl(control) {
        Qt.callLater(function() {
            var flick = scroller.contentItem
            if (!flick || !control)
                return
            var point = control.mapToItem(contentColumn, 0, 0)
            var margin = 6
            var top = point.y - margin
            var bottom = point.y + control.height + margin
            var viewportHeight = scroller.availableHeight
            if (top < flick.contentY) {
                flick.contentY = Math.max(0, top)
            } else if (bottom > flick.contentY + viewportHeight) {
                var maximum = Math.max(0, flick.contentHeight - viewportHeight)
                flick.contentY = Math.min(maximum, bottom - viewportHeight)
            }
        })
    }
    function primaryActionIndex() {
        var preferredIndex = 0
        for (var index = 0; index < (scenario.actions || []).length; ++index) {
            if (scenario.actions[index].id === "push"
                    || scenario.actions[index].id === "target_x_increase") {
                preferredIndex = index
                break
            }
        }
        return preferredIndex
    }
    function focusFirstExperimentControl() {
        var action = actionRepeater.itemAt(primaryActionIndex())
        if (action) {
            action.forceActiveFocus()
            return
        }
        var control = controlRepeater.itemAt(0)
        if (control)
            control.focusControl()
    }
    function revealFocusedControl() {
        for (var index = 0; index < controlRepeater.count; ++index) {
            var control = controlRepeater.itemAt(index)
            if (control && control.revealIfFocused())
                return
        }
    }
    function showEvidenceComplete() {
        var flick = scroller.contentItem
        if (flick)
            flick.contentY = 0
    }
    function focusEvidence() {
        var flick = scroller.contentItem
        if (flick)
            flick.contentY = 0
        evidenceWorkflowItem.focusPrediction()
    }
    function formatControlValue(control, value) {
        var digits = Number(control.digits || 0)
        var suffix = control.unit ? " " + control.unit : ""
        return Number(value).toFixed(digits) + suffix
    }

    radius: 12
    color: "#FFFFFF"
    border.color: "#B8C3D4"
    border.width: 1
    Accessible.role: Accessible.Pane
    Accessible.name: backend.language === "ko"
                     ? "핵심 실험 제어" : "Core experiment controls"

    ScrollView {
        id: scroller
        anchors.fill: parent
        anchors.margins: compact ? 9 : 12
        contentWidth: availableWidth
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
        ScrollBar.vertical.policy: ScrollBar.AsNeeded
        ColumnLayout {
            id: contentColumn
            width: parent.width
            spacing: compact ? 6 : 8
            Label {
                visible: !(compact && panel.evidenceWorkflow)
                text: backend.hasReplay
                      ? backend.localizedText(backend.language, "transport.replay")
                      : backend.localizedText(backend.language, "experiment.try")
                color: "#172033"
                font.pixelSize: compact ? 17 : 20
                font.bold: true
                Accessible.name: backend.hasReplay && compact ? panel.workflowPrompt : text
            }
            Label {
                visible: backend.hasReplay
                text: backend.localizedText(backend.language, "transport.replay_help")
                color: "#334155"
                font.pixelSize: compact ? 12 : 13
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            EvidenceWorkflow {
                id: evidenceWorkflowItem
                visible: panel.evidenceWorkflow
                compact: panel.compact
                compactActionPrompt: panel.compactActionPrompt
                workflowPrompt: panel.workflowPrompt
                liveEditable: panel.liveEditable
                onRevealRequested: control => panel.revealControl(control)
                onPredictionCommitted: Qt.callLater(panel.focusFirstExperimentControl)
                onObservationCommitted: panel.evidenceSaved()
                onHeightChanged: Qt.callLater(panel.revealFocusedControl)
            }
            GridLayout {
                visible: !panel.needsEvidenceRetry && !backend.hasReplay
                         && (!scenario.requiresEvidence || backend.hasPrediction)
                         && (scenario.actions || []).length > 0
                Layout.fillWidth: true
                columns: Math.min(2, (scenario.actions || []).length)
                columnSpacing: 8
                rowSpacing: 6
                Repeater {
                    id: actionRepeater
                    model: scenario.actions || []
                    MButton {
                        id: actionButton
                        minimumButtonWidth: compact ? 84 : 112
                        text: modelData.label
                        accessibleName: backend.localizedText(backend.language, "experiment.try") + ": " + modelData.label
                        secondary: backend.hasLearnerAction
                                   || index !== panel.primaryActionIndex()
                        enabled: panel.liveEditable
                        Layout.fillWidth: true
                        onClicked: backend.applyAction(modelData.id)
                        onActiveFocusChanged: {
                            if (activeFocus)
                                panel.revealControl(actionButton)
                        }
                    }
                }
            }
            Label {
                visible: !panel.needsEvidenceRetry && !backend.hasReplay && !compact
                         && !backend.hasLearnerAction
                         && (!scenario.requiresEvidence || backend.hasPrediction)
                         && (scenario.actions || []).length > 0
                text: backend.language === "ko"
                      ? "먼저 버튼으로 움직임을 만든 뒤 값을 바꿔 보세요."
                      : "Create motion first, then change one value."
                color: "#475569"
                font.pixelSize: 12
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Rectangle {
                visible: !panel.needsEvidenceRetry && !backend.hasReplay
                         && !backend.hasLearnerAction
                         && (!scenario.requiresEvidence || backend.hasPrediction)
                         && (scenario.actions || []).length > 0
                Layout.fillWidth: true; height: 1; color: "#DCE2EC"
            }
            GridLayout {
                id: controlGrid
                Layout.fillWidth: true
                columns: compact ? 1 : 2
                columnSpacing: compact ? 0 : 10
                rowSpacing: compact ? 0 : 4
                Repeater {
                    id: controlRepeater
                    model: backend.hasReplay || panel.needsEvidenceRetry
                           || (scenario.requiresEvidence && !backend.hasPrediction)
                           ? [] : (scenario.controls || [])
                    ColumnLayout {
                        function focusControl() { slider.forceActiveFocus() }
                        function revealIfFocused() {
                            if (!slider.activeFocus)
                                return false
                            panel.revealControl(slider)
                            return true
                        }
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        Layout.preferredWidth: compact
                                               ? controlGrid.width
                                               : (controlGrid.width - controlGrid.columnSpacing) / 2
                        spacing: 0
                        RowLayout {
                            Layout.fillWidth: true
                            Label {
                                text: modelData.label
                                color: "#172033"
                                font.pixelSize: compact ? 13 : 14
                                font.bold: true
                                Layout.fillWidth: true
                                elide: Text.ElideRight
                            }
                            Label {
                                text: panel.formatControlValue(modelData, slider.value)
                                color: "#1D4ED8"
                                font.pixelSize: 14
                                font.bold: true
                                Accessible.name: modelData.label + ": " + text
                            }
                        }
                        Slider {
                            id: slider
                            Layout.fillWidth: true
                            Layout.preferredHeight: 28
                            from: modelData.minimum; to: modelData.maximum; stepSize: modelData.step
                            value: modelData.value
                            enabled: panel.liveEditable
                            focusPolicy: Qt.StrongFocus
                            Accessible.name: modelData.label
                            Accessible.description: (backend.language === "ko" ? "범위 " : "Range ")
                                                    + panel.formatControlValue(modelData, modelData.minimum)
                                                    + "–"
                                                    + panel.formatControlValue(modelData, modelData.maximum)
                                                    + (backend.language === "ko" ? ", 현재 " : ", current ")
                                                    + panel.formatControlValue(modelData, value)
                            onMoved: {
                                backend.applyControl(modelData.id, value)
                                panel.revealControl(slider)
                            }
                            onActiveFocusChanged: {
                                if (activeFocus)
                                    panel.revealControl(slider)
                            }
                            FocusRing { anchors.fill: parent; shown: slider.activeFocus }
                        }
                    }
                }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: "#DCE2EC" }
            GridLayout {
                Layout.fillWidth: true
                columns: compact ? 1 : 2
                columnSpacing: 8
                rowSpacing: 4
                Repeater {
                    model: backend.telemetryItems
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.columnSpan: !compact && index === 2 ? 2 : 1
                        Layout.preferredHeight: compact ? 38 : 34
                        radius: 6
                        color: "#F1F5F9"
                        Label {
                            anchors.fill: parent; anchors.margins: 6
                            text: modelData.label + "  " + modelData.value
                                  + (modelData.unit ? " " + modelData.unit : "")
                            color: "#172033"
                            font.pixelSize: 12
                            font.bold: true
                            verticalAlignment: Text.AlignVCenter
                            elide: Text.ElideRight
                        }
                    }
                }
            }
            MButton {
                id: resetCameraButton
                objectName: "sceneCameraReset"
                secondary: true
                enabled: panel.liveEditable || backend.hasReplay
                minimumButtonWidth: compact ? 84 : 124
                text: backend.localizedText(backend.language, "control.reset_camera")
                accessibleDescription: backend.localizedText(
                                           backend.language, "control.reset_camera_help")
                Layout.fillWidth: true
                onClicked: backend.applyAction("reset_camera")
                ToolTip {
                    id: cameraHelpTip
                    visible: resetCameraButton.hovered || resetCameraButton.activeFocus
                    text: backend.localizedText(backend.language, "control.camera_help")
                    width: resetCameraButton.width
                    x: 0
                    y: -height - 6
                    padding: 10
                    delay: 0
                    timeout: -1
                    contentItem: Text {
                        text: cameraHelpTip.text
                        color: "#172033"
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                    }
                    background: Rectangle {
                        color: "#FFFFFF"
                        border.color: "#64748B"
                        radius: 6
                    }
                }
                onActiveFocusChanged: {
                    if (activeFocus)
                        panel.revealControl(resetCameraButton)
                }
            }
            MCheckBox {
                id: advancedToggle
                objectName: "advancedToggle"
                text: backend.localizedText(backend.language, "experiment.advanced")
                Accessible.description: backend.language === "ko"
                                        ? "YAML 설정 파일과 플롯 프리셋을 표시합니다."
                                        : "Shows the YAML config file and plot preset."
                onActiveFocusChanged: {
                    if (activeFocus)
                        panel.revealControl(advancedToggle)
                }
            }
            Label {
                visible: advancedToggle.checked
                text: (scenario.config || "") + "\n" + (scenario.plotPreset || "")
                color: "#475569"; wrapMode: Text.WrapAnywhere
                Layout.fillWidth: true
            }
        }
    }
}

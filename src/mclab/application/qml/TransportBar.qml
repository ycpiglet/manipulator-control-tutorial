import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: bar
    property bool compact: false
    property bool needsEvidenceRetry: backend.sessionState === "completed"
                                      && !backend.hasReplay
                                      && backend.selectedScenario.requiresEvidence
                                      && !backend.hasObservation
    property bool experimentActionIsPrimary: Boolean(
                                                 !backend.hasReplay
                                                 && !backend.hasLearnerAction
                                                 && backend.sessionState !== "completed"
                                                 && (backend.selectedScenario.actions || []).length > 0
                                             )
    property bool evidenceEntryIsPrimary: Boolean(
                                              !backend.hasReplay
                                              && backend.selectedScenario.requiresEvidence
                                              && backend.hasLearnerAction
                                              && !backend.hasObservation
                                              && backend.sessionState !== "completed"
                                          )
    function focusPrimary() {
        primaryTransportButton.forceActiveFocus()
    }
    implicitHeight: compact ? 76 : 92
    radius: 12
    color: "#FFFFFF"
    border.color: "#CBD5E1"
    border.width: 1

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: compact ? 6 : 8
        spacing: 2
        Item {
            Layout.fillWidth: true
            Layout.preferredHeight: compact ? 20 : 24
            MProgressBar {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                visible: !backend.hasReplay
                value: backend.sessionProgress
                Accessible.name: backend.localizedText(backend.language, "transport.progress")
                Accessible.description: backend.localizedText(backend.language, "transport.progress_help")
            }
            Label {
                id: replayPositionLabel
                visible: backend.hasReplay
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                text: backend.replayPosition
                color: "#334155"; font.pixelSize: 12; font.bold: true
            }
            Item {
                id: replayTrackArea
                visible: backend.hasReplay
                anchors.left: parent.left
                anchors.right: replayPositionLabel.left
                anchors.rightMargin: compact ? 8 : 12
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                Slider {
                    id: timeline
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    height: 24
                    from: 0; to: 1; value: backend.sessionProgress
                    focusPolicy: Qt.StrongFocus
                    Accessible.name: backend.localizedText(backend.language, "transport.timeline")
                    Accessible.description: backend.localizedText(backend.language, "transport.timeline_help")
                    onMoved: backend.seekProgress(value)
                    FocusRing { anchors.fill: parent; shown: timeline.activeFocus }
                }
                Repeater {
                    model: backend.eventMarkers
                    Button {
                        id: eventMarker
                        property string markerLabel: (backend.language === "ko" ? "조작 이벤트: " : "Interaction event: ")
                                                     + modelData.name + (modelData.count > 1 ? " ×" + modelData.count : "")
                                                     + " · " + Number(modelData.time).toFixed(2) + " s"
                        x: Math.max(0, Math.min(parent.width - width, modelData.position * parent.width - width / 2))
                        y: parent.height - height; width: 24; height: 24; padding: 0
                        focusPolicy: Qt.StrongFocus
                        Accessible.name: markerLabel
                        Accessible.description: backend.language === "ko"
                                                ? "선택하면 이 이벤트가 기록된 프레임으로 이동합니다."
                                                : "Activate to move to the frame where this event was recorded."
                        onClicked: backend.seekEvent(index)
                        background: Item {
                            Rectangle {
                                anchors.horizontalCenter: parent.horizontalCenter
                                anchors.bottom: parent.bottom
                                width: 3; height: 9; radius: 1; color: "#FB7185"
                            }
                            Rectangle {
                                anchors.horizontalCenter: parent.horizontalCenter
                                anchors.bottom: parent.bottom; anchors.bottomMargin: 7
                                width: 7; height: 7; rotation: 45; color: "#FB7185"
                            }
                            FocusRing { anchors.fill: parent; shown: eventMarker.activeFocus }
                        }
                        contentItem: Item {}
                        ToolTip.visible: hovered || activeFocus
                        ToolTip.text: markerLabel
                    }
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            spacing: compact ? 5 : 8
            MButton {
                visible: backend.hasReplay
                secondary: true
                minimumButtonWidth: compact ? 44 : 70; text: "|◀"
                font.pixelSize: compact ? 14 : 16
                accessibleName: backend.language === "ko" ? "처음 프레임" : "First frame"
                ToolTip.visible: hovered || activeFocus; ToolTip.text: accessibleName
                onClicked: backend.firstFrame()
            }
            MButton {
                visible: backend.hasReplay
                secondary: true
                minimumButtonWidth: compact ? 44 : 90
                text: "◀"
                font.pixelSize: compact ? 14 : 16
                accessibleName: backend.localizedText(backend.language, "transport.previous_frame")
                ToolTip.visible: hovered || activeFocus; ToolTip.text: accessibleName
                onClicked: backend.previousFrame()
            }
            MButton {
                id: primaryTransportButton
                enabled: !backend.waitingForPrediction
                secondary: backend.sessionState === "completed" && !backend.hasReplay
                           && !bar.needsEvidenceRetry
                           || bar.experimentActionIsPrimary
                           || bar.evidenceEntryIsPrimary
                minimumButtonWidth: compact ? 76 : 104
                font.pixelSize: compact ? 14 : 16
                text: backend.waitingForPrediction
                      ? backend.localizedText(backend.language, "transport.predict_to_start")
                      : backend.sessionState === "completed" && !backend.hasReplay
                      ? (compact ? backend.localizedText(backend.language, "transport.restart_short") : backend.localizedText(backend.language, "transport.restart"))
                      : backend.sessionState === "completed" && backend.hasReplay
                      ? backend.localizedText(backend.language, "transport.play")
                      : backend.sessionState === "paused" ? backend.localizedText(backend.language, "transport.play") : backend.localizedText(backend.language, "transport.pause")
                accessibleDescription: backend.waitingForPrediction
                                       ? backend.localizedText(backend.language, "evidence.waiting_help")
                                       : bar.needsEvidenceRetry
                                         ? backend.localizedText(backend.language, "evidence.restart_first") : ""
                onClicked: backend.togglePause()
            }
            MButton {
                secondary: true
                visible: !backend.hasReplay
                enabled: !backend.waitingForPrediction
                         && !(backend.sessionState === "completed"
                              && backend.selectedScenario.requiresEvidence)
                minimumButtonWidth: compact ? 98 : 124
                text: backend.localizedText(backend.language, "transport.step")
                accessibleDescription: backend.localizedText(backend.language, "transport.step_help")
                ToolTip.visible: hovered || activeFocus
                ToolTip.text: backend.localizedText(backend.language, "transport.step_help")
                onClicked: backend.stepOnce()
            }
            MButton {
                visible: backend.hasReplay
                secondary: true
                minimumButtonWidth: compact ? 44 : 124
                text: compact ? "▶" : backend.localizedText(backend.language, "transport.next_frame")
                font.pixelSize: compact ? 14 : 16
                accessibleName: backend.localizedText(backend.language, "transport.next_frame")
                accessibleDescription: backend.localizedText(backend.language, "transport.frame_help")
                ToolTip.visible: hovered || activeFocus
                ToolTip.text: backend.localizedText(backend.language, "transport.frame_help")
                onClicked: backend.nextFrame()
            }
            MButton {
                visible: backend.hasReplay
                secondary: true
                minimumButtonWidth: compact ? 44 : 70; text: "▶|"
                font.pixelSize: compact ? 14 : 16
                accessibleName: backend.language === "ko" ? "마지막 프레임" : "Last frame"
                ToolTip.visible: hovered || activeFocus; ToolTip.text: accessibleName
                onClicked: backend.lastFrame()
            }
            MButton {
                secondary: true
                visible: !backend.hasReplay && backend.sessionState !== "completed"
                enabled: !backend.waitingForPrediction
                minimumButtonWidth: compact ? 92 : 124
                text: compact ? backend.localizedText(backend.language, "transport.restart_short") : backend.localizedText(backend.language, "transport.restart")
                onClicked: backend.resetExperiment()
            }
            MButton {
                secondary: true
                visible: !backend.hasReplay && !compact
                enabled: !backend.waitingForPrediction
                text: backend.localizedText(backend.language, "transport.defaults")
                onClicked: backend.applyAction("restore_defaults")
            }
            MButton {
                id: loopToggle
                objectName: "replayLoopToggle"
                visible: backend.hasReplay
                checkable: true
                secondary: true
                minimumButtonWidth: compact ? 68 : 124
                text: (checked ? "✓ " : compact ? "↻ " : "")
                      + backend.localizedText(
                            backend.language,
                            compact ? "transport.loop_short" : "transport.loop"
                        )
                font.pixelSize: compact ? 14 : 16
                accessibleName: backend.localizedText(backend.language, "transport.loop")
                accessibleDescription: backend.language === "ko"
                                       ? "선택한 기록 구간을 반복 재생합니다."
                                       : "Repeats the selected recording range."
                onToggled: backend.setReplayLoop(loopRange.first.value, loopRange.second.value, checked)
                ToolTip.visible: hovered || activeFocus
                ToolTip.text: backend.language === "ko"
                              ? "선택한 기록 구간을 반복 재생합니다."
                              : "Repeats the selected recording range."
            }
            RangeSlider {
                id: loopRange
                visible: backend.hasReplay
                enabled: loopToggle.checked
                Layout.preferredWidth: compact ? 88 : 120
                Layout.preferredHeight: 24
                from: 0; to: 1; first.value: 0; second.value: 1
                focusPolicy: Qt.StrongFocus
                Accessible.name: backend.language === "ko" ? "반복 구간" : "Replay loop range"
                Accessible.description: backend.language === "ko"
                                        ? "반복할 시작과 끝 위치를 선택합니다."
                                        : "Selects the start and end positions to repeat."
                first.onMoved: backend.setReplayLoop(first.value, second.value, loopToggle.checked)
                second.onMoved: backend.setReplayLoop(first.value, second.value, loopToggle.checked)
                background: Rectangle {
                    x: loopRange.leftPadding
                    y: loopRange.topPadding + loopRange.availableHeight / 2 - height / 2
                    width: loopRange.availableWidth; height: 6; radius: 3
                    color: loopRange.enabled ? "#CBD5E1" : "#E2E8F0"
                    Rectangle {
                        x: loopRange.first.visualPosition * parent.width
                        width: (loopRange.second.visualPosition - loopRange.first.visualPosition) * parent.width
                        height: parent.height; radius: 3
                        color: loopRange.enabled ? "#2563EB" : "#94A3B8"
                    }
                }
                first.handle: Rectangle {
                    x: loopRange.leftPadding + loopRange.first.visualPosition * (loopRange.availableWidth - width)
                    y: loopRange.topPadding + loopRange.availableHeight / 2 - height / 2
                    width: 20; height: 20; radius: 10
                    color: loopRange.enabled ? "#2563EB" : "#94A3B8"
                    border.color: "#FFFFFF"; border.width: 2
                }
                second.handle: Rectangle {
                    x: loopRange.leftPadding + loopRange.second.visualPosition * (loopRange.availableWidth - width)
                    y: loopRange.topPadding + loopRange.availableHeight / 2 - height / 2
                    width: 20; height: 20; radius: 10
                    color: loopRange.enabled ? "#2563EB" : "#94A3B8"
                    border.color: "#FFFFFF"; border.width: 2
                }
                FocusRing { anchors.fill: parent; shown: loopRange.activeFocus }
            }
            Item { Layout.fillWidth: true }
            SpeedSelector { implicitWidth: compact ? 72 : 92 }
        }
    }
}

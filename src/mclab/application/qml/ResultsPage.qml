import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: page
    objectName: "resultsPage"
    property bool compact: width < 900
    property var runs: backend.results
    property var batch: backend.batchProgress
    property int visibleLimit: 20
    property var firstPrimaryButton: null
    property var firstManageButton: null
    ScrollFocusHelper { id: resultFocusScroll }
    function openManager(run, trigger) {
        manageDialog.openFor(run, trigger)
    }
    function openFirstManager() {
        if (runs.length > 0)
            openManager(runs[0], firstManageButton)
    }
    function focusFirstPrimary() {
        if (firstPrimaryButton)
            firstPrimaryButton.forceActiveFocus()
    }
    function deleteManagedRun(confirmation, cleanupToken) {
        if (manageDialog.run.path) {
            if (backend.deleteRun(manageDialog.run.path, confirmation, cleanupToken))
                manageDialog.close()
        }
    }
    function loadMoreResults() {
        var firstNewIndex = visibleLimit
        var transferFocus = loadMoreButton.activeFocus
        visibleLimit = Math.min(runs.length, visibleLimit + 20)
        if (transferFocus) {
            Qt.callLater(function() {
                var card = resultRepeater.itemAt(firstNewIndex)
                if (card && card.primaryControl) {
                    card.primaryControl.forceActiveFocus()
                    Qt.callLater(function() {
                        resultFocusScroll.reveal(resultsScroller, resultsColumn, card, 4)
                    })
                }
            })
        }
    }
    function batchStatusText() {
        if (batch.cancelling)
            return backend.localizedText(backend.language, "path.cancelling_batch")
        if (batch.current > 0)
            return backend.localizedText(backend.language, "path.batch_progress")
                   .replace("{current}", batch.current).replace("{total}", batch.total)
                   .replace("{name}", batch.label)
        return backend.localizedText(backend.language, "path.batch_starting")
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 10
        ResultsHeader {
            Layout.fillWidth: true
            runCount: page.runs.length
            batchRunning: page.batch.running
        }
        ActiveSessionBar {}
        BatchSessionBar {}
        Rectangle {
            visible: page.runs.length === 0
            Layout.fillWidth: true
            Layout.maximumWidth: 760
            Layout.preferredHeight: page.batch.running ? 158 : 196
            Layout.alignment: Qt.AlignHCenter
            radius: 12
            color: "#FFFFFF"
            border.color: "#CBD5E1"
            border.width: 1
            ColumnLayout {
                anchors.centerIn: parent
                width: Math.min(parent.width - 32, 520)
                spacing: 10
                Label {
                    Layout.alignment: Qt.AlignHCenter
                    visible: !page.batch.running
                    text: "＋"
                    color: "#2563EB"
                    font.pixelSize: 30
                    font.bold: true
                }
                Label {
                    Layout.fillWidth: true
                    text: backend.localizedText(backend.language, "results.empty_title")
                    color: "#172033"
                    font.pixelSize: 21
                    font.bold: true
                    horizontalAlignment: Text.AlignHCenter
                }
                Label {
                    Layout.fillWidth: true
                    text: backend.localizedText(backend.language, "results.empty")
                    color: "#475569"
                    wrapMode: Text.WordWrap
                    horizontalAlignment: Text.AlignHCenter
                }
                MButton {
                    Layout.alignment: Qt.AlignHCenter
                    text: backend.localizedText(backend.language, "results.start_first")
                    accessibleDescription: page.batch.running
                                           ? backend.localizedText(backend.language, "batch.launch_blocked")
                                           : backend.hasActiveExperiment
                                             ? backend.localizedText(backend.language, "active.launch_blocked")
                                           : backend.localizedText(backend.language, "results.start_help")
                    enabled: backend.nextScenarioId !== ""
                             && !backend.hasActiveExperiment && !page.batch.running
                    onClicked: backend.startScenario(backend.nextScenarioId)
                }
            }
        }
        Label {
            visible: page.runs.length > 0
            text: page.runs.length > 0 ? page.runs[0].collectionSummary : ""
            color: "#475569"
            font.pixelSize: 13
        }
        ScrollView {
            id: resultsScroller
            visible: page.runs.length > 0
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: availableWidth
            ColumnLayout {
                id: resultsColumn
                width: parent.width
                spacing: 8
                Repeater {
                    id: resultRepeater
                    model: page.runs.slice(0, page.visibleLimit)
                    Rectangle {
                        id: resultCard
                        property var primaryControl: primaryAction
                        Layout.fillWidth: true
                        Layout.maximumWidth: 1120
                        Layout.preferredHeight: 224
                        Layout.alignment: Qt.AlignHCenter
                        radius: 12
                        color: "#FFFFFF"
                        border.color: "#CBD5E1"
                        border.width: 1
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 10
                            spacing: 4
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                Label {
                                    Layout.fillWidth: true
                                    text: modelData.lab + " · " + modelData.title + " · " + modelData.runLabel
                                    color: "#172033"
                                    font.pixelSize: 17
                                    font.bold: true
                                    elide: Text.ElideRight
                                }
                                Rectangle {
                                    implicitWidth: statusLabel.implicitWidth + 16
                                    implicitHeight: 24
                                    radius: 12
                                    color: modelData.statusCode === "completed" ? "#E7F8EF"
                                         : modelData.statusCode === "error" ? "#FEECEC" : "#FFF7E6"
                                    Label {
                                        id: statusLabel
                                        anchors.centerIn: parent
                                        text: modelData.status
                                        color: modelData.statusCode === "completed" ? "#166534"
                                             : modelData.statusCode === "error" ? "#991B1B" : "#704000"
                                        font.pixelSize: 12
                                        font.bold: true
                                    }
                                }
                            }
                            Label {
                                Layout.fillWidth: true
                                text: modelData.activeBatch ? page.batchStatusText() : modelData.outcome
                                color: "#334155"
                                font.pixelSize: 13
                                elide: Text.ElideRight
                            }
                            Label {
                                objectName: "completionReasonLabel"; Layout.fillWidth: true
                                text: backend.localizedText(backend.language, "results.completion_reason_label") + ": " + modelData.completionReasonText + " · " + modelData.completionReason
                                color: modelData.completed ? "#166534" : "#92400E"; font.pixelSize: 12
                                font.bold: true; elide: Text.ElideRight; Accessible.name: text
                            }
                            GridLayout {
                                visible: modelData.metrics.length > 0
                                Layout.fillWidth: true
                                Layout.preferredHeight: 42
                                columns: Math.max(1, modelData.metrics.length)
                                columnSpacing: 6
                                Repeater {
                                    model: modelData.metrics
                                    Rectangle {
                                        Layout.fillWidth: true
                                        Layout.fillHeight: true
                                        radius: 7
                                        color: "#F1F5F9"
                                        ColumnLayout {
                                            anchors.fill: parent
                                            anchors.margins: 5
                                            spacing: 0
                                            Label {
                                                Layout.fillWidth: true
                                                text: modelData.label
                                                color: "#475569"
                                                font.pixelSize: 12
                                                font.bold: true
                                                elide: Text.ElideRight
                                            }
                                            Label {
                                                text: modelData.value + (modelData.unit ? " " + modelData.unit : "")
                                                color: "#172033"
                                                font.pixelSize: 14
                                                font.bold: true
                                                font.family: "Noto Sans Mono"
                                            }
                                        }
                                    }
                                }
                            }
                            Label {
                                visible: modelData.metrics.length === 0
                                Layout.fillWidth: true
                                Layout.preferredHeight: 42
                                text: backend.localizedText(backend.language, "results.no_metrics")
                                color: "#64748B"
                                verticalAlignment: Text.AlignVCenter
                            }
                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 32
                                radius: 7
                                color: "#EAF1FF"
                                Label {
                                    anchors.fill: parent
                                    anchors.margins: 7
                                    text: modelData.nextAction
                                    color: "#1E40AF"
                                    font.pixelSize: 12
                                    font.bold: true
                                    elide: Text.ElideRight
                                }
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 8
                                MButton {
                                    id: primaryAction
                                    secondary: index > 0
                                    objectName: index === 0 ? "firstResultPrimaryAction" : ""
                                    property bool prefersReplay: !modelData.isBatch && Boolean(modelData.replay)
                                    property bool prefersRerun: !modelData.isBatch
                                                                 && !prefersReplay
                                                                 && Boolean(modelData.rerun)
                                    property bool launchesSession: prefersReplay || prefersRerun
                                    property bool launchBlocked: launchesSession
                                                                 && (backend.hasActiveExperiment
                                                                     || page.batch.running)
                                    Layout.fillWidth: true
                                    visible: launchesSession || Boolean(modelData.report)
                                    text: prefersReplay
                                          ? backend.localizedText(backend.language, "transport.replay")
                                          : prefersRerun
                                            ? backend.localizedText(backend.language, "transport.rerun")
                                            : backend.localizedText(backend.language, "results.report")
                                    accessibleName: text + ": " + modelData.lab + " · " + modelData.title + " · " + modelData.runLabel
                                    accessibleDescription: launchBlocked
                                                           ? backend.localizedText(
                                                                 backend.language,
                                                                 page.batch.running
                                                                 ? (prefersRerun
                                                                    ? "batch.launch_blocked"
                                                                    : "batch.replay_blocked")
                                                                 : (prefersRerun
                                                                    ? "active.launch_blocked"
                                                                    : "active.replay_launch_blocked"))
                                                           : launchesSession
                                                             ? modelData.nextAction
                                                             : enabled
                                                               ? modelData.outcome
                                                               : backend.localizedText(backend.language, "results.report_missing")
                                    enabled: launchesSession ? !launchBlocked : Boolean(modelData.report)
                                    ToolTip.visible: (hovered || activeFocus) && !enabled
                                    ToolTip.text: accessibleDescription
                                    onClicked: prefersReplay
                                               ? backend.replayRun(modelData.path)
                                               : prefersRerun
                                                 ? backend.rerunSavedRun(modelData.path, false)
                                                 : backend.openPath(modelData.reportPath)
                                    onActiveFocusChanged: { if (activeFocus) resultFocusScroll.reveal(resultsScroller, resultsColumn, resultCard, 4) }
                                    Component.onCompleted: {
                                        if (index === 0)
                                            page.firstPrimaryButton = primaryAction
                                    }
                                    Component.onDestruction: { if (page.firstPrimaryButton === primaryAction) page.firstPrimaryButton = null }
                                }
                                MButton {
                                    id: supportingAction
                                    property bool startsNewWork: !modelData.canRerunBatch || !page.batch.running
                                    property bool launchBlocked: startsNewWork
                                                                 && (backend.hasActiveExperiment
                                                                     || page.batch.running)
                                    Layout.fillWidth: true
                                    visible: modelData.canRerunBatch || (primaryAction.launchesSession && Boolean(modelData.report))
                                    secondary: true
                                    text: modelData.canRerunBatch
                                          ? (page.batch.cancelling
                                             ? backend.localizedText(backend.language, "path.cancelling_button")
                                             : page.batch.running
                                             ? backend.localizedText(backend.language, "path.cancel_batch")
                                             : backend.localizedText(backend.language, "results.run_compare"))
                                          : backend.localizedText(backend.language, "results.report")
                                    accessibleName: text + ": " + modelData.lab + " · " + modelData.title + " · " + modelData.runLabel
                                    accessibleDescription: modelData.canRerunBatch && launchBlocked
                                                           ? backend.localizedText(
                                                                 backend.language,
                                                                 page.batch.running
                                                                 ? "batch.replay_blocked"
                                                                 : modelData.canRerunBatch
                                                                   ? "active.launch_blocked"
                                                                   : "active.replay_launch_blocked")
                                                           : modelData.canRerunBatch
                                                             ? modelData.nextAction
                                                             : modelData.outcome
                                    enabled: modelData.canRerunBatch
                                             ? (page.batch.running
                                                ? !page.batch.cancelling
                                                : !launchBlocked)
                                             : Boolean(modelData.report)
                                    ToolTip.visible: (hovered || activeFocus) && !enabled
                                    ToolTip.text: accessibleDescription
                                    onClicked: modelData.canRerunBatch
                                               ? (page.batch.cancelling
                                                  ? undefined
                                                  : page.batch.running
                                                  ? backend.cancelBatch()
                                                  : backend.startAllCompare())
                                               : backend.openPath(modelData.reportPath)
                                    onActiveFocusChanged: { if (activeFocus) resultFocusScroll.reveal(resultsScroller, resultsColumn, resultCard, 4) }
                                }
                                MButton {
                                    id: manageButton
                                    Layout.fillWidth: true
                                    secondary: true
                                    text: backend.localizedText(backend.language, "results.manage")
                                    accessibleName: text + ": " + modelData.lab + " · " + modelData.title + " · " + modelData.runLabel
                                    accessibleDescription: modelData.activeBatch
                                                           ? backend.localizedText(backend.language, "results.active_batch_manage") : ""
                                    enabled: !modelData.activeBatch
                                    ToolTip.visible: modelData.activeBatch && (hovered || activeFocus)
                                    ToolTip.text: backend.localizedText(backend.language, "results.active_batch_manage")
                                    onClicked: page.openManager(modelData, manageButton)
                                    onActiveFocusChanged: { if (activeFocus) resultFocusScroll.reveal(resultsScroller, resultsColumn, resultCard, 4) }
                                    Component.onCompleted: {
                                        if (index === 0)
                                            page.firstManageButton = manageButton
                                    }
                                    Component.onDestruction: { if (page.firstManageButton === manageButton) page.firstManageButton = null }
                                }
                            }
                        }
                    }
                }
                MButton {
                    id: loadMoreButton
                    objectName: "loadMoreResultsButton"
                    visible: page.visibleLimit < page.runs.length
                    Layout.alignment: Qt.AlignHCenter
                    secondary: true
                    text: backend.localizedText(backend.language, "results.load_more")
                    accessibleDescription: page.visibleLimit + " / " + page.runs.length
                    onClicked: page.loadMoreResults()
                    onActiveFocusChanged: { if (activeFocus) resultFocusScroll.reveal(resultsScroller, resultsColumn, loadMoreButton) }
                }
            }
        }
    }
    ResultManageDialog {
        id: manageDialog
        launchBlocked: backend.hasActiveExperiment || page.batch.running
        launchBlockedDescription: page.batch.running
                                  ? backend.localizedText(backend.language,
                                                          "batch.manage_blocked")
                                  : backend.localizedText(backend.language,
                                                          "active.manage_blocked")
        deleteBlocked: backend.hasActiveExperiment
        onDeleteRequested: function(confirmation, cleanupToken) {
            page.deleteManagedRun(confirmation, cleanupToken)
        }
    }
}

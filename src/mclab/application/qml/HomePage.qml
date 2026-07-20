import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: page
    objectName: "homePage"
    property var course: backend.courseProgress
    property var batch: backend.batchProgress

    function focusTourSkip() {
        if (!tourStrip.visible)
            return
        tourStrip.focusSkip()
    }

    function focusTourAgain() {
        if (!tourAgainButton.visible)
            return
        tourAgainButton.forceActiveFocus()
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
    ScrollView {
        anchors.fill: parent
        contentWidth: availableWidth
        ColumnLayout {
            width: parent.width
            spacing: 18
            RowLayout {
                Layout.fillWidth: true
                Label {
                    text: backend.localizedText(backend.language, "app.name")
                    color: "#172033"
                    font.pixelSize: 34
                    font.bold: true
                    Layout.fillWidth: true
                }
                MButton {
                    id: tourAgainButton
                    visible: !backend.tourVisible && backend.setupStatus.ready
                             && !backend.hasActiveExperiment && !batch.running
                    secondary: true
                    text: backend.localizedText(backend.language, "tour.again")
                    accessibleDescription: backend.localizedText(backend.language,
                                                                  "tour.again_help")
                    onClicked: {
                        backend.showTour()
                        Qt.callLater(function() { tourStrip.focusSkip() })
                    }
                }
            }
            ActiveSessionBar {}
            TourStrip {
                id: tourStrip
                visible: backend.tourVisible && backend.setupStatus.ready
                         && !backend.hasActiveExperiment && !batch.running
                Layout.fillWidth: true
                onDismissRequested: {
                    backend.dismissTour()
                    Qt.callLater(function() { nextActionButton.forceActiveFocus() })
                }
            }
            EnvironmentStatusCard { visible: !backend.setupStatus.ready }
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: page.width < 820 ? 144 : 160
                radius: 12
                color: course.complete ? "#F0FDF4"
                                       : batch.cancelling ? "#FFF7E6"
                                       : course.next.ready === false ? "#FFF7E6" : "#EAF1FF"
                border.width: 1
                border.color: course.complete ? "#86C9A9"
                                              : batch.cancelling ? "#E7B34A"
                                              : course.next.ready === false ? "#E7B34A" : "#B8CCF4"
                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 24
                    spacing: 20
                    ColumnLayout {
                        Layout.fillWidth: true
                        Label {
                            text: course.complete ? backend.localizedText(backend.language, "path.complete_title")
                                  : batch.running ? backend.localizedText(backend.language, "path.batch_running_title")
                                  : (course.nextKind === "batch"
                                     ? backend.localizedText(backend.language, "path.final_step")
                                     : backend.localizedText(backend.language, "path.next_experiment")) + ": "
                                    + (course.next.lab || "").toUpperCase()
                                    + " · " + (course.next.title || "")
                            color: "#172033"
                            font.pixelSize: 22
                            font.bold: true
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                        Label {
                            text: course.complete ? backend.localizedText(backend.language, "path.complete_detail")
                                                  : batch.running ? page.batchStatusText()
                                                  : (course.next.purpose || "")
                            color: "#334155"
                            font.pixelSize: 14
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                        Label {
                            text: course.complete
                                  ? course.done + " / " + course.total + " · "
                                    + backend.localizedText(backend.language, "path.saved_results")
                                  : (course.next.minutes || 0) + " "
                                    + backend.localizedText(backend.language, "scenario.minutes") + " · "
                                    + (course.next.difficulty || "") + " · "
                                    + (backend.language === "ko" ? "결과 자동 저장" : "Results save automatically")
                            color: "#334155"
                            font.pixelSize: 15
                        }
                    }
                    MassSpringPreview {
                        visible: !course.complete && course.nextKind === "scenario"
                                 && page.width >= 900
                    }
                    MButton {
                        id: nextActionButton
                        property bool startsNewWork: !course.complete && !batch.running
                        text: course.complete ? backend.localizedText(backend.language, "path.review_results")
                              : batch.cancelling ? backend.localizedText(backend.language, "path.cancelling_button")
                              : batch.running ? backend.localizedText(backend.language, "path.cancel_batch")
                              : course.nextKind === "batch" ? backend.localizedText(backend.language, "path.start_batch")
                              : backend.localizedText(backend.language, "home.next")
                        enabled: (course.complete || (batch.running && !batch.cancelling)
                                  || (!batch.running && course.next.ready !== false))
                                 && (!startsNewWork || !backend.hasActiveExperiment
                                     || backend.sessionState !== "completed")
                        accessibleDescription: startsNewWork && backend.hasActiveExperiment
                                               && backend.sessionState === "completed"
                                               ? backend.localizedText(backend.language, "active.launch_blocked")
                                               : enabled
                                                 ? (course.complete ? backend.localizedText(backend.language, "path.complete_detail")
                                                    : batch.running ? page.batchStatusText()
                                                                    : (course.next.purpose || ""))
                                                 : (course.next.readinessDetail + " "
                                                    + course.next.readinessAction)
                        onClicked: course.complete ? backend.navigate("results")
                                   : batch.cancelling ? undefined
                                   : batch.running ? backend.cancelBatch()
                                                   : backend.startCourseNext()
                    }
                }
            }
            EnvironmentStatusCard { visible: backend.setupStatus.ready }
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: progressContent.implicitHeight + 32
                radius: 12
                color: "#FFFFFF"
                border.color: "#CBD5E1"
                border.width: 1
                ColumnLayout {
                    id: progressContent
                    anchors.left: parent.left; anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.margins: 16
                    spacing: 8
                    RowLayout {
                        Layout.fillWidth: true
                        Label { text: backend.localizedText(backend.language, "home.progress"); color: "#172033"; font.pixelSize: 20; font.bold: true; Layout.fillWidth: true }
                        Label {
                            text: course.done + " / " + course.total
                            color: "#1D4ED8"
                            font.pixelSize: 22
                            font.bold: true
                        }
                    }
                    Label {
                        text: backend.localizedText(backend.language, "home.progress_detail")
                        color: "#334155"
                        font.pixelSize: 15
                        wrapMode: Text.WordWrap
                        Layout.fillWidth: true
                    }
                    MProgressBar {
                        value: course.total > 0 ? course.done / course.total : 0
                        Layout.fillWidth: true
                        Accessible.name: backend.localizedText(backend.language, "home.progress")
                    }
                }
            }
            RowLayout {
                Layout.fillWidth: true
                Label { text: backend.localizedText(backend.language, "home.contents"); color: "#172033"; font.pixelSize: 24; font.bold: true; Layout.fillWidth: true }
            }
            Label {
                text: backend.localizedText(backend.language, "home.contents_hint")
                color: "#334155"
                font.pixelSize: 15
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            GridLayout {
                Layout.fillWidth: true
                columns: page.width >= 1500 ? 3 : page.width >= 900 ? 2 : 1
                columnSpacing: 12
                rowSpacing: 12
                Repeater { model: course.path; PathStepRow { scenario: modelData } }
            }
            Item { Layout.preferredHeight: 8 }
        }
    }
}

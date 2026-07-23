import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: page
    property var course: visible ? backend.courseProgress
                                 : ({complete: false, done: 0, next: {}, nextKind: "",
                                     path: [], total: 0})
    property var batch: backend.batchProgress
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
            spacing: 12

            RowLayout {
                Layout.fillWidth: true
                Label {
                    text: backend.localizedText(backend.language, "nav.path")
                    color: "#172033"
                    font.pixelSize: 30
                    font.bold: true
                    Layout.fillWidth: true
                }
                Label {
                    text: course.done + " / " + course.total
                    color: course.complete ? "#166534" : "#1D4ED8"
                    font.pixelSize: 22
                    font.bold: true
                }
            }
            Label {
                text: course.complete ? backend.localizedText(backend.language, "path.complete_summary")
                                      : backend.localizedText(backend.language, "path.subtitle")
                color: "#475569"
                font.pixelSize: 15
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            ActiveSessionBar {}
            MProgressBar {
                value: course.total > 0 ? course.done / course.total : 0
                Layout.fillWidth: true
                Accessible.name: backend.localizedText(backend.language, "path.progress")
                Accessible.description: course.done + " / " + course.total
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: nextContent.implicitHeight + 28
                radius: 12
                color: course.complete ? "#F0FDF4"
                                       : batch.cancelling ? "#FFF7E6"
                                       : course.next.ready === false ? "#FFF7E6" : "#EAF1FF"
                border.width: course.complete || batch.cancelling
                              || course.next.ready === false ? 1 : 2
                border.color: course.complete ? "#86C9A9"
                                              : batch.cancelling ? "#E7B34A"
                                              : course.next.ready === false ? "#E7B34A" : "#2563EB"

                RowLayout {
                    id: nextContent
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.margins: 14
                    spacing: 12

                    Rectangle {
                        width: 44
                        height: 44
                        radius: 22
                        color: course.complete ? "#16794B"
                                               : batch.cancelling ? "#9A6700"
                                               : course.next.ready === false ? "#9A6700" : "#2563EB"
                        Label {
                            anchors.centerIn: parent
                            text: course.complete ? "✓" : batch.running ? "…" : (course.done + 1)
                            color: "#FFFFFF"
                            font.pixelSize: 19
                            font.bold: true
                        }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 3
                        Label {
                            text: course.complete ? backend.localizedText(backend.language, "path.complete_title")
                                  : batch.running ? backend.localizedText(backend.language, "path.batch_running_title")
                                  : (course.nextKind === "batch"
                                     ? backend.localizedText(backend.language, "path.final_step")
                                     : backend.localizedText(backend.language, "path.next_experiment")) + " · "
                                    + (course.next.lab || "").toUpperCase() + " · "
                                    + (course.next.title || "")
                            color: "#172033"
                            font.pixelSize: 18
                            font.bold: true
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                        Label {
                            text: course.complete ? backend.localizedText(backend.language, "path.complete_detail")
                                  : batch.running ? page.batchStatusText()
                                  : course.next.ready === false
                                    ? course.next.readinessDetail : (course.next.purpose || "")
                            color: course.next.ready === false && !course.complete
                                   ? "#704000" : "#334155"
                            font.pixelSize: 14
                            maximumLineCount: 2
                            elide: Text.ElideRight
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                        Label {
                            visible: !course.complete && !batch.running
                                     && course.next.ready === false
                            text: course.next.readinessAction || ""
                            color: "#704000"
                            font.pixelSize: 13
                            font.bold: true
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                    }
                    MButton {
                        property bool startsNewWork: !course.complete && !batch.running
                        text: course.complete ? backend.localizedText(backend.language, "path.review_results")
                              : batch.cancelling ? backend.localizedText(backend.language, "path.cancelling_button")
                              : batch.running ? backend.localizedText(backend.language, "path.cancel_batch")
                              : course.nextKind === "batch" ? backend.localizedText(backend.language, "path.start_batch")
                              : backend.localizedText(backend.language, "path.start_next")
                        accessibleName: text + (course.complete ? "" : ": "
                                        + (course.next.lab || "").toUpperCase() + " · "
                                        + (course.next.title || ""))
                        accessibleDescription: startsNewWork && backend.hasActiveExperiment
                                               && backend.sessionState === "completed"
                                               ? backend.localizedText(backend.language, "active.launch_blocked")
                                               : course.complete ? backend.localizedText(backend.language, "path.complete_detail")
                                               : batch.running ? page.batchStatusText()
                                               : course.next.ready === false
                                                 ? course.next.readinessDetail + " "
                                                   + course.next.readinessAction
                                                 : (course.next.purpose || "")
                        enabled: (course.complete || (batch.running && !batch.cancelling)
                                  || (!batch.running && course.next.ready !== false))
                                 && (!startsNewWork || !backend.hasActiveExperiment
                                     || backend.sessionState !== "completed")
                        onClicked: course.complete ? backend.navigate("results")
                                   : batch.cancelling ? undefined
                                   : batch.running ? backend.cancelBatch()
                                                   : backend.startCourseNext()
                    }
                }
            }

            Label {
                text: backend.localizedText(backend.language, "path.all_steps")
                color: "#172033"
                font.pixelSize: 20
                font.bold: true
                Layout.topMargin: 4
            }
            GridLayout {
                Layout.fillWidth: true
                columns: page.width >= 1100 ? 2 : 1
                columnSpacing: 10
                rowSpacing: 10
                Repeater {
                    model: course.path
                    PathStepRow { scenario: modelData }
                }
            }
            Item { Layout.preferredHeight: 4 }
        }
    }
}

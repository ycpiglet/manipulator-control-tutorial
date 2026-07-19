import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: bar
    property var batch: backend.batchProgress

    function statusText() {
        if (batch.cancelling)
            return backend.localizedText(backend.language, "path.cancelling_batch")
        if (batch.current > 0)
            return backend.localizedText(backend.language, "path.batch_progress")
                   .replace("{current}", batch.current).replace("{total}", batch.total)
                   .replace("{name}", batch.label)
        return backend.localizedText(backend.language, "path.batch_starting")
    }

    visible: batch.running
    Layout.fillWidth: true
    Layout.preferredHeight: content.implicitHeight + 20
    radius: 12
    color: batch.cancelling ? "#FFF7E6" : "#EAF1FF"
    border.width: 1
    border.color: batch.cancelling ? "#E7B34A" : "#93B4F4"

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
            color: bar.batch.cancelling ? "#9A6700" : "#2563EB"
            Label {
                anchors.centerIn: parent
                text: "…"
                color: "#FFFFFF"
                font.pixelSize: 20
                font.bold: true
                Accessible.ignored: true
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            Label {
                Layout.fillWidth: true
                text: backend.localizedText(backend.language, "path.batch_running_title")
                color: bar.batch.cancelling ? "#704000" : "#173E77"
                font.pixelSize: 16
                font.bold: true
                wrapMode: Text.WordWrap
            }
            Label {
                Layout.fillWidth: true
                text: bar.statusText()
                color: bar.batch.cancelling ? "#704000" : "#334155"
                font.pixelSize: 13
                maximumLineCount: 2
                elide: Text.ElideRight
                wrapMode: Text.WordWrap
                Accessible.name: text
            }
        }
        MButton {
            minimumButtonWidth: 126
            text: bar.batch.cancelling
                  ? backend.localizedText(backend.language, "path.cancelling_button")
                  : backend.localizedText(backend.language, "path.cancel_batch")
            enabled: !bar.batch.cancelling
            accessibleDescription: bar.statusText()
            onClicked: backend.cancelBatch()
        }
    }
}

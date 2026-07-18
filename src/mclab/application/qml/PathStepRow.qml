import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: row
    property var scenario
    Layout.fillWidth: true
    implicitHeight: 74
    radius: 10
    color: scenario.isNext ? "#EAF1FF" : "#FFFFFF"
    border.width: scenario.isNext ? 2 : 1
    border.color: scenario.isNext ? "#2563EB" : "#CBD5E1"

    RowLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 12
        Rectangle {
            width: 42; height: 42; radius: 21
            color: scenario.completed ? "#16794B" : scenario.isNext ? "#2563EB" : "#E2E8F0"
            Label {
                anchors.centerIn: parent
                text: scenario.step || ""
                color: scenario.completed || scenario.isNext ? "#FFFFFF" : "#334155"
                font.pixelSize: 17
                font.bold: true
            }
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2
            Label {
                text: (scenario.lab ? scenario.lab.charAt(0).toUpperCase() + scenario.lab.slice(1) + " · " : "") + (scenario.title || "")
                color: "#172033"
                font.pixelSize: 16
                font.bold: true
                Layout.fillWidth: true
                elide: Text.ElideRight
            }
            Label {
                text: scenario.purpose || ""
                color: "#475569"
                font.pixelSize: 13
                Layout.fillWidth: true
                elide: Text.ElideRight
            }
        }
        Rectangle {
            implicitWidth: statusText.implicitWidth + 20
            height: 32
            radius: 16
            color: scenario.completed ? "#DCFCE7" : scenario.isNext ? "#DBEAFE" : "#F1F5F9"
            Label {
                id: statusText
                anchors.centerIn: parent
                text: scenario.completed ? backend.localizedText(backend.language, "path.completed") : scenario.isNext ? backend.localizedText(backend.language, "path.next") : backend.localizedText(backend.language, "path.upcoming")
                color: scenario.completed ? "#166534" : scenario.isNext ? "#1D4ED8" : "#475569"
                font.pixelSize: 13
                font.bold: true
            }
        }
    }
}

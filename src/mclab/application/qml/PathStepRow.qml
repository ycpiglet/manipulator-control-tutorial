import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: row
    property var scenario
    property var latestDecision: scenario && scenario.latestCompletionDecision
                                         ? scenario.latestCompletionDecision : ({})
    property var creditedDecision: scenario && scenario.creditedCompletionDecision
                                           ? scenario.creditedCompletionDecision : ({})
    property string latestRunFolder: runFolder(scenario ? scenario.latestRun : "")
    property string creditedRunFolder: runFolder(scenario ? scenario.creditedRun : "")
    property bool showsHistoricalDiagnostic: Boolean(
        scenario && scenario.completed
        && creditedDecision.complete === true
        && latestDecision.complete === false
        && latestRunFolder && creditedRunFolder
        && latestRunFolder !== creditedRunFolder
    )
    property string historicalDiagnosticText: showsHistoricalDiagnostic
                                              ? historicalDiagnostic() : ""
    Layout.fillWidth: true
    implicitHeight: showsHistoricalDiagnostic ? 94 : 74
    radius: 10
    color: scenario.isNext ? "#EAF1FF" : "#FFFFFF"
    border.width: scenario.isNext ? 2 : 1
    border.color: scenario.isNext ? "#2563EB" : "#CBD5E1"

    function runFolder(path) {
        var normalized = String(path || "").replace(/\\/g, "/")
        var parts = normalized.split("/")
        for (var index = parts.length - 1; index >= 0; --index) {
            if (parts[index])
                return parts[index]
        }
        return ""
    }

    function latestReasonText() {
        var reason = String(latestDecision.primary_reason || "")
        if (!reason)
            return backend.language === "ko" ? "완료 증거 미충족"
                                               : "Completion evidence incomplete"
        var suffix = reason.split(".").pop()
        var key = "results.completion_reason." + suffix
        var localized = backend.localizedText(backend.language, key)
        return localized && localized !== key ? localized : reason
    }

    function historicalDiagnostic() {
        var reason = latestReasonText()
        return backend.language === "ko"
               ? "이전 완료 인정 " + creditedRunFolder + "; 최신 " + latestRunFolder + ": " + reason
               : "Done via credited " + creditedRunFolder + "; latest " + latestRunFolder + ": " + reason
    }

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
            Label {
                objectName: "historicalCompletionDiagnostic"
                visible: row.showsHistoricalDiagnostic
                text: row.historicalDiagnosticText
                color: "#9A6700"
                font.pixelSize: 12
                font.bold: true
                Layout.fillWidth: true
                elide: Text.ElideRight
                Accessible.role: Accessible.StaticText
                Accessible.name: text
                Accessible.ignored: !visible
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

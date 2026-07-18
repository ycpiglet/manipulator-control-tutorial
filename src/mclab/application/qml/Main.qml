import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: window
    property bool compactWindow: width < 900 || height < 500
    function focusPageEntry() {
        var indices = {"home": 0, "path": 1, "explore": 2, "results": 3}
        var index = indices[backend.page]
        if (index !== undefined) {
            var item = navigation.itemAt(index)
            if (item)
                item.forceActiveFocus()
        }
    }
    width: requestedWindowWidth > 0 ? requestedWindowWidth : 1280
    height: requestedWindowHeight > 0 ? requestedWindowHeight : 720
    minimumWidth: 640
    minimumHeight: 360
    visible: true
    title: backend.localizedText(backend.language, "app.name")
    color: "#F5F7FB"
    palette.window: "#F5F7FB"
    palette.windowText: "#172033"
    palette.text: "#172033"
    palette.buttonText: "#172033"
    palette.highlight: "#2563EB"
    palette.highlightedText: "#FFFFFF"

    header: Rectangle {
        height: window.compactWindow ? 52 : 68
        color: "#FFFFFF"
        border.color: "#DCE2EC"
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: window.compactWindow ? 8 : 20
            anchors.rightMargin: window.compactWindow ? 8 : 20
            spacing: window.compactWindow ? 3 : 8
            Label { text: "MCLab"; color: "#172033"; font.pixelSize: window.compactWindow ? 19 : 23; font.bold: true; Layout.rightMargin: window.compactWindow ? 5 : 18 }
            Repeater {
                id: navigation
                model: [["home", "nav.home"], ["path", "nav.path"], ["explore", "nav.explore"], ["results", "nav.results"]]
                Button {
                    text: backend.localizedText(backend.language, modelData[1])
                    implicitWidth: Math.max(44, contentItem.implicitWidth + 16)
                    implicitHeight: 44
                    flat: true
                    focusPolicy: Qt.StrongFocus
                    Accessible.name: text
                    Accessible.description: backend.page === modelData[0]
                                            ? (backend.language === "ko" ? "현재 화면" : "Current page")
                                            : ""
                    font.bold: backend.page === modelData[0]
                    contentItem: Text {
                        text: parent.text
                        color: backend.page === modelData[0] ? "#1D4ED8" : "#26334D"
                        font.pixelSize: window.compactWindow ? 13 : 15
                        font.weight: backend.page === modelData[0] ? Font.Bold : Font.DemiBold
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                    onClicked: backend.navigate(modelData[0])
                    background: Rectangle {
                        radius: 8
                        color: parent.hovered || backend.page === modelData[0] ? "#EAF1FF" : "transparent"
                        border.width: parent.activeFocus ? 3 : 0
                        border.color: parent.activeFocus ? "#FFDD00" : "transparent"
                        Rectangle {
                            anchors.fill: parent; anchors.margins: 3
                            radius: 5; color: "transparent"
                            border.width: parent.parent.activeFocus ? 2 : 0
                            border.color: "#000000"
                        }
                    }
                }
            }
            Item { Layout.fillWidth: true }
            LanguageSelector {
                currentIndex: backend.language === "ko" ? 0 : 1
                implicitWidth: window.compactWindow ? 132 : 152
                implicitHeight: window.compactWindow ? 44 : 48
                Accessible.name: backend.language === "ko" ? "언어" : "Language"
                onActivated: backend.setLanguage(currentIndex === 0 ? "ko" : "en")
            }
        }
    }

    StackLayout {
        anchors.fill: parent
        anchors.margins: window.compactWindow ? 8 : 20
        currentIndex: ({"home": 0, "path": 1, "explore": 2, "results": 3, "experiment": 4})[backend.page] || 0
        HomePage {}
        LearningPathPage {}
        ExplorePage {}
        ResultsPage {}
        ExperimentPage {}
    }

    Connections {
        target: backend
        function onPage_changed() {
            if (backend.page !== "experiment")
                Qt.callLater(window.focusPageEntry)
        }
    }

    Dialog {
        id: errorDialog
        property var returnFocusItem: null
        modal: true
        anchors.centerIn: parent
        width: Math.min(window.width - 64, 620)
        title: backend.localizedText(backend.language, "error.title")
        visible: backend.errorMessage.length > 0
        standardButtons: Dialog.NoButton
        onAboutToShow: returnFocusItem = window.activeFocusItem
        onClosed: {
            backend.clearError()
            var target = returnFocusItem
            returnFocusItem = null
            if (target && target.visible && target.enabled)
                Qt.callLater(function() { target.forceActiveFocus() })
        }
        background: Rectangle {
            color: "#FFFFFF"
            radius: 12
            border.color: "#64748B"
            border.width: 2
        }
        ColumnLayout {
            width: parent.width
            spacing: 16
            Label {
                text: backend.errorMessage
                color: "#172033"
                font.pixelSize: 17
                font.weight: Font.DemiBold
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: recoveryText.implicitHeight + 24
                radius: 8
                color: "#FFF7E6"
                border.color: "#E7B34A"
                Label {
                    id: recoveryText
                    anchors.fill: parent
                    anchors.margins: 12
                    text: backend.localizedText(backend.language, "error.action") + ": " + backend.errorAction
                    color: "#704000"
                    font.pixelSize: 15
                    wrapMode: Text.WordWrap
                }
            }
            RowLayout {
                Layout.fillWidth: true
                MButton {
                    secondary: true
                    text: backend.localizedText(backend.language, "error.copy")
                    accessibleDescription: backend.language === "ko"
                                           ? "오류 원인과 권장 복구 행동을 클립보드에 복사합니다."
                                           : "Copies the error cause and recommended recovery action."
                    onClicked: {
                        detail.selectAll()
                        detail.copy()
                    }
                }
                Item { Layout.fillWidth: true }
                MButton {
                    id: closeErrorButton
                    text: backend.localizedText(backend.language, "error.close")
                    onClicked: errorDialog.close()
                }
            }
            MCheckBox {
                id: showDetails
                text: backend.localizedText(backend.language, "error.show_details")
                Accessible.description: backend.language === "ko"
                                        ? "오류의 기술 세부정보를 펼치거나 접습니다."
                                        : "Expands or collapses technical error details."
            }
            ScrollView {
                visible: showDetails.checked
                Layout.fillWidth: true
                Layout.preferredHeight: 150
                TextArea {
                    id: detail
                    text: backend.errorDetail + "\n" + backend.errorAction
                    readOnly: true
                    wrapMode: Text.WrapAnywhere
                    color: "#172033"
                    Accessible.name: backend.localizedText(backend.language, "error.show_details")
                    FocusRing { anchors.fill: parent; shown: detail.activeFocus }
                }
            }
        }
        onOpened: closeErrorButton.forceActiveFocus()
    }
}

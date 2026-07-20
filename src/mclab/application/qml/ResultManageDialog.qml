import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Dialog {
    id: dialog
    property var run: ({
        "lab": "", "title": "", "scenarioId": "", "name": "", "size": "",
        "availability": "", "deleteWarning": "", "path": "", "cleanupToken": "",
        "rerun": false, "tuned": false
    })
    property var returnFocusItem: null
    property bool launchBlocked: false
    property string launchBlockedDescription: ""
    property bool deleteBlocked: false
    property bool deleteConfirming: false
    signal deleteRequested(string confirmation, string cleanupToken)

    function openFor(savedRun, trigger) {
        run = savedRun
        returnFocusItem = trigger || null
        deleteConfirming = false
        deleteConfirmation.clear()
        open()
    }

    parent: Overlay.overlay
    x: Math.max(12, (parent.width - width) / 2)
    y: Math.max(8, (parent.height - height) / 2)
    width: Math.min(560, parent.width - 24)
    height: Math.min(360, parent.height - 16)
    modal: true
    focus: true
    title: backend.localizedText(backend.language, "results.manage_title")
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    onOpened: {
        // Dialog is a Popup, so the accessible Dialog interface belongs to
        // the generated popup Item rather than this non-Item QML object.
        // Name that actual interface without introducing a second Dialog
        // role in the accessibility tree.
        if (dialog.contentItem && dialog.contentItem.parent)
            dialog.contentItem.parent.Accessible.name = dialog.title
        closeButton.forceActiveFocus()
    }
    onTitleChanged: {
        if (dialog.visible && dialog.contentItem && dialog.contentItem.parent)
            dialog.contentItem.parent.Accessible.name = dialog.title
    }
    onClosed: {
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

    contentItem: ColumnLayout {
        spacing: 6
        Label {
            Layout.fillWidth: true
            text: dialog.run.lab + " · " + dialog.run.title
            color: "#172033"
            font.bold: true
            font.pixelSize: 17
        }
        Label {
            Layout.fillWidth: true
            text: dialog.run.scenarioId + " · " + dialog.run.name + " · " + dialog.run.size
            color: "#475569"
            font.pixelSize: 12
            wrapMode: Text.WrapAnywhere
        }
        Label {
            Layout.fillWidth: true
            text: dialog.run.availability
            color: "#334155"
            font.pixelSize: 12
            font.bold: true
            wrapMode: Text.WordWrap
        }
        Label {
            visible: dialog.launchBlocked
            Layout.fillWidth: true
            text: dialog.launchBlockedDescription
            color: "#1E40AF"
            font.pixelSize: 12
            font.bold: true
            wrapMode: Text.WordWrap
            Accessible.name: text
        }
        GridLayout {
            visible: !dialog.deleteConfirming
            Layout.fillWidth: true
            columns: 3
            columnSpacing: 6
            MButton {
                Layout.fillWidth: true
                text: backend.localizedText(backend.language, "transport.rerun")
                enabled: Boolean(dialog.run.rerun) && !dialog.launchBlocked
                accessibleDescription: dialog.launchBlocked
                                       ? dialog.launchBlockedDescription
                                       : enabled ? "" : backend.localizedText(backend.language, "results.rerun_missing")
                onClicked: backend.rerunSavedRun(dialog.run.path, false)
            }
            MButton {
                Layout.fillWidth: true
                text: backend.localizedText(backend.language, "transport.tuned")
                enabled: Boolean(dialog.run.tuned) && !dialog.launchBlocked
                accessibleDescription: dialog.launchBlocked
                                       ? dialog.launchBlockedDescription
                                       : enabled ? "" : backend.localizedText(backend.language, "results.tuned_missing")
                onClicked: backend.rerunSavedRun(dialog.run.path, true)
            }
            MButton {
                Layout.fillWidth: true
                secondary: true
                text: backend.localizedText(backend.language, "results.open_folder")
                onClicked: backend.openPath(dialog.run.path)
            }
        }
        Label {
            Layout.fillWidth: true
            text: dialog.run.deleteWarning
            color: "#991B1B"
            font.pixelSize: 12
            wrapMode: Text.WordWrap
        }
        GridLayout {
            visible: !dialog.deleteConfirming
            Layout.fillWidth: true
            columns: 2
            columnSpacing: 8
            MButton {
                id: beginDeleteButton
                objectName: "beginQuarantineButton"
                Layout.fillWidth: true
                danger: true
                text: backend.localizedText(backend.language, "results.delete")
                enabled: !dialog.deleteBlocked
                accessibleDescription: dialog.deleteBlocked
                                       ? backend.localizedText(backend.language, "active.manage_blocked")
                                       : dialog.run.deleteWarning
                onClicked: {
                    dialog.deleteConfirming = true
                    deleteConfirmation.forceActiveFocus()
                }
            }
            MButton {
                id: closeButton
                Layout.fillWidth: true
                secondary: true
                text: backend.localizedText(backend.language, "results.close")
                onClicked: dialog.close()
            }
        }
        ColumnLayout {
            visible: dialog.deleteConfirming
            Layout.fillWidth: true
            spacing: 6
            Label {
                Layout.fillWidth: true
                text: backend.localizedText(backend.language, "results.delete_confirm")
                             .replace("{name}", dialog.run.name)
                color: "#7F1D1D"
                font.pixelSize: 12
                font.bold: true
                wrapMode: Text.WrapAnywhere
            }
            TextField {
                id: deleteConfirmation
                objectName: "deleteConfirmationInput"
                Layout.fillWidth: true
                implicitHeight: 48
                placeholderText: backend.localizedText(
                    backend.language, "results.delete_confirm_placeholder")
                placeholderTextColor: "#5B6475"
                color: "#172033"
                font.pixelSize: 14
                leftPadding: 12
                rightPadding: 12
                verticalAlignment: TextInput.AlignVCenter
                Accessible.name: backend.localizedText(
                    backend.language, "results.delete_confirm").replace(
                        "{name}", dialog.run.name)
                Accessible.description: placeholderText
                background: Rectangle {
                    color: "#FFFFFF"
                    radius: 8
                    border.color: "#64748B"
                    border.width: 2
                }
                FocusRing {
                    anchors.fill: parent
                    shown: deleteConfirmation.activeFocus
                }
            }
            GridLayout {
                Layout.fillWidth: true
                columns: 2
                columnSpacing: 8
                MButton {
                    objectName: "confirmQuarantineButton"
                    Layout.fillWidth: true
                    danger: true
                    text: backend.localizedText(
                        backend.language, "results.delete_confirm_action")
                    enabled: !dialog.deleteBlocked
                             && deleteConfirmation.text === dialog.run.name
                    accessibleDescription: enabled
                                           ? dialog.run.deleteWarning
                                           : backend.localizedText(
                                               backend.language,
                                               "results.delete_confirm_placeholder")
                    onClicked: dialog.deleteRequested(
                        deleteConfirmation.text, dialog.run.cleanupToken)
                }
                MButton {
                    objectName: "cancelQuarantineButton"
                    Layout.fillWidth: true
                    secondary: true
                    text: backend.localizedText(backend.language, "results.delete_cancel")
                    onClicked: {
                        dialog.deleteConfirming = false
                        deleteConfirmation.clear()
                        beginDeleteButton.forceActiveFocus()
                    }
                }
            }
        }
    }
}

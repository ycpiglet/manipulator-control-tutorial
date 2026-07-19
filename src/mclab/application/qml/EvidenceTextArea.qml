import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ScrollView {
    id: control
    property bool compact: false
    property bool editable: true
    property int maximumLength: 240
    property string inputObjectName: ""
    property string scrollerObjectName: ""
    property string scrollBarObjectName: ""
    property string placeholder: ""
    property string accessibleName: ""
    property string accessibleDescription: ""
    property Item tabTarget: null
    property alias text: editor.text
    signal revealRequested(var controlItem)

    function forceInputFocus() {
        editor.forceActiveFocus()
    }

    objectName: scrollerObjectName
    Layout.fillWidth: true
    contentWidth: availableWidth
    clip: true
    Accessible.role: Accessible.EditableText
    Accessible.name: control.accessibleName
    Accessible.description: control.accessibleDescription
    Accessible.focusable: true
    Accessible.focused: editor.activeFocus
    Accessible.editable: control.editable
    Accessible.multiLine: true
    Accessible.onPressAction: editor.forceActiveFocus()
    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
    ScrollBar.vertical: ScrollBar {
        id: verticalScrollBar
        objectName: control.scrollBarObjectName
        policy: ScrollBar.AsNeeded
        minimumSize: 0.25
        visible: editor.contentHeight > control.availableHeight + 0.5
        width: 10
        padding: 2
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        z: 2
        background: Rectangle {
            radius: 3
            color: "#E2E8F0"
        }
        contentItem: Rectangle {
            implicitWidth: 6
            implicitHeight: 24
            radius: 3
            color: verticalScrollBar.pressed ? "#334155" : "#64748B"
        }
    }
    background: Rectangle {
        radius: 7
        color: "#FFFFFF"
        border.width: editor.activeFocus ? 4 : 2
        border.color: editor.activeFocus ? "#FFDD00" : "#64748B"
        Rectangle {
            anchors.fill: parent
            anchors.margins: 3
            radius: 4
            color: "transparent"
            border.width: editor.activeFocus ? 2 : 0
            border.color: "#000000"
        }
    }
    TextArea {
        id: editor
        objectName: control.inputObjectName
        enabled: control.editable
        width: control.availableWidth
        height: Math.max(control.availableHeight, contentHeight)
        wrapMode: TextEdit.WordWrap
        placeholderText: control.placeholder
        placeholderTextColor: "#64748B"
        color: "#172033"
        font.pixelSize: control.compact ? 12 : 13
        selectByMouse: true
        KeyNavigation.priority: KeyNavigation.BeforeItem
        KeyNavigation.tab: control.tabTarget
        Accessible.ignored: true
        onActiveFocusChanged: {
            if (activeFocus)
                control.revealRequested(control)
        }
        onTextChanged: {
            if (length > control.maximumLength)
                remove(control.maximumLength, length)
        }
        background: null
    }
}

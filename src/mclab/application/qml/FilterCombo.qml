import QtQuick
import QtQuick.Controls

ComboBox {
    id: control
    property string filterName: ""
    property string filterDescription: ""
    property string displayPrefix: ""
    implicitWidth: 170
    implicitHeight: 48
    leftPadding: 12
    rightPadding: 30
    font.pixelSize: 14
    font.weight: Font.DemiBold
    focusPolicy: Qt.StrongFocus
    Accessible.name: filterName
    Accessible.description: filterDescription + " " + displayText

    contentItem: Text {
        text: control.displayPrefix + " · " + control.displayText
        color: "#172033"
        font: control.font
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }
    indicator: Text {
        anchors.right: parent.right
        anchors.rightMargin: 11
        anchors.verticalCenter: parent.verticalCenter
        text: "▼"
        color: "#172033"
        font.pixelSize: 11
        font.bold: true
    }
    background: Rectangle {
        radius: 8
        color: control.down ? "#EAF1FF" : "#FFFFFF"
        border.width: control.activeFocus ? 4 : 2
        border.color: control.activeFocus ? "#FFDD00" : "#64748B"
        Rectangle {
            anchors.fill: parent
            anchors.margins: 3
            radius: 5
            color: "transparent"
            border.width: control.activeFocus ? 2 : 0
            border.color: "#000000"
        }
    }
    delegate: ItemDelegate {
        width: control.width
        height: 44
        text: modelData
        font: control.font
        highlighted: control.highlightedIndex === index
        contentItem: Text {
            text: parent.text
            color: "#172033"
            font: parent.font
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle { color: parent.highlighted ? "#DBEAFE" : "#FFFFFF" }
    }
    popup: Popup {
        y: control.height + 4
        width: control.width
        implicitHeight: contentItem.implicitHeight + 8
        padding: 4
        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: control.popup.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
        }
        background: Rectangle {
            color: "#FFFFFF"
            radius: 8
            border.color: "#64748B"
            border.width: 2
        }
    }
}

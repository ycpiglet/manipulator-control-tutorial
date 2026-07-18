import QtQuick

Rectangle {
    property bool shown: false
    visible: shown
    color: "transparent"
    radius: 8
    border.width: 4
    border.color: "#FFDD00"
    z: 100
    Rectangle {
        anchors.fill: parent
        anchors.margins: 3
        radius: 5
        color: "transparent"
        border.width: 2
        border.color: "#000000"
    }
}

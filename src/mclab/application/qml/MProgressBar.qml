import QtQuick
import QtQuick.Controls

ProgressBar {
    id: control
    property bool complete: value >= 1
    implicitHeight: 10

    background: Rectangle {
        implicitHeight: 10
        radius: 5
        color: "#D7DFEA"
    }
    contentItem: Item {
        implicitHeight: 10
        Rectangle {
            width: control.visualPosition * parent.width
            height: parent.height
            radius: 5
            color: control.complete ? "#16794B" : "#2563EB"
        }
    }
}

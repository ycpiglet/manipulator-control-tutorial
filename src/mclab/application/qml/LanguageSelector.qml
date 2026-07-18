import QtQuick
import QtQuick.Controls

ComboBox {
    id: control
    model: ["한국어", "English"]
    implicitWidth: 152
    implicitHeight: 48
    leftPadding: 16
    rightPadding: 40
    font.pixelSize: 16
    font.weight: Font.Bold
    focusPolicy: Qt.StrongFocus
    Accessible.description: backend.language === "ko"
                            ? "앱 표시 언어를 한국어 또는 영어로 바꿉니다."
                            : "Changes the app language between Korean and English."

    contentItem: Text {
        text: control.displayText
        color: "#172033"
        font: control.font
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideNone
    }
    indicator: Text {
        anchors.right: parent.right
        anchors.rightMargin: 15
        anchors.verticalCenter: parent.verticalCenter
        text: "▼"
        color: "#172033"
        font.pixelSize: 13
        font.bold: true
    }
    background: Rectangle {
        radius: 8
        color: control.down ? "#EAF1FF" : "#FFFFFF"
        border.width: control.activeFocus ? 4 : 2
        border.color: control.activeFocus ? "#FFDD00" : "#64748B"
        Rectangle {
            anchors.fill: parent
            anchors.margins: 2
            radius: 6
            color: "transparent"
            border.width: control.activeFocus ? 2 : 0
            border.color: "#000000"
        }
    }
    delegate: ItemDelegate {
        width: control.width
        height: 48
        text: modelData
        font: control.font
        highlighted: control.highlightedIndex === index
        contentItem: Text {
            text: parent.text
            color: "#172033"
            font: parent.font
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle {
            color: parent.highlighted ? "#DBEAFE" : "#FFFFFF"
        }
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

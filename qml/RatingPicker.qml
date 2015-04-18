import QtQuick 2.0
import QtQuick.Controls 1.1

Item { id: ratingPicker
    property alias labelText: label.text
    property variant values: ["a", "b", "c"]
    property int currentIndex: 0
    property variant value: values[currentIndex]

    width: content.width + 10
    height: label.height + 10

    Row { id: content
        spacing: 5
        anchors{ margins: 5; centerIn: parent}

        Text { id: label
            color: "white"
            text: "<label>"
            font.bold: ratingPicker.activeFocus
        }

        Repeater { id: choices
            model: values
            Text {
                property bool selected: index == currentIndex
                text: modelData
                color: selected ? "white" : "lightGray"
                font.bold: selected
                font.italic: !selected
            }
        }
    }

    Keys.onLeftPressed: {
        if (currentIndex > 0) { currentIndex--; }
        event.accepted = true;
    }
    Keys.onRightPressed: {
        if (currentIndex < values.length - 1) { currentIndex++; }
        event.accepted = true;
    }
}

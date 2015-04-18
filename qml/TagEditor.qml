import QtQuick 2.0
import QtQuick.Controls 1.1
import QtQuick.Layouts 1.1

FocusScope {
    width: content.width
    height: content.height

    Rectangle { id: background
        color: "black"
        opacity: 0.5
        anchors.fill: parent
    }

    Column { id: content
        anchors.centerIn: parent
        RatingPicker { id: overallPicker
            labelText: "overall"
            focus: true

            KeyNavigation.down: stylePicker
            KeyNavigation.tab: stylePicker
        }
        RatingPicker { id: stylePicker
            labelText: "style"
            KeyNavigation.up: overallPicker
            KeyNavigation.backtab: overallPicker
            KeyNavigation.down: subjectPicker
            KeyNavigation.tab: subjectPicker
        }
        RatingPicker { id: subjectPicker
            labelText: "subject"
            KeyNavigation.up: stylePicker
            KeyNavigation.backtab: stylePicker
        }
    }

    // TODO: content tag booleans
}

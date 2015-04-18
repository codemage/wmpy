import QtQuick 2.0

Rectangle { id: currentTagsBackground
    property variant image: null
    property variant allTags: null
    color: "#CC000000"
    width: currentTags.width + 20
    height: currentTags.height + 20
    visible: image != null
    FocusScope { anchors.fill: parent; id: currentTagsFocus; Column { id: currentTags
        anchors.centerIn: parent;
        spacing: 10;
        Repeater {
            id: currentTagsRepeater
            model: image != null ? image.tags : []
            delegate: Text {
                color: "white";
                text: modelData.name ? modelData.name : modelData
            }
            property variant editor: Component { Text {
                text: modelData
                enabled: true
                focus: index == 0
                color: focus || tagSelect.containsMouse ? "yellow" : "white"
                font.bold: hasTag(modelData)
                horizontalAlignment: Text.AlignHCenter
                KeyNavigation.up: index > 0 ? currentTagsRepeater.itemAt(index+1) : currentTagsRepeater.itemAt(currentTagsRepeater.count - 1)
                KeyNavigation.down: index < (currentTagsRepeater.count - 1) ? currentTagsRepeater.itemAt(index+1) : currentTagsRepeater.itemAt(0)
                function toggle() { if (view.image.toggleTag) view.image.toggleTag(modelData); }
                Keys.onLeftPressed: { toggle(); }
                Keys.onRightPressed: { toggle(); }
                MouseArea {
                    id: tagSelect
                    hoverEnabled: true
                    x: -10; width: currentTagsBackground.width
                    y: -5; height: parent.height+10
                    onClicked: { toggle(); }
                }
            }}
        }
    }}
    states: State { name: "edit";
        PropertyChanges { target: currentTagsRepeater
            model: allTags
            delegate: currentTagsRepeater.editor
        }
        PropertyChanges { target: currentTagsBackground
            color: "#EE000000"
        }
        PropertyChanges { target: currentTagsFocus
            focus: true
        }
    }
}

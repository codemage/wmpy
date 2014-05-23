import QtQuick 2.0

Rectangle { id: currentTagsBackground
    property variant image: null
    property variant allTags: null
    color: "#CC000000"
    width: currentTags.width + 20
    height: currentTags.height + 20
    visible: image != null
    Column { id: currentTags
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
                color: tagSelect.containsMouse ? "yellow" : "white"
                font.bold: hasTag(modelData)
                horizontalAlignment: Text.AlignHCenter
                MouseArea {
                    id: tagSelect
                    hoverEnabled: true
                    x: -10; width: currentTagsBackground.width
                    y: -5; height: parent.height+10
                    onClicked: {
                        if (image.toggleTag) {
                            image.toggleTag(modelData);
                        }
                        // keyboardHandler.focus = true;
                    }
                }
            }}
        }
    }
    states: State { name: "edit";
        PropertyChanges { target: currentTagsRepeater
            model: allTags
            delegate: currentTagsRepeater.editor
        }
    }
}

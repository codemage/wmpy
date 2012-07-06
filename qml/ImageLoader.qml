import QtQuick 1.1

Loader { id: imagewrapper
    property variant image: null
    property variant size: Qt.size(1, 1)
    property int fillMode: Image.PreserveAspectFit
    property variant sourceSize: null
    property bool loaded: Boolean(image && image.size && image.size.width)
    onImageChanged: { if (image) size = image.size; }
    sourceComponent: image && image.size ? filled : empty
    Component { id: empty; Text {
        text: "(nothing loaded)"
        anchors.centerIn: parent
    }}
    Component { id: filled; Image { id: imageview
        anchors.fill: parent
        fillMode: parent.fillMode
        smooth: true
        cache: false
        asynchronous: true
        source: image.path
        onStatusChanged: {
            if (imageview.status == Image.Ready) {
                if (image.size.width == 0 && imageview.state == "") {
                    image.size = imageview.sourceSize;
                    imagewrapper.size = image.size;
                }
            }
        }
        states: State { name: "shrunk"
            PropertyChanges { target: imageview;
                when: imagewrapper.size.width != 0 && parent.sourceSize
                sourceSize: parent.sourceSize
            }
        }
    }}
}

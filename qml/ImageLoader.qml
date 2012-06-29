import QtQuick 1.1

Loader {
    id: imagewrapper
    property variant image: modelData
    property int fillMode: Image.PreserveAspectFit
    property variant sourceSize: null
    sourceComponent: Image {
        id: imageview
        anchors.centerIn: parent
        fillMode: parent.fillMode
        smooth: true
        cache: false
        asynchronous: true
        source: image.path
        visible: image.path != "nothing_loaded.png"
        onStatusChanged: {
            if (imageview.status == Image.Ready) {
                if (image.size.width == 0 && imageview.state == "") {
                    image.size = imageview.sourceSize;
                }
            }
        }
        states: State { name: "shrunk"
            PropertyChanges { target: imageview;
                when: image.size.width != 0 && parent.sourceSize
                sourceSize: parent.sourceSize
            }
        }
    }
}

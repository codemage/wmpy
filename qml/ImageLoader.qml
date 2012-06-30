import QtQuick 1.1

Loader {
    id: imagewrapper
    property variant image: null
    property variant size: Qt.size(1, 1)
    property int fillMode: Image.PreserveAspectFit
    property variant sourceSize: null
    onImageChanged: { if (image) size = image.size; }
    sourceComponent: Image {
        id: imageview
        anchors.fill: parent
        fillMode: parent.fillMode
        smooth: true
        cache: false
        asynchronous: true
        source: image ? image.path : "nothing_loaded.png"
        visible: Boolean(image)
        onStatusChanged: {
            if (imageview.status == Image.Ready) {
                if (image && image.size.width == 0 && imageview.state == "") {
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
    }
}

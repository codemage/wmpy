import QtQuick 1.1

Loader {
    id: imagewrapper
    property variant image: modelData
    property int fillMode: Image.PreserveAspectFit
    property variant sourceSize: null
    Component { id: unsized
        Image { // XXX UNTESTED
            id: imageview
            anchors.centerIn: parent
            fillMode: parent.fillMode
            smooth: true
            cache: false
            asynchronous: true
            source: image.path
            visible: image.path != "nothing_loaded.png"
            onStatusChanged: {
                if (imageview.status == Image.Ready)
                    image.size = imageview.sourceSize;
            }
        }
    }
    Component { id: sized
        Image {
            id: imageview
            anchors.centerIn: parent
            fillMode: parent.fillMode
            smooth: true
            cache: false
            asynchronous: true
            source: image.path
            visible: image.path != "nothing_loaded.png"
            sourceSize: parent.sourceSize
        }
    }
    sourceComponent: image.size && imagewrapper.sourceSize ? sized : unsized
}

import QtQuick 2.0

Loader { id: imagewrapper
    property variant image: null
    property variant size: Qt.size(1, 1)
    property int fillMode: Image.PreserveAspectFit
    property variant sourceSize: null
    property bool imageLoaded: Boolean(image && image.size && image.size.width && image.path)
    property bool loaded: Boolean(imageLoaded && status == Loader.Ready && item.status == Image.Ready)
    // the property here just ensures that onComplete only fires once:
    property bool isComplete: false  // whether the initial load is finished
    signal complete // fires when initial load is completed (successful or not)
    onIsCompleteChanged: { if (isComplete) imagewrapper.complete(); }
    onStatusChanged: { if (status == Loader.Error) isComplete = true; }
    onImageChanged: { if (image) size = image.size; }
    sourceComponent: image && image.size ? filled : empty
    Component { id: empty; Text {
        text: "(nothing loaded)"
        anchors.centerIn: parent
    }}
    Component { id: filled; Image { id: imageview
        // parent and image may be null after component is deparented by loaded-ness change
        anchors.fill: parent
        fillMode: parent ? parent.fillMode : Image.PreserveAspectFit
        smooth: true
        cache: false
        asynchronous: true
        source: image ? image.url : ""
        onStatusChanged: {
            if (imageview.status == Image.Ready) {
                if (image.size.width == 0 && imageview.state == "") {
                    image.size = imageview.sourceSize;
                    imagewrapper.size = image.size;
                }
            }
            if (imageview.status == Image.Ready || imageview.status == Image.Error) {
                imagewrapper.isComplete = true
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

// import QtQuick 1.0 // to target S60 5th Edition or Maemo 5
import QtQuick 1.1
//import QtDesktop 0.1

Rectangle {
    id: view
    color: "black"
    width: 500
    height: 500
    focus: true
    
    property string tagName: ""
    property variant tag: tagdb.loaded && view.tagName ? tagdb.getTag(view.tagName) : false
    property variant images: view.tag ? view.tag.images : [
        {"image": {"tags":[{"name": "no image loaded"}]}, "path": "nothing_loaded.png"}
        ]
    property variant image: list.currentItem.image

    function next() { list.incrementCurrentIndex(); }
        // list.positionViewAtIndex(list.currentIndex+1, ListView.Center); }
    function prev() { list.decrementCurrentIndex(); }
        // list.positionViewAtIndex(list.currentIndex-1, ListView.Center); }
    function random() { var target = Math.floor(Math.random()*list.count);
        list.positionViewAtIndex(target, ListView.Center);
        list.currentIndex = target;
        }

    ListView {
        anchors.fill: parent
        id: list
        keyNavigationWraps: true
        cacheBuffer: parent.width*3
        orientation: ListView.Horizontal
        highlightMoveSpeed: view.width*100
        highlightMoveDuration: 100
        preferredHighlightBegin: (view.width - list.currentItem.width) / 2
        preferredHighlightEnd: list.preferredHighlightBegin
        highlightRangeMode: ListView.StrictlyEnforceRange
        property bool completed: false
        Component.onCompleted: { list.completed = true }
        delegate: Loader {
            height: view.height
            width: view.width
            id: imagewrapper
            property variant image: modelData
            Connections { target: image; onSizeChanged: resize() }
            Connections { target: view; onHeightChanged: resize()
                                        onWidthChanged: resize() }
            onStatusChanged: resize()
            function resize() {
                if (!image.size) { return; }
                if (imagewrapper.status != Loader.Ready) { return; }
                var scale = 1.0*view.height/image.size.height;
                if (image.size.width * scale > view.width - 10)
                    scale = 1.0*(view.width - 10)/image.size.width;

                var targetWidth = Math.floor(image.size.width * scale) + 10
                if (imagewrapper.width == targetWidth)
                    return;
                imagewrapper.width = targetWidth;
            }
            sourceComponent: Image {
                id: imageview
                anchors.centerIn: parent
                smooth: true
                cache: false
                asynchronous: true
                fillMode: Image.PreserveAspectFit
                source: image.path
                visible: image.path != "nothing_loaded.png"
                onStatusChanged: {
                    if (imageview.status == Image.Ready)
                        image.size = imageview.sourceSize;
                }
            }
        }
        model: view.images
        MouseArea {
            anchors.fill: parent
            onClicked: next()
        }
    }

    Rectangle {
        anchors.fill: leftColumn
        color: "#80000000"
    }
    Column {
        id: leftColumn
        anchors {
            left: parent.left; bottom: parent.bottom
        }
        Text { 
            color: "white"
            text: view.tag ? list.currentIndex + "/" + list.count : "0/0"
        }
        Repeater {
            delegate: Text {
                color: "white"; text: modelData
                font.bold: modelData == view.tagName
                MouseArea {
                    anchors{ left: parent.left; top: parent.top; bottom: parent.bottom }
                    width: leftColumn.width
                    onClicked: view.tagName = modelData
                }
            }
            model: Object.keys(tagdb.tags)
        }
    }
    Rectangle {
        anchors { verticalCenter: rightColumn.verticalCenter;
                  right: rightColumn.right;}
        width: Math.max(rightColumn.width, 50);
        height: Math.max(rightColumn.height, 100);
        color: "#80000000"
    }
    Column {
        id: rightColumn
        anchors { right: parent.right;
                  verticalCenter: parent.verticalCenter}
        Repeater {
            id: tagview
            model: view.image.tags
            delegate: Text {color: "white"; text: modelData.name}
        }
    }
    Text {
        id: loadingIndicator
        text: "Loading..."
        color: "white"
        anchors.centerIn: parent
        height: parent.height/7
        font.pixelSize: loadingIndicator.height
        visible: tagdb.loading
    }
    Keys.onReleased: {
        if (event.key == Qt.Key_Return) {
            app.fullScreen ? app.showNormal() : app.showFullScreen();
        } else if (event.key == Qt.Key_Escape || event.key == Qt.Key_Q) {
            Qt.quit();
        } else if (event.key == Qt.Key_Right || event.key == Qt.Key_Space) {
            next();
        } else if (event.key == Qt.Key_Left) {
            prev();
        } else if (event.key == Qt.Key_Z) {
            random();
        } else {
            console.log(event.key);
        }
    }
}


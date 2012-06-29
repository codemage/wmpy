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
    property variant images: view.tag ? view.tag.images :
        [{"image":
            {"tags":[{"name": "no image loaded"}]},
             "path": "nothing_loaded.png",
             "hasTag": function(tag) { return false; }
        }]
    property variant image: list.currentItem.image
    Connections { target: tagdb;
        onLoadedChanged: {
            if (tagdb.loaded) {
                if (view.tagName == "")
                    view.tagName = Object.keys(tagdb.tags)[0];
            } else { view.tagName = "" }
        }
    }

    function next() { list.incrementCurrentIndex(); }
    function prev() { list.decrementCurrentIndex(); }
    function random() { var target = Math.floor(Math.random()*list.count);
        list.positionViewAtIndex(target, ListView.Center);
        list.currentIndex = target;
        }

    ListView { id: list
        anchors.fill: parent
        keyNavigationWraps: true
        cacheBuffer: parent.width*2
        orientation: ListView.Horizontal
        highlightMoveSpeed: view.width*5
        highlightMoveDuration: 100
        preferredHighlightBegin: (view.width - list.currentItem.width) / 2
        preferredHighlightEnd: list.preferredHighlightBegin
        highlightRangeMode: ListView.StrictlyEnforceRange
        property bool completed: false
        Component.onCompleted: { list.completed = true }
        delegate: ImageLoader { id: imageloader
            height: view.height
            width: {
                if (!image.size.width) return view.width;
                var ry = 1.0*view.height/image.size.height;
                var rx = 1.0*view.width/image.size.width;
                var scale = Math.min(rx, ry);
                return Math.floor(image.size.width * scale) + 10;
            }
        }
        model: view.images
        MouseArea {
            anchors.fill: parent
            onClicked: next()
        }
    }

    Rectangle { anchors.fill: leftColumn; color: "#80000000" }
    Column { id: leftColumn
        anchors { left: parent.left; bottom: parent.bottom }
        Text { text: view.tag ? list.currentIndex + "/" + list.count : "0/0"
            color: "white"
        }
        Repeater { id: listAllTags
            model: Object.keys(tagdb.tags)
            delegate: Text {
                color: "white"; text: modelData
                font.bold: modelData == view.tagName
                MouseArea {
                    height: parent.height
                    width: leftColumn.width
                    onClicked: view.tagName = modelData
                }
            }
        }
    }
    Rectangle { id: rightColumn
        anchors { verticalCenter: parent.verticalCenter;
                  right: parent.right;}
        color: "#80000000"
        width: currentTagsList.width + 20;
        height: currentTagsList.height + 20;
        Column { id: currentTagsList
            anchors { margins: 10; left: parent.left; top: parent.top }
            Repeater {
                id: tagview
                model: view.image.tags
                delegate: Text {color: "white"; text: modelData.name}
            }
        }
    }
    Text { id: loadingIndicator
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
            if (view.state == "") {
                Qt.quit();
            } else {
                view.state = "";
            }
        } else if (event.key == Qt.Key_Right || event.key == Qt.Key_Space) {
            next();
        } else if (event.key == Qt.Key_Left) {
            prev();
        } else if (event.key == Qt.Key_T && view.tag) {
            view.state = (view.state == "" ? "setTags" : "");
        } else if (event.key == Qt.Key_Z) {
            random();
        } else {
            console.log(event.key);
            return;
        }
        event.accepted = true;
    }
    function hasTag(tagname) {
        if (!view.tag || !view.image) return false;
        for (var i = 0; i < view.image.tags.length; i++) {
            var tag = view.image.tags.data(i);
            if (tag.name == tagname)
                return true;
        }
        return false;
    }
    Rectangle { id: tagEditor
        anchors.centerIn: parent
        visible: false
        color: "#CC000000"
        width: tagEditorList.width + 30
        height: tagEditorList.height + 30
        Column { id: tagEditorList; Repeater {
            model: Object.keys(tagdb.tags)
            delegate: Text {
                text: modelData
                color: tagSelect.containsMouse ? "yellow" : "white"
                font.bold: hasTag(modelData)
                horizontalAlignment: Text.AlignHCenter
                MouseArea {
                    id: tagSelect
                    hoverEnabled: true
                    x: -15; width: tagEditor.width
                    y: -5; height: parent.height+10
                    onClicked: view.image.toggleTag(modelData)
                }
            }
        } anchors.centerIn: parent; spacing: 10 }
    }
    states: [
    State { name: "setTags"
        PropertyChanges { target: tagEditor; visible: true }
    }
    ]
}


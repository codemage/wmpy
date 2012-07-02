import QtQuick 1.1
//import QtDesktop 0.1

Rectangle {
    id: view
    color: "black"
    width: 500
    height: 500
    focus: true
    
    function z(obj, prop) { return obj ? obj[prop] : 0; }

    property string tagName: ""
    property real zoomLevel: 1.5
    property variant tag: tagdb.loaded && view.tagName ? tagdb.getTag(view.tagName) : false
    property variant images: view.tag ? view.tag.images : []
    property variant image: z(list.currentItem, 'image')

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

    Flickable { id: zoomed
        visible: false
        anchors.fill: parent
        contentWidth: zoomLoader.width
        contentHeight: zoomLoader.height
        boundsBehavior: Flickable.StopAtBounds
        ImageLoader { id: zoomLoader
            image: view.image
            width: Math.max(size.width*zoomLevel, view.width)
            height: Math.max(size.height*zoomLevel, view.height)
        }
    }
    ListView { id: list
        model: view.images
        anchors.fill: parent
        keyNavigationWraps: true
        cacheBuffer: parent.width*2
        orientation: ListView.Horizontal
        highlightMoveSpeed: view.width*5
        highlightMoveDuration: 100
        preferredHighlightBegin: list.currentItem && list.currentItem.width
            ? (view.width - list.currentItem.width) / 2
            : 0
        preferredHighlightEnd: list.preferredHighlightBegin
        highlightRangeMode: ListView.StrictlyEnforceRange
        spacing: 10
        delegate: Flickable { id: listEntry
            property variant image: listLoader.image
            height: view.height
            width: listLoader.width
            contentWidth: listLoader.width
            contentHeight: listLoader.height
            boundsBehavior: Flickable.StopAtBounds
            ImageLoader { id: listLoader
                image: modelData
                function zoom() {
                    if (!image || !image.size.width) return 1;
                    var s = image.size;
                    var aspect = s.width/s.height;
                    var ry = view.height/s.height;
                    var rx = view.width/s.width;
                    if (aspect < 1 && view.zoomLevel > 1)
                        ry = view.height/(s.height/view.zoomLevel);
                    return Math.min(rx, ry);
                }
                width: listLoader.size.width
                    ? Math.min(view.width, listLoader.size.width * zoom())
                    : view.width*0.75
                height: Math.max(view.height, listLoader.size.height * zoom());
            }
            onContentHeightChanged: {
                listEntry.contentY = (listEntry.contentHeight - view.height)/2
            }
            MouseArea {
                anchors.fill: parent
                onClicked: next()
            }
        }
    }

    Rectangle { anchors.fill: leftColumn; color: "#80000000" }
    Column { id: leftColumn
        anchors { left: parent.left; bottom: parent.bottom }
        Text { text: view.zoomLevel; color: "white" }
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
            view.state = (view.state == "setTags" ? "" : "setTags");
        } else if (event.key == Qt.Key_R) {
            random();
        } else if (event.key == Qt.Key_Z) {
            view.state = (view.state == "zoomed" ? "" : "zoomed");
        } else if (event.key == Qt.Key_Up) {
            zoomLevel += 0.25;
        } else if (event.key == Qt.Key_Down) {
            zoomLevel -= 0.25;
        } else if (event.key == Qt.Key_X) {
            zoomLevel =  1.5;
        } else {
            console.log(event.key);
            return;
        }
        event.accepted = true;
    }
    function hasTag(tagname) {
        if (!view.image) return false;
        for (var i = 0; i < view.image.tags.length; i++) {
            var tag = view.image.tags.get(i);
            if (tag.name == tagname)
                return true;
        }
        return false;
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
                model: view.image ? view.image.tags : []
                delegate: Text {color: "white"; text: modelData.name}
            }
        }
    }
    Rectangle { id: tagEditor
        anchors { verticalCenter: parent.verticalCenter; right: parent.right }
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
    State { name: "setTags";
        PropertyChanges { target: tagEditor; visible: true }
        PropertyChanges { target: rightColumn; visible: false }
    },
    State { name: "zoomed";
        PropertyChanges { target: zoomed; visible: true }
        PropertyChanges { target: list; visible: false }
    }
    ]
}


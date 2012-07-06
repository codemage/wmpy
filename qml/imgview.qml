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
    property real zoomLevel: 1
    property variant tag: tagdb.loaded && view.tagName ? tagdb.getTag(view.tagName) : false
    property variant images: []
    property variant image: z(list.currentItem, 'image')

    onTagChanged: {
        if (tagdb.loaded && view.tag != "")
            images = tagdb.getImageList(view.tagName)
    }
    Connections { target: tagdb;
        onLoadedChanged: {
            view.tagName = ""
            if (tagdb && tagdb.loaded) {
                images = tagdb.getImageList('len(tags)==0')
            }
        }
    }

    function next() { list.incrementCurrentIndex(); }
    function prev() { list.decrementCurrentIndex(); }
    function show(target) {
        list.positionViewAtIndex(target, ListView.Center);
        list.currentIndex = target;
        }
    function random() { show(Math.floor(Math.random()*list.count)); }

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
        width: parent.width
        height: parent.height
        Behavior on height { SmoothedAnimation { duration: 150 } }
        keyNavigationWraps: true
        cacheBuffer: width*2
        orientation: ListView.Horizontal
        highlightMoveSpeed: width*5
        highlightMoveDuration: 100
        preferredHighlightBegin: list.currentItem && list.currentItem.width
            ? (list.width - list.currentItem.width) / 2
            : 0
        preferredHighlightEnd: list.preferredHighlightBegin
        highlightRangeMode: ListView.StrictlyEnforceRange
        spacing: 10
        clip: true
        delegate: Flickable { id: listEntry
            property variant image: loader ? loader.image : 0
            anchors { top: parent.top; bottom: parent.bottom }
            width: view.z(loader, 'width')
            contentWidth: view.z(loader, 'width')
            contentHeight: view.z(loader, 'height')
            boundsBehavior: Flickable.StopAtBounds
            ImageLoader { id: loader
                image: modelData
                function zoom() {
                    if (!loader.loaded) return 1;
                    var s = image.size;
                    var aspect = s.width/s.height;
                    var ry = list.height/s.height;
                    var rx = list.width/s.width;
                    if (view.zoomLevel > 1)
                        ry = list.height/(s.height/view.zoomLevel);
                    return Math.min(rx, ry);
                }
                width: loader.loaded
                    ? Math.min(list.width, loader.size.width * zoom())
                    : list.width*0.75
                height: loader.loaded
                    ? Math.max(list.height, loader.size.height * zoom())
                    : list.height
            }
            onContentHeightChanged: {
                listEntry.contentY = (listEntry.contentHeight - list.height)/2
            }
            MouseArea {
                anchors.fill: parent
                onClicked: next()
            }
            states: State { name: "scratch"
                ParentChange { target: loader; parent: view }
                PropertyChanges { target: listEntry; width: 0 }
                PropertyChanges { target: loader;
                    x: view.width/2-scratch.height;
                    y: view.height * 0.7;
                    width: scratch.height; height: scratch.height
                }
            }
            transitions: Transition { from: ""; to: "scratch"
                SequentialAnimation {
                    PropertyAction { target: list
                        property: "highlightRangeMode"
                        value: ListView.NoHighlightRange; }
                    ParallelAnimation {
                        NumberAnimation { target: loader; duration: 200;
                            properties: "x,y,width,height" }
                        NumberAnimation { target: listEntry; duration: 200;
                            properties: "width" }
                    }
                    ScriptAction { script: {
                        var image = loader.image;
                        images.remove(index);
                        scratch.model.append({'asdf': image});
                        loader.destroy();
                    }}
                    PropertyAction { target: list
                        property: "highlightRangeMode"
                        value: ListView.StrictlyEnforceRange; }
                }
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
                if (view.state != "rearrange") 
                    view.state = "";
                // TODO: allow Q to undo a rearrange
            }
        } else if (event.key == Qt.Key_T) {
            view.state = (view.state == "setTags" ? "" : "setTags");
        } else if (event.key == Qt.Key_R) {
            random();
        } else if (event.key == Qt.Key_Z) {
            view.state = (view.state == "zoomed" ? "" : "zoomed");
        } else if (event.key == Qt.Key_X) {
            zoomLevel =  1;
        } else if (event.key == Qt.Key_Space) {
            next();
        } else if (event.key == Qt.Key_Right) {
            next();
        } else if (event.key == Qt.Key_Left) {
            prev();
        } else if (event.key == Qt.Key_Up) {
            if (view.state == "zoomed" || event.modifiers & Qt.ShiftModifier) {
                zoomLevel += 0.25;
            } else if (scratch.count > 0) {
                var scratchImages = [];
                for (var i = 0; i < scratch.count; i++) {
                    scratchImages.push(scratch.model.get(i).asdf);
                }
                scratch.model.clear();
                var curIndex = list.currentIndex;
                scratchClearTimer.targetIndex = curIndex;
                images.insert(curIndex, scratchImages);
                show(curIndex);
            }
        } else if (event.key == Qt.Key_Down) {
            if (view.state == "zoomed" || event.modifiers & Qt.ShiftModifier) {
                zoomLevel -= 0.25;
            } else if (list.count > 0) {
                list.currentItem.state = "scratch";
            }
        } else {
            console.log(event.key);
            return;
        }
        event.accepted = true;
    }
    function hasTag(tagname) {
        if (!view.image || !view.image.tags) return false;
        
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
        width: tagEditorList.width + 20
        height: tagEditorList.height + 20
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
                    x: -10; width: tagEditor.width
                    y: -5; height: parent.height+10
                    onClicked: {
                        if (view.image.toggleTag) {
                            view.image.toggleTag(modelData);
                        }
                    }
                }
            }
        } anchors.centerIn: parent; spacing: 10 }
    }
    Repeater { id: scratch
        visible: false
        model: ListModel {}
        anchors.bottom: parent.bottom
        height: parent.height * 0.3
        width: parent.width

        delegate: ImageLoader { id: scratchitem
            y: scratch.y
            height: scratch.height
            width: Math.min(scratch.height, scratch.width/scratch.count)
            x: (scratch.width - width*scratch.count)/2 + width*index
            image: asdf
        }
    }
    states: [
    State { name: "setTags";
        PropertyChanges { target: tagEditor; visible: true }
        PropertyChanges { target: rightColumn; visible: false }
    },
    State { name: "zoomed";
        PropertyChanges { target: zoomed; visible: true }
        PropertyChanges { target: list; visible: false }
    },
    State { name: "rearrange";
        when: scratch.model.count > 0
        PropertyChanges { target: list; height: view.height*0.7 }
        PropertyChanges { target: scratch; visible: true }
    }
    ]
}


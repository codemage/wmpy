import QtQuick 1.1
//import QtDesktop 0.1

// in context from Python:
// tagdb -- QTagDB instance
// viewProxy -- has getView which returns ImgView (indirection avoids crash-causing reference loop)

Rectangle {
    id: view
    color: "black"
    width: 500
    height: 500

    function z(obj, prop) { return obj ? obj[prop] : 0; }
    function sorted(x) { x.sort(); return x; }
    function info(x) { console.log(x, sorted(Object.keys(x))); }

    property string tagName: ""
    property string tagExpr: tagdb.startingTagExpr
    property real zoomLevel: 1
    property variant tag: tagdb.loaded && view.tagName ? tagdb.getTag(view.tagName) : false
    property variant images: []
    property variant image: (tagdb.loaded && list.currentIndex >= 0) ? view.images.get(list.currentIndex) : null
    property variant scratchLoader: null
    onImageChanged: { console.log("current image: ", image ? image.name : "None"); }

    function reloadImages() {
        if (tagdb.hasTag(view.tagExpr)) {
            view.tagName = view.tagExpr;
            tagExprEdit.text = "<custom tag expression>";
        } else {
            view.tagName = "";
            tagExprEdit.text = view.tagExpr;
        }
        view.images = tagdb.getImageList(view.tagExpr);
    }
    onTagExprChanged: {
        if (tagdb.loaded) {
            reloadImages();
        }
    }
    Connections { target: tagdb;
        onLoadedChanged: {
            reloadImages();
        }
    }

    function next() { list.incrementCurrentIndex(); }
    function prev() { list.decrementCurrentIndex(); }
    function show(target) {
        list.positionViewAtIndex(target, ListView.Center);
        list.currentIndex = target;
        }
    function random() { show(Math.floor(Math.random()*list.count)); }

    ImageList { id: list
        images: view.images
    }
    Component { id: movedListImage; Item { id: movedImageManager
        property Item listEntry
        property Item loader
        property int index: -1
        property Item scratchItem
        Component.onCompleted: {
            loader = listEntry.loader;
            if (loader.parent != view) {
                var image = loader.image;
                var scratchIndex = scratch.model.count;
                scratch.model.append({'scratchImage': image});
                scratchItem = scratch.itemAt(scratchIndex);
                moveToScratch.start();
            } else {
                scratchItem = loader; // suppresses warnings when parsing animation
                movedImageManager.destroy();
            }
        }

        SequentialAnimation { id: moveToScratch
            PropertyAction { target: list
                property: "highlightRangeMode"
                value: ListView.NoHighlightRange; }
            ParentAnimation { target: loader; newParent: view; }
            ParallelAnimation {
                NumberAnimation { target: loader; property: "x";
                    duration: 200;
                    to: scratchItem.x }
                    // to: view.width/2-scratch.height; }
                NumberAnimation { target: loader; property: "y";
                    duration: 200;
                    to: view.height * 0.7; }
                NumberAnimation { target: loader; property: "width";
                    duration: 200;
                    to: scratchItem.width; }
                NumberAnimation { target: loader; property: "height";
                    duration: 200;
                    to: scratchItem.height; }
                NumberAnimation { target: listEntry; property: "width";
                    duration: 200;
                    to: 0; }
                // TODO: animation to make space in scratch list somehow
            }
            ScriptAction { script: {
                images.remove(index);
                // TODO: wait to destroy loader until scratch version is loaded
                scratchItem.opacity = 1;
                loader.destroy();
                loader = null;
            }}
            PropertyAction { target: list
                property: "highlightRangeMode"
                value: ListView.StrictlyEnforceRange; }
            onRunningChanged: { if (!running) movedImageManager.destroy(); }
        }
    }}
        
    Flickable { id: zoomed
        visible: false
        interactive: false
        x: list.currentItem
            ? list.currentItem.x - list.contentX
            : 0;
        width: view.z(list.currentItem, "width")
        // onWidthChanged: console.log("zw", zoomed.width)
        height: view.z(list.currentItem, "height")
        contentWidth: zoomLoader.width
        contentHeight: zoomLoader.height
        contentX: view.z(list.currentItem, "contentX");
        contentY: view.z(list.currentItem, "contentY");
        boundsBehavior: Flickable.StopAtBounds
        ImageLoader { id: zoomLoader
            image: view.image
            width: list.currentItem ? list.currentItem.contentWidth : 0;
            height: list.currentItem ? list.currentItem.contentHeight : 0;
            property real activeWidth:
                Math.max(size.width*zoomLevel, view.width)
            property real activeHeight:
                Math.max(size.height*zoomLevel, view.height)
        }
        // contentX/Y don't want to animate back to zero properly
        // track any nonzero values and use as the start for un-zoom animation:
        property real lastContentX: 0;
        onContentXChanged: if (contentX && state != "") lastContentX = contentX;
        property real lastContentY: 0
        onContentYChanged: if (contentY && state != "") lastContentY = contentY;
        states: [
        State { name: "active"
            PropertyChanges { target: zoomed
                x: 0
                width: view.width
                height: view.height
                visible: true
                interactive: true
            }
            PropertyChanges { target: zoomed; explicit: true
                contentX: (zoomLoader.activeWidth - view.width) / 2
                contentY: (zoomLoader.activeHeight - view.height) / 2
            }
            PropertyChanges { target: zoomLoader
                width: zoomLoader.activeWidth
                height: zoomLoader.activeHeight
            }
            PropertyChanges { target: list
                opacity: 0
            }
        }
        ]
        transitions: [
        Transition { from: ""; to: "active"
            SequentialAnimation {
                PropertyAction { target: zoomed; property: "visible" }
                ParallelAnimation {
                    NumberAnimation { targets: [zoomed,zoomLoader]
                        properties: "x,width,height"
                        duration: 200
                    }
                    NumberAnimation { target: zoomed
                        properties: "contentX, contentY"
                        duration: 200
                    }
                }
                PropertyAction { target: zoomed; property: "interactive" }
            }
        },
        Transition { from: "active"; to: ""
            SequentialAnimation {
                PropertyAction { target: zoomed; property: "interactive" }
                ParallelAnimation {
                    NumberAnimation { targets: [zoomed,zoomLoader]
                        properties: "x,width,height"
                        duration: 200
                    }
                    NumberAnimation { target: zoomed
                        property: "contentY"
                        duration: 200
                        from: zoomed.lastContentY
                    }
                    NumberAnimation { target: zoomed
                        property: "contentX"
                        duration: 200
                        from: zoomed.lastContentX
                    }
                }
                PropertyAction { target: zoomed; property: "visible" }
            }
        }
        ]
    }

    Rectangle { anchors.fill: leftColumn; color: "#80000000"; visible: leftColumn.visible; }
    // ^ not a child of leftColumn because leftColumn is sized based on its children
    Column { id: leftColumn
        anchors { left: parent.left; bottom: parent.bottom }
        visible: tagdb.loaded
        Text { text: "Zoom: " + view.zoomLevel; color: "white" }
        Text { text: list.count ? list.currentIndex + "/" + list.count : "0/0"
            color: "white"
        }
        TextInput { id: tagExprEdit;
            text: "untagged"
            font.bold: !focus && tagdb.loaded && text == view.tagExpr && !tagdb.hasTag(text)
            color: tagExprEdit.focus ? "black" : "white"
            width: Math.max(implicitWidth, 100)
            Rectangle { anchors.fill: parent; color: "white"; visible: parent.focus; z: -1; }
            onAccepted: {
                keyboardHandler.focus = true;
                view.tagExpr = text;
            }
            onFocusChanged: {
                if (focus && tagdb.hasTag(view.tagExpr))
                    text = view.tagExpr;
                if (!focus && tagdb.hasTag(text))
                    text = "<custom tag expression>";
            }
        }
        Repeater { id: listAllTags
            model: Object.keys(tagdb.tags)
            delegate: Text {
                color: "white"; text: modelData
                font.bold: modelData == view.tagName
                MouseArea {
                    height: parent.height
                    width: leftColumn.width
                    onClicked: { view.tagExpr = modelData; keyboardHandler.focus = true; }
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
    function hasTag(tagname) {
        if (!view.image || !view.image.tags) return false;

        for (var i = 0; i < view.image.tags.length; i++) {
            var tag = view.image.tags[i];
            if (tag == tagname)
                return true;
        }
        return false;
    }
    Rectangle { id: currentTagsBackground
        anchors { verticalCenter: parent.verticalCenter;
                  right: parent.right;}
        color: "#CC000000"
        width: currentTags.width + 20;
        height: currentTags.height + 20;
        Column { id: currentTags
            anchors.centerIn: parent;
            spacing: 10;
            Repeater {
                id: currentTagsRepeater
                model: view.image ? view.image.tags : []
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
                            if (view.image.toggleTag) {
                                view.image.toggleTag(modelData);
                            }
                            keyboardHandler.focus = true;
                        }
                    }
                }}
            }
            states: State { name: "edit";
                PropertyChanges { target: currentTagsRepeater
                    model: Object.keys(tagdb.tags)
                    delegate: currentTagsRepeater.editor
                }
            }
        }
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
            image: scratchImage
            opacity: 0 // set to 1 by moveToScratch animation
        }
    }
    states: [
    State { name: "rearrange";
        when: scratch.model.count > 0
        PropertyChanges { target: list; height: view.height*0.7 }
        PropertyChanges { target: scratch; visible: true }
    }
    ]
    Item { id: keyboardHandler; focus: true; Keys.onReleased: {
        var qtView = viewProxy.getView();
        if (event.key == Qt.Key_Return) {
            qtView.fullScreen ? qtView.showNormal() : qtView.showFullScreen();
        } else if (event.key == Qt.Key_Escape || event.key == Qt.Key_Q) {
            if (view.state == "") {
                Qt.quit();
            } else {
                if (view.state != "rearrange")
                    view.state = "";
                // TODO: allow Q to undo a rearrange
            }
        } else if (event.key == Qt.Key_T) {
            currentTags.state = (currentTags.state == "edit" ? "" : "edit");
        } else if (event.key == Qt.Key_R) {
            random();
        } else if (event.key == Qt.Key_Z) {
            zoomed.state = (zoomed.state == "active" ? "" : "active");
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
                    scratchImages.push(scratch.model.get(i).scratchImage);
                }
                scratch.model.clear();
                var curIndex = list.currentIndex;
                images.insert(curIndex, scratchImages);
                show(curIndex);
            }
        } else if (event.key == Qt.Key_Down) {
            if (view.state == "zoomed" || event.modifiers & Qt.ShiftModifier) {
                zoomLevel -= 0.25;
            } else if (list.count > 0) {
                movedListImage.createObject(view, {
                    listEntry: list.currentItem,
                    index: list.currentIndex,
                    })
            }
        } else {
            // console.log(event.key);
            return;
        }
        event.accepted = true;
    }}
}


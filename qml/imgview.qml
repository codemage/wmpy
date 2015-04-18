import QtQuick 2.0
//import QtDesktop 0.1

// in context from Python:
// tagdb -- QTagDB instance
// viewProxy -- has toggleFullscreen method (indirection avoids crash-causing reference loop)

Rectangle {
    id: view
    color: "black"
    width: 500
    height: 500

    function z(obj, prop) { return obj ? obj[prop] : 0; }
    function sorted(x) { x.sort(); return x; }
    function info(x) { console.log(x, sorted(Object.keys(x))); }

    property string tagExpr: tagdb.startingTagExpr
    property real zoomLevel: 1
    property variant curImages: []
    property variant allImages: null
    property variant images: view.curImages
    property variant image: (tagdb.loaded && list.currentIndex >= 0 && list.currentIndex < view.images.length) ? view.images.get(list.currentIndex) : null
    property variant scratchLoader: null
    // onCurImagesChanged: { console.log("current images changed, new count:", curImages ? curImages.length : "(null)"); }
    onImageChanged: { console.log("current image: ", image ? image.name : "None"); }

    function reloadImages() {
        //list.state = "";
        if (!view.allImages) {
            view.allImages = tagdb.getImageList("");
        }
        view.curImages = tagdb.getImageList(view.tagExpr);
    }
    onTagExprChanged: {
        if (tagdb.loaded) {
            reloadImages();
        }
    }
    Connections { target: tagdb;
        onLoadedChanged: {
            view.allImages = null;
            reloadImages();
        }
        onScanningChanged: {
            if (!tagdb.scanning) {
                view.allImages = tagdb.getImageList("")
            }
        }
    }

    ImageList { id: list
        property int lastIndex: -1
        property int nextIndex: -1
        images: view.images
        enabled: visible && opacity > 0
        onModelChanged: {
            if (list.nextIndex != -1) {
                list.positionViewAtIndex(list.nextIndex, ListView.Center);
                list.nextIndex = -1;
            }
        }
        states: [
        State { name: "VIEW_ALL"
            StateChangeScript { script: {
                list.lastIndex = list.currentIndex;
                if (list.lastIndex >= 0) {
                    list.nextIndex = allImages.find(curImages.get(list.lastIndex));
                }
            }}
            PropertyChanges { target: view; images: allImages; }
        },
        State { name: ""
            StateChangeScript { script: {
                list.nextIndex = list.lastIndex;
            }}
            PropertyChanges { target: view; images: curImages; }
        }
        ]
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
                // move already in progress
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
        enabled: visible
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
        Keys.onUpPressed: { zoomLevel += 0.25; }
        Keys.onDownPressed: { zoomLevel -= 0.25; }
        states: [
        State { name: "active"
            PropertyChanges { target: zoomed
                x: 0
                width: view.width
                height: view.height
                visible: true
                interactive: true
                focus: true
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
                PropertyAction { target: view; property: "focus"; value: true }
            }
        }
        ]
    }

    Rectangle { anchors.fill: leftColumn; color: "#80000000"; visible: leftColumn.visible; }
    // ^ not a child of leftColumn because leftColumn is sized based on its children
    Column { id: leftColumn
        anchors { left: parent.left; bottom: parent.bottom }
        visible: tagdb.loaded
        enabled: visible
        Text { text: "Zoom: " + view.zoomLevel; color: "white" }
        Text { text: list.count ? (list.currentIndex + 1) + "/" + list.count : "0/0"
            color: "white"
            visible: list.count > 0
        }
        Text { text: "Scanning..."; color: "red"; visible: tagdb.scanning; }

        TextInput { id: tagExprEdit;
            text: tagdb.startingTagExpr
            font.bold: !focus && tagdb.loaded && text == view.tagExpr && !tagdb.hasTag(text)
            color: tagExprEdit.focus ? "black" : "white"
            width: Math.max(implicitWidth, 100)
            Rectangle { anchors.fill: parent; color: "white"; visible: parent.focus; z: -1; }
            Keys.onReturnPressed: {
                // was onAccepted() but that does not consume the keypress if it moves focus?
                event.accepted = true;
                view.focus = true;
                view.tagExpr = text;
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
    ImageTagList {
        id: currentTags
        anchors { verticalCenter: parent.verticalCenter
                  right: parent.right;}
        image: view.image
        allTags: Object.keys(tagdb.tags)
    }
    Repeater { id: scratch
        visible: false
        enabled: visible
        model: ListModel {}
        anchors.bottom: parent.bottom
        height: parent.height * 0.3
        width: parent.width

        delegate: ImageLoader { id: scratchitem
            enabled: visible && opacity > 0
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

    // Keyboard handling:
    focus: true;
    Keys.forwardTo: [list];
    function debugKeys(event) {
        if (event.key === Qt.Key_G) {
            gc();
            tagdb.pyGarbageCollect();
        } else {
            return false;
        }
        event.accepted = true;
        return true;
    }
    function cutToScratch() {
        if (list.count == 0) return;
        movedListImage.createObject(view, {
            listEntry: list.currentItem,
            index: list.currentIndex,
            })
    }
    function pasteFromScratch() {
        if (scratch.count == 0) return;
        var scratchImages = [];
        for (var i = 0; i < scratch.count; i++) {
            scratchImages.push(scratch.model.get(i).scratchImage);
        }
        scratch.model.clear();
        var curIndex = list.currentIndex;
        images.insert(curIndex, scratchImages);
        list.positionViewAtIndex(curIndex);
    }
    Timer { id: slideshow
        interval: 15000
        repeat: true
        onTriggered: {
            console.log("next slide")
            list.incrementCurrentIndex()
        }
    }
    Keys.onPressed: {
        if (event.key === Qt.Key_Control) {
            currentTags.state = "edit";
        } else if (event.modifiers & Qt.ControlModifier) {
            return;
        } else if (event.key === Qt.Key_Return) {
            viewProxy.toggleFullscreen();
        } else if (event.key === Qt.Key_A && event.modifiers & Qt.ShiftModifier) {
            if (list.state == "") {
                list.state = "VIEW_ALL";
            } else {
                list.state = "";
            }
        } else if (event.key === Qt.Key_Escape || event.key === Qt.Key_Q) {
            if (view.state == "") {
                Qt.quit();
            } else {
                if (view.state == "rearrange")
                    pasteFromScratch();
                else
                    view.state = "";
            }
        } else if (event.key === Qt.Key_S) {
            if (event.modifiers & Qt.ShiftModifier) {
                if (slideshow.running) {
                    console.log("slideshow mode stopped");
                    slideshow.stop();
                } else {
                    console.log("slideshow mode started");
                    slideshow.start();
                }
            } else {
                tagdb.scan_for_untagged();
            }
        } else if (event.key === Qt.Key_T) {
            currentTags.state = (currentTags.state == "edit" ? "" : "edit");
        } else if (event.key === Qt.Key_Z) {
            zoomed.state = (zoomed.state == "active" ? "" : "active");
        } else if (event.key === Qt.Key_X) {
            zoomLevel =  1;
        } else if (event.key === Qt.Key_Up) {
            pasteFromScratch();
        } else if (event.key === Qt.Key_Down) {
            cutToScratch();
        } else {
            console.log("main view rejected key event: ", event.key, event.nativeScanCode, event.modifiers);
            return;
        }
        //console.log("main view accepted key event:", event.key)
        event.accepted = true;
    }
    Keys.onReleased: {
        if (event.key === Qt.Key_Control) {
            currentTags.state = "";
            view.focus = true;
        }
    }

    // TODO: use TagEditor component
}


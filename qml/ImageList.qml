import QtQuick 2.0

ListView { id: list
    property variant images: null
    property variant loader: list.currentItem ? list.currentItem.loader : null
    model: list.images
    width: parent.width
    height: parent.height
    Behavior on height { SmoothedAnimation { duration: 150 } }
    keyNavigationWraps: true
    cacheBuffer: width*2
    orientation: ListView.Horizontal
    highlightMoveVelocity: -1
    highlightMoveDuration: 100
    highlightResizeVelocity: -1
    highlightResizeDuration: 100
    preferredHighlightBegin: list.currentItem && list.currentItem.width
        ? (list.width - list.currentItem.width) / 2
        : 0
    // preferredHighlightEnd: list.width  // XXX
    preferredHighlightEnd: preferredHighlightBegin
        ? preferredHighlightBegin + list.currentItem.width / 2
        : list.width
    highlightRangeMode: ListView.StrictlyEnforceRange
    spacing: 10
    clip: true
    Behavior on opacity { NumberAnimation { duration: 200 } }
    delegate: Flickable { id: listEntry
        property variant image: loader ? loader.image : 0
        property alias loader: loader
        anchors { top: parent.top; bottom: parent.bottom }
        width: view.z(loader, 'width')
        contentWidth: view.z(loader, 'width')
        contentHeight: view.z(loader, 'height')
        boundsBehavior: Flickable.StopAtBounds
        ImageLoader { id: loader
            image: modelData
            onComplete: {
                if (status == Loader.Error || item.status == Image.Error) {
                    if (image) { console.log("unable to load ", image.path); }
                    if (index >= 0) { images.remove(index); }
                }
            }
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
            onClicked: { incrementCurrentIndex(); }
        }
    }
    function positionViewAtRandomIndex() {
        var randomIndex = Math.floor(Math.random()*list.count);
        console.log("moving to random index =", randomIndex)
        list.positionViewAtIndex(randomIndex, ListView.Center);
    }
    onFocusChanged: console.log("ImageView.focus =", focus)
    focus: false
    Keys.priority: Keys.BeforeItem
    Keys.onPressed: {
        if (currentIndex == -1) {
            //console.log("list ignored key event: ", event.key);
            return;
        }
        if (event.key === Qt.Key_R) {
            event.accepted = true;
            positionViewAtRandomIndex();
        } else if (event.key === Qt.Key_Space) {
            event.accepted = true;
            incrementCurrentIndex();
        } else {
            //console.log("list ignored key event: ", event.key);
        }
    }
}

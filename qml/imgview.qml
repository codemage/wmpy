// import QtQuick 1.0 // to target S60 5th Edition or Maemo 5
import QtQuick 1.1
import QtDesktop 0.1

Rectangle {
    id: view
    color: "black"
    width: 500
    height: 500
    focus: true
    
    property string tagName: ""
    property variant tag: tagdb.loaded && view.tagName ? tagdb.getTag(view.tagName) : false
    property variant images: view.tag ? view.tag.images : false
    property int imageIdx: 0
    property int imageCount: view.images ? view.images.rowCount() : 0
    property variant image: view.imageIdx < view.imageCount ?
        images.data(view.imageIdx) : {"tags": [], "path": "nothing_loaded.png"}

    function next() { view.imageIdx = (view.imageIdx + 1) % view.imageCount; }
    function prev() {
        view.imageIdx = (view.imageIdx + view.imageCount - 1) % view.imageCount;
    }

    onImageCountChanged: {
        if (view.imageIdx > view.imageCount)
            view.imageIdx = 0;
    }
        
    Image {
        anchors.fill: parent
        fillMode: Image.PreserveAspectFit
        smooth: true
        asynchronous: true
        visible: view.image.path != "nothing_loaded.png"
        source: view.image.path
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
            text: view.imageIdx + "/" + view.imageCount
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
        Button {
            id: loadButton
            onClicked: tagdb.open("imgtag.cfg")
            text: "Load"
        }
        Button {
            id: quitButton
            onClicked: Qt.quit()
            text: "Quit"
        }
    }
    ListModel { id: empty }
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
            model: view.image ? view.image.tags : empty
            delegate: Text {color: "white"; text: value.name}
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
            console.log(app.fullScreen);
            app.fullScreen ? app.showNormal() : app.showFullScreen();
        } else if (event.key == Qt.Key_Escape || event.key == Qt.Key_Q) {
            Qt.quit();
        } else if (event.key == Qt.Key_Right || event.key == Qt.Key_Space) {
            next();
        } else if (event.key == Qt.Key_Left) {
            prev();
        } else if (event.key == Qt.Key_Z) {
            if (tagdb.loaded) {
                var rand = Math.random();
                view.imageIdx = Math.floor(rand*view.imageCount)
            }
        } else {
            console.log(event.key);
        }
    }
}


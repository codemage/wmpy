function checkDownloaded(url, callback) {
  //console.log("in checkDownloaded", url);
  url = url.replace("_noncustom.", "."); // XXX IB specific
  var linkParts = url.split("/");
  var filename = linkParts[linkParts.length - 1];
  var nameParts = filename.split(".");
  if (nameParts.length > 1) {
    nameParts.pop();
  }
  filename = nameParts.join(".");
  var request = new XMLHttpRequest();
  request.open("GET", "http://localhost:5000/db/image/" + filename);
  request.onreadystatechange = function() {
    if (request.readyState == 4) {
      if (request.status == 200) {
        callback({"action": "checkDownloaded", "result": true});
      } else {
        callback({"action": "checkDownloaded", "result": false});
      }
    }
  };
  request.send();
}

function extractInkBunnySubmissionInfo(doc) {
  var widgets = doc.getElementsByClassName("widget_imageFromSubmission");
  var images = [];
  var links = [];
  var thumbs = [];
  for (var i = 0; i < widgets.length; i++) {
    var elt = widgets[i].lastElementChild;
    if (elt.tagName == "IMG") {
      images.push(elt.src);
    } else if (elt.tagName == "A") {
      if (elt.href.search("/full/") != -1) {
        images.push(elt.href);
      } else {
        links.push(elt.href);
        thumbs.push(elt.firstElementChild.src);
      }
    } else {
      console.log("unknown: ", images[i]);
    }
  }
  return {"images": images, "links": links, "thumbs": thumbs};
}

function getInkBunnySubmissionInfo(url, callback) {
  var request = new XMLHttpRequest();
  request.responseType = "document";
  request.open("GET", url);
  request.onreadystatechange = function() {
    if (request.readyState == 4) {
      if (request.status == 200) {
        var info = extractInkBunnySubmissionInfo(request.response);
        callback(info);
      } else {
        callback(null);
      }
    }
  }
  request.send();
}

function checkMulti(url, callback) {
  //console.log("in checkMulti", url);
  getInkBunnySubmissionInfo(url, function(info) {
    if (info == null) {
      callback(null); return;
    }
    var urls = info.images.concat(info.thumbs);
    var left = urls.length;
    var numDownloaded = 0;
    function checkOne(url) {
      checkDownloaded(url, function(response) {
        left--;
        if (response.result) {
          numDownloaded++;
        }
        if (numDownloaded == 1) {
          callback({"action": "checkDownloaded", "result": true});
        } else if (left == 0 && numDownloaded == 0) {
          callback({"action": "checkDownloaded", "result": false});
        }
      });
    }
    for (var i = 0; i < urls.length; i++) {
      checkOne(urls[i]);
    }
  });
}

chrome.runtime.onMessage.addListener(
  function(request, sender, sendResponse) {
    console.log("event page got request", request);
    if (request.action == "checkDownloaded") {
      if (request.isMulti) {
        checkMulti(request.url, sendResponse);
      } else {
        checkDownloaded(request.url, sendResponse);
      }
      return true;
    } else {
      console.log("Unknown request: ", request);
    }
  }
);

chrome.downloads.onChanged.addListener(function(downloadDelta) {
  if (downloadDelta.state && downloadDelta.state.current == "complete") {
    chrome.downloads.search({"id": downloadDelta.id}, function(results) {
      var filename = results[0].filename;
      var request = new XMLHttpRequest();
      request.open("POST", "http://localhost:5000/download_event");
      var form = new FormData();
      form.append("filename", filename);
      request.send(form);
    });
  }
});

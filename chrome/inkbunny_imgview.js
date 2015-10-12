// TODO: fix multiple-page submission view to only check downloaded images
// TODO: "download all" for multiple-page submissions
// TODO: toggle-able "click to download" mode for galleries
// Maybe: "download some" link, add checkboxes on thumbnails

function _fill_xpath_options(options) {
  if (options == null) {
    options = {};
  }
  if (typeof options.context === "undefined") {
    options.context = document;
  }
  if (typeof options.result_type === "undefined") {
    options.result_type = XPathResult.ANY_TYPE;
  }
  return options;
}

function xpath(expr, options) {
  options = _fill_xpath_options(options);
  var iterator = document.evaluate(expr, options.context, null, options.result_type, null);
  var result = [];
  var node = iterator.iterateNext();
  while (node) {
    result.push(node);
    node = iterator.iterateNext();
  }
  return result;
}

function xpath_check(expr, options) {
  options = _fill_xpath_options(options);
  return document.evaluate(expr, options.context, null, options.result_type, null);
}

function makeCheck() {
  var element = document.createElement("img");
  element.setAttribute("src", chrome.runtime.getURL("check.svg"));
  element.setAttribute("style", "width: 100%; height: 100%; position: absolute; x: 0; y: 0; z-index: 100;")
  return element;
}

function annotateLink(node, url, isMulti, callback) {
  //node.appendChild(document.createTextNode("*****"));
  checkDownloaded(url, isMulti, function(isDownloaded) {
    if (callback) {
      callback(isDownloaded);
    }
    if (isDownloaded) {
      node.insertBefore(makeCheck(), node.firstChild);
    } else {
      node.appendChild(document.createTextNode("-----"));
    }
  });
}

function annotateImage(node, url, isDownloaded) {
  if (node.tagName == "A") {
    // image links to larger version
    url = node.href;
    node = node.parentElement;
  }
  if (isDownloaded) {
    var downloadLink = document.createElement("span");
  } else {
    var downloadLink = document.createElement("a");
    downloadLink.setAttribute("download", "download");
    downloadLink.setAttribute("href", url);
  }
  downloadLink.setAttribute("style", "font-size: larger");
  downloadLink.appendChild(document.createTextNode("Download"));
  node.parentElement.appendChild(downloadLink);
}

function checkDownloaded(url, isMulti, callback) {
  chrome.runtime.sendMessage(
    {"action": "checkDownloaded", "url": url, "isMulti": isMulti},
    function(response) {
      if (response === null) {
        console.log("null checkDownloaded response");
      } else if (typeof response !== "object") {
        console.log("unrecognized checkDownloaded response", response)
      } else if (response.action == "checkDownloaded") {
        callback(response.result);
      } else {
        console.log("unrecognized checkDownloaded response", response)
      }
    });
}

var images = xpath("//img[contains(@src, '/files/')]");
for (var i = 0; i < images.length; i++) {
  (function(image) {
    var url = image.getAttribute("src");
    var node = image.parentElement;
    if (url === undefined) {
      console.log("unknown URL for submission", image);
    } else {
      annotateLink(node, url, false, function(isDownloaded) {
        annotateImage(node, url, isDownloaded);
      });
    }
  })(images[i]);
}

var thumbnails = xpath("//img[contains(@src, 'thumbnails/')]");
for (var i = 0; i < thumbnails.length; i++) {
  (function(thumbnail) {
    var link = thumbnail.parentElement;
    var isMulti = xpath_check("count(//div[contains(@title, 'pages')]) > 0", {"context": link});
    // if we're already viewing a page of a multi-page image, only check the
    // pages we have downloaded:
    if (isMulti && images.length == 0) {
      if (link.href === undefined) {
        console.log("unknown URL for thumbnail", thumbnail);
      } else {
        annotateLink(link, link.href, true);
      }
    } else {
      var url = thumbnail.getAttribute("src");
      url = url.replace("_noncustom.", ".");
      if (url === undefined) {
        console.log("unknown URL for thumbnail", thumbnail);
      } else {
        annotateLink(link, url, false);
      }
    }
  })(thumbnails[i]);
}

// vim: et sw=2 sts=2 encoding=utf-8

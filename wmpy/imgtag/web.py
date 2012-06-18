from __future__ import absolute_import

import sys
import os
import os.path

import flask

if __name__ == '__main__':
    if __package__ is None:
        __package__ = 'wmpy.imgtag'
        sys.path[0] = os.path.join(sys.path[0], '..', '..')

    from wmpy import imgtag
    from wmpy.imgtag.web import main
    main()
    sys.exit(0)

from .. import imgtag

app = flask.Flask(__name__)
app.secret_key = os.urandom(24)

@app.route("/")
def index():
    return flask.render_template('index.html')

@app.route("/db")
def db():
    data = dict(
        top_path = app.db.top_path,
        tags = {
            tag.name: dict(
                source=tag.list_path,
            ) for tag in app.db.tags.values()},
        images = {
            image.name: dict(
                path=image.path,
                also=[path for path in image.paths if path != image.path],
                tags=list(image.tags))
            for image in app.db.images.values()},
        )
    return flask.jsonify(data)

@app.route("/tag/<name>")
def tag(name):
    if name in app.db.tags:
        tag = app.db.tags[name]
    else:
        return flask.abort(404)
    images = list(tag.image_list)
    paths = '\n'.join(image.path for image in images)
    return (paths, None, {"Content-Type": 'text/plain'})

@app.route("/image/<name>")
def image(name):
    if name in app.db.images:
        image = app.db.images[name]
    else:
        flask.abort(404)
    return flask.send_file(image.path)

def main():
    app.db = imgtag.TagDB()
    app.run(debug=True)


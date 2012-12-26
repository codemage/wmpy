import sys
import os
import os.path

import flask

if __name__ == '__main__':
    sys.path.append(os.path.join(os.path.basename(__file__), ".."))

from wmpy import imgtag

app = flask.Flask(__name__)
app.secret_key = os.urandom(24)

def image_json(image):
    return dict(
            path=image.path,
            also=[path for path in image.abs_paths if path != image.path],
            tags=list(image.tags)
        )

def images_json(images):
    return {
        image.name: image_json(image)
        for image in list(images)
        }

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
            ) for tag in list(app.db.tags.values())},
        images = images_json(app.db.images.values()),
        )
    return flask.jsonify(data)

@app.route("/db/hash/<hashval>")
def by_hash(hashval):
    return flask.jsonify(app.db.find_by_hash(hashval))

@app.route("/db/image/<name>")
def by_name(name):
    if name in app.db.images:
        return flask.jsonify(image_json(app.db.images[name]))
    else:
        flask.abort(404)

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
    app.db = imgtag.TagDB(config_path=sys.argv[1] + "/imgtag.cfg")
    app.db.scan()
    app.run(debug=True)

if __name__ == '__main__':
    main()
    sys.exit(0)


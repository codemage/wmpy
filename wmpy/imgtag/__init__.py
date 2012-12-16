import collections
import functools
import itertools
import os
from os import path as p
import pipes
import stat
import sys
import threading
import weakref

from .. import nat_sort_key
from .. import _collection
from .. import _io
from .. import _logging
from .. import _threading
from .. import ValueObjectMixin
from . import tagexpr

_logger, _dbg, _info, _warn = _logging.get_logging_shortcuts(__name__)

class TaggedImage(ValueObjectMixin, object):
    _cmp_key = property(lambda self: self.name)
    def __init__(self, path, tags, base):
        ValueObjectMixin.__init__(self)
        self.base = base
        self.name = p.basename(path)
        self.tags = weakref.proxy(tags[self])
        self.paths = {path}

    def add_path(self, new_path):
        assert(p.basename(new_path) == self.name)
        self.paths.add(new_path)

    @property
    def path(self):
        """ canonical path is always the shortest: """
        return min(self.paths, key=len)

    def __str__(self):
        return p.relpath(self.path, self.base)

    def __repr__(self):
        return 'TaggedImage(%r)' % self.path
    
    @property
    def tagstr(self):
        return '|'.join(sorted(self.tags))

    def move(self, target_dir):
        new_path = p.join(self.base, target_dir, self.name)
        if new_path in self.paths:
            _warn("Not moving %s, already at %s", self, new_path)
            return
        old_path = self.path
        _info("Moving %s from %s to %s (tags: %s)", self.name,
            old_path, new_path, self.tagstr)
        try:
            os.renames(old_path, new_path)
            self.paths.remove(old_path)
            self.paths.add(new_path)
        except OSError:
            _warn("Failed to move %s", self, exc_info=True)

def _raise(exc):
    raise exc

class Tag(object):
    _cmp_key = property(lambda self: self.name)
    def __init__(self, name, list_path, image_list, base, factory):
        self.base = base
        self.name = name
        self.list_path = list_path
        self.image_list = image_list
        self.factory = factory
        self.dirty = False
        if p.isfile(self.list_path):
            self.load(initial=True)

        def _list_changed(image_list, weakself=weakref.ref(self)):
            self = weakself()
            if self is None:
                image_list.listeners.remove(_list_changed)
            assert(self.image_list is image_list)
            self.dirty = True
        self.image_list.listeners.append(_list_changed)

    def reset(self, images):
        self.image_list[:] = images
        self.dirty = False

    def load(self, list_path=None, initial=False):
        if list_path is not None:
            self.list_path = list_path
        if initial:
            _info('reading tag %s from %s', self.name, self.list_path)
        else:
            _info('reloading tag %s from %s', self.name, self.list_path)
        seen_names = set()
        new_image_list = []
        with open(self.list_path, 'rb') as fp:
            for line in fp:
                line = str(line.strip(), 'utf-8')
                if len(line) == 0:
                    continue

                if self.base is not None:
                    path = p.join(self.base, *line.split('/'))
                name = p.basename(line)
                if name in seen_names:
                    continue
                seen_names.add(name)
                new_image_list.append(self.factory(path))
        
        self.reset(new_image_list)
        _dbg("read %s images tagged with %s from %s",
            len(new_image_list), self.name, self.list_path)
    
    def save(self, force=False):
        if not force and not self.dirty:
            _info("Tag list for %s unchanged", self.name)
            return
        _info("Saving tag list for %s to %s", self.name, self.list_path)
        with open(self.list_path, 'wb') as fp:
            for image in self.image_list:
                path = image.path
                if self.base is not None:
                    path = p.relpath(image.path, self.base)
                path = path.replace('\\', '/').encode('utf-8')
                fp.write(path+b'\n')
        self.dirty = False

    def __str__(self):
        return self.name

class TagDB(_logging.InstanceLoggingMixin,
            object):
    default_config = {
        'ignore_extensions': {
            '.rar', '.zip', '.db', '.orig', '.txt', '.cfg', '.swp', '.hashes',
            '.mp3', '.doc', '.swf', '.rtf',  '.pdf', '.odt', ''
        },
        'taggable_extensions': {'.jpg', '.jpeg', '.png', '.gif'}
    }

    @property
    def config_dir(self):
        return p.dirname(self.config_path)
    def _path_from_cfg(self, name, default='.'):
        rv = p.join(self.config_dir, self.config.get(name, default))
        return p.abspath(rv)
    @property
    def top_path(self):
        return self._path_from_cfg('image_path')
    @property
    def tags_path(self):
        return self._path_from_cfg('tags_path', p.join(self.top_path, 'imgtag'))
    @property
    def _hash_cache_path(self):
        return self._path_from_cfg('hash_cache', p.join(self.tags_path, '.hashes'))

    def __init__(self, config_path='./imgtag.cfg', config=None):
        _logging.InstanceLoggingMixin.__init__(self)
        self.config_path = p.abspath(str(config_path))
        if config is None:
            self.config = self.default_config.copy()
            if p.isfile(self.config_path):
                self._dbg("loading configuration from %s", config_path)
                with open(self.config_path, 'rU') as config_fp:
                    try:
                        config_code = compile(config_fp.read(), self.config_path, 'exec')
                        exec(config_code, self.config)
                    except Exception as ex:
                        self._warn("error in config file, raising")
                        raise
                self._dbg("images under %s", self.top_path)
                self._dbg("tags under %s", self.tags_path)
            else:
                self._dbg("config not found at %s, using default config", self.config_path)
        else:
            self.config = config

        if not p.isdir(self.tags_path):
            self._dbg("making new tags dir at %s", self.tags_path)
            os.mkdir(self.tags_path)

        self._hash_cache = _io.FileHashCache(self._hash_cache_path)
        self._scanning = False
        self._scanning_changed = threading.Condition()
        self._cancel_scan = False

        self.images = {}
        self.tags = {}

        self._mm_tags, self._mm_images = \
            _collection.ManyToMany('set', 'checked_list')

    @property
    def scanning(self):
        return self._scanning

    @scanning.setter
    def scanning(self, is_scanning):
        with self._scanning_changed:
            self._scanning = is_scanning
            if not is_scanning:
                self._cancel_scan = False
            self._scanning_changed.notify_all()
    
    def _image(self, path, source=None):
        abspath = p.abspath(p.join(self.top_path, path))
        filename = p.basename(abspath)
        if filename in self.images:
            if abspath not in self.images[filename].paths:
                if source is None:  # path is on the filesystem:
                    self.images[filename].add_path(abspath)
                else:
                    self._warn("path %s from %s, but file is at %s",
                        abspath, source, self.images[filename].path)
        else:
            self.images[filename] = TaggedImage(
                path=abspath,
                tags=self._mm_tags,
                base=self.top_path)
        return self.images[filename]

    def _tag(self, tagname, list_path=None):
        if list_path is None:
            list_path = p.join(self.tags_path, '%s.list' % tagname)
        
        if tagname not in self.tags:
            self.tags[tagname] = Tag(
                name=tagname,
                list_path=list_path,
                image_list=self._mm_images[tagname],
                base=self.top_path,
                factory=functools.partial(self._image, source=list_path),
                )
        return self.tags[tagname]

    def stopScan(self):
        with self._scanning_changed:
            if not self.scanning:
                return False
            while self.scanning:
                self._cancel_scan = True
                self._scanning_changed.wait(999999)
            assert not self.scanning
            return True

    def scan(self):
        with self._scanning_changed:
            if self.scanning:
                raise ValueError("Concurrent call to scan() detected")
            else:
                self.scanning = True
        self._dbg("scanning %s...", self.top_path)
        walk = os.walk(self.top_path, onerror=_raise)
        if not self.tags_path.startswith(self.top_path):
            walk = itertools.chain(walk, 
                os.walk(self.tags_path, onerror=_raise))

        tagfiles = {}
        for parent, dirs, files in walk:
            dirs[:] = [d for d in dirs if not d.startswith('.')]

            for filename in files:
                with self._scanning_changed:
                    if self._cancel_scan:
                        self._dbg("scan cancelled")
                        self.scanning = False
                        return False

                path = p.join(parent, filename)
                name, ext = p.splitext(filename)
                if ext == '.list':
                    if not path.startswith(self.tags_path):
                        _warn("ignoring tag file outside of tag path: %s", path)
                    elif name in tagfiles:
                        _warn("ignoring duplicate tag file: %s", path)
                    else:
                        tagfiles[name] = path
                elif ext in self.config['taggable_extensions']:
                    if os.stat(path)[stat.ST_SIZE] == 0:
                        _warn("ignoring empty file: %s", path)
                    else:
                        self._image(path)
                elif ext in self.config.get('ignore_extensions', ()):
                    pass
                else:
                    _warn("unrecognized file: %s", path)

        for tag, list_path in tagfiles.items():
            self._tag(tag, list_path)

        self.scanning = False
        return True

    def find_dupes(self):
        by_hash = collections.defaultdict(dict)
        cnt = 0
        for image in self.images.values():
            cnt += 1
            if cnt % 1000 == 0:
                self._hash_cache.save()
            for path in image.paths:
                path_hash = self._hash_cache.find_hash(path)
                by_hash[path_hash][path] = image

        for entry in by_hash.values():
            if len(entry) > 1:
                yield entry

    def find_by_tags(self, tag_expression, **bindings):
        tag_expression = compile(tag_expression, '<tagexpr>', 'eval')
        for tagname in self.tags:
            bindings.setdefault(tagname, tagexpr.Tag(tagname))
        bindings.setdefault('untagged', tagexpr.Untagged())
        tag_expression = eval(tag_expression, bindings)
        images = []
        for image in self.images.values():
            tags = set(image.tags)
            if tag_expression.evaluate(image, tags):
                images.append(image)

        sort_tag = tag_expression.sort_tag()
        if sort_tag is not None:
            indices = {}
            for i, image in enumerate(self.tags[sort_tag].image_list):
                indices[id(image)] = i
            print("sorting image list by tag " + sort_tag)
            images.sort(key=lambda image: indices[id(image)])
        else:
            print("sorting image list by name")
            images.sort(key=lambda image: nat_sort_key(image.name))
        return images

    @staticmethod
    def images_to_paths(images, sort=True):
        if sort:
            images = sorted(images)
        return [image.path for image in images]

    def save_dirty(self):
        self._hash_cache.save()
        for tag in self.tags.values():
            try:
                tag.save()
            except Exception:  # pylint: disable=W0703
                _info("Error saving %s to %s", tag, tag.list_path,
                    exc_info=True)
        if any(tag.dirty for tag in self.tags.values()):
            ns = globals().copy()
            ns.update(locals())
            import code
            code.interact(local=ns,
                banner="error saving tags, dropping into interpreter\n")


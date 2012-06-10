#!/usr/bin/env python

"""
This is a tool for doing image or photo tagging by integrating with the feh
image viewer for Linux.  The storage format is a Python configuration file
plus a list of plain text ".list" files with relative paths to images, and
it makes the presumption that image filenames are unique within the directory
tree on which it operates.

It is portable and can interact with the tagset on Windows, but is only really
useful on operating systems with Unix-style shells and pipe semantics because the
'view' action relies heavily on feh and on some magic with Unix FIFO descriptors.

This is software built for personal use; if anyone besides me can figure out how
to make it work, great, but for now I am not going to bother documenting it properly.
"""

import argparse
import collections
from collections import defaultdict
from contextlib import contextmanager
import errno
import functools
import inspect
import io
import logging
import os, os.path as p
import pipes
import re
import shlex
import shutil
import subprocess as sp
import sys
import threading
import weakref

if __name__ == '__main__':
    if os.environ.get('IMGTAG_DEBUG', '') != '':
        logging.basicConfig(level=logging.DEBUG, stream=sys.stdout,
            format="%(levelname)s %(message)s")
    else:
        logging.basicConfig(level=logging.INFO,
            format="%(levelname)s %(message)s")
    sys.path[0] = p.join(sys.path[0], '..')

import wmpy
_logger, _dbg, _info, _warn = wmpy.get_logging_shortcuts(__name__)

def _raise(exc):
    raise exc

@functools.total_ordering
class ValueObj(object):
    @property
    def _cmp_key(self):
	return id(self)
    def __eq__(self, other):
	if type(self) != type(other):
	    return False
	return self._cmp_key == other._cmp_key
    def __lt__(self, other):
	if type(self) != type(other):
	    raise TypeError
	return self._cmp_key < other._cmp_key
    def __hash__(self):
	return hash(type(self)) ^ hash(self._cmp_key)

class TaggedImage(ValueObj):
    _cmp_key = property(lambda self: self.name)
    def __init__(self, path, tags, base):
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
	new_path = p.join(self.base, target_dir, name)
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

class Tag(object):
    _cmp_key = property(lambda self: self.name)
    def __init__(self, name, list_path, image_list, base, factory):
	self.base = base
	self.name = name
	self.list_path = list_path
	self.image_list = image_list
	self.factory = factory
	self.dirty = False
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
	with file(self.list_path, 'rb') as fp:
	    for line in fp:
		line = line.strip()
		if len(line) == 0:
		    continue

		if self.base is not None:
		    path = p.join(self.base, line)
		name = p.basename(line)
		if name in seen_names:
		    continue
		seen_names.add(name)
		new_image_list.append(self.factory(path))
	
	self.reset(new_image_list)
	_dbg("read %s images tagged with %s from %s", len(new_image_list), self.name, self.list_path)
    
    def save(self, force=False):
	if not force and not self.dirty:
	    _info("Tag list for %s unchanged", self.name)
	    return
	_info("Saving tag list for %s to %s", self.name, self.list_path)
	with file(self.list_path, 'wb') as fp:
	    for image in self.image_list:
		path = image.path
		if self.base is not None:
		    path = p.relpath(image.path, self.base)
		fp.write("%s\n" % path)
	self.dirty = False

    def __str__(self):
	return self.name

class TagDB(wmpy.InstanceLoggingMixin,
	    object):
    @property
    def config_dir(self):
	return p.dirname(self.config_path)
    def _dir_from_cfg(self, name, default='.'):
	rv = p.join(self.config_dir, self.config.get(name, default))
	return p.abspath(rv)
    @property
    def top_path(self):
	return self._dir_from_cfg('image_path')
    @property
    def tags_path(self):
	return self._dir_from_cfg('tags_path')

    def __init__(self, config_path=None, config=None):
	if config_path is None:
	    self.config_path = p.abspath('./imgtag.cfg')
	else:
	    self.config_path = p.abspath(config_path)
	if config is None:
	    self.config = {}
	    self._dbg("loading configuration from %s", config_path)
	    execfile(config_path, self.config)
	else:
	    self.config = config

	self.images = {}
	self.tags = {}

	self._mm_tags, self._mm_images = \
	    wmpy.ManyToMany('set', 'checked_list')

	self.scan()
    
    def _image(self, abspath, source=None):
	filename = p.basename(abspath)
	relpath = p.relpath(abspath, self.top_path)
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

    def scan(self):
	self._dbg("scanning %s...", self.top_path)
	walk = os.walk(self.top_path, onerror=_raise)
	if not self.tags_path.startswith(self.top_path):
	    walk = itertools.chain(walk, 
		os.walk(self.tags_path, onerror=_raise))

	tagfiles = {}
	for parent, dirs, files in walk:
	    dirs[:] = filter(lambda d: not d.startswith('.'), dirs)

	    for filename in files:
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
		    self._image(path)
		elif ext in self.config.get('ignore_extensions', ()):
		    pass
		else:
		    _warn("unrecognized file: %s", path)

	for tag, list_path in tagfiles.iteritems():
	    self.tags[tag] = Tag(
		name=tag,
		list_path=list_path,
		image_list=self._mm_images[tag],
		base=self.top_path,
		factory=functools.partial(self._image, source=list_path),
		)
    
    def _make_dupe_checker(self, path):
	self._dbg("reading %s to check for duplicates", path)
	with file(path, 'rb') as fp:
	    data = fp.read()
	def _do_check(dupe):
	    self._dbg("comparing %s to %s", path, dupe)
	    with file(dupe, 'rb') as fp:
		dupe_data = fp.read()
	    return data == dupe_data
	return _do_check

    def print_dupes(self, delete=False):
	for image in self.images.itervalues():
	    check = self._check_dupe(image.path)
	    for path in image.paths:
		if path == image.path:
		    continue
		if check:
		    print "%s: duplicate at %s" % (image, dupe)
		    if delete:
			os.unlink(path)
		else:
		    print "%s: name conflict %s" % (image, dupe)

    def find_by_tags(self, tagexpr, **bindings):
	tagexpr = compile(tagexpr, '<tagexpr>', 'eval')
	for tagname in self.tags:
	    bindings.setdefault(tagname, {tagname})
	for image in self.images.itervalues():
	    tags = set(image.tags)
	    bindings.update(
		name=image.name,
		tags=tags,
		path=image.path,
		)
	    result = eval(tagexpr, bindings)
	    if isinstance(result, set):
		result = (tags == result)
	    if result:
		yield image

    def images_to_paths(self, images, sort=True):
	if sort:
	    images = sorted(images)
	return [image.path for image in images]

    def view_tags(self, tagexpr, feh_args=[], **bindings):
	paths = self.images_to_paths(
		    self.find_by_tags(tagexpr, **bindings))

	if len(paths) == 0:
	    print "No matching images.\n"
	    return

	with wmpy.Pipe() as (cmd_r, cmd_w), \
	     wmpy.Pipe() as (info_r, info_w):

	    def _preexec():
		os.close(cmd_r.fileno())
		os.close(info_w.fileno())

	    tag_bindings = self.config.get('tag_bindings', {})
	    cmd = ['feh',
		'--info', 'IFS=""; exec <&%s; echo info "%%f" >&%d; read -r INFO; echo "$INFO"' % (info_r.fileno(), cmd_w.fileno())]
	    for numkey, tag in tag_bindings.iteritems():
		cmd.extend(('--action%d' % numkey,
		    ';echo tag %s "%%f" >&%d' % (tag, cmd_w.fileno())))
	    cmd.extend(feh_args)
	    paths_on_stdin = True
	    if paths_on_stdin:
		cmd.extend(['-f', '-'])
		self._info('Running viewer: %s < [%d paths]',
		    ' '.join(map(pipes.quote, cmd)), len(paths))
	    else:
		self._info('Running viewer: %s [%d paths]',
		    ' '.join(map(pipes.quote, cmd)), len(paths))
		cmd.extend(paths)

	    viewer = sp.Popen(cmd, stdin=sp.PIPE, preexec_fn=_preexec,
		cwd=self.top_path)
	    cmd_w.close()
	    info_r.close()

	    finish_cond = threading.Condition()
	    thread_err = []
	    def _notify_finish():
		with finish_cond:
		    if sys.exc_info() != (None, None, None):
			thread_err[:] = sys.exc_info()
		    finish_cond.notify_all()

	    def _comm_thread_func():
		if paths_on_stdin:
		    input_data = '\n'.join(paths)
		else:
		    input_data = ''
		viewer.communicate(input=input_data)
		_notify_finish()

	    binding_desc = ' '.join('%s->%s' % (k,v) for k,v in tag_bindings.items())
	    def _cmd_info(command):
		fn = ' '.join(command[1:])
		self._dbg("info request: %s", fn)
		image = self.images[p.basename(fn)]
		info_w.write('%s tags=|%s|\\n%s\n' % (image, image.tagstr, binding_desc))
		info_w.flush()

	    def _cmd_tag(command):
		tag = self.tags[command[1]]
		fn = ' '.join(command[2:])
		image = self.images[p.basename(fn)]
		if tag.name in image.tags:
		    _warn("remove tag %s %s", image, tag)
		    tag.image_list.remove(image)
		else:
		    _warn("add tag %s %s", image, tag)
		    tag.image_list.append(image)

	    def _cmd_thread_func():
                self._dbg('viewer command thread starting')
		for cmdline in cmd_r:
		    command = cmdline.strip().split(' ')
		    if command[0] == 'info':
			_cmd_info(command)
		    elif command[0] == 'tag':
			_cmd_tag(command)
		    else:
			_warn("unknown command from viewer: %r" % cmdline)
		_notify_finish()
	
	    try:
		comm_thread = wmpy.WatchedThread('comm_thread',
                    _comm_thread_func, _notify_finish)
		comm_thread.start()
		cmd_thread = wmpy.WatchedThread('cmd_thread',
                    _cmd_thread_func, _notify_finish)
		cmd_thread.start()
		wmpy.WatchedThread.join_all(comm_thread, cmd_thread)
	    finally:
		if viewer.returncode is None:
		    os.kill(viewer.pid, 15) # TERM

	if viewer.returncode != 0:
	    sys.exit(viewer.returncode)

    def save_dirty(self):
	for tag in self.tags.itervalues():
	    try:
		tag.save()
	    except:
		_info("Error saving %s to %s", tag, tag.list_path,
		    exc_info=True)
	if any(tag.dirty for tag in self.tags.itervalues()):
	    ns = globals().copy()
	    ns.update(locals())
	    import code
	    code.interact(local=ns,
		banner="error saving tags, dropping into interpreter\n")

def parse_bindings(db, bindings):
    binding_pairs = [ b.split('=') for b in bindings ]
    return { name: set(value.split(',')) if value else set()
	for name, value in binding_pairs }

gen_parser = wmpy.ParserGenerator(ignored_args=['db'], 
    tagexpr=dict(help='image selection expression',
	metavar='"<tagexpr>"', nargs='?'),
    bindings=dict(help='tagsets to bind in expr',
	metavar='name=tag[,...]', nargs='*'),
    )

@gen_parser(
    feh=dict(short='f', help='arguments to viewer',
	     metavar='<feh args>', action='append'),
    )
def do_view(db, tagexpr='True', feh=('-Z', '-F'), *bindings):
    """View/tag images in feh, selected based on their tags"""
    try:
	bindings = parse_bindings(db, bindings)
	feh_args = shlex.split(' '.join(feh))
	db.view_tags(tagexpr, feh_args=feh_args, **bindings)
    finally:
	def _save():
	    # add stack frame so as not to modify exception context
	    try:
		db.save_dirty()
	    except Exception:
		pass
	_save()

@gen_parser(
    dupes=dict(short='d', action='store_true',
               help='only show duplicated images'),
    long=dict(short='l', action='store_true',
	       help='list by name, with tags and path'),
    )
def do_ls(db, tagexpr='True', dupes=False, long=False, *bindings):
    """List information about images, selected based on their tags"""
    bindings = parse_bindings(db, bindings)
    try:
        for image in sorted(db.find_by_tags(tagexpr, **bindings)):
	    if dupes and len(image.paths) == 1:
		continue
	    if long:
		duplicates = [' + %s' % d for d in image.paths if d != image.path]
		dupe_str = ''.join(duplicates)
		print "%s\t|%s|\t%s%s" % (image.name, image.tagstr, image.path, dupe_str)
	    else:
		print p.relpath(image.path)
    except IOError, ioerr:
	if ioerr.errno != errno.EPIPE: # if EPIPE, don't care
	    raise

@gen_parser
def do_tag(db):
    """Read lines like <add/remove> <filename> <tag> from stdin."""
    for line in sys.stdin:
	if line.strip() == '':
	    continue
	cmd, name, tag = line.strip().split()
	if cmd == 'add':
	    db.images[name].tags.append(tag)
	elif cmd == 'remove':
	    db.images[name].tags.remove(tag)
	else:
	    raise ValueError('unknown command: ' + line.strip())
    db.save_dirty()

actions = {name[3:].replace('_', '-'): func
    for name, func in globals().iteritems()
    if name.startswith('do_') and hasattr(func, 'parser')}

@gen_parser(
    parser_args=dict(add_help=False, prog=sys.argv[0]),
    ignore=['argv'],
    cfg=dict(short='c', help='config file to use', metavar='<imgtag.cfg>'),
    action=dict(nargs='?', choices=actions.keys()),
    help=dict(short='h', action='store_true',
	      help='show this help message and exit')
    )
def main(cfg='tags/imgtag.cfg', action=None, help=False, argv=[]):
    if help:
	if action is not None:
	    actions[options.action].parser.print_help()
	else:
	    # don't set metavar in params, the default {a|b|c}
	    # is good for print_usage(); this is better for long help:
            main.args['action'].metavar = '<action>'
	    main.parser.print_help()
	    print "\n<action> may be any of:"
	    for name, action in actions.iteritems():
		print "  %s: %s" % (name, action.__doc__)
		usage = action.parser.format_usage()
		usage = usage.replace(' %s' % sys.argv[0], '')
		usage = re.sub('\n +', " ", usage).replace(' [-h]', '')
		print "     ", usage,
	print
	return 0
    elif action is None:
	main.parser.print_usage()
	return 1
	
    action = actions[options.action]
    action_kw = {}
    if 'db' in action.required_args:
	action_kw['db'] = TagDB(config_path=cfg)
    return action.parse_and_call(argv, **action_kw)

if __name__ == '__main__':
    options, extra_argv = main.parser.parse_known_args(sys.argv[1:])
    options.argv = extra_argv
    sys.exit(main.call_with_options(**vars(options)))


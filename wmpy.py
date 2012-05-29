""" Python bits and pieces WM finds handy.

Copyright (c) 2012 Walter Mundt; see LICENSE file for details.
"""

import argparse
from contextlib import contextmanager
import inspect
import io
import logging
import os
import re
import sys
import time
import threading

_VERSION = (0, 0, 1)

_logger = logging.getLogger(__name__)
_dbg = _logger.debug
_info = _logger.info
_warn = _logger.warning

def nat_sort_key(val):
    """ Splits a string into a tuple of string components and
        integer components, such that sorting a list of strings
        with this function set as the key= parameter will
        sort sets of strings like "foo_1_bar", "foo_2_bar",
        "foo_10_bar" into that order.

        Works poorly on strings of hex digits and in other similar
        cases.
    """
    def _conv(item):
	try:
	    return int(item)
	except:
	    return item
    rv = tuple(filter(None, map(_conv, re.split("(\d+)", str(val)))))
    _dbg("nat_sort_key: %r -> %r", s, rv)
    return rv

@contextmanager
def io_pipe():
    """ Context manager that wraps `os.pipe()`, yielding the read and
        write sides of the pipe after wrapping them with io.open;
        ensures that both ends are closed on exit from the with block.
    """
    r_fd, w_fd = os.pipe()
    with io.open(r_fd, 'rb', 0) as r, \
    	 io.open(w_fd, 'wb', 0) as w:
    	yield r, w

class WatchedThread(threading.Thread):
    """ Thread that calls fail_cb in the thread's context on uncaught
        exceptions; if fail_cb is not provided, an uncaught exception
        in the thread aborts the whole process with os._exit(), doing no
        cleanup whatsoever.

        If the thread has exited due to an uncaught exception, the
        `died` attribute will be True, and `will_throw` will be True until the
        next call to `reraise()`.  Calling `reraise` when `will_throw`
        atomically reraises the uncaught exception and clears that flag; if it
        is not set `reraise()` does nothing.  `join()` implies `reraise()`
        if it does not time out.

        If multiple threads are to be joined, and one or more may have
        died abnormally, the classmethod join_all will raise the first
        uncaught exception to arrive.  If there are several, the other
        threads will keep their `will_throw` flag and stored exception
        until the next time their `reraise` is called.

        Also, for no particularly good reason, the `daemon` flag defaults to
        True in this subclass.
    """
    _any_exit = threading.Condition()

    def __init__(self, name, target, fail_cb = None, **kw):
	threading.Thread.__init__(self, **kw)
        self._lock = threading.RLock()
	self.name = name
	self.target = target
	self.fail_cb = fail_cb
        self.active = False # used instead of isAlive in case
                            # join_all catches the space between
                            # _any_exit().notify_all() and thread death
        self.died = False
	self.exc_info = None
        self.daemon = True

    def run(self):
        self.active = True
	try:
	    self.rv = self.target()
	except:
	    _logger.exception("uncaught exception in thread %s" % self.name)
            with self._lock:
                self.exc_info = sys.exc_info()
                self.died = True
            if self.fail_cb is None:
                sys.stdout.flush()
                sys.stderr.flush()
                os._exit(1)
            else:
                self.fail_cb()
        finally:
            with self._any_exit:
                self.active = False
                self._any_exit.notify_all()

    @property
    def will_throw(self):
	return self.exc_info is not None

    def reraise(self):
	if self.exc_info is not None:
            with self._lock:
                if self.exc_info is None:
                    return # it went away while getting the lock
                try:
                    raise self.exc_info[0], \
                          self.exc_info[1], \
                          self.exc_info[2]
                finally:
                    self.exc_info = None # clear ref cycle

    def join(self, *args, **kw):
	rv = threading.Thread.join(self, *args, **kw)
	self.reraise()
	return rv

    @classmethod
    def join_all(cls, *threads, **kw):
        # timeout would be a keyword-only arg in python 3:
        timeout = kw.pop('timeout', None)
        end_time = None if timeout is None else time.time() + timeout
        while any(thread.active for thread in threads):
            with cls._any_exit:
                for thread in threads:
                    thread.reraise()
                time_left = end_time - time.time() \
                            if end_time is not None \
                            else None
                if (time_left is not None and time_left <= 0) or \
                   not any(thread.active for thread in threads):
                    return
                cls._any_exit.wait(time_left)

class ArgSpec(object):
    """ Wrapper around inspect.getargspec that adds some niceties.

        First off, the defaults attribute is a mapping from
        argument name to default value instead of a sequence of
        defaults for the final arguments, and is never None.

        Second, it has a `func` attribute set to the function object
        it was built from.

        Third, it provides make_call_args, to translate a dictionary
        of arguments into an (args, kw) pair usable to call the function.
        This differs from inspect.getcallargs in that it accepts no starting
        positional arguments and will correctly fill varargs from an
        appropriately-named keyword entry mapped to a sequence.  Note that
        this is fragile: a wrapper or substiture function that is semantically
        equivalent in every possible call may use a different *varargs
        name, changing the behavior of this method.  Raises KeyError
        for missing arguments.

        Fourth, it may be called with keyword arguments, and will use
        `self.make_call_args` to convert them and call `func`.  This is
        fragile for the same reason as `make_call_args` itself, but can
        be useful nonetheless.

        Fifth, it contains a 'positionals' attribute that is equal to
        `args` unless the `func` has a *varargs parameter, in which
        case the name of that parameter is appended.
    """
    def __init__(self, func):
        self.func = func
        self.args, self.varargs, self.keywords, defaults = \
            inspect.getargspec(func)
        self.positionals = self.args + \
            ([self.varargs] if self.varargs is not None else [])

	# build a mapping from argument names to their default values, if any:
	if defaults is None:
            self.defaults = {}
	else:
            defaulted_args = self.args[-len(defaults):]
	    self.defaults = {name: val
		for name, val in zip(defaulted_args, defaults)}

    def make_call_args(self, arguments):
        args = []
        kw = arguments.copy()
        for arg in self.args:
            if arg in kw:
                args.append(kw.pop(arg))
            elif arg in self.defaults:
                arg.append(self.defaults[arg])
            else:
                raise TypeError("missing argument in call to %s(): %s" %
                    (self.func.__name__, arg))
        if self.varargs is not None:
            args.extend(kw.pop(self.varargs))
        return args, kw

    def __call__(self, **arguments):
        args, kw = self.make_call_args(arguments)
        _dbg("Calling %s(*%r, **%r)", self.func.__name__,
            args, kw)
        return self.func(*args, **kw)

class ParserGenerator(object):
    """ A configurable decorator that builds ArgumentParser instances
        from function signatures.  These parsers are stored as 'parser'
        attributes on the functions, but should primarily be used by calling
        'func.parse_and_call(argv, **extra_args)'; this is set up to use the
        generated parser to build appropriate arguments for a call to the
        function.

        By default, all parameters will be represented as positional arguments
        of the same name, will be required iff they have no defaults, and
        result in string values being passed.

        If the decorator is provided with keyword arguments, they should be
        set to dictionaries of keyword arguments for parser.add_argument
        calls.  By default, arguments specified this way are --long options;
        they may include a 'name' or 'names' keyword to provide other names.
        If a nargs keyword is present (even if None), a positional argument is
        made instead.  Argument settings defined this way override the
        automatic defaults for wrapped-function parameters of the same names;
        keys with no matching names are passed as keyword parameters.  (If a
        name is not an arg name, and the function does not accept a **kw-style
        argument, an error is raised from gen_parser.)
        
        Decorator keywords may also be set to any other value, in which case
        the generated flag will be a --long flag whose presence will result in
        the named parameter being set to that value; the parameter should have
        a default setting for when the flag is absent.
    """

    def __init__(self, ignored_args = [], **common_options):
        """ ignored_args should be a sequence of argument names; these are not
            added to the parser as arguments by default; they must be passed as
            keyword arguments to the built `parse_and_call`.
        
            common_options provides argparse overrides by name; any arg with
            a matching name in any generated parser will default to using
            those settings instead of just being a positional.
        """
        self.ignored_args = ignored_args
        self.common_options = self._fix_argparse_dicts(common_options)

    def build_parser(self, argspec, arguments):
        """ May be overridden to customize how the parser instance
            is build before adding arguments.

            Accepts an ArgSpec instance and an arguments dictionary
            as is provided when a ParserGenerator is used as a decorator.
        """
        fname = argspec.func.__name__
        if fname.startswith('do_'):
            fname = fname[3:]

        parser_args = arguments.pop('parser_args', {})
        parser_args.setdefault('prog', '%s %s' % (sys.argv[0], fname))
        if argspec.func.__doc__ is not None:
            parser_args.setdefault('description', argspec.func.__doc__)
        return argparse.ArgumentParser(**parser_args)

    def _fix_argparse_dicts(self, arguments):
        return {
            name: (info if isinstance(info, dict)
                   else dict(action='store_const', const=info))
            for name, info in arguments.iteritems() }

    def __call__(self, ignore=None, **arguments):
        """ This actually implements the decorator. """
        func = None
        if inspect.isfunction(ignore):
            # left off the parens?
            func = ignore
            ignore = []
        elif ignore is None:
            ignore = []

        ignore += self.ignored_args
        if func is None:
            return lambda func: self._make_parser(func, ignore, arguments)
        else:
            return self._make_parser(func, ignore, arguments)

    def _add_arg(self, argspec, parser, flag, info):
        assert (
            # we can only pass in things in the arg list, unless
            # the function takes a **kw:
            flag in argspec.positionals
            or argspec.keywords is not None), \
            "%s not in args %s" % (flag, argspec.positionals)
        
        for k, v in self.common_options.get(flag, {}).iteritems():
            info.setdefault(k, v)

        if flag in argspec.defaults:
            info.setdefault('default', argspec.defaults[flag])

        if 'nargs' in info:
            argnames = [flag]
        else:
            argnames = ['-%s' % char for char in info.pop('short', [])]
            argnames.append('--%s' % flag)
            info.setdefault('required',
                flag in argspec.args and flag not in argspec.defaults)

        _dbg("  add arg: %s %s", argnames, info)
        argspec.func.args[flag] = parser.add_argument(*argnames, **info)

    def _make_parser(self, func, ignore, arguments):
        _dbg("make action for %s, ignore=%r, arguments=%r",
            func.__name__, ignore, arguments)

        # canonicalize non-dict keywords from decorator into store_const:
        arguments = self._fix_argparse_dicts(arguments)

	argspec = ArgSpec(func)

        func.args = {}
        func.required_args = set()
        func.unparsed_args = set()
	for arg in argspec.args:
	    if arg in ignore:
                if arg not in arguments:
                    func.unparsed_args.add(arg)
                if arg not in argspec.defaults:
                    func.required_args.add(arg)
		continue # don't default these to anything

	    # anything completly missing from the spec is a positional:
            if arg not in arguments:
                _dbg("%s: defaulting %s to positional",
                    func.__name__, arg)
                arguments[arg] = {
                    'nargs': '?' if arg in argspec.defaults else None}
	
	if argspec.varargs is not None:
	    arguments.setdefault(argspec.varargs, {})
	    arguments[argspec.varargs].setdefault('nargs', '*')

        # now that we have the arguments dict all filled in,
        # build a parser out of it
        parser = self.build_parser(argspec, arguments)

	# add positional arguments from the function signature in order first,
        # stripping them out of the arguments dict as we go
	for arg in argspec.positionals:
            if arg in arguments:
		self._add_arg(argspec, parser,
                    arg, arguments.pop(arg))

	# the rest ought to be **kw params, for which don't care about ordering
	for flag, info in arguments.iteritems():
	    self._add_arg(argspec, parser, flag, info)

        # we have a parser, build parse_and_call
	def parse_and_call(argv, **other_args):
	    options = vars(parser.parse_args(argv))
            options.update(other_args)
            return argspec(**options)

        # okay, that's everything; set attach our fine work to the function
        # and return it.
        # (We don't wrap the function so that it is still possible to call it
        # with the original signature instead of an argv.)
	func.parser = parser
	func.parse_and_call = parse_and_call
        func.call_with_options = argspec
	return func


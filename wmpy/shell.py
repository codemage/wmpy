#!/usr/bin/env python
""" wmpy.shell

This is a prototype of a Unix-style shell in Python.

It will not be sh-compatible.  It is designed for interactive
use.
"""

import os, os.path
import sys

def _generic_main_boilerplate(module_globals, expected_package, module_name):
    # This is standard boilerplate for modules that are loaded as part of a
    # package and want to have a _main() function, and who want their _main
    # to run in the context of the version of the module attached to the
    # package.  Since the whole point is to get to a sane import/sys.path
    # state, it can't be extracted into an importable function without
    # introducing a dependency on the module it's defined in being installed
    # system-wide.
    #
    # This avoids the issue where there are two parallel copies of the module,
    # one called __main__ and one by its normal name, with different versions
    # of all of the types and module-level state and constants.
    #
    # Modules using this boilerplate can be run via python -m 'pkg.mod', python
    # pkg/mod.py or even 'cd pkg; python mod.py' and will work regardless.
    #
    # It's written so that if I ever to decide to just stick it in a module in
    # the system path, it can be imported and called and still work.
    if module_globals['__name__'] != '__main__':
        return

    if module_globals.get('__package__') is None:
        module_globals['__package__'] = expected_package
    package = module_globals['__package__']
    full_name = '%s.%s' % (package, module_name)

    if os.path.abspath(os.path.dirname(__file__)) == \
       os.path.abspath(sys.path[0]):
        # python pkg/mod.py mucks up the path, fix it:
        sys.path[0] += '/..' * len(package.split('.'))

    __import__(full_name, globals(), locals(), None, 0)
    sys.modules[full_name]._main() # pylint: disable=W0212
    sys.exit(0)

_generic_main_boilerplate(globals(), 'wmpy', 'shell')

import shlex

from . import _proc, _io, _logging, VERSION

def _main():
    import readline
    print 'wmpy.shell %s.%s.%s' % VERSION
    while True:
        try:
            line = raw_input('wmpy.shell $ ')
        except EOFError, KeyboardInterrupt:
            print
            return
        print repr(shlex.split(line))


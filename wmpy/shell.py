#!/usr/bin/env python
""" wmpy.shell

This is a prototype of a Unix-style shell in Python.

It will not be sh-compatible.  It is designed for interactive
use.

Requires parcon (from PyPI) to work.
"""

# pylint: disable=W0231

# TEMP, while there are big missing pieces, no unused import warnings:
# pylint: disable=W0611

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

import parcon
from parcon import *  # pylint: disable=W0614

def merge_strings(vals):
    rv = [vals[0]]
    for val in vals[1:]:
        if isinstance(rv[-1], str) and isinstance(val, str):
            rv[-1] += val
        else:
            rv.append(val)
    if len(rv) == 1:
        return rv[0]
    return rv

class ParseNode(object):
    def __init__(self, val):
        self.val = val
    def __str__(self):
        return repr(self)
    def __repr__(self):
        return '%s(%r)' % (type(self).__name__, self.val)

class Var(ParseNode):
    def __init__(self, val):
        _dollar, name = val
        self.name = name
    def __str__(self):
        return '${%s}' % self.name
    def __repr__(self):
        return "Var(%s)" % self.name

class ShellPyExpr(ParseNode):
    def __init__(self, expr):
        self.expr = expr
    def __str__(self):
        return '~{{%s}}' % self.expr
    def __repr__(self):
        return 'ShellPyExpr(%r)' % self.expr

class Arg(ParseNode):
    pass

class JoinedArg(ParseNode):
    pass

def make_arg(val):
    val = merge_strings(val)
    if isinstance(val, str):
        return Arg(val)
    elif isinstance(val, list):
        return JoinedArg(val)
    else:
        return val

@apply
def grammar():
    # pylint: disable=W0612
    L = Literal
    SL = SignificantLiteral
    ToStr = lambda p: Translate(p, ''.join)

    MaybeBraced = lambda p: p | ("{" + p + "}")
    VariableName = Word(alphanum_chars+'_.', init_chars=alpha_chars+'_')(
        expected='variable name')
    VariableRef = (SL('$') + MaybeBraced(VariableName))(    
        expected='$VAR, ${VAR}')[
        Var]

    LongPythonExpr = Exact(OneOrMore(CharNotIn("}") | 
        ToStr(SL("}") + CharNotIn("}"))))
    ShortPythonExpr = Exact(+CharNotIn("}"))
    ShortPythonArg = Exact("~{" + ShortPythonExpr + "}")
    LongPythonArg = Exact("~{{" + LongPythonExpr + "}}")
    PythonArg = ToStr(LongPythonArg | ShortPythonArg)(
        expected='${python expr}, ${{python expr}}')[
        ShellPyExpr]
    SingleQuotedString = ToStr(Exact("'" + CharNotIn("'")[...] + "'"))(
        expected="'quoted string'")
    UnquotedArg = ToStr(+CharNotIn("' \t\n\r\\${}"))(
        expected="unquoted_word")
    ShellArg = Exact(OneOrMore(
        PythonArg |
        SingleQuotedString |
        UnquotedArg |
        VariableRef
        ))[make_arg]
    ShellLine = ShellArg[...] + End()
    return locals()
    # pylint: enable=W0612

def _main():
    import readline  # pylint: disable=W0612
    print 'wmpy.shell %s.%s.%s' % VERSION
    while True:
        try:
            line = raw_input('wmpy.shell $ ')
            parsed = grammar['ShellLine'].parse_string(line)
            print ' '.join(map(str, parsed))
        except parcon.ParseException as ex:
            print ex
            print
        except (EOFError, KeyboardInterrupt):
            print
            return

""" Python bits and pieces WM finds handy.

Copyright (c) 2012 Walter Mundt; see LICENSE file for details.
"""


import re
import functools

VERSION = (0, 0, 2)

from ._logging import *
_logger, _dbg, _info, _warn = get_logging_shortcuts(__name__)


_grouped_digits_re = re.compile(r'(\d+)')
def nat_sort_key(val):
    """ Splits a string into a tuple of string components and
        integer components, such that sorting a list of strings
        with this function set as the key= parameter will
        sort sets of strings like "foo_1_bar", "foo_2_bar",
        "foo_10_bar" into that order.

        Works poorly on strings of hex digits and in other similar
        cases.
    """
    split_val = _grouped_digits_re.split(str(val))
    for i in range(1, len(split_val), 2):
        split_val[i] = int(split_val[i])
    start = 1 if split_val[0] == '' else 0
    end = -1 if split_val[-1] == '' else None
    split_val = split_val[start:end]
    # _dbg("nat_sort_key: %r -> %r", val, split_val)
    return split_val

@functools.total_ordering
class ValueObjectMixin(object):
    """ Base class for hashable, comparable value objects.

        Subclasses should implement a _cmp_key property as a base for
        both comparison and hashing.  Note that instances of different
        subclasses of this type will compare unequal and not be orderable even
        if their _cmp_key values are the same.
    """
    @property
    def _cmp_key(self):
        return id(self)
    def __eq__(self, other):
        if type(self) != type(other):
            return False
        return self._cmp_key == other._cmp_key  # pylint: disable=W0212
    def __lt__(self, other):
        if type(self) != type(other):
            raise TypeError
        return self._cmp_key < other._cmp_key  # pylint: disable=W0212
    def __hash__(self):
        return hash(type(self)) ^ hash(self._cmp_key)

class weakmethod(object):
    """ Converts a bound method to one with a weakly-referenced 'self'. """
    def __init__(self, method, weakref_cb):
        self.obj = weakref.ref(method.__self__, weakref_cb)
        self.method = method.__func__

    def __call__(self, *args, **kw):
        self.method(self.obj(), *args, **kw)

from ._collection import *
from ._io import *
from ._introspect import *
from ._proc import *
from ._threading import *


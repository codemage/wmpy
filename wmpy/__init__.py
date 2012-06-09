""" Python bits and pieces WM finds handy.

Copyright (c) 2012 Walter Mundt; see LICENSE file for details.
"""
from __future__ import absolute_import

_VERSION = (0, 0, 1)

from ._logging import *
from ._io import *
from ._introspect import *
from ._proc import *
from ._threading import *

_logger, _dbg, _warn, _error = get_logging_shortcuts(__name__)

import re

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
    for i in xrange(1, len(split_val), 2):
        split_val[i] = int(split_val[i])
    start = 1 if split_val[0] == '' else 0
    end = -1 if split_val[-1] == '' else None
    split_val = split_val[start:end]
    # _dbg("nat_sort_key: %r -> %r", val, split_val)
    return split_val



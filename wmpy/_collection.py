import collections
import operator
import types
import weakref

from . import _logging
_logger, _dbg, _info, _warn = _logging.get_logging_shortcuts(__name__)

class _ManyToManyCollection(#_logging.InstanceLoggingMixin,
			    object):
    inner = None
    _append = None
    _extend = None

    def __init__(self, my_idx, other_side, items = None):
	if items is None:
	    items = self.inner()
	self._my_idx = my_idx
	self._other_side = other_side
	self._items = items
	self._link_all(items)
	self.listeners = []

    def __index__(self, idx):
	return self._items[idx]
    def __len__(self):
	return len(self._items)
    def __iter__(self):
	return iter(self._items)
    def _notify(self):
	for func in self.listeners:
	    func(self)
    def clear(self, notify=True):
	self._unlink_all(self._items)
	self._items = self.inner()
	if notify:
	    self._notify()
    def _link(self, item, notify=True):
	self._other_side[item]._append(self._my_idx)
	if notify:
	    #self._dbg('link %s notify %s', self._my_idx, item)
	    self._other_side[item]._notify()
    def _link_all(self, items):
	items = list(items)
	for item in items:
	    self._link(item, notify=False)
	for item in items:
	    # do in second pass so notifications go out after
	    # establishing consistency:
	    #self._dbg('link all %s notify %s', self._my_idx, item)
	    self._other_side[item]._notify()
    def _unlink(self, item, notify=True):
	self._other_side[item]._remove(self._my_idx)
	if notify:
	    #self._dbg('unlink %s notify %s', self._my_idx, item)
	    self._other_side[item]._notify()
    def _unlink_all(self, items):
	items = list(items)
	for item in items:
	    self._unlink(item, notify=False)
	for item in items:
	    #self._dbg('unlink all %s notify %s %x', self._my_idx, item, id(self._other_side[item]))
	    self._other_side[item]._notify()
    def append(self, item):
	self._append(item)
	self._link(item)
	#self._dbg('append %s notify self', self._my_idx)
	self._notify()
    def extend(self, items):
	self._extend(items)
	self._link_all(items)
	#self._dbg('extend %s notify self', self._my_idx)
	self._notify()
    def _remove(self, item):
	self._items.remove(item)
    def remove(self, item):
	self._remove(item)
	self._unlink(item)
	self._notify()
    def _replace(self, newitems):
	self.clear(notify=False)
	self.extend(newitems)
	return self
    def _op(name):
	op = getattr(operator, name)
	def do_op(self, other):
	    #_dbg('op %s %s %s', self, op, other)
	    if isinstance(other, _ManyToManyCollection):
		return op(self._items, other._items)
	    else:
		return op(self._items, other)
	def do_iop(self, other):
	    newitems = op(self, other)
	    return self._replace(newitems)
	do_op.__name__ = name
	do_iop.__name__ = '__i' + name[2:]
	return do_op, do_iop
    __add__, __iadd__ = _op('__add__')
    __and__,__iand__ = _op('__and__')
    __or__,__ior__ = _op('__or__')
    __xor__,__ixor__ = _op('__xor__')

    def __str__(self):
	return repr(self)
    def __repr__(self):
	return '<%s(%r)>' % (type(self).__name__, self._items)

class _MMList(_ManyToManyCollection):
    inner = list
    def _append(self, item):
	self._items.append(item)
    def _extend(self, items):
	self._items.extend(items)
    def __getitem__(self, idx):
	return self._items[idx]
    def __setitem__(self, idx, new_item):
	if isinstance(idx, slice):
	    self._unlink_all(self._items[idx])
	else:
	    self._unlink(self._items[idx])
	self._items[idx] = new_item
	if isinstance(idx, slice):
	    self._link_all(new_item)
	else:
	    self._link(new_item)
	#self._dbg('setitem %s notify self', self._my_idx)
	self._notify()
    def __delitem__(self, idx):
	if isinstance(idx, slice):
	    self._unlink_all(self._items[idx])
	else:
	    self._unlink(self._items[idx])
	del self._items[idx]
	#self._dbg('delitem %s notify self', self._my_idx)
	self._notify()

class _MMCheckedList(_MMList):
    @classmethod
    def _setup(cls):
	for k, v in _MMList.__dict__.items():
	    if isinstance(v, types.FunctionType):
		_dbg('adding uniqueness check to %s.%s', cls.__name__, k)
		def make_check_and_do(k=k, v=v):
		    def check_and_do(self, *args, **kw):
			#_dbg('doing uniqueness check for %s.%s', cls.__name__, k)
			rv = v(self, *args, **kw)
			self._check('after ' + k)
			return rv
		    check_and_do.__name__ = k + '_and_check'
		    return check_and_do
		setattr(cls, k, make_check_and_do())
	del cls._setup

    def _check(self, when):
	dupes = collections.Counter(self._items) - \
		collections.Counter(set(self._items))
	if len(dupes) > 0:
	    raise ValueError(
		'duplicates detected in list check %s: %s'
		% (when, list(dupes.elements())))

_MMCheckedList._setup()

class _MMSet(_ManyToManyCollection):
    inner = set
    def _append(self, item):
	self._items.add(item)
    def _extend(self, items):
	self._items.update(items)
    def _replace(self, newitems):
	self._unlink_all(self._items - newitems)
	self._link_all(newitems - self._items)
	self._items = newitems
	#self._dbg('_replace %s notify self', self._my_idx)
	self._notify()
	return self
    # override append and extend to not add redundant links for existing items:
    def append(self, item):
	if item in self:
	    return
	_ManyToManyCollection.append(self, item)
    def extend(self, items):
	items = set(items) - self._items
	_ManyToManyCollection.extend(self, items)

class _MMCounter(_ManyToManyCollection):
    inner = collections.Counter
    def _append(self, item):
	self._items.update((item,))
    def _extend(self, items):
	self._items.update(items)
    def _remove(self, item):
	self._items.subtract((item,))
    def _replace(self, newitems):
	self._unlink_all((self._items - newitems).elements())
	self._link_all((newitems - self._items).elements())
	self._items = newitems
	#self._dbg('_replace %s notify self', self._my_idx)
	self._notify()
	return self
    def __iter__(self):
	return iter(self._items.elements())

class _ManyToManySide(object):
    kinds = {
	'checked_list': _MMCheckedList,
	'counter': _MMCounter,
	'list': _MMList,
	'set': _MMSet,
    }

    def __init__(self, kind, other=None):
	self._kind = self.kinds[kind]
	self._contents = {}
	if other is not None:
	    self._other = weakref.proxy(other)

    def set_other(self, new_other):
	self._other = weakref.proxy(new_other)

    def __getitem__(self, idx):
	if isinstance(idx, slice):
	    raise TypeError
	if idx not in self._contents:
	    self._contents[idx] = self._kind(idx, self._other)
	return self._contents[idx]

    def __setitem__(self, idx, items):
	if self[idx] is items:
	    return
	items = self._kind.inner(items)
	self[idx]._replace(items)

    def __delitem__(self, idx):
	if isinstance(idx, slice):
	    raise TypeError
	self._contents.pop(idx).clear()

    def __len__(self):
	return len(self._contents)
    def __iter__(self):
	return iter(self._contents.iteritems())
    def keys(self):
	return self._contents.iterkeys()
    def values(self):
	return self._contents.itervalues()
    def items(self):
	return self._contents.iteritems()

class ManyToMany(object):
    def __init__(self, left_kind='set', right_kind='set'):
	self.left = _ManyToManySide(left_kind)
	self.right = _ManyToManySide(right_kind, self.left)
	self.left.set_other(self.right)

    def __iter__(self):
	return iter((self.left, self.right))

from contextlib import contextmanager
import unittest

class _ManyToManyTests(unittest.TestCase):
    def setUp(self):
	if 'g_log_handler' in globals():
	    g_log_handler.stream = sys.stdout

    def allkinds(self):
	for lk in _ManyToManySide.kinds:
	    for rk in _ManyToManySide.kinds:
		yield ManyToMany(lk, rk)

    def testBasic(self):
	for mm in self.allkinds():
	    left, right = mm

	    left['foo'].append('bar')
	    self.assertItemsEqual(['bar'], left['foo'])
	    self.assertItemsEqual(['foo'], right['bar'])
	    self.assertIn('bar', left['foo'])
	    self.assertNotIn('foo', left['foo'])

	    right['baz'].append('qux')
	    self.assertItemsEqual(['baz'], left['qux'])
	    self.assertItemsEqual(['qux'], right['baz'])

	    def assertFull():
		self.assertItemsEqual(['bar', 'baz'], left['foo'])
		self.assertItemsEqual(['baz'], left['qux'])
		self.assertItemsEqual(['foo'], right['bar'])
		self.assertItemsEqual(['foo', 'qux'], right['baz'])
	
	    right['baz'].append('foo')
	    assertFull()
	    
	    del left['foo']
	    self.assertItemsEqual([], left['foo'])
	    self.assertItemsEqual(['baz'], left['qux'])
	    self.assertItemsEqual([], right['bar'])
	    self.assertItemsEqual(['qux'], right['baz'])

	    left['foo'] = ['bar', 'baz']
	    assertFull()
	    
	    left['foo'].remove('bar')
	    self.assertItemsEqual(['baz'], left['foo'])
	    self.assertItemsEqual(['baz'], left['qux'])
	    self.assertItemsEqual([], right['bar'])
	    self.assertItemsEqual(['foo', 'qux'], right['baz'])

	    left['foo'].extend(['bar'])
	    assertFull()
    
    def testListener(self):
	for mm in self.allkinds():
	    left, right = mm
	
	    @contextmanager
	    def assertNotifies(entry, desc, count=1):
		notifications = [0]
		def _notify(_entry):
		    self.assertIs(entry, _entry)
		    notifications[0] += 1
		entry.listeners.append(_notify)
		yield
		entry.listeners.remove(_notify)
		self.assertEqual(count, notifications[0], '%s@%x notified %d times, expected %d' % (desc, id(entry), notifications[0],count))

	    with assertNotifies(left[0], 'left[0]'), assertNotifies(right[1], 'right[1]'):
		left[0] = [1,2,3]
	    with assertNotifies(left[0], 'left[0]'), assertNotifies(right[1], 'right[1]'):
	    	left[0] = [2,3]
    
    def testCheckedList(self):
	def make(right_kind='list'):
	    left, right = make.mm = ManyToMany('checked_list', right_kind)
	    left['foo'] = [1,2,3]
	    return make.mm  # store as attribute to keep refs to both sides

	with self.assertRaisesRegexp(ValueError, 'duplicates detected'):
	    make().left['foo'].append(1)
	with self.assertRaisesRegexp(ValueError, 'duplicates detected'):
	    make().left['foo'].extend([2])
	with self.assertRaisesRegexp(ValueError, 'duplicates detected'):
	    make().left['foo'].extend([1,2,3])
	with self.assertRaisesRegexp(ValueError, 'duplicates detected'):
	    make().right[1].append('foo')

	left, right = make(right_kind='set')
	self.assertItemsEqual(['foo'], right[1])
	right[1].append('foo')  # should not raise
	with self.assertRaisesRegexp(ValueError, 'duplicates detected'):
	    left['foo'].append(1)  # ...but this will

    def testSetOps(self):
	left, right = ManyToMany('set', 'set')
	left['foo'] = {1,2,3}
	self.assertItemsEqual({1,2,3}, left['foo'])
	for i in {1,2,3}:
	    self.assertItemsEqual(['foo'], right[i],
		'expected right[%s] == ["foo"], got %s' % 
		(i, set(right[i])))

	right[1] |= {'baz', 'qux'}
	self.assertItemsEqual({'foo','baz','qux'}, right[1])
	self.assertItemsEqual([1,2,3], left['foo'])
	self.assertItemsEqual([1], left['baz'])
	self.assertItemsEqual([1], left['qux'])

	left['foo'] &= {2,3,5}
	self.assertItemsEqual([2,3], left['foo'])
	self.assertItemsEqual(['baz', 'qux'], right[1])
	self.assertItemsEqual(['foo'], right[2])
	self.assertItemsEqual(['foo'], right[3])

    def testListOps(self):
	left, right = ManyToMany('list', 'list')
	left[0][:] = [1,2,3]
	self.assertItemsEqual([1,2,3], left[0])
	self.assertItemsEqual([0], right[1])
	self.assertItemsEqual([0], right[2])
	self.assertItemsEqual([0], right[3])

if __name__ == '__main__':
    import logging
    import sys
    g_log_handler = logging.StreamHandler(sys.stdout)
    logging.getLogger().addHandler(g_log_handler)
    logging.getLogger().setLevel(logging.DEBUG)
    unittest.main()

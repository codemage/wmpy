import operator
import weakref

class _ManyToManyCollection(object):
    inner = None
    _append = None
    _extend = None

    def __init__(self, my_idx, other_side, items = None):
	if items is None:
	    items = self.inner()
	self._my_idx = my_idx
	self._other_side = other_side
	self._items = items
	for item in self._items:
	    self._other_side[item].append(item)

    def __index__(self, idx):
	return self._items[idx]
    def __len__(self):
	return len(self._items)
    def __iter__(self):
	return iter(self._items)
    def clear(self):
	self._unlink_all(self._items)
	self._items = self.inner()
    def _link(self, item):
	other = self._other_side[item]
	getattr(other._items, other._append)(self._my_idx)
    def _link_all(self, items):
	for item in items:
	    self._link(item)
    def _unlink(self, item):
	other = self._other_side[item]
	other._items.remove(self._my_idx)
    def _unlink_all(self, items):
	for item in items:
	    self._unlink(item)
    def append(self, item):
	getattr(self._items, self._append)(item)
	self._link(item)
    def extend(self, items):
	getattr(self._items, self._extend)(items)
	self._link_all(items)
    def remove(self, item):
	self._items.remove(item)
	self._unlink(item)
    def _replace(self, newitems):
	self.clear()
	self.extend(newitems)
	return self
    def _op(name):
	op = getattr(operator, name)
	def do_op(self, other):
	    if isintance(other, _ManyToManyCollection):
		return op(self._inner, other._inner)
	    else:
		return op(self._inner, other)
	def do_iop(self, other):
	    return self._replace(op(self, other))
	do_op.__name__ = name
	do_iop.__name__ = '__i' + name[2:]
	return do_op, do_iop
    __add__, __iadd__ = _op('__add__')
    __and__,__iand__ = _op('__and__')
    __or__,__ior__ = _op('__or__')
    __xor__,__ixor__ = _op('__xor__')


class _MMList(_ManyToManyCollection):
    inner = list
    _append = 'append'
    _extend = 'extend'
    def __getitem__(self, idx):
	return self._items[idx]
    def __setitem__(self, idx, new_item):
	if isinstance(idx, slice):
	    self._unlink_all(self._items[idx])
	else:
	    self._unlink(self._items[idx])
	self._items[idx] = new_item
    def __delitem__(self, idx):
	if isinstance(idx, slice):
	    self._unlink_all(self._items[idx])
	else:
	    self._unlink(self._items[idx])
	del self._items[idx]

class _MMSet(_ManyToManyCollection):
    inner = set
    _append = 'add'
    _extend = 'update'
    def _replace(self, newitems):
	self._unlink_all(self._items - newitems)
	self._link_all(newitems - self._items)
	self._items = newitems

class _ManyToManySide(object):
    kinds = {'list': _MMList, 'set': _MMSet}

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
	if isinstance(idx, slice):
	    raise TypeError
	if isinstance(items, self.kind):
	    items = self.kind.inner(items)
	if not isinstance(items, self.kind.inner):
	    raise TypeError('got %s, expected %s' % (type(items), self.kind.inner))
	if idx in self:
	    del self[idx]
	self._contents[idx] = self._kind(idx, self._other, items)

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

import unittest

class ManyToManyTests(unittest.TestCase):
    def allkinds(self):
	for lk in ('list', 'set'):
	    for rk in ('list', 'set'):
		yield ManyToMany(lk, rk)

    def testBasic(self):
	for mm in self.allkinds():
	    mm.left['foo'].append('bar')
	    self.assertItemsEqual(['bar'], mm.left['foo'])
	    self.assertItemsEqual(['foo'], mm.right['bar'])

	    mm.right['baz'].append('qux')
	    self.assertItemsEqual(['baz'], mm.left['qux'])
	    self.assertItemsEqual(['qux'], mm.right['baz'])
	
	    mm.right['baz'].append('foo')
	    self.assertItemsEqual(['baz'], mm.left['qux'])
	    self.assertItemsEqual(['bar', 'baz'], mm.left['foo'])
	    self.assertItemsEqual(['foo', 'qux'], mm.right['baz'])
	    
	    del mm.left['foo']
	    self.assertItemsEqual([], mm.left['foo'])
	    self.assertItemsEqual([], mm.right['bar'])
	    self.assertItemsEqual(['qux'], mm.right['baz'])

if __name__ == '__main__':
    unittest.main()

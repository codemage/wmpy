from contextlib import contextmanager
import os.path
import sys
import unittest

if __name__ == '__main__' and __package__ is None:
    sys.path[0] = os.path.join(sys.path[0], '..')

from . import _logging
from . import _collection as c

# pylint: disable=E1102,W0212

class ManyToManyTests(_logging.LogBufferMixin,
                       unittest.TestCase):
    @staticmethod
    def allkinds():
        for lk in c._ManyToManySide.kinds:
            for rk in c._ManyToManySide.kinds:
                yield c.ManyToMany(lk, rk)

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
                self.assertEqual(count, notifications[0],
                    '%s@%x notified %d times, expected %d' %
                    (desc, id(entry), notifications[0],count))

            with assertNotifies(left[0], 'left[0]'), \
                 assertNotifies(right[1], 'right[1]'):
                left[0] = [1,2,3]
            with assertNotifies(left[0], 'left[0]'), \
                 assertNotifies(right[1], 'right[1]'):
                left[0] = [2,3]
    
    def testCheckedList(self):
        def make(right_kind='list'):
            left, _right = make.mm = c.ManyToMany('checked_list', right_kind)
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
        left, right = c.ManyToMany('set', 'set')
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
        left, right = c.ManyToMany('list', 'list')
        left[0][:] = [1,2,3]
        self.assertItemsEqual([1,2,3], left[0])
        self.assertItemsEqual([0], right[1])
        self.assertItemsEqual([0], right[2])
        self.assertItemsEqual([0], right[3])

if __name__ == '__main__':
    unittest.main()
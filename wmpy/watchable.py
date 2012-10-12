import collections
import weakref
import sys

from . import _logging
_logger, _dbg, _info, _warn = _logging.get_logging_shortcuts(__name__)

class WatchableMixin(object):
    """ Mixin for adding "watchable" events to an object.

        Elaboration upon the "observer" pattern that allows notification both
        before and after changes, and for notifications about arbitrary events
        not necessarily linked to state changes in the watched object.

        Events are named, and can have separate sets of "before" and "after"
        listeners.  They can be fired in two ways: all at once with `_emit()`,
        or by the using `_event()` context manager in a with statement.

        Example of the latter:

            def frobnicate(self, count):
                with self._event('frobnicate', count=count) as evt:
                    num_frobnicated = self._really_frobnicate(count)
                    evt.set_result(num_frobnicated=num_frobnicated)
                return num_frobnicated

        If an exception is raised within such a with block, the "after"
        listeners receive an additional 'exc_info' keyword parameter.
        If `set_result` is never called, the keywords from the `_event`
        call are used by default.

        The `_listener_exception()` method is called whenever a listener
        raises an exception and may be overridden.  By default, listener
        exceptions are propagated unless they would be suppressing an
        exception already being handled before they were called.  On entry
        into that method `sys.exc_info` contains the exception raised by
        the listener.  `outer_exc` is whatever was in sys.exc_info()[1] before
        calling any listeners.
    """
    _Listeners = collections.namedtuple('_Listeners', 'before after gen')

    def __init__(self):
        self.listeners = collections.defaultdict(
            lambda: self._Listeners([],[],[]))
        self.buckets = {}
        self._next_id = 0

    def _add_listener(self, listener, bucket):
        self._next_id += 1
        bucket.append((self._next_id, listener))
        self.buckets[self._next_id] = bucket
        return self._next_id

    def add_listener_before(self, eventname, func):
        return self._add_listener(func, self.listeners[eventname].before)

    def add_listener_after(self, eventname, func):
        return self._add_listener(func, self.listeners[eventname].after)

    def add_listener_gen(self, eventname, generator):
        return self._add_listener(generator, self.listeners[eventname].gen)

    def remove_listener(self, id_to_remove):
        bucket = self.buckets.pop(self._next_id)
        for idx, (listener_id, _listener) in enumerate(bucket):
            if listener_id == id_to_remove:
                del bucket[idx]
                return
        raise KeyError("No listener with id %s registered" % id_to_remove)

    def _listener_exception(self, outer_exc, listener, eventname, kw):
        if outer_exc is None:
            raise
        else:
            _logger.exception("exception in listener for %s.%s suppressed",
                type(self).__name__, eventname)

    def _call_listener(self, outer_exc, listener, eventname, kw):
        try:
            listener(self, eventname, **kw)
        except Exception:
            self._listener_exception(outer_exc, listener, eventname, kw)

    def _notify_of_event(self, listeners, eventname, kw):
        outer_exc = sys.exc_info()[1]
        for listener in listeners:
            self._call_listener(outer_exc, listener, eventname, kw)

    def _make_gen_begin(self, listener_gen, instance_list):
        def _gen_begin(watchable, eventname, **kw):
            gen_instance = listener_gen(watchable, eventname, **kw)
            next(gen_instance)
            instance_list.append(gen_instance)
        return _gen_begin

    def _begin_event(self, eventname, kw):
        gen_instances = []
        listeners = [listener for lid, listener in
                     self.listeners[eventname].before]
        # gen_instances gets filled in during _notify_of_event by the wrapper
        # functions we build and append to the queue in this loop:
        for lid, gen_listener in self.listeners[eventname].gen:
            listeners.append(
                self._make_gen_begin(gen_listener, gen_instances))
        self._notify_of_event(listeners, eventname, kw)
        # ...so that we can return them to be used later:
        return gen_instances

    def _make_gen_end(self, gen_instance):
        def _gen_end(watchable, eventname, **kw):
            try:
                gen_instance.send(kw)
            except StopIteration:
                pass
        return _gen_end

    def _end_event(self, gen_instances, eventname, kw):
        listeners = [listener for lid, listener
                     in self.listeners[eventname].after]
        listeners.extend(self._make_gen_end(gen_instance)
            for gen_instance in gen_instances)
        self._notify_of_event(listeners, eventname, kw)

    class _EventContext(object):
        def __init__(self, watchable, eventname, kw):
            self.watchable, self.eventname, self.kw = watchable, eventname, kw
        def set_result(self, **kw):
            self.kw = kw
        def __enter__(self):
            self.gen_instances = self.watchable._begin_event(
                self.eventname, self.kw)
            return self
        def __exit__(self, *exc_info):
            if exc_info != (None, None, None):
                # don't put exc_info into self, avoids an unnecessary ref loop
                kw = self.kw.copy()
                kw['exc_info'] = exc_info
            else:
                kw = self.kw
            self.watchable._end_event(self.gen_instances,
                self.eventname, kw)

    def _event(self, eventname, **kw):
        return self._EventContext(self, eventname, kw)

# alias to allow inheriting from 'watchable.Mixin' after importing this module:
Mixin = WatchableMixin

def method(eventname):
    """ Decorator to make an event fire when a method is called.

        Without parameters, the event is named after the method;
        it is possible to specify the name as a parameter to the
        decorator as well.

        "Before" listeners to the event will get the 'args' and 'kw'
        keywords containing the values used to invoke the function.
        
        "After" listeners will additionally get a 'result' or 'exc_info'
        keyword with the return value or raised-exception-context from
        the call.
    """
    def make_watchable_method(func):
        def watchable_method(self, *args, **kw):
            with self._event(eventname, args=args, kw=kw) as evt:
                result = func(self, *args, **kw)
                evt.set_result(args=args, kw=kw, result=result)
            return result
        return watchable_method
    if isinstance(eventname, collections.Callable):
        func = eventname
        eventname = func.__name__
        return make_watchable_method(func)
    else:
        return make_watchable_method

def property(eventname, fget, fset, *args):
    """ Builds a property attribute that automatically fires an
        event whenever the setter is invoked.  Both "before" and
        "after" listeners get a `value` keyword containing the
        value of the property when the listener is invoked, a
        `new_value` keyword with the parameter to the setter, and a
        `prev_value` keyword with the starting value.  "After"
        listeners get an `exc_info` as well if the setter raises,
        in which case the value may be unchanged.

        (`new_value` and `value` are provided still separately to the
        "after" listener both for symmetry and because the setter and/or
        getter often do some sort of transformation on the value when
        properties are in use, and this allows listeners to see what is
        going on.)
    """
    def watchable_fset(self, value):
        prev_value = fget()
        with self._event(eventname, 
                         value=prev_value,
                         prev_value=prev_value,
                         new_value=value) as evt:
            rv = fset(self, value)
            evt.set_result(value=fget(),
                           prev_value=prev_value,
                           new_value=value)
        return rv
    return __builtin__.property(fget, watchable_fset, *args)
            
import unittest

class BasicWatchableTest(unittest.TestCase):
    class BasicWatchable(WatchableMixin):
        x = 5
        def update(self, new_x):
            with self._event('update', x=self.x) as evt:
                self.x = new_x
                evt.set_result(x=new_x)

    def setUp(self):
        self.foo = BasicWatchableTest.BasicWatchable()
        self.assertEqual(5, self.foo.x)
        self.before_called = False

    def testNoWatcher(self):
        self.foo.update(42)
        self.assertEqual(42, self.foo.x)
        self.assertFalse(self.before_called)

    def assertListenerPreconditions(self, expected_x, x, foo, eventname):
        self.assertEqual('update', eventname)
        self.assertIs(self.foo, foo)
        self.assertEqual(expected_x, x)
        self.assertEqual(expected_x, foo.x)

    def before(self, foo, eventname, x):
        self.assertListenerPreconditions(5, x, foo, eventname)
        self.before_called = True
        foo.x = -1  # should be overwritten

    def testBeforeWatcher(self):
        self.foo.add_listener_before('update', self.before)
        self.foo.update(42)
        self.assertEqual(42, self.foo.x)
        self.assertTrue(self.before_called)

    def after(self, foo, eventname, x):
        self.assertListenerPreconditions(42, x, foo, eventname)
        foo.x = 0  # should persist after call to update() returns

    def testAfterWatcher(self):
        self.foo.add_listener_after('update', self.after)
        self.foo.update(42)
        self.assertEqual(0, self.foo.x)
            
    def gen(self, foo, eventname, x):
        self.before(foo, eventname, x)
        after_kw = yield
        self.after(foo, eventname, **after_kw)

    def testGenWatcher(self):
        self.foo.add_listener_gen('update', self.gen)
        self.foo.update(42)
        self.assertEqual(0, self.foo.x)
        self.assertTrue(self.before_called)

    def testRemoveWatcher(self):
        lid = self.foo.add_listener_before('update', self.before)
        self.foo.remove_listener(lid)
        self.testNoWatcher()

class WatchableMethodTest(unittest.TestCase):
    class MethodWatchableUser(WatchableMixin):
        x = 5

        @method('update')
        def watchableUpdate(self, new_x):
            self.x = new_x
            return self.x

    def genWatcher(self, foo, eventname, args, kw):
        self.assertEqual('update', eventname)
        self.assertEqual(6, foo.x)
        self.assertEqual((7,), args)
        self.assertEqual({}, kw)
        after_kw = yield
        self.assertEqual({'args': (7,), 'kw': {}, 'result': 7},
            after_kw)
        self.assertEqual(7, foo.x)
        foo.x = 8

    def testWatchableMethod(self):
        foo = self.MethodWatchableUser()
        self.assertEqual(5, foo.x)
        rv = foo.watchableUpdate(6)
        self.assertEqual(6, rv)
        self.assertEqual(6, foo.x)
        lid = foo.add_listener_gen('update', self.genWatcher)
        rv = foo.watchableUpdate(7)
        self.assertEqual(7, rv)
        self.assertEqual(8, foo.x)
        foo.remove_listener(lid)
        rv = foo.watchableUpdate(9)
        self.assertEqual(9, rv)
        self.assertEqual(9, foo.x)


if __name__ == '__main__':
    unittest.main()


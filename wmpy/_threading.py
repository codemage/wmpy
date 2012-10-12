import os
import sys
import threading
import time

from . import _logging
_logger, _dbg, _info, _warn = _logging.get_logging_shortcuts(__name__)

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

    def __repr__(self):
        return "WatchedThread(%s, %s)" % (self.name,
            { key: getattr(self, key) for key in
              ['active', 'died', 'will_throw']})

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

        self._dbg = _logger.getChild("WatchedThread.%s" % self.name).debug
        self._dbg("Created %r", self)

    def run(self):
        self.active = True
        self._dbg("Started %r", self)
        try:
            self.rv = self.target()  # pylint: disable=W0201
            self._dbg("Finished %r", self)
        except BaseException:
            _logger.exception("uncaught exception in thread %s" % self.name)
            with self._lock:
                self.exc_info = sys.exc_info()
                self.died = True
            if self.fail_cb is None:
                sys.stdout.flush()
                sys.stderr.flush()
                os._exit(1)  # pylint: disable=W0212
            else:
                self.fail_cb()
        finally:
            with self._any_exit:
                self.active = False
                self._any_exit.notify_all()
            self._dbg("Finally %r", self)

    @property
    def will_throw(self):
        return self.exc_info is not None

    def reraise(self):
        self._dbg("Reraise %r", self)
        if self.exc_info is not None:
            with self._lock:
                if self.exc_info is None:
                    return # it went away while getting the lock
                try:
                    raise self.exc_info[0](self.exc_info[1]).with_traceback(self.exc_info[2])
                finally:
                    self.exc_info = None # clear ref cycle

    def join(self, *args, **kw):
        self._dbg("Join %r", self)
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
                _dbg('loop in WatchedThread.join_all%r', threads)
                for thread in threads:
                    thread.reraise()
                time_left = end_time - time.time() \
                            if end_time is not None \
                            else None
                if (time_left is not None and time_left <= 0) or \
                   not any(thread.active for thread in threads):
                    return
                cls._any_exit.wait(time_left)

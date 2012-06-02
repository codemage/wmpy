from collections import namedtuple
from fcntl import fcntl, F_SETFL, F_GETFL
import io
import os
import select

from . import _logging
_logger, _dbg, _warn, _error = _logging.get_logging_shortcuts(__name__)

class ClosingContextMixin(object):
    """ Mixin for objects that just want close() on __exit__ """
    __slots__ = []
    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()

class Pipe(namedtuple('_Pipe', 'r w'), ClosingContextMixin):
    """ Context manager that wraps `os.pipe()`, yielding the read and
        write sides of the pipe after wrapping them with io.open;
        ensures that both ends are closed on exit from the with block.
    """
    __slots__ = []
    def __new__(cls, r_bufsize=0, w_bufsize=0):
        rfd, wfd = os.pipe()
        super(Pipe, cls).__new__(cls,
            io.open(rfd, 'rb', r_bufsize),
            io.open(wfd, 'wb', w_bufsize))

    if False: # for linter
        def __init__(self, r, w):
            ClosingContextMixin.__init__(self)
            self.r = r
            self.w = w

    def close(self):
        self.r.close()
        self.w.close()

class Poller(ClosingContextMixin, object):
    """ Simple callback-based wrapper around select.poll()
    """
    IN = select.POLLIN | select.POLLPRI
    OUT = select.POLLOUT
    ERR = select.POLLERR
    def __init__(self):
        ClosingContextMixin.__init__(self)
        self._poll = select.poll()
        self._handlers = {}
    def register(self, fd, events, handler):
        make_nonblocking(fd)
        self._handlers[fd] = handler
        self._poll.register(fd, events)
    def unregister(self, fd):
        del self._handlers[fd]
        self._poll.unregister(fd)
    def close(self):
        for fd in self._handlers:
            self._poll.unregister(fd)
        # poll() objects aren't actually close()-able
        del self._poll
    def poll(self, *args):
        empty = True
        for fd, event in self._poll.poll(*args):
            empty = False
            self._handlers[fd](fd, event)
        return empty

def make_nonblocking(fd):
    fcntl(fd, F_SETFL, fcntl(fd, F_GETFL) | os.O_NONBLOCK)


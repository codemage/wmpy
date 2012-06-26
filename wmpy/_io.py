from __future__ import absolute_import

try:
    from fcntl import fcntl, F_SETFL, F_GETFL
except:
    fcntl = None
import io
import os
import select

from . import _logging
_logger, _dbg, _info, _warn = _logging.get_logging_shortcuts(__name__)

class ClosingContextMixin(_logging.InstanceLoggingMixin,
                          object):
    """ Mixin for objects that just want close() on __exit__ """
    __slots__ = ()
    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        # self._dbg('%x.__exit__ => close()', id(self))
        self.close()

class Pipe(ClosingContextMixin,
           # _logging.InstanceLoggingMixin,
           ):
    """ Context manager that wraps `os.pipe()`, yielding the read and
        write sides of the pipe after wrapping them with io.open;
        ensures that both ends are closed on exit from the with block.
    """
    __slots__ = ('r', 'w')
    def __init__(self, r_bufsize=0, w_bufsize=0):
        super(Pipe, self).__init__()
        rfd, wfd = os.pipe()
        self.r = io.open(rfd, 'rb', r_bufsize)
        self.w = io.open(wfd, 'wb', w_bufsize)

    def __iter__(self):
        return iter((self.r, self.w))

    def close(self):
        if not self.r.closed:
            self.r.close()
        if not self.w.closed:
            self.w.close()

class Poller(ClosingContextMixin,
             _logging.InstanceLoggingMixin,
             object):
    """ Simple callback-based wrapper around select.poll()
    """
    if hasattr(select, 'POLLIN'):
        IN = select.POLLIN | select.POLLPRI
        OUT = select.POLLOUT
        ERR = select.POLLERR

    def __init__(self):
        super(Poller, self).__init__()
        if not hasattr(self, 'IN'):
            raise ValueError("no select.poll() on this os")
        self._poll = select.poll()
        self._handlers = {}
    def register(self, fd, events, handler):
        if not isinstance(fd, int):
            fd = fd.fileno()
        make_nonblocking(fd)
        self._handlers[fd] = handler
        self._poll.register(fd, events)
    def unregister(self, fd):
        if not isinstance(fd, int):
            fd = fd.fileno()
        if fd not in self._handlers:
            raise ValueError('fd not registered')
        del self._handlers[fd]
        self._poll.unregister(fd)
    def close(self):
        if not hasattr(self, '_poll'):
            return
        for fd in self._handlers:
            self._poll.unregister(fd)
        # poll() objects aren't actually close()-able
        del self._poll
    def poll(self, *args):
        empty = True
        events = self._poll.poll(*args)
        self._dbg('poll() events => %r fds = %r', events, self._handlers)
        for fd, event in events:
            empty = False
            self._dbg('poll() enter handler[%d] event=%d', fd, event)
            self._handlers[fd](fd, event)
        self._dbg('exit poll()')
        return empty

def make_nonblocking(fd):
    if fcntl is not None:
        fcntl(fd, F_SETFL, fcntl(fd, F_GETFL) | os.O_NONBLOCK)
    else:
        raise ValueError("unsupported without fcntl and os.O_NONBLOCK")


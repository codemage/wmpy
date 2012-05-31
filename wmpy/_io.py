from contextlib import contextmanager
from errno import EAGAIN
from fcntl import fcntl, F_SETFL, F_GETFL
import io
import os
import select
from select import POLLIN, POLLOUT, POLLERR

from . import _logging
_logger, _dbg, _warn, _error = _logging.get_logging_shortcuts(__name__)

@contextmanager
def io_pipe():
    """ Context manager that wraps `os.pipe()`, yielding the read and
        write sides of the pipe after wrapping them with io.open;
        ensures that both ends are closed on exit from the with block.
    """
    r_fd, w_fd = os.pipe()
    with io.open(r_fd, 'rb', 0) as r, \
    	 io.open(w_fd, 'wb', 0) as w:
    	yield r, w

class Poller(object):
    """ Simple callback-based wrapper around select.poll()
    """
    def __init__(self):
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
        pass
    def poll(self, *args):
        empty = True
        for fd, event in self._poll.poll(*args):
            empty = False
            self._handlers[fd](fd, event)
        return empty

def make_nonblocking(fd):
    fcntl(fd, F_SETFL, fcntl(fd, F_GETFL) | os.O_NONBLOCK)


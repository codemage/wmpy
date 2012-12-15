import collections
try:
    from fcntl import fcntl, F_SETFL, F_GETFL
except:
    fcntl = None
import hashlib
import io
import os
import os.path
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

class FileHashCache(object):
    READ_BATCH_SIZE = 1024*1024
    # note: unix filenames are bytes, so we try to avoid translating paths
    #       provided as bytes to str and back.

    Entry = collections.namedtuple('Entry', 'hashval size mtime')
    def __init__(self, cache_path):
        self.cache = {}
        self.cache_path = cache_path
        if os.path.isfile(cache_path):
            self.load()
        else:
            _dbg("hash cache at %s not present, starting from scratch", cache_path)

    def load(self):
        _dbg("reading hash cache at %s", self.cache_path)
        with open(self.cache_path, 'rb') as cache_fp:
            for cache_entry in cache_fp:
                if cache_entry.strip() == b'':
                    continue
                try:
                    hashval, size, mtime, path = cache_entry.strip().split(b' ', 3)
                    self.cache[path] = self.Entry(str(hashval, 'utf-8'), int(size), float(mtime))
                except ValueError:
                    _warn("ignoring invalid cache entry %a", cache_entry.strip())
        _dbg("read cache with %s entries from %s", len(self.cache), self.cache_path)

    @classmethod
    def calculate_hash(cls, path):
        #_dbg("calculating hash for %s", path)
        buf = bytearray(cls.READ_BATCH_SIZE)
        with open(path, 'rb', buffering=0) as fp:
            bytes_read = fp.readinto(buf)
            hasher = hashlib.sha1(buf[:bytes_read])
            while bytes_read > 0:
                bytes_read = fp.readinto(buf)
                hasher.update(buf[:bytes_read])
        #_dbg("hash for %s is %s", path, hasher.hexdigest())
        return hasher.hexdigest()

    def find_hash(self, path):
        # should we abspath here?
        if isinstance(path, bytes):
            key = path
        else:
            key = str(path).encode('utf-8')
        if not os.path.isfile(path):
            self.cache.pop(key, None)
            return ''

        st = os.stat(path)
        if key in self.cache:
            entry = self.cache[key]
            if entry.size == st.st_size and entry.mtime == st.st_mtime:
                return entry.hashval
            # else fall through and re-calculate

        hashval = self.calculate_hash(path)
        self.cache[key] = self.Entry(hashval, st.st_size, float(st.st_mtime))
        return hashval

    def save(self):
        _dbg("saving hash cache to %s with %s entries", self.cache_path, len(self.cache))
        with open(self.cache_path, 'wb') as cache_fp:
            for path, entry in self.cache.items():
                cache_fp.write('{} {} {} '.format(entry.hashval, entry.size, entry.mtime).encode('utf-8'))
                cache_fp.write(path)
                cache_fp.write(b'\n')

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
    def __init__(self, base_path, cache_path):
        self.cache = {}
        self.by_hash = collections.defaultdict(set)
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
                    hashval, size, mtime, path_key = cache_entry.strip().split(b' ', 3)
                    self.cache[path_key] = self.Entry(str(hashval, 'utf-8'), int(size), float(mtime))
                    self.by_hash[hashval].add(path_key)
                except ValueError:
                    _warn("ignoring invalid cache entry %a", cache_entry.strip())
        _dbg("read cache with %s entries from %s", len(self.cache), self.cache_path)

    @classmethod
    def calculate_hash(cls, abs_path):
        #_dbg("calculating hash for %s", path)
        buf = bytearray(cls.READ_BATCH_SIZE)
        with open(abs_path, 'rb', buffering=0) as fp:
            bytes_read = fp.readinto(buf)
            hasher = hashlib.sha1(buf[:bytes_read])
            while bytes_read > 0:
                bytes_read = fp.readinto(buf)
                hasher.update(buf[:bytes_read])
        #_dbg("hash for %s is %s", path, hasher.hexdigest())
        return hasher.hexdigest()

    @classmethod
    def path_to_key(cls, path):
        """ Whether paths are bytes or str is OS-dependent; we key based on
            bytes, UTF-8 encoding if necessary. """
        if isinstance(path, bytes):
            return path
        else:
            return str(path).encode('utf-8')

    def find_hash(self, path):
        """ Find a hash in the cache for path, which should be relative to base_path
            as passed to the constructor. """
        key = self.path_to_key(path)
        abs_path = os.path.join(self.base_path, path)
        if not os.path.isfile(abs_path):
            self.cache.pop(key, None)
            return ''

        st = os.stat(abs_path)
        if key in self.cache:
            entry = self.cache[key]
            if entry.size == st.st_size and entry.mtime == st.st_mtime:
                return entry.hashval
            # else fall through and re-calculate

        hashval = self.calculate_hash(abs_path)
        self.cache[key] = self.Entry(hashval, st.st_size, float(st.st_mtime))
        self.by_hash[hashval].add(key)
        return hashval

    def paths_for_hash(self, hashval):
        if hashval not in self.by_hash:
            return set()
        else:
            return self.by_hash[hashval]

    def save(self):
        _dbg("saving hash cache to %s with %s entries", self.cache_path, len(self.cache))
        with open(self.cache_path, 'wb') as cache_fp:
            for path, entry in self.cache.items():
                cache_fp.write('{} {} {} '.format(entry.hashval, entry.size, entry.mtime).encode('utf-8'))
                cache_fp.write(path)
                cache_fp.write(b'\n')

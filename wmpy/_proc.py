""" wmpy._proc -- tools for dealing with subprocesses """
from collections import namedtuple
import os
import select
import subprocess as sp

from . import _io as wmio
from . import _logging
_logger, _dbg, _warn, _error = _logging.get_logging_shortcuts(__name__)

class CmdException(Exception):
    def __init__(self, proc, stdout, stderr, *args, **kwargs):
        self.proc = proc
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = self.proc.returncode
        super(Exception, self).__init__(*args, **kwargs)

_CmdBase = namedtuple('_CmdBase', 'argv popen_kwargs')
class Cmd(_CmdBase):
    """ Represents a runnable command.
    
        This is basically a stored set of parameters for subprocess.Popen.
        It is designed to be immutable, though that's not enforced.
        Writing to the attributes is not recommended.

        The `proc()` method just invokes the command and returns the Popen
        object.  `run()` defaults stdout and stderr to sp.PIPE if not
        specified, runs communicate(), and either returns the standard
        output and prints the stderr, or (for nonzero return codes) throws a
        CmdException with both attached.
    """
    __slots__ = ()
    def __new__(cls, *argv, **popen_kwargs):
        return _CmdBase.__new__(cls, argv, popen_kwargs)
    
    if False:
        def __init__(self, argv, popen_kwargs): # for linter
            self.argv = argv
            self.popen_kwargs = popen_kwargs

    def update(self, **popen_kwargs):
        """ Returns a new Cmd with the Popen keywords specified
            updated, with the previous settings operating as defaults.
        """
        return Cmd(self.argv,
            **dict(self.popen_kwargs, **popen_kwargs))

    def append(self, *extra_argv):
        """ Returns a new Cmd with added arguments. """
        return Cmd(self.argv+extra_argv, self.popen_kwargs)

    def _popen(self, _popen_kw):
        if _popen_kw.get('shell'):
            # shell=True -> should be a single cmd, join args:
            # don't escape, we want to allow shell metacharacters if we are
            # doing this at all
            return sp.Popen(self.argv.join(' '), **_popen_kw)
        else:
            return sp.Popen(self.argv, **_popen_kw)

    def popen(self):
        _dbg("%r.proc()", self)
        return self._popen(self.popen_kwargs)

    def run(self, stdin_data=''):
        _dbg("%r.run(<%d bytes>)", self, len(stdin_data))
        kwargs_with_pipe = dict({'stdin': sp.PIPE, 'stdout': sp.PIPE},
            **self.popen_kwargs)
        proc = self._popen(kwargs_with_pipe)
        stdout, stderr = proc.communicate(stdin_data)
        if proc.returncode != 0:
            raise CmdException(proc, stdout, stderr,
                "Error running {}".format(self))
        if stderr:
            print stderr
        return stdout

    def __or__(self, other):
        if isinstance(other, Cmd):
            return CmdPipeline(self, other)
        if isinstance(other, CmdPipeline):
            other.commands = [self].extend(other.commands)
        raise TypeError("can't pipe to {} from {}".format(
            repr(other), self))

    def __str__(self):
        return "%s(%s)" % (type(self).__name__, ' '.join(self.argv))

    def __repr__(self):
        return "%s(*%r, **%r)" % (type(self).__name__,
            self.argv, self.popen_kwargs)

class PopenPipeline(wmio.ClosingContextMixin, object):
    """ More or less like a Popen instance on a shell-style pipeline of
        commands.  Unix only.  Construct with any number of Cmd instances as
        positional parameters; these represents the commands to be run.

        The `stdin`, `stdout`, and `stderr` keyword parameters operate on the
        pipeline as a whole; `stdin` feeds the first command, `stdout` comes
        from the last, and all `stderr` streams are merged into the stderr
        handle.  Intermediate processes' stdin and stdout streams are paired
        vit pipes internally.  All three default to `subprocess.PIPE`,
        resulting in attributes on the instance with file-like objects for
        accessing them.  `None` can be passed explicitly to request that a
        stream be inherited from the Python process.

        Any additional keyword parameters are passed to every `Popen` instance
        used to construct the pipeline.

        Calling `poll()` or `wait()` will cause every process in the pipeline
        to be polled or waited on, respectively.

        Has a `close()` method, which closes any pipes opened by the process;
        it does NOT close any that were passed in from outside.  May be used
        as a context manager to ensure that the pipes are closed promptly.

        Has a `returncode` property, which is `None` as long as any process in
        the pipeline is running; afterwards it is the return code of the last
        process.

        Has an iterable `procs` property is a sequence of the `subprocess.Popen`
        instances that are linked together to form the pipeline.  This may be
        used to examine individual processes' return codes or pids or to
        send them signals.  Attempting to access the I/O stream attributes
        of the component `Popen` instances is not recommended.
    """
    def __init__(self, first_cmd, *remaining_cmds, **kw):
        # keyword-only parameters for stream redirection:
        stdin = kw.pop('stdin', sp.PIPE)
        stdout = kw.pop('stdout', sp.PIPE)
        stderr = kw.pop('stderr', sp.PIPE)

        wmio.ClosingContextMixin.__init__(self)

        self.proc = first_cmd.update(
            stdin=stdin,
            stdout=sp.PIPE if len(remaining_cmds) > 0 else stdout,
            stderr=stderr,
            **kw).popen()
        self.stdin = self.proc.stdin
        if stderr == sp.PIPE:
            # we want to have one stderr pipe for the whole pipeline, so
            # grab it and pass it on down the pipeline:
            self.stderr = stderr = self.proc.stderr
        else:
            self.stderr = None
        if len(remaining_cmds) == 0:
            # end of the line; set stdout from this proc, which gets
            # propagated back up as the whole pipeline's stdout:
            self.next = None
            self.stdout = self.proc.stdout
        else:
            self.next = type(self)(  # build another instance of same type:
                    stdin=self.proc.stdout,
                    stdout=stdout, stderr=stderr,
                    *remaining_cmds, **kw)
            # out stdout was made into the next cmd's stdin, close it here:
            self.proc.stdout.close()
            # our "stdout" should come from the end of the pipeline:
        
        self._communicate_called = False
        self._poller = None
        self._close_pipe = None
        self._open_pipes = None
        self.stdin_data = None
        self.stdout_data = None
        self.stderr_data = None

    @property
    def procs(self):
        cur = self
        while cur is not None:
            yield cur.proc
            cur = cur.next
            self.stdout = self.next.stdout

    @property
    def returncode(self):
        for proc in self.procs:
            if proc.returncode is None:
                return None
            rv = proc.returncode
        return rv

    def poll(self):
        for proc in self.procs:
            if proc.poll() is None:
                return None
            rv = proc.returncode
        return rv

    def wait(self):
        for proc in self.procs:
            rv = proc.wait()
        return rv

    def close(self):
        for item in (self.proc.stdin, self.proc.stdout,
                     self.stderr, self._poller, self.next):
            if item is not None:
                item.close()

    def _comm_setup_poller(self, stdin_data, poller=None):
        if getattr(self, '_communicate_called', False):
            raise ValueError(">1 call to PopenPipeline.communicate()")
        self._communicate_called = True

        self.stdin_data = memoryview(stdin_data)
        self.stdout_data = []
        self.stderr_data = []

        self._open_pipes = 0
        if poller is None:
            poller = self._poller = wmio.Poller()

        def _register(fp, ev, cb):
            if fp:
                wmio.make_nonblocking(fp)
                poller.register(fp, ev, cb)
                self._open_pipes += 1

        _register(self.stdin, poller.IN, self.send_stdin)
        _register(self.stdout, poller.OUT,
            self.read_cb(self.stdout, self.stdout_data))
        _register(self.stderr, poller.OUT,
            self.read_cb(self.stderr, self.stderr_data))
        def _close_pipe(self, fp):
            poller.unregister(fp)
            fp.close()
            self._open_pipes -= 1
        self._close_pipe = _close_pipe
        
        return poller

    def communicate(self, stdin_data=''):
        with self, self._comm_setup_poller(stdin_data) as poller:
            while self._open_pipes > 0 and self.poll() is None:
                poller.poll(250)
        # self.close() called implicitly from with block

        self.stdout_data = ''.join(self.stdout_data)
        self.stderr_data = ''.join(self.stderr_data)
        return self.stdout_data, self.stderr_data

    def communicate_async(self, poller, stdin_data=''):
        self._comm_setup_poller(stdin_data, poller)
        return self

    def send_stdin(self, fd, event):
        if event & wmio.Poller.ERR:
            if not self.stdin_data:
                self._close_pipe(self.stdin)
            # else we will probably raise an IOError shortly...
            # (this is what we want to do anyway)
        elif not (event & wmio.Poller.OUT):
            raise Exception("unknown event %x on %d", event, fd)
            
        if self.stdin_data:
            written = os.write(fd, self.stdin_data[:select.PIPE_BUF])
            self.stdin_data = self.stdin_data[written:]

        if not self.stdin_data:
            self._close_pipe(self.stdin)

    def read_cb(self, fp, read_data_list):
        def do_read(self, fd, _event):
            data = os.read(fd, 512)
            if len(data) == 0:
                self._close_pipe(fp)
            else:
                read_data_list.append(data)
        return do_read

class CmdPipeline(Cmd):
    def _popen(self, pipeline_kw):
        return PopenPipeline(*self.argv, **pipeline_kw)

    def __or__(self, other):
        if not isinstance(other, Cmd):
            raise TypeError("Can't pipe to %s" % other)
        return CmdPipeline(self.argv[:] + [other], self.popen_kwargs)

    def __str__(self):
        return '(%s)' % ' | '.join(map(str, self.argv))

def env_plus(**kwargs):
    """ Returns the environment variable map, with updated
        settings from the keyword args.
    """
    return dict(os.environ, **kwargs)


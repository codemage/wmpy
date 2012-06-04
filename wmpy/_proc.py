""" wmpy._proc -- tools for dealing with subprocesses """
from __future__ import absolute_import

import os, os.path
import sys

def _generic_main_boilerplate(module_globals, expected_package, module_name):
    # This is standard boilerplate for modules that are loaded as part of a
    # package and want to have a _main() function, and who want their _main
    # to run in the context of the version of the module attached to the
    # package.  Since the whole point is to get to a sane import/sys.path
    # state, it can't be extracted into an importable function without
    # introducing a dependcency on the module it's defined in being installed
    # system-wide.
    #
    # This avoids the issue where there are two parallel copies of the module,
    # one called __main__ and one by its normal name, with different versions
    # of all of the types and module-level state and constants.
    #
    # Modules using this boilerplate can be run via python -m 'pkg.mod', python
    # pkg/mod.py or even 'cd pkg; python mod.py' and will work regardless.
    #
    # It's written so that if I ever to decide to just stick it in a module in
    # the system path, it can be imported and called and still work.
    if module_globals['__name__'] != '__main__':
        return

    if module_globals.get('__package__') is None:
        module_globals['__package__'] = expected_package
    package = module_globals['__package__']
    full_name = '%s.%s' % (package, module_name)

    if os.path.abspath(os.path.dirname(__file__)) == \
       os.path.abspath(sys.path[0]):
        # python pkg/mod.py mucks up the path, fix it:
        sys.path[0] += '/..' * len(package.split('.'))

    __import__(full_name, globals(), locals(), None, 0)
    sys.modules[full_name]._main() # pylint: disable=W0212
    sys.exit(0)

_generic_main_boilerplate(globals(), 'wmpy', '_proc')
 
# annoying boilerplate is done, back to our regularly scheduled programming:
import errno
import logging
import pipes
import select
import subprocess as sp

from . import _io
from . import _logging

_logger, _dbg, _warn, _error = _logging.get_logging_shortcuts(__name__)

class CmdException(Exception):
    def __init__(self, proc, stdout, stderr, *args, **kwargs):
        self.proc = proc
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = self.proc.returncode
        super(Exception, self).__init__(*args, **kwargs)

class Cmd(_logging.InstanceLoggingMixin):
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
    __slots__ = ('argv', 'popen_kwargs')
    def __init__(self, *argv, **popen_kwargs):
        super(Cmd, self).__init__()
        self.argv = argv
        self.popen_kwargs = popen_kwargs

    def update(self, **popen_kwargs):
        """ Returns copy of self with the Popen keywords specified
            updated, with the previous settings operating as defaults.
        """
        return type(self)(*self.argv,
            **dict(self.popen_kwargs, **popen_kwargs))

    def default(self, **popen_default_kwargs):
        """ As for update(), but will not change existing keys. """
        return type(self)(*self.argv,
            **dict(popen_default_kwargs, **self.popen_kwargs))

    def append(self, *extra_argv):
        """ Returns a copy of self with added arguments. """
        return type(self)(tuple(self.argv+extra_argv), self.popen_kwargs)

    def _popen(self, _popen_kw):
        if _popen_kw.get('shell'):
            # shell=True -> should be a single cmd, join args:
            # don't escape, we want to allow shell metacharacters if we are
            # doing this at all
            argv = ' '.join(self.argv)
        else:
            argv = self.argv
        return sp.Popen(argv, **_popen_kw)

    def popen(self):
        """ Returns a Popen instance instantiated based on my settings. """
        self._dbg("popen() %r",
            self._kw_desc(self.popen_kwargs))
        return self._popen(self.popen_kwargs)

    @staticmethod
    def _fd_desc(fd):
        if fd == sp.PIPE:
            return 'PIPE'
        elif fd == sp.STDOUT:
            return 'STDOUT'
        elif hasattr(fd, 'fileno'):
            if fd.closed:
                return '_'
            else:
                return fd.fileno()
        else:
            return fd

    @classmethod
    def _kw_desc(cls, kwargs):
        kw_desc = kwargs.copy()
        for fdarg in 'stdin', 'stdout', 'stderr':
            fd = cls._fd_desc(kw_desc.pop(fdarg, None))
            if fd is not None:
                kw_desc[fdarg] = fd
        preexec_fn = kw_desc.pop('preexec_fn', None)
        if preexec_fn is not None:
            kw_desc['preexec_fn'] = preexec_fn.func_name + '()'
        return kw_desc

    def run(self, stdin_data=''):
        kwargs_with_pipe = dict({'stdin': sp.PIPE, 'stdout': sp.PIPE},
            **self.popen_kwargs)
        self._dbg("run(<%d bytes>) %r", len(stdin_data),
            self._kw_desc(kwargs_with_pipe))
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

    @property
    def _logging_desc(self):
        return ' '.join(map(pipes.quote, self.argv))

    def __str__(self):
        return "%s(%s)" % (type(self).__name__, self._logging_desc)

    def __repr__(self):
        return "%s(*%r, **%r)" % (type(self).__name__,
            self.argv, self.popen_kwargs)

class PopenPipeline(_io.ClosingContextMixin,
                    _logging.InstanceLoggingMixin,
                    object):
    """ More or less like a Popen instance on a shell-style pipeline of
        commands.  Unix only.  Construct with any number of Cmd instances as
        positional parameters; these represent the commands to be run.

        The `stdin`, `stdout`, and `stderr` keyword parameters operate on the
        pipeline as a whole; `stdin` feeds the first command, `stdout` comes
        from the last, and all `stderr` streams are merged into the stderr
        handle.  Intermediate processes' stdin and stdout streams are paired
        vit pipes internally.

        Any additional keyword parameters are passed to every `Popen` instance
        used to construct the pipeline.

        Calling `poll()` or `wait()` will cause every process in the pipeline
        to be polled or waited on, respectively.

        Has a `close()` method, which closes any pipes opened by the process;
        it does NOT close any that were passed in from outside.  May be used
        as a context manager to ensure that the pipes are closed promptly.

        Has a `returncodes` property, which is `None` as long as any process in
        the pipeline is running; afterwards it is a tuple of the returncodes
        of the processes in the pipeline.  `returncode` is a shortcut to the
        last value in `returncodes`, and is also None until all children
        exit.  Both are only updated on calls to `poll()` or `wait()`.

        Has an iterable `procs` property is a sequence of the `subprocess.Popen`
        instances that are linked together to form the pipeline.  This may be
        used to examine individual processes' pids or to send them signals.
        Attempting to access the I/O stream attributes of the component `Popen`
        instances is not recommended.
    """
    def __init__(self, *commands, **kw):
        # keyword-only parameters for stream redirection amd preexec_fn:
        stdin = kw.pop('stdin', None)
        stdout = kw.pop('stdout', None)
        stderr = kw.pop('stderr', None)
        preexec_fn = kw.pop('preexec_fn', None)

        super(PopenPipeline, self).__init__()

        # this is state for communicate():
        self._communicate_called = False
        self._poller = None
        self._close_pipe = None
        self._open_pipes = None
        self.stdin_data = None
        self.stdout_data = None
        self.stderr_data = None

        # okay, let's get to work...
        self.cmds = []
        self.procs = []
        self._parent_fds = []
        self._orig_preexec_fn = preexec_fn
        self.stderr = None
        should_close_stderr = False
        if stderr is sp.PIPE:
            # we want to have one stderr pipe for the whole pipeline, so
            # we set it up ourselves:
            self.stderr, stderr = _io.Pipe()
            self._parent_fds.append(self.stderr.fileno())
            should_close_stderr = True
        try:
            for i, cmd in enumerate(commands):
                is_last_cmd = (i == len(commands) - 1)
                self.cmds.append(cmd.update(
                    stdin=stdin,
                    stdout=stdout if is_last_cmd else sp.PIPE,
                    stderr=stderr,
                    preexec_fn=self._preexec,
                    **kw))
                self.procs.append(self.cmds[i].popen())
                _fd = lambda fp: fp if isinstance(fp, int) else (fp.fileno() if fp and not fp.closed else '_')
                p = self.procs[-1]
                self._dbg('[%d]: in=%s out=%s err=%s', i, _fd(p.stdin), _fd(p.stdout), _fd(p.stderr))
                if i > 0:
                    # stdin is connected the previous command in the pipeline, we
                    # don't want to hold on to it:
                    stdin.close()
                if not is_last_cmd:
                    # next command's stdin should use our stdout:
                    stdin = self.procs[i].stdout
                if i == 0:
                    if self.procs[0].stdin:
                        self._dbg('adding stdin %s to parent fds:', self.procs[0].stdin.fileno())
                        self._parent_fds.append(self.procs[0].stdin.fileno())
                    elif stdin not in (None, STDOUT):
                        self._dbg('adding stdin %s to parent fds:', _fd(stdin))
                        self._parent_fds.append(_fd(stdin))
        except BaseException:
            self.close(suppress_exc=True)
            raise
        finally:
            if should_close_stderr:
                stderr.close()

        # these are only used in self._preexec:
        del self._parent_fds
        del self._orig_preexec_fn

        # stdin and stdout come from the ends of the pipeline:
        self.stdin = self.procs[0].stdin
        self.stdout = self.procs[-1].stdout

        self._returncodes = None

    def _preexec(self):
        for fd in self._parent_fds:
        #    sys.stderr.write('PID {0} preexec: closing {1}\n'.format(os.getpid(), fd))
            os.close(fd)
        #os.system('exec 1>&2; echo Files for PID {0}:; ls -l /proc/{0}/fd'.format(os.getpid()))
        if self._orig_preexec_fn is not None:
            return self._orig_preexec_fn()

    @property
    def returncodes(self):
        if self._returncodes is not None:
            return self._returncodes
        if any(p.returncode is None for p in self.procs):
            return None
        self._returncodes = tuple(p.returncode for p in self.procs)
        return self._returncodes

    @property
    def returncode(self):
        if self.returncodes is None:
            return None
        return self.returncodes[-1]

    def poll(self):
        if any(p.poll() is None for p in self.procs):
            return None
        return self.returncodes

    def wait(self):
        return tuple(p.wait() for p in self.procs)

    @staticmethod
    def _doclose(obj, suppress_exc):
        if obj is None:
            return
        try:
            obj.close()
        except BaseException:
            if not suppress_exc:
                raise
            self._warn("suppressed exception in _doclose()", exc_info=True)

    def close(self, suppress_exc=False):
        try:
            for proc in self.procs:
                for stream in proc.stdin, proc.stdout, proc.stderr:
                    self._doclose(stream, suppress_exc)
            self._doclose(self._poller, suppress_exc)
        except BaseException:
            if not suppress_exc:
                raise
            self._warn("suppressed exception in close()", exc_info=True)

    def _comm_setup_poller(self, stdin_data, poller=None):
        if getattr(self, '_communicate_called', False):
            raise ValueError(">1 call to PopenPipeline.communicate()")
        self._communicate_called = True

        if stdin_data:
            #self._dbg('got stdin data, writing to %s', self.stdin.fileno())
            self.stdin_data = memoryview(stdin_data)
        elif self.stdin:
            #self._dbg('no stdin data, closing %s', self.stdin.fileno())
            self.stdin.close()
            self.stdin = None

        self.stdout_data = []
        self.stderr_data = []

        self._open_pipes = 0
        if poller is None:
            poller = self._poller = _io.Poller()

        def _close_pipe(fp):
            #desc = 'stdin' if fp is self.stdin else (
            #       'stdout' if fp is self.stdout else 'stderr')
            #self._dbg("closing %s fd %d", desc, fp.fileno())
            poller.unregister(fp)
            fp.close()
            self._open_pipes -= 1
        self._close_pipe = _close_pipe

        def _register(_desc, fp, ev, cb):
            if fp:
                _io.make_nonblocking(fp)
                poller.register(fp, ev, cb)
                self._open_pipes += 1

        _register('stdin', self.stdin, poller.IN, self.send_stdin)
        _register('stdout', self.stdout, poller.OUT,
            self.read_cb(self.stdout, self.stdout_data))
        _register('stderr', self.stderr, poller.OUT,
            self.read_cb(self.stderr, self.stderr_data))
        
        return poller

    def communicate(self, stdin_data=''):
        prev_codes = [None] * len(self.procs)
        with self, self._comm_setup_poller(stdin_data) as poller:
            while self._open_pipes > 0 or self.poll() is None:
                codes = [p.poll() for p in self.procs]
                for i, (prev, cur) in enumerate(zip(prev_codes, codes)):
                    if cur is not None and prev is None:
                        _dbg('[%d]: "%s" exited %s', i, self.cmds[i]._logging_desc, cur)
                prev_codes = codes
                if self.stdin_data:
                    self.send_stdin(self.stdin.fileno(), poller.OUT)
                poller.poll(1000)
        # self.close() called implicitly from with block

        self.stdout_data = ''.join(self.stdout_data)
        self.stderr_data = ''.join(self.stderr_data)
        return self.stdout_data, self.stderr_data

    def communicate_async(self, poller, stdin_data=''):
        self._comm_setup_poller(stdin_data, poller)
        return self

    def send_stdin(self, fd, event):
        if event & _io.Poller.ERR:
            if not self.stdin_data: 
                # we were done anyway, never mind
                self._close_pipe(self.stdin)
                return
            # else we will probably raise an IOError shortly...
            # (this is what we want to do anyway)
        elif not (event & _io.Poller.OUT):
            raise Exception("unknown event %x on %d", event, fd)
            
        if self.stdin_data:
            try:
                written = os.write(fd, self.stdin_data[:select.PIPE_BUF])
                #self._dbg('%d bytes written to stdin', written)
                self.stdin_data = self.stdin_data[written:]
            except IOError, exc:
                if exc.errno != errno.EAGAIN:
                    raise

        if not self.stdin_data:
            self._close_pipe(self.stdin)

    def read_cb(self, fp, read_data_list):
        def do_read(fd, _event):
            data = os.read(fd, 512)
            if len(data) == 0:
                self._close_pipe(fp)
            else:
                read_data_list.append(data)
        do_read.func_name = 'read_stderr' if fp is self.stderr else 'read_stdout'
        return do_read

class CmdPipeline(Cmd):
    @property
    def commands(self):
        return self.argv

    def _popen(self, pipeline_kw):
        return PopenPipeline(*self.commands, **pipeline_kw)

    def __or__(self, other):
        if not isinstance(other, Cmd):
            raise TypeError("Can't pipe to %s" % other)
        return CmdPipeline(*(self.commands[:] + (other,)),
            **self.popen_kwargs)

    def __str__(self):
        return '(%s)' % ' | '.join(map(str, self.commands))

    @property
    def _logging_desc(self):
        return ' | '.join(cmd._logging_desc for cmd in self.commands)

def env_plus(**kwargs):
    """ Returns the environment variable map, with updated
        settings from the keyword args.
    """
    return dict(os.environ, **kwargs)

def _main():
    logging.basicConfig(level=logging.INFO)
    #logging.getLogger('wmpy._io.Poller').setLevel(logging.INFO)
    # do some tests and exit
    def do_run(cmd, stdin_data=''):
        #pipeline = pipeline.update(stderr=sp.PIPE)
        try:
            cmd_output = cmd.run(stdin_data)
            print "%r => %s => %r" % (stdin_data, cmd._logging_desc, cmd_output)
        except CmdException, exc:
            if isinstance(cmd, CmdPipeline):
                returncode = [p.returncode for p in exc.proc.procs]
            else:
                returncode = exc.proc.returncode
            print "%s exit %s => out=%r err=%r" % (cmd._logging_desc, returncode, exc.stdout, exc.stderr)

    say_hello = Cmd('echo', 'hello')
    cat = Cmd('cat')
    wc_l = Cmd('wc', '-l')
    tee = Cmd('tee', '/dev/fd/2')
    errtest = Cmd('echo bleh; echo argh 1>&2; exit 42', shell=True)
    errtest2 = Cmd('cat; echo argh 1>&2; exit 42', shell=True)

    do_run(say_hello)
    do_run(CmdPipeline(say_hello))
    do_run(tee, 'test\n')
    do_run(CmdPipeline(tee), 'test\n')
    do_run(say_hello | tee)
    do_run(cat | say_hello)
    do_run(say_hello | cat | wc_l)
    do_run(tee|cat|cat|cat|cat|cat|tee|cat|cat|cat|wc_l, 'whee\n')
    do_run(errtest.update(stderr=sp.PIPE))
    do_run((say_hello|errtest2).update(stderr=sp.PIPE))


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
    # Modules using this boilerplace can be run via python -m 'pkg.mod', python
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
        kw = popen_kwargs.copy()
        for k in kw:
            try:
                kw[k] = kw[k].fileno()
            except:
                pass
        self._dbg('init %s', kw)

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
            argv = self.argv.join(' ')
        else:
            argv = self.argv
        return sp.Popen(argv, **_popen_kw)

    def popen(self):
        """ Returns a Popen instance instantiated based on my settings. """
        self._dbg("popen()")
        return self._popen(self.popen_kwargs)

    def run(self, stdin_data=''):
        kwargs_with_pipe = dict({'stdin': sp.PIPE, 'stdout': sp.PIPE},
            **self.popen_kwargs)
        self._dbg("run(<%d bytes>) %r", len(stdin_data), kwargs_with_pipe)
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
        positional parameters; these represents the commands to be run.

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
        stdin = kw.pop('stdin', None)
        stdout = kw.pop('stdout', None)
        stderr = kw.pop('stderr', None)

        super(PopenPipeline, self).__init__()
        if kw.pop('_first', True):
            self._dbg('init(%r, %r, %r)', first_cmd, remaining_cmds, kw)

        self.cmd = first_cmd.default(close_fds=True).update(
            stdin=stdin,
            stdout=sp.PIPE if len(remaining_cmds) > 0 else stdout,
            stderr=stderr,
            **kw)
        self.proc = self.cmd.popen()
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
            self._dbg('->popen %x => pipeline_stdout %s', id(self.cmd), self.stdout.fileno())
        else:
            self._dbg('->popen %x => next_stdout %s', id(self.cmd), self.proc.stdout.fileno())
            self.next = type(self)(  # build another instance of same type:
                    stdin=self.proc.stdout,
                    stdout=stdout, stderr=stderr,
                    _first=False,
                    *remaining_cmds, **kw)
            # self.proc's stdout was made into the next cmd's stdin, close it:
            self.proc.stdout.close()
            # our "stdout" should come from the end of the pipeline:
            self.stdout = self.next.stdout
        
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
                if hasattr(item, 'closed') and item.closed:
                    continue
                item.close()

    def _comm_setup_poller(self, stdin_data, poller=None):
        if getattr(self, '_communicate_called', False):
            raise ValueError(">1 call to PopenPipeline.communicate()")
        self._communicate_called = True

        if stdin_data:
            self.stdin_data = memoryview(stdin_data)
            self._dbg('got stdin data, writing to %s', self.stdin.fileno())
        elif self.stdin:
            self._dbg('no stdin data, closing %s', self.stdin.fileno())
            self.stdin.close()
            self.stdin = None
        else:
            self._dbg('neither stdin_data nor stdin present')

        self.stdout_data = []
        self.stderr_data = []

        self._open_pipes = 0
        if poller is None:
            poller = self._poller = _io.Poller()

        def _close_pipe(fp):
            desc = 'stdin' if fp is self.stdin else (
                   'stdout' if fp is self.stdout else 'stderr')
            self._dbg("closing %s fd %d", desc, fp.fileno())
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
        with self, self._comm_setup_poller(stdin_data) as poller:
            while self._open_pipes > 0 or self.poll() is None:
                self._dbg('poll: %s %s', self._open_pipes, self.poll())
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
                self._dbg('%d bytes written to stdin', written)
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
        return CmdPipeline(self.commands[:] + [other], self.popen_kwargs)

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
    logging.basicConfig(level=logging.DEBUG)
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
            print "%s XX %s => %s" % (desc, returncode, exc.stdout)

    say_hello = Cmd('echo', 'hello')
    cat = Cmd('cat')
    wc_l = Cmd('wc', '-l')

    do_run(say_hello)
    do_run(CmdPipeline(say_hello))
    do_run(say_hello | cat)
    do_run(cat, 'hello')
    do_run(say_hello | wc_l)
    do_run(cat | wc_l, '1\n2\n3\n')


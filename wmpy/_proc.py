import os
from subprocess import Popen, PIPE, check_call

from ._io import Poller
from . import _logging
_logger, _dbg, _warn, _error = _logging.get_logging_shortcuts(__name__)

class CmdException(Exception):
    pass

class Cmd(object):
    def __init__(self, *args, **kwargs):
        self.cmd = args
        self.params = kwargs
    def update(self, **kwargs):
        self.params.update(kwargs)
    def proc(self, **kwargs):
        self.params.update(kwargs)
        cmd = self.cmd
        if kwargs.get('shell'):
            cmd = cmd.join(' ')
        return Popen(cmd, **self.params)
    def run(self, input=None, **kwargs):
        kwargs['stdin'] = kwargs['stdout'] = kwargs['stderr'] = PIPE
        proc = self.proc(**kwargs)
        stdout, stderr = proc.communicate(input)
        if proc.returncode != 0:
            raise CmdException("Error running %s: %s" % (' '.join(self.cmd), stderr))
        if stderr:
            print stderr
        return stdout
    def __or__(self, other):
        if isinstance(other, Cmd):
            return Pipe(self, other)
        if isinstance(other, Pipe):
            other.commands = [self].extend(other.commands)
        raise TypeError("can't pipe to %s from %s" % (type(other), self))
    def __str__(self):
        return "Cmd(%s)" % ' '.join(self.cmd)

class Pipe(object):
    def __init__(self, *commands):
        self.commands = list(commands)

    def __or__(self, other):
        self.commands.append(other)
        return self

    def _proc(self, cmd):
        proc = cmd.proc(close_fds=True)
        #print "Running", cmd, cmd.params['stdin'], cmd.params['stdout'], proc.pid
        return proc

    def run(self, in_data=''):
        in_r, self.in_w = os.pipe()
        self.out_r, out_w = os.pipe()
        self.err_r, err_w = os.pipe()
        self.plumbing = [in_r, out_w, err_w]
        self.procs = []
        self.commands[0].update(stdin=in_r)
        self.commands[-1].update(stdout=out_w)
        for a, b in zip(self.commands[:-1], self.commands[1:]):
            out_r, out_w = os.pipe()
            #print "connecting %s -> %d %d -> %s" % (a, out_w, out_r, b)
            a.update(stdout=out_w, stderr=err_w)
            b.update(stdin=out_r, stderr=err_w)
            self.plumbing.extend([out_r, out_w])

        self._errors = []
        self._left = 3

        procs = map(self._proc, self.commands)
        for fd in self.plumbing:
            os.close(fd)
        self._input = in_data
        self.stdout = []
        self.stderr = []
        self.poller = poller = Poller()
        poller.register(self.in_w, POLLOUT, self.send_stdin)
        poller.register(self.out_r, POLLIN, self.read_stdout)
        poller.register(self.err_r, POLLIN, self.read_stderr)
        self._procs_active = set(range(len(procs)))
        while self._left > 0 and len(self._procs_active) > 0:
            poller.poll(1000)
            for i, proc in enumerate(procs):
                if i not in self._procs_active:
                    continue
                if proc.returncode is not None or proc.poll():
                    self._procs_active.remove(i)
        poller.close()
        for i, proc in enumerate(procs):
            if proc.wait() != 0:
                command = self.commands[i]
                self._errors.append(
                    CmdException("%s returned %s in %s" %
                                 (command, proc.returncode, self)))
        self.stdout = ''.join(self.stdout)
        self.stderr = ''.join(self.stderr)
        if len(self._errors) > 0:
            if self.stderr:
                print self.stderr
            raise self._errors[0]
        return self.stdout

    def finish(self, fd):
        self.poller.unregister(fd)
        os.close(fd)
        self._left -= 1

    def send_stdin(self, fd, event):
        #print "send_stdin", fd, event
        if event & POLLERR:
            if len(self._input) == 0:
                self.finish(fd)
            else:
                self.finish(fd)
                self._errors.append(CmdException("can't write input in %s" % self))
        elif event & POLLOUT:
            if self._input:
                written = os.write(fd, self._input[:512])
                self._input = self._input[written:]
            else:
                self.finish(fd)
        else:
            #print "closing stdin %d unknown event %x" % (fd, event)
            self.finish(fd)

    def read_stderr(self, fd, event):
        #print "read_stderr", fd, event
        data = os.read(fd, 512)
        if len(data) == 0:
            self.finish(fd)
        else:
            self.stderr.append(data)

    def read_stdout(self, fd, event):
        #print "read_stdout", fd, event
        data = os.read(fd, 512)
        if len(data) == 0:
            self.finish(fd)
        else:
            self.stdout.append(data)

    def __str__(self):
        return 'Pipe(%s)' % ' | '.join(map(str, self.commands))

def env_plus(**kwargs):
    env = dict(os.environ)
    env.update(kwargs)
    return env

# example:
def git(*args, **kwargs):
    """ returns Cmd that runs git out of repodir """
    kwargs['cwd'] = repodir
    args = ['git'] + list(args)
    return Cmd(*args, **kwargs)


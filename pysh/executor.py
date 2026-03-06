"""
Command executor for pysh.

Handles running simple commands, pipelines, lists (&&, ||, ;, &),
I/O redirections, and subshells.
"""

import os
import sys
import signal
import glob as globmod
from typing import List, Optional, Tuple, Dict

from pysh.parser import (
    CommandList, ListEntry, Pipeline, SimpleCommand, Subshell, Redirect
)


class ExecutionError(Exception):
    pass


class Executor:
    def __init__(self, shell):
        self.shell = shell

    def execute(self, cmd_list: CommandList) -> int:
        return self._exec_list(cmd_list)

    def _exec_list(self, cmd_list: CommandList) -> int:
        last_status = 0
        for entry in cmd_list.entries:
            if entry.operator == '&':
                self._exec_pipeline_bg(entry.pipeline)
                last_status = 0
                continue

            last_status = self._exec_pipeline(entry.pipeline)
            self.shell.last_status = last_status

            op = entry.operator
            if op == '&&' and last_status != 0:
                # skip next entries until we find || or ;
                continue
            elif op == '||' and last_status == 0:
                continue

        return last_status

    def _exec_pipeline_bg(self, pipeline: Pipeline):
        pid = os.fork()
        if pid == 0:
            os.setpgrp()
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            status = self._exec_pipeline(pipeline)
            os._exit(status)
        else:
            self.shell.jobs.add_job(pid, str(pipeline))
            print(f"[{self.shell.jobs.last_job_num}] {pid}")

    def _exec_pipeline(self, pipeline: Pipeline) -> int:
        commands = pipeline.commands
        if len(commands) == 1:
            status = self._exec_command(commands[0])
        else:
            status = self._exec_pipe_chain(commands)

        if pipeline.negated:
            status = 0 if status != 0 else 1
        return status

    def _exec_pipe_chain(self, commands: list) -> int:
        """Execute a chain of piped commands."""
        sys.stdout.flush()
        sys.stderr.flush()
        n = len(commands)
        pipes = []
        for _ in range(n - 1):
            pipes.append(os.pipe())

        pids = []
        for i, cmd in enumerate(commands):
            pid = os.fork()
            if pid == 0:
                signal.signal(signal.SIGINT, signal.SIG_DFL)
                # set up pipe fds
                if i > 0:
                    os.dup2(pipes[i - 1][0], 0)
                if i < n - 1:
                    os.dup2(pipes[i][1], 1)
                for r, w in pipes:
                    os.close(r)
                    os.close(w)

                if isinstance(cmd, Subshell):
                    status = self._run_subshell(cmd)
                else:
                    status = self._exec_simple_in_child(cmd)
                sys.stdout.flush()
                sys.stderr.flush()
                os._exit(status)
            pids.append(pid)

        for r, w in pipes:
            os.close(r)
            os.close(w)

        last_status = 0
        for pid in pids:
            _, status = os.waitpid(pid, 0)
            last_status = _exit_status(status)

        return last_status

    def _exec_command(self, cmd) -> int:
        if isinstance(cmd, Subshell):
            return self._run_subshell(cmd)
        return self._exec_simple(cmd)

    def _run_subshell(self, sub: Subshell) -> int:
        sys.stdout.flush()
        sys.stderr.flush()
        pid = os.fork()
        if pid == 0:
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            self._apply_redirects(sub.redirects)
            status = self._exec_list(sub.body)
            os._exit(status)
        _, status = os.waitpid(pid, 0)
        return _exit_status(status)

    def _exec_simple(self, cmd: SimpleCommand) -> int:
        if not cmd.args:
            return self._handle_bare_redirects(cmd)

        args = self._expand(cmd)
        if not args:
            return 0

        name = args[0]

        builtin_fn = self.shell.builtins.get(name)
        if builtin_fn is not None:
            sys.stdout.flush()
            sys.stderr.flush()
            saved_fds = self._setup_redirects(cmd.redirects)
            try:
                result = builtin_fn(args)
                sys.stdout.flush()
                sys.stderr.flush()
                return result
            finally:
                self._restore_fds(saved_fds)

        return self._exec_external(args, cmd.redirects)

    def _exec_simple_in_child(self, cmd: SimpleCommand) -> int:
        """Execute a simple command already inside a forked child."""
        if not cmd.args:
            self._apply_redirects(cmd.redirects)
            return 0

        args = self._expand(cmd)
        if not args:
            return 0

        name = args[0]
        builtin_fn = self.shell.builtins.get(name)
        if builtin_fn is not None:
            self._apply_redirects(cmd.redirects)
            return builtin_fn(args)

        self._apply_redirects(cmd.redirects)
        self._exec_program(args)
        return 127  # only reached on failure

    def _exec_external(self, args: List[str], redirects: List[Redirect]) -> int:
        sys.stdout.flush()
        sys.stderr.flush()
        pid = os.fork()
        if pid == 0:
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            self._apply_redirects(redirects)
            self._exec_program(args)
            os._exit(127)

        _, status = os.waitpid(pid, 0)
        return _exit_status(status)

    def _exec_program(self, args: List[str]):
        """Replace current process with the given program (only returns on error)."""
        program = args[0]
        if '/' in program:
            try:
                os.execv(program, args)
            except OSError as e:
                print(f"pysh: {program}: {e.strerror}", file=sys.stderr)
                os._exit(127)
        else:
            path_dirs = os.environ.get('PATH', '/usr/bin:/bin').split(':')
            for d in path_dirs:
                full = os.path.join(d, program)
                if os.path.isfile(full) and os.access(full, os.X_OK):
                    try:
                        os.execv(full, args)
                    except OSError:
                        continue
            print(f"pysh: {program}: command not found", file=sys.stderr)
            os._exit(127)

    def _expand(self, cmd: SimpleCommand) -> List[str]:
        """Perform variable expansion, tilde expansion, and glob expansion on command args."""
        result = []
        for arg, quoted in zip(cmd.args, cmd.quoted_args):
            expanded = self._expand_variables(arg)
            expanded = self._expand_tilde(expanded)
            if not quoted and any(c in expanded for c in ('*', '?', '[')):
                globbed = sorted(globmod.glob(expanded))
                if globbed:
                    result.extend(globbed)
                else:
                    result.append(expanded)
            else:
                result.append(expanded)
        return result

    def _expand_variables(self, text: str) -> str:
        """Expand $VAR, ${VAR}, $?, $$, and $N references."""
        result = []
        i = 0
        n = len(text)
        while i < n:
            if text[i] == '$' and i + 1 < n:
                i += 1
                if text[i] == '{':
                    i += 1
                    name = []
                    while i < n and text[i] != '}':
                        name.append(text[i])
                        i += 1
                    if i < n:
                        i += 1  # skip }
                    varname = ''.join(name)
                    result.append(self._get_var(varname))
                elif text[i] == '?':
                    result.append(str(self.shell.last_status))
                    i += 1
                elif text[i] == '$':
                    result.append(str(os.getpid()))
                    i += 1
                elif text[i] == '0':
                    result.append('pysh')
                    i += 1
                elif text[i].isdigit():
                    result.append('')  # positional params not yet implemented
                    i += 1
                elif text[i] == '#':
                    result.append('0')
                    i += 1
                elif text[i].isalpha() or text[i] == '_':
                    name = []
                    while i < n and (text[i].isalnum() or text[i] == '_'):
                        name.append(text[i])
                        i += 1
                    result.append(self._get_var(''.join(name)))
                else:
                    result.append('$')
            else:
                result.append(text[i])
                i += 1
        return ''.join(result)

    def _expand_tilde(self, text: str) -> str:
        if text == '~' or text.startswith('~/'):
            return os.environ.get('HOME', '~') + text[1:]
        return text

    def _get_var(self, name: str) -> str:
        val = self.shell.variables.get(name)
        if val is not None:
            return val
        return os.environ.get(name, '')

    def _handle_bare_redirects(self, cmd: SimpleCommand) -> int:
        """Handle commands that are only redirections (e.g., `> file`)."""
        for redir in cmd.redirects:
            target = self._expand_variables(redir.target)
            try:
                if redir.op == '>':
                    open(target, 'w').close()
                elif redir.op == '>>':
                    open(target, 'a').close()
            except OSError as e:
                print(f"pysh: {target}: {e.strerror}", file=sys.stderr)
                return 1
        return 0

    def _setup_redirects(self, redirects: List[Redirect]) -> List[Tuple[int, int]]:
        """Apply redirections, saving original fds for later restoration."""
        saved = []
        for redir in redirects:
            target = self._expand_variables(redir.target)
            try:
                if redir.op == '>':
                    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
                    saved.append((1, os.dup(1)))
                    os.dup2(fd, 1)
                    os.close(fd)
                elif redir.op == '>>':
                    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
                    saved.append((1, os.dup(1)))
                    os.dup2(fd, 1)
                    os.close(fd)
                elif redir.op == '<':
                    fd = os.open(target, os.O_RDONLY)
                    saved.append((0, os.dup(0)))
                    os.dup2(fd, 0)
                    os.close(fd)
            except OSError as e:
                print(f"pysh: {target}: {e.strerror}", file=sys.stderr)
        return saved

    def _restore_fds(self, saved: List[Tuple[int, int]]):
        for orig_fd, saved_fd in reversed(saved):
            os.dup2(saved_fd, orig_fd)
            os.close(saved_fd)

    def _apply_redirects(self, redirects: List[Redirect]):
        """Apply redirections without saving (for use in child processes)."""
        for redir in redirects:
            target = self._expand_variables(redir.target)
            try:
                if redir.op == '>':
                    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
                    os.dup2(fd, 1)
                    os.close(fd)
                elif redir.op == '>>':
                    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
                    os.dup2(fd, 1)
                    os.close(fd)
                elif redir.op == '<':
                    fd = os.open(target, os.O_RDONLY)
                    os.dup2(fd, 0)
                    os.close(fd)
            except OSError as e:
                print(f"pysh: {target}: {e.strerror}", file=sys.stderr)


def _exit_status(status: int) -> int:
    """Convert os.waitpid status to exit code."""
    if os.WIFEXITED(status):
        return os.WEXITSTATUS(status)
    if os.WIFSIGNALED(status):
        return 128 + os.WTERMSIG(status)
    return 1

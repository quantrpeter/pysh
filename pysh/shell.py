"""
Core shell object for pysh.

Ties together the lexer, parser, executor, builtins, and job control.
Manages the REPL loop, prompt, history, and RC file loading.
"""

import os
import sys
import signal
import traceback
from typing import Dict, Optional

from pysh.lexer import tokenize, LexerError
from pysh.parser import Parser, ParseError
from pysh.executor import Executor
from pysh.builtins import register_builtins
from pysh.jobs import JobManager


class Shell:
    def __init__(self):
        self.variables: Dict[str, str] = {}
        self.aliases: Dict[str, str] = {}
        self.last_status: int = 0
        self.jobs = JobManager()
        self.builtins = register_builtins(self)
        self.executor = Executor(self)
        self.running = True

        self._init_env()

    def _init_env(self):
        os.environ.setdefault('PWD', os.getcwd())
        self.variables['SHELL'] = os.path.abspath(sys.argv[0])
        self.variables['PYSH_VERSION'] = '0.1.0'

        if 'USER' not in os.environ:
            import getpass
            try:
                os.environ['USER'] = getpass.getuser()
            except Exception:
                os.environ['USER'] = 'user'

        if 'HOSTNAME' not in os.environ:
            import socket
            try:
                os.environ['HOSTNAME'] = socket.gethostname()
            except Exception:
                os.environ['HOSTNAME'] = 'localhost'

    def get_prompt(self) -> str:
        """Generate the shell prompt, supporting PS1-like formatting."""
        ps1 = self.variables.get('PS1') or os.environ.get('PS1')
        if ps1:
            return self._expand_prompt(ps1)

        user = os.environ.get('USER', 'user')
        host = os.environ.get('HOSTNAME', 'localhost').split('.')[0]
        cwd = os.getcwd()
        home = os.environ.get('HOME', '')
        if home and cwd.startswith(home):
            cwd = '~' + cwd[len(home):]

        uid = os.getuid() if hasattr(os, 'getuid') else 1000
        symbol = '#' if uid == 0 else '$'
        return f"[PYSH] \033[1;32m{user}@{host}\033[0m:\033[1;34m{cwd}\033[0m{symbol} "

    def _expand_prompt(self, ps1: str) -> str:
        """Expand bash-style PS1 escape sequences."""
        result = []
        i = 0
        while i < len(ps1):
            if ps1[i] == '\\' and i + 1 < len(ps1):
                c = ps1[i + 1]
                if c == 'u':
                    result.append(os.environ.get('USER', 'user'))
                elif c == 'h':
                    result.append(os.environ.get('HOSTNAME', 'localhost').split('.')[0])
                elif c == 'H':
                    result.append(os.environ.get('HOSTNAME', 'localhost'))
                elif c == 'w':
                    cwd = os.getcwd()
                    home = os.environ.get('HOME', '')
                    if home and cwd.startswith(home):
                        cwd = '~' + cwd[len(home):]
                    result.append(cwd)
                elif c == 'W':
                    result.append(os.path.basename(os.getcwd()) or '/')
                elif c == '$':
                    uid = os.getuid() if hasattr(os, 'getuid') else 1000
                    result.append('#' if uid == 0 else '$')
                elif c == 'n':
                    result.append('\n')
                elif c == '[':
                    result.append('\001')
                elif c == ']':
                    result.append('\002')
                elif c == 'e':
                    result.append('\033')
                elif c == 'a':
                    result.append('\007')
                elif c == '\\':
                    result.append('\\')
                else:
                    result.append('\\')
                    result.append(c)
                i += 2
            else:
                result.append(ps1[i])
                i += 1
        return ''.join(result)

    def run_command(self, line: str) -> int:
        """Parse and execute a single command line. Returns exit status."""
        line = line.strip()
        if not line or line.startswith('#'):
            return 0

        # Handle variable assignments: VAR=value
        if '=' in line and not any(c in line.split('=')[0] for c in ' \t|&;<>()'):
            first_word = line.split()[0]
            if '=' in first_word and first_word[0] != '=' and first_word.split('=')[0].replace('_', '').isalnum():
                name, _, value = first_word.partition('=')
                rest = line[len(first_word):].strip()
                if not rest:
                    self.variables[name] = self.executor._expand_variables(value)
                    return 0

        line = self._expand_aliases(line)

        try:
            tokens = tokenize(line)
            parser = Parser(tokens)
            cmd_list = parser.parse()
            self.last_status = self.executor.execute(cmd_list)
            return self.last_status
        except LexerError as e:
            print(f"pysh: syntax error: {e}", file=sys.stderr)
            return 2
        except ParseError as e:
            print(f"pysh: parse error: {e}", file=sys.stderr)
            return 2

    def _expand_aliases(self, line: str) -> str:
        """Expand aliases in the command line (first word only, with recursion guard)."""
        if not self.aliases:
            return line
        words = line.split(None, 1)
        if not words:
            return line

        seen = set()
        while words[0] in self.aliases and words[0] not in seen:
            seen.add(words[0])
            expansion = self.aliases[words[0]]
            rest = words[1] if len(words) > 1 else ''
            line = f"{expansion} {rest}".strip() if rest else expansion
            words = line.split(None, 1)
            if not words:
                return line
        return line

    def load_rc(self):
        """Load ~/.pyshrc if it exists."""
        home = os.environ.get('HOME', '')
        rc_path = os.path.join(home, '.pyshrc')
        if os.path.isfile(rc_path):
            try:
                with open(rc_path) as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            self.run_command(line)
            except OSError:
                pass

    def setup_readline(self):
        """Configure readline for tab completion and history."""
        try:
            import readline
        except ImportError:
            return

        history_file = os.path.join(os.environ.get('HOME', '.'), '.pysh_history')
        try:
            readline.read_history_file(history_file)
        except FileNotFoundError:
            pass
        readline.set_history_length(10000)

        import atexit
        atexit.register(readline.write_history_file, history_file)

        readline.set_completer(self._completer)
        readline.set_completer_delims(' \t\n;|&><()')
        readline.parse_and_bind('tab: complete')

    def _completer(self, text: str, state: int):
        """Tab completion: commands, files, and directories."""
        if state == 0:
            self._completions = self._get_completions(text)
        if state < len(self._completions):
            return self._completions[state]
        return None

    def _get_completions(self, text: str) -> list:
        import glob as globmod

        completions = []

        # File/directory completion
        pattern = text + '*'
        for path in sorted(globmod.glob(pattern)):
            if os.path.isdir(path):
                completions.append(path + '/')
            else:
                completions.append(path)

        if not text or '/' not in text:
            for name in sorted(self.builtins.keys()):
                if name.startswith(text):
                    completions.append(name + ' ')
            for name in sorted(self.aliases.keys()):
                if name.startswith(text):
                    completions.append(name + ' ')

            for d in os.environ.get('PATH', '').split(':'):
                try:
                    for entry in os.listdir(d):
                        if entry.startswith(text):
                            full = os.path.join(d, entry)
                            if os.access(full, os.X_OK):
                                val = entry + ' '
                                if val not in completions:
                                    completions.append(val)
                except OSError:
                    continue

        return sorted(set(completions))

    def repl(self):
        """Main read-eval-print loop."""
        self.setup_readline()
        self.load_rc()

        signal.signal(signal.SIGINT, self._handle_sigint)
        try:
            signal.signal(signal.SIGTSTP, signal.SIG_IGN)
        except (OSError, AttributeError):
            pass

        while self.running:
            self.jobs.reap()
            try:
                line = input(self.get_prompt())
            except EOFError:
                print()
                break
            except KeyboardInterrupt:
                print()
                continue

            if not line.strip():
                continue

            try:
                self.run_command(line)
            except SystemExit as e:
                sys.exit(e.code)
            except Exception:
                traceback.print_exc()
                self.last_status = 1

    def _handle_sigint(self, signum, frame):
        print()

"""
Built-in commands for pysh.

These run in the shell process itself rather than being forked.
"""

import os
import sys
from typing import List, Callable, Dict

from pysh.commands import CUSTOM_COMMANDS


def register_builtins(shell) -> Dict[str, Callable]:
    """Create and return a dict of builtin name -> function."""

    def builtin_cd(args: List[str]) -> int:
        if len(args) < 2:
            target = os.environ.get('HOME', '/')
        elif args[1] == '-':
            target = shell.variables.get('OLDPWD', os.getcwd())
            print(target)
        else:
            target = args[1]

        oldpwd = os.getcwd()
        try:
            os.chdir(target)
            shell.variables['OLDPWD'] = oldpwd
            os.environ['OLDPWD'] = oldpwd
            os.environ['PWD'] = os.getcwd()
            return 0
        except OSError as e:
            print(f"pysh: cd: {target}: {e.strerror}", file=sys.stderr)
            return 1

    def builtin_pwd(args: List[str]) -> int:
        print(os.getcwd())
        return 0

    def builtin_echo(args: List[str]) -> int:
        parts = args[1:]
        newline = True
        if parts and parts[0] == '-n':
            newline = False
            parts = parts[1:]
        text = ' '.join(parts)
        if newline:
            print(text)
        else:
            sys.stdout.write(text)
            sys.stdout.flush()
        return 0

    def builtin_exit(args: List[str]) -> int:
        code = 0
        if len(args) > 1:
            try:
                code = int(args[1])
            except ValueError:
                print(f"pysh: exit: {args[1]}: numeric argument required", file=sys.stderr)
                code = 2
        raise SystemExit(code)

    def builtin_export(args: List[str]) -> int:
        if len(args) < 2:
            for key, val in sorted(os.environ.items()):
                print(f'declare -x {key}="{val}"')
            return 0
        for arg in args[1:]:
            if '=' in arg:
                name, _, value = arg.partition('=')
                os.environ[name] = value
                shell.variables[name] = value
            else:
                val = shell.variables.get(arg, '')
                os.environ[arg] = val
        return 0

    def builtin_unset(args: List[str]) -> int:
        for name in args[1:]:
            os.environ.pop(name, None)
            shell.variables.pop(name, None)
        return 0

    def builtin_type(args: List[str]) -> int:
        status = 0
        for name in args[1:]:
            if name in builtins:
                print(f"{name} is a shell builtin")
            elif name in shell.aliases:
                print(f"{name} is aliased to '{shell.aliases[name]}'")
            else:
                found = False
                for d in os.environ.get('PATH', '').split(':'):
                    full = os.path.join(d, name)
                    if os.path.isfile(full) and os.access(full, os.X_OK):
                        print(f"{name} is {full}")
                        found = True
                        break
                if not found:
                    print(f"pysh: type: {name}: not found", file=sys.stderr)
                    status = 1
        return status

    def builtin_alias(args: List[str]) -> int:
        if len(args) < 2:
            for name, val in sorted(shell.aliases.items()):
                print(f"alias {name}='{val}'")
            return 0
        for arg in args[1:]:
            if '=' in arg:
                name, _, value = arg.partition('=')
                shell.aliases[name] = value
            else:
                if arg in shell.aliases:
                    print(f"alias {arg}='{shell.aliases[arg]}'")
                else:
                    print(f"pysh: alias: {arg}: not found", file=sys.stderr)
                    return 1
        return 0

    def builtin_unalias(args: List[str]) -> int:
        for name in args[1:]:
            if name == '-a':
                shell.aliases.clear()
                return 0
            if name in shell.aliases:
                del shell.aliases[name]
            else:
                print(f"pysh: unalias: {name}: not found", file=sys.stderr)
                return 1
        return 0

    def builtin_history(args: List[str]) -> int:
        try:
            import readline
            length = readline.get_current_history_length()
            start = 1
            if len(args) > 1:
                try:
                    count = int(args[1])
                    start = max(1, length - count + 1)
                except ValueError:
                    pass
            for i in range(start, length + 1):
                item = readline.get_history_item(i)
                if item:
                    print(f" {i:5d}  {item}")
        except ImportError:
            print("pysh: history: readline not available", file=sys.stderr)
            return 1
        return 0

    def builtin_source(args: List[str]) -> int:
        if len(args) < 2:
            print("pysh: source: filename argument required", file=sys.stderr)
            return 2
        filepath = args[1]
        try:
            with open(filepath) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    shell.run_command(line)
        except FileNotFoundError:
            print(f"pysh: source: {filepath}: No such file or directory", file=sys.stderr)
            return 1
        return 0

    def builtin_jobs(args: List[str]) -> int:
        for num, state, pid, desc in shell.jobs.list_jobs():
            print(f"[{num}]  {state}\t\t{desc}")
        return 0

    def builtin_fg(args: List[str]) -> int:
        spec = args[1] if len(args) > 1 else None
        job = shell.jobs.get_job(spec)
        if job is None:
            print("pysh: fg: no current job", file=sys.stderr)
            return 1
        print(job.description)
        return shell.jobs.foreground(job)

    def builtin_bg(args: List[str]) -> int:
        spec = args[1] if len(args) > 1 else None
        job = shell.jobs.get_job(spec)
        if job is None:
            print("pysh: bg: no current job", file=sys.stderr)
            return 1
        shell.jobs.background(job)
        return 0

    def builtin_set(args: List[str]) -> int:
        if len(args) < 2:
            for key, val in sorted(shell.variables.items()):
                print(f"{key}={val}")
            for key, val in sorted(os.environ.items()):
                if key not in shell.variables:
                    print(f"{key}={val}")
            return 0
        return 0

    def builtin_true(args: List[str]) -> int:
        return 0

    def builtin_false(args: List[str]) -> int:
        return 1

    def builtin_read(args: List[str]) -> int:
        prompt = ""
        var_args = args[1:]

        i = 0
        while i < len(var_args):
            if var_args[i] == '-p' and i + 1 < len(var_args):
                prompt = var_args[i + 1]
                var_args = var_args[:i] + var_args[i + 2:]
            else:
                i += 1

        try:
            line = input(prompt)
        except EOFError:
            return 1

        if not var_args:
            shell.variables['REPLY'] = line
        else:
            parts = line.split(None, len(var_args) - 1)
            for j, name in enumerate(var_args):
                shell.variables[name] = parts[j] if j < len(parts) else ''
        return 0

    def builtin_test(args: List[str]) -> int:
        return _evaluate_test(args[1:])

    def builtin_bracket(args: List[str]) -> int:
        if not args or args[-1] != ']':
            print("pysh: [: missing ']'", file=sys.stderr)
            return 2
        return _evaluate_test(args[1:-1])

    builtins = {
        **CUSTOM_COMMANDS,
        'cd': builtin_cd,
        'pwd': builtin_pwd,
        'echo': builtin_echo,
        'exit': builtin_exit,
        'export': builtin_export,
        'unset': builtin_unset,
        'type': builtin_type,
        'alias': builtin_alias,
        'unalias': builtin_unalias,
        'history': builtin_history,
        'source': builtin_source,
        '.': builtin_source,
        'jobs': builtin_jobs,
        'fg': builtin_fg,
        'bg': builtin_bg,
        'set': builtin_set,
        'true': builtin_true,
        'false': builtin_false,
        'read': builtin_read,
        'test': builtin_test,
        '[': builtin_bracket,
    }
    return builtins


def _evaluate_test(args: List[str]) -> int:
    """Evaluate a test/[ expression. Returns 0 for true, 1 for false."""
    if not args:
        return 1

    if len(args) == 1:
        return 0 if args[0] else 1

    if args[0] == '!':
        return 1 if _evaluate_test(args[1:]) == 0 else 0

    if args[0] == '-n':
        return 0 if len(args[1]) > 0 else 1
    if args[0] == '-z':
        return 0 if len(args[1]) == 0 else 1
    if args[0] == '-e':
        return 0 if os.path.exists(args[1]) else 1
    if args[0] == '-f':
        return 0 if os.path.isfile(args[1]) else 1
    if args[0] == '-d':
        return 0 if os.path.isdir(args[1]) else 1
    if args[0] == '-r':
        return 0 if os.access(args[1], os.R_OK) else 1
    if args[0] == '-w':
        return 0 if os.access(args[1], os.W_OK) else 1
    if args[0] == '-x':
        return 0 if os.access(args[1], os.X_OK) else 1
    if args[0] == '-s':
        try:
            return 0 if os.path.getsize(args[1]) > 0 else 1
        except OSError:
            return 1

    if len(args) == 3:
        left, op, right = args[0], args[1], args[2]
        if op == '=':
            return 0 if left == right else 1
        if op == '!=':
            return 0 if left != right else 1
        try:
            l, r = int(left), int(right)
            if op == '-eq': return 0 if l == r else 1
            if op == '-ne': return 0 if l != r else 1
            if op == '-lt': return 0 if l < r else 1
            if op == '-le': return 0 if l <= r else 1
            if op == '-gt': return 0 if l > r else 1
            if op == '-ge': return 0 if l >= r else 1
        except ValueError:
            pass

    return 1

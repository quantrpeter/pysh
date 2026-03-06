"""Entry point for `python -m pysh`."""

import sys
from pysh.shell import Shell


def main():
    shell = Shell()

    if len(sys.argv) > 1:
        if sys.argv[1] == '-c' and len(sys.argv) > 2:
            sys.exit(shell.run_command(sys.argv[2]))
        else:
            filepath = sys.argv[1]
            try:
                with open(filepath) as f:
                    status = 0
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            status = shell.run_command(line)
                    sys.exit(status)
            except FileNotFoundError:
                print(f"pysh: {filepath}: No such file or directory", file=sys.stderr)
                sys.exit(127)
    else:
        shell.repl()


if __name__ == '__main__':
    main()

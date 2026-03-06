"""
Built-in var command for pysh.

Displays shell and environment variables in a formatted table.
"""

import os
import sys
from typing import List, Optional, Tuple

C_RESET = '\033[0m'
C_BOLD = '\033[1m'
C_DIM = '\033[2m'
C_CYAN = '\033[36m'
C_GREEN = '\033[32m'
C_YELLOW = '\033[33m'
C_BLUE = '\033[34m'
C_MAGENTA = '\033[35m'

HEADER_BG = '\033[48;5;236m'
BORDER_COLOR = '\033[38;5;240m'


def builtin_var(args: List[str], shell=None) -> int:
    opts, pattern = _parse_args(args)
    if opts is None:
        return 0

    use_color = not opts['no_color'] and sys.stdout.isatty()
    variables = _collect_variables(shell, opts, pattern)

    if not variables:
        if pattern:
            print(f"var: no variables matching '{pattern}'", file=sys.stderr)
            return 1
        return 0

    _print_table(variables, opts, use_color)
    return 0


def _parse_args(args: List[str]) -> Tuple[Optional[dict], Optional[str]]:
    opts = {
        'show_shell': True,
        'show_env': True,
        'show_source': True,
        'no_color': False,
        'export_only': False,
    }
    pattern = None

    i = 1
    while i < len(args):
        arg = args[i]
        if arg in ('-h', '--help'):
            _print_help()
            return None, None
        elif arg in ('-s', '--shell'):
            opts['show_shell'] = True
            opts['show_env'] = False
        elif arg in ('-e', '--env'):
            opts['show_shell'] = False
            opts['show_env'] = True
        elif arg in ('-x', '--exported'):
            opts['export_only'] = True
        elif arg == '--no-color':
            opts['no_color'] = True
        elif arg == '--':
            if i + 1 < len(args):
                pattern = args[i + 1]
            break
        elif not arg.startswith('-'):
            pattern = arg
        else:
            print(f"var: unknown option '{arg}'", file=sys.stderr)
            return None, None
        i += 1

    return opts, pattern


def _collect_variables(shell, opts: dict, pattern: Optional[str]) -> List[dict]:
    variables = []
    seen = set()

    if opts['show_shell'] and shell and not opts['export_only']:
        for name, value in sorted(shell.variables.items()):
            if pattern and pattern.lower() not in name.lower() and pattern.lower() not in str(value).lower():
                continue
            exported = name in os.environ
            variables.append({
                'name': name,
                'value': value,
                'source': 'exported' if exported else 'shell',
            })
            seen.add(name)

    if opts['show_env']:
        for name, value in sorted(os.environ.items()):
            if name in seen:
                continue
            if pattern and pattern.lower() not in name.lower() and pattern.lower() not in str(value).lower():
                continue
            variables.append({
                'name': name,
                'value': value,
                'source': 'env',
            })

    return variables


def _print_table(variables: List[dict], opts: dict, use_color: bool):
    max_name = max(len(v['name']) for v in variables)
    max_name = max(max_name, 8)  # min col width

    try:
        term_width = os.get_terminal_size().columns
    except (AttributeError, ValueError, OSError):
        term_width = 80

    source_width = 8 if opts['show_source'] else 0
    border_chars = 7 if opts['show_source'] else 5  # "| " + " | " + " |" or similar
    max_value = term_width - max_name - source_width - border_chars
    max_value = max(max_value, 20)

    bc = BORDER_COLOR if use_color else ''
    rs = C_RESET if use_color else ''
    hdr_bg = HEADER_BG if use_color else ''
    bold = C_BOLD if use_color else ''

    name_bar = '─' * (max_name + 2)
    value_bar = '─' * (max_value + 2)
    source_bar = '─' * (source_width + 2) if opts['show_source'] else ''

    if opts['show_source']:
        print(f"{bc}┌{name_bar}┬{value_bar}┬{source_bar}┐{rs}")
        print(f"{bc}│{rs}{hdr_bg}{bold} {'Name':<{max_name}} {rs}{bc}│{rs}"
              f"{hdr_bg}{bold} {'Value':<{max_value}} {rs}{bc}│{rs}"
              f"{hdr_bg}{bold} {'Source':<{source_width}} {rs}{bc}│{rs}")
        print(f"{bc}├{name_bar}┼{value_bar}┼{source_bar}┤{rs}")
    else:
        print(f"{bc}┌{name_bar}┬{value_bar}┐{rs}")
        print(f"{bc}│{rs}{hdr_bg}{bold} {'Name':<{max_name}} {rs}{bc}│{rs}"
              f"{hdr_bg}{bold} {'Value':<{max_value}} {rs}{bc}│{rs}")
        print(f"{bc}├{name_bar}┼{value_bar}┤{rs}")

    for v in variables:
        name_str = _color_name(v['name'], use_color)
        name_pad = max_name - len(v['name'])

        display_val = v['value'].replace('\n', '\\n').replace('\t', '\\t')
        if len(display_val) > max_value:
            display_val = display_val[:max_value - 1] + '…'

        value_str = _color_value(display_val, use_color)
        value_pad = max_value - len(display_val)

        if opts['show_source']:
            source_str = _color_source(v['source'], use_color)
            source_pad = source_width - len(v['source'])
            print(f"{bc}│{rs} {name_str}{' ' * name_pad} "
                  f"{bc}│{rs} {value_str}{' ' * value_pad} "
                  f"{bc}│{rs} {source_str}{' ' * source_pad} {bc}│{rs}")
        else:
            print(f"{bc}│{rs} {name_str}{' ' * name_pad} "
                  f"{bc}│{rs} {value_str}{' ' * value_pad} {bc}│{rs}")

    if opts['show_source']:
        print(f"{bc}└{name_bar}┴{value_bar}┴{source_bar}┘{rs}")
    else:
        print(f"{bc}└{name_bar}┴{value_bar}┘{rs}")

    dim = C_DIM if use_color else ''
    print(f"{dim}{len(variables)} variable(s){rs}")


def _color_name(name: str, use_color: bool) -> str:
    if not use_color:
        return name
    return f"{C_CYAN}{name}{C_RESET}"


def _color_value(value: str, use_color: bool) -> str:
    if not use_color:
        return value
    if not value:
        return f"{C_DIM}(empty){C_RESET}"
    return f"{C_GREEN}{value}{C_RESET}"


def _color_source(source: str, use_color: bool) -> str:
    if not use_color:
        return source
    colors = {
        'shell': C_YELLOW,
        'env': C_BLUE,
        'exported': C_MAGENTA,
    }
    c = colors.get(source, '')
    return f"{c}{source}{C_RESET}"


def _print_help():
    print("""Usage: var [OPTION] [PATTERN]
Display shell and environment variables in a table.

  -s, --shell       show only shell-local variables
  -e, --env         show only environment variables
  -x, --exported    show only exported variables
      --no-color    disable colors
  -h, --help        show this help

PATTERN filters variables by name or value (case-insensitive).""")

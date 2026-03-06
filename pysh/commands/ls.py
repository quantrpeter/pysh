"""
Built-in ls command for pysh.

A pure-Python implementation of ls with colorized output, column layout,
and support for the most common flags.
"""

import os
import sys
import stat
import time
import grp
import pwd
from typing import List, Optional, Tuple


# ANSI color codes
C_RESET = '\033[0m'
C_BOLD = '\033[1m'
C_DIR = '\033[1;34m'       # bold blue
C_LINK = '\033[1;36m'      # bold cyan
C_EXEC = '\033[1;32m'      # bold green
C_FIFO = '\033[33m'        # yellow
C_SOCK = '\033[1;35m'      # bold magenta
C_BLK = '\033[1;33m'       # bold yellow
C_CHR = '\033[1;33m'       # bold yellow
C_SETUID = '\033[37;41m'   # white on red
C_SETGID = '\033[30;43m'   # black on yellow
C_STICKY = '\033[37;44m'   # white on blue
C_ORPHAN = '\033[1;31m'    # bold red (broken symlink)
C_ARCHIVE = '\033[1;31m'   # bold red
C_IMAGE = '\033[1;35m'     # bold magenta
C_AUDIO = '\033[0;36m'     # cyan
C_VIDEO = '\033[1;35m'     # bold magenta

ARCHIVE_EXTS = {'.tar', '.gz', '.bz2', '.xz', '.zip', '.rar', '.7z', '.tgz', '.zst', '.deb', '.rpm'}
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp', '.ico', '.tiff'}
AUDIO_EXTS = {'.mp3', '.wav', '.flac', '.ogg', '.aac', '.wma', '.m4a'}
VIDEO_EXTS = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm'}


class LsOptions:
    def __init__(self):
        self.long = False           # -l
        self.all = False            # -a (include . and ..)
        self.almost_all = False     # -A (include hidden, exclude . and ..)
        self.human = False          # -h
        self.recursive = False      # -R
        self.one_per_line = False   # -1
        self.reverse = False        # -r
        self.sort_time = False      # -t
        self.sort_size = False      # -S
        self.sort_none = False      # -U
        self.dir_only = False       # -d
        self.inode = False          # -i
        self.no_color = False
        self.classify = False       # -F
        self.no_group = False       # -G (in long format, hide group)
        self.dereference = False    # -L


def _parse_args(args: List[str]) -> Tuple[LsOptions, List[str]]:
    opts = LsOptions()
    paths = []

    i = 1
    while i < len(args):
        arg = args[i]
        if arg == '--':
            paths.extend(args[i + 1:])
            break
        if arg.startswith('-') and len(arg) > 1 and not arg.startswith('--'):
            for ch in arg[1:]:
                if ch == 'l': opts.long = True
                elif ch == 'a': opts.all = True
                elif ch == 'A': opts.almost_all = True
                elif ch == 'h': opts.human = True
                elif ch == 'R': opts.recursive = True
                elif ch == '1': opts.one_per_line = True
                elif ch == 'r': opts.reverse = True
                elif ch == 't': opts.sort_time = True
                elif ch == 'S': opts.sort_size = True
                elif ch == 'U': opts.sort_none = True
                elif ch == 'd': opts.dir_only = True
                elif ch == 'i': opts.inode = True
                elif ch == 'F': opts.classify = True
                elif ch == 'G': opts.no_group = True
                elif ch == 'L': opts.dereference = True
                else:
                    print(f"ls: invalid option -- '{ch}'", file=sys.stderr)
                    return opts, []
        elif arg == '--color=never':
            opts.no_color = True
        elif arg == '--color=always' or arg == '--color=auto' or arg == '--color':
            opts.no_color = False
        elif arg == '--help':
            _print_help()
            return opts, None
        else:
            paths.append(arg)
        i += 1

    if not paths:
        paths = ['.']

    return opts, paths


def builtin_ls(args: List[str]) -> int:
    opts, paths = _parse_args(args)
    if paths is None:
        return 0

    use_color = not opts.no_color and (sys.stdout.isatty() or os.environ.get('CLICOLOR_FORCE'))
    is_tty = sys.stdout.isatty()

    if not is_tty and not opts.long:
        opts.one_per_line = True

    status = 0
    show_header = len(paths) > 1 or opts.recursive

    first = True
    for path in paths:
        if not first:
            print()
        first = False

        if opts.dir_only:
            entries = [_stat_entry(path, path, opts)]
            if entries[0] is None:
                print(f"ls: cannot access '{path}': No such file or directory", file=sys.stderr)
                status = 2
                continue
            if show_header:
                print(f"{path}:")
            _display(entries, opts, use_color, is_tty)
            continue

        try:
            st = os.stat(path) if opts.dereference else os.lstat(path)
        except OSError as e:
            print(f"ls: cannot access '{path}': {e.strerror}", file=sys.stderr)
            status = 2
            continue

        if not stat.S_ISDIR(st.st_mode):
            entry = _stat_entry(path, os.path.dirname(path) or '.', opts)
            if entry:
                _display([entry], opts, use_color, is_tty)
            continue

        if show_header:
            print(f"{path}:")

        try:
            names = os.listdir(path)
        except PermissionError:
            print(f"ls: cannot open directory '{path}': Permission denied", file=sys.stderr)
            status = 2
            continue

        if opts.all:
            names = ['.', '..'] + sorted(names)
        elif opts.almost_all:
            names = sorted(names)
        else:
            names = sorted([n for n in names if not n.startswith('.')])

        entries = []
        for name in names:
            entry = _stat_entry(name, path, opts)
            if entry:
                entries.append(entry)

        entries = _sort_entries(entries, opts)
        _display(entries, opts, use_color, is_tty)

        if opts.recursive:
            subdirs = []
            for e in entries:
                if e['is_dir'] and e['name'] not in ('.', '..'):
                    subdirs.append(os.path.join(path, e['name']))
            for subdir in sorted(subdirs):
                print()
                first = False
                _list_recursive(subdir, opts, use_color, is_tty)

    return status


def _list_recursive(path: str, opts: LsOptions, use_color: bool, is_tty: bool):
    print(f"{path}:")
    try:
        names = os.listdir(path)
    except PermissionError:
        print(f"ls: cannot open directory '{path}': Permission denied", file=sys.stderr)
        return

    if opts.all:
        names = ['.', '..'] + sorted(names)
    elif opts.almost_all:
        names = sorted(names)
    else:
        names = sorted([n for n in names if not n.startswith('.')])

    entries = []
    for name in names:
        entry = _stat_entry(name, path, opts)
        if entry:
            entries.append(entry)

    entries = _sort_entries(entries, opts)
    _display(entries, opts, use_color, is_tty)

    subdirs = []
    for e in entries:
        if e['is_dir'] and e['name'] not in ('.', '..'):
            subdirs.append(os.path.join(path, e['name']))
    for subdir in sorted(subdirs):
        print()
        _list_recursive(subdir, opts, use_color, is_tty)


def _stat_entry(name: str, parent: str, opts: LsOptions) -> Optional[dict]:
    full = os.path.join(parent, name) if name not in ('.', '..') else os.path.join(parent, name)

    try:
        lst = os.lstat(full)
        if opts.dereference and stat.S_ISLNK(lst.st_mode):
            try:
                st = os.stat(full)
            except OSError:
                st = lst
        else:
            st = lst
    except OSError:
        return None

    is_link = stat.S_ISLNK(lst.st_mode)
    link_target = None
    link_broken = False
    if is_link:
        try:
            link_target = os.readlink(full)
            try:
                os.stat(full)
            except OSError:
                link_broken = True
        except OSError:
            link_target = '?'

    return {
        'name': name if name in ('.', '..') else os.path.basename(name) if '/' not in name else name,
        'full': full,
        'stat': st,
        'lstat': lst,
        'is_dir': stat.S_ISDIR(st.st_mode),
        'is_link': is_link,
        'link_target': link_target,
        'link_broken': link_broken,
        'mode': lst.st_mode,
    }


def _sort_entries(entries: list, opts: LsOptions) -> list:
    if opts.sort_none:
        result = entries
    elif opts.sort_time:
        result = sorted(entries, key=lambda e: e['stat'].st_mtime, reverse=True)
    elif opts.sort_size:
        result = sorted(entries, key=lambda e: e['stat'].st_size, reverse=True)
    else:
        result = sorted(entries, key=lambda e: e['name'].lower())

    if opts.reverse:
        result.reverse()
    return result


def _display(entries: list, opts: LsOptions, use_color: bool, is_tty: bool):
    if not entries:
        return

    if opts.long:
        _display_long(entries, opts, use_color)
    elif opts.one_per_line:
        for e in entries:
            prefix = f"{e['lstat'].st_ino} " if opts.inode else ""
            name = _colorize(e, use_color) + _classify_suffix(e, opts)
            print(f"{prefix}{name}")
    else:
        _display_columns(entries, opts, use_color)


def _display_long(entries: list, opts: LsOptions, use_color: bool):
    rows = []
    for e in entries:
        st = e['stat'] if not e['is_link'] else e['lstat']
        lst = e['lstat']

        mode_str = _format_mode(lst.st_mode)
        nlinks = str(lst.st_nlink)

        try:
            owner = pwd.getpwuid(lst.st_uid).pw_name
        except (KeyError, OverflowError):
            owner = str(lst.st_uid)

        if not opts.no_group:
            try:
                group = grp.getgrgid(lst.st_gid).gr_name
            except (KeyError, OverflowError):
                group = str(lst.st_gid)
        else:
            group = None

        size = e['stat'].st_size
        if stat.S_ISCHR(lst.st_mode) or stat.S_ISBLK(lst.st_mode):
            major = os.major(lst.st_rdev)
            minor = os.minor(lst.st_rdev)
            size_str = f"{major}, {minor:>3}"
        elif opts.human:
            size_str = _human_size(size)
        else:
            size_str = str(size)

        mtime = lst.st_mtime
        time_str = _format_time(mtime)

        name_str = _colorize(e, use_color) + _classify_suffix(e, opts)
        if e['is_link'] and e['link_target']:
            target_color = C_ORPHAN if e['link_broken'] else ''
            target_reset = C_RESET if (use_color and e['link_broken']) else ''
            if use_color and e['link_broken']:
                name_str += f" -> {target_color}{e['link_target']}{target_reset}"
            else:
                name_str += f" -> {e['link_target']}"

        inode_str = f"{lst.st_ino} " if opts.inode else ""

        rows.append({
            'inode': inode_str,
            'mode': mode_str,
            'nlinks': nlinks,
            'owner': owner,
            'group': group,
            'size': size_str,
            'time': time_str,
            'name': name_str,
        })

    w_nlinks = max(len(r['nlinks']) for r in rows)
    w_owner = max(len(r['owner']) for r in rows)
    w_group = max(len(r['group']) for r in rows) if not opts.no_group else 0
    w_size = max(len(r['size']) for r in rows)

    for r in rows:
        parts = [
            r['inode'],
            r['mode'],
            f" {r['nlinks']:>{w_nlinks}}",
            f" {r['owner']:<{w_owner}}",
        ]
        if not opts.no_group:
            parts.append(f" {r['group']:<{w_group}}")
        parts.extend([
            f" {r['size']:>{w_size}}",
            f" {r['time']}",
            f" {r['name']}",
        ])
        print(''.join(parts))

def _display_columns(entries: list, opts: LsOptions, use_color: bool):
    """Display entries in columns, like ls without -l."""
    try:
        term_width = os.get_terminal_size().columns
    except (AttributeError, ValueError, OSError):
        term_width = 80

    names = []
    raw_lens = []
    for e in entries:
        prefix = f"{e['lstat'].st_ino} " if opts.inode else ""
        colored = prefix + _colorize(e, use_color) + _classify_suffix(e, opts)
        raw = prefix + e['name'] + _classify_suffix(e, opts)
        names.append(colored)
        raw_lens.append(len(raw))

    n = len(names)
    if n == 0:
        return

    for ncols in range(n, 0, -1):
        nrows = (n + ncols - 1) // ncols
        col_widths = []
        fits = True
        for col in range(ncols):
            max_w = 0
            for row in range(nrows):
                idx = row + col * nrows
                if idx < n:
                    max_w = max(max_w, raw_lens[idx])
            col_widths.append(max_w)

        total = sum(col_widths) + 2 * (ncols - 1)
        if total <= term_width:
            for row in range(nrows):
                parts = []
                for col in range(ncols):
                    idx = row + col * nrows
                    if idx < n:
                        pad = col_widths[col] - raw_lens[idx]
                        if col < ncols - 1:
                            parts.append(names[idx] + ' ' * pad + '  ')
                        else:
                            parts.append(names[idx])
                print(''.join(parts))
            return

    for name in names:
        print(name)


def _colorize(entry: dict, use_color: bool) -> str:
    name = entry['name']
    if not use_color:
        return name

    mode = entry['mode']

    if entry['is_link']:
        if entry['link_broken']:
            return f"{C_ORPHAN}{name}{C_RESET}"
        return f"{C_LINK}{name}{C_RESET}"

    if stat.S_ISDIR(mode):
        if mode & stat.S_ISVTX and mode & stat.S_IWOTH:
            return f"{C_STICKY}{name}{C_RESET}"
        if mode & stat.S_ISVTX:
            return f"{C_STICKY}{name}{C_RESET}"
        return f"{C_DIR}{name}{C_RESET}"

    if stat.S_ISFIFO(mode):
        return f"{C_FIFO}{name}{C_RESET}"
    if stat.S_ISSOCK(mode):
        return f"{C_SOCK}{name}{C_RESET}"
    if stat.S_ISBLK(mode):
        return f"{C_BLK}{name}{C_RESET}"
    if stat.S_ISCHR(mode):
        return f"{C_CHR}{name}{C_RESET}"

    if mode & stat.S_ISUID:
        return f"{C_SETUID}{name}{C_RESET}"
    if mode & stat.S_ISGID:
        return f"{C_SETGID}{name}{C_RESET}"

    if mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
        return f"{C_EXEC}{name}{C_RESET}"

    _, ext = os.path.splitext(name)
    ext = ext.lower()
    if ext in ARCHIVE_EXTS:
        return f"{C_ARCHIVE}{name}{C_RESET}"
    if ext in IMAGE_EXTS:
        return f"{C_IMAGE}{name}{C_RESET}"
    if ext in AUDIO_EXTS:
        return f"{C_AUDIO}{name}{C_RESET}"
    if ext in VIDEO_EXTS:
        return f"{C_VIDEO}{name}{C_RESET}"

    return name


def _classify_suffix(entry: dict, opts: LsOptions) -> str:
    if not opts.classify:
        return ''
    mode = entry['mode']
    if stat.S_ISDIR(mode):
        return '/'
    if stat.S_ISLNK(entry['lstat'].st_mode):
        return '@'
    if stat.S_ISFIFO(mode):
        return '|'
    if stat.S_ISSOCK(mode):
        return '='
    if mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
        return '*'
    return ''


def _format_mode(mode: int) -> str:
    """Format file mode bits as rwxrwxrwx string."""
    ftypes = {
        stat.S_IFREG: '-', stat.S_IFDIR: 'd', stat.S_IFLNK: 'l',
        stat.S_IFBLK: 'b', stat.S_IFCHR: 'c', stat.S_IFIFO: 'p',
        stat.S_IFSOCK: 's',
    }
    ft = stat.S_IFMT(mode)
    result = [ftypes.get(ft, '?')]

    for shift, xbit, xchar in [
        (6, stat.S_ISUID, 's'),
        (3, stat.S_ISGID, 's'),
        (0, stat.S_ISVTX, 't'),
    ]:
        r = 'r' if mode & (stat.S_IRUSR >> (6 - shift)) else '-'
        w = 'w' if mode & (stat.S_IWUSR >> (6 - shift)) else '-'
        x_val = mode & (stat.S_IXUSR >> (6 - shift))
        special = mode & xbit
        if special and x_val:
            x = xchar
        elif special:
            x = xchar.upper()
        elif x_val:
            x = 'x'
        else:
            x = '-'
        result.extend([r, w, x])

    return ''.join(result)


def _format_time(mtime: float) -> str:
    """Format modification time as yyyy-mm-dd hh:mm:ss."""
    t = time.localtime(mtime)
    return time.strftime('%Y-%m-%d %H:%M:%S', t)


def _human_size(size: int) -> str:
    if size < 1024:
        return str(size)
    for unit in ('K', 'M', 'G', 'T', 'P'):
        size /= 1024.0
        if size < 10:
            return f"{size:.1f}{unit}"
        if size < 1024:
            return f"{size:.0f}{unit}"
    return f"{size:.0f}E"


def _print_help():
    print("""Usage: ls [OPTION]... [FILE]...
List directory contents (pysh built-in).

  -a            show all entries including . and ..
  -A            show hidden entries except . and ..
  -l            long listing format
  -h            human-readable sizes (with -l)
  -R            list subdirectories recursively
  -1            one entry per line
  -r            reverse sort order
  -t            sort by modification time (newest first)
  -S            sort by size (largest first)
  -U            do not sort
  -d            list directories themselves, not contents
  -i            show inode numbers
  -F            append indicator (/ for dirs, * for executables, etc.)
  -G            hide group in long listing
  -L            dereference symbolic links
  --color=WHEN  'always', 'auto', or 'never'
  --help        show this help""")

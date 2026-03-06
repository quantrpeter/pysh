"""
Custom built-in commands for pysh.

These override system commands with pure-Python implementations.
"""

from pysh.commands.ls import builtin_ls
from pysh.commands.var import builtin_var


CUSTOM_COMMANDS = {
    'ls': builtin_ls,
}

SHELL_COMMANDS = {
    'var': builtin_var,
}

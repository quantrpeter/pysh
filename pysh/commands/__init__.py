"""
Custom built-in commands for pysh.

These override system commands with pure-Python implementations.
"""

from pysh.commands.ls import builtin_ls


CUSTOM_COMMANDS = {
    'ls': builtin_ls,
}

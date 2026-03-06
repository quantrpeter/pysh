# pysh — A Python Shell

A bash-like shell implemented entirely in Python using only the standard library.

## Features

- **Command execution** — Run any external program found in `$PATH`
- **Pipelines** — `ls | grep foo | wc -l`
- **I/O redirection** — `>`, `>>`, `<`
- **Logical operators** — `&&`, `||`
- **Background jobs** — `sleep 10 &`, with `jobs`, `fg`, `bg`
- **Subshells** — `(cd /tmp && ls)`
- **Variable expansion** — `$HOME`, `${VAR}`, `$?`, `$$`
- **Glob expansion** — `*.py`, `src/**/*.txt`
- **Tilde expansion** — `~/Documents`
- **Quoting** — Single quotes, double quotes, backslash escapes
- **Aliases** — `alias ll='ls -la'`
- **Built-in commands** — `cd`, `pwd`, `echo`, `exit`, `export`, `unset`, `type`, `alias`, `unalias`, `history`, `source`, `jobs`, `fg`, `bg`, `set`, `read`, `test`, `[`
- **Tab completion** — Commands, files, and directories
- **Command history** — Persisted to `~/.pysh_history`
- **RC file** — Loads `~/.pyshrc` on startup
- **PS1 prompt** — Supports `\u`, `\h`, `\w`, `\W`, `\$` and more
- **Comments** — Lines starting with `#`
- **Signal handling** — Ctrl+C interrupts, Ctrl+D exits

## Quick Start

```bash
# Run interactively
python -m pysh

# Run a single command
python -m pysh -c "echo hello world"

# Run a script
python -m pysh script.sh
```

## Usage

```
python -m pysh              # interactive shell
python -m pysh -c "cmd"     # run a command string
python -m pysh script.sh    # run a script file
```

## RC File

Create `~/.pyshrc` to run commands on startup:

```bash
alias ll='ls -la'
alias la='ls -A'
alias ..='cd ..'
export EDITOR=vim
PS1='\u@\h:\w\$ '
```

## Requirements

- Python 3.8+
- No external dependencies

## Project Structure

```
pysh/
├── __init__.py      # Package metadata
├── __main__.py      # Entry point (python -m pysh)
├── shell.py         # Core shell: REPL, prompt, readline, RC loading
├── lexer.py         # Tokenizer: quotes, escapes, operators
├── parser.py        # Parser: pipelines, lists, subshells, redirects
├── executor.py      # Executor: fork/exec, pipes, redirects, globs
├── builtins.py      # Built-in commands (cd, export, alias, etc.)
└── jobs.py          # Job control (background processes, fg, bg)
```

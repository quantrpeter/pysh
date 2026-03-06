"""
Lexer/tokenizer for pysh shell commands.

Breaks raw input into tokens: words, operators, redirections, pipes, etc.
Handles single quotes, double quotes, escape characters, and variable references.
"""

from enum import Enum, auto
from dataclasses import dataclass, field
from typing import List, Optional


class TokenType(Enum):
    WORD = auto()
    PIPE = auto()           # |
    AND = auto()            # &&
    OR = auto()             # ||
    SEMICOLON = auto()      # ;
    REDIRECT_OUT = auto()   # >
    REDIRECT_APPEND = auto()  # >>
    REDIRECT_IN = auto()    # <
    HEREDOC = auto()        # <<
    BACKGROUND = auto()     # &
    NEWLINE = auto()
    LPAREN = auto()         # (
    RPAREN = auto()         # )
    EOF = auto()


@dataclass
class Token:
    type: TokenType
    value: str
    quoted: bool = False  # True if any part was quoted (suppress glob expansion)


class LexerError(Exception):
    pass


def tokenize(line: str) -> List[Token]:
    """Tokenize a shell command line into a list of tokens."""
    tokens: List[Token] = []
    i = 0
    n = len(line)

    while i < n:
        c = line[i]

        if c in (' ', '\t'):
            i += 1
            continue

        if c == '#':
            break

        if c == '\n':
            tokens.append(Token(TokenType.NEWLINE, '\n'))
            i += 1
            continue

        if c == ';':
            tokens.append(Token(TokenType.SEMICOLON, ';'))
            i += 1
            continue

        if c == '(':
            tokens.append(Token(TokenType.LPAREN, '('))
            i += 1
            continue

        if c == ')':
            tokens.append(Token(TokenType.RPAREN, ')'))
            i += 1
            continue

        if c == '|':
            if i + 1 < n and line[i + 1] == '|':
                tokens.append(Token(TokenType.OR, '||'))
                i += 2
            else:
                tokens.append(Token(TokenType.PIPE, '|'))
                i += 1
            continue

        if c == '&':
            if i + 1 < n and line[i + 1] == '&':
                tokens.append(Token(TokenType.AND, '&&'))
                i += 2
            else:
                tokens.append(Token(TokenType.BACKGROUND, '&'))
                i += 1
            continue

        if c == '>':
            if i + 1 < n and line[i + 1] == '>':
                tokens.append(Token(TokenType.REDIRECT_APPEND, '>>'))
                i += 2
            else:
                tokens.append(Token(TokenType.REDIRECT_OUT, '>'))
                i += 1
            continue

        if c == '<':
            if i + 1 < n and line[i + 1] == '<':
                tokens.append(Token(TokenType.HEREDOC, '<<'))
                i += 2
            else:
                tokens.append(Token(TokenType.REDIRECT_IN, '<'))
                i += 1
            continue

        word, i, was_quoted = _read_word(line, i, n)
        tokens.append(Token(TokenType.WORD, word, quoted=was_quoted))

    tokens.append(Token(TokenType.EOF, ''))
    return tokens


def _read_word(line: str, start: int, n: int) -> tuple:
    """Read a word token, handling quoting and escape sequences. Returns (word, new_pos, was_quoted)."""
    parts = []
    i = start
    was_quoted = False

    while i < n:
        c = line[i]

        if c in (' ', '\t', '\n', ';', '|', '&', '>', '<', '(', ')'):
            break

        if c == '#' and parts:
            break

        if c == '\\':
            if i + 1 < n:
                parts.append(line[i + 1])
                i += 2
            else:
                parts.append('\\')
                i += 1
            continue

        if c == "'":
            was_quoted = True
            i += 1
            while i < n and line[i] != "'":
                parts.append(line[i])
                i += 1
            if i >= n:
                raise LexerError("unterminated single quote")
            i += 1  # skip closing '
            continue

        if c == '"':
            was_quoted = True
            i += 1
            while i < n and line[i] != '"':
                if line[i] == '\\' and i + 1 < n and line[i + 1] in ('"', '\\', '$', '`', '\n'):
                    parts.append(line[i + 1])
                    i += 2
                else:
                    parts.append(line[i])
                    i += 1
            if i >= n:
                raise LexerError("unterminated double quote")
            i += 1  # skip closing "
            continue

        parts.append(c)
        i += 1

    return ''.join(parts), i, was_quoted

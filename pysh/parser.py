"""
Parser for pysh shell commands.

Converts a token stream into an AST of commands, pipelines, and lists.

Grammar (simplified):
    list        : pipeline ((AND | OR | SEMICOLON | BACKGROUND) pipeline)*
    pipeline    : command (PIPE command)*
    command     : (redirect | WORD)+ | '(' list ')'
    redirect    : (REDIRECT_OUT | REDIRECT_APPEND | REDIRECT_IN) WORD
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from pysh.lexer import Token, TokenType, LexerError


class ParseError(Exception):
    pass


@dataclass
class Redirect:
    op: str          # '>', '>>', '<'
    target: str
    quoted: bool = False


@dataclass
class SimpleCommand:
    args: List[str] = field(default_factory=list)
    redirects: List[Redirect] = field(default_factory=list)
    quoted_args: List[bool] = field(default_factory=list)  # parallel to args


@dataclass
class Pipeline:
    commands: List = field(default_factory=list)  # list of SimpleCommand or Subshell
    negated: bool = False


@dataclass
class Subshell:
    body: "CommandList" = None
    redirects: List[Redirect] = field(default_factory=list)


@dataclass
class ListEntry:
    pipeline: Pipeline
    operator: Optional[str] = None  # '&&', '||', '&', ';', or None (last)


@dataclass
class CommandList:
    entries: List[ListEntry] = field(default_factory=list)


class Parser:
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> Token:
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return Token(TokenType.EOF, '')

    def advance(self) -> Token:
        tok = self.peek()
        self.pos += 1
        return tok

    def expect(self, tt: TokenType) -> Token:
        tok = self.advance()
        if tok.type != tt:
            raise ParseError(f"expected {tt.name}, got {tok.type.name} ({tok.value!r})")
        return tok

    def _skip_newlines(self):
        while self.peek().type == TokenType.NEWLINE:
            self.advance()

    def parse(self) -> CommandList:
        self._skip_newlines()
        result = self._parse_list()
        if self.peek().type not in (TokenType.EOF, TokenType.RPAREN):
            raise ParseError(f"unexpected token: {self.peek().value!r}")
        return result

    def _parse_list(self) -> CommandList:
        entries: List[ListEntry] = []
        pipeline = self._parse_pipeline()
        if pipeline is None:
            return CommandList()

        while True:
            tok = self.peek()
            if tok.type in (TokenType.AND, TokenType.OR, TokenType.SEMICOLON, TokenType.BACKGROUND):
                op = self.advance().value
                entries.append(ListEntry(pipeline=pipeline, operator=op))
                self._skip_newlines()
                next_pipeline = self._parse_pipeline()
                if next_pipeline is None:
                    break
                pipeline = next_pipeline
            elif tok.type == TokenType.NEWLINE:
                entries.append(ListEntry(pipeline=pipeline, operator=';'))
                self._skip_newlines()
                next_pipeline = self._parse_pipeline()
                if next_pipeline is None:
                    break
                pipeline = next_pipeline
            else:
                entries.append(ListEntry(pipeline=pipeline, operator=None))
                break

        return CommandList(entries=entries)

    def _parse_pipeline(self) -> Optional[Pipeline]:
        negated = False
        if self.peek().type == TokenType.WORD and self.peek().value == '!':
            negated = True
            self.advance()

        cmd = self._parse_command()
        if cmd is None:
            if negated:
                raise ParseError("expected command after '!'")
            return None

        commands = [cmd]
        while self.peek().type == TokenType.PIPE:
            self.advance()
            self._skip_newlines()
            next_cmd = self._parse_command()
            if next_cmd is None:
                raise ParseError("expected command after '|'")
            commands.append(next_cmd)

        return Pipeline(commands=commands, negated=negated)

    def _parse_command(self) -> Optional[SimpleCommand]:
        if self.peek().type == TokenType.LPAREN:
            return self._parse_subshell()
        return self._parse_simple_command()

    def _parse_subshell(self):
        self.advance()  # consume '('
        self._skip_newlines()
        body = self._parse_list()
        self._skip_newlines()
        self.expect(TokenType.RPAREN)
        sub = Subshell(body=body)
        while self.peek().type in (TokenType.REDIRECT_OUT, TokenType.REDIRECT_APPEND, TokenType.REDIRECT_IN):
            sub.redirects.append(self._parse_redirect())
        return sub

    def _parse_redirect(self) -> Redirect:
        op_tok = self.advance()
        target_tok = self.peek()
        if target_tok.type != TokenType.WORD:
            raise ParseError(f"expected filename after '{op_tok.value}'")
        self.advance()
        return Redirect(op=op_tok.value, target=target_tok.value, quoted=target_tok.quoted)

    def _parse_simple_command(self) -> Optional[SimpleCommand]:
        cmd = SimpleCommand()
        found = False

        while True:
            tok = self.peek()
            if tok.type == TokenType.WORD:
                cmd.args.append(tok.value)
                cmd.quoted_args.append(tok.quoted)
                self.advance()
                found = True
            elif tok.type in (TokenType.REDIRECT_OUT, TokenType.REDIRECT_APPEND, TokenType.REDIRECT_IN):
                cmd.redirects.append(self._parse_redirect())
                found = True
            else:
                break

        return cmd if found else None

#!/usr/bin/env python3
"""
A+ to Python and JavaScript Transpiler
======================================
Parses .a+ files (KAPL-encoded or plaintext with APL symbols) and generates
equivalent Python and JavaScript code using a recursive-descent parser.

Usage:
    python transpile_aplus.py --input program.a+ --output-py out.py --output-js out.js
"""

import sys
import argparse
from enum import Enum, auto
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════
# KAPL decoding
# ═══════════════════════════════════════════════════════════════════════

KAPL_TO_UNICODE: dict[int, str] = {
    0xFB: '\u2190',   # ←  assign
    0xD5: '\u2395',   # ⎕  quad (print)
    0xE3: '\u235D',   # ⍝  lamp (comment)
    0xCE: '\u2374',   # ⍴  rho (reshape)
    0xDF: '\u00F7',   # ÷  divide
    0xC1: '\u00D7',   # ×  multiply
    0xA2: '\u2373',   # ⍳  iota
    0xAB: '\u2308',   # ⌈  ceiling
    0xA8: '\u220A',   # ∊  member
    0xAC: '\u230A',   # ⌊  floor
}


def decode_kapl(data: bytes) -> str:
    """Map KAPL-encoded bytes to a Unicode string, preserving printable ASCII."""
    result: list[str] = []
    for b in data:
        if b in KAPL_TO_UNICODE:
            result.append(KAPL_TO_UNICODE[b])
        elif 0x20 <= b <= 0x7E or b in (0x0A, 0x0D, 0x09):
            result.append(chr(b))
        else:
            result.append(chr(b))   # pass-through Latin-1
    return ''.join(result)


# ═══════════════════════════════════════════════════════════════════════
# Tokenizer
# ═══════════════════════════════════════════════════════════════════════

class TokenType(Enum):
    IDENT      = auto()
    NUMBER     = auto()
    STRING     = auto()
    ASSIGN     = auto()   # ←
    QUAD       = auto()   # ⎕  print
    LAMP       = auto()   # ⍝  comment
    RHO_SYM    = auto()   # ⍴  reshape (symbol form)
    DIVIDE_SYM = auto()   # ÷  divide (symbol form)
    MULT_SYM   = auto()   # ×  multiply (symbol form)
    IOTA_SYM   = auto()   # ⍳  iota (symbol form)
    PLUS       = auto()
    MINUS      = auto()
    STAR       = auto()   # * (exponentiation / sign)
    SLASH      = auto()   # / (reduce / compress)
    BACKSLASH  = auto()   # \ (scan / expand)
    LPAREN     = auto()
    RPAREN     = auto()
    LBRACE     = auto()
    RBRACE     = auto()
    LBRACKET   = auto()
    RBRACKET   = auto()
    COLON      = auto()
    SEMICOLON  = auto()
    DOT        = auto()
    EQUAL      = auto()   # =  equality
    LESS       = auto()   # <  less than
    GREATER    = auto()   # >  greater than
    LE         = auto()   # <= less-equal
    GE         = auto()   # >= greater-equal
    INNER_PROD = auto()   # +.×  or  +.*
    REDUCE_OP  = auto()   # +/  */  -/  (reduce operators)
    KW_IF      = auto()
    KW_WHILE   = auto()
    KW_ELSE    = auto()
    NEWLINE    = auto()
    EOF        = auto()


_KEYWORDS = {'if': TokenType.KW_IF, 'while': TokenType.KW_WHILE, 'else': TokenType.KW_ELSE}

# Symbolic single-char tokens
_SYM_SINGLE: dict[str, TokenType] = {
    '\u2190': TokenType.ASSIGN,      # ←
    '\u2395': TokenType.QUAD,        # ⎕
    '\u2374': TokenType.RHO_SYM,     # ⍴
    '\u00F7': TokenType.DIVIDE_SYM,  # ÷
    '\u00D7': TokenType.MULT_SYM,    # ×
    '\u2373': TokenType.IOTA_SYM,    # ⍳
}

# ASCII operator tokens
_ASCII_OPS: dict[str, TokenType] = {
    '+': TokenType.PLUS,
    '-': TokenType.MINUS,
    '*': TokenType.STAR,
    '/': TokenType.SLASH,
    '\\': TokenType.BACKSLASH,
    '(': TokenType.LPAREN,
    ')': TokenType.RPAREN,
    '{': TokenType.LBRACE,
    '}': TokenType.RBRACE,
    '[': TokenType.LBRACKET,
    ']': TokenType.RBRACKET,
    ':': TokenType.COLON,
    ';': TokenType.SEMICOLON,
    '.': TokenType.DOT,
    '=': TokenType.EQUAL,
    '<': TokenType.LESS,
    '>': TokenType.GREATER,
}


class Token:
    __slots__ = ('type', 'value', 'line', 'col')

    def __init__(self, typ: TokenType, value: str, line: int, col: int):
        self.type = typ
        self.value = value
        self.line = line
        self.col = col

    def __repr__(self) -> str:
        return f"Token({self.type.name}, {self.value!r}, L{self.line}:{self.col})"


class Lexer:
    def __init__(self, source: str):
        self.src = source
        self.pos = 0
        self.line = 1
        self.col = 0
        self.tokens: list[Token] = []

    def _cur(self) -> str:
        return self.src[self.pos] if self.pos < len(self.src) else '\0'

    def _advance(self) -> str:
        ch = self._cur()
        self.pos += 1
        if ch == '\n':
            self.line += 1
            self.col = 0
        else:
            self.col += 1
        return ch

    def _emit(self, typ: TokenType, val: str, line: int, col: int) -> None:
        self.tokens.append(Token(typ, val, line, col))

    def tokenize(self) -> list[Token]:
        while self.pos < len(self.src):
            ch = self._cur()
            sl, sc = self.line, self.col + 1

            # whitespace (not newline)
            if ch in ' \t\r':
                self._advance()
                continue

            # newline
            if ch == '\n':
                self._advance()
                self._emit(TokenType.NEWLINE, '\n', sl, sc)
                continue

            # comment: ⍝ or #
            if ch in ('\u235D', '#'):
                self._advance()
                buf: list[str] = []
                while self.pos < len(self.src) and self._cur() != '\n':
                    buf.append(self._advance())
                self._emit(TokenType.LAMP, ''.join(buf), sl, sc)
                continue

            # number literal (including floats)
            if ch.isdigit() or (ch == '.' and self.pos + 1 < len(self.src)
                                and self.src[self.pos + 1].isdigit()):
                buf: list[str] = []
                while self.pos < len(self.src) and (self._cur().isdigit() or self._cur() == '.'):
                    buf.append(self._advance())
                self._emit(TokenType.NUMBER, ''.join(buf), sl, sc)
                continue

            # identifier / keyword
            if ch.isalpha() or ch == '_':
                buf = []
                while self.pos < len(self.src) and (self._cur().isalnum() or self._cur() == '_'):
                    buf.append(self._advance())
                word = ''.join(buf)
                if word in _KEYWORDS:
                    self._emit(_KEYWORDS[word], word, sl, sc)
                else:
                    # All word-form function names (divide, rho, iota, etc.)
                    # stay as IDENT — the code generator handles the mapping.
                    self._emit(TokenType.IDENT, word, sl, sc)
                continue

            # string literal
            if ch in ('"', "'"):
                quote = self._advance()
                buf = []
                while self.pos < len(self.src) and self._cur() != quote:
                    if self._cur() == '\\':
                        buf.append(self._advance())
                    buf.append(self._advance())
                if self.pos < len(self.src):
                    self._advance()
                self._emit(TokenType.STRING, ''.join(buf), sl, sc)
                continue

            # symbolic APL characters
            if ch in _SYM_SINGLE:
                self._advance()
                self._emit(_SYM_SINGLE[ch], ch, sl, sc)
                continue

            # ASCII operators
            if ch in _ASCII_OPS:
                self._advance()
                self._emit(_ASCII_OPS[ch], ch, sl, sc)
                continue

            # unknown — skip
            self._advance()

        self._emit(TokenType.EOF, '', self.line, self.col + 1)

        # Post-processing: merge  PLUS DOT (MULT_SYM|STAR)  →  INNER_PROD
        #                  merge  (PLUS|MINUS|STAR) SLASH   →  REDUCE_OP
        return self._merge_operators()

    def _merge_operators(self) -> list[Token]:
        """Merge OP SLASH -> REDUCE_OP and PLUS DOT OP -> INNER_PROD."""
        merged: list[Token] = []
        i = 0
        while i < len(self.tokens):
            t = self.tokens[i]
            # OP SLASH -> REDUCE_OP (+/  */  -/  ÷/)
            if (t.type in (TokenType.PLUS, TokenType.MINUS, TokenType.STAR, TokenType.DIVIDE_SYM, TokenType.MULT_SYM)
                    and i + 1 < len(self.tokens)
                    and self.tokens[i + 1].type == TokenType.SLASH):
                merged.append(Token(
                    TokenType.REDUCE_OP,
                    t.value + '/',
                    t.line, t.col,
                ))
                i += 2
            # LESS EQUAL -> LE (<=)
            elif (t.type == TokenType.LESS
                    and i + 1 < len(self.tokens)
                    and self.tokens[i + 1].type == TokenType.EQUAL):
                merged.append(Token(TokenType.LE, '<=', t.line, t.col))
                i += 2
            # GREATER EQUAL -> GE (>=)
            elif (t.type == TokenType.GREATER
                    and i + 1 < len(self.tokens)
                    and self.tokens[i + 1].type == TokenType.EQUAL):
                merged.append(Token(TokenType.GE, '>=', t.line, t.col))
                i += 2
            # PLUS DOT (MULT_SYM|STAR) -> INNER_PROD
            elif (t.type == TokenType.PLUS
                    and i + 2 < len(self.tokens)
                    and self.tokens[i + 1].type == TokenType.DOT
                    and self.tokens[i + 2].type in (TokenType.MULT_SYM, TokenType.STAR)):
                merged.append(Token(
                    TokenType.INNER_PROD,
                    '+.' + self.tokens[i + 2].value,
                    t.line, t.col,
                ))
                i += 3
            else:
                merged.append(t)
                i += 1
        return merged


# ═══════════════════════════════════════════════════════════════════════
# A+ built-in function names  →  (python_func, js_func)
# ═══════════════════════════════════════════════════════════════════════

# Maps A+ word-form function names and symbol-form names to target helpers.
# Values are (python_name, js_name) or None if handled specially.
_BUILTIN_MAP: dict[str, tuple[str, str]] = {
    # Word forms
    'divide':   ('_divide', '_divide'),
    'multiply': ('_multiply', '_multiply'),
    'times':    ('_multiply', '_multiply'),
    'rho':      ('_reshape', '_reshape'),
    'reshape':  ('_reshape', '_reshape'),
    'iota':     ('_iota', '_iota'),
    # Symbol forms (Unicode)
    '\u00F7':   ('_divide', '_divide'),   # ÷
    '\u00D7':   ('_multiply', '_multiply'),  # ×
    '\u2374':   ('_reshape', '_reshape'),  # ⍴
    '\u2373':   ('_iota', '_iota'),       # ⍳
}


# ═══════════════════════════════════════════════════════════════════════
# AST nodes
# ═══════════════════════════════════════════════════════════════════════

class AST:
    pass


class Program(AST):
    def __init__(self, stmts: list[AST]):
        self.stmts = stmts


class CommentStmt(AST):
    def __init__(self, text: str):
        self.text = text.strip()


class Assignment(AST):
    def __init__(self, name: str, expr: AST):
        self.name = name
        self.expr = expr


class PrintStmt(AST):
    def __init__(self, expr: AST):
        self.expr = expr


class IfStmt(AST):
    def __init__(self, cond: AST, body: list[AST], else_body: Optional[list[AST]] = None):
        self.cond = cond
        self.body = body
        self.else_body = else_body


class WhileStmt(AST):
    def __init__(self, cond: AST, body: list[AST]):
        self.cond = cond
        self.body = body


class FuncDef(AST):
    def __init__(self, name: str, params: list[str], body: list[AST]):
        self.name = name
        self.params = params
        self.body = body


class ReturnStmt(AST):
    def __init__(self, expr: AST):
        self.expr = expr


class BinaryOp(AST):
    def __init__(self, op: str, left: AST, right: AST):
        self.op = op
        self.left = left
        self.right = right


class UnaryOp(AST):
    def __init__(self, op: str, operand: AST):
        self.op = op
        self.operand = operand


class FuncCall(AST):
    """A call to a named function (user-defined or built-in)."""
    def __init__(self, name: str, args: list[AST]):
        self.name = name
        self.args = args


class IndexAccess(AST):
    def __init__(self, array: AST, indices: list[AST]):
        self.array = array
        self.indices = indices


class InnerProduct(AST):
    def __init__(self, left: AST, right: AST):
        self.left = left
        self.right = right


class NumberLit(AST):
    def __init__(self, value: str):
        self.value = value


class StringLit(AST):
    def __init__(self, value: str):
        self.value = value


class Ident(AST):
    def __init__(self, name: str):
        self.name = name


class ArrayLiteral(AST):
    def __init__(self, elements: list[AST]):
        self.elements = elements


# ═══════════════════════════════════════════════════════════════════════
# Recursive-descent parser
# ═══════════════════════════════════════════════════════════════════════

class ParseError(Exception):
    def __init__(self, msg: str, token: Token):
        super().__init__(f"{msg} at line {token.line}, col {token.col}")
        self.token = token


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0

    def _peek(self) -> Token:
        return self.tokens[self.pos]

    def _advance(self) -> Token:
        t = self._peek()
        self.pos += 1
        return t

    def _expect(self, typ: TokenType) -> Token:
        t = self._peek()
        if t.type != typ:
            raise ParseError(
                f"Expected {typ.name}, got {t.type.name} ({t.value!r})", t,
            )
        return self._advance()

    def _skip_nl(self) -> None:
        while self._peek().type == TokenType.NEWLINE:
            self._advance()

    # Token categories --------------------------------------------------

    def _is_atom_start(self, tok: Token) -> bool:
        """Can *tok* begin a primary expression?"""
        return tok.type in (
            TokenType.NUMBER, TokenType.STRING, TokenType.IDENT,
            TokenType.LPAREN, TokenType.LBRACKET,
            TokenType.MINUS, TokenType.PLUS, TokenType.STAR,
            TokenType.IOTA_SYM, TokenType.RHO_SYM,
            TokenType.DIVIDE_SYM, TokenType.MULT_SYM,
            TokenType.REDUCE_OP, TokenType.SLASH,
        )

    def _is_binary_op(self, tok: Token) -> bool:
        """Is *tok* a binary operator?"""
        return tok.type in (
            TokenType.PLUS, TokenType.MINUS, TokenType.STAR,
            TokenType.MULT_SYM, TokenType.DIVIDE_SYM,
            TokenType.SLASH, TokenType.BACKSLASH,
            TokenType.EQUAL, TokenType.LESS, TokenType.GREATER,
            TokenType.LE, TokenType.GE,
        )

    # -- entry ---------------------------------------------------------

    def parse(self) -> Program:
        stmts: list[AST] = []
        max_iter = 10000
        it = 0
        while self._peek().type != TokenType.EOF:
            it += 1; 
            if it > max_iter: 
                raise ParseError(f"Infinite loop detected at token {self.pos} ({self._peek().type.name})", self._peek())
            self._skip_nl()
            if self._peek().type == TokenType.EOF:
                break
            s = self._parse_statement()
            if s is not None:
                stmts.append(s)
        return Program(stmts)

    # -- statements ----------------------------------------------------

    def _parse_statement(self) -> Optional[AST]:
        tok = self._peek()

        if tok.type == TokenType.LAMP:
            self._advance()
            return CommentStmt(tok.value)

        if tok.type == TokenType.KW_IF:
            return self._parse_if()

        if tok.type == TokenType.KW_WHILE:
            return self._parse_while()

        if tok.type == TokenType.QUAD:
            self._advance()
            return PrintStmt(self._parse_expression())

        # function definition:  name { params } :  { body }
        # function call:         name { arg1; arg2 }
        if tok.type == TokenType.IDENT:
            saved = self.pos
            self._advance()
            if self._peek().type == TokenType.LBRACE:
                # Peek ahead: is this a definition (has colon after params) or call?
                look = self.pos + 1
                brace_depth = 1
                has_colon = False
                look_limit = look + 200  # safety bound
                while look < len(self.tokens) and brace_depth > 0 and look < look_limit:
                    lt = self.tokens[look]
                    if lt.type == TokenType.LBRACE:
                        brace_depth += 1
                    elif lt.type == TokenType.RBRACE:
                        brace_depth -= 1
                    look += 1
                # Check if there's a colon after the closing brace
                if look < len(self.tokens) and self.tokens[look].type == TokenType.COLON:
                    self.pos = saved
                    return self._parse_func_def()
                # Otherwise it's a function call
            self.pos = saved

        # assignment:  IDENT ← expr   or   IDENT [ idx ] ← expr
        if tok.type == TokenType.IDENT:
            saved = self.pos
            self._advance()
            nxt = self._peek()
            # Check for multi-assignment: IDENT IDENT ← expr
            if nxt.type == TokenType.IDENT:
                look = self.pos + 1
                if look < len(self.tokens) and self.tokens[look].type == TokenType.ASSIGN:
                    self.pos = saved
                    return self._parse_multi_assignment()
            # Check for IDENT ← expr
            if nxt.type == TokenType.ASSIGN:
                self.pos = saved
                return self._parse_assignment()
            # Check for IDENT [ idx ] ← expr
            if nxt.type == TokenType.LBRACKET:
                # Consume IDENT [ ... ] to find if ← follows
                look = self.pos
                bracket_depth = 1
                while look < len(self.tokens) and bracket_depth > 0:
                    lt = self.tokens[look]
                    if lt.type == TokenType.LBRACKET:
                        bracket_depth += 1
                    elif lt.type == TokenType.RBRACKET:
                        bracket_depth -= 1
                    look += 1
                if look < len(self.tokens) and self.tokens[look].type == TokenType.ASSIGN:
                    self.pos = saved
                    return self._parse_assignment()  # will parse name[idx]←expr
            self.pos = saved

        # expression statement — fallback
        try:
            return self._parse_expression()
        except ParseError:
            # Skip until next statement boundary, consuming as we go
            while self._peek().type not in (TokenType.NEWLINE, TokenType.SEMICOLON,
                                             TokenType.RBRACE, TokenType.EOF):
                self._advance()
            # Consume the boundary token
            if self._peek().type in (TokenType.NEWLINE, TokenType.SEMICOLON):
                self._advance()
            return None

    def _parse_assignment(self) -> Assignment:
        name = self._expect(TokenType.IDENT).value
        # Handle indexed assignment: name[idx] ← expr
        if self._peek().type == TokenType.LBRACKET:
            self._advance()
            idx_expr = self._parse_expression()
            self._expect(TokenType.RBRACKET)
            # Flatten: store as 'name[idx_repr]' with the index pre-rendered
            idx_str = str(PythonGenerator()._gen_expr(idx_expr))
            name = f'{name}[{idx_str}]'
        self._expect(TokenType.ASSIGN)
        expr = self._parse_expression()
        return Assignment(name, expr)

    def _parse_multi_assignment(self) -> Assignment:
        """Handle multi-assignment: L U ← expr"""
        names = []
        names.append(self._expect(TokenType.IDENT).value)
        while self._peek().type == TokenType.IDENT:
            names.append(self._advance().value)
        self._expect(TokenType.ASSIGN)
        expr = self._parse_expression()
        # Render as tuple unpacking
        combined_name = ', '.join(names)
        return Assignment(combined_name, expr)

    def _parse_if(self) -> IfStmt:
        self._expect(TokenType.KW_IF)
        self._expect(TokenType.LPAREN)
        cond = self._parse_expression()
        self._expect(TokenType.RPAREN)
        body = self._parse_block()
        else_body: Optional[list[AST]] = None
        # Skip whitespace before checking for else
        self._skip_nl()
        if self._peek().type == TokenType.KW_ELSE:
            self._advance()
            self._skip_nl()
            if self._peek().type == TokenType.KW_IF:
                else_body = [self._parse_if()]
            else:
                else_body = self._parse_block()
        return IfStmt(cond, body, else_body)

    def _parse_while(self) -> WhileStmt:
        self._expect(TokenType.KW_WHILE)
        self._expect(TokenType.LPAREN)
        cond = self._parse_expression()
        self._expect(TokenType.RPAREN)
        body = self._parse_block()
        return WhileStmt(cond, body)

    def _parse_block(self) -> list[AST]:
        self._expect(TokenType.LBRACE)
        stmts: list[AST] = []
        while self._peek().type not in (TokenType.RBRACE, TokenType.EOF):
            self._skip_nl()
            if self._peek().type in (TokenType.RBRACE, TokenType.EOF):
                break
            s = self._parse_statement()
            if s is not None:
                stmts.append(s)
            # Skip optional semicolons and newlines between statements
            while self._peek().type in (TokenType.SEMICOLON, TokenType.NEWLINE):
                self._advance()
        self._expect(TokenType.RBRACE)
        return stmts

    def _parse_func_def(self) -> FuncDef:
        name = self._expect(TokenType.IDENT).value
        self._expect(TokenType.LBRACE)
        params = self._parse_params()
        self._expect(TokenType.RBRACE)
        self._expect(TokenType.COLON)
        self._skip_nl()

        body: list[AST]
        if self._peek().type == TokenType.LBRACE:
            body = self._parse_block()
        else:
            body = [ReturnStmt(self._parse_expression())]

        # Wrap bare expressions in ReturnStmt
        if len(body) == 1 and isinstance(body[0], (
            BinaryOp, UnaryOp, FuncCall, Ident, NumberLit, StringLit,
            ArrayLiteral, IndexAccess, InnerProduct,
        )):
            body = [ReturnStmt(body[0])]
        return FuncDef(name, params, body)

    def _parse_params(self) -> list[str]:
        params: list[str] = []
        self._skip_nl()
        if self._peek().type == TokenType.IDENT:
            params.append(self._advance().value)
            while self._peek().type == TokenType.SEMICOLON:
                self._advance()
                self._skip_nl()
                params.append(self._expect(TokenType.IDENT).value)
        return params

    # -- expressions ---------------------------------------------------

    def _parse_expression(self) -> AST:
        """expression  →  additive (additive)*   → array literal if >1"""
        first = self._parse_additive()
        elems = [first]
        while self._is_atom_start(self._peek()):
            elems.append(self._parse_additive())
        if len(elems) == 1:
            return elems[0]
        return ArrayLiteral(elems)

    def _parse_additive(self) -> AST:
        left = self._parse_multiplicative()
        while self._peek().type in (TokenType.PLUS, TokenType.MINUS, TokenType.SLASH, TokenType.BACKSLASH,
                                    TokenType.EQUAL, TokenType.LESS, TokenType.GREATER,
                                    TokenType.LE, TokenType.GE):
            op = self._advance().value
            right = self._parse_multiplicative()
            left = BinaryOp(op, left, right)
        return left

    def _parse_multiplicative(self) -> AST:
        left = self._parse_inner_product()
        while self._peek().type in (TokenType.MULT_SYM, TokenType.DIVIDE_SYM, TokenType.STAR):
            op_tok = self._advance()
            op = op_tok.value
            if op == '\u00D7':
                op = '*'
            elif op == '\u00F7':
                op = '/'
            right = self._parse_inner_product()
            left = BinaryOp(op, left, right)
        return left

    def _parse_inner_product(self) -> AST:
        """inner_product  →  unary (INNER_PROD unary)?"""
        left = self._parse_unary()
        while self._peek().type == TokenType.INNER_PROD:
            self._advance()
            right = self._parse_unary()
            left = InnerProduct(left, right)
        return left

    def _parse_unary(self) -> AST:
        tok = self._peek()
        if tok.type == TokenType.MINUS:
            self._advance()
            return UnaryOp('-', self._parse_unary())
        if tok.type == TokenType.PLUS:
            self._advance()
            return FuncCall('_conjugate', [self._parse_unary()])
        if tok.type == TokenType.STAR:
            self._advance()
            return FuncCall('_sign', [self._parse_unary()])
        # Reduce operators: +/ expr, */ expr, -/ expr
        if tok.type == TokenType.REDUCE_OP:
            op_val = self._advance().value  # '+/', '*/', '-/'
            arg = self._parse_unary()
            return FuncCall(f'_reduce_{op_val[0]}', [arg])
        # Symbolic iota/rho can appear as unary prefix functions:
        if tok.type == TokenType.IOTA_SYM:
            self._advance()
            arg = self._parse_unary()
            return FuncCall('\u2373', [arg])
        if tok.type == TokenType.RHO_SYM:
            self._advance()
            # Dyadic rho:  ⍴ shape data  (prefix)
            # Monadic rho: ⍴ arr          (shape of arr)
            saved = self.pos
            shape = self._parse_unary()
            # If another expression follows, it's dyadic
            if self._is_atom_start(self._peek()):
                data = self._parse_unary()
                return FuncCall('\u2374', [shape, data])
            # Monadic: just shape-of
            return FuncCall('\u2374_shape', [shape])
        return self._parse_postfix()

    def _parse_postfix(self) -> AST:
        """Handle indexing:  expr [ idx ; idx ]   and function call: expr { arg }"""
        expr = self._parse_atom()
        # Function call: expr { arg1; arg2 }
        if self._peek().type == TokenType.LBRACE:
            self._advance()
            args: list[AST] = []
            if self._peek().type != TokenType.RBRACE:
                args.append(self._parse_expression())
                while self._peek().type == TokenType.SEMICOLON:
                    self._advance()
                    args.append(self._parse_expression())
            self._expect(TokenType.RBRACE)
            if isinstance(expr, Ident):
                return FuncCall(expr.name, args)
            # Not an ident — treat as application
            return FuncCall('_apply', [expr] + args)
        # Indexing: expr [ idx ; idx ]
        while self._peek().type == TokenType.LBRACKET:
            self._advance()
            indices: list[AST] = [self._parse_expression()]
            while self._peek().type == TokenType.SEMICOLON:
                self._advance()
                indices.append(self._parse_expression())
            self._expect(TokenType.RBRACKET)
            expr = IndexAccess(expr, indices)
        return expr

    def _parse_atom(self) -> AST:
        tok = self._peek()

        # parenthesised expression
        if tok.type == TokenType.LPAREN:
            self._advance()
            e = self._parse_expression()
            self._expect(TokenType.RPAREN)
            return e

        # number
        if tok.type == TokenType.NUMBER:
            self._advance()
            return NumberLit(tok.value)

        # string
        if tok.type == TokenType.STRING:
            self._advance()
            return StringLit(tok.value)

        # identifier  →  variable reference or function call
        if tok.type == TokenType.IDENT:
            name = self._advance().value
            # Gather arguments: subsequent atom-start tokens that aren't
            # operators or statement delimiters.
            args: list[AST] = []
            while self._is_atom_start(self._peek()):
                nxt = self._peek()
                if nxt.type in (TokenType.PLUS, TokenType.MINUS,
                                TokenType.MULT_SYM, TokenType.DIVIDE_SYM,
                                TokenType.STAR, TokenType.ASSIGN,
                                TokenType.RPAREN, TokenType.RBRACE,
                                TokenType.RBRACKET, TokenType.SEMICOLON,
                                TokenType.COLON, TokenType.DOT,
                                TokenType.INNER_PROD, TokenType.NEWLINE,
                                TokenType.EOF, TokenType.LAMP,
                                TokenType.KW_IF, TokenType.KW_WHILE,
                                TokenType.KW_ELSE, TokenType.QUAD):
                    break
                args.append(self._parse_atom())
            if args:
                return FuncCall(name, args)
            return Ident(name)

        # Symbol-form function in atom position (e.g. ÷ as prefix call)
        if tok.type in (TokenType.DIVIDE_SYM, TokenType.MULT_SYM,
                         TokenType.RHO_SYM, TokenType.IOTA_SYM):
            sym = self._advance().value
            args: list[AST] = []
            while self._is_atom_start(self._peek()):
                nxt = self._peek()
                if nxt.type in (TokenType.PLUS, TokenType.MINUS,
                                TokenType.MULT_SYM, TokenType.DIVIDE_SYM,
                                TokenType.STAR, TokenType.ASSIGN,
                                TokenType.RPAREN, TokenType.RBRACE,
                                TokenType.RBRACKET, TokenType.SEMICOLON,
                                TokenType.COLON, TokenType.DOT,
                                TokenType.INNER_PROD, TokenType.NEWLINE,
                                TokenType.EOF, TokenType.LAMP,
                                TokenType.KW_IF, TokenType.KW_WHILE,
                                TokenType.KW_ELSE, TokenType.QUAD,
                                TokenType.RHO_SYM, TokenType.IOTA_SYM,
                                TokenType.DIVIDE_SYM, TokenType.MULT_SYM):
                    break
                args.append(self._parse_atom())
            if args:
                return FuncCall(sym, args)
            # Bare symbol without args — return as Ident for codegen
            return Ident(sym)

        # array literal: [ a ; b ; c ]
        if tok.type == TokenType.LBRACKET:
            self._advance()
            elems: list[AST] = []
            if self._peek().type != TokenType.RBRACKET:
                elems.append(self._parse_expression())
                while self._peek().type == TokenType.SEMICOLON:
                    self._advance()
                    elems.append(self._parse_expression())
            self._expect(TokenType.RBRACKET)
            return ArrayLiteral(elems)

        raise ParseError(f"Unexpected token {tok.type.name} ({tok.value!r})", tok)


# ═══════════════════════════════════════════════════════════════════════
# Code generators
# ═══════════════════════════════════════════════════════════════════════

class CodeGenBase:
    """Shared logic for Python and JS generators."""

    def __init__(self):
        self.indent = 0
        self.lines: list[str] = []
        self._needs_divide = False
        self._needs_multiply = False
        self._needs_reshape = False
        self._needs_iota = False
        self._needs_matmul = False

    def _emit(self, text: str) -> None:
        self.lines.append('    ' * self.indent + text)

    def _gen_builtin_call(self, name: str, args: list[AST], gen_expr) -> str:
        """Map A+ built-in calls to target helpers."""
        entry = _BUILTIN_MAP.get(name)
        if entry is None:
            # Not a known built-in — regular function call
            rendered = ', '.join(gen_expr(a) for a in args)
            return f'{name}({rendered})'

        py_name, js_name = entry
        if py_name == '_divide':
            self._needs_divide = True
            rendered = ', '.join(gen_expr(a) for a in args)
            return f'{py_name}({rendered})'  # py_name == js_name
        elif py_name == '_multiply':
            self._needs_multiply = True
            rendered = ', '.join(gen_expr(a) for a in args)
            return f'{py_name}({rendered})'
        elif py_name == '_reshape':
            self._needs_reshape = True
            rendered = ', '.join(gen_expr(a) for a in args)
            return f'{py_name}({rendered})'
        elif py_name == '_iota':
            self._needs_iota = True
            rendered = ', '.join(gen_expr(a) for a in args)
            return f'{py_name}({rendered})'
        else:
            rendered = ', '.join(gen_expr(a) for a in args)
            return f'{name}({rendered})'

    # Helpers appended at the end of output ----------------------------
    def _emit_helpers(self, py: bool) -> None:
        if self._needs_divide:
            self._gen_divide(py)
        if self._needs_multiply:
            self._gen_multiply(py)
        if self._needs_reshape:
            self._gen_reshape(py)
        if self._needs_iota:
            self._gen_iota(py)
        if self._needs_matmul:
            self._gen_matmul(py)

    def _gen_divide(self, py: bool) -> None:
        self.lines.append('')
        if py:
            self._emit('def _divide(a, b=None):')
            self.indent += 1
            self._emit('"""A+ divide: monadic → reciprocal; dyadic → a/b."""')
            self._emit('if b is None:')
            self.indent += 1
            self._emit('return 1.0 / a')
            self.indent -= 1
            self._emit('return a / b')
            self.indent -= 1
        else:
            self._emit('function _divide(a, b) {')
            self.indent += 1
            self._emit('// A+ divide: monadic → reciprocal; dyadic → a/b')
            self._emit('if (b === undefined) return 1.0 / a;')
            self._emit('return a / b;')
            self.indent -= 1
            self._emit('}')

    def _gen_multiply(self, py: bool) -> None:
        self.lines.append('')
        if py:
            self._emit('def _multiply(a, b=None):')
            self.indent += 1
            self._emit('"""A+ multiply: monadic → sign; dyadic → a*b."""')
            self._emit('import math')
            self._emit('if b is None:')
            self.indent += 1
            self._emit('return (a > 0) - (a < 0)')
            self.indent -= 1
            self._emit('return a * b')
            self.indent -= 1
        else:
            self._emit('function _multiply(a, b) {')
            self.indent += 1
            self._emit('// A+ multiply: monadic → sign; dyadic → a*b')
            self._emit('if (b === undefined) return (a > 0) - (a < 0);')
            self._emit('return a * b;')
            self.indent -= 1
            self._emit('}')

    def _gen_reshape(self, py: bool) -> None:
        self.lines.append('')
        if py:
            self._emit('def _reshape(data, shape):')
            self.indent += 1
            self._emit('"""Reshape flat data into nested lists of given shape."""')
            self._emit('if not isinstance(shape, (list, tuple)):')
            self.indent += 1
            self._emit('shape = [shape]')
            self.indent -= 1
            self._emit('total = 1')
            self._emit('for s in shape:')
            self.indent += 1
            self._emit('total *= s')
            self.indent -= 1
            self._emit('if total != len(data):')
            self.indent += 1
            self._emit('raise ValueError(')
            self.indent += 1
            self._emit('f"Cannot reshape {len(data)} elements into {shape}")')
            self.indent -= 1
            self.indent -= 1
            self._emit('def _rec(d, shp):')
            self.indent += 1
            self._emit('if len(shp) == 1:')
            self.indent += 1
            self._emit('return d[:shp[0]]')
            self.indent -= 1
            self._emit('size = shp[0]')
            self._emit('stride = len(d) // size')
            self._emit('return [_rec(d[i*stride:(i+1)*stride], shp[1:])')
            self._emit('        for i in range(size)]')
            self.indent -= 1
            self._emit('return _rec(list(data), list(shape))')
            self.indent -= 1
        else:
            self._emit('function _reshape(data, shape) {')
            self.indent += 1
            self._emit('// Reshape flat data into nested arrays of given shape')
            self._emit('if (!Array.isArray(shape)) shape = [shape];')
            self._emit('const total = shape.reduce((a, b) => a * b, 1);')
            self._emit('if (total !== data.length) {')
            self.indent += 1
            self._emit('throw new Error(')
            self._emit('  `Cannot reshape ${data.length} elements into [${shape}]`);')
            self.indent -= 1
            self._emit('}')
            self._emit('function rec(d, shp) {')
            self.indent += 1
            self._emit('if (shp.length === 1) return d.slice(0, shp[0]);')
            self._emit('const size = shp[0];')
            self._emit('const stride = Math.floor(d.length / size);')
            self._emit('const result = [];')
            self._emit('for (let i = 0; i < size; i++) {')
            self.indent += 1
            self._emit('result.push(')
            self._emit('  rec(d.slice(i * stride, (i + 1) * stride), shp.slice(1)));')
            self.indent -= 1
            self._emit('}')
            self._emit('return result;')
            self.indent -= 1
            self._emit('}')
            self._emit('return rec(Array.from(data), Array.from(shape));')
            self.indent -= 1
            self._emit('}')

    def _gen_iota(self, py: bool) -> None:
        self.lines.append('')
        if py:
            self._emit('def _iota(n):')
            self.indent += 1
            self._emit('"""Generate 0 .. n-1 (⍳n)."""')
            self._emit('return list(range(int(n)))')
            self.indent -= 1
        else:
            self._emit('function _iota(n) {')
            self.indent += 1
            self._emit('// Generate 0 .. n-1 (iota)')
            self._emit('return Array.from({length: Math.floor(n)}, (_, i) => i);')
            self.indent -= 1
            self._emit('}')

    def _gen_matmul(self, py: bool) -> None:
        self.lines.append('')
        if py:
            self._emit('def _matmul(a, b):')
            self.indent += 1
            self._emit('"""Matrix multiplication for nested lists (+.×)."""')
            self._emit('if not a or not b:')
            self.indent += 1
            self._emit('return []')
            self.indent -= 1
            self._emit('# Vector-vector: dot product')
            self._emit('if not isinstance(a[0], list) and not isinstance(b[0], list):')
            self.indent += 1
            self._emit('return sum(x * y for x, y in zip(a, b))')
            self.indent -= 1
            self._emit('# Matrix-vector')
            self._emit('if isinstance(a[0], list) and not isinstance(b[0], list):')
            self.indent += 1
            self._emit('return [sum(row[j] * b[j] for j in range(len(b)))')
            self._emit('        for row in a]')
            self.indent -= 1
            self._emit('# Vector-matrix')
            self._emit('if not isinstance(a[0], list) and isinstance(b[0], list):')
            self.indent += 1
            self._emit('cols = len(b[0])')
            self._emit('return [sum(a[k] * b[k][j] for k in range(len(a)))')
            self._emit('        for j in range(cols)]')
            self.indent -= 1
            self._emit('# Matrix-matrix')
            self._emit('rows_a, cols_a = len(a), len(a[0])')
            self._emit('rows_b, cols_b = len(b), len(b[0])')
            self._emit('if cols_a != rows_b:')
            self.indent += 1
            self._emit('raise ValueError(')
            self._emit('    f"Shape mismatch: ({rows_a},{cols_a}) x ({rows_b},{cols_b})")')
            self.indent -= 1
            self._emit('result = []')
            self._emit('for i in range(rows_a):')
            self.indent += 1
            self._emit('row = []')
            self._emit('for j in range(cols_b):')
            self.indent += 1
            self._emit('s = 0')
            self._emit('for k in range(cols_a):')
            self.indent += 1
            self._emit('s += a[i][k] * b[k][j]')
            self.indent -= 1
            self._emit('row.append(s)')
            self.indent -= 1
            self._emit('result.append(row)')
            self.indent -= 1
            self._emit('return result')
            self.indent -= 1
        else:
            self._emit('function _matmul(a, b) {')
            self.indent += 1
            self._emit('// Matrix multiplication for arrays (+.×)')
            self._emit('if (!a.length || !b.length) return [];')
            self._emit('// Vector-vector: dot product')
            self._emit('if (!Array.isArray(a[0]) && !Array.isArray(b[0])) {')
            self.indent += 1
            self._emit('let s = 0;')
            self._emit('for (let i = 0; i < a.length; i++) s += a[i] * b[i];')
            self._emit('return s;')
            self.indent -= 1
            self._emit('}')
            self._emit('// Matrix-vector')
            self._emit('if (Array.isArray(a[0]) && !Array.isArray(b[0])) {')
            self.indent += 1
            self._emit('return a.map(row => {')
            self.indent += 1
            self._emit('let s = 0;')
            self._emit('for (let j = 0; j < b.length; j++) s += row[j] * b[j];')
            self._emit('return s;')
            self.indent -= 1
            self._emit('});')
            self.indent -= 1
            self._emit('}')
            self._emit('// Vector-matrix')
            self._emit('if (!Array.isArray(a[0]) && Array.isArray(b[0])) {')
            self.indent += 1
            self._emit('const cols = b[0].length;')
            self._emit('const result = [];')
            self._emit('for (let j = 0; j < cols; j++) {')
            self.indent += 1
            self._emit('let s = 0;')
            self._emit('for (let k = 0; k < a.length; k++) s += a[k] * b[k][j];')
            self._emit('result.push(s);')
            self.indent -= 1
            self._emit('}')
            self._emit('return result;')
            self.indent -= 1
            self._emit('}')
            self._emit('// Matrix-matrix')
            self._emit('const rowsA = a.length, colsA = a[0].length;')
            self._emit('const rowsB = b.length, colsB = b[0].length;')
            self._emit('if (colsA !== rowsB) {')
            self.indent += 1
            self._emit('throw new Error(')
            self._emit('  `Shape mismatch: (${rowsA},${colsA}) x (${rowsB},${colsB})`);')
            self.indent -= 1
            self._emit('}')
            self._emit('const result = [];')
            self._emit('for (let i = 0; i < rowsA; i++) {')
            self.indent += 1
            self._emit('const row = [];')
            self._emit('for (let j = 0; j < colsB; j++) {')
            self.indent += 1
            self._emit('let s = 0;')
            self._emit('for (let k = 0; k < colsA; k++) s += a[i][k] * b[k][j];')
            self._emit('row.push(s);')
            self.indent -= 1
            self._emit('}')
            self._emit('result.push(row);')
            self.indent -= 1
            self._emit('}')
            self._emit('return result;')
            self.indent -= 1
            self._emit('}')


class PythonGenerator(CodeGenBase):
    def generate(self, prog: Program) -> str:
        self.lines = []
        self.indent = 0
        self._needs_divide = False
        self._needs_multiply = False
        self._needs_reshape = False
        self._needs_iota = False
        self._needs_matmul = False

        self._emit('import math')
        for stmt in prog.stmts:
            self._gen_stmt(stmt)

        self._emit_helpers(py=True)
        return '\n'.join(self.lines) + '\n'

    def _gen_stmt(self, stmt: AST) -> None:
        if isinstance(stmt, CommentStmt):
            self._emit(f'# {stmt.text}')
        elif isinstance(stmt, Assignment):
            self._emit(f'{stmt.name} = {self._gen_expr(stmt.expr)}')
        elif isinstance(stmt, PrintStmt):
            self._emit(f'print({self._gen_expr(stmt.expr)})')
        elif isinstance(stmt, IfStmt):
            self._emit(f'if {self._gen_expr(stmt.cond)}:')
            self.indent += 1
            for s in stmt.body:
                self._gen_stmt(s)
            self.indent -= 1
            if stmt.else_body:
                self._emit('else:')
                self.indent += 1
                for s in stmt.else_body:
                    self._gen_stmt(s)
                self.indent -= 1
        elif isinstance(stmt, WhileStmt):
            self._emit(f'while {self._gen_expr(stmt.cond)}:')
            self.indent += 1
            for s in stmt.body:
                self._gen_stmt(s)
            self.indent -= 1
        elif isinstance(stmt, FuncDef):
            params = ', '.join(stmt.params)
            self._emit(f'def {stmt.name}({params}):')
            self.indent += 1
            for s in stmt.body:
                self._gen_stmt(s)
            self.indent -= 1
            self._emit('')
        elif isinstance(stmt, ReturnStmt):
            self._emit(f'return {self._gen_expr(stmt.expr)}')
        else:
            self._emit(self._gen_expr(stmt))

    def _gen_expr(self, node: AST) -> str:
        if isinstance(node, NumberLit):
            return node.value
        if isinstance(node, StringLit):
            return repr(node.value)
        if isinstance(node, Ident):
            return node.name
        if isinstance(node, BinaryOp):
            left = self._gen_expr(node.left)
            right = self._gen_expr(node.right)
            op = node.op
            if op == '\u00D7':
                op = '*'
            elif op == '\u00F7':
                op = '/'
            return f'({left} {op} {right})'
        if isinstance(node, UnaryOp):
            return f'(-{self._gen_expr(node.operand)})'
        if isinstance(node, FuncCall):
            return self._gen_builtin_call(node.name, node.args, self._gen_expr)
        if isinstance(node, IndexAccess):
            arr = self._gen_expr(node.array)
            result = arr
            for idx in node.indices:
                result = f'{result}[int({self._gen_expr(idx)})]'
            return result
        if isinstance(node, InnerProduct):
            self._needs_matmul = True
            return f'_matmul({self._gen_expr(node.left)}, {self._gen_expr(node.right)})'
        if isinstance(node, ArrayLiteral):
            elems = ', '.join(self._gen_expr(e) for e in node.elements)
            return f'[{elems}]'
        raise ValueError(f'Unknown AST node: {type(node).__name__}')


class JavaScriptGenerator(CodeGenBase):
    def generate(self, prog: Program) -> str:
        self.lines = []
        self.indent = 0
        self._needs_divide = False
        self._needs_multiply = False
        self._needs_reshape = False
        self._needs_iota = False
        self._needs_matmul = False

        for stmt in prog.stmts:
            self._gen_stmt(stmt)

        self._emit_helpers(py=False)
        return '\n'.join(self.lines) + '\n'

    def _gen_stmt(self, stmt: AST) -> None:
        if isinstance(stmt, CommentStmt):
            self._emit(f'// {stmt.text}')
        elif isinstance(stmt, Assignment):
            self._emit(f'let {stmt.name} = {self._gen_expr(stmt.expr)};')
        elif isinstance(stmt, PrintStmt):
            self._emit(f'console.log({self._gen_expr(stmt.expr)});')
        elif isinstance(stmt, IfStmt):
            self._emit(f'if ({self._gen_expr(stmt.cond)}) {{')
            self.indent += 1
            for s in stmt.body:
                self._gen_stmt(s)
            self.indent -= 1
            if stmt.else_body:
                self._emit('} else {')
                self.indent += 1
                for s in stmt.else_body:
                    self._gen_stmt(s)
                self.indent -= 1
            self._emit('}')
        elif isinstance(stmt, WhileStmt):
            self._emit(f'while ({self._gen_expr(stmt.cond)}) {{')
            self.indent += 1
            for s in stmt.body:
                self._gen_stmt(s)
            self.indent -= 1
            self._emit('}')
        elif isinstance(stmt, FuncDef):
            params = ', '.join(stmt.params)
            self._emit(f'function {stmt.name}({params}) {{')
            self.indent += 1
            for s in stmt.body:
                self._gen_stmt(s)
            self.indent -= 1
            self._emit('}')
            self._emit('')
        elif isinstance(stmt, ReturnStmt):
            self._emit(f'return {self._gen_expr(stmt.expr)};')
        else:
            self._emit(f'{self._gen_expr(stmt)};')

    def _gen_expr(self, node: AST) -> str:
        if isinstance(node, NumberLit):
            return node.value
        if isinstance(node, StringLit):
            return repr(node.value)
        if isinstance(node, Ident):
            return node.name
        if isinstance(node, BinaryOp):
            left = self._gen_expr(node.left)
            right = self._gen_expr(node.right)
            op = node.op
            if op == '\u00D7':
                op = '*'
            elif op == '\u00F7':
                op = '/'
            return f'({left} {op} {right})'
        if isinstance(node, UnaryOp):
            return f'(-{self._gen_expr(node.operand)})'
        if isinstance(node, FuncCall):
            return self._gen_builtin_call(node.name, node.args, self._gen_expr)
        if isinstance(node, IndexAccess):
            arr = self._gen_expr(node.array)
            result = arr
            for idx in node.indices:
                result = f'{result}[Math.floor({self._gen_expr(idx)})]'
            return result
        if isinstance(node, InnerProduct):
            self._needs_matmul = True
            return f'_matmul({self._gen_expr(node.left)}, {self._gen_expr(node.right)})'
        if isinstance(node, ArrayLiteral):
            elems = ', '.join(self._gen_expr(e) for e in node.elements)
            return f'[{elems}]'
        raise ValueError(f'Unknown AST node: {type(node).__name__}')


class GoGenerator(CodeGenBase):
    """Generate Go code from A+ AST."""

    def generate(self, prog: Program) -> str:
        self.lines = []
        self.indent = 0
        self._needs_divide = False
        self._needs_multiply = False
        self._needs_reshape = False
        self._needs_iota = False
        self._needs_matmul = False

        self._emit('package main')
        self._emit('')
        self._emit('import (')
        self.indent += 1
        self._emit('"fmt"')
        self._emit('"math"')
        self.indent -= 1
        self._emit(')')
        self._emit('')

        self._emit('func main() {')
        self.indent += 1
        for stmt in prog.stmts:
            self._gen_stmt(stmt)
        self.indent -= 1
        self._emit('}')

        self._emit_helpers(py=False)
        return '\n'.join(self.lines) + '\n'

    def _gen_stmt(self, stmt: AST) -> None:
        if isinstance(stmt, CommentStmt):
            self._emit(f'// {stmt.text}')
        elif isinstance(stmt, Assignment):
            self._emit(f'{stmt.name} := {self._gen_expr(stmt.expr)}')
        elif isinstance(stmt, PrintStmt):
            self._emit(f'fmt.Println({self._gen_expr(stmt.expr)})')
        elif isinstance(stmt, IfStmt):
            self._emit(f'if {self._gen_expr(stmt.cond)} {{')
            self.indent += 1
            for s in stmt.body:
                self._gen_stmt(s)
            self.indent -= 1
            if stmt.else_body:
                self._emit('} else {')
                self.indent += 1
                for s in stmt.else_body:
                    self._gen_stmt(s)
                self.indent -= 1
            self._emit('}')
        elif isinstance(stmt, WhileStmt):
            self._emit(f'for {self._gen_expr(stmt.cond)} {{')
            self.indent += 1
            for s in stmt.body:
                self._gen_stmt(s)
            self.indent -= 1
            self._emit('}')
        elif isinstance(stmt, FuncDef):
            params = ', '.join(f'{p} float64' for p in stmt.params)
            self._emit(f'func {stmt.name}({params}) float64 {{')
            self.indent += 1
            for s in stmt.body:
                self._gen_stmt(s)
            self.indent -= 1
            self._emit('}')
            self._emit('')
        elif isinstance(stmt, ReturnStmt):
            self._emit(f'return {self._gen_expr(stmt.expr)}')
        else:
            self._emit(f'_ = {self._gen_expr(stmt)}')

    def _gen_expr(self, node: AST) -> str:
        if isinstance(node, NumberLit):
            return node.value
        if isinstance(node, StringLit):
            return repr(node.value)
        if isinstance(node, Ident):
            return node.name
        if isinstance(node, BinaryOp):
            left = self._gen_expr(node.left)
            right = self._gen_expr(node.right)
            op = node.op
            if op == '\u00D7':
                op = '*'
            elif op == '\u00F7':
                op = '/'
            return f'({left} {op} {right})'
        if isinstance(node, UnaryOp):
            return f'(-{self._gen_expr(node.operand)})'
        if isinstance(node, FuncCall):
            return self._gen_builtin_call(node.name, node.args, self._gen_expr)
        if isinstance(node, IndexAccess):
            arr = self._gen_expr(node.array)
            result = arr
            for idx in node.indices:
                result = f'{result}[int({self._gen_expr(idx)})]'
            return result
        if isinstance(node, InnerProduct):
            self._needs_matmul = True
            return f'_matmul({self._gen_expr(node.left)}, {self._gen_expr(node.right)})'
        if isinstance(node, ArrayLiteral):
            elems = ', '.join(self._gen_expr(e) for e in node.elements)
            return f'[]{elems}'
        raise ValueError(f'Unknown AST node: {type(node).__name__}')

    def _emit_helpers(self, py: bool) -> None:
        if self._needs_divide:
            self._gen_divide_go()
        if self._needs_multiply:
            self._gen_multiply_go()
        if self._needs_reshape:
            self._gen_reshape_go()
        if self._needs_iota:
            self._gen_iota_go()
        if self._needs_matmul:
            self._gen_matmul_go()

    def _gen_divide_go(self) -> None:
        self.lines.append('')
        self._emit('func _divide(a, b float64) float64 {')
        self.indent += 1
        self._emit('if b == 0 { return 1.0 / a }')
        self._emit('return a / b')
        self.indent -= 1
        self._emit('}')

    def _gen_multiply_go(self) -> None:
        self.lines.append('')
        self._emit('func _multiply(a, b float64) float64 {')
        self.indent += 1
        self._emit('if b == 0 { if a > 0 { return 1 }; return -1 }')
        self._emit('return a * b')
        self.indent -= 1
        self._emit('}')

    def _gen_reshape_go(self) -> None:
        pass  # Skipped for Go — rely on runtime

    def _gen_iota_go(self) -> None:
        self.lines.append('')
        self._emit('func _iota(n int) []float64 {')
        self.indent += 1
        self._emit('r := make([]float64, n)')
        self._emit('for i := 0; i < n; i++ { r[i] = float64(i) }')
        self._emit('return r')
        self.indent -= 1
        self._emit('}')

    def _gen_matmul_go(self) -> None:
        pass  # Skipped


class RustGenerator(CodeGenBase):
    """Generate Rust code from A+ AST."""

    def generate(self, prog: Program) -> str:
        self.lines = []
        self.indent = 0
        self._needs_divide = False
        self._needs_multiply = False
        self._needs_reshape = False
        self._needs_iota = False
        self._needs_matmul = False

        self._emit('fn main() {')
        self.indent += 1
        for stmt in prog.stmts:
            self._gen_stmt(stmt)
        self.indent -= 1
        self._emit('}')

        self._emit_helpers(py=False)
        return '\n'.join(self.lines) + '\n'

    def _gen_stmt(self, stmt: AST) -> None:
        if isinstance(stmt, CommentStmt):
            self._emit(f'// {stmt.text}')
        elif isinstance(stmt, Assignment):
            if stmt.name == stmt.name.lower() and '_' not in stmt.name:
                self._emit(f'let mut {stmt.name} = {self._gen_expr(stmt.expr)};')
            else:
                self._emit(f'let {stmt.name} = {self._gen_expr(stmt.expr)};')
        elif isinstance(stmt, PrintStmt):
            self._emit(f'println!(\"{{}}\", {self._gen_expr(stmt.expr)});')
        elif isinstance(stmt, IfStmt):
            self._emit(f'if {self._gen_expr(stmt.cond)} {{')
            self.indent += 1
            for s in stmt.body:
                self._gen_stmt(s)
            self.indent -= 1
            if stmt.else_body:
                self._emit('} else {')
                self.indent += 1
                for s in stmt.else_body:
                    self._gen_stmt(s)
                self.indent -= 1
            self._emit('}')
        elif isinstance(stmt, WhileStmt):
            self._emit(f'while {self._gen_expr(stmt.cond)} {{')
            self.indent += 1
            for s in stmt.body:
                self._gen_stmt(s)
            self.indent -= 1
            self._emit('}')
        elif isinstance(stmt, FuncDef):
            params = ', '.join(f'{p}: f64' for p in stmt.params)
            self._emit(f'fn {stmt.name}({params}) -> f64 {{')
            self.indent += 1
            for s in stmt.body:
                self._gen_stmt(s)
            self.indent -= 1
            self._emit('}')
            self._emit('')
        elif isinstance(stmt, ReturnStmt):
            self._emit(f'return {self._gen_expr(stmt.expr)};')
        else:
            self._emit(f'let _ = {self._gen_expr(stmt)};')

    def _gen_expr(self, node: AST) -> str:
        if isinstance(node, NumberLit):
            return node.value if '.' in node.value else f'{node.value}.0'
        if isinstance(node, StringLit):
            return f'\"{node.value}\"'
        if isinstance(node, Ident):
            return node.name
        if isinstance(node, BinaryOp):
            left = self._gen_expr(node.left)
            right = self._gen_expr(node.right)
            op = node.op
            if op == '\u00D7':
                op = '*'
            elif op == '\u00F7':
                op = '/'
            return f'({left} {op} {right})'
        if isinstance(node, UnaryOp):
            return f'(-{self._gen_expr(node.operand)})'
        if isinstance(node, FuncCall):
            return self._gen_builtin_call(node.name, node.args, self._gen_expr)
        if isinstance(node, IndexAccess):
            arr = self._gen_expr(node.array)
            result = arr
            for idx in node.indices:
                result = f'{result}[{self._gen_expr(idx)} as usize]'
            return result
        if isinstance(node, InnerProduct):
            self._needs_matmul = True
            return f'_matmul({self._gen_expr(node.left)}, {self._gen_expr(node.right)})'
        if isinstance(node, ArrayLiteral):
            elems = ', '.join(self._gen_expr(e) for e in node.elements)
            return f'vec![{elems}]'
        raise ValueError(f'Unknown AST node: {type(node).__name__}')

    def _emit_helpers(self, py: bool) -> None:
        if self._needs_divide:
            self._gen_divide_rust()
        if self._needs_multiply:
            self._gen_multiply_rust()
        if self._needs_iota:
            self._gen_iota_rust()

    def _gen_divide_rust(self) -> None:
        self.lines.append('')
        self._emit('fn _divide(a: f64, b: f64) -> f64 {')
        self.indent += 1
        self._emit('if b == 0.0 { 1.0 / a } else { a / b }')
        self.indent -= 1
        self._emit('}')

    def _gen_multiply_rust(self) -> None:
        self.lines.append('')
        self._emit('fn _multiply(a: f64, b: f64) -> f64 {')
        self.indent += 1
        self._emit('if b == 0.0 { if a > 0.0 { 1.0 } else { -1.0 } } else { a * b }')
        self.indent -= 1
        self._emit('}')

    def _gen_iota_rust(self) -> None:
        self.lines.append('')
        self._emit('fn _iota(n: usize) -> Vec<f64> {')
        self.indent += 1
        self._emit('(0..n).map(|i| i as f64).collect()')
        self.indent -= 1
        self._emit('}')


class CGenerator(CodeGenBase):
    """Generate C code from A+ AST."""

    def generate(self, prog: Program) -> str:
        self.lines = []
        self.indent = 0
        self._needs_divide = False
        self._needs_multiply = False
        self._needs_reshape = False
        self._needs_iota = False
        self._needs_matmul = False

        self._emit('#include <stdio.h>')
        self._emit('#include <math.h>')
        self._emit('')
        self._emit('int main(void) {')
        self.indent += 1
        for stmt in prog.stmts:
            self._gen_stmt(stmt)
        self._emit('return 0;')
        self.indent -= 1
        self._emit('}')

        self._emit_helpers(py=False)
        return '\n'.join(self.lines) + '\n'

    def _gen_stmt(self, stmt: AST) -> None:
        if isinstance(stmt, CommentStmt):
            self._emit(f'/* {stmt.text} */')
        elif isinstance(stmt, Assignment):
            self._emit(f'double {stmt.name} = {self._gen_expr(stmt.expr)};')
        elif isinstance(stmt, PrintStmt):
            self._emit(f'printf(\"%g\\n\", {self._gen_expr(stmt.expr)});')
        elif isinstance(stmt, IfStmt):
            self._emit(f'if ({self._gen_expr(stmt.cond)}) {{')
            self.indent += 1
            for s in stmt.body:
                self._gen_stmt(s)
            self.indent -= 1
            if stmt.else_body:
                self._emit('} else {')
                self.indent += 1
                for s in stmt.else_body:
                    self._gen_stmt(s)
                self.indent -= 1
            self._emit('}')
        elif isinstance(stmt, WhileStmt):
            self._emit(f'while ({self._gen_expr(stmt.cond)}) {{')
            self.indent += 1
            for s in stmt.body:
                self._gen_stmt(s)
            self.indent -= 1
            self._emit('}')
        elif isinstance(stmt, FuncDef):
            params = ', '.join(f'double {p}' for p in stmt.params)
            self._emit(f'double {stmt.name}({params}) {{')
            self.indent += 1
            for s in stmt.body:
                self._gen_stmt(s)
            self.indent -= 1
            self._emit('}')
            self._emit('')
        elif isinstance(stmt, ReturnStmt):
            self._emit(f'return {self._gen_expr(stmt.expr)};')
        else:
            self._emit(f'(void)({self._gen_expr(stmt)});')

    def _gen_expr(self, node: AST) -> str:
        if isinstance(node, NumberLit):
            return node.value if '.' in node.value else f'{node.value}.0'
        if isinstance(node, StringLit):
            return f'\"{node.value}\"'
        if isinstance(node, Ident):
            return node.name
        if isinstance(node, BinaryOp):
            left = self._gen_expr(node.left)
            right = self._gen_expr(node.right)
            op = node.op
            if op == '\u00D7':
                op = '*'
            elif op == '\u00F7':
                op = '/'
            return f'({left} {op} {right})'
        if isinstance(node, UnaryOp):
            return f'(-{self._gen_expr(node.operand)})'
        if isinstance(node, FuncCall):
            return self._gen_builtin_call(node.name, node.args, self._gen_expr)
        if isinstance(node, IndexAccess):
            arr = self._gen_expr(node.array)
            result = arr
            for idx in node.indices:
                result = f'{result}[(int)({self._gen_expr(idx)})]'
            return result
        if isinstance(node, InnerProduct):
            self._needs_matmul = True
            return f'_matmul({self._gen_expr(node.left)}, {self._gen_expr(node.right)})'
        if isinstance(node, ArrayLiteral):
            elems = ', '.join(self._gen_expr(e) for e in node.elements)
            return f'(double[]){{{elems}}}'
        raise ValueError(f'Unknown AST node: {type(node).__name__}')

    def _emit_helpers(self, py: bool) -> None:
        if self._needs_divide:
            self._gen_divide_c()
        if self._needs_multiply:
            self._gen_multiply_c()
        if self._needs_iota:
            self._gen_iota_c()

    def _gen_divide_c(self) -> None:
        self.lines.append('')
        self._emit('double _divide(double a, double b) {')
        self.indent += 1
        self._emit('return b == 0.0 ? 1.0 / a : a / b;')
        self.indent -= 1
        self._emit('}')

    def _gen_multiply_c(self) -> None:
        self.lines.append('')
        self._emit('double _multiply(double a, double b) {')
        self.indent += 1
        self._emit('return b == 0.0 ? (a > 0.0 ? 1.0 : -1.0) : a * b;')
        self.indent -= 1
        self._emit('}')

    def _gen_iota_c(self) -> None:
        pass  # Requires custom array handling in C


# ═══════════════════════════════════════════════════════════════════════
# Constant folding optimization
# ═══════════════════════════════════════════════════════════════════════

def optimize_constant_folding(prog: Program) -> Program:
    """Fold constant binary expressions: 2+3 → 5, 4*5 → 20, etc."""

    def fold(node: AST) -> AST:
        if isinstance(node, BinaryOp):
            node.left = fold(node.left)
            node.right = fold(node.right)
            if isinstance(node.left, NumberLit) and isinstance(node.right, NumberLit):
                try:
                    a = float(node.left.value)
                    b = float(node.right.value)
                    op = node.op
                    if op in ('\u00D7', '*'):
                        result = a * b
                    elif op in ('\u00F7', '/'):
                        result = a / b if b != 0 else float('inf')
                    elif op == '+':
                        result = a + b
                    elif op == '-':
                        result = a - b
                    else:
                        return node
                    return NumberLit(str(int(result) if result == int(result) else result))
                except (ValueError, ZeroDivisionError):
                    return node
        elif isinstance(node, UnaryOp):
            node.operand = fold(node.operand)
            if isinstance(node.operand, NumberLit) and node.op == '-':
                val = -float(node.operand.value)
                return NumberLit(str(int(val) if val == int(val) else val))
        elif isinstance(node, FuncCall):
            node.args = [fold(a) for a in node.args]
        elif isinstance(node, IndexAccess):
            node.array = fold(node.array)
            node.indices = [fold(i) for i in node.indices]
        elif isinstance(node, InnerProduct):
            node.left = fold(node.left)
            node.right = fold(node.right)
        elif isinstance(node, ArrayLiteral):
            node.elements = [fold(e) for e in node.elements]
        elif isinstance(node, Assignment):
            node.expr = fold(node.expr)
        elif isinstance(node, PrintStmt):
            node.expr = fold(node.expr)
        elif isinstance(node, IfStmt):
            node.cond = fold(node.cond)
            node.body = [optimize_constant_folding(Program(node.body)).stmts[0]
                         if len(node.body) == 1 and isinstance(node.body[0], type(node.body[0]))
                         else s for s in node.body]
            node.body = [fold(s) if isinstance(s, (BinaryOp, UnaryOp, FuncCall))
                         else s for s in node.body]
            if node.else_body:
                node.else_body = [fold(s) if isinstance(s, (BinaryOp, UnaryOp, FuncCall))
                                  else s for s in node.else_body]
        elif isinstance(node, WhileStmt):
            node.cond = fold(node.cond)
        elif isinstance(node, ReturnStmt):
            node.expr = fold(node.expr)
        return node

    prog.stmts = [fold(s) if isinstance(s, (BinaryOp, UnaryOp, FuncCall, Assignment,
                                             PrintStmt, IfStmt, WhileStmt, ReturnStmt))
                   else s for s in prog.stmts]
    return prog


# ═══════════════════════════════════════════════════════════════════════
# Source map generation
# ═══════════════════════════════════════════════════════════════════════

class SourceMapGenerator:
    """Generate source maps mapping A+ source lines to generated code lines."""

    def __init__(self):
        self.mappings: list[dict] = []

    def add(self, aplus_line: int, target_line: int, target_col: int = 0) -> None:
        self.mappings.append({
            'aplus_line': aplus_line,
            'target_line': target_line,
            'target_col': target_col,
        })

    def to_json(self) -> str:
        import json as _json
        return _json.dumps({
            'version': 3,
            'sources': ['input.a+'],
            'mappings': self._encode_mappings(),
        })

    def _encode_mappings(self) -> str:
        """Encode mappings in VLQ format (simplified)."""
        if not self.mappings:
            return ''
        parts = []
        prev_tgt = 0
        prev_src = 0
        for m in self.mappings:
            tgt_delta = m['target_line'] - prev_tgt
            src_delta = m['aplus_line'] - prev_src
            parts.append(f'{tgt_delta}A{src_delta}A')
            prev_tgt = m['target_line']
            prev_src = m['aplus_line']
        return ';'.join(parts)


def main() -> None:
    ap = argparse.ArgumentParser(description='A+ to Python / JavaScript / Go / Rust / C transpiler')
    ap.add_argument('--input', '-i', required=True,
                    help='Path to the .a+ source file (KAPL-encoded or plaintext)')
    ap.add_argument('--output-py', default=None,
                    help='Path to write Python output')
    ap.add_argument('--output-js', default=None,
                    help='Path to write JavaScript output')
    ap.add_argument('--output-go', default=None,
                    help='Path to write Go output')
    ap.add_argument('--output-rs', default=None,
                    help='Path to write Rust output')
    ap.add_argument('--output-c', default=None,
                    help='Path to write C output')
    ap.add_argument('--optimize', action='store_true',
                    help='Apply constant folding optimization')
    ap.add_argument('--source-map', default=None,
                    help='Path to write source map JSON')
    args = ap.parse_args()

    # Read and decode KAPL
    with open(args.input, 'rb') as fh:
        raw = fh.read()
    source = decode_kapl(raw)

    # Lex
    tokens = Lexer(source).tokenize()

    # Parse
    try:
        ast = Parser(tokens).parse()
    except ParseError as exc:
        print(f'Parse error: {exc}', file=sys.stderr)
        sys.exit(1)

    # Optimize
    if args.optimize:
        ast = optimize_constant_folding(ast)

    # Generate
    any_output = False

    if args.output_py:
        code = PythonGenerator().generate(ast)
        with open(args.output_py, 'w', encoding='utf-8') as fh:
            fh.write(code)
        print(f'Python     -> {args.output_py}')
        any_output = True

    if args.output_js:
        code = JavaScriptGenerator().generate(ast)
        with open(args.output_js, 'w', encoding='utf-8') as fh:
            fh.write(code)
        print(f'JavaScript -> {args.output_js}')
        any_output = True

    if args.output_go:
        code = GoGenerator().generate(ast)
        with open(args.output_go, 'w', encoding='utf-8') as fh:
            fh.write(code)
        print(f'Go         -> {args.output_go}')
        any_output = True

    if args.output_rs:
        code = RustGenerator().generate(ast)
        with open(args.output_rs, 'w', encoding='utf-8') as fh:
            fh.write(code)
        print(f'Rust       -> {args.output_rs}')
        any_output = True

    if args.output_c:
        code = CGenerator().generate(ast)
        with open(args.output_c, 'w', encoding='utf-8') as fh:
            fh.write(code)
        print(f'C          -> {args.output_c}')
        any_output = True

    if args.source_map:
        smap = SourceMapGenerator()
        smap.to_json()
        with open(args.source_map, 'w', encoding='utf-8') as fh:
            fh.write(smap.to_json())
        print(f'Source map -> {args.source_map}')

    # If no output specified, print all to stdout
    if not any_output:
        print('=== Python ===')
        print(PythonGenerator().generate(ast))
        print('=== JavaScript ===')
        print(JavaScriptGenerator().generate(ast))


if __name__ == '__main__':
    main()

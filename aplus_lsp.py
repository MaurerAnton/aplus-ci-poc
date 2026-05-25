#!/usr/bin/env python3
"""
A+ Language Server Protocol (LSP) Implementation
=================================================
Provides completions, diagnostics, hover, and go-to-definition for .a+ files.
Uses the transpile_aplus.py parser as its parsing backend.

Run: python3 aplus_lsp.py

Protocol: JSON-RPC 2.0 over stdio (stdin/stdout).
"""

import sys
import json
import os
import re
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Import the existing transpiler parser
# ---------------------------------------------------------------------------
# Ensure we can import from the same directory
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from transpile_aplus import (
    Lexer,
    Parser,
    ParseError,
    Token,
    TokenType,
    decode_kapl,
    KAPL_TO_UNICODE,
    _BUILTIN_MAP,
    _KEYWORDS,
)

# ---------------------------------------------------------------------------
# A+ glyph completion table (KAPL token → Unicode + description)
# ---------------------------------------------------------------------------
GLYPH_COMPLETIONS = {
    'assign':   ('←', 'Assign (←)', 'Assign operator'),
    'print':    ('⎕', 'Print (⎕ — Quad)', 'Print / output value'),
    'comment':  ('⍝', 'Comment (⍝ — Lamp)', 'Line comment'),
    'rho':      ('⍴', 'Rho / Reshape (⍴)', 'Reshape or shape-of array'),
    'divide':   ('÷', 'Divide (÷)', 'Element-wise division'),
    'multiply': ('×', 'Multiply (×)', 'Element-wise multiplication'),
    'iota':     ('⍳', 'Iota (⍳)', 'Generate index vector'),
    'ceil':     ('⌈', 'Ceiling (⌈)', 'Round up to nearest integer'),
    'member':   ('∊', 'Member (∊)', 'Membership test'),
    'floor':    ('⌊', 'Floor (⌊)', 'Round down to nearest integer'),
}

# A+ keywords
KEYWORD_COMPLETIONS = [
    ('if', 'if keyword', 'Conditional branching: if (cond) { ... }'),
    ('while', 'while keyword', 'Loop: while (cond) { ... }'),
    ('else', 'else keyword', 'Alternative branch for if'),
]

# Built-in function completions (word forms)
BUILTIN_FUNC_COMPLETIONS = [
    ('divide',   'divide(a, b)',   'Element-wise division: a ÷ b'),
    ('multiply', 'multiply(a, b)', 'Element-wise multiplication: a × b'),
    ('times',    'times(a, b)',    'Alias for multiply'),
    ('rho',      'rho(shape, data)', 'Reshape array or get shape'),
    ('reshape',  'reshape(shape, data)', 'Alias for rho'),
    ('iota',     'iota(n)',        'Generate indices 0..n-1'),
    ('sigmoid',  'sigmoid(x)',     'Sigmoid activation: 1/(1+e^-x)'),
    ('ceil',     'ceil(x)',        'Round up to integer'),
    ('floor',    'floor(x)',       'Round down to integer'),
    ('member',   'member(x, arr)', 'Check if x is in arr'),
    ('inner',    'inner(A, B)',    'Inner product: A +.× B'),
    ('outer',    'outer(A, B)',    'Outer product'),
    ('reduce',   'reduce(op, arr)', 'Reduce array with operator'),
    ('scan',     'scan(op, arr)',  'Scan (prefix reduction)'),
    ('sign',     'sign(x)',        'Sign of x: -1, 0, or 1'),
    ('conjugate','conjugate(x)',   'Complex conjugate'),
    ('shape',    'shape(arr)',     'Get shape of array'),
    ('ravel',    'ravel(arr)',     'Flatten array to vector'),
    ('transpose','transpose(arr)',  'Transpose matrix'),
    ('invert',   'invert(mat)',    'Matrix inverse'),
]

# Detailed hover documentation for built-in functions
BUILTIN_DOCS: dict[str, str] = {
    'divide': (
        "**divide(a, b)** — Element-wise array division.\n\n"
        "Equivalent to APL `a ÷ b`. Divides each element of `a` by the\n"
        "corresponding element of `b`. Supports scalar-array broadcasting."
    ),
    'multiply': (
        "**multiply(a, b)** — Element-wise array multiplication.\n\n"
        "Equivalent to APL `a × b`. Multiplies each element of `a` by the\n"
        "corresponding element of `b`. Supports scalar-array broadcasting."
    ),
    'times': (
        "**times(a, b)** — Alias for multiply.\n\n"
        "Same as `multiply(a, b)` — element-wise multiplication."
    ),
    'rho': (
        "**rho(shape, data)** — Reshape or shape-of.\n\n"
        "Equivalent to APL `⍴`. \n"
        "- Dyadic: `shape ⍴ data` reshapes `data` to dimensions `shape`.\n"
        "- Monadic: `⍴ arr` returns the shape (dimensions) of `arr`."
    ),
    'reshape': (
        "**reshape(shape, data)** — Alias for rho.\n\n"
        "Reshapes `data` to the dimensions given by `shape`."
    ),
    'iota': (
        "**iota(n)** — Generate index vector.\n\n"
        "Equivalent to APL `⍳n`. Returns a vector of integers from 0 to n-1."
    ),
    'sigmoid': (
        "**sigmoid(x)** — Sigmoid activation function.\n\n"
        "Computes `1 / (1 + e^(-x))` element-wise.\n"
        "Commonly used in neural networks as an activation function."
    ),
    'ceil': (
        "**ceil(x)** — Ceiling (round up).\n\n"
        "Equivalent to APL `⌈`. Rounds each element up to the nearest integer."
    ),
    'floor': (
        "**floor(x)** — Floor (round down).\n\n"
        "Equivalent to APL `⌊`. Rounds each element down to the nearest integer."
    ),
    'member': (
        "**member(x, arr)** — Membership test.\n\n"
        "Equivalent to APL `∊`. Returns 1 if `x` is an element of `arr`,\n"
        "0 otherwise."
    ),
    'inner': (
        "**inner(A, B)** — Inner product.\n\n"
        "Equivalent to APL `A +.× B`. Matrix multiplication using sum-of-products."
    ),
    'sign': (
        "**sign(x)** — Sign function.\n\n"
        "Returns -1, 0, or 1 for each element based on its sign."
    ),
    'shape': (
        "**shape(arr)** — Get array dimensions.\n\n"
        "Returns a vector of dimension sizes for `arr`."
    ),
    'reduce': (
        "**reduce(op, arr)** — Reduce array.\n\n"
        "Applies operator `op` between all elements of `arr`. \n"
        "Examples: `reduce(+, arr)` for sum, `reduce(*, arr)` for product."
    ),
    'ravel': (
        "**ravel(arr)** — Flatten array.\n\n"
        "Returns a 1D vector containing all elements of `arr`."
    ),
    'transpose': (
        "**transpose(mat)** — Matrix transpose.\n\n"
        "Flips rows and columns of a 2D matrix."
    ),
}


# ---------------------------------------------------------------------------
# JSON-RPC message framing
# ---------------------------------------------------------------------------

def read_message() -> Optional[dict]:
    """Read a single JSON-RPC message from stdin (Content-Length header framing)."""
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.readline()
        if not line:
            return None  # EOF
        line = line.rstrip('\r\n')
        if line == '':
            break
        if ':' in line:
            key, val = line.split(':', 1)
            headers[key.strip().lower()] = val.strip()
    content_length = int(headers.get('content-length', 0))
    if content_length == 0:
        return None
    body = sys.stdin.read(content_length)
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def send_message(msg: dict) -> None:
    """Send a single JSON-RPC message to stdout with Content-Length framing."""
    body = json.dumps(msg, ensure_ascii=False)
    header = f"Content-Length: {len(body.encode('utf-8'))}\r\n\r\n"
    sys.stdout.write(header + body)
    sys.stdout.flush()


# ---------------------------------------------------------------------------
# Document store and parser helpers
# ---------------------------------------------------------------------------

class Document:
    """In-memory representation of an open A+ document."""
    __slots__ = ('uri', 'version', 'text', 'diagnostics', 'tokens', 'ast')

    def __init__(self, uri: str, text: str, version: int = 0):
        self.uri = uri
        self.version = version
        self.text = text
        self.diagnostics: list[dict] = []
        self.tokens: list[Token] = []
        self.ast: Any = None

    def parse(self) -> None:
        """Parse the document and populate tokens, ast, and diagnostics."""
        self.diagnostics = []
        self.tokens = []
        self.ast = None

        # Decode source if path ends with .a+ (could be KAPL-encoded)
        source = self.text

        # Lex
        try:
            lexer = Lexer(source)
            self.tokens = lexer.tokenize()
        except Exception as exc:
            self.diagnostics.append(_make_diag(
                1, 1, 1, 1,
                f"Lexer error: {exc}",
                severity=1,  # Error
            ))
            return

        # Parse
        try:
            parser = Parser(self.tokens)
            self.ast = parser.parse()
        except ParseError as exc:
            self.diagnostics.append(_make_diag(
                exc.token.line, exc.token.col,
                exc.token.line, exc.token.col + len(exc.token.value),
                str(exc),
                severity=1,  # Error
            ))
        except Exception as exc:
            self.diagnostics.append(_make_diag(
                1, 1, 1, 1,
                f"Parse error: {exc}",
                severity=1,
            ))


def _make_diag(line_start: int, col_start: int,
               line_end: int, col_end: int,
               message: str, severity: int = 1) -> dict:
    """Create an LSP Diagnostic object."""
    return {
        "range": {
            "start": {"line": line_start - 1, "character": col_start - 1},
            "end":   {"line": line_end - 1,   "character": col_end - 1},
        },
        "severity": severity,
        "source": "aplus-lsp",
        "message": message,
    }


# ---------------------------------------------------------------------------
# A+ Language Server
# ---------------------------------------------------------------------------

class APlusServer:
    """Main LSP server for A+ language."""

    def __init__(self):
        self._docs: dict[str, Document] = {}  # uri -> Document
        self._pending_requests: dict[int, str] = {}  # id -> method name

    # -- document management ------------------------------------------------

    def _get_doc(self, uri: str) -> Optional[Document]:
        return self._docs.get(uri)

    def _open_doc(self, uri: str, text: str, version: int) -> Document:
        doc = Document(uri, text, version)
        doc.parse()
        self._docs[uri] = doc
        return doc

    def _update_doc(self, uri: str, changes: list[dict], version: int) -> Optional[Document]:
        """Apply textDocument/didChange to a document."""
        doc = self._docs.get(uri)
        if doc is None:
            return None
        # Full-text sync: replace entire content
        for change in changes:
            if 'text' in change:
                doc.text = change['text']
        doc.version = version
        doc.parse()
        return doc

    # -- entry point -------------------------------------------------------

    def handle_message(self, msg: dict) -> None:
        """Dispatch an incoming JSON-RPC message."""
        method = msg.get('method', '')
        params = msg.get('params', {})
        msg_id = msg.get('id')

        if method == 'initialize':
            self._handle_initialize(msg_id, params)
        elif method == 'initialized':
            pass  # No-op; server is ready
        elif method == 'shutdown':
            self._handle_shutdown(msg_id)
        elif method == 'exit':
            self._handle_exit()
        elif method == 'textDocument/didOpen':
            self._handle_did_open(params)
        elif method == 'textDocument/didChange':
            self._handle_did_change(params)
        elif method == 'textDocument/didClose':
            self._handle_did_close(params)
        elif method == 'textDocument/completion':
            self._handle_completion(msg_id, params)
        elif method == 'textDocument/hover':
            self._handle_hover(msg_id, params)
        elif method == 'textDocument/definition':
            self._handle_definition(msg_id, params)
        elif method == 'textDocument/diagnostic':
            self._handle_diagnostic(msg_id, params)
        elif method and method.startswith('$/') or method and method.startswith('window/'):
            pass  # Notification — ignore

    # -- handlers ----------------------------------------------------------

    def _handle_initialize(self, msg_id: Any, params: dict) -> None:
        result = {
            "capabilities": {
                "textDocumentSync": 1,  # Full sync
                "completionProvider": {
                    "triggerCharacters": ["."],
                },
                "hoverProvider": True,
                "definitionProvider": True,
                "diagnosticProvider": {
                    "interFileDependencies": False,
                    "workspaceDiagnostics": False,
                },
            },
            "serverInfo": {
                "name": "aplus-lsp",
                "version": "1.0.0",
            },
        }
        send_message({"jsonrpc": "2.0", "id": msg_id, "result": result})

    def _handle_shutdown(self, msg_id: Any) -> None:
        send_message({"jsonrpc": "2.0", "id": msg_id, "result": None})

    def _handle_exit(self) -> None:
        sys.exit(0)

    def _handle_did_open(self, params: dict) -> None:
        td = params.get('textDocument', {})
        uri = td.get('uri', '')
        text = td.get('text', '')
        version = td.get('version', 0)
        doc = self._open_doc(uri, text, version)
        self._publish_diagnostics(uri, doc.diagnostics)

    def _handle_did_change(self, params: dict) -> None:
        td = params.get('textDocument', {})
        uri = td.get('uri', '')
        version = td.get('version', 0)
        changes = params.get('contentChanges', [])
        doc = self._update_doc(uri, changes, version)
        if doc:
            self._publish_diagnostics(uri, doc.diagnostics)

    def _handle_did_close(self, params: dict) -> None:
        td = params.get('textDocument', {})
        uri = td.get('uri', '')
        self._docs.pop(uri, None)

    def _handle_completion(self, msg_id: Any, params: dict) -> None:
        td = params.get('textDocument', {})
        uri = td.get('uri', '')
        position = params.get('position', {})
        line = position.get('line', 0)
        char = position.get('character', 0)

        doc = self._get_doc(uri)
        items = self._get_completions(doc, line, char)
        send_message({"jsonrpc": "2.0", "id": msg_id, "result": items})

    def _handle_hover(self, msg_id: Any, params: dict) -> None:
        td = params.get('textDocument', {})
        uri = td.get('uri', '')
        position = params.get('position', {})
        line = position.get('line', 0)
        char = position.get('character', 0)

        doc = self._get_doc(uri)
        hover = self._get_hover(doc, line, char)
        send_message({"jsonrpc": "2.0", "id": msg_id, "result": hover})

    def _handle_definition(self, msg_id: Any, params: dict) -> None:
        td = params.get('textDocument', {})
        uri = td.get('uri', '')
        position = params.get('position', {})
        line = position.get('line', 0)
        char = position.get('character', 0)

        doc = self._get_doc(uri)
        definition = self._get_definition(doc, line, char)
        send_message({"jsonrpc": "2.0", "id": msg_id, "result": definition})

    def _handle_diagnostic(self, msg_id: Any, params: dict) -> None:
        td = params.get('textDocument', {})
        uri = td.get('uri', '')
        doc = self._get_doc(uri)
        if doc:
            items = [{
                "uri": uri,
                "diagnostics": doc.diagnostics,
            }]
            send_message({"jsonrpc": "2.0", "id": msg_id, "result": {"items": items}})
        else:
            send_message({"jsonrpc": "2.0", "id": msg_id, "result": {"items": []}})

    def _publish_diagnostics(self, uri: str, diagnostics: list[dict]) -> None:
        send_message({
            "jsonrpc": "2.0",
            "method": "textDocument/publishDiagnostics",
            "params": {
                "uri": uri,
                "diagnostics": diagnostics,
            },
        })

    # -- completions -------------------------------------------------------

    def _get_completions(self, doc: Optional[Document], line: int, char: int) -> list[dict]:
        """Generate completion items."""
        items: list[dict] = []

        # 1. KAPL glyph completions (with Unicode replacements)
        for glyph_key, (unicode_char, label, detail) in GLYPH_COMPLETIONS.items():
            # TextEdit to insert the Unicode glyph
            items.append({
                "label": label,
                "kind": 1,  # Text
                "detail": detail,
                "insertText": unicode_char,
                "documentation": {
                    "kind": "markdown",
                    "value": f"Insert A+ glyph: `{unicode_char}` — {detail}",
                },
            })

        # 2. A+ keywords
        for kw, label, detail in KEYWORD_COMPLETIONS:
            items.append({
                "label": label,
                "kind": 14,  # Keyword
                "detail": detail,
                "insertText": kw,
            })

        # 3. Built-in functions
        for name, label, detail in BUILTIN_FUNC_COMPLETIONS:
            items.append({
                "label": label,
                "kind": 3,  # Function
                "detail": detail,
                "insertText": name,
            })

        return items

    # -- hover -------------------------------------------------------------

    def _get_hover(self, doc: Optional[Document], line: int, char: int) -> Optional[dict]:
        """Provide hover documentation for the word at the given position."""
        if doc is None:
            return None

        word = self._word_at_position(doc.text, line, char)
        if word is None:
            return None

        # Check built-in docs first
        doc_text = BUILTIN_DOCS.get(word.lower())
        if doc_text:
            return {
                "contents": {
                    "kind": "markdown",
                    "value": doc_text,
                },
                "range": self._word_range(doc.text, line, char),
            }

        # Check KAPL glyph docs
        for glyph_key, (unicode_char, label, detail) in GLYPH_COMPLETIONS.items():
            if word == unicode_char or word == glyph_key:
                return {
                    "contents": {
                        "kind": "markdown",
                        "value": f"**{label}** — {detail}\n\nUnicode: `{unicode_char}`",
                    },
                }

        return None

    # -- go-to-definition --------------------------------------------------

    def _get_definition(self, doc: Optional[Document], line: int, char: int) -> Optional[list[dict]]:
        """Find the definition of the identifier at the given position."""
        if doc is None:
            return None

        word = self._word_at_position(doc.text, line, char)
        if word is None:
            return None

        # Search for function definition:  name { params } :
        # or inline:   name { params } : expression
        text = doc.text

        # Pattern: identifier, optional whitespace, {, params, }, optional whitespace, :
        pattern = re.compile(
            r'^(\s*)'                           # leading whitespace (optional)
            + re.escape(word)
            + r'\s*\{[^}]*\}\s*:',
            re.MULTILINE,
        )

        match = pattern.search(text)
        if match:
            line_num = text[:match.start()].count('\n')
            # Find the column of the identifier
            line_start = text.rfind('\n', 0, match.start()) + 1
            col_num = match.start() - line_start
            return [{
                "uri": doc.uri,
                "range": {
                    "start": {"line": line_num, "character": col_num},
                    "end":   {"line": line_num, "character": col_num + len(word)},
                },
            }]

        # Also search for assignment:  IDENT ← expr
        pattern2 = re.compile(
            r'^(\s*)' + re.escape(word) + r'\s*\u2190',
            re.MULTILINE,
        )
        match2 = pattern2.search(text)
        if match2:
            line_num = text[:match2.start()].count('\n')
            line_start = text.rfind('\n', 0, match2.start()) + 1
            col_num = match2.start() - line_start
            return [{
                "uri": doc.uri,
                "range": {
                    "start": {"line": line_num, "character": col_num},
                    "end":   {"line": line_num, "character": col_num + len(word)},
                },
            }]

        return None

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _word_at_position(text: str, line: int, char: int) -> Optional[str]:
        """Extract the word at the given 0-indexed line/char position."""
        lines = text.split('\n')
        if line >= len(lines):
            return None
        target_line = lines[line]
        if char >= len(target_line):
            return None

        ch = target_line[char]

        # Handle single KAPL/Unicode glyph characters (←, ⍴, ÷, etc.)
        if not ch.isalnum() and ch != '_' and ch != ' ':
            return ch

        # Find word boundaries for alphanumeric identifiers
        start = char
        while start > 0 and (target_line[start - 1].isalnum() or target_line[start - 1] == '_'):
            start -= 1
        end = char
        while end < len(target_line) and (target_line[end].isalnum() or target_line[end] == '_'):
            end += 1

        word = target_line[start:end]
        return word if word else None

    @staticmethod
    def _word_range(text: str, line: int, char: int) -> dict:
        """Get the LSP range for the word at the given position."""
        lines = text.split('\n')
        if line >= len(lines):
            return {"start": {"line": line, "character": char},
                    "end":   {"line": line, "character": char}}
        target_line = lines[line]
        if char >= len(target_line):
            return {"start": {"line": line, "character": char},
                    "end":   {"line": line, "character": char}}

        ch = target_line[char]

        # Handle single KAPL/Unicode glyph characters
        if not ch.isalnum() and ch != '_' and ch != ' ':
            return {
                "start": {"line": line, "character": char},
                "end":   {"line": line, "character": char + 1},
            }

        start = char
        while start > 0 and (target_line[start - 1].isalnum() or target_line[start - 1] == '_'):
            start -= 1
        end = char
        while end < len(target_line) and (target_line[end].isalnum() or target_line[end] == '_'):
            end += 1
        return {
            "start": {"line": line, "character": start},
            "end":   {"line": line, "character": end},
        }


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> None:
    server = APlusServer()

    while True:
        msg = read_message()
        if msg is None:
            break
        server.handle_message(msg)


if __name__ == '__main__':
    main()

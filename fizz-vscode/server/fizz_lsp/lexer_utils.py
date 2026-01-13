from __future__ import annotations

import re
from typing import Optional

from antlr4 import InputStream

from .fizz_parser.FizzLexer import FizzLexer


_FRONTMATTER_RE = re.compile(r"^(\s*)---[^\n]*\n([\s\S]*?)---[^\n]*\n", re.MULTILINE)


def frontmatter_line_count(text: str) -> int:
    """Return number of lines occupied by YAML frontmatter block, if present.

    This matches the frontmatter extraction in `fizz_lsp.parse`.
    """
    m = _FRONTMATTER_RE.search(text)
    if not m:
        return 0
    return len(m.group(0).splitlines())


def token_name(lexer: FizzLexer, token) -> Optional[str]:
    if token is None:
        return None
    if not hasattr(token, "type"):
        return None
    if 0 <= token.type < len(lexer.symbolicNames):
        return lexer.symbolicNames[token.type]
    return None


def lex(text: str) -> tuple[FizzLexer, list]:
    """Return (lexer, tokens) for the full document text."""
    stream = InputStream(text)
    lexer = FizzLexer(stream)
    tokens = lexer.getAllTokens()
    return lexer, tokens


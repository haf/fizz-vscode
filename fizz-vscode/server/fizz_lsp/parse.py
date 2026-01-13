from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from antlr4 import CommonTokenStream, InputStream
from antlr4.error.ErrorListener import ErrorListener

from .fizz_parser.FizzLexer import FizzLexer
from .fizz_parser.FizzParser import FizzParser


@dataclass(frozen=True)
class ParseError:
    line: int  # 1-based
    column: int  # 0-based (ANTLR convention)
    message: str


class CollectingErrorListener(ErrorListener):
    def __init__(self) -> None:
        super().__init__()
        self.errors: List[ParseError] = []

    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):  # noqa: N802
        self.errors.append(ParseError(line=line, column=column, message=str(msg)))


_YAML_FRONTMATTER_RE = re.compile(r"^(\s*)---[^\n]*\n([\s\S]*?)---[^\n]*\n", re.MULTILINE)


def extract_yaml_frontmatter(text: str) -> Tuple[str, str, str]:
    """Return (initial_indent, yaml_frontmatter, remainder).

    Mirrors behavior of `vendor/fizzbee/parser/parser.py` so line numbers match.
    """
    m = _YAML_FRONTMATTER_RE.search(text)
    if not m:
        return "", "", text
    initial_text = m.group(1)
    yaml_frontmatter = m.group(2)
    remaining_text = text[m.end() :]
    return initial_text, yaml_frontmatter, remaining_text


@dataclass(frozen=True)
class ParsedDocument:
    content_for_parser: str
    frontmatter_yaml: str
    frontmatter_line_count: int
    errors: List[ParseError]
    tree: Optional[object]


def parse_text(text: str) -> ParsedDocument:
    initial_spaces, yaml_frontmatter, remainder = extract_yaml_frontmatter(text)

    if initial_spaces == "" and yaml_frontmatter == "":
        pad_lines = 0
    else:
        # initial_spaces may contain newlines (rare, but keep behavior aligned with upstream)
        pad_lines = len(initial_spaces.splitlines()) + len(yaml_frontmatter.splitlines()) + 2

    # Pad with blank lines so ANTLR line numbers match the original file.
    content_for_parser = ("\n" * pad_lines) + remainder
    frontmatter_yaml = ("\n" * len(initial_spaces.splitlines())) + yaml_frontmatter

    stream = InputStream(content_for_parser)
    lexer = FizzLexer(stream)
    tokens = CommonTokenStream(lexer)
    parser = FizzParser(tokens)

    error_listener = CollectingErrorListener()
    parser.removeErrorListeners()
    parser.addErrorListener(error_listener)

    try:
        tree = parser.root()
    except Exception as e:
        # ANTLR can throw on hard failures; capture a synthetic error if none exists.
        if not error_listener.errors:
            error_listener.errors.append(ParseError(line=1, column=0, message=str(e)))
        tree = None

    return ParsedDocument(
        content_for_parser=content_for_parser,
        frontmatter_yaml=frontmatter_yaml,
        frontmatter_line_count=pad_lines,
        errors=error_listener.errors,
        tree=tree,
    )


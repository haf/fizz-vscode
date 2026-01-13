from __future__ import annotations

from typing import Optional

from lsprotocol.types import Position, Range, SymbolKind

from .analysis.indexer import Index, Span, Symbol
from .positions import codepoint_index_to_utf16_units, utf16_units_to_codepoint_index


def span_to_range(text: str, span: Span) -> Range:
    lines = text.splitlines()
    s_line0 = max(0, span.start_line - 1)
    e_line0 = max(0, span.end_line - 1)
    s_line_text = lines[s_line0] if s_line0 < len(lines) else ""
    e_line_text = lines[e_line0] if e_line0 < len(lines) else ""

    s_char = codepoint_index_to_utf16_units(s_line_text, span.start_col)
    e_char = codepoint_index_to_utf16_units(e_line_text, span.end_col)

    return Range(
        start=Position(line=s_line0, character=s_char),
        end=Position(line=e_line0, character=e_char),
    )


def symbol_kind(sym: Symbol) -> SymbolKind:
    if sym.kind == "role":
        return SymbolKind.Class
    if sym.container is not None:
        return SymbolKind.Method
    if sym.kind in ("action", "function", "assertion"):
        return SymbolKind.Function
    return SymbolKind.Variable


def role_at_position(idx: Index, line1: int, col_codepoint: int) -> Optional[str]:
    for role_name, span in idx.role_blocks.items():
        if line1 < span.start_line or line1 > span.end_line:
            continue
        if line1 == span.start_line and col_codepoint < span.start_col:
            continue
        if line1 == span.end_line and col_codepoint > span.end_col:
            continue
        return role_name
    return None


def identifier_at(line_text: str, utf16_character: int) -> str:
    col = utf16_units_to_codepoint_index(line_text, utf16_character)
    if col > len(line_text):
        col = len(line_text)

    def is_ident(ch: str) -> bool:
        return ch == "_" or ch.isalnum()

    l = col
    while l > 0 and is_ident(line_text[l - 1]):
        l -= 1
    r = col
    while r < len(line_text) and is_ident(line_text[r]):
        r += 1
    return line_text[l:r]


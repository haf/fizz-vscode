from __future__ import annotations

from typing import Optional

from lsprotocol.types import Hover, MarkupContent, MarkupKind, Position

from ..analysis.indexer import Index
from ..lsp_utils import identifier_at, role_at_position, span_to_range
from ..positions import utf16_units_to_codepoint_index


def hover_for_position(text: str, idx: Index, position: Position) -> Optional[Hover]:
    line0 = position.line
    char0 = position.character
    lines = text.splitlines()
    line_text = lines[line0] if 0 <= line0 < len(lines) else ""
    ident = identifier_at(line_text, char0)
    if not ident:
        return None

    candidates = idx.by_name.get(ident, [])
    if not candidates:
        return None

    col_codepoint = utf16_units_to_codepoint_index(line_text, char0)
    role = role_at_position(idx, line0 + 1, col_codepoint)
    sym = idx.role_methods.get((role, ident)) if role else None
    if sym is None and len(candidates) == 1:
        sym = candidates[0]
    if sym is None:
        return None

    detail = f"{sym.kind} {sym.name}"
    if sym.container:
        detail = f"{sym.container}.{sym.name} ({sym.kind})"

    return Hover(
        contents=MarkupContent(kind=MarkupKind.Markdown, value=f"```fizz\n{detail}\n```"),
        range=span_to_range(text, sym.span),
    )


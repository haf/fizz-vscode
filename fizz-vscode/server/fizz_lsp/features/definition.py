from __future__ import annotations

from typing import Dict, Optional

from lsprotocol.types import Location, Position

from ..analysis.indexer import Index
from ..analysis.type_env import callsite_at
from ..lsp_utils import identifier_at, role_at_position, span_to_range
from ..positions import utf16_units_to_codepoint_index


def definition_locations(
    *, text: str, idx: Index, type_env: Optional[Dict[str, str]], uri: str, position: Position
) -> Optional[list[Location]]:
    line0 = position.line
    char0 = position.character
    lines = text.splitlines()
    line_text = lines[line0] if 0 <= line0 < len(lines) else ""
    ident = identifier_at(line_text, char0)
    if not ident:
        return None

    col_codepoint = utf16_units_to_codepoint_index(line_text, char0)
    role = role_at_position(idx, line0 + 1, col_codepoint)

    call = callsite_at(idx, line0 + 1, col_codepoint)
    if call is not None and call.callee == ident:
        # Resolve method calls like `rm.Prepare()`.
        if call.receiver == "self" and role is not None:
            sym = idx.role_methods.get((role, ident))
            if sym is not None:
                return [Location(uri=uri, range=span_to_range(text, sym.span))]
        elif call.receiver and type_env:
            recv_type = type_env.get(call.receiver)
            if recv_type:
                sym = idx.role_methods.get((recv_type, ident))
                if sym is not None:
                    return [Location(uri=uri, range=span_to_range(text, sym.span))]

    if role is not None:
        sym = idx.role_methods.get((role, ident))
        if sym is not None:
            return [Location(uri=uri, range=span_to_range(text, sym.span))]

    candidates = idx.by_name.get(ident, [])
    if len(candidates) == 1:
        sym = candidates[0]
        return [Location(uri=uri, range=span_to_range(text, sym.span))]

    return None


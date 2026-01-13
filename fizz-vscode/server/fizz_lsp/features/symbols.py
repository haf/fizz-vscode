from __future__ import annotations

from typing import Dict, List

from lsprotocol.types import DocumentSymbol

from ..analysis.indexer import Index, Symbol
from ..lsp_utils import span_to_range, symbol_kind


def document_symbols_for(text: str, idx: Index) -> list[DocumentSymbol]:
    by_role: Dict[str, list[Symbol]] = {}
    top_level: list[Symbol] = []
    role_syms: list[Symbol] = []

    for s in idx.symbols:
        if s.kind == "role":
            role_syms.append(s)
            continue
        if s.container:
            by_role.setdefault(s.container, []).append(s)
        else:
            top_level.append(s)

    symbols: list[DocumentSymbol] = []

    for role_sym in sorted(role_syms, key=lambda x: (x.span.start_line, x.span.start_col)):
        children = [
            DocumentSymbol(
                name=child.name,
                kind=symbol_kind(child),
                range=span_to_range(text, child.span),
                selection_range=span_to_range(text, child.span),
            )
            for child in sorted(by_role.get(role_sym.name, []), key=lambda x: (x.span.start_line, x.span.start_col))
        ]
        role_range = idx.role_blocks.get(role_sym.name, role_sym.span)
        symbols.append(
            DocumentSymbol(
                name=role_sym.name,
                kind=symbol_kind(role_sym),
                range=span_to_range(text, role_range),
                selection_range=span_to_range(text, role_sym.span),
                children=children or None,
            )
        )

    for s in sorted(top_level, key=lambda x: (x.span.start_line, x.span.start_col)):
        symbols.append(
            DocumentSymbol(
                name=s.name,
                kind=symbol_kind(s),
                range=span_to_range(text, s.span),
                selection_range=span_to_range(text, s.span),
            )
        )

    return symbols


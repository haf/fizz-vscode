from __future__ import annotations

from lsprotocol.types import CompletionItem, CompletionItemKind

from ..analysis.indexer import Index
from ..lsp_utils import role_at_position
from ..positions import utf16_units_to_codepoint_index


KEYWORD_COMPLETIONS = [
    "action",
    "func",
    "init",
    "role",
    "symmetric",
    "atomic",
    "serial",
    "parallel",
    "oneof",
    "any",
    "exists",
    "fair",
    "require",
    "invariants",
    "always",
    "eventually",
    "assertion",
    "transition",
    "compose",
    "refine",
]


def completion_items_for_position(text: str, idx: Index, line0: int, char0_utf16: int) -> list[CompletionItem]:
    lines = text.splitlines()
    line_text = lines[line0] if 0 <= line0 < len(lines) else ""
    col_cp = utf16_units_to_codepoint_index(line_text, char0_utf16)
    prefix = line_text[:col_cp]

    items: list[CompletionItem] = []

    # Member completions after self.
    if prefix.endswith("self."):
        role = role_at_position(idx, line0 + 1, col_cp)
        if role:
            members = [s for s in idx.symbols if s.container == role and s.kind in ("action", "function")]
            for m in sorted(members, key=lambda s: s.name):
                items.append(
                    CompletionItem(
                        label=m.name,
                        kind=CompletionItemKind.Method if m.container else CompletionItemKind.Function,
                        detail=f"{m.kind} {m.name}",
                    )
                )
            return items

    # Fallback: keywords + known top-level symbols.
    for kw in KEYWORD_COMPLETIONS:
        items.append(CompletionItem(label=kw, kind=CompletionItemKind.Keyword))

    for s in sorted((s for s in idx.symbols if s.container is None), key=lambda s: s.name):
        kind = CompletionItemKind.Class if s.kind == "role" else CompletionItemKind.Function
        items.append(CompletionItem(label=s.name, kind=kind, detail=s.kind))

    return items


from __future__ import annotations


def codepoint_index_to_utf16_units(s: str, codepoint_index: int) -> int:
    """Convert a Python codepoint index into an LSP UTF-16 code unit index.

    LSP positions are measured in UTF-16 code units. Python string indexing is
    Unicode codepoints. For BMP-only strings these match; for astral codepoints
    they differ.
    """
    if codepoint_index <= 0:
        return 0
    prefix = s[:codepoint_index]
    return len(prefix.encode("utf-16-le")) // 2


def utf16_unit_length(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2


def utf16_units_to_codepoint_index(s: str, utf16_units: int) -> int:
    """Convert an LSP UTF-16 code unit offset to a Python codepoint index."""
    if utf16_units <= 0:
        return 0
    seen = 0
    for i, ch in enumerate(s):
        seen += utf16_unit_length(ch)
        if seen > utf16_units:
            return i
        if seen == utf16_units:
            return i + 1
    return len(s)


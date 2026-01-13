from __future__ import annotations

import re
from typing import Optional

from lsprotocol.types import Position, Range, TextEdit, WorkspaceEdit

from ..lexer_utils import frontmatter_line_count, lex, token_name
from ..positions import codepoint_index_to_utf16_units, utf16_units_to_codepoint_index


def is_valid_identifier(name: str) -> bool:
    return re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is not None


def name_token_at_position(text: str, line0: int, char0_utf16: int):
    """Return lexer token for the NAME under cursor, or None."""
    lines = text.splitlines()
    line_text = lines[line0] if 0 <= line0 < len(lines) else ""
    col_cp = utf16_units_to_codepoint_index(line_text, char0_utf16)
    line1 = line0 + 1

    fm_lines = frontmatter_line_count(text)
    lexer, tokens = lex(text)

    for tok in tokens:
        if tok.line is None:
            continue
        if fm_lines and tok.line <= fm_lines:
            continue
        if tok.line != line1:
            continue
        if tok.text is None:
            continue
        if token_name(lexer, tok) != "NAME":
            continue
        start = tok.column
        end = tok.column + len(tok.text)
        if start <= col_cp < end:
            return tok
    return None


def rename_edits_for_document(text: str, old: str, new: str) -> list[TextEdit]:
    """Compute file-local rename edits for NAME tokens, skipping frontmatter."""
    if not is_valid_identifier(new):
        return []
    if old in ("self",):
        return []

    fm_lines = frontmatter_line_count(text)
    lexer, tokens = lex(text)
    lines = text.splitlines()

    edits: list[TextEdit] = []
    for tok in tokens:
        if tok.line is None or tok.text is None:
            continue
        if fm_lines and tok.line <= fm_lines:
            continue
        if token_name(lexer, tok) != "NAME":
            continue
        if tok.text != old:
            continue
        line0 = tok.line - 1
        if not (0 <= line0 < len(lines)):
            continue
        line_text = lines[line0]
        start_char = codepoint_index_to_utf16_units(line_text, tok.column)
        end_char = codepoint_index_to_utf16_units(line_text, tok.column + len(tok.text))
        edits.append(
            TextEdit(
                range=Range(
                    start=Position(line=line0, character=start_char),
                    end=Position(line=line0, character=end_char),
                ),
                new_text=new,
            )
        )
    return edits


def prepare_rename_range(text: str, line0: int, char0_utf16: int) -> Optional[Range]:
    tok = name_token_at_position(text, line0, char0_utf16)
    if tok is None or tok.text is None:
        return None
    if tok.text in ("self",):
        return None
    lines = text.splitlines()
    line0_tok = tok.line - 1
    line_text = lines[line0_tok] if 0 <= line0_tok < len(lines) else ""
    start_char = codepoint_index_to_utf16_units(line_text, tok.column)
    end_char = codepoint_index_to_utf16_units(line_text, tok.column + len(tok.text))
    return Range(
        start=Position(line=line0_tok, character=start_char),
        end=Position(line=line0_tok, character=end_char),
    )


def workspace_edit_for_rename(
    text: str, uri: str, line0: int, char0_utf16: int, new_name: str
) -> Optional[WorkspaceEdit]:
    tok = name_token_at_position(text, line0, char0_utf16)
    if tok is None or tok.text is None:
        return None
    old = tok.text
    edits = rename_edits_for_document(text, old, new_name)
    if not edits:
        return None
    return WorkspaceEdit(changes={uri: edits})

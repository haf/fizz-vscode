from __future__ import annotations

from fizz_lsp.features.rename import rename_edits_for_document


def _apply_edits(text: str, edits) -> str:
    # Apply edits in reverse document order (line, char) to keep offsets stable.
    lines = text.splitlines(keepends=True)

    def pos_key(e):
        return (e.range.start.line, e.range.start.character)

    for e in sorted(edits, key=pos_key, reverse=True):
        line = e.range.start.line
        start = e.range.start.character
        end = e.range.end.character
        # This test file uses ASCII only, so UTF-16 == codepoint offsets.
        s = lines[line]
        lines[line] = s[:start] + e.new_text + s[end:]
    return "".join(lines)


def test_rename_replaces_name_tokens_only() -> None:
    text = "\n".join(
        [
            "init:",
            "  a = 0",
            "  b = a + 1",
            '  s = "a should not change"',
            "  # a comment mentioning a should not change",
            "",
            "atomic action Add:",
            "  a = a + 1",
            "",
        ]
    )
    edits = rename_edits_for_document(text, "a", "count")
    out = _apply_edits(text, edits)
    assert "a = 0" not in out
    assert "count = 0" in out
    assert "b = count + 1" in out
    assert '"a should not change"' in out
    assert "# a comment mentioning a should not change" in out


def test_rename_rejects_invalid_identifier() -> None:
    text = "init:\n  a = 0\n"
    assert rename_edits_for_document(text, "a", "not valid") == []

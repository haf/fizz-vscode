from __future__ import annotations

from fizz_lsp.lexer_utils import frontmatter_line_count
from fizz_lsp.parse import parse_text
from fizz_lsp.server import _name_token_at_position


def test_frontmatter_line_count_matches_parse_padding() -> None:
    text = (
        "---\n"
        "title: x\n"
        "tags: [a, b]\n"
        "---\n"
        "\n"
        "init:\n"
        "  a = 0\n"
    )
    parsed = parse_text(text)
    assert frontmatter_line_count(text) == parsed.frontmatter_line_count


def test_name_token_at_position_skips_frontmatter() -> None:
    text = (
        "---\n"
        "title: x\n"
        "---\n"
        "\n"
        "init:\n"
        "  a = 0\n"
    )
    # Cursor on 'title' in frontmatter should yield no NAME token for rename.
    tok = _name_token_at_position(text, line0=1, char0_utf16=1)
    assert tok is None


def test_name_token_at_position_finds_identifier() -> None:
    text = "init:\n  a = 0\n  b = a + 1\n"
    # line0=1 => "  a = 0"; position on 'a'
    tok = _name_token_at_position(text, line0=1, char0_utf16=2)
    assert tok is not None
    assert tok.text == "a"


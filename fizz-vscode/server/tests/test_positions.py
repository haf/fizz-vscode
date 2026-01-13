from __future__ import annotations

from fizz_lsp.positions import (
    codepoint_index_to_utf16_units,
    utf16_unit_length,
    utf16_units_to_codepoint_index,
)


def test_utf16_mapping_handles_astral_codepoints() -> None:
    # 😀 is U+1F600 => 2 UTF-16 code units
    s = "a😀b"
    assert utf16_unit_length(s) == 4  # a(1) + 😀(2) + b(1)
    assert codepoint_index_to_utf16_units(s, 0) == 0
    assert codepoint_index_to_utf16_units(s, 1) == 1  # after 'a'
    assert codepoint_index_to_utf16_units(s, 2) == 3  # after 'a😀'
    assert codepoint_index_to_utf16_units(s, 3) == 4  # after 'a😀b'
    assert utf16_units_to_codepoint_index(s, 0) == 0
    assert utf16_units_to_codepoint_index(s, 1) == 1
    assert (
        utf16_units_to_codepoint_index(s, 2) == 1
    )  # in the middle of the surrogate pair => points at 😀
    assert utf16_units_to_codepoint_index(s, 3) == 2
    assert utf16_units_to_codepoint_index(s, 4) == 3

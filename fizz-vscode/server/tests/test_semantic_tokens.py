from __future__ import annotations

from pathlib import Path

from fizz_lsp.analysis.indexer import build_index
from fizz_lsp.parse import parse_text
from fizz_lsp.server import (
    _SEMANTIC_TOKEN_TYPES,
    _encode_semantic_tokens,
    _semantic_token_type,
)


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for p in [here] + list(here.parents):
        if (p / "vendor" / "fizzbee").is_dir():
            return p
    raise AssertionError("could not locate repo root containing vendor/fizzbee")


def _decode(data: list[int]) -> list[tuple[int, int, int, int]]:
    """Decode LSP semantic tokens delta encoding.

    Returns (line0, startCharUtf16, length, tokenTypeIdx).
    """
    out = []
    line = 0
    start = 0
    for i in range(0, len(data), 5):
        dl, ds, length, ttype, _mods = data[i : i + 5]
        line += dl
        start = start + ds if dl == 0 else ds
        out.append((line, start, length, ttype))
    return out


def test_semantic_tokens_cover_indexed_symbols() -> None:
    root = _repo_root()
    f = (
        root
        / "vendor"
        / "fizzbee"
        / "examples"
        / "tutorials"
        / "49-roles"
        / "SimpleRoles.fizz"
    )
    text = f.read_text("utf-8")
    parsed = parse_text(text)
    assert parsed.errors == []
    assert parsed.tree is not None

    idx = build_index(parsed.tree)
    expected = [s for s in idx.symbols if _semantic_token_type(s) is not None]

    data = _encode_semantic_tokens(text, idx.symbols, idx.calls)
    decoded = _decode(data)

    # We now include lexical semantic tokens too, so this is a lower bound.
    assert len(decoded) >= len(expected) + len(idx.calls)
    # sanity: sorted order
    assert decoded == sorted(decoded)


def test_semantic_tokens_include_keywords() -> None:
    text = "init:\n  a = 0\n\natomic action Add:\n  a = a + 1\n"
    parsed = parse_text(text)
    assert parsed.errors == []
    assert parsed.tree is not None
    idx = build_index(parsed.tree)

    data = _encode_semantic_tokens(text, idx.symbols, idx.calls)
    decoded = _decode(data)
    keyword_idx = _SEMANTIC_TOKEN_TYPES.index("keyword")
    assert any(t[3] == keyword_idx for t in decoded)

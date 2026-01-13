from __future__ import annotations

from pathlib import Path

from fizz_lsp.analysis.indexer import build_index
from fizz_lsp.parse import parse_text
from fizz_lsp.server import _completion_for_position


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for p in [here] + list(here.parents):
        if (p / "vendor" / "fizzbee").is_dir():
            return p
    raise AssertionError("could not locate repo root containing vendor/fizzbee")


def test_self_member_completion_inside_role() -> None:
    root = _repo_root()
    f = root / "vendor" / "fizzbee" / "examples" / "tutorials" / "49-roles" / "SimpleRoles.fizz"
    text = f.read_text("utf-8")
    parsed = parse_text(text)
    assert parsed.errors == []
    assert parsed.tree is not None
    idx = build_index(parsed.tree)

    lines = text.splitlines()
    target_line0 = next(i for i, l in enumerate(lines) if "self.state" in l)
    line = lines[target_line0]
    # cursor right after "self."
    char0 = line.index("self.") + len("self.")
    items = _completion_for_position(text, idx, target_line0, char0)
    labels = {i.label for i in items}

    assert "Abort" in labels
    assert "Commit" in labels
    assert "Write" in labels


def test_keyword_completion_always_present() -> None:
    text = "init:\n  a = 0\n"
    parsed = parse_text(text)
    assert parsed.errors == []
    assert parsed.tree is not None
    idx = build_index(parsed.tree)

    items = _completion_for_position(text, idx, 0, 0)
    labels = {i.label for i in items}
    assert "action" in labels
    assert "role" in labels


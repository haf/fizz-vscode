from __future__ import annotations

from pathlib import Path

from fizz_lsp.analysis.indexer import build_index
from fizz_lsp.parse import parse_text
from fizz_lsp.server import _build_type_env


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for p in [here] + list(here.parents):
        if (p / "vendor" / "fizzbee").is_dir():
            return p
    raise AssertionError("could not locate repo root containing vendor/fizzbee")


def test_inferrs_loop_var_role_type_from_append_pattern() -> None:
    root = _repo_root()
    f = root / "vendor" / "fizzbee" / "examples" / "tutorials" / "49-roles" / "SimpleRoles.fizz"
    text = f.read_text("utf-8")
    parsed = parse_text(text)
    assert parsed.errors == []
    assert parsed.tree is not None
    idx = build_index(parsed.tree)

    env = _build_type_env(text, idx)
    # In the example, `participants.append(p)` where `p = Participant()` and then `for rm in participants:`
    assert env.get("rm") == "Participant"


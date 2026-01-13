from __future__ import annotations

from pathlib import Path

from fizz_lsp.analysis.indexer import build_index
from fizz_lsp.parse import parse_text


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for p in [here] + list(here.parents):
        if (p / "vendor" / "fizzbee").is_dir():
            return p
    raise AssertionError("could not locate repo root containing vendor/fizzbee")


def test_indexes_roles_and_role_methods() -> None:
    root = _repo_root()
    f = root / "vendor" / "fizzbee" / "examples" / "tutorials" / "49-roles" / "SimpleRoles.fizz"
    text = f.read_text("utf-8")
    parsed = parse_text(text)
    assert parsed.errors == []
    assert parsed.tree is not None

    idx = build_index(parsed.tree)

    roles = {s.name for s in idx.symbols if s.kind == "role"}
    assert "Coordinator" in roles
    assert "Participant" in roles

    # Methods/actions inside roles
    coordinator_members = {(s.container, s.kind, s.name) for s in idx.symbols if s.container == "Coordinator"}
    assert ("Coordinator", "action", "Write") in coordinator_members
    assert ("Coordinator", "function", "Abort") in coordinator_members
    assert ("Coordinator", "function", "Commit") in coordinator_members

    participant_members = {(s.container, s.kind, s.name) for s in idx.symbols if s.container == "Participant"}
    assert ("Participant", "function", "Prepare") in participant_members


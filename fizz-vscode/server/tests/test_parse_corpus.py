from __future__ import annotations

import glob
from pathlib import Path

from fizz_lsp.parse import parse_text


def _find_examples_dir() -> Path | None:
    here = Path(__file__).resolve()
    for p in [here] + list(here.parents):
        cand = p / "vendor" / "fizzbee" / "examples"
        if cand.is_dir():
            return cand
    return None


def test_parses_all_example_specs() -> None:
    examples_dir = _find_examples_dir()
    assert examples_dir is not None, "could not find vendor/fizzbee/examples directory"

    fizz_files = sorted(
        Path(p).resolve()
        for p in glob.glob(str(examples_dir / "**" / "*.fizz"), recursive=True)
    )
    assert fizz_files, "expected at least one .fizz example"

    for f in fizz_files:
        text = f.read_text("utf-8")
        parsed = parse_text(text)
        assert parsed.tree is not None, f"{f}: parse tree missing"
        assert parsed.errors == [], f"{f}: unexpected parse errors: {parsed.errors}"


def test_frontmatter_padding_keeps_line_numbers_stable() -> None:
    # Includes unicode in YAML and code to ensure we don't crash while parsing.
    text = (
        "---\n"
        'title: "🍰"\n'
        "tags: [a, b]\n"
        "---\n"
        "\n"
        "init:\n"
        "  a = 0\n"
        "\n"
        "action Add:\n"
        "  atomic:\n"
        "    a = a + 1\n"
    )
    parsed = parse_text(text)
    assert parsed.tree is not None
    assert parsed.errors == []
    # sanity: we did pad at least the frontmatter header/footer lines
    assert parsed.frontmatter_line_count >= 4

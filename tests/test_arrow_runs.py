"""No arrow turns a corner and then arrives with almost no line.

An orthogonal arrow that turns just before a box is all head: it reads as a blot
on the corner. Every family keeps a straight run into the box after the last
turn (`drawspec.routing.arrow_run` asks for the head and as much shaft again);
`tools/arrows.py` measures what was drawn, and every reference is held to it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from arrows import RATIO, short_arrows

from drawspec import render
from drawspec.routing import arrow_run
from drawspec.theme import load_theme

REFERENCE = Path(__file__).resolve().parents[1] / "docs" / "reference"
REFERENCES = sorted(REFERENCE.glob("*.json"))


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_no_reference_arrow_is_all_head(path: Path) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    assert [str(arrow) for arrow in short_arrows(render(document))] == []


@pytest.mark.parametrize(
    "name", ["neuralnet-residual-block", "neuralnet-transformer-encoder", "neuralnet-inception"]
)
def test_a_skip_or_a_branch_arrives_with_its_full_run(name: str) -> None:
    """The figures the owner reported: a shaft as long as the head, at least."""
    document = json.loads((REFERENCE / f"{name}.json").read_text(encoding="utf-8"))
    assert short_arrows(render(document), ratio=2.0) == []


def test_the_run_is_a_head_and_as_much_shaft_again() -> None:
    theme = load_theme()
    head = theme.head_length_for("flow")
    assert arrow_run(theme, "flow") == pytest.approx(2 * head + theme.edge.clearance)


def test_the_checker_finds_a_blot() -> None:
    """A route that turns one head's length before the box is reported; two is not."""
    head = '<polygon points="100,50 92,46 92,54" fill="currentColor"/>'

    def drawing(turn: float) -> str:
        line = f'<path d="M 0 0 L {100 - turn} 0 L {100 - turn} 50 L 100 50" stroke="black"/>'
        return f'<svg xmlns="http://www.w3.org/2000/svg">{line}{head}</svg>'

    assert len(short_arrows(drawing(9.0))) == 1
    assert short_arrows(drawing(8.0 * RATIO + 1)) == []

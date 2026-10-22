"""`sunburst` — a hierarchy as concentric rings of sectors, read from the middle out.

The kind's promises: every terminal node takes an equal slice of the circle and a
parent spans its own, clockwise from twelve; the rings are at most three; no label
is ever upside down; and a label that cannot be made to fit its sector at the floor
size is refused rather than drawn illegibly. The hub is optional and is not a ring.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from drawspec import render
from drawspec.errors import FitError
from drawspec.kinds.sunburst import SunburstDrawing, sunburst_drawing
from drawspec.schema import SUNBURST_NODE_MAX, parse_document, validate_document
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])
REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "reference"
REFERENCES = sorted(REFERENCE.glob("sunburst-*.json"))


def wheel(**extra: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "version": 1,
        "kind": "sunburst",
        "centre": "How I feel",
        "nodes": [
            {
                "text": "Angry",
                "children": [
                    {"text": "Hurt", "children": [{"text": "Let down"}, {"text": "Numb"}]},
                    {"text": "Mad", "children": [{"text": "Furious"}]},
                ],
            },
            {
                "text": "Happy",
                "children": [
                    {"text": "Proud", "children": [{"text": "Valued"}]},
                    {"text": "Playful"},
                ],
            },
        ],
    }
    document.update(extra)
    return document


def drawn(document: dict[str, Any]) -> SunburstDrawing:
    return sunburst_drawing(parse_document(document), THEME, MEASURER)


def pointers(document: dict[str, Any]) -> list[str]:
    return [violation.pointer for violation in validate_document(document)]


def messages(document: dict[str, Any]) -> str:
    return "\n".join(violation.message for violation in validate_document(document))


def normalise(degrees: float) -> float:
    """A rotation folded into (-180, 180]."""
    return (degrees + 180.0) % 360.0 - 180.0


# -- the references -----------------------------------------------------------


def test_there_is_at_least_one_reference_wheel() -> None:
    assert REFERENCES


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_every_reference_renders_and_validates(path: Path) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    assert validate_document(document) == ()
    assert render(document).startswith("<svg")


# -- the angles ---------------------------------------------------------------


def test_sunburst_leaves_get_equal_angles() -> None:
    """Every terminal node takes the same slice: 360 over the number of leaves."""
    drawing = drawn(wheel())
    leaves = [segment for segment in drawing.segments if segment.leaf]
    spans = [segment.end - segment.start for segment in leaves]
    expected = 360.0 / len(leaves)
    assert spans == pytest.approx([expected] * len(leaves))


def test_sunburst_parent_span_is_sum_of_children() -> None:
    """A parent spans exactly its leaves — so it spans the sum of its children."""
    drawing = drawn(wheel())
    slice_angle = 360.0 / sum(1 for segment in drawing.segments if segment.leaf)
    for segment in drawing.segments:
        assert segment.end - segment.start == pytest.approx(segment.weight * slice_angle)


# -- the labels ---------------------------------------------------------------


def test_sunburst_labels_are_never_upside_down() -> None:
    """Every label, left half or right, is readable without turning the page over."""
    drawing = drawn(wheel())
    assert drawing.segments
    for segment in drawing.segments:
        assert abs(normalise(segment.rotate)) <= 90.0 + 1e-6


def test_sunburst_optional_centre_hub_renders_and_is_not_a_ring() -> None:
    """The hub is drawn, holds its words, and does not count as one of the rings."""
    with_hub = drawn(wheel())
    without = drawn(wheel(centre=""))
    assert with_hub.hub > 0
    assert without.hub == 0
    # The same tree makes the same number of rings whether or not there is a hub.
    assert with_hub.rings == without.rings == 3
    assert render(wheel()).count("How I feel") == 1


def test_sunburst_label_too_long_to_fit_raises_fiterror() -> None:
    # Three rings squeezed onto a tiny canvas leave no band wide enough for a word.
    with pytest.raises(FitError):
        drawn(wheel(width=140))


# -- the refusals -------------------------------------------------------------


def test_sunburst_depth_over_three_rings_raises_documenterror() -> None:
    too_deep = wheel(
        nodes=[
            {
                "text": "a",
                "children": [
                    {"text": "b", "children": [{"text": "c", "children": [{"text": "d"}]}]}
                ],
            },
            {"text": "e"},
        ]
    )
    assert any(pointer.endswith("children") for pointer in pointers(too_deep))
    assert "three rings" in messages(too_deep) or "fourth ring" in messages(too_deep)


def test_sunburst_rejects_coordinate_and_weight_fields() -> None:
    for field in ("angle", "weight", "size", "value", "amount", "x", "y"):
        document = wheel(nodes=[{"text": "a", field: 1}, {"text": "b"}])
        assert validate_document(document), f"{field} should be refused"


def test_sunburst_deeply_nested_input_is_refused_not_a_recursionerror() -> None:
    # `sunburst-node` is self-referential; validate_document must not recurse into
    # a RecursionError on pathologically deep input (it serves MCP/agent input).
    deep: dict[str, Any] = {"text": "a"}
    cursor = deep
    for _ in range(3000):
        child: dict[str, Any] = {"text": "x"}
        cursor["children"] = [child]
        cursor = child
    document = wheel(nodes=[deep])
    found = validate_document(document)
    assert found and any("fourth ring" in message for message in messages(document).splitlines())


def test_sunburst_refuses_more_than_the_node_budget() -> None:
    many = [{"text": f"n{i}"} for i in range(SUNBURST_NODE_MAX + 1)]
    # Spread them under two roots so the first-ring cap is not what trips.
    document = wheel(
        nodes=[
            {"text": "left", "children": many[: len(many) // 2]},
            {"text": "right", "children": many[len(many) // 2 :]},
        ]
    )
    assert any("in all" in message for message in messages(document).splitlines())

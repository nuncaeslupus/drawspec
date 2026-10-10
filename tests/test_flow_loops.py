"""Causal loop diagrams on `flow`: `polarity`, `delay` and named `loops`.

A loop's type is arithmetic, not drawing: an even number of negative links
reinforces, an odd number balances. So the type is derived and drawn as R or B,
and an author who states the wrong one is refused at the pointer with the count.
The marker is placed, not written: it is asserted to lie inside the figure its
loop's routes close (or beside the loop's first link) and clear of every box,
label and line. Signs are written as edge labels, so they are placed like labels.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

from drawspec import render
from drawspec.errors import FitError
from drawspec.kinds.graph import graph_drawing
from drawspec.kinds.loops import CausalDrawing, causal_drawing, loop_kind
from drawspec.schema import parse_document, validate_document
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
SO = load_theme({"version": 1, "flow": {"polarity": "so"}})
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])
REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "reference"
REFERENCES = sorted(REFERENCE.glob("flow-loops-*.json"))


def waiting(**extra: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "version": 1,
        "kind": "flow",
        "nodes": [
            {"id": "wait", "text": "Time on the waiting list"},
            {"id": "acute", "text": "Emergency admissions"},
            {"id": "beds", "text": "Beds free for planned surgery"},
            {"id": "private", "text": "Patients who go private"},
        ],
        "edges": [
            {"from": "wait", "to": "acute", "polarity": "+", "delay": True},
            {"from": "acute", "to": "beds", "polarity": "-"},
            {"from": "beds", "to": "wait", "polarity": "-"},
            {"from": "wait", "to": "private", "polarity": "+"},
            {"from": "private", "to": "wait", "polarity": "-"},
        ],
        "loops": [
            {"text": "Deterioration", "nodes": ["wait", "acute", "beds"]},
            {"text": "Exit to private care", "nodes": ["wait", "private"]},
        ],
    }
    document.update(extra)
    return document


def drawn(document: dict[str, Any], theme: Any = THEME) -> tuple[Any, CausalDrawing]:
    parsed = parse_document(document)
    drawing = graph_drawing(parsed, theme, MEASURER)
    return drawing, causal_drawing(parsed, drawing, theme, MEASURER)


def pointers(document: dict[str, Any]) -> list[str]:
    return [violation.pointer for violation in validate_document(document)]


def messages(document: dict[str, Any]) -> str:
    return "\n".join(violation.message for violation in validate_document(document))


def gap(one: tuple[float, ...], other: tuple[float, ...]) -> float:
    dx = max(other[0] - one[2], one[0] - other[2], 0.0)
    dy = max(other[1] - one[3], one[1] - other[3], 0.0)
    return math.hypot(dx, dy)


def contains(polygon: tuple[tuple[float, float], ...], x: float, y: float) -> bool:
    inside = False
    for (x0, y0), (x1, y1) in zip(polygon, [*polygon[1:], polygon[0]], strict=True):
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            inside = not inside
    return inside


def assert_markers_clear(drawing: Any, causal: CausalDrawing) -> None:
    """No marker touches a box, a label, a line or another marker."""
    rects = [(b.x, b.y, b.x + b.width, b.y + b.height) for b in drawing.boxes.values()]
    rects += [label.box for label in drawing.labels]
    for route in drawing.routes:
        for (x0, y0), (x1, y1) in route.segments:
            rects.append((min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))
    for index, marker in enumerate(causal.markers):
        for part in marker.footprint:
            assert all(gap(part, rect) > 0 for rect in rects), marker.name
            for other in causal.markers[index + 1 :]:
                assert all(gap(part, theirs) > 0 for theirs in other.footprint)


# ---------------------------------------------------------------------------
# Parity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("signs", "expected"),
    [
        (["+", "+", "+"], "reinforcing"),
        (["+", "-", "-"], "reinforcing"),
        (["+", "+", "-"], "balancing"),
        (["-", "-", "-"], "balancing"),
    ],
)
def test_the_type_is_the_parity_of_negative_links(signs: list[str], expected: str) -> None:
    document = waiting()
    for edge, sign in zip(document["edges"][:3], signs, strict=True):
        edge["polarity"] = sign
    parsed = parse_document(document)
    assert loop_kind(parsed, parsed.loops[0]) == expected


def test_markers_are_numbered_by_derived_type() -> None:
    _, causal = drawn(waiting())
    assert [marker.name for marker in causal.markers] == ["R1", "B1"]
    assert [marker.kind for marker in causal.markers] == ["reinforcing", "balancing"]


def test_a_wrong_type_is_refused_with_the_count() -> None:
    document = waiting()
    document["loops"][0]["type"] = "balancing"
    assert pointers(document) == ["/loops/0/type"]
    assert "has 2 negative links, so it is reinforcing" in messages(document)


def test_a_stated_type_that_agrees_is_accepted() -> None:
    document = waiting()
    document["loops"][0]["type"] = "reinforcing"
    document["loops"][1]["type"] = "balancing"
    assert validate_document(document) == ()


# ---------------------------------------------------------------------------
# Placement
# ---------------------------------------------------------------------------


def test_there_are_at_least_three_references() -> None:
    assert len(REFERENCES) >= 3


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_every_reference_marker_is_inside_its_loop_and_clear(path: Path) -> None:
    document = json.loads(path.read_text())
    assert render(document).startswith("<svg")
    theme = load_theme(document.get("theme") or None)
    drawing, causal = drawn(document, theme)
    assert len(causal.markers) == len(document["loops"])
    for marker in causal.markers:
        assert marker.inside, marker.name
        assert contains(marker.polygon, marker.cx, marker.cy)
    assert_markers_clear(drawing, causal)


def test_the_ring_turns_the_way_the_loop_runs() -> None:
    _, causal = drawn(waiting())
    for marker in causal.markers:
        area = sum(
            x0 * y1 - x1 * y0
            for (x0, y0), (x1, y1) in zip(
                marker.polygon, [*marker.polygon[1:], marker.polygon[0]], strict=True
            )
        )
        assert marker.clockwise == (area > 0)


def test_a_delay_is_two_strokes_on_its_edges_shaft() -> None:
    drawing, causal = drawn(waiting())
    ((delay,),) = [causal.delays]
    route = next(r for r in drawing.routes if (r.source, r.target) == ("wait", "acute"))
    on_shaft = any(
        min(x0, x1) - 1e-6 <= delay.x <= max(x0, x1) + 1e-6
        and min(y0, y1) - 1e-6 <= delay.y <= max(y0, y1) + 1e-6
        for (x0, y0), (x1, y1) in route.segments
    )
    assert on_shaft
    for label in drawing.labels:
        assert gap((delay.x - 4, delay.y - 4, delay.x + 4, delay.y + 4), label.box) > 0


def test_signs_are_written_as_labels_in_the_themes_glyphs() -> None:
    drawing, _ = drawn(waiting())
    assert sorted(label.text for label in drawing.labels) == [
        "+",
        "+",
        "\u2212",
        "\u2212",
        "\u2212",
    ]
    drawing, _ = drawn(waiting(), SO)
    assert sorted(label.text for label in drawing.labels) == ["o", "o", "o", "s", "s"]


def test_a_sign_goes_before_a_label() -> None:
    document = waiting()
    document["edges"][3]["label"] = "after a year"
    drawing, _ = drawn(document)
    assert "+ after a year" in [label.text for label in drawing.labels]


def test_a_marker_with_no_room_is_a_fit_error_naming_the_loop() -> None:
    document = waiting()
    document["loops"][1]["text"] = "Exit" * 40
    with pytest.raises(FitError, match="loop B1"):
        drawn(document)


def test_groups_are_allowed_with_loops() -> None:
    document = waiting(
        groups=[{"id": "hospital", "text": "The hospital", "members": ["acute", "beds"]}]
    )
    assert validate_document(document) == ()
    drawing, causal = drawn(document)
    assert len(causal.markers) == 2
    assert_markers_clear(drawing, causal)


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def test_the_example_is_valid() -> None:
    assert validate_document(waiting()) == ()


def test_a_half_signed_diagram_is_refused_at_the_unsigned_edge() -> None:
    document = waiting()
    del document["edges"][2]["polarity"]
    assert "/edges/2" in pointers(document)
    assert "half-signed" in messages(document)


def test_a_sign_on_an_edge_with_no_causal_direction_is_refused() -> None:
    document = waiting()
    document["edges"][4]["role"] = "link"
    assert pointers(document) == ["/edges/4/polarity"]


def test_a_delay_without_a_sign_is_refused() -> None:
    document = waiting(loops=[])
    for edge in document["edges"]:
        del edge["polarity"]
    assert pointers(document) == ["/edges/0/delay"]


def test_loops_without_signs_are_refused() -> None:
    document = waiting()
    for edge in document["edges"]:
        edge.pop("polarity")
        edge.pop("delay", None)
    assert pointers(document) == ["/loops"]


def test_a_loop_whose_nodes_are_not_joined_in_order_names_the_missing_edge() -> None:
    document = waiting()
    document["loops"][0]["nodes"] = ["wait", "beds", "acute"]
    assert pointers(document)[0] == "/loops/0/nodes/0"
    assert "no edge runs wait → beds" in messages(document)


def test_a_loop_naming_a_node_twice_is_refused() -> None:
    document = waiting()
    document["loops"][0]["nodes"] = ["wait", "acute", "wait"]
    assert pointers(document) == ["/loops/0/nodes/2"]


def test_a_one_node_loop_is_refused() -> None:
    document = waiting()
    document["loops"][0]["nodes"] = ["wait"]
    assert pointers(document) == ["/loops/0/nodes"]


def test_an_unknown_node_is_refused_with_a_suggestion() -> None:
    document = waiting()
    document["loops"][0]["nodes"][1] = "acut"
    assert "/loops/0/nodes/1" in pointers(document)
    assert "did you mean 'acute'" in messages(document)


def test_the_same_loop_twice_is_refused() -> None:
    document = waiting()
    document["loops"].append({"text": "Again", "nodes": ["acute", "beds", "wait"]})
    assert pointers(document) == ["/loops/2/nodes"]


def test_more_than_six_loops_is_past_the_budget() -> None:
    document = waiting()
    document["loops"] = [dict(document["loops"][1], text=f"Loop {n}") for n in range(7)]
    assert "/loops/6" in pointers(document)


@pytest.mark.parametrize("kind", ["tree", "lanes"])
def test_polarity_on_another_kind_is_refused(kind: str) -> None:
    document = waiting(kind=kind, loops=[])
    document["edges"] = [{"from": "wait", "to": "acute", "polarity": "+"}]
    document["nodes"] = document["nodes"][:2]
    if kind == "lanes":
        for node in document["nodes"]:
            node["actor"] = "A clerk"
    assert "/edges/0/polarity" in pointers(document)


def test_loops_on_another_kind_are_refused() -> None:
    document = waiting(kind="tree")
    assert "/loops" in pointers(document)


def test_an_unknown_polarity_word_in_the_theme_is_refused() -> None:
    with pytest.raises(Exception, match=r"\[flow\] polarity"):
        load_theme({"version": 1, "flow": {"polarity": "pm"}})

"""`venn` with four sets — four congruent ellipses, all fifteen regions.

Four circles cannot draw the two diagonal pairs, so four sets are ellipses. The
promise is the same as for circles and asserted the same way, point by point:
every corner of every region's words is inside each ellipse the region is in and
outside each it is not; set names cross no outline; every one of the fifteen
regions exists; and the four-set rules — short region text, five sets refused —
are asserted by the pointer of the refusal.
"""

from __future__ import annotations

import itertools
import json
import math
from pathlib import Path
from typing import Any

import pytest

from drawspec import render
from drawspec.kinds.venn import ELLIPSES, VennDrawing, inside_four, venn_drawing
from drawspec.scene import Path as ScenePath
from drawspec.scene import Polygon
from drawspec.schema import parse_document, validate_document
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])
REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "reference"
REFERENCES = sorted(REFERENCE.glob("venn-four-*.json"))
IDS = ["a", "b", "c", "d"]


def four(**extra: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "version": 1,
        "kind": "venn",
        "sets": [{"id": key, "text": f"Survey {key.upper()}"} for key in IDS],
        "regions": [
            {"in": list(members), "text": str(10 + index)}
            for index, members in enumerate(
                combo for size in range(1, 5) for combo in itertools.combinations(IDS, size)
            )
        ],
    }
    document.update(extra)
    return document


def drawn(document: dict[str, Any]) -> VennDrawing:
    return venn_drawing(parse_document(document), THEME, MEASURER)


def pointers(document: dict[str, Any]) -> list[str]:
    return [violation.pointer for violation in validate_document(document)]


def messages(document: dict[str, Any]) -> str:
    return "\n".join(violation.message for violation in validate_document(document))


def in_ellipse(ellipse: tuple[float, float, float, float, float], x: float, y: float) -> float:
    """The ellipse's implicit value at the point: below one inside, above outside."""
    cx, cy, rx, ry, angle = ellipse
    c, s = math.cos(angle), math.sin(angle)
    u, v = (x - cx) * c + (y - cy) * s, -(x - cx) * s + (y - cy) * c
    return (u / rx) ** 2 + (v / ry) ** 2


def corners(rect: tuple[float, float, float, float]) -> list[tuple[float, float]]:
    left, top, right, bottom = rect
    return [(left, top), (right, top), (right, bottom), (left, bottom)]


def edge_points(rect: tuple[float, float, float, float]) -> list[tuple[float, float]]:
    """Points every two units round the rectangle's sides."""
    left, top = rect[0], rect[1]
    found: list[tuple[float, float]] = []
    for (x0, y0), (x1, y1) in itertools.pairwise([*corners(rect), (left, top)]):
        steps = max(1, math.ceil(math.hypot(x1 - x0, y1 - y0) / 2))
        found += [(x0 + (x1 - x0) * k / steps, y0 + (y1 - y0) * k / steps) for k in range(steps)]
    return found


def assert_inside_its_region(drawing: VennDrawing, ids: list[str]) -> None:
    for membership, rect in drawing.regions:
        for identifier, ellipse in zip(ids, drawing.ellipses, strict=True):
            if identifier in membership:
                # Convex: every corner inside means the whole block is.
                assert all(in_ellipse(ellipse, x, y) < 1 for x, y in corners(rect))
            else:
                assert all(in_ellipse(ellipse, x, y) > 1 for x, y in edge_points(rect))


# ---------------------------------------------------------------------------
# The geometry
# ---------------------------------------------------------------------------


def test_all_fifteen_regions_exist() -> None:
    """The reason for ellipses: every membership has somewhere to be."""
    points = [(i * 0.02, j * 0.02) for i in range(-65, 66) for j in range(-50, 51)]
    for mask in itertools.product((False, True), repeat=4):
        if any(mask):
            assert any(inside_four(mask, x, y) for x, y in points), mask
    assert len(ELLIPSES) == 4


def test_the_ellipses_are_congruent() -> None:
    drawing = drawn(four())
    assert len({(round(rx, 6), round(ry, 6)) for _, _, rx, ry, _ in drawing.ellipses}) == 1
    outlines = [p for p in drawing.scene.primitives if isinstance(p, ScenePath) and p.closed]
    assert len(outlines) == 4


def test_a_count_in_every_region_is_drawn_inside_it() -> None:
    drawing = drawn(four())
    assert len(drawing.regions) == 15
    assert_inside_its_region(drawing, IDS)


def test_an_emphasised_region_is_filled_inside_its_own_region() -> None:
    document = four()
    document["regions"][-1]["role"] = "emphasis"
    drawing = drawn(document)
    ((membership, points),) = drawing.fills
    assert membership == frozenset(IDS)
    fills = [p for p in drawing.scene.primitives if isinstance(p, Polygon) and p.region]
    assert len(fills) == 1
    centre_x = sum(x for x, _ in points) / len(points)
    centre_y = sum(y for _, y in points) / len(points)
    assert all(in_ellipse(ellipse, centre_x, centre_y) < 1 for ellipse in drawing.ellipses)
    # Every outline point lies on one ellipse.
    for x, y in points:
        assert min(abs(in_ellipse(e, x, y) - 1) for e in drawing.ellipses) < 1e-6


def test_an_emphasised_set_has_a_heavier_outline() -> None:
    document = four()
    document["sets"][2]["role"] = "emphasis"
    outlines = [p for p in drawn(document).scene.primitives if isinstance(p, ScenePath)]
    assert [p.role for p in outlines] == ["step", "step", "emphasis", "step"]


# ---------------------------------------------------------------------------
# The references
# ---------------------------------------------------------------------------


def test_there_are_at_least_three_references() -> None:
    assert len(REFERENCES) >= 3


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_every_reference_puts_each_regions_words_inside_its_region(path: Path) -> None:
    document = json.loads(path.read_text())
    assert render(document).startswith("<svg")
    drawing = drawn(document)
    assert len(drawing.regions) == len(document.get("regions", []))
    assert_inside_its_region(drawing, [item["id"] for item in document["sets"]])


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_no_set_name_crosses_an_ellipse(path: Path) -> None:
    drawing = drawn(json.loads(path.read_text()))
    for rect in drawing.names.values():
        for ellipse in drawing.ellipses:
            assert all(in_ellipse(ellipse, x, y) > 1 for x, y in edge_points(rect))
            assert all(in_ellipse(ellipse, x, y) > 1 for x, y in corners(rect))


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_names_do_not_overlap(path: Path) -> None:
    rects = list(drawn(json.loads(path.read_text())).names.values())
    for one, other in itertools.combinations(rects, 2):
        assert one[2] <= other[0] or other[2] <= one[0] or one[3] <= other[1] or other[3] <= one[1]


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def test_the_example_is_valid() -> None:
    assert validate_document(four()) == ()


def test_a_fifth_set_is_refused_suggesting_a_matrix() -> None:
    document = four()
    document["sets"].append({"id": "e", "text": "Survey E"})
    assert pointers(document) == ["/sets/4"]
    assert "`matrix`" in messages(document)


def test_long_region_text_is_refused_with_four_sets() -> None:
    document = four()
    document["regions"][4]["text"] = "Shared by the first two"
    assert pointers(document) == ["/regions/4/text"]
    assert "12 at most" in messages(document)


def test_markup_does_not_count_against_the_four_set_limit() -> None:
    document = four()
    document["regions"][4]["text"] = "**Twelve chars**"
    assert validate_document(document) == ()


def test_the_same_text_with_three_sets_is_not_limited() -> None:
    document = four()
    document["sets"].pop()
    document["regions"] = [{"in": ["a", "b"], "text": "Shared by the first two"}]
    assert validate_document(document) == ()

"""`venn` — two or three overlapping sets, each region named by membership.

The kind's one promise is that a region's words are inside the region the author
named, so it is asserted point by point: every corner of every region's words is
inside each circle the region is in and outside each it is not. Set names stay
off every outline, an emphasised region is filled along its exact outline, and
the document rules — two or three sets, memberships that land and differ — are
asserted by the pointer of the refusal.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

from drawspec import render
from drawspec.errors import FitError
from drawspec.kinds.venn import CENTRES, VennDrawing, inside, venn_drawing
from drawspec.scene import Ellipse, Polygon
from drawspec.schema import parse_document, validate_document
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])
REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "reference"
REFERENCES = sorted(REFERENCE.glob("venn-*.json"))


def two(**extra: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "version": 1,
        "kind": "venn",
        "sets": [{"id": "a", "text": "Tea"}, {"id": "b", "text": "Coffee"}],
        "regions": [
            {"in": ["a"], "text": "Tannin"},
            {"in": ["b"], "text": "Crema"},
            {"in": ["a", "b"], "text": "Caffeine", "role": "emphasis"},
        ],
    }
    document.update(extra)
    return document


def three(**extra: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "version": 1,
        "kind": "venn",
        "sets": [
            {"id": "a", "text": "Fast"},
            {"id": "b", "text": "Cheap"},
            {"id": "c", "text": "Good"},
        ],
        "regions": [
            {"in": ["a", "b"], "text": "Rushed"},
            {"in": ["b", "c"], "text": "Slow"},
            {"in": ["a", "c"], "text": "Costly"},
            {"in": ["a", "b", "c"], "text": "Rare", "role": "emphasis"},
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


def assert_inside_its_region(drawing: VennDrawing, ids: list[str]) -> None:
    """Every corner of every region's words: in its circles, out of the others."""
    for membership, (left, top, right, bottom) in drawing.regions:
        for x in (left, right):
            for y in (top, bottom):
                for identifier, (cx, cy) in zip(ids, drawing.centres, strict=True):
                    distance = math.hypot(x - cx, y - cy)
                    if identifier in membership:
                        assert distance < drawing.radius, (membership, identifier)
                    else:
                        assert distance > drawing.radius, (membership, identifier)


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
def test_no_set_name_crosses_a_circle(path: Path) -> None:
    drawing = drawn(json.loads(path.read_text()))
    for left, top, right, bottom in drawing.names.values():
        for cx, cy in drawing.centres:
            # The name's box is wholly outside every circle: its nearest point is too.
            nx, ny = min(max(cx, left), right), min(max(cy, top), bottom)
            assert math.hypot(nx - cx, ny - cy) > drawing.radius


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("make", [two, three])
def test_the_circles_are_equal_and_a_radius_apart(make: Any) -> None:
    drawing = drawn(make())
    circles = [p for p in drawing.scene.primitives if isinstance(p, Ellipse)]
    assert {round(c.rx, 6) for c in circles} == {round(drawing.radius, 6)}
    for index, (x0, y0) in enumerate(drawing.centres):
        for x1, y1 in drawing.centres[index + 1 :]:
            assert math.hypot(x1 - x0, y1 - y0) == pytest.approx(drawing.radius)


def test_a_region_not_listed_is_drawn_empty() -> None:
    drawing = drawn(three())
    assert len(drawing.regions) == 4
    assert all(len(membership) > 1 for membership, _ in drawing.regions)


@pytest.mark.parametrize("make", [two, three])
def test_an_emphasised_region_is_filled_along_its_own_outline(make: Any) -> None:
    document = make()
    drawing = drawn(document)
    ((membership, points),) = drawing.fills
    ids = [item["id"] for item in document["sets"]]
    mask = tuple(identifier in membership for identifier in ids)
    fills = [p for p in drawing.scene.primitives if isinstance(p, Polygon) and p.region]
    assert len(fills) == 1 and fills[0].fill == THEME.mark.fill_for(0)
    # Every point of the outline is on the region's boundary: on one circle, and
    # inside or outside each of the others as the region is.
    count = len(ids)
    for x, y in points:
        distances = [math.hypot(x - cx, y - cy) / drawing.radius for cx, cy in drawing.centres]
        assert min(abs(d - 1) for d in distances) < 1e-6
    # And the polygon's centroid lies in the region.
    centre_x = sum(x for x, _ in points) / len(points)
    centre_y = sum(y for _, y in points) / len(points)
    origin_x, origin_y = drawing.centres[0]
    unit_x = (centre_x - origin_x) / drawing.radius + CENTRES[count][0][0]
    unit_y = (centre_y - origin_y) / drawing.radius + CENTRES[count][0][1]
    assert inside(mask, count, unit_x, unit_y)


def test_an_emphasised_set_has_a_heavier_outline() -> None:
    document = two()
    document["sets"][0]["role"] = "emphasis"
    document["regions"][2]["role"] = "step"
    circles = [p for p in drawn(document).scene.primitives if isinstance(p, Ellipse)]
    assert [c.role for c in circles] == ["emphasis", "step"]


def test_longer_words_draw_larger_circles() -> None:
    short = drawn(two())
    document = two()
    document["regions"][2]["text"] = " ".join(["Caffeine and a break"] * 6)
    assert drawn(document).radius > short.radius


def test_words_that_fit_no_region_are_a_fit_error_naming_the_region() -> None:
    document = two()
    document["regions"][2]["text"] = " ".join(["Somewhat"] * 60)
    with pytest.raises(FitError, match="region 'Somewhat"):
        drawn(document)


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def test_the_examples_are_valid() -> None:
    assert validate_document(two()) == ()
    assert validate_document(three()) == ()


def test_one_set_is_refused() -> None:
    document = two(sets=[{"id": "a", "text": "Tea"}], regions=[])
    assert pointers(document) == ["/sets"]
    assert "2 or 3 sets" in messages(document)


def test_four_sets_are_refused_suggesting_a_matrix() -> None:
    document = three()
    document["sets"].append({"id": "d", "text": "Fun"})
    assert pointers(document) == ["/sets/3"]
    assert "`matrix`" in messages(document)


def test_a_region_naming_an_unknown_set_is_refused_at_its_pointer() -> None:
    document = two()
    document["regions"][0]["in"] = ["aa"]
    assert pointers(document) == ["/regions/0/in/0"]
    assert "did you mean 'a'" in messages(document)


def test_an_empty_membership_is_refused() -> None:
    document = two()
    document["regions"][0]["in"] = []
    assert pointers(document) == ["/regions/0/in"]


def test_the_same_membership_twice_is_refused() -> None:
    document = two()
    document["regions"][1]["in"] = ["b", "a"]
    assert pointers(document) == ["/regions/2/in"]
    assert "already" in messages(document)


def test_a_set_named_twice_in_one_membership_is_refused() -> None:
    document = two()
    document["regions"][2]["in"] = ["a", "a"]
    assert pointers(document) == ["/regions/2/in/1"]


def test_duplicate_set_ids_are_refused() -> None:
    document = two(sets=[{"id": "a", "text": "Tea"}, {"id": "a", "text": "Coffee"}], regions=[])
    assert pointers(document) == ["/sets/1/id"]


@pytest.mark.parametrize(
    ("where", "name", "expected"),
    [
        ("root", "edges", "nothing to connect"),
        ("set", "subset_of", "`rings`"),
        ("set", "size", "not how much"),
    ],
)
def test_fields_a_venn_has_no_place_for_are_refused_by_name(
    where: str, name: str, expected: str
) -> None:
    document = two()
    if where == "root":
        document[name] = []
        pointer = f"/{name}"
    else:
        document["sets"][0][name] = 3
        pointer = f"/sets/0/{name}"
    assert pointers(document) == [pointer]
    assert expected in messages(document)

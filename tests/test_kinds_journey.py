"""`journey` — one person's named feeling across the stages of an experience.

The kind's promise is the feeling line: each stage's point sits on its level's
guide, the line passes through every point, and between two points it never
strays past either — two neighbours at one level are joined flat. Columns are
equal, cells sit in their column under their row, the emphasis stage is framed,
and every refusal in the proposal is asserted by its pointer.
"""

from __future__ import annotations

import json
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest

from drawspec import render
from drawspec.errors import FitError
from drawspec.kinds.journey import JourneyDrawing, journey_drawing, monotone
from drawspec.scene import Ellipse, TextLine
from drawspec.scene import Path as LinePath
from drawspec.schema import parse_document, validate_document
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])
REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "reference"
REFERENCES = sorted(REFERENCE.glob("journey-*.json"))


def permit(**extra: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "version": 1,
        "kind": "journey",
        "feelings": ["annoyed", "neutral", "pleased"],
        "rows": [{"id": "does", "text": "Does"}, {"id": "where", "text": "Where"}],
        "stages": [
            {
                "text": "Applies",
                "feeling": "neutral",
                "details": [
                    {"row": "does", "text": "Fills in the form"},
                    {"row": "where", "text": "Website"},
                ],
            },
            {
                "text": "Uploads",
                "feeling": "annoyed",
                "role": "emphasis",
                "details": [{"row": "does", "text": "Sends a bill"}],
            },
            {"text": "Pays", "feeling": "annoyed"},
            {"text": "Receives", "feeling": "pleased"},
        ],
    }
    document.update(extra)
    return document


def drawn(document: dict[str, Any]) -> JourneyDrawing:
    return journey_drawing(parse_document(document), THEME, MEASURER)


def pointers(document: dict[str, Any]) -> list[str]:
    return [violation.pointer for violation in validate_document(document)]


def messages(document: dict[str, Any]) -> str:
    return "\n".join(violation.message for violation in validate_document(document))


def on_line(line: tuple[tuple[float, float], ...], x: float, y: float) -> bool:
    return any(abs(px - x) < 1e-6 and abs(py - y) < 1e-6 for px, py in line)


# ---------------------------------------------------------------------------
# The references
# ---------------------------------------------------------------------------


def test_there_are_at_least_three_references() -> None:
    assert len(REFERENCES) >= 3


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_every_point_is_on_its_level_and_on_the_line(path: Path) -> None:
    document = json.loads(path.read_text())
    assert render(document).startswith("<svg")
    drawing = drawn(document)
    assert len(drawing.points) == len(document["stages"])
    for stage, (left, right), (x, y) in zip(
        document["stages"], drawing.columns, drawing.points, strict=True
    ):
        assert y == pytest.approx(drawing.levels[stage["feeling"]])
        assert x == pytest.approx((left + right) / 2)
        assert on_line(drawing.line, x, y)


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_the_line_never_strays_past_its_two_points(path: Path) -> None:
    drawing = drawn(json.loads(path.read_text()))
    for (x0, y0), (x1, y1) in pairwise(drawing.points):
        low, high = min(y0, y1), max(y0, y1)
        for x, y in drawing.line:
            if x0 <= x <= x1:
                assert low - 1e-6 <= y <= high + 1e-6


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_every_cell_is_inside_its_column_and_its_row(path: Path) -> None:
    drawing = drawn(json.loads(path.read_text()))
    for row, index, (left, top, right, bottom) in drawing.cells:
        column_left, column_right = drawing.columns[index]
        row_top, row_bottom = drawing.rows[row]
        assert column_left <= left and right <= column_right
        assert row_top < top and bottom < row_bottom


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


def test_the_worst_feeling_is_at_the_bottom_and_levels_are_even() -> None:
    drawing = drawn(permit())
    ys = [drawing.levels[name] for name in ("annoyed", "neutral", "pleased")]
    assert ys[0] > ys[1] > ys[2]
    assert ys[0] - ys[1] == pytest.approx(ys[1] - ys[2])


def test_two_neighbours_at_one_level_are_joined_flat() -> None:
    drawing = drawn(permit())
    (x0, y0), (x1, y1) = drawing.points[1], drawing.points[2]
    assert y0 == y1
    assert all(y == pytest.approx(y0) for x, y in drawing.line if x0 <= x <= x1)


def test_the_monotone_line_passes_through_every_point() -> None:
    points = ((0.0, 0.0), (10.0, 5.0), (20.0, 5.0), (30.0, -2.0), (40.0, 8.0))
    line = monotone(points)
    for x, y in points:
        assert on_line(line, x, y)
    assert monotone(points[:2]) == points[:2]


def test_the_columns_are_equal() -> None:
    drawing = drawn(permit())
    widths = {round(right - left, 6) for left, right in drawing.columns}
    assert len(widths) == 1


def test_the_emphasis_stage_is_framed_and_its_point_larger_and_solid() -> None:
    drawing = drawn(permit())
    ((left, top, right, bottom),) = drawing.frames
    column_left, column_right = drawing.columns[1]
    assert left < column_left and column_right < right
    assert top == 0.0 and bottom == drawing.scene.height
    points = [p for p in drawing.scene.primitives if isinstance(p, Ellipse)]
    emphasis = [p for p in points if p.role == "emphasis"]
    ordinary = [p for p in points if p.role == "step"]
    assert len(emphasis) == 1 and len(ordinary) == 3
    assert emphasis[0].rx > ordinary[0].rx and emphasis[0].fill == "solid"


def test_a_missing_detail_is_an_empty_cell() -> None:
    drawing = drawn(permit())
    assert {(row, index) for row, index, _ in drawing.cells} == {
        ("does", 0),
        ("where", 0),
        ("does", 1),
    }


def test_a_journey_with_no_rows_is_headings_and_the_band_only() -> None:
    document = permit()
    del document["rows"]
    for stage in document["stages"]:
        stage.pop("details", None)
    drawing = drawn(document)
    assert drawing.rows == {} and drawing.cells == ()
    words = [p.text for p in drawing.scene.primitives if isinstance(p, TextLine)]
    assert words == ["Applies", "Uploads", "Pays", "Receives", "annoyed", "neutral", "pleased"]
    separators = [
        p
        for p in drawing.scene.primitives
        if isinstance(p, LinePath) and p.role == THEME.journey.separator
    ]
    assert separators == []


def test_the_line_and_guides_take_the_themes_roles() -> None:
    drawing = drawn(permit())
    roles = [p.role for p in drawing.scene.primitives if isinstance(p, LinePath)]
    assert roles.count(THEME.journey.line) == 1
    assert roles.count(THEME.journey.guide) == 3
    assert roles.count(THEME.journey.separator) == 2


def test_a_word_too_wide_for_its_column_is_a_fit_error() -> None:
    document = permit()
    document["stages"][0]["details"][0]["text"] = "Supercalifragilisticexpialidocious" * 2
    with pytest.raises(FitError, match="detail 'Supercali"):
        drawn(document)


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def test_the_example_is_valid() -> None:
    assert validate_document(permit()) == ()


@pytest.mark.parametrize("value", [3, 2.5])
def test_a_number_for_a_feeling_is_refused(value: float) -> None:
    document = permit()
    document["stages"][0]["feeling"] = value
    assert pointers(document) == ["/stages/0/feeling"]
    assert "a name, not a score" in messages(document)


def test_a_number_among_the_feelings_is_refused() -> None:
    document = permit(feelings=[1, 2, 3])
    assert "/feelings/0" in pointers(document)
    assert "a name, not a score" in messages(document)


def test_a_feeling_not_in_feelings_is_refused_naming_the_closest() -> None:
    document = permit()
    document["stages"][3]["feeling"] = "please"
    assert pointers(document) == ["/stages/3/feeling"]
    assert "did you mean 'pleased'" in messages(document)


def test_a_stage_without_a_feeling_is_refused_naming_flow() -> None:
    document = permit()
    del document["stages"][2]["feeling"]
    assert pointers(document) == ["/stages/2/feeling"]
    assert "`flow`" in messages(document)


def test_personas_are_refused() -> None:
    document = permit(personas=["Resident", "Clerk"])
    assert pointers(document) == ["/personas"]
    assert "one person" in messages(document)


def test_edges_are_refused() -> None:
    document = permit(edges=[{"from": "a", "to": "b"}])
    assert pointers(document) == ["/edges"]
    assert "already in order" in messages(document)


def test_a_score_on_a_stage_is_refused() -> None:
    document = permit()
    document["stages"][0]["score"] = 4
    assert pointers(document) == ["/stages/0/score"]
    assert "not a score" in messages(document)


@pytest.mark.parametrize(
    ("field", "count", "pointer"),
    [("stages", 8, "/stages/7"), ("feelings", 6, "/feelings/5"), ("rows", 5, "/rows/4")],
)
def test_past_the_budget_is_refused_suggesting_two_journeys(
    field: str, count: int, pointer: str
) -> None:
    document = permit()
    if field == "stages":
        document["stages"] = [{"text": f"S{i}", "feeling": "neutral"} for i in range(count)]
    elif field == "feelings":
        document["feelings"] = ["annoyed", "neutral", "pleased", "a", "b", "c"][:count]
    else:
        document["rows"] = [{"id": f"r{i}", "text": f"R{i}"} for i in range(count)]
        document["stages"][0]["details"] = []
        document["stages"][1]["details"] = []
    assert pointers(document) == [pointer]
    assert "journey" in messages(document)


def test_one_feeling_or_one_stage_is_refused() -> None:
    assert pointers(permit(feelings=["neutral"])) == [
        "/feelings",
        "/stages/1/feeling",
        "/stages/2/feeling",
        "/stages/3/feeling",
    ]
    assert "at least 2 feelings" in messages(permit(feelings=["neutral"]))
    document = permit()
    document["stages"] = document["stages"][:1]
    assert pointers(document) == ["/stages"]


def test_a_detail_in_an_unknown_row_is_refused_at_its_pointer() -> None:
    document = permit()
    document["stages"][1]["details"][0]["row"] = "dose"
    assert pointers(document) == ["/stages/1/details/0/row"]
    assert "did you mean 'does'" in messages(document)


def test_a_detail_with_no_rows_declared_is_refused() -> None:
    document = permit()
    del document["rows"]
    assert pointers(document) == [
        "/stages/0/details/0/row",
        "/stages/0/details/1/row",
        "/stages/1/details/0/row",
    ]
    assert "no `rows`" in messages(document)


def test_a_row_named_twice_in_one_stage_is_refused() -> None:
    document = permit()
    document["stages"][0]["details"][1]["row"] = "does"
    assert pointers(document) == ["/stages/0/details/1/row"]


def test_duplicate_feelings_and_row_ids_are_refused() -> None:
    assert pointers(permit(feelings=["annoyed", "neutral", "neutral", "pleased"])) == [
        "/feelings/2"
    ]
    document = permit(rows=[{"id": "does", "text": "Does"}, {"id": "does", "text": "Where"}])
    document["stages"][0]["details"].pop()
    assert pointers(document) == ["/rows/1/id"]


def test_details_as_an_object_keyed_by_row_is_refused() -> None:
    document = permit()
    document["stages"][0]["details"] = {"does": "Fills in the form"}
    assert pointers(document) == ["/stages/0/details"]

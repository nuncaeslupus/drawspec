"""`rag` — a RAG status report: rows rated red, amber or green, in words and shapes.

The kind's promise is that a rating is never told by colour alone: each mark
carries the theme's word and the theme's shape for it, the three shapes and the
three words differ (the theme loader holds both to that), and a trend is written
in words beside its arrow because an arrow alone means opposite things in
different reports (corpus R2, R5). The geometry is asserted on the drawing; the
document rules by the pointer of the refusal.
"""

from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path
from typing import Any

import pytest

from drawspec import render
from drawspec.errors import FitError, ThemeError
from drawspec.geometry import fit
from drawspec.kinds.rag import RagDrawing, rag_drawing
from drawspec.schema import RAG_ROW_MAX, READABILITY_BUDGET, parse_document, validate_document
from drawspec.text import TextMeasurer
from drawspec.theme import Theme, load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])
REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "reference"
REFERENCES = sorted(REFERENCE.glob("rag-*.json"))


def report(*rows: dict[str, Any], **extra: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "version": 1,
        "kind": "rag",
        "rows": list(rows) or [{"text": "Data migration", "rag": "amber"}],
    }
    document.update(extra)
    return document


def drawn(document: dict[str, Any], theme: Theme = THEME) -> RagDrawing:
    parsed = parse_document(document)
    return fit(theme, lambda scaled: rag_drawing(parsed, scaled, MEASURER)).value


def pointers(document: dict[str, Any]) -> list[str]:
    return [violation.pointer for violation in validate_document(document)]


def messages(document: dict[str, Any]) -> str:
    return "\n".join(violation.message for violation in validate_document(document))


THREE = (
    {"text": "Building works", "rag": "red", "trend": "worse", "note": "Two weeks late."},
    {"text": "Kiosks", "rag": "amber", "trend": "same", "note": "Awaiting parts."},
    {"text": "Training", "rag": "green", "trend": "better", "note": "Booked."},
)


# --------------------------------------------------------------------------
# The references
# --------------------------------------------------------------------------


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_every_reference_renders(path: Path) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    assert validate_document(document) == ()
    assert render(document).startswith("<svg")


def test_there_are_at_least_three_references() -> None:
    assert len(REFERENCES) >= 3


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_no_two_words_overlap_in_a_reference(path: Path) -> None:
    drawing = drawn(json.loads(path.read_text(encoding="utf-8")))
    for one, two in combinations(drawing.texts, 2):
        apart = one[2] <= two[0] or two[2] <= one[0] or one[3] <= two[1] or two[3] <= one[1]
        assert apart, (one, two)


# --------------------------------------------------------------------------
# Never colour alone
# --------------------------------------------------------------------------


def test_each_rating_has_its_own_word_and_shape() -> None:
    """The word and the shape both differ, so greyscale keeps all three ratings."""
    drawing = drawn(report(*THREE))
    assert drawing.words == ("Red", "Amber", "Green")
    assert [mark[0] for mark in drawing.marks] == ["square", "triangle", "circle"]


def test_the_default_theme_draws_marks_in_the_pages_ink() -> None:
    svg = render(report(*THREE))
    assert "#" not in svg.split(">", 1)[1].replace("#p", "").replace("url(#", "")


def test_the_accent_theme_colours_the_marks_on_top() -> None:
    svg = render(report(*THREE), theme="accent")
    for colour in ("#c0452a", "#d9a21b", "#3e7a4a"):
        assert colour in svg
    assert "Red" in svg and "Amber" in svg and "Green" in svg


def test_a_house_may_rename_the_ratings() -> None:
    theme = load_theme(
        {"version": 1, "rag": {"red": "Off track", "amber": "At risk", "green": "On track"}}
    )
    assert drawn(report(*THREE), theme).words == ("Off track", "At risk", "On track")


def test_the_trend_is_written_in_words() -> None:
    drawing = drawn(report(*THREE))
    assert drawing.trends == ("worsening", "no change", "improving")


def test_a_row_without_a_trend_writes_none() -> None:
    drawing = drawn(report(THREE[0], {"text": "Kiosks", "rag": "green"}))
    assert drawing.trends == ("worsening", "")


@pytest.mark.parametrize(
    ("override", "says"),
    [
        ({"red_shape": "circle"}, "repeat a shape"),
        ({"amber": "Red"}, "repeat a word"),
        ({"worse": "improving"}, "repeat a word"),
        ({"green_shape": "star"}, "is not one of"),
        ({"red_colour": "none"}, "visible"),
        ({"blue": "Blue"}, "blue"),
    ],
)
def test_the_theme_keeps_the_ratings_apart(override: dict[str, str], says: str) -> None:
    with pytest.raises(ThemeError, match=says):
        load_theme({"version": 1, "rag": override})


# --------------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------------


def test_the_mark_sits_on_the_names_first_line() -> None:
    """A long note makes a tall row; the mark stays with the name, not the middle."""
    long = "A sentence of commentary that is long enough to wrap onto several lines. " * 3
    drawing = drawn(report({"text": "Building works", "rag": "red", "note": long}))
    top, bottom = drawing.rows[0][1], drawing.rows[0][3]
    centre = drawing.marks[0][2]
    assert bottom - top > 3 * 14
    assert top < centre < top + 20


def test_the_columns_line_up_down_the_rows() -> None:
    drawing = drawn(report(*THREE))
    xs = [mark[1] for mark in drawing.marks]
    assert max(xs) - min(xs) < 1e-6
    assert len(drawing.columns) == 4


def test_rows_run_down_the_page_in_the_order_written() -> None:
    drawing = drawn(report(*THREE))
    tops = [row[1] for row in drawing.rows]
    assert tops == sorted(tops)
    for upper, lower in zip(drawing.rows, drawing.rows[1:], strict=False):
        assert upper[3] < lower[1]


def test_a_report_without_notes_is_centred() -> None:
    drawing = drawn(report({"text": "Kiosks", "rag": "green"}))
    left, right = drawing.rows[0][0], drawing.rows[0][2]
    assert abs(left - (THEME.canvas.width - right)) < 1.0


def test_a_name_wider_than_its_column_wraps() -> None:
    name = "A workstream whose name runs on well past a third of the page width"
    drawing = drawn(report({"text": name, "rag": "amber", "note": "Some note."}))
    assert drawing.columns[1] < THEME.canvas.width * 0.4


def test_too_narrow_a_canvas_is_a_fit_error() -> None:
    document = report(*THREE, width=180)
    with pytest.raises(FitError):
        drawn(document)


# --------------------------------------------------------------------------
# Refusals, by pointer
# --------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["amber/green", "blue", "Red", "grey"])
def test_a_rating_outside_the_three_is_refused(value: str) -> None:
    document = report({"text": "Kiosks", "rag": value})
    assert pointers(document) == ["/rows/0/rag"]
    assert "note" in messages(document)


@pytest.mark.parametrize("value", ["up", "down", "improving"])
def test_a_trend_by_direction_is_refused_with_the_reason(value: str) -> None:
    document = report({"text": "Kiosks", "rag": "green", "trend": value})
    assert pointers(document) == ["/rows/0/trend"]
    assert "better" in messages(document) and "arrow" in messages(document)


def test_a_row_must_have_a_rating() -> None:
    assert pointers(report({"text": "Kiosks"})) == ["/rows/0/rag"]


@pytest.mark.parametrize(
    ("name", "says"),
    [
        ("status", "`rag`"),
        ("colour", "word, a shape"),
        ("score", "`matrix`"),
        ("owner", "caption"),
        ("commentary", "`note`"),
    ],
)
def test_a_field_reached_for_is_refused_with_advice(name: str, says: str) -> None:
    document = report({"text": "Kiosks", "rag": "green", name: "x"})
    assert pointers(document) == [f"/rows/0/{name}"]
    assert says in messages(document)


@pytest.mark.parametrize("name", ["edges", "columns"])
def test_connections_and_dimensions_are_refused(name: str) -> None:
    document = report(**{name: []})
    assert pointers(document) == [f"/{name}"]


def test_no_rows_is_refused() -> None:
    assert pointers({"version": 1, "kind": "rag", "rows": []}) == ["/rows"]
    assert pointers({"version": 1, "kind": "rag"}) == ["/rows"]


def test_the_budget_is_the_largest_register_plus_headroom() -> None:
    assert dict(READABILITY_BUDGET["rag"]) == {"rows": RAG_ROW_MAX}
    rows = [{"text": f"Risk {n}", "rag": "green"} for n in range(RAG_ROW_MAX)]
    assert validate_document(report(*rows)) == ()
    rows.append({"text": "One too many", "rag": "red"})
    found = validate_document(report(*rows))
    assert [violation.pointer for violation in found] == [f"/rows/{RAG_ROW_MAX}"]
    assert "split" in found[0].message

"""`board` — cards sorted into columns: a kanban board, a retrospective, a story map.

The kind's claims are counted rather than ranked, so they are asserted from the
drawing: every card is its column's width and inside it, cards stack in the
order written, a heading's `n / limit` is drawspec's count and takes `emphasis`
over the limit, and the cut is under the row it names and nowhere else. The
document rules — no connectors, ids that land, half a story map, a cut with
nothing below it, the per-cell cap — are asserted by the pointer of the refusal.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from drawspec import render
from drawspec.errors import DocumentError, FitError, ThemeError
from drawspec.kinds.board import BoardDrawing, board_drawing
from drawspec.scene import Path as Stroke
from drawspec.scene import Polygon, Rect, TextLine
from drawspec.schema import BOARD_CELL_MAX, READABILITY_BUDGET, parse_document, validate_document
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])
REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "reference"
REFERENCES = sorted(REFERENCE.glob("board-*.json"))
EPSILON = 1e-6


def kanban(**extra: Any) -> dict[str, Any]:
    """Three columns, one with a limit it is over, one card of each role."""
    document: dict[str, Any] = {
        "version": 1,
        "kind": "board",
        "columns": [
            {"id": "todo", "text": "To do"},
            {"id": "doing", "text": "Doing", "limit": 2},
            {"id": "done", "text": "Done", "limit": 5},
        ],
        "cards": [
            {"text": "First", "column": "doing"},
            {"text": "Second", "column": "doing", "actor": "Ana", "role": "emphasis"},
            {"text": "Third", "column": "doing", "note": "waiting on review"},
            {"text": "Shipped", "column": "done"},
            {"text": "+ 4 more", "column": "todo", "role": "note"},
        ],
    }
    document.update(extra)
    return document


def story(**extra: Any) -> dict[str, Any]:
    """Two steps sliced into three releases, cut under the first."""
    document: dict[str, Any] = {
        "version": 1,
        "kind": "board",
        "columns": [{"id": "find", "text": "Find"}, {"id": "buy", "text": "Buy"}],
        "rows": [
            {"id": "one", "text": "First release"},
            {"id": "two", "text": "Next"},
            {"id": "three", "text": "Later"},
        ],
        "cut": "one",
        "cards": [
            {"text": "Search", "column": "find", "row": "one"},
            {"text": "Pay by card", "column": "buy", "row": "one"},
            {"text": "Filters", "column": "find", "row": "two"},
            {"text": "Gift cards", "column": "buy", "row": "three"},
        ],
    }
    document.update(extra)
    return document


def drawn(document: dict[str, Any], theme: Any = THEME) -> BoardDrawing:
    return board_drawing(parse_document(document), theme, MEASURER)


def pointers(document: dict[str, Any]) -> list[str]:
    return [violation.pointer for violation in validate_document(document)]


def messages(document: dict[str, Any]) -> str:
    return "\n".join(violation.message for violation in validate_document(document))


# ---------------------------------------------------------------------------
# The references
# ---------------------------------------------------------------------------


def test_there_are_at_least_three_references() -> None:
    assert len(REFERENCES) >= 3


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_every_reference_renders_with_each_card_inside_its_column(path: Path) -> None:
    document = json.loads(path.read_text())
    assert render(document).startswith("<svg")
    drawing = drawn(document)
    for card, (left, top, right, bottom) in zip(
        parse_document(document).cards, drawing.cards, strict=True
    ):
        assert (left, right) == pytest.approx(drawing.columns[card.column])
        row_top, row_bottom = drawing.rows[card.row]
        assert row_top - EPSILON <= top < bottom <= row_bottom + EPSILON


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


def test_columns_are_equal_and_in_the_order_written() -> None:
    drawing = drawn(kanban())
    spans = [drawing.columns[name] for name in ("todo", "doing", "done")]
    widths = {round(right - left, 6) for left, right in spans}
    assert len(widths) == 1
    assert spans[0][1] < spans[1][0] and spans[1][1] < spans[2][0]


def test_cards_in_a_cell_stack_in_the_order_written_from_the_top() -> None:
    """Top-aligned: the first card of every column starts at the same height."""
    drawing = drawn(kanban())
    tops = [card[1] for card in drawing.cards]
    first, second, third, shipped, more = tops
    assert first < second < third
    assert first == pytest.approx(shipped) == pytest.approx(more)
    # Stacked, not overlapping.
    for upper, lower in zip(drawing.cards[:2], drawing.cards[1:3], strict=True):
        assert upper[3] < lower[1]


def test_a_column_over_its_limit_is_counted_and_its_heading_takes_emphasis() -> None:
    drawing = drawn(kanban())
    text, role = drawing.headings["doing"]
    assert "3 / 2" in text.replace("**", "")
    assert role == "emphasis"
    rules = [p for p in drawing.scene.primitives if isinstance(p, Stroke) and p.role == "emphasis"]
    left, right = drawing.columns["doing"]
    assert any(
        rule.points[0][0] == pytest.approx(left) and rule.points[-1][0] == pytest.approx(right)
        for rule in rules
    )


def test_a_column_at_its_limit_keeps_its_own_role() -> None:
    document = kanban()
    document["cards"] = document["cards"][:2]
    drawing = drawn(document)
    text, role = drawing.headings["doing"]
    assert "2 / 2" in text.replace("**", "")
    assert role == "step"


def test_a_note_card_is_not_counted_against_a_limit() -> None:
    document = kanban()
    document["columns"][0]["limit"] = 1
    text, role = drawn(document).headings["todo"]
    assert "0 / 1" in text.replace("**", "")
    assert role == "step"


def test_the_count_is_written_in_the_heading_text_drawn() -> None:
    drawing = drawn(kanban())
    words = " ".join(
        span.text
        for primitive in drawing.scene.primitives
        if isinstance(primitive, TextLine)
        for span in primitive.spans
    )
    assert "3 / 2" in words and "1 / 5" in words


def test_an_emphasis_column_draws_a_heavy_rule() -> None:
    document = kanban()
    document["columns"][0]["role"] = "emphasis"
    assert drawn(document).headings["todo"][1] == "emphasis"


def test_the_cut_is_under_the_row_it_names_and_nowhere_else() -> None:
    drawing = drawn(story())
    assert drawing.cut is not None
    one_bottom = drawing.rows["one"][1]
    two_top = drawing.rows["two"][0]
    assert one_bottom < drawing.cut < two_top
    heavy = [
        p for p in drawing.scene.primitives if isinstance(p, Stroke) and p.role == THEME.board.cut
    ]
    assert len(heavy) == 1
    # The other gap gets an ordinary separator instead.
    (separator,) = drawing.separators
    assert drawing.rows["two"][1] < separator < drawing.rows["three"][0]


def test_without_a_cut_every_gap_is_a_separator() -> None:
    document = story()
    del document["cut"]
    drawing = drawn(document)
    assert drawing.cut is None
    assert len(drawing.separators) == 2


def test_the_theme_chooses_the_lines() -> None:
    theme = load_theme({"version": 1, "board": {"separator": "aside", "cut": "flow"}})
    document = story()
    strokes = {p.role for p in drawn(document, theme).scene.primitives if isinstance(p, Stroke)}
    assert {"aside", "flow"} <= strokes


def test_the_board_theme_section_is_checked() -> None:
    with pytest.raises(ThemeError):
        load_theme({"version": 1, "board": {"cut": "thick"}})
    with pytest.raises(ThemeError):
        load_theme({"version": 1, "board": {"colour": "red"}})


def test_slice_labels_sit_in_a_margin_left_of_every_column() -> None:
    drawing = drawn(story())
    first_column = min(left for left, _ in drawing.columns.values())
    labels = [
        p
        for p in drawing.scene.primitives
        if isinstance(p, TextLine) and p.anchor == "start" and p.x < first_column
    ]
    assert {span.text for label in labels for span in label.spans} >= {"Later", "Next"}


def test_an_actor_is_the_cards_lead_and_a_note_hangs_under_the_card() -> None:
    drawing = drawn(kanban())
    lines = [p for p in drawing.scene.primitives if isinstance(p, TextLine)]

    def where(word: str) -> TextLine:
        return next(line for line in lines if any(span.text == word for span in line.spans))

    assert where("Ana").y < where("Second").y
    note = where("waiting on review")
    assert note.level == "label" and note.y > where("Third").y
    # Under the card, outside its border: words inside a shape are body text.
    _, _, _, bottom = drawing.cards[2]
    assert note.y > bottom
    # And above the next card in its column, if any; here, the last.
    assert all(card[1] < bottom for card in drawing.cards[:3])


def test_roles_are_told_apart_without_colour() -> None:
    """An emphasis card is the heavier box, a note card a dashed polygon."""
    drawing = drawn(kanban())
    rects = [p for p in drawing.scene.primitives if isinstance(p, Rect)]
    assert {rect.role for rect in rects} == {"step", "emphasis"}
    notes = [p for p in drawing.scene.primitives if isinstance(p, Polygon)]
    assert [p.role for p in notes] == ["note"]


def test_no_connectors_are_drawn() -> None:
    """Every line is a heading rule, a separator or the cut: horizontal, no heads."""
    drawing = drawn(story())
    for primitive in drawing.scene.primitives:
        if isinstance(primitive, Stroke):
            ((_, y1), (_, y2)) = primitive.points
            assert y1 == pytest.approx(y2)
        assert not (isinstance(primitive, Polygon) and primitive.role in THEME.edge_roles)


def test_a_word_wider_than_a_column_is_a_fit_error() -> None:
    document = kanban(width=320)
    document["columns"] = [
        {"id": name, "text": name.title()} for name in ("todo", "doing", "done", "a", "b", "c")
    ]
    document["cards"][0]["text"] = "Incomprehensibilities"
    with pytest.raises(FitError):
        render(document)


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def test_edges_are_refused_with_flow_and_lanes_named() -> None:
    document = kanban(edges=[{"from": "a", "to": "b"}])
    assert pointers(document) == ["/edges"]
    message = messages(document)
    assert "`flow`" in message and "`lanes`" in message


@pytest.mark.parametrize("name", ["label", "tag", "colour"])
def test_a_per_card_appearance_field_is_refused_with_its_reason(name: str) -> None:
    document = kanban()
    document["cards"][0][name] = "urgent"
    assert pointers(document) == [f"/cards/0/{name}"]
    assert "column" in messages(document)


def test_order_is_refused_the_array_is_the_order() -> None:
    document = kanban()
    document["cards"][0]["order"] = 2
    assert pointers(document) == ["/cards/0/order"]


def test_a_card_in_an_unknown_column_is_refused_at_its_pointer() -> None:
    document = kanban()
    document["cards"][1]["column"] = "doign"
    assert pointers(document) == ["/cards/1/column"]
    assert "'doing'" in messages(document)


def test_a_card_in_an_unknown_row_is_refused_at_its_pointer() -> None:
    document = story()
    document["cards"][2]["row"] = "tow"
    assert pointers(document) == ["/cards/2/row"]


def test_a_row_on_a_board_with_no_rows_is_refused() -> None:
    document = kanban()
    document["cards"][0]["row"] = "one"
    assert pointers(document) == ["/cards/0/row"]


def test_a_card_with_no_row_on_a_board_with_rows_is_refused() -> None:
    document = story()
    del document["cards"][3]["row"]
    assert pointers(document) == ["/cards/3/row"]
    assert "half a story map" in messages(document)


def test_a_cut_naming_the_last_row_is_refused() -> None:
    assert pointers(story(cut="three")) == ["/cut"]
    assert "cuts nothing" in messages(story(cut="three"))


def test_a_cut_naming_an_unknown_row_is_refused() -> None:
    assert pointers(story(cut="fist")) == ["/cut"]


def test_a_cut_without_rows_is_refused() -> None:
    assert pointers(kanban(cut="one")) == ["/cut"]


def test_a_limit_must_be_a_positive_integer() -> None:
    for value in (0, -1, 1.5, "2"):
        document = kanban()
        document["columns"][1]["limit"] = value
        assert pointers(document) == ["/columns/1/limit"], value


def test_duplicate_column_and_row_ids_are_refused() -> None:
    document = story()
    document["columns"][1]["id"] = "find"
    document["rows"][2]["id"] = "two"
    assert set(pointers(document)) >= {"/columns/1/id", "/rows/2/id"}


def test_an_actor_forbids_a_second_paragraph() -> None:
    document = kanban()
    document["cards"][1]["text"] = "Second\nwith detail"
    assert pointers(document) == ["/cards/1/text"]


def test_a_card_role_outside_the_vocabulary_is_refused() -> None:
    document = kanban()
    document["cards"][0]["role"] = "decision"
    assert pointers(document) == ["/cards/0/role"]


def test_seven_columns_are_refused_with_the_split_message() -> None:
    assert dict(READABILITY_BUDGET["board"])["columns"] == 6
    document = kanban(
        columns=[{"id": f"c{index}", "text": "Column"} for index in range(7)],
        cards=[{"text": "Card", "column": "c0"}],
    )
    (violation,) = validate_document(document)
    assert violation.pointer == "/columns/6"
    assert "Split it" in violation.message


def test_five_rows_are_refused() -> None:
    document = story(
        rows=[{"id": f"r{index}", "text": "Row"} for index in range(5)],
        cut="r0",
        cards=[{"text": "Card", "column": "find", "row": "r0"}],
    )
    assert pointers(document) == ["/rows/4"]


def test_a_ninth_card_in_one_cell_is_refused_with_a_summary_card_suggested() -> None:
    document = story(
        cards=[{"text": "Card", "column": "find", "row": "one"} for _ in range(BOARD_CELL_MAX)]
        + [{"text": "Other", "column": "buy", "row": "one"}]
    )
    assert validate_document(document) == ()
    document["cards"].append({"text": "One too many", "column": "find", "row": "one"})
    assert pointers(document) == [f"/cards/{BOARD_CELL_MAX + 1}"]
    assert '"role": "note"' in messages(document)


def test_the_cell_cap_counts_per_row_not_per_column() -> None:
    cards = [
        {"text": "Card", "column": "find", "row": row}
        for row in ("one", "two")
        for _ in range(BOARD_CELL_MAX)
    ]
    assert validate_document(story(cards=cards)) == ()


def test_a_refused_document_raises_with_every_violation() -> None:
    document = story(cut="three")
    document["cards"][0]["column"] = "nowhere"
    with pytest.raises(DocumentError) as error:
        parse_document(document)
    assert len(error.value.violations) == 2

"""`wardley` — a value chain placed against evolution, with no coordinate written.

The kind's promises: a component's row is derived from what needs it (one below the
lowest dependent; `depth` only sinks it); its place across is a named stage, early,
middle or late in it, left to right; dependency lines run down and pass through no
other dot; no name meets another, a dot, a line, an arrow or a bar, and a name with
nowhere to go is refused. A map that hangs from nothing, loops, or moves leftwards is
refused at its pointer.
"""

from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path
from typing import Any

import pytest

from drawspec import render
from drawspec.errors import DrawspecError, FitError, ThemeError
from drawspec.kinds.wardley import WardleyDrawing, _crosses, _distance, wardley_drawing
from drawspec.render import render_text
from drawspec.schema import (
    WARDLEY_COMPONENT_MAX,
    WARDLEY_EVOLUTION,
    parse_document,
    validate_document,
)
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])
REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "reference"
REFERENCES = sorted(REFERENCE.glob("wardley-*.json"))


def tea(**extra: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "version": 1,
        "kind": "wardley",
        "anchors": [{"id": "customer", "text": "Customer", "needs": ["cup"]}],
        "components": [
            {"id": "cup", "text": "Cup of tea", "evolution": "product", "needs": ["tea", "water"]},
            {"id": "tea", "text": "Tea", "evolution": "late product"},
            {"id": "water", "text": "Hot water", "evolution": "commodity", "needs": ["kettle"]},
            {"id": "kettle", "text": "Kettle", "evolution": "custom", "needs": ["power"]},
            {"id": "power", "text": "Power", "evolution": "late commodity"},
        ],
    }
    document.update(extra)
    return document


def component(document: dict[str, Any], ident: str) -> dict[str, Any]:
    entry: dict[str, Any] = next(c for c in document["components"] if c["id"] == ident)
    return entry


def drawn(document: dict[str, Any]) -> WardleyDrawing:
    return wardley_drawing(parse_document(document), THEME, MEASURER)


def refusals(document: dict[str, Any]) -> dict[str, str]:
    return {violation.pointer: violation.message for violation in validate_document(document)}


# -- the references -----------------------------------------------------------


def test_there_are_references() -> None:
    assert len(REFERENCES) >= 3


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_every_reference_validates_and_renders(path: Path) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    assert validate_document(document) == ()
    assert render(document).startswith("<svg")
    assert render(document, "blueprint", "standalone").startswith("<svg")


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_no_name_meets_another_name_a_dot_or_a_line(path: Path) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    drawing = drawn(document)
    boxes = list(drawing.labels.values())
    for first, second in combinations(boxes, 2):
        overlap = (
            first[0] < second[2]
            and second[0] < first[2]
            and first[1] < second[3]
            and second[1] < first[3]
        )
        assert not overlap
    for box in boxes:
        for x, y in drawing.centres.values():
            assert not (box[0] <= x <= box[2] and box[1] <= y <= box[3])
    parsed = parse_document(document)
    for item in parsed.wardley_components:
        for need in item.needs:
            start, end = drawing.centres[item.id], drawing.centres[need]
            for box in boxes:
                shrunk = (box[0] + 0.5, box[1] + 0.5, box[2] - 0.5, box[3] - 0.5)
                assert not _crosses(shrunk, start, end), (item.id, need)


# -- the plane ----------------------------------------------------------------


def test_rows_are_derived_from_needs() -> None:
    """One row below the lowest thing that needs it: the longest path from an anchor."""
    drawing = drawn(tea())
    assert drawing.rows == {"cup": 1, "tea": 2, "water": 2, "kettle": 3, "power": 4}
    ys = {key: y for key, (_, y) in drawing.centres.items()}
    assert ys["cup"] < ys["tea"] == ys["water"] < ys["kettle"] < ys["power"]


def test_a_component_needed_at_two_depths_sits_below_the_deeper() -> None:
    document = tea()
    component(document, "cup")["needs"].append("power")
    assert drawn(document).rows["power"] == 4


def test_depth_sinks_a_component_and_what_it_needs() -> None:
    document = tea()
    component(document, "kettle")["depth"] = 5
    drawing = drawn(document)
    assert drawing.rows["kettle"] == 5
    assert drawing.rows["power"] == 6


def test_evolution_runs_left_to_right_through_the_twelve_places() -> None:
    """Every named place is further right than the one before it."""
    xs = []
    for place in WARDLEY_EVOLUTION:
        document = tea()
        component(document, "power")["evolution"] = place
        xs.append(drawn(document).centres["power"][0])
    assert xs == sorted(xs)
    assert len(set(xs)) == len(xs)


def test_two_components_on_one_place_and_row_sit_side_by_side() -> None:
    document = tea()
    component(document, "tea")["evolution"] = "commodity"
    drawing = drawn(document)
    (tea_x, tea_y), (water_x, water_y) = drawing.centres["tea"], drawing.centres["water"]
    assert tea_y == water_y
    assert tea_x < water_x  # in the order written


def test_no_line_passes_through_a_dot_it_does_not_join() -> None:
    """Three in a column: the middle one slides aside for the line past it."""
    document = {
        "version": 1,
        "kind": "wardley",
        "anchors": [{"id": "user", "text": "User", "needs": ["a"]}],
        "components": [
            {"id": "a", "text": "Alpha", "evolution": "product", "needs": ["b", "c"]},
            {"id": "b", "text": "Beta", "evolution": "product", "needs": ["c"]},
            {"id": "c", "text": "Gamma", "evolution": "product"},
        ],
    }
    drawing = drawn(document)
    centres = drawing.centres
    assert _distance(centres["b"], centres["a"], centres["c"]) > 4.5


def test_too_many_on_one_place_and_row_is_a_fiterror() -> None:
    needs = [f"c{index}" for index in range(5)]
    document = {
        "version": 1,
        "kind": "wardley",
        "anchors": [{"id": "user", "text": "User", "needs": needs}],
        "components": [{"id": ident, "text": ident, "evolution": "product"} for ident in needs],
    }
    with pytest.raises(FitError):
        render(document)


def test_evolution_arrow_and_inertia_are_drawn() -> None:
    document = tea()
    component(document, "kettle").update({"evolves": "product", "inertia": True})
    svg = render(document)
    assert 'stroke-dasharray="3 2"' in svg  # the ghost circle
    assert 'stroke-dasharray="4 3"' in svg  # the evolution arrow


def test_an_evolution_arrow_through_another_dot_is_a_fiterror() -> None:
    document = tea()
    component(document, "kettle")["evolution"] = "genesis"
    component(document, "kettle")["evolves"] = "commodity"
    document["components"].append({"id": "pot", "text": "Pot", "evolution": "product", "depth": 3})
    component(document, "water")["needs"].append("pot")
    with pytest.raises(FitError, match="through 'Pot'"):
        drawn(document)


def test_notes_are_numbered_beside_and_under_the_map() -> None:
    svg = render(tea(notes=[{"text": "Kettles are a commodity now.", "on": ["kettle"]}]))
    assert svg.count(">1<") == 2
    assert "Kettles are a commodity now." in svg


def test_the_stage_names_are_the_themes() -> None:
    theme = load_theme({"version": 1, "wardley": {"commodity": "Utility"}})
    svg = render(tea(), theme)
    assert "Utility" in svg
    assert "Commodity (+utility)" not in svg


def test_the_theme_refuses_two_stages_with_one_name() -> None:
    with pytest.raises(ThemeError):
        load_theme({"version": 1, "wardley": {"genesis": "New", "custom": "New"}})


def test_there_is_no_text_form() -> None:
    with pytest.raises(DrawspecError, match="no text form"):
        render_text(parse_document(tea()))


# -- the refusals -------------------------------------------------------------


@pytest.mark.parametrize("value", [0.4, "middling", "product-ish"])
def test_evolution_must_be_a_named_place(value: object) -> None:
    document = tea()
    component(document, "cup")["evolution"] = value
    found = refusals(document)
    assert "named place" in found["/components/0/evolution"]


def test_evolves_must_be_further_right() -> None:
    document = tea()
    component(document, "cup")["evolves"] = "custom"
    assert "further right" in refusals(document)["/components/0/evolves"]


def test_a_component_nothing_needs_is_refused() -> None:
    document = tea()
    document["components"].append({"id": "spare", "text": "Spare", "evolution": "genesis"})
    assert "no place in the value chain" in refusals(document)["/components/5"]


@pytest.mark.parametrize(
    ("need", "words"),
    [("customer", "is an anchor"), ("cup", "cannot need itself"), ("nowhere", "not the id")],
)
def test_needs_must_name_another_component(need: str, words: str) -> None:
    document = tea()
    component(document, "cup")["needs"].append(need)
    assert words in refusals(document)["/components/0/needs/2"]


def test_a_need_listed_twice_is_refused() -> None:
    document = tea()
    component(document, "cup")["needs"].append("tea")
    assert "twice" in refusals(document)["/components/0/needs/2"]


def test_a_loop_is_refused() -> None:
    document = tea()
    component(document, "power")["needs"] = ["water"]
    assert "loop" in refusals(document)["/components"]


def test_a_depth_above_what_needs_it_is_refused() -> None:
    document = tea()
    component(document, "power")["depth"] = 2
    assert "no higher than row 4" in refusals(document)["/components/4/depth"]


def test_a_chain_too_deep_is_refused() -> None:
    document = tea()
    component(document, "power")["depth"] = 9
    assert "rows deep" in refusals(document)["/components"]


def test_a_duplicate_id_is_refused() -> None:
    document = tea()
    component(document, "tea")["id"] = "cup"
    assert "used twice" in refusals(document)["/components/1/id"]


def test_a_name_on_two_lines_is_refused() -> None:
    document = tea()
    component(document, "tea")["text"] = "Tea\nleaves"
    assert "one line" in refusals(document)["/components/1/text"]


def test_a_note_on_an_unknown_id_is_refused() -> None:
    document = tea(notes=[{"text": "Hm.", "on": ["kettle", "ghost"]}])
    assert "not the id" in refusals(document)["/notes/0/on/1"]


@pytest.mark.parametrize(
    ("field", "value"),
    [("visibility", 0.8), ("maturity", 0.4), ("position", [1, 2]), ("x", 10)],
)
def test_coordinates_are_refused_with_a_reason(field: str, value: object) -> None:
    document = tea()
    component(document, "cup")[field] = value
    message = refusals(document)[f"/components/0/{field}"]
    assert "coordinate" in message or "derived" in message or "by name" in message


def test_edges_are_refused_for_needs() -> None:
    found = refusals(tea(edges=[{"from": "cup", "to": "tea"}]))
    assert "`needs`" in found["/edges"]


def test_the_component_budget_is_enforced() -> None:
    """A flat map, one past the budget: refused by the budget, at the first entry past it."""
    count = WARDLEY_COMPONENT_MAX + 1
    idents = [f"c{index}" for index in range(count)]
    document = {
        "version": 1,
        "kind": "wardley",
        "anchors": [{"id": "user", "text": "User", "needs": idents}],
        "components": [
            {"id": ident, "text": f"Part {ident}", "evolution": "product"} for ident in idents
        ],
    }
    found = refusals(document)
    assert f"/components/{WARDLEY_COMPONENT_MAX}" in found
    assert "past what one wardley can be read at" in found[f"/components/{WARDLEY_COMPONENT_MAX}"]

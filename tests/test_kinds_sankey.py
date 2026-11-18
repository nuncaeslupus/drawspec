"""`sankey` — where a known quantity goes, each flow a band as thick as its amount.

The kind makes three promises, each asserted numerically. One scale for the whole
drawing: every band's thickness over its amount is the same number. Conservation:
every bar is exactly as tall as the bands that leave it, and as the bands that
reach it, and those bands tile it without a gap or an overlap. And no word is
drawn on a band — the labels sit beside the outer columns' bars and above the
inner columns', where only straight bands pass.

Everything a sankey refuses because of its numbers — a loop, a middle node whose
inflow is not its outflow, a band too thin to see, a fifth column — is refused
while validating, at its pointer, so a refused document never waits on a layout.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from drawspec import render
from drawspec.errors import DocumentError, FitError
from drawspec.kinds.sankey import (
    FLOW_TINT,
    NOTE_TINT,
    STRONG_TINT,
    SankeyDrawing,
    sankey_drawing,
)
from drawspec.scene import Polygon, TextLine
from drawspec.schema import (
    SANKEY_BAND,
    SANKEY_MIN_BAND,
    parse_document,
    sankey_columns,
    validate_document,
)
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])
UNIT = THEME.scale["body"] / 11
REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "reference"
REFERENCES = sorted(REFERENCE.glob("sankey-*.json"))
EPSILON = 1e-6


def budget(**extra: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "version": 1,
        "kind": "sankey",
        "unit": "€ million",
        "nodes": [
            {"id": "tax", "text": "Local taxes"},
            {"id": "fees", "text": "Fees"},
            {"id": "budget", "text": "Budget", "role": "emphasis"},
            {"id": "staff", "text": "Staff"},
            {"id": "invest", "text": "Investment"},
            {"id": "debt", "text": "Debt service", "role": "note"},
        ],
        "flows": [
            {"from": "tax", "to": "budget", "amount": 80},
            {"from": "fees", "to": "budget", "amount": 20},
            {"from": "budget", "to": "staff", "amount": 50, "role": "strong"},
            {"from": "budget", "to": "invest", "amount": 35},
            {"from": "budget", "to": "debt", "amount": 15},
        ],
    }
    document.update(extra)
    return document


def drawn(document: dict[str, Any]) -> SankeyDrawing:
    return sankey_drawing(parse_document(document), THEME, MEASURER)


def messages(document: dict[str, Any]) -> dict[str, str]:
    return {violation.pointer: violation.message for violation in validate_document(document)}


def loaded(path: Path) -> dict[str, Any]:
    document: dict[str, Any] = json.loads(path.read_text())
    return document


def _segments_cross_rect(
    points: tuple[tuple[float, float], ...], rect: tuple[float, float, float, float]
) -> bool:
    """Whether any edge of the closed outline enters the rectangle's interior."""
    left, top, width, height = rect
    right, bottom = left + width, top + height
    for index, (x0, y0) in enumerate(points):
        x1, y1 = points[(index + 1) % len(points)]
        # Liang-Barsky against the rectangle shrunk by a hair.
        t0, t1 = 0.0, 1.0
        dx, dy = x1 - x0, y1 - y0
        inside = True
        for p, q in (
            (-dx, x0 - left - 0.5),
            (dx, right - 0.5 - x0),
            (-dy, y0 - top - 0.5),
            (dy, bottom - 0.5 - y0),
        ):
            if p == 0:
                if q < 0:
                    inside = False
                    break
                continue
            t = q / p
            if p < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
            if t0 > t1:
                inside = False
                break
        if inside:
            return True
    return False


def _contains(points: tuple[tuple[float, float], ...], x: float, y: float) -> bool:
    found = False
    for index, (x0, y0) in enumerate(points):
        x1, y1 = points[(index + 1) % len(points)]
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            found = not found
    return found


# ---------------------------------------------------------------------------
# The references
# ---------------------------------------------------------------------------


def test_there_are_at_least_three_references() -> None:
    assert len(REFERENCES) >= 3


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_every_band_is_drawn_at_one_scale(path: Path) -> None:
    """Thickness over amount is one number for the whole drawing — the kind's claim."""
    document = loaded(path)
    drawing = drawn(document)
    for index, flow in enumerate(document["flows"]):
        assert drawing.thickness[index] == pytest.approx(flow["amount"] * drawing.scale)


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_every_bar_is_as_tall_as_the_bands_it_holds_and_they_tile_it(path: Path) -> None:
    """Conservation, on the page: what leaves a bar and what reaches it each fill it exactly."""
    document = loaded(path)
    drawing = drawn(document)
    for node in document["nodes"]:
        _, top, _, height = drawing.bars[node["id"]]
        for side, end in (("from", 0), ("to", 1)):
            bands = sorted(
                (drawing.ends[index][end], drawing.thickness[index])
                for index, flow in enumerate(document["flows"])
                if flow[side] == node["id"]
            )
            if not bands:
                continue
            assert sum(thickness for _, thickness in bands) == pytest.approx(height)
            cursor = top
            for start, thickness in bands:
                assert start == pytest.approx(cursor)
                cursor = start + thickness
            assert cursor == pytest.approx(top + height)


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_no_label_is_drawn_on_a_band_or_on_another_label(path: Path) -> None:
    drawing = drawn(loaded(path))
    labels = list(drawing.labels.items())
    for name, rect in labels:
        left, top, width, height = rect
        for index, band in drawing.bands.items():
            assert not _segments_cross_rect(band, rect), (name, index)
            assert not _contains(band, left + width / 2, top + height / 2), (name, index)
        for other, (x, y, w, h) in labels:
            if other != name:
                apart = x >= left + width or left >= x + w or y >= top + height or top >= y + h
                assert apart, (name, other)


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_every_drawing_is_within_the_canvas(path: Path) -> None:
    drawing = drawn(loaded(path))
    assert drawing.scene.width <= THEME.canvas.width + EPSILON
    for left, top, width, height in drawing.labels.values():
        assert left >= -EPSILON and top >= -EPSILON
        assert left + width <= drawing.scene.width + EPSILON
        assert top + height <= drawing.scene.height + EPSILON


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_the_same_document_renders_to_the_same_bytes(path: Path) -> None:
    document = loaded(path)
    assert render(document) == render(document)


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------


def test_columns_are_derived_with_every_end_in_the_last_column() -> None:
    columns = sankey_columns(
        ["a", "b", "c", "end", "early"],
        [("a", "b"), ("b", "c"), ("c", "end"), ("a", "early")],
    )
    assert columns == {"a": 0, "b": 1, "c": 2, "end": 3, "early": 3}


def test_a_flow_that_skips_a_column_passes_through_it_without_crossing_a_bar() -> None:
    document = budget()
    document["nodes"].append({"id": "reserve", "text": "Reserve"})
    document["flows"].append({"from": "tax", "to": "reserve", "amount": 10})
    document["nodes"].insert(5, {"id": "audit", "text": "Audit"})
    document["flows"].append({"from": "staff", "to": "audit", "amount": 50})
    drawing = drawn(document)
    assert drawing.columns["reserve"] == 3
    assert ">5" in drawing.order[1] and ">5" in drawing.order[2]
    for name in ("budget", "staff"):
        left, top, width, height = drawing.bars[name]
        assert not _segments_cross_rect(drawing.bands[5], (left, top, width, height))


def test_the_crossing_reduction_untangles_a_written_order_that_crosses() -> None:
    document = {
        "version": 1,
        "kind": "sankey",
        "nodes": [
            {"id": "a", "text": "A"},
            {"id": "b", "text": "B"},
            {"id": "x", "text": "To B"},
            {"id": "y", "text": "To A"},
        ],
        "flows": [
            {"from": "a", "to": "y", "amount": 10},
            {"from": "b", "to": "x", "amount": 10},
        ],
    }
    drawing = drawn(document)
    assert drawing.order[1] == ("y", "x")


def test_the_written_order_stands_when_nothing_crosses() -> None:
    drawing = drawn(budget())
    assert drawing.order[0] == ("tax", "fees")
    assert drawing.order[2] == ("staff", "invest", "debt")


def test_the_fullest_column_sets_the_scale() -> None:
    drawing = drawn(budget())
    assert drawing.scale == pytest.approx(SANKEY_BAND * UNIT / 100)


def test_outgoing_bands_are_stacked_in_the_order_of_what_they_reach() -> None:
    drawing = drawn(budget())
    starts = [drawing.ends[index][0] for index in (2, 3, 4)]
    assert starts == sorted(starts)


def test_inner_labels_sit_above_their_bar_and_outer_labels_beside_it() -> None:
    drawing = drawn(budget())
    left, top, width, _ = drawing.bars["budget"]
    x, y, w, h = drawing.labels["budget"]
    assert y + h <= top + EPSILON
    assert x + w / 2 == pytest.approx(left + width / 2)
    tax_left = drawing.bars["tax"][0]
    assert drawing.labels["tax"][0] + drawing.labels["tax"][2] < tax_left
    staff_right = drawing.bars["staff"][0] + drawing.bars["staff"][2]
    assert drawing.labels["staff"][0] > staff_right


def test_each_total_is_written_under_its_words_unless_values_is_false() -> None:
    def words(document: dict[str, Any]) -> list[str]:
        scene = drawn(document).scene
        return [
            "".join(span.text for span in primitive.spans)
            for primitive in scene.primitives
            if isinstance(primitive, TextLine)
        ]

    assert "100 € million" in words(budget())
    assert "15 € million" in words(budget())
    assert not any("million" in line for line in words(budget(values=False)))


def test_roles_set_the_tints_and_the_emphasis_is_bold() -> None:
    scene = drawn(budget()).scene
    bands = [p for p in scene.primitives if isinstance(p, Polygon) and p.region]
    tints = sorted(band.fill_opacity for band in bands)
    assert tints == [NOTE_TINT, FLOW_TINT, FLOW_TINT, FLOW_TINT, STRONG_TINT]
    assert NOTE_TINT < FLOW_TINT < STRONG_TINT
    bars = {p.role for p in scene.primitives if isinstance(p, Polygon) and not p.region}
    assert bars == {"step", "emphasis", "note"}
    bold = [
        span.text
        for primitive in scene.primitives
        if isinstance(primitive, TextLine)
        for span in primitive.spans
        if span.weight == "bold"
    ]
    assert bold == ["Budget"]


def test_a_label_too_wide_for_every_width_is_refused_naming_the_node() -> None:
    document = budget(width=240)
    document["nodes"][0]["text"] = "Extraordinarilyunbreakablelocaltaxationrevenue"
    with pytest.raises(FitError, match="'tax'"):
        drawn(document)


def test_a_refusal_by_fit_reaches_render_quickly() -> None:
    """Every shrink of the type is tried before the refusal, and each try is cheap."""
    document = budget(width=240)
    document["nodes"][0]["text"] = "Extraordinarilyunbreakablelocaltaxationrevenue"
    started = time.perf_counter()
    with pytest.raises(FitError):
        render(document)
    assert time.perf_counter() - started < 1.0


def test_a_refusal_by_the_numbers_never_runs_a_layout() -> None:
    document = budget()
    document["flows"][0]["amount"] = 79
    started = time.perf_counter()
    with pytest.raises(DocumentError):
        render(document)
    assert time.perf_counter() - started < 0.2


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def test_the_examples_are_valid() -> None:
    for path in REFERENCES:
        assert validate_document(loaded(path)) == (), path.stem
    assert validate_document(budget()) == ()


def test_a_loop_is_refused_at_the_flow_that_closes_it() -> None:
    document = budget()
    document["flows"].append({"from": "staff", "to": "tax", "amount": 5})
    found = messages(document)
    assert "loop" in found["/flows/5"]


def test_a_middle_node_whose_inflow_is_not_its_outflow_is_refused_with_the_difference() -> None:
    document = budget()
    document["flows"][2]["amount"] = 48
    found = messages(document)
    assert "difference of 2 € million" in found["/nodes/2"]
    assert "Add a flow of 2 € million to a named node" in found["/nodes/2"]


def test_a_middle_node_sending_more_than_it_takes_says_where_it_came_from() -> None:
    document = budget()
    document["flows"][2]["amount"] = 53
    assert "came from" in messages(document)["/nodes/2"]


@pytest.mark.parametrize("amount", [0, -4])
def test_an_amount_of_zero_or_less_is_refused(amount: float) -> None:
    document = budget()
    document["flows"][0]["amount"] = amount
    assert "more than 0" in messages(document)["/flows/0/amount"]


def test_value_is_refused_naming_amount() -> None:
    document = budget()
    document["flows"][0]["value"] = document["flows"][0].pop("amount")
    assert "`amount`" in messages(document)["/flows/0/value"]


def test_a_band_too_thin_to_see_is_refused_with_the_merge() -> None:
    document = budget()
    document["flows"][3]["amount"] = 34.5
    document["flows"][4]["amount"] = 0.5
    document["flows"][1]["amount"] = 19
    document["flows"][0]["amount"] = 81
    found = messages(document)
    ratio = round(SANKEY_BAND / SANKEY_MIN_BAND)
    assert f"under 1/{ratio}" in found["/flows/4/amount"]
    assert "Merge the small flows" in found["/flows/4/amount"]


def test_a_fifth_column_is_refused() -> None:
    nodes = [{"id": f"n{i}", "text": f"Step {i}"} for i in range(6)]
    flows = [{"from": f"n{i}", "to": f"n{i + 1}", "amount": 5} for i in range(5)]
    found = messages({"version": 1, "kind": "sankey", "nodes": nodes, "flows": flows})
    assert "4 columns at most" in found["/nodes/4"]


def test_more_than_fourteen_nodes_is_past_the_budget() -> None:
    nodes = [{"id": "s", "text": "Source"}] + [
        {"id": f"n{i}", "text": f"End {i}"} for i in range(14)
    ]
    flows = [{"from": "s", "to": f"n{i}", "amount": 5} for i in range(14)]
    found = messages({"version": 1, "kind": "sankey", "nodes": nodes, "flows": flows})
    assert "past what one sankey can be read at" in found["/nodes/14"]


def test_an_unknown_node_is_refused_with_the_closest() -> None:
    document = budget()
    document["flows"][0]["to"] = "budgte"
    assert "did you mean 'budget'" in messages(document)["/flows/0/to"]


def test_a_flow_to_itself_is_refused() -> None:
    document = budget()
    document["flows"].append({"from": "staff", "to": "staff", "amount": 5})
    assert "to itself" in messages(document)["/flows/5/to"]


def test_a_second_flow_between_the_same_nodes_is_refused() -> None:
    document = budget()
    document["flows"].append({"from": "tax", "to": "budget", "amount": 5})
    assert "add the amounts" in messages(document)["/flows/5"]


def test_duplicate_node_ids_are_refused() -> None:
    document = budget()
    document["nodes"].append({"id": "staff", "text": "Staff again"})
    assert "duplicate node id" in messages(document)["/nodes/6/id"]


def test_a_node_no_flow_touches_is_refused() -> None:
    document = budget()
    document["nodes"].append({"id": "spare", "text": "Spare"})
    assert "bar of nothing" in messages(document)["/nodes/6"]


def test_one_node_is_refused() -> None:
    document = budget(nodes=[{"id": "tax", "text": "Taxes"}], flows=[])
    found = messages(document)
    assert "at least 2 nodes" in found["/nodes"]


@pytest.mark.parametrize(
    ("pointer", "field", "expected"),
    [
        ("", "edges", "`flows`"),
        ("/nodes/0", "column", "derived"),
        ("/nodes/0", "rank", "derived"),
        ("/flows/0", "percent", "Write the amount"),
        ("/flows/0", "label", "carries no words"),
        ("/flows/0", "fill", "role"),
    ],
)
def test_fields_a_sankey_has_no_place_for_are_refused_by_name(
    pointer: str, field: str, expected: str
) -> None:
    document = budget()
    target: Any = document
    for part in pointer.split("/")[1:]:
        target = target[int(part)] if isinstance(target, list) else target[part]
    target[field] = 1
    assert expected in messages(document)[f"{pointer}/{field}"]

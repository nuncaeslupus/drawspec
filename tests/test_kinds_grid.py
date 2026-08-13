"""T12 — grid kinds: stack, timeline, columns.

The gate is `same_rank_size_variance == 0`. These three kinds have no routing
problem and no layout engine: positions come from counting, which is why "peers
are the same size" can be an exact equality here rather than a normalisation that
happens to work out.

This is also the first task where a document becomes an SVG, so the end-to-end
path is asserted here too: parse, load the theme, fit, render, emit.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import replace
from itertools import pairwise
from xml.etree import ElementTree

import pytest

from drawspec import render
from drawspec.emit import check_embedding_safety
from drawspec.errors import DrawspecError, FitError
from drawspec.kinds import IMPLEMENTED, scene_for
from drawspec.kinds.common import line_bounds
from drawspec.kinds.grid import AXIS_ROLE, grid_scene
from drawspec.scene import Path, Polygon, Rect, Scene, TextLine
from drawspec.schema import KINDS, parse_document
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])

LAYERS = ("Interface", "Domain logic, which is where the rules of the thing live", "Storage")
MOMENTS = ("Brief", "Specification", "Plan", "Build", "Ship")


def document(kind: str, *texts: str, **extra: object) -> dict[str, object]:
    return {
        "version": 1,
        "kind": kind,
        "title": f"A {kind}",
        "items": [{"text": text} for text in texts],
        **extra,
    }


def scene(kind: str, *texts: str, **extra: object) -> Scene:
    return grid_scene(parse_document(document(kind, *texts, **extra)), THEME, MEASURER)


def rects(built: Scene) -> list[Rect]:
    return [item for item in built.primitives if isinstance(item, Rect)]


def paths(built: Scene) -> list[Path]:
    return [item for item in built.primitives if isinstance(item, Path)]


# --------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------


def test_stack_layers_are_equal_height_and_full_width() -> None:
    """A stack whose layers differ in height reads as a ranking of importance."""
    built = scene("stack", *LAYERS)
    layers = rects(built)
    assert len(layers) == len(LAYERS)
    assert len({round(layer.height, 6) for layer in layers}) == 1
    assert len({round(layer.width, 6) for layer in layers}) == 1
    assert all(layer.width == pytest.approx(built.width) for layer in layers)
    assert all(layer.x == 0.0 for layer in layers)


def test_columns_of_the_same_role_are_equal_width() -> None:
    built = scene("columns", "Before", "After", "Difference")
    columns = rects(built)
    assert len(columns) == 3
    assert len({round(column.width, 6) for column in columns}) == 1
    assert len({round(column.height, 6) for column in columns}) == 1


def test_timeline_ticks_are_evenly_spaced() -> None:
    """One step computed once, so the last tick lands exactly on the last centre."""
    built = scene("timeline", *MOMENTS)
    ticks = [path for path in paths(built) if path.points[0][0] == path.points[1][0]]
    assert len(ticks) == len(MOMENTS)
    centres = sorted(tick.points[0][0] for tick in ticks)
    gaps = [second - first for first, second in pairwise(centres)]
    assert len({round(gap, 6) for gap in gaps}) == 1


@pytest.mark.parametrize("kind", ["stack", "columns", "timeline"])
def test_peers_have_no_size_variance_at_all(kind: str) -> None:
    """`same_rank_size_variance == 0`, measured on the primitives themselves."""
    built = scene(kind, *MOMENTS)
    boxes = rects(built)
    assert len({(round(box.width, 6), round(box.height, 6)) for box in boxes}) == 1


# --------------------------------------------------------------------------
# stack
# --------------------------------------------------------------------------


def test_stack_layers_run_top_to_bottom_in_document_order() -> None:
    built = scene("stack", *LAYERS)
    layers = rects(built)
    assert [layer.y for layer in layers] == sorted(layer.y for layer in layers)
    texts = [item.text for item in built.primitives if isinstance(item, TextLine)]
    assert texts[0] == LAYERS[0]


def test_stack_layers_do_not_overlap_and_leave_a_gap() -> None:
    built = scene("stack", *LAYERS)
    for upper, lower in pairwise(rects(built)):
        assert lower.y >= upper.y + upper.height
        assert lower.y - (upper.y + upper.height) == pytest.approx(THEME.box.padding.top)


def test_stack_height_is_its_layers_plus_the_gaps_between_them() -> None:
    built = scene("stack", *LAYERS)
    layers = rects(built)
    expected = sum(layer.height for layer in layers) + THEME.box.padding.top * (len(layers) - 1)
    assert built.height == pytest.approx(expected)


def test_stack_of_one_layer_has_no_trailing_gap() -> None:
    built = scene("stack", "Only")
    assert built.height == pytest.approx(rects(built)[0].height)


def test_stack_respects_a_document_width_override() -> None:
    built = scene("stack", *LAYERS, width=480.0)
    assert built.width == 480.0
    assert all(layer.width == pytest.approx(480.0) for layer in rects(built))


# --------------------------------------------------------------------------
# columns
# --------------------------------------------------------------------------


def test_columns_are_side_by_side_with_a_gutter_and_no_overlap() -> None:
    built = scene("columns", "Before", "After", "Difference")
    columns = sorted(rects(built), key=lambda column: column.x)
    for left, right in pairwise(columns):
        gap = right.x - (left.x + left.width)
        assert gap == pytest.approx(THEME.box.padding.horizontal)


def test_columns_fill_the_canvas_width_exactly() -> None:
    built = scene("columns", "One", "Two", "Three", "Four")
    columns = sorted(rects(built), key=lambda column: column.x)
    assert columns[0].x == pytest.approx(0.0)
    assert columns[-1].x + columns[-1].width == pytest.approx(built.width)


def test_columns_of_one_item_take_the_whole_width() -> None:
    built = scene("columns", "Only")
    assert rects(built)[0].width == pytest.approx(built.width)


def test_too_many_columns_raises_fiterror_naming_the_remedies() -> None:
    with pytest.raises(FitError) as error:
        scene("columns", *[f"Column {index}" for index in range(30)])
    message = str(error.value)
    assert "30 columns" in message
    assert "fewer columns" in message


def test_columns_keep_a_role_the_author_chose() -> None:
    built = grid_scene(
        parse_document(
            {
                "version": 1,
                "kind": "columns",
                "items": [{"text": "Old", "role": "note"}, {"text": "New", "role": "emphasis"}],
            }
        ),
        THEME,
        MEASURER,
    )
    assert {rect.role for rect in rects(built)} == {"note", "emphasis"}


# --------------------------------------------------------------------------
# timeline
# --------------------------------------------------------------------------


def test_timeline_has_one_axis_running_the_full_width() -> None:
    built = scene("timeline", *MOMENTS)
    axes = [path for path in paths(built) if path.points[0][1] == path.points[1][1]]
    assert len(axes) == 1
    assert axes[0].points[0][0] == pytest.approx(0.0)
    assert axes[0].points[1][0] == pytest.approx(built.width)


def test_timeline_axis_is_a_plain_connector_with_no_head() -> None:
    """An axis has no direction, so it is named as a role rather than drawn as one."""
    built = scene("timeline", *MOMENTS)
    assert {path.role for path in paths(built)} == {AXIS_ROLE}
    assert THEME.edge_roles[AXIS_ROLE].has_head is False


def test_timeline_first_and_last_labels_sit_inside_the_canvas() -> None:
    built = scene("timeline", *MOMENTS)
    labels = sorted(rects(built), key=lambda label: label.x)
    assert labels[0].x >= -1e-9
    assert labels[-1].x + labels[-1].width <= built.width + 1e-9


def test_timeline_ticks_are_centred_on_their_labels() -> None:
    built = scene("timeline", *MOMENTS)
    ticks = sorted(
        (path for path in paths(built) if path.points[0][0] == path.points[1][0]),
        key=lambda path: path.points[0][0],
    )
    labels = sorted(rects(built), key=lambda label: label.x)
    for tick, label in zip(ticks, labels, strict=True):
        assert tick.points[0][0] == pytest.approx(label.x + label.width / 2)


def test_timeline_labels_sit_above_the_axis() -> None:
    built = scene("timeline", *MOMENTS)
    axis_y = next(path for path in paths(built) if path.points[0][1] == path.points[1][1]).points[
        0
    ][1]
    for label in rects(built):
        assert label.y + label.height <= axis_y + 1e-9


def test_timeline_of_one_moment_places_it_across_the_canvas() -> None:
    built = scene("timeline", "Now")
    assert rects(built)[0].width == pytest.approx(built.width)


def test_too_many_timeline_entries_raises_fiterror_suggesting_a_vertical_kind() -> None:
    with pytest.raises(FitError) as error:
        scene("timeline", *[f"Moment {index}" for index in range(40)])
    assert "stack" in str(error.value)


# --------------------------------------------------------------------------
# End to end: a document becomes an SVG
# --------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["stack", "columns", "timeline"])
@pytest.mark.parametrize("profile", ["inline", "standalone"])
def test_every_grid_kind_renders_to_safe_svg(kind: str, profile: str) -> None:
    svg = render(document(kind, *LAYERS), profile=profile)
    assert check_embedding_safety(svg, load_theme(), profile) == ()
    assert ElementTree.fromstring(svg) is not None


@pytest.mark.parametrize("kind", ["stack", "columns", "timeline"])
def test_every_grid_kind_renders_identically_twice(kind: str) -> None:
    """`nondeterministic_reruns == 0` for the path that exists so far."""
    first = render(document(kind, *LAYERS))
    second = render(document(kind, *LAYERS))
    assert first == second


def test_render_carries_the_documents_title_and_description() -> None:
    svg = render(document("stack", *LAYERS, description="What sits on what."))
    assert "<title" in svg and "A stack" in svg
    assert "What sits on what." in svg


def test_render_at_two_widths_produces_two_drawings() -> None:
    """One document, several widths, without editing it."""
    narrow = render(document("stack", *LAYERS, width=400.0))
    wide = render(document("stack", *LAYERS, width=800.0))
    assert _content_width(narrow) == pytest.approx(400.0)
    assert _content_width(wide) == pytest.approx(800.0)


def _content_width(svg: str) -> float:
    """The drawing's own width, from a layer that spans it."""
    return max(float(width) for width in re.findall(r'<rect[^>]* width="([\d.]+)"', svg))


def test_render_applies_the_elastic_fit_when_content_is_tight() -> None:
    """One factor for the whole diagram, or a refusal — never a per-element size.

    At 300 wide these three columns fit at full size; at 280 they need 0.9. Both
    render, and both use exactly one type size, because the factor is applied to
    the whole scale rather than to whichever element was too big.
    """
    words = ("Before", "Afterwards", "Difference")
    roomy = render(document("columns", *words, width=300.0))
    tight = render(document("columns", *words, width=280.0))

    def sizes(svg: str) -> set[float]:
        return {float(size) for size in re.findall(r'font-size="([\d.]+)"', svg)}

    body = load_theme().scale["body"]
    assert sizes(roomy) == {body}
    assert len(sizes(tight)) == 1
    assert max(sizes(tight)) < body


def test_render_refuses_rather_than_shrinking_past_the_band() -> None:
    """Below `scale_min` the answer is restructure, not a smaller size."""
    with pytest.raises(FitError, match="restructure"):
        render(document("columns", "Before", "Afterwards", "Difference", width=260.0))


def test_every_kind_the_schema_accepts_now_has_a_family() -> None:
    """T11 was the last one. A document that parses is a document that draws."""
    assert set(KINDS) == set(IMPLEMENTED)


def test_scene_for_refuses_a_kind_it_has_no_family_for() -> None:
    """Unreachable through the parser, and still the dispatch's job to say so.

    Built by hand rather than parsed, because the schema's kind vocabulary is
    closed: this is the guard that a *new* kind added to the vocabulary without a
    family fails by name instead of falling through to something odd.
    """
    parsed = parse_document(document("stack", *LAYERS))
    with pytest.raises(DrawspecError, match="cannot render it yet"):
        scene_for(replace(parsed, kind="constellation"), THEME, MEASURER)


def test_scene_for_dispatches_on_the_documents_kind() -> None:
    built = scene_for(parse_document(document("stack", *LAYERS)), THEME, MEASURER)
    assert built.primitives
    assert built.title == "A stack"


def test_grid_scene_refuses_a_kind_from_another_family() -> None:
    parsed = parse_document(
        {"version": 1, "kind": "pyramid", "levels": [{"text": "Top"}, {"text": "Base"}]}
    )
    with pytest.raises(DrawspecError, match="not a grid kind"):
        grid_scene(parsed, THEME, MEASURER)


@pytest.mark.parametrize("kind", ["stack", "columns", "timeline"])
def test_no_text_escapes_its_box_in_any_grid_kind(kind: str) -> None:
    """`text_overflow_count == 0`, measured on the emitted primitives.

    Every text run must start inside its own box and end inside it, measured with
    the same measurer that sized the box.
    """
    built = scene(kind, *LAYERS)
    boxes = rects(built)
    runs = [item for item in built.primitives if isinstance(item, TextLine)]
    assert runs
    for run in runs:
        left, right = line_bounds(run, THEME, MEASURER)
        inside = [
            box for box in boxes if box.x - 1e-6 <= left and right <= box.x + box.width + 1e-6
        ]
        assert inside, f"{run.text!r} at {left} is not inside any box"


def test_every_timeline_tick_touches_its_own_label() -> None:
    """A tick beside the axis leaves the reader to pair labels with marks by eye.

    The mark said *a moment happened somewhere along here*; which label it
    belonged to was a guess from proximity. Running it from the label's own
    bottom edge to the axis makes the pairing the drawing's claim rather than the
    reader's inference.
    """
    built = scene("timeline", *MOMENTS)
    labels = rects(built)
    ticks = [line for line in paths(built) if line.points[0][0] == line.points[1][0]]
    assert len(ticks) == len(labels)
    for tick in ticks:
        x = tick.points[0][0]
        top = min(point[1] for point in tick.points)
        owner = [
            box
            for box in labels
            if box.x - 1e-6 <= x <= box.x + box.width + 1e-6 and top <= box.y + box.height + 1e-6
        ]
        assert owner, f"the tick at {x} starts below every label"


# --------------------------------------------------------------------------
# matrix
# --------------------------------------------------------------------------


def matrix(cells: list[dict[str, object]], **extra: object) -> Scene:
    document = {
        "version": 1,
        "kind": "matrix",
        "title": "A matrix",
        "cells": cells,
        **extra,
    }
    return grid_scene(parse_document(document), THEME, MEASURER)


SHARED: list[dict[str, object]] = [
    {"text": "The customer", "column": 0, "row": 0, "group": "customer"},
    {"text": "The provider", "column": 0, "row": 1},
    {"text": "The customer", "column": 1, "row": 0, "group": "customer"},
    {"text": "The provider", "column": 1, "row": 1},
]


def cells_of(built: Scene) -> list[Polygon]:
    return [item for item in built.primitives if isinstance(item, Polygon)]


def test_a_matrix_draws_one_figure_per_cell() -> None:
    assert len(cells_of(matrix(SHARED))) == len(SHARED)


def test_matrix_columns_are_equal() -> None:
    """The family's rule: peers are the same size, by construction."""
    widths = {
        round(max(x for x, _ in cell.points) - min(x for x, _ in cell.points), 6)
        for cell in cells_of(matrix(SHARED))
    }
    assert len(widths) == 1


def test_matrix_cells_meet_without_a_gap_or_an_overlap() -> None:
    """A table's cells share their edges; a gap reads as separate diagrams."""
    built = matrix(SHARED)
    lefts = sorted({round(min(x for x, _ in cell.points), 6) for cell in cells_of(built)})
    rights = sorted({round(max(x for x, _ in cell.points), 6) for cell in cells_of(built)})
    assert lefts[1:] == rights[:-1]


def test_a_spanning_cell_covers_the_rows_it_claims() -> None:
    built = matrix(
        [
            {"text": "One", "column": 0, "row": 0},
            {"text": "Two", "column": 0, "row": 1},
            {"text": "Both", "column": 1, "row": 0, "down": 2},
        ]
    )
    cells = cells_of(built)
    tall = max(
        cells, key=lambda cell: max(y for _, y in cell.points) - min(y for _, y in cell.points)
    )
    short = [cell for cell in cells if cell is not tall and min(x for x, _ in cell.points) == 0.0]
    covered = sum(max(y for _, y in cell.points) - min(y for _, y in cell.points) for cell in short)
    height = max(y for _, y in tall.points) - min(y for _, y in tall.points)
    assert height == pytest.approx(covered)


def test_a_spanning_cell_does_not_deepen_every_row_it_passes() -> None:
    """It needs the rows together, not each of them as deep as itself."""
    plain = matrix(
        [
            {"text": "One", "column": 0, "row": 0},
            {"text": "Two", "column": 0, "row": 1},
        ]
    )
    spanned = matrix(
        [
            {"text": "One", "column": 0, "row": 0},
            {"text": "Two", "column": 0, "row": 1},
            {"text": "Both", "column": 1, "row": 0, "down": 2},
        ]
    )
    assert spanned.height == pytest.approx(plain.height)


def test_a_cell_names_its_group_and_the_theme_picks_the_fill() -> None:
    """Never by colour, and never by the author naming an appearance."""
    fills = {cell.fill for cell in cells_of(matrix(SHARED))}
    assert fills == {THEME.mark.fill_for(0), ""}


def test_two_cells_in_one_square_are_refused() -> None:
    """A document that means two things at once, drawn one on top of the other."""
    with pytest.raises(DrawspecError) as error:
        matrix(
            [
                {"text": "One", "column": 0, "row": 0},
                {"text": "Two", "column": 0, "row": 0},
            ]
        )
    assert "One" in str(error.value) and "Two" in str(error.value)


def test_a_cell_before_the_first_square_is_refused() -> None:
    """The far side needs no check — the matrix grows to fit. This side cannot."""
    with pytest.raises(DrawspecError) as error:
        matrix([{"text": "One", "column": -1, "row": 0}])
    assert "column -1" in str(error.value)


def test_a_cell_spanning_more_columns_makes_a_wider_matrix() -> None:
    """The extent is derived from the cells, which is why there is no upper check."""
    built = matrix([{"text": "One", "column": 0, "row": 0, "across": 3}])
    (cell,) = cells_of(built)
    assert max(x for x, _ in cell.points) == pytest.approx(built.width)


def test_matrix_headings_are_set_at_the_same_level_as_its_cells() -> None:
    """One type size on a page, still."""
    built = matrix(SHARED, columns=["A", "B"], rows=["First", "Second"])
    levels = {item.level for item in built.primitives if isinstance(item, TextLine)}
    assert levels == {"body"}


def test_row_headings_take_width_from_the_grid_rather_than_overlapping_it() -> None:
    built = matrix(SHARED, rows=["First", "Second"])
    plain = matrix(SHARED)
    assert min(min(x for x, _ in cell.points) for cell in cells_of(built)) > 0.0
    assert built.width == pytest.approx(plain.width)


# --------------------------------------------------------------------------
# timeline: spacing by when things happened
# --------------------------------------------------------------------------


def timeline(*items: Mapping[str, object]) -> Scene:
    document = {
        "version": 1,
        "kind": "timeline",
        "title": "A timeline",
        "items": list(items),
    }
    return grid_scene(parse_document(document), THEME, MEASURER)


def tick_positions(built: Scene) -> list[float]:
    """Where each tick meets the axis, left to right."""
    ticks = [
        line
        for line in built.primitives
        if isinstance(line, Path) and line.points[0][0] == line.points[-1][0]
    ]
    return sorted(line.points[0][0] for line in ticks)


UNEVEN: tuple[Mapping[str, object], ...] = (
    {"text": "First", "at": 0},
    {"text": "Second", "at": 4},
    {"text": "Third", "at": 24},
)


def test_a_timeline_without_placements_is_evenly_spaced() -> None:
    """The default, unchanged: even spacing is what this kind has always meant."""
    built = timeline({"text": "First"}, {"text": "Second"}, {"text": "Third"})
    positions = tick_positions(built)
    gaps = [later - earlier for earlier, later in pairwise(positions)]
    assert gaps[0] == pytest.approx(gaps[1])


def test_a_placed_timeline_spaces_by_when_things_happened() -> None:
    """The gaps then say something a reader can see."""
    positions = tick_positions(timeline(*UNEVEN))
    gaps = [later - earlier for earlier, later in pairwise(positions)]
    assert gaps[1] > gaps[0] * 4


def test_placements_are_in_proportion_to_their_own_values() -> None:
    positions = tick_positions(timeline(*UNEVEN))
    span = positions[-1] - positions[0]
    assert (positions[1] - positions[0]) / span == pytest.approx(4 / 24, abs=0.01)


def test_two_placed_labels_never_touch() -> None:
    """The closest pair decides how wide a label may be, and it keeps daylight."""
    built = timeline(*UNEVEN)
    boxes = sorted(
        (item for item in built.primitives if isinstance(item, Rect)),
        key=lambda box: box.x,
    )
    for earlier, later in pairwise(boxes):
        assert earlier.x + earlier.width < later.x


def test_a_timeline_placing_only_some_of_its_entries_spaces_evenly() -> None:
    """All or nothing: otherwise a reader measures one gap and counts the next."""
    positions = tick_positions(
        timeline({"text": "First", "at": 0}, {"text": "Second"}, {"text": "Third", "at": 20})
    )
    gaps = [later - earlier for earlier, later in pairwise(positions)]
    assert gaps[0] == pytest.approx(gaps[1])


def test_a_timeline_with_every_entry_at_one_point_is_refused() -> None:
    """There is nothing for the spacing to say, and drawing it would say it anyway."""
    with pytest.raises(FitError) as error:
        timeline({"text": "First", "at": 3}, {"text": "Second", "at": 3})
    assert "same point" in str(error.value)

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
from dataclasses import replace
from itertools import pairwise
from xml.etree import ElementTree

import pytest

from drawspec import render
from drawspec.emit import check_embedding_safety
from drawspec.errors import DrawspecError, FitError
from drawspec.kinds import IMPLEMENTED, scene_for
from drawspec.kinds.grid import AXIS_ROLE, grid_scene
from drawspec.scene import Path, Rect, Scene, TextRun
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
    texts = [item.text for item in built.primitives if isinstance(item, TextRun)]
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
    runs = [item for item in built.primitives if isinstance(item, TextRun)]
    assert runs
    for run in runs:
        width = MEASURER.measure(run.text, run.font, THEME.scale[run.level]).width
        inside = [
            box
            for box in boxes
            if box.x - 1e-6 <= run.x and run.x + width <= box.x + box.width + 1e-6
        ]
        assert inside, f"{run.text!r} at {run.x} is not inside any box"

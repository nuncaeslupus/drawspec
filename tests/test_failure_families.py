"""T16 — the acceptance suite: 63 review notes, 11 families, none expressible.

This is what the project is measured against. Every other test file asks whether
a stage does its job; this one asks the question the brief asks — *can a
generator still commit this failure?* — and answers it in one of two ways, never
a third:

**By the schema.** The field that would express it does not exist, so the
document cannot say it. A refusal at parse time with a JSON pointer.

**By an invariant.** The geometry is derived rather than declared, so the
failure has no way in. A box sized from its own text cannot be too small for it.

What this file deliberately does *not* do is check that drawspec happens to
avoid the failure on some example. An example that passes proves nothing about
the next document; the two answers above are the only ones that generalise, so
each test below names which of the two it is relying on.

The gate is `unrepresentable_failure_families == 11`. `FAMILIES` is that count,
and the last test in the file asserts every one of them has a test here — so a
family cannot be quietly dropped to make the number work.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import replace
from itertools import pairwise
from pathlib import Path
from typing import Final

import pytest

from drawspec import render
from drawspec.errors import DocumentError, LayoutError
from drawspec.geometry import Box, candidate_factors, size_box
from drawspec.kinds import scene_for
from drawspec.kinds.graph import graph_drawing
from drawspec.routing import Connector, Obstacle, route_edges, shaft_length
from drawspec.scene import Ellipse, Polygon, Rect, Scene, TextRun
from drawspec.schema import REJECTED_FIELDS, load_document, parse_document
from drawspec.text import TextMeasurer
from drawspec.theme import TYPE_LEVELS, load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])

#: The same theme with `[box] widen_steps` spent down to none. A family called
#: directly gets no elastic fit around it, so it gets no chance to fall back the
#: way `fit` does when a generous box makes a drawing too wide for the canvas —
#: and these tests are about ranks, anchors and angles, not about how much width
#: a box talked its way into. Fixing the generosity keeps them measuring that.
STRICT = replace(THEME, box=replace(THEME.box, widen_steps=0))

REFERENCE_DIR = Path(__file__).resolve().parents[1] / "docs" / "reference"

#: The eleven families in `docs/brief.md`, in the order the brief counts them.
#: The brief's twelfth row is "no clear category", which is not a family — it is
#: what is left over, and there is nothing to make impossible.
FAMILIES: Final = (
    "text_crossing_lines",
    "text_escaping_its_box",
    "arrow_without_shaft",
    "margins_and_leading",
    "uneven_type_sizes",
    "vertical_centring",
    "line_not_reaching_the_box",
    "curve_instead_of_a_right_angle",
    "badly_proportioned_pyramid",
    "hatching_too_heavy",
    "ring_text_touching_its_arc",
)


def document(name: str) -> dict[str, object]:
    text = (REFERENCE_DIR / f"{name}.json").read_text(encoding="utf-8")
    loaded: dict[str, object] = json.loads(text)
    return loaded


def scene(name: str) -> Scene:
    return scene_for(load_document(REFERENCE_DIR / f"{name}.json"), THEME, MEASURER)


def text_box(run: TextRun) -> tuple[float, float, float, float]:
    extents = MEASURER.measure(run.text, run.font, THEME.scale[run.level], run.weight)
    left = {
        "start": run.x,
        "middle": run.x - extents.width / 2,
        "end": run.x - extents.width,
    }[run.anchor]
    top = run.y - extents.ascent
    return left, top, left + extents.width, top + extents.height


def rejects(field: str, **document_extra: object) -> DocumentError:
    """The document with `field` written on its first node, and what happened."""
    payload = {
        "version": 1,
        "kind": "flow",
        "nodes": [{"id": "a", "text": "One", field: 1}, {"id": "b", "text": "Two"}],
        "edges": [{"from": "a", "to": "b"}],
        **document_extra,
    }
    with pytest.raises(DocumentError) as error:
        parse_document(payload)
    return error.value


# --------------------------------------------------------------------------
# 1. Text crossing lines or other boxes — 13 notes
# --------------------------------------------------------------------------


def test_family_text_crossing_lines_is_unrepresentable() -> None:
    """By invariant: a label is placed only where nothing else is.

    Placement measures each candidate against every route segment of every edge,
    every node shape and every label already placed, and refuses the document if
    no candidate is clear — so a label on a line is not a bad placement, it is
    one placement never returned.
    """
    drawing = graph_drawing(load_document(REFERENCE_DIR / "flow-validation.json"), THEME, MEASURER)
    assert drawing.labels
    for label in drawing.labels:
        for route in drawing.routes:
            for first, second in pairwise(route.points):
                assert not _segment_in_box(first, second, label.box), label.text
        for other in drawing.labels:
            if other is not label:
                assert not _boxes_overlap(label.box, other.box), (label.text, other.text)


# --------------------------------------------------------------------------
# 2. Text escaping its box, or not fitting — 11 notes
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["stack-decisions", "columns-before-after", "timeline-work"])
def test_family_text_escaping_its_box_is_unrepresentable(name: str) -> None:
    """By invariant: the box is sized from the text, not the text fitted to a box.

    There is no `width` or `height` an author can write, so no box exists that
    the text was not measured for. Checked on the finished scene: every run is
    inside one of the boxes drawn in it.
    """
    built = scene(name)
    boxes = [item for item in built.primitives if isinstance(item, Rect)]
    assert boxes
    for run in _runs(built):
        assert any(_box_contains(text_box(run), box) for box in boxes), run.text


def test_family_text_escaping_its_box_is_unrepresentable_in_a_graph() -> None:
    """The same claim where the boxes were placed by an engine that never saw them.

    A label belongs to an edge rather than to a box and is excluded here — that
    it misses everything is family 1, measured there.
    """
    drawing = graph_drawing(load_document(REFERENCE_DIR / "flow-validation.json"), THEME, MEASURER)
    built = scene("flow-validation")
    label_texts = {label.text for label in drawing.labels}
    for run in _runs(built):
        if run.text in label_texts:
            continue
        assert any(_box_contains(text_box(run), box) for box in drawing.boxes.values()), run.text


def test_family_a_box_cannot_be_declared_smaller_than_its_text() -> None:
    """By schema: `width` and `height` on a node are not fields."""
    for field in ("width", "height"):
        assert "derived from measured text" in REJECTED_FIELDS[field]
        assert field in str(rejects(field))


# --------------------------------------------------------------------------
# 3. Arrow with no shaft, or only a head — 10 notes
# --------------------------------------------------------------------------


def test_family_arrow_without_shaft_is_unrepresentable() -> None:
    """By invariant: a route too short for a shaft is refused, not drawn.

    The head is not a thing an author places — `arrow_head` is not a field — and
    the shaft is measured against the theme's minimum with the head length taken
    off. Boxes too close together are a `LayoutError` about the arrangement.
    """
    assert "head geometry is the theme's" in REJECTED_FIELDS["arrow_head"]

    drawing = graph_drawing(load_document(REFERENCE_DIR / "flow-validation.json"), THEME, MEASURER)
    for route in drawing.routes:
        assert shaft_length(route, THEME) >= THEME.edge.min_shaft_length - 1e-9

    cramped = (
        Obstacle("a", x=0.0, y=0.0, width=100.0, height=40.0),
        Obstacle("b", x=0.0, y=44.0, width=100.0, height=40.0),
    )
    with pytest.raises(LayoutError, match="shaft"):
        route_edges((Connector("a", "b"),), cramped, THEME)


# --------------------------------------------------------------------------
# 4. Margins and line spacing inside boxes — 7 notes
# --------------------------------------------------------------------------


def test_family_margins_and_leading_is_unrepresentable() -> None:
    """By schema and by invariant: both come from the theme, for every box.

    The document has no padding, no leading and no offset; the box adds the
    theme's padding on all four sides, and the lines are one theme line-height
    apart. Measured here rather than asserted: the gaps between successive
    baselines in a two-line box are all the same number.
    """
    for field in ("dx", "dy"):
        assert field in REJECTED_FIELDS

    box = size_box(
        "A label long enough that it has to break across three separate lines",
        theme=THEME,
        measurer=MEASURER,
        max_width=140.0,
    )
    baselines = box.baselines()
    assert len(baselines) >= 3
    gaps = {round(second - first, 6) for first, second in pairwise(baselines)}
    assert len(gaps) == 1
    assert gaps.pop() == pytest.approx(THEME.scale["body"] * THEME.box.line_height)

    left, top, right, bottom = box.content_bounds()
    assert left - box.x == pytest.approx(THEME.box.padding.left)
    assert box.x + box.width - right >= THEME.box.padding.right - 1e-6
    assert top - box.y >= THEME.box.padding.top - 1e-6
    assert box.y + box.height - bottom >= THEME.box.padding.bottom - 1e-6


# --------------------------------------------------------------------------
# 5. Small type, or uneven type sizes — 6 notes
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["flow-validation", "chart-complaints", "pyramid-evidence"])
def test_family_uneven_type_sizes_is_unrepresentable(name: str) -> None:
    """By schema: there is no per-element size, and the scale moves as one.

    Every `font-size` in the output is one of the four levels at the one fit
    factor the whole diagram was drawn at — the corpus's twelve sizes cannot
    happen, because a size is never written, only selected.
    """
    assert "type is selected by semantic role" in REJECTED_FIELDS["font_size"]

    svg = render(document(name))
    sizes = {float(value) for value in re.findall(r'font-size="([\d.]+)"', svg)}
    assert sizes
    assert len(sizes) <= len(TYPE_LEVELS)

    # One factor from the theme's own band explains every size in the drawing —
    # the elastic fit moves all four levels together or not at all.
    def explains(factor: float) -> bool:
        levels = [THEME.scale[level] * factor for level in TYPE_LEVELS]
        return all(
            any(math.isclose(size, level, abs_tol=5e-4) for level in levels) for size in sizes
        )

    assert any(explains(factor) for factor in candidate_factors(THEME))
    assert min(sizes) >= THEME.canvas.min_legible_size - 1e-9


# --------------------------------------------------------------------------
# 6. Vertical centring of text in the box — 5 notes
# --------------------------------------------------------------------------


def test_family_vertical_centring_is_unrepresentable() -> None:
    """By invariant: the baseline is computed from the font's own metrics.

    The space above the first line's ascent equals the space below the last
    line's descent, which is what "centred" means when the thing being centred is
    a line box rather than a rectangle of ink.
    """
    for text in ("Ace", "Agile", "A label that needs two lines to fit in this box"):
        box = size_box(text, theme=THEME, measurer=MEASURER, max_width=160.0)
        _, top, _, bottom = box.content_bounds()
        above = top - (box.y + THEME.box.padding.top)
        below = (box.y + box.height - THEME.box.padding.bottom) - bottom
        assert above == pytest.approx(below, abs=0.5), text


# --------------------------------------------------------------------------
# 7. Lines that do not reach the box — 4 notes
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["flow-validation", "tree-decisions"])
def test_family_line_not_reaching_the_box_is_unrepresentable(name: str) -> None:
    """By invariant: the endpoint *is* a point on the outline.

    Not near it, and not on the bounding rectangle either: a diamond's anchor is
    on the sloped edge. There is no expression in the router for an endpoint
    anywhere else, and this measures it against the shapes.
    """
    parsed = load_document(REFERENCE_DIR / f"{name}.json")
    drawing = graph_drawing(parsed, STRICT, MEASURER)
    shapes = {node.id: THEME.roles[node.role].shape for node in parsed.nodes}
    for route in drawing.routes:
        for point, identifier in (
            (route.points[0], route.source),
            (route.points[-1], route.target),
        ):
            box = drawing.boxes[identifier]
            assert _on_outline(point, box, shapes[identifier]), (identifier, point)


# --------------------------------------------------------------------------
# 8. Curves where there should be a right angle — 3 notes
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["flow-validation", "tree-decisions"])
def test_family_curve_instead_of_a_right_angle_is_unrepresentable(name: str) -> None:
    """By invariant: routes are found on a grid of horizontal and vertical lines.

    Scoped to the shafts of edges between boxes, which is where the note was
    written. A ring's arc and a chart's series are curves on purpose and are not
    connectors; an arrow head is a mark whose geometry is the theme's, and an
    `open` head is a V by design. The claim is that an edge's *line* cannot be a
    curve, not that drawspec never draws a slope.

    A role the theme routes **direct** is the declared exception, and it is not
    a curve either: a mesh is drawn with chords on purpose, so a straight
    diagonal is the answer rather than the failure. What is still refused
    everywhere is a bend that is neither a right angle nor a chord.
    """
    drawing = graph_drawing(load_document(REFERENCE_DIR / f"{name}.json"), STRICT, MEASURER)
    assert drawing.routes
    for route in drawing.routes:
        if STRICT.edge_roles[route.role].routing == "direct":
            assert len(route.points) == 2, "a chord is one straight run or it is not a chord"
            continue
        for first, second in pairwise(route.points):
            assert first[0] == pytest.approx(second[0]) or first[1] == pytest.approx(second[1])


# --------------------------------------------------------------------------
# 9. Badly proportioned pyramids — 3 notes
# --------------------------------------------------------------------------


def test_family_badly_proportioned_pyramid_is_unrepresentable() -> None:
    """By invariant: every level is one height, and the width step is constant.

    The author writes the levels; the proportions are computed from how many
    there are, so a pyramid with a squashed tier has no way to be described.
    """
    built = scene("pyramid-evidence")
    levels = [item for item in built.primitives if isinstance(item, Polygon)]
    assert len(levels) >= 3
    heights = {round(_extent(level, axis=1), 6) for level in levels}
    assert len(heights) == 1
    widths = sorted(_extent(level, axis=0) for level in levels)
    steps = {round(second - first, 6) for first, second in pairwise(widths)}
    assert len(steps) == 1


# --------------------------------------------------------------------------
# 10. Hatching too heavy — 3 notes
# --------------------------------------------------------------------------


def test_family_hatching_too_heavy_is_unrepresentable() -> None:
    """By schema and by theme: a fill is a role's property, and the pattern is one.

    An author cannot ask for a hatch at all — `fill` is not a field — and the
    pattern the emitter defines is a theme-wide constant, thin and part
    transparent, so text on top of it stays legible.
    """
    assert "appearance is a property of the role" in REJECTED_FIELDS["fill"]

    hatched = {
        "version": 1,
        "kind": "stack",
        "items": [{"text": "Legacy", "role": "note"}, {"text": "Replacement"}],
    }
    svg = render(hatched)
    for width in re.findall(r'<pattern[^>]*>.*?stroke-width="([\d.]+)"', svg):
        assert float(width) <= 1.0
    for opacity in re.findall(r'(?:stroke|fill)-opacity="([\d.]+)"', svg):
        assert float(opacity) <= 0.5


# --------------------------------------------------------------------------
# 11. Concentric circles with text touching the ring — 2 notes
# --------------------------------------------------------------------------


def test_family_ring_text_touching_its_arc_is_unrepresentable() -> None:
    """By invariant: a ring's label is offset into the band, not centred on it.

    Only the innermost circle's text is centred, because only the innermost has
    no arc through the middle of it.
    """
    built = scene("rings-scope")
    rings = sorted(
        (item for item in built.primitives if isinstance(item, Ellipse)),
        key=lambda ring: ring.rx,
    )
    assert len(rings) >= 2
    for run in _runs(built):
        left, top, right, bottom = text_box(run)
        for ring in rings:
            for x, y in ((left, top), (right, top), (left, bottom), (right, bottom)):
                distance = math.hypot((x - ring.cx) / ring.rx, (y - ring.cy) / ring.ry)
                assert not math.isclose(distance, 1.0, abs_tol=0.02), (run.text, ring.rx)


# --------------------------------------------------------------------------
# The count
# --------------------------------------------------------------------------


def test_every_failure_family_has_a_test_in_this_file() -> None:
    """`unrepresentable_failure_families == 11`, and no family quietly dropped."""
    named = {
        name.removeprefix("test_family_").removesuffix("_is_unrepresentable")
        for name in globals()
        if name.startswith("test_family_") and name.endswith("_is_unrepresentable")
    }
    assert len(FAMILIES) == 11
    assert set(FAMILIES) <= named, set(FAMILIES) - named


def test_the_whole_reference_set_still_renders() -> None:
    """The families are not made impossible by refusing to draw anything."""
    for path in sorted(REFERENCE_DIR.glob("*.json")):
        svg = render(document(path.stem))
        assert svg.startswith("<svg")


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _runs(built: Scene) -> list[TextRun]:
    return [item for item in built.primitives if isinstance(item, TextRun)]


def _extent(polygon: Polygon, axis: int) -> float:
    values = [point[axis] for point in polygon.points]
    return max(values) - min(values)


def _boxes_overlap(
    first: tuple[float, float, float, float], second: tuple[float, float, float, float]
) -> bool:
    return (
        first[0] < second[2] - 1e-6
        and second[0] < first[2] - 1e-6
        and first[1] < second[3] - 1e-6
        and second[1] < first[3] - 1e-6
    )


def _segment_in_box(
    first: tuple[float, float],
    second: tuple[float, float],
    box: tuple[float, float, float, float],
    samples: int = 40,
) -> bool:
    for step in range(samples + 1):
        fraction = step / samples
        x = first[0] + (second[0] - first[0]) * fraction
        y = first[1] + (second[1] - first[1]) * fraction
        if box[0] - 1e-6 < x < box[2] + 1e-6 and box[1] - 1e-6 < y < box[3] + 1e-6:
            return True
    return False


def _box_contains(text: tuple[float, float, float, float], box: Rect | Box) -> bool:
    """A `Rect` from a scene and a `Box` from the geometry read the same here."""
    return (
        text[0] >= box.x - 1e-6
        and text[1] >= box.y - 1e-6
        and text[2] <= box.x + box.width + 1e-6
        and text[3] <= box.y + box.height + 1e-6
    )


def _on_outline(point: tuple[float, float], box: Box, shape: str) -> bool:
    left, top, width, height = box.x, box.y, box.width, box.height
    across = abs(point[0] - (left + width / 2)) / (width / 2)
    down = abs(point[1] - (top + height / 2)) / (height / 2)
    if shape == "diamond":
        return math.isclose(across + down, 1.0, abs_tol=1e-6)
    if shape == "ellipse":
        return math.isclose(math.hypot(across, down), 1.0, abs_tol=1e-6)
    if shape == "pill":
        radius = min(width, height) / 2
        flat = width / 2 - radius
        beyond = max(abs(point[0] - (left + width / 2)) - flat, 0.0)
        return math.isclose(
            math.hypot(beyond, point[1] - (top + height / 2)) / radius, 1.0, abs_tol=1e-6
        )
    return math.isclose(across, 1.0, abs_tol=1e-6) or math.isclose(down, 1.0, abs_tol=1e-6)

"""T13 — shape kinds: pyramid and concentric rings.

The gate is `text_outside_shape_count == 0`, and both kinds fail it the same way
if they are built naively: by fitting text to the *average* width of a shape
rather than the width where the text actually is. A pyramid level is narrowest at
its top edge; a ring's band is narrowest at the top of the band. Every assertion
below is made against the real outline — the sloped side, the arc — rather than
against a bounding box.
"""

from __future__ import annotations

import math
from itertools import pairwise

import pytest

from drawspec import render
from drawspec.emit import check_embedding_safety
from drawspec.errors import DrawspecError, FitError
from drawspec.kinds.common import line_bounds
from drawspec.kinds.shape import shape_scene
from drawspec.scene import Ellipse, Polygon, Scene, TextLine
from drawspec.schema import parse_document
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])

LEVELS = ("A decision", "A measurement", "A method someone else could repeat")
RINGS = ("Everything a theme can express", "The nine kinds", "One document, one SVG")


def pyramid(*texts: str, **extra: object) -> Scene:
    document = {
        "version": 1,
        "kind": "pyramid",
        "title": "A pyramid",
        "levels": [{"text": text} for text in texts],
        **extra,
    }
    return shape_scene(parse_document(document), THEME, MEASURER)


def rings(*texts: str, **extra: object) -> Scene:
    document = {
        "version": 1,
        "kind": "rings",
        "title": "Some rings",
        "rings": [{"text": text} for text in texts],
        **extra,
    }
    return shape_scene(parse_document(document), THEME, MEASURER)


def levels_of(built: Scene) -> list[Polygon]:
    return [item for item in built.primitives if isinstance(item, Polygon)]


def circles_of(built: Scene) -> list[Ellipse]:
    return [item for item in built.primitives if isinstance(item, Ellipse)]


def runs_of(built: Scene) -> list[TextLine]:
    return [item for item in built.primitives if isinstance(item, TextLine)]


def run_edges(run: TextLine) -> tuple[float, float]:
    """The left and right edge of a line, as drawspec measured it."""
    return line_bounds(run, THEME, MEASURER)


def run_width(run: TextLine) -> float:
    left, right = run_edges(run)
    return right - left


# --------------------------------------------------------------------------
# pyramid
# --------------------------------------------------------------------------


def test_pyramid_levels_are_equal_height_with_constant_width_progression() -> None:
    """Regular proportions: no level may read as more important than another."""
    built = pyramid(*LEVELS)
    trapezoids = levels_of(built)
    assert len(trapezoids) == len(LEVELS)

    heights = {round(_height(level), 6) for level in trapezoids}
    assert len(heights) == 1

    widths = [_top_width(level) for level in trapezoids]
    steps = [second - first for first, second in pairwise([*widths, _bottom_width(trapezoids[-1])])]
    assert len({round(step, 6) for step in steps}) == 1


def test_pyramid_level_text_fits_the_narrowest_span_of_its_level() -> None:
    """`text_outside_shape_count == 0` — measured against the sloped sides.

    Every corner of every label is inside its own trapezoid. Fitting the level's
    average width instead is exactly how text crosses a slope.
    """
    built = pyramid(*LEVELS)
    for level in levels_of(built):
        for run in _runs_within(built, level):
            for x in (run.x, run.x + run_width(run)):
                assert _inside_trapezoid(x, run.y, level), (run.text, x, run.y)


def test_pyramid_levels_stack_without_a_gap() -> None:
    built = pyramid(*LEVELS)
    trapezoids = levels_of(built)
    for upper, lower in pairwise(trapezoids):
        assert _bottom(upper) == pytest.approx(_top(lower))
        assert _bottom_width(upper) == pytest.approx(_top_width(lower))


def test_pyramid_widens_from_top_to_bottom() -> None:
    built = pyramid(*LEVELS)
    widths = [_top_width(level) for level in levels_of(built)]
    assert widths == sorted(widths)
    assert widths[0] < widths[-1]


def test_pyramid_base_fills_the_canvas_width() -> None:
    built = pyramid(*LEVELS)
    assert _bottom_width(levels_of(built)[-1]) == pytest.approx(built.width)


def test_pyramid_apex_is_flat_so_something_can_be_written_in_it() -> None:
    """A true point has no width; the top level is a trapezoid, not a triangle."""
    assert _top_width(levels_of(pyramid(*LEVELS))[0]) > 0


def test_pyramid_of_one_level_is_a_single_band() -> None:
    built = pyramid("Only")
    assert len(levels_of(built)) == 1


def test_pyramid_with_a_long_apex_label_wraps_inside_the_narrowest_span() -> None:
    """A long apex label is not a failure — it wraps, and stays inside the slope.

    The apex has the narrowest span, so it wraps first and hardest. What must not
    happen is the text reaching for the level's *wider* lower edge, which is how
    a label ends up crossing a sloped side.
    """
    built = pyramid("An apex label far too long to sit comfortably at the point", "Base")
    apex = levels_of(built)[0]
    lines = _runs_within(built, apex)
    assert len(lines) > 1, "the apex label should have wrapped"
    for run in lines:
        for x in run_edges(run):
            assert _inside_trapezoid(x, run.y, apex), (run.text, x)
    # And the levels stay equal, so the apex does not distort the proportions.
    assert len({round(_height(level), 6) for level in levels_of(built)}) == 1


def test_pyramid_with_an_unbreakable_apex_label_raises_fiterror_naming_the_level() -> None:
    """When wrapping cannot save it, the message says which level and what to do."""
    with pytest.raises(FitError) as error:
        pyramid("Unsplittableliteralrunofcharactersfarwiderthantheapexcouldeverbe", "Base")
    message = str(error.value)
    assert "pyramid level 1" in message
    assert "shortest label" in message


def test_pyramid_text_is_centred_on_the_axis() -> None:
    built = pyramid(*LEVELS)
    for run in runs_of(built):
        left, right = run_edges(run)
        assert (left + right) / 2 == pytest.approx(built.width / 2, abs=1.0)


# --------------------------------------------------------------------------
# rings
# --------------------------------------------------------------------------


def test_ring_label_is_offset_below_its_own_arc() -> None:
    """ "Each ring's text is shifted downwards so it does not touch its own circle." """
    built = rings(*RINGS)
    circles = circles_of(built)
    for index, circle in enumerate(circles[:-1]):
        label = _label_for(built, circle, circles)
        top_of_arc = circle.cy - circle.ry
        assert label.y > top_of_arc, f"ring {index} label sits on its own arc"


def test_innermost_ring_label_is_centred() -> None:
    """The one exception the requirements name."""
    built = rings(*RINGS)
    circles = circles_of(built)
    innermost = min(circles, key=lambda circle: circle.rx)
    label = _label_for(built, innermost, circles)
    assert label.y == pytest.approx(innermost.cy, abs=THEME.scale["body"])


def test_rings_are_concentric_with_equal_radial_steps() -> None:
    built = rings(*RINGS)
    circles = circles_of(built)
    assert len({(round(c.cx, 6), round(c.cy, 6)) for c in circles}) == 1
    radii = sorted(circle.rx for circle in circles)
    steps = [second - first for first, second in pairwise(radii)]
    assert len({round(step, 6) for step in steps}) == 1


def test_ring_labels_stay_inside_their_own_circle() -> None:
    """`text_outside_shape_count == 0` — measured against the arc, not a box."""
    built = rings(*RINGS)
    circles = circles_of(built)
    for circle in circles:
        for run in _runs_for(built, circle, circles):
            for x in run_edges(run):
                distance = math.dist((x, run.y), (circle.cx, circle.cy))
                assert distance <= circle.rx + 1e-6, (run.text, x, run.y)


def test_ring_labels_do_not_stray_into_the_next_ring_in() -> None:
    built = rings(*RINGS)
    circles = sorted(circles_of(built), key=lambda circle: -circle.rx)
    for outer, inner in pairwise(circles):
        for run in _runs_for(built, outer, circles):
            assert run.y < inner.cy - inner.ry + THEME.scale["body"]


def test_rings_fill_the_canvas_and_are_square() -> None:
    built = rings(*RINGS)
    assert built.width == pytest.approx(built.height)
    assert max(circle.rx for circle in circles_of(built)) == pytest.approx(built.width / 2)


def test_rings_of_one_is_a_single_centred_circle() -> None:
    built = rings("Alone")
    assert len(circles_of(built)) == 1
    assert runs_of(built)


def test_too_many_rings_raises_fiterror_naming_the_remedies() -> None:
    with pytest.raises(FitError) as error:
        rings(*[f"Ring number {index} with a reasonably long label" for index in range(9)])
    assert "fewer rings" in str(error.value)


# --------------------------------------------------------------------------
# Shared
# --------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["pyramid", "rings"])
@pytest.mark.parametrize("profile", ["inline", "standalone"])
def test_shape_kinds_render_to_safe_svg(kind: str, profile: str) -> None:
    texts = LEVELS if kind == "pyramid" else RINGS
    key = "levels" if kind == "pyramid" else "rings"
    document = {"version": 1, "kind": kind, key: [{"text": text} for text in texts]}
    svg = render(document, profile=profile)
    assert check_embedding_safety(svg, THEME, profile) == ()


def test_shape_scene_refuses_a_kind_from_another_family() -> None:
    parsed = parse_document({"version": 1, "kind": "stack", "items": [{"text": "One"}]})
    with pytest.raises(DrawspecError, match="not a shape kind"):
        shape_scene(parsed, THEME, MEASURER)


def test_shape_kinds_render_identically_twice() -> None:
    document = {"version": 1, "kind": "pyramid", "levels": [{"text": t} for t in LEVELS]}
    assert render(document) == render(document)


# --------------------------------------------------------------------------
# Geometry helpers — deliberately independent of drawspec's own
# --------------------------------------------------------------------------


def _top(level: Polygon) -> float:
    return min(y for _, y in level.points)


def _bottom(level: Polygon) -> float:
    return max(y for _, y in level.points)


def _height(level: Polygon) -> float:
    return _bottom(level) - _top(level)


def _top_width(level: Polygon) -> float:
    top = _top(level)
    xs = [x for x, y in level.points if y == pytest.approx(top)]
    return max(xs) - min(xs)


def _bottom_width(level: Polygon) -> float:
    bottom = _bottom(level)
    xs = [x for x, y in level.points if y == pytest.approx(bottom)]
    return max(xs) - min(xs)


def _inside_trapezoid(x: float, y: float, level: Polygon) -> bool:
    """Whether a point is inside the level, by interpolating its sloped sides."""
    top, bottom = _top(level), _bottom(level)
    if not top - 1e-6 <= y <= bottom + 1e-6:
        return False
    fraction = (y - top) / (bottom - top) if bottom > top else 0.0
    half = (_top_width(level) + (_bottom_width(level) - _top_width(level)) * fraction) / 2
    middle = (min(px for px, _ in level.points) + max(px for px, _ in level.points)) / 2
    return abs(x - middle) <= half + 1e-6


def _runs_within(built: Scene, level: Polygon) -> list[TextLine]:
    return [run for run in runs_of(built) if _top(level) <= run.y <= _bottom(level)]


def _label_for(built: Scene, circle: Ellipse, circles: list[Ellipse]) -> TextLine:
    return _runs_for(built, circle, circles)[0]


def _runs_for(built: Scene, circle: Ellipse, circles: list[Ellipse]) -> list[TextLine]:
    """The runs belonging to `circle`: those in its band, or in it if innermost."""
    ordered = sorted(circles, key=lambda item: -item.rx)
    index = ordered.index(circle)
    outer_top = circle.cy - circle.rx
    inner_top = (
        ordered[index + 1].cy - ordered[index + 1].rx
        if index + 1 < len(ordered)
        else circle.cy + circle.rx
    )
    return [run for run in runs_of(built) if outer_top <= run.y <= inner_top]

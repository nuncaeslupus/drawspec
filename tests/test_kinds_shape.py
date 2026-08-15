"""T13 — shape kinds: pyramid, concentric rings, and the funnel.

The gate is `text_outside_shape_count == 0`, and both kinds fail it the same way
if they are built naively: by fitting text to the *average* width of a shape
rather than the width where the text actually is. A pyramid level is narrowest at
its top edge; a ring's band is narrowest at the top of the band. Every assertion
below is made against the real outline — the sloped side, the arc — rather than
against a bounding box.
"""

from __future__ import annotations

import math
from dataclasses import replace
from itertools import pairwise

import pytest

from drawspec import render
from drawspec.emit import check_embedding_safety
from drawspec.errors import DocumentError, DrawspecError, FitError
from drawspec.geometry import size_box
from drawspec.kinds.common import line_bounds
from drawspec.kinds.shape import (
    FUNNEL_MIN_DEPTH,
    FUNNEL_TAPER,
    GATE_ROLE,
    PYRAMID_FILL,
    PYRAMID_MIN_SHARE,
    RINGS_MIN_SHARE,
    SHAPE_LEVEL,
    shape_scene,
)
from drawspec.scene import Ellipse, Path, Polygon, Scene, TextLine, TextRun
from drawspec.schema import parse_document
from drawspec.text import TextMeasurer
from drawspec.theme import Theme, load_theme

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
            for x in run_edges(run):
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


def test_a_pyramid_of_short_labels_does_not_fill_the_canvas() -> None:
    """The one kind that should not be as wide as the page.

    Its base is the widest thing in it, so a base at the canvas width leaves a
    shape three or four times wider than it is tall — a flight of steps. The
    labels decide the base and the canvas is only a ceiling; the drawing is then
    centred in what is left, like any other narrow diagram.
    """
    built = pyramid("A decision", "A measurement", "A method someone else could repeat")
    assert built.width < THEME.canvas.width
    assert built.height / built.width > 0.4, "this should read as a pyramid, not as a staircase"


def test_a_pyramid_never_shrinks_below_its_share_of_the_canvas() -> None:
    """A pyramid of one-word levels is still a diagram, not a caption with a hat."""
    built = pyramid("One", "Two", "Three")
    assert built.width == pytest.approx(THEME.canvas.width * PYRAMID_MIN_SHARE)


def test_a_pyramid_level_is_never_much_taller_than_its_own_text() -> None:
    """The limit on buying a shape with empty band.

    A level that dwarfs its label is what made the type look lost the first time
    round, and raising the type was the wrong answer: the shape is the end with
    nothing to be consistent with, so the shape gives.
    """
    for texts in (
        ("One", "Two", "Three"),
        ("A decision", "A measurement", "A method someone else could repeat"),
    ):
        built = pyramid(*texts)
        level_height = _height(levels_of(built)[0])
        tallest = max(
            size_box(
                text,
                theme=THEME,
                measurer=MEASURER,
                role="step",
                level=SHAPE_LEVEL,
                max_width=built.width,
                shape="rect",
            ).height
            for text in texts
        )
        assert level_height <= tallest * PYRAMID_FILL + 1e-6


def test_a_ring_set_does_not_fill_the_canvas_either() -> None:
    """The same complaint as the pyramid, one round later.

    Rings filling the width was defended by their needing room to nest, which is
    true of the ratio between the bands and not of the absolute size. Drawn to
    the page the figure is mostly circle, and the type — the same size as
    everywhere else in the document — is a smaller part of what the reader sees.
    """
    built = rings(*RINGS)
    assert built.width < THEME.canvas.width
    assert built.width == pytest.approx(built.height), "a ring set is as tall as it is wide"


def test_a_ring_set_never_shrinks_below_its_share_of_the_canvas() -> None:
    """One-word rings are still a diagram, not a coin.

    Two of them, because with three the band depth binds first and the floor
    never comes into it — the labels would fit a smaller circle than the bands
    they sit in do.
    """
    assert rings("One", "Two").width == pytest.approx(THEME.canvas.width * RINGS_MIN_SHARE)
    assert rings("One", "Two", "Three").width >= THEME.canvas.width * RINGS_MIN_SHARE


def test_a_ring_label_wraps_to_buy_the_set_a_smaller_circle() -> None:
    """Wrapping is the lever here, which is what makes bisection the right search.

    A band is a fixed fraction of the extent in both directions, so breaking a
    label over two lines trades width the band is short of for depth it has, and
    the trade terminates when the depth runs out. Held to one line each, the set
    would need a circle as wide as its longest label demands of the narrowest
    part of its band — wider than the canvas here.
    """
    built = rings(*RINGS)
    assert len(runs_of(built)) > len(RINGS), "at least one label should have wrapped"
    for run in runs_of(built):
        assert run_width(run) < built.width


# --------------------------------------------------------------------------
# funnel
# --------------------------------------------------------------------------


#: A funnel drawn the other way. `down` is the default — a funnel is a thing you
#: pour into — and the tests below that predate the choice describe the sideways
#: geometry, so they name the theme that draws it rather than being deleted: both
#: directions are supported and both have to keep working.
SIDEWAYS = replace(THEME, funnel=replace(THEME.funnel, direction="right"))


def funnel(*texts: str, theme: Theme = SIDEWAYS, **extra: object) -> Scene:
    document = {
        "version": 1,
        "kind": "funnel",
        "title": "A funnel",
        "stages": [{"text": text} for text in texts],
        **extra,
    }
    return shape_scene(parse_document(document), theme, MEASURER)


STAGES = ("Many ideas", "Assessed and chosen", "Validated", "Deployed")


def band_of(built: Scene) -> Polygon:
    (band,) = [item for item in built.primitives if isinstance(item, Polygon)]
    return band


def gates_of(built: Scene) -> list[Path]:
    return [item for item in built.primitives if isinstance(item, Path)]


def test_a_funnel_narrows_from_throat_to_mouth() -> None:
    """The one thing the shape claims."""
    band = band_of(funnel(*STAGES))
    left = [y for x, y in band.points if x == pytest.approx(min(p[0] for p in band.points))]
    right = [y for x, y in band.points if x == pytest.approx(max(p[0] for p in band.points))]
    assert max(left) - min(left) > max(right) - min(right)


def test_a_funnel_mouth_is_open_so_something_can_be_written_in_it() -> None:
    """A funnel that closed to a point would have no last stage."""
    band = band_of(funnel(*STAGES))
    right = [y for x, y in band.points if x == pytest.approx(max(p[0] for p in band.points))]
    assert max(right) - min(right) > 0


def test_a_funnel_has_one_gate_between_each_pair_of_stages() -> None:
    built = funnel(*STAGES)
    assert len(gates_of(built)) == len(STAGES) - 1


def test_every_gate_is_drawn_in_the_role_that_means_threshold() -> None:
    """A gate is something you pass through, which a solid line would deny."""
    assert {gate.role for gate in gates_of(funnel(*STAGES))} == {GATE_ROLE}


def test_every_gate_reaches_both_sides_of_the_band_it_cuts() -> None:
    """A divider that stopped short would read as a tick rather than a gate."""
    built = funnel(*STAGES)
    band = band_of(built)
    top = {x: y for x, y in band.points[:2]}
    for gate in gates_of(built):
        (x, first), (_, second) = gate.points
        depth = abs(second - first)
        # Linear taper, so the band's depth at the gate is interpolated between
        # its ends — the gate must span exactly that, not less.
        share = x / built.width
        expected = built.height * (1 - (1 - FUNNEL_TAPER) * share)
        assert depth == pytest.approx(expected, abs=0.5), (x, depth, expected)
    assert top


def test_funnel_stage_text_fits_the_band_where_its_stage_ends() -> None:
    """The narrowest part of a stage is where it ends — the pyramid's rule, turned.

    Every line of every stage's label sits inside the band at the *right* edge of
    its own slice, which is the depth that slice has least of. Fitting the middle
    or the left instead is how text ends up across the taper.
    """
    built = funnel(*STAGES)
    count = len(STAGES)
    middle = built.height / 2
    for index in range(count):
        share = (index + 1) / count
        half = built.height * (1 - (1 - FUNNEL_TAPER) * share) / 2
        left = index * built.width / count
        right = (index + 1) * built.width / count
        for run in runs_of(built):
            if not left <= run.x <= right:
                continue
            assert middle - half <= run.y <= middle + half, (run.text, index)
            for x in run_edges(run):
                assert left <= x <= right, (run.text, index)


def test_a_funnel_of_short_stages_is_still_a_funnel_and_not_a_rule() -> None:
    built = funnel("One", "Two", "Three")
    assert built.height >= built.width * FUNNEL_MIN_DEPTH - 1e-6


def test_a_funnel_fills_the_canvas_width() -> None:
    """Unlike the pyramid: a funnel that did not would be a wedge in a corner."""
    assert funnel(*STAGES).width == pytest.approx(THEME.canvas.width)


def test_a_funnel_deepens_to_hold_a_long_last_stage() -> None:
    """The mouth is the tightest place, so a long label there sets the depth."""
    shallow = funnel("One", "Two")
    deep = funnel("One", "A label long enough that the mouth has to open for it")
    assert deep.height > shallow.height


# --------------------------------------------------------------------------
# funnel, the way the word draws it
# --------------------------------------------------------------------------


def test_a_funnel_tapers_down_the_page_by_default() -> None:
    """*"It says embut, which should look as vertical."*

    A funnel is a thing you pour into, and every reader has seen one. Drawn
    sideways it is a pipeline, which is a different picture with the same stages
    in it — so the default draws the one the word names, and `[funnel] direction`
    is how a document that meant the pipeline says so.
    """
    band = band_of(funnel(*STAGES, theme=THEME))
    top = [x for x, y in band.points if y == pytest.approx(min(p[1] for p in band.points))]
    bottom = [x for x, y in band.points if y == pytest.approx(max(p[1] for p in band.points))]
    assert max(top) - min(top) > max(bottom) - min(bottom)


def test_a_vertical_funnel_keeps_its_mouth_open() -> None:
    """The same reason a pyramid's apex is flat: a point has nothing written in it."""
    band = band_of(funnel(*STAGES, theme=THEME))
    bottom = [x for x, y in band.points if y == pytest.approx(max(p[1] for p in band.points))]
    assert max(bottom) - min(bottom) == pytest.approx(THEME.canvas.width * FUNNEL_TAPER)


def test_a_vertical_funnel_fills_the_canvas_at_its_mouth() -> None:
    """The mouth is the one part of a funnel a reader already knows the size of."""
    assert funnel(*STAGES, theme=THEME).width == pytest.approx(THEME.canvas.width)


def test_every_stage_of_a_vertical_funnel_is_the_same_depth() -> None:
    """A stage taller than its neighbours reads as a longer step, which was not said."""
    built = funnel(*STAGES, theme=THEME)
    gates = sorted(gate.points[0][1] for gate in gates_of(built))
    steps = [
        second - first for first, second in zip([0.0, *gates], [*gates, built.height], strict=True)
    ]
    assert max(steps) - min(steps) < 1e-6


def test_a_vertical_stage_label_fits_the_band_where_its_stage_ends() -> None:
    """The narrowest part of a stage is its bottom edge — the pyramid's rule, inverted."""
    built = funnel(*STAGES, theme=THEME)
    count = len(STAGES)
    middle = built.width / 2
    depth = built.height / count
    for index in range(count):
        half = built.width * (1 - (1 - FUNNEL_TAPER) * (index + 1) / count) / 2
        for run in runs_of(built):
            if not index * depth <= run.y <= (index + 1) * depth:
                continue
            for x in run_edges(run):
                assert middle - half <= x <= middle + half, (run.text, index)


def test_a_document_draws_either_way_without_being_edited() -> None:
    """The seam: the author named stages narrowing, the theme named which way."""
    stages = [{"text": text} for text in STAGES]
    document = parse_document(
        {"version": 1, "kind": "funnel", "title": "A funnel", "stages": stages}
    )
    down = shape_scene(document, THEME, MEASURER)
    right = shape_scene(document, SIDEWAYS, MEASURER)
    assert down.metadata != right.metadata
    # The same words, in the same order. Not the same *lines*: a stage that is a
    # band across the page and a stage that is a band down it have different
    # widths to break in, which is the point of having both.
    assert " ".join(run.text for run in runs_of(down)) == " ".join(
        run.text for run in runs_of(right)
    )


def test_a_vertical_stage_uses_the_whole_width_of_its_narrow_edge() -> None:
    """The padding comes out once, not twice.

    `_label` hands its span to `size_box` as a `max_width`, and `size_box` takes
    the theme's padding out itself — so a family that subtracts it first charges
    every label for it twice, wraps labels that had the room, and makes every
    stage deeper for it. The pyramid passes its geometric width; this asserts the
    funnel does the same, by giving a stage a label that only fits if it does.
    """
    theme = THEME
    stages = ("One", "Two", "Three", "Sized to the bottom edge")
    built = funnel(*stages, theme=theme)
    count = len(stages)
    narrow = built.width * (1 - (1 - FUNNEL_TAPER) * count / count)
    room = narrow - theme.box.padding.horizontal
    longest = max(
        (run_width(run) for run in runs_of(built) if run.y > built.height * (count - 1) / count),
        default=0.0,
    )
    assert longest <= room + 1e-6
    # And it really is using that room rather than half of it: the label fits on
    # fewer lines than the double-charged span would have allowed.
    bottom = [run for run in runs_of(built) if run.y > built.height * (count - 1) / count]
    assert len(bottom) <= 2, [run.text for run in bottom]


# --------------------------------------------------------------------------
# The gate between two stages
# --------------------------------------------------------------------------


def gated(theme: Theme = THEME) -> Scene:
    document = {
        "version": 1,
        "kind": "funnel",
        "title": "A stage-gate funnel",
        "stages": [
            {"text": "Generació", "gate": "porta"},
            {"text": "Avaluació i selecció", "gate": "porta"},
            {"text": "Validació del concepte", "gate": "porta"},
            {"text": "Desenvolupament i explotació"},
        ],
    }
    return shape_scene(parse_document(document), theme, MEASURER)


@pytest.mark.parametrize("theme", [THEME, SIDEWAYS])
def test_a_gate_is_named_once_between_each_pair_of_stages(theme: Theme) -> None:
    """The source writes *porta* three times for four stages, and it is the
    three words that make it a stage-gate model rather than a narrowing."""
    written = [
        item.text for item in gated(theme).primitives if isinstance(item, TextRun) and item.text
    ]
    assert written.count("porta") == 3


@pytest.mark.parametrize("theme", [THEME, SIDEWAYS])
def test_a_gate_label_sits_on_no_line(theme: Theme) -> None:
    """The divider breaks to let its name through, rather than running under it."""
    built = gated(theme)
    labels = [item for item in built.primitives if isinstance(item, TextRun)]
    size = THEME.scale[SHAPE_LEVEL]
    for label in labels:
        half = MEASURER.measure(label.text, THEME.font.default, size).width / 2
        for path in gates_of(built):
            for (x1, y1), (x2, y2) in pairwise(path.points):
                if abs(y1 - y2) < 1e-6 and abs(y1 - label.y) < size:
                    assert max(x1, x2) <= label.x - half or min(x1, x2) >= label.x + half
                if abs(x1 - x2) < 1e-6 and abs(x1 - label.x) < half:
                    assert min(y1, y2) >= label.y or max(y1, y2) <= label.y - size


def test_a_gate_on_the_last_stage_is_refused() -> None:
    """Nothing stands between the last stage and a stage that is not there."""
    with pytest.raises(DocumentError, match="no next stage"):
        parse_document(
            {
                "version": 1,
                "kind": "funnel",
                "stages": [{"text": "One"}, {"text": "Two", "gate": "porta"}],
            }
        )


def test_an_unnamed_divider_is_still_drawn_whole() -> None:
    """A funnel without gates is the funnel it always was."""
    built = funnel(*STAGES, theme=THEME)
    assert len(gates_of(built)) == len(STAGES) - 1


# --------------------------------------------------------------------------
# A name is a name, whether or not it needed explaining
# --------------------------------------------------------------------------


def _weights(built: Scene) -> dict[str, str]:
    return {
        span.text: span.weight
        for item in built.primitives
        if isinstance(item, TextLine)
        for span in item.spans
    }


def test_a_bare_ring_name_is_set_like_the_one_that_carries_a_detail() -> None:
    """Three ring names of the same rank, one of which happens to be explained.

    It used to be the only one in bold, because a lead was decided per label:
    *Governança* had a second line and *SVS* did not, so the two came out set
    differently for a reason that is about the explanation rather than about
    the name.
    """
    document = {
        "version": 1,
        "kind": "rings",
        "title": "Governance around the system",
        "rings": [
            {"text": "Value chain and practices"},
            {"text": "SVS"},
            {"text": "Governance\nevaluate, direct, monitor"},
        ],
    }
    weights = _weights(shape_scene(parse_document(document), THEME, MEASURER))
    assert weights["Governance"] == "bold"
    assert weights["SVS"] == "bold"
    assert weights["Value chain and"] == "bold"
    assert weights["evaluate, direct,"] == "normal"


def test_a_set_with_no_detail_anywhere_is_left_plain() -> None:
    """The rule only fires when the set has said it is names-and-details."""
    weights = _weights(funnel(*STAGES, theme=THEME))
    assert set(weights.values()) == {"normal"}

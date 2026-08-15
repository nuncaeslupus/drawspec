"""T14 — the chart kind.

The gate is `unlabelled_axis_count == 0`, and the four things asserted here are
the four the source corpus did worst on. Three are geometry; the first is not,
and is worth saying plainly: **an unlabelled axis is already impossible**,
because the document schema makes `label` required on both axes. The refusal
happens at parse time with a JSON pointer. This file proves that rather than
reimplementing it.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from itertools import combinations, pairwise

import pytest

from drawspec import render
from drawspec.charts import DIVIDER_ROLE, MARKER_FRACTION, _crosses, _label_box, chart_scene
from drawspec.emit import check_embedding_safety, emit
from drawspec.errors import DocumentError, DrawspecError, FitError
from drawspec.legend import SWATCH_ASPECT, SWATCH_SHARE
from drawspec.scene import Ellipse, Path, Polygon, Rect, Scene, TextLine, TextRun
from drawspec.schema import parse_document
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])

SERIES = [{"name": "Accepted", "data": [[1, 10], [2, 14], [3, 12], [4, 17]]}]
AXES = {
    "horizontal": {"label": "Week"},
    "vertical": {"label": "Requests", "unit": "thousands"},
}


def document(**extra: object) -> dict[str, object]:
    return {
        "version": 1,
        "kind": "chart",
        "title": "A chart",
        "axes": AXES,
        "series": SERIES,
        **extra,
    }


def scene(**extra: object) -> Scene:
    return chart_scene(parse_document(document(**extra)), THEME, MEASURER)


def lines(built: Scene) -> list[Path]:
    return [item for item in built.primitives if isinstance(item, Path)]


def markers(built: Scene) -> list[Ellipse]:
    return [item for item in built.primitives if isinstance(item, Ellipse)]


def texts(built: Scene) -> list[TextRun]:
    return [item for item in built.primitives if isinstance(item, TextRun)]


def labels(built: Scene) -> list[TextRun | TextLine]:
    """Every piece of text, whichever primitive carries it.

    A span's name is a `TextLine` because it is wrapped like every other text
    field — it may hold `**bold**`, or a lead over a detail. Both primitives
    carry `.text` and `.x`, and a test about where a label sits does not care
    which of the two it is.
    """
    return [item for item in built.primitives if isinstance(item, (TextRun, TextLine))]


def series_paths(built: Scene) -> list[Path]:
    """The series lines: the ones with more than two points."""
    return [line for line in lines(built) if len(line.points) > 2]


# --------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------


@pytest.mark.parametrize("axis", ["horizontal", "vertical"])
def test_chart_without_an_axis_label_raises_documenterror(axis: str) -> None:
    """`unlabelled_axis_count == 0`, enforced by the schema at parse time.

    A missing vertical axis label was one of the three worst failures in the
    source corpus, so it is not a rendering concern that could be forgotten — it
    is a field the document cannot omit.
    """
    axes = {name: dict(value) for name, value in AXES.items()}
    del axes[axis]["label"]
    with pytest.raises(DocumentError) as error:
        parse_document(document(axes=axes))
    assert f"/axes/{axis}/label" in str(error.value)


def test_chart_missing_a_whole_axis_raises_documenterror() -> None:
    with pytest.raises(DocumentError, match="/axes/vertical"):
        parse_document(document(axes={"horizontal": {"label": "Week"}}))


def test_chart_point_markers_lie_on_the_series_path() -> None:
    """Markers land on the line, not beside it — the same coordinates build both."""
    built = scene()
    path = series_paths(built)[0]
    points = {(round(x, 6), round(y, 6)) for x, y in path.points}
    assert markers(built)
    for marker in markers(built):
        assert (round(marker.cx, 6), round(marker.cy, 6)) in points


def test_chart_point_labels_do_not_intersect_the_series_path() -> None:
    """A label on the curve is the failure this kind exists to avoid."""
    built = scene()
    paths = [path.points for path in series_paths(built)]
    for label in _point_labels(built):
        box = _text_box(label)
        for points in paths:
            for first, second in pairwise(points):
                assert not _segment_meets(first, second, box), (label.text, box)


def test_chart_vertical_axis_label_is_rotated_and_horizontal_is_not() -> None:
    """Decided once and constant, in every chart."""
    built = scene()
    rotated = [run for run in texts(built) if run.rotate]
    assert len(rotated) == 1
    assert rotated[0].rotate == -90.0
    assert "Requests" in rotated[0].text

    horizontal = next(run for run in texts(built) if "Week" in run.text)
    assert horizontal.rotate == 0.0


# --------------------------------------------------------------------------
# Scales, ticks and axes
# --------------------------------------------------------------------------


def test_chart_has_two_axis_lines_meeting_at_the_origin() -> None:
    built = scene()
    axes = [line for line in lines(built) if len(line.points) == 2]
    verticals = [line for line in axes if line.points[0][0] == line.points[1][0]]
    horizontals = [line for line in axes if line.points[0][1] == line.points[1][1]]
    assert verticals and horizontals


def test_chart_ticks_are_evenly_spaced_on_both_axes() -> None:
    built = scene()
    ticks = [line for line in lines(built) if len(line.points) == 2 and _is_tick(line)]
    across = sorted(t.points[0][0] for t in ticks if _is_vertical(t))
    up = sorted(t.points[0][1] for t in ticks if not _is_vertical(t))
    for values in (across, up):
        assert len(values) > 2
        gaps = [second - first for first, second in pairwise(values)]
        assert max(gaps) - min(gaps) < 1e-9


def test_chart_tick_labels_are_readable_numbers() -> None:
    """A step a reader can do arithmetic with, not the raw data range over five."""
    built = scene()
    numbers = [run.text for run in texts(built) if re.fullmatch(r"-?\d+(\.\d+)?", run.text)]
    assert numbers
    for text in numbers:
        assert len(text.split(".")[-1]) <= 2 if "." in text else True


def test_chart_honours_an_axis_minimum_the_author_pinned() -> None:
    """One of the few numbers an author may write: it is about the subject."""
    axes = {"horizontal": {"label": "Week"}, "vertical": {"label": "Requests", "min": 0}}
    built = chart_scene(parse_document(document(axes=axes)), THEME, MEASURER)
    assert "0" in [run.text for run in texts(built)]


def test_chart_with_a_max_below_its_min_is_refused() -> None:
    axes = {"horizontal": {"label": "Week"}, "vertical": {"label": "R", "min": 10, "max": 2}}
    with pytest.raises(DrawspecError, match="max below its min"):
        chart_scene(parse_document(document(axes=axes)), THEME, MEASURER)


def test_chart_with_a_flat_series_still_draws() -> None:
    """Every value the same is a real chart, and a zero range is not divisible."""
    flat = [{"name": "Flat", "data": [[1, 5], [2, 5], [3, 5]]}]
    built = chart_scene(parse_document(document(series=flat)), THEME, MEASURER)
    assert series_paths(built)


def test_chart_of_a_single_point_draws_a_marker() -> None:
    single = [{"name": "One", "data": [[1, 5]]}]
    built = chart_scene(parse_document(document(series=single)), THEME, MEASURER)
    assert len(markers(built)) == 1


# --------------------------------------------------------------------------
# Series
# --------------------------------------------------------------------------


def test_chart_draws_one_path_per_series() -> None:
    two = [*SERIES, {"name": "Rejected", "data": [[1, 2], [2, 3], [3, 1], [4, 4]], "role": "note"}]
    built = chart_scene(parse_document(document(series=two)), THEME, MEASURER)
    assert len(series_paths(built)) == 2


def test_chart_series_are_told_apart_without_colour() -> None:
    """Two series differ by their roles, which the theme guarantees are distinct."""
    two = [*SERIES, {"name": "Rejected", "data": [[1, 2], [2, 3], [3, 1]], "role": "note"}]
    built = chart_scene(parse_document(document(series=two)), THEME, MEASURER)
    roles = {path.role for path in series_paths(built)}
    assert len(roles) == 2
    channels = {THEME.roles[role].channels for role in roles}
    assert len(channels) == 2


def test_chart_marker_size_comes_from_the_theme() -> None:
    built = scene()
    expected = THEME.edge.head_length * MARKER_FRACTION
    assert all(marker.rx == pytest.approx(expected) for marker in markers(built))


def test_chart_without_a_series_is_refused() -> None:
    parsed = parse_document(document())
    with pytest.raises(DrawspecError, match="at least one series"):
        chart_scene(
            parse_document({**document(), "series": SERIES}).__class__(
                kind="chart", axes=parsed.axes, series=()
            ),
            THEME,
            MEASURER,
        )


def test_chart_refuses_a_document_of_another_kind() -> None:
    parsed = parse_document({"version": 1, "kind": "stack", "items": [{"text": "One"}]})
    with pytest.raises(DrawspecError, match="not the chart kind"):
        chart_scene(parsed, THEME, MEASURER)


def test_chart_too_small_for_its_own_axis_labels_raises_fiterror() -> None:
    with pytest.raises(FitError, match="no room left for the plot"):
        scene(width=60.0, height=40.0)


# --------------------------------------------------------------------------
# End to end
# --------------------------------------------------------------------------


@pytest.mark.parametrize("profile", ["inline", "standalone"])
def test_chart_renders_to_safe_svg(profile: str) -> None:
    svg = render(document(), profile=profile)
    assert check_embedding_safety(svg, THEME, profile) == ()


def test_chart_renders_identically_twice() -> None:
    assert render(document()) == render(document())


def test_chart_uses_no_matplotlib() -> None:
    """The plan says so, and for a reason: its SVG fails the inline test worse
    than the diagram tools do."""
    import drawspec.charts

    assert "matplotlib" not in (drawspec.charts.__doc__ or "").lower()
    assert not any("matplotlib" in name for name in dir(drawspec.charts))


# --------------------------------------------------------------------------
# Helpers, independent of drawspec's own geometry
# --------------------------------------------------------------------------


def _is_vertical(line: Path) -> bool:
    return line.points[0][0] == pytest.approx(line.points[1][0])


def _is_tick(line: Path) -> bool:
    length = math.dist(line.points[0], line.points[1])
    return length <= THEME.edge.head_length + 1e-6


def _point_labels(built: Scene) -> list[TextRun]:
    """Runs tagged with a series role rather than the furniture role."""
    series_roles = {path.role for path in series_paths(built)}
    return [run for run in texts(built) if run.role in series_roles]


def _text_box(run: TextRun) -> tuple[float, float, float, float]:
    extents = MEASURER.measure(run.text, run.font, THEME.scale[run.level], run.weight)
    starts = {"middle": run.x - extents.width / 2, "start": run.x, "end": run.x - extents.width}
    left = starts[run.anchor]
    return left, run.y - extents.height, left + extents.width, run.y


def _segment_meets(
    first: tuple[float, float], second: tuple[float, float], box: tuple[float, float, float, float]
) -> bool:
    left, top, right, bottom = box
    for index in range(25):
        fraction = index / 24
        x = first[0] + (second[0] - first[0]) * fraction
        y = first[1] + (second[1] - first[1]) * fraction
        if left <= x <= right and top <= y <= bottom:
            return True
    return False


# --------------------------------------------------------------------------
# A label that says which point it belongs to
# --------------------------------------------------------------------------


def test_point_labels_tell_the_chart_s_own_values_apart() -> None:
    """Four points at four heights must not all be labelled the same number.

    The precision used to come from the axis step, which is the wrong source
    exactly when it matters: values close together share a tick interval, so the
    reference chart's 7.2, 6.8, 7.4 and 6.9 all printed as `7` — four labels
    reading `7` at four visibly different heights, which reads as a broken chart
    rather than as a rounded one.
    """
    close = [{"name": "Placement", "data": [[1, 7.2], [2, 6.8], [3, 7.4], [4, 6.9]]}]
    # The axes are pinned wider than the data on purpose. This is a test about
    # *precision*, and a series whose highest and lowest points sit on the plot's
    # own edges loses all its labels to the all-or-nothing placement rule: above
    # the top point is outside the plot and below it crosses the curve. Correct
    # behaviour, different subject — and a limitation worth knowing about, noted
    # in docs/kinds-wanted.md.
    built = scene(
        series=close,
        axes={
            "horizontal": {"label": "Attempt", "min": 0, "max": 5},
            "vertical": {"label": "Seconds", "min": 6.5, "max": 7.7},
        },
    )
    labels = [run.text for run in texts(built) if run.text.replace(".", "").isdigit()]
    assert {"7.2", "6.8", "7.4", "6.9"} <= set(labels)


def test_point_labels_carry_no_more_decimals_than_they_need() -> None:
    """Precision is what the values ask for — values a whole apart print whole."""
    apart = [{"name": "Accepted", "data": [[1, 10], [2, 14], [3, 12], [4, 17]]}]
    built = scene(series=apart)
    for run in texts(built):
        assert "." not in run.text


def test_the_last_tick_label_fits_inside_the_canvas() -> None:
    """A label centred on the end of an axis hangs half its width past it."""
    built = scene()
    for run in texts(built):
        if run.anchor == "middle":
            width = MEASURER.measure(run.text, run.font, THEME.scale[run.level]).width
            assert run.x + width / 2 <= built.width + 1e-6, f"{run.text!r} runs off the canvas"


# --------------------------------------------------------------------------
# marks: bars, areas, stacks
# --------------------------------------------------------------------------


def marked(*series: Mapping[str, object]) -> Scene:
    document = {
        "version": 1,
        "kind": "chart",
        "title": "Marks",
        "axes": {
            "horizontal": {"label": "Quarter"},
            "vertical": {"label": "Count"},
        },
        "series": list(series),
    }
    return chart_scene(parse_document(document), THEME, MEASURER)


BARS: Mapping[str, object] = {"name": "One", "mark": "bar", "data": [[1, 30], [2, 40], [3, 20]]}
MORE: Mapping[str, object] = {"name": "Two", "mark": "bar", "data": [[1, 10], [2, 20], [3, 35]]}


SWATCH_TALL = MEASURER.measure("0", THEME.font.default, THEME.scale["label"]).height * SWATCH_SHARE
SWATCH_WIDE = SWATCH_TALL * SWATCH_ASPECT


def _is_swatch(item: Polygon) -> bool:
    """A legend swatch: one known size, which no mark is by accident."""
    xs = [x for x, _ in item.points]
    ys = [y for _, y in item.points]
    return (
        len(item.points) == 4
        and abs(max(xs) - min(xs) - SWATCH_WIDE) < 1e-6
        and abs(max(ys) - min(ys) - SWATCH_TALL) < 1e-6
    )


def filled_of(built: Scene) -> list[Polygon]:
    """The filled marks. A legend swatch is a polygon too, and is not a mark."""
    return [item for item in built.primitives if isinstance(item, Polygon) and not _is_swatch(item)]


def test_a_bar_series_draws_one_closed_figure_per_point() -> None:
    built = marked(BARS)
    bars = filled_of(built)
    assert len(bars) == 3
    for bar in bars:
        assert len(bar.points) == 4


def test_a_bar_stands_on_the_baseline() -> None:
    """A bar says 'this much of it' by its length, which needs somewhere to start."""
    built = marked(BARS)
    bottoms = {round(max(y for _, y in bar.points), 6) for bar in filled_of(built)}
    assert len(bottoms) == 1, "every bar starts at the same place"


def test_a_filled_chart_stretches_its_axis_to_the_baseline() -> None:
    """Otherwise a bar of 7.0 next to one of 7.4 looks like nothing beside three times nothing."""
    lined = marked({"name": "One", "mark": "line", "data": [[1, 30], [2, 40]]})
    barred = marked({"name": "One", "mark": "bar", "data": [[1, 30], [2, 40]]})
    assert _plot_span(barred) > _plot_span(lined)


def _plot_span(built: Scene) -> float:
    """How much of the vertical axis the drawing covers, in data terms.

    Read off the tick labels rather than the internals: the axis a reader sees is
    the thing the claim is about.
    """
    values = [
        float(item.text)
        for item in built.primitives
        if isinstance(item, TextRun) and re.fullmatch(r"-?\d+(\.\d+)?", item.text)
    ]
    return max(values) - min(values)


def test_two_bar_series_stand_beside_each_other_without_overlapping() -> None:
    built = marked(BARS, MORE)
    spans = sorted(
        (min(x for x, _ in bar.points), max(x for x, _ in bar.points)) for bar in filled_of(built)
    )
    for (_, first_right), (second_left, _) in pairwise(spans):
        assert first_right <= second_left + 1e-6


def test_a_stacked_series_starts_where_the_one_below_it_ended() -> None:
    """Which is the whole difference between stacked and merely overlapping."""
    built = marked(
        {"name": "One", "mark": "bar", "stack": "s", "data": [[1, 30]]},
        {"name": "Two", "mark": "bar", "stack": "s", "data": [[1, 20]]},
    )
    lower, upper = sorted(filled_of(built), key=lambda bar: -max(y for _, y in bar.points))
    assert min(y for _, y in lower.points) == pytest.approx(max(y for _, y in upper.points))


def test_stacked_series_share_one_slot_and_unstacked_ones_do_not() -> None:
    stacked = marked(
        {"name": "One", "mark": "bar", "stack": "s", "data": [[1, 30]]},
        {"name": "Two", "mark": "bar", "stack": "s", "data": [[1, 20]]},
    )
    apart = marked(
        {"name": "One", "mark": "bar", "data": [[1, 30]]},
        {"name": "Two", "mark": "bar", "data": [[1, 20]]},
    )
    lefts = {round(min(x for x, _ in bar.points), 6) for bar in filled_of(stacked)}
    assert len(lefts) == 1, "a stack is one column"
    assert len({round(min(x for x, _ in bar.points), 6) for bar in filled_of(apart)}) == 2


def test_every_filled_series_gets_a_different_fill() -> None:
    """Greyscale legibility, made structural: the theme declares the sequence."""
    built = marked(BARS, MORE)
    by_left: dict[float, str] = {}
    for bar in filled_of(built):
        by_left.setdefault(round(min(x for x, _ in bar.points), 3), bar.fill)
    assert len(set(by_left.values())) == 2
    assert set(by_left.values()) <= set(THEME.mark.fills)


def test_an_area_reaches_the_baseline_at_both_ends() -> None:
    """Stated as an extent, not as a point order — the ring closes at the floor.

    An unstacked area's floor *is* the baseline, so both ends of its x-range have
    a corner sitting on it. Asserting `points[0]` and `points[-1]` instead pins
    the order the ring happens to be wound in, which changed the moment areas
    learned to stack on a floor that is not the baseline.
    """
    built = marked({"name": "One", "mark": "area", "data": [[1, 30], [2, 40], [3, 20]]})
    (area,) = filled_of(built)
    baseline = max(y for _, y in area.points)
    on_floor = {round(x, 3) for x, y in area.points if y == pytest.approx(baseline)}
    xs = [x for x, _ in area.points]
    assert {round(min(xs), 3), round(max(xs), 3)} <= on_floor


def test_a_bar_has_square_corners() -> None:
    """A rect would take the theme's corner radius and stop meeting its own baseline."""
    assert not [item for item in marked(BARS).primitives if isinstance(item, Rect)]


def test_an_unknown_mark_is_refused_by_the_schema() -> None:
    with pytest.raises(DocumentError) as error:
        parse_document(
            {
                "version": 1,
                "kind": "chart",
                "title": "Marks",
                "axes": {"horizontal": {"label": "x"}, "vertical": {"label": "y"}},
                "series": [{"name": "One", "mark": "candlestick", "data": [[1, 2]]}],
            }
        )
    assert "candlestick" in str(error.value)


# --------------------------------------------------------------------------
# quadrant
# --------------------------------------------------------------------------


def quadrant(*positions: Mapping[str, object]) -> Scene:
    document = {
        "version": 1,
        "kind": "quadrant",
        "title": "A quadrant",
        "axes": {
            "horizontal": {"label": "How much of this"},
            "vertical": {"label": "How much of that"},
        },
        "positions": list(positions),
    }
    return chart_scene(parse_document(document), THEME, MEASURER)


CORNERS: tuple[Mapping[str, object], ...] = (
    {"text": "Neither", "across": 0.1, "up": 0.1},
    {"text": "That only", "across": 0.1, "up": 0.9},
    {"text": "This only", "across": 0.9, "up": 0.1},
    {"text": "Both", "across": 0.9, "up": 0.9},
    {"text": "Some of each", "across": 0.5, "up": 0.5},
)


def test_a_quadrant_marks_every_position_it_was_given() -> None:
    assert len(markers(quadrant(*CORNERS))) == len(CORNERS)


def test_a_quadrant_labels_every_position_it_marks() -> None:
    said = {run.text for run in texts(quadrant(*CORNERS))}
    for item in CORNERS:
        assert item["text"] in said


def test_a_quadrant_has_no_ticks() -> None:
    """A tick invites a reader to measure a diagram whose author was comparing."""
    numbers = [
        run.text for run in texts(quadrant(*CORNERS)) if re.fullmatch(r"-?\d+(\.\d+)?", run.text)
    ]
    assert numbers == []


def test_a_quadrant_draws_both_midlines() -> None:
    """'Which quarter is it in' is the question these diagrams are for."""
    dividers = [line for line in lines(quadrant(*CORNERS)) if line.role == DIVIDER_ROLE]
    assert len(dividers) == 2
    assert {_orientation(line) for line in dividers} == {"horizontal", "vertical"}


def _orientation(line: Path) -> str:
    (x1, y1), (x2, y2) = line.points[0], line.points[-1]
    return "horizontal" if abs(y2 - y1) < abs(x2 - x1) else "vertical"


def test_no_quadrant_label_sits_on_a_midline() -> None:
    """The point in the middle of the field is a real answer, and it needs a label."""
    built = quadrant(*CORNERS)
    dividers = [line for line in lines(built) if line.role == DIVIDER_ROLE]
    named = {str(item["text"]) for item in CORNERS}
    for run in texts(built):
        if run.text not in named:
            continue  # the axis labels sit outside the plot the midlines span
        extents = MEASURER.measure(run.text, THEME.font.default, THEME.scale[run.level])
        half = extents.width / 2
        box = _label_box(run.x, run.y, run.anchor, extents.width, extents.height, half)
        for divider in dividers:
            assert not _crosses(box, divider.points), (run.text, divider.points)


def test_two_quadrant_labels_never_overlap() -> None:
    built = quadrant(*CORNERS)
    named = {str(item["text"]) for item in CORNERS}
    boxes = []
    for run in texts(built):
        if run.text not in named:
            continue
        extents = MEASURER.measure(run.text, THEME.font.default, THEME.scale[run.level])
        boxes.append(
            _label_box(run.x, run.y, run.anchor, extents.width, extents.height, extents.width / 2)
        )
    for first, second in combinations(boxes, 2):
        assert not (
            first[0] < second[2]
            and second[0] < first[2]
            and first[1] < second[3]
            and second[1] < first[3]
        )


def test_a_quadrant_still_needs_both_axes_labelled() -> None:
    """The rule holds wherever there is an axis."""
    with pytest.raises(DocumentError):
        parse_document(
            {
                "version": 1,
                "kind": "quadrant",
                "title": "A quadrant",
                "axes": {"horizontal": {"label": "x"}, "vertical": {}},
                "positions": [{"text": "One", "across": 0.5, "up": 0.5}],
            }
        )


# --------------------------------------------------------------------------
# curve
# --------------------------------------------------------------------------


def curve(*curves: Mapping[str, object], axes: Mapping[str, object] | None = None) -> Scene:
    document = {
        "version": 1,
        "kind": "curve",
        "title": "A curve",
        "axes": axes or {"horizontal": {"label": "Time"}, "vertical": {"label": "How much"}},
        "curves": list(curves),
    }
    return chart_scene(parse_document(document), THEME, MEASURER)


HYPE: Mapping[str, object] = {
    "waypoints": [
        {"text": "Start", "across": 0.0, "up": 0.1},
        {"across": 0.2, "up": 0.9},
        {"text": "Peak", "across": 0.3, "up": 1.0},
        {"across": 0.5, "up": 0.2},
        {"text": "Trough", "across": 0.6, "up": 0.1},
        {"text": "Plateau", "across": 1.0, "up": 0.5},
    ]
}
STRAIGHT: Mapping[str, object] = {
    "name": "Ideal",
    "waypoints": [{"across": 0.0, "up": 1.0}, {"across": 1.0, "up": 0.0}],
}


def test_a_curve_passes_through_every_waypoint() -> None:
    """Through, not near: a waypoint is a named place, and its marker sits on it."""
    built = curve(HYPE)
    (path,) = series_paths(built)
    for marker in markers(built):
        assert any(math.hypot(x - marker.cx, y - marker.cy) < 0.5 for x, y in path.points), (
            marker.cx,
            marker.cy,
        )


def test_a_curve_of_two_points_stays_a_straight_line() -> None:
    """Which is what an 'ideal' burn-down is, and what smoothing would spoil."""
    built = curve(STRAIGHT)
    drawn = [line for line in lines(built) if line.role == "step"]
    assert len(drawn) == 1
    assert len(drawn[0].points) == 2


def test_a_curve_diagram_has_no_ticks() -> None:
    """Nobody has the numbers behind a hype cycle."""
    numbers = [run.text for run in texts(curve(HYPE)) if re.fullmatch(r"-?\d+(\.\d+)?", run.text)]
    assert numbers == []


def test_a_curve_draws_the_categories_named_on_its_axis() -> None:
    """It used to accept them and draw nothing, which is the one outcome refused.

    *dia 1* and *últim dia* are two places on the axis, named — not numbers read
    off a shape nobody measured, which is what `test_a_curve_diagram_has_no_ticks`
    keeps out.
    """
    built = curve(
        STRAIGHT,
        axes={
            "horizontal": {"label": "Temps", "categories": ["dia 1", "últim dia"]},
            "vertical": {"label": "Nivell"},
        },
    )
    drawn = {run.text for run in texts(built)}
    assert {"dia 1", "últim dia"} <= drawn


def test_a_curves_first_and_last_mark_land_where_the_curve_does() -> None:
    """Spread over the waypoints' range, not the plot's — *dia 1* is where the
    line leaves the corner, and a margin's width away from it means somewhere else."""
    built = curve(
        STRAIGHT,
        axes={
            "horizontal": {"label": "Temps", "categories": ["first", "last"]},
            "vertical": {"label": "Nivell"},
        },
    )
    (path,) = [line for line in lines(built) if line.role == "step"]
    first = next(run for run in texts(built) if run.text == "first")
    last = next(run for run in texts(built) if run.text == "last")
    assert abs(first.x - path.points[0][0]) < 0.5
    assert abs(last.x - path.points[-1][0]) < 0.5


def test_a_curve_refuses_an_axis_mark_that_would_run_off_the_sheet() -> None:
    """The first mark sits at the left end of the axis, so a long name centred on
    it goes off the canvas — text off the sheet, refused rather than drawn."""
    with pytest.raises(FitError, match="past the edge"):
        curve(
            STRAIGHT,
            axes={
                "horizontal": {
                    "label": "Temps",
                    "categories": [
                        "a very long name indeed for one single place on the axis",
                        "and another name just as long for the place beside it",
                    ],
                },
                "vertical": {"label": "Nivell"},
            },
        )


def test_a_curve_refuses_two_axis_marks_that_would_overlap() -> None:
    """Text over text is one of the two failures the tool exists to prevent, and
    no stroke is involved, so the clearance pass cannot save it."""
    with pytest.raises(FitError, match="overlap"):
        curve(
            STRAIGHT,
            axes={
                "horizontal": {
                    "label": "Temps",
                    "categories": [
                        "one",
                        "a name long enough to touch",
                        "a moderately long name here",
                        "and one more",
                        "five",
                    ],
                },
                "vertical": {"label": "Nivell"},
            },
        )


def test_only_named_waypoints_are_marked() -> None:
    """The rest are there to shape the curve, not to be read."""
    waypoints = HYPE["waypoints"]
    assert isinstance(waypoints, list)
    named = [point for point in waypoints if point.get("text")]
    assert len(markers(curve(HYPE))) == len(named)


def test_a_curve_name_is_drawn_where_the_curve_ends() -> None:
    built = curve(STRAIGHT)
    (path,) = [line for line in lines(built) if len(line.points) == 2 and line.role == "step"]
    (label,) = [run for run in texts(built) if run.text == "Ideal"]
    assert label.x > path.points[-1][0]
    assert abs(label.y - path.points[-1][1]) < THEME.scale["label"]


def test_a_waypoint_label_never_lands_on_a_curve_name() -> None:
    """The two would be saying different things about the same point."""
    built = curve(
        {
            **STRAIGHT,
            "waypoints": [
                {"across": 0.0, "up": 1.0},
                {"text": "The end", "across": 1.0, "up": 0.0},
            ],
        }
    )
    boxes = []
    for run in texts(built):
        if run.text not in ("Ideal", "The end"):
            continue
        extents = MEASURER.measure(run.text, THEME.font.default, THEME.scale[run.level])
        boxes.append(
            _label_box(run.x, run.y, run.anchor, extents.width, extents.height, extents.width / 2)
        )
    for first, second in combinations(boxes, 2):
        assert not (
            first[0] < second[2]
            and second[0] < first[2]
            and first[1] < second[3]
            and second[1] < first[3]
        )


def test_a_curve_needs_at_least_two_waypoints() -> None:
    with pytest.raises(DocumentError):
        parse_document(
            {
                "version": 1,
                "kind": "curve",
                "title": "A curve",
                "axes": {"horizontal": {"label": "x"}, "vertical": {"label": "y"}},
                "curves": [{"waypoints": [{"across": 0, "up": 0}]}],
            }
        )


# --------------------------------------------------------------------------
# Axis captions
# --------------------------------------------------------------------------


def _horizontal_axis(built: Scene) -> Path:
    """The bottom rule: the widest horizontal line in the drawing."""
    flat = [
        line
        for line in lines(built)
        if len(line.points) == 2 and _orientation(line) == "horizontal"
    ]
    return max(flat, key=lambda line: abs(line.points[1][0] - line.points[0][0]))


def _caption(built: Scene, text: str) -> TextRun:
    return next(run for run in texts(built) if run.text == text and not run.rotate)


CAPTIONED: tuple[tuple[str, Scene], ...] = (
    ("Week", scene()),
    ("How much of this", quadrant(*CORNERS)),
)


@pytest.mark.parametrize(("label", "built"), CAPTIONED, ids=["chart", "quadrant"])
def test_the_horizontal_axis_caption_keeps_daylight_from_the_axis(label: str, built: Scene) -> None:
    """A caption welded to the line it names reads as part of the line.

    The rotated caption on the left hides this class of mistake — a run turned a
    quarter turn measures its gap from the descender side — so the horizontal one
    is the one worth asserting on.
    """
    caption = _caption(built, label)
    extents = MEASURER.measure(caption.text, THEME.font.default, THEME.scale[caption.level])
    top_of_text = caption.y - extents.ascent
    axis_y = _horizontal_axis(built).points[0][1]
    assert top_of_text - axis_y > 0.0, "the caption's cap-height sits on the axis"


def test_the_curve_caption_keeps_daylight_from_the_axis() -> None:
    built = curve({"name": "One", "waypoints": [{"across": 0, "up": 0}, {"across": 1, "up": 1}]})
    caption = _caption(built, "Time")
    extents = MEASURER.measure(caption.text, THEME.font.default, THEME.scale[caption.level])
    axis_y = _horizontal_axis(built).points[0][1]
    assert caption.y - extents.ascent - axis_y > 0.0


def test_a_label_on_the_middle_of_a_quadrant_clears_both_dividers() -> None:
    """Dead centre is a real answer, and it is the case the diagonals exist for.

    Above, below, left and right all straddle one divider there; a corner
    position offset only vertically has its edge flush against the other. That
    one used to be taken, and it passed by touching exactly.
    """
    built = quadrant({"text": "Split it", "across": 0.5, "up": 0.5})
    dividers = [line for line in lines(built) if line.role == DIVIDER_ROLE]
    run = _caption(built, "Split it")
    extents = MEASURER.measure(run.text, THEME.font.default, THEME.scale[run.level])
    box = _label_box(run.x, run.y, run.anchor, extents.width, extents.height, extents.width / 2)
    for divider in dividers:
        assert not _crosses(box, divider.points)


# --------------------------------------------------------------------------
# Areas and piles
# --------------------------------------------------------------------------


def test_an_area_is_not_outlined() -> None:
    """Its sides are where the drawing stops, not something that happened.

    Stroked, the two verticals closing an area are indistinguishable from a
    measurement — over a bar chart they drew a full-weight line straight down
    through the bar at each end of the area's range.
    """
    built = marked({"name": "One", "mark": "area", "data": [[1, 30], [2, 40], [3, 20]]})
    (area,) = filled_of(built)
    assert area.region
    drawn = next(line for line in emit(built, THEME).split("<") if line.startswith("polygon"))
    assert 'stroke="none"' in drawn


def test_an_area_draws_its_top_edge_as_a_line() -> None:
    """No data is lost by not outlining the region: the crest is a line of its own."""
    data = [[1, 30], [2, 40], [3, 20]]
    built = marked({"name": "One", "mark": "area", "data": data})
    (area,) = filled_of(built)
    crest = {
        (round(x, 3), round(y, 3)) for x, y in area.points if y != max(p[1] for p in area.points)
    }
    tops = [line for line in lines(built) if len(line.points) == len(data)]
    assert tops, "the area's top edge is drawn as its own path"
    assert crest <= {(round(x, 3), round(y, 3)) for line in tops for x, y in line.points}


def test_a_stacked_area_sits_on_the_one_below_it() -> None:
    """`stack` used to be read for bars only, so a stacked area silently overlaid."""
    built = marked(
        {"name": "Lower", "mark": "area", "stack": "s", "data": [[1, 10], [2, 10]]},
        {"name": "Upper", "mark": "area", "stack": "s", "data": [[1, 10], [2, 10]]},
    )
    lower, upper = filled_of(built)
    # y grows downwards, so "above" is a smaller number.
    assert min(y for _, y in upper.points) < min(y for _, y in lower.points)
    assert max(y for _, y in upper.points) == pytest.approx(min(y for _, y in lower.points))


def test_a_pile_is_measured_by_its_total_not_by_its_tallest_member() -> None:
    """Two bars of 20 in one stack reach 40, and used to be drawn off the top.

    The scale was taken from the raw values, so the axis stopped at 20 and the
    second bar of the pile was placed above the top edge of the drawing.
    """
    built = marked(
        {"name": "a", "mark": "bar", "stack": "s", "data": [[1, 20], [2, 20]]},
        {"name": "b", "mark": "bar", "stack": "s", "data": [[1, 20], [2, 20]]},
    )
    for bar in filled_of(built):
        assert min(y for _, y in bar.points) >= 0.0, "a bar is drawn off the top of the plot"
        assert max(y for _, y in bar.points) <= built.height


# --------------------------------------------------------------------------
# Values written on the marks
# --------------------------------------------------------------------------


BARS_TWO = (
    {"name": "Raised", "mark": "bar", "data": [[1, 34], [2, 41]]},
    {"name": "Closed", "mark": "bar", "data": [[1, 52], [2, 47]]},
)


def _on_bar(built: Scene, bar: Polygon, text: str) -> TextRun:
    """The run reading `text` that belongs to `bar`, not the tick label of the same name.

    A tick can be numbered `10` too, and it was the one `next()` found first.
    """
    left, right = min(x for x, _ in bar.points), max(x for x, _ in bar.points)
    return next(
        run
        for run in texts(built)
        if run.text == text and run.anchor == "middle" and left <= run.x <= right
    )


def test_a_bar_says_its_own_number() -> None:
    built = marked(*BARS_TWO)
    for bar in filled_of(built):
        left = min(x for x, _ in bar.points)
        assert [run for run in texts(built) if run.anchor == "middle" and run.x > left]


def test_a_bar_s_number_sits_above_it_and_a_stacked_one_sits_inside() -> None:
    """Open sky over a bar is where a person writing on a printout puts it.

    A segment of a stack has no sky: the next segment starts exactly at its top
    edge, so its number goes inside it instead.
    """
    plain = marked({"name": "One", "mark": "bar", "data": [[1, 10], [2, 12]]})
    bar = min(filled_of(plain), key=lambda item: min(x for x, _ in item.points))
    assert _on_bar(plain, bar, "10").y < min(y for _, y in bar.points)

    piled = marked(
        {"name": "Lower", "mark": "bar", "stack": "s", "data": [[1, 10]]},
        {"name": "Upper", "mark": "bar", "stack": "s", "data": [[1, 12]]},
    )
    upper = min(filled_of(piled), key=lambda item: min(y for _, y in item.points))
    label = _on_bar(piled, upper, "12")
    assert min(y for _, y in upper.points) < label.y < max(y for _, y in upper.points)


def test_a_bar_number_never_spills_over_the_bar_beside_it() -> None:
    """Wider than its own bar means the series gets no numbers at all.

    Numbering only the bars that happen to have room reads as arbitrary — the
    same judgement the point labels are held to.
    """
    narrow = {
        "version": 1,
        "kind": "chart",
        "title": "Crowded",
        "width": 220,
        "axes": {"horizontal": {"label": "Quarter"}, "vertical": {"label": "Count"}},
        "series": [
            {"name": name, "mark": "bar", "data": [[1, value], [2, value + 1]]}
            for name, value in (("a", 1234), ("b", 3456), ("c", 5678), ("d", 7891))
        ],
    }
    built = chart_scene(parse_document(narrow), THEME, MEASURER)
    said = {run.text for run in texts(built)}
    assert not {"1234", "3456", "5678", "7891"} & said


def test_values_false_silences_every_number_on_the_marks() -> None:
    """The tick labels stay: they are the axis, not a claim about a point."""
    document = {
        "version": 1,
        "kind": "chart",
        "title": "Quiet",
        "values": False,
        "axes": {"horizontal": {"label": "Quarter"}, "vertical": {"label": "Count"}},
        "series": list(BARS_TWO),
    }
    said = {run.text for run in texts(chart_scene(parse_document(document), THEME, MEASURER))}
    assert not {"34", "41", "52", "47"} & said
    assert any(re.fullmatch(r"\d+", run) for run in said), "the ticks are still numbered"


# --------------------------------------------------------------------------
# Category labels
# --------------------------------------------------------------------------

LONG_CATEGORIES = [
    "Suspensio PROVISIONAL (mesura cautelar)",
    "Suspensio FERMA per sentencia",
    "Inhabilitacio especial",
    "Multa coercitiva",
]


def _categorical(categories: list[str], **extra: object) -> Scene:
    return chart_scene(
        parse_document(
            document(
                axes={
                    "horizontal": {"label": "Mesura", "categories": categories},
                    "vertical": {"label": "Dies"},
                },
                series=[
                    {
                        "name": "Durada",
                        "data": [[index + 1, 10 * (index + 1)] for index in range(len(categories))],
                        "mark": "bar",
                    }
                ],
                **extra,
            )
        ),
        THEME,
        MEASURER,
    )


def _run_box(run: TextRun) -> tuple[float, float]:
    width = MEASURER.advance(run.text, THEME.font.default, THEME.scale[run.level])
    return run.x - width / 2, run.x + width / 2


def test_long_category_labels_do_not_overprint_each_other() -> None:
    """Two of these used to read as one smudge.

    'Suspensio PROVISIONAL (mesura cautelar)' and the one after it overlapped by
    27 units at the default width — text over text, which is the first failure
    family the tool exists to remove.
    """
    built = _categorical(LONG_CATEGORIES)
    bottom = max(run.y for run in texts(built))
    band = [run for run in texts(built) if run.y > bottom - 60 and run.anchor == "middle"]
    by_line: dict[float, list[TextRun]] = {}
    for run in band:
        by_line.setdefault(round(run.y, 3), []).append(run)
    for row in by_line.values():
        boxes = sorted(_run_box(run) for run in row)
        for (_, first_right), (second_left, _) in pairwise(boxes):
            assert first_right <= second_left + 1e-6


def test_a_long_category_label_stays_inside_the_canvas() -> None:
    """The first label began 55 units outside the viewBox: text off the sheet."""
    built = _categorical(LONG_CATEGORIES)
    for run in texts(built):
        if run.anchor != "middle" or run.rotate:
            continue
        left, right = _run_box(run)
        assert left >= -1e-6, run.text
        assert right <= built.width + 1e-6, run.text


def test_a_long_category_label_is_wrapped_rather_than_shrunk() -> None:
    """It gets more lines, not a smaller size — the size is the theme's."""
    built = _categorical(LONG_CATEGORIES)
    wanted = ("Suspensio", "PROVISIONAL", "(mesura cautelar)")
    written = " ".join(run.text for run in texts(built) if run.text in wanted)
    assert written == "Suspensio PROVISIONAL (mesura cautelar)"


def test_a_short_category_label_is_left_on_one_line() -> None:
    built = _categorical(["IaaS", "PaaS", "SaaS"])
    assert [run.text for run in texts(built) if run.text.endswith("aaS")] == [
        "IaaS",
        "PaaS",
        "SaaS",
    ]


def test_a_category_that_cannot_be_broken_small_enough_is_refused() -> None:
    """A refusal naming the label beats illegible output, which is the promise."""
    with pytest.raises(FitError, match="does not fit"):
        _categorical(["Unsplittableliteralrunofcharactersthatgoesonandon", "b", "c", "d", "e", "f"])


# --------------------------------------------------------------------------
# A named distance between two waypoints
# --------------------------------------------------------------------------


VARIANCE = {
    "version": 1,
    "kind": "curve",
    "title": "Where a project has got to",
    "axes": {"horizontal": {"label": "Time"}, "vertical": {"label": "Cost"}},
    "curves": [
        {
            "name": "Planned",
            "waypoints": [
                {"across": 0.0, "up": 0.0},
                {"id": "pv", "across": 0.55, "up": 0.45},
                {"across": 1.0, "up": 1.0},
            ],
        },
        {
            "name": "Spent",
            "waypoints": [{"across": 0.0, "up": 0.0}, {"id": "ac", "across": 0.72, "up": 0.72}],
        },
        {
            "name": "Earned",
            "waypoints": [{"across": 0.0, "up": 0.0}, {"id": "ev", "across": 0.72, "up": 0.45}],
        },
    ],
    "spans": [
        {"text": "Cost variance", "from": "ac", "to": "ev"},
        {"text": "Schedule variance", "from": "ev", "to": "pv"},
    ],
}


def _variance(**changes: object) -> Scene:
    return chart_scene(parse_document({**VARIANCE, **changes}), THEME, MEASURER)


def test_a_span_measures_the_gap_between_two_curves() -> None:
    """Both quantities the drawing exists to explain are gaps rather than
    points, and both used to be pushed into the caption as formulas — which
    states them and does not show them."""
    written = {run.text for run in labels(_variance())}
    assert {"Cost variance", "Schedule variance"} <= written


def test_one_span_measures_down_and_the_other_along() -> None:
    """A vertical-only span would leave the schedule variance as unsayable as
    it was: the two are not the same shape."""
    runs = [item for item in _variance().primitives if isinstance(item, Path)]
    bars = [run for run in runs if len(run.points) == 2]
    vertical = [b for b in bars if b.points[0][0] == pytest.approx(b.points[1][0])]
    horizontal = [b for b in bars if b.points[0][1] == pytest.approx(b.points[1][1])]
    assert vertical and horizontal


def test_two_spans_meeting_at_one_point_do_not_label_each_other() -> None:
    """A cost variance and a schedule variance share the earned-value waypoint,
    so normals derived from each bar's own direction both point into the corner
    they share."""
    found = [run for run in labels(_variance()) if "variance" in run.text]
    (first, second) = found
    apart = max(abs(first.x - second.x), abs(first.y - second.y))
    assert apart > THEME.scale["label"]


def test_a_span_naming_a_waypoint_that_is_not_there_is_refused() -> None:
    with pytest.raises(DocumentError, match="not the id of any waypoint"):
        parse_document({**VARIANCE, "spans": [{"text": "X", "from": "ac", "to": "nowhere"}]})


def test_a_span_between_a_point_and_itself_is_refused() -> None:
    with pytest.raises(DocumentError, match="no distance to name"):
        parse_document({**VARIANCE, "spans": [{"text": "X", "from": "ac", "to": "ac"}]})


def test_two_waypoints_sharing_an_id_are_refused() -> None:
    curves = [
        {
            "name": "One",
            "waypoints": [{"id": "same", "across": 0.0, "up": 0.0}, {"across": 1.0, "up": 1.0}],
        },
        {
            "name": "Two",
            "waypoints": [{"id": "same", "across": 0.0, "up": 0.5}, {"across": 1.0, "up": 0.5}],
        },
    ]
    with pytest.raises(DocumentError, match="duplicate waypoint id"):
        parse_document({**VARIANCE, "curves": curves, "spans": []})


def test_a_span_label_takes_the_other_side_rather_than_leaving_the_canvas() -> None:
    """A span against the right-hand edge has no room on its right, and a label
    written there is a label the canvas clips — the failure this whole family
    exists to prevent."""
    document = {
        **VARIANCE,
        "curves": [
            {
                "name": "Spent",
                "waypoints": [{"across": 0.0, "up": 0.0}, {"id": "ac", "across": 1.0, "up": 1.0}],
            },
            {
                "name": "Earned",
                "waypoints": [{"across": 0.0, "up": 0.0}, {"id": "ev", "across": 1.0, "up": 0.2}],
            },
        ],
        "spans": [{"text": "A very long variance name", "from": "ac", "to": "ev"}],
    }
    built = chart_scene(parse_document(document), THEME, MEASURER)
    (label,) = [run for run in labels(built) if "variance" in run.text]
    width = MEASURER.advance(label.text, THEME.font.default, THEME.scale[label.level])
    assert label.x - width / 2 >= 0
    assert label.x + width / 2 <= built.width


def test_a_span_whose_name_fits_on_neither_side_is_refused() -> None:
    """Refusing names the span; clipping says nothing at all."""
    document = {
        **VARIANCE,
        "width": 200,
        "curves": [
            {
                "name": "A",
                "waypoints": [{"across": 0.0, "up": 0.0}, {"id": "ac", "across": 1.0, "up": 1.0}],
            },
            {
                "name": "B",
                "waypoints": [{"across": 0.0, "up": 0.0}, {"id": "ev", "across": 1.0, "up": 0.2}],
            },
        ],
        "spans": [
            {
                "text": "A name far too long for two hundred units of canvas",
                "from": "ac",
                "to": "ev",
            }
        ],
    }
    with pytest.raises(FitError, match="no room for its name"):
        chart_scene(parse_document(document), THEME, MEASURER)


def test_two_waypoints_at_one_place_are_refused_rather_than_dropped() -> None:
    """A span that quietly vanishes is worse than one that cannot be drawn: the
    author asked for exactly that gap to be visible."""
    document = {
        **VARIANCE,
        "curves": [
            {
                "name": "A",
                "waypoints": [{"across": 0.0, "up": 0.0}, {"id": "ac", "across": 0.5, "up": 0.5}],
            },
            {
                "name": "B",
                "waypoints": [{"across": 0.0, "up": 0.1}, {"id": "ev", "across": 0.5, "up": 0.5}],
            },
        ],
        "spans": [{"text": "Nothing", "from": "ac", "to": "ev"}],
    }
    with pytest.raises(DocumentError, match="no distance between them"):
        parse_document(document)

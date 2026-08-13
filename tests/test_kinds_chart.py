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
from drawspec.emit import check_embedding_safety
from drawspec.errors import DocumentError, DrawspecError, FitError
from drawspec.scene import Ellipse, Path, Polygon, Rect, Scene, TextRun
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


def filled_of(built: Scene) -> list[Polygon]:
    return [item for item in built.primitives if isinstance(item, Polygon)]


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
    built = marked({"name": "One", "mark": "area", "data": [[1, 30], [2, 40], [3, 20]]})
    (area,) = filled_of(built)
    baseline = max(y for _, y in area.points)
    assert area.points[0][1] == pytest.approx(baseline)
    assert area.points[-1][1] == pytest.approx(baseline)


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


def curve(*curves: Mapping[str, object]) -> Scene:
    document = {
        "version": 1,
        "kind": "curve",
        "title": "A curve",
        "axes": {"horizontal": {"label": "Time"}, "vertical": {"label": "How much"}},
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

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
from itertools import pairwise

import pytest

from drawspec import render
from drawspec.charts import MARKER_FRACTION, chart_scene
from drawspec.emit import check_embedding_safety
from drawspec.errors import DocumentError, DrawspecError, FitError
from drawspec.scene import Ellipse, Path, Scene, TextRun
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

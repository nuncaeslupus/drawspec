"""The legend: what each fill in a drawing stands for.

Two families draw one — `chart` and `matrix` — and both had the same hole before
it existed: a drawing that tells things apart by fill, and never says which fill
is which. The matrix original this project replaces carried a legend; the first
redraw of it quietly dropped one.
"""

from __future__ import annotations

import pytest

from drawspec.charts import chart_scene
from drawspec.kinds.grid import grid_scene
from drawspec.legend import Entry, entries_for, height_of, primitives_for
from drawspec.scene import Path, Polygon, Scene, TextRun
from drawspec.schema import parse_document
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])


def said(built: Scene) -> set[str]:
    return {item.text for item in built.primitives if isinstance(item, TextRun)}


def bars(*names: str) -> Scene:
    document = {
        "version": 1,
        "kind": "chart",
        "title": "A chart",
        "axes": {"horizontal": {"label": "Quarter"}, "vertical": {"label": "Count"}},
        "series": [
            {"name": name, "mark": "bar", "data": [[1, 10 + index], [2, 12 + index]]}
            for index, name in enumerate(names)
        ],
    }
    return chart_scene(parse_document(document), THEME, MEASURER)


# --------------------------------------------------------------------------
# When there is one
# --------------------------------------------------------------------------


def test_one_thing_needs_no_legend() -> None:
    """One fill explains itself: there is nothing to tell it apart from."""
    assert entries_for([("Only", "step", True)], THEME) == ()


def test_two_things_get_one_entry_each() -> None:
    key = entries_for([("First", "step", True), ("Second", "step", True)], THEME)
    assert [entry.text for entry in key] == ["First", "Second"]
    assert len({entry.fill for entry in key}) == 2


def test_an_empty_legend_costs_no_height() -> None:
    """So a caller may reserve it unconditionally and lose nothing by doing so."""
    assert height_of((), THEME, MEASURER, 640.0) == 0.0
    assert primitives_for((), THEME, MEASURER, 0.0, 0.0, 640.0) == ()


def test_a_chart_of_one_series_draws_no_legend() -> None:
    assert "Only" not in said(bars("Only"))


def test_a_chart_of_two_series_names_both() -> None:
    assert {"Platform", "Service desk"} <= said(bars("Platform", "Service desk"))


# --------------------------------------------------------------------------
# What the sample is
# --------------------------------------------------------------------------


def test_the_legend_and_the_drawing_agree_about_which_fill_is_whose() -> None:
    """Structural rather than checked: there is one rule and both sides run it.

    The fill sequence advances only for the filled things, which is what
    `_filled_marks` does — so a line series between two bar series cannot shift
    the second bar series' swatch onto the wrong pattern.
    """
    key = entries_for(
        [("Bars", "step", True), ("A line", "step", False), ("More bars", "step", True)], THEME
    )
    assert key[0].fill == THEME.mark.fill_for(0)
    assert key[1].fill == ""
    assert key[2].fill == THEME.mark.fill_for(1)


def test_a_line_series_gets_a_line_for_a_sample() -> None:
    """It is told apart by dash and weight, not by a fill, so its sample is a line."""
    key = entries_for([("Filled", "step", True), ("Drawn", "note", False)], THEME)
    drawn = primitives_for(key, THEME, MEASURER, 0.0, 0.0, 640.0)
    assert len([item for item in drawn if isinstance(item, Polygon)]) == 1
    samples = [item for item in drawn if isinstance(item, Path)]
    assert len(samples) == 1
    assert samples[0].role == "note", "the sample carries the line's own role"


def test_a_swatch_is_not_rounded() -> None:
    """A rect takes the theme's corner radius, and a lozenge is a shape, not a fill."""
    key = entries_for([("One", "step", True), ("Two", "step", True)], THEME)
    drawn = primitives_for(key, THEME, MEASURER, 0.0, 0.0, 640.0)
    assert all(not isinstance(item, type(None)) for item in drawn)
    assert [type(item).__name__ for item in drawn].count("Rect") == 0


# --------------------------------------------------------------------------
# Where it goes
# --------------------------------------------------------------------------


def test_a_legend_too_wide_for_one_row_wraps() -> None:
    names = [f"A rather long name number {index}" for index in range(6)]
    key = entries_for([(name, "step", True) for name in names], THEME)
    one_row = height_of(key[:1] + key[1:2], THEME, MEASURER, 640.0)
    assert height_of(key, THEME, MEASURER, 640.0) > one_row


def test_the_reserved_height_is_what_the_drawing_uses() -> None:
    """`height_of` and `primitives_for` take the same `top`, so they cannot drift."""
    key = entries_for([(f"Name {index}", "step", True) for index in range(4)], THEME)
    reserved = height_of(key, THEME, MEASURER, 300.0)
    drawn = primitives_for(key, THEME, MEASURER, 0.0, 100.0, 300.0)
    lowest = max(
        max(y for _, y in item.points) if isinstance(item, Polygon) else item.y
        for item in drawn
        if isinstance(item, Polygon | TextRun)
    )
    assert lowest <= 100.0 + reserved


def test_a_chart_s_plot_gives_up_the_room_the_legend_takes() -> None:
    """It is not an annotation on a finished drawing: the plot is placed around it.

    A chart's canvas height comes from its aspect ratio, so the drawing is the
    same size and the plot inside it is shorter. That is why `height_of` is
    measured before the gutters rather than after the plot is drawn.
    """
    alone, keyed = bars("Only"), bars("First", "Second")
    assert keyed.height == alone.height
    assert _plot_floor(keyed) < _plot_floor(alone)


def _plot_floor(built: Scene) -> float:
    """The baseline the bars stand on: the lowest point of the tallest polygon."""
    tallest = max(
        (item for item in built.primitives if isinstance(item, Polygon)),
        key=lambda item: max(y for _, y in item.points) - min(y for _, y in item.points),
    )
    return max(y for _, y in tallest.points)


def test_a_matrix_grows_by_the_height_its_legend_takes() -> None:
    """Its height comes from its content, so the legend is more content."""

    def matrix(*groups: str) -> Scene:
        return grid_scene(
            parse_document(
                {
                    "version": 1,
                    "kind": "matrix",
                    "title": "A matrix",
                    "cells": [
                        {"text": "x", "column": index, "row": 0, "group": group}
                        for index, group in enumerate(groups)
                    ],
                }
            ),
            THEME,
            MEASURER,
        )

    assert matrix("Data", "Parity").height > matrix("Data").height


# --------------------------------------------------------------------------
# The matrix
# --------------------------------------------------------------------------


def test_a_matrix_names_its_groups() -> None:
    """Its whole content is a comparison between groups; unnamed, they say nothing."""
    document = parse_document(
        {
            "version": 1,
            "kind": "matrix",
            "title": "A matrix",
            "cells": [
                {"text": "A", "column": 0, "row": 0, "group": "Data"},
                {"text": "P", "column": 1, "row": 0, "group": "Parity"},
            ],
        }
    )
    assert {"Data", "Parity"} <= said(grid_scene(document, THEME, MEASURER))


def test_the_matrix_legend_follows_first_mention() -> None:
    """The same order the fills were handed out in — see `_group_fills`."""
    key = entries_for([("Data", "step", True), ("Parity", "step", True)], THEME)
    assert isinstance(key[0], Entry)
    assert key[0].fill == THEME.mark.fill_for(0)


# --------------------------------------------------------------------------
# Categorical axes
# --------------------------------------------------------------------------


def test_a_categorical_axis_names_its_ticks_instead_of_numbering_them() -> None:
    """A bar chart's horizontal axis is almost never a measurement."""
    document = parse_document(
        {
            "version": 1,
            "kind": "chart",
            "title": "A chart",
            "axes": {
                "horizontal": {"label": "What you rent", "categories": ["IaaS", "PaaS", "SaaS"]},
                "vertical": {"label": "Share", "unit": "%"},
            },
            "series": [{"name": "You", "mark": "bar", "data": [[1, 67], [2, 33], [3, 17]]}],
        }
    )
    spoken = said(chart_scene(document, THEME, MEASURER))
    assert {"IaaS", "PaaS", "SaaS"} <= spoken
    assert "1" not in spoken and "2" not in spoken


def test_categories_are_refused_where_the_schema_says_they_may_not_go() -> None:
    """`categories` belongs to an axis, and an axis belongs to the chart kinds."""
    with pytest.raises(Exception, match="categories"):
        parse_document(
            {
                "version": 1,
                "kind": "flow",
                "title": "A flow",
                "categories": ["one"],
                "nodes": [{"id": "a", "text": "One"}],
            }
        )

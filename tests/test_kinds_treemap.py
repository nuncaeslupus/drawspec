"""`treemap` — the parts of one known total, each by its area, each labelled inside itself.

The kind makes two promises, and both are asserted numerically. Every drawn
cell's share of the drawn total is its value's share of the whole, within 2 %,
after the gaps have been taken from the cells. And every part's words and value
are wholly inside its own cell — the clipping check made against the cell rather
than the canvas — or the document is refused with the part's pointer and the
merge that would fix it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from drawspec import render
from drawspec.errors import FitError
from drawspec.kinds.treemap import (
    GAP,
    TreemapDrawing,
    best_partition,
    bold,
    format_value,
    place,
    treemap_drawing,
)
from drawspec.scene import Polygon, TextLine
from drawspec.schema import parse_document, validate_document
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])
UNIT = THEME.scale["body"] / 11
REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "reference"
REFERENCES = sorted(REFERENCE.glob("treemap-*.json"))


def flat(**extra: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "version": 1,
        "kind": "treemap",
        "unit": "hours",
        "parts": [
            {"text": "Disk alerts", "amount": 74, "role": "emphasis"},
            {"text": "Certificate renewals", "amount": 41},
            {"text": "Real incidents", "amount": 38},
            {"text": "Access requests", "amount": 24},
            {"text": "Everything else", "amount": 20, "role": "note"},
        ],
    }
    document.update(extra)
    return document


def grouped(**extra: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "version": 1,
        "kind": "treemap",
        "unit": "GB",
        "groups": [
            {"id": "docker", "text": "`/var/lib/docker`"},
            {"id": "log", "text": "`/var/log`"},
        ],
        "parts": [
            {"text": "Dangling images", "amount": 61, "group": "docker"},
            {"text": "Build cache", "amount": 38, "group": "docker"},
            {"text": "Journal", "amount": 9, "group": "log"},
            {"text": "App logs", "amount": 6, "group": "log"},
            {"text": "Other", "amount": 4, "role": "note"},
        ],
    }
    document.update(extra)
    return document


def drawn(document: dict[str, Any]) -> TreemapDrawing:
    return treemap_drawing(parse_document(document), THEME, MEASURER)


def pointers(document: dict[str, Any]) -> list[str]:
    return [violation.pointer for violation in validate_document(document)]


def messages(document: dict[str, Any]) -> str:
    return "\n".join(violation.message for violation in validate_document(document))


def assert_proportional(drawing: TreemapDrawing, values: list[float]) -> None:
    """Each cell's share of the drawn total is its value's share, within 2 %."""
    areas = [drawing.cells[index][2] * drawing.cells[index][3] for index in range(len(values))]
    drawn_total, total = sum(areas), sum(values)
    for area, value in zip(areas, values, strict=True):
        assert abs(area / drawn_total - value / total) / (value / total) < 0.02


def assert_labels_inside(drawing: TreemapDrawing) -> None:
    """Every label's bounds lie inside its own cell."""
    for index, (left, top, width, height) in drawing.labels.items():
        x, y, w, h = drawing.cells[index]
        assert x < left and left + width < x + w, index
        assert y < top and top + height < y + h, index


def overlap(one: tuple[float, ...], two: tuple[float, ...]) -> bool:
    return (
        one[0] < two[0] + two[2]
        and two[0] < one[0] + one[2]
        and one[1] < two[1] + two[3]
        and two[1] < one[1] + one[3]
    )


# ---------------------------------------------------------------------------
# The references
# ---------------------------------------------------------------------------


def test_there_are_at_least_three_references() -> None:
    assert len(REFERENCES) >= 3


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_every_reference_draws_areas_in_proportion(path: Path) -> None:
    document = json.loads(path.read_text())
    assert render(document).startswith("<svg")
    assert_proportional(drawn(document), [part["amount"] for part in document["parts"]])


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_every_reference_labels_each_part_inside_its_own_cell(path: Path) -> None:
    drawing = drawn(json.loads(path.read_text()))
    assert_labels_inside(drawing)


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_cells_are_a_gap_apart_and_each_grouped_cell_is_inside_its_frame(path: Path) -> None:
    document = json.loads(path.read_text())
    drawing = drawn(document)
    cells = list(drawing.cells.values())
    gap = GAP * UNIT
    half = gap * 0.49

    def grown(cell: tuple[float, ...]) -> tuple[float, ...]:
        return (cell[0] - half, cell[1] - half, cell[2] + 2 * half, cell[3] + 2 * half)

    # Two cells grown by just under half a gap each still do not meet.
    for index, one in enumerate(cells):
        for two in cells[index + 1 :]:
            assert not overlap(grown(one), grown(two))
    for index, part in enumerate(document["parts"]):
        x, y, w, h = drawing.cells[index]
        assert x >= 0 and x + w <= drawing.scene.width + 1e-6
        assert y >= 0 and y + h <= drawing.scene.height + 1e-6
        if "group" in part:
            fx, fy, fw, fh = drawing.frames[part["group"]]
            assert fx < x and x + w < fx + fw and fy < y and y + h < fy + fh
            # Below its group's caption, never across it.
            caption = drawing.captions[part["group"]]
            assert caption[1] + caption[3] < y


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------


def test_areas_stay_in_proportion_after_the_gaps_for_a_wide_range_of_values() -> None:
    document = flat()
    document["parts"] = [
        {"text": "Big", "amount": 300},
        {"text": "Mid", "amount": 60},
        {"text": "Small", "amount": 20},
        {"text": "Tiny", "amount": 14},
    ]
    assert_proportional(drawn(document), [300, 60, 20, 14])


def test_with_groups_every_part_is_still_in_proportion_to_the_whole() -> None:
    document = grouped()
    assert_proportional(drawn(document), [part["amount"] for part in document["parts"]])


def test_parts_are_laid_out_largest_first_and_the_remainder_last() -> None:
    document = flat()
    document["parts"][4]["amount"] = 80  # the largest, but a `note`
    assert drawn(document).order == (0, 1, 2, 3, 4)


def test_equal_values_are_laid_out_in_written_order() -> None:
    document = flat()
    for part in document["parts"]:
        part["amount"] = 10
        part.pop("role", None)
    assert drawn(document).order == (0, 1, 2, 3, 4)
    first, second = drawn(document), drawn(document)
    assert first.cells == second.cells


def test_written_order_does_not_change_the_layout_of_unequal_values() -> None:
    document = flat()
    reversed_document = flat()
    reversed_document["parts"] = list(reversed(document["parts"]))
    one, two = drawn(document), drawn(reversed_document)
    count = len(document["parts"])
    for index in range(count):
        assert one.cells[index] == pytest.approx(two.cells[count - 1 - index])


def test_the_first_cut_is_across_the_longer_side() -> None:
    cells = place(
        best_partition([1.0, 1.0], (0.0, 0.0, 200.0, 100.0)), [1.0, 1.0], (0, 0, 200, 100)
    )
    assert cells[0] == pytest.approx((0, 0, 100, 100))
    assert cells[1] == pytest.approx((100, 0, 100, 100))


def test_the_search_prefers_cells_a_label_fits_over_better_shapes() -> None:
    weights = [2.0, 1.0, 1.0]
    rect = (0.0, 0.0, 240.0, 160.0)
    # By shape alone the two small parts share a column, 120 by 80 each.
    by_shape = place(best_partition(weights, rect), weights, rect)
    assert by_shape[1][3] == pytest.approx(80)
    # Labels that need 140 of height take two narrow full-height columns instead.
    sizes: list[tuple[tuple[float, float], ...]] = [
        ((10.0, 10.0),),
        ((50.0, 140.0),),
        ((50.0, 140.0),),
    ]
    by_label = place(best_partition(weights, rect, sizes), weights, rect)
    assert by_label[1][3] == pytest.approx(160) and by_label[2][3] == pytest.approx(160)


def test_a_top_level_height_is_the_block_height() -> None:
    drawing = drawn(flat(height=300))
    assert drawing.scene.height == 300
    assert drawing.scene.width == THEME.canvas.width


def test_a_label_that_needs_it_makes_the_block_taller_before_it_is_refused() -> None:
    document = flat()
    document["parts"][4]["text"] = "Everything else, in four lines"
    plain = drawn(flat())
    taller = drawn(document)
    assert taller.scene.height >= plain.scene.height
    assert_labels_inside(taller)


# ---------------------------------------------------------------------------
# Labels and roles
# ---------------------------------------------------------------------------


def test_values_are_written_with_their_unit_and_percent_takes_no_space() -> None:
    assert format_value(910, "kB") == "910 kB"
    assert format_value(12.5, "GB") == "12.5 GB"
    assert format_value(30, "%") == "30%"
    assert format_value(0.1 + 0.2, "") == "0.3"


def test_each_value_is_drawn_under_its_words_unless_values_is_false() -> None:
    texts = [p.text for p in drawn(flat()).scene.primitives if isinstance(p, TextLine)]
    assert "74 hours" in texts
    quiet = [p.text for p in drawn(flat(values=False)).scene.primitives if isinstance(p, TextLine)]
    assert not any("hours" in text for text in quiet)


def test_a_groups_caption_carries_its_name_and_total() -> None:
    lines = [p for p in drawn(grouped()).scene.primitives if isinstance(p, TextLine)]
    texts = [line.text for line in lines]
    assert "/var/lib/docker" in texts and "99 GB" in texts and "15 GB" in texts
    # The path is code, not bold with its backticks showing.
    path = next(line for line in lines if line.text == "/var/lib/docker")
    assert path.spans[0].font == "mono"


def test_bold_keeps_code_spans_as_code() -> None:
    assert bold("Why `/var` is full") == "**Why** `/var` **is** **full**"


def test_roles_draw_the_emphasis_heavy_and_bold_and_the_remainder_dashed() -> None:
    primitives = drawn(flat()).scene.primitives
    cells = [p for p in primitives if isinstance(p, Polygon)]
    assert sorted(cell.role for cell in cells) == ["emphasis", "note", "step", "step", "step"]
    bold_line = next(p for p in primitives if isinstance(p, TextLine) and p.text == "Disk alerts")
    assert bold_line.spans[0].weight == "bold"
    plain = next(p for p in primitives if isinstance(p, TextLine) and p.text == "Real incidents")
    assert plain.spans[0].weight == "normal"


def test_groups_take_the_themes_mark_fills_in_the_order_written() -> None:
    document = grouped()
    drawing = drawn(document)
    polygons = [p for p in drawing.scene.primitives if isinstance(p, Polygon)]
    frames = [p for p in polygons if p.role == "group"]
    assert len(frames) == 2
    fills = {p.fill for p in polygons if p.role != "group"}
    assert fills == {THEME.mark.fill_for(0), THEME.mark.fill_for(1), ""}


# ---------------------------------------------------------------------------
# The sliver refusal
# ---------------------------------------------------------------------------


def slivers() -> dict[str, Any]:
    return flat(
        parts=[
            {"text": "Video", "amount": 900},
            {"text": "Photos", "amount": 300},
            {"text": "Music library", "amount": 120},
            {"text": "Documents", "amount": 9},
            {"text": "Settings", "amount": 1},
        ],
        unit="MB",
    )


def test_a_part_too_small_for_its_words_is_refused_naming_it_and_the_merge() -> None:
    with pytest.raises(FitError) as caught:
        drawn(slivers())
    message = str(caught.value)
    assert "/parts/4" in message and "'Settings'" in message
    assert "Merge the parts of 9 MB or less" in message
    assert "`note` part" in message


def test_the_sliver_refusal_reaches_render_after_the_type_is_shrunk() -> None:
    with pytest.raises(FitError, match="never beside it"):
        render(slivers())


def test_a_group_name_wider_than_its_frame_is_refused_naming_the_group() -> None:
    document = grouped()
    document["groups"][1]["text"] = "Supercalifragilisticexpialidocious-logs"
    with pytest.raises(FitError, match=r"/groups/1"):
        drawn(document)


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def test_the_examples_are_valid() -> None:
    assert validate_document(flat()) == ()
    assert validate_document(grouped()) == ()


def test_one_part_is_refused() -> None:
    document = flat(parts=[{"text": "All of it", "amount": 1}])
    assert pointers(document) == ["/parts"]
    assert "one part of a total is the total" in messages(document)


@pytest.mark.parametrize("value", [0, -3])
def test_a_value_of_zero_or_less_is_refused(value: float) -> None:
    document = flat()
    document["parts"][1]["amount"] = value
    assert pointers(document) == ["/parts/1/amount"]
    assert "more than 0" in messages(document)


def test_a_part_with_no_value_is_refused() -> None:
    document = flat()
    del document["parts"][1]["amount"]
    assert pointers(document) == ["/parts/1/amount"]


def test_an_unknown_group_is_refused_with_the_closest() -> None:
    document = grouped()
    document["parts"][2]["group"] = "logs"
    assert "/parts/2/group" in pointers(document)
    assert "did you mean 'log'" in messages(document)


def test_a_group_on_a_treemap_with_no_groups_is_refused() -> None:
    document = flat()
    document["parts"][0]["group"] = "x"
    assert pointers(document) == ["/parts/0/group"]
    assert "no `groups`" in messages(document)


def test_a_group_with_no_parts_is_refused() -> None:
    document = grouped()
    document["groups"].append({"id": "tmp", "text": "`/var/tmp`"})
    assert pointers(document) == ["/groups/2"]
    assert "empty frame" in messages(document)


def test_duplicate_group_ids_are_refused() -> None:
    document = grouped()
    document["groups"][1]["id"] = "docker"
    assert "/groups/1/id" in pointers(document)


@pytest.mark.parametrize(
    ("where", "name", "expected"),
    [
        ("root", "edges", "nothing to connect"),
        ("part", "percent", "Write the amount"),
        ("part", "share", "Write the amount"),
        ("part", "children", "one level of grouping"),
        ("group", "parts", "names its group"),
        ("group", "groups", "never groups"),
        ("group", "group", "never groups"),
        ("part", "fill", "appearance is a property of the role"),
        ("part", "value", "its `amount`"),
    ],
)
def test_fields_a_treemap_has_no_place_for_are_refused_by_name(
    where: str, name: str, expected: str
) -> None:
    document = grouped()
    if where == "root":
        document[name] = []
        pointer = f"/{name}"
    elif where == "part":
        document["parts"][0][name] = 3
        pointer = f"/parts/0/{name}"
    else:
        document["groups"][0][name] = []
        pointer = f"/groups/0/{name}"
    assert pointers(document) == [pointer]
    assert expected in messages(document)


def test_more_than_ten_parts_is_past_the_budget() -> None:
    document = flat(parts=[{"text": f"Part {n}", "amount": 10} for n in range(11)])
    assert pointers(document) == ["/parts/10"]
    assert "`note` part" in messages(document)


def test_more_than_four_groups_is_past_the_budget() -> None:
    groups = [{"id": f"g{n}", "text": f"Group {n}"} for n in range(5)]
    parts = [{"text": f"Part {n}", "amount": 10, "group": f"g{n}"} for n in range(5)]
    document = flat(groups=groups, parts=parts)
    assert pointers(document) == ["/groups/4"]
    assert "one per group" in messages(document)

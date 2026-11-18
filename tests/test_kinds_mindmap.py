"""`mindmap` — one topic in the middle, its branches radiating to both sides.

The kind's promises: the main branches run clockwise from the top right in the
order written, split so the two sides balance and the first always on the right;
siblings read top to bottom in the order written; no line crosses a word and no
word touches another; an `emphasis` branch's line is heavy all the way back to
the centre, and a `note` is faint with everything under it. Cross-links are a
concept map, and are refused with that word.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

from drawspec import render
from drawspec.errors import FitError, ThemeError
from drawspec.geometry import fit
from drawspec.kinds.mindmap import MindmapDrawing, mindmap_drawing
from drawspec.schema import READABILITY_BUDGET, parse_document, validate_document
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
BOXED = load_theme({"version": 1, "mindmap": {"boxes": True}})
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])
REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "reference"
REFERENCES = sorted(REFERENCE.glob("mindmap-*.json"))


def move(**extra: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "version": 1,
        "kind": "mindmap",
        "centre": "The move",
        "branches": [
            {"text": "Before", "branches": [{"text": "Give notice"}, {"text": "Book the van"}]},
            {"text": "Paperwork", "branches": [{"text": "Change of address"}]},
            {
                "text": "The day",
                "role": "emphasis",
                "branches": [{"text": "Meter readings", "branches": [{"text": "Photos"}]}],
            },
            {"text": "After", "role": "note", "branches": [{"text": "Meet the neighbours"}]},
        ],
    }
    document.update(extra)
    return document


def drawn(document: dict[str, Any], theme: Any = THEME) -> MindmapDrawing:
    """The drawing at the type scale `render` settles on — the fit pass shrinks it."""
    parsed = parse_document(document)
    return fit(theme, lambda scaled: mindmap_drawing(parsed, scaled, MEASURER)).value


def pointers(document: dict[str, Any]) -> list[str]:
    return [violation.pointer for violation in validate_document(document)]


def messages(document: dict[str, Any]) -> str:
    return "\n".join(violation.message for violation in validate_document(document))


def leaves(branch: dict[str, Any]) -> int:
    children = branch.get("branches", [])
    return sum(leaves(child) for child in children) if children else 1


def overlaps(a: tuple[float, ...], b: tuple[float, ...], inset: float = 0.5) -> bool:
    return (
        a[0] + inset < b[2] - inset
        and b[0] + inset < a[2] - inset
        and a[1] + inset < b[3] - inset
        and b[1] + inset < a[3] - inset
    )


# -- the references -----------------------------------------------------------


def test_there_are_at_least_three_reference_maps() -> None:
    assert len(REFERENCES) >= 3


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_every_reference_renders_and_validates(path: Path) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    assert validate_document(document) == ()
    assert render(document).startswith("<svg")


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_the_two_sides_balance(path: Path) -> None:
    """The proposal's bound: the sides' leaf counts differ by at most the largest branch's."""
    document = json.loads(path.read_text(encoding="utf-8"))
    drawing = drawn(document)
    counts = [leaves(branch) for branch in document["branches"]]
    right = sum(counts[index] for index in drawing.right)
    left = sum(counts[index] for index in drawing.left)
    assert abs(right - left) <= max(counts)


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_main_branches_run_clockwise_from_the_top_right(path: Path) -> None:
    """Right side top to bottom, then the left side from the bottom up: the order written."""
    document = json.loads(path.read_text(encoding="utf-8"))
    drawing = drawn(document)
    assert drawing.right[0] == 0
    assert [*drawing.right, *reversed(drawing.left)] == list(range(len(document["branches"])))
    mains = {entry.path[0]: entry for entry in drawing.branches if entry.depth == 1}
    for side in (drawing.right, drawing.left):
        tops = [mains[index].ink[1] for index in side]
        assert tops == sorted(tops)
    centre = (drawing.centre[0] + drawing.centre[2]) / 2
    assert all(mains[index].ink[0] > centre for index in drawing.right)
    assert all(mains[index].ink[2] < centre for index in drawing.left)


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_siblings_read_top_to_bottom_in_the_order_written(path: Path) -> None:
    drawing = drawn(json.loads(path.read_text(encoding="utf-8")))
    by_parent: dict[tuple[int, ...], list[tuple[int, float]]] = {}
    for entry in drawing.branches:
        if entry.depth > 1:
            by_parent.setdefault(entry.path[:-1], []).append((entry.path[-1], entry.words[1]))
    for children in by_parent.values():
        ordered = sorted(children)
        assert [top for _, top in ordered] == sorted(top for _, top in ordered)


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_no_word_touches_another_or_the_centre(path: Path) -> None:
    drawing = drawn(json.loads(path.read_text(encoding="utf-8")))
    inks = [entry.ink for entry in drawing.branches]
    for index, ink in enumerate(inks):
        assert not overlaps(ink, drawing.centre)
        for other in inks[index + 1 :]:
            assert not overlaps(ink, other)


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_no_line_crosses_a_word(path: Path) -> None:
    """Every sampled point of every line is outside every branch's words."""
    drawing = drawn(json.loads(path.read_text(encoding="utf-8")))
    for line in drawing.lines:
        for x, y in line.points:
            for entry in drawing.branches:
                left, top, right, bottom = entry.words
                assert not (left + 1 < x < right - 1 and top + 1 < y < bottom - 1), (
                    line.to,
                    entry.text,
                )


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_the_map_fits_the_canvas(path: Path) -> None:
    drawing = drawn(json.loads(path.read_text(encoding="utf-8")))
    assert drawing.scene.width <= THEME.canvas.width + 1e-6


# -- roles --------------------------------------------------------------------


def test_the_line_to_an_emphasis_branch_is_heavy_from_the_centre() -> None:
    """Fishbone's rule, here: the path to the branch the map is about is one heavy stroke."""
    document = move()
    document["branches"][2]["role"] = "step"
    document["branches"][2]["branches"][0]["branches"][0]["role"] = "emphasis"
    lines = {line.to: line for line in drawn(document).lines}
    assert lines[(2,)].widths[0] > lines[(0,)].widths[0]
    assert lines[(2, 0)].widths[0] > lines[(0, 0)].widths[0]
    assert lines[(2, 0, 0)].widths[0] > THEME.mindmap.taper[2]


def test_a_note_is_faint_and_so_is_everything_under_it() -> None:
    drawing = drawn(move())
    roles = {entry.path: entry.role for entry in drawing.branches}
    lines = {line.to: line.role for line in drawing.lines}
    assert roles[(3,)] == roles[(3, 0)] == "note"
    assert lines[(3,)] == lines[(3, 0)] == "aside"
    assert lines[(0,)] == "flow"


def test_main_branches_are_boxed_and_twigs_sit_on_a_line() -> None:
    entries = {entry.path: entry for entry in drawn(move()).branches}
    assert entries[(0,)].boxed
    assert not entries[(0, 0)].boxed
    assert not entries[(3,)].boxed, "a note main branch is words on a line, not a box"


def test_the_theme_can_box_every_branch() -> None:
    entries = {entry.path: entry for entry in drawn(move(), BOXED).branches}
    assert entries[(0, 0)].boxed and entries[(2, 0, 0)].boxed


def test_lines_thin_from_the_centre_outwards() -> None:
    lines = {line.to: line for line in drawn(move()).lines}
    assert lines[(0,)].widths[0] > lines[(0, 0)].widths[0]
    assert lines[(0,)].widths[0] > lines[(0,)].widths[1]


def test_the_same_document_draws_the_same_way() -> None:
    assert render(move()) == render(move())


def test_the_split_balances_heights() -> None:
    """Six equal branches split three and three."""
    document = move(
        branches=[
            {"text": f"Branch {index}", "branches": [{"text": "a"}, {"text": "b"}]}
            for index in range(6)
        ]
    )
    drawing = drawn(document)
    assert drawing.right == (0, 1, 2)
    assert drawing.left == (5, 4, 3)


def test_a_long_leaf_is_wrapped_rather_than_refused() -> None:
    document = move()
    document["branches"][0]["branches"][0]["text"] = (
        "Give the landlord written notice a full month before the move"
    )
    drawing = drawn(document)
    assert drawing.scene.width <= THEME.canvas.width + 1e-6


def test_a_word_too_wide_for_any_branch_is_a_fit_error() -> None:
    document = move()
    document["branches"][0]["branches"][0]["text"] = "W" * 80
    with pytest.raises(FitError):
        render(document)


# -- refusals -----------------------------------------------------------------


def test_one_main_branch_is_a_tree() -> None:
    document = move(branches=[{"text": "Only"}])
    assert "/branches" in pointers(document)
    assert "`tree`" in messages(document)


def test_nine_main_branches_are_past_the_budget() -> None:
    document = move(branches=[{"text": f"Branch {index}"} for index in range(9)])
    assert "/branches/8" in pointers(document)
    assert "peers" in messages(document)


def test_thirty_one_branches_in_all_are_past_the_budget() -> None:
    branches: list[dict[str, Any]] = [
        {"text": f"B{main}", "branches": [{"text": f"L{main}.{leaf}"} for leaf in range(5)]}
        for main in range(5)
    ]
    branches[4]["branches"].append({"text": "one too many"})
    document = move(branches=branches)
    assert pointers(document) == ["/branches/4/branches/5"]
    assert "overview" in messages(document)


def test_a_fourth_level_is_refused_at_its_pointer() -> None:
    document = move()
    document["branches"][2]["branches"][0]["branches"][0]["branches"] = [{"text": "Deeper"}]
    assert pointers(document) == ["/branches/2/branches/0/branches/0/branches"]
    assert "a fourth level" in messages(document)


def test_edges_are_a_concept_map() -> None:
    document = move(edges=[{"from": "a", "to": "b"}])
    assert pointers(document) == ["/edges"]
    assert "concept map" in messages(document)
    assert "`flow`" in messages(document)


@pytest.mark.parametrize("name", ["links", "id"])
def test_a_cross_link_on_a_branch_is_a_concept_map(name: str) -> None:
    document = move()
    document["branches"][0][name] = ["paperwork"] if name == "links" else "before"
    assert pointers(document) == [f"/branches/0/{name}"]
    assert "concept map" in messages(document)


def test_a_side_is_a_coordinate() -> None:
    document = move()
    document["branches"][1]["side"] = "left"
    assert pointers(document) == ["/branches/1/side"]
    assert "balance" in messages(document)


def test_empty_words_are_refused() -> None:
    document = move(centre=" ")
    document["branches"][0]["branches"][1]["text"] = ""
    assert pointers(document) == ["/centre", "/branches/0/branches/1/text"]


def test_an_empty_branches_list_is_refused() -> None:
    document = move()
    document["branches"][1]["branches"] = []
    assert pointers(document) == ["/branches/1/branches"]


def test_a_shape_role_is_refused() -> None:
    document = move()
    document["branches"][0]["role"] = "decision"
    assert pointers(document) == ["/branches/0/role"]
    assert "`emphasis`" in messages(document)


def test_a_third_emphasis_is_refused() -> None:
    document = move()
    document["branches"][0]["role"] = "emphasis"
    document["branches"][1]["role"] = "emphasis"
    assert pointers(document) == ["/branches/2/role"]


def test_the_centre_is_required() -> None:
    document = move()
    del document["centre"]
    assert pointers(document) == ["/centre"]


def test_the_budget_is_owner_approved() -> None:
    assert dict(READABILITY_BUDGET["mindmap"]) == {"branches": 8, "branches*": 30}


# -- theme --------------------------------------------------------------------


def test_a_taper_that_thickens_outwards_is_refused() -> None:
    with pytest.raises(ThemeError, match="thickens"):
        load_theme({"version": 1, "mindmap": {"taper": [2.0, 4.0, 1.0]}})


def test_a_taper_needs_one_width_per_level() -> None:
    with pytest.raises(ThemeError, match="3 widths"):
        load_theme({"version": 1, "mindmap": {"taper": [4.0, 2.0]}})


def test_boxes_must_be_a_boolean() -> None:
    with pytest.raises(ThemeError, match="boxes"):
        load_theme({"version": 1, "mindmap": {"boxes": "yes"}})


def test_lines_leave_the_centre_fanned_out() -> None:
    """Main lines leave the centre's rounded end at different heights, not one point."""
    drawing = drawn(move())
    starts = {round(line.points[0][1], 3) for line in drawing.lines if len(line.to) == 1}
    assert len(starts) > 1
    assert all(math.isfinite(y) for y in starts)

"""`railroad` — a grammar's rules as syntax diagrams, tracks derived from expressions.

The kind's promises: every item says exactly one thing it is, and every `rule` box
names a rule that is defined or listed as external; the three boxes draw in three
shapes; a choice keeps its first alternative on the main line and stacks the rest
under it; a long rule wraps between the items of its top-level sequence; an item
too wide for a line of its own is refused at its pointer rather than drawn off the
canvas; and the text form is the same track on character cells.
"""

from __future__ import annotations

import json
import math
from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest

from drawspec import render
from drawspec.errors import FitError
from drawspec.kinds.railroad import RailroadDrawing, railroad_drawing
from drawspec.render import render_text
from drawspec.scene import Rect
from drawspec.schema import (
    RAILROAD_BOX_MAX,
    RAILROAD_BRANCH_MAX,
    RAILROAD_DEPTH_MAX,
    RAILROAD_RULE_MAX,
    parse_document,
    validate_document,
)
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])
REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "reference"
REFERENCES = sorted(REFERENCE.glob("railroad-*.json"))


def grammar(*rules: dict[str, Any], **extra: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "version": 1,
        "kind": "railroad",
        "rules": list(rules)
        or [
            {
                "name": "list",
                "expr": {
                    "seq": [
                        {"terminal": "["},
                        {
                            "repeat": {"rule": "item"},
                            "separator": {"terminal": ","},
                            "min": 0,
                        },
                        {"terminal": "]"},
                    ]
                },
            },
            {
                "name": "item",
                "expr": {"choice": [{"terminal": "true"}, {"special": "a number"}]},
            },
        ],
    }
    document.update(extra)
    return document


def rule(expr: dict[str, Any], name: str = "r") -> dict[str, Any]:
    return {"name": name, "expr": expr}


def drawn(document: dict[str, Any]) -> RailroadDrawing:
    return railroad_drawing(parse_document(document), THEME, MEASURER)


def refusals(document: dict[str, Any]) -> dict[str, str]:
    return {violation.pointer: violation.message for violation in validate_document(document)}


# -- the references -----------------------------------------------------------


def test_there_are_references_for_each_use_case() -> None:
    assert len(REFERENCES) >= 3


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_every_reference_validates_and_renders(path: Path) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    assert validate_document(document) == ()
    assert render(document).startswith("<svg")
    assert render_text(parse_document(document)).endswith("\n")


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_no_two_boxes_overlap_in_a_reference(path: Path) -> None:
    drawing = drawn(json.loads(path.read_text(encoding="utf-8")))
    boxes = [box for _, _, box in drawing.boxes]
    for index, (left, top, right, bottom) in enumerate(boxes):
        for other in boxes[index + 1 :]:
            apart = (
                right <= other[0] + 1e-6
                or other[2] <= left + 1e-6
                or bottom <= other[1] + 1e-6
                or other[3] <= top + 1e-6
            )
            assert apart, ((left, top, right, bottom), other)


def test_the_long_select_wraps_and_stays_on_the_canvas() -> None:
    document = json.loads((REFERENCE / "railroad-sql-select.json").read_text(encoding="utf-8"))
    drawing = drawn(document)
    assert drawing.rows[0] > 1, "the select rule is wider than the canvas, so it wraps"
    assert drawing.rows[1] == 1
    assert drawing.scene.width <= THEME.canvas.width + 1e-6
    for track in drawing.tracks:
        assert all(0 <= x <= THEME.canvas.width + 1e-6 for x, _ in track)


# -- the drawing ---------------------------------------------------------------


def test_each_box_draws_in_its_own_shape_and_its_words_once() -> None:
    svg = render(grammar())
    assert svg.count(">true<") == 1 and svg.count(">a number<") == 1
    drawing = drawn(grammar())
    rects = [primitive for primitive in drawing.scene.primitives if isinstance(primitive, Rect)]
    shapes = [shape for shape, _, _ in drawing.boxes if shape != "comment"]
    roles = dict(zip(shapes, (rect.role for rect in rects), strict=True))
    assert len(set(roles.values())) == 3 == len(roles)


def test_a_choice_keeps_its_first_alternative_on_the_main_line() -> None:
    drawing = drawn(
        grammar(
            rule({"choice": [{"terminal": "first"}, {"terminal": "second"}, {"terminal": "third"}]})
        )
    )
    mids = {words: (box[1] + box[3]) / 2 for _, words, box in drawing.boxes}
    assert mids["first"] < mids["second"] < mids["third"]
    entry = drawing.tracks[0][0][1]
    assert mids["first"] == pytest.approx(entry)


def test_an_optional_draws_a_bypass_over_its_item_and_a_repeat_a_loop_under_it() -> None:
    optional = drawn(grammar(rule({"optional": {"terminal": "x"}})))
    repeat = drawn(grammar(rule({"repeat": {"terminal": "x"}, "min": 1})))
    (_, _, (_, otop, _, obottom)) = optional.boxes[0]
    (_, _, (_, rtop, _, rbottom)) = repeat.boxes[0]
    assert min(y for track in optional.tracks for _, y in track) < otop
    assert max(y for track in optional.tracks for _, y in track) <= obottom + 1e-6
    assert max(y for track in repeat.tracks for _, y in track) > rbottom
    assert min(y for track in repeat.tracks for _, y in track) >= rtop - 1e-6


def test_turns_are_rounded_so_a_branch_meets_the_line_tangentially() -> None:
    drawing = drawn(grammar(rule({"choice": [{"terminal": "a"}, {"terminal": "b"}]})))
    bent = [track for track in drawing.tracks if len(track) > 4]
    assert bent, "a lower branch is a rounded path"
    for track in bent:
        # No corner: each piece turns at most an arc step's worth from the last.
        headings = [math.atan2(y1 - y0, x1 - x0) for (x0, y0), (x1, y1) in pairwise(track)]
        for before, after in pairwise(headings):
            turn = abs((after - before + math.pi) % (2 * math.pi) - math.pi)
            assert turn <= math.radians(15.0) + 1e-6


def test_an_item_too_wide_for_a_line_of_its_own_is_refused_at_its_pointer() -> None:
    wide = grammar(rule({"seq": [{"terminal": "a"}, {"terminal": "x" * 120}]}))
    with pytest.raises(FitError, match=r"/rules/0/expr/seq/1: .*rule of its own"):
        render(wide)


def test_a_narrow_canvas_wraps_more_lines() -> None:
    document = grammar(
        rule({"seq": [{"terminal": f"word{index}"} for index in range(12)]}),
    )
    wide = drawn(document)
    narrow = drawn({**document, "width": 300})
    assert narrow.rows[0] > wide.rows[0] >= 1


def test_a_comment_breaks_the_line_rather_than_crossing_its_words() -> None:
    drawing = drawn(grammar(rule({"seq": [{"terminal": "a"}, {"comment": "a note"}]})))
    (_, _, (left, top, right, bottom)) = next(box for box in drawing.boxes if box[0] == "comment")
    for track in drawing.tracks:
        for x, y in track:
            assert not (left + 1 < x < right - 1 and top < y < bottom)


# -- the text form -------------------------------------------------------------


def test_text_draws_the_same_track_on_cells() -> None:
    drawn_text = render_text(parse_document(grammar()))
    assert "list" in drawn_text and "item" in drawn_text
    assert "╭───╮" in drawn_text and "┌┄" in drawn_text and "┤ , ├" in drawn_text
    loop = render_text(parse_document(grammar(rule({"repeat": {"terminal": "a"}, "min": 1}))))
    assert "◀" in loop
    ascii_text = render_text(parse_document(grammar()), charset="ascii")
    assert all(ord(character) < 128 for character in ascii_text)
    assert "( [ )" in ascii_text and ": a number :" in ascii_text


def test_text_too_narrow_names_the_width_it_needs() -> None:
    document = parse_document(grammar(rule({"terminal": "a-rather-long-keyword"})))
    with pytest.raises(FitError, match=r"^/rules/0/expr: .*--width 32 or more"):
        render_text(document, width=20)
    assert "a-rather-long-keyword" in render_text(document, width=32)


# -- the refusals --------------------------------------------------------------


def test_an_item_must_say_what_it_is() -> None:
    found = refusals(grammar(rule({"min": 1})))
    assert "one of 'terminal'" in found["/rules/0/expr"]


def test_an_item_is_one_thing() -> None:
    found = refusals(grammar(rule({"terminal": "a", "rule": "b"})))
    assert "is one thing" in found["/rules/0/expr/rule"]


def test_a_repeat_must_say_its_min_and_it_is_zero_or_one() -> None:
    assert "'min'" in refusals(grammar(rule({"repeat": {"terminal": "a"}})))["/rules/0/expr/min"]
    found = refusals(grammar(rule({"repeat": {"terminal": "a"}, "min": 2})))
    assert "0 or 1" in found["/rules/0/expr/min"]


def test_separator_and_min_belong_to_a_repeat() -> None:
    found = refusals(grammar(rule({"optional": {"terminal": "a"}, "min": 1})))
    assert "belongs to a 'repeat'" in found["/rules/0/expr/min"]


def test_a_separator_is_one_box() -> None:
    found = refusals(
        grammar(
            rule(
                {
                    "repeat": {"terminal": "a"},
                    "min": 1,
                    "separator": {"seq": [{"terminal": ","}, {"terminal": ";"}]},
                }
            )
        )
    )
    assert "one box" in found["/rules/0/expr/separator"]


def test_a_rule_box_names_a_defined_or_external_rule() -> None:
    found = refusals(grammar(rule({"rule": "valu"}), rule({"terminal": "v"}, name="value")))
    assert "Did you mean 'value'?" in found["/rules/0/expr/rule"]
    assert refusals(grammar(rule({"rule": "elsewhere"}), external=["elsewhere"])) == {}


def test_external_names_are_used_and_not_defined_here() -> None:
    found = refusals(
        grammar(rule({"rule": "x"}), rule({"terminal": "t"}, name="x"), external=["x", "y"])
    )
    assert "not external" in found["/external/0"]
    assert "says nothing" in found["/external/1"]


def test_rule_names_are_unique() -> None:
    found = refusals(grammar(rule({"terminal": "a"}), rule({"terminal": "b"})))
    assert "already defined" in found["/rules/1/name"]


def test_a_seq_or_choice_of_one_is_refused() -> None:
    found = refusals(grammar(rule({"seq": [{"terminal": "a"}]})))
    assert "on its own" in found["/rules/0/expr/seq"]
    found = refusals(grammar(rule({"choice": [{"terminal": "a"}]})))
    assert "'optional'" in found["/rules/0/expr/choice"]


def test_optional_twice_is_refused() -> None:
    found = refusals(grammar(rule({"optional": {"optional": {"terminal": "a"}}})))
    assert "already optional" in found["/rules/0/expr/optional"]


def test_empty_and_multi_line_words_are_refused() -> None:
    found = refusals(grammar(rule({"seq": [{"terminal": " "}, {"special": "two\nlines"}]})))
    assert "needs words" in found["/rules/0/expr/seq/0/terminal"]
    assert "one line" in found["/rules/0/expr/seq/1/special"]


@pytest.mark.parametrize(
    ("field", "phrase"),
    [
        ("text", "'terminal', 'rule' or 'special'"),
        ("max", "count is never drawn"),
        ("default", "first branch"),
        ("x", "coordinates"),
        ("role", "drawn by what it is"),
    ],
)
def test_fields_an_author_reaches_for_are_refused_with_a_reason(field: str, phrase: str) -> None:
    found = refusals(grammar(rule({"terminal": "a", field: 1})))
    message = found[f"/rules/0/expr/{field}"]
    assert phrase.replace("'", "`") in message or phrase in message


def test_the_caps() -> None:
    many_rules = grammar(*(rule({"terminal": "t"}, name=f"r{n}") for n in range(13)))
    assert any(str(RAILROAD_RULE_MAX) in message for message in refusals(many_rules).values())
    boxes = grammar(rule({"seq": [{"terminal": "t"}] * (RAILROAD_BOX_MAX + 1)}))
    assert "boxes on one track" in refusals(boxes)["/rules/0/expr"]
    branches = grammar(rule({"choice": [{"terminal": "t"}] * (RAILROAD_BRANCH_MAX + 1)}))
    assert "alternatives" in refusals(branches)["/rules/0/expr/choice"]


def test_deep_nesting_is_refused_not_a_recursionerror() -> None:
    deep: dict[str, Any] = {"terminal": "x"}
    for _ in range(3000):
        deep = {"optional": deep}
    found = validate_document(grammar(rule(deep)))
    assert len(found) == 1
    assert f"{RAILROAD_DEPTH_MAX} at most" in found[0].message

"""`argument` — a claim, the points for and against it, and co-premises.

The kind's promises: every point is tagged with the theme's word for its stance
and every `against` box carries the hatch, so stance survives greyscale; each
co-premise group shares one bracket and one connector, so a box has one arrow per
separate reason; every connector arrives at the box it bears on from below; and
an objection to how co-premises combine is refused with the way to say it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from drawspec import render
from drawspec.errors import FitError, ThemeError
from drawspec.geometry import fit
from drawspec.kinds.argument import ArgumentDrawing, argument_drawing
from drawspec.schema import READABILITY_BUDGET, parse_document, validate_document
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])
REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "reference"
REFERENCES = sorted(REFERENCE.glob("argument-*.json"))


def contract(**extra: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "version": 1,
        "kind": "argument",
        "claim": "A binding contract was formed",
        "points": [
            {"id": "offer", "on": "claim", "stance": "for", "text": "The quote was an offer"},
            {
                "id": "accept",
                "on": "claim",
                "stance": "for",
                "with": ["offer"],
                "text": "The email accepted it",
            },
            {"id": "price", "on": "claim", "stance": "for", "text": "Price was agreed"},
            {"id": "counter", "on": "accept", "stance": "against", "text": "A counter-offer"},
            {"id": "enquiry", "on": "counter", "stance": "against", "text": "A mere enquiry"},
        ],
    }
    document.update(extra)
    return document


def drawn(document: dict[str, Any], theme: Any = THEME) -> ArgumentDrawing:
    """The drawing at the type scale `render` settles on."""
    parsed = parse_document(document)
    return fit(theme, lambda scaled: argument_drawing(parsed, scaled, MEASURER)).value


def pointers(document: dict[str, Any]) -> list[str]:
    return [violation.pointer for violation in validate_document(document)]


def messages(document: dict[str, Any]) -> str:
    return "\n".join(violation.message for violation in validate_document(document))


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
def test_stance_is_drawn_on_two_channels(path: Path) -> None:
    """Every `against` box is hatched and tagged `but`; every `for` box is plain, `because`."""
    document = json.loads(path.read_text(encoding="utf-8"))
    drawing = drawn(document)
    svg = render(document)
    for point in drawing.points:
        if point.role == "note":
            assert point.fill == ""
            continue
        assert point.fill == ("hatch" if point.stance == "against" else ""), point.id
    stances = [point["stance"] for point in document["points"]]
    assert svg.count(">because<") == stances.count("for")
    assert svg.count(">but<") == stances.count("against")


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_one_connector_per_separate_reason(path: Path) -> None:
    """The edge count is the points less the co-premise extras."""
    document = json.loads(path.read_text(encoding="utf-8"))
    drawing = drawn(document)
    extras = sum(len(members) - 1 for members, _ in drawing.brackets)
    assert len(drawing.connectors) == len(document["points"]) - extras


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_connectors_arrive_from_below_at_the_box_they_bear_on(path: Path) -> None:
    drawing = drawn(json.loads(path.read_text(encoding="utf-8")))
    boxes = {point.id: point.box for point in drawing.points}
    boxes["claim"] = drawing.claim
    for connector in drawing.connectors:
        left, _, right, bottom = boxes[connector.to]
        (x0, y0), (x1, y1) = connector.points[-2], connector.points[-1]
        assert x0 == pytest.approx(x1), "the last run is vertical"
        assert y1 == pytest.approx(bottom) and y0 > y1, "and arrives from below"
        assert left < x1 < right
        for (ax, ay), (bx, by) in zip(connector.points, connector.points[1:], strict=False):
            assert ax == pytest.approx(bx) or ay == pytest.approx(by), "square runs only"


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_no_box_touches_another_or_a_connector(path: Path) -> None:
    drawing = drawn(json.loads(path.read_text(encoding="utf-8")))
    boxes = [point.box for point in drawing.points] + [drawing.claim]
    for index, box in enumerate(boxes):
        for other in boxes[index + 1 :]:
            assert not overlaps(box, other)
    for connector in drawing.connectors:
        # A note is unboxed, so its line reaches down into its margin to its tag.
        others = [point.box for point in drawing.points if point.id not in connector.members] + [
            drawing.claim
        ]
        words = [point.words for point in drawing.points] + [point.tag for point in drawing.points]
        for (ax, ay), (bx, by) in zip(connector.points, connector.points[1:], strict=False):
            run = (min(ax, bx) - 0.1, min(ay, by), max(ax, bx) + 0.1, max(ay, by))
            for box in [*others, *words]:
                assert not overlaps(run, box, 1.0)


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_points_read_down_from_the_claim(path: Path) -> None:
    drawing = drawn(json.loads(path.read_text(encoding="utf-8")))
    for point in drawing.points:
        assert point.box[1] > drawing.claim[3]
    rows: dict[int, list[float]] = {}
    for point in drawing.points:
        rows.setdefault(point.depth, []).append(point.box[1])
    tops = [min(rows[depth]) for depth in sorted(rows)]
    assert tops == sorted(tops)


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_the_tag_sits_in_the_top_margin_at_the_left(path: Path) -> None:
    drawing = drawn(json.loads(path.read_text(encoding="utf-8")))
    for point in drawing.points:
        assert point.tag[3] <= point.words[1] + 0.01
        if point.role != "note":
            assert point.box[0] < point.tag[0] < point.words[0] + 0.01 or (
                point.tag[0] <= point.words[0] + 0.01
            )


# -- co-premises and layout ---------------------------------------------------


def test_co_premises_sit_side_by_side_under_one_bracket() -> None:
    drawing = drawn(contract())
    (members, (left, top, right, bottom)), *_ = drawing.brackets
    assert members == ("offer", "accept")
    boxes = {point.id: point.box for point in drawing.points}
    assert boxes["offer"][1] == pytest.approx(boxes["accept"][1])
    assert left > boxes["offer"][0] and right < boxes["accept"][2]
    assert bottom == pytest.approx(boxes["offer"][1])
    group = [c for c in drawing.connectors if c.members == ("offer", "accept")]
    assert len(group) == 1 and group[0].points[0][1] == pytest.approx(top)


def test_with_written_on_either_member_is_one_group() -> None:
    document = contract()
    del document["points"][1]["with"]
    document["points"][0]["with"] = ["accept"]
    assert [members for members, _ in drawn(document).brackets] == [("offer", "accept")]


def test_siblings_are_drawn_in_the_order_written() -> None:
    drawing = drawn(contract())
    lefts = {point.id: point.box[0] for point in drawing.points}
    assert lefts["offer"] < lefts["accept"] < lefts["price"]


def test_emphasis_and_note_connectors() -> None:
    document = contract()
    document["points"][4]["role"] = "emphasis"
    document["points"][2]["role"] = "note"
    roles = {c.members: c.role for c in drawn(document).connectors}
    assert roles[("enquiry",)] == "strong"
    assert roles[("price",)] == "weak"
    assert roles[("counter",)] == "flow"


def test_the_theme_names_the_tags_and_the_fill() -> None:
    theme = load_theme(
        {
            "version": 1,
            "argument": {"for_tag": "since", "against_tag": "however", "against_fill": "dots"},
        }
    )
    svg = render(contract(), theme)
    assert ">since<" in svg and ">however<" in svg and ">because<" not in svg
    fills = {point.id: point.fill for point in drawn(contract(), theme).points}
    assert fills["counter"] == "dots" and fills["offer"] == ""


def test_the_same_tag_for_both_stances_is_refused() -> None:
    with pytest.raises(ThemeError, match="tell a reason from an objection"):
        load_theme({"version": 1, "argument": {"for_tag": "so", "against_tag": "so"}})


def test_a_fill_that_hides_the_words_is_refused() -> None:
    with pytest.raises(ThemeError, match="against_fill"):
        load_theme({"version": 1, "argument": {"against_fill": "solid"}})


def test_a_word_too_wide_for_any_point_is_a_fit_error() -> None:
    document = contract()
    document["points"][0]["text"] = "W" * 90
    with pytest.raises(FitError):
        render(document)


def test_a_wide_row_wraps_before_it_is_refused() -> None:
    document = contract(
        points=[
            {
                "id": f"p{index}",
                "on": "claim",
                "stance": "for" if index % 2 else "against",
                "text": "A reason long enough to need wrapping somewhere",
            }
            for index in range(5)
        ]
    )
    assert drawn(document).scene.width <= THEME.canvas.width + 1e-6


def test_a_row_that_cannot_fit_names_itself() -> None:
    document = contract(
        points=[
            {"id": f"p{index}", "on": "claim", "stance": "for", "text": "Unbreakablewordhere"}
            for index in range(12)
        ]
    )
    with pytest.raises(FitError, match="row 1"):
        render(document)


# -- refusals -----------------------------------------------------------------


def test_an_unknown_on_is_refused_at_its_pointer() -> None:
    document = contract()
    document["points"][3]["on"] = "acceptance"
    assert pointers(document) == ["/points/3/on"]
    assert "Known ids" in messages(document)


def test_a_cycle_through_on_is_refused() -> None:
    document = contract()
    document["points"][1]["on"] = "counter"
    del document["points"][1]["with"]
    assert "/points/1/on" in pointers(document)
    assert "circle" in messages(document)


def test_a_point_on_itself_is_refused() -> None:
    document = contract()
    document["points"][2]["on"] = "price"
    assert pointers(document) == ["/points/2/on"]


def test_a_missing_stance_belongs_in_the_caption() -> None:
    document = contract()
    del document["points"][2]["stance"]
    assert pointers(document) == ["/points/2/stance"]
    assert "caption" in messages(document)


@pytest.mark.parametrize("stance", ["rebuttal", "objection"])
def test_a_third_stance_is_refused(stance: str) -> None:
    document = contract()
    document["points"][4]["stance"] = stance
    assert pointers(document) == ["/points/4/stance"]
    assert "`against` on the point it answers" in messages(document)


def test_with_naming_a_different_box_is_refused() -> None:
    document = contract()
    document["points"][1]["with"] = ["counter"]
    assert pointers(document) == ["/points/1/with/0"]
    assert "same box" in messages(document)


def test_with_naming_a_different_stance_is_refused() -> None:
    document = contract()
    document["points"][2]["stance"] = "against"
    document["points"][1]["with"] = ["offer", "price"]
    assert pointers(document) == ["/points/1/with/1"]
    assert "same way" in messages(document)


def test_with_naming_an_unknown_point_is_refused() -> None:
    document = contract()
    document["points"][1]["with"] = ["offr"]
    assert pointers(document) == ["/points/1/with/0"]


def test_a_group_of_five_is_refused() -> None:
    points: list[dict[str, Any]] = [
        {"id": f"p{index}", "on": "claim", "stance": "for", "text": f"Premise {index}"}
        for index in range(5)
    ]
    for index in range(1, 5):
        points[index]["with"] = [f"p{index - 1}"]
    document = contract(points=points)
    assert pointers(document) == ["/points/4/with"]
    assert "sub-argument" in messages(document)


@pytest.mark.parametrize("target", [["offer", "accept"], "offer+accept"])
def test_an_objection_to_a_co_premise_group_says_how_to_write_it(target: object) -> None:
    """The corpus's inference objection (A5): state the hidden premise, object to that."""
    document = contract()
    document["points"][3]["on"] = target
    assert pointers(document) == ["/points/3/on"]
    assert "inference objection" in messages(document)
    assert "`with` them" in messages(document)


def test_edges_are_refused_with_the_reason() -> None:
    document = contract(edges=[{"from": "offer", "to": "claim"}])
    assert pointers(document) == ["/edges"]
    assert "`on`" in messages(document)


def test_ids_are_unique_and_claim_is_reserved() -> None:
    document = contract()
    document["points"][2]["id"] = "offer"
    document["points"][4]["id"] = "claim"
    assert pointers(document)[:2] == ["/points/2/id", "/points/4/id"]


def test_a_fifth_level_is_refused() -> None:
    points: list[dict[str, Any]] = [{"id": "p0", "on": "claim", "stance": "for", "text": "Level 1"}]
    for index in range(1, 5):
        points.append(
            {"id": f"p{index}", "on": f"p{index - 1}", "stance": "against", "text": "Deeper"}
        )
    document = contract(points=points)
    assert pointers(document) == ["/points/4/on"]
    assert "4 at most" in messages(document)


def test_sixteen_points_are_past_the_budget() -> None:
    document = contract(
        points=[
            {"id": f"p{index}", "on": "claim", "stance": "for", "text": "A reason"}
            for index in range(16)
        ]
    )
    assert pointers(document) == ["/points/15"]
    assert "overview" in messages(document)


def test_empty_words_are_refused() -> None:
    document = contract(claim=" ")
    document["points"][0]["text"] = ""
    assert pointers(document) == ["/claim", "/points/0/text"]


def test_a_shape_role_is_refused() -> None:
    document = contract()
    document["points"][0]["role"] = "decision"
    assert pointers(document) == ["/points/0/role"]
    assert "Stance is not a role" in messages(document)


def test_the_budget() -> None:
    assert dict(READABILITY_BUDGET["argument"]) == {"points": 15}

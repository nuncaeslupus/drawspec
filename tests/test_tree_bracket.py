"""`tree` + `"style": "bracket"` — a tournament bracket or a cladogram.

The style's promises: every leaf on one outer edge, an inner node as far from it
as its deepest leaf, its row halfway between its first and last child's, joined
by square elbows; the root at the `left`, the `right` or in the `middle`; the
same in text, in box-drawing characters; and every refusal in
`docs/proposals/tree-bracket.md` at its JSON pointer.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path
from typing import Any

import pytest

from drawspec import render, render_text
from drawspec.errors import FitError
from drawspec.kinds.bracket import BracketDrawing, bracket_drawing
from drawspec.schema import BRACKET_LEAVES_MAX, load_document, parse_document, validate_document
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])
REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "reference"
REFERENCES = sorted(REFERENCE.glob("tree-bracket-*.json"))


def knockout(**extra: Any) -> dict[str, Any]:
    """Four teams, two semi-finals and a final, the scores on the edges."""
    document: dict[str, Any] = {
        "version": 1,
        "kind": "tree",
        "style": "bracket",
        "root": "right",
        "nodes": [
            {"id": "final", "text": "Ash"},
            {"id": "s1", "text": "Ash"},
            {"id": "s2", "text": "Elm"},
            {"id": "a", "text": "Ash"},
            {"id": "b", "text": "Beech"},
            {"id": "c", "text": "Cedar"},
            {"id": "e", "text": "Elm"},
        ],
        "edges": [
            {"from": "final", "to": "s1", "label": "2", "role": "strong"},
            {"from": "final", "to": "s2", "label": "1"},
            {"from": "s1", "to": "a", "label": "3", "role": "strong"},
            {"from": "s1", "to": "b", "label": "0"},
            {"from": "s2", "to": "c", "label": "1"},
            {"from": "s2", "to": "e", "label": "2"},
        ],
    }
    document.update(extra)
    return document


def cladogram(**extra: Any) -> dict[str, Any]:
    """A ladder of three splits, the inner nodes unnamed."""
    document: dict[str, Any] = {
        "version": 1,
        "kind": "tree",
        "style": "bracket",
        "nodes": [
            {"id": "root", "text": ""},
            {"id": "x", "text": ""},
            {"id": "y", "text": "Apes"},
            {"id": "fish", "text": "Fish"},
            {"id": "frog", "text": "Frog"},
            {"id": "ape", "text": "Gorilla"},
            {"id": "us", "text": "Human"},
        ],
        "edges": [
            {"from": "root", "to": "fish"},
            {"from": "root", "to": "x"},
            {"from": "x", "to": "frog"},
            {"from": "x", "to": "y"},
            {"from": "y", "to": "ape"},
            {"from": "y", "to": "us"},
        ],
    }
    document.update(extra)
    return document


def drawn(document: dict[str, Any]) -> BracketDrawing:
    return bracket_drawing(parse_document(document), THEME, MEASURER)


def pointers(document: dict[str, Any]) -> list[str]:
    return [violation.pointer for violation in validate_document(document)]


def messages(document: dict[str, Any]) -> str:
    return "\n".join(violation.message for violation in validate_document(document))


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------


def test_every_leaf_stands_on_one_outer_edge() -> None:
    for document in (knockout(), cladogram(), knockout(root="middle")):
        drawing = drawn(document)
        leaves = [
            drawing.lines[node["id"]][0][0]
            for node in document["nodes"]
            if not any(edge["from"] == node["id"] for edge in document["edges"])
        ]
        if document.get("root") == "middle":
            assert len({round(x, 6) for x in leaves}) == 2  # one edge per side
        else:
            assert len({round(x, 6) for x in leaves}) == 1


def test_a_tournament_reads_left_to_right_to_the_champion() -> None:
    drawing = drawn(knockout())
    first_round = drawing.lines["a"][0][0]
    semi = drawing.lines["s1"][0][0]
    final = drawing.lines["final"][0][0]
    assert first_round < semi < final
    # The root's line runs on to the right of its elbow: the champion's.
    assert drawing.lines["final"][1][0] > final
    assert "final" in drawing.words


def test_a_cladogram_puts_the_root_left_and_the_names_past_the_tips() -> None:
    drawing = drawn(cladogram())
    tip = drawing.lines["fish"][0][0]
    root = drawing.lines["root"][0][0]
    assert root < tip
    for leaf in ("fish", "frog", "ape", "us"):
        assert drawing.words[leaf][0] > tip
    # A ladder climbs one step per split: each split nearer the tips than the last.
    assert drawing.lines["root"][0][0] < drawing.lines["x"][0][0] < drawing.lines["y"][0][0]
    # An unnamed split has no words.
    assert "root" not in drawing.words and "x" not in drawing.words


def test_elbows_are_square_and_an_inner_row_is_halfway_between_its_children() -> None:
    drawing = drawn(knockout())
    for identifier, points in drawing.lines.items():
        for (x0, y0), (x1, y1) in itertools.pairwise(points):
            assert x0 == pytest.approx(x1) or y0 == pytest.approx(y1), identifier
    first, last = drawing.lines["a"][0][1], drawing.lines["b"][0][1]
    assert drawing.lines["s1"][0][1] == pytest.approx((first + last) / 2)


def test_the_score_is_by_the_elbow_and_the_name_at_the_line_s_own_end() -> None:
    drawing = drawn(knockout())
    line = drawing.lines["a"]
    assert drawing.words["a"][0] < drawing.labels["a"][0]
    assert drawing.labels["a"][2] < line[1][0]  # the label ends before the elbow
    # Words and labels sit over their line, never across another.
    for identifier, rect in (*drawing.words.items(), *drawing.labels.items()):
        assert rect[3] < drawing.lines[identifier][0][1], identifier


def test_a_two_sided_bracket_meets_in_the_middle_with_the_root_over_it() -> None:
    drawing = drawn(knockout(root="middle"))
    left, right = drawing.lines["s1"], drawing.lines["s2"]
    assert left[1][0] == pytest.approx(right[1][0])
    assert left[0][0] < left[1][0] < right[0][0]
    stub = drawing.lines["final"]
    assert stub[0][0] == pytest.approx(stub[1][0]) and stub[1][1] < stub[0][1]
    assert drawing.words["final"][3] < stub[1][1]


def test_strong_edges_are_drawn_heavy() -> None:
    svg = render(knockout())
    assert svg.count('stroke-width="1"') > 0
    heavy = [part for part in svg.split("<path")[1:] if 'stroke-width="1"' not in part]
    assert len(heavy) >= 3  # the champion's two elbows and the final's line


def test_no_words_overlap() -> None:
    for document in (knockout(), cladogram(), knockout(root="middle")):
        drawing = drawn(document)
        rects = [*drawing.words.values(), *drawing.labels.values()]
        for index, a in enumerate(rects):
            for b in rects[index + 1 :]:
                apart = a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]
                assert apart, (a, b)


def test_too_wide_a_bracket_is_a_fit_error_naming_the_longest_name() -> None:
    document = knockout(width=120.0)
    with pytest.raises(FitError, match="/nodes/"):
        drawn(document)


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_reference_documents_render(path: Path) -> None:
    document = load_document(path)
    assert document.tree_style == "bracket"
    assert render(json.loads(path.read_text(encoding="utf-8"))).startswith("<svg")


def test_the_boxed_tree_is_unchanged_by_default() -> None:
    plain = knockout()
    del plain["style"], plain["root"]
    for edge in plain["edges"]:
        edge.pop("role", None)
    assert parse_document(plain).tree_style == "boxes"
    assert "<svg" in render(plain)


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------


def test_text_draws_square_elbows_with_the_words_inline() -> None:
    text = render_text(parse_document(knockout()))
    lines = text.splitlines()
    assert lines[0].startswith("Ash ") and lines[0].rstrip().endswith("┐")
    assert "┘" in lines[2] and "├" in lines[1]
    assert "━" in text  # the champion's run
    for word in ("Ash", "Beech", "Cedar", "Elm", " 3 ", " 0 "):
        assert word in text


def test_text_cladogram_names_past_the_tips_in_one_column() -> None:
    text = render_text(parse_document(cladogram()))
    columns = {
        line.index(name)
        for name in ("Fish", "Frog", "Gorilla", "Human")
        for line in text.splitlines()
        if name in line
    }
    assert len(columns) == 1
    assert "Apes" in text


def test_text_in_ascii_and_two_sided() -> None:
    text = render_text(parse_document(knockout(root="middle")), charset="ascii")
    assert text.isascii() and "+" in text and "=" in text
    assert text.splitlines()[0].strip() == "Ash"


def test_text_too_wide_is_refused_with_the_width_it_needs() -> None:
    with pytest.raises(FitError, match="--width"):
        render_text(parse_document(knockout()), width=20)


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def test_root_without_the_bracket_style_is_refused() -> None:
    document = cladogram(root="right")
    del document["style"]
    assert "/root" in pointers(document)


def test_a_root_at_the_top_says_a_bracket_reads_across() -> None:
    document = cladogram(root="top")
    assert pointers(document) == ["/root"]
    assert "reads across" in messages(document)


def test_a_second_parent_is_refused_at_the_edge() -> None:
    document = cladogram()
    document["edges"].append({"from": "x", "to": "ape"})
    assert "/edges/6/to" in pointers(document)


def test_a_node_of_one_child_is_refused() -> None:
    document = cladogram()
    document["nodes"].append({"id": "z", "text": ""})
    document["edges"][0] = {"from": "root", "to": "z"}
    document["edges"].append({"from": "z", "to": "fish"})
    assert "/nodes/7" in pointers(document)
    assert "one child" in messages(document)


def test_two_roots_are_refused_at_the_second() -> None:
    document = cladogram()
    document["nodes"].append({"id": "lone", "text": "Lone"})
    assert pointers(document) == ["/nodes/7"]


def test_a_cycle_is_refused() -> None:
    document = cladogram()
    document["edges"].append({"from": "us", "to": "root"})
    assert pointers(document) == ["/edges"]


def test_a_self_loop_is_refused() -> None:
    document = cladogram()
    document["edges"].append({"from": "us", "to": "us"})
    assert "/edges/6/to" in pointers(document)


def test_an_unnamed_leaf_is_refused() -> None:
    document = cladogram()
    document["nodes"][3]["text"] = ""
    assert pointers(document) == ["/nodes/3/text"]


@pytest.mark.parametrize(
    ("field", "value", "pointer"),
    [
        ("class", "x", "/nodes/3/class"),
        ("status", "added", "/nodes/3/status"),
        ("actor", "Me", "/nodes/3/actor"),
        ("role", "emphasis", "/nodes/3/role"),
        ("text", "Fish\nand more", "/nodes/3/text"),
    ],
)
def test_a_node_field_with_no_box_is_refused(field: str, value: str, pointer: str) -> None:
    document = cladogram()
    document["nodes"][3][field] = value
    assert pointer in pointers(document)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("groups", [{"id": "g", "members": ["fish"]}]),
        ("bands", [{"text": "b", "members": ["fish"]}]),
        ("classes", [{"id": "x", "text": "X"}]),
    ],
)
def test_a_document_field_with_no_box_is_refused(field: str, value: Any) -> None:
    document = cladogram(**{field: value})
    assert f"/{field}" in pointers(document)


@pytest.mark.parametrize(
    ("field", "value"),
    [("role", "weak"), ("status", "added"), ("label", "two\nlines")],
)
def test_an_edge_field_a_bracket_cannot_draw_is_refused(field: str, value: str) -> None:
    document = cladogram()
    document["edges"][0][field] = value
    assert f"/edges/0/{field}" in pointers(document)


def test_a_two_sided_bracket_needs_a_root_of_two() -> None:
    document = cladogram(root="middle")
    document["edges"].append({"from": "root", "to": "extra"})
    document["nodes"].append({"id": "extra", "text": "Extra"})
    assert "/root" in pointers(document)


def test_past_the_leaf_budget_is_refused_at_the_first_leaf_over() -> None:
    count = BRACKET_LEAVES_MAX + 1
    nodes = [{"id": "root", "text": ""}] + [
        {"id": f"l{i}", "text": f"Team {i}"} for i in range(count)
    ]
    edges = [{"from": "root", "to": f"l{i}"} for i in range(count)]
    document = cladogram(nodes=nodes, edges=edges)
    assert pointers(document) == [f"/nodes/{count}"]
    assert "region" in messages(document)


def test_a_bracket_of_sixteen_is_past_the_boxed_tree_s_node_budget() -> None:
    """A bracket counts its leaves: the cup's 31 nodes are refused only as boxes."""
    path = REFERENCE / "tree-bracket-cup.json"
    assert len(load_document(path).nodes) > 15
    boxed = json.loads(path.read_text(encoding="utf-8"))
    del boxed["style"], boxed["root"]
    assert "/nodes/15" in pointers(boxed)

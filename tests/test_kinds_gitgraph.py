"""`gitgraph` — commits on branches over time, forked, merged, tagged and picked.

The kind's promises: one lane per branch in the order written and one place in
time per step in the order written; a line between lanes only for a fork or a
merge, turning between two steps and never under a label; every history git
would refuse, or that would draw nothing new, refused at its pointer; and a text
form that draws the same history as `git log --graph` does, oldest first.
"""

from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path
from typing import Any

import pytest

from drawspec import render
from drawspec.errors import FitError, ThemeError
from drawspec.kinds import text_for
from drawspec.kinds.gitgraph import GitgraphDrawing, gitgraph_drawing, history
from drawspec.scene import Ellipse, Polygon, Rect
from drawspec.scene import Path as ScenePath
from drawspec.schema import (
    GITGRAPH_BRANCH_MAX,
    GITGRAPH_STEP_MAX,
    parse_document,
    validate_document,
)
from drawspec.text import TextMeasurer
from drawspec.theme import Theme, load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])
REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "reference"
REFERENCES = sorted(REFERENCE.glob("gitgraph-*.json"))


def graph(**extra: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "version": 1,
        "kind": "gitgraph",
        "branches": [{"name": "main"}, {"name": "feature", "from": "main"}],
        "steps": [
            {"on": "main", "id": "a", "text": "Initial commit"},
            {"on": "feature", "id": "b", "text": "Add the form"},
            {"on": "main", "id": "c", "text": "Fix a typo"},
            {"on": "feature", "id": "d", "text": "Validate the form"},
            {"on": "main", "merge": "feature", "tag": "v1.0"},
        ],
    }
    document.update(extra)
    return document


def drawn(document: dict[str, Any], theme: Theme = THEME) -> GitgraphDrawing:
    return gitgraph_drawing(parse_document(document), theme, MEASURER)


def refusals(document: dict[str, Any]) -> dict[str, str]:
    return {violation.pointer: violation.message for violation in validate_document(document)}


def overlaps(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
    return a[0] < b[2] - 0.5 and b[0] < a[2] - 0.5 and a[1] < b[3] - 0.5 and b[1] < a[3] - 0.5


# -- the references -----------------------------------------------------------


def test_there_are_references_in_both_directions() -> None:
    directions = {json.loads(path.read_text()).get("direction", "right") for path in REFERENCES}
    assert directions == {"right", "down"}


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_each_reference_validates_renders_and_keeps_its_words_apart(path: Path) -> None:
    document = json.loads(path.read_text())
    assert validate_document(document) == ()
    assert render(document).startswith("<svg")
    result = drawn(document, load_theme(document.get("theme") or None))
    for first, second in combinations(result.texts, 2):
        assert not overlaps(first, second), (first, second)


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_each_reference_has_a_text_form(path: Path) -> None:
    document = parse_document(json.loads(path.read_text()))
    for charset in ("unicode", "ascii"):
        text = text_for(document, 80, charset)
        assert len(text.splitlines()) >= len(document.git_steps)
        if charset == "ascii":
            assert text.isascii()


# -- placement ----------------------------------------------------------------


def test_one_lane_per_branch_in_the_order_written_and_steps_in_order() -> None:
    result = drawn(graph())
    assert result.lanes[0] < result.lanes[1]
    xs = [x for x, _ in result.marks]
    assert xs == sorted(xs) and len(set(xs)) == len(xs)
    ys = [y for _, y in result.marks]
    assert ys == [
        result.lanes[0],
        result.lanes[1],
        result.lanes[0],
        result.lanes[1],
        result.lanes[0],
    ]


def test_down_puts_time_down_the_page_and_the_labels_beside_every_lane() -> None:
    result = drawn(graph(direction="down"))
    ys = [y for _, y in result.marks]
    assert ys == sorted(ys) and len(set(ys)) == len(ys)
    right_of_lanes = max(result.lanes)
    words = [box for box in result.texts if box[1] > ys[0] - 20]
    assert all(box[0] > right_of_lanes for box in words[2:])


def test_a_fork_and_a_merge_each_draw_one_line_between_lanes() -> None:
    result = drawn(graph())
    assert len(result.connectors) == 2
    for points in result.connectors:
        assert len({round(y, 3) for _, y in points}) > 2, "a connector turns, with a curve"


def test_a_line_between_lanes_turns_between_two_steps() -> None:
    result = drawn(graph())
    xs = [x for x, _ in result.marks]
    for points in result.connectors:
        # The vertical run: the points strictly between the two lanes.
        lanes = sorted(result.lanes)
        middle = [x for x, y in points if lanes[0] + 1 < y < lanes[1] - 1]
        assert middle
        assert not any(abs(x - mark) < 4 for x in middle for mark in xs)


def test_history_replays_parents_as_git_would() -> None:
    commits = history(parse_document(graph()))
    assert [commit.parent for commit in commits] == [None, 0, 0, 1, 2]
    assert commits[4].kind == "merge" and commits[4].merged == 3
    assert commits[1].starts and not commits[3].starts


def test_a_pick_copies_its_original_label_and_draws_a_dashed_ring() -> None:
    document = graph()
    document["steps"].append({"on": "feature", "id": "e", "text": "Hotfix"})
    document["steps"].append({"on": "main", "pick": "e"})
    assert validate_document(document) == ()
    commits = history(parse_document(document))
    assert commits[-1].kind == "pick" and commits[-1].label == "Hotfix"
    scene = drawn(document).scene
    assert any(isinstance(p, Ellipse) and p.role == "note" for p in scene.primitives)


def test_a_pick_of_a_pick_keeps_the_original_label() -> None:
    document = graph(
        branches=[
            {"name": "main"},
            {"name": "release", "from": "main"},
            {"name": "support", "from": "main"},
        ],
        steps=[
            {"on": "main", "text": "Start"},
            {"on": "release", "text": "Cut"},
            {"on": "support", "text": "Branch"},
            {"on": "main", "id": "fix", "text": "Fix the VAT"},
            {"on": "release", "id": "copy", "pick": "fix"},
            {"on": "support", "pick": "copy"},
        ],
    )
    assert validate_document(document) == ()
    commits = history(parse_document(document))
    assert commits[-1].label == "Fix the VAT"


def test_emphasis_is_a_square_mark_and_a_heavy_lane() -> None:
    document = graph()
    document["branches"][1]["role"] = "emphasis"
    document["steps"][2]["role"] = "emphasis"
    scene = drawn(document).scene
    assert any(isinstance(p, Polygon) and p.role == "emphasis" for p in scene.primitives)
    assert any(isinstance(p, ScenePath) and p.role == "strong" for p in scene.primitives)


def test_a_colour_theme_fills_the_dots_and_washes_the_names() -> None:
    theme = load_theme("accent")
    scene = drawn(graph(), theme).scene
    colours = {p.fill_colour for p in scene.primitives if isinstance(p, Ellipse) and p.fill}
    assert colours == set(theme.gitgraph.colours[:2])
    washed = [p for p in scene.primitives if isinstance(p, Rect) and p.fill_colour]
    assert len(washed) == 2 and all(p.fill_opacity < 1 for p in washed)
    plain = drawn(graph()).scene
    assert {p.fill_colour for p in plain.primitives if isinstance(p, Ellipse) and p.fill} == {
        "currentColor"
    }


def test_the_theme_refuses_a_colour_of_none_and_unknown_keys() -> None:
    with pytest.raises(ThemeError, match="none"):
        Theme.from_mapping({"version": 1, "gitgraph": {"colours": ["none"]}})
    with pytest.raises(ThemeError, match="unknown key"):
        Theme.from_mapping({"version": 1, "gitgraph": {"lanes": 3}})


def test_too_many_steps_across_a_narrow_page_is_a_fit_error() -> None:
    steps = [{"on": "main", "text": f"Commit number {n}"} for n in range(GITGRAPH_STEP_MAX)]
    document = graph(branches=[{"name": "main"}], steps=steps, width=300)
    with pytest.raises(FitError, match="direction: down"):
        drawn(document)


# -- text -------------------------------------------------------------------


def test_text_draws_the_fork_and_the_merge_with_corners() -> None:
    text = text_for(parse_document(graph()), 80, "unicode")
    lines = text.splitlines()
    assert lines[0].startswith("●") and "[main] Initial commit" in lines[0]
    assert any("┐" in line for line in lines), "the fork turns down into its lane"
    assert any("◉" in line and "(v1.0)" in line for line in lines)
    assert "[feature] Add the form" in text


def test_text_refuses_a_word_wider_than_its_column() -> None:
    document = graph()
    document["steps"][0]["text"] = "Supercalifragilisticexpialidocious"
    with pytest.raises(FitError, match="/steps/0/text"):
        text_for(parse_document(document), 30, "unicode")


# -- refusals -----------------------------------------------------------------


def test_the_example_is_valid() -> None:
    assert validate_document(graph()) == ()


@pytest.mark.parametrize(
    ("change", "pointer", "words"),
    [
        (lambda d: d["steps"].append({"on": "nope"}), "/steps/5/on", "not one of the branches"),
        (lambda d: d["steps"].append({"on": "main", "merge": "main"}), "/steps/5/merge", "itself"),
        (
            lambda d: d["steps"].append({"on": "main", "merge": "feature"}),
            "/steps/5/merge",
            "already in",
        ),
        (lambda d: d["steps"].append({"on": "main", "pick": "zz"}), "/steps/5/pick", "not any"),
        (lambda d: d["steps"].append({"on": "main", "pick": "b"}), "/steps/5/pick", "already"),
        (
            lambda d: (
                d["steps"][4].update(id="m") or d["steps"].append({"on": "feature", "pick": "m"})
            ),
            "/steps/5/pick",
            "merge commit",
        ),
        (lambda d: d["steps"][1].update(merge="main"), "/steps/1/merge", "first commit"),
        (lambda d: d["steps"][0].update(merge="feature"), "/steps/0/merge", "a commit on"),
        (
            lambda d: d["branches"].append({"name": "idle"}),
            "/branches/2",
            "no commit",
        ),
        (lambda d: d["branches"][0].update({"from": "feature"}), "/branches/0/from", "trunk"),
        (lambda d: d["branches"][1].update({"from": "zz"}), "/branches/1/from", "neither"),
        (lambda d: d["branches"][1].update({"from": "c"}), "/branches/1/from", "written after"),
        (lambda d: d["branches"][1].update(name="main"), "/branches/1/name", "twice"),
        (lambda d: d["steps"][1].update(id="a"), "/steps/1/id", "twice"),
        (lambda d: d["steps"][1].update(id="main"), "/steps/1/id", "branch's name"),
        (lambda d: d["steps"][1].update(tag="v1.0"), "/steps/4/tag", "two commits"),
        (lambda d: d["steps"][4].update(pick="b"), "/steps/4/pick", "not both"),
        (lambda d: d["steps"][0].update(text=" "), "/steps/0/text", "empty"),
        (lambda d: d["steps"][0].update(lane=1), "/steps/0/lane", "lane"),
        (lambda d: d["steps"][0].update(parents=["x"]), "/steps/0/parents", "derived"),
        (lambda d: d["steps"][0].update(type="HIGHLIGHT"), "/steps/0/type", "role: emphasis"),
        (lambda d: d["steps"][0].update(branch="main"), "/steps/0/branch", "`on`"),
        (lambda d: d.update(direction="up"), "/direction", ""),
    ],
)
def test_each_refusal_is_at_its_pointer(change: Any, pointer: str, words: str) -> None:
    document = graph()
    change(document)
    found = refusals(document)
    assert pointer in found, found
    assert words in found[pointer]


def test_a_branch_cannot_fork_from_a_branch_with_no_commit_yet() -> None:
    document = graph(
        branches=[{"name": "main"}, {"name": "a", "from": "b"}, {"name": "b", "from": "main"}],
        steps=[
            {"on": "main"},
            {"on": "a"},
            {"on": "b"},
        ],
    )
    assert "has no commit yet" in refusals(document)["/steps/1/on"]


def test_the_budget_caps_branches_and_steps() -> None:
    branches = [{"name": "main"}] + [
        {"name": f"b{n}", "from": "main"} for n in range(GITGRAPH_BRANCH_MAX)
    ]
    steps = [{"on": branch["name"]} for branch in branches]
    found = refusals(graph(branches=branches, steps=steps))
    assert any("branches" in message for message in found.values())
    steps = [{"on": "main"} for _ in range(GITGRAPH_STEP_MAX + 1)]
    found = refusals(graph(branches=[{"name": "main"}], steps=steps))
    assert any("steps" in message for message in found.values())


def test_more_than_two_emphasised_is_refused() -> None:
    document = graph()
    for index in range(3):
        document["steps"][index]["role"] = "emphasis"
    assert "/steps/2/role" in refusals(document)

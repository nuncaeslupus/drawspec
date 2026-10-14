"""Text output, phase 2: the graph kinds — `flow`, `states`, `lanes` — on a character grid.

The proposal (`docs/proposals/text.md`, phase 2) places the boxes by the layered
engine's ranks and order, routes every edge through free cells, and refuses
what would print as noise. These are its gates, over every reference document
of the three kinds (the gallery draws the same ones) and each kind's minimal
example, in both character sets:

* the phase-1 invariants — no line wider than the width in terminal cells,
  every label said, ASCII bytes below 128, no trailing whitespace;
* **every edge touches both its boxes**: its first cell is beside its source,
  its last beside its target, and both are drawn;
* **a drawn crossing is a counted one**: the `┼` in the drawing are exactly the
  crossings the router made, and no other junction is drawn so;
* the **text budget** refuses at the document, pointing at SVG;
* a golden file per kind per charset;
* **the width table**: every reference document of the graph kinds, and the
  seven sequences, at 80, 100 and 120 columns — the measurement the owner asked
  for before the default width of these kinds is settled. It is asserted, so a
  layout change that moves a document across a width is a diff to this file.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Final

import pytest

from drawspec import render_text
from drawspec.errors import DrawspecError, FitError
from drawspec.examples import EXAMPLES
from drawspec.kinds import TEXT_KINDS
from drawspec.kinds.graphtext import (
    GRAPH_TEXT_KINDS,
    TEXT_CROSSINGS,
    TEXT_NODES,
    TextDrawing,
    attempts,
    chosen,
    text_drawing,
)
from drawspec.schema import Document, Edge, Node, load_document, parse_document
from drawspec.textgrid import cells, plain

REFERENCE: Final = Path(__file__).resolve().parent.parent / "docs" / "reference"
GOLDEN: Final = Path(__file__).resolve().parent / "golden" / "text"
UPDATE: Final = bool(os.environ.get("DRAWSPEC_UPDATE_GOLDEN"))
CHARSETS: Final = ("unicode", "ascii")

#: Reference documents a text form refuses by design, and where it points: a
#: band has no text form yet, and a full mesh crosses its own lines past the budget.
REFUSED: Final = {
    "flow-bands": "/bands",
    "flow-mesh": "/edges",
}

#: Reference documents that do not fit 80 columns, and the width each needs.
WIDER: Final = {
    "lanes-classes-claim": 83,
    "lanes-expense": 89,
    "lanes-phases-purchase": 105,
}

#: One reference document per graph kind, held as a golden file in each charset.
GOLDENS: Final = {
    "flow": "flow-retry",
    "states": "states-process",
    "lanes": "lanes-phases-loan",
}


def _references(kinds: tuple[str, ...]) -> Iterator[tuple[str, Path]]:
    for path in sorted(REFERENCE.glob("*.json")):
        if json.loads(path.read_text(encoding="utf-8"))["kind"] in kinds:
            yield path.stem, path


#: A tree with a second parent: drawn as a graph rather than refused.
CROSS_LINKED: Final = {
    "version": 1,
    "kind": "tree",
    "nodes": [
        {"id": "a", "text": "Root"},
        {"id": "b", "text": "Left"},
        {"id": "c", "text": "Right"},
        {"id": "d", "text": "Shared"},
    ],
    "edges": [
        {"from": "a", "to": "b"},
        {"from": "a", "to": "c"},
        {"from": "b", "to": "d"},
        {"from": "c", "to": "d", "label": "also"},
    ],
}

ALL: Final = {
    **{f"example-{kind}": parse_document(EXAMPLES[kind]) for kind in GRAPH_TEXT_KINDS},
    **{name: load_document(path) for name, path in _references(GRAPH_TEXT_KINDS)},
    "tree-cross-linked": parse_document(CROSS_LINKED),
}

#: Every document the gates run over: those with a text form.
FIXTURES: Final = {name: document for name, document in ALL.items() if name not in REFUSED}


def _width(name: str) -> int:
    return WIDER.get(name, 80)


def _drawn(name: str, charset: str) -> str:
    return render_text(FIXTURES[name], width=_width(name), charset=charset)


def _drawing(name: str, charset: str) -> TextDrawing:
    return chosen(FIXTURES[name], _width(name), charset)


def _labels(document: Document) -> tuple[list[str], list[str]]:
    """What the drawing must say: lines said whole, and lines said word by word.

    An edge's label is drawn as written, a line at a time. A box's words may be
    wrapped at spaces to fit, as the SVG wraps them, and so may a caption and a
    class's name; a lane's or a phase's name is drawn on one line.
    """
    whole = [line for edge in document.edges for line in plain(edge.label).split("\n")]
    whole += [plain(lane) for lane in document.lanes]
    whole += [plain(phase.text) for phase in document.phases]
    whole += [plain(group.text) for group in document.groups]
    words = [line for node in document.nodes for line in plain(node.label).split("\n")]
    words += [klass.text for klass in document.classes]
    words += [loop.text for loop in document.loops]
    words.append(document.caption)
    return (
        [line for line in whole if line.strip()],
        [plain(line) for line in words if line.strip()],
    )


# ---------------------------------------------------------------------------
# The phase-1 invariants, for the graph kinds
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("charset", CHARSETS)
@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_no_line_is_wider_than_the_width_in_terminal_cells(name: str, charset: str) -> None:
    overflow = [line for line in _drawn(name, charset).splitlines() if cells(line) > _width(name)]
    assert not overflow, overflow


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_every_label_is_said(name: str) -> None:
    """An edge's label whole on a line; a box's words, every one, where they wrap."""
    drawn = _drawn(name, "unicode")
    whole, words = _labels(FIXTURES[name])
    for label in whole:
        assert label in drawn, label
    for label in words:
        missing = [word for word in label.split() if word not in drawn]
        assert not missing, (label, missing)


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_an_ascii_drawing_is_bytes_below_128(name: str) -> None:
    assert all(byte < 128 for byte in _drawn(name, "ascii").encode("utf-8"))


@pytest.mark.parametrize("charset", CHARSETS)
@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_no_trailing_whitespace_and_one_final_newline(name: str, charset: str) -> None:
    drawn = _drawn(name, charset)
    assert drawn.endswith("\n") and not drawn.endswith("\n\n")
    assert all(line == line.rstrip() for line in drawn.split("\n"))


@pytest.mark.parametrize("name", sorted(WIDER))
def test_a_reference_document_wider_than_80_refuses_naming_the_width_it_needs(name: str) -> None:
    with pytest.raises(FitError, match=rf"^/.*--width {WIDER[name]} or more"):
        render_text(FIXTURES[name], width=80)


@pytest.mark.parametrize("width", [30, 50])
@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_the_width_a_refusal_names_is_enough(name: str, width: int) -> None:
    """A refusal is located and actionable: `--width N` from its message draws."""
    try:
        render_text(FIXTURES[name], width=width)
    except FitError as error:
        message = str(error)
        assert message.startswith("/"), message
        needed = re.search(r"--width (\d+) or more", message)
        assert needed, message
        assert int(needed.group(1)) > width, message
        render_text(FIXTURES[name], width=int(needed.group(1)))


# ---------------------------------------------------------------------------
# Routing: every edge drawn, touching both its boxes, crossings only where real
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("charset", CHARSETS)
@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_every_edge_touches_its_boxes_at_both_ends(name: str, charset: str) -> None:
    drawing = _drawing(name, charset)
    document = FIXTURES[name]
    assert {route.edge for route in drawing.routes} >= set(range(len(document.edges)))
    for route in drawing.routes:
        source, target = drawing.boxes[route.source], drawing.boxes[route.target]
        first, last = route.cells[0], route.cells[-1]
        assert source.beside(*first), (route, source)
        assert target.beside(*last), (route, target)
        for cell in route.cells:
            assert drawing.glyph(*cell).strip(), (route, cell)
        for left, right in zip(route.cells, route.cells[1:], strict=False):
            assert abs(left[0] - right[0]) + abs(left[1] - right[1]) == 1, route


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_no_route_runs_through_a_box(name: str) -> None:
    drawing = _drawing(name, "unicode")
    for route in drawing.routes:
        for identifier, box in drawing.boxes.items():
            if identifier in drawing.boxes and not _framed(drawing, identifier):
                assert not any(box.holds(*cell) for cell in route.cells), (route, identifier)


def _framed(drawing: TextDrawing, identifier: str) -> bool:
    """Whether an end is a group's frame, which a route crosses to reach what is inside."""
    box = drawing.boxes[identifier]
    return any(
        other != identifier
        and box.holds(inner.top, inner.left)
        and box.holds(inner.bottom, inner.right)
        for other, inner in drawing.boxes.items()
    )


CROSSING_GLYPHS: Final = "┼╋╂"


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_crossings_drawn_are_crossings_counted(name: str) -> None:
    drawing = _drawing(name, "unicode")
    drawn = sum(line.count(glyph) for line in drawing.lines for glyph in CROSSING_GLYPHS)
    assert drawn == drawing.crossings
    assert drawing.crossings <= TEXT_CROSSINGS


def test_some_reference_drawing_does_cross() -> None:
    """The crossing gate is not vacuous: at least one drawing crosses, and says so."""
    assert any(_drawing(name, "unicode").crossings for name in FIXTURES)


def test_a_drawing_is_tried_down_the_page_first() -> None:
    assert _drawing("flow-retry", "unicode").direction == "down"
    assert attempts(FIXTURES["flow-retry"])[0] == ("down", 0)
    # Eleven boxes with no edges are one rank: across the page, they are a column.
    assert _drawing("flow-node-roles", "unicode").direction == "right"


# ---------------------------------------------------------------------------
# The text budget
# ---------------------------------------------------------------------------


def _chain(count: int) -> Document:
    """A chain of `count` steps, built directly: the schema's own budget stops a
    document past fifteen nodes before any renderer sees it, and the text budget
    is held to the same number however it is reached."""
    nodes = tuple(Node(id=f"n{index}", text=f"Step {index}") for index in range(count))
    edges = tuple(Edge(f"n{index}", f"n{index + 1}") for index in range(count - 1))
    return Document(kind="flow", nodes=nodes, edges=edges)


def test_more_boxes_than_the_budget_refuses_at_the_nodes() -> None:
    render_text(_chain(TEXT_NODES), width=200)
    with pytest.raises(DrawspecError, match=rf"^/nodes: .*{TEXT_NODES + 1} boxes.*SVG"):
        render_text(_chain(TEXT_NODES + 1), width=200)


@pytest.mark.parametrize("name", sorted(REFUSED))
def test_a_refused_reference_document_points_at_the_document(name: str) -> None:
    with pytest.raises(DrawspecError) as refused:
        render_text(ALL[name], width=200)
    message = str(refused.value)
    assert message.startswith(f"{REFUSED[name]}: "), message
    assert "SVG" in message
    assert not isinstance(refused.value, FitError)


def test_crossings_past_the_budget_refuse_at_the_edges() -> None:
    with pytest.raises(
        DrawspecError, match=rf"cross each other \d+ times.*allows {TEXT_CROSSINGS}"
    ):
        render_text(ALL["flow-mesh"], width=200)


# ---------------------------------------------------------------------------
# Roles, states and lanes
# ---------------------------------------------------------------------------


def _flow(role: str = "step", edge: str = "flow") -> dict[str, Any]:
    return {
        "version": 1,
        "kind": "flow",
        "nodes": [{"id": "a", "text": "First"}, {"id": "b", "text": "Second", "role": role}],
        "edges": [{"from": "a", "to": "b", "role": edge}],
    }


NODE_ROLES: Final = (
    "step",
    "start",
    "decision",
    "terminal",
    "emphasis",
    "note",
    "group",
    "io",
    "subroutine",
    "store",
    "person",
)
EDGE_ROLES: Final = ("flow", "strong", "weak", "link", "aside", "exchange", "owns")


@pytest.mark.parametrize("charset", CHARSETS)
def test_every_node_role_draws_differently(charset: str) -> None:
    drawn = {role: render_text(parse_document(_flow(role)), charset=charset) for role in NODE_ROLES}
    assert len(set(drawn.values())) == len(NODE_ROLES)


@pytest.mark.parametrize("charset", CHARSETS)
def test_every_edge_role_draws_differently(charset: str) -> None:
    drawn = {
        role: render_text(parse_document(_flow(edge=role)), charset=charset) for role in EDGE_ROLES
    }
    assert len(set(drawn.values())) == len(EDGE_ROLES)


def test_the_role_glyphs() -> None:
    """The proposal's table on a graph: heavy, rounded, double; heads filled, open and none."""
    assert "┏" in render_text(parse_document(_flow("emphasis")))
    assert "╭" in render_text(parse_document(_flow("terminal")))
    assert "╔" in render_text(parse_document(_flow("start")))
    assert "< Second >" in render_text(parse_document(_flow("decision")))
    assert "▼" in render_text(parse_document(_flow()))
    assert "┃" in render_text(parse_document(_flow(edge="strong")))
    assert "▽" in render_text(parse_document(_flow(edge="weak")))
    linked = render_text(parse_document(_flow(edge="link")))
    assert not any(head in linked for head in "▼▲▶◀▽")
    assert "v" in render_text(parse_document(_flow()), charset="ascii")


def test_a_state_machine_has_its_dots_and_its_hooks() -> None:
    document = parse_document(EXAMPLES["states"])
    drawn = render_text(document)
    assert drawn.count("●") == 1
    process = render_text(FIXTURES["states-process"])
    assert "●" in process and "◉" in process
    ascii_process = render_text(FIXTURES["states-process"], charset="ascii")
    assert "(*)" in ascii_process
    retry = _drawing("flow-retry", "unicode")
    loops = [route for route in retry.routes if route.source == route.target]
    assert len(loops) == 2
    assert "timed out: retry" in render_text(FIXTURES["flow-retry"])


def test_a_fork_is_a_bar_and_a_composite_state_a_frame() -> None:
    drawn = render_text(FIXTURES["states-fork-order"])
    assert "━━━" in drawn
    assert "┌╌ Fulfilling" in drawn


def test_lanes_are_named_and_a_hand_off_crosses_their_rule() -> None:
    document = FIXTURES["lanes-phases-loan"]
    drawing = _drawing("lanes-phases-loan", "unicode")
    text = "\n".join(drawing.lines)
    for name in (*document.lanes, *(phase.text for phase in document.phases)):
        assert name in text
    assert "╎" in text and "╌" in text
    # A hand-off leaves one lane and arrives in another: some cell of its line is
    # drawn where the rule between them runs.
    dividers = {
        column for row in drawing.lines for column, character in enumerate(row) if character == "╎"
    }
    crossing = [
        route for route in drawing.routes if {column for _, column in route.cells} & dividers
    ]
    assert crossing


def test_every_graph_kind_has_a_text_form_and_a_golden() -> None:
    assert set(GRAPH_TEXT_KINDS) <= set(TEXT_KINDS)
    assert sorted(GOLDENS) == sorted(GRAPH_TEXT_KINDS)


@pytest.mark.parametrize("charset", CHARSETS)
@pytest.mark.parametrize("kind", sorted(GOLDENS))
def test_golden(kind: str, charset: str) -> None:
    name = GOLDENS[kind]
    drawn = _drawn(name, charset)
    path = GOLDEN / f"{name}.{charset}.txt"
    if UPDATE:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(drawn, encoding="utf-8")
    assert path.is_file(), f"{path} is missing: run with DRAWSPEC_UPDATE_GOLDEN=1 and read it"
    assert drawn == path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# The width table: what fits at 80, 100 and 120
# ---------------------------------------------------------------------------

WIDTHS: Final = (80, 100, 120)

#: Per kind: reference documents, refused (budget or no text form), then how
#: many fit at each width — in whichever arrangement, down the page only, and
#: across it only. Sequences have one arrangement. Measured; the owner decides
#: from this whether the graph kinds (and sequences) default to 100.
FIT_TABLE: Final = {
    "flow": {
        "documents": 26,
        "refused": 2,
        "any": (24, 24, 24),
        "down": (21, 21, 21),
        "right": (11, 16, 17),
    },
    "states": {
        "documents": 12,
        "refused": 0,
        "any": (12, 12, 12),
        "down": (12, 12, 12),
        "right": (1, 3, 5),
    },
    "lanes": {
        "documents": 9,
        "refused": 0,
        "any": (6, 8, 9),
        "down": (5, 7, 8),
        "right": (1, 2, 3),
    },
    "sequence": {"documents": 7, "refused": 0, "any": (4, 7, 7)},
}


def _fits(document: Document, width: int, direction: str | None) -> bool:
    """Whether a graph fits `width`, in any arrangement or only in one direction."""
    if direction is None:
        try:
            chosen(document, width, "unicode")
        except FitError:
            return False
        return True
    return any(
        drawing is not None and drawing.width <= width and drawing.crossings <= TEXT_CROSSINGS
        for way, wrap in attempts(document)
        if way == direction
        for drawing in (text_drawing(document, "unicode", way, wrap),)
    )


def _fit_table() -> dict[str, dict[str, Any]]:
    table: dict[str, dict[str, Any]] = {}
    for kind in (*GRAPH_TEXT_KINDS, "sequence"):
        documents = [load_document(path) for _, path in _references((kind,))]
        refused = 0
        counts: dict[str, list[int]] = {"any": [], "down": [], "right": []}
        drawable = []
        for document in documents:
            try:
                render_text(document, width=1000)
            except DrawspecError:
                refused += 1
                continue
            drawable.append(document)
        for width in WIDTHS:
            if kind == "sequence":
                fit = 0
                for document in drawable:
                    try:
                        render_text(document, width=width)
                        fit += 1
                    except FitError:
                        pass
                counts["any"].append(fit)
                continue
            counts["any"].append(sum(_fits(d, width, None) for d in drawable))
            counts["down"].append(sum(_fits(d, width, "down") for d in drawable))
            counts["right"].append(sum(_fits(d, width, "right") for d in drawable))
        table[kind] = {
            "documents": len(documents),
            "refused": refused,
            **{key: tuple(value) for key, value in counts.items() if value},
        }
    return table


def test_the_width_table(capsys: pytest.CaptureFixture[str]) -> None:
    """Prints, and holds, how many reference documents fit at 80, 100 and 120 columns."""
    table = _fit_table()
    with capsys.disabled():
        print()
        print(f"{'kind':10}{'docs':>5}{'refused':>8}   fits at " + " / ".join(map(str, WIDTHS)))
        for kind, row in table.items():
            ways = "".join(
                f"   {label} {'/'.join(map(str, row[key]))}"
                for key, label in (("down", "down"), ("right", "across"))
                if key in row
            )
            print(
                f"{kind:10}{row['documents']:>5}{row['refused']:>8}   "
                f"{'/'.join(map(str, row['any'])):>10}{ways}"
            )
    assert table == FIT_TABLE

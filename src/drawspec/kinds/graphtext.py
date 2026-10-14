"""Text for the graph kinds: `flow`, `states`, `lanes`, and a `tree` that is a graph.

Phase 2 of the text output (`docs/proposals/text.md`): the kinds whose lines go
anywhere, drawn on a character grid by the same three stages as their SVG —
place, route, label — and never by rounding the SVG's coordinates to cells.

**Placement is the layered engine's.** Ranks are `kinds.lanes.acyclic` and
`layout.base.rank_nodes` (for `lanes`, `kinds.lanes.ranked`, phases included),
the order within a rank `LayeredEngine`'s barycentre sweeps, and the position
across a rank its isotonic alignment under the parents — given box sizes in
cells and gaps in cells instead of points. An edge spanning ranks gets a
one-cell placeholder in each rank it passes, so the order leaves it a column.
A group is laid out the same way inside its own frame, and placed in its
parent's layout as one box; a composite state's regions sit side by side
inside theirs, divided by a dashed rule.

**Routing is a search through free cells.** Each edge is the cheapest
orthogonal path from a cell beside its source to a cell beside its target,
leaving and arriving square to the side, with a price on every bend, on
running beside a box, and on crossing a line already drawn. A box and a label
are never entered; a line already drawn is only ever crossed square, through
one of its straight cells, and that cell is drawn `┼` — so a drawn crossing is
a real one, and `TextDrawing.crossings` counts exactly the cells drawn so. A
lane's divider, a phase's rule and a frame's border are crossed the same way
but drawn as the edge, because crossing them is the hand-off they exist to show.

**Labels go beside their own line**, in the first free place along it from
its source: right or left of a vertical run, over or under a horizontal one,
with a space between the words and anything else. When an edge cannot be
routed or a label placed, the whole drawing is laid out again with wider gaps.

**Roles are glyphs, as in phase 1**: `emphasis` heavy, `terminal` rounded,
`start` double, `note` dashed, a `decision` between `<` and `>`, `io` between
slants, a `subroutine` with doubled sides, a `store` with a lid, a `person`
with a head on the box; a `strong` edge heavy, a `weak` one dashed with an open
head, `link` and `aside` headless. A state machine's initial dot is `●` and
its final one `◉` (`*` and `(*)` in ASCII), a fork or join a heavy bar, and a
transition to itself a hook on the box's side.

**Width decides the arrangement.** A drawing is tried down the page first —
a terminal is narrow and scrolls — with its boxes' words as written, then
wrapped narrower, then across the page, and the first that fits `width` is
drawn. None fitting refuses at the rightmost thing of the narrowest, with the
width it needs. Past a **text budget** — more boxes than `TEXT_NODES`, or more
crossings than `TEXT_CROSSINGS` however it is arranged — a drawing is refused
as noise, pointing at the document and at SVG.
"""

from __future__ import annotations

import heapq
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Final

from drawspec.errors import DrawspecError
from drawspec.filetree import STATUS_MARKS
from drawspec.kinds.graph import _with_pseudo_states, tree_text
from drawspec.kinds.lanes import acyclic, ranked
from drawspec.layout import LayeredEngine, LayoutEdge, LayoutNode, Spacing, rank_nodes
from drawspec.schema import STATE_BARS, Document, Edge
from drawspec.textgrid import (
    BOX_STYLE,
    BOXES,
    Grid,
    caption_lines,
    cells,
    finished,
    label_lines,
    line_style,
    pad,
    plain,
    spelt,
    too_wide,
    wrapped,
)

#: The most boxes a graph drawn as text holds. Past it the lines between them
#: are noise — the proposal's number, and the largest reference flow's size.
TEXT_NODES: Final = 15

#: The most crossings a graph drawn as text may have, in whichever arrangement
#: fits. Measured over the reference documents (see `tests/test_text_graph.py`):
#: none of them needs more, and a drawing that does is better read as SVG.
TEXT_CROSSINGS: Final = 3

#: The graph kinds this module draws.
GRAPH_TEXT_KINDS: Final = ("flow", "states", "lanes")

#: The widest a box's words are set, in cells, tried in turn: as written (0),
#: then narrower until the drawing fits. Each is tried down the page first.
TEXT_WRAPS: Final = (0, 24, 18, 14)

#: The two arrangements, in the order they are tried: ranks down the page, then
#: across it. For `lanes`, lanes as columns, then as rows.
TEXT_DIRECTIONS: Final = ("down", "right")

#: Empty cells kept round the placed drawing for routes that go round it.
MARGIN: Final = 4

#: What a route pays per cell, per bend, per crossing, and per cell beside a box.
STEP: Final = 1.0
BEND: Final = 2.0
CROSS: Final = 10.0
NEAR: Final = 2.0
CROWD: Final = 1.0
RULE: Final = 0.5

_N, _E, _S, _W = 0, 1, 2, 3
_SIDES: Final = "nesw"
_ANY: Final = (0, 1, 2, 3)
_DR: Final = (-1, 0, 1, 0)
_DC: Final = (0, 1, 0, -1)

#: Arrowheads by the way the line arrives — down, up, right, left — filled then open.
HEADS: Final = {
    "unicode": {_S: ("▼", "▽"), _N: ("▲", "△"), _E: ("▶", "▷"), _W: ("◀", "◁")},
    "ascii": {_S: ("v", "v"), _N: ("^", "^"), _E: (">", ">"), _W: ("<", "<")},
}

#: How each edge role ends: a filled head, an open one, a diamond, or none.
HEAD_KIND: Final = {
    "flow": "filled",
    "strong": "filled",
    "exchange": "filled",
    "weak": "open",
    "async": "open",
    "owns": "diamond",
    "link": "",
    "aside": "",
}

#: A tee where a line leaves a box, by the box's line weight and the side.
TEES: Final = {
    "light": {_S: "┬", _N: "┴", _E: "├", _W: "┤"},
    "heavy": {_S: "┯", _N: "┷", _E: "┠", _W: "┨"},
    "double": {_S: "╤", _N: "╧", _E: "╟", _W: "╢"},
}

#: The glyphs of a box's top and bottom, and of its sides, that a line may
#: join: every straight stretch of every role's box, in both charsets — never a
#: corner, a store's lid or a person's head.
SIDES_ACROSS: Final = frozenset("─━═┄┅-=.~")
SIDES_DOWN: Final = frozenset("│┃║┆┇|#:!<>/()")

#: The pseudo-states' dots, per charset.
DOTS: Final = {"unicode": {"initial": "●", "final": "◉"}, "ascii": {"initial": "*", "final": "(*)"}}

#: A fork's or join's bar, per charset: across the page, then down it.
BARS: Final = {"unicode": ("━", "┃"), "ascii": ("=", "#")}

#: The head of an `owns` edge: the part's end, a diamond.
DIAMONDS: Final = {"unicode": "◆", "ascii": "*"}

#: A rule — a lane's divider, a phase's, a region's — running across or down.
RULES: Final = {"unicode": ("╌", "╎"), "ascii": ("~", "!")}

#: A causal loop's letter in the key, by its type.
LOOP_LETTERS: Final = {"reinforcing": "R ", "balancing": "B "}


@dataclass(frozen=True)
class Rect:
    """Cells from (`top`, `left`), `height` rows by `width` columns."""

    top: int
    left: int
    height: int
    width: int

    @property
    def bottom(self) -> int:
        """The last row inside."""
        return self.top + self.height - 1

    @property
    def right(self) -> int:
        """The last column inside."""
        return self.left + self.width - 1

    def moved(self, rows: int, columns: int) -> Rect:
        return Rect(self.top + rows, self.left + columns, self.height, self.width)

    def holds(self, row: int, column: int) -> bool:
        return self.top <= row <= self.bottom and self.left <= column <= self.right

    def beside(self, row: int, column: int) -> bool:
        """Whether the cell is outside, sharing a side with a cell inside."""
        if self.holds(row, column):
            return False
        return any(self.holds(row + dr, column + dc) for dr, dc in zip(_DR, _DC, strict=True))


@dataclass(frozen=True)
class TextRoute:
    """One edge as drawn: its cells from beside its source to beside its target."""

    source: str
    target: str
    cells: tuple[tuple[int, int], ...]
    edge: int
    """Its index in the document's `edges`, or -1 for a pseudo-state's."""


@dataclass(frozen=True)
class TextDrawing:
    """A graph on cells, before its caption: what a test asks questions of."""

    lines: tuple[str, ...]
    boxes: Mapping[str, Rect]
    """Every end an edge can have — a box, a dot, a bar, a group's frame — by id."""

    routes: tuple[TextRoute, ...]
    crossings: int
    """Cells where two edges cross: each one drawn `┼`, and no other cell is."""

    direction: str
    width: int
    pointer: str
    """The thing furthest right, for a refusal at too narrow a width."""

    what: str

    def glyph(self, row: int, column: int) -> str:
        """The character drawn in a cell, a space for an empty one."""
        if not 0 <= row < len(self.lines):
            return " "
        at = 0
        for character in self.lines[row]:
            if at == column:
                return character
            at += cells(character)
            if at > column:
                return ""
        return " "


class _Unroutable(Exception):
    """An edge found no path, or a label no place, at these gaps."""


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def graph_text(document: Document, width: int, charset: str) -> str:
    """A `flow`, `states` or `lanes` document as plain text.

    Tried down the page with its words as written, then wrapped narrower, then
    across the page; the first arrangement that fits `width` within the
    crossing budget is drawn, with the caption and any causal loops' key under it.

    Raises:
        DrawspecError: past the text budget, or a part with no text form (bands).
        FitError: no arrangement fits `width`, at the narrowest one's rightmost
            thing, with the width it needs.
    """
    drawing = chosen(document, width, charset)
    return finished(
        [
            *drawing.lines,
            *_loop_key(document, width, charset),
            *caption_lines(document.caption, width, charset),
        ]
    )


def tree_graph_text(document: Document, width: int, charset: str) -> str:
    """A `tree`: on `files`' guides when it is one, as a graph when it has cross-links.

    A tree with a cross-link, a cycle or groups is a graph a guide cannot draw,
    so it is routed like a flow instead of refused.
    """
    if _guided(document):
        return tree_text(document, width, charset)
    return graph_text(document, width, charset)


def _guided(document: Document) -> bool:
    """Whether a tree hangs every node from one parent, with no groups: guides can draw it."""
    if document.groups:
        return False
    if document.bands:
        return True  # which `tree_text` refuses, as it did before
    parent: dict[str, str] = {}
    for edge in document.edges:
        if edge.target in parent or edge.target == edge.source:
            return False
        parent[edge.target] = edge.source
    reached: set[str] = set()
    children: dict[str, list[str]] = {}
    for edge in document.edges:
        children.setdefault(edge.source, []).append(edge.target)
    stack = [node.id for node in document.nodes if node.id not in parent]
    while stack:
        identifier = stack.pop()
        reached.add(identifier)
        stack.extend(children.get(identifier, ()))
    return len(reached) == len(document.nodes)


def chosen(document: Document, width: int, charset: str) -> TextDrawing:
    """The arrangement `graph_text` draws: the first that fits, within the budget.

    Raises:
        DrawspecError: past the text budget, or a part with no text form.
        FitError: nothing fits `width`.
    """
    _supported(document)
    narrowest: TextDrawing | None = None
    tangled: TextDrawing | None = None
    for direction, wrap in attempts(document):
        drawing = text_drawing(document, charset, direction, wrap)
        if drawing is None:
            continue
        if drawing.crossings > TEXT_CROSSINGS:
            if tangled is None or drawing.crossings < tangled.crossings:
                tangled = drawing
            continue
        if drawing.width <= width:
            return drawing
        if narrowest is None or drawing.width < narrowest.width:
            narrowest = drawing
    if narrowest is not None:
        raise too_wide(narrowest.pointer, narrowest.what, narrowest.width, width)
    if tangled is not None:
        raise DrawspecError(
            f"/edges: drawn as text, this {document.kind}'s lines cross each other "
            f"{tangled.crossings} times however it is arranged, and a text drawing allows "
            f"{TEXT_CROSSINGS}. Render it as SVG, or split it."
        )
    raise DrawspecError(f"/: this {document.kind} could not be drawn as text. Render it as SVG.")


def attempts(document: Document) -> list[tuple[str, int]]:
    """The arrangements tried, in order: each direction, words as written, then narrower.

    A wrap no box's words reach would draw the same thing again, so it is
    skipped — unless the document has regions, which the narrower attempts stack.
    """
    longest = max(
        (cells(line) for node in document.nodes for line in plain(node.label).split("\n")),
        default=0,
    )
    narrower = [wrap for wrap in TEXT_WRAPS[1:] if wrap < longest]
    if not narrower and any(group.region for group in document.groups):
        # The narrower attempt also stacks a composite state's regions.
        narrower = [TEXT_WRAPS[1]]
    wraps = [0, *narrower]
    return [(direction, wrap) for direction in TEXT_DIRECTIONS for wrap in wraps]


def _supported(document: Document) -> None:
    """Refuse what text cannot draw, and what it would draw as noise.

    Raises:
        DrawspecError: bands, or more boxes than the text budget.
    """
    if document.bands:
        raise DrawspecError(
            f"/bands: a {document.kind} with bands has no text form yet. Render it as SVG."
        )
    if len(document.nodes) > TEXT_NODES:
        raise DrawspecError(
            f"/nodes: this {document.kind} has {len(document.nodes)} boxes, and a text drawing "
            f"holds {TEXT_NODES} before its lines are noise. Split it, or render it as SVG."
        )


@lru_cache(maxsize=1024)
def text_drawing(document: Document, charset: str, direction: str, wrap: int) -> TextDrawing | None:
    """One arrangement of a graph on cells, gaps widened until every edge and label fits.

    `None` when no gap tried was enough — the next arrangement is tried instead.
    """
    for loosen in range(5):
        try:
            return _Plan(document, charset, direction, wrap, loosen).drawn()
        except _Unroutable:
            continue
    return None


def _loop_key(document: Document, width: int, charset: str) -> list[str]:
    """A causal loop diagram's loops, one per line under the drawing: letter, name, path."""
    if not document.loops:
        return []
    names = {node.id: plain(node.text).split("\n")[0] for node in document.nodes}
    arrow = " -> " if charset == "ascii" else " → "
    out = [""]
    for index, loop in enumerate(document.loops):
        path = arrow.join(names.get(identifier, identifier) for identifier in loop.nodes)
        first = names.get(loop.nodes[0], loop.nodes[0]) if loop.nodes else ""
        text = f"{LOOP_LETTERS.get(loop.type, '')}{plain(loop.text)}: {path}{arrow}{first}"
        pointer = f"/loops/{index}"
        out += wrapped(spelt(text, charset, pointer), width, pointer, width)
    return out


# ---------------------------------------------------------------------------
# Shapes
# ---------------------------------------------------------------------------


@dataclass
class _Leaf:
    """One box, dot or bar, drawn, with the hooks of its loops beside it."""

    id: str
    rows: list[str]
    kind: str
    """`box`, `dot` or `bar`."""

    style: str
    """The box's line weight, for its tees: `light`, `heavy` or `double`."""

    loops: list[tuple[int, str, str]] = field(default_factory=list)
    """Each self-loop: its edge's index, its role, and its label on one line."""

    offset: tuple[int, int] = (0, 0)
    """Where the box sits inside its extent: rows and columns of loop above and left."""

    extent: tuple[int, int] = (0, 0)
    """Rows and columns taken with the loops."""

    @property
    def height(self) -> int:
        return len(self.rows)

    @property
    def width(self) -> int:
        return max((cells(row) for row in self.rows), default=0)


def _box(lines: Sequence[str], role: str, charset: str) -> tuple[list[str], str]:
    """`lines` in the box a node role draws, and the box's line weight."""
    inner = max((cells(line) for line in lines), default=0)
    unicode = charset == "unicode"
    plain_box = BOXES[charset]["plain"]
    style = BOX_STYLE.get(role, "plain")
    glyphs = BOXES[charset][style]
    weight = "heavy" if style == "heavy" else "double" if style == "double" else "light"
    left, right = glyphs.left, glyphs.right
    top_left, top, top_right = glyphs.top_left, glyphs.top, glyphs.top_right
    bottom_left, bottom, bottom_right = glyphs.bottom_left, glyphs.bottom, glyphs.bottom_right
    lid: str | None = None
    if role == "decision":
        left, right = "<", ">"
    elif role == "io":
        left, right = "/", "/"
    elif role == "subroutine":
        left, right = plain_box.left * 2, plain_box.right * 2
    elif role == "group":
        top = bottom = "┅" if unicode else "~"
        left = right = "┇" if unicode else "!"
    elif role == "store":
        rounded = BOXES[charset]["rounded"]
        top_left, top_right = rounded.top_left, rounded.top_right
        bottom_left, bottom_right = rounded.bottom_left, rounded.bottom_right
        left, right = plain_box.left, plain_box.right
        lid = ("├" if unicode else "|") + plain_box.top * (inner + 2) + ("┤" if unicode else "|")
    span = inner + 2
    head = top * span
    if role == "person":
        middle = span // 2
        head = top * middle + ("○" if unicode else "o") + top * (span - middle - 1)
    rows = [top_left + head + top_right]
    if lid is not None:
        rows.append(lid)
    rows += [f"{left} {pad(line, inner)} {right}" for line in lines]
    rows.append(bottom_left + bottom * span + bottom_right)
    if len(left) == 2:
        rows[0] = top_left + top + head + top + top_right
        rows[-1] = bottom_left + bottom * (span + 2) + bottom_right
        if lid is not None:
            rows[1] = lid[0] + lid[1] * (span + 2) + lid[-1]
    return rows, weight


def _rewrapped(line: str, wrap: int) -> list[str]:
    """A line broken at spaces into lines of at most `wrap` cells; a longer word stays whole."""
    if not wrap or cells(line) <= wrap:
        return [line]
    out: list[str] = []
    current = ""
    for word in line.split(" "):
        candidate = f"{current} {word}" if current else word
        if current and cells(candidate) > wrap:
            out.append(current)
            current = word
        else:
            current = candidate
    out.append(current)
    return out


# ---------------------------------------------------------------------------
# Placement
# ---------------------------------------------------------------------------


@dataclass
class _Block:
    """A laid-out part of the drawing, in cells from its own top left."""

    height: int
    width: int
    leaves: dict[str, tuple[int, int]] = field(default_factory=dict)
    """Each leaf's extent's top left."""

    frames: dict[str, Rect] = field(default_factory=dict)
    rules: dict[tuple[int, int], str] = field(default_factory=dict)
    """Dividing cells, and which way the rule through each runs: `h` or `v`."""

    texts: list[tuple[int, int, str]] = field(default_factory=list)
    """Words placed with the layout: lanes' and phases' names."""

    def take(self, other: _Block, row: int, column: int) -> None:
        """Put `other` into this block with its top left at (`row`, `column`)."""
        for identifier, (top, left) in other.leaves.items():
            self.leaves[identifier] = (top + row, left + column)
        for identifier, rect in other.frames.items():
            self.frames[identifier] = rect.moved(row, column)
        for (top, left), way in other.rules.items():
            self.rules[(top + row, left + column)] = way
        self.texts += [(top + row, left + column, text) for top, left, text in other.texts]


class _Plan:
    """One attempt at a graph on cells: a direction, a wrap and a looseness."""

    def __init__(
        self, document: Document, charset: str, direction: str, wrap: int, loosen: int
    ) -> None:
        self.original = document
        self.document, self.markers = _with_pseudo_states(document)
        self.charset = charset
        self.down = direction == "down"
        self.direction = direction
        self.wrap = wrap
        self.rank_gap = 2 + (loosen + 1) // 2
        self.node_gap = (3 if self.down else 1) + 2 * loosen
        first = sum(
            1
            for edge in self.document.edges[: len(self.document.edges) - len(document.edges)]
            if edge.source in self.markers and self.markers[edge.source] == "initial"
        )
        self.indices = [
            position - first if 0 <= position - first < len(document.edges) else -1
            for position in range(len(self.document.edges))
        ]
        self.parent: dict[str, str] = {}
        for group in self.document.groups:
            for member in group.members:
                self.parent[member] = group.id
        self.groups = {group.id: group for group in self.document.groups}
        self.nodes = {node.id: node for node in self.document.nodes}
        self.written = {node.id: index for index, node in enumerate(document.nodes)}
        self.labels = [self._label(position) for position in range(len(self.document.edges))]
        self.leaves = {node.id: self._leaf(node.id) for node in self.document.nodes}

    # -- what is drawn ----------------------------------------------------

    def _label(self, position: int) -> list[str]:
        """An edge's label as drawn: its change's mark, its sign, its delay, its words."""
        edge = self.document.edges[position]
        index = self.indices[position]
        if index < 0:
            return []
        marks = []
        if edge.status:
            marks.append(STATUS_MARKS[edge.status])
        if edge.polarity:
            marks.append(edge.polarity)
        if edge.delay:
            marks.append("||" if self.charset == "ascii" else "‖")
        lines = label_lines(edge.label, self.charset, f"/edges/{index}/label") if edge.label else []
        lines = [line for line in lines if line] or ([""] if marks else [])
        if marks:
            lines[0] = " ".join([*marks, lines[0]]).rstrip()
        return [line for line in lines if line]

    def _leaf(self, identifier: str) -> _Leaf:
        node = self.nodes[identifier]
        marker = self.markers.get(identifier, "")
        loops = [
            (position, edge.role, " ".join(self._label(position)))
            for position, edge in enumerate(self.document.edges)
            if edge.source == identifier and edge.target == identifier
        ]
        if marker in ("initial", "final"):
            leaf = _Leaf(identifier, [DOTS[self.charset][marker]], "dot", "light")
        elif marker in STATE_BARS:
            degree = max(
                sum(1 for edge in self.document.edges if edge.source == identifier),
                sum(1 for edge in self.document.edges if edge.target == identifier),
                1,
            )
            length = max(5, 4 * degree + 1)
            across, upright = BARS[self.charset]
            rows = [across * length] if self.down else [upright] * max(3, 2 * degree + 1)
            leaf = _Leaf(identifier, rows, "bar", "heavy")
        else:
            index = self.written.get(identifier, 0)
            pointer = f"/nodes/{index}/text"
            lines = [
                part
                for line in label_lines(node.label, self.charset, pointer)
                for part in _rewrapped(line, self.wrap)
            ]
            classes = {klass.id: klass.text for klass in self.document.classes}
            if node.klass in classes:
                klass = " ".join(label_lines(classes[node.klass], self.charset, "/classes"))
                lines += _rewrapped(f"({klass})", self.wrap)
            if node.status:
                lines.append(f"{STATUS_MARKS[node.status]} {node.status}")
            if loops and self.down and len(lines) < 2:
                # Two rows inside, for a loop to leave by one and come back by the other.
                lines.append("")
            rows, weight = _box(lines, node.role, self.charset)
            leaf = _Leaf(identifier, rows, "box", weight)
        leaf.loops = loops
        self._hooked(leaf)
        return leaf

    def _hooked(self, leaf: _Leaf) -> None:
        """Make room for a leaf's loops: beside it down the page, under and over it across."""
        height, width = leaf.height, leaf.width
        if not leaf.loops:
            leaf.extent = (height, width)
            return
        if leaf.kind == "box" and not self.down and width < 7:
            grow = 7 - width
            leaf.rows = [row[:-1] + row[-2] * grow + row[-1] for row in leaf.rows]
            width = 7
        before = after = 0
        top = bottom = 0
        for number, (_, _, label) in enumerate(leaf.loops):
            room = 3 + (cells(label) + 1 if label else 0)
            if self.down:
                if number == 0:
                    after = room
                else:
                    before = room
            else:
                reach = 6 + cells(label) if label else 5
                after = max(after, reach - width)
                if number == 0:
                    bottom = 2
                else:
                    top = 2
        if self.down:
            leaf.offset = (0, before)
            leaf.extent = (height, before + width + after)
        else:
            leaf.offset = (top, 0)
            leaf.extent = (top + height + bottom, width + max(after, 0))

    # -- arrangement ------------------------------------------------------

    def _along(self, height: int, width: int) -> int:
        return height if self.down else width

    def _across(self, height: int, width: int) -> int:
        return width if self.down else height

    def _at(self, along: int, across: int) -> tuple[int, int]:
        return (along, across) if self.down else (across, along)

    def _within(self, identifier: str, container: str) -> str | None:
        """The member of `container` that holds `identifier`, or it itself; else `None`."""
        current: str | None = identifier
        while current is not None:
            above = self.parent.get(current, "")
            if above == container:
                return current
            current = above or None
        return None

    def _block(self, identifier: str) -> _Block:
        if identifier in self.leaves:
            height, width = self.leaves[identifier].extent
            return _Block(height, width, leaves={identifier: (0, 0)})
        group = self.groups[identifier]
        regions = [member for member in group.members if member in self.groups]
        if regions and all(self.groups[member].region for member in regions):
            inner = self._regions(regions) if not self.wrap else self._stacked(regions)
        else:
            inner = self._arranged(identifier, list(group.members))
        return self._framed(identifier, inner)

    def _framed(self, identifier: str, inner: _Block) -> _Block:
        """A group's block inside its frame, its name on the top border."""
        caption = " ".join(
            label_lines(self.groups[identifier].text, self.charset, self._group_pointer(identifier))
        ).strip()
        # Room inside the border for a line that crosses it to turn: two rows
        # down the page, where the name on the top border is in the way.
        rows, columns = (2, 2) if self.down else (1, 2)
        width = max(inner.width + 2 + 2 * columns, cells(caption) + 6 if caption else 0)
        height = inner.height + 2 + 2 * rows
        block = _Block(height, width)
        block.take(inner, 1 + rows, 1 + columns + (width - 2 - 2 * columns - inner.width) // 2)
        block.frames[identifier] = Rect(0, 0, height, width)
        return block

    def _group_pointer(self, identifier: str) -> str:
        for index, group in enumerate(self.original.groups):
            if group.id == identifier:
                return f"/groups/{index}/text"
        return "/groups"

    def _regions(self, regions: Sequence[str]) -> _Block:
        """A composite state's regions side by side across, a dashed rule between each two."""
        blocks = [self._arranged(region, list(self.groups[region].members)) for region in regions]
        along = max(self._along(block.height, block.width) for block in blocks)
        gap = 2
        across = sum(self._across(b.height, b.width) for b in blocks) + (2 * gap + 1) * (
            len(blocks) - 1
        )
        height, width = (along, across) if self.down else (across, along)
        out = _Block(height, width)
        at = 0
        for number, block in enumerate(blocks):
            out.take(block, *self._at(0, at))
            at += self._across(block.height, block.width)
            if number < len(blocks) - 1:
                at += gap
                for step in range(-2, along + 2):
                    out.rules[self._at(step, at)] = "v" if self.down else "h"
                at += 1 + gap
        return out

    def _stacked(self, regions: Sequence[str]) -> _Block:
        """A composite state's regions one after another along the reading, a rule between.

        The narrower form, tried with the narrower words: UML draws regions
        either way, and a terminal is narrower than it is long.
        """
        blocks = [self._arranged(region, list(self.groups[region].members)) for region in regions]
        across = max(self._across(block.height, block.width) for block in blocks)
        gap = 1
        along = sum(self._along(b.height, b.width) for b in blocks) + (2 * gap + 1) * (
            len(blocks) - 1
        )
        height, width = (along, across) if self.down else (across, along)
        out = _Block(height, width)
        at = 0
        for number, block in enumerate(blocks):
            room = across - self._across(block.height, block.width)
            out.take(block, *self._at(at, room // 2))
            at += self._along(block.height, block.width)
            if number < len(blocks) - 1:
                at += gap
                for step in range(-2, across + 2):
                    out.rules[self._at(at, step)] = "h" if self.down else "v"
                at += 1 + gap
        return out

    def _pairs(self, container: str, members: Sequence[str]) -> list[tuple[str, str, int]]:
        """The edges between members of `container`, as members: source, target, edge position."""
        inside = set(members)
        out = []
        for position, edge in enumerate(self.document.edges):
            if edge.source == edge.target:
                continue
            source = self._within(edge.source, container)
            target = self._within(edge.target, container)
            if source in inside and target in inside and source != target:
                assert source is not None and target is not None
                out.append((source, target, position))
        return out

    def _room(self, position: int) -> int:
        """How much a gap between ranks grows for this edge's label: rows down, columns across."""
        lines = self.labels[position]
        if not lines:
            return 0
        return len(lines) if self.down else max(cells(line) for line in lines) + 2

    def _arranged(self, container: str, members: list[str]) -> _Block:
        """`members` laid out by the layered engine's ranks and order, in cells."""
        blocks = {member: self._block(member) for member in members}
        pairs = self._pairs(container, members)
        edges, _ = acyclic(members, [LayoutEdge(source, target) for source, target, _ in pairs])
        ranks = rank_nodes([LayoutNode(member, 1.0, 1.0) for member in members], edges)
        return self._layered(members, blocks, pairs, ranks)

    def _gaps(
        self, pairs: Sequence[tuple[str, str, int]], ranks: Mapping[str, int], depth: int
    ) -> list[int]:
        """The gap after each rank: the base, and room for the labels of the edges across it."""
        gaps = [self.rank_gap] * max(depth - 1, 0)
        room = [0] * max(depth - 1, 0)
        for source, target, position in pairs:
            low, high = sorted((ranks[source], ranks[target]))
            for gap in range(low, high):
                room[gap] = max(room[gap], self._room(position))
        return [gap + extra for gap, extra in zip(gaps, room, strict=True)]

    def _order(
        self,
        members: Sequence[str],
        blocks: Mapping[str, _Block],
        pairs: Sequence[tuple[str, str, int]],
        ranks: Mapping[str, int],
    ) -> tuple[list[LayoutNode], list[LayoutEdge], dict[str, int], tuple[tuple[str, ...], ...]]:
        """The engine's order, with a one-cell placeholder wherever an edge passes a rank."""
        nodes = [
            LayoutNode(
                member,
                float(self._across(blocks[member].height, blocks[member].width)),
                float(self._along(blocks[member].height, blocks[member].width)),
            )
            for member in members
        ]
        every = dict(ranks)
        chain: list[LayoutEdge] = []
        seen: set[tuple[str, str]] = set()
        for source, target, _ in pairs:
            low, high = (source, target) if ranks[source] < ranks[target] else (target, source)
            if (low, high) in seen:
                continue
            seen.add((low, high))
            previous = low
            for rank in range(ranks[low] + 1, ranks[high]):
                placeholder = f"\x00{len(every)}"
                every[placeholder] = rank
                nodes.append(LayoutNode(placeholder, 1.0, 1.0))
                chain.append(LayoutEdge(previous, placeholder))
                previous = placeholder
            chain.append(LayoutEdge(previous, high))
        order = LayeredEngine._order(nodes, chain, every)
        return nodes, chain, every, order

    def _layered(
        self,
        members: Sequence[str],
        blocks: Mapping[str, _Block],
        pairs: Sequence[tuple[str, str, int]],
        ranks: Mapping[str, int],
    ) -> _Block:
        nodes, chain, every, order = self._order(members, blocks, pairs, ranks)
        engine = LayeredEngine(spacing=Spacing(node_gap=float(self.node_gap), rank_gap=1.0))
        placements, _, _ = engine._place(nodes, order, chain)
        sizes = {node.id: (int(node.height), int(node.width)) for node in nodes}
        across = {identifier: int(place.x + 0.5) for identifier, place in placements.items()}
        for layer in order:
            reach = None
            for identifier in layer:
                if reach is not None:
                    across[identifier] = max(across[identifier], reach)
                reach = across[identifier] + sizes[identifier][1] + self.node_gap
        least = min(across.values(), default=0)
        depth = len(order)
        bands = [max((sizes[i][0] for i in layer), default=1) for layer in order]
        gaps = self._gaps(pairs, every, depth)
        starts = [0]
        for band, gap in zip(bands, gaps, strict=False):
            starts.append(starts[-1] + band + gap)
        along = starts[-1] + bands[-1] if bands else 0
        wide = max((across[i] - least + sizes[i][1] for i in across), default=0)
        if self.down:
            # A label goes beside its line, which drops from somewhere under its
            # source: the block is kept wide enough for it there — and, for an
            # edge that returns up the page round the boxes, on the left too.
            before = 0
            for source, target, position in pairs:
                if self.labels[position]:
                    room = max(cells(line) for line in self.labels[position]) + 3
                    for end in (source, target):
                        middle = across[end] - least + sizes[end][1] // 2
                        wide = max(wide, middle + room)
                        if every[source] > every[target]:
                            before = max(before, room - middle)
            least -= before
            wide += before
        height, width = (along, wide) if self.down else (wide, along)
        out = _Block(height, width)
        for member in members:
            out.take(blocks[member], *self._at(starts[every[member]], across[member] - least))
        return out

    def _lanes(self) -> _Block:
        """A `lanes` document: each lane a band across the ranks, named at its head.

        Down the page the lanes are columns with their names over them and the
        phases named at the left; across it they are rows, named at the left,
        with the phases named over them. Dashed rules divide lanes and phases,
        and a hand-off crosses them.
        """
        document = self.document
        members = [node.id for node in document.nodes]
        blocks = {member: self._block(member) for member in members}
        _, _, ranks = ranked(document)
        pairs = self._pairs("", members)
        _, _, every, order = self._order(members, blocks, pairs, ranks)
        lane_of = {node.id: document.lanes.index(node.lane) for node in document.nodes}
        names = [
            " ".join(label_lines(lane, self.charset, f"/lanes/{index}"))
            for index, lane in enumerate(document.lanes)
        ]
        phase_of = {m: i for i, phase in enumerate(document.phases) for m in phase.members}
        phases = [
            " ".join(label_lines(phase.text, self.charset, f"/phases/{index}/text"))
            for index, phase in enumerate(document.phases)
        ]
        pad = 3 if self.down else 2
        depth = len(order)
        cell: dict[tuple[int, int], list[str]] = {}
        for rank, layer in enumerate(order):
            for identifier in layer:
                if identifier in lane_of:
                    cell.setdefault((lane_of[identifier], rank), []).append(identifier)

        def spread(identifiers: Sequence[str]) -> int:
            return sum(self._across(blocks[i].height, blocks[i].width) for i in identifiers) + (
                self.node_gap * max(len(identifiers) - 1, 0)
            )

        widths = []
        for lane, name in enumerate(names):
            need = max((spread(cell.get((lane, rank), [])) for rank in range(depth)), default=0)
            need += 2 * pad
            if self.down:
                need = max(need, cells(name) + 2)
            widths.append(need)
        bands = [
            max(
                (self._along(blocks[i].height, blocks[i].width) for i in layer if i in lane_of),
                default=1,
            )
            for layer in order
        ]
        gaps = self._gaps(pairs, every, depth)
        boundaries: list[int] = []
        for rank in range(depth - 1):
            here = {phase_of[i] for i in order[rank] if i in phase_of}
            there = {phase_of[i] for i in order[rank + 1] if i in phase_of}
            if here and there and max(here) < min(there):
                gaps[rank] = max(gaps[rank], 2) + 2
                boundaries.append(rank)
        # Across the reading: the phases' names (a column down the page, a row
        # across it), then the lanes. Along it: the lanes' names (a row of
        # headings down the page, a column across it), a rule, then the ranks.
        if self.down:
            lead = (max(cells(phase) for phase in phases) + 2) if phases else 0
            head = 3
        else:
            lead = 1 if phases else 0
            head = max(cells(name) for name in names) + 3
        starts = [head]
        for band, gap in zip(bands, gaps, strict=False):
            starts.append(starts[-1] + band + gap)
        along_end = starts[-1] + bands[-1] if bands else head
        lane_starts = []
        at = lead + (1 if lead else 0)
        for wide in widths:
            lane_starts.append(at)
            at += wide + 1
        across_end = at - 1
        height, width = (along_end, across_end) if self.down else (across_end, along_end)
        out = _Block(height, width)
        for (lane, rank), identifiers in cell.items():
            spot = lane_starts[lane] + (widths[lane] - spread(identifiers)) // 2
            for identifier in identifiers:
                block = blocks[identifier]
                out.take(block, *self._at(starts[rank], spot))
                spot += self._across(block.height, block.width) + self.node_gap
        runs_along, runs_across = ("v", "h") if self.down else ("h", "v")
        # The dividers between lanes, and between the phases' names and the lanes.
        dividers = [start - 1 for start in lane_starts[1:]]
        if lead:
            dividers.insert(0, lane_starts[0] - 1)
        for spot in dividers:
            for step in range(0, along_end):
                out.rules[self._at(step, spot)] = runs_along
        for rank in boundaries:
            middle = starts[rank] + bands[rank] + gaps[rank] // 2
            for step in range(0, across_end + 1):
                out.rules.setdefault(self._at(middle, step), runs_across)
        for step in range(0, across_end + 1):
            out.rules.setdefault(self._at(head - 2, step), runs_across)
        for lane, name in enumerate(names):
            spot = lane_starts[lane] + ((widths[lane] - cells(name)) // 2 if self.down else pad)
            out.texts.append((*self._at(0, spot), name))
        for index, name in enumerate(phases):
            first = min((every[m] for m in document.phases[index].members if m in every), default=0)
            out.texts.append((*self._at(starts[first], 0), name))
        return out

    # -- drawing ----------------------------------------------------------

    def drawn(self) -> TextDrawing:
        if self.document.kind == "lanes":
            block = self._lanes()
        else:
            top = [
                identifier
                for identifier in (
                    *(node.id for node in self.document.nodes),
                    *(group.id for group in self.document.groups),
                )
                if identifier not in self.parent
            ]
            block = self._arranged("", top)
        return _Canvas(self, block).drawn()


# ---------------------------------------------------------------------------
# Routing and labelling
# ---------------------------------------------------------------------------


class _Canvas:
    """The placed drawing on an occupancy grid: routes, then labels, then glyphs."""

    def __init__(self, plan: _Plan, block: _Block) -> None:
        self.plan = plan
        self.charset = plan.charset
        self.height = block.height + 2 * MARGIN
        self.width = block.width + 2 * MARGIN
        self.ends: dict[str, Rect] = {}
        self.text: dict[tuple[int, int], str] = {}
        self.owner: dict[tuple[int, int], tuple[str, str]] = {}
        self.blocked: set[tuple[int, int]] = set()
        self.rules: dict[tuple[int, int], str] = {}
        self.lines: dict[tuple[int, int], str] = {}
        self.arms: dict[tuple[int, int], dict[str, str]] = {}
        self.near: set[tuple[int, int]] = set()
        self.crowd: set[tuple[int, int]] = set()
        self.crossed = 0
        self.routes: list[TextRoute] = []
        for identifier, (top, left) in block.leaves.items():
            leaf = plan.leaves[identifier]
            row, column = top + MARGIN + leaf.offset[0], left + MARGIN + leaf.offset[1]
            self.ends[identifier] = Rect(row, column, leaf.height, leaf.width)
            self._write(row, column, leaf.rows, self._pointer(identifier))
        for identifier, rect in block.frames.items():
            frame = rect.moved(MARGIN, MARGIN)
            self.ends[identifier] = frame
            self._frame(identifier, frame)
        for (row, column), way in block.rules.items():
            cell = (row + MARGIN, column + MARGIN)
            if cell not in self.text and cell not in self.rules:
                self.rules[cell] = way
        for row, column, words in block.texts:
            self._write(row + MARGIN, column + MARGIN, [words], ("/lanes", repr(words)))
        for identifier, rect in self.ends.items():
            if identifier in plan.leaves:
                for row in range(rect.top - 1, rect.bottom + 2):
                    for column in range(rect.left - 1, rect.right + 2):
                        if rect.beside(row, column):
                            self.near.add((row, column))

    def _pointer(self, identifier: str) -> tuple[str, str]:
        if identifier in self.plan.written:
            node = self.plan.original.nodes[self.plan.written[identifier]]
            return (
                f"/nodes/{self.plan.written[identifier]}/text",
                f"the box {plain(node.label).split(chr(10))[0]!r}",
            )
        return ("/", "the drawing")

    def _write(self, row: int, column: int, rows: Sequence[str], owner: tuple[str, str]) -> None:
        for number, line in enumerate(rows):
            at = column
            for character in line:
                cell = (row + number, at)
                self.text[cell] = character
                self.blocked.add(cell)
                self.owner[cell] = owner
                if cells(character) == 2:
                    self.text[(row + number, at + 1)] = ""
                    self.blocked.add((row + number, at + 1))
                    at += 2
                else:
                    at += 1

    def _frame(self, identifier: str, frame: Rect) -> None:
        """A group's dashed frame: its border a rule an edge crosses, its name words it may not."""
        glyphs = BOXES[self.charset]["dashed"]
        for column in range(frame.left + 1, frame.right):
            self.rules[(frame.top, column)] = "h"
            self.rules[(frame.bottom, column)] = "h"
        for row in range(frame.top + 1, frame.bottom):
            self.rules[(row, frame.left)] = "v"
            self.rules[(row, frame.right)] = "v"
        corners = (
            ((frame.top, frame.left), glyphs.top_left),
            ((frame.top, frame.right), glyphs.top_right),
            ((frame.bottom, frame.left), glyphs.bottom_left),
            ((frame.bottom, frame.right), glyphs.bottom_right),
        )
        for cell, glyph in corners:
            self.text[cell] = glyph
            self.blocked.add(cell)
        group = self.plan.groups[identifier]
        pointer = self.plan._group_pointer(identifier)
        caption = " ".join(label_lines(group.text, self.charset, pointer)).strip()
        if caption:
            words = f" {caption} "
            self._write(frame.top, frame.left + 2, [words], (pointer, f"the group {caption!r}"))
            for column in range(frame.left + 2, frame.left + 2 + cells(words)):
                self.rules.pop((frame.top, column), None)

    # -- routes -----------------------------------------------------------

    def _ports(self, identifier: str, side: int) -> list[tuple[int, int, float]]:
        """The free cells beside one side of an end, each with a small price off-centre."""
        rect = self.ends[identifier]
        leaf = self.plan.leaves.get(identifier)
        out = []
        if side in (_N, _S):
            row = rect.top if side == _N else rect.bottom
            spots = [(row, column) for column in range(rect.left, rect.right + 1)]
            middle = (rect.left + rect.right) / 2
        else:
            column = rect.left if side == _W else rect.right
            spots = [(row, column) for row in range(rect.top, rect.bottom + 1)]
            middle = (rect.top + rect.bottom) / 2
        for row, column in spots:
            corner = (row, column) in (
                (rect.top, rect.left),
                (rect.top, rect.right),
                (rect.bottom, rect.left),
                (rect.bottom, rect.right),
            )
            if (leaf is None or leaf.kind == "box") and corner:
                continue
            if (leaf is None or leaf.kind == "box") and not self._straight_side(
                identifier, row, column, side
            ):
                continue
            cell = (row + _DR[side], column + _DC[side])
            if self._free(cell):
                offset = abs((column if side in (_N, _S) else row) - middle)
                out.append((cell[0], cell[1], 0.1 * offset + CROWD * (cell in self.crowd)))
        return out

    def _straight_side(self, identifier: str, row: int, column: int, side: int) -> bool:
        """Whether a border cell is a plain stretch of side: no corner, no lid, no head."""
        if identifier not in self.plan.leaves:
            return (row, column) in self.rules
        glyph = self.text.get((row, column), "")
        return glyph in (SIDES_ACROSS if side in (_N, _S) else SIDES_DOWN)

    def _free(self, cell: tuple[int, int]) -> bool:
        row, column = cell
        return (
            0 <= row < self.height
            and 0 <= column < self.width
            and cell not in self.blocked
            and cell not in self.lines
            and cell not in self.rules
        )

    def _sides(self, source: str, target: str) -> tuple[tuple[int, ...], tuple[int, ...]]:
        """The sides an edge leaves and arrives by: square to the reading, or round it."""
        first, second = self.ends[source], self.ends[target]
        if self.plan.down:
            if second.top > first.bottom:
                return (_S,), (_N,)
            if second.bottom < first.top:
                return (_E, _W), (_E, _W)
            if second.left > first.right:
                return (_E,), (_W,)
            if second.right < first.left:
                return (_W,), (_E,)
        else:
            if second.left > first.right:
                return (_E,), (_W,)
            if second.right < first.left:
                return (_S, _N), (_S, _N)
            if second.top > first.bottom:
                return (_S,), (_N,)
            if second.bottom < first.top:
                return (_N,), (_S,)
        return (_N, _E, _S, _W), (_N, _E, _S, _W)

    def route(
        self, position: int, sides: tuple[Sequence[int], Sequence[int]] | None = None
    ) -> None:
        """Route one edge: by `sides` when given, else square sides first, then any side.

        Raises:
            _Unroutable: no path at these gaps.
        """
        edge = self.plan.document.edges[position]
        if sides is not None:
            found = self._search(edge, *sides)
        else:
            found = self._search(edge, *self._sides(edge.source, edge.target))
            if found is None:
                found = self._search(edge, _ANY, _ANY)
        if found is None:
            raise _Unroutable(position)
        path, leaving, arriving = found
        self._lay(position, edge, path, leaving, arriving)

    def _choices(self, position: int) -> list[tuple[Sequence[int], Sequence[int]]]:
        """The sides to try a returning edge by, until its label has room beside it."""
        edge = self.plan.document.edges[position]
        leaving, arriving = self._sides(edge.source, edge.target)
        pairs = [((first,), (second,)) for first in leaving for second in arriving]
        return [(leaving, arriving), *pairs, (_ANY, _ANY)]

    def _state(self) -> tuple[object, ...]:
        return (
            set(self.blocked),
            dict(self.lines),
            {cell: dict(arms) for cell, arms in self.arms.items()},
            set(self.crowd),
            dict(self.text),
            dict(self.owner),
            self.crossed,
            list(self.routes),
        )

    def _restore(self, state: tuple[object, ...]) -> None:
        (
            self.blocked,
            self.lines,
            self.arms,
            self.crowd,
            self.text,
            self.owner,
            self.crossed,
            self.routes,
        ) = state  # type: ignore[assignment]

    def returning(self, position: int) -> None:
        """Route and label an edge that reads against the flow, side by side until both fit.

        Raises:
            _Unroutable: no sides give the edge a path and its label room.
        """
        lines = self.plan.labels[position]
        for sides in self._choices(position):
            state = self._state()
            try:
                self.route(position, sides)
                if lines:
                    self.label(self.routes[-1], lines)
            except _Unroutable:
                self._restore(state)
                continue
            return
        raise _Unroutable(position)

    def _search(
        self, edge: Edge, leaving: Sequence[int], arriving: Sequence[int]
    ) -> tuple[list[tuple[int, int]], int, int] | None:
        goals: dict[tuple[int, int], int] = {}
        for side in arriving:
            for row, column, _ in self._ports(edge.target, side):
                goals.setdefault((row, column), (side + 2) % 4)
        if not goals:
            return None
        heap: list[tuple[float, int, int, int, int]] = []
        start_side = leaving[0]
        best: dict[tuple[int, int, int], float] = {}
        before: dict[tuple[int, int, int], tuple[int, int, int] | None] = {}
        count = 0
        for side in leaving:
            for row, column, price in self._ports(edge.source, side):
                state = (row, column, side)
                if price < best.get(state, float("inf")):
                    best[state] = price
                    before[state] = None
                    heapq.heappush(heap, (price, count, row, column, side))
                    count += 1
        while heap:
            cost, _, row, column, heading = heapq.heappop(heap)
            state = (row, column, heading)
            if cost > best.get(state, float("inf")):
                continue
            if goals.get((row, column)) == heading:
                path = []
                walk: tuple[int, int, int] | None = state
                while walk is not None:
                    path.append((walk[0], walk[1]))
                    previous = before[walk]
                    if previous is None:
                        start_side = walk[2]
                    walk = previous
                path.reverse()
                return path, start_side, (heading + 2) % 4
            here = (row, column)
            through = here in self.lines or here in self.rules
            for turn in range(4):
                if turn == (heading + 2) % 4 or (through and turn != heading):
                    continue
                cell = (row + _DR[turn], column + _DC[turn])
                if not (0 <= cell[0] < self.height and 0 <= cell[1] < self.width):
                    continue
                if cell in self.blocked:
                    continue
                step = STEP + (BEND if turn != heading else 0.0)
                upright = turn in (_N, _S)
                if cell in self.rules:
                    if (self.rules[cell] == "v") == upright or cell in goals:
                        continue
                    step += RULE
                if cell in self.lines:
                    kind = self.lines[cell]
                    if kind not in ("h", "v") or (kind == "v") == upright or cell in goals:
                        continue
                    step += CROSS
                if cell in self.near and cell not in goals:
                    step += NEAR
                if cell in self.crowd:
                    step += CROWD
                after = (cell[0], cell[1], turn)
                total = cost + step
                if total < best.get(after, float("inf")):
                    best[after] = total
                    before[after] = state
                    heapq.heappush(heap, (total, count, cell[0], cell[1], turn))
                    count += 1
        return None

    def _lay(
        self,
        position: int,
        edge: Edge,
        path: Sequence[tuple[int, int]],
        leaving: int,
        arriving: int,
    ) -> None:
        """Record a found path: its cells, its arms, its crossings, its head and tee."""
        style = line_style(self._role(edge))
        back = (leaving + 2) % 4  # from the first cell, towards the source
        sides: list[set[int]] = []
        for index, cell in enumerate(path):
            arms: set[int] = set()
            if index == 0:
                arms.add(back)
            else:
                previous = path[index - 1]
                arms.add(_toward(cell, previous))
            if index < len(path) - 1:
                arms.add(_toward(cell, path[index + 1]))
            else:
                arms.add((arriving + 2) % 4)
            sides.append(arms)
        for index, (cell, arms) in enumerate(zip(path, sides, strict=True)):
            kind = "x"
            if 0 < index < len(path) - 1:
                if arms == {_N, _S}:
                    kind = "v"
                elif arms == {_E, _W}:
                    kind = "h"
            if cell in self.lines:
                self.crossed += 1
                kind = "x"
            self.lines[cell] = kind
            self.crowd.update((cell[0] + dr, cell[1] + dc) for dr, dc in zip(_DR, _DC, strict=True))
            drawn = self.arms.setdefault(cell, {})
            for arm in arms:
                drawn[_SIDES[arm]] = style
        self._ends(edge, path, leaving, arriving)
        self.routes.append(
            TextRoute(edge.source, edge.target, tuple(path), self.plan.indices[position])
        )

    def _role(self, edge: Edge) -> str:
        return "aside" if edge.status == "removed" else edge.role

    def _ends(
        self, edge: Edge, path: Sequence[tuple[int, int]], leaving: int, arriving: int
    ) -> None:
        """The head at the target, the tee (or a tail) at the source."""
        role = self._role(edge)
        kind = HEAD_KIND.get(role, "filled")
        last = path[-1]
        moving = (arriving + 2) % 4
        if kind:
            self.text[last] = self._head(kind, moving)
        else:
            # A line with no head joins its target as it leaves its source.
            self._tee(edge.target, last, arriving)
        first = path[0]
        if role == "exchange":
            self.text[first] = self._head("filled", (leaving + 2) % 4)
        else:
            self._tee(edge.source, first, leaving)

    def _head(self, kind: str, moving: int) -> str:
        if kind == "diamond":
            return DIAMONDS[self.charset]
        filled, hollow = HEADS[self.charset][moving]
        return hollow if kind == "open" else filled

    def _tee(self, identifier: str, first: tuple[int, int], leaving: int) -> None:
        """The source's border where a line leaves it, as a tee — on a box's plain stretch only."""
        border = (first[0] - _DR[leaving], first[1] - _DC[leaving])
        leaf = self.plan.leaves.get(identifier)
        if leaf is not None and leaf.kind != "box":
            square = leaving in ((_N, _S) if self.plan.down else (_E, _W))
            if leaf.kind == "bar" and square and self.charset == "unicode":
                self.text[border] = TEES["heavy"][leaving]
            return
        glyph = self.text.get(border, "")
        if leaf is None:
            self.text[border] = "+" if self.charset == "ascii" else TEES["light"][leaving]
            return
        if glyph in "<>/()":
            return
        if self.charset == "ascii":
            self.text[border] = "#" if leaf.style == "heavy" else "+"
        else:
            self.text[border] = TEES[leaf.style][leaving]

    def loops(self) -> None:
        """Each self-loop as a hook beside its box: out by one tee, back by the head."""
        for identifier, leaf in self.plan.leaves.items():
            if not leaf.loops:
                continue
            rect = self.ends[identifier]
            for number, (position, role, label) in enumerate(leaf.loops):
                edge = self.plan.document.edges[position]
                style = line_style("aside" if edge.status == "removed" else role)
                kind = HEAD_KIND.get("aside" if edge.status == "removed" else role, "filled")
                if self.plan.down:
                    outward = _E if number == 0 else _W
                    step = 1 if number == 0 else -1
                    column = rect.right if number == 0 else rect.left
                    top, lower = rect.top + 1, rect.top + 2
                    path = [
                        (top, column + step),
                        (top, column + 2 * step),
                        (lower, column + 2 * step),
                        (lower, column + step),
                    ]
                    words = (top, column + 4 * step if number == 0 else column - 3 - cells(label))
                else:
                    outward = _S if number == 0 else _N
                    step = 1 if number == 0 else -1
                    row = rect.bottom if number == 0 else rect.top
                    first, second = rect.left + 2, rect.left + 4
                    path = [
                        (row + step, first),
                        (row + 2 * step, first),
                        (row + 2 * step, first + 1),
                        (row + 2 * step, second),
                        (row + step, second),
                    ]
                    words = (row + 2 * step, second + 2)
                inward = (outward + 2) % 4
                for index, cell in enumerate(path):
                    arms = {_toward(cell, path[index - 1])} if index else {inward}
                    arms.add(_toward(cell, path[index + 1]) if index < len(path) - 1 else inward)
                    drawn = self.arms.setdefault(cell, {})
                    for arm in arms:
                        drawn[_SIDES[arm]] = style
                    self.blocked.add(cell)
                    self.lines[cell] = "x"
                if kind:
                    self.text[path[-1]] = self._head(kind, inward)
                self._tee(identifier, path[0], outward)
                if label:
                    index = self.plan.indices[position]
                    self._write(*words, [label], (f"/edges/{index}/label", f"the label {label!r}"))
                self.routes.append(
                    TextRoute(identifier, identifier, tuple(path), self.plan.indices[position])
                )

    # -- labels -----------------------------------------------------------

    def label(self, route: TextRoute, lines: Sequence[str]) -> None:
        """Put an edge's label beside its own line, in the first free place from its source.

        Beside a run along the reading first — right or left of a line down the
        page, over or under one across it — then beside a run the other way.
        Never beside the head's cell, so the words are not read as the next box's.

        Raises:
            _Unroutable: nowhere along the line has room.
        """
        tall = len(lines)
        wide = max(cells(line) for line in lines)
        path = route.cells
        runs: list[tuple[int, int, str]] = []
        source = self.ends[route.source]
        for index in range(len(path) - 1):
            row, column = path[index]
            ahead = path[index + 1]
            behind = (
                path[index - 1]
                if index
                else next(
                    (
                        (row + dr, column + dc)
                        for dr, dc in zip(_DR, _DC, strict=True)
                        if source.holds(row + dr, column + dc)
                    ),
                    ahead,
                )
            )
            upright = ahead[1] == column and behind[1] == column
            across = ahead[0] == row and behind[0] == row
            if upright:
                runs.append((row, column, "v"))
            elif across:
                runs.append((row, column, "h"))
        first = "v" if self.plan.down else "h"
        other = "h" if first == "v" else "v"
        tries = [(way, strict) for strict in (True, False) for way in (first, other)]
        for way, strict in tries:
            for row, column, kind in runs:
                if kind != way:
                    continue
                if kind == "v":
                    spots = [(row, column + 2), (row, column - 1 - wide)]
                else:
                    left = column - wide // 2
                    spots = [(row - tall, left), (row + 1, left)]
                for top, left in spots:
                    if self._room(top, left, tall, wide, set(path) if strict else None):
                        pointer = f"/edges/{route.edge}/label"
                        for number, line in enumerate(lines):
                            owner = (pointer, f"the label {line!r}")
                            self._write(top + number, left, [line], owner)
                            # Two cells either side that no later line may take, so
                            # the words are never read as another line's.
                            self.blocked.update(
                                (top + number, column)
                                for column in (left - 2, left - 1, left + wide, left + wide + 1)
                                if (top + number, column) not in path
                            )
                        return
        raise _Unroutable(route.edge)

    def _room(
        self, top: int, left: int, tall: int, wide: int, own: set[tuple[int, int]] | None
    ) -> bool:
        """Whether a label fits at (`top`, `left`) with room either side of every line.

        A free cell either side, and — when `own` names the label's own line —
        no other line in the cell beyond: a label one space from a line not its
        own reads as that line's, so that is only accepted when nothing else
        fits. A label may reach past the routing margin: the drawing grows to
        hold it.
        """
        for row in range(top, top + tall):
            for column in range(left - 1, left + wide + 1):
                cell = (row, column)
                if cell in self.blocked or cell in self.lines or cell in self.rules:
                    return False
            for column in (left - 2, left + wide + 1):
                if own is not None and (row, column) in self.lines and (row, column) not in own:
                    return False
        return True

    # -- the whole --------------------------------------------------------

    def drawn(self) -> TextDrawing:
        plan = self.plan
        self.loops()
        edges = plan.document.edges
        order = [p for p, edge in enumerate(edges) if edge.source != edge.target]

        def priority(position: int) -> tuple[int, int, int]:
            edge = edges[position]
            first, second = self.ends[edge.source], self.ends[edge.target]
            forward = (second.top > first.bottom) if plan.down else (second.left > first.right)
            distance = abs(first.top - second.top) + abs(first.left - second.left)
            return (0 if forward else 1, distance, position)

        # The edges that read forward are routed first and then labelled, and
        # the returns after them, round those labels as well as the boxes — as
        # the SVG routes a state machine.
        ranked = sorted(order, key=priority)
        done = []
        for position in ranked:
            if not priority(position)[0]:
                self.route(position)
                done.append((position, self.routes[-1]))
        for position, route in done:
            lines = plan.labels[position]
            if lines:
                self.label(route, lines)
        for position in ranked:
            if priority(position)[0]:
                self.returning(position)
        return self._rendered()

    def _rendered(self) -> TextDrawing:
        grid = Grid(self.charset)
        horizontal, vertical = RULES[self.charset]
        used = [*self.rules, *self.arms, *(cell for cell, glyph in self.text.items() if glyph)]
        down = -min((row for row, _ in used), default=0)
        across = -min((column for _, column in used), default=0)
        for (row, column), way in self.rules.items():
            if (row, column) not in self.lines:
                grid.text(row + down, column + across, horizontal if way == "h" else vertical)
        for (row, column), arms in self.arms.items():
            for side, style in arms.items():
                grid.arm(row + down, column + across, side, style)
        for (row, column), glyph in self.text.items():
            if glyph:
                grid.text(row + down, column + across, glyph)
        raw = grid.lines()
        top = next((index for index, line in enumerate(raw) if line.strip()), 0)
        bottom = max((index for index, line in enumerate(raw) if line.strip()), default=0)
        kept = raw[top : bottom + 1]
        indent = min(
            (len(line) - len(line.lstrip(" ")) for line in kept if line.strip()), default=0
        )
        lines = tuple(line[indent:] for line in kept)
        top, indent = top - down, indent - across
        width = max((cells(line) for line in lines), default=0)
        pointer, what = self._rightmost()
        return TextDrawing(
            lines=lines,
            boxes={identifier: rect.moved(-top, -indent) for identifier, rect in self.ends.items()},
            routes=tuple(
                TextRoute(
                    route.source,
                    route.target,
                    tuple((row - top, column - indent) for row, column in route.cells),
                    route.edge,
                )
                for route in self.routes
            ),
            crossings=self.crossed,
            direction=self.plan.direction,
            width=width,
            pointer=pointer,
            what=what,
        )

    def _rightmost(self) -> tuple[str, str]:
        """What reaches furthest right — a box, a label, a lane's name — for a refusal."""
        if not self.owner:
            return "/nodes", f"this {self.plan.document.kind}"
        pointer, what = self.owner[max(self.owner, key=lambda cell: (cell[1], -cell[0]))]
        if self.plan.down:
            return pointer, f"{what}, furthest right,"
        return pointer, f"{what}, at the end of the drawing laid across the page,"


def _toward(cell: tuple[int, int], other: tuple[int, int]) -> int:
    """The side of `cell` that `other` is on, for two cells side by side."""
    row, column = other[0] - cell[0], other[1] - cell[1]
    if row < 0:
        return _N
    if row > 0:
        return _S
    return _E if column > 0 else _W


__all__ = [
    "GRAPH_TEXT_KINDS",
    "TEXT_CROSSINGS",
    "TEXT_NODES",
    "Rect",
    "TextDrawing",
    "TextRoute",
    "attempts",
    "chosen",
    "graph_text",
    "text_drawing",
    "tree_graph_text",
]

"""A `tree` with `"style": "bracket"`: a tournament bracket or a cladogram.

The boxed tree ranks boxes down from its root. A bracket is placed from the
other end: **every leaf stands on one outer edge**, one row each, so the teams of
a draw or the taxa of a cladogram read as one column. An inner node sits as far
from that edge as its deepest leaf is below it — its *height* — so a round of a
knockout is a column, and a ladder cladogram climbs one step per split. Its row
is halfway between its first and last child's.

**Every node is a line, not a box.** A node's line runs from its own end (the
leaf edge, or its own elbow) to its parent's elbow; the elbow is square, one
vertical run joining the children's lines to the parent's. A node's words sit on
its own line at its own end, an edge's `label` (a score, a trait) at the other
end, by the elbow it feeds. An inner node with no words is a bare junction: a
cladogram's common ancestor.

**Where the root stands** is the document's `root`. `right` reads as a
tournament, from the first round on the left to the champion's line at the end,
each team's name on its line. `left` is a cladogram's way round: the root's
short stub at the left and the leaves' names in a column past the tips at the
right. `middle` is the two-sided draw: the root's first child's half as `right`
on the left, its second mirrored on the right, the final in the middle, and the
root's words over a stub above where the two lines meet.

Nothing is placed by an author's number, and nothing overlaps by construction:
two lines in one column belong to disjoint subtrees, so they are a row apart,
and each row is tall enough for the words over a line.

The text form is the same layout on cells: leaves two rows apart, lines in
box-drawing characters joined square, the words inline on their lines.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final

from drawspec.errors import DrawspecError, FitError
from drawspec.scene import Path, Primitive, Scene, TextLine, TextSpan, moved
from drawspec.schema import Document
from drawspec.text.measure import TextMeasurer
from drawspec.text.wrap import TextBlock, wrap
from drawspec.textgrid import Drawn, caption_lines, cells, finished, label_lines, widest
from drawspec.theme import Theme

#: Lengths in units, a unit being the body size over eleven, so the spacing
#: shrinks with the type when the fit pass shrinks it.
PAD: Final = 3.0
"""Between a line's words and the end or the elbow they stand by."""
WORD_GAP: Final = 8.0
"""Along a line: the least run between its words and its edge's label."""
TEXT_GAP: Final = 2.5
"""From the bottom of a line's words to the line."""
ROW_GAP: Final = 6.0
"""Down: between a line and the bottom of the words over the next."""
MIN_RUN: Final = 14.0
"""The shortest a column of lines is, so an unnamed split still reads as a step."""
STUB: Final = 12.0
"""The root's own line when it has no words: a cladogram's root."""
NAME_GAP: Final = 4.0
"""Past a cladogram's tips: from the tip to its name."""

#: The roles lines and words are drawn in: an ordinary line is the headless
#: `link`, the path the reader follows the heavy `strong`.
LINE_ROLE: Final = "link"
STRONG_ROLE: Final = "strong"
WORDS_ROLE: Final = "step"

#: A rectangle: left, top, right, bottom.
type Rect = tuple[float, float, float, float]


@dataclass
class _Node:
    """One node of the bracket, from the tree first, positions filled in."""

    id: str
    index: int
    text: str
    label: str = ""
    """The label of the edge into this node: written by its parent's elbow."""
    strong: bool = False
    """Whether the edge into this node is `strong`."""
    edge: int = -1
    """The position of the edge into this node, for a refusal's pointer."""
    parent: str = ""
    children: list[str] = field(default_factory=list)
    height: int = 0
    side: int = 1
    """+1 when the root is to the right of this node's line, -1 when to its left."""
    row: float = 0.0


@dataclass(frozen=True)
class _Tree:
    root: str
    nodes: Mapping[str, _Node]
    height: int


def _tree(document: Document) -> _Tree:
    """The tree the edges make, siblings in their edges' order, sides and rows set.

    Validation has checked it is one: a single root, a parent each, no cycle.
    """
    order = {node.id: index for index, node in enumerate(document.nodes)}
    nodes = {node.id: _Node(node.id, order[node.id], node.text) for node in document.nodes}
    for position, edge in enumerate(document.edges):
        child = nodes[edge.target]
        child.parent, child.label, child.strong = edge.source, edge.label, edge.role == "strong"
        child.edge = position
        nodes[edge.source].children.append(edge.target)
    roots = [node.id for node in nodes.values() if not node.parent]
    if len(roots) != 1:
        raise DrawspecError("a bracket needs one root")  # validation says where

    def height(identifier: str) -> int:
        node = nodes[identifier]
        node.height = 1 + max((height(child) for child in node.children), default=-1)
        return node.height

    root = roots[0]
    height(root)
    halves = (
        [(child, 1 if position == 0 else -1) for position, child in enumerate(nodes[root].children)]
        if document.bracket_root == "middle"
        else [(root, 1 if document.bracket_root == "right" else -1)]
    )

    def place(identifier: str, side: int, start: list[int]) -> float:
        node = nodes[identifier]
        node.side = side
        if not node.children:
            node.row = float(start[0])
            start[0] += 1
        else:
            rows = [place(child, side, start) for child in node.children]
            node.row = (rows[0] + rows[-1]) / 2
        return node.row

    counts: list[int] = []
    for top, side in halves:
        counts.append(_leaves(nodes, top))
        place(top, side, [0])
    if document.bracket_root == "middle":
        # The smaller half is centred against the taller, so the final is level.
        tallest = max(counts)
        for (top, _), count in zip(halves, counts, strict=True):
            _shift(nodes, top, (tallest - count) / 2)
        root_node = nodes[root]
        root_node.side = 0
        root_node.row = min(nodes[child].row for child in root_node.children)
    return _Tree(root, nodes, nodes[root].height)


def _leaves(nodes: Mapping[str, _Node], identifier: str) -> int:
    children = nodes[identifier].children
    return 1 if not children else sum(_leaves(nodes, child) for child in children)


def _shift(nodes: Mapping[str, _Node], identifier: str, by: float) -> None:
    nodes[identifier].row += by
    for child in nodes[identifier].children:
        _shift(nodes, child, by)


def _names_past_tips(document: Document) -> bool:
    """Whether the leaves' names stand past their tips (a cladogram) or on their lines."""
    return document.bracket_root == "left"


# ---------------------------------------------------------------------------
# SVG
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BracketDrawing:
    """The finished geometry, in final coordinates, for tests and the scene."""

    scene: Scene
    lines: Mapping[str, tuple[tuple[float, float], ...]]
    """Each node's drawn line, by id: from its own end, to its parent's elbow, to the
    parent's row. The root's is its stub."""
    words: Mapping[str, Rect]
    """The rectangle each node's words take, by id — for the nodes that have words."""
    labels: Mapping[str, Rect]
    """The rectangle each edge label takes, by the id of the node it is on."""
    columns: tuple[float, ...]
    """Each height's distance from the leaf edge, leaves first, the root last."""


def bracket_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Draw a bracket `tree`."""
    return bracket_drawing(document, theme, measurer).scene


def bracket_drawing(document: Document, theme: Theme, measurer: TextMeasurer) -> BracketDrawing:
    """Lay the bracket out.

    Raises:
        FitError: it is wider than the canvas at this type scale. `render` tries
            a smaller one, and past the smallest the author is told what to cut.
    """
    tree = _tree(document)
    nodes = tree.nodes
    unit = theme.scale["body"] / 11
    past = _names_past_tips(document)
    middle = document.bracket_root == "middle"

    def block(text: str, level: str) -> TextBlock | None:
        return wrap(text, 1e6, measurer, theme=theme, level=level) if text.strip() else None

    words = {identifier: block(node.text, "body") for identifier, node in nodes.items()}
    labels = {identifier: block(node.label, "label") for identifier, node in nodes.items()}
    text_height = max(
        (b.height for b in (*words.values(), *labels.values()) if b is not None), default=unit * 11
    )

    def on_line(identifier: str) -> float:
        """How much of its own line's length a node's words and label need."""
        node = nodes[identifier]
        own = words[identifier] if not (past and not node.children) else None
        mark = labels[identifier]
        need = PAD * unit * 2
        if own is not None:
            need += own.width
        if mark is not None:
            need += mark.width
        if own is not None and mark is not None:
            need += WORD_GAP * unit
        return max(need, MIN_RUN * unit)

    width_of = [MIN_RUN * unit] * (tree.height + 1)
    for identifier, node in nodes.items():
        if identifier != tree.root:
            width_of[node.height] = max(width_of[node.height], on_line(identifier))
    root_words = words[tree.root]
    if middle and root_words is not None:
        # The final's words are centred over the middle: the last column on each side
        # is wide enough that they never reach the elbows before it.
        last = tree.height - 1
        width_of[last] = max(width_of[last], root_words.width / 2 + PAD * unit * 2)
    columns = [0.0]
    for height in range(tree.height):
        columns.append(columns[-1] + width_of[height])
    stub = max(STUB * unit, (root_words.width + PAD * unit * 2) if root_words else 0.0)
    reach = columns[-1] + (0.0 if middle else stub)
    centre = columns[-1]

    def x(side: int, along: float) -> float:
        """Where `along` from the leaf edge lands, on a line whose root is `side`-ward."""
        if middle:
            return along if side > 0 else 2 * centre - along
        return along if side > 0 else reach - along

    pitch = text_height + (TEXT_GAP + ROW_GAP) * unit
    if past:
        pitch = max(pitch, text_height + ROW_GAP * unit)
    rows = {identifier: node.row * pitch for identifier, node in nodes.items()}

    lines: list[Primitive] = []
    heavy: list[Primitive] = []
    texts: list[Primitive] = []
    drawn: dict[str, tuple[tuple[float, float], ...]] = {}
    word_rects: dict[str, Rect] = {}
    label_rects: dict[str, Rect] = {}

    def write(
        text: TextBlock, left: float, top: float, anchor: str, level: str
    ) -> tuple[float, float, float, float]:
        for index, line in enumerate(text.lines):
            spans = tuple(
                TextSpan(text=span.text, font=span.font, weight=span.weight)
                for span in line.spans
                if span.text
            )
            if spans:
                texts.append(
                    TextLine(
                        WORDS_ROLE,
                        x=left,
                        y=top + text.baseline(index),
                        spans=spans,
                        level=level,
                        anchor=anchor,
                    )
                )
        start = left if anchor == "start" else left - text.width
        return (start, top, start + text.width, top + text.height)

    def over(text: TextBlock, y: float) -> float:
        return y - TEXT_GAP * unit - text.height

    for identifier, node in nodes.items():
        y = rows[identifier]
        side = node.side
        if identifier == tree.root:
            strong = any(nodes[child].strong for child in node.children)
            if middle:
                rise = text_height + (TEXT_GAP + ROW_GAP) * unit
                points: tuple[tuple[float, float], ...] = ((centre, y), (centre, y - rise))
                if root_words is not None:
                    top = y - rise - TEXT_GAP * unit - root_words.height
                    word_rects[identifier] = write(
                        root_words, centre - root_words.width / 2, top, "start", "body"
                    )
            else:
                points = ((x(side, columns[-1]), y), (x(side, reach), y))
                if root_words is not None:
                    at = x(side, columns[-1]) + side * PAD * unit
                    word_rects[identifier] = write(
                        root_words, at, over(root_words, y), "start" if side > 0 else "end", "body"
                    )
            (heavy if strong else lines).append(
                Path(STRONG_ROLE if strong else LINE_ROLE, points=points)
            )
            drawn[identifier] = points
            continue
        parent = nodes[node.parent]
        own_at = x(side, columns[node.height])
        elbow = centre if parent.id == tree.root and middle else x(side, columns[parent.height])
        points = ((own_at, y), (elbow, y))
        if rows[parent.id] != y:
            points = (*points, (elbow, rows[parent.id]))
        (heavy if node.strong else lines).append(
            Path(STRONG_ROLE if node.strong else LINE_ROLE, points=points)
        )
        drawn[identifier] = points
        own = words[identifier]
        if own is not None:
            if past and not node.children:
                # A cladogram's taxon: past its tip, centred on its line.
                word_rects[identifier] = write(
                    own, own_at + NAME_GAP * unit, y - own.height / 2, "start", "body"
                )
            else:
                at = own_at + side * PAD * unit
                word_rects[identifier] = write(
                    own, at, over(own, y), "start" if side > 0 else "end", "body"
                )
        mark = labels[identifier]
        if mark is not None:
            at = elbow - side * PAD * unit
            label_rects[identifier] = write(
                mark, at, over(mark, y), "end" if side > 0 else "start", "label"
            )

    rects = [*word_rects.values(), *label_rects.values()]
    xs = [px for points in drawn.values() for px, _ in points]
    ys = [py for points in drawn.values() for _, py in points]
    left = min([*xs, *(rect[0] for rect in rects)])
    right = max([*xs, *(rect[2] for rect in rects)])
    top = min([*ys, *(rect[1] for rect in rects)])
    bottom = max([*ys, *(rect[3] for rect in rects)])
    canvas = document.width if document.width else theme.canvas.width
    if right - left > canvas + 0.5:
        longest = max(
            (node for node in nodes.values() if words[node.id] is not None),
            key=lambda node: words[node.id].width,  # type: ignore[union-attr]
        )
        raise FitError(
            f"/nodes/{longest.index}: this bracket needs {right - left:.0f} across and the "
            f"canvas is {canvas:.0f}. Shorten the longest names, such as {longest.text!r}, "
            "drop the winners' names from the inner lines of a cladogram, or give it more "
            "width." + ("" if document.bracket_root != "middle" else ' Or say `"root": "right"`.')
        )
    dx, dy = -left, -top

    def shifted(rect: Rect) -> Rect:
        return (rect[0] + dx, rect[1] + dy, rect[2] + dx, rect[3] + dy)

    scene = Scene(
        width=right - left,
        height=bottom - top,
        primitives=tuple(moved(primitive, dx, dy) for primitive in (*lines, *heavy, *texts)),
        title=document.title,
        description=document.description,
    )
    return BracketDrawing(
        scene=scene,
        lines={
            identifier: tuple((px + dx, py + dy) for px, py in points)
            for identifier, points in drawn.items()
        },
        words={identifier: shifted(rect) for identifier, rect in word_rects.items()},
        labels={identifier: shifted(rect) for identifier, rect in label_rects.items()},
        columns=tuple(columns),
    )


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------

_N, _E, _S, _W = 1, 2, 4, 8

#: A cell's glyph by the directions its lines leave it in.
_LIGHT: Final = {
    _E | _W: "─",
    _E: "─",
    _W: "─",
    _N | _S: "│",
    _N: "│",
    _S: "│",
    _S | _E: "┌",
    _S | _W: "┐",
    _N | _E: "└",
    _N | _W: "┘",
    _N | _S | _E: "├",
    _N | _S | _W: "┤",
    _E | _W | _S: "┬",
    _E | _W | _N: "┴",
    _N | _E | _S | _W: "┼",
}

#: A strong line's run, by charset: the rest of the glyphs are the light ones.
_HEAVY_RUN: Final = {"unicode": "━", "ascii": "="}


def bracket_text(document: Document, width: int, charset: str) -> str:
    """A bracket `tree` as plain text: the same layout, on cells.

    Raises:
        FitError: wider than `width`, at the longest name's node.
        DrawspecError: a name has no ASCII spelling under `ascii`.
    """
    tree = _tree(document)
    nodes = tree.nodes
    past = _names_past_tips(document)
    middle = document.bracket_root == "middle"
    words = {
        identifier: " ".join(label_lines(node.text, charset, f"/nodes/{node.index}/text")).strip()
        for identifier, node in nodes.items()
    }
    labels = {
        identifier: " ".join(label_lines(node.label, charset, f"/edges/{node.edge}/label")).strip()
        for identifier, node in nodes.items()
    }

    def need(identifier: str) -> int:
        """Cells a line needs: its elbow, a dash, ` words `, a dash, ` label `, a dash.

        A team's line starts with its name, and a taxon's names stand past the tip.
        """
        node = nodes[identifier]
        own = words[identifier] if not (past and not node.children) else ""
        mark = labels[identifier]
        total = 1 if not node.children and not past else 2
        if own:
            total += cells(own) + (1 if not node.children else 2) + 1
        if mark:
            total += cells(mark) + 2 + 1
        return max(total, 3)

    width_of = [3] * (tree.height + 1)
    for identifier, node in nodes.items():
        if identifier != tree.root:
            width_of[node.height] = max(width_of[node.height], need(identifier))
    root_words = words[tree.root]
    if middle and root_words:
        # The final's words are centred over the middle, clear of the elbows before it.
        width_of[tree.height - 1] = max(width_of[tree.height - 1], cells(root_words) // 2 + 3)
    columns = [0]
    for height in range(tree.height):
        columns.append(columns[-1] + width_of[height])
    stub = max(3, cells(root_words) + 5 if root_words else 0)
    centre = columns[-1]
    names = max((cells(words[i]) for i, n in nodes.items() if not n.children), default=0)
    reach = centre + (0 if middle else stub)

    def x(side: int, along: int) -> int:
        if middle:
            return along if side > 0 else 2 * centre - along
        return along if side > 0 else reach - along

    rows = {identifier: int(node.row * 2) for identifier, node in nodes.items()}
    if middle:
        root = nodes[tree.root]
        rows[tree.root] = min(rows[child] for child in root.children)
    top_row = min(rows.values()) - (2 if middle else 0)
    total = (2 * centre + 1) if middle else reach + 1 + ((names + 2) if past else 0)
    height = max(rows.values()) - top_row + 1
    links = [[0] * total for _ in range(height)]
    strong = [[False] * total for _ in range(height)]
    glyphs: list[list[str | None]] = [[None] * total for _ in range(height)]

    def run(row: int, a: int, b: int, heavy: bool) -> None:
        low, high = sorted((a, b))
        for column in range(low, high + 1):
            if column < high:
                links[row - top_row][column] |= _E
            if column > low:
                links[row - top_row][column] |= _W
            if heavy:
                strong[row - top_row][column] = True

    def climb(column: int, a: int, b: int) -> None:
        low, high = sorted((a, b))
        for row in range(low, high + 1):
            if row < high:
                links[row - top_row][column] |= _S
            if row > low:
                links[row - top_row][column] |= _N

    def put(row: int, column: int, text: str) -> None:
        for offset, character in enumerate(text):
            glyphs[row - top_row][column + offset] = character

    def inline(row: int, own_at: int, side: int, text: str) -> None:
        """Words on a line by its own elbow: the elbow, a dash, then ` words `."""
        if side > 0:
            put(row, own_at + 2, f" {text} ")
        else:
            put(row, own_at - 3 - cells(text), f" {text} ")

    for identifier, node in nodes.items():
        row, side = rows[identifier], node.side
        if identifier == tree.root:
            heavy = any(nodes[child].strong for child in node.children)
            if middle:
                climb(centre, row - 1, row)
                if root_words:
                    put(row - 2, max(0, centre - cells(root_words) // 2), root_words)
                continue
            own_at = x(side, centre)
            run(row, own_at, x(side, reach), heavy)
            if root_words:
                inline(row, own_at, side, root_words)
            continue
        parent = nodes[node.parent]
        own_at = x(side, columns[node.height])
        elbow = centre if middle and parent.id == tree.root else x(side, columns[parent.height])
        run(row, own_at, elbow, node.strong)
        climb(elbow, row, rows[parent.id])
        own, mark = words[identifier], labels[identifier]
        if own and not node.children:
            if past:
                put(row, own_at + 1, f" {own}")
            elif side > 0:
                # A team's name on its line, from the outer edge.
                put(row, own_at, f"{own} ")
            else:
                put(row, own_at - cells(own), f" {own}")
        elif own:
            inline(row, own_at, side, own)
        if mark:
            put(row, elbow - 3 - cells(mark) if side > 0 else elbow + 2, f" {mark} ")

    heavy_run = _HEAVY_RUN[charset]
    out: list[Drawn] = []
    for index, joined in enumerate(links):
        line: list[str] = []
        for column, link in enumerate(joined):
            glyph = glyphs[index][column]
            if glyph is not None:
                line.append(glyph)
            elif not link:
                line.append(" ")
            elif strong[index][column] and not link & (_N | _S):
                line.append(heavy_run)
            elif charset == "ascii":
                line.append("-" if link & (_N | _S) == 0 else "|" if link & (_E | _W) == 0 else "+")
            else:
                line.append(_LIGHT[link])
        text = "".join(line)
        owner = next((n for i, n in nodes.items() if rows[i] - top_row == index and words[i]), None)
        out.append(
            Drawn(
                text,
                f"/nodes/{owner.index}" if owner else "",
                f"the line {words[owner.id]!r}" if owner else "the bracket",
            )
        )
    widest(out, width)
    return finished([line.text for line in out] + caption_lines(document.caption, width, charset))


__all__ = ["BracketDrawing", "bracket_drawing", "bracket_scene", "bracket_text"]

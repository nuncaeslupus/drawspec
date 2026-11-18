"""The `sankey` kind: where a known quantity goes, each flow a band as thick as its amount.

A sankey answers *where does it go, and how much each way* for one quantity
split and merged along the way — a budget, a quarter's tickets, a hall's power.
It states a small set of flows the author already knows; it is not a way to
explore data, and its budget (fourteen nodes, four columns) keeps it that way.

**Columns** are derived from the flows, never written: each node sits one column
past the longest way into it, and every end — a node nothing leaves — is moved to
the last column, so the arrivals line up on the right. A flow that skips a column
passes *through* it, in a slot of its own, so no band is ever drawn across a bar.

**Order down each column** starts from the order written and is improved by
barycentre sweeps, as the layered engine does it: each column sorted by the
amount-weighted mean position of what it is joined to, left to right and back,
keeping whichever order crosses fewest bands. Then each column is slid towards
what it is joined to, its items never overlapping, the fullest column fixed.

**One scale for the whole drawing**: the fullest column's bands are
`SANKEY_BAND` units tall, so every band's thickness is its amount over the
fullest column's total times that, and every bar is as tall as what passes
through it. A band thinner than `SANKEY_MIN_BAND` is refused while validating —
it is a fact about the numbers, not about the type — so no layout runs for it.

**Labels** never sit on a band: the first column's beside its bars on the left,
the last column's on the right, and an inner column's above its bar, inside the
column's slot, where only straight bands pass. A label too wide for every width
tried is a `FitError` naming the node.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from drawspec.errors import FitError
from drawspec.kinds.treemap import bold
from drawspec.scene import Polygon, Primitive, Scene, TextLine, TextSpan, moved
from drawspec.schema import (
    SANKEY_BAND,
    Document,
    SankeyFlow,
    SankeyNode,
    sankey_amount,
    sankey_columns,
)
from drawspec.text.measure import TextMeasurer
from drawspec.text.wrap import TextBlock, wrap
from drawspec.theme import Theme

#: Lengths in units, a unit being the body size over eleven, so the spacing
#: shrinks with the type when the fit pass shrinks it.
BAR: Final = 10.0
"""A node's bar, across: about the cap height of the body type."""
GAP: Final = 12.0
"""Between two things stacked in one column — two bars, or a bar and a label."""
LABEL_GAP: Final = 6.0
"""From a bar to its label, beside it or above it."""
SLOT_MIN: Final = 34.0
"""The narrowest an inner column is: its bar, and a straight stretch each side."""
RUN_MIN: Final = 56.0
"""The least horizontal run a band has between two columns to bend in."""
RUN_MAX: Final = 220.0
"""The most: past it a band is a long flat ribbon, and the drawing is centred instead."""

#: The widths a label is wrapped to, as shares of the canvas, widest first: the
#: first at which every column fits the width wins, so labels break only when
#: the bands would otherwise have no room to bend.
LIMITS: Final = (0.26, 0.22, 0.19, 0.16, 0.13, 0.1)

#: How many points each bend of a band is sampled at. drawspec emits straight
#: segments only, and two dozen reads as a smooth curve at any size drawn.
SAMPLES: Final = 24

#: Sweeps of the crossing reduction and of the vertical relaxation.
SWEEPS: Final = 8
RELAXATIONS: Final = 8

#: How much of the page's ink each band and bar lays down. Lightness is the
#: channel greyscale keeps, so `strong` survives a black-and-white printer.
FLOW_TINT: Final = 0.2
STRONG_TINT: Final = 0.45
NOTE_TINT: Final = 0.1
BAR_TINT: Final = 0.6
NOTE_BAR_TINT: Final = 0.15

#: The role a band and a label are drawn in: furniture, not boxes.
TEXT_ROLE: Final = "step"
BAND_ROLE: Final = "step"
INK: Final = "currentColor"

type _Rect = tuple[float, float, float, float]
"""Left, top, width, height."""

type _Key = tuple[str, int, int]
"""An item in a column: `("n", node index, column)` or `("d", flow index, column)`."""


@dataclass(frozen=True)
class SankeyDrawing:
    """The finished geometry, in final coordinates, for tests and the scene."""

    scene: Scene
    columns: dict[str, int] = field(default_factory=dict)
    """Each node's column, by id."""

    bars: dict[str, _Rect] = field(default_factory=dict)
    """Each node's bar, by id."""

    bands: dict[int, tuple[tuple[float, float], ...]] = field(default_factory=dict)
    """Each flow's band outline, by its index among the flows as written."""

    thickness: dict[int, float] = field(default_factory=dict)
    """Each flow's band thickness, by the same index."""

    ends: dict[int, tuple[float, float]] = field(default_factory=dict)
    """Where each flow's band leaves its source bar and reaches its target bar: the top y."""

    labels: dict[str, _Rect] = field(default_factory=dict)
    """The bounds of each node's words and total, by id."""

    order: dict[int, tuple[str, ...]] = field(default_factory=dict)
    """Each column's items from the top: a node's id, or `>` and a flow index passing."""

    scale: float = 0.0
    """Units of drawing per unit of amount."""


@dataclass
class _Item:
    """One thing stacked in a column: a node's bar, or a flow passing through."""

    key: _Key
    thickness: float
    above: float = 0.0
    """Room the item keeps over its bar — an inner node's label."""
    below: float = 0.0
    top: float = 0.0
    """Where the bar's top edge is."""

    @property
    def centre(self) -> float:
        return self.top + self.thickness / 2


def sankey_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Draw `document` as a sankey."""
    return sankey_drawing(document, theme, measurer).scene


def sankey_drawing(document: Document, theme: Theme, measurer: TextMeasurer) -> SankeyDrawing:
    """Columns, order, one scale, then bands and labels.

    Raises:
        FitError: a node's words, or its total, are too wide for the columns to fit
            the canvas at every label width tried.
    """
    unit = theme.scale["body"] / 11
    width = theme.canvas.width
    nodes = document.sankey_nodes
    flows = document.sankey_flows
    index_of = {node.id: index for index, node in enumerate(nodes)}
    columns = sankey_columns(
        [node.id for node in nodes], [(flow.source, flow.target) for flow in flows]
    )
    count = max(columns.values()) + 1
    column_of = [columns[node.id] for node in nodes]

    totals = _totals(document)

    # Each flow's chain of items: its source, one pass per column it skips, its target.
    chains: list[list[_Key]] = []
    for position, flow in enumerate(flows):
        first, last = columns[flow.source], columns[flow.target]
        chain: list[_Key] = [("n", index_of[flow.source], first)]
        chain.extend(("d", position, column) for column in range(first + 1, last))
        chain.append(("n", index_of[flow.target], last))
        chains.append(chain)

    order = _ordered(nodes, column_of, chains, flows, count)

    labels, slots, run = _labels(document, column_of, count, theme, measurer, width, unit)

    column_totals = [0.0] * count
    for column in range(count):
        for key in order[column]:
            column_totals[column] += _amount(key, totals, flows)
    scale = SANKEY_BAND * unit / max(column_totals)

    items: dict[_Key, _Item] = {}
    for column in range(count):
        for key in order[column]:
            item = _Item(key, _amount(key, totals, flows) * scale)
            if key[0] == "n":
                height = labels[key[1]].height
                if 0 < column < count - 1:
                    item.above = height + LABEL_GAP * unit
                else:
                    item.above = item.below = max(0.0, (height - item.thickness) / 2)
            items[key] = item

    gap = GAP * unit
    stacks = [[items[key] for key in order[column]] for column in range(count)]
    heights = [
        sum(item.above + item.thickness + item.below for item in stack) + gap * (len(stack) - 1)
        for stack in stacks
    ]
    tallest = max(heights)
    for stack, height in zip(stacks, heights, strict=True):
        cursor = (tallest - height) / 2
        for item in stack:
            item.top = cursor + item.above
            cursor = item.top + item.thickness + item.below + gap
    _relax(stacks, chains, flows, items, tallest, gap)

    # Horizontal: the first column's labels, then bar, run, slot, run, ..., bar, labels.
    bar = BAR * unit
    label_gap = LABEL_GAP * unit
    lefts: list[float] = []
    rights: list[float] = []
    x = slots[0] + label_gap
    for column in range(count):
        span = bar if column in (0, count - 1) else slots[column]
        lefts.append(x)
        rights.append(x + span)
        x += span + run
    drawn_width = rights[-1] + label_gap + slots[count - 1]

    # Where each band meets each item: outgoing stacked by what they reach, from the
    # top; incoming by where they come from.
    leaving: dict[_Key, list[tuple[int, int]]] = {}
    arriving: dict[_Key, list[tuple[int, int]]] = {}
    for position, chain in enumerate(chains):
        for hop in range(len(chain) - 1):
            leaving.setdefault(chain[hop], []).append((position, hop))
            arriving.setdefault(chain[hop + 1], []).append((position, hop))
    starts: dict[tuple[int, int], float] = {}
    finishes: dict[tuple[int, int], float] = {}
    for key, hops in leaving.items():
        cursor = items[key].top
        for position, hop in sorted(
            hops, key=lambda h: (items[chains[h[0]][h[1] + 1]].centre, h[0])
        ):
            starts[(position, hop)] = cursor
            cursor += flows[position].amount * scale
    for key, hops in arriving.items():
        cursor = items[key].top
        for position, hop in sorted(hops, key=lambda h: (items[chains[h[0]][h[1]]].centre, h[0])):
            finishes[(position, hop)] = cursor
            cursor += flows[position].amount * scale

    def bar_edges(column: int) -> tuple[float, float]:
        middle = (lefts[column] + rights[column]) / 2
        return middle - bar / 2, middle + bar / 2

    bands: dict[int, tuple[tuple[float, float], ...]] = {}
    ends: dict[int, tuple[float, float]] = {}
    thickness: dict[int, float] = {}
    for position, chain in enumerate(chains):
        band = flows[position].amount * scale
        thickness[position] = band
        top: list[tuple[float, float]] = []
        first_column = chain[0][2]
        y = starts[(position, 0)]
        top.append((bar_edges(first_column)[1], y))
        for hop in range(len(chain) - 1):
            source_column, target_column = chain[hop][2], chain[hop + 1][2]
            y0, y1 = starts[(position, hop)], finishes[(position, hop)]
            top.append((rights[source_column], y0))
            top.extend(_bend(rights[source_column], y0, lefts[target_column], y1))
            if chain[hop + 1][0] == "d":
                top.append((rights[target_column], y1))
        last_column = chain[-1][2]
        top.append((bar_edges(last_column)[0], finishes[(position, len(chain) - 2)]))
        top = _deduplicated(top)
        bottom = [(px, py + band) for px, py in top]
        bands[position] = (*top, *reversed(bottom))
        ends[position] = (starts[(position, 0)], finishes[(position, len(chain) - 2)])

    note_nodes = {node.id for node in nodes if node.role == "note"}
    primitives: list[Primitive] = []
    texts: list[Primitive] = []

    def tint(flow: SankeyFlow) -> float:
        if flow.role == "strong":
            return STRONG_TINT
        if flow.source in note_nodes or flow.target in note_nodes:
            return NOTE_TINT
        return FLOW_TINT

    for position in sorted(range(len(flows)), key=lambda p: (tint(flows[p]), p)):
        primitives.append(
            Polygon(
                BAND_ROLE,
                points=bands[position],
                fill="solid",
                fill_colour=INK,
                fill_opacity=tint(flows[position]),
                region=True,
            )
        )

    bars: dict[str, _Rect] = {}
    label_bounds: dict[str, _Rect] = {}
    for index, node in enumerate(nodes):
        column = column_of[index]
        item = items[("n", index, column)]
        left, right = bar_edges(column)
        bars[node.id] = (left, item.top, bar, item.thickness)
        primitives.append(
            Polygon(
                node.role,
                points=_corners(left, item.top, bar, item.thickness),
                fill="solid",
                fill_colour=INK,
                fill_opacity=NOTE_BAR_TINT if node.role == "note" else BAR_TINT,
            )
        )
        label = labels[index]
        if column == 0:
            anchor, x_text, x_left = "end", left - label_gap, left - label_gap - label.width
            y_text = item.centre - label.height / 2
        elif column == count - 1:
            anchor, x_text, x_left = "start", right + label_gap, right + label_gap
            y_text = item.centre - label.height / 2
        else:
            middle = (left + right) / 2
            anchor, x_text, x_left = "middle", middle, middle - label.width / 2
            y_text = item.top - label_gap - label.height
        texts.extend(label.lines(x_text, y_text, anchor))
        label_bounds[node.id] = (x_left, y_text, label.width, label.height)

    # The drawing's own top and bottom: a side label may stand clear of its bar.
    ceiling = min(0.0, *(bounds[1] for bounds in label_bounds.values()))
    floor = max(tallest, *(bounds[1] + bounds[3] for bounds in label_bounds.values()))
    scene = Scene(
        width=drawn_width,
        height=floor - ceiling,
        primitives=(*primitives, *texts),
        title=document.title,
        description=document.description,
    )
    if ceiling < 0:
        scene = Scene(
            width=scene.width,
            height=scene.height,
            primitives=tuple(moved(primitive, 0.0, -ceiling) for primitive in scene.primitives),
            title=scene.title,
            description=scene.description,
        )
    return SankeyDrawing(
        scene=scene,
        columns=dict(columns),
        bars=bars,
        bands=bands,
        thickness=thickness,
        ends=ends,
        labels=label_bounds,
        order={
            column: tuple(
                nodes[key[1]].id if key[0] == "n" else f">{key[1]}" for key in order[column]
            )
            for column in range(count)
        },
        scale=scale,
    )


def _amount(key: _Key, totals: list[float], flows: tuple[SankeyFlow, ...]) -> float:
    return totals[key[1]] if key[0] == "n" else flows[key[1]].amount


def _ordered(
    nodes: tuple[SankeyNode, ...],
    column_of: list[int],
    chains: list[list[_Key]],
    flows: tuple[SankeyFlow, ...],
    count: int,
) -> list[list[_Key]]:
    """Each column's items, top to bottom, with the fewest bands crossing.

    Starts from the written order — nodes as written, then each flow passing
    through in the order written — and sweeps: each column sorted by the
    amount-weighted mean position of what it is joined to in the column before,
    left to right, then after, right to left. The order with the fewest crossings
    is kept, the first found on a tie, so the written order wins when nothing beats
    it and the result is the same on every run.
    """
    order: list[list[_Key]] = [[] for _ in range(count)]
    for index, column in enumerate(column_of):
        order[column].append(("n", index, column))
    for chain in chains:
        for key in chain[1:-1]:
            order[key[2]].append(key)

    # Joins between neighbouring columns: (left item, right item, amount).
    joins: list[list[tuple[_Key, _Key, float]]] = [[] for _ in range(count)]
    for position, chain in enumerate(chains):
        for hop in range(len(chain) - 1):
            joins[chain[hop][2]].append((chain[hop], chain[hop + 1], flows[position].amount))

    best = [list(column) for column in order]
    fewest = _crossings(order, joins)
    for sweep in range(SWEEPS):
        forward = sweep % 2 == 0
        sequence = range(1, count) if forward else range(count - 2, -1, -1)
        for column in sequence:
            neighbour = column - 1 if forward else column + 1
            ranks = {key: rank for rank, key in enumerate(order[neighbour])}
            pulls: dict[_Key, tuple[float, float]] = {}
            for left, right, amount in joins[min(column, neighbour)]:
                mine, theirs = (right, left) if forward else (left, right)
                total, weight = pulls.get(mine, (0.0, 0.0))
                pulls[mine] = (total + ranks[theirs] * amount, weight + amount)
            current = {key: rank for rank, key in enumerate(order[column])}
            scale = max(len(order[neighbour]) - 1, 1) / max(len(order[column]) - 1, 1)
            order[column].sort(
                key=lambda key: (
                    pulls[key][0] / pulls[key][1] if key in pulls else current[key] * scale,
                    current[key],
                )
            )
        crossings = _crossings(order, joins)
        if crossings < fewest:
            fewest = crossings
            best = [list(column) for column in order]
    return best


def _crossings(order: list[list[_Key]], joins: list[list[tuple[_Key, _Key, float]]]) -> int:
    """How many pairs of bands cross between neighbouring columns."""
    found = 0
    for column, between in enumerate(joins[:-1]):
        left = {key: rank for rank, key in enumerate(order[column])}
        right = {key: rank for rank, key in enumerate(order[column + 1])}
        ranked = [(left[a], right[b]) for a, b, _ in between]
        for one, (a1, b1) in enumerate(ranked):
            for a2, b2 in ranked[one + 1 :]:
                if (a1 - a2) * (b1 - b2) < 0:
                    found += 1
    return found


def _relax(
    stacks: list[list[_Item]],
    chains: list[list[_Key]],
    flows: tuple[SankeyFlow, ...],
    items: dict[_Key, _Item],
    tallest: float,
    gap: float,
) -> None:
    """Slide each column's items towards what they are joined to, never overlapping.

    Each item's centre is moved to the amount-weighted mean of its neighbours'
    centres — the column before on the way right, the column after on the way
    back — then the column is pushed apart from the top and in from the bottom, in
    its order. The fullest column has no room to move, so it anchors the rest.
    """
    before: dict[_Key, list[tuple[_Key, float]]] = {}
    after: dict[_Key, list[tuple[_Key, float]]] = {}
    for position, chain in enumerate(chains):
        for hop in range(len(chain) - 1):
            amount = flows[position].amount
            before.setdefault(chain[hop + 1], []).append((chain[hop], amount))
            after.setdefault(chain[hop], []).append((chain[hop + 1], amount))
    count = len(stacks)
    for _ in range(RELAXATIONS):
        for neighbours, sequence in (
            (before, range(1, count)),
            (after, range(count - 2, -1, -1)),
        ):
            for column in sequence:
                for item in stacks[column]:
                    joined = neighbours.get(item.key)
                    if not joined:
                        continue
                    weight = sum(amount for _, amount in joined)
                    centre = sum(items[key].centre * amount for key, amount in joined) / weight
                    item.top = centre - item.thickness / 2
                _separated(stacks[column], tallest, gap)


def _separated(stack: list[_Item], tallest: float, gap: float) -> None:
    """Push a column's items apart, in order, inside the drawing's height."""
    cursor = 0.0
    for item in stack:
        item.top = max(item.top, cursor + item.above)
        cursor = item.top + item.thickness + item.below + gap
    cursor = tallest
    for item in reversed(stack):
        item.top = min(item.top, cursor - item.below - item.thickness)
        cursor = item.top - item.above - gap


def _labels(
    document: Document,
    column_of: list[int],
    count: int,
    theme: Theme,
    measurer: TextMeasurer,
    width: float,
    unit: float,
) -> tuple[list[_Label], list[float], float]:
    """Every node's label, each column's width, and the run between two columns.

    Each column's width is its widest label's — an inner column's at least
    `SLOT_MIN` — and the first and last columns' widths are the label room beside
    their bars. The labels are wrapped to the widest of `LIMITS` at which the
    columns leave every run at least `RUN_MIN` units to bend in.

    Raises:
        FitError: no width tried leaves the bands room.
    """
    nodes = document.sankey_nodes
    totals = _totals(document)
    bar = BAR * unit
    label_gap = LABEL_GAP * unit
    widest = ""
    for share in LIMITS:
        limit = width * share
        labels: list[_Label] = []
        for index, node in enumerate(nodes):
            text = bold(node.text) if node.role == "emphasis" else node.text
            value = sankey_amount(totals[index], document.unit) if document.values else None
            label = _stacked(text, value, limit, theme, measurer)
            if label is None:
                widest = node.id
                break
            labels.append(label)
        if len(labels) < len(nodes):
            break
        slots = [0.0] * count
        for index, label in enumerate(labels):
            column = column_of[index]
            slots[column] = max(slots[column], label.width)
        for column in range(1, count - 1):
            slots[column] = max(slots[column], SLOT_MIN * unit)
        fixed = (
            slots[0]
            + slots[count - 1]
            + 2 * (label_gap + bar)
            + sum(slots[column] for column in range(1, count - 1))
        )
        room = (width - fixed) / (count - 1)
        if room >= RUN_MIN * unit:
            return labels, slots, min(room, RUN_MAX * unit)
        widest = nodes[max(range(len(nodes)), key=lambda index: (labels[index].width, -index))].id
    raise FitError(
        f"the node {widest!r} has words, or a total, too wide to leave {count} columns of "
        f"bands room to bend in {width:.0f} units across, at every width its label was "
        f"wrapped to. Shorten its words, or give the diagram more `width`."
    )


def _totals(document: Document) -> list[float]:
    """Each node's total: what passes through it — the larger of what arrives and leaves."""
    index_of = {node.id: index for index, node in enumerate(document.sankey_nodes)}
    into = [0.0] * len(index_of)
    out = [0.0] * len(index_of)
    for flow in document.sankey_flows:
        out[index_of[flow.source]] += flow.amount
        into[index_of[flow.target]] += flow.amount
    return [max(a, b) for a, b in zip(into, out, strict=True)]


def _bend(x0: float, y0: float, x1: float, y1: float) -> list[tuple[float, float]]:
    """A band's edge from one column to the next: level at both ends, an S between."""
    if abs(y1 - y0) < 1e-9:
        return [(x1, y1)]
    middle = (x0 + x1) / 2
    found: list[tuple[float, float]] = []
    for step in range(1, SAMPLES + 1):
        t = step / SAMPLES
        u = 1 - t
        x = u**3 * x0 + 3 * u * u * t * middle + 3 * u * t * t * middle + t**3 * x1
        y = (u**3 + 3 * u * u * t) * y0 + (3 * u * t * t + t**3) * y1
        found.append((x, y))
    return found


def _deduplicated(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    found: list[tuple[float, float]] = []
    for point in points:
        if found and abs(found[-1][0] - point[0]) < 1e-9 and abs(found[-1][1] - point[1]) < 1e-9:
            continue
        found.append(point)
    return found


def _corners(
    left: float, top: float, width: float, height: float
) -> tuple[tuple[float, float], ...]:
    right, bottom = left + width, top + height
    return ((left, top), (right, top), (right, bottom), (left, bottom))


@dataclass(frozen=True)
class _Label:
    """A node's words over its total, each wrapped to one width."""

    words: TextBlock
    value: TextBlock | None

    @property
    def width(self) -> float:
        return max(self.words.width, self.value.width if self.value is not None else 0.0)

    @property
    def height(self) -> float:
        if self.value is None:
            return self.words.height
        return self.words.height + self.value.height

    def lines(self, x: float, top: float, anchor: str) -> list[TextLine]:
        """The words from `top` down, then the total under them, all at the body size."""
        found = _lines(self.words, x, top, anchor)
        if self.value is not None:
            found.extend(_lines(self.value, x, top + self.words.height, anchor))
        return found


def _stacked(
    words: str, value: str | None, width: float, theme: Theme, measurer: TextMeasurer
) -> _Label | None:
    """`words` wrapped to `width` over `value` on one line, or `None` if either is too wide.

    The total is never broken: a number split from its unit reads as two things.
    """
    try:
        block = wrap(words, width, measurer, theme=theme, level="body", lead=False)
    except FitError:
        return None
    number: TextBlock | None = None
    if value is not None:
        number = wrap(value, 1e6, measurer, theme=theme, level="body")
        if number.width > width + 1e-6:
            return None
    return _Label(block, number)


def _lines(block: TextBlock, x: float, top: float, anchor: str) -> list[TextLine]:
    """A wrapped block as one `TextLine` per line, from `top` down."""
    found: list[TextLine] = []
    for index, line in enumerate(block.lines):
        spans = tuple(
            TextSpan(text=span.text, font=span.font, weight=span.weight)
            for span in line.spans
            if span.text
        )
        if spans:
            found.append(
                TextLine(
                    TEXT_ROLE,
                    x=x,
                    y=top + block.baseline(index),
                    spans=spans,
                    level="body",
                    anchor=anchor,
                )
            )
    return found


__all__ = ["SankeyDrawing", "sankey_drawing", "sankey_scene"]

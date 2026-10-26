"""The `neuralnet` kind: a neural network's layers, in the two notations figures use.

**`neurons`** is the textbook's fully connected figure (Nielsen's, NN-SVG's FCNN
style): each layer a column of circles, centred on one another, every neuron
joined by a plain line to every neuron of the next layer. A layer larger than
`NEURALNET_NEURONS_SHOWN` is drawn as its first three neurons, a column of dots
and its last two, joined like the rest, with its size written under its name —
the 784 inputs of an MNIST network, as every textbook draws them. A bias unit is
a circle marked `+1` at the top of its column, feeding the next layer only.
An arrow comes into each input neuron and leaves each output neuron.

**`blocks`** is a paper's architecture figure (LeNet, ResNet, the Transformer,
PlotNeuralNet): each layer a box in sequence, an arrow from each to the next,
its output tensor written beside it, its fill taken by `type` with a key under
the drawing. A skip connection leaves the top of its layer (the right side, when
the network runs down or up), runs clear of every box and frame it bypasses, and
comes back into the layer it feeds. A repeated block is drawn once, inside a frame
marked `xN`. A set of branches (GoogLeNet's Inception module) is two to four
towers stacked across the sequence, the arrow from the layer before splitting to
each and every tower joining into the layer after. Nothing is placed by an
engine: a sequence is a line, so the coordinates are computed along it and across
it, then turned to the direction.

The text form is a model summary: in `neurons`, a row per layer with its neurons
and its parameters (weights and biases, computed); in `blocks`, a row per layer
with its type and output shape, then the skips and repeats.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Final

from drawspec.errors import DrawspecError, FitError
from drawspec.geometry import Box, normalise, size_box
from drawspec.kinds.common import box_primitives, painted
from drawspec.legend import SWATCH_ROLE, Entry, height_of, primitives_for
from drawspec.routing import Route, arrow_run, edge_primitives
from drawspec.scene import Ellipse, Primitive, Rect, Scene, TextLine, TextRun, TextSpan
from drawspec.schema import NEURALNET_NEURONS_SHOWN, Document, NeuralLayer
from drawspec.text.measure import TextMeasurer
from drawspec.textgrid import Drawn, caption_lines, cells, finished, pad, spelt, widest
from drawspec.theme import Theme

#: The role a neuron's circle, its label and a block's box are drawn in.
NEURON_ROLE: Final = "step"
BLOCK_ROLE: Final = "step"

#: The headless line joining two neurons: a dense figure has dozens, and a head on
#: each would bury the circles they point at. The layers' order says the way.
LINK_ROLE: Final = "link"

#: The arrow from one block to the next, and a skip connection's.
FLOW_ROLE: Final = "flow"

#: A repeated block's frame.
FRAME_ROLE: Final = "group"

#: A bias unit's label, as Ng's and Nielsen's figures write it.
BIAS: Final = "+1"

#: How many neurons a cut layer shows above its dots, and below them.
HEAD: Final = 3
TAIL: Final = 2

#: Lengths in units, a unit being the body size over eleven.
MIN_RADIUS: Final = 9.0
"""The smallest a neuron is drawn."""

NAME_AIR: Final = 3.5
"""The least air between a neuron's label and its circle."""

NEURON_GAP: Final = 7.0
"""Between two neurons of a column."""

COLUMN_MIN: Final = 60.0
COLUMN_MAX: Final = 150.0
"""The least and the most between two columns' centres; between the two, the
columns spread to the canvas."""

STUB: Final = 20.0
"""How far the arrow into each input neuron, and out of each output neuron, reaches."""

DOT: Final = 1.4
"""A dot's radius, in a cut layer's column of three."""

NAME_GAP: Final = 7.0
"""Between the lowest neuron and the layer names, and between two names side by side."""

ARROW_MIN: Final = 26.0
"""The shortest arrow between two blocks, its head included."""

LABEL_GAP: Final = 4.0
"""Between a box and its shape, a lane and its label, a frame and its mark."""

LANE_GAP: Final = 10.0
"""Between a skip's lane and whatever it passes over."""

FRAME_PAD: Final = 8.0
"""Between a repeated block's frame and what it holds."""

TOWER_GAP: Final = 12.0
"""Between two branches' towers, side by side."""

FAN: Final = 10.0
"""What a gap that splits into branches, or joins them, adds for the turn of its lines."""

BLOCK_SHARE: Final = 0.3
"""The widest a block's box may be, as a share of the canvas."""


Point = tuple[float, float]
Bounds = tuple[float, float, float, float]


def shown(size: int) -> tuple[int | None, ...]:
    """The neurons a layer of `size` is drawn with, top to bottom; `None` is the dots."""
    if size <= NEURALNET_NEURONS_SHOWN:
        return tuple(range(size))
    return (*range(HEAD), None, *range(size - TAIL, size))


def parameters(layers: Sequence[NeuralLayer]) -> list[int]:
    """Each layer's weights and biases, fully connected to the one before; 0 for the first."""
    return [0] + [previous.size * layer.size + layer.size for previous, layer in pairwise(layers)]


def repeat_mark(times: int, text: str) -> str:
    """A repeated block's mark: `x6`, or `Encoder x6`."""
    mark = f"\N{MULTIPLICATION SIGN}{times}"
    return f"{text} {mark}" if text else mark


def neuralnet_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Render a `neuralnet` document to a `Scene`.

    Raises:
        FitError: the network does not fit the canvas at this type scale.
    """
    if not document.neural_layers:
        raise DrawspecError("a neural network needs at least one layer")
    if document.neural_style == "blocks":
        return _blocks_scene(document, theme, measurer)
    return _neurons_scene(document, theme, measurer)


# ---------------------------------------------------------------------------
# Neurons
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Neuron:
    """One drawn neuron: its layer, its place in it (`-1` for a bias unit), its circle."""

    layer: int
    index: int
    cx: float
    cy: float
    r: float
    label: str = ""


def neurons_drawing(
    document: Document, theme: Theme, measurer: TextMeasurer
) -> tuple[list[Neuron], list[tuple[Point, Point]], list[Primitive], float, float]:
    """The neurons, the lines between them and every other mark, in scene coordinates.

    Returns the neurons, the connecting lines (border to border), the dots and
    names, and the drawing's width and height.
    """
    layers = document.neural_layers
    unit = theme.scale["body"] / 11
    body = theme.scale["body"]
    small = theme.scale["label"]
    sans = theme.font.default
    line = measurer.measure("", sans, body)
    half = (line.ascent + line.descent) / 2
    words = [label for layer in layers for label in layer.labels]
    if any(layer.bias for layer in layers):
        words.append(BIAS)
    radius = max(
        MIN_RADIUS * unit,
        *((measurer.measure(word, sans, body).width / 2) + NAME_AIR * unit for word in words),
        half + NAME_AIR * unit,
    )
    pitch = 2 * radius + NEURON_GAP * unit
    slots = [(len(shown(layer.size)) + (1 if layer.bias else 0)) for layer in layers]
    tallest = max(slots)
    names = [layer.text for layer in layers]
    notes = [
        f"{layer.size:,} neurons" if layer.size > NEURALNET_NEURONS_SHOWN else ""
        for layer in layers
    ]
    spans = [
        max(
            measurer.measure(name, sans, body).width if name else 0.0,
            measurer.measure(note, sans, small).width if note else 0.0,
            2 * radius,
        )
        for name, note in zip(names, notes, strict=True)
    ]
    least = max(
        [COLUMN_MIN * unit]
        + [(first + second) / 2 + NAME_GAP * unit for first, second in pairwise(spans)]
    )
    canvas = document.width if document.width else theme.canvas.width
    reach = radius + STUB * unit
    left, right = max(spans[0] / 2, reach), max(spans[-1] / 2, reach)
    count = len(layers)
    gap = 0.0
    if count > 1:
        gap = min(max((canvas - left - right) / (count - 1), least), max(least, COLUMN_MAX * unit))
    width = left + right + gap * (count - 1)
    if width > canvas + 0.01:
        raise FitError(
            f"this network needs {width:.0f} across for its {count} layers and the canvas is "
            f"{canvas:.0f}. Shorten the layer names, give the document more `width`, or draw it "
            f"as `blocks`."
        )

    neurons: list[Neuron] = []
    dots: list[Primitive] = []
    columns: list[list[Neuron]] = []
    for position, layer in enumerate(layers):
        cx = left + gap * position
        top = (tallest - slots[position]) * pitch / 2
        column: list[Neuron] = []
        slot = 0
        if layer.bias:
            column.append(Neuron(position, -1, cx, top + pitch / 2, radius, BIAS))
            slot = 1
        for index in shown(layer.size):
            cy = top + (slot + 0.5) * pitch
            slot += 1
            if index is None:
                for step in (-1, 0, 1):
                    dots.append(
                        painted(
                            Ellipse(
                                NEURON_ROLE,
                                cx=cx,
                                cy=cy + step * pitch / 4,
                                rx=DOT * unit,
                                ry=DOT * unit,
                            ),
                            "solid",
                            "currentColor",
                        )
                    )
                continue
            label = layer.labels[index] if index < len(layer.labels) else ""
            column.append(Neuron(position, index, cx, cy, radius, label))
        columns.append(column)
        neurons.extend(column)

    links: list[tuple[Point, Point]] = []
    for sources, targets in pairwise(columns):
        for source in sources:
            for target in targets:
                if target.index < 0:
                    continue  # a bias unit is fed by nothing
                dx, dy = target.cx - source.cx, target.cy - source.cy
                length = (dx * dx + dy * dy) ** 0.5
                ux, uy = dx / length, dy / length
                links.append(
                    (
                        (round(source.cx + ux * radius, 3), round(source.cy + uy * radius, 3)),
                        (round(target.cx - ux * radius, 3), round(target.cy - uy * radius, 3)),
                    )
                )

    # What goes in and what comes out, as Nielsen draws it: an arrow into each input
    # neuron and one out of each output neuron. A bias unit takes no input.
    marks: list[Primitive] = list(dots)
    if len(columns) > 1:
        for neuron in columns[0]:
            if neuron.index >= 0:
                stub = ((neuron.cx - reach, neuron.cy), (neuron.cx - radius, neuron.cy))
                marks.extend(edge_primitives(Route("", "", FLOW_ROLE, stub), theme))
        for neuron in columns[-1]:
            stub = ((neuron.cx + radius, neuron.cy), (neuron.cx + reach, neuron.cy))
            marks.extend(edge_primitives(Route("", "", FLOW_ROLE, stub), theme))
    height = tallest * pitch
    has_names = any(names)
    has_notes = any(notes)
    small_line = measurer.measure("", sans, small)
    baseline = height + NAME_GAP * unit + line.ascent
    note_baseline = (
        baseline + line.descent if has_names else height + NAME_GAP * unit
    ) + small_line.ascent
    for position, (name, note) in enumerate(zip(names, notes, strict=True)):
        cx = left + gap * position
        if name:
            marks.append(
                TextRun(NEURON_ROLE, x=cx, y=baseline, text=name, level="body", anchor="middle")
            )
        if note:
            marks.append(
                TextRun(
                    NEURON_ROLE, x=cx, y=note_baseline, text=note, level="label", anchor="middle"
                )
            )
    if has_notes:
        height = note_baseline + small_line.descent
    elif has_names:
        height = baseline + line.descent
    return neurons, links, marks, width, height


def _neurons_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    neurons, links, marks, width, height = neurons_drawing(document, theme, measurer)
    body = measurer.measure("", theme.font.default, theme.scale["body"])
    primitives: list[Primitive] = []
    for start, end in links:
        primitives.extend(edge_primitives(Route("", "", LINK_ROLE, (start, end)), theme))
    for neuron in neurons:
        primitives.append(
            Ellipse(NEURON_ROLE, cx=neuron.cx, cy=neuron.cy, rx=neuron.r, ry=neuron.r)
        )
        if neuron.label:
            primitives.append(
                TextLine(
                    NEURON_ROLE,
                    x=neuron.cx,
                    y=neuron.cy + (body.ascent - body.descent) / 2,
                    spans=(TextSpan(text=neuron.label, font=theme.font.default),),
                    level="body",
                    anchor="middle",
                )
            )
    primitives.extend(marks)
    return Scene(
        width=width,
        height=height,
        primitives=tuple(primitives),
        title=document.title,
        description=document.description,
        metadata=(("style", "neurons"),),
    )


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------
#
# Laid out in (u, v): u along the sequence, v across it, the boxes centred on
# v = 0. Skips take the negative side (above, or right when vertical), shapes and
# repeat marks the positive side (below, or left). `_turned` maps to the page.


@dataclass(frozen=True)
class _Text:
    """A label to set: its words, level, and where, already on the page."""

    text: str
    level: str
    x: float
    y: float
    anchor: str
    bounds: Bounds


def _blocks_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    canvas = document.width if document.width else theme.canvas.width
    direction = document.neural_direction or "right"
    try:
        return _blocks_in(document, theme, measurer, direction, canvas, wrap=False)
    except FitError:
        if direction != "right":
            raise
    # Across, when the boxes at their own widths do not fit, they share the canvas:
    # each takes its part of what the arrows leave, and its words wrap to it.
    try:
        return _blocks_in(document, theme, measurer, "right", canvas, wrap=True)
    except FitError:
        if document.neural_direction:
            raise
    return _blocks_in(document, theme, measurer, "down", canvas, wrap=False)


def _blocks_in(
    document: Document,
    theme: Theme,
    measurer: TextMeasurer,
    direction: str,
    canvas: float,
    *,
    wrap: bool,
) -> Scene:
    layers = document.neural_layers
    unit = theme.scale["body"] / 11
    sans = theme.font.default
    small = theme.scale["label"]
    across = direction == "right"
    limit = canvas * BLOCK_SHARE
    head = theme.head_length_for(FLOW_ROLE)
    inner = max(ARROW_MIN * unit, head + 12 * unit)  # the arrow between two boxes
    # Every box drawn, a tower's included: (layer, its item, its tower or -1).
    drawn = [
        (part, index, tower)
        for index, layer in enumerate(layers)
        for tower, part in (
            [(-1, layer)]
            if not layer.branches
            else [(tower, part) for tower, branch in enumerate(layer.branches) for part in branch]
        )
    ]
    if wrap:
        count = sum(max(map(len, layer.branches)) if layer.branches else 1 for layer in layers)
        arrows = (count - 1) * ARROW_MIN * unit
        limit = min(limit, max((canvas - arrows) / count, 0.0))
    sized = [
        size_box(part.text, theme=theme, measurer=measurer, role=BLOCK_ROLE, max_width=limit)
        for part, _, _ in drawn
    ]
    if across:
        tallest = max(box.height for box in sized)
        sized = [box.resized(height=tallest) for box in sized]
    else:
        sized = list(normalise(sized))

    def run(box: Box) -> float:
        return box.width if across else box.height

    def depth(box: Box) -> float:
        return box.height if across else box.width

    # Each item's extent along the sequence and across it: a layer's box, or a set
    # of branches' towers stacked across the sequence, as long as the longest.
    along: list[float] = []
    thick: list[float] = []
    towers: dict[int, list[list[tuple[NeuralLayer, Box, float]]]] = {}
    for index, layer in enumerate(layers):
        mine = [
            (part, box, tower)
            for (part, item, tower), box in zip(drawn, sized, strict=True)
            if item == index
        ]
        if not layer.branches:
            along.append(run(mine[0][1]))
            thick.append(depth(mine[0][1]))
            continue
        stacks: list[list[tuple[NeuralLayer, Box, float]]] = [[] for _ in layer.branches]
        for part, box, tower in mine:
            offset = sum(run(other) + inner for _, other, _ in stacks[tower])
            stacks[tower].append((part, box, offset))
        towers[index] = stacks
        along.append(max(stack[-1][2] + run(stack[-1][1]) for stack in stacks))
        side = max(depth(box) for _, box, _ in mine)
        thick.append(len(stacks) * side + (len(stacks) - 1) * TOWER_GAP * unit)
    label_line = measurer.measure("", sans, small)
    label_height = label_line.ascent + label_line.descent

    def extent(text: str) -> tuple[float, float]:
        """A label's extent along the sequence and across it."""
        wide = measurer.measure(text, sans, small).width
        return (wide, label_height) if across else (label_height, wide)

    shapes = [extent(layer.shape) if layer.shape else (0.0, 0.0) for layer in layers]
    ids = {layer.id: index for index, layer in enumerate(layers) if layer.id}
    repeats = [(ids[span.source], ids[span.target], span) for span in document.neural_repeats]
    skips = [(ids[span.source], ids[span.target], span) for span in document.neural_skips]
    pad = FRAME_PAD * unit
    fan = FAN * unit
    approach = arrow_run(theme, FLOW_ROLE)  # the run into a box after a turn

    # Along the sequence: each gap holds an arrow, the overhang of the shapes on
    # either side when they lie along it, and the padding of a frame it enters or
    # leaves. A frame's leading padding holds a whole arrow run, so a skip inside
    # the frame can branch off the arrow entering it a run before the box.
    lead = pad + approach
    starts = {first for first, _, _ in repeats}
    ends = {last for _, last, _ in repeats}
    # A frame that opens on a set of branches holds the split's turn as well.
    leads = {first: lead + (fan if first in towers else 0.0) for first in starts}
    # Where a skip branches off an arrow, the junction keeps a whole arrow run
    # before the box ahead (and before a split's turn), and a fan's length after
    # the box behind, so the head never sits on the junction.
    branching = {first + 1 for first, _, _ in skips}
    positions = [0.0]
    for index in range(1, len(layers)):
        gap = inner + fan * ((index in towers) + (index - 1 in towers))
        if index in branching:
            gap = max(gap, approach + fan * (1 + (index in towers)))
        if across:
            overhang = (
                max(shapes[index - 1][0] - along[index - 1], 0) / 2
                + max(shapes[index][0] - along[index], 0) / 2
            )
            gap = max(gap, overhang + LABEL_GAP * unit)
        gap += pad * (index - 1 in ends) + leads.get(index, 0.0)
        positions.append(positions[-1] + along[index - 1] + gap)
    centres = [position + size / 2 for position, size in zip(positions, along, strict=True)]

    # Across: the positive side holds each shape, then frames and their marks; the
    # negative side the skips' lanes, worked out from the innermost span outwards.
    near = [-size / 2 for size in thick]  # the most negative v taken over each layer
    far = [
        size / 2 + (LABEL_GAP * unit + shape[1] if shape[1] else 0.0)
        for size, shape in zip(thick, shapes, strict=True)
    ]
    lane_of: dict[int, float] = {}
    frame_of: dict[int, tuple[float, float]] = {}
    work = sorted(
        [(last - first - 1, 0, index) for index, (first, last, _) in enumerate(skips)]
        + [(last - first, 1, index) for index, (first, last, _) in enumerate(repeats)]
    )
    skip_labels = [extent(span.text) if span.text else (0.0, 0.0) for _, _, span in skips]
    for _, is_repeat, index in work:
        if is_repeat:
            first, last, span = repeats[index]
            low = min(near[first : last + 1]) - pad
            high = max(far[first : last + 1]) + pad
            frame_of[index] = (low, high)
            for place in range(first, last + 1):
                near[place] = low
                far[place] = high + LABEL_GAP * unit + extent(repeat_mark(span.times, span.text))[1]
            continue
        # A skip branches off the arrow leaving its `from`, so its lane runs over
        # the layers after it, up to the one it feeds.
        first, last, _ = skips[index]
        lane = min(near[first + 1 : last + 1]) - max(LANE_GAP * unit, approach)
        lane_of[index] = lane
        taken = lane - (skip_labels[index][1] + LABEL_GAP * unit if skip_labels[index][1] else 0.0)
        for place in range(first + 1, last + 1):
            near[place] = taken

    # Where each skip branches: mid-arrow, or just inside a frame the arrow enters
    # when the skip is inside it. Where it lands: spread over its box's edge, the
    # longer skips on the later side, so no lane runs across another's riser.
    def split(index: int) -> float:
        """Where the arrow into the set of branches at `index` turns to each tower."""
        return positions[index] - approach

    def join(index: int) -> float:
        """Where the towers of the set at `index - 1` turn to join at `index`."""
        return positions[index] - leads.get(index, 0.0) - approach

    branches: dict[int, float] = {}
    for index, (first, last, _) in enumerate(skips):
        start, end = positions[first] + along[first], positions[first + 1]
        if first in ends:
            start += pad
        inside = any(begin == first + 1 and last <= stop for begin, stop, _ in repeats)
        turn = end - approach - (fan if first + 1 in towers else 0.0)
        if inside or first + 1 not in starts:
            branches[index] = turn  # a run before the box (or the split), inside any frame
        else:
            # Round a frame that opens on the next layer: before the frame's edge.
            branches[index] = (start + end - leads[first + 1]) / 2
    ports: dict[int, float] = {}
    for place in range(len(layers)):
        arriving = sorted(
            (index for index, (_, last, _) in enumerate(skips) if last == place),
            key=lambda index: skips[index][1] - skips[index][0],
        )
        for slot, index in enumerate(arriving):
            ports[index] = positions[place] + along[place] * (slot + 1) / (len(arriving) + 1)

    def turned(u: float, v: float) -> Point:
        if across:
            return (u, v)
        if direction == "down":
            return (-v, u)
        return (-v, -u)

    def rect(u0: float, u1: float, v0: float, v1: float) -> Bounds:
        (x0, y0), (x1, y1) = turned(u0, v0), turned(u1, v1)
        return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))

    def middle_of(index: int, tower: int) -> float:
        """A tower's centre across the sequence: the first branch at the top, or the left."""
        count = len(towers[index])
        side = (thick[index] - (count - 1) * TOWER_GAP * unit) / count
        place = tower if across else count - 1 - tower  # down the page v runs right to left
        return -thick[index] / 2 + side / 2 + place * (side + TOWER_GAP * unit)

    placed: list[tuple[NeuralLayer, Box]] = []
    strokes: list[tuple[str, tuple[Point, ...]]] = []

    def arrow(*points: tuple[float, float]) -> None:
        kept = [points[0], *(b for a, b in pairwise(points) if b != a)]
        strokes.append((FLOW_ROLE, tuple(turned(u, v) for u, v in kept)))

    for index, layer in enumerate(layers):
        if index not in towers:
            box = sized[[item for _, item, _ in drawn].index(index)]
            left, top, _, _ = rect(
                positions[index],
                positions[index] + along[index],
                -thick[index] / 2,
                thick[index] / 2,
            )
            placed.append((layer, box.moved_to(left, top)))
            continue
        for tower, stack in enumerate(towers[index]):
            v = middle_of(index, tower)
            for (part, box, offset), after in zip(stack, [*stack[1:], None], strict=True):
                u = positions[index] + offset
                left, top, _, _ = rect(u, u + run(box), v - depth(box) / 2, v + depth(box) / 2)
                placed.append((part, box.moved_to(left, top)))
                if after is not None:
                    arrow((u + run(box), v), (positions[index] + after[2], v))

    for index in range(1, len(layers)):
        out, into = positions[index - 1] + along[index - 1], positions[index]
        if index in towers:
            turn = split(index)
            for tower in range(len(towers[index])):
                v = middle_of(index, tower)
                arrow((out, 0.0), (turn, 0.0), (turn, v), (into, v))
        elif index - 1 in towers:
            turn = join(index)
            for tower, stack in enumerate(towers[index - 1]):
                v = middle_of(index - 1, tower)
                end = positions[index - 1] + stack[-1][2] + run(stack[-1][1])
                arrow((end, v), (turn, v), (turn, 0.0), (into, 0.0))
        else:
            arrow((out, 0.0), (into, 0.0))
    for index, (_, last, _) in enumerate(skips):
        lane = lane_of[index]
        out, back = branches[index], ports[index]
        strokes.append(
            (
                FLOW_ROLE,
                (
                    turned(out, 0.0),
                    turned(out, lane),
                    turned(back, lane),
                    turned(back, -thick[last] / 2),
                ),
            )
        )

    texts: list[_Text] = []
    gap = LABEL_GAP * unit

    def label(text: str, u: float, v: float, side: int) -> None:
        """Set `text` beside (u, v), on the positive side (`side` 1) or the negative (-1)."""
        wide = measurer.measure(text, sans, small).width
        x, y = turned(u, v)
        if across:
            top = y + gap if side > 0 else y - gap - label_height
            texts.append(
                _Text(
                    text,
                    "label",
                    x,
                    top + label_line.ascent,
                    "middle",
                    (x - wide / 2, top, x + wide / 2, top + label_height),
                )
            )
            return
        # Vertical: the positive side is the left of the page, the negative the right.
        middle = y - label_height / 2
        if side > 0:
            texts.append(
                _Text(
                    text,
                    "label",
                    x - gap,
                    middle + label_line.ascent,
                    "end",
                    (x - gap - wide, middle, x - gap, middle + label_height),
                )
            )
        else:
            texts.append(
                _Text(
                    text,
                    "label",
                    x + gap,
                    middle + label_line.ascent,
                    "start",
                    (x + gap, middle, x + gap + wide, middle + label_height),
                )
            )

    for index, layer in enumerate(layers):
        if layer.shape:
            label(layer.shape, centres[index], thick[index] / 2, 1)
    for index, (_, _, span) in enumerate(skips):
        if span.text:
            middle = (branches[index] + ports[index]) / 2
            label(span.text, middle, lane_of[index], -1)
    frames: list[Bounds] = []
    for index, (first, last, span) in enumerate(repeats):
        low, high = frame_of[index]
        frames.append(
            rect(positions[first] - leads[first], positions[last] + along[last] + pad, low, high)
        )
        label(
            repeat_mark(span.times, span.text),
            (positions[first] + positions[last] + along[last]) / 2,
            high,
            1,
        )

    # The key of the types, under the drawing.
    types: list[str] = []
    for part, _, _ in drawn:
        if part.type and part.type not in types:
            types.append(part.type)
    fills = {kind: theme.classes.fill_for(index) for index, kind in enumerate(types)}

    xs: list[float] = []
    ys: list[float] = []
    for _, box in placed:
        xs += [box.x, box.x + box.width]
        ys += [box.y, box.y + box.height]
    for bounds in [*frames, *(text.bounds for text in texts)]:
        xs += [bounds[0], bounds[2]]
        ys += [bounds[1], bounds[3]]
    for _, points in strokes:
        xs += [x for x, _ in points]
        ys += [y for _, y in points]
    dx, dy = -min(xs), -min(ys)
    width = max(xs) + dx
    height = max(ys) + dy
    if width > canvas + 0.01:
        raise FitError(
            f"this network needs {width:.0f} across and the canvas is {canvas:.0f}. Shorten the "
            f"layer names, run it `down`, or give the document more `width`."
        )

    def moved(point: Point) -> Point:
        return (round(point[0] + dx, 3), round(point[1] + dy, 3))

    primitives: list[Primitive] = []
    for left, top, right, bottom in frames:
        primitives.append(
            Rect(FRAME_ROLE, x=left + dx, y=top + dy, width=right - left, height=bottom - top)
        )
    for role, points in strokes:
        primitives.extend(
            edge_primitives(Route("", "", role, tuple(moved(point) for point in points)), theme)
        )
    for layer, box in placed:
        box = box.moved_to(box.x + dx, box.y + dy)
        parts = box_primitives(box, theme, measurer)
        if layer.type:
            parts = tuple(painted(part, *fills[layer.type]) for part in parts)
        primitives.extend(parts)
    for text in texts:
        primitives.append(
            TextRun(
                BLOCK_ROLE,
                x=text.x + dx,
                y=text.y + dy,
                text=text.text,
                level=text.level,
                anchor=text.anchor,
            )
        )
    if len(types) > 1:
        key = tuple(Entry(kind, SWATCH_ROLE, *fills[kind]) for kind in types)
        primitives.extend(primitives_for(key, theme, measurer, 0.0, height, width))
        height += height_of(key, theme, measurer, width)
    return Scene(
        width=width,
        height=height,
        primitives=tuple(primitives),
        title=document.title,
        description=document.description,
        metadata=(("style", "blocks"), ("direction", direction)),
    )


# ---------------------------------------------------------------------------
# The text form
# ---------------------------------------------------------------------------

#: The rule under the table's heading, per charset.
TEXT_RULE: Final = {"unicode": "─", "ascii": "-"}

#: Spaces between two columns of the table.
TEXT_GAP: Final = 3


def neuralnet_text(document: Document, width: int, charset: str) -> str:
    """A network as a model summary: a row per layer, as Keras's `summary()` prints one.

    `neurons`: each layer's name, its neurons (`+ bias` when a bias unit is drawn)
    and its parameters, fully connected to the layer before — weights and biases —
    then the total. `blocks`: each layer's number, name, type and output shape (a
    branch's layers numbered `3a`, `3b1`, `3b2`), then
    a line per skip (`2 → 4`, by row number) and per repeated block (`x6: layers 3-6`).

    Raises:
        FitError: the table is wider than `width`, at the widest row's layer.
        DrawspecError: an `ascii` drawing meets a name with no ASCII spelling.
    """
    layers = document.neural_layers
    blocks = document.neural_style == "blocks"
    names = [
        spelt(layer.text, charset, f"/layers/{index}/text") if layer.text else f"Layer {index + 1}"
        for index, layer in enumerate(layers)
    ]
    rows: list[list[str]]
    where: list[tuple[str, str]]  # each row's pointer and name, for a refusal
    right: set[int]
    if blocks:
        # A set of branches is a row per layer of each tower, numbered `3a`, `3b1`, `3b2`.
        entries: list[tuple[str, NeuralLayer, str]] = []
        for index, layer in enumerate(layers):
            if not layer.branches:
                entries.append((str(index + 1), layer, f"/layers/{index}"))
                continue
            for tower, branch in enumerate(layer.branches):
                for step, part in enumerate(branch):
                    mark = f"{index + 1}{chr(ord('a') + tower)}"
                    if len(branch) > 1:
                        mark += str(step + 1)
                    entries.append((mark, part, f"/layers/{index}/branches/{tower}/layers/{step}"))
        heads = ["#", "Layer"]
        typed = any(part.type for _, part, _ in entries)
        shaped = any(part.shape for _, part, _ in entries)
        if typed:
            heads.append("Type")
        if shaped:
            heads.append("Output shape")
        rows = []
        where = []
        for mark, part, pointer in entries:
            name = spelt(part.text, charset, f"{pointer}/text")
            row = [mark, name]
            if typed:
                row.append(spelt(part.type, charset, f"{pointer}/type"))
            if shaped:
                row.append(spelt(part.shape, charset, f"{pointer}/shape"))
            rows.append(row)
            where.append((pointer, name))
        right = {0}
    else:
        heads = ["Layer", "Neurons", "Parameters"]
        counts = parameters(layers)
        rows = [
            [
                names[index],
                f"{layer.size:,}" + (" + bias" if layer.bias else ""),
                f"{counts[index]:,}" if index else "",
            ]
            for index, layer in enumerate(layers)
        ]
        where = [(f"/layers/{index}", name) for index, name in enumerate(names)]
        right = {1, 2}
    sizes = [max(cells(row[column]) for row in [heads, *rows]) for column in range(len(heads))]
    rule = TEXT_RULE[charset]
    gap = " " * TEXT_GAP

    def drawn(row: Sequence[str]) -> str:
        return gap.join(
            (" " * (sizes[column] - cells(text)) + text)
            if column in right
            else pad(text, sizes[column])
            for column, text in enumerate(row)
        )

    lines: list[Drawn] = [Drawn(drawn(heads), "/layers", "the heading")]
    lines.append(Drawn(rule * max(cells(drawn(row).rstrip()) for row in [heads, *rows])))
    for row, (pointer, name) in zip(rows, where, strict=True):
        lines.append(Drawn(drawn(row), pointer, f"the row of {name!r}"))
    if not blocks and len(layers) > 1:
        total = sum(parameters(layers))
        lines.append(Drawn(""))
        lines.append(Drawn(f"{total:,} parameters (weights and biases)."))
    if blocks:
        arrow = "→" if charset == "unicode" else "->"
        ids = {layer.id: index for index, layer in enumerate(layers) if layer.id}
        extra: list[Drawn] = []
        for index, span in enumerate(document.neural_skips):
            words = f"skip: {ids[span.source] + 1} {arrow} {ids[span.target] + 1}"
            if span.text:
                words += f" ({spelt(span.text, charset, f'/skips/{index}/text')})"
            extra.append(Drawn(words, f"/skips/{index}", "the skip"))
        for index, span in enumerate(document.neural_repeats):
            mark = spelt(repeat_mark(span.times, span.text), charset, f"/repeats/{index}/text")
            first, last = ids[span.source] + 1, ids[span.target] + 1
            run = f"layer {first}" if first == last else f"layers {first}-{last}"
            extra.append(Drawn(f"{mark}: {run}", f"/repeats/{index}", "the repeat"))
        if extra:
            lines.append(Drawn(""))
            lines.extend(extra)
    widest(lines, width)
    return finished([line.text for line in lines] + caption_lines(document.caption, width, charset))


__all__ = [
    "BIAS",
    "Neuron",
    "neuralnet_scene",
    "neuralnet_text",
    "neurons_drawing",
    "parameters",
    "repeat_mark",
    "shown",
]

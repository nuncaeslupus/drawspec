"""The `railroad` kind: a grammar's rules as syntax (railroad) diagrams.

A layout family of its own. Each rule is a track from an entry bar on the left
to an exit bar on the right, and the input is the expression the track draws —
there are no coordinates to write. What the track does is derived from the
expression alone:

* **A box per word.** A `terminal` is literal text, in a rounded box and in
  monospace; a `rule` names another rule, in a square box; a `special` describes
  a set in words, in a dashed box. A `comment` is words over the line, no box.
  Shape says which is which, so greyscale and a reader who cannot see colour
  keep the distinction — the convention since Wirth's Pascal manual.
* **A `seq`** runs left to right. **A `choice`** stacks its alternatives under
  the first, which stays on the main line, and rejoins them. **An `optional`**
  keeps its item on the line and draws a bypass over it. **A `repeat`** keeps its
  item on the line and loops back under it, through its separator when it has
  one; `min: 0` adds the bypass too.
* **Every turn is a quarter circle of one radius**, so a branch leaves and
  rejoins the line tangentially, as a train would, and no two turns can collide:
  each construct reserves room for its own.
* **A long rule wraps.** When a rule's top-level `seq` is wider than the canvas
  it is broken between items onto further lines, and a return track runs back
  under each line to the start of the next, as SQLite's diagrams do. An item that
  is wider than the canvas on a line of its own is refused at its pointer, with
  the advice SQLite's documentation follows: make it a rule of its own.

The layout is computed once, on abstract lengths (`_Metrics`), and drawn twice:
on points with arcs for the SVG, and on character cells with box-drawing corners
for `render --format text`. Both read the same tree the same way, so the text
form is the same drawing at a coarser grain.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final, Protocol

from drawspec.charts import FURNITURE_ROLE
from drawspec.errors import FitError
from drawspec.scene import Path, Polygon, Primitive, Rect, Scene, TextLine, TextSpan
from drawspec.schema import Document, RailroadItem
from drawspec.text.measure import TextMeasurer
from drawspec.textgrid import (
    Grid,
    caption_lines,
    cells,
    finished,
    spelt,
    too_wide,
)
from drawspec.theme import Theme

#: The node role each box is drawn in: a terminal rounded (a pill), a rule square,
#: a special dashed. Three shapes, so the three read apart in greyscale.
BOX_ROLES: Final = {"terminal": "start", "rule": "step", "special": "group"}

#: The font each box's words are set in: a terminal is literal text, so monospace.
BOX_FONTS: Final = {"terminal": "mono", "rule": "sans", "special": "sans", "comment": "sans"}

#: The edge role the track is drawn in: an ordinary solid line. Its arrowheads, on
#: the lines that run backwards, are drawn by this module as filled triangles.
TRACK_ROLE: Final = "flow"

#: Lengths in units, a unit being the body size over eleven, so a fitted (smaller)
#: type scale draws a proportionally smaller track.
RADIUS: Final = 8.0
"""The radius of every turn."""

GAP: Final = 8.0
"""The least space between a box and a line or a box running past it."""

BRANCH_GAP: Final = 10.0
"""The least space between two alternatives of a choice, one over the other."""

SPACE: Final = 10.0
"""The length of track between two items in a sequence."""

PAD_X: Final = 7.0
"""The space beside a box's words."""

PAD_Y: Final = 4.0
"""The space over and under a box's words."""

COMMENT_GAP: Final = 4.0
"""The track's break either side of a comment's words."""

RULE_GAP: Final = 16.0
"""The space between one rule's track and the next rule's name."""

NAME_GAP: Final = 4.0
"""The space between a rule's name and the top of its track."""

ARROW: Final = 7.0
"""An arrowhead's length, on a line the track runs backwards along."""

#: The most degrees one straight piece of a turn may span.
ARC_STEPS: Final = 6


@dataclass(frozen=True)
class _Metrics:
    """The lengths one drawing is laid out with, in its own units (points or cells)."""

    radius: float
    line_gap: float
    """Between a box and a line that runs past it: a bypass, a loop, a return."""

    box_gap: float
    """Between two alternatives of a choice, stacked."""

    space: float
    arrow: float
    """The room an arrowhead takes on a backward line; 0 draws none."""

    size: Callable[[RailroadItem], tuple[float, float, float]]
    """A box's or a comment's width, and how far it reaches above and below the line."""

    tail: float = 0.0
    """The track after a line's last item, to its exit or its turn down; 0 is a radius."""

    loop_pad: float = 0.0
    """Room beside a loop's item, so the loop's turns stand clear of its sides."""

    snap: Callable[[float], float] = float
    """How a centred position is rounded: not at all on points, down to a cell on text."""


@dataclass(frozen=True)
class _Size:
    width: float
    up: float
    down: float


class _Sink(Protocol):
    """What a drawing is made of; the SVG and the text forms each implement it."""

    def box(self, item: RailroadItem, x: float, y: float, width: float) -> None: ...

    def path(self, points: list[tuple[float, float]]) -> None: ...

    def arrow(self, x: float, y: float) -> None:
        """An arrowhead pointing left, its tip at (x, y)."""


class _Layout:
    """Sizes and draws items with one set of metrics."""

    def __init__(self, metrics: _Metrics) -> None:
        self.m = metrics
        # Keyed by identity, holding the item too so its id is never reused.
        self._sizes: dict[int, tuple[RailroadItem, _Size]] = {}

    # -- sizes -------------------------------------------------------------------

    def size(self, item: RailroadItem) -> _Size:
        key = id(item)
        if key not in self._sizes:
            self._sizes[key] = (item, self._measure(item))
        return self._sizes[key][1]

    def _branches(self, item: RailroadItem) -> list[float]:
        """Each alternative's line, as a drop below the choice's main line."""
        r, gap = self.m.radius, self.m.box_gap
        sizes = [self.size(child) for child in item.items]
        drops = [0.0]
        for previous, current in itertools.pairwise(sizes):
            drop = drops[-1] + previous.down + gap + current.up
            drops.append(max(drop, drops[-1] + 2 * r) if len(drops) == 1 else drop)
        return drops

    def _rise(self, inner: _Size) -> float:
        """How far a bypass runs above the line, over `inner`."""
        return max(inner.up + self.m.line_gap, 2 * self.m.radius)

    def _loop(self, item: RailroadItem) -> float:
        """How far a repeat's loop runs below the line."""
        inner = self.size(item.items[0])
        up = self.size(item.separator).up if item.separator else 0.0
        return max(inner.down + self.m.line_gap + up, 2 * self.m.radius)

    def _measure(self, item: RailroadItem) -> _Size:
        r = self.m.radius
        if item.shape in ("terminal", "rule", "special", "comment"):
            width, up, down = self.m.size(item)
            return _Size(width, up, down)
        if item.shape == "seq":
            sizes = [self.size(child) for child in item.items]
            return _Size(
                sum(size.width for size in sizes) + self.m.space * (len(sizes) - 1),
                max(size.up for size in sizes),
                max(size.down for size in sizes),
            )
        if item.shape == "choice":
            sizes = [self.size(child) for child in item.items]
            drops = self._branches(item)
            return _Size(
                max(size.width for size in sizes) + 4 * r,
                sizes[0].up,
                drops[-1] + sizes[-1].down,
            )
        if item.shape == "optional":
            inner = self.size(item.items[0])
            return _Size(inner.width + 4 * r, self._rise(inner), inner.down)
        # repeat
        inner = self.size(item.items[0])
        if item.separator is not None:
            separator = self.size(item.separator)
            back = separator.width
            bottom = self._loop(item) + separator.down
        else:
            back = self.m.arrow + 2 * r
            bottom = self._loop(item)
        loop = _Size(max(inner.width, back) + 2 * (r + self.m.loop_pad), inner.up, bottom)
        if item.min == 0:
            return _Size(loop.width + 4 * r, self._rise(loop), loop.down)
        return loop

    # -- drawing -----------------------------------------------------------------

    def draw(self, item: RailroadItem, x: float, y: float, sink: _Sink) -> None:
        """Draw `item` with its main line at `y`, from `x` to `x` plus its width."""
        r = self.m.radius
        size = self.size(item)
        if item.shape in ("terminal", "rule", "special", "comment"):
            sink.box(item, x, y, size.width)
            return
        if item.shape == "seq":
            cursor = x
            for index, child in enumerate(item.items):
                if index:
                    sink.path([(cursor, y), (cursor + self.m.space, y)])
                    cursor += self.m.space
                self.draw(child, cursor, y, sink)
                cursor += self.size(child).width
            return
        if item.shape == "choice":
            right = x + size.width
            for child, drop in zip(item.items, self._branches(item), strict=True):
                width = self.size(child).width
                if drop == 0:
                    sink.path([(x, y), (x + 2 * r, y)])
                    sink.path([(x + 2 * r + width, y), (right, y)])
                else:
                    low = y + drop
                    sink.path([(x, y), (x + r, y), (x + r, low), (x + 2 * r, low)])
                    sink.path(
                        [(x + 2 * r + width, low), (right - r, low), (right - r, y), (right, y)]
                    )
                self.draw(child, x + 2 * r, y + drop, sink)
            return
        if item.shape == "optional" or (item.shape == "repeat" and item.min == 0):
            inner = (
                item.items[0]
                if item.shape == "optional"
                else RailroadItem(
                    "repeat", items=item.items, separator=item.separator, pointer=item.pointer
                )
            )
            inner_size = self.size(inner)
            right = x + size.width
            top = y - self._rise(inner_size)
            sink.path(
                [(x, y), (x + r, y), (x + r, top), (right - r, top), (right - r, y), (right, y)]
            )
            sink.path([(x, y), (x + 2 * r, y)])
            sink.path([(x + 2 * r + inner_size.width, y), (right, y)])
            self.draw(inner, x + 2 * r, y, sink)
            return
        # repeat, one or more
        right = x + size.width
        child = item.items[0]
        width = self.size(child).width
        start = x + self.m.snap((size.width - width) / 2)
        sink.path([(x, y), (start, y)])
        self.draw(child, start, y, sink)
        sink.path([(start + width, y), (right, y)])
        low = y + self._loop(item)
        if item.separator is not None:
            back = self.size(item.separator).width
            begin = x + self.m.snap((size.width - back) / 2)
            sink.path([(right - r, y), (right, y), (right, low), (begin + back, low)])
            self.draw(item.separator, begin, low, sink)
            sink.path([(begin, low), (x, low), (x, y), (x + r, y)])
        else:
            sink.path([(right - r, y), (right, y), (right, low), (x, low), (x, y), (x + r, y)])
            if self.m.arrow:
                sink.arrow(x + self.m.snap((size.width - self.m.arrow) / 2), low)


def _pieces(item: RailroadItem) -> list[RailroadItem]:
    """A rule's top-level sequence, flattened: the places a long rule may wrap."""
    if item.shape != "seq":
        return [item]
    return [piece for child in item.items for piece in _pieces(child)]


@dataclass(frozen=True)
class _Row:
    items: tuple[RailroadItem, ...]
    width: float
    up: float
    down: float


def _rows(
    layout: _Layout, item: RailroadItem, room: float, refuse: Callable[[RailroadItem, float], None]
) -> list[_Row]:
    """A rule's pieces packed into lines no wider than `room`, greedily, in order."""
    space = layout.m.space
    rows: list[list[RailroadItem]] = [[]]
    used = 0.0
    for piece in _pieces(item):
        width = layout.size(piece).width
        if width > room:
            refuse(piece, width)
        if rows[-1] and used + space + width > room:
            rows.append([])
            used = 0.0
        used += (space if rows[-1] else 0.0) + width
        rows[-1].append(piece)
    out: list[_Row] = []
    for pieces in rows:
        sizes = [layout.size(piece) for piece in pieces]
        out.append(
            _Row(
                tuple(pieces),
                sum(size.width for size in sizes) + space * (len(sizes) - 1),
                max(size.up for size in sizes),
                max(size.down for size in sizes),
            )
        )
    return out


@dataclass
class _Track:
    """One rule's track, placed: the line each row runs on and where it ends."""

    rows: list[_Row]
    ys: list[float] = field(default_factory=list)
    returns: list[float] = field(default_factory=list)
    bottom: float = 0.0


def _place(layout: _Layout, rows: list[_Row], top: float) -> _Track:
    """The rows one under another from `top`, a return track between each two."""
    r, gap = layout.m.radius, layout.m.line_gap
    track = _Track(rows)
    y = top + rows[0].up
    for index, row in enumerate(rows):
        track.ys.append(y)
        if index + 1 < len(rows):
            back = y + max(row.down + gap, 2 * r)
            track.returns.append(back)
            y = back + max(gap + rows[index + 1].up, 2 * r)
    track.bottom = track.ys[-1] + rows[-1].down
    return track


def _draw_track(layout: _Layout, track: _Track, start: float, sink: _Sink) -> float:
    """Draw a placed track from its entry at `start`; the exit's x."""
    r = layout.m.radius
    tail = layout.m.tail or r
    left = start + 2 * r
    exit_x = left
    for index, (row, y) in enumerate(zip(track.rows, track.ys, strict=True)):
        if index == 0:
            sink.path([(start, y), (left, y)])
        cursor = left
        for number, piece in enumerate(row.items):
            if number:
                sink.path([(cursor, y), (cursor + layout.m.space, y)])
                cursor += layout.m.space
            layout.draw(piece, cursor, y, sink)
            cursor += layout.size(piece).width
        end = left + row.width
        if index + 1 < len(track.rows):
            back = track.returns[index]
            following = track.ys[index + 1]
            sink.path(
                [
                    (end, y),
                    (end + tail, y),
                    (end + tail, back),
                    (left - r, back),
                    (left - r, following),
                    (left, following),
                ]
            )
            if layout.m.arrow:
                sink.arrow(layout.m.snap((left + end - layout.m.arrow) / 2), back)
        else:
            sink.path([(end, y), (end + tail, y)])
            exit_x = end + tail
    return exit_x


# ---------------------------------------------------------------------------
# SVG
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RailroadDrawing:
    """The finished geometry, in final coordinates, for tests and the scene."""

    scene: Scene
    boxes: tuple[tuple[str, str, tuple[float, float, float, float]], ...] = ()
    """Each box drawn: its shape, its words, and its left, top, right, bottom."""

    rows: tuple[int, ...] = ()
    """How many lines each rule's track was wrapped onto."""

    tracks: tuple[tuple[tuple[float, float], ...], ...] = ()
    """Every stretch of track, as the points drawn (turns already rounded)."""


def _rounded(points: list[tuple[float, float]], radius: float) -> tuple[tuple[float, float], ...]:
    """An orthogonal polyline with every corner turned on a quarter circle."""
    if len(points) < 3:
        return tuple(points)
    out = [points[0]]
    for before, corner, after in zip(points, points[1:], points[2:], strict=False):
        din = (corner[0] - before[0], corner[1] - before[1])
        dout = (after[0] - corner[0], after[1] - corner[1])
        lin, lout = math.hypot(*din), math.hypot(*dout)
        if lin == 0 or lout == 0 or abs(din[0] * dout[1] - din[1] * dout[0]) < 1e-9:
            out.append(corner)
            continue
        ui = (din[0] / lin, din[1] / lin)
        uo = (dout[0] / lout, dout[1] / lout)
        turn = min(radius, lin, lout)
        a = (corner[0] - ui[0] * turn, corner[1] - ui[1] * turn)
        centre = (a[0] + uo[0] * turn, a[1] + uo[1] * turn)
        for step in range(ARC_STEPS + 1):
            t = step / ARC_STEPS * math.pi / 2
            # From `a` (on the incoming line) to the corner's exit, round `centre`.
            out.append(
                (
                    centre[0] - uo[0] * turn * math.cos(t) + ui[0] * turn * math.sin(t),
                    centre[1] - uo[1] * turn * math.cos(t) + ui[1] * turn * math.sin(t),
                )
            )
    out.append(points[-1])
    deduped = [out[0]]
    for point in out[1:]:
        if math.dist(point, deduped[-1]) > 1e-6:
            deduped.append(point)
    return tuple(deduped)


class _SvgSink:
    def __init__(self, theme: Theme, measurer: TextMeasurer, unit: float, radius: float) -> None:
        self.theme = theme
        self.measurer = measurer
        self.unit = unit
        self.radius = radius
        self.lines: list[Primitive] = []
        self.shapes: list[Primitive] = []
        self.texts: list[Primitive] = []
        self.boxes: list[tuple[str, str, tuple[float, float, float, float]]] = []
        self.tracks: list[tuple[tuple[float, float], ...]] = []

    def extents(self, item: RailroadItem) -> tuple[float, float, float]:
        level = "label" if item.shape == "comment" else "body"
        size = self.theme.scale[level]
        found = self.measurer.measure(item.text, BOX_FONTS[item.shape], size)
        return found.width, found.ascent, found.descent

    def size(self, item: RailroadItem) -> tuple[float, float, float]:
        width, ascent, descent = self.extents(item)
        u = self.unit
        if item.shape == "comment":
            # On the line itself, the track stopping short of the words either side.
            return width + 2 * COMMENT_GAP * u, (ascent + descent) / 2, (ascent + descent) / 2
        height = ascent + descent + 2 * PAD_Y * u
        extra = height / 3 if item.shape == "terminal" else 0.0
        return width + 2 * PAD_X * u + 2 * extra, height / 2, height / 2

    def box(self, item: RailroadItem, x: float, y: float, width: float) -> None:
        _text_width, ascent, descent = self.extents(item)
        level = "label" if item.shape == "comment" else "body"
        if item.shape == "comment":
            baseline = y + (ascent - descent) / 2
            self.texts.append(self._words(item, x + width / 2, baseline, level))
            self.boxes.append(
                (item.shape, item.text, (x, baseline - ascent, x + width, baseline + descent))
            )
            return
        _, up, down = self.size(item)
        self.shapes.append(
            Rect(BOX_ROLES[item.shape], x=x, y=y - up, width=width, height=up + down)
        )
        baseline = y + (ascent - descent) / 2
        self.texts.append(self._words(item, x + width / 2, baseline, level))
        self.boxes.append((item.shape, item.text, (x, y - up, x + width, y + down)))

    def _words(self, item: RailroadItem, x: float, baseline: float, level: str) -> TextLine:
        return TextLine(
            FURNITURE_ROLE,
            x=x,
            y=baseline,
            spans=(TextSpan(text=item.text, font=BOX_FONTS[item.shape]),),
            level=level,
            anchor="middle",
        )

    def path(self, points: list[tuple[float, float]]) -> None:
        if len(points) < 2 or all(math.dist(points[0], point) < 1e-9 for point in points):
            return
        drawn = _rounded(points, self.radius)
        self.tracks.append(drawn)
        self.lines.append(Path(TRACK_ROLE, points=drawn))

    def arrow(self, x: float, y: float) -> None:
        length = ARROW * self.unit
        half = length * 0.45
        self.shapes.append(
            Polygon(
                TRACK_ROLE,
                points=((x, y), (x + length, y - half), (x + length, y + half)),
            )
        )

    def bar(self, x: float, y: float) -> None:
        reach = self.radius * 0.9
        self.lines.append(Path(TRACK_ROLE, points=((x, y - reach), (x, y + reach))))


def railroad_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Draw `document` as railroad diagrams, one rule under another."""
    return railroad_drawing(document, theme, measurer).scene


def railroad_drawing(document: Document, theme: Theme, measurer: TextMeasurer) -> RailroadDrawing:
    """Lay every rule out, wrapping a long one onto further lines.

    Raises:
        FitError: an item is wider than the canvas on a line of its own.
    """
    width = document.width if document.width else theme.canvas.width
    unit = theme.scale["body"] / 11
    radius = RADIUS * unit
    sink = _SvgSink(theme, measurer, unit, radius)
    metrics = _Metrics(
        radius=radius,
        line_gap=GAP * unit,
        box_gap=BRANCH_GAP * unit,
        space=SPACE * unit,
        arrow=ARROW * unit,
        size=sink.size,
        loop_pad=radius,
    )
    layout = _Layout(metrics)
    heading = theme.scale["heading"]
    name_font = theme.font.default
    # The track's entry bar sits half a stroke in, so its ink is inside the canvas.
    start = theme.edge.stroke_width
    room = width - start - 3 * radius - theme.edge.stroke_width

    def refuse(piece: RailroadItem, piece_width: float) -> None:
        raise FitError(
            f"{piece.pointer}: this item is {piece_width:.0f} units wide on a line of its own, "
            f"and a {width:.0f}-wide canvas leaves {room:.0f} for one. Make it a rule of its "
            f'own and refer to it with {{"rule": name}}, shorten its words, or widen the '
            f"diagram."
        )

    top = 0.0
    rows_per_rule: list[int] = []
    right = 0.0
    for rule in document.railroad_rules:
        name = measurer.measure(rule.name, name_font, heading, "bold")
        if name.width > width:
            raise FitError(
                f"{rule.pointer}/name: the rule's name is {name.width:.0f} units wide and the "
                f"canvas {width:.0f}. Shorten it, or widen the diagram."
            )
        sink.texts.append(
            TextLine(
                FURNITURE_ROLE,
                x=0.0,
                y=top + name.ascent,
                spans=(TextSpan(text=rule.name, font=name_font, weight="bold"),),
                level="heading",
                anchor="start",
            )
        )
        right = max(right, name.width)
        rows = _rows(layout, rule.expr, room, refuse)
        rows_per_rule.append(len(rows))
        track = _place(layout, rows, top + name.height + NAME_GAP * unit + radius * 0.9)
        sink.bar(start, track.ys[0])
        exit_x = _draw_track(layout, track, start, sink)
        sink.bar(exit_x, track.ys[-1])
        widest = max((start + 2 * radius + row.width + radius for row in rows), default=exit_x)
        right = max(right, widest + theme.edge.stroke_width)
        bottom = max(track.bottom, track.ys[-1] + radius * 0.9)
        top = bottom + RULE_GAP * unit

    height = top - RULE_GAP * unit
    scene = Scene(
        width=min(max(right, 1.0), width),
        height=height,
        primitives=(*sink.lines, *sink.shapes, *sink.texts),
        title=document.title,
        description=document.description,
    )
    return RailroadDrawing(
        scene=scene,
        boxes=tuple(sink.boxes),
        rows=tuple(rows_per_rule),
        tracks=tuple(sink.tracks),
    )


# ---------------------------------------------------------------------------
# Text: the same track on character cells
# ---------------------------------------------------------------------------

#: A box's sides per shape and charset: top-left, top, top-right, the side the
#: track enters, the side it leaves, bottom-left, bottom, bottom-right.
TEXT_BOXES: Final = {
    "unicode": {
        "terminal": ("╭", "─", "╮", "┤", "├", "╰", "─", "╯"),
        "rule": ("┌", "─", "┐", "┤", "├", "└", "─", "┘"),
        "special": ("┌", "┄", "┐", "┤", "├", "└", "┄", "┘"),
    },
    "ascii": {
        "terminal": (".", "-", ".", "(", ")", "'", "-", "'"),
        "rule": ("+", "-", "+", "|", "|", "+", "-", "+"),
        "special": ("+", ".", "+", ":", ":", "+", ".", "+"),
    },
}

#: The entry and exit bars, and an arrowhead pointing back along a loop.
TEXT_ENDS: Final = {"unicode": ("├", "┤", "◀"), "ascii": ("|", "|", "<")}


class _TextSink:
    def __init__(self, charset: str) -> None:
        self.charset = charset
        self.grid = Grid(charset)
        self.words: dict[int, str] = {}

    def label(self, item: RailroadItem) -> str:
        key = id(item)
        if key not in self.words:
            self.words[key] = spelt(item.text, self.charset, f"{item.pointer}/{item.shape}")
        return self.words[key]

    def size(self, item: RailroadItem) -> tuple[float, float, float]:
        width = cells(self.label(item))
        if item.shape == "comment":
            # A cell of track, a space, the words, a space: the next line starts after.
            return width + 3, 0, 0
        # The box and a cell of track either side of it, so a turn never abuts a side.
        return width + 6, 1, 1

    def box(self, item: RailroadItem, x: float, y: float, width: float) -> None:
        column, row, span = round(x), round(y), round(width)
        words = self.label(item)
        if item.shape == "comment":
            self.grid.text(row, column + 2, words)
            return
        tl, top, tr, enter, leave, bl, bottom, br = TEXT_BOXES[self.charset][item.shape]
        inner = span - 4
        self.grid.horizontal(row, column, column + 1)
        self.grid.horizontal(row, column + span - 2, column + span - 1)
        self.grid.text(row - 1, column + 1, tl + top * inner + tr)
        self.grid.text(row, column + 1, enter + " " + words + " " + leave)
        self.grid.text(row + 1, column + 1, bl + bottom * inner + br)

    def path(self, points: list[tuple[float, float]]) -> None:
        cellwise = [(round(x), round(y)) for x, y in points]
        for (x0, y0), (x1, y1) in itertools.pairwise(cellwise):
            if y0 == y1 and x0 != x1:
                self.grid.horizontal(y0, x0, x1)
            elif x0 == x1 and y0 != y1:
                self.grid.vertical(x0, y0, y1)

    def arrow(self, x: float, y: float) -> None:
        self.grid.text(round(y), round(x), TEXT_ENDS[self.charset][2])


def railroad_text(document: Document, width: int, charset: str) -> str:
    """A `railroad` grammar as plain text: each rule's name, then its track.

    The SVG's layout on cells: a box is three rows, the track running through its
    middle; a turn is a corner; a choice's alternatives, a loop and a bypass take
    the same places they take in the SVG. A rule wider than `width` wraps between
    the items of its top-level sequence, a return line leading back under it.

    Raises:
        FitError: a rule's name, or one item on a line of its own, is wider than
            `width`, at its pointer and with the width it needs.
    """
    sink = _TextSink(charset)
    metrics = _Metrics(
        radius=1,
        line_gap=1,
        box_gap=2,
        space=1,
        arrow=1,
        size=sink.size,
        tail=2,
        snap=math.floor,
    )
    layout = _Layout(metrics)
    start = 0
    # The rows' items run from column 2 (after the entry bar and a turn's room),
    # leaving two cells of track after the last and a column for the turn or exit.
    room = width - 2 - 3

    # Refuse at whatever needs the most width, so the width named is enough.
    needed: list[tuple[int, str, str]] = []
    for rule in document.railroad_rules:
        name = spelt(rule.name, charset, f"{rule.pointer}/name")
        needed.append((cells(name), f"{rule.pointer}/name", f"the rule name {name!r}"))
        for piece in _pieces(rule.expr):
            needed.append(
                (
                    round(layout.size(piece).width) + 5,
                    piece.pointer,
                    "this item, on a line of its own,",
                )
            )
    most, pointer, what = max(needed, key=lambda entry: entry[0])
    if most > width:
        raise too_wide(pointer, what, most, width)

    def refuse(piece: RailroadItem, piece_width: float) -> None:  # pragma: no cover - checked above
        raise too_wide(piece.pointer, "this item", round(piece_width) + 5, width)

    lines: list[str] = []
    for index, rule in enumerate(document.railroad_rules):
        sink.grid = Grid(charset)
        rows = _rows(layout, rule.expr, room, refuse)
        track = _place(layout, rows, 0)
        ends = TEXT_ENDS[charset]
        exit_x = _draw_track(layout, track, start, sink)
        sink.grid.text(round(track.ys[0]), start, ends[0])
        sink.grid.text(round(track.ys[-1]), round(exit_x), ends[1])
        if index:
            lines.append("")
        lines.append(spelt(rule.name, charset, f"{rule.pointer}/name"))
        lines.extend(sink.grid.lines())
    return finished(lines + caption_lines(document.caption, width, charset))


__all__ = ["RailroadDrawing", "railroad_drawing", "railroad_scene", "railroad_text"]

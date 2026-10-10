"""The `argument` kind: a claim, the reasons for it, and the objections to them.

An argument map. Its claim is fixed — one contention at the top; every box below
bears **for** or **against** the box above it — and a `tree` loses both halves of
it: the stance, and co-premises, two reasons that support only together.

**The claim** is at the top, in a pill in the `terminal` role, its words bold.
Points hang below it by `on`, as a downward tidy tree, siblings in the order
written; an argument is read from the contention down, so the direction is fixed.

**Stance on two channels, so greyscale holds.** Each point carries a tag in its
top margin, at its left, in the label type — the theme's words, `because` and
`but` by default, so the map reads aloud down any chain (*claim, because …, but
…, but …*) — and an `against` box is filled with the theme's hatch, a `for` box
is plain. A rebuttal is an `against` on an `against`: no third stance.

**Co-premises** sit side by side under one bracket — a line joining their tops —
and one connector runs from the bracket's middle to the box they support. An
independent reason has its own connector. So the number of arrows into a box is
the number of separate reasons bearing on it.

**Connectors** run up from a point (or a bracket) and arrive square on the
bottom of the box they bear on, each at its own port, with the arrow head at the
box. A connector that has to move across does so on its own lane between the two
rows, the outermost highest, so no two cross. `emphasis` (the decisive point) is
drawn heavy; `note` — evidence or a source, not a reason — is drawn in the note
type, and joined by a dashed line.

When the tree is wider than the canvas, the points wrap narrower until it fits;
when no width works, `FitError` names the widest row.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from drawspec.errors import FitError
from drawspec.routing import end_marker
from drawspec.scene import Path, Primitive, Rect, Scene, TextLine, TextRun, TextSpan, moved
from drawspec.schema import ArgumentPoint, Document
from drawspec.text.measure import TextMeasurer
from drawspec.text.wrap import TextBlock, wrap
from drawspec.theme import Theme

#: The most of the canvas the claim, and one point, may take before wrapping.
CLAIM_SHARE: Final = 0.6
POINT_SHARE: Final = 0.3

#: The narrowest a point may be wrapped to, as a share of the canvas, before the
#: map is refused as too wide; and each narrower attempt's share of the last.
POINT_MIN_SHARE: Final = 0.12
POINT_STEP: Final = 0.92

#: Lengths in units, a unit being the body size over eleven.
UNIT_GAP: Final = 14.0
"""Across: between two separate reasons (or groups) under one box."""
MEMBER_GAP: Final = 8.0
"""Across: between two co-premises under one bracket."""
ROW_GAP: Final = 26.0
"""Down: the least room between one row of boxes and the next."""
LANE: Final = 14.0
"""Down: between two lanes of connectors crossing between rows."""
BRACKET: Final = 10.0
"""Down: from a bracket to the tops of the co-premises it joins."""
PORT: Final = 12.0
"""Across: the least distance between two connectors arriving at one box."""
INSET: Final = 10.0
"""Across: how far in from a box's corner a connector may arrive."""
TAG_GAP: Final = 3.0
"""Down: from a tag to the words under it."""

#: The roles a box is outlined in, by the point's role. A `note` has no outline.
BOX_ROLES: Final = {"step": "step", "emphasis": "emphasis", "note": "note"}
CLAIM_ROLE: Final = "terminal"

#: The edge roles a connector is drawn in, by the point's role.
CONNECTOR_ROLES: Final = {"step": "flow", "emphasis": "strong", "note": "weak"}

#: A rectangle: left, top, right, bottom.
type Rect4 = tuple[float, float, float, float]


@dataclass(frozen=True)
class PointDrawn:
    """Where one point landed, in final coordinates."""

    id: str
    stance: str
    role: str
    box: Rect4
    tag: Rect4
    """The tag's measured extent."""

    words: Rect4
    fill: str
    """The fill pattern the box is drawn with: the theme's hatch for `against`."""

    depth: int


@dataclass(frozen=True)
class ConnectorDrawn:
    """One connector: from a point or a bracket up to the box it bears on."""

    members: tuple[str, ...]
    """The point, or the co-premises its bracket joins."""

    to: str
    points: tuple[tuple[float, float], ...]
    role: str


@dataclass(frozen=True)
class ArgumentDrawing:
    """The finished geometry, in final coordinates, for tests and the scene."""

    scene: Scene
    claim: Rect4 = (0.0, 0.0, 0.0, 0.0)
    points: tuple[PointDrawn, ...] = field(default_factory=tuple)
    connectors: tuple[ConnectorDrawn, ...] = field(default_factory=tuple)
    brackets: tuple[tuple[tuple[str, ...], Rect4], ...] = ()
    """Each co-premise group and its bracket's extent."""


@dataclass
class _Box:
    """One box, sized: the claim or a point."""

    id: str
    point: ArgumentPoint | None
    depth: int
    tag: TextBlock | None
    block: TextBlock
    width: float
    height: float
    units: list[_Unit] = field(default_factory=list)
    span: float = 0.0
    """The width this box and everything under it take."""

    x: float = 0.0
    y: float = 0.0


@dataclass
class _Unit:
    """What bears on one box with one connector: a point, or co-premises."""

    members: list[_Box]
    span: float = 0.0


def argument_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Draw `document` as an argument map."""
    return argument_drawing(document, theme, measurer).scene


def argument_drawing(document: Document, theme: Theme, measurer: TextMeasurer) -> ArgumentDrawing:
    """Lay the map out, wrapping points narrower until it fits the canvas.

    Raises:
        FitError: no width for the points fits the canvas, or a word is wider
            than the narrowest width a point may have.
    """
    width = theme.canvas.width
    floor = width * POINT_MIN_SHARE
    cap = width * POINT_SHARE
    widest: tuple[int, float] = (0, 0.0)
    while True:
        try:
            root = _tree(document, theme, measurer, cap)
        except FitError:
            break
        if root.span <= width + 1e-6:
            return _drawing(document, root, theme, measurer)
        widest = _widest_row(root)
        if cap <= floor:
            break
        cap = max(floor, cap * POINT_STEP)
    row, needed = widest
    raise FitError(
        f"the argument map does not fit a width of {width:.0f}, even with every point "
        f"wrapped to {floor:.0f}: row {row} (the points {row} below the claim) needs "
        f"{needed:.0f}. Shorten those points, split the map — an overview with the top-level "
        f"reasons and objections, and a map per contested reason — or give the diagram "
        f"more width."
    )


def _tree(document: Document, theme: Theme, measurer: TextMeasurer, cap: float) -> _Box:
    """Every box sized and grouped under the box it bears on; spans measured."""
    unit = theme.scale["body"] / 11
    claim = _sized(
        "claim", None, 0, document.claim, theme, measurer, theme.canvas.width * CLAIM_SHARE
    )
    boxes: dict[str, _Box] = {"claim": claim}
    depth: dict[str, int] = {"claim": 0}

    def depth_of(point: ArgumentPoint) -> int:
        if point.id not in depth:
            parent = (
                next(p for p in document.points if p.id == point.on)
                if point.on != "claim"
                else None
            )
            depth[point.id] = 1 if parent is None else depth_of(parent) + 1
        return depth[point.id]

    for point in document.points:
        boxes[point.id] = _sized(point.id, point, depth_of(point), point.text, theme, measurer, cap)
    groups = _groups(document.points)
    placed: set[str] = set()
    for point in document.points:
        if point.id in placed:
            continue
        members = [boxes[member] for member in groups.get(point.id, (point.id,))]
        placed.update(member.id for member in members)
        boxes[point.on].units.append(_Unit(members=members))
    _measure(claim, unit)
    return claim


def _groups(points: tuple[ArgumentPoint, ...]) -> dict[str, tuple[str, ...]]:
    """Each point in a co-premise group, mapped to the group in the order written."""
    parent = {point.id: point.id for point in points}

    def find(name: str) -> str:
        while parent[name] != name:
            parent[name] = parent[parent[name]]
            name = parent[name]
        return name

    for point in points:
        for other in point.with_:
            if other in parent:
                parent[find(point.id)] = find(other)
    members: dict[str, list[str]] = {}
    for point in points:
        members.setdefault(find(point.id), []).append(point.id)
    return {
        point.id: tuple(members[find(point.id)])
        for point in points
        if len(members[find(point.id)]) > 1
    }


def _measure(box: _Box, unit: float) -> None:
    for each in box.units:
        for member in each.members:
            _measure(member, unit)
        each.span = sum(member.span for member in each.members) + MEMBER_GAP * unit * (
            len(each.members) - 1
        )
    under = sum(each.span for each in box.units) + UNIT_GAP * unit * max(len(box.units) - 1, 0)
    box.span = max(box.width, under)


def _widest_row(root: _Box) -> tuple[int, float]:
    """The row whose boxes, side by side, need the most width — what to name."""
    rows: dict[int, float] = {}

    def walk(box: _Box) -> None:
        rows[box.depth] = rows.get(box.depth, 0.0) + box.width
        for each in box.units:
            for member in each.members:
                walk(member)

    walk(root)
    return max(rows.items(), key=lambda item: item[1])


def _sized(
    name: str,
    point: ArgumentPoint | None,
    depth: int,
    text: str,
    theme: Theme,
    measurer: TextMeasurer,
    cap: float,
) -> _Box:
    """A box round its words, with its tag above them in the top margin."""
    padding = theme.box.padding
    level = "body"
    words = text
    if point is None or point.role == "emphasis":
        words = "\n".join(
            f"**{line.replace('**', '')}**" if line.strip() else line for line in text.split("\n")
        )
    try:
        block = _balanced(words, cap, level, theme, measurer)
    except FitError as error:
        what = "the claim" if point is None else f"the point {name!r}"
        raise FitError(
            f"{what} has a word wider than the {cap:.0f} units it may have. Shorten it, or "
            f"give the diagram more width."
        ) from error
    tag: TextBlock | None = None
    tag_height = 0.0
    if point is not None:
        tag = wrap(_tag_words(point, theme), 1e6, measurer, theme=theme, level="label")
        tag_height = tag.height + TAG_GAP * theme.scale["body"] / 11
    inner = max(block.width, tag.width if tag is not None else 0.0)
    width = inner + padding.horizontal
    height = padding.top + tag_height + block.height + padding.bottom
    if point is None:
        # A pill: its caps take room the words may not use.
        width += block.height * 0.6
    return _Box(id=name, point=point, depth=depth, tag=tag, block=block, width=width, height=height)


def _tag_words(point: ArgumentPoint, theme: Theme) -> str:
    return theme.argument.for_tag if point.stance == "for" else theme.argument.against_tag


def _drawing(
    document: Document, root: _Box, theme: Theme, measurer: TextMeasurer
) -> ArgumentDrawing:
    unit = theme.scale["body"] / 11
    rows: dict[int, list[_Box]] = {}

    def collect(box: _Box) -> None:
        rows.setdefault(box.depth, []).append(box)
        for each in box.units:
            for member in each.members:
                collect(member)

    collect(root)

    # Across: each box centred over what hangs from it.
    def place(box: _Box, left: float) -> None:
        under = sum(each.span for each in box.units) + UNIT_GAP * unit * max(len(box.units) - 1, 0)
        box.x = left + (box.span - box.width) / 2
        cursor = left + (box.span - under) / 2
        for each in box.units:
            inner = cursor
            for member in each.members:
                place(member, inner)
                inner += member.span + MEMBER_GAP * unit
            cursor += each.span + UNIT_GAP * unit

    place(root, 0.0)

    # Down: each row as tall as its tallest box, and the gap under it as deep as
    # the lanes its connectors need, plus a bracket's room if one hangs there.
    plans: dict[str, _Plan] = {}
    for depth in sorted(rows):
        for box in rows[depth]:
            plans[box.id] = _plan(box, unit)
    tops: dict[int, float] = {}
    cursor = 0.0
    depths = sorted(rows)
    for depth in depths:
        tops[depth] = cursor
        height = max(box.height for box in rows[depth])
        lanes = max((plans[box.id].levels for box in rows[depth]), default=0)
        bracket = any(len(each.members) > 1 for box in rows[depth] for each in box.units)
        cursor += (
            height
            + max(ROW_GAP * unit, (lanes + 1) * LANE * unit)
            + (BRACKET * unit if bracket else 0.0)
        )
        for box in rows[depth]:
            box.y = tops[depth]

    lines: list[Primitive] = []
    shapes: list[Primitive] = []
    texts: list[Primitive] = []
    drawn: list[PointDrawn] = []
    connectors: list[ConnectorDrawn] = []
    brackets: list[tuple[tuple[str, ...], Rect4]] = []
    fill = theme.argument.against_fill
    fill_colour = (
        theme.mark.colour_for(theme.mark.fills.index(fill)) if fill in theme.mark.fills else ""
    )

    for depth in depths:
        row_bottom = tops[depth] + max(box.height for box in rows[depth])
        for box in rows[depth]:
            plan = plans[box.id]
            if not box.units:
                continue
            below = tops[depth + 1]
            bracket_room = (
                BRACKET * unit
                if any(len(e.members) > 1 for b in rows[depth] for e in b.units)
                else 0.0
            )
            lane_top = row_bottom
            lane_bottom = below - bracket_room
            levels = max(plan.levels, 1)
            bottom = box.y + box.height
            for each, port, level in zip(box.units, plan.ports, plan.lanes, strict=True):
                first = each.members[0]
                role = CONNECTOR_ROLES[first.point.role if first.point else "step"]
                if len(each.members) > 1:
                    # A bracket over the whole group, its ends turned down onto the
                    # outer corners, and one stem from its middle.
                    reach = INSET * unit
                    left_end = each.members[0].x + reach
                    right_end = each.members[-1].x + each.members[-1].width - reach
                    bracket_y = below - bracket_room
                    start = (_anchor(each), bracket_y)
                    lines.append(
                        Path(
                            role,
                            points=(
                                (left_end, below),
                                (left_end, bracket_y),
                                (right_end, bracket_y),
                                (right_end, below),
                            ),
                        )
                    )
                    brackets.append(
                        (tuple(m.id for m in each.members), (left_end, bracket_y, right_end, below))
                    )
                    role = CONNECTOR_ROLES["step"]
                else:
                    start = (first.x + first.width / 2, below)
                    if first.point is not None and first.point.role == "note":
                        # Unboxed: the line reaches down to the words' tag.
                        start = (start[0], below + theme.box.padding.top - 2 * unit)
                route: tuple[tuple[float, float], ...]
                if level is None:
                    start = (port, start[1])
                    route = (start, (port, bottom))
                else:
                    lane_y = lane_top + (lane_bottom - lane_top) * (level + 1) / (levels + 1)
                    route = (start, (start[0], lane_y), (port, lane_y), (port, bottom))
                head = end_marker("arrow", route[-2], route[-1], role, theme)
                tip_back = theme.head_length_for(role)
                shaft = (*route[:-1], (port, bottom + tip_back * 0.6))
                lines.append(Path(role, points=shaft))
                lines.extend(head)
                connectors.append(
                    ConnectorDrawn(
                        members=tuple(m.id for m in each.members),
                        to=box.id,
                        points=route,
                        role=role,
                    )
                )

    for depth in depths:
        for box in rows[depth]:
            shapes_, texts_, entry = _box_primitives(box, theme, unit, fill, fill_colour)
            shapes.extend(shapes_)
            texts.extend(texts_)
            if entry is not None:
                drawn.append(entry)

    left = min(box.x for depth in depths for box in rows[depth])
    right = max(box.x + box.width for depth in depths for box in rows[depth])
    bottom_edge = max(box.y + box.height for depth in depths for box in rows[depth])
    dx, dy = -left, 0.0
    scene = Scene(
        width=right - left,
        height=bottom_edge,
        primitives=tuple(moved(p, dx, dy) for p in (*lines, *shapes, *texts)),
        title=document.title,
        description=document.description,
    )

    def shifted(rect: Rect4) -> Rect4:
        return (rect[0] + dx, rect[1] + dy, rect[2] + dx, rect[3] + dy)

    return ArgumentDrawing(
        scene=scene,
        claim=shifted((root.x, root.y, root.x + root.width, root.y + root.height)),
        points=tuple(
            PointDrawn(
                id=entry.id,
                stance=entry.stance,
                role=entry.role,
                box=shifted(entry.box),
                tag=shifted(entry.tag),
                words=shifted(entry.words),
                fill=entry.fill,
                depth=entry.depth,
            )
            for entry in drawn
        ),
        connectors=tuple(
            ConnectorDrawn(
                members=c.members,
                to=c.to,
                points=tuple((x + dx, y + dy) for x, y in c.points),
                role=c.role,
            )
            for c in connectors
        ),
        brackets=tuple((ids, shifted(rect)) for ids, rect in brackets),
    )


@dataclass
class _Plan:
    """Where each connector arrives on one box, and the lane it crosses on."""

    ports: list[float]
    lanes: list[int | None]
    levels: int


def _plan(box: _Box, unit: float) -> _Plan:
    """Ports along `box`'s bottom, one per unit, and a lane for each that must move.

    A port sits straight above its unit when the box's bottom reaches that far,
    so most connectors are one vertical line; the rest arrive in order, `PORT`
    apart. A connector that moves across goes on its own lane: those moving
    right are numbered from the outermost (highest) in, and so are those moving
    left, so no two cross.
    """
    count = len(box.units)
    if not count:
        return _Plan([], [], 0)
    anchors = [_anchor(each) for each in box.units]
    spans = [_reach(each, unit) for each in box.units]
    low = box.x + INSET * unit
    high = box.x + box.width - INSET * unit
    gap = PORT * unit
    if count > 1 and (high - low) / (count - 1) < gap:
        gap = (high - low) / (count - 1)
    # Each port as near its unit's middle as the two edges allow: anywhere both
    # this box's bottom and the unit's top (or bracket) reach is a straight line.
    ports: list[float] = []
    for anchor, (start, end) in zip(anchors, spans, strict=True):
        shared = (max(start, low), min(end, high))
        lo, hi = shared if shared[0] <= shared[1] else (low, high)
        ports.append(min(max(anchor, lo), hi))
    for index in range(1, count):
        ports[index] = max(ports[index], ports[index - 1] + gap)
    for index in range(count - 1, -1, -1):
        limit = high - gap * (count - 1 - index)
        ports[index] = min(ports[index], limit)
        if index < count - 1:
            ports[index] = min(ports[index], ports[index + 1] - gap)
    ports = [max(port, low) for port in ports]
    straight = [
        start - 1e-6 <= port <= end + 1e-6 for port, (start, end) in zip(ports, spans, strict=True)
    ]
    rightward = [i for i in range(count) if not straight[i] and anchors[i] < ports[i]]
    leftward = [i for i in range(count) if not straight[i] and anchors[i] > ports[i]]
    lanes: list[int | None] = [None] * count
    for level, index in enumerate(rightward):
        lanes[index] = level
    for level, index in enumerate(reversed(leftward)):
        lanes[index] = level
    return _Plan(ports, lanes, max(len(rightward), len(leftward)))


def _reach(each: _Unit, unit: float) -> tuple[float, float]:
    """Where along a unit's top (or its bracket) a connector may leave it."""
    first, last = each.members[0], each.members[-1]
    return (first.x + INSET * unit, last.x + last.width - INSET * unit)


def _anchor(each: _Unit) -> float:
    """Where a unit's connector leaves it: a point's middle, or its bracket's."""
    first, last = each.members[0], each.members[-1]
    return (first.x + last.x + last.width) / 2


def _box_primitives(
    box: _Box, theme: Theme, unit: float, fill: str, fill_colour: str
) -> tuple[list[Primitive], list[Primitive], PointDrawn | None]:
    padding = theme.box.padding
    point = box.point
    shapes: list[Primitive] = []
    texts: list[Primitive] = []
    if point is None:
        shapes.append(Rect(CLAIM_ROLE, x=box.x, y=box.y, width=box.width, height=box.height))
        top = box.y + padding.top
        texts.extend(_lines(box.block, box.x + box.width / 2, top, CLAIM_ROLE, "body", "middle"))
        return shapes, texts, None
    role = BOX_ROLES[point.role]
    against = point.stance == "against"
    boxed = theme.roles[role].shape != "none"
    drawn_fill = fill if against and boxed else ""
    if boxed:
        shapes.append(
            Rect(
                role,
                x=box.x,
                y=box.y,
                width=box.width,
                height=box.height,
                fill=drawn_fill,
                fill_colour=fill_colour if drawn_fill else "",
            )
        )
    assert box.tag is not None
    middle = box.x + box.width / 2
    # Unboxed, the tag lines up with the words rather than with a box's padding.
    tag_left = box.x + padding.left if boxed else middle - box.block.width / 2
    tag_top = box.y + padding.top
    # A run, not a line: the tag is furniture in the label type, like a change's
    # tag — the theme's word, never an author's spans.
    texts.append(
        TextRun(
            role,
            x=tag_left,
            y=tag_top + box.tag.baseline(0),
            text=_tag_words(point, theme),
            level="label",
            font=theme.font.default,
            anchor="start",
        )
    )
    words_top = tag_top + box.tag.height + TAG_GAP * unit
    texts.extend(_lines(box.block, middle, words_top, role, "body", "middle"))
    return (
        shapes,
        texts,
        PointDrawn(
            id=point.id,
            stance=point.stance,
            role=point.role,
            box=(box.x, box.y, box.x + box.width, box.y + box.height),
            tag=(tag_left, tag_top, tag_left + box.tag.width, tag_top + box.tag.height),
            words=(
                middle - box.block.width / 2,
                words_top,
                middle + box.block.width / 2,
                words_top + box.block.height,
            ),
            fill=drawn_fill,
            depth=box.depth,
        ),
    )


def _lines(
    block: TextBlock, x: float, top: float, role: str, level: str, anchor: str
) -> list[TextLine]:
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
                    role,
                    x=x,
                    y=top + block.baseline(index),
                    spans=spans,
                    level=level,
                    anchor=anchor,
                )
            )
    return found


def _balanced(
    text: str, width: float, level: str, theme: Theme, measurer: TextMeasurer
) -> TextBlock:
    """`text` wrapped to `width`, then as narrow as it goes on as many lines."""
    block = wrap(text, width, measurer, theme=theme, level=level)
    if len(block.lines) < 2:
        return block
    low, high = width / 2, width
    for _ in range(10):
        middle = (low + high) / 2
        try:
            trial = wrap(text, middle, measurer, theme=theme, level=level)
        except FitError:
            low = middle
            continue
        if len(trial.lines) == len(block.lines):
            high, block = middle, trial
        else:
            low = middle
    return block


__all__ = [
    "ArgumentDrawing",
    "ConnectorDrawn",
    "PointDrawn",
    "argument_drawing",
    "argument_scene",
]

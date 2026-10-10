"""`lanes`: a flow whose actors are drawn as swimlanes.

A `lanes` document is a `flow` document whose every node names its `actor`, and
the whole difference is where that actor is drawn: once, as a strip of the page
holding every step of that party, instead of as the lead of each box. An arrow
that crosses from one strip to another is then a hand-off, which is the thing a
swimlane diagram exists to show.

**Everything but the cross axis is the flow's.** The graph is ranked exactly as
`flow` ranks it — cycles broken, longest path — and the ranks run along the
lanes. Only the other coordinate changes: where a flow orders a rank to reduce
crossings, here a box's lane decides it, and boxes of one lane sharing a rank
stack inside the strip. The result is handed back as an `Arrangement`, so sizing,
self-loops, routing and label placement are `kinds.graph`'s, unchanged.

**The theme picks the orientation.** `[lanes] orientation` says whether the
lanes run across the page (`rows`, ranks reading left to right) or down it
(`columns`, ranks reading down); `auto` takes rows when they fit the width and
columns when they do not. The author never chooses, as with direction anywhere.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from itertools import pairwise
from types import MappingProxyType
from typing import Final

from drawspec.errors import FitError
from drawspec.geometry import Box, size_box
from drawspec.kinds.common import text_runs
from drawspec.kinds.containers import GROUP_LEVEL, GROUP_ROLE, Arrangement
from drawspec.layout import Layout, LayoutEdge, LayoutNode, Placement, Spacing
from drawspec.layout.base import rank_nodes
from drawspec.routing import Obstacle, Route
from drawspec.scene import Path, Polygon, Primitive
from drawspec.schema import Document
from drawspec.text.measure import TextMeasurer
from drawspec.theme import Theme

#: The layout direction each orientation reads in: lanes across the page are
#: read left to right, lanes down it are read top to bottom.
DIRECTION_OF: Final[Mapping[str, str]] = MappingProxyType({"rows": "right", "columns": "down"})

#: How much of the canvas a lane's heading may take across a row of lanes before
#: it wraps. A heading column is width every rank pays for, so it is kept to the
#: name of a party rather than a sentence about one.
HEADING_SHARE: Final = 0.16

#: The most of the canvas one box may take, as on a `flow` (`kinds.graph`'s
#: `NODE_WIDTH_SHARE`, which cannot be imported from there without a cycle).
NODE_SHARE: Final = 0.25


@dataclass(frozen=True)
class Lane:
    """One lane, placed: its strip — heading cell included — and its heading."""

    name: str
    x: float
    y: float
    width: float
    height: float
    heading: Box
    """The lane's name, sized and placed in its heading cell."""

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    def moved(self, dx: float, dy: float) -> Lane:
        return replace(
            self,
            x=self.x + dx,
            y=self.y + dy,
            heading=self.heading.moved_to(self.heading.x + dx, self.heading.y + dy),
        )

    def resized(self, start: float, size: float, rows: bool) -> Lane:
        """This lane from `start` across, `size` thick, its heading re-centred in it."""
        heading = self.heading
        if rows:
            spot = heading.moved_to(heading.x, start + (size - heading.height) / 2)
            return replace(self, y=start, height=size, heading=spot)
        spot = heading.moved_to(start + (size - heading.width) / 2, heading.y)
        return replace(self, x=start, width=size, heading=spot)


@dataclass(frozen=True)
class Swimlanes:
    """The lanes of one drawing, and which way they run."""

    lanes: tuple[Lane, ...]
    orientation: str
    """`rows` or `columns` — never `auto`, which is resolved by the time a drawing exists."""

    head: float
    """Where the heading cells end along the reading direction: the divider."""

    def moved(self, dx: float, dy: float) -> Swimlanes:
        return replace(
            self,
            lanes=tuple(lane.moved(dx, dy) for lane in self.lanes),
            head=self.head + (dx if self.orientation == "rows" else dy),
        )

    def settled(
        self,
        routes: Sequence[Route],
        places: Mapping[str, Placement],
        lane_of: Mapping[str, str],
        clear: float,
    ) -> Swimlanes:
        """Each boundary moved off any route that runs along it, into the widest gap.

        A route going round a box needs its arrow head's length before it may
        turn, which can be most of a lane's padding — and the boundary is where
        the padding ends, so a returning edge ran a few units beside the dashed
        line or on it. Only a boundary with a route closer than `clear` moves,
        and only between the last box of one lane and the first of the next, so
        every box stays inside its own strip and a heading never loses room.
        """
        rows = self.orientation == "rows"
        lanes = list(self.lanes)
        runs = [
            (first[1] if rows else first[0])
            for route in routes
            for first, second in pairwise(route.points)
            if (first[1] == second[1]) == rows and first != second
        ]
        for index in range(1, len(lanes)):
            before, after = lanes[index - 1], lanes[index]
            here = after.y if rows else after.x
            low = max(
                (places[i].bottom if rows else places[i].right)
                for i, lane in lane_of.items()
                if lane == before.name
            )
            high = min(
                (places[i].y if rows else places[i].x)
                for i, lane in lane_of.items()
                if lane == after.name
            )
            near = sorted(run for run in runs if low < run < high)
            if not any(abs(run - here) < clear for run in near):
                continue
            stops = [low, *near, high]
            start, end = max(pairwise(stops), key=lambda gap: gap[1] - gap[0])
            moved = (start + end) / 2
            span_before = moved - (before.y if rows else before.x)
            span_after = (after.bottom if rows else after.right) - moved
            if not rows and (
                span_before < before.heading.width or span_after < after.heading.width
            ):
                continue
            if rows:
                lanes[index - 1] = before.resized(before.y, span_before, rows)
                lanes[index] = after.resized(moved, span_after, rows)
            else:
                lanes[index - 1] = before.resized(before.x, span_before, rows)
                lanes[index] = after.resized(moved, span_after, rows)
        return replace(self, lanes=tuple(lanes))

    def covering(self, left: float, top: float, right: float, bottom: float) -> Swimlanes:
        """The lanes stretched to take in everything drawn between these bounds.

        A route that goes round the drawing, or a label beside one, is outside
        the boxes' extent; the strips are stretched along the reading direction to
        reach it, and the outermost two across it, so nothing drawn sits outside
        every lane.
        """
        if not self.lanes:
            return self
        rows = self.orientation == "rows"
        first, last = self.lanes[0], self.lanes[-1]
        stretched: list[Lane] = []
        for lane in self.lanes:
            if rows:
                near = min(lane.y, top) if lane is first else lane.y
                far = max(lane.bottom, bottom) if lane is last else lane.bottom
                end = max(lane.right, right)
                stretched.append(replace(lane, y=near, height=far - near, width=end - lane.x))
            else:
                near = min(lane.x, left) if lane is first else lane.x
                far = max(lane.right, right) if lane is last else lane.right
                end = max(lane.bottom, bottom)
                stretched.append(replace(lane, x=near, width=far - near, height=end - lane.y))
        return replace(self, lanes=tuple(stretched))

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """Left, top, right, bottom of every lane together."""
        return (
            min(lane.x for lane in self.lanes),
            min(lane.y for lane in self.lanes),
            max(lane.right for lane in self.lanes),
            max(lane.bottom for lane in self.lanes),
        )

    def markers(self) -> tuple[Obstacle, ...]:
        """A sliver of each boundary inside the heading band, for routing only.

        The router lays its channels down the middle of each gap between box
        edges, and the middle of the gap between two lanes' boxes is the
        boundary itself — so a route going round a box ran along the dashed
        line. A boundary's edges added to the grid split that gap in two, and
        each half keeps its channel inside its own lane. Inside the heading band
        they block nothing the band does not already block.
        """
        if not self.lanes:
            return ()
        sliver = 0.5
        if self.orientation == "rows":
            left = min(lane.x for lane in self.lanes)
            return tuple(
                Obstacle(
                    f"\x00lane boundary {index}",
                    x=left,
                    y=lane.y - sliver,
                    width=self.head - left,
                    height=sliver * 2,
                )
                for index, lane in enumerate(self.lanes[1:])
            )
        top = min(lane.y for lane in self.lanes)
        return tuple(
            Obstacle(
                f"\x00lane boundary {index}",
                x=lane.x - sliver,
                y=top,
                width=sliver * 2,
                height=self.head - top,
            )
            for index, lane in enumerate(self.lanes[1:])
        )

    def headings(self) -> tuple[Obstacle, ...]:
        """The heading band, as one obstacle a route must go round and a label avoid."""
        if not self.lanes:
            return ()
        left, top, right, bottom = self.bounds
        if self.orientation == "rows":
            return (
                Obstacle(
                    "\x00lane headings", x=left, y=top, width=self.head - left, height=bottom - top
                ),
            )
        return (
            Obstacle(
                "\x00lane headings", x=left, y=top, width=right - left, height=self.head - top
            ),
        )

    def separators(self) -> tuple[tuple[tuple[float, float], tuple[float, float]], ...]:
        """The lines drawn: one between each two lanes, and the heading divider."""
        if not self.lanes:
            return ()
        left, top, right, bottom = self.bounds
        lines: list[tuple[tuple[float, float], tuple[float, float]]] = []
        if self.orientation == "rows":
            lines.append(((self.head, top), (self.head, bottom)))
            lines.extend(((left, lane.y), (right, lane.y)) for lane in self.lanes[1:])
        else:
            lines.append(((left, self.head), (right, self.head)))
            lines.extend(((lane.x, top), (lane.x, bottom)) for lane in self.lanes[1:])
        return tuple(lines)


def lanes_arrangement(
    document: Document,
    sized: Callable[[float], dict[str, Box]],
    grown: Callable[[Mapping[str, Box]], Mapping[str, Box]],
    theme: Theme,
    measurer: TextMeasurer,
    spacing: Spacing,
    *,
    max_width: float,
    max_height: float = 0.0,
) -> tuple[Arrangement, Swimlanes, dict[str, Box]]:
    """Lay the document out in lanes, in whichever orientation the theme allows and fits.

    `auto` tries rows first and takes columns when rows are wider than the
    canvas — and, with a binding height, taller than it. When neither fits the
    narrower is returned with `fits=False`, for the caller to raise on, exactly
    as `layout.base.best_layout` does for a flow.

    The boxes are sized here, once per orientation, by `sized` at a width limit
    — because the limit is the orientation's: lanes side by side share the
    canvas between them, and ranks across it share it between those. `grown`
    adds any room reserved around a box (its self-loops). The boxes returned are
    the chosen orientation's, before growing.
    """
    choice = theme.lanes.orientation
    orientations = ("rows", "columns") if choice == "auto" else (choice,)
    pad = lane_padding(theme)
    share = max_width * NODE_SHARE
    lanes_wide = max_width / max(len(document.lanes), 1) - pad * 2
    identifiers = [node.id for node in document.nodes]
    ranked, _ = acyclic(identifiers, [LayoutEdge(e.source, e.target) for e in document.edges])
    depth = max(rank_nodes([LayoutNode(i, 1.0, 1.0) for i in identifiers], ranked).values()) + 1
    attempts: list[tuple[Arrangement, Swimlanes, dict[str, Box]]] = []
    for orientation in orientations:
        limit = min(share, lanes_wide)
        if orientation == "rows":
            head = max(
                _heading(name, max_width * HEADING_SHARE, theme, measurer).width
                for name in document.lanes
            )
            room = max_width - head - spacing.node_gap - spacing.rank_gap * (depth - 1)
            limit = min(share, max(room / depth, share / 2))
        try:
            plain = sized(limit)
            arrangement, lanes = _laid_out(
                document, grown(plain), theme, measurer, spacing, orientation, max_width
            )
        except FitError:
            # A word longer than this orientation allows is this orientation not
            # fitting, and the next one may; only when none is left is it raised.
            if orientation == orientations[-1] and not attempts:
                raise
            continue
        attempts.append((arrangement, lanes, plain))
    for wanted_height in (True, False):
        for arrangement, lanes, plain in attempts:
            layout = arrangement.layout
            if layout.width <= max_width and (
                not wanted_height or not max_height or layout.height <= max_height
            ):
                return arrangement, lanes, plain
    arrangement, lanes, plain = min(attempts, key=lambda attempt: attempt[0].layout.width)
    return replace(arrangement, layout=replace(arrangement.layout, fits=False)), lanes, plain


def _heading(name: str, limit: float, theme: Theme, measurer: TextMeasurer) -> Box:
    """A lane's name, sized as a group's caption is, at `limit` wide at most."""
    return size_box(
        _bold(name),
        theme=theme,
        measurer=measurer,
        role=GROUP_ROLE,
        level=GROUP_LEVEL,
        max_width=limit,
        shape="rect",
    )


def _laid_out(
    document: Document,
    boxes: Mapping[str, Box],
    theme: Theme,
    measurer: TextMeasurer,
    spacing: Spacing,
    orientation: str,
    max_width: float,
) -> tuple[Arrangement, Swimlanes]:
    """One orientation: rank along the lanes, stack across them, then place the strips.

    Worked in two axes named for what they mean — *along* the lanes, which is
    the ranks' axis, and *across* them, which is the lanes' — and turned into x
    and y only at the end, so the two orientations are one routine.
    """
    rows = orientation == "rows"
    direction = DIRECTION_OF[orientation]
    pad = lane_padding(theme)
    names = document.lanes
    lane_of = {node.id: node.lane for node in document.nodes}

    def along(box: Box) -> float:
        return box.width if rows else box.height

    def across(box: Box) -> float:
        return box.height if rows else box.width

    # 1. Rank as a flow ranks: cycles broken, longest path in.
    identifiers = [node.id for node in document.nodes]
    nodes = [LayoutNode(i, boxes[i].width, boxes[i].height) for i in identifiers]
    pairs = [LayoutEdge(edge.source, edge.target) for edge in document.edges]
    ranked, reversed_edges = acyclic(identifiers, pairs)
    rank = rank_nodes(nodes, ranked)
    depth = max(rank.values(), default=0) + 1

    # 2. The boxes of each lane at each rank, in the order written, then sorted
    # once by where their neighbours sit, so a fan inside one lane does not cross
    # itself. Within the lane only: the lane decides everything else.
    cells: dict[tuple[str, int], list[str]] = {}
    for identifier in identifiers:
        cells.setdefault((lane_of[identifier], rank[identifier]), []).append(identifier)

    # 3. Headings. Across a row of lanes, a column of names at the start of the
    # strips, each broken to a share of the canvas; down a column of lanes, a
    # name over each strip, broken to the strip it heads.
    stack = {
        name: max(
            (
                sum(across(boxes[i]) for i in cells.get((name, r), ()))
                + spacing.node_gap * max(len(cells.get((name, r), ())) - 1, 0)
                for r in range(depth)
            ),
            default=0.0,
        )
        for name in names
    }
    headings: dict[str, Box] = {}
    for name in names:
        limit = max_width * HEADING_SHARE if rows else max(stack[name], max_width * HEADING_SHARE)
        headings[name] = _heading(name, limit, theme, measurer)
    if rows:
        head = max(heading.width for heading in headings.values())
        thickness = {name: max(stack[name] + pad * 2, headings[name].height) for name in names}
    else:
        head = max(heading.height for heading in headings.values())
        thickness = {name: max(stack[name] + pad * 2, headings[name].width) for name in names}

    # 4. Along: rank bands as the layered engine spaces them, after the headings
    # and a gap — the rank gap, so an arrow arriving at a first box has its shaft.
    bands = [
        max((along(boxes[i]) for i in identifiers if rank[i] == r), default=0.0)
        for r in range(depth)
    ]
    starts: list[float] = []
    cursor = head + spacing.node_gap
    for band in bands:
        starts.append(cursor)
        cursor += band + spacing.rank_gap
    length = cursor - spacing.rank_gap

    # 5. Across: each lane's strip in order, each cell's stack centred in it.
    offsets: dict[str, float] = {}
    cursor = 0.0
    for name in names:
        offsets[name] = cursor
        cursor += thickness[name]
    breadth = cursor

    centre_of: dict[str, float] = {}
    for (name, _), members in cells.items():
        total = sum(across(boxes[i]) for i in members) + spacing.node_gap * (len(members) - 1)
        at = offsets[name] + (thickness[name] - total) / 2
        for identifier in members:
            centre_of[identifier] = at + across(boxes[identifier]) / 2
            at += across(boxes[identifier]) + spacing.node_gap
    centre_of = _untangled(cells, centre_of, ranked, boxes, across, spacing.node_gap)

    places: dict[str, Placement] = {}
    for identifier in identifiers:
        box = boxes[identifier]
        r = rank[identifier]
        a = starts[r] + (bands[r] - along(box)) / 2
        c = centre_of[identifier] - across(box) / 2
        x, y = (a, c) if rows else (c, a)
        places[identifier] = Placement(x=x, y=y, width=box.width, height=box.height, rank=r)

    lanes: list[Lane] = []
    for name in names:
        heading = headings[name]
        start, size = offsets[name], thickness[name]
        if rows:
            spot = heading.moved_to((head - heading.width) / 2, start + (size - heading.height) / 2)
            lanes.append(Lane(name, 0.0, start, length, size, spot))
        else:
            spot = heading.moved_to(start + (size - heading.width) / 2, (head - heading.height) / 2)
            lanes.append(Lane(name, start, 0.0, size, length, spot))

    width, height = (length, breadth) if rows else (breadth, length)
    ranks = tuple(
        tuple(i for name in names for i in cells.get((name, r), ())) for r in range(depth)
    )
    layout = Layout(
        placements=places,
        width=width,
        height=height,
        ranks=ranks,
        reversed_edges=reversed_edges,
        direction=direction,
        fits=width <= max_width,
    )
    arrangement = Arrangement(
        layout=layout,
        places=places,
        frames=(),
        directions=MappingProxyType(dict.fromkeys(places, direction)),
    )
    return arrangement, Swimlanes(tuple(lanes), orientation, head)


def acyclic(
    identifiers: Sequence[str], edges: Sequence[LayoutEdge]
) -> tuple[tuple[LayoutEdge, ...], frozenset[tuple[str, str]]]:
    """The edges with every cycle broken from where the process starts.

    `layout.base.break_cycles` searches from the ids in sorted order, which is
    deterministic and knows nothing of the reading: a review loop whose step
    happened to sort first was taken as the start, and *Amends* was drawn beside
    *Opens a pull request* as if the two began the process together. Here the
    search starts from the steps nothing leads to, in the order written, then
    from any step still unvisited, and follows edges in the order written — so
    the edge reversed is the one that returns, as the author wrote it.
    Deterministic all the same: everything it reads is the document's order.
    """
    outgoing: dict[str, list[str]] = {identifier: [] for identifier in identifiers}
    entered: set[str] = set()
    for edge in edges:
        if edge.source != edge.target:
            outgoing[edge.source].append(edge.target)
            entered.add(edge.target)
    roots = [i for i in identifiers if i not in entered] + [i for i in identifiers if i in entered]
    colour = dict.fromkeys(identifiers, 0)  # 0 unseen, 1 on the path, 2 done
    back: set[tuple[str, str]] = set()
    for root in roots:
        if colour[root]:
            continue
        colour[root] = 1
        stack: list[tuple[str, int]] = [(root, 0)]
        while stack:
            node, index = stack[-1]
            if index < len(outgoing[node]):
                stack[-1] = (node, index + 1)
                target = outgoing[node][index]
                if colour[target] == 1:
                    back.add((node, target))
                elif colour[target] == 0:
                    colour[target] = 1
                    stack.append((target, 0))
            else:
                colour[node] = 2
                stack.pop()
    ranked = tuple(
        LayoutEdge(edge.target, edge.source) if (edge.source, edge.target) in back else edge
        for edge in edges
        if edge.source != edge.target
    )
    return ranked, frozenset(back)


def lane_padding(theme: Theme) -> float:
    """The room between a lane's boundary and the boxes in it, on each side.

    A box's own side padding plus a route's clearance: enough that a line going
    round a box inside its lane has a channel between the box and the boundary,
    and does not run along the boundary itself.
    """
    return theme.box.padding.left + theme.edge.clearance


def _untangled(
    cells: Mapping[tuple[str, int], Sequence[str]],
    centres: Mapping[str, float],
    edges: Sequence[LayoutEdge],
    boxes: Mapping[str, Box],
    across: Callable[[Box], float],
    gap: float,
) -> dict[str, float]:
    """Each stack of several boxes reordered by where its neighbours sit across.

    One barycentre pass, and only inside a cell — a lane at one rank — because
    the lane, not the crossings, decides everything else. Ties keep the order
    written, as the layered engine's do. The slots the stack already holds are
    kept; only who stands in which changes.
    """
    moved = dict(centres)
    neighbours: dict[str, list[str]] = {}
    for edge in edges:
        neighbours.setdefault(edge.source, []).append(edge.target)
        neighbours.setdefault(edge.target, []).append(edge.source)
    for members in cells.values():
        if len(members) < 2:
            continue
        written = {identifier: index for index, identifier in enumerate(members)}
        pulls: dict[str, tuple[float, int]] = {}
        for identifier in members:
            near = [centres[n] for n in neighbours.get(identifier, ()) if n not in written]
            mean = sum(near) / len(near) if near else centres[identifier]
            pulls[identifier] = (mean, written[identifier])
        ordered = sorted(members, key=pulls.__getitem__)
        at = min(centres[i] - across(boxes[i]) / 2 for i in members)
        for identifier in ordered:
            size = across(boxes[identifier])
            moved[identifier] = at + size / 2
            at += size + gap
    return moved


def _bold(name: str) -> str:
    """A lane's name, set bold where the author's own spans leave room for it."""
    return name if "**" in name or "`" in name else f"**{name}**"


def lanes_primitives(
    lanes: Swimlanes, theme: Theme, measurer: TextMeasurer
) -> tuple[Primitive, ...]:
    """Every second lane's stripe, the separators, then each lane's heading."""
    lines: list[Primitive] = []
    if theme.lanes.stripe:
        lines.extend(
            Polygon(
                GROUP_ROLE,
                points=(
                    (lane.x, lane.y),
                    (lane.right, lane.y),
                    (lane.right, lane.bottom),
                    (lane.x, lane.bottom),
                ),
                fill="solid",
                fill_colour="currentColor",
                fill_opacity=theme.lanes.stripe,
                region=True,
            )
            for lane in lanes.lanes[1::2]
        )
    lines.extend(Path(theme.lanes.separator, points=points) for points in lanes.separators())
    for lane in lanes.lanes:
        lines.extend(text_runs(lane.heading, theme, measurer))
    return tuple(lines)


__all__ = [
    "DIRECTION_OF",
    "HEADING_SHARE",
    "Lane",
    "Swimlanes",
    "acyclic",
    "lane_padding",
    "lanes_arrangement",
    "lanes_primitives",
]

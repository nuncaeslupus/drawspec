"""The `cycle` kind: nodes on a circle, arrows following it round.

A cycle is a parametric template, not a graph layout — `docs/theme-requirements.md`
§6 lists it with pyramids and concentric circles, and D-1 records what happens
when it is treated as a graph instead: the layered engine ranks the loop into a
column and the back edge retraces the forward edges, so the cycle is invisible.
No amount of routing repairs that; the layout is what is wrong.

So the geometry here is trigonometry rather than ranking, and it delivers the
three things the requirements ask of a cycle directly:

**Steps spaced evenly.** One angle, `2π / n`, used for every node. Not
accumulated per node — accumulating is how the last gap ends up different from
the rest.

**Arrows all following one direction.** Every edge is drawn as an arc along the
circle in the same rotational sense, so the drawing reads as a loop wherever the
eye enters it.

**No crossings.** Adjacent nodes are joined along the circumference, so two
edges can only meet at a node they share. An edge between non-adjacent nodes
would be a chord, and a chord across a ring is not a cycle — such a document is
refused rather than drawn misleadingly.
"""

from __future__ import annotations

import math
from typing import Final

from drawspec.errors import DrawspecError, FitError
from drawspec.geometry import Box, normalise, size_box
from drawspec.kinds.common import box_primitives
from drawspec.scene import Path, Polygon, Primitive, Scene, TextRun, extents, moved
from drawspec.schema import Document, Node
from drawspec.text.measure import TextMeasurer
from drawspec.theme import Theme

#: Where the first node sits: the top of the circle, reading clockwise, which is
#: how a clock face and every cycle diagram in the corpus are read.
START_ANGLE: Final = -math.pi / 2

#: How much of the canvas width a cycle's node boxes may take. A node wider than
#: this leaves no room for the ring itself.
NODE_WIDTH_SHARE: Final = 0.34

#: How far past that share a step may go when its shape has made it taller than
#: it is wide. Less headroom than a graph gets: a cycle's boxes sit on a ring
#: whose radius they set, so a wider box is a bigger figure, and half a canvas
#: of node would leave nothing for the ring.
NODE_WIDEN: Final = 1.5

#: Segments per arc. Enough that a curve reads as a curve at the sizes these are
#: drawn, few enough that the path data stays legible in a diff.
ARC_SEGMENTS: Final = 12

#: How far a band's head reaches back along the arc, as a multiple of the band's
#: own width. The same proportion an ordinary arrow head has to its shaft, so a
#: ribbon reads as that arrow drawn fat rather than as a different mark.
ARROW_ASPECT: Final = 1.1

#: How much wider a band's head is than its shaft. Below about 1.6 the head stops
#: reading as a head and the whole thing looks like a band that got confused at
#: one end.
HEAD_FLARE: Final = 2.0

#: The smallest cycle that can be drawn. Two nodes is a pair of arcs there and
#: back, which does read as a loop; one node is not a cycle at all.
MINIMUM_NODES: Final = 2

#: Halvings used to find where the ring crosses a box's outline. Forty takes the
#: answer far below a rendered pixel, and a fixed count is what makes the same
#: document render to the same bytes twice.
_BISECTIONS: Final = 40


def cycle_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Render a `cycle` document to a `Scene`.

    Raises:
        DrawspecError: the document is not a cycle, or its edges do not form one.
        FitError: the ring cannot fit the canvas at this type scale.
    """
    if document.kind != "cycle":
        raise DrawspecError(f"{document.kind!r} is not the cycle kind")
    if len(document.nodes) < MINIMUM_NODES:
        raise DrawspecError(
            f"a cycle needs at least {MINIMUM_NODES} nodes; this one has "
            f"{len(document.nodes)}. One step is not a loop."
        )

    order = _ring_order(document)
    width = document.width if document.width else theme.canvas.width
    boxes = _boxes(document, theme, measurer, width)
    radius = _radius(boxes, theme)
    hub = _hub_box(document.hub, theme, measurer, width)
    spokes = _spokes(document)
    if hub is not None:
        radius = _around_hub(radius, order, boxes, hub, spokes, theme, measurer, width)
    extent = _extent(radius, boxes, width, hub)

    # Across, the ring sits in the middle of the canvas every diagram shares.
    # Down, it sits under the top margin: a ring is wider than it is tall as soon
    # as its steps hold sentences, and squaring the canvas would hang a third of
    # the drawing's own height off it as blank paper above and below.
    tallest = max(box.height for box in boxes.values())
    centre = (extent / 2, theme.box.padding.top + tallest / 2 + radius)
    placed = {
        node_id: boxes[node_id].moved_to(
            centre[0] + radius * math.cos(_angle(index, len(order))) - boxes[node_id].width / 2,
            centre[1] + radius * math.sin(_angle(index, len(order))) - boxes[node_id].height / 2,
        )
        for index, node_id in enumerate(order)
    }
    if hub is not None and document.hub is not None:
        placed[document.hub.id] = hub.moved_to(
            centre[0] - hub.width / 2, centre[1] - hub.height / 2
        )

    primitives: list[Primitive] = []
    # Arcs first, so a node box is drawn over the line that reaches it rather
    # than under it — the same paint order every other family uses.
    for index, node_id in enumerate(order):
        following = order[(index + 1) % len(order)]
        role = _edge_role(document, node_id, following)
        primitives.extend(
            _arc(
                centre,
                radius,
                index,
                index + 1,
                len(order),
                placed[node_id],
                placed[following],
                role,
                theme,
            )
        )
    # Shortcuts before the boxes for the same reason the arcs are: a step is
    # drawn over the line that reaches it.
    for source, target, role, label in _shortcuts(document, order):
        if hub is not None and document.hub is not None:
            _clear_of_hub(source, target, placed, document.hub, theme)
        primitives.extend(_shortcut(placed[source], placed[target], role, label, theme, measurer))
    # Spokes: the same straight run a shortcut is, between the middle and a step.
    for source, target, role, label in spokes:
        primitives.extend(
            _shortcut(placed[source], placed[target], role, label, theme, measurer, spoke=True)
        )
    for node_id in order:
        primitives.extend(box_primitives(placed[node_id], theme, measurer))
    if hub is not None and document.hub is not None:
        primitives.extend(box_primitives(placed[document.hub.id], theme, measurer))

    # Framed against the ink rather than against the steps: with five steps the
    # lowest point of the drawing is the bottom of the arc *between* the two
    # lowest boxes, and a canvas measured from the boxes cuts that arc in half.
    # Flush to that ink — the channel of blank around it is `render.framed`'s, and
    # was this family's own ten units of `[box] padding` while every other family
    # had a different answer.
    _, top, _, bottom = extents(primitives)
    shift = -top
    primitives = [moved(primitive, 0.0, shift) for primitive in primitives]
    centre = (centre[0], centre[1] + shift)

    return Scene(
        width=extent,
        height=bottom + shift,
        primitives=tuple(primitives),
        title=document.title,
        description=document.description,
        # The ring is no longer the middle of the canvas, so where it *is* has to
        # be sayable by something other than dividing the height by two.
        metadata=(
            ("centre_x", f"{centre[0]:.6f}"),
            ("centre_y", f"{centre[1]:.6f}"),
            ("radius", f"{radius:.6f}"),
        ),
    )


def _angle(index: int, count: int) -> float:
    """The angle of node `index`. Computed, never accumulated."""
    return START_ANGLE + 2 * math.pi * index / count


def _ring_order(document: Document) -> tuple[str, ...]:
    """The nodes in the order the edges walk them, starting at the first node.

    A cycle document says which step follows which; this follows that chain
    rather than the order the nodes happen to be listed in, so an author can
    write the nodes in any order and still get the loop they described.

    **A step may have more than one outgoing edge.** It used to be refused
    outright — *"a cycle is one loop: every step has exactly one next step"* —
    which is true of the ring and false of the diagram: the NIST incident cycle
    is four phases round a loop *plus* a dashed return from containment to
    detection, labelled *when new indicators appear*. Drawn as a `flow` instead,
    the loop breaks open and the four phases read 3, 4, 1, 2 down the page, so
    the author had to choose between the cycle and its one exception.

    So the ring is now *found* rather than read off: the walk tries each
    outgoing edge in the order the document lists them and backtracks, and the
    first closed loop through every node is the ring. Every edge not on it is a
    shortcut, drawn inside. Trying declaration order first is what makes the
    answer predictable — an author who lists the ring edges first gets the ring
    they wrote.

    Raises:
        DrawspecError: no closed loop through every node exists.
    """
    identifiers = [node.id for node in document.nodes]
    known = set(identifiers)
    # A spoke to the hub is not a way round, so it does not count towards one.
    ring_edges = [edge for edge in document.edges if edge.source in known and edge.target in known]
    if len(ring_edges) < len(identifiers):
        raise DrawspecError(
            f"a cycle of {len(identifiers)} nodes needs {len(identifiers)} edges to "
            f"close the loop; this one has {len(ring_edges)}"
            + (" between its steps, the hub's spokes aside." if document.hub else ".")
        )

    following: dict[str, list[str]] = {identifier: [] for identifier in identifiers}
    for edge in document.edges:
        if edge.source in known and edge.target in known:
            following[edge.source].append(edge.target)

    start = identifiers[0]
    order: list[str] = [start]
    seen = {start}

    def walk(current: str) -> bool:
        if len(order) == len(identifiers):
            return start in following[current]
        for target in following[current]:
            if target in seen:
                continue
            order.append(target)
            seen.add(target)
            if walk(target):
                return True
            seen.discard(target)
            order.pop()
        return False

    if not walk(start):
        raise DrawspecError(
            f"these edges do not close one loop through every node, so this is not a "
            f"cycle: no way round from {start!r} visits all {len(identifiers)} steps and "
            f"comes back. A cycle returns to where it started, having been everywhere."
        )
    return tuple(order)


def _shortcuts(document: Document, order: tuple[str, ...]) -> tuple[tuple[str, str, str, str], ...]:
    """Every edge that is not part of the ring, as `(source, target, role, label)`.

    A cycle plus a shortcut is still a cycle. What the shortcut is *not* is
    another step of the loop, which is why it is drawn across the ring rather
    than along it.
    """
    ring = {(node, order[(index + 1) % len(order)]) for index, node in enumerate(order)}
    hub = document.hub.id if document.hub else None
    return tuple(
        (edge.source, edge.target, edge.role, edge.label)
        for edge in document.edges
        if (edge.source, edge.target) not in ring and hub not in (edge.source, edge.target)
    )


def _spokes(document: Document) -> tuple[tuple[str, str, str, str], ...]:
    """Every edge joining the hub to a step, as `(source, target, role, label)`."""
    if document.hub is None:
        return ()
    hub = document.hub.id
    return tuple(
        (edge.source, edge.target, edge.role, edge.label)
        for edge in document.edges
        if hub in (edge.source, edge.target)
    )


def _edge_role(document: Document, source: str, target: str) -> str:
    for edge in document.edges:
        if edge.source == source and edge.target == target:
            return edge.role
    return "flow"


def _shortcut(
    source: Box,
    target: Box,
    role: str,
    label: str,
    theme: Theme,
    measurer: TextMeasurer,
    *,
    spoke: bool = False,
) -> tuple[Primitive, ...]:
    """One edge across the ring: a straight run between two steps' outlines.

    Across rather than along, because along is what the ring already means. A
    shortcut drawn as another arc would be indistinguishable from the loop it is
    an exception to; drawn as a chord it reads as what it is — a way of going
    back early, inside the circle the four steps make.

    Its label sits at the middle of the chord, pushed off the line by the same
    daylight every other label keeps, and the whole thing is refused if the
    chord would run through a step it does not join. That refusal is the point
    of drawing this at all: the alternative was a caption saying the loop has an
    exception, which tells the reader it exists without ever showing it.
    """
    start = _outline_point(source, _centre(target))
    finish = _outline_point(target, _centre(source))
    head = theme.edge_roles[role].has_head
    span = math.hypot(finish[0] - start[0], finish[1] - start[1])
    if span <= theme.edge.min_shaft_length:
        raise FitError(
            f"the shortcut between these two steps has {span:.0f} units of room and needs "
            f"{theme.edge.min_shaft_length:.0f} for a visible shaft. Give the diagram more "
            f"width, or shorten the step labels so the ring is bigger."
        )

    towards = ((finish[0] - start[0]) / span, (finish[1] - start[1]) / span)
    tip = finish
    if head:
        back = theme.edge.head_length
        shaft_end = (finish[0] - towards[0] * back, finish[1] - towards[1] * back)
        wing = theme.edge.head_length / 2
        across = (-towards[1] * wing, towards[0] * wing)
        primitives: list[Primitive] = [
            Path(role, points=(start, shaft_end)),
            Polygon(
                role,
                points=(
                    tip,
                    (shaft_end[0] + across[0], shaft_end[1] + across[1]),
                    (shaft_end[0] - across[0], shaft_end[1] - across[1]),
                ),
            ),
        ]
    else:
        primitives = [Path(role, points=(start, finish))]

    if label:
        size = theme.scale["label"]
        extents_of = measurer.measure(label, theme.font.default, size)
        middle = ((start[0] + finish[0]) / 2, (start[1] + finish[1]) / 2)
        normal = (-towards[1], towards[0])
        if spoke:
            # Beside the line by the daylight every label keeps, measured to the
            # label's nearest corner rather than its baseline: a spoke running down
            # the page would otherwise pass through the words centred on it.
            half = abs(normal[0]) * extents_of.width / 2 + abs(normal[1]) * extents_of.height / 2
            away = theme.edge.clearance + half
            drop = (extents_of.ascent - extents_of.descent) / 2
        else:
            # A shortcut's chord lies close along the ring, and a label pushed out
            # that far would land on the arc beside it: its baseline sits off the
            # line by the daylight plus an ascent, inside the ring.
            away = theme.edge.clearance + extents_of.ascent
            drop = 0.0
        primitives.append(
            TextRun(
                role,
                x=middle[0] + normal[0] * away,
                y=middle[1] + normal[1] * away + drop,
                text=label,
                level="label",
                font=theme.font.default,
                anchor="middle",
            )
        )
    return tuple(primitives)


def _centre(box: Box) -> tuple[float, float]:
    return (box.x + box.width / 2, box.y + box.height / 2)


def _outline_point(box: Box, towards: tuple[float, float]) -> tuple[float, float]:
    """Where the line from `box`'s centre to `towards` leaves the box."""
    centre = _centre(box)
    dx, dy = towards[0] - centre[0], towards[1] - centre[1]
    if dx == 0 and dy == 0:
        return centre
    scale = min(
        (box.width / 2) / abs(dx) if dx else math.inf,
        (box.height / 2) / abs(dy) if dy else math.inf,
    )
    return (centre[0] + dx * scale, centre[1] + dy * scale)


def _boxes(
    document: Document, theme: Theme, measurer: TextMeasurer, width: float
) -> dict[str, Box]:
    """One box per node, normalised to a common width: every step is a peer.

    A common *height* is not part of that: the ring already centres each box on
    its own spoke, so a two-word step does not need to be as tall as the
    longest one to look like its equal.
    """
    limit = width * NODE_WIDTH_SHARE
    sized = [
        size_box(
            node.label,
            theme=theme,
            measurer=measurer,
            role=node.role,
            level="body",
            max_width=limit,
            widen=NODE_WIDEN,
            lead=node.lead,
        )
        for node in document.nodes
    ]
    return dict(zip((node.id for node in document.nodes), normalise(sized), strict=True))


def _radius(boxes: dict[str, Box], theme: Theme) -> float:
    """The ring radius its steps alone demand.

    Two constraints, and the radius is the larger of what each demands. The ring
    has to be big enough that adjacent boxes do not touch — that is what the
    chord between two neighbours has to clear — and the arcs between them have to
    be long enough to carry a visible shaft, which is the same minimum-shaft rule
    the layout obeys.
    """
    count = len(boxes)
    box = next(iter(boxes.values()))
    diagonal = math.hypot(box.width, box.height)

    # Chord between neighbours is 2 * r * sin(pi / n); it must clear the boxes.
    separation = diagonal + theme.box.padding.horizontal
    from_spacing = separation / (2 * math.sin(math.pi / count))

    # Arc between neighbours is 2 * pi * r / n; it must leave a visible shaft.
    shaft = theme.edge.min_shaft_length + theme.edge.head_length + diagonal
    from_shaft = shaft * count / (2 * math.pi)

    return max(from_spacing, from_shaft)


def _extent(radius: float, boxes: dict[str, Box], width: float, hub: Box | None) -> float:
    """The square extent the whole figure occupies, which is the canvas width.

    Raises:
        FitError: the ring is wider than the canvas.
    """
    box = next(iter(boxes.values()))
    extent = 2 * radius + max(box.width, box.height)
    if extent > width:
        grown = (
            " It grew to make room for the hub in its middle, so a shorter hub label helps too."
            if hub is not None
            else ""
        )
        raise FitError(
            f"a cycle of {len(boxes)} steps needs {extent:.0f} to draw at this type size, "
            f"and the canvas is {width:.0f}. The ring is sized by its longest label, so: "
            f"shorten the labels, use fewer steps, or give the diagram more width.{grown} "
            f"drawspec will not overlap the steps to make them fit."
        )
    return width


#: How far the ring grows per try while making room for a hub. One unit is
#: below anything a reader can see, and a fixed step keeps the answer — and the
#: bytes — the same on every run.
HUB_GROWTH: Final = 1.0


def _hub_box(hub: Node | None, theme: Theme, measurer: TextMeasurer, width: float) -> Box | None:
    """The hub sized to its own text, with the allowance a step gets."""
    if hub is None:
        return None
    return size_box(
        hub.text,
        theme=theme,
        measurer=measurer,
        role=hub.role,
        level="body",
        max_width=width * NODE_WIDTH_SHARE,
        widen=NODE_WIDEN,
    )


def _around_hub(
    radius: float,
    order: tuple[str, ...],
    boxes: dict[str, Box],
    hub: Box,
    spokes: tuple[tuple[str, str, str, str], ...],
    theme: Theme,
    measurer: TextMeasurer,
    width: float,
) -> float:
    """The smallest radius, from `radius` up, at which the hub sits clear inside the ring.

    Two things have to hold, and the ring grows until both do. The hub must stay
    inside the ring's arcs, with the daylight any route keeps from a box it
    passes; and it must stand clear of every step by the gap peers keep — or, for
    a step a spoke joins, by enough for that spoke to show a shaft and to carry
    its label beside it rather than over either end.

    A ring that would need to grow past the canvas stops here; `_extent` then
    refuses it with the remedies.
    """
    count = len(order)
    inner = theme.edge.clearance + (
        theme.cycle.width / 2 * HEAD_FLARE
        if theme.cycle.connector == "band"
        else theme.edge.head_length / 2
    )
    corner = math.hypot(hub.width / 2, hub.height / 2)
    reach = {node: theme.box.padding.horizontal for node in order}
    for index, node in enumerate(order):
        angle = _angle(index, count)
        towards = (abs(math.cos(angle)), abs(math.sin(angle)))
        for source, target, role, label in spokes:
            if node not in (source, target):
                continue
            need = theme.edge.min_shaft_length + (
                theme.edge.head_length if theme.edge_roles[role].has_head else 0.0
            )
            if label:
                size = measurer.measure(label, theme.font.default, theme.scale["label"])
                along = towards[0] * size.width / 2 + towards[1] * size.height / 2
                need = max(need, 2 * along + 2 * theme.edge.clearance)
            reach[node] = max(reach[node], need + theme.edge.clearance)

    def fits(at: float) -> bool:
        if corner > at - inner:
            return False
        for index, node in enumerate(order):
            angle = _angle(index, count)
            box = boxes[node]
            gap_x = abs(at * math.cos(angle)) - (box.width + hub.width) / 2
            gap_y = abs(at * math.sin(angle)) - (box.height + hub.height) / 2
            if math.hypot(max(gap_x, 0.0), max(gap_y, 0.0)) < reach[node]:
                return False
        return True

    while not fits(radius) and radius < width:
        radius += HUB_GROWTH
    return radius


def _clear_of_hub(
    source: str, target: str, placed: dict[str, Box], hub: Node, theme: Theme
) -> None:
    """Refuse a shortcut whose chord would run through the hub.

    A shortcut is drawn straight across the ring, and the hub is in the middle of
    it: a chord between two steps on opposite sides goes through the very thing
    the loop turns around, and drawn anyway it would read as passing *through*
    it. There is no detour that does not invent a route the author never wrote.

    Raises:
        DrawspecError: the chord crosses the hub's box.
    """
    box = placed[hub.id]
    start, finish = _centre(placed[source]), _centre(placed[target])
    margin = theme.edge.clearance
    left, right = box.x - margin, box.x + box.width + margin
    top, bottom = box.y - margin, box.y + box.height + margin
    # Liang-Barsky: clip the segment against the inflated box.
    low, high = 0.0, 1.0
    dx, dy = finish[0] - start[0], finish[1] - start[1]
    for p, q in (
        (-dx, start[0] - left),
        (dx, right - start[0]),
        (-dy, start[1] - top),
        (dy, bottom - start[1]),
    ):
        if p == 0:
            if q < 0:
                return
            continue
        t = q / p
        if p < 0:
            low = max(low, t)
        else:
            high = min(high, t)
        if low > high:
            return
    raise DrawspecError(
        f"the shortcut from {source!r} to {target!r} would cross the ring through its "
        f"hub, {hub.id!r}, and read as passing through it. Join steps nearer each other "
        f"round the ring, or route the relation through the hub as two spokes."
    )


def _arc(
    centre: tuple[float, float],
    radius: float,
    start_index: int,
    end_index: int,
    count: int,
    box: Box,
    target: Box,
    role: str,
    theme: Theme,
) -> tuple[Primitive, ...]:
    """One arc from node `start_index` to the next, plus its head.

    Both ends are found on the boxes themselves — the angle at which the ring
    leaves the source's outline, and the angle at which it reaches the target's —
    which is the same rule the graph kinds anchor by, said in polar coordinates.

    It replaces a clearance computed from the box's *diagonal*, and the
    difference is the whole drawing rather than a detail. The diagonal is the
    distance to a corner, so an arc approaching a wide flat box side-on stopped a
    half-diagonal short of a border that was a half-*width* away, at both ends,
    on a ring whose radius already guaranteed a clear chord. What was left was a
    stub of arc hanging in the middle of the gap, touching neither step: five
    short curves floating inside a ring that no longer read as a loop at all.
    """
    head_span = theme.edge.head_length / radius
    gap = theme.edge.clearance / radius

    begin = _leaves(centre, radius, _angle(start_index, count), box, theme, forwards=True) + gap
    finish = _leaves(centre, radius, _angle(end_index, count), target, theme, forwards=False) - gap
    if finish <= begin:
        return ()

    head = theme.edge_roles[role].has_head
    if theme.cycle.connector == "band":
        return (_band(centre, radius, begin, finish, role, theme, head=head),)

    last = finish - head_span if head else finish
    points = tuple(
        _on_circle(centre, radius, begin + (last - begin) * step / ARC_SEGMENTS)
        for step in range(ARC_SEGMENTS + 1)
    )
    shaft = Path(role, points=points)

    if not head:
        return (shaft,)
    return (shaft, _head(centre, radius, finish, head_span, role, theme))


def _band(
    centre: tuple[float, float],
    radius: float,
    begin: float,
    finish: float,
    role: str,
    theme: Theme,
    *,
    head: bool,
) -> Polygon:
    """One connector drawn as a broad tapered ribbon — the recycling mark.

    A single closed figure rather than a shaft plus a head, because that is what
    it is: the outer edge runs from the start of the arc to the shoulder, out to
    the wide point of the head, in to the tip, back out along the inner shoulder,
    and home along the inner edge. Drawn in one piece, the taper is continuous
    and there is no seam where a stroked shaft would meet a filled triangle.

    It is filled with the edge's own colour and not outlined, which is what the
    emitter already does with an arrow head — a head is the same weight as its
    shaft whatever the theme says, and a band is a head that goes all the way
    round.
    """
    half = theme.cycle.width / 2
    # The head's span along the arc is proportional to how wide it is, so a
    # ribbon and a thin arrow are the same shape at two sizes.
    span = (theme.cycle.width * ARROW_ASPECT) / radius if head else 0.0
    shoulder = max(begin, finish - span)

    def along(offset: float, start: float, end: float) -> tuple[tuple[float, float], ...]:
        return tuple(
            _on_circle(centre, radius + offset, start + (end - start) * step / ARC_SEGMENTS)
            for step in range(ARC_SEGMENTS + 1)
        )

    if not head:
        return Polygon(role, points=(*along(half, begin, finish), *along(-half, finish, begin)))
    return Polygon(
        role,
        points=(
            *along(half, begin, shoulder),
            _on_circle(centre, radius + half * HEAD_FLARE, shoulder),
            _on_circle(centre, radius, finish),
            _on_circle(centre, radius - half * HEAD_FLARE, shoulder),
            *along(-half, shoulder, begin),
        ),
    )


def _leaves(
    centre: tuple[float, float],
    radius: float,
    angle: float,
    box: Box,
    theme: Theme,
    *,
    forwards: bool,
) -> float:
    """The angle at which the ring crosses `box`'s outline, leaving it.

    Bisection rather than algebra: the crossing is with a rectangle, so there are
    four cases and two of them are degenerate, and a fixed number of halvings is
    both exact enough at these sizes and — the property that matters — the same
    number on every run.

    The node's own angle is inside the box by construction (its centre is on the
    ring there) and a quarter turn away is outside it, because the radius was
    chosen so a whole box fits in the chord between neighbours.
    """
    step = 1.0 if forwards else -1.0
    low, high = 0.0, math.pi / 2
    for _ in range(_BISECTIONS):
        middle = (low + high) / 2
        if _inside(_on_circle(centre, radius, angle + step * middle), box):
            low = middle
        else:
            high = middle
    return angle + step * high


def _inside(point: tuple[float, float], box: Box) -> bool:
    return box.x <= point[0] <= box.x + box.width and box.y <= point[1] <= box.y + box.height


def _head(
    centre: tuple[float, float],
    radius: float,
    tip_angle: float,
    head_span: float,
    role: str,
    theme: Theme,
) -> Polygon:
    """A triangular head at the end of an arc, pointing the way the arc runs."""
    tip = _on_circle(centre, radius, tip_angle)
    back = tip_angle - head_span
    half = theme.edge.head_length / 2
    return Polygon(
        role,
        points=(
            tip,
            _on_circle(centre, radius + half, back),
            _on_circle(centre, radius - half, back),
        ),
    )


def _on_circle(centre: tuple[float, float], radius: float, angle: float) -> tuple[float, float]:
    return centre[0] + radius * math.cos(angle), centre[1] + radius * math.sin(angle)


__all__ = [
    "ARC_SEGMENTS",
    "MINIMUM_NODES",
    "NODE_WIDEN",
    "NODE_WIDTH_SHARE",
    "START_ANGLE",
    "cycle_scene",
]

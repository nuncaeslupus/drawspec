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
from drawspec.scene import Path, Polygon, Primitive, Scene, extents, moved
from drawspec.schema import Document
from drawspec.text.measure import TextMeasurer
from drawspec.theme import Theme

#: Where the first node sits: the top of the circle, reading clockwise, which is
#: how a clock face and every cycle diagram in the corpus are read.
START_ANGLE: Final = -math.pi / 2

#: How much of the canvas width a cycle's node boxes may take. A node wider than
#: this leaves no room for the ring itself.
NODE_WIDTH_SHARE: Final = 0.34

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
    radius, extent = _radius(boxes, theme, width)

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
    for node_id in order:
        primitives.extend(box_primitives(placed[node_id], theme, measurer))

    # Framed against the ink rather than against the steps: with five steps the
    # lowest point of the drawing is the bottom of the arc *between* the two
    # lowest boxes, and a canvas measured from the boxes cuts that arc in half.
    margin = theme.box.padding.top
    _, top, _, bottom = extents(primitives)
    shift = margin - top
    primitives = [moved(primitive, 0.0, shift) for primitive in primitives]
    centre = (centre[0], centre[1] + shift)

    return Scene(
        width=extent,
        height=bottom + shift + margin,
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

    Raises:
        DrawspecError: the edges do not form one closed loop through every node.
    """
    following: dict[str, str] = {}
    for edge in document.edges:
        if edge.source in following:
            raise DrawspecError(
                f"node {edge.source!r} has more than one outgoing edge. A cycle is one "
                f"loop: every step has exactly one next step."
            )
        following[edge.source] = edge.target

    identifiers = [node.id for node in document.nodes]
    if len(document.edges) != len(identifiers):
        raise DrawspecError(
            f"a cycle of {len(identifiers)} nodes needs {len(identifiers)} edges to "
            f"close the loop; this one has {len(document.edges)}."
        )

    start = identifiers[0]
    order = [start]
    seen = {start}
    current = start
    while len(order) < len(identifiers):
        target = following.get(current)
        if target is None:
            raise DrawspecError(f"node {current!r} has no outgoing edge, so the loop is open")
        if target in seen:
            raise DrawspecError(
                f"the edges close back to {target!r} before reaching every node, so this "
                f"is a shorter loop with extra nodes beside it rather than one cycle"
            )
        order.append(target)
        seen.add(target)
        current = target

    if following.get(order[-1]) != start:
        raise DrawspecError(
            f"the last step {order[-1]!r} does not return to {start!r}, so the loop is open"
        )
    return tuple(order)


def _edge_role(document: Document, source: str, target: str) -> str:
    for edge in document.edges:
        if edge.source == source and edge.target == target:
            return edge.role
    return "flow"


def _boxes(
    document: Document, theme: Theme, measurer: TextMeasurer, width: float
) -> dict[str, Box]:
    """One box per node, all normalised: every step in a cycle is a peer."""
    limit = width * NODE_WIDTH_SHARE
    sized = [
        size_box(
            node.text, theme=theme, measurer=measurer, role=node.role, level="body", max_width=limit
        )
        for node in document.nodes
    ]
    return dict(zip((node.id for node in document.nodes), normalise(sized), strict=True))


def _radius(boxes: dict[str, Box], theme: Theme, width: float) -> tuple[float, float]:
    """The ring radius, and the square extent the whole figure occupies.

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

    radius = max(from_spacing, from_shaft)
    extent = 2 * radius + max(box.width, box.height)

    if extent > width:
        raise FitError(
            f"a cycle of {count} steps needs {extent:.0f} to draw at this type size, and "
            f"the canvas is {width:.0f}. The ring is sized by its longest label, so: "
            f"shorten the labels, use fewer steps, or give the diagram more width. "
            f"drawspec will not overlap the steps to make them fit."
        )
    return radius, width


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


__all__ = ["ARC_SEGMENTS", "MINIMUM_NODES", "NODE_WIDTH_SHARE", "START_ANGLE", "cycle_scene"]

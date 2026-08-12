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
from drawspec.scene import Path, Polygon, Primitive, Scene
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

#: The smallest cycle that can be drawn. Two nodes is a pair of arcs there and
#: back, which does read as a loop; one node is not a cycle at all.
MINIMUM_NODES: Final = 2


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

    centre = extent / 2
    placed = {
        node_id: boxes[node_id].moved_to(
            centre + radius * math.cos(_angle(index, len(order))) - boxes[node_id].width / 2,
            centre + radius * math.sin(_angle(index, len(order))) - boxes[node_id].height / 2,
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
            _arc(centre, radius, index, index + 1, len(order), placed[node_id], role, theme)
        )
    for node_id in order:
        primitives.extend(box_primitives(placed[node_id], theme, measurer))

    return Scene(
        width=extent,
        height=extent,
        primitives=tuple(primitives),
        title=document.title,
        description=document.description,
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
    centre: float,
    radius: float,
    start_index: int,
    end_index: int,
    count: int,
    box: Box,
    role: str,
    theme: Theme,
) -> tuple[Primitive, ...]:
    """One arc from node `start_index` to the next, plus its head.

    The arc stops short of the target node by the box's own reach, so the head
    lands beside the box rather than under it. Border anchoring proper is T9's
    work for the graph kinds; a ring is regular enough to do it with one angle.
    """
    span = 2 * math.pi / count
    # How much angle to leave at each end, so the arc starts and finishes clear
    # of the boxes rather than inside them.
    #
    # The angle a box subtends from the centre is *not* the right number: two
    # points that angle apart on the ring are a chord apart, and the chord is
    # shorter than the arc. Solving on the chord instead — 2r sin(t/2) >= reach —
    # is what actually puts the arc's end outside the box's own circle.
    #
    # The radius was chosen so the chord between neighbours clears a whole box,
    # which puts this below half a sector by construction; the cap is a safety
    # net for the degenerate cases, not a constraint on the normal ones.
    reach = math.hypot(box.width, box.height) / 2
    clearance = min(2 * math.asin(min(reach / (2 * radius), 1.0)), span * 0.45)
    head_span = theme.edge.head_length / radius

    begin = _angle(start_index, count) + clearance
    finish = _angle(end_index, count) - clearance
    if finish <= begin:
        return ()

    points = tuple(
        _on_circle(centre, radius, begin + (finish - head_span - begin) * step / ARC_SEGMENTS)
        for step in range(ARC_SEGMENTS + 1)
    )
    shaft = Path(role, points=points)

    if not theme.edge_roles[role].has_head:
        return (shaft,)
    return (shaft, _head(centre, radius, finish, head_span, role, theme))


def _head(
    centre: float, radius: float, tip_angle: float, head_span: float, role: str, theme: Theme
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


def _on_circle(centre: float, radius: float, angle: float) -> tuple[float, float]:
    return centre + radius * math.cos(angle), centre + radius * math.sin(angle)


__all__ = ["ARC_SEGMENTS", "MINIMUM_NODES", "NODE_WIDTH_SHARE", "START_ANGLE", "cycle_scene"]

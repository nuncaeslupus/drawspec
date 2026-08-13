"""The graph kinds: `flow` and `tree`. Where every stage meets.

This family is the one that uses the whole tool at once — measurement sizes the
boxes, an engine places them, routing joins them, placement puts the labels
somewhere none of that is — so it is mostly assembly, and the assembly order is
the interesting part.

**Sizes before positions.** The engine is given boxes that already fit their
text, and never sees a word. That is what the `LayoutEngine` protocol is for, and
it is why a graph cannot end up with text overflowing a box the engine chose the
size of: nothing chooses a box size but the text in it.

**Direction is chosen, not assumed.** `best_layout` lays the graph out both ways
and takes the one that fits the width. That is the theme requirements' rule 2 —
if the arrows do not fit horizontally the diagram goes vertical — and it happens
before any arrow is drawn, because the remedy is the arrangement rather than a
shorter arrow.

**Nothing fits by shrinking a gap.** When neither direction fits, this raises
`FitError` and `render` retries the whole diagram at a smaller type scale; when
the band is exhausted the author is told to restructure. The rank gap is floored
at what routing demands for a visible shaft, and no path here can lower it.

`cycle` is a graph kind to the schema and is not rendered here — D-1 moved it to
a parametric template, because a cycle through a layered engine comes out as a
column of boxes with a line down the side.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Final

from drawspec.errors import DrawspecError, FitError
from drawspec.geometry import Box, normalise, size_box
from drawspec.kinds.common import box_primitives
from drawspec.kinds.containers import (
    Frame,
    arrange,
    border_obstacles,
    caption_obstacle,
    captions_for,
    crossed,
    frame_primitives,
    nesting_of,
)
from drawspec.layout import Layout, Spacing
from drawspec.routing import (
    Connector,
    Label,
    Obstacle,
    Route,
    edge_primitives,
    label_primitives,
    minimum_rank_gap,
    place_labels,
    route_edges,
)
from drawspec.scene import Primitive, Scene
from drawspec.schema import Document
from drawspec.text.measure import TextMeasurer
from drawspec.theme import Theme

#: The graph kinds this family draws. `cycle` is the third by the schema and
#: belongs to `drawspec.kinds.cycle` — see D-1.
DRAWN_KINDS: Final = ("flow", "tree")

#: How much of the canvas width one node box may take: a quarter, so four ranks
#: fit beside each other with their gaps. A graph that has to go `right` to fit
#: is the case this number is for — three ranks and two gaps is the least that
#: reads as a graph rather than a list, and the reference tree needs all four.
#: Wider boxes are not more readable here; they are the reason a diagram ends up
#: a single column of full-width sentences.
NODE_WIDTH_SHARE: Final = 0.25

#: Which way each kind reads when both directions fit. A flow chart is read down
#: the page; a tree of one-line labels is usually wider than it is tall, but its
#: hierarchy still reads downwards, so both prefer `down` and let the width
#: decide.
PREFERRED_DIRECTION: Final = "down"


@dataclass(frozen=True)
class GraphDrawing:
    """Everything a graph scene is made of, before it becomes primitives.

    Kept as a value of its own rather than inlined into `graph_scene` because it
    is what a test can ask questions of: whether a child's rank really is deeper
    than its parent is a question about the layout, and it should not have to be
    inferred from the coordinates of a text run.
    """

    layout: Layout
    boxes: Mapping[str, Box]
    routes: tuple[Route, ...]
    labels: tuple[Label, ...]
    width: float
    height: float
    frames: tuple[Frame, ...] = ()
    """The group containers, outermost first — empty when the author declared none."""


def graph_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Render a `flow` or `tree` document to a `Scene`.

    Raises:
        DrawspecError: the document is not one this family draws.
        FitError: the graph does not fit its width in either direction at this
            type scale. `render` catches this and tries a smaller one.
    """
    drawing = graph_drawing(document, theme, measurer)

    primitives: list[Primitive] = []
    # Frames first of all — a container is behind what it contains, and its
    # dashed border must never sit on top of a box or a route.
    for frame in drawing.frames:
        primitives.extend(frame_primitives(frame, theme, measurer))
    # Lines next, then boxes over them, then labels over everything: a route
    # arrives at a border, so whichever is drawn second owns the join, and it
    # should be the box.
    for route in drawing.routes:
        primitives.extend(edge_primitives(route, theme))
    for identifier in sorted(drawing.boxes):
        primitives.extend(box_primitives(drawing.boxes[identifier], theme, measurer))
    for label in drawing.labels:
        primitives.extend(label_primitives(label))

    return Scene(
        width=drawing.width,
        height=drawing.height,
        primitives=tuple(primitives),
        title=document.title,
        description=document.description,
        metadata=(("direction", drawing.layout.direction),),
    )


def graph_drawing(document: Document, theme: Theme, measurer: TextMeasurer) -> GraphDrawing:
    """Size, place, route and label — the whole graph, in scene coordinates."""
    if document.kind == "cycle":
        raise DrawspecError(
            "a cycle is drawn as a parametric template rather than as a graph layout — "
            "see drawspec.kinds.cycle, and D-1 for why"
        )
    if document.kind not in DRAWN_KINDS:
        raise DrawspecError(f"{document.kind!r} is not a graph kind")
    if not document.nodes:
        raise DrawspecError(f"a {document.kind} needs at least one node")

    width = document.width if document.width else theme.canvas.width
    margin = theme.box.padding.horizontal
    boxes = _sized(document, theme, measurer, width * NODE_WIDTH_SHARE)

    nesting = nesting_of(document)
    spacing = _spacing(theme)
    arrangement = arrange(
        nesting.roots,
        nesting,
        [(edge.source, edge.target) for edge in document.edges],
        boxes,
        captions_for(document, nesting, theme, measurer, width * NODE_WIDTH_SHARE),
        theme,
        spacing,
        max_width=width - margin * 2,
        prefer=PREFERRED_DIRECTION,
        entered=crossed([(edge.source, edge.target) for edge in document.edges], nesting),
    )
    # The top level's own layout, with every leaf from every level in it — the
    # ranks and reversed edges are the top level's, which is what a caller
    # asking about ranks means by the question.
    layout = replace(arrangement.layout, placements=arrangement.places)
    if not layout.fits:
        raise FitError(
            f"this {document.kind} needs {layout.width + margin * 2:.0f} at its narrowest "
            f"and the canvas is {width:.0f}. Both directions were tried. Shorten the "
            f"longest label, split the diagram, or give it more width — drawspec will not "
            f"overlap the boxes or shorten the arrows to make it fit."
        )

    shapes = {node.id: theme.roles[node.role].shape for node in document.nodes}
    obstacles = tuple(
        Obstacle(
            identifier,
            x=place.x,
            y=place.y,
            width=place.width,
            height=place.height,
            shape=shapes[identifier],
        )
        for identifier, place in sorted(layout.placements.items())
    )
    routes = route_edges(
        tuple(
            Connector(edge.source, edge.target, role=edge.role, label=edge.label)
            for edge in document.edges
        ),
        # Frames do not obstruct — an edge into a group must cross its border —
        # but a frame's caption does, so an arrow arriving from above comes in
        # beside the words rather than through them.
        (
            *obstacles,
            *(blocked for frame in arrangement.frames for blocked in caption_obstacle(frame)),
        ),
        theme,
        direction=layout.direction,
    )
    # Labels avoid the frames as well as the boxes — only the frames' borders,
    # so a label belonging to an edge inside a group can still sit inside it.
    labels = place_labels(
        routes,
        (
            *obstacles,
            *(border for frame in arrangement.frames for border in border_obstacles(frame, theme)),
        ),
        theme,
        measurer,
    )

    return _framed(layout, boxes, obstacles, routes, labels, margin, arrangement.frames)


def _spacing(theme: Theme) -> Spacing:
    """The gaps the engine must leave.

    `rank_gap` is floored at what routing demands rather than at anything chosen
    here: the minimum shaft length is a layout constraint, and this is the line
    where it becomes one.
    """
    return Spacing(
        node_gap=theme.box.padding.horizontal,
        rank_gap=max(minimum_rank_gap(theme), theme.box.padding.horizontal * 2),
    )


def _sized(
    document: Document, theme: Theme, measurer: TextMeasurer, limit: float
) -> dict[str, Box]:
    """One box per node, with peers normalised to a common size.

    Peers here are nodes sharing a role, which is the best available stand-in for
    "the same kind of thing" before ranks exist — the layout has not run yet, so
    rank-based normalisation is not available, and normalising afterwards would
    invalidate the positions it was computed from.
    """
    boxes = {
        node.id: size_box(
            node.text,
            theme=theme,
            measurer=measurer,
            role=node.role,
            level="body",
            max_width=limit,
        )
        for node in document.nodes
    }
    by_role: dict[str, list[str]] = {}
    for node in document.nodes:
        by_role.setdefault(node.role, []).append(node.id)
    for identifiers in by_role.values():
        for identifier, box in zip(
            identifiers, normalise([boxes[i] for i in identifiers]), strict=True
        ):
            boxes[identifier] = box
    return boxes


def _framed(
    layout: Layout,
    boxes: Mapping[str, Box],
    obstacles: Sequence[Obstacle],
    routes: Sequence[Route],
    labels: Sequence[Label],
    margin: float,
    frames: Sequence[Frame] = (),
) -> GraphDrawing:
    """Shift everything so the drawing starts at the margin, and measure it.

    The layout's own extents are not the drawing's: a back edge routed around the
    outside and a label placed to the left of the leftmost box both live outside
    them, and either would be clipped by a canvas sized to the boxes alone. So
    the frame is taken from what was actually produced.
    """
    xs: list[float] = []
    ys: list[float] = []
    for box in obstacles:
        xs += [box.x, box.right]
        ys += [box.y, box.bottom]
    for route in routes:
        xs += [point[0] for point in route.points]
        ys += [point[1] for point in route.points]
    for label in labels:
        xs += [label.left, label.left + label.width]
        ys += [label.top, label.top + label.height]
    for frame in frames:
        xs += [frame.x, frame.right]
        ys += [frame.y, frame.bottom]

    offset_x = margin - min(xs, default=0.0)
    offset_y = margin - min(ys, default=0.0)
    return GraphDrawing(
        layout=layout,
        boxes={
            identifier: boxes[identifier]
            .resized(width=place.width, height=place.height)
            .moved_to(place.x + offset_x, place.y + offset_y)
            for identifier, place in layout.placements.items()
        },
        routes=tuple(
            replace(
                route,
                points=tuple((x + offset_x, y + offset_y) for x, y in route.points),
            )
            for route in routes
        ),
        labels=tuple(
            replace(label, left=label.left + offset_x, top=label.top + offset_y) for label in labels
        ),
        width=max(xs, default=0.0) + offset_x + margin,
        height=max(ys, default=0.0) + offset_y + margin,
        frames=tuple(frame.moved(offset_x, offset_y) for frame in frames),
    )


__all__ = [
    "DRAWN_KINDS",
    "NODE_WIDTH_SHARE",
    "PREFERRED_DIRECTION",
    "GraphDrawing",
    "graph_drawing",
    "graph_scene",
]

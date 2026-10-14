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

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from functools import partial
from itertools import pairwise
from types import MappingProxyType
from typing import Final

from drawspec.errors import DrawspecError, FitError
from drawspec.filetree import STATUS_MARKS
from drawspec.geometry import Box, normalise, size_box
from drawspec.kinds.common import (
    DRAWN_MARKS,
    box_primitives,
    painted,
    status_box_primitives,
    status_key,
    status_size,
    status_words,
)
from drawspec.kinds.containers import (
    GROUP_ROLE,
    Arrangement,
    Frame,
    Nesting,
    arrange,
    border_obstacles,
    caption_obstacle,
    captions_for,
    crossed,
    frame_anchors,
    frame_primitives,
    nesting_of,
    region_dividers,
    region_separators,
    separator_obstacles,
)
from drawspec.kinds.lanes import Swimlanes, lanes_arrangement, lanes_primitives
from drawspec.layout import Layout, Placement, Spacing
from drawspec.legend import SWATCH_ROLE, Entry, height_of, primitives_for, width_of
from drawspec.routing import (
    BAR_SHAPE,
    LOOP_SIDES,
    Connector,
    Label,
    Loop,
    Obstacle,
    Route,
    claimed_sides,
    edge_primitives,
    goes_round,
    label_extents,
    label_primitives,
    loop_label_size,
    loop_margin,
    loop_sides,
    minimum_rank_gap,
    place_labels,
    place_loop,
    route_edges,
)
from drawspec.scene import Ellipse, Path, Polygon, Primitive, Scene, TextLine, TextSpan, moved
from drawspec.schema import STATE_BARS, Band, Document, Edge, Node
from drawspec.text.measure import TextMeasurer
from drawspec.text.wrap import TextBlock, wrap
from drawspec.textgrid import (
    STRAIGHT,
    Drawn,
    box_glyphs,
    boxed,
    caption_lines,
    cells,
    finished,
    label_lines,
    line_style,
    plain,
    spelt,
    widest,
)
from drawspec.theme import POLARITY_GLYPHS, Theme

#: The kinds this family draws. `cycle` is a graph kind by the schema and
#: belongs to `drawspec.kinds.cycle` — see D-1. `states` is not a graph kind to
#: the schema, which parses its states and transitions into nodes and edges; it
#: is drawn here with its pseudo-states added as dots (see `_with_pseudo_states`).
#: Nor is `lanes`, whose nodes are laid out in strips by `kinds.lanes` and then
#: routed and labelled here like any flow's.
DRAWN_KINDS: Final = ("flow", "tree", "states", "lanes")

#: How much of the canvas width one node box may take: a quarter, so four ranks
#: fit beside each other with their gaps. A graph that has to go `right` to fit
#: is the case this number is for — three ranks and two gaps is the least that
#: reads as a graph rather than a list, and the reference tree needs all four.
#: Wider boxes are not more readable here; they are the reason a diagram ends up
#: a single column of full-width sentences.
NODE_WIDTH_SHARE: Final = 0.25

#: How far past that share a box may go when its own shape has made it taller
#: than it is wide. Twice, so no node ever takes more than half the canvas — and
#: only ever in exchange for fewer lines, which is what `size_box`'s `widen`
#: enforces. This is where the corpus's tallest boxes came from: a nine-line
#: pill spends most of a quarter-canvas allowance on its own caps.
NODE_WIDEN: Final = 2.0

#: Which way each kind reads when both directions fit. A flow chart is read down
#: the page; a tree of one-line labels is usually wider than it is tall, but its
#: hierarchy still reads downwards, so both prefer `down` and let the width
#: decide.
PREFERRED_DIRECTION: Final = "down"


#: How many label lines a `states` drawing adds to the gap between ranks.
STATES_LABEL_LINES: Final = 2

#: The role a band's bar is drawn in. A band is not a relation between two boxes,
#: so it has no head and no direction — which is what `link` means, and the same
#: reasoning that makes a timeline's axis a `link`.
BAND_ROLE: Final = "link"

#: The role a band's name is tagged with. A `TextRun` takes no styling from its
#: role — its level and font decide how it is set — but every primitive must carry
#: a role the theme declares, and there is no role for "furniture".
BAND_TEXT_ROLE: Final = "step"


@dataclass(frozen=True)
class BandBar:
    """One band, placed: a bar beside the boxes it accompanies, and its name.

    The name sits *beside* the bar rather than on it, on the far side from the
    drawing. A gate breaks its divider to let its name through because a gate's
    name belongs to the threshold itself; a band's name belongs to the whole
    length of it, and outside is where there is room for the words.

    Room for the words, and no more: the name is broken to the **length of its
    own bar**, which is the same promise the bar itself makes. A band says *this
    runs alongside these boxes*, so a name that ran past the last of them would
    be claiming boxes the band does not have; and one that ran past the canvas —
    which is what an unbroken name did — would not be on the page at all.

    `label_x` and `label_y` anchor the wrapped block rather than a baseline: the
    block's top and centre for a bar drawn across the page, its left edge and
    centre for one drawn down it. `block` is what makes the extent knowable, and
    the extent is what `_framed` needs — a canvas measured from an anchor point
    is a canvas that clips every word around it.
    """

    text: str
    points: tuple[tuple[float, float], ...]
    block: TextBlock
    label_x: float
    label_y: float
    rotate: float = 0.0

    def moved(self, dx: float, dy: float) -> BandBar:
        return replace(
            self,
            points=tuple((x + dx, y + dy) for x, y in self.points),
            label_x=self.label_x + dx,
            label_y=self.label_y + dy,
        )

    @property
    def label_box(self) -> tuple[float, float, float, float]:
        """The name's bounds — left, top, right, bottom — after any rotation.

        Turned a quarter turn, a block's *height* is what it takes across the
        page and its *width* is what it takes down it, which is the swap a
        canvas sized from the unrotated block would get backwards.
        """
        if self.rotate:
            return (
                self.label_x,
                self.label_y - self.block.width / 2,
                self.label_x + self.block.height,
                self.label_y + self.block.width / 2,
            )
        return (
            self.label_x - self.block.width / 2,
            self.label_y,
            self.label_x + self.block.width / 2,
            self.label_y + self.block.height,
        )


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

    bands: tuple[BandBar, ...] = ()
    """The bands, in declaration order — empty when the author declared none."""

    markers: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))
    """Pseudo-state id → `initial` or `final`: the boxes drawn as dots, not boxes.
    Empty for everything but a `states` document."""

    offset: tuple[float, float] = (0.0, 0.0)
    """How far everything was shifted to start the drawing at its own ink."""

    loops: tuple[Loop, ...] = ()
    """The self-loops, placed — their routes and labels are also in `routes` and
    `labels`, so this is for asking which side each took."""

    lanes: Swimlanes | None = None
    """A `lanes` document's strips and headings; `None` for every other kind."""


def graph_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Render a `flow` or `tree` document to a `Scene`.

    Raises:
        DrawspecError: the document is not one this family draws.
        FitError: the graph does not fit its width in either direction at this
            type scale. `render` catches this and tries a smaller one.
    """
    drawing = graph_drawing(document, theme, measurer)

    primitives: list[Primitive] = []
    # Lanes behind everything: a strip is the paper a party's steps are drawn on.
    if drawing.lanes is not None:
        primitives.extend(lanes_primitives(drawing.lanes, theme, measurer))
    # Frames first of all — a container is behind what it contains, and its
    # dashed border must never sit on top of a box or a route.
    for frame in drawing.frames:
        primitives.extend(frame_primitives(frame, theme, measurer))
    # A composite state's regions are divided by dashed lines, in the frame's role.
    primitives.extend(Path(GROUP_ROLE, points=line) for line in region_separators(drawing.frames))
    # Lines next, then boxes over them, then labels over everything: a route
    # arrives at a border, so whichever is drawn second owns the join, and it
    # should be the box.
    for route in drawing.routes:
        primitives.extend(edge_primitives(route, theme))
    status = {node.id: node.status for node in document.nodes}
    fills = class_fills(document, theme)
    for identifier in sorted(drawing.boxes):
        box = drawing.boxes[identifier]
        if identifier in drawing.markers:
            primitives.extend(marker_primitives(box, drawing.markers[identifier], theme))
        elif status.get(identifier):
            primitives.extend(status_box_primitives(box, status[identifier], theme, measurer))
        elif identifier in fills:
            # A class is a fill on the box's own outline: its inner lines and its
            # words are drawn as they always are, over it.
            primitives.extend(
                painted(part, *fills[identifier]) for part in box_primitives(box, theme, measurer)
            )
        else:
            primitives.extend(box_primitives(box, theme, measurer))
    for label in drawing.labels:
        primitives.extend(label_primitives(label))
    # Bands last: they sit outside the boxes, so nothing is over them, and the
    # clearance pass has the whole scene either way.
    for bar in drawing.bands:
        primitives.extend(band_primitives(bar, theme))

    width, height = drawing.width, drawing.height
    # A causal loop diagram's delay marks and loop markers, over everything else.
    if document.loops or any(edge.delay for edge in document.edges):
        from drawspec.kinds.loops import causal_drawing  # it imports this module

        causal = causal_drawing(document, drawing, theme, measurer)
        primitives.extend(causal.primitives)
        rects = [rect for marker in causal.markers for rect in marker.footprint]
        top = min((rect[1] for rect in rects), default=0.0)
        if top < 0:
            primitives = [moved(primitive, 0.0, -top) for primitive in primitives]
            height -= top
        height = max(height, *(rect[3] - min(top, 0.0) for rect in rects), 0.0)
    # The key of a drawing of a change: the tags of every status used, under it.
    # Only when an edge carries one — a box's own tag already says its word, and
    # it is the bare `+` on a line that needs a key to be read.
    if any(edge.status for edge in document.edges):
        used = {node.status for node in document.nodes} | {e.status for e in document.edges}
        top = height + theme.box.padding.top
        key, row, tall = status_key(used - {""}, top, max(width, 0.0), theme, measurer)
        if row > width:
            across = (row - width) / 2
            primitives = [moved(primitive, across, 0.0) for primitive in primitives]
            key = tuple(moved(primitive, across, 0.0) for primitive in key)
            width = row
        primitives.extend(key)
        height = top + tall

    # The key of the classes: every class's fill beside its name, in the order
    # declared, under the drawing (and under a change's key), as a matrix's is.
    if document.classes:
        # Laid out across the canvas rather than the drawing, so a narrow drawing
        # keeps its key on one row: a key wider than the drawing widens it, and
        # the drawing moves to stay centred over the key.
        legend = class_key(document, theme)
        canvas = document.width if document.width else theme.canvas.width
        across = max(width, canvas, 0.0)
        row = width_of(legend, theme, measurer, across)
        if row > width:
            shift = (row - width) / 2
            primitives = [moved(primitive, shift, 0.0) for primitive in primitives]
            width = row
        left = (width - row) / 2
        primitives.extend(primitives_for(legend, theme, measurer, left, height, width))
        height += height_of(legend, theme, measurer, width)

    return Scene(
        width=width,
        height=height,
        primitives=tuple(primitives),
        title=document.title,
        description=document.description,
        metadata=(("direction", drawing.layout.direction),),
    )


def class_fills(document: Document, theme: Theme) -> dict[str, tuple[str, str, float]]:
    """Each classed node's fill, ink and opacity, from its class's place in `classes`."""
    order = {entry.id: index for index, entry in enumerate(document.classes)}
    return {
        node.id: theme.classes.fill_for(order[node.klass])
        for node in document.nodes
        if node.klass in order
    }


def class_key(document: Document, theme: Theme) -> tuple[Entry, ...]:
    """The key of a drawing's classes: one swatch and name per class, as declared."""
    return tuple(
        Entry(entry.text, SWATCH_ROLE, *theme.classes.fill_for(index))
        for index, entry in enumerate(document.classes)
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

    document, markers = _with_pseudo_states(document)
    width = document.width if document.width else theme.canvas.width
    nesting = nesting_of(document)
    # A lanes drawing sizes its boxes again for each orientation it tries: see
    # `kinds.lanes.lanes_arrangement`. These are what its loops are measured on.
    boxes = _sized(document, theme, measurer, width * NODE_WIDTH_SHARE, nesting, markers)
    spacing = _spacing(theme)
    if document.kind == "states":
        # Every transition of a state machine is labelled, and a label with a
        # guard or an action is two or three lines: the gap between ranks holds
        # one, so it can sit beside its own line clear of everyone else's.
        _, tall, _, _ = label_extents("\n".join(["|"] * STATES_LABEL_LINES), theme, measurer)
        spacing = replace(spacing, rank_gap=spacing.rank_gap + tall)
    if document.loops:
        # A causal loop's marker goes inside the loop, and between two ranks is
        # where a loop has room: a ring and a two-line name under it.
        spacing = replace(
            spacing,
            rank_gap=spacing.rank_gap + LOOP_ROOM * theme.scale["body"],
            turn_gap=spacing.rank_gap,
        )
    pairs = [(edge.source, edge.target) for edge in document.edges]
    captions = captions_for(document, nesting, theme, measurer, width * NODE_WIDTH_SHARE)
    looped = _loops(document)
    labels_of = {
        identifier: [loop_label_size(edge.label, theme, measurer) for edge in edges]
        for identifier, edges in looped.items()
    }

    # A self-loop is not an edge to the ranker: it is part of its box's extent.
    # Which part depends on which way the box's own level reads — the loop goes
    # across that direction — and the direction is chosen by the layout, so the
    # room is reserved for the preferred one and the layout run again for any box
    # whose level came out the other way, keeping what was reserved before. Two
    # directions, so it settles within three runs and what is drawn always has
    # its room.
    reserved = {identifier: {PREFERRED_DIRECTION} for identifier in looped}
    for _ in range(3):
        margins = {
            identifier: _loop_margins(boxes[identifier], labels_of[identifier], ways, theme)
            for identifier, ways in reserved.items()
        }
        inflated = _grown(boxes, margins)
        if document.kind == "lanes":
            arrangement, swimlanes, boxes = lanes_arrangement(
                document,
                lambda limit: _sized(document, theme, measurer, limit, nesting, markers, 1.0),
                partial(_grown, margins=dict(margins)),
                theme,
                measurer,
                spacing,
                max_width=width,
                max_height=(document.height or 0.0) if document.height_binding else 0.0,
            )
        else:
            swimlanes = None
            arrangement = _arranged(
                partial(
                    arrange,
                    nesting.roots,
                    nesting,
                    pairs,
                    inflated,
                    captions,
                    theme,
                    spacing,
                    max_width=width,
                    entered=crossed(pairs, nesting),
                    centre=next((node.id for node in document.nodes if node.centre), ""),
                    # A binding height is the only thing that can make a chain read across
                    # rather than down: see `layout.base.best_layout`. An advisory height is
                    # not passed, because it is advisory.
                    max_height=(document.height or 0.0) if document.height_binding else 0.0,
                    room=_region_room(document, nesting, inflated, theme, measurer),
                    turning=_bar_ends(document, markers),
                ),
                bool(nesting.regions),
                (document.height or 0.0) if document.height_binding else 0.0,
            )
        missing = {
            identifier
            for identifier in looped
            if arrangement.directions.get(identifier, PREFERRED_DIRECTION)
            not in reserved[identifier]
        }
        if not missing:
            break
        for identifier in missing:
            reserved[identifier].add(arrangement.directions[identifier])
    # The top level's own layout, with every leaf from every level in it — the
    # ranks and reversed edges are the top level's, which is what a caller
    # asking about ranks means by the question. A box with a loop gets its own
    # extent back; the room around it stays empty for the loop.
    places = dict(arrangement.places)
    for identifier, (across, down) in margins.items():
        place = places[identifier]
        places[identifier] = replace(
            place,
            x=place.x + across,
            y=place.y + down,
            width=place.width - across * 2,
            height=place.height - down * 2,
        )
    if markers:
        places = _pulled_in(
            places, markers, document.edges, arrangement, _spacing(theme), spacing.node_gap
        )
    places, ports = _spanned_bars(places, markers, document.edges, arrangement, theme, spacing)
    layout = replace(arrangement.layout, placements=places)
    if not layout.fits:
        raise FitError(
            f"this {document.kind} needs {layout.width:.0f} at its narrowest "
            f"and the canvas is {width:.0f}. Both directions were tried. Shorten the "
            f"longest label, split the diagram, or give it more width — drawspec will not "
            f"overlap the boxes or shorten the arrows to make it fit."
        )

    shapes = {node.id: theme.roles[node.role].shape for node in document.nodes}
    shapes.update(
        {
            identifier: BAR_SHAPE if marker in STATE_BARS else "ellipse"
            for identifier, marker in markers.items()
        }
    )
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
    connectors = tuple(
        Connector(
            edge.source,
            edge.target,
            role=_drawn_role(edge),
            label=_marked(edge, theme),
            source_port=ports.get((index, 0)),
            target_port=ports.get((index, 1)),
        )
        for index, edge in enumerate(document.edges)
    )
    loops = _placed_loops(
        connectors, {box.id: box for box in obstacles}, arrangement, theme, measurer
    )
    # Each loop and its label is somewhere no other route may go, exactly like a
    # box: the room was reserved for it, and a line through it would cross the
    # loop or run through its words.
    zones = tuple(
        Obstacle(f"\x00loop {index}", x=left, y=top, width=right - left, height=bottom - top)
        for index, loop in enumerate(loops)
        for left, top, right, bottom in (loop.zone,)
    )
    anchors = frame_anchors(arrangement.frames)
    captions_blocked = tuple(
        blocked for frame in arrangement.frames for blocked in caption_obstacle(frame)
    )
    separators = separator_obstacles(region_separators(arrangement.frames), theme)
    loop_words = tuple(
        _label_obstacle(loop.label, f"\x00loop label {index}")
        for index, loop in enumerate(loops)
        if loop.label is not None
    )
    # A lane's heading is words and its divider a line nothing should run along,
    # so routes go round the headings and labels keep off both; the lines between
    # lanes are crossed freely, because crossing one is the hand-off.
    headings = (*swimlanes.headings(), *swimlanes.markers()) if swimlanes is not None else ()
    dividers = _divider_obstacles(swimlanes, theme) if swimlanes is not None else ()
    plain = tuple(connector for connector in connectors if connector.source != connector.target)
    # A state machine is full of return edges, and every one of its transitions
    # is labelled. Routed together, the returns took the lanes beside the boxes
    # and left a forward transition's label no room between them; so a state
    # machine routes its forward transitions first, places their labels, and
    # then routes the returns around those labels as well as the boxes.
    phases = (
        _forward_then_back(plain, {box.id: box for box in (*obstacles, *anchors)}, layout)
        if document.kind == "states"
        else (plain,)
    )
    routes: tuple[Route, ...] = ()
    labels: tuple[Label, ...] = ()
    for phase in phases:
        if not phase:
            continue
        earlier = tuple(
            _label_obstacle(label, f"\x00label {index}") for index, label in enumerate(labels)
        )
        # Frames do not obstruct — an edge into a group must cross its border —
        # but a frame's caption does, so an arrow arriving from above comes in
        # beside the words rather than through them.
        fresh = route_edges(
            phase,
            (*obstacles, *zones, *captions_blocked, *separators, *earlier, *headings),
            theme,
            direction=layout.direction,
            # …and yet an edge may *end* on one. A frame is a box with an extent
            # and a border, which is everything an endpoint needs; what it must
            # not be is something to route around. `anchors` is that
            # distinction — R5-2.
            anchors=anchors,
            dividers=region_dividers(arrangement.frames),
        )
        if swimlanes is not None:
            # A route running along a lane boundary moves the boundary, not the
            # route — and before the labels, so they keep off where it lands.
            swimlanes = swimlanes.settled(
                (*routes, *fresh, *(loop.route for loop in loops)),
                layout.placements,
                {node.id: node.lane for node in document.nodes},
                theme.edge.lane_spacing,
            )
            dividers = _divider_obstacles(swimlanes, theme)
        # Labels avoid the frames as well as the boxes — only the frames'
        # borders, so a label belonging to an edge inside a group can still sit
        # inside it. And the captions, for the same reason the routes avoid them:
        # a caption is words, and two sets of words in one place are neither of
        # them. An edge label landed on top of "Another worker" and the pair read
        # as one smudge. A loop's label is already placed; it is one more thing
        # to keep clear of, and its line one more line.
        labels = (
            *labels,
            *place_labels(
                (
                    *fresh,
                    *(replace(route, label="") for route in routes),
                    *(replace(loop.route, label="") for loop in loops),
                ),
                (
                    *obstacles,
                    *(
                        border
                        for frame in arrangement.frames
                        if not frame.region_of
                        for border in border_obstacles(frame, theme)
                    ),
                    *captions_blocked,
                    *separators,
                    *loop_words,
                    *earlier,
                    *headings,
                    *dividers,
                ),
                theme,
                measurer,
            ),
        )
        routes = (*routes, *fresh)
    routes = (*routes, *(loop.route for loop in loops))
    labels = (*labels, *(loop.label for loop in loops if loop.label is not None))

    if swimlanes is not None:
        swimlanes = swimlanes.covering(
            *_ink(obstacles, routes, labels), margin=theme.edge.lane_spacing
        )
    drawing = _framed(
        layout,
        boxes,
        obstacles,
        routes,
        labels,
        arrangement.frames,
        _bands(document, layout, theme, measurer),
        swimlanes,
    )
    shift_x, shift_y = drawing.offset
    return replace(
        drawing,
        markers=MappingProxyType(markers),
        loops=tuple(
            Loop(
                loop.side,
                replace(
                    loop.route,
                    points=tuple((x + shift_x, y + shift_y) for x, y in loop.route.points),
                ),
                None
                if loop.label is None
                else replace(
                    loop.label, left=loop.label.left + shift_x, top=loop.label.top + shift_y
                ),
            )
            for loop in loops
        ),
    )


def _bands(
    document: Document,
    layout: Layout,
    theme: Theme,
    measurer: TextMeasurer,
) -> tuple[BandBar, ...]:
    """One bar per band, beside the boxes it accompanies, alternating sides.

    A band runs **along** the reading direction and is placed **across** it, which
    is the only arrangement that makes it a band rather than another rank: a
    process read across the page has its continuous activities above and below it,
    and the same process read down the page has them left and right. So the axis
    it spans is the layout's own direction, and nothing here needs to know which
    one the author got.

    Sides alternate in declaration order, and that is what makes two bands peers.
    The first goes on one side, the second on the other, the third outside the
    first — so the commonest case, the two the source sheets draw, comes out
    *surrounding* the steps exactly as the original's own description says. A
    `group` could not say this at all: a box sits inside one container or none, so
    two groups over the same members had to nest, drawing a hierarchy that is not
    there.

    Raises:
        DrawspecError: a band names no member that was placed. Every id is checked
            against the document at parse time, so this is the empty-band case
            rather than a typo, and it is refused rather than drawn as a bar of no
            length beside nothing.
    """
    if not document.bands:
        return ()
    places = layout.placements
    across = layout.direction == "right"
    gap = theme.box.padding.horizontal

    everything = list(places.values())
    near = min((place.y if across else place.x) for place in everything)
    far = max((place.bottom if across else place.right) for place in everything)

    spans = [_band_span(band, places, across) for band in document.bands]
    blocks = [
        _band_name(band, finish - start, theme, measurer)
        for band, (start, finish) in zip(document.bands, spans, strict=True)
    ]
    # One band's whole claim on the cross axis: the gap to its name, and the name.
    # Taken from the tallest name rather than from each, so two bands on opposite
    # sides sit the same distance out and read as the peers they are.
    step = gap + max(block.height for block in blocks) + gap

    bars: list[BandBar] = []
    for index, (band, (start, finish), block) in enumerate(
        zip(document.bands, spans, blocks, strict=True)
    ):
        # Outward: even-numbered bands on the near side, odd on the far side, each
        # pair a step further out than the last.
        rank = index // 2
        outward = gap + rank * step
        near_side = index % 2 == 0
        cross = near - outward if near_side else far + outward
        middle = (start + finish) / 2
        # The name goes on the far side of the bar from the drawing, so a longer
        # name never reaches back over the boxes. On the near side the block grows
        # away from the drawing too, so it is its *far* edge that sits at the gap.
        block_at = cross - gap - block.height if near_side else cross + gap

        if across:
            bars.append(
                BandBar(
                    text=band.text,
                    points=((start, cross), (finish, cross)),
                    block=block,
                    label_x=middle,
                    label_y=block_at,
                )
            )
        else:
            bars.append(
                BandBar(
                    text=band.text,
                    points=((cross, start), (cross, finish)),
                    block=block,
                    label_x=block_at,
                    label_y=middle,
                    rotate=-90.0,
                )
            )
    return tuple(bars)


def _band_span(band: Band, places: Mapping[str, Placement], across: bool) -> tuple[float, float]:
    """Where one band's bar starts and finishes along the reading direction.

    Raises:
        DrawspecError: the band names no member that was placed. Every id is
            checked against the document at parse time, so this is the empty-band
            case rather than a typo, and it is refused rather than drawn as a bar
            of no length beside nothing.
    """
    members = [places[member] for member in band.members if member in places]
    if not members:
        raise DrawspecError(
            f"the band {band.text[:32]!r} names no box that this drawing placed, so "
            f"there is nothing for it to run alongside. Give it members that are "
            f"nodes of this document."
        )
    start = min((place.x if across else place.y) for place in members)
    finish = max((place.right if across else place.bottom) for place in members)
    return start, finish


def _band_name(band: Band, length: float, theme: Theme, measurer: TextMeasurer) -> TextBlock:
    """A band's name, broken to the length of its own bar.

    The band name was the last text field that skipped the wrapper, and it kept
    none of a text field's promises for it: `**bold**` went out with its asterisks
    showing, a second paragraph was flattened into the first, and — because an
    unbroken name has no width anyone measured — a long one was drawn straight off
    the canvas and simply not there. A name of eighty characters beside a
    two-box chain lost sixty per cent of itself that way, silently.

    Raises:
        FitError: a single word in the name is longer than the bar. Named as the
            band, because the diagram was fine and the name was not, and the
            author should be told which of the two to shorten.
    """
    try:
        return wrap(band.text, length, measurer, theme=theme, level="label")
    except FitError as error:
        raise FitError(
            f"the band name {band.text[:40]!r} does not fit the "
            f"{length:.0f} units its members span: {error}"
        ) from None


def band_primitives(bar: BandBar, theme: Theme) -> tuple[Primitive, ...]:
    """A band's bar and its name, one `TextLine` per wrapped line.

    A quarter turn swaps which of the block's two axes is which: the lines still
    advance down the block, but *down the block* is across the page, so a line's
    baseline offset is added to x rather than to y.
    """
    del theme  # the name's type comes from its role, like every other text run's
    lines = tuple(
        TextLine(
            BAND_TEXT_ROLE,
            x=bar.label_x + (bar.block.baseline(index) if bar.rotate else 0.0),
            y=bar.label_y + (0.0 if bar.rotate else bar.block.baseline(index)),
            spans=tuple(
                TextSpan(text=span.text, font=span.font, weight=span.weight)
                for span in line.spans
                if span.text
            ),
            level="label",
            anchor="middle",
            rotate=bar.rotate,
        )
        for index, line in enumerate(bar.block.lines)
        if line.spans
    )
    return (Path(BAND_ROLE, points=bar.points), *lines)


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
    document: Document,
    theme: Theme,
    measurer: TextMeasurer,
    limit: float,
    nesting: Nesting,
    markers: Mapping[str, str] = MappingProxyType({}),
    widen: float = NODE_WIDEN,
) -> dict[str, Box]:
    """One box per node, with peers normalised to a common width.

    Peers are nodes that share a role **and a container**. The role stands in for
    "the same kind of thing" before ranks exist — the layout has not run yet, so
    rank-based normalisation is not available, and normalising afterwards would
    invalidate the positions it was computed from.

    **The container is the other half, and it used to be missing.** Sharing a
    width is what makes peers read as peers, and it is also what gives a long
    label the room to need fewer lines — but across a whole document it becomes
    one long paragraph setting the width of every box in the drawing. Seven boxes
    on the nested-boxes sheet all came out 243.5 wide, the one holding the word
    *AGE* included, because a three-line paragraph lived in a different box
    somewhere else. The three administrations then would not share a row until
    the canvas was 880 wide, and at 640 the packer put them in two rows and left
    one stranded — so the author loses either the source's arrangement or a
    legible type size, which is the trade the tool exists to prevent.

    A container is the scope an author already declared, and the one a reader
    compares within: boxes side by side inside a frame are being set against each
    other, and a box in another frame is not. Same alignment, and it stops
    travelling across the drawing.
    """
    nodes = [node for node in document.nodes if node.id not in markers]
    boxes = {node.id: _sized_node(node, theme, measurer, limit, widen) for node in nodes}
    peers: dict[tuple[str, str], list[str]] = {}
    for node in nodes:
        peers.setdefault((nesting.parent.get(node.id, ""), node.role), []).append(node.id)
    for identifiers in peers.values():
        for identifier, box in zip(
            identifiers, normalise([boxes[i] for i in identifiers]), strict=True
        ):
            boxes[identifier] = box
    for identifier, marker in markers.items():
        boxes[identifier] = _marker_box(marker, theme, _bar_arrows(document, identifier))
    return boxes


#: The role a removed edge is drawn in, whatever role it was written with:
#: dashed and headless, a connection that is no longer there to go anywhere.
REMOVED_EDGE_ROLE: Final = "aside"


#: How much taller the gap between ranks is in a causal loop diagram, in body
#: sizes: room for a loop's marker — a ring round its letters, its name under it.
LOOP_ROOM: Final = 4.5


def _drawn_role(edge: Edge) -> str:
    return REMOVED_EDGE_ROLE if edge.status == "removed" else edge.role


def _marked(edge: Edge, theme: Theme) -> str:
    """An edge's label with its change's mark and its sign written first — or those alone.

    A causal link's sign is its label: placed like one, it keeps clear of every
    line, box and other label.
    """
    marks = []
    if edge.status:
        marks.append(DRAWN_MARKS[edge.status])
    if edge.polarity:
        marks.append(POLARITY_GLYPHS[theme.flow.polarity][edge.polarity])
    return " ".join([*marks, edge.label] if edge.label else marks)


def _sized_node(
    node: Node, theme: Theme, measurer: TextMeasurer, limit: float, widen: float = NODE_WIDEN
) -> Box:
    """One node's box — with room for its change's tag as a last line, when it has one.

    The tag is sized as a paragraph of the box's own text so every shape makes
    room for it the way it makes room for words, then drawn as a pill in that
    line's place. It must not become the detail of a lead nobody wrote, so a
    single-paragraph label stays one: the lead is the author's, or the actor's.
    """
    if not node.status:
        return size_box(
            node.label,
            theme=theme,
            measurer=measurer,
            role=node.role,
            level="body",
            max_width=limit,
            widen=widen,
            lead=node.lead,
        )
    box = size_box(
        f"{node.label}\n{status_words(node.status)}",
        theme=theme,
        measurer=measurer,
        role=node.role,
        level="body",
        max_width=limit,
        widen=widen,
        lead=bool(node.actor) or "\n" in node.text.strip(),
    )
    tag_width, _ = status_size(node.status, theme, measurer)
    return box.resized(width=tag_width + theme.box.padding.horizontal)


# ---------------------------------------------------------------------------
# Self-loops
# ---------------------------------------------------------------------------


def _loops(document: Document) -> dict[str, list[Edge]]:
    """Each box's self-loops, in the order written. Validation caps them at two."""
    looped: dict[str, list[Edge]] = {}
    for edge in document.edges:
        if edge.source == edge.target:
            looped.setdefault(edge.source, []).append(edge)
    return looped


def _loop_margins(
    box: Box,
    labels: Sequence[tuple[float, float]],
    directions: set[str],
    theme: Theme,
) -> tuple[float, float]:
    """The room to keep clear around a box with loops: across, then down, each side.

    The same on both sides of the box, so a box with a loop stays centred in its
    column and its neighbours' edges still meet it square; and so the loop can
    take whichever of the two sides no other edge ends on, which is not known
    until the edges are routed.
    """
    across = down = 0.0
    for direction in directions:
        sides = LOOP_SIDES.get(direction, LOOP_SIDES[PREFERRED_DIRECTION])
        reach = max(loop_margin(sides[0], label, theme) for label in labels)
        # The label is beside the loop's far leg, centred on the side; if it is
        # longer than the side, it overhangs along it too.
        if sides[0] in ("left", "right"):
            across = max(across, reach)
            overhang = max(height for _, height in labels) - box.height
            down = max(down, overhang / 2)
        else:
            down = max(down, reach)
            overhang = max(width for width, _ in labels) - box.width
            across = max(across, overhang / 2)
    return across, max(down, 0.0)


def _label_obstacle(label: Label, identifier: str) -> Obstacle:
    """A placed label, as something a later route or label must keep clear of."""
    return Obstacle(identifier, x=label.left, y=label.top, width=label.width, height=label.height)


def _forward_then_back(
    connectors: Sequence[Connector], boxes: Mapping[str, Obstacle], layout: Layout
) -> tuple[tuple[Connector, ...], tuple[Connector, ...]]:
    """The connectors that go with the reading direction, then those that go round."""
    forward: list[Connector] = []
    back: list[Connector] = []
    for connector in connectors:
        (back if goes_round(connector, boxes, layout.direction) else forward).append(connector)
    return tuple(forward), tuple(back)


def _placed_loops(
    connectors: Sequence[Connector],
    boxes: Mapping[str, Obstacle],
    arrangement: Arrangement,
    theme: Theme,
    measurer: TextMeasurer,
) -> tuple[Loop, ...]:
    """Every self-loop, on the sides of its box no other edge ends on, where possible."""
    loops: list[Loop] = []
    pending: dict[str, list[Connector]] = {}
    for connector in connectors:
        if connector.source == connector.target:
            pending.setdefault(connector.source, []).append(connector)
    for identifier, mine in pending.items():
        direction = arrangement.directions.get(identifier, arrangement.direction)
        box = boxes[identifier]
        sides = loop_sides(
            box,
            len(mine),
            claimed_sides(identifier, connectors, boxes, direction),
            direction,
        )
        loops.extend(
            place_loop(box, side, connector, theme, measurer)
            for side, connector in zip(sides, mine, strict=False)
        )
    return tuple(loops)


def _region_room(
    document: Document,
    nesting: Nesting,
    boxes: Mapping[str, Box],
    theme: Theme,
    measurer: TextMeasurer,
) -> dict[str, float]:
    """Room on each side of a composite state's region for its return transitions.

    A plain frame lets a transition that goes back up run outside it, label and
    all; a region is closed in by the dashed line to its neighbour, so a region
    whose own transitions go round in a cycle keeps its widest label's width
    clear beside its states, where that line and its words can go.
    """
    room: dict[str, float] = {}
    for region in nesting.regions:
        inside = set(nesting.descendants(region))
        edges = [e for e in document.edges if e.source in inside and e.target in inside]
        leads: dict[str, set[str]] = {}
        for edge in edges:
            leads.setdefault(edge.source, set()).add(edge.target)

        def reaches(start: str, goal: str, leads: Mapping[str, set[str]] = leads) -> bool:
            seen: set[str] = set()
            stack = [start]
            while stack:
                current = stack.pop()
                if current == goal:
                    return True
                if current not in seen:
                    seen.add(current)
                    stack.extend(leads.get(current, ()))
            return False

        def width_of(end: str) -> float:
            # A nested composite has no box of its own yet: its frame is at least
            # as wide as the widest box inside it, which is a safe lower bound.
            if end in boxes:
                return boxes[end].width
            inner = [boxes[member].width for member in nesting.descendants(end) if member in boxes]
            return max(inner, default=0.0)

        gap = theme.edge.clearance * 2
        needs = [0.0]
        for edge in edges:
            if edge.source == edge.target or not edge.label:
                continue
            wide = label_extents(edge.label, theme, measurer)[0] + gap
            if reaches(edge.target, edge.source):
                needs.append(wide)
            else:
                # A forward label sits beside its line, which leaves the middle of
                # its box: half the box and the padding are already room for it.
                narrowest = min(width_of(end) for end in (edge.source, edge.target))
                needs.append(wide - narrowest / 2 - theme.box.padding.horizontal / 2)
        if max(needs) > 0:
            room[region] = max(needs)
    return room


# ---------------------------------------------------------------------------
# Pseudo-states
# ---------------------------------------------------------------------------

#: The role a pseudo-state's dot is drawn in. A dot is not a role an author can
#: name — it has no words and no shape choice — so it borrows the default box
#: role's line, and the theme's `[states]` section sizes it.
MARKER_ROLE: Final = "step"


def _with_pseudo_states(document: Document) -> tuple[Document, dict[str, str]]:
    """A `states` document with its pseudo-states as nodes, and which nodes they are.

    The initial dot is a node with an edge to the initial state, so the layered
    ranking puts it above that state by itself; a final dot is a node with an
    edge from its final state, so it lands below. A group with an `initial` gets
    its own dot inside its frame. Nothing else in this family needs to know a
    state machine has them, beyond drawing them as dots.
    """
    if document.kind != "states":
        return document, {}
    taken = {node.id for node in document.nodes} | {group.id for group in document.groups}

    def fresh(name: str) -> str:
        while name in taken:
            name += "'"
        taken.add(name)
        return name

    parent = {member: group.id for group in document.groups for member in group.members}
    markers: dict[str, str] = {}
    added: dict[str, list[str]] = {}
    first: list[Edge] = []
    last: list[Edge] = []

    # A fork or join bar is the author's own state, by id, drawn as a mark: it
    # keeps its id, so its transitions need nothing changed.
    bars = {node.id: node.role for node in document.nodes if node.role in STATE_BARS}
    markers.update(bars)

    start = fresh("(initial)")
    markers[start] = "initial"
    first.append(Edge(start, document.initial))
    for group in document.groups:
        if group.initial:
            entry = fresh(f"(initial {group.id})")
            markers[entry] = "initial"
            added.setdefault(group.id, []).append(entry)
            first.append(Edge(entry, group.initial))
    for state in document.final:
        end = fresh(f"(final {state})")
        markers[end] = "final"
        if state in parent:
            added.setdefault(parent[state], []).append(end)
        last.append(Edge(state, end))

    return (
        replace(
            document,
            nodes=(
                *(
                    Node(id=node.id, text=" ") if node.id in bars else node
                    for node in document.nodes
                ),
                *(Node(id=marker, text=" ") for marker in markers if marker not in bars),
            ),
            edges=(*first, *document.edges, *last),
            groups=tuple(
                replace(group, members=(*group.members, *added.get(group.id, ())))
                for group in document.groups
            ),
        ),
        markers,
    )


def _pulled_in(
    places: Mapping[str, Placement],
    markers: Mapping[str, str],
    edges: Sequence[Edge],
    arrangement: Arrangement,
    base: Spacing,
    gap: float,
) -> dict[str, Placement]:
    """Each pseudo-state moved up against its state, an ordinary arrow's length away.

    A dot is ranked like a box, so it was a whole rank away from its state — and
    a state machine's ranks are spaced for labels, which a pseudo-state's arrow
    never carries. So each dot is moved to the plain rank gap from its state,
    centred on it, wherever that place is empty; otherwise it stays where the
    layout put it.
    """
    moved = dict(places)
    frames = arrangement.frames
    for identifier, marker in markers.items():
        if marker in STATE_BARS:
            continue
        partner = next(
            (
                edge.target if marker == "initial" else edge.source
                for edge in edges
                if (edge.source if marker == "initial" else edge.target) == identifier
            ),
            None,
        )
        if partner is None or partner not in places:
            continue
        here, there = places[identifier], places[partner]
        direction = arrangement.directions.get(identifier, arrangement.direction)
        if direction == "right":
            x = (
                there.x - base.rank_gap - here.width
                if marker == "initial"
                else there.right + base.rank_gap
            )
            y = there.y + (there.height - here.height) / 2
        else:
            x = there.x + (there.width - here.width) / 2
            y = (
                there.y - base.rank_gap - here.height
                if marker == "initial"
                else there.bottom + base.rank_gap
            )
        spot = replace(here, x=x, y=y)
        # The dot and its arrow together: nothing else may be in that stretch.
        reach = Placement(
            min(spot.x, there.x) - gap,
            min(spot.y, there.y) - gap,
            max(spot.right, there.right) - min(spot.x, there.x) + gap * 2,
            max(spot.bottom, there.bottom) - min(spot.y, there.y) + gap * 2,
            0,
        )
        crowded = any(
            other != identifier and other != partner and reach.overlaps(place)
            for other, place in moved.items()
        ) or any(
            _crosses_border(reach, frame, here) or _crosses_border(reach, frame, there)
            for frame in frames
        )
        if not crowded:
            moved[identifier] = spot
    return moved


#: Which side of a bar faces back up the flow and which faces on down it.
_BAR_SIDES: Final[Mapping[str, tuple[str, str]]] = {
    "down": ("top", "bottom"),
    "right": ("left", "right"),
}


def _spanned_bars(
    places: Mapping[str, Placement],
    markers: Mapping[str, str],
    edges: Sequence[Edge],
    arrangement: Arrangement,
    theme: Theme,
    spacing: Spacing,
) -> tuple[dict[str, Placement], dict[tuple[int, int], tuple[str, float]]]:
    """Each fork or join bar stretched to reach over the states its arrows join, and
    the port each of those arrows takes on it: (edge index, 0 source / 1 target).

    A bar is sized by its count of arrows, but the regions it splits into are as
    wide as their states, so the arrows left the bar and turned to reach them.
    So a bar lengthens to span its far ends' centres, keeping half a `bar_step`
    beyond the outermost, and each arrow leaves it straight over (or under) the
    end it joins, as a hand-drawn bar is drawn — unless a longer bar would come
    within a node gap of another box, or an end is not beyond the bar in the
    flow, when the arrows keep the even spread routing gives a bar.
    """
    ports: dict[tuple[int, int], tuple[str, float]] = {}
    centres = {identifier: place.centre for identifier, place in places.items()}
    centres.update(
        {
            frame.id: (frame.x + frame.width / 2, frame.y + frame.height / 2)
            for frame in arrangement.frames
        }
    )
    ends = {
        bar: (
            [
                (
                    index,
                    0 if marker == "fork" else 1,
                    edge.target if marker == "fork" else edge.source,
                )
                for index, edge in enumerate(edges)
                if (edge.source if marker == "fork" else edge.target) == bar
            ],
            [
                (
                    index,
                    1 if marker == "fork" else 0,
                    edge.source if marker == "fork" else edge.target,
                )
                for index, edge in enumerate(edges)
                if (edge.target if marker == "fork" else edge.source) == bar
            ],
        )
        for bar, marker in markers.items()
        if marker in STATE_BARS and bar in places
    }
    flows = {
        bar: (0 if arrangement.directions.get(bar, arrangement.direction) != "right" else 1)
        for bar in ends
    }

    def lengthwise(place: Placement, across: int, low: float, high: float) -> Placement:
        if across == 0:
            return replace(place, x=low, width=high - low)
        return replace(place, y=low, height=high - low)

    # First every bar at its own length, centred where the layout put it — which
    # may have kept it more room than that (see `containers.arrange`).
    moved = dict(places)
    for bar, (busy, _) in ends.items():
        place, across = places[bar], flows[bar]
        start, end = (place.x, place.right) if across == 0 else (place.y, place.bottom)
        own = theme.states.bar_step * max(len(busy), 2)
        moved[bar] = lengthwise(
            place, across, (start + end) / 2 - own / 2, (start + end) / 2 + own / 2
        )
    for bar, (busy, single) in ends.items():
        marker, across = markers[bar], flows[bar]
        direction = "right" if across else "down"
        back, on = _BAR_SIDES[direction]
        place = moved[bar]
        far = {end for _, _, end in busy}
        near = {end for _, _, end in single}
        if not far <= centres.keys() or not near <= centres.keys():
            continue
        start, end = (place.x, place.right) if across == 0 else (place.y, place.bottom)
        middle = (place.y + place.bottom) / 2 if across == 0 else (place.x + place.right) / 2

        def beyond(
            identifier: str, ahead: bool, middle: float = middle, across: int = across
        ) -> bool:
            flow = centres[identifier][1 - across]
            return flow > middle if ahead else flow < middle

        if not all(beyond(e, marker == "fork") for e in far) or not all(
            beyond(e, marker != "fork") for e in near
        ):
            continue
        margin = theme.states.bar_step / 2
        lanes = {e: _clear_lane(e, centres, places, place, across, arrangement, theme) for e in far}
        along = list(lanes.values())
        # Far ends side by side across the bar's length would share a port: the
        # regions run the other way. Leave them the even spread.
        if any(second - first < margin for first, second in pairwise(sorted(along))):
            continue
        low, high = min(start, min(along) - margin), max(end, max(along) + margin)
        stretched = lengthwise(place, across, low, high)
        reach = Placement(
            stretched.x - spacing.node_gap,
            stretched.y - spacing.node_gap,
            stretched.width + spacing.node_gap * 2,
            stretched.height + spacing.node_gap * 2,
            0,
        )
        if any(
            other != bar and other in places and reach.overlaps(other_place)
            for other, other_place in moved.items()
        ):
            continue
        moved[bar] = stretched
        length = high - low
        busy_side = on if marker == "fork" else back
        single_side = back if marker == "fork" else on
        for index, end_of, identifier in busy:
            ports[(index, end_of)] = (busy_side, (lanes[identifier] - low) / length)
            if identifier in places and lanes[identifier] != centres[identifier][across]:
                # Moved off a caption: the far end is met there too, so the line is straight.
                other = places[identifier]
                start_of = other.x if across == 0 else other.y
                size = other.width if across == 0 else other.height
                ports[(index, 1 - end_of)] = (
                    single_side,
                    (lanes[identifier] - start_of) / size,
                )
        for index, end_of, identifier in single:
            spot = min(max(centres[identifier][across], low + margin), high - margin)
            ports[(index, end_of)] = (single_side, (spot - low) / length)
    return moved, ports


def _clear_lane(
    end: str,
    centres: Mapping[str, tuple[float, float]],
    places: Mapping[str, Placement],
    bar: Placement,
    across: int,
    arrangement: Arrangement,
    theme: Theme,
) -> float:
    """Where along a bar the straight line to `end` runs: through its centre, or —
    when a frame's caption between the two is in the way — just past the caption,
    as long as that still lands on `end` clear of its corners."""
    lane = centres[end][across]
    if end not in places:
        return lane
    target = places[end]
    flow = (bar.y, target.y) if across == 0 else (bar.x, target.x)
    low_flow, high_flow = min(flow), max(flow)
    clearance = theme.edge.clearance
    for frame in arrangement.frames:
        caption = frame.caption
        if caption is None:
            continue
        start = caption.x if across == 0 else caption.y
        size = caption.width if across == 0 else caption.height
        depth = (
            (caption.y, caption.y + caption.height)
            if across == 0
            else (
                caption.x,
                caption.x + caption.width,
            )
        )
        if depth[1] <= low_flow or depth[0] >= high_flow:
            continue
        if start - clearance < lane < start + size + clearance:
            lane = start + size + clearance
    first = target.x if across == 0 else target.y
    extent = target.width if across == 0 else target.height
    if not first + extent * 0.2 <= lane <= first + extent * 0.8:
        return centres[end][across]
    return lane


def _crosses_border(reach: Placement, frame: Frame, inside: Placement) -> bool:
    """Whether `reach` crosses `frame`'s border on one side of `inside` but not the other."""
    held = (
        frame.x <= inside.x
        and inside.right <= frame.right
        and frame.y <= inside.y
        and inside.bottom <= frame.bottom
    )
    within = (
        frame.x <= reach.x
        and reach.right <= frame.right
        and frame.y <= reach.y
        and reach.bottom <= frame.bottom
    )
    apart = (
        reach.right <= frame.x
        or frame.right <= reach.x
        or reach.bottom <= frame.y
        or frame.bottom <= reach.y
    )
    return not within and not apart if held else not apart


def _arranged(
    arranging: Callable[..., Arrangement], regions: bool, max_height: float = 0.0
) -> Arrangement:
    """`containers.arrange`, and again reading across when that is how it should come out.

    A composite's regions are arranged before the level around it picks its
    direction, so they sit side by side under a machine that reads down — and
    under one that turned out to read across (or would have, but for regions
    side by side too wide to fit), where its bars stand upright and the regions
    should be stacked against them, each reading across too. So a machine with
    `regions` whose top level came out `right`, or too tall for a binding
    height, is arranged once more preferring `right` all the way in, which stacks
    them. Nothing without regions is arranged twice.
    """
    arrangement = arranging(prefer=PREFERRED_DIRECTION)
    too_tall = bool(max_height) and arrangement.layout.height > max_height
    if not regions or (arrangement.layout.direction != "right" and not too_tall):
        return arrangement
    again = arranging(prefer="right")
    if again.layout.direction != "right" or not again.layout.fits:
        return arrangement
    return again if not too_tall or again.layout.height < arrangement.layout.height else arrangement


def _bar_ends(document: Document, markers: Mapping[str, str]) -> dict[str, tuple[str, ...]]:
    """Each fork's or join's far ends: where a fork's arrows go, where a join's come from."""
    return {
        bar: tuple(
            edge.target if marker == "fork" else edge.source
            for edge in document.edges
            if (edge.source if marker == "fork" else edge.target) == bar
        )
        for bar, marker in markers.items()
        if marker in STATE_BARS
    }


def _bar_arrows(document: Document, identifier: str) -> int:
    """How many arrows a bar's busy side holds: a fork's ways out, a join's ways in."""
    return max(
        sum(edge.source == identifier for edge in document.edges),
        sum(edge.target == identifier for edge in document.edges),
    )


def _marker_box(marker: str, theme: Theme, arrows: int = 0) -> Box:
    """A pseudo-state's extent: a circle with no text, or a bar, sized by the theme.

    A bar is sized lying across a `down` flow — `bar_step` per arrow long, `bar`
    thick — and the layout turns it upright when the flow runs `right`.
    """
    empty = TextBlock(lines=(), width=0.0, height=0.0, advance=0.0, ascent=0.0, descent=0.0)
    if marker in STATE_BARS:
        return Box(
            role=MARKER_ROLE,
            shape=BAR_SHAPE,
            level="label",
            block=empty,
            width=theme.states.bar_step * max(arrows, 2),
            height=theme.states.bar,
        )
    size = theme.states.dot if marker == "initial" else theme.states.final
    return Box(
        role=MARKER_ROLE,
        shape="ellipse",
        level="label",
        block=empty,
        width=size,
        height=size,
    )


def marker_primitives(box: Box, marker: str, theme: Theme) -> tuple[Primitive, ...]:
    """A filled dot for the initial pseudo-state; a dot in a ring for a final one;
    a solid bar for a fork or a join."""
    if marker in STATE_BARS:
        left, top, right, bottom = box.x, box.y, box.x + box.width, box.y + box.height
        return (
            Polygon(
                MARKER_ROLE,
                points=((left, top), (right, top), (right, bottom), (left, bottom)),
                fill="solid",
                fill_colour="currentColor",
                region=True,
            ),
        )
    cx, cy = box.x + box.width / 2, box.y + box.height / 2
    dot = theme.states.dot / 2
    filled = Ellipse(
        MARKER_ROLE, cx=cx, cy=cy, rx=dot, ry=dot, fill="solid", fill_colour="currentColor"
    )
    if marker == "initial":
        return (filled,)
    ring = box.width / 2
    return (Ellipse(MARKER_ROLE, cx=cx, cy=cy, rx=ring, ry=ring), filled)


def _grown(boxes: Mapping[str, Box], margins: Mapping[str, tuple[float, float]]) -> dict[str, Box]:
    """Each box with the room kept around it for its loops, across then down."""
    return {
        identifier: box.resized(
            width=box.width + margins[identifier][0] * 2,
            height=box.height + margins[identifier][1] * 2,
        )
        if identifier in margins
        else box
        for identifier, box in boxes.items()
    }


def _divider_obstacles(lanes: Swimlanes, theme: Theme) -> tuple[Obstacle, ...]:
    """Each line between lanes or phases as a thin obstacle, for labels: words never sit on one."""
    half = theme.edge.clearance
    found: list[Obstacle] = []
    for index, ((x1, y1), (x2, y2)) in enumerate((*lanes.separators(), *lanes.phase_lines())):
        left, top = min(x1, x2) - half, min(y1, y2) - half
        found.append(
            Obstacle(
                f"\x00lane divider {index}",
                x=left,
                y=top,
                width=abs(x2 - x1) + half * 2,
                height=abs(y2 - y1) + half * 2,
            )
        )
    return tuple(found)


def _ink(
    obstacles: Sequence[Obstacle], routes: Sequence[Route], labels: Sequence[Label]
) -> tuple[float, float, float, float]:
    """Left, top, right and bottom of the boxes, routes and labels together."""
    xs = [value for box in obstacles for value in (box.x, box.right)]
    ys = [value for box in obstacles for value in (box.y, box.bottom)]
    xs += [x for route in routes for x, _ in route.points]
    ys += [y for route in routes for _, y in route.points]
    xs += [value for label in labels for value in (label.left, label.left + label.width)]
    ys += [value for label in labels for value in (label.top, label.top + label.height)]
    return min(xs), min(ys), max(xs), max(ys)


def _framed(
    layout: Layout,
    boxes: Mapping[str, Box],
    obstacles: Sequence[Obstacle],
    routes: Sequence[Route],
    labels: Sequence[Label],
    frames: Sequence[Frame] = (),
    bands: Sequence[BandBar] = (),
    lanes: Swimlanes | None = None,
) -> GraphDrawing:
    """Shift everything so the drawing starts at its own ink, and measure it.

    The layout's own extents are not the drawing's: a back edge routed around the
    outside and a label placed to the left of the leftmost box both live outside
    them, and either would be clipped by a canvas sized to the boxes alone. So
    the frame is taken from what was actually produced.

    The result is flush to that ink. The outer margin used to be added here, out
    of `[box] padding`, which made a flow chart's channel of blank a decision the
    graph family took on its own — see `render.framed` for the one place it is
    taken now.
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
    for bar in bands:
        xs += [point[0] for point in bar.points]
        ys += [point[1] for point in bar.points]
        # The name's whole box, not its anchor. Measured from the anchor alone,
        # the canvas ended where the words began and drew the rest off the page.
        left, top, right, bottom = bar.label_box
        xs += [left, right]
        ys += [top, bottom]
    if lanes is not None:
        left, top, right, bottom = lanes.bounds
        xs += [left, right]
        ys += [top, bottom]

    offset_x = -min(xs, default=0.0)
    offset_y = -min(ys, default=0.0)
    return GraphDrawing(
        layout=layout,
        boxes={
            identifier: (
                # A bar is the one box the layout may make narrower: it turns.
                replace(boxes[identifier], width=place.width, height=place.height)
                if boxes[identifier].shape == BAR_SHAPE
                else boxes[identifier].resized(width=place.width, height=place.height)
            ).moved_to(place.x + offset_x, place.y + offset_y)
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
        width=max(xs, default=0.0) + offset_x,
        height=max(ys, default=0.0) + offset_y,
        frames=tuple(frame.moved(offset_x, offset_y) for frame in frames),
        bands=tuple(bar.moved(offset_x, offset_y) for bar in bands),
        offset=(offset_x, offset_y),
        lanes=None if lanes is None else lanes.moved(offset_x, offset_y),
    )


# ---------------------------------------------------------------------------
# Text: a `tree` as boxes on guides
# ---------------------------------------------------------------------------

#: A child's guide, per charset: its branch, and the last child's branch.
TEXT_BRANCHES: Final = {"unicode": ("├", "└"), "ascii": ("|", "`")}


def tree_text(document: Document, width: int, charset: str) -> str:
    """A `tree` as plain text: each box under its parent, joined by `files`' guides.

    The layered engine's topology without its coordinates: a node's children in
    the order their edges are written, each box indented under its parent's and
    joined to it by a guide from the parent's bottom edge to the child's side. An
    edge's label rides on its stub, drawn in the edge's line style; a class is
    named after its box; a status is the `+ ~ -` mark `files` writes, in a column
    at the left that appears only when some node has one.

    Raises:
        DrawspecError: the tree has cross-links, a cycle, groups or bands — a
            graph a guide cannot draw, which waits for the text router.
        FitError: a line is wider than `width`, at the widest box's pointer.
    """
    if document.groups or document.bands:
        raise DrawspecError(
            f"/{'groups' if document.groups else 'bands'}: a `tree` with groups or bands has "
            f"no text form yet. Render it as SVG."
        )
    index = {node.id: position for position, node in enumerate(document.nodes)}
    children: dict[str, list[tuple[int, Edge]]] = {node.id: [] for node in document.nodes}
    parent: dict[str, str] = {}
    for position, edge in enumerate(document.edges):
        if edge.target in parent or edge.target == edge.source:
            raise DrawspecError(
                f"/edges/{position}: {edge.target!r} already hangs under "
                f"{parent.get(edge.target, edge.source)!r}. A `tree` with cross-links has no "
                f"text form yet; render it as SVG."
            )
        parent[edge.target] = edge.source
        children[edge.source].append((position, edge))
    classes = {klass.id: klass.text for klass in document.classes}
    vertical = STRAIGHT[charset]["light"][1]
    reached: set[str] = set()

    def subtree(identifier: str) -> list[Drawn]:
        reached.add(identifier)
        node = document.nodes[index[identifier]]
        pointer = f"/nodes/{index[identifier]}/text"
        what = f"the box {plain(node.label)!r}"
        box = boxed(label_lines(node.label, charset, pointer), node.role, charset)
        if children[identifier]:
            box[-1] = box[-1][:2] + box_glyphs(node.role, charset).down + box[-1][3:]
        if node.klass in classes:
            klass = spelt(plain(classes[node.klass]), charset, "/classes")
            box[1] += f"  ({klass})"
        out = [
            Drawn(line, pointer, what, node.status if row == 1 else "", row == 1)
            for row, line in enumerate(box)
        ]
        under = children[identifier]
        for number, (position, edge) in enumerate(under):
            last = number == len(under) - 1
            stub = STRAIGHT[charset][line_style(edge.role)][0]
            label = spelt(plain(edge.label).replace("\n", " "), charset, f"/edges/{position}/label")
            reach = f"{stub} {label} {stub}" if label else stub
            indent = " " * cells(reach)
            branch = TEXT_BRANCHES[charset][1 if last else 0]
            joined = box_glyphs(document.nodes[index[edge.target]].role, charset).joined
            seen = False
            for line in subtree(edge.target):
                if line.joint and not seen:
                    seen = True
                    text = f"  {branch}{reach}{joined}{line.text[1:]}"
                elif not seen:
                    text = f"  {vertical} {indent[1:]}{line.text}"
                else:
                    text = ("   " if last else f"  {vertical}") + indent + line.text
                out.append(Drawn(text, line.pointer, line.what, line.status, False))
        return out

    drawn: list[Drawn] = []
    for node in document.nodes:
        if node.id not in parent:
            drawn.extend(subtree(node.id))
    if len(reached) < len(document.nodes):
        stray = next(
            position for position, node in enumerate(document.nodes) if node.id not in reached
        )
        raise DrawspecError(
            f"/nodes/{stray}: {document.nodes[stray].id!r} is on a cycle, and a `tree` drawn "
            f"as text hangs every node from a root. Render it as SVG."
        )
    if any(line.status for line in drawn):
        drawn = [
            Drawn(
                f"{STATUS_MARKS[line.status]} {line.text}" if line.status else f"  {line.text}",
                line.pointer,
                line.what,
            )
            for line in drawn
        ]
    widest(drawn, width)
    return finished([line.text for line in drawn] + caption_lines(document.caption, width, charset))


__all__ = [
    "DRAWN_KINDS",
    "NODE_WIDEN",
    "NODE_WIDTH_SHARE",
    "PREFERRED_DIRECTION",
    "BandBar",
    "GraphDrawing",
    "band_primitives",
    "graph_drawing",
    "graph_scene",
    "marker_primitives",
    "tree_text",
]

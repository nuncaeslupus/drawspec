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
    Nesting,
    arrange,
    border_obstacles,
    caption_obstacle,
    captions_for,
    crossed,
    frame_anchors,
    frame_primitives,
    nesting_of,
)
from drawspec.layout import Layout, Placement, Spacing
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
from drawspec.scene import Path, Primitive, Scene, TextLine, TextSpan
from drawspec.schema import Band, Document
from drawspec.text.measure import TextMeasurer
from drawspec.text.wrap import TextBlock, wrap
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
    # Bands last: they sit outside the boxes, so nothing is over them, and the
    # clearance pass has the whole scene either way.
    for bar in drawing.bands:
        primitives.extend(band_primitives(bar, theme))

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
    nesting = nesting_of(document)
    boxes = _sized(document, theme, measurer, width * NODE_WIDTH_SHARE, nesting)
    spacing = _spacing(theme)
    arrangement = arrange(
        nesting.roots,
        nesting,
        [(edge.source, edge.target) for edge in document.edges],
        boxes,
        captions_for(document, nesting, theme, measurer, width * NODE_WIDTH_SHARE),
        theme,
        spacing,
        max_width=width,
        prefer=PREFERRED_DIRECTION,
        entered=crossed([(edge.source, edge.target) for edge in document.edges], nesting),
        centre=next((node.id for node in document.nodes if node.centre), ""),
        # A binding height is the only thing that can make a chain read across
        # rather than down: see `layout.base.best_layout`. An advisory height is
        # not passed, because it is advisory.
        max_height=(document.height or 0.0) if document.height_binding else 0.0,
    )
    # The top level's own layout, with every leaf from every level in it — the
    # ranks and reversed edges are the top level's, which is what a caller
    # asking about ranks means by the question.
    layout = replace(arrangement.layout, placements=arrangement.places)
    if not layout.fits:
        raise FitError(
            f"this {document.kind} needs {layout.width:.0f} at its narrowest "
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
        # …and yet an edge may *end* on one. A frame is a box with an extent and
        # a border, which is everything an endpoint needs; what it must not be is
        # something to route around. `anchors` is that distinction — R5-2.
        anchors=frame_anchors(arrangement.frames),
    )
    # Labels avoid the frames as well as the boxes — only the frames' borders,
    # so a label belonging to an edge inside a group can still sit inside it.
    # And the captions, for the same reason the routes avoid them: a caption is
    # words, and two sets of words in one place are neither of them. An edge
    # label landed on top of "Another worker" and the pair read as one smudge.
    labels = place_labels(
        routes,
        (
            *obstacles,
            *(border for frame in arrangement.frames for border in border_obstacles(frame, theme)),
            *(blocked for frame in arrangement.frames for blocked in caption_obstacle(frame)),
        ),
        theme,
        measurer,
    )

    return _framed(
        layout,
        boxes,
        obstacles,
        routes,
        labels,
        arrangement.frames,
        _bands(document, layout, theme, measurer),
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
    boxes = {
        node.id: size_box(
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
    }
    peers: dict[tuple[str, str], list[str]] = {}
    for node in document.nodes:
        peers.setdefault((nesting.parent.get(node.id, ""), node.role), []).append(node.id)
    for identifiers in peers.values():
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
    frames: Sequence[Frame] = (),
    bands: Sequence[BandBar] = (),
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

    offset_x = -min(xs, default=0.0)
    offset_y = -min(ys, default=0.0)
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
        width=max(xs, default=0.0) + offset_x,
        height=max(ys, default=0.0) + offset_y,
        frames=tuple(frame.moved(offset_x, offset_y) for frame in frames),
        bands=tuple(bar.moved(offset_x, offset_y) for bar in bands),
    )


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
]

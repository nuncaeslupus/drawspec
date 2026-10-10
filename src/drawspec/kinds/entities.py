"""The `entities` kind: data models, database schemas and class diagrams.

Three diagrams drawn as one: **a named box with a list in it, and typed relations
between boxes.** An ER model lists attributes and puts a cardinality at each end
of a line; a physical schema lists columns with types and keys, and draws a
foreign key from one column; a class diagram adds operations and draws
inheritance with a hollow triangle. A document uses whichever of those it needs.

**Boxes are sized before they are placed, row by row.** Every row has one height
— the body type's line — so where a row sits inside its box is known before the
box is placed anywhere, and a relation that names a field can land on that row:
the router is handed a fixed port, at the row's centre, on the side facing the
other box. It is never authored; `port` stays refused.

**Placement is the layered engine's.** With a hierarchy in the diagram the
general entity is ranked above the specific one and the drawing prefers to read
down; without one, relations are ranked as written and it prefers to read across,
which is how a schema's tables sit. Either way the other direction is taken when
the preferred one does not fit.

**Ends are the theme's.** The author says how many at each end; the theme says
crow's feet or numbers. The router is asked for room at every end as though each
carried the longest mark, so a mark always has a straight run to sit on.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Final

from drawspec.errors import DrawspecError, FitError
from drawspec.layout import LayeredEngine, Layout, LayoutEdge, LayoutNode, Spacing, best_layout
from drawspec.routing import (
    LABEL_GAP,
    Connector,
    Label,
    Obstacle,
    Route,
    end_marker,
    hollow_base,
    label_extents,
    label_primitives,
    minimum_rank_gap,
    place_labels,
    route_edges,
)
from drawspec.scene import Path, Primitive, Rect, Scene, TextLine, TextRun, TextSpan
from drawspec.schema import HIERARCHY_ROLES, Document, Entity, EntityField, Relation
from drawspec.text.measure import TextMeasurer
from drawspec.text.wrap import Span, parse_spans
from drawspec.theme import Theme

#: What a field's key is drawn as: letters, never a colour or a symbol to learn.
KEY_MARKS: Final[Mapping[str, str]] = MappingProxyType(
    {"primary": "PK", "foreign": "FK", "unique": "UQ"}
)

#: A cardinality in `numeric` notation, as UML writes a multiplicity.
NUMBERS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "one": "1",
        "zero-or-one": "0..1",
        "many": "*",
        "zero-or-many": "0..*",
        "one-or-many": "1..*",
    }
)

#: How much of the canvas one entity may take across. Wider than a flow's box:
#: a schema's rows are a name and a type side by side, and do not wrap.
WIDTH_SHARE: Final = 0.45

#: The room every end is routed with, in head lengths: the longest crow's-foot
#: mark (a foot and a ring) and a little air, so whichever mark an end carries
#: has a straight run to sit on.
MARK_REACH: Final = 1.9

#: Crow's-foot geometry, in head lengths: how far the prongs and bars reach either
#: side of the line, and the radius of a ring.
MARK_SPREAD: Final = 0.6
RING: Final = 0.35

#: Straight pieces a ring is traced with: past what a reader can see at its size.
RING_SEGMENTS: Final = 24

#: The edge role every relation is *routed* in — never drawn in: one with an end
#: at both sides, so the router keeps a straight run at each for the marks.
ROUTING_ROLE: Final = "exchange"

#: The role a compartment's rules are drawn in: the box's own line, but never the
#: emphasised weight, which would make the rules louder than the outline.
RULE_ROLE: Final = "step"

#: Vertical air inside each compartment, as a share of `[box] padding` top.
COMPARTMENT: Final = 0.6

#: The least gap between a field's name and its type, in units (body size / 11).
TYPE_GAP: Final = 14.0

#: The gap between a key mark's column and the names, in units.
KEY_GAP: Final = 5.0


@dataclass(frozen=True)
class Row:
    """One line inside an entity: a field, or an operation (`field` is then `None`)."""

    text: str
    top: float
    """The top of the row's slot, measured from the box's top."""

    field: EntityField | None = None


@dataclass(frozen=True)
class EntityBox:
    """One entity, sized and (once placed) positioned: everything needed to draw it."""

    entity: Entity
    width: float
    height: float
    advance: float
    """The height of every row, and of the name's line."""

    rows: tuple[Row, ...]
    rules: tuple[float, ...]
    """Where each rule between compartments sits, measured from the box's top."""

    key_column: float
    """The width kept before the names for key marks; zero when no field has a key."""

    name_top: float
    tag_top: float
    ascent: float
    """The body face's ascent at the body size: what a row's baseline is set from."""

    descent: float
    x: float = 0.0
    y: float = 0.0

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def centre(self) -> tuple[float, float]:
        return self.x + self.width / 2, self.y + self.height / 2

    def row_centre(self, field_id: str) -> float:
        """The y of the middle of the row holding `field_id`, in drawing coordinates."""
        for row in self.rows:
            if row.field is not None and row.field.id == field_id:
                return self.y + row.top + self.advance / 2
        raise DrawspecError(f"{self.entity.id!r} has no field {field_id!r}")

    def moved_to(self, x: float, y: float) -> EntityBox:
        return replace(self, x=x, y=y)


@dataclass(frozen=True)
class Number:
    """One cardinality in `numeric` notation, placed: its text and its box."""

    text: str
    role: str
    left: float
    top: float
    width: float
    height: float
    ascent: float

    @property
    def box(self) -> tuple[float, float, float, float]:
        return self.left, self.top, self.left + self.width, self.top + self.height


@dataclass(frozen=True)
class EntitiesDrawing:
    """Everything an entity diagram is made of, in scene coordinates.

    A value of its own so a test can ask where a relation landed — on the row it
    named, or on the box — without reading it back out of the primitives.
    """

    boxes: Mapping[str, EntityBox]
    routes: tuple[Route, ...]
    """One per relation, in the order written, each in its relation's own role."""

    labels: tuple[Label, ...]
    numbers: tuple[Number, ...]
    width: float
    height: float
    direction: str


def entities_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Render an `entities` document to a `Scene`.

    Raises:
        FitError: an entity is wider than its share of the canvas, or the diagram
            does not fit in either direction at this type scale.
    """
    drawing = entities_drawing(document, theme, measurer)
    primitives: list[Primitive] = []
    for route, relation in zip(drawing.routes, document.relations, strict=True):
        primitives.extend(relation_primitives(route, relation, theme))
    for entity in document.entities:
        primitives.extend(entity_primitives(drawing.boxes[entity.id], theme, measurer))
    for label in drawing.labels:
        primitives.extend(label_primitives(label))
    for number in drawing.numbers:
        primitives.append(
            TextRun(
                number.role,
                x=number.left,
                y=number.top + number.ascent,
                text=number.text,
                level="label",
                font=theme.font.default,
            )
        )
    return Scene(
        width=drawing.width,
        height=drawing.height,
        primitives=tuple(primitives),
        title=document.title,
        description=document.description,
        metadata=(("direction", drawing.direction),),
    )


def entities_drawing(document: Document, theme: Theme, measurer: TextMeasurer) -> EntitiesDrawing:
    """Size, place, route and label every entity and relation."""
    if not document.entities:
        raise DrawspecError("an entities diagram needs at least one entity")
    width = document.width if document.width else theme.canvas.width
    sized = {
        entity.id: sized_entity(entity, theme, measurer, width * WIDTH_SHARE)
        for entity in document.entities
    }
    router = routing_theme(theme, document.relations)
    layout = _placed(document, sized, theme, measurer, router, width)
    boxes = {
        identifier: box.moved_to(layout.placements[identifier].x, layout.placements[identifier].y)
        for identifier, box in sized.items()
    }
    obstacles = tuple(
        Obstacle(identifier, x=box.x, y=box.y, width=box.width, height=box.height)
        for identifier, box in sorted(boxes.items())
    )
    # Each relation is routed the way it was ranked — general to specific, one to
    # many — so the router sees every line going with the drawing's direction
    # rather than taking the upward ones for returns and sending them round the
    # outside; the route is turned back to the author's direction afterwards.
    used: dict[tuple[str, str], int] = {}
    connectors = tuple(_connector(relation, boxes, used) for relation in document.relations)
    routed = route_edges(connectors, obstacles, router, direction=layout.direction)
    routes = tuple(
        replace(
            route,
            source=relation.source,
            target=relation.target,
            role=relation.role,
            points=route.points if route.source == relation.source else route.points[::-1],
        )
        for route, relation in zip(routed, document.relations, strict=True)
    )

    numbers: list[Number] = []
    zones: list[Obstacle] = []
    for index, (route, relation) in enumerate(zip(routes, document.relations, strict=True)):
        for end, cardinality in (("source", relation.source_end), ("target", relation.target_end)):
            if not cardinality:
                continue
            tip, previous = _end(route, end)
            if theme.entities.notation == "numeric":
                number = _numbered(
                    NUMBERS[cardinality],
                    route.role,
                    tip,
                    previous,
                    (*obstacles, *zones),
                    routes,
                    theme,
                    measurer,
                )
                numbers.append(number)
                zones.append(_box_obstacle(number.box, f"\x00number {index} {end}"))
            else:
                zones.append(
                    _mark_zone(tip, previous, route.role, theme, f"\x00mark {index} {end}")
                )
    labels = place_labels(routes, (*obstacles, *zones), theme, measurer)
    return _framed(boxes, routes, labels, tuple(numbers), layout.direction)


# ---------------------------------------------------------------------------
# Sizing
# ---------------------------------------------------------------------------


def sized_entity(entity: Entity, theme: Theme, measurer: TextMeasurer, limit: float) -> EntityBox:
    """One entity's box at the origin: its compartments, rows and width.

    Raises:
        FitError: its widest row does not fit `limit`. Rows never wrap — a field
            is one name and one type — so the remedy is a shorter name, and the
            message names the row.
    """
    pad = theme.box.padding
    unit = theme.scale["body"] / 11
    body, label = theme.scale["body"], theme.scale["label"]
    advance = theme.box.line_height * body
    air = pad.top * COMPARTMENT
    sans = theme.font.default

    def spans_width(spans: Sequence[Span]) -> float:
        return sum(
            measurer.measure(span.text, span.font, body, span.weight).width for span in spans
        )

    keys = [KEY_MARKS[field.key] for field in entity.fields if field.key]
    key_column = (
        max(measurer.measure(mark, sans, label, "bold").width for mark in keys) + KEY_GAP * unit
        if keys
        else 0.0
    )
    widths: list[tuple[float, str]] = [
        (spans_width(name_spans(entity.text, sans)), entity.text),
    ]
    if entity.tag:
        widths.append((measurer.measure(tag_text(entity.tag), sans, body).width, entity.tag))
    for field in entity.fields:
        row = key_column + spans_width(parse_spans(field.text, font=sans))
        if field.type:
            row += TYPE_GAP * unit + measurer.measure(field.type, "mono", body).width
        widths.append((row, field.text))
    for operation in entity.operations:
        widths.append((spans_width(parse_spans(operation, font=sans)), operation))
    content, widest = max(widths)
    width = content + pad.horizontal
    if width > limit:
        raise FitError(
            f"the entity {entity.id!r} needs {width:.0f} across for {widest[:40]!r} and may take "
            f"{limit:.0f}: a row is one line and never wraps. Shorten that row, or give the "
            f"diagram more width."
        )

    metrics = measurer.measure("", sans, body)
    tag_top = air
    name_top = air + (advance if entity.tag else 0.0)
    top = name_top + advance + air
    rows: list[Row] = []
    rules: list[float] = []
    compartments: tuple[list[tuple[str, EntityField | None]], ...] = (
        [(field.text, field) for field in entity.fields],
        [(operation, None) for operation in entity.operations],
    )
    for compartment in compartments:
        if not compartment:
            continue
        rules.append(top)
        top += air
        for text, held in compartment:
            rows.append(Row(text=text, top=top, field=held))
            top += advance
        top += air
    return EntityBox(
        entity=entity,
        width=width,
        height=top,
        advance=advance,
        rows=tuple(rows),
        rules=tuple(rules),
        key_column=key_column,
        name_top=name_top,
        tag_top=tag_top,
        ascent=metrics.ascent,
        descent=metrics.descent,
    )


def name_spans(text: str, font: str) -> tuple[Span, ...]:
    """An entity's name as drawn: bold, a `code` span in the code face's bold."""
    return tuple(
        Span(span.text, font=span.font, weight="bold") for span in parse_spans(text, font=font)
    )


def tag_text(tag: str) -> str:
    """A stereotype as drawn: in guillemets."""
    return f"«{tag}»"


# ---------------------------------------------------------------------------
# Placement and routing
# ---------------------------------------------------------------------------


def routing_theme(theme: Theme, relations: Sequence[Relation] = ()) -> Theme:
    """`theme` as the router should see it: every end needing room for a full mark.

    The router reserves a straight run at each end of a route as long as that
    end's head. A relation's end may carry a ring and a foot, which is longer than
    any arrow head, so relations are routed in one role with a head at both ends
    and a head length of the longest mark any of them draws — and drawn in their
    own role afterwards.
    """
    reach = MARK_REACH * max(
        (mark_length(relation.role, theme) for relation in relations),
        default=theme.edge.head_length,
    )
    return replace(
        theme,
        edge=replace(theme.edge, head_length=reach),
        edge_roles=MappingProxyType({ROUTING_ROLE: theme.edge_roles[ROUTING_ROLE]}),
    )


def mark_length(role: str, theme: Theme) -> float:
    """The length a crow's foot is drawn at on a line of `role`.

    The theme's head length, grown in proportion on a heavier line as an arrow
    head is — a foot drawn at a `strong` line's weight and an arrow's size is a
    blot — but never shrunk on a lighter one: the marks are what a reader counts,
    and a `link` is the line most of them sit on.
    """
    width = theme.edge_roles[role].stroke_width
    return theme.edge.head_length * max(1.0, width / theme.edge.stroke_width)


#: The cardinalities whose most is more than one.
MANY: Final = ("many", "zero-or-many", "one-or-many")


def ranked_forward(relation: Relation) -> bool:
    """Whether a relation is ranked from its `from` entity to its `to` entity.

    A hierarchy is ranked general first, so `inherits` and `realizes` — written
    from the specific class — are ranked backwards. A relation with many at its
    `from` end and not at its `to` end is too: the one side of a relation comes
    before its many side, whichever way the author wrote it, so a foreign key
    drawn from its column reads from the table it refers to.
    """
    if relation.role in HIERARCHY_ROLES:
        return False
    return not (relation.source_end in MANY and relation.target_end not in MANY)


def _placed(
    document: Document,
    boxes: Mapping[str, EntityBox],
    theme: Theme,
    measurer: TextMeasurer,
    router: Theme,
    width: float,
) -> Layout:
    """The layered engine's placement: general above specific, else across.

    Raises:
        FitError: neither direction fits the canvas at this type scale.
    """
    hierarchy = any(relation.role in HIERARCHY_ROLES for relation in document.relations)
    pairs: dict[tuple[str, str], None] = {}
    for relation in document.relations:
        pair = (
            (relation.source, relation.target)
            if ranked_forward(relation)
            else (relation.target, relation.source)
        )
        if pair not in pairs and pair[::-1] not in pairs:
            pairs[pair] = None
    base = Spacing(
        node_gap=theme.box.padding.horizontal * 1.5,
        rank_gap=max(minimum_rank_gap(router), theme.box.padding.horizontal * 2),
    )
    # Read across, a relation's label sits on the line between two ranks, so the
    # gap is widened to hold the widest label between the two ends' marks; read
    # down, it sits beside the line and the plain gap is enough.
    widest = max(
        (
            label_extents(relation.label, theme, measurer)[0]
            for relation in document.relations
            if relation.label
        ),
        default=0.0,
    )
    across = replace(
        base,
        rank_gap=max(
            base.rank_gap,
            widest + router.edge.head_length * 2 + LABEL_GAP * 4 if widest else 0.0,
        ),
    )
    nodes = [LayoutNode(identifier, box.width, box.height) for identifier, box in boxes.items()]
    edges = [LayoutEdge(source, target) for source, target in pairs]
    ceiling = (document.height or 0.0) if document.height_binding else 0.0
    prefer = "down" if hierarchy else "right"
    other = "right" if prefer == "down" else "down"

    def attempt(direction: str, extra: float = 0.0) -> Layout:
        spacing = across if direction == "right" else base
        engine = LayeredEngine(replace(spacing, rank_gap=spacing.rank_gap + extra))
        return best_layout(
            engine, nodes, edges, max_width=width, prefer=direction, max_height=ceiling
        )

    # `best_layout` falls back to the other direction by itself, but with this
    # direction's spacing; so the other direction is asked for in its own.
    layout = attempt(prefer)
    if not (layout.fits and layout.direction == prefer):
        second = attempt(other)
        layout = second if second.fits or not layout.fits else layout
    # A gap that many relations cross needs a lane for each to turn in, or lane
    # separation runs out of room and lines are drawn one over another.
    crowd = _crowding(layout, list(pairs))
    if layout.fits and crowd > CROWD:
        roomier = attempt(layout.direction, (crowd - CROWD) * theme.edge.lane_spacing)
        if roomier.fits and roomier.direction == layout.direction:
            layout = roomier
    if not layout.fits:
        raise FitError(
            f"this entities diagram needs {layout.width:.0f} at its narrowest and the canvas "
            f"is {width:.0f}. Both directions were tried. Shorten the widest rows, split the "
            f"diagram by subsystem, or give it more width."
        )
    return layout


#: How many relations may cross one gap between ranks before it is widened by a
#: lane for each further one.
CROWD: Final = 2


def _crowding(layout: Layout, pairs: Sequence[tuple[str, str]]) -> int:
    """The most relations crossing any one gap between neighbouring ranks."""
    counts: dict[int, int] = {}
    for first, second in pairs:
        low, high = sorted((layout.placements[first].rank, layout.placements[second].rank))
        for gap in range(low, high):
            counts[gap] = counts.get(gap, 0) + 1
    return max(counts.values(), default=0)


def _connector(
    relation: Relation, boxes: Mapping[str, EntityBox], used: dict[tuple[str, str], int]
) -> Connector:
    """A relation as the router takes it, with a fixed port for each end naming a field.

    `used` counts the row-anchored ends already on each side of each box, so two
    relations between boxes one above the other take opposite sides rather than
    crossing on the same one.
    """
    first, second = (relation.source, relation.target)
    first_field, second_field = (relation.source_field, relation.target_field)
    if not ranked_forward(relation):
        first, second = second, first
        first_field, second_field = second_field, first_field
    source, target = boxes[first], boxes[second]
    side, other = _facing(source, target, used)
    for identifier, named, taken in ((first, first_field, side), (second, second_field, other)):
        if named:
            used[(identifier, taken)] = used.get((identifier, taken), 0) + 1
    return Connector(
        first,
        second,
        role=ROUTING_ROLE,
        label=relation.label,
        source_port=(
            _general_port(source, target)
            if relation.role in HIERARCHY_ROLES
            else _row_port(source, first_field, side)
        ),
        target_port=_row_port(target, second_field, other),
    )


def _general_port(general: EntityBox, specific: EntityBox) -> tuple[str, float]:
    """Where a hierarchy line meets its general class: the middle of the facing side.

    Every subclass's line arrives at the same point, so their triangles are drawn
    one over another as one, and the lines share a trunk out of it — the tree a
    class diagram draws, rather than a row of triangles side by side.
    """
    if specific.y >= general.bottom:
        return "bottom", 0.5
    if specific.bottom <= general.y:
        return "top", 0.5
    return ("right" if specific.x >= general.right else "left"), 0.5


def _facing(
    source: EntityBox, target: EntityBox, used: Mapping[tuple[str, str], int]
) -> tuple[str, str]:
    """The sides a row-anchored line leaves `source` by and reaches `target` by.

    Facing each other when the boxes stand apart across the page. When one is
    above the other both ends take the same side, so the line goes out, along and
    back in, as a schema draws it, rather than out one side and round to the
    other: the side fewer such lines already use, then the one towards the other
    box's centre, then the right.
    """
    if target.x >= source.right:
        return "right", "left"
    if target.right <= source.x:
        return "left", "right"

    def load(side: str) -> int:
        return used.get((source.entity.id, side), 0) + used.get((target.entity.id, side), 0)

    toward = "right" if target.centre[0] >= source.centre[0] else "left"
    away = "left" if toward == "right" else "right"
    side = away if load(away) < load(toward) else toward
    return side, side


def _row_port(box: EntityBox, field_id: str, side: str) -> tuple[str, float] | None:
    if not field_id:
        return None
    return side, (box.row_centre(field_id) - box.y) / box.height


def _end(route: Route, end: str) -> tuple[tuple[float, float], tuple[float, float]]:
    """An end's tip on the border, and the point before it along the route."""
    if end == "target":
        return route.points[-1], route.points[-2]
    return route.points[0], route.points[1]


def _box_obstacle(box: tuple[float, float, float, float], identifier: str) -> Obstacle:
    left, top, right, bottom = box
    return Obstacle(identifier, x=left, y=top, width=right - left, height=bottom - top)


def _mark_zone(
    tip: tuple[float, float],
    previous: tuple[float, float],
    role: str,
    theme: Theme,
    identifier: str,
) -> Obstacle:
    """The patch of paper an end's crow's foot covers, for labels to keep off."""
    length = mark_length(role, theme)
    reach = length * MARK_REACH
    spread = length * MARK_SPREAD
    far = _along(tip, previous, reach)
    xs = (tip[0], far[0])
    ys = (tip[1], far[1])
    horizontal = abs(tip[1] - previous[1]) < abs(tip[0] - previous[0])
    left, right = min(xs) - (0 if horizontal else spread), max(xs) + (0 if horizontal else spread)
    top, bottom = min(ys) - (spread if horizontal else 0), max(ys) + (spread if horizontal else 0)
    return Obstacle(identifier, x=left, y=top, width=right - left, height=bottom - top)


def _numbered(
    text: str,
    role: str,
    tip: tuple[float, float],
    previous: tuple[float, float],
    obstacles: Sequence[Obstacle],
    routes: Sequence[Route],
    theme: Theme,
    measurer: TextMeasurer,
) -> Number:
    """A multiplicity beside its end: just outside the box, off the line.

    Above a line that arrives across the page and beside one that arrives down
    it, on whichever side is clear of boxes and other lines — tried in that order,
    and the first kept if none is.
    """
    extents = measurer.measure(text, theme.font.default, theme.scale["label"])
    width, height = extents.width, extents.height
    gap = LABEL_GAP
    away = (previous[0] - tip[0], previous[1] - tip[1])
    horizontal = abs(away[0]) >= abs(away[1])
    if horizontal:
        left = tip[0] + gap if away[0] > 0 else tip[0] - gap - width
        candidates = [(left, tip[1] - gap - height), (left, tip[1] + gap)]
    else:
        top = tip[1] + gap if away[1] > 0 else tip[1] - gap - height
        candidates = [(tip[0] + gap, top), (tip[0] - gap - width, top)]
    segments = [segment for route in routes for segment in route.segments]
    for left, top in candidates:
        # Tested with air round it, so a line merely grazing the number is not
        # taken as clear — the clearance pass would break that line under it.
        air = gap / 2
        box = (left - air, top - air, left + width + air, top + height + air)
        if any(obstacle.overlaps(box) for obstacle in obstacles):
            continue
        if any(_meets(box, first, second) for first, second in segments):
            continue
        break
    else:
        left, top = candidates[0]
    return Number(text, role, left, top, width, height, extents.ascent)


def _meets(
    box: tuple[float, float, float, float],
    first: tuple[float, float],
    second: tuple[float, float],
) -> bool:
    """Whether an axis-aligned segment passes through `box`'s interior."""
    left, right = sorted((first[0], second[0]))
    top, bottom = sorted((first[1], second[1]))
    return left < box[2] and right > box[0] and top < box[3] and bottom > box[1]


def _framed(
    boxes: Mapping[str, EntityBox],
    routes: Sequence[Route],
    labels: Sequence[Label],
    numbers: Sequence[Number],
    direction: str,
) -> EntitiesDrawing:
    """Everything shifted so the drawing starts at its own ink, and measured."""
    xs = [value for box in boxes.values() for value in (box.x, box.right)]
    ys = [value for box in boxes.values() for value in (box.y, box.bottom)]
    xs += [x for route in routes for x, _ in route.points]
    ys += [y for route in routes for _, y in route.points]
    for left, top, right, bottom in (*(label.box for label in labels), *(n.box for n in numbers)):
        xs += [left, right]
        ys += [top, bottom]
    dx, dy = -min(xs), -min(ys)
    return EntitiesDrawing(
        boxes={
            identifier: box.moved_to(box.x + dx, box.y + dy) for identifier, box in boxes.items()
        },
        routes=tuple(
            replace(route, points=tuple((x + dx, y + dy) for x, y in route.points))
            for route in routes
        ),
        labels=tuple(replace(label, left=label.left + dx, top=label.top + dy) for label in labels),
        numbers=tuple(
            replace(number, left=number.left + dx, top=number.top + dy) for number in numbers
        ),
        width=max(xs) + dx,
        height=max(ys) + dy,
        direction=direction,
    )


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------


def entity_primitives(
    box: EntityBox, theme: Theme, measurer: TextMeasurer
) -> tuple[Primitive, ...]:
    """An entity's outline, its rules, its name and every row."""
    del measurer  # the box was measured when it was sized
    role = box.entity.role
    pad = theme.box.padding
    sans = theme.font.default
    body = theme.scale["body"]
    drawn: list[Primitive] = []
    if theme.roles[role].shape == "none":
        # A note entity is drawn lighter: its own dashed line round it, since its
        # role has no shape of its own and the rows still need a box to sit in.
        corners = (
            (box.x, box.y),
            (box.right, box.y),
            (box.right, box.bottom),
            (box.x, box.bottom),
        )
        drawn.append(Path(role, points=corners, closed=True))
        rule_role = role
    else:
        drawn.append(Rect(role, x=box.x, y=box.y, width=box.width, height=box.height))
        rule_role = RULE_ROLE
    for offset in box.rules:
        drawn.append(Path(rule_role, points=((box.x, box.y + offset), (box.right, box.y + offset))))

    middle = box.x + box.width / 2

    def baseline(top: float, size: float, advance: float) -> float:
        scale = size / body
        return box.y + top + (advance + (box.ascent - box.descent) * scale) / 2

    if box.entity.tag:
        drawn.append(
            TextLine(
                role,
                x=middle,
                y=baseline(box.tag_top, body, box.advance),
                spans=(TextSpan(text=tag_text(box.entity.tag), font=sans),),
                level="body",
                anchor="middle",
            )
        )
    drawn.append(
        TextLine(
            role,
            x=middle,
            y=baseline(box.name_top, body, box.advance),
            spans=_spans(name_spans(box.entity.text, sans)),
            level="body",
            anchor="middle",
        )
    )
    left = box.x + pad.left
    for row in box.rows:
        y = baseline(row.top, body, box.advance)
        field = row.field
        if field is not None and field.placeholder:
            drawn.append(
                TextRun(role, x=left + box.key_column, y=y, text="…", level="body", font=sans)
            )
            continue
        if field is not None and field.key:
            drawn.append(
                TextRun(
                    role,
                    x=left,
                    y=y,
                    text=KEY_MARKS[field.key],
                    level="label",
                    font=sans,
                    weight="bold",
                )
            )
        drawn.append(
            TextLine(
                role,
                x=left + (box.key_column if field is not None else 0.0),
                y=y,
                spans=_spans(parse_spans(row.text, font=sans)),
                level="body",
                anchor="start",
            )
        )
        if field is not None and field.type:
            drawn.append(
                TextRun(
                    role,
                    x=box.right - pad.right,
                    y=y,
                    text=field.type,
                    level="body",
                    font="mono",
                    anchor="end",
                )
            )
    return tuple(drawn)


def _spans(spans: Sequence[Span]) -> tuple[TextSpan, ...]:
    return tuple(
        TextSpan(text=span.text, font=span.font, weight=span.weight) for span in spans if span.text
    )


def relation_primitives(route: Route, relation: Relation, theme: Theme) -> tuple[Primitive, ...]:
    """A relation's line and what is drawn at its ends.

    An end with a cardinality draws it — crow's feet, or nothing here when the
    theme writes numbers, which are text — in place of the role's head; an end
    without one draws the role's own treatment. A ring is not filled, so the line
    is broken under it rather than drawn through it.
    """
    role = theme.edge_roles[route.role]
    numeric = theme.entities.notation == "numeric"
    points = list(route.points)
    drawn: list[Primitive] = []
    stubs: list[Primitive] = []
    for end, cardinality, treatment in (
        ("source", relation.source_end, role.tail),
        ("target", relation.target_end, role.head),
    ):
        tip, previous = _end(route, end)
        cut: tuple[float, float] | None = None
        if cardinality and not numeric:
            marks, ring = _crowsfoot(cardinality, tip, previous, route.role, theme)
            drawn.extend(marks)
            if ring is not None:
                near, far = ring
                stubs.append(
                    Path(route.role, points=(_along(tip, previous, near), tip), marker=True)
                )
                cut = _along(tip, previous, far)
        elif not cardinality and treatment != "none":
            drawn.extend(end_marker(treatment, previous, tip, route.role, theme))
            if treatment == "triangle":
                cut = hollow_base(previous, tip, route.role, theme)
        if cut is not None:
            if end == "target":
                points[-1] = cut
            else:
                points[0] = cut
    # A hierarchy's lines share a trunk out of the general class, so each is drawn
    # from that end: a dashed `realizes` then starts its dashes at the same point
    # as its siblings', and the shared trunk stays dashed instead of filling in.
    if relation.role in HIERARCHY_ROLES:
        points.reverse()
    return (Path(route.role, points=tuple(points)), *stubs, *drawn)


def _crowsfoot(
    cardinality: str,
    tip: tuple[float, float],
    previous: tuple[float, float],
    role: str,
    theme: Theme,
) -> tuple[list[Primitive], tuple[float, float] | None]:
    """The marks for one end, and where a ring breaks the line (near, far), if any.

    Read from the box outwards: the mark nearest the box says the most there can
    be — a bar for one, a foot for many — and the one beyond it the least — a bar
    for one, a ring for none. `many` alone says nothing about the least.
    """
    length = mark_length(role, theme)
    spread = length * MARK_SPREAD
    radius = length * RING
    span = math.dist(previous, tip) or 1.0
    ux, uy = (tip[0] - previous[0]) / span, (tip[1] - previous[1]) / span
    nx, ny = -uy, ux

    def at(back: float, across: float) -> tuple[float, float]:
        return (tip[0] - ux * back + nx * across, tip[1] - uy * back + ny * across)

    def bar(back: float) -> Primitive:
        return Path(role, points=(at(back, spread), at(back, -spread)), marker=True)

    many = cardinality in ("many", "zero-or-many", "one-or-many")
    marks: list[Primitive] = []
    if many:
        marks.append(
            Path(role, points=(at(0.0, spread), at(length, 0.0), at(0.0, -spread)), marker=True)
        )
    else:
        marks.append(bar(length * 0.45))
    beyond = length * (1.25 if many else 0.8)
    ring: tuple[float, float] | None = None
    if cardinality in ("one", "one-or-many"):
        marks.append(bar(beyond))
    elif cardinality in ("zero-or-one", "zero-or-many"):
        centre = at(beyond + radius, 0.0)
        # Traced as an open path back to its start rather than drawn as an
        # ellipse: a mark is solid on a dashed line, and only a path says it is one.
        marks.append(
            Path(
                role,
                points=tuple(
                    (
                        centre[0] + radius * math.cos(math.tau * step / RING_SEGMENTS),
                        centre[1] + radius * math.sin(math.tau * step / RING_SEGMENTS),
                    )
                    for step in range(RING_SEGMENTS + 1)
                ),
                marker=True,
            )
        )
        ring = (beyond, beyond + radius * 2)
    return marks, ring


def _along(
    tip: tuple[float, float], previous: tuple[float, float], distance: float
) -> tuple[float, float]:
    """The point `distance` back from `tip` towards `previous`."""
    span = math.dist(previous, tip) or 1.0
    return (
        tip[0] + (previous[0] - tip[0]) / span * distance,
        tip[1] + (previous[1] - tip[1]) / span * distance,
    )


__all__ = [
    "KEY_MARKS",
    "MARK_REACH",
    "NUMBERS",
    "EntitiesDrawing",
    "EntityBox",
    "Number",
    "Row",
    "entities_drawing",
    "entities_scene",
    "entity_primitives",
    "relation_primitives",
    "routing_theme",
    "sized_entity",
]

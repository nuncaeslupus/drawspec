"""The input document: the model, the validator, and the published JSON Schema.

This is the contract that is most expensive to change, because documents written
against it live in the consumer's repository. Three properties matter more than
anything else in this module.

**What the author may not write is the point.** Coordinates, type sizes,
colours, arrow-head geometry and z-order are all decisions that require seeing
the output, and an author working blind cannot take them. So there is no field
for any of them — and, because every object sets `additionalProperties: false`,
writing one is an error that names the field rather than a key that is silently
dropped. A silently dropped key is the worst outcome available: the author
believes they configured something.

**One description, two renderings.** The field tables below are the single
source of truth. `parse_document` validates against them at runtime and
`build_schema` renders them as JSON Schema, so the published artefact cannot
drift from the tool. An editor's completion and `drawspec validate` are
therefore never in disagreement — which is the whole reason to publish a schema
rather than prose.

**Violations are located, not just named.** Each one carries a JSON pointer
(`/nodes/2/font_size`), the way an HTML validator names a line and an attribute,
and `validate_document` returns all of them rather than stopping at the first.

One class of check is deliberately outside the schema: referential integrity —
an edge naming a node that does not exist, or two nodes sharing an id. JSON
Schema cannot express it, so the parser enforces it alone and the schema
documents the gap rather than pretending to cover it.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from drawspec.errors import DocumentError
from drawspec.theme import EDGE_ROLES, NODE_ROLES

#: The document format version this module reads.
DOCUMENT_VERSION: Final = 1

#: The published schema's stable identifier. A document that carries
#: `"$schema": "<this>"` gets completion and inline errors in any editor with
#: JSON Schema support — the author is told `font_size` is not allowed *while
#: typing it*, rather than after a render.
SCHEMA_ID: Final = "https://drawspec.dev/schema/drawspec-v1.schema.json"

#: Where the generated artefact is committed, relative to the repository root.
SCHEMA_FILENAME: Final = "drawspec-v1.schema.json"

GRAPH_KINDS: Final = ("flow", "tree", "cycle")
GRID_KINDS: Final = ("stack", "timeline", "columns", "matrix")
SHAPE_KINDS: Final = ("pyramid", "rings", "funnel")
CHART_KINDS: Final = ("chart", "quadrant", "curve")

#: How a series may be drawn. `line` is the default and was the only one until
#: the corpus asked for the others; `area` is a line whose fill reaches the
#: baseline, and `bar` is a column per point. Closed, like every other
#: vocabulary here.
MARKS: Final = ("line", "bar", "area")

#: The order a chart's axes are held in, so `Document.axes` is not a mapping
#: whose iteration order a reader has to trust.
AXIS_ORDER: Final = ("horizontal", "vertical")

#: The kinds. Closed: a new one needs evidence, not a preference — and the
#: evidence is `docs/kinds-wanted.md`, which sorts the 89 hand-drawn originals by
#: the kind that would have to draw them. The four that opened the vocabulary
#: from nine to thirteen — `matrix`, `funnel`, `quadrant`, `curve` — each cleared
#: originals nothing here could draw.
KINDS: Final = GRAPH_KINDS + GRID_KINDS + SHAPE_KINDS + CHART_KINDS

#: Fields an author might reach for that drawspec refuses, and why. Not used for
#: validation — `additionalProperties: false` already rejects them — but for the
#: message, which is the teaching surface for an author working blind.
REJECTED_FIELDS: Final = {
    "x": "coordinates are the tool's output, never its input",
    "y": "coordinates are the tool's output, never its input",
    "cx": "coordinates are the tool's output, never its input",
    "cy": "coordinates are the tool's output, never its input",
    "points": "coordinates are the tool's output, never its input",
    "d": "coordinates are the tool's output, never its input",
    "width": "box geometry is derived from measured text plus theme padding",
    "height": "box geometry is derived from measured text plus theme padding",
    "font_size": "type is selected by semantic role from the theme's scale",
    "font_family": "type is selected by semantic role from the theme's scale",
    "font_weight": "type is selected by semantic role from the theme's scale",
    "color": "appearance is a property of the role, not of the element",
    "fill": "appearance is a property of the role, not of the element",
    "stroke": "appearance is a property of the role, not of the element",
    "stroke_width": "appearance is a property of the role, not of the element",
    "anchor": "edge geometry comes from the edge's semantic role",
    "port": "edge geometry comes from the edge's semantic role",
    "arrow_head": 'say role: "link", not arrow_head: "none" — head geometry is the theme\'s',
    "dash": "line treatment comes from the edge's semantic role",
    "dx": "coordinates are the tool's output, never its input",
    "dy": "coordinates are the tool's output, never its input",
    "z": "overlap is resolved by the layout, not declared",
    "order": "overlap is resolved by the layout, not declared",
    "layer": "overlap is resolved by the layout, not declared",
    "viewBox": "derived from width and the content",
    "canvas": "derived from width and the content",
}


# ---------------------------------------------------------------------------
# The field tables — the single source of truth for both renderings
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FieldSpec:
    """One field: what it is called, what it may hold, whether it is required."""

    name: str
    kind: str
    """`string`, `number`, `integer`, `boolean`, `array` or `object`."""

    required: bool = False
    enum: tuple[str, ...] = ()
    ref: str = ""
    """For `object`: the name of the object table this field holds."""

    item_ref: str = ""
    """For `array`: the name of the object table each element holds."""

    item_kind: str = ""
    """For `array` of scalars: `string`, or `point` for an [x, y] pair."""

    min_items: int = 0
    exclusive_minimum: float | None = None
    description: str = ""


def _text(name: str = "text", *, required: bool = True) -> FieldSpec:
    return FieldSpec(
        name,
        "string",
        required=required,
        description=(
            "The words themselves. May carry inline spans — `code` for the monospace "
            "role and **bold** for emphasis — because those are semantic, not typographic. "
            "A newline says this label is a lead and a detail rather than one sentence; "
            "the theme's `[box] lead` decides what the first paragraph looks like. Prefer "
            "it to punctuating the two apart inside one line."
        ),
    )


#: What `note` is for, and — the part that matters — where it is actually drawn.
#:
#: `timeline` puts an entry's note under the axis: above the line is the event,
#: below it is when. **No other kind draws one.** Saying so here is the whole of
#: the fix available inside v1: the field is accepted by every object that
#: accepted it before, because a document that validated against the published
#: v1 schema has to keep validating against it, and removing a field is a change
#: of meaning that ships as v2. What can change now is that an author reads this
#: before writing one, in their editor, rather than finding out by rendering and
#: seeing nothing.
_NOTE_DESCRIPTION: Final = (
    "A short aside attached to this element. **Only `timeline` draws one** — it goes "
    "under the axis, beside the entry's own mark. Every other kind accepts the field "
    "and has nowhere to put it, so it is not drawn; for text belonging to the whole "
    "diagram, use the top-level `caption` instead."
)


def _role(vocabulary: tuple[str, ...], default: str) -> FieldSpec:
    return FieldSpec(
        "role",
        "string",
        enum=vocabulary,
        description=(
            f"The semantic role, which the theme resolves to an appearance. "
            f"Defaults to {default!r}."
        ),
    )


#: Objects a document is built from. Every one sets `additionalProperties: false`.
OBJECTS: Final[Mapping[str, tuple[FieldSpec, ...]]] = {
    "node": (
        FieldSpec("id", "string", required=True, description="Unique within the document."),
        FieldSpec(
            "centre",
            "boolean",
            description=(
                "Whether this node is the subject the rest are arranged around. One node "
                "per document may say so, and only a `flow`. For the diagram that starts "
                "in the middle rather than at the top: a thing with named relations on "
                "every side, where the relations are peers and there is no sequence "
                "between them. Ranked instead, the middle object becomes just another row."
            ),
        ),
        _text(),
        _role(NODE_ROLES, "step"),
        FieldSpec("note", "string", description=_NOTE_DESCRIPTION),
    ),
    "edge": (
        FieldSpec("from", "string", required=True, description="The id of the source node."),
        FieldSpec("to", "string", required=True, description="The id of the target node."),
        FieldSpec("label", "string", description="A short label placed along the edge."),
        _role(EDGE_ROLES, "flow"),
    ),
    "group": (
        FieldSpec("id", "string", required=True, description="Unique within the document."),
        _text(required=False),
        FieldSpec(
            "members",
            "array",
            required=True,
            item_kind="string",
            min_items=1,
            description=(
                "The ids of the nodes this group contains, in the order they are "
                "meant to read — the members of a container are an ordered set."
            ),
        ),
    ),
    "band": (
        _text(required=True),
        FieldSpec(
            "members",
            "array",
            required=True,
            item_kind="string",
            min_items=1,
            description=(
                "The ids of the nodes this band accompanies. Unlike a group's, they "
                "are a set rather than a container: a band names something that runs "
                "alongside those boxes, and the same box may be under any number of "
                "bands."
            ),
        ),
    ),
    "item": (
        FieldSpec("id", "string", description="Optional; generated from position when absent."),
        _text(),
        _role(NODE_ROLES, "step"),
        FieldSpec("note", "string", description=_NOTE_DESCRIPTION),
        FieldSpec(
            "at",
            "number",
            description=(
                "For `timeline`: when this happened, so the gaps mean something. "
                "Give it to every entry or to none."
            ),
        ),
    ),
    "level": (
        _text(),
        _role(NODE_ROLES, "step"),
        FieldSpec("note", "string", description=_NOTE_DESCRIPTION),
    ),
    "ring": (
        _text(),
        _role(NODE_ROLES, "step"),
    ),
    "cell": (
        FieldSpec(
            "id",
            "string",
            description=(
                "Optional, and only needed to join this cell to another: an edge names "
                "the two cells it runs between. Unique within the document."
            ),
        ),
        _text(),
        FieldSpec(
            "column",
            "integer",
            required=True,
            description="Which column this cell starts in, counting from zero.",
        ),
        FieldSpec(
            "row", "integer", required=True, description="Which row it starts in, from zero."
        ),
        FieldSpec("across", "integer", description="How many columns it covers. Default 1."),
        FieldSpec("down", "integer", description="How many rows it covers. Default 1."),
        FieldSpec(
            "group",
            "string",
            description=(
                "Which group this cell belongs to. Cells sharing a group are filled "
                "alike; the theme decides how. Naming the fill itself is not an "
                "author's decision."
            ),
        ),
        _role(NODE_ROLES, "step"),
    ),
    "waypoint": (
        FieldSpec(
            "id",
            "string",
            description=(
                "Optional, and only needed to measure from this point: a span names the "
                "two waypoints it runs between. Unique within the document."
            ),
        ),
        FieldSpec(
            "text",
            "string",
            description="What to call this point. Omit for a point that only shapes the curve.",
        ),
        FieldSpec(
            "across",
            "number",
            required=True,
            description="Where this sits on the horizontal axis. Data, not a coordinate.",
        ),
        FieldSpec(
            "up",
            "number",
            required=True,
            description="Where this sits on the vertical axis. Data, not a coordinate.",
        ),
    ),
    "curve": (
        FieldSpec(
            "name",
            "string",
            description=(
                "Drawn where the curve ends. Omit it when there is only one curve "
                "and the axes already say what it is."
            ),
        ),
        FieldSpec(
            "waypoints",
            "array",
            required=True,
            item_ref="waypoint",
            min_items=2,
            description="The points the curve passes through, in order. Two is a line.",
        ),
        _role(NODE_ROLES, "step"),
    ),
    "position": (
        _text(),
        FieldSpec(
            "across",
            "number",
            required=True,
            description="Where this sits on the horizontal axis. Data, not a coordinate.",
        ),
        FieldSpec(
            "up",
            "number",
            required=True,
            description="Where this sits on the vertical axis. Data, not a coordinate.",
        ),
        _role(NODE_ROLES, "step"),
    ),
    "stage": (
        _text(),
        _role(NODE_ROLES, "step"),
        FieldSpec(
            "gate",
            "string",
            description=(
                "What stands between this stage and the next — the threshold a thing "
                "has to pass to get from one to the other, which is what makes a "
                "stage-gate model one. Drawn on the divider, which breaks to let it "
                "through. The last stage has no next stage, so it may not carry one."
            ),
        ),
        FieldSpec("note", "string", description=_NOTE_DESCRIPTION),
    ),
    "span": (
        _text(),
        FieldSpec(
            "from",
            "string",
            required=True,
            description="The id of the entry the interval starts at.",
        ),
        FieldSpec(
            "to",
            "string",
            required=True,
            description="The id of the entry it ends at. Must come after `from`.",
        ),
    ),
    "key": (
        FieldSpec(
            "group",
            "string",
            required=True,
            description="Which group this names. Some cell must belong to it.",
        ),
        _text(),
    ),
    "axis": (
        FieldSpec(
            "label",
            "string",
            required=True,
            description="Required: an unlabelled axis cannot be read.",
        ),
        FieldSpec(
            "unit", "string", description="What the numbers are in, written after the label."
        ),
        FieldSpec(
            "min",
            "number",
            description="Where the axis starts. Omit to take it from the data.",
        ),
        FieldSpec(
            "max",
            "number",
            description="Where the axis ends. Omit to take it from the data.",
        ),
        FieldSpec(
            "categories",
            "array",
            item_kind="string",
            description=(
                "Names for the positions 1, 2, 3 … along this axis, instead of "
                "numbers. What a bar chart's horizontal axis usually is: the "
                "quarters, the service models, the teams."
            ),
        ),
    ),
    "axes": (
        # Named by orientation rather than `x`/`y`: those name coordinates
        # everywhere else in this contract, and coordinates are drawspec's output.
        FieldSpec(
            "horizontal", "object", required=True, ref="axis", description="The axis across."
        ),
        FieldSpec("vertical", "object", required=True, ref="axis", description="The axis up."),
    ),
    "series": (
        FieldSpec(
            "name",
            "string",
            required=True,
            description="What to call this series, in the legend and at its end.",
        ),
        FieldSpec(
            "data",
            "array",
            required=True,
            item_kind="point",
            min_items=1,
            description="The values to plot, as [x, y] pairs. Data, not coordinates.",
        ),
        _role(NODE_ROLES, "step"),
        FieldSpec(
            "mark",
            "string",
            enum=MARKS,
            description="How this series is drawn: a line, bars, or a filled area. Default 'line'.",
        ),
        FieldSpec(
            "stack",
            "string",
            description=(
                "Series sharing a stack name are piled on each other rather than "
                "drawn side by side. Bars and areas only."
            ),
        ),
    ),
}

_VERSION_REQUIRED: Final = (
    "'version' is required. Declare it so a future format change is a loud failure "
    "rather than a misread document."
)


#: Fields every document carries, whatever its kind.
COMMON_FIELDS: Final = (
    FieldSpec(
        "$schema",
        "string",
        description="Optional, and only for editors: the URL of this schema.",
    ),
    FieldSpec("version", "integer", required=True, description=_VERSION_REQUIRED),
    FieldSpec(
        "kind",
        "string",
        required=True,
        enum=KINDS,
        description=(
            "Which of the thirteen diagrams this is. It selects the fields that are "
            "legal below, so it is the first thing to get right."
        ),
    ),
    FieldSpec("title", "string", description="The diagram's accessible name."),
    FieldSpec("description", "string", description="The diagram's accessible description."),
    FieldSpec(
        "caption",
        "string",
        description=(
            "A line of text belonging to the whole diagram rather than to any one "
            "element — an axis's units, a condition that holds throughout, the "
            "sentence the original wrote alongside the figure. Drawn outside the "
            "drawing; the theme's `[canvas] caption` says above or below. Use a "
            "`note` for something attached to one element."
        ),
    ),
    FieldSpec(
        "width",
        "number",
        exclusive_minimum=0,
        description="Overrides the theme's canvas width. Binding.",
    ),
    FieldSpec(
        "height",
        "number",
        exclusive_minimum=0,
        description="Advisory unless height_binding is true.",
    ),
    FieldSpec(
        "height_binding",
        "boolean",
        description="Makes height a constraint rather than a hint.",
    ),
    FieldSpec("theme", "string", description="A bundled theme name or the path of a theme file."),
)

#: The payload fields each kind family adds. The kind selects the family, and
#: the family selects which further fields are legal.
KIND_PAYLOADS: Final[Mapping[tuple[str, ...], tuple[FieldSpec, ...]]] = {
    GRAPH_KINDS: (
        FieldSpec(
            "nodes",
            "array",
            required=True,
            item_ref="node",
            min_items=1,
            description=(
                "The boxes. Order is not a coordinate — the layout decides where a "
                "box goes — but it is the order siblings are drawn in: where nothing "
                "else separates two boxes of the same rank, they read in the order "
                "written here."
            ),
        ),
        FieldSpec(
            "edges",
            "array",
            item_ref="edge",
            description="What connects to what. A `tree` takes one edge per child.",
        ),
        FieldSpec(
            "groups",
            "array",
            item_ref="group",
            description="Boxes drawn around sets of nodes, each with its own caption.",
        ),
        FieldSpec(
            "bands",
            "array",
            item_ref="band",
            description=(
                "Named things that run alongside a set of boxes rather than "
                "containing them — drawn as a labelled bar beside the boxes they "
                "accompany. For the activity that goes on throughout: a source sheet "
                "with one continuous concern above its steps and another below says "
                "the steps are *surrounded* by them, and two such bands are peers. "
                "A `group` cannot say that — a box sits inside one container or none, "
                "so two groups over the same members had to be nested, which draws a "
                "hierarchy that is not there."
            ),
        ),
    ),
    ("stack", "timeline", "columns"): (
        FieldSpec(
            "items",
            "array",
            required=True,
            item_ref="item",
            min_items=1,
            description=(
                "The entries, in the order they are meant to be read: down for "
                "`stack`, along for `timeline` and `columns`."
            ),
        ),
    ),
    ("timeline",): (
        FieldSpec(
            "spans",
            "array",
            item_ref="span",
            description=(
                "Named intervals between two entries, drawn as bars under the axis. "
                "For the quantity that is not a thing on the diagram but the distance "
                "between two things on it: a recovery objective is not an event, it is "
                "how much lies between the last backup and the disaster."
            ),
        ),
    ),
    ("matrix",): (
        FieldSpec(
            "cells",
            "array",
            required=True,
            item_ref="cell",
            min_items=1,
            description=(
                "What is in the grid. A cell states where it starts, not where it is drawn."
            ),
        ),
        FieldSpec(
            "columns",
            "array",
            item_kind="string",
            description="Column headings, left to right. Omit for a matrix with none.",
        ),
        FieldSpec("rows", "array", item_kind="string", description="Row headings, top to bottom."),
        FieldSpec(
            "edges",
            "array",
            item_ref="edge",
            description=(
                "What connects to what, between cells that carry an `id`. The cells of a "
                "grid are not always only cells: one may produce another, or come before "
                "it. The grid places them; the relations are a separate thing, and "
                "without them a reader sees a table where the source drew a process."
            ),
        ),
        FieldSpec(
            "key",
            "array",
            item_ref="key",
            description=(
                "What each group of cells is called, for the key drawn under the grid. "
                "Without one, a group is announced to the reader under the name the "
                "cells use for it — which is fine when that name is a name, and is how "
                "an id-shaped key like `carrega` ends up as visible text."
            ),
        ),
    ),
    ("pyramid",): (
        FieldSpec(
            "levels",
            "array",
            required=True,
            item_ref="level",
            min_items=1,
            description="Apex first. The widest band is the last one written.",
        ),
    ),
    ("rings",): (
        FieldSpec(
            "rings",
            "array",
            required=True,
            item_ref="ring",
            min_items=1,
            description="Innermost first, working outwards.",
        ),
    ),
    ("funnel",): (
        FieldSpec(
            "stages",
            "array",
            required=True,
            item_ref="stage",
            min_items=1,
            description="Widest first: a funnel is a pyramid lying down.",
        ),
    ),
    ("chart",): (
        FieldSpec(
            "axes",
            "object",
            required=True,
            ref="axes",
            description="Both axes. An unlabelled axis cannot be read, so both are required.",
        ),
        FieldSpec(
            "series",
            "array",
            required=True,
            item_ref="series",
            min_items=1,
            description="What is plotted. More than one gets a legend.",
        ),
        FieldSpec(
            "values",
            "boolean",
            description=(
                "Whether to write each point's own number on the drawing. Defaults "
                "to true; set false for a chart whose shape is the message and "
                "whose numbers would be noise."
            ),
        ),
    ),
    ("quadrant",): (
        FieldSpec(
            "axes",
            "object",
            required=True,
            ref="axes",
            description="The two named axes whose crossing makes the four quadrants.",
        ),
        FieldSpec(
            "positions",
            "array",
            required=True,
            item_ref="position",
            min_items=1,
            description=(
                "The items placed in the plane, each by what it scores, not by where it goes."
            ),
        ),
    ),
    ("curve",): (
        FieldSpec(
            "spans",
            "array",
            item_ref="span",
            description=(
                "Named distances between two waypoints, drawn as a capped line with the "
                "name beside it. For the quantity that is the gap itself: a cost variance "
                "is not a point on the drawing, it is how far one curve is from another, "
                "and a caption saying so states it without showing it. Either way round — "
                "two waypoints at one moment measure vertically, two at one value measure "
                "along."
            ),
        ),
        FieldSpec(
            "axes",
            "object",
            required=True,
            ref="axes",
            description="Both axes. A named shape still needs saying what it is a shape of.",
        ),
        FieldSpec(
            "curves",
            "array",
            required=True,
            item_ref="curve",
            min_items=1,
            description="The shapes drawn, each through its own waypoints.",
        ),
    ),
}


def payload_for(kind: str) -> tuple[FieldSpec, ...]:
    """The payload fields legal for `kind`, from every group that names it.

    Accumulated rather than first-match, so a family's shared fields and one
    member's own can be written as two entries: `timeline` takes `items` with
    the rest of the grid kinds and `spans` by itself, and neither entry has to
    know about the other.

    Raises:
        KeyError: no group names this kind.
    """
    found = tuple(
        field for kinds, fields in KIND_PAYLOADS.items() if kind in kinds for field in fields
    )
    if not found:
        raise KeyError(kind)
    return found


def fields_for(kind: str) -> tuple[FieldSpec, ...]:
    """Every field legal for `kind` — common plus payload."""
    return COMMON_FIELDS + payload_for(kind)


# ---------------------------------------------------------------------------
# The model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Node:
    id: str
    text: str
    role: str = "step"
    centre: bool = False
    """Whether the rest of a `flow` is arranged around this one."""

    note: str = ""
    """Accepted for v1 compatibility; only `timeline` items are drawn."""


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    label: str = ""
    role: str = "flow"


@dataclass(frozen=True)
class Group:
    id: str
    members: tuple[str, ...]
    text: str = ""


@dataclass(frozen=True)
class Band:
    """Something that runs alongside a set of boxes rather than containing them.

    A `Group` is a container: a box sits inside one or none, and drawing two over
    the same members means nesting one in the other, which claims a hierarchy the
    author did not. A band claims nothing but company — it accompanies its members
    — so any number of them may cover the same box and they are peers by
    construction. That is what a source sheet means when its own description says
    the steps are *surrounded* by two continuous activities.
    """

    text: str
    members: tuple[str, ...]


@dataclass(frozen=True)
class Item:
    text: str
    id: str = ""
    role: str = "step"
    note: str = ""
    at: float | None = None
    gate: str = ""
    """For a `funnel` stage: what separates it from the next one."""


@dataclass(frozen=True)
class Cell:
    text: str
    column: int
    row: int
    id: str = ""
    across: int = 1
    down: int = 1
    group: str = ""
    role: str = "step"


@dataclass(frozen=True)
class Span:
    """A named interval between two entries of a timeline."""

    text: str
    start: str
    end: str


@dataclass(frozen=True)
class Key:
    """What one group of cells is called, where a reader can see it."""

    group: str
    text: str


@dataclass(frozen=True)
class Waypoint:
    """One point on a curve. Named, or there only to shape it."""

    across: float
    up: float
    text: str = ""
    id: str = ""
    """Optional; only needed when a span measures from this point."""


@dataclass(frozen=True)
class Curve:
    """A shape through its waypoints. Not a series: there is no data here."""

    waypoints: tuple[Waypoint, ...]
    name: str = ""
    role: str = "step"


@dataclass(frozen=True)
class Position:
    """One named point in the plane. `across` and `up` are data, not coordinates."""

    text: str
    across: float
    up: float
    role: str = "step"


@dataclass(frozen=True)
class Axis:
    label: str
    unit: str = ""
    minimum: float | None = None
    maximum: float | None = None
    categories: tuple[str, ...] = ()
    """Names for the positions 1, 2, 3 … Empty for an axis that carries numbers."""


@dataclass(frozen=True)
class Series:
    name: str
    data: tuple[tuple[float, float], ...]
    role: str = "step"
    mark: str = "line"
    stack: str = ""


@dataclass(frozen=True)
class Document:
    """A validated document. Every field the author may write, and none they may not."""

    kind: str
    version: int = DOCUMENT_VERSION
    title: str = ""
    description: str = ""
    caption: str = ""
    """Text belonging to the whole diagram, drawn outside the drawing."""

    width: float | None = None
    height: float | None = None
    height_binding: bool = False
    values: bool = True
    """Whether a `chart` writes each point's own number beside its mark."""

    theme: str = ""
    nodes: tuple[Node, ...] = ()
    edges: tuple[Edge, ...] = ()
    groups: tuple[Group, ...] = ()
    bands: tuple[Band, ...] = ()
    items: tuple[Item, ...] = ()
    levels: tuple[Item, ...] = ()
    rings: tuple[Item, ...] = ()
    stages: tuple[Item, ...] = ()
    cells: tuple[Cell, ...] = ()
    columns: tuple[str, ...] = ()
    rows: tuple[str, ...] = ()
    key: tuple[Key, ...] = ()
    spans: tuple[Span, ...] = ()
    positions: tuple[Position, ...] = ()
    curves: tuple[Curve, ...] = ()
    axes: tuple[Axis, ...] = ()
    """The horizontal axis then the vertical one, for `chart`. Empty otherwise."""

    series: tuple[Series, ...] = ()

    @property
    def family(self) -> str:
        """Which rendering family this document's kind belongs to."""
        for name, kinds in (
            ("graph", GRAPH_KINDS),
            ("grid", GRID_KINDS),
            ("shape", SHAPE_KINDS),
            ("chart", CHART_KINDS),
        ):
            if self.kind in kinds:
                return name
        raise KeyError(self.kind)


# ---------------------------------------------------------------------------
# Violations
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Violation:
    """One validation failure, located by JSON pointer."""

    pointer: str
    message: str

    def __str__(self) -> str:
        return f"{self.pointer or '/'}: {self.message}"


def _escape(part: object) -> str:
    """One JSON pointer token, escaped as RFC 6901 requires."""
    return str(part).replace("~", "~0").replace("/", "~1")


def _pointer(*parts: object) -> str:
    """A JSON pointer, with the escaping RFC 6901 asks for."""
    return "".join("/" + _escape(part) for part in parts if part != "")


def _unknown_field_message(name: str, legal: Sequence[str]) -> str:
    reason = REJECTED_FIELDS.get(name)
    if reason:
        return (
            f"{name!r} is not a field an author may write: {reason}. Every decision "
            f"that requires seeing the output is taken by drawspec."
        )
    return f"{name!r} is not a known field here. Known fields: {', '.join(sorted(legal))}."


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_JSON_TYPES: Final[dict[str, type | tuple[type, ...]]] = {
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _check_type(value: object, spec: FieldSpec, pointer: str, found: list[Violation]) -> bool:
    expected = _JSON_TYPES[spec.kind]
    # `True` is an `int` in Python but not a number in JSON, and a document that
    # says `width = true` should hear about it.
    if isinstance(value, bool) is not (spec.kind == "boolean"):
        found.append(Violation(pointer, f"expected {spec.kind}, got {type(value).__name__}"))
        return False
    if not isinstance(value, expected):
        found.append(Violation(pointer, f"expected {spec.kind}, got {type(value).__name__}"))
        return False
    return True


def _check_field(value: object, spec: FieldSpec, pointer: str, found: list[Violation]) -> None:
    if not _check_type(value, spec, pointer, found):
        return

    if spec.enum and value not in spec.enum:
        found.append(
            Violation(
                pointer,
                f"{value!r} is not one of {', '.join(spec.enum)}. The vocabulary is "
                f"closed, so a role the theme does not declare cannot be named.",
            )
        )
    if spec.exclusive_minimum is not None and float(value) <= spec.exclusive_minimum:  # type: ignore[arg-type]
        found.append(Violation(pointer, f"must be greater than {spec.exclusive_minimum}"))

    if spec.kind == "object" and spec.ref:
        _check_object(value, OBJECTS[spec.ref], pointer, found)  # type: ignore[arg-type]

    if spec.kind == "array":
        elements: list[Any] = value  # type: ignore[assignment]
        if len(elements) < spec.min_items:
            found.append(
                Violation(
                    pointer,
                    f"needs at least {spec.min_items} entr"
                    f"{'y' if spec.min_items == 1 else 'ies'}, got {len(elements)}",
                )
            )
        for index, element in enumerate(elements):
            where = f"{pointer}/{index}"
            if spec.item_ref:
                if not isinstance(element, dict):
                    found.append(Violation(where, f"expected object, got {type(element).__name__}"))
                    continue
                _check_object(element, OBJECTS[spec.item_ref], where, found)
            elif spec.item_kind == "string" and not isinstance(element, str):
                found.append(Violation(where, f"expected string, got {type(element).__name__}"))
            elif spec.item_kind == "point":
                _check_point(element, where, found)


def _check_point(element: object, pointer: str, found: list[Violation]) -> None:
    numbers = (
        isinstance(element, list)
        and len(element) == 2
        and all(isinstance(value, int | float) and not isinstance(value, bool) for value in element)
    )
    if not numbers:
        found.append(Violation(pointer, "expected a pair of numbers, [x, y]"))


def _check_object(
    mapping: Mapping[str, Any],
    specs: Sequence[FieldSpec],
    pointer: str,
    found: list[Violation],
) -> None:
    legal = {spec.name for spec in specs}
    for name in sorted(set(mapping) - legal):
        found.append(
            Violation(f"{pointer}/{_escape(name)}", _unknown_field_message(name, sorted(legal)))
        )
    for spec in specs:
        if spec.name not in mapping:
            if spec.required:
                found.append(
                    Violation(f"{pointer}/{_escape(spec.name)}", f"{spec.name!r} is required")
                )
            continue
        _check_field(mapping[spec.name], spec, f"{pointer}/{_escape(spec.name)}", found)


def validate_document(document: Mapping[str, Any]) -> tuple[Violation, ...]:
    """Every structural and referential violation in `document`, each located.

    Returns all of them rather than stopping at the first, so `drawspec validate`
    can print a document's whole story in one pass.
    """
    found: list[Violation] = []
    kind = document.get("kind")

    if not isinstance(kind, str) or kind not in KINDS:
        # Without a kind there is no way to know which payload fields are legal,
        # so reporting them would be a page of violations about the wrong thing.
        found.append(
            Violation(
                "/kind",
                "'kind' is required"
                if kind is None
                else f"{kind!r} is not one of {', '.join(KINDS)}. The vocabulary is "
                f"closed: a new kind needs evidence, in docs/kinds-wanted.md.",
            )
        )
        if "version" not in document:
            found.append(Violation("/version", _VERSION_REQUIRED))
        return tuple(found)

    _check_object(document, fields_for(kind), "", found)

    version = document.get("version")
    if isinstance(version, int) and not isinstance(version, bool) and version != DOCUMENT_VERSION:
        found.append(
            Violation(
                "/version",
                f"version {version!r} is not supported; this drawspec reads version "
                f"{DOCUMENT_VERSION}. A change of meaning ships as v2, with both "
                f"readable in parallel for at least one release.",
            )
        )

    found.extend(_referential_violations(document, kind))
    return tuple(found)


def _referential_violations(document: Mapping[str, Any], kind: str) -> list[Violation]:
    """The checks JSON Schema cannot express: unique ids, and edges that land."""
    found: list[Violation] = []
    if kind in GRAPH_KINDS:
        middles = [
            index
            for index, node in enumerate(document.get("nodes", ()) or ())
            if isinstance(node, dict) and node.get("centre")
        ]
        for index in middles[1:]:
            found.append(
                Violation(
                    _pointer("nodes", index, "centre"),
                    "a second node says it is the centre. A diagram arranged around a "
                    "subject has one subject.",
                )
            )
        if middles and kind != "flow":
            found.append(
                Violation(
                    _pointer("nodes", middles[0], "centre"),
                    f"a {kind} is ranked from its root, so it has no middle to arrange "
                    f"around. Use a flow.",
                )
            )
    if kind == "curve":
        marked: set[str] = set()
        located: dict[str, tuple[Any, Any]] = {}
        for curve_index, entry in enumerate(document.get("curves", ()) or ()):
            if not isinstance(entry, dict):
                continue
            for point_index, point in enumerate(entry.get("waypoints", ()) or ()):
                if not isinstance(point, dict) or not isinstance(point.get("id"), str):
                    continue
                if not point["id"]:
                    continue
                if point["id"] in marked:
                    found.append(
                        Violation(
                            f"/curves/{curve_index}/waypoints/{point_index}/id",
                            f"duplicate waypoint id {point['id']!r}",
                        )
                    )
                marked.add(point["id"])
                located[point["id"]] = (point.get("across"), point.get("up"))
        for index, span in enumerate(document.get("spans", ()) or ()):
            if not isinstance(span, dict):
                continue
            start, end = span.get("from"), span.get("to")
            for role, value in (("from", start), ("to", end)):
                if isinstance(value, str) and value not in marked:
                    found.append(
                        Violation(
                            f"/spans/{index}/{role}",
                            f"{value!r} is not the id of any waypoint in this document. A "
                            f"span measures between two points, so both need naming — give "
                            f"the waypoints ids.",
                        )
                    )
            if isinstance(start, str) and start == end:
                found.append(
                    Violation(
                        f"/spans/{index}/to",
                        "a span between a point and itself has no distance to name.",
                    )
                )
            elif (
                isinstance(start, str)
                and isinstance(end, str)
                and start in located
                and end in located
                and located[start] == located[end]
            ):
                found.append(
                    Violation(
                        f"/spans/{index}/to",
                        f"{start!r} and {end!r} are two names for the same place, so there "
                        f"is no distance between them to draw. A span makes a gap visible; "
                        f"this one has no gap.",
                    )
                )
        return found
    if kind == "timeline":
        entries = document.get("items")
        spans = document.get("spans")
        if not isinstance(entries, list) or not isinstance(spans, list):
            return found
        order = {
            str(entry["id"]): index
            for index, entry in enumerate(entries)
            if isinstance(entry, dict) and isinstance(entry.get("id"), str) and entry["id"]
        }
        for index, span in enumerate(spans):
            if not isinstance(span, dict):
                continue
            start, end = span.get("from"), span.get("to")
            for role, value in (("from", start), ("to", end)):
                if isinstance(value, str) and value not in order:
                    found.append(
                        Violation(
                            f"/spans/{index}/{role}",
                            f"{value!r} is not the id of any entry on this timeline. A span "
                            f"runs between two of its moments, so both need naming — give "
                            f"the entries ids.",
                        )
                    )
            if (
                isinstance(start, str)
                and isinstance(end, str)
                and start in order
                and end in order
                and order[start] >= order[end]
            ):
                found.append(
                    Violation(
                        f"/spans/{index}/to",
                        f"{end!r} is not after {start!r} on this timeline, so there is no "
                        f"interval between them to name. A span runs forwards.",
                    )
                )
        return found
    if kind == "matrix":
        cells = document.get("cells")
        if not isinstance(cells, list):
            return found
        identified: set[str] = set()
        for index, cell in enumerate(cells):
            if not isinstance(cell, dict) or not isinstance(cell.get("id"), str) or not cell["id"]:
                continue
            if cell["id"] in identified:
                found.append(
                    Violation(_pointer("cells", index, "id"), f"duplicate cell id {cell['id']!r}")
                )
            identified.add(cell["id"])
        for index, edge in enumerate(document.get("edges", ()) or ()):
            if not isinstance(edge, dict):
                continue
            for end in ("from", "to"):
                target = edge.get(end)
                if isinstance(target, str) and target not in identified:
                    found.append(
                        Violation(
                            _pointer("edges", index, end),
                            f"{target!r} is not the id of any cell in this document. An edge "
                            f"on a matrix joins two cells, and a cell needs an `id` before "
                            f"anything can name it.",
                        )
                    )
            if isinstance(edge.get("from"), str) and edge["from"] == edge.get("to"):
                found.append(
                    Violation(
                        _pointer("edges", index, "to"),
                        f"the cell {edge['from']!r} is joined to itself, and a grid has "
                        f"nowhere to draw that: the two ends are the same square.",
                    )
                )
        entries = document.get("key")
        if not isinstance(entries, list):
            return found
        cell_groups = {
            str(cell["group"])
            for cell in cells
            if isinstance(cell, dict) and isinstance(cell.get("group"), str) and cell["group"]
        }
        seen_groups: set[str] = set()
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            group = entry.get("group")
            if not isinstance(group, str):
                continue
            if group not in cell_groups:
                found.append(
                    Violation(
                        f"/key/{index}/group",
                        f"no cell belongs to the group {group!r}, so naming it puts a line "
                        f"in the key for a fill that is not in the drawing. Groups here: "
                        f"{', '.join(sorted(cell_groups)) or 'none'}.",
                    )
                )
            elif group in seen_groups:
                found.append(
                    Violation(
                        f"/key/{index}/group",
                        f"the group {group!r} is named twice. One group, one line in the key.",
                    )
                )
            seen_groups.add(group)
        return found
    if kind == "funnel":
        stages = document.get("stages")
        if isinstance(stages, list) and stages:
            last = stages[-1]
            if isinstance(last, dict) and last.get("gate"):
                found.append(
                    Violation(
                        f"/stages/{len(stages) - 1}/gate",
                        "the last stage has no next stage, so nothing stands between it "
                        "and one. A gate names the threshold *after* a stage; drop it, or "
                        "add the stage it leads to.",
                    )
                )
        return found
    if kind not in GRAPH_KINDS:
        return found

    nodes = document.get("nodes")
    if not isinstance(nodes, list):
        return found

    seen: set[str] = set()
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue
        identifier = node.get("id")
        if not isinstance(identifier, str):
            continue
        if identifier in seen:
            found.append(
                Violation(_pointer("nodes", index, "id"), f"duplicate node id {identifier!r}")
            )
        seen.add(identifier)

    edges = document.get("edges")
    if isinstance(edges, list):
        for index, edge in enumerate(edges):
            if not isinstance(edge, dict):
                continue
            for end in ("from", "to"):
                target = edge.get(end)
                if isinstance(target, str) and target not in seen:
                    found.append(
                        Violation(
                            _pointer("edges", index, end),
                            f"{target!r} is not the id of any node in this document",
                        )
                    )

    groups = document.get("groups")
    if isinstance(groups, list):
        # A member may name a node or another group: a container that contains a
        # container is how the corpus draws three frames deep, and refusing it
        # would make the nesting the renderer supports unsayable.
        containers = {
            group.get("id")
            for group in groups
            if isinstance(group, dict) and isinstance(group.get("id"), str)
        }
        # A group id is a name a member may resolve to, and the renderer keys its
        # containment tree and its captions by it. So a repeated one does not
        # draw twice — the second silently replaces the first, and the drawing
        # stops matching the document with nothing said. An id shared with a node
        # is the same failure by another route: a member naming it could mean
        # either, and which one it gets is an implementation detail.
        named: set[str] = set()
        for index, group in enumerate(groups):
            if not isinstance(group, dict):
                continue
            identifier = group.get("id")
            if isinstance(identifier, str):
                if identifier in seen:
                    found.append(
                        Violation(
                            _pointer("groups", index, "id"),
                            f"{identifier!r} is already the id of a node; a member naming it "
                            f"could mean either",
                        )
                    )
                elif identifier in named:
                    found.append(
                        Violation(
                            _pointer("groups", index, "id"),
                            f"duplicate group id {identifier!r}",
                        )
                    )
                named.add(identifier)

            members = group.get("members")
            if not isinstance(members, list):
                continue
            for position, member in enumerate(members):
                if isinstance(member, str) and member not in seen and member not in containers:
                    found.append(
                        Violation(
                            _pointer("groups", index, "members", position),
                            f"{member!r} is not the id of any node or group in this document",
                        )
                    )

    bands = document.get("bands")
    if isinstance(bands, list):
        # A band's members are nodes and nothing else. It runs *beside* boxes, so
        # naming a group would be asking it to run beside a frame, which is a
        # different drawing and not one this says how to make.
        for index, band in enumerate(bands):
            if not isinstance(band, dict):
                continue
            members = band.get("members")
            if not isinstance(members, list):
                continue
            for position, member in enumerate(members):
                if isinstance(member, str) and member not in seen:
                    found.append(
                        Violation(
                            _pointer("bands", index, "members", position),
                            f"{member!r} is not the id of any node in this document",
                        )
                    )
    return found


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_document(document: Mapping[str, Any]) -> Document:
    """Validate `document` and build the model.

    Raises:
        DocumentError: carrying every violation, each with its JSON pointer.
    """
    if not isinstance(document, Mapping):
        raise DocumentError("a document must be a mapping", ())
    violations = validate_document(document)
    if violations:
        raise DocumentError(_describe(violations), violations)

    kind = str(document["kind"])
    return Document(
        kind=kind,
        version=DOCUMENT_VERSION,
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        values=bool(document.get("values", True)),
        theme=str(document.get("theme", "")),
        nodes=tuple(
            Node(
                id=entry["id"],
                text=entry["text"],
                role=entry.get("role", "step"),
                centre=bool(entry.get("centre", False)),
                note=entry.get("note", ""),
            )
            for entry in document.get("nodes", ())
        ),
        edges=tuple(
            Edge(
                source=entry["from"],
                target=entry["to"],
                label=entry.get("label", ""),
                role=entry.get("role", "flow"),
            )
            for entry in document.get("edges", ())
        ),
        groups=tuple(
            Group(id=entry["id"], members=tuple(entry["members"]), text=entry.get("text", ""))
            for entry in document.get("groups", ())
        ),
        bands=tuple(
            Band(text=entry["text"], members=tuple(entry["members"]))
            for entry in document.get("bands", ())
        ),
        items=_items(document.get("items", ())),
        levels=_items(document.get("levels", ())),
        stages=_items(document.get("stages", ())),
        rings=_items(document.get("rings", ())),
        cells=tuple(
            Cell(
                text=entry["text"],
                id=entry.get("id", ""),
                column=int(entry["column"]),
                row=int(entry["row"]),
                across=int(entry.get("across", 1)),
                down=int(entry.get("down", 1)),
                group=entry.get("group", ""),
                role=entry.get("role", "step"),
            )
            for entry in document.get("cells", ())
        ),
        columns=tuple(document.get("columns", ())),
        rows=tuple(document.get("rows", ())),
        key=tuple(
            Key(group=entry["group"], text=entry["text"]) for entry in document.get("key", ())
        ),
        spans=tuple(
            Span(text=entry["text"], start=entry["from"], end=entry["to"])
            for entry in document.get("spans", ())
        ),
        positions=tuple(
            Position(
                text=entry["text"],
                across=float(entry["across"]),
                up=float(entry["up"]),
                role=entry.get("role", "step"),
            )
            for entry in document.get("positions", ())
        ),
        curves=tuple(
            Curve(
                name=entry.get("name", ""),
                waypoints=tuple(
                    Waypoint(
                        across=float(point["across"]),
                        up=float(point["up"]),
                        text=point.get("text", ""),
                        id=point.get("id", ""),
                    )
                    for point in entry["waypoints"]
                ),
                role=entry.get("role", "step"),
            )
            for entry in document.get("curves", ())
        ),
        axes=_axes(document.get("axes")),
        series=tuple(
            Series(
                name=entry["name"],
                data=tuple((float(x), float(y)) for x, y in entry["data"]),
                role=entry.get("role", "step"),
                mark=entry.get("mark", "line"),
                stack=entry.get("stack", ""),
            )
            for entry in document.get("series", ())
        ),
    )


def _items(entries: Sequence[Mapping[str, Any]]) -> tuple[Item, ...]:
    return tuple(
        Item(
            text=entry["text"],
            id=entry.get("id", ""),
            role=entry.get("role", "step"),
            note=entry.get("note", ""),
            at=None if entry.get("at") is None else float(entry["at"]),
            gate=entry.get("gate", ""),
        )
        for entry in entries
    )


def _axes(entry: Mapping[str, Any] | None) -> tuple[Axis, ...]:
    """The horizontal axis then the vertical one. Ordered, for determinism."""
    if entry is None:
        return ()
    return tuple(_axis(entry[name]) for name in AXIS_ORDER)


def _axis(entry: Mapping[str, Any]) -> Axis:
    return Axis(
        label=entry["label"],
        unit=entry.get("unit", ""),
        minimum=_optional_number(entry.get("min")),
        maximum=_optional_number(entry.get("max")),
        categories=tuple(str(name) for name in entry.get("categories", ())),
    )


def _optional_number(value: object) -> float | None:
    return None if value is None else float(value)  # type: ignore[arg-type]


def _describe(violations: Sequence[Violation]) -> str:
    heading = f"{len(violations)} violation{'s' if len(violations) > 1 else ''} in this document"
    return heading + ":\n" + "\n".join(f"  {violation}" for violation in violations)


def load_document(path: str | Path) -> Document:
    """Read and validate a JSON document from `path`."""
    location = Path(path)
    try:
        text = location.read_text(encoding="utf-8")
    except OSError as error:
        raise DocumentError(f"document could not be read: {location} ({error})", ()) from None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as error:
        raise DocumentError(f"document is not valid JSON: {location} ({error})", ()) from None
    return parse_document(parsed)


# ---------------------------------------------------------------------------
# The published schema
# ---------------------------------------------------------------------------


def _field_schema(spec: FieldSpec) -> dict[str, Any]:
    schema: dict[str, Any] = {}
    if spec.kind == "object" and spec.ref:
        schema["$ref"] = f"#/$defs/{spec.ref}"
        if spec.description:
            schema["description"] = spec.description
        return schema

    schema["type"] = spec.kind
    if spec.description:
        schema["description"] = spec.description
    if spec.enum:
        schema["enum"] = list(spec.enum)
    if spec.exclusive_minimum is not None:
        schema["exclusiveMinimum"] = spec.exclusive_minimum
    if spec.kind == "array":
        if spec.item_ref:
            schema["items"] = {"$ref": f"#/$defs/{spec.item_ref}"}
        elif spec.item_kind == "point":
            schema["items"] = {
                "type": "array",
                "items": {"type": "number"},
                "minItems": 2,
                "maxItems": 2,
            }
        elif spec.item_kind:
            schema["items"] = {"type": spec.item_kind}
        if spec.min_items:
            schema["minItems"] = spec.min_items
    return schema


def _object_schema(specs: Sequence[FieldSpec], *, title: str = "") -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object"}
    if title:
        schema["title"] = title
    schema["properties"] = {spec.name: _field_schema(spec) for spec in specs}
    required = [spec.name for spec in specs if spec.required]
    if required:
        schema["required"] = required
    # The load-bearing line: a forbidden field fails by name rather than being
    # silently absorbed, which is what makes the schema teach.
    schema["additionalProperties"] = False
    return schema


def build_schema() -> dict[str, Any]:
    """Render the field tables above as a JSON Schema document.

    Generated rather than hand-written, so the published artefact and the runtime
    validator cannot disagree. Referential checks (unique ids, edges that land on
    a real node) are outside JSON Schema's reach and are documented as such
    rather than silently missing.
    """
    # One branch per *set of legal fields*, not per entry in the table above: a
    # kind may draw its fields from more than one entry — `timeline` takes
    # `items` with the other grid kinds and `spans` on its own — and a kind
    # appearing in two branches would match both, which `oneOf` reads as invalid.
    grouped: dict[tuple[str, ...], list[str]] = {}
    for kind in KINDS:
        grouped.setdefault(tuple(field.name for field in payload_for(kind)), []).append(kind)

    variants = []
    for names, kinds in grouped.items():
        by_name = {field.name: field for field in payload_for(kinds[0])}
        specs = list(COMMON_FIELDS) + [by_name[name] for name in names]
        variant = _object_schema(specs, title=" / ".join(kinds))
        variant["properties"]["kind"] = {"type": "string", "enum": list(kinds)}
        variant["properties"]["version"] = {"const": DOCUMENT_VERSION}
        variants.append(variant)

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_ID,
        "title": "drawspec document, version 1",
        "description": (
            "A declarative diagram. The author describes what the diagram means; every "
            "decision that requires seeing the output — coordinates, type size, colour, "
            "arrow-head geometry, z-order — is taken by drawspec and has no field here. "
            "Referential rules (node ids are unique; an edge names nodes that exist) are "
            "beyond JSON Schema and are enforced by `drawspec validate`."
        ),
        "oneOf": variants,
        "$defs": {name: _object_schema(specs) for name, specs in sorted(OBJECTS.items())},
    }


def schema_json() -> str:
    """The published schema as the committed file spells it."""
    return json.dumps(build_schema(), indent=2, sort_keys=False, ensure_ascii=False) + "\n"


def published_schema_path() -> Path:
    """The committed schema artefact on disk.

    One file, two places it can be: inside an installed wheel, or at
    `schema/<name>` in a source checkout, which is where it is committed and
    where the wheel copies it from. Never two files, because two files drift.

    Raises:
        FileNotFoundError: neither location has it.
    """
    packaged = Path(__file__).resolve().parent / "schemas" / SCHEMA_FILENAME
    if packaged.is_file():
        return packaged
    checkout = Path(__file__).resolve().parents[2] / "schema" / SCHEMA_FILENAME
    if checkout.is_file():
        return checkout
    raise FileNotFoundError(
        f"{SCHEMA_FILENAME} is neither packaged nor in a source checkout; "
        f"regenerate it with `python -m drawspec.schema`"
    )


def main() -> int:
    """Write the schema to its committed location. Run by `make schema` and CI."""
    destination = Path(__file__).resolve().parents[2] / "schema" / SCHEMA_FILENAME
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(schema_json(), encoding="utf-8")
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "AXIS_ORDER",
    "CHART_KINDS",
    "COMMON_FIELDS",
    "DOCUMENT_VERSION",
    "GRAPH_KINDS",
    "GRID_KINDS",
    "KINDS",
    "OBJECTS",
    "REJECTED_FIELDS",
    "SCHEMA_FILENAME",
    "SCHEMA_ID",
    "SHAPE_KINDS",
    "Axis",
    "Band",
    "Cell",
    "Curve",
    "Document",
    "Edge",
    "FieldSpec",
    "Group",
    "Item",
    "Node",
    "Position",
    "Series",
    "Violation",
    "Waypoint",
    "build_schema",
    "fields_for",
    "load_document",
    "parse_document",
    "payload_for",
    "published_schema_path",
    "schema_json",
    "validate_document",
]

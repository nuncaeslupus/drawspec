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
from collections.abc import Mapping, Sequence, Set
from dataclasses import dataclass
from difflib import get_close_matches
from pathlib import Path
from typing import Any, Final

from drawspec.errors import DocumentError
from drawspec.filetree import ORDERS, STATUSES, Entry, problems
from drawspec.theme import EDGE_ROLES, NODE_ROLES, RAMP_STEPS

#: The document format version this module reads.
DOCUMENT_VERSION: Final = 1

#: The published schema's stable identifier. A document that carries
#: `"$schema": "<this>"` gets completion and inline errors in any editor with
#: JSON Schema support — the author is told `font_size` is not allowed *while
#: typing it*, rather than after a render.
#:
#: **An `$id` has to be a URL that actually serves the document**, and this one
#: did not: it named `drawspec.dev`, which nobody had ever checked and which does
#: not resolve. Every author who copied the recommended `$schema` line got
#: silence instead of completion — the one feature that most makes this format
#: pleasant to write by hand, absent, with nothing to say so.
#:
#: It is now the GitHub Pages URL, which serves `schema/drawspec-v1.schema.json`
#: from the default branch: free, already the project's own domain, and no
#: second copy of the artefact anywhere. Changed *before* the first release
#: rather than after, because an `$id` is an identity — once a version is on
#: PyPI it is in the wild, and moving it stops being a find-and-replace.
SCHEMA_ID: Final = "https://nuncaeslupus.github.io/drawspec/schema/drawspec-v1.schema.json"

#: Where the generated artefact is committed, relative to the repository root.
SCHEMA_FILENAME: Final = "drawspec-v1.schema.json"

GRAPH_KINDS: Final = ("flow", "tree", "cycle")

#: The graph kinds that *draw* their containers, and so may name a group at an
#: edge's end — R5-2. `cycle` is a graph kind to the schema and a parametric
#: template to the renderer (D-1): it places its steps on a ring and draws no
#: frame, so there is no border for an arrow to anchor on and no placement for
#: the id to resolve to. Accepting a group there would hand the renderer an id
#: it cannot place, which is a crash rather than a drawing.
CONTAINER_KINDS: Final = ("flow", "tree")

#: The edge roles a `cycle`'s hub may be joined by. Spokes, not steps: each of
#: these is drawn without a solid head (`weak` is dashed), so none of them reads
#: as one more move round the loop — which a `flow` arrow into the middle would.
HUB_EDGE_ROLES: Final = ("aside", "weak", "link")

#: The fewest steps a ring with a hub may have. Two steps and a middle is three
#: boxes in a row, which is a `flow` and draws as one.
HUB_MINIMUM_NODES: Final = 3

GRID_KINDS: Final = ("stack", "timeline", "columns", "matrix")
SHAPE_KINDS: Final = ("pyramid", "rings", "funnel")
CHART_KINDS: Final = ("chart", "quadrant", "scatter", "curve")

#: A kind of its own: rows of names under a root, drawn like a file browser.
#: Not a `tree` — that one is boxes and arrows for a hierarchy of ideas; this one
#: is a listing, read top to bottom, whose structure is already written in paths.
FILES_KINDS: Final = ("files",)

#: A state machine. Drawn by the graph family's layout, but not a graph kind to
#: the schema: its boxes are conditions something is *in*, not steps, so it has
#: its own payload — `states`, `transitions`, an `initial` and `final` states —
#: and its own refusals, of which reachability is the one only it can make.
STATES_KINDS: Final = ("states",)

#: The roles a state may take. `decision` is refused because a choice in a state
#: machine is a guard on a transition, and a diamond would promise a step; `start`
#: because the initial pseudo-state is a dot, not a box saying "start"; `note`
#: and `group` because neither is a condition the machine can be in.
STATE_ROLES: Final = ("step", "emphasis", "terminal")

#: The roles a transition may take: the default, the happy path drawn heavier,
#: and a rare or error path drawn dashed. `owns`, `link`, `exchange` and `aside`
#: are not transitions — a transition has one direction and goes somewhere.
TRANSITION_ROLES: Final = ("flow", "strong", "weak")

#: Messages between participants, in order. A layout family of its own: the
#: participants are columns in the order written, the messages rows in the order
#: written, and nothing is ranked — the order *is* the diagram.
SEQUENCE_KINDS: Final = ("sequence",)

#: The roles a participant may take: a box, the box the diagram is about, and an
#: outside system drawn as words with no box. `decision`, `start`, `terminal` and
#: `group` promise a shape a lifeline's head does not have.
PARTICIPANT_ROLES: Final = ("step", "emphasis", "note")

#: The roles a message may take: a call (`flow`), a reply (`weak`, dashed with an
#: open head, which is what UML draws for one), and the exchange that matters
#: (`strong`). Every one has a head, because a message has a direction: `aside`,
#: `link`, `exchange` and `owns` are refused. A signal nobody answers is a `flow`
#: with no reply, and is drawn with no activation bar.
MESSAGE_ROLES: Final = ("flow", "weak", "strong")

#: What a fragment's frame says about the messages inside it, written in its tab.
#: `alt` and `par` may be divided by `else`; `loop` and `opt` have one branch.
FRAGMENT_OPERATORS: Final = ("loop", "alt", "opt", "par")

#: The operators whose frame may be divided into branches.
BRANCHING_OPERATORS: Final = ("alt", "par")

#: A `flow` whose actors are drawn as swimlanes. Drawn by the graph family, and
#: not a graph kind to the schema: every node must name its `actor`, which is
#: its lane rather than its box's lead, and a lane is already the container — so
#: `groups`, `bands` and `centre` are refused rather than drawn across the lanes.
LANES_KINDS: Final = ("lanes",)

#: The most lanes one drawing may have, whether listed in `lanes` or read from
#: the actors. Lanes are expensive across the reading direction: past six the
#: strips are too thin to hold a stack, or the drawing too wide to read across.
LANES_MAX: Final = 6

#: The roles a lane's step may take: a flow's, but not `group` — the lane is the
#: container, and a box drawn as a frame inside it would claim to be another.
LANE_NODE_ROLES: Final = tuple(role for role in NODE_ROLES if role != "group")

#: Data models, schemas and class diagrams: named boxes holding lists, and typed
#: relations between them. A layout family of its own — a box's rows are known
#: before it is placed, so a relation can land on one row of it.
ENTITIES_KINDS: Final = ("entities",)

#: The roles an entity may take: the default box, the entity the diagram is
#: about, and an outside or out-of-scope one, drawn lighter.
ENTITY_ROLES: Final = ("step", "emphasis", "note")

#: The edge roles only an `entities` diagram may name: a class diagram's "is a",
#: drawn with a hollow triangle at the general end. Per kind, by the owner's
#: decision — in a `flow` they would mean nothing, so they are refused there.
HIERARCHY_ROLES: Final = ("inherits", "realizes")

#: The roles a relation between entities may take. `link` (the default: an
#: association has no direction), `owns` (composition: this is a part of that),
#: `weak` (a dependency), `strong` (the relation that matters), and the two
#: hierarchy roles. Aggregation is not offered — see `AGGREGATION_REFUSED`.
ENTITY_EDGE_ROLES: Final = ("link", "owns", "weak", "strong", *HIERARCHY_ROLES)

#: The edge roles every other kind with an `edges` array may name.
GRAPH_EDGE_ROLES: Final = tuple(role for role in EDGE_ROLES if role not in HIERARCHY_ROLES)

#: What a relation's end may say about how many: *how many of this end per one of
#: the other*. The author states the cardinality; the theme's `[entities]
#: notation` decides whether it is drawn as crow's feet or as numbers.
CARDINALITIES: Final = ("one", "zero-or-one", "many", "zero-or-many", "one-or-many")

#: What a field's key mark may say, drawn as letters before its name.
FIELD_KEYS: Final = ("primary", "foreign", "unique")

#: The longest stereotype an entity's `tag` may be: a word or two in guillemets.
TAG_MAX: Final = 16

#: The text of a field standing for the ones not shown, as in `files`.
FIELD_PLACEHOLDERS: Final = ("...", "…")

#: The words of the refusal a role that means aggregation gets.
AGGREGATION_REFUSED: Final = (
    "aggregation (the hollow diamond) is not offered: it is the most misread mark in a "
    "class diagram and has no agreed meaning. Say `owns` if the part cannot outlive the "
    "whole, `link` if it can."
)

#: Plans: one row per piece of work, each an interval on a numbered axis. A
#: layout family of its own — rows in the order written, bars placed by value —
#: drawing on the chart's ticks for the axis. No dates: a task starts and ends at
#: numbers in a unit the axis names, which is the owner's decision.
GANTT_KINDS: Final = ("gantt",)

#: The roles a task may take: the default bar, a task on the critical path
#: (`strong`, the same word its dependencies take, drawn heavier), the task the
#: diagram is about (`emphasis`, heavier and differently filled), and an outside
#: task drawn lighter (`note`). `strong` is not counted by the emphasis cap, for
#: the reason the `strong` edge is not: a path is several things by nature.
TASK_ROLES: Final = ("step", "strong", "emphasis", "note")

#: The roles a dependency may take: the default, the critical path drawn heavier,
#: and a soft or assumed dependency drawn dashed. Each has a head, because a
#: finish-to-start dependency has a direction.
DEPENDENCY_ROLES: Final = ("flow", "strong", "weak")

#: The fields of a task that hold a position on the axis.
TASK_VALUES: Final = ("start", "end", "at")

#: Boards: cards sorted into columns, with no connectors — a kanban board, a
#: retrospective, and (with `rows` and a `cut`) a story map. A layout family of
#: its own: a grid of stacks, placed by counting, with nothing to route.
BOARD_KINDS: Final = ("board",)

#: The roles a card may take: the default, the one that matters (blocked, at
#: risk), and a placeholder or summary card drawn lighter and not counted
#: against its column's limit.
CARD_ROLES: Final = ("step", "emphasis", "note")

#: The roles a column's heading may take. A column over its `limit` takes
#: `emphasis` whatever it was given, because drawspec counted and the author
#: did not.
BOARD_COLUMN_ROLES: Final = ("step", "emphasis")

#: The most cards one cell of a board may stack — a column, or a column within
#: one slice. Past it a reader counts instead of reading: write a summary card.
BOARD_CELL_MAX: Final = 8

#: Fishbone (Ishikawa) diagrams: one effect, its causes grouped by category. A
#: fixed two-level structure — effect, categories, causes — drawn as bones
#: slanting into a spine that ends at the effect. A layout family of its own.
FISHBONE_KINDS: Final = ("fishbone",)

#: The roles a cause may take: the default, the confirmed root cause (its bone
#: is drawn heavy all the way to the spine), and one investigated and ruled out.
CAUSE_ROLES: Final = ("step", "emphasis", "note")

#: The most categories one fishbone may have, and causes one category may list.
#: Past six bones the drawing stops being scannable; past five causes a bone is
#: a list.
FISHBONE_CATEGORY_MAX: Final = 6
FISHBONE_CAUSE_MAX: Final = 5

#: How a `files` tree is drawn. `icons` is the file-browser look; `plain` keeps
#: the guides and drops the pictures; `unicode` and `ascii` are the tree as text,
#: set in the monospace face, the way `tree` prints it.
FILES_STYLES: Final = ("icons", "plain", "unicode", "ascii")

#: How a series may be drawn. `line` is the default and was the only one until
#: the corpus asked for the others; `area` is a line whose fill reaches the
#: baseline, and `bar` is a column per point. Closed, like every other
#: vocabulary here.
MARKS: Final = ("line", "bar", "area")

#: The order a chart's axes are held in, so `Document.axes` is not a mapping
#: whose iteration order a reader has to trust.
AXIS_ORDER: Final = ("horizontal", "vertical")

#: The kinds. Closed: a new one needs evidence, not a preference. For most of
#: these the evidence is `docs/kinds-wanted.md`, which sorts the 89 hand-drawn
#: originals by the kind that would have to draw them — the four that opened
#: the vocabulary from nine to thirteen (`matrix`, `funnel`, `quadrant`,
#: `curve`) each cleared originals nothing here could draw. `scatter` is the
#: first exception: no original asked for it, but a consumer project did (a
#: Pareto-frontier view needs two continuous, ticked axes, which `quadrant`
#: deliberately refuses to draw) — evidence external to the corpus, not absent.
#: `files` is the second, on the same footing: a directory listing is the figure
#: every technical document draws by hand, and none of the others can draw it.
#: `states` is the third on that footing: a state machine looked like a `flow`
#: and claimed something else — an initial dot with no words, labelled
#: transitions, self-loops, and a reachability rule a `flow` cannot make.
#: `sequence` is the fourth: who says what to whom, in order — a fixed set of
#: participants exchanging messages down the page, which a `flow` can only draw
#: by duplicating its boxes and losing the order to the ranker. `lanes` is the
#: fifth: not a new picture of a process but a different claim about it — that
#: the hand-offs between parties are the point, which a lead in each box cannot
#: show and a strip per party can. `entities` is the sixth: ER diagrams,
#: database schemas and class diagrams are one shape — a named box with a list in
#: it, and typed relations between boxes that may land on one row — which
#: `tree-compartments` could only imitate with a newline per attribute. `gantt`
#: is the seventh: a plan, one row per task, each an interval — overlap is what
#: the reader looks for, and a `timeline`'s one axis of instants cannot show it.
#: `board` is the eighth: cards sorted into columns with no connectors — a
#: matrix cell is one box, and a board's cell is a list whose count matters.
#: `fishbone` is the ninth: one effect and its causes by category — a two-level
#: `tree` with the effect on top reads as if it owned its causes.
KINDS: Final = (
    GRAPH_KINDS
    + GRID_KINDS
    + SHAPE_KINDS
    + CHART_KINDS
    + FILES_KINDS
    + STATES_KINDS
    + SEQUENCE_KINDS
    + LANES_KINDS
    + ENTITIES_KINDS
    + GANTT_KINDS
    + BOARD_KINDS
    + FISHBONE_KINDS
)

#: The readability budget: per kind, the most entries each counted array may
#: hold before the document is refused as too much for one picture. This is not
#: the fit limit — a `FitError` says the canvas is physically too small, and
#: arrives around twenty boxes — but the earlier point at which a diagram stops
#: being read and starts being searched.
#:
#: Measured, not chosen: every number sits at or above the largest document in
#: `docs/reference/` (in brackets) with headroom, and above the largest drawing
#: of that shape in `corpus/` — whose biggest box-and-arrow original has eleven
#: boxes and ten connectors. `flow` is the tightest fit: `flow-edge-roles` has
#: fourteen nodes (seven independent pairs) and `flow-mesh` twelve edges. A
#: limit that refused a reference document would be a limit set too low, and a
#: test renders every one of them.
#:
#: There is no opt-out. The top-level `width` and `height` are a budget for the
#: canvas, and a wider canvas does not make twenty boxes easier to take in; the
#: remedy is the one the refusal names — an overview plus detail diagrams.
READABILITY_BUDGET: Final[Mapping[str, tuple[tuple[str, int], ...]]] = {
    "flow": (("nodes", 15), ("edges", 16)),  # [14 nodes, 12 edges]
    "tree": (("nodes", 15),),  # [11]
    "cycle": (("nodes", 8),),  # [5]
    "stack": (("items", 8),),  # [3]
    "timeline": (("items", 10),),  # [5]
    "columns": (("items", 6),),  # [5]
    "matrix": (("cells", 25),),  # [16]
    "pyramid": (("levels", 7),),  # [4]
    "rings": (("rings", 6),),  # [3]
    "funnel": (("stages", 7),),  # [4]
    "chart": (("series", 6),),  # [3]
    "quadrant": (("positions", 12),),  # [5]
    "scatter": (("positions", 20),),  # [9]
    "curve": (("curves", 4),),  # [3]
    "files": (("entries", 30),),  # [10]
    # Set by the proposal rather than by the references: past fourteen states the
    # back edges a machine is full of cross in the layered layout.
    "states": (("states", 14), ("transitions", 24)),  # [6 states, 8 transitions]
    # Set by the proposal: past eight lifelines and thirty messages a sequence
    # diagram is a trace, not an explanation — split it into phases.
    "sequence": (("participants", 8), ("messages", 30)),  # [5 participants, 13 messages]
    # A flow's budget, and a cap on the strips: see `LANES_MAX`. When `lanes` is
    # omitted the same cap is applied to the distinct actors, at the node that
    # names the one too many.
    "lanes": (("nodes", 15), ("edges", 16), ("lanes", LANES_MAX)),  # [7 nodes, 7 edges, 4 lanes]
    # Set by the proposal: a schema of thirty tables is a database tool's output.
    # A name with a slash counts inside each entry of the array before it — the
    # rows of one box — and its refusal says to show the ones that matter.
    "entities": (
        ("entities", 8),
        ("edges", 12),
        ("entities/fields", 12),
        ("entities/operations", 8),
    ),  # [5 entities, 5 edges, 6 fields, 3 operations]
    # Set by the proposal: a two-hundred-line plan is a project tool's export.
    "gantt": (("tasks", 16), ("edges", 20), ("marks", 4)),  # [11 tasks, 9 edges, 2 marks]
    # Set by the proposal: past six columns a card's words no longer fit its
    # column. A name with an `@` counts the first array's entries per what the
    # second names — here the cards that share a column and a slice.
    "board": (
        ("columns", 6),
        ("rows", 4),
        ("cards", 32),
        ("cards@cell", BOARD_CELL_MAX),
    ),  # [5 columns, 3 rows, 11 cards, 4 per cell]
    # Set by the proposal: past six bones a fishbone stops being scannable, and
    # past five causes a bone is a list. Both refusals say what to do instead.
    "fishbone": (
        ("categories", FISHBONE_CATEGORY_MAX),
        ("categories/causes", FISHBONE_CAUSE_MAX),
    ),  # [6 categories, 3 causes]
}


#: The role that marks a focal element, and how many a diagram may carry. A
#: reader's eye goes to the heaviest thing first; three heaviest things is no
#: heaviest thing. Two, not one, because the reference documents mark a pair
#: — the two milestones on `flow-critical-path` and `flow-accent`; no other
#: reference or test document needed more, and the one that had three
#: (`scatter-pareto`) emphasised a point another dominated. The `strong`
#: edge role is not counted: it marks a *path*, which is several edges by
#: nature and reads as one line.
EMPHASIS_ROLE: Final = "emphasis"
EMPHASIS_CAP: Final = 2

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
    "value": (
        "a cell is filled by the `scale` step its `group` names, not by a number — "
        "bucket the values and name the buckets; the number can stay in the text"
    ),
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
    missing: str = ""
    """For a required field: what to say when it is absent, if more than that it is."""


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
_ACTOR_DESCRIPTION: Final = (
    "Who performs this step — free text, and orthogonal to `role`. `role` says what kind "
    "of step it is; this says whose it is, and the two are independent: a human step can "
    "be routine and an automated one can be the critical path. Drawn as the box's **lead**, "
    "the name over what belongs to it, so the same words sit in the same place in every box "
    "and a reader can scan a column of them. Free text rather than an enum on purpose: an "
    "actor is told apart by its **name**, which is legible in greyscale and in any medium, "
    "so it costs none of the four non-colour channels the roles are told apart by. "
    "**Only a `flow`, a `tree` or a `cycle` draws one**, and a node that names an actor may "
    "not also write its own lead — the box has one lead and this is it."
)

_NOTE_DESCRIPTION: Final = (
    "A short aside attached to this element. **Only `timeline` draws one** — it goes "
    "under the axis, beside the entry's own mark. Every other kind accepts the field "
    "and has nowhere to put it, so it is not drawn; for text belonging to the whole "
    "diagram, use the top-level `caption` instead."
)


#: What a lane diagram says to a node with no actor: the one thing a swimlane
#: needs that a flow does not, and the way back to the kind that does not need it.
LANES_ACTOR_MISSING: Final = (
    "'actor' is required: every box in a lanes diagram is in a lane, and the actor "
    "names it. If this step belongs to nobody, the diagram is a flow — change the kind, "
    "and any actors become the boxes' leads."
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
        FieldSpec("actor", "string", description=_ACTOR_DESCRIPTION),
        FieldSpec("note", "string", description=_NOTE_DESCRIPTION),
        FieldSpec(
            "status",
            "string",
            enum=STATUSES,
            description=(
                "What a proposed change does to this box, as a diff would say it — for "
                "one drawing of the target state with the change marked on it, instead "
                "of a before and an after to compare by eye. Drawn as the labelled mark "
                "`files` uses (`+ added`, `~ changed`, `- removed`) inside the box, never "
                "as a colour; a removed box is also dashed and its text struck through. "
                "**Only a `flow` or a `tree`**: a loop that changes is a different loop. "
                "An edge touching a removed box must be `removed`, and one touching an "
                "added box must be `added`."
            ),
        ),
    ),
    "edge": (
        FieldSpec(
            "from",
            "string",
            required=True,
            description=(
                "The id of the source node — or, in a `flow` or a `tree`, of a group: "
                "an edge may name a container, for a relation that belongs to the whole "
                "of it rather than to any one box inside. It may not join a container to "
                "something already within it. A `cycle` draws no containers, so an edge "
                "in one names a node — or its `hub`, as a spoke."
            ),
        ),
        FieldSpec(
            "to",
            "string",
            required=True,
            description=(
                "The id of the target node — or, in a `flow` or a `tree`, of a group. "
                "The same id space as `from`. The same id as `from` draws a loop on the "
                "side of that box, across the reading direction, with its label outside "
                "it: two per box at most, and never on a group."
            ),
        ),
        FieldSpec("label", "string", description="A short label placed along the edge."),
        _role(GRAPH_EDGE_ROLES, "flow"),
        FieldSpec(
            "status",
            "string",
            enum=STATUSES,
            description=(
                "What a proposed change does to this connection: the same marks as a "
                "node's, written before the label (`+`, `~`, `-`), with a key of the "
                "marks under the drawing. A removed edge is drawn in the `aside` "
                "treatment — dashed, no head — whatever its role. **Only a `flow`, a "
                "`tree` or `lanes`.**"
            ),
        ),
    ),
    "lane-node": (
        FieldSpec("id", "string", required=True, description="Unique within the document."),
        _text(),
        _role(LANE_NODE_ROLES, "step"),
        FieldSpec(
            "actor",
            "string",
            required=True,
            missing=LANES_ACTOR_MISSING,
            description=(
                "Who performs this step, and so which lane it is drawn in. Required: every "
                "box in a swimlane diagram is in a lane. Drawn once, as the lane's heading, "
                "and not repeated in the box — so `text` may again use a newline for its "
                "own lead and detail. Free text, matched exactly against `lanes` when that "
                "is given."
            ),
        ),
        FieldSpec(
            "status",
            "string",
            enum=STATUSES,
            description=(
                "What a proposed change does to this box, drawn as on a `flow`: the "
                "labelled mark inside the box, never a colour."
            ),
        ),
    ),
    "hub": (
        FieldSpec(
            "id",
            "string",
            required=True,
            description=(
                "Unique within the document, and in the same id space as the nodes, so "
                "an edge may name the hub — as a spoke, never as a step of the loop."
            ),
        ),
        _text(),
        _role(NODE_ROLES, "step"),
    ),
    "state": (
        FieldSpec(
            "id",
            "string",
            required=True,
            description="Unique within the document, among the states and the groups.",
        ),
        _text(),
        _role(STATE_ROLES, "step"),
    ),
    "transition": (
        FieldSpec(
            "from",
            "string",
            required=True,
            description=(
                "The state the machine leaves — or a group, for a transition that "
                "leaves the composite from whichever state inside it is current."
            ),
        ),
        FieldSpec(
            "to",
            "string",
            required=True,
            description=(
                "The state the machine enters — or a group, which is entered at its own "
                "`initial`. The same id as `from` draws a self-loop."
            ),
        ),
        FieldSpec(
            "event",
            "string",
            description=(
                "What happens that moves the machine. Omit for a completion transition, "
                "taken as soon as the state's work is done."
            ),
        ),
        FieldSpec(
            "guard",
            "string",
            description=(
                "The condition that must hold for the event to move the machine. Written "
                "plainly; drawspec adds the brackets."
            ),
        ),
        FieldSpec(
            "action",
            "string",
            description=(
                "What the machine does on the way. Written plainly; drawspec adds the "
                "slash. The label reads `event [guard] / action`, each part optional."
            ),
        ),
        _role(TRANSITION_ROLES, "flow"),
    ),
    "composite": (
        FieldSpec(
            "id",
            "string",
            required=True,
            description="Unique within the document, among the states and the groups.",
        ),
        FieldSpec(
            "text",
            "string",
            required=True,
            description="The composite state's name, drawn at its frame's corner.",
        ),
        FieldSpec(
            "members",
            "array",
            required=True,
            item_kind="string",
            min_items=1,
            description="The states (or groups) inside this composite state.",
        ),
        FieldSpec(
            "initial",
            "string",
            description=(
                "The member this composite is entered at, drawn as a dot inside the "
                "frame. Required when a transition, or the machine's own `initial`, "
                "names the group."
            ),
        ),
    ),
    "participant": (
        FieldSpec(
            "id",
            "string",
            required=True,
            description="Unique within the document, among the participants and the groups.",
        ),
        _text(),
        _role(PARTICIPANT_ROLES, "step"),
    ),
    "message": (
        FieldSpec(
            "id",
            "string",
            description=(
                "Optional, and only needed to name this message from a fragment. Unique "
                "among the messages."
            ),
        ),
        FieldSpec(
            "from",
            "string",
            required=True,
            description="The participant that sends it.",
        ),
        FieldSpec(
            "to",
            "string",
            required=True,
            description=(
                "The participant that receives it. The same id as `from` is a message to "
                "itself, drawn as a hook on the right of its lifeline."
            ),
        ),
        FieldSpec(
            "text",
            "string",
            description=(
                "What is said, written above the arrow. May carry inline spans. Omit for "
                "a bare arrow."
            ),
        ),
        _role(MESSAGE_ROLES, "flow"),
        FieldSpec(
            "note",
            "string",
            description=(
                "A short aside about this message, drawn on its row in one column to the "
                "right of the last lifeline, so the notes read down as one margin."
            ),
        ),
    ),
    "fragment": (
        FieldSpec(
            "operator",
            "string",
            required=True,
            enum=FRAGMENT_OPERATORS,
            description=(
                "What the frame says about the messages inside it, written in its tab: "
                "`loop` repeats them, `opt` may happen, `alt` is one branch of several, "
                "`par` runs its branches at once."
            ),
        ),
        FieldSpec(
            "from",
            "string",
            required=True,
            description="The id of the first message inside the frame.",
        ),
        FieldSpec(
            "to",
            "string",
            required=True,
            description=(
                "The id of the last message inside the frame — the same as `from` for a "
                "frame round one message. Not before `from`."
            ),
        ),
        FieldSpec(
            "text",
            "string",
            description=(
                "The condition, beside the tab: what the loop runs over, when the "
                "option or the first branch happens. Written plainly; drawspec adds the "
                "brackets."
            ),
        ),
        FieldSpec(
            "else",
            "array",
            item_ref="branch",
            description=(
                "For `alt` and `par` only: where the frame is divided, each a dashed line "
                "above a message inside it, with that branch's condition under it."
            ),
        ),
    ),
    "branch": (
        FieldSpec(
            "at",
            "string",
            required=True,
            description=(
                "The id of the first message of this branch. The divider is drawn above "
                "it, so it is after the fragment's first message and no later than its "
                "last."
            ),
        ),
        FieldSpec(
            "text",
            "string",
            description=(
                "This branch's condition. Written plainly; drawspec adds the brackets. "
                "Omit it for a `par` branch, which runs alongside the others and has none."
            ),
        ),
    ),
    "entity": (
        FieldSpec(
            "id",
            "string",
            required=True,
            description="Unique among the entities.",
        ),
        FieldSpec(
            "text",
            "string",
            required=True,
            description=(
                "The entity's name, drawn bold over its fields. One line: may carry "
                "`code` and **bold** spans — a table name is usually `code`."
            ),
        ),
        FieldSpec(
            "tag",
            "string",
            description=(
                f"A short stereotype drawn over the name in guillemets — `interface` is "
                f"drawn «interface». Free text, {TAG_MAX} characters at most."
            ),
        ),
        _role(ENTITY_ROLES, "step"),
        FieldSpec(
            "fields",
            "array",
            item_ref="field",
            description=(
                "What the entity holds, one row each under its name: attributes, columns. "
                "A last field of `...` stands for those not shown."
            ),
        ),
        FieldSpec(
            "operations",
            "array",
            item_kind="string",
            description=(
                "What a class can do — `area() → float` — drawn in a compartment of their "
                "own under the fields. Strings, not objects: an operation is read, never "
                "linked to."
            ),
        ),
    ),
    "field": (
        FieldSpec(
            "id",
            "string",
            description=(
                "Only needed for a relation to land on this row (`from_field`, "
                "`to_field`). Unique among the fields of the document."
            ),
        ),
        FieldSpec(
            "text",
            "string",
            required=True,
            description=(
                "The field's name, one line. `...` as the last field is a row standing "
                "for the fields not shown."
            ),
        ),
        FieldSpec(
            "type",
            "string",
            description="Its type — `uuid`, `float` — drawn right-aligned in the monospace face.",
        ),
        FieldSpec(
            "key",
            "string",
            enum=FIELD_KEYS,
            description=(
                "Whether it is a key, drawn as letters before the name — `PK`, `FK`, "
                "`UQ`: a word, never a colour."
            ),
        ),
    ),
    "relation": (
        FieldSpec(
            "from",
            "string",
            required=True,
            description=(
                "The id of an entity. For `inherits` and `realizes`, the specific one — "
                "the subclass, the implementation."
            ),
        ),
        FieldSpec(
            "to",
            "string",
            required=True,
            description=(
                "The id of another entity — for `inherits` and `realizes` the general one, "
                "which gets the hollow triangle. Not the same as `from`."
            ),
        ),
        FieldSpec(
            "from_field",
            "string",
            description=(
                "The id of one of the `from` entity's fields: the line leaves that row, "
                "at the side facing the other entity, instead of the box. A foreign key "
                "drawn from its column."
            ),
        ),
        FieldSpec(
            "to_field",
            "string",
            description="As `from_field`, a field of the `to` entity: the line arrives at its row.",
        ),
        FieldSpec(
            "from_end",
            "string",
            enum=CARDINALITIES,
            description=(
                "How many of the `from` entity there are per one of the other, drawn at "
                "the `from` end — crow's feet or numbers, as the theme's `[entities] "
                "notation` says. Not on `inherits` or `realizes`."
            ),
        ),
        FieldSpec(
            "to_end",
            "string",
            enum=CARDINALITIES,
            description=(
                "As `from_end`, for the `to` end: how many of it per one of the other. Not on "
                "`owns`, whose `to` end is the whole, drawn as the diamond."
            ),
        ),
        FieldSpec("label", "string", description="A short label placed along the line."),
        FieldSpec(
            "role",
            "string",
            enum=ENTITY_EDGE_ROLES,
            description=(
                "What the relation is. `link` (the default) an association; `owns` "
                "composition — `from` is a part of `to`, diamond at `to`; `weak` a "
                "dependency; `strong` the relation that matters; `inherits` and `realizes` "
                "a subclass and an implementation, hollow triangle at `to`. An end with a "
                "cardinality draws it in place of the role's head."
            ),
        ),
    ),
    "task": (
        FieldSpec("id", "string", required=True, description="Unique within the document."),
        _text(),
        FieldSpec(
            "start",
            "number",
            description=(
                "Where the task starts on the axis, with `end`. A number in the axis's unit "
                "(week 3, day 12, minute 45) — data, not a coordinate. Never a date."
            ),
        ),
        FieldSpec(
            "end",
            "number",
            description=(
                "Where it ends, after `start`. With categories, 4 is where the fourth "
                "period begins."
            ),
        ),
        FieldSpec(
            "at",
            "number",
            description=(
                "Instead of `start` and `end`: makes the task a milestone, drawn as a mark "
                "at this point with no length."
            ),
        ),
        FieldSpec(
            "actor",
            "string",
            description=(
                "Who does it — free text, drawn as the row label's lead, so the names line "
                "up in a column. A task with an actor may not put a newline in `text`."
            ),
        ),
        FieldSpec(
            "role",
            "string",
            enum=TASK_ROLES,
            description=(
                "`step` (the default bar), `strong` (on the critical path: drawn heavier, the "
                "word its dependencies take), `emphasis` (the task the diagram is about) or "
                "`note` (outside the plan, drawn lighter)."
            ),
        ),
    ),
    "dependency": (
        FieldSpec(
            "from",
            "string",
            required=True,
            description="The id of the task that has to finish first.",
        ),
        FieldSpec(
            "to",
            "string",
            required=True,
            description=(
                "The id of the task that waits for it, which may not start before `from` "
                "ends. Drawn from the end of one bar into the start of the other."
            ),
        ),
        FieldSpec(
            "role",
            "string",
            enum=DEPENDENCY_ROLES,
            description=(
                "`flow` (the default), `strong` (the critical path) or `weak` (a soft "
                "dependency, dashed)."
            ),
        ),
    ),
    "mark": (
        _text(),
        FieldSpec(
            "at",
            "number",
            required=True,
            description="Where on the axis: a line is drawn across every row there.",
        ),
    ),
    "axis-gantt": (
        FieldSpec(
            "label",
            "string",
            required=True,
            description="Required, and the unit's name: `Week`, `Day`, `Minutes after 02:00`.",
        ),
        FieldSpec(
            "unit", "string", description="What the numbers are in, written after the label."
        ),
        FieldSpec(
            "min",
            "number",
            description="Where the plan starts. Omit to take it from the tasks.",
        ),
        FieldSpec(
            "max",
            "number",
            description="Where the plan ends. Omit to take it from the tasks.",
        ),
        FieldSpec(
            "categories",
            "array",
            item_kind="string",
            min_items=1,
            description=(
                "Names for the periods, in order, instead of numbers — months, sprints, "
                "quarters. The first period runs from 1 to 2, the second from 2 to 3, so a "
                "task over the first three is `start` 1, `end` 4. Sets the range itself, "
                "so not with `min` or `max`."
            ),
        ),
    ),
    "board-column": (
        FieldSpec(
            "id",
            "string",
            required=True,
            description="Unique among the columns; what a card's `column` names.",
        ),
        _text(),
        FieldSpec(
            "limit",
            "integer",
            exclusive_minimum=0,
            description=(
                "A work-in-progress limit. drawspec counts the column's cards (a `note` card "
                "is not work, so it is not counted) and writes `n / limit` in the heading; "
                "over the limit the heading takes `emphasis`. Never write the count yourself."
            ),
        ),
        FieldSpec(
            "role",
            "string",
            enum=BOARD_COLUMN_ROLES,
            description=(
                "`step` (the default) or `emphasis` (the column the board is about), drawn "
                "as the weight of the rule under the heading."
            ),
        ),
    ),
    "slice": (
        FieldSpec(
            "id",
            "string",
            required=True,
            description="Unique among the rows; what a card's `row` and the board's `cut` name.",
        ),
        _text(),
    ),
    "card": (
        _text(),
        FieldSpec(
            "column",
            "string",
            required=True,
            description="The id of the column it is in. Its kind is its column.",
        ),
        FieldSpec(
            "row",
            "string",
            description=(
                "The id of the row (slice) it is in. Required when the board has `rows`, "
                "refused when it has none."
            ),
        ),
        FieldSpec(
            "role",
            "string",
            enum=CARD_ROLES,
            description=(
                "`step` (the default), `emphasis` (blocked, at risk, the one that matters) "
                "or `note` (a placeholder or a summary such as `+ 6 more`, drawn lighter "
                "and not counted against a limit)."
            ),
        ),
        FieldSpec(
            "actor",
            "string",
            description=(
                "Who holds it — free text, drawn as the card's lead, as in a `flow` box. A "
                "card with an actor may not put a newline in `text`."
            ),
        ),
        FieldSpec(
            "note",
            "string",
            description=("A short aside hung under the card, smaller: `blocked on a decision`."),
        ),
    ),
    "effect": (_text(),),
    "category": (
        _text(),
        FieldSpec(
            "causes",
            "array",
            required=True,
            item_ref="cause",
            min_items=1,
            description=(
                "What was investigated under this category, in reading order from the "
                "category's name inwards to the spine. Leaves: a cause has no causes."
            ),
        ),
    ),
    "cause": (
        _text(),
        FieldSpec(
            "role",
            "string",
            enum=CAUSE_ROLES,
            description=(
                "`step` (the default), `emphasis` (the confirmed root cause: its bone is "
                "drawn heavy up to the spine) or `note` (investigated and ruled out, its "
                "tick drawn light and dashed)."
            ),
        ),
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
    "entry": (
        FieldSpec(
            "path",
            "string",
            required=True,
            description=(
                "Where this sits, from the top of the tree: `src/app/main.py`. The folders "
                "it passes through are drawn without being listed. A trailing `/` makes it "
                "a folder — needed only for one with nothing listed inside. A last segment "
                "of `...` is a row standing for entries not listed."
            ),
        ),
        FieldSpec(
            "note",
            "string",
            description="A short comment drawn after the name, in the smaller label type.",
        ),
        FieldSpec(
            "link",
            "string",
            description=(
                "Makes this entry a symbolic link, drawn with an arrow to this target. "
                "Written, never followed: the target need not be in the tree."
            ),
        ),
        FieldSpec(
            "status",
            "string",
            enum=STATUSES,
            description=(
                "What a change did to this entry, as a diff would say it. Drawn as a "
                "labelled mark after the name — never as a colour alone."
            ),
        ),
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
    # `scatter`'s own axis type, not `axis` above: it has no `categories`, so a
    # document that sets one fails the published schema directly rather than
    # passing it and only failing `drawspec validate` — the same
    # `additionalProperties: false` teaching this contract uses everywhere else,
    # rather than a runtime-only check for something the schema can say itself.
    "axis-continuous": (
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
    ),
    "axes-continuous": (
        FieldSpec(
            "horizontal",
            "object",
            required=True,
            ref="axis-continuous",
            description="The axis across, read as a measurement — unlike `quadrant`'s.",
        ),
        FieldSpec(
            "vertical",
            "object",
            required=True,
            ref="axis-continuous",
            description="The axis up, read as a measurement — unlike `quadrant`'s.",
        ),
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
            "Which of the twenty-two diagrams this is. It selects the fields that are "
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
    ("cycle",): (
        FieldSpec(
            "hub",
            "object",
            ref="hub",
            description=(
                "What the loop turns around: the system a quality cycle improves, the "
                "model a data flywheel retrains. Not a step — it is drawn in the middle "
                "of the ring, outside the check that the ring closes through every "
                "node. An edge may join it to a step only as a spoke, in the roles "
                f"{', '.join(repr(role) for role in HUB_EDGE_ROLES)}: a solid "
                "arrow to the middle would read as one more step. Needs a ring of at "
                f"least {HUB_MINIMUM_NODES} steps."
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
    ("columns", "timeline"): (
        FieldSpec(
            "rise",
            "boolean",
            description=(
                "Whether the series ascends: each entry drawn taller than the one "
                "before it, all sitting on a common baseline — the canvas floor for "
                "`columns`, the axis itself for `timeline`. For a scale where the "
                "order is the content and not merely the reading direction — five "
                "levels of open data, three degrees of a change — and where equal "
                "entries say they are peers, which is the opposite. "
                "The author says the series rises; the theme's `[box] rise` says by "
                "how much, so there is no per-column height to get wrong. Not a "
                "`pyramid`: that draws the last level as the *narrowest*, which is "
                "the right shape for a maturity model and the wrong one for a ladder."
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
            "scale",
            "array",
            item_kind="string",
            min_items=2,
            description=(
                f"Says the groups are **ordered**, and in what order: 2 to {RAMP_STEPS} "
                'group names, **weakest first** — `["rare", "sometimes", "often"]`. '
                "For a heatmap, a risk matrix, a skills matrix: a grid whose cells say "
                "*how much*. The cells are then filled by tone, light to dark, from the "
                "theme's `[mark] ramp` instead of with unrelated patterns, and the key "
                "lists every step in this order (with `key` texts where given). Every "
                "cell `group` must be one of these; a cell with no `group` stays blank, "
                "for *not assessed*. Names, not numbers: the author buckets the values."
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
    FILES_KINDS: (
        FieldSpec(
            "root",
            "string",
            description=(
                "The folder everything is in, drawn as the top row. Omit it for a listing "
                "with several top-level entries and no common parent."
            ),
        ),
        FieldSpec(
            "entries",
            "array",
            required=True,
            item_ref="entry",
            min_items=1,
            description="The paths, one per entry. Siblings keep the order written here.",
        ),
        FieldSpec(
            "sort",
            "string",
            enum=ORDERS,
            description=(
                "How siblings are ordered: `given` (the default) keeps the order written, "
                "`name` sorts naturally (`file2` before `file10`), `folders-first` sorts "
                "by name with folders above files. A `...` row stays last."
            ),
        ),
        FieldSpec(
            "style",
            "string",
            enum=FILES_STYLES,
            description=(
                "`icons` (the default) draws folder and file pictures; `plain` draws the "
                "names and guides only; `unicode` and `ascii` draw the tree as monospace "
                "text, with box-drawing or plain ASCII branches."
            ),
        ),
    ),
    STATES_KINDS: (
        FieldSpec(
            "states",
            "array",
            required=True,
            item_ref="state",
            min_items=1,
            description=(
                "The conditions the machine can be in. A newline in `text` is a lead "
                "and a detail, as everywhere: the state's name over what holds in it. "
                "Every state must be reachable from `initial`."
            ),
        ),
        FieldSpec(
            "initial",
            "string",
            required=True,
            description=(
                "The state the machine starts in, drawn as a filled dot with an arrow to "
                "it. Required: reachability is measured from here. May name a group, "
                "which must then say its own `initial`."
            ),
        ),
        FieldSpec(
            "final",
            "array",
            item_kind="string",
            description=(
                "The states the machine ends in, each drawn with an arrow to a ringed "
                "dot. A final state has no outgoing transition."
            ),
        ),
        FieldSpec(
            "transitions",
            "array",
            item_ref="transition",
            description=(
                "What moves the machine from one state to another, each labelled "
                "`event [guard] / action` from its own fields."
            ),
        ),
        FieldSpec(
            "groups",
            "array",
            item_ref="composite",
            description=(
                "Composite states: a frame around the states inside it, named at its "
                "corner. Groups may nest. A transition from a group leaves it from any "
                "state inside; one to a group enters it at the group's `initial`."
            ),
        ),
    ),
    SEQUENCE_KINDS: (
        FieldSpec(
            "participants",
            "array",
            required=True,
            item_ref="participant",
            min_items=2,
            description=(
                "Who takes part, drawn left to right in the order written, each a head "
                "with a dashed lifeline under it. The order is the reading order, not a "
                "coordinate. Every participant must send or receive a message."
            ),
        ),
        FieldSpec(
            "messages",
            "array",
            required=True,
            item_ref="message",
            min_items=1,
            description=(
                "What is said, drawn top to bottom in the order written: the order is "
                "the diagram. A call (`flow`) answered later by a `weak` reply opens an "
                "activation bar on the receiver from the call's row to the reply's; "
                "nobody writes how tall it is."
            ),
        ),
        FieldSpec(
            "fragments",
            "array",
            item_ref="fragment",
            description=(
                "Frames round a run of messages, `from` to `to`, and every participant "
                "they touch. Fragments nest or are apart; one that starts inside "
                "another and ends outside it is refused."
            ),
        ),
        FieldSpec(
            "groups",
            "array",
            item_ref="group",
            description=(
                "A frame round a run of neighbouring lifelines, named at its top — "
                "*inside our account*. Members must be next to each other in "
                "`participants`, and a participant is in one group or none."
            ),
        ),
    ),
    LANES_KINDS: (
        FieldSpec(
            "nodes",
            "array",
            required=True,
            item_ref="lane-node",
            min_items=1,
            description=(
                "The steps, each in the lane its `actor` names. Ranked along the lanes as "
                "a `flow` is; within one lane, order is the order siblings are drawn in."
            ),
        ),
        FieldSpec(
            "edges",
            "array",
            item_ref="edge",
            description=(
                "What follows what, as on a `flow`. An edge between two lanes crosses "
                "the boundaries between them: that crossing is the hand-off."
            ),
        ),
        FieldSpec(
            "lanes",
            "array",
            item_kind="string",
            min_items=1,
            description=(
                "The lanes in order — top to bottom when they run across the page, left "
                "to right when they run down it; the theme decides which. Each must be "
                "some node's `actor`, spelled exactly, and every actor must be listed. "
                "Omit it and the lanes come in the order their actors first appear in "
                f"`nodes`. At most {LANES_MAX}."
            ),
        ),
    ),
    ENTITIES_KINDS: (
        FieldSpec(
            "entities",
            "array",
            required=True,
            item_ref="entity",
            min_items=1,
            description=(
                "The boxes: each a name (and a stereotype), a rule, its fields, and its "
                "operations under a second rule. Placed by their relations: general above "
                "specific when there is a hierarchy, side by side otherwise."
            ),
        ),
        FieldSpec(
            "edges",
            "array",
            item_ref="relation",
            description=(
                "The relations between entities, each landing on a box — or, with "
                "`from_field` / `to_field`, on one row of it — and carrying a cardinality "
                "at either end. A hierarchy may not loop."
            ),
        ),
    ),
    GANTT_KINDS: (
        FieldSpec(
            "axis",
            "object",
            required=True,
            ref="axis-gantt",
            description=(
                "The one axis the plan runs along: what its numbers count, in a unit you "
                "name. There are no dates."
            ),
        ),
        FieldSpec(
            "tasks",
            "array",
            required=True,
            item_ref="task",
            min_items=1,
            description=(
                "One row each, in the order written — that order is the reading order. "
                "`start` and `end` make a bar; `at` makes a milestone."
            ),
        ),
        FieldSpec(
            "groups",
            "array",
            item_ref="group",
            description=(
                "Phases, each a run of consecutive tasks, drawn as a heading row with a "
                "bracket over the phase's span. With groups, every task is in one."
            ),
        ),
        FieldSpec(
            "edges",
            "array",
            item_ref="dependency",
            description=(
                "Finish-to-start dependencies between tasks: drawn from the end of `from` "
                "into the start of `to`."
            ),
        ),
        FieldSpec(
            "marks",
            "array",
            item_ref="mark",
            description=(
                "Named points in time — today, a deadline, a freeze — each a line across "
                "every row with its name above."
            ),
        ),
    ),
    BOARD_KINDS: (
        FieldSpec(
            "columns",
            "array",
            required=True,
            item_ref="board-column",
            min_items=1,
            description=(
                "Left to right as written: states on a kanban board, prompts on a "
                "retrospective, the steps of a story on a story map. All one width."
            ),
        ),
        FieldSpec(
            "rows",
            "array",
            item_ref="slice",
            min_items=1,
            description=(
                "Slices across every column, top to bottom — the releases of a story map. "
                "With rows, every card names one."
            ),
        ),
        FieldSpec(
            "cut",
            "string",
            description=(
                "The id of a row: a heavy rule is drawn under it — everything above ships "
                "first. Not the last row, which has nothing below it to cut from."
            ),
        ),
        FieldSpec(
            "cards",
            "array",
            required=True,
            item_ref="card",
            min_items=1,
            description=(
                "Each in a column (and a row, with rows). Within a cell they stack in the "
                "order written, top-aligned, so a short column looks short."
            ),
        ),
    ),
    FISHBONE_KINDS: (
        FieldSpec(
            "effect",
            "object",
            required=True,
            ref="effect",
            description=(
                "The observed problem, stated as a fact: drawn in the head box at the end of "
                "the spine, always as the diagram's emphasis."
            ),
        ),
        FieldSpec(
            "categories",
            "array",
            required=True,
            item_ref="category",
            min_items=2,
            description=(
                "The bones, drawn alternately above and below the spine, nearest the head "
                "first: the written order is the reading order from the head outwards."
            ),
        ),
    ),
    ("scatter",): (
        FieldSpec(
            "axes",
            "object",
            required=True,
            ref="axes-continuous",
            description="Both axes, each read as a measurement — unlike `quadrant`'s.",
        ),
        FieldSpec(
            "positions",
            "array",
            required=True,
            item_ref="position",
            min_items=1,
            description="The points, each placed by its two measured values.",
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

    actor: str = ""
    """Who performs this step. Free text, and empty when nobody was named."""

    status: str = ""
    """What a proposed change does to this box: `added`, `changed`, `removed`, or empty."""

    lane: str = ""
    """The lane a `lanes` node is drawn in — its author's `actor`, which there is
    a strip of the drawing rather than the box's lead, so `actor` stays empty."""

    @property
    def label(self) -> str:
        """The words this node's box is sized and drawn from.

        An actor is the box's **lead**: the name over what belongs to it, which is
        the compartment a hand-drawn class box, record or component already uses.
        Written here rather than by each family, so `flow`, `tree` and `cycle`
        cannot disagree about where the actor sits.
        """
        return f"{self.actor}\n{self.text}" if self.actor else self.text

    @property
    def lead(self) -> bool | None:
        """Whether this node's first paragraph is a lead.

        `True` when an actor supplied one, and `None` — meaning *ask the text* —
        otherwise. Never `False`: a node without an actor may still have written
        its own lead, and answering for it would take that away.
        """
        return True if self.actor else None


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    label: str = ""
    role: str = "flow"
    status: str = ""
    """What a proposed change does to this connection, or empty."""


@dataclass(frozen=True)
class Group:
    id: str
    members: tuple[str, ...]
    text: str = ""
    initial: str = ""
    """For a composite state: the member it is entered at, or empty."""


@dataclass(frozen=True)
class Message:
    """One message of a `sequence`: who says it, to whom, and in what role."""

    source: str
    target: str
    text: str = ""
    role: str = "flow"
    id: str = ""
    note: str = ""


@dataclass(frozen=True)
class Branch:
    """Where an `alt` or `par` frame is divided: above message `at`."""

    at: str
    text: str = ""


@dataclass(frozen=True)
class Fragment:
    """A frame round the messages `start` to `end`, inclusive, by message id."""

    operator: str
    start: str
    end: str
    text: str = ""
    branches: tuple[Branch, ...] = ()


@dataclass(frozen=True)
class EntityField:
    """One row of an entity: a name, and optionally a type, a key mark and an id."""

    text: str
    type: str = ""
    key: str = ""
    id: str = ""

    @property
    def placeholder(self) -> bool:
        """Whether this row stands for the fields not shown."""
        return self.text.strip() in FIELD_PLACEHOLDERS


@dataclass(frozen=True)
class Entity:
    """One box of an `entities` diagram: its name over its fields and operations."""

    id: str
    text: str
    role: str = "step"
    tag: str = ""
    fields: tuple[EntityField, ...] = ()
    operations: tuple[str, ...] = ()


@dataclass(frozen=True)
class Relation:
    """One relation between two entities, with what is drawn at each end."""

    source: str
    target: str
    label: str = ""
    role: str = "link"
    source_field: str = ""
    target_field: str = ""
    source_end: str = ""
    target_end: str = ""


@dataclass(frozen=True)
class Task:
    """One row of a `gantt`: an interval from `start` to `end`, or a milestone `at`."""

    id: str
    text: str
    start: float = 0.0
    end: float = 0.0
    at: float | None = None
    role: str = "step"
    actor: str = ""

    @property
    def milestone(self) -> bool:
        """Whether this task is a point rather than an interval."""
        return self.at is not None

    @property
    def begins(self) -> float:
        """Where it starts on the axis: `start`, or `at` for a milestone."""
        return self.at if self.at is not None else self.start

    @property
    def finishes(self) -> float:
        """Where it ends on the axis: `end`, or `at` for a milestone."""
        return self.at if self.at is not None else self.end

    @property
    def label(self) -> str:
        """The words of its row label: the actor as the lead, as in a `flow` box."""
        return f"{self.actor}\n{self.text}" if self.actor else self.text


@dataclass(frozen=True)
class Mark:
    """A named point on a `gantt`'s axis, drawn as a line across every row."""

    text: str
    at: float


@dataclass(frozen=True)
class BoardColumn:
    """One column of a `board`, left to right, with an optional work-in-progress limit."""

    id: str
    text: str
    limit: int | None = None
    role: str = "step"


@dataclass(frozen=True)
class Slice:
    """One row of a `board` — a release of a story map — across every column."""

    id: str
    text: str


@dataclass(frozen=True)
class Card:
    """One card of a `board`: in a column, and in a row when the board has rows."""

    text: str
    column: str
    row: str = ""
    role: str = "step"
    actor: str = ""
    note: str = ""

    @property
    def label(self) -> str:
        """The words of the card: the actor as the lead, as in a `flow` box."""
        return f"{self.actor}\n{self.text}" if self.actor else self.text


@dataclass(frozen=True)
class Cause:
    """One cause on a `fishbone` bone: a leaf, with a role."""

    text: str
    role: str = "step"


@dataclass(frozen=True)
class Category:
    """One bone of a `fishbone`: a category's name and the causes under it."""

    text: str
    causes: tuple[Cause, ...] = ()


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

    rise: bool = False
    """Whether the series ascends, each entry taller than the last."""

    theme: str = ""
    nodes: tuple[Node, ...] = ()
    """The boxes — a `states` document's states are parsed into these too."""

    initial: str = ""
    """The state or group a `states` machine starts in."""

    final: tuple[str, ...] = ()
    """The states a `states` machine ends in."""

    hub: Node | None = None
    """What a `cycle` turns around, drawn inside its ring. Not one of `nodes`."""

    edges: tuple[Edge, ...] = ()
    """The connectors — a `states` document's transitions, labelled, are parsed into these."""

    groups: tuple[Group, ...] = ()
    bands: tuple[Band, ...] = ()
    items: tuple[Item, ...] = ()
    levels: tuple[Item, ...] = ()
    rings: tuple[Item, ...] = ()
    stages: tuple[Item, ...] = ()
    cells: tuple[Cell, ...] = ()
    columns: tuple[str, ...] = ()
    rows: tuple[str, ...] = ()
    scale: tuple[str, ...] = ()
    """A `matrix`'s ordered groups, weakest first. Empty when the groups are a set."""

    key: tuple[Key, ...] = ()
    spans: tuple[Span, ...] = ()
    positions: tuple[Position, ...] = ()
    curves: tuple[Curve, ...] = ()
    axes: tuple[Axis, ...] = ()
    """The horizontal axis then the vertical one, for `chart`. Empty otherwise."""

    series: tuple[Series, ...] = ()
    root: str = ""
    """The top folder of a `files` tree, or empty for several top-level entries."""

    entries: tuple[Entry, ...] = ()
    order: str = "given"
    """How a `files` tree orders siblings — the document's `sort`."""

    style: str = "icons"
    participants: tuple[Node, ...] = ()
    """A `sequence`'s participants, left to right."""

    messages: tuple[Message, ...] = ()
    """A `sequence`'s messages, top to bottom."""

    fragments: tuple[Fragment, ...] = ()
    lanes: tuple[str, ...] = ()
    """A `lanes` diagram's lanes in order: as listed, or as the actors first appear."""

    entities: tuple[Entity, ...] = ()
    relations: tuple[Relation, ...] = ()
    """An `entities` diagram's edges, which carry fields and ends a graph edge has not."""

    tasks: tuple[Task, ...] = ()
    """A `gantt`'s rows, top to bottom. Its axis is the one entry of `axes`."""

    marks: tuple[Mark, ...] = ()

    board_columns: tuple[BoardColumn, ...] = ()
    """A `board`'s columns, left to right. Not `columns`, which is a matrix's headings."""

    slices: tuple[Slice, ...] = ()
    """A `board`'s rows, top to bottom."""

    cards: tuple[Card, ...] = ()
    cut: str = ""
    """The id of the slice a `board` draws its heavy rule under."""

    effect: str = ""
    """A `fishbone`'s effect: the words in the head box."""

    categories: tuple[Category, ...] = ()
    """A `fishbone`'s bones, nearest the head first."""

    @property
    def family(self) -> str:
        """Which rendering family this document's kind belongs to."""
        for name, kinds in (
            ("graph", GRAPH_KINDS),
            ("grid", GRID_KINDS),
            ("shape", SHAPE_KINDS),
            ("chart", CHART_KINDS),
            ("files", FILES_KINDS),
            ("states", STATES_KINDS),
            ("sequence", SEQUENCE_KINDS),
            ("lanes", LANES_KINDS),
            ("entities", ENTITIES_KINDS),
            ("gantt", GANTT_KINDS),
            ("board", BOARD_KINDS),
            ("fishbone", FISHBONE_KINDS),
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
                    Violation(
                        f"{pointer}/{_escape(spec.name)}",
                        spec.missing or f"{spec.name!r} is required",
                    )
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

    if kind in LANES_KINDS:
        found = [_lanes_refusal(violation) for violation in found]
    if kind in GANTT_KINDS:
        found = [_gantt_refusal(violation, document) for violation in found]
    if kind in BOARD_KINDS:
        found = [_board_refusal(violation) for violation in found]
    if kind in FISHBONE_KINDS:
        found = [_fishbone_refusal(violation) for violation in found]
    found = [_edge_role_refusal(violation, document, kind) for violation in found]
    found.extend(_referential_violations(document, kind))
    found.extend(_readability_violations(document, kind))
    found.extend(_emphasis_violations(document))
    return tuple(found)


def _edge_role_refusal(violation: Violation, document: Mapping[str, Any], kind: str) -> Violation:
    """An edge role outside the kind's vocabulary, told which kind it belongs to.

    The generic refusal lists the legal roles, which says nothing to an author who
    wrote `inherits` in a `flow`, or `aggregates` in an entity diagram, on purpose.
    """
    parts = violation.pointer.split("/")
    if len(parts) != 4 or parts[1] != "edges" or parts[3] != "role":
        return violation
    edges = document.get("edges")
    try:
        role = edges[int(parts[2])]["role"]  # type: ignore[index]
    except (TypeError, ValueError, IndexError, KeyError):
        return violation
    if not isinstance(role, str):
        return violation
    if role in HIERARCHY_ROLES and kind not in ENTITIES_KINDS:
        legal = DEPENDENCY_ROLES if kind in GANTT_KINDS else GRAPH_EDGE_ROLES
        return Violation(
            violation.pointer,
            f"{role!r} is an edge role of the `entities` kind only: it says one class is a "
            f"kind of another, which a {kind} has no classes to mean. Here, one of "
            f"{', '.join(legal)}.",
        )
    if kind in ENTITIES_KINDS and role.startswith("aggregat"):
        return Violation(violation.pointer, f"{role!r}: {AGGREGATION_REFUSED}")
    return violation


#: What to do instead, for a budget whose generic advice ("split it into an
#: overview and details") is not the remedy. Keyed by (kind, array) for a
#: top-level budget and by (outer, inner) for a nested one.
BUDGET_ADVICE: Final[Mapping[tuple[str, str], str]] = {
    ("fishbone", "categories"): (
        "Past six bones a fishbone stops being scannable: merge the categories that overlap, "
        "or draw the biggest category as a fishbone of its own."
    ),
    ("categories", "causes"): (
        "Past five causes a bone is a list: keep the ones the investigation turned on, or "
        "make this category its own fishbone with these causes as its categories."
    ),
}


def _readability_violations(document: Mapping[str, Any], kind: str) -> list[Violation]:
    """Every counted array that holds more than its kind's readability budget.

    A refusal of a document that would draw: it says the picture would not be
    read, which is a different claim from `FitError`'s and comes before it.
    """
    found: list[Violation] = []
    for name, limit in READABILITY_BUDGET.get(kind, ()):
        if "/" in name:
            found.extend(_nested_budget(document, name, limit))
            continue
        if "@" in name:
            found.extend(_cell_budget(document, name, limit))
            continue
        entries = document.get(name)
        if not isinstance(entries, list) or len(entries) <= limit:
            continue
        found.append(
            Violation(
                _pointer(name, limit),
                f"{len(entries)} {name} is past what one {kind} can be read at — "
                f"{limit} at most. "
                + BUDGET_ADVICE.get(
                    (kind, name),
                    "Past that a reader searches the diagram instead of "
                    "taking it in. Split it: an overview that names each part once, plus a "
                    "detail diagram per part, each within the budget.",
                )
                + " The budget is not a canvas size, so a larger top-level 'width' does not "
                "lift it.",
            )
        )
    return found


def _nested_budget(document: Mapping[str, Any], name: str, limit: int) -> list[Violation]:
    """The budget of an array inside each entry of another — the rows of one box."""
    outer, inner = name.split("/")
    found: list[Violation] = []
    for index, entry in enumerate(_listed(document, outer)):
        rows = entry.get(inner) if isinstance(entry, dict) else None
        if not isinstance(rows, list) or len(rows) <= limit:
            continue
        advice = BUDGET_ADVICE.get((outer, inner))
        found.append(
            Violation(
                _pointer(outer, index, inner, limit),
                f"{len(rows)} {inner} is past what one box can be read at — {limit} at "
                f"most. Show the ones this diagram is about and end the list with a "
                f"`...` field, which says there are more."
                if advice is None
                else f"{len(rows)} {inner} is past what one {outer[:-3]}y can be read at — "
                f"{limit} at most. {advice}",
            )
        )
    return found


def _cell_budget(document: Mapping[str, Any], name: str, limit: int) -> list[Violation]:
    """The budget of a board's cell: how many cards share one column and one row."""
    outer, _ = name.split("@")
    found: list[Violation] = []
    counts: dict[tuple[object, object], int] = {}
    for index, card in enumerate(_listed(document, outer)):
        if not isinstance(card, dict):
            continue
        cell = (card.get("column"), card.get("row"))
        if not all(isinstance(part, str | None) for part in cell):
            continue
        counts[cell] = counts.get(cell, 0) + 1
        if counts[cell] == limit + 1:
            found.append(
                Violation(
                    _pointer(outer, index),
                    f"this is card {limit + 1} in one cell, and a board's cell can be read at "
                    f"{limit} at most — past that a reader counts instead of reading. Keep the "
                    f'ones that matter and end with a summary card, `{{"text": "+ 6 more", '
                    f'"role": "note"}}`, which says there are more.',
                )
            )
    return found


def _emphasis_violations(document: Mapping[str, Any]) -> list[Violation]:
    """Every focal element past the cap, wherever in the document it was written.

    Counted across the whole document — nodes, items, positions, series, curves
    — because the reader's eye does not care which array a heavy mark came from.
    """
    found: list[Violation] = []
    focal: list[str] = []

    def collect(value: object, pointer: str) -> None:
        if isinstance(value, dict):
            if value.get("role") == EMPHASIS_ROLE:
                focal.append(pointer)
            for key, child in value.items():
                collect(child, f"{pointer}/{_escape(key)}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                collect(child, f"{pointer}/{index}")

    collect(document, "")
    for pointer in focal[EMPHASIS_CAP:]:
        found.append(
            Violation(
                f"{pointer}/role",
                f"{len(focal)} elements say {EMPHASIS_ROLE!r}, and a diagram may have "
                f"{EMPHASIS_CAP}. Emphasis means *look here first*; when three things "
                f"say it, none of them is first. Keep the one or two the diagram is "
                f"about and give the rest their ordinary role — or, if they really are "
                f"equal, emphasise none.",
            )
        )
    return found


def _referential_violations(document: Mapping[str, Any], kind: str) -> list[Violation]:
    """The checks JSON Schema cannot express: unique ids, and edges that land."""
    found: list[Violation] = []
    if kind in STATES_KINDS:
        return _states_violations(document)
    if kind in SEQUENCE_KINDS:
        return _sequence_violations(document)
    if kind in ENTITIES_KINDS:
        return _entities_violations(document)
    if kind in GANTT_KINDS:
        return _gantt_violations(document)
    if kind in BOARD_KINDS:
        return _board_violations(document)
    if kind in FISHBONE_KINDS:
        return []
    if kind in LANES_KINDS:
        found.extend(_lanes_violations(document))
    if kind in FILES_KINDS:
        entries = document.get("entries", ())
        # Only a well-formed list is worth reading for paths: the structural pass
        # has already reported anything else, and would be reported twice here.
        well_formed = isinstance(entries, list) and all(
            isinstance(entry, dict)
            and isinstance(entry.get("path"), str)
            and all(isinstance(entry.get(name, ""), str) for name in ("note", "link", "status"))
            for entry in entries
        )
        found.extend(
            Violation(_pointer("entries", index, name), message)
            for index, name, message in (problems(_entries(entries)) if well_formed else [])
        )
        root = document.get("root", "")
        if isinstance(root, str) and ("/" in root.strip("/") or root.strip() != root):
            found.append(
                Violation(
                    "/root",
                    f"{root!r} is one folder's name, drawn as the top row — not a path. "
                    "Put the folders below it in the entries' paths.",
                )
            )
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
        # An actor is drawn as the box's lead, and a box has one lead. A node
        # that wrote its own is not refused a *field* — it is told that the two
        # are the same slot, which is a different mistake and a different fix.
        for index, node in enumerate(document.get("nodes", ()) or ()):
            if not isinstance(node, dict) or not node.get("actor"):
                continue
            text = node.get("text")
            if isinstance(text, str) and "\n" in text.strip():
                found.append(
                    Violation(
                        _pointer("nodes", index, "actor"),
                        "this node names an actor and also writes its own lead — the "
                        "newline in its 'text' says the first paragraph is one. A box "
                        "has a single lead and the actor is it: either drop the actor, "
                        "or join the text into one paragraph.",
                    )
                )
        if middles and kind != "flow":
            found.append(
                Violation(
                    _pointer("nodes", middles[0], "centre"),
                    f"a {kind} is ranked from its root, so it has no middle to arrange "
                    f"around. Use a flow"
                    + (
                        " — or, for something the loop turns around rather than a step "
                        "on it, the cycle's own 'hub'."
                        if kind == "cycle"
                        else "."
                    ),
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
            if "status" in edge:
                found.append(
                    Violation(
                        _pointer("edges", index, "status"),
                        "a matrix is not a drawing of a change; 'status' marks one on a "
                        "flow or a tree.",
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
        scale = document.get("scale")
        steps: set[str] | None = None
        if isinstance(scale, list) and all(isinstance(step, str) for step in scale):
            steps = set(scale)
            found.extend(_scale_violations(scale, cells))
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
            if steps is not None and group not in steps:
                found.append(
                    Violation(
                        f"/key/{index}/group",
                        f"{group!r} is not a step of this matrix's scale, so a key line for "
                        f"it would describe nothing in the drawing. Steps: "
                        f"{', '.join(str(step) for step in scale or ())}.",
                    )
                )
            elif steps is None and group not in cell_groups:
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
    if kind not in GRAPH_KINDS + LANES_KINDS:
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

    found.extend(_status_violations(document, kind))

    if kind == "cycle":
        found.extend(_hub_violations(document, seen))
        hub = document.get("hub")
        if isinstance(hub, dict) and isinstance(hub.get("id"), str):
            seen.add(hub["id"])

    groups = document.get("groups")
    # A member may name a node or another group: a container that contains a
    # container is how the corpus draws three frames deep, and refusing it
    # would make the nesting the renderer supports unsayable.
    containers = {
        group["id"]
        for group in (groups if isinstance(groups, list) else ())
        if isinstance(group, dict) and isinstance(group.get("id"), str)
    }

    # A group is a name an edge may resolve to, because a relation can belong to
    # the whole container rather than to any one box in it — R5-2. The frame is
    # already a box with an extent and a border, so the only thing that was
    # missing was saying so. Only where the frame is *drawn*, though: see
    # `CONTAINER_KINDS`. A `cycle` accepts `groups` in its payload and draws
    # none, so a group id at an edge's end is an id its renderer cannot place.
    endpoints = containers if kind in CONTAINER_KINDS else frozenset()

    edges = document.get("edges")
    if isinstance(edges, list):
        for index, edge in enumerate(edges):
            if not isinstance(edge, dict):
                continue
            for end in ("from", "to"):
                target = edge.get(end)
                if not isinstance(target, str) or target in seen or target in endpoints:
                    continue
                found.append(
                    Violation(
                        _pointer("edges", index, end),
                        f"{target!r} is a group, and a {kind} is drawn as a ring of steps "
                        f"with no containers in it, so an edge here may only name a node"
                        if target in containers
                        else f"{target!r} is not the id of any node"
                        + (" or group" if kind in CONTAINER_KINDS else "")
                        + " in this document",
                    )
                )
        found.extend(_self_containment(edges, groups, endpoints))
        if kind in CONTAINER_KINDS + LANES_KINDS:
            found.extend(_loop_violations(edges, frozenset(containers), "edges"))

    if isinstance(groups, list):
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


#: Why a `lanes` document may not write what a `flow` may, by the field's name.
LANES_REFUSED: Final[Mapping[str, str]] = {
    "groups": (
        "a lanes diagram has no 'groups': a lane is already the container, and a frame "
        "drawn across lanes would put a box in two containers at once. Use a flow for "
        "frames, or name the containing party as the nodes' actor."
    ),
    "bands": (
        "a lanes diagram has no 'bands': a band runs alongside its boxes, and here that "
        "would run across the lanes. Use a flow with bands, or make the activity a lane."
    ),
    "centre": (
        "a lanes diagram is ranked along its lanes, so it has no middle to arrange "
        "around. Use a flow."
    ),
}


def _lanes_refusal(violation: Violation) -> Violation:
    """An unknown field on a `lanes` document, with why a flow's field is not here."""
    name = violation.pointer.rsplit("/", 1)[-1]
    if name in LANES_REFUSED and "is not a known field" in violation.message:
        return Violation(violation.pointer, LANES_REFUSED[name])
    return violation


def _lanes_violations(document: Mapping[str, Any]) -> list[Violation]:
    """What a swimlane diagram may not be: a box in no lane, or a lane with no box.

    Ids and edges are the graph checks, shared with `flow`; these are the lane's
    own. A listed lane must hold some node and every actor must be listed, since
    either mismatch is nearly always a spelling difference — so the closest lane
    is named. With no list, the distinct actors are capped as the list would be.
    """
    found: list[Violation] = []
    actors: list[tuple[int, str]] = []
    for index, node in enumerate(_listed(document, "nodes")):
        if not isinstance(node, dict) or not isinstance(node.get("actor"), str):
            continue
        if not node["actor"].strip():
            found.append(Violation(_pointer("nodes", index, "actor"), LANES_ACTOR_MISSING))
            continue
        actors.append((index, node["actor"]))

    listed = document.get("lanes")
    if isinstance(listed, list) and all(isinstance(lane, str) for lane in listed):
        seen: set[str] = set()
        for index, lane in enumerate(listed):
            if lane in seen:
                found.append(
                    Violation(_pointer("lanes", index), f"the lane {lane!r} is listed twice.")
                )
            seen.add(lane)
        named = {actor for _, actor in actors}
        for index, actor in actors:
            if actor in seen:
                continue
            close = get_close_matches(actor, listed, n=1, cutoff=0.0)
            found.append(
                Violation(
                    _pointer("nodes", index, "actor"),
                    f"{actor!r} is not one of the lanes"
                    + (f" — did you mean {close[0]!r}?" if close else ".")
                    + " An actor names its lane exactly; add it to 'lanes' if it is a new one.",
                )
            )
        for index, lane in enumerate(listed):
            if lane not in named and listed.index(lane) == index:
                found.append(
                    Violation(
                        _pointer("lanes", index),
                        f"no node names {lane!r} as its actor, so its lane would be an empty "
                        f"strip saying that party does nothing. Drop it, or give it its step.",
                    )
                )
    elif listed is None:
        distinct: dict[str, int] = {}
        for index, actor in actors:
            if actor not in distinct:
                distinct[actor] = index
                if len(distinct) == LANES_MAX + 1:
                    found.append(
                        Violation(
                            _pointer("nodes", index, "actor"),
                            f"{actor!r} would be lane {LANES_MAX + 1}, and a lanes diagram "
                            f"can be read at {LANES_MAX} at most. Merge parties that act "
                            f"together, or split the process at a hand-off.",
                        )
                    )
    return found


def transition_label(event: str = "", guard: str = "", action: str = "") -> str:
    """A transition's label, `event [guard] / action`, from whichever parts were given.

    Composed here rather than written by the author, so the punctuation is the
    same on every transition and a missing part leaves no stray bracket or slash.
    Each part is set on its own line — the event, under it the guard, under that
    the action — because the three on one line made the widest labels in any
    drawing, and a label too long for the gap beside its line had nowhere to go.
    """
    parts = [event.strip()]
    if guard.strip():
        parts.append(f"[{guard.strip()}]")
    if action.strip():
        parts.append(f"/ {action.strip()}")
    return "\n".join(part for part in parts if part)


def _states_violations(document: Mapping[str, Any]) -> list[Violation]:
    """What a state machine may not be: ids that do not land, and a wrong machine.

    The structural pass has the types; this one has the meaning. Ids first —
    every state and group named once, every reference resolving — and only when
    those hold, the three claims about the machine itself: a final state that
    is left, a pair of transitions that make it non-deterministic, and a state
    nothing can reach. Each is a bug in the machine rather than in the drawing.
    """
    found: list[Violation] = []
    groups_raw = _listed(document, "groups")
    transitions = _listed(document, "transitions")

    state_ids: set[str] = set()
    for index, state in enumerate(_listed(document, "states")):
        identifier = state.get("id") if isinstance(state, dict) else None
        if not isinstance(identifier, str):
            continue
        if identifier in state_ids:
            found.append(
                Violation(_pointer("states", index, "id"), f"duplicate state id {identifier!r}")
            )
        state_ids.add(identifier)

    groups: dict[str, Mapping[str, Any]] = {}
    for index, group in enumerate(groups_raw):
        if not isinstance(group, dict) or not isinstance(group.get("id"), str):
            continue
        identifier = group["id"]
        if identifier in state_ids:
            found.append(
                Violation(
                    _pointer("groups", index, "id"),
                    f"{identifier!r} is already the id of a state; a transition naming it "
                    f"could mean either",
                )
            )
        elif identifier in groups:
            found.append(
                Violation(_pointer("groups", index, "id"), f"duplicate group id {identifier!r}")
            )
        else:
            groups[identifier] = group
    known = state_ids | set(groups)

    parent: dict[str, str] = {}
    for index, group in enumerate(groups_raw):
        if not isinstance(group, dict) or not isinstance(group.get("id"), str):
            continue
        members = group.get("members")
        members = members if isinstance(members, list) else []
        for position, member in enumerate(members):
            if not isinstance(member, str):
                continue
            if member not in known:
                found.append(
                    Violation(
                        _pointer("groups", index, "members", position),
                        f"{member!r} is not the id of any state or group in this document",
                    )
                )
            elif member == group["id"]:
                found.append(
                    Violation(
                        _pointer("groups", index, "members", position),
                        "a group cannot contain itself",
                    )
                )
            elif member in parent:
                found.append(
                    Violation(
                        _pointer("groups", index, "members", position),
                        f"{member!r} is already inside {parent[member]!r}. A state is in one "
                        f"composite or none; nest the groups instead.",
                    )
                )
            else:
                parent[member] = group["id"]
        entry = group.get("initial")
        if isinstance(entry, str) and entry not in members:
            found.append(
                Violation(
                    _pointer("groups", index, "initial"),
                    f"{entry!r} is not a member of {group['id']!r}. A composite is entered "
                    f"at one of its own states.",
                )
            )

    def entered(identifier: str, pointer: str) -> bool:
        """Whether naming `identifier` as a target lands on a state; reported if not."""
        group = groups.get(identifier)
        if group is None or isinstance(group.get("initial"), str):
            return True
        found.append(
            Violation(
                pointer,
                f"{identifier!r} is a group with no 'initial', so entering it does not say "
                f"which state the machine is then in. Give the group an 'initial', or point "
                f"this at one of its states.",
            )
        )
        return False

    initial = document.get("initial")
    if isinstance(initial, str):
        if initial not in known:
            found.append(
                Violation(
                    "/initial",
                    f"{initial!r} is not the id of any state or group in this document",
                )
            )
        else:
            entered(initial, "/initial")

    finals: set[str] = set()
    for index, name in enumerate(_listed(document, "final")):
        if not isinstance(name, str):
            continue
        pointer = _pointer("final", index)
        if name in groups:
            found.append(
                Violation(
                    pointer,
                    f"{name!r} is a group. A final state is a state; to end the machine when "
                    f"a composite completes, draw a transition from the group to a final state.",
                )
            )
        elif name not in state_ids:
            found.append(Violation(pointer, f"{name!r} is not the id of any state"))
        elif name in finals:
            found.append(Violation(pointer, f"{name!r} is named final twice"))
        finals.add(name)

    resolved = True
    for index, transition in enumerate(transitions):
        if not isinstance(transition, dict):
            continue
        for end in ("from", "to"):
            target = transition.get(end)
            if isinstance(target, str) and target not in known:
                resolved = False
                found.append(
                    Violation(
                        _pointer("transitions", index, end),
                        f"{target!r} is not the id of any state or group in this document",
                    )
                )
        source, target = transition.get("from"), transition.get("to")
        if isinstance(target, str) and target in groups:
            resolved = entered(target, _pointer("transitions", index, "to")) and resolved
        if isinstance(source, str) and source in finals:
            found.append(
                Violation(
                    _pointer("transitions", index, "from"),
                    f"{source!r} is a final state, and a final state is not left: the machine "
                    f"has ended there. Drop this transition, or take {source!r} out of 'final'.",
                )
            )
    found.extend(_self_containment(transitions, groups_raw, frozenset(groups)))
    found.extend(_loop_violations(transitions, frozenset(groups), "transitions"))

    # Two ways out of one state on the same event and guard: which one is taken?
    seen: dict[tuple[str, str, str], tuple[int, str]] = {}
    for index, transition in enumerate(transitions):
        if not isinstance(transition, dict):
            continue
        source, target = transition.get("from"), transition.get("to")
        event, guard = transition.get("event", ""), transition.get("guard", "")
        if not all(isinstance(value, str) for value in (source, target, event, guard)):
            continue
        key = (str(source), str(event).strip(), str(guard).strip())
        if key in seen and seen[key][1] != target:
            first = seen[key][0]
            found.append(
                Violation(
                    _pointer("transitions", index, "to"),
                    f"transitions {first} and {index} both leave {source!r} on "
                    + (f"{event.strip()!r}" if event.strip() else "completion")
                    + (f" when {guard.strip()!r}" if guard.strip() else "")
                    + ", to different states, so the machine cannot say which it takes. "
                    "Give them guards that tell them apart.",
                )
            )
        seen.setdefault(key, (index, str(target)))

    if found or not resolved or not isinstance(initial, str):
        return found

    # Reachability, through the composites: entering a group enters its initial,
    # and a transition from a group leaves from every state inside it.
    def ancestors(identifier: str) -> list[str]:
        chain: list[str] = []
        current = parent.get(identifier)
        while current is not None and current not in chain:
            chain.append(current)
            current = parent.get(current)
        return chain

    leaving: dict[str, list[str]] = {}
    for transition in transitions:
        if isinstance(transition, dict):
            leaving.setdefault(transition["from"], []).append(transition["to"])

    reached: set[str] = set()
    queue = [initial]
    while queue:
        current = queue.pop()
        if current in reached:
            continue
        reached.add(current)
        group = groups.get(current)
        if group is not None:
            queue.append(str(group["initial"]))
            continue
        for scope in (current, *ancestors(current)):
            reached.add(scope)
            queue.extend(leaving.get(scope, ()))

    for index, state in enumerate(_listed(document, "states")):
        identifier = state.get("id") if isinstance(state, dict) else None
        if isinstance(identifier, str) and identifier not in reached:
            found.append(
                Violation(
                    _pointer("states", index),
                    f"no transition reaches {identifier!r} from the initial state, so the "
                    f"machine can never be in it. Add the transition that leads there, or "
                    f"delete the state.",
                )
            )
    return found


#: The most self-loops one box may carry: one on each side across the reading
#: direction. Mirrors `drawspec.routing.MAX_LOOPS`, which the drawing obeys.
MAX_SELF_LOOPS: Final = 2


def _loop_violations(edges: Sequence[Any], groups: Set[str], name: str) -> list[Violation]:
    """Self-loops drawspec has nowhere to draw: on a group, or a third on one box.

    A loop leaves a box and comes back to the same side; a frame has a border
    other edges cross on their way in, and a loop on it would read as one of
    them. A box has two sides across the reading direction, so two loops.
    """
    found: list[Violation] = []
    counted: dict[str, int] = {}
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            continue
        source, target = edge.get("from"), edge.get("to")
        if not isinstance(source, str) or source != target:
            continue
        if source in groups:
            found.append(
                Violation(
                    _pointer(name, index, "to"),
                    f"{source!r} is a group, and a loop from a group back to itself has no box "
                    f"to loop on. Draw it on the member it starts from.",
                )
            )
            continue
        counted[source] = counted.get(source, 0) + 1
        if counted[source] > MAX_SELF_LOOPS:
            found.append(
                Violation(
                    _pointer(name, index, "to"),
                    f"{source!r} already loops back to itself {MAX_SELF_LOOPS} times, one on "
                    f"each side of its box. Join these into one label, or split the state.",
                )
            )
    return found


def _sequence_violations(document: Mapping[str, Any]) -> list[Violation]:
    """What a sequence diagram may not be: ids that do not land, and frames that cannot draw.

    Ids first — participants and groups named once, every message's ends a
    participant, every fragment's ends a message — then the claims only this
    kind makes: a participant nobody talks to, a group whose lifelines are not
    neighbours, a fragment that ends before it starts or half-overlaps another,
    and a branch divider that is not inside its own frame.
    """
    found: list[Violation] = []
    participants: dict[str, int] = {}
    for index, participant in enumerate(_listed(document, "participants")):
        identifier = participant.get("id") if isinstance(participant, dict) else None
        if not isinstance(identifier, str):
            continue
        if identifier in participants:
            found.append(
                Violation(
                    _pointer("participants", index, "id"),
                    f"duplicate participant id {identifier!r}",
                )
            )
            continue
        participants[identifier] = index

    talking: set[str] = set()
    message_ids: dict[str, int] = {}
    for index, message in enumerate(_listed(document, "messages")):
        if not isinstance(message, dict):
            continue
        for end in ("from", "to"):
            target = message.get(end)
            if not isinstance(target, str):
                continue
            if target not in participants:
                found.append(
                    Violation(
                        _pointer("messages", index, end),
                        f"{target!r} is not the id of any participant in this document",
                    )
                )
            talking.add(target)
        identifier = message.get("id")
        if isinstance(identifier, str):
            if identifier in message_ids:
                found.append(
                    Violation(
                        _pointer("messages", index, "id"),
                        f"duplicate message id {identifier!r}",
                    )
                )
            else:
                message_ids[identifier] = index

    for identifier, index in participants.items():
        if identifier not in talking:
            found.append(
                Violation(
                    _pointer("participants", index),
                    f"no message is sent to or from {identifier!r}, so its lifeline would be "
                    f"a box with a line under it. It is usually a mistyped id in a message; "
                    f"otherwise delete the participant.",
                )
            )

    found.extend(_sequence_group_violations(document, participants))
    found.extend(_fragment_violations(document, message_ids))
    return found


def _entities_violations(document: Mapping[str, Any]) -> list[Violation]:
    """What an entity diagram may not be: ids that do not land, and relations that cannot draw.

    Entity ids once each and field ids once in the document; every relation's
    ends an entity and every `from_field`/`to_field` a field *of that end's*
    entity; no relation of an entity to itself; a `...` row only last, and
    plain; no cardinality on a hierarchy relation, and no hierarchy that loops.
    """
    found: list[Violation] = []
    entities: dict[str, int] = {}
    owner: dict[str, str] = {}
    for index, entity in enumerate(_listed(document, "entities")):
        if not isinstance(entity, dict):
            continue
        identifier = entity.get("id")
        if isinstance(identifier, str):
            if identifier in entities:
                found.append(
                    Violation(
                        _pointer("entities", index, "id"), f"duplicate entity id {identifier!r}"
                    )
                )
            else:
                entities[identifier] = index
        tag = entity.get("tag")
        if isinstance(tag, str) and len(tag) > TAG_MAX:
            found.append(
                Violation(
                    _pointer("entities", index, "tag"),
                    f"a tag is a stereotype — a word or two — and this one is {len(tag)} "
                    f"characters; {TAG_MAX} at most. Put a description in the name or the "
                    f"surrounding prose.",
                )
            )
        fields = entity.get("fields")
        rows = fields if isinstance(fields, list) else []
        for row, field in enumerate(rows):
            if not isinstance(field, dict):
                continue
            where = ("entities", index, "fields", row)
            text = field.get("text")
            if isinstance(text, str) and text.strip() in FIELD_PLACEHOLDERS:
                if row != len(rows) - 1:
                    found.append(
                        Violation(
                            _pointer(*where, "text"),
                            "a `...` field stands for the fields not shown, so it comes "
                            "last. Move it to the end of this entity's fields.",
                        )
                    )
                for name in ("id", "type", "key"):
                    if name in field:
                        found.append(
                            Violation(
                                _pointer(*where, name),
                                f"a `...` field stands for fields not shown, so it has no "
                                f"{name} of its own. Delete it.",
                            )
                        )
            if isinstance(text, str) and "\n" in text:
                found.append(
                    Violation(
                        _pointer(*where, "text"),
                        "a field is one row: write its name on one line, and its type in `type`.",
                    )
                )
            field_id = field.get("id")
            if isinstance(field_id, str) and isinstance(identifier, str):
                if field_id in owner:
                    found.append(
                        Violation(_pointer(*where, "id"), f"duplicate field id {field_id!r}")
                    )
                else:
                    owner[field_id] = identifier
        text = entity.get("text")
        if isinstance(text, str) and "\n" in text:
            found.append(
                Violation(
                    _pointer("entities", index, "text"),
                    "an entity's name is one line — what it holds goes in `fields`, and a "
                    "stereotype in `tag`.",
                )
            )

    hierarchy: dict[str, list[str]] = {}
    for index, edge in enumerate(_listed(document, "edges")):
        if not isinstance(edge, dict):
            continue
        ends: dict[str, str] = {}
        for end in ("from", "to"):
            target = edge.get(end)
            if not isinstance(target, str):
                continue
            if target not in entities:
                found.append(
                    Violation(
                        _pointer("edges", index, end),
                        f"{target!r} is not the id of any entity in this document"
                        + _closest(target, entities),
                    )
                )
                continue
            ends[end] = target
        if ends.get("from") is not None and ends.get("from") == ends.get("to"):
            found.append(
                Violation(
                    _pointer("edges", index, "to"),
                    "a relation from an entity to itself is not drawn: name the field that "
                    "holds the reference (`manager_id`, key `foreign`) and say what it "
                    "points at in its text, or draw the two roles as two entities.",
                )
            )
        for end in ("from", "to"):
            named = edge.get(f"{end}_field")
            if not isinstance(named, str) or end not in ends:
                continue
            if named not in owner:
                found.append(
                    Violation(
                        _pointer("edges", index, f"{end}_field"),
                        f"{named!r} is not the id of any field in this document"
                        + _closest(named, owner),
                    )
                )
            elif owner[named] != ends[end]:
                found.append(
                    Violation(
                        _pointer("edges", index, f"{end}_field"),
                        f"{named!r} is a field of {owner[named]!r}, not of {ends[end]!r}: "
                        f"the line would leave a box from a row it does not have.",
                    )
                )
        role = edge.get("role", "link")
        if role == "owns" and "to_end" in edge:
            found.append(
                Violation(
                    _pointer("edges", index, "to_end"),
                    "the `to` end of `owns` is the whole, drawn as the diamond, and a part "
                    "belongs to exactly one whole — there is no count to draw there. Delete "
                    "'to_end'; say how many parts with 'from_end'.",
                )
            )
        if role in HIERARCHY_ROLES:
            for name in ("from_end", "to_end", "from_field", "to_field"):
                if name in edge:
                    what = "cardinality" if name.endswith("_end") else "row to land on"
                    found.append(
                        Violation(
                            _pointer("edges", index, name),
                            f"{role!r} says one class is a kind of another, which has no "
                            f"{what}: inheritance is between whole classes, one to one. "
                            f"Delete {name!r}.",
                        )
                    )
            if "from" in ends and "to" in ends and ends["from"] != ends["to"]:
                if _reaches(hierarchy, ends["to"], ends["from"]):
                    found.append(
                        Violation(
                            _pointer("edges", index),
                            f"this {role!r} closes a loop: {ends['to']!r} is already, "
                            f"through others, a kind of {ends['from']!r}. A hierarchy has "
                            f"a top; delete the relation that is the wrong way round.",
                        )
                    )
                else:
                    hierarchy.setdefault(ends["from"], []).append(ends["to"])
    return found


#: What a gantt says to a date: the owner's decision, and the two ways round it.
GANTT_NO_DATES: Final = (
    "a gantt draws no calendar, so a place on its axis is a number in a unit the axis names — "
    'with `"axis": {"label": "Week"}`, week 3 is 3. For a plan by month or sprint, name '
    "the periods in `axis.categories` and count them: the first runs from 1 to 2."
)


def _gantt_refusal(violation: Violation, document: Mapping[str, Any]) -> Violation:
    """A structural refusal in a gantt, told what this kind means by it.

    A string where a task's place belongs is almost always a date, and the generic
    "expected number" says nothing about why one is not accepted. `progress` is
    refused by name for the reason the proposal gives.
    """
    parts = violation.pointer.split("/")
    if len(parts) == 4 and parts[1] in ("tasks", "marks"):
        name = parts[3]
        try:
            value = document[parts[1]][int(parts[2])][name]
        except (TypeError, ValueError, IndexError, KeyError):
            value = None
        if name in TASK_VALUES and isinstance(value, str):
            return Violation(violation.pointer, f"{value!r} is not a number: {GANTT_NO_DATES}")
        if parts[1] == "tasks" and name in ("progress", "complete", "percent"):
            return Violation(
                violation.pointer,
                f"{name!r} is not drawn: how far a task has got is status, not plan, and it "
                f"is out of date the day the drawing is made. Say it in the text, or draw "
                f"what is done as tasks that have ended before a `today` mark.",
            )
    return violation


def _gantt_violations(document: Mapping[str, Any]) -> list[Violation]:
    """What a plan may not be: tasks that are not one thing, and claims that cannot hold.

    Each task is a milestone or an interval, ends after it starts, and sits on the
    axis; ids land; a dependency's task does not start before the one it waits
    for ends; a phase is a run of consecutive tasks, and with phases every task
    is in one.
    """
    found: list[Violation] = []
    axis = document.get("axis")
    axis = axis if isinstance(axis, dict) else {}
    low, high = axis.get("min"), axis.get("max")
    low = low if _is_number(low) else None
    high = high if _is_number(high) else None
    categories = axis.get("categories")
    if isinstance(categories, list) and categories:
        for name in ("min", "max"):
            if name in axis:
                found.append(
                    Violation(
                        _pointer("axis", name),
                        f"with categories the axis runs from 1 to {len(categories) + 1}, one "
                        f"period each, so it takes no {name!r}. Drop it, or drop the categories "
                        f"and number the axis.",
                    )
                )
        low, high = 1, len(categories) + 1
    elif low is not None and high is not None and high <= low:
        found.append(
            Violation(
                _pointer("axis", "max"), f"the axis ends at {high}, not after its start {low}"
            )
        )
        low = high = None

    remedy = "add periods to the categories" if categories else "widen the axis"

    def outside(value: float, pointer: str) -> None:
        if (low is not None and value < low) or (high is not None and value > high):
            span = f"{'…' if low is None else low} to {'…' if high is None else high}"
            found.append(
                Violation(
                    pointer,
                    f"{value} is off the axis, which runs {span}: it would be drawn off the "
                    f"plot. Fix the value or {remedy}.",
                )
            )

    tasks: dict[str, tuple[float, float] | None] = {}
    order: dict[str, int] = {}
    for index, task in enumerate(_listed(document, "tasks")):
        if not isinstance(task, dict):
            continue
        identifier = task.get("id")
        here = _pointer("tasks", index)
        values = {name: task[name] for name in TASK_VALUES if _is_number(task.get(name))}
        given = {name for name in TASK_VALUES if name in task}
        span: tuple[float, float] | None = None
        if "at" in given and given & {"start", "end"}:
            found.append(
                Violation(
                    _pointer("tasks", index, "at"),
                    "a task is a milestone (`at`) or an interval (`start` and `end`), not both. "
                    "For a step that ends in a milestone, write the two as two tasks.",
                )
            )
        elif "at" in given:
            if "at" in values:
                span = (values["at"], values["at"])
        elif not given:
            found.append(
                Violation(
                    here,
                    "a task needs `start` and `end` (an interval) or `at` (a milestone); it has "
                    "no place on the axis.",
                )
            )
        elif given != {"start", "end"}:
            missing = ({"start", "end"} - given).pop()
            found.append(
                Violation(
                    _pointer("tasks", index, missing),
                    f"{missing!r} is required with {({'start', 'end'} - {missing}).pop()!r}: "
                    f"an interval has two ends. For a point in time, write `at` alone.",
                )
            )
        elif "start" in values and "end" in values:
            if values["end"] <= values["start"]:
                found.append(
                    Violation(
                        _pointer("tasks", index, "end"),
                        f"this task ends at {values['end']}, which is not after it starts at "
                        f"{values['start']}. For a point in time, write `at` instead.",
                    )
                )
            else:
                span = (values["start"], values["end"])
        for name, value in values.items():
            outside(value, _pointer("tasks", index, name))
        text = task.get("text")
        if isinstance(task.get("actor"), str) and isinstance(text, str) and "\n" in text:
            found.append(
                Violation(
                    _pointer("tasks", index, "text"),
                    "a task with an actor has the actor as its label's lead, so its text may "
                    "not start a second paragraph. Put it on one line.",
                )
            )
        if not isinstance(identifier, str):
            continue
        if identifier in tasks:
            found.append(
                Violation(_pointer("tasks", index, "id"), f"duplicate task id {identifier!r}")
            )
            continue
        tasks[identifier] = span
        order[identifier] = index

    for index, mark in enumerate(_listed(document, "marks")):
        if isinstance(mark, dict) and _is_number(mark.get("at")):
            outside(mark["at"], _pointer("marks", index, "at"))

    for index, edge in enumerate(_listed(document, "edges")):
        if not isinstance(edge, dict):
            continue
        ends = {name: edge.get(name) for name in ("from", "to")}
        sound = True
        for name, target in ends.items():
            if isinstance(target, str) and target not in tasks:
                found.append(
                    Violation(
                        _pointer("edges", index, name),
                        f"{target!r} is not the id of any task in this document"
                        + _closest(target, tasks),
                    )
                )
                sound = False
        source, target = ends["from"], ends["to"]
        if not (sound and isinstance(source, str) and isinstance(target, str)):
            continue
        if source == target:
            found.append(Violation(_pointer("edges", index, "to"), "a task cannot wait for itself"))
            continue
        before, after = tasks[source], tasks[target]
        if before is not None and after is not None and after[0] < before[1]:
            found.append(
                Violation(
                    _pointer("edges", index, "to"),
                    f"{target!r} starts at {after[0]}, before {source!r} ends at {before[1]}, "
                    f"and a dependency says it cannot start until then. Either the plan or "
                    f"the dependency is wrong; only you know which.",
                )
            )

    groups = _listed(document, "groups")
    owner: dict[str, str] = {}
    group_ids: set[str] = set()
    for index, group in enumerate(groups):
        if not isinstance(group, dict):
            continue
        identifier = group.get("id")
        if isinstance(identifier, str):
            if identifier in tasks:
                found.append(
                    Violation(
                        _pointer("groups", index, "id"), f"{identifier!r} is already a task's id"
                    )
                )
            elif identifier in group_ids:
                found.append(
                    Violation(_pointer("groups", index, "id"), f"duplicate group id {identifier!r}")
                )
            group_ids.add(identifier)
        if "text" not in group:
            found.append(
                Violation(
                    _pointer("groups", index, "text"),
                    "a phase is drawn as its name over its tasks, so it needs `text`",
                )
            )
        members = group.get("members")
        if not isinstance(members, list):
            continue
        rows: list[int] = []
        sound = True
        for position, member in enumerate(members):
            if not isinstance(member, str):
                sound = False
                continue
            pointer = _pointer("groups", index, "members", position)
            if member not in tasks:
                found.append(Violation(pointer, f"{member!r} is not the id of any task"))
                sound = False
            elif member in owner:
                found.append(
                    Violation(
                        pointer,
                        f"{member!r} is already in {owner[member]!r}. A task is in one phase.",
                    )
                )
                sound = False
            else:
                owner[member] = str(identifier)
                rows.append(order[member])
        if not sound or not rows:
            continue
        names = {row: name for name, row in order.items()}
        between = [names[row] for row in range(min(rows), max(rows) + 1) if row not in rows]
        if between:
            found.append(
                Violation(
                    _pointer("groups", index, "members"),
                    f"{between[0]!r} stands between members of {identifier!r} in 'tasks', so "
                    f"the phase would take in a row that is not in it. Reorder 'tasks' so a "
                    f"phase's tasks are next to each other.",
                )
            )
    if groups:
        for identifier, index in order.items():
            if identifier not in owner:
                found.append(
                    Violation(
                        _pointer("tasks", index),
                        f"{identifier!r} is in no phase, and with phases its row would read as "
                        f"part of the one above it. Put it in a group, or drop 'groups'.",
                    )
                )
    return found


#: Fields a board refuses by name, and why: what an author reaches for when the
#: board is really something else, or when appearance is wanted per card.
BOARD_REFUSED: Final = {
    "edges": (
        "a board has no connectors: its cards are sorted, not joined. If the order between "
        "cards matters, it is a `flow` — or `lanes`, when who hands off to whom matters"
    ),
    "label": "a card has its `text`, and its kind is its column; a second label is a tag",
    "tag": "appearance is the role's, and a card's kind is its column. Name it in the text",
    "tags": "appearance is the role's, and a card's kind is its column. Name it in the text",
    "colour": "appearance is the role's, and a card's kind is its column",
}


def _board_refusal(violation: Violation) -> Violation:
    """An unknown field on a board, told why a board has no place for it."""
    name = violation.pointer.rsplit("/", 1)[-1]
    if name in BOARD_REFUSED and "is not a known field" in violation.message:
        return Violation(violation.pointer, f"{name!r}: {BOARD_REFUSED[name]}.")
    return violation


def _board_violations(document: Mapping[str, Any]) -> list[Violation]:
    """What a board may not be: cards in columns or rows it does not have, half a story map.

    Column and row ids are unique and land; with rows every card names one and
    without them none does; a cut names a row that has another below it; a card
    with an actor keeps its text on one line.
    """
    found: list[Violation] = []

    def ids(name: str) -> dict[str, int]:
        seen: dict[str, int] = {}
        for index, entry in enumerate(_listed(document, name)):
            identifier = entry.get("id") if isinstance(entry, dict) else None
            if not isinstance(identifier, str):
                continue
            if identifier in seen:
                found.append(
                    Violation(
                        _pointer(name, index, "id"), f"duplicate {name[:-1]} id {identifier!r}"
                    )
                )
                continue
            seen[identifier] = index
        return seen

    columns = ids("columns")
    rows = ids("rows")
    has_rows = isinstance(document.get("rows"), list)

    cut = document.get("cut")
    if isinstance(cut, str):
        if not has_rows:
            found.append(
                Violation(
                    "/cut",
                    "a cut is drawn under a row, and this board has no `rows`. Add the slices "
                    "(a first release and what follows), or drop the cut.",
                )
            )
        elif cut not in rows:
            found.append(
                Violation("/cut", f"{cut!r} is not the id of any row" + _closest(cut, rows))
            )
        elif rows[cut] == len(document["rows"]) - 1:
            found.append(
                Violation(
                    "/cut",
                    f"{cut!r} is the last row, and a cut with nothing below it cuts nothing. "
                    f"Name the row the first release ends at.",
                )
            )

    for index, card in enumerate(_listed(document, "cards")):
        if not isinstance(card, dict):
            continue
        column = card.get("column")
        if isinstance(column, str) and column not in columns:
            found.append(
                Violation(
                    _pointer("cards", index, "column"),
                    f"{column!r} is not the id of any column" + _closest(column, columns),
                )
            )
        row = card.get("row")
        if has_rows and "row" not in card:
            found.append(
                Violation(
                    _pointer("cards", index, "row"),
                    "'row' is required: this board has rows, so every card is in one — half a "
                    "story map is a mistake. Name the slice it ships in.",
                )
            )
        elif not has_rows and "row" in card:
            found.append(
                Violation(
                    _pointer("cards", index, "row"),
                    "this board has no `rows`, so a card cannot be in one. Add the rows (a "
                    "story map), or drop 'row' from every card (a kanban board).",
                )
            )
        elif isinstance(row, str) and row not in rows:
            found.append(
                Violation(
                    _pointer("cards", index, "row"),
                    f"{row!r} is not the id of any row" + _closest(row, rows),
                )
            )
        text = card.get("text")
        if isinstance(card.get("actor"), str) and isinstance(text, str) and "\n" in text:
            found.append(
                Violation(
                    _pointer("cards", index, "text"),
                    "a card with an actor has the actor as its lead, so its text may not start "
                    "a second paragraph. Put it on one line, or the rest in `note`.",
                )
            )
    return found


#: Why a fishbone has no place for a field an author may reach for.
FISHBONE_REFUSED: Final = {
    "edges": (
        "the connections of a fishbone are its structure, so there is nothing to add. A cause "
        "that contributes to another cause is a different diagram: a `flow`"
    ),
    "causes": (
        "a cause is a leaf. A sub-cause of a cause is a second fishbone, with that cause as "
        "its effect — draw that one beside this"
    ),
    "role": (
        "the effect is the head, always drawn as the diagram's emphasis; it takes no role. "
        "Mark the confirmed root cause with `emphasis` on that cause instead"
    ),
}


def _fishbone_refusal(violation: Violation) -> Violation:
    """A structural refusal in a fishbone, told what this kind means by it."""
    parts = violation.pointer.split("/")
    name = parts[-1]
    unknown = "is not a known field" in violation.message
    if unknown and name == "edges" and len(parts) == 2:
        return Violation(violation.pointer, f"'edges': {FISHBONE_REFUSED['edges']}.")
    if unknown and name == "causes" and len(parts) == 6:
        return Violation(violation.pointer, f"'causes': {FISHBONE_REFUSED['causes']}.")
    if unknown and name == "role" and parts[1:2] == ["effect"]:
        return Violation(violation.pointer, f"'role': {FISHBONE_REFUSED['role']}.")
    if "needs at least" in violation.message:
        if parts[1:] == ["categories"]:
            return Violation(
                violation.pointer,
                "a fishbone needs at least 2 categories: one category is a list of causes. "
                "Write it as a list, or name the second category the causes fall under.",
            )
        if len(parts) == 4 and name == "causes":
            return Violation(
                violation.pointer,
                "a category with no causes is a heading with no investigation under it. If "
                'nothing was found, say so: `{"text": "nothing found", "role": "note"}`.',
            )
    if len(parts) == 6 and name == "role" and "is not one of" in violation.message:
        return Violation(
            violation.pointer,
            violation.message.split(".")[0]
            + ". A cause is a tick on a bone, with no shape to mean `decision` or "
            "`terminal`: `step`, `emphasis` for the confirmed root cause, `note` for one "
            "ruled out.",
        )
    return violation


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _reaches(graph: Mapping[str, Sequence[str]], start: str, goal: str) -> bool:
    """Whether `goal` is reachable from `start` along `graph`'s edges."""
    seen: set[str] = set()
    stack = [start]
    while stack:
        here = stack.pop()
        if here == goal:
            return True
        if here in seen:
            continue
        seen.add(here)
        stack.extend(graph.get(here, ()))
    return False


def _closest(name: str, known: Mapping[str, Any]) -> str:
    """`; did you mean 'x'?` when one known id is close to `name`, else nothing."""
    close = get_close_matches(name, list(known), n=1)
    return f"; did you mean {close[0]!r}?" if close else ""


def _sequence_group_violations(
    document: Mapping[str, Any], participants: Mapping[str, int]
) -> list[Violation]:
    """Groups over lifelines: known members, one group each, and neighbours."""
    found: list[Violation] = []
    names = {index: identifier for identifier, index in participants.items()}
    owner: dict[str, str] = {}
    group_ids: set[str] = set()
    for index, group in enumerate(_listed(document, "groups")):
        if not isinstance(group, dict):
            continue
        identifier = group.get("id")
        if isinstance(identifier, str):
            if identifier in participants:
                found.append(
                    Violation(
                        _pointer("groups", index, "id"),
                        f"{identifier!r} is already the id of a participant",
                    )
                )
            elif identifier in group_ids:
                found.append(
                    Violation(_pointer("groups", index, "id"), f"duplicate group id {identifier!r}")
                )
            group_ids.add(identifier)
        members = group.get("members")
        if not isinstance(members, list):
            continue
        positions: list[int] = []
        sound = True
        for position, member in enumerate(members):
            if not isinstance(member, str):
                sound = False
                continue
            pointer = _pointer("groups", index, "members", position)
            if member not in participants:
                found.append(Violation(pointer, f"{member!r} is not the id of any participant"))
                sound = False
            elif member in owner:
                found.append(
                    Violation(
                        pointer,
                        f"{member!r} is already in {owner[member]!r}. A lifeline is in one "
                        f"group or none.",
                    )
                )
                sound = False
            else:
                owner[member] = str(identifier)
                positions.append(participants[member])
        if not sound or not positions:
            continue
        inside = set(positions)
        between = [
            names[spot] for spot in range(min(positions), max(positions) + 1) if spot not in inside
        ]
        if between:
            found.append(
                Violation(
                    _pointer("groups", index, "members"),
                    f"{between[0]!r} stands between members of {identifier!r} in "
                    f"'participants', so the group's frame would enclose a lifeline that is "
                    f"not in it. Reorder 'participants' so the members are next to each other.",
                )
            )
    return found


def _fragment_violations(
    document: Mapping[str, Any], message_ids: Mapping[str, int]
) -> list[Violation]:
    """Fragments: ends that are messages, in order, nested or apart, and branches inside."""
    found: list[Violation] = []
    spans: list[tuple[int, int, int]] = []
    fragments = _listed(document, "fragments")
    for index, fragment in enumerate(fragments):
        if not isinstance(fragment, dict):
            continue
        ends: dict[str, int] = {}
        for end in ("from", "to"):
            target = fragment.get(end)
            if not isinstance(target, str):
                continue
            if target not in message_ids:
                found.append(
                    Violation(
                        _pointer("fragments", index, end),
                        f"{target!r} is not the id of any message. A fragment names its first "
                        f"and last message by their 'id'.",
                    )
                )
            else:
                ends[end] = message_ids[target]
        if len(ends) < 2:
            continue
        start, finish = ends["from"], ends["to"]
        if finish < start:
            found.append(
                Violation(
                    _pointer("fragments", index, "to"),
                    f"{fragment['to']!r} comes before {fragment['from']!r}, so the frame would "
                    f"end before it starts. Swap them.",
                )
            )
            continue
        spans.append((index, start, finish))

    for position, (index, start, finish) in enumerate(spans):
        for other, first, last in spans[:position]:
            if first < start <= last < finish or start < first <= finish < last:
                found.append(
                    Violation(
                        _pointer("fragments", index),
                        f"this fragment starts inside fragment {other} and ends outside it "
                        f"(or the other way round), and no frame drawing of that does not "
                        f"cross. Fragments nest or are apart: end one inside the other, or "
                        f"after it.",
                    )
                )

    span_of = {index: (start, finish) for index, start, finish in spans}
    for index, fragment in enumerate(fragments):
        if not isinstance(fragment, dict) or "else" not in fragment:
            continue
        branches = fragment.get("else")
        if not isinstance(branches, list):
            continue
        operator = fragment.get("operator")
        if operator not in BRANCHING_OPERATORS:
            found.append(
                Violation(
                    _pointer("fragments", index, "else"),
                    f"a {operator!r} fragment has one branch, so it has nothing to divide. "
                    f"Only {' and '.join(repr(name) for name in BRANCHING_OPERATORS)} take "
                    f"'else'.",
                )
            )
            continue
        if index not in span_of:
            continue
        start, finish = span_of[index]
        previous = start
        for position, branch in enumerate(branches):
            at = branch.get("at") if isinstance(branch, dict) else None
            if not isinstance(at, str):
                continue
            pointer = _pointer("fragments", index, "else", position, "at")
            if at not in message_ids:
                found.append(Violation(pointer, f"{at!r} is not the id of any message"))
                continue
            row = message_ids[at]
            if not start < row <= finish:
                found.append(
                    Violation(
                        pointer,
                        f"{at!r} is not after the fragment's first message and within it, so "
                        f"the divider above it would be "
                        + ("at the frame's top" if row == start else "outside the frame")
                        + ". A branch starts at a later message inside the fragment.",
                    )
                )
                continue
            if row <= previous and position:
                found.append(
                    Violation(
                        pointer,
                        f"{at!r} does not come after the previous divider. List the "
                        f"branches in the order their messages are.",
                    )
                )
                continue
            previous = row
            for other, (first, last) in span_of.items():
                inner = other != index and start <= first and last <= finish
                if inner and (first, last) != (start, finish) and first < row <= last:
                    found.append(
                        Violation(
                            pointer,
                            f"{at!r} is inside fragment {other}, which is nested in this one, "
                            f"so the divider would cut through that frame. Divide at its "
                            f"first message, or at one outside it.",
                        )
                    )
                    break
    return found


def _listed(document: Mapping[str, Any], name: str) -> list[Any]:
    value = document.get(name)
    return value if isinstance(value, list) else []


def _status_violations(document: Mapping[str, Any], kind: str) -> list[Violation]:
    """Where a change's marks contradict each other, or are on a kind with no change.

    Marks on a drawing of a change make claims about the state after it, so two
    of them can disagree: an edge that stays, drawn to a box that goes, would
    outlive what it connects; an edge that was always there cannot reach a box
    that is new. Each is refused at the edge's `status`, where the fix is.
    """
    nodes = document.get("nodes")
    edges = document.get("edges")
    found: list[Violation] = []
    if kind == "cycle":
        for name, entries in (("nodes", nodes), ("edges", edges)):
            for index, entry in enumerate(entries if isinstance(entries, list) else ()):
                if isinstance(entry, dict) and "status" in entry:
                    found.append(
                        Violation(
                            _pointer(name, index, "status"),
                            "a cycle that changes is a different cycle, and a ring with a "
                            "step marked removed is still drawn as a ring through it. Draw "
                            "the loop before and the loop after as two cycles.",
                        )
                    )
        return found
    status_of = {
        node["id"]: node.get("status", "")
        for node in (nodes if isinstance(nodes, list) else ())
        if isinstance(node, dict) and isinstance(node.get("id"), str)
    }
    for index, edge in enumerate(edges if isinstance(edges, list) else ()):
        if not isinstance(edge, dict):
            continue
        ends = {
            end: status_of.get(edge.get(end), "")
            for end in ("from", "to")
            if isinstance(edge.get(end), str)
        }
        marked = edge.get("status", "")
        gone = [edge[end] for end, status in ends.items() if status == "removed"]
        new = [edge[end] for end, status in ends.items() if status == "added"]
        pointer = _pointer("edges", index, "status")
        if gone and new:
            found.append(
                Violation(
                    pointer,
                    f"this edge joins {new[0]!r}, which the change adds, to {gone[0]!r}, "
                    f"which it removes. The two never exist at the same time, so nothing "
                    f"can connect them.",
                )
            )
        elif gone and marked != "removed":
            found.append(
                Violation(
                    pointer,
                    f"{gone[0]!r} is removed by this change, so an edge to it cannot "
                    f"outlive it: mark this edge 'removed' too.",
                )
            )
        elif new and marked != "added":
            found.append(
                Violation(
                    pointer,
                    f"{new[0]!r} is added by this change, so an edge to it is new as well: "
                    f"mark this edge 'added'.",
                )
            )
    return found


def _scale_violations(scale: Sequence[str], cells: Sequence[Any]) -> list[Violation]:
    """What an ordered fill may not be: too long, repeated, or missing a cell's group.

    A `scale` turns a matrix's groups from a set into an order, so every filled
    cell has to be *on* it — a cell in a group the scale does not name would take
    a fill that means nothing on a drawing whose fills are amounts.
    """
    found: list[Violation] = []
    if len(scale) > RAMP_STEPS:
        found.append(
            Violation(
                _pointer("scale", RAMP_STEPS),
                f"a scale of {len(scale)} steps is past what tone can carry — {RAMP_STEPS} "
                f"at most. Beyond that, neighbouring steps are one grey in print and the "
                f"order stops being visible. Merge buckets until there are {RAMP_STEPS} "
                f"or fewer.",
            )
        )
    seen: set[str] = set()
    for index, step in enumerate(scale):
        if not step.strip():
            found.append(Violation(_pointer("scale", index), "a scale step needs a name"))
        elif step in seen:
            found.append(
                Violation(
                    _pointer("scale", index),
                    f"{step!r} is already a step of this scale. An order names each step once.",
                )
            )
        seen.add(step)
    for index, cell in enumerate(cells):
        if not isinstance(cell, dict):
            continue
        group = cell.get("group")
        if isinstance(group, str) and group and group not in seen:
            found.append(
                Violation(
                    _pointer("cells", index, "group"),
                    f"{group!r} is not a step of this matrix's scale ({', '.join(scale)}). "
                    f"When the groups are an order every filled cell is on it; leave "
                    f"'group' out for a cell that was not assessed.",
                )
            )
    return found


def _hub_violations(document: Mapping[str, Any], nodes: Set[str]) -> list[Violation]:
    """What a `cycle`'s hub may not be: a step, a duplicate, or a middle of too little.

    The hub shares the node id space so an edge can name it, and that is the one
    thing it shares: an edge to it is a spoke, so only a role drawn without a
    solid head may make one. A `flow` arrow from the last step into the middle
    reads as the loop ending there, which is the opposite of what a hub says.
    """
    hub = document.get("hub")
    if not isinstance(hub, dict) or not isinstance(hub.get("id"), str):
        return []
    found: list[Violation] = []
    identifier = hub["id"]
    if identifier in nodes:
        found.append(
            Violation(
                "/hub/id",
                f"{identifier!r} is already the id of a node. The hub is not a step on the "
                f"ring, so it needs an id of its own.",
            )
        )
    steps = document.get("nodes")
    if isinstance(steps, list) and len(steps) < HUB_MINIMUM_NODES:
        found.append(
            Violation(
                "/hub",
                f"a hub needs a ring of at least {HUB_MINIMUM_NODES} steps around it, and "
                f"this one has {len(steps)}. Two steps and a middle is three boxes in a "
                f"row: draw it as a flow.",
            )
        )
    for index, edge in enumerate(document.get("edges", ()) or ()):
        if not isinstance(edge, dict) or identifier not in (edge.get("from"), edge.get("to")):
            continue
        if edge.get("from") == edge.get("to"):
            found.append(
                Violation(
                    _pointer("edges", index, "to"),
                    "the hub is joined to itself, and there is nowhere to draw that: a "
                    "spoke runs between the middle and a step.",
                )
            )
            continue
        role = edge.get("role", "flow")
        if isinstance(role, str) and role not in HUB_EDGE_ROLES:
            found.append(
                Violation(
                    _pointer("edges", index, "role"),
                    f"an edge to the hub is a spoke, and {role!r} draws a solid arrow, "
                    f"which reads as one more step of the loop. Give it one of "
                    f"{', '.join(HUB_EDGE_ROLES)}.",
                )
            )
    return found


def _self_containment(edges: Sequence[Any], groups: Any, containers: Set[str]) -> list[Violation]:
    """Edges between a container and something already inside it.

    An edge naming a group says *this relation belongs to the whole of it* — a
    platform that watches the cluster rather than one pod of it. That reading
    only holds against something **outside** the container: an edge from a frame
    to a box within it would leave a border and arrive inside the same border,
    which is not a relation between two things but a line from a thing to part of
    itself. There is no geometry for it, and no sentence it draws.

    Refused by name rather than dropped, for the same reason an id that resolves
    to nothing is: the author meant something, and only they can say what.
    """
    parent: dict[str, str] = {}
    for group in groups if isinstance(groups, list) else ():
        if not isinstance(group, dict) or not isinstance(group.get("id"), str):
            continue
        members = group.get("members")
        if not isinstance(members, list):
            continue
        for member in members:
            # First claim wins. A member claimed twice is its own violation and
            # is reported by the group checks; walking either chain would answer
            # this question the same way.
            if isinstance(member, str) and member not in parent:
                parent[member] = group["id"]

    def encloses(container: str, identifier: str) -> bool:
        """Whether `container` is an ancestor of `identifier`, at any depth."""
        walked: set[str] = set()
        current = parent.get(identifier)
        while current is not None and current not in walked:
            if current == container:
                return True
            walked.add(current)
            current = parent.get(current)
        return False

    found: list[Violation] = []
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            continue
        source, target = edge.get("from"), edge.get("to")
        if not isinstance(source, str) or not isinstance(target, str):
            continue
        for end, container, inside in (("from", source, target), ("to", target, source)):
            if container in containers and encloses(container, inside):
                found.append(
                    Violation(
                        _pointer("edges", index, end),
                        f"{container!r} contains {inside!r}, so an edge between them would "
                        f"leave a border and arrive inside it. An edge naming a container is "
                        f"about the whole of it, which only says something against what is "
                        f"outside — draw it from a member instead, or point it elsewhere.",
                    )
                )
                break
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
    if kind in STATES_KINDS:
        return _states_document(document)
    if kind in SEQUENCE_KINDS:
        return _sequence_document(document)
    if kind in LANES_KINDS:
        return _lanes_document(document)
    if kind in ENTITIES_KINDS:
        return _entities_document(document)
    if kind in GANTT_KINDS:
        return _gantt_document(document)
    if kind in BOARD_KINDS:
        return _board_document(document)
    if kind in FISHBONE_KINDS:
        return _fishbone_document(document)
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
        rise=bool(document.get("rise", False)),
        theme=str(document.get("theme", "")),
        nodes=tuple(
            Node(
                id=entry["id"],
                text=entry["text"],
                role=entry.get("role", "step"),
                centre=bool(entry.get("centre", False)),
                note=entry.get("note", ""),
                actor=entry.get("actor", ""),
                status=entry.get("status", ""),
            )
            for entry in document.get("nodes", ())
        ),
        hub=_hub(document.get("hub")),
        edges=tuple(
            Edge(
                source=entry["from"],
                target=entry["to"],
                label=entry.get("label", ""),
                role=entry.get("role", "flow"),
                status=entry.get("status", ""),
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
        scale=tuple(document.get("scale", ())),
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
        root=str(document.get("root", "")),
        entries=_entries(document.get("entries", ())),
        order=str(document.get("sort", "given")),
        style=str(document.get("style", "icons")),
    )


def _lanes_document(document: Mapping[str, Any]) -> Document:
    """A swimlane diagram as the graph family reads it: a flow whose actors are lanes.

    The actor is moved to `Node.lane`, so the box is sized from its own text and
    the actor is drawn once, as its lane's heading, rather than in every box.
    """
    nodes = tuple(
        Node(
            id=entry["id"],
            text=entry["text"],
            role=entry.get("role", "step"),
            status=entry.get("status", ""),
            lane=entry["actor"],
        )
        for entry in document["nodes"]
    )
    return Document(
        kind=str(document["kind"]),
        version=DOCUMENT_VERSION,
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        nodes=nodes,
        edges=tuple(
            Edge(
                source=entry["from"],
                target=entry["to"],
                label=entry.get("label", ""),
                role=entry.get("role", "flow"),
                status=entry.get("status", ""),
            )
            for entry in document.get("edges", ())
        ),
        lanes=lane_order(document),
    )


def lane_order(document: Mapping[str, Any]) -> tuple[str, ...]:
    """The lanes of a `lanes` document, in order: as listed, or as first named."""
    listed = document.get("lanes")
    if isinstance(listed, list):
        return tuple(str(lane) for lane in listed)
    order: dict[str, None] = {}
    for node in _listed(document, "nodes"):
        if isinstance(node, dict) and isinstance(node.get("actor"), str):
            order.setdefault(node["actor"], None)
    return tuple(order)


def _states_document(document: Mapping[str, Any]) -> Document:
    """A state machine as the graph family reads it: states as nodes, transitions as edges.

    The transition's three parts are composed into the edge's label here, once,
    so the renderer never learns that a state machine has events.
    """
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        nodes=tuple(
            Node(id=entry["id"], text=entry["text"], role=entry.get("role", "step"))
            for entry in document["states"]
        ),
        initial=str(document["initial"]),
        final=tuple(document.get("final", ())),
        edges=tuple(
            Edge(
                source=entry["from"],
                target=entry["to"],
                label=transition_label(
                    entry.get("event", ""), entry.get("guard", ""), entry.get("action", "")
                ),
                role=entry.get("role", "flow"),
            )
            for entry in document.get("transitions", ())
        ),
        groups=tuple(
            Group(
                id=entry["id"],
                members=tuple(entry["members"]),
                text=entry["text"],
                initial=entry.get("initial", ""),
            )
            for entry in document.get("groups", ())
        ),
    )


def _sequence_document(document: Mapping[str, Any]) -> Document:
    """A sequence diagram: participants as nodes, and its own messages and fragments."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        participants=tuple(
            Node(id=entry["id"], text=entry["text"], role=entry.get("role", "step"))
            for entry in document["participants"]
        ),
        messages=tuple(
            Message(
                source=entry["from"],
                target=entry["to"],
                text=entry.get("text", ""),
                role=entry.get("role", "flow"),
                id=entry.get("id", ""),
                note=entry.get("note", ""),
            )
            for entry in document["messages"]
        ),
        fragments=tuple(
            Fragment(
                operator=entry["operator"],
                start=entry["from"],
                end=entry["to"],
                text=entry.get("text", ""),
                branches=tuple(
                    Branch(at=branch["at"], text=branch.get("text", ""))
                    for branch in entry.get("else", ())
                ),
            )
            for entry in document.get("fragments", ())
        ),
        groups=tuple(
            Group(id=entry["id"], members=tuple(entry["members"]), text=entry.get("text", ""))
            for entry in document.get("groups", ())
        ),
    )


def _entities_document(document: Mapping[str, Any]) -> Document:
    """An entity diagram: its boxes with their rows, and relations with their ends."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        entities=tuple(
            Entity(
                id=entry["id"],
                text=entry["text"],
                role=entry.get("role", "step"),
                tag=entry.get("tag", ""),
                fields=tuple(
                    EntityField(
                        text=field["text"],
                        type=field.get("type", ""),
                        key=field.get("key", ""),
                        id=field.get("id", ""),
                    )
                    for field in entry.get("fields", ())
                ),
                operations=tuple(entry.get("operations", ())),
            )
            for entry in document["entities"]
        ),
        relations=tuple(
            Relation(
                source=entry["from"],
                target=entry["to"],
                label=entry.get("label", ""),
                role=entry.get("role", "link"),
                source_field=entry.get("from_field", ""),
                target_field=entry.get("to_field", ""),
                source_end=entry.get("from_end", ""),
                target_end=entry.get("to_end", ""),
            )
            for entry in document.get("edges", ())
        ),
    )


def _gantt_document(document: Mapping[str, Any]) -> Document:
    """A plan: its axis, its tasks in order, phases, dependencies and marks."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        axes=(_axis(document["axis"]),),
        tasks=tuple(
            Task(
                id=entry["id"],
                text=entry["text"],
                start=float(entry.get("start", 0.0)),
                end=float(entry.get("end", 0.0)),
                at=_optional_number(entry.get("at")),
                role=entry.get("role", "step"),
                actor=entry.get("actor", ""),
            )
            for entry in document["tasks"]
        ),
        groups=tuple(
            Group(id=entry["id"], members=tuple(entry["members"]), text=entry.get("text", ""))
            for entry in document.get("groups", ())
        ),
        edges=tuple(
            Edge(source=entry["from"], target=entry["to"], role=entry.get("role", "flow"))
            for entry in document.get("edges", ())
        ),
        marks=tuple(
            Mark(text=entry["text"], at=float(entry["at"])) for entry in document.get("marks", ())
        ),
    )


def _board_document(document: Mapping[str, Any]) -> Document:
    """A board: its columns, its rows if any, its cut, and its cards in order."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        board_columns=tuple(
            BoardColumn(
                id=entry["id"],
                text=entry["text"],
                limit=entry.get("limit"),
                role=entry.get("role", "step"),
            )
            for entry in document["columns"]
        ),
        slices=tuple(
            Slice(id=entry["id"], text=entry["text"]) for entry in document.get("rows", ())
        ),
        cut=str(document.get("cut", "")),
        cards=tuple(
            Card(
                text=entry["text"],
                column=entry["column"],
                row=entry.get("row", ""),
                role=entry.get("role", "step"),
                actor=entry.get("actor", ""),
                note=entry.get("note", ""),
            )
            for entry in document["cards"]
        ),
    )


def _fishbone_document(document: Mapping[str, Any]) -> Document:
    """A fishbone: its effect and its categories, each with its causes, in order."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        effect=str(document["effect"]["text"]),
        categories=tuple(
            Category(
                text=entry["text"],
                causes=tuple(
                    Cause(text=cause["text"], role=cause.get("role", "step"))
                    for cause in entry["causes"]
                ),
            )
            for entry in document["categories"]
        ),
    )


def _hub(entry: Mapping[str, Any] | None) -> Node | None:
    if entry is None:
        return None
    return Node(id=entry["id"], text=entry["text"], role=entry.get("role", "step"))


def _entries(entries: Sequence[Mapping[str, Any]]) -> tuple[Entry, ...]:
    return tuple(
        Entry(
            path=entry["path"],
            note=entry.get("note", ""),
            link=entry.get("link", ""),
            status=entry.get("status", ""),
        )
        for entry in entries
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
    # Grouped by the full field tuple, not just names: `quadrant` and `scatter`
    # both take `axes` + `positions`, but with different descriptions for what
    # those mean, and merging on name alone silently dropped one kind's prose.
    grouped: dict[tuple[FieldSpec, ...], list[str]] = {}
    for kind in KINDS:
        grouped.setdefault(payload_for(kind), []).append(kind)

    variants = []
    for specs_for_kind, kinds in grouped.items():
        specs = list(COMMON_FIELDS) + list(specs_for_kind)
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
            "beyond JSON Schema and are enforced by `drawspec validate`, as are the "
            "readability budget (the most entries each kind may hold) and the cap of "
            f"{EMPHASIS_CAP} elements with the 'emphasis' role (docs/format.md)."
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
    "BOARD_CELL_MAX",
    "BOARD_KINDS",
    "CARDINALITIES",
    "CAUSE_ROLES",
    "CHART_KINDS",
    "COMMON_FIELDS",
    "CONTAINER_KINDS",
    "DOCUMENT_VERSION",
    "ENTITIES_KINDS",
    "ENTITY_EDGE_ROLES",
    "ENTITY_ROLES",
    "FIELD_KEYS",
    "FISHBONE_CATEGORY_MAX",
    "FISHBONE_CAUSE_MAX",
    "FISHBONE_KINDS",
    "FRAGMENT_OPERATORS",
    "GRAPH_EDGE_ROLES",
    "GRAPH_KINDS",
    "GRID_KINDS",
    "HIERARCHY_ROLES",
    "HUB_EDGE_ROLES",
    "HUB_MINIMUM_NODES",
    "KINDS",
    "LANES_KINDS",
    "LANES_MAX",
    "MESSAGE_ROLES",
    "OBJECTS",
    "PARTICIPANT_ROLES",
    "REJECTED_FIELDS",
    "SCHEMA_FILENAME",
    "SCHEMA_ID",
    "SEQUENCE_KINDS",
    "SHAPE_KINDS",
    "STATES_KINDS",
    "STATE_ROLES",
    "TRANSITION_ROLES",
    "Axis",
    "Band",
    "BoardColumn",
    "Branch",
    "Card",
    "Category",
    "Cause",
    "Cell",
    "Curve",
    "Document",
    "Edge",
    "Entity",
    "EntityField",
    "FieldSpec",
    "Fragment",
    "Group",
    "Item",
    "Message",
    "Node",
    "Position",
    "Relation",
    "Series",
    "Slice",
    "Violation",
    "Waypoint",
    "build_schema",
    "fields_for",
    "lane_order",
    "load_document",
    "parse_document",
    "payload_for",
    "published_schema_path",
    "schema_json",
    "transition_label",
    "validate_document",
]

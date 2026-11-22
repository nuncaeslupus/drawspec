"""The field tables: the single description the validator and the JSON Schema both read."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from drawspec.filetree import ORDERS, STATUSES
from drawspec.schema._constants import (
    ARGUMENT_KINDS,
    ARGUMENT_ROLES,
    ARGUMENT_STANCES,
    AUTOMATON_KINDS,
    BARMODEL_KINDS,
    BARMODEL_PART_ROLES,
    BOARD_COLUMN_ROLES,
    BOARD_KINDS,
    BRACKET_LEAVES_MAX,
    BRACKET_ROOTS,
    CARD_ROLES,
    CARDINALITIES,
    CAUSE_ROLES,
    CLASSES_MAX,
    CLOCK_KINDS,
    CLOCK_NUMERALS,
    CLOCK_READOUTS,
    DEPENDENCY_ROLES,
    ENTITIES_KINDS,
    ENTITY_EDGE_ROLES,
    ENTITY_ROLES,
    FAMILYTREE_GENDERS,
    FAMILYTREE_KINDS,
    FAMILYTREE_PREGNANCIES,
    FAMILYTREE_ROLES,
    FAMILYTREE_SEXES,
    FAMILYTREE_STATUSES,
    FAMILYTREE_ZYGOSITIES,
    FIELD_KEYS,
    FILES_KINDS,
    FILES_STYLES,
    FISHBONE_KINDS,
    FRAGMENT_OPERATORS,
    GANTT_KINDS,
    GITGRAPH_DIRECTIONS,
    GITGRAPH_KINDS,
    GITGRAPH_ROLES,
    GRAPH_EDGE_ROLES,
    GRAPH_KINDS,
    HUB_EDGE_ROLES,
    HUB_MINIMUM_NODES,
    JOURNEY_KINDS,
    JOURNEY_STAGE_ROLES,
    KINDS,
    LANE_NODE_ROLES,
    LANES_KINDS,
    LANES_MAX,
    LANES_PHASES_MAX,
    LOOP_TYPES,
    MARKS,
    MESSAGE_ROLES,
    METER_BAND_MIN,
    METER_KINDS,
    METER_ROLES,
    METER_STYLES,
    MINDMAP_KINDS,
    MINDMAP_ROLES,
    NETWORK_HOST_ROLES,
    NETWORK_KINDS,
    NEURALNET_BRANCH_MAX,
    NEURALNET_DIRECTIONS,
    NEURALNET_KINDS,
    NEURALNET_LABEL_MAX,
    NEURALNET_LAYER_MAX,
    NEURALNET_NEURONS_SHOWN,
    NEURALNET_STYLES,
    NEURALNET_TOWER_MAX,
    NUMBERLINE_KINDS,
    NUMBERLINE_ROLES,
    PACKET_KINDS,
    PACKET_NUMBERINGS,
    PACKET_ROLES,
    PARTICIPANT_ROLES,
    PERT_KINDS,
    PIE_KINDS,
    PIE_ROLES,
    PLAIN_NODE_ROLES,
    POLARITIES,
    RAG_KINDS,
    RAG_TRENDS,
    RAG_VALUES,
    RAILROAD_KINDS,
    REGION_ROLES,
    SANKEY_FLOW_ROLES,
    SANKEY_KINDS,
    SANKEY_NODE_ROLES,
    SEQUENCE_KINDS,
    STATE_ROLES,
    STATES_KINDS,
    SUNBURST_KINDS,
    TAG_MAX,
    TASK_ROLES,
    TIMING_KINDS,
    TIMING_LANES,
    TRANSITION_ROLES,
    TREE_STYLES,
    TREEMAP_KINDS,
    TREEMAP_PART_ROLES,
    USECASE_EDGE_ROLES,
    USECASE_KINDS,
    VENN_KINDS,
    VENN_SET_ROLES,
    WARDLEY_EVOLUTION,
    WARDLEY_KINDS,
    WATERFALL_KINDS,
    WATERFALL_ROLES,
)
from drawspec.theme import NODE_ROLES, RAMP_STEPS


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


#: A Wardley map's anchor or component name: one line, set beside its dot.
_WARDLEY_NAME: Final = FieldSpec(
    "text",
    "string",
    required=True,
    description=(
        "The name, on one line, set beside its dot (an anchor's in bold). May carry inline "
        "spans — `code` and **bold** — because those are semantic, not typographic. A "
        "newline is refused: put the detail in a numbered `note`."
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
            "class",
            "string",
            description=(
                "Which of the document's `classes` this box belongs to — an author-chosen "
                "grouping such as *external system* or *owned by the payments team*, drawn "
                "as that class's faint fill and named in a key under the drawing. Must be "
                "the `id` of a declared class. Not on a `note` or a `group`, and not with "
                "`status` (both would mark the box). **Only a `flow`, a `tree` or `lanes`.**"
            ),
        ),
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
        FieldSpec(
            "polarity",
            "string",
            enum=POLARITIES,
            description=(
                "A causal link's sign: more of the source means more (`+`) or less (`-`) of "
                "the target, written as the edge's label (`s`/`o` under a theme that says "
                "so). Every `flow` or `strong` edge of the document has one, or none does. "
                "**Only a `flow`.**"
            ),
        ),
        FieldSpec(
            "delay",
            "boolean",
            description=(
                "The effect takes time: drawn as the double stroke across the shaft. Needs "
                "`polarity`. **Only a `flow`.**"
            ),
        ),
    ),
    "loop": (
        _text(required=True),
        FieldSpec(
            "nodes",
            "array",
            required=True,
            item_kind="string",
            min_items=2,
            description=(
                "The loop's variables in the order it runs: each joined to the next, and "
                "the last back to the first, by a signed edge in that direction."
            ),
        ),
        FieldSpec(
            "type",
            "string",
            enum=LOOP_TYPES,
            description=(
                "Optional, and checked: an even number of `-` links is `reinforcing`, an "
                "odd number `balancing`. Drawn as R or B, numbered in the order written."
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
        FieldSpec(
            "class",
            "string",
            description=(
                "Which of the document's `classes` this box belongs to — an author-chosen "
                "grouping such as *external system* or *owned by the payments team*, drawn "
                "as that class's faint fill and named in a key under the drawing. Must be "
                "the `id` of a declared class. Not on a `note` or a `group`, and not with "
                "`status` (both would mark the box). **Only a `flow`, a `tree` or `lanes`.**"
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
        _role(PLAIN_NODE_ROLES, "step"),
    ),
    "state": (
        FieldSpec(
            "id",
            "string",
            required=True,
            description="Unique within the document, among the states and the groups.",
        ),
        FieldSpec(
            "text",
            "string",
            description=(
                "The state's name. A newline makes it a lead and a detail, as on any box. "
                "Required on every state but a `fork` or `join` bar, which has no words."
            ),
        ),
        FieldSpec(
            "role",
            "string",
            enum=STATE_ROLES,
            description=(
                "The semantic role, which the theme resolves to an appearance. Defaults "
                "to 'step'. `fork` and `join` make this state a bar: a fork has one "
                "transition in and two or more out, each into a different region of one "
                "composite; a join is the reverse. A bar has no `text`, and the "
                "transitions out of a fork or into a join carry no `event` or `guard`."
            ),
        ),
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
            item_kind="string",
            min_items=1,
            description=(
                "The states (or groups) inside this composite state. A composite lists "
                "its `members` or its `regions`, not both."
            ),
        ),
        FieldSpec(
            "initial",
            "string",
            description=(
                "The member this composite is entered at, drawn as a dot inside the "
                "frame. Required when a transition, or the machine's own `initial`, "
                "names the group. With `regions`, each region names its own instead."
            ),
        ),
        FieldSpec(
            "regions",
            "array",
            item_ref="state_region",
            min_items=2,
            description=(
                "Orthogonal regions: parts of this composite that are all current at "
                "once, drawn side by side (or stacked) and divided by dashed lines. Each "
                "region lists its own members and its own `initial` — unless every way "
                "into the composite is a `fork` with an arrow into that region, which "
                "says where it starts — and entering the composite enters every region "
                "there. A transition may not run between two regions of one composite. "
                "In place of `members`."
            ),
        ),
    ),
    "state_region": (
        FieldSpec(
            "members",
            "array",
            required=True,
            item_kind="string",
            min_items=1,
            description=(
                "The states (or groups) in this region. A state is in one region; each "
                "region is a machine of its own, running alongside the others."
            ),
        ),
        FieldSpec(
            "initial",
            "string",
            description=(
                "The member this region starts in when its composite is entered, drawn "
                "as a dot inside the region. Required unless every way into the "
                "composite is a `fork` with an arrow into this region, which says "
                "where it starts instead."
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
            "centre",
            "boolean",
            description=(
                "Whether this entity is the one the rest are arranged around: a star "
                "schema's fact table, its dimensions round it — the first above, the rest "
                "clockwise in the order written. One entity per document may say so, and "
                "not in a class hierarchy, which is drawn general above specific."
            ),
        ),
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
            "done",
            "number",
            description=(
                "How much of the task is complete, 0 to 100: drawn as a solid band inside "
                "the bar from its start, MS Project's progress line. Not on a milestone."
            ),
        ),
        FieldSpec(
            "events",
            "array",
            item_ref="task-event",
            description=(
                "Moments on the task's own row — a delivery, a release, a review — each a "
                "diamond on the bar where it falls, its words under the bar. Unlike a "
                "milestone task they take no row of their own, so several fall on one "
                "row. Within the task's `start` to `end`; not on a milestone."
            ),
        ),
        FieldSpec(
            "iterations",
            "array",
            item_ref="iteration",
            description=(
                "Cycles the work goes round: each an arc over the bar from an "
                "iteration's `end` back to its `start`, the return a life cycle draws. "
                "Within the task's `start` to `end`, in order and not overlapping; not on "
                "a milestone."
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
    "task-event": (
        FieldSpec(
            "at",
            "number",
            required=True,
            description="Where on the axis, inside the task's interval.",
        ),
        _text(required=False),
    ),
    "iteration": (
        FieldSpec(
            "start",
            "number",
            required=True,
            description="Where the cycle begins on the axis: the arc's head lands here.",
        ),
        FieldSpec(
            "end",
            "number",
            required=True,
            description="Where it ends and turns back, after `start`: the arc leaves from here.",
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
    "venn-set": (
        FieldSpec(
            "id",
            "string",
            required=True,
            description="Unique among the sets; what a region's `in` names.",
        ),
        _text(),
        FieldSpec(
            "role",
            "string",
            enum=VENN_SET_ROLES,
            description=(
                "`step` (the default) or `emphasis` (the set the diagram is about), drawn as "
                "a heavier outline."
            ),
        ),
    ),
    "region": (
        FieldSpec(
            "in",
            "array",
            required=True,
            item_kind="string",
            min_items=1,
            description=(
                "The ids of exactly the sets this region is in, and no others: "
                '`["gdpr"]` is what only that set holds, `["gdpr", "ens"]` what the two '
                "share. drawspec knows where that region is."
            ),
        ),
        _text(),
        FieldSpec(
            "role",
            "string",
            enum=REGION_ROLES,
            description=(
                "`step` (the default) or `emphasis` (the region the diagram is about): its "
                "words bold and the region filled with the theme's first mark fill."
            ),
        ),
    ),
    "journey-row": (
        FieldSpec(
            "id",
            "string",
            required=True,
            description="Unique among the rows; what a stage's `details` name in `row`.",
        ),
        _text(),
    ),
    "journey-stage": (
        _text(),
        FieldSpec(
            "feeling",
            "string",
            required=True,
            missing=(
                "'feeling' is required: the feeling line is the reason to draw a journey, "
                "and it passes through every stage. A stage nobody can name a feeling for "
                "means the diagram is a `flow` or a `timeline`."
            ),
            description=(
                "One of the journey's `feelings`, by name: the level this stage's point is "
                "drawn at. A name, never a score."
            ),
        ),
        FieldSpec(
            "role",
            "string",
            enum=JOURNEY_STAGE_ROLES,
            description=(
                "`step` (the default) or `emphasis` (the stage the map is about, usually the "
                "trough): its column framed, its point drawn larger and solid."
            ),
        ),
        FieldSpec(
            "details",
            "array",
            item_ref="detail",
            description=(
                "What this stage holds in each detail row, a `{row, text}` per row it fills. "
                "A row it does not name is drawn as an empty cell."
            ),
        ),
    ),
    "detail": (
        FieldSpec(
            "row",
            "string",
            required=True,
            description="The id of one of the journey's `rows`, at most once per stage.",
        ),
        _text(),
    ),
    "treemap-part": (
        _text(),
        FieldSpec(
            "amount",
            "number",
            required=True,
            exclusive_minimum=0,
            description=(
                "How much of the total this part is, in the treemap's `unit`: its area is in "
                "proportion. A number you already know, more than 0."
            ),
        ),
        FieldSpec(
            "group",
            "string",
            description=(
                "The id of one of the treemap's `groups`: the part is laid out with the "
                "group's other parts inside its captioned frame. Omit it to sit beside the "
                "groups."
            ),
        ),
        FieldSpec(
            "role",
            "string",
            enum=TREEMAP_PART_ROLES,
            description=(
                "`step` (the default), `emphasis` (the part the diagram is about — not "
                "automatically the largest: a heavier outline, its words bold) or `note` (the "
                "remainder, `Everything else`: a light dashed outline, laid out last)."
            ),
        ),
    ),
    "sankey-node": (
        FieldSpec(
            "id",
            "string",
            required=True,
            description="Unique among the nodes; what a flow's `from` and `to` name.",
        ),
        _text(),
        FieldSpec(
            "role",
            "string",
            enum=SANKEY_NODE_ROLES,
            description=(
                "`step` (the default), `emphasis` (the node the diagram is about: its bar "
                "outlined heavier, its words bold) or `note` (the remainder — `Lost`, "
                "`Reserved, idle` — drawn lighter, with the bands that reach it)."
            ),
        ),
    ),
    "sankey-flow": (
        FieldSpec(
            "from",
            "string",
            required=True,
            description="The id of the node the amount leaves.",
        ),
        FieldSpec(
            "to",
            "string",
            required=True,
            description="The id of the node the amount reaches.",
        ),
        FieldSpec(
            "amount",
            "number",
            required=True,
            exclusive_minimum=0,
            description=(
                "How much flows, in the sankey's `unit`: the band's thickness is in proportion. "
                "A number you already know, more than 0."
            ),
        ),
        FieldSpec(
            "role",
            "string",
            enum=SANKEY_FLOW_ROLES,
            description=(
                "`flow` (the default band) or `strong` (the path the diagram is about, drawn "
                "darker)."
            ),
        ),
    ),
    "axis-numberline": (
        FieldSpec(
            "min",
            "number",
            required=True,
            description="Where the scale starts, at the left arrowhead's side.",
        ),
        FieldSpec(
            "max",
            "number",
            required=True,
            description="Where the scale ends: more than `min`.",
        ),
        FieldSpec(
            "step",
            "number",
            exclusive_minimum=0,
            description=(
                "The distance between two ticks, each labelled with its number. Omit it for a "
                "step a reader can count in, chosen from the range."
            ),
        ),
        FieldSpec(
            "label",
            "string",
            description="What the numbers measure, centred under them: `pH`, `Temperature`.",
        ),
        FieldSpec(
            "unit",
            "string",
            description="What the numbers are in, written after the label: `°C`, `cm`.",
        ),
        FieldSpec(
            "ends",
            "array",
            item_kind="string",
            min_items=2,
            description=(
                "Two words for the low and the high end — `past` and `future`, `fully remote` "
                "and `fully on site` — written under the arrowheads, for a scale that is named "
                "rather than measured. No numbers are drawn: only the order and the gaps "
                "count, so not with `step` or `unit`."
            ),
        ),
    ),
    "numberline-point": (
        FieldSpec(
            "at",
            "number",
            required=True,
            description="Where the dot sits on the axis: a number between `min` and `max`.",
        ),
        _text(required=False),
        FieldSpec(
            "open",
            "boolean",
            description=(
                "Whether the dot is hollow: the value itself is excluded — `x ≠ 3`, a hole. "
                "Defaults to false, a filled dot."
            ),
        ),
        FieldSpec(
            "role",
            "string",
            enum=NUMBERLINE_ROLES,
            description=(
                "`step` (the default), `emphasis` (the point the line is about: a larger dot, "
                "its words bold) or `note` (context: a smaller dot)."
            ),
        ),
    ),
    "numberline-range": (
        FieldSpec(
            "from",
            "number",
            description=(
                "Where the range starts. Omit it for a range that runs on below `min`, drawn as "
                "an arrow off the left end."
            ),
        ),
        FieldSpec(
            "to",
            "number",
            description=(
                "Where the range ends: more than `from`. Omit it for a range that runs on "
                "above `max`, drawn as an arrow off the right end."
            ),
        ),
        FieldSpec(
            "from_open",
            "boolean",
            description=(
                "Whether `from` is excluded — `x > 1` rather than `x ≥ 1`. Defaults to false. "
                "The theme's `[numberline] ends` draws it as a hollow dot or a parenthesis."
            ),
        ),
        FieldSpec(
            "to_open",
            "boolean",
            description=(
                "Whether `to` is excluded — `x < 4` rather than `x ≤ 4`. Defaults to false."
            ),
        ),
        _text(required=False),
        FieldSpec(
            "role",
            "string",
            enum=NUMBERLINE_ROLES,
            description=(
                "`step` (the default, a heavy line), `emphasis` (the range the line is about — "
                "the solution set: a heavier bar, its words bold) or `note` (context: dashed)."
            ),
        ),
    ),
    "barmodel-bar": (
        FieldSpec(
            "id",
            "string",
            description=(
                "What a brace's `over` names, for a brace over the whole bar. Unique among "
                "the bars and the parts."
            ),
        ),
        _text(required=False),
        FieldSpec(
            "parts",
            "array",
            required=True,
            item_ref="barmodel-part",
            min_items=1,
            description=(
                "The bar's parts, left to right, each as long as its `value` or its `units` "
                "say — in one scale for every bar."
            ),
        ),
    ),
    "barmodel-part": (
        FieldSpec(
            "id",
            "string",
            description="What a brace's `over` names. Unique among the bars and the parts.",
        ),
        FieldSpec(
            "amount",
            "number",
            exclusive_minimum=0,
            description=(
                "How much the part is, more than 0: its length is in proportion, and its "
                "words default to the number. Give it even for the unknown — the `?` is "
                "its `text`."
            ),
        ),
        FieldSpec(
            "units",
            "integer",
            exclusive_minimum=0,
            description=(
                "How many equal boxes the part is, each one unit long: groups to multiply, "
                "the shares of a ratio, the fifths of a fraction. Not with `amount`, and not "
                "in a document whose parts have amounts."
            ),
        ),
        _text(required=False),
        FieldSpec(
            "role",
            "string",
            enum=BARMODEL_PART_ROLES,
            description=(
                "`step` (the default), `emphasis` (the part the problem asks about: bold "
                "words, filled) or `note` (a part that is not there — the difference a "
                "shorter bar lacks: dashed)."
            ),
        ),
    ),
    "barmodel-brace": (
        FieldSpec(
            "over",
            "array",
            required=True,
            item_kind="string",
            min_items=1,
            description=(
                "What the brace spans: the ids of side-by-side parts of one bar, drawn over "
                "it (under it, for the last of several bars), or of whole bars — one bar "
                "the same way, several consecutive bars with an upright brace at their right."
            ),
        ),
        FieldSpec(
            "amount",
            "number",
            exclusive_minimum=0,
            description=(
                "What the stretch adds up to. Checked: the parts' amounts must sum to it, "
                "and with units every brace must make one unit worth the same. Written "
                "unless `text` is given."
            ),
        ),
        _text(required=False),
    ),
    "waterfall-axis": (
        FieldSpec(
            "label",
            "string",
            required=True,
            description=(
                "What the numbers are, with their unit — `Borrowing, £ billion`. Set beside "
                "the vertical axis; required, as on every chart."
            ),
        ),
    ),
    "waterfall-bar": (
        _text(),
        FieldSpec(
            "total",
            "number",
            description=(
                "A total: the bar stands on zero and runs to it. The first bar is one and so "
                "is the last; one in between is a subtotal. Every total after the first is "
                "checked: it must be the running sum. Not with `amount`."
            ),
        ),
        FieldSpec(
            "amount",
            "number",
            description=(
                "A signed step, not 0: the bar floats from the running sum to the running "
                "sum plus this, and is written `+6.1` or `\N{MINUS SIGN}9.4`. Not with `total`."
            ),
        ),
        FieldSpec(
            "role",
            "string",
            enum=WATERFALL_ROLES,
            description=(
                "`step` (the default) or `emphasis` (the bar the chart is about: a heavier "
                "outline, its number bold)."
            ),
        ),
    ),
    "pie-part": (
        _text(),
        FieldSpec(
            "amount",
            "number",
            required=True,
            exclusive_minimum=0,
            description=(
                "How much of the total this part is, more than 0, in the pie's `unit`: a "
                'count, a sum, or with `unit: "%"` a percentage. Its angle is its share of '
                "the sum of the amounts, computed — never written."
            ),
        ),
        FieldSpec(
            "role",
            "string",
            enum=PIE_ROLES,
            description=(
                "`step` (the default), `emphasis` (the part the chart is about: a heavier "
                "outline, its words bold) or `note` (the remainder, `Everything else`: "
                "unfilled and dashed, drawn last). At most one `note`."
            ),
        ),
    ),
    "argument-point": (
        FieldSpec(
            "id",
            "string",
            required=True,
            description="Unique within the document, and not `claim`: what `on` and `with` name.",
        ),
        _text(),
        FieldSpec(
            "on",
            "string",
            required=True,
            description=(
                "The box this point bears on: `claim`, or another point's id. The points "
                "hang below it, in the order written."
            ),
        ),
        FieldSpec(
            "stance",
            "string",
            required=True,
            enum=ARGUMENT_STANCES,
            missing=(
                "'stance' is required: a point is `for` or `against` the box it is `on`. A "
                "remark that is neither is not part of the argument; put it in the `caption`."
            ),
            description=(
                "`for` (a reason, drawn plain, tagged *because*) or `against` (an objection, "
                "hatched, tagged *but*) the box it is `on`. A rebuttal is an `against` on an "
                "`against`."
            ),
        ),
        FieldSpec(
            "with",
            "array",
            item_kind="string",
            min_items=1,
            description=(
                "Co-premises: the ids of points with the same `on` and `stance` that support "
                "it only together. Written once, on any member; the group is every point "
                "joined this way, at most 4, drawn side by side under one bracket with one "
                "connector."
            ),
        ),
        FieldSpec(
            "role",
            "string",
            enum=ARGUMENT_ROLES,
            description=(
                "`step` (the default), `emphasis` (the decisive point: heavy outline and "
                "connector, bold words) or `note` (evidence or a source rather than a reason: "
                "the note type, unboxed, on a dashed connector)."
            ),
        ),
    ),
    "familytree-person": (
        FieldSpec(
            "id",
            "string",
            required=True,
            description="Unique within the document: what `couples` name.",
        ),
        FieldSpec(
            "sex",
            "string",
            required=True,
            enum=FAMILYTREE_SEXES,
            missing=(
                "'sex' is required: it is the symbol, a square (`male`), a circle (`female`) "
                "or a diamond (`unknown`). Write `unknown` when it is not known or not said."
            ),
            description=(
                "The symbol: a square (`male`), a circle (`female`) or a diamond (`unknown`), "
                "as the standard nomenclature draws them. With `gender`, the symbol shows the "
                "gender instead and this is noted under it (`AMAB`, `AFAB`) when the two differ."
            ),
        ),
        FieldSpec(
            "gender",
            "string",
            enum=FAMILYTREE_GENDERS,
            description=(
                "Gender identity, per the 2022 revision of the standard: the symbol becomes "
                "a square (`man`), a circle (`woman`) or a diamond (`nonbinary`), and `sex` is "
                "the sex assigned at birth, written under it when it differs. Leave it out "
                "and the symbol follows `sex`."
            ),
        ),
        FieldSpec(
            "text",
            "string",
            description=(
                "The name, or an age or a test result, under the symbol and its number. A "
                "newline makes it a lead and a detail, as anywhere: a name over the years."
            ),
        ),
        FieldSpec(
            "status",
            "string",
            enum=FAMILYTREE_STATUSES,
            description=(
                "The one trait the tree tracks: `affected` (the symbol filled), `carrier` (the "
                "theme's carrier mark: a dot in the middle, or the left half filled) or "
                "`unaffected` (the default: empty). Told apart without colour; a key under "
                "the drawing names the ones used."
            ),
        ),
        FieldSpec(
            "deceased",
            "boolean",
            description="A diagonal stroke through the symbol. An age or year goes in `text`.",
        ),
        FieldSpec(
            "proband",
            "boolean",
            description=(
                "The affected person through whom the family came to attention: an arrow at "
                "the lower left with a `P`. One per tree."
            ),
        ),
        FieldSpec(
            "consultand",
            "boolean",
            description=(
                "The person asking for advice or testing: the arrow without the `P`. May be "
                "the proband too."
            ),
        ),
        FieldSpec(
            "adopted",
            "boolean",
            description=(
                "Adopted into the couple whose `children` list them: brackets round the "
                "symbol and a dashed line down from the sibship line. A child is listed "
                "once, in the couple that raised them."
            ),
        ),
        FieldSpec(
            "pregnancy",
            "string",
            enum=FAMILYTREE_PREGNANCIES,
            description=(
                "`ongoing`: a `P` in the symbol (the weeks go in `text`); `loss`: a small "
                "triangle in place of the symbol, shaded when `affected`. Either is a child "
                "only: no partners."
            ),
        ),
        FieldSpec(
            "role",
            "string",
            enum=FAMILYTREE_ROLES,
            description=(
                "`step` (the default) or `emphasis`: the person the figure is about when "
                "there is no proband — a heavier symbol and a bold name."
            ),
        ),
    ),
    "familytree-couple": (
        FieldSpec(
            "between",
            "array",
            required=True,
            item_kind="string",
            min_items=2,
            description=(
                "The two partners' ids, in either order: drawspec puts them side by side, "
                "joined by the partner line. A person's couples are their partners in the "
                "order written — marriage order — at most 6."
            ),
        ),
        FieldSpec(
            "children",
            "array",
            item_kind="string",
            description=(
                "Their children's ids, in birth order: left to right under the sibship line. "
                "Leave it out for a couple with none."
            ),
        ),
        FieldSpec(
            "twins",
            "array",
            item_ref="familytree-twins",
            description=(
                "Children of one birth, each set written next to each other in `children`."
            ),
        ),
        FieldSpec(
            "separated",
            "boolean",
            description="The relationship has ended: two short strokes across the partner line.",
        ),
        FieldSpec(
            "consanguineous",
            "boolean",
            description="The partners are related by blood: a double partner line.",
        ),
    ),
    "meter-meter": (
        FieldSpec(
            "text",
            "string",
            required=True,
            description=(
                "The meter's name. A second line after a newline is its caption, drawn plain "
                "under the name: what the reading is of — `This year's milestones only`."
            ),
        ),
        FieldSpec(
            "amount",
            "number",
            required=True,
            description=(
                "The reading, on the scale from `min` to `max`. Written with its `unit` in the "
                "readout; never as a percentage the author worked out."
            ),
        ),
        FieldSpec(
            "max",
            "number",
            required=True,
            description=(
                "The end of the scale: a thermometer's goal, a progress bar's whole, a dial's "
                "right-hand end."
            ),
        ),
        FieldSpec(
            "min",
            "number",
            description=(
                "Where the scale starts, on a `dial` only (0 by default): a needle reads a "
                "position, so it may start anywhere. A bar's length is its amount, so a bar, a "
                "bullet and a thermometer start at 0."
            ),
        ),
        FieldSpec(
            "unit",
            "string",
            description=(
                "What the numbers are in: `%`, a currency sign (`£`, `$`, `€`, `¥`, written "
                "before the number) or a word (`tasks`, after it)."
            ),
        ),
        FieldSpec(
            "target",
            "number",
            description=(
                "A mark on the scale — the plan, a stage of an appeal — drawn across the "
                "track and written in the readout. Inside the scale."
            ),
        ),
        FieldSpec(
            "bands",
            "array",
            item_ref="meter-band",
            min_items=METER_BAND_MIN,
            description=(
                "Named stretches of the scale, rising: each runs from the end of the one "
                "before (or `min`) to its own `to`, and the last ends at `max`. Required on a "
                "`bullet`, optional on a `dial`, refused on the others. Drawn in tones of the "
                "page's ink with their words on them, so a band is never told by colour alone."
            ),
        ),
        FieldSpec(
            "role",
            "string",
            enum=METER_ROLES,
            description=(
                "`step` (the default) or `emphasis` (the meter the panel is about: its name "
                "and reading bold)."
            ),
        ),
    ),
    "clock-face": (
        FieldSpec(
            "time",
            "string",
            description=(
                "The time the hands show, `H:MM` or `HH:MM` from `0:00` to `23:59` — `15:40` "
                "for twenty to four in the afternoon. No seconds, no date. Leave it out for a "
                "face with no hands, to draw them on."
            ),
        ),
        FieldSpec(
            "text",
            "string",
            description=("A name or a prompt under the face: `Home time`, `Draw half past seven`."),
        ),
        FieldSpec(
            "since",
            "string",
            description=(
                "An earlier time, `H:MM`, up to 12 hours before `time`: the face shades what "
                "has passed since it, and the readout says how long."
            ),
        ),
    ),
    "rag-row": (
        FieldSpec(
            "text",
            "string",
            required=True,
            description=(
                "The workstream or risk. A second line after a newline is a caption under it, "
                "at the label size: an owner, a reference."
            ),
        ),
        FieldSpec(
            "rag",
            "string",
            required=True,
            enum=RAG_VALUES,
            description=(
                "The rating: `red`, `amber` or `green`. Drawn as the theme's word and shape for "
                "it (and its colour, when the theme has one), so it is never told by colour "
                "alone."
            ),
        ),
        FieldSpec(
            "trend",
            "string",
            enum=RAG_TRENDS,
            description=(
                "The direction of travel since the last report: `better`, `same` or `worse`. "
                "Drawn as an arrow (up, across, down) with the theme's word beside it."
            ),
        ),
        FieldSpec(
            "note",
            "string",
            description=(
                "Why: a sentence or two of commentary, wrapped in the last column. "
                "`**bold**` for a decision asked for."
            ),
        ),
    ),
    "meter-band": (
        FieldSpec(
            "text",
            "string",
            required=True,
            description=(
                "The band's name, written on it: `Good`, `Strained`, or `Green` when that is "
                "the word the reader is taught. One or two short words."
            ),
        ),
        FieldSpec(
            "to",
            "number",
            required=True,
            description="Where the band ends; it starts where the band before ends.",
        ),
    ),
    "familytree-twins": (
        FieldSpec(
            "of",
            "array",
            required=True,
            item_kind="string",
            min_items=2,
            description=(
                "Two or three of the couple's children, next to each other in `children`: "
                "drawn from one point on the sibship line."
            ),
        ),
        FieldSpec(
            "zygosity",
            "string",
            required=True,
            enum=FAMILYTREE_ZYGOSITIES,
            missing=(
                "'zygosity' is required: `monozygotic` (identical: a bar joins their lines), "
                "`dizygotic` (fraternal) or `unknown` (a `?` between them)."
            ),
            description=(
                "`monozygotic` (identical: a bar joins their lines), `dizygotic` (fraternal) "
                "or `unknown` (a `?` between them)."
            ),
        ),
    ),
    "mindmap-branch": (
        _text(),
        FieldSpec(
            "role",
            "string",
            enum=MINDMAP_ROLES,
            description=(
                "`step` (the default), `emphasis` (the branch the map is about: bold, its "
                "line heavy all the way from the centre; at most two) or `note` (context, "
                "not content: faint, and so is everything under it)."
            ),
        ),
        FieldSpec(
            "branches",
            "array",
            item_ref="mindmap-branch",
            min_items=1,
            description=(
                "The branches off this one, drawn top to bottom in the order written. At "
                "most three levels below the centre: a branch, a twig, a leaf."
            ),
        ),
    ),
    "timing-signal": (
        FieldSpec(
            "text",
            "string",
            required=True,
            description=(
                "The signal's name, drawn at the left of its lane: `SCLK`, `CS#`, `User`. "
                "Unique in the figure — an interval names its signal by it."
            ),
        ),
        FieldSpec(
            "lane",
            "string",
            enum=TIMING_LANES,
            description=(
                "What the lane draws: `bit` (the default: levels and clock pulses), `bus` (a "
                "word per value, in the hexagon lanes of a datasheet) or `state` (a line "
                "stepping between the named `states`, UML's robust lifeline)."
            ),
        ),
        FieldSpec(
            "values",
            "array",
            required=True,
            item_kind="string",
            min_items=1,
            description=(
                "One string per time step, every signal the same length. A `bit` lane takes "
                "`0`, `1`, `z` (high impedance), `x` (unknown), `p` (a clock pulse, high then "
                "low) and `n` (low then high); a `bus` takes any word, with `x` and `z` "
                "reserved; a `state` lane takes one of its `states`. `.` carries the step "
                "before on: a clock keeps pulsing, a word holds without a new edge."
            ),
        ),
        FieldSpec(
            "states",
            "array",
            item_kind="string",
            min_items=2,
            description=(
                "A `state` lane's named states, 2 to 6, top to bottom in the order written — "
                "write the busiest or highest first. Required on a `state` lane, refused "
                "elsewhere."
            ),
        ),
        FieldSpec(
            "group",
            "string",
            description=(
                "The name of the group this signal is in — `Controller`, `Peripheral` — drawn once "
                "over its signals. Signals in one group are written next to each other."
            ),
        ),
    ),
    "timing-marker": (
        FieldSpec(
            "at",
            "number",
            required=True,
            description=(
                "Where the marker stands, in steps from the start: `0` is the left edge, a "
                "whole number is the edge between two steps, and a half is the middle of one "
                "(where a clock pulse falls)."
            ),
        ),
        FieldSpec(
            "text",
            "string",
            description="The marker's name, over the figure: `S`, `Sr`, `P`, `sample`.",
        ),
    ),
    "timing-interval": (
        FieldSpec(
            "from",
            "number",
            required=True,
            description=(
                "The edge the interval starts at, in steps (whole or half), as a marker's `at`."
            ),
        ),
        FieldSpec(
            "to",
            "number",
            required=True,
            description="The edge it ends at, after `from`, in steps (whole or half).",
        ),
        FieldSpec(
            "text",
            "string",
            required=True,
            description=(
                "What the interval is, over its arrow: `tSU;STA`, `setup`, `100 ms`. A name, "
                "not a measurement drawspec makes — the steps are not to scale in time."
            ),
        ),
        FieldSpec(
            "signal",
            "string",
            description=(
                "The signal it is measured on, by its `text`: the arrow is drawn under that "
                "lane. Left out, it goes under the last lane."
            ),
        ),
    ),
    "usecase-actor": (
        FieldSpec(
            "id",
            "string",
            required=True,
            description=(
                "Unique among the actors, use cases and systems; what a relation's `from` "
                "and `to` name."
            ),
        ),
        _text(),
        FieldSpec(
            "supporting",
            "boolean",
            description=(
                "Whether this actor is a supporting (secondary) one — a bank, a payment "
                "service, a librarian who serves the borrower: drawn on the right of the "
                "boundary, primary actors on the left. Left out, it is derived: an actor whose "
                "every use case an actor written before it already has is supporting. An actor "
                "that `inherits` stands on its parent's side."
            ),
        ),
    ),
    "usecase-case": (
        FieldSpec(
            "id",
            "string",
            required=True,
            description=(
                "Unique among the actors, use cases and systems; what a relation's `from` "
                "and `to` name."
            ),
        ),
        _text(),
        FieldSpec(
            "system",
            "string",
            description=(
                "The id of the system whose boundary this use case is drawn in. Needed when "
                "there are two or more `systems`; with one it may be left out, and with none "
                "there is no boundary to name."
            ),
        ),
    ),
    "usecase-system": (
        FieldSpec(
            "id",
            "string",
            required=True,
            description=(
                "Unique among the actors, use cases and systems; what a use case's `system` names."
            ),
        ),
        _text(),
    ),
    "usecase-edge": (
        FieldSpec(
            "from",
            "string",
            required=True,
            description=(
                "An association's actor or use case (either way round); the base use case "
                "that `include`s; the use case that `extend`s; the specialised actor or use "
                "case that `inherits`."
            ),
        ),
        FieldSpec(
            "to",
            "string",
            required=True,
            description=(
                "The other end: the use case included, the use case extended, the general "
                "actor or use case inherited from."
            ),
        ),
        FieldSpec(
            "role",
            "string",
            enum=USECASE_EDGE_ROLES,
            description=(
                "`association` (the default: an actor takes part in a use case, a solid line "
                "with no head), `include` (the base always does the other: a dashed arrow "
                "«include» to it), `extend` (this one sometimes adds to the other: a dashed "
                "arrow «extend» to the base) or `inherits` (a kind of the other, actor to "
                "actor or use case to use case: a hollow triangle at the general end)."
            ),
        ),
    ),
    "packet-field": (
        FieldSpec(
            "text",
            "string",
            description=(
                "The field's name, written inside it: `Version`, `Source Port`, `TXEN`. "
                "Required, except on a `reserved` field, which may be left blank. Where it "
                "will not fit across the field it is broken at a space, then turned on its "
                "side, then replaced by `short`, and last by a number, the name going to the "
                "key under the drawing."
            ),
        ),
        FieldSpec(
            "bits",
            "integer",
            required=True,
            exclusive_minimum=0,
            description=(
                "How many bits wide the field is. Fields are laid end to end in the order "
                "written, left to right and row after row; one that crosses a row's end is "
                "split there and its continuation marked, so no field ever carries a position."
            ),
        ),
        FieldSpec(
            "short",
            "string",
            description=(
                "The author's own abbreviation, used when the name will not fit across the "
                "field (`DF` for `Don't Fragment`); the key under the drawing spells it out. "
                "drawspec never abbreviates on its own."
            ),
        ),
        FieldSpec(
            "holds",
            "string",
            description=(
                "What the field holds, written small under its name: a fixed value (`4`), a "
                "reset value (`0x00`), its access (`R/W`). Moved to the key when the field is "
                "too narrow for it."
            ),
        ),
        FieldSpec(
            "note",
            "string",
            description=(
                "A sentence about the field, set in the key under the drawing beside its name, "
                "as an RFC lists its fields under the header."
            ),
        ),
        FieldSpec(
            "role",
            "string",
            enum=PACKET_ROLES,
            description=(
                "`field` (the default), `reserved` (unused or reserved bits: hatched, and "
                "`text` may be left out) or `emphasis` (the field the diagram is about: a "
                "heavier outline and a bold name; at most two)."
            ),
        ),
    ),
    "pert-activity": (
        FieldSpec(
            "id",
            "string",
            required=True,
            description=(
                "A handle for this activity, unique in the document, that another activity's "
                "`after` names: `A`, `excavate`. Not drawn; the box shows `text`."
            ),
        ),
        _text(),
        FieldSpec(
            "duration",
            "number",
            description=(
                "How long the activity takes, in the document's `unit`: zero or more. Write "
                "this, or the three PERT estimates, not both."
            ),
        ),
        FieldSpec(
            "optimistic",
            "number",
            description=(
                "A PERT estimate: the shortest the activity could take. With `likely` and "
                "`pessimistic` in place of `duration`; the box carries the expected duration, "
                "(optimistic + 4 x likely + pessimistic) / 6."
            ),
        ),
        FieldSpec(
            "likely",
            "number",
            description=(
                "A PERT estimate: the most likely duration, no less than `optimistic` and no "
                "more than `pessimistic`."
            ),
        ),
        FieldSpec(
            "pessimistic",
            "number",
            description="A PERT estimate: the longest the activity could take.",
        ),
        FieldSpec(
            "after",
            "array",
            item_kind="string",
            description=(
                "The ids of the activities that must finish before this one starts "
                "(finish-to-start). Leave it out of an activity that can start at once. No "
                "circles: drawspec refuses a loop and names it."
            ),
        ),
    ),
    "automaton-state": (
        FieldSpec(
            "id",
            "string",
            required=True,
            description=(
                "A handle for this state, unique in the document, that `start`, `accepting` "
                "and each transition's `from` and `to` name: `q0`, `even`. Drawn in the "
                "circle when there is no `text`."
            ),
        ),
        FieldSpec(
            "text",
            "string",
            description=(
                "The name drawn in the circle, when it differs from the `id`: `q₀`, `S1`. One "
                "line of at most 12 characters, its `output` included: every circle is drawn "
                "the size of the widest name."
            ),
        ),
        FieldSpec(
            "output",
            "string",
            description=(
                "A Moore machine's output in this state, drawn after its name as `q0 / 1`. "
                "Give it on every state or none, and never with a transition's `output`."
            ),
        ),
    ),
    "automaton-transition": (
        FieldSpec(
            "from",
            "string",
            required=True,
            description="The id of the state the move leaves.",
        ),
        FieldSpec(
            "to",
            "string",
            required=True,
            description=(
                "The id of the state the move enters. The same id as `from` is drawn as a "
                "loop on the circle."
            ),
        ),
        FieldSpec(
            "on",
            "string",
            description=(
                "The input symbol the move reads: `0`, `a`, `coin`. One symbol per transition; "
                "two transitions between the same two states are drawn as one arrow labelled "
                "`a, b`. Leave it out of an empty move and write `epsilon` instead."
            ),
        ),
        FieldSpec(
            "epsilon",
            "boolean",
            description=(
                "`true` makes this an empty move, taken without reading a symbol, labelled ε. "
                "Not with `on`, and never in a `deterministic` automaton."
            ),
        ),
        FieldSpec(
            "output",
            "string",
            description=(
                "A Mealy machine's output on this move, drawn after its symbol as `a / 1`. "
                "Give it on every transition or none, and never with a state's `output`."
            ),
        ),
    ),
    "neuralnet-layer": (
        FieldSpec(
            "id",
            "string",
            description=(
                "A handle for this layer, unique in the document, that a `blocks` network's "
                "`skips` and `repeats` name: `conv1`, `add`. Needed only by a layer they name."
            ),
        ),
        FieldSpec(
            "text",
            "string",
            description=(
                "The layer's name. In `neurons`, written under its column: `Input layer`, "
                "`Hidden 1`; may be left out. In `blocks`, required, and written in its box: "
                "`Conv 5x5, 6`, `Multi-head attention`."
            ),
        ),
        FieldSpec(
            "size",
            "integer",
            exclusive_minimum=0,
            description=(
                "`neurons` only, and required there: how many neurons the layer holds. Up to "
                f"{NEURALNET_NEURONS_SHOWN} are drawn whole; a larger layer is drawn as its "
                "first three, a column of dots and its last two, with its size under it."
            ),
        ),
        FieldSpec(
            "labels",
            "array",
            item_kind="string",
            description=(
                "`neurons` only: a name inside each neuron, top to bottom — `x₁`, `x₂` — "
                f"one per neuron, at most {NEURALNET_LABEL_MAX} characters each. Only on a "
                "layer drawn whole."
            ),
        ),
        FieldSpec(
            "bias",
            "boolean",
            description=(
                "`neurons` only: `true` draws a bias unit, `+1`, above the column, joined to "
                "every neuron of the next layer. Not on the last layer, which feeds nothing."
            ),
        ),
        FieldSpec(
            "type",
            "string",
            description=(
                "`blocks` only: what sort of layer this is — `conv`, `pool`, `dense`. Layers "
                f"of one type share a fill, and a key names them; at most {CLASSES_MAX} types."
            ),
        ),
        FieldSpec(
            "shape",
            "string",
            description=(
                "`blocks` only: the tensor the layer puts out, written beside its box in the "
                "label size: `28x28x6`, `512`."
            ),
        ),
        FieldSpec(
            "branches",
            "array",
            item_ref="neuralnet-branch",
            min_items=2,
            description=(
                f"`blocks` only: in place of a layer, 2 to {NEURALNET_BRANCH_MAX} parallel "
                "branches, each a tower of layers, split from the layer before and joined by "
                "the layer after (a `concat`) — GoogLeNet's Inception module. Such an entry "
                "holds `branches` alone; never first or last, and never two in a row."
            ),
        ),
    ),
    "neuralnet-tower-layer": (
        FieldSpec(
            "text",
            "string",
            required=True,
            description="What the layer is, written in its box: `1x1 conv`, `3x3 max pool`.",
        ),
        FieldSpec(
            "type",
            "string",
            description="What sort of layer this is, sharing a fill and the key with the rest.",
        ),
    ),
    "neuralnet-branch": (
        FieldSpec(
            "layers",
            "array",
            required=True,
            item_ref="neuralnet-tower-layer",
            min_items=1,
            description=(
                f"The branch's layers in order, 1 to {NEURALNET_TOWER_MAX}, each with its "
                "`text` and `type` only: drawn as a tower beside the other branches."
            ),
        ),
    ),
    "neuralnet-skip": (
        FieldSpec(
            "from",
            "string",
            required=True,
            description="The id of the layer whose output the connection carries.",
        ),
        FieldSpec(
            "to",
            "string",
            required=True,
            description=(
                "The id of a later layer the connection feeds — an `add` layer for a residual "
                "connection, a `concat` for a dense one. Not the next layer: that is joined "
                "already."
            ),
        ),
        _text(required=False),
    ),
    "neuralnet-repeat": (
        FieldSpec(
            "from",
            "string",
            required=True,
            description="The id of the first layer of the repeated block.",
        ),
        FieldSpec(
            "to",
            "string",
            required=True,
            description="The id of the last layer of the block; the same as `from` for one.",
        ),
        FieldSpec(
            "times",
            "integer",
            exclusive_minimum=1,
            required=True,
            description=(
                "How many times the block is stacked: `6`, drawn "
                "`\N{MULTIPLICATION SIGN}6` by its frame."
            ),
        ),
        _text(required=False),
    ),
    "sunburst-node": (
        _text(),
        FieldSpec(
            "children",
            "array",
            item_ref="sunburst-node",
            min_items=1,
            description=(
                "The sectors nested inside this one — the next ring, drawn clockwise in the "
                "order written. At most three rings in all; leave it out of a node that ends "
                "the hierarchy."
            ),
        ),
    ),
    "network-segment": (
        FieldSpec(
            "id",
            "string",
            required=True,
            description="Unique among the networks; what a host's attachment names.",
        ),
        FieldSpec(
            "text",
            "string",
            description=(
                "The network's name, written in bold at the left of its bus. Left out, the "
                "`id` is the name."
            ),
        ),
        FieldSpec(
            "address",
            "string",
            description=(
                "The network's address, written on its bus after the name — `210.x.x.x/24`, "
                "`10.0.1.0/24`. Words, not parsed: drawspec checks nothing about it."
            ),
        ),
    ),
    "network-attachment": (
        FieldSpec(
            "network",
            "string",
            required=True,
            description="The id of a network this host is on.",
        ),
        FieldSpec(
            "address",
            "string",
            description=(
                "The host's address on that network, written beside its line where it meets "
                "the bus — `.1`, `10.0.1.10`. Optional."
            ),
        ),
    ),
    "network-host": (
        FieldSpec(
            "id",
            "string",
            required=True,
            description="Unique among the hosts; what a group's `members` name.",
        ),
        FieldSpec(
            "text",
            "string",
            description=(
                "The words in the host's box. Left out, the `id` is the name. A newline makes "
                "the first line a lead over a detail — `db01` over `primary`."
            ),
        ),
        FieldSpec(
            "role",
            "string",
            enum=NETWORK_HOST_ROLES,
            description=(
                "`step` (the default box: a server, a router, a firewall, any device), "
                "`emphasis` (the host the diagram is about; at most two), `store` (a drum: a "
                "database, a storage array) or `person` (a user's machine, a client). No "
                "device icons: say what a box is in its words."
            ),
        ),
        FieldSpec(
            "networks",
            "array",
            required=True,
            item_ref="network-attachment",
            min_items=1,
            description=(
                "The networks this host is on, each with an optional address. A host on two "
                "or more is drawn between them, joining them — a router, a firewall, a "
                "dual-homed server. The column order is drawspec's, chosen so the line "
                "crosses no bus it is not on; where no order manages that, the line hops "
                "over the bus, a jump that does not join it, and the fewest hops win."
            ),
        ),
    ),
    "network-group": (
        FieldSpec(
            "text",
            "string",
            description="The group's name, at the top left of its backdrop. Optional.",
        ),
        FieldSpec(
            "members",
            "array",
            required=True,
            item_kind="string",
            min_items=1,
            description=(
                "The ids of the hosts drawn on this group's shaded backdrop, side by side. A "
                "host is in one group at most."
            ),
        ),
    ),
    "gitgraph-branch": (
        FieldSpec(
            "name",
            "string",
            required=True,
            description=(
                "The branch's name, as git spells it (`main`, `feature/login`): written at "
                "the head of its lane and named by every step on it. Unique in the document."
            ),
        ),
        FieldSpec(
            "from",
            "string",
            description=(
                "Where the branch forks: the name of another branch — it forks from that "
                "branch's latest commit at the branch's first step — or the `id` of a commit "
                "written before then. Left out, it is the first branch; the first branch "
                "itself has none."
            ),
        ),
        _role(GITGRAPH_ROLES, "step"),
    ),
    "gitgraph-step": (
        FieldSpec(
            "on",
            "string",
            required=True,
            description=(
                "The branch this commit is made on — one of `branches`. Steps are drawn in "
                "the order written, one place in time each."
            ),
        ),
        _text(required=False),
        FieldSpec(
            "id",
            "string",
            description=(
                "A handle for this commit, unique in the document: what a `pick` or a "
                "branch's `from` names. Drawn as the label when there is no `text` (a short "
                "hash, `C2`)."
            ),
        ),
        FieldSpec(
            "merge",
            "string",
            description=(
                "Makes this a merge commit: the name of the branch merged into `on`, at its "
                "latest commit. The merged branch may carry on afterwards."
            ),
        ),
        FieldSpec(
            "pick",
            "string",
            description=(
                "Makes this a cherry-pick: the `id` of an earlier commit on another branch, "
                "copied onto `on`. Its label is the original's unless `text` says otherwise."
            ),
        ),
        FieldSpec(
            "tag",
            "string",
            description="A tag on this commit (`v1.0`), drawn as a tag beside it. Unique.",
        ),
        _role(GITGRAPH_ROLES, "step"),
    ),
    "railroad-rule": (
        FieldSpec(
            "name",
            "string",
            required=True,
            description=(
                'The rule\'s name, drawn above its track and referred to by `{"rule": name}` '
                "boxes. Unique in the document; one line, drawn exactly as written."
            ),
        ),
        FieldSpec(
            "expr",
            "object",
            required=True,
            ref="railroad-item",
            description=(
                "What the rule matches, as one item: usually a `seq`. The track runs from an "
                "entry bar on the left to an exit bar on the right; a long top-level `seq` "
                "wraps onto further lines, a return track leading each line into the next."
            ),
        ),
    ),
    "railroad-item": (
        FieldSpec(
            "terminal",
            "string",
            description=(
                "Literal text the input must contain, drawn in a rounded box in monospace, "
                "exactly as written: a keyword, a punctuation mark, an option."
            ),
        ),
        FieldSpec(
            "rule",
            "string",
            description=(
                "The name of another rule, drawn in a square box: one of `rules`, or a name "
                "listed in `external` when it is defined elsewhere."
            ),
        ),
        FieldSpec(
            "special",
            "string",
            description=(
                "A set described in words rather than spelt out, drawn in a dashed box: "
                "`any digit 1-9`, `any character but a quote`."
            ),
        ),
        FieldSpec(
            "comment",
            "string",
            description=(
                "Words written on the track with no box, the line breaking for them — what "
                "a branch means, or a loop's separator in words. Matches nothing."
            ),
        ),
        FieldSpec(
            "seq",
            "array",
            item_ref="railroad-item",
            min_items=2,
            description=(
                "Items one after another, left to right. A rule's top-level `seq` wraps onto "
                "further lines when it is wider than the canvas."
            ),
        ),
        FieldSpec(
            "choice",
            "array",
            item_ref="railroad-item",
            min_items=2,
            description=(
                "Alternatives, 2 to 10, stacked one under another and rejoining. The first "
                "is drawn on the main line, so put the usual one first; an empty alternative "
                "is an `optional` round the choice."
            ),
        ),
        FieldSpec(
            "optional",
            "object",
            ref="railroad-item",
            description="An item that may be left out: drawn on the line, with a bypass over it.",
        ),
        FieldSpec(
            "repeat",
            "object",
            ref="railroad-item",
            description=(
                "An item that may be repeated: drawn on the line, with a loop back under it. "
                "`min` says whether it may also be left out."
            ),
        ),
        FieldSpec(
            "separator",
            "object",
            ref="railroad-item",
            description=(
                "With `repeat` only: what comes between repetitions, drawn on the loop — a "
                '`terminal`, `rule`, `special` or `comment`, such as `{"terminal": ","}`.'
            ),
        ),
        FieldSpec(
            "min",
            "integer",
            description=(
                "With `repeat`, and required there: `1` for one or more, `0` for zero or "
                "more (the loop with a bypass over it)."
            ),
        ),
    ),
    "wardley-anchor": (
        FieldSpec(
            "id",
            "string",
            required=True,
            description="Unique among the anchors and components; nothing needs an anchor.",
        ),
        _WARDLEY_NAME,
        FieldSpec(
            "needs",
            "array",
            required=True,
            item_kind="string",
            min_items=1,
            description=(
                "The ids of the components this user or need depends on directly — the top "
                "of the value chain. The anchor is drawn above them, across the top row."
            ),
        ),
    ),
    "wardley-component": (
        FieldSpec(
            "id",
            "string",
            required=True,
            description="Unique among the anchors and components; what a `needs` names.",
        ),
        _WARDLEY_NAME,
        FieldSpec(
            "evolution",
            "string",
            required=True,
            enum=WARDLEY_EVOLUTION,
            description=(
                "How evolved this component is, by name: `genesis`, `custom` (custom-built), "
                "`product` (+rental) or `commodity` (+utility), optionally `early` or `late` in "
                "the stage (`late product`). Twelve places, left to right; never a number."
            ),
        ),
        FieldSpec(
            "needs",
            "array",
            item_kind="string",
            description=(
                "The ids of the components this one depends on. Each is drawn below it — "
                "lower in the value chain, less visible — joined by a straight line."
            ),
        ),
        FieldSpec(
            "depth",
            "integer",
            exclusive_minimum=0,
            description=(
                "Which row of the value chain this sits on, the anchors being row 0. Left out, "
                "it is one row below the lowest thing that needs it; set it only to sink a "
                "component further, never above what needs it."
            ),
        ),
        FieldSpec(
            "evolves",
            "string",
            enum=WARDLEY_EVOLUTION,
            description=(
                "Where this component is heading: a place further right, in the same words as "
                "`evolution`. Drawn as a dashed arrow to a dashed circle on the same row."
            ),
        ),
        FieldSpec(
            "inertia",
            "boolean",
            description=(
                "Something resists this component's evolution — an investment, a habit, a "
                "regulation. Drawn as a heavy bar on its right, the way it would move."
            ),
        ),
    ),
    "wardley-note": (
        _text(),
        FieldSpec(
            "on",
            "array",
            required=True,
            item_kind="string",
            min_items=1,
            description=(
                "The ids of the anchors or components this note is about. Each is marked with "
                "the note's number, and the note is written out, numbered, under the map."
            ),
        ),
    ),
    "treemap-group": (
        FieldSpec(
            "id",
            "string",
            required=True,
            description="Unique among the groups; what a part's `group` names.",
        ),
        _text(),
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
    "class": (
        FieldSpec(
            "id",
            "string",
            required=True,
            description="What a node's `class` names. Unique among the classes.",
        ),
        _text(required=True),
    ),
    "phase": (
        _text(required=True),
        FieldSpec(
            "members",
            "array",
            required=True,
            item_kind="string",
            min_items=1,
            description=(
                "The ids of the steps in this phase, in any order and in any lane. Every "
                "step is in one phase, so a step left out or listed twice is refused."
            ),
        ),
    ),
    "item": (
        FieldSpec("id", "string", description="Optional; generated from position when absent."),
        _text(),
        _role(PLAIN_NODE_ROLES, "step"),
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
        _role(PLAIN_NODE_ROLES, "step"),
        FieldSpec("note", "string", description=_NOTE_DESCRIPTION),
    ),
    "ring": (
        _text(),
        _role(PLAIN_NODE_ROLES, "step"),
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
        _role(PLAIN_NODE_ROLES, "step"),
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
        _role(PLAIN_NODE_ROLES, "step"),
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
        _role(PLAIN_NODE_ROLES, "step"),
    ),
    "stage": (
        _text(),
        _role(PLAIN_NODE_ROLES, "step"),
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
        FieldSpec(
            "amount",
            "number",
            exclusive_minimum=0,
            description=(
                "On a `funnel` stage: how many reached it. Written under the name, with the "
                "share kept from the stage before; the taper stays the drawing's own, not to "
                "scale. Every stage or none, never more than the stage before."
            ),
        ),
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
                "quarters, the service models, the teams. On a chart's vertical axis "
                "they make horizontal bars: every series a `bar`, each point "
                "`[amount, position]`, the first category the top row, names on the left."
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
    # `quadrant`'s own axis type: no `categories` (a quadrant's directions are
    # judgements, not a list), and two named `ends` — the field `numberline` uses.
    "axis-quadrant": (
        FieldSpec(
            "label",
            "string",
            required=True,
            description="Required: an unlabelled axis cannot be read.",
        ),
        FieldSpec("unit", "string", description="What the scores are in, written after the label."),
        FieldSpec(
            "min",
            "number",
            description="Where the axis starts. Omit to take it from the positions.",
        ),
        FieldSpec(
            "max",
            "number",
            description="Where the axis ends. Omit to take it from the positions.",
        ),
        FieldSpec(
            "ends",
            "array",
            item_kind="string",
            min_items=2,
            description=(
                "Two words for the low and the high end — `Low` and `High`, `Rarely` and "
                "`Often` — written at the two ends of the axis, as on a `numberline`."
            ),
        ),
    ),
    "axes-quadrant": (
        FieldSpec(
            "horizontal",
            "object",
            required=True,
            ref="axis-quadrant",
            description="The judgement across.",
        ),
        FieldSpec(
            "vertical",
            "object",
            required=True,
            ref="axis-quadrant",
            description="The judgement up.",
        ),
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
        _role(PLAIN_NODE_ROLES, "step"),
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
            "Which of the forty-seven diagrams this is. It selects the fields that are "
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
    FieldSpec(
        "theme",
        "string",
        description=(
            "A bundled theme name or the path of a theme file. A relative path is read "
            "from the document's own folder when the file is there, so a theme can sit "
            "beside the diagrams that use it."
        ),
    ),
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
    # A `cycle` is a ring of peers: it takes no classes.
    ("flow", "tree"): (
        FieldSpec(
            "classes",
            "array",
            item_ref="class",
            min_items=1,
            description=(
                "The classes the boxes are sorted into, each `{id, text}`: 1 to "
                f"{CLASSES_MAX}, every one used by some node. Each is drawn as a faint fill "
                "from the theme's fixed sequence (`[classes] fills`: a grey wash, then "
                "patterns), in the order declared, and the key under the drawing names "
                "each by its `text`. For a grouping the reader must see across the whole "
                "drawing — external systems greyed in a C4 context, steps by owning team."
            ),
        ),
    ),
    ("tree",): (
        FieldSpec(
            "style",
            "string",
            enum=TREE_STYLES,
            description=(
                "`boxes` (the default) ranks boxed nodes down from the root. `bracket` draws "
                "a tournament bracket or a cladogram: every leaf on one outer edge, square "
                "elbows, and each inner node unboxed — its words (a match's winner, a "
                'clade\'s name) on its own line, or none (`"text": ""`). An edge\'s '
                "`label` is written on the child's line by the elbow: a score, a trait. "
                "Every node but the root has one parent and every inner node at least two "
                f"children; at most {BRACKET_LEAVES_MAX} leaves, and no groups, bands, "
                "classes, and no node role but `step`."
            ),
        ),
        FieldSpec(
            "root",
            "string",
            enum=BRACKET_ROOTS,
            description=(
                'Only with `"style": "bracket"`: the edge the root stands at. `right` '
                "(the default) is a tournament read left to right, the champion last; `left` "
                "is a cladogram's, the leaves' names in a column at the right; `middle` "
                "is the two-sided draw, the root's first child's half on the left and its "
                "second's on the right, the final in the middle. A bracket reads across, "
                "so there is no top or bottom."
            ),
        ),
    ),
    ("flow",): (
        FieldSpec(
            "loops",
            "array",
            item_ref="loop",
            description=(
                "The feedback loops of a causal loop diagram, each named and marked R "
                "(reinforcing) or B (balancing) inside the loop it closes — the type "
                "derived from the signs, never chosen. Needs `polarity` on the edges."
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
                "without them a reader sees a table where the source drew a process. "
                "An edge between cells in neighbouring rows that share no column, such as "
                "a return from the last output to the first process, turns along the "
                "join between the rows, and its label is wrapped onto a stretch of that "
                "join no other edge crosses."
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
        FieldSpec(
            "unit",
            "string",
            description=(
                "What the stages' amounts count — `visitors`, `applications`, `£k` — written "
                "after each one. Only with amounts."
            ),
        ),
        FieldSpec(
            "values",
            "boolean",
            description=(
                "`false` leaves the amounts and shares out and writes the stage names alone. "
                "Defaults to true."
            ),
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
            ref="axes-quadrant",
            description="The two named axes whose crossing makes the four quadrants.",
        ),
        FieldSpec(
            "quadrants",
            "array",
            item_kind="string",
            description=(
                "Exactly four names, one per quarter, written faint in its outer corner: "
                "top right first, then counter-clockwise — top left, bottom left, bottom "
                "right (Mermaid's order). An empty string leaves that quarter unnamed."
            ),
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
                "state inside; one to a group enters it at the group's `initial`. A "
                "composite with `regions` is drawn divided by dashed lines, every region "
                "current at once."
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
                "coordinate. Every participant must send or receive a message. A "
                'person taking part is `role: "actor"`, drawn as the UML stick figure '
                "with the name under it."
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
                "nobody writes how tall it is. An `async` message (solid line, open "
                "head) is sent without waiting, opens no bar and takes no reply."
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
        FieldSpec(
            "phases",
            "array",
            item_ref="phase",
            min_items=2,
            description=(
                "The stages the process passes through, in the order it runs — named in a "
                "band along the lanes' edge and divided by faint lines across every lane "
                "(a cross-functional flowchart's phases). Each phase lists its steps, and "
                "with `phases` given every step is in exactly one. A phase's steps are "
                "drawn after every step of the phases before it, so the phases never "
                f"interleave. 2 to {LANES_PHASES_MAX}."
            ),
        ),
        FieldSpec(
            "classes",
            "array",
            item_ref="class",
            min_items=1,
            description=(
                "The classes the boxes are sorted into, each `{id, text}`: 1 to "
                f"{CLASSES_MAX}, every one used by some node. Each is drawn as a faint fill "
                "from the theme's fixed sequence (`[classes] fills`: a grey wash, then "
                "patterns), in the order declared, and the key under the drawing names "
                "each by its `text`. For a grouping the reader must see across the whole "
                "drawing — external systems greyed in a C4 context, steps by owning team."
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
                "specific when there is a hierarchy, side by side otherwise; round the one "
                "marked `centre`, a star schema's fact table, when one is."
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
    VENN_KINDS: (
        FieldSpec(
            "sets",
            "array",
            required=True,
            item_ref="venn-set",
            min_items=2,
            description=(
                "Two to four sets, each a circle of one size with its name outside it — four "
                "are four equal ellipses, so all fifteen regions exist. Not sizes: the "
                "shapes are equal, because a Venn diagram says what overlaps, not how much."
            ),
        ),
        FieldSpec(
            "regions",
            "array",
            item_ref="region",
            description=(
                "What each region holds, named by membership. A region not listed is drawn "
                "empty: its set's name says enough."
            ),
        ),
    ),
    JOURNEY_KINDS: (
        FieldSpec(
            "feelings",
            "array",
            required=True,
            item_kind="string",
            min_items=2,
            description=(
                "The named levels a stage's feeling may take, **worst first**: drawn as "
                "guides across the map, the worst at the bottom, each named once on the "
                "left. Names, not scores."
            ),
        ),
        FieldSpec(
            "rows",
            "array",
            item_ref="journey-row",
            min_items=1,
            description=(
                "The detail rows under the feeling line, top to bottom: what the person "
                "does, where, what gets in the way. Optional: without rows the map is the "
                "stages and the line."
            ),
        ),
        FieldSpec(
            "stages",
            "array",
            required=True,
            item_ref="journey-stage",
            min_items=2,
            description=(
                "Left to right as written, one column each, all one width. The feeling line "
                "passes through every stage's point."
            ),
        ),
    ),
    TREEMAP_KINDS: (
        FieldSpec(
            "parts",
            "array",
            required=True,
            item_ref="treemap-part",
            min_items=2,
            description=(
                "The parts of one total, each a rectangle whose area is in proportion to its "
                "`amount`, with its words inside it. Laid out largest first whatever the "
                "written order, which only breaks ties; `note` parts go last."
            ),
        ),
        FieldSpec(
            "groups",
            "array",
            item_ref="treemap-group",
            min_items=1,
            description=(
                "One level of grouping: each group is a captioned frame holding the parts that "
                "name it, filled with the theme's mark fills in the order written. Groups do "
                "not nest."
            ),
        ),
        FieldSpec(
            "unit",
            "string",
            description="What the values are in — `kB`, `GB`, `hours` — written after each one.",
        ),
        FieldSpec(
            "values",
            "boolean",
            description=(
                "Whether to write each part's amount under its words, and each group's total "
                "beside its name. Defaults to true."
            ),
        ),
    ),
    SANKEY_KINDS: (
        FieldSpec(
            "nodes",
            "array",
            required=True,
            item_ref="sankey-node",
            min_items=2,
            description=(
                "Where the quantity starts, passes and ends. A node's column is derived from the "
                "flows — sources left, ends right — never written; the written order is where "
                "the order down each column starts."
            ),
        ),
        FieldSpec(
            "flows",
            "array",
            required=True,
            item_ref="sankey-flow",
            min_items=1,
            description=(
                "How much goes from one node to another, each a band whose thickness is in "
                "proportion to its `amount`. What reaches a node in the middle must all leave "
                "it, and nothing flows back."
            ),
        ),
        FieldSpec(
            "unit",
            "string",
            description=(
                "What the amounts are in — `tickets`, `cores`, `€ million` — written after "
                "each total."
            ),
        ),
        FieldSpec(
            "values",
            "boolean",
            description="Whether to write each node's total under its name. Defaults to true.",
        ),
    ),
    NUMBERLINE_KINDS: (
        FieldSpec(
            "axis",
            "object",
            required=True,
            ref="axis-numberline",
            description=(
                "The one scale, drawn across the canvas with an arrowhead at each end: "
                "numbered ticks, or two named `ends`."
            ),
        ),
        FieldSpec(
            "points",
            "array",
            item_ref="numberline-point",
            description=(
                "Values marked on the axis, each a dot with its words above it — or below the "
                "numbers, with a leader, when the words above would touch."
            ),
        ),
        FieldSpec(
            "ranges",
            "array",
            item_ref="numberline-range",
            description=(
                "Stretches of the scale, each a line in its own track above the axis, in the "
                "order written — the last nearest the axis. Each end is closed, open, or "
                "missing: a range with no `to` runs on past `max`."
            ),
        ),
    ),
    BARMODEL_KINDS: (
        FieldSpec(
            "bars",
            "array",
            required=True,
            item_ref="barmodel-bar",
            min_items=1,
            description=(
                "One to three bars, top to bottom, all starting at one left edge, every "
                "length in one scale: the longest bar fills the width."
            ),
        ),
        FieldSpec(
            "braces",
            "array",
            item_ref="barmodel-brace",
            description=(
                "What a stretch adds up to — the whole, a difference, a total over two bars "
                "— each a brace with its amount or its `?`."
            ),
        ),
    ),
    WATERFALL_KINDS: (
        FieldSpec(
            "axis",
            "object",
            required=True,
            ref="waterfall-axis",
            description="The vertical axis: its `label`, what the numbers are and their unit.",
        ),
        FieldSpec(
            "bars",
            "array",
            required=True,
            item_ref="waterfall-bar",
            min_items=3,
            description=(
                "The bars, left to right: a `total` first, signed `amount` steps, any "
                "subtotals (a `total` mid-way, checked against the running sum), and a "
                "`total` last."
            ),
        ),
    ),
    ARGUMENT_KINDS: (
        FieldSpec(
            "claim",
            "string",
            required=True,
            description=(
                "The contention, drawn at the top in the heavy outline. Points name it as "
                '`"on": "claim"`. A qualifier (*probably*, *in most cases*) is a word in it.'
            ),
        ),
        FieldSpec(
            "points",
            "array",
            required=True,
            item_ref="argument-point",
            min_items=1,
            description=(
                "Every reason, objection, rebuttal and piece of evidence, each `on` the box "
                "it bears on, `for` or `against` it. Drawn as a tree down from the claim, "
                "siblings in the order written; at most 15, and 4 deep."
            ),
        ),
    ),
    FAMILYTREE_KINDS: (
        FieldSpec(
            "people",
            "array",
            required=True,
            item_ref="familytree-person",
            min_items=2,
            description=(
                "Everyone in the tree. Generations and numbers are derived: a child is one "
                "row below its parents, a partner shares their partner's row, and people "
                "are numbered left to right in each row (II-3). At most 30, in 4 generations."
            ),
        ),
        FieldSpec(
            "couples",
            "array",
            required=True,
            item_ref="familytree-couple",
            min_items=1,
            description=(
                "Who partnered whom, and their children. Everyone is in at least one couple, "
                "as a partner or a child."
            ),
        ),
    ),
    METER_KINDS: (
        FieldSpec(
            "style",
            "string",
            enum=METER_STYLES,
            description=(
                "How every meter in the document is drawn: `bar` (the default, a progress "
                "bar), `thermometer` (a goal filling up), `dial` (a needle on a half-circle) "
                "or `bullet` (a bar on named bands, with a target tick). One for the whole "
                "panel, so like is compared with like."
            ),
        ),
        FieldSpec(
            "meters",
            "array",
            required=True,
            item_ref="meter-meter",
            min_items=1,
            description=(
                "The meters, 1 to 6, in reading order: rows for bars and bullets, columns for "
                "thermometers, up to three dials to a row. Each has its own scale."
            ),
        ),
    ),
    CLOCK_KINDS: (
        FieldSpec(
            "clocks",
            "array",
            required=True,
            item_ref="clock-face",
            min_items=1,
            description=(
                "The faces, 1 to 12, in reading order, up to four to a row: each a `time`, "
                "and optionally a `text` under it and a `since`."
            ),
        ),
        FieldSpec(
            "numerals",
            "string",
            enum=CLOCK_NUMERALS,
            description=(
                "The numbers round every face: `arabic` (the default, 1 to 12), `roman` (I to "
                "XII), `quarters` (12, 3, 6 and 9 only) or `none`."
            ),
        ),
        FieldSpec(
            "readout",
            "string",
            enum=CLOCK_READOUTS,
            description=(
                "What is written under each face: `words` (the default: `quarter past three`), "
                "`digits` (`3:15`, as written), `both`, or `none` for a worksheet."
            ),
        ),
    ),
    RAG_KINDS: (
        FieldSpec(
            "rows",
            "array",
            required=True,
            item_ref="rag-row",
            min_items=1,
            description=(
                "The workstreams or risks, 1 to 15, in the order written: each a name, its "
                "`rag`, and optionally a `trend` and a `note`."
            ),
        ),
    ),
    NETWORK_KINDS: (
        FieldSpec(
            "networks",
            "array",
            required=True,
            item_ref="network-segment",
            min_items=1,
            description=(
                "The networks, 1 to 6, each a horizontal bus, drawn top to bottom in the order "
                "written. Write them in the order traffic meets them — the internet, the DMZ, "
                "the internal network, storage — so a host on two neighbours sits between them."
            ),
        ),
        FieldSpec(
            "hosts",
            "array",
            required=True,
            item_ref="network-host",
            min_items=1,
            description=(
                "The hosts, 1 to 24, each a box under its topmost network with a line to every "
                "network it is on. The columns are drawspec's: ordered for the fewest lines "
                "hopping over a bus they are not on (usually none), then as few and as close to "
                "the order written as that allows."
            ),
        ),
        FieldSpec(
            "groups",
            "array",
            item_ref="network-group",
            min_items=1,
            description=(
                "Optional: up to 6 sets of hosts drawn on a shaded backdrop, with an optional "
                "name — a cluster, a rack, a site. No host outside a group may stand inside it."
            ),
        ),
    ),
    TIMING_KINDS: (
        FieldSpec(
            "signals",
            "array",
            required=True,
            item_ref="timing-signal",
            min_items=1,
            description=(
                "The lanes, 1 to 12, top to bottom in the order written: each a `text`, a "
                "`lane` and one value per step in `values`, every signal the same number of "
                "steps (40 at most)."
            ),
        ),
        FieldSpec(
            "ticks",
            "array",
            item_kind="string",
            description=(
                "A name for each step, written under the figure — one per step, as many as "
                "the values; an empty string leaves a step unnamed."
            ),
        ),
        FieldSpec(
            "markers",
            "array",
            item_ref="timing-marker",
            description=(
                "Vertical lines across every lane at an edge, up to 8, each named over the "
                "figure: a START, a sample point."
            ),
        ),
        FieldSpec(
            "intervals",
            "array",
            item_ref="timing-interval",
            description=(
                "Named spans between two edges, up to 10, each an arrow under a signal's "
                "lane: a setup time, a hold time, a timeout."
            ),
        ),
    ),
    USECASE_KINDS: (
        FieldSpec(
            "systems",
            "array",
            item_ref="usecase-system",
            description=(
                "The systems whose boundaries hold the use cases, 0 to 3, each a frame with its "
                "name in the corner, stacked down the middle in the order written. Left out, "
                "the use cases stand with no boundary."
            ),
        ),
        FieldSpec(
            "actors",
            "array",
            required=True,
            item_ref="usecase-actor",
            min_items=1,
            description=(
                "Who or what uses the system, 1 to 8, each drawn as a stick figure with its "
                "name under it, outside every boundary: primary actors on the left, "
                "`supporting` ones on the right, a specialised actor above or below its "
                "parent. "
                "No coordinates; the order down each side is derived to keep lines from "
                "crossing."
            ),
        ),
        FieldSpec(
            "usecases",
            "array",
            required=True,
            item_ref="usecase-case",
            min_items=1,
            description=(
                "What the actors do with the system, 1 to 15, each an ellipse inside its "
                "system's boundary. A use case that is included, that extends another or that "
                "specialises one stands a column to the right of it, three columns at most."
            ),
        ),
        FieldSpec(
            "edges",
            "array",
            required=True,
            item_ref="usecase-edge",
            min_items=1,
            description=(
                "The relations, up to 30: `association` between an actor and a use case, "
                "`include` and `extend` between use cases, `inherits` between two actors or "
                "two use cases. No labels: the role says what each line is."
            ),
        ),
    ),
    PACKET_KINDS: (
        FieldSpec(
            "bits_per_row",
            "integer",
            description=(
                "How many bits one row holds: 8, 16, 32 (the default: an RFC header's word) "
                "or 64. A field wider than what is left of its row is split across the rows."
            ),
        ),
        FieldSpec(
            "numbering",
            "string",
            enum=PACKET_NUMBERINGS,
            description=(
                "Which end bit 0 is at. `left` (the default) is the RFC convention: the ruler "
                "counts 0 to 31 from the left of every word. `right` is a register's: the "
                "highest bit at the top left, counting down to bit 0 at the bottom right, each "
                "row with its own ruler — so the fields are still written in reading order, "
                "the highest bits first, and must fill whole rows."
            ),
        ),
        FieldSpec(
            "fields",
            "array",
            required=True,
            item_ref="packet-field",
            min_items=1,
            description=(
                "The bit fields, 1 to 40, in reading order: left to right, then row after row, "
                "each with its width in `bits`. Wrapped into rows of `bits_per_row`, 16 rows "
                "at most; a field that crosses a row's end is split and its continuation "
                "marked."
            ),
        ),
    ),
    SUNBURST_KINDS: (
        FieldSpec(
            "centre",
            "string",
            description=(
                "An optional hub label in the middle — the overall topic. Left out, the first "
                "ring fills the centre."
            ),
        ),
        FieldSpec(
            "nodes",
            "array",
            required=True,
            item_ref="sunburst-node",
            min_items=2,
            description=(
                "The first ring, 2 to 8, clockwise from twelve o'clock in the order written, "
                "each with optional `children` for the ring nested inside it. Nested up to "
                "three rings, 150 sectors in all; every terminal sector takes an equal angle, "
                "so there are no amounts."
            ),
        ),
    ),
    GITGRAPH_KINDS: (
        FieldSpec(
            "branches",
            "array",
            required=True,
            item_ref="gitgraph-branch",
            min_items=1,
            description=(
                "The branches, 1 to 8, one lane each in the order written: the first is the "
                "trunk (`main`) and every other forks `from` another branch or a commit `id`; "
                "the lane order need not be the order the branches were made."
            ),
        ),
        FieldSpec(
            "steps",
            "array",
            required=True,
            item_ref="gitgraph-step",
            min_items=1,
            description=(
                "The commits, 1 to 30, in the order they were made: each `on` a branch, and a "
                "merge (`merge`) or a cherry-pick (`pick`) when it is one. Lanes, spacing and "
                "the lines between commits are derived."
            ),
        ),
        FieldSpec(
            "direction",
            "string",
            enum=GITGRAPH_DIRECTIONS,
            description=(
                "Which way time runs: `right` (the default) across the page, each commit's "
                "label under it; `down` the page, the labels in a column beside the lanes as "
                "`git log --graph` sets them — the one for long commit messages."
            ),
        ),
    ),
    RAILROAD_KINDS: (
        FieldSpec(
            "rules",
            "array",
            required=True,
            item_ref="railroad-rule",
            min_items=1,
            description=(
                "The grammar's rules, 1 to 12, drawn one under another in the order written, "
                "each a named track from entry to exit, at most 40 boxes on one track."
            ),
        ),
        FieldSpec(
            "external",
            "array",
            item_kind="string",
            description=(
                "Names a `rule` box may refer to that this document does not define — rules "
                "drawn elsewhere. Every other `rule` must name one of `rules`."
            ),
        ),
    ),
    WARDLEY_KINDS: (
        FieldSpec(
            "anchors",
            "array",
            required=True,
            item_ref="wardley-anchor",
            min_items=1,
            description=(
                "The users or needs the map is anchored on, 1 to 3, across the top: each names "
                "the components it needs. Everything on the map hangs from an anchor."
            ),
        ),
        FieldSpec(
            "components",
            "array",
            required=True,
            item_ref="wardley-component",
            min_items=1,
            description=(
                "The value chain, 1 to 24: each a name, a named `evolution` stage and what it "
                "`needs`. Its row is derived — below everything that needs it — and its place "
                "across is its stage; neither is a coordinate."
            ),
        ),
        FieldSpec(
            "notes",
            "array",
            item_ref="wardley-note",
            description=(
                "Up to 6 numbered notes, each about one or more anchors or components: the "
                "number is set beside each, the words under the map."
            ),
        ),
    ),
    AUTOMATON_KINDS: (
        FieldSpec(
            "states",
            "array",
            required=True,
            item_ref="automaton-state",
            min_items=1,
            description=(
                "The states, 1 to 12, each a circle with its name inside, all the size of the "
                "widest. Ranked left to right from `start` by the transitions; the order "
                "written breaks ties and is the row order of the text form's table."
            ),
        ),
        FieldSpec(
            "start",
            "string",
            required=True,
            description=(
                "The id of the start state, entered by an arrow coming in from nowhere. "
                "Exactly one."
            ),
        ),
        FieldSpec(
            "accepting",
            "array",
            item_kind="string",
            description=(
                "The ids of the accepting (final) states, each drawn as a double circle. May "
                "include `start`; may be left out, as a Mealy or Moore machine often is."
            ),
        ),
        FieldSpec(
            "transitions",
            "array",
            item_ref="automaton-transition",
            description=(
                "The moves, each `from`, `to` and the symbol it reads `on` (or `epsilon`). "
                "Several between the same two states, in the same direction, are drawn as "
                "one arrow labelled `a, b`; a pair in opposite directions as two arcs bowed "
                "apart; a move from a state to itself as a loop on its circle."
            ),
        ),
        FieldSpec(
            "deterministic",
            "boolean",
            description=(
                "`true` says this is a DFA, and has drawspec hold it to that: no ε-move, and "
                "no two moves from one state on the same symbol. A missing move is allowed — "
                "the textbooks leave the dead state out."
            ),
        ),
    ),
    NEURALNET_KINDS: (
        FieldSpec(
            "style",
            "string",
            enum=NEURALNET_STYLES,
            description=(
                "`neurons` (the default) draws each layer as a column of circles, every "
                "neuron joined to every neuron of the next layer: the textbook's fully "
                "connected network. `blocks` draws each layer as a box in sequence, its "
                "tensor shape beside it, its fill by `type`, with `skips` and `repeats`: a "
                "paper's architecture figure."
            ),
        ),
        FieldSpec(
            "layers",
            "array",
            required=True,
            item_ref="neuralnet-layer",
            min_items=1,
            description=(
                f"The layers, input first, 1 to {NEURALNET_LAYER_MAX} (at least 2 in "
                "`neurons`). Each is joined to the next in the order written."
            ),
        ),
        FieldSpec(
            "skips",
            "array",
            item_ref="neuralnet-skip",
            description=(
                "`blocks` only: connections that jump over layers — ResNet's identity "
                "shortcut, U-Net's copy — each drawn as a line bowed round the layers it "
                "bypasses, into the layer it feeds."
            ),
        ),
        FieldSpec(
            "repeats",
            "array",
            item_ref="neuralnet-repeat",
            description=(
                "`blocks` only: runs of layers stacked several times, each drawn once inside "
                "a frame marked with how many times it stacks — the Transformer's `Nx`. Two "
                "repeats never overlap, and a skip is inside a repeat or outside it, never "
                "across its frame."
            ),
        ),
        FieldSpec(
            "direction",
            "string",
            enum=NEURALNET_DIRECTIONS,
            description=(
                "`blocks` only: which way the layers run — `right` (across the page), `down` "
                "or `up` (the Transformer's bottom-to-top). Left out, across, and down when "
                "across does not fit."
            ),
        ),
    ),
    PERT_KINDS: (
        FieldSpec(
            "activities",
            "array",
            required=True,
            item_ref="pert-activity",
            min_items=2,
            description=(
                "The activities, 2 to 20, each an `id`, its `text`, a `duration` (or three PERT "
                "estimates) and the activities it comes `after`. Ranked left to right by those "
                "dependencies; every start, finish and float is computed, so none is written."
            ),
        ),
        FieldSpec(
            "unit",
            "string",
            description=(
                "What the durations are in — `days`, `weeks` — written in the key under the "
                "network. The numbers count from 0, the start of the project."
            ),
        ),
        FieldSpec(
            "start",
            "string",
            description=(
                "A start milestone's words, `Start`: a node before every activity with no "
                "`after`, so the network begins at one point. Left out, none is drawn."
            ),
        ),
        FieldSpec(
            "finish",
            "string",
            description=(
                "A finish milestone's words, `Finish`: a node after every activity nothing "
                "waits for, carrying the project's duration. Left out, none is drawn."
            ),
        ),
    ),
    MINDMAP_KINDS: (
        FieldSpec(
            "centre",
            "string",
            required=True,
            description=(
                "The topic: the one strongly boxed element, in the middle of the map. "
                "Every main branch is a peer round it."
            ),
        ),
        FieldSpec(
            "branches",
            "array",
            required=True,
            item_ref="mindmap-branch",
            min_items=2,
            description=(
                "The main branches, 2 to 8, placed clockwise from the top right in the order "
                "written and split between the two sides so they balance: the first is "
                "always on the right. Nested, up to three levels, 30 branches in all; the "
                "nesting is the structure, so there are no edges."
            ),
        ),
    ),
    PIE_KINDS: (
        FieldSpec(
            "parts",
            "array",
            required=True,
            item_ref="pie-part",
            min_items=2,
            description=(
                "The parts of one total, 2 to 8, clockwise from twelve o'clock in the order "
                "written (a `note` part last), each labelled with its `text` and amount — "
                "inside its sector, or beside it on a leader line."
            ),
        ),
        FieldSpec(
            "unit",
            "string",
            description=(
                "What the amounts are in — `pupils`, `£m`, `%` — written after each one. "
                "With `%` the amounts must add up to 100, within one point of rounding."
            ),
        ),
        FieldSpec(
            "values",
            "boolean",
            description="`false` leaves the amounts out and writes the names alone.",
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

"""The parsed document: its dataclasses and the `Violation` a check reports."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from drawspec.filetree import Entry
from drawspec.schema._constants import (
    ARGUMENT_KINDS,
    AUTOMATON_KINDS,
    BARMODEL_KINDS,
    BOARD_KINDS,
    CHART_KINDS,
    CLOCK_KINDS,
    DOCUMENT_VERSION,
    ENTITIES_KINDS,
    FAMILYTREE_KINDS,
    FIELD_PLACEHOLDERS,
    FILES_KINDS,
    FISHBONE_KINDS,
    GANTT_KINDS,
    GITGRAPH_KINDS,
    GRAPH_KINDS,
    GRID_KINDS,
    JOURNEY_KINDS,
    LANES_KINDS,
    METER_KINDS,
    MINDMAP_KINDS,
    NETWORK_KINDS,
    NEURALNET_KINDS,
    NUMBERLINE_KINDS,
    PACKET_KINDS,
    PERT_KINDS,
    PIE_KINDS,
    RAG_KINDS,
    RAILROAD_KINDS,
    SANKEY_KINDS,
    SEQUENCE_KINDS,
    SHAPE_KINDS,
    STATES_KINDS,
    SUNBURST_KINDS,
    TIMING_KINDS,
    TREEMAP_KINDS,
    USECASE_KINDS,
    VENN_KINDS,
    WARDLEY_KINDS,
    WATERFALL_KINDS,
)


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

    klass: str = ""
    """The `id` of the class this box belongs to (the document's `class` field;
    `class` is a Python keyword), or empty."""

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
    polarity: str = ""
    """A causal link's sign, `+` or `-`, or empty: only on a `flow`."""
    delay: bool = False
    """Whether the link's effect takes time: only on a `flow`."""


@dataclass(frozen=True)
class CausalLoop:
    """One named feedback loop of a causal loop diagram: its variables, in order."""

    text: str
    nodes: tuple[str, ...]
    type: str = ""


@dataclass(frozen=True)
class Group:
    id: str
    members: tuple[str, ...]
    text: str = ""
    initial: str = ""
    """For a composite state: the member it is entered at, or empty."""

    region: bool = False
    """For a composite state's orthogonal region: drawn with no frame of its own,
    divided from its sibling regions by a dashed line. Its composite's members
    are its regions, and nothing else."""


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
    centre: bool = False
    """Whether the rest are arranged round this one, a star schema's fact table."""


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
class TaskEvent:
    """A moment on a `gantt` task's own row: a delivery, a release, a review."""

    at: float
    text: str = ""


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
    done: float | None = None
    """How much is complete, 0 to 100, or `None` for a plan that does not say."""

    events: tuple[TaskEvent, ...] = ()
    """Moments on the task's own row, in the order written."""

    iterations: tuple[tuple[float, float], ...] = ()
    """Each cycle's start and end, in the order written."""

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
    """One row across every column: a `board`'s release, or a `journey`'s detail row."""

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
class VennSet:
    """One set of a `venn`: a circle, its name drawn outside it."""

    id: str
    text: str
    role: str = "step"


@dataclass(frozen=True)
class Region:
    """One region of a `venn`, named by exactly the sets it is in."""

    members: tuple[str, ...]
    text: str
    role: str = "step"


@dataclass(frozen=True)
class Detail:
    """What one stage of a `journey` holds in one detail row."""

    row: str
    text: str


@dataclass(frozen=True)
class JourneyStage:
    """One stage of a `journey`: a column, its feeling by name, and its details."""

    text: str
    feeling: str
    role: str = "step"
    details: tuple[Detail, ...] = ()


@dataclass(frozen=True)
class TreemapPart:
    """One part of a `treemap`: a rectangle with an area in proportion to its amount."""

    text: str
    amount: float
    group: str = ""
    role: str = "step"


@dataclass(frozen=True)
class SankeyNode:
    """One node of a `sankey`: a bar as tall as what passes through it."""

    id: str
    text: str
    role: str = "step"


@dataclass(frozen=True)
class SankeyFlow:
    """One flow of a `sankey`: a band from one node to another, as thick as its amount."""

    source: str
    target: str
    amount: float
    role: str = "flow"


@dataclass(frozen=True)
class NumberAxis:
    """A `numberline`'s scale: from `minimum` to `maximum`, numbered or named at its ends."""

    minimum: float
    maximum: float
    step: float | None = None
    label: str = ""
    unit: str = ""
    ends: tuple[str, ...] = ()
    """The low and the high end's words, for a named scale. Empty for a numbered one."""


@dataclass(frozen=True)
class NumberPoint:
    """One point of a `numberline`: a dot on the axis, filled or hollow."""

    at: float
    text: str = ""
    open: bool = False
    role: str = "step"


@dataclass(frozen=True)
class NumberRange:
    """One range of a `numberline`: a stretch of the scale in its own track.

    A missing end (`None`) is unbounded: the range runs on past the axis.
    """

    start: float | None = None
    end: float | None = None
    start_open: bool = False
    end_open: bool = False
    text: str = ""
    role: str = "step"


@dataclass(frozen=True)
class ModelPart:
    """One part of a bar model's bar: a stretch as long as its amount, or equal units."""

    amount: float | None = None
    units: int | None = None
    text: str = ""
    id: str = ""
    role: str = "step"


@dataclass(frozen=True)
class ModelBar:
    """One bar of a `barmodel`: its parts left to right, and its name."""

    parts: tuple[ModelPart, ...]
    text: str = ""
    id: str = ""


@dataclass(frozen=True)
class ModelBrace:
    """One brace of a `barmodel`, over side-by-side parts or consecutive bars."""

    over: tuple[str, ...]
    amount: float | None = None
    text: str = ""


@dataclass(frozen=True)
class WaterfallBar:
    """One bar of a `waterfall`: a total standing on zero, or a signed step."""

    text: str
    total: float | None = None
    amount: float | None = None
    role: str = "step"


@dataclass(frozen=True)
class ClockFace:
    """One clock face: the time its hands show, if any, a text, and a time since."""

    time: str = ""
    text: str = ""
    since: str = ""


@dataclass(frozen=True)
class RagRow:
    """One row of a RAG report: a name, its rating, and optionally a trend and a note."""

    text: str
    rag: str
    trend: str = ""
    note: str = ""


@dataclass(frozen=True)
class MeterBand:
    """One named stretch of a meter's scale, from the band before it to `to`."""

    text: str
    to: float


@dataclass(frozen=True)
class Meter:
    """One meter: an amount against its scale, with a target and bands if given."""

    text: str
    amount: float
    max: float
    min: float = 0.0
    unit: str = ""
    target: float | None = None
    bands: tuple[MeterBand, ...] = ()
    role: str = "step"


@dataclass(frozen=True)
class FamilyPerson:
    """One person in a `familytree`."""

    id: str
    sex: str
    gender: str = ""
    text: str = ""
    status: str = "unaffected"
    deceased: bool = False
    proband: bool = False
    consultand: bool = False
    adopted: bool = False
    pregnancy: str = ""
    role: str = "step"


@dataclass(frozen=True)
class FamilyTwins:
    """Children of one birth, in birth order."""

    of: tuple[str, ...]
    zygosity: str


@dataclass(frozen=True)
class FamilyCouple:
    """Two partners and their children, in birth order."""

    between: tuple[str, str]
    children: tuple[str, ...] = ()
    twins: tuple[FamilyTwins, ...] = ()
    separated: bool = False
    consanguineous: bool = False


@dataclass(frozen=True)
class ArgumentPoint:
    """One point of an `argument`: a box bearing for or against another."""

    id: str
    text: str
    on: str
    stance: str
    with_: tuple[str, ...] = ()
    """Its co-premises as written on it; the group is every point joined this way."""

    role: str = "step"


@dataclass(frozen=True)
class MindmapBranch:
    """One branch of a `mindmap`, with the branches off it, in the order written."""

    text: str
    role: str = "step"
    branches: tuple[MindmapBranch, ...] = ()


@dataclass(frozen=True)
class NetworkSegment:
    """One network of a `network` diagram: a bus, its name and its address."""

    id: str
    text: str
    address: str = ""


@dataclass(frozen=True)
class NetworkHost:
    """One host of a `network` diagram, and the networks it is on, in network order."""

    id: str
    text: str
    role: str = "step"
    networks: tuple[str, ...] = ()
    addresses: tuple[str, ...] = ()
    """The host's address on each of its `networks`, in the same order; may be empty."""


@dataclass(frozen=True)
class NetworkGroup:
    """A set of hosts drawn on one shaded backdrop."""

    text: str
    members: tuple[str, ...]


@dataclass(frozen=True)
class TimingSignal:
    """One lane of a `timing` figure: a name, what it draws, and a value per step."""

    text: str
    lane: str = "bit"
    values: tuple[str, ...] = ()
    states: tuple[str, ...] = ()
    group: str = ""


@dataclass(frozen=True)
class TimingMarker:
    """A vertical line across a `timing` figure at an edge, with its name."""

    at: float
    text: str = ""


@dataclass(frozen=True)
class TimingInterval:
    """A named span between two edges, drawn as an arrow under a signal's lane."""

    start: float
    end: float
    text: str
    signal: str = ""


@dataclass(frozen=True)
class UsecaseActor:
    """One actor of a `usecase` diagram: a stick figure outside every boundary."""

    id: str
    text: str
    supporting: bool | None = None
    """Written or left out (`None`); `usecase_sides` derives the side either way."""


@dataclass(frozen=True)
class UseCase:
    """One use case: an ellipse inside its system's boundary, if there is one."""

    id: str
    text: str
    system: str = ""


@dataclass(frozen=True)
class UsecaseSystem:
    """One system boundary: a frame round its use cases, its name in the corner."""

    id: str
    text: str


@dataclass(frozen=True)
class UsecaseEdge:
    """One relation of a `usecase` diagram, as written."""

    source: str
    target: str
    role: str = "association"


@dataclass(frozen=True)
class PacketField:
    """One bit field of a `packet`, in reading order: its name and its width."""

    bits: int
    text: str = ""
    short: str = ""
    holds: str = ""
    note: str = ""
    role: str = "field"


@dataclass(frozen=True)
class PertActivity:
    """One activity of a `pert` network: its words, how long it takes, what it waits for."""

    id: str
    text: str
    duration: Fraction
    """The duration the schedule is computed from: as written, or the PERT expected
    duration of the three estimates. Exact, so a float of zero is zero."""

    after: tuple[str, ...] = ()
    estimates: tuple[Fraction, Fraction, Fraction] | None = None
    """The optimistic, likely and pessimistic estimates, when the author wrote them."""


@dataclass(frozen=True)
class NeuralLayer:
    """One layer of a `neuralnet`: its handle, its name, and its style's fields."""

    id: str = ""
    text: str = ""
    size: int = 0
    """How many neurons a `neurons` layer holds, or 0 in `blocks`."""

    labels: tuple[str, ...] = ()
    bias: bool = False
    type: str = ""
    """A `blocks` layer's sort — `conv` — which decides its fill, or empty."""

    shape: str = ""
    """A `blocks` layer's output tensor, as written, or empty."""

    branches: tuple[tuple[NeuralLayer, ...], ...] = ()
    """A set of branches' towers, each its layers in order; empty for a layer."""


@dataclass(frozen=True)
class NeuralSpan:
    """A run of a `neuralnet`'s layers, `from` to `to`: a skip, or a repeated block."""

    source: str
    target: str
    text: str = ""
    times: int = 0
    """How many times a repeated block is stacked; 0 for a skip."""


@dataclass(frozen=True)
class AutomatonState:
    """One state of an `automaton`: its handle, the name drawn in it, a Moore output."""

    id: str
    text: str
    """The name in the circle: as written, or the id."""

    output: str = ""


@dataclass(frozen=True)
class AutomatonTransition:
    """One move of an `automaton`: from, to, the symbol it reads (empty for ε)."""

    source: str
    target: str
    symbol: str = ""
    epsilon: bool = False
    output: str = ""
    """A Mealy machine's output on this move, or empty."""


@dataclass(frozen=True)
class SunburstNode:
    """One sector of a `sunburst`, with the sectors nested inside it, in order."""

    text: str
    children: tuple[SunburstNode, ...] = ()


@dataclass(frozen=True)
class GitBranch:
    """One branch of a `gitgraph`: a lane, and where it forks from."""

    name: str
    source: str = ""
    """The `from` written: a branch name or a commit id; empty for the default."""
    role: str = "step"


@dataclass(frozen=True)
class GitStep:
    """One step of a `gitgraph`: a commit on a branch, a merge or a cherry-pick."""

    on: str
    text: str = ""
    id: str = ""
    merge: str = ""
    pick: str = ""
    tag: str = ""
    role: str = "step"


@dataclass(frozen=True)
class RailroadItem:
    """One item on a railroad track: a box, a comment, or a combination of items."""

    shape: str
    """One of `RAILROAD_SHAPES`."""

    text: str = ""
    """A box's or a comment's words, exactly as written."""

    items: tuple[RailroadItem, ...] = ()
    """A `seq`'s or a `choice`'s items, in order; the one item an `optional` or a
    `repeat` holds."""

    separator: RailroadItem | None = None
    """A `repeat`'s separator, drawn on its loop."""

    min: int = 1
    """A `repeat`'s least count: 0 or 1."""

    pointer: str = ""
    """Where the item was written, so a refusal at layout time can say."""


@dataclass(frozen=True)
class RailroadRule:
    """One named rule of a `railroad` grammar and what it matches."""

    name: str
    expr: RailroadItem
    pointer: str = ""


@dataclass(frozen=True)
class WardleyAnchor:
    """A user or need a `wardley` map hangs from, and what it needs directly."""

    id: str
    text: str
    needs: tuple[str, ...] = ()


@dataclass(frozen=True)
class WardleyComponent:
    """One component of a `wardley` map: a named stage and what it needs."""

    id: str
    text: str
    evolution: str
    needs: tuple[str, ...] = ()
    depth: int | None = None
    evolves: str = ""
    inertia: bool = False


@dataclass(frozen=True)
class WardleyNote:
    """A numbered note under a `wardley` map, marked on what it is about."""

    text: str
    on: tuple[str, ...] = ()


@dataclass(frozen=True)
class PiePart:
    """One part of a `pie`: a sector whose angle is its share of the total."""

    text: str
    amount: float
    role: str = "step"


@dataclass(frozen=True)
class TreemapGroup:
    """One group of a `treemap`: a captioned frame around the parts that name it."""

    id: str
    text: str


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
class NodeClass:
    """One of a `flow`, `tree` or `lanes` drawing's classes: a fill and a key entry."""

    id: str
    text: str


@dataclass(frozen=True)
class Phase:
    """A named run of a `lanes` diagram's steps, across every lane.

    Not a `Group`: a group is a frame round its members inside one drawing's
    flow, and a phase is the other axis of a swimlane grid — a stretch of the
    process every lane passes through, drawn as a cell of a header band and a
    line across all the lanes.
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
    amount: float | None = None
    """For a `funnel` stage: how many reached it, or `None`."""


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
    ends: tuple[str, ...] = ()
    """A quadrant axis's words for its low and high end, or empty."""


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
    loops: tuple[CausalLoop, ...] = ()
    """A causal loop diagram's named loops, in the order written."""
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
    quadrants: tuple[str, ...] = ()
    """A quadrant's four quarter names, top right first, counter-clockwise."""
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

    phases: tuple[Phase, ...] = ()
    """A `lanes` diagram's phases, in the order the process runs."""

    classes: tuple[NodeClass, ...] = ()
    """A `flow`, `tree` or `lanes` drawing's node classes, in the order declared."""

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

    venn_sets: tuple[VennSet, ...] = ()
    """A `venn`'s sets, in the order written: the circles' order is theirs."""

    regions: tuple[Region, ...] = ()

    feelings: tuple[str, ...] = ()
    """A `journey`'s named levels, worst first."""

    journey_rows: tuple[Slice, ...] = ()
    """A `journey`'s detail rows, top to bottom."""

    journey_stages: tuple[JourneyStage, ...] = ()
    """A `journey`'s stages, left to right."""

    treemap_parts: tuple[TreemapPart, ...] = ()
    """A `treemap`'s parts, in the order written: the tie-breaker between equal amounts."""

    treemap_groups: tuple[TreemapGroup, ...] = ()
    """A `treemap`'s groups, in the order written: the order their fills are taken in."""

    unit: str = ""
    """What a `treemap`'s or a `sankey`'s amounts are in, written after each one."""

    sankey_nodes: tuple[SankeyNode, ...] = ()
    """A `sankey`'s nodes, in the order written: where each column's order starts."""

    sankey_flows: tuple[SankeyFlow, ...] = ()
    """A `sankey`'s flows, in the order written."""

    number_axis: NumberAxis | None = None
    """A `numberline`'s scale."""

    number_points: tuple[NumberPoint, ...] = ()
    """A `numberline`'s points, in the order written."""

    number_ranges: tuple[NumberRange, ...] = ()
    """A `numberline`'s ranges, top track first."""

    model_bars: tuple[ModelBar, ...] = ()
    """A `barmodel`'s bars, top to bottom."""

    model_braces: tuple[ModelBrace, ...] = ()
    """A `barmodel`'s braces, in the order written."""

    waterfall_bars: tuple[WaterfallBar, ...] = ()
    """A `waterfall`'s bars, left to right."""

    waterfall_label: str = ""
    """A `waterfall`'s axis label: what the numbers are, and their unit."""

    pie_parts: tuple[PiePart, ...] = ()
    """A `pie`'s parts, in the order written: clockwise from twelve o'clock."""

    centre: str = ""
    """A `mindmap`'s topic, or a `sunburst`'s optional hub label, drawn in the middle."""

    branches: tuple[MindmapBranch, ...] = ()
    """A `mindmap`'s main branches, in the order written: clockwise from the top right."""

    claim: str = ""
    """An `argument`'s contention, drawn at the top."""

    points: tuple[ArgumentPoint, ...] = ()
    """An `argument`'s points, in the order written."""

    people: tuple[FamilyPerson, ...] = ()
    """A `familytree`'s people, in the order written."""

    couples: tuple[FamilyCouple, ...] = ()
    """A `familytree`'s couples, in the order written: each person's in marriage order."""

    tree_style: str = "boxes"
    """How a `tree` is drawn: `boxes`, or `bracket` (leaves on one edge, square elbows)."""

    bracket_root: str = "right"
    """Which edge a bracket's root stands at: `left`, `right` or `middle`."""

    meter_style: str = "bar"
    """How a `meter` document's meters are drawn: one style for the panel."""

    meters: tuple[Meter, ...] = ()
    """A `meter` document's meters, in reading order."""

    rag_rows: tuple[RagRow, ...] = ()
    """A `rag` document's rows, in the order written."""

    clocks: tuple[ClockFace, ...] = ()
    """A `clock` document's faces, in reading order."""

    clock_numerals: str = "arabic"
    """The numbers round a `clock` document's faces."""

    clock_readout: str = "words"
    """What is written under a `clock` document's faces."""

    sunburst_nodes: tuple[SunburstNode, ...] = ()
    """A `sunburst`'s first ring, in the order written: clockwise from twelve o'clock,
    each node's `children` the ring nested inside it."""

    pert_activities: tuple[PertActivity, ...] = ()
    """A `pert` network's activities, in the order written: the tie-breaker within a rank."""

    pert_start: str = ""
    """A `pert` network's start milestone's words, or empty for none."""

    pert_finish: str = ""
    """A `pert` network's finish milestone's words, or empty for none."""

    automaton_states: tuple[AutomatonState, ...] = ()
    """An `automaton`'s states, in the order written."""

    automaton_transitions: tuple[AutomatonTransition, ...] = ()
    """An `automaton`'s moves, in the order written, one symbol each."""

    automaton_start: str = ""
    """The id of an `automaton`'s start state."""

    automaton_accepting: tuple[str, ...] = ()
    """The ids of an `automaton`'s accepting states."""

    automaton_deterministic: bool = False
    """Whether the author declared the automaton a DFA (checked by validation)."""

    neural_style: str = "neurons"
    """How a `neuralnet` is drawn: `neurons` or `blocks`."""

    neural_layers: tuple[NeuralLayer, ...] = ()
    """A `neuralnet`'s layers, input first."""

    neural_skips: tuple[NeuralSpan, ...] = ()
    """A `blocks` network's skip connections, in the order written."""

    neural_repeats: tuple[NeuralSpan, ...] = ()
    """A `blocks` network's repeated blocks, in the order written."""

    neural_direction: str = ""
    """Which way a `blocks` network runs, or empty to choose: across, else down."""

    packet_fields: tuple[PacketField, ...] = ()
    """A `packet`'s bit fields, in reading order: left to right, row after row."""

    packet_row_bits: int = 32
    """How many bits one row of a `packet` holds."""

    packet_numbering: str = "left"
    """Which end of a `packet`'s rows bit 0 is at."""

    wardley_anchors: tuple[WardleyAnchor, ...] = ()
    """A `wardley` map's users or needs, across the top in the order written."""

    wardley_components: tuple[WardleyComponent, ...] = ()
    """A `wardley` map's components, in the order written."""

    wardley_notes: tuple[WardleyNote, ...] = ()
    """A `wardley` map's numbered notes, numbered in the order written."""

    usecase_actors: tuple[UsecaseActor, ...] = ()
    """A `usecase` diagram's actors, in the order written."""

    usecase_cases: tuple[UseCase, ...] = ()
    """A `usecase` diagram's use cases, in the order written, each with its system."""

    usecase_systems: tuple[UsecaseSystem, ...] = ()
    """A `usecase` diagram's system boundaries, top to bottom."""

    usecase_edges: tuple[UsecaseEdge, ...] = ()
    """A `usecase` diagram's relations, in the order written."""

    railroad_rules: tuple[RailroadRule, ...] = ()
    """A `railroad` grammar's rules, in the order written: drawn top to bottom."""

    railroad_external: tuple[str, ...] = ()
    """Rule names a `railroad` refers to but defines elsewhere."""

    networks: tuple[NetworkSegment, ...] = ()
    """A `network` diagram's buses, top to bottom in the order written."""

    hosts: tuple[NetworkHost, ...] = ()
    """A `network` diagram's hosts, in the order written."""

    host_groups: tuple[NetworkGroup, ...] = ()
    """A `network` diagram's groups, in the order written."""
    timing_signals: tuple[TimingSignal, ...] = ()
    """A `timing` figure's lanes, top to bottom, each a value per step."""

    timing_ticks: tuple[str, ...] = ()
    """A `timing` figure's step names, one per step, or none."""

    timing_markers: tuple[TimingMarker, ...] = ()
    """A `timing` figure's vertical markers, in the order written."""

    timing_intervals: tuple[TimingInterval, ...] = ()
    """A `timing` figure's named intervals, in the order written."""
    git_branches: tuple[GitBranch, ...] = ()
    """A `gitgraph`'s branches, one lane each in the order written."""

    git_steps: tuple[GitStep, ...] = ()
    """A `gitgraph`'s commits, merges and cherry-picks, in the order made."""

    git_direction: str = "right"
    """Which way a `gitgraph`'s time runs: `right` or `down`."""

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
            ("venn", VENN_KINDS),
            ("journey", JOURNEY_KINDS),
            ("treemap", TREEMAP_KINDS),
            ("sankey", SANKEY_KINDS),
            ("numberline", NUMBERLINE_KINDS),
            ("barmodel", BARMODEL_KINDS),
            ("waterfall", WATERFALL_KINDS),
            ("pie", PIE_KINDS),
            ("mindmap", MINDMAP_KINDS),
            ("argument", ARGUMENT_KINDS),
            ("familytree", FAMILYTREE_KINDS),
            ("meter", METER_KINDS),
            ("rag", RAG_KINDS),
            ("clock", CLOCK_KINDS),
            ("sunburst", SUNBURST_KINDS),
            ("packet", PACKET_KINDS),
            ("wardley", WARDLEY_KINDS),
            ("usecase", USECASE_KINDS),
            ("railroad", RAILROAD_KINDS),
            ("network", NETWORK_KINDS),
            ("timing", TIMING_KINDS),
            ("gitgraph", GITGRAPH_KINDS),
            ("pert", PERT_KINDS),
            ("automaton", AUTOMATON_KINDS),
            ("neuralnet", NEURALNET_KINDS),
        ):
            if self.kind in kinds:
                return name
        raise KeyError(self.kind)


@dataclass(frozen=True)
class Violation:
    """One validation failure, located by JSON pointer."""

    pointer: str
    message: str

    def __str__(self) -> str:
        return f"{self.pointer or '/'}: {self.message}"

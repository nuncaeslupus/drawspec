"""Vocabularies, limits and published constants shared by the document format."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from drawspec.theme import EDGE_ROLES, NODE_ROLES

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


#: The node roles that draw a flowchart symbol — a parallelogram for data in or
#: out, a doubled-sided box for a process defined elsewhere, a drum for where data
#: rests — and the C4 `person`, a human as against a system. Named only where a box
#: is a step of a process: a `flow`, a `tree` and a `lanes` node. Every other kind's
#: roles are fixed by what it draws.
SHAPED_ROLES: Final = ("io", "subroutine", "store", "person")


#: The node roles everywhere else a kind takes the general vocabulary.
PLAIN_NODE_ROLES: Final = tuple(role for role in NODE_ROLES if role not in SHAPED_ROLES)


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
#: and `group` because neither is a condition the machine can be in. `fork` and
#: `join` are UML's bar pseudo-states (#107): drawn as a short thick bar with no
#: words, one way in and several out into the regions of one composite (a fork),
#: or the reverse (a join). See `STATE_BARS`.
STATE_ROLES: Final = ("step", "emphasis", "terminal", "fork", "join")


#: The state roles that are bars, not boxes: a pseudo-state the machine passes
#: through at once, so it has no words, no event to wait for, and a fixed shape.
STATE_BARS: Final = ("fork", "join")


#: The most orthogonal regions one composite state may hold (owner, kind audit
#: question 4). UML textbooks draw two or three; past four, side by side or
#: stacked, each region is too small to hold a machine of its own.
STATES_REGION_MAX: Final = 4


#: The roles a transition may take: the default, the happy path drawn heavier,
#: and a rare or error path drawn dashed. `owns`, `link`, `exchange` and `aside`
#: are not transitions — a transition has one direction and goes somewhere.
TRANSITION_ROLES: Final = ("flow", "strong", "weak")


#: Messages between participants, in order. A layout family of its own: the
#: participants are columns in the order written, the messages rows in the order
#: written, and nothing is ranked — the order *is* the diagram.
SEQUENCE_KINDS: Final = ("sequence",)


#: The roles a participant may take: a box, the box the diagram is about, an
#: outside system drawn as words with no box, and `actor`, a person drawn as the
#: UML stick figure with the name under it. `decision`, `start`, `terminal` and
#: `group` promise a shape a lifeline's head does not have.
PARTICIPANT_ROLES: Final = ("step", "emphasis", "note", "actor")


#: The roles a message may take: a call (`flow`), a reply (`weak`, dashed with an
#: open head, which is what UML draws for one), and the exchange that matters
#: (`strong`). Every one has a head, because a message has a direction: `aside`,
#: `link`, `exchange` and `owns` are refused. A signal nobody answers is a `flow`
#: with no reply, and is drawn with no activation bar; `async` says so outright,
#: a solid line with an open head (UML's asynchronous message), and awaits no
#: reply, so a `weak` message answering one is refused.
MESSAGE_ROLES: Final = ("flow", "weak", "strong", "async")


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


#: The most node classes one `flow`, `tree` or `lanes` drawing may declare. Each
#: class is a faint fill a reader matches against a key under the drawing; past
#: four the fills stop being told apart at a glance, and the key is a table. One
#: is enough (owner): a C4 context greys only its external systems, and the key
#: still names what the grey means.
CLASSES_MAX: Final = 4


#: The roles a classed node may not take: a `note` has no outline to fill (it is
#: "not the content"), and a `group` is a container, not a box of a class.
UNCLASSED_ROLES: Final = ("note", "group")


#: The most phases one swimlane diagram names across its lanes: past six the
#: header band is a table of contents, and the cells too narrow for their names.
LANES_PHASES_MAX: Final = 6


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


#: Venn diagrams: two to four overlapping sets, each region named by which sets
#: it is in. With two or three circles, or four ellipses, every region is fixed
#: by its membership, so nothing about the drawing needs a coordinate. A layout
#: family of its own.
VENN_KINDS: Final = ("venn",)


#: A causal link's sign: more of the source means more (`+`) or less (`-`) of the
#: target. Only on a `flow`.
POLARITIES: Final = ("+", "-")


#: The edge roles a sign may go on: a link that says *this drives that*. `link`,
#: `aside` and `weak` have no causal direction, and the others mean other things.
POLARITY_EDGE_ROLES: Final = ("flow", "strong")


#: What a loop's type may be written as; it is checked against the signs.
LOOP_TYPES: Final = ("reinforcing", "balancing")


#: The most loops one causal loop diagram names (its readability budget).
LOOP_MAX: Final = 6


#: The most sets a `venn` draws: four, as four ellipses — the only arrangement in
#: common use that shows every one of the fifteen regions.
VENN_SET_MAX: Final = 4


#: With four sets the smallest regions are small: a region's words are a count or
#: a word or two, at most this many characters (the corpus's research figures put
#: a number in each region; the ikigai figure a single word).
VENN_FOUR_TEXT_MAX: Final = 12


#: The roles a set's circle may take: the default, and the set the diagram is
#: about, drawn with a heavier outline.
VENN_SET_ROLES: Final = ("step", "emphasis")


#: The roles a region may take: the default, and the region the diagram is
#: about — its words bold and the region filled with the theme's first mark fill.
REGION_ROLES: Final = ("step", "emphasis")


#: Journey maps: one person's feeling across the stages of an experience, a named
#: level per stage, set against what they do there. The feeling is ordinal and
#: named — there is no number to read off the line. A layout family of its own.
JOURNEY_KINDS: Final = ("journey",)


#: The roles a stage may take: the default, and the stage the map is about —
#: usually the trough — its column framed and its point drawn larger and solid.
JOURNEY_STAGE_ROLES: Final = ("step", "emphasis")


#: The most stages, feeling levels and detail rows a journey holds. Past seven
#: stages the columns are too narrow to read; past five levels two neighbours
#: cannot be told apart; past four rows the map is a table with a line on it.
JOURNEY_STAGE_MAX: Final = 7


JOURNEY_FEELING_MAX: Final = 5


JOURNEY_ROW_MAX: Final = 4


#: Treemaps: one total split into a few parts, each drawn with an area in
#: proportion to its value and labelled inside itself. A small set of proportions
#: the author already knows, stated — not data to explore. A layout family of its
#: own.
TREEMAP_KINDS: Final = ("treemap",)


#: The roles a part may take: the default; the part the diagram is about (not
#: automatically the largest), outlined heavier with its words bold; and the
#: remainder, a light dashed outline laid out after the others.
TREEMAP_PART_ROLES: Final = ("step", "emphasis", "note")


#: The most parts and groups a treemap holds. Past ten parts the smallest are
#: slivers no label fits, and the drawing is a disk-usage tool's output; past four
#: groups the frames crowd out the parts they hold.
TREEMAP_PART_MAX: Final = 10


TREEMAP_GROUP_MAX: Final = 4


#: Sankey diagrams: where a known quantity goes — nodes in columns, joined by
#: bands whose thickness is in proportion to the amount that flows. A small set
#: of known flows, stated — not data to explore. A layout family of its own.
SANKEY_KINDS: Final = ("sankey",)


#: The roles a node may take: the default; the node the diagram is about, its
#: bar outlined heavier and its words bold; and the remainder (`lost`, `idle`),
#: drawn lighter along with the bands that reach it.
SANKEY_NODE_ROLES: Final = ("step", "emphasis", "note")


#: The roles a flow may take: the default band, and the path the diagram is
#: about, drawn darker.
SANKEY_FLOW_ROLES: Final = ("flow", "strong")


#: The most nodes, flows and columns a sankey holds. Past fourteen nodes or four
#: columns the bands are a tangle, not a picture of where something goes.
SANKEY_NODE_MAX: Final = 14


SANKEY_FLOW_MAX: Final = 24


SANKEY_COLUMN_MAX: Final = 4


#: The thickness, in units of the body size over eleven, of the fullest column's
#: bands, and the thinnest band drawn. The scale is one factor for the whole
#: drawing, so a flow under `SANKEY_MIN_BAND / SANKEY_BAND` of the fullest
#: column's total is a hairline — refused while validating, not after a layout.
SANKEY_BAND: Final = 240.0


SANKEY_MIN_BAND: Final = 2.0


#: Number lines: values and ranges on one scale — an inequality, a spectrum, the
#: pH scale, a tense relative to *now*. One axis, numbers the author already
#: knows, and nothing placed by hand. A layout family of its own.
NUMBERLINE_KINDS: Final = ("numberline",)


#: The roles a point or a range may take: the default; the one the drawing is
#: about, drawn heavier with its words bold; and a context mark, drawn lighter.
NUMBERLINE_ROLES: Final = ("step", "emphasis", "note")


#: The most points and ranges a number line holds. Points: the pH scale with a
#: substance at every whole value is fifteen, the largest real figure found
#: (`docs/research/corpus-round2.md`, N4 and N5). Ranges: no figure stacks more than
#: two; past four tracks the drawing is a table of intervals.
NUMBERLINE_POINT_MAX: Final = 15


NUMBERLINE_RANGE_MAX: Final = 4


#: Bar models (tape diagrams): a word problem drawn as bars split into parts,
#: every length in proportion, with braces saying what a stretch adds up to. A
#: layout family of its own — rectangles in a row, placed by arithmetic.
BARMODEL_KINDS: Final = ("barmodel",)


#: The roles a part may take: the default; the part the problem asks about, bold
#: and filled; and a part that is not there — a difference — drawn dashed.
BARMODEL_PART_ROLES: Final = ("step", "emphasis", "note")


#: The most bars, parts per bar, unit boxes per bar and braces a bar model holds.
#: The corpus (B1 to B4) draws one to three bars of two to eight parts; past twelve
#: unit boxes a reader counts instead of seeing a ratio.
BARMODEL_BAR_MAX: Final = 3


BARMODEL_PART_MAX: Final = 8


BARMODEL_UNIT_MAX: Final = 12


BARMODEL_BRACE_MAX: Final = 6


#: Waterfalls (bridge charts): from one total to another, step by step — every
#: step a bar floating on the running sum, subtotals checked against it. A
#: layout family of its own, sharing the chart kind's ticks.
WATERFALL_KINDS: Final = ("waterfall",)


#: The roles a bar may take: the default, and the step the chart is about.
WATERFALL_ROLES: Final = ("step", "emphasis")


#: The most bars a waterfall holds. The corpus (W1 to W4) draws five to ten; past
#: twelve the names under the bars are too narrow to read at the canvas width.
WATERFALL_BAR_MAX: Final = 12


#: Pie charts: the shares of one known total as sectors of a circle, every
#: sector labelled. A few proportions stated, as on a treemap — not data to
#: explore. A layout family of its own.
PIE_KINDS: Final = ("pie",)


#: The roles a part may take: the default; the part the chart is about, outlined
#: heavier with its words bold; and the remainder, unfilled and dashed, drawn last.
PIE_ROLES: Final = ("step", "emphasis", "note")


#: The most parts a pie holds. The corpus's school pies have three to six, its
#: budget pies eight to fifteen; past eight the smallest are slivers no one
#: compares, so the rest go into one `note` part.
PIE_PART_MAX: Final = 8


#: The smallest share of the total a part may be. Under it a sector is a sliver
#: whose angle cannot be read.
PIE_SHARE_MIN: Final = 0.02


#: How far percentages may add up to from 100 and still be read as rounding.
PIE_PERCENT_TOLERANCE: Final = 1.0


#: Mind maps: one topic in the middle, its branches radiating to both sides,
#: nested up to three levels. The structure is the nesting, so there are no
#: edges. A layout family of its own.
MINDMAP_KINDS: Final = ("mindmap",)


#: The roles a branch may take: the default; the branch the map is about (bold,
#: its line heavy all the way from the centre); and context, not content (faint,
#: and so is everything under it).
MINDMAP_ROLES: Final = ("step", "emphasis", "note")


#: The most main branches round the centre, branches in all, and levels below
#: the centre. Owner-approved from the corpus (M1-M5): study-skills maps have a
#: handful of main branches and never more than three levels (branch, twig,
#: node); real maps run to 20-40 entries, and a mind map's leaves are phrases on
#: a line, not boxes, so thirty fit where a `tree` stops at fifteen.
MINDMAP_BRANCH_MAX: Final = 8


MINDMAP_NODE_MAX: Final = 30


MINDMAP_DEPTH_MAX: Final = 3


#: Argument maps: one claim at the top, the points for and against it below, and
#: the points for and against those. A layout family of its own.
ARGUMENT_KINDS: Final = ("argument",)


#: Which way a point bears on the box it is `on`. A rebuttal is an `against` on an
#: `against`: its name follows from the depth, so there is no third stance.
ARGUMENT_STANCES: Final = ("for", "against")


#: The roles a point may take: the default; the decisive point; and evidence or a
#: source rather than a reason (the corpus's "basis" boxes).
ARGUMENT_ROLES: Final = ("step", "emphasis", "note")


#: The most points, the deepest chain below the claim, and the most co-premises
#: in one group. The corpus (A1-A5) draws about a dozen boxes, three deep; past
#: fifteen and four levels the map is split, one map per contested reason.
ARGUMENT_POINT_MAX: Final = 15


ARGUMENT_DEPTH_MAX: Final = 4


ARGUMENT_GROUP_MAX: Final = 4


#: Family trees (pedigrees, in genetics and medicine): people, the couples they
#: form and the children of each couple, a generation to a row. A layout family
#: of its own: a child hangs from a couple, not a person, and partners share a row.
FAMILYTREE_KINDS: Final = ("familytree",)


#: What a person's symbol is: square, circle or diamond. Under the 2022 revision
#: of the standard nomenclature the shape shows gender when `gender` is written,
#: and `sex` becomes the note under it; without `gender` it is the shape.
FAMILYTREE_SEXES: Final = ("male", "female", "unknown")


FAMILYTREE_GENDERS: Final = ("man", "woman", "nonbinary")


#: The one trait a family tree tracks: shaded in full, the theme's carrier mark,
#: or empty. A tree of two conditions is two trees.
FAMILYTREE_STATUSES: Final = ("affected", "carrier", "unaffected")


#: A pregnancy, drawn in the symbol (`P`), or a pregnancy loss: a small triangle.
FAMILYTREE_PREGNANCIES: Final = ("ongoing", "loss")


#: Twins come from one point on the sibship line; identical twins have a bar
#: between their two lines, and twins of unknown zygosity a `?`.
FAMILYTREE_ZYGOSITIES: Final = ("monozygotic", "dizygotic", "unknown")


#: The roles a person may take: the default, and the person the figure is about.
FAMILYTREE_ROLES: Final = ("step", "emphasis")


#: The most people; the most generations; the most partners one person may have
#: (Henry VIII's six, the corpus's F1); and the most children of one birth. The
#: clinical and exam pedigrees of the corpus (F5, F7) hold ten to twenty people in
#: three generations; a royal tree (F4) about thirty in four.
FAMILYTREE_PEOPLE_MAX: Final = 30


FAMILYTREE_GENERATION_MAX: Final = 4


FAMILYTREE_PARTNER_MAX: Final = 6


FAMILYTREE_TWIN_MAX: Final = 3


#: Meters: one amount against its scale — a progress bar, a fundraising
#: thermometer, a dial, a bullet graph — alone or a few to a panel. A layout
#: family of its own; every reading is placed by arithmetic.
METER_KINDS: Final = ("meter",)


#: How the meters of a document are drawn: one style for the whole panel, so
#: like is compared with like. `bar` is the default.
METER_STYLES: Final = ("bar", "thermometer", "dial", "bullet")


#: The styles whose meters may start above zero. A bar's length is its amount,
#: so only a needle, which encodes a position rather than a length, may.
METER_MIN_STYLES: Final = ("dial",)


#: The styles that take `bands`: required on a bullet, optional on a dial.
METER_BAND_STYLES: Final = ("dial", "bullet")


#: The roles a meter may take: the default, and the meter the panel is about.
METER_ROLES: Final = ("step", "emphasis")


#: The most meters to a panel and bands to a meter. The corpus (G4, G9) stacks a
#: handful of meters; the bullet graph's specification (G8) allows two to five
#: ranges, and past five neighbouring tones blur.
METER_MAX: Final = 6


METER_BAND_MIN: Final = 2


METER_BAND_MAX: Final = 5


#: The units written before the number rather than after it.
METER_CURRENCIES: Final = ("£", "$", "€", "¥")


#: RAG status reports: workstreams or risks, one row each, rated red, amber or
#: green, with a direction of travel and a note. A layout family of its own: rows
#: set one under another, every column lined up.
RAG_KINDS: Final = ("rag",)


#: The three ratings, worst first. Boards settle on three (corpus R3); the theme
#: says the word, the shape and the colour each is drawn with.
RAG_VALUES: Final = ("red", "amber", "green")


#: The direction of travel since the last report, said as what it means: an arrow
#: up means *improving* in one report and *risk rising* in another (R2, R5).
RAG_TRENDS: Final = ("better", "same", "worse")


#: The most rows to one report: the largest register in the corpus has 13 (R4).
RAG_ROW_MAX: Final = 15


#: Clock faces: an analogue clock showing a time, for teaching it — alone, a few
#: in a row, or a worksheet of them. A layout family of its own; each hand is
#: placed by arithmetic from the time.
CLOCK_KINDS: Final = ("clock",)


#: The numbers round a face: all twelve, Roman I-XII, only 12, 3, 6 and 9, or none.
CLOCK_NUMERALS: Final = ("arabic", "roman", "quarters", "none")


#: What is written under each face: the time in words, in digits, both, or
#: nothing (a worksheet, whose answers are the pupil's).
CLOCK_READOUTS: Final = ("words", "digits", "both", "none")


#: The most faces to a sheet: a worksheet holds a dozen (corpus C4).
CLOCK_MAX: Final = 12


#: How long before a face's time its `since` may be, in minutes: past twelve
#: hours the hour hand has gone all the way round and the sweep says nothing.
CLOCK_SINCE_MAX: Final = 12 * 60


#: Sunburst wheels: a hierarchy drawn as concentric rings of sectors, each label
#: read from the middle outward. A layout family of its own; every sector's angle
#: is its share of the circle, computed from the tree — a terminal node gets an
#: equal slice and a parent spans its descendants.
SUNBURST_KINDS: Final = ("sunburst",)


#: The most rings (levels of nodes). Three keeps the outer labels readable; a
#: fourth is refused, with the hint to fold detail into fewer rings.
SUNBURST_DEPTH_MAX: Final = 3


#: The most nodes in the first ring. Past eight the central wedges are too narrow
#: for a word read outward.
SUNBURST_RING_MAX: Final = 8


#: The most nodes in all rings together. A full feelings-wheel is ~130 terms and
#: reads cleanly on a wide enough canvas; past this a wheel is searched, not read,
#: and anything the type cannot hold at the legible floor is refused by fit first.
SUNBURST_NODE_MAX: Final = 150


#: Packet diagrams: a protocol header or a hardware register as bit fields laid
#: out in rows of a fixed width, a bit ruler over them. A layout family of its own:
#: a field's place is the sum of the widths written before it, never a position.
PACKET_KINDS: Final = ("packet",)


#: The row widths a packet may be drawn at, in bits. A word of a protocol header is
#: 32 bits; a register is 8, 16, 32 or 64. Nothing else lines up with a byte.
PACKET_ROW_BITS: Final = (8, 16, 32, 64)


#: The row width when none is written: the RFC header's 32-bit word.
PACKET_ROW_DEFAULT: Final = 32


#: Which end of a row bit 0 is at. `left` is the RFC convention (bit 0 is the first
#: bit sent, at the left of each 32-bit word); `right` is a datasheet register's
#: (the highest bit at the left, bit 0 at the right).
PACKET_NUMBERINGS: Final = ("left", "right")


#: What a field may be: an ordinary field, a reserved one (hatched), or the one or
#: two the diagram is about (heavier, bold).
PACKET_ROLES: Final = ("field", "reserved", "emphasis")


#: The most fields in one packet. A TCP header with every flag is eighteen; past
#: forty a register map is searched, not read.
PACKET_FIELD_MAX: Final = 40


#: The most rows one packet may run to. Sixteen 32-bit words is a 64-byte header,
#: longer than any header a reader takes in at once.
PACKET_ROW_MAX: Final = 16


#: Network diagrams in the nwdiag style: networks as horizontal buses in the order
#: written, hosts as boxes in columns, each dropping a line to every bus it is on.
#: A layout family of its own; the column order is derived (`drawspec.buses`).
NETWORK_KINDS: Final = ("network",)


#: The most networks (buses). Past six the hosts between them are a rack drawing.
NETWORK_MAX: Final = 6


#: The most hosts. Past two dozen boxes a network diagram is an inventory: draw an
#: overview with one host per role and a diagram per segment.
NETWORK_HOST_MAX: Final = 24


#: The most groups (shaded backdrops behind hosts).
NETWORK_GROUP_MAX: Final = 6


#: The roles a host may take: the default box (a server, a router, any device),
#: the host the diagram is about, a drum for where data rests (a database, a
#: storage array), and a person for a user's machine or a client. drawspec draws
#: no device icons: a router is a host on two networks, and its name says so.
NETWORK_HOST_ROLES: Final = ("step", "emphasis", "store", "person")


#: Timing diagrams: signals over one shared time axis, a lane each — clock lines,
#: digital levels, buses with labelled values, and named-state lanes (WaveDrom,
#: PlantUML and UML timing diagrams, datasheet SPI and I²C figures). A layout
#: family of its own; time is counted in equal steps, never in coordinates.
TIMING_KINDS: Final = ("timing",)


#: What a lane draws: `bit` levels (high, low, high impedance, unknown, clock
#: pulses), a `bus` of labelled values, or a `state` lane of named states.
TIMING_LANES: Final = ("bit", "bus", "state")


#: The values a `bit` lane takes per step: low, high, high impedance, unknown,
#: a positive pulse (high then low) and a negative one (low then high).
TIMING_BIT_VALUES: Final = ("0", "1", "z", "x", "p", "n")


#: The value that carries the step before it on, unchanged — a clock keeps
#: pulsing, a bus keeps its word, a level holds.
TIMING_HOLD: Final = "."


#: The values a `bus` lane reserves: unknown and high impedance. Every other
#: string is a word on the bus.
TIMING_BUS_RESERVED: Final = ("x", "z")


#: The most signals (lanes). Past twelve a datasheet figure is split by bus.
TIMING_SIGNAL_MAX: Final = 12


#: The most steps on the time axis. Past forty a step is too narrow for a clock
#: pulse to read at the canvas width, and a word on a bus has no room.
TIMING_STEP_MAX: Final = 40


#: The most named states one `state` lane may hold. Past six its levels crowd.
TIMING_STATE_MAX: Final = 6


#: The most vertical markers, and the most measured intervals.
TIMING_MARKER_MAX: Final = 8


TIMING_INTERVAL_MAX: Final = 10


#: Git graphs: commits on branches over time, with the forks, merges, tags and
#: cherry-picks between them. A layout family of its own: one lane per branch,
#: one place in time per step, in the order written — no coordinate is written.
GITGRAPH_KINDS: Final = ("gitgraph",)


#: The two ways time may run: across the page (the default) or down it, with the
#: commit messages in a column beside the lanes, as `git log --graph` sets them.
GITGRAPH_DIRECTIONS: Final = ("right", "down")


#: The roles a branch or a step may take: an ordinary one, or the one the figure is
#: about (heavier; at most two in a document, with everything else that is emphasis).
GITGRAPH_ROLES: Final = ("step", "emphasis")


#: The most branches, so the most lanes. Git-flow, the busiest workflow figure found
#: (nvie 2010), draws five kinds of branch; eight leaves room for a second feature.
GITGRAPH_BRANCH_MAX: Final = 8


#: The most steps (commits, merges and cherry-picks). Across a 640-wide page a step
#: takes a column, so thirty is already the fit limit for short labels.
GITGRAPH_STEP_MAX: Final = 30


#: Railroad (syntax) diagrams: a grammar's named rules, each a track from an entry
#: to an exit through terminals, rule references, choices, bypasses and loops. A
#: layout family of its own; the input is an expression tree per rule and every
#: position is derived from it, a long sequence wrapping onto further lines.
RAILROAD_KINDS: Final = ("railroad",)


#: What an item on a railroad track can be: the four boxes and words, then the
#: four ways of combining items. Every item says exactly one of these.
RAILROAD_BOXES: Final = ("terminal", "rule", "special", "comment")


RAILROAD_COMBINERS: Final = ("seq", "choice", "optional", "repeat")


RAILROAD_SHAPES: Final = RAILROAD_BOXES + RAILROAD_COMBINERS


#: The most rules one document draws, one under another. Past a dozen a grammar
#: is a reference manual, and a figure per group of rules reads better.
RAILROAD_RULE_MAX: Final = 12


#: The most boxes (terminals, rule references, specials, comments) on one rule's
#: track. SQLite's busiest figures carry about forty; past that a rule is factored
#: into named sub-rules, which is what SQLite's own documentation does.
RAILROAD_BOX_MAX: Final = 40


#: The most branches one choice stacks. JSON.org's escape choice has nine.
RAILROAD_BRANCH_MAX: Final = 10


#: How deeply items may nest inside one another. Past this the track is a maze of
#: bypasses; the inner part reads better as a rule of its own.
RAILROAD_DEPTH_MAX: Final = 8


#: Use case diagrams: actors outside a system's boundary, the use cases inside it
#: as ellipses, joined by associations, with «include», «extend» and
#: generalisation between them. A layout family of its own: actors stand on the
#: two sides, use cases are stacked inside the boundaries in derived columns.
USECASE_KINDS: Final = ("usecase",)


#: What a relation in a use case diagram may be. `association` joins an actor to a
#: use case (a solid line, no head); `include` and `extend` join two use cases (a
#: dashed arrow named «include» or «extend»); `inherits` says one actor or use case
#: is a kind of another (a hollow triangle at the general end).
USECASE_EDGE_ROLES: Final = ("association", "include", "extend", "inherits")


#: The theme's edge role each relation is drawn in. `link` is the headless
#: association every graph kind already draws, `weak` the dashed open-headed
#: arrow UML draws a dependency with, `inherits` the class diagram's hollow head.
USECASE_DRAWN_ROLES: Final[Mapping[str, str]] = {
    "association": "link",
    "include": "weak",
    "extend": "weak",
    "inherits": "inherits",
}


#: The most actors, use cases, boundaries and relations one diagram holds. Past
#: these the lines between the sides and the boundary are a net to untangle; the
#: refusal says to draw one diagram per actor or per subsystem.
USECASE_ACTOR_MAX: Final = 8


USECASE_CASE_MAX: Final = 15


USECASE_SYSTEM_MAX: Final = 3


USECASE_EDGE_MAX: Final = 30


#: The most columns of use cases inside one boundary. A use case another includes,
#: extends or specialises stands one column right of it; three columns fill the
#: canvas between two sides of actors.
USECASE_COLUMN_MAX: Final = 3


#: Wardley maps: components placed by how visible they are to a user (down the
#: page, derived from the value chain) and how evolved they are (across it, a
#: named stage). A layout family of its own; no position is ever written.
WARDLEY_KINDS: Final = ("wardley",)


#: The four stages of evolution, left to right, as Wardley names them. A
#: component's `evolution` is one of these, optionally `early` or `late` in it.
WARDLEY_STAGES: Final = ("genesis", "custom", "product", "commodity")


#: Where in its stage a component sits: the first, middle or last third.
WARDLEY_PHASES: Final = ("early", "", "late")


#: Every value `evolution` and `evolves` may take, left to right: twelve named
#: places on the evolution axis, never a number.
WARDLEY_EVOLUTION: Final = tuple(
    f"{phase} {stage}".strip() for stage in WARDLEY_STAGES for phase in WARDLEY_PHASES
)


#: The most components on one map. Wardley's own teaching maps hold a dozen or
#: two; past this the map is a wall of dots, and is split into a map per need.
WARDLEY_COMPONENT_MAX: Final = 24


#: The most anchors (users or needs) across the top.
WARDLEY_ANCHOR_MAX: Final = 3


#: The most numbered notes under a map.
WARDLEY_NOTE_MAX: Final = 6


#: The deepest a value chain may go below its anchors. Past eight rows the
#: chain is a stack of dependencies, not a picture of what is visible.
WARDLEY_DEPTH_MAX: Final = 8


#: Project network diagrams: activities as boxes of their computed times, joined
#: finish-to-start, the critical path drawn heavy (activity on node, the
#: precedence diagram method). Placed by the layered engine like a `flow`; every
#: number in a box — early and late start and finish, float — is drawspec's,
#: computed by a forward and a backward pass, never written.
PERT_KINDS: Final = ("pert",)


#: The most activities one network holds. Textbook exercises run to a dozen or
#: so; past twenty the boxes are searched for rather than read along a path.
PERT_ACTIVITY_MAX: Final = 20


#: The most dependencies (entries in every `after` together). Past this the
#: lines between ranks are a weave, not a network.
PERT_DEPENDENCY_MAX: Final = 32


#: The three estimates of a PERT activity, in the order the formula weighs them
#: (1, 4, 1): its expected duration is (optimistic + 4 x likely + pessimistic) / 6.
PERT_ESTIMATES: Final = ("optimistic", "likely", "pessimistic")


#: Finite automata as the theory-of-computation textbooks draw them: states as
#: circles, accepting ones doubled, the start state entered by an arrow from
#: nowhere, transitions labelled by the symbols they read (DFA, NFA, ε-NFA, and
#: the Mealy and Moore transducers). Placed by the layered engine; the arcs are
#: drawspec's own, curved round the circles they do not belong to.
AUTOMATON_KINDS: Final = ("automaton",)


#: The most states one automaton holds. Textbook figures run to three to eight;
#: past twelve circles the reader traces a word through a maze, not a machine.
AUTOMATON_STATE_MAX: Final = 12


#: The most transitions, counted as written (one per symbol), before merging.
AUTOMATON_TRANSITION_MAX: Final = 36


#: The longest a state's name may be, in characters, its Moore output included.
#: A circle grows with its name, and every circle is drawn the size of the
#: widest: past this the machine wants boxes — a `states` diagram.
AUTOMATON_NAME_MAX: Final = 12


#: What an author may write for the empty move instead of `epsilon: true`, each
#: refused so that ε is never mistaken for a symbol read from the input.
#: Compared case-insensitively (`casefold`), so `Epsilon`, `EPS` and `Λ` are caught too;
#: `ϵ` is the lunate epsilon (U+03F5) some keyboards and LaTeX's `\epsilon` produce.
AUTOMATON_EMPTY_SPELLINGS: Final = ("ε", "ϵ", "λ", "eps", "epsilon", "lambda")


_AUTOMATON_EMPTY: Final = frozenset(word.casefold() for word in AUTOMATON_EMPTY_SPELLINGS)


#: Neural networks in the two notations most figures use: `neurons`, the
#: textbook's fully connected figure (layers as columns of circles, every neuron
#: joined to every neuron of the next layer), and `blocks`, a paper's architecture
#: figure (layers as boxes in sequence with their tensor shapes, skip connections
#: and repeated blocks). One kind, because both say the same thing — the layers of
#: a network in order — and an author moves between them as the network grows.
NEURALNET_KINDS: Final = ("neuralnet",)


#: How a network is drawn. `neurons` is the default: the figure every textbook
#: opens with.
NEURALNET_STYLES: Final = ("neurons", "blocks")


#: Which way a `blocks` network's layers run: across the page (LeNet, AlexNet,
#: PlotNeuralNet), or down or up it (ResNet's stacked blocks; the Transformer reads
#: from the bottom).
NEURALNET_DIRECTIONS: Final = ("right", "down", "up")


#: The most layers one network holds. LeNet-5 is seven, a Transformer encoder
#: drawn whole about eight; past sixteen boxes the network wants an overview of
#: its stages and a figure per stage.
NEURALNET_LAYER_MAX: Final = 16


#: The most neurons a `neurons` layer is drawn whole with. A larger layer is drawn
#: as its first neurons, a column of dots and its last, with its size written
#: under it — Nielsen's 784 input neurons, as every textbook draws them.
NEURALNET_NEURONS_SHOWN: Final = 8


#: The most characters a neuron's label holds: `x₁`, `h₂`, `ŷ`, `+1`. A label is
#: inside a circle, and every circle is drawn the size of the widest.
NEURALNET_LABEL_MAX: Final = 4


#: The most skip connections and repeated blocks a `blocks` network carries.
NEURALNET_SKIP_MAX: Final = 6


#: The most branches a set splits into, and the most layers in one branch: GoogLeNet's
#: Inception module is four towers of one or two layers.
NEURALNET_BRANCH_MAX: Final = 4


NEURALNET_TOWER_MAX: Final = 3


NEURALNET_REPEAT_MAX: Final = 3


#: The most ticks a step may cut the axis into. Past thirty the numbers crowd
#: into each other at the canvas width.
NUMBERLINE_TICK_MAX: Final = 30


#: How a `files` tree is drawn. `icons` is the file-browser look; `plain` keeps
#: the guides and drops the pictures; `unicode` and `ascii` are the tree as text,
#: set in the monospace face, the way `tree` prints it.
FILES_STYLES: Final = ("icons", "plain", "unicode", "ascii")


#: How a `tree` is drawn. `boxes` (the default) ranks boxes down from the root
#: and joins them with arrows; `bracket` is a tournament bracket or a cladogram:
#: every leaf on one outer edge, square elbows, and the inner nodes unboxed — a
#: winner's name on its line, or nothing at all.
TREE_STYLES: Final = ("boxes", "bracket")


#: Which edge a bracket's root stands at. `left` is a cladogram's (the common
#: ancestor at the left, the taxa in a column at the right); `right` is a
#: tournament read left to right, the champion at the end; `middle` is the
#: two-sided draw, half the field on each side and the final in the middle.
BRACKET_ROOTS: Final = ("left", "right", "middle")


#: The most leaves one bracket holds: a sixteen-team knockout. The NCAA's 64-team
#: draw is printed as four regions of sixteen and a final four, which is the
#: split this says to make. With no node of one child, sixteen leaves are at most
#: thirty-one nodes, which replaces a boxed tree's fifteen.
BRACKET_LEAVES_MAX: Final = 16


#: The edge roles a bracket draws: an ordinary line, and a heavy one for the path
#: the reader follows (the champion's run, the lineage the lesson is about).
BRACKET_EDGE_ROLES: Final = ("flow", "strong")


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
#: `venn` is the tenth: two or three sets and what they share — a `matrix` can
#: list memberships but cannot show an overlap.
#: `journey` is the eleventh: a named feeling across stages — a `curve` would put
#: a number on the feeling, and a `board` cannot draw the line through it.
#: `treemap` is the twelfth: the parts of one known total by area — a `chart`'s
#: bars compare the parts but do not show that they make one whole.
#: `sankey` is the thirteenth: where a known quantity goes — a `flow` can say
#: where, but not how much of it goes each way.
#: `numberline` is the fourteenth: values and ranges on one scale, each end open
#: or closed — a `timeline` places by number too, but reads as *when*, and its
#: spans cannot say whether an end belongs to the range.
#: `barmodel` is the fifteenth: a word problem as bars of parts in one scale,
#: braced — a `chart`'s bars stand on an axis, and a `treemap` is unaligned.
#: `waterfall` is the sixteenth: from one total to another, step by step — a
#: `chart`'s bars stand on the baseline, and nothing in it checks a total.
#: `pie` is the seventeenth: the shares of one known total as sectors — a
#: `treemap` says the same by area, unfamiliar to the readers a pie is taught to.
#: `mindmap` is the eighteenth: a topic in the middle and its branches as peers
#: round it — a `tree` is ranked from a root at one edge, which says *first*.
#: `argument` is the nineteenth: a claim and the points for and against it — a
#: `tree` cannot say which way a box bears, or that two reasons count only together.
#: `familytree` is the twentieth: people, couples and children by generation — a
#: `tree` gives a child one parent, and a married-in partner none.
#: `meter` is the twenty-first: one amount against its scale — a `chart`'s bar
#: has no end to be read against, and a `numberline` no fill, target or bands.
#: `rag` is the twenty-second: rows rated red, amber or green in words and shapes
#: — a `matrix` scale is a tone with no word on it, and a `board` sorts, not rates.
#: `clock` is the twenty-third: two hands placed by a time — a `meter` dial reads
#: one amount on a half-circle, and nothing else places a hand by the hour.
#: `sunburst` is the twenty-fourth: a hierarchy as concentric rings of sectors,
#: read from the middle outward — a `treemap` nests by area and a `mindmap`
#: radiates, but neither splits a ring into its parent's sectors.
#: `timing` is the twenty-fifth: signals against one shared time axis — a
#: `gantt` lays intervals of work on time, but nothing draws a level, a clock or
#: a bus changing from step to step.
#: `gitgraph` is the twenty-sixth: commits on branches over time, forked and
#: merged — a `gantt` has intervals, a `flow` has no lanes in time, and a
#: `timeline` has one line.
#: `network` is the twenty-seventh: networks as buses with hosts hanging between
#: them — a `flow` joins boxes to boxes, and nothing else joins boxes to a bus.
#: `railroad` is the twenty-eighth: a grammar's rules as tracks through terminals,
#: choices and loops — a `flow` routes arbitrary edges between boxes, but nothing
#: else derives a syntax diagram's branches and bypasses from an expression.
#: `usecase` is the twenty-ninth: who uses a system for what — actors outside a
#: boundary, use cases inside it. A `flow` has no boundary its edges must cross
#: once, and no actor drawn as the stick figure a reader looks for.
#: `wardley` is the thirtieth: components placed by value chain and evolution,
#: joined by what they need — a `quadrant` places things but joins nothing, and
#: a `flow` joins things but places them by its own layout, not by a stage.
#: `packet` is the thirty-first: bit fields in rows of a fixed width under a bit
#: ruler — a `barmodel` sizes parts by amount and a `stack` by words, but neither
#: wraps a field across a row boundary at a bit position.
#: `pert` is the thirty-second: activities joined finish-to-start with their
#: schedule computed — a `gantt` places bars by times the author wrote, and a
#: `flow` computes nothing.
#: `automaton` is the thirty-third: a finite automaton as the textbooks draw it —
#: circles, a doubled ring for an accepting state, an arrow from nowhere into the
#: start, symbols on curved arcs — where a `states` diagram is UML's rounded
#: boxes, a filled start dot and `event [guard] / action` labels.
#: `neuralnet` is the thirty-fourth: a neural network's layers in order, as
#: columns of neurons fully joined or as boxes with tensor shapes — where a `flow`
#: draws no neurons and computes no parameters.
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
    + VENN_KINDS
    + JOURNEY_KINDS
    + TREEMAP_KINDS
    + SANKEY_KINDS
    + NUMBERLINE_KINDS
    + BARMODEL_KINDS
    + WATERFALL_KINDS
    + PIE_KINDS
    + MINDMAP_KINDS
    + ARGUMENT_KINDS
    + FAMILYTREE_KINDS
    + METER_KINDS
    + RAG_KINDS
    + CLOCK_KINDS
    + SUNBURST_KINDS
    + PACKET_KINDS
    + NETWORK_KINDS
    + TIMING_KINDS
    + GITGRAPH_KINDS
    + RAILROAD_KINDS
    + USECASE_KINDS
    + WARDLEY_KINDS
    + PERT_KINDS
    + AUTOMATON_KINDS
    + NEURALNET_KINDS
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
    # Loops set by the proposal and the corpus: teaching diagrams name two or three.
    # `classes` is the owner's cap (kind audit rank 5): see `CLASSES_MAX`.
    "flow": (
        ("nodes", 15),
        ("edges", 16),
        ("loops", LOOP_MAX),
        ("classes", CLASSES_MAX),
    ),  # [14 nodes, 12 edges, 3 loops, 3 classes]
    "tree": (("nodes", 15), ("classes", CLASSES_MAX)),  # [11 nodes, 3 classes]
    "cycle": (("nodes", 8),),  # [5]
    # A consumer's corpus holds a nine-item legal enumeration (the principles of
    # preventive action, LPRL art. 15), so 10, with headroom as for timeline.
    "stack": (("items", 10),),  # [3]
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
    # `groups/regions` is the owner's (kind audit question 4): past four regions
    # side by side a composite outgrows its share of the canvas. A name with `=`
    # counts the entries of its array that take one of the roles after it: past
    # four fork and join bars (#107) the machine is a workflow, and an activity
    # diagram's job.
    "states": (
        ("states", 14),
        ("transitions", 24),
        ("groups/regions", STATES_REGION_MAX),
        ("states=fork|join", 4),
    ),  # [8 states, 10 transitions, 3 regions, 2 bars]
    # Set by the proposal: past eight lifelines and thirty messages a sequence
    # diagram is a trace, not an explanation — split it into phases.
    "sequence": (("participants", 8), ("messages", 30)),  # [5 participants, 13 messages]
    # A flow's budget, and a cap on the strips: see `LANES_MAX`. When `lanes` is
    # omitted the same cap is applied to the distinct actors, at the node that
    # names the one too many.
    # `phases` is the proposal's (kind audit rank 8), not the references'.
    "lanes": (
        ("nodes", 15),
        ("edges", 16),
        ("lanes", LANES_MAX),
        ("phases", LANES_PHASES_MAX),
        ("classes", CLASSES_MAX),
    ),  # [7 nodes, 7 edges, 4 lanes, 3 phases, 2 classes]
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
    # A row's deliveries and iterations: past eight a row's marks crowd its bar.
    "gantt": (
        ("tasks", 16),
        ("edges", 20),
        ("marks", 4),
        ("tasks/events", 8),
        ("tasks/iterations", 8),
    ),  # [11 tasks, 9 edges, 2 marks, 4 events, 4 iterations]
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
    # Set by the corpus: research figures draw four sets as four ellipses, every
    # one of the fifteen regions there; past four no drawing shows every region.
    "venn": (("sets", VENN_SET_MAX), ("regions", 15)),  # [4 sets, 15 regions]
    # Set by the proposal: columns narrow past seven, neighbouring levels blur
    # past five, and past four rows the map is a table with a line on it.
    "journey": (
        ("stages", JOURNEY_STAGE_MAX),
        ("feelings", JOURNEY_FEELING_MAX),
        ("rows", JOURNEY_ROW_MAX),
    ),  # [7 stages, 5 feelings, 3 rows]
    # Set by the proposal: past ten parts the smallest are slivers no label fits,
    # and one level of four groups is as much framing as the parts can carry.
    "treemap": (
        ("parts", TREEMAP_PART_MAX),
        ("groups", TREEMAP_GROUP_MAX),
    ),  # [9 parts, 3 groups]
    # Set by the proposal: past fourteen nodes the bands are a tangle. The four
    # columns are derived, not written, so `SANKEY_COLUMN_MAX` is checked with the
    # flows, at the node that makes the fifth.
    "sankey": (
        ("nodes", SANKEY_NODE_MAX),
        ("flows", SANKEY_FLOW_MAX),
    ),  # [10 nodes, 9 flows]
    # Set by the corpus: the pH scale is fifteen points, and no real figure stacks
    # more than two ranges.
    "numberline": (
        ("points", NUMBERLINE_POINT_MAX),
        ("ranges", NUMBERLINE_RANGE_MAX),
    ),  # [15 points, 3 ranges]
    # Set by the corpus: one to three bars of two to eight parts. Units per bar are
    # checked with the parts, at the part that makes the thirteenth box.
    "barmodel": (
        ("bars", BARMODEL_BAR_MAX),
        ("bars/parts", BARMODEL_PART_MAX),
        ("braces", BARMODEL_BRACE_MAX),
    ),  # [3 bars, 2 parts, 2 braces]
    # Set by the corpus: five to ten bars, start and end totals included.
    "waterfall": (("bars", WATERFALL_BAR_MAX),),  # [9]
    # Set by the corpus: school pies have three to six sectors, budget pies more,
    # the rest merged into one `note` part.
    "pie": (("parts", PIE_PART_MAX),),  # [8]
    # Owner-approved from the corpus: a handful of main branches, never more than
    # three levels. A name ending `*` counts its array at every depth together.
    "mindmap": (
        ("branches", MINDMAP_BRANCH_MAX),
        ("branches*", MINDMAP_NODE_MAX),
    ),  # [6 main branches, 25 in all]
    # Set by the corpus: argument maps in study guides hold about a dozen boxes.
    # The depth (4) and a co-premise group's size (4) are checked with the points.
    "argument": (("points", ARGUMENT_POINT_MAX),),  # [7]
    # Set by the corpus: clinical pedigrees hold ten to twenty people, a royal tree
    # about thirty. Generations (4) and partners (6) are checked with the couples.
    "familytree": (("people", FAMILYTREE_PEOPLE_MAX),),  # [16]
    # Set by the corpus: a panel stacks a handful of meters, and a bullet graph
    # two to five bands.
    "meter": (("meters", METER_MAX), ("meters/bands", METER_BAND_MAX)),  # [5 meters, 4 bands]
    # Set by the corpus: the largest risk register found rates 13 risks (R4).
    "rag": (("rows", RAG_ROW_MAX),),  # [10]
    # Set by the corpus: a worksheet holds a dozen faces (C4).
    "clock": (("clocks", CLOCK_MAX),),  # [8]
    # Owner-approved: up to eight first-ring sectors, three rings, 150 in all. The
    # total across the rings is checked with the nodes (see `_sunburst_violations`),
    # since the nesting key is `children`, not `nodes`.
    "sunburst": (("nodes", SUNBURST_RING_MAX),),  # first ring; the total is _sunburst_violations
    # Set by the references: a TCP header with every flag is 18 fields. The rows
    # (16) are counted from the widths, in `_packet_violations`.
    "packet": (("fields", PACKET_FIELD_MAX),),
    # Set by the proposal: nwdiag's and PlantUML's own examples hold two or three
    # networks and four to ten hosts; past these the drawing is an inventory.
    "network": (
        ("networks", NETWORK_MAX),
        ("hosts", NETWORK_HOST_MAX),
        ("groups", NETWORK_GROUP_MAX),
    ),  # [3 networks, 10 hosts, 3 groups]
    # Set by the evidence (NXP UM10204, TI SPI figures, UML timing): an SPI read is
    # four signals over ~20 steps; the step cap is checked per signal's values in
    # `_timing_violations`, since it is a length, not an array of objects.
    "timing": (
        ("signals", TIMING_SIGNAL_MAX),
        ("signals/states", TIMING_STATE_MAX),
        ("markers", TIMING_MARKER_MAX),
        ("intervals", TIMING_INTERVAL_MAX),
    ),  # [4 signals, 3 states, 3 markers, 5 intervals]
    # Set by the originals: git-flow's five kinds of branch (nvie 2010) with room for
    # more features, and a step per column across the page.
    "gitgraph": (("branches", GITGRAPH_BRANCH_MAX), ("steps", GITGRAPH_STEP_MAX)),
    # Proposal: a dozen rules, forty boxes on one track (SQLite's busiest). The
    # boxes are counted per rule with the items (see `_railroad_violations`).
    "railroad": (("rules", RAILROAD_RULE_MAX),),
    # Set by the originals: the textbook figures hold three to six actors and a dozen
    # use cases in one or two boundaries.
    "usecase": (
        ("actors", USECASE_ACTOR_MAX),
        ("usecases", USECASE_CASE_MAX),
        ("systems", USECASE_SYSTEM_MAX),
        ("edges", USECASE_EDGE_MAX),
    ),
    # Set with the kind: Wardley's teaching maps (the tea shop, the photo service)
    # hold 7 to 12 components under one or two anchors.
    "wardley": (
        ("components", WARDLEY_COMPONENT_MAX),
        ("anchors", WARDLEY_ANCHOR_MAX),
        ("notes", WARDLEY_NOTE_MAX),
    ),
    # Set by the evidence: a textbook network is eight to fourteen activities.
    # The dependencies are counted with the activities (see `_pert_violations`).
    "pert": (("activities", PERT_ACTIVITY_MAX),),
    # Set by the evidence: the textbook figures hold three to eight states and a
    # dozen or so transitions. [3 states, 6 transitions; 4 and 7; 4 and 8]
    "automaton": (
        ("states", AUTOMATON_STATE_MAX),
        ("transitions", AUTOMATON_TRANSITION_MAX),
    ),
    # Set by the evidence: LeNet-5 is seven layers, a Transformer encoder drawn
    # whole eight, ResNet's residual block four with one skip, Nielsen's network
    # three columns. [7 layers; 8 layers, 2 skips, 1 repeat; 5 and 1]
    "neuralnet": (
        ("layers", NEURALNET_LAYER_MAX),
        ("skips", NEURALNET_SKIP_MAX),
        ("repeats", NEURALNET_REPEAT_MAX),
    ),
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

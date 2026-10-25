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
import math
import re
from collections.abc import Iterator, Mapping, Sequence, Set
from dataclasses import dataclass, replace
from difflib import get_close_matches
from fractions import Fraction
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
                "dual-homed server. Its line may cross no bus it is not on, so the column "
                "order is drawspec's; a set of attachments no order can draw is refused."
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
            "Which of the forty-five diagrams this is. It selects the fields that are "
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
                "network it is on. The columns are drawspec's: ordered so no line crosses a bus "
                "it is not on, then as few and as close to the order written as that allows."
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

    if kind in SUNBURST_KINDS:
        # `sunburst-node` is self-referential, so cap the depth before the
        # recursive structural pass can overflow on pathologically deep input.
        too_deep = _sunburst_too_deep(document)
        if too_deep is not None:
            found.append(too_deep)
            return tuple(found)

    if kind in RAILROAD_KINDS:
        # `railroad-item` is self-referential too: cap the nesting before recursing.
        nested = _railroad_too_deep(document)
        if nested is not None:
            found.append(nested)
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

    if kind in SEQUENCE_KINDS:
        found = [_sequence_refusal(violation, document) for violation in found]
    if kind in LANES_KINDS:
        found = [_lanes_refusal(violation) for violation in found]
    if kind in GANTT_KINDS:
        found = [_gantt_refusal(violation, document) for violation in found]
    if kind in BOARD_KINDS:
        found = [_board_refusal(violation) for violation in found]
    if kind in FISHBONE_KINDS:
        found = [_fishbone_refusal(violation) for violation in found]
    if kind in VENN_KINDS:
        found = [_venn_refusal(violation) for violation in found]
    if kind in JOURNEY_KINDS:
        found = [_journey_refusal(violation) for violation in found]
    if kind in TREEMAP_KINDS:
        found = [_treemap_refusal(violation) for violation in found]
    if kind in SANKEY_KINDS:
        found = [_sankey_refusal(violation) for violation in found]
    if kind in NUMBERLINE_KINDS:
        found = [_numberline_refusal(violation, document) for violation in found]
    if kind in BARMODEL_KINDS:
        found = [_barmodel_refusal(violation) for violation in found]
    if kind in WATERFALL_KINDS:
        found = [_waterfall_refusal(violation) for violation in found]
    if kind in PIE_KINDS:
        found = [_pie_refusal(violation) for violation in found]
    if kind in MINDMAP_KINDS:
        found = [_mindmap_refusal(violation) for violation in found]
    if kind in ARGUMENT_KINDS:
        found = [_argument_refusal(violation, document) for violation in found]
    if kind in FAMILYTREE_KINDS:
        found = [_familytree_refusal(violation) for violation in found]
    if kind in METER_KINDS:
        found = [_meter_refusal(violation) for violation in found]
    if kind in RAG_KINDS:
        found = [_rag_refusal(violation) for violation in found]
    if kind in CLOCK_KINDS:
        found = [_clock_refusal(violation) for violation in found]
    if kind in SUNBURST_KINDS:
        found = [_sunburst_refusal(violation) for violation in found]
    if kind in PERT_KINDS:
        found = [_pert_refusal(violation) for violation in found]
    if kind in PACKET_KINDS:
        found = [_packet_refusal(violation) for violation in found]
    if kind in WARDLEY_KINDS:
        found = [_wardley_refusal(violation) for violation in found]
    if kind == "tree":
        found = [_tree_refusal(violation, document) for violation in found]
    if kind in USECASE_KINDS:
        found = [_usecase_refusal(violation) for violation in found]
    if kind in RAILROAD_KINDS:
        found = [_railroad_refusal(violation) for violation in found]
    if kind in NETWORK_KINDS:
        found = [_network_refusal(violation) for violation in found]
    if kind in TIMING_KINDS:
        found = [_timing_refusal(violation) for violation in found]
    if kind in GITGRAPH_KINDS:
        found = [_gitgraph_refusal(violation) for violation in found]
    found = [_edge_role_refusal(violation, document, kind) for violation in found]
    found.extend(_referential_violations(document, kind))
    if kind == "tree":
        found.extend(_bracket_violations(document))
    found.extend(_readability_violations(document, kind))
    found.extend(_emphasis_violations(document))
    return tuple(found)


def _tree_refusal(violation: Violation, document: Mapping[str, Any]) -> Violation:
    """A bracket's `root` at the top or bottom, told why a bracket only reads across."""
    root = document.get("root")
    if violation.pointer == "/root" and root in ("top", "bottom", "up", "down"):
        return Violation(
            "/root",
            f"{root!r}: a bracket reads across, each leaf's name on a row of its own, so its "
            "root stands at the `left`, the `right` or in the `middle`. A tree read down the "
            'page is the boxed one: drop `"style": "bracket"`.',
        )
    return violation


#: Why a bracket refuses what a boxed tree takes, by the field's name.
BRACKET_REFUSED: Final[Mapping[str, str]] = {
    "groups": (
        "a bracket has no boxes to frame: its nodes are lines. Name a part of the draw in an "
        "inner node's words (a region, a clade), or draw it as boxes without the bracket style."
    ),
    "bands": (
        "a bracket has no boxes for a band to run beside. Say what runs alongside in the "
        "`caption`, or draw it as boxes without the bracket style."
    ),
    "classes": (
        "a bracket has no boxes to fill, so a class would have nothing to mark. Name the "
        "grouping in an inner node's words, or draw it as boxes without the bracket style."
    ),
    "class": "a bracket's node is a line, with no box for a class's fill. Drop it.",
    "status": (
        "a bracket's node is a line, with no box for a change's mark. Draw the change as two "
        "brackets, or as boxes without the bracket style."
    ),
    "actor": (
        "a bracket's node is one line of words, with no box for an actor's lead. Write who "
        "into the node's `text`."
    ),
    "role": (
        "a bracket's node is a line of words, with no box for a role to shape. To mark the "
        'path the reader should follow, give its edges `"role": "strong"`.'
    ),
}


def _bracket_violations(document: Mapping[str, Any]) -> list[Violation]:
    """A tree drawn as a bracket: one root, one parent each, no node of one child.

    The boxed tree draws any graph its edges make, cross-links included. A bracket
    places every node from its leaves, so the edges must be a tree, rooted once,
    and each inner node a match or a split of at least two.
    """
    if document.get("style", "boxes") != "bracket":
        if "root" in document:
            return [
                Violation(
                    "/root",
                    "`root` says which edge a bracket's root stands at, and this tree is drawn "
                    'as boxes ranked down from its root. Say `"style": "bracket"`, or drop it.',
                )
            ]
        return []
    found: list[Violation] = []
    for name in ("groups", "bands", "classes"):
        if name in document:
            found.append(Violation(f"/{name}", BRACKET_REFUSED[name]))
    ids: dict[str, int] = {}
    texts: dict[str, str] = {}
    for index, node in enumerate(_listed(document, "nodes")):
        if not isinstance(node, dict):
            continue
        for name in ("class", "status", "actor"):
            if name in node:
                found.append(Violation(_pointer("nodes", index, name), BRACKET_REFUSED[name]))
        if node.get("role", "step") != "step":
            found.append(Violation(_pointer("nodes", index, "role"), BRACKET_REFUSED["role"]))
        text = node.get("text")
        if isinstance(text, str) and "\n" in text.strip():
            found.append(
                Violation(
                    _pointer("nodes", index, "text"),
                    "a bracket's node is one line of words on its line: a team, a taxon, a "
                    "winner. Join the text into one line, or put the detail in the caption.",
                )
            )
        identifier = node.get("id")
        if isinstance(identifier, str) and identifier not in ids:
            ids[identifier] = index
            texts[identifier] = text if isinstance(text, str) else ""
    parent: dict[str, str] = {}
    children: dict[str, list[str]] = {identifier: [] for identifier in ids}
    for index, edge in enumerate(_listed(document, "edges")):
        if not isinstance(edge, dict):
            continue
        if "status" in edge:
            found.append(Violation(_pointer("edges", index, "status"), BRACKET_REFUSED["status"]))
        role = edge.get("role", "flow")
        if isinstance(role, str) and role not in BRACKET_EDGE_ROLES:
            found.append(
                Violation(
                    _pointer("edges", index, "role"),
                    f"{role!r}: a bracket's lines are all one line, square elbows to the next "
                    'round, so an edge is `"flow"` (the default) or `"strong"`, the heavy '
                    "path the reader follows.",
                )
            )
        label = edge.get("label")
        if isinstance(label, str) and "\n" in label.strip():
            found.append(
                Violation(
                    _pointer("edges", index, "label"),
                    "an edge's label is written on one line beside the elbow: a score, a "
                    "trait. Join it into one line.",
                )
            )
        source, target = edge.get("from"), edge.get("to")
        if not isinstance(source, str) or not isinstance(target, str):
            continue
        if source not in ids or target not in ids:
            continue  # reported by the graph checks
        if source == target:
            found.append(
                Violation(
                    _pointer("edges", index, "to"),
                    f"{target!r} joins itself, and a bracket only joins a node to the match "
                    "or the split it feeds. Drop the edge.",
                )
            )
        elif target in parent:
            found.append(
                Violation(
                    _pointer("edges", index, "to"),
                    f"{target!r} already hangs from {parent[target]!r}, and in a bracket each "
                    "node feeds one match or one split. A team in two matches is two "
                    "entries, and a hybrid of two lineages is a network, not a tree: draw "
                    "that as boxes without the bracket style.",
                )
            )
        else:
            parent[target] = source
            children[source].append(target)
    if not ids:
        return found
    roots = [identifier for identifier in ids if identifier not in parent]
    if not roots:
        found.append(
            Violation(
                "/edges",
                "every node hangs from another, so the edges make a cycle and the bracket has "
                "no root: no final, no common ancestor. Drop the edge into the root.",
            )
        )
        return found
    if len(roots) > 1:
        found.append(
            Violation(
                _pointer("nodes", ids[roots[1]]),
                f"{roots[1]!r} hangs from nothing, and neither does {roots[0]!r}: a bracket "
                "has one root, the final or the common ancestor, and every other node feeds "
                "into it. Add the edge that joins them, or draw two brackets.",
            )
        )
        return found
    reached: set[str] = set()
    stack = [roots[0]]
    while stack:
        identifier = stack.pop()
        if identifier not in reached:
            reached.add(identifier)
            stack.extend(children[identifier])
    for identifier, index in ids.items():
        if identifier not in reached:
            found.append(
                Violation(
                    _pointer("nodes", index),
                    f"{identifier!r} is on a cycle of edges that never reaches the root "
                    f"{roots[0]!r}. Drop the edge that closes the cycle.",
                )
            )
            return found
    for identifier, kids in children.items():
        if len(kids) == 1:
            found.append(
                Violation(
                    _pointer("nodes", ids[identifier]),
                    f"{identifier!r} has one child, {kids[0]!r}: a match has two sides and a "
                    "split at least two branches, so a node of one is the same line twice. "
                    "Drop it and join its child to its parent, or give it its other side.",
                )
            )
    leaves = [identifier for identifier, kids in children.items() if not kids]
    for identifier in leaves:
        if not texts[identifier].strip():
            found.append(
                Violation(
                    _pointer("nodes", ids[identifier], "text"),
                    f"{identifier!r} is a leaf, and the leaves are what a bracket is of: the "
                    "teams, the taxa. Only an inner node may go unnamed.",
                )
            )
    if len(leaves) > BRACKET_LEAVES_MAX:
        found.append(
            Violation(
                _pointer("nodes", ids[leaves[BRACKET_LEAVES_MAX]]),
                f"{len(leaves)} leaves are past what one bracket can be read at — "
                f"{BRACKET_LEAVES_MAX} at most. Split it as a 64-team draw is printed: one "
                "bracket per region of sixteen, and one more for the regions' winners. The "
                "budget is not a canvas size, so a larger top-level 'width' does not lift it.",
            )
        )
    if document.get("root") == "middle" and len(children[roots[0]]) != 2:
        found.append(
            Violation(
                "/root",
                f"a two-sided bracket puts the root's first child's half on the left and its "
                f"second's on the right, and {roots[0]!r} has {len(children[roots[0]])} "
                'children. Give it two, or say `"root": "left"` or `"right"`.',
            )
        )
    return found


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


_CLASSES_ADVICE: Final = (
    f"Past {CLASSES_MAX} classes the fills stop being told apart and the key is a table. "
    "Merge the classes a reader need not tell apart, or draw one diagram per class that "
    "matters."
)

#: What to do instead, for a budget whose generic advice ("split it into an
#: overview and details") is not the remedy. Keyed by (kind, array) for a
#: top-level budget and by (outer, inner) for a nested one.
BUDGET_ADVICE: Final[Mapping[tuple[str, str], str]] = {
    ("flow", "classes"): _CLASSES_ADVICE,
    ("tree", "classes"): _CLASSES_ADVICE,
    ("lanes", "classes"): _CLASSES_ADVICE,
    ("lanes", "phases"): (
        f"Past {LANES_PHASES_MAX} phases the header band is a table of contents. Merge "
        "neighbouring phases, or split the process at a phase boundary into two diagrams."
    ),
    ("fishbone", "categories"): (
        "Past six bones a fishbone stops being scannable: merge the categories that overlap, "
        "or draw the biggest category as a fishbone of its own."
    ),
    ("barmodel", "bars"): (
        "Past three bars a bar model is a table of quantities. Draw the step the problem "
        "turns on, or one model per step of a multi-step problem."
    ),
    ("argument", "points"): (
        "Past fifteen points an argument map is searched, not read. Split it: an overview "
        "with the claim and the top-level reasons and objections, and a map per contested "
        "reason, with that reason as its claim."
    ),
    ("familytree", "people"): (
        "Past thirty people a family tree is searched, not read. Split it by branch: one "
        "tree per side of the family, each naming where it joins the other in a `caption`."
    ),
    ("mindmap", "branches"): (
        "Past eight main branches they stop reading as peers round one centre. Group the "
        "ones that belong together under a new main branch, or split the topic into two maps."
    ),
    ("mindmap", "branches*"): (
        "Split it: an overview map naming the main branches, and a map per main branch "
        "carrying its detail, with that branch as its centre."
    ),
    ("meter", "meters"): (
        "Past six meters a panel is a dashboard, read as a table. Keep the ones the page is "
        "about, and put the rest in a table beside it."
    ),
    ("clock", "clocks"): (
        "Past twelve faces a sheet is two sheets: split it by the skill each practises — "
        "o'clock and half past on one, quarters on the next."
    ),
    ("timing", "signals"): (
        "Past twelve lanes a timing figure is searched, not read: split it by bus or by "
        "phase, one figure each, on the same steps."
    ),
    ("signals", "states"): (
        "Past six states the levels of one lane crowd: merge the states the reader need not "
        "tell apart, or draw the machine as a `states` diagram."
    ),
    ("rag", "rows"): (
        "Past fifteen rows a status report is searched, not read: split it by programme or "
        "directorate, one report each, or put the green rows in a table beside it."
    ),
    ("pert", "activities"): (
        "Past twenty activities a network is searched, not followed. Draw an overview network "
        "with one activity per phase, and a network per phase carrying its detail."
    ),
    ("meters", "bands"): (
        "Past five bands neighbouring tones blur: merge the bands the reader need not tell "
        "apart. Few's bullet graph uses two to five."
    ),
    ("pie", "parts"): (
        "Past eight sectors the smallest are slivers no one compares: keep the largest seven "
        'and merge the rest into one `"role": "note"` part — `Everything else` — or draw a '
        "bar `chart`."
    ),
    ("waterfall", "bars"): (
        "Past twelve bars the names under them are too narrow to read. Split the bridge at "
        "a subtotal into two waterfalls, or merge the smallest steps into one `Other` step."
    ),
    ("bars", "parts"): (
        "Past eight parts the boxes are too thin to write in: merge the parts the question "
        "does not ask about into one, or draw the bar in `units`."
    ),
    ("flow", "loops"): (
        "Past six loops the markers crowd the map and none reads as a story. Split it: one "
        "diagram per subsystem, as research maps do, each naming its own loops."
    ),
    ("venn", "sets"): (
        "No drawing of five sets shows every region legibly, so a fifth set cannot be drawn "
        "honestly. Use a `matrix`: the sets as columns, the items as rows, a mark where an "
        "item belongs."
    ),
    ("journey", "stages"): (
        "Past seven stages the columns are too narrow to read. Split it into two journeys, "
        "before and after a hand-off, each with its own feeling line."
    ),
    ("journey", "feelings"): (
        "Past five levels two neighbours cannot be told apart on the page. Merge the levels "
        "nobody could tell apart in a sentence either."
    ),
    ("journey", "rows"): (
        "Past four rows the map is a table with a line on it. Keep the rows the line is "
        "explained by, or split it into two journeys, before and after a hand-off."
    ),
    ("treemap", "parts"): (
        "Past ten parts the smallest are slivers no label fits, and the drawing is a "
        "disk-usage tool's output. Merge the smallest into one `note` part — `Everything "
        "else` — and say what it holds in the caption."
    ),
    ("usecase", "actors"): (
        "Past eight actors the lines from the two sides are a net. Draw one use case "
        "diagram per kind of user — the customer's, the staff's — each with the use "
        "cases that user takes part in."
    ),
    ("usecase", "usecases"): (
        "Past fifteen use cases the boundary is a list. Draw an overview with one use case "
        "per goal, then a diagram per goal with the steps it includes and extends."
    ),
    ("usecase", "edges"): (
        "Past thirty relations the lines are a net. Split the diagram by actor or by "
        "subsystem, so each holds the relations one reader follows."
    ),
    ("sankey", "nodes"): (
        "Past fourteen nodes the bands are a tangle. Merge the small ends into one `note` "
        "node, or draw one sankey per stage — the middle column's nodes become the next "
        "one's sources."
    ),
    ("sankey", "flows"): (
        "Past twenty-four flows the bands are a tangle. Merge the small flows into one named "
        "`other` flow, or draw one sankey per stage."
    ),
    ("treemap", "groups"): (
        "Past four groups the frames crowd out the parts they hold. Draw one treemap of the "
        "groups' totals, then one per group that matters."
    ),
    ("groups", "regions"): (
        "Past four regions each is too small to hold a machine. Draw the composite as one "
        "state here and give each region a state machine of its own."
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
        if kind == "tree" and name == "nodes" and document.get("style") == "bracket":
            continue  # a bracket counts its leaves instead: see `BRACKET_LEAVES_MAX`
        if "/" in name:
            found.extend(_nested_budget(document, name, limit))
            continue
        if "@" in name:
            found.extend(_cell_budget(document, name, limit))
            continue
        if name.endswith("*"):
            found.extend(_deep_budget(document, kind, name[:-1], limit))
            continue
        if "=" in name:
            found.extend(_role_budget(document, kind, name, limit))
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


def _role_budget(document: Mapping[str, Any], kind: str, name: str, limit: int) -> list[Violation]:
    """The budget of the entries of an array that take some roles: a machine's bars."""
    outer, roles = name.split("=")
    taking = roles.split("|")
    counted = [
        index
        for index, entry in enumerate(_listed(document, outer))
        if isinstance(entry, dict) and entry.get("role") in taking
    ]
    if len(counted) <= limit:
        return []
    named = " and ".join(taking)
    return [
        Violation(
            _pointer(outer, counted[limit], "role"),
            f"{len(counted)} {named} bars are past what one {kind} can be read at — "
            f"{limit} at most. Past that the machine is a workflow: draw it as a `flow` "
            f"or `lanes`, or split it into a machine per stage.",
        )
    ]


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
                else f"{len(rows)} {inner} is past what one {_singular(outer)} can be read at — "
                f"{limit} at most. {advice}",
            )
        )
    return found


def _deep_budget(document: Mapping[str, Any], kind: str, name: str, limit: int) -> list[Violation]:
    """The budget of an array counted at every depth together: a mind map's branches.

    Counted in reading order, depth first, so the pointer lands on the entry that
    made one too many, wherever it is nested.
    """
    seen: list[str] = []

    def walk(entries: object, pointer: str) -> None:
        if not isinstance(entries, list):
            return
        for index, entry in enumerate(entries):
            seen.append(f"{pointer}/{index}")
            if isinstance(entry, dict):
                walk(entry.get(name), f"{pointer}/{index}/{name}")

    walk(document.get(name), f"/{name}")
    if len(seen) <= limit:
        return []
    return [
        Violation(
            seen[limit],
            f"{len(seen)} {name} in all is past what one {kind} can be read at — {limit} at "
            f"most, counted at every level. "
            + BUDGET_ADVICE.get((kind, f"{name}*"), "Split it into an overview and details.")
            + " The budget is not a canvas size, so a larger top-level 'width' does not lift it.",
        )
    ]


def _singular(name: str) -> str:
    """`categories` → `category`, `bars` → `bar`: one entry of a counted array."""
    return name[:-3] + "y" if name.endswith("ies") else name[:-1]


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
    if kind in VENN_KINDS:
        return _venn_violations(document)
    if kind in JOURNEY_KINDS:
        return _journey_violations(document)
    if kind in TREEMAP_KINDS:
        return _treemap_violations(document)
    if kind in SANKEY_KINDS:
        return _sankey_violations(document)
    if kind in NUMBERLINE_KINDS:
        return _numberline_violations(document)
    if kind in BARMODEL_KINDS:
        return _barmodel_violations(document)
    if kind in WATERFALL_KINDS:
        return _waterfall_violations(document)
    if kind in PIE_KINDS:
        return _pie_violations(document)
    if kind in MINDMAP_KINDS:
        return _mindmap_violations(document)
    if kind in ARGUMENT_KINDS:
        return _argument_violations(document)
    if kind in FAMILYTREE_KINDS:
        return _familytree_violations(document)
    if kind in METER_KINDS:
        return _meter_violations(document)
    if kind in CLOCK_KINDS:
        return _clock_violations(document)
    if kind in SUNBURST_KINDS:
        return _sunburst_violations(document)
    if kind in PERT_KINDS:
        return _pert_violations(document)
    if kind in PACKET_KINDS:
        return _packet_violations(document)
    if kind in WARDLEY_KINDS:
        return _wardley_violations(document)
    if kind in USECASE_KINDS:
        return _usecase_violations(document)
    if kind in RAILROAD_KINDS:
        return _railroad_violations(document)
    if kind in NETWORK_KINDS:
        return _network_violations(document)
    if kind in TIMING_KINDS:
        return _timing_violations(document)
    if kind in GITGRAPH_KINDS:
        return _gitgraph_violations(document)
    if kind == "chart":
        return _chart_violations(document)
    if kind == "quadrant":
        return _quadrant_violations(document)
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
            for name in ("polarity", "delay"):
                if name in edge:
                    found.append(
                        Violation(
                            _pointer("edges", index, name),
                            f"{name!r} marks a causal link, and a causal loop diagram is a "
                            f"`flow`: draw it as one.",
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
        found.extend(_funnel_amount_violations(document))
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
    found.extend(_class_violations(document, kind))
    found.extend(_causal_violations(document, kind, seen))

    if kind == "cycle":
        found.extend(_shaped_in_cycle(nodes))
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


def _chart_violations(document: Mapping[str, Any]) -> list[Violation]:
    """A chart with `categories` on its vertical axis: horizontal bars, checked.

    The categories become rows, so every series is bars, every point is
    `[amount, position]` with a position that names a row, and the category axis
    takes no `min`/`max` — the rows frame it. Amounts start at zero: a bar that
    runs left of the names is a diverging chart, which this kind does not draw.
    """
    found: list[Violation] = []
    axes = document.get("axes")
    if not isinstance(axes, dict):
        return found
    vertical, horizontal = axes.get("vertical"), axes.get("horizontal")
    if not isinstance(vertical, dict) or not vertical.get("categories"):
        return found
    count = len(vertical["categories"])
    if isinstance(horizontal, dict) and horizontal.get("categories"):
        found.append(
            Violation(
                "/axes/horizontal/categories",
                "both axes name categories, so no axis carries an amount for a bar to "
                "measure. With `categories` on the vertical axis the bars run across: "
                "give the horizontal axis numbers.",
            )
        )
    for name in ("min", "max"):
        if name in vertical:
            found.append(
                Violation(
                    _pointer("axes", "vertical", name),
                    f"with `categories` the vertical axis is the {count} rows, one per "
                    f"category, top first, so it takes no {name!r}. Drop it.",
                )
            )
    for index, series in enumerate(_listed(document, "series")):
        if not isinstance(series, dict):
            continue
        if series.get("mark", "line") != "bar":
            found.append(
                Violation(
                    _pointer("series", index, "mark"),
                    "with `categories` on the vertical axis this is a horizontal bar chart, "
                    'and every series is `"mark": "bar"`. A line drawn down a list of '
                    "names joins things that have no order between them.",
                )
            )
        for point, pair in enumerate(series.get("data", ()) or ()):
            if not isinstance(pair, list) or len(pair) != 2:
                continue
            amount, position = pair
            if _is_number(position) and (
                not 1 <= position <= count or not float(position).is_integer()
            ):
                found.append(
                    Violation(
                        _pointer("series", index, "data", point, 1),
                        f"a horizontal bar is `[amount, position]`, and the position names a "
                        f"category: a whole number from 1 to {count}, not {position!r}.",
                    )
                )
            if _is_number(amount) and amount < 0:
                found.append(
                    Violation(
                        _pointer("series", index, "data", point, 0),
                        f"{amount!r} is below zero, and a horizontal bar grows right from "
                        f"zero beside its name. A chart of gains and losses is upright: put "
                        f"the categories on the horizontal axis, or use a `waterfall`.",
                    )
                )
    return found


def _quadrant_violations(document: Mapping[str, Any]) -> list[Violation]:
    """Four quarter names exactly, and two ends to an axis."""
    found: list[Violation] = []
    quadrants = document.get("quadrants")
    if isinstance(quadrants, list) and len(quadrants) != 4:
        found.append(
            Violation(
                "/quadrants",
                f"{len(quadrants)} names: a quadrant has four quarters, named top right "
                f"first, then counter-clockwise. Leave a quarter unnamed with an empty string.",
            )
        )
    axes = document.get("axes")
    for name in AXIS_ORDER:
        axis = axes.get(name) if isinstance(axes, dict) else None
        ends = axis.get("ends") if isinstance(axis, dict) else None
        if isinstance(ends, list) and len(ends) > 2:
            found.append(
                Violation(
                    _pointer("axes", name, "ends"),
                    f"{len(ends)} ends: an axis has two, the low end's word then the high end's.",
                )
            )
    return found


def _funnel_amount_violations(document: Mapping[str, Any]) -> list[Violation]:
    """Amounts on every stage or on none, each no more than the one before."""
    found: list[Violation] = []
    stages = [stage for stage in _listed(document, "stages") if isinstance(stage, dict)]
    counted = [index for index, stage in enumerate(stages) if "amount" in stage]
    if counted and len(counted) < len(stages):
        missing = next(index for index in range(len(stages)) if index not in counted)
        found.append(
            Violation(
                _pointer("stages", missing, "amount"),
                f"{len(counted)} of the {len(stages)} stages have an amount and this one has "
                f"none, so the share kept here could not be said. Give every stage its "
                f"amount, or none.",
            )
        )
    if "unit" in document and not counted:
        found.append(
            Violation(
                "/unit",
                "a unit with no amounts names nothing: no stage has an `amount` to write "
                "it after. Drop it, or give the stages their amounts.",
            )
        )
    previous: float | None = None
    for index, stage in enumerate(stages):
        if not _is_number(stage.get("amount")):
            continue
        amount = float(stage["amount"])
        if previous is not None and amount > previous:
            found.append(
                Violation(
                    _pointer("stages", index, "amount"),
                    f"{_figure(amount)} reached this stage, more than the {_figure(previous)} "
                    f"at the one before. A funnel only narrows: if things join part-way, "
                    f"draw it as a `flow` or a `sankey`.",
                )
            )
        previous = amount
    return found


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
    found.extend(_phase_violations(document))
    return found


def _phase_violations(document: Mapping[str, Any]) -> list[Violation]:
    """A swimlane diagram's phases: known steps, each in one phase, in the order run.

    The phases partition the steps, as a gantt's groups partition its tasks, so
    every step's column (or row) of the grid is the author's and never the
    layout's guess. Order is checked on the arrows: one that runs from a later
    phase into an earlier one is a loop back only if the earlier step leads on to
    the later one again; otherwise the phases are written out of order, or the
    step is in the wrong one.
    """
    phases = document.get("phases")
    if not isinstance(phases, list):
        return []
    ids = [
        node["id"]
        for node in _listed(document, "nodes")
        if isinstance(node, dict) and isinstance(node.get("id"), str)
    ]
    known = set(ids)
    found: list[Violation] = []
    phase_of: dict[str, int] = {}
    for index, phase in enumerate(phases):
        if not isinstance(phase, dict):
            continue
        for position, member in enumerate(_listed(phase, "members")):
            if not isinstance(member, str):
                continue
            pointer = _pointer("phases", index, "members", position)
            if member not in known:
                close = get_close_matches(member, ids, n=1)
                found.append(
                    Violation(
                        pointer,
                        f"{member!r} is not the id of any step"
                        + (f" — did you mean {close[0]!r}?" if close else "."),
                    )
                )
            elif member in phase_of:
                earlier = phases[phase_of[member]].get("text")
                found.append(
                    Violation(
                        pointer,
                        f"{member!r} is already in the phase {earlier!r}. Phases do not "
                        f"overlap: a step happens in one phase, so name it once.",
                    )
                )
            else:
                phase_of[member] = index
    for index, identifier in enumerate(ids):
        if identifier not in phase_of and phase_of:
            found.append(
                Violation(
                    _pointer("nodes", index),
                    f"{identifier!r} is in no phase. With 'phases' given every step is in "
                    f"exactly one: add it to the 'members' of the phase it happens in.",
                )
            )
    if found:
        return found
    following: dict[str, list[str]] = {identifier: [] for identifier in ids}
    edges = _listed(document, "edges")
    for edge in edges:
        if isinstance(edge, dict) and edge.get("from") in known and edge.get("to") in known:
            following[edge["from"]].append(edge["to"])
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            continue
        source, target = edge.get("from"), edge.get("to")
        if source not in phase_of or target not in phase_of:
            continue
        if phase_of[source] <= phase_of[target] or _reaches(following, target, source):
            continue
        later = phases[phase_of[source]].get("text")
        earlier = phases[phase_of[target]].get("text")
        found.append(
            Violation(
                _pointer("edges", index),
                f"this arrow runs from {source!r} in the phase {later!r} back to {target!r} "
                f"in the earlier phase {earlier!r}, and nothing leads from {target!r} on to "
                f"{source!r}, so it is not a loop back. The phases are out of order, or one "
                f"of the two steps is in the wrong phase: list the phases in the order the "
                f"process runs.",
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
    # Member → its region's place in its composite, for a composite with regions.
    region_of: dict[str, int] = {}
    for index, group in enumerate(groups_raw):
        if not isinstance(group, dict) or not isinstance(group.get("id"), str):
            continue
        found.extend(_composite_shape(group, index))
        for members, prefix, region in _composite_parts(group):
            for position, member in enumerate(members):
                if not isinstance(member, str):
                    continue
                pointer = _pointer("groups", index, *prefix, "members", position)
                if member not in known:
                    found.append(
                        Violation(
                            pointer,
                            f"{member!r} is not the id of any state or group in this document",
                        )
                    )
                elif member == group["id"]:
                    found.append(Violation(pointer, "a group cannot contain itself"))
                elif member in parent:
                    where = (
                        f"another region of {parent[member]!r}"
                        if parent[member] == group["id"] and region_of.get(member) != region
                        else repr(parent[member])
                    )
                    found.append(
                        Violation(
                            pointer,
                            f"{member!r} is already inside {where}. A state is in one "
                            f"composite or none, and in one of its regions; nest the groups "
                            f"instead.",
                        )
                    )
                else:
                    parent[member] = group["id"]
                    if region is not None:
                        region_of[member] = region
            entry = (
                group.get("initial")
                if region is None
                else _listed(group, "regions")[region].get("initial")
            )
            if isinstance(entry, str) and entry not in members:
                found.append(
                    Violation(
                        _pointer("groups", index, *prefix, "initial"),
                        f"{entry!r} is not a member of "
                        + (
                            f"{group['id']!r}. A composite is entered "
                            if region is None
                            else f"this region of {group['id']!r}. A region starts "
                        )
                        + "at one of its own states.",
                    )
                )

    def entered(identifier: str, pointer: str) -> bool:
        """Whether naming `identifier` as a target lands on a state; reported if not."""
        group = groups.get(identifier)
        if group is None or isinstance(group.get("initial"), str) or "regions" in group:
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
    flattened = [
        {**group, "members": [m for members, _, _ in _composite_parts(group) for m in members]}
        for group in groups_raw
        if isinstance(group, dict)
    ]
    found.extend(_self_containment(transitions, flattened, frozenset(groups)))
    found.extend(_loop_violations(transitions, frozenset(groups), "transitions"))
    found.extend(_crossing_regions(transitions, parent, region_of))
    found.extend(_bar_violations(document, parent, region_of))
    found.extend(_region_initials(document, groups, parent, region_of))
    forks = {
        state["id"]
        for state in _listed(document, "states")
        if isinstance(state, dict) and state.get("role") == "fork"
    }

    # Two ways out of one state on the same event and guard: which one is taken?
    # A fork's are all taken at once, which is what a fork is.
    seen: dict[tuple[str, str, str], tuple[int, str]] = {}
    for index, transition in enumerate(transitions):
        if not isinstance(transition, dict):
            continue
        source, target = transition.get("from"), transition.get("to")
        if source in forks:
            continue
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
            queue.extend(_composite_entries(group))
            continue
        for scope in (current, *ancestors(current)):
            reached.add(scope)
            queue.extend(leaving.get(scope, ()))
            # Entering any state of a composite with regions enters the others at theirs.
            if scope in groups and "regions" in groups[scope]:
                queue.extend(_composite_entries(groups[scope]))

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


def _composite_parts(
    group: Mapping[str, Any],
) -> list[tuple[list[Any], tuple[str | int, ...], int | None]]:
    """A composite's member lists: its `members`, or each region's, with where each sits."""
    regions = group.get("regions")
    if isinstance(regions, list):
        return [
            (
                region["members"] if isinstance(region.get("members"), list) else [],
                ("regions", number),
                number,
            )
            for number, region in enumerate(regions)
            if isinstance(region, dict)
        ]
    members = group.get("members")
    return [(members if isinstance(members, list) else [], (), None)]


def _composite_shape(group: Mapping[str, Any], index: int) -> list[Violation]:
    """A composite lists its `members` or its `regions` — one, not both, not neither."""
    if "regions" not in group:
        if "members" in group:
            return []
        return [
            Violation(
                _pointer("groups", index),
                f"composite {group['id']!r} has no 'members'. List the states inside it, "
                f"or its 'regions' when parts of it run at once.",
            )
        ]
    if "members" in group:
        return [
            Violation(
                _pointer("groups", index, "members"),
                f"composite {group['id']!r} has both 'members' and 'regions'. With regions "
                f"every member belongs to one of them: move these into the regions.",
            )
        ]
    if "initial" in group:
        return [
            Violation(
                _pointer("groups", index, "initial"),
                f"composite {group['id']!r} has regions, and entering it enters every region "
                f"at its own 'initial'. Drop this; each region names where it starts.",
            )
        ]
    return []


def _composite_entries(group: Mapping[str, Any]) -> list[str]:
    """Where entering a composite lands: its `initial`, or every region's."""
    if "regions" in group:
        return [
            region["initial"]
            for region in _listed(group, "regions")
            if isinstance(region, dict) and isinstance(region.get("initial"), str)
        ]
    return [str(group["initial"])]


def _regions_above(
    identifier: str, parent: Mapping[str, str], region_of: Mapping[str, int]
) -> dict[str, int]:
    """Each composite with regions that `identifier` is inside, and which region."""
    found: dict[str, int] = {}
    current = identifier
    while current in parent and parent[current] not in found:
        if current in region_of:
            found[parent[current]] = region_of[current]
        current = parent[current]
    return found


def _bar_violations(
    document: Mapping[str, Any], parent: Mapping[str, str], region_of: Mapping[str, int]
) -> list[Violation]:
    """What a fork or join bar may not be, and the words every other state needs.

    A bar is a pseudo-state the machine passes through at once (UML's fork and
    join): it has no name, nothing to wait for, and a fixed count of ways in and
    out. A fork splits one transition into one per region of a composite, so its
    arrows must end in different regions of one composite — two in one region
    would put the machine in two of its states at once, and arrows to states in
    no region would claim a concurrency the machine has nowhere to hold. A join
    is the same rule read backwards.
    """
    found: list[Violation] = []
    bars: dict[str, str] = {}
    for index, state in enumerate(_listed(document, "states")):
        if not isinstance(state, dict) or not isinstance(state.get("id"), str):
            continue
        role = state.get("role")
        if role in STATE_BARS:
            bars[state["id"]] = str(role)
            if "text" in state:
                found.append(
                    Violation(
                        _pointer("states", index, "text"),
                        f"a {role} is drawn as a bar with no words. Drop 'text'; name the "
                        f"state the machine is in before or after it instead.",
                    )
                )
        elif "text" not in state:
            found.append(Violation(_pointer("states", index, "text"), "'text' is required"))
    if not bars:
        return found

    def refuse_naming(pointer: str, name: object, what: str) -> None:
        if isinstance(name, str) and name in bars:
            found.append(
                Violation(
                    pointer,
                    f"{name!r} is a {bars[name]} bar, which the machine passes through at "
                    f"once and is never in, so it cannot be {what}. Name a state.",
                )
            )

    refuse_naming("/initial", document.get("initial"), "where the machine starts")
    for index, name in enumerate(_listed(document, "final")):
        refuse_naming(_pointer("final", index), name, "where the machine ends")
    for index, group in enumerate(_listed(document, "groups")):
        if not isinstance(group, dict):
            continue
        refuse_naming(_pointer("groups", index, "initial"), group.get("initial"), "an entry")
        for number, region in enumerate(_listed(group, "regions")):
            if isinstance(region, dict):
                refuse_naming(
                    _pointer("groups", index, "regions", number, "initial"),
                    region.get("initial"),
                    "where a region starts",
                )

    into: dict[str, list[int]] = {bar: [] for bar in bars}
    out: dict[str, list[int]] = {bar: [] for bar in bars}
    transitions = _listed(document, "transitions")
    for index, transition in enumerate(transitions):
        if not isinstance(transition, dict):
            continue
        source, target = transition.get("from"), transition.get("to")
        if isinstance(source, str) and source in bars:
            if source == target:
                found.append(
                    Violation(
                        _pointer("transitions", index, "to"),
                        f"{source!r} is a {bars[source]} bar, and a bar is passed through, "
                        f"not stayed in: it has no self-loop.",
                    )
                )
                continue
            out[source].append(index)
            if "event" in transition:
                found.append(
                    Violation(
                        _pointer("transitions", index, "event"),
                        f"this transition leaves the {bars[source]} bar {source!r}, which "
                        f"the machine passes through at once, so there is no event to wait "
                        f"for. Put the event on the transition into the bar.",
                    )
                )
            if bars[source] == "fork" and "guard" in transition:
                found.append(
                    Violation(
                        _pointer("transitions", index, "guard"),
                        f"a fork starts every one of its arrows at once, so none of them "
                        f"can be guarded (UML forbids it). Put the guard on the transition "
                        f"into {source!r}.",
                    )
                )
        if isinstance(target, str) and target in bars and target != source:
            into[target].append(index)
            if bars[target] == "join":
                for part in ("event", "guard"):
                    if part in transition:
                        found.append(
                            Violation(
                                _pointer("transitions", index, part),
                                f"a join is passed when every arrow into it has arrived, "
                                f"each as its state completes, so an arrow into "
                                f"{target!r} has no {part} (UML forbids it). Move it to "
                                f"the transition into this arrow's state, or out of "
                                f"{target!r}.",
                            )
                        )

    for index, state in enumerate(_listed(document, "states")):
        if not isinstance(state, dict) or state.get("id") not in bars:
            continue
        bar = str(state["id"])
        kind = bars[bar]
        single, many = (into, out) if kind == "fork" else (out, into)
        one_way, many_way = ("in", "out") if kind == "fork" else ("out", "in")
        if len(single[bar]) != 1:
            found.append(
                Violation(
                    _pointer("transitions", single[bar][1], "to" if kind == "fork" else "from")
                    if len(single[bar]) > 1
                    else _pointer("states", index),
                    f"the {kind} {bar!r} has {len(single[bar])} transitions {one_way}; a "
                    f"{kind} has exactly one, "
                    + (
                        "which it splits into one per region."
                        if kind == "fork"
                        else "which leaves once every region has arrived."
                    ),
                )
            )
        if len(many[bar]) < 2:
            found.append(
                Violation(
                    _pointer("states", index),
                    f"the {kind} {bar!r} has {len(many[bar])} transition"
                    f"{'' if len(many[bar]) == 1 else 's'} {many_way}; a {kind} has two or "
                    f"more, one per region of a composite. With one, draw a plain "
                    f"transition instead.",
                )
            )
            continue
        ends = [
            (number, transitions[number].get("to" if kind == "fork" else "from"))
            for number in many[bar]
        ]
        found.extend(_bar_regions(bar, kind, ends, parent, region_of))
    return found


def _region_initials(
    document: Mapping[str, Any],
    groups: Mapping[str, Mapping[str, Any]],
    parent: Mapping[str, str],
    region_of: Mapping[str, int],
) -> list[Violation]:
    """Each region with no `initial` that the machine can enter without saying where.

    Entering a composite enters every region at its `initial`, and so does
    entering one state of one region for the others. Only a fork says where each
    region it reaches starts, so a region may go without an `initial` exactly when
    every way into its composite is a fork with an arrow into it.
    """
    bars = {
        state["id"]: state.get("role")
        for state in _listed(document, "states")
        if isinstance(state, dict) and state.get("role") in STATE_BARS
    }

    def inside(identifier: str, composite: str) -> bool:
        current: str | None = identifier
        seen: set[str] = set()
        while current is not None and current not in seen:
            if current == composite:
                return True
            seen.add(current)
            current = parent.get(current)
        return False

    found: list[Violation] = []
    for index, group in enumerate(_listed(document, "groups")):
        if not isinstance(group, dict) or group.get("id") not in groups:
            continue
        composite = str(group["id"])
        regions = _listed(group, "regions")
        missing = {
            number
            for number, region in enumerate(regions)
            if isinstance(region, dict) and "initial" not in region
        }
        if not missing:
            continue
        # Why each region would be entered with nowhere to start: the first reason.
        reasons: dict[int, str] = {}
        initial = document.get("initial")
        if isinstance(initial, str) and inside(initial, composite):
            for number in missing:
                reasons.setdefault(number, "the machine starts inside it")
        forks: dict[str, set[int]] = {}
        for transition in _listed(document, "transitions"):
            if not isinstance(transition, dict):
                continue
            source, target = transition.get("from"), transition.get("to")
            if not isinstance(source, str) or not isinstance(target, str):
                continue
            if not inside(target, composite) or inside(source, composite):
                continue
            if target == composite:
                for number in missing:
                    reasons.setdefault(number, f"a transition from {source!r} enters it")
                continue
            region = _regions_above(target, parent, region_of).get(composite)
            if bars.get(source) == "fork":
                forks.setdefault(source, set()).add(region if region is not None else -1)
                continue
            for number in missing - {region}:
                reasons.setdefault(number, f"the transition from {source!r} to {target!r}")
        for fork, reached in forks.items():
            for number in missing - reached:
                reasons.setdefault(number, f"the fork {fork!r} has no arrow into it")
        for number in sorted(reasons):
            found.append(
                Violation(
                    _pointer("groups", index, "regions", number, "initial"),
                    f"this region of {composite!r} has no 'initial', and "
                    f"{reasons[number]}, so the machine would be in no state of it. Name "
                    f"where it starts, or reach it with an arrow from every fork into "
                    f"{composite!r}.",
                )
            )
    return found


def _bar_regions(
    bar: str,
    kind: str,
    ends: Sequence[tuple[int, object]],
    parent: Mapping[str, str],
    region_of: Mapping[str, int],
) -> list[Violation]:
    """A bar's far ends, each in a different region of one composite, or why not."""
    names = [end for _, end in ends if isinstance(end, str)]
    if len(names) != len(ends):
        return []
    above = [_regions_above(name, parent, region_of) for name in names]
    shared = set(above[0]).intersection(*above[1:])
    if any(len({regions[composite] for regions in above}) == len(names) for composite in shared):
        return []
    # The arrow that broke the rule: the first that shares a region with an
    # earlier one, or is in no region the others are in.
    position = next(
        (
            count - 1
            for count in range(2, len(names) + 1)
            if not any(
                len({regions[composite] for regions in above[:count]}) == count
                for composite in set(above[0]).intersection(*above[1:count])
            )
        ),
        len(names) - 1,
    )
    verb, end = ("starts", "end") if kind == "fork" else ("waits for", "start")
    return [
        Violation(
            _pointer("transitions", ends[position][0], "to" if kind == "fork" else "from"),
            f"the {kind} {bar!r} {verb} parts of the machine that run at once, so each of "
            f"its arrows must {end} in a different region of one composite state, and "
            f"{names[position]!r} is in no region the others share, or in the same region "
            f"as one of them. Give the composite 'regions', one per arrow.",
        )
    ]


def _crossing_regions(
    transitions: Sequence[Any], parent: Mapping[str, str], region_of: Mapping[str, int]
) -> list[Violation]:
    """Transitions from one region of a composite into another region of the same one.

    Regions are all current at once, so a state of one cannot hand the machine to
    a state of another: both are already running. UML forbids it, and there is no
    line to draw that would not claim the impossible.
    """

    def regions_above(identifier: str) -> dict[str, int]:
        return _regions_above(identifier, parent, region_of)

    found: list[Violation] = []
    for index, transition in enumerate(transitions):
        if not isinstance(transition, dict):
            continue
        source, target = transition.get("from"), transition.get("to")
        if not isinstance(source, str) or not isinstance(target, str):
            continue
        here, there = regions_above(source), regions_above(target)
        for composite, region in here.items():
            if composite in there and there[composite] != region:
                found.append(
                    Violation(
                        _pointer("transitions", index, "to"),
                        f"{source!r} and {target!r} are in different regions of "
                        f"{composite!r}, which run at once: neither can hand the machine to "
                        f"the other. Join them through a state outside {composite!r}, or "
                        f"put both in one region.",
                    )
                )
                break
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

    found.extend(_async_reply_violations(document))
    found.extend(_sequence_group_violations(document, participants))
    found.extend(_fragment_violations(document, message_ids))
    return found


def _async_reply_violations(document: Mapping[str, Any]) -> list[Violation]:
    """A `weak` reply whose only question was an `async` message, which awaits none.

    An asynchronous message is sent and the sender carries on: there is no call
    for a dashed reply to return from. An answer that comes later is a message of
    its own, sent back the other way.
    """
    found: list[Violation] = []
    calls: set[tuple[str, str]] = set()
    sent: set[tuple[str, str]] = set()
    for index, message in enumerate(_listed(document, "messages")):
        if not isinstance(message, dict):
            continue
        source, target, role = message.get("from"), message.get("to"), message.get("role", "flow")
        if not isinstance(source, str) or not isinstance(target, str) or source == target:
            continue
        if role in ("flow", "strong"):
            calls.add((source, target))
        elif role == "async":
            sent.add((source, target))
        elif role == "weak" and (target, source) in sent and (target, source) not in calls:
            found.append(
                Violation(
                    _pointer("messages", index, "role"),
                    f"this reply answers {target!r}'s async message to {source!r}, and an "
                    f"async message awaits no reply. Send the answer as a message of its own "
                    f"(role 'async' or 'flow'), or make the question a call ('flow').",
                )
            )
    return found


def _sequence_refusal(violation: Violation, document: Mapping[str, Any]) -> Violation:
    """A structural refusal in a sequence diagram, told what this kind means by it."""
    parts = violation.pointer.split("/")
    if len(parts) == 4 and parts[1] == "participants" and parts[3] == "role":
        entries = document.get("participants")
        try:
            role = entries[int(parts[2])]["role"]  # type: ignore[index]
        except (TypeError, ValueError, IndexError, KeyError):
            return violation
        if role in ("person", "user", "human"):
            return Violation(
                violation.pointer,
                f"{role!r} is not a participant role here: a person taking part is "
                f"'actor', drawn as a stick figure over the lifeline.",
            )
    if len(parts) == 4 and parts[1] == "messages" and parts[3] == "role":
        entries = document.get("messages")
        try:
            role = entries[int(parts[2])]["role"]  # type: ignore[index]
        except (TypeError, ValueError, IndexError, KeyError):
            return violation
        if role in ("asynchronous", "signal", "event", "sync", "call", "reply", "return"):
            return Violation(
                violation.pointer,
                f"{role!r} is not a message role: a call is 'flow', its reply 'weak', a "
                f"message nobody waits on 'async', and the exchange that matters 'strong'.",
            )
    return violation


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

    # A star: one entity in the middle, the rest round it. A class hierarchy is
    # drawn general above specific, which a ring round a middle cannot keep.
    middles = [
        index
        for index, entity in enumerate(_listed(document, "entities"))
        if isinstance(entity, dict) and entity.get("centre") is True
    ]
    for index in middles[1:]:
        found.append(
            Violation(
                _pointer("entities", index, "centre"),
                "a second entity says it is the centre. A star has one middle: the fact "
                "table. Drop 'centre' here, or split the diagram into one star per fact.",
            )
        )
    if middles:
        for index, edge in enumerate(_listed(document, "edges")):
            if isinstance(edge, dict) and edge.get("role") in HIERARCHY_ROLES:
                found.append(
                    Violation(
                        _pointer("entities", middles[0], "centre"),
                        f"edge {index} is {edge['role']!r}, and a class hierarchy is drawn "
                        f"general above specific; arranged round a middle, a subclass could "
                        f"land above its parent. Drop 'centre', or draw the hierarchy in a "
                        f"diagram of its own.",
                    )
                )
                break
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
                f"{name!r} is not a field: how much of a task is complete is `done`, a "
                f"number from 0 to 100, drawn as a band inside the bar.",
            )
    return violation


def _row_marks_violations(
    task: Mapping[str, Any], index: int, span: tuple[float, float] | None
) -> list[Violation]:
    """A task's `events` and `iterations`: on an interval, inside it, cycles in order.

    A milestone is a moment, so nothing falls inside it and nothing goes round
    it. An event or a cycle outside the bar would claim a delivery the task does
    not cover. Cycles are written in order and may touch, end to start, as one
    iteration hands on to the next; overlapping, two arcs would be drawn over
    one stretch of bar and the reader could not tell which return is which.
    """
    found: list[Violation] = []
    present = [name for name in ("events", "iterations") if task.get(name)]
    if "at" in task:
        for name in present:
            found.append(
                Violation(
                    _pointer("tasks", index, name),
                    f"a milestone is a moment, so nothing falls inside it and it has no "
                    f"{name}. Make the task an interval with `start` and `end`, or put each "
                    f"event on the task it belongs to.",
                )
            )
        return found
    if span is None or span[0] == span[1]:
        return found
    low, high = span

    def within(value: Any, pointer: str) -> bool:
        if not _is_number(value):
            return False
        if low <= value <= high:
            return True
        found.append(
            Violation(
                pointer,
                f"{_figure(value)} is outside this task, which runs {_figure(low)} to "
                f"{_figure(high)}: it would be drawn off its bar. Move it, or widen the task.",
            )
        )
        return False

    for position, event in enumerate(_listed(task, "events")):
        if isinstance(event, dict):
            within(event.get("at"), _pointer("tasks", index, "events", position, "at"))
    previous: float | None = None
    for position, cycle in enumerate(_listed(task, "iterations")):
        if not isinstance(cycle, dict):
            continue
        here = _pointer("tasks", index, "iterations", position)
        sound = within(cycle.get("start"), f"{here}/start") & within(
            cycle.get("end"), f"{here}/end"
        )
        if not sound:
            continue
        start, end = float(cycle["start"]), float(cycle["end"])
        if end <= start:
            found.append(
                Violation(
                    f"{here}/end",
                    f"this iteration ends at {_figure(end)}, which is not after it starts at "
                    f"{_figure(start)}. An iteration runs forward and its arc turns back.",
                )
            )
            continue
        if previous is not None and start < previous:
            found.append(
                Violation(
                    f"{here}/start",
                    f"this iteration starts at {_figure(start)}, before the one written "
                    f"before it ends at {_figure(previous)}. Iterations follow one another: "
                    f"write them in order, each starting where or after the last ends.",
                )
            )
        previous = end
    return found


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
        done = float(task["done"]) if _is_number(task.get("done")) else None
        if done is not None and not 0 <= done <= 100:
            found.append(
                Violation(
                    _pointer("tasks", index, "done"),
                    f"{_figure(done)} is not a share of a task: `done` runs from 0 (not "
                    f"started) to 100 (finished).",
                )
            )
        elif "done" in task and "at" in given:
            found.append(
                Violation(
                    _pointer("tasks", index, "done"),
                    "a milestone is a moment, so it is reached or not and has no part done. "
                    "Drop `done`, or make the task an interval with `start` and `end`.",
                )
            )
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
        found.extend(_row_marks_violations(task, index, span))
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


#: Why a venn has no place for a field an author may reach for.
VENN_REFUSED: Final = {
    "edges": "a Venn diagram has nothing to connect: what relates the sets is their overlap",
    "subset_of": (
        "a set wholly inside another is scopes nested inside scopes, which is `rings`; a "
        "Venn diagram draws sets that overlap"
    ),
    "size": (
        "the circles are equal on purpose: a Venn diagram says what overlaps, not how much. "
        "A number belongs in the text, or in a `chart`"
    ),
    "value": (
        "the circles are equal on purpose: a Venn diagram says what overlaps, not how much. "
        "A number belongs in the text, or in a `chart`"
    ),
}


def _venn_refusal(violation: Violation) -> Violation:
    """A structural refusal in a venn, told what this kind means by it."""
    parts = violation.pointer.split("/")
    name = parts[-1]
    if name in VENN_REFUSED and "is not a known field" in violation.message:
        return Violation(violation.pointer, f"{name!r}: {VENN_REFUSED[name]}.")
    if parts[1:] == ["sets"] and "needs at least" in violation.message:
        return Violation(
            violation.pointer,
            "a Venn diagram needs 2 to 4 sets: one set overlaps nothing. Say what it holds in "
            "a sentence, or as a list.",
        )
    return violation


def _venn_violations(document: Mapping[str, Any]) -> list[Violation]:
    """Set ids that are unique, and regions whose memberships land and differ."""
    found: list[Violation] = []
    sets: dict[str, int] = {}
    for index, entry in enumerate(_listed(document, "sets")):
        identifier = entry.get("id") if isinstance(entry, dict) else None
        if not isinstance(identifier, str):
            continue
        if identifier in sets:
            found.append(
                Violation(_pointer("sets", index, "id"), f"duplicate set id {identifier!r}")
            )
            continue
        sets[identifier] = index
    seen: dict[frozenset[str], int] = {}
    for index, region in enumerate(_listed(document, "regions")):
        members = region.get("in") if isinstance(region, dict) else None
        if not isinstance(members, list) or not all(isinstance(m, str) for m in members):
            continue
        named: set[str] = set()
        landed = True
        for position, member in enumerate(members):
            if member not in sets:
                landed = False
                found.append(
                    Violation(
                        _pointer("regions", index, "in", position),
                        f"{member!r} is not the id of any set" + _closest(member, sets),
                    )
                )
            elif member in named:
                landed = False
                found.append(
                    Violation(
                        _pointer("regions", index, "in", position),
                        f"{member!r} is named twice: `in` lists each set the region is in once.",
                    )
                )
            named.add(member)
        if not landed or not named:
            continue
        key = frozenset(named)
        if key in seen:
            found.append(
                Violation(
                    _pointer("regions", index, "in"),
                    f"region {seen[key]} is already the region in exactly these sets. A region "
                    f"is drawn once: put both texts in one.",
                )
            )
            continue
        seen[key] = index
    if len(sets) == VENN_SET_MAX:
        for index, region in enumerate(_listed(document, "regions")):
            text = region.get("text") if isinstance(region, dict) else None
            if not isinstance(text, str):
                continue
            shown = text.replace("**", "").replace("`", "").replace("\n", " ")
            if len(shown) > VENN_FOUR_TEXT_MAX:
                found.append(
                    Violation(
                        _pointer("regions", index, "text"),
                        f"{len(shown)} characters is more than a region of four sets holds — "
                        f"{VENN_FOUR_TEXT_MAX} at most. With four sets the smallest regions "
                        f"are small: write a count or a word or two, and say the rest in the "
                        f"caption.",
                    )
                )
    return found


#: Why a journey has no place for a field an author may reach for.
JOURNEY_REFUSED: Final = {
    "edges": (
        "a journey's stages are already in order, left to right, and the feeling line joins "
        "them; an arrow between two stages adds nothing. Branching steps are a `flow`"
    ),
    "personas": (
        "a journey map is one person's: two feeling lines cross and erase each other. Draw "
        "one journey per person, with the same stages"
    ),
    "score": (
        "a feeling is a name, not a score — a numeric axis invites reading 3.4 off a sketch. "
        "Name the levels in `feelings`, worst first, and give each stage one by name"
    ),
    "value": (
        "a feeling is a name, not a score — a numeric axis invites reading 3.4 off a sketch. "
        "Name the levels in `feelings`, worst first, and give each stage one by name"
    ),
}


def _journey_refusal(violation: Violation) -> Violation:
    """A structural refusal in a journey, told what this kind means by it."""
    parts = violation.pointer.split("/")
    name = parts[-1]
    if name in JOURNEY_REFUSED and "is not a known field" in violation.message:
        return Violation(violation.pointer, f"{name!r}: {JOURNEY_REFUSED[name]}.")
    numeric = violation.message in ("expected string, got int", "expected string, got float")
    if numeric and (name == "feeling" or parts[1:2] == ["feelings"]):
        return Violation(violation.pointer, f"a number: {JOURNEY_REFUSED['score']}.")
    if parts[1:] == ["feelings"] and "needs at least" in violation.message:
        return Violation(
            violation.pointer,
            "a journey needs at least 2 feelings: with one level the line is flat and says "
            "nothing. Name the levels the person moves between, worst first.",
        )
    if parts[1:] == ["stages"] and "needs at least" in violation.message:
        return Violation(
            violation.pointer,
            "a journey needs at least 2 stages: a feeling at one stage is a sentence, not a line.",
        )
    return violation


def _journey_violations(document: Mapping[str, Any]) -> list[Violation]:
    """Feelings and row ids that are unique, and stages whose names land."""
    found: list[Violation] = []
    feelings: dict[str, int] = {}
    for index, feeling in enumerate(_listed(document, "feelings")):
        if not isinstance(feeling, str):
            continue
        if feeling in feelings:
            found.append(
                Violation(
                    _pointer("feelings", index),
                    f"{feeling!r} is already level {feelings[feeling]}: each level is named once.",
                )
            )
            continue
        feelings[feeling] = index
    rows: dict[str, int] = {}
    for index, entry in enumerate(_listed(document, "rows")):
        identifier = entry.get("id") if isinstance(entry, dict) else None
        if not isinstance(identifier, str):
            continue
        if identifier in rows:
            found.append(
                Violation(_pointer("rows", index, "id"), f"duplicate row id {identifier!r}")
            )
            continue
        rows[identifier] = index
    has_rows = isinstance(document.get("rows"), list)
    for index, stage in enumerate(_listed(document, "stages")):
        if not isinstance(stage, dict):
            continue
        feeling = stage.get("feeling")
        if isinstance(feeling, str) and feelings and feeling not in feelings:
            found.append(
                Violation(
                    _pointer("stages", index, "feeling"),
                    f"{feeling!r} is not one of the feelings, {', '.join(feelings)}"
                    + (_closest(feeling, feelings) or ". Name one of them, or add it there."),
                )
            )
        named: set[str] = set()
        details = stage.get("details")
        for position, detail in enumerate(details if isinstance(details, list) else []):
            row = detail.get("row") if isinstance(detail, dict) else None
            if not isinstance(row, str):
                continue
            where = _pointer("stages", index, "details", position, "row")
            if not has_rows:
                found.append(
                    Violation(
                        where,
                        "this journey has no `rows`, so a detail has no row to go in. Declare "
                        "the rows (what the person does, where, what gets in the way), or drop "
                        "'details'.",
                    )
                )
            elif row not in rows:
                found.append(
                    Violation(where, f"{row!r} is not the id of any row" + _closest(row, rows))
                )
            elif row in named:
                found.append(
                    Violation(
                        where,
                        f"{row!r} is named twice in this stage: a stage has one cell per row. "
                        f"Put both in one text.",
                    )
                )
            named.add(row)
    return found


#: Why a treemap has no place for a field an author may reach for.
TREEMAP_REFUSED: Final = {
    "edges": (
        "a treemap's parts are related by being one whole; there is nothing to connect. "
        "Where a quantity goes from one place to another is a `flow`"
    ),
    "percent": (
        "drawspec takes each part's share from its `amount` and the total, so the areas "
        "cannot disagree with the numbers. Write the amount"
    ),
    "share": (
        "drawspec takes each part's share from its `amount` and the total, so the areas "
        "cannot disagree with the numbers. Write the amount"
    ),
    "children": (
        "a treemap has one level of grouping: a part names its group in `group`, and a "
        "group holds parts, not groups. Past one level it is a disk-usage tool's output"
    ),
    "parts": (
        "a group does not list its parts: each part names its group in `group`. Groups do not nest"
    ),
    "groups": (
        "a treemap has one level of grouping, so a group holds parts, never groups. Draw a "
        "treemap per group instead"
    ),
    "group": (
        "a treemap has one level of grouping, so a group holds parts, never groups. Draw a "
        "treemap per group instead"
    ),
}


def _treemap_refusal(violation: Violation) -> Violation:
    """A structural refusal in a treemap, told what this kind means by it."""
    parts = violation.pointer.split("/")
    name = parts[-1]
    in_group = parts[1:2] == ["groups"] and len(parts) == 4
    if name == "value" and parts[1:2] == ["parts"] and len(parts) == 4:
        return Violation(
            violation.pointer,
            "'value': a treemap part's number is its `amount` — how much of the total it is, "
            "in the treemap's `unit`.",
        )
    if "is not a known field" in violation.message and name in TREEMAP_REFUSED:
        if name in ("parts", "groups", "group") and not in_group:
            return violation
        return Violation(violation.pointer, f"{name!r}: {TREEMAP_REFUSED[name]}.")
    if name == "amount" and parts[1:2] == ["parts"] and "greater than" in violation.message:
        return Violation(
            violation.pointer,
            "a part's amount is its area, so it must be more than 0. A part of nothing is not "
            "drawn: leave it out, or say so in the caption.",
        )
    if parts[1:] == ["parts"] and "needs at least" in violation.message:
        return Violation(
            violation.pointer,
            "a treemap needs at least 2 parts: one part of a total is the total. Say it in a "
            "sentence.",
        )
    return violation


def _treemap_violations(document: Mapping[str, Any]) -> list[Violation]:
    """Group ids that are unique, parts whose groups land, and no empty group."""
    found: list[Violation] = []
    groups: dict[str, int] = {}
    for index, entry in enumerate(_listed(document, "groups")):
        identifier = entry.get("id") if isinstance(entry, dict) else None
        if not isinstance(identifier, str):
            continue
        if identifier in groups:
            found.append(
                Violation(_pointer("groups", index, "id"), f"duplicate group id {identifier!r}")
            )
            continue
        groups[identifier] = index
    named: set[str] = set()
    for index, part in enumerate(_listed(document, "parts")):
        group = part.get("group") if isinstance(part, dict) else None
        if not isinstance(group, str):
            continue
        if group not in groups:
            found.append(
                Violation(
                    _pointer("parts", index, "group"),
                    f"{group!r} is not the id of any group"
                    + (_closest(group, groups) if groups else ": this treemap has no `groups`."),
                )
            )
            continue
        named.add(group)
    for identifier, index in groups.items():
        if identifier not in named:
            found.append(
                Violation(
                    _pointer("groups", index),
                    f"no part names the group {identifier!r}, so it would be an empty frame. "
                    f'Give it parts with `"group": "{identifier}"`, or drop it.',
                )
            )
    return found


#: Why a sankey has no place for a field an author may reach for.
SANKEY_REFUSED: Final = {
    "edges": ("a sankey's connections are its `flows`, each with the `amount` that goes along it"),
    "column": (
        "a node's column is derived from the flows — sources on the left, ends on the right, "
        "each node one column past the longest way in. Write the flows"
    ),
    "rank": (
        "a node's column is derived from the flows — sources on the left, ends on the right, "
        "each node one column past the longest way in. Write the flows"
    ),
    "percent": (
        "drawspec draws each band from its `amount`, so the thicknesses cannot disagree with "
        "the numbers. Write the amount"
    ),
    "share": (
        "drawspec draws each band from its `amount`, so the thicknesses cannot disagree with "
        "the numbers. Write the amount"
    ),
    "label": (
        "a band carries no words: what goes where is read from the nodes' totals, written "
        "beside each bar. Name the destination as a node instead"
    ),
}


def _sankey_refusal(violation: Violation) -> Violation:
    """A structural refusal in a sankey, told what this kind means by it."""
    parts = violation.pointer.split("/")
    name = parts[-1]
    if name == "value" and parts[1:2] == ["flows"] and len(parts) == 4:
        return Violation(
            violation.pointer,
            "'value': a flow's number is its `amount` — how much goes from one node to the "
            "other, in the sankey's `unit`.",
        )
    if "is not a known field" in violation.message and name in SANKEY_REFUSED:
        return Violation(violation.pointer, f"{name!r}: {SANKEY_REFUSED[name]}.")
    if name == "amount" and parts[1:2] == ["flows"] and "greater than" in violation.message:
        return Violation(
            violation.pointer,
            "a flow's amount is its band's thickness, so it must be more than 0. A flow of "
            "nothing is not drawn: leave it out.",
        )
    if parts[1:] == ["nodes"] and "needs at least" in violation.message:
        return Violation(
            violation.pointer,
            "a sankey needs at least 2 nodes: an amount goes from one to another.",
        )
    return violation


def sankey_columns(ids: Sequence[str], flows: Sequence[tuple[str, str]]) -> dict[str, int]:
    """Each node's column: one past the longest way in, every end in the last column.

    `flows` must join known ids and close no loop. A node no flow touches is in the
    first column. Ends — nodes with nothing leaving — are moved to the last column,
    so every arrival lines up on the right edge, the way the quantity is read.
    """
    incoming: dict[str, list[str]] = {identifier: [] for identifier in ids}
    leaving: set[str] = set()
    for source, target in flows:
        incoming[target].append(source)
        leaving.add(source)
    column: dict[str, int] = {}

    def depth(identifier: str) -> int:
        if identifier not in column:
            column[identifier] = 0
            column[identifier] = max(
                (depth(source) + 1 for source in incoming[identifier]), default=0
            )
        return column[identifier]

    for identifier in ids:
        depth(identifier)
    last = max(column.values(), default=0)
    for identifier in ids:
        if identifier not in leaving and incoming[identifier]:
            column[identifier] = last
    return column


def sankey_amount(value: float, unit: str) -> str:
    """An amount as written: no trailing zeros, the unit after a space (`%` after none)."""
    text = f"{value:.10g}"
    if not unit:
        return text
    return f"{text}{unit}" if unit == "%" else f"{text} {unit}"


def _sankey_violations(document: Mapping[str, Any]) -> list[Violation]:
    """Ids that land, no loop, every middle node balanced, four columns, no hairline.

    Each is a fact about the numbers and the joins alone, so each is refused here,
    at its pointer, before any layout runs: an imbalance, a loop or a band too thin
    to see is never a question a smaller type size could answer.
    """
    found: list[Violation] = []
    written = document.get("unit")
    unit = written if isinstance(written, str) else ""
    nodes: dict[str, int] = {}
    for index, entry in enumerate(_listed(document, "nodes")):
        identifier = entry.get("id") if isinstance(entry, dict) else None
        if not isinstance(identifier, str):
            continue
        if identifier in nodes:
            found.append(
                Violation(_pointer("nodes", index, "id"), f"duplicate node id {identifier!r}")
            )
            continue
        nodes[identifier] = index

    # The flows that land, in written order: (index, from, to, amount).
    flows: list[tuple[int, str, str, float]] = []
    pairs: dict[tuple[str, str], int] = {}
    balance: list[tuple[str, str, float]] = []
    reaches: dict[str, set[str]] = {identifier: {identifier} for identifier in nodes}
    for index, entry in enumerate(_listed(document, "flows")):
        if not isinstance(entry, dict):
            continue
        ends = []
        for side in ("from", "to"):
            name = entry.get(side)
            if not isinstance(name, str):
                continue
            if name not in nodes:
                found.append(
                    Violation(
                        _pointer("flows", index, side),
                        f"{name!r} is not the id of any node" + _closest(name, nodes),
                    )
                )
                continue
            ends.append(name)
        if len(ends) != 2:
            continue
        source, target = ends
        if source == target:
            found.append(
                Violation(
                    _pointer("flows", index, "to"),
                    f"a flow from {source!r} to itself: an amount that stays where it is does "
                    "not flow. Leave it out.",
                )
            )
            continue
        amount = entry.get("amount")
        number = float(amount) if isinstance(amount, int | float) else 0.0
        balance.append((source, target, max(number, 0.0)))
        if (source, target) in pairs:
            found.append(
                Violation(
                    _pointer("flows", index),
                    f"a second flow from {source!r} to {target!r} (the first is "
                    f"/flows/{pairs[(source, target)]}): add the amounts into one flow.",
                )
            )
            continue
        if target in reaches[source]:
            found.append(
                Violation(
                    _pointer("flows", index),
                    f"the flow from {source!r} to {target!r} closes a loop — {target!r} already "
                    "leads back to it. A quantity does not flow backwards in a sankey: leave "
                    "this flow out, or draw the loop as a `cycle` or a `flow`.",
                )
            )
            continue
        pairs[(source, target)] = index
        # Everything that reached `source` now reaches `target` and what it leads to.
        downstream = {name for name, before in reaches.items() if target in before}
        for name in downstream:
            reaches[name] |= reaches[source]
        flows.append((index, source, target, max(number, 0.0)))

    touched = {name for _, source, target, _ in flows for name in (source, target)}
    for identifier, index in nodes.items():
        if identifier not in touched and not any(
            isinstance(entry, dict) and identifier in (entry.get("from"), entry.get("to"))
            for entry in _listed(document, "flows")
        ):
            found.append(
                Violation(
                    _pointer("nodes", index),
                    f"no flow reaches or leaves {identifier!r}, so it would be a bar of "
                    "nothing. Give it a flow, or leave it out.",
                )
            )

    into: dict[str, float] = dict.fromkeys(nodes, 0.0)
    out: dict[str, float] = dict.fromkeys(nodes, 0.0)
    for source, target, amount in balance:
        out[source] += amount
        into[target] += amount
    for identifier, index in nodes.items():
        arrived, left = into[identifier], out[identifier]
        if not (arrived and left) or abs(arrived - left) <= 1e-9 * max(arrived, left):
            continue
        more, verb = ("takes in", "sends on") if arrived > left else ("sends on", "takes in")
        difference = abs(arrived - left)
        found.append(
            Violation(
                _pointer("nodes", index),
                f"{identifier!r} {more} {sankey_amount(max(arrived, left), unit)} and {verb} "
                f"{sankey_amount(min(arrived, left), unit)}: the drawing would have to invent "
                f"where the difference of {sankey_amount(difference, unit)} "
                f"{'went' if arrived > left else 'came from'}. Add a flow of "
                f"{sankey_amount(difference, unit)} "
                f"{'to' if arrived > left else 'from'} a named node — `Lost`, `Idle`, a `note` "
                "— or correct the amounts.",
            )
        )

    columns = sankey_columns(list(nodes), [(source, target) for _, source, target, _ in flows])
    for identifier, index in nodes.items():
        if columns.get(identifier, 0) >= SANKEY_COLUMN_MAX:
            found.append(
                Violation(
                    _pointer("nodes", index),
                    f"{identifier!r} is {columns[identifier] + 1} steps from where the quantity "
                    f"starts, and a sankey can be read at {SANKEY_COLUMN_MAX} columns at most. "
                    "Draw one sankey per stage — the last column of one is the first of the "
                    "next — or merge the steps between.",
                )
            )
            break

    # The fullest column's total sets the scale: every node is as tall as what
    # passes through it, and a flow that skips a column passes through it too.
    totals: dict[int, float] = {}
    for identifier in nodes:
        column = columns.get(identifier, 0)
        totals[column] = totals.get(column, 0.0) + max(into[identifier], out[identifier])
    for _, source, target, amount in flows:
        for column in range(columns[source] + 1, columns[target]):
            totals[column] = totals.get(column, 0.0) + amount
    fullest = max(totals.values(), default=0.0)
    least = fullest * SANKEY_MIN_BAND / SANKEY_BAND
    ratio = round(SANKEY_BAND / SANKEY_MIN_BAND)
    for index, source, target, amount in flows:
        if 0 < amount < least:
            found.append(
                Violation(
                    _pointer("flows", index, "amount"),
                    f"the flow from {source!r} to {target!r} is {sankey_amount(amount, unit)} of "
                    f"the {sankey_amount(fullest, unit)} in the fullest column — under 1/{ratio} "
                    "of it, a band too thin to see. Merge the small flows into one flow to a "
                    "named `note` node (`Other`), and say what it holds in the caption.",
                )
            )
    return found


#: Why a numberline has no place for a field an author may reach for.
NUMBERLINE_REFUSED: Final = {
    "edges": (
        "a number line joins nothing: what relates two values is where they sit on the one scale"
    ),
    "series": (
        "a number line has one scale and no data series. Two values per item is a `scatter`; "
        "a number that changes over something is a `chart`"
    ),
    "axes": "a number line has one scale, `axis`. Two values per item is a `scatter`",
    "value": "a point's place on the scale is `at`",
    "id": "nothing names a point or a range, so it takes no id",
    "date": (
        "a number line places numbers. For events in time, use a `timeline`; for a plan, a "
        "`gantt` with its axis in a unit you name"
    ),
}

#: What a numberline says to a string where a number belongs.
NUMBERLINE_NUMBERS: Final = (
    "a number line places numbers on its scale. A date or a named time is a `timeline`; "
    "a named scale with no numbers takes `axis.ends` and still places by number between "
    "`min` and `max`."
)


def _numberline_refusal(violation: Violation, document: Mapping[str, Any]) -> Violation:
    """A structural refusal in a numberline, told what this kind means by it."""
    parts = violation.pointer.split("/")
    name = parts[-1]
    unknown = "is not" in violation.message and "field" in violation.message
    if name in NUMBERLINE_REFUSED and unknown:
        return Violation(violation.pointer, f"{name!r}: {NUMBERLINE_REFUSED[name]}.")
    if name in ("at", "from", "to", "min", "max", "step"):
        value: object = document
        for part in parts[1:]:
            try:
                value = value[int(part) if isinstance(value, list) else part]  # type: ignore[index]
            except (TypeError, ValueError, IndexError, KeyError):
                return violation
        if isinstance(value, str):
            return Violation(violation.pointer, f"{value!r} is not a number: {NUMBERLINE_NUMBERS}")
    return violation


def _numberline_violations(document: Mapping[str, Any]) -> list[Violation]:
    """A scale that runs one way, and points and ranges that sit on it.

    Every value is inside `[min, max]` — an arrow is how a range says it goes on
    — a range has at least one end and ends after it starts, an open end is an
    end that exists, two points are not one dot, and a named scale carries no
    numbers.
    """
    found: list[Violation] = []
    axis = document.get("axis")
    axis = axis if isinstance(axis, dict) else {}
    low: float | None = axis.get("min") if _is_number(axis.get("min")) else None
    high: float | None = axis.get("max") if _is_number(axis.get("max")) else None
    if low is not None and high is not None and high <= low:
        found.append(
            Violation(
                _pointer("axis", "max"),
                f"the scale ends at {high}, not after its start {low}: `max` is the right-hand "
                f"end, and more than `min`.",
            )
        )
        low = high = None
    ends = axis.get("ends")
    if isinstance(ends, list):
        if len(ends) > 2:
            found.append(
                Violation(
                    _pointer("axis", "ends"),
                    f"{len(ends)} ends: a scale has two, the low end's words then the high end's.",
                )
            )
        for name in ("step", "unit"):
            if name in axis:
                found.append(
                    Violation(
                        _pointer("axis", name),
                        f"a scale named by its `ends` draws no numbers, so it takes no "
                        f"{name!r}. Drop it, or drop the ends and number the scale.",
                    )
                )
    step: Any = axis.get("step")
    if low is not None and high is not None and _is_number(step) and step > 0:
        count = (high - low) / step
        if count > NUMBERLINE_TICK_MAX:
            found.append(
                Violation(
                    _pointer("axis", "step"),
                    f"a step of {step} cuts {low} to {high} into {count:.0f} ticks, and the "
                    f"numbers crowd past {NUMBERLINE_TICK_MAX}. Take a larger step, or a "
                    f"narrower scale.",
                )
            )

    def outside(value: Any, pointer: str) -> None:
        if not _is_number(value) or low is None or high is None:
            return
        if value < low or value > high:
            found.append(
                Violation(
                    pointer,
                    f"{value} is off the scale, which runs {low} to {high}. Widen the axis — "
                    f"or, for a range that goes on, leave this end out and it is drawn as an "
                    f"arrow.",
                )
            )

    points = _listed(document, "points")
    ranges = _listed(document, "ranges")
    if not points and not ranges:
        found.append(
            Violation(
                "/points",
                "a number line needs something on it: at least one of `points` and `ranges`. "
                "A bare scale says nothing a sentence would not.",
            )
        )
    seen: dict[float, int] = {}
    for index, point in enumerate(points):
        if not isinstance(point, dict):
            continue
        at: Any = point.get("at")
        outside(at, _pointer("points", index, "at"))
        if _is_number(at):
            if at in seen:
                found.append(
                    Violation(
                        _pointer("points", index, "at"),
                        f"point {seen[at]} is already at {at}, and two dots at one value are "
                        f"one dot. Put both texts in one point.",
                    )
                )
            else:
                seen[at] = index
    for index, entry in enumerate(ranges):
        if not isinstance(entry, dict):
            continue
        start: Any = entry.get("from")
        end: Any = entry.get("to")
        if "from" not in entry and "to" not in entry:
            found.append(
                Violation(
                    _pointer("ranges", index),
                    "a range with neither `from` nor `to` is the whole line. Say that in the "
                    "title, or give the range an end.",
                )
            )
        for name, bound in (("from_open", "from"), ("to_open", "to")):
            if name in entry and bound not in entry:
                found.append(
                    Violation(
                        _pointer("ranges", index, name),
                        f"this range has no {bound!r}, so it runs on past the axis: an end that "
                        f"is not there cannot be open. Drop {name!r}, or give the range its "
                        f"{bound!r}.",
                    )
                )
        outside(start, _pointer("ranges", index, "from"))
        outside(end, _pointer("ranges", index, "to"))
        if _is_number(start) and _is_number(end) and end <= start:
            found.append(
                Violation(
                    _pointer("ranges", index, "to"),
                    f"the range ends at {end}, not after its start {start}. For a single value, "
                    f"use a point.",
                )
            )
    return found


#: Why a bar model has no place for a field an author may reach for.
BARMODEL_REFUSED: Final = {
    "edges": "a bar model joins nothing: what relates two bars is their lengths, side by side",
    "axes": (
        "a bar model has no axis: the numbers are written in the parts. Values compared "
        "against an axis are a `chart`"
    ),
    "series": (
        "a bar model has no data series: the numbers are written in the parts. Values "
        "compared against an axis are a `chart`"
    ),
    "total": (
        "a total is a brace over the bar: "
        '`{"over": ["the bar\'s id"], "amount": 60}`, checked against its parts'
    ),
    "unknown": 'an unknown part still has a size: give its `amount` or `units`, and `text: "?"`',
    "value": "a part's or a brace's size is its `amount`",
}


def _barmodel_refusal(violation: Violation) -> Violation:
    """A structural refusal in a bar model, told what this kind means by it."""
    name = violation.pointer.split("/")[-1]
    unknown = "is not" in violation.message and "field" in violation.message
    if name in BARMODEL_REFUSED and unknown:
        return Violation(violation.pointer, f"{name!r}: {BARMODEL_REFUSED[name]}.")
    return violation


def _barmodel_violations(document: Mapping[str, Any]) -> list[Violation]:
    """Parts with one size each, in one kind of size, and braces whose sums hold.

    Every part is an `amount` or `units`, never both or neither, and a document is
    all amounts or all units. Ids are unique across bars and parts. A brace spans
    side-by-side parts of one bar or consecutive whole bars, and its `amount` is
    checked: the sum of the parts it spans, or — with units — the same worth per
    unit as every other brace with an amount.
    """
    found: list[Violation] = []
    ids: dict[str, tuple[str, int, int]] = {}
    mode = ""
    mode_at = ""
    count = 0
    bars = _listed(document, "bars")
    for index, bar in enumerate(bars):
        if not isinstance(bar, dict):
            continue
        identifier = bar.get("id")
        if isinstance(identifier, str):
            if identifier in ids:
                found.append(
                    Violation(_pointer("bars", index, "id"), f"duplicate id {identifier!r}")
                )
            else:
                ids[identifier] = ("bar", index, -1)
        boxes = 0
        for position, part in enumerate(_listed(bar, "parts")):
            if not isinstance(part, dict):
                continue
            count += 1
            here = _pointer("bars", index, "parts", position)
            name = part.get("id")
            if isinstance(name, str):
                if name in ids:
                    found.append(Violation(f"{here}/id", f"duplicate id {name!r}"))
                else:
                    ids[name] = ("part", index, position)
            sizes = [field for field in ("amount", "units") if field in part]
            if not sizes:
                found.append(
                    Violation(
                        here,
                        "a part needs a size, or its length would be a guess: an `amount` (its "
                        "length in proportion) or `units` (that many equal boxes). An unknown "
                        'part still has one — write its `amount` and `"text": "?"`.',
                    )
                )
                continue
            if len(sizes) == 2:
                found.append(
                    Violation(
                        f"{here}/units",
                        "a part is an `amount` or a number of `units`, not both. Drop one.",
                    )
                )
                continue
            size = sizes[0]
            if not mode:
                mode, mode_at = size, f"{here}/{size}"
            elif size != mode:
                found.append(
                    Violation(
                        f"{here}/{size}",
                        f"this document's parts are sized by {mode!r} (from {mode_at}), and a "
                        f"unit has no length against a number. Size every part one way: give "
                        f"the units an amount each, or draw every part in units.",
                    )
                )
            units = part.get("units")
            if size == "units" and isinstance(units, int) and not isinstance(units, bool):
                boxes += units
                if boxes > BARMODEL_UNIT_MAX and boxes - units <= BARMODEL_UNIT_MAX:
                    found.append(
                        Violation(
                            f"{here}/units",
                            f"this bar is {boxes} unit boxes, and past {BARMODEL_UNIT_MAX} a "
                            f"reader counts boxes instead of seeing the ratio. Simplify the "
                            f"ratio, or let one box stand for more.",
                        )
                    )
    if bars and count == 1:
        found.append(
            Violation(
                _pointer("bars", 0, "parts"),
                "one part in one bar compares nothing: a bar model needs a second part, or a "
                "second bar. One number is a sentence.",
            )
        )

    def size_of(bar: int, position: int) -> float:
        part = _listed(bars[bar], "parts")[position]
        value: Any = part.get(mode) if isinstance(part, dict) else None
        return float(value) if _is_number(value) else math.nan

    worth: tuple[float, int] | None = None
    for index, brace in enumerate(_listed(document, "braces")):
        if not isinstance(brace, dict):
            continue
        if "amount" not in brace and "text" not in brace:
            found.append(
                Violation(
                    _pointer("braces", index),
                    "a brace says what the stretch adds up to: give it an `amount` (checked), "
                    'or `"text": "?"` for the unknown.',
                )
            )
        over = brace.get("over")
        if not isinstance(over, list) or not all(isinstance(item, str) for item in over):
            continue
        resolved: list[tuple[str, int, int]] = []
        for position, item in enumerate(over):
            if item not in ids:
                found.append(
                    Violation(
                        _pointer("braces", index, "over", position),
                        f"{item!r} is not the id of any bar or part" + _closest(item, ids),
                    )
                )
            elif ids[item] in resolved:
                found.append(
                    Violation(
                        _pointer("braces", index, "over", position),
                        f"{item!r} is named twice: a brace spans each thing once.",
                    )
                )
            else:
                resolved.append(ids[item])
        if len(resolved) != len(over):
            continue
        kinds = {kind for kind, _, _ in resolved}
        spanned: list[tuple[int, int]] = []
        if kinds == {"part"}:
            rows = {bar for _, bar, _ in resolved}
            columns = sorted(position for _, _, position in resolved)
            if len(rows) > 1:
                found.append(
                    Violation(
                        _pointer("braces", index, "over"),
                        "these parts are in different bars, and a brace spans one stretch of "
                        "one bar. For a total over bars, name the bars.",
                    )
                )
                continue
            if columns != list(range(columns[0], columns[0] + len(columns))):
                found.append(
                    Violation(
                        _pointer("braces", index, "over"),
                        "these parts are not side by side, and a brace spans one stretch. Name "
                        "the parts between them too, or use two braces.",
                    )
                )
                continue
            (row,) = rows
            spanned = [(row, column) for column in columns]
        elif kinds == {"bar"}:
            rows_list = sorted(bar for _, bar, _ in resolved)
            if rows_list != list(range(rows_list[0], rows_list[0] + len(rows_list))):
                found.append(
                    Violation(
                        _pointer("braces", index, "over"),
                        "these bars are not next to each other, and an upright brace spans "
                        "consecutive bars. Reorder the bars, or use two braces.",
                    )
                )
                continue
            spanned = [
                (row, column)
                for row in rows_list
                for column in range(len(_listed(bars[row], "parts")))
            ]
        else:
            found.append(
                Violation(
                    _pointer("braces", index, "over"),
                    "a brace spans parts of one bar or whole bars, not both. Name the bar "
                    "for the whole of it.",
                )
            )
            continue
        value: Any = brace.get("amount")
        if not _is_number(value) or not mode:
            continue
        total = sum(size_of(row, column) for row, column in spanned)
        if math.isnan(total):
            continue
        if mode == "amount":
            if not math.isclose(total, value, rel_tol=1e-9, abs_tol=1e-9):
                found.append(
                    Violation(
                        _pointer("braces", index, "amount"),
                        f"the parts this brace spans add up to {total:g}, not {value:g}. The "
                        f"model would teach the wrong sum: fix a part's amount, or the brace's.",
                    )
                )
        elif worth is None:
            worth = (value / total, index)
        elif not math.isclose(value / total, worth[0], rel_tol=1e-9):
            found.append(
                Violation(
                    _pointer("braces", index, "amount"),
                    f"this brace makes one unit worth {value / total:g}, and brace {worth[1]} "
                    f"makes it {worth[0]:g}. Every unit in a bar model is the same size: fix "
                    f"one of the two.",
                )
            )
    return found


#: Why a waterfall has no place for a field an author may reach for.
WATERFALL_REFUSED: Final = {
    "edges": "a waterfall's connectors join each bar to the next for you, at the running sum",
    "series": (
        "a waterfall is one sequence of bars, totals and steps. Several series against an "
        "axis are a `chart`"
    ),
    "axes": (
        "a waterfall has one numeric axis, `axis`, and its bars in order across. Values "
        "against two axes are a `chart`"
    ),
    "value": "a step's size is its signed `amount`, and a total's is its `total`",
    "subtotal": "a subtotal is a `total` between the first bar and the last, checked",
    "start": "the start is the first bar, a `total`",
    "end": "the end is the last bar, a `total`, checked against the steps",
    "unit": "the unit goes in the axis label: `Borrowing, £ billion`",
}


def _waterfall_refusal(violation: Violation) -> Violation:
    """A structural refusal in a waterfall, told what this kind means by it."""
    name = violation.pointer.split("/")[-1]
    unknown = "is not" in violation.message and "field" in violation.message
    if name in WATERFALL_REFUSED and unknown:
        return Violation(violation.pointer, f"{name!r}: {WATERFALL_REFUSED[name]}.")
    return violation


def _waterfall_violations(document: Mapping[str, Any]) -> list[Violation]:
    """Bars that are each a total or a step, and totals that are the running sum.

    The first and the last bar are totals; a total straight after a total says
    nothing; a step of 0 is not drawn. Every total after the first is checked
    against the sum of the bars before it, and refused with the difference.
    """
    found: list[Violation] = []
    bars = [bar for bar in _listed(document, "bars") if isinstance(bar, dict)]
    if len(bars) != len(_listed(document, "bars")):
        return found
    running: float | None = None
    previous = ""
    scale = max(
        (
            abs(float(bar[field]))
            for bar in bars
            for field in ("total", "amount")
            if _is_number(bar.get(field))
        ),
        default=1.0,
    )
    tolerance = max(scale, 1.0) * 1e-9
    for index, bar in enumerate(bars):
        here = _pointer("bars", index)
        sizes = [field for field in ("total", "amount") if field in bar]
        if not sizes:
            found.append(
                Violation(
                    here,
                    "a bar is a `total` (it stands on zero) or a signed `amount` (a step "
                    "from the running sum). Give it one.",
                )
            )
            running, previous = None, ""
            continue
        if len(sizes) == 2:
            found.append(
                Violation(
                    f"{here}/amount",
                    "a bar is a `total` or an `amount`, not both. A subtotal is a `total` "
                    "on a bar of its own.",
                )
            )
            running, previous = None, ""
            continue
        size = sizes[0]
        number = bar[size]
        if not _is_number(number):
            running, previous = None, ""
            continue
        if size == "amount":
            if index == 0:
                found.append(
                    Violation(
                        f"{here}/amount",
                        "a waterfall starts from a total the reader knows: make the first "
                        'bar `{"text": …, "total": …}`, and the steps follow it.',
                    )
                )
            if number == 0:
                found.append(
                    Violation(
                        f"{here}/amount",
                        "a step of 0 moves nothing and has no bar to draw. Leave it out, or "
                        "say it in the caption.",
                    )
                )
            if running is not None:
                running += float(number)
            previous = "amount"
            continue
        if index and previous == "total":
            found.append(
                Violation(
                    f"{here}/total",
                    "a total straight after a total repeats it: a subtotal comes after the "
                    "steps it adds up. Drop one of the two.",
                )
            )
        elif running is not None and abs(running - float(number)) > tolerance:
            difference = float(number) - running
            found.append(
                Violation(
                    f"{here}/total",
                    f"the bars before this total add up to {_figure(running)}, and it says "
                    f"{_figure(float(number))} — {_figure(abs(difference))} "
                    f"{'more' if difference > 0 else 'less'}. A total in a waterfall is the "
                    f"running sum, or the chart shows a step that is not there: fix a step or "
                    f"the total.",
                )
            )
            previous = "total"
            continue
        running = float(number)
        previous = "total"
    if bars and previous == "amount" and running is not None:
        found.append(
            Violation(
                _pointer("bars", len(bars) - 1),
                f"a waterfall ends at a total, and the steps reach {_figure(running)}. Add a "
                f'last bar: `{{"text": …, "total": {_figure(running)}}}`.',
            )
        )
    elif bars and previous == "amount":
        found.append(
            Violation(
                _pointer("bars", len(bars) - 1),
                "a waterfall ends at a total: add a last bar with a `total`.",
            )
        )
    return found


#: Why a clock has no place for a field an author may reach for.
CLOCK_REFUSED: Final = {
    "edges": "two faces are related by `since`, which shades the time between them",
    "seconds": (
        "a teaching face has two hands, and no lesson asks a pupil to read a seconds hand: "
        "say the seconds in the `text`"
    ),
    "date": "a clock reads a time of day; dates belong on a `timeline`",
    "hands": "the hands are placed by the `time`; leave it out for a face with none",
    "hour": 'the hands are placed by the `time`: `"time": "3:15"`',
    "minute": 'the hands are placed by the `time`: `"time": "3:15"`',
    "angle": "the hands are placed by the `time`",
    "numerals": "the numerals are the sheet's, at the top: one face style per sheet",
    "readout": "the readout is the sheet's, at the top: a worksheet hides every answer",
    "label": "the words under a face are its `text`",
}


def _clock_refusal(violation: Violation) -> Violation:
    """A structural refusal on a clock sheet, told what this kind means by it."""
    name = violation.pointer.split("/")[-1]
    unknown = "is not" in violation.message and "field" in violation.message
    if name in CLOCK_REFUSED and unknown:
        return Violation(violation.pointer, f"{name!r}: {CLOCK_REFUSED[name]}.")
    return violation


#: A clock time: one or two digits of hour, 0-23, then two of minute.
_CLOCK_TIME: Final = re.compile(r"^([01]?[0-9]|2[0-3]):([0-5][0-9])$")


def clock_minutes(text: str) -> int | None:
    """Minutes past midnight for an `H:MM` time, or None when it is not one."""
    match = _CLOCK_TIME.match(text)
    if match is None:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))


def _clock_time_problem(text: Any) -> str | None:
    """Why `text` is not a clock time, or None when it is one."""
    if not isinstance(text, str):
        return None  # The structural check has already said so.
    if clock_minutes(text) is not None:
        return None
    if re.match(r"^\d{1,2}:\d{2}:\d{2}$", text.strip()):
        return (
            f"{text!r} has seconds. A teaching face has an hour hand and a minute hand, and "
            f"no lesson asks a pupil to read a seconds hand: write `H:MM`."
        )
    if re.search(r"(?i)\d\s*[ap]\.?m\.?\s*$", text):
        return (
            f"{text!r}: a time is written on the 24-hour clock, `H:MM` — `15:15` for a quarter "
            f"past three in the afternoon. The face is the same; the readout writes it as given."
        )
    if re.search(r"\d{4}-\d{2}|T\d", text):
        return f"{text!r} carries a date. A clock reads a time of day: `H:MM`."
    return (
        f"{text!r} is not a time: write `H:MM` or `HH:MM`, from `0:00` to `23:59` — "
        f"`9:05`, `15:40`."
    )


def _clock_violations(document: Mapping[str, Any]) -> list[Violation]:
    """Each face's times well formed, and each `since` before its time, within 12 hours."""
    found: list[Violation] = []
    for index, face in enumerate(_listed(document, "clocks")):
        if not isinstance(face, dict):
            continue
        here = _pointer("clocks", index)
        for name in ("time", "since"):
            problem = _clock_time_problem(face.get(name))
            if problem is not None:
                found.append(Violation(f"{here}/{name}", problem))
        if "since" not in face:
            continue
        if "time" not in face:
            found.append(
                Violation(
                    f"{here}/since",
                    "a face with no hands has nothing to measure from: give it a `time`, or "
                    "leave `since` out.",
                )
            )
            continue
        start, end = clock_minutes(str(face["since"])), clock_minutes(str(face["time"]))
        if start is None or end is None:
            continue
        gap = (end - start) % (24 * 60)
        if gap == 0 or gap >= CLOCK_SINCE_MAX:
            found.append(
                Violation(
                    f"{here}/since",
                    f"{face['since']!r} must be before {face['time']!r} and less than 12 hours "
                    f"before it: past that the hour hand has gone all the way round, and the "
                    f"face cannot show how long. Say a longer time in the `text`.",
                )
            )
    return found


#: Why a RAG row has no place for a field an author may reach for.
RAG_REFUSED: Final = {
    "edges": "a RAG report rates each row on its own; there is nothing to connect",
    "columns": (
        "one rating per row. Cost, time and scope rated separately are a table, or one "
        "report per dimension"
    ),
    "status": (
        "a rating is `rag` (`red`, `amber`, `green`); `status` marks a change on `flow` and `tree`"
    ),
    "colour": (
        "the rating is `rag`, and the theme draws it as a word, a shape and a colour. Write "
        '`"rag": "green"`'
    ),
    "score": (
        "a risk score is a number on a likelihood-by-impact grid: a `matrix` with a `scale`. "
        "Here the row carries its `rag`"
    ),
    "likelihood": "a likelihood-by-impact grid is a `matrix` with a `scale`",
    "impact": "a likelihood-by-impact grid is a `matrix` with a `scale`",
    "owner": "an owner is a caption: a second line in `text`, after a newline",
    "comment": "the commentary is `note`",
    "commentary": "the commentary is `note`",
}

#: What an author may mean by a rating or a trend outside the vocabulary.
RAG_VALUE_ADVICE: Final = (
    "Three ratings, as boards settle on: choose the nearer of the two in a split rating "
    "(`amber/green`) and say why in the `note`; a finished workstream is `green` with "
    "*Complete* in its note."
)
RAG_TREND_ADVICE: Final = (
    "Say what the change means — `better`, `same` or `worse` — not which way an arrow "
    "points: an arrow up means *improving* in one report and *risk rising* in another."
)


def _rag_refusal(violation: Violation) -> Violation:
    """A structural refusal in a RAG report, told what this kind means by it."""
    name = violation.pointer.split("/")[-1]
    unknown = "is not" in violation.message and "field" in violation.message
    if name in RAG_REFUSED and unknown:
        return Violation(violation.pointer, f"{name!r}: {RAG_REFUSED[name]}.")
    if "is not one of" in violation.message and name in ("rag", "trend"):
        advice = RAG_VALUE_ADVICE if name == "rag" else RAG_TREND_ADVICE
        return Violation(violation.pointer, violation.message.split(".")[0] + ". " + advice)
    return violation


#: Why a meter has no place for a field an author may reach for.
METER_REFUSED: Final = {
    "edges": "a meter has nothing to connect: each one is read against its own scale",
    "series": "a meter is one amount against a scale. Values against an axis are a `chart`",
    "axes": "a meter's scale is its `min` and `max`. Values against two axes are a `chart`",
    "value": "a meter's reading is its `amount`",
    "goal": "a thermometer's goal is the top of its scale, `max`; a stage under it is a `target`",
    "percent": (
        'write the reading as it is, with `"unit": "%"` and `"max": 100` for a percentage, '
        "or the amount and the whole it is out of"
    ),
    "style": (
        "the style is the document's, at the top: one panel, one style, so like is "
        "compared with like. Two styles are two documents"
    ),
    "from": "a band runs from the end of the one before it, or from the scale's start",
    "colour": (
        "a band is told by its words and drawn in the theme's tones. Write the word the "
        "reader is taught — `Green`, or `On track`"
    ),
}


def _meter_refusal(violation: Violation) -> Violation:
    """A structural refusal in a meter panel, told what this kind means by it."""
    name = violation.pointer.split("/")[-1]
    unknown = "is not" in violation.message and "field" in violation.message
    if name in METER_REFUSED and unknown:
        return Violation(violation.pointer, f"{name!r}: {METER_REFUSED[name]}.")
    return violation


def _meter_violations(document: Mapping[str, Any]) -> list[Violation]:
    """Each meter's reading, target and bands inside its scale, and bands its style takes.

    A bar, a bullet and a thermometer start at zero (their length is their
    amount); bands go on a bullet, which needs them, and a dial; they rise, and
    the last one ends the scale.
    """
    found: list[Violation] = []
    style = document.get("style", "bar")
    if style not in METER_STYLES:
        return found
    for index, meter in enumerate(_listed(document, "meters")):
        if not isinstance(meter, dict):
            continue
        here = _pointer("meters", index)
        high: Any = meter.get("max")
        if "min" in meter and style not in METER_MIN_STYLES:
            found.append(
                Violation(
                    f"{here}/min",
                    f"a {style}'s length is its amount, so its scale starts at 0. A reading "
                    f"on a scale that starts elsewhere — a temperature — is a "
                    f'`"style": "dial"`, whose needle reads a position.',
                )
            )
            continue
        low: Any = meter.get("min", 0)
        if not (_is_number(high) and _is_number(low)):
            continue
        if high <= low:
            found.append(
                Violation(
                    f"{here}/max",
                    f"the scale runs from {_figure(float(low))} up to `max`, so `max` must be "
                    f"more than {_figure(float(low))}.",
                )
            )
            continue
        for name in ("amount", "target"):
            reading: Any = meter.get(name)
            if _is_number(reading) and not low <= reading <= high:
                found.append(
                    Violation(
                        f"{here}/{name}",
                        f"{_figure(float(reading))} is outside the scale, "
                        f"{_figure(float(low))} to {_figure(float(high))}: a meter has nowhere "
                        f"to point past its ends. Change `max`"
                        + (" or `min`." if style in METER_MIN_STYLES else ".")
                        + (
                            " A goal beaten is a full thermometer with the amount in the caption."
                            if style == "thermometer" and name == "amount"
                            else ""
                        ),
                    )
                )
        bands = meter.get("bands")
        if bands is not None and style not in METER_BAND_STYLES:
            advice = (
                'a bar on named bands is a bullet graph: say `"style": "bullet"`.'
                if style == "bar"
                else "a thermometer fills toward one goal. Bands on a scale are a "
                '`"style": "bullet"` or a `"dial"`.'
            )
            found.append(Violation(f"{here}/bands", advice))
            continue
        if bands is None and style == "bullet":
            found.append(
                Violation(
                    here,
                    "a bullet graph is a bar on named bands: give it `bands` — "
                    '`[{"text": "Poor", "to": …}, …]` — or say `"style": "bar"`.',
                )
            )
            continue
        if not isinstance(bands, list):
            continue
        start = float(low)
        for position, band in enumerate(bands):
            if not isinstance(band, dict) or not _is_number(band.get("to")):
                start = float("nan")
                continue
            end = float(band["to"])
            if not end > start:
                found.append(
                    Violation(
                        f"{here}/bands/{position}/to",
                        f"bands rise along the scale, each from the end of the one before: "
                        f"this one must end above {_figure(start)}.",
                    )
                )
            start = end
        last: Any = bands[-1] if bands else None
        if (
            isinstance(last, dict)
            and _is_number(last.get("to"))
            and not math.isclose(float(last["to"]), float(high))
        ):
            found.append(
                Violation(
                    f"{here}/bands/{len(bands) - 1}/to",
                    f"the last band ends the scale: its `to` is `max`, "
                    f"{_figure(float(high))}. Bands cover the scale once, with no gap at the "
                    f"top.",
                )
            )
    return found


#: Why a pie has no place for a field an author may reach for.
PIE_REFUSED: Final = {
    "edges": "a pie's parts are related by being one whole; there is nothing to connect",
    "series": "a pie is one total split into parts. Values against an axis are a `chart`",
    "axes": "a pie has no axes. Values against an axis are a `chart`",
    "value": "a part's size is its `amount`",
    "percent": (
        "drawspec takes each share from the `amount`s and their sum, so the angles cannot "
        'disagree with the numbers. Write the amount; for percentages, set `"unit": "%"`'
    ),
    "share": (
        "drawspec takes each share from the `amount`s and their sum, so the angles cannot "
        'disagree with the numbers. Write the amount; for percentages, set `"unit": "%"`'
    ),
    "angle": "a sector's angle is its share of the total, computed from its `amount`",
    "total": (
        "a pie's total is the sum of its amounts, so it cannot disagree with them. Say it "
        "in the title if the reader needs it"
    ),
    "groups": "a pie has one level of parts. Parts in groups are a `treemap`",
    "group": "a pie has one level of parts. Parts in groups are a `treemap`",
    "donut": 'a ring instead of a disc is house style: a theme\'s `[pie] shape = "donut"`',
    "hole": 'a ring instead of a disc is house style: a theme\'s `[pie] shape = "donut"`',
}


def _pie_refusal(violation: Violation) -> Violation:
    """A structural refusal in a pie, told what this kind means by it."""
    parts = violation.pointer.split("/")
    name = parts[-1]
    unknown = "is not" in violation.message and "field" in violation.message
    if name in PIE_REFUSED and unknown:
        return Violation(violation.pointer, f"{name!r}: {PIE_REFUSED[name]}.")
    if parts[1:] == ["parts"] and "needs at least" in violation.message:
        return Violation(
            violation.pointer,
            "a pie needs at least 2 parts: one part of a total is the total. Say it in a sentence.",
        )
    if name == "amount" and parts[1:2] == ["parts"] and "greater than" in violation.message:
        return Violation(
            violation.pointer,
            "a part's amount is its angle, so it must be more than 0. A part of nothing is "
            "not drawn: leave it out.",
        )
    return violation


def _pie_violations(document: Mapping[str, Any]) -> list[Violation]:
    """One remainder at most, no sliver, and percentages that add up to 100."""
    found: list[Violation] = []
    parts = [part for part in _listed(document, "parts") if isinstance(part, dict)]
    notes = [
        index
        for index, part in enumerate(_listed(document, "parts"))
        if isinstance(part, dict) and part.get("role") == "note"
    ]
    for index in notes[1:]:
        found.append(
            Violation(
                _pointer("parts", index, "role"),
                f"part {notes[0]} is already the remainder: a pie has one `note` part, "
                f"`Everything else`. Merge the two.",
            )
        )
    amounts = [float(part["amount"]) for part in parts if _is_number(part.get("amount"))]
    if not amounts or len(amounts) != len(parts) or min(amounts) <= 0:
        return found
    total = float(sum(amounts))
    for index, amount in enumerate(amounts):
        if amount / total < PIE_SHARE_MIN:
            found.append(
                Violation(
                    _pointer("parts", index, "amount"),
                    f"this part is {100 * amount / total:.1f}% of the total, a sliver whose "
                    f"angle cannot be read — under {100 * PIE_SHARE_MIN:g}%. Merge it into one "
                    f'`"role": "note"` part with the others too small to see.',
                )
            )
    if document.get("unit") == "%" and abs(total - 100) > PIE_PERCENT_TOLERANCE:
        found.append(
            Violation(
                "/parts",
                f"these percentages add up to {_figure(total)}, not 100 — "
                f"{_figure(abs(total - 100))} {'over' if total > 100 else 'short'}, more "
                f"than rounding. A pie of percentages is the whole: fix a part, or add the "
                f"missing share as a `note` part.",
            )
        )
    return found


#: Why an argument map has no place for a field an author may reach for.
ARGUMENT_REFUSED: Final = {
    "edges": (
        "an argument map's structure is each point's `on`: the box it bears on. A point "
        "that bears on two boxes is two points"
    ),
    "nodes": "an argument map's boxes are its `claim` and its `points`",
    "parent": "the box a point bears on is its `on`",
    "children": "a point names the box it bears on with `on`; the points under a box follow",
    "side": "where a point goes is drawspec's: it hangs under the box it is `on`, in order",
}

#: What a third stance would be, and why there is none.
_STANCE_ADVICE: Final = (
    "A rebuttal or an objection is an `against` on the point it answers; its name follows "
    "from the depth, and the tags already read *because*, *but*, *but* down the chain"
)


def _inference_objection(names: Sequence[str]) -> str:
    joined = " and ".join(f"{name!r}" for name in names)
    return (
        f"`on` names one box. An objection to how {joined} together support their box — an "
        f"inference objection — is an objection to the premise that links them, which the "
        f"argument leaves unstated. Write that premise as a point `with` them, and put the "
        f"objection `on` it."
    )


def _argument_refusal(violation: Violation, document: Mapping[str, Any]) -> Violation:
    """A structural refusal in an argument map, told what this kind means by it."""
    parts = violation.pointer.split("/")
    name = parts[-1]
    unknown = "is not a known field" in violation.message or (
        "is not" in violation.message and "field" in violation.message
    )
    if unknown and name in ARGUMENT_REFUSED:
        return Violation(violation.pointer, f"{name!r}: {ARGUMENT_REFUSED[name]}.")
    if name == "stance" and "is not one of" in violation.message:
        return Violation(
            violation.pointer,
            violation.message.split(".")[0] + f". {_STANCE_ADVICE}.",
        )
    if name == "on" and "expected" in violation.message and len(parts) == 4:
        points = document.get("points")
        entry = points[int(parts[2])] if isinstance(points, list) else None
        names = entry.get("on") if isinstance(entry, dict) else None
        if isinstance(names, list) and all(isinstance(each, str) for each in names):
            return Violation(violation.pointer, _inference_objection(names))
    if name == "role" and "is not one of" in violation.message:
        return Violation(
            violation.pointer,
            violation.message.split(".")[0]
            + ". Stance is not a role: `step`, `emphasis` for the decisive point, `note` for "
            "evidence or a source.",
        )
    if parts[1:] == ["points"] and "needs at least" in violation.message:
        return Violation(
            violation.pointer,
            "an argument map needs at least one point: a claim alone is a sentence.",
        )
    return violation


def _argument_violations(document: Mapping[str, Any]) -> list[Violation]:
    """Ids that resolve, a tree under the claim, co-premises that match, and depth."""
    found: list[Violation] = []
    claim = document.get("claim")
    if isinstance(claim, str) and not claim.strip():
        found.append(Violation("/claim", "the claim is the contention: it needs words."))
    entries = [
        (index, entry)
        for index, entry in enumerate(_listed(document, "points"))
        if isinstance(entry, dict)
    ]
    ids: dict[str, int] = {}
    for index, entry in entries:
        name = entry.get("id")
        text = entry.get("text")
        if isinstance(text, str) and not text.strip():
            found.append(Violation(_pointer("points", index, "text"), "a point needs words."))
        if not isinstance(name, str):
            continue
        if name == "claim":
            found.append(
                Violation(
                    _pointer("points", index, "id"),
                    "'claim' names the contention, so no point may take it as its id.",
                )
            )
        elif name in ids:
            found.append(
                Violation(
                    _pointer("points", index, "id"),
                    f"{name!r} is already the id of point {ids[name]}: ids are unique.",
                )
            )
        else:
            ids[name] = index
    by_id = {name: dict(entries)[index] for name, index in ids.items()}

    parent: dict[str, str] = {}
    for index, entry in entries:
        target = entry.get("on")
        name = entry.get("id")
        if not isinstance(target, str) or not isinstance(name, str):
            continue
        where = _pointer("points", index, "on")
        if target == "claim" or target in ids:
            if target == name and name != "claim":
                found.append(Violation(where, "a point cannot bear on itself."))
            elif ids.get(name) == index:
                parent[name] = target
            continue
        pieces = [piece.strip() for piece in re.split(r"[+&,]", target)]
        if len(pieces) > 1 and all(piece in ids for piece in pieces):
            found.append(Violation(where, _inference_objection(pieces)))
        else:
            found.append(
                Violation(
                    where,
                    f"{target!r} is not `claim` or the id of a point. Known ids: "
                    f"{', '.join(sorted(ids)) or 'none'}.",
                )
            )

    # A tree: every chain of `on` ends at the claim, at most four deep.
    depth: dict[str, int] = {}
    for name in parent:
        chain: list[str] = []
        current = name
        while current != "claim" and current in parent and current not in chain:
            chain.append(current)
            current = parent[current]
        if current != "claim":
            if current in chain:
                index = ids[name]
                found.append(
                    Violation(
                        _pointer("points", index, "on"),
                        f"this `on` goes round in a circle ({' -> '.join([*chain, current])}): "
                        f"an argument is a tree under the claim.",
                    )
                )
            continue
        depth[name] = len(chain)
    for name, levels in depth.items():
        if levels > ARGUMENT_DEPTH_MAX:
            found.append(
                Violation(
                    _pointer("points", ids[name], "on"),
                    f"this point is {levels} levels below the claim, past what one argument "
                    f"map can be read at — {ARGUMENT_DEPTH_MAX} at most. Draw the point it "
                    f"answers as the claim of a map of its own.",
                )
            )

    # Co-premises: same box, same stance, a group of at most four.
    links: dict[str, set[str]] = {name: set() for name in ids}
    for index, entry in entries:
        name = entry.get("id")
        others = entry.get("with")
        if not isinstance(name, str) or ids.get(name) != index or not isinstance(others, list):
            continue
        for position, other in enumerate(others):
            where = _pointer("points", index, "with", position)
            if not isinstance(other, str):
                continue
            if other == name:
                found.append(Violation(where, "a point is not its own co-premise."))
                continue
            if other not in by_id:
                found.append(
                    Violation(where, f"{other!r} is not the id of a point; `with` names points.")
                )
                continue
            mate = by_id[other]
            if mate.get("on") != entry.get("on"):
                found.append(
                    Violation(
                        where,
                        f"{other!r} is `on` {mate.get('on')!r} and this point is `on` "
                        f"{entry.get('on')!r}: co-premises support the same box.",
                    )
                )
                continue
            if mate.get("stance") != entry.get("stance"):
                found.append(
                    Violation(
                        where,
                        f"{other!r} is {mate.get('stance')!r} and this point is "
                        f"{entry.get('stance')!r}: co-premises bear the same way.",
                    )
                )
                continue
            links[name].add(other)
            links[other].add(name)
    seen: set[str] = set()
    for name in ids:
        if name in seen or not links[name]:
            continue
        group: list[str] = []
        stack = [name]
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            group.append(current)
            stack.extend(links[current])
        if len(group) > ARGUMENT_GROUP_MAX:
            last = max(group, key=lambda member: ids[member])
            found.append(
                Violation(
                    _pointer("points", ids[last], "with"),
                    f"{len(group)} co-premises in one group, and a group can be read at "
                    f"{ARGUMENT_GROUP_MAX} at most. Premises that many usually hide a "
                    f"sub-argument: make some of them a point of their own, with its "
                    f"own reasons under it.",
                )
            )
    return found


#: Why a family tree has no place for a field an author may reach for.
FAMILYTREE_REFUSED: Final = {
    "edges": "a family tree's lines are its `couples`: partners, and the children of each",
    "nodes": "a family tree's symbols are its `people`",
    "groups": "a family's branches are drawn from its `couples`; split a tree by branch instead",
    "generation": (
        "generations are derived: a child is one row below its parents' couple, a partner "
        "shares their partner's row"
    ),
    "number": "people are numbered for you, left to right in each generation (II-3)",
    "parents": "a person's parents are the couple whose `children` list them",
    "children": "a person's children are listed on the couple they had them with, in `couples`",
    "partner": "partners are a couple: `couples: [{between: [a, b]}]`, in marriage order",
    "partners": "partners are couples: one `{between: [a, b]}` per partner, in marriage order",
    "spouse": "partners are a couple: `couples: [{between: [a, b]}]`",
    "twin": "twins are written on their parents' couple: `twins: [{of: [a, b], zygosity}]`",
    "ancestors": (
        "a family tree draws couples and all their children; a chart of one person's "
        "ancestors only is a binary tree — draw it as a `tree`"
    ),
}


def _familytree_refusal(violation: Violation) -> Violation:
    """A structural refusal in a family tree, told what this kind means by it."""
    parts = violation.pointer.split("/")
    name = parts[-1]
    if "is not a known field" in violation.message and name in FAMILYTREE_REFUSED:
        return Violation(violation.pointer, f"{name!r}: {FAMILYTREE_REFUSED[name]}.")
    if name == "role" and "is not one of" in violation.message:
        return Violation(
            violation.pointer,
            violation.message.split(".")[0]
            + ". A person's shape is their `sex` and their shading their `status`; `role` is "
            "`step`, or `emphasis` for the person the figure is about.",
        )
    if name == "status" and "is not one of" in violation.message:
        return Violation(
            violation.pointer,
            violation.message.split(".")[0]
            + ". A family tree tracks one trait; a second condition is a second tree. A "
            "pregnancy loss is `pregnancy: loss`, and death is `deceased`.",
        )
    return violation


def _familytree_violations(document: Mapping[str, Any]) -> list[Violation]:
    """Ids that resolve, one set of parents each, rows that agree, and one family."""
    found: list[Violation] = []
    people = [
        (index, entry)
        for index, entry in enumerate(_listed(document, "people"))
        if isinstance(entry, dict)
    ]
    ids: dict[str, int] = {}
    for index, entry in people:
        name = entry.get("id")
        text = entry.get("text")
        if isinstance(text, str) and not text.strip():
            found.append(
                Violation(
                    _pointer("people", index, "text"),
                    "an empty name: leave `text` out for a person drawn by number only.",
                )
            )
        if not isinstance(name, str):
            continue
        if name in ids:
            found.append(
                Violation(
                    _pointer("people", index, "id"),
                    f"{name!r} is already the id of person {ids[name]}: ids are unique.",
                )
            )
        else:
            ids[name] = index
    person = {name: dict(people)[index] for name, index in ids.items()}

    probands = [index for index, entry in people if entry.get("proband") is True]
    for index in probands[1:]:
        found.append(
            Violation(
                _pointer("people", index, "proband"),
                f"a family tree has one proband, and person {probands[0]} is already it. "
                f"Anyone else who asked for advice or testing is a `consultand`.",
            )
        )
    for index, entry in people:
        pregnancy = entry.get("pregnancy")
        if pregnancy == "loss" and entry.get("deceased") is True:
            found.append(
                Violation(
                    _pointer("people", index, "deceased"),
                    "a pregnancy loss is its own symbol, a small triangle; `deceased` is for "
                    "someone who was born.",
                )
            )
        if pregnancy == "ongoing" and entry.get("status") in ("affected", "carrier"):
            found.append(
                Violation(
                    _pointer("people", index, "status"),
                    "an ongoing pregnancy carries a `P` in its symbol, so it is not shaded: "
                    "write a prenatal result in `text`.",
                )
            )

    # Couples: two known, distinct partners; known children, each with one set of
    # parents; twins next to each other among them.
    couples = [
        (index, entry)
        for index, entry in enumerate(_listed(document, "couples"))
        if isinstance(entry, dict)
    ]
    pairs: dict[frozenset[str], int] = {}
    partners: dict[str, list[tuple[int, str]]] = {name: [] for name in ids}
    parents_of: dict[str, int] = {}
    valid: list[tuple[int, tuple[str, str], list[str]]] = []
    # Everyone a couple names, valid or not: a refused couple is reported once, not
    # again as people in no couple.
    mentioned: set[object] = set()
    for _, entry in couples:
        for field_name in ("between", "children"):
            listed = entry.get(field_name)
            if isinstance(listed, list):
                mentioned.update(each for each in listed if isinstance(each, str))
    for index, entry in couples:
        between = entry.get("between")
        where = _pointer("couples", index, "between")
        if not isinstance(between, list):
            continue
        if len(between) != 2:
            if len(between) > 2:
                found.append(
                    Violation(
                        where,
                        f"a couple is two people, and this names {len(between)}. A person with "
                        f"several partners is in one couple per partner, in marriage order.",
                    )
                )
            continue
        names = [name for name in between if isinstance(name, str)]
        if len(names) != 2:
            continue
        bad = False
        for position, name in enumerate(names):
            if name not in ids:
                found.append(
                    Violation(
                        _pointer("couples", index, "between", position),
                        f"{name!r} is not the id of a person. Known ids: "
                        f"{', '.join(sorted(ids)) or 'none'}.",
                    )
                )
                bad = True
        if bad:
            continue
        if names[0] == names[1]:
            found.append(
                Violation(where, f"a couple is two people; this names {names[0]!r} twice.")
            )
            continue
        key = frozenset(names)
        if key in pairs:
            found.append(
                Violation(
                    where,
                    f"{names[0]!r} and {names[1]!r} are already couple {pairs[key]}: list all "
                    f"their children there.",
                )
            )
            continue
        pairs[key] = index
        for name in names:
            if person[name].get("pregnancy") in FAMILYTREE_PREGNANCIES:
                found.append(
                    Violation(
                        where,
                        f"{name!r} is a pregnancy, which is drawn as a child only: it has no "
                        f"partners.",
                    )
                )
                bad = True
        if bad:
            continue
        for name in names:
            partners[name].append((index, names[1] if name == names[0] else names[0]))
        kids: list[str] = []
        children = entry.get("children")
        for position, child in enumerate(children if isinstance(children, list) else []):
            if not isinstance(child, str):
                continue
            here = _pointer("couples", index, "children", position)
            if child not in ids:
                found.append(
                    Violation(
                        here,
                        f"{child!r} is not the id of a person. Known ids: "
                        f"{', '.join(sorted(ids)) or 'none'}.",
                    )
                )
            elif child in names:
                found.append(
                    Violation(here, f"{child!r} is a partner in this couple, not a child.")
                )
            elif child in kids:
                found.append(Violation(here, f"{child!r} is already a child of this couple."))
            elif child in parents_of:
                found.append(
                    Violation(
                        here,
                        f"{child!r} is already a child of couple {parents_of[child]}: a person "
                        f"has one set of parents. An adopted child is listed once, in the couple "
                        f"that raised them, with `adopted: true`.",
                    )
                )
            else:
                parents_of[child] = index
                kids.append(child)
        twinned: set[str] = set()
        twins = entry.get("twins")
        for position, birth in enumerate(twins if isinstance(twins, list) else []):
            members = birth.get("of") if isinstance(birth, dict) else None
            if not isinstance(members, list):
                continue
            here = _pointer("couples", index, "twins", position, "of")
            named = [member for member in members if isinstance(member, str)]
            if len(named) > FAMILYTREE_TWIN_MAX:
                found.append(
                    Violation(
                        here,
                        f"{len(named)} children of one birth, and a tree draws "
                        f"{FAMILYTREE_TWIN_MAX} at most from one point. Write the number in a "
                        f"`caption`, and the children as ordinary siblings.",
                    )
                )
                continue
            strays = [member for member in named if member not in kids]
            if strays:
                found.append(
                    Violation(
                        here,
                        f"{strays[0]!r} is not one of this couple's `children`: twins are "
                        f"children of the couple they are written on.",
                    )
                )
                continue
            if len(set(named)) != len(named) or twinned & set(named):
                found.append(
                    Violation(here, "a child is in one set of twins, and named once in it.")
                )
                continue
            places = sorted(kids.index(member) for member in named)
            if places != list(range(places[0], places[0] + len(places))):
                found.append(
                    Violation(
                        here,
                        f"twins {', '.join(repr(member) for member in named)} are not next to "
                        f"each other in `children`: children of one birth are drawn from one "
                        f"point, so write them together.",
                    )
                )
                continue
            twinned.update(named)
        valid.append((index, (names[0], names[1]), kids))

    for name, mine in partners.items():
        for index, _ in mine[FAMILYTREE_PARTNER_MAX:]:
            found.append(
                Violation(
                    _pointer("couples", index, "between"),
                    f"{name!r} is in {len(mine)} couples, past what one row can draw — "
                    f"{FAMILYTREE_PARTNER_MAX} partners at most. Draw the later partners' "
                    f"families as a tree of their own.",
                )
            )
    for name, index in ids.items():
        entry = person[name]
        if entry.get("adopted") is True and name not in parents_of:
            found.append(
                Violation(
                    _pointer("people", index, "adopted"),
                    f"{name!r} is adopted, but no couple lists them among its `children`: "
                    f"list them in the couple that raised them.",
                )
            )
        if name not in mentioned:
            found.append(
                Violation(
                    _pointer("people", index),
                    f"{name!r} is in no couple, as a partner or a child, so nothing places "
                    f"them in the tree.",
                )
            )
    if found:
        return found

    # Descent goes one way: nobody is their own ancestor.
    below: dict[str, list[str]] = {name: [] for name in ids}
    for _, pair, kids in valid:
        for parent in pair:
            below[parent].extend(kids)
    state: dict[str, int] = {}

    def cycle(name: str, trail: list[str]) -> list[str] | None:
        state[name] = 1
        for child in below[name]:
            if state.get(child) == 1:
                return [*trail, name, child]
            if child not in state:
                looped = cycle(child, [*trail, name])
                if looped:
                    return looped
        state[name] = 2
        return None

    for name in ids:
        if name not in state:
            looped = cycle(name, [])
            if looped:
                begin = looped.index(looped[-1])
                return [
                    Violation(
                        _pointer("couples", parents_of[looped[-1]], "children"),
                        f"descent goes round in a circle ({' -> '.join(looped[begin:])}): "
                        f"nobody is their own ancestor.",
                    )
                ]

    # Generations: partners share a row, a child is one row below its couple.
    generation: dict[str, int] = {}
    links: dict[str, list[tuple[str, int, int]]] = {name: [] for name in ids}
    for index, pair, kids in valid:
        links[pair[0]].append((pair[1], 0, index))
        links[pair[1]].append((pair[0], 0, index))
        for child in kids:
            for parent in pair:
                links[parent].append((child, 1, index))
                links[child].append((parent, -1, index))
    families = 0
    for start in ids:
        if start in generation:
            continue
        families += 1
        if families > 1:
            return [
                Violation(
                    _pointer("people", ids[start]),
                    f"{start!r} is not related to {next(iter(ids))!r} through any couple: one "
                    f"family tree is one family. Draw the other family as a tree of its own.",
                )
            ]
        generation[start] = 0
        # Parents and children first, partners only when nothing else is left: so
        # a contradiction surfaces at the couple whose partners cannot share a row.
        queue = [start]
        later: list[tuple[str, str, int]] = []
        while queue or later:
            if not queue:
                current, other, index = later.pop(0)
                if other not in generation:
                    generation[other] = generation[current]
                    queue.append(other)
                elif generation[other] != generation[current]:
                    return [
                        Violation(
                            _pointer("couples", index, "between"),
                            f"{current!r} and {other!r} are partners, but their descent puts "
                            f"them {abs(generation[other] - generation[current])} generation(s) "
                            f"apart, and partners share a row. A family where they cannot is "
                            f"drawn as two trees.",
                        )
                    ]
                continue
            current = queue.pop(0)
            for other, step, index in links[current]:
                if step == 0:
                    later.append((current, other, index))
                    continue
                expected = generation[current] + step
                if other not in generation:
                    generation[other] = expected
                    queue.append(other)
                elif generation[other] != expected:
                    return [
                        Violation(
                            _pointer("couples", index, "children"),
                            f"the generations of couple {index} disagree with the rest of the "
                            f"tree: partners share a row and a child is one row below its "
                            f"parents, and no rows satisfy both here.",
                        )
                    ]
    low = min(generation.values())
    rows = max(generation.values()) - low + 1
    if rows > FAMILYTREE_GENERATION_MAX:
        deepest = next(name for name in ids if generation[name] - low == FAMILYTREE_GENERATION_MAX)
        found.append(
            Violation(
                _pointer("people", ids[deepest]),
                f"the tree spans {rows} generations, past what one family tree can be read at "
                f"— {FAMILYTREE_GENERATION_MAX} at most. Split it: the older generations as one "
                f"tree, and each branch below as a tree of its own.",
            )
        )

    # A row draws one person's partners beside them; a partner of theirs with
    # partners of their own would need a second row.
    for name, mine in partners.items():
        if len(mine) < 2:
            continue
        for index, other in mine:
            if len(partners[other]) > 1:
                found.append(
                    Violation(
                        _pointer("couples", index, "between"),
                        f"{name!r} and {other!r} both have other partners, and a row draws one "
                        f"person's partners beside them. Leave one of the earlier couples out, "
                        f"or draw it as a tree of its own.",
                    )
                )
                return found
        if len(mine) > 2:
            for index, other in mine[1:]:
                if other in parents_of:
                    found.append(
                        Violation(
                            _pointer("couples", index, "between"),
                            f"{other!r} is {name!r}'s partner number "
                            f"{mine.index((index, other)) + 1}, "
                            f"and has parents in the tree. Past two partners, the line to each "
                            f"later one runs over the row, so only the first partner's family "
                            f"can be drawn above. Draw {other!r}'s family as a tree of its own.",
                        )
                    )

    # An ancestor chart — a person, their parents, their four grandparents — is a
    # binary tree, not a family: every couple has one child, and couples marry
    # into each other from both sides.
    if (
        rows >= 3
        and len(valid) >= 3
        and all(len(kids) == 1 for _, _, kids in valid)
        and any(all(parent in parents_of for parent in pair) for _, pair, _ in valid)
    ):
        found.append(
            Violation(
                "/couples",
                "every couple here has one child, and partners come from both sides: this is "
                "an ancestor chart (a genealogist's pedigree chart), one person and their "
                "forebears. That is a binary tree, so draw it as a `tree`. A family tree draws "
                "couples and all their children.",
            )
        )
    return found


#: Why a mind map has no place for a field an author may reach for.
MINDMAP_REFUSED: Final = {
    "edges": (
        "a mind map is nested: a branch belongs to the one it is written in, so there is "
        "nothing to connect. Links across branches, each named by a phrase, are a concept "
        "map: draw that as a `flow` with labelled edges"
    ),
    "links": (
        "a mind map is nested, so a line between two branches would make it a concept map. "
        "Draw that as a `flow` with labelled edges"
    ),
    "id": (
        "nothing refers to a branch: its place is where it is written. A link from one "
        "branch to another is a concept map, which is a `flow` with labelled edges"
    ),
    "side": (
        "the layout splits the main branches between the two sides so they balance; a side "
        "chosen by the author is a coordinate. Order them, and drawspec places them "
        "clockwise from the top right"
    ),
    "nodes": "a mind map's entries are its `branches`, nested under the `centre`",
}


def _mindmap_refusal(violation: Violation) -> Violation:
    """A structural refusal in a mind map, told what this kind means by it."""
    parts = violation.pointer.split("/")
    name = parts[-1]
    unknown = "is not a known field" in violation.message or (
        "is not" in violation.message and "field" in violation.message
    )
    if unknown and name in MINDMAP_REFUSED:
        return Violation(violation.pointer, f"{name!r}: {MINDMAP_REFUSED[name]}.")
    if parts[1:] == ["branches"] and "needs at least" in violation.message:
        return Violation(
            violation.pointer,
            "a mind map needs at least 2 main branches round its centre: one branch is a "
            "hierarchy from a root, which is a `tree`.",
        )
    if name == "branches" and len(parts) > 2 and "needs at least" in violation.message:
        return Violation(
            violation.pointer,
            "an empty 'branches' list draws nothing: leave the field out of a branch that "
            "ends here.",
        )
    if name == "role" and "is not one of" in violation.message:
        return Violation(
            violation.pointer,
            violation.message.split(".")[0]
            + ". A branch is words on a line, with no shape to mean `decision` or "
            "`terminal`: `step`, `emphasis` for the branch the map is about, `note` for "
            "context.",
        )
    return violation


def _mindmap_violations(document: Mapping[str, Any]) -> list[Violation]:
    """No empty words, and no fourth level below the centre."""
    found: list[Violation] = []
    centre = document.get("centre")
    if isinstance(centre, str) and not centre.strip():
        found.append(Violation("/centre", "the centre is the topic: it needs words."))

    def walk(entries: object, pointer: str, depth: int) -> None:
        if not isinstance(entries, list):
            return
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            here = f"{pointer}/{index}"
            text = entry.get("text")
            if isinstance(text, str) and not text.strip():
                found.append(
                    Violation(
                        f"{here}/text", "a branch needs words: an empty one draws a bare line."
                    )
                )
            children = entry.get("branches")
            if depth == MINDMAP_DEPTH_MAX and isinstance(children, list):
                found.append(
                    Violation(
                        f"{here}/branches",
                        f"a fourth level below the centre is past what one mind map can be "
                        f"read at — {MINDMAP_DEPTH_MAX} levels at most: a branch, a twig, a "
                        f"leaf. Make this branch the centre of a map of its own, or fold the "
                        f"detail into this leaf's words.",
                    )
                )
                continue
            walk(children, f"{here}/branches", depth + 1)

    walk(document.get("branches"), "/branches", 1)
    return found


#: Why a sunburst has no place for a field an author may reach for.
SUNBURST_REFUSED: Final = {
    "angle": (
        "a sector's angle is its share of the circle, computed from the tree — a terminal "
        "node takes an equal slice and a parent spans its children. It is never written"
    ),
    "weight": (
        "every terminal node weighs the same, so the wheel is read from its shape alone. A "
        "wheel sized by amounts is a `pie` or a `treemap`"
    ),
    "value": (
        "a sunburst states a hierarchy, not quantities: the shares are equal and derived. "
        "For an amount per part draw a `pie` or a `treemap`"
    ),
    "amount": (
        "a sunburst states a hierarchy, not quantities: the shares are equal and derived. "
        "For an amount per part draw a `pie` or a `treemap`"
    ),
    "size": (
        "a label's size is chosen to fit its sector, largest first and smaller for a longer "
        "word: the type is drawspec's, never the author's"
    ),
    "radius": (
        "the rings are sized to the words they hold; a radius set by the author is a coordinate"
    ),
    "role": (
        "a sunburst node is words in a sector, with no shape or stance to mark: it takes only "
        "`text` and `children`"
    ),
    "id": "nothing refers to a sector: its place is where it is written, nested in its parent",
    "edges": (
        "a sunburst is nested, so there is nothing to connect; a line between sectors is a `flow`"
    ),
}


def _sunburst_refusal(violation: Violation) -> Violation:
    """A structural refusal in a sunburst, told what this kind means by it."""
    parts = violation.pointer.split("/")
    name = parts[-1]
    unknown = "is not a known field" in violation.message or (
        "is not" in violation.message and "field" in violation.message
    )
    if unknown and name in SUNBURST_REFUSED:
        return Violation(violation.pointer, f"{name!r}: {SUNBURST_REFUSED[name]}.")
    if parts[1:] == ["nodes"] and "needs at least" in violation.message:
        return Violation(
            violation.pointer,
            "a sunburst needs at least 2 nodes in its first ring: one sector is a whole "
            "circle, which says nothing.",
        )
    if name == "children" and "needs at least" in violation.message:
        return Violation(
            violation.pointer,
            "an empty 'children' list draws nothing: leave the field out of a node that ends "
            "the hierarchy.",
        )
    return violation


def _sunburst_fourth_ring(pointer: str) -> Violation:
    """The located violation for a node that would open a fourth ring."""
    return Violation(
        pointer,
        f"a fourth ring is past what one sunburst can be read at — "
        f"{SUNBURST_DEPTH_MAX} rings at most. Fold the detail into this "
        f"sector's words, or make it the centre of a wheel of its own.",
    )


def _sunburst_too_deep(document: Mapping[str, Any]) -> Violation | None:
    """The first node nested past `SUNBURST_DEPTH_MAX`, found without recursion.

    `sunburst-node` refers to itself through `children`, and the structural pass
    (`_check_object`) recurses once per level with no depth limit. A document
    nested hundreds deep still parses as JSON, so without this it raises
    `RecursionError` inside `validate_document` — which also serves MCP and agent
    input — instead of a located violation. This iterative pre-scan runs first so
    the depth cap is reported before the recursive pass can overflow.
    """
    stack: list[tuple[object, str, int]] = [(document.get("nodes"), "/nodes", 1)]
    while stack:
        entries, pointer, depth = stack.pop()
        if not isinstance(entries, list):
            continue
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict) or not isinstance(entry.get("children"), list):
                continue
            here = f"{pointer}/{index}/children"
            if depth == SUNBURST_DEPTH_MAX:
                return _sunburst_fourth_ring(here)
            stack.append((entry["children"], here, depth + 1))
    return None


def _sunburst_violations(document: Mapping[str, Any]) -> list[Violation]:
    """No empty words, no fourth ring, and the first-ring and total caps."""
    found: list[Violation] = []
    centre = document.get("centre")
    if isinstance(centre, str) and centre and not centre.strip():
        found.append(Violation("/centre", "the hub label needs words, or leave `centre` out."))

    total = 0
    first = document.get("nodes")

    def walk(entries: object, pointer: str, depth: int) -> None:
        nonlocal total
        if not isinstance(entries, list):
            return
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            total += 1
            here = f"{pointer}/{index}"
            text = entry.get("text")
            if isinstance(text, str) and not text.strip():
                found.append(
                    Violation(
                        f"{here}/text", "a sector needs words: an empty one is a blank wedge."
                    )
                )
            children = entry.get("children")
            if depth == SUNBURST_DEPTH_MAX and isinstance(children, list):
                found.append(_sunburst_fourth_ring(f"{here}/children"))
                continue
            walk(children, f"{here}/children", depth + 1)

    walk(first, "/nodes", 1)
    if total > SUNBURST_NODE_MAX:
        found.append(
            Violation(
                "/nodes",
                f"{total} sectors in all is past what one sunburst can be read at — "
                f"{SUNBURST_NODE_MAX} at most, counted across every ring. Split it into an "
                f"overview wheel and a wheel per branch.",
            )
        )
    return found


#: Why a network diagram has no place for a field an author may reach for.
NETWORK_REFUSED: Final = {
    "column": (
        "a host's column is drawspec's: chosen so no line crosses a bus it is not on, then "
        "as few columns and as close to the order written as that allows"
    ),
    "order": (
        "the networks are drawn in the order written and the columns are derived from the "
        "attachments; reorder the `networks` array to move a bus"
    ),
    "icon": (
        "drawspec draws no device icons: a host is a box (`store` a drum, `person` a client), "
        "and its words say what it is — `fw01 (firewall)`"
    ),
    "shape": (
        "a host's shape comes from its `role`: `step` a box, `store` a drum, `person` a client"
    ),
    "edges": (
        "a network diagram joins hosts to buses, not hosts to hosts: put both hosts on a "
        "network. For links between boxes, draw a `flow`"
    ),
    "color": "appearance is the theme's: a network's bus is drawn the same as every other",
    "colour": "appearance is the theme's: a network's bus is drawn the same as every other",
}

#: What a device role an author may reach for is, in drawspec's vocabulary.
NETWORK_ROLE_HINTS: Final = {
    "router": "a router is a host on two networks: leave the role out and name it",
    "firewall": "a firewall is a host on the networks it divides: leave the role out and name it",
    "switch": "a switch is the network itself: make it one of the `networks`",
    "server": "a server is the default box: leave the role out",
    "database": "a database is `store`, drawn as a drum",
    "storage": "a storage array is `store`, drawn as a drum",
    "cloud": "the internet is a network: make it the first of the `networks`",
    "internet": "the internet is a network: make it the first of the `networks`",
    "client": "a user's machine is `person`",
    "user": "a user's machine is `person`",
}


def _network_refusal(violation: Violation) -> Violation:
    """A structural refusal in a network diagram, told what this kind means by it."""
    parts = violation.pointer.split("/")
    name = parts[-1]
    if "is not a known field" in violation.message and name in NETWORK_REFUSED:
        return Violation(violation.pointer, f"{name!r}: {NETWORK_REFUSED[name]}.")
    if name == "role" and "is not one of" in violation.message:
        value = violation.message.split(" is not one of", 1)[0].strip("'\"")
        hint = NETWORK_ROLE_HINTS.get(value.lower())
        if hint:
            return Violation(
                violation.pointer,
                f"{value!r} is not a host role ({', '.join(NETWORK_HOST_ROLES)}): {hint}. "
                f"drawspec draws no device icons.",
            )
    return violation


def _network_violations(document: Mapping[str, Any]) -> list[Violation]:
    """Ids that land, no empty bus, groups that hold, and lines that cross no bus.

    The last is the kind's one hard question: a host on two networks that are not
    neighbours must stand outside every bus between them. `drawspec.buses` looks
    for a column order where every host does; when it finds none the document is
    refused here, at the host, before any layout runs.
    """
    from drawspec.buses import arrange

    found: list[Violation] = []
    networks: dict[str, int] = {}
    # Whether every entry is whole enough to arrange: a network skipped here keeps
    # its slot, so a host on a later one would name an index past the count.
    whole = True
    for index, entry in enumerate(_listed(document, "networks")):
        if not isinstance(entry, dict):
            whole = False
            continue
        identifier = entry.get("id")
        text = entry.get("text")
        if isinstance(text, str) and not text.strip():
            found.append(Violation(_pointer("networks", index, "text"), "a network needs a name."))
        if not isinstance(identifier, str):
            whole = False
            continue
        if identifier in networks:
            found.append(
                Violation(_pointer("networks", index, "id"), f"duplicate network id {identifier!r}")
            )
            whole = False
            continue
        networks[identifier] = index

    hosts: dict[str, int] = {}
    attached: list[list[int]] = []
    used: set[int] = set()
    for index, entry in enumerate(_listed(document, "hosts")):
        if not isinstance(entry, dict):
            whole = False
            continue
        identifier = entry.get("id")
        text = entry.get("text")
        if isinstance(text, str) and not text.strip():
            found.append(Violation(_pointer("hosts", index, "text"), "a host needs a name."))
        if isinstance(identifier, str):
            if identifier in hosts or identifier in networks:
                what = "host" if identifier in hosts else "network"
                found.append(
                    Violation(
                        _pointer("hosts", index, "id"),
                        f"{identifier!r} is already the id of a {what}: every id names one thing.",
                    )
                )
            else:
                hosts[identifier] = index
        on: list[int] = []
        for position, item in enumerate(_listed(entry, "networks")):
            if not isinstance(item, dict) or not isinstance(item.get("network"), str):
                whole = False
                continue
            name = item["network"]
            pointer = _pointer("hosts", index, "networks", position, "network")
            if name not in networks:
                found.append(
                    Violation(
                        pointer, f"{name!r} is not the id of any network" + _closest(name, networks)
                    )
                )
                whole = False
                continue
            if networks[name] in on:
                found.append(
                    Violation(
                        pointer,
                        f"this host is on {name!r} already: one line per network. Two addresses "
                        f"on one network go in one `address`, `.1, .2`.",
                    )
                )
                continue
            on.append(networks[name])
        if not on:
            whole = False
        used.update(on)
        attached.append(on)

    for name, index in networks.items():
        if index not in used and whole:
            found.append(
                Violation(
                    _pointer("networks", index),
                    f"no host is on {name!r}: an empty bus says nothing. Put a host on it, or "
                    f"leave it out.",
                )
            )

    members: list[list[int]] = []
    owner: dict[str, int] = {}
    for index, entry in enumerate(_listed(document, "groups")):
        if not isinstance(entry, dict):
            whole = False
            continue
        text = entry.get("text")
        if isinstance(text, str) and not text.strip():
            found.append(
                Violation(
                    _pointer("groups", index, "text"),
                    "a group's name needs words, or leave `text` out.",
                )
            )
        listed: list[int] = []
        for position, member in enumerate(_listed(entry, "members")):
            if not isinstance(member, str):
                whole = False
                continue
            pointer = _pointer("groups", index, "members", position)
            if member not in hosts:
                found.append(
                    Violation(
                        pointer, f"{member!r} is not the id of any host" + _closest(member, hosts)
                    )
                )
                whole = False
                continue
            if member in owner:
                where = "this group" if owner[member] == index else f"group {owner[member]}"
                found.append(
                    Violation(
                        pointer,
                        f"{member!r} is in {where} already: a host stands on one backdrop.",
                    )
                )
                continue
            owner[member] = index
            listed.append(hosts[member])
        members.append(listed)

    if found or not whole or not attached or len(hosts) != len(attached):
        return found
    if len(networks) > NETWORK_MAX or len(attached) > NETWORK_HOST_MAX:
        return found  # the budget refuses it, and the search would be slow for nothing

    names = list(networks)
    arrangement = arrange(len(networks), attached, members)
    for host, network in arrangement.crossings[:1]:
        on = sorted(attached[host])
        found.append(
            Violation(
                _pointer("hosts", host, "networks"),
                f"this host is on {names[on[0]]!r} and {names[on[-1]]!r}, so its line passes "
                f"{names[network]!r}, which it is not on — and in no column order does it stand "
                f"clear of the hosts on {names[network]!r}. Put it on {names[network]!r} too, "
                f"move {names[network]!r} in `networks` so the ones it joins are neighbours, or "
                f"split the diagram.",
            )
        )
    named = {index: identifier for identifier, index in hosts.items()}
    clashes = [clash for clash in arrangement.clashes if not arrangement.crossings]
    for group, other in clashes[:1]:
        if other >= 0:
            message = (
                f"no column order keeps this group's hosts together without host "
                f"{named[other]!r} standing on its backdrop too. Add it to the group, or group "
                f"fewer."
            )
        else:
            message = (
                f"no column order keeps this group's backdrop clear of group {-1 - other}'s. "
                f"Merge the two, or group fewer hosts."
            )
        found.append(Violation(_pointer("groups", group, "members"), message))
    return found


#: Why a timing figure has no place for a field an author may reach for.
TIMING_REFUSED: Final = {
    "wave": (
        'the values are an array, one string per step — `["p", ".", ".", "0"]` — '
        "so a wrong one is pointed at by its step. Write them in `values`"
    ),
    "data": "a bus's words are its values: write each word in `values` at the step it starts",
    "period": (
        "time is counted in equal steps, so a clock is a `p` per step (or `p` then `.`): "
        "there is no period to write"
    ),
    "time": (
        "time is counted in steps, not seconds: the steps are not to scale. Name them with "
        "`ticks`, and name a measured span with an `intervals` entry"
    ),
    "duration": (
        "a span is named, not measured: write it as an `intervals` entry from one edge to another"
    ),
    "scale": "every step is the same width, decided by the canvas; there is no scale to set",
    "edges": (
        "a named span between two edges is an `intervals` entry; a line across every lane is a "
        "`markers` entry. An arrow from one edge to an edge on another signal is not drawn"
    ),
    "edge": (
        "a named span between two edges is an `intervals` entry; a line across every lane is a "
        "`markers` entry. An arrow from one edge to an edge on another signal is not drawn"
    ),
    "role": (
        "a lane is told by what it draws, its `lane`: `bit`, `bus` or `state`. There is no "
        "emphasis to mark"
    ),
    "type": "what a lane draws is its `lane`: `bit`, `bus` or `state`",
    "id": "a signal is named by its `text`, which an interval refers to",
    "name": "a signal's name is its `text`",
}


def _timing_refusal(violation: Violation) -> Violation:
    """A structural refusal in a timing figure, told what this kind means by it."""
    parts = violation.pointer.split("/")
    name = parts[-1]
    unknown = "is not a known field" in violation.message or (
        "is not" in violation.message and "field" in violation.message
    )
    if unknown and name in TIMING_REFUSED:
        return Violation(violation.pointer, f"{name!r}: {TIMING_REFUSED[name]}.")
    if (
        len(parts) == 5
        and parts[1] == "signals"
        and parts[3] == "values"
        and "expected string" in violation.message
    ):
        return Violation(
            violation.pointer,
            'a value is a string, one per step: write a level as `"0"` or `"1"`, in quotes, '
            "and a word on a bus as its text.",
        )
    return violation


def _timing_edge_problem(value: object, steps: int) -> str | None:
    """Why `value` is not an edge on a `steps`-step axis, or None when it is one."""
    if not isinstance(value, int | float) or isinstance(value, bool):
        return None  # the structural pass has said so
    if not math.isfinite(value):
        return (
            f"{value!r} is not a number of steps: an edge is from 0 (the left edge) to "
            f"{steps} (the right), whole or half."
        )
    if value < 0 or value > steps:
        return (
            f"{_figure(float(value))} is off the axis: an edge is from 0 (the left edge) to "
            f"{steps} (the right), in steps."
        )
    if not (float(value) * 2).is_integer():
        return (
            f"{_figure(float(value))} falls inside a step: an edge is a whole step (between "
            f"two) or a half (where a clock pulse falls)."
        )
    return None


def _timing_states(here: str, states: object, found: list[Violation]) -> list[str]:
    """A state lane's named states, each checked: named, once, and not `.`."""
    names: list[str] = []
    if not isinstance(states, list):
        return names
    for position, state in enumerate(states):
        if not isinstance(state, str):
            continue
        where = f"{here}/states/{position}"
        if not state.strip():
            found.append(Violation(where, "a state needs a name."))
        elif state in names:
            found.append(Violation(where, f"{state!r} is written twice: each state is one level."))
        elif state == TIMING_HOLD:
            found.append(Violation(where, "`.` carries a step on, so it cannot name a state."))
        else:
            names.append(state)
    return names


def _timing_values(
    here: str, lane: object, values: list[Any], states: list[str] | None, found: list[Violation]
) -> None:
    """Every value of one lane: one its lane can draw, and no `.` with nothing before it."""
    if len(values) > TIMING_STEP_MAX:
        found.append(
            Violation(
                f"{here}/values/{TIMING_STEP_MAX}",
                f"{len(values)} steps is past what one timing figure can be read at — "
                f"{TIMING_STEP_MAX} at most. Draw the part the figure is about, and leave "
                f"the idle time out.",
            )
        )
    for step, value in enumerate(values):
        if not isinstance(value, str):
            continue
        where = f"{here}/values/{step}"
        if value == TIMING_HOLD:
            if step == 0:
                found.append(
                    Violation(
                        where,
                        "`.` carries the step before on, and the first step has none: start "
                        "with a value.",
                    )
                )
            continue
        if lane == "bit" and value not in TIMING_BIT_VALUES:
            found.append(
                Violation(
                    where,
                    f"{value!r} is not a level. A `bit` lane takes `0`, `1`, `z` (high "
                    f"impedance), `x` (unknown), `p` and `n` (clock pulses) and `.` (as "
                    f"before); for a word per step, set `lane` to `bus`.",
                )
            )
        elif lane == "bus" and not value.strip():
            found.append(
                Violation(
                    where,
                    "an empty word is not a value: write `x` for unknown, `z` for high "
                    "impedance, or `.` to hold the word before.",
                )
            )
        elif lane == "state" and states is not None and value not in states:
            found.append(
                Violation(
                    where,
                    f"{value!r} is not one of this lane's states "
                    f"({', '.join(states) or 'none'}); add it to `states`, or write `.` to "
                    f"stay in the state before.",
                )
            )


def _timing_signal(
    index: int,
    signal: Mapping[str, Any],
    names: dict[str, int],
    groups: dict[str, int],
    previous_group: str | None,
    found: list[Violation],
) -> str | None:
    """One signal's name, lane, states, group and values; its group, for the next."""
    here = _pointer("signals", index)
    text = signal.get("text")
    if isinstance(text, str):
        if not text.strip():
            found.append(Violation(f"{here}/text", "a signal needs a name: its lane is blank."))
        elif text in names:
            found.append(
                Violation(
                    f"{here}/text",
                    f"{text!r} names signal {names[text]} already: an interval refers to a "
                    f"signal by its name, so each is written once.",
                )
            )
        else:
            names[text] = index
    lane = signal.get("lane", "bit")
    if lane == "state" and "states" not in signal:
        found.append(
            Violation(
                f"{here}/states",
                "a `state` lane needs its `states`, top to bottom: the levels its line steps "
                "between.",
            )
        )
    if lane != "state" and "states" in signal:
        found.append(
            Violation(
                f"{here}/states",
                f"a {lane!r} lane has no named states: its levels are fixed. Set `lane` to "
                f"`state` to draw a line between named levels.",
            )
        )
    states = _timing_states(here, signal.get("states"), found)
    group = signal.get("group")
    if isinstance(group, str):
        if not group.strip():
            found.append(Violation(f"{here}/group", "a group needs a name, or leave `group` out."))
        elif group in groups and previous_group != group:
            found.append(
                Violation(
                    f"{here}/group",
                    f"the group {group!r} began at signal {groups[group]} and was left: write "
                    f"a group's signals next to each other, so it is drawn once.",
                )
            )
        else:
            groups.setdefault(group, index)
    values = signal.get("values")
    if isinstance(values, list):
        _timing_values(
            here, lane, values, states if isinstance(signal.get("states"), list) else None, found
        )
    return group if isinstance(group, str) else None


def _timing_violations(document: Mapping[str, Any]) -> list[Violation]:
    """Every value a lane can draw, every lane one length, and every reference found."""
    found: list[Violation] = []
    names: dict[str, int] = {}
    groups: dict[str, int] = {}
    lengths: list[tuple[int, int]] = []
    previous_group: str | None = None
    for index, signal in enumerate(_listed(document, "signals")):
        if not isinstance(signal, dict):
            continue
        previous_group = _timing_signal(index, signal, names, groups, previous_group, found)
        if isinstance(signal.get("values"), list):
            lengths.append((index, len(signal["values"])))
    if not lengths:
        return found
    first, steps = lengths[0]
    for index, length in lengths[1:]:
        if length != steps:
            found.append(
                Violation(
                    _pointer("signals", index, "values"),
                    f"{length} steps, where signal {first} has {steps}: every lane runs the "
                    f"whole axis, one value per step. Pad the shorter with `.` or `x`.",
                )
            )
    ticks = document.get("ticks")
    if isinstance(ticks, list) and len(ticks) != steps:
        found.append(
            Violation(
                "/ticks",
                f"{len(ticks)} ticks for {steps} steps: name each step once, an empty string "
                f"for a step left unnamed.",
            )
        )
    for index, marker in enumerate(_listed(document, "markers")):
        if not isinstance(marker, dict):
            continue
        problem = _timing_edge_problem(marker.get("at"), steps)
        if problem:
            found.append(Violation(_pointer("markers", index, "at"), problem))
        text = marker.get("text")
        if isinstance(text, str) and text and not text.strip():
            found.append(
                Violation(_pointer("markers", index, "text"), "a blank name: leave `text` out.")
            )
    for index, interval in enumerate(_listed(document, "intervals")):
        if isinstance(interval, dict):
            found.extend(_timing_interval(index, interval, steps, names))
    return found


def _timing_interval(
    index: int, interval: Mapping[str, Any], steps: int, names: Mapping[str, int]
) -> list[Violation]:
    """One interval: both edges on the axis, running forward, named, on a signal there is."""
    found: list[Violation] = []
    for end in ("from", "to"):
        problem = _timing_edge_problem(interval.get(end), steps)
        if problem:
            found.append(Violation(_pointer("intervals", index, end), problem))
    start, stop = interval.get("from"), interval.get("to")
    numbers = all(
        isinstance(value, int | float) and not isinstance(value, bool) for value in (start, stop)
    )
    if numbers and float(stop) <= float(start):  # type: ignore[arg-type]
        found.append(
            Violation(
                _pointer("intervals", index, "to"),
                f"an interval runs forward: `to` ({_figure(float(stop))}) must be after "  # type: ignore[arg-type]
                f"`from` ({_figure(float(start))}).",  # type: ignore[arg-type]
            )
        )
    text = interval.get("text")
    if isinstance(text, str) and not text.strip():
        found.append(Violation(_pointer("intervals", index, "text"), "an interval needs a name."))
    signal = interval.get("signal")
    if isinstance(signal, str) and signal not in names:
        found.append(
            Violation(
                _pointer("intervals", index, "signal"),
                f"{signal!r} is not a signal here; the signals are "
                f"{', '.join(repr(name) for name in names) or 'none'}.",
            )
        )
    return found


#: Why a git graph has no place for a field an author may reach for.
GITGRAPH_REFUSED: Final = {
    "lane": (
        "a branch's lane is its place in `branches`, in the order written; the lane's "
        "position on the page is drawspec's"
    ),
    "column": "a step's place in time is its place in `steps`, in the order written",
    "colour": "a branch's colour is the theme's, never the document's",
    "parent": (
        "a commit's parents are derived: the latest commit on its branch, and for a merge "
        "the latest commit on the branch it merges"
    ),
    "parents": (
        "a commit's parents are derived: the latest commit on its branch, and for a merge "
        "the latest commit on the branch it merges"
    ),
    "branch": (
        "a step names its branch with `on`; a new branch is declared once in `branches`, "
        "with `from` saying where it forks"
    ),
    "checkout": ("there is no current branch to switch: every step says which branch it is `on`"),
    "type": (
        "a commit's kind is derived: `merge` makes a merge commit and `pick` a cherry-pick; "
        "for the commit the figure is about, say `role: emphasis`"
    ),
    "date": (
        "a git graph is an order, not a calendar: steps are evenly spaced in the order "
        "written. For dates on an axis draw a `timeline`"
    ),
    "tags": "a commit takes one `tag`; a second tag on the same commit is a second release name",
}


def _gitgraph_refusal(violation: Violation) -> Violation:
    """A structural refusal in a git graph, told what this kind means by it."""
    name = violation.pointer.split("/")[-1]
    if "is not a known field" in violation.message and name in GITGRAPH_REFUSED:
        return Violation(violation.pointer, f"{name!r}: {GITGRAPH_REFUSED[name]}.")
    return violation


def _gitgraph_violations(document: Mapping[str, Any]) -> list[Violation]:
    """Names and handles that resolve, and a history git could have made.

    The steps are replayed in order, as git would make them: a branch forks at its
    first step from the latest commit on its `from`; a merge takes the latest commit
    of the branch it names; a cherry-pick copies an earlier commit. A step that git
    would refuse, or that would draw nothing new, is refused here, at its pointer.
    """
    found: list[Violation] = []
    raw_branches = document.get("branches")
    raw_steps = document.get("steps")
    if not isinstance(raw_branches, list) or not isinstance(raw_steps, list):
        return found
    branches = [entry if isinstance(entry, dict) else {} for entry in raw_branches]
    steps = [entry if isinstance(entry, dict) else {} for entry in raw_steps]

    names: dict[str, int] = {}
    for index, branch in enumerate(branches):
        name = branch.get("name")
        if not isinstance(name, str):
            continue
        if not name.strip():
            found.append(Violation(f"/branches/{index}/name", "a branch needs a name."))
        elif name in names:
            found.append(
                Violation(
                    f"/branches/{index}/name",
                    f"the branch {name!r} is declared twice (first at /branches/{names[name]}): "
                    f"one lane per branch, so give the second its own name.",
                )
            )
        else:
            names[name] = index

    ids: dict[str, int] = {}
    tags: dict[str, int] = {}
    for index, step in enumerate(steps):
        for field_name in ("text", "tag"):
            value = step.get(field_name)
            if isinstance(value, str) and not value.strip():
                found.append(
                    Violation(
                        f"/steps/{index}/{field_name}",
                        f"an empty {field_name!r} draws nothing: leave the field out.",
                    )
                )
        handle = step.get("id")
        if isinstance(handle, str):
            if not handle.strip():
                found.append(Violation(f"/steps/{index}/id", "an empty 'id' names nothing."))
            elif handle in ids:
                found.append(
                    Violation(
                        f"/steps/{index}/id",
                        f"the id {handle!r} is used twice (first at /steps/{ids[handle]}): a "
                        f"commit's handle names one commit.",
                    )
                )
            elif handle in names:
                found.append(
                    Violation(
                        f"/steps/{index}/id",
                        f"{handle!r} is already a branch's name, and a `from` names either: "
                        f"give the commit another id.",
                    )
                )
            else:
                ids[handle] = index
        tag = step.get("tag")
        if isinstance(tag, str) and tag.strip():
            if tag in tags:
                found.append(
                    Violation(
                        f"/steps/{index}/tag",
                        f"the tag {tag!r} is on two commits (first at /steps/{tags[tag]}): a "
                        f"tag names one commit.",
                    )
                )
            else:
                tags[tag] = index
        if "merge" in step and "pick" in step:
            found.append(
                Violation(
                    f"/steps/{index}/pick",
                    "a step is a merge or a cherry-pick, not both: write them as two steps.",
                )
            )
    if found:
        return found

    known = ", ".join(repr(name) for name in names)
    sources: dict[str, str] = {}
    for index, branch in enumerate(branches):
        name = branch.get("name")
        source = branch.get("from")
        if not isinstance(name, str):
            continue
        if index == 0:
            if source is not None:
                found.append(
                    Violation(
                        "/branches/0/from",
                        "the first branch is the trunk, and forks from nothing: put the "
                        "branch it forks from before it in `branches`.",
                    )
                )
            continue
        if source is None:
            source = next(iter(names))
        if not isinstance(source, str):
            continue
        if source == name:
            found.append(Violation(f"/branches/{index}/from", "a branch cannot fork from itself."))
        elif source not in names and source not in ids:
            found.append(
                Violation(
                    f"/branches/{index}/from",
                    f"{source!r} is neither a branch ({known}) nor a commit's `id`.",
                )
            )
        else:
            sources[name] = source
    if found:
        return found

    # Replay the history, as git would make it.
    tips: dict[str, int] = {}
    ancestors: list[set[int]] = []
    for index, step in enumerate(steps):
        on = step.get("on")
        here = f"/steps/{index}"
        if not isinstance(on, str) or on not in names:
            found.append(Violation(f"{here}/on", f"{on!r} is not one of the branches: {known}."))
            return found
        parents: list[int] = []
        if on in tips:
            parents.append(tips[on])
        elif names[on] != 0:
            source = sources[on]
            if source in names:
                if source not in tips:
                    found.append(
                        Violation(
                            f"{here}/on",
                            f"{on!r} forks from {source!r} at its first commit, and {source!r} "
                            f"has no commit yet: commit on {source!r} first.",
                        )
                    )
                    return found
                parents.append(tips[source])
            else:
                if ids[source] >= index:
                    found.append(
                        Violation(
                            f"/branches/{names[on]}/from",
                            f"{on!r} forks from {source!r}, which is written after the "
                            f"branch's first commit (/steps/{index}): a branch can only fork "
                            f"from a commit that already exists.",
                        )
                    )
                    return found
                parents.append(ids[source])
            if "merge" in step:
                found.append(
                    Violation(
                        f"{here}/merge",
                        f"this is {on!r}'s first commit, so the merge would only fast-forward "
                        f"it: commit on {on!r} first, or merge into the branch it forks from.",
                    )
                )
                return found
        elif "merge" in step:
            found.append(
                Violation(
                    f"{here}/merge",
                    f"a merge needs a commit on {on!r} to merge into: commit on it first.",
                )
            )
            return found
        reach: set[int] = {index}
        for parent in parents:
            reach |= ancestors[parent]
        merged = step.get("merge")
        if isinstance(merged, str):
            if merged not in names:
                found.append(
                    Violation(f"{here}/merge", f"{merged!r} is not one of the branches: {known}.")
                )
                return found
            if merged == on:
                found.append(Violation(f"{here}/merge", f"a branch cannot merge itself ({on!r})."))
                return found
            if merged not in tips:
                found.append(
                    Violation(
                        f"{here}/merge",
                        f"{merged!r} has no commit yet, so there is nothing to merge.",
                    )
                )
                return found
            if tips[merged] in reach:
                found.append(
                    Violation(
                        f"{here}/merge",
                        f"everything on {merged!r} is already in {on!r}: the merge would make "
                        f"no change. Commit on {merged!r} first, or leave the merge out.",
                    )
                )
                return found
            reach |= ancestors[tips[merged]]
        picked = step.get("pick")
        if isinstance(picked, str):
            if picked not in ids:
                found.append(Violation(f"{here}/pick", f"{picked!r} is not any commit's `id`."))
                return found
            source_index = ids[picked]
            if source_index >= index:
                found.append(
                    Violation(
                        f"{here}/pick",
                        f"{picked!r} is written after this step: a cherry-pick copies a commit "
                        f"that already exists.",
                    )
                )
                return found
            if "merge" in steps[source_index]:
                found.append(
                    Violation(
                        f"{here}/pick",
                        f"{picked!r} is a merge commit, which git will not cherry-pick without "
                        f"choosing a side: pick one of the commits it merged.",
                    )
                )
                return found
            if source_index in reach:
                found.append(
                    Violation(
                        f"{here}/pick",
                        f"{picked!r} is already in {on!r}'s history: picking it changes nothing.",
                    )
                )
                return found
        ancestors.append(reach)
        tips[on] = index

    for name, index in names.items():
        if name not in tips:
            found.append(
                Violation(
                    f"/branches/{index}",
                    f"the branch {name!r} has no commit, so it has no lane to draw: commit on "
                    f"it, or leave it out (a name on a commit is a `tag`).",
                )
            )
    return found


#: Why a railroad has no place for a field an author may reach for.
RAILROAD_REFUSED: Final = {
    "text": (
        "a box's words go in `terminal`, `rule` or `special` — which of the three says how it "
        "is drawn — and words on the track with no box in `comment`"
    ),
    "name": 'only a rule has a name; inside a track, refer to a rule with `{"rule": name}`',
    "max": (
        "a loop is drawn the same whatever its most, so a count is never drawn: say it in a "
        "`comment` as the `separator`, or write the item that many times in a `seq`"
    ),
    "times": (
        "a loop is drawn the same whatever its count: write the item that many times in a "
        "`seq`, or say it in a `comment`"
    ),
    "count": (
        "a loop is drawn the same whatever its count: write the item that many times in a "
        "`seq`, or say it in a `comment`"
    ),
    "default": (
        "the first branch of a `choice` is the one drawn on the main line: put the usual one first"
    ),
    "index": (
        "the first branch of a `choice` is the one drawn on the main line: put the usual one first"
    ),
    "skip": "an alternative that matches nothing is an `optional` round the `choice`",
    "empty": "an alternative that matches nothing is an `optional` round the `choice`",
    "role": (
        "an item is drawn by what it is — a terminal rounded, a rule square, a special dashed: "
        "say `terminal`, `rule` or `special` instead"
    ),
    "id": "nothing refers to an item: a rule is referred to by its `name`",
    "edges": (
        "a track's lines are derived from `seq`, `choice`, `optional` and `repeat`; arbitrary "
        "lines between boxes are a `flow`"
    ),
    "nodes": "a grammar is written as `rules`, each an `expr`",
}


def _railroad_refusal(violation: Violation) -> Violation:
    """A structural refusal in a railroad, told what this kind means by it."""
    parts = violation.pointer.split("/")
    name = parts[-1]
    if "is not a known field" in violation.message and name in RAILROAD_REFUSED:
        return Violation(violation.pointer, f"{name!r}: {RAILROAD_REFUSED[name]}.")
    if name == "seq" and "needs at least" in violation.message:
        return Violation(
            violation.pointer,
            "a 'seq' of fewer than 2 items is that item: write it on its own.",
        )
    if name == "choice" and "needs at least" in violation.message:
        return Violation(
            violation.pointer,
            "a 'choice' needs 2 alternatives at least; one is that item on its own, and one "
            "that may be left out is an 'optional'.",
        )
    return violation


def _railroad_children(entry: Mapping[str, Any], pointer: str) -> Iterator[tuple[object, str]]:
    """Every item directly inside `entry`, with its pointer."""
    for key in ("seq", "choice"):
        value = entry.get(key)
        if isinstance(value, list):
            for index, element in enumerate(value):
                yield element, f"{pointer}/{key}/{index}"
    for key in ("optional", "repeat", "separator"):
        value = entry.get(key)
        if isinstance(value, dict):
            yield value, f"{pointer}/{key}"


def _railroad_too_deep(document: Mapping[str, Any]) -> Violation | None:
    """The first item nested past `RAILROAD_DEPTH_MAX`, found without recursion.

    As `_sunburst_too_deep`: `railroad-item` refers to itself, the structural pass
    recurses once per level, and a pathologically deep document must come back as
    a located violation rather than a `RecursionError`.
    """
    rules = document.get("rules")
    if not isinstance(rules, list):
        return None
    stack: list[tuple[object, str, int]] = [
        (rule.get("expr"), f"/rules/{index}/expr", 1)
        for index, rule in enumerate(rules)
        if isinstance(rule, dict)
    ]
    while stack:
        entry, pointer, depth = stack.pop()
        if not isinstance(entry, dict):
            continue
        if depth > RAILROAD_DEPTH_MAX:
            return Violation(
                pointer,
                f"items nested {depth} deep are past what one track can be followed at — "
                f"{RAILROAD_DEPTH_MAX} at most. Make the inner part a rule of its own and "
                f'refer to it with {{"rule": name}}.',
            )
        stack.extend(
            (child, where, depth + 1) for child, where in _railroad_children(entry, pointer)
        )
    return None


def _railroad_words(value: object, pointer: str, what: str, found: list[Violation]) -> None:
    """A box's, a comment's or a name's words: present, and on one line."""
    if not isinstance(value, str):
        return
    if not value.strip():
        found.append(Violation(pointer, f"{what} needs words: an empty one is a blank box."))
    elif "\n" in value:
        found.append(
            Violation(
                pointer,
                f"{what} is one line on a track: a newline has nowhere to go. Shorten it, or "
                f"split it into two items in a 'seq'.",
            )
        )


def _railroad_violations(document: Mapping[str, Any]) -> list[Violation]:
    """Each item one thing, its fields its own, every rule it names defined, and the caps."""
    found: list[Violation] = []
    rules = document.get("rules")
    if not isinstance(rules, list):
        return found

    defined: dict[str, int] = {}
    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            continue
        name = rule.get("name")
        _railroad_words(name, f"/rules/{index}/name", "a rule's name", found)
        if isinstance(name, str) and name.strip():
            if name in defined:
                found.append(
                    Violation(
                        f"/rules/{index}/name",
                        f"a rule named {name!r} is already defined at /rules/{defined[name]}: "
                        f"each rule is drawn once, so merge the two with a 'choice'.",
                    )
                )
            else:
                defined[name] = index

    external: dict[str, int] = {}
    listed = document.get("external")
    if isinstance(listed, list):
        for index, name in enumerate(listed):
            if not isinstance(name, str):
                continue
            pointer = f"/external/{index}"
            _railroad_words(name, pointer, "an external rule's name", found)
            if name in defined:
                found.append(
                    Violation(
                        pointer,
                        f"{name!r} is defined in this document, at /rules/{defined[name]}, so it "
                        f"is not external: take it out of 'external'.",
                    )
                )
            elif name in external:
                found.append(Violation(pointer, f"{name!r} is listed twice in 'external'."))
            else:
                external[name] = index

    used: set[str] = set()
    known = sorted({*defined, *external})

    def check(entry: object, pointer: str, counter: list[int]) -> None:
        if not isinstance(entry, dict):
            return
        shapes = [shape for shape in RAILROAD_SHAPES if shape in entry]
        if not shapes:
            found.append(
                Violation(
                    pointer,
                    "an item needs to say what it is: one of "
                    + ", ".join(f"'{shape}'" for shape in RAILROAD_SHAPES)
                    + ".",
                )
            )
            return
        if len(shapes) > 1:
            found.append(
                Violation(
                    f"{pointer}/{shapes[1]}",
                    f"an item is one thing, and this one says both {shapes[0]!r} and "
                    f"{shapes[1]!r}. Put them one after the other in a 'seq', or one inside "
                    f"the other.",
                )
            )
            return
        shape = shapes[0]
        if shape != "repeat":
            for key in ("separator", "min"):
                if key in entry:
                    found.append(
                        Violation(
                            f"{pointer}/{key}",
                            f"{key!r} belongs to a 'repeat', and this item is a {shape!r}.",
                        )
                    )
        if shape in RAILROAD_BOXES:
            counter[0] += 1
            words = {
                "terminal": "a terminal",
                "rule": "a rule box",
                "special": "a special box",
                "comment": "a comment",
            }[shape]
            _railroad_words(entry[shape], f"{pointer}/{shape}", words, found)
            if shape == "rule" and isinstance(entry[shape], str) and entry[shape].strip():
                target = entry[shape]
                used.add(target)
                if target not in defined and target not in external:
                    close = get_close_matches(target, known, n=1)
                    hint = f" Did you mean {close[0]!r}?" if close else ""
                    found.append(
                        Violation(
                            f"{pointer}/rule",
                            f"no rule is named {target!r}: define it in 'rules', or list it in "
                            f"'external' if it is drawn elsewhere.{hint}",
                        )
                    )
            return
        branches = entry["choice"] if shape == "choice" else None
        if isinstance(branches, list) and len(branches) > RAILROAD_BRANCH_MAX:
            found.append(
                Violation(
                    f"{pointer}/choice",
                    f"{len(branches)} alternatives are past what one choice can be read at — "
                    f"{RAILROAD_BRANCH_MAX} at most. Group some under a rule of their own.",
                )
            )
        if shape == "optional" and isinstance(entry["optional"], dict):
            inner = entry["optional"]
            if "optional" in inner or (inner.get("repeat") is not None and inner.get("min") == 0):
                found.append(
                    Violation(
                        f"{pointer}/optional",
                        "this is already optional: a second bypass round it draws nothing new. "
                        "Take one away.",
                    )
                )
        if shape == "repeat":
            if "min" not in entry:
                found.append(
                    Violation(
                        f"{pointer}/min",
                        "a 'repeat' needs 'min': 1 for one or more, 0 for zero or more (a loop "
                        "that may also be skipped).",
                    )
                )
            elif isinstance(entry["min"], int) and entry["min"] not in (0, 1):
                found.append(
                    Violation(
                        f"{pointer}/min",
                        f"'min' is 0 or 1, not {entry['min']!r}: a loop is drawn the same "
                        f"whatever its count. Write the item that many times in a 'seq' before "
                        f"a repeat with min 0.",
                    )
                )
            separator = entry.get("separator")
            if isinstance(separator, dict) and any(key in separator for key in RAILROAD_COMBINERS):
                found.append(
                    Violation(
                        f"{pointer}/separator",
                        "a separator is one box or a comment — a 'terminal', 'rule', 'special' "
                        "or 'comment' — because it is read backwards along the loop. Make a "
                        "longer one a rule of its own.",
                    )
                )
        for child, where in _railroad_children(entry, pointer):
            check(child, where, counter)

    for index, rule in enumerate(rules):
        if not isinstance(rule, dict):
            continue
        counter = [0]
        check(rule.get("expr"), f"/rules/{index}/expr", counter)
        if counter[0] > RAILROAD_BOX_MAX:
            found.append(
                Violation(
                    f"/rules/{index}/expr",
                    f"{counter[0]} boxes on one track is past what one rule can be read at — "
                    f"{RAILROAD_BOX_MAX} at most. Factor part of it into a rule of its own, "
                    f"as SQLite's diagrams do.",
                )
            )

    for name, index in external.items():
        if name not in used:
            found.append(
                Violation(
                    f"/external/{index}",
                    f"no rule box refers to {name!r}, so listing it says nothing: take it out.",
                )
            )
    return found


#: Why a use case diagram has no place for a field an author may reach for.
USECASE_REFUSED: Final = {
    "text": (
        "a relation's words are its role: `include` is drawn «include» and `extend` "
        "«extend», and an association is a plain line. A condition on an extension belongs "
        "in the extending use case's own words"
    ),
    "label": (
        "a relation's words are its role: `include` is drawn «include» and `extend` "
        "«extend», and an association is a plain line"
    ),
    "side": (
        "which side an actor stands on is derived — primary actors left, supporting ones "
        "right. Say `supporting: true` for an actor who serves rather than starts the use "
        "cases"
    ),
    "x": "a use case diagram is placed by drawspec; there are no coordinates",
    "y": "a use case diagram is placed by drawspec; there are no coordinates",
    "column": (
        "a use case's column is derived: one included, extending or specialising another "
        "stands right of it"
    ),
    "role": (
        "an actor is a stick figure and a use case an ellipse, with nothing else to mark: "
        "they take `id`, `text` and `supporting` or `system` only"
    ),
    "groups": ("a use case diagram's frames are its `systems`; name each use case's `system`"),
    "nodes": (
        "a use case diagram's things are `actors` (outside the boundary) and `usecases` (inside it)"
    ),
    "multiplicity": (
        "a use case diagram's associations carry no multiplicities here; say how many in "
        "the use case's words"
    ),
}


def _usecase_refusal(violation: Violation) -> Violation:
    """A structural refusal in a use case diagram, told what this kind means by it."""
    name = violation.pointer.split("/")[-1]
    if "is not a known field" in violation.message and name in USECASE_REFUSED:
        return Violation(violation.pointer, f"{name!r}: {USECASE_REFUSED[name]}.")
    return violation


def usecase_columns(cases: Sequence[str], edges: Sequence[tuple[str, str, str]]) -> dict[str, int]:
    """Each use case's column inside its boundary, 0 at the left.

    A use case that is included, that extends another, or that specialises another
    stands one column right of the use case it is about — the longest such chain
    decides. `edges` are `(from, to, role)`; anything not between two of `cases`
    is ignored, and a loop (refused by validation) stops where it closes.
    """
    known = set(cases)
    later: dict[str, list[str]] = {name: [] for name in cases}
    for source, target, role in edges:
        if source not in known or target not in known or source == target:
            continue
        if role == "include":
            later[source].append(target)
        elif role in ("extend", "inherits"):
            later[target].append(source)
    column = dict.fromkeys(cases, 0)
    # Longest path by relaxation; bounded by the number of use cases, so a loop
    # that slipped through cannot spin forever.
    for _ in range(len(cases)):
        changed = False
        for name in cases:
            for after in later[name]:
                if column[after] < column[name] + 1:
                    column[after] = column[name] + 1
                    changed = True
        if not changed:
            break
    return column


def usecase_sides(
    actors: Sequence[tuple[str, bool | None]],
    edges: Sequence[tuple[str, str, str]],
) -> dict[str, str]:
    """Each actor's side of the boundary, `left` or `right`.

    A written `supporting` decides; an actor that inherits stands on its parent's
    side; otherwise an actor whose every use case an actor written before it
    already has is supporting — a bank behind the customer's withdrawal — and
    stands on the right. The rest are primary, on the left.
    """
    names = [name for name, _ in actors]
    known = set(names)
    parent: dict[str, str] = {}
    cases: dict[str, set[str]] = {name: set() for name in names}
    for source, target, role in edges:
        if role == "inherits" and source in known and target in known:
            parent.setdefault(source, target)
        elif role == "association":
            if source in known and target not in known:
                cases[source].add(target)
            elif target in known and source not in known:
                cases[target].add(source)
    written = dict(actors)
    side: dict[str, str] = {}

    def resolve(name: str, seen: frozenset[str]) -> str:
        if name in side:
            return side[name]
        if name in parent and parent[name] not in seen:
            side[name] = resolve(parent[name], seen | {name})
            return side[name]
        choice = written.get(name)
        if choice is None:
            before: set[str] = set()
            for earlier in names[: names.index(name)]:
                before |= cases[earlier]
            choice = bool(cases[name]) and cases[name] <= before
        side[name] = "right" if choice else "left"
        return side[name]

    for name in names:
        resolve(name, frozenset({name}))
    return side


def _usecase_violations(document: Mapping[str, Any]) -> list[Violation]:
    """Ids that land, relations between the right ends, no loops, the column cap."""
    found: list[Violation] = []
    owner: dict[str, str] = {}
    actors: dict[str, int] = {}
    cases: dict[str, int] = {}
    systems: dict[str, int] = {}
    for array, table in (("systems", systems), ("actors", actors), ("usecases", cases)):
        for index, entry in enumerate(_listed(document, array)):
            if not isinstance(entry, dict):
                continue
            identifier = entry.get("id")
            text = entry.get("text")
            if isinstance(text, str) and not text.strip():
                found.append(
                    Violation(_pointer(array, index, "text"), "this needs words to be drawn.")
                )
            if not isinstance(identifier, str):
                continue
            if identifier in owner:
                found.append(
                    Violation(
                        _pointer(array, index, "id"),
                        f"duplicate id {identifier!r} (already used in /{owner[identifier]}): "
                        "actors, use cases and systems share one set of ids.",
                    )
                )
                continue
            owner[identifier] = f"{array}/{index}"
            table[identifier] = index

    # Each use case in a boundary, when there are boundaries.
    system_of: dict[str, str] = {}
    only = next(iter(systems)) if len(systems) == 1 else ""
    for index, entry in enumerate(_listed(document, "usecases")):
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            continue
        named = entry.get("system")
        if isinstance(named, str):
            if named not in systems:
                found.append(
                    Violation(
                        _pointer("usecases", index, "system"),
                        f"{named!r} is not the id of any system" + _closest(named, systems),
                    )
                )
                continue
            system_of[entry["id"]] = named
        elif len(systems) > 1:
            found.append(
                Violation(
                    _pointer("usecases", index),
                    "with more than one system, each use case names the `system` whose "
                    "boundary it is drawn in.",
                )
            )
        else:
            system_of[entry["id"]] = only
    for identifier, index in systems.items():
        if identifier not in system_of.values():
            found.append(
                Violation(
                    _pointer("systems", index),
                    f"system {identifier!r} holds no use case, so its boundary would be an "
                    "empty box: give it a use case or leave it out.",
                )
            )

    # The relations.
    landed: list[tuple[str, str, str]] = []
    pairs: dict[frozenset[str], int] = {}
    linked: set[str] = set()
    parents: dict[str, str] = {}
    for index, entry in enumerate(_listed(document, "edges")):
        if not isinstance(entry, dict):
            continue
        role = entry.get("role", "association")
        if role not in USECASE_EDGE_ROLES:
            continue
        ends: list[str] = []
        for end in ("from", "to"):
            name = entry.get(end)
            if not isinstance(name, str):
                continue
            if name in systems:
                found.append(
                    Violation(
                        _pointer("edges", index, end),
                        f"{name!r} is a system: a relation joins an actor or a use case, and "
                        "the boundary is drawn round its use cases.",
                    )
                )
                continue
            if name not in actors and name not in cases:
                found.append(
                    Violation(
                        _pointer("edges", index, end),
                        f"{name!r} is not the id of any actor or use case"
                        + _closest(name, {**actors, **cases}),
                    )
                )
                continue
            ends.append(name)
        if len(ends) != 2:
            continue
        source, target = ends
        here = _pointer("edges", index)
        if source == target:
            found.append(
                Violation(here, f"a relation from {source!r} to itself says nothing: leave it out.")
            )
            continue
        pair = frozenset(ends)
        if pair in pairs:
            found.append(
                Violation(
                    here,
                    f"a second relation between {source!r} and {target!r} (the first is "
                    f"/edges/{pairs[pair]}): two things are related one way.",
                )
            )
            continue
        pairs[pair] = index
        actor_ends = [name in actors for name in ends]
        if role == "association":
            if all(actor_ends):
                found.append(
                    Violation(
                        here,
                        f"an association between two actors, {source!r} and {target!r}: actors "
                        "meet through the use cases they share. Join each to the use case, or "
                        "say one is a kind of the other with `inherits`.",
                    )
                )
                continue
            if not any(actor_ends):
                found.append(
                    Violation(
                        _pointer("edges", index, "role"),
                        f"an association between two use cases, {source!r} and {target!r}: "
                        "say how they relate — `include` (one always does the other), `extend` "
                        "(one sometimes adds to the other) or `inherits`.",
                    )
                )
                continue
        elif role in ("include", "extend"):
            if any(actor_ends):
                found.append(
                    Violation(
                        _pointer("edges", index, "role"),
                        f"`{role}` joins two use cases, and {source if actor_ends[0] else target!r}"
                        " is an actor: an actor takes part through an `association`.",
                    )
                )
                continue
        elif actor_ends[0] != actor_ends[1]:
            found.append(
                Violation(
                    _pointer("edges", index, "role"),
                    f"`inherits` says one thing is a kind of another, actor to actor or use case "
                    f"to use case — {source!r} and {target!r} are one of each.",
                )
            )
            continue
        if (
            role != "association"
            and not any(actor_ends)
            and system_of.get(source) != system_of.get(target)
        ):
            found.append(
                Violation(
                    here,
                    f"{source!r} and {target!r} are in different systems: a use case "
                    f"{role}s one in its own boundary. Move them into one system.",
                )
            )
            continue
        if role == "inherits" and all(actor_ends):
            if source in parents:
                found.append(
                    Violation(
                        here,
                        f"{source!r} already inherits from {parents[source]!r}: an actor here is a "
                        "kind of one other actor at most.",
                    )
                )
                continue
            parents[source] = target
        linked.update(ends)
        landed.append((source, target, role))

    # Actor generalisation: one level, no loop.
    for child, parent in parents.items():
        if parent in parents:
            index = next(
                i
                for i, entry in enumerate(_listed(document, "edges"))
                if isinstance(entry, dict)
                and entry.get("from") == child
                and entry.get("role") == "inherits"
            )
            found.append(
                Violation(
                    _pointer("edges", index),
                    f"{child!r} inherits from {parent!r}, which itself inherits from "
                    f"{parents[parent]!r}: one level of actor generalisation is drawn. Have "
                    f"{child!r} inherit from {parents[parent]!r} directly.",
                )
            )

    # An actor written supporting against the side its parent stands on — the
    # parent's written `supporting`, or the side derived for it.
    entries = _listed(document, "actors")
    declared: list[tuple[str, bool | None]] = []
    for name, index in actors.items():
        entry = entries[index]
        value = entry.get("supporting") if isinstance(entry, dict) else None
        declared.append((name, value if isinstance(value, bool) else None))
    resolved = usecase_sides(declared, landed)
    written_of = dict(declared)
    for child, parent in parents.items():
        written = written_of.get(child)
        if written is None:
            continue
        theirs = resolved.get(parent, "left")
        if ("right" if written else "left") != theirs:
            found.append(
                Violation(
                    _pointer("actors", actors[child], "supporting"),
                    f"{child!r} inherits from {parent!r}, which stands on the {theirs}, so it "
                    "stands there too: leave `supporting` out of it.",
                )
            )

    # No loop among the use cases, and the column cap.
    later: dict[str, set[str]] = {name: set() for name in cases}
    for source, target, role in landed:
        if source in actors or target in actors:
            continue
        first, second = (source, target) if role == "include" else (target, source)
        later[first].add(second)

    def reaches(start: str, goal: str) -> bool:
        stack, seen = [start], set()
        while stack:
            name = stack.pop()
            if name == goal:
                return True
            if name in seen:
                continue
            seen.add(name)
            stack.extend(later[name])
        return False

    looped = False
    for name in cases:
        if any(reaches(after, name) for after in later[name]):
            found.append(
                Violation(
                    _pointer("usecases", cases[name]),
                    f"the relations between use cases go round in a loop through {name!r}: "
                    "an included or extending use case is a part of another, never its whole.",
                )
            )
            looped = True
            break
    if not looped:
        columns = usecase_columns(list(cases), landed)
        for name, column in columns.items():
            if column >= USECASE_COLUMN_MAX:
                found.append(
                    Violation(
                        _pointer("usecases", cases[name]),
                        f"{name!r} is {column + 1} use cases deep in a chain of include, extend "
                        f"and inherits, and a boundary holds {USECASE_COLUMN_MAX} columns. "
                        "Fold a step into the use case it is part of, or draw it as a use case "
                        "diagram of its own.",
                    )
                )
                break

    for name, index in actors.items():
        if name not in linked:
            found.append(
                Violation(
                    _pointer("actors", index),
                    f"actor {name!r} takes part in nothing: associate it with a use case, or "
                    "leave it out.",
                )
            )
    return found


#: Why a Wardley map has no place for a field an author may reach for.
WARDLEY_REFUSED: Final = {
    "visibility": (
        "a component's height is its place in the value chain, derived from `needs`: one row "
        "below the lowest thing that needs it. To sink it further, give it a `depth` (a row)"
    ),
    "maturity": "say how evolved it is by name, in `evolution` (`late product`), not as a number",
    "position": (
        "a component's place is derived: across from its `evolution` stage, down from its "
        "place in the value chain. Neither is a coordinate"
    ),
    "at": "say where in its stage a component is with `early` or `late` in `evolution`",
    "stage": "the stage is written in `evolution` itself: `product`, `early product`, …",
    "edges": "a dependency is written on the component that has it, as `needs`",
    "role": (
        "a component is a dot and its name; what it is about goes in a numbered `note`, and an "
        "anchor is an anchor because it is in `anchors`"
    ),
    "label": "a component's name is its `text`, and drawspec places it clear of every line",
}


def _wardley_refusal(violation: Violation) -> Violation:
    """A structural refusal in a Wardley map, told what this kind means by it."""
    name = violation.pointer.split("/")[-1]
    if name in WARDLEY_REFUSED and "is not" in violation.message:
        return Violation(violation.pointer, f"{name!r}: {WARDLEY_REFUSED[name]}.")
    if name in ("evolution", "evolves") and (
        "is not one of" in violation.message or "expected string" in violation.message
    ):
        return Violation(
            violation.pointer,
            f"{name!r} is a named place on the evolution axis, not a number: one of "
            f"{', '.join(repr(value) for value in WARDLEY_EVOLUTION)}.",
        )
    return violation


def wardley_depths(
    anchors: Mapping[str, Sequence[str]],
    components: Mapping[str, Sequence[str]],
    pinned: Mapping[str, int],
) -> dict[str, int]:
    """Each component's row in the value chain, the anchors being row 0.

    One row below the lowest thing that needs it — the longest path down from an
    anchor — or its `depth`, when that is lower still. A component no anchor
    reaches is left out; a loop is refused by validation before this is asked.
    """
    depths: dict[str, int] = {}
    parents: dict[str, list[str]] = {name: [] for name in components}
    for owner, needs in (*anchors.items(), *components.items()):
        for need in dict.fromkeys(needs):
            if need in parents and need != owner:
                parents[need].append(owner)
    for name in _wardley_order(components):
        reached = [
            0 if p in anchors else depths[p] for p in parents[name] if p in anchors or p in depths
        ]
        if reached:
            depths[name] = max(1 + max(reached), pinned.get(name, 0))
    return depths


def _wardley_order(components: Mapping[str, Sequence[str]]) -> list[str]:
    """The components in dependency order: each after everything that needs it.

    Shorter than `components` when some of them need each other in a loop.
    """
    incoming = dict.fromkeys(components, 0)
    for owner, needs in components.items():
        for need in dict.fromkeys(needs):
            if need in incoming and need != owner:
                incoming[need] += 1
    ready = [name for name in components if incoming[name] == 0]
    order: list[str] = []
    while ready:
        name = ready.pop(0)
        order.append(name)
        for need in dict.fromkeys(components[name]):
            if need in incoming and need != name:
                incoming[need] -= 1
                if incoming[need] == 0:
                    ready.append(need)
    return order


def _wardley_needs(entry: Mapping[str, Any]) -> list[str]:
    needs = entry.get("needs", [])
    return [need for need in needs if isinstance(need, str)] if isinstance(needs, list) else []


def _wardley_violations(document: Mapping[str, Any]) -> list[Violation]:
    """Unique ids, needs that resolve, no loop, everything anchored, rightward moves."""
    found: list[Violation] = []
    raw_anchors = document.get("anchors", ())
    raw_components = document.get("components", ())
    anchors = (
        [a for a in raw_anchors if isinstance(a, dict)] if isinstance(raw_anchors, list) else []
    )
    components = (
        [c for c in raw_components if isinstance(c, dict)]
        if isinstance(raw_components, list)
        else []
    )
    seen: set[str] = set()
    for group, entries in (("anchors", anchors), ("components", components)):
        for index, entry in enumerate(entries):
            here = f"/{group}/{index}"
            ident = entry.get("id")
            if isinstance(ident, str):
                if ident in seen:
                    found.append(
                        Violation(f"{here}/id", f"{ident!r} is used twice: an id names one thing.")
                    )
                seen.add(ident)
            text = entry.get("text")
            if isinstance(text, str) and not text.strip():
                found.append(Violation(f"{here}/text", "a component needs a name."))
            elif isinstance(text, str) and "\n" in text:
                found.append(
                    Violation(
                        f"{here}/text",
                        "a name on a Wardley map is one line, set beside its dot; put the detail "
                        "in a numbered `note`.",
                    )
                )
    anchor_ids = {a["id"] for a in anchors if isinstance(a.get("id"), str)}
    component_ids = {c["id"] for c in components if isinstance(c.get("id"), str)}

    for group, entries in (("anchors", anchors), ("components", components)):
        for index, entry in enumerate(entries):
            ident = entry.get("id")
            listed: set[str] = set()
            for position, need in enumerate(_wardley_needs(entry)):
                where = f"/{group}/{index}/needs/{position}"
                if need == ident:
                    found.append(Violation(where, "a component cannot need itself."))
                elif need in anchor_ids:
                    found.append(
                        Violation(
                            where,
                            f"{need!r} is an anchor: an anchor is the user at the top of the "
                            f"chain, so nothing needs it.",
                        )
                    )
                elif need not in component_ids:
                    found.append(Violation(where, f"{need!r} is not the id of any component."))
                elif need in listed:
                    found.append(Violation(where, f"{need!r} is listed twice."))
                listed.add(need)

    anchor_needs = {a["id"]: _wardley_needs(a) for a in anchors if isinstance(a.get("id"), str)}
    component_needs = {
        c["id"]: _wardley_needs(c) for c in components if isinstance(c.get("id"), str)
    }
    order = _wardley_order(component_needs)
    if len(order) < len(component_needs):
        looped = sorted(set(component_needs) - set(order))
        found.append(
            Violation(
                "/components",
                f"{', '.join(repr(name) for name in looped)} need each other in a loop. A value "
                f"chain only runs down: each component sits below what needs it.",
            )
        )
        return found
    pinned = {
        c["id"]: c["depth"]
        for c in components
        if isinstance(c.get("id"), str)
        and isinstance(c.get("depth"), int)
        and not isinstance(c.get("depth"), bool)
    }
    depths = wardley_depths(anchor_needs, component_needs, {})
    for index, entry in enumerate(components):
        ident = entry.get("id")
        if not isinstance(ident, str):
            continue
        here = f"/components/{index}"
        if ident not in depths:
            found.append(
                Violation(
                    here,
                    f"nothing on the map needs {ident!r}, so it has no place in the value chain. "
                    f"A Wardley map hangs from its anchors: list it in the `needs` of what "
                    f"depends on it.",
                )
            )
            continue
        depth = pinned.get(ident)
        if depth is not None and depth < depths[ident]:
            found.append(
                Violation(
                    f"{here}/depth",
                    f"row {depth} is above what needs {ident!r}: it can sit no higher than row "
                    f"{depths[ident]}. Leave `depth` out, or sink it lower.",
                )
            )
        evolution, evolves = entry.get("evolution"), entry.get("evolves")
        if (
            evolution in WARDLEY_EVOLUTION
            and evolves in WARDLEY_EVOLUTION
            and WARDLEY_EVOLUTION.index(evolves) <= WARDLEY_EVOLUTION.index(evolution)
        ):
            found.append(
                Violation(
                    f"{here}/evolves",
                    f"{evolves!r} is not further right than {evolution!r}: a component "
                    f"evolves towards commodity, so `evolves` names a later place.",
                )
            )
    if not found:
        rows = max(wardley_depths(anchor_needs, component_needs, pinned).values(), default=0)
        if rows > WARDLEY_DEPTH_MAX:
            found.append(
                Violation(
                    "/components",
                    f"the value chain is {rows} rows deep, past the {WARDLEY_DEPTH_MAX} one map "
                    f"can be read at. Fold a run of components into one, or map the lower part "
                    f"on a map of its own.",
                )
            )
    notes = document.get("notes", ())
    if isinstance(notes, list):
        for index, note in enumerate(notes):
            if not isinstance(note, dict):
                continue
            text = note.get("text")
            if isinstance(text, str) and not text.strip():
                found.append(Violation(f"/notes/{index}/text", "a note needs words."))
            on = note.get("on", [])
            for position, target in enumerate(on if isinstance(on, list) else []):
                if isinstance(target, str) and target not in seen:
                    found.append(
                        Violation(
                            f"/notes/{index}/on/{position}",
                            f"{target!r} is not the id of any anchor or component.",
                        )
                    )
    return found


#: Why a packet has no place for a field an author may reach for.
PACKET_REFUSED: Final = {
    "start": (
        "a field starts where the one before it ends: write the fields in order, each with "
        "its width in `bits`"
    ),
    "end": "a field ends where its `bits` take it, counted from where the one before it ended",
    "offset": "a field's offset is the sum of the widths written before it, never written",
    "position": "a field's position is the sum of the widths written before it, never written",
    "range": (
        "a field is its width in `bits`, in order; a bit range such as `0-3` is a position, "
        "which drawspec derives"
    ),
    "length": "a field's width is `bits`",
    "size": "a field's width is `bits`; the type size is the theme's",
    "name": "a field's name is `text`",
    "label": "a field's name is `text`",
    "attr": "what a field holds — a fixed value, a reset value, its access — is `holds`",
    "value": "what a field holds — a fixed value, a reset value, its access — is `holds`",
    "reset": "a reset value is what the field `holds`: write it there (`0x00`)",
    "access": "a field's access is what it `holds`: write it there (`R/W`)",
    "reserved": 'a reserved field is `"role": "reserved"`',
    "type": 'a reserved field is `"role": "reserved"`; anything else is an ordinary field',
    "rotate": (
        "a name is turned on its side by drawspec, only when it will not fit across its field"
    ),
    "lanes": "the rows are `bits_per_row` wide, and as many as the fields fill",
    "vspace": "a row's height is measured from the words in it",
    "hspace": "the drawing is the canvas's width; a bit is its share of the row",
    "bits_per_row": "`bits_per_row` is the document's, at the top: every row is as wide",
    "numbering": "`numbering` is the document's, at the top: every row counts the same way",
    "colour": "a field is told by its name and its role; a reserved one is hatched by the theme",
    "edges": "a packet is a row of fields side by side; there is nothing to connect",
    "variable": (
        "a packet draws fields of a known width. Draw a variable-length field (options, the "
        "payload) as a whole row and say so in its words: `Options (variable)`"
    ),
}

#: The packet's own top-level fields: refused by name only inside a field.
_PACKET_TOP: Final = ("bits_per_row", "numbering")


def _packet_refusal(violation: Violation) -> Violation:
    """A structural refusal in a packet, told what this kind means by it."""
    parts = violation.pointer.split("/")
    name = parts[-1]
    unknown = "is not" in violation.message and "field" in violation.message
    top = len(parts) == 2 and name in _PACKET_TOP
    if unknown and name in PACKET_REFUSED and not top:
        return Violation(violation.pointer, f"{name!r}: {PACKET_REFUSED[name]}.")
    if name == "bits" and len(parts) == 4 and "greater than" in violation.message:
        return Violation(
            violation.pointer,
            "a field is at least one bit wide; a field of no bits is not drawn — leave it out.",
        )
    return violation


def _packet_violations(document: Mapping[str, Any]) -> list[Violation]:
    """The row width, every field's words, the row cap, and whole rows for a register."""
    found: list[Violation] = []
    row = document.get("bits_per_row", PACKET_ROW_DEFAULT)
    if not isinstance(row, int) or isinstance(row, bool):
        row = PACKET_ROW_DEFAULT
    elif row not in PACKET_ROW_BITS:
        found.append(
            Violation(
                "/bits_per_row",
                f"a row of {row} bits does not line up with a byte: draw it at "
                f"{', '.join(str(bits) for bits in PACKET_ROW_BITS[:-1])} or "
                f"{PACKET_ROW_BITS[-1]} bits.",
            )
        )
        row = PACKET_ROW_DEFAULT
    total = 0
    for index, entry in enumerate(_listed(document, "fields")):
        if not isinstance(entry, dict):
            continue
        found.extend(_packet_field_violations(entry, _pointer("fields", index)))
        bits = entry.get("bits")
        if isinstance(bits, int) and not isinstance(bits, bool) and bits > 0:
            total += bits
    rows = -(-total // row)
    if rows > PACKET_ROW_MAX:
        found.append(
            Violation(
                "/fields",
                f"{total} bits make {rows} rows of {row}, past what one packet can be read at — "
                f"{PACKET_ROW_MAX} rows at most. Split it: the header in one drawing, each "
                f"long part (options, a payload) in its own.",
            )
        )
    if document.get("numbering") == "right" and total % row:
        found.append(
            Violation(
                "/fields",
                f"the fields add up to {total} bits, which is not a whole number of "
                f"{row}-bit rows. A register numbered from the right counts down to bit 0 at "
                f"the end of its last row, so its fields must fill every row: add the "
                f"{row - total % row} missing bits, as a reserved field if they are unused.",
            )
        )
    return found


def _packet_field_violations(entry: Mapping[str, Any], here: str) -> list[Violation]:
    """One field's words: a name unless reserved, one line, and a `short` that is shorter."""
    found: list[Violation] = []
    text = entry.get("text")
    if "text" not in entry and entry.get("role") != "reserved":
        found.append(
            Violation(
                f"{here}/text",
                "a field needs its name in `text`. Only a reserved field "
                '(`"role": "reserved"`) may be left blank.',
            )
        )
    if isinstance(text, str) and not text.strip():
        found.append(
            Violation(
                f"{here}/text",
                "a field's name needs words; leave `text` out of a blank reserved field.",
            )
        )
    if isinstance(text, str) and "\n" in text:
        found.append(
            Violation(
                f"{here}/text",
                "a field's name is one line; drawspec breaks it at spaces when the field is "
                "narrow. Put a second thought in `note`.",
            )
        )
    for name in ("short", "holds", "note"):
        value = entry.get(name)
        if isinstance(value, str) and not value.strip():
            found.append(
                Violation(f"{here}/{name}", f"an empty {name!r} says nothing: leave it out.")
            )
    short = entry.get("short")
    if isinstance(short, str) and short.strip():
        if not isinstance(text, str) or not text.strip():
            found.append(
                Violation(
                    f"{here}/short",
                    "a `short` abbreviates the field's `text`, and this field has none.",
                )
            )
        elif len(short) >= len(text):
            found.append(
                Violation(
                    f"{here}/short",
                    f"{short!r} is no shorter than {text!r}: a `short` is the abbreviation "
                    f"drawn when the name will not fit, so it must be shorter.",
                )
            )
    return found


#: Why a pert activity is computed rather than written, said once.
_PERT_COMPUTED: Final = (
    "computed by drawspec's forward and backward pass from the durations and `after`, and "
    "drawn in the box; it is never written"
)

#: Why a pert network has no place for a field an author may reach for.
PERT_REFUSED: Final = {
    **{
        name: f"an activity's {words} is {_PERT_COMPUTED}"
        for name, words in (
            ("es", "early start"),
            ("ef", "early finish"),
            ("ls", "late start"),
            ("lf", "late finish"),
            ("start", "start"),
            ("end", "finish"),
            ("finish", "finish"),
        )
    },
    "float": f"float (slack) is {_PERT_COMPUTED}",
    "slack": f"float (slack) is {_PERT_COMPUTED}",
    "critical": (
        "the critical path is computed — every activity with no float — and drawn heavy; it "
        "is never marked by hand"
    ),
    "role": (
        "the critical path is computed and drawn heavy, and nothing else in a network is "
        "marked: an activity takes `id`, `text`, a duration and `after`"
    ),
    "lag": (
        "every dependency is finish-to-start with no lag. A wait between two activities is an "
        "activity of its own — `Concrete cures`, with its duration"
    ),
    "type": (
        "every dependency is finish-to-start: the next starts when this one finishes. Start-"
        "to-start and finish-to-finish links are not drawn"
    ),
    "before": "write each dependency once, on the later activity, as `after`",
    "successors": "write each dependency once, on the later activity, as `after`",
    "predecessors": "the activities this one waits for are `after`",
    "dependencies": "the activities this one waits for are `after`",
    "depends_on": "the activities this one waits for are `after`",
    "edges": (
        "a network's arrows are each activity's `after` list: the dependencies are written on "
        "the activities, so no arrow can name an activity that is not there"
    ),
    "nodes": "a network's boxes are its `activities`",
    "most_likely": "the most likely estimate is `likely`",
    "expected": (
        "the expected duration is computed from the three estimates, (optimistic + 4 x likely "
        "+ pessimistic) / 6. Write the three, or a plain `duration`"
    ),
}


def _pert_refusal(violation: Violation) -> Violation:
    """A structural refusal in a pert network, told what this kind means by it."""
    parts = violation.pointer.split("/")
    name = parts[-1]
    unknown = "is not a known field" in violation.message or (
        "is not" in violation.message and "field" in violation.message
    )
    if unknown and name in PERT_REFUSED:
        return Violation(violation.pointer, f"{name!r}: {PERT_REFUSED[name]}.")
    if parts[1:] == ["activities"] and "needs at least" in violation.message:
        return Violation(
            violation.pointer,
            "a network needs at least 2 activities: one activity is its own critical path, "
            "which a sentence says better.",
        )
    return violation


def _pert_violations(document: Mapping[str, Any]) -> list[Violation]:
    """What a network may not be: ids that do not land, durations that are not one, a loop.

    Each activity has one duration — written, or the three PERT estimates in order —
    its `after` names other activities once each, the dependencies stay within the
    budget, and following them never comes back to where it began.
    """
    found: list[Violation] = []
    for name in ("start", "finish"):
        value = document.get(name)
        if isinstance(value, str) and not value.strip():
            found.append(
                Violation(
                    _pointer(name),
                    f"a {name} milestone needs words — `{name.capitalize()}` — or leave "
                    f"`{name}` out.",
                )
            )
    ids: dict[str, int] = {}
    for index, entry in enumerate(_listed(document, "activities")):
        if not isinstance(entry, dict):
            continue
        identifier = entry.get("id")
        if isinstance(identifier, str):
            if identifier in ids:
                found.append(
                    Violation(
                        _pointer("activities", index, "id"),
                        f"{identifier!r} is already the id of activity {ids[identifier]}: "
                        f"every activity needs its own, so `after` names one box.",
                    )
                )
            else:
                ids[identifier] = index
        text = entry.get("text")
        if isinstance(text, str) and not text.strip():
            found.append(
                Violation(
                    _pointer("activities", index, "text"),
                    "an activity needs words: an empty box is a step nobody can do.",
                )
            )
        found.extend(_pert_duration_violations(entry, index))

    graph: dict[str, list[tuple[str, int]]] = {}
    count = 0
    for index, entry in enumerate(_listed(document, "activities")):
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            continue
        identifier = entry["id"]
        seen: set[str] = set()
        for position, before in enumerate(_listed(entry, "after")):
            if not isinstance(before, str):
                continue
            count += 1
            here = _pointer("activities", index, "after", position)
            if before == identifier:
                found.append(Violation(here, f"{identifier!r} cannot wait for itself to finish."))
            elif before in seen:
                found.append(
                    Violation(here, f"{before!r} is already in this `after`: list it once.")
                )
            elif before not in ids:
                close = get_close_matches(before, list(ids), n=1)
                hint = f" Did you mean {close[0]!r}?" if close else ""
                found.append(
                    Violation(here, f"{before!r} names no activity in this network.{hint}")
                )
            else:
                graph.setdefault(before, []).append((identifier, position))
            seen.add(before)
    if count > PERT_DEPENDENCY_MAX:
        found.append(
            Violation(
                "/activities",
                f"{count} dependencies is past what one network can be read at — "
                f"{PERT_DEPENDENCY_MAX} at most, counted across every `after`. Split it into "
                f"an overview network of phases and a network per phase.",
            )
        )
    if found:
        return found
    looped = _pert_cycle(list(ids), graph)
    if looped:
        path, position = looped
        return [
            Violation(
                _pointer("activities", ids[path[-1]], "after", position),
                f"the dependencies go round in a circle ({' -> '.join(path)}): "
                f"{path[0]!r} would have to finish before it could start, so the network has "
                f"no schedule. Remove one of these `after` entries.",
            )
        ]
    return found


def _pert_duration_violations(entry: Mapping[str, Any], index: int) -> list[Violation]:
    """One activity's duration: written, or three PERT estimates in order; never negative."""
    given = [name for name in PERT_ESTIMATES if name in entry]
    if "duration" in entry and given:
        return [
            Violation(
                _pointer("activities", index, given[0]),
                "an activity takes a `duration` or the three PERT estimates, not both: the "
                "estimates are how the duration is found. Keep one.",
            )
        ]
    if "duration" not in entry and not given:
        return [
            Violation(
                _pointer("activities", index),
                "an activity needs a `duration`, or `optimistic`, `likely` and `pessimistic` "
                "for a PERT estimate: without one it has no place in the schedule.",
            )
        ]
    if given and len(given) < len(PERT_ESTIMATES):
        missing = [name for name in PERT_ESTIMATES if name not in entry]
        return [
            Violation(
                _pointer("activities", index, missing[0]),
                f"{missing[0]!r} is required with {', '.join(repr(name) for name in given)}: a "
                f"PERT estimate is all three, or write a plain `duration`.",
            )
        ]
    found: list[Violation] = []
    for name in ("duration", *PERT_ESTIMATES):
        value = entry.get(name)
        if not _is_number(value):
            continue
        value = float(value)  # type: ignore[arg-type]
        if not math.isfinite(value) or value < 0:
            found.append(
                Violation(
                    _pointer("activities", index, name),
                    f"{_figure(value) if math.isfinite(value) else value} is not a length of "
                    f"time: a duration is zero (a milestone) or more.",
                )
            )
    if found or not given:
        return found
    low, likely, high = (entry[name] for name in PERT_ESTIMATES)
    if not all(_is_number(value) for value in (low, likely, high)):
        return found
    if likely < low:
        found.append(
            Violation(
                _pointer("activities", index, "likely"),
                f"the likely duration {_figure(likely)} is shorter than the optimistic "
                f"{_figure(low)}: the estimates run optimistic <= likely <= pessimistic.",
            )
        )
    elif high < likely:
        found.append(
            Violation(
                _pointer("activities", index, "pessimistic"),
                f"the pessimistic duration {_figure(high)} is shorter than the likely "
                f"{_figure(likely)}: the estimates run optimistic <= likely <= pessimistic.",
            )
        )
    return found


def _pert_cycle(
    ids: Sequence[str], graph: Mapping[str, Sequence[tuple[str, int]]]
) -> tuple[list[str], int] | None:
    """The first loop in the dependencies, as a path that ends where it began.

    Returned with the position, in the last activity's `after`, of the entry that
    closes it — where the refusal points. Iterative, so a long chain cannot
    overflow the stack.
    """
    state: dict[str, int] = {}
    for root in ids:
        if root in state:
            continue
        state[root] = 1
        trail = [root]
        stack = [iter(graph.get(root, ()))]
        while stack:
            step = next(stack[-1], None)
            if step is None:
                stack.pop()
                state[trail.pop()] = 2
                continue
            later, position = step
            if state.get(later) == 1:
                begin = trail.index(later)
                return [*trail[begin:], later], position
            if later not in state:
                state[later] = 1
                trail.append(later)
                stack.append(iter(graph.get(later, ())))
    return None


def _figure(value: float) -> str:
    """A number as an author wrote it: no float noise, no trailing zeros."""
    text = f"{round(value, 9):.9f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


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


def _causal_violations(document: Mapping[str, Any], kind: str, nodes: set[str]) -> list[Violation]:
    """A causal loop diagram's signs, delays and loops: whole, causal and checked.

    Signs go on every causal edge or none — a half-signed diagram is ambiguous —
    and only on a `flow`. A loop runs along signed edges in the order written,
    and a type the author states is checked against the signs: an even number of
    negative links reinforces, an odd number balances.
    """
    found: list[Violation] = []
    edges = [edge for edge in _listed(document, "edges") if isinstance(edge, dict)]
    if kind != "flow":
        for index, edge in enumerate(_listed(document, "edges")):
            for name in ("polarity", "delay"):
                if isinstance(edge, dict) and name in edge:
                    found.append(
                        Violation(
                            _pointer("edges", index, name),
                            f"{name!r} marks a causal link, and a causal loop diagram is a "
                            f"`flow`: draw it as one.",
                        )
                    )
        return found
    signed = any("polarity" in edge for edge in edges)
    for index, edge in enumerate(_listed(document, "edges")):
        if not isinstance(edge, dict):
            continue
        role = edge.get("role", "flow")
        if "polarity" in edge and role not in POLARITY_EDGE_ROLES:
            found.append(
                Violation(
                    _pointer("edges", index, "polarity"),
                    f"a {role!r} edge has no causal direction, so it has no sign. Make it a "
                    f"'flow' edge, or drop the sign.",
                )
            )
        elif signed and "polarity" not in edge and role in POLARITY_EDGE_ROLES:
            found.append(
                Violation(
                    _pointer("edges", index),
                    "this link has no 'polarity' and others do: a half-signed causal diagram "
                    "is ambiguous. Give every causal link its sign, '+' or '-'.",
                )
            )
        if edge.get("delay") and "polarity" not in edge:
            found.append(
                Violation(
                    _pointer("edges", index, "delay"),
                    "a delay belongs to a causal link: give this edge its 'polarity' too.",
                )
            )
    loops = _listed(document, "loops")
    if loops and not signed:
        found.append(
            Violation(
                "/loops",
                "a loop's type is counted from its links' signs, and no edge has a "
                "'polarity'. Give every causal link its sign, '+' or '-'.",
            )
        )
        return found
    polarity: dict[tuple[str, str], str] = {}
    for edge in edges:
        if isinstance(edge.get("from"), str) and isinstance(edge.get("to"), str):
            polarity.setdefault((edge["from"], edge["to"]), edge.get("polarity", ""))
    rings: dict[tuple[str, ...], int] = {}
    for index, loop in enumerate(loops):
        members = loop.get("nodes") if isinstance(loop, dict) else None
        if not isinstance(members, list) or not all(isinstance(m, str) for m in members):
            continue
        whole = True
        for position, member in enumerate(members):
            if member not in nodes:
                whole = False
                found.append(
                    Violation(
                        _pointer("loops", index, "nodes", position),
                        f"{member!r} is not the id of any node"
                        + _closest(member, dict.fromkeys(nodes)),
                    )
                )
            elif member in members[:position]:
                whole = False
                found.append(
                    Violation(
                        _pointer("loops", index, "nodes", position),
                        f"{member!r} is named twice: a loop passes each variable once. Two "
                        f"loops through one variable are two loops.",
                    )
                )
        if not whole or len(members) < 2:
            continue
        for position, member in enumerate(members):
            following = members[(position + 1) % len(members)]
            if (member, following) not in polarity:
                whole = False
                found.append(
                    Violation(
                        _pointer("loops", index, "nodes", position),
                        f"no edge runs {member} \u2192 {following}: a loop's nodes are its "
                        f"variables in the order it runs, each joined to the next and the "
                        f"last back to the first.",
                    )
                )
        if not whole:
            continue
        start = members.index(min(members))
        key = tuple(members[start:] + members[:start])
        if key in rings:
            found.append(
                Violation(
                    _pointer("loops", index, "nodes"),
                    f"loop {rings[key]} is already this loop: the same variables in the same "
                    f"order. Name it once.",
                )
            )
            continue
        rings[key] = index
        minus = sum(
            polarity[(member, members[(position + 1) % len(members)])] == "-"
            for position, member in enumerate(members)
        )
        derived = "balancing" if minus % 2 else "reinforcing"
        stated = loop.get("type")
        if isinstance(stated, str) and stated in LOOP_TYPES and stated != derived:
            found.append(
                Violation(
                    _pointer("loops", index, "type"),
                    f"this loop has {minus} negative link{'s' if minus != 1 else ''}, so it is "
                    f"{derived}: an even number of '-' links reinforces, an odd number "
                    f"balances. Check the signs, or the type.",
                )
            )
    return found


def _shaped_in_cycle(nodes: Any) -> list[Violation]:
    """A cycle step drawn as a flowchart symbol: a ring of boxes has no data in it."""
    return [
        Violation(
            _pointer("nodes", index, "role"),
            (
                "'person' draws a person, and a cycle is a ring of steps that each lead to "
                "the next, not the people taking them. Name who does a step with `actor`, "
                "or draw the people and the system as a `flow`."
            )
            if node["role"] == "person"
            else f"{node['role']!r} draws a flowchart symbol, and a cycle is a ring of steps "
            f"that each lead to the next: there is no input, store or sub-process on it. "
            f"Draw the process as a `flow` if those matter.",
        )
        for index, node in enumerate(nodes if isinstance(nodes, list) else ())
        if isinstance(node, dict) and node.get("role") in SHAPED_ROLES
    ]


def _class_violations(document: Mapping[str, Any], kind: str) -> list[Violation]:
    """Node classes: declared, each used, unique, and never on a box they cannot mark.

    A class is a fill a reader matches against the key, so a class nobody uses
    is a key entry pointing at nothing, and a `class` with no declaration has no
    name to show in the key. A `note` has no outline to fill and a `group` is a
    container; a box with a `status` is already marked, and two marks on one box
    say neither clearly. A `cycle` is a ring of peers: it takes no classes.
    """
    nodes = _listed(document, "nodes")
    classes = document.get("classes")
    found: list[Violation] = []
    if kind == "cycle":
        if "classes" in document:
            found.append(
                Violation(
                    "/classes",
                    "a cycle is a ring of steps that each lead to the next, so it has no "
                    "classes to sort them into. Draw the process as a `flow` to class its "
                    "boxes.",
                )
            )
        found.extend(
            Violation(
                _pointer("nodes", index, "class"),
                "a cycle takes no node classes: draw the process as a `flow` to class its boxes.",
            )
            for index, node in enumerate(nodes)
            if isinstance(node, dict) and "class" in node
        )
        return found
    declared: list[str] = []
    for index, entry in enumerate(classes if isinstance(classes, list) else ()):
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            continue
        if entry["id"] in declared:
            found.append(
                Violation(
                    _pointer("classes", index, "id"),
                    f"duplicate class id {entry['id']!r}: each class is one fill and one "
                    f"line of the key.",
                )
            )
        declared.append(entry["id"])
    used: set[str] = set()
    for index, node in enumerate(nodes):
        if not isinstance(node, dict) or not isinstance(node.get("class"), str):
            continue
        name = node["class"]
        pointer = _pointer("nodes", index, "class")
        if name not in declared:
            close = get_close_matches(name, declared, n=1)
            found.append(
                Violation(
                    pointer,
                    f"{name!r} is not one of the document's classes"
                    + (
                        f" — did you mean {close[0]!r}?"
                        if close
                        else ": declare it in the top-level 'classes' as {id, text}, "
                        "so the key can name it."
                    ),
                )
            )
            continue
        used.add(name)
        role = node.get("role", "step")
        if role in UNCLASSED_ROLES:
            found.append(
                Violation(
                    pointer,
                    f"a {role!r} box takes no class: "
                    + (
                        "a note has no outline to fill, and is not the content."
                        if role == "note"
                        else "a group is a container, not a box of a class."
                    ),
                )
            )
        if node.get("status"):
            found.append(
                Violation(
                    pointer,
                    "a box with a 'status' is already marked by the change; a class's fill "
                    "on it as well says neither clearly. Drop one: a drawing of a change "
                    "is about the change.",
                )
            )
    for index, name in enumerate(declared):
        if name not in used:
            found.append(
                Violation(
                    _pointer("classes", index),
                    f"no node is in the class {name!r}: a key entry that matches nothing in "
                    f"the drawing. Give it to the boxes it names, or remove it.",
                )
            )
    return found


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
    if kind in VENN_KINDS:
        return _venn_document(document)
    if kind in JOURNEY_KINDS:
        return _journey_document(document)
    if kind in TREEMAP_KINDS:
        return _treemap_document(document)
    if kind in SANKEY_KINDS:
        return _sankey_document(document)
    if kind in NUMBERLINE_KINDS:
        return _numberline_document(document)
    if kind in BARMODEL_KINDS:
        return _barmodel_document(document)
    if kind in WATERFALL_KINDS:
        return _waterfall_document(document)
    if kind in PIE_KINDS:
        return _pie_document(document)
    if kind in MINDMAP_KINDS:
        return _mindmap_document(document)
    if kind in ARGUMENT_KINDS:
        return _argument_document(document)
    if kind in FAMILYTREE_KINDS:
        return _familytree_document(document)
    if kind in METER_KINDS:
        return _meter_document(document)
    if kind in RAG_KINDS:
        return _rag_document(document)
    if kind in CLOCK_KINDS:
        return _clock_document(document)
    if kind in SUNBURST_KINDS:
        return _sunburst_document(document)
    if kind in PACKET_KINDS:
        return _packet_document(document)
    if kind in WARDLEY_KINDS:
        return _wardley_document(document)
    if kind in USECASE_KINDS:
        return _usecase_document(document)
    if kind in RAILROAD_KINDS:
        return _railroad_document(document)
    if kind in NETWORK_KINDS:
        return _network_document(document)
    if kind in TIMING_KINDS:
        return _timing_document(document)
    if kind in GITGRAPH_KINDS:
        return _gitgraph_document(document)
    if kind in PERT_KINDS:
        return _pert_document(document)
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
        tree_style=str(document.get("style", "boxes")) if kind == "tree" else "boxes",
        bracket_root=str(document.get("root", "right")) if kind == "tree" else "right",
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
                klass=entry.get("class", ""),
            )
            for entry in document.get("nodes", ())
        ),
        classes=_classes(document),
        hub=_hub(document.get("hub")),
        edges=tuple(
            Edge(
                source=entry["from"],
                target=entry["to"],
                label=entry.get("label", ""),
                role=entry.get("role", "flow"),
                status=entry.get("status", ""),
                polarity=entry.get("polarity", ""),
                delay=bool(entry.get("delay", False)),
            )
            for entry in document.get("edges", ())
        ),
        loops=tuple(
            CausalLoop(
                text=entry["text"],
                nodes=tuple(entry["nodes"]),
                type=entry.get("type", ""),
            )
            for entry in document.get("loops", ())
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
        unit=str(document.get("unit", "")),
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
        quadrants=tuple(str(name) for name in document.get("quadrants", ())),
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


def _classes(document: Mapping[str, Any]) -> tuple[NodeClass, ...]:
    return tuple(
        NodeClass(id=entry["id"], text=entry["text"]) for entry in document.get("classes", ())
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
            klass=entry.get("class", ""),
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
        phases=tuple(
            Phase(text=entry["text"], members=tuple(entry["members"]))
            for entry in document.get("phases", ())
        ),
        classes=_classes(document),
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
            Node(id=entry["id"], text=entry.get("text", ""), role=entry.get("role", "step"))
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
            group for entry in document.get("groups", ()) for group in _composite_groups(entry)
        ),
    )


def region_id(composite: str, number: int) -> str:
    """The id a composite's region is drawn under: never one an author can write."""
    return f"({composite} region {number + 1})"


def _composite_groups(entry: Mapping[str, Any]) -> tuple[Group, ...]:
    """A composite as groups: itself, and for one with regions a frameless group per region."""
    regions = entry.get("regions")
    if not regions:
        return (
            Group(
                id=entry["id"],
                members=tuple(entry["members"]),
                text=entry["text"],
                initial=entry.get("initial", ""),
            ),
        )
    names = tuple(region_id(entry["id"], number) for number in range(len(regions)))
    return (
        Group(id=entry["id"], members=names, text=entry["text"]),
        *(
            Group(
                id=name,
                members=tuple(region["members"]),
                initial=region.get("initial", ""),
                region=True,
            )
            for name, region in zip(names, regions, strict=True)
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
                centre=bool(entry.get("centre", False)),
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
                done=_optional_number(entry.get("done")),
                events=tuple(
                    TaskEvent(at=float(event["at"]), text=event.get("text", ""))
                    for event in entry.get("events", ())
                ),
                iterations=tuple(
                    (float(cycle["start"]), float(cycle["end"]))
                    for cycle in entry.get("iterations", ())
                ),
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


def _venn_document(document: Mapping[str, Any]) -> Document:
    """A venn: its sets in order, and its regions by membership."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        venn_sets=tuple(
            VennSet(id=entry["id"], text=entry["text"], role=entry.get("role", "step"))
            for entry in document["sets"]
        ),
        regions=tuple(
            Region(
                members=tuple(entry["in"]),
                text=entry["text"],
                role=entry.get("role", "step"),
            )
            for entry in document.get("regions", ())
        ),
    )


def _journey_document(document: Mapping[str, Any]) -> Document:
    """A journey: its feelings worst first, its rows, and its stages in order."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        feelings=tuple(document["feelings"]),
        journey_rows=tuple(
            Slice(id=entry["id"], text=entry["text"]) for entry in document.get("rows", ())
        ),
        journey_stages=tuple(
            JourneyStage(
                text=entry["text"],
                feeling=entry["feeling"],
                role=entry.get("role", "step"),
                details=tuple(
                    Detail(row=detail["row"], text=detail["text"])
                    for detail in entry.get("details", ())
                ),
            )
            for entry in document["stages"]
        ),
    )


def _treemap_document(document: Mapping[str, Any]) -> Document:
    """A treemap: its parts and groups in the order written."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        values=bool(document.get("values", True)),
        theme=str(document.get("theme", "")),
        unit=str(document.get("unit", "")),
        treemap_parts=tuple(
            TreemapPart(
                text=entry["text"],
                amount=float(entry["amount"]),
                group=entry.get("group", ""),
                role=entry.get("role", "step"),
            )
            for entry in document["parts"]
        ),
        treemap_groups=tuple(
            TreemapGroup(id=entry["id"], text=entry["text"]) for entry in document.get("groups", ())
        ),
    )


def _sankey_document(document: Mapping[str, Any]) -> Document:
    """A sankey: its nodes and flows in the order written."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        values=bool(document.get("values", True)),
        theme=str(document.get("theme", "")),
        unit=str(document.get("unit", "")),
        sankey_nodes=tuple(
            SankeyNode(id=entry["id"], text=entry["text"], role=entry.get("role", "step"))
            for entry in document["nodes"]
        ),
        sankey_flows=tuple(
            SankeyFlow(
                source=entry["from"],
                target=entry["to"],
                amount=float(entry["amount"]),
                role=entry.get("role", "flow"),
            )
            for entry in document["flows"]
        ),
    )


def _numberline_document(document: Mapping[str, Any]) -> Document:
    """A number line: its scale, its points and its ranges in the order written."""
    axis = document["axis"]
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        number_axis=NumberAxis(
            minimum=float(axis["min"]),
            maximum=float(axis["max"]),
            step=_optional_number(axis.get("step")),
            label=str(axis.get("label", "")),
            unit=str(axis.get("unit", "")),
            ends=tuple(axis.get("ends", ())),
        ),
        number_points=tuple(
            NumberPoint(
                at=float(entry["at"]),
                text=entry.get("text", ""),
                open=bool(entry.get("open", False)),
                role=entry.get("role", "step"),
            )
            for entry in document.get("points", ())
        ),
        number_ranges=tuple(
            NumberRange(
                start=_optional_number(entry.get("from")),
                end=_optional_number(entry.get("to")),
                start_open=bool(entry.get("from_open", False)),
                end_open=bool(entry.get("to_open", False)),
                text=entry.get("text", ""),
                role=entry.get("role", "step"),
            )
            for entry in document.get("ranges", ())
        ),
    )


def _barmodel_document(document: Mapping[str, Any]) -> Document:
    """A bar model: its bars top to bottom, each with its parts, and its braces."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        model_bars=tuple(
            ModelBar(
                parts=tuple(
                    ModelPart(
                        amount=_optional_number(part.get("amount")),
                        units=part.get("units"),
                        text=part.get("text", ""),
                        id=part.get("id", ""),
                        role=part.get("role", "step"),
                    )
                    for part in bar["parts"]
                ),
                text=bar.get("text", ""),
                id=bar.get("id", ""),
            )
            for bar in document["bars"]
        ),
        model_braces=tuple(
            ModelBrace(
                over=tuple(brace["over"]),
                amount=_optional_number(brace.get("amount")),
                text=brace.get("text", ""),
            )
            for brace in document.get("braces", ())
        ),
    )


def _waterfall_document(document: Mapping[str, Any]) -> Document:
    """A waterfall: its axis label and its bars, left to right."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        waterfall_label=str(document["axis"]["label"]),
        waterfall_bars=tuple(
            WaterfallBar(
                text=bar["text"],
                total=_optional_number(bar.get("total")),
                amount=_optional_number(bar.get("amount")),
                role=bar.get("role", "step"),
            )
            for bar in document["bars"]
        ),
    )


def _clock_document(document: Mapping[str, Any]) -> Document:
    """A clock sheet: its faces, in reading order, and how each is numbered and read."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        clock_numerals=str(document.get("numerals", "arabic")),
        clock_readout=str(document.get("readout", "words")),
        clocks=tuple(
            ClockFace(
                time=str(face.get("time", "")),
                text=str(face.get("text", "")),
                since=str(face.get("since", "")),
            )
            for face in document["clocks"]
        ),
    )


def _rag_document(document: Mapping[str, Any]) -> Document:
    """A RAG report: its rows, in the order written."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        rag_rows=tuple(
            RagRow(
                text=str(row["text"]),
                rag=str(row["rag"]),
                trend=str(row.get("trend", "")),
                note=str(row.get("note", "")),
            )
            for row in document["rows"]
        ),
    )


def _meter_document(document: Mapping[str, Any]) -> Document:
    """A meter panel: its style and its meters, in reading order."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        meter_style=str(document.get("style", "bar")),
        meters=tuple(
            Meter(
                text=str(meter["text"]),
                amount=float(meter["amount"]),
                max=float(meter["max"]),
                min=float(meter.get("min", 0.0)),
                unit=str(meter.get("unit", "")),
                target=_optional_number(meter.get("target")),
                bands=tuple(
                    MeterBand(text=str(band["text"]), to=float(band["to"]))
                    for band in meter.get("bands", ())
                ),
                role=str(meter.get("role", "step")),
            )
            for meter in document["meters"]
        ),
    )


def _familytree_document(document: Mapping[str, Any]) -> Document:
    """A family tree: its people and its couples, in the order written."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        people=tuple(
            FamilyPerson(
                id=str(person["id"]),
                sex=str(person["sex"]),
                gender=str(person.get("gender", "")),
                text=str(person.get("text", "")),
                status=str(person.get("status", "unaffected")),
                deceased=bool(person.get("deceased", False)),
                proband=bool(person.get("proband", False)),
                consultand=bool(person.get("consultand", False)),
                adopted=bool(person.get("adopted", False)),
                pregnancy=str(person.get("pregnancy", "")),
                role=str(person.get("role", "step")),
            )
            for person in document["people"]
        ),
        couples=tuple(
            FamilyCouple(
                between=(str(couple["between"][0]), str(couple["between"][1])),
                children=tuple(str(child) for child in couple.get("children", ())),
                twins=tuple(
                    FamilyTwins(
                        of=tuple(str(each) for each in twins["of"]),
                        zygosity=str(twins["zygosity"]),
                    )
                    for twins in couple.get("twins", ())
                ),
                separated=bool(couple.get("separated", False)),
                consanguineous=bool(couple.get("consanguineous", False)),
            )
            for couple in document["couples"]
        ),
    )


def _argument_document(document: Mapping[str, Any]) -> Document:
    """An argument map: its claim and its points, in the order written."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        claim=str(document["claim"]),
        points=tuple(
            ArgumentPoint(
                id=str(point["id"]),
                text=str(point["text"]),
                on=str(point["on"]),
                stance=str(point["stance"]),
                with_=tuple(str(other) for other in point.get("with", ())),
                role=str(point.get("role", "step")),
            )
            for point in document["points"]
        ),
    )


def _mindmap_branch(entry: Mapping[str, Any]) -> MindmapBranch:
    return MindmapBranch(
        text=str(entry["text"]),
        role=str(entry.get("role", "step")),
        branches=tuple(_mindmap_branch(child) for child in entry.get("branches", ())),
    )


def _mindmap_document(document: Mapping[str, Any]) -> Document:
    """A mind map: its centre and its nested branches, in the order written."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        centre=str(document["centre"]),
        branches=tuple(_mindmap_branch(entry) for entry in document["branches"]),
    )


def _packet_document(document: Mapping[str, Any]) -> Document:
    """A packet: its row width, its numbering and its fields, in reading order."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        packet_row_bits=int(document.get("bits_per_row", PACKET_ROW_DEFAULT)),
        packet_numbering=str(document.get("numbering", "left")),
        packet_fields=tuple(
            PacketField(
                bits=int(entry["bits"]),
                text=str(entry.get("text", "")),
                short=str(entry.get("short", "")),
                holds=str(entry.get("holds", "")),
                note=str(entry.get("note", "")),
                role=str(entry.get("role", "field")),
            )
            for entry in document["fields"]
        ),
    )


def _exact(value: object) -> Fraction:
    """A validated number as an exact fraction: `0.1` is a tenth, not its float."""
    if isinstance(value, float):
        return Fraction(repr(value))
    return Fraction(int(value))  # type: ignore[call-overload]


def _pert_activity(entry: Mapping[str, Any]) -> PertActivity:
    """One activity, its duration exact: as written, or (o + 4m + p) / 6."""
    estimates: tuple[Fraction, Fraction, Fraction] | None = None
    if "duration" in entry:
        duration = _exact(entry["duration"])
    else:
        low, likely, high = (_exact(entry[name]) for name in PERT_ESTIMATES)
        estimates = (low, likely, high)
        duration = (low + 4 * likely + high) / 6
    return PertActivity(
        id=str(entry["id"]),
        text=str(entry["text"]),
        duration=duration,
        after=tuple(str(name) for name in entry.get("after", ())),
        estimates=estimates,
    )


def _pert_document(document: Mapping[str, Any]) -> Document:
    """A project network: its activities in the order written, and its milestones."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        unit=str(document.get("unit", "")),
        pert_activities=tuple(_pert_activity(entry) for entry in document["activities"]),
        pert_start=str(document.get("start", "")),
        pert_finish=str(document.get("finish", "")),
    )


def _sunburst_node(entry: Mapping[str, Any]) -> SunburstNode:
    """One sunburst node and its subtree, built from the validated mapping."""
    return SunburstNode(
        text=str(entry["text"]),
        children=tuple(_sunburst_node(child) for child in entry.get("children", ())),
    )


def _sunburst_document(document: Mapping[str, Any]) -> Document:
    """A sunburst: its optional hub and its nested rings, in the order written."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        centre=str(document.get("centre", "")),
        sunburst_nodes=tuple(_sunburst_node(entry) for entry in document["nodes"]),
    )


def _network_document(document: Mapping[str, Any]) -> Document:
    """A network diagram: its buses, its hosts and its groups, in the order written."""
    order = {entry["id"]: index for index, entry in enumerate(document["networks"])}

    def host(entry: Mapping[str, Any]) -> NetworkHost:
        attached = sorted(entry["networks"], key=lambda item: order[item["network"]])
        return NetworkHost(
            id=str(entry["id"]),
            text=str(entry.get("text", entry["id"])),
            role=str(entry.get("role", "step")),
            networks=tuple(str(item["network"]) for item in attached),
            addresses=tuple(str(item.get("address", "")) for item in attached),
        )

    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        networks=tuple(
            NetworkSegment(
                id=str(entry["id"]),
                text=str(entry.get("text", entry["id"])),
                address=str(entry.get("address", "")),
            )
            for entry in document["networks"]
        ),
        hosts=tuple(host(entry) for entry in document["hosts"]),
        host_groups=tuple(
            NetworkGroup(
                text=str(entry.get("text", "")),
                members=tuple(str(member) for member in entry["members"]),
            )
            for entry in document.get("groups", ())
        ),
    )


def _gitgraph_document(document: Mapping[str, Any]) -> Document:
    """A git graph: its branches and its steps, in the order written."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        git_branches=tuple(
            GitBranch(
                name=str(entry["name"]),
                source=str(entry.get("from", "")),
                role=str(entry.get("role", "step")),
            )
            for entry in document["branches"]
        ),
        git_steps=tuple(
            GitStep(
                on=str(entry["on"]),
                text=str(entry.get("text", "")),
                id=str(entry.get("id", "")),
                merge=str(entry.get("merge", "")),
                pick=str(entry.get("pick", "")),
                tag=str(entry.get("tag", "")),
                role=str(entry.get("role", "step")),
            )
            for entry in document["steps"]
        ),
        git_direction=str(document.get("direction", "right")),
    )


def _timing_document(document: Mapping[str, Any]) -> Document:
    """A timing figure: its lanes, step names, markers and intervals, as written."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        timing_signals=tuple(
            TimingSignal(
                text=str(signal["text"]),
                lane=str(signal.get("lane", "bit")),
                values=tuple(str(value) for value in signal["values"]),
                states=tuple(str(state) for state in signal.get("states", ())),
                group=str(signal.get("group", "")),
            )
            for signal in document["signals"]
        ),
        timing_ticks=tuple(str(tick) for tick in document.get("ticks", ())),
        timing_markers=tuple(
            TimingMarker(at=float(marker["at"]), text=str(marker.get("text", "")))
            for marker in document.get("markers", ())
        ),
        timing_intervals=tuple(
            TimingInterval(
                start=float(interval["from"]),
                end=float(interval["to"]),
                text=str(interval["text"]),
                signal=str(interval.get("signal", "")),
            )
            for interval in document.get("intervals", ())
        ),
    )


def _railroad_item(entry: Mapping[str, Any], pointer: str) -> RailroadItem:
    """One railroad item and everything inside it, built from the validated mapping."""
    shape = next(shape for shape in RAILROAD_SHAPES if shape in entry)
    if shape in RAILROAD_BOXES:
        return RailroadItem(shape=shape, text=str(entry[shape]), pointer=pointer)
    if shape in ("seq", "choice"):
        return RailroadItem(
            shape=shape,
            items=tuple(
                _railroad_item(child, f"{pointer}/{shape}/{index}")
                for index, child in enumerate(entry[shape])
            ),
            pointer=pointer,
        )
    separator = entry.get("separator")
    return RailroadItem(
        shape=shape,
        items=(_railroad_item(entry[shape], f"{pointer}/{shape}"),),
        separator=_railroad_item(separator, f"{pointer}/separator") if separator else None,
        min=int(entry.get("min", 1)),
        pointer=pointer,
    )


def _railroad_document(document: Mapping[str, Any]) -> Document:
    """A railroad grammar: its rules in the order written, and the names it borrows."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        railroad_rules=tuple(
            RailroadRule(
                name=str(rule["name"]),
                expr=_railroad_item(rule["expr"], f"/rules/{index}/expr"),
                pointer=f"/rules/{index}",
            )
            for index, rule in enumerate(document["rules"])
        ),
        railroad_external=tuple(str(name) for name in document.get("external", ())),
    )


def _wardley_document(document: Mapping[str, Any]) -> Document:
    """A Wardley map: its anchors, components and notes, in the order written."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        wardley_anchors=tuple(
            WardleyAnchor(
                id=str(entry["id"]),
                text=str(entry["text"]),
                needs=tuple(str(need) for need in entry["needs"]),
            )
            for entry in document["anchors"]
        ),
        wardley_components=tuple(
            WardleyComponent(
                id=str(entry["id"]),
                text=str(entry["text"]),
                evolution=str(entry["evolution"]),
                needs=tuple(str(need) for need in entry.get("needs", ())),
                depth=int(entry["depth"]) if "depth" in entry else None,
                evolves=str(entry.get("evolves", "")),
                inertia=bool(entry.get("inertia", False)),
            )
            for entry in document["components"]
        ),
        wardley_notes=tuple(
            WardleyNote(text=str(entry["text"]), on=tuple(str(target) for target in entry["on"]))
            for entry in document.get("notes", ())
        ),
    )


def _pie_document(document: Mapping[str, Any]) -> Document:
    """A pie: its parts in the order written, and the unit they are in."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        values=bool(document.get("values", True)),
        theme=str(document.get("theme", "")),
        unit=str(document.get("unit", "")),
        pie_parts=tuple(
            PiePart(
                text=part["text"],
                amount=float(part["amount"]),
                role=part.get("role", "step"),
            )
            for part in document["parts"]
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
            amount=None if entry.get("amount") is None else float(entry["amount"]),
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
        ends=tuple(str(name) for name in entry.get("ends", ())),
    )


def _usecase_document(document: Mapping[str, Any]) -> Document:
    """A use case diagram: its systems, actors, use cases and relations as written."""
    systems = tuple(
        UsecaseSystem(id=entry["id"], text=entry["text"]) for entry in document.get("systems", ())
    )
    only = systems[0].id if len(systems) == 1 else ""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        usecase_systems=systems,
        usecase_actors=tuple(
            UsecaseActor(id=entry["id"], text=entry["text"], supporting=entry.get("supporting"))
            for entry in document["actors"]
        ),
        usecase_cases=tuple(
            UseCase(id=entry["id"], text=entry["text"], system=entry.get("system", only))
            for entry in document["usecases"]
        ),
        usecase_edges=tuple(
            UsecaseEdge(
                source=entry["from"], target=entry["to"], role=entry.get("role", "association")
            )
            for entry in document["edges"]
        ),
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
    document = parse_document(parsed)
    return replace(document, theme=_beside(document.theme, location))


def _beside(theme: str, location: Path) -> str:
    """A relative theme path, read from the document's folder when the file is there.

    A theme beside its diagrams is the natural layout — a derived brand theme
    next to the documents that use it — and a path that only worked from one
    working directory is a document that renders in one build and not another.
    A bundled name, an absolute path, or a file that is not beside the document
    is left as written, so nothing that resolved before resolves differently.
    """
    if not theme or not theme.endswith(".toml") or Path(theme).is_absolute():
        return theme
    beside = location.parent / theme
    return str(beside) if beside.is_file() else theme


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
    "ARGUMENT_DEPTH_MAX",
    "ARGUMENT_GROUP_MAX",
    "ARGUMENT_KINDS",
    "ARGUMENT_POINT_MAX",
    "ARGUMENT_ROLES",
    "ARGUMENT_STANCES",
    "AXIS_ORDER",
    "BARMODEL_BAR_MAX",
    "BARMODEL_BRACE_MAX",
    "BARMODEL_KINDS",
    "BARMODEL_PART_MAX",
    "BARMODEL_PART_ROLES",
    "BARMODEL_UNIT_MAX",
    "BOARD_CELL_MAX",
    "BOARD_KINDS",
    "CARDINALITIES",
    "CAUSE_ROLES",
    "CHART_KINDS",
    "CLASSES_MAX",
    "CLOCK_KINDS",
    "CLOCK_MAX",
    "CLOCK_NUMERALS",
    "CLOCK_READOUTS",
    "CLOCK_SINCE_MAX",
    "COMMON_FIELDS",
    "CONTAINER_KINDS",
    "DOCUMENT_VERSION",
    "ENTITIES_KINDS",
    "ENTITY_EDGE_ROLES",
    "ENTITY_ROLES",
    "FAMILYTREE_GENDERS",
    "FAMILYTREE_GENERATION_MAX",
    "FAMILYTREE_KINDS",
    "FAMILYTREE_PARTNER_MAX",
    "FAMILYTREE_PEOPLE_MAX",
    "FAMILYTREE_PREGNANCIES",
    "FAMILYTREE_ROLES",
    "FAMILYTREE_SEXES",
    "FAMILYTREE_STATUSES",
    "FAMILYTREE_TWIN_MAX",
    "FAMILYTREE_ZYGOSITIES",
    "FIELD_KEYS",
    "FISHBONE_CATEGORY_MAX",
    "FISHBONE_CAUSE_MAX",
    "FISHBONE_KINDS",
    "FRAGMENT_OPERATORS",
    "GITGRAPH_BRANCH_MAX",
    "GITGRAPH_DIRECTIONS",
    "GITGRAPH_KINDS",
    "GITGRAPH_ROLES",
    "GITGRAPH_STEP_MAX",
    "GRAPH_EDGE_ROLES",
    "GRAPH_KINDS",
    "GRID_KINDS",
    "HIERARCHY_ROLES",
    "HUB_EDGE_ROLES",
    "HUB_MINIMUM_NODES",
    "JOURNEY_KINDS",
    "JOURNEY_STAGE_ROLES",
    "KINDS",
    "LANES_KINDS",
    "LANES_MAX",
    "LOOP_MAX",
    "LOOP_TYPES",
    "MESSAGE_ROLES",
    "METER_BAND_MAX",
    "METER_BAND_MIN",
    "METER_BAND_STYLES",
    "METER_CURRENCIES",
    "METER_KINDS",
    "METER_MAX",
    "METER_MIN_STYLES",
    "METER_ROLES",
    "METER_STYLES",
    "MINDMAP_BRANCH_MAX",
    "MINDMAP_DEPTH_MAX",
    "MINDMAP_KINDS",
    "MINDMAP_NODE_MAX",
    "MINDMAP_ROLES",
    "NETWORK_GROUP_MAX",
    "NETWORK_HOST_MAX",
    "NETWORK_HOST_ROLES",
    "NETWORK_KINDS",
    "NETWORK_MAX",
    "NUMBERLINE_KINDS",
    "NUMBERLINE_POINT_MAX",
    "NUMBERLINE_RANGE_MAX",
    "NUMBERLINE_ROLES",
    "NUMBERLINE_TICK_MAX",
    "OBJECTS",
    "PACKET_FIELD_MAX",
    "PACKET_KINDS",
    "PACKET_NUMBERINGS",
    "PACKET_ROLES",
    "PACKET_ROW_BITS",
    "PACKET_ROW_DEFAULT",
    "PACKET_ROW_MAX",
    "PARTICIPANT_ROLES",
    "PERT_ACTIVITY_MAX",
    "PERT_DEPENDENCY_MAX",
    "PERT_ESTIMATES",
    "PERT_KINDS",
    "PIE_KINDS",
    "PIE_PART_MAX",
    "PIE_PERCENT_TOLERANCE",
    "PIE_ROLES",
    "PIE_SHARE_MIN",
    "PLAIN_NODE_ROLES",
    "POLARITIES",
    "POLARITY_EDGE_ROLES",
    "RAG_KINDS",
    "RAG_ROW_MAX",
    "RAG_TRENDS",
    "RAG_VALUES",
    "RAILROAD_BOXES",
    "RAILROAD_BOX_MAX",
    "RAILROAD_BRANCH_MAX",
    "RAILROAD_COMBINERS",
    "RAILROAD_DEPTH_MAX",
    "RAILROAD_KINDS",
    "RAILROAD_RULE_MAX",
    "RAILROAD_SHAPES",
    "REGION_ROLES",
    "REJECTED_FIELDS",
    "SANKEY_BAND",
    "SANKEY_FLOW_ROLES",
    "SANKEY_KINDS",
    "SANKEY_MIN_BAND",
    "SANKEY_NODE_ROLES",
    "SCHEMA_FILENAME",
    "SCHEMA_ID",
    "SEQUENCE_KINDS",
    "SHAPED_ROLES",
    "SHAPE_KINDS",
    "STATES_KINDS",
    "STATE_ROLES",
    "SUNBURST_DEPTH_MAX",
    "SUNBURST_KINDS",
    "SUNBURST_NODE_MAX",
    "SUNBURST_RING_MAX",
    "TIMING_BIT_VALUES",
    "TIMING_BUS_RESERVED",
    "TIMING_HOLD",
    "TIMING_INTERVAL_MAX",
    "TIMING_KINDS",
    "TIMING_LANES",
    "TIMING_MARKER_MAX",
    "TIMING_SIGNAL_MAX",
    "TIMING_STATE_MAX",
    "TIMING_STEP_MAX",
    "TRANSITION_ROLES",
    "TREEMAP_KINDS",
    "TREEMAP_PART_ROLES",
    "USECASE_ACTOR_MAX",
    "USECASE_CASE_MAX",
    "USECASE_COLUMN_MAX",
    "USECASE_DRAWN_ROLES",
    "USECASE_EDGE_MAX",
    "USECASE_EDGE_ROLES",
    "USECASE_KINDS",
    "USECASE_SYSTEM_MAX",
    "VENN_FOUR_TEXT_MAX",
    "VENN_KINDS",
    "VENN_SET_MAX",
    "VENN_SET_ROLES",
    "WARDLEY_ANCHOR_MAX",
    "WARDLEY_COMPONENT_MAX",
    "WARDLEY_DEPTH_MAX",
    "WARDLEY_EVOLUTION",
    "WARDLEY_KINDS",
    "WARDLEY_NOTE_MAX",
    "WARDLEY_STAGES",
    "WATERFALL_BAR_MAX",
    "WATERFALL_KINDS",
    "WATERFALL_ROLES",
    "ArgumentPoint",
    "Axis",
    "Band",
    "BoardColumn",
    "Branch",
    "Card",
    "Category",
    "CausalLoop",
    "Cause",
    "Cell",
    "ClockFace",
    "Curve",
    "Detail",
    "Document",
    "Edge",
    "Entity",
    "EntityField",
    "FamilyCouple",
    "FamilyPerson",
    "FamilyTwins",
    "FieldSpec",
    "Fragment",
    "GitBranch",
    "GitStep",
    "Group",
    "Item",
    "JourneyStage",
    "Message",
    "Meter",
    "MeterBand",
    "MindmapBranch",
    "ModelBar",
    "ModelBrace",
    "ModelPart",
    "NetworkGroup",
    "NetworkHost",
    "NetworkSegment",
    "Node",
    "NodeClass",
    "NumberAxis",
    "NumberPoint",
    "NumberRange",
    "PacketField",
    "PertActivity",
    "Phase",
    "PiePart",
    "Position",
    "RagRow",
    "RailroadItem",
    "RailroadRule",
    "Region",
    "Relation",
    "SankeyFlow",
    "SankeyNode",
    "Series",
    "Slice",
    "SunburstNode",
    "TimingInterval",
    "TimingMarker",
    "TimingSignal",
    "TreemapGroup",
    "TreemapPart",
    "UseCase",
    "UsecaseActor",
    "UsecaseEdge",
    "UsecaseSystem",
    "VennSet",
    "Violation",
    "WaterfallBar",
    "Waypoint",
    "build_schema",
    "clock_minutes",
    "fields_for",
    "lane_order",
    "load_document",
    "parse_document",
    "payload_for",
    "published_schema_path",
    "sankey_amount",
    "sankey_columns",
    "schema_json",
    "transition_label",
    "validate_document",
]

# Changelog

All notable changes to drawspec are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The **document format** is versioned separately and independently: a document
declares `"version": 1`, and that number changes only when a document written
against it would stop working. Everything below is about the *package*.

## [Unreleased]

### Added

- **A `wardley` kind.** A Wardley map: what a user needs at the top, what that rests on
  below, each part placed across by how evolved it is — genesis, custom-built, product,
  commodity. No position is a coordinate: `evolution` is a stage by name, optionally
  `early` or `late` in it (twelve named places), and the row is derived from `needs`, one
  below the lowest thing that needs it (`depth` sinks a part further, never above what
  needs it). Straight dependency lines; `evolves` draws a dashed arrow to a dashed circle
  further right; `inertia` a heavy bar on the right; up to 6 numbered `notes` marked
  beside what they are about and written out under the map. Names are placed clear of
  every dot, line and other name by a small search, a dot in a line's way slides along its
  place, a crowded map is drawn taller, and a name with nowhere to go is refused. A
  component nothing needs, a loop, an `evolves` that is not further right, and a numeric
  `evolution` are refused at their pointers. The axis words are a `[wardley]` theme
  section. No text form. Three references — Wardley's tea shop, an online photo service,
  a council's build, buy or share — and `make docs`, `make schema` and the gallery pick it
  up.
- **A `sunburst` kind.** A hierarchy drawn as concentric rings of sectors, each label read
  from the middle outward: a wheel of emotions, a taxonomy. The input is just a tree of
  `{text, children?}` with an optional `centre` hub — every terminal node takes an equal
  slice and a parent spans its own, so there are no amounts. A terminal node reaches the
  rim, so an uneven tree is a full disc; each ring takes one size and its band is sized to
  the type it carries, so the words sit near their borders; labels are centred and never
  upside down; the hub label fills its disc. The structure is drawn in three weights — bold
  first-ring dividers and rim, medium ring boundaries, thin deep divisions — tunable in a
  `[sunburst]` theme section and scaling with the wheel. Up to three rings and 150 sectors,
  with the full Willcox/Junto feelings wheel as a reference. `make docs`, `make schema` and
  the gallery pick it up.

### Fixed

- **An edge no longer runs along a frame's border.** A frame is padded by about one lane, so
  the lane outside its outermost box could be the frame's own border, and a route on it was
  drawn on top of the dashed line — it read as entering the frame lengthways
  (`flow-loops-town`, `states-brand-station`). Such a run now moves a lane outward, and its
  neighbours cross the border square on. `tools/frames.py` reports any run left along a border.

## [0.4.3] — 2026-10-20

### Changed

- **The README renders on PyPI.** Every image and link in it is now an absolute
  `raw.githubusercontent.com` / `github.com` URL, because PyPI shows the long description
  without the repository beside it and relative paths broke there; the new README, merged
  after 0.4.2, reaches PyPI with this release.

- **A shorter README that leads with what drawspec does.** The long status list and the
  corpus figures are gone; a flow and a sequence are shown spec-beside-drawing, with a
  grid of nine more kinds and a section on use from an LLM. The drawings are PNGs, one
  per GitHub theme (`make readme`, `tools/readme.py`), so they show on the dark theme,
  and the text example is ASCII, whose columns line up in any font.

## [0.4.2] — 2026-10-19

### Fixed

- **A `matrix` return edge reaches its cells, and its label is not crossed** (issue #132,
  still showing in 0.4.0). An edge between cells in neighbouring rows that share no
  column, such as the return from the last output to the first process, ran level along
  the join between the rows, at a height neither cell occupies, so the arrow touched
  neither; and its label lay across the links from each process to its output, which
  were broken short of the outputs to let it through. Such an edge now leaves its source
  across the join, runs along it and enters its target, a quarter in from the side it
  comes from; its label is wrapped onto the widest stretch of the join that no other
  edge crosses, and the join is made deep enough for it and for the head. The label is
  centred in the gap between the cells and its run, rather than hung off the run.
- **A `matrix` with edges centres each cell's words in the cell it draws.** Such a
  matrix draws every cell an edge clearance in from its slot, but sized the cell's box
  for the whole slot, so the box was taller and wider than the cell: a two-line cell's
  words sat a clearance low, all but touching its bottom, and a line as wide as the slot
  ran past the cell's sides. Boxes are now sized for the cell, and rows are deep enough
  for the box and the clearance either side. Matrices with edges come out a little
  taller; tables without edges are unchanged.
- **An edge to or from a `group` no longer undoes the packing of its members.** Groups
  that an edge ranks side by side were each still packed as if alone on the sheet, so a
  control plane with an arrow to each of two worker nodes needed 1072 on a 640 canvas, in
  both directions, and was refused. A level too wide for its canvas now packs the groups
  in its too-wide rows narrower until it fits; a group alone in its row keeps its rows,
  and members keep the order they were written in.

## [0.4.1] — 2026-10-19

### Fixed

- **`gantt` iteration arrows are circular arcs** that bend evenly and stop just above the
  bar, steep enough for the head to point down at it. 0.4.0 drew a flattened curve with
  upright stubs at each end, which kinked where they met and left the head lying on the
  bar's edge, its shaft entering from one side and showing past its tip.

## [0.4.0] — 2026-10-19

### Added

- **`gantt` tasks take `events` and `iterations`**, so one row can be a lane of a
  life-cycle comparison. An event (`{at, text?}`) is a diamond on the task's own bar
  with its words under it, such as a delivery or a release; several fall on one row
  where a milestone task would take a row each. An iteration (`{start, end}`) is a
  curved arrow over the bar from the iteration's end back to its start, the loop a life cycle
  draws. Both lie within the task's `start` to `end`. Iterations are in order and may
  touch but not overlap. Neither is allowed on a milestone. Each is budgeted at 8 per
  task. Text output draws an iteration as `▼───┐` over the bar and an event as `◆` on
  it, with the words under the bar, or listed under the chart when they would touch.
  Example: `reference/gantt-life-cycles.json`, the PMBOK continuum of life cycles
  (issue #131).
- **`entities` star schemas**: `"centre": true` on one entity places it in the middle and
  the rest round it, the first above and the rest clockwise in the order written, with
  the PK/FK marks and crow's feet `entities` draws. Lines naming no field join the boxes
  square, spread along each side of the middle; a second `centre`, or one in a class
  hierarchy, is refused. Reference: `entities-star.json`. (#135)

- **One SVG, several themes** (#136): `render --variant dark=night.toml` (repeatable;
  `variants=` in Python, `variants` in MCP's `render_document`) draws the document in
  each theme and merges them into one SVG whose colours are CSS custom properties. An
  ancestor's `data-theme="name"` selects a theme, a variant named `dark` also follows
  `prefers-color-scheme`, and the base theme answers to `light`. A variant may change
  colours only; one that changes the drawing is refused by name. The root carries
  `data-drawspec-theme="light=name@digest …"`. The `<style>` this needs is admitted by
  the embedding check only when every rule is scoped to the drawing's root and sets
  only its own colour properties. Single-theme output is unchanged.

### Fixed

- **A `cycle` edge's `label` is drawn** (#134). It was accepted, validated and dropped.
  It now sits beside its own arc, outside the ring and clear of every step, and a label
  with no room there is refused by name. A new test walks every kind's field tables and
  fails on any free-text field that is accepted and not drawn. It keeps a short, explained
  list of exceptions, which is `note` on the kinds other than `timeline` that v1 keeps.
- **A `matrix` edge label no longer prints over cell text** (#132). A labelled edge
  running along the join between two rows opens a channel there for its words. Every
  label is tried at points along its run until one is clear of the cells' words, and is
  refused by name when none is.
- **A two-line `emphasis` point on a `numberline` is bold on both lines** (#133). It
  printed `**` raw: one bold pair spanning a newline was split into two unmatched halves.
  Every kind that sets a whole label bold now bolds each line on its own.

## [0.3.3] — 2026-10-15

### Changed

- **Tighter MCP tool descriptions**: each now says what its arguments accept, with an
  example value (the bundled theme names, `kind`, the document as a JSON object), how
  `width`, `height` and `theme` behave with `format: text`, and what a call costs (local,
  deterministic, rough answer size). Return shapes already in an output schema are no
  longer repeated, and the refusal shape is shorter.

## [0.3.2] — 2026-10-15

### Changed

- **The MCP tools are renamed to one verb_noun convention**: `validate` →
  `validate_document`, `render` → `render_document`, `kinds` → `list_kinds`. The CLI
  commands keep their names.
- **Sharper tool descriptions**: when to validate and when to render, the shape of
  every answer and of every refusal, and read-only annotations on all tools. JSON
  answers also come back as structured content matching an output schema.

### Added

- **`get_example`** and **`get_schema`** MCP tools: the smallest valid document of a
  kind (what `drawspec example` prints), and that kind's slice of the published
  schema with only the definitions it uses (a few thousand characters, not the whole
  file's two hundred thousand).

## [0.3.1] — 2026-10-15

### Added

- **The official MCP Registry** lists drawspec as `io.github.nuncaeslupus/drawspec`:
  `server.json`, the `mcp-name` line the registry looks for in the PyPI README, and a
  release job that publishes it through GitHub's OIDC once PyPI has the version.
- **`drawspec mcp`**, the same server as `drawspec-mcp`, so a launcher that only runs the
  package's own command reaches it: `uvx --from 'drawspec[mcp]' drawspec mcp`.

## [0.3.0] — 2026-10-14

### Added

- **`glama.json` and a `Dockerfile`** for MCP registries such as Glama: the image installs
  `drawspec[mcp]` from the checkout and runs `drawspec-mcp` over stdio.
- **Text width defaults by kind**: 100 columns for `lanes` and `sequence`, whose parties
  sit side by side, 80 for the rest. `--width` (CLI), `width` (MCP) and `render_text(width=)`
  still set any width the caller wants.
- **Text output for eight more kinds** (proposal `text.md`, phase 1): `render --format
  text` / `-o diagram.txt`, `render_text()` and the MCP `render` tool's `format: "text"`
  now draw `tree`, `sequence`, `gantt`, `timeline`, `board`, `stack`, `rag` and `meter`
  (the `bar` style) as well as `files`. Each kind lays itself out on a character grid from
  its layout's topology — a sequence's lifelines as columns and messages as rows, a plan's
  bars in cells on the SVG's axis — never from the SVG's coordinates. Roles are glyphs: a
  heavy box for `emphasis`, rounded for `terminal`, double for `start`, dashed for `note`;
  `━━▶`, `┄┄▷` and `──▷` for `strong`, `weak` and `async`; the `+ ~ -` status column.
- **`--width N` and `--charset unicode|ascii`** for text, and `render_text(document, *,
  width=80, charset="unicode")`. Width is in terminal cells (an East Asian wide character
  is two). A drawing wider than `width` is refused at its widest thing's pointer, naming
  the width it needs; text is wrapped only where the SVG wraps it, and only at spaces.
  `ascii` is bytes below 128 only. A `files` tree's output is unchanged, and its
  `style: "ascii"` still selects ASCII; unlike the other kinds, it is not held to
  `--width` for now, so a wide tree prints as it always did.

- **Text output for the graph kinds** (proposal `text.md`, phase 2): `flow`, `states`
  and `lanes` — and a `tree` with cross-links or groups — now have a text form. The
  layered engine ranks and orders the boxes; each edge is routed square through free
  cells, its label beside its own line, and a `┼` is drawn only where two edges really
  cross. Groups are dashed frames named on their top border, a composite state's regions
  are divided by a dashed rule, lanes are named columns (or rows) whose rules a hand-off
  crosses, and phases are named beside them. A state machine's dots are `●` and `◉`
  (`*` and `(*)` in ASCII), a fork or join a heavy bar, a self-transition a hook on the
  box's side; a causal loop diagram's loops are listed under it. A graph is tried down
  the page first, then with its words wrapped narrower, then across the page.
- **A text budget** for the graph kinds: more than 15 boxes, or lines crossing more than
  3 times in every arrangement, is refused at `/nodes` or `/edges` as noise, pointing at
  SVG. `bands` have no text form yet and refuse at `/bands`.

- **Text output for a `thermometer` meter**: a tube down the page filled up from its
  bulb, the SVG's ticks at its left, the target a heavy stroke across it, the readout and
  name under the bulb; several side by side.
- **Text output for a `dial` and a `bullet` meter**, so every `meter` style has one. A
  dial is a half-circle of cells five rows deep from `min` to `max`, its bands in shades
  lightest first (`░ ▒ ▓`, ASCII `. : #`) or, with none, filled `█` to the amount; a
  needle from the hub `●` in the stroke nearest its angle (`─ ╱ │ ╲`), the target `◆` on
  the arc, the scale's ends under its feet, then a key of its bands, the readout and the
  name; up to three to a row, as the SVG sets them. A bullet is a bar's row three cells
  deep: its bands in shades with their words over them, the measure a thin heavy bar `━`
  (`=`) along the middle to the amount, the target `│` (`!`) down all three, and the
  SVG's ticks from zero under it. A band too short for its word is refused at the
  meter's pointer, naming the width that gives it room.
- **`gantt` dependencies in text**: each is a line from the end of its bar, down through
  blank cells and right into the start of the dependent bar (or straight down onto it),
  in its role's line style. One with no clean route is listed under the chart,
  `B after A`, instead of being dropped.
- **A `timeline` in text is spaced by `at`** when every entry has one: gaps in proportion,
  the closest pair one blank row apart, a gap past eight blank rows shortened and dashed.

### Changed

- The refusal for a kind with no text form names the kinds that have one, instead of
  saying only `files` does. A tree with bands refuses at its pointer; a tree with
  cross-links or groups is drawn as a graph.
- **The bundled fonts cover Box Drawing and Block Elements** (U+2500–259F), the glyphs
  text output draws with, so a label that uses one measures and rasterises as itself
  rather than as `.notdef`. Every other glyph, and every advance, is unchanged.
- **The README banner shows text output**: a small reference sequence,
  `sequence-terminal`, as `--format text` and `--charset ascii` draw it, set in the
  embedded monospace face beside the SVG plates; its title block's output reads
  `SVG · PNG · TEXT`. The README shows the same two drawings beside the paragraph on text.

## [0.2.1] — 2026-10-13

### Changed

- **A `stack` takes up to 10 `items`** (was 8). A real document refused by 0.2.0
  is a nine-item legal enumeration (the principles of preventive action, LPRL
  art. 15) that splitting would misstate; 10 matches `timeline`.

## [0.2.0] — 2026-10-12

### Added

- **Fork and join bars in `states`**: a state with `"role": "fork"` or `"join"` and no
  `text` is UML's bar pseudo-state, drawn as a short thick bar across the flow (upright
  when the machine reads across), `[states] bar_step` long per arrow and stretched to
  reach over the states it splits into or gathers, so each arrow drops straight onto its
  state. A region every fork reaches may omit its `initial`. Refused at their pointers:
  `text` on a bar; a fork without exactly one way in and two or more out (a join the
  reverse); arrows into two states of one region or into no region; an `event` or
  `guard` out of a fork or into a join, or an `event` out of a join; a bar as `initial`,
  `final` or a region's `initial`; a loop on a bar; a region with no `initial` the
  machine can enter without a fork; more than 4 bars (budget `states=fork|join`). A
  machine laid out across stacks its regions against its upright bars. New theme keys
  `[states] bar` and `bar_step`. See `reference/states-fork-order.json`,
  `states-fork-release.json` and `states-fork-onboarding.json`; no existing drawing
  changes.

- **`sequence` async messages and actors**: message role `async`, UML's asynchronous
  message — a solid line with an open head (new theme edge role `async`) — which opens
  no activation bar; a `weak` reply answering one is refused. Participant role `actor`
  draws a person as the UML stick figure over the name, every head's name on one line
  and the lifeline under it. `person`/`user` on a participant and `asynchronous`,
  `signal`, `reply` and the like on a message are refused with the right role named.
  See `reference/sequence-actor-signin.json`, `sequence-async-export.json` and
  `sequence-actor-handover.json`; no existing drawing changes.

- **Orthogonal regions in `states`**: a composite takes `regions` (2–4, each
  `{members, initial}`) in place of `members`, drawn side by side or stacked and divided
  by dashed lines in the frame's role, each region with its own initial dot. Entering the
  composite enters every region; entering one state inside a region starts the others.
  Refused at their pointers: a state in two regions, a region without an `initial` (or
  with one outside it), `members` beside `regions`, an `initial` on the composite, a
  single region, more than 4 (budget `groups/regions`), and a transition between two
  regions of one composite. No arrow to or from the composite lands on a divider. Fork
  and join bars are not drawn. See `reference/states-regions-order.json`,
  `states-regions-player.json` and `states-regions-keyboard.json`.

- **`person` node role**, on `flow`, `tree` and `lanes` nodes: the C4 person, a body
  with rounded shoulders under a round head, drawn as one outline (new theme shape
  `person`), the name written in the body. Arrows land on the visible outline: on the
  head from above, on the shoulders beside it, on the body or head from the side. A
  `cycle` refuses it (use `actor`). See `reference/flow-person-helpdesk.json`,
  `tree-person-escalation.json` and `flow-classes-context.json`; `flow-node-roles`
  draws all eleven roles.

- **Node classes with a key**, on `flow`, `tree` and `lanes`: a node's `class` names
  one of 1–4 top-level `classes` (`{id, text}`); each class is drawn as the next fill
  of the theme's new `[classes] fills` sequence (a grey wash at `[classes] tone`, then
  dots, hatch, grid — ink only), and a key under the drawing names each. Refused at
  their pointers: an undeclared class (closest named), an unused class, more than 4
  (budget), a duplicate id, a class on a `note` or `group`, a class with `status` on
  the same box, and classes on a `cycle`. See `reference/flow-classes-context.json`
  (a C4-style context, external systems greyed), `flow-classes-teams.json`,
  `tree-classes-board.json` and `lanes-classes-claim.json`. One class alone is
  allowed, so a C4 context can grey only its external systems and keep the key.

- **Graded levels**, theme only: a `pyramid`'s levels, a `funnel`'s stages, `rings`
  and a `stack`'s layers are filled from `[mark] ramp`, lightest first in the order
  written, one ramp step per level (spread across the ramp past five). The page's ink
  at part opacity, so dark mode and greyscale keep it, and the ramp's ceiling keeps
  text legible. On by default; the new key `[levels] shade = false` turns it off. A
  `note` level stays unfilled. `[frames] tone` and `[lanes] stripe` now also take
  `false` for off, and the guide lists all three greys and how to turn each off.
  Changes every pyramid, funnel, rings and stack drawing in the gallery.

- **`lanes` take `phases`**, the second axis of a cross-functional flowchart:
  `[{text, members}]` in the order the process runs, every step in exactly one.
  Drawn as a band of phase names along the lanes' outer edge (over the strips in
  rows, beside them in columns) and a light line across every lane between phases,
  in the new theme key `[lanes] phase` (edge role, `aside` by default). Each phase's
  steps are ranked after all of the phases before it, so phases never interleave;
  an arrow back into an earlier phase is drawn as a return. Refused at their
  pointers: an unknown step, a step in two phases or in none, fewer than 2 or more
  than 6 phases (budget), and a backward arrow that is not a loop (phases out of
  order). See `reference/lanes-phases-purchase.json`, `lanes-phases-release.json`
  and `lanes-phases-loan.json`.
- **Washed frames and striped lanes**, theme only. A group's frame, a composite
  state and a sequence group are filled with `[frames] tone` of the page's ink (0.05
  in the default theme), drawn as `currentColor` at part opacity so dark mode and
  greyscale keep it; nested frames lay wash over wash, one step darker per level for
  `[frames] levels` (3) levels. `[lanes] stripe` (0.04) washes every second lane.
  Both cap at 0.1; 0 turns them off. This changes every grouped drawing and every
  swimlane in the gallery.
- **Three flowchart symbols as node roles**, on `flow`, `tree` and `lanes` nodes:
  `io` (a parallelogram: data in or out), `subroutine` (a box with doubled vertical
  sides: a process defined elsewhere) and `store` (a drum: a database, a queue, a file
  kept). New theme shapes `parallelogram`, `subroutine` and `cylinder`; text is fitted
  inside the slanted sides, the inner lines and under the lid, and arrows land on the
  visible outline. A `cycle` refuses them at the node's `role`; every kind with its own
  role vocabulary still does. See `reference/flow-meter-readings.json` and
  `reference/lanes-appointment.json`.
- **`gantt` tasks take `done`**, a number from 0 to 100: how much of the task is
  complete, drawn as a solid band through the middle of the bar from its start (MS
  Project's progress line). It is the page's ink at the strength of the new theme key
  `[gantt] done` (default 0.7), so it holds in greyscale and on a dark page. Refused at
  its pointer: a value outside 0–100, and `done` on a milestone. `progress`, `complete`
  and `percent` are still refused by name, now pointing to `done`. See
  `reference/gantt-progress.json`.
- **`funnel` stages can carry an `amount`**, with a top-level `unit` and `values`: each
  stage writes its count under its name and, from the second on, the share kept from
  the stage before (`310 people · 7.4% kept`), derived rather than written. The taper
  stays the drawing's uniform one, not to scale. Refused at their pointers: some stages
  with an amount and some without, an amount above the stage before's, an amount of zero
  or less, and a `unit` with no amounts. See `reference/funnel-applications.json`.
- **`quadrant` names its quarters and the ends of its axes.** `quadrants`: exactly four
  names, top right first and then counter-clockwise (Mermaid's order), each written
  faint (the page's ink at part opacity, so dark mode keeps it) in its quarter's outer
  corner; an empty string leaves a quarter unnamed. Each axis takes `ends`, the
  `numberline` field: two words for its low and high end, written at the two ends of the
  axis between it and its caption (turned, on the vertical axis). Refused at their
  pointers: `quadrants` not four, `ends` past two, and — since a quadrant axis now has
  its own type — `categories`, which was accepted and ignored. A point landing on a
  quarter name, or a name wider than half the plot, is a fit refusal. See
  `reference/quadrant-priorities.json`.
- **`clock`, the thirty-sixth kind** — analogue clock faces showing a time, for teaching
  it: 1–12 `clocks`, up to four to a row, each a `time` (`H:MM` or `HH:MM`, 0:00 to
  23:59; leave it out for a face with no hands, to draw on), an optional `text` under it,
  and an optional `since`, an earlier time whose passing is shaded round the face (the
  minute hand's sweep up to an hour, the hour hand's beyond) and said in the readout.
  The hour hand moves on with the minutes. `numerals` (`arabic`, `roman`, `quarters`,
  `none`) and `readout` (`words`, `digits`, `both`, `none` for a worksheet) are the
  sheet's. Refused at their pointers: seconds, `am`/`pm` (the 24-hour clock instead), a
  date, any other spelling of a time, a `since` with no time or 12 hours or more before
  it, `seconds`, `hands`, `hour`, `minute`, `angle`, `label`, `numerals` or `readout` on
  a face, `edges`. Budget: 12 faces. `docs/proposals/clock.md` records the design, and
  section 12 of `docs/research/corpus-round2.md` the originals.
- **`rag`, the thirty-fifth kind** — a RAG status report: 1–15 `rows`, each a `text` (a
  newline adds a caption: an owner), a `rag` of `red`, `amber` or `green`, and optionally
  a `trend` (`better`, `same`, `worse`) and a `note`, ruled apart with every column lined
  up. A rating is never told by colour alone: the new theme table `[rag]` gives each a
  word and a shape (square, triangle, circle by default; the loader refuses repeats) and,
  optionally, a colour, which `accent` sets. A trend is an arrow with its word beside it,
  because an arrow up means *improving* in one report and *risk rising* in another. The
  field is `rag` because `status` already marks a change on `flow` and `tree`. Refused at
  their pointers: any other rating (`amber/green`, `blue`), a trend of `up`/`down`,
  `status`, `colour`, `score`, `likelihood`, `impact`, `owner`, `commentary`, `columns`,
  `edges`. Budget: 15 rows. `docs/proposals/rag.md` records the design, and section 11 of
  `docs/research/corpus-round2.md` the originals.
- **`meter`, the thirty-fourth kind** — one amount against its scale, alone or up to
  six to a panel, in one `style` per document: `bar` (a progress bar; the default),
  `thermometer` (a goal filling up), `dial` (a needle on a half-circle, the only style
  that takes a `min`) or `bullet` (a thin bar on named bands with ticks from zero). Each
  meter is `text` (a newline adds a caption), `amount`, `max`, and optionally `unit`
  (`%`, a currency sign before the number, or a word after it), a `target` drawn
  across the track, and 2–5 named `bands` (`{text, to}`, rising to `max`; required on a
  bullet, optional on a dial) in ramp tones with their words on them, never colour
  alone. A readout says every number: the amount, the band it is in, the target.
  Refused at their pointers: a reading or target off the scale, `min` off a dial, bands
  on a bar (a `bullet`) or a thermometer, a bullet without them, bands that do not rise
  to `max`, `style` on a meter, `value`, `goal`, `percent`, a band's `from`. Budget: 6
  meters, 5 bands. `docs/proposals/meter.md` records the design, and section 10 of
  `docs/research/corpus-round2.md` the originals.
- **`familytree`, the thirty-third kind** — a family tree, or a pedigree in genetics
  and medicine: `people` and the `couples` they form, each couple's `children` in
  birth order. Generations are rows (I, II, III) and people are numbered left to right
  in each (II-3), all derived. The standard's symbols: `sex` picks square, circle or
  diamond (`gender`, per the 2022 revision, picks it instead, with `AMAB`/`AFAB`
  under it when they differ); `status` affected (filled) or carrier (the new theme
  key `[familytree] carrier`: `dot` or `half`), keyed under the drawing; `deceased`,
  `proband`, `consultand`, `adopted`, `pregnancy` (`ongoing`, `loss`). Couples may be
  `consanguineous` or `separated` and have `twins` (`monozygotic`, `dizygotic`,
  `unknown`). Up to 6 partners each, the later ones over the row on levels of their
  own so no lines cross; 30 people, 4 generations. Refused at their pointers: a child
  of two couples, a cycle, partners in different rows, a person in no couple, two
  unrelated families, an ancestor-only chart (a `tree`), `generation` and `number`.
  `docs/proposals/familytree.md` (was `pedigree.md`) records the design.
- **`argument`, the thirty-second kind** — an argument map: a `claim` at the top and
  up to 15 `points`, each `on` the box it bears on, `for` or `against` it (a rebuttal
  is an `against` on an `against`; no third stance), down to four levels. Stance is
  drawn twice, so greyscale holds: a tag in each box's top margin (`because`/`but`)
  and a hatch on every `against` box. Co-premises (`with`, written on any member) sit
  side by side under one bracket with one connector, so the arrows into a box count
  its separate reasons; connectors arrive square from below, each on its own port,
  crossing on their own lanes. `emphasis` is the decisive point; `note` is evidence,
  unboxed on a dashed connector. A new theme section, `[argument] for_tag`,
  `against_tag`, `against_fill`. Refused at their pointers: unknown or circular `on`,
  a missing or third stance, mismatched or unknown `with`, a group past 4, an
  objection `on` a co-premise group (with how to write it: state the linking premise
  and object to that), `edges`, duplicate or reserved ids, a fifth level, empty
  words. `docs/proposals/argument.md` records the design.
- **`mindmap`, the thirty-first kind** — one topic in the middle and its branches
  round it as peers, where a `tree` would rank them from a root. `centre` and 2 to 8
  `branches`, nested up to three levels (30 in all); the nesting is the structure, so
  there are no edges. Main branches go clockwise from the top right in the order
  written, split between the sides so they balance (the first always on the right);
  each side is a horizontal tidy tree, siblings top to bottom in the order written, the
  main branches bulging out round the centre where there is room. Main branches are
  boxed lightly, twigs and leaves sit on their line; lines are smooth tapered curves.
  `emphasis` draws the line heavy all the way from the centre; `note` is faint, with
  everything under it. When it is too wide, only the branch reaching furthest out
  wraps narrower. A new theme section, `[mindmap] boxes` and `taper`. Refused at their
  pointers: fewer than 2 or more than 8 main branches, more than 30 in all (a new
  budget form, counted at every level), a fourth level, `edges`, `links`, `id` (a
  concept map, which is a `flow`), `side`, empty words. `docs/proposals/mindmap.md`
  records the design.
- **Causal loop diagrams on `flow`** — `polarity` (`+`/`-`) on every causal edge,
  written as its label and so placed clear of everything; `delay: true`, the double
  stroke across the shaft; and named `loops`, each its variables in order. A loop's
  type is derived from the signs (an even number of `-` links reinforces) and drawn
  as `R1`, `B1`, … in a ring whose arrow turns the way the loop runs, placed inside
  the loop; a stated `type` the signs contradict is refused with the count. The
  gap between ranks grows to hold the markers; `groups` work with `loops`. A new
  theme section, `[flow] polarity = "+-" | "so"`. Refused at their pointers:
  half-signed diagrams, a sign on a `link`/`aside`/`weak` edge, a delay without a
  sign, loops without signs, a loop not joined in order (naming the missing edge),
  a node twice, the same loop twice, these fields on any other kind. Budget: 6
  loops. `docs/proposals/flow-loops.md` records the design.
- **`venn` draws four sets** — as four equal ellipses, so all fifteen regions exist
  (four circles cannot draw the two diagonal pairs). A region's words are placed
  as for circles, exactly inside their region; set names go outside, the middle
  two above their tips, the outer two under their outer lobes. With four sets a
  region's text is at most 12 characters: a count, or a word or two. A fifth set is
  refused, suggesting a `matrix`. Budget: 4 sets, 15 regions.
  `docs/proposals/venn4.md` records the design.
- **`pie`, the thirtieth kind** — the shares of one known total as sectors of a
  circle, let in with limits like `treemap`: a few known proportions stated, not
  data to explore. 2 to 8 `parts`, each a `text` and an `amount`; shares are
  computed from the amounts (never written), and with `unit: "%"` the amounts must
  add up to 100 within one point of rounding. Clockwise from twelve in the order
  written, one `note` part (`Everything else`, unfilled and dashed) last. Every
  sector labelled with its name and amount, inside it when it fits, else beside the
  circle on a leader that clears the circle; fills only keep touching sectors apart.
  A new theme section, `[pie] shape = "pie" | "donut"`: the donut is house style.
  Refused at their pointers: more than 8 parts, a part under 2%, percentages off
  100, a second `note`, one part, `value`, `percent`, `share`, `angle`, `total`,
  `groups` (naming `treemap`), `series`, `axes` (naming `chart`), `donut`, `hole`
  (naming the theme), `edges`. Budget: 8 parts. `docs/proposals/pie.md` records the
  design.
- **`waterfall`, the twenty-ninth kind** — the bridge chart of a budget paper: how
  one total became another, step by step. Its 3 to 12 `bars` are each a `total`
  (standing on zero: the first, the last, and any subtotal between) or a signed
  `amount` floating on the running sum; every total after the first is checked
  against the running sum and refused with the difference. Numbers are written on
  every bar, the steps signed with a true minus; dashed connectors follow the
  running sum; totals, rises and falls take the first three mark fills. Bridges
  below zero hang from the zero line, and ones crossing it are drawn across it.
  `axis.label` is required. Refused at their pointers: a first or last bar that is
  not a total (the last naming the sum to write), a total off the running sum, a
  total straight after a total, a bar with both sizes or neither, a step of 0,
  `value`, `subtotal`, `start`, `end`, `unit`, `series`, `axes` (naming `chart`),
  `edges`. Budget: 12 bars. Built as its own kind rather than a `chart` mark, lifting
  the deferral in `docs/proposals/README.md`; `docs/proposals/waterfall.md` records why.
- **`barmodel`, the twenty-eighth kind** — the bar model, or tape diagram, of
  primary maths: a word problem drawn as up to three `bars` of parts, before the
  sum is written. Every length is in proportion, in one scale for every bar on one
  left edge: a part is an `amount` (more than 0) or `units` (that many equal boxes),
  and the unknown keeps its size with `"text": "?"`. `braces` over side-by-side
  parts or a whole bar go above it (under it for the last of several bars), stacked
  outwards when they would touch; over several consecutive bars they stand upright
  at the right. A brace's `amount` is checked — the sum of the parts it spans, or one
  unit's worth agreed by every brace. Part roles `step`, `emphasis` (filled, bold:
  the part asked about) and `note` (dashed: the difference a shorter bar lacks).
  Refused at their pointers: a part with no size or two, amounts and units mixed, a
  brace sum or unit worth that does not hold, a brace over parts of two bars, parts
  not side by side, bars not consecutive, or a bar and a part together, a brace with
  nothing to say, unknown ids (naming the closest), duplicate ids, a single part,
  `total` (naming a brace), `value` (naming `amount`), `edges`, `axes`, `series` (naming `chart`). Budget: 3
  bars, 8 parts a bar, 12 unit boxes a bar, 6 braces. A new proposal,
  `docs/proposals/barmodel.md`, records the design and where it was built
  differently.
- **`numberline`, the twenty-seventh kind** — values and ranges on one scale:
  an inequality and its solution set, interval notation, the pH scale, a tense
  relative to *now*, options on a spectrum. The `axis` runs from `min` to `max`
  with an arrowhead at each end, ticked every `step` (or a step chosen from the
  range) with its numbers under the ticks and negative numbers in a true minus
  sign; `ends` names the two ends instead, for a scale with no numbers. `points`
  are dots on the line, hollow when `open`; their words go directly above, then
  directly under the numbers, then in rows further out with a thin leader, a slot
  taken only if the words touch no other words and the leader crosses none.
  `ranges` stack in tracks above the line in the order written, the last nearest
  it; `from_open`/`to_open` exclude an end, and a missing end runs on as an arrow.
  Roles `step`, `emphasis` (a thicker bar or a larger dot, bold words) and `note`
  (a dashed range, a smaller dot). New theme section `[numberline]`: `ends =
  "dots"` (filled in, hollow out) or `"brackets"` (`[` in, `(` out, the US and
  college convention) — house style, so one course theme switches every drawing.
  Refused at their pointers: a value off the scale, a range with no end, `to` not
  after `from`, an open end that is not there, two points at one value, `ends`
  with `step` or `unit`, more than 30 ticks, a string where a number belongs
  (naming `timeline`), `value` (naming `at`), `edges`, `series`, `axes` (naming
  `scatter`). Budget: 15 points (the pH scale with a substance at every whole
  value), 4 ranges. The guide and `AGENTS.md` say when to use it rather than
  `timeline`.
- **A drafting sheet for any diagram, and the bundled `blueprint` theme.** New
  `[canvas]` keys — `ground`, `pattern = "grid"`, `border = "zoned"`,
  `title_block`, `rule` and `accent` — draw a ground, a fine grid, a double
  border with zone numbers and letters, centring arrows, registration marks and
  an engineering title block (the document's title, a content-derived drawing
  number, its kind, the drawing's size and format version) in the `standalone`
  profile and PNG export; `inline` ignores them, as it ignores `ink`. The canvas
  grows to hold the sheet, so nothing in the drawing sits under it. A theme with
  a `ground` is refused unless its ink reads on it at 4.5:1 and every other
  declared colour at 3:1. The furniture lives in `drawspec.sheet`, which
  `tools/hero.py` now draws its banner with. Three gallery drawings use it.
- **A hero image for the README and the GitHub social preview**, drawn by
  drawspec itself: `docs/hero.svg` and a 1280x640 `docs/hero.png`, composed by
  `tools/hero.py` (`make hero`; `--check` reports a stale file). A blueprint
  sheet of reference drawings as plates, a JSON flow spec beside the drawing it
  renders, and a title block; the fonts are embedded as subset `@font-face` so
  the SVG renders the same through GitHub's `<img>`.
- **The logo** beside the README heading (so on PyPI too) and on the gallery
  page, as its header and favicon.

### Fixed

- **An edge no longer runs through a frame it has no end in.** A line between two
  boxes outside a `flow`/`tree` group, a `states` composite or one of its regions
  could take the straight way through the frame, reading as an edge that went in and
  came out. The router now treats such a frame as a box for that edge (only when the
  first route went through it, so other drawings are unchanged); an edge into a member
  crosses each border once. New `tools/frames.py` checks this over the gallery. Only
  `states-invoice` changes: *cancelled* now goes round *Issued* to *Void*.
- **A chart's numbers print at the precision written.** Bar and point labels used
  the fewest decimals that kept the chart's values apart, so `8.4` among whole
  numbers printed `8`, a value the data does not hold. Every label in the set now
  carries the most decimals any of its values was written with (`12.0`, `8.4`),
  capped at three.
- **A `chart` with `categories` on its vertical axis** was accepted and drawn wrongly:
  upright bars standing at the amounts, each as tall as its category's number. It now
  draws **horizontal bars** — each category a row, the first at the top, its name on
  the left wrapped to about a third of the width, each bar growing right from zero with
  its number past its end (inside, for a stacked segment). Each point is
  `[amount, position]`. Refused at their pointers: a series that is not `bar`, a
  position that names no category, an amount below zero, `min`/`max` on the category
  axis, and `categories` on both axes. See `reference/chart-across.json`.

## [0.1.0] — 2026-10-10

### Added

- **PNG export, behind the optional `drawspec[png]` extra** — `drawspec render
  doc.json -o doc.png` (or `--format png`; the format is inferred from a `.png`,
  `.svg` or `.txt` output name) writes the standalone drawing as a PNG, with
  `--background light|dark|transparent` (theme ink on white, `#e8e8e8` on
  `#121212`, or no page) and `--scale` (pixels per unit, default 2, at most 8).
  The renderer is `resvg-py`, one self-contained wheel with no system libraries;
  it is handed the fonts the layout was measured with and ignores the host's, so
  the PNG is byte-identical everywhere with the bundled fonts. Also
  `drawspec.render_png()` in Python and `format: "png"` on the MCP `render` tool
  (a base64 image block). Without the extra a PNG is refused (exit 1,
  `ExportError`) with the install line. No PDF or JPEG; no WebP, which would need
  a second dependency. See `docs/proposals/exports.md`.
- **`drawspec theme from`, a theme derived from a brand** — reads CSS custom
  properties (`.css`) and W3C design tokens (`.json`/`.tokens`: groups, inherited
  `$type`, `{aliases}`, colour and dimension objects), local files only, and
  writes the theme as TOML (stdout or `-o`), each key commented with its token. The
  accent colour goes on `emphasis`, `terminal` and `strong`, muted on `note`,
  `group` and `link` — the roles the `accent` theme colours — and the palette on
  `[mark] colours`; font families on `[font]`; a radius, a stroke weight (every
  weight scaled together) and a line height on `[box]`/`[edge]`, clamped; the text
  colour on `[canvas] ink` (standalone only). Every token left out is reported on
  stderr with why: backgrounds, surfaces, borders, status colours, interaction
  states, dark-mode overrides, heading faces, sizes, spacing. A colour under 3:1 on
  white or on `#121212` is darkened or lightened, hue kept, until it reads on both
  (`--strict` refuses instead); the result is loaded, so every theme invariant has
  run. A URL is a usage error. Sample brand in `docs/reference/brand/`, and three
  gallery drawings in the theme it derives.
- **A relative `theme` path in a document is read from the document's folder**
  when the file is there, so a theme can sit beside the diagrams that use it.
  Bundled names and paths that resolved before resolve the same way.
- **`sankey`, the twenty-sixth kind** — where a known quantity goes: `nodes`
  joined by `flows`, each a band whose thickness is its `amount` (in the
  document's `unit`) at one scale for the whole drawing, each bar as tall as what
  passes through it with its total under its name (`"values": false` drops them).
  For stating a few flows you already know, not for exploring data — it keeps to
  `chart`'s line. Columns are derived (one past the longest way in, every end in
  the last column); a flow that skips a column passes through it in a slot of its
  own; the order down each column starts from the written order and barycentre
  sweeps keep the one crossing fewest bands. Labels beside the outer columns'
  bars and above the inner columns', never on a band. Node roles `step`,
  `emphasis` (heavier outline, bold words), `note` (lighter, with its bands);
  flow roles `flow` and `strong` (darker). Refused at their pointers, while
  validating — a refused document never waits on a layout: a loop, a middle node
  whose inflow is not its outflow (giving the difference), a band under 1/120 of
  the fullest column, a fifth column, a self-flow, a repeated pair, an unknown
  node (naming the closest), duplicate ids, a node no flow touches, an amount of
  0 or less, `value` (naming `amount`), `percent`/`share`, `column`/`rank`, a
  flow's `label`, `edges`. Budget: 14 nodes, 24 flows, 4 columns.
- **`treemap`, the twenty-fifth kind** — the parts of one known total, each a
  rectangle whose area is in proportion to its `amount` (in the document's
  `unit`), labelled inside itself: its words top-left, its amount under them
  (`"values": false` drops the amounts). For stating a few proportions you
  already know, not for exploring data — it keeps to `chart`'s line. Parts are
  laid out largest first, written order breaking ties and `note` parts last, by
  the best of every order-keeping cut of the block across its longer side: the
  most labels fitting, then cells nearest a label's shape. The gap between cells
  is taken from the cells and the areas corrected for it, so every drawn share is
  the amount's share within a fraction of a percent. The block is three fifths of
  the width tall, a little taller if a label needs it, or the top-level
  `height`. One level of `groups`: a captioned frame in the `group` role with its
  name and total, its parts filled with the theme's mark fills in the order
  written. Part roles `step`, `emphasis` (heavier outline, bold words) and `note`
  (light dashed outline). A part too small for its words is a `FitError` naming
  it and the parts to merge into one `note` part — never a label outside its
  cell. Refused at their pointers: one part, an amount of 0 or less, `value`
  (naming `amount`), `percent`/`share`, an undeclared group (naming the
  closest), an empty group, duplicate group ids, a second level of grouping,
  `edges`. Budget: 10 parts, 4 groups.
- **`journey`, the twenty-fourth kind** — a user or citizen journey map: one
  person's feeling across 2 to 7 `stages`, each naming one of the document's
  `feelings` (2 to 5 named levels, worst first — names, never scores). The levels
  are light guides named once on the left, worst at the bottom; the feeling line
  is a monotone cubic through every stage's point, so it never overshoots and two
  neighbours at one level are joined flat. Stages are equal columns under bold
  headings. Optional `rows` (up to 4) run under the line as a table, filled by each
  stage's `details`, a list of `{row, text}` — not an object keyed by row ids; a
  row a stage does not name is an empty cell. Stage roles `step` and `emphasis`
  (the column framed, the point larger and solid). New theme section
  `[journey]`: `line` (`strong`), `guide` (`aside`), `separator` (`link`).
  Refused at their pointers: a number for a feeling, a feeling not in `feelings`
  (naming the closest), a stage with no feeling (naming `flow`), `personas`,
  `score`, `edges`, a detail in an undeclared row or twice in one stage, one
  feeling or one stage, and duplicate feelings or row ids. Budget: 7 stages,
  5 feelings, 4 rows, with "split it into two journeys" as the advice.
- **`venn`, the twenty-third kind** — two or three overlapping sets as equal
  circles (centres a radius apart: side by side, or a triangle), and `regions`
  named by membership: `in` is exactly the set ids a region is in, so no
  coordinate is ever written. The circles are as small as they can be, between a
  floor and what the width allows, while every region's words fit inside their
  region, clear of every outline; each block is placed where it has the most
  room, on as few lines as sit comfortably. A region not listed is drawn empty.
  Set names are outside the circles. Set roles `step` and `emphasis` (a heavier
  outline); region roles `step` and `emphasis` (bold words, the region filled
  with the theme's first mark fill along its exact outline). Refused at their
  pointers: one set or four or more (suggesting a `matrix`), an unknown, empty
  or repeated `in`, the same membership twice, duplicate set ids, `subset_of`
  (naming `rings`), `size`/`value`, and `edges`; words that fit no size are a
  `FitError` naming the region. Budget: 3 sets, 7 regions.
- **`fishbone`, the twenty-second kind** — a root-cause (Ishikawa) diagram: one
  `effect` in a box at the head of a spine, and 2 to 6 `categories` drawn as bones
  slanting into the spine, alternately above and below, nearest the head first.
  Each category lists 1 to 5 `causes`, ticks off its bone with the words standing
  on them, from the category's name inwards. Cause roles `step`, `emphasis` (the
  confirmed root cause: bold, its tick and bone to the spine drawn in the spine's
  role) and `note` (ruled out, a light dashed tick). Slots along the spine
  interleave: each goes as near the head as its words allow; causes wrap narrower
  until the drawing fits, or `FitError` names the longest. New theme section
  `[fishbone]`: `slant` (30 to 90 degrees, default 60 — the one diagonal drawspec
  draws on purpose), `spine`, `bone` and `cause` (edge roles, drawn with no
  head). Refused at their pointers: a third level (`causes` in a cause, "a second
  fishbone"), a category with no causes, one category, `edges`, a cause role
  with a shape, and a `role` on the effect. Budget: 6 categories, 5 causes per
  category.
- **`board`, the twenty-first kind** — cards sorted into columns, with no
  connectors: a kanban board, a retrospective, and — with `rows` and a `cut` — a
  story map. `columns` are equal and left to right as written, each with a bold
  heading over a rule; a column's `limit` makes drawspec count its cards (a
  `note` card is not counted) and write `n / limit` in the heading, which takes
  `emphasis` over the limit. `cards` stack in each cell in the order written,
  top-aligned; an `actor` is a card's lead, a `note` hangs under the card.
  `rows` are slices across every column, named in a left margin; the cut row has
  the board's one heavy line under it. Card roles `step`, `emphasis` and `note`
  (a light dashed card); column roles `step` and `emphasis`. New theme section
  `[board]`: `separator` and `cut` (edge roles). Refused at their pointers:
  `edges` (naming `flow` and `lanes`), a per-card `label`/`tag`/`colour`, a card
  in an unknown column or row, a `row` on a board without rows or missing on one
  with them, a cut without rows, unknown or on the last row, and a newline in a
  card's text when it has an actor. Budget: 6 columns, 4 rows, 32 cards, 8 cards
  per cell.
- **`gantt`, the twentieth kind** — a plan: one row per task in the order
  written, each a bar from `start` to `end` on a numbered `axis`, or a milestone
  (`at`) drawn as a filled diamond. **No dates**, by the owner's decision: the
  axis counts in a unit its `label` names, or names its periods with
  `categories` (the first period runs from 1 to 2). An `actor` is the row
  label's lead. `groups` are phases of consecutive tasks, drawn as a bold heading
  row with a bracket over the phase's span; `edges` are finish-to-start
  dependencies, drawn from the end of one bar into the start of the other and
  round the bars they can avoid; `marks` (today, a deadline) are lines across
  every row. Task roles `step`, `strong` (the critical path — not counted by the
  emphasis cap), `emphasis` and `note`; dependency roles `flow`, `strong` and
  `weak`. New theme section `[gantt]`: `milestone` (`diamond` or `circle`) and
  `marks` (an edge role). Refused at their pointers: a string date (suggesting a
  unit and `categories`), a task that is both or neither a milestone and an
  interval, an `end` not after its `start`, a value off the axis, `min`/`max`
  with categories, a dependency whose task starts before the one it waits for
  ends, a phase that is not consecutive or has no name, a task in no phase when
  there are phases, and `progress`. Budget: 16 tasks, 20 edges, 4 marks.
- **`entities`, the nineteenth kind** — ER models, database schemas and class
  diagrams as one: `entities`, each a name (with an optional `tag`, drawn
  «in guillemets»), a rule, its `fields` — a row each, with an optional `type`
  right-aligned in the code face and a `key` drawn as `PK`/`FK`/`UQ` — and its
  `operations` under a second rule; a last field of `...` stands for the rest.
  `edges` land on the box, or with `from_field`/`to_field` on one row of it, at
  the side facing the other entity — an internal port, never authored. `from_end`
  and `to_end` take a cardinality (`one`, `zero-or-one`, `many`, `zero-or-many`,
  `one-or-many`), drawn in place of the role's head. Roles `link` (default),
  `owns`, `weak`, `strong`, `inherits` and `realizes`. Placed by the layered
  engine: general above specific when there is a hierarchy (reading down), else
  the one side of each relation before its many side (reading across), with the
  other direction taken when the first does not fit. New theme section
  `[entities]`: `notation` (`crowsfoot` or `numeric`). Refused at their pointers:
  a cardinality or row on `inherits`/`realizes`, a hierarchy that loops, a field
  of another entity, a relation of an entity to itself, a `to_end` on `owns`, a
  `...` field that is not last or carries a type/key/id, a two-line name, a tag
  over 16 characters, and aggregation (with the reason). Budget: 8 entities, 12
  edges, and — new, a budget counted inside each entry — 12 fields and 8
  operations per entity.
- **Edge roles `inherits` and `realizes`, per kind.** Drawn with a new hollow
  `triangle` end treatment (the shaft stops at its base); `realizes` is dashed.
  Only `entities` accepts them: any other kind refuses them by name, saying which
  kind they belong to — edge roles are now a per-kind vocabulary in the schema.
- **`lanes`, the eighteenth kind** — swimlanes: a `flow` document whose every
  node names its `actor`, drawn with one strip per actor instead of the actor as
  each box's lead, so a hand-off is an arrow crossing a lane. Ranked as a `flow`
  is, along the lanes; a box's lane decides the other coordinate, and steps of
  one lane at the same rank stack in its strip. `lanes` (optional) orders the
  strips; omitted, they come in the order the actors first appear. Routing,
  labels, self-loops and `status` are the flow's. A cycle is broken from where
  the process starts, in the order written, so a review loop returns rather
  than starting the drawing. New theme section `[lanes]`: `orientation` (`rows`
  across the page with the names in a column at the left, `columns` down it
  with a name over each, or `auto` — rows when they fit the width, else columns)
  and `separator` (the edge role of the line between lanes, `link`). Refused at
  their pointers: a node with no `actor` (the message points back to `flow`),
  an actor not in `lanes` (naming the closest lane), a listed lane no node
  names or one listed twice, `groups`, `bands`, `centre` and the `group` node
  role. Budget: 15 nodes, 16 edges, 6 lanes (counted from the actors when
  `lanes` is omitted). References: `lanes-disclosure`, `lanes-tender`,
  `lanes-expense`, `lanes-onboarding`.
- **`sequence`, the seventeenth kind** — who says what to whom, in order:
  `participants` drawn left to right as heads over dashed lifelines, and
  `messages` top to bottom, each an arrow with its label above it. Message roles
  are `flow` (a call), `weak` (a reply: dashed, open head) and `strong`. A call
  answered later by a `weak` reply draws an **activation bar** on the receiver
  from the call's row to the reply's, nested when calls nest, and running to the
  last answer when the replies sit in the branches of an `alt`; an unanswered
  call has none. A message to itself is a hook right of its lifeline; a `note` is
  set on its message's row in one column right of the last lifeline.
  `fragments` (`loop`, `alt`, `opt`, `par`) frame the messages `from`…`to` and
  every participant they touch, with the operator in an opaque tab and the
  condition beside it; `alt` and `par` take `else` dividers. `groups` frame a run
  of neighbouring lifelines. Columns are as far apart as the labels need, and a
  drawing too wide is retried with narrower wrapping before a `FitError` naming
  the longest label. Refused at their pointers: a message naming an unknown
  participant, a participant no message names, a fragment ending before it
  starts or partly overlapping another, `else` on `loop`/`opt` or a divider
  outside, at the top of, or inside a nested frame, a group whose members are
  not neighbours or a participant in two groups, and the roles `aside`, `link`,
  `exchange`, `owns`. New theme section `[sequence]`: `activation` (the bar's
  width) and `lifeline` (the edge role it is drawn in, `aside` by default).
  Budget: 8 participants, 30 messages. References: `sequence-dns`,
  `sequence-upload`, `sequence-drain`, `sequence-checkout`.
- **`states`, the sixteenth kind** — a state machine: `states`, a required
  `initial`, optional `final`, and `transitions` whose label drawspec composes
  from `event`, `guard` and `action` (one part per line: `event`, `[guard]`,
  `/ action`). The initial state is drawn as a filled dot with an arrow to it,
  each final state with an arrow to a ringed dot (sized by the theme's new
  `[states]` section). `groups` are composite states and may nest; a transition
  from a group leaves it from any state inside, one to a group enters it at the
  group's own `initial`, drawn as a dot inside the frame. A transition from a
  state to itself is a **self-loop** on the side of its box across the reading
  direction (two at most, one per side), its label outside it, and its room
  reserved in the layout. Refused at their pointers: a state not reachable from
  `initial` (through groups), a final state with an outgoing transition, `final`
  naming a group, two transitions from one state on the same event and guard to
  different states, entering a group that has no `initial`, a loop on a group or
  a third on one state; state roles are `step`/`emphasis`/`terminal` and
  transition roles `flow`/`strong`/`weak`. Budget: 14 states, 24 transitions.
  References: `states-process`, `states-breaker`, `states-invoice`,
  `states-ticket`.
- **`status` on `flow` and `tree`** nodes and edges — `added`, `changed`,
  `removed`, the `files` vocabulary — so a proposed change is one drawing of the
  target state rather than a before and an after. A marked box carries a
  `+ added` / `~ changed` / `− removed` tag inside it; a removed box is dashed
  and its text struck through (`text-decoration`, so no stroke crosses the
  words). A marked edge writes its mark before its label; a removed edge is
  drawn dashed and headless. A key of the statuses used goes under the drawing
  when an edge is marked. An edge touching a removed node must be `removed`,
  one touching an added node `added`; `status` on a `cycle` or a `matrix` edge
  is refused. References: `flow-status-search`, `flow-status-failover`,
  `tree-status-reorg`.
- **`scale` on `matrix`** — the groups as an order, weakest first (2 to 5
  steps), for heatmaps, risk matrices and skills matrices. Cells are filled by
  tone from the theme's new `[mark] ramp` (the page's ink at increasing
  strength; a short scale is spread across the whole ramp) and the key lists
  every step in order. Every cell `group` must be a step; an ungrouped cell
  stays blank for *not assessed*. A `key` line off the scale, a repeated step,
  and more than five steps are refused at their pointers, and a cell `value`
  is refused with the advice to bucket and name. The theme loader refuses a
  ramp of fewer than five steps, neighbours closer than 0.08, or a step darker
  than 0.4 (past that a cell's label drops under 4.5:1 on a dark page, where
  the heaviest step is the lightest cell). References: `matrix-scale-risk`, `matrix-scale-ci`,
  `matrix-scale-skills`.
- **`hub` on `cycle`** — what the loop turns around (the management system a
  quality cycle improves, the log a flywheel learns from), drawn centred inside
  the ring, which grows to make room. It is not a step: the ring check ignores
  it, and an edge may join it only as a spoke in `aside`, `weak` or `link`
  (refused at the edge's `role` otherwise). A hub needs three steps around it, a
  shortcut whose chord would cross it is refused, and `centre` on a cycle node
  now points at `hub`. Spoke labels stand beside their line. References:
  `cycle-hub-quality`, `cycle-hub-flywheel`, `cycle-hub-oncall`.
- **A readability budget per kind.** A document holding more than its kind can
  be read at — 15 nodes and 16 edges on a `flow`, 15 on a `tree`, 8 on a
  `cycle`, 6 `columns`, 25 `matrix` cells, and so on — is refused by
  `drawspec validate` with the pointer of the first entry over and a message
  telling the author to split it into an overview plus detail diagrams. It
  comes before the physical fit limit (around twenty boxes), and the top-level
  `width` does not lift it. Every limit sits above the largest reference
  document of its kind; the table is generated into `docs/format.md`.
- **An emphasis cap.** At most two elements per document may take the
  `emphasis` role (nodes, items, positions, series, curves counted together);
  the third is refused at its `role` with the fix. `strong` edges are not
  counted — a path is several edges and reads as one line.
- **An Agent Skill, `skills/drawspec/SKILL.md`** — a short pointer (install,
  read `AGENTS.md`, write JSON, `drawspec validate`, `drawspec render`, fix
  refusals) with triggers and do-not-use cases in its description. A test holds
  every command, flag and MCP tool it names to the real CLI and server.
- **Gallery renders on every pull request.** CI's `gallery` job renders
  `docs/reference/` with the branch's code and uploads the SVGs as the
  `gallery-pr-<number>` workflow artifact, so reviewers can see the drawings.
- **`files`, the fifteenth kind** — a directory listing drawn from flat paths
  (`src/app/main.py`); the folders a path passes through are inferred, so there
  is no nesting depth to get wrong. A trailing `/` marks an empty folder, a last
  segment of `...` stands for entries not listed, `link` draws a symlink to its
  target, `status` marks an entry `added`, `changed` or `removed` with a labelled
  pill (never colour alone), and `note` adds a comment in one aligned column.
  `sort` is `given` (default), `name` (natural) or `folders-first`. `style` is
  `icons` (default: tinted folders, and pages with a small tag spelling the
  extension — `PDF`, `JSON` — lettered as part of the picture), `plain` (names and guides), or `unicode` /
  `ascii` (monospace text, as `tree` prints it). Paths written twice, a file used
  as a folder, `..` segments and absolute paths are refused at their entry.
- **`drawspec render --format text`** and `render_text()` — a `files` tree as
  plain text for a code block.
- **`[files]` theme section** — `tint` (folder fill strength, 0 for outlines),
  `types` (`labels`, `pictures` — five drawn type shapes — or `none`),
  `colours` (by extension, type family or `folder`; a coloured label is a
  solid tag), `label_ink` (its letters' colour) and `align` (`left`, the
  default, or `centre`). The `accent` theme colours them — white `PDF` on red;
  the default stays monochrome.
- **`rise` on `columns` and `timeline`** — the series ascends, each column drawn taller than
  the one before it on a common baseline, for a scale whose order is the
  content. Two corpus originals drew one by hand and both said so in their own
  words (*each star adds a condition to the one before it*); redrawn as plain
  `columns` they came out flat, and nothing caught it — no word was lost and no
  line crossed a word. What was lost was the geometry. It is a boolean, not a
  height per column: the author says the series rises and the theme's new
  `[box] rise` says by how much, so there is no number to get wrong. `pyramid`
  is not a substitute — it draws the last level as the narrowest, which is right
  for a maturity model and backwards for a ladder. On a `timeline` it is the
  same arithmetic and the axis is the baseline the labels already share, so
  nothing else about the drawing moves: each tick still runs from its own
  label's bottom edge to the line.
- `py.typed`, so a consumer's type checker gets the types the strict build
  already proves. Without the marker, PEP 561 requires a checker to treat the
  package as untyped, and every call into it resolved to `Any`.
- PyPI metadata: keywords, trove classifiers, project URLs and authors.
- `drawspec kinds` and `drawspec example <kind>`, for a caller that has the
  package but not the documentation. `validate` now reads `-` as stdin, so
  `drawspec example flow | drawspec validate -` is a toolchain smoke test.
- `AGENTS.md` and `llms.txt` — the whole format on one page, for an agent
  writing documents. Gated so it cannot drift from the code.
- **An MCP server** — `pip install 'drawspec[mcp]'` and `drawspec-mcp`, serving
  `validate`, `render` and `kinds` over stdio. `validate`'s violations arrive as
  `{"pointer", "message"}` objects rather than as prose on stderr, so an agent's
  write-validate-fix cycle closes without a shell in it. An optional extra: the
  library gains no dependency for anyone who does not install it.
- **`actor` on a node** — who performs a step, orthogonal to `role`, answering
  [#48](https://github.com/nuncaeslupus/drawspec/issues/48). Drawn as the box's
  lead so the names line up in a column. Free text rather than an enum on
  purpose: an actor is told apart by its **name**, which is legible in greyscale,
  so ownership costs none of the four non-colour channels the roles are told
  apart by and the greyscale invariant is untouched. A box has one lead, so a
  node naming an actor may not also write its own; that is refused by pointer.
- `CONTRIBUTING.md` and this changelog.

### Fixed

- **A `link` (any role the theme routes `direct`) whose centre-to-centre line
  grazed a neighbouring box** fell back to an orthogonal bracket, so
  `flow-mesh` drew ten of its twelve links as chords and two as right angles.
  Before falling back, the router now tries straight lines between the two
  boxes' facing sides, nearest the middle first, under the same clearance
  check; only an edge with no clear straight line is routed. Reference:
  `flow-mesh`, the only drawing that changes.
- **A `chart` of bars with no horizontal `min`/`max`** drew the first and last
  bar half outside the axes, because the range stopped exactly at the first and
  last x (1 … N for `categories`). An unpinned side now gets half a bar band of
  room; a side the author pins is unchanged, so no reference drawing moves.
- **A self-loop in a `flow` or a `tree`** (an edge from a box to itself) left
  the box's side and re-entered through the middle of its top, where its
  incoming arrow lands, so the two heads met and the loop read as a branch of
  the edge above. It now uses the `states` geometry: out and back on the same
  side, across the reading direction, its label outside it and its room
  reserved in the layout so no neighbour sits on it. A loop on a group and a
  third loop on one box are refused at the edge's `to`. Reference: `flow-retry`.
- An edge from a group's frame no longer starts on the line an edge from a box
  inside it leaves by, which drew the two as one edge from that box; and an
  edge arriving at the far side of a frame, out past every box, is routed
  instead of refused with "no orthogonal route".

### Changed

- A `files` status tag draws removal with a true minus sign, `− removed`, as
  the new graph marks do; the plain-text tree keeps the ASCII `-`.
- **`AGENTS.md` routes by purpose.** It opens with *should this be a diagram at
  all?* (a list is bullets, attributes are a table, one shape is a sentence),
  chooses the kind from what the reader must understand — including `rise` for
  a ranking or ascent — and states the readability budget, the emphasis cap and
  the overview-plus-detail split. The timeline worked example moved out to keep
  the page under its 200-line limit; the README still carries it.
- `docs/reference/scatter-pareto.json` emphasises two initiatives, not three:
  *Add SSO* had the same impact as *Cache the slow query* at four times the
  cost, so it was not a pick.

## 0.1.0 — unreleased

The first release. Thirteen diagram kinds, a published JSON Schema, a themeable
renderer, and a CLI.

### Added

- **Thirteen kinds** — `flow`, `tree`, `cycle`, `stack`, `timeline`, `columns`,
  `matrix`, `pyramid`, `rings`, `funnel`, `chart`, `quadrant`, `curve`.
- **A document format with no coordinates in it.** `x`, `font_size`, `stroke`
  and twenty-odd other fields are refused by name, each with the JSON pointer of
  the place it was written, so a placement mistake cannot be expressed rather
  than being caught late.
- **A published JSON Schema**, versioned and addressable, generated from the same
  field tables the runtime validator uses — so the schema an editor completes
  against and the tool that validates can never disagree.
- **Themes**, in TOML, resolving semantic roles to appearance. Includes a
  greyscale invariant: no information is carried by colour alone, so a diagram
  survives dark mode and monochrome printing.
- **Groups and bands** — containers drawn around boxes, and named things running
  alongside them. An edge may name a group as well as a node, for a relation that
  belongs to the whole container rather than to one box inside it.
- **Orthogonal edge routing** with border anchoring, lane separation, a minimum
  visible shaft, and label placement that avoids every line, box and other label.
- **A CLI** — `render`, `validate`, `theme check`, `schema` — with documented
  exit codes.
- **Embeddable output.** Inline SVG with no global `<style>`, no colliding ids
  when two diagrams share a page, and colour inherited from the surrounding
  document.
- **Bundled subsetted fonts**, so text measures identically on a laptop and in a
  container with no fonts installed. No system dependency of any kind.

<!-- Compare links are added by the release, once there is a tag to compare
     against. `main...HEAD` compares the default branch with itself, and a
     link to an unpushed tag is a 404: both show a reader nothing. -->

[Unreleased]: https://github.com/nuncaeslupus/drawspec/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/nuncaeslupus/drawspec/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/nuncaeslupus/drawspec/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/nuncaeslupus/drawspec/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/nuncaeslupus/drawspec/releases/tag/v0.1.0

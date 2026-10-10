# Changelog

All notable changes to drawspec are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The **document format** is versioned separately and independently: a document
declares `"version": 1`, and that number changes only when a document written
against it would stop working. Everything below is about the *package*.

## Unreleased

### Added

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
  than 0.5. References: `matrix-scale-risk`, `matrix-scale-ci`,
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

### Fixed

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

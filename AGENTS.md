# drawspec, for agents

You write a JSON document that says what a diagram **means**. drawspec decides
every coordinate. This file is meant to be read whole; it is the short version of
[`docs/format.md`](docs/format.md) and [`docs/guide.md`](docs/guide.md).

```bash
drawspec render diagram.json -o diagram.svg   # or stdout; -o diagram.png needs drawspec[png]
drawspec validate diagram.json                # every violation, with a JSON pointer
drawspec schema --out schema.json             # the full JSON Schema
drawspec theme from site.css -o house.toml    # a theme from a brand's CSS or design tokens
drawspec render d.json --theme accent --variant dark=night.toml   # one SVG, both page modes
```

**If your client speaks MCP**, `drawspec-mcp` serves `list_kinds`, `get_example`, `get_schema`, `validate_document` and `render_document` as tools,
each violation a `{"pointer": "/edges/0/to", "message": …}` object: `pip install 'drawspec[mcp]'`, [`docs/guide.md`](docs/guide.md).

## The one rule

**You may not write anything you would need to see the output to get right.**
No `x`, `y`, `width` on a box, `font_size`, `color`, `stroke`, `points`, `dx`,
`z` — 26 such fields are refused **by name**, each with the JSON pointer of where
you wrote it. That is not a restriction to work around; it is the whole design.
If you find yourself wanting a coordinate, the answer is another `kind` or `role`.

You *may* set `width` and `height` at the **top level** — a budget for the whole canvas, not for one box.

## Every document

The smallest document that renders:

```json
{"version": 1, "kind": "flow", "nodes": [{"id": "a", "text": "A step"}]}
```

`version` (always `1`) and `kind` are required, and so is the payload the kind
selects — a `flow` with no `nodes` is refused rather than drawn empty. `title`,
`description` and `caption` are optional and always allowed. Add
`"$schema": "https://nuncaeslupus.github.io/drawspec/schema/drawspec-v1.schema.json"` for editor
completion.

`text` anywhere carries `**bold**` and `` `code` `` spans, and nothing else. A newline in `text` means *this is a lead and a detail*, not one sentence.

## Should this be a diagram at all?

Draw only what a picture says better than prose. Unrelated things are a bullet list; things with attributes are a table; one shape or one step is a sentence. If a reader learns no more from the picture than the paragraph, write the paragraph.

## Choosing a kind

Pick by what the reader must **understand**, not by what it looks like.

| The reader must understand… | Kind | Payload |
|---|---|---|
| How work moves, branches, merges or loops back; or a causal loop diagram | `flow` | `nodes` + `edges` (causal: `polarity` `+`/`-` on every edge, `delay`, named `loops`, R/B derived from the signs) |
| A hierarchy: what belongs to or reports to what | `tree` | `nodes` + `edges` |
| What a proposed change adds, changes or removes — one drawing, not before + after | `flow` or `tree` + `status` | `added`/`changed`/`removed` on nodes and edges; an edge touching a removed node is `removed`, one touching an added node `added` |
| A loop that returns to where it started | `cycle` | `nodes` + `edges` closing the ring (+ `hub`: what it turns around, joined only by `aside`/`weak`/`link` spokes) |
| Layers, each resting on the one below | `stack` | `items` |
| What happened when | `timeline` | `items` (+ `spans`) |
| How a few options differ, side by side | `columns` | `items` |
| A ranking or an ascent, where order is the point | `columns` or `timeline` + `"rise": true` | `items` |
| How rows relate to columns | `matrix` | `cells` (+ `rows`, `columns`, `edges`, `key`) |
| How much, cell by cell: a heatmap, a risk or skills matrix | `matrix` + `scale` | `cells` whose `group` is a `scale` step, weakest first |
| Levels where size means quantity or rank | `pyramid` | `levels` |
| Scopes nested inside scopes | `rings` | `rings` |
| What is lost between narrowing stages | `funnel` | `stages` (+ `amount` on every stage or none, never rising; top-level `unit`: each count and the share kept are written, the taper stays uniform) |
| A small number you already know | `chart` | `axes` + `series` (`categories` on the vertical axis: horizontal bars, each point `[amount, position]`) |
| Where items fall against two named judgements | `quadrant` | `axes` (+ `ends`: low and high words) + `positions` (+ 4 `quadrants`, top right first, counter-clockwise) |
| Where items fall by two measured values | `scatter` | `axes` + `positions` |
| The shape of a change: a hype cycle, a burndown | `curve` | `axes` + `curves` |
| What is in a directory | `files` | `entries` (+ `root`, `sort`, `style`) |
| The conditions something is in, and the events that move it | `states` | `states` + `initial` + `transitions` (`event`/`guard`/`action`; + `final`, `groups`, a group's `regions`, `fork`/`join` bar roles); every state reachable |
| Who says what to whom, in order, between a fixed set of participants | `sequence` | `participants` + `messages` (+ `fragments` `loop`/`alt`/`opt`/`par`, `groups`, `note`); a `weak` reply to a call draws the activation bar; `async` message role, `actor` participant role |
| A process whose hand-offs between parties are the point | `lanes` | a `flow`'s `nodes` + `edges`, `actor` required on each (+ `lanes`, their order; + `phases`: `[{text, members}]` in run order, every step in one); no `groups`, `bands`, `centre` |
| What a data model, schema or class holds, and how its parts relate | `entities` | `entities` (`fields` with `type`/`key`, `operations`, `tag`, `centre` for a star schema) + `edges` (`from_field`/`to_field` land on a row; `from_end`/`to_end`: `one`, `zero-or-many`, …) |
| What runs when in a plan, one row per task: overlap, phases, what waits on what | `gantt` | `axis` (numbers in a named unit, or `categories`; no dates) + `tasks` (`start`/`end`, or `at` for a milestone; `strong` on the critical path; `done` 0–100 fills the bar; `events` [{at, text}] are deliveries on the bar, `iterations` [{start, end}] loops over it) (+ `groups` of consecutive tasks, `edges` finish-to-start, `marks`) |
| A project network: what waits on what, when each can start, how much slack it has, which path sets the end date (PERT / CPM, activity on node) | `pert` | 2–20 `activities`, each `id`, `text`, `duration` (or `optimistic`/`likely`/`pessimistic`: (o+4m+p)/6) and `after` (ids, finish-to-start; no loops) (+ top-level `unit`, `start`/`finish` milestones); ES/EF/LS/LF, float and the critical path are computed, never written |
| Work sorted into columns, not joined: a kanban board, a retrospective, a story map | `board` | `columns` (a `limit` is counted for you) + `cards`, stacked in the order written (+ `rows` as slices, `cut` under the first release); no `edges` |
| One observed problem and the causes investigated, by category: a root-cause review | `fishbone` | `effect` + 2–6 `categories`, each with 1–5 `causes` (leaves: no third level; `emphasis` = confirmed root cause, `note` = ruled out); no `edges` |
| What two to four sets share, and what each holds alone | `venn` | `sets` (2 or 3 equal circles; 4 equal ellipses, region text ≤ 12 characters; no sizes) + `regions`, each named by `in`: exactly the set ids it is in; a region not listed is empty |
| One person's feeling, stage by stage, against what they do: a user or citizen journey | `journey` | `feelings` (named levels, worst first; no scores) + 2–7 `stages`, each with a `feeling` (+ `rows`, filled by each stage's `details`: `{row, text}`); one person, no `edges` |
| The parts of one known total by area — what dominates, and by how much | `treemap` | 2–10 `parts`, each an `amount` (+ `unit`, one level of `groups`); every label inside its cell, or merge the smallest into one `note` part |
| Where a known quantity goes, and how much each way: a budget, tickets by outcome | `sankey` | `nodes` (columns derived, ≤ 4) + `flows` (`from`, `to`, `amount`; `strong`); a middle node's in = out, no loops, a `note` node for the remainder |
| Values and ranges on one scale, each end in or out: an inequality, the pH scale, a spectrum | `numberline` | `axis` (`min`, `max`, `step`; or two named `ends`, no numbers) + `points` (`at`, `open`) and/or ≤ 4 `ranges` (`from`/`to`, `from_open`/`to_open`; a missing end runs on as an arrow) |
| A word problem as quantities: a whole and its parts, two amounts compared, a ratio or a fraction (bar model, tape diagram) | `barmodel` | 1–3 `bars` of `parts`, each an `amount` (length in proportion) or `units` (equal boxes), `"text": "?"` for the unknown (+ `braces` `over` part or bar ids, their `amount` checked) |
| The shares of one known total, a few of them, each labelled: a class survey, where the budget goes (a pie; a donut is the theme's `[pie] shape`) | `pie` | 2–8 `parts`, each `text` + `amount` (shares computed; `unit: "%"` must make 100 ± 1), clockwise from twelve; merge the rest into one `note` part, `Everything else` |
| A topic and its subtopics, with no order between them: revision notes, a brainstorm, a plan (a mind map) | `mindmap` | `centre` + 2–8 `branches`, each `text` (+ `branches`, nested ≤ 3 levels, ≤ 30 in all), clockwise from the top right, sides balanced for you; no `edges`, no `side` |
| A claim, the reasons for it and the objections to them: a case, a policy option, a paper's conclusion (an argument map) | `argument` | `claim` + ≤ 15 `points`, each `id`, `text`, `on` (`claim` or a point), `stance` `for`/`against` (a rebuttal is an `against` on an `against`), `with` for co-premises; `note` = evidence |
| Who is whose child and partner, generation by generation: a family tree, or a pedigree in genetics | `familytree` | ≤ 30 `people` (`id`, `sex` → square/circle/diamond; `status` `affected`/`carrier`, `deceased`, `proband`, `consultand`, `adopted`, `pregnancy`, `gender`) + `couples` (`between` two, `children` in birth order, `twins`, `separated`, `consanguineous`); rows and numbers derived; ≤ 6 partners, 4 generations |
| How one total became another, step by step: a budget gap, a deficit, a forecast to an outturn (bridge chart) | `waterfall` | `axis` (`label`, with the unit) + 3–12 `bars` left to right: each a `total` (stands on zero; first, last, and subtotals checked against the running sum) or a signed `amount` |
| How far one amount is along its scale: a progress bar, a fundraising thermometer, a KPI dial, a bullet graph | `meter` | `style` (`bar`, `thermometer`, `dial`, `bullet`; one per document) + 1–6 `meters`, each `text`, `amount`, `max` (+ `unit`, `target`; `min` on a dial; 2–5 named `bands`, `{text, to}`, rising to `max`: required on a bullet) |
| Workstreams or risks rated red, amber or green: a highlight report, a risk register, a board paper's status list | `rag` | 1–15 `rows`, each `text` (a newline adds a caption: an owner), `rag` (`red`/`amber`/`green`; the theme draws a word and a shape, never colour alone) (+ `trend` `better`/`same`/`worse`, written in words; `note`) |
| A time on an analogue clock, for teaching it: o'clock to the nearest minute, a worksheet, how long between two times | `clock` | 1–12 `clocks`, each `time` `H:MM` (0:00–23:59; none = a face to draw on; no seconds, no dates) (+ `text`, `since` shading the time passed); `numerals` `arabic`/`roman`/`quarters`/`none`, `readout` `words`/`digits`/`both`/`none` |
| A hierarchy as concentric rings, read from the middle outward: a wheel of emotions, a taxonomy (a sunburst) | `sunburst` | 2–8 `nodes`, each `text` (+ `children`, nested ≤ 3 rings, ≤ 150 in all), clockwise from twelve; optional `centre` hub; every terminal sector an equal angle, so no amounts, no `angle`/`weight` |

`flow` vs `tree`: a tree is a hierarchy and takes one edge per child; a flow may branch, merge and loop back. `flow` vs `cycle`: a `cycle` must close a ring through **every** node, and is refused if it does not.
`flow` vs `states`: a box something *is in*, re-entered, labelled by events, is a state. `flow` vs `sequence`: the same few participants talking in turn, in order, is a sequence. `flow` vs `lanes`: same document; when *who hands off to whom* matters, say `lanes`. `gantt` vs `pert`: bars on a time axis at times you know is a gantt; boxes joined by what waits on what, the times and critical path computed, is a pert network.
`tree` vs `mindmap`: a tree ranks from a root (*this first*); a mind map's main branches are peers round a centre. Links across branches make a concept map: a `flow`. `tree` vs `argument`: when each box is *for* or *against* the one above, it is an argument. `tree` vs `familytree`: a child of two parents is a family tree; one person's ancestors only is a `tree`. `sunburst` vs `treemap`/`mindmap`: a sunburst nests a hierarchy into equal-angle rings read outward (a wheel); a `treemap` nests it by *area* for amounts, a `mindmap` radiates it as peer branches with no rings. `timeline` vs `numberline`: *when* things happened, in order, is a timeline; where values sit on one measured or named scale, and whether a range's ends are in it, is a number line; one amount read against its scale, with a target or named bands, is a `meter`.

**Keep it readable.** Each kind has a budget ([`docs/format.md`](docs/format.md#the-readability-budget); a `flow`: 15 nodes, 16 edges).
Past it a document is refused even though it would fit: split it into an **overview** naming each part once, plus a **detail** diagram per part. At most two elements may be `emphasis`.

## Roles

A role is semantic. The theme turns it into a shape and a weight — you never
name either.

**Nodes** — `start`, `step` (default), `decision`, `terminal`, `emphasis`, `note`, `group`;
`io` (data in/out), `subroutine` (defined elsewhere), `store` (database, queue), `person` (a human, C4) in `flow`/`tree`/`lanes`.
**Edges** — `flow` (default), `link`, `exchange`, `weak`, `owns`, `strong`, `aside`; `inherits` and `realizes` (hollow triangle) in `entities` only.

Use `decision` for a question with branching answers, `note` for an aside that is not a step, `link` for a connection with no direction.

**Who performs a step is not a role.** Use `actor` — free text on a node,
orthogonal to `role`, drawn as the box's lead so the names line up in a column:
`{"id": "approve", "text": "Sign off", "actor": "A release manager"}`. A human step
is not a `decision`: a diamond promises a branch. A box has one lead, so an `actor`
forbids a newline in `text` — except in `lanes`, where the actor is the lane.

## Worked examples

A flow — `role` is the only appearance decision in the file:

```json
{
  "version": 1,
  "kind": "flow",
  "title": "Triaging a report",
  "nodes": [
    {"id": "arrive", "text": "A report arrives", "role": "start"},
    {"id": "repro", "text": "Does it reproduce?", "role": "decision"},
    {"id": "fix", "text": "Schedule a fix", "role": "step"},
    {"id": "ask", "text": "Ask for the document", "role": "terminal"}
  ],
  "edges": [
    {"from": "arrive", "to": "repro"},
    {"from": "repro", "to": "fix", "label": "yes"},
    {"from": "repro", "to": "ask", "label": "no"}
  ]
}
```

A chart — no colour is named; series are told apart by fill pattern too, so the drawing survives greyscale:

```json
{
  "version": 1,
  "kind": "chart",
  "title": "Where the tickets went",
  "axes": {"horizontal": {"label": "Quarter", "min": 0, "max": 5},
           "vertical": {"label": "Incidents"}},
  "series": [
    {"name": "Platform", "mark": "bar", "data": [[1, 34], [2, 41], [3, 28]]},
    {"name": "Still open", "mark": "line", "data": [[1, 12], [2, 18], [3, 9]]}
  ]
}
```

## Containers

`groups` draws a frame around nodes — *these are inside this*; `bands` a labelled bar alongside them — *this runs alongside these*. A box is in one group or none, and any number of bands.
`classes` (1–4 `{id, text}`, named by a node's `class`; `flow`/`tree`/`lanes`) fills boxes *of one kind* wherever they sit — external systems, one team's services — with a key; never on a `note`/`group` or beside `status`.

An edge may name a **group** as well as a node, for a relation belonging to the
whole container rather than one box in it. It may not join a container to
something already inside it.

```json
{
  "version": 1,
  "kind": "flow",
  "nodes": [
    {"id": "api", "text": "The API"},
    {"id": "store", "text": "The store"},
    {"id": "watch", "text": "The monitoring platform", "role": "note"}
  ],
  "edges": [{"from": "watch", "to": "plane", "label": "watches"}],
  "groups": [{"id": "plane", "text": "The control plane", "members": ["api", "store"]}]
}
```

## When it refuses

A refusal is information, not an obstacle. Three kinds, and each tells you what to do:

- **`DocumentError`** — a field is wrong or an id does not resolve. The message carries a JSON pointer (`/edges/2/to`). Fix that path.
  All violations are reported at once, so read them all before editing. A budget refusal (`… is past what one flow can be read at`)
  means split, not trim; an emphasis refusal means give all but one or two their ordinary role.
- **`FitError`** — the diagram does not fit its width in either direction. Shorten the longest label, split the diagram, or raise the top-level `width`. Do **not** try to shrink a gap; you cannot, and that is deliberate.
- **A refused field** — you wrote a coordinate or a style. Delete it; express the
  intent with `kind` or `role` instead.

Always run `drawspec validate` before calling a document done; it prints every problem. For a terminal, a commit message or a code block, `drawspec render --format text` draws `files`, `tree`, `sequence`, `gantt`, `timeline`, `board`, `stack`, `rag`, `meter` (every style), `flow`, `states`, `lanes` and `pert` as plain text, 80 columns (100 for `lanes` and `sequence`) unless `--width` says otherwise (a plan's dependencies are lines into the next bar, or listed under it as `B after A` when no clean route exists; a timeline whose entries all have `at` is spaced in proportion, long gaps shortened and dashed); a drawing too wide is refused at its widest thing's pointer, a graph past the text budget (15 boxes, 3 crossings) is refused as noise, and other kinds refuse.

## Do not

- Do not emit SVG yourself. The whole point is that you do not place anything.
- Do not add fields hoping they are ignored — unknown fields are errors.
- Do not use `chart`, `treemap`, `sankey`, `pie`, `waterfall` or `meter` for exploring data. No statistics, dates, log scales or second axis. They state a few numbers you already know.
- Do not use drawspec for anything whose point is *where things are* — a floor plan, a map. There is no declarative description of those.

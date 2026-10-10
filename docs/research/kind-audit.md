# Kind audit: can the older kinds say more, or say it more clearly?

Status: **audit**, input to proposals, not a decision. Written on branch
`ccr-6186f7c4-lrvt8d` in answer to the owner's question: the newer kinds are richer
graphically; can the older ones show more complex things, or show them more clearly,
without becoming more complex — and is there anything yEd-class editors express that
drawspec cannot?

## Method

The round-2 method ([`corpus-round2.md`](corpus-round2.md), [`kinds-survey.md`](kinds-survey.md)),
applied to the 26 kinds that predate round 2:

1. **What real diagrams of the kind show** that drawspec cannot express, named against a
   public convention or tool feature set: ISO 5807 / GCSE flowchart symbols, UML, BPMN,
   C4, Mermaid, PlantUML, Visio, MS Project, Plotly, yEd/draw.io. Sources were found by
   web search and read from the search engine's summary; nothing was opened and measured,
   so rows marked **(check)** need a direct look before building, as in round 2.
2. **What our own gallery shows**: every older kind's reference documents were rendered
   to PNG (`drawspec render … --format png`) and looked at, alongside the newer kinds
   (meter, rag, pie, waterfall, treemap, mindmap, familytree) to see the visual vocabulary
   they introduced.
3. **Verdict** by `CONTRIBUTING.md`'s rule: a new field needs evidence that real diagrams
   use it **and** that today's vocabulary cannot say it. A theme-only change (no document
   field) is preferred when the meaning is already in the document.

Two things were also tested by hand rather than read: a `tree` with a second, `weak`
parent (accepted and drawn: org-chart dotted-line reporting already works) and nested
`groups` in a `flow` (accepted). And one defect turned up: see rank 1.

### The visual vocabulary the newer kinds introduced

| Device | Where it is used | What it means |
|---|---|---|
| Ink-fraction **tone ramp** (`[mark] ramp`, 0.08–0.4 of the ink) | matrix `scale`, meter bands | an order: light = less |
| Faint **fill patterns** (`[mark] fills`: dots, hatch, grid, cross) + a **key** | chart series, pie, treemap groups, waterfall, matrix `group`/`key`, argument `against` | a set of unordered classes, legible in greyscale |
| **`note` role** = dashed, unfilled | pie/treemap remainder, board placeholder, numberline context | "not the content, the rest" |
| **`emphasis`** = heavier outline + bold, ≤ 2 | everywhere | "look here" |
| **Shape** carries a class | rag (circle/triangle/square), familytree (square/circle/diamond) | category without colour |

The older kinds use the last two only. Nothing in `flow`/`tree`/`lanes`/`states`
can say *these boxes are of one class* (with a key), and no container or level is ever
toned. That is the gap the owner sensed; most of it can be closed in the **theme**,
because the meaning is already in the document.

## Recommended improvements, ranked

| Rank | Kind(s) | Proposal | Evidence | Size | Value |
|---|---|---|---|:-:|:-:|
| 1 | `chart` | **Horizontal bars**: `categories` on the `vertical` axis draws bars running across, each `[amount, position]`. Today it is accepted and drawn wrongly (vertical bars at the amounts, height = category index — tested). At minimum refuse it now; then draw it. | FT *Visual Vocabulary* "ordered bar" and the ONS/GSS chart guidance use horizontal bars for long category names **(check)**; Plotly/Excel `orientation` | S | high |
| 2 | `quadrant` | **`quadrants`**: four strings, top-right first (Mermaid's order) — named quadrant labels drawn faint in each corner; and **axis `ends`** (`["Low", "High"]`, the `numberline` field) for the two ends of each axis. Refuse `quadrants` ≠ 4 and `ends` with `min`/`max`. | Mermaid `quadrantChart` (`quadrant-1..4`, `x-axis Low --> High`); BCG matrix, Eisenhower, Gartner MQ, power/interest grid all name the quadrants | S | high |
| 3 | `flow`, `lanes`, `tree` | **Three node roles with distinct shapes**: `io` (parallelogram: data in or out), `subroutine` (box with doubled sides: a process defined elsewhere), `store` (cylinder: where data rests — a database, a queue, a file). New theme shapes `parallelogram`, `subroutine`, `cylinder`. Refused in kinds whose roles are fixed (states, sequence, entities). | ISO 5807 symbols; UK GCSE CS (OCR J277, AQA) teach terminal, process, decision, **input/output**, **sub-program** **(check)**; Mermaid `[/ /]`, `[[ ]]`, `[( )]`; DFD (Yourdon/Gane–Sarson) data store; C4 database container | M | high |
| 4 | graph kinds (theme only) | **Toned containers**: a group frame (flow/tree `groups`, states composites, sequence `groups`, lanes) washed with an ink-fraction tone, deeper nesting one ramp step darker; alternate lanes washed. A theme key (`[role.group] tone = 0.05`, `[lanes] stripe = true`), drawn as `currentColor` + `fill-opacity` so dark mode works. No document field. | draw.io/yEd containers and swimlanes are tinted by default; C4 boundary boxes; Visio cross-functional lanes **(check)**. Tested: a theme `fill_pattern = "solid"` on `role.group` already tints frames, but only with a hex colour that breaks dark mode | S | med-high |
| 5 | `flow`, `lanes`, `tree` | **Node classes with a key**: node `class` (free word) + top-level `classes`: `[{id, text}]`, 2–4 of them. Each class gets one of `[mark] fills` (faint) and the key is drawn under the drawing, as matrix `key` is. Refuse a `class` not declared, > 4 classes, a class with no node. Not with `status` on the same node (both mark the box). | C4: person / internal / **external (grey)** systems, with a legend recommended (draw.io C4 docs); Mermaid `classDef`/`class`; PlantUML stereotypes + skinparam; DFD external entities; architecture diagrams coloured by tier or team | M | med-high |
| 6 | `funnel` | **`amount`** on stages (+ top-level `unit`, `values`): widths stay the drawn taper but each stage writes its count and the share kept from the one before, derived. Refuse amounts that rise, and a mix of stages with and without. | Plotly funnel `textinfo: value+percent previous`; GA4 funnel exploration, sales pipeline reports; PRISMA-style screening counts **(check)** | S | med |
| 7 | `gantt` | **`done`** on a task: a number 0–100, the share complete, drawn as a solid ink inner bar (MS Project's progress line). Refused on milestones and outside 0–100. | MS Project *% Complete*; Mermaid gantt `done`/`active`; GanttProject, Smartsheet "complete-through" bar | S | med |
| 8 | `lanes` | **`phases`**: `[{text, members}]` — consecutive ranks named across all lanes, drawn as a header strip and a separator line, the other axis of the grid. Members must be a contiguous run in rank order. | Visio cross-functional flowchart *Separator / Phase* shapes (Microsoft docs); BPMN tools' milestone lanes **(check)** | M | med |
| 9 | `pyramid`, `funnel`, `rings`, `stack` (theme only) | **Graded levels**: an optional theme key per kind (`[pyramid] shade = "ramp"`, etc.) that fills levels from the existing `[mark] ramp`, apex/innermost darkest. Off by default. | Maslow, evidence pyramids, onion/ring diagrams and marketing funnels are almost always graded **(check)**; matches meter bands | S | low-med |
| 10 | `tree` | **`chance`** node role (circle) for decision trees, beside `decision` (square in that convention, diamond here). | OpenLearn and CIE Business decision-tree conventions (both already in `kinds-survey.md`) | S | low |

Ranks 1–2 are small and fill a plain gap; 3–5 are the cross-cutting work the owner asked
about; 6–10 are per-kind and optional. Every row keeps the rules: no colour named in a
document, no `value` (rank 6 uses `amount`), emphasis cap untouched, every new
distinction carried by shape, pattern or word and so legible in greyscale.

## Cross-cutting: graph kinds against yEd and draw.io

| Feature (yEd / draw.io) | drawspec today | Verdict |
|---|---|---|
| **Node shapes** (dozens of palettes) | 5 via roles: rect, pill, diamond, ellipse, none | **Matters, narrowly.** Three shapes carry meaning across standards: I/O, sub-process, data store (rank 3). Hexagon ("preparation"), manual input, punched tape, off-page connector are ISO 5807 relics — gimmicks today. Icons (AWS/Azure stencils) are out of scope: drawing, not meaning. |
| **Groups / nested containers** | `groups`, nested, edges to a group, `bands` | Already covered structurally. **Clarity gap**: frames are dashed outlines only, so nesting reads weakly (rank 4). Collapsible groups are an editor feature, not a drawing one. |
| **Swimlanes / tables** | `lanes` (one axis), `matrix` | One axis only; Visio's second axis (phases) is rank 8. yEd's lane-in-lane nesting (pool → lane) is rare in real figures: leave. |
| **Edge styles**: dashed, bold, bidirectional, undirected, arrowheads | `weak`/`aside` dashed, `strong` heavy, `exchange` both ways, `link` none, `owns`/`inherits`/`realizes` UML heads | Covered. Each style is already a role with a meaning. Arbitrary arrowhead choice is a gimmick. |
| **Edge labels** | `label`, plain text | Covered. Code spans in labels are open question 2 of `review-2026-10.md`. |
| **Ports** (edge attaches at a chosen side) | refused by name (`port`) | **Gimmick for us**: a coordinate decision. `entities` `from_field` already covers the one semantic use (land on a row). |
| **Colour / grey fills** | per role in the theme; `status` marks | Matters as *classes with a key* (rank 5) and *toned containers* (rank 4), never as per-node colour. |
| **Legends** | auto key for matrix, chart, status, treemap | Comes for free with rank 5; a free-form legend box is a `note`. |
| **Edge bundling, orthogonal/organic layout choice** | layout is the tool's | Out of scope by design. |
| **Images / icons in nodes** | none | Out of scope (drawing program); `files` already draws its own icons. |

## Per-kind notes

**flow** — Richest older kind (groups, bands, loops, status, actor, self-loops). Real
flowcharts and DFDs need I/O, sub-process and store shapes (rank 3); architecture and
C4-style context diagrams need classes with a key (rank 5). Gallery: `flow-groups` nested
frames read as a tangle of dashed lines; a tone would separate them (rank 4).

**tree** — Dotted-line second parent already works (`weak` edge). Decision trees want a
chance node (rank 10). Org charts' vacant post = `note` role; enough. Shapes from rank 3
apply.

**cycle** — `hub` added; real life-cycle and PDCA figures need nothing more. Wheel theme
covers the loud style. LEAVE.

**stack** — Layer diagrams (OSI, tech stacks) sometimes show a side bracket spanning
layers; that is a `flow` `band`. Gallery: plain but clear. LEAVE (optional tone, rank 9).

**timeline** — `spans`, `at`, `rise`, notes cover eras and gaps. Parallel tracks are a
`gantt`. LEAVE.

**columns** — Comparison columns; `emphasis` marks the recommended option. LEAVE.

**matrix** — Most developed of the older kinds (`scale`, `group`/`key`, `edges`). LEAVE.

**pyramid** — Real pyramids (Maslow, evidence hierarchy) are graded and sometimes labelled
on the side; the side label is a `note`. Gallery is a bare outline. Rank 9 at most.

**rings** — Onion/scope diagrams; gallery is three bare circles with lots of air. Real ones
are usually graded (rank 9). Sectors in rings (capability wheels) would be a new kind:
LEAVE.

**funnel** — The kind's own definition is "what is lost between stages", yet it cannot
state how much. Rank 6.

**chart** — Horizontal bars are drawn wrongly today (rank 1). Reference/target lines:
`meter` bullet and `curve` spans cover the common cases. Dual axis, log, error bars stay
refused (not charting software). Otherwise LEAVE.

**quadrant** — Missing the most recognisable element of the genre, the quadrant names, and
the low/high ends of each axis (rank 2). Gallery shows four unlabelled quarters.

**scatter** — Grouped points (marker shape per group + key) appear in real figures, but
the 20-point budget and the "not charting software" rule make it marginal. LEAVE; revisit
if rank 5's `classes` lands, since the same key could apply.

**curve** — Hype cycle, burndown, variance: `spans` and named waypoints cover them. Shaded
phase backgrounds are decoration. LEAVE.

**files** — Icons, link, status, notes, four styles. LEAVE.

**states** — UML statecharts also have choice pseudostates (diamond), history (H),
fork/join and orthogonal regions (Mermaid `--`, PlantUML `||`). Entry/exit/do activities
already fit as the detail line. Choice is expressible with guards; regions are a real
feature but L-sized and rare outside textbooks. LEAVE; owner question 4.

**sequence** — Mermaid/PlantUML offer participant kinds (actor stick figure, database,
queue) and async arrows. A person/system distinction is the one with meaning; `role: note`
and grouping cover much of it. LEAVE unless rank 5 lands (then participants could take
`class`). Owner question 4.

**lanes** — BPMN's circles for events and pools are notation detail; the gap with meaning
is phases (rank 8). Gallery: lanes are separated by thin lines only; a stripe (rank 4)
helps a 5–6 lane drawing. Shapes (rank 3) apply.

**entities** — Covers ER and UML class. Self-relations are already owner question 1 of the
review. A toned header compartment (theme, rank 4 family) is how draw.io/dbdiagram draw
it; optional. LEAVE.

**gantt** — Progress is the one missing standard element (rank 7). Baselines and resource
histograms are project-tool features: out.

**board** — Card labels/tags in Trello/Jira are colour; `actor`, `emphasis`, `note` and
card `note` cover the meaning. LEAVE.

**fishbone** — Root cause emphasised, ruled out dashed: matches the RCA convention. LEAVE.

**venn** — Done in round 2 (4 sets, emphasis region). LEAVE.

**journey** — Rows, feelings, emphasis: matches the UX references. Emoji faces are
decoration. LEAVE.

**treemap** — Review noted group patterns behind text look busy; consider faint tones
instead of patterns for groups (a theme default, no field). LEAVE otherwise.

**sankey** — LEAVE.

## Questions for the owner

1. **Node classes (rank 5)** — accept a per-node classification with a key at all? It is
   the one proposal that adds an author-chosen grouping rather than a fixed role. If yes,
   name: `class` (Mermaid/PlantUML precedent) or `category`? (`group` is taken by
   containers on `flow`.)
2. **New shape roles (rank 3)** — all three (`io`, `subroutine`, `store`), or only
   `store`, which also serves architecture diagrams? And should `person` (C4, sequence
   actor) be a fourth, or stay text?
3. **Tones by default (ranks 4, 9)** — turn toned containers and lane stripes on in the
   default theme, or only in `accent`? The default is ink-only today; a 5 % wash is still
   ink, but it changes every grouped drawing in the gallery.
4. **State and sequence depth** — orthogonal regions in `states`, async/actor participants
   in `sequence`: leave out (current advice) or collect originals first?
5. **Funnel numbers (rank 6)** — should the taper become proportional to `amount` (a data
   chart), or stay the uniform taper with numbers written (a diagram)? The audit recommends
   the second.

## Sources

- Mermaid quadrant chart docs (mirror): https://www.mintlify.com/mermaid-js/mermaid/diagrams/quadrant
- Mermaid flowchart shapes and `classDef`: https://mermaid.js.org/syntax/flowchart.html
- draw.io C4 modelling (legend advice): https://www.drawio.com/docs/diagram-types/c4-modelling/ ; C4 overview: https://www.freecodecamp.org/news/how-to-create-software-architecture-diagrams-using-the-c4-model/
- OCR J277 flowchart teaching (I/O, sub-process, terminal) **(check the spec itself)**: https://craigndave.org/videos/ocr-gcse-j277-slr-2-1-how-to-produce-algorithms-using-pseudocode-and-flow-diagrams/ ; https://www.csnewbs.com/ocr2020-1-2-designingalgorithms
- Visio cross-functional flowchart, swimlanes and phase separators: https://support.microsoft.com/en-us/visio/create-a-cross-functional-flowchart-in-visio-for-the-web
- MS Project percent complete: https://support.microsoft.com/lv-lv/project/track-percent-complete-for-tasks ; Mermaid gantt tags (tutorial): https://dev.to/integerman/creating-gantt-charts-with-markdown-and-mermaidjs-k0g
- Plotly funnel `textinfo`: https://plotly.com/python/funnel-charts/
- Decision-tree chance nodes: see `kinds-survey.md` (OpenLearn, Cognito rows).

## As built

**Rank 1, `chart` horizontal bars** — built, not refused. `categories` on the vertical
axis make every category a row, **the first at the top** (an ordered bar chart reads
like a list, so the written order wins over "position 1 is lowest"), names on the left
wrapped to 36 % of the width, bars growing right from zero with their numbers past the
end (inside a stacked segment). Points are `[amount, position]`. Narrowed to what
draws well: every series a `bar` (a line down a list of names is refused), no negative
amounts (a diverging bar chart is out of scope), no `min`/`max` on the category axis,
not both axes categorical — each refused at its pointer.

**Rank 2, `quadrant` names and ends** — built as proposed, with two changes. Names are
drawn in each quarter's **outer corner** at part opacity of the page ink (a new
`opacity` on text runs, never a colour), and `""` leaves a quarter unnamed. `ends` with
`min`/`max` is **allowed**, not refused: a quadrant draws no numbers either way, and
`min`/`max` only frame where the scores fall. A quadrant axis got its own schema type,
so `categories` there — previously accepted and ignored — is now refused.

**Rank 6, `funnel` amounts** — built as proposed: `amount` on stages, top-level `unit`
and `values` (as `treemap` and `sankey` do units: one per document, no per-stage unit,
since a funnel counts one thing throughout). The taper stays uniform (owner question 5,
the audit's recommendation). The count and share are a line under the stage's words,
`310 people · 7.4% kept`; the share is whole above 10 %, one decimal below. Refused:
a mix of stages with and without, a rising amount, an amount of zero or less, a `unit`
with no amounts.

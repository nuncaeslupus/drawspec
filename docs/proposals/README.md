# Proposals

Designs for what drawspec might draw next. Each is written before any code, in the order
the project works: **evidence and examples first, then a JSON design with no coordinates
that refuses what it cannot draw well, then implementation.**

`filetree.md` is the one that has been through that whole path (it is now the `files`
kind) and is the template the others follow. `coverage-vs-diagram-design.md` is the
survey that produced the rest: a competing prompt pack's 44 diagram types, each sorted
into covered / feature / new kind / out of scope.

## Implementation order

Cheap features first (each closes a type outright with one field), then kinds by value
to the course notes, design documents and runbooks drawspec is for. Size is the
whole job — schema, validation, layout, theme keys, reference document, gallery, docs
regeneration, `AGENTS.md` row, and tests.

| # | Proposal | What | Size | Depends on |
|---:|---|---|:-:|---|
| 1 | [`cycle-hub.md`](cycle-hub.md) | `cycle` + `hub`: the thing a loop turns around — **built** | S | — |
| 2 | [`matrix-scale.md`](matrix-scale.md) | `matrix` + ordered `scale`: heatmaps, risk and skills matrices — **built** | S | theme `[mark] ramp` + a `theme check` rule |
| 3 | [`flow-status.md`](flow-status.md) | `flow`/`tree` + `status`: a change marked on one diagram — **built** | S | `files`' status marks (exist) |
| 4 | [`states.md`](states.md) | `states`: state machines, with initial/final pseudo-states and self-loops — **built** | M | graph layout + containers (exist); self-loop geometry (new; also fixes `flow`'s) |
| 5 | [`sequence.md`](sequence.md) | `sequence`: messages between participants, in order — **built** | L | none — a new layout family; reuses the group object and the edge roles |
| 6 | [`lanes.md`](lanes.md) | `lanes`: a `flow` with `actor` drawn as swimlanes — **built** | M | layered ranker gains a fixed cross-axis partition |
| 7 | [`entities.md`](entities.md) | `entities`: ER, database schema and class diagrams in one kind — **built** | L | new edge roles `inherits`/`realizes`; crow's-foot end treatments; row-anchored routing |
| 8 | [`gantt.md`](gantt.md) | `gantt`: tasks as intervals, phases, milestones, dependencies — **built** | M | chart axis machinery (exists) |
| 9 | [`board.md`](board.md) | `board`: kanban, story map, retrospective — **built** | M | — |
| 10 | [`fishbone.md`](fishbone.md) | `fishbone`: one effect, causes by category — **built** | M | theme `[fishbone] slant` |
| 11 | [`venn.md`](venn.md) | `venn`: two or three sets, regions named by membership — **built** | S | — |
| 12 | [`journey.md`](journey.md) | `journey`: stages, a named-feeling line, detail rows — **built** | M | `curve`'s through-every-point spline (exists) |
| 13 | [`treemap.md`](treemap.md) | `treemap`: one total by area — **built** | M | owner decision on scope (decided) |
| 14 | [`sankey.md`](sankey.md) | `sankey`: where a known quantity goes — **built** | L | owner decision on scope (decided); crossing reduction from the layered engine |
| 15 | [`theme-from.md`](theme-from.md) | `drawspec theme from`: a theme derived from a brand's CSS or design tokens — **built** | S | — |
| 16 | [`exports.md`](exports.md) | PNG export next to SVG, behind the `drawspec[png]` extra — **built** | S | — |

## Proposed from the 2026-10 survey: not yet built

[`../research/kinds-survey.md`](../research/kinds-survey.md) surveyed fields outside
software: education, business, operations, product, law and policy, health, research
papers and personal planning. Most of what it found is already covered. These five are
the gaps it ranked highest, ordered by value first and then by smallest size. The
round-2 corpus ([`../research/corpus-round2.md`](../research/corpus-round2.md)) holds
the real originals each is checked against; a built one says so in its row.

| # | Proposal | What | Size | Depends on |
|---:|---|---|:-:|---|
| 17 | [`numberline.md`](numberline.md) | `numberline`: values and ranges on one scale, with open and closed ends (inequalities, tenses, spectra) — **built** | S | `timeline`'s axis; owner decision: kind or `timeline` field (decided: its own kind) |
| 18 | [`mindmap.md`](mindmap.md) | `mindmap`: a centre topic radiating into nested branches, balanced on two sides — **built** | M | `tree`'s tidy placement; owner decision on budget (decided: 8 branches, 30 in all, depth 3) |
| 19 | [`flow-loops.md`](flow-loops.md) | `flow` + `polarity`, `delay`, `loops`: causal loop diagrams, R/B derived from the signs — **built** | S | `venn`'s depth sampling for the loop marker |
| 20 | [`argument.md`](argument.md) | `argument`: a claim, reasons and objections by stance, with co-premises under one bracket — **built** | M | `tree` layout; a hatch pattern for `against` |
| 21 | [`familytree.md`](familytree.md) | `familytree` (pedigree): people, couples and children by generation, standard symbols, derived numbering — **built** | L | the layered engine's crossing reduction, with couples as units |
| 22 | [`barmodel.md`](barmodel.md) | `barmodel`: a word problem as bars of parts in proportion, braced (the tape diagram) — **built** | S | round-2 corpus (B1–B4); owner decision: in |
| 23 | [`waterfall.md`](waterfall.md) | `waterfall`: from one total to another, step by step, subtotals checked (the bridge chart) — **built** | S | round-2 corpus (W1–W4) lifted the deferral; owner decision: in; its own kind, not a `chart` mark |
| 24 | [`pie.md`](pie.md) | `pie`: the shares of one known total as labelled sectors, donut as a theme variant — **built** | S | round-2 corpus (P1–P4); owner decision: in, with limits |
| 25 | [`venn4.md`](venn4.md) | `venn` with four sets, as four ellipses so all fifteen regions exist — **built** | S | round-2 corpus (V1–V4); owner decision: in, as ellipses |
| 26 | [`meter.md`](meter.md) | `meter`: one amount against its scale — progress bar, thermometer, dial, bullet; `style` per document — **built** | S | round-2 corpus section 10 (G1–G9) |
| 28 | [`clock.md`](clock.md) | `clock`: analogue faces showing a time, for teaching it — hands by the time, numerals, the time in words, `since` shaded — **built** | S | round-2 corpus section 12 (C1–C5) |
| 27 | [`rag.md`](rag.md) | `rag`: workstreams or risks rated red, amber or green, each a word and a shape, the trend in words — **built** | S | round-2 corpus section 11 (R1–R6); `status` was taken, so the field is `rag` |
| 30 | [`sunburst.md`](sunburst.md) | `sunburst`: a hierarchy as concentric rings of sectors, read from the middle outward, labels rotated and stepped to fit (the emotion wheel) — **built** | M | owner request; equal-angle leaves, 3 rings, optional hub |
| 32 | [`pert.md`](pert.md) | `pert`: a project network, activity on node — ES/EF/LS/LF and float computed by a forward and backward pass, the critical path drawn heavy, PERT three-point estimates — **built** | M | owner request; course notes and the textbook exercise as originals; the layered engine and router |

## Proposed: output formats

| # | Proposal | What | Size | Depends on |
|---:|---|---|:-:|---|
| 29 | [`text.md`](text.md) | text output for kinds that sit on a grid (`sequence`, `gantt`, `board`, …) and for the graph kinds (`flow`, `states`, `lanes`) — **both phases built**, plus every `meter` style, gantt dependencies and `at` spacing | M / L | accepted: both phases; width 80 for now, phase 2's 80 / 100 / 120 table is with the owner |

## Extensions filed as issues

Fields on an existing kind, each asked for by a real figure filed as an issue.

| # | Proposal | What | Size | Depends on |
|---:|---|---|:-:|---|
| 30 | [`entities-centre.md`](entities-centre.md) | `entities` + `centre`: a star schema, the fact table in the middle and its dimensions round it — **built** | S | `flow`'s radial placement; issue #135 (one original) |
| 31 | [`gantt-events-iterations.md`](gantt-events-iterations.md) | `gantt` + `events` and `iterations` on a task: lanes of a life-cycle comparison on one axis, deliveries and loops per row — **built** | S | issue #131 (one original) |

## Deferred, not proposed

The survey's one remaining *feature* verdict is left unbuilt on purpose, until a real
original asks for it (the *find the originals* rule below), not for size. Waterfall was
deferred here too until the round-2 corpus found four originals (W1–W4); it is now
built, as [`waterfall.md`](waterfall.md).

| Type | Would be | Why deferred |
|---|---|---|
| wardley | `scatter`/`quadrant` + edges between positions | One niche strategy artefact; it needs routed edges on a numeric plane, which no chart kind has. Not small, and no original yet. |

Also declined in the survey and not revisited: fan-in badges on `flow` (a count the
reader can see), dumbbell bars, polar, radar and bubble charts (charting).

Nothing here depends on another proposal, except that `states` (4) should land the
self-loop geometry that `flow` then either adopts or refuses.

## Before building any of it

* **Find the originals.** This list came from a competitor's menu, which says what
  someone expected to be asked for. `kinds-wanted.md` opened the vocabulary on 89 real
  hand-drawn figures, and the same test applies: before a kind is built, collect at least
  two real figures it would replace, and check them against the design — the survey
  there moved one in six figures to a different kind once they were actually drawn.
* **Each kind lands whole**: a `docs/reference/<kind>-*.json` per use case, rendered in
  the gallery and looked at; `make docs` and `make schema` regenerated; a row in
  `AGENTS.md`'s kind table (a test enforces it); every refusal in the proposal as a test
  with its JSON pointer; `collisions.py` and `clipping.py` clean on the references.
* **The README's count** ("more than 30 kinds") and the `kind` enum description (now
  "thirty-eight diagrams") change with every new kind.

## Decisions for the owner

1. **Scope of `sankey` and `treemap`.** Both make area carry a number. Proposed as
   in-scope under "states a small number you already know", with hard limits — or out,
   under "not charting software". — *Decided for `treemap`: in scope, kept to stating a
   small set of known proportions, not data exploration (10 parts, one level of groups,
   every part labelled inside itself), as the README's "not charting software" says.
   Built. Decided for `sankey` the same way: in scope, kept to stating a small set of
   known flows, not data exploration (14 nodes, 4 derived columns, every middle node
   balanced, no band too thin to see), as `treemap` was. Built.*
2. **Dates in `gantt`.** Proposed: none (numbers in a named unit, plus `categories`).
   Allowing ISO dates means a calendar. — *Decided: no dates; built.*
3. **Edge roles: global or per kind.** `entities` needs `inherits` and `realizes`;
   `sequence` and `states` give existing roles a kind-specific reading (`weak` = reply).
   Proposed: keep roles global, refuse the ones a kind has no meaning for. —
   *Decided: per kind; built with `entities`.*
4. **`flow` self-loops**: accepted today and drawn through the box's own incoming edge.
   Refuse in `flow`, or adopt the `states` geometry? — *Decided: adopt; built.*
5. **`lanes` as a kind** (proposed: same payload as `flow`, `actor` required) or as a
   `flow` field (`"lanes": [...]`). The kind keeps `flow`'s refusals simple. —
   *Decided: its own kind; built.*
6. **`journey.details`** is the first object keyed by ids in the format. Accept it, or
   use a flat `cells`-style array? — *Decided: neither; a list of `{row, text}` per
   stage. Built.*
7. **Count caps.** The proposals give explicit maxima (8 participants, 16 tasks, …)
   beside `FitError`. drawspec has so far refused by fit, not by count; confirm hard caps
   are wanted, or keep fit as the only limit. — *Decided: caps are wanted, and they live
   in each kind's readability budget (`docs/format.md`), refused before the fit limit;
   every new kind got an entry.*

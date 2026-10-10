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

## Deferred, not proposed

The survey's two remaining *feature* verdicts are left unbuilt on purpose, each until a
real original asks for it (the *find the originals* rule below), not for size:

| Type | Would be | Why deferred |
|---|---|---|
| waterfall | `chart` + a `bridge` mark (bars floating on a running total) | Charting-adjacent: a running total is arithmetic drawspec would do for the reader, against *not charting software*. Small to build, but none of the 89 originals in `docs/kinds-wanted.md` is one. |
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
* **The README's count** (now "twenty-six kinds") and the `kind` enum description change with
  every new kind.

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

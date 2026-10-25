# Coverage: drawspec against diagram-design's 44 types

Status: **survey** — the input to the proposals beside this page, not a decision. Every
proposed feature and kind is now built; wardley and waterfall, deferred here, were
built once originals were found ([`wardley.md`](wardley.md), [`waterfall.md`](waterfall.md)).

diagram-design is a prompt pack: 44 reference files, each telling a
model how to hand-write the SVG for one diagram type, with pixel budgets and a verifier
per type. It is a useful catalogue of *what people ask to have drawn*, and nothing else
is taken from it here: its examples, data and wording are not reused, and every example
in the proposals is our own.

It is weaker evidence than `docs/kinds-wanted.md` used. That document counted 89 real
originals; this one counts a competitor's menu. A type being on the menu says someone
expected demand, not that a set of course notes, a design document or a runbook needed
it. So each proposal names its own use cases, and the method in `kinds-wanted.md` —
*find the originals first* — still applies before any of them is built (see
`README.md` here, *Before building any of it*).

## Verdicts

Four answers, the same ones `kinds-wanted.md` uses:

* **covered** — an existing kind or field draws it today;
* **feature** — an existing kind draws it once it gains a field;
* **new kind** — nothing draws it, and it is worth a kind;
* **out of scope** — against *What it is not* in the README: not a graph engine, not
  charting software, not a drawing program.

| Their type | Verdict | Ours |
|---|---|---|
| architecture | covered | `flow` + `groups` (+ `bands` for cross-cutting concerns) |
| architecture-delta | feature | `flow` + `status` on nodes and edges → [`flow-status.md`](flow-status.md). Two side-by-side panels refused: one drawing with marked changes says it |
| axonometric-plan | out of scope | A floor plan: the point is where things are. Drawing program |
| bar | covered | `chart`, `mark: "bar"` (+ `stack`). Their dumbbell variant: out of scope (charting) |
| data-flow | covered | `flow` + `actor`; or `lanes` once it exists |
| db-schema | new kind | merged into `entities` → [`entities.md`](entities.md) |
| dependency | covered | `flow` (multi-parent and back edges are what it does). Fan-in badges: not proposed — a count the reader can see is not worth a mark |
| deployment | covered | `flow` + nested `groups` (environment ⊃ cluster ⊃ pod) |
| dp-integration | covered | `flow` with a `centre` node + `groups` |
| dp-security-matrix | covered | `matrix` (`rows`, `columns`, cell `group` + `key`) |
| er | new kind | `entities` → [`entities.md`](entities.md) |
| exploded | out of scope | A picture of a physical object in projection. Drawing program |
| fishbone | new kind | `fishbone` → [`fishbone.md`](fishbone.md) |
| flowchart | covered | `flow` |
| gantt | new kind | `gantt` → [`gantt.md`](gantt.md) |
| heatmap | feature | `matrix` + an ordered `scale` → [`matrix-scale.md`](matrix-scale.md). Numeric colour scales out of scope (charting) |
| high-level | covered | `flow` + `groups` + `bands` |
| it-state | covered | `flow` + `groups`, pain points as `note`/`emphasis` roles |
| journey | new kind | `journey` → [`journey.md`](journey.md) |
| kanban | new kind | merged into `board` → [`board.md`](board.md) |
| layers | covered | `stack` |
| line | covered | `chart`, `mark: "line"` |
| loop | feature | `cycle` + `hub` → [`cycle-hub.md`](cycle-hub.md) |
| medallion | covered | `stack`, or `flow` + `groups` when the promotions between tiers matter |
| nested | covered | `rings` (concentric scopes) or `flow` with nested `groups` (zones holding things) |
| org-chart | covered | `tree` + `actor` |
| polar | out of scope | A quantitative series on a circular axis. Charting |
| process | covered | `flow` + `actor`; `lanes` once it exists |
| pyramid | covered | `pyramid`, `funnel` |
| quadrant | covered | `quadrant` |
| radar | out of scope | Multi-series scores on N radial axes. Charting; `matrix` or `columns` states the same scores |
| sankey | new kind | `sankey` → [`sankey.md`](sankey.md). Borderline: see the scope question there |
| scatter | covered | `scatter`. Their bubble variant (area as a third value): out of scope (charting) |
| sequence | new kind | `sequence` → [`sequence.md`](sequence.md) |
| state | new kind | `states` → [`states.md`](states.md) |
| story-map | new kind | merged into `board` → [`board.md`](board.md) |
| swimlane | new kind | `lanes` → [`lanes.md`](lanes.md) |
| timeline | covered | `timeline` (+ `at`, `spans`) |
| tree | covered | `tree`; file trees `files` |
| treemap | new kind | `treemap` → [`treemap.md`](treemap.md) |
| uml-class | new kind | merged into `entities` → [`entities.md`](entities.md) |
| venn | new kind | `venn` → [`venn.md`](venn.md) |
| wardley | feature, not proposed | `scatter`/`quadrant` would need edges between positions. One niche strategy artefact; wait for an original — since built as its own kind, `wardley` → [`wardley.md`](wardley.md) |
| waterfall | feature, not proposed | `chart` would need a `bridge` mark (running total). Plausible, but charting-adjacent; wait for an original — since built as its own kind, `waterfall` → [`waterfall.md`](waterfall.md) |

**Tally:** 21 covered, 5 features (3 proposed), 14 types → 11 new kinds, 4 out of scope.

## Merges

* **ER + UML class + database schema → `entities`.** All three are named boxes with a
  list inside and typed relations between them; what differs is the vocabulary on the
  line (cardinality, inheritance, a foreign key landing on a column). One kind with
  those as fields, not three kinds with one box each.
* **Kanban + story map → `board`.** Both are cards in columns, with no connectors; a
  story map adds horizontal slices and a release cut. A board without rows is a kanban.
* **Swimlane + process + data-flow → `lanes`**, which is `flow` with `actor` promoted from
  a box's lead to the lane it sits in. Process and data-flow stay *covered* by `flow` +
  `actor` today; `lanes` is the better drawing when hand-offs are the point.

## Found while surveying

* **A self-loop is accepted by `flow` and drawn badly.** `{"from": "b", "to": "b"}`
  validates, and renders as an orthogonal route that leaves the box and re-enters it
  across its own incoming edge. Either refuse it in `flow` or give it a real geometry;
  `states` needs the geometry anyway (see [`states.md`](states.md)).
* **`cycle` refuses `centre`** with *"a cycle is ranked from its root, so it has no
  middle"*. That reasoning is right for a node *on* the ring, which is why the loop's hub
  is proposed as a separate field rather than by lifting the refusal.
* **Field names already taken by the refusal table** constrained the designs: `order`,
  `layer` and `port` are refused everywhere, so a board's card order is the order
  written, and an entity relation lands on a column through `from_field`, never `port`.

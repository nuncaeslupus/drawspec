# Session Handover

<!-- Written at session end. A new session reading this file can resume without additional context. -->

**Date**: 2026-08-13 (overnight)
**Branch**: `claude/graphic-types-review-l28z1e` · **PRs**: #20–#29, all merged

**drawspec draws thirteen kinds. It drew nine yesterday.** The four new ones —
`matrix`, `funnel`, `quadrant`, `curve` — plus containers on the graph kinds,
bars, areas and stacks on the chart, a timeline that can space by when things
happened, and an edge role for the path that matters. **1055 passing**, up from
918.

Review sheet: <https://claude.ai/code/artifact/9a70769a-8667-40b2-866c-e24ff830cea5>

## How the work was chosen

Not by preference. `docs/kinds-wanted.md` extracts all 89 hand-drawn SVGs from
the opos temario into a gitignored `originals/` and sorts every one by the kind
that would have to draw it: **68 landed on a kind that existed, 21 did not.** The
schema's own error message said a new kind "needs evidence"; that document is the
evidence, and every kind added since cites it.

## What landed, in order

| PR | What | Why it was the next thing |
|---|---|---|
| #20 | ten defects a human reviewer found | (yesterday's) |
| #21 | rings sized from labels; the inventory | closed the last review note |
| #22 | `group` — a box that contains boxes | 6 originals; the schema had declared `groups` since v1 and nothing drew them |
| #23 | `funnel` | 2 originals, and the pyramid's geometry turned a quarter turn |
| #24 | chart marks: `bar`, `area`, `stack` | the standing request, and it built the fill vocabulary `matrix` needed |
| #25 | `matrix` | 5 originals, on that vocabulary |
| #26 | `quadrant` and `curve` | 5 originals; both are diagrams with no numbers |
| #27 | the README and `KINDS` said nine | housekeeping |
| #28 | `timeline` spaced by `at` | the reviewer's own note from round one |
| #29 | the `strong` edge role | 1 original marks a critical path, and only nodes could be emphasised |

## The three decisions worth carrying forward

**Keep hand-rolling the chart.** Nothing matplotlib, plotly or pygal emits can
pass an emitter that forbids a `<style>` element, namespaces every id, allows
only theme-declared colours and embeds no font. What a library sells is
statistical plotting, interactivity and thirty chart types; what was wanted was a
**mark abstraction**, so the next mark is additive. That is what `mark:
line|bar|area` plus `stack` is.

**The author names meaning; the theme names appearance.** A matrix cell was going
to carry a `fill` until the test suite refused it — `fill` is in the schema's
rejection table. It names a **group** instead, and `[mark] fills` turns groups
into patterns in order of first mention. The same vocabulary serves chart marks.
Two new patterns (`cross`, `grid`) so four series have four fills, every one
drawn faint because *"the hatching is too strong and it is hard to read client"*
was the loudest complaint the originals drew.

**The two role vocabularies must stay disjoint.** `role_for` resolves a name
against `NODE_ROLES` first, and `edge_primitives` reads a head with
`getattr(role, "head", "none")` — so an edge whose role is also a node role
silently loses its arrow. Adding `emphasis` to both is what taught this; the edge
role is `strong` and a test holds the line.

**A container is not a kind.** `group` is a property of the graph family:
nesting is layout inside layout, only leaves obstruct routing, and the caption is
a corner tab because centred is exactly where an arrow arriving from outside
comes in.

## Open, and deliberately so

- **`spans`** — one original (RPO/RTO/WRT brackets over a timeline). One is one;
  it may be better served by irregular timeline spacing plus a bracket than by a
  kind.
- **Two pictures** — Wi-Fi cells, vector-against-raster. drawspec should decline
  them; a declarative document whose author has no coordinates is the wrong tool
  for a picture.
- **A chart series whose extremes sit on the plot edges loses its point labels.**
  Above the top point is outside the plot and below it crosses the curve, so the
  all-or-nothing rule drops them. The fix is a vertical margin on the scale, the
  way `quadrant` already has one. Left alone because it changes every existing
  chart drawing and those have been reviewed.
- The features table in `docs/kinds-wanted.md`: a label inside a bar, an axis
  caption, fork and join, and a declared straight-edge style for the one diagram
  where the mesh *is* the message. Irregular timeline spacing and edge emphasis
  are done.

## Notes for the next session

- The queue is empty; all six seeded tasks are `done` with their PRs. Export
  `ARSENAL_QUEUE_DIR="$(claude-arsenal/bin/queue_branch.sh)"` before reading it —
  the copy on the default branch is the seed, not live state.
- `originals/` is gitignored study material belonging to the other project. Rebuild
  it with the scripts in the session scratchpad if it is missing; the committed
  evidence is the inventory table in `docs/kinds-wanted.md`.
- **The habit held again.** Every fix tonight came from rendering the thing and
  looking at it — square corners on bars, the caption an arrow drove through, a
  label sitting on a midline. Keep ending a rendering task with `make gallery`.

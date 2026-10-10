# Proposal: `sankey` — where a known quantity goes

Status: **implemented** — see *As built* at the end for where it departs from this
text. Scope decided by the owner: in, kept to stating a small set of known flows. Size
**L** (a new layout with a crossing-minimisation pass and banded ribbons).

## The scope question first

A Sankey diagram is the one kind here where **thickness carries a number**. That is close
to the line the README draws: *not charting software*. The case for it is the same as for
`chart`: drawspec does not explore data, but it does **state a small number you already
know** in the same ink as the rest of the page — and a budget split, a ticket triage or
a capacity allocation is exactly such a number in design docs and course notes. The case
against: the layout is the hardest in this set, and a plotting library draws Sankeys.

Proposed: build it, with hard limits that keep it a diagram (≤ 4 columns, ≤ 14 nodes),
and refuse the rest.

## Use cases

### 1. Course notes — where a town's budget goes (illustrative figures)

```json
{
  "version": 1,
  "kind": "sankey",
  "title": "A town budget of €120 million",
  "caption": "Illustrative figures for a town of 60,000.",
  "unit": "€ million",
  "nodes": [
    {"id": "tax", "text": "Local taxes"},
    {"id": "grants", "text": "State transfers"},
    {"id": "fees", "text": "Fees"},
    {"id": "budget", "text": "Budget", "role": "emphasis"},
    {"id": "services", "text": "Public services"},
    {"id": "staff", "text": "Staff"},
    {"id": "invest", "text": "Investment"},
    {"id": "debt", "text": "Debt service"}
  ],
  "flows": [
    {"from": "tax", "to": "budget", "value": 58},
    {"from": "grants", "to": "budget", "value": 47},
    {"from": "fees", "to": "budget", "value": 15},
    {"from": "budget", "to": "staff", "value": 46},
    {"from": "budget", "to": "services", "value": 41},
    {"from": "budget", "to": "invest", "value": 22},
    {"from": "budget", "to": "debt", "value": 11}
  ]
}
```

### 2. Design document — where support tickets went last quarter

```json
{
  "version": 1,
  "kind": "sankey",
  "title": "1,000 tickets, by channel and outcome",
  "unit": "tickets",
  "nodes": [
    {"id": "email", "text": "Email"},
    {"id": "chat", "text": "Chat"},
    {"id": "phone", "text": "Phone"},
    {"id": "bot", "text": "Answered by the help bot"},
    {"id": "l1", "text": "First line"},
    {"id": "l2", "text": "Engineering", "role": "emphasis"},
    {"id": "solved", "text": "Solved"},
    {"id": "dup", "text": "Duplicate"}
  ],
  "flows": [
    {"from": "email", "to": "l1", "value": 380},
    {"from": "chat", "to": "bot", "value": 260},
    {"from": "chat", "to": "l1", "value": 140},
    {"from": "phone", "to": "l1", "value": 220},
    {"from": "bot", "to": "solved", "value": 260},
    {"from": "l1", "to": "solved", "value": 520},
    {"from": "l1", "to": "l2", "value": 150},
    {"from": "l1", "to": "dup", "value": 70},
    {"from": "l2", "to": "solved", "value": 150, "role": "strong"}
  ]
}
```

### 3. Runbook — where the cluster's cores are reserved

```json
{
  "version": 1,
  "kind": "sankey",
  "title": "64 reserved cores, by team and workload",
  "unit": "cores",
  "values": true,
  "nodes": [
    {"id": "search", "text": "Search team"},
    {"id": "pay", "text": "Payments team"},
    {"id": "api", "text": "APIs"},
    {"id": "batch", "text": "Batch jobs"},
    {"id": "idle", "text": "Reserved, idle", "role": "note"}
  ],
  "flows": [
    {"from": "search", "to": "api", "value": 18},
    {"from": "search", "to": "batch", "value": 14},
    {"from": "search", "to": "idle", "value": 8},
    {"from": "pay", "to": "api", "value": 16},
    {"from": "pay", "to": "idle", "value": 8}
  ]
}
```

## Fields

| Field | Where | Required | Decision |
|---|---|---|---|
| `nodes` | root | **yes**, 2+ | `{id, text, role?}`. Column is **derived** (longest path from a source), never written. Order within a column: written order is the starting point for crossing reduction. |
| `flows` | root | **yes**, 1+ | `{from, to, value, role?}`. `value` > 0. |
| `unit` | root | no | Written after every value and in the caption line, once. |
| `values` | root | no | As in `chart`: write each node's total beside it. Default true. |

## Refused, and why

| Refused | Why |
|---|---|
| A cycle | Quantity does not flow backwards in this picture. |
| An intermediate node whose inflow ≠ outflow | The drawing would have to invent where the difference went. Add the flow to a named node (*lost*, *idle*) — use case 3 does. The message gives the difference. |
| `value` ≤ 0 | No thickness to draw. |
| A flow thinner than the theme's minimum band at the drawn scale | It would be a hairline nobody can see or label. Refused with: *merge the small flows into one named "other" flow*. |
| More than **4** columns or **14** nodes | Keeps it a diagram. |
| A per-flow colour | Flows are told apart by position; `role: strong` (or `emphasis` on a node) draws the one that matters with the theme's emphasis fill pattern. |

## Roles

Nodes: `step`, `emphasis`, `note` (drawn lighter: the remainder). Flows: `flow`
(default band fill), `strong` (the path the diagram is about, emphasis pattern). Bands
are filled shapes in the theme's mark fills, so greyscale survives.

## Layout sketch

1. Columns by longest path; sources left, sinks right.
2. Scale: the tallest column's total plus gaps must fit the height budget (the theme's
   `[sankey] height`, or a binding `height`); value → thickness is one factor for the
   whole drawing.
3. Order within columns: barycentre sweeps (as the layered engine does) to reduce
   crossings, starting from written order so the result is deterministic.
4. Flow bands: stacked at both ends in the order of the other end's position; edges
   are cubic curves sampled to a polygon (as `cycle` samples arcs).
5. Labels: outside the bar for the first and last columns; in the gap above the bar for
   inner columns. A label that cannot fit its gap → `FitError`.

## Acceptance tests to write

* Reference documents for the three use cases.
* Conservation: each drawn node height equals the sum of its bands' thicknesses at both
  sides (to emitter precision).
* Band thickness proportional to value across the whole drawing.
* Each refusal; the imbalance message gives the missing amount.
* Deterministic output for the same document (byte-identical SVG over two runs).

## As built

Built in `kinds/sankey.py`, a layout family of its own. The owner's decision on
scope: **in, kept to stating a small set of known flows — not data exploration**,
consistent with the README's "not charting software" and with how `treemap` was
decided; the guide, `AGENTS.md` and the README say so. The three use cases are
`docs/reference/sankey-budget.json`, `sankey-tickets.json` and `sankey-cores.json`;
`sankey-energy.json` (a data centre's power, course notes) is the largest, 10 nodes in
four columns with two flows passing through a column. Where it departs from the text
above:

* **`amount`, not `value`.** As in `treemap`: `value` is refused by name everywhere,
  so a flow's number is `amount`, and a `value` on a flow is refused naming it. The
  top-level `values` switch keeps its `chart` name.
* **Every numeric refusal happens while validating, not after a layout.** The scale
  does not depend on the type: the fullest column's bands are always 240 units tall
  (a unit being the body size over eleven), and label room is added *around* the
  bands, not taken from them. So "a band thinner than the theme's minimum" is a plain
  ratio — under 1/120 of the fullest column's total, counting the flows that pass
  through it — and is a `DocumentError` at the flow's `amount`, like the loop, the
  imbalance and the fifth column. A refused document never waits on a layout or on
  the elastic fit's sixteen type sizes (treemap's sliver refusal, a `FitError`, has
  to try them all). The only `FitError` left is a label too wide to leave the bands
  room, and each try costs a few milliseconds.
* **Ends go to the last column.** Longest-path columns alone left a sink fed early
  (`Duplicate`, fed by first line) in an inner column with its label over the bands
  running past it; every node nothing leaves is moved to the last column, so the
  arrivals line up on the right.
* **A flow that skips a column passes through it.** The sketch drew skipping bands as
  one curve, which runs across any bar in between. Each such flow takes a slot in
  every column it skips — ordered and spaced like a node, the way the layered engine
  uses dummy nodes — and runs straight through it.
* **Inner labels sit above the bar inside a column slot.** An inner column is as wide
  as its widest label (at least 34 units), its bar in the middle, the bands straight
  across the slot either side of it; a label above its bar therefore has only
  straight bands below and above it, never a curve. The first column's labels are
  right-aligned left of their bars, the last column's left of theirs on the right,
  centred on the bar. Labels are wrapped to the widest of six widths (26 % of the
  canvas down to 10 %) at which every run between columns keeps 56 units to bend in;
  a run is at most 220 units, past which the drawing is centred instead.
* **Crossing reduction** is barycentre sweeps over the columns, weighted by amount,
  starting from the written order (nodes, then the flows passing through) and
  keeping the order with the fewest crossings — the written order on a tie. Then each
  column is relaxed towards what it is joined to, its items never overlapping.
* **Roles drawn**: bands are unoutlined tints of the page's ink — `flow` 0.2,
  `strong` 0.45, a band to or from a `note` node 0.1 — so they survive greyscale by
  lightness, and two bands crossing read as the darker overlap. Bars are sharp
  polygons in the node's role, tinted darker; `emphasis` has the heavier outline and
  bold words, `note` the dashed outline and a light tint.
* **No per-band label.** A band carries no words, and a flow's `label` is refused:
  the totals written under each node name every amount the reader needs in these
  diagrams, and words on a band are words on a fill. The proposal had none either;
  the refusal says so.
* **Refused by name** besides the proposal's list: a flow from a node to itself, a
  second flow between the same two nodes (add the amounts), a node no flow touches,
  duplicate ids, an unknown node (naming the closest), `percent`/`share`,
  `column`/`rank` (derived), `edges` (naming `flows`). The caps live in the
  readability budget — 14 nodes, 24 flows; the four columns, being derived, are
  checked with the flows at the node that makes the fifth.
* **No theme section.** The band height, bar, gaps and runs are fixed in units, so a
  theme cannot change which documents are refused.

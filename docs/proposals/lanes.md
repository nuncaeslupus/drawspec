# Proposal: `lanes` — a flow whose actors are the lanes

Status: **implemented** — see *As built* at the end for where it departs from this
text. Size **M** (the ranker exists; it gains a fixed cross-axis partition).

## Why

`actor` already says who performs a step, and draws the name as the box's lead. That is
the right drawing when ownership is a property of each box. When the **hand-offs** are the
point — a request crossing from support to engineering and back — the reader needs to
see a step *leave* one party's territory, and that is what a lane is: every box of one
actor in one strip, so an arrow crossing a boundary is a hand-off.

The design choice that makes this small: **`lanes` takes a `flow` document unchanged**
and reads `actor` as the lane. Turning an actor-annotated flow into a swimlane is
changing `"kind": "flow"` to `"kind": "lanes"`. Nothing new to learn, nothing to keep in
sync, and the two kinds disagree only about where an actor is drawn.

## Use cases

### 1. Runbook — handling a reported security vulnerability

```json
{
  "version": 1,
  "kind": "lanes",
  "title": "From report to disclosure",
  "lanes": ["Reporter", "Security team", "Engineering"],
  "nodes": [
    {"id": "report", "text": "Reports privately", "actor": "Reporter", "role": "start"},
    {"id": "ack", "text": "Acknowledges within 2 working days", "actor": "Security team"},
    {"id": "valid", "text": "Is it a vulnerability?", "actor": "Security team", "role": "decision"},
    {"id": "close", "text": "Explains why not", "actor": "Security team", "role": "terminal"},
    {"id": "fix", "text": "Prepares a fix in a private branch", "actor": "Engineering"},
    {"id": "verify", "text": "Confirms the fix", "actor": "Reporter"},
    {"id": "release", "text": "Releases and publishes the advisory", "actor": "Engineering", "role": "terminal"}
  ],
  "edges": [
    {"from": "report", "to": "ack"},
    {"from": "ack", "to": "valid"},
    {"from": "valid", "to": "close", "label": "no"},
    {"from": "valid", "to": "fix", "label": "yes"},
    {"from": "fix", "to": "verify"},
    {"from": "verify", "to": "release"},
    {"from": "verify", "to": "fix", "label": "still exploitable", "role": "weak"}
  ]
}
```

### 2. Course notes — an open public tender

```json
{
  "version": 1,
  "kind": "lanes",
  "title": "Open procedure, in outline",
  "caption": "Deadlines vary by contract value; see the procurement act.",
  "nodes": [
    {"id": "publish", "text": "Publishes the call for tenders", "actor": "Contracting authority", "role": "start"},
    {"id": "submit", "text": "Submit sealed bids", "actor": "Bidders"},
    {"id": "admin", "text": "Checks the administrative documents", "actor": "Contracting committee"},
    {"id": "score", "text": "Scores the bids against the published criteria", "actor": "Contracting committee"},
    {"id": "propose", "text": "Proposes the award", "actor": "Contracting committee"},
    {"id": "award", "text": "Awards the contract", "actor": "Contracting authority", "role": "emphasis"},
    {"id": "sign", "text": "Signs the contract", "actor": "Bidders", "role": "terminal"}
  ],
  "edges": [
    {"from": "publish", "to": "submit"},
    {"from": "submit", "to": "admin"},
    {"from": "admin", "to": "score"},
    {"from": "score", "to": "propose"},
    {"from": "propose", "to": "award"},
    {"from": "award", "to": "sign", "label": "the winning bidder"}
  ]
}
```

No `lanes` list: the lanes appear in the order their actors first appear.

### 3. Design document — an expense claim, with a system as a party

```json
{
  "version": 1,
  "kind": "lanes",
  "title": "Who touches an expense claim",
  "lanes": ["Employee", "Manager", "Finance", "Payroll system"],
  "nodes": [
    {"id": "submit", "text": "Submits receipts", "actor": "Employee", "role": "start"},
    {"id": "approve", "text": "Approves?", "actor": "Manager", "role": "decision"},
    {"id": "fix", "text": "Corrects the claim", "actor": "Employee"},
    {"id": "check", "text": "Checks against policy", "actor": "Finance"},
    {"id": "pay", "text": "Adds it to the next payslip", "actor": "Payroll system", "role": "terminal"}
  ],
  "edges": [
    {"from": "submit", "to": "approve"},
    {"from": "approve", "to": "fix", "label": "no"},
    {"from": "fix", "to": "approve", "role": "weak"},
    {"from": "approve", "to": "check", "label": "yes"},
    {"from": "check", "to": "pay"}
  ]
}
```

## Fields

Everything `flow` takes, with these differences:

| Field | Decision |
|---|---|
| `nodes[].actor` | **Required** on every node, and names its lane. Drawn as the lane's heading, **not** repeated as the box's lead — so the node may again use a newline for its own lead and detail, which `flow` forbids alongside `actor`. |
| `lanes` | Optional, `array of string`: the lane order, top to bottom (or left to right). Omitted → order of first appearance in `nodes`. Free text matching the `actor` strings exactly. |
| `groups` | **Refused.** A lane is the container; a frame that spans lanes says a box is in two containers. If a group is wanted inside one lane, that is a v2 question. |
| `bands`, `centre` | **Refused.** `centre` contradicts a ranked reading; a band runs alongside boxes and would cross lanes. |

## Refused, and why

| Refused | Why |
|---|---|
| A node without `actor` | Every box in a lane diagram is in a lane. The message: *if it belongs to nobody, this is a `flow`*. |
| An actor not in `lanes` (when `lanes` is given) | Almost always a spelling difference (`"Finance "`); refused at the node's pointer, naming the closest lane. |
| A lane in `lanes` with no node | An empty strip says that party does nothing; usually a stale entry. |
| More than **6** lanes, or **20** nodes | The same budget as `flow`, and lanes are expensive in the cross axis. `FitError` as well. |

## Roles

Node and edge roles exactly as `flow`. Lane headings use the `group` caption type level;
lane separators use the theme's `weak` edge role. One new theme key, `[lanes]
orientation = "rows" | "columns" | "auto"`, decides whether lanes run across the page
(the common hand-drawn form) or down it; `auto` tries rows and falls back to columns on
a `FitError`. The author never chooses, consistent with direction everywhere else.

## Layout sketch

1. Rank the graph exactly as `flow` does (`break_cycles`, layered ranks) along the
   lane direction.
2. Assign each node's cross position from its lane instead of from crossing reduction.
   Within a lane, nodes sharing a rank stack; the lane's thickness is its deepest stack.
3. Crossing reduction runs **within** each lane only.
4. Routing is orthogonal as in `flow`; lane separators do not obstruct (edges must cross
   them — that is the hand-off).
5. A rank column that would put two consecutive steps of one lane far apart is
   acceptable; compaction is a later improvement, not a correctness issue.

## Acceptance tests to write

* Reference documents for the three use cases.
* Every node's box lies wholly inside its lane's strip.
* `flow` → `lanes` round trip: the three documents above validate as `flow` once `kind`
  is changed (minus the lead/newline exemption), so the shared payload stays shared.
* An edge between two lanes crosses exactly the separators between them.
* Each refusal at its pointer; the missing-actor message mentions `flow`.
* `orientation = "auto"` falls back to columns for a seven-step, two-lane document that
  does not fit across.

## As built

Built as its own kind, as decided, drawn by the graph family: `kinds/lanes.py`
ranks and places the boxes and hands back the same `Arrangement` a flow's layout
does, so sizing, self-loops, routing and label placement are `flow`'s code.

* **Lane boundaries are `link`, not `weak`.** A `weak` line is dashed at an
  arrow's weight, and next to a dashed return edge the two read as one; the
  boundary is now a thin solid line, so every arrow — dashed or not — stands out
  against it. It is a theme key, `[lanes] separator` (any edge role), beside
  `orientation`.
* **Headings.** Rows put the names in a column at the start of the strips, each
  broken to a sixth of the canvas, with a line between them and the first step;
  columns put a name over each strip, with a line under them. Set at the group
  caption's level, in bold, so a party's name is not read as one more step.
* **Budget.** A flow's 15 nodes and 16 edges, not 20 — the proposal said both —
  plus 6 lanes. When `lanes` is omitted the cap applies to the distinct actors,
  refused at the node that names the seventh.
* **Cycles are broken from where the process starts.** The flow's ranker breaks
  them from the ids in sorted order, which in a review loop put *Amends* beside
  *Opens a pull request* as if both started the process. `lanes` searches from
  the steps nothing leads to, in the order written, and follows edges in the
  order written, so the reversed edge is the one that returns. `flow` is
  unchanged (changing it would move existing drawings).
* **Boxes are sized per orientation.** Lanes side by side share the canvas, so a
  box is held to its lane's share and may not widen past it (it is a geometric
  width there); ranks across the page share it too, so rows wrap boxes to their
  rank's share. At the default 640 width, a process of more than four or five
  ranks reads as columns; `auto` takes rows only when they fit.
* **A boundary moves off a route.** A returning edge needs its arrow head's
  length before it may turn, which is most of a lane's padding, so it ran
  along the boundary. The router's channels are kept off the boundaries (a
  sliver of each boundary is added to the grid inside the heading band), and
  any boundary still within a lane-spacing of a route running along it is moved
  to the middle of the widest clear gap between the two lanes' boxes.
* **Crossing reduction within a lane** is one barycentre pass over each stack of
  boxes sharing a lane and a rank, ties in the order written.
* **Also refused:** a lane listed twice, a blank `actor` (as missing), and the
  `group` node role — the lane is the container. Lane nodes take `id`, `text`,
  `role`, `actor` and `status`; not `note`, which a flow accepts and never draws.
  Self-loops and `status` are accepted, as on a flow.
* **References.** The three use cases (`lanes-disclosure`, `lanes-tender`,
  `lanes-expense`) all read as columns at the default width; `lanes-onboarding`
  is short enough for rows, and stacks IT's two simultaneous steps in its lane.

# Proposal: `states` — a finite state machine

Status: **implemented** — see *As built* at the end for where it departs from this text.
Size **M** (reuses the graph layout; adds pseudo-states, self-loops
and structured transition labels).

## Why not `flow`

A state machine looks like a flow and claims something different. A flow's boxes are
things done, once each, top to bottom; a state machine's boxes are conditions something
*is in*, revisited, with the arrows labelled by what moves it. Three things only a
dedicated kind can say or check:

* **The initial pseudo-state is a dot with no words.** Every `flow` node requires `text`,
  so today an author writes a `start` pill saying "start" — a state that is not one.
* **Transitions are structured**: `event [guard] / action`. Written as one free label the
  three parts are punctuated by hand and inconsistently; as fields, the theme sets the
  guard and the action apart, and validation can read them.
* **Reachability is a correctness claim.** A state no transition reaches is a bug in the
  machine, not a layout choice. `flow` cannot refuse it; `states` should.

It also needs a real self-loop (a retry, a reminder, a timer tick), which `flow` accepts
today and draws as a route through its own incoming edge (see the coverage survey).

## Use cases

### 1. Course notes — the life of an operating-system process

```json
{
  "version": 1,
  "kind": "states",
  "title": "The five states of a process",
  "initial": "new",
  "final": ["exited"],
  "states": [
    {"id": "new", "text": "New"},
    {"id": "ready", "text": "Ready"},
    {"id": "running", "text": "Running", "role": "emphasis"},
    {"id": "blocked", "text": "Blocked"},
    {"id": "exited", "text": "Exited"}
  ],
  "transitions": [
    {"from": "new", "to": "ready", "event": "admitted"},
    {"from": "ready", "to": "running", "event": "dispatched"},
    {"from": "running", "to": "ready", "event": "time slice used up"},
    {"from": "running", "to": "blocked", "event": "waits for I/O"},
    {"from": "blocked", "to": "ready", "event": "I/O completes"},
    {"from": "running", "to": "exited", "event": "calls exit()"}
  ]
}
```

### 2. Runbook — the circuit breaker in front of the payments provider

```json
{
  "version": 1,
  "kind": "states",
  "title": "When we stop calling the provider",
  "caption": "Thresholds are in `breaker.toml`; the drawing names them, it does not restate them.",
  "initial": "closed",
  "states": [
    {"id": "closed", "text": "Closed\ncalls go through"},
    {"id": "open", "text": "Open\ncalls fail fast", "role": "emphasis"},
    {"id": "half", "text": "Half-open\none trial call"}
  ],
  "transitions": [
    {"from": "closed", "to": "closed", "event": "call fails", "guard": "under the threshold", "action": "count it"},
    {"from": "closed", "to": "open", "event": "call fails", "guard": "threshold reached"},
    {"from": "open", "to": "half", "event": "cool-down elapses"},
    {"from": "half", "to": "closed", "event": "trial succeeds", "action": "reset the count"},
    {"from": "half", "to": "open", "event": "trial fails"}
  ]
}
```

### 3. Design document — an invoice, with a composite state

```json
{
  "version": 1,
  "kind": "states",
  "title": "What can happen to an invoice",
  "initial": "draft",
  "final": ["paid", "void", "written_off"],
  "states": [
    {"id": "draft", "text": "Draft"},
    {"id": "awaiting", "text": "Awaiting payment"},
    {"id": "overdue", "text": "Overdue"},
    {"id": "paid", "text": "Paid"},
    {"id": "void", "text": "Void"},
    {"id": "written_off", "text": "Written off", "role": "emphasis"}
  ],
  "groups": [
    {"id": "issued", "text": "Issued", "members": ["awaiting", "overdue"]}
  ],
  "transitions": [
    {"from": "draft", "to": "awaiting", "event": "sent to the customer"},
    {"from": "draft", "to": "void", "event": "cancelled"},
    {"from": "awaiting", "to": "overdue", "event": "due date passes"},
    {"from": "overdue", "to": "overdue", "event": "every 7 days", "action": "send a reminder"},
    {"from": "issued", "to": "paid", "event": "payment matched"},
    {"from": "overdue", "to": "written_off", "event": "90 days overdue", "guard": "finance approves"}
  ]
}
```

`issued → paid` names the **group**: payment is accepted from either state inside it.
That is exactly what an edge naming a container already means in `flow`, and here it is
also what UML means by a transition leaving a composite state.

## Fields

| Field | Where | Required | Decision |
|---|---|---|---|
| `states` | root | **yes**, 1+ | `{id, text, role?, note?}` — the node object, minus `actor` and `centre`. A newline in `text` is lead and detail as everywhere: the state's name over what holds in it. |
| `initial` | root | **yes** | The id of the state the machine starts in. Drawn as a filled dot with an unlabelled arrow to it. Required: a machine with no start state cannot be read, and reachability is measured from here. May name a group (it starts in that composite), in which case the group must say its own `initial`. |
| `final` | root | no | Ids of states in which the machine **ends**. Each gets an arrow to a ringed dot. |
| `transitions` | root | no | `{from, to, event?, guard?, action?, role?}`. `from`/`to` are state or group ids. |
| `event` / `guard` / `action` | transition | no | Composed by drawspec as `event [guard] / action`; the theme may set the guard in the `note` type level. All three optional: an unlabelled transition is a completion transition, which is real. |
| `role` | transition | no | Edge roles `flow` (default), `strong` (the happy path), `weak` (a rare or error path). Others refused: `owns`/`link`/`exchange` are not transitions. |
| `groups` | root | no | Composite states, reusing the group object; groups may nest. A group may carry `initial` (its default entry state). |

## Refused, and why

| Refused | Why |
|---|---|
| A state not reachable from `initial` | A bug in the machine. The message names it and says either add the transition or delete the state. Computed through groups (entering a group reaches its `initial`). |
| A `final` state with an outgoing transition | It is final or it is not. |
| `final` naming a group | v1 keeps finals as states; a composite's completion is drawn with a transition from the group. |
| Two transitions with the same `from`, `event` and `guard` but different `to` | A non-deterministic machine; almost always a missing guard. |
| `actor`, `centre`, `bands` | `actor` says who performs a step; a state is not performed. `bands` and `centre` have no meaning here. |
| History (`H`), fork/join, parallel regions | Not in v1. Each needs its own pseudo-state and none has evidence yet. A machine with orthogonal regions is two machines; the message says draw two. |
| More than **14** states or **24** transitions | Past that the layered layout produces the dense crossings this tool refuses elsewhere; split by composite state. Also bounded by `FitError`. |

## Roles and theme

* States: `step` (default, a rounded box — the theme may give states a softer corner
  than flow steps via `[states] shape`), `emphasis`, `terminal` (drawn as the box a final
  state is, if the theme wants it distinct), `note`. `decision` refused: a choice in a
  state machine is a guard on a transition, and a diamond would promise a step.
* Theme gains two **markers**, not roles: `[states] initial` (filled dot) and
  `[states] final` (ringed dot), sized in the theme. No author field reaches them.

## Layout sketch

Reuse `layout` (layered ranking with `break_cycles`) and `containers` (groups as
layout-in-layout) unchanged. Additions:

1. The initial dot is ranked as a node above `initial`; final dots below their states.
2. **Self-loops** are not edges to the ranker. Each is a fixed-size loop attached to the
   side of its box facing away from the rank direction (the right in a top-down
   layout), its label outside the loop. A box with two self-loops uses both sides.
   Its size is part of the box's reserved extent, so neighbours keep clear of it.
3. Back edges (state machines are full of them: *trial fails* returns to *Open*) are
   routed as `flow` already routes reversed edges.
4. Two transitions between the same pair in opposite directions are offset from each
   other rather than drawn on one line.

## Acceptance tests to write

* Reference documents for the three use cases.
* The initial dot exists, has no text, and its arrow ends on `initial`'s box border.
* An unreachable state → `DocumentError` at `/states/<i>`; a final with an outgoing
  transition → at `/transitions/<i>/from`.
* A self-loop leaves and returns to the **same** side of its box, does not cross the
  box, and its label is clear of every other line (`collisions.py`).
* A transition naming a group starts on the group frame, not on a member.
* Label composition: `event [guard] / action`, each part optional, no stray brackets or
  slashes when one is missing.
* Separately, in `flow`: decide the self-loop question (refuse, or route it with this
  geometry) and test whichever is chosen.

## As built

Implemented as proposed, with these changes:

* **One part per line.** A transition's label is composed as `event`, then
  `[guard]`, then `/ action`, each on its own line, not as one line. Rendered,
  the one-line form made the widest labels in any drawing (`call fails [under
  the threshold] / count it`), and a label wider than the gap beside its line had
  nowhere to go and was refused. The guard is not set in a different type level:
  the brackets already set it apart, and a fifth type size breaks the theme's
  four. Edge labels learned to carry several lines for this; only a composed
  label has a newline in it.
* **Fewer state fields and roles.** A state is `{id, text, role?}` — no `note`,
  which every other kind but `timeline` accepts and does not draw, and a new
  kind need not repeat that. State roles are `step`, `emphasis` and `terminal`:
  `note` and `group` are refused with `decision` and `start` (the initial dot
  replaces a "start" box), because none of them is a condition the machine is in,
  and a `note` would be refused as unreachable anyway.
* **Composite states are their own object**, `composite` (`id`, `text`,
  `members`, `initial?`), so `initial` is legal on a `states` group and not on a
  `flow` one. Its `text` is required: a composite with no name is a frame, not a
  state. Its `initial` is **drawn**, as a dot inside the frame with an arrow to
  that member, and is required whenever anything enters the group — the
  machine's `initial` or any transition — since entering it otherwise names no
  state. It must be a member of the group.
* **Theme keys.** `[states] dot` (the filled dot's diameter, and the dot inside
  a final ring) and `[states] ring` (the gap to the ring). No `[states] shape`:
  a state is the default box, whose corners the theme already rounds.
* **Self-loops.** At most two per state — one on each side across the reading
  direction — and none on a group (a frame has no box to loop on); both refused
  at the transition's `to`. The room is reserved on **both** sides of the box, so
  it stays centred in its column and its neighbours' edges still meet it square;
  the loop then takes the side no other edge of that box ends on (a return edge
  in a downward drawing goes round the right or the left). A box whose level
  reads across gets its loops below and above, and the layout is re-run if a
  level came out in the direction nobody reserved for.
* **Layout.** The gap between ranks is widened by two label lines, since every
  transition is labelled. Each pseudo-state is then pulled in to the plain rank
  gap from its state where that spot is empty, so a dot's arrow — which carries no
  label — is not a whole labelled rank long.
* **Routing order.** Forward transitions are routed first and their labels
  placed; return edges are then routed around those labels as well as the boxes.
  Routed together, the returns took the lanes beside the boxes and left the
  forward labels no room. `flow` is unchanged.
* **Two router fixes found here**, neither moving any existing drawing: an edge
  from a group's frame no longer starts on the line an edge from a member leaves
  by (the invoice's `issued → paid` and `overdue → written_off` drew as one
  trunk), and an edge arriving at the far side of a frame, out past every box,
  is routed (a return into a composite from below was refused with "no
  orthogonal route", in `flow` too).
* **Opposite-direction pairs** needed no code: the forward one leaves the bottom
  and the return goes round the side, so they are never on one line.
* **References.** The three use cases plus `states-ticket` (a composite with an
  `initial`, a return into it, `strong`/`weak` transitions, two transitions
  between one pair). In `states-process`, *Exited* is declared before *Blocked*:
  declared the other way, *Blocked* sits left of the spine and its return to
  *Ready* goes round the right, crossing *Running*'s two outgoing edges. Order
  is still the author's; a return from the left of the spine is the router's
  weak spot.
* **`flow` self-loops** adopt this geometry, in a separate change: a loop on the
  side of its box across the reading direction, never through its own incoming
  edge (`flow-retry`).

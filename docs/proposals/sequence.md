# Proposal: `sequence` — who says what to whom, in order

Status: **proposed**. Size **L** (a new layout family; no existing engine places it).

## Why

A sequence diagram is the one box-and-arrow diagram `flow` cannot fake. Its content is
**the order of messages between a fixed set of participants**: the same two
participants exchange several messages, the vertical position *is* time, and the reader
scans down. Drawn as a `flow`, every message becomes a node or a duplicated edge, the
participants are repeated, and the order is lost to the ranker.

It is also where hand-written SVG fails hardest: twenty arrows whose ends must land
exactly on a dashed lifeline, labels that must not sit on a third participant's
lifeline, and activation bars whose height must match the messages they cover. Every
one of those is placement, which is drawspec's whole argument.

## Use cases

### 1. Course notes — what DNS resolution actually does

```json
{
  "version": 1,
  "kind": "sequence",
  "title": "Resolving a name the first time",
  "caption": "Nothing is cached yet, so the resolver walks the hierarchy from the top.",
  "participants": [
    {"id": "laptop", "text": "Laptop"},
    {"id": "resolver", "text": "Recursive resolver", "role": "emphasis"},
    {"id": "root", "text": "Root server"},
    {"id": "tld", "text": "`.org` server"},
    {"id": "auth", "text": "Authoritative server"}
  ],
  "messages": [
    {"from": "laptop", "to": "resolver", "text": "where is `wiki.example.org`?"},
    {"from": "resolver", "to": "root", "text": "where is `wiki.example.org`?"},
    {"from": "root", "to": "resolver", "text": "ask the `.org` servers", "role": "weak"},
    {"from": "resolver", "to": "tld", "text": "where is `wiki.example.org`?"},
    {"from": "tld", "to": "resolver", "text": "ask `ns1.example.org`", "role": "weak"},
    {"from": "resolver", "to": "auth", "text": "where is `wiki.example.org`?"},
    {"from": "auth", "to": "resolver", "text": "`203.0.113.7`", "role": "weak"},
    {"from": "resolver", "to": "resolver", "text": "cache it for the TTL", "note": "the next lookup stops here"},
    {"from": "resolver", "to": "laptop", "text": "`203.0.113.7`", "role": "weak"}
  ]
}
```

### 2. Design document — uploading a file without passing it through the API

```json
{
  "version": 1,
  "kind": "sequence",
  "title": "A direct upload",
  "description": "The API never sees the file's bytes. It hands out a short-lived upload address, the browser writes to the store directly, and the store tells a scanner, which tells the API whether the file may be used.",
  "participants": [
    {"id": "browser", "text": "Browser"},
    {"id": "api", "text": "API"},
    {"id": "store", "text": "Object store"},
    {"id": "scan", "text": "Virus scanner"}
  ],
  "groups": [
    {"id": "ours", "text": "Our account", "members": ["api", "store", "scan"]}
  ],
  "messages": [
    {"id": "ask", "from": "browser", "to": "api", "text": "I want to upload `report.pdf`"},
    {"from": "api", "to": "browser", "text": "upload address, valid 5 min", "role": "weak"},
    {"id": "put", "from": "browser", "to": "store", "text": "PUT the bytes"},
    {"from": "store", "to": "browser", "text": "stored", "role": "weak"},
    {"id": "event", "from": "store", "to": "scan", "text": "a new object arrived"},
    {"id": "clean", "from": "scan", "to": "api", "text": "`report.pdf` is clean"},
    {"id": "dirty", "from": "scan", "to": "api", "text": "`report.pdf` is infected", "role": "strong"},
    {"id": "delete", "from": "api", "to": "store", "text": "delete it"}
  ],
  "fragments": [
    {"operator": "alt", "from": "clean", "to": "delete", "text": "scan passed",
     "else": [{"at": "dirty", "text": "scan failed"}]}
  ]
}
```

The `alt` frame runs from `clean` to `delete`, and its `else` divider sits above
`dirty`: the first branch is one message, the second is two. Had the author ended the
fragment at `dirty`, the delete would be drawn *below* the frame — happening either way —
and a reviewer would see that, where in prose or in a hand-drawn figure it hides.

### 3. Runbook — draining a node before maintenance

```json
{
  "version": 1,
  "kind": "sequence",
  "title": "Draining a node",
  "participants": [
    {"id": "op", "text": "On-call engineer"},
    {"id": "lb", "text": "Load balancer"},
    {"id": "sched", "text": "Scheduler"},
    {"id": "node", "text": "Node `web-3`"}
  ],
  "messages": [
    {"id": "out", "from": "op", "to": "lb", "text": "take `web-3` out of rotation"},
    {"from": "lb", "to": "op", "text": "0 new connections to `web-3`", "role": "weak"},
    {"id": "cordon", "from": "op", "to": "sched", "text": "cordon `web-3`"},
    {"id": "move", "from": "sched", "to": "node", "text": "stop one workload"},
    {"id": "moved", "from": "node", "to": "sched", "text": "stopped", "role": "weak"},
    {"id": "check", "from": "op", "to": "node", "text": "anything still running?",
     "note": "wait for long requests: up to 2 min"},
    {"from": "node", "to": "op", "text": "nothing", "role": "weak"}
  ],
  "fragments": [
    {"operator": "loop", "from": "move", "to": "moved", "text": "for each workload on the node"}
  ]
}
```

## Fields

| Field | Where | Required | Decision |
|---|---|---|---|
| `participants` | root | **yes**, 2+ | `{id, text, role?}`. Drawn left to right **in the order written** — that order is the reading order, not a coordinate, the same promise `nodes` makes. |
| `messages` | root | **yes**, 1+ | `{id?, from, to, text?, role?, note?}`. Drawn top to bottom in the order written. The order *is* the diagram, so there is no `at`. |
| `messages[].role` | message | no | An **edge role**, reused: `flow` (default) is a call; `weak` (dashed, open head) is a reply, which is what UML draws for one; `strong` is the exchange that matters; `aside` (dashed, no head) is a signal with no expected answer. `link`, `owns`, `exchange` refused — a message has a direction and is not ownership. |
| `messages[].from == to` | message | — | Allowed: a self-message, drawn as a hook on the right of the lifeline. |
| `messages[].note` | message | no | Drawn in **one aligned column to the right of the last lifeline**, on the message's row — the way `files` draws its notes. The first kind besides `timeline` and `files` to draw a `note`. |
| `fragments` | root | no | `{operator, from, to, text?, else?}`. A frame around the messages `from`…`to` (message ids, inclusive) and every participant they touch. `operator` is one of `loop`, `alt`, `opt`, `par`, drawn as the frame's tab. |
| `fragments[].else` | fragment | no | Only for `alt` and `par`: `[{at, text}]` — a dashed divider drawn *above* message `at`, with the condition beside it. |
| `groups` | root | no | `{id, text, members}` over **participants**: a frame round a run of lifelines ("inside our account"). Reuses the group object unchanged. |

**Inferred, not written: activation bars.** A call (`flow`) from A to B opens an
activation on B; the first later `weak` reply from B to A closes it. Nested calls nest
their bars. A call never answered gets no bar — which is the honest drawing of an
asynchronous call, so nothing is refused. The author never says how tall a bar is,
which is the one thing hand-drawn sequence diagrams get wrong most.

## Refused, and why

| Refused | Why |
|---|---|
| A message naming an unknown participant | As `/messages/3/to`, like an edge in `flow`. |
| A fragment whose `to` comes before its `from` | Same rule as a timeline `span`. |
| Two fragments that **partly** overlap | Fragments nest or are disjoint; a frame that starts inside another and ends outside it has no drawing that does not cross. Refused by pointer to the second. |
| `else` on `loop` or `opt`, or an `else.at` outside its fragment | The divider would be in a frame with one branch, or outside the frame. |
| A `group` whose members are not adjacent in `participants` | Its frame would enclose a lifeline that is not a member. The message names the participant in the way and says to reorder. |
| `activation`, `start`, `end`, `lifeline` fields | Activations are inferred (above); a field to override them is a height in disguise. |
| A participant with no message | A lifeline nothing talks to is a box with a line under it. Refused rather than drawn — it is usually a typo in an id. |
| `create`/`destroy` of participants | Not in v1. No evidence yet; a participant whose life starts mid-diagram needs its box drawn at a row, which is a decision worth making only once. |
| More than **8** participants or **30** messages | Above that a sequence diagram is a trace, not an explanation. The message says split it into phases. Participants are also bounded by fit (below). |

## Roles

* **Participants**: node roles — `step` (default) for a box, `emphasis` for the
  participant the diagram is about, `note` for an external system drawn lighter.
  `decision`, `start`, `terminal`, `group` refused (they promise a shape a lifeline head
  does not have).
* **Messages**: edge roles, as above.
* **Lifelines**: drawn in the theme's `weak` edge role with no head, a new
  `[sequence] lifeline` key if a theme wants it different.

## Layout sketch

1. **Columns.** One per participant, in order. The gap between adjacent lifelines is
   solved from the messages: every message's label must fit between its two lifelines.
   Process messages by span (adjacent first), widening the gaps they cross evenly until
   the label fits. Self-message labels claim space to the right of their lifeline.
   If the total exceeds the canvas width → `FitError`, naming the longest label.
2. **Rows.** One per message, at the height of its wrapped label plus the theme's gap; a
   self-message takes two. A fragment adds a header row above its first message and a
   footer gap below its last; each `else` adds a row.
3. **Labels never sit on a lifeline.** A label spanning intermediate lifelines would be
   crossed by them; the lifeline **breaks** under it, the way a funnel's gate line
   breaks for its gate text. That keeps the no-line-crosses-text rule intact.
4. **Fragments** are rectangles from the leftmost to the rightmost participant their
   messages touch, padded one step out per level of nesting.
5. **Notes** go in the right-hand column, top-aligned with their message.

## Acceptance tests to write

* `docs/reference/sequence-*.json` for each use case above, rendered in the gallery.
* Every message's arrow ends **exactly** on its target's lifeline (x equal to the
  lifeline's), and every head is at the end, not the start.
* A reply is drawn in the `weak` role; a call answered later gets an activation bar
  whose top and bottom are the call's and the reply's rows; nested calls nest.
* An unanswered call has no bar.
* `collisions.py` and `clipping.py` clean on every reference document — in particular
  no lifeline crosses a message label.
* Each refusal above has a test asserting its JSON pointer and its message.
* Eight participants with long names → `FitError`, not a cramped drawing.
* Greyscale: a reply is told from a call by dash and head, not by colour.

## Open questions

* Should async calls get their own role (open head, solid)? Not proposed: `aside` covers
  "a signal with no reply" and there is no evidence yet that the head shape matters to a
  reader of course notes.
* A "time passes" divider (`…an hour later…`) between rows is common in runbooks. Cheap
  (`{"gap": "an hour later"}` as a message-less entry), but waits for an original.

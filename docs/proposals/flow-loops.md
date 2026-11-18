# Proposal: `flow` + `polarity`, `delay` and `loops`: causal loop diagrams

Status: **built**. See *As built* at the end for where it departs from this text. It comes from `docs/research/kinds-survey.md` (rank 3).
Size **S**: two edge fields drawn as small marks, plus a loop label placed inside a
cycle the layout already draws. The check on loop type is a parity count.

## Why

A causal loop diagram is how systems thinking is taught and argued, in public health,
policy, sustainability, management courses and ecology. Its content is a few variables,
arrows saying *more of this means more (+) or less (−) of that*, and the feedback loops
those arrows close. Each loop is named and marked **R** (reinforcing) or **B**
(balancing).

`flow` already draws the variables and the arrows, back edges included. What it cannot
say is the sign on each arrow, the delay on some of them, or the name of each loop. Two
facts make this a drawspec feature and not just decoration:

* **The loop's type is derived, not drawn.** A loop with an even number of − links is
  reinforcing, and one with an odd number is balancing. drawspec can count, so an
  author who labels a loop wrongly is refused rather than published. That is the
  "you may not write anything you would need to see the output to get right" rule
  applied to arithmetic.
* **The loop marker goes where the loop is**, inside the cycle its arrows close. The
  layout knows that place and the author does not.

This stays a `flow`, so the budget and the self-loop geometry are unchanged. A new kind
was considered and rejected: the payload would be `flow`'s, field for field.

## Use cases

### 1. Policy brief: why waiting lists grow

```json
{
  "version": 1,
  "kind": "flow",
  "title": "Waiting lists: one loop that feeds itself, one that drains it",
  "nodes": [
    {"id": "wait", "text": "Time on the waiting list", "role": "emphasis"},
    {"id": "acute", "text": "Emergency admissions"},
    {"id": "beds", "text": "Beds free for planned surgery"},
    {"id": "private", "text": "Patients who go private"}
  ],
  "edges": [
    {"from": "wait", "to": "acute", "polarity": "+", "delay": true},
    {"from": "acute", "to": "beds", "polarity": "-"},
    {"from": "beds", "to": "wait", "polarity": "-"},
    {"from": "wait", "to": "private", "polarity": "+"},
    {"from": "private", "to": "wait", "polarity": "-"}
  ],
  "loops": [
    {"id": "R1", "text": "Deterioration", "nodes": ["wait", "acute", "beds"], "type": "reinforcing"},
    {"id": "B1", "text": "Exit to private care", "nodes": ["wait", "private"], "type": "balancing"}
  ]
}
```

R1 has two − links, so it is reinforcing, and the author's `type` agrees. If the author
wrote `"balancing"`, the document would be refused at `/loops/0/type`, and the message
would count the signs.

### 2. Course notes (ecology): predator and prey

```json
{
  "version": 1,
  "kind": "flow",
  "title": "Rabbits and foxes",
  "nodes": [
    {"id": "rabbits", "text": "Rabbits"},
    {"id": "births", "text": "Rabbit births"},
    {"id": "foxes", "text": "Foxes"},
    {"id": "deaths", "text": "Fox deaths"}
  ],
  "edges": [
    {"from": "rabbits", "to": "births", "polarity": "+"},
    {"from": "births", "to": "rabbits", "polarity": "+"},
    {"from": "rabbits", "to": "foxes", "polarity": "+", "delay": true},
    {"from": "foxes", "to": "rabbits", "polarity": "-"},
    {"from": "foxes", "to": "deaths", "polarity": "+"},
    {"from": "deaths", "to": "foxes", "polarity": "-"}
  ],
  "loops": [
    {"id": "R1", "text": "Breeding", "nodes": ["rabbits", "births"]},
    {"id": "B1", "text": "Predation", "nodes": ["rabbits", "foxes"]},
    {"id": "B2", "text": "Fox mortality", "nodes": ["foxes", "deaths"]}
  ]
}
```

Without `type`, drawspec derives it and draws R or B, and the id is the author's.

### 3. Business course: limits to growth

```json
{
  "version": 1,
  "kind": "flow",
  "title": "Word of mouth, until the market runs out",
  "nodes": [
    {"id": "customers", "text": "Customers"},
    {"id": "talk", "text": "Recommendations"},
    {"id": "rate", "text": "Adoption rate"},
    {"id": "left", "text": "People yet to adopt"}
  ],
  "edges": [
    {"from": "customers", "to": "talk", "polarity": "+"},
    {"from": "talk", "to": "rate", "polarity": "+"},
    {"from": "rate", "to": "customers", "polarity": "+"},
    {"from": "customers", "to": "left", "polarity": "-"},
    {"from": "left", "to": "rate", "polarity": "+"}
  ],
  "loops": [
    {"id": "R1", "text": "Word of mouth", "nodes": ["customers", "talk", "rate"]},
    {"id": "B1", "text": "Saturation", "nodes": ["customers", "left", "rate"]}
  ]
}
```

## Fields

| Field | Where | Required | Decision |
|---|---|---|---|
| `polarity` | edge, `flow` only | no | `"+"` or `"-"`. Drawn as the sign beside the arrowhead, in the label type. Either every edge in the document has one or none does: a half-signed causal diagram is ambiguous. |
| `delay` | edge, `flow` only | no | `true` draws the standard double stroke across the middle of the shaft. Requires `polarity`. |
| `loops` | root, `flow` only | no | `{id, text, nodes, type?}`. `nodes` lists the loop's variables in order. Each consecutive pair, and the last back to the first, must be joined by an edge in that direction. `type` is `reinforcing` or `balancing`, and when it is given it is checked against the parity of − signs. The marker shows `id` and `text`. |

## Refused, and why

| Refused | Why |
|---|---|
| `polarity` on some edges but not all | At the first unsigned edge's pointer. |
| `polarity` on a `link`, `aside` or `weak` edge | A sign states a causal direction, and those roles have none. |
| `delay` without `polarity` | A delay belongs to a causal link. |
| `loops` without `polarity` on the edges | The loop's type is computed from the signs. |
| A loop whose `nodes` are not joined in that order | At `/loops/i/nodes/j`, naming the missing edge `a → b`. |
| A loop listing a node twice, or fewer than 2 nodes | It is a simple cycle. A one-node loop is a self-loop edge, which `flow` already draws. |
| `type` disagreeing with the parity | At `/loops/i/type`: "has 1 negative link, so it is balancing". |
| Two loops with the same `nodes` | The same loop written twice. |
| `polarity`, `delay` or `loops` on any other kind | Refused by name, as usual for another family's field. |
| More than 6 loops | Budget. Beyond that the map is an overview to split. |

## Roles

No new roles. Signs and delay strokes are drawn in the edge's own ink. The loop marker
is a small circular arrow, with clockwise or anticlockwise matching how the loop runs
on the page, around the letter R or B with the `id`. The `text` goes under it in the
note type.

## Layout sketch

1. Lay the graph out as `flow` does. Back edges are already routed.
2. For each loop, take the polygon through its nodes' centres in loop order. Place the
   marker at the point of that polygon's interior furthest from every box and route
   (the same depth sampling `venn` uses for its regions). If no point has room for the
   marker, place it beside the loop's first edge, outside the boxes, and if that also
   fails, raise a `FitError` naming the loop.
3. The marker's arrow turns the way the loop runs on the page: the sign of the
   polygon's area, so it is derived and not chosen.
4. Signs sit beside the arrowhead, on the side away from the route's turn, and take
   part in the existing label-collision checks.

## Acceptance tests to write

* Reference documents for the three use cases.
* Parity: a loop with 0 or 2 − links is drawn R, and one with 1 or 3 is drawn B. A
  wrong `type` is refused at its pointer, and the message names the count.
* A loop whose nodes are not consecutive edges is refused with the missing edge named.
* Every marker lies inside its loop's polygon, or beside its first edge when the
  polygon has no room, and no marker overlaps a box, a label or a route.
* Half-signed edges are refused, and so is `polarity` on any kind other than `flow`.
* The `AGENTS.md` row for `flow` gains "a causal loop diagram: `polarity` on every
  edge, `loops` named".

## As built

Built in `kinds/loops.py`, drawn over a laid-out `flow`, with the schema checks in
`schema.py`. The references are `docs/reference/flow-loops-waiting.json`,
`flow-loops-predators.json` and `flow-loops-adoption.json` (the three use cases), and
`flow-loops-town.json` (two subsystems as `groups`, following the round-2 corpus).
The changes from the text above:

* **No `id` on a loop.** The marker's letter and number are derived. The letter
  comes from the parity of the signs, and the number counts that letter's loops in
  the order written: `R1`, `R2`, `B1`. A written id such as `B1` on a reinforcing
  loop would be one more thing that could disagree with the signs. A loop is
  `{text, nodes, type?}`, and refusals point at `/loops/i/...`.
* **The sign is the edge's label.** It is not pinned beside the head. Written as
  the label (before any `label` of the edge's own), it goes through the label
  placer, which keeps it clear of every line, box and other label.
* **Causal edges, not all edges.** "Every edge or none" applies to `flow` and
  `strong` edges. A `link`, `aside` or `weak` edge has no causal direction, so it
  cannot carry a sign, and it is not counted.
* **`groups` with `loops`, as the corpus asked.** Research maps group their
  variables into subsystems. The guide says to draw one subsystem per diagram.
* **`s`/`o` as a theme word**, as the corpus asked: `[flow] polarity = "+-" | "so"`.
  `flow-loops-adoption` uses it through `docs/reference/themes/same-opposite.toml`.
* **Room is made, then found.** A loop's interior in a layered drawing is mostly
  the gap between two ranks. A flow with `loops` therefore gets a taller rank gap
  (4.5 body sizes), which is room for a ring and a two-line name. A frame entered
  from outside keeps the ordinary gap (`Spacing.turn_gap`). The figure a loop
  closes is the polygon of its routes, in order. The marker goes at the point of
  that figure furthest from every box, label, line and earlier marker, with the
  name under the ring, beside it, or wrapped. A point in no other loop's figure is
  preferred, so that two loops sharing a side do not share a marker's place. When
  the figure has no room, the marker goes at the nearest point beside the loop's
  first link. When that also fails, the document is a `FitError` naming the loop.
* **The ring** is wide enough that the letters, and the clearance every stroke
  keeps from words, sit inside it. Its gap is at the top, and the head points the
  way the loop runs (the sign of the figure's area).
* **Delay strokes** go at the first point along the edge, from the middle outwards,
  that is clear of every label and box and away from a bend.
* **Budget**: 6 loops, in the flow's readability budget.

Review note: in `flow-loops-town` a back edge runs along a frame's side. That comes
from the existing group routing and is not specific to loops.

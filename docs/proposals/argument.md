# Proposal: `argument`: a claim, the reasons for it, and the objections

Status: **proposed, not built**. It comes from `docs/research/kinds-survey.md` (rank 4).
Size **M**: a `tree` layout with two stances drawn apart, and co-premises joined under
one bracket.

## Why

Law schools, philosophy and critical-thinking courses, debating clubs and policy units
all teach the argument map. It has one contention at the top, the reasons beneath it,
the objections to those reasons, and the rebuttals of the objections. A research
paper's discussion section has the same shape, and so does a judge's reasoning on one
issue.

A `tree` holds the hierarchy but loses the two things that make it an argument:

* **Stance.** Every box is *for* or *against* the box above it. That is the first thing
  a reader looks for, and in a `tree` it can only be put in the text.
* **Co-premises.** Two reasons that only support the claim *together* ("the offer was
  accepted" and "consideration was given") are a different argument from two
  independent reasons. Argument-mapping guides draw them under one shared bracket. A
  `tree` gives every child its own edge, so the difference cannot be drawn.

The Toulmin model (claim, grounds, warrant, backing, qualifier, rebuttal) fits the same
kind. The grounds are a `for` point. The warrant is a `for` point on the grounds, and
its backing a `for` point on the warrant. The rebuttal is an `against` point. The
qualifier is a word in the claim's text. A fixed six-slot Toulmin layout is not
proposed: its slots are a template, and the template here is the stance.

## Use cases

### 1. Law course notes: was a contract formed?

```json
{
  "version": 1,
  "kind": "argument",
  "title": "Did the email of 3 May form a contract?",
  "claim": "A binding contract was formed on 3 May",
  "points": [
    {"id": "offer", "on": "claim", "stance": "for", "text": "The quote was an offer\ncapable of acceptance"},
    {"id": "accept", "on": "claim", "stance": "for", "with": ["offer"], "text": "The buyer's email\naccepted it"},
    {"id": "consid", "on": "claim", "stance": "for", "text": "Price was agreed:\nconsideration given"},
    {"id": "counter", "on": "accept", "stance": "against", "text": "The email asked for a\nlater delivery date: a counter-offer"},
    {"id": "enquiry", "on": "counter", "stance": "against", "role": "emphasis", "text": "It asked whether the date\ncould move: a mere enquiry"}
  ]
}
```

`offer` and `accept` are co-premises: they hang from one bracket, because neither
supports the claim alone. `with` is written once, on either member. `enquiry` is a
rebuttal, an `against` on an `against`. The format needs no third stance for it.

### 2. Policy brief: a congestion charge

```json
{
  "version": 1,
  "kind": "argument",
  "title": "Should the city centre have a congestion charge?",
  "claim": "Introduce a weekday charge for the centre",
  "points": [
    {"id": "air", "on": "claim", "stance": "for", "text": "Cuts traffic and roadside pollution"},
    {"id": "evidence", "on": "air", "stance": "for", "role": "note", "text": "Comparable cities saw\ndouble-digit traffic falls"},
    {"id": "funds", "on": "claim", "stance": "for", "text": "Revenue funds the buses"},
    {"id": "fair", "on": "claim", "stance": "against", "text": "Falls hardest on low-income drivers"},
    {"id": "exempt", "on": "fair", "stance": "against", "text": "Discounts for residents and\ncare workers answer most of it"},
    {"id": "trade", "on": "claim", "stance": "against", "text": "Shops in the zone lose trade"}
  ]
}
```

### 3. Research paper: what the result supports

```json
{
  "version": 1,
  "kind": "argument",
  "title": "Does the follow-up call reduce readmissions?",
  "claim": "A nurse call at 48 h reduces 30-day readmissions",
  "points": [
    {"id": "rct", "on": "claim", "stance": "for", "text": "Randomised trial: fewer\nreadmissions in the call arm"},
    {"id": "single", "on": "rct", "stance": "against", "text": "One hospital, one season"},
    {"id": "blind", "on": "rct", "stance": "against", "text": "Outcome assessors were not blinded"},
    {"id": "records", "on": "blind", "stance": "against", "text": "Readmission is read from records,\nnot judged by an assessor"},
    {"id": "mech", "on": "claim", "stance": "for", "text": "Most avoided readmissions were\nmedication errors the call caught"}
  ]
}
```

## Fields

| Field | Where | Required | Decision |
|---|---|---|---|
| `claim` | root | **yes** | The contention: a string, drawn at the top and addressed as `"claim"` by `on`. |
| `points` | root | **yes**, at least 1 | `{id, text, on, stance, with?, role?}`. `on` is `"claim"` or another point's id. `stance` is `for` or `against` the box named by `on`. `with` lists co-premises: points with the same `on` and `stance` that support jointly. Siblings are drawn in the order written. |

## Refused, and why

| Refused | Why |
|---|---|
| `on` naming an unknown id, or a cycle through `on` | At its pointer. An argument is a tree. |
| A point with no `stance` | Required. A point with no stance is not part of the argument, and belongs in the `caption`. |
| `with` naming a point with a different `on` or `stance` | Co-premises support the same box in the same direction. |
| A point in two co-premise groups | A group is the set joined by `with` links, whichever member writes them. One point belongs to one group, at most 4 points to a group. |
| A stance other than `for` and `against` (`rebuttal`, `objection`) | A rebuttal is an `against` on an `against`. The names follow from the depth and do not need to be declared. |
| `edges` | The structure is `on`. |
| More than 15 points, or depth past 4 | Budget. Split per reason: an overview with the top-level reasons and objections, and a map per contested reason. |

## Roles

`step` (the default), `emphasis` (the decisive point; at most two), and `note` (a point
that is evidence or a source rather than a reason: drawn in the note type, beneath its
parent). Stance is not a role. It is drawn on two channels so that greyscale holds:

* a **tag** above each box, with the theme's words (`[argument] for = "because"`,
  `against = "but"`), so a reader can read the map aloud;
* the **box treatment**: `for` boxes use the theme's plain box, and `against` boxes the
  first hatch pattern. Connectors always point up to the box they bear on.

## Layout sketch

1. The claim goes at the top. Points are placed as a downward `tree` by `on`, with
   sibling order as written. Direction is fixed downward, because an argument map is
   read from the contention down.
2. Co-premises are laid out as one node of their combined width: their boxes sit side by
   side under one horizontal bracket, and a single connector runs from the bracket to
   the parent.
3. Tags sit in the box's top margin, at the box's left, in the label type. They are part
   of the box's measured extent, so nothing has to be fitted after the layout.
4. If the tree does not fit the width, raise a `FitError` naming the widest level. There
   is no horizontal fallback, which would break the reading direction.

## Acceptance tests to write

* Reference documents for the three use cases.
* Every `against` box carries the hatch and the `but` tag, and every `for` box the
  `because` tag. The test checks the emitted SVG's class per box.
* Co-premises share one bracket and one connector: the edge count equals the number of
  points minus the number of co-premise extras.
* Every refusal above, at its pointer. An unclosed `with` names the missing link.
* No tag collides with a connector (`collisions.py`).

## Open question

Should `stance` also accept `rebuttal`, as a reader-facing synonym for `against` on an
`against`? Proposed no. The tags already say *but*, *because* and *but* down the chain,
which reads correctly without a third word.

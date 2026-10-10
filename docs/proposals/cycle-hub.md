# Proposal: `cycle` + `hub` — what the loop keeps coming back to

Status: **implemented** — see *As built* at the end for where it departs from this text.
Size **S** (one field; the ring is unchanged; one box in its middle).

## Why

Many loops have something in their middle that is not a step: the PDCA wheel turns
around *the management system*; a data flywheel turns around *the model*; an
improvement cycle around *the service*. Today the middle of a `cycle` is empty, and an
author either puts the hub on the ring (wrong: it becomes a step) or reaches for `flow`
with `centre` (wrong: the ring is lost and the "every node is on the loop" check with it).

`cycle` already refuses `centre`, with the right reason: *a cycle is ranked from its
root, so it has no middle to arrange around.* A node on the ring has no middle. So the
hub is **not a node**: it is its own field, outside the ring check, drawn inside the
ring.

## Use cases

### 1. Course notes — the quality cycle

```json
{
  "version": 1,
  "kind": "cycle",
  "title": "Plan, do, check, act",
  "hub": {"id": "qms", "text": "The quality\nmanagement system", "role": "emphasis"},
  "nodes": [
    {"id": "plan", "text": "Plan"},
    {"id": "do", "text": "Do"},
    {"id": "check", "text": "Check"},
    {"id": "act", "text": "Act"}
  ],
  "edges": [
    {"from": "plan", "to": "do"},
    {"from": "do", "to": "check"},
    {"from": "check", "to": "act"},
    {"from": "act", "to": "plan"}
  ]
}
```

### 2. Design document — the feedback loop of a recommender

```json
{
  "version": 1,
  "kind": "cycle",
  "title": "Every click trains tomorrow's ranking",
  "hub": {"id": "log", "text": "Interaction log"},
  "nodes": [
    {"id": "rank", "text": "Rank items"},
    {"id": "show", "text": "Show them"},
    {"id": "click", "text": "User clicks or skips"},
    {"id": "train", "text": "Retrain nightly"}
  ],
  "edges": [
    {"from": "rank", "to": "show"},
    {"from": "show", "to": "click"},
    {"from": "click", "to": "train"},
    {"from": "train", "to": "rank"},
    {"from": "click", "to": "log", "role": "aside", "label": "recorded"},
    {"from": "log", "to": "train", "role": "aside"}
  ]
}
```

### 3. Runbook — the on-call week

```json
{
  "version": 1,
  "kind": "cycle",
  "title": "One on-call rotation",
  "hub": {"id": "runbook", "text": "This runbook"},
  "nodes": [
    {"id": "handover", "text": "Take the pager"},
    {"id": "respond", "text": "Respond to pages"},
    {"id": "review", "text": "Review the week"},
    {"id": "update", "text": "Fix what the week found", "role": "emphasis"}
  ],
  "edges": [
    {"from": "handover", "to": "respond"},
    {"from": "respond", "to": "review"},
    {"from": "review", "to": "update"},
    {"from": "update", "to": "handover"},
    {"from": "update", "to": "runbook", "role": "aside"}
  ]
}
```

## Fields

| Field | Where | Decision |
|---|---|---|
| `hub` | `cycle` root, optional | `{id, text, role?}`. Drawn centred inside the ring. Its id shares the node id space so edges may name it. |
| edges naming the hub | `cycle` `edges` | Allowed, **only** in the roles `aside`, `weak`, `link`: spokes, not steps. They are left out of the ring check (the ring must still close through every node, hub excluded). |

## Refused, and why

| Refused | Why |
|---|---|
| A hub edge in `flow`/`strong`/`exchange`/`owns` | A solid arrow to the middle reads as a step of the loop. |
| A hub in a ring of fewer than 3 nodes | Two nodes and a centre is a `flow`. |
| A hub text that does not fit the ring's interior | The ring grows to make room; if the canvas cannot, `FitError` naming the hub. |
| `centre` on a node (unchanged) | The existing message gains: *for something the loop turns around, use `hub`*. |

## Layout sketch

The ring is laid out as today. The interior's free radius is computed from the ring's
inner edge (node boxes included); the hub box is sized to its text and must fit in it
with the theme gap; if not, the ring radius grows. Spokes are straight (like `link` chords
already are), from the hub border to the node border, never crossing the ring's arcs —
they are short because they go to the nearest side.

## Acceptance tests to write

* The three documents render; the hub is centred on the ring's centre.
* Spoke edges do not cross ring arcs or other boxes (`collisions.py`).
* The ring check ignores hub edges; a ring broken elsewhere is still refused.
* Refusals above; the `centre` message mentions `hub`.

## As built

Implemented as proposed, with these changes:

* **The hub's own object.** `hub` is a `hub` object (`id`, `text`, `role`) rather
  than a `node`: a node carries `centre`, `actor` and `note`, none of which means
  anything in the middle of a ring, and `additionalProperties: false` now says so
  in an editor instead of at render time.
* **One more refusal: a shortcut through the hub.** A `cycle` already draws a
  non-ring edge as a straight chord. With a hub in the middle, a chord between
  two opposite steps would run straight through it and read as passing *through*
  the thing the loop turns around. It is refused, naming both steps and the hub,
  with the remedy (join nearer steps, or make it two spokes).
* **Spoke labels stand beside the line.** A chord's label has always been offset
  from the line by an ascent, which is enough for a slanting chord near the ring
  and not for a spoke running straight down the page: the line went through the
  middle of the word. A spoke's label is offset by the daylight measured to its
  nearest corner, and the ring grows until each labelled spoke is long enough to
  hold its label between the two boxes. Shortcut labels are unchanged, so no
  existing drawing moved.
* **How the ring grows.** One unit at a time from the radius the steps alone
  need, until the hub sits inside the arcs (clear of the wheel theme's broad
  bands too) and apart from every step by the gap peers keep — more for a step
  joined by a spoke, which needs a visible shaft. Past the canvas width the
  usual `FitError` is raised, and it names the hub.
* **The ring-check message** counts only edges between steps and says the
  spokes were set aside, so an author who closed the loop through the hub is
  told what happened.

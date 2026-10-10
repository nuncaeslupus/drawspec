# Proposal: `flow` + `status` — what a change does to an architecture

Status: **implemented** — see *As built* at the end for where it departs from this text.
Size **S** (the vocabulary and the marks exist in `files`).

## Why a feature and not a kind

Design documents propose changes to systems, and the figure that goes with one says
*what is new, what goes, what changes*. Hand-drawn, it is usually two diagrams side by
side, which forces the reader to diff them by eye and the author to keep two layouts
consistent — the exact placement problem drawspec exists to remove.

`files` already solved this for a directory: `status: added | changed | removed`, drawn as
a labelled mark (`+ ~ −` and the word), never by colour alone, with removed entries
struck through. The same vocabulary on `flow` nodes and edges draws **one** diagram of
the target state with the change marked on it.

## Use cases

### 1. Design document — taking sessions out of the monolith

```json
{
  "version": 1,
  "kind": "flow",
  "title": "Sessions move to their own service",
  "nodes": [
    {"id": "web", "text": "Web front end"},
    {"id": "mono", "text": "Monolith", "status": "changed"},
    {"id": "sess", "text": "Session service", "status": "added"},
    {"id": "redis", "text": "Redis", "status": "added"},
    {"id": "table", "text": "`sessions` table", "status": "removed"},
    {"id": "db", "text": "Main database"}
  ],
  "edges": [
    {"from": "web", "to": "mono"},
    {"from": "web", "to": "sess", "status": "added"},
    {"from": "sess", "to": "redis", "status": "added"},
    {"from": "mono", "to": "db"},
    {"from": "mono", "to": "table", "status": "removed"}
  ],
  "groups": [{"id": "dbs", "text": "Database server", "members": ["db", "table"]}]
}
```

### 2. Runbook — the failover topology during the maintenance

```json
{
  "version": 1,
  "kind": "flow",
  "title": "While the primary is down",
  "caption": "Marked against normal running.",
  "nodes": [
    {"id": "app", "text": "Application"},
    {"id": "proxy", "text": "Connection proxy", "status": "changed"},
    {"id": "primary", "text": "Primary", "status": "removed"},
    {"id": "replica", "text": "Replica, promoted", "status": "changed", "role": "emphasis"}
  ],
  "edges": [
    {"from": "app", "to": "proxy"},
    {"from": "proxy", "to": "primary", "status": "removed"},
    {"from": "proxy", "to": "replica", "status": "added"}
  ]
}
```

### 3. Course notes — what a CDN changes

```json
{
  "version": 1,
  "kind": "flow",
  "title": "Adding a CDN in front of a site",
  "nodes": [
    {"id": "user", "text": "Visitor", "role": "start"},
    {"id": "cdn", "text": "CDN edge", "status": "added"},
    {"id": "origin", "text": "Origin server", "status": "changed"}
  ],
  "edges": [
    {"from": "user", "to": "origin", "status": "removed"},
    {"from": "user", "to": "cdn", "status": "added"},
    {"from": "cdn", "to": "origin", "status": "added", "label": "cache misses only"}
  ]
}
```

## Fields

| Field | Where | Decision |
|---|---|---|
| `status` | `flow` and `tree` nodes and edges, optional | `added`, `changed`, `removed` — the `files` enum, reused verbatim. A node gets the `files` mark after its text; a removed node is drawn struck through in the `weak` treatment; an added edge carries a small `+` beside its label (or alone, mid-edge); a removed edge is drawn in the `aside` treatment with `−`. |
| key | automatic | If any status is used, a key of the statuses used is drawn under the figure, as `matrix` draws one. |

## Refused, and why

| Refused | Why |
|---|---|
| An unmarked or `added` edge touching a `removed` node | After the change the node is gone, so an edge to it must be going too. |
| An unmarked or `removed` edge touching an `added` node | An edge to something new is itself new: it must be `added`. |
| `status` in `cycle` | A loop that changes is a different loop; draw both. |
| Two panels (`before`, `after`) | Not offered. One drawing with marks is the point. |

## Acceptance tests to write

* The three documents render; each status mark is a text glyph plus word, not colour.
* Removed nodes struck through; removed edges dashed with no head.
* The consistency refusals above at the edge's pointer.
* The key lists exactly the statuses used.

## As built

Implemented as proposed, with these changes:

* **The node's mark is a tag inside the box, under its text**, not "after its
  text". A box is sized from its words, and a pill appended on the same line made
  every marked box wider than its peers for a word that is not part of its name.
  The tag is sized as one more line of the box's own text — so a diamond or a
  pill makes room for it the way it makes room for words — and drawn as the
  `files` pill in that line's place. It never turns a one-paragraph label into a
  bold lead over it; an author's or an actor's lead is kept.
* **Strike-through is a text decoration.** `files` draws its strike as a path
  over the name. Here it is `text-decoration="line-through"` on the line, so the
  renderer puts it at its own font's middle and `tools/collisions.py` does not
  read a deliberate line through the words as a defect.
* **A removed box is outlined in the `weak` treatment** (dashed, at the box's
  own corner radius) by tracing its shape as a path — a removed decision keeps its
  diamond — rather than switching its role, which would also change its shape.
* **Removal is drawn with a true minus sign, `−`.** Beside an edge, alone, a
  hyphen is a tick a quarter of an em long and reads as a flaw in the line. The
  `files` pill now uses the same glyph; its plain-text tree keeps ASCII `-`.
* **The key is drawn only when an edge is marked.** A marked box's tag already
  says its word, so a key repeating it says nothing new; a bare `+` on an edge is
  what needs one. When drawn, it lists exactly the statuses used, as tags.
* **Changed edges** take `~` before their label and keep their role; the
  proposal did not say.
* **One more refusal**: an edge between an added and a removed box ("the two
  never exist at the same time"). A `changed` edge touching a removed or an added
  box is refused with the unmarked case. `status` on a `matrix` edge is refused
  too: `edge` is one object shared with `matrix`, so the field is in its schema
  and the refusal is at validation, with the pointer.

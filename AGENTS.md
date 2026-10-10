# drawspec, for agents

You write a JSON document that says what a diagram **means**. drawspec decides
every coordinate. This file is meant to be read whole; it is the short version of
[`docs/format.md`](docs/format.md) and [`docs/guide.md`](docs/guide.md).

```bash
drawspec render diagram.json -o diagram.svg   # or to stdout
drawspec validate diagram.json                # every violation, with a JSON pointer
drawspec schema --out schema.json             # the full JSON Schema
```

**If your client speaks MCP**, `drawspec-mcp` serves the same three things as
tools — `validate`, `render`, `kinds` — and `validate`'s violations arrive as
`{"pointer": "/edges/0/to", "message": …}` rather than as text to read. Install
it with `pip install 'drawspec[mcp]'`; see [`docs/guide.md`](docs/guide.md).

## The one rule

**You may not write anything you would need to see the output to get right.**
No `x`, `y`, `width` on a box, `font_size`, `color`, `stroke`, `points`, `dx`,
`z` — 26 such fields are refused **by name**, each with the JSON pointer of where
you wrote it. That is not a restriction to work around; it is the whole design.
If you find yourself wanting a coordinate, the answer is a different `kind` or a
different `role`.

You *may* set `width` and `height` at the **top level** — a budget for the whole
canvas, not for one box.

## Every document

The smallest document that renders:

```json
{"version": 1, "kind": "flow", "nodes": [{"id": "a", "text": "A step"}]}
```

`version` (always `1`) and `kind` are required, and so is the payload the kind
selects — a `flow` with no `nodes` is refused rather than drawn empty. `title`,
`description` and `caption` are optional and always allowed. Add
`"$schema": "https://nuncaeslupus.github.io/drawspec/schema/drawspec-v1.schema.json"` for editor
completion.

`text` anywhere carries `**bold**` and `` `code` `` spans, and nothing else. A
newline in `text` means *this is a lead and a detail*, not one sentence.

## Should this be a diagram at all?

Draw only what a picture says better than prose. Things with no relation
between them are a bullet list; things with attributes are a table; one shape
or one step is a sentence. Ask whether a reader learns more from the picture
than from the paragraph you would otherwise write. If not, write the paragraph.

## Choosing a kind

Pick by what the reader must **understand**, not by what it looks like.

| The reader must understand… | Kind | Payload |
|---|---|---|
| How work moves, branches, merges or loops back | `flow` | `nodes` + `edges` |
| A hierarchy: what belongs to or reports to what | `tree` | `nodes` + `edges` |
| A loop that returns to where it started | `cycle` | `nodes` + `edges` closing the ring |
| Layers, each resting on the one below | `stack` | `items` |
| What happened when | `timeline` | `items` (+ `spans`) |
| How a few options differ, side by side | `columns` | `items` |
| A ranking or an ascent, where order is the point | `columns` or `timeline` + `"rise": true` | `items` |
| How rows relate to columns | `matrix` | `cells` (+ `rows`, `columns`, `edges`, `key`) |
| Levels where size means quantity or rank | `pyramid` | `levels` |
| Scopes nested inside scopes | `rings` | `rings` |
| What is lost between narrowing stages | `funnel` | `stages` |
| A small number you already know | `chart` | `axes` + `series` |
| Where items fall against two named judgements | `quadrant` | `axes` + `positions` |
| Where items fall by two measured values | `scatter` | `axes` + `positions` |
| The shape of a change: a hype cycle, a burndown | `curve` | `axes` + `curves` |
| What is in a directory | `files` | `entries` (+ `root`, `sort`, `style`) |

`flow` vs `tree`: a tree is a hierarchy and takes one edge per child; a flow may
branch, merge and loop back. `flow` vs `cycle`: a `cycle` must close a ring
through **every** node, and is refused if it does not.

**Keep it readable.** Each kind has a budget ([`docs/format.md`](docs/format.md#the-readability-budget);
a `flow`: 15 nodes, 16 edges). Past it a document is refused even though it
would fit: split it into an **overview** naming each part once, plus a
**detail** diagram per part. At most two elements may be `emphasis`.

## Roles

A role is semantic. The theme turns it into a shape and a weight — you never
name either.

**Nodes** — `start`, `step` (default), `decision`, `terminal`, `emphasis`,
`note`, `group`.
**Edges** — `flow` (default), `link`, `exchange`, `weak`, `owns`, `strong`,
`aside`.

Use `decision` for a question with branching answers, `note` for an aside that is
not a step, `link` for a connection with no direction.

**Who performs a step is not a role.** Use `actor` — free text on a node,
orthogonal to `role`, drawn as the box's lead so the names line up in a column:
`{"id": "approve", "text": "Sign off", "actor": "A release manager"}`. Do not
reach for `decision` to make a human step stand out; a diamond promises a branch.
A box has one lead, so a node with an `actor` may not also put a newline in its
`text`.

## Worked examples

A flow — `role` is the only appearance decision in the file:

```json
{
  "version": 1,
  "kind": "flow",
  "title": "Triaging a report",
  "nodes": [
    {"id": "arrive", "text": "A report arrives", "role": "start"},
    {"id": "repro", "text": "Does it reproduce?", "role": "decision"},
    {"id": "fix", "text": "Schedule a fix", "role": "step"},
    {"id": "ask", "text": "Ask for the document", "role": "terminal"}
  ],
  "edges": [
    {"from": "arrive", "to": "repro"},
    {"from": "repro", "to": "fix", "label": "yes"},
    {"from": "repro", "to": "ask", "label": "no"}
  ]
}
```

A chart — no colour is named; series are told apart by fill pattern too, so the
drawing survives greyscale:

```json
{
  "version": 1,
  "kind": "chart",
  "title": "Where the tickets went",
  "axes": {"horizontal": {"label": "Quarter", "min": 0, "max": 5},
           "vertical": {"label": "Incidents"}},
  "series": [
    {"name": "Platform", "mark": "bar", "data": [[1, 34], [2, 41], [3, 28]]},
    {"name": "Still open", "mark": "line", "data": [[1, 12], [2, 18], [3, 9]]}
  ]
}
```

## Containers

`groups` draws a frame around nodes — *these are inside this*. `bands` draws a
labelled bar alongside them — *this runs alongside these*. A box belongs to one
group or none, and to any number of bands.

An edge may name a **group** as well as a node, for a relation belonging to the
whole container rather than one box in it. It may not join a container to
something already inside it.

```json
{
  "version": 1,
  "kind": "flow",
  "nodes": [
    {"id": "api", "text": "The API"},
    {"id": "store", "text": "The store"},
    {"id": "watch", "text": "The monitoring platform", "role": "note"}
  ],
  "edges": [{"from": "watch", "to": "plane", "label": "watches"}],
  "groups": [{"id": "plane", "text": "The control plane", "members": ["api", "store"]}]
}
```

## When it refuses

A refusal is information, not an obstacle. Three kinds, and each tells you what
to do:

- **`DocumentError`** — a field is wrong or an id does not resolve. The message
  carries a JSON pointer (`/edges/2/to`). Fix that path. All violations are
  reported at once, so read them all before editing. A budget refusal
  (`… is past what one flow can be read at`) means split, not trim; an emphasis
  refusal means give all but one or two their ordinary role.
- **`FitError`** — the diagram does not fit its width in either direction. Shorten
  the longest label, split the diagram, or raise the top-level `width`. Do **not**
  try to shrink a gap; you cannot, and that is deliberate.
- **A refused field** — you wrote a coordinate or a style. Delete it; express the
  intent with `kind` or `role` instead.

Always run `drawspec validate` before claiming a document is done. It exits
non-zero and prints every problem.

## Do not

- Do not emit SVG yourself. The whole point is that you do not place anything.
- Do not add fields hoping they are ignored — unknown fields are errors.
- Do not use `chart` for exploring data. No statistics, dates, log scales or
  second axis. It states a number you already know.
- Do not use drawspec for anything whose point is *where things are* — a floor
  plan, a map. There is no declarative description of those.

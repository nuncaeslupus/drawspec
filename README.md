# drawspec

Declarative diagram spec → clean, themeable SVG. Writable by an LLM with no
coordinates to get wrong.

> **Status: it draws.** All thirteen kinds render — `flow`, `tree`, `cycle`,
> `stack`, `timeline`, `columns`, `matrix`, `pyramid`, `rings`, `funnel`,
> `chart`, `quadrant` and `curve` — and each of the eleven failure families
> below has a test asserting it cannot be expressed. The vocabulary opened from
> nine to thirteen on evidence: see `docs/kinds-wanted.md`, which sorts all 89
> hand-drawn originals by the kind that would have to draw them.

## The problem

Language models draw diagrams by emitting SVG with absolute `x`/`y`
coordinates, and they fail at the same things every time: arrows with a head
but no shaft, text that escapes its box, lines that stop short of the shape
they point at, a different font size in every element.

These are not failures of judgement. In a corpus of 87 LLM-written diagrams
reviewed by a human, **63 drew a complaint, and every one was about placement,
not content** — nobody disputed what the diagram said, only where things ended
up. See `docs/brief.md` for the measured breakdown.

Placement failures cannot be reviewed away: a cheap mechanical check over
finished SVG catches 17 of those 63 and misses 46. They have to be made
impossible to express.

## The approach

The author writes what the diagram *means* — nodes, edges, labels, and a
semantic role for each. Everything that can be got wrong without seeing the
result is not in the format at all:

| The author writes | The tool decides |
|---|---|
| Nodes, edges, labels | Coordinates, box sizes, canvas size |
| A semantic role per node | Font family and size, colour, stroke weight |
| Grouping and diagram type | Edge routing, anchor points, arrowheads |
| An optional size budget | Overlap resolution, label placement |

Output is SVG that can be pasted inline into a Markdown document: colour
inherited from the surrounding page, no global `<style>`, no ids that collide
when two diagrams share a page, and no information carried by colour alone —
so it survives dark mode and greyscale printing.

## What it looks like

Three documents and the drawings they produced. Nothing was positioned by hand,
and every one of these is a file in [`docs/reference/`](docs/reference) that
`make gallery` renders — so the picture is always the render of the spec beside
it.

### A flow

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

<p align="center">
  <img src="docs/gallery/flow-triage.svg" alt="A flow chart: a report arrives, is asked whether it reproduces, and is either scheduled for a fix or sent back for the document" width="460">
</p>

The `role` on each node is the only appearance decision in the file, and it is a
semantic one: `start` and `terminal` came out as pills and `decision` as a
diamond because *the theme* says those roles look like that. Change the theme and
every diagram in your project changes with it.

### A timeline

The thirteen kinds are the part people do not expect, so here is one that is not
a box-and-arrow diagram at all:

```json
{
  "version": 1,
  "kind": "timeline",
  "title": "How the work went",
  "items": [
    {"text": "Brief", "note": "March"},
    {"text": "Specification", "note": "April"},
    {"text": "Plan", "note": "May"},
    {"text": "Foundation", "note": "June to July"},
    {"text": "Kinds", "note": "August"}
  ]
}
```

<p align="center">
  <img src="docs/gallery/timeline-work.svg" alt="A timeline: brief, specification, plan, foundation and kinds, each with the month it happened below the axis" width="560">
</p>

Above the line is what happened; below it is when. That is what `note` means on a
timeline, and it is the only kind that draws one.

### A chart

```json
{
  "version": 1,
  "kind": "chart",
  "title": "Where the tickets went",
  "axes": {
    "horizontal": { "label": "Quarter", "min": 0, "max": 5 },
    "vertical": { "label": "Incidents" }
  },
  "series": [
    { "name": "Platform", "mark": "bar", "data": [[1, 34], [2, 41], [3, 28], [4, 22]] },
    { "name": "Service desk", "mark": "bar", "data": [[1, 52], [2, 47], [3, 55], [4, 38]] },
    { "name": "Still open", "mark": "line", "data": [[1, 12], [2, 18], [3, 9], [4, 6]] }
  ]
}
```

<p align="center">
  <img src="docs/gallery/chart-bars.svg" alt="A bar chart of two teams' incident counts over four quarters, with a line for the ones still open" width="560">
</p>

No colours are named anywhere in that file. The series are told apart by fill
pattern as well as by hue, which is what lets the same drawing survive greyscale
printing — a theme is checked against that invariant by `drawspec theme check`.

**There are no coordinates in any of them, and none may be written.** `x`,
`font_size`, `stroke` and twenty-odd other fields are refused by name, with the
JSON pointer of the place they were written. A document may size the whole canvas
— `width` and `height` at the top level — and may not size one box in it.

## Try it

```bash
pip install git+https://github.com/nuncaeslupus/drawspec   # not on PyPI yet

drawspec render diagram.json -o diagram.svg   # or to stdout
drawspec validate diagram.json                # every violation, by JSON pointer
drawspec theme check default                  # including the greyscale invariant
drawspec schema --out drawspec-v1.schema.json # for editor completion
```

Put `"$schema": "https://nuncaeslupus.github.io/drawspec/schema/drawspec-v1.schema.json"` at the top
of a document and any editor with JSON Schema support completes the fields and
flags a refused one *while you type it*, rather than after a render.

## The gallery

**[Every kind, drawn, on one page →](https://nuncaeslupus.github.io/drawspec/docs/gallery/)**

One document per kind lives in [`docs/reference`](docs/reference), and `make
gallery` renders every one of them into `docs/gallery/index.html`, which is what
that link publishes. It is the fastest way to see the whole vocabulary, and the
fastest way to see what a change did — looking at it is how four rendering
defects were found that no gate had caught.

It is committed as well as published, so a diff shows what a change did to the
pictures.

Every kind is drawn to the theme's one canvas width, and a diagram narrower than
it is centred in it rather than cropped to its own ink. That is what makes the
three above the same type size at the same column width — and it is the whole
reason the width belongs to the theme. Set `[canvas] width_mode = "ink"` for a
diagram meant to be sized on its own.

Every kind is also framed alike: `[canvas] margin` is the blank between the
drawing and the edge of the figure, one number applied in one place. Before it
existed each family invented its own, so a timeline above a flow chart bled to
the edge beside the flow's quarter-inch of white.

## What it is not

drawspec draws **simple, declarative diagrams well**, and it is the wrong tool
for several jobs it might look like it does.

* **It is not a Graphviz replacement.** Graphviz is a graph-layout engine with
  decades of work behind its layered and force-directed placement, and it will
  lay out a hundred-node graph that drawspec refuses. drawspec's layout exists
  to serve thirteen named diagram shapes at the sizes a document reads at; past
  roughly twenty boxes it will tell you it cannot fit rather than produce
  something dense and unreadable, which is deliberate but is not what a graph
  tool does.
* **It is not charting software.** `chart` has lines, bars, areas, stacks,
  point labels and a legend. It has no statistics, no interactivity, no dates,
  no log scales, no error bars, and no second axis. If you are exploring data,
  use a plotting library; if you are *stating* a small number you already know,
  this draws it in the same ink and at the same type size as every other
  diagram on the page, which a plotting library will not.
* **It is not a drawing program.** A document has no coordinates in it, on
  purpose — see *The approach* above. Anything whose whole point is where things are
  (a floor plan, a map, a picture of two overlapping Wi-Fi cells) has no
  declarative description, and drawspec should decline it rather than pretend.
* **It is not a rich-text system.** Text carries `**bold**` and `` `code` ``
  spans and nothing else.

What it is good at is the long tail of ordinary explanatory diagrams — the kind
that fills a set of course notes, a design document or a runbook — drawn
consistently, reviewably, and without an author ever choosing a coordinate.

## Documentation

[**The guide**](docs/guide.md) is the way in, and it is meant to be enough on its
own — install, a first diagram, choosing a kind, embedding the output, validating
in a build, and writing a theme. Under it sit three references, each **generated
from the code it describes**, so none of them can quietly go out of date:

| Page | What it answers |
|---|---|
| [The document format](docs/format.md) | Every field a document may carry, by kind — and every field that is refused, with the reason |
| [The command line](docs/cli.md) | Every command, argument and exit code |
| [The theme reference](docs/theme.md) | Every key a theme may set, and what the default sets it to |

`make docs` regenerates all three; a test fails if what is committed is not what
the code would write, which is the same arrangement the published JSON Schema
has.

### If you are an agent, or pointing one here

[**`AGENTS.md`**](AGENTS.md) is the whole format on one page — the rule, the
thirteen kinds, the roles, worked examples, and what each refusal is telling you
to do. It is written to be read in a single pass rather than navigated, which is
what the guide and the references are for. [`llms.txt`](llms.txt) is the index
that points at it.

It cannot drift either: a test asserts that every kind in the vocabulary is named
in it, that every role the theme declares appears, and that **every example in it
is a document that still validates**. An agent copying from a stale brief is the
failure that file exists to prevent, so it is held to the same standard as the
generated references.

## Repository layout

Everything you would look in, and the two directories you can ignore.

| Path | What |
|---|---|
| `src/` | The library and CLI — `src/drawspec/` is the whole of the shipped package |
| `docs/` | Everything written. The four entries below are the ones worth knowing apart |
| `docs/guide.md` | Using drawspec in another project: install, first diagram, embedding, theming |
| `docs/format.md`, `docs/cli.md`, `docs/theme.md` | The three generated references. `make docs` writes them; `tools/docs.py` is the generator |
| `docs/reference/` | One document per kind — the examples, and what the gallery and the acceptance suite both render |
| `docs/gallery/` | The rendered gallery: `make gallery` writes it, and it is committed so a diff shows what a change did to the pictures |
| `docs/brief.md` | The originating brief: the problem, the measured failure taxonomy, the acceptance tests. `theme-requirements.md`, `kinds-wanted.md` and the `plan-round-*.md` files sit beside it — the evidence each round was decided on |
| `schema/` | The published JSON Schema, versioned and addressable. Copied into the wheel from here, so there is only ever one of it |
| `corpus/` | 87 anonymized LLM-written diagrams and their measurements, as evidence |
| `tests/` | The suite. `test_acceptance.py` and `test_failure_families.py` are the two that encode the promises rather than the mechanics |
| `tools/` | Development scripts, not shipped: the docs generator, the gallery builder, and the two checkers — `collisions.py` (is the word readable) and `clipping.py` (is the word on the page) |
| `status/` | The origin documents: the specification this was built from, and its plan. Kept because `docs/brief.md` is the summary and this is the source, and because the session protocol reads `status/plan.md` |
| `.claude/`, `claude-arsenal/` | Development machinery for the agent workflow this is built with — task queue, session protocol, vendored skills. **Nothing here affects the package**; skip both if you are reading the project rather than working on it |

## Development

```bash
make sync     # install with dev extras
make lint     # ruff + strict mypy
make test     # pytest
make gallery  # render every reference document and look at it
make docs     # regenerate the format, CLI and theme references
make schema   # regenerate the published JSON Schema
```

## License

MIT — see `LICENSE`.

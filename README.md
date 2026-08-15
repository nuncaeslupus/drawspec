# drawspec

Declarative diagram spec → clean, themeable SVG. Writable by an LLM with no
coordinates to get wrong.

> **Status: it draws.** All thirteen kinds render — `flow`, `tree`, `cycle`,
> `stack`, `timeline`, `columns`, `matrix`, `pyramid`, `rings`, `funnel`,
> `chart`, `quadrant` and `curve` — and each of the eleven failure families
> below has a test asserting it cannot be expressed. The vocabulary opened from
> nine to thirteen on evidence: see `docs/kinds-wanted.md`, which sorts all 89
> hand-drawn originals by the kind that would have to draw them.

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
  purpose — see the table above. Anything whose whole point is where things are
  (a floor plan, a map, a picture of two overlapping Wi-Fi cells) has no
  declarative description, and drawspec should decline it rather than pretend.
* **It is not a rich-text system.** Text carries `**bold**` and `` `code` ``
  spans and nothing else.

What it is good at is the long tail of ordinary explanatory diagrams — the kind
that fills a set of course notes, a design document or a runbook — drawn
consistently, reviewably, and without an author ever choosing a coordinate.

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

## Try it

```bash
pip install git+https://github.com/nuncaeslupus/drawspec   # not on PyPI yet

drawspec render diagram.json -o diagram.svg   # or to stdout
drawspec validate diagram.json                # every violation, by JSON pointer
drawspec theme check default                  # including the greyscale invariant
drawspec schema --out drawspec-v1.schema.json # for editor completion
```

A document is what the diagram *means*:

```json
{
  "version": 1,
  "kind": "flow",
  "title": "Request validation",
  "nodes": [
    {"id": "arrive", "text": "Request arrives", "role": "start"},
    {"id": "shape", "text": "Is the payload well formed?", "role": "decision"},
    {"id": "queue", "text": "Queue for processing"},
    {"id": "reject", "text": "Reject with a reason the caller can act on", "role": "terminal"}
  ],
  "edges": [
    {"from": "arrive", "to": "shape"},
    {"from": "shape", "to": "queue", "label": "well formed"},
    {"from": "shape", "to": "reject", "label": "malformed"}
  ]
}
```

There are no coordinates in it, and none may be written: `x`, `font_size`,
`stroke` and twenty-odd other fields are refused by name, with the JSON pointer
of the place they were written. A document may size the whole canvas — `width`
and `height` at the top level — and may not size one box in it.

## The gallery

One document per kind lives in `docs/reference`, and `make gallery` renders every
one of them into a single page — `docs/gallery/index.html` — which is the
fastest way to see what changed. Looking at that page is how four rendering
defects were found that no gate had caught.

Every kind is drawn to the theme's one canvas width, and a diagram narrower than
it is centred in it rather than cropped to its own ink. That is what makes the
two below the same type size at the same column width — and it is the whole
reason the width belongs to the theme. Set `[canvas] width_mode = "ink"` for a
diagram meant to be sized on its own.

<p align="center">
  <img src="docs/gallery/flow-validation.svg" alt="A flow chart: a request arrives, is validated, and is either queued or rejected" width="420">
  <br>
  <img src="docs/gallery/tree-decisions.svg" alt="A tree: which decisions belong to the author, the theme and the tool" width="420">
</p>

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

## Repository layout

| Path | What |
|---|---|
| `docs/guide.md` | Using drawspec in another project: install, first diagram, embedding, theming |
| `docs/format.md`, `docs/cli.md`, `docs/theme.md` | The three generated references. `make docs` writes them; `tools/docs.py` is the generator |
| `docs/brief.md` | The originating brief: the problem, the measured failure taxonomy, the acceptance tests |
| `docs/theme-requirements.md` | A real consumer's style rules — the worked example of what a theme must express |
| `docs/plan-round-three.md` | What a consumer's corpus could not express, checked against the code, sized and ordered |
| `corpus/` | 87 anonymized LLM-written diagrams and their measurements, as evidence |
| `docs/reference/` | One document per kind — the examples, and what the gallery and the acceptance suite both render |
| `docs/gallery/` | The rendered gallery: `make gallery` writes it, and it is committed so a diff shows what a change did to the pictures |
| `schema/` | The published JSON Schema, versioned and addressable |
| `src/drawspec/` | The library and CLI |

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

# drawspec

Declarative diagram spec → clean, themeable SVG. Writable by an LLM with no
coordinates to get wrong.

> **Status: it draws.** All nine kinds render — `flow`, `tree`, `cycle`,
> `stack`, `timeline`, `columns`, `pyramid`, `rings` and `chart` — and each of
> the eleven failure families below has a test asserting it cannot be expressed.

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
pip install drawspec

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

There are no coordinates in it, and none may be written: `x`, `width`,
`font_size`, `stroke` and twenty other fields are refused by name, with the
JSON pointer of the place they were written.

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

## Repository layout

| Path | What |
|---|---|
| `docs/brief.md` | The originating brief: the problem, the measured failure taxonomy, the acceptance tests |
| `docs/theme-requirements.md` | A real consumer's style rules — the worked example of what a theme must express |
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
```

## License

MIT — see `LICENSE`.

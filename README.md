# drawspec

Declarative diagram spec → clean, themeable SVG. Writable by an LLM with no
coordinates to get wrong.

> **Status: specification.** No renderer yet. The problem, the evidence and the
> acceptance tests are in place; the design is being written.

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

## Repository layout

| Path | What |
|---|---|
| `docs/brief.md` | The originating brief: the problem, the measured failure taxonomy, the acceptance tests |
| `docs/theme-requirements.md` | A real consumer's style rules — the worked example of what a theme must express |
| `corpus/` | 87 anonymized LLM-written diagrams and their measurements, as evidence |
| `src/drawspec/` | The library and CLI |

## Development

```bash
make sync     # install with dev extras
make lint     # ruff + strict mypy
make test     # pytest
```

## License

MIT — see `LICENSE`.

# <img src="https://raw.githubusercontent.com/nuncaeslupus/drawspec/main/docs/logo.png" width="40" height="40" alt="" align="top"> drawspec

<!-- mcp-name: io.github.nuncaeslupus/drawspec -->

[![PyPI](https://img.shields.io/pypi/v/drawspec)](https://pypi.org/project/drawspec/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![drawspec MCP server – quality and maintenance score on Glama](https://glama.ai/mcp/servers/nuncaeslupus/drawspec/badges/score.svg)](https://glama.ai/mcp/servers/nuncaeslupus/drawspec)
<!-- claude-arsenal:attribution: added by claude-arsenal's /init. Delete this block to drop it (it is not put back), or set `attribution = false` in the arsenal config.toml. -->
[![Built with claude-arsenal](https://img.shields.io/badge/built%20with-claude--arsenal-d97756)](https://github.com/nuncaeslupus/claude-arsenal)
<!-- /claude-arsenal:attribution -->

**Diagrams from a JSON description — no coordinates, so nothing to misplace.**
You say what the diagram *means*: the boxes, the arrows, the labels, and a role
for each. drawspec decides every position, size, route and colour, and draws a
clean SVG, PNG or plain-text diagram.

It is built for language models first. An LLM that writes SVG by hand gets the
content right and the placement wrong — arrows that miss their boxes, text that
spills out, lines that stop short. A drawspec document has no `x`, `y` or font
size to get wrong: those fields are refused, and every mistake comes back as an
error pointing at the exact field, so the model can fix it and try again.

```bash
pip install drawspec
drawspec render diagram.json -o diagram.svg
```

**[Browse the gallery: all 36 kinds, drawn →](https://nuncaeslupus.github.io/drawspec/docs/gallery/)**

## Example

You write this:

```json
{
  "$schema": "https://nuncaeslupus.github.io/drawspec/schema/drawspec-v1.schema.json",
  "version": 1,
  "kind": "flow",
  "title": "The nightly import",
  "description": "The vendor's export is fetched, checked and loaded into staging before it replaces the live table; a timeout and a deadlock are each retried in place.",
  "nodes": [
    {"id": "fetch", "text": "Fetch the vendor's export", "role": "start"},
    {"id": "check", "text": "Do the row counts match?", "role": "decision"},
    {"id": "load", "text": "Load into staging"},
    {"id": "page", "text": "Page the data owner", "role": "terminal"},
    {"id": "swap", "text": "Swap staging into live", "role": "terminal"}
  ],
  "edges": [
    {"from": "fetch", "to": "fetch", "label": "timed out: retry"},
    {"from": "fetch", "to": "check"},
    {"from": "check", "to": "load", "label": "yes"},
    {"from": "check", "to": "page", "label": "no"},
    {"from": "load", "to": "load", "label": "deadlock: retry"},
    {"from": "load", "to": "swap"}
  ]
}
```

drawspec draws this:

<p align="center">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/readme/flow-retry-dark.png">
  <img src="docs/readme/flow-retry-light.png" alt="A flow chart: fetch the vendor's export, retried on timeout; check the row counts; on a match load into staging, retried on deadlock, then swap into live; otherwise page the data owner" width="620">
</picture>
</p>

The same document as text, for a terminal, a commit message or a code block
(`--format text --charset ascii`):

```text
             *---------------------------*
             | Fetch the vendor's export +-+ timed out: retry
             |                           |<+
             *-------------+-------------*
                           |
                           v
                       +--------------------------+
                       < Do the row counts match? >
                       ++-------------------+-----+
                        | yes               | no
                   +----+                   |
                   v                        v
+-------------------+                      .---------------------.
| Load into staging +-+ deadlock: retry    ( Page the data owner )
|                   |<+                    '---------------------'
+---------+---------+
          |
          v
       .------------------------.
       ( Swap staging into live )
       '------------------------'
```

A sequence diagram works the same way — participants and messages in order;
activation bars, arrows and spacing are worked out for you:

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

<p align="center">
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/readme/sequence-dns-dark.png">
  <img src="docs/readme/sequence-dns-light.png" alt="A sequence diagram: a laptop asks a recursive resolver, which asks the root, the .org server and the authoritative server in turn, caches the answer and replies" width="720">
</picture>
</p>

## 36 kinds of diagram

Flow charts, sequence diagrams, state machines, ER and class diagrams, Gantt
charts, swimlanes, mind maps, timelines, Venn, Sankey, treemaps, pie and bar
charts, kanban boards, fishbone, family trees, file trees and more — one format
for all of them. Click a drawing for its source.

<table>
<tr>
<td align="center" width="33%">
<a href="docs/reference/sequence-checkout.json"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/readme/sequence-checkout-dark.png"><img src="docs/readme/sequence-checkout-light.png" alt="A checkout sequence diagram with alt and par fragments"></picture></a><br>
<sub><code>sequence</code></sub>
</td>
<td align="center" width="33%">
<a href="docs/reference/entities-orders.json"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/readme/entities-orders-dark.png"><img src="docs/readme/entities-orders-light.png" alt="A database schema of customers, orders and order lines with crow's-foot ends"></picture></a><br>
<sub><code>entities</code></sub>
</td>
<td align="center" width="33%">
<a href="docs/reference/states-ticket.json"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/readme/states-ticket-dark.png"><img src="docs/readme/states-ticket-light.png" alt="A support ticket state machine"></picture></a><br>
<sub><code>states</code></sub>
</td>
</tr>
<tr>
<td align="center" width="33%">
<a href="docs/reference/gantt-migration.json"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/readme/gantt-migration-dark.png"><img src="docs/readme/gantt-migration-light.png" alt="A migration plan as a Gantt chart with phases and milestones"></picture></a><br>
<sub><code>gantt</code></sub>
</td>
<td align="center" width="33%">
<a href="docs/reference/mindmap-offsite.json"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/readme/mindmap-offsite-dark.png"><img src="docs/readme/mindmap-offsite-light.png" alt="A mind map planning a team offsite"></picture></a><br>
<sub><code>mindmap</code></sub>
</td>
<td align="center" width="33%">
<a href="docs/reference/sankey-budget.json"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/readme/sankey-budget-dark.png"><img src="docs/readme/sankey-budget-light.png" alt="A Sankey diagram of where a budget goes"></picture></a><br>
<sub><code>sankey</code></sub>
</td>
</tr>
<tr>
<td align="center" width="33%">
<a href="docs/reference/venn-telemetry.json"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/readme/venn-telemetry-dark.png"><img src="docs/readme/venn-telemetry-light.png" alt="A three-set Venn diagram of logs, metrics and traces"></picture></a><br>
<sub><code>venn</code></sub>
</td>
<td align="center" width="33%">
<a href="docs/reference/chart-bars.json"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/readme/chart-bars-dark.png"><img src="docs/readme/chart-bars-light.png" alt="A bar and line chart of incidents per quarter"></picture></a><br>
<sub><code>chart</code></sub>
</td>
<td align="center" width="33%">
<a href="docs/reference/fishbone-flaky-ci.json"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/readme/fishbone-flaky-ci-dark.png"><img src="docs/readme/fishbone-flaky-ci-light.png" alt="A fishbone diagram of causes of a flaky CI"></picture></a><br>
<sub><code>fishbone</code></sub>
</td>
</tr>
</table>

The full list: `flow` · `tree` · `cycle` · `stack` · `timeline` · `columns` ·
`matrix` · `pyramid` · `rings` · `funnel` · `chart` · `quadrant` · `scatter` ·
`curve` · `files` · `states` · `sequence` · `lanes` · `entities` · `gantt` ·
`board` · `fishbone` · `venn` · `journey` · `treemap` · `sankey` · `numberline` ·
`barmodel` · `waterfall` · `pie` · `mindmap` · `argument` · `familytree` ·
`meter` · `rag` · `clock`. Each has an example in [`docs/reference`](docs/reference),
and [the gallery](https://nuncaeslupus.github.io/drawspec/docs/gallery/)
(`docs/gallery/index.html`) draws every one.

## Using it from an LLM

- **MCP server** — `pip install 'drawspec[mcp]'` adds `drawspec-mcp`, with the tools
  `list_kinds`, `get_example`, `get_schema`, `validate_document` and
  `render_document`. A mistake comes back as data the model can act on:
  `{"pointer": "/edges/0/to", "message": …}`.
  See [the guide](docs/guide.md#using-it-from-an-agent-the-mcp-server).
- **[`AGENTS.md`](AGENTS.md)** — the whole format on one page, written for a model to
  read in one pass: which kind fits, the size limits, the roles, worked examples, and
  what each error means. [`llms.txt`](llms.txt) indexes it.
- **Agent Skill** — copy [`skills/drawspec/`](skills/drawspec/SKILL.md) into your
  skills directory.
- **JSON Schema** — start a document with
  `"$schema": "https://nuncaeslupus.github.io/drawspec/schema/drawspec-v1.schema.json"`
  for completion and errors as you type, in an editor or a structured-output call.

A typical loop: the model picks a kind, writes the JSON, calls
`validate_document`, fixes what is reported, and renders.

## What you get

| You write | drawspec decides |
|---|---|
| Nodes, edges, labels | Coordinates, box sizes, canvas size |
| A semantic role per node (`start`, `decision`, `emphasis`…) | Shape, font, colour, stroke weight |
| The kind of diagram | Layout, edge routing, arrowheads, label placement |

- **SVG** that pastes inline into Markdown or HTML: it takes the page's text colour,
  carries no global styles or colliding ids, and never relies on colour alone, so it
  works in dark mode and in greyscale print. `--variant dark=<theme>` adds a dark
  version that follows `prefers-color-scheme`.
- **PNG** on a light, dark or transparent background (`pip install 'drawspec[png]'`).
- **Plain text** (box-drawing or ASCII) for twelve kinds, including flows, state
  machines, sequences, Gantt charts and file trees.
- **Themes**: change one TOML file and every diagram in a project follows.
  `drawspec theme from site.css` builds one from your CSS or design tokens.
- **Readable by design**: each kind has a size budget (15 boxes for a `flow`);
  past it, drawspec asks you to split the diagram rather than draw a dense one.

## Command line

```bash
drawspec render diagram.json -o diagram.svg          # or to stdout
drawspec render diagram.json -o diagram.png          # needs drawspec[png]; --background dark, --scale 3
drawspec render diagram.json --theme blueprint -o sheet.png
drawspec render diagram.json --format text           # 80 columns; --charset ascii
drawspec validate diagram.json                       # every error, by JSON pointer
drawspec theme from site.css -o house.toml           # a theme from your CSS
drawspec schema --out drawspec-v1.schema.json        # for editor completion
```

## What it is not

- **Not a graph-layout engine.** For a hundred-node graph, use Graphviz.
- **Not a plotting library.** `chart` states a few numbers you already know; it has
  no statistics, dates, log scales or interactivity.
- **Not a drawing program.** Anything whose point is *where* things are — a floor
  plan, a map — has no place in a format without coordinates.

## Documentation

| Page | What it covers |
|---|---|
| [Guide](docs/guide.md) | Install, a first diagram, choosing a kind, embedding, validating in CI, themes |
| [Document format](docs/format.md) | Every field of every kind, and every refused field with the reason |
| [Command line](docs/cli.md) | Every command, option and exit code |
| [Themes](docs/theme.md) | Every theme key and its default |
| [AGENTS.md](AGENTS.md) | The format on one page, for language models |

The references are generated from the code (`make docs`), and a test fails if they
drift.

## Development

```bash
make sync     # install with dev extras
make lint     # ruff + strict mypy
make test     # pytest
make gallery  # render every reference document into docs/gallery
make readme   # redraw the README's example images in docs/readme
make docs     # regenerate the format, CLI and theme references
make schema   # regenerate the published JSON Schema
```

The library is in `src/drawspec/`, the examples in `docs/reference/`, the tests in
`tests/`. `docs/brief.md` and `corpus/` hold the original design brief and the
evidence it was based on. `.claude/` and `claude-arsenal/` are development tooling
and do not affect the package.

## Related projects

Built with [claude-arsenal](https://github.com/nuncaeslupus/claude-arsenal), a
spec-driven Claude Code workflow whose skills draw their diagrams with drawspec.
By the same author:

- [integral-job-search](https://github.com/nuncaeslupus/integral-job-search) — a candidate-centred job search run as a conversation in Claude Code.
- [literary-critic](https://github.com/nuncaeslupus/literary-critic) — lets an LLM index, analyse and advise on a full novel manuscript the way a professional editor would.
- [doc-control](https://github.com/nuncaeslupus/doc-control) — a deterministic tool for AI agents to edit Word documents as tracked changes (in development).

## License

MIT — see [`LICENSE`](LICENSE).

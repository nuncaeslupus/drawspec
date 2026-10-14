# Proposal: text output — diagrams as plain text for code blocks and terminals

Status: **phase 1 built** (see *As built* at the end); phase 2 accepted — tasks `t-f26679ad` (phase 1) and `t-5355943b` (phase 2). Size **M** for phase 1 (one emitter, eight kinds that already sit
on a grid), **L** for phase 2 (graph kinds, which need a character-grid router).
Depends on an owner decision: which phase, and whether the evidence below is enough.

## Why

drawspec's place is docs, specs and READMEs. A lot of those are read where no picture
draws: a terminal (`cat README.md`, `git log`, `man`), a code comment, a commit
message, an issue in a mail client, a chat that strips images, and — increasingly — the
context window of a language model, which reads `├──` and `──▶` but not an SVG's path
data. Today only `files` has a text form (`render --format text`, `.txt`), and every
other kind refuses with *"Render it as SVG."*

The usual workaround is an ASCII diagram drawn by hand, which is exactly the
"arrows that miss their boxes" problem drawspec exists to remove, only in characters.

This is **an output format, not a kind**: the same document, a second emitter. It adds
no vocabulary to the format and nothing an author has to learn.

## Prior art surveyed

| Tool | What it taught |
|---|---|
| Unix `tree`, drawspec `files` | box-drawing guides; `--charset=ascii` as a fallback, not a separate style |
| PlantUML `-ttxt` / `-utxt` | sequence diagrams are the kind that survives text best: lifelines are columns, messages are rows |
| Graph::Easy `as_ascii` / `as_boxart` | layered graphs on a cell grid work up to ~15 nodes; past that, crossings make it unreadable |
| `mermaid-ascii` | the same limit for flowcharts; long labels widen every cell in a rank |
| Diagon | per-kind text layouts (sequence, tree, table, flowchart) beat one generic rasteriser |
| svgbob | the reverse direction (text → SVG); shows which glyphs readers take as lines and arrowheads |

The lesson they agree on: **lay out per kind on a character grid; never rasterise the
SVG scene into cells.** A scene's coordinates are in points, its text is proportional,
and rounding both to cells produces collisions the SVG layout carefully avoided.

## Design

### Shape of it

* `render --format text` and `-o diagram.txt` already exist; they stop refusing for the
  kinds below. The MCP `render` tool takes the same `format`.
* `drawspec.render.render_text(document, *, width=80, charset="unicode")` gains the two
  keyword arguments; the CLI exposes them as `--width` and `--charset unicode|ascii`.
  For `files`, `style: "ascii"` keeps selecting the ASCII charset, so nothing changes there.
* **Each kind that has a text form owns a `text(document, width, charset)` function** next
  to its layout, reusing that layout's *topology* (ranks, order, rows, columns, intervals)
  but never its coordinates.
* **A kind without a text form refuses**, as today, naming the kinds that have one.
* **A drawing that does not fit `width` is refused**, at the pointer of the widest thing
  (the label, the column count), with the width it needs — the same rule as the SVG
  canvas. Text never wraps a box mid-word or truncates a label silently.

### Roles without colour

Text has no ink or weight to spend, so roles map to glyphs. The SVG's greyscale test
already requires roles to stay distinct without colour; text is the same promise, made
with characters.

| Role | Unicode | ASCII |
|---|---|---|
| plain box | `┌─┐ │ └─┘` | `+-+ \| +-+` |
| `emphasis` | heavy `┏━┓ ┃ ┗━┛` | `#=#` |
| `terminal` | rounded `╭─╮ ╰─╯` | `( )` ends |
| edge / arrow | `─ │ ──▶` | `- \| -->` |
| `strong` edge | `━ ┃ ━━▶` | `= ‖ ==>` |
| dashed / async | `┄ ┆ ┄┄▷` | `. : ..>` |
| `status` added / changed / removed | `+ ~ -` prefix, as `files` already does | same |

### Phase 1 — kinds that already sit on a grid (M)

Each is rows and columns before it is a picture, so its text form is a direct reading of
its layout:

| Kind | Text form |
|---|---|
| `tree` | `files`' guides, labels in boxes or bare by `style` |
| `sequence` | one column per participant, one row per message, `──▶` / `◀┄┄` for call and reply, activation as `┃` on the lifeline |
| `gantt` | one row per task, a bar of `█` (`#`) on a numbered axis; milestones `◆` (`*`); phases as header rows |
| `timeline` | the axis vertical: one row per entry, `at` in a left column |
| `board` | columns of cards, WIP limits in the header (`Doing 2/3`) |
| `stack` | layers as stacked boxes, full width |
| `rag` | a table: workstream, the word (`RED`), the shape letter, the trend in words — already how it reads |
| `meter` | `progress` style only: `[██████░░░░] 60 %` |

### Phase 2 — graph kinds (L)

`flow`, `states`, `lanes`, `tree` with cross-links: the layered engine's rank and order,
placed on a cell grid, edges routed orthogonally through free cells with `┼` only where
two edges genuinely cross. A **text budget** stricter than the SVG one (say 15 nodes,
3 crossings) refuses what would print as noise, pointing at SVG.

### Never

Kinds whose message is area, angle or curve: `pie`, `venn`, `treemap`, `sankey`,
`curve`, `scatter`, `clock`, `journey`, `chart`. A pie in characters is a picture of a
pie, not the pie's information; a reader is better served by the data as a table, which
the document already is.

## Tests (gates)

* `text_overflow_lines == 0`: no line wider than `width`, measured in **terminal cells**
  (East Asian wide characters count 2, via `unicodedata.east_asian_width` — no new
  dependency).
* Every label in the document appears verbatim in the output (nothing truncated).
* `--charset ascii` output is bytes < 128 only.
* No trailing whitespace on any line; output ends in one newline.
* Each role in the table above stays distinguishable: two fixtures differing only in a
  role produce different text.
* A golden file per phase-1 kind per charset, reviewed by eye once, then held.
* The refusal for a non-text kind names the kinds that have a text form.

## Owner decisions

1. **Evidence:** enough; no text corpus round first.
2. **Scope:** both phases; phase 2 queued behind phase 1.
3. **Width:** default 80. Graph kinds are the risk: phase 2 measures how many reference
   flows fit at 80 / 100 / 120 before the default is settled, and proposes a per-kind
   default if 80 refuses too many. `--width` always overrides.

## As built

Phase 1, as `drawspec.textgrid` (cells, boxes, the junction grid, the one too-wide
refusal) and a `<kind>_text(document, width, charset)` beside each kind's layout,
dispatched by `drawspec.kinds.TEXT_FORMS`. Gated by `tests/test_text_output.py`: every
reference document of the nine kinds, in both charsets, plus a golden file per kind
per charset under `tests/golden/text/`. What changed or was decided:

* **Measured at 80:** every phase-1 reference document fits except four, which refuse
  at 80 naming the width they need — `sequence-async-export` (83), `sequence-drain`
  (85), `sequence-dns` (93) and `board-onboarding` (88, five columns and the word
  *Thirty-minute*). The test lists them; the width a refusal names is checked to be
  enough. A sequence too wide is first tried with its heads, labels and notes wrapped
  narrower, as the SVG's is.
* **`start` is a double box** (`╔═╗`, ASCII `*-*`). The table gave `terminal` the rounded
  one, and `start` — a thinner pill in the SVG — must not draw like it.
* **An `async` message is `──▷`, a `weak` reply `┄┄▷`:** the default theme draws `async`
  solid with an open head and `weak` dashed with one, so the table's single "dashed /
  async" row is split. In ASCII the open head is `>>`.
* **`gantt` bars are filled by role**, lighter to heavier (`░ ▒ ▓ █`, ASCII `. = # @`),
  the undone part of a `done` bar dotted, and **dependencies are not drawn**: a
  finish-to-start line routed through cells would cross the bars it joins, and the
  bars' order already says it.
* **`rag` uses the default theme's words and shapes** (`■ RED`, `▲ AMBER`, `● GREEN`,
  ASCII `# ^ o`): text has no theme. **`meter` is `bar` only**, `[█████░░░│░░]`, the
  target a bar across the track, the readout's lines under one another; `thermometer`,
  `dial` and `bullet` refuse.
* **`tree`** draws its boxes on `files`' guides, a class named after its box and an
  edge's label on its stub; a tree with cross-links, a cycle, groups or bands refuses,
  as phase 2's work.
* **A `timeline` is drawn down the page** with even rows, not spaced by `at`; a span is
  a bracket in a lane beside the entries, each lane with its own column for its names.
* **ASCII spells** the common punctuation (`→` as `->`, `—` as `--`, accents dropped)
  and refuses a character with no spelling, at its pointer.
* **`files` is unchanged** byte for byte, except that a tree wider than `--width` is now
  refused like every other text drawing.

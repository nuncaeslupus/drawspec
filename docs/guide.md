# Using drawspec

This is the page to read if you want to *use* drawspec in another project — put
it in a dependency list, write documents against it, give it a theme that
matches your house style, and get SVG out that survives being pasted into your
pages. It is meant to be enough on its own: nothing here asks you to read the
source.

Three reference pages sit under it, each generated from the code it describes,
so none of them can quietly go out of date:

* **[The document format](format.md)** — every field a document may carry, by
  kind, and every field that is refused.
* **[The command line](cli.md)** — the commands, their arguments and the exit
  codes.
* **[The theme reference](theme.md)** — every key a theme may set, and what the
  default sets it to.

---

## Install

drawspec is a pure-Python package. It needs Python 3.12 or newer and pulls in
one dependency, `fonttools`.

```bash
pip install drawspec
# or, with uv:
uv add drawspec
```

Extras: `drawspec[png]` for PNG export, `drawspec[mcp]` for the MCP server.

There is **no system dependency** — no Graphviz, no Cairo, no headless browser,
nothing to apt-get in a CI image. That is a deliberate acceptance criterion
rather than a happy accident: a diagram tool that needs a C toolchain installed
is one that gets dropped from the build the first time the build breaks.

The fonts it measures against are bundled and subsetted, so a container with no
fonts installed measures text the same way your laptop does. Naming a family
that is not available is not an error — drawspec substitutes the nearest bundled
family and says so on stderr.

Check it:

```bash
drawspec --version
```

## Your first diagram

A document says what the diagram **means**. Write `diagram.json`:

```json
{
  "$schema": "https://nuncaeslupus.github.io/drawspec/schema/drawspec-v1.schema.json",
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

Then:

```bash
drawspec render diagram.json -o diagram.svg
```

There is no coordinate in that document, and none may be written. `x`,
`font_size`, `stroke` and twenty-odd other names are refused *by name*, with the
JSON pointer of the place they were written — see
[what may not be written](format.md#what-may-not-be-written). That refusal is
the whole design: the failures this tool exists to prevent are placement
failures, and a format that cannot express a position cannot express a wrong
one.

What a document *may* size is the canvas: `width` and `height` at the top level
are a budget for the whole drawing, and the same names on a node are refused,
because how big one box is follows from its text and the theme's padding.

### The one placement you do control: which comes first

No document names a position, but the *order* it writes things in is content,
and drawspec reads it. Where two boxes end up on the same rank — three children
of one parent, four members of a group, a row of boxes nothing connects — they
are drawn in the order the document lists them, left to right or top to bottom
as the direction requires. The same goes for a group's `members`.

It is a tie-break, not an override. An edge that would cross still moves a box:
the layout reduces crossings first and reads your order only where that leaves
it a free choice — which, for a fan of siblings, is every time.

So write a list in the order it is meant to be read. If the subject lists three
bodies in a fixed order, and the reader will be asked about them in that order,
that order is part of the diagram and the document is where it goes.

### A box with a lead and a detail

Labels often carry two things: a name, and what the name means. Write them as
two paragraphs, with a newline between:

```json
{"id": "digitise", "text": "Digitisation\nchanges the medium, not the process"}
```

The theme sets the first paragraph in bold and leaves the rest alone. Do not
punctuate the two apart on one line — `**Digitisation** — changes the medium`
puts a typographic decision in the document, and reads as a dash rather than as
two levels, which is exactly what the corpus review objected to. A theme may
switch the treatment off with `[box] lead = "plain"`; the break stays either
way, because a break is structure.

The third treatment is a **rule** between the two, and it is for the case where
the second part is not an explanation but a *list of things belonging to* the
first — the attributes of a class, the fields of a record, the members of a
team, who performs a step. Weight would say "this one matters more", which is
not what those diagrams mean; a line says "this is the heading of those", which
is what every hand-drawn class box already does. The bundled `compartment` theme
is `default` plus that one setting, and `docs/reference/tree-compartments.json`
is what it looks like:

```json
{"id": "card", "text": "**Card payment**\nlast four digits\nscheme"}
```

Still no new field — the same newline, read the same way. The rule is drawn in
the box's own ink and runs edge to edge, stopping on the sloped sides of a
diamond rather than coming out of them.

The `$schema` line is optional and costs nothing at render time, but it earns
its place in an editor: point any JSON-Schema-aware editor at it and you get
completion over the field names and an inline error on `font_size` *while you
are typing it*, rather than after a render.

## Choosing a kind

The `kind` is the first thing to get right, because it decides which other
fields are legal. Twenty-six exist, and they fall into fifteen families:

| Family | Kinds | What they are for |
|---|---|---|
| Graph | `flow`, `tree`, `cycle`, `lanes` | Things connected to other things: a process, a hierarchy, a loop that comes round again, a process drawn in one strip per party. |
| Grid | `stack`, `timeline`, `columns`, `matrix` | Things in an arrangement: layers, events in order, side-by-side comparison, rows against columns. |
| Shape | `pyramid`, `rings`, `funnel` | Things in a proportion: levels narrowing to an apex, scopes nested inside scopes, stages narrowing to an outcome. |
| Plot | `chart`, `quadrant`, `scatter`, `curve` | Things with numbers: series against axes, items placed in a plane, points by two measured values, a named shape with labelled waypoints. |
| Listing | `files` | Things in folders: a directory tree from its paths, drawn with pictures or as `tree`-style text (`drawspec render --format text`). |
| Machine | `states` | Things that change state: the conditions something can be in, and the events that move it between them. |
| Exchange | `sequence` | Things said in order: messages between a fixed set of participants, read down the page. |
| Model | `entities` | Things with fields, and how they relate: an ER model, a database schema, a class diagram. |
| Plan | `gantt` | Things that take time: one row per task, each an interval, with phases, milestones and what waits on what. |
| Board | `board` | Things sorted, not joined: cards in columns — a kanban board, a retrospective, a story map sliced into releases. |
| Cause | `fishbone` | Things that led to one effect: causes by category on bones slanting into a spine — a root-cause (Ishikawa) diagram. |
| Overlap | `venn` | Things that share: two or three sets as equal circles, each region named by the sets it is in. |
| Experience | `journey` | How one person feels, stage by stage: a named feeling per stage as a line, over what they do there. |
| Share | `treemap` | The parts of one known total: each a rectangle by its area, labelled inside itself. |
| Quantity | `sankey` | Where a known quantity goes: nodes in derived columns, joined by bands as thick as their amounts. |

One worked document per kind lives in [`reference/`](reference), and `make
gallery` renders all of them onto one page. That page is the fastest way to see
what a kind actually looks like before committing a document to it.

Two notes worth having before you pick — and one question before both: **should
this be a diagram at all?** Things with no relation between them are a bullet
list, things with attributes are a table, and one shape or one step is a
sentence. A diagram earns its place when a reader learns more from it than from
the paragraph it replaces. [`AGENTS.md`](../AGENTS.md) carries the same question
and a table that routes from *what the reader must understand* to the kind.

* **Read what the original is saying, not what it looks like.** A
  shared-responsibility diagram that looks like a grid is usually *how much of
  each column* is one party versus the other — a stacked proportion, not a
  matrix. Choosing `matrix` for it invents semantic rows the subject never had.
* **Some diagrams are not drawspec's job**, and it is better to say so than to
  approximate. Anything whose whole point is *where things are* — a floor plan,
  a map, two overlapping Wi-Fi cells — has no declarative description.
  [`kinds-wanted.md`](kinds-wanted.md) is the inventory that decided which kinds
  exist and which requests were declined.

### How much one diagram may hold

Each kind has a **readability budget** — at most 15 nodes and 16 edges on a
`flow`, 8 steps on a `cycle`, 6 `columns`, and so on; the whole table is in
[the format reference](format.md#the-readability-budget). Past it, `drawspec
validate` refuses the document with the pointer of the first entry over, even
though the drawing would fit: a picture of twenty boxes is searched, not read.

The fix is never a bigger canvas — `width` does not lift the budget — but a
split: an **overview** that names each part once, plus a **detail** diagram per
part. The numbers were measured against the reference documents and the corpus,
so every diagram in the gallery is inside them with room to spare.

## Choosing a role

*"I don't know what criteria you use to choose between circle and rectangle
here"* — asked three times in one review, which means the answer was never
written down. Here it is.

**A role says what a box is; the theme decides what that looks like.** So the
question to ask is never "should this be a diamond" — it is "is this a
question?". These are the seven, and the shape each one currently gets from the
bundled theme:

| Role | Use it for | Drawn as |
|---|---|---|
| `step` | The ordinary box. **The default, and most boxes should be one.** | a rectangle |
| `start` | Where the diagram begins — the trigger, the arrival, the input | a pill |
| `terminal` | Where it ends. Not "the last box": the box after which nothing happens | a pill, heavier |
| `decision` | A question, with named ways out. If the edges leaving it are not labelled, it is probably a `step` | a diamond |
| `emphasis` | The one box the diagram is about. One per drawing, two at most — a third is refused, because when three things say *look here first* none of them is first | a rectangle, heavier |
| `note` | An aside — a caveat, a source, a reminder. Not part of the argument | no outline at all |
| `group` | A container drawn around other boxes. Set by naming `members`; rarely written by hand | a dashed rectangle |

Two mistakes worth naming, both made in the corpus and both caught in review:

* **`start` and `terminal` are not decoration for the extremities.** Making one
  child a `step` and its sibling a `terminal` says the second one ends the
  process, and if the original gave them equal weight, that is a claim the
  author did not make.
* **A role is not a size.** `emphasis` and `terminal` are heavier because the
  theme draws them so. Reaching for one to make a box stand out is writing a
  typographic instruction in a document that has no field for one.

The same holds for connectors, where the vocabulary answers *what kind of
relation is this* and the theme answers whether it has a head. Roles are per
kind: the last two below belong to `entities`, and a `flow` refuses them by name.
Two of the others are worth reading together, because the difference is easy to miss and choosing
wrong misstates the drawing: `weak` is dashed **and** directed, so it says *this
may lead to that*; `aside` is dashed and **un**directed, so it says *this belongs
with that* and nothing about which way.

| Role | Use it for | Drawn as |
|---|---|---|
| `flow` | Then this happens. The default | an arrow |
| `strong` | The same relation, on the path that has no slack in it | a heavier arrow |
| `link` | Merely associated — no direction, no order | no head, and drawn as a straight chord |
| `exchange` | Both ways at once | a head at each end |
| `weak` | A soft or conditional dependency | dashed, with an open head |
| `owns` | This is a part of that | a diamond at the owning end |
| `aside` | Loosely associated, and in no direction — a note, a source, a caveat hanging off the thing it is about | dashed, with no head |
| `inherits` | `entities` only: this class is a kind of that one | a hollow triangle at the general end |
| `realizes` | `entities` only: this class implements that interface | dashed, with a hollow triangle |

Both sets are drawn, one box per role, in
[`reference/flow-node-roles.json`](reference/flow-node-roles.json) and
[`reference/flow-edge-roles.json`](reference/flow-edge-roles.json). `make
gallery` renders them; that page is the fastest answer to "what does `owns`
look like". The mechanical properties behind each row — shape, dash,
stroke width — are in [the theme reference](theme.md).

An edge whose `from` and `to` are the same box — a retry, a poll, a timer — is
drawn as a loop on that box's side, across the reading direction (right or left
in a drawing that reads down), leaving and returning on the same side so it
never meets the box's own incoming arrow; its label goes outside it and the
layout keeps room for both. A box may carry two, one per side; a loop on a
group is refused. See [`reference/flow-retry.json`](reference/flow-retry.json).

## Embedding the output

`render --profile` picks how the SVG is written, and the choice is about where
it is going, not how it looks.

**Inline** (the default) is for pasting into a Markdown or HTML page:

```bash
drawspec render diagram.json --profile inline -o diagram.svg
```

Every stroke is `currentColor`, so the drawing inherits the page's ink and
follows it into dark mode. There is no `<style>` block to leak into the page,
and every internal id is scoped, so two diagrams on one page cannot collide —
which is exactly the failure that makes hand-written SVG unsafe to paste twice.

**Standalone** is for a linked `.svg`, a PDF conversion, or anywhere there is
nothing to inherit from:

```bash
drawspec render diagram.json --profile standalone -o diagram.svg
chromium --headless --print-to-pdf=diagram.pdf diagram.svg
```

`currentColor` is resolved to the theme's `[canvas] ink`, because a converter's
own default is not a design decision anyone made.

In both profiles, no information is carried by colour alone. A diagram that
still reads on a black-and-white printer is the same diagram that still reads in
dark mode, and neither is caught by looking at the screen it was made on.

## Exporting an image

An SVG is the best form for a page you control. For everywhere else — a chat
message, a slide, an issue, a document editor that only takes pictures — render a
PNG:

```bash
pip install 'drawspec[png]'
drawspec render diagram.json -o diagram.png                  # inferred from .png
drawspec render diagram.json --format png --background dark -o diagram-dark.png
```

It is an **optional extra** because the core stays one dependency. The extra is
[`resvg-py`](https://pypi.org/project/resvg-py/), a single self-contained wheel
for Linux, macOS and Windows — still no Cairo and nothing to apt-get. Without it,
asking for a PNG is refused with exit 1 and the install line above.

* **It is the standalone drawing.** The inline profile draws in `currentColor`,
  which means nothing in a picture file, so the PNG is always made from the
  standalone SVG; `--profile` does not apply.
* **`--background`** picks the page: `light` (the default) is the theme's ink on
  white; `dark` is a light ink on near-black `#121212`, what the inline SVG does
  by itself on a dark page; `transparent` is the theme's ink on nothing — for a
  light page you do not control.
* **`--scale`** is pixels per SVG unit, `2` by default, so a 640-wide drawing is
  about 1,330 pixels across and stays crisp on a high-density screen. `1` is the
  smallest file; the most is `8`.
* **The text is set in the fonts it was measured with.** The renderer ignores
  the machine's fonts and loads the files drawspec measured against — the bundled
  ones unless your theme names a family you have installed — so a label that
  fitted in the SVG fits in the PNG, and with the bundled fonts the file is
  byte-identical on every machine.

There is no JPEG (it smears line art), no PDF (print the standalone SVG, above),
and no WebP: the renderer encodes PNG only, and WebP would mean a second
dependency for a format every PNG viewer already covers.

From Python, `render_png(document, theme, scale=2.0, background="light")` returns
the bytes; it raises `ExportError` when the extra is missing.

## Validating in a build

```bash
drawspec validate diagram.json
```

`validate` parses and checks without drawing anything, and prints **every**
violation with its JSON pointer rather than stopping at the first — one pass
over its output should be one edit. Pass `--theme` as well and the theme is
loaded too, because a theme that will not load is a reason this document cannot
be rendered, and finding that out at validation time is the point of validating.

The exit codes are the part a build script consumes, and the split is worth
knowing: **2 is the invocation, 1 is the content.** A misspelt flag is 2 —
nothing was read, so nothing can be said about it. A document that cannot be
parsed or cannot be made to fit is 1. A refusal is an outcome, not a crash, and
its message names the remedy as well as the fault, so pass stderr through rather
than truncating it to a summary line.

```bash
# a pre-commit or CI step over a directory of documents
for document in docs/diagrams/*.json; do
  drawspec validate "$document" || exit 1
done
```

## Writing a theme

A theme is **data, not code** — a TOML file you version and diff without
importing anything. It owns every appearance decision, so no document has to,
and changing it changes every diagram at once.

Start from the smallest possible file. Everything is merged over the bundled
default, leaf by leaf, so declare only what you change:

```toml
version = 1
name = "house"

[font]
# Put the family your *page* is set in first. The SVG inherits the page's font
# stack, so measuring a different family is what makes a tight box overflow.
sans = ["Inter", "DejaVu Sans", "sans-serif"]

[scale]
body = 12.0

[role.note]
dash = "2 2"
```

`version` is the one key not inherited: a theme must state which format it was
written against, or a future v2 file would load as a v1.

Then check it:

```bash
drawspec theme check house.toml
drawspec render diagram.json --theme house.toml -o diagram.svg
```

`theme check` loads the file and runs its invariants. The one that will catch
you is the greyscale rule: **two roles may not be distinguishable by colour
alone.** If you colour `emphasis` red and leave everything else about it
identical to `step`, the theme is refused — not the render, the theme, at load
time. Give it a heavier stroke or a different shape as well, and the colour
becomes a second signal rather than the only one.

Colour is not forbidden. The bundled `accent` theme uses it on six roles, every
one of which already differed from its neighbours by weight, dash or shape.
Colour may *point*, and it may never *carry*.

[The theme reference](theme.md) lists every key and its default. Three are worth
understanding before you change anything else:

* **`[canvas] width`** is why two diagrams on one page are the same type size.
  It belongs to the theme rather than to a document on purpose.
* **`[canvas] margin`** is the channel of blank between the drawing and the edge
  of the figure, on all four sides. It sits *around* `width`, so the emitted
  canvas is `width + margin * 2` and the drawing keeps every unit of its own
  budget — set `width` to your column less twice this to fill a measure exactly.
  Set it to `0` for a page that pads its own figures. It exists because without
  it each kind framed itself: a timeline above a flow chart bled to the edge
  beside a quarter-inch of white.
* **`[canvas] width_mode`** decides whether a narrow drawing keeps that canvas
  (`fixed`, centred in it) or is cropped to its own ink (`ink`). Cropping is
  what makes a page scale two diagrams by different factors and read one label
  at two sizes. Use `ink` only for a diagram meant to be sized on its own.
* **`[fit] scale_min` / `scale_max`** are how far the whole type scale may
  stretch to make content fit — one factor applied to all four levels at once,
  so a tight diagram never gains a type size its neighbours do not have. Below
  `[canvas] min_legible_size` nothing is drawn at all: it is a refusal, with a
  message, rather than text nobody can read.

### A drafting sheet: the `blueprint` theme

```bash
drawspec render pump.json --theme blueprint -o pump.png
```

Any diagram comes out on an engineering drawing sheet: white ink on blueprint
blue, a fine grid, a double border with zone numbers and letters, registration
marks, and a title block filled from the document — its `title` (or its kind),
a drawing number derived from its content, its `kind`, the drawing's size, and
its format `version`. It is the sheet the README banner is drawn on.

The sheet is `[canvas]` furniture, so any theme can have it:

```toml
version = 1
name = "drafting"

[canvas]
ground = "#0b2d52"      # the sheet; "none" draws it on the page
ink = "#f2f8ff"         # must read on the ground at 4.5:1, or the theme is refused
rule = "#8fbbe6"        # grid and quiet lettering; empty means the ink
accent = "#ffb547"      # registration marks and the drawing number
pattern = "grid"        # or "none"
border = "zoned"        # or "none"
title_block = true
```

Three things to know. It is drawn **only in the `standalone` profile** — a
linked `.svg`, a PDF, a PNG; pasted inline, the same theme inherits the page's
ink and background like any other, so a README can show it either way. The
canvas **grows** to hold it rather than drawing over the diagram: every diagram
in the theme gains the same border, so they are still one width, and the title
block has a strip of its own below the drawing. And a title too long to set on
one line in the block is a `FitError` on a fixed-width canvas — shorten the
`title`. The gallery's `*-blueprint-*` drawings are rendered this way.

## Matching your brand

If your project already has a design system, derive the theme from it rather than
copying values across by hand:

```bash
drawspec theme from site.css                          # the theme on stdout
drawspec theme from site.css tokens.json -o house.toml --name house
drawspec theme check house.toml
```

It reads **CSS custom properties** (`--color-accent: #0f7b8a` in a `.css` file)
and **W3C design tokens** (a `.json` or `.tokens` file of `$value`s, aliases and
inherited `$type`s), writes the theme as TOML with each key commented with the
token it came from, and prints one line per token on stderr: `used`, `adjusted`,
or `ignored` and why. Local files only — save the stylesheet first; drawspec
fetches nothing. A later file wins a tie, so a tokens file can refine a stylesheet.

| The brand says (by token name) | The theme gets |
|---|---|
| an `accent`, `primary` or `brand` colour | the stroke of `emphasis`, `terminal` and `strong`, and the first chart colour |
| a `secondary`, `tertiary` colour | the second and third chart colours |
| a `muted`, `subtle` or `neutral` colour | the stroke of `note`, `group` and `link`, and the last chart colours |
| a `text` or `foreground` colour | `[canvas] ink` — the `standalone` profile only |
| a `sans`/`body`, `serif`, `mono`/`code` font family | `[font] sans`, `serif`, `mono`; a serif body face also sets `default = "serif"` |
| a `radius` | `[box] corner_radius`, at most 12 |
| a `border-width` or `stroke-width` | every stroke weight, scaled together (0.75–1.5×) so the ratios hold |
| a unitless `line-height` | `[box] line_height`, 1.2–1.6 |

**What it will not take, and why.** A drawspec SVG inherits its page: strokes and
text are `currentColor` and there is no background, which is what makes a diagram
follow its page into dark mode. So a brand's background, surface and border
colours are ignored — the drawing already sits on the page's own — and so are
dark-mode overrides (`@media (prefers-color-scheme: dark)`, or any selector other
than `:root`). Status colours (`success`, `danger`) are ignored because colour may
point but never carry. Font sizes and spacing are ignored: the type scale is
relative to the canvas, which the page scales to its column, so a CSS pixel says
nothing about it.

**Colour is held to the page, both pages.** A brand colour does not follow dark
mode, so it has to read on both: at least **3:1**, WCAG's figure for lines and
shapes, against white *and* against `#121212`. A pale brand yellow is darkened, a
deep violet lightened, hue kept, until it does, and the report gives both ratios.
Pass `--strict` to refuse instead. Colour lands only where the `accent` theme puts
it — on roles already told apart by weight, dash or shape, and over chart fill
patterns that stay distinct — so the greyscale rule holds with no help from you.

Name the family your page is set in and drawspec measures with it if it is
installed; if not, it measures with the next family in the stack and says so. The
gallery's `*-brand-*` drawings use a theme derived from
[`docs/reference/brand/tidemark.css`](reference/brand/tidemark.css). A relative
`theme` path in a document file is read from the document's own folder when the
theme is there, and from the working directory otherwise.

## Using it from Python

The CLI is the supported interface, but the library underneath it is small and
stable enough to call directly:

Everything that can be refused raises a `DrawspecError` — `DocumentError`, which
also carries its violations as a list, `ThemeError`, or `FitError` when the
content cannot be drawn legibly at the size it was given. Catch the base class
and print it: the message is the product, and it already names every violation
with its pointer.

```python
from pathlib import Path

from drawspec.errors import DrawspecError
from drawspec.render import render_document
from drawspec.schema import load_document
from drawspec.theme import load_theme

try:
    document = load_document("diagram.json")
    svg = render_document(document, load_theme("house.toml"), "inline")
except DrawspecError as refusal:
    print(refusal)  # every violation, located
else:
    Path("diagram.svg").write_text(svg, encoding="utf-8")
```

`drawspec.render_png(document)` returns the same drawing as PNG bytes — see
[Exporting an image](#exporting-an-image).

## Saying who performs a step

`role` says what kind of step a box is. `actor` says whose it is, and the two are
independent — a human step can be routine and an automated one can be the
critical path:

```json
{ "id": "approve", "text": "Sign off the release", "actor": "A release manager" }
```

It is drawn as the box's **lead**: the name over what belongs to it. So the same
words sit in the same place in every box, and the odd one out in a pipeline is
found by scanning one column rather than by reading five labels.

Free text, not an enum, and that is load-bearing. **An actor is told apart by its
name** — `CI` does not look like `A release manager` in colour, in greyscale or
read aloud — so ownership costs none of the four non-colour channels the *roles*
are told apart by, and the greyscale invariant needs nothing new. An enum would
have thrown that away, and would not have covered `"Finance"` or
`"The customer"`.

Two things it deliberately is not:

* **Not a swimlane.** Nothing is partitioned; the layout is unchanged. When the
  hand-offs between parties are the point, change the kind to `lanes` — the same
  document, drawn with one strip per actor; see [Swimlanes](#swimlanes).
* **Not a band.** A band says *this runs alongside these*, and its bar spans its
  members' extent — so an owner holding the first, second and fourth step would
  draw a bar straight across the third, claiming a step it does not perform.
  Ownership belongs to one box. Compare
  [`flow-bands`](reference/flow-bands.json) with
  [`flow-actor-handover`](reference/flow-actor-handover.json): same four steps,
  opposite statements.

A box has one lead, so a node that names an actor may not also write its own with
a newline in `text`. That is refused by pointer rather than resolved silently —
picking a winner would be drawspec deciding which of two things you meant.

## Using it from an agent: the MCP server

If the thing writing your documents is a language model rather than a person,
there is a third interface. `drawspec-mcp` serves the same work as three MCP
tools over stdio:

| Tool | Answers |
|---|---|
| `validate` | would `render` refuse this, and **where** — every violation as `{"pointer", "message"}` |
| `render` | the SVG, with the same optional `theme`, `width` and `height` — or, with `"format": "png"` (and optional `scale`, `background`), a base64 PNG image block, when the server has `drawspec[png]` |
| `kinds` | every kind and what it is for, so a model chooses one instead of guessing |

```bash
pip install 'drawspec[mcp]'
```

Then point a client at it. For anything that reads the conventional JSON config:

```json
{
  "mcpServers": {
    "drawspec": { "command": "drawspec-mcp" }
  }
}
```

**`validate` is the one that earns the server.** Shelling out to the CLI works,
and it hands a model prose on stderr that it has to read to discover that
`/edges/2/to` names nothing. As a tool the same refusal comes back as data, in
the model's own loop, and the write-validate-fix cycle closes without a shell in
it. It is the same check the CLI runs — the server does not describe the format a
second time, and a refusal here says exactly what a refusal there says.

**For agents that load skills**, [`skills/drawspec/SKILL.md`](../skills/drawspec/SKILL.md)
is an [Agent Skill](https://agentskills.io): copy the directory into your skills
folder and the agent learns *when* to reach for drawspec and the loop to follow
— install, read `AGENTS.md`, write the JSON, validate, render. It is a pointer,
not a copy of the format, so it cannot drift from it, and a test holds every
command it names to the CLI.

## Groups and bands

Both take a set of nodes, and they say different things about them.

| | Says | Drawn as | A box may be in |
|---|---|---|---|
| `groups` | These are **inside** this | a dashed frame with a caption | one group, or none |
| `bands` | This runs **alongside** these | a bar beside them, with its name outside it | any number of bands |

The distinction is worth the second field because containment is exclusive and
company is not. A process with one continuous concern above its steps and another
below has two things of equal rank accompanying the same six boxes; written as
groups, one has to be nested inside the other, and the drawing then claims a
hierarchy nobody stated. Written as bands they are peers, which is what they are.

**An edge may name a group.** `from` and `to` take a group's id as readily as a
node's, and the arrow then stops on the frame's border rather than on any box
inside it. That is for the relation that belongs to the whole container — a
platform that watches *the cluster* rather than one pod of it, a report produced
by *the service* rather than by one of its components. Drawn from a member the
diagram says something narrower, and choosing which member is exactly the
coordinate decision drawspec exists to spare an author. See
[`reference/flow-groups.json`](reference/flow-groups.json), whose monitoring
platform arrives on the control plane itself.

An edge between a container and something already inside it is refused, at any
depth of nesting: it would leave a border and arrive within the same border,
which is not a relation between two things. Draw it from a member instead.

This is `flow` and `tree` only. A `cycle` accepts `groups` and draws none — it
places its steps on a ring — so an edge in one names a node, and a group id at
either end is refused with a message that says which of the two you have.

A band runs *along* the reading direction and is placed *across* it, so a process
read across the page gets its bands above and below, and the same process read
down gets them left and right. See
[`reference/flow-bands.json`](reference/flow-bands.json).

A band's name is a text field like any other: it carries `**bold**` and
`` `code` ``, a newline makes the first paragraph a lead over its detail, and it
**wraps to the length of its own bar**. That length is the extent the band already
claims — a name running past the last of its members would be claiming boxes the
band has not got — so a long name beside a short bar comes back as two or three
lines rather than one long one. A single word longer than the bar is refused, and
the message names the band rather than the diagram.

## Drawing a change

A design document proposing a change usually wants to say *what is new, what
goes, what changes* — and hand-drawn, that is two diagrams side by side that the
reader has to diff by eye. In a `flow` or a `tree`, draw the target state **once**
and mark the change on it with `status`, the same vocabulary `files` uses:

```json
{
  "version": 1,
  "kind": "flow",
  "nodes": [
    {"id": "web", "text": "Web front end"},
    {"id": "mono", "text": "Monolith", "status": "changed"},
    {"id": "sess", "text": "Session service", "status": "added"},
    {"id": "table", "text": "Sessions table", "status": "removed"}
  ],
  "edges": [
    {"from": "web", "to": "mono"},
    {"from": "web", "to": "sess", "status": "added"},
    {"from": "mono", "to": "table", "status": "removed"}
  ]
}
```

A marked box carries a tag inside it — `+ added`, `~ changed`, `− removed`, a
mark and a word, never a colour — and a removed box is also outlined dashed with
its words struck through. A marked edge writes its mark before its label (or
alone, mid-edge), and a removed edge is drawn dashed with no head whatever its
role. When any edge is marked, a key of the statuses used goes under the drawing.

The marks have to agree with each other: an edge touching a removed box must be
`removed` (it cannot outlive what it connects), and one touching an added box must
be `added` (an edge to something new is new). Either is refused at the edge's
`status`. A `cycle` refuses `status` — a loop that changes is a different loop,
so draw both. See [`reference/flow-status-search.json`](reference/flow-status-search.json),
[`reference/flow-status-failover.json`](reference/flow-status-failover.json) and
[`reference/tree-status-reorg.json`](reference/tree-status-reorg.json).

## A grid whose cells say how much

A `matrix` fills cells that share a `group` alike, and by default the groups are a
set: *data*, *copy* and *parity* get three unrelated patterns. A heatmap, a risk
matrix or a skills matrix needs the opposite — the groups are an **order**, and
the eye should find the heavy cells without reading a word. Say so with `scale`,
the group names weakest first:

```json
{
  "version": 1,
  "kind": "matrix",
  "columns": ["Minor", "Severe"],
  "rows": ["Likely", "Rare"],
  "scale": ["low", "medium", "high"],
  "cells": [
    {"text": "Ledger totals disagree", "column": 1, "row": 0, "group": "high"},
    {"text": "Dashboards lag", "column": 0, "row": 0, "group": "medium"},
    {"text": "Symbols misplaced", "column": 0, "row": 1, "group": "low"},
    {"text": "Not assessed", "column": 1, "row": 1}
  ]
}
```

The cells are then filled by **tone**, light to dark, from the theme's
`[mark] ramp` — lightness is what survives greyscale, and patterns cannot carry
an order. The key lists every step in scale order, with `key` texts where you
give them. A cell with no `group` stays blank, for *not assessed*. Every cell
`group` must be a step, a scale has 2 to 5 steps (past five, neighbouring greys
merge in print), and there is no numeric `value` to colour by: bucket the
numbers, name the buckets, and keep the number in the cell's text if it
matters. See [`reference/matrix-scale-risk.json`](reference/matrix-scale-risk.json),
[`reference/matrix-scale-ci.json`](reference/matrix-scale-ci.json) and
[`reference/matrix-scale-skills.json`](reference/matrix-scale-skills.json).

## A loop with something in its middle

Many loops turn around something that is not a step: a quality cycle around the
management system it improves, a data flywheel around the log it learns from. Put
that on the ring and it becomes a fifth step; give a node `centre` and a `cycle`
refuses it, because a ring has no node in the middle. Say it with `hub`:

```json
{
  "version": 1,
  "kind": "cycle",
  "hub": {"id": "log", "text": "Interaction log"},
  "nodes": [
    {"id": "rank", "text": "Rank the items"},
    {"id": "show", "text": "Show them"},
    {"id": "click", "text": "User clicks or skips"},
    {"id": "train", "text": "Retrain nightly"}
  ],
  "edges": [
    {"from": "rank", "to": "show"},
    {"from": "show", "to": "click"},
    {"from": "click", "to": "train"},
    {"from": "train", "to": "rank"},
    {"from": "click", "to": "log", "role": "weak", "label": "written"}
  ]
}
```

The hub is drawn centred inside the ring, and the ring grows to make room for it.
It is not a node: the check that the edges close one loop through every step
ignores it. An edge may name it, but only as a **spoke**, in `aside`, `weak` or
`link` — a solid arrow into the middle would read as one more step, so `flow`,
`strong`, `exchange` and `owns` are refused at the edge's `role`. A hub needs at
least three steps around it (two and a middle is a `flow`), and a shortcut whose
chord would cross the middle is refused rather than drawn through the hub. See
[`reference/cycle-hub-quality.json`](reference/cycle-hub-quality.json) and
[`reference/cycle-hub-flywheel.json`](reference/cycle-hub-flywheel.json).

## A state machine

A `flow`'s boxes are things done, once each; a state machine's are conditions
something *is in*, revisited, with every arrow labelled by what moves it. Say
that with `states`:

```json
{
  "version": 1,
  "kind": "states",
  "initial": "closed",
  "states": [
    {"id": "closed", "text": "Closed\ncalls go through"},
    {"id": "open", "text": "Open\ncalls fail fast"},
    {"id": "half", "text": "Half-open\none trial call"}
  ],
  "transitions": [
    {"from": "closed", "to": "closed", "event": "call fails", "guard": "under the threshold", "action": "count it"},
    {"from": "closed", "to": "open", "event": "call fails", "guard": "threshold reached"},
    {"from": "open", "to": "half", "event": "cool-down elapses"},
    {"from": "half", "to": "closed", "event": "trial succeeds"},
    {"from": "half", "to": "open", "event": "trial fails"}
  ]
}
```

`initial` is drawn as a filled dot with an arrow to that state; each state in
`final` gets an arrow to a ringed dot (the theme's `[states]` sizes both). A
transition's label is composed from `event`, `guard` and `action` — one under
the other, the guard in brackets and the action after a slash — so write the
words and not the punctuation. A transition from a state to itself is a loop on
the side of its box, across the reading direction, with its label outside it;
a state may have two. Roles: `step`, `emphasis` or `terminal` on a state;
`flow`, `strong` (the happy path) or `weak` (a rare or error path) on a
transition.

`groups` are composite states, and may nest. A transition **from** a group
leaves it from whichever state inside is current; one **to** a group enters it at
the group's own `initial`, which is drawn as a dot inside the frame — and is
required when anything enters the group.

Refused, each at its pointer: a state no transition reaches from `initial` (a
bug in the machine — add the transition or delete the state); a `final` state
with an outgoing transition; `final` naming a group; two transitions leaving one
state on the same event and guard for different states (give them guards); a
loop on a group, or a third loop on one state. A machine with parallel regions
is two machines: draw two. See
[`reference/states-breaker.json`](reference/states-breaker.json),
[`reference/states-invoice.json`](reference/states-invoice.json) and
[`reference/states-ticket.json`](reference/states-ticket.json).

## A sequence diagram

When the same few participants talk to each other several times and the order
is the point — a protocol, a request through three services, a runbook's
hand-offs — draw a `sequence`. Participants are columns in the order written,
messages are rows in the order written, and nothing else is placed:

```json
{
  "version": 1,
  "kind": "sequence",
  "participants": [
    {"id": "client", "text": "Client"},
    {"id": "service", "text": "Order service", "role": "emphasis"},
    {"id": "db", "text": "Database"}
  ],
  "messages": [
    {"id": "ask", "from": "client", "to": "service", "text": "get order 42"},
    {"id": "read", "from": "service", "to": "db", "text": "read the row"},
    {"id": "row", "from": "db", "to": "service", "text": "the row", "role": "weak"},
    {"from": "service", "to": "client", "text": "the order", "role": "weak", "note": "cached for a minute"}
  ],
  "fragments": [
    {"operator": "opt", "from": "read", "to": "row", "text": "not in the cache"}
  ]
}
```

A message's `role` says what it is: `flow` (the default) is a call, `weak` a
reply — dashed with an open head — and `strong` the exchange that matters. A call
answered later by a `weak` reply from the participant it called gives that
participant an **activation bar** from the call's row to the reply's, nested when
calls nest; you never write one. A call nobody answers has no bar, which is how
an asynchronous message is drawn. A message `from` and `to` the same participant
is a hook on the right of its lifeline, and a `note` is set on its message's row
in one column right of the last lifeline.

`fragments` frame a run of messages, by the ids of the first and last: `loop`,
`opt`, `alt` or `par`, written in the frame's tab, with `text` as the condition
beside it. An `alt` or `par` may be divided by `else` — `[{"at": "<id>", "text":
…}]`, a dashed line above that message. If a reply inside one branch of an `alt`
answers a call made before the frame, the bar runs on to the last answer in the
frame. `groups` frame a run of neighbouring lifelines, named at the top.
Participant roles are `step`, `emphasis`, or `note` for an outside system drawn
as words with no box; the theme's `[sequence]` sets the bar's width and the role
a lifeline is drawn in.

Refused, each at its pointer: a message naming an unknown participant; a
participant no message names; a fragment that ends before it starts, or that
starts inside another and ends outside it; `else` on a `loop` or `opt`, or a
divider outside its frame, at its top, or inside a nested frame; a group whose
members are not neighbours in `participants` (the message names the one in the
way), or a participant in two groups; any role with no single direction
(`aside`, `link`, `exchange`, `owns`). Budget: 8 participants, 30 messages —
past that it is a trace; split it into phases. See
[`reference/sequence-dns.json`](reference/sequence-dns.json),
[`reference/sequence-upload.json`](reference/sequence-upload.json),
[`reference/sequence-drain.json`](reference/sequence-drain.json) and
[`reference/sequence-checkout.json`](reference/sequence-checkout.json).

## Swimlanes

When what matters is *who hands off to whom* — a request crossing from support to
engineering and back — draw `lanes`. It takes a `flow` document unchanged, with
one difference: every node names its `actor`, and the actor is drawn once, as a
strip of the page holding all of that party's steps, instead of as each box's
lead. An arrow that crosses from one strip to another is a hand-off:

```json
{
  "version": 1,
  "kind": "lanes",
  "lanes": ["Employee", "Manager", "Finance"],
  "nodes": [
    {"id": "submit", "text": "Submits receipts", "actor": "Employee", "role": "start"},
    {"id": "approve", "text": "Approves?", "actor": "Manager", "role": "decision"},
    {"id": "fix", "text": "Corrects the claim", "actor": "Employee"},
    {"id": "pay", "text": "Pays it", "actor": "Finance", "role": "terminal"}
  ],
  "edges": [
    {"from": "submit", "to": "approve"},
    {"from": "approve", "to": "fix", "label": "no"},
    {"from": "fix", "to": "approve", "role": "weak"},
    {"from": "approve", "to": "pay", "label": "yes"}
  ]
}
```

The graph is ranked exactly as a `flow`'s, along the lanes; a box's lane decides
the other coordinate, and two steps of one party at the same rank stack inside
its strip. `lanes` gives the order of the strips — omit it and they come in the
order their actors first appear. Since the actor is not in the box, `text` may
use a newline for its own lead and detail again. Node and edge roles, edge
labels, self-loops and `status` are a flow's.

Whether the strips run across the page as rows (ranks reading left to right, a
column of names at the left) or down it as columns (ranks reading down, a name
over each) is the theme's `[lanes] orientation`: `auto`, the default, takes rows
when they fit the width and columns when they do not. At the default width, a
process of more than four or five steps in a row reads down. `[lanes] separator`
is the edge role the line between two lanes is drawn in.

Refused, each at its pointer: a node with no `actor` (the message points you back
to `flow`); an actor not in `lanes`, naming the closest lane; a lane in `lanes`
that no node names, or one listed twice; `groups`, `bands` and `centre`, because
a lane is already the container and a frame or band would cross it; and the
`group` node role. Budget: a flow's 15 nodes and 16 edges, and 6 lanes, counted
from the actors when `lanes` is omitted. See
[`reference/lanes-disclosure.json`](reference/lanes-disclosure.json),
[`reference/lanes-tender.json`](reference/lanes-tender.json),
[`reference/lanes-expense.json`](reference/lanes-expense.json) and
[`reference/lanes-onboarding.json`](reference/lanes-onboarding.json).

## Data models, schemas and class diagrams

An ER model, a database schema and a class diagram are one drawing — a named box
with a list in it, and typed relations between boxes — so they are one kind,
`entities`, and a document uses the parts its vocabulary needs:

```json
{
  "version": 1,
  "kind": "entities",
  "entities": [
    {"id": "teams", "text": "`teams`", "fields": [
      {"id": "t_id", "text": "`id`", "type": "uuid", "key": "primary"},
      {"text": "`name`", "type": "text"}
    ]},
    {"id": "people", "text": "`people`", "fields": [
      {"text": "`id`", "type": "uuid", "key": "primary"},
      {"id": "p_team", "text": "`team_id`", "type": "uuid", "key": "foreign"},
      {"text": "..."}
    ]}
  ],
  "edges": [
    {"from": "people", "from_field": "p_team", "to": "teams", "to_field": "t_id",
     "from_end": "zero-or-many", "to_end": "one"}
  ]
}
```

Each entity is drawn as its name (bold, with an optional `tag` over it in
guillemets — `«interface»`), a rule, its `fields` one row each, and its
`operations` under a second rule. A field may carry a `type`, drawn right-aligned
in the code face, and a `key` — `primary`, `foreign` or `unique`, drawn as the
letters `PK`, `FK`, `UQ`. A last field of `...` is a row standing for the fields
not shown. Rows never wrap: a row too wide for the entity's share of the canvas
is a `FitError` naming it.

A relation lands on the box — or, when it names `from_field` or `to_field`, on
that **row**, at the side facing the other entity: a foreign key drawn from its
own column. `from_end` and `to_end` say *how many of this end per one of the
other* — `one`, `zero-or-one`, `many`, `zero-or-many`, `one-or-many` — and the
theme's `[entities] notation` says how that is drawn: crow's-foot marks (the
default) or UML's numbers (`1`, `0..1`, `*`, `0..*`, `1..*`). An end with a
cardinality draws it in place of the role's head.

Relation roles: `link` (the default — an association has no direction), `owns`
(composition: `from` is a part of `to`, diamond at `to`), `weak` (dashed: a
dependency, or a non-identifying relation), `strong` (the one that matters), and
`inherits` and `realizes`, which only this kind accepts — a hollow triangle at the
general end, solid for a subclass and dashed for an implementation. With a
hierarchy in the diagram, general entities are placed above specific ones and it
reads down; without one it reads across, the one side of each relation before
its many side; either way the other direction is taken when the first does not
fit.

Refused, each at its pointer: a cardinality or a row on `inherits`/`realizes`; a
hierarchy that loops (at the relation that closes it); a `from_field` that is a
field of another entity; a relation of an entity to itself; a `to_end` on `owns`
(the whole is always one); a `...` field that is not last, or that carries a
type, key or id; a name on two lines; a `tag` over 16 characters; and aggregation
(`aggregates`), which is not offered — say `owns` or `link`. Visibility is not a
field: write `- name` in `text`. Entity roles are `step`, `emphasis` and `note` (an
outside entity, drawn dashed). Budget: 8 entities, 12 edges, 12 fields and 8
operations per entity. See
[`reference/entities-library.json`](reference/entities-library.json),
[`reference/entities-orders.json`](reference/entities-orders.json),
[`reference/entities-shapes.json`](reference/entities-shapes.json) and
[`reference/entities-enrolment.json`](reference/entities-enrolment.json).

## A plan

A `timeline` is one axis of instants: *when things happened*. A plan is one row
per piece of work, each an interval, and what the reader looks for is overlap —
what runs in parallel, what waits on what, what the plan looks like in week six.
That is `gantt`:

```json
{
  "version": 1,
  "kind": "gantt",
  "axis": {"label": "Week", "min": 0, "max": 10},
  "tasks": [
    {"id": "provision", "text": "Provision the cluster", "start": 0, "end": 2},
    {"id": "backfill", "text": "Backfill history", "start": 2, "end": 6, "role": "emphasis"},
    {"id": "cutover", "text": "Cut reads over", "at": 6},
    {"id": "retire", "text": "Retire the old cluster", "start": 6, "end": 10}
  ],
  "edges": [
    {"from": "provision", "to": "backfill"},
    {"from": "backfill", "to": "cutover"},
    {"from": "cutover", "to": "retire"}
  ],
  "marks": [{"text": "today", "at": 3}]
}
```

**There are no dates.** A task's `start` and `end` are numbers in a unit the
axis names — week 3, day 12, minute 45 — and a real calendar, with its weekends
and month lengths, is a project tool's job. For a plan by month, sprint or term,
name the periods in `axis.categories`: the first runs from 1 to 2, the second
from 2 to 3, and each name is written in the middle of its period, so a task
over the first three months is `"start": 1, "end": 4`. Categories set the range,
so they take no `min` or `max`. Otherwise an end the author does not pin is taken
out to the next tick.

Rows are in the order written, labels in a column at the left (as wide as the
widest, up to about a third of the canvas, then wrapped). A task with `at`
instead of `start` and `end` is a **milestone**, drawn as a filled diamond (the
theme's `[gantt] milestone` may make it a dot). An `actor` is the label's lead,
as in a `flow` box. Task roles: `step` (the default bar), `strong` (on the
critical path — heavier, the same word its dependencies take, and not counted by
the emphasis cap), `emphasis` (the task the diagram is about — heavier and
differently filled) and `note` (outside the plan — a light dashed outline).

`edges` are finish-to-start: each is drawn from the end of one bar into the start
of the other, and the line goes round the bars it can rather than through them.
Roles `flow`, `strong` (the critical path) and `weak` (a soft dependency).
`groups` are phases: each a run of consecutive tasks, drawn as a bold heading row
with a bracket over the phase's span, its tasks indented under it. `marks` are
named points — today, a deadline, a freeze — each a line across every row (in the
theme's `[gantt] marks` edge role) with its name beside the top.

Refused, each at its pointer: a string where a number belongs (a date, almost
always — the message suggests a unit and `categories`); a task with both `at` and
`start`/`end`, or neither, or only one end; an `end` not after its `start`; any
value or mark off the axis; a dependency whose `to` starts before its `from` ends
(either the plan or the dependency is wrong, and only the author knows which); a
dependency on an unknown task or on itself; a phase whose tasks are not
consecutive, a task in two phases, and — with phases — a task in none; a phase
with no `text`; `progress`, which is status rather than plan; and a newline in a
task's `text` when it has an actor. Budget: 16 tasks, 20 edges and 4 marks. See
[`reference/gantt-migration.json`](reference/gantt-migration.json),
[`reference/gantt-critical-path.json`](reference/gantt-critical-path.json),
[`reference/gantt-upgrade.json`](reference/gantt-upgrade.json) and
[`reference/gantt-semester.json`](reference/gantt-semester.json).

## A board

A kanban board, a retrospective and a story map are one picture: **cards sorted
into columns, with no connectors**. That is `board`:

```json
{
  "version": 1,
  "kind": "board",
  "columns": [
    {"id": "todo", "text": "To do"},
    {"id": "review", "text": "In review", "limit": 2},
    {"id": "done", "text": "Published"}
  ],
  "cards": [
    {"text": "Troubleshooting", "column": "todo"},
    {"text": "Theming guide", "column": "review", "actor": "Ana"},
    {"text": "MCP server", "column": "review", "role": "emphasis", "note": "blocked on a decision"},
    {"text": "Gallery page", "column": "review"},
    {"text": "Install guide", "column": "done"}
  ]
}
```

Columns are equal and left to right as written, each a bold heading over a
rule. A column with a `limit` is **counted by drawspec**: the heading reads
`3 / 2` here, and over its limit it takes `emphasis` (a heavier rule and a bold
count) — never write the count yourself. Cards stack in each cell **in the order
written**, top-aligned, so a short column looks short. Card roles: `step`,
`emphasis` (blocked, at risk) and `note` (a placeholder or a summary such as
`+ 6 more`, a light dashed card, not counted against a limit). An `actor` is the
card's lead, as in a `flow` box; a card's `note` hangs under the card, smaller.

With `rows` it is a **story map**: each row a slice across every column (a
release), named in a margin at the left, and every card names its `row`. `cut`
names the row the first release ends at; the board's one heavy line is drawn
under it (the theme's `[board] cut`), and the other slices are parted by
`[board] separator`.

Refused, each at its pointer: `edges` — if the order between cards matters it is
a `flow`, or `lanes`; a per-card `label`, `tag` or `colour` (a card's kind is its
column); a card in an unknown column or row; a `row` on a board without rows, or
a card without one on a board with them (half a story map is a mistake); a `cut`
without rows, on an unknown row or on the last; and a newline in a card's `text`
when it has an actor. Budget: 6 columns, 4 rows, 32 cards, and 8 cards in one
cell — past that, end the cell with a summary card. See
[`reference/board-migration.json`](reference/board-migration.json),
[`reference/board-retrospective.json`](reference/board-retrospective.json),
[`reference/board-story-map.json`](reference/board-story-map.json) and
[`reference/board-onboarding.json`](reference/board-onboarding.json).

## A fishbone

A root-cause review has one claim, and it is fixed: **one effect; causes grouped
into categories; nothing deeper**. Drawn as a two-level `tree`, the effect sits on
top as if it owned its causes. `fishbone` draws it the other way round —
everything flows into the head:

```json
{
  "version": 1,
  "kind": "fishbone",
  "title": "Why the backup finished at 09:40",
  "effect": {"text": "Nightly backup overran its window by 3 h 40 min"},
  "categories": [
    {"text": "Data", "causes": [
      {"text": "Audit table grew 4× after the logging change", "role": "emphasis"},
      {"text": "No retention on audit rows"}
    ]},
    {"text": "Infrastructure", "causes": [{"text": "Backup volume on slower storage tier"}]},
    {"text": "Monitoring", "causes": [{"text": "Duration alert only at 6 h", "role": "note"}]}
  ]
}
```

The effect is the box at the head of the spine, always drawn as the emphasis (it
takes no `role`). Categories are bones, alternately above and below the spine,
**nearest the head first**, all one length and slanted at the theme's `[fishbone]
slant` (60° by default; `90` draws upright bones). A cause is a tick off its bone
with its words standing on it, listed from the category's name inwards. Cause
roles: `step`, `emphasis` — the confirmed root cause, set bold, its tick and the
rest of its bone to the spine drawn in the spine's heavy role — and `note`, a
cause investigated and ruled out, on a light dashed tick. Keep the ruled-out
causes: a fishbone records what was investigated.

Refused, each at its pointer: `causes` inside a cause — a sub-cause of a cause is
a second fishbone with that cause as its effect; a category with no causes (write
`"nothing found"` as a `note` cause instead); fewer than 2 categories; `edges` (a
cause that feeds another cause is a `flow`); a cause role with a shape
(`decision`, `terminal`); a `role` on the effect. Budget: 6 categories and 5
causes in one. When the causes will not fit the width, they wrap narrower; when no
width works, `FitError` names the longest cause. See
[`reference/fishbone-backup.json`](reference/fishbone-backup.json),
[`reference/fishbone-late-orders.json`](reference/fishbone-late-orders.json),
[`reference/fishbone-flaky-ci.json`](reference/fishbone-flaky-ci.json) and
[`reference/fishbone-signups.json`](reference/fishbone-signups.json).

## A Venn diagram

"What do these share" is a Venn diagram, and with two or three sets it needs no
coordinates at all: every region is fixed by **which sets it is in**. That is
`venn`:

```json
{
  "version": 1,
  "kind": "venn",
  "title": "Two frameworks, one breach",
  "sets": [
    {"id": "gdpr", "text": "Data protection regulation"},
    {"id": "ens", "text": "National security framework"}
  ],
  "regions": [
    {"in": ["gdpr"], "text": "Notify the supervisory authority within 72 h"},
    {"in": ["ens"], "text": "Report to the national CERT"},
    {"in": ["gdpr", "ens"], "text": "Keep an incident record", "role": "emphasis"}
  ]
}
```

`in` is the exact list of set ids a region belongs to, and no others: `["gdpr"]`
is what only that set holds. The circles are equal — two side by side, or three
in a triangle, their centres a radius apart — and as small as they can be while
every region's words fit inside their region, clear of every outline. A region
not listed is drawn empty. Set names are drawn outside, above two circles, or
above the top one and below the other two of three. Roles: a set's `emphasis`
draws a heavier outline; a region's `emphasis` sets its words bold and fills the
region with the theme's first mark fill, along its exact outline.

Refused, each at its pointer: one set, or four or more (no arrangement of four
circles shows every region — use a `matrix`, sets as columns and items as rows);
an `in` naming an unknown set, empty, or naming a set twice; the same membership
twice; `subset_of` (a set inside another is `rings`); `size` or `value` (the
circles are equal on purpose: a Venn diagram says what overlaps, not how much);
`edges`. Words too long for their region at the largest size the width allows are
a `FitError` naming the region. See
[`reference/venn-frameworks.json`](reference/venn-frameworks.json),
[`reference/venn-data-roles.json`](reference/venn-data-roles.json),
[`reference/venn-parity.json`](reference/venn-parity.json) and
[`reference/venn-telemetry.json`](reference/venn-telemetry.json).

## A journey map

"What does a citizen go through to get X, and how does it feel" is a journey map:
one person's feeling across the stages of an experience, set against what they
do at each. The feeling line is the reason to draw it, and the feeling is a
**name**, not a score. That is `journey`:

```json
{
  "version": 1,
  "kind": "journey",
  "title": "The first week, as the new starter lives it",
  "feelings": ["lost", "neutral", "welcome"],
  "rows": [{"id": "does", "text": "Does"}, {"id": "needs", "text": "Needs"}],
  "stages": [
    {"text": "Day 1", "feeling": "welcome", "details": [
      {"row": "does", "text": "Meets the team"}, {"row": "needs", "text": "A buddy to ask"}]},
    {"text": "Day 2", "feeling": "lost", "role": "emphasis", "details": [
      {"row": "does", "text": "Waits for accounts"}, {"row": "needs", "text": "Access on day one"}]},
    {"text": "Day 5", "feeling": "welcome", "details": [
      {"row": "does", "text": "Ships a first change"}]}
  ]
}
```

`feelings` are the levels, **worst first**: each is a light guide across the map,
named once on the left, the worst at the bottom. Every stage names one, and its
point sits on that guide at the middle of its column; the heavy line passes
through every point and never overshoots, so two neighbours at one level are
joined by a flat segment. Stages are equal columns, left to right as written,
each under its bold heading. `rows` are optional detail bands under the line —
what the person does, where, what gets in the way — and a stage fills them with
`details`, a `{row, text}` per row; a row a stage does not name is an empty cell.
Without rows the map is the headings and the line. The `emphasis` stage — usually
the trough — has its column framed and its point drawn larger and solid. The
theme's `[journey]` section picks the line's, the guides' and the row rules' edge
roles.

Refused, each at its pointer: a number for a feeling, or a feeling not in
`feelings` (naming the closest); a stage with no `feeling` (it is a `flow` or a
`timeline`); `personas` (two lines cross and erase each other — one map per
person); `score`; `edges` (the stages are already in order); a detail in a row
that is not declared, or twice in one stage; one feeling or one stage. Budget:
7 stages, 5 feelings, 4 rows — past that, split it into two journeys, before and
after a hand-off. A word wider than its column is a `FitError`. See
[`reference/journey-parking-permit.json`](reference/journey-parking-permit.json),
[`reference/journey-first-week.json`](reference/journey-first-week.json),
[`reference/journey-bug-report.json`](reference/journey-bug-report.json) and
[`reference/journey-outpatient.json`](reference/journey-outpatient.json).

## A treemap

"What is in the bundle, and what dominates" is one total split into a few parts,
and a treemap says it as one block whose parts are visibly a whole. That is
`treemap`:

```json
{
  "version": 1,
  "kind": "treemap",
  "title": "Why /var is full on the build server",
  "unit": "GB",
  "groups": [
    {"id": "docker", "text": "`/var/lib/docker`"},
    {"id": "log", "text": "`/var/log`"}
  ],
  "parts": [
    {"text": "Dangling images", "amount": 61, "group": "docker", "role": "emphasis"},
    {"text": "Build cache", "amount": 38, "group": "docker"},
    {"text": "Journal", "amount": 9, "group": "log"},
    {"text": "App logs", "amount": 6, "group": "log"},
    {"text": "Other", "amount": 4, "role": "note"}
  ]
}
```

It is for **stating a small set of proportions you already know** — not for
exploring data. drawspec is not charting software, and `treemap` keeps to the
same line as `chart`: at most ten parts and one level of groups, and every part
labelled inside itself. Each part's `amount` (more than 0, in the document's
`unit`) sets its area; the gap between cells is taken from the cells and the
areas corrected for it, so every drawn share is the amount's share of the total.
Parts are laid out largest first — written order only breaks ties — and a
`note` part, the remainder, goes last. The block is the canvas width wide and
three fifths of it tall, a little taller if a label needs it, or the top-level
`height`. A part's words sit top-left in its cell with its amount under them;
`"values": false` drops the amounts. Roles: `emphasis` (the part the diagram is
about, not automatically the largest) is outlined heavier with its words bold;
`note` is a light dashed outline. A group is a captioned frame — its name and
total at the top — and its parts take the theme's mark fills, one per group in
the order written.

Refused, each at its pointer: one part (it is the total); an `amount` of 0 or
less; `value` (it is called `amount`); `percent` or `share` (drawspec computes
the share); a `group` that is not declared (naming the closest), or a group no
part names; duplicate group ids; a second level — `parts` or `groups` inside a
group, or `children`; `edges`; `fill`. Budget: 10 parts, 4 groups. A part too
small for its words at the tallest height tried is a `FitError` naming the part
and its pointer, and saying which parts to merge into one `note` part — never a
label outside its cell, never a legend. See
[`reference/treemap-bundle.json`](reference/treemap-bundle.json),
[`reference/treemap-disk.json`](reference/treemap-disk.json),
[`reference/treemap-oncall.json`](reference/treemap-oncall.json) and
[`reference/treemap-latency.json`](reference/treemap-latency.json).

## A sankey

"Where did the budget go" is one quantity split, and sometimes merged, along the
way, and a sankey draws each flow as a band whose thickness is its amount. That
is `sankey`:

```json
{
  "version": 1,
  "kind": "sankey",
  "title": "64 reserved cores, by team and workload",
  "unit": "cores",
  "nodes": [
    {"id": "search", "text": "Search team"},
    {"id": "pay", "text": "Payments team"},
    {"id": "api", "text": "APIs"},
    {"id": "batch", "text": "Batch jobs"},
    {"id": "idle", "text": "Reserved, idle", "role": "note"}
  ],
  "flows": [
    {"from": "search", "to": "api", "amount": 18},
    {"from": "search", "to": "batch", "amount": 14},
    {"from": "search", "to": "idle", "amount": 8},
    {"from": "pay", "to": "api", "amount": 16},
    {"from": "pay", "to": "idle", "amount": 8}
  ]
}
```

Like `chart` and `treemap`, it is for **stating a small set of flows you already
know** — not for exploring data: at most fourteen nodes, twenty-four flows and
four columns. A node's column is never written: each sits one column past the
longest way into it, and every end — a node nothing leaves — is in the last
column. A flow that skips a column passes through it in a slot of its own, never
across a bar. The order down each column starts from the written order and is
rearranged only to cross fewer bands. Each flow's `amount` (more than 0, in the
document's `unit`) sets its band's thickness, at one scale for the whole drawing,
and each bar is as tall as what passes through it; its total is written under its
name (`"values": false` drops them). The first column's labels sit left of their
bars, the last column's right, and an inner column's above its bar — never on a
band. Roles: a node's `emphasis` outlines its bar heavier and sets its words
bold, and `note` (the remainder: `Lost`, `Idle`) draws it lighter, with its
bands; a flow's `strong` draws the path the diagram is about darker.

Refused, each at its pointer and before any layout: a flow that closes a loop; a
middle node whose inflow is not its outflow (the message gives the difference —
add a flow to a named `note` node); a flow under 1/120 of the fullest column, a
band too thin to see (merge the small flows into one `Other`); a fifth column; a
flow from a node to itself, or a second flow between the same two nodes; an
unknown node (naming the closest), a duplicate id, a node no flow touches; an
`amount` of 0 or less; `value` (it is called `amount`), `percent`, `share`,
`column`, `rank`, a flow's `label`, `edges`. A label too wide to leave the bands
room at every width tried is a `FitError` naming the node. See
[`reference/sankey-budget.json`](reference/sankey-budget.json),
[`reference/sankey-tickets.json`](reference/sankey-tickets.json),
[`reference/sankey-cores.json`](reference/sankey-cores.json) and
[`reference/sankey-energy.json`](reference/sankey-energy.json).

## Asking for a wide drawing instead of a tall one

Reading direction is part of what a diagram says, and some processes read across
the page rather than down it. drawspec will not take an instruction to lay a
`flow` out horizontally — that is an arrangement, and arrangements are its output.
What it takes is the **constraint** the arrangement has to satisfy:

```json
{ "width": 760, "height": 150, "height_binding": true }
```

`height` on its own is advisory. With `height_binding`, it is a ceiling: the
direction choice now has two dimensions to compare instead of one, and a chain
that would have gone down goes across because down does not fit. Six steps in a
760-by-150 band come out as a band.

Two things follow from it being a constraint rather than a switch:

* **A ceiling nothing satisfies is a refusal, not a squeeze.** The elastic fit
  tries smaller type first; when the band is exhausted you get a message naming
  the height it reached and the height you asked for. It will not overlap boxes
  or shorten arrows to make the number come true.
* **Without a ceiling, down always wins, and that is correct.** A chain laid out
  downward is one box wide, so it fits every canvas — there is no width at which
  the tool should guess that you wanted it turned.

## When it refuses

A refusal is a designed outcome and the message is meant to be actionable. The
ones you will meet:

| It says | It means | Do this |
|---|---|---|
| A violation with a JSON pointer | A field is misspelt, missing, or not legal for this kind | Fix the field the pointer names. `additionalProperties` is closed everywhere, so a key that looks ignored is always an error instead. |
| `… is the tool's output, never its input` | The document tried to place, size or colour something | Say what you mean instead — a `role` rather than a `stroke`, a `kind` rather than an arrangement. |
| `… is past what one flow can be read at` | The document holds more than its kind's [readability budget](format.md#the-readability-budget) | Split it into an overview plus a detail diagram per part. A larger `width` does not lift it. |
| `… elements say 'emphasis', and a diagram may have 2` | More than two elements are marked as the focus | Keep the one or two the diagram is about and give the rest their ordinary role. |
| A fit refusal | The content cannot be drawn above the legibility floor at this width | Shorten the text, split the diagram, or raise `width` — in that order. A smaller type size is not offered, on purpose. |

## What it is not

drawspec draws simple, declarative diagrams well, and is the wrong tool for
several jobs it might look like it does: it is not a Graphviz replacement, not
charting software, not a drawing program, and not a rich-text system. The
[README](../README.md#what-it-is-not) says why for each, and it is worth reading
before you push it past its readability budget.

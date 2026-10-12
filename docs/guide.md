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
fields are legal. Thirty-four exist, and they fall into twenty-three families:

| Family | Kinds | What they are for |
|---|---|---|
| Graph | `flow`, `tree`, `cycle`, `lanes` | Things connected to other things: a process, a hierarchy, a loop that comes round again, a process drawn in one strip per party, a causal loop diagram. |
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
| Overlap | `venn` | Things that share: two or three sets as equal circles (four as equal ellipses), each region named by the sets it is in. |
| Experience | `journey` | How one person feels, stage by stage: a named feeling per stage as a line, over what they do there. |
| Share | `treemap` | The parts of one known total: each a rectangle by its area, labelled inside itself. |
| Portion | `pie` | The shares of one known total, a few of them: sectors of a circle, each labelled with its name and amount (a donut by a theme). |
| Quantity | `sankey` | Where a known quantity goes: nodes in derived columns, joined by bands as thick as their amounts. |
| Word problem | `barmodel` | Quantities in a word problem: bars of parts in proportion, braced — a part and a whole, a comparison, a ratio (the bar model, or tape diagram). |
| Bridge | `waterfall` | How one total became another: a start total, signed steps floating on the running sum, checked subtotals, an end total — the bridge chart. |
| Scale | `numberline` | Where values sit on one scale: points and ranges, each end in or out — an inequality, the pH scale, a spectrum. |
| Topic | `mindmap` | Things round one topic, as peers: a centre and its branches nested three levels deep, on both sides — revision notes, a brainstorm, a plan (a mind map). |
| Family | `familytree` | Who is whose child and partner: people, couples and their children a generation to a row, in the standard symbols — a family tree, or a pedigree in genetics. |
| Gauge | `meter` | How far one amount is along its scale: a progress bar, a fundraising thermometer, a dial with named bands, a bullet graph — alone or a few to a panel. |
| Status | `rag` | Things rated red, amber or green: workstreams or risks a row each, the rating a word and a shape (a colour only by the theme), a trend in words and a note — a highlight report, a risk register. |
| Time | `clock` | A time of day on an analogue face, for teaching it: two hands placed by the time, the numerals the lesson uses, the time in words under it, how long since an earlier time shaded round the face. |
| Reasoning | `argument` | Things said for and against a claim: reasons, objections, rebuttals and evidence by stance, co-premises under one bracket (an argument map). |

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
question?". These are the eleven, and the shape each one currently gets from the
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
| `io` | Data coming in or going out: a file read, a form filled in, a report sent | a parallelogram |
| `subroutine` | A process defined elsewhere — a routine with its own chart, a job run by name | a box with doubled sides |
| `store` | Where data rests: a database, a queue, a file kept | a drum (cylinder) |
| `person` | A human — a user, a customer, a member of staff — as against a system: C4's person, a use case's actor | a body with rounded shoulders under a round head, the name in the body |

`io`, `subroutine` and `store` are the flowchart symbols (ISO 5807, a data-flow
diagram's store) and `person` is the C4 person; all four are named only on a
`flow`, `tree` or `lanes` node — every other kind's boxes have a fixed vocabulary
of their own, and a `cycle` refuses them. A person's head sits above its body and
an arrow from above lands on the head, so leave room for it rather than for a
taller box: the words go in the body. `person` says *a human is here*; who
performs a step is still `actor` (see
[`reference/flow-person-helpdesk.json`](reference/flow-person-helpdesk.json),
[`reference/tree-person-escalation.json`](reference/tree-person-escalation.json)
and the C4-style [`reference/flow-classes-context.json`](reference/flow-classes-context.json)). Reach for one
only when the distinction is the point — a chart whose every box is `io` has
said nothing.

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
| `async` | `sequence` messages only: sent without waiting for an answer | solid, with an open head |

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

### The greys the default theme adds, and how to turn each off

The default theme is ink only, with three faint greys that carry order or
grouping the document already states. Each is the page's ink at part opacity
(`currentColor` with a `fill-opacity`), never a colour, so it follows a dark page
and prints as grey. **All three are on by default and each is optional**: one line
in your theme turns it off.

| What is grey | Key and default | Turn it off |
|---|---|---|
| A group's frame, a composite state, a sequence group (deeper nesting darker) | `[frames] tone = 0.05` | `[frames]` `tone = 0` (or `false`) |
| Every second lane of a swimlane diagram | `[lanes] stripe = 0.04` | `[lanes]` `stripe = 0` (or `false`) |
| The levels of a `pyramid`, the stages of a `funnel`, `rings` and a `stack`'s layers, lightest first in the order written | `[levels] shade = true` | `[levels]` `shade = false` |

```toml
version = 1
name = "outlines"

[frames]
tone = 0

[lanes]
stripe = 0

[levels]
shade = false
```

Graded levels take their tones from `[mark] ramp`, the same steps a matrix
`scale` is filled with: one step per level from the lightest, spread across the
ramp only when there are more levels than steps. The ramp's ceiling is what keeps
a label legible on the darkest level, on a white page and a dark one. A `note`
level stays unfilled, and so does a level whose role your theme already fills.

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

**An edge goes round a frame it has no end in.** One between two boxes outside a
group, a composite state or one of its regions is routed round that frame rather
than through it, and one that reaches a box inside crosses each frame's border
once. A line straight through reads as one that goes in and comes out again.

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

**Frames are washed, faintly.** A group's frame — and a composite state, and a
sequence diagram's group — is filled with a little of the page's ink
(`[frames] tone`, 0.05 by default): drawn as `currentColor` at part opacity, so it
follows a dark page and prints as a light grey, never a colour. A frame inside a
frame lays its wash over its parent's, so each level of nesting reads one step
darker, for `[frames] levels` levels (3); deeper frames are outlined only. A theme
that wants outlines only sets `[frames] tone = 0` (or `false`); see
[the greys the default theme adds](#the-greys-the-default-theme-adds-and-how-to-turn-each-off).

## Classes: boxes of a kind, with a key

A group says *these are inside this*; a **class** says *these are of one kind*,
wherever they sit. On a `flow`, a `tree` or `lanes`, declare 1 to 4 `classes`,
each `{id, text}`, and give a node `class` naming one:

```json
{
  "version": 1,
  "kind": "flow",
  "nodes": [
    {"id": "lending", "text": "Lending system", "class": "ours"},
    {"id": "payments", "text": "Card payments", "class": "external"}
  ],
  "edges": [{"from": "lending", "to": "payments", "label": "fines"}],
  "classes": [
    {"id": "external", "text": "Run by another organisation"},
    {"id": "ours", "text": "Built and run by the library"}
  ]
}
```

Each class takes the next fill of the theme's fixed sequence, in the order
declared — `[classes] fills`: a grey wash first (the ink at `[classes] tone`),
then dots, hatch and a grid, all faint and all ink, so greyscale and dark mode
keep them — and the key under the drawing shows each fill beside the class's
`text`. Declare first the class the reader should notice least: in a C4-style
context diagram that is the external systems, greyed by convention. A node with
no `class` stays plain, so a class is for the boxes that stand apart, not a
label every box must carry — and one class is enough: a context diagram that
greys only its external systems declares just that class, and the key still says
what the grey means.

Use a class for a grouping the reader must see across the whole drawing — who
runs a system, which team owns a service, which steps are automated — and a
`group` when the members belong *together* in one place. Refused, each at its
pointer: a `class` no class declares (naming the closest), a class no node uses
(a key entry pointing at nothing), more than 4 classes, a duplicate id, a class on
a `note` (no outline to fill) or a `group`, a class together with `status` on one
box (both mark it; a drawing of a change is about the change), and classes on a
`cycle`. See [`reference/flow-classes-context.json`](reference/flow-classes-context.json),
[`reference/flow-classes-teams.json`](reference/flow-classes-teams.json),
[`reference/tree-classes-board.json`](reference/tree-classes-board.json) and
[`reference/lanes-classes-claim.json`](reference/lanes-classes-claim.json).

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

## A causal loop diagram

How a system feeds itself is a causal loop diagram: a few variables, arrows saying
*more of this means more (`+`) or less (`-`) of that*, and the feedback loops those
arrows close, each named and marked **R** (reinforcing) or **B** (balancing). It is
a `flow` with a sign on every arrow:

```json
{
  "version": 1,
  "kind": "flow",
  "title": "Waiting lists",
  "nodes": [
    {"id": "wait", "text": "Time on the waiting list"},
    {"id": "acute", "text": "Emergency admissions"},
    {"id": "beds", "text": "Beds free for planned surgery"},
    {"id": "private", "text": "Patients who go private"}
  ],
  "edges": [
    {"from": "wait", "to": "acute", "polarity": "+", "delay": true},
    {"from": "acute", "to": "beds", "polarity": "-"},
    {"from": "beds", "to": "wait", "polarity": "-"},
    {"from": "wait", "to": "private", "polarity": "+"},
    {"from": "private", "to": "wait", "polarity": "-"}
  ],
  "loops": [
    {"text": "Deterioration", "nodes": ["wait", "acute", "beds"]},
    {"text": "Exit to private care", "nodes": ["wait", "private"]}
  ]
}
```

`polarity` is written as the edge's label (before any `label` of its own), so it is
placed like one, clear of every line and box; a theme's `[flow] polarity = "so"`
writes `s` and `o` instead of `+` and `−`. `delay: true` draws the double stroke
across the shaft. Each loop lists its variables in the order it runs, each joined to
the next — and the last to the first — by a signed edge. **Its type is derived, not
chosen**: an even number of `-` links reinforces, an odd number balances. The marker
says `R1`, `B1`, … numbered in the order written, with an arrow turning the way the
loop runs on the page, inside the loop (in no other loop's figure when there is
room), its name beside or under it; the gap between ranks is made taller to hold it.
`type` is optional and checked.

Research maps are an order of magnitude bigger than teaching diagrams and group
their variables into subsystems: `groups` work with `loops`, but draw one subsystem
per diagram — the budget is 15 nodes and 6 loops.

Refused, each at its pointer: a sign on some causal edges but not all (a
half-signed diagram is ambiguous); a sign on a `link`, `aside` or `weak` edge (no
causal direction); `delay` without a sign; `loops` with no signs; a loop whose nodes
are not joined in that order (naming the missing `a → b`), that names a node twice,
or has fewer than 2; the same loop twice; a `type` the signs contradict (naming the
count); `polarity`, `delay` or `loops` on any other kind. A marker with no room
inside its loop or beside its first link is a `FitError` naming the loop. See
[`reference/flow-loops-waiting.json`](reference/flow-loops-waiting.json),
[`reference/flow-loops-predators.json`](reference/flow-loops-predators.json),
[`reference/flow-loops-adoption.json`](reference/flow-loops-adoption.json) (signs
as `s`/`o`) and [`reference/flow-loops-town.json`](reference/flow-loops-town.json)
(with groups).

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

**Orthogonal regions.** When parts of one composite are current at the same time
— an order paid for while it is packed, caps lock and num lock — give the
composite `regions` in place of `members`: a list of `{members, initial}`, two
to four of them. The regions are drawn side by side (stacked when they do not fit
across) and divided by dashed lines, each with its own initial dot; entering the
composite enters every region at its `initial`, and a transition from it leaves
all of them. A transition from the composite with no `event` is the completion
transition, taken once every region is done:

```json
{"id": "processing", "text": "Processing", "regions": [
  {"members": ["authorising", "captured"], "initial": "authorising"},
  {"members": ["picking", "packed"], "initial": "picking"}
]}
```

Refused at their pointers: a state in two regions, a region with no `initial` or
one outside it, `members` beside `regions`, an `initial` on the composite itself
(each region names its own), one region alone, more than four (budget), and a
transition from one region of a composite into another (they run at once, so
neither can hand the machine to the other). Entering the composite, or a state
inside one region, starts the others at their own `initial`. See
[`reference/states-regions-order.json`](reference/states-regions-order.json),
[`reference/states-regions-player.json`](reference/states-regions-player.json) and
[`reference/states-regions-keyboard.json`](reference/states-regions-keyboard.json)
(three regions, stacked).

**Fork and join bars.** To say where each region starts, or that the machine
leaves only once every region has finished, give a state `"role": "fork"` or
`"role": "join"` and no `text`: it is drawn as UML's short thick bar, across the
flow (upright when the machine reads left to right), long enough to reach over
the states it splits into or gathers, each arrow dropping straight onto its state.
A fork has exactly one transition in and two or more out, each into a different
region of one composite; a join has two or more in, one from each region, and
exactly one out. A region every fork reaches needs no `initial` — the fork says
where it starts — but one the machine can enter any other way still does.

```json
{"id": "start", "role": "fork"},
{"from": "basket", "to": "start", "event": "checkout"},
{"from": "start", "to": "authorising"},
{"from": "start", "to": "picking"}
```

A bar is passed at once, so it waits for nothing: the transitions out of a fork
or into a join take no `event` or `guard` (UML forbids both; put them on the
transition into the fork, or into each state before the join), nor does the way
out of a join take an `event`; an `action` is fine anywhere. Refused at their
pointers, too: `text` on a bar, a fork with a second way in or fewer than two
out (and the join's mirror image), arrows into two states of one region or into
states in no region, a bar as `initial`, `final` or a region's `initial`, a loop
on a bar, and more than four bars (budget). See
[`reference/states-fork-order.json`](reference/states-fork-order.json),
[`reference/states-fork-release.json`](reference/states-fork-release.json)
(three regions) and
[`reference/states-fork-onboarding.json`](reference/states-fork-onboarding.json)
(read across, bars upright).

Refused, each at its pointer: a state no transition reaches from `initial` (a
bug in the machine — add the transition or delete the state); a `final` state
with an outgoing transition; `final` naming a group; two transitions leaving one
state on the same event and guard for different states (give them guards); a
loop on a group, or a third loop on one state. See
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
calls nest; you never write one. A call nobody answers has no bar. To say a
message is sent without waiting — a queue, an event, a text message — give it
`role: "async"`: UML's solid line with an open, stick head. It opens no bar, and a
`weak` reply answering it is refused (an answer that comes later is a message of
its own). A message `from` and `to` the same participant
is a hook on the right of its lifeline, and a `note` is set on its message's row
in one column right of the last lifeline.

`fragments` frame a run of messages, by the ids of the first and last: `loop`,
`opt`, `alt` or `par`, written in the frame's tab, with `text` as the condition
beside it. An `alt` or `par` may be divided by `else` — `[{"at": "<id>", "text":
…}]`, a dashed line above that message. If a reply inside one branch of an `alt`
answers a call made before the frame, the bar runs on to the last answer in the
frame. `groups` frame a run of neighbouring lifelines, named at the top.
Participant roles are `step`, `emphasis`, `note` for an outside system drawn
as words with no box, or `actor` for a person — the UML stick figure over the
name, the names of all heads on one line and the lifeline under them (`person`
is refused, pointing here); the theme's `[sequence]` sets the bar's width and the role
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
[`reference/sequence-checkout.json`](reference/sequence-checkout.json); for
actors and async messages,
[`reference/sequence-actor-signin.json`](reference/sequence-actor-signin.json),
[`reference/sequence-async-export.json`](reference/sequence-async-export.json) and
[`reference/sequence-actor-handover.json`](reference/sequence-actor-handover.json).

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
is the edge role the line between two lanes is drawn in, and `[lanes] stripe`
(0.04 by default; `stripe = 0` or `false` in a theme for none) washes every second lane with that share of the
page's ink, so five or six lanes read as bands.

### Phases

A cross-functional flowchart's second axis is its **phases**: stretches of the
process every lane passes through — *Request*, *Order*, *Pay*. `phases` names them
in the order the process runs, and each lists its steps:

```json
"phases": [
  {"text": "Request", "members": ["submit", "approve", "fix"]},
  {"text": "Payment", "members": ["pay"]}
]
```

They are drawn as a band along the lanes' outer edge — over the strips when they
run across the page, beside them when they run down it — with each phase's name in
its cell, and a light dashed line (`[lanes] phase`, `aside` by default) across
every lane between one phase and the next. Both orientations draw them.

Why the steps, not the first step of each phase: the steps are what you know when
you write the document, and what the drawing shows is decided by them. Each phase's
steps are placed after every step of the phases before it, so the phases never
interleave and you never have to predict where the layout puts a step. A returning
arrow into an earlier phase — *changes requested* sending work back to *Build* — is
fine: it is drawn as a return. With `phases`, **every step is in exactly one**.

Refused, each at its pointer: a member that is not a step (naming the closest id);
a step in two phases (phases do not overlap); a step in no phase; fewer than 2
phases, or more than 6; and an arrow from a later phase back into an earlier one
that is not a loop — nothing leads back from where it lands — because then the
phases are out of order or the step is in the wrong one. See
[`reference/lanes-phases-purchase.json`](reference/lanes-phases-purchase.json),
[`reference/lanes-phases-release.json`](reference/lanes-phases-release.json) and
[`reference/lanes-phases-loan.json`](reference/lanes-phases-loan.json) (rows).

### Refusals

Refused, each at its pointer: a node with no `actor` (the message points you back
to `flow`); an actor not in `lanes`, naming the closest lane; a lane in `lanes`
that no node names, or one listed twice; `groups`, `bands` and `centre`, because
a lane is already the container and a frame or band would cross it; and the
`group` node role. Budget: a flow's 15 nodes and 16 edges, 6 lanes, counted
from the actors when `lanes` is omitted, and 6 phases. See
[`reference/lanes-disclosure.json`](reference/lanes-disclosure.json),
[`reference/lanes-tender.json`](reference/lanes-tender.json),
[`reference/lanes-expense.json`](reference/lanes-expense.json),
[`reference/lanes-onboarding.json`](reference/lanes-onboarding.json) and
[`reference/lanes-appointment.json`](reference/lanes-appointment.json), which draws
the flowchart symbols (`io`, `subroutine`, `store`).

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

## A funnel that says how many

A `funnel`'s stages narrow to an outcome, and the point is what is lost on the way. Give
every stage an `amount` and it says how much: each stage writes its count under its
name, and from the second on the share of the stage before that reached it.

```json
{
  "version": 1,
  "kind": "funnel",
  "unit": "people",
  "stages": [
    {"text": "Saw the advert", "amount": 4200},
    {"text": "Applied", "amount": 310},
    {"text": "**Started**", "amount": 5}
  ]
}
```

The second stage reads *310 people · 7.4% kept*. The share is derived, never written,
and the taper stays the funnel's own uniform one: widths in proportion would make it a
bar chart, and a stage keeping 2 % would be too thin to hold its name. `"values": false`
leaves the numbers out. Amounts go on every stage or none, never rise from one stage to
the next (things joining part-way are a `flow` or a `sankey`), and are above zero; a
`unit` needs amounts to follow. Each is refused at its pointer. See
[`reference/funnel-applications.json`](reference/funnel-applications.json).

## Naming a quadrant's quarters

A quadrant's most recognisable part is often the names of its four quarters — *Do
now*, *Plan it*, *Drop it*, *Hand it on* — and of the two ends of each axis. Both are
words in the document, not drawing:

```json
{
  "version": 1,
  "kind": "quadrant",
  "axes": {
    "horizontal": {"label": "How urgent", "ends": ["Can wait", "Today"]},
    "vertical": {"label": "How important", "ends": ["Minor", "Matters"]}
  },
  "quadrants": ["Do now", "Plan it", "Drop it", "Hand it on"],
  "positions": [{"text": "Payroll file rejected", "across": 0.9, "up": 0.85}]
}
```

`quadrants` is exactly four names, **top right first, then counter-clockwise** — top
left, bottom left, bottom right — the order Mermaid numbers them in. Each is written
faint in its quarter's outer corner, behind the points; `""` leaves a quarter unnamed.
An axis's `ends` are its low and high words, as on a `numberline`, written at the two
ends of the axis. Refused: `quadrants` not four, more than two `ends`, and
`categories` on a quadrant axis. See
[`reference/quadrant-priorities.json`](reference/quadrant-priorities.json).

## Bars on their side

A bar chart whose categories are sentences — *Report a pothole or broken street
light* — has no room for them under upright bars. Put the `categories` on the
**vertical** axis instead and the bars lie down: each category is a row, the first
at the top (an ordered bar chart reads like a list), its name on the left, and each
bar grows right from zero.

```json
{
  "version": 1,
  "kind": "chart",
  "axes": {
    "horizontal": {"label": "Calls", "unit": "thousands"},
    "vertical": {"label": "Reason", "categories": ["Missed bin collection", "Parking permit or fine"]}
  },
  "series": [{"name": "Calls", "mark": "bar", "data": [[8.4, 1], [4.7, 2]]}]
}
```

Each point is turned round: `[amount, position]`, the position naming the category,
1 for the first. Names wrap to about a third of the width; the numbers are written
past the bars' ends (inside each segment, when series share a `stack`), at the
precision you wrote them: the most decimals any value carries, for every bar, so
`8.4` beside `12` prints `8.4` and `12.0` (at most three; upright bars and line
points follow the same rule). Every series
must be a `bar`, amounts start at zero, and the category axis takes no `min`/`max`:
each is refused at its pointer. See
[`reference/chart-across.json`](reference/chart-across.json).

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

A task's `done`, a number from 0 to 100, is how much of it is complete — drawn as a
solid band through the middle of its bar from the start, the progress line MS Project
draws. It is ink, not colour: the theme's `[gantt] done` sets how strong (0.7 by
default), so the band reads in greyscale and on a dark page. Pair it with a `today`
mark and the plan says where each task should be and where it is. See
[`reference/gantt-progress.json`](reference/gantt-progress.json).

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
with no `text`; `progress` (the field is `done`); `done` outside 0–100 or on a
milestone; and a newline in a
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

"What do these share" is a Venn diagram, and with two to four sets it needs no
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

**Four sets** are four equal ellipses, not circles: four circles cannot draw the
two diagonal pairs, and four ellipses show all fifteen regions. The middle two
cross as an X with their names above; the outer two lie lower, their names under
their outer lobes. The smallest regions are small, so with four sets a region's
text is a count or a word or two — at most 12 characters, markup aside — the
research figure with a number in every region, or the ikigai figure with only the
pairs and the centre named and the rest left empty:

```json
{
  "version": 1,
  "kind": "venn",
  "title": "Ikigai: where four questions meet",
  "sets": [
    {"id": "love", "text": "What you love"},
    {"id": "good", "text": "What you are good at"},
    {"id": "need", "text": "What the world needs"},
    {"id": "paid", "text": "What you can be paid for"}
  ],
  "regions": [
    {"in": ["love", "good"], "text": "Passion"},
    {"in": ["love", "need"], "text": "Mission"},
    {"in": ["need", "paid"], "text": "Vocation"},
    {"in": ["good", "paid"], "text": "Profession"},
    {"in": ["love", "good", "need", "paid"], "text": "Ikigai", "role": "emphasis"}
  ]
}
```

Refused, each at its pointer: one set, or five or more (no drawing of five sets
shows every region legibly — use a `matrix`, sets as columns and items as rows);
region text past 12 characters with four sets;
an `in` naming an unknown set, empty, or naming a set twice; the same membership
twice; `subset_of` (a set inside another is `rings`); `size` or `value` (the
circles are equal on purpose: a Venn diagram says what overlaps, not how much);
`edges`. Words too long for their region at the largest size the width allows are
a `FitError` naming the region. See
[`reference/venn-frameworks.json`](reference/venn-frameworks.json),
[`reference/venn-data-roles.json`](reference/venn-data-roles.json),
[`reference/venn-parity.json`](reference/venn-parity.json),
[`reference/venn-telemetry.json`](reference/venn-telemetry.json), and for four sets
[`reference/venn-four-ikigai.json`](reference/venn-four-ikigai.json),
[`reference/venn-four-ponds.json`](reference/venn-four-ponds.json) and
[`reference/venn-four-launch.json`](reference/venn-four-launch.json).

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

## A number line

"Which values of x satisfy both" is a question about one scale — where each end
of a range is, whether the end belongs to it, and which way it runs on — and a
number line says it in the form every maths textbook uses. That is `numberline`:

```json
{
  "version": 1,
  "kind": "numberline",
  "title": "Where x > −1 and x ≤ 4 both hold",
  "axis": {"min": -4, "max": 7, "step": 1},
  "ranges": [
    {"from": -1, "from_open": true, "text": "x > −1"},
    {"to": 4, "text": "x ≤ 4"},
    {"from": -1, "to": 4, "from_open": true, "text": "both: −1 < x ≤ 4", "role": "emphasis"}
  ]
}
```

**`numberline` or `timeline`?** A `timeline` is events in order — *when* things
happened — each a box with its date under the line, and `at` only spaces them out.
A number line is *where values sit* on a measured or named scale, and what it can
say that a timeline cannot is whether a range's end is in it (`x ≤ 4`) or out of it
(`x < 4`), and that a range runs on for ever. Inequalities, interval notation, the
pH scale, a temperature band, positions on a policy spectrum, a tense relative to
*now* in a language class: a number line. A project's history, a release
schedule, a sequence of events: a timeline (or a `gantt`, for work that overlaps).

The `axis` runs from `min` to `max` (numbers, `min` < `max`) across the canvas with
an arrowhead at each end, ticked every `step` with the numbers under the ticks; with
no `step`, one a reader can count in is chosen. `label` and `unit` are written under
the numbers. For a scale that is named rather than measured, give `ends` — the low
and the high end's words, written under the arrowheads — and no numbers are drawn;
points and ranges are still placed by number between `min` and `max`, so only the
order and the gaps count.

`points` are dots on the line: filled, or hollow with `"open": true` (the value
itself is excluded — a hole). Their words go directly above the dot when they fit,
otherwise directly under the numbers, then in rows further out joined to the dot by
a thin leader — so fifteen substances on the pH scale settle into alternating rows,
as the textbook draws them. `ranges` are stacked in tracks above the line in the
order written, the last nearest it — write the answer last. Each is a heavy line
with its words centred over it. `from_open` / `to_open` exclude an end; an end left
out runs on past the axis, drawn as an arrow. Roles for both: `emphasis` (the
solution set, the point that matters: a thicker bar or a larger dot, bold words) and
`note` (context: a dashed range, a smaller dot).

How an excluded end looks is house style, not content: the theme's
`[numberline] ends` draws `"dots"` (filled in, hollow out — the default, and the
school convention in most of the world) or `"brackets"` (`[` in, `(` out, as US and
college algebra texts do). Set it once in a course's theme; the documents do not
change. A single point is a dot either way.

Refused, each at its pointer: a value outside `min`–`max` (widen the axis, or leave
the end out so it is drawn as an arrow); a range with neither `from` nor `to` (the
whole line — say it in the title); `to` not after `from` (a single value is a
point); `from_open` without `from`, `to_open` without `to`; two points at one value;
`ends` with `step` or `unit`, or more than two ends; a step that makes more than 30
ticks; a string where a number belongs (a date is a `timeline`); `value` (it is
`at`), `edges`, `series`, `axes` (two values per item is a `scatter`). Budget: 15
points, 4 ranges. Tick numbers that touch, two dots too close to tell apart, or a
point's words with no row within five of the line that keeps clear of the others
are a `FitError`. See
[`reference/numberline-inequality.json`](reference/numberline-inequality.json),
[`reference/numberline-interval-us.json`](reference/numberline-interval-us.json)
(drawn with brackets by a course theme),
[`reference/numberline-ph.json`](reference/numberline-ph.json),
[`reference/numberline-tense.json`](reference/numberline-tense.json) and
[`reference/numberline-spectrum.json`](reference/numberline-spectrum.json).

## A bar model

"12 of the 30 children walk; how many come by bus?" is a word problem, and the
bar model — the *tape diagram* of US curricula, the Singapore bar model of primary
teaching — is how it is drawn before the sum is written: a bar for the quantity,
split into parts, a brace for what a stretch adds up to, a `?` for what is asked.
That is `barmodel`:

```json
{
  "version": 1,
  "kind": "barmodel",
  "title": "How many children come by bus?",
  "bars": [
    {"id": "class", "parts": [
      {"amount": 12, "text": "walk: 12"},
      {"amount": 18, "text": "bus: ?", "role": "emphasis"}
    ]}
  ],
  "braces": [{"over": ["class"], "amount": 30, "text": "30 children"}]
}
```

The one rule the drawing keeps is the one teachers insist on: **lengths are in
proportion**. Up to three `bars` run top to bottom from one left edge, each named
by its `text` in a column at the left, and one scale serves them all — the longest
bar fills the width — so a comparison is read by length. Each bar has up to eight
`parts`, left to right, and every part has a size: an `amount` (more than 0, its
length in proportion, written in it unless its `text` says otherwise) or `units`
(that many equal boxes, its `text` in each — groups to multiply, the shares of a
ratio, the fifths of a fraction; at most twelve boxes a bar). A document is all
amounts or all units. **The unknown still has a size**: write its `amount` and
`"text": "?"`, so the bar is drawn to the answer and the reader sees the question.
Roles: `emphasis` (the part asked about: filled, bold) and `note` (a part that is
not there — the stretch a shorter bar lacks in a comparison: dashed).

`braces` say what a stretch adds up to. `over` names ids: side-by-side parts of one
bar, or a whole bar — braced above it, or under it for the last of several bars, so
a comparison's two bars are braced on their outer sides — or several consecutive
bars, braced upright at their right (a ratio's total). Braces on one side that would
touch stack outwards, the narrowest nearest the bar. A brace's `amount` is
**checked**: the parts it spans must add up to it, and with units every brace with an
amount must make one unit worth the same. Its `text`, if given, is what is written —
`"30 children"`, `"?"`.

Refused, each at its pointer: a part with no size, or both; amounts and units in one
document; a brace amount that is not the sum of what it spans, or a second brace that
makes a unit worth a different amount; a brace over parts of two bars, parts not side
by side, bars not consecutive, or a bar and a part together; a brace with neither
`amount` nor `text`; an unknown id (naming the closest); duplicate ids; a document of
one part; `total` on a bar (it is a brace); `value` (it is `amount`); `edges`, `axes`, `series` (a bar model has
no axis — that is a `chart`). Budget: 3 bars, 8 parts a bar, 6 braces. A part too
narrow for its words at the scale the longest bar sets is a `FitError` naming it. See
[`reference/barmodel-bus.json`](reference/barmodel-bus.json),
[`reference/barmodel-pages.json`](reference/barmodel-pages.json),
[`reference/barmodel-ratio.json`](reference/barmodel-ratio.json),
[`reference/barmodel-fraction.json`](reference/barmodel-fraction.json) and
[`reference/barmodel-savings.json`](reference/barmodel-savings.json).

## A waterfall

A budget paper explains how one number became another — last year's deficit to this
year's plan, a forecast to an outturn — as a **waterfall**, or bridge chart: a total,
the steps that moved it, and the total it arrived at. That is `waterfall`:

```json
{
  "version": 1,
  "kind": "waterfall",
  "title": "How the council's budget gap closed",
  "axis": {"label": "Budget gap, £ million"},
  "bars": [
    {"text": "Autumn forecast", "total": 18.4},
    {"text": "Council tax rise", "amount": -4.2},
    {"text": "Grant settlement", "amount": -6.5},
    {"text": "Social care demand", "amount": 5.1},
    {"text": "Savings programme", "amount": -7.6, "role": "emphasis"},
    {"text": "Remaining gap", "total": 5.2}
  ]
}
```

Each of the 3 to 12 `bars`, left to right, is one of two things. A **`total`** stands
on zero and runs to its value: the first bar is one, the last is one, and one in
between is a **subtotal**. An **`amount`** is a signed step (not 0) that floats from
the running sum to the running sum plus it. **Every total after the first is
checked**: it must be the running sum, and one that is not is refused with the sum
and the difference — the chart would otherwise show a step that is not there. The
end total is written, not derived: you state the number the reader is told, and
drawspec says whether the steps get there.

Every bar's number is written beyond its far end — above a rise or a positive total,
under a fall or a negative one — the steps signed (`+5.1`, `−7.6`, with a true minus),
all with as many decimals as the most precise figure. Thin dashed connectors join each
bar to the next at the running sum. Totals, rises and falls take the theme's first
three mark fills, so they are told apart in greyscale too. A bridge entirely below
zero (a deficit getting smaller) hangs from the zero line; one that crosses zero is
drawn across it. `axis.label` is required: what the numbers are, with their unit.
`role: "emphasis"` marks the step the chart is about (a heavier outline, a bold
number).

Refused, each at its pointer: a first bar that is not a `total`; a last bar that is
not one (the refusal says what the steps add up to); a total that is not the running
sum; a total straight after a total; a bar with both `total` and `amount`, or
neither; an `amount` of 0; `value` (it is `amount` or `total`), `subtotal`, `start`,
`end` (each is a `total`), `unit` (it goes in the axis label), `series`, `axes` (a
`chart`), `edges`. Budget: 12 bars — split a longer bridge at a subtotal. A name with
a word wider than its bar's band, or a number wider than the band, is a `FitError`. See
[`reference/waterfall-budget-gap.json`](reference/waterfall-budget-gap.json),
[`reference/waterfall-deficit.json`](reference/waterfall-deficit.json) (every bar below
zero, two subtotals),
[`reference/waterfall-cash.json`](reference/waterfall-cash.json) and
[`reference/waterfall-result.json`](reference/waterfall-result.json) (crossing zero).

## A pie

The pie chart is what a class draws from a tally and what a budget-day leaflet prints:
one total, split into a few shares, each sector labelled. That is `pie`:

```json
{
  "version": 1,
  "kind": "pie",
  "title": "How the 30 pupils in 6B travel to school",
  "unit": "pupils",
  "parts": [
    {"text": "Walk", "amount": 12},
    {"text": "Car", "amount": 8},
    {"text": "Bus", "amount": 6},
    {"text": "Bike", "amount": 4}
  ]
}
```

**Use it for a few known proportions, not to explore data.** It reads well when one or
two parts dominate or a share is a nice fraction (½, ¼); for parts of similar size, for
comparing two totals, or for more than eight parts, a bar `chart` or a `treemap` says
it better. The limits say so: 2 to 8 `parts`, none under 2% of the total.

Each part is a `text` and an `amount` more than 0, as it is in the source — a count
from a tally, a sum of money. **Shares are computed, never written**: each angle is the
part's share of the sum of the amounts, so the drawing cannot disagree with the
numbers, and `percent`, `share`, `angle` and `total` are refused. Percentages are the
one case that can disagree — they claim a total of 100 — so with `"unit": "%"` the
amounts must add up to 100 within one point of rounding. `unit` is written after each
amount (`12 pupils`, `27%`); `"values": false` writes the names alone.

Sectors run clockwise from twelve o'clock in the order written. Past eight parts, keep
the largest and merge the rest into one `"role": "note"` part — `Everything else` —
drawn last, unfilled and dashed; there is at most one. `emphasis` marks the part the
chart is about (a heavier outline, bold words).

A sector is identified by its **label**, never by its fill: each carries its name and
amount, inside it when they fit, otherwise beside the circle on a leader from the
middle of its arc, the outside labels kept in angle order on their side and never
touching. Fills are the theme's mark patterns in turn, only so that touching sectors
differ — there is no legend to match them against, so a reader in greyscale loses
nothing.

**A donut is house style**, not content: a theme with `[pie] shape = "donut"` draws
every pie in a report as a ring, with every label outside. The documents do not change.

Refused, each at its pointer: more than 8 parts (with the advice above); a part under
2% (merge it into the `note` part); percentages more than one point off 100; a second
`note` part; one part; `value` (it is `amount`), `percent`, `share`, `angle`, `total`;
`groups` (a `treemap`); `series`, `axes` (a `chart`); `donut`, `hole` (the theme);
`edges`. Labels beside the circle that leave it too small to read are a `FitError`.
See [`reference/pie-travel.json`](reference/pie-travel.json),
[`reference/pie-trip.json`](reference/pie-trip.json) (nice fractions),
[`reference/pie-spending.json`](reference/pie-spending.json) (percentages, with a
remainder) and [`reference/pie-team-week.json`](reference/pie-team-week.json) (a donut,
by [`reference/themes/donut.toml`](reference/themes/donut.toml)).

## A mind map

Revision notes, a brainstorm, the plan for a move: one topic in the middle and what
belongs to it radiating out, every main branch a peer. A `tree` holds the same
hierarchy but ranks it from a root at one edge, which says *this comes first*; a mind
map says none does. That is `mindmap`:

```json
{
  "version": 1,
  "kind": "mindmap",
  "title": "Moving in March",
  "centre": "The move",
  "branches": [
    {"text": "Before", "branches": [{"text": "Give notice"}, {"text": "Book the van"}]},
    {"text": "Paperwork", "branches": [{"text": "Change of address"}, {"text": "Council tax"}]},
    {"text": "The day", "role": "emphasis", "branches": [{"text": "Meter readings"}]},
    {"text": "After", "branches": [{"text": "Unpack the kitchen first"}]}
  ]
}
```

`centre` is the topic, drawn as the one strongly boxed element. `branches` are the main
branches, 2 to 8, each a `text` and optionally its own `branches`: nested, at most three
levels below the centre (a branch, a twig, a leaf) and 30 in all. **The nesting is the
structure**, so there are no edges to write and none to get wrong.

**Placement is drawspec's.** The main branches go clockwise from the top right in the
order written — down the right side, then up the left — and the split between the two
sides is the one that balances them best, the first branch always on the right. Under a
branch, its own branches read top to bottom in the order written, on both sides. So an
**ordered plan** — an essay's introduction, sections and conclusion — is written in that
order, and a numbered lead (`1. Introduction`) says the order aloud. `side` is refused:
which side a branch goes is a coordinate.

Main branches are boxed lightly, in bold. A twig or a leaf sits on its line, which runs on
under its words, the mind-map convention; a theme's `[mindmap] boxes = true` boxes them
instead. Lines are smooth and thin from the centre outwards, by the theme's `[mindmap]
taper`. Colour per branch, which the study guides recommend, is a theme's matter; nothing
in the drawing depends on it.

Roles: `step` (the default); `emphasis` — the branch the map is about, bold, its line and
every line back to the centre drawn heavy; `note` — context, not content (sources, ideas
parked), faint words on a dashed line, and so is everything under it.

**A cross-link is a different diagram.** Arrows between ideas on different branches, each
labelled with how they relate, make a *concept map*: draw that as a `flow` with labelled
edges. `edges`, `links` and an `id` on a branch are refused with that suggestion.

Refused, each at its pointer: fewer than 2 or more than 8 main branches; more than 30 in
all (the 31st is named; split into an overview map and a map per branch); a fourth level;
an empty `branches` list or empty words; `edges`, `links`, `id`, `side`; a branch role
with a shape (`decision`, `terminal`). When the words do not fit the width, the twigs and
leaves of the branch reaching furthest out wrap narrower first; when no width works,
`FitError` names the longest. See
[`reference/mindmap-photosynthesis.json`](reference/mindmap-photosynthesis.json) (revision
notes, three levels), [`reference/mindmap-essay-plan.json`](reference/mindmap-essay-plan.json)
(an ordered plan), [`reference/mindmap-moving-house.json`](reference/mindmap-moving-house.json)
and [`reference/mindmap-offsite.json`](reference/mindmap-offsite.json) (eight branches).

## An argument map

Law and critical-thinking courses, debating clubs and policy units draw the same
figure: one contention at the top, the reasons for it beneath, the objections to those
reasons, and the replies to the objections. A `tree` holds the hierarchy but cannot say
the two things that make it an argument — which way each box bears, and that two
reasons count only together. That is `argument`:

```json
{
  "version": 1,
  "kind": "argument",
  "title": "Did the email of 3 May form a contract?",
  "claim": "A binding contract was formed on 3 May",
  "points": [
    {"id": "offer", "on": "claim", "stance": "for", "text": "The quote was an offer"},
    {"id": "accept", "on": "claim", "stance": "for", "with": ["offer"], "text": "The buyer's email accepted it"},
    {"id": "price", "on": "claim", "stance": "for", "text": "Price was agreed: consideration given"},
    {"id": "counter", "on": "accept", "stance": "against", "text": "It asked for a later date: a counter-offer"},
    {"id": "enquiry", "on": "counter", "stance": "against", "role": "emphasis", "text": "It only asked whether the date could move"}
  ]
}
```

`claim` is the contention, drawn at the top in the heavy outline; a qualifier
(*probably*) is a word in it. Each point names the box it bears on with `on` —
`"claim"` or another point's `id` — and its `stance`: `for` or `against` that box.
There is no third stance: a **rebuttal is an `against` on an `against`**, and a
warrant or its backing (Toulmin's slots) is a `for` on the point it supports. Points
hang below the box they bear on, siblings in the order written, down to four levels.

**Stance is drawn twice**, so a greyscale print still says it: a tag in each box's
top margin, `because` or `but` (read aloud, a chain goes *claim, because …, but …,
but …*), and an `against` box filled with a faint hatch. A theme's `[argument]`
section changes the words and the pattern.

**Co-premises** are points that support only together — an offer *and* its
acceptance. Write `with` on any member, naming the others (same `on`, same `stance`;
at most four in a group); they are drawn side by side under one bracket, with one
connector to the box they support. Every separate reason has its own connector, so
the arrows into a box count its independent reasons.

**An objection to how co-premises combine** — the *inference objection* — attacks the
step from the group to its box, not any one premise. `on` names one box, so it is
refused with what to write instead, which is what argument-mapping guides advise:
state the premise that links them (*homework is only worth setting for what it
adds*) as a point `with` them, and put the objection `on` that point.
[`reference/argument-homework.json`](reference/argument-homework.json) does exactly
this.

Roles: `step`; `emphasis` — the decisive point, heavy outline and connector, bold;
`note` — **evidence or a source**, not a reason (a study guide's *basis* box): words
without a box, on a dashed connector, still tagged by stance.

Refused, each at its pointer: an `on` that names no point, or names itself, or goes
round in a circle; a missing `stance` (a remark that is neither belongs in the
`caption`); `rebuttal` or `objection` as a stance; `with` naming an unknown point, or
one with a different `on` or `stance`; a group of five; `on` naming a co-premise group
(a list, or `a+b`); `edges`; a duplicate id, or `claim` as an id; a fifth level;
empty words; a role with a shape. Budget: 15 points. When the tree is too wide, the
points wrap narrower; when no width works, `FitError` names the widest row — split the
map, an overview with the top-level reasons and objections and a map per contested
reason. See [`reference/argument-contract.json`](reference/argument-contract.json),
[`reference/argument-congestion.json`](reference/argument-congestion.json) (with
evidence), [`reference/argument-readmissions.json`](reference/argument-readmissions.json)
and [`reference/argument-homework.json`](reference/argument-homework.json).

## A family tree, or a pedigree

A biology lesson on inheritance, a genetics clinic's letter and a history lesson on a
dynasty draw the same figure: people, who partnered whom, and the children of each
couple, a generation to a row. Genetics and medicine call it a **pedigree**; everyone
else a family tree. A `tree` cannot draw it — a child there has one parent, and a
partner who married in has none — so it is `familytree`:

```json
{
  "version": 1,
  "kind": "familytree",
  "title": "A recessive condition skips a generation",
  "people": [
    {"id": "gf", "sex": "male"},
    {"id": "gm", "sex": "female", "status": "carrier"},
    {"id": "dad", "sex": "male", "status": "carrier"},
    {"id": "aunt", "sex": "female"},
    {"id": "mum", "sex": "female", "status": "carrier"},
    {"id": "c1", "sex": "female"},
    {"id": "c2", "sex": "male", "status": "affected", "proband": true}
  ],
  "couples": [
    {"between": ["gf", "gm"], "children": ["dad", "aunt"]},
    {"between": ["dad", "mum"], "children": ["c1", "c2"]}
  ]
}
```

Every person has an `id` and a `sex`, which is the symbol: a square (`male`), a circle
(`female`) or a diamond (`unknown`). Each couple names its two partners in `between`
and its `children` in birth order. **Nothing else places anyone**: a child is one row
below its parents, a partner who married in takes their partner's row, the rows are
numbered I, II, III at the left and people 1, 2, 3 left to right in each, under the
symbol — so "II-3" in a letter is a number drawspec keeps right when someone is
added. `generation` and `number` are refused by name. `text` goes under the number:
a name, an age, a test result.

**The standard's marks.** `status` is the one trait the tree tracks: `affected` fills
the symbol, `carrier` draws the theme's carrier mark (`[familytree] carrier`: a dot in
the middle, the standard's, or `half`, the exam pedigree's half-shaded symbol), and a
key under the drawing names the ones used — no colour, so greyscale holds. `deceased`
strokes through the symbol; `proband` (one per tree) is an arrow at the lower left with
a `P`, `consultand` the arrow alone; `adopted` puts brackets round the symbol and a
dashed line down to it, from the couple that raised them; `pregnancy: ongoing` writes
a `P` in it, and `pregnancy: loss` draws a small triangle instead. Under the 2022
revision of the standard the symbol shows **gender**: write `gender` (`man`, `woman`,
`nonbinary`) and the shape follows it, with the sex assigned at birth noted under it
(`AMAB`, `AFAB`) when the two differ.

**Couples.** A couple's line joins the two partners; `consanguineous` doubles it and
`separated` puts two strokes across it. Children hang from a sibship line under it;
`twins` (`of` two or three children written together, `zygosity` `monozygotic`,
`dizygotic` or `unknown`) leave it from one point. A person's couples are their
partners in marriage order, at most six: two sit one on each side, and past two the
first is on the left and the rest on the right, the line to each later one running
over the row on its own level, so none cross.

Refused, each at its pointer: an id that names no one; a couple that is not two
different people, or a pair written twice; a child of two couples (an adopted child is
listed once, `adopted`, in the couple that raised them); someone their own ancestor;
partners whose descent puts them in different rows; a person in no couple, or a second
family with no couple joining it; past 6 partners, 4 generations or 30 people; past two
partners, a later one with parents in the tree; two partners who both have other
partners; twins not written together; a second proband; a pregnancy with partners. **An
ancestor chart** — one person, their two parents, four grandparents, every couple with
one child — is a genealogist's *pedigree chart* and a binary tree: it is refused with a
pointer to `tree`. See [`reference/familytree-cousins.json`](reference/familytree-cousins.json)
(an exam pedigree, four generations, a consanguineous couple),
[`reference/familytree-clinic.json`](reference/familytree-clinic.json) (a clinic letter),
[`reference/familytree-tudors.json`](reference/familytree-tudors.json) (six marriages)
and [`reference/familytree-reunion.json`](reference/familytree-reunion.json) (remarriage,
twins, adoption, gender).

## A meter: progress bar, thermometer, dial, bullet

Some figures say one thing: *this much, out of that*. A parish's roof appeal draws a
thermometer filling toward its goal; a delivery plan draws a progress bar per project; a
roadside fire sign is a half-circle of named bands with a needle on today's; a dashboard
draws a bullet graph, a bar on bands of grey with a target tick across it. That is
`meter`:

```json
{
  "version": 1,
  "kind": "meter",
  "style": "thermometer",
  "title": "The chapel roof appeal",
  "meters": [
    {"text": "Chapel roof appeal", "amount": 41250, "max": 60000, "target": 45000, "unit": "£"}
  ]
}
```

Each of the 1 to 6 `meters` is an `amount` read against its own scale, which ends at
`max`. `style` is set once for the whole document — `bar` (the default), `thermometer`,
`dial` or `bullet` — because a panel compares like with like: lengths with lengths,
needles with needles. A document wanting two styles is two documents.

* **`bar`**: a progress bar. One row per meter, names in a column at the left, the
  tracks lined up, the readouts in a column at the right.
* **`thermometer`**: a tube on a bulb, filled from zero toward the goal (`max`), its
  scale ticked at the left. Several stand side by side.
* **`dial`**: a needle on a half-circle from `min` (the only style that takes one; 0 by
  default) at the left to `max` at the right, up to three to a row. A needle reads a
  position, so a dial may start anywhere; a bar's length is its amount, so the others
  start at zero.
* **`bullet`**: a thin bar on named bands, with ticks from zero under it — Few's bullet
  graph, the honest replacement for a dial.

`target` is a mark on the scale — the plan for now, a stage of an appeal — drawn as a
short heavy stroke across the track. `bands` are 2 to 5 named stretches of the scale,
each `{"text", "to"}`, running from the end of the band before (or `min`) and rising to
`max`; required on a `bullet`, optional on a `dial`, refused on the others. **A band is
never told by colour alone**: it is drawn in a tone of the page's ink, lightest first,
and its word is written on it. If the reader is taught red, amber and green, write
`Red`, `Amber`, `Green` — the words carry it, and the theme decides the tones.

Every number is said in words in the meter's **readout**: the amount in bold — *of*
`max` on a bar and a thermometer (`23 of 30 sessions`, `£41,250 of £60,000`; just `64%`
for a percentage of 100) — then the band the amount is in, then the target. `unit` is
`%`, a currency sign written before the number (`£`, `$`, `€`, `¥`) or a word written
after it. A newline in a meter's `text` makes the rest a caption under its name: what
the reading is *of*. `role: "emphasis"` makes one meter's name and readout bold.

Refused, each at its pointer: an `amount` or `target` outside the scale; `max` not above
`min`; `min` on a bar, a bullet or a thermometer; `bands` on a bar (that is a `bullet`)
or a thermometer; a bullet without them; bands that do not rise, or whose last `to` is
not `max`; one band; `style` on a meter (it is the document's); `value` (it is
`amount`), `goal` (`max`, or a `target` under it), `percent`, a band's `from`, `colour`;
`series`, `axes`, `edges`. Budget: 6 meters, 5 bands. A band's word longer than its
band on a bullet, or band words that run into each other round a dial, are a
`FitError`. See [`reference/meter-appeal.json`](reference/meter-appeal.json) (a
fundraising thermometer with a stage target),
[`reference/meter-migration.json`](reference/meter-migration.json) (a project progress
panel), [`reference/meter-ward.json`](reference/meter-ward.json) (KPI dials, one rated
red, amber or green in words) and
[`reference/meter-library.json`](reference/meter-library.json) (a bullet-graph set).

## A RAG status report: highlight reports and risk registers

A programme board's highlight report, a council's risk register and a trust's board
assurance framework print the same figure: a list of workstreams or risks, each rated
red, amber or green, often with a direction of travel since the last report and a
sentence saying why. In most of them the colour is the only thing that says the rating,
so a greyscale print loses the page's whole point. That is `rag`:

```json
{
  "version": 1,
  "kind": "rag",
  "title": "Library refit: highlight report, period 7",
  "rows": [
    {"text": "Building works\nLead: estates", "rag": "amber", "trend": "worse",
     "note": "The asbestos survey added two weeks."},
    {"text": "Staff training", "rag": "red", "trend": "same",
     "note": "**Decision needed:** approve the trainer's quote."}
  ]
}
```

Each of the 1 to 15 `rows` is a `text` (a newline adds a caption under it: an owner, a
reference), a `rag` of `red`, `amber` or `green`, and optionally a `trend` and a `note`.
The rows are drawn in the order written, ruled apart, every column lined up: the name in
bold, the mark, the trend, and the note wrapped in the rest of the width. A report with
no notes is centred.

**A rating is never told by colour alone.** The theme's `[rag]` table gives each rating
a word (`Red`, `Amber`, `Green`; a house that says *On track* sets it there) and a shape
(a square, a triangle and a circle by default); the loader refuses a theme whose three
words or three shapes repeat. A colour is added only when a theme declares one — the
default theme draws the marks in the page's ink, and `accent` colours them.

`trend` is `better`, `same` or `worse`, not a direction: an arrow up means *improving* in
one report and *the risk rose* in another. The arrow points up, across or down, and the
theme's word for it (`improving`, `no change`, `worsening`) is written beside it.

Why `rag` and not `status`: on `flow` and `tree`, `status` already marks a change as
`added`, `changed` or `removed`.

Refused, each at its pointer: a rating other than the three (`amber/green`: pick one and
say why in the note; `blue`: a finished workstream is `green`, *Complete*); a trend of
`up`, `down` or `improving`; `status`, `colour`, `score`, `likelihood`, `impact`
(a scored risk grid is a `matrix` with a `scale`), `owner` (a caption), `commentary` (a
`note`); `columns` (one rating per row: cost, time and scope rated apart are a table);
`edges`. Budget: 15 rows. See [`reference/rag-refit.json`](reference/rag-refit.json) (a
highlight report), [`reference/rag-register.json`](reference/rag-register.json) (a risk
register), [`reference/rag-confidence.json`](reference/rag-confidence.json) (delivery
confidence, in the accent theme) and [`reference/rag-school.json`](reference/rag-school.json)
(a school's priorities, no notes).

## A clock face: teaching the time

Every primary maths scheme teaches the analogue clock — o'clock and half past, then
quarter past and quarter to, five-minute times, the nearest minute, Roman numerals and
the 24-hour clock — and every lesson and worksheet draws the same face. That is `clock`:

```json
{
  "version": 1,
  "kind": "clock",
  "title": "Quarter past and quarter to",
  "clocks": [{"time": "3:15"}, {"time": "3:45"}]
}
```

Each of the 1 to 12 `clocks` is a `time`, `H:MM` or `HH:MM` from `0:00` to `23:59`, and
optionally a `text` under the face (a name, or a prompt). Faces sit up to four to a row,
the rows kept even. The hands are placed by the time and told apart by shape — the hour
hand short and broad, the minute hand long and narrow — and **the hour hand moves on with
the minutes**: at half past seven it is halfway from the 7 to the 8, the point every
lesson makes. A face with no `time` has no hands: one for the pupil to draw on.

`numerals` is the sheet's: `arabic` (the default), `roman` (I to XII, with IV as taught),
`quarters` (12, 3, 6 and 9 only) or `none`. `readout` says what is written under each
face: `words` (the default: *quarter past three*, *twenty-two minutes to twelve*),
`digits` (the time as written, so `15:15` stays on the 24-hour clock), `both`, or `none`
for a worksheet whose answers are the pupil's.

`since` is an earlier time, less than 12 hours before: the face shades what has passed —
the minute hand's sweep when it is an hour or less, the hour hand's, nearer the hub,
when it is more, with a dashed line where the hand started — and the readout adds *40
minutes after 2:35*. Two or three faces in a row, each `since` the one before, is an
elapsed-time question.

Refused, each at its pointer: a time with seconds (no teaching face has a seconds hand to
read); `am`/`pm` (write the 24-hour time: `15:15`); a date; any other spelling (`9.30`,
`9:5`, `24:00`); `since` with no `time`, equal to it, or 12 hours or more before;
`seconds`, `date`, `hands`, `hour`, `minute`, `angle`, `label` (the `text`), `numerals` or
`readout` on a face (they are the sheet's); `edges`. Budget: 12 faces. A face too small
for its numerals is a `FitError`. See [`reference/clock-quarters.json`](reference/clock-quarters.json)
(o'clock to quarter to), [`reference/clock-worksheet.json`](reference/clock-worksheet.json)
(read and draw, answers hidden), [`reference/clock-roman.json`](reference/clock-roman.json)
(Roman numerals to the minute, in words and digits) and
[`reference/clock-journey.json`](reference/clock-journey.json) (how long between times).

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

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

It is **not on PyPI yet**, so install it from the repository:

```bash
pip install git+https://github.com/nuncaeslupus/drawspec
# or, with uv:
uv add git+https://github.com/nuncaeslupus/drawspec
```

Once it is published, `pip install drawspec` will be the whole of it.

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
  "$schema": "https://drawspec.dev/schema/drawspec-v1.schema.json",
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

The `$schema` line is optional and costs nothing at render time, but it earns
its place in an editor: point any JSON-Schema-aware editor at it and you get
completion over the field names and an inline error on `font_size` *while you
are typing it*, rather than after a render.

## Choosing a kind

The `kind` is the first thing to get right, because it decides which other
fields are legal. Thirteen exist, and they fall into four families:

| Family | Kinds | What they are for |
|---|---|---|
| Graph | `flow`, `tree`, `cycle` | Things connected to other things: a process, a hierarchy, a loop that comes round again. |
| Grid | `stack`, `timeline`, `columns`, `matrix` | Things in an arrangement: layers, events in order, side-by-side comparison, rows against columns. |
| Shape | `pyramid`, `rings`, `funnel` | Things in a proportion: levels narrowing to an apex, scopes nested inside scopes, stages narrowing to an outcome. |
| Plot | `chart`, `quadrant`, `curve` | Things with numbers: series against axes, items placed in a plane, a named shape with labelled waypoints. |

One worked document per kind lives in [`reference/`](reference), and `make
gallery` renders all of them onto one page. That page is the fastest way to see
what a kind actually looks like before committing a document to it.

Two notes worth having before you pick:

* **Read what the original is saying, not what it looks like.** A
  shared-responsibility diagram that looks like a grid is usually *how much of
  each column* is one party versus the other — a stacked proportion, not a
  matrix. Choosing `matrix` for it invents semantic rows the subject never had.
* **Some diagrams are not drawspec's job**, and it is better to say so than to
  approximate. Anything whose whole point is *where things are* — a floor plan,
  a map, two overlapping Wi-Fi cells — has no declarative description.
  [`kinds-wanted.md`](kinds-wanted.md) is the inventory that decided which kinds
  exist and which requests were declined.

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
* **`[canvas] width_mode`** decides whether a narrow drawing keeps that canvas
  (`fixed`, centred in it) or is cropped to its own ink (`ink`). Cropping is
  what makes a page scale two diagrams by different factors and read one label
  at two sizes. Use `ink` only for a diagram meant to be sized on its own.
* **`[fit] scale_min` / `scale_max`** are how far the whole type scale may
  stretch to make content fit — one factor applied to all four levels at once,
  so a tight diagram never gains a type size its neighbours do not have. Below
  `[canvas] min_legible_size` nothing is drawn at all: it is a refusal, with a
  message, rather than text nobody can read.

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

## When it refuses

A refusal is a designed outcome and the message is meant to be actionable. The
three you will meet:

| It says | It means | Do this |
|---|---|---|
| A violation with a JSON pointer | A field is misspelt, missing, or not legal for this kind | Fix the field the pointer names. `additionalProperties` is closed everywhere, so a key that looks ignored is always an error instead. |
| `… is the tool's output, never its input` | The document tried to place, size or colour something | Say what you mean instead — a `role` rather than a `stroke`, a `kind` rather than an arrangement. |
| A fit refusal | The content cannot be drawn above the legibility floor at this width | Shorten the text, split the diagram, or raise `width` — in that order. A smaller type size is not offered, on purpose. |

## What it is not

drawspec draws simple, declarative diagrams well, and is the wrong tool for
several jobs it might look like it does: it is not a Graphviz replacement, not
charting software, not a drawing program, and not a rich-text system. The
[README](../README.md#what-it-is-not) says why for each, and it is worth reading
before you push it past about twenty boxes.

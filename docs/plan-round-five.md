# Round five: what looking at the drawings found

Rounds two, three and four each came from a report. This one did not. The input
was round four's own page — *some of these graphics can be fixed* — so the method
had to be different: instead of checking claims, measure the drawings and see
what falls out.

Two things fell out. One of them was in the feature round four had shipped four
days earlier.

---

## First, the measurement round four owed

Round four ended on this:

> What is blocked on vocabulary should now be **zero**. That is a prediction, not
> a measurement — the measurement is yours to take.

It has been taken, on this side. The consumer's corpus is 87 documents in
`nuncaeslupus/opos` at `docs/esquemas/drawspec/corpus/`. Rendered with this
build:

| | |
|---|---:|
| documents | 87 |
| rendered | **87** |
| refused | 0 |
| strokes through a word | **0** |
| ink outside the canvas | **0** |

The three `etiqueta-cruzada-por-su-linea` notes in the consumer's
`revision.jsonl` — sheets 47, 65 and 69 — are closed by measurement rather than
by claim. The clearance pass round four added does hold on their sheets and not
only on ours.

Four of their documents were still written against the old vocabulary because
the vocabulary had not existed when they were written. They are rewritten in
[`nuncaeslupus/opos#145`](https://github.com/nuncaeslupus/opos/pull/145) —
sheet 51 with two sibling `bands` read across, 88 with `aside`, 41 with span
markup, 06 with curve `categories`.

---

## The defect: a band's name was the last text field that skipped `wrap`

The consumer had already reported this shape once. `span-text-raw`, round four:
*a span's `text` is emitted raw, so neither the line break nor the inline bold
works there.* It was fixed for spans. The band — added in the same round — still
had it, and two faults besides:

| | Was | Is |
|---|---|---|
| `**RPO**` | drew its asterisks | a bold run |
| a newline | flattened into one line | a lead over its detail |
| a name longer than the drawing | **drawn off the canvas** | broken to its bar |

The third is the serious one and it is worth being precise about, because it is
the failure family this whole project exists to make unrepresentable.

`_bands` never measured the name. `measurer.measure("0", …)` gave it a line
height and nothing else, so `BandBar` carried an anchor point and a rotation —
and `_framed`, which sizes the drawing from what was actually produced, had only
that point to size from. The canvas therefore ended where the words began.

An eighty-eight character band name beside a two-box chain:

```
name:    466.8 units long
canvas:  171.2 units tall
clipped: 147.8 above + 147.8 below  =  63% of it outside the page
```

Silently, in both orientations — 50.3 units off the side when the bar is
horizontal. Nothing raised, nothing logged, and the words are all present in the
markup. It is *text outside its box* moved up one level, from the box to the
canvas.

**The fix is the measure the bar already implies.** A band says *this runs
alongside these boxes*, so a name running past the last of them would be
claiming boxes the band has not got. The name is broken to the length of its own
bar; `BandBar` carries the block and reports `label_box`; `_framed` reserves it.
`TextLine` gained `rotate`, because setting a name on its side used to mean
dropping to a `TextRun` — a run of plain characters, which is exactly why the
markup showed. A single word longer than its bar is a `FitError` named as the
band rather than as the diagram.

---

## And a caption below ran flush to the bottom of the figure

`captioned` reserved one gap and spent it between the caption and the drawing,
so the far side went unpaid: the canvas ended where the block did and the words
sat against the edge of the figure. Above, the same code spent it on the outside
and butted the caption against the drawing instead. Neither side was symmetric
with the other and no test pinned either.

That is the starved bottom margin `[box] padding` calls *the single most repeated
failure in the corpus* — fixed inside the box in round one and reintroduced at
the canvas. Two gaps now, which also makes the band the same size whichever side
a house style puts it on, so the side stays a style choice rather than a change
of measurements.

Bottom gutters across the captioned references: **1.7 → 11.7**. `flow-bands`
wanted ten more units of `height_binding` ceiling and got them.

---

## `tools/clipping.py` — is the word on the page

`collisions.py` answers *can the word be read*. This answers the question before
it, and it exists because the band defect passed every check in the suite: it is
in the markup, it collides with nothing, and a coverage check over the text finds
every word.

It measures rather than rasterises, for the reason the last one did. The
`viewBox` comes from `scene.extents`, which records a text run as its **anchor
point** — the docstring says so and justifies it, correctly, for a family that
has already sized a box around its text. The families that place text *outside*
their boxes are the ones it does not hold for. That belief is where the bug is,
so the check is made against the same font metrics the belief was formed from.

It measures **rotated** runs rather than skipping them, which `collisions` does
skip. On its side a name is long in exactly the direction the canvas is short,
which is why that arrangement lost the most.

### The counter needed its own adversary

Review found three holes in it, and all three were the same shape as the defect
it was written for — a gate reporting zero because it did not look:

* **It measured every run in the parent's sans.** An inline `` `code` `` span is
  emitted as a `<tspan>` with its own monospace family, and monospace is the
  wider face: `identificacio_del_registre` measures 124.3 as sans and 156.5 as
  mono. A box a fifth too narrow is a clipped label called clean. `collisions.py`
  shares the helper and had the identical hole — its boxes were too small too.
* **Fill-only shapes and ellipses were invisible.** It took its geometry from
  `collisions._segments`, which skips `stroke="none"`. Every arrow head drawspec
  draws is a fill, and a chart's point marks are `<ellipse>`.
* **A `TextMeasurer` per `<text>`**, which threw the face cache away on every
  label.

All three fixed, with a regression test each. `<ellipse>` stays out of
`_segments` on purpose: that function asks whether a stroke runs *through a
word* and answers it by walking straight segments, and an arc has none to walk.
Being outside the canvas is a question about bounds, which an ellipse has.

The lesson is the round's own, and it generalises: **a new gate's zero means
nothing until something has tried to get past it.**

---

## What this round did not decide

Two items, both seeded as queue tasks rather than left in prose — see the
*Divergence handling* rule in `claude-arsenal/AGENTS.md`, which applies for the
same reason here: a finding that lives only in a document is a finding the next
session overwrites.

**R5-1 — the outer margin is decided per family, and the families disagree.**
There is no outer margin in the theme at all. Measured over the 33 references the
top gutter comes to four answers: **0** (stack, timeline, funnel, pyramid),
**10.5** (cycle), **≈22** (curve, quadrant, chart with an axis label), **24.5**
(flow, tree). Nothing clips and nothing collides — it is an unmade decision, not
a defect. But a `timeline` above a `flow` in one document, which the consumer's
temario does on most pages, bleeds to the edge beside a 25-unit gutter. Either a
drawing is flush and the page pads it, or a figure carries its own gutter and it
belongs in `[canvas]` beside `width` — for the same reason `width` lives there.
Not taken unilaterally because it moves all 33 drawings.

R5-1 has since been decided — *the figure carries its own channel* — and done;
what that took is the section after this one. R5-2 is still open.

**R5-2 — `edge-from-a-group`.** Still refused, checked rather than assumed. It is
the oldest item on the consumer's list that is not closed, `gap4` on sheets 39
and 44, and 44 is still `blocked` on it. `Frame` already carries an extent and
`border_obstacles` already treats its border as geometry an edge must cross, so
the missing piece is small: let the schema name a group in `from`/`to`, and let a
route anchor on the frame.

---

## R5-1, decided: `[canvas] margin`

The owner's call, taken after the round: **a figure carries its own gutter, and
it belongs in `[canvas]` beside `width`** — for the same reason `width` lives
there. So there is now one number, read from the theme, applied in one place
(`render.framed`), equal across all thirteen kinds. `kinds/graph` and
`kinds/cycle` stopped adding their own, and the eleven other families that added
none now get one.

### The half of the decision that was not in the question

*Where the margin comes from* turned out to matter more than what it is set to,
and only one of the two answers is safe.

Taken **out of** the width, every family lays out against `width - margin * 2`
and the emitted canvas stays 640. That is the tidier story — the number a
consumer sets to match their column is the number the SVG comes out — and it was
the first implementation. It breaks a document that used to draw. `timeline-work`
survived it; `timeline-disaster` did not. An `at`-spaced timeline sizes every
label to its **tightest** pair of marks, and that sheet's tightest pair is a
seventh of its span, so it needs 630 of the 640 it has. Twelve units off each
side put it at 616 and it refused — correctly, by its own rules, for a diagram
nobody had touched. A theme growing a frame must not be able to stop a document
rendering.

Nor could that reference simply be given more width: `canvas_width_variance == 0`
across the kinds is this project's own acceptance gate, and one drawing at 664
beside thirty-two at 640 fails it. The escape hatch and the invariant are the
same field.

So the margin goes **around** the width. `[canvas] width` keeps meaning the width
of the *drawing*; the canvas is `width + margin * 2`, the same arithmetic for
every kind, so two figures on a page are still one width and comparability — the
whole reason `width` is a theme value — is untouched. `height` and
`height_binding` keep meaning the height of the drawing for the same reason, so
no binding height moved either. Nothing in any layout budget changed except the
one that was wrong: `kinds/graph` had been taking its own 24-unit margin out of
`max_width`, charging every flow chart and tree 48 units for a gutter it now does
not draw. Four ranks that used to need 330 units of depth read across in 80.

### Measured

| | Before | After |
|---|---:|---:|
| smallest outer gutter, 33 references | **0.00** | **12.00** |
| largest *tightest* gutter | **24.50** | **18.00** |
| spread | **24.50** | **6.00** |

The 18.00 is one drawing, `matrix-process`, and it is interior rather than a
family framing itself: a matrix carrying edges puts `[edge] clearance` around
every cell so an arrow has somewhere to live in the join, including the cells on
the outside — taking it off those alone would make the edge cells wider than the
middle ones, and equal cells are that family's whole rule. The rest of the
residue is half a stroke, because `emit` widens the `viewBox` by half the
*heaviest* stroke in the scene and a lighter outermost element reads a hair clear
of it.

The consumer's corpus is the same shape and was measured, not predicted: **87
documents, 87 drawn, 0 refused, 0 collisions, 0 outside the canvas**, tightest
gutter 12.00 and widest 18.00 — the 18.00 again a matrix with edges.

`tests/test_margins.py` gates both halves per document: no drawing framed tighter
than the margin (exact — `emit`'s inset means a gutter can only come out at the
margin or above), and no drawing's tightest side further from it than that
interior allowance.

### And the clipping checker had a fourth hole

Found by pointing the new measurement at the gallery: a fill pattern's tile is a
`<rect>` a few units square at the origin inside `<defs>`, and its coordinates
are in the pattern's own space. Measured as canvas coordinates it is ink pinned
to the top-left corner, which is why five chart drawings reported an outer gutter
of zero while they were framed like everything else. `clipped` could only ever
have *under*-reported because of it, which is why it never showed — the same
shape as the three the round found: a gate looking at the wrong thing and
reporting a number anyway.

## Still the owner's, and untouched

Content decisions on sheets **01** and **27**; the glosses on **53 / 74 / 81**;
and the three redraws written in English against a Catalan source — **27, 83,
86**. Round five went nowhere near any of them.

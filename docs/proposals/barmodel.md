# Proposal: `barmodel`: a word problem as bars of parts (the tape diagram)

Status: **built** (see *As built* at the end). It comes from the round-2 corpus
([`../research/corpus-round2.md`](../research/corpus-round2.md), section 7, B1–B4) and
the owner's decision to let it in. Size **S**: rectangles in a row, laid out by
arithmetic; the only new mark is the brace.

## Why

The bar model — the *tape diagram* in US curricula, the Singapore bar model in
primary teaching — is how children are taught to see a word problem before they write
a sum. A bar is a quantity; it is split into parts; a brace says what a stretch of it
adds up to; a `?` marks what is asked. Three questions cover nearly every use:

* **part–whole**: one bar, its parts, and the whole braced over it;
* **comparison**: two bars on one left edge, the difference visible as the part one has
  and the other has not;
* **equal units**: a bar of identical boxes — groups for multiplication, the parts of a
  ratio or a fraction — with one unit's worth found from a total.

The corpus is clear on the one rule the drawing must keep: **lengths are in
proportion** (B2: pupils read unequal parts as equal unless they are drawn so), and
equal units are drawn equal (B3, B4). Hand-drawn and slide-drawn bar models break
this constantly, which is why it should be computed and not drawn.

drawspec cannot draw this today. `chart` bars stand on an axis and compare values
against it; `treemap` splits one total but by area, unaligned; `stack` has no lengths.
None draws a brace, and none puts two bars on one left edge in one scale.

What it is not: a bar chart (no axis, no ticks — the numbers are written in the
parts), and not a fraction wall (rows of every fraction, a table).

## Use cases

### 1. Primary maths: part–whole, the unknown part

"30 children are in the class. 12 walk to school; the rest come by bus. How many come by
bus?"

```json
{
  "version": 1,
  "kind": "barmodel",
  "title": "How many come by bus?",
  "bars": [
    {"id": "class", "parts": [
      {"value": 12, "text": "walk: 12"},
      {"value": 18, "text": "bus: ?", "role": "emphasis"}
    ]}
  ],
  "braces": [{"over": ["class"], "value": 30, "text": "30 children"}]
}
```

The author writes the bus part's `value` so its length is right, and its `text` says
what the child sees: `?`. The brace's `value` is checked against the parts it spans.

### 2. Primary maths: comparison

"Maya read 45 pages. Tom read 28. How many more did Maya read?"

```json
{
  "version": 1,
  "kind": "barmodel",
  "title": "How many more pages did Maya read?",
  "bars": [
    {"text": "Maya", "parts": [{"value": 45}]},
    {"text": "Tom", "parts": [{"value": 28}, {"value": 17, "text": "?", "role": "note"}]}
  ]
}
```

Both bars start at one left edge, in one scale. The difference is a `note` part: drawn
dashed, the stretch Tom's bar would need to match Maya's.

### 3. Ratio: equal units and a total over two bars

"Red and blue beads are in the ratio 3 : 5. There are 64 beads. How many are red?"

```json
{
  "version": 1,
  "kind": "barmodel",
  "title": "Red to blue is 3 : 5, and there are 64 beads",
  "bars": [
    {"id": "red", "text": "Red", "parts": [{"units": 3}]},
    {"id": "blue", "text": "Blue", "parts": [{"units": 5}]}
  ],
  "braces": [
    {"over": ["red", "blue"], "value": 64},
    {"over": ["red"], "text": "?"}
  ]
}
```

A brace over two bars is drawn upright at their right. With a `value`, it fixes what
one unit is worth (64 ÷ 8 = 8), and every other brace with a `value` must agree.

### 4. Fractions: a fraction of an amount

"Two fifths of a bag of 40 sweets are eaten."

```json
{
  "version": 1,
  "kind": "barmodel",
  "bars": [
    {"id": "bag", "parts": [
      {"id": "eaten", "units": 2, "role": "emphasis"},
      {"units": 3}
    ]}
  ],
  "braces": [
    {"over": ["bag"], "value": 40, "text": "40 sweets"},
    {"over": ["eaten"], "text": "eaten: ?"}
  ]
}
```

## Fields

| Field | Where | Required | Decision |
|---|---|---|---|
| `bars` | root | **yes** | 1–3 bars, top to bottom, all on one left edge and in one scale. |
| `bar.text` | bar | no | The bar's name, left of it: `Maya`, `Red`. |
| `bar.id` | bar | no | What a brace's `over` names. Unique among bars and parts. |
| `bar.parts` | bar | **yes** | 1–8 parts, left to right. |
| `part.value` | part | one of | A number > 0: the part's length is in proportion. Its words default to the number. |
| `part.units` | part | one of | A whole number ≥ 1: that many equal boxes, each one unit long. |
| `part.text` | part | no | What is written in the part (in each box of a `units` part): `?`, `walk: 12`. |
| `part.id`, `part.role` | part | no | Roles `step`, `emphasis` (bold, filled: the part asked about), `note` (dashed: a difference, a part not there). |
| `braces` | root | no | `{over, value?, text?}`: a brace over the ids in `over` — contiguous parts of one bar (drawn over the bar, under the last bar), or whole bars (one bar: over it; several consecutive bars: upright at their right). |

## Refused, and why

| Refused | Why |
|---|---|
| A part with neither `value` nor `units`, or both | Its length would be a guess. |
| `value` parts and `units` parts in one document | A unit has no length against a number. |
| A brace `value` that is not the sum of what it spans | The model would teach the wrong sum. |
| Two braces that make one unit worth different amounts | The same. |
| A brace over parts of two bars, parts not side by side, or bars not consecutive | A brace spans one stretch. |
| More than 3 bars, 8 parts in a bar, 12 units in a bar, 6 braces | Readability budget. |
| A single part in the whole document | A bar with nothing to compare says nothing. |
| `edges`, `axes`, `series` | Not a chart: the numbers are in the parts. |

A part too narrow for its words is a `FitError` naming it: make the bar model's parts
closer in size, or shorten the words.

## Layout sketch

1. Names in a column at the left; braces over several bars in a column at the right;
   the bars in between, the longest bar filling the width.
2. One scale for the document: a `value` is its share of the longest bar's total, a
   unit is the longest bar's share per unit.
3. A brace over a bar's parts goes above it, and above every bar but the last when
   there are several; the last bar's go under it. Braces on one side that would touch
   are stacked outwards, the narrowest nearest the bar.
4. The height is derived. There is no author control.

## As built

Built as proposed, with the kind named `barmodel` rather than the corpus's working
name `bars`, which reads as a bar chart; *tape diagram* and *bar model* are the
names the guide gives it. What was settled while building, and why:

* **`amount`, not `value`**, for a part's size and a brace's checked total, as on
  `treemap` and `sankey`: `value` is refused in every document by name (it is the
  word for a number drawspec would turn into a colour or a position), and a bar model
  here keeps that rule rather than carving out an exception. `value` in a bar model
  is refused naming `amount`.
* **No theme key.** Proportion is the content, and a brace is a brace in every
  curriculum the corpus found; there is no house style to choose between.
* **A units part's words go in every box** — `6` in each of four boxes reads as
  "four groups of six", which is what B3 draws — and `emphasis` fills every box.
* **Braces never sit between two bars**: the first bars are braced above, the last
  under, so a comparison's two bars keep a plain gap between them and the eye goes
  from one to the other. A brace over a whole single bar uses the same rule.
* **`note` parts are drawn first**, so the edge a dashed difference shares with a
  solid part stays solid.
* **`total` on a bar is refused by name**, pointing to a brace over the bar: one way
  to state a total, and the one that is checked.
* **The multi-step case** (three bars, a total over all three, a difference braced
  on the first) is the fifth reference, `barmodel-savings`, beyond the four use cases
  above; `barmodel-pages` braces the difference under the second bar.

References: `barmodel-bus` (use case 1), `barmodel-pages` (2), `barmodel-ratio` (3),
`barmodel-fraction` (4), `barmodel-savings`.

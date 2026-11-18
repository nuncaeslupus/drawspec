# Proposal: `waterfall`: from one total to another, step by step (the bridge chart)

Status: **built** (see *As built* at the end). It lifts the deferral in [`README.md`](README.md) (*Deferred, not
proposed*): the deferral waited for a real original, and the round-2 corpus
([`../research/corpus-round2.md`](../research/corpus-round2.md), section 6, W1–W4)
found four, in NHS board papers and public-finance commentary. The owner's decision:
in. Size **S**: bars on one vertical scale, placed by arithmetic, with the chart
kind's ticks.

## Why

A waterfall (a *bridge* in finance) explains how one total became another: last year's
deficit to this year's plan, a forecast to an outturn, an opening balance to a closing
one. It starts from a total, every step floats on the running sum and moves it up or
down, and it ends at a total; most originals stop half-way at a **subtotal** (W1, W3).
A board reads it for one thing: which steps did the moving, and by how much.

What the corpus asks for:

* **5–10 bars**, every bar's number written on it (W4: steps that nearly cancel can only
  be read from their labels).
* **Start and end totals**, and **subtotals mid-way** that are what the running sum says
  they are. A subtotal the author writes is a claim; drawspec checks it, the way
  `barmodel` checks a brace and `sankey` balances a node.
* **Bridges below zero** (W1, W3): a deficit getting smaller is a chart whose every bar
  hangs under the zero line. Bridges that **cross** zero have to work too.

drawspec cannot draw this today. `chart` bars stand on the baseline; there is no bar
that floats on another's end, and nothing checks a total.

## A kind, not a `chart` mark

The survey proposed a `bridge` mark on `chart`. Built as its own kind instead, because
nothing of `chart`'s payload fits:

* a chart's horizontal axis is numeric (`data: [[x, y]]`), with `categories` as an
  overlay; a waterfall's horizontal is an **ordered list of named steps**, and the names
  are the content;
* a chart's series are told apart by a legend; a waterfall has one sequence of bars of
  **three sorts** (total, up, down), and which sort a bar is follows from its field;
* a chart checks nothing; a waterfall's subtotals are **checked**, with refusals of its
  own (a missing start total, a subtotal off by 0.4, a bridge that does not end at a
  total). As a mark, each of these would be a rule for one mark inside a kind whose other
  marks have none — the reason `lanes` became a kind rather than a `flow` field.

A kind also gets its own readability budget (12 bars), which a mark could not.

## Use cases

### 1. Public finance: a forecast to an outturn

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

A bar is a `total` (it stands on zero, and after the first it is checked) or a signed
`amount` (it floats on the running sum). The end total is written, not derived: the
author states the number the reader is told, and drawspec says whether the steps get
there.

### 2. A board paper: a deficit bridge, every bar below zero, two subtotals

```json
{
  "version": 1,
  "kind": "waterfall",
  "title": "From last year's deficit to this year's plan",
  "axis": {"label": "Surplus or deficit, £ million"},
  "bars": [
    {"text": "Last year", "total": -24.0},
    {"text": "One-off support ends", "amount": -6.0},
    {"text": "Unfunded pay award", "amount": -3.5},
    {"text": "Underlying", "total": -33.5},
    {"text": "Efficiency", "amount": 12.0},
    {"text": "Extra activity", "amount": 4.5},
    {"text": "Before stretch", "total": -17.0},
    {"text": "Stretch target", "amount": 5.0, "role": "emphasis"},
    {"text": "Plan", "total": -12.0}
  ]
}
```

### 3. A small business: opening balance to closing, one subtotal

Cash at the start of the month, what came in and went out, the position before tax, and
the closing balance — the same shape at the scale of a sole trader's notes.

### 4. A result that crosses zero

A small surplus pushed into deficit by energy and pay, and back by a price rise: the
steps cross the zero line twice, and each bar is drawn between its two running sums
whichever side of zero they are on.

## Fields

| Field | Where | Required | Decision |
|---|---|---|---|
| `axis` | root | **yes** | `{label}`: what the numbers are, with their unit — `Borrowing, £ billion`. Required for the reason a `chart`'s axis label is. |
| `bars` | root | **yes** | 3–12 bars, left to right. |
| `bar.text` | bar | **yes** | The step's name, under its bar. |
| `bar.total` | bar | one of | A total: stands on zero. The first bar is one, and so is the last; one in between is a subtotal. Every one after the first must equal the running sum. |
| `bar.amount` | bar | one of | A signed step, not 0: floats from the running sum to the running sum plus it. |
| `bar.role` | bar | no | `step` (the default) or `emphasis` (the step the chart is about: a heavier outline, its number bold). |

`amount`, not `value`: `value` is refused in every document by name, and is refused
here naming `amount` (and `total`).

## Refused, and why

| Refused | Why |
|---|---|
| A first bar that is not a `total` | A bridge starts from a number the reader knows. |
| A last bar that is not a `total` | A bridge ends at one — the refusal says what the steps add up to, so the author can write it. |
| A `total` that is not the running sum | The chart would show a step that is not there. Refused with the sum and the difference. |
| A `total` straight after a `total` | It repeats it. |
| A bar with both `total` and `amount`, or neither; an `amount` of 0 | A bar is one or the other; a step of nothing is not drawn. |
| More than 12 bars | Readability budget: the corpus has 5–10. Past 12 the names under the bars are too narrow to read. Split at a subtotal into two bridges. |
| `series`, `axes` | Values against an axis are a `chart`. |
| `edges` | The bridge's connectors are drawn for it. |
| `subtotal`, `start`, `end` | A subtotal is a `total` between the first and the last. |

## Layout sketch

1. A vertical axis at the left, ticked like a `chart`'s, its label rotated beside it; a
   zero line across the plot whenever zero is in range (always: a total stands on it).
2. One band per bar, left to right, the bar in the middle of its band. A total runs
   from zero to its value; a step from the running sum before it to the sum after it.
3. A thin dashed connector at each running sum, from one bar to the next, so the eye
   follows the level.
4. Every bar's number beyond its far end: above a rise or a positive total, under a fall
   or a negative one. Steps are written signed (`+6.1`, `−9.4`, a true minus sign), with
   as many decimals as the most precise bar.
5. Totals, rises and falls take the first three of the theme's mark fills, so they are
   told apart in greyscale by pattern as well as by the sign and the direction of travel.
6. The names under the plot, wrapped to their band. The height is derived.

## As built

Built as proposed, as its own kind. What was settled while building, and why:

* **Use case 1 changed its numbers.** It was first drawn as national borrowing, a
  forecast of 118 against steps of 2 to 9: honest, because every total stands on zero,
  and unreadable, because the steps were slivers along the top. A bridge whose steps
  are small against its totals is what an axis starting above zero would "fix", and a
  bar that does not start at zero misstates its length, so the axis stays at zero and
  the reference became a council's budget gap, where the steps are the story.
* **The axis runs between whole ticks** below and above every running sum, zero
  always in it; the zero line is drawn across the plot over the bars, so a step that
  crosses it shows where.
* **A number that would sit on the zero line moves to the bar's other end** (a fall
  ending just above zero writes its number at its top). Numbers are kept to their
  bar's band, so they never reach a neighbour, and a number wider than the band is a
  `FitError` rather than an overlap.
* **No legend.** A total stands on zero, a step's sign is written on it, and its
  direction is the direction it travels; the fills say the same a third time, for
  greyscale. A legend would name three things the drawing already names.
* **A subtotal that is off is refused once.** The running sum carries on from the
  steps, not from the wrong total, so one wrong figure is one refusal, not a cascade
  down every later total.
* **`unit` is refused**, naming the axis label: the unit is said once, beside the
  axis, and the bars carry bare numbers as every original in the corpus does.

References: `waterfall-budget-gap` (use case 1), `waterfall-deficit` (2, below zero,
two subtotals), `waterfall-cash` (3), `waterfall-result` (4, crossing zero twice).

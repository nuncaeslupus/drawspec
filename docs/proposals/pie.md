# Proposal: `pie`: the shares of one known total, as sectors of a circle

Status: **built** (see *As built* at the end). It comes from the round-2 corpus
([`../research/corpus-round2.md`](../research/corpus-round2.md), section 8, P1–P4) and
the owner's decision on survey question 5: **in, with limits**, the way `treemap` and
`sankey` were let in — stating a few proportions the author already knows, not
exploring data. Size **S**: sectors by arithmetic; the work is in the labels.

## Why

The pie chart is taught in every school (P1, P2: from a frequency table, each share of
the total times 360°, every sector labelled) and printed on every budget day (P3, P4:
where the money goes). It answers one question — *what share of the whole is each
part?* — and reads best when one or two parts dominate or a part is a nice fraction
(½, ¼).

`treemap` already says "parts of one total by area", and the survey proposed keeping
the pie out on that ground. The owner let it in because the pie is what the readers of
course notes and public documents are taught to read; a treemap of a class's journeys
to school is correct and unfamiliar.

What it is **not**: a chart for comparing parts of similar size (a bar chart is), for
many parts (past eight sectors the small ones are slivers no one compares), or for two
totals side by side (P4 draws two pies; two `pie` documents do that, each read alone).
The guide says so where it introduces the kind.

## Use cases

### 1. School: how a class travels (P1, P2)

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

Counts, as written in a frequency table. drawspec computes each share (12 of 30 is
144°); the author never writes an angle or a percentage.

### 2. Public finance: where each £100 goes (P3, P4), with a remainder

```json
{
  "version": 1,
  "kind": "pie",
  "title": "Where each £100 of public spending goes",
  "unit": "%",
  "parts": [
    {"text": "Social protection", "amount": 27},
    {"text": "Health", "amount": 20},
    {"text": "Education", "amount": 10},
    {"text": "Debt interest", "amount": 8},
    {"text": "Defence", "amount": 5},
    {"text": "Transport", "amount": 4},
    {"text": "Public order", "amount": 4},
    {"text": "Everything else", "amount": 22, "role": "note"}
  ]
}
```

Fifteen budget areas (P3) are past the limit, so the smallest are merged into one
`note` part — *Everything else* — drawn last, unfilled. With `unit: "%"` the amounts
are percentages, and they must add up to 100 within rounding.

### 3. A week of a team's time, as a donut

The same document, drawn as a ring by a theme with `[pie] shape = "donut"`. No
non-vendor donut was found in the corpus; it appears in template galleries, so it is a
house style, not a document field.

## Fields

| Field | Where | Required | Decision |
|---|---|---|---|
| `parts` | root | **yes** | 2–8 parts, clockwise from twelve o'clock in the order written; a `note` part goes last. |
| `part.text` | part | **yes** | The part's name, written in its sector or beside it with a leader. |
| `part.amount` | part | **yes** | More than 0: a count, a sum of money, or — with `unit: "%"` — a percentage. The angle is its share of the sum. |
| `part.role` | part | no | `step` (the default), `emphasis` (the part the chart is about: a heavier outline, its words bold), `note` (the remainder, *Everything else*: unfilled, dashed, last). |
| `unit` | root | no | What the amounts are in, written after each one: `pupils`, `£m`, `%`. `%` is checked. |
| `values` | root | no | `false` leaves the numbers out and writes the names alone. |

**Shares are computed, never written.** The author gives amounts as they are in the
source — counts from a tally, money from a budget line — and drawspec takes each share
of their sum, so the angles cannot disagree with the numbers. The one statement that
*can* disagree is a percentage, which claims a total of 100: with `unit: "%"` the
amounts must add up to 100 within one point of rounding (eight percentages rounded to
whole numbers can miss 100 by a point, never by more in practice), and anything further
off is refused with the sum. That replaces a separate checked `total` field: a count's
total is the sum, and saying it twice would be a second place to get it wrong.

## No colour-only meaning

A sector is identified by its **label**, never by its fill: every sector carries its
name and number, inside it when they fit and otherwise beside it on a leader line from
its arc. Fills are the theme's mark patterns, taken in turn only so that **neighbours
differ** (the last sector checked against the first, which it touches); with eight
sectors and five patterns two sectors share a pattern, which is harmless because no
reader is asked to match a fill to a key. There is no legend to match against.

## Refused, and why

| Refused | Why |
|---|---|
| More than 8 parts | Readability budget (P3's fifteen is the case to refuse). Merge the smallest into one `note` part, or draw a bar chart. |
| A part under 2% of the total | A sliver whose angle no one can read; merge it into the `note` part. |
| Percentages that do not add up to 100 (±1) | The pie would quietly rescale them. |
| More than one `note` part | One remainder. |
| `value`, `percent`, `share`, `angle` | The size is `amount`; shares and angles are computed. |
| `total` | The total is the sum of the amounts. |
| `groups` | One level of parts; grouped parts are a `treemap`. |
| `series`, `axes` | A `chart`. |
| `donut`, `hole` | A theme's `[pie] shape`. |

## Layout sketch

1. One circle, as large as the labels beside it allow; sectors clockwise from twelve.
2. Each label is tried inside its sector (pie only), and goes outside on a leader when
   it does not fit — on the side of the circle its sector is on, the labels on each
   side kept in angle order and pushed apart so they never touch.
3. A donut is the same with a hole of about half the radius; its labels always go
   outside.

## As built

Built as proposed. What was settled while building, and why:

* **`parts`, as on `treemap`**, not `sectors`: the same idea — the parts of one total,
  each a `text` and an `amount` — under the same names, so a document moves between the
  two kinds by changing `kind`, and `unit` and `values` mean what they mean there.
* **Cap 8**, the corpus's suggestion, rather than `treemap`'s 10: labels beside a
  circle need a column of their own, and past eight a budget pie's smallest sectors
  crowd one side. A sector under 2% is refused too, naming the `note` part — P3's
  fifteen-way split becomes the seven largest and *Everything else*.
* **No `total` field.** Shares come from the sum of the amounts, so a stated total
  could only repeat the sum; percentages are the one case checked, because they claim
  100. The tolerance is one point: eight shares rounded to whole percentages miss 100
  by at most four in theory and by one in practice, and one is what published pies show.
* **Order is as written**, not largest first: a school pie follows its frequency
  table, and an ordered scale (never, sometimes, always) must stay in order. Only the
  `note` part moves, to the end.
* **The theme key is `[pie] shape`** (`pie` | `donut`), a section of its own rather
  than the corpus's suggested `[chart] pie`: there is no `[chart]` section, and the
  other kinds' house styles each live in a section named for the kind. The donut's
  hole is 55% of the radius, and all its labels go outside.
* **A leader meets its label at the name's first line**, runs straight out from the
  middle of the arc, and moves its elbow further out until the run across to the label
  clears the circle, so a label pushed down its column never crosses another sector.
* **Fills skip nothing**: the theme's sequence includes `none`, so with five fills
  and eight sectors one sector is unfilled; its label, as for every sector, is what
  identifies it, and the remainder is still told apart by its dashed outline.

References: `pie-travel` (use case 1), `pie-trip` (nice fractions, P2),
`pie-spending` (use case 2, percentages with a remainder), `pie-team-week` (use case
3, a donut by `docs/reference/themes/donut.toml`).

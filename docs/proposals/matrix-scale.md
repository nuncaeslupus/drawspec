# Proposal: `matrix` + `scale` — an ordered fill, for heatmaps

Status: **implemented** — see *As built* at the end for where it departs from this text.
Size **S** (one field, one validation, one theme ramp).

## Why a feature and not a kind

A heatmap is a grid whose cells say *how much*, where the eye looks for the cell that
stands out. `matrix` already draws the grid, and cells already name a `group` whose fill
the theme chooses. What it lacks is **order**: groups are filled in order of first
mention, as a set of distinct patterns, so "rare / sometimes / often" come out as three
unrelated patterns, and nothing says *often* is the strong one.

`scale` says the groups are ordered. The theme then fills them on a ramp (light to
heavy, by pattern density as well as by tone, so greyscale holds) and the key is drawn
in that order.

Numbers stay out. A heatmap of raw values with a continuous colour scale is a plotting
library's job; an author who bucketed the values and named the buckets is stating a
judgement, which is drawspec's job.

## Use cases

### 1. Course notes — a risk matrix

```json
{
  "version": 1,
  "kind": "matrix",
  "title": "Risk = likelihood × impact",
  "columns": ["Minor", "Moderate", "Severe"],
  "rows": ["Likely", "Possible", "Unlikely"],
  "scale": ["low", "medium", "high"],
  "key": [
    {"group": "low", "text": "Accept and monitor"},
    {"group": "medium", "text": "Mitigate this year"},
    {"group": "high", "text": "Mitigate now"}
  ],
  "cells": [
    {"text": "Medium", "column": 0, "row": 0, "group": "medium"},
    {"text": "High", "column": 1, "row": 0, "group": "high"},
    {"text": "High", "column": 2, "row": 0, "group": "high"},
    {"text": "Low", "column": 0, "row": 1, "group": "low"},
    {"text": "Medium", "column": 1, "row": 1, "group": "medium"},
    {"text": "High", "column": 2, "row": 1, "group": "high"},
    {"text": "Low", "column": 0, "row": 2, "group": "low"},
    {"text": "Low", "column": 1, "row": 2, "group": "low"},
    {"text": "Medium", "column": 2, "row": 2, "group": "medium"}
  ]
}
```

### 2. Design document — where CI fails, by service and week

```json
{
  "version": 1,
  "kind": "matrix",
  "title": "Failed CI runs, last four weeks",
  "caption": "Rare: under 2 %. Often: over 10 %.",
  "columns": ["Week 1", "Week 2", "Week 3", "Week 4"],
  "rows": ["`auth`", "`billing`", "`search`"],
  "scale": ["rare", "sometimes", "often"],
  "cells": [
    {"text": "1 %", "column": 0, "row": 0, "group": "rare"},
    {"text": "1 %", "column": 1, "row": 0, "group": "rare"},
    {"text": "3 %", "column": 2, "row": 0, "group": "sometimes"},
    {"text": "2 %", "column": 3, "row": 0, "group": "sometimes"},
    {"text": "4 %", "column": 0, "row": 1, "group": "sometimes"},
    {"text": "14 %", "column": 1, "row": 1, "group": "often", "role": "emphasis"},
    {"text": "12 %", "column": 2, "row": 1, "group": "often"},
    {"text": "5 %", "column": 3, "row": 1, "group": "sometimes"},
    {"text": "0 %", "column": 0, "row": 2, "group": "rare"},
    {"text": "1 %", "column": 1, "row": 2, "group": "rare"},
    {"text": "1 %", "column": 2, "row": 2, "group": "rare"},
    {"text": "0 %", "column": 3, "row": 2, "group": "rare"}
  ]
}
```

The numbers are the cells' **text**, not their fill: the author chose the buckets.

### 3. Course notes — a skills matrix

```json
{
  "version": 1,
  "kind": "matrix",
  "title": "Who can cover what",
  "columns": ["Networking", "Databases", "Kubernetes"],
  "rows": ["Ana", "Luis", "Marta"],
  "scale": ["learning", "can do", "can teach"],
  "cells": [
    {"text": "can teach", "column": 0, "row": 0, "group": "can teach"},
    {"text": "learning", "column": 1, "row": 0, "group": "learning"},
    {"text": "can do", "column": 2, "row": 0, "group": "can do"},
    {"text": "can do", "column": 0, "row": 1, "group": "can do"},
    {"text": "can teach", "column": 1, "row": 1, "group": "can teach"},
    {"text": "learning", "column": 2, "row": 1, "group": "learning"},
    {"text": "learning", "column": 0, "row": 2, "group": "learning"},
    {"text": "can do", "column": 1, "row": 2, "group": "can do"},
    {"text": "can teach", "column": 2, "row": 2, "group": "can teach"}
  ]
}
```

No `key` here: with `scale` and no `key`, the key lists the scale's names in order,
which is what a reader needs.

## Fields

| Field | Where | Decision |
|---|---|---|
| `scale` | `matrix` root, optional | `array of string`, 2–5 entries, **weakest first**. Every cell `group` must be one of them; the fills come from the theme's new `[mark] ramp`, by index. The key is drawn in scale order (and uses `key` texts where given). |

## Refused, and why

| Refused | Why |
|---|---|
| A cell `group` not in `scale` | When a matrix is a scale, every filled cell is on it. A cell with no `group` is still allowed (unfilled: "not assessed"). |
| `scale` with more than 5 entries | Past five, steps of a ramp cannot be told apart in greyscale. |
| A numeric `value` on a cell to colour by | No continuous colour scale; bucket and name it. |
| A `key` entry for a name not in `scale` | It would describe nothing. |

## Theme

New `[mark] ramp`: an ordered list of fills, lightest to heaviest, each distinct from its
neighbours in a non-colour channel (pattern density). `drawspec theme check` gains a
test that consecutive ramp entries differ in greyscale by a minimum contrast step.

## Acceptance tests to write

* The three documents render; fills follow scale index, not first mention (test: list
  `high` first in `cells` and check it still gets the heaviest fill).
* Key order equals scale order.
* Each refusal at its pointer.
* Theme check fails a ramp whose two neighbours are indistinguishable in greyscale.

## As built

Implemented as proposed, with these changes:

* **The ramp is tone, not pattern density.** The proposal asked for fills that
  differ "by pattern density as well as by tone". Rendered, the existing patterns
  could not carry an order: dots, hatch and a grid are three *things*, not three
  *amounts*, and at cell size the eye does not rank them. So `[mark] ramp` is a
  list of ink strengths, lightest first (`[0.08, 0.16, 0.24, 0.32, 0.4]` by
  default): each step is the page's own ink laid down at that strength, which is
  greyscale lightness by construction — the channel a printed heatmap is read
  in — and follows `currentColor` into dark mode like everything else.
* **The theme check is on that lightness.** At load, a ramp needs at least five
  steps (one per step of the longest scale), each at least 0.08 darker than the
  last — the first measured from a blank cell, so the lightest bucket never
  reads as *not assessed* — and none darker than 0.4, so a label on the
  heaviest cell keeps 4.5:1 on a dark page too. (First built at 0.5 / 0.48;
  checked in a browser on `#121212`, the heaviest cell's light label was 3.4:1,
  because in dark mode the heaviest tone is the lightest cell.)
* **Steps are spread, not taken by index.** A three-step scale takes the ramp's
  first, middle and last tones rather than its first three, so the ends of any
  scale are the ends of the ramp and a two-step scale is light against dark.
* **The key lists every step**, including one no cell uses: the key of a
  heatmap is its scale, and a reader looking for *often* should see that nothing
  was. A `key` line may therefore name an unused step, but not a name off the
  scale.
* **Two more refusals**: a step named twice, and (by the schema) a scale of one.
  A cell `value` is refused by `additionalProperties` like any unknown field, and
  `value` now has its own message in the refused-field table pointing at
  bucketing.

# Proposal: `numberline`: values and ranges on one scale

Status: **proposed, not built**. It comes from `docs/research/kinds-survey.md` (rank 1).
Size **S**: one axis, which `timeline` and `chart` already draw, plus marks and bars in
tracks above it.

## Why

The number line is the most common diagram in school maths. Children use it to count
on at six, and students use it to solve compound inequalities at sixteen. Outside maths
it is one scale with things placed on it: tenses relative to *now* in a language class,
positions on a policy spectrum, the pH scale in chemistry.

drawspec comes close and misses. `timeline` + `at` places entries by a number. But it
reads as *when*, and its `spans` join two entries. It cannot say that a range includes
or excludes an end, or that a range runs on for ever. `chart` has an axis but no point
labels on a single line. An inequality's content is exactly those three facts: where
each end is, whether the end belongs to the range, and which way it is unbounded.

What it is not: a plot. There is one axis, no second dimension and no data series.
Positions are numbers the author already knows.

## Use cases

### 1. Course notes: a compound inequality

```json
{
  "version": 1,
  "kind": "numberline",
  "title": "−3 ≤ x < 4",
  "axis": {"min": -5, "max": 6, "step": 1},
  "ranges": [
    {"from": -3, "to": 4, "to_open": true, "text": "x", "role": "emphasis"}
  ]
}
```

The closed dot at −3 and the open dot at 4 are the ends of the range. The author does
not place them.

### 2. Course notes: two inequalities and their overlap

```json
{
  "version": 1,
  "kind": "numberline",
  "title": "Where x > 1 and x ≤ 5 both hold",
  "axis": {"min": -2, "max": 8, "step": 1},
  "ranges": [
    {"from": 1, "from_open": true, "text": "x > 1"},
    {"to": 5, "text": "x ≤ 5"},
    {"from": 1, "to": 5, "from_open": true, "text": "both", "role": "emphasis"}
  ]
}
```

A range with no `to` runs off the right end with an arrow, and one with no `from` runs
off the left. Ranges are stacked in tracks above the line, in the order written.

### 3. Language notes: where the present perfect sits

```json
{
  "version": 1,
  "kind": "numberline",
  "title": "“I have lived here for three years”",
  "axis": {"min": -5, "max": 2, "ends": ["past", "future"]},
  "points": [
    {"at": 0, "text": "now", "role": "emphasis"},
    {"at": -4, "text": "“I lived in Leeds”"}
  ],
  "ranges": [
    {"from": -3, "to": 0, "text": "“I have lived here”"}
  ]
}
```

With `ends`, the scale is named rather than measured, so no numbers are drawn. Only the
order and the gaps count, as on `curve` and `quadrant`.

### 4. Policy brief: where the options sit on one spectrum

```json
{
  "version": 1,
  "kind": "numberline",
  "title": "Office attendance options",
  "axis": {"min": 0, "max": 5, "ends": ["fully remote", "fully on site"]},
  "points": [
    {"at": 0.5, "text": "Remote by default"},
    {"at": 2, "text": "Two anchor days"},
    {"at": 3, "text": "Team chooses", "role": "emphasis"},
    {"at": 4.5, "text": "Office by default"}
  ]
}
```

## Fields

| Field | Where | Required | Decision |
|---|---|---|---|
| `axis` | root | **yes** | `{min, max, step?, unit?, label?, ends?}`. `min` < `max`. `step` sets the ticks; without it a "nice" step is chosen from the range. `ends` is `[low, high]` text for a named scale and turns the tick numbers off. |
| `points` | root | no | `{id?, at, text?, open?, role?}`. A dot at `at`, hollow when `open`. Its label goes above the line, or below if the labels above would collide. |
| `ranges` | root | no | `{id?, from?, to?, from_open?, to_open?, text?, role?}`. Each range is drawn as a bar in its own track above the line. A missing end is unbounded and drawn as an arrow off the axis. A missing `*_open` means closed. |

At least one of `points` and `ranges` is required.

## Refused, and why

| Refused | Why |
|---|---|
| `at`, `from` or `to` outside `[min, max]` | At its pointer. Widen the axis. The arrow is how a range says it goes on. |
| A range with neither `from` nor `to` | That is the whole line. Say it in the title. |
| `from` ≥ `to` | At the pointer of `to`. |
| `from_open` without `from` (or `to_open` without `to`) | An unbounded end has no dot to leave hollow. |
| `ends` with `step` or `unit` | A named scale has no numbers to step through. |
| `value` (already refused everywhere) | Positions are `at`. |
| More than 12 points or 4 ranges | Readability budget. A fifth track means it belongs in a table. |
| Two point labels that cannot be placed without overlap | `FitError` naming both points. Spread them out, or shorten them. |
| `edges`, `series`, a second axis | One scale. Two values per item is `scatter`. |

## Roles

Points and ranges take `step` (the default), `emphasis` (bold label, filled bar with the
theme's first mark fill, so greyscale holds) and `note` (a faint mark for context).
Open and closed ends are the convention every maths textbook uses: a hollow or a filled
dot. They are not a theme choice.

## Layout sketch

1. The axis is horizontal across the canvas width, with an arrowhead at both ends.
   Ticks every `step`, labelled with the number, or with `unit` after the last one.
   With `ends`, the two texts sit under the arrowheads and there are no ticks.
2. Ranges go in tracks above the axis, one per range, in the order written. Each bar is
   inset to the track's height. An end dot sits on the bar at its value and is hollow
   when open. Each range's `text` goes at the left inside its bar, or beside the bar
   when it does not fit.
3. Points sit on the axis line. Their labels go above, in the track nearest the line
   that is free between the label's extent and any range bar, and otherwise below. The
   fit is exact: labels are boxes, and two boxes may not overlap.
4. The height is derived from the number of tracks used. There is no author control.

## Acceptance tests to write

* Reference documents for the four use cases.
* An open end draws a hollow dot and a closed end a filled one, exactly at its value
  (the centre of the dot lies on the tick for an integer value).
* An unbounded range ends in an arrowhead at the axis end and has no end dot.
* Every refusal above, at its pointer.
* `ends` suppresses tick numbers, and `ends` with `step` is refused.
* `collisions.py` and `clipping.py` are clean on the references, including the
  spectrum case with labels staggered above and below.

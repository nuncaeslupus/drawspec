# Proposal: `meter`: one amount against a scale (progress bar, thermometer, dial, bullet)

Status: **built** (see *As built* at the end). Arsenal task `t-df2996f3` (issue #96). The evidence is section 10 of
the round-2 corpus ([`../research/corpus-round2.md`](../research/corpus-round2.md),
G1–G9), read from search summaries only and every row marked **(check)**. Size **S**:
each meter is placed by arithmetic on its own scale; the work is in the labels and in
lining a panel up.

## Why

A meter says one thing: *this much, out of that*. A parish roof appeal draws it as a
thermometer filling toward the goal (G1–G3); a council's delivery plan draws a progress
bar per project (G4, G5); a roadside fire sign is a half-circle of named bands with a
needle pointing at today's (G6, G7); a dashboard designer who has read Few draws a
bullet graph, a bar on bands of grey with a target tick across it (G8, G9).

drawspec cannot draw any of these. `chart` bars stand on an axis and say nothing about
an end; `numberline` places a value on a scale but has no fill, no target, no bands;
`pie` is shares of a total. What the reader of a meter needs is the amount, the scale
it is read against, and, when there is one, the target and which named band it is in.

What it is not: a dashboard of numbers to explore. One amount per meter, at most six
meters, each with its own scale, every number written.

## Style: per document, not per meter

`style` is set once, at the top. Every multi-meter original in the corpus (G4, G9) draws
one style, aligned, so the reader compares like with like: lengths with lengths,
needles with needles. A panel mixing a dial with two bars has nothing to align, and the
eye reads the dial as the important one because it is the biggest. A document with two
styles is two documents. `style` on a meter is refused, naming the top-level field.

## Use cases

### 1. A fundraising thermometer, with a stage target (G1–G3)

```json
{
  "version": 1,
  "kind": "meter",
  "style": "thermometer",
  "title": "The chapel roof appeal",
  "caption": "Raised by 30 September.",
  "meters": [
    {"text": "Chapel roof", "amount": 41250, "max": 60000, "target": 45000, "unit": "£"}
  ]
}
```

The top of the tube is `max`, the goal. `target` is a mark under it (a stage of the
appeal). Readout: **£41,250** of £60,000, then *target £45,000*.

### 2. A project progress panel (G4, G5)

Five workstreams of a records migration, each `amount` percent complete with `unit:
"%"`, `max: 100`, and a `target` where the plan said each would be by now. A bar is the
default style. Readout: **72%**, *target 80%*.

### 3. KPI dials with named bands (G6, G7)

```json
{
  "version": 1,
  "kind": "meter",
  "style": "dial",
  "meters": [
    {
      "text": "Ward bed occupancy",
      "amount": 91, "min": 60, "max": 100, "unit": "%",
      "bands": [
        {"text": "Low", "to": 75},
        {"text": "Safe", "to": 85},
        {"text": "Strained", "to": 95},
        {"text": "Critical", "to": 100}
      ]
    }
  ]
}
```

Bands run from `min` (or the band before) up to their own `to`; the last ends at `max`.
Every band is **named**: an author who means red, amber and green writes the words
(`Red`, `Amber`, `Green` or what they stand for), and the theme fills them in tones of
the page's ink, so nothing is said by colour alone. The readout names the band the needle
is in: **91%**, *Strained*.

### 4. A bullet-chart set (G8, G9)

Four library-service measures for a year, each a bar on three bands (`Poor`, `Fair`,
`Good`) with the year's target as a tick, scales from zero, stacked with their labels
in one column.

## Fields

| Field | Where | Required | Decision |
|---|---|---|---|
| `style` | root | no | `bar` (default), `thermometer`, `dial` or `bullet`. One per document (above). |
| `meters` | root | **yes** | 1–6 meters, in reading order. |
| `meter.text` | meter | **yes** | The meter's name. A second line after a newline is its caption, drawn plain under the name: *this year's milestones only*. |
| `meter.amount` | meter | **yes** | The reading. Not `value`, which is refused everywhere by name (the same word `treemap`, `sankey`, `waterfall` and `pie` use). |
| `meter.max` | meter | **yes** | The end of the scale: a thermometer's goal, a progress bar's whole. |
| `meter.min` | meter | no | Where the scale starts, `dial` only (0 by default). A bar's length is its amount, so a bar, a bullet and a thermometer start at zero; a needle's position does not encode length, so a dial may start anywhere (a temperature from −10). |
| `meter.unit` | meter | no | `%`, a currency sign (`£`, `$`, `€`, `¥`, written before the number) or a word (`tasks`, after it). |
| `meter.target` | meter | no | A mark on the scale: the plan, the stage goal. Inside the scale. |
| `meter.bands` | meter | `bullet`: **yes**; `dial`: no | 2–5 named bands, `{text, to}`, rising; the last `to` is `max`. Refused on `bar` and `thermometer`, naming `bullet`. |
| `meter.role` | meter | no | `step` (default) or `emphasis`: the meter the panel is about, its name bold. |

## Refused, and why

| Refused | Why |
|---|---|
| `amount` or `target` outside the scale | A reading past the end has nowhere to point. Raise `max`, or lower `min` on a dial. |
| `min` on `bar`, `bullet`, `thermometer` | A bar's length is its amount; one that does not start at zero misstates it. |
| `bands` on `bar` or `thermometer` | A bar with bands is a bullet: say `"style": "bullet"`. A thermometer fills toward one goal. |
| A `bullet` meter with no `bands` | Without them it is a progress bar: say `"style": "bar"`. |
| Bands that do not rise, or whose last `to` is not `max` | The bands cover the scale once, in order. |
| `style` on a meter | One panel, one style (above). |
| `value`, `goal`, `from` on a band | `amount`; `max` (the goal) or `target`; a band runs from the end of the one before. |
| More than 6 meters, more than 5 bands | Readability budget: G4 and G9 stack a handful; past five bands the tones blur (G8: two to five). |
| `series`, `axes`, `edges` | Values against two axes are a `chart`; a meter has no connectors. |

## Layout sketch

* **`bar`, `bullet`**: one row per meter. Names (and captions) in one column at the left,
  wrapped to at most a third of the width; the tracks share one left and one right edge;
  the readouts in one column at the right. A bar's track is outlined and filled to the
  amount in the first mark fill. A bullet's track is its bands, in ramp tones lightest
  first, the band words over them, with a thin solid bar to the amount and nice ticks
  from zero to `max` under it. A target is a short heavy stroke across the track.
* **`thermometer`**: tubes side by side, one column each, the bulb at the foot filled in
  and the tube filled to the amount; ticks with their numbers at the left of each tube,
  `max` always labelled at the top. Name, caption and readout under the bulb.
* **`dial`**: half-circles, up to three to a row. The arc is the scale from `min` at the
  left to `max` at the right; bands are sectors of it in ramp tones, each word outside the
  arc at its middle. Without bands the arc fills to the amount. A needle from the hub to
  the arc; `min` and `max` under the arc's ends; readout, name and caption under the hub.
* **The readout** is the meter's numbers in words, so no reading needs the drawing: the
  amount in bold, *of* `max` on a bar and a thermometer, the band it is in on a dial and a
  bullet, and the target.

## As built

Built as proposed, as its own kind (`kinds/meter.py`). What was settled while building,
and why:

* **The fill is a solid tone, not a mark pattern.** A progress bar or a thermometer drawn
  in the first mark fill (faint dots) read as empty at a glance. The filled part is the
  first mark colour, or the page's ink, at the ramp's darkest tone: filled in greyscale,
  and the readout says the number anyway.
* **Band words are set at the body size**, as the author's words, not at the tick size:
  they are content (the reading *is* the band on a fire sign), and a smaller size made
  them look like furniture. Ticks and the scale's ends stay at the label size.
* **On a bullet the band words sit over the track**, centred on each band; a word longer
  than its band is a `FitError`, not an overlap. The ticks under it are nice steps from
  zero with `max` always labelled; a tick whose number would touch the next is dropped.
* **On a dial the band words sit outside the arc** at each band's middle, pushed out until
  they clear it; the half-circle is the largest whose words stay inside its column, so
  short words buy a bigger dial. Words that would touch each other are a `FitError`.
* **Readout before name, under a thermometer and a dial.** The reading belongs to the
  instrument, so it sits next to it; the name and its caption follow. On rows the name is
  the left column and the readout the right, as proposed.
* **A word unit is said once**: `23 of 30 sessions`, not `23 sessions of 30 sessions`;
  a sign unit (`£`, `%`) is on both numbers; a percentage of 100 is just `64%`.
* **A reading on a band boundary is in the band above**, and one at `max` in the last.
* **`colour` is refused on a meter** with the advice to write the word (`Green`), on top
  of the global refusal of `color`.

References: `meter-appeal` (use case 1, thermometer with a stage target),
`meter-migration` (2, a progress panel), `meter-ward` (3, three dials, one in
red/amber/green words) and `meter-library` (4, a bullet-graph set).

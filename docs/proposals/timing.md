# `timing` — signals over one shared time axis

Status: **built.** `src/drawspec/kinds/timing.py` (SVG and text), schema and validation in
`src/drawspec/schema.py`, the `[timing]` theme section in `src/drawspec/theme.py`, three
reference documents (`docs/reference/timing-spi.json`, `timing-i2c.json`,
`timing-session.json`) and tests in `tests/test_kinds_timing.py`.

A timing diagram draws what several signals do over the same stretch of time, a lane each,
one under another, so an edge on one lane lines up with the edge it causes on the next. It
is the figure every serial-bus datasheet carries (SPI, I²C), what WaveDrom exists to draw,
and UML's timing diagram: a lifeline's states against time. This came as an owner request
(new kinds borrowed from Mermaid, PlantUML, WaveDrom, D2), and it fills a real gap — nothing
drawspec draws puts a *level* or a *word on a bus* on a time axis. A `gantt` lays intervals
of work on time; a `sequence` orders messages down the page with no time scale; a `states`
diagram has the states and no time at all.

## The originals

Published figures, found by web search with the owner's approval to cite them, each checked
against the design below.

| # | Figure | What it needs |
|---|---|---|
| T1 | NXP, *UM10204 I²C-bus specification and user manual*, the START/STOP and "definition of timing for F/S-mode devices" figures — <https://www.nxp.com/docs/en/user-guide/UM10204.pdf>; the same figure reproduced and explained in Analog Devices, *I²C Timing: Definition and Specification Guide (Part 2)* — <https://www.analog.com/en/resources/technical-articles/i2c-timing-definition-and-specification-guide-part-2.html> | two `bit` lanes (SDA, SCL); edges at half a clock period (SDA falls *while* SCL is high); markers `S`, `Sr`, `P`; named intervals between edges (`tHD;STA`, `tSU;STO`, `tBUF`, `tHIGH`, `tLOW`) |
| T2 | Texas Instruments, *TSC2006* datasheet, serial-interface timing (SPI mode 0: CS, SCLK, MOSI, MISO) — <https://www.ti.com/lit/ds/symlink/tsc2006.pdf>; the four CPOL/CPHA modes in Analog Devices, *Interfacing SPI peripherals* — <https://www.analog.com/en/resources/technical-articles/interfacing-spi-peripherals-to-the-max7651-processor.html>, and Wikipedia's *Serial Peripheral Interface* timing figure — <https://en.wikipedia.org/wiki/Serial_Peripheral_Interface> | a clock that idles and then pulses; a select line; data lanes as hexagons of bit names (`D7` … `D0`) changing on one clock edge; high impedance and don't-care stretches; setup/hold intervals |
| T3 | uml-diagrams.org, *UML timing diagrams* (the website-latency example: a user and a server lifeline, states against ticks, a duration constraint) — <https://www.uml-diagrams.org/timing-diagrams.html> | `state` lanes (robust notation): named states as levels, a line stepping between them; named ticks under the axis; a duration between two events |
| T4 | PlantUML, *Timing diagram* — <https://plantuml.com/timing-diagram> (robust, concise, clock and binary participants) | the same four lane kinds a text format offers: robust → `state`, concise → `bus`, clock and binary → `bit` |
| T5 | WaveDrom, *Hitchhiker's Guide to the WaveDrom* — <https://wavedrom.com/tutorial.html> | the step model: one character per period, `.` extends, `p`/`n` clocks, `x` and `z`, `=` with a `data` list for buses, groups of lanes |

What they agree on: **time runs in equal steps** (a clock period, or half one) and is not to
scale in seconds; what matters in time is *named*, as an interval between two edges, not
measured off the drawing. Every original is drawn in black ink only — level, hexagon and
hatch carry the meaning.

## The design

```json
{
  "version": 1,
  "kind": "timing",
  "signals": [
    {"text": "CS#",  "values": ["1", "0", ".", ".", ".", "1"]},
    {"text": "SCLK", "values": ["0", "n", ".", ".", ".", "0"]},
    {"text": "MOSI", "lane": "bus", "values": ["z", "C1", "C0", "x", ".", "z"]},
    {"text": "MISO", "lane": "bus", "values": ["z", "z", "z", "D1", "D0", "z"]}
  ],
  "markers": [{"at": 1, "text": "start"}],
  "intervals": [{"from": 1, "to": 1.5, "text": "tCSS", "signal": "CS#"}],
  "ticks": ["0", "1", "2", "3", "4", "5"]
}
```

* **A signal is a lane**: `text` (its name, unique), `lane` (`bit`, the default; `bus`;
  `state`) and `values`, **one string per step**. Every lane has the same number of steps.
* **Why an array, not a WaveDrom string.** `"p....x=="` is shorter, but an error in it can
  only be pointed at as "character 7 of `/signals/2/wave`". An array lets every refusal land
  on the exact step — `/signals/2/values/7: 'high' is not a level` — which is what an LLM
  needs to fix it in one pass, and the length check is a count of entries, not of
  characters. `wave`, `data`, `period` and friends are refused *by name*, with the way to
  say it here.
* **The vocabulary.** A `bit` lane: `0`, `1`, `z` (high impedance, the middle line), `x`
  (unknown, hatched), `p` (a clock pulse, high then low) and `n` (low then high) — the
  pulses give half-step edges, which is what an I²C START needs (SDA falls while SCL is
  high). A `bus`: any word, drawn in its hexagon; `x` and `z` are reserved. A `state` lane:
  one of its `states`, listed top to bottom. `.` carries the step before on everywhere: a
  clock keeps pulsing, a word holds without a new edge (the same word written again is a
  new word, with an edge).
* **Groups** are a `group` name on each signal, consecutive signals only, drawn once over
  them with a bracket (Controller / Peripheral).
* **Markers** rule one edge across every lane (`at`, whole or half steps, from 0 to the
  last edge), named over the figure. **Intervals** are an arrow between two edges under a
  named signal's lane, the name over it, with guides up to the lane — rows packed so no two
  names collide. **Ticks** name the steps under an axis; an empty string leaves a step
  unnamed, and a name may run on over the unnamed steps after it.

### What is drawn, and decided by drawspec

* The steps are equal and fill the canvas width after the name column. A `bit` lane's edges
  are upright, as a level's are; a bus changes word with a slant (the hexagon), whose width
  is the theme's `[timing] slew` — a share of a step, capped at a few units. Unknown is the
  theme's hatch, high impedance the middle line.
* A bus word is written at the body size, stepped down to the label size, and **refused**
  (`FitError` at the step it was written) when it still does not fit its run — hold it for
  more steps with `.`, shorten it, or widen the figure.
* `[timing] grid = true` rules every step edge faintly, as WaveDrom does; off by default.

### Text output

Yes — a timing figure *is* a grid. Each step takes the same even number of cells (at least
four, widened until every bus word fits its run and every tick name its span); a `bit` and
a `bus` lane take three rows (high, middle, low) and a `state` lane a row per state, with
the state names right-aligned beside them. Edges are box-drawing junctions, so adjacent
words share their edge (`┬ ┴`); `x` is `░` (ASCII `x`); markers are `┆` through the blank
cells; intervals are `├─ name ─┤` (the name after the arrow when the arrow is too short).
The default text width for `timing` is 100, like `sequence` and `lanes`, because the steps
run across the line; past it the figure refuses at whatever made it wide.

## What it refuses

At its pointer: a value a lane cannot draw; a number where a string is wanted (told to
quote `"0"`); `.` on the first step; lanes of different lengths (at the shorter); a state
not in `states`; `states` missing on a `state` lane or present on another; duplicate names;
a group written apart; a marker or interval edge off the axis or inside a step (only whole
and half steps); an interval that runs backwards or names an unknown signal; `ticks` not one
per step. By name: `wave`, `data`, `period`, `time`, `duration`, `scale`, `edge(s)` (an
arrow from an edge on one signal to an edge on another, WaveDrom's `edge`, is not drawn —
see below), `role`, `type`, `id`, `name`.

**Not drawn, on purpose:** arrows between edges on different signals (WaveDrom's `node` and
`edge`, UML's messages between lifelines) — they are routed across lanes and labels, and the
originals that use them are better served by an interval on one signal plus a marker
through all; a time scale in seconds; per-step colours; analogue waveforms.

## The budget

12 signals, 40 steps, 6 states per `state` lane, 8 markers, 10 intervals. Past 12 lanes a
figure is split by bus; past 40 steps a clock pulse is narrower than five units at the
default canvas, and the word on a bus has no room. A name column so wide that a step falls
under ten units is a `FitError` at the widest name.

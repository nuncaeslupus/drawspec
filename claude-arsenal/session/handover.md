# Session Handover

<!-- Written at session end. A new session reading this file can resume without additional context. -->

**Date**: 2026-08-15 · **Branch**: `claude/drawspec-graphics-schemas-sp577b`
**PRs**: [#47](https://github.com/nuncaeslupus/drawspec/pull/47) — **merged** as `c99347f` (handover only) ·
[#49](https://github.com/nuncaeslupus/drawspec/pull/49) — **merged** as `d13b1c7`, CI green
**Suite**: 1 546 passing, 1 skipped · lint + strict mypy clean
**Gates**: 0 collisions **and 0 outside the canvas**, across 34 references *and* the consumer's 87

## What this session was

R5-1 got its decision and was built, review of it found a second defect worth
fixing, and a consumer issue arrived and was answered with a third change. All
three are in #49.

## The three

| | What | Where |
|---|---|---|
| **`[canvas] margin`** | one outer margin, read from the theme, applied in one place. Four emergent answers — 0 / 10.5 / ~22 / 24.5 — become one | `theme.Canvas.margin`, `render.framed` |
| **`_within_width`** | a drawing wider than the canvas is refused instead of emitted as an oversized `viewBox` | `render._within_width` |
| **`[box] lead = "rule"`** | a third lead treatment: a line between a label's two parts, so a box can be a name over what belongs to it | `text.wrap`, `geometry.span_at`, `kinds/common.lead_rule` |

## The thing worth carrying forward

**Where a frame comes from matters more than what it is set to.** The obvious
implementation of R5-1 takes the margin *out* of `[canvas] width`: families lay
out against `width - margin * 2` and the emitted canvas stays 640, which is the
tidier story because the number a consumer sets to match their column is the
number the file comes out. It breaks a document that used to draw.
`timeline-disaster` sizes every label to its **tightest** pair of marks and needs
630 of its 640, so twelve units a side refused a diagram nobody had touched — and
it could not be given more width either, because `canvas_width_variance == 0` is
this project's own acceptance gate, so the escape hatch and the invariant are the
same field.

So the margin goes **around** the width. `width` and `height` keep describing the
drawing, the canvas is `width + margin * 2` for every kind alike, and no layout
budget moved except the one that was wrong: `kinds/graph` had been charging every
flow and tree 48 units for a gutter it no longer draws.

Measured over the 33 references: smallest outer gutter **0.00 → 12.00**, spread of
the tightest side **24.50 → 6.00**. The residue is interior — half a stroke, and
`[edge] clearance` around a matrix's outermost cells, which cannot come off
without making the edge cells wider than the middle ones.

## Review found one real defect, and it predates the branch

A family checks its *layout* against the width; the drawing is not the layout. A
band's bar and name sit beside the boxes, are measured after placement, and are
in nobody's budget — so a layout that exactly fills the canvas produces a drawing
that does not, and `centred` leaves an oversized scene alone by design. The
reproducer is **7 units over on `main`** and **90 with the graph cushion gone**.
`_within_width` refuses it after the elastic fit has tried every smaller scale,
`width_mode = "ink"` exempt. Two other findings were declined with the check
written into the thread; a third was intended and is now said out loud
(`height_binding` bounds the drawing, not the canvas).

Also a fourth hole in `tools/clipping.py`, found by pointing the new measurement
at the gallery: a fill pattern's tile lives in `<defs>` in the pattern's own
coordinate space, and measuring it as canvas coordinates pinned phantom ink to the
top-left corner of five chart drawings.

## The consumer issue

[#48](https://github.com/nuncaeslupus/drawspec/issues/48) — no way to say *who
performs a step*. The diagnosis holds and was checked: a node role is four
non-colour channels and they are exactly the four the greyscale invariant
compares, all four already spent, so ownership would need a fifth channel rather
than a ninth role.

Answered with `[box] lead = "rule"` rather than with an `actor` field. No new
document field — the same blank-free newline the format already reads as *these
are two things*, with the theme deciding what separates them. That covers the
**content** half and not the scannable half, which is written into the reply, so
the issue stays **open**. `actor` remains available as a separate additive step.

## Next session

`docs/plan-round-five.md` carries the full record of R5-1, including the rejected
alternative. **R5-2 `lo-0e91` (`edge-from-a-group`) is the one open task** — still
refused, still `gap4` on the consumer's sheets 39 and 44.

**Two things about the queue that cost time this session, so they are written
down:**

* The coordination branch (`arsenal-queue`) is **not** stale — `T1`–`T18` /
  `G1`–`G6` are all `done` there. It is the copy on `main` that still shows them
  `open`. The previous handover said the queue was stale; that was reading the
  wrong copy.
* The R5 tasks were authored on `main` during a feature-branch session, so they
  were invisible to the coordination branch until `queue_sync.sh` ported them.
  Run step 1b of the protocol before trusting `queue_eval.sh`.

`lo-2382` is recorded `done` against #49 with its gate re-run and passed.

Content decisions unchanged and still the owner's: **01**, **27**, the glosses on
**53 / 74 / 81**, and the English-against-Catalan redraws **27, 83, 86**.

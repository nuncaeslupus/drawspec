# Session Handover

<!-- Written at session end. A new session reading this file can resume without additional context. -->

**Date**: 2026-08-13
**Branch**: `claude/graphic-types-review-l28z1e` · **Last PR**: [#20](https://github.com/nuncaeslupus/drawspec/pull/20)

**A human reviewed all nine kinds by eye and found ten defects.** Every one of
them was in a drawing that passed every mechanical gate — which is what the
specification predicts and what `make gallery` exists for. All ten are fixed on
this branch, each with a test that fails without it: **915 passing**, up from 868.

## What was reviewed

The nine reference documents, rendered and published as a review sheet. The
reviewer's report is the source of the ten items below; nothing here came from a
gate.

## The ten, and why each was drawable

| Fix | Root cause |
|---|---|
| One canvas width for every kind | The canvas was cropped to the ink, so a 365-wide flow and a 602-wide tree scaled differently in one page — the same 11pt label read at two sizes. Now centred on the theme's canvas; `[canvas] width_mode = "ink"` restores the old behaviour. |
| Routes keep clearance from boxes they pass | A path along a border is as short and straight as one beside it. Boxes are grown by a new `[edge] clearance` before blocking the search. |
| Two routes no longer share one line | Both edges crossing a gap get the same cheapest route. Overlapping runs are separated after routing — grouped by overlapping stretch, not by lane. |
| Arrow heads have a straight run | The first lane in front of a port could be 1.7 units away. Degenerate lanes dropped; the approach is floored at the head length; a route that still turns too close is refused. |
| An open head is never dashed | It was stroked with the role's dash. `Path.marker` says a head is a mark, not a length of line. |
| Cycle arcs reach both steps | Clearance came from the box *diagonal* while an arc arrives side-on. Both ends are now found on the box outline by bisection. |
| The bold word keeps its space | SVG strips whitespace at the edge of a text element. |
| Centred text stays centred on a phone | Per-run coordinates were computed in a font the reader may not have. |
| Timeline ticks touch their labels | The tick started beside the axis, so the pairing was the reader's inference. |
| Pyramid/rings type size | Level height was a fixed fraction of the base; it now comes from the labels. The type level went to `heading` for one round and came straight back to `body` — a reader picked those two kinds out of the nine at once. **Every kind sets its shape text at one level, and `test_every_kind_sets_its_text_at_the_same_level` says so.** The shape gives, not the type. |
| Chart point labels | Precision came from the axis step, so 7.2/6.8/7.4/6.9 all printed `7`. It now comes from the data. |

## The structural change worth knowing about

`TextRun` (one positioned element per span) is joined by **`TextLine`** (one
anchored element, spans as `<tspan>`s laid out by the reader's renderer). Box
text uses `TextLine`; single-run furniture — chart tick labels, edge labels —
still uses `TextRun`. `kinds.common.line_bounds` is how a test measures a line.

`scene.moved` / `scene.extents` are shared translation and bounds helpers; every
family should use them rather than reimplementing.

## If work continues

- **Queue anomaly, unresolved.** `queue_eval.sh` hands back `lo-dcd5` (T1) and
  the whole of T1–T18 as `open` on the default branch, while the previous
  handover records them all merged through PR #18. It looks like a stale seed on
  `main` rather than real work. Confirm against `arsenal-queue` before acting;
  nothing was done to it this session.
- **Left open on purpose**: irregular timeline spacing (a different kind, not a
  fix); edge bundling for the comb of three arrows leaving one box; chart marks
  beyond lines — bars, areas — which is where the real work in that kind is.
- **The habit held.** Every one of these ten came from rendering and looking.
  Keep ending a rendering task with `make gallery`.

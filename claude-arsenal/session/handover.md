# Session Handover

<!-- Written at session end. A new session reading this file can resume without additional context. -->

**Date**: 2026-08-15 · **Branch**: `claude/drawspec-feedback-schemas-62zkuf`
**PR**: [#45](https://github.com/nuncaeslupus/drawspec/pull/45) — open, **CI green**, Qodo **0 bugs**
**Suite**: 1418 passing, 1 skipped · lint + strict mypy clean · **0 collisions across 33 drawings**

## What this session was

Round four of the corpus review, from the consumer (`nuncaeslupus/opos`). It named
two round-three items that do not hold up, five things that cannot be said, and
five defects — ten in all. **All ten are done, in seven commits on the PR above.**

Everything was reproduced against the code before being fixed. Where the report
gave a number, the number was re-measured independently; where it named a defect,
the defect was made to fail a test first.

| Item | What it was | Where it landed |
|---|---|---|
| `label-on-its-own-line` | 3 gallery collisions, reproduced exactly | `drawspec/clearance.py` — scene-level pass |
| `sibling-order` | one child broke a whole fan's declared order | `layout/layered.py` `_sweep` |
| `uniform-box-size` (width) | one paragraph set every box's width | `kinds/graph.py` `_sized`, scoped by container |
| `validate` vs `render` | validator passed what the renderer refused | `cli.py` — validate now draws and discards |
| `curve-categories` | accepted, drew nothing | `charts.py` — named marks on curve axes |
| `span-text-raw` | `**RPO**` drew its asterisks | both span kinds now go through `wrap` |
| `height-not-binding` | documented as a constraint, read by nothing | `render.py` `_within_height` |
| `always-down` | `right` unreachable for any document | `layout/base.py` — `max_height` |
| `dashed-headless` | no such edge role existed | `aside`, seventh edge role |
| `sibling-bands` | two peer bands over one set unsayable | `bands`, new document field |

## The one thing worth carrying forward

**A measurement that runs in the suite beats one run by hand.** `tools/collisions.py`
answers *can the word be read* — the counterpart to a coverage check's *is the word
there*. It does a browser-based checker's arithmetic against **the same font metrics
the layout used**, for two reasons: the belief is where the bug is, and a check that
needs a browser runs once, in the round that added it. It found the report's three
collisions independently, and it is now a per-document gate.

Qodo then made it stricter (a stroke is paint around a centreline, so the checker
measures the paint) and the gate still reports zero.

## Still open, and not code

Content decisions the owner has to make, carried over from the report: sheets **01**
and **27**, and the glosses on **53 / 74 / 81**. Also still outstanding from the
previous session and untouched here: three redraws written in English against a
Catalan source — items **27**, **83**, **86**.

## Next session

Nothing is mid-flight. If #45 has merged, round four is closed; the natural next
input is round five from the consumer. If it has not, check the PR for review
comments — CI was green and Qodo clean at hand-off.

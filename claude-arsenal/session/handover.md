# Session Handover

<!-- Written at session end. A new session reading this file can resume without additional context. -->

**Date**: 2026-08-12
**Branch**: `claude/continuation-yq88jv` · **Last PR**: [#18](https://github.com/nuncaeslupus/drawspec/pull/18)

**The plan is finished.** Every task in `status/plan.md` — T1 to T18, plus T0,
T6b and D-1 — is delivered, gated and merged. PRs #2 to #18 are all merged; the
queue holds 21 rows, all `done`, and `queue_doctor` reports 0 findings.

## Last task

- **ID**: `lo-c107`
- **Title**: T18 — acceptance close-out
- **Status at handover**: `done` ([#18](https://github.com/nuncaeslupus/drawspec/pull/18), merged); nothing claimed, nothing in flight

## What was done this session

Eight tasks, and four rendering defects that no gate had caught.

| Task | Gate | Measured |
|---|---|---|
| T14 | `unlabelled_axis_count == 0` | `0` — impossible by construction: the schema requires both axis labels |
| T9 | `edge_anchor_violations == 0` | `0` over 92 routes (3 graphs × 2 engines × 2 directions), measured against the shapes |
| T10 | `label_overlap_count == 0` | `0` — five labels clear of every shape, every route segment and each other |
| T11 | `text_overflow_count == 0` | `0` — every run inside the box measured for it; the gallery draws all 9 kinds |
| T15 | `cli_exit_code_mismatches == 0` | `0` — every code in §5.4 asserted as a value |
| T16 | `unrepresentable_failure_families == 11` | `11`, each by the schema or by an invariant, never by example |
| T17 | `embedding_safety_violations == 0` per profile | `0` and `0`; the PDF conversion really runs in CI |
| T18 | `nondeterministic_reruns == 0` | `0` in this interpreter and in two freshly seeded ones; renders with `PATH=""` |

Suite: **868 passing, 1 skipped** (the PDF conversion, where no converter is
installed). ruff, ruff format and strict mypy clean.

## What looking at the output found

Every one of these came from rendering the references and looking, not from a
gate. The habit is worth keeping: **end a rendering task by running `make
gallery` and opening it.**

1. **Bold was measured with the regular face**, so the following run started 3.8
   units early and landed on top of it. Weight is now threaded end to end.
2. **Half of every flush stroke was outside the viewBox**, which read as uneven
   line weight. The viewBox is now the bounds of the ink.
3. **Ports landed on a diamond's bounding box**, so an arrow stopped in the empty
   corner beside it, pointing at nothing. Anchors are projected onto the outline.
4. **Route lanes hugged the boxes**, so a connector ran the width of its target
   just above the border and read as an underline. Lanes are mid-gap now.

## If work continues

Nothing is queued. Candidates, none of them blocking:

- **Edge bundling.** Three sibling edges leaving one node run parallel a few
  units apart before they diverge, which reads as one thick line at small sizes.
  A shared trunk would look better; port spreading is what keeps a decision's two
  branches apart, so the two cases want different treatment.
- **The node width share is one tuned number** (a quarter of the canvas). It is
  what lets the reference tree fit at all, and it makes a `down` flow narrower
  than it needs to be. A per-direction limit, or a second sizing pass, would do
  better than one constant.
- **`docs/gallery/` is committed** so a diff shows what a change did to the
  pictures. It has to be regenerated when rendering changes, and nothing enforces
  that yet.

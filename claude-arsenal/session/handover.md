# Session Handover

<!-- Written at session end. A new session reading this file can resume without additional context. -->

**Date**: 2026-08-12
**Branch**: `claude/drawspec-graphs-tool-8jkf9o` · **PR**: [#1](https://github.com/nuncaeslupus/drawspec/pull/1) (open, unmerged)

## Last task

- **ID**: — (no task claimed yet)
- **Title**: —
- **Status at handover**: all 18 tasks `open`; nothing claimed, nothing in flight

## What was done this session

Everything up to but not including implementation. drawspec was bootstrapped
from nothing: claude-arsenal vendored at `v0.23.1` for Claude Code web, the
Python toolchain set up to the arsenal defaults (uv, ruff, strict mypy, pytest,
src layout) with GitHub Actions CI on 3.12/3.13, the evidence corpus landed in
anonymized form, and the full specification and plan written, reviewed by the
user through the annotatable reader, and revised against their notes. The queue
was then seeded from the plan. Last commit `d332c98`; both the PR branch and the
`arsenal-queue` coordination branch are pushed and clean.

**Read these before doing anything else** — they carry decisions that are not
obvious from the code, because there is no code yet:

- `status/specification.md` — the candidate survey, the recommendation, the four
  contracts, the risks, and the product direction.
- `status/plan.md` — 18 tasks with gates, tests and the dependency graph.
- `docs/brief.md` — the problem and the 11 failure families that are the
  acceptance suite.
- `docs/theme-requirements.md` — what a theme must be able to express.

### Decisions already taken — do not relitigate

- **Option B**: drawspec owns the renderer; graph layout sits behind a
  `LayoutEngine` protocol. No system binaries — `pip install drawspec` is the
  whole install story. (The user's stated fallback: if pure Python proves
  inadequate, *then* price adding a C or Node dependency. Not before.)
- **Two seams carry the design**: `Scene` (all rendering families converge on
  one untyped primitive list, so embedding-safety lives in one file) and
  `LayoutEngine` (one method, sizes in and coordinates out).
- **Font resolution**: replace and warn, never fail on this alone, never
  silent. Bundled generic serif/sans/mono so substitution is deterministic
  across hosts.
- **Sizing**: width binding, height advisory unless explicitly marked binding.
- **Themes**: TOML, parsed to a frozen dataclass.
- **Elastic fit**: one uniform scale factor across *all* type levels at once.
  Never per-level — that reintroduces the corpus's most common failure.
- **Edge roles** are semantic (`flow`, `link`, `exchange`, `weak`, `owns`); the
  theme resolves head geometry. The author can say "merely associated", never
  "filled triangle".
- **Two embedding profiles**: `inline` (inherits colour) and `standalone`
  (explicit colour and dimensions, for linked `.svg` and PDF conversion).
- **Layout engine choice is deliberately still open** — T7 is a spike that
  settles grandalf vs a direct implementation on rendered output. Do not
  pre-empt it in T8.

### Repository hygiene

The corpus under `corpus/fixtures/` is **anonymized** — the originals belong to
a different project. Never restore original text, and do not add any content
from that project. Everything authored in this repo is in **English**.

## What remains

All 18 tasks. Nothing has been implemented; `src/drawspec/` holds only the
scaffold (`__init__.py`, a `cli.py` stub) that CI hangs from.

Four tasks are immediately dispatchable, with no dependency between them:

| Task | | Gate |
|---|---|---|
| `lo-b94c` | T3 — text measurement (`fonttools`, replace-and-warn) | `text_measurement_error_ratio <= 0.02` |
| `lo-dcd5` | T1 — Scene primitives, emitter, both profiles | `embedding_safety_violations == 0` |
| `lo-4f9b` | T2 — theme, role vocabularies, elastic fit, greyscale | `greyscale_ambiguous_role_pairs == 0` |
| `lo-1c47` | T4 — document model + published JSON Schema | `forbidden_field_acceptance_count == 0` |

**Start with T3.** It is on the critical path (T3 → T5 → T6 → T7 → T8 → T9 →
T10 → T11 → T15 → T17 → T18) and gates box sizing, which gates everything else.

### Open questions for the user

- Whether to run the orchestrator loop with real worker fan-out, or work tasks
  serially. This session worked serially by default because subagents were not
  requested. T1–T4 are exactly the independent batch fan-out is built for.
- Diagram titles ("Figure 1" style) — proposed as a theme switch, default off.
- The metric-compatible fallback font set: which families, and bundled versus
  mapped onto host fonts.

## How to continue

1. Read `claude-arsenal/AGENTS.md` for the worker loop algorithm.
2. `export ARSENAL_QUEUE_DIR="$(claude-arsenal/bin/queue_branch.sh)"` — the
   selector, `claim.sh` and `release.sh` all read the coordination worktree,
   **not** the main tree. Seeding into the main tree's `tasks.jsonl` alone makes
   the queue look empty; that trap already bit once this session.
3. `claude-arsenal/bin/queue_eval.sh` for the next unblocked task.
4. Gates are mechanical — every payload carries a fenced bash block. They
   currently exit **1** (tests do not exist yet, the correct RED state), not
   **3** (could not run). Write the payload's named tests RED first.

## Surface profile at handover

```json
{
  "surface": "unknown",
  "capabilities": ["surface:cli", "surface:web"]
}
```

Claude Code on the web: no `/plugin` support, so skills are vendored into
`.claude/skills/` and refreshed with `make update-skills`. Pushes to both the
PR branch and `arsenal-queue` were verified working this session, so the
shared-ref claim lock is functional here.

## Queue snapshot at handover

```
total=18  open=18  in_progress=0  done=0  merged=0  blocked=0  escalated=0

  lo-dcd5  [open]  T1: Scene primitives, SVG emitter with both embedding profiles
  lo-4f9b  [open]  T2: Theme dataclass, TOML loader, role vocabularies, elastic fit
  lo-b94c  [open]  T3: Text measurement from font files via fonttools
  lo-1c47  [open]  T4: Document model, validation, published JSON Schema
  lo-533d  [open]  T5: Line breaking and text block sizing            deps=T2,T3
  lo-b7a8  [open]  T6: Box geometry, vertical centring, elastic fit   deps=T5
  lo-4c51  [open]  T7: SPIKE — LayoutEngine: grandalf vs direct       deps=T6
  lo-e93c  [open]  T8: The chosen default layout engine              deps=T7
  lo-7bfe  [open]  T9: Orthogonal routing, border anchoring          deps=T8
  lo-9dd6  [open]  T10: Edge label placement, overlap avoidance      deps=T9
  lo-b569  [open]  T11: Graph kinds — flow, tree, cycle              deps=T1,T4,T10
  lo-2f7f  [open]  T12: Grid kinds — stack, timeline, columns        deps=T1,T4,T6
  lo-f75a  [open]  T13: Shape kinds — pyramid, concentric rings      deps=T1,T4,T6
  lo-0e20  [open]  T14: Chart kind — scales, ticks, axis labels      deps=T1,T4,T6
  lo-38d8  [open]  T15: CLI                                          deps=T11..T14
  lo-1291  [open]  T16: The acceptance suite — 11 failure families   deps=T11..T14
  lo-30b0  [open]  T17: Embedding targets — Markdown, HTML, PDF      deps=T15
  lo-c107  [open]  T18: Acceptance close-out                         deps=T16,T17
```

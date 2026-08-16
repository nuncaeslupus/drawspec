# Session Handover

<!-- Written at session end. A new session reading this file can resume without additional context. -->

**Date**: 2026-08-16 · **Branch**: `claude/continuation-hkhyz8`
**PR**: [#51](https://github.com/nuncaeslupus/drawspec/pull/51) — open, CI running at hand-off
**Suite**: 1 564 passing, 1 skipped · lint + strict mypy clean
**Gates**: 0 collisions **and** 0 outside the canvas across 34 references · `gate_run.sh lo-0e91` passed

## What this session was

One task: **R5-2 `lo-0e91` — `edge-from-a-group`**, the last open row in the
queue. It is recorded `done` against #51 with its gate re-run and passed.
**The queue is now empty of open tasks.**

## The change

`{"from": "watch", "to": "plane"}` where `plane` is a declared group validates,
routes, and draws an arrow that stops on the frame's border — the reverse
direction too, and group to group. `gap4` on the consumer's sheets **39** and
**44**; 44 had been `blocked` on it for five rounds.

## The thing worth carrying forward

**Routing asks two questions about a box and had only ever needed one answer.**
*May a line cross you* and *may a line land on you* — `route_edges` built its
endpoint lookup **out of** its obstacle list, so the two were the same set by
construction. A frame has never been allowed in that list (every edge reaching a
box inside a group crosses that border to get there), so it could not be an
endpoint either. That, and nothing about geometry, is why the feature was
missing: `Frame` already had an extent, `border_obstacles` already treated its
sides as geometry, `crossed` already lifted edges to the level holding both ends.

So the fix is one keyword-only `route_edges(..., anchors=…)` and
`kinds/containers.frame_anchors` as its only use. Ports, stubs, lanes, the grid
and label placement already keyed off `route.source`/`route.target` rather than
off membership of the obstacle list, so none of them needed to know. **Ranking
needed nothing at all** — a group is one node of its own size in its parent's
layout and `Nesting.lift` returns it unchanged.

Two refusals came with it: a container joined to something already inside it (at
any depth — it would leave a border and arrive within it), and, still, an id that
is neither a node nor a group. The id space grew; it did not open.

`docs/reference/flow-groups.json` is the demonstration — a monitoring platform
arriving on the control plane itself, clear of the caption in its corner.
`docs/plan-round-five.md` carries the full record; `docs/guide.md` has the
paragraph an author would look for.

## Queue state, and one thing to fix

`queue_doctor.sh` reports **4 ERROR [missing-payload]** — `lo-ee92`, `lo-1b55`,
`lo-b67b`, `lo-1270` (G3–G6) reference payload files that are not on the
coordination branch. All four are `done` with merged PRs, so nothing is blocked;
it is a ledger inconsistency to clear, not work. Pre-existing — it predates this
session.

`reconcile_merged.sh` cannot run here (`gh` is not installed in this
environment), so `done` rows never flip to `merged`. Run it from the laptop to
settle the board.

## Next session

**Nothing is open.** Round five is finished on this side: R5-1 (#49) and R5-2
(#51) are both done. Before seeding anything new, ask — there is no plan file
with unstarted rows.

Standing carry-overs, unchanged and still the owner's: content decisions on
sheets **01** and **27**, the glosses on **53 / 74 / 81**, and the
English-against-Catalan redraws **27, 83, 86**.
[#48](https://github.com/nuncaeslupus/drawspec/issues/48) stays **open** — `[box]
lead = "rule"` covered its content half and not its scannable half, and `actor`
remains available as a separate additive step.

**Two queue facts still worth knowing** (they cost the last session time and are
unchanged):

* The coordination branch `arsenal-queue` is the source of truth. The copy of
  `tasks.jsonl` on `main` is stale and shows finished tasks `open`.
* Tasks authored on `main` during a feature-branch session are invisible to the
  coordination branch until `queue_sync.sh` ports them — protocol step 1b.

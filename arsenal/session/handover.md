# Session Handover

<!-- Written at session end. A new session reading this file can resume without additional context. -->

**Date**: 2026-08-28 · **Branch**: `claude/github-coderabbit-limits-huuu88`
**This session**: migrated `claude-arsenal` from the coordination-branch queue
(v0.23.1) to the GitHub-issues task board (v2.4.23) — [#70](https://github.com/nuncaeslupus/drawspec/pull/70)
— and added a `scatter` kind, requested by `integral-job-search` — [#71](https://github.com/nuncaeslupus/drawspec/pull/71).
**Suite**: 1 662 passing, 1 skipped · lint + strict mypy clean
**Tasks**: 6 live (issues #64–#69, `arsenal:task`), 38 terminal (archived in
`arsenal/tasks/_history/`)

---

## Read this first

**The task board is GitHub issues now, not a queue file.** List issues labelled
`arsenal:task` (open and closed), then `python3 claude-arsenal/scripts/task_select.py`
picks the next unblocked one — see `claude-arsenal/AGENTS.md`'s session-start
protocol. The five pre-existing tasks below are unchanged in substance; only the
mechanics of finding and claiming them changed.

**Every one of the five pre-existing tasks still needs a laptop** — no code work
is left for them. **One switch unblocks four of the five.**

> **Settings → Pages → Source: Deploy from a branch → `main` / `/` (root)**

| | | Blocked on |
|---|---|---|
| **C2** `lo-f0f8` (#66) | Flip Pages on, open the gallery, look at it | the switch |
| **C3** `lo-70ef` (#67) | Run its gate; it fetches `SCHEMA_ID` and compares to the committed artefact | C2 |
| **C1** `lo-2158` (#65) | Topics, homepage, description — values are paste-ready | C2 (supplies the homepage) |
| **C4** `lo-52fa` (#68) | Sweep the consumer's 87 documents onto the new `$schema` | C2 |
| **A3** `lo-666f` (#69) | PyPI: configure the trusted publisher, bump, tag, push | C3 |

Every payload is self-contained: exact values, exact commands, and why the order
is what it is. `C1` and `C2` are `laptop` because **the GitHub tooling in a cloud
session has no repository-settings API** — no topics setter, no Pages toggle.
That is a capability limit, not an oversight. `A3` is `laptop` because a cloud
session cannot hold a PyPI credential; everything else about the release is
built and merged.

**The sixth task, `scatter` (`lo-825e` / #64), is implemented and its PR is
open**: [#71](https://github.com/nuncaeslupus/drawspec/pull/71), pending
review — not yet merged, so `lo-825e` is still a live task file, not archived.
It needed no laptop: a 2-D kind, two continuous ticked axes, reusing
`quadrant`'s axis machinery and `chart`'s tick furniture almost unchanged.
Once #71 merges, `open_task_pr.sh`'s archival moves the task file to
`arsenal/tasks/_history/` and closes #64 automatically — nothing to do by
hand.

## What this session did

**R5-2** (`edge-from-a-group`) closed the old queue. Then the owner asked whether
the project was in good shape to show people; it was audited, and the answer
became an eleven-task round tagged `readiness`, of which seven shipped in #52 and
two more in #53.

**The audit's finding, which is the thing to carry forward:** the problem was
never quality — it was that almost none of the quality was **reachable**. Strict
mypy no consumer's checker could see; a 34-drawing gallery you had to clone to
look at; a format an agent could not learn without reading 800 lines; a schema
`$id` naming a domain that does not resolve; and `pip install drawspec` returning
nothing.

Shipped: `py.typed` and full PyPI metadata · **`AGENTS.md`** (185 lines, gated so
it cannot drift) and `llms.txt` · `drawspec kinds` and `drawspec example <kind>`,
with `validate` reading `-` so they compose · a README that shows three specs
each above **its own** drawing · CONTRIBUTING, CHANGELOG, issue templates · the
schema and gallery repointed at GitHub Pages · and a tag-triggered release
workflow with trusted publishing.

## Three things that cost time, so they are written down

* **A gate's zero means nothing until something has tried to get past it.** This
  bit twice. `AGENTS.md`'s example gate caught a skeleton document with
  `"nodes": []` on its first run — the file would have shipped telling agents to
  write something invalid. And the Pages coupling test I wrote was **vacuous**:
  it searched the README for `SCHEMA_ID`'s host, which the README always
  contains because it quotes `SCHEMA_ID` in full. Review caught it. It now parses
  the gallery link out and compares hosts, verified by deleting the link and
  watching it fail.
* **A gate block containing a fenced ` ```json ` block must spell the fence in
  hex** (`\x60\x60\x60`). A nested fence closes the outer one and the gate dies
  on a `SyntaxError` instead of reporting a verdict. Two payloads hit this.
* **`gate_run.sh` hardens the environment**, which breaks anything needing the
  network — `uv build` fails TLS with `UnknownIssuer`. Use
  `ARSENAL_GATE_INHERIT_ENV=1` for gates that fetch or build.

## B3 shipped: the MCP server (#60)

`pip install 'drawspec[mcp]'` and `drawspec-mcp` — `validate`, `render`, `kinds`
over stdio, behind an extra so nobody rendering from Python pays for starlette.
`validate`'s refusals now arrive as `{"pointer", "message"}` in the agent's own
loop instead of as prose on stderr.

Two things about it worth not relearning:

* **`mcp>=2.0`, not looser.** The 2.0 SDK's server is the `on_list_tools` /
  `on_call_tool` callback API; a wider floor resolves to something that imports
  and then fails to serve. Also: construct its models with the **snake_case**
  field names (`input_schema`, `is_error`) — mypy rejects the camelCase aliases,
  and pydantic still puts camelCase on the wire.
* **The tests drive the process over a pipe** rather than calling the handlers.
  Every failure this server can have is a transport one, and none of those are
  visible from inside the process.

It closes a *convenience* gap, not a reach gap: an agent still has to know
drawspec exists, which `A3` and `C1` address far more cheaply. **Still do those
first.**

## F1 shipped: `actor` (#62), and issue #48 is answered

The thing worth carrying forward is **why it was stuck for two rounds and why it
turned out to be small.** The diagnosis was: four non-colour channels, all spent
on the eight roles, therefore no room for ownership. That was true, and it
assumed ownership must be encoded as **appearance**. It need not be — the tag
carries the actor's *name*, and text is distinguishable in greyscale by
construction. So it costs none of the four channels and `theme check` needed no
new axis, which is why the field is free text rather than an enum.

Drawn as the box's **lead**, so the existing lead machinery reserves the space at
measure time — the part that would otherwise have been hard.

**Bands were measured, not argued about,** and both failures are now tests so
nobody re-proposes them: a band's bar spans its members' *extent*, so a
discontiguous owner's bar runs straight past a step it does not own; and a band
over a single node cannot be named, because the name has to fit its members'
span. Swimlanes remain deliberately unbuilt — revisit only with evidence that a
per-node marker is not enough.

Two reference documents carry it: `flow-actors` (the issue's pipeline) and
`flow-actor-handover`, which is the same four steps `flow-bands` draws so the two
sit side by side as *accompanying* versus *owning*.

## After those

What is left is not a task and should not be invented as one:

* **Measure whether the readiness round worked.** Does an agent handed only
  `AGENTS.md` produce valid documents? It is the claim the whole project rests
  on and nothing has tested it — but *how* to test it is a real design question
  (what counts as the subject, what counts as a pass), so it wants a decision
  before a task. Checked, and deliberately not queued: a corpus re-measurement
  would **not** serve here — `docs/kinds-wanted.md` already records all five
  vocabulary gaps as closed, so re-running it would confirm what is written.
* The owner's standing content decisions — sheets **01** and **27**, the glosses
  on **53 / 74 / 81**, the English-against-Catalan redraws **27, 83, 86**.
  Untouched across five rounds because they are judgement calls, not work.

## Task-board mechanics worth knowing

* **GitHub issues are the source of truth now, not a branch.** The old
  `claude-arsenal/queue/tasks.jsonl`, `queue_sync.sh` and `queue_eval.sh` are
  gone from the tree — removed by the v2.4.23 migration. The `arsenal-queue`
  coordination branch is obsolete and no longer authoritative, but its
  **remote deletion is still pending manual cleanup** — this session's push
  access is restricted to its own branch, so `git push origin --delete
  arsenal-queue` needs a human or a session without that restriction. Do not
  read from it or push to it in the meantime; a task's real state is its
  issue's open/closed state plus its `arsenal:claimed` label —
  `python3 claude-arsenal/scripts/query_status.py` reads the board.
* Each live task file (`arsenal/tasks/<id>.md`) carries an `arsenal-task: <id>`
  line in its linked issue's body — that is the whole of how an issue resolves
  to a task, so never strip it when editing an issue by hand.
* PR #70 (the migration itself) had a CodeRabbit review flag ~14 real bugs in
  the *vendored* bundle content it brought in (`claude-arsenal/`, the skills
  under `.claude/skills/`, `.github/workflows/arsenal-queue.yml`) — things like
  an unquoted curl arg, a `pull_request_target` authorization gap, and a
  skill-edit gate that does not recognize `git restore`. None of that is
  drawspec's to hand-patch (upstream owns that prefix and overwrites it on the
  next refresh); filed upstream instead. Check
  [nuncaeslupus/claude-arsenal](https://github.com/nuncaeslupus/claude-arsenal/issues)
  for the tracking issue before assuming those are still open — a bundle
  refresh may have already pulled the fixes in.

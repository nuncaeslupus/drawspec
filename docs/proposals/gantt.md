# Proposal: `gantt` — tasks as intervals, one row each

Status: **proposed**. Size **M** (reuses the chart axis; rows and bars are new).

## Why not `timeline`

A `timeline` is one axis of instants, with `spans` between them: *when things happened*.
A Gantt chart is **one row per piece of work**, each an interval, and what the reader
looks for is overlap — which tasks run in parallel, what waits on what, what the plan
looks like in week six. The rows are the content. Bolting rows onto `timeline` would
give it two meanings of `items`; a kind keeps each one simple.

## Scope, decided up front

drawspec's chart has **no dates**, and that stays true here. A task's start and end are
**numbers in a unit the author names** (week 3, day 12, minute 45), and the axis can name
its positions. A real calendar — weekends, month lengths, time zones — is a project
tool's job. This is the deliberate cost of the kind, and the first thing the owner
should confirm (see *Open questions*).

## Use cases

### 1. Design document — a migration plan

```json
{
  "version": 1,
  "kind": "gantt",
  "title": "Moving search to the new cluster",
  "axis": {"label": "Week", "min": 0, "max": 10},
  "tasks": [
    {"id": "provision", "text": "Provision the cluster", "start": 0, "end": 2},
    {"id": "mirror", "text": "Mirror writes to both", "start": 2, "end": 5},
    {"id": "backfill", "text": "Backfill history", "start": 2, "end": 6, "role": "emphasis"},
    {"id": "shadow", "text": "Shadow-read and compare", "start": 6, "end": 8},
    {"id": "cutover", "text": "Cut reads over", "at": 8},
    {"id": "retire", "text": "Retire the old cluster", "start": 8, "end": 10}
  ],
  "groups": [
    {"id": "prepare", "text": "Prepare", "members": ["provision"]},
    {"id": "move", "text": "Move", "members": ["mirror", "backfill", "shadow", "cutover"]},
    {"id": "finish", "text": "Finish", "members": ["retire"]}
  ],
  "edges": [
    {"from": "provision", "to": "mirror"},
    {"from": "backfill", "to": "shadow"},
    {"from": "shadow", "to": "cutover"}
  ],
  "marks": [{"text": "today", "at": 3}]
}
```

A task with `at` instead of `start`/`end` is a **milestone**, drawn as a diamond.

### 2. Course notes — finding the critical path

```json
{
  "version": 1,
  "kind": "gantt",
  "title": "Six activities, one critical path",
  "caption": "Emphasised bars have no float: delaying any of them delays the project.",
  "axis": {"label": "Day", "min": 0, "max": 14},
  "tasks": [
    {"id": "a", "text": "A — design", "start": 0, "end": 3, "role": "emphasis"},
    {"id": "b", "text": "B — order parts", "start": 0, "end": 5},
    {"id": "c", "text": "C — build frame", "start": 3, "end": 8, "role": "emphasis"},
    {"id": "d", "text": "D — fit parts", "start": 8, "end": 11, "role": "emphasis"},
    {"id": "e", "text": "E — write manual", "start": 3, "end": 6},
    {"id": "f", "text": "F — test", "start": 11, "end": 14, "role": "emphasis"}
  ],
  "edges": [
    {"from": "a", "to": "c", "role": "strong"},
    {"from": "b", "to": "d"},
    {"from": "c", "to": "d", "role": "strong"},
    {"from": "a", "to": "e"},
    {"from": "d", "to": "f", "role": "strong"}
  ]
}
```

### 3. Runbook — the maintenance window, by the minute

```json
{
  "version": 1,
  "kind": "gantt",
  "title": "Saturday's database upgrade",
  "axis": {"label": "Minutes after 02:00", "min": 0, "max": 90},
  "tasks": [
    {"id": "freeze", "text": "Announce read-only mode", "at": 0, "actor": "On-call"},
    {"id": "backup", "text": "Take and verify a backup", "start": 0, "end": 20, "actor": "DBA"},
    {"id": "upgrade", "text": "Upgrade the primary", "start": 20, "end": 50, "actor": "DBA", "role": "emphasis"},
    {"id": "replicas", "text": "Rebuild replicas", "start": 50, "end": 75, "actor": "DBA"},
    {"id": "smoke", "text": "Run smoke tests", "start": 50, "end": 65, "actor": "On-call"},
    {"id": "open", "text": "Lift read-only mode", "at": 70, "actor": "On-call"}
  ],
  "marks": [{"text": "rollback deadline", "at": 60}]
}
```

## Fields

| Field | Where | Required | Decision |
|---|---|---|---|
| `axis` | root | **yes** | The chart's `axis` object, reused: `label`, `unit`, `min`, `max`, `categories`. With `categories`, positions 1, 2, 3 … are named (`"Jan", "Feb"`), which covers month-level plans without dates. |
| `tasks` | root | **yes**, 1+ | `{id, text, start?, end?, at?, role?, actor?, note?}`. One row each, **in the order written** — that order is the reading order. |
| `start` / `end` | task | with each other | Numbers on the axis. Data, not coordinates, in the sense `across`/`up` already are. |
| `at` | task | instead of `start`/`end` | Makes the task a milestone. |
| `actor` | task | no | Who does it; drawn as the row label's lead, as in `flow`. |
| `groups` | root | no | Phases. The group object reused; members must be **consecutive** tasks. Drawn as a heading row and a light frame round its rows. |
| `edges` | root | no | Finish-to-start dependencies: drawn from the end of `from` to the start of `to`. Roles `flow` (default), `strong` (critical path), `weak`. |
| `marks` | root | no | `[{text, at}]` — a vertical line across all rows with its name at the top: *today*, a deadline, a freeze. |

## Refused, and why

| Refused | Why |
|---|---|
| A string date (`"2026-03-01"`) in `start`, `end`, `at` | No dates (see *Scope*). The message suggests a unit and `categories`. |
| `end <= start` | A task that ends before it starts. |
| A task with both `at` and `start`/`end`, or neither | It is a milestone or an interval. |
| Anything outside `axis.min`…`max` when both are given | It would be drawn off the plot. |
| An edge whose `to` starts before its `from` ends | Finish-to-start says it cannot. Either the plan or the edge is wrong; only the author knows which. |
| A group whose members are not consecutive | Its frame would enclose a task that is not in it. |
| More than **16** tasks | A two-hundred-line plan is a project tool's export. Split by phase. Also `FitError` on height when `height_binding`. |
| `progress` / percentage-complete fields | Not in v1: it is status, not plan, and goes stale the day it is drawn. Open question. |

## Roles

Tasks: `step` (default bar), `emphasis` (the task the diagram is about), `strong` is an
**edge** role — so for "critical", tasks use `emphasis` and edges `strong`. Using the
same word for both would need `strong` as a node role; flag for the owner. `note` for a
task drawn lighter (optional, external). Milestones take the theme's `decision` shape
(a diamond) without being a decision — the theme gets a `[gantt] milestone` shape key
rather than borrowing the role.

Bars are drawn with the theme's mark fills, so `emphasis` survives greyscale by pattern.

## Layout sketch

1. Left column: task labels (wrapped to a theme share of the width, with `actor` as
   lead). Its width is the widest label, capped; a longer label wraps.
2. Plot: the chart's horizontal axis machinery, unchanged — ticks, `categories`,
   label, unit.
3. One row per task; row height from its label. Group heading rows interleave.
4. Bars from `start` to `end`; milestones as a diamond at `at` with no text in the plot
   (the label is in the column).
5. Dependency edges: orthogonal, from bar end, down/up to the target row, into its start,
   with a short horizontal run before the head so a head never sits on the bar's corner.
6. Marks: dashed in the `weak` role, labelled above the first row.

## Acceptance tests to write

* Reference documents for the three use cases.
* A bar's left and right edges are at the axis positions of `start` and `end` (to the
  emitter's precision).
* A milestone is a diamond centred at `at`.
* Every dependency edge starts at its source bar's end and ends at its target's start.
* Each refusal at its pointer, including the date string.
* A 17-task document is refused with the split message.

## Open questions

* **Dates.** Keep "no dates" (proposed), or allow ISO dates in `gantt` only? Allowing them
  means a calendar, and the README's charting promise changes.
* `strong` on a task as well as an edge, so "critical" is one word in both places?

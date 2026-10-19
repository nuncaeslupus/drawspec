# Proposal: `gantt` + `events` and `iterations`, lanes on one axis

Status: **built**. Size **S**: two arrays on a task, a diamond the kind already draws,
and an arc made from the edge primitives.

## Why

The PMBOK continuum of life cycles compares four lanes over one time axis: predictive,
iterative, incremental and agile. The comparison between the lanes is the point.
Predictive has no loops and delivers once, at the end. Agile loops and delivers four
times. Each lane needs its deliveries where they fall and an arc for each cycle.

No kind said it (checked with 0.3.3, issue #131):

* `timeline` has an axis, but only one row.
* `matrix` has rows, but no continuous axis.
* `lanes` is a `flow`: it orders steps and does not place them on an axis.
* `gantt` has the shared axis, but one row is one task. Four deliveries for one lane
  became four milestone rows.

Evidence: one real figure, opos `tic/pmbok-enfoques-y-ciclo-de-vida`, filed by the owner
as issue #131. That is fewer than the two originals a new kind needs. This is two fields
on an existing kind, so one figure was taken as enough.

## New kind or extension

An extension of `gantt`. A new kind or a multi-row `timeline` was not chosen:

* `gantt` already has the one numeric axis and one row per piece of work, in the
  order written. A lane is a task that runs the whole axis.
* The `gantt` proposal kept rows out of `timeline` on purpose. A timeline is a
  sequence of events, not work over time.
* Two fields on a task are less vocabulary than a kind. Everything a plan already
  has still works on a lane: phases, roles, `done`, marks and dependencies.

## The shape

```json
{"id": "agile", "text": "Agile", "start": 0, "end": 12,
 "iterations": [{"start": 0, "end": 3}, {"start": 3, "end": 6},
                {"start": 6, "end": 9}, {"start": 9, "end": 12}],
 "events": [{"at": 3, "text": "1"}, {"at": 6, "text": "2"},
            {"at": 9, "text": "3"}, {"at": 12, "text": "4"}]}
```

* **Event.** An event is drawn as a milestone's diamond on the bar at `at`, with its
  `text` centred under the bar and kept on the canvas. Words that would touch are a
  fit error. The name is `events`. `marks` was not used, because a gantt's `marks`
  are lines across every row. `points` was not used either, because it is in the
  schema's rejection table: there it means coordinates, which are never input.
* **Iteration.**
  * An iteration is an orthogonal arc. It goes up from the bar near the iteration's
    `end`, back over it, and down with its head onto the bar near its `start`: the
    return a life-cycle figure draws.
  * The legs stand clear of an event's diamond, so iterations that touch end to start
    leave a gap round the delivery between them.
  * The fields are `start` and `end`, the task's own words. A dependency's
    `from` and `to` name tasks, so those words were not used.
* **Row.** A row with arcs or words grows by what they take. Its label stays beside
  the bar.
* **Text output.** An iteration is `▼───┐` (ASCII `v---+`) in a row over the bar, and
  an event is `◆` on the bar. The words go in the row under the bar. When they would
  touch, they are listed under the chart as `Task: words at 5`, so none is dropped.

## Refused

* Either field on a milestone, at `/tasks/<i>/events` or `/tasks/<i>/iterations`.
  Nothing falls inside a moment.
* An event or iteration end outside the task's `start` to `end`.
* An iteration whose `end` is not after its `start`.
* An iteration that starts before the one written before it ends. Iterations may touch.
* More than 8 of either on one task (the readability budget).
* An iteration too short on the axis for its arc's two legs: a fit error in SVG, and
  fewer than two cells in text.

## As built

As proposed. Reference: [`../reference/gantt-life-cycles.json`](../reference/gantt-life-cycles.json),
the continuum over twenty weeks.

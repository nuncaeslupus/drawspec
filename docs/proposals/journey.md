# Proposal: `journey` — what a person does, and how it feels, stage by stage

Status: **implemented** — see *As built* at the end for where it departs from this
text. Size **M** (columns of text plus a named-level curve; both exist in pieces —
`matrix`'s grid and `curve`'s through-every-point line).

## Why

A journey map's content is **one person's feeling across the stages of an experience**,
set against what they do at each stage. The feeling line is the reason to draw it: a
journey with no feeling line is a `flow` or a `timeline`, and the refusal should say so.
Service-design and public-administration course notes use it for exactly the questions
drawspec's corpus is full of: *what does a citizen go through to get X*.

The feeling is **ordinal and named**, not a score. That is the decision that keeps it out
of charting: there is no number to read off the curve, only which named level a stage
sits at — the same reasoning that gave `curve` and `quadrant` no ticks.

## Use cases

### 1. Design document — applying for a residents' parking permit online

```json
{
  "version": 1,
  "kind": "journey",
  "title": "A parking permit, from the resident's side",
  "feelings": ["frustrated", "uneasy", "neutral", "satisfied", "relieved"],
  "rows": [
    {"id": "does", "text": "Does"},
    {"id": "channel", "text": "Where"},
    {"id": "pain", "text": "Friction"}
  ],
  "stages": [
    {"text": "Finds out", "feeling": "neutral",
     "details": {"does": "Gets a warning ticket", "channel": "Windscreen"}},
    {"text": "Applies", "feeling": "uneasy",
     "details": {"does": "Fills in the form", "channel": "City website", "pain": "Asked for the car's registration twice"}},
    {"text": "Proves address", "feeling": "frustrated", "role": "emphasis",
     "details": {"does": "Uploads a utility bill", "channel": "City website", "pain": "Rejects phone photos over 2 MB"}},
    {"text": "Pays", "feeling": "neutral",
     "details": {"does": "Pays the annual fee", "channel": "Payment gateway"}},
    {"text": "Receives", "feeling": "relieved",
     "details": {"does": "Gets the digital permit", "channel": "Email"}}
  ]
}
```

### 2. Course notes — a new employee's first week

```json
{
  "version": 1,
  "kind": "journey",
  "title": "The first week, as the new starter lives it",
  "feelings": ["lost", "neutral", "welcome"],
  "rows": [
    {"id": "does", "text": "Does"},
    {"id": "needs", "text": "Needs"}
  ],
  "stages": [
    {"text": "Day 1", "feeling": "welcome", "details": {"does": "Meets the team", "needs": "A buddy"}},
    {"text": "Day 2", "feeling": "lost", "role": "emphasis", "details": {"does": "Waits for accounts", "needs": "Access on day one"}},
    {"text": "Days 3–4", "feeling": "neutral", "details": {"does": "Reads the handbook", "needs": "A first small task"}},
    {"text": "Day 5", "feeling": "welcome", "details": {"does": "Ships a first change", "needs": "Feedback on it"}}
  ]
}
```

### 3. Open-source project notes — reporting a bug

```json
{
  "version": 1,
  "kind": "journey",
  "title": "Reporting a bug to us",
  "feelings": ["ignored", "unsure", "heard"],
  "stages": [
    {"text": "Hits the bug", "feeling": "unsure"},
    {"text": "Searches issues", "feeling": "unsure"},
    {"text": "Files a report", "feeling": "heard"},
    {"text": "Waits 3 weeks", "feeling": "ignored", "role": "emphasis"},
    {"text": "Gets a fix", "feeling": "heard"}
  ],
  "caption": "The wait is the whole problem: triage within a week is the proposed fix."
}
```

`rows` is optional: with none, the map is stages and the feeling line only.

## Fields

| Field | Where | Required | Decision |
|---|---|---|---|
| `feelings` | root | **yes**, 2–5 | The named levels, **worst first**. Drawn as labelled guide lines, worst at the bottom. |
| `stages` | root | **yes**, 2–7 | `{text, feeling, role?, details?}`, left to right as written. |
| `feeling` | stage | **yes** | One of `feelings`. Required on every stage: a stage nobody can name a feeling for means the diagram is a `flow`. |
| `rows` | root | no | `{id, text}`: the labelled bands under the line, top to bottom. |
| `details` | stage | no | An object from row id to text. Only ids from `rows`. A missing key draws an empty cell. |
| `role` | stage | no | `emphasis` marks the stage the diagram is about (usually the trough): its column is framed and its point drawn larger. `step` default. |

`details` is the one place a drawspec document would use an object keyed by ids. The
alternative — a flat `cells` array like `matrix` with `stage` and `row` indexes — is more
typing and easier to misalign. Flagged for the owner.

## Refused, and why

| Refused | Why |
|---|---|
| A number for `feeling` | A feeling is a name, not a score; a numeric axis would invite reading 3.4 off a sketch. Message suggests naming the levels. |
| `feeling` not in `feelings` | At its pointer, naming the closest level. |
| More than one person (`personas`, two lines) | Two feeling lines cross and erase each other. One map per person. |
| More than **7** stages, **5** feelings, **4** rows | Split into two journeys (before and after a hand-off). |
| `details` key not in `rows` | Typo, almost always. |
| `edges` | Stages are already in order; an arrow between them adds nothing. |

## Roles

Stages: `step`, `emphasis`. The feeling line is drawn in the `strong` edge weight; guide
lines in `weak`; row bands as the `group` caption level for labels. Points are a fixed
marker; the `emphasis` stage's marker uses the emphasis treatment (non-colour channel:
size and fill).

## Layout sketch

1. Columns: one per stage, equal width; a left margin column for feeling and row labels
   sized to the widest.
2. Stage headings across the top.
3. Feeling band: height from the theme (`[journey] band`), divided into
   `len(feelings)` levels evenly; a guide line at each.
4. Points at each column's centre, at its level; the line passes **through every point**,
   using the `curve` spline (which already guarantees it).
5. Rows: under the band, one cell per stage per row, text wrapped to the column; row
   height is the tallest cell.
6. Labels of the feeling line are never on the line: the levels are named on the left,
   once.

## Acceptance tests to write

* Reference documents for the three use cases.
* Each point lies on its level's guide line and on the drawn curve.
* Two adjacent stages at the same level → a flat segment (no overshoot from the spline).
* Each refusal at its pointer.
* A journey with no `rows` renders headings + band only.

## As built

Built in `kinds/journey.py`, a layout family of its own. The three use cases are
`docs/reference/journey-parking-permit.json`, `journey-first-week.json` and
`journey-bug-report.json` (no rows, with a caption); `journey-outpatient.json` is
a full-budget map, 7 stages, with a flat run and two troughs. Where it departs
from the text above:

* **`details` is a list per stage, not an object keyed by row ids** (owner's
  decision). Each entry is `{"row": "<id>", "text": "..."}`, the same id
  reference `from`/`to`, `column` and `in` already use, so nothing in the format
  is keyed by an id. An undeclared row is refused with the closest id; a row
  named twice in one stage is refused (one cell per row); a detail in a journey
  with no `rows` says to declare them. An object where the list goes is refused
  as a type error.
* **A monotone cubic, not the `curve` spline.** Catmull-Rom passes through every
  point but overshoots: between two equal neighbours it bulges, which would break
  the "flat segment" acceptance test and draw the line past a level nobody named.
  The line is Fritsch–Carlson (Butland's slopes): zero slope where it turns or
  runs level, so it is flat between equal neighbours and stays between the heights
  of any two consecutive points.
* **No `[journey] band` height.** Levels are a fixed distance apart in units (more
  if a wrapped level name needs it), so a theme cannot change which documents fit.
  `[journey]` instead names the three lines' edge roles, like `[board]`: `line`
  (`strong`), `guide` (`aside`, light and dashed, rather than `weak`, whose head
  and weight belong to a relation) and `separator` (`link`, the thin solid rule
  above each row).
* **Level names are right-aligned** against their guides, the way tick labels
  sit; row names are bold and left-aligned, top-aligned with their cells, as a
  board's slice names are. Cells are centred in their column, top-aligned.
* **The emphasis frame** is the `emphasis` role's own rounded box from the top of
  the headings to the bottom of the last row (a plain rectangle in a theme whose
  `emphasis` is another shape). Every heading's rule is one weight: a heavier rule
  inside the frame said it twice.
* **Refused by name** besides the proposal's list: `score` and `value` on a stage
  (a feeling is a name), duplicate feelings and row ids, and one feeling or one
  stage. A stage with no `feeling` names `flow` and `timeline`. The caps live in
  the readability budget — 7 stages, 5 feelings, 4 rows — each with "split it into
  two journeys" (or "merge the levels") as the advice.

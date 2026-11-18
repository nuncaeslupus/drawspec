# Proposal: `rag`: a RAG status report (traffic-light marks, with words)

Status: **built** (see *As built* at the end). Arsenal task `t-875d4d3f` (issue #97). The evidence is section 11
of the round-2 corpus ([`../research/corpus-round2.md`](../research/corpus-round2.md),
R1–R6), read from search summaries only and every row marked **(check)**. Size **S**:
rows set one under another; the work is in the mark, the trend and lining the columns
up.

## Why

A council's programme board, an NHS trust's board assurance framework and a project's
fortnightly highlight report all print the same figure: a list of workstreams or risks,
each with a red, amber or green rating, often a direction of travel since last time, and
a sentence saying why (R1, R2, R4, R5). In most of them the colour is the only thing
that carries the rating, so a greyscale print, or a reader who cannot tell red from
green, loses the one thing the page is for.

drawspec cannot draw it. A `matrix` with a `scale` gives an ordered tone per cell but no
word or shape on the mark, a `board` sorts cards into columns rather than rating each,
and a `meter` is an amount, not a judgement. What the reader needs is the row's name,
its rating said **three ways at once** (a word, a shape, and, when the theme has one, a
colour), the direction of travel **in words**, and the note.

What it is not: a table of every field a project tracks. One rating per row; a page with
cost, time and scope rated separately (R1's second paper) is a table, or three of these.

## The field name: `rag`

`status` is taken: on `flow` and `tree` it marks a change as `added`, `changed` or
`removed`, and a second meaning for the same word in the same format is a trap. The
candidates were:

* **`rag`**: the corpus's own word. Every source calls it a *RAG rating* or *RAG status*
  (R1–R5), and its values are the three words the reader is taught. Chosen.
* `health`: a project-tool word for the same idea, but it says nothing about the three
  values, and on a risk register a red risk is not ill health.
* `rating`: collides with a risk's *score* (likelihood × impact), which R4 and R5 print
  beside the RAG, and a reader would expect a number.

The kind is named for its field: `"kind": "rag"`, rows each with a `"rag"`.

## Use cases

### 1. A programme highlight report (R1, R2)

```json
{
  "version": 1,
  "kind": "rag",
  "title": "Library refit: highlight report, period 7",
  "rows": [
    {"text": "Building works", "rag": "amber", "trend": "worse",
     "note": "Asbestos survey added two weeks; the contractor is re-sequencing the ground floor."},
    {"text": "Self-service kiosks", "rag": "green", "trend": "same", "note": "Installed and tested."},
    {"text": "Staff training", "rag": "red", "trend": "worse",
     "note": "No trainer booked. **Decision needed:** approve the supplier's quote by Friday."}
  ]
}
```

### 2. A risk register for a committee (R4, R5)

Twelve key risks, each its name, its owner as a caption (`"text": "Cyber attack\nOwner:
head of IT"`), its RAG and its direction of travel. A risk that rose is `worse`.

### 3. A delivery confidence summary (R6)

A department's five major projects, each rated with a one-line reason, the meanings
stated once in the `caption`.

## Fields

| Field | Where | Required | Decision |
|---|---|---|---|
| `rows` | root | **yes** | 1–15 rows, in the order written (the author's priority, or the register's). |
| `row.text` | row | **yes** | The workstream or risk. A second line after a newline is a caption under it: an owner, a reference. |
| `row.rag` | row | **yes** | `red`, `amber` or `green`. Three, as the corpus settled (R3 dropped five). |
| `row.trend` | row | no | `better`, `same` or `worse` since the last report. Not `up`/`down`: an arrow up means *improving* in R2 and *risk rising* in R5. The drawing writes the word beside the arrow. |
| `row.note` | row | no | Why: a sentence or two, wrapped. `**bold**` for a decision asked for. |

## The mark: a word, a shape, a colour

The theme, not the document, says how each rating is drawn (`[rag]`):

* **A word**, always: `Red`, `Amber`, `Green` by default; a house that says `On track`,
  `At risk`, `Off track` sets the three words once.
* **A shape**, always, and the three must differ: `circle` for green, `triangle` for
  amber, `square` for red by default (`diamond` is the fourth choice). Shape is what a
  greyscale print and a colour-blind reader keep.
* **A colour**, only when the theme declares one. The default theme is drawn in the
  page's ink, like every kind; the `accent` theme colours the three marks. Removing the
  colour removes nothing the reader needs.

The trend's arrow points up for `better`, across for `same`, down for `worse`, and its
word (`improving`, `no change`, `worsening`, the theme's) is written beside it.

## Refused, and why

| Refused | Why |
|---|---|
| A `rag` other than the three, such as `amber/green` or `blue` | Three ratings, as boards settle on (R3). A finished workstream is `green` with *Complete* in its note. |
| `colour`, `color` on a row | The rating is the word; the theme colours it. |
| `status` on a row | That word marks a change on `flow` and `tree`; a rating is `rag`. |
| `trend` as `up`, `down`, `improving`, … | `better`, `same`, `worse`: an arrow's direction means opposite things in different reports. |
| `score`, `likelihood`, `impact` | A score is a number on a risk matrix: a `matrix` with a `scale`. |
| More than 15 rows | Readability budget: the largest register found has 13 risks (R4). Split it by directorate. |
| `edges`, `columns` | Nothing here connects; ratings per dimension are a table. |

## Layout sketch

One row per entry, a table without a header, rules between rows:

* **Name** in a column at the left, wrapped to at most a third of the width, its caption
  under it at the label size.
* **Mark**: the shape, about the cap height of the body type, then its word, in one
  column as wide as the widest word.
* **Trend**, when any row has one: the arrow and its word, in one column.
* **Note**, when any row has one: the rest of the width, wrapped.

Every cell starts at the row's top, so the mark sits on the name's first line whatever
the note's length.

## As built

Built as proposed, as its own kind (`kinds/rag.py`) with a new theme table, `[rag]`.
What was settled while building, and why:

* **The theme table is flat**: `red`, `amber`, `green` (the words), `red_shape` … (the
  shapes) and `red_colour` … (empty in the default theme, set by `accent`), and
  `better`, `same`, `worse` (the trend words). The loader refuses three words or three
  shapes that repeat, and a trend word that repeats, since the word is what a reader
  without colour goes by.
* **A mark is filled and outlined in the page's ink**: in the default theme it is a
  solid shape; in `accent` the colour fills it and the ink outline keeps its edge on a
  pale colour such as amber.
* **The name and the rating's word are bold**, the note plain: the eye runs down the
  names and the ratings, and reads a note only for the row it stops at.
* **Without notes the name may take the room the notes would have**, and the report is
  centred, as every other kind is, instead of hanging at the left of the canvas.
* **The trend word is set at the label size** on the name's baseline, so it reads as a
  qualifier of the rating beside it, not as a second rating.
* **`owner`, `commentary`, `likelihood`, `impact`** were added to the refusals with
  advice (a caption, `note`, a `matrix`), as the fields a register's author reaches for.

References: `rag-refit` (use case 1, a highlight report with owners and notes),
`rag-register` (2, ten risks with their trends, no notes), `rag-confidence` (3, delivery
confidence in the `accent` theme, the meanings in the caption) and `rag-school` (a
school's priorities for its governors).

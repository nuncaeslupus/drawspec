# Proposal: `clock`: analogue clock faces for teaching time

Status: **built** (see *As built* at the end). Arsenal task `t-629fc7cd` (issue #98). The evidence is section 12
of the round-2 corpus ([`../research/corpus-round2.md`](../research/corpus-round2.md),
C1–C5), read from search summaries only and every row marked **(check)**. Size **S**:
each face is placed by arithmetic; the work is in the hands, the numerals and the words.

## Why

Every primary maths scheme teaches the analogue clock: o'clock and half past at five or
six, quarter past and quarter to and five-minute times at seven, the nearest minute,
Roman numerals and the 24-hour clock at eight (C1, C2). The figure is the same in each
lesson and on every worksheet: a round face, twelve numbers, sixty minute ticks, a short
hour hand and a long minute hand, often several faces in a row, the time written under
each or left blank for the pupil (C3, C4), and for elapsed time a start and an end (C5).

drawspec cannot draw one. A `meter` dial is a half-circle reading one amount; a `pie` is
shares of a whole; a `cycle` is steps round a loop. Nothing places two hands by a time.

What it is not: a timetable or a schedule. Times are readings of a clock, `HH:MM`, never
dates, and there is no seconds hand: no lesson in the corpus asks a pupil to read one.

## Use cases

### 1. Reading quarter past and quarter to (C1)

```json
{
  "version": 1,
  "kind": "clock",
  "title": "Quarter past and quarter to",
  "clocks": [
    {"time": "3:00"}, {"time": "3:15"}, {"time": "3:30"}, {"time": "3:45"}
  ]
}
```

Four faces in a row, each with its time in words under it: *three o'clock*, *quarter past
three*, *half past three*, *quarter to four*. The hour hand moves on between them, which
is the point the lesson makes (C1's common error).

### 2. A worksheet: write the time, draw the hands (C4)

Eight faces, `"readout": "none"` so the answers are not printed; four with a time to
read, four with no `time` and a prompt as their `text` (`Draw twenty to six`), so they
are drawn without hands.

### 3. Roman numerals to the nearest minute (C2, C3)

`"numerals": "roman"`, three faces at `9:07`, `14:52` and `11:38`, `"readout": "both"`:
*seven minutes past nine* and `9:07`.

### 4. How long did it take? (C5)

Two faces: the start, and the end with `"since": "2:35"`, which shades the minutes
passed round the face from the start's minute to the end's and writes *40 minutes
later* under it.

## Fields

| Field | Where | Required | Decision |
|---|---|---|---|
| `clocks` | root | **yes** | 1–12 faces, in reading order, up to four to a row. |
| `numerals` | root | no | `arabic` (default), `roman` (I–XII), `quarters` (12, 3, 6 and 9 only) or `none`. One for the sheet, as each corpus sheet uses one. |
| `readout` | root | no | What is written under each face: `words` (default), `digits`, `both`, or `none` for a worksheet. |
| `clock.time` | clock | no | `H:MM` or `HH:MM`, 0:00 to 23:59. Without it the face has no hands: one to draw on. |
| `clock.text` | clock | no | A name or a prompt under the face: *Home time*, *Draw half past seven*. |
| `clock.since` | clock | no | An earlier time: the face shades what has passed since it, and the readout says how long. Up to 12 hours before. |

## Refused, and why

| Refused | Why |
|---|---|
| A time with seconds (`9:15:30`), `seconds` | No teaching face in the corpus has a seconds hand to read; seconds are a fact (60 in a minute), not a hand. |
| A time that is not `H:MM` (`9.30`, `9:5`, `24:00`, `3:15 pm`) | One spelling; `pm` is the 24-hour clock: `15:15`. |
| `date`, a time with a date | A clock reads a time of day; a day is a `timeline`'s. |
| `since` without `time`, equal to it, or 12 hours or more before | A sweep needs both ends, and past 12 hours the hour hand has gone round. |
| `hands`, `angle`, `hour`, `minute` | The hands are placed by the `time`. |
| `numerals` on a clock | One face style per sheet. |
| More than 12 faces | Readability budget: a worksheet holds a dozen (C4). |
| `edges` | Two faces are related by `since`, not by a line. |

## Layout sketch

* Faces in rows of up to four, as many to a row as keeps the rows even; each face a
  circle, sixty ticks (every fifth longer), numerals inside the ticks.
* The hour hand short and broad, the minute hand long and narrow, both filled, so they
  are told apart by shape; a dot on the hub.
* `since`: the minutes passed are a faint sector under the minute hand when they are an
  hour or less; over an hour, the hour hand's sweep is shaded instead, nearer the hub.
* Under the face: the readout, then the `text`.

## As built

Built as proposed, as its own kind (`kinds/clock.py`), with no theme keys. What was
settled while building, and why:

* **The minute hand stops just inside the numerals.** Drawn to the ticks, as on a real
  clock, it lay across the number it pointed at — the 3 at quarter past — which is the
  number the pupil has to read. It now ends a little short of the ring of numerals, and
  the hour hand is about three fifths of it, broader; the face with no numerals keeps
  the same proportions from the tick ring.
* **The words are British classroom English** (*twenty-five to four*, *seven minutes past
  nine*, *quarter to one*), as the curriculum sources use; a five-minute time drops
  *minutes*, any other keeps it, and twelve is *twelve* at noon and midnight.
* **Digits are written as the author wrote them**, so a `15:40` stays on the 24-hour
  clock and a `3:40` on the 12-hour one; the face is the same either way.
* **`since` says how long *after* the earlier time** (*40 minutes after 2:35*) under the
  readout, and nothing when the readout is `none`: on a worksheet that is the question.
  The shaded sweep follows the minute hand up to an hour, the hour hand past it, and a
  sweep may run over midnight (`22:40` to `1:10`).
* **The readout's first line is bold**, the `text` plain under it: the time is what the
  face says, the text what it is for.
* **Roman four is IV**, as the curriculum teaches it, not the IIII of many real clocks.
* **The refusals gained `label`** (it is the `text`), and the `am`/`pm` advice names the
  24-hour time.

References: `clock-quarters` (use case 1), `clock-worksheet` (2, eight faces, answers
hidden, four to draw on), `clock-roman` (3) and `clock-journey` (4, two `since` sweeps:
one of the minute hand, one of the hour hand, `quarters` numerals).

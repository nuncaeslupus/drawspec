# `railroad` — a grammar's rules as syntax diagrams

A syntax (railroad) diagram draws what may follow what in a language: each rule a track
from an entry to an exit, through **terminals** — literal text, in rounded boxes — and
**non-terminals** — other rules, in square boxes — with **choices** stacked and rejoining,
**bypasses** over what may be left out and **loops** back under what may repeat. A reader
follows the track with a finger; every path from entry to exit is a valid input.

This came as an owner request — new kinds borrowed from similar tools — but it answers a
real gap: nothing drawspec draws derives branches, bypasses and loops from an expression.
A `flow` routes arbitrary arrows between boxes, and drawing a grammar with one means
placing every junction by hand, which is exactly the coordinate-writing drawspec refuses.

## The originals

Found by web search and checked against the design below (the figures themselves are
images; the search results confirmed the pages and what is on them).

| # | Original | What it shows | What it taught |
|---|---|---|---|
| R1 | [JSON.org, *Introducing JSON*](https://www.json.org/json-en) | `value`, `object`, `array`, `string`, `number` and `whitespace` as railroad figures beside the grammar text | Rounded boxes are the characters, square boxes a placeholder for another rule ([a walk-through](https://dev.to/tanhauhau/json-parser-with-javascript-578c)); `number` is optional minus, a choice, then two optional groups — every construct in one figure; `string`'s escapes each carry a *comment* (*quotation mark*, *reverse solidus*) beside them; `object`'s members loop back through `,`. Redrawn as `railroad-json-number`, `railroad-json-string`, `railroad-json-value`. |
| R2 | [SQLite's syntax diagrams](https://sqlite.org/syntaxdiagrams.html), and the SELECT page ([a copy](https://docs.w3cub.com/sqlite/lang_select)) | Every statement as a figure: `select-stmt`, `select-core`, `result-column`, `join-clause`, `ordering-term` … | A long rule **wraps** onto several lines with a return track; a rule too big for one figure is **factored** into named sub-rules (the page offers a *factored* select-stmt beside the all-in-one); keywords are upper-case terminals. Redrawn (a subset) as `railroad-sql-select`. |
| R3 | [Syntax diagram (Wikipedia)](https://en.wikipedia.org/wiki/Syntax_diagram) | The notation's history: Wirth's *Pascal User Manual* | *"terminals have been represented by round boxes and nonterminals by rectangular boxes but there is no official standard"* — so the shape convention is drawspec's to keep, and keeping it is what makes the two read apart in greyscale. |
| R4 | [A PostgreSQL thread on railroad diagrams for its docs](https://www.postgresql.org/message-id/13866.1279400658%40sss.pgh.pa.us) | Tom Lane: they look great for simple cases, but SELECT would span pages | Why a budget, and why the refusal for a rule that will not fit is *factor it into rules*, not *shrink it*. |

Tools that draw them, read for their vocabulary:
[tabatkins' railroad-diagrams](https://pypi.org/project/railroad-diagrams/3.0.0)
(`Sequence`, `Choice(index, …)`, `Optional`, `OneOrMore(child, repeat)`,
`ZeroOrMore = Optional(OneOrMore)`, `Comment`),
[PlantUML's EBNF diagrams](https://plantuml.com/de/ebnf) and
[regex diagrams](https://plantuml.com/regex),
[Mermaid's railroad syntax](https://mermaid.js.org/syntax/railroad.html), SQLite's own
generator ([Pikchr, as one reader traced it](https://jordaneldredge.com/notes/sqlite-railroad/)),
and the layout literature
([confluent orthogonal drawings of syntax diagrams](https://arxiv.org/pdf/1509.00818)).

## The design

**No coordinates: an expression tree per rule.** A document is `rules`, each a `name`
and an `expr`, and an item is an object that says exactly one thing it is:

```json
{"version": 1, "kind": "railroad", "external": ["item"],
 "rules": [{"name": "list", "expr": {"seq": [
   {"terminal": "["},
   {"repeat": {"rule": "item"}, "separator": {"terminal": ","}, "min": 0},
   {"terminal": "]"}]}}]}
```

| Item | Drawn as |
|---|---|
| `{"terminal": "SELECT"}` | literal text, monospace, in a rounded box |
| `{"rule": "expr"}` | another rule, in a square box — defined in `rules`, or listed in `external` |
| `{"special": "any digit 1-9"}` | a set described in words, in a dashed box (EBNF's special sequence; JSON.org's *any code point except …*) |
| `{"comment": "backspace"}` | words on the line, the track breaking for them |
| `{"seq": [a, b, …]}` | left to right |
| `{"choice": [a, b, …]}` | stacked, the first on the main line — put the usual one first |
| `{"optional": a}` | on the line, a bypass over it |
| `{"repeat": a, "min": 1, "separator": s}` | on the line, a loop back under it through `s`; `min: 0` adds the bypass |

Why this shape, for a model writing it: one key per item says what it is, so nothing is
positional; `min` is **required** on a repeat, because "repeat" means *zero or more* to
an EBNF reader and *one or more* to a regex reader, and a silent default would be wrong
for half of them. **No compact string form** (`"'SELECT' expr*"`): it would need its own
quoting rules for terminals that are themselves quotes and stars (`"`, `*`, `\`), which is
where a model writing it goes wrong; the object form needs only JSON's.

**Everything else is derived.** One turn radius for every curve, so a branch leaves and
rejoins the line tangentially and no two turns collide; each construct reserves its own
room; a rule's top-level `seq` that is wider than the canvas **wraps** between items onto
further lines, a return track (with an arrowhead) running back under each line, as R2
does. Rules are drawn one under another, each named above its track.

**Text output: yes.** A track sits on a grid: a box is three rows with the track through
its middle, a turn is a corner, and the same layout code places everything on cells. A
rule too wide wraps the same way; an item too wide alone is refused with the width it
needs.

## What it refuses

Each with its JSON pointer, as a test:

- an item that says nothing, or two things (`terminal` and `rule`);
- a `repeat` without `min`, a `min` other than 0 or 1 (a count is never drawn — say it in a
  `comment` separator, or write the item out), `separator`/`min` off a repeat, a separator
  that is not one box (it is read backwards along the loop);
- a `rule` box naming no defined or external rule (with a *did you mean*), a rule name
  defined twice, an `external` name that is defined here or never used;
- a `seq` or `choice` of one, `optional` round something already optional, empty words,
  and words over two lines (a box on a track is one line);
- fields a model reaches for: `text` (say which box), `max`/`times`/`count`, `default`/
  `index` (the first branch is the main line), `skip`/`empty` (use `optional`), `role`, `id`,
  coordinates.

## The limits

12 rules a document, 40 boxes a rule (SQLite's busiest figures), 10 alternatives a choice
(JSON.org's escapes are nine), 8 levels of nesting — past these, the refusal says to
factor the part into a rule of its own, as R2 does and R4 recommends. An item wider than
the canvas on a line of its own is a `FitError` at its pointer, with the same advice.

## Status

**Built.** `src/drawspec/kinds/railroad.py` (SVG and text), schema and validation in
`src/drawspec/schema.py`, references `docs/reference/railroad-*.json` (JSON number,
string and value; a SQLite SELECT subset; a command line), tests in
`tests/test_kinds_railroad.py`.

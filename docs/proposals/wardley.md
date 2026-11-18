# `wardley` — a value chain placed against evolution

A Wardley map puts a user's need at the top and everything that need rests on below it,
each part placed across the page by how evolved it is: from **genesis** (new, uncertain,
made once) through **custom-built** and **product (+rental)** to **commodity (+utility)**
(standard, metered, invisible). Lines join a part to what it needs. On top of that plane
sit the moves: an arrow to where a part is heading, a bar where something resists that
move, and numbered notes. It is the picture a team argues over when it decides what to
build, what to buy and what to rent.

This kind was deferred in the 2026-10 survey ([`README.md`](README.md#deferred-not-proposed)):
*one niche strategy artefact; it needs routed edges on a numeric plane, which no chart kind
has; no original yet.* The owner has since asked for it, with originals found by search.

## The originals

Each was found by web search on 2026-10-25; the figures were seen in the results' pages
and descriptions, not redrawn from memory.

| # | Original | What it shows | What the design takes from it |
|---|---|---|---|
| WM1 | Simon Wardley, *A good enough map* (his book's teaching chapter, on Medium: <https://swardley.medium.com/a-good-enough-map-eaed8a525bf4>), and the same tea shop in *Wardley Mapping in 5 Minutes* (<https://courses.learnwardleymapping.com/courses/364585/lectures/8591556>) | A tea shop: *Business* and *Public* at the top needing a *Cup of tea*, which needs *Cup*, *Tea* and *Hot water*; hot water needs *Water* and a *Kettle*; the kettle needs *Power*. Ordered by visibility to the customer; placed by evolution | Two anchors over one need; depth is the dependency chain, read down; four named stages across; straight lines. Redrawn as [`wardley-tea-shop.json`](../reference/wardley-tea-shop.json) |
| WM2 | *Wardley Mapping 101* (<https://www.wardleymaps.com/guides/wardley-mapping-101>) | A user need to store and share photos online, the value chain beneath it, and *Photo storage* shown moving from product to commodity | The evolution arrow: the same part, further right, on the same row. Redrawn as [`wardley-photo-service.json`](../reference/wardley-photo-service.json) |
| WM3 | Local Digital (GOV.UK), *Decide to build, buy or share* (<https://localdigital.gov.uk/resources/decide-to-build-buy-or-share>) | A council's exercise: user needs at the top, the capabilities under them, each placed by evolution to decide which to build, buy or share; "keep it simple" | Notes beside parts (*build*, *share*), several anchors (a resident, a team), shared national services as commodities. Redrawn as [`wardley-council-service.json`](../reference/wardley-council-service.json) |
| WM4 | OnlineWardleyMaps, *inertia* (<https://docs.onlinewardleymaps.com/docs/map-elements/inertia>), and IT Revolution's *How to Wardley map* (<https://itrevolution.com/how-to-wardley-map>) | Inertia drawn as a block to the right of a component, the way it would move; the café whose owner sees no gain in a better kettle | `inertia` as a heavy bar on the right; the tea shop's note |
| WM5 | Mermaid's `wardley-beta` syntax (<https://mermaid.js.org/syntax/wardley.html>) and OnlineWardleyMaps' component syntax (<https://docs.onlinewardleymaps.com/docs/map-elements/component>) | The two text formats in use: `component Name [visibility, evolution]`, both numbers from 0 to 1, plus a `label [x, y]` offset in pixels | What *not* to copy — see below |

## Positions without coordinates

A Wardley map **is** a plane: a part's place on it is the whole message. So the question
this kind has to answer is the one drawspec exists to refuse — the existing formats (WM5)
ask the author for two numbers per component and a pixel offset per label, which is
exactly the *x*, *y* and nudge that the brief ([`../brief.md`](../brief.md)) found models
getting wrong, and that the README's first line promises never to ask for.

The answer is that **neither axis is a measurement**; each is a judgement with a name or
a structure, and the name or the structure is what is written:

- **Across: evolution is a named stage, not a number.** Wardley's own axis is four named
  stages, and his maps place a part by asking which stage's *characteristics* it has
  (WM1). A number between 0 and 1 adds a precision nobody has: no one can say whether a
  kettle is at 0.62 or 0.65, but anyone can say it is a product, late in that stage. So
  `evolution` is one of twelve names — a stage, optionally `early` or `late` in it
  (`late product`) — and `evolves` uses the same twelve. A schema enum, so a misspelling is
  refused before anything is drawn, and a number is refused with the twelve names.
  Considered and rejected: a number (the coordinate in disguise, and the tools' format);
  `{stage, at}` with a fraction inside the stage (a coordinate again, one level down); the
  stage alone (too coarse — WM1 has *Tea* plainly further right than *Cup of tea* inside
  one stage). Thirds are the finest grain a reader can see on a 640-wide map anyway: a
  third of a stage is about 50 units.
- **Down: visibility is the value chain, derived.** In every original the vertical order
  *is* the dependency chain: a part sits below what needs it (WM1–WM3). So nothing is
  written: the anchors are row 0, and each component is one row below the lowest thing
  that needs it — the longest path from an anchor, so every line runs downward. The one
  override is `depth`, a row number, and it may only **sink** a part (a power supply drawn
  at the bottom of the map though only two steps from the user); a `depth` above what needs
  it is refused. A row is a rank, like a gantt row, not a position — drawspec still decides
  where the row is.
- **Collisions are drawspec's.** Two parts on one row and one place share it side by side,
  in the order written; a dot that a line would pass through slides along its place; a
  name is placed in the nearest of 38 spots round its dot that is clear of every dot, line,
  bar, arrow and other name, by a small backtracking search; a crowded map is drawn taller
  (rows 5, 6.5, then 8 lines apart); and a name with nowhere to go is a `FitError` that says
  what to move. There is no label offset to write.

The quadrant kind already takes `across`/`up` as numbers from 0 to 1. That is right for a
quadrant, whose axes are an author's two free judgements; it is wrong here, because one of
a Wardley map's axes is a structure already in the document (the `needs`), and the other
has names in its own literature.

## The design

```json
{
  "version": 1,
  "kind": "wardley",
  "anchors": [{"id": "customer", "text": "Customer", "needs": ["tea"]}],
  "components": [
    {"id": "tea", "text": "Cup of tea", "evolution": "product", "needs": ["water"]},
    {"id": "water", "text": "Hot water", "evolution": "commodity", "needs": ["kettle"]},
    {"id": "kettle", "text": "Kettle", "evolution": "custom", "evolves": "product", "inertia": true}
  ],
  "notes": [{"text": "The owner sees no gain in a new kettle.", "on": ["kettle"]}]
}
```

- `anchors` (1–3): `id`, `text`, `needs`. Drawn bold across the top, each over the middle of
  what it needs, pushed apart when their names would meet.
- `components` (1–24): `id`, `text` (one line), `evolution`, and optionally `needs`,
  `depth`, `evolves`, `inertia`. A dot, its name beside it.
- Dependencies: straight lines dot to dot (Wardley's convention), drawn in the `link` role.
- `evolves`: a dashed arrow (`weak`) to a dashed circle (`note`) further right on the same
  row; it must be further right.
- `inertia`: a heavy bar on the component's right, between it and where it would go.
- `notes` (≤ 6): `{text, on}` — a numbered ring beside each thing it is `on`, and the words
  under the map, numbered. A note is about parts, so it is anchored to them by id, never
  placed.
- The axes: the value chain up the left (*Visible* at the top, *Invisible* at the bottom),
  evolution along the bottom with its four stage names under dashed stage dividers. The
  words are a `[wardley]` theme section, so a house or a translation sets them once.

## Refusals

At the pointer, each: a number (or any unknown name) for `evolution` or `evolves`; an
`evolves` that is not further right; a component that nothing needs (it has no place in the
value chain); a `needs` naming an anchor, itself, nothing, or the same thing twice; a loop;
a `depth` above what needs it; a chain deeper than 8 rows; a duplicate id; a name with a
newline; a note `on` an unknown id; `visibility`, `maturity`, `position`, `at`, `stage`,
`label`, `role`, `edges` with the reason; and past the budget (24 components, 3 anchors,
6 notes). At fit: too many parts on one place and row, a line that cannot be slid clear of
a dot, a name or a note's number with nowhere to go, a stage name wider than its quarter.

**No text form.** A map's message is position on a plane; on an 80-column grid twelve
places across leave six characters each, and the names would not fit beside their dots.
`--format text` refuses it as it does the other plane kinds.

## Not built

Pipelines (a component spread over a range of evolution), sub-maps, market and ecosystem
markers, build/buy/outsource styling, and accelerator/deaccelerator arrows. Each is in
OnlineWardleyMaps; none is in the originals above, so none is proposed until one asks.

## Status

**Built.** `src/drawspec/kinds/wardley.py`, schema and validation in
`src/drawspec/schema.py`, the `[wardley]` theme section, references
`docs/reference/wardley-*.json`, tests in `tests/test_kinds_wardley.py`.

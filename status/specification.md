# Specification: drawspec — declarative diagram spec to themeable SVG

**Date**: 2026-08-11
**Ticket / PR**: [#1](https://github.com/nuncaeslupus/drawspec/pull/1)
**Author**: drawspec

---

## 1. Problem statement

Language models produce diagrams by emitting SVG with absolute `x`/`y`
coordinates, and they fail at the same things every time. In the 87-diagram
evidence corpus (`corpus/`), **63 drew a complaint from a human reviewer, and
every complaint was about placement, not content**: arrows with a head but no
shaft, text escaping its box, lines stopping short of the shape they point at,
a different font size in every element. These failures cannot be reviewed away
— a cheap mechanical check over finished SVG catches 17 of the 63 and misses
46. Nor can they be prompted away, because the author cannot see the result.
They have to be made *unrepresentable*: the author describes what the diagram
means, and every decision that requires seeing the output is taken by the tool.
drawspec is that tool — a Python library and CLI that takes a declarative
document and emits SVG clean enough to paste inline into a Markdown page,
inheriting the document's colour and surviving greyscale printing.

**Success criteria (measurable)** — each seeds a task Gate in the plan:

- [ ] `unrepresentable_failure_families == 11` — for each of the 11 categorized
      failure families in `docs/brief.md`, a test demonstrates that no valid
      input document can produce it. Judged per family: either the input schema
      has no field that expresses it, or a layout invariant excludes it.
- [ ] `inline_safety_violations == 0` over every generated fixture — no
      `<style>` element, no id that is not prefixed with the document's unique
      namespace, no embedded or referenced external font, no `fill`/`stroke`
      literal outside the values the active theme declares. Mechanically
      checked by the emitter's own validator.
- [ ] `greyscale_ambiguous_role_pairs == 0` — for a theme to load, every pair of
      semantic roles must differ in at least one non-colour channel (shape,
      dash pattern, stroke weight, fill pattern) **or** by a luminance delta
      `>= 0.25` in relative luminance. Checked once per theme at load time.
- [ ] `text_overflow_count == 0` over the regression fixture set — no text run's
      measured advance width exceeds its container's usable width, and no text
      block's measured height exceeds its container's usable height.
- [ ] `system_dependencies == 0` — `pip install drawspec` followed by
      `drawspec render` succeeds in a container with no non-Python binaries
      installed beyond CPython itself.
- [ ] `text_measurement_error_ratio <= 0.02` — for a font with published
      metrics, drawspec's measured advance width for a reference string set is
      within 2% of the value computed from the font's own `hmtx`/`kern` tables
      by an independent reader.
- [ ] `nondeterministic_reruns == 0` — rendering the same document twice with
      the same theme produces byte-identical SVG.
- [ ] `line_coverage >= 0.85`.
- [ ] A document whose content cannot fit at the theme's minimum legible size
      **fails loudly** rather than shrinking type or overflowing. Judged by a
      test asserting a specific exception, not by a number.

## 2. Systems & Impact

drawspec is a greenfield library, so the table maps its own subsystems rather
than existing services. "Needs changes" reads as "must be built".

| System | Type | Role | Needs changes? | Impact | Severity |
|--------|------|------|----------------|--------|----------|
| `drawspec.schema` | Primary | The input document model and its JSON Schema. Defines what an author *can* say — and, more importantly, what they cannot. | Yes | Every other subsystem reads it. Getting the omissions wrong reintroduces the failure classes. | High |
| `drawspec.text` | Primary | Text measurement: advance widths, line breaking, block height, from a font file. Must work for a font it has never seen. | Yes | The prerequisite for box sizing, pyramid fitting and chart labels. If it is wrong, everything downstream is wrong. | High |
| `drawspec.layout` | Primary | Coordinate assignment for graph-shaped diagrams, behind a swappable engine interface. | Yes | Determines which failure families are excluded structurally vs merely checked. | High |
| `drawspec.routing` | Primary | Orthogonal edge routing, border anchoring, minimum shaft length, label placement. | Yes | Owns 4 of the 11 failure families on its own. No candidate engine does this to the required standard. | High |
| `drawspec.templates` | Primary | Parametric non-graph shapes: pyramid, concentric circles, stack, timeline, column comparison. | Yes | 5 of the 9 diagram types. No graph theory involved; pure geometry plus text fitting. | Medium |
| `drawspec.charts` | Primary | Axis charts: scales, ticks, labels, series. A separate family sharing only theme and text measurement. | Yes | 1 of the 9 types, and the one the corpus did worst. | Medium |
| `drawspec.theme` | Primary | Canvas width, font stack, type scale, padding, stroke scale, role→appearance mapping, greyscale validation. | Yes | The proof that no consumer style is baked in. | High |
| `drawspec.emit` | Primary | SVG serialisation and the inline-safety invariants (id namespacing, `currentColor`, `<title>`/`<desc>`). | Yes | Owns acceptance test 1 outright. | High |
| `drawspec.cli` | Primary | `drawspec render doc.json -o out.svg`, plus `validate` and `theme check`. | Yes | The interface a build pipeline calls. | Low |
| Consuming project | Dependent | Calls the library or CLI, receives SVG files, saves and embeds them. | No | Gains a build step; loses hand-written SVG. Must supply a theme or accept the default. | Low |
| Fonts on the host | Shared resource | Metric source for measurement. | No (validate) | If the named font is absent, measurement must fall back explicitly and say so, never silently. | Medium |

**Impact dimensions.**

- **Data**: none — the tool is a pure function from document to SVG. No storage.
- **API contract**: the input schema is the contract, and it is the thing most
  expensive to change later, because documents written against it live in the
  consumer's repository. Versioned from v1 with an explicit `version` field.
  **High.**
- **Performance**: irrelevant at corpus scale (median 4 nodes, max 17). A
  render should be milliseconds. Not a design constraint. **Low.**
- **User-facing**: the diagrams are the product for the consumer's readers.
  Regressions are visible. **High.**
- **Operational**: adding a system binary dependency would push an install
  burden onto every consumer and every CI job. **Medium**, and it is the reason
  Option C below is not recommended.
- **Risk of inaction**: hand-written SVG keeps producing a ~72% complaint rate
  (63 of 87), with review cost borne by a human on every diagram, forever.

## 3. Options

### The candidate survey

All consulted **2026-08-11**. The question is not "does it draw well" but the
brief's two acceptance tests: (1) does it emit SVG safe to paste inline into
Markdown — no global `<style>`, no colliding ids, no embedded fonts, colour
inherited, greyscale-safe; and (2) can it fix the three worst corpus diagrams.

| Candidate | Licence | How it is driven | What it emits | Test 1 | Notes |
|---|---|---|---|---|---|
| [Graphviz](https://graphviz.org/) | EPL-1.0 | `dot` C binary; `pip install graphviz` gives **bindings only** | SVG, **or coordinates only** via `-Tplain` / `-Tjson` | Fails as SVG; **passes as a coordinate source** | Its `-Tplain` output is positions and edge control points with no styling. Orthogonal routing (`splines=ortho`) exists but is weak and has no port/label-avoidance model. Needs a system binary. |
| [ELK](https://eclipse.dev/elk/) | EPL-2.0 | Java library; [elkjs](https://github.com/kieler/elkjs) is a GWT transpile to JS | **Nothing but coordinates** — ELK does not render, by design | N/A — nothing to fail | The best-designed layout kernel of the set, with real port anchoring. No Python binding; would mean a JVM or a Node process. [elk-rs](https://github.com/openedges/elk-rs) is an early Rust port. |
| [grandalf](https://github.com/bdcht/grandalf) | **GPLv2 *or* EPL-1.0** (dual) | Pure Python, `pip install grandalf` | **Coordinates only** — "it is up to you to actually draw" | N/A — nothing to fail | Sugiyama hierarchical layout in ~600 lines plus a force-directed layout. Version 0.8, lightly maintained. The EPL-1.0 arm of the dual licence is compatible with shipping MIT code around it. |
| [D2](https://d2lang.com/) | MPL-2.0 | Go binary, `d2 in.d2 out.svg` | SVG / PNG / PDF only | **Fails** | Emits a styled standalone document with its own fonts and palette. No coordinate-only output. Adds a Go binary dependency. |
| [Mermaid](https://mermaid.js.org/) | MIT | JS library; CLI needs a headless browser | SVG with embedded `<style>` | **Fails** | Global CSS classes collide when two diagrams share a page — precisely the disqualifier in the brief. Needs Node plus Chromium. |
| [PlantUML](https://plantuml.com/) | GPL | Java jar | SVG with baked colours | **Fails** | GPL plus a JVM. Styling is theme-file driven but the output is not inheritance-friendly. |
| [TikZ/PGF](https://ctan.org/pkg/pgf) | LGPL / GPL | LaTeX toolchain | PDF, SVG via converters | **Fails** | A full TeX installation to render a 4-box diagram. |
| [Kroki](https://kroki.io/) | MIT (service) | HTTP service wrapping the above | Whatever the wrapped tool emits | **Inherits the failure** | Adds a network dependency and inherits each backend's output problems. |
| [yFiles](https://www.yworks.com/) | Proprietary, commercial | Library licence per developer/project | Its own rendering | Not evaluable | The quality bar the brief names, and commercially licensed. Out of scope. |

**What the survey settles.**

1. **No candidate passes acceptance test 1.** Every tool that renders, renders
   to its own taste: global `<style>`, its own palette, its own ids, sometimes
   its own fonts. Post-processing another tool's SVG into inline-safe SVG is a
   permanent tax paid on every release of that tool. **So drawspec owns the
   renderer regardless of which option is chosen.** This is not a decision; it
   is a finding.
2. **The useful candidates are coordinate oracles, not renderers.** Graphviz
   (`-Tplain`), ELK and grandalf all hand back positions and let the caller
   draw. That is exactly the seam drawspec needs, and it makes the layout
   engine a swappable component rather than an architectural commitment.
3. **The dependency question the brief left open has an answer.** `pip install
   graphviz` installs bindings only; the `dot` executable is a separate system
   install. For a library whose whole point is to be called from another Python
   project's build, that pushes an out-of-band binary install onto every
   consumer and every CI job. ELK is worse: a JVM or a Node process.
4. **The corpus is small enough that this matters more than engine power.**
   Median 4 boxes, maximum 17. Graphviz's and ELK's real value is on graphs two
   orders of magnitude larger. At this scale a pure-Python layered layout is
   adequate, and adequacy with no system dependency beats excellence with one.

### Option A: Adopt an existing tool with a post-processing template (Conservative)

- **Description**: Pick D2 or Graphviz, write the declarative format as a thin
  transpiler to its input language, and post-process the emitted SVG into
  inline-safe form — strip `<style>`, rewrite ids, replace colours with
  `currentColor`, drop font declarations.
- **Scope**: A transpiler, an SVG rewriter, a theme mapped onto the upstream
  tool's styling options. No layout, routing, templates or measurement of our
  own.
- **Effort**: Small to start, Medium and rising to maintain.
- **Tradeoffs**: Fastest to a first diagram, and the brief explicitly counts
  this as a success if it works. But post-processing is structurally fragile —
  it is pattern-matching another project's output, and it breaks on their
  releases. Worse, it does not deliver the core promise: text still is not
  measured by us, so box sizing stays the upstream tool's decision, and the
  "text does not fit" family is only *usually* fixed rather than
  *unrepresentable*. Pyramids, concentric circles and axis charts are not
  expressible at all — 3 of 9 types unserved. And it inherits a system binary.
- **Compatibility**: Consumers install a Go or C binary.

### Option B: Own the renderer, pluggable pure-Python layout (Recommended)

- **Description**: drawspec owns the input schema, text measurement, theme,
  routing, templates, charts and SVG emission. Graph layout sits behind a
  narrow `LayoutEngine` protocol — nodes with measured sizes in, coordinates
  out — with a pure-Python implementation as the default. Additional engines
  (Graphviz via `-Tplain`, ELK via a subprocess) become optional extras for
  anyone who has them and wants them on larger graphs.
- **Scope**: All of `src/drawspec/`. The engine boundary is one small protocol,
  making the choice of engine reversible.
- **Effort**: Large — but concentrated where the brief says the real work is
  (style layer, measurement, non-graph shapes), not in reimplementing layout
  research.
- **Tradeoffs**: Most work up front. In exchange: no system dependency, so
  `pip install drawspec` is the whole install story; total control of the SVG,
  so acceptance test 1 is satisfied by construction rather than by rewriting;
  and all three rendering families served by one theme and one measurement
  core. The risk is layout quality — mitigated by the graph sizes actually in
  evidence, and by the escape hatch of a Graphviz engine for anyone who needs
  it. Whether the default engine wraps `grandalf` (EPL-1.0 arm, ~600 lines of
  Sugiyama, lightly maintained) or implements layered layout directly is a
  decision the protocol defers; the prototype should answer it.
- **Compatibility**: Pure Python, 3.12+. One pure-Python runtime dependency for
  font parsing (`fonttools`).

### Option C: Own the renderer, Graphviz as the only layout engine

- **Description**: As Option B, but the layout engine is Graphviz driven via
  `-Tplain`, with no pure-Python fallback.
- **Scope**: Same as B minus the layout implementation, plus a subprocess
  boundary and its error handling.
- **Effort**: Medium.
- **Tradeoffs**: Removes the layout work and gets a battle-tested engine for
  free. But it makes a C binary a hard install requirement for a Python
  library, in exchange for capability the corpus does not need; it introduces a
  subprocess with version-dependent output to parse; and it makes the
  `system_dependencies == 0` success criterion unachievable. Graphviz's
  orthogonal routing is also not good enough to own the arrow failure families,
  so the routing work does not actually go away.
- **Compatibility**: Consumers install Graphviz.

### Comparison

| | A: adopt + post-process | B: own renderer, pluggable layout | C: own renderer, Graphviz only |
|---|---|---|---|
| Effort | Small now, rising | Large | Medium |
| Risk | High — fragile coupling to upstream output | Medium — layout quality, mitigated by graph size | Medium — install burden, subprocess parsing |
| Completeness | 6 of 9 diagram types; failure families mitigated, not excluded | 9 of 9; families excluded structurally | 9 of 9; families excluded structurally |
| Acceptance test 1 | By rewriting, fragile | By construction | By construction |
| Install story | System binary required | `pip install drawspec` | System binary required |
| Maintenance | Tracks another project's releases | Ours | Ours plus a version-sensitive parser |

## 4. Recommendation

**Recommended option: B — own the renderer, pluggable pure-Python layout.**

The survey converts the brief's opening hypothesis ("do not write a layout
engine, wrap one") into something more precise. The half that survives contact
with the evidence is: *do not write a **renderer** around someone else's
opinions* — and the answer there is the opposite of wrapping, because every
candidate's SVG fails the inline-Markdown test and post-processing it is a
permanent tax. The half that does not survive is the assumption that wrapping a
layout engine is cheap: at median 4 and maximum 17 nodes, the engine's power is
not the binding constraint, while its install cost is charged to every consumer
forever. Keeping the engine behind a one-method protocol gets the benefit of
the hypothesis (we can drop Graphviz or ELK in later, and should, if the
default proves inadequate) without paying its cost on day one.

Three consequences worth stating explicitly, because they shape the plan:

- **Three rendering families, one core.** Graph-shaped diagrams (flow, tree,
  cycle) need the layout engine. Grid-shaped ones (stack, timeline, column
  comparison) and parametric shapes (pyramid, concentric circles) need geometry
  and text fitting, not graph theory. Axis charts are a third family again. All
  three share exactly two things: the theme and text measurement. Nothing else
  should be shared, and no chart library (matplotlib included) can be used for
  the third, because their SVG fails acceptance test 1 more badly than the
  diagram tools do.
- **Text measurement is the critical path.** It gates box sizing, pyramid
  fitting and chart labels, and it must work for a font drawspec has never
  seen — read from the font file with `fonttools`, cached, never a hardcoded
  table. The known-hard part is that the rendered font may not be the measured
  font, since the SVG inherits the page's stack; the design must carry an
  explicit safety margin and never rely on a tight fit.
- **The failure families are the acceptance suite.** For each of the 11, the
  plan should name the structural reason it cannot be expressed, and a test
  that demonstrates it.

**Immediate next action**: run `design` to turn this into `status/plan.md` — the
input schema first, since it is the contract everything else reads and the most
expensive thing to change later, then text measurement, then the emitter, then
the three rendering families in that order.

**Decisions taken** (2026-08-11):

- [x] **Font resolution** — *replace and warn*. When the theme names a font that
      is not resolvable, drawspec substitutes a metric-compatible fallback,
      measures against the substitute, and emits a warning naming both fonts.
      It never fails on this alone and never substitutes silently. The warning
      must reach the CLI's stderr and the library's `warnings` channel, so a
      build can be configured to treat it as an error.
- [x] **Sizing input** — *width binding, height advisory*. The document may
      carry a width, a height, or both. Width is always binding: content is
      laid out to fit it, and failing to fit at the theme's minimum legible
      size is an error. Height is advisory by default — the canvas grows past
      it rather than compressing — and becomes binding only when the author
      marks it so, at which point overflow is an error like width.
- [x] **Theme format** — *TOML*. A theme is a TOML file so a consumer can
      version and diff it without importing drawspec. The loader parses it into
      a frozen dataclass; that dataclass is also constructible directly for
      programmatic use, but TOML is the documented surface.
- [x] **Default layout engine** — *deferred behind the protocol*. Whether the
      default engine wraps `grandalf` (EPL-1.0 arm, ~600 lines of Sugiyama,
      v0.8, lightly maintained) or implements layered layout directly is left
      open deliberately. The `LayoutEngine` protocol is the commitment; the
      implementation behind it is not. The first prototype of the three worst
      corpus diagrams settles it, and the plan should carry a task for that
      comparison before a task for the implementation.

**Open questions**:

- [ ] **Diagram titles**: the consumer's style rules leave "Figure 1"-style
      titles undecided. Proposed: a theme switch, default off, so the decision
      stays with the consumer and costs nothing to change.
- [ ] **Metric-compatible fallback set**: "replace and warn" needs a defensible
      substitution table (which fallback for a named serif / sans / mono, and
      on what basis). Whether drawspec bundles a font for this or maps onto the
      host's fonts is a packaging decision for the plan.

---

> Sections 5–6 (contracts, risks) are appended by `design`.

## 5. Contracts

The tool has no network surface and no database. Its contracts are four: the
input document, the theme file, the public Python API, and the CLI. The first
is by far the most expensive to change, because documents written against it
live in the consumer's repository.

### 5.1 The input document (the primary contract)

A document is JSON (or any format that parses to the same mapping). It carries
an explicit `version`, and a `kind` that selects both the rendering family and
which further fields are legal.

```json
{
  "version": 1,
  "kind": "flow",
  "title": "Request validation",
  "description": "An incoming request is validated, then either accepted for processing or rejected with a reason.",
  "width": 640,
  "nodes": [
    {"id": "in",  "text": "Request arrives",        "role": "start"},
    {"id": "chk", "text": "Is the payload valid?",  "role": "decision"},
    {"id": "ok",  "text": "Queue for processing",   "role": "step"},
    {"id": "no",  "text": "Reject with a reason",   "role": "terminal"}
  ],
  "edges": [
    {"from": "in",  "to": "ok"},
    {"from": "in",  "to": "chk"},
    {"from": "chk", "to": "ok", "label": "yes"},
    {"from": "chk", "to": "no", "label": "no"}
  ]
}
```

**What the author may write.** `version`, `kind`, `title`, `description`,
`width`, `height` (with an optional `height_binding` flag), `theme`, and the
per-kind payload: `nodes`/`edges`/`groups` for graph kinds, `levels` for
`pyramid`, `rings` for `rings`, `items` for `stack`/`timeline`/`columns`,
`axes`/`series` for `chart`. On a node: `id`, `text`, `role`, optional `note`.
On an edge: `from`, `to`, optional `label`, optional `style` naming a
theme-declared edge role.

**What the author may not write — and the schema rejects rather than ignores.**
Because the schema sets `additionalProperties: false` throughout, an author who
writes any of these gets a validation error naming the field, not a silently
discarded key. That error message is the teaching surface for a model authoring
blind:

| Rejected | Why |
|---|---|
| `x`, `y`, `cx`, `cy`, `points`, `d` | Coordinates are the tool's output, never its input |
| `width`/`height` **on a node or shape** | Box geometry is derived from measured text plus theme padding |
| `font_size`, `font_family`, `font_weight` | Type is selected by semantic role from the theme's scale |
| `color`, `fill`, `stroke`, `stroke_width` | Appearance is a property of the role, not the element |
| `anchor`, `port`, `arrow_head`, `dx`, `dy` | Edge geometry is derived from the shapes it connects |
| `z`, `order`, `layer` | Overlap is resolved by the layout, not declared |
| `viewBox`, `canvas` | Derived from `width` and the content |

`role` is drawn from a closed vocabulary the theme defines
(`start`, `step`, `decision`, `terminal`, `emphasis`, `note`, `group`), so a
role the theme does not declare is a validation error too. Text may carry
inline spans — `` `code` `` for the monospace role and `**bold**` for the
emphasis role — because those are semantic, not typographic.

**Versioning.** `version` is required and validated. v1 is frozen once the
first consumer document exists; additive fields ship as v1 minor changes with
defaults, and anything that changes the meaning of an existing field ships as
v2 with both readable in parallel for at least one release.

### 5.2 The theme (TOML)

```toml
version = 1
name = "example"

[canvas]
width = 640
min_legible_size = 9.0

[font]
sans = ["Source Sans 3", "DejaVu Sans", "sans-serif"]
mono = ["Source Code Pro", "DejaVu Sans Mono", "monospace"]
serif = ["Source Serif 4", "DejaVu Serif", "serif"]
default = "sans"

[scale]
title = 15.0
heading = 13.0
body = 11.0
label = 10.0

[box]
padding = [10.0, 12.0, 10.0, 12.0]
line_height = 1.35
corner_radius = 4.0

[edge]
stroke_width = 1.5
min_shaft_length = 16.0
head_length = 6.0

[role.step]
shape = "rect"
stroke = "currentColor"
dash = "none"

[role.decision]
shape = "diamond"
stroke = "currentColor"
dash = "none"

[role.note]
shape = "rect"
stroke = "currentColor"
dash = "3 2"
```

A theme is rejected at load time if any two roles are distinguishable only by
colour — see the `greyscale_ambiguous_role_pairs` criterion in §1. Colour is
optional throughout; `currentColor` is the default and the documented norm.

### 5.3 Public Python API

```python
from drawspec import render, render_document, load_theme, Theme

svg: str = render(document: Mapping[str, Any], theme: Theme | str | Path | None = None) -> str
```

- Pure function: same document plus same theme yields byte-identical SVG.
- Raises `DocumentError` (schema violation, naming the offending field),
  `ThemeError` (malformed or greyscale-ambiguous theme), `FitError` (content
  cannot fit at the theme's minimum legible size), `LayoutError` (the engine
  could not produce a valid arrangement).
- Emits `FontSubstitutionWarning` through `warnings` when a named font is not
  resolvable, naming the requested and substituted families, so a consumer can
  promote it with `warnings.simplefilter("error", FontSubstitutionWarning)`.

### 5.4 CLI

| Command | Behaviour | Exit |
|---|---|---|
| `drawspec render DOC [-o OUT] [--theme T] [--width N] [--height N]` | Writes SVG to `OUT` or stdout | 0 ok, 1 document/fit error, 2 usage |
| `drawspec validate DOC [--theme T]` | Validates without rendering; prints each violation with its JSON pointer | 0 clean, 1 violations |
| `drawspec theme check THEME` | Runs the theme invariants, including the greyscale pairing check | 0 clean, 1 violations |
| `drawspec schema [--out FILE]` | Emits the JSON Schema for the document format | 0 |

`--width`/`--height` override the document's own values, so a build can render
one document at several widths without editing it.

### 5.5 Internal component contracts

| Caller | Callee | Contract | Failure handling |
|---|---|---|---|
| Renderer | `TextMeasurer` | `measure(text, font_role, size) -> Extents`; `wrap(text, max_width, …) -> list[Line]` | Unresolvable font → substitute, warn, continue |
| Renderer | `LayoutEngine` | `layout(nodes_with_sizes, edges, direction) -> Positions`. The only coupling to a layout implementation — one method, sizes in, coordinates out | Engine failure → `LayoutError`; the protocol lets a Graphviz or ELK engine be substituted without touching callers |
| Family renderers | `Scene` | Each family emits a `Scene`: primitives (`Rect`, `Path`, `Ellipse`, `Polygon`, `TextRun`) in final coordinates, each tagged with a semantic role and carrying no styling | A primitive with an undeclared role is a programming error, caught in tests |
| `Scene` + `Theme` | `emit` | The single place SVG is produced, and therefore the single place the inline-safety invariants are enforced | Violation raises rather than emitting bad SVG |

The `Scene` seam is the load-bearing one: three rendering families converge on
one primitive list, so acceptance test 1 is satisfied in exactly one file
rather than three.

### 5.6 Persisted artefacts

None. drawspec has no database and no migrations; it is a pure function from
document to string. The only files it reads are the document, the theme, and
font files it does not modify.

## 6. Risks & Validation

| Risk | Likelihood | Impact | Mitigation | Validation |
|------|-----------|--------|------------|------------|
| **The measured font is not the rendered font.** The SVG inherits the page's font stack, so a consumer's page may render in a family drawspec never measured, and tight boxes overflow. | High | High | Never design for a tight fit: theme padding carries an explicit safety margin, and box width is the measured width plus that margin. Document that the theme's font stack should match the consuming page's. Warn loudly on substitution. | Integration test rendering the fixture set measured against font A and checked for overflow against the metrics of font B |
| **Pure-Python layout is not good enough** for the graph kinds, even at 17 nodes. | Medium | High | The `LayoutEngine` protocol is one method, so a Graphviz (`-Tplain`) or ELK engine is an additive change, not a rewrite. The T7 spike settles this on the three worst corpus diagrams *before* the implementation task, and its output is a picture, not an argument. | T7 spike; then edge-crossing and overlap counts on the fixture set |
| **The input schema is wrong in a way only found later**, after consumer documents exist. | Medium | High | `version` is required from day one and validated; `additionalProperties: false` means unknown fields fail loudly rather than being silently absorbed, so a mistaken field never becomes de-facto API. Freeze v1 only once a real consumer document exists. | Schema round-trip tests; a test asserting every forbidden field in §5.1 is rejected by name |
| **`FitError` fires too often** and the tool is unusable — every second document refuses to render. | Medium | Medium | The error is correct behaviour per the consumer's own style rules, but its *message* is the product: it must say what did not fit, by how much, and which of the three remedies applies. Measure the rate over the fixture set and treat a high rate as a theme-tuning signal, not a reason to soften the rule. | `fit_error_rate` measured over the regression fixtures |
| **Determinism breaks** — dict ordering, float formatting, or set iteration makes reruns differ, defeating diffable committed SVG. | Medium | Medium | Sort every iteration order explicitly; format floats through one helper with fixed precision; no `set` iteration in emit paths. | A test rendering every fixture twice and comparing bytes |
| **Anonymized corpus text distorts the fixtures.** Lorem ipsum has different letter frequencies from real prose, so measured widths differ from the originals. | Low | Low | The fixtures are reference material, not the test suite — drawspec's own fixtures are authored for the cases under test. Reproducing the corpus is explicitly not a goal. | n/a — scope boundary, stated in `corpus/README.md` |
| **Scope creep into a general diagramming tool** — ports, swimlanes, nested compound graphs, animation. | Medium | Medium | The rule from the brief: no feature that no corpus note asked for. The nine kinds are closed for v1; a tenth needs evidence. | Review gate on any PR adding a `kind` |
| **`grandalf`'s maintenance status** (v0.8, lightly maintained) becomes a liability if it is chosen in T7. | Low | Medium | It sits behind the protocol, and the EPL-1.0 arm of its dual licence permits vendoring the ~600 lines we would use if upstream goes dark. | T7 records the decision and its escape route |

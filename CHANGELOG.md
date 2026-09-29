# Changelog

All notable changes to drawspec are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The **document format** is versioned separately and independently: a document
declares `"version": 1`, and that number changes only when a document written
against it would stop working. Everything below is about the *package*.

## Unreleased

### Added

- **`files`, the fifteenth kind** — a directory listing drawn from flat paths
  (`src/app/main.py`); the folders a path passes through are inferred, so there
  is no nesting depth to get wrong. A trailing `/` marks an empty folder, a last
  segment of `...` stands for entries not listed, `link` draws a symlink to its
  target, `status` marks an entry `added`, `changed` or `removed` with a labelled
  pill (never colour alone), and `note` adds a comment in one aligned column.
  `sort` is `given` (default), `name` (natural) or `folders-first`. `style` is
  `icons` (default: tinted folders, and pages whose foot is a tag spelling the
  extension — `PDF`, `JSON`), `plain` (names and guides), or `unicode` /
  `ascii` (monospace text, as `tree` prints it). Paths written twice, a file used
  as a folder, `..` segments and absolute paths are refused at their entry.
- **`drawspec render --format text`** and `render_text()` — a `files` tree as
  plain text for a code block.
- **`[files]` theme section** — `tint` (folder fill strength, 0 for outlines),
  `types` (`labels`, `pictures` — five drawn type shapes — or `none`),
  `colours` (by extension, type family or `folder`; a coloured label is a
  solid tag), `label_ink` (its letters' colour) and `align` (`left`, the
  default, or `centre`). The `accent` theme colours them — white `PDF` on red;
  the default stays monochrome.

- **`rise` on `columns` and `timeline`** — the series ascends, each column drawn taller than
  the one before it on a common baseline, for a scale whose order is the
  content. Two corpus originals drew one by hand and both said so in their own
  words (*each star adds a condition to the one before it*); redrawn as plain
  `columns` they came out flat, and nothing caught it — no word was lost and no
  line crossed a word. What was lost was the geometry. It is a boolean, not a
  height per column: the author says the series rises and the theme's new
  `[box] rise` says by how much, so there is no number to get wrong. `pyramid`
  is not a substitute — it draws the last level as the narrowest, which is right
  for a maturity model and backwards for a ladder. On a `timeline` it is the
  same arithmetic and the axis is the baseline the labels already share, so
  nothing else about the drawing moves: each tick still runs from its own
  label's bottom edge to the line.
- `py.typed`, so a consumer's type checker gets the types the strict build
  already proves. Without the marker, PEP 561 requires a checker to treat the
  package as untyped, and every call into it resolved to `Any`.
- PyPI metadata: keywords, trove classifiers, project URLs and authors.
- `drawspec kinds` and `drawspec example <kind>`, for a caller that has the
  package but not the documentation. `validate` now reads `-` as stdin, so
  `drawspec example flow | drawspec validate -` is a toolchain smoke test.
- `AGENTS.md` and `llms.txt` — the whole format on one page, for an agent
  writing documents. Gated so it cannot drift from the code.
- **An MCP server** — `pip install 'drawspec[mcp]'` and `drawspec-mcp`, serving
  `validate`, `render` and `kinds` over stdio. `validate`'s violations arrive as
  `{"pointer", "message"}` objects rather than as prose on stderr, so an agent's
  write-validate-fix cycle closes without a shell in it. An optional extra: the
  library gains no dependency for anyone who does not install it.
- **`actor` on a node** — who performs a step, orthogonal to `role`, answering
  [#48](https://github.com/nuncaeslupus/drawspec/issues/48). Drawn as the box's
  lead so the names line up in a column. Free text rather than an enum on
  purpose: an actor is told apart by its **name**, which is legible in greyscale,
  so ownership costs none of the four non-colour channels the roles are told
  apart by and the greyscale invariant is untouched. A box has one lead, so a
  node naming an actor may not also write its own; that is refused by pointer.
- `CONTRIBUTING.md` and this changelog.

## 0.1.0 — unreleased

The first release. Thirteen diagram kinds, a published JSON Schema, a themeable
renderer, and a CLI.

### Added

- **Thirteen kinds** — `flow`, `tree`, `cycle`, `stack`, `timeline`, `columns`,
  `matrix`, `pyramid`, `rings`, `funnel`, `chart`, `quadrant`, `curve`.
- **A document format with no coordinates in it.** `x`, `font_size`, `stroke`
  and twenty-odd other fields are refused by name, each with the JSON pointer of
  the place it was written, so a placement mistake cannot be expressed rather
  than being caught late.
- **A published JSON Schema**, versioned and addressable, generated from the same
  field tables the runtime validator uses — so the schema an editor completes
  against and the tool that validates can never disagree.
- **Themes**, in TOML, resolving semantic roles to appearance. Includes a
  greyscale invariant: no information is carried by colour alone, so a diagram
  survives dark mode and monochrome printing.
- **Groups and bands** — containers drawn around boxes, and named things running
  alongside them. An edge may name a group as well as a node, for a relation that
  belongs to the whole container rather than to one box inside it.
- **Orthogonal edge routing** with border anchoring, lane separation, a minimum
  visible shaft, and label placement that avoids every line, box and other label.
- **A CLI** — `render`, `validate`, `theme check`, `schema` — with documented
  exit codes.
- **Embeddable output.** Inline SVG with no global `<style>`, no colliding ids
  when two diagrams share a page, and colour inherited from the surrounding
  document.
- **Bundled subsetted fonts**, so text measures identically on a laptop and in a
  container with no fonts installed. No system dependency of any kind.

<!-- Compare links are added by the release, once there is a tag to compare
     against. `main...HEAD` compares the default branch with itself, and a
     link to an unpushed tag is a 404: both show a reader nothing. -->

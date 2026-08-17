# Changelog

All notable changes to drawspec are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The **document format** is versioned separately and independently: a document
declares `"version": 1`, and that number changes only when a document written
against it would stop working. Everything below is about the *package*.

## [Unreleased]

### Added

- `py.typed`, so a consumer's type checker gets the types the strict build
  already proves. Without the marker, PEP 561 requires a checker to treat the
  package as untyped, and every call into it resolved to `Any`.
- PyPI metadata: keywords, trove classifiers, project URLs and authors.
- `CONTRIBUTING.md` and this changelog.

## [0.1.0] — unreleased

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

[Unreleased]: https://github.com/nuncaeslupus/drawspec/compare/main...HEAD
[0.1.0]: https://github.com/nuncaeslupus/drawspec/releases/tag/v0.1.0

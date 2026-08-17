# Contributing to drawspec

Thank you for looking. This page is short on ceremony and long on the two or
three things that are genuinely easy to get wrong here.

## Getting set up

```bash
make sync     # install with dev extras (uses uv)
make test     # pytest
make lint     # ruff check + ruff format --check + strict mypy
```

Python 3.12 or newer. There is no system dependency — no Graphviz, no Cairo, no
headless browser. If something asks you to install one, that is a bug.

## Four files are generated. Do not edit them by hand.

This is the thing a first pull request usually trips over, and a test will fail
if you do:

| File | Regenerate with |
|---|---|
| `docs/format.md` | `make docs` |
| `docs/cli.md` | `make docs` |
| `docs/theme.md` | `make docs` |
| `schema/drawspec-v1.schema.json` | `make schema` |

They are generated **from the code they describe** — the field tables in
`src/drawspec/schema.py` and the argument parser in `src/drawspec/cli.py` are the
single source of truth. That is deliberate: a reference that can drift from the
tool is worse than no reference, because an editor will tell an author their
document is fine while `drawspec validate` rejects it. So if you add a field,
add it to the table and run `make docs && make schema`; the diff is the
documentation.

## The gallery is committed on purpose

`docs/gallery/` holds a rendered SVG per reference document plus the combined
page, and all of it is checked in. That is not an oversight — **it is how you see
what your change did to the pictures.** Run:

```bash
make gallery
```

and read the diff. A layout change that looks harmless in the code and moves
thirty drawings is exactly the kind of thing this catches, and it has caught it:
four rendering defects were found by looking at that page and by no gate.

If your change alters the drawings, commit the regenerated gallery with it.

## Two checkers worth running on anything that touches layout

```bash
uv run python tools/collisions.py docs/gallery   # does a line cross a word
uv run python tools/clipping.py  docs/gallery    # is every word on the page
```

Both should report zero. They answer different questions and neither implies the
other — `clipping.py` exists because a defect passed every check in the suite
while being partly drawn off the canvas.

## What a change should look like

* **Commits** follow [Conventional Commits](https://www.conventionalcommits.org)
  — `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`.
* **A new field, kind or theme key needs evidence.** The vocabulary is closed on
  purpose and opened on measurement: `docs/kinds-wanted.md` sorts 89 hand-drawn
  originals by the kind that would have to draw them, and the four kinds added
  since v1 each cleared originals nothing could draw. "It would be nice to have"
  is not enough; "here are three documents that cannot be expressed" is.
* **A refusal is a feature.** If drawspec cannot draw something correctly it
  should say so, by name and with a JSON pointer, rather than draw it badly.
  Prefer a good error to a bad diagram.
* **Tests carry their reasoning.** Assertions here are numeric, and a coordinate
  comparison cannot say why anyone cared. A docstring recording the drawing that
  went wrong is the convention, not clutter.

## Releasing

`.github/workflows/release.yml` does the work; a tag is the only input. Pushing
`v0.1.0` runs the suite, builds, checks, publishes 0.1.0 to PyPI and cuts a
GitHub release. A `workflow_dispatch` run does everything except the upload, so
the path can be exercised without cutting a tag.

**Once, before the first release.** PyPI needs a trusted publisher configured —
this is what lets the workflow upload with no API token stored anywhere. On
PyPI, under the project (or as a *pending* publisher, since `drawspec` is not
registered yet):

| Field | Value |
|---|---|
| Owner | `nuncaeslupus` |
| Repository | `drawspec` |
| Workflow | `release.yml` |
| Environment | `pypi` |

**Each release.**

1. Bump `version` in `pyproject.toml` **and** `__version__` in
   `src/drawspec/__init__.py`. A test pins them together, and the workflow
   checks both against the tag before it publishes anything — a tag that
   disagrees with the package cannot be withdrawn once uploaded.
2. In `CHANGELOG.md`, retitle `## Unreleased` to the version and date, open a
   fresh `## Unreleased`, and add the compare links at the bottom — they are
   deliberately absent until there is a tag to compare against:
   ```markdown
   [Unreleased]: https://github.com/nuncaeslupus/drawspec/compare/v0.1.0...HEAD
   [0.1.0]: https://github.com/nuncaeslupus/drawspec/releases/tag/v0.1.0
   ```
   Restore the brackets on the headings so the references resolve.
3. Merge that, then tag the merge commit and push:
   ```bash
   git tag -a v0.1.0 -m "v0.1.0" && git push origin v0.1.0
   ```
4. Watch the run. If `check` fails, no upload happened — fix and re-tag.

**If the first upload is rejected**, the usual cause is the trusted publisher
not being configured, or being configured against a different environment name.
The workflow's environment is `pypi`.

## Reporting a bug

Please include **the document**. A drawspec bug is almost always reproducible
from the JSON alone, which makes it the single most useful thing in a report —
more than a screenshot, and much more than a description. The issue template
asks for it, plus your theme and `drawspec --version`.

## Licence

By contributing you agree that your contribution is licensed under the MIT
licence, the same as the rest of the project.

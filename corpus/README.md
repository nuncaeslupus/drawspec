# Evidence corpus

87 SVG diagrams written by hand by an LLM, and their objective measurements.
They are here as evidence of the failure modes drawspec exists to make
impossible — see `docs/brief.md` for the analysis and `docs/theme-requirements.md`
for the style rules they were reviewed against.

## These files are anonymized

The originals belong to a different project and their content is not ours to
publish. What is here is a derivative that keeps every **drawing** decision and
destroys every **content** decision:

| Kept | Removed |
|---|---|
| Geometry: coordinates, sizes, paths, shapes | All human-readable text |
| Typography: `font-size`, `font-family`, anchors | `<title>` and `<desc>` wording |
| Strokes, fills, markers, patterns | Original filenames (now `fixture-NNN`) |
| Document structure and element counts | `id` values (renumbered `n1`, `n2`, …) |

Every text run was replaced with lorem ipsum of the **same character length**,
so string widths stay representative and the original layout problems remain
visible. The files contain no non-ASCII characters and no word outside the lorem
ipsum vocabulary.

Do not treat the text as meaningful — a fixture whose boxes say
"consectetur adipiscing" is still a faithful record of a box that was too small
for what it had to hold.

## What is here

| Path | What |
|---|---|
| `fixtures/fixture-NNN.svg` | The 87 anonymized diagrams, numbered in the source order |
| `metrics.json` | Per-fixture measurements: viewBox, element counts, box and text counts, font sizes, stroke widths, curve and marker counts, and whether a human flagged it |

`metrics.json` records `reviewer_flagged` — whether that diagram drew a review
note — but not the note itself, since the notes name the source material. The
aggregate failure taxonomy is in `docs/brief.md`.

## The three worst

Named in the brief as the acceptance test for any candidate tool:

| Fixture | The reviewer's verdict |
|---|---|
| `fixture-020.svg` | Terrible on margins and arrows and text that does not fit |
| `fixture-067.svg` | Overlapping text, arrows with only a head, no vertical axis label |
| `fixture-047.svg` | A cycle whose arrows fail to close, with a truncated sentence crossing a line |

## Using them

The corpus is reference material and a source of realistic test cases, not a
test suite. drawspec's own tests use fixtures it generates itself, covering
cases the corpus happens not to contain — long text in tight boxes, labels
between nodes, mixed typography, deep pyramids. Reproducing this corpus is not
a goal; making its failure families unrepresentable is.

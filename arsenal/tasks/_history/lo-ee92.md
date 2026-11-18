---
id: lo-ee92
title: "G3: matrix — rows against columns with spanning cells"
priority: 5
status: done
pr: https://github.com/nuncaeslupus/drawspec/pull/25
---

Completed in round four and merged as [#25](https://github.com/nuncaeslupus/drawspec/pull/25).

**This payload is a reconstruction.** The original was never committed to the
coordination branch — the task was authored and worked in the same session, and
the row referenced a file that only ever existed on a feature branch.
`queue_doctor.sh` reported it as `missing-payload` from then on. Nothing was
blocked by it; the work is merged and the acceptance evidence is the PR and the
suite. It is restored so the ledger is consistent for a cold-start session, and
because an audit that always reports the same four errors is an audit people stop
reading.

## Acceptance gate

Met at merge, and still enforced continuously rather than by this file: the kind
has a reference document in `docs/reference/`, the gallery renders it, and
`tests/test_gallery.py::test_gallery_covers_every_kind_in_the_vocabulary`
asserts that every kind in the vocabulary has one.

```bash
uv run python -c "
from drawspec.schema import KINDS
assert 'matrix' in KINDS, 'the kind is no longer in the vocabulary'
print('matrix is in the vocabulary; docs/reference and the gallery cover it')
"
```

## Tests

`tests/test_kinds_grid.py`, plus the gallery and acceptance suites.

## Location

`src/drawspec/kinds/grid.py`, `docs/reference/`.

---
id: t-ee8091be
title: "review: Non-finite numbers pass validation: SVG with `inf` coordinates or a traceback"
priority: 5
requires: [human:gate]
---

Imported from issue #184

**Severity:** high · **Confidence:** high · **Category:** correctness

**Where:** `src/drawspec/schema.py:7439-7491, src/drawspec/charts.py:441, src/drawspec/charts.py:1027, src/drawspec/clearance.py:294, src/drawspec/kinds/pie.py:312, src/drawspec/kinds/treemap.py:215, src/drawspec/kinds/sankey.py:188, src/drawspec/kinds/gantt.py:975, src/drawspec/kinds/grid.py:765`

### Finding
Nothing checks number fields for finiteness (only timing and pert do). `1e400` is valid JSON and parses to inf; Python's json also accepts NaN/Infinity. `drawspec render` then exits 0 with `viewBox="... inf ..."` / `x="inf"`, `validate` says 'a valid sankey document', or the renderer dies with ValueError/OverflowError/ZeroDivisionError.

### Evidence
Repro: `echo '{"version":1,"kind":"flow","width":Infinity,"nodes":[{"id":"a","text":"x"}],"edges":[]}' | drawspec render -` prints an SVG full of `inf`, exit 0. sankey flow amount 1e400 -> `validate` reports valid. Mutation fuzz of the bundled examples: chart axis max=inf -> OverflowError charts.py:441; treemap amount=inf -> ZeroDivisionError; gantt at=1e308 in text mode -> OverflowError; chart data value 1e308 (finite) -> polygon points 'inf,...'.

### Suggested direction
Reject non-finite and absurdly large numbers once in _check_field (math.isfinite plus a magnitude bound), and pass parse_constant to json.loads so NaN/Infinity are refused at the JSON layer.

_From the full repo review of 2026-11-11 (finding #3). Not fixed yet; verify before acting._

## Acceptance gate

<!-- This task came from an issue, so its "gate" is prose. Write a real check
     below, then DELETE the `requires: [human:gate]` line in the front matter.
     Until that line is gone the selector will not offer this task, which is
     deliberate: a prose gate runs nothing, and a gate that runs nothing passes
     everything. -->

```bash
# arsenal:gate-placeholder — replace with the real check; it may land in this task's own PR
false
```

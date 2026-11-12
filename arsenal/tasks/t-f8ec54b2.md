---
id: t-f8ec54b2
title: "review: No fuzz or property tests: a 5-minute mutation fuzz finds 12 crash sites"
priority: 5
requires: [human:gate]
---

Imported from issue #194

**Severity:** medium · **Confidence:** high · **Category:** tests

**Where:** `tests/test_mcp.py:278-330, tests/test_schema.py:378-420, tests/test_failure_families.py`

### Finding
The suite is large (8,413 tests, >4 min; 1,006 tests in the four emit/CLI/MCP files alone take 78 s) and example/golden driven, but nothing mutates valid documents. Substituting each scalar/array in the 47 bundled examples with boundary values (4.6k cases, no dependencies) surfaces 12 distinct non-DrawspecError crash sites across 9 kinds plus `inf` in output - the findings above. The invariant 'render raises only DrawspecError' is the MCP server's contract and is not pinned.

### Evidence
pytest --collect-only: 8413 tests; `grep -rl hypothesis tests` empty. Fuzz script results: IndexError grid.py:918, ValueError wrap.py:215, KeyError schema.py:9301 and :13756, OverflowError grid.py:765/charts.py:441/gantt.py:975, ZeroDivisionError treemap.py:215/sankey.py:188, ValueError charts.py:441/1027, pie.py:312, clearance.py:294.

### Suggested direction
Add a parametrised mutation test over EXAMPLES asserting that render/render_text either succeed with well-formed XML containing no nan/inf, or raise DrawspecError.

_From the full repo review of 2026-11-11 (finding #13). Not fixed yet; verify before acting._

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

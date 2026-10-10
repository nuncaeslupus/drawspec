---
id: t-2f4aa14a
title: "Audit every existing kind: clearer, more expressive, no gimmicks"
priority: 1
tags: [research]
---

Owner asked: check all drawing kinds the way round 2 researched new ones (real public diagrams, yEd/draw.io feature sets, colour/grey use) and implement only improvements with evidence.

Deliverable: docs/research/kind-audit.md with a per-kind verdict (improve / leave) and evidence; worthwhile items built with docs, references, gallery.

## Acceptance gate
```bash
test -s docs/research/kind-audit.md && uv run pytest -q && uv run python tools/collisions.py docs/gallery && uv run python tools/clipping.py docs/gallery
```


## Acceptance gate

<!-- Replace this with a fenced bash block. A gate that is only prose runs
     nothing, and a gate that runs nothing passes everything — `task_select.py`
     reports gate: false for a task with no block, so an unenforced gate is
     visible rather than quietly inert. -->

```bash
# arsenal:gate-placeholder — replace with the real check; it may land in this task's own PR
# e.g. bash tests/surface_probe_test.sh
false
```

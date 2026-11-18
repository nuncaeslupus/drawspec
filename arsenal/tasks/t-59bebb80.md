---
id: t-59bebb80
title: "review: schema.py is an 18.5k-line god module; each kind is spread over five places"
priority: 5
requires: [human:gate]
---

Imported from issue #192

**Severity:** medium · **Confidence:** high · **Category:** design

**Where:** `src/drawspec/schema.py:7032-7343, src/drawspec/schema.py:7570-7650, src/drawspec/schema.py:16611-16816, src/drawspec/kinds/__init__.py:150-270`

### Finding
src/drawspec/schema.py is 18,483 of 72,370 lines (25%) and holds, for all 47 kinds, the constants, field tables, ~90 dataclasses, a 122-field union `Document`, every `_<kind>_refusal/_violations/_document` function and the JSON Schema generator. Dispatch is by hand-written if-chains (31 consecutive `if kind in X_KINDS` in validate_document, 133 kind branches in schema.py, 37 in kinds/__init__.py), so adding a kind means editing schema.py in ~6 spots plus kinds/<kind>.py, kinds/__init__.py, examples.py and the docs - the repo ships an `add-kind` skill and a 'kind checker' to cope with that.

### Evidence
wc -l; `grep -c '_KINDS: Final' schema.py` = 38; `grep -n 'if kind in|kind ==' | uniq -c` = 133 in schema.py; Document field count 122 (grep over lines 7032-7343).

### Suggested direction
Give each kind one module that registers {fields, validate, parse, scene, text, example, purpose} in a registry, with a per-kind payload dataclass instead of the union Document; schema.py shrinks to the shared machinery.

_From the full repo review of 2026-11-11 (finding #11). Not fixed yet; verify before acting._

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

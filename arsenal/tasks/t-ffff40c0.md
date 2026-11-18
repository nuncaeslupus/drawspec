---
id: t-ffff40c0
title: "review: MCP refusals carry every violation twice and are unbounded in size"
priority: 5
requires: [human:gate]
---

Imported from issue #189

**Severity:** medium · **Confidence:** high · **Category:** ux

**Where:** `src/drawspec/mcp.py:285-304, src/drawspec/cli.py:518-531, src/drawspec/schema.py:18034-18036`

### Finding
_refusal returns `message: str(error)` - which for a DocumentError is already the full multi-line list of violations - plus the same violations again as objects. The CLI's _refuse docstring explains this doubling was removed there; the MCP path re-introduces it, so every correction round costs the agent roughly double the tokens. There is also no cap: a 4000-node document with bad refs returns ~650 KB of message plus ~650 KB of violations.

### Evidence
validate_document on a flow with one bad edge and one forbidden field: message is 279 chars, violations JSON 303 chars, same content. Flow with 4000 nodes/edges of unknown ids -> DocumentError message of 652,245 chars (8002 violations).

### Suggested direction
For DocumentError send a one-line summary in `message` and the list only in `violations`; cap the list (e.g. first 50 plus a count) and collapse repeated identical messages.

_From the full repo review of 2026-11-11 (finding #8). Not fixed yet; verify before acting._

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

---
id: t-bbbecf6a
title: "review: Theme paths let a document or MCP caller probe arbitrary files on the server"
priority: 5
requires: [human:gate]
---

Imported from issue #190

**Severity:** medium · **Confidence:** high · **Category:** security

**Where:** `src/drawspec/theme.py:2747-2764, src/drawspec/mcp.py:85-103, src/drawspec/mcp.py:325-356, src/drawspec/schema.py:18054-18066`

### Finding
A theme is 'a bundled name or a path', resolved with expanduser and opened without restriction, and it can come from the tool's `theme`/`variants` arguments or from the untrusted document's own `theme` field. The error text distinguishes 'not found' from 'could not be read' from a TOML parse error with line/column, so a caller can test for the existence of any path and learn about its first tokens; valid TOML files are merged as a theme. The tools are nevertheless annotated read-only/closed-world and described as 'no I/O'.

### Evidence
render_document with theme='/etc/passwd' -> 'theme file could not be parsed as TOML: /etc/passwd (Expected \'=\' after a key ... (at line 1, column 5))'; variants={'dark':'/root/.ssh/id_rsa'} -> 'theme file not found: /root/.ssh/id_rsa'. Same via {"theme": "/etc/passwd"} inside the document with no theme argument.

### Suggested direction
In the MCP server accept bundled theme names only (or paths under an explicitly configured directory) and ignore/refuse a path in the document's `theme`; keep path themes for the local CLI.

_From the full repo review of 2026-11-11 (finding #9). Not fixed yet; verify before acting._

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

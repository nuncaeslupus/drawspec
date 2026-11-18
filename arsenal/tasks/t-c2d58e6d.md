---
id: t-c2d58e6d
title: "review: Skill reads AGENTS.md from `main`, which can be ahead of the installed package"
priority: 5
requires: [human:gate]
---

Imported from issue #196

**Severity:** medium · **Confidence:** medium · **Category:** ux

**Where:** `skills/drawspec/SKILL.md:9-19, CHANGELOG.md:11-30, pyproject.toml:97-103`

### Finding
skills/drawspec/SKILL.md tells the agent to read the format from the GitHub `main` URL of AGENTS.md; AGENTS.md is not in the wheel. main already documents kinds listed under CHANGELOG 'Unreleased' (neuralnet branches etc.), so an agent with the released package writes documents its installed drawspec refuses as unknown kind/field. It also makes the skill depend on network access and on whatever that URL serves at the time.

### Evidence
Read SKILL.md and the hatch wheel config (packages=['src/drawspec'] plus the schema only); CHANGELOG Unreleased lists new neuralnet features while __version__ is 0.4.3. PyPI contents not checked.

### Suggested direction
Ship AGENTS.md inside the package and expose it offline (`drawspec agents` / an MCP resource), or link the skill to the tag matching the installed version.

_From the full repo review of 2026-11-11 (finding #15). Not fixed yet; verify before acting._

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

---
id: t-281dc4ac
title: "review: Release workflow pushes the tag before the suite runs"
priority: 5
requires: [human:gate]
---

Imported from issue #195

**Severity:** medium · **Confidence:** medium · **Category:** release

**Where:** `.github/workflows/release.yml:20-58, .github/workflows/release.yml:60-66`

### Finding
On a push to main the `tag` job creates and pushes v<version> and only then does `check` run lint/mypy/pytest. If the suite fails, the tag stays on a red commit and nothing is published; the next push to main sees 'tag already exists; nothing to release' (tag output empty), so a fix-forward commit can never publish that version without someone deleting the tag by hand or pushing a tag manually.

### Evidence
Traced the workflow: `git push origin "$tag"` is in job `tag`; `check` has `needs: tag`; `publish` requires needs.tag.outputs.tag != '', which the already-exists branch never sets. Tags pushed with GITHUB_TOKEN do not start a new tag-push run.

### Suggested direction
Run the suite first and create the tag only after it passes (or in the publish job), or make the 'already exists' branch still emit the tag when no PyPI release exists for it.

_From the full repo review of 2026-11-11 (finding #14). Not fixed yet; verify before acting._

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

---
id: lo-f0f8
title: "C2: publish the gallery to GitHub Pages and link it from the README"
priority: 5
tags: [laptop, readiness]
---

**The most persuasive artefact this project has, and you currently have to clone
the repository to see it.** `docs/gallery/index.html` is already built, already
committed, and already inlines all 34 reference drawings into one page — and
`has_pages` is `false`, so there is no URL to send anyone.

For a tool whose entire claim is *the drawings come out right*, a link that shows
34 of them is worth more than any paragraph in the README. It is also the natural
value for **C1**'s homepage field.

Two things to decide:

* **Source.** Pages can serve `/docs` from `main` with no workflow at all, which
  is the cheapest thing that works and keeps the committed gallery as the
  published one. A build workflow that regenerates on push is tidier but adds a
  moving part; the gallery is committed precisely so a diff shows what a change
  did to the pictures, and that property should survive.
* **What else goes up.** `docs/` also holds the guide and the three generated
  references, so serving the directory publishes those too — which is a feature,
  and makes the *Documentation* URL in **A2** and **C1** real. Confirm the plan
  docs and `kinds-wanted.md` reading as public is intended before switching it on.

## Acceptance gate

The gallery is reachable at a public URL, that URL is in the README, and the page
still carries every reference drawing.

```bash
set -e
grep -qiE "github\.io|drawspec\.dev" README.md
uv run python - <<'PY'
import pathlib, re
page = pathlib.Path("docs/gallery/index.html").read_text(encoding="utf-8")
count = len(re.findall(r"<svg", page))
expected = len(list(pathlib.Path("docs/reference").glob("*.json")))
assert count >= expected, f"{count} drawings inlined, {expected} reference documents"
print(f"{count} drawings on the page")
PY
```

The URL itself has to be opened by a human once — a 200 is not proof the page
renders.

## Tests

`tests/test_gallery.py` already asserts the page builds and that ids do not
collide across inlined diagrams. Nothing new is needed there; this task is
delivery, not rendering.

## Location

GitHub repository settings (Pages), `README.md`, and possibly a
`.github/workflows/pages.yml` depending on the decision above.

---

## Confirmed from a cloud session, 2026-08-17

Same finding as C1: no Pages tool on the available GitHub MCP surface, so this is
`laptop` work. The cheapest thing that works, and the recommendation:

**Settings → Pages → Source: Deploy from a branch → `main` / `/docs`.** No
workflow, no build step, and the committed gallery stays the published one —
which preserves the property that a diff of `docs/gallery/` shows what a change
did to the pictures.

That serves the whole of `docs/`, so these all become real URLs:

| | |
|---|---|
| gallery | `https://nuncaeslupus.github.io/drawspec/gallery/` |
| guide | `https://nuncaeslupus.github.io/drawspec/guide.html` |
| format reference | `https://nuncaeslupus.github.io/drawspec/format.html` |

Confirm first that the round-plan documents and `kinds-wanted.md` reading as
public is intended — they are already public in the repository, so this is a
question of prominence rather than of disclosure.

The README link is **not** pre-written: pointing at a page that does not exist
yet is worse than not linking, so add it once Pages is live. That is also the
value for C1's homepage field, which is why C1 depends on this one.

---

## Repository side done in #53, 2026-08-17 — one switch left

Everything that can be done from a repository is in **#53**: `_config.yml` for a
root-served Pages site, and the gallery link at the top of the README's gallery
section.

**Deliberately not recorded `done`.** The page 404s until Pages is enabled, and
recording done for an unreachable URL is the false-`done` this queue exists to
prevent. The payload always said a human has to open it once — a 200 is not
proof the page renders.

**The switch: Settings → Pages → Source: Deploy from a branch → `main` / `/`
(root).** Root rather than `/docs`, because the schema at
`schema/drawspec-v1.schema.json` has to be served too — see C3, which shares the
host.

Then open `https://nuncaeslupus.github.io/drawspec/docs/gallery/` and look at it.

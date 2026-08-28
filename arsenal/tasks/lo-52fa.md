---
id: lo-52fa
title: "C4: the consumer's 87 documents still pin the old schema URL"
priority: 5
tags: [readiness, laptop]
---

Raised by cross-repo review on #53, and it is correct.

`nuncaeslupus/opos` carries the drawspec corpus at
`docs/esquemas/drawspec/corpus/*.json`, and those documents embed
`"$schema": "https://drawspec.dev/schema/drawspec-v1.schema.json"` — the URL
that does not resolve. #53 moved this repository's `SCHEMA_ID` to the GitHub
Pages host; it could not touch theirs.

**Nothing regressed.** The old URL was already dead, so those documents were
already getting no completion and no inline errors — this is an unfixed gap, not
a break introduced by #53. Worth being precise about, because the review framed
it as drift caused by the change.

**Why it is a separate task.** This session's GitHub access is scoped to
`nuncaeslupus/drawspec`; `opos` is a different repository and out of scope. It
also has to happen *after* Pages is switched on (**C2**), or it would replace one
dead URL with another.

## Acceptance gate

Every document in the consumer's corpus quotes the live `SCHEMA_ID`, and the
count of documents still naming the dead domain is zero.

```bash
set -e
uv run python - <<'PY'
import pathlib, json, sys
from drawspec.schema import SCHEMA_ID
corpus = pathlib.Path("../opos/docs/esquemas/drawspec/corpus")
if not corpus.is_dir():
    sys.exit("the consumer's corpus is not checked out beside this repository; "
             "clone nuncaeslupus/opos as a sibling and re-run")
stale = [p.name for p in sorted(corpus.glob("*.json"))
         if "drawspec.dev" in p.read_text(encoding="utf-8")]
assert not stale, f"{len(stale)} document(s) still name the dead domain: {stale[:5]}"
carried = [p for p in corpus.glob("*.json") if SCHEMA_ID in p.read_text(encoding="utf-8")]
print(f"{len(carried)} document(s) quote the live SCHEMA_ID, 0 stale")
PY
```

The gate assumes `opos` is cloned as a sibling directory, which is how the
comparison tooling already expects it.

## Tests

None here — the assertion belongs in the consumer's repository if anywhere. This
repository's own coupling is already covered by
`test_the_published_gallery_and_the_schema_id_are_served_from_one_place`.

## Location

`nuncaeslupus/opos`, `docs/esquemas/drawspec/corpus/*.json`. A find-and-replace,
and the PR should say why the URL moved rather than only that it did.

Depends on **C2** — do not run this until the Pages switch is on and the new URL
actually serves, or it swaps one dead identity for another.

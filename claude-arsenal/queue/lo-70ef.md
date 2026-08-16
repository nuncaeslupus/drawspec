# C3: settle the schema URL — does drawspec.dev resolve, and what is the fallback

`schema.SCHEMA_ID` is `https://drawspec.dev/schema/drawspec-v1.schema.json`, and
`docs/guide.md` tells every author to put that in their document's `$schema` so
they get completion and inline errors while typing. That single line is most of
what makes the format pleasant to write by hand — and **all of it depends on the
URL resolving**.

**This session could not check it.** The agent proxy refused the CONNECT with a
403, so the result is *unknown*, not *broken* — do not act on an assumption
either way. First step is to open it from a normal network.

Then, whichever it is:

* **It resolves** — nothing to do but say so here and close this, ideally with a
  test that fetches it and compares against the committed `schema/` artefact, so
  a stale deployment is caught rather than discovered by an author.
* **It does not** — decide between registering the domain (the owner's call and a
  recurring cost) and pointing `SCHEMA_ID` at a URL that already exists, which
  GitHub Pages gives for free once **C2** lands. Note that `$id` is an identity,
  not just a location: changing it changes the identifier every existing document
  references, so it is a v1-compatibility question and not a find-and-replace.
  The published `schema/drawspec-v1.schema.json` and the copy inside the wheel
  both carry it.

**Owner decision either way** — buying a domain, or changing a published
identifier, is not a call to take unilaterally.

## Acceptance gate

The URL in `SCHEMA_ID` resolves and serves the same document as the committed
artefact.

```bash
set -e
uv run python - <<'PY'
import json, urllib.request, pathlib
from drawspec.schema import SCHEMA_ID, published_schema_path
with urllib.request.urlopen(SCHEMA_ID, timeout=20) as response:
    served = json.load(response)
committed = json.loads(published_schema_path().read_text(encoding="utf-8"))
assert served == committed, f"{SCHEMA_ID} serves a different document than schema/"
print(f"{SCHEMA_ID} resolves and matches the committed artefact")
PY
```

If the sandbox cannot reach the host, this cannot be recorded `done` from a cloud
session — run it from the laptop. A gate that could not run is not a gate that
passed.

## Tests

The gate should **not** go in the suite as written: a network fetch makes `make
test` fail offline and on every CI runner with restricted egress. If it becomes a
test, mark it for an opt-in marker rather than the default run.

## Location

`src/drawspec/schema.py` (`SCHEMA_ID`), `schema/drawspec-v1.schema.json`,
`docs/guide.md`, and DNS if the answer is to register the domain.

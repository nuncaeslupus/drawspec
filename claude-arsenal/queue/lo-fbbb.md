# B3: an MCP server — render and validate as tools an agent can call

**Decided, after B1 landed.** The original question was *skill or MCP server*.
The answer is MCP, and the reasoning is worth keeping because it is what makes
this task worth doing at all.

A skill would have been a document — and the document already exists. `AGENTS.md`
is 185 lines, gated so it cannot drift, and found by every coding agent that
looks for repository instructions. Shipping a skill would have been a *second
copy of the format* to keep current, which is the drift this project keeps
designing out, for a narrower audience.

**An MCP server adds what no document can: the feedback loop.** Today an agent
writing a document has to shell out to `drawspec validate`, capture stderr, and
parse prose to find out that `/edges/2/to` names nothing. Those refusals are the
best thing this tool produces — located, complete, one pass is one edit — and
they arrive as text an agent has to scrape. As tools they come back as data, in
the agent's own loop, and the write-validate-fix cycle closes without a shell.

## What it exposes

Three tools, and deliberately not more:

| Tool | In | Out |
|---|---|---|
| `validate` | a document | ok, or every violation as `{pointer, message}` — **structured, not prose** |
| `render` | a document, optional theme/width | the SVG |
| `kinds` | — | the thirteen kinds and what each is for |

`validate` is the one that earns the server. `render` is the payoff. `kinds` is
free — `drawspec.examples.PURPOSE` already holds it.

**Do not invent a second vocabulary.** Every tool takes the same document the CLI
takes, and the errors are the ones `DocumentError.violations` already carries.
An MCP layer that paraphrases drawspec's refusals is a third description of the
format to keep in step with the other two.

## Decisions still open

* **Where it lives.** In this repository as an optional extra
  (`pip install drawspec[mcp]`, entry point `drawspec-mcp`) keeps it versioned
  with the format it serves — the same argument that put the JSON Schema in the
  wheel. A separate repository decouples its release cadence. **Recommendation:
  here, behind an extra**, so it cannot drift and costs nothing to anyone who
  does not install it.
* **stdio only, or HTTP too.** stdio is what every client supports and is
  enough. Do not build HTTP until something asks for it.

## Acceptance gate

The server starts, lists exactly the three tools, and a document round-trips —
including a *refusal* arriving as structured violations rather than as a string,
which is the whole point.

```bash
set -e
uv sync --all-extras
uv run python - <<'PY'
import json, subprocess, sys
# Speaks MCP over stdio: initialize, tools/list, then one good and one bad
# document through `validate`.
def rpc(proc, method, params=None, ident=1):
    proc.stdin.write(json.dumps(
        {"jsonrpc": "2.0", "id": ident, "method": method, "params": params or {}}) + "\n")
    proc.stdin.flush()
    return json.loads(proc.stdout.readline())

proc = subprocess.Popen([sys.executable, "-m", "drawspec.mcp"],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
rpc(proc, "initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                         "clientInfo": {"name": "gate", "version": "0"}})
listed = rpc(proc, "tools/list", ident=2)
names = {t["name"] for t in listed["result"]["tools"]}
assert names == {"validate", "render", "kinds"}, names

good = {"version": 1, "kind": "flow", "nodes": [{"id": "a", "text": "A step"}]}
bad = {"version": 1, "kind": "flow", "nodes": [{"id": "a", "text": "A step"}],
       "edges": [{"from": "a", "to": "ghost"}]}
ok = rpc(proc, "tools/call", {"name": "validate", "arguments": {"document": good}}, 3)
assert not ok["result"].get("isError"), ok

refused = rpc(proc, "tools/call", {"name": "validate", "arguments": {"document": bad}}, 4)
body = json.loads(refused["result"]["content"][0]["text"])
assert body["violations"], "a refusal came back with no violations"
assert body["violations"][0]["pointer"] == "/edges/0/to", body
proc.terminate()
print(f"three tools, and a refusal carrying {body['violations'][0]['pointer']}")
PY
```

## Tests

`tests/test_mcp.py`, driving the server the way the gate does rather than calling
the handlers directly — the transport is where this kind of thing breaks. Assert
the tool list, a render round-trip, and that a refusal's pointers survive
serialisation.

Skip the module if the MCP dependency is not installed, so the default `make
test` stays green without the extra.

## Location

`src/drawspec/mcp.py` (new, `python -m drawspec.mcp`), `pyproject.toml` (an
`mcp` optional-dependency group and a `drawspec-mcp` script), `tests/test_mcp.py`,
and a short section in `docs/guide.md` plus a line in `AGENTS.md` saying the
tools exist.

Depends on **B1**, which is done: `AGENTS.md` is the knowledge, this is the
delivery.

**Reassess before starting.** The gap this closes is convenience, not reach —
an agent still has to know drawspec exists. **A3** (so `pip install drawspec`
works) and **C1** (so search finds it) address that more cheaply and should land
first.

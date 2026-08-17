"""The MCP server, driven the way a client drives it: over a pipe.

**These tests spawn the process and speak JSON-RPC to it.** Calling the handlers
directly would be faster and would check almost nothing that matters — the
handlers are thin, and every failure this server can have is a transport one. A
result model that does not serialise, a field whose alias is wrong, a refusal
that escapes as an exception instead of arriving as a result: none of those are
visible from inside the process, and all of them make the server useless to the
agent it exists for.

The claim under test is the one that justified building this at all: **a refusal
arrives as located data, not as prose.** `/edges/0/to` has to survive being
turned into a `CallToolResult`, serialised, written to a pipe, and parsed at the
other end. That round trip is the test.

The module is skipped when the `mcp` extra is not installed, so `make test`
stays green for a checkout that did not ask for it.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Iterator
from typing import Any

import pytest

pytest.importorskip("mcp", reason="the MCP server is an optional extra: pip install drawspec[mcp]")

#: A document with nothing wrong with it, small enough to read.
GOOD: dict[str, Any] = {
    "version": 1,
    "kind": "flow",
    "title": "Two steps",
    "nodes": [
        {"id": "a", "text": "A step", "role": "start"},
        {"id": "b", "text": "Another", "role": "terminal"},
    ],
    "edges": [{"from": "a", "to": "b"}],
}

#: An edge pointing at a node that does not exist. Chosen because the violation
#: is *referential* — it is found by the document checks rather than by the
#: schema — so a pointer arriving intact proves the whole path, not just a type
#: check near the surface.
DANGLING: dict[str, Any] = {
    "version": 1,
    "kind": "flow",
    "nodes": [{"id": "a", "text": "A step"}],
    "edges": [{"from": "a", "to": "ghost"}],
}


class Client:
    """Enough of an MCP client to ask the questions, and no more."""

    def __init__(self, process: subprocess.Popen[str]) -> None:
        self._process = process
        self._next = 0

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._next += 1
        assert self._process.stdin is not None
        assert self._process.stdout is not None
        request = {"jsonrpc": "2.0", "id": self._next, "method": method, "params": params or {}}
        self._process.stdin.write(json.dumps(request) + "\n")
        self._process.stdin.flush()
        line = self._process.stdout.readline()
        assert line, f"the server closed the pipe instead of answering {method}"
        response: dict[str, Any] = json.loads(line)
        return response

    def tool(self, name: str, **arguments: Any) -> dict[str, Any]:
        """One `tools/call`, unwrapped to the result the server produced."""
        response = self.call("tools/call", {"name": name, "arguments": arguments})
        assert "result" in response, response
        result: dict[str, Any] = response["result"]
        return result


@pytest.fixture(scope="module")
def client() -> Iterator[Client]:
    """One initialised server for the module.

    Module-scoped because starting a process per test would dominate the run,
    and nothing here mutates server state — every tool is a pure function of its
    arguments, which is itself worth having a reason to notice if it changes.
    """
    process = subprocess.Popen(
        [sys.executable, "-m", "drawspec.mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    session = Client(process)
    handshake = session.call(
        "initialize",
        {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "drawspec-tests", "version": "0"},
        },
    )
    assert "result" in handshake, handshake
    try:
        yield session
    finally:
        process.terminate()
        process.wait(timeout=10)


def _viewbox(result: dict[str, Any]) -> float:
    """The width of a rendered SVG's canvas."""
    svg = result["content"][0]["text"]
    box = re.search(r'viewBox="([^"]+)"', svg)
    assert box, svg[:200]
    return float(box.group(1).split()[2])


def _body(result: dict[str, Any]) -> Any:
    """The JSON a tool put in its first content block."""
    content = result["content"]
    assert content, result
    return json.loads(content[0]["text"])


def test_it_lists_exactly_three_tools(client: Client) -> None:
    """Three, and the count is the assertion.

    The vocabulary being small is a design decision — an MCP layer that grows a
    tool per CLI flag becomes a second command line to document. Asserting the
    set rather than a subset makes adding a fourth a deliberate act.
    """
    listed = client.call("tools/list")
    names = {tool["name"] for tool in listed["result"]["tools"]}
    assert names == {"validate", "render", "kinds"}


def test_every_tool_describes_its_arguments(client: Client) -> None:
    """A tool with no schema is a tool an agent has to guess at."""
    listed = client.call("tools/list")
    for tool in listed["result"]["tools"]:
        assert tool["description"], tool["name"]
        assert tool["inputSchema"]["type"] == "object", tool["name"]


def test_a_good_document_validates(client: Client) -> None:
    result = client.tool("validate", document=GOOD)
    assert not result.get("isError"), result
    assert _body(result)["kind"] == "flow"


def test_a_refusal_keeps_its_json_pointer(client: Client) -> None:
    """The claim this server was built to make.

    An agent that gets `/edges/0/to` back can fix the document without parsing a
    sentence. An agent that gets a paragraph has to, and will sometimes get it
    wrong — which is the whole gap between shelling out to the CLI and this.
    """
    result = client.tool("validate", document=DANGLING)
    assert result["isError"] is True, result
    body = _body(result)
    assert body["ok"] is False
    assert body["violations"][0]["pointer"] == "/edges/0/to"
    assert "ghost" in body["violations"][0]["message"]


def test_a_refusal_always_carries_at_least_one_violation(client: Client) -> None:
    """Not every drawspec failure has pointers; every refusal here still has the shape.

    `DocumentError` carries violations, and a malformed document that is not even
    a mapping does not. A caller should not have to branch on which — so the
    empty pointer, which RFC 6901 spells as `""`, stands for the document as a
    whole.
    """
    result = client.tool("validate", document=[1, 2, 3])
    assert result["isError"] is True, result
    violations = _body(result)["violations"]
    assert violations, result
    assert violations[0]["pointer"] == ""


def test_render_returns_svg_for_the_document_it_was_given(client: Client) -> None:
    result = client.tool("render", document=GOOD)
    assert not result.get("isError"), result
    svg = result["content"][0]["text"]
    assert svg.startswith("<svg")
    assert "A step" in svg
    assert "Another" in svg


def test_render_refuses_the_same_documents_validate_refuses(client: Client) -> None:
    """One refusal surface, not two.

    A `render` that accepted what `validate` rejected — or the reverse — would
    make `validate` advice rather than an answer.
    """
    refused = client.tool("render", document=DANGLING)
    assert refused["isError"] is True, refused
    assert _body(refused)["violations"][0]["pointer"] == "/edges/0/to"


def test_width_is_applied_before_the_drawing_is_made(client: Client) -> None:
    """An override is an input to layout, not a scale factor on the output.

    Asserted as a difference between two renders rather than against a literal,
    because the canvas is the requested width *plus the theme's margin* — and the
    margin is a theme decision this test has no business pinning.
    """
    canvases = [_viewbox(client.tool("render", document=GOOD, width=width)) for width in (420, 900)]
    assert canvases[1] - canvases[0] == pytest.approx(480)


def test_kinds_names_the_whole_vocabulary(client: Client) -> None:
    """Every kind the library knows, so this cannot answer a stale list."""
    from drawspec.schema import KINDS

    result = client.tool("kinds")
    assert not result.get("isError"), result
    listed = {entry["kind"] for entry in _body(result)["kinds"]}
    assert listed == set(KINDS)
    assert all(entry["purpose"] for entry in _body(result)["kinds"])


def test_a_missing_document_argument_is_refused_in_the_same_shape(client: Client) -> None:
    """One error path for the caller, whatever went wrong."""
    result = client.tool("validate")
    assert result["isError"] is True, result
    body = _body(result)
    assert body["ok"] is False
    assert body["violations"]


def test_an_unknown_tool_says_which_tools_there_are(client: Client) -> None:
    result = client.tool("summon")
    assert result["isError"] is True, result
    said = result["content"][0]["text"]
    assert "validate" in said and "render" in said and "kinds" in said

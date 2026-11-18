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

import base64
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


def test_it_lists_exactly_five_tools(client: Client) -> None:
    """Five, one per step of writing a document, and the count is the assertion.

    The vocabulary being small is a design decision — an MCP layer that grows a
    tool per CLI flag becomes a second command line to document. Asserting the
    set rather than a subset makes adding a sixth a deliberate act.
    """
    listed = client.call("tools/list")
    names = {tool["name"] for tool in listed["result"]["tools"]}
    assert names == {
        "list_kinds",
        "get_example",
        "get_schema",
        "validate_document",
        "render_document",
    }


def test_every_tool_is_read_only(client: Client) -> None:
    """None of them writes anything, and each says so for the client to see."""
    for tool in client.call("tools/list")["result"]["tools"]:
        hints = tool["annotations"]
        assert hints["readOnlyHint"] is True, tool["name"]
        assert hints["idempotentHint"] is True, tool["name"]


def test_every_example_is_a_valid_document(client: Client) -> None:
    """`get_example` hands out documents that `validate_document` accepts."""
    from drawspec.schema import KINDS

    for kind in KINDS:
        example = client.tool("get_example", kind=kind)
        assert not example.get("isError"), example
        assert example["structuredContent"]["kind"] == kind
        checked = client.tool("validate_document", document=_body(example))
        assert not checked.get("isError"), (kind, checked)


def test_get_schema_is_one_kind_and_self_contained(client: Client) -> None:
    """A slice of the published schema an agent can read: one kind, every `$ref` resolved."""
    schema = _body(client.tool("get_schema", kind="flow"))
    assert schema["properties"]["kind"] == {"const": "flow"}
    text = json.dumps(schema)
    for name in re.findall(r'"#/\$defs/([^"]+)"', text):
        assert name in schema.get("$defs", {}), name
    assert len(text) < 20_000


def test_an_unknown_kind_is_a_refusal(client: Client) -> None:
    result = client.tool("get_example", kind="spaghetti")
    assert result["isError"] is True, result
    assert "list_kinds" in _body(result)["message"]


def test_every_tool_describes_its_arguments(client: Client) -> None:
    """A tool with no schema is a tool an agent has to guess at."""
    listed = client.call("tools/list")
    for tool in listed["result"]["tools"]:
        assert tool["description"], tool["name"]
        assert tool["inputSchema"]["type"] == "object", tool["name"]


def test_a_good_document_validates(client: Client) -> None:
    result = client.tool("validate_document", document=GOOD)
    assert not result.get("isError"), result
    assert _body(result)["kind"] == "flow"


def test_a_refusal_keeps_its_json_pointer(client: Client) -> None:
    """The claim this server was built to make.

    An agent that gets `/edges/0/to` back can fix the document without parsing a
    sentence. An agent that gets a paragraph has to, and will sometimes get it
    wrong — which is the whole gap between shelling out to the CLI and this.
    """
    result = client.tool("validate_document", document=DANGLING)
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
    result = client.tool("validate_document", document=[1, 2, 3])
    assert result["isError"] is True, result
    violations = _body(result)["violations"]
    assert violations, result
    assert violations[0]["pointer"] == ""


def test_render_returns_svg_for_the_document_it_was_given(client: Client) -> None:
    result = client.tool("render_document", document=GOOD)
    assert not result.get("isError"), result
    svg = result["content"][0]["text"]
    assert svg.startswith("<svg")
    assert "A step" in svg
    assert "Another" in svg


def test_render_returns_a_png_image_block_when_asked(client: Client) -> None:
    """`format: png` arrives as an MCP image block, base64 PNG, not as text."""
    pytest.importorskip("resvg_py", reason="PNG export is an optional extra: drawspec[png]")
    result = client.tool("render_document", document=GOOD, format="png", background="dark")
    assert not result.get("isError"), result
    block = result["content"][0]
    assert block["type"] == "image"
    assert block["mimeType"] == "image/png"
    assert base64.b64decode(block["data"]).startswith(b"\x89PNG\r\n\x1a\n")


def test_render_returns_plain_text_when_asked(client: Client) -> None:
    """`format: text` arrives as a text block, drawn to `width` in `charset`."""
    stack = {"version": 1, "kind": "stack", "items": [{"text": "Top"}, {"text": "Bottom"}]}
    result = client.tool(
        "render_document", document=stack, format="text", width=40, charset="ascii"
    )
    assert not result.get("isError"), result
    text = result["content"][0]["text"]
    assert "Top" in text and "Bottom" in text
    assert text.isascii()
    assert all(len(line) <= 40 for line in text.splitlines())


def test_a_kind_with_no_text_form_is_a_located_refusal(client: Client) -> None:
    pie = {
        "version": 1,
        "kind": "pie",
        "parts": [{"text": "A", "amount": 1}, {"text": "B", "amount": 2}],
    }
    result = client.tool("render_document", document=pie, format="text")
    assert result.get("isError"), result
    assert "`sequence`" in _body(result)["message"]


def test_a_flow_renders_as_text(client: Client) -> None:
    result = client.tool("render_document", document=GOOD, format="text")
    assert not result.get("isError"), result


def test_an_out_of_range_scale_is_a_refusal_not_a_crash(client: Client) -> None:
    result = client.tool("render_document", document=GOOD, format="png", scale=100)
    assert result["isError"] is True, result
    assert "scale" in _body(result)["message"]


def test_render_refuses_the_same_documents_validate_refuses(client: Client) -> None:
    """One refusal surface, not two.

    A `render` that accepted what `validate` rejected — or the reverse — would
    make `validate` advice rather than an answer.
    """
    refused = client.tool("render_document", document=DANGLING)
    assert refused["isError"] is True, refused
    assert _body(refused)["violations"][0]["pointer"] == "/edges/0/to"


def test_width_is_applied_before_the_drawing_is_made(client: Client) -> None:
    """An override is an input to layout, not a scale factor on the output.

    Asserted as a difference between two renders rather than against a literal,
    because the canvas is the requested width *plus the theme's margin* — and the
    margin is a theme decision this test has no business pinning.
    """
    canvases = [
        _viewbox(client.tool("render_document", document=GOOD, width=width)) for width in (420, 900)
    ]
    assert canvases[1] - canvases[0] == pytest.approx(480)


def test_kinds_names_the_whole_vocabulary(client: Client) -> None:
    """Every kind the library knows, so this cannot answer a stale list."""
    from drawspec.schema import KINDS

    result = client.tool("list_kinds")
    assert not result.get("isError"), result
    listed = {entry["kind"] for entry in _body(result)["kinds"]}
    assert listed == set(KINDS)
    assert all(entry["purpose"] for entry in _body(result)["kinds"])


def test_a_missing_document_argument_is_refused_in_the_same_shape(client: Client) -> None:
    """One error path for the caller, whatever went wrong."""
    result = client.tool("validate_document")
    assert result["isError"] is True, result
    body = _body(result)
    assert body["ok"] is False
    assert body["violations"]


def test_an_unknown_tool_says_which_tools_there_are(client: Client) -> None:
    result = client.tool("summon")
    assert result["isError"] is True, result
    said = result["content"][0]["text"]
    for name in ("list_kinds", "get_example", "get_schema", "validate_document", "render_document"):
        assert name in said


def test_the_cli_serves_the_same_server() -> None:
    """`drawspec mcp` is what the MCP Registry's `uvx --from 'drawspec[mcp]' drawspec mcp` runs."""
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "0"},
        },
    }
    done = subprocess.run(
        [sys.executable, "-c", "from drawspec.cli import main; main(['mcp'])"],
        input=json.dumps(initialize) + "\n",
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    reply = json.loads(done.stdout.splitlines()[0])
    assert reply["result"]["serverInfo"]["name"] == "drawspec"


def test_server_json_matches_the_released_package() -> None:
    """The MCP Registry publishes server.json as is, so it must name the PyPI version."""
    import tomllib
    from pathlib import Path

    from drawspec import __version__

    root = Path(__file__).parent.parent
    version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    server = json.loads((root / "server.json").read_text())
    assert server["version"] == version == __version__
    assert {p["version"] for p in server["packages"]} == {version}
    assert f"mcp-name: {server['name']}" in (root / "README.md").read_text(encoding="utf-8")


def _many_bad_edges(count: int) -> dict[str, Any]:
    return {
        "version": 1,
        "kind": "flow",
        "nodes": [{"id": "a", "text": "A step"}],
        "edges": [{"from": "a", "to": f"ghost{i}"} for i in range(count)],
    }


def test_a_bug_in_a_renderer_is_a_tool_error_not_a_protocol_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    import mcp.types as types

    from drawspec import mcp as server

    def boom(*_args: Any, **_kwargs: Any) -> str:
        raise IndexError("/secret/path")

    monkeypatch.setattr(server, "render_document", boom)
    params = types.CallToolRequestParams(name="render_document", arguments={"document": GOOD})
    result = asyncio.run(server._on_call_tool(None, params))
    assert result.is_error
    body = json.loads(result.content[0].text)  # type: ignore[union-attr]
    assert body["error"] == "InternalError"
    assert "IndexError" in body["message"] and "/secret/path" not in body["message"]


def test_a_malformed_argument_is_an_invalid_argument(client: Client) -> None:
    result = client.tool("render_document", document=GOOD, variants="dark")
    assert _body(result)["error"] == "InvalidArgument"
    result = client.tool("render_document", document=GOOD, width="wide")
    assert _body(result)["error"] == "InvalidArgument"


def test_a_refusal_lists_each_violation_once_and_caps_the_list(client: Client) -> None:
    small = _body(client.tool("validate_document", document=_many_bad_edges(1)))
    assert len(small["violations"]) == 1
    assert small["message"].startswith("the document has 1 problem")
    assert "ghost0" not in small["message"]

    big = _body(client.tool("validate_document", document=_many_bad_edges(200)))
    assert len(big["violations"]) == 50
    assert "151 omitted" in big["message"]


def test_a_theme_path_is_refused_and_does_not_say_whether_it_exists(client: Client) -> None:
    messages = set()
    for path in ("/etc/passwd", "/no/such/file.toml"):
        result = client.tool("render_document", document=GOOD, theme=path)
        assert result["isError"] is True, result
        message = _body(result)["message"]
        assert "TOML" not in message and "not found" not in message
        messages.add(message.replace(path, ""))
    assert len(messages) == 1

    own = {**GOOD, "theme": "/etc/passwd"}
    assert client.tool("validate_document", document=own)["isError"] is True
    variant = client.tool("render_document", document=GOOD, variants={"dark": "/etc/passwd"})
    assert variant["isError"] is True


def test_a_bundled_theme_still_loads(client: Client) -> None:
    from drawspec import mcp as server

    name = server._BUNDLED_THEMES[0]
    assert not client.tool("render_document", document=GOOD, theme=name).get("isError")


def test_themes_load_from_the_configured_directory_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    from drawspec import mcp as server
    from drawspec.errors import ThemeError

    inside = tmp_path / "mine.toml"
    inside.write_text("version = 1\n")
    (tmp_path / "sub").mkdir()
    monkeypatch.setenv(server.THEME_DIR_ENV, str(tmp_path))
    assert server._theme("mine.toml") == str(inside)
    for refused in ("../mine.toml", "sub/x.toml", "/etc/passwd", "absent.toml"):
        with pytest.raises(ThemeError):
            server._theme(refused)


def test_text_beyond_the_cap_is_refused_before_any_drawing(client: Client) -> None:
    from drawspec.schema import MAX_TEXT_LENGTH

    long = {**GOOD, "nodes": [{"id": "a", "text": "word " * MAX_TEXT_LENGTH}]}
    body = _body(client.tool("validate_document", document=long))
    assert body["violations"][0]["pointer"] == "/nodes/0/text"
    assert str(MAX_TEXT_LENGTH) in body["violations"][0]["message"]


def test_an_unknown_format_is_refused_not_answered_with_svg(client: Client) -> None:
    for name in ("jpeg", "PNG"):
        result = client.tool("render_document", document=GOOD, format=name)
        assert result["isError"] is True, result
        assert _body(result)["error"] == "InvalidArgument"


def test_a_document_passed_as_a_string_is_told_to_pass_the_object(client: Client) -> None:
    result = client.tool("render_document", document=json.dumps(GOOD))
    assert result["isError"] is True
    assert "not its text" in json.dumps(_body(result))


@pytest.mark.parametrize("size", [0, -5])
def test_a_size_override_must_be_positive(client: Client, size: int) -> None:
    result = client.tool("render_document", document=GOOD, width=size)
    assert _body(result)["error"] == "InvalidArgument"


def test_a_fractional_text_width_is_refused(client: Client) -> None:
    result = client.tool("render_document", document=GOOD, format="text", width=0.5)
    assert _body(result)["error"] == "InvalidArgument"
    result = client.tool("render_document", document=GOOD, format="")
    assert _body(result)["error"] == "InvalidArgument"

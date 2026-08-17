"""drawspec as three MCP tools, so an agent's refusals arrive as data.

An agent writing a document today has to shell out to `drawspec validate`,
capture stderr, and read prose to find out that `/edges/2/to` names nothing.
Those refusals are the best thing this tool produces — located, complete, one
pass is one edit — and they arrive in the one shape a program cannot use.

**That is the whole reason this module exists.** Over MCP a refusal comes back
as `{"pointer": "/edges/0/to", "message": ...}` inside the agent's own loop, and
the write-validate-fix cycle closes without a shell in it.

Three tools and deliberately not more:

======================  ====================================================
:func:`_validate`       would `render` refuse this, and where
:func:`_render`         the SVG
:func:`_kinds`          the thirteen kinds and what each is for
======================  ====================================================

**Nothing here paraphrases drawspec.** Every tool takes the document the CLI
takes and reports the violations :class:`~drawspec.schema.Violation` already
carries; `kinds` is `drawspec.examples.PURPOSE` verbatim. A layer that reworded
the refusals would be a third description of the format to keep in step with the
schema and `AGENTS.md`, which is the drift this project keeps designing out.

Run it with `python -m drawspec.mcp`, or as the `drawspec-mcp` script. It speaks
stdio, which is what every client supports; there is no HTTP transport because
nothing has asked for one.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any, Final

try:
    import anyio
    import mcp.types as types
    from mcp.server.lowlevel import Server
    from mcp.server.models import InitializationOptions
    from mcp.server.stdio import stdio_server
except ImportError as error:  # pragma: no cover - the extra is installed in CI
    # A client's configuration names `drawspec-mcp` before anything runs it, so
    # the person who sees this failure is the one who pasted the config and has
    # no reason to connect `No module named 'mcp'` to an extra they never chose.
    raise ImportError(
        "drawspec's MCP server needs its optional dependency: pip install 'drawspec[mcp]'"
    ) from error

from drawspec import __version__
from drawspec.errors import DrawspecError
from drawspec.examples import PURPOSE
from drawspec.render import render_document
from drawspec.schema import KINDS, SCHEMA_ID, Document, parse_document

#: What every tool is handed. Spelled once because all three take the same
#: thing: an agent that has learnt one call has learnt all of them.
_DOCUMENT: Final[dict[str, Any]] = {
    "type": "object",
    "description": (
        f"A drawspec document, as JSON. The full field list is published at {SCHEMA_ID}, "
        f"and `kinds` names the {len(KINDS)} values `kind` may take."
    ),
}

_THEME: Final[dict[str, Any]] = {
    "type": "string",
    "description": "A bundled theme name or a path to a theme file. Omit for the default.",
}


TOOLS: Final[tuple[types.Tool, ...]] = (
    types.Tool(
        name="validate",
        title="Validate a drawspec document",
        description=(
            "Answer whether `render` would refuse this document, and if so exactly where. "
            "Returns every violation, not the first — each located by JSON pointer, so one "
            "pass is one edit. Call this before `render` while a document is being written."
        ),
        input_schema={
            "type": "object",
            "properties": {"document": _DOCUMENT, "theme": _THEME},
            "required": ["document"],
        },
    ),
    types.Tool(
        name="render",
        title="Render a drawspec document to SVG",
        description=(
            "Draw the document and return the SVG. The output is safe to paste inline into "
            "a Markdown page: no global styles, no colliding ids, and no meaning carried by "
            "colour alone. Refuses with located violations exactly as `validate` does."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "document": _DOCUMENT,
                "theme": _THEME,
                "width": {"type": "number", "description": "Override the document's width."},
                "height": {"type": "number", "description": "Override the document's height."},
            },
            "required": ["document"],
        },
    ),
    types.Tool(
        name="kinds",
        title="List the diagram kinds",
        description=(
            "The vocabulary: every value `kind` may take and what each one is for. Takes no "
            "arguments. Read this before choosing a kind — several of them are not "
            "box-and-arrow diagrams and are easy to miss."
        ),
        input_schema={"type": "object", "properties": {}},
        annotations=types.ToolAnnotations(read_only_hint=True, idempotent_hint=True),
    ),
)


def _refusal(error: DrawspecError) -> dict[str, Any]:
    """A drawspec failure as data, in one shape whatever raised it.

    **The shape does not vary**, which is the point: `violations` is always a
    non-empty list, so a caller never has to branch on whether the failure
    happened to carry pointers. Only `DocumentError` does; a layout that will not
    fit, a theme that fails the greyscale invariant and an emitter refusal are
    all statements about the document as a whole, and RFC 6901 spells that as the
    empty pointer.
    """
    located = [
        {"pointer": violation.pointer, "message": violation.message}
        for violation in getattr(error, "violations", ())
    ]
    return {
        "ok": False,
        "error": type(error).__name__,
        "message": str(error),
        "violations": located or [{"pointer": "", "message": str(error)}],
    }


def _document(arguments: dict[str, Any]) -> Document:
    """The `document` argument, parsed and validated.

    Raises:
        DrawspecError: with every violation, the way `parse_document` does.
    """
    return parse_document(arguments["document"])


def _validate(arguments: dict[str, Any]) -> dict[str, Any]:
    """Would `render` refuse this?

    It answers that question the only way it can be answered honestly — **by
    drawing the document and throwing the drawing away**. Checking a subset of
    what drawing checks is how a validator comes to pass a document the renderer
    then rejects, which costs the author a whole round of edits. This is the same
    reasoning, and the same call, as `drawspec validate`.
    """
    document = _document(arguments)
    render_document(document, arguments.get("theme") or None)
    return {"ok": True, "kind": document.kind, "message": f"a valid {document.kind} document"}


def _render(arguments: dict[str, Any]) -> str:
    """The SVG.

    The overrides are applied to the *document*, before anything is drawn: width
    is an input to wrapping, to sizing and to the direction choice, so applying
    it afterwards would scale a picture that had already decided it fitted.
    """
    document = _document(arguments)
    if arguments.get("width") is not None:
        document = replace(document, width=float(arguments["width"]))
    if arguments.get("height") is not None:
        document = replace(document, height=float(arguments["height"]))
    return render_document(document, arguments.get("theme") or None)


def _kinds() -> dict[str, Any]:
    """The vocabulary, in `KINDS` order rather than alphabetically.

    That order groups the families — graph, grid, shape, chart — and a reader
    choosing between `flow` and `tree` is helped by their being adjacent.
    """
    return {"kinds": [{"kind": kind, "purpose": PURPOSE[kind]} for kind in KINDS]}


def _text(payload: object) -> types.CallToolResult:
    body = payload if isinstance(payload, str) else json.dumps(payload, indent=2)
    return types.CallToolResult(content=[types.TextContent(type="text", text=body)])


async def _on_list_tools(
    context: object, params: types.PaginatedRequestParams | None
) -> types.ListToolsResult:
    return types.ListToolsResult(tools=list(TOOLS))


async def _on_call_tool(
    context: object, params: types.CallToolRequestParams
) -> types.CallToolResult:
    """Dispatch, and turn a drawspec refusal into a result rather than a crash.

    **A refused document is an outcome, not a transport failure.** Letting the
    exception escape would hand the agent a protocol-level error whose text it
    would have to scrape — the exact thing this server exists to stop. So every
    `DrawspecError` comes back as `isError` with the located violations in the
    body, and only a genuine bug in drawspec propagates.
    """
    arguments = dict(params.arguments or {})
    try:
        if params.name == "validate":
            return _text(_validate(arguments))
        if params.name == "render":
            return _text(_render(arguments))
        if params.name == "kinds":
            return _text(_kinds())
    except DrawspecError as error:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=json.dumps(_refusal(error), indent=2))],
            is_error=True,
        )
    except KeyError as error:
        # A required argument was not supplied. Reported in the same shape as
        # every other refusal, so a caller has one error path.
        return types.CallToolResult(
            content=[
                types.TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "ok": False,
                            "error": "MissingArgument",
                            "message": f"{error.args[0]!r} is required",
                            "violations": [
                                {"pointer": "", "message": f"{error.args[0]!r} is required"}
                            ],
                        },
                        indent=2,
                    ),
                )
            ],
            is_error=True,
        )

    known = ", ".join(tool.name for tool in TOOLS)
    return types.CallToolResult(
        content=[
            types.TextContent(type="text", text=f"unknown tool {params.name!r}. Known: {known}.")
        ],
        is_error=True,
    )


def build_server() -> Server[None]:
    """The server, assembled but not running — so a test can inspect it."""
    return Server(
        "drawspec",
        version=__version__,
        title="drawspec",
        instructions=(
            "Write what a diagram means — nodes, edges, labels, and a semantic role for each — "
            "and drawspec decides every coordinate. Call `kinds` to choose a kind, `validate` "
            "while writing (its violations are located by JSON pointer), and `render` for the "
            f"SVG. The document format is published at {SCHEMA_ID}."
        ),
        on_list_tools=_on_list_tools,
        on_call_tool=_on_call_tool,
    )


async def serve() -> None:
    """Serve over stdio until the client goes away."""
    server = build_server()
    options: InitializationOptions = server.create_initialization_options()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options)


def main() -> None:
    """The `drawspec-mcp` script, and `python -m drawspec.mcp`."""
    anyio.run(serve)


if __name__ == "__main__":
    main()

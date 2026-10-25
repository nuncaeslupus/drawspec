"""drawspec as five MCP tools, so an agent's refusals arrive as data.

An agent writing a document today has to shell out to `drawspec validate`,
capture stderr, and read prose to find out that `/edges/2/to` names nothing.
Those refusals are the best thing this tool produces — located, complete, one
pass is one edit — and they arrive in the one shape a program cannot use.

**That is the whole reason this module exists.** Over MCP a refusal comes back
as `{"pointer": "/edges/0/to", "message": ...}` inside the agent's own loop, and
the write-validate-fix cycle closes without a shell in it.

Five tools, one per step of writing a document, and deliberately not more:

======================  ====================================================
``list_kinds``          every kind and what each is for
``get_example``         the smallest valid document of one kind
``get_schema``          one kind's fields, cut from the published schema
``validate_document``   would ``render_document`` refuse this, and where
``render_document``     the SVG, a PNG as an image block, or plain text
======================  ====================================================

**Nothing here paraphrases drawspec.** Every tool takes the document the CLI
takes and reports the violations :class:`~drawspec.schema.Violation` already
carries; `list_kinds` is `drawspec.examples.PURPOSE` verbatim, `get_example`
is `drawspec.examples.EXAMPLES` and `get_schema` a slice of the generated
schema. A layer that reworded the refusals would be a third description of the
format to keep in step with the schema and `AGENTS.md`, which is the drift this
project keeps designing out.

Run it with `python -m drawspec.mcp`, or as the `drawspec-mcp` script. It speaks
stdio, which is what every client supports; there is no HTTP transport because
nothing has asked for one.
"""

from __future__ import annotations

import base64
import json
from dataclasses import replace
from pathlib import Path
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
from drawspec import theme as _theme_module
from drawspec.errors import DrawspecError
from drawspec.examples import EXAMPLES, PURPOSE
from drawspec.export import BACKGROUNDS, DEFAULT_SCALE, MAX_SCALE, render_png
from drawspec.kinds import TEXT_KINDS
from drawspec.render import render_document, render_text
from drawspec.schema import KINDS, SCHEMA_ID, Document, build_schema, parse_document
from drawspec.textgrid import CHARSETS, DEFAULT_WIDTH, WIDE_WIDTH

#: What every tool is handed. Spelled once because the document tools all take
#: the same thing: an agent that has learnt one call has learnt all of them.
_DOCUMENT: Final[dict[str, Any]] = {
    "type": "object",
    "description": (
        "A drawspec document as a JSON object (not a string or a path), e.g. "
        '`{"version": 1, "kind": "flow", "nodes": [...], "edges": [...]}`. '
        f"`list_kinds` names the {len(KINDS)} values `kind` may take, `get_example` returns "
        "the smallest valid document of one, and `get_schema` returns its fields (the whole "
        f"format is published at {SCHEMA_ID})."
    ),
}

#: The themes shipped inside the package, by the name `theme` accepts.
_BUNDLED_THEMES: Final[tuple[str, ...]] = tuple(
    sorted(path.stem for path in (Path(_theme_module.__file__).parent / "themes").glob("*.toml"))
)

_THEME: Final[dict[str, Any]] = {
    "type": "string",
    "description": (
        f"A bundled theme name ({', '.join(_BUNDLED_THEMES)}) or a path to a `.toml` theme "
        "file on the server's disk, e.g. `blueprint`. Omit for `default`."
    ),
}

_KIND: Final[dict[str, Any]] = {
    "type": "string",
    "enum": list(KINDS),
    "description": "A diagram kind, exactly as `list_kinds` names it, e.g. `flow`.",
}

#: Every tool reads its arguments and writes nothing: calling one twice with the
#: same arguments returns the same answer and changes nothing anywhere.
_READ_ONLY: Final = types.ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)

#: What a refused call returns, in the description's words. One shape for every
#: tool, so a caller has one error path.
_REFUSAL_SHAPE: Final[str] = (
    "Refusals are error results with JSON text "
    '`{"ok": false, "error": "DocumentError", "message": "...", '
    '"violations": [{"pointer": "/edges/0/to", "message": "..."}]}`: '
    "`error` is e.g. `DocumentError` or `FitError`, `pointer` is RFC 6901 (empty for the "
    "whole document), and `violations` is never empty."
)


TOOLS: Final[tuple[types.Tool, ...]] = (
    types.Tool(
        name="list_kinds",
        title="List the diagram kinds",
        description=(
            f"List the vocabulary: all {len(KINDS)} values `kind` may take, each with a "
            "one-line purpose. Call it first, before choosing a kind — several kinds are not "
            "box-and-arrow diagrams and are easy to miss — then `get_example` for a starting "
            "document. No arguments. Static and local: no I/O, about 4 KB, the same "
            "answer every call, in a fixed order that keeps related kinds (graphs, grids, "
            "shapes, charts) adjacent."
        ),
        input_schema={"type": "object", "properties": {}},
        output_schema={
            "type": "object",
            "properties": {
                "kinds": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"kind": {"type": "string"}, "purpose": {"type": "string"}},
                        "required": ["kind", "purpose"],
                    },
                }
            },
            "required": ["kinds"],
        },
        annotations=_READ_ONLY,
    ),
    types.Tool(
        name="get_example",
        title="Get an example document of one kind",
        description=(
            "Get the smallest valid document of one kind, as JSON ready to edit: the fastest "
            "way to the right field names. `kind` is one exact value from `list_kinds`, e.g. "
            "`flow`. Use it after `list_kinds` has settled the kind, and `get_schema` only for "
            "a field the example leaves out. Static and local: the document `drawspec example "
            "<kind>` prints, under 1 KB, identical every call; it passes `validate_document` "
            "as is. An unknown kind is an error result naming `list_kinds`."
        ),
        input_schema={
            "type": "object",
            "properties": {"kind": _KIND},
            "required": ["kind"],
        },
        output_schema={"type": "object", "description": "A drawspec document."},
        annotations=_READ_ONLY,
    ),
    types.Tool(
        name="get_schema",
        title="Get the JSON Schema for one kind",
        description=(
            "Get the JSON Schema (draft 2020-12) for one kind's documents: every field it "
            "accepts, with types, limits and descriptions, plus only the shared `$defs` it "
            "refers to. `kind` is one value from `list_kinds`, e.g. `sequence`. Use it when "
            "`get_example` does not show a field you need. Local and deterministic: 3 to 13 KB "
            "per kind, cut from the ~150 KB published schema. Referential rules (unique ids, "
            "edges that land on real nodes) are beyond JSON Schema — `validate_document` "
            "checks those."
        ),
        input_schema={
            "type": "object",
            "properties": {"kind": _KIND},
            "required": ["kind"],
        },
        output_schema={"type": "object", "description": "A JSON Schema (draft 2020-12)."},
        annotations=_READ_ONLY,
    ),
    types.Tool(
        name="validate_document",
        title="Validate a drawspec document",
        description=(
            "Check whether `render_document` would refuse this document, and exactly where. "
            "It renders with the same `theme` and discards the drawing, so it passes only "
            "what draws; every violation comes back at once, so one pass is one edit. Call "
            "it while writing or editing; skip it when about to render anyway, since "
            "`render_document` refuses in the same shape. Local, deterministic, milliseconds. "
            + _REFUSAL_SHAPE
        ),
        input_schema={
            "type": "object",
            "properties": {"document": _DOCUMENT, "theme": _THEME},
            "required": ["document"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
                "kind": {"type": "string"},
                "message": {"type": "string"},
            },
            "required": ["ok", "kind", "message"],
        },
        annotations=_READ_ONLY,
    ),
    types.Tool(
        name="render_document",
        title="Render a drawspec document to SVG, PNG or text",
        description=(
            "Draw the document. Use it when it is ready to show; while still fixing errors, "
            "`validate_document` returns just the verdict. Returns one content block by "
            "`format`: `svg` (default) self-contained SVG text, safe inline in Markdown; "
            "`png` a base64 `image/png` block (needs the server's `drawspec[png]` extra, "
            "slowest); `text` plain text for a code block, only for kinds with a text form. "
            "`width`/`height` override the document's size; with `text`, `width` is cells per "
            "line and `height` and `theme` are ignored. Local, deterministic, writes nothing. "
            + _REFUSAL_SHAPE
        ),
        input_schema={
            "type": "object",
            "properties": {
                "document": _DOCUMENT,
                "theme": _THEME,
                "width": {
                    "type": "number",
                    "description": (
                        "Override the document's width, e.g. `640`. With format `text`, the "
                        f"most terminal cells a line may take (default {DEFAULT_WIDTH}, or "
                        f"{WIDE_WIDTH} for `lanes`, `sequence` and `timing`)."
                    ),
                },
                "height": {
                    "type": "number",
                    "description": "Override the document's height (ignored with format `text`).",
                },
                "format": {
                    "type": "string",
                    "enum": ["svg", "png", "text"],
                    "description": (
                        "svg (default), png, or text: the diagram as plain text for a code "
                        f"block or a terminal, for the kinds {', '.join(TEXT_KINDS)}."
                    ),
                },
                "charset": {
                    "type": "string",
                    "enum": list(CHARSETS),
                    "description": "text only: box-drawing characters, or ASCII only "
                    "(default unicode).",
                },
                "scale": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                    "maximum": MAX_SCALE,
                    "description": f"png only: pixels per SVG unit (default {DEFAULT_SCALE:g}).",
                },
                "background": {
                    "type": "string",
                    "enum": list(BACKGROUNDS),
                    "description": "png only: the page the drawing is on (default light).",
                },
                "variants": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": (
                        "svg only: more themes for the same drawing, by the name a page "
                        'selects each with, e.g. `{"dark": "./dark.toml"}`. The SVG '
                        "switches on an ancestor's `data-theme`, and `dark` also follows "
                        "`prefers-color-scheme`; `theme` is the base and answers to `light`. "
                        "A variant may change colours only."
                    ),
                },
            },
            "required": ["document"],
        },
        annotations=_READ_ONLY,
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


def _render(arguments: dict[str, Any]) -> str | bytes:
    """The SVG, or the PNG or the plain text when `format` asks for one.

    The overrides are applied to the *document*, before anything is drawn: width
    is an input to wrapping, to sizing and to the direction choice, so applying
    it afterwards would scale a picture that had already decided it fitted.
    """
    document = _document(arguments)
    variants = arguments.get("variants") or None
    if variants and arguments.get("format", "svg") != "svg":
        raise DrawspecError("`variants` applies to format svg only")
    if arguments.get("format") == "text":
        width = arguments.get("width")
        return render_text(
            document,
            width=None if width is None else int(width),
            charset=str(arguments.get("charset", "unicode")),
        )
    if arguments.get("width") is not None:
        document = replace(document, width=float(arguments["width"]))
    if arguments.get("height") is not None:
        document = replace(document, height=float(arguments["height"]))
    if arguments.get("format", "svg") == "png":
        return render_png(
            document,
            arguments.get("theme") or None,
            scale=float(arguments.get("scale", DEFAULT_SCALE)),
            background=str(arguments.get("background", "light")),
        )
    return render_document(document, arguments.get("theme") or None, variants=variants)


def _kinds() -> dict[str, Any]:
    """The vocabulary, in `KINDS` order rather than alphabetically.

    That order groups the families — graph, grid, shape, chart — and a reader
    choosing between `flow` and `tree` is helped by their being adjacent.
    """
    return {"kinds": [{"kind": kind, "purpose": PURPOSE[kind]} for kind in KINDS]}


def _kind(arguments: dict[str, Any]) -> str:
    """The `kind` argument, checked: an unknown kind is the arguments' fault."""
    kind = str(arguments["kind"])
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}; `list_kinds` names the {len(KINDS)} kinds")
    return kind


def _example(arguments: dict[str, Any]) -> dict[str, Any]:
    """The smallest document of one kind — the same one `drawspec example` prints."""
    return dict(EXAMPLES[_kind(arguments)])


def _schema(arguments: dict[str, Any]) -> dict[str, Any]:
    """One kind's branch of the published schema, with only the definitions it uses.

    The whole schema is some two hundred thousand characters, most of it about
    kinds the caller is not writing. The branch is cut from the same generated
    schema the file is, so the two cannot disagree; the `$defs` it needs are
    followed transitively through `$ref`, since a definition may refer to another.
    """
    kind = _kind(arguments)
    full = build_schema()
    branch = next(v for v in full["oneOf"] if kind in v["properties"]["kind"]["enum"])
    branch = {**branch, "properties": {**branch["properties"], "kind": {"const": kind}}}
    branch.pop("title", None)
    definitions: dict[str, Any] = full["$defs"]
    needed: dict[str, Any] = {}
    pending = _refs(branch)
    while pending:
        name = pending.pop()
        if name not in needed:
            needed[name] = definitions[name]
            pending |= _refs(definitions[name])
    schema = {
        "$schema": full["$schema"],
        "$id": SCHEMA_ID,
        "title": f"drawspec {kind} document",
        "description": full["description"],
        **branch,
    }
    if needed:
        schema["$defs"] = dict(sorted(needed.items()))
    return schema


def _refs(node: object) -> set[str]:
    """The `$defs` names a schema fragment refers to, directly."""
    if isinstance(node, dict):
        found = set()
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            found.add(ref.removeprefix("#/$defs/"))
        for value in node.values():
            found |= _refs(value)
        return found
    if isinstance(node, list):
        return set().union(*(_refs(item) for item in node)) if node else set()
    return set()


def _image(png: bytes) -> types.CallToolResult:
    data = base64.b64encode(png).decode("ascii")
    return types.CallToolResult(
        content=[types.ImageContent(type="image", data=data, mime_type="image/png")]
    )


def _text(payload: object) -> types.CallToolResult:
    if isinstance(payload, str):
        return types.CallToolResult(content=[types.TextContent(type="text", text=payload)])
    # A JSON answer goes out twice: as text for clients that read only content,
    # and as structured content matching the tool's `output_schema`.
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=json.dumps(payload, indent=2))],
        structured_content=payload if isinstance(payload, dict) else None,
    )


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
        if params.name == "validate_document":
            return _text(_validate(arguments))
        if params.name == "render_document":
            rendered = _render(arguments)
            return _image(rendered) if isinstance(rendered, bytes) else _text(rendered)
        if params.name == "list_kinds":
            return _text(_kinds())
        if params.name == "get_example":
            return _text(_example(arguments))
        if params.name == "get_schema":
            return _text(_schema(arguments))
    except DrawspecError as error:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=json.dumps(_refusal(error), indent=2))],
            is_error=True,
        )
    except ValueError as error:
        # An out-of-range `scale`, an unknown `background` or `kind`: the arguments,
        # not the document, so there is nothing to locate.
        message = str(error)
        return types.CallToolResult(
            content=[
                types.TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "ok": False,
                            "error": "InvalidArgument",
                            "message": message,
                            "violations": [{"pointer": "", "message": message}],
                        },
                        indent=2,
                    ),
                )
            ],
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
            "and drawspec decides every coordinate. Call `list_kinds` to choose a kind, "
            "`get_example` for a starting document (`get_schema` for every field), "
            "`validate_document` while writing (its violations are located by JSON pointer), "
            f"and `render_document` for the SVG. The document format is published at {SCHEMA_ID}."
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

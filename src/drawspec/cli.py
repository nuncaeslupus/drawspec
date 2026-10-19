"""The command line: six commands, and an exit code that means something.

The contract is specification §5.4, and the exit codes are the part of it that a
build script actually consumes:

======  ==========================================================
``0``   it worked
``1``   the document, the theme or the fit was refused
``2``   the command line itself was wrong
======  ==========================================================

The split between 1 and 2 is worth stating: **2 is about the invocation, 1 is
about the content**. A misspelt flag or an unknown profile is 2 — nothing was
read, so nothing can be said about it. A document that cannot be read, cannot be
parsed, or cannot be fitted is 1, and its message goes to stderr in full, because
a refusal is an outcome and the message is the product. Nothing is printed to
stdout but the thing that was asked for: the SVG, the schema, or a one-line
confirmation. That is what makes `drawspec render doc.json > doc.svg` safe.

`validate` is the validator the specification promises: it prints every
violation with its JSON pointer, so a failure names the exact location and the
exact field the way an HTML validator names a line and an attribute. Every
violation, not the first — one pass should be one edit.

**One pass being one edit is why `validate` draws the document and discards it.**
Its answer is "would `render` refuse this?", not "does this satisfy the schema",
because a validator that passes what the renderer then rejects has spent the
author's round of edits for nothing — which is exactly what two groups sharing
one member used to do.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Final, TextIO

from drawspec import __version__
from drawspec.brand import derive_theme
from drawspec.emit import PROFILES
from drawspec.errors import DocumentError, DrawspecError, ThemeError
from drawspec.examples import EXAMPLES, PURPOSE
from drawspec.export import BACKGROUNDS, DEFAULT_SCALE, MAX_SCALE, render_png
from drawspec.kinds import TEXT_KINDS
from drawspec.render import render_document, render_text
from drawspec.schema import KINDS, Document, load_document, parse_document, schema_json
from drawspec.textgrid import CHARSETS, DEFAULT_WIDTH, WIDE_WIDTH
from drawspec.theme import load_theme

#: The conventional name for standard input, as a document argument. Reading a
#: document from a pipe is what makes `example` and `validate` compose, which is
#: how a caller with no files yet checks that its toolchain works.
STDIN: Final = "-"

#: What the shell gets back. Named, because these are the contract.
#: What `render --format` accepts, and the extension each is inferred from.
FORMATS: Final = ("svg", "png", "text")
EXTENSIONS: Final = {".svg": "svg", ".png": "png", ".txt": "text"}

OK: Final = 0
REFUSED: Final = 1
USAGE: Final = 2


def build_parser() -> argparse.ArgumentParser:
    """Every command in §5.4, and nothing that is not in it."""
    parser = argparse.ArgumentParser(
        prog="drawspec",
        description="Render a declarative diagram specification to SVG.",
    )
    parser.add_argument("--version", action="version", version=f"drawspec {__version__}")
    commands = parser.add_subparsers(dest="command")

    render = commands.add_parser(
        "render",
        help="render a document to SVG, PNG or plain text",
        description=(
            "Read a document, draw it, and write the SVG to stdout or to a file. "
            "With --format png, or an -o ending in .png, write a PNG instead "
            "(needs pip install 'drawspec[png]'). With --format text, or an -o ending in "
            ".txt, write the diagram as plain text, refused when it is wider than --width."
        ),
    )
    render.add_argument("document", help="the document to render")
    render.add_argument("-o", "--out", help="write here instead of stdout")
    render.add_argument("--theme", help="a bundled theme name or a theme file")
    render.add_argument(
        "--variant",
        action="append",
        metavar="NAME=THEME",
        help=(
            "for svg: also draw the diagram in THEME, switched on by an ancestor's "
            "data-theme=NAME (and, for NAME dark, by prefers-color-scheme). Repeatable. "
            "--theme is the base and answers to light"
        ),
    )
    render.add_argument(
        "--width",
        type=float,
        help=(
            "override the document's width; with --format text, the most terminal cells a "
            f"line may take (default {DEFAULT_WIDTH}, or {WIDE_WIDTH} for lanes and sequence)"
        ),
    )
    render.add_argument("--height", type=float, help="override the document's height")
    render.add_argument(
        "--profile", choices=PROFILES, default="inline", help="the embedding profile"
    )
    render.add_argument(
        "--format",
        choices=FORMATS,
        help=(
            "what to write: svg; png, a raster image of the standalone drawing; or text, the "
            f"diagram as plain text for a code block or a terminal ({', '.join(TEXT_KINDS)}). "
            "Default: from the -o extension, else svg"
        ),
    )
    render.add_argument(
        "--charset",
        choices=CHARSETS,
        help="for text: box-drawing characters, or ASCII only (default unicode)",
    )
    render.add_argument(
        "--scale",
        type=_scale,
        help=f"for png: pixels per SVG unit, at most {MAX_SCALE:g} (default {DEFAULT_SCALE:g})",
    )
    render.add_argument(
        "--background",
        choices=BACKGROUNDS,
        help="for png: theme ink on white, light ink on near-black, or no page (default light)",
    )

    validate = commands.add_parser(
        "validate",
        help="validate a document without rendering it",
        description=(
            "Parse and check a document, drawing nothing. Every violation is printed "
            "with the JSON pointer of the place it was written."
        ),
    )
    validate.add_argument("document", help="the document to validate")
    validate.add_argument("--theme", help="a bundled theme name or a theme file")

    theme = commands.add_parser(
        "theme", help="theme tools", description="Tools for the files that decide appearance."
    )
    theme_commands = theme.add_subparsers(dest="theme_command")
    check = theme_commands.add_parser(
        "check",
        help="run a theme's invariants",
        description=("Load a theme and run its invariants, the greyscale role pairing included."),
    )
    check.add_argument("theme", help="a bundled theme name or a theme file")
    derive = theme_commands.add_parser(
        "from",
        help="derive a theme from a brand's CSS or design tokens",
        description=(
            "Read CSS custom properties (a .css file) or W3C design tokens (a .json or "
            ".tokens file) and write the theme they map onto, as TOML. Fonts, the accent "
            "and muted colours, a corner radius and a stroke weight are taken; every token "
            "left out is reported on stderr with the reason. A colour that would not read "
            "at 3:1 on both a white and a near-black page is darkened or lightened until it "
            "does. Local files only: no URL is fetched."
        ),
    )
    derive.add_argument(
        "brand", nargs="+", help="a .css or design-tokens file; a later file wins a tie"
    )
    derive.add_argument("-o", "--out", help="write here instead of stdout")
    derive.add_argument("--name", help="the theme's name; the first file's name by default")
    derive.add_argument(
        "--strict",
        action="store_true",
        help="refuse a colour that would need adjusting, instead of adjusting it",
    )

    schema = commands.add_parser(
        "schema",
        help="write the document JSON Schema",
        description="Write the published document JSON Schema, for editor completion.",
    )
    schema.add_argument("--out", help="write here instead of stdout")

    # `kinds` and `example` are the pair that lets a reader with no documentation
    # to hand find out what a document looks like. `schema` already answers
    # "what is legal", exhaustively and at thirty thousand characters; these
    # answer "what do I write", which is a different question and the one asked
    # first.
    commands.add_parser(
        "kinds",
        help="list the diagram kinds and what each is for",
        description="One line per kind: the claim that kind of diagram makes.",
    )

    example = commands.add_parser(
        "example",
        help="write a minimal valid document of a given kind",
        description=(
            "Write the smallest document of that kind that renders, to stdout. "
            "Pipe it straight back in: drawspec example flow | drawspec validate -"
        ),
    )
    example.add_argument("kind", choices=KINDS, help="which kind to write")

    # The same server as `drawspec-mcp`, reachable as `drawspec mcp` so a launcher
    # that can only run the package's own command (`uvx --from 'drawspec[mcp]'
    # drawspec mcp`, the MCP Registry's entry) gets to it too.
    commands.add_parser(
        "mcp",
        help="serve validate, render and kinds as MCP tools over stdio",
        description="The MCP server; needs the extra: pip install 'drawspec[mcp]'.",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one command and return its exit code.

    Returns rather than exits, and catches argparse's own `SystemExit`, so the
    codes in §5.4 are testable as values instead of as process outcomes.
    """
    parser = build_parser()
    try:
        arguments = parser.parse_args(argv)
    except SystemExit as exit_code:  # argparse's own usage failure
        return USAGE if exit_code.code else OK

    if arguments.command is None:
        parser.print_usage(sys.stderr)
        print("drawspec: a command is required", file=sys.stderr)
        return USAGE

    if arguments.command == "render":
        return _render(arguments)
    if arguments.command == "validate":
        return _validate(arguments)
    if arguments.command == "kinds":
        return _kinds()
    if arguments.command == "mcp":
        from drawspec.mcp import main as serve_mcp

        serve_mcp()
        return OK
    if arguments.command == "example":
        return _example(arguments)
    if arguments.command == "theme":
        command = getattr(arguments, "theme_command", None)
        if command == "from":
            return _theme_from(arguments)
        if command != "check":
            parser.print_usage(sys.stderr)
            print("drawspec: theme takes one of two commands: check, from", file=sys.stderr)
            return USAGE
        return _theme_check(arguments)
    return _schema(arguments)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def _render(arguments: argparse.Namespace) -> int:
    """Document in, SVG (or PNG, or text) out, with the overrides applied first.

    The overrides are applied to the *document*, not to the finished drawing:
    width is an input to wrapping, sizing and the direction choice, so overriding
    it after the fact would scale a picture that had already decided it fitted.

    The format is the flag when given, and otherwise the `-o` extension, so
    `-o diagram.png` does what it says. A flag that contradicts the extension is
    a usage error rather than a file whose name lies about its contents.
    """
    output_format = _output_format(arguments)
    if output_format is None:
        return USAGE
    if output_format != "png" and (arguments.scale is not None or arguments.background):
        print("drawspec: --scale and --background apply to --format png only", file=sys.stderr)
        return USAGE
    if output_format != "svg" and arguments.variant:
        print("drawspec: --variant applies to --format svg only", file=sys.stderr)
        return USAGE
    variants: dict[str, str] = {}
    for pair in arguments.variant or ():
        name, equals, source = pair.partition("=")
        if not (equals and name and source):
            print(f"drawspec: --variant takes NAME=THEME; got {pair!r}", file=sys.stderr)
            return USAGE
        if name in variants:
            print(f"drawspec: --variant {name!r} is given twice", file=sys.stderr)
            return USAGE
        variants[name] = source
    if output_format != "text" and arguments.charset:
        print("drawspec: --charset applies to --format text only", file=sys.stderr)
        return USAGE
    if (
        output_format == "text"
        and arguments.width is not None
        and (arguments.width < 1 or arguments.width != int(arguments.width))
    ):
        print("drawspec: with --format text, --width is a whole number of columns", file=sys.stderr)
        return USAGE
    if output_format == "png" and not arguments.out and sys.stdout.isatty():
        print(
            "drawspec: a PNG is binary and stdout is a terminal; pass -o file.png "
            "or redirect the output",
            file=sys.stderr,
        )
        return USAGE

    try:
        document = _read(arguments.document)
        if arguments.width is not None and output_format != "text":
            document = replace(document, width=arguments.width)
        if arguments.height is not None:
            document = replace(document, height=arguments.height)
        if output_format == "png":
            image = render_png(
                document,
                arguments.theme,
                scale=DEFAULT_SCALE if arguments.scale is None else arguments.scale,
                background=arguments.background or "light",
            )
        elif output_format == "text":
            svg = render_text(
                document,
                width=None if arguments.width is None else int(arguments.width),
                charset=arguments.charset or "unicode",
            ).rstrip("\n")
        else:
            svg = render_document(
                document, arguments.theme, arguments.profile, variants=variants or None
            )
    except DrawspecError as error:
        return _refuse(error)

    if output_format == "png":
        if arguments.out:
            Path(arguments.out).write_bytes(image)
        else:
            sys.stdout.buffer.write(image)
            sys.stdout.flush()
        return OK
    if arguments.out:
        Path(arguments.out).write_text(svg, encoding="utf-8")
    else:
        print(svg)
    return OK


def _output_format(arguments: argparse.Namespace) -> str | None:
    """The format `render` writes, or None after reporting a contradiction."""
    inferred = EXTENSIONS.get(Path(arguments.out).suffix.lower()) if arguments.out else None
    chosen: str | None = arguments.format
    if chosen and inferred and chosen != inferred:
        print(
            f"drawspec: --format {chosen} contradicts -o {arguments.out}; "
            f"name the file .{'txt' if chosen == 'text' else chosen} or drop --format",
            file=sys.stderr,
        )
        return None
    return chosen or inferred or "svg"


def _scale(value: str) -> float:
    """`--scale`, refused by argparse when it is not a usable factor."""
    try:
        scale = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number: {value!r}") from None
    if not 0 < scale <= MAX_SCALE:
        raise argparse.ArgumentTypeError(f"must be above 0 and at most {MAX_SCALE:g}")
    return scale


def _validate(arguments: argparse.Namespace) -> int:
    """Every refusal `render` has, and none of its output.

    **`validate` answers "would `render` refuse this?"** — so it draws the
    document and throws the drawing away, rather than re-checking a subset of
    what drawing checks. It used to parse the schema and stop, which meant it
    could hand back *a valid flow document* for a document `render` then refused:
    two groups claiming one member validated and failed to draw, because the
    containment check lives where the containment is built. Every check that a
    kind, a layout, a fit or the emitter makes is now on this path, and there is
    no list of them here to fall out of step with the ones that exist.

    A named theme is checked too, because a theme that will not load is a reason
    this document cannot be rendered — but it is not loaded twice: `render_document`
    resolves and loads whatever theme it is handed, so passing the name through is
    the whole of it.
    """
    try:
        document = _read(arguments.document)
        render_document(document, arguments.theme or None)
    except DocumentError as error:
        return _refuse(error)
    except DrawspecError as error:
        return _refuse(error)

    name = "stdin" if arguments.document == STDIN else arguments.document
    print(f"{name}: a valid {document.kind} document")
    return OK


def _kinds() -> int:
    """The vocabulary, one line each.

    Ordered by `KINDS` rather than alphabetically, because that order groups the
    families — graph, grid, shape, chart — and a reader choosing between `flow`
    and `tree` is helped by their being adjacent.
    """
    width = max(len(kind) for kind in KINDS)
    for kind in KINDS:
        print(f"{kind:<{width}}  {PURPOSE[kind]}")
    return OK


def _example(arguments: argparse.Namespace) -> int:
    """The smallest document of one kind, on stdout, ready to be edited.

    Two spaces and a trailing newline, so the output is a file rather than a
    blob: the expected next move is `drawspec example flow > diagram.json`.
    """
    print(json.dumps(EXAMPLES[arguments.kind], indent=2))
    return OK


def _read(source: str) -> Document:
    """A document from a path, or from stdin when the path is `-`.

    Reading a pipe is what makes the commands compose — `drawspec example flow |
    drawspec validate -` is how a caller with no files yet confirms the toolchain
    works before writing anything. Malformed JSON on stdin is refused with the
    same message a file gets, minus a path it does not have.
    """
    if source != STDIN:
        return load_document(source)
    text = sys.stdin.read()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as error:
        raise DocumentError(f"document is not valid JSON: stdin ({error})", ()) from None
    return parse_document(parsed)


def _theme_check(arguments: argparse.Namespace) -> int:
    """The theme's invariants, greyscale pairing included.

    `load_theme` already refuses an ambiguous theme — the check is not something
    a caller can forget to run — so this reports what it raised rather than
    re-implementing the comparison, and prints the pair count when it loads.
    """
    try:
        theme = load_theme(arguments.theme)
    except ThemeError as error:
        return _refuse(error)

    ambiguous = theme.ambiguous_role_pairs()
    if ambiguous:  # unreachable through load_theme, and cheap insurance if it changes
        for first, second in ambiguous:
            print(f"{first} and {second} differ only by colour", file=sys.stderr)
        return REFUSED
    print(f"{theme.name}: {len(ambiguous)} ambiguous role pairs")
    return OK


def _theme_from(arguments: argparse.Namespace) -> int:
    """A brand's tokens in, a theme out, and a line on stderr for every token.

    The theme is the thing asked for, so it alone goes to stdout; the report is
    about how it was made, and goes beside it. A URL is a usage error rather than
    a refusal — nothing was read — and drawspec never fetches one.
    """
    for brand in arguments.brand:
        if re.match(r"^[a-z][a-z0-9+.-]*://", brand, re.IGNORECASE):
            print(
                f"drawspec: {brand} is a URL. theme from reads local files only and makes "
                f"no network request; save the stylesheet or tokens file and pass its path.",
                file=sys.stderr,
            )
            return USAGE
    try:
        derived = derive_theme(arguments.brand, arguments.name, strict=arguments.strict)
    except ThemeError as error:
        return _refuse(error)

    print(derived.report, file=sys.stderr)
    if arguments.out:
        Path(arguments.out).write_text(derived.toml, encoding="utf-8")
    else:
        sys.stdout.write(derived.toml)
    return OK


def _schema(arguments: argparse.Namespace) -> int:
    text = schema_json()
    if arguments.out:
        Path(arguments.out).write_text(text, encoding="utf-8")
    else:
        print(text)
    return OK


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def _refuse(error: DrawspecError, stream: TextIO | None = None) -> int:
    """Print a refusal in full, to stderr, and return the code for it.

    In full: the message a drawspec error carries names the remedy as well as the
    fault, and truncating it to a summary line is how an author ends up guessing.

    A `DocumentError`'s message already carries every located violation — that is
    what `_describe` builds it from — so printing `error.violations` as well is
    how each one came out twice. One pass over the output should be one edit, and
    that is not true of a list a reader has to notice is doubled.
    """
    out = stream or sys.stderr
    print(str(error), file=out)
    return REFUSED


if __name__ == "__main__":
    sys.exit(main())

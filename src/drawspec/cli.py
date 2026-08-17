"""The command line: four commands, and an exit code that means something.

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
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Final, TextIO

from drawspec import __version__
from drawspec.emit import PROFILES
from drawspec.errors import DocumentError, DrawspecError, ThemeError
from drawspec.examples import EXAMPLES, PURPOSE
from drawspec.render import render_document
from drawspec.schema import KINDS, Document, load_document, parse_document, schema_json
from drawspec.theme import load_theme

#: The conventional name for standard input, as a document argument. Reading a
#: document from a pipe is what makes `example` and `validate` compose, which is
#: how a caller with no files yet checks that its toolchain works.
STDIN: Final = "-"

#: What the shell gets back. Named, because these are the contract.
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
        help="render a document to SVG",
        description="Read a document, draw it, and write the SVG to stdout or to a file.",
    )
    render.add_argument("document", help="the document to render")
    render.add_argument("-o", "--out", help="write here instead of stdout")
    render.add_argument("--theme", help="a bundled theme name or a theme file")
    render.add_argument("--width", type=float, help="override the document's width")
    render.add_argument("--height", type=float, help="override the document's height")
    render.add_argument(
        "--profile", choices=PROFILES, default="inline", help="the embedding profile"
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
    if arguments.command == "example":
        return _example(arguments)
    if arguments.command == "theme":
        if getattr(arguments, "theme_command", None) != "check":
            parser.print_usage(sys.stderr)
            print("drawspec: theme takes one command: check", file=sys.stderr)
            return USAGE
        return _theme_check(arguments)
    return _schema(arguments)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def _render(arguments: argparse.Namespace) -> int:
    """Document in, SVG out, with the overrides applied before anything is drawn.

    The overrides are applied to the *document*, not to the finished drawing:
    width is an input to wrapping, sizing and the direction choice, so overriding
    it after the fact would scale a picture that had already decided it fitted.
    """
    try:
        document = _read(arguments.document)
        if arguments.width is not None:
            document = replace(document, width=arguments.width)
        if arguments.height is not None:
            document = replace(document, height=arguments.height)
        svg = render_document(document, arguments.theme, arguments.profile)
    except DrawspecError as error:
        return _refuse(error)

    if arguments.out:
        Path(arguments.out).write_text(svg, encoding="utf-8")
    else:
        print(svg)
    return OK


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

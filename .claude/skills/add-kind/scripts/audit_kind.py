#!/usr/bin/env python3
"""Report every place a drawspec kind should appear and does not.

A kind is wired into the code at about a dozen points and described in about
ten documents; the repository rule is that one pull request touches all of
them. This script checks each by reading the files as text, so it needs no
install and no import of drawspec.

    audit_kind.py neuralnet
    audit_kind.py neuralnet --repo-root path/to/drawspec

Exit: 0 when nothing is missing, 1 when something is, 2 on a usage error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

UNITS = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
]
TENS = ["_", "_", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]

#: Documents that describe every kind, so each must name a new one.
DOCUMENTS = (
    "README.md",
    "docs/guide.md",
    "docs/format.md",
    "AGENTS.md",
    "CHANGELOG.md",
    "docs/proposals/README.md",
    "schema/drawspec-v1.schema.json",
)

#: Where the number of kinds is written in words, as a pattern around the word.
COUNTS = (
    ("src/drawspec/schema.py", r"Which of the {word} diagrams"),
    ("docs/guide.md", r"{word} exist"),
    ("llms.txt", r"{word} diagram"),
    ("docs/proposals/README.md", r'"{word} diagrams"'),
)


def spelt(number: int) -> str:
    """`number` in words as the documents write it: `forty-seven`."""
    if number < 20:
        return UNITS[number]
    tens, units = divmod(number, 10)
    return TENS[tens] + (f"-{UNITS[units]}" if units else "")


def read(root: Path, name: str) -> str:
    path = root / name
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def audit(root: Path, kind: str) -> tuple[list[str], list[str]]:
    """The missing pieces (failures) and the thin ones (warnings) for `kind`."""
    missing: list[str] = []
    thin: list[str] = []
    schema = read(root, "src/drawspec/schema.py")
    found = re.search(
        rf'^([A-Z_]+_KINDS): Final = \(([^)]*"{re.escape(kind)}"[^)]*)\)', schema, re.M
    )
    if not found:
        return [f'src/drawspec/schema.py: no `*_KINDS: Final = ("{kind}", ...)` constant'], []
    const = found.group(1)
    # A kind in a family of its own is wired at every point below; one sharing an
    # older family (`flow` and `tree` in GRAPH_KINDS) is wired through it instead.
    alone = found.group(2).count('"') == 2
    code = {
        "src/drawspec/schema.py": [
            (rf"\+ {const}\b", f"`+ {const}` in the KINDS tuple"),
            (rf'^    "{kind}": \(', f'READABILITY_BUDGET entry `"{kind}": (...)`'),
            (rf"^    {const}: \(", f"KIND_PAYLOADS entry `{const}: (...)`"),
            (rf'\("{kind}", {const}\)', f'Document.family entry `("{kind}", {const})`'),
            (rf"if kind in {const}:", f"a validation or parse dispatch on {const}"),
        ],
        "src/drawspec/kinds/__init__.py": [
            (rf"\*{const},", f"`*{const}` in IMPLEMENTED"),
            (rf"if document\.kind in {const}:", f"the `_drawn` dispatch on {const}"),
        ],
        "src/drawspec/examples.py": [
            (rf'^    "{kind}": "', "a PURPOSE line"),
            (rf'^    "{kind}": \{{', "an EXAMPLES document"),
        ],
        "tools/gallery.py": [(rf'^    "{kind}",$', "a KIND_ORDER entry")],
    }
    graph = read(root, "src/drawspec/kinds/graph.py")
    if re.search(rf'^DRAWN_KINDS: Final = \([^)]*"{kind}"', graph, re.M):
        # Drawn by the graph family, which `_drawn` reaches through DRAWN_KINDS.
        code.pop("src/drawspec/kinds/__init__.py")
    if not alone:
        thin.append(f"{const} is a shared family: its wiring is the family's, not checked here")
        code = {"src/drawspec/examples.py": code["src/drawspec/examples.py"]}
        code["tools/gallery.py"] = [(rf'^    "{kind}",$', "a KIND_ORDER entry")]
    for name, checks in code.items():
        text = read(root, name)
        for pattern, what in checks:
            if not re.search(pattern, text, re.M):
                missing.append(f"{name}: {what}")

    references = sorted((root / "docs/reference").glob(f"{kind}-*.json"))
    if not references:
        missing.append(f"docs/reference/{kind}-*.json: no reference document")
    elif len(references) < 3:
        thin.append(f"docs/reference: {len(references)} reference(s); three or more show the range")
    for path in references:
        if not (root / "docs/gallery" / f"{path.stem}.svg").is_file():
            missing.append(f"docs/gallery/{path.stem}.svg: not drawn (run `make gallery`)")
    if not (root / "tests" / f"test_kinds_{kind}.py").is_file():
        # Older kinds are tested in files named otherwise (`test_clock.py`); the
        # text-output suite names every kind, so it does not count.
        tested = any(
            f'"{kind}"' in path.read_text(encoding="utf-8")
            for path in (root / "tests").glob("test_*.py")
            if path.name != "test_text_output.py"
        )
        (thin if tested else missing).append(f"tests/test_kinds_{kind}.py: no test file")
    if not (root / "docs/proposals" / f"{kind}.md").is_file():
        thin.append(f"docs/proposals/{kind}.md: no proposal with the originals")

    texts = read(root, "src/drawspec/kinds/__init__.py")
    if re.search(rf'^    "{kind}": \w+_text,$', texts, re.M):
        if not list((root / "tests/golden/text").glob(f"{kind}-*.unicode.txt")):
            missing.append(f"tests/golden/text/{kind}-*.txt: a text form with no golden file")
        if f"`{kind}`" not in read(root, "llms.txt"):
            missing.append(f"llms.txt: the text-form list does not name `{kind}`")
    for name in DOCUMENTS:
        if kind not in read(root, name):
            # The proposals index began after the first kinds; only new ones need a row.
            older = name == "docs/proposals/README.md" and not alone
            (thin if older else missing).append(f"{name}: does not mention `{kind}`")

    try:
        schema_json = json.loads(read(root, "schema/drawspec-v1.schema.json"))
        # One `oneOf` branch per family of kinds, each with its `kind` enum.
        kinds = {
            name for branch in schema_json["oneOf"] for name in branch["properties"]["kind"]["enum"]
        }
    except (ValueError, KeyError, TypeError):
        missing.append(
            "schema/drawspec-v1.schema.json: no `kind` enum to count (run `make schema`)"
        )
        return missing, thin
    total = len(kinds)
    if kind not in kinds:
        missing.append(f"schema/drawspec-v1.schema.json: `{kind}` is not in the `kind` enum")
    word = spelt(total)
    for name, shape in COUNTS:
        pattern = shape.format(word=re.escape(word))
        if not re.search(pattern, read(root, name), re.I):
            missing.append(f"{name}: the kind count is not written as {word!r} ({total} kinds)")
    return missing, thin


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("kind", help="the kind's name, as documents write it: `neuralnet`")
    parser.add_argument("--repo-root", default=".", help="the drawspec checkout (default: .)")
    args = parser.parse_args()
    root = Path(args.repo_root)
    if not (root / "src/drawspec/schema.py").is_file():
        print(f"error: {root} is not a drawspec checkout", file=sys.stderr)
        return 2
    missing, thin = audit(root, args.kind)
    for line in missing:
        print(f"missing  {line}")
    for line in thin:
        print(f"warning  {line}")
    if not missing:
        print(f"{args.kind}: wired into every registration point and document")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())

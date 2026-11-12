"""Bad input ends in a located refusal, never a traceback or malformed output.

Each case here crashed, or rendered something no parser would load, before it was
refused where it is read: non-finite or huge numbers, characters XML cannot carry,
blank text, entries that failed the type check reaching the referential passes, and
label text that looked like markup to the embedding-safety check. The last test is
the property behind them all, run over every bundled example.
"""

from __future__ import annotations

import copy
import random
import re
from typing import Any
from xml.dom import minidom

import pytest

from drawspec import render
from drawspec.errors import DocumentError, DrawspecError
from drawspec.examples import EXAMPLES
from drawspec.render import render_text
from drawspec.schema import parse_document, validate_document


def _with(kind: str, path: tuple[str | int, ...], value: object) -> dict[str, Any]:
    document = copy.deepcopy(dict(EXAMPLES[kind]))
    target: Any = document
    for step in path[:-1]:
        target = target[step]
    target[path[-1]] = value
    return document


def _pointers(kind: str, path: tuple[str | int, ...], value: object) -> list[str]:
    return [violation.pointer for violation in validate_document(_with(kind, path, value))]


@pytest.mark.parametrize("bad", [float("inf"), float("-inf"), float("nan"), 1e400, 10**400, 1e13])
def test_a_number_that_is_not_finite_or_is_absurdly_large_is_refused_at_its_pointer(
    bad: float,
) -> None:
    assert "/width" in _pointers("flow", ("width",), bad)
    assert set(_pointers("sankey", ("flows", 0, "amount"), bad)) == {"/flows/0/amount"}
    assert set(_pointers("chart", ("axes", "horizontal", "min"), bad)) == {"/axes/horizontal/min"}


def test_a_large_but_sane_number_is_still_accepted() -> None:
    assert _pointers("sankey", ("flows", 0, "amount"), 1e9) == []


@pytest.mark.parametrize("bad", ["a\x01b", "esc\x1b[0m", "half \ud83d emoji", "x￾"])
def test_a_character_xml_cannot_carry_is_refused_at_its_pointer(bad: str) -> None:
    assert _pointers("flow", ("nodes", 0, "text"), bad) == ["/nodes/0/text"]
    assert _pointers("flow", ("title",), bad) == ["/title"]


def test_tab_newline_and_astral_characters_are_accepted() -> None:
    text = "a\tb\nc \U0001f600"
    svg = render(_with("flow", ("nodes", 0, "text"), text))
    minidom.parseString(svg.encode("utf-8"))


@pytest.mark.parametrize("blank", ["", " ", "\n", "​"])
def test_blank_text_in_a_matrix_cell_or_a_venn_set_renders(blank: str) -> None:
    for document in (
        _with("matrix", ("cells", 0, "text"), blank),
        _with("venn", ("sets", 0, "text"), blank),
        _with("venn", ("regions", 0, "text"), blank),
    ):
        minidom.parseString(render(document).encode("utf-8"))


@pytest.mark.parametrize(
    ("kind", "path", "value"),
    [
        ("states", ("transitions", 0), {}),
        ("states", ("transitions", 0, "from"), []),
        ("states", ("transitions", 0, "to"), []),
        ("gitgraph", ("branches", 1, "from"), 5),
        ("flow", ("nodes",), 5),
        ("curve", ("curves",), 5),
    ],
)
def test_a_malformed_entry_gets_its_violation_not_a_traceback_from_a_referential_pass(
    kind: str, path: tuple[str | int, ...], value: object
) -> None:
    assert validate_document(_with(kind, path, value))
    with pytest.raises(DocumentError):
        parse_document(_with(kind, path, value))


@pytest.mark.parametrize(
    "label",
    [
        "set href=x",
        "report.ttf",
        "a.woff2",
        'id="main"',
        'fill="red"',
        "url(#grad)",
        "currentColor",
        'style="x"',
        "@font-face",
        "data:font",
    ],
)
@pytest.mark.parametrize("profile", ["inline", "standalone"])
def test_label_text_that_looks_like_markup_is_not_an_embedding_violation(
    label: str, profile: str
) -> None:
    svg = render(_with("flow", ("nodes", 0, "text"), label), profile=profile)
    assert label.replace('"', "&quot;") in svg or label in svg


_BOUNDARY: tuple[object, ...] = (
    float("inf"),
    float("nan"),
    1e308,
    -1,
    0,
    "",
    " ",
    "a\x01b",
    "\ud83d",
    None,
    [],
    {},
)


def _leaves(node: object, path: tuple[str | int, ...] = ()) -> list[tuple[str | int, ...]]:
    found = [path] if path else []
    if isinstance(node, dict):
        for key, child in node.items():
            found += _leaves(child, (*path, key))
    elif isinstance(node, list):
        for index, child in enumerate(node):
            found += _leaves(child, (*path, index))
    return found


def test_any_mutated_example_either_renders_cleanly_or_is_refused_cleanly() -> None:
    """The MCP server's contract: only a DrawspecError, and never `inf` in the output."""
    rng = random.Random(194)
    cases = [(name, path) for name, example in EXAMPLES.items() for path in _leaves(example)]
    for name, path in rng.sample(cases, 400):
        document = _with(name, path, rng.choice(_BOUNDARY))
        try:
            svg = render(document)
            render_text(parse_document(document))
        except DrawspecError:
            continue
        minidom.parseString(svg.encode("utf-8"))
        assert not re.search(r"\b(?:nan|inf)\b", svg), (name, path)

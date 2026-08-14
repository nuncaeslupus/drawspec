"""The generated references: they exist, they are complete, and they have not drifted.

Three of the four pages under `docs/` that a consumer reads are generated from
the code they describe — the field tables, the argument parser, the theme
dataclasses. A generated artefact that is committed can go stale, and a stale
reference is worse than none: it is confidently wrong, and the consumer has no
way to tell. So the same arrangement the published JSON Schema already has
applies here — regenerate, compare, fail on a difference, fix with `make docs`.

The completeness checks are the more interesting half. Drift is caught by
comparison, but *omission* is not: a new kind, a new command or a new theme
section would generate a page that is internally consistent and silently missing
the new thing. Each of the three has an assertion below that the page names
everything its vocabulary contains.
"""

from __future__ import annotations

import argparse
import dataclasses
from pathlib import Path

import pytest

import docs
from drawspec.cli import build_parser
from drawspec.schema import KINDS, OBJECTS, REJECTED_FIELDS
from drawspec.theme import _TOP_LEVEL_KEYS, load_theme

GENERATED = docs.generate()


@pytest.mark.parametrize("path", sorted(GENERATED, key=str), ids=lambda path: path.name)
def test_generated_reference_is_committed_and_current(path: Path) -> None:
    """The artefact cannot drift: regenerate with `make docs`."""
    assert path.is_file(), f"{path} has never been generated — run `make docs`"
    assert not docs.stale({path: GENERATED[path]}), f"{path} is stale — run `make docs`"


def test_every_generated_page_says_it_is_generated() -> None:
    """Nobody should edit one of these by hand and lose the edit at the next run."""
    for content in GENERATED.values():
        assert content.startswith(docs.BANNER)


# ---------------------------------------------------------------------------
# Completeness — the half that comparison cannot catch
# ---------------------------------------------------------------------------


def test_format_reference_names_every_kind_and_every_object() -> None:
    page = docs.format_markdown()
    for kind in KINDS:
        assert f"`{kind}`" in page, f"{kind} is not documented"
    for name in OBJECTS:
        assert f"### `{name}` object" in page, f"the {name} object is not documented"


def test_format_reference_names_every_refused_field() -> None:
    """The refusal list is the teaching surface; a gap in it teaches nothing."""
    page = docs.format_markdown()
    for name in REJECTED_FIELDS:
        assert f"`{name}`" in page, f"{name} is refused but not documented"


def test_cli_reference_names_every_command_and_argument() -> None:
    page = docs.cli_markdown()
    parser = build_parser()
    for name, command in docs._subcommands(parser).items():
        assert f"`drawspec {name}`" in page
        for action in command._actions:
            if isinstance(action, argparse._HelpAction | argparse._SubParsersAction):
                continue
            for option in action.option_strings or [action.dest]:
                assert f"`{option}`" in page, f"{name} {option} is not documented"


def test_theme_reference_names_every_section_key_and_role() -> None:
    page = docs.theme_markdown()
    theme = load_theme(None)
    for section, cls in docs.THEME_SECTIONS.items():
        assert f"### `[{section}]`" in page, f"[{section}] is not documented"
        for field in dataclasses.fields(cls):
            assert f"`{field.name}`" in page, f"[{section}] {field.name} is not documented"
    for role in (*theme.roles, *theme.edge_roles):
        assert f"`{role}`" in page, f"the {role} role is not documented"


def test_theme_reference_covers_every_section_the_loader_accepts() -> None:
    """A theme section the loader reads but this page omits is an invisible feature."""
    documented = set(docs.THEME_SECTIONS) | {"version", "name", "role", "edge_role"}
    assert set(_TOP_LEVEL_KEYS) == documented


def test_guide_links_to_all_three_references() -> None:
    """The guide is the way in; a reference it does not link to is not found."""
    guide = (docs.DOCS_DIR / "guide.md").read_text(encoding="utf-8")
    for name in docs.GENERATED:
        assert f"]({name})" in guide, f"the guide does not link to {name}"

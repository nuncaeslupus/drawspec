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
import json
import re
from pathlib import Path

import pytest

import docs
from drawspec.cli import build_parser
from drawspec.schema import KINDS, OBJECTS, REJECTED_FIELDS, parse_document
from drawspec.theme import _TOP_LEVEL_KEYS, EDGE_ROLES, NODE_ROLES, load_theme

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


def _documented_arguments(page: str, command: argparse.ArgumentParser, where: str) -> None:
    for action in command._actions:
        if isinstance(action, argparse._HelpAction | argparse._SubParsersAction):
            continue
        for option in action.option_strings or [action.dest]:
            assert f"`{option}`" in page, f"{where} {option} is not documented"


def test_cli_reference_names_every_command_and_argument() -> None:
    page = docs.cli_markdown()
    parser = build_parser()
    # The root parser's own options too — `--version` lives there, not on any
    # command, and walking only the subcommands is how a global flag ends up in
    # the usage synopsis and nowhere else.
    _documented_arguments(page, parser, "drawspec")
    for name, command in docs._subcommands(parser).items():
        assert f"`drawspec {name}`" in page
        _documented_arguments(page, command, name)
        for nested_name, nested in docs._subcommands(command).items():
            assert f"`drawspec {name} {nested_name}`" in page
            _documented_arguments(page, nested, f"{name} {nested_name}")


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


def test_the_guide_answers_the_question_the_review_asked_three_times() -> None:
    """*"I don't know what criteria you use to choose between circle and
    rectangle here"* — the roles are a vocabulary, and a vocabulary nobody
    documented is a vocabulary nobody can use."""
    guide = (Path(__file__).resolve().parents[1] / "docs" / "guide.md").read_text(encoding="utf-8")
    assert "## Choosing a role" in guide
    for role in NODE_ROLES:
        assert f"`{role}`" in guide, role
    for role in EDGE_ROLES:
        assert f"`{role}`" in guide, role


def test_every_role_is_drawn_somewhere_in_the_reference_set() -> None:
    """Prose says what a role means; only a drawing says what it looks like."""
    reference = Path(__file__).resolve().parents[1] / "docs" / "reference"
    drawn: set[str] = set()
    linking: set[str] = set()
    for path in reference.glob("*.json"):
        document = json.loads(path.read_text(encoding="utf-8"))
        drawn.update(node.get("role", "step") for node in document.get("nodes", ()))
        drawn.update("group" for _ in document.get("groups", ()))
        linking.update(edge.get("role", "flow") for edge in document.get("edges", ()))
    assert set(NODE_ROLES) <= drawn, set(NODE_ROLES) - drawn
    assert set(EDGE_ROLES) <= linking, set(EDGE_ROLES) - linking


# --------------------------------------------------------------------------
# The README's examples — E1
# --------------------------------------------------------------------------


def test_every_json_example_in_the_readme_is_a_document_that_validates() -> None:
    """A trimmed snippet that no longer parses is worse than no example.

    The README used to show a four-node `flow` beside a render of the seven-node
    reference document — the reader was shown a spec, then shown a picture, and
    left to infer a relationship that was not there. Pairing them is only worth
    anything if the pairing is true, so both halves are checked: the spec has to
    parse, and the drawing beside it has to exist.
    """
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```json\n(.*?)```", readme, re.DOTALL)
    assert len(blocks) >= 2, f"only {len(blocks)} example document(s) in the README"
    kinds = set()
    for block in blocks:
        document = parse_document(json.loads(block))
        kinds.add(document.kind)
    assert len(kinds) >= 2, f"every README example is the same kind: {kinds}"

    drawings = re.findall(r'src="(docs/gallery/[^"]+\.svg)"', readme)
    assert len(drawings) >= len(blocks), f"{len(blocks)} specs but {len(drawings)} drawings"
    for path in drawings:
        assert (Path(__file__).resolve().parents[1] / path).exists(), (
            f"the README points at a drawing that is not there: {path}"
        )


def test_each_readme_example_is_the_render_of_the_document_beside_it() -> None:
    """The pairing itself, not just that both halves exist.

    Every README example names a drawing under `docs/gallery/`, and every such
    drawing is `make gallery`'s render of the reference document of the same
    name. So the spec shown must be the reference document — otherwise the
    picture drifts from the text the first time either is edited, which is the
    failure this whole arrangement exists to prevent.
    """
    root = Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")
    pairs = re.findall(r"```json\n(.*?)```.*?src=\"docs/gallery/([^\"]+)\.svg\"", readme, re.DOTALL)
    assert pairs, "no spec is paired with a drawing in the README"
    for block, name in pairs:
        reference = root / "docs" / "reference" / f"{name}.json"
        assert reference.exists(), f"README pairs a spec with {name}.svg, which has no document"
        shown = json.loads(block)
        actual = json.loads(reference.read_text(encoding="utf-8"))
        for field in ("kind", "nodes", "edges", "items", "series", "axes"):
            if field in shown:
                assert shown[field] == actual.get(field), (
                    f"the README's {name} example differs from docs/reference/{name}.json "
                    f"at {field!r} — the picture is not the render of the spec shown"
                )


# --------------------------------------------------------------------------
# AGENTS.md — B1
# --------------------------------------------------------------------------


def test_agents_md_names_every_kind_in_the_vocabulary() -> None:
    """A brief that silently omits a kind is worse than one that omits the list.

    It is the file an agent reads *instead of* the references, so a kind missing
    from it is a kind that does not exist as far as its reader is concerned. The
    check is against `KINDS` rather than a copy, so adding a kind breaks this
    until the brief is updated.
    """
    text = (Path(__file__).resolve().parents[1] / "AGENTS.md").read_text(encoding="utf-8")
    missing = [kind for kind in KINDS if f"`{kind}`" not in text]
    assert not missing, f"AGENTS.md never names: {missing}"


def test_every_example_in_agents_md_is_a_document_that_validates() -> None:
    """The brief is held to the standard the generated references are.

    Its whole value is that an agent can copy from it, so an example that no
    longer parses is worse than no example at all — the reader has no way to
    tell, and neither did we until this ran.
    """
    text = (Path(__file__).resolve().parents[1] / "AGENTS.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```json\n(.*?)```", text, re.DOTALL)
    assert blocks, "AGENTS.md carries no example, so nothing pins it to the format"
    for block in blocks:
        parse_document(json.loads(block))


def test_agents_md_still_fits_in_a_context_window() -> None:
    """The constraint that makes it useful. Length is the feature."""
    text = (Path(__file__).resolve().parents[1] / "AGENTS.md").read_text(encoding="utf-8")
    lines = len(text.splitlines())
    assert lines <= 200, f"AGENTS.md is {lines} lines; it has to be readable in one go"


def test_agents_md_lists_the_roles_the_theme_actually_declares() -> None:
    """A role an agent writes that the theme does not declare is a hard refusal,
    so the two vocabularies have to be the same one."""
    text = (Path(__file__).resolve().parents[1] / "AGENTS.md").read_text(encoding="utf-8")
    for role in (*NODE_ROLES, *EDGE_ROLES):
        assert f"`{role}`" in text, f"AGENTS.md never names the role {role!r}"

"""The `files` kind: paths in, a directory listing out — drawn or as text."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from drawspec import render, render_text
from drawspec.cli import main
from drawspec.emit import check_embedding_safety
from drawspec.errors import DocumentError, DrawspecError, ThemeError
from drawspec.filetree import Entry, rows, text
from drawspec.schema import FILES_STYLES, parse_document, validate_document
from drawspec.theme import FilesStyle, Theme, load_theme


def document(*entries: dict[str, str], **extra: object) -> dict[str, object]:
    return {"version": 1, "kind": "files", "entries": list(entries), **extra}


PROJECT = document(
    {"path": "src/components/Button.tsx"},
    {"path": "src/components/...", "note": "12 more"},
    {"path": "src/index.ts", "note": "entry point"},
    {"path": "src/utils", "link": "../shared/utils"},
    {"path": "tests/index.test.ts", "status": "added"},
    {"path": "dist/", "note": "empty"},
    {"path": "old.cfg", "status": "removed"},
    {"path": "package.json", "status": "changed"},
    root="my-app",
)


def messages(doc: dict[str, object]) -> list[str]:
    return [str(violation) for violation in validate_document(doc)]


# -- validation ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("entries", "pointer", "words"),
    [
        ([{"path": "a"}, {"path": "a/b"}], "/entries/1/path", "Only a folder has contents"),
        ([{"path": "a/b"}, {"path": "a"}], "/entries/0/path", "Only a folder has contents"),
        ([{"path": "a"}, {"path": "a"}], "/entries/1/path", "written twice"),
        ([{"path": "a"}, {"path": "a/"}], "/entries/1/path", "a folder here and a file"),
        ([{"path": "/a"}], "/entries/0/path", "not a relative path"),
        ([{"path": "a//b"}], "/entries/0/path", "empty, '.' or '..'"),
        ([{"path": "a/../b"}], "/entries/0/path", "empty, '.' or '..'"),
        ([{"path": ".../b"}], "/entries/0/path", "last segment"),
        ([{"path": "a/...", "status": "added"}], "/entries/0/path", "'...' row"),
        ([{"path": "a/", "link": "b"}], "/entries/0/link", "no contents"),
        ([{"path": "a", "link": "b"}, {"path": "a/c"}], "/entries/1/path", "is a link"),
    ],
)
def test_a_path_that_cannot_be_a_row_is_refused_at_its_entry(
    entries: list[dict[str, str]], pointer: str, words: str
) -> None:
    found = messages(document(*entries))
    assert any(line.startswith(pointer) and words in line for line in found), found


def test_a_folder_may_be_listed_and_also_passed_through() -> None:
    assert messages(document({"path": "a/"}, {"path": "a/b"})) == []
    assert messages(document({"path": "a/b"}, {"path": "a/"})) == []


def test_several_ellipsis_rows_and_both_spellings_are_accepted() -> None:
    assert messages(document({"path": "a/..."}, {"path": "a/…"}, {"path": "a/x"})) == []


def test_root_is_one_name_not_a_path() -> None:
    assert any("/root" in line for line in messages(document({"path": "a"}, root="x/y")))


def test_an_unknown_status_style_or_sort_is_refused_by_the_schema() -> None:
    assert messages(document({"path": "a", "status": "moved"}))
    assert messages(document({"path": "a"}, style="tree"))
    assert messages(document({"path": "a"}, sort="size"))


def test_a_malformed_entries_list_is_reported_once_not_crashed_on() -> None:
    found = messages(document({"path": 3}))  # type: ignore[dict-item]
    assert found and all("expected string" in line for line in found)


# -- rows ---------------------------------------------------------------------


def names(entries: list[str], order: str = "given", root: str = "") -> list[str]:
    return [row.name for row in rows([Entry(path) for path in entries], root, order)]


def test_folders_are_inferred_from_the_paths_that_pass_through_them() -> None:
    assert names(["a/b/c.txt"]) == ["a", "b", "c.txt"]
    kinds = [row.kind for row in rows([Entry("a/b/c.txt")])]
    assert kinds == ["folder", "folder", "file"]


def test_given_order_is_kept_and_name_order_is_natural() -> None:
    entries = ["file10", "b/", "File2", "a"]
    assert names(entries) == ["file10", "b", "File2", "a"]
    assert names(entries, "name") == ["a", "b", "File2", "file10"]
    assert names(entries, "folders-first") == ["b", "a", "File2", "file10"]


def test_an_ellipsis_row_stays_last_whatever_the_order() -> None:
    assert names(["d/...", "d/b", "d/a"], "name") == ["d", "a", "b", "…"]


def test_a_root_is_the_top_row_and_everything_hangs_under_it() -> None:
    tree = rows([Entry("a"), Entry("b/c")], "top")
    assert [(row.name, row.depth, row.parent) for row in tree] == [
        ("top", 0, None),
        ("a", 1, 0),
        ("b", 1, 0),
        ("c", 2, 2),
    ]


# -- text ---------------------------------------------------------------------


def test_text_draws_the_tree_as_tree_prints_it() -> None:
    doc = parse_document(PROJECT)
    assert render_text(doc) == (
        "  my-app/\n"
        "  ├── src/\n"
        "  │   ├── components/\n"
        "  │   │   ├── Button.tsx\n"
        "  │   │   └── … 12 more\n"
        "  │   ├── index.ts                  # entry point\n"
        "  │   └── utils -> ../shared/utils\n"
        "  ├── tests/\n"
        "+ │   └── index.test.ts\n"
        "  ├── dist/                         # empty\n"
        "- ├── old.cfg\n"
        "~ └── package.json\n"
    )


def test_ascii_text_uses_no_character_outside_ascii() -> None:
    doc = parse_document({**PROJECT, "style": "ascii"})
    assert render_text(doc).isascii()
    assert "`-- " in render_text(doc)


def test_a_mark_column_appears_only_when_some_entry_has_a_status() -> None:
    assert text(rows([Entry("a"), Entry("b", status="added")])) == "  a\n+ b\n"
    assert text(rows([Entry("a"), Entry("b")])) == "a\nb\n"


def test_without_a_root_the_top_level_entries_have_no_branches() -> None:
    assert text(rows([Entry("a/b"), Entry("c")])) == "a/\n└── b\nc\n"


def test_only_a_files_document_has_a_text_form() -> None:
    flow = parse_document(
        {"version": 1, "kind": "flow", "nodes": [{"id": "a", "text": "A"}], "edges": []}
    )
    with pytest.raises(DrawspecError, match="only a `files` document"):
        render_text(flow)


def test_the_cli_writes_the_text_form(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "tree.json"
    source.write_text(json.dumps(document({"path": "a/b"})), encoding="utf-8")
    assert main(["render", str(source), "--format", "text"]) == 0
    assert capsys.readouterr().out == "a/\n└── b\n"


# -- drawn --------------------------------------------------------------------


@pytest.mark.parametrize("style", FILES_STYLES)
@pytest.mark.parametrize("theme", ["default", "accent"])
def test_every_style_renders_embedding_safe_svg(style: str, theme: str) -> None:
    svg = render({**PROJECT, "style": style}, theme)
    assert check_embedding_safety(svg, load_theme(theme)) == ()
    assert "my-app" in svg


def test_the_names_are_drawn_as_written() -> None:
    svg = render(PROJECT)
    for name in ("Button.tsx", "index.ts", "12 more", "entry point", "../shared/utils"):
        assert name in svg
    assert "+ added" in svg and "~ changed" in svg and "- removed" in svg


def test_folders_are_tinted_in_the_default_theme_and_outlined_at_zero_tint() -> None:
    assert 'fill-opacity="0.25"' in render(PROJECT)
    outline = replace(load_theme(), files=FilesStyle(tint=0))
    assert "fill-opacity" not in render(PROJECT, outline)


def test_a_themes_colours_reach_folders_and_types() -> None:
    svg = render(PROJECT, "accent")
    accent = load_theme("accent").files
    assert accent.colour_for("folder") in svg
    assert accent.colour_for("code") in svg  # index.ts and Button.tsx


def test_plain_style_draws_no_pictures() -> None:
    svg = render({**PROJECT, "style": "plain"})
    assert "<polygon" not in svg
    assert "src/" in svg


def test_text_styles_keep_their_columns_without_relying_on_spaces() -> None:
    svg = render({**PROJECT, "style": "unicode"})
    assert "  " not in "".join(part.split(">", 1)[-1] for part in svg.split("</text>"))


# -- theme --------------------------------------------------------------------


@pytest.mark.parametrize(
    "files",
    [{"tint": 1.5}, {"types": "yes"}, {"colours": {"PDF": "#000000"}}, {"shade": 1}],
)
def test_a_bad_files_section_is_refused(files: dict[str, object]) -> None:
    with pytest.raises(ThemeError, match=r"\[files\]"):
        Theme.from_mapping({"version": 1, "files": files})


def test_a_document_error_carries_every_path_problem() -> None:
    with pytest.raises(DocumentError) as raised:
        parse_document(document({"path": "/a"}, {"path": "b"}, {"path": "b"}))
    assert len(raised.value.violations) == 2

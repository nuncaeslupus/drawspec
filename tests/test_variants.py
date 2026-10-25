"""One SVG, several themes (#136): the page picks the colours."""

from __future__ import annotations

import importlib
import json
import re
from pathlib import Path
from typing import Any

import pytest

from drawspec.cli import main
from drawspec.emit import check_embedding_safety
from drawspec.errors import EmitError, ThemeError
from drawspec.examples import EXAMPLES
from drawspec.render import render
from drawspec.theme import Theme, load_theme
from drawspec.variants import theme_stamp

#: `accent`'s colours, lifted for a dark page. Everything else is `accent`'s, so
#: the two draw the same drawing and differ in paint alone.
DARK_COLOURS: dict[str, Any] = {
    "role": {
        "emphasis": {"stroke": "#F08A70"},
        "terminal": {"stroke": "#F08A70"},
        "note": {"stroke": "#A9B3BF"},
        "group": {"stroke": "#A9B3BF"},
    },
    "edge_role": {"strong": {"stroke": "#F08A70"}, "link": {"stroke": "#A9B3BF"}},
    "mark": {"colours": ["#F08A70", "#7FB0F0", "#86C28F", "#A9B3BF", "#A9B3BF"]},
    "gitgraph": {"colours": ["#7FB0F0", "#86C28F", "#E8C060", "#C09AE0", "#F08A70", "#A9B3BF"]},
}

FLOW: dict[str, Any] = {
    "version": 1,
    "kind": "flow",
    "nodes": [
        {"id": "a", "text": "Request", "role": "start"},
        {"id": "b", "text": "Decide", "role": "emphasis"},
        {"id": "c", "text": "Done", "role": "terminal"},
    ],
    "edges": [{"from": "a", "to": "b"}, {"from": "b", "to": "c", "role": "strong"}],
}


@pytest.fixture(scope="module")
def dark() -> Theme:
    accent = load_theme("accent")
    files = {"files": {"tint": accent.files.tint}}
    return load_theme({"version": 1, "name": "accent-dark", **files, **DARK_COLOURS})


def _root(svg: str) -> str:
    return svg[: svg.index(">") + 1]


def test_one_render_switches_by_data_theme_and_by_the_colour_scheme(dark: Theme) -> None:
    svg = render(FLOW, "accent", variants={"dark": dark})
    namespace = re.search(r'id="(ds[0-9a-f]+)-svg"', _root(svg))
    assert namespace is not None
    ns = namespace.group(1)
    style = re.fullmatch(r".*?<style>(.*?)</style>.*", svg, re.DOTALL)
    assert style is not None
    css = style.group(1)
    assert css.startswith(f"#{ns}-svg{{--{ns}-c0:#c0452a")
    assert f"@media (prefers-color-scheme: dark){{#{ns}-svg{{--{ns}-c0:#f08a70" in css
    assert f'[data-theme="light"] #{ns}-svg{{--{ns}-c0:#c0452a' in css
    assert f'[data-theme="dark"] #{ns}-svg{{--{ns}-c0:#f08a70' in css
    # A page's own switch must beat the reader's setting: the attribute rules
    # come after the query and are more specific than it.
    assert css.index("@media") < css.index('[data-theme="light"]')
    # The base colour stays on the element, so a host that strips <style> still
    # gets a whole drawing.
    assert f'stroke="#c0452a" stroke-width="2.5" style="stroke:var(--{ns}-c0)"' in svg
    assert not check_embedding_safety(svg, load_theme("accent"), variants=[dark])


def test_the_root_is_stamped_with_every_theme_and_its_digest(dark: Theme) -> None:
    svg = render(FLOW, "accent", variants={"dark": dark})
    stamp = re.search(r'data-drawspec-theme="([^"]*)"', _root(svg))
    assert stamp is not None
    assert stamp.group(1) == (f"light={theme_stamp(load_theme('accent'))} dark={theme_stamp(dark)}")
    assert re.fullmatch(r"accent@[0-9a-f]{8}", theme_stamp(load_theme("accent")))


def test_the_stamp_changes_with_the_theme_and_not_between_loads() -> None:
    assert theme_stamp(load_theme("accent")) == theme_stamp(load_theme("accent"))
    changed = load_theme({"version": 1, "name": "accent", "role": {"note": {"stroke": "#000"}}})
    assert theme_stamp(changed) != theme_stamp(load_theme("accent"))


def test_single_theme_output_carries_no_style_stamp_or_root_id() -> None:
    svg = render(FLOW, "accent")
    assert "<style" not in svg
    assert "data-drawspec-theme" not in svg
    assert "style=" not in svg
    assert render(FLOW, "accent", variants={}) == svg


def test_a_default_inline_base_reads_the_pages_ink_in_light_mode(dark: Theme) -> None:
    svg = render(FLOW, variants={"dark": dark})
    ns = re.search(r'id="(ds[0-9a-f]+)-svg"', svg)
    assert ns is not None
    assert f"#{ns.group(1)}-svg{{--{ns.group(1)}-c0:currentColor" in svg


@pytest.mark.parametrize("profile", ["inline", "standalone"])
@pytest.mark.parametrize("kind", sorted(EXAMPLES))
def test_every_kind_merges_into_a_safe_multi_theme_svg(
    kind: str, profile: str, dark: Theme
) -> None:
    svg = render(EXAMPLES[kind], "accent", profile, variants={"dark": dark})
    assert not check_embedding_safety(svg, load_theme("accent"), profile, variants=[dark])
    assert 'data-drawspec-theme="light=accent@' in _root(svg)


def test_hatched_marks_keep_one_pattern_per_mark_in_every_theme(dark: Theme) -> None:
    svg = render(EXAMPLES["chart"], "accent", variants={"dark": dark})
    ids = re.findall(r'<pattern id="([^"]*)"', svg)
    assert ids and all(re.fullmatch(r"ds[0-9a-f]+-p\d+", i) for i in ids)
    for identifier in ids:
        assert f"url(#{identifier})" in svg


def test_a_variant_that_changes_more_than_colour_is_refused_by_name() -> None:
    bigger = load_theme({"version": 1, "name": "bigger", "box": {"corner_radius": 9.0}})
    with pytest.raises(ThemeError, match=r"variant 'dark': theme 'bigger'.*colours only"):
        render(FLOW, variants={"dark": bigger})


@pytest.mark.parametrize("name", ["light", "Dark", "dark mode", "1st"])
def test_a_variant_name_a_page_cannot_select_is_refused(name: str) -> None:
    with pytest.raises(ThemeError, match="variant name"):
        render(FLOW, variants={name: "accent"})


def test_an_unscoped_style_is_still_a_violation() -> None:
    theme = load_theme("accent")
    leaking = '<svg id="dsx-svg"><style>text{fill:#c0452a}</style><rect id="dsx-a"/></svg>'
    assert [v.rule for v in check_embedding_safety(leaking, theme)] == ["no-style-element"]
    foreign = '<svg id="dsx-svg"><style>#dsx-svg{--dsx-c0:#123456}</style></svg>'
    assert [v.rule for v in check_embedding_safety(foreign, theme)] == ["no-style-element"]
    painted = '<svg id="dsx-svg"><rect fill="none" style="fill:red"/></svg>'
    assert [v.rule for v in check_embedding_safety(painted, theme)] == ["no-style-element"]


def test_the_cli_writes_one_svg_with_a_variant_file(tmp_path: Path) -> None:
    document = tmp_path / "flow.json"
    document.write_text(json.dumps(FLOW), encoding="utf-8")
    theme = tmp_path / "dark.toml"
    theme.write_text(
        'version = 1\nname = "night"\n[role.emphasis]\nstroke = "#F08A70"\n', encoding="utf-8"
    )
    out = tmp_path / "flow.svg"
    assert main(["render", str(document), "--variant", f"dark={theme}", "-o", str(out)]) == 0
    svg = out.read_text(encoding="utf-8")
    assert "light=default@" in svg and "dark=night@" in svg
    assert "prefers-color-scheme: dark" in svg


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["--variant", "dark=accent", "--format", "text"], "--format svg only"),
        (["--variant", "dark"], "NAME=THEME"),
        (["--variant", "dark=accent", "--variant", "dark=wheel"], "given twice"),
    ],
)
def test_the_cli_refuses_a_variant_it_cannot_honour(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], arguments: list[str], message: str
) -> None:
    document = tmp_path / "flow.json"
    document.write_text(json.dumps(FLOW), encoding="utf-8")
    assert main(["render", str(document), *arguments]) == 2
    assert message in capsys.readouterr().err


def test_a_failed_merge_is_never_returned(dark: Theme, monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module("drawspec.render")
    monkeypatch.setattr(module, "merged", lambda drawings, namespace: "<svg><style>*{}</style>")
    with pytest.raises(EmitError, match="multi-theme"):
        render(FLOW, "accent", variants={"dark": dark})

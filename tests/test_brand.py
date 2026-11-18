"""`drawspec theme from`: a theme derived from a brand's CSS or design tokens.

The guarantees a brand import may not break are the ones the default theme makes:
the drawing inherits its page (no background, `currentColor` ink), colour never
carries on its own, and a pinned colour reads in dark mode as well as on paper.
Most tests here are one of those, checked against a brand that tries to break it.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from drawspec.brand import (
    DARK_PAGE,
    GRAPHIC_CONTRAST,
    LIGHT_PAGE,
    contrast,
    derive_theme,
    fit_colour,
    parse_colour,
    read_tokens,
)
from drawspec.cli import OK, REFUSED, USAGE, main
from drawspec.errors import ThemeError
from drawspec.render import render_document
from drawspec.schema import load_document
from drawspec.theme import load_theme

ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "docs" / "reference" / "brand"


def _css(tmp_path: Path, body: str, name: str = "brand.css") -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def _tokens(tmp_path: Path, data: object, name: str = "brand.tokens.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _outcomes(derived_notes: tuple[object, ...]) -> dict[str, tuple[str, str]]:
    return {note.token: (note.outcome, note.detail) for note in derived_notes}  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


def test_css_reads_root_properties_and_resolves_var_through_a_fallback(tmp_path: Path) -> None:
    path = _css(
        tmp_path,
        """
        /* a comment with a --fake: #000; inside */
        :root {
          --teal: #0f7b8a;
          --color-accent: var(--teal);
          --color-muted: var(--missing, #6b7a86);
          --color-broken: var(--nowhere);
          --font-sans: "Brand Sans", sans-serif;
        }
        """,
    )
    tokens = {token.label: token for token in read_tokens([path])}
    assert "--fake" not in tokens
    assert tokens["--color-accent"].value == "#0f7b8a"
    assert tokens["--color-muted"].value == "#6b7a86"
    assert tokens["--color-broken"].out_of_scope
    assert tokens["--font-sans"].value == '"Brand Sans", sans-serif'


def test_css_a_dark_mode_override_is_read_as_out_of_scope_not_as_the_palette(
    tmp_path: Path,
) -> None:
    """The dark block comes second, and a naive reader takes its accent: the
    page's light-mode accent is what a drawing pinned to one colour must use."""
    path = _css(
        tmp_path,
        """
        @layer base { :root { --color-accent: #0f7b8a; } }
        @media (prefers-color-scheme: dark) { :root { --color-accent: #4fc3d1; } }
        [data-theme="dark"] { --color-muted: #9aa5b1; }
        """,
    )
    derived = derive_theme([path])
    assert derived.theme.roles["emphasis"].stroke == "#0f7b8a"
    reasons = [note.detail for note in derived.notes if note.outcome == "ignored"]
    assert any("@media (prefers-color-scheme: dark)" in reason for reason in reasons)
    assert any('[data-theme="dark"]' in reason for reason in reasons)


def test_css_a_property_redeclared_in_root_takes_the_last_value(tmp_path: Path) -> None:
    path = _css(tmp_path, ":root { --color-accent: #111111; }\n:root { --color-accent: #0f7b8a; }")
    assert derive_theme([path]).theme.roles["emphasis"].stroke == "#0f7b8a"


def test_tokens_inherit_type_resolve_aliases_and_read_value_objects(tmp_path: Path) -> None:
    path = _tokens(
        tmp_path,
        {
            "palette": {"$type": "color", "teal": {"$value": "#0f7b8a"}},
            "color": {
                "accent": {"$type": "color", "$value": "{palette.teal}"},
                "muted": {
                    "$type": "color",
                    "$value": {"colorSpace": "srgb", "components": [0.42, 0.478, 0.525]},
                },
                "loop": {"$type": "color", "$value": "{color.loop}"},
            },
            "radius": {"md": {"$type": "dimension", "$value": {"value": 0.375, "unit": "rem"}}},
        },
    )
    tokens = {token.label: token for token in read_tokens([path])}
    assert tokens["color.accent"].value == "#0f7b8a"
    assert tokens["palette.teal"].type == "color"
    assert tokens["color.loop"].out_of_scope
    derived = derive_theme([path])
    assert derived.theme.box.corner_radius == 6.0
    assert derived.theme.roles["note"].stroke == "#6b7a86"


@pytest.mark.parametrize(
    ("written", "expected"),
    [
        ("#abc", ("#aabbcc", 1.0)),
        ("#0F7B8A", ("#0f7b8a", 1.0)),
        ("#0f7b8a80", ("#0f7b8a", 128 / 255)),
        ("rgb(15 123 138)", ("#0f7b8a", 1.0)),
        ("rgba(15, 123, 138, 0.5)", ("#0f7b8a", 0.5)),
        ("hsl(0 100% 50%)", ("#ff0000", 1.0)),
        ({"hex": "#0f7b8a"}, ("#0f7b8a", 1.0)),
        ("oklch(60% 0.1 200)", None),
        ("teal", None),
    ],
)
def test_colour_forms(written: object, expected: tuple[str, float] | None) -> None:
    assert parse_colour(written) == expected


# ---------------------------------------------------------------------------
# The guarantees
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("colour", ["#f2c230", "#ffff00", "#2a1a5e", "#000000", "#ffffff"])
def test_a_colour_is_fitted_to_read_on_both_pages_keeping_its_hue(colour: str) -> None:
    fitted = fit_colour(colour, minimum=GRAPHIC_CONTRAST, pages=(LIGHT_PAGE, DARK_PAGE))
    assert fitted is not None
    assert contrast(fitted, LIGHT_PAGE) >= GRAPHIC_CONTRAST
    assert contrast(fitted, DARK_PAGE) >= GRAPHIC_CONTRAST


def test_a_colour_that_already_reads_is_left_exactly_as_the_brand_wrote_it() -> None:
    assert fit_colour("#0f7b8a", minimum=3.0, pages=(LIGHT_PAGE, DARK_PAGE)) == "#0f7b8a"


def test_a_pale_brand_colour_is_darkened_and_the_report_gives_both_ratios(
    tmp_path: Path,
) -> None:
    path = _css(tmp_path, ":root { --color-accent: #f2c230; }")
    derived = derive_theme([path])
    stroke = derived.theme.roles["emphasis"].stroke
    assert stroke != "#f2c230"
    assert contrast(stroke, LIGHT_PAGE) >= 3.0 and contrast(stroke, DARK_PAGE) >= 3.0
    outcome, detail = _outcomes(derived.notes)["--color-accent"]
    assert outcome == "adjusted"
    assert "darkened" in detail and "#f2c230" in detail and stroke in detail


def test_strict_refuses_a_colour_it_would_have_adjusted(tmp_path: Path) -> None:
    path = _css(tmp_path, ":root { --color-accent: #f2c230; }")
    with pytest.raises(ThemeError, match="--strict"):
        derive_theme([path], strict=True)


def test_every_pinned_colour_of_the_sample_brand_reads_on_both_pages() -> None:
    theme = derive_theme([BRAND / "tidemark.css"]).theme
    pinned = {
        colour
        for colour in theme.declared_colours()
        if colour.startswith("#") and colour != theme.canvas.ink
    }
    assert pinned
    for colour in pinned:
        assert contrast(colour, LIGHT_PAGE) >= 3.0, colour
        assert contrast(colour, DARK_PAGE) >= 3.0, colour


def test_the_page_is_inherited_backgrounds_borders_and_text_never_become_strokes(
    tmp_path: Path,
) -> None:
    path = _css(
        tmp_path,
        """:root {
          --color-background: #fafaf7; --color-surface: #ffffff; --color-border: #e4e7eb;
          --color-text: #1f2933; --color-text-muted: #52606d; --color-danger: #c62f2f;
          --color-primary-hover: #0b5f6b; --color-accent: #0f7b8a;
        }""",
    )
    derived = derive_theme([path])
    outcomes = _outcomes(derived.notes)
    for token in (
        "--color-background",
        "--color-surface",
        "--color-border",
        "--color-text-muted",
        "--color-danger",
        "--color-primary-hover",
    ):
        assert outcomes[token][0] == "ignored", token
    assert "background" in outcomes["--color-background"][1]
    # Strokes with nothing to say stay the page's ink, so dark mode still works.
    assert derived.theme.roles["step"].stroke == "currentColor"
    assert derived.theme.edge_roles["flow"].stroke == "currentColor"
    # The text colour is the standalone ink only; inline SVG keeps currentColor.
    assert derived.theme.canvas.ink == "#1f2933"
    svg = render_document(
        load_document(ROOT / "docs" / "reference" / "flow-triage.json"), derived.theme
    )
    assert "#1f2933" not in svg and "#fafaf7" not in svg


def test_colour_lands_only_on_the_roles_the_accent_theme_colours(tmp_path: Path) -> None:
    path = _css(tmp_path, ":root { --color-accent: #0f7b8a; --color-muted: #6b7a86; }")
    theme = derive_theme([path]).theme
    coloured = {name for name, role in theme.roles.items() if role.stroke != "currentColor"}
    coloured |= {name for name, role in theme.edge_roles.items() if role.stroke != "currentColor"}
    accent = load_theme("accent")
    expected = {name for name, role in accent.roles.items() if role.stroke != "currentColor"}
    expected |= {name for name, role in accent.edge_roles.items() if role.stroke != "currentColor"}
    assert coloured == expected
    assert theme.ambiguous_role_pairs() == ()
    assert theme.mark.colours == ("#0f7b8a", "currentColor", "currentColor", "#6b7a86", "#6b7a86")


def test_stroke_weight_scales_every_line_together_and_is_clamped(tmp_path: Path) -> None:
    default = load_theme(None)
    theme = derive_theme([_css(tmp_path, ":root { --border-width: 2px; }")]).theme
    for name, role in theme.edge_roles.items():
        ratio = role.stroke_width / default.edge_roles[name].stroke_width
        assert ratio == pytest.approx(4 / 3, abs=0.01)
    thin = derive_theme([_css(tmp_path, ":root { --border-width: 0.5px; }", "t.css")])
    assert thin.theme.edge_roles["link"].stroke_width == pytest.approx(0.75)
    assert _outcomes(thin.notes)["--border-width"][0] == "adjusted"


def test_radius_and_line_height_are_clamped_into_what_a_box_can_take(tmp_path: Path) -> None:
    path = _css(tmp_path, ":root { --radius: 9999px; --line-height: 2.4; }")
    derived = derive_theme([path])
    assert derived.theme.box.corner_radius == 12.0
    assert derived.theme.box.line_height == 1.6
    assert {note.outcome for note in derived.notes} == {"adjusted"}


def test_fonts_map_to_roles_and_a_serif_body_face_sets_the_default(tmp_path: Path) -> None:
    path = _css(
        tmp_path,
        """:root {
          --font-body: "Brand Serif", Georgia, serif;
          --font-heading: "Brand Display", serif;
          --font-code: "Brand Mono";
        }""",
    )
    derived = derive_theme([path])
    assert derived.theme.font.serif == ("Brand Serif", "Georgia", "serif")
    assert derived.theme.font.default == "serif"
    assert derived.theme.font.mono == ("Brand Mono", "monospace")  # a generic is appended
    assert _outcomes(derived.notes)["--font-heading"][0] == "ignored"


def test_a_later_file_wins_a_tie(tmp_path: Path) -> None:
    first = _css(tmp_path, ":root { --color-accent: #0f7b8a; }")
    second = _tokens(tmp_path, {"color": {"accent": {"$type": "color", "$value": "#c0452a"}}})
    assert derive_theme([first, second]).theme.roles["emphasis"].stroke == "#c0452a"
    assert derive_theme([second, first]).theme.roles["emphasis"].stroke == "#0f7b8a"


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def test_a_brand_with_nothing_that_maps_is_refused_naming_what_was_read(tmp_path: Path) -> None:
    path = _css(tmp_path, ":root { --color-background: #fff; --space-2: 8px; }")
    with pytest.raises(ThemeError, match=r"nothing in brand\.css maps") as raised:
        derive_theme([path])
    assert "--color-background" in str(raised.value)


def test_a_file_with_no_tokens_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ThemeError, match="no tokens found"):
        derive_theme([_css(tmp_path, "body { color: red; }")])


def test_an_unknown_file_type_and_a_url_are_refused(tmp_path: Path) -> None:
    other = tmp_path / "brand.scss"
    other.write_text("$accent: #0f7b8a;", encoding="utf-8")
    with pytest.raises(ThemeError, match="not a brand file"):
        derive_theme([other])
    with pytest.raises(ThemeError, match="local files only"):
        derive_theme(["https://example.com/site.css"])


# ---------------------------------------------------------------------------
# The file it writes
# ---------------------------------------------------------------------------


def test_the_toml_written_loads_to_the_same_theme(tmp_path: Path) -> None:
    derived = derive_theme([BRAND / "tidemark.css"])
    parsed = tomllib.loads(derived.toml)
    assert parsed == json.loads(json.dumps(derived.mapping))
    written = tmp_path / "house.toml"
    written.write_text(derived.toml, encoding="utf-8")
    assert load_theme(written) == derived.theme


def test_the_committed_sample_theme_is_what_theme_from_writes_today() -> None:
    """The gallery's brand drawings use this file, so it may not drift from the tool."""
    committed = (BRAND / "tidemark.toml").read_text(encoding="utf-8")
    assert committed == derive_theme([BRAND / "tidemark.css"]).toml, (
        "regenerate: drawspec theme from docs/reference/brand/tidemark.css "
        "-o docs/reference/brand/tidemark.toml"
    )


def test_the_sample_tokens_file_derives_the_same_accent_as_the_stylesheet() -> None:
    from_css = derive_theme([BRAND / "tidemark.css"]).theme
    from_tokens = derive_theme([BRAND / "tidemark.tokens.json"]).theme
    assert from_tokens.roles["emphasis"].stroke == from_css.roles["emphasis"].stroke
    assert from_tokens.mark.colours[1] == from_css.mark.colours[1]


# ---------------------------------------------------------------------------
# The command line
# ---------------------------------------------------------------------------


def test_cli_writes_the_theme_to_stdout_and_the_report_to_stderr(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["theme", "from", str(BRAND / "tidemark.css")]) == OK
    out, err = capsys.readouterr()
    assert tomllib.loads(out)["name"] == "tidemark"
    assert "ignored   --color-background" in err
    assert "adjusted  --color-secondary" in err


def test_cli_out_and_name(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = tmp_path / "house.toml"
    code = main(
        ["theme", "from", str(BRAND / "tidemark.css"), "-o", str(target), "--name", "house"]
    )
    assert code == OK
    assert capsys.readouterr().out == ""
    assert load_theme(target).name == "house"
    assert main(["theme", "check", str(target)]) == OK


def test_cli_a_url_is_a_usage_error_and_strict_a_refusal(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["theme", "from", "https://example.com/site.css"]) == USAGE
    assert "local files only" in capsys.readouterr().err
    assert main(["theme", "from", "--strict", str(BRAND / "tidemark.css")]) == REFUSED
    assert "--color-secondary" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# A theme beside its documents
# ---------------------------------------------------------------------------


def test_a_relative_theme_path_is_read_from_the_documents_folder(tmp_path: Path) -> None:
    (tmp_path / "themes").mkdir()
    (tmp_path / "themes" / "house.toml").write_text(
        derive_theme([BRAND / "tidemark.css"], "house").toml, encoding="utf-8"
    )
    document = tmp_path / "flow.json"
    document.write_text(
        json.dumps(
            {
                "version": 1,
                "kind": "flow",
                "theme": "themes/house.toml",
                "nodes": [{"id": "a", "text": "A step", "role": "emphasis"}],
            }
        ),
        encoding="utf-8",
    )
    loaded = load_document(document)
    assert Path(loaded.theme) == tmp_path / "themes" / "house.toml"
    assert "#0f7b8a" in render_document(loaded)


def test_a_bundled_theme_name_in_a_document_is_left_as_written() -> None:
    assert load_document(ROOT / "docs" / "reference" / "flow-accent.json").theme == "accent"

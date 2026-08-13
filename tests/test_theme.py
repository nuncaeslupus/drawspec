"""T2 — the theme: role vocabularies, the elastic-fit band, greyscale safety.

The gate is `greyscale_ambiguous_role_pairs == 0`, checked once per theme at load
time rather than per diagram at review time: for a theme to load, every pair of
semantic roles must differ in at least one non-colour channel, or by a relative
luminance delta of 0.25 or more.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import pytest

from drawspec.errors import ThemeError
from drawspec.theme import (
    DEFAULT_THEME_PATH,
    EDGE_HEADS,
    EDGE_ROLES,
    NODE_ROLES,
    TYPE_LEVELS,
    Theme,
    load_theme,
    relative_luminance,
)


def default_mapping() -> dict[str, Any]:
    """The bundled theme as a plain mapping, for tests that perturb one field."""
    with DEFAULT_THEME_PATH.open("rb") as handle:
        return tomllib.load(handle)


def write_theme(directory: Path, body: str) -> Path:
    path = directory / "theme.toml"
    path.write_text(body, encoding="utf-8")
    return path


MINIMAL = """
version = 1
name = "test"
"""


# --------------------------------------------------------------------------
# The gate: greyscale-ambiguous role pairs cannot load
# --------------------------------------------------------------------------


def test_theme_roles_differing_only_by_colour_raises_themeerror(tmp_path: Path) -> None:
    """Two roles alike but for a near-identical colour are indistinguishable."""
    path = write_theme(
        tmp_path,
        MINIMAL
        + """
[role.step]
shape = "rect"
stroke = "#777777"
dash = "none"
stroke_width = 1.5

[role.emphasis]
shape = "rect"
stroke = "#7a7a7a"
dash = "none"
stroke_width = 1.5
""",
    )
    with pytest.raises(ThemeError) as error:
        load_theme(path)
    message = str(error.value)
    assert "step" in message and "emphasis" in message
    assert "greyscale" in message.lower()


def test_theme_roles_differing_by_dash_pattern_loads_successfully(tmp_path: Path) -> None:
    """A non-colour channel difference survives greyscale, so it is accepted."""
    path = write_theme(
        tmp_path,
        MINIMAL
        + """
[role.step]
shape = "rect"
stroke = "#777777"
dash = "none"
stroke_width = 1.5

[role.emphasis]
shape = "rect"
stroke = "#7a7a7a"
dash = "4 3"
stroke_width = 1.5
""",
    )
    theme = load_theme(path)
    assert theme.roles["emphasis"].dash == "4 3"


def test_theme_roles_differing_only_by_a_large_luminance_delta_loads(tmp_path: Path) -> None:
    """Colour is not banned — a 0.25 luminance delta does survive greyscale."""
    path = write_theme(
        tmp_path,
        MINIMAL
        + """
[role.step]
shape = "rect"
stroke = "#000000"
dash = "none"
stroke_width = 1.5

[role.emphasis]
shape = "rect"
stroke = "#ffffff"
dash = "none"
stroke_width = 1.5
""",
    )
    assert load_theme(path).roles["emphasis"].stroke == "#ffffff"


def test_theme_roles_alike_and_both_currentcolor_raises_themeerror(tmp_path: Path) -> None:
    """`currentColor` has no luminance to compare, so it cannot rescue a pair."""
    path = write_theme(
        tmp_path,
        MINIMAL
        + """
[role.step]
shape = "rect"
stroke = "currentColor"
dash = "none"
stroke_width = 1.5

[role.emphasis]
shape = "rect"
stroke = "currentColor"
dash = "none"
stroke_width = 1.5
""",
    )
    with pytest.raises(ThemeError, match="greyscale"):
        load_theme(path)


def test_theme_edge_roles_differing_only_by_colour_raises_themeerror(tmp_path: Path) -> None:
    """The invariant covers edge roles too, not only node roles."""
    path = write_theme(
        tmp_path,
        MINIMAL
        + """
[edge_role.flow]
head = "arrow"
tail = "none"
dash = "none"
stroke = "#777777"

[edge_role.owns]
head = "arrow"
tail = "none"
dash = "none"
stroke = "#7a7a7a"
""",
    )
    with pytest.raises(ThemeError, match="greyscale"):
        load_theme(path)


def test_bundled_default_theme_loads_without_violations() -> None:
    """The shipped theme passes its own invariant."""
    theme = load_theme()
    assert theme.name
    assert theme.ambiguous_role_pairs() == ()


def test_bundled_default_theme_declares_every_role_in_both_vocabularies() -> None:
    theme = load_theme()
    assert tuple(sorted(theme.roles)) == tuple(sorted(NODE_ROLES))
    assert tuple(sorted(theme.edge_roles)) == tuple(sorted(EDGE_ROLES))


@pytest.mark.parametrize("first", NODE_ROLES)
@pytest.mark.parametrize("second", NODE_ROLES)
def test_bundled_default_theme_node_roles_are_pairwise_distinguishable(
    first: str, second: str
) -> None:
    """`greyscale_ambiguous_role_pairs == 0`, one pair at a time."""
    if first == second:
        return
    theme = load_theme()
    assert (first, second) not in theme.ambiguous_role_pairs()
    assert (second, first) not in theme.ambiguous_role_pairs()


# --------------------------------------------------------------------------
# Edge roles are how "no arrow, just a line" is said
# --------------------------------------------------------------------------


def test_theme_edge_role_with_head_none_loads_and_renders_a_plain_line() -> None:
    """§5.2: a headless connector is expressible, and it is a role, not geometry."""
    theme = load_theme()
    link = theme.edge_roles["link"]
    assert link.head == "none"
    assert link.tail == "none"
    # Nothing to draw at either end: the emitter has no head geometry to place,
    # which is what makes "merely associated" sayable without saying "no arrow".
    assert link.has_head is False
    assert link.has_tail is False


def test_theme_edge_role_head_outside_vocabulary_raises_themeerror(tmp_path: Path) -> None:
    """The head vocabulary is closed."""
    path = write_theme(
        tmp_path,
        MINIMAL
        + """
[edge_role.flow]
head = "filled-triangle"
""",
    )
    with pytest.raises(ThemeError) as error:
        load_theme(path)
    message = str(error.value)
    assert "filled-triangle" in message
    assert all(head in message for head in EDGE_HEADS)


def test_theme_edge_role_bidirectional_has_both_ends() -> None:
    exchange = load_theme().edge_roles["exchange"]
    assert exchange.has_head and exchange.has_tail


def test_theme_role_outside_the_node_vocabulary_raises_themeerror(tmp_path: Path) -> None:
    """A role no document can name is a typo, not an extension point."""
    path = write_theme(tmp_path, MINIMAL + '\n[role.swimlane]\nshape = "rect"\n')
    with pytest.raises(ThemeError) as error:
        load_theme(path)
    assert "swimlane" in str(error.value)


def test_theme_node_shape_outside_vocabulary_raises_themeerror(tmp_path: Path) -> None:
    path = write_theme(tmp_path, MINIMAL + '\n[role.step]\nshape = "octagon"\n')
    with pytest.raises(ThemeError, match="octagon"):
        load_theme(path)


def test_theme_fill_pattern_outside_vocabulary_raises_themeerror(tmp_path: Path) -> None:
    path = write_theme(tmp_path, MINIMAL + '\n[role.step]\nfill_pattern = "tartan"\n')
    with pytest.raises(ThemeError, match="tartan"):
        load_theme(path)


# --------------------------------------------------------------------------
# Elastic fit: one factor, every level
# --------------------------------------------------------------------------


def test_theme_fit_band_defaults_to_shrink_only() -> None:
    """§5.2: `scale_max` defaults to 1.0 — drawspec shrinks to fit, never grows."""
    fit = load_theme().fit
    assert fit.scale_max == 1.0
    assert 0 < fit.scale_min <= 1.0


def test_theme_scale_scaled_applies_one_factor_to_every_level() -> None:
    """The uniform-factor rule is structural: there is no per-level scaling API."""
    scale = load_theme().scale
    scaled = scale.scaled(0.9)
    for level in TYPE_LEVELS:
        assert getattr(scaled, level) == pytest.approx(getattr(scale, level) * 0.9)


def test_theme_scale_scaled_preserves_the_ratios_between_levels() -> None:
    scale = load_theme().scale
    scaled = scale.scaled(0.85)
    assert scaled.title / scaled.body == pytest.approx(scale.title / scale.body)
    assert scaled.heading / scaled.label == pytest.approx(scale.heading / scale.label)


def test_theme_scale_scaled_rejects_a_non_positive_factor() -> None:
    with pytest.raises(ValueError, match="factor"):
        load_theme().scale.scaled(0.0)


def test_theme_fit_band_with_min_above_max_raises_themeerror(tmp_path: Path) -> None:
    path = write_theme(tmp_path, MINIMAL + "\n[fit]\nscale_min = 1.2\nscale_max = 1.0\n")
    with pytest.raises(ThemeError, match="scale_min"):
        load_theme(path)


def test_theme_scale_with_a_non_positive_size_raises_themeerror(tmp_path: Path) -> None:
    path = write_theme(tmp_path, MINIMAL + "\n[scale]\nbody = 0.0\n")
    with pytest.raises(ThemeError, match="body"):
        load_theme(path)


# --------------------------------------------------------------------------
# Loading, merging and the structural checks
# --------------------------------------------------------------------------


def test_load_theme_with_no_argument_returns_the_bundled_default() -> None:
    assert load_theme().name == load_theme("default").name


def test_load_theme_merges_over_the_default_so_a_theme_declares_only_overrides(
    tmp_path: Path,
) -> None:
    """A consumer theme is a diff, not a full restatement of every role."""
    path = write_theme(tmp_path, MINIMAL + "\n[canvas]\nwidth = 800.0\n")
    theme = load_theme(path)
    assert theme.canvas.width == 800.0
    # Everything not mentioned still comes from the default.
    assert theme.roles["decision"].shape == load_theme().roles["decision"].shape
    assert theme.box.line_height == load_theme().box.line_height


def test_load_theme_accepts_a_mapping() -> None:
    theme = load_theme({"version": 1, "name": "inline", "canvas": {"width": 480.0}})
    assert theme.name == "inline"
    assert theme.canvas.width == 480.0


def test_load_theme_missing_version_raises_themeerror(tmp_path: Path) -> None:
    path = write_theme(tmp_path, 'name = "no version"\n')
    with pytest.raises(ThemeError, match="version"):
        load_theme(path)


def test_load_theme_unsupported_version_raises_themeerror(tmp_path: Path) -> None:
    path = write_theme(tmp_path, 'version = 99\nname = "future"\n')
    with pytest.raises(ThemeError, match="version"):
        load_theme(path)


def test_load_theme_unknown_key_raises_themeerror(tmp_path: Path) -> None:
    """A silently ignored theme key is the same failure as a silently ignored
    document field: the author believes they configured something."""
    path = write_theme(tmp_path, MINIMAL + "\n[canvas]\nwdith = 800.0\n")
    with pytest.raises(ThemeError, match="wdith"):
        load_theme(path)


def test_load_theme_unknown_section_raises_themeerror(tmp_path: Path) -> None:
    path = write_theme(tmp_path, MINIMAL + "\n[shadows]\nblur = 3\n")
    with pytest.raises(ThemeError, match="shadows"):
        load_theme(path)


def test_load_theme_malformed_toml_raises_themeerror(tmp_path: Path) -> None:
    path = write_theme(tmp_path, "version = = 1\n")
    with pytest.raises(ThemeError, match="parse"):
        load_theme(path)


def test_load_theme_missing_file_raises_themeerror(tmp_path: Path) -> None:
    with pytest.raises(ThemeError, match="not"):
        load_theme(tmp_path / "absent.toml")


def test_load_theme_returns_the_theme_it_is_given() -> None:
    theme = load_theme()
    assert load_theme(theme) is theme


def test_theme_padding_must_have_four_values(tmp_path: Path) -> None:
    path = write_theme(tmp_path, MINIMAL + "\n[box]\npadding = [10.0, 12.0]\n")
    with pytest.raises(ThemeError, match="padding"):
        load_theme(path)


def test_theme_padding_reads_in_css_order() -> None:
    padding = load_theme().box.padding
    assert (padding.top, padding.right, padding.bottom, padding.left) == tuple(
        default_mapping()["box"]["padding"]
    )


def test_theme_padding_bottom_is_not_less_than_the_top() -> None:
    """The corpus's single most repeated failure was a starved bottom margin."""
    padding = load_theme().box.padding
    assert padding.bottom >= padding.top


def test_theme_dash_pattern_must_be_positive_numbers(tmp_path: Path) -> None:
    path = write_theme(tmp_path, MINIMAL + '\n[role.note]\ndash = "3 -2"\n')
    with pytest.raises(ThemeError, match="dash"):
        load_theme(path)


def test_theme_colour_must_be_currentcolor_none_or_hex(tmp_path: Path) -> None:
    path = write_theme(tmp_path, MINIMAL + '\n[role.step]\nstroke = "rebeccapurple"\n')
    with pytest.raises(ThemeError, match="rebeccapurple"):
        load_theme(path)


def test_theme_short_hex_colour_is_normalised(tmp_path: Path) -> None:
    """One spelling per colour, so the emitter's declared-value check is exact."""
    path = write_theme(
        tmp_path, MINIMAL + '\n[role.step]\nstroke = "#ABC"\ndash = "none"\nstroke_width = 3.0\n'
    )
    assert load_theme(path).roles["step"].stroke == "#aabbcc"


def test_theme_declared_colours_are_the_emitters_allowlist() -> None:
    """T1 checks emitted literals against exactly this set."""
    theme = load_theme()
    assert "currentColor" in theme.declared_colours()
    for role in theme.roles.values():
        assert role.stroke in theme.declared_colours()


def test_theme_is_immutable() -> None:
    theme = load_theme()
    with pytest.raises(AttributeError):
        theme.name = "other"  # type: ignore[misc]


def test_theme_roles_mapping_is_immutable() -> None:
    theme = load_theme()
    with pytest.raises(TypeError):
        theme.roles["step"] = theme.roles["note"]  # type: ignore[index]


def test_theme_font_default_must_name_a_declared_stack(tmp_path: Path) -> None:
    path = write_theme(tmp_path, MINIMAL + '\n[font]\ndefault = "cursive"\n')
    with pytest.raises(ThemeError, match="cursive"):
        load_theme(path)


def test_theme_font_stacks_reach_the_measurer_unchanged() -> None:
    """The theme's stacks are what T3 resolves — no second source of truth."""
    theme = load_theme()
    assert theme.font.stacks()["sans"] == theme.font.sans
    assert set(theme.font.stacks()) == {"sans", "serif", "mono"}


def test_theme_title_is_off_by_default() -> None:
    """`docs/theme-requirements.md` §8: raised, left open, so none is added."""
    assert load_theme().title.show is False


def test_theme_from_mapping_is_deterministic() -> None:
    """Same input, same theme — the determinism criterion starts here."""
    mapping = default_mapping()
    assert Theme.from_mapping(mapping) == Theme.from_mapping(mapping)


# --------------------------------------------------------------------------
# Relative luminance
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("colour", "expected"),
    [("#000000", 0.0), ("#ffffff", 1.0), ("#808080", 0.2158), ("#ff0000", 0.2126)],
)
def test_relative_luminance_matches_the_wcag_definition(colour: str, expected: float) -> None:
    assert relative_luminance(colour) == pytest.approx(expected, abs=5e-4)


def test_relative_luminance_of_an_uncomputable_colour_is_none() -> None:
    assert relative_luminance("currentColor") is None
    assert relative_luminance("none") is None


def test_the_two_role_vocabularies_share_no_name() -> None:
    """A name in both would resolve to the node role and cost an edge its head.

    `role_for` tries nodes first, and `edge_primitives` reads a head with
    `getattr(role, "head", "none")` — so an edge whose role is also a node role
    silently loses its arrow. That is exactly what happened when `emphasis` was
    added to both vocabularies: the critical path came out headless, and the
    drawing looked plausible.
    """
    assert set(NODE_ROLES).isdisjoint(EDGE_ROLES)

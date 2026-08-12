"""T1 — the Scene seam and the SVG emitter.

The gate is `embedding_safety_violations == 0`, measured **per profile** rather
than summed: `standalone` is exercised less than `inline`, and aggregating the
two is exactly how an unresolved `currentColor` reaches a PDF.
"""

from __future__ import annotations

import re
from xml.etree import ElementTree

import pytest

from drawspec.emit import (
    PROFILES,
    check_embedding_safety,
    emit,
    format_number,
    namespace_for,
)
from drawspec.errors import EmitError
from drawspec.scene import Ellipse, Path, Polygon, Rect, Scene, TextRun
from drawspec.theme import load_theme

THEME = load_theme()


def a_scene(title: str = "Request validation") -> Scene:
    """A scene touching every primitive, every role kind and both fonts."""
    return Scene(
        width=320.0,
        height=180.0,
        title=title,
        description="An incoming request is validated, then accepted or rejected.",
        primitives=(
            Rect("step", x=20.0, y=20.0, width=120.0, height=40.0),
            Rect("start", x=20.0, y=90.0, width=120.0, height=40.0),
            Ellipse("note", cx=240.0, cy=40.0, rx=50.0, ry=24.0),
            Polygon("decision", points=((200.0, 100.0), (240.0, 80.0), (280.0, 100.0))),
            Path("flow", points=((80.0, 60.0), (80.0, 90.0))),
            Path("link", points=((140.0, 40.0), (190.0, 40.0))),
            Polygon("flow", points=((76.0, 84.0), (84.0, 84.0), (80.0, 90.0))),
            TextRun("step", x=30.0, y=45.0, text="Request arrives", level="body"),
            TextRun("step", x=30.0, y=115.0, text="queue.process()", level="label", font="mono"),
        ),
    )


def parse(svg: str) -> ElementTree.Element:
    return ElementTree.fromstring(svg)


def paints(svg: str) -> list[str]:
    return [value for _, value in re.findall(r'\b(fill|stroke)="([^"]*)"', svg)]


# --------------------------------------------------------------------------
# The gate
# --------------------------------------------------------------------------


@pytest.mark.parametrize("profile", PROFILES)
def test_emit_any_scene_produces_no_style_element(profile: str) -> None:
    """A global <style> leaks into the host page, in either profile."""
    assert "<style" not in emit(a_scene(), THEME, profile)


@pytest.mark.parametrize("profile", PROFILES)
def test_emit_passes_its_own_safety_check_per_profile(profile: str) -> None:
    """`embedding_safety_violations == 0` — measured per profile, not summed."""
    svg = emit(a_scene(), THEME, profile)
    assert check_embedding_safety(svg, THEME, profile) == ()


def test_emit_two_documents_on_one_page_produce_no_duplicate_ids() -> None:
    """The inline promise: two diagrams share a page without colliding."""
    first = emit(a_scene("First diagram"), THEME)
    second = emit(a_scene("Second diagram"), THEME)
    identifiers = re.findall(r'\bid="([^"]*)"', first + second)
    assert identifiers
    assert len(identifiers) == len(set(identifiers))


def test_emit_inline_profile_strokes_use_currentcolor() -> None:
    """Inline, the diagram is drawn in the page's ink and follows it into dark mode."""
    svg = emit(a_scene(), THEME, "inline")
    assert "currentColor" in svg
    assert all(paint in {"currentColor", "none"} for paint in paints(svg))


def test_emit_standalone_profile_leaves_no_unresolved_currentcolor() -> None:
    svg = emit(a_scene(), THEME, "standalone")
    assert "currentColor" not in svg
    assert THEME.canvas.ink in svg


def test_emit_standalone_profile_carries_explicit_dimensions() -> None:
    root = parse(emit(a_scene(), THEME, "standalone"))
    assert root.get("width") == "320"
    assert root.get("height") == "180"
    assert root.get("viewBox") == "0 0 320 180"


def test_emit_inline_profile_carries_a_viewbox_and_no_dimensions() -> None:
    """Inline, the diagram scales to whatever contains it."""
    root = parse(emit(a_scene(), THEME, "inline"))
    assert root.get("viewBox") == "0 0 320 180"
    assert root.get("width") is None
    assert root.get("height") is None


def test_emit_scene_with_undeclared_role_raises_error() -> None:
    scene = Scene(width=10.0, height=10.0, primitives=(Rect("swimlane", width=5.0, height=5.0),))
    with pytest.raises(EmitError) as error:
        emit(scene, THEME)
    assert "swimlane" in str(error.value)


def test_emit_rect_tagged_with_a_non_rectangular_role_raises() -> None:
    """A `decision` drawn as a rectangle is silent, and looks like a render bug.

    It produces a box sized for a diamond's inscribed rectangle — so the label
    floats in a lot of empty space — and nothing about the SVG says why. This
    exact mistake shipped in T7's spike harness, so it is checked rather than
    left as a convention.
    """
    scene = Scene(width=40.0, height=40.0, primitives=(Rect("decision", width=30.0, height=20.0),))
    with pytest.raises(EmitError) as error:
        emit(scene, THEME)
    message = str(error.value)
    assert "decision" in message and "diamond" in message
    assert "box_primitives" in message


def test_emit_rect_is_fine_for_a_role_the_theme_draws_as_one() -> None:
    for role in ("step", "start", "note", "group", "emphasis", "terminal"):
        scene = Scene(width=40.0, height=40.0, primitives=(Rect(role, width=30.0, height=20.0),))
        assert emit(scene, THEME)


def test_emit_same_scene_twice_produces_identical_bytes() -> None:
    """`nondeterministic_reruns == 0` for the emitter's own contribution."""
    assert emit(a_scene(), THEME).encode() == emit(a_scene(), THEME).encode()


def test_emit_embeds_no_font() -> None:
    svg = emit(a_scene(), THEME)
    assert "@font-face" not in svg
    assert ".ttf" not in svg and ".woff" not in svg


def test_emit_uses_only_colours_the_theme_declares() -> None:
    for profile in PROFILES:
        for paint in paints(emit(a_scene(), THEME, profile)):
            assert paint in THEME.declared_colours()


# --------------------------------------------------------------------------
# The validator itself — it has to catch what it claims to catch
# --------------------------------------------------------------------------


def test_safety_check_catches_a_style_element() -> None:
    svg = "<svg><style>.a{fill:red}</style></svg>"
    rules = {violation.rule for violation in check_embedding_safety(svg, THEME)}
    assert "no-style-element" in rules


def test_safety_check_catches_an_unnamespaced_id() -> None:
    svg = '<svg><rect id="ds1234-box"/><rect id="box"/></svg>'
    violations = check_embedding_safety(svg, THEME, namespace="ds1234")
    assert [violation.rule for violation in violations] == ["namespaced-ids"]
    assert "'box'" in violations[0].detail


def test_safety_check_catches_a_reference_outside_the_document() -> None:
    svg = '<svg><rect fill="url(#other-hatch)"/></svg>'
    rules = {violation.rule for violation in check_embedding_safety(svg, THEME, namespace="ds1")}
    assert "namespaced-ids" in rules


def test_safety_check_catches_an_undeclared_colour() -> None:
    svg = '<svg><rect stroke="#ff00ff"/></svg>'
    violations = check_embedding_safety(svg, THEME)
    assert [violation.rule for violation in violations] == ["declared-colours-only"]


def test_safety_check_catches_an_embedded_font() -> None:
    svg = "<svg><defs><style>@font-face{src:url(a.woff2)}</style></defs></svg>"
    rules = {violation.rule for violation in check_embedding_safety(svg, THEME)}
    assert "no-embedded-font" in rules


def test_safety_check_catches_currentcolor_in_the_standalone_profile() -> None:
    svg = '<svg><rect stroke="currentColor"/></svg>'
    assert check_embedding_safety(svg, THEME, "inline") == ()
    rules = {violation.rule for violation in check_embedding_safety(svg, THEME, "standalone")}
    assert "standalone-resolves-colour" in rules


def test_emit_refuses_rather_than_returning_unsafe_svg() -> None:
    """§5.5: a violation raises. Bad SVG on a page is found by a reader."""
    unsafe = load_theme(
        {
            "version": 1,
            "name": "unsafe",
            "canvas": {"ink": "#111111"},
            "role": {"step": {"stroke": "#ff00ff"}},
        }
    )
    scene = Scene(width=10.0, height=10.0, primitives=(Rect("step", width=5.0, height=5.0),))
    # The theme declares #ff00ff, so its own render is fine...
    assert emit(scene, unsafe)
    # ...but the same SVG checked against a theme that does not declare it fails.
    assert check_embedding_safety(emit(scene, unsafe), THEME) != ()


# --------------------------------------------------------------------------
# Styling comes from the theme, and only from the theme
# --------------------------------------------------------------------------


def test_emit_node_role_stroke_width_comes_from_the_theme() -> None:
    scene = Scene(width=10.0, height=10.0, primitives=(Rect("emphasis", width=5.0, height=5.0),))
    svg = emit(scene, THEME)
    assert f'stroke-width="{format_number(THEME.roles["emphasis"].stroke_width)}"' in svg


def test_emit_dashed_role_carries_its_dash_pattern() -> None:
    scene = Scene(width=10.0, height=10.0, primitives=(Rect("note", width=5.0, height=5.0),))
    assert f'stroke-dasharray="{THEME.roles["note"].dash}"' in emit(scene, THEME)


def test_emit_solid_role_carries_no_dash_attribute() -> None:
    scene = Scene(width=10.0, height=10.0, primitives=(Rect("step", width=5.0, height=5.0),))
    assert "stroke-dasharray" not in emit(scene, THEME)


def test_emit_pill_role_is_rounded_to_a_pill() -> None:
    """A `pill` role is a box rounded until it stops looking like one."""
    scene = Scene(width=40.0, height=40.0, primitives=(Rect("start", width=30.0, height=20.0),))
    assert 'rx="10"' in emit(scene, THEME)


def test_emit_rect_role_uses_the_themes_one_corner_radius() -> None:
    scene = Scene(width=40.0, height=40.0, primitives=(Rect("step", width=30.0, height=20.0),))
    assert f'rx="{format_number(THEME.box.corner_radius)}"' in emit(scene, THEME)


def test_emit_edge_path_is_stroked_and_not_filled() -> None:
    scene = Scene(
        width=40.0, height=40.0, primitives=(Path("flow", points=((0.0, 0.0), (10.0, 0.0))),)
    )
    svg = emit(scene, THEME)
    assert 'fill="none"' in svg
    assert 'd="M 0 0 L 10 0"' in svg


def test_emit_edge_head_polygon_is_filled_and_not_stroked() -> None:
    """A head is the same ink as its shaft, whatever weight the theme sets."""
    scene = Scene(
        width=40.0,
        height=40.0,
        primitives=(Polygon("flow", points=((0.0, 0.0), (6.0, 3.0), (0.0, 6.0))),),
    )
    svg = emit(scene, THEME)
    assert 'fill="currentColor"' in svg
    assert 'stroke="none"' in svg


def test_theme_edge_role_with_head_none_renders_a_plain_line() -> None:
    """T2's `link` role, proved at the output: a line, and nothing at its ends."""
    scene = Scene(
        width=40.0, height=40.0, primitives=(Path("link", points=((0.0, 0.0), (20.0, 0.0))),)
    )
    root = parse(emit(scene, THEME))
    drawn = [child.tag.rsplit("}", 1)[-1] for child in root]
    assert drawn == ["path"]
    assert THEME.edge_roles["link"].has_head is False


def test_emit_hatched_role_defines_a_namespaced_pattern() -> None:
    hatched = load_theme(
        {
            "version": 1,
            "name": "hatched",
            "role": {"group": {"fill_pattern": "hatch", "fill": "currentColor"}},
        }
    )
    scene = Scene(width=40.0, height=40.0, primitives=(Rect("group", width=30.0, height=20.0),))
    svg = emit(scene, hatched)
    namespace = namespace_for(scene, hatched, "inline")
    assert f'<pattern id="{namespace}-hatch"' in svg
    assert f'fill="url(#{namespace}-hatch)"' in svg
    assert check_embedding_safety(svg, hatched) == ()


def test_emit_scene_without_a_pattern_emits_no_defs() -> None:
    scene = Scene(width=10.0, height=10.0, primitives=(Rect("step", width=5.0, height=5.0),))
    assert "<defs>" not in emit(scene, THEME)


# --------------------------------------------------------------------------
# Text
# --------------------------------------------------------------------------


def test_emit_text_size_comes_from_the_type_scale() -> None:
    scene = Scene(
        width=40.0,
        height=40.0,
        primitives=(TextRun("step", x=1.0, y=2.0, text="A", level="title"),),
    )
    assert f'font-size="{format_number(THEME.scale.title)}"' in emit(scene, THEME)


def test_emit_text_family_comes_from_the_theme_stack() -> None:
    scene = Scene(
        width=40.0,
        height=40.0,
        primitives=(TextRun("step", x=1.0, y=2.0, text="A", font="mono"),),
    )
    svg = emit(scene, THEME)
    for family in THEME.font.mono:
        assert family in svg


def test_emit_text_uses_no_dominant_baseline() -> None:
    """Renderers disagree about it, so the baseline is computed, not delegated."""
    assert "dominant-baseline" not in emit(a_scene(), THEME)


def test_emit_text_escapes_markup_in_its_content() -> None:
    scene = Scene(
        width=40.0,
        height=40.0,
        primitives=(TextRun("step", x=1.0, y=2.0, text="a < b & c"),),
    )
    svg = emit(scene, THEME)
    assert "a &lt; b &amp; c" in svg
    assert parse(svg)[0].text == "a < b & c"


def test_emit_rotated_text_carries_a_rotation_about_its_own_origin() -> None:
    scene = Scene(
        width=40.0,
        height=40.0,
        primitives=(TextRun("step", x=10.0, y=20.0, text="Volume", rotate=-90.0),),
    )
    assert 'transform="rotate(-90 10 20)"' in emit(scene, THEME)


def test_emit_bold_run_carries_a_weight_and_a_normal_one_does_not() -> None:
    bold = Scene(width=40.0, height=40.0, primitives=(TextRun("step", text="A", weight="bold"),))
    plain = Scene(width=40.0, height=40.0, primitives=(TextRun("step", text="A"),))
    assert 'font-weight="bold"' in emit(bold, THEME)
    assert "font-weight" not in emit(plain, THEME)


# --------------------------------------------------------------------------
# Accessibility, structure and numbers
# --------------------------------------------------------------------------


def test_emit_title_and_description_are_reachable_from_the_root() -> None:
    root = parse(emit(a_scene(), THEME))
    labelled = (root.get("aria-labelledby") or "").split()
    identifiers = re.findall(r'\bid="([^"]*)"', emit(a_scene(), THEME))
    assert labelled and set(labelled) <= set(identifiers)
    assert root.get("role") == "img"


def test_emit_scene_without_a_title_emits_no_ids_at_all() -> None:
    """Nothing to collide with is the strongest form of not colliding."""
    scene = Scene(width=10.0, height=10.0, primitives=(Rect("step", width=5.0, height=5.0),))
    svg = emit(scene, THEME)
    assert "id=" not in svg
    assert "aria-labelledby" not in svg


def test_emit_output_is_well_formed_xml() -> None:
    for profile in PROFILES:
        assert parse(emit(a_scene(), THEME, profile)) is not None


def test_emit_preserves_primitive_order() -> None:
    """Overlap is resolved by the layout, so paint order is the scene's order."""
    root = parse(emit(a_scene(), THEME))
    drawn = [
        child.tag.rsplit("}", 1)[-1]
        for child in root
        if child.tag.rsplit("}", 1)[-1] not in ("title", "desc")
    ]
    assert drawn == [
        "rect",
        "rect",
        "ellipse",
        "polygon",
        "path",
        "path",
        "polygon",
        "text",
        "text",
    ]


def test_emit_unknown_profile_raises_valueerror() -> None:
    with pytest.raises(ValueError, match="profile"):
        emit(a_scene(), THEME, "printed")


def test_emit_accepts_a_theme_by_name() -> None:
    assert emit(a_scene(), "default")


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0.0, "0"), (-0.0, "0"), (2.0, "2"), (2.5, "2.5"), (1.0004, "1"), (-3.25, "-3.25")],
)
def test_format_number_has_one_spelling_per_number(value: float, expected: str) -> None:
    assert format_number(value) == expected


def test_namespace_is_derived_from_content_so_it_is_stable_and_distinct() -> None:
    assert namespace_for(a_scene("A"), THEME, "inline") == namespace_for(
        a_scene("A"), THEME, "inline"
    )
    assert namespace_for(a_scene("A"), THEME, "inline") != namespace_for(
        a_scene("B"), THEME, "inline"
    )


def test_scene_roles_are_sorted_and_deduplicated() -> None:
    assert a_scene().roles() == ("decision", "flow", "link", "note", "start", "step")

"""`fishbone` — one effect, its causes grouped by category.

The kind's claims are geometric, so they are asserted from the drawing: every
bone meets the spine, the spine meets the effect's box at the middle of its left
border, no cause's words cross its bone or another cause, the bones alternate
above and below nearest the head first, and a confirmed root cause is the one
heavy path to the spine. The document rules — two levels and no third, no
connectors, no empty category, the counts — are asserted by the pointer of the
refusal.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from drawspec import render
from drawspec.errors import FitError, ThemeError
from drawspec.kinds.fishbone import BoneDrawn, FishboneDrawing, fishbone_drawing
from drawspec.scene import Path as Stroke
from drawspec.schema import (
    FISHBONE_CATEGORY_MAX,
    FISHBONE_CAUSE_MAX,
    parse_document,
    validate_document,
)
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])
REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "reference"
REFERENCES = sorted(REFERENCE.glob("fishbone-*.json"))
EPSILON = 1e-6


def fishbone(**extra: Any) -> dict[str, Any]:
    """Three categories, one with a root cause and one with a cause ruled out."""
    document: dict[str, Any] = {
        "version": 1,
        "kind": "fishbone",
        "effect": {"text": "Checkout is slow"},
        "categories": [
            {
                "text": "Database",
                "causes": [
                    {"text": "Missing index on orders", "role": "emphasis"},
                    {"text": "Connection pool too small"},
                ],
            },
            {
                "text": "Network",
                "causes": [{"text": "DNS lookups on every call", "role": "note"}],
            },
            {"text": "Code", "causes": [{"text": "N+1 queries"}, {"text": "Logging in the loop"}]},
        ],
    }
    document.update(extra)
    return document


def drawn(document: dict[str, Any], theme: Any = THEME) -> FishboneDrawing:
    return fishbone_drawing(parse_document(document), theme, MEASURER)


def pointers(document: dict[str, Any]) -> list[str]:
    return [violation.pointer for violation in validate_document(document)]


def messages(document: dict[str, Any]) -> str:
    return "\n".join(violation.message for violation in validate_document(document))


def bone_x(bone: BoneDrawn, y: float) -> float:
    """Where the bone is at height `y`, along the straight line from far end to spine."""
    (fx, fy), (jx, jy) = bone.far, bone.junction
    return jx + (fx - jx) * (y - jy) / (fy - jy)


def overlaps(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
    return (
        a[0] < b[2] - EPSILON
        and b[0] < a[2] - EPSILON
        and a[1] < b[3] - EPSILON
        and (b[1] < a[3] - EPSILON)
    )


# ---------------------------------------------------------------------------
# The references
# ---------------------------------------------------------------------------


def test_there_are_at_least_three_references() -> None:
    assert len(REFERENCES) >= 3


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_every_reference_renders_and_every_bone_meets_the_spine(path: Path) -> None:
    document = json.loads(path.read_text())
    assert render(document).startswith("<svg")
    drawing = drawn(document)
    (start_x, spine_y), (end_x, end_y) = drawing.spine
    assert spine_y == pytest.approx(end_y)
    for bone in drawing.bones:
        x, y = bone.junction
        assert y == pytest.approx(spine_y)
        assert start_x - EPSILON <= x <= end_x + EPSILON


@pytest.mark.parametrize("path", REFERENCES, ids=lambda path: path.stem)
def test_no_words_cross_a_bone_or_each_other(path: Path) -> None:
    drawing = drawn(json.loads(path.read_text()))
    words = [bone.label for bone in drawing.bones]
    for bone in drawing.bones:
        for cause in bone.causes:
            left, top, right, bottom = cause.text
            # The words end short of their own bone, at every height they span.
            assert right < min(bone_x(bone, top), bone_x(bone, bottom))
            # And stand on their tick, which runs to the bone.
            (open_x, tick_y), (end_x, end_y) = cause.tick
            assert tick_y == pytest.approx(end_y) and tick_y >= bottom
            assert open_x <= left and end_x == pytest.approx(bone_x(bone, tick_y))
            words.append(cause.text)
    for index, first in enumerate(words):
        for second in words[index + 1 :]:
            assert not overlaps(first, second), (first, second)


def test_the_spine_meets_the_middle_of_the_effects_left_border() -> None:
    drawing = drawn(fishbone())
    left, top, _, bottom = drawing.effect
    (_, _), (end_x, end_y) = drawing.spine
    assert end_x == pytest.approx(left)
    assert end_y == pytest.approx((top + bottom) / 2)


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


def test_bones_alternate_above_and_below_nearest_the_head_first() -> None:
    drawing = drawn(fishbone())
    first, second, third = drawing.bones
    assert first.above and not second.above and third.above
    # The first two share a slot; the third is farther from the head.
    assert first.junction == pytest.approx(second.junction)
    assert third.junction[0] < first.junction[0]


def test_bones_slant_back_from_the_spine_at_the_theme_angle() -> None:
    drawing = drawn(fishbone())
    for bone in drawing.bones:
        dx = bone.junction[0] - bone.far[0]
        dy = abs(bone.junction[1] - bone.far[1])
        assert dx > 0
        assert dy / dx == pytest.approx(3**0.5, rel=1e-6)  # 60 degrees


def test_causes_read_from_the_category_name_inwards() -> None:
    drawing = drawn(fishbone())
    above, _, below = drawing.bones[0], drawing.bones[1], drawing.bones[2]
    # Above the spine the name is at the top: the first cause is the highest.
    assert above.causes[0].text[1] < above.causes[1].text[1]
    assert below.causes[0].text[1] < below.causes[1].text[1]
    lower = drawn(fishbone(categories=[*fishbone()["categories"][2:], *fishbone()["categories"]]))
    # Below it the name is at the bottom: the first cause is the lowest.
    second = lower.bones[1]
    assert second.causes[0].text[1] > second.causes[1].text[1]


def test_a_root_cause_is_one_heavy_path_from_its_tick_to_the_spine() -> None:
    drawing = drawn(fishbone())
    rooted, ruled_out, plain = drawing.bones
    assert rooted.heavy_from is not None
    assert ruled_out.heavy_from is None and plain.heavy_from is None
    assert rooted.causes[0].role == THEME.fishbone.spine
    strokes = [p for p in drawing.scene.primitives if isinstance(p, Stroke)]
    heavy = [p for p in strokes if p.role == THEME.fishbone.spine]
    assert any(
        p.points[0] == pytest.approx(rooted.heavy_from)
        and p.points[-1] == pytest.approx(rooted.junction)
        for p in heavy
    )
    # No other bone has a heavy piece: the plain bone is drawn whole in the bone role.
    assert any(
        p.role == THEME.fishbone.bone
        and p.points[0] == pytest.approx(plain.far)
        and p.points[-1] == pytest.approx(plain.junction)
        for p in strokes
    )


def test_a_cause_ruled_out_stands_on_a_light_dashed_tick() -> None:
    drawing = drawn(fishbone())
    assert drawing.bones[1].causes[0].role == "aside"
    assert drawing.bones[2].causes[0].role == THEME.fishbone.cause


def test_slant_90_draws_upright_bones_with_the_same_structure() -> None:
    theme = load_theme({"version": 1, "fishbone": {"slant": 90}})
    drawing = drawn(fishbone(), theme)
    reference = drawn(fishbone())
    assert len(drawing.bones) == len(reference.bones)
    for bone, other in zip(drawing.bones, reference.bones, strict=True):
        assert bone.far[0] == pytest.approx(bone.junction[0])
        assert bone.above == other.above
        assert len(bone.causes) == len(other.causes)
        for cause in bone.causes:
            assert cause.text[2] < bone.junction[0]
    assert render(fishbone(), theme=theme).startswith("<svg")


@pytest.mark.parametrize("slant", [20, 95, "steep"])
def test_a_slant_outside_its_range_is_a_theme_error(slant: object) -> None:
    with pytest.raises(ThemeError, match="slant"):
        load_theme({"version": 1, "fishbone": {"slant": slant}})


def test_a_document_too_wide_for_any_wrap_is_a_fit_error_naming_the_longest_cause() -> None:
    long = "Unbreakablewordthatgoesonandonforeverandeverwithoutstopping"
    document = fishbone(
        categories=[
            {"text": f"Category {n}", "causes": [{"text": f"{long}{n}"}]}
            for n in range(FISHBONE_CATEGORY_MAX)
        ]
    )
    with pytest.raises(FitError, match="longest cause"):
        drawn(document)


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def test_the_smallest_fishbone_is_valid() -> None:
    assert validate_document(fishbone()) == ()


def test_a_third_level_is_refused_as_a_second_fishbone() -> None:
    document = fishbone()
    document["categories"][0]["causes"][1]["causes"] = [{"text": "Default of 10"}]
    assert pointers(document) == ["/categories/0/causes/1/causes"]
    assert "second fishbone" in messages(document)


def test_edges_are_refused_with_flow_named() -> None:
    document = fishbone(edges=[{"from": "a", "to": "b"}])
    assert pointers(document) == ["/edges"]
    assert "`flow`" in messages(document)


def test_a_category_with_no_causes_is_refused_suggesting_nothing_found() -> None:
    document = fishbone()
    document["categories"][1]["causes"] = []
    assert pointers(document) == ["/categories/1/causes"]
    assert "nothing found" in messages(document)


def test_one_category_is_refused() -> None:
    document = fishbone()
    document["categories"] = document["categories"][:1]
    assert pointers(document) == ["/categories"]
    assert "at least 2 categories" in messages(document)


def test_past_six_categories_is_refused_at_the_seventh() -> None:
    categories = [
        {"text": f"C{n}", "causes": [{"text": "a cause"}]} for n in range(FISHBONE_CATEGORY_MAX + 1)
    ]
    document = fishbone(categories=categories)
    assert pointers(document) == [f"/categories/{FISHBONE_CATEGORY_MAX}"]
    assert "scannable" in messages(document)


def test_past_five_causes_in_one_category_is_refused_at_the_sixth() -> None:
    document = fishbone()
    document["categories"][0]["causes"] = [
        {"text": f"cause {n}"} for n in range(FISHBONE_CAUSE_MAX + 1)
    ]
    assert pointers(document) == [f"/categories/0/causes/{FISHBONE_CAUSE_MAX}"]
    assert "category" in messages(document) and "list" in messages(document)


def test_a_cause_role_with_a_shape_is_refused() -> None:
    document = fishbone()
    document["categories"][2]["causes"][0]["role"] = "decision"
    assert pointers(document) == ["/categories/2/causes/0/role"]
    assert "tick on a bone" in messages(document)


def test_the_effect_takes_no_role() -> None:
    document = fishbone(effect={"text": "Checkout is slow", "role": "emphasis"})
    assert pointers(document) == ["/effect/role"]
    assert "always drawn as the diagram's emphasis" in messages(document)


def test_the_effect_is_required() -> None:
    document = fishbone()
    del document["effect"]
    assert pointers(document) == ["/effect"]

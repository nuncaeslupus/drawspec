"""A line of text that belongs to the whole diagram, and the field that did not.

Item C of the round-two corpus review. The reviewer asked the same thing on four
drawings and then in general — *"do we have options to add texts outside graphs?
For example, above or below"* — and the answer had been no twice over: there was
no diagram-level text at all, and the `note` that looked like one was accepted by
four objects and drawn by exactly one family.

Both halves are asserted here, because they are one decision: a `caption` belongs
to the diagram, a `note` belongs to an element, and neither may quietly stand in
for the other.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from drawspec.errors import FitError
from drawspec.kinds import scene_for
from drawspec.scene import Scene, TextLine, extents
from drawspec.schema import Document, parse_document, validate_document
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])

CAPTION = "Continuous consultation and review sit outside every ring."


def document(**overrides: object) -> Document:
    base = {
        "version": 1,
        "kind": "rings",
        "title": "What is in scope",
        "rings": [{"text": "The core"}, {"text": "Everything around it"}],
    }
    return parse_document({**base, **overrides})


def caption_lines(scene: Scene) -> list[TextLine]:
    """The caption's own runs: the only ones set at the label level in a rings."""
    return [
        primitive
        for primitive in scene.primitives
        if isinstance(primitive, TextLine) and primitive.level == "label"
    ]


def test_a_caption_is_drawn_outside_the_drawing() -> None:
    plain = scene_for(document(), THEME, MEASURER)
    with_caption = scene_for(document(caption=CAPTION), THEME, MEASURER)

    assert not caption_lines(plain)
    assert caption_lines(with_caption)
    assert with_caption.height > plain.height, "the caption has to make room for itself"


def test_a_caption_below_leaves_the_drawing_where_it_was() -> None:
    """Below is the default, and below costs the drawing nothing."""
    plain = scene_for(document(), THEME, MEASURER)
    below = scene_for(document(caption=CAPTION), THEME, MEASURER)
    assert extents(below.primitives[: len(plain.primitives)])[1] == pytest.approx(
        extents(plain.primitives)[1]
    ), "a caption below moved the drawing"
    assert all(line.y > plain.height for line in caption_lines(below))


def test_a_caption_above_moves_the_drawing_down_to_make_room() -> None:
    """The other half of the setting, so it is a choice rather than a default."""
    theme = replace(THEME, canvas=replace(THEME.canvas, caption="above"))
    above = scene_for(document(caption=CAPTION), theme, MEASURER)
    plain = scene_for(document(), theme, MEASURER)
    lines = caption_lines(above)
    assert lines
    assert all(line.y < plain.height for line in lines)
    assert above.height == pytest.approx(
        scene_for(document(caption=CAPTION), THEME, MEASURER).height
    ), "which side it sits does not change how much room it needs"


def test_a_caption_is_centred_on_the_scene_it_is_added_to() -> None:
    scene = scene_for(document(caption=CAPTION), THEME, MEASURER)
    assert all(line.anchor == "middle" for line in caption_lines(scene))
    assert all(line.x == pytest.approx(scene.width / 2) for line in caption_lines(scene))


def test_a_caption_wider_than_its_drawing_widens_the_scene() -> None:
    """Otherwise it hangs off the side, and `centred` has nothing to work with."""
    narrow = document(rings=[{"text": "One"}, {"text": "Two"}])
    long_caption = document(
        rings=[{"text": "One"}, {"text": "Two"}],
        caption="A caption considerably longer than either of the two very short ring labels",
    )
    assert (
        scene_for(long_caption, THEME, MEASURER).width >= scene_for(narrow, THEME, MEASURER).width
    )


def test_every_kind_takes_a_caption() -> None:
    """It is added once, in the dispatch, so no family can forget it."""
    for kind, payload in (
        ("flow", {"nodes": [{"id": "a", "text": "One"}]}),
        ("stack", {"items": [{"text": "One"}, {"text": "Two"}]}),
        ("pyramid", {"levels": [{"text": "Top"}, {"text": "Bottom"}]}),
    ):
        scene = scene_for(
            parse_document({"version": 1, "kind": kind, "caption": CAPTION, **payload}),
            THEME,
            MEASURER,
        )
        assert caption_lines(scene), f"{kind} drew no caption"


# --------------------------------------------------------------------------
# The field that is accepted everywhere and drawn in one place
# --------------------------------------------------------------------------


def test_a_timeline_still_draws_its_notes() -> None:
    """The one family that has somewhere to put one."""
    scene = scene_for(
        parse_document(
            {
                "version": 1,
                "kind": "timeline",
                "items": [{"text": "Incident", "note": "day 1"}, {"text": "Report"}],
            }
        ),
        THEME,
        MEASURER,
    )
    assert any(
        isinstance(primitive, TextLine) and primitive.spans[0].text == "day 1"
        for primitive in scene.primitives
    )


@pytest.mark.parametrize("kind", ["stack", "columns"])
def test_a_note_a_kind_cannot_draw_is_still_accepted(kind: str) -> None:
    """v1 stays v1, which is the whole of what can be done about it here.

    Only `timeline` draws a note, so on any other kind the field has no effect —
    and a field with no effect is the worst outcome available, because the author
    believes they configured something. The fix that suggests itself is to refuse
    it; the fix that is *available* is not, because a document carrying one
    validated against the published v1 schema and has to keep validating. Removing
    a field is a change of meaning, and a change of meaning ships as v2.

    So the field is accepted and the description says where it is drawn — which
    reaches the author in their editor, before they have written it, rather than
    after a render that shows nothing.
    """
    document = parse_document(
        {"version": 1, "kind": kind, "items": [{"text": "One", "note": "an aside"}]}
    )
    assert document.items[0].note == "an aside"
    assert not validate_document(
        {"version": 1, "kind": kind, "items": [{"text": "One", "note": "an aside"}]}
    )


@pytest.mark.parametrize(
    "collection,name", [("nodes", "node"), ("levels", "level"), ("stages", "stage")]
)
def test_note_is_still_offered_by_every_object_that_offered_it(collection: str, name: str) -> None:
    """Removing it from the tables would fail documents the published schema allows."""
    from drawspec.schema import OBJECTS

    assert "note" in {field.name for field in OBJECTS[name]}


def test_the_note_description_says_where_it_is_drawn() -> None:
    """The one thing v1 can do about a field that does nothing: say so, in the schema.

    This is load-bearing rather than cosmetic — it is the whole remedy — so it is
    asserted rather than left to survive an edit.
    """
    from drawspec.schema import OBJECTS

    for name in ("node", "item", "level", "stage"):
        (note,) = [field for field in OBJECTS[name] if field.name == "note"]
        assert "timeline" in note.description
        assert "caption" in note.description


def test_a_caption_that_will_not_fit_says_it_is_the_caption() -> None:
    """Otherwise the author is told to restructure a diagram that was fine.

    The caption is broken inside the elastic fit, like everything else, and
    `fit`'s own message only knows that *something* would not go — so a document
    whose drawing fits and whose caption has one unbreakable word in it would be
    told the diagram does not fit at any type size.
    """
    with pytest.raises(FitError, match="caption"):
        scene_for(
            document(caption="Unbreakablesequenceoflettersfarwiderthananycanvas" * 4),
            THEME,
            MEASURER,
        )

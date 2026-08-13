"""Groups — a box drawn around other boxes.

The schema declared `groups` and the theme declared a `group` role from v1, and
nothing drew either; six of the 89 originals in `docs/kinds-wanted.md` need one.
Every assertion here is about containment, because that is the whole claim a
frame makes: what is inside it is inside it.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from drawspec.errors import DrawspecError
from drawspec.kinds.common import line_bounds
from drawspec.kinds.containers import GROUP_ROLE, Frame, nesting_of
from drawspec.kinds.graph import GraphDrawing, graph_drawing, graph_scene
from drawspec.scene import Rect, TextLine
from drawspec.schema import Document, load_document, parse_document
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

THEME = load_theme()
MEASURER = TextMeasurer(THEME.font.stacks(), search_paths=[])


def flow(
    nodes: Sequence[tuple[str, str]],
    edges: Sequence[tuple[str, str]],
    groups: Sequence[tuple[str, str, tuple[str, ...]]],
) -> Document:
    document = {
        "version": 1,
        "kind": "flow",
        "title": "A grouped flow",
        "nodes": [{"id": i, "text": t} for i, t in nodes],
        "edges": [{"from": s, "to": t} for s, t in edges],
        "groups": [{"id": i, "text": t, "members": list(m)} for i, t, m in groups],
    }
    return parse_document(document)


FLAT = flow(
    [("a", "The first"), ("b", "The second"), ("c", "The third")],
    [("a", "b"), ("b", "c")],
    [("pair", "Two of them", ("a", "b"))],
)

NESTED = flow(
    [("a", "The first"), ("b", "The second"), ("c", "The third")],
    [("a", "c")],
    [("inner", "Inside", ("a", "b")), ("outer", "Outside", ("inner",))],
)


def drawing(document: Document) -> GraphDrawing:
    return graph_drawing(document, THEME, MEASURER)


def frame_named(built: GraphDrawing, identifier: str) -> Frame:
    for frame in built.frames:
        if frame.id == identifier:
            return frame
    raise AssertionError(f"no frame {identifier!r} in {[f.id for f in built.frames]}")


def test_a_group_becomes_a_frame_around_its_members() -> None:
    """The one claim a container makes."""
    built = drawing(FLAT)
    frame = frame_named(built, "pair")
    for member in ("a", "b"):
        box = built.boxes[member]
        assert frame.x <= box.x and box.x + box.width <= frame.right, member
        assert frame.y <= box.y and box.y + box.height <= frame.bottom, member


def test_a_box_outside_the_group_stays_outside_the_frame() -> None:
    """Otherwise the frame says something false about the diagram."""
    built = drawing(FLAT)
    frame = frame_named(built, "pair")
    box = built.boxes["c"]
    inside = frame.x <= box.x and box.x + box.width <= frame.right
    inside = inside and frame.y <= box.y and box.y + box.height <= frame.bottom
    assert not inside


def test_a_nested_group_sits_inside_its_parent() -> None:
    """Nesting is layout inside layout, so the frames must nest too."""
    built = drawing(NESTED)
    inner = frame_named(built, "inner")
    outer = frame_named(built, "outer")
    assert outer.x <= inner.x and inner.right <= outer.right
    assert outer.y <= inner.y and inner.bottom <= outer.bottom
    assert inner.depth > outer.depth


def test_a_caption_never_sits_on_a_member_of_its_own_group() -> None:
    """A caption is a label of the container, not a title over its contents."""
    built = drawing(FLAT)
    frame = frame_named(built, "pair")
    caption = frame.caption
    assert caption is not None
    for member in ("a", "b"):
        box = built.boxes[member]
        assert not (
            caption.x < box.x + box.width
            and box.x < caption.x + caption.width
            and caption.y < box.y + box.height
            and box.y < caption.y + caption.height
        ), member


def test_a_caption_stays_inside_its_own_frame() -> None:
    built = drawing(NESTED)
    for identifier in ("inner", "outer"):
        frame = frame_named(built, identifier)
        caption = frame.caption
        assert caption is not None
        assert frame.x <= caption.x
        assert caption.x + caption.width <= frame.right + 1e-6
        assert frame.y <= caption.y
        assert caption.y + caption.height <= frame.bottom


def test_no_route_crosses_a_frame_caption() -> None:
    """Rule 5 of the review, applied to the one piece of text a frame owns.

    Against the reference document rather than the fixture above, because this
    only bites when an edge arrives into a group *from outside*: it comes down
    on the first box's port, and the caption is what it meets on the way.
    """
    built = drawing(load_document("docs/reference/flow-groups.json"))
    for frame in built.frames:
        caption = frame.caption
        assert caption is not None
        for route in built.routes:
            for (x1, y1), (x2, y2) in zip(route.points, route.points[1:], strict=False):
                left, right = sorted((x1, x2))
                top, bottom = sorted((y1, y2))
                assert not (
                    left < caption.x + caption.width
                    and caption.x < right
                    and top < caption.y + caption.height
                    and caption.y < bottom
                ), (frame.id, route.source, route.target)


def test_a_frame_is_drawn_before_what_it_contains() -> None:
    """A container is behind its contents; its dashed border is never on top."""
    scene = graph_scene(FLAT, THEME, MEASURER)
    kinds = [type(item).__name__ for item in scene.primitives]
    frames = [
        index
        for index, item in enumerate(scene.primitives)
        if isinstance(item, Rect) and item.role == GROUP_ROLE
    ]
    assert frames, "the group should have produced a frame"
    assert max(frames) < kinds.index("Path"), "frames come before the routes"


def test_a_group_caption_is_set_at_the_same_level_as_every_other_label() -> None:
    """One type size on a page — the rule the pyramid learned the hard way."""
    scene = graph_scene(FLAT, THEME, MEASURER)
    levels = {item.level for item in scene.primitives if isinstance(item, TextLine)}
    assert levels == {"body"}


def test_a_caption_line_fits_the_frame_it_labels() -> None:
    built = drawing(FLAT)
    scene = graph_scene(FLAT, THEME, MEASURER)
    frame = frame_named(built, "pair")
    captions = [
        item for item in scene.primitives if isinstance(item, TextLine) and item.role == GROUP_ROLE
    ]
    assert captions
    for line in captions:
        left, right = line_bounds(line, THEME, MEASURER)
        assert frame.x <= left and right <= frame.right


def test_a_box_claimed_by_two_groups_is_refused() -> None:
    """A box sits inside one container or none, and the message says which two."""
    document = flow(
        [("a", "One"), ("b", "Two")],
        [("a", "b")],
        [("left", "Left", ("a",)), ("right", "Right", ("a",))],
    )
    with pytest.raises(DrawspecError) as error:
        nesting_of(document)
    assert "'a'" in str(error.value)
    assert "left" in str(error.value) and "right" in str(error.value)


def test_a_group_that_contains_itself_is_refused() -> None:
    document = parse_document(
        {
            "version": 1,
            "kind": "flow",
            "title": "A loop of containers",
            "nodes": [{"id": "a", "text": "One"}],
            "groups": [
                {"id": "one", "members": ["two"]},
                {"id": "two", "members": ["one"]},
            ],
        }
    )
    with pytest.raises(DrawspecError) as error:
        nesting_of(document)
    assert "contains itself" in str(error.value)


def test_a_document_with_no_groups_draws_no_frames() -> None:
    """Groups cost nothing when nobody asked for one."""
    plain = flow([("a", "One"), ("b", "Two")], [("a", "b")], [])
    assert drawing(plain).frames == ()

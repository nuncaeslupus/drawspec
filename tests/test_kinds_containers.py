"""Groups — a box drawn around other boxes.

The schema declared `groups` and the theme declared a `group` role from v1, and
nothing drew either; six of the 89 originals in `docs/kinds-wanted.md` need one.
Every assertion here is about containment, because that is the whole claim a
frame makes: what is inside it is inside it.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from drawspec.errors import DrawspecError
from drawspec.kinds.common import line_bounds
from drawspec.kinds.containers import GROUP_ROLE, Frame, nesting_of
from drawspec.kinds.graph import GraphDrawing, graph_drawing, graph_scene
from drawspec.scene import Rect, TextLine
from drawspec.schema import Document, load_document, parse_document
from drawspec.text import TextMeasurer
from drawspec.theme import load_theme

REFERENCE_DIR = Path(__file__).resolve().parents[1] / "docs" / "reference"

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


def test_an_edge_label_never_lands_on_a_group_caption() -> None:
    """A caption is words, and two sets of words in one place are neither of them.

    The routes were already told to avoid a caption; the labels were not, so
    "assigns work" was drawn on top of "Another worker" and the pair read as one
    smudge. Both are text placed after the fact, and both dodge the same thing.
    """
    document = load_document(REFERENCE_DIR / "flow-groups.json")
    built = drawing(document)
    assert built.labels, "this document is only a test while it still has edge labels"
    for frame in built.frames:
        caption = frame.caption
        if caption is None:
            continue
        for label in built.labels:
            left, top, right, bottom = label.box
            assert not (
                caption.x < right
                and left < caption.x + caption.width
                and caption.y < bottom
                and top < caption.y + caption.height
            ), (label.text, frame.id)


def test_group_members_are_laid_out_in_the_order_they_were_written() -> None:
    """A group's members are an ordered set, and the order is the author's.

    They were laid out in id order, so the Kubernetes control plane came out
    *cloud-controller-manager, etcd, kube-apiserver, …* — alphabetical, which is
    neither the order the source draws nor a meaningful one.
    """
    written = ("kube-apiserver", "etcd", "kube-scheduler", "cloud-cm")
    document = flow(
        [(identifier, identifier) for identifier in written],
        [],
        [("cp", "Control plane", written)],
    )
    built = drawing(document)
    placed = sorted(written, key=lambda i: (built.boxes[i].y, built.boxes[i].x))
    assert tuple(placed) == written


def test_two_top_level_groups_keep_the_order_their_members_were_written_in() -> None:
    """Roots were read out of a `frozenset`, whose iteration order follows the
    interpreter's hash seed — so the same document could render two ways. A
    group now sits where its first member was written, which is the only
    position the document gives it."""
    document = flow(
        [("a", "One"), ("b", "Two"), ("c", "Three"), ("d", "Four")],
        [],
        [("second", "Later", ("c", "d")), ("first", "Earlier", ("a", "b"))],
    )
    built = drawing(document)
    earlier = frame_named(built, "first")
    later = frame_named(built, "second")
    assert (earlier.y, earlier.x) < (later.y, later.x)


def test_a_group_sits_where_its_earliest_member_was_written_not_its_first() -> None:
    """A group has no position of its own — `groups` is a second array — so it
    takes the earliest position its content occupies.

    Not `members[0]`: that would tie a container's place among its siblings to
    which of its own members it happens to list first, so reordering the inside
    of a container would move the container. Here `late` lists `d` first and
    `a` second, and it still sorts before the loose node `b`, because `a` is
    where its content starts.
    """
    document = flow(
        [("a", "One"), ("b", "Two"), ("c", "Three"), ("d", "Four")],
        [],
        [("late", "Lists d first", ("d", "a"))],
    )
    nesting = nesting_of(document)
    assert nesting.roots == ("late", "b", "c")


def test_a_long_label_does_not_set_the_width_of_a_box_in_another_container() -> None:
    """The half of `uniform-box-size` that round three left: the shared width.

    Sharing a width is what makes peers read as peers, and across a whole document
    it became one long paragraph setting the width of every box in the drawing.
    Seven boxes on the nested-boxes sheet all came out 243.5 wide, the one holding
    the word *AGE* included, because a three-line paragraph lived somewhere else.
    """
    built = drawing(
        flow(
            [
                ("age", "AGE"),
                ("ccaa", "CCAA"),
                ("eell", "EELL"),
                (
                    "note",
                    "Each administration keeps its own inventory of processing "
                    "activities, and the register of them is public.",
                ),
            ],
            [("age", "note")],
            [("admins", "Administrations", ("age", "ccaa", "eell"))],
        )
    )
    inside = [built.boxes[name].width for name in ("age", "ccaa", "eell")]
    assert len(set(inside)) == 1, "peers in one container still share an edge"
    assert built.boxes["note"].width > inside[0] * 2, "and the paragraph keeps its own width"


def test_peers_in_the_same_container_still_share_an_edge() -> None:
    """The alignment is the point of normalising; only its scope changed."""
    built = drawing(FLAT)
    assert built.boxes["a"].width == built.boxes["b"].width


def test_two_containers_are_normalised_apart() -> None:
    """A box is compared against what sits beside it, not against the whole page."""
    built = drawing(
        flow(
            [("a", "x"), ("b", "y"), ("c", "a very much longer label than the others here")],
            [("a", "c")],
            [("left", "Left", ("a", "b")), ("right", "Right", ("c",))],
        )
    )
    assert built.boxes["a"].width == built.boxes["b"].width
    assert built.boxes["c"].width > built.boxes["a"].width

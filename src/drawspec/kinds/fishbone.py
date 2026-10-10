"""The `fishbone` kind: one effect, its causes grouped by category.

An Ishikawa diagram. Its claim is fixed — one effect; causes grouped into
categories; nothing deeper — and so is its shape: everything flows into the
head. Drawn as a two-level `tree` it reads the other way round, the effect on
top as if it owned its causes.

**The spine** runs across the page into the effect's box, which is the head at
the right end, drawn in the `emphasis` role. The spine meets the box's left
border at its middle.

**The bones** are the categories, alternately above and below the spine,
nearest the head first, each slanting back from the spine at the theme's
`[fishbone] slant` — the one diagonal drawspec draws on purpose, because the
slant is the shape. The two bones of a slot meet the spine at one point. Every
bone is as long as the longest stack of causes, so the fish is symmetric and a
short category reads as short. The category's name sits beyond the bone's far
end, in bold.

**A cause** is a horizontal tick off its bone with the words standing on it,
set to end just short of the bone so they read away from it and never cross it.
They are listed from the category's name inwards, the order written. A
confirmed root cause (`emphasis`) is bold, and its tick and the rest of its bone
down to the spine are drawn in the spine's role, so the path from that cause to
the effect is one heavy line in greyscale. A cause ruled out (`note`) stands on
a light dashed tick.

**Spacing along the spine** is what keeps neighbouring bones' words apart: a
slot is as wide as its widest cause, measured from where its bones meet the
spine. When the whole does not fit the canvas, the causes wrap narrower until
it does; when no width works, `FitError` names the longest cause.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Final

from drawspec.errors import FitError
from drawspec.geometry import Box, size_box
from drawspec.kinds.common import outline, text_runs
from drawspec.scene import Path, Primitive, Scene, TextLine, TextSpan, moved
from drawspec.schema import Cause, Document
from drawspec.text.measure import TextMeasurer
from drawspec.text.wrap import TextBlock, wrap
from drawspec.theme import Theme

#: The most of the canvas the effect's box may take, and a category's name.
EFFECT_SHARE: Final = 0.24
CATEGORY_SHARE: Final = 0.26

#: The narrowest a cause may be wrapped to, as a share of the canvas, before the
#: drawing is refused as too wide.
CAUSE_MIN_SHARE: Final = 0.12

#: Each narrower attempt at the causes' width is this share of the one before.
CAUSE_STEP: Final = 0.92

#: Lengths in units, a unit being the body size over eleven, so the spacing
#: shrinks with the type when the fit pass shrinks it.
END_GAP: Final = 8.0
"""Along a bone: from its far end to the first cause, and from the last to the spine."""
CAUSE_GAP: Final = 7.0
"""Along a bone: from one cause's tick to the top of the next cause's words."""
TEXT_GAP: Final = 3.5
"""From the bottom of a cause's words to the tick they stand on."""
BONE_GAP: Final = 5.0
"""Across: from the end of a cause's words to its bone."""
OVERHANG: Final = 3.0
"""How far a tick runs past the start of its words."""
LABEL_GAP: Final = 5.0
"""From a bone's far end to its category's name."""
SLOT_GAP: Final = 14.0
"""Across: between one slot's causes and the next slot's bones."""
HEAD_GAP: Final = 20.0
"""Along the spine: from the nearest bones to the effect's box."""
SPINE_STEP: Final = 28.0
"""Along the spine: the least distance between two slots' junctions."""
SLICE: Final = 4.0
"""The height of each slice a slanted bone is cut into when slots are spaced."""
TAIL: Final = 14.0
"""Along the spine: past the farthest bones, when they are upright."""

#: A rectangle: left, top, right, bottom.
type _Rect = tuple[float, float, float, float]

#: How many halvings the search for a balanced line break takes.
BALANCE_STEPS: Final = 10

#: The edge role a ruled-out cause's tick is drawn in: light and dashed.
RULED_OUT_ROLE: Final = "aside"


@dataclass(frozen=True)
class CauseDrawn:
    """Where one cause landed: its words' bounds, its tick, and the role drawn."""

    text: tuple[float, float, float, float]
    """Left, top, right, bottom of the words, as drawspec measured them."""

    tick: tuple[tuple[float, float], tuple[float, float]]
    """From the open end to the point on the bone."""

    role: str


@dataclass(frozen=True)
class BoneDrawn:
    """One category's bone, from its far end to the spine, and its causes."""

    far: tuple[float, float]
    junction: tuple[float, float]
    """Where the bone meets the spine."""

    heavy_from: tuple[float, float] | None
    """Where the bone turns to the spine's role, for a category with a root cause."""

    label: tuple[float, float, float, float]
    """Left, top, right, bottom of the category's name."""

    causes: tuple[CauseDrawn, ...] = ()
    above: bool = True


@dataclass(frozen=True)
class FishboneDrawing:
    """The finished geometry, in final coordinates, for tests and the scene."""

    scene: Scene
    effect: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)
    """The head box: left, top, right, bottom."""

    spine: tuple[tuple[float, float], tuple[float, float]] = ((0.0, 0.0), (0.0, 0.0))
    bones: tuple[BoneDrawn, ...] = field(default_factory=tuple)


def fishbone_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Draw `document` as a fishbone."""
    return fishbone_drawing(document, theme, measurer).scene


def fishbone_drawing(document: Document, theme: Theme, measurer: TextMeasurer) -> FishboneDrawing:
    """Lay the fishbone out, wrapping its causes narrower until it fits the canvas.

    Raises:
        FitError: no width for the causes fits the canvas, or a word is wider
            than the narrowest width a cause may have.
    """
    width = theme.canvas.width
    causes = [cause for category in document.categories for cause in category.causes]
    natural = max(_natural(_words(cause), theme, measurer) for cause in causes)
    floor = width * CAUSE_MIN_SHARE
    cap = natural
    while True:
        drawing = _attempt(document, theme, measurer, max(cap, floor))
        if drawing is not None:
            return drawing
        if cap <= floor:
            break
        cap *= CAUSE_STEP
    longest = max(causes, key=lambda cause: _natural(_words(cause), theme, measurer))
    raise FitError(
        f"the fishbone does not fit a width of {width:.0f}, even with every cause wrapped "
        f"to {floor:.0f}. The longest cause is {longest.text[:48]!r}: shorten it, use fewer "
        f"categories, or give the diagram more width."
    )


@dataclass
class _Bone:
    """A bone laid out about its own junction at (0, 0), before slots are placed."""

    above: bool
    run: float
    length: float
    label: TextBlock
    causes: list[tuple[Cause, TextBlock, float, float, float, float]]
    """Each cause, its block, its words' left, top, its tick's y and its tick's bone x."""

    def rects(self, unit: float) -> list[_Rect]:
        """The bone's ink as rectangles about its junction: words, ticks, name, bone.

        The slanted bone is cut into short slices, each its own rectangle, so a
        neighbouring slot's words may sit beside the part of the bone that leans
        away from them — which is what lets the slots interleave.
        """
        sign = -1.0 if self.above else 1.0
        found: list[_Rect] = []
        for _, block, left, top, tick, bone_x in self.causes:
            found.append((left, min(top, tick), left + OVERHANG * unit + block.width, tick))
            found.append((left, tick - unit, bone_x, tick + unit))
        far_x = -self.run
        gap = LABEL_GAP * unit
        label_y = (
            sign * self.length - gap - self.label.height if self.above else sign * self.length + gap
        )
        found.append(
            (
                far_x - self.label.width / 2,
                label_y,
                far_x + self.label.width / 2,
                label_y + self.label.height,
            )
        )
        slices = max(1, math.ceil(self.length / (SLICE * unit)))
        cot = self.run / self.length if self.length else 0.0
        for index in range(slices):
            near, far = self.length * index / slices, self.length * (index + 1) / slices
            low, high = sorted((sign * near, sign * far))
            found.append((-far * cot - unit, low, -near * cot + unit, high))
        return found


def _attempt(
    document: Document, theme: Theme, measurer: TextMeasurer, cap: float
) -> FishboneDrawing | None:
    """The drawing with every cause wrapped to `cap`, or `None` if it is too wide."""
    unit = theme.scale["body"] / 11
    width = theme.canvas.width
    angle = math.radians(theme.fishbone.slant)
    cot = math.cos(angle) / math.sin(angle)
    overhang = OVERHANG * unit

    try:
        blocks = [
            [_block(_words(cause), cap, theme, measurer) for cause in category.causes]
            for category in document.categories
        ]
    except FitError:
        return None

    # Every bone as long as the longest stack of causes, so the fish is
    # symmetric and a category with one cause is still a bone, not a stub.
    def stack(category_blocks: list[TextBlock]) -> float:
        return (
            2 * END_GAP * unit
            + sum(block.height + TEXT_GAP * unit for block in category_blocks)
            + (len(category_blocks) - 1) * CAUSE_GAP * unit
        )

    length = max(stack(category_blocks) for category_blocks in blocks)
    run = length * cot
    bones: list[_Bone] = []
    for index, (category, category_blocks) in enumerate(
        zip(document.categories, blocks, strict=True)
    ):
        above = index % 2 == 0
        label = _labelled(category.text, width * CATEGORY_SHARE, theme, measurer)
        stacked: list[tuple[Cause, TextBlock, float, float, float, float]] = []
        cursor = length - END_GAP * unit
        for cause, block in zip(category.causes, category_blocks, strict=True):
            # Distances from the spine, measured outwards; the first cause is the
            # one nearest the category's name.
            if above:
                top_out = cursor
                tick_out = cursor - block.height - TEXT_GAP * unit
                cursor = tick_out - CAUSE_GAP * unit
                top, tick = -top_out, -tick_out
                farthest = top_out
            else:
                tick_out = cursor
                top_out = cursor - TEXT_GAP * unit - block.height
                cursor = top_out - CAUSE_GAP * unit
                top, tick = top_out, tick_out
                farthest = tick_out
            right = -farthest * cot - BONE_GAP * unit
            left = right - block.width
            stacked.append((cause, block, left - overhang, top, tick, -tick_out * cot))
        bones.append(_Bone(above=above, run=run, length=length, label=label, causes=stacked))

    # Slots along the spine, nearest the head first; the two bones of a slot meet
    # the spine at one point. Each slot goes as near the head as it can while
    # everything in it stays left of whatever it shares a height with.
    effect = _effect(document.effect, width * EFFECT_SHARE, theme, measurer)
    slots = [bones[index : index + 2] for index in range(0, len(bones), 2)]
    placed: list[_Rect] = [(0.0, -effect.height / 2, effect.width, effect.height / 2)]
    junctions: list[float] = []
    gap = SLOT_GAP * unit
    for number, slot in enumerate(slots):
        x = -HEAD_GAP * unit if number == 0 else junctions[-1] - SPINE_STEP * unit
        rects = [rect for bone in slot for rect in bone.rects(unit)]
        for _, top, right, bottom in rects:
            for p_left, p_top, _, p_bottom in placed:
                if top < p_bottom + unit and p_top < bottom + unit:
                    x = min(x, p_left - gap - right)
        junctions.append(x)
        placed.extend((x + x0, y0, x + x1, y1) for x0, y0, x1, y1 in rects)

    spine_start = junctions[-1] - max(TAIL * unit, *(bone.run for bone in slots[-1]))
    leftmost = min(spine_start, *(rect[0] for rect in placed))
    if effect.width - leftmost > width + 1e-6:
        return None

    primitives: list[Primitive] = []
    texts: list[Primitive] = []
    drawn: list[BoneDrawn] = []
    label_gap = LABEL_GAP * unit
    for number, bone in enumerate(bones):
        junction = junctions[number // 2]
        sign = -1.0 if bone.above else 1.0
        far = (junction - bone.run, sign * bone.length)
        heavy: tuple[float, float] | None = None
        causes_drawn: list[CauseDrawn] = []
        for cause, block, left, top, tick, bone_x in bone.causes:
            open_end = (junction + left, tick)
            on_bone = (junction + bone_x, tick)
            role = (
                theme.fishbone.spine
                if cause.role == "emphasis"
                else RULED_OUT_ROLE
                if cause.role == "note"
                else theme.fishbone.cause
            )
            primitives.append(Path(role, points=(open_end, on_bone)))
            text_left = junction + left + overhang
            texts.extend(_lines(block, text_left + block.width, top, cause.role))
            causes_drawn.append(
                CauseDrawn(
                    text=(text_left, top, text_left + block.width, top + block.height),
                    tick=(open_end, on_bone),
                    role=role,
                )
            )
            if cause.role == "emphasis" and heavy is None:
                heavy = on_bone
        point = (junction, 0.0)
        if heavy is None:
            primitives.append(Path(theme.fishbone.bone, points=(far, point)))
        else:
            primitives.append(Path(theme.fishbone.bone, points=(far, heavy)))
            primitives.append(Path(theme.fishbone.spine, points=(heavy, point)))
        label_top = far[1] - label_gap - bone.label.height if bone.above else far[1] + label_gap
        texts.extend(_centred(bone.label, far[0], label_top))
        drawn.append(
            BoneDrawn(
                far=far,
                junction=point,
                heavy_from=heavy,
                label=(
                    far[0] - bone.label.width / 2,
                    label_top,
                    far[0] + bone.label.width / 2,
                    label_top + bone.label.height,
                ),
                causes=tuple(causes_drawn),
                above=bone.above,
            )
        )

    head = effect.moved_to(0.0, -effect.height / 2)
    primitives.append(Path(theme.fishbone.spine, points=((spine_start, 0.0), (0.0, 0.0))))
    primitives.extend(outline(head, theme))
    texts.extend(text_runs(head, theme, measurer))

    # Frame: everything shifted so the ink starts at the origin.
    top = min(
        -effect.height / 2,
        *(bone.label[1] for bone in drawn),
        *(cause.text[1] for bone in drawn for cause in bone.causes),
    )
    bottom = max(
        effect.height / 2,
        *(bone.label[3] for bone in drawn),
        *(cause.text[3] for bone in drawn for cause in bone.causes),
    )
    dx, dy = -leftmost, -top
    scene = Scene(
        width=effect.width - leftmost,
        height=bottom - top,
        primitives=tuple(moved(primitive, dx, dy) for primitive in (*primitives, *texts)),
        title=document.title,
        description=document.description,
    )
    return FishboneDrawing(
        scene=scene,
        effect=(dx, -effect.height / 2 + dy, dx + effect.width, effect.height / 2 + dy),
        spine=((spine_start + dx, dy), (dx, dy)),
        bones=tuple(_shifted(bone, dx, dy) for bone in drawn),
    )


def _effect(text: str, width: float, theme: Theme, measurer: TextMeasurer) -> Box:
    """The head box, balanced like a cause: as narrow as it goes on as many lines."""

    def sized(limit: float) -> Box:
        return size_box(
            text,
            theme=theme,
            measurer=measurer,
            role="emphasis",
            level="body",
            max_width=limit,
            shape="rect",
        )

    try:
        box = sized(width)
    except FitError as error:
        raise FitError(
            f"the effect {text[:40]!r} has a word wider than the {width:.0f} units its box "
            f"can have. Shorten it, or give the diagram more width."
        ) from error
    lines = len(box.block.lines)
    if lines < 2:
        return box
    low, high = width / 2, width
    for _ in range(BALANCE_STEPS):
        middle = (low + high) / 2
        try:
            trial = sized(middle)
        except FitError:
            low = middle
            continue
        if len(trial.block.lines) == lines:
            high, box = middle, trial
        else:
            low = middle
    return box


def _shifted(bone: BoneDrawn, dx: float, dy: float) -> BoneDrawn:
    def point(value: tuple[float, float]) -> tuple[float, float]:
        return (value[0] + dx, value[1] + dy)

    def bounds(value: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
        return (value[0] + dx, value[1] + dy, value[2] + dx, value[3] + dy)

    return BoneDrawn(
        far=point(bone.far),
        junction=point(bone.junction),
        heavy_from=None if bone.heavy_from is None else point(bone.heavy_from),
        label=bounds(bone.label),
        causes=tuple(
            CauseDrawn(
                text=bounds(cause.text),
                tick=(point(cause.tick[0]), point(cause.tick[1])),
                role=cause.role,
            )
            for cause in bone.causes
        ),
        above=bone.above,
    )


def _words(cause: Cause) -> str:
    """A cause's words as set: a confirmed root cause is bold throughout."""
    if cause.role == "emphasis":
        return "\n".join(
            f"**{line.replace('**', '')}**" if line.strip() else line
            for line in cause.text.split("\n")
        )
    return cause.text


def _natural(text: str, theme: Theme, measurer: TextMeasurer) -> float:
    """How wide `text` is set on its own lines, unbroken."""
    return wrap(text, 1e6, measurer, theme=theme, level="body").width


def _block(text: str, width: float, theme: Theme, measurer: TextMeasurer) -> TextBlock:
    """`text` wrapped to `width`, then as narrow as it goes on as many lines.

    Balanced, so a cause that needs two lines breaks near its middle rather than
    leaving one word on the second: the same lines, the least ragged.
    """
    block = wrap(text, width, measurer, theme=theme, level="body")
    low, high = width / 2, width
    if len(block.lines) < 2:
        return block
    for _ in range(BALANCE_STEPS):
        middle = (low + high) / 2
        try:
            trial = wrap(text, middle, measurer, theme=theme, level="body")
        except FitError:
            low = middle
            continue
        if len(trial.lines) == len(block.lines):
            high, block = middle, trial
        else:
            low = middle
    return block


def _labelled(text: str, width: float, theme: Theme, measurer: TextMeasurer) -> TextBlock:
    """A category's name, bold, wrapped to its share of the canvas."""
    bold = f"**{text.replace('**', '')}**"
    try:
        return wrap(bold, width, measurer, theme=theme, level="body")
    except FitError as error:
        raise FitError(
            f"the category {text[:40]!r} has a word wider than the {width:.0f} units a "
            f"category's name can have. Shorten it, or give the diagram more width."
        ) from error


def _lines(
    block: TextBlock, x: float, top: float, role: str, anchor: str = "end"
) -> list[TextLine]:
    found: list[TextLine] = []
    for index, line in enumerate(block.lines):
        spans = tuple(
            TextSpan(text=span.text, font=span.font, weight=span.weight)
            for span in line.spans
            if span.text
        )
        if spans:
            found.append(
                TextLine(role, x=x, y=top + block.baseline(index), spans=spans, anchor=anchor)
            )
    return found


def _centred(block: TextBlock, x: float, top: float) -> list[TextLine]:
    return _lines(block, x, top, "step", anchor="middle")


__all__ = [
    "BoneDrawn",
    "CauseDrawn",
    "FishboneDrawing",
    "fishbone_drawing",
    "fishbone_scene",
]

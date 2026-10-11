"""The `sequence` kind: who says what to whom, in order.

A layout family of its own, and the simplest one: nothing is ranked or routed.
Participants are columns in the order written, messages are rows in the order
written, and every decision left is a width or a height.

**Columns** are as far apart as their messages need. Every gap starts wide
enough for the two heads either side of it and for whatever hangs off the
lifeline on its left — activation bars, a message to itself and its label —
and then each message, shortest span first, widens the gaps it crosses evenly
until its label fits over its arrow. A diagram that ends up wider than the
canvas is tried again with heads and labels wrapped narrower, and only then
refused, naming the longest label.

**Rows** are as tall as their labels. A message is its label with the arrow
under it; a message to itself is a hook beside its label; a fragment adds a row
for its tab above its first message and a frame's padding below its last, and
each `else` a row for its divider and condition.

**Activation bars are inferred.** A call (`flow` or `strong`) from A to B is
answered by the first later `weak` reply from B to A, and B carries a bar from
the call's row to the reply's. Calls inside calls nest their bars, each set half
a bar to the right of the one it is inside. An unanswered call gets no bar,
which is the honest drawing of an asynchronous one.

**Nothing crosses a word.** A label over a long message sits across the
lifelines between its ends, and the frame of a group of lifelines may run
through a label that crosses it; both are `Path`s, and `drawspec.clearance`
breaks them under the words like every other stroke.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Final

from drawspec.errors import FitError
from drawspec.geometry import Box, size_box
from drawspec.kinds.common import box_primitives
from drawspec.routing import Route, edge_primitives
from drawspec.scene import Ellipse, Path, Polygon, Primitive, Scene, TextLine, TextSpan, moved
from drawspec.schema import Document, Fragment, Message
from drawspec.text.measure import TextMeasurer
from drawspec.text.wrap import TextBlock, wrap
from drawspec.theme import Theme

#: The role a fragment's frame and its tab are drawn in: a thin solid line, so
#: it reads as a frame round messages and not as one of them.
FRAME: Final = "link"

#: The role an `else` divider is drawn in — dashed, as UML draws one.
DIVIDER: Final = "aside"

#: The role an activation bar is outlined in: the weight of a call's arrow.
BAR: Final = "flow"

#: The role a group of lifelines is framed in, as a `flow` frames its groups.
GROUP: Final = "group"

#: The role the stick figure's head is outlined in: the default box's line, as a
#: state machine's dot borrows it.
FIGURE_HEAD_ROLE: Final = "step"

#: The role a message's note is set in.
NOTE: Final = "note"

#: The participant role drawn as a person: the UML stick figure, its name under it.
ACTOR: Final = "actor"

#: The stick figure's parts, in units, and the role its strokes are drawn in —
#: the weight of a call's arrow, as an activation bar is.
FIGURE: Final = "flow"
FIGURE_HEAD: Final = 6.0
FIGURE_BODY: Final = 13.0
FIGURE_LEGS: Final = 12.0
FIGURE_WIDTH: Final = 20.0
FIGURE_HEIGHT: Final = FIGURE_HEAD * 2 + FIGURE_BODY + FIGURE_LEGS
FIGURE_GAP: Final = 4.0

#: The message roles that open an activation bar on their receiver.
CALLS: Final = ("flow", "strong")

#: The message role that closes one.
REPLY: Final = "weak"

#: What share of the canvas a head, a label and a note may be wrapped to — widest
#: first. A diagram that does not fit is tried again a step narrower before it is
#: refused, so a long label wraps to two lines rather than widening every gap.
WIDTHS: Final = ((0.22, 0.34, 0.26), (0.18, 0.27, 0.2), (0.15, 0.21, 0.16))

#: Lengths in units, a unit being the body size over eleven, so the spacing
#: shrinks with the type when the fit pass shrinks it.
HEAD_GAP: Final = 16.0
LABEL_MARGIN: Final = 6.0
LABEL_GAP: Final = 3.0
ROW_GAP: Final = 10.0
HOOK: Final = 18.0
HOOK_DROP: Final = 14.0
FRAME_PAD: Final = 8.0
GROUP_PAD: Final = 8.0
TAB_PAD: Final = 4.0
TAB_CUT: Final = 5.0
BAR_OVERHANG: Final = 3.0


@dataclass(frozen=True)
class Activation:
    """One activation bar: a participant busy from a call's row to its reply's."""

    participant: int
    start: int
    """The index of the call that opened it."""

    end: int
    """The index of the reply that closed it."""

    depth: int
    """How many bars on the same lifeline it is inside."""


@dataclass(frozen=True)
class SequenceDrawing:
    """The finished geometry, in final coordinates, for tests and the scene."""

    scene: Scene
    lifelines: dict[str, float] = field(default_factory=dict)
    """Each participant's lifeline x."""

    arrows: tuple[tuple[tuple[float, float], ...], ...] = ()
    """Each message's route, in message order: tail first, head last."""

    bars: tuple[tuple[Activation, tuple[float, float, float, float]], ...] = ()
    """Each activation and its rectangle — left, top, right, bottom."""

    frames: tuple[tuple[float, float, float, float], ...] = ()
    """Each fragment's frame, in document order — left, top, right, bottom."""

    groups: tuple[tuple[float, float, float, float], ...] = ()
    """Each group's frame, in document order."""

    labels: tuple[tuple[float, float, float, float] | None, ...] = ()
    """Each message's label box, or `None` for a bare arrow."""

    notes: float | None = None
    """The x the note column starts at, when there are notes."""


def activations(document: Document) -> tuple[Activation, ...]:
    """Every activation bar the messages imply, ordered by lifeline and start.

    A reply closes the most recent call still open between the same two
    participants the other way, so a call made inside a call is answered first.
    A reply inside one branch of an `alt` does not end a call made before the
    frame: the other branches answer it too, so the bar runs to the last answer
    in the frame.
    """
    index = {participant.id: position for position, participant in enumerate(document.participants)}
    rows = {message.id: row for row, message in enumerate(document.messages) if message.id}
    alternatives: list[tuple[int, int, tuple[int, ...]]] = [
        (rows[fragment.start], rows[fragment.end], tuple(rows[b.at] for b in fragment.branches))
        for fragment in document.fragments
        if fragment.operator == "alt"
    ]
    open_calls: list[tuple[int, int, int]] = []
    closed: list[tuple[int, int, int]] = []
    answered: set[int] = set()
    for row, message in enumerate(document.messages):
        sender, receiver = index[message.source], index[message.target]
        if sender == receiver or row in answered:
            continue
        if message.role in CALLS:
            open_calls.append((sender, receiver, row))
        elif message.role == REPLY:
            for position in range(len(open_calls) - 1, -1, -1):
                caller, callee, start = open_calls[position]
                if caller == receiver and callee == sender:
                    del open_calls[position]
                    end = row
                    for first, last, dividers in alternatives:
                        if not first <= row <= last or first <= start <= last:
                            continue
                        branch = sum(1 for at in dividers if at <= row)
                        for later in range(row + 1, last + 1):
                            other = document.messages[later]
                            if (
                                other.role == REPLY
                                and (index[other.source], index[other.target]) == (sender, receiver)
                                and sum(1 for at in dividers if at <= later) > branch
                            ):
                                answered.add(later)
                                end = max(end, later)
                    closed.append((sender, start, end))
                    break
    closed.sort()
    found: list[Activation] = []
    for participant, start, end in closed:
        depth = sum(
            1 for bar in found if bar.participant == participant and bar.start <= start <= bar.end
        )
        found.append(Activation(participant, start, end, depth))
    return tuple(found)


def sequence_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Draw `document` as a sequence diagram."""
    return sequence_drawing(document, theme, measurer).scene


def sequence_drawing(document: Document, theme: Theme, measurer: TextMeasurer) -> SequenceDrawing:
    """Lay `document` out at the widest wrap that fits the canvas.

    Raises:
        FitError: not even the narrowest wrap fits, naming the longest label.
    """
    attempt: SequenceDrawing | None = None
    for heads, labels, notes in WIDTHS:
        attempt = _Layout(document, theme, measurer, heads, labels, notes).drawing()
        if theme.canvas.width_mode != "fixed" or attempt.scene.width <= theme.canvas.width + 0.01:
            return attempt
    assert attempt is not None
    texts = [message.text for message in document.messages if message.text]
    longest = max(texts, key=len, default="")
    raise FitError(
        f"this sequence needs {attempt.scene.width:.0f} units across and the canvas is "
        f"{theme.canvas.width:.0f}: {len(document.participants)} lifelines"
        + (f", the longest label {longest[:40]!r}" if longest else "")
        + ". Shorten the longest labels and names, split the diagram into phases, or "
        "give it more width."
    )


class _Layout:
    """One attempt at the layout, at one pair of wrap widths."""

    def __init__(
        self,
        document: Document,
        theme: Theme,
        measurer: TextMeasurer,
        head_share: float,
        label_share: float,
        note_share: float,
    ) -> None:
        self.document = document
        self.theme = theme
        self.measurer = measurer
        self.unit = theme.scale["body"] / 11
        self.bar = theme.sequence.activation
        canvas = theme.canvas.width
        self.index = {
            participant.id: position for position, participant in enumerate(document.participants)
        }
        self.message_index = {
            message.id: row for row, message in enumerate(document.messages) if message.id
        }
        self.bars = activations(document)

        self.actors = {
            position
            for position, participant in enumerate(document.participants)
            if participant.role == ACTOR
        }
        # An actor's name is words with no box under the figure, as a `note` head is.
        boxes = [
            size_box(
                participant.text,
                theme=theme,
                measurer=measurer,
                role=NOTE if position in self.actors else participant.role,
                level="body",
                max_width=canvas * head_share,
            )
            for position, participant in enumerate(document.participants)
        ]
        self.figure = (FIGURE_HEIGHT + FIGURE_GAP) * self.unit if self.actors else 0.0
        boxed = [box.height for position, box in enumerate(boxes) if position not in self.actors]
        tallest = max(boxed or [box.height for box in boxes])
        self.boxes = [
            box.resized(width=max(box.width, FIGURE_WIDTH * self.unit))
            if position in self.actors
            else box.resized(height=tallest)
            for position, box in enumerate(boxes)
        ]
        # Every head stands on one line, where the lifelines start: an actor's
        # figure rises above its name, past the top of the boxes beside it.
        self.heads_height = max(
            [tallest, *(self.boxes[position].height + self.figure for position in self.actors)]
        )
        self.label_width = canvas * label_share
        self.blocks = [self._wrap(message.text, self.label_width) for message in document.messages]
        self.note_blocks = [
            self._wrap(message.note, canvas * note_share) for message in document.messages
        ]
        self.guards = [
            self._wrap(f"[{fragment.text}]" if fragment.text else "", self.label_width)
            for fragment in document.fragments
        ]
        self.branch_blocks = [
            [
                self._wrap(f"[{branch.text}]" if branch.text else "", self.label_width)
                for branch in fragment.branches
            ]
            for fragment in document.fragments
        ]
        self.group_of: dict[int, int] = {
            self.index[member]: position
            for position, group in enumerate(document.groups)
            for member in group.members
        }

    # -- small helpers ------------------------------------------------------

    def _wrap(self, text: str, width: float) -> TextBlock | None:
        if not text:
            return None
        return wrap(text, width, self.measurer, theme=self.theme, level="label")

    def _rows(self, message: Message) -> tuple[int, int]:
        return self.index[message.source], self.index[message.target]

    def _offsets(self, participant: int, row: int) -> tuple[float, float]:
        """How far left and right of its lifeline a participant's bars reach at `row`."""
        active = [
            bar
            for bar in self.bars
            if bar.participant == participant and bar.start <= row <= bar.end
        ]
        if not active:
            return 0.0, 0.0
        half = self.bar / 2
        return (
            min(bar.depth * half - half for bar in active),
            max(bar.depth * half + half for bar in active),
        )

    def _reach(self, participant: int) -> tuple[float, float]:
        """How far left and right of its lifeline anything below the head reaches."""
        left = right = 0.0
        for row, message in enumerate(self.document.messages):
            sender, receiver = self._rows(message)
            if participant not in (sender, receiver):
                continue
            low, high = self._offsets(participant, row)
            left, right = min(left, low), max(right, high)
            if sender == receiver:
                right = max(right, high + self._hook_reach(row))
        return -left, right

    def _hook_reach(self, row: int) -> float:
        """How far right of its start a message to itself reaches, label included."""
        block = self.blocks[row]
        reach = HOOK * self.unit
        return reach + (LABEL_GAP * self.unit + block.width if block else 0.0)

    def _range(self, fragment: Fragment) -> tuple[int, int]:
        return self.message_index[fragment.start], self.message_index[fragment.end]

    # -- the layout ---------------------------------------------------------

    def _columns(self) -> list[float]:
        """Each lifeline's x, from the left one at zero."""
        unit = self.unit
        count = len(self.boxes)
        reach = [self._reach(position) for position in range(count)]
        gaps: list[float] = []
        for left in range(count - 1):
            right = left + 1
            heads = self.boxes[left].width / 2 + self.boxes[right].width / 2 + HEAD_GAP * unit
            below = reach[left][1] + reach[right][0] + 2 * LABEL_MARGIN * unit
            gap = max(heads, below)
            first, second = self.group_of.get(left), self.group_of.get(right)
            if first != second:
                gap += GROUP_PAD * unit * ((first is not None) + (second is not None))
            gaps.append(gap)

        shaft = self.theme.edge.min_shaft_length + self.theme.widest_head
        spans: list[tuple[int, int, int]] = []
        for row, message in enumerate(self.document.messages):
            sender, receiver = self._rows(message)
            if sender != receiver:
                spans.append((abs(receiver - sender), row, min(sender, receiver)))
        for length, row, low in sorted(spans):
            message = self.document.messages[row]
            sender, receiver = self._rows(message)
            high = low + length
            block = self.blocks[row]
            facing = -self._offsets(high, row)[0] + self._offsets(low, row)[1]
            needed = max((block.width if block else 0.0) + 2 * LABEL_MARGIN * unit, shaft) + facing
            have = sum(gaps[low:high])
            if have < needed:
                share = (needed - have) / length
                for position in range(low, high):
                    gaps[position] += share
        xs = [0.0]
        for gap in gaps:
            xs.append(xs[-1] + gap)
        return xs

    def _frame_spans(self, xs: Sequence[float]) -> dict[int, tuple[float, float]]:
        """Each fragment's left and right, inner first so outer frames pad round them.

        A frame is as wide as the lifelines, bars and hooks its messages touch,
        plus its padding. Its condition is then wrapped to that width where it can
        be, so a long condition takes two lines rather than widening the frame
        past everything else and pushing the notes out with it.
        """
        unit = self.unit
        half = self.bar / 2
        canvas = self.theme.canvas.width
        ranges = {
            position: self._range(fragment)
            for position, fragment in enumerate(self.document.fragments)
        }
        # A frame may widen as far as the drawing already reaches without widening it.
        edge = max(
            xs[position] + max(box.width / 2, self._reach(position)[1])
            for position, box in enumerate(self.boxes)
        )
        spans: dict[int, tuple[float, float]] = {}
        for position in sorted(ranges, key=lambda f: (ranges[f][1] - ranges[f][0], -f)):
            first, last = ranges[position]
            lows: list[float] = []
            highs: list[float] = []
            for row in range(first, last + 1):
                sender, receiver = self._rows(self.document.messages[row])
                for participant in (sender, receiver):
                    offsets = self._offsets(participant, row)
                    lows.append(xs[participant] + min(offsets[0], -half))
                    highs.append(xs[participant] + max(offsets[1], half))
                if sender == receiver:
                    highs.append(xs[sender] + self._offsets(sender, row)[1] + self._hook_reach(row))
            for other, (left, right) in spans.items():
                if first <= ranges[other][0] and ranges[other][1] <= last:
                    lows.append(left)
                    highs.append(right)
            left = min(lows) - FRAME_PAD * unit
            right = max(highs) + FRAME_PAD * unit
            fragment = self.document.fragments[position]
            tab = self._tab_width(fragment.operator)
            reach = max(right, edge) - left - FRAME_PAD * unit
            room = max(reach - tab - LABEL_GAP * unit, canvas * 0.12)
            if fragment.text:
                self.guards[position] = self._wrap(
                    f"[{fragment.text}]", min(room, self.label_width)
                )
            room = max(reach - TAB_PAD * unit, canvas * 0.12)
            self.branch_blocks[position] = [
                self._wrap(f"[{branch.text}]" if branch.text else "", min(room, self.label_width))
                for branch in fragment.branches
            ]
            guard = self.guards[position]
            wanted = tab + (LABEL_GAP * unit + guard.width if guard else 0.0)
            for block in self.branch_blocks[position]:
                if block:
                    wanted = max(wanted, block.width + TAB_PAD * unit)
            spans[position] = (left, max(right, left + wanted + FRAME_PAD * unit))
        return spans

    def drawing(self) -> SequenceDrawing:
        unit = self.unit
        theme = self.theme
        document = self.document
        xs = self._columns()
        frame_spans = self._frame_spans(xs)
        primitives: list[Primitive] = []
        frames_below: list[Primitive] = []
        texts: list[Primitive] = []

        # Group frames sit round the heads, so their labels come first, above them.
        group_spans: list[tuple[float, float]] = []
        label_height = 0.0
        group_labels: list[TextBlock | None] = []
        for group in document.groups:
            members = sorted(self.index[member] for member in group.members)
            first, last = members[0], members[-1]
            reach_first, reach_last = self._reach(first), self._reach(last)
            left = xs[first] - max(self.boxes[first].width / 2, reach_first[0]) - GROUP_PAD * unit
            right = xs[last] + max(self.boxes[last].width / 2, reach_last[1]) + GROUP_PAD * unit
            group_spans.append((left, right))
            block = self._wrap(group.text, max(right - left - 2 * GROUP_PAD * unit, unit))
            group_labels.append(block)
            if block:
                label_height = max(label_height, block.height)
        heads_top = 0.0
        if document.groups:
            heads_top = (label_height + TAB_PAD * unit if label_height else 0.0) + GROUP_PAD * unit

        heads_bottom = heads_top + self.heads_height
        for position, box in enumerate(self.boxes):
            placed: Box = box.moved_to(xs[position] - box.width / 2, heads_bottom - box.height)
            primitives.extend(box_primitives(placed, theme, self.measurer))
            if position in self.actors:
                primitives.extend(_stick_figure(xs[position], placed.y - FIGURE_GAP * unit, unit))

        # Rows, top to bottom.
        fragments = list(enumerate(document.fragments))
        ranges = {position: self._range(fragment) for position, fragment in fragments}
        starts: dict[int, list[int]] = {}
        ends: dict[int, list[int]] = {}
        for position, (first, last) in ranges.items():
            starts.setdefault(first, []).append(position)
            ends.setdefault(last, []).append(position)
        branches: dict[int, list[tuple[int, int]]] = {}
        for position, fragment in fragments:
            for number, branch in enumerate(fragment.branches):
                branches.setdefault(self.message_index[branch.at], []).append((position, number))

        label_size = theme.scale["label"]
        tab_height = theme.box.line_height * label_size + 2 * TAB_PAD * unit
        frame_top: dict[int, float] = {}
        frame_bottom: dict[int, float] = {}
        dividers: dict[tuple[int, int], float] = {}
        arrow_rows: list[tuple[float, float]] = []
        row_tops: list[float] = []

        y = heads_bottom + ROW_GAP * unit
        for row, message in enumerate(document.messages):
            for position in sorted(starts.get(row, ()), key=lambda f: (-ranges[f][1], f)):
                frame_top[position] = y
                guard = self.guards[position]
                header = max(tab_height, (guard.height if guard else 0.0) + 2 * TAB_PAD * unit)
                y += header + LABEL_GAP * unit
            for position, number in branches.get(row, ()):
                dividers[(position, number)] = y
                block = self.branch_blocks[position][number]
                y += TAB_PAD * unit + (block.height if block else 0.0) + LABEL_GAP * unit
            row_tops.append(y)
            block = self.blocks[row]
            height = block.height if block else 0.0
            sender, receiver = self._rows(message)
            if sender == receiver:
                top = y + LABEL_GAP * unit
                drop = max(height, HOOK_DROP * unit)
                arrow_rows.append((top, top + drop))
                ink = top + drop
            else:
                arrow = y + height + LABEL_GAP * unit
                arrow_rows.append((arrow, arrow))
                ink = arrow
            note = self.note_blocks[row]
            y = max(ink, y + (note.height if note else 0.0)) + ROW_GAP * unit
            closing = sorted(ends.get(row, ()), key=lambda f: (-ranges[f][0], -f))
            for position in closing:
                ink += FRAME_PAD * unit
                frame_bottom[position] = ink
            if closing:
                y = max(y, ink + ROW_GAP * unit)
        bottom = y

        # A fragment's tab is opaque: what stands under it — a lifeline, a bar's
        # side — stops at its edge, so the operator reads as a label over the
        # frame's corner rather than as words with lines through them.
        tabs = [
            (
                left,
                frame_top[position],
                left + self._tab_width(document.fragments[position].operator),
                frame_top[position] + tab_height,
            )
            for position, (left, _) in frame_spans.items()
        ]

        def upright(
            role: str, x: float, start: float, end: float, covered: list[tuple[float, float]]
        ) -> None:
            """A vertical stroke at `x`, broken where `covered` or a tab stands on it."""
            cuts = covered + [(top, low) for left, top, right, low in tabs if left <= x <= right]
            for piece_start, piece_end in _uncovered(start, end, cuts):
                primitives.append(Path(role, points=((x, piece_start), (x, piece_end))))

        # Activation bars.
        bar_boxes: list[tuple[Activation, tuple[float, float, float, float]]] = []
        half = self.bar / 2
        for bar in self.bars:
            centre = xs[bar.participant] + bar.depth * half
            top = arrow_rows[bar.start][0] - BAR_OVERHANG * unit
            low = arrow_rows[bar.end][0] + BAR_OVERHANG * unit
            bar_boxes.append((bar, (centre - half, top, centre + half, low)))
        for bar, (left, top, right, low) in bar_boxes:
            primitives.append(Path(BAR, points=((left, top), (right, top))))
            primitives.append(Path(BAR, points=((left, low), (right, low))))
            upright(BAR, left, top, low, [])
            covered = [
                (other_box[1], other_box[3])
                for other, other_box in bar_boxes
                if other.participant == bar.participant and other.depth > bar.depth
            ]
            upright(BAR, right, top, low, covered)

        # Lifelines, broken where a bar stands on them.
        lifelines: dict[str, float] = {}
        for position, participant in enumerate(document.participants):
            x = xs[position]
            lifelines[participant.id] = x
            covered = [(box[1], box[3]) for bar, box in bar_boxes if bar.participant == position]
            upright(theme.sequence.lifeline, x, heads_bottom, bottom, covered)

        # Messages and their labels.
        arrows: list[tuple[tuple[float, float], ...]] = []
        label_boxes: list[tuple[float, float, float, float] | None] = []
        rights: list[float] = []
        for row, message in enumerate(document.messages):
            sender, receiver = self._rows(message)
            block = self.blocks[row]
            top, low = arrow_rows[row]
            if sender == receiver:
                start = xs[sender] + self._offsets(sender, row)[1]
                bend = start + HOOK * unit
                points: tuple[tuple[float, float], ...] = (
                    (start, top),
                    (bend, top),
                    (bend, low),
                    (start, low),
                )
                label_box: tuple[float, float, float, float] | None = None
                if block:
                    left = bend + LABEL_GAP * unit
                    label_top = top + (low - top - block.height) / 2
                    texts.extend(_lines(block, left, label_top, message.role, "start"))
                    label_box = (left, label_top, left + block.width, label_top + block.height)
                    rights.append(left + block.width)
                rights.append(bend)
            else:
                rightward = receiver > sender
                start = xs[sender] + self._offsets(sender, row)[1 if rightward else 0]
                end = xs[receiver] + self._offsets(receiver, row)[0 if rightward else 1]
                points = ((start, top), (end, top))
                label_box = None
                if block:
                    middle = (start + end) / 2
                    label_top = top - LABEL_GAP * unit - block.height
                    texts.extend(_lines(block, middle, label_top, message.role, "middle"))
                    label_box = (
                        middle - block.width / 2,
                        label_top,
                        middle + block.width / 2,
                        label_top + block.height,
                    )
            arrows.append(points)
            label_boxes.append(label_box)
            primitives.extend(
                edge_primitives(Route(message.source, message.target, message.role, points), theme)
            )

        frame_boxes = {
            position: (left, frame_top[position], right, frame_bottom[position])
            for position, (left, right) in frame_spans.items()
        }
        for position, fragment in fragments:
            left, top, right, low = frame_boxes[position]
            frames_below.append(Path(FRAME, points=_outline(left, top, right, low)))
            tab_width = self._tab_width(fragment.operator)
            cut = TAB_CUT * unit
            frames_below.append(
                Path(
                    FRAME,
                    points=(
                        (left, top + tab_height),
                        (left + tab_width - cut, top + tab_height),
                        (left + tab_width, top + tab_height - cut),
                        (left + tab_width, top),
                    ),
                )
            )
            operator = self._wrap(f"**{fragment.operator}**", self.label_width)
            assert operator is not None
            text_top = top + TAB_PAD * unit
            texts.extend(_lines(operator, left + TAB_PAD * unit, text_top, FRAME, "start"))
            guard = self.guards[position]
            if guard:
                texts.extend(
                    _lines(guard, left + tab_width + LABEL_GAP * unit, text_top, FRAME, "start")
                )
            for number, block in enumerate(self.branch_blocks[position]):
                at = dividers[(position, number)]
                frames_below.append(Path(DIVIDER, points=((left, at), (right, at))))
                if block:
                    texts.extend(
                        _lines(block, left + TAB_PAD * unit, at + TAB_PAD * unit, FRAME, "start")
                    )

        # Group frames, round the heads and down past the last row.
        group_boxes: list[tuple[float, float, float, float]] = []
        for (left, right), block in zip(group_spans, group_labels, strict=True):
            low = bottom + GROUP_PAD * unit / 2
            group_boxes.append((left, 0.0, right, low))
            if theme.frames.tone:
                frames_below.append(
                    Polygon(
                        GROUP,
                        points=((left, 0.0), (right, 0.0), (right, low), (left, low)),
                        fill="solid",
                        fill_colour="currentColor",
                        fill_opacity=theme.frames.tone,
                        region=True,
                    )
                )
            frames_below.append(Path(GROUP, points=_outline(left, 0.0, right, low)))
            if block:
                texts.extend(_lines(block, left + GROUP_PAD * unit, TAB_PAD * unit, GROUP, "start"))

        # Notes: one column, right of everything else, each on its message's row.
        extents_right = [
            xs[position] + max(box.width / 2, self._reach(position)[1])
            for position, box in enumerate(self.boxes)
        ]
        extents_right += rights
        extents_right += [box[2] for box in frame_boxes.values()]
        extents_right += [box[2] for box in group_boxes]
        extents_left = [
            xs[position] - max(box.width / 2, self._reach(position)[0])
            for position, box in enumerate(self.boxes)
        ]
        extents_left += [box[0] for box in frame_boxes.values()]
        extents_left += [box[0] for box in group_boxes]
        right_edge = max(extents_right)
        notes: float | None = None
        if any(self.note_blocks):
            notes = right_edge + 3 * LABEL_MARGIN * unit
            for row, block in enumerate(self.note_blocks):
                if block:
                    texts.extend(_lines(block, notes, row_tops[row], NOTE, "start"))
                    right_edge = max(right_edge, notes + block.width)
        left_edge = min(extents_left)
        height = max([bottom] + [box[3] for box in group_boxes])

        shift = -left_edge
        everything = [*frames_below, *primitives, *texts]
        scene = Scene(
            width=right_edge - left_edge,
            height=height,
            primitives=tuple(moved(primitive, shift, 0.0) for primitive in everything),
            title=document.title,
            description=document.description,
        )

        def across(box: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
            return box[0] + shift, box[1], box[2] + shift, box[3]

        return SequenceDrawing(
            scene=scene,
            lifelines={name: x + shift for name, x in lifelines.items()},
            arrows=tuple(tuple((x + shift, y) for x, y in points) for points in arrows),
            bars=tuple((bar, across(box)) for bar, box in bar_boxes),
            frames=tuple(across(frame_boxes[position]) for position, _ in fragments),
            groups=tuple(across(box) for box in group_boxes),
            labels=tuple(across(box) if box else None for box in label_boxes),
            notes=None if notes is None else notes + shift,
        )

    def _tab_width(self, operator: str) -> float:
        size = self.theme.scale["label"]
        text = self.measurer.measure(operator, self.theme.font.default, size, "bold").width
        return text + 2 * TAB_PAD * self.unit + TAB_CUT * self.unit


def _stick_figure(x: float, bottom: float, unit: float) -> list[Primitive]:
    """UML's actor, standing on `bottom` and centred on `x`: a round head, a body,
    arms out level a little below the neck, and two legs from the hip."""
    head = FIGURE_HEAD * unit
    feet = bottom
    hip = feet - FIGURE_LEGS * unit
    neck = hip - FIGURE_BODY * unit
    centre = neck - head
    arms = neck + FIGURE_BODY * unit * 0.3
    half = FIGURE_WIDTH * unit / 2
    stride = FIGURE_LEGS * unit * 0.6
    return [
        Ellipse(FIGURE_HEAD_ROLE, cx=x, cy=centre, rx=head, ry=head),
        Path(FIGURE, points=((x, neck), (x, hip))),
        Path(FIGURE, points=((x - half, arms), (x + half, arms))),
        Path(FIGURE, points=((x - stride, feet), (x, hip), (x + stride, feet))),
    ]


def _outline(
    left: float, top: float, right: float, bottom: float
) -> tuple[tuple[float, float], ...]:
    """A rectangle as one open path, starting and ending mid-way along its top.

    Not a closed `Path`: the emitter fills a closed figure in an edge role, which
    is what an arrow head is. Starting mid-edge keeps the join off the corners.
    """
    middle = (left + right) / 2
    return (
        (middle, top),
        (right, top),
        (right, bottom),
        (left, bottom),
        (left, top),
        (middle, top),
    )


def _uncovered(
    start: float, end: float, covered: Sequence[tuple[float, float]]
) -> list[tuple[float, float]]:
    """The pieces of `start`…`end` that no interval in `covered` overlaps."""
    pieces: list[tuple[float, float]] = []
    cursor = start
    for low, high in sorted(covered):
        if high <= cursor:
            continue
        if low > cursor:
            pieces.append((cursor, min(low, end)))
        cursor = max(cursor, high)
        if cursor >= end:
            break
    if cursor < end:
        pieces.append((cursor, end))
    return [(low, high) for low, high in pieces if high - low > 0.5]


def _lines(block: TextBlock, x: float, top: float, role: str, anchor: str) -> list[TextLine]:
    """A wrapped block as one `TextLine` per line from `top` down, anchored at `x`."""
    lines: list[TextLine] = []
    for index, line in enumerate(block.lines):
        spans = tuple(
            TextSpan(text=span.text, font=span.font, weight=span.weight)
            for span in line.spans
            if span.text
        )
        if spans:
            lines.append(
                TextLine(
                    role,
                    x=x,
                    y=top + block.baseline(index),
                    spans=spans,
                    level="label",
                    anchor=anchor,
                )
            )
    return lines


__all__ = ["Activation", "SequenceDrawing", "activations", "sequence_drawing", "sequence_scene"]

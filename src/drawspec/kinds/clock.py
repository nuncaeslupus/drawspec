"""The `clock` kind: analogue clock faces showing a time, for teaching it.

A layout family of its own. Every hand is placed by arithmetic from its face's
time, so the decisions made here are about the face and the words under it:

**The face** is a circle with sixty ticks, every fifth longer, and the numerals
the sheet asks for inside them: all twelve, Roman I to XII, only the quarters, or
none.

**The hands** are told apart by shape, not colour: the hour hand short and broad,
the minute hand long and narrow, both filled, with a dot on the hub. The hour
hand moves on with the minutes — at quarter past three it is a quarter of the way
from the 3 to the 4 — because leaving it on the hour is the one mistake every
lesson in the corpus warns about.

**`since`** shades what has passed: the minute hand's sweep when it is an hour or
less, the hour hand's, nearer the hub, when it is more, with a dashed line where
the hand started.

**Under each face** the readout — the time in words (*quarter past three*), in
digits as written, both, or nothing on a worksheet — then how long since, then
the face's `text`. Faces sit up to four to a row, the rows kept even.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Final

from drawspec.charts import AXIS_ROLE, FURNITURE_ROLE
from drawspec.errors import FitError
from drawspec.kinds.treemap import bold
from drawspec.scene import Ellipse, Path, Polygon, Primitive, Scene, TextLine, TextSpan
from drawspec.schema import ClockFace, Document, clock_minutes
from drawspec.text.measure import TextMeasurer
from drawspec.text.wrap import TextBlock, wrap
from drawspec.theme import Theme

#: The most faces to a row. Past four a face is too small for its numerals.
FACES_PER_ROW: Final = 4

#: The largest face, as a share of the canvas width: one clock alone is a figure,
#: not a poster.
RADIUS_SHARE: Final = 0.17

#: The hands' widths at the hub, as shares of the radius. The minute hand reaches
#: to just inside the numerals, so it points at a number without covering it; the
#: hour hand is this share of the minute hand's length.
HOUR_WIDTH: Final = 0.08
MINUTE_WIDTH: Final = 0.05
HOUR_SHARE: Final = 0.62

#: The least the minute hand may be, as a share of the radius, before the face is
#: too crowded by its numerals to tell the hands apart.
MINUTE_LEAST: Final = 0.5

#: The role the rim is drawn in, and the ticks: an hour tick an ordinary line, a
#: minute tick the lightest.
RIM_ROLE: Final = "step"
HOUR_TICK_ROLE: Final = "flow"
SINCE_ROLE: Final = "weak"

ROMAN: Final = ("XII", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI")

_ONES: Final = (
    "",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
)

Box = tuple[float, float, float, float]


@dataclass(frozen=True)
class ClockDrawing:
    """The finished geometry, in final coordinates, for tests and the scene."""

    scene: Scene
    faces: tuple[tuple[float, float, float], ...] = ()
    """Each face's centre and radius."""

    hands: tuple[tuple[float, float] | None, ...] = ()
    """Each face's hour and minute hand angles, in degrees clockwise from twelve,
    or None for a face with no hands."""

    readouts: tuple[str, ...] = ()
    """What is written under each face, its lines joined by newlines."""

    numerals: tuple[str, ...] = ()
    """The numerals drawn round each face, from twelve clockwise."""

    sweeps: tuple[tuple[str, float, float] | None, ...] = ()
    """Each face's shaded `since`: which hand's sweep, and from and to which angle."""

    texts: tuple[Box, ...] = field(default=())
    """Every piece of text placed, for the tests that nothing overlaps."""


def clock_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Draw `document` as a clock face or a sheet of them."""
    return clock_drawing(document, theme, measurer).scene


# --------------------------------------------------------------------------
# Words
# --------------------------------------------------------------------------


def number_word(value: int) -> str:
    """A number from 1 to 59 in words: `twenty-five`."""
    if value < 20:
        return _ONES[value]
    tens = ("", "", "twenty", "thirty", "forty", "fifty")[value // 10]
    return f"{tens}-{_ONES[value % 10]}" if value % 10 else tens


def hour_word(hour: int) -> str:
    """An hour on a twelve-hour face in words: 0 and 12 are both `twelve`."""
    return _ONES[hour % 12 or 12]


def time_words(minutes: int) -> str:
    """A time as a primary classroom says it: `quarter past three`, `twenty to four`."""
    hour, minute = divmod(minutes % (24 * 60), 60)
    if minute == 0:
        return f"{hour_word(hour)} o'clock"
    if minute == 15:
        return f"quarter past {hour_word(hour)}"
    if minute == 30:
        return f"half past {hour_word(hour)}"
    if minute == 45:
        return f"quarter to {hour_word(hour + 1)}"
    if minute < 30:
        count, after = minute, f"past {hour_word(hour)}"
    else:
        count, after = 60 - minute, f"to {hour_word(hour + 1)}"
    if count % 5 == 0:
        return f"{number_word(count)} {after}"
    unit = "minute" if count == 1 else "minutes"
    return f"{number_word(count)} {unit} {after}"


def duration_words(minutes: int) -> str:
    """How long, in hours and minutes: `1 hour 20 minutes`, `45 minutes`."""
    hours, minute = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours} hour" + ("s" if hours != 1 else ""))
    if minute:
        parts.append(f"{minute} minute" + ("s" if minute != 1 else ""))
    return " ".join(parts)


def readout(face: ClockFace, mode: str) -> list[str]:
    """The lines under a face: its time in words or digits, then how long since."""
    minutes = clock_minutes(face.time) if face.time else None
    if minutes is None or mode == "none":
        return []
    lines: list[str] = []
    if mode in ("words", "both"):
        lines.append(time_words(minutes))
    if mode in ("digits", "both"):
        lines.append(face.time.strip())
    start = clock_minutes(face.since) if face.since else None
    if start is not None:
        lines.append(f"{duration_words((minutes - start) % (24 * 60))} after {face.since.strip()}")
    return lines


def hand_angles(minutes: int) -> tuple[float, float]:
    """The hour and minute hands' angles, clockwise from twelve, in degrees.

    The hour hand moves on with the minutes: half past three is halfway from 3 to 4.
    """
    hour, minute = divmod(minutes % (24 * 60), 60)
    return ((hour % 12) * 30.0 + minute * 0.5, minute * 6.0)


def numerals_for(style: str) -> tuple[str, ...]:
    """The twelve numerals from twelve clockwise, an empty string where none is drawn."""
    if style == "none":
        return ("",) * 12
    if style == "roman":
        return ROMAN
    if style == "quarters":
        return tuple(str(hour or 12) if hour % 3 == 0 else "" for hour in range(12))
    return tuple(str(hour or 12) for hour in range(12))


# --------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------


def _at(cx: float, cy: float, radius: float, angle: float) -> tuple[float, float]:
    """The point `radius` from the centre at `angle` degrees clockwise from twelve."""
    a = math.radians(angle)
    return (cx + radius * math.sin(a), cy - radius * math.cos(a))


def _hand(
    cx: float, cy: float, angle: float, length: float, width: float
) -> tuple[tuple[float, float], ...]:
    """A tapered hand: broad at the hub, a short tail behind it, narrowing to the tip."""
    tail = width * 0.6
    a = math.radians(angle)
    ux, uy = math.sin(a), -math.cos(a)
    px, py = -uy, ux
    base, tip = width / 2, width / 5

    def point(along: float, across: float) -> tuple[float, float]:
        return (cx + ux * along + px * across, cy + uy * along + py * across)

    return (
        point(-tail, base * 0.7),
        point(0.0, base),
        point(length * 0.92, tip),
        point(length, 0.0),
        point(length * 0.92, -tip),
        point(0.0, -base),
        point(-tail, -base * 0.7),
    )


def _wedge(
    cx: float, cy: float, radius: float, start: float, end: float
) -> tuple[tuple[float, float], ...]:
    """A sector from the hub, clockwise from `start` to `end` degrees."""
    sweep = (end - start) % 360.0 or 360.0
    steps = max(4, int(sweep / 3))
    arc = [_at(cx, cy, radius, start + sweep * step / steps) for step in range(steps + 1)]
    return ((cx, cy), *arc)


def _centred(cx: float, top: float, block: TextBlock) -> Box:
    return (cx - block.width / 2, top, cx + block.width / 2, top + block.height)


def _plain(text: str) -> str:
    return text.replace("**", "").replace("`", "")


def _lines(block: TextBlock, x: float, top: float, level: str) -> list[TextLine]:
    """A wrapped block centred on `x`, from `top` down."""
    lines: list[TextLine] = []
    for index, wrapped in enumerate(block.lines):
        spans = tuple(
            TextSpan(text=span.text, font=span.font, weight=span.weight)
            for span in wrapped.spans
            if span.text
        )
        if spans:
            lines.append(
                TextLine(
                    FURNITURE_ROLE,
                    x=x,
                    y=top + block.baseline(index),
                    spans=spans,
                    level=level,
                    anchor="middle",
                )
            )
    return lines


# --------------------------------------------------------------------------
# The layout
# --------------------------------------------------------------------------


def clock_drawing(document: Document, theme: Theme, measurer: TextMeasurer) -> ClockDrawing:
    """Lay the faces out in even rows, each with its words under it.

    Raises:
        FitError: a face is too small for its numerals, or a word under it is wider
            than its column, at this type scale.
    """
    width = document.width if document.width else theme.canvas.width
    faces = document.clocks
    count = len(faces)
    rows = math.ceil(count / FACES_PER_ROW)
    across = math.ceil(count / rows)
    column = width / across
    gap = theme.box.padding.top
    font = theme.font.default
    level = "body"
    size = theme.scale[level]
    line = measurer.measure("0", font, size)
    radius = min(column / 2 - gap, width * RADIUS_SHARE)
    numerals = numerals_for(document.clock_numerals)
    hour_tick = radius * 0.1
    minute_tick = radius * 0.05
    tall = line.ascent

    def numeral_distance(text: str, angle: float) -> tuple[float, float]:
        """How far from the hub a numeral's centre sits, inside the hour tick, and
        how far its box reaches towards the hub from there."""
        a = math.radians(angle)
        said = measurer.measure(text, font, size).width
        extent = abs(math.sin(a)) * said / 2 + abs(math.cos(a)) * tall / 2
        return radius - hour_tick - gap / 2 - extent, extent

    ring = radius - hour_tick - gap / 2
    for hour, text in enumerate(numerals):
        if text:
            centre, extent = numeral_distance(text, hour * 30.0)
            ring = min(ring, centre - extent)
    minute_length = ring - gap / 2
    hour_length = minute_length * HOUR_SHARE
    # The numerals sit inside the hour ticks, and must leave the minute hand room
    # to be told from the hour hand.
    if minute_length < radius * MINUTE_LEAST:
        raise FitError(
            f"each of {count} faces gets {column:.0f} units, too small for its numerals at this "
            f"size. Draw fewer faces to a sheet, or give the diagram more width."
        )
    room = column - gap

    def block(text: str, what: str, weight_bold: bool = False) -> TextBlock:
        words = bold(text) if weight_bold else text
        try:
            return wrap(words, max(room, 1.0), measurer, theme=theme, level=level, lead=False)
        except FitError as error:
            raise FitError(
                f"{what} {_plain(text)!r} has a word wider than the {room:.0f} units each face "
                f"gets. Shorten it, draw fewer faces to a row, or give the diagram more width."
            ) from error

    primitives: list[Primitive] = []
    texts: list[Primitive] = []
    boxes: list[Box] = []
    centres: list[tuple[float, float, float]] = []
    hands: list[tuple[float, float] | None] = []
    sweeps: list[tuple[str, float, float] | None] = []
    readouts: list[str] = []
    row_top = 0.0
    for row in range(rows):
        members = list(range(row * across, min((row + 1) * across, count)))
        offset = (across - len(members)) * column / 2
        cy = row_top + radius + 1.0
        row_bottom = cy + radius
        for slot, index in enumerate(members):
            face = faces[index]
            cx = offset + column * (slot + 0.5)
            centres.append((cx, cy, radius))

            minutes = clock_minutes(face.time) if face.time else None
            start = clock_minutes(face.since) if face.since else None
            sweep: tuple[str, float, float] | None = None
            if minutes is not None and start is not None:
                passed = (minutes - start) % (24 * 60)
                hour_from, minute_from = hand_angles(start)
                hour_to, minute_to = hand_angles(minutes)
                if passed <= 60:
                    sweep = ("minute", minute_from, minute_to)
                    reach = minute_length
                else:
                    sweep = ("hour", hour_from, hour_to)
                    reach = hour_length
                primitives.append(
                    Polygon(
                        RIM_ROLE,
                        points=_wedge(
                            cx,
                            cy,
                            reach,
                            sweep[1],
                            sweep[1] + passed * (6.0 if sweep[0] == "minute" else 0.5),
                        ),
                        fill="solid",
                        fill_colour="currentColor",
                        fill_opacity=theme.mark.ramp[1],
                        region=True,
                    )
                )
                primitives.append(Path(SINCE_ROLE, points=((cx, cy), _at(cx, cy, reach, sweep[1]))))
            sweeps.append(sweep)

            primitives.append(Ellipse(RIM_ROLE, cx=cx, cy=cy, rx=radius, ry=radius))
            for tick in range(60):
                angle = tick * 6.0
                long = tick % 5 == 0
                inner = radius - (hour_tick if long else minute_tick)
                primitives.append(
                    Path(
                        HOUR_TICK_ROLE if long else AXIS_ROLE,
                        points=(_at(cx, cy, inner, angle), _at(cx, cy, radius, angle)),
                    )
                )
            for hour, text in enumerate(numerals):
                if not text:
                    continue
                angle = hour * 30.0
                said = measurer.measure(text, font, size)
                distance, _ = numeral_distance(text, angle)
                x, y = _at(cx, cy, distance, angle)
                texts.append(
                    TextLine(
                        FURNITURE_ROLE,
                        x=x,
                        y=y + tall / 2,
                        spans=(TextSpan(text=text, font=font),),
                        level=level,
                        anchor="middle",
                    )
                )
                boxes.append((x - said.width / 2, y - tall / 2, x + said.width / 2, y + tall / 2))

            if minutes is not None:
                hour_angle, minute_angle = hand_angles(minutes)
                hands.append((hour_angle, minute_angle))
                for angle, length, broad in (
                    (hour_angle, hour_length, HOUR_WIDTH),
                    (minute_angle, minute_length, MINUTE_WIDTH),
                ):
                    primitives.append(
                        Polygon(
                            RIM_ROLE,
                            points=_hand(cx, cy, angle, length, radius * broad),
                            fill="solid",
                            fill_colour="currentColor",
                            region=True,
                        )
                    )
            else:
                hands.append(None)
            hub = radius * 0.055
            primitives.append(
                Ellipse(
                    RIM_ROLE, cx=cx, cy=cy, rx=hub, ry=hub, fill="solid", fill_colour="currentColor"
                )
            )

            # Under the face: the readout, then the text.
            said_lines = readout(face, document.clock_readout)
            readouts.append("\n".join(said_lines))
            top = cy + radius + gap
            for position, text in enumerate(said_lines):
                written = block(text, "the readout", weight_bold=position == 0)
                texts.extend(_lines(written, cx, top, level))
                boxes.append(
                    (cx - written.width / 2, top, cx + written.width / 2, top + written.height)
                )
                top += written.height
            if face.text:
                if said_lines:
                    top += gap / 2
                written = block(face.text, "the text")
                texts.extend(_lines(written, cx, top, level))
                boxes.append(
                    (cx - written.width / 2, top, cx + written.width / 2, top + written.height)
                )
                top += written.height
            row_bottom = max(row_bottom, top if top > cy + radius + gap else cy + radius + 1.0)
        row_top = row_bottom + 2 * gap

    height = row_top - 2 * gap
    scene = Scene(
        width=width,
        height=height,
        primitives=(*primitives, *texts),
        title=document.title,
        description=document.description,
    )
    return ClockDrawing(
        scene=scene,
        faces=tuple(centres),
        hands=tuple(hands),
        readouts=tuple(readouts),
        numerals=numerals,
        sweeps=tuple(sweeps),
        texts=tuple(boxes),
    )


__all__ = [
    "ClockDrawing",
    "clock_drawing",
    "clock_scene",
    "duration_words",
    "hand_angles",
    "readout",
    "time_words",
]

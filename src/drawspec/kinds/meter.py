"""The `meter` kind: one amount against its scale, alone or a few to a panel.

A layout family of its own. Every reading is placed by arithmetic on its own
meter's scale, so the decisions made here are about lining a panel up and about
where the words go. One `style` draws the whole panel:

**`bar`** and **`bullet`** are rows. The names sit in one column at the left,
the tracks share one left and one right edge, and the readouts sit in one column
at the right, so the eye runs down each. A bar's track is outlined and filled to
the amount in the theme's first mark fill. A bullet's track is its bands, in the
theme's ramp tones lightest first with each band's word over it, a thin solid
bar to the amount along the middle and ticks from zero under it.

**`thermometer`** is columns: a tube on a bulb, filled from the bulb to the
amount, ticked at its left with `max`, the goal, always labelled at the top.

**`dial`** is half-circles, up to three to a row: the arc runs from `min` at the
left to `max` at the right, its bands sectors of it with their words outside, or,
with no bands, the arc filled to the amount. A needle points from the hub.

**A target** is a short heavy stroke across the track, the tube or the arc.

**The readout** says every number in words, so nothing has to be read off the
drawing: the amount in bold — *of* `max` on a bar and a thermometer — the band it
is in, and the target. A band is never told by its tone alone: its word is on it
and in the readout.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Final

from drawspec.charts import AXIS_ROLE, FURNITURE_ROLE, _nice_step
from drawspec.errors import FitError
from drawspec.kinds.treemap import bold
from drawspec.scene import Ellipse, Path, Polygon, Primitive, Scene, TextLine, TextSpan
from drawspec.schema import METER_CURRENCIES, Document, Meter
from drawspec.text.measure import TextMeasurer
from drawspec.text.wrap import TextBlock, wrap
from drawspec.textgrid import (
    Drawn,
    caption_lines,
    cells,
    finished,
    label_lines,
    pad,
    plain,
    spelt,
    too_wide,
    widest,
)
from drawspec.theme import Theme

#: The role a target is drawn in: the heaviest stroke the theme has, headless.
TARGET_ROLE: Final = "strong"

#: The true minus sign: a hyphen is shorter than a plus and reads as a dash.
MINUS: Final = "\N{MINUS SIGN}"

#: The most of the width a name column, or a readout column, may take in a row
#: of bars or bullets.
COLUMN_SHARE: Final = 0.3

#: The most dials to a row. Past three each half-circle is too small to carry
#: the words of its bands round it at the canvas width.
DIALS_PER_ROW: Final = 3

#: A thermometer's tube, as a share of the canvas width: its height, and the
#: least and most its width may be in units.
TUBE_SHARE: Final = 0.42
TUBE_WIDTH: Final = (14.0, 22.0)

#: How many straight pieces an arc is drawn with, per degree.
ARC_STEPS_PER_DEGREE: Final = 0.5

Box = tuple[float, float, float, float]


@dataclass(frozen=True)
class MeterDrawing:
    """The finished geometry, in final coordinates, for tests and the scene."""

    scene: Scene
    style: str = "bar"
    tracks: tuple[Box, ...] = ()
    """Each meter's scale: a bar's or a bullet's track, a thermometer's tube from
    the zero mark to the top mark, a dial's bounding box."""

    readings: tuple[float, ...] = ()
    """Where each amount is drawn: an x on a bar or a bullet, a y on a
    thermometer, the needle's angle in degrees on a dial (180 is `min`, 0 `max`)."""

    targets: tuple[float | None, ...] = ()
    """Where each target is drawn, in the same terms as `readings`."""

    readouts: tuple[str, ...] = ()
    """Each meter's readout, its lines joined by newlines, inline marks removed."""

    words: tuple[Box, ...] = field(default=())
    """Every piece of text placed, for the tests that nothing overlaps."""

    bands: tuple[tuple[Box, ...], ...] = ()
    """Each meter's band words, in band order."""


def meter_scene(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Draw `document` as a meter or a panel of them."""
    return meter_drawing(document, theme, measurer).scene


def meter_drawing(document: Document, theme: Theme, measurer: TextMeasurer) -> MeterDrawing:
    """Lay the meters out on the canvas in the document's style.

    Raises:
        FitError: a name, a readout or a band's word does not fit the room its
            meter has, at this type scale.
    """
    width = document.width if document.width else theme.canvas.width
    layout = _Layout(document, theme, measurer, width)
    if document.meter_style == "thermometer":
        return layout.thermometers()
    if document.meter_style == "dial":
        return layout.dials()
    return layout.rows()


# --------------------------------------------------------------------------
# Numbers and words
# --------------------------------------------------------------------------


def number(value: float, unit: str = "") -> str:
    """A reading as a person writes it: grouped thousands, a true minus, the unit.

    `%` is set close, a currency sign before the number, a word after a space.
    """
    text = f"{abs(value):,.10g}"
    sign = MINUS if value < 0 and text.strip("0.,") else ""
    if unit == "%":
        return f"{sign}{text}%"
    if unit in METER_CURRENCIES:
        return f"{sign}{unit}{text}"
    return f"{sign}{text} {unit}" if unit else f"{sign}{text}"


def tick_unit(unit: str) -> str:
    """The unit a tick carries: a sign, never a word, which the readout says once."""
    return unit if unit == "%" or unit in METER_CURRENCIES else ""


def band_of(meter: Meter) -> int | None:
    """The band the amount is in: from where it starts up to, not including, its end.

    A reading on a boundary is in the band above it; one at `max`, in the last.
    """
    if not meter.bands:
        return None
    for index, band in enumerate(meter.bands):
        if meter.amount < band.to:
            return index
    return len(meter.bands) - 1


def readout(meter: Meter, style: str) -> list[str]:
    """The meter's numbers in words, one line each: amount, band, target."""
    amount = number(meter.amount, meter.unit)
    whole = meter.unit == "%" and meter.min == 0 and meter.max == 100
    if style in ("bar", "thermometer") and not whole:
        # A word unit is said once, after the whole: `23 of 30 sessions`.
        sign = meter.unit == "%" or meter.unit in METER_CURRENCIES
        said = amount if sign or not meter.unit else number(meter.amount)
        first = f"**{said}** of {number(meter.max, meter.unit)}"
    else:
        first = f"**{amount}**"
    lines = [first]
    band = band_of(meter)
    if band is not None:
        lines.append(meter.bands[band].text)
    if meter.target is not None:
        lines.append(f"target {number(meter.target, meter.unit)}")
    return lines


def _ticks(high: float, room: float, widest: float, unit: str) -> list[tuple[float, str]]:
    """Ticks from 0 to `high`, as many as `room` holds labels `widest` apart; `high` last."""
    count = max(1, min(5, int(room // max(widest, 1.0))))
    step = _nice_step(high / count)
    found: list[tuple[float, str]] = []
    value = 0.0
    while value < high - step * 0.5 + 1e-9:
        found.append((value, number(value, unit)))
        value = round(value + step, 10)
    found.append((high, number(high, unit)))
    return found


def _plain(text: str) -> str:
    return text.replace("**", "").replace("`", "")


def _lines(
    block: TextBlock, x: float, top: float, anchor: str, level: str = "body"
) -> list[TextLine]:
    """A wrapped block anchored at `x` (start, middle or end), from `top` down."""
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
                    anchor=anchor,
                )
            )
    return lines


def _rect(left: float, top: float, right: float, bottom: float) -> tuple[tuple[float, float], ...]:
    return ((left, top), (right, top), (right, bottom), (left, bottom))


def _overlap(one: Box, two: Box, gap: float = 0.0) -> bool:
    return (
        one[0] < two[2] + gap
        and two[0] < one[2] + gap
        and one[1] < two[3] + gap
        and two[1] < one[3] + gap
    )


# --------------------------------------------------------------------------
# The layout
# --------------------------------------------------------------------------


@dataclass
class _Stack:
    """Blocks set one under another, centred or anchored, each at its own level."""

    blocks: list[tuple[TextBlock, str]]
    gap: float

    @property
    def width(self) -> float:
        return max((block.width for block, _ in self.blocks), default=0.0)

    @property
    def height(self) -> float:
        heights = [block.height for block, _ in self.blocks]
        return sum(heights) + self.gap * max(len(heights) - 1, 0)

    def place(self, x: float, top: float, anchor: str) -> tuple[list[Primitive], list[Box]]:
        primitives: list[Primitive] = []
        boxes: list[Box] = []
        y = top
        for block, level in self.blocks:
            primitives.extend(_lines(block, x, y, anchor, level))
            left = {"start": x, "middle": x - block.width / 2, "end": x - block.width}[anchor]
            boxes.append((left, y, left + block.width, y + block.height))
            y += block.height + self.gap
        return primitives, boxes


class _Layout:
    """What every style shares: the type, the spacing, and each meter's words."""

    def __init__(self, document: Document, theme: Theme, measurer: TextMeasurer, width: float):
        self.document = document
        self.theme = theme
        self.measurer = measurer
        self.width = width
        self.style = document.meter_style
        self.meters = document.meters
        self.unit = theme.scale["body"] / 11.0
        self.gap = theme.box.padding.top
        self.clearance = theme.edge.clearance
        self.font = theme.font.default
        self.label = theme.scale["label"]
        self.line = measurer.measure("0", self.font, self.label)
        self.word = measurer.measure("0", self.font, theme.scale["body"])
        self.readouts = [readout(meter, self.style) for meter in self.meters]

    # -- words --------------------------------------------------------------

    def _wrap(self, text: str, room: float, level: str, what: str) -> TextBlock:
        try:
            return wrap(text, max(room, 1.0), self.measurer, theme=self.theme, level=level)
        except FitError as error:
            raise FitError(
                f"{what} {_plain(text)!r} has a word wider than the {room:.0f} units it gets. "
                f"Shorten it, give the diagram more width, or draw fewer meters."
            ) from error

    def name(self, meter: Meter, room: float) -> TextBlock:
        text = bold(meter.text) if meter.role == "emphasis" else meter.text
        return self._wrap(text, room, "body", "the name")

    def readout_stack(self, index: int, room: float) -> _Stack:
        meter = self.meters[index]
        blocks: list[tuple[TextBlock, str]] = []
        for position, text in enumerate(self.readouts[index]):
            words = bold(text) if meter.role == "emphasis" else text
            level = "body" if position == 0 else "label"
            block = self._wrap(words, 1e6, level, "the readout")
            if block.width > room + 1e-6:
                raise FitError(
                    f"the readout {_plain(text)!r} is {block.width:.0f} units wide, and "
                    f"{room:.0f} are left for it. Shorten the unit or the band's word, give the "
                    f"diagram more width, or draw fewer meters."
                )
            blocks.append((block, level))
        return _Stack(blocks, gap=self.unit)

    def natural(self, text: str, level: str) -> float:
        return wrap(text, 1e6, self.measurer, theme=self.theme, level=level).width

    def text_width(self, text: str, level: str = "label") -> float:
        return self.measurer.measure(text, self.font, self.theme.scale[level]).width

    def tone(self, index: int, count: int) -> float:
        return self.theme.mark.tone_for(index, count)

    def filled(self, role: str, points: tuple[tuple[float, float], ...]) -> Polygon:
        """How far a bar, a tube or an arc is filled: the first mark's colour, or the
        page's ink, at the ramp's darkest tone, so it reads as filled in greyscale."""
        return Polygon(
            role,
            points=points,
            fill="solid",
            fill_colour=self.theme.mark.colour_for(0) or "currentColor",
            fill_opacity=self.theme.mark.ramp[-1],
            region=True,
        )

    def scene(self, primitives: list[Primitive], height: float) -> Scene:
        return Scene(
            width=self.width,
            height=height,
            primitives=tuple(primitives),
            title=self.document.title,
            description=self.document.description,
        )

    def tick_label(
        self, x: float, y: float, text: str, anchor: str, level: str = "label"
    ) -> TextLine:
        """A tick's number at `label` size, or a band's word — the author's — at `body`."""
        line = self.line if level == "label" else self.word
        return TextLine(
            FURNITURE_ROLE,
            x=x,
            y=y + line.ascent,
            spans=(TextSpan(text=text, font=self.font),),
            level=level,
            anchor=anchor,
        )

    def tick_box(self, x: float, y: float, text: str, anchor: str, level: str = "label") -> Box:
        wide = self.text_width(text, level)
        tall = (self.line if level == "label" else self.word).height
        left = {"start": x, "middle": x - wide / 2, "end": x - wide}[anchor]
        return (left, y, left + wide, y + tall)

    # -- bars and bullets ---------------------------------------------------

    def rows(self) -> MeterDrawing:
        bullet = self.style == "bullet"
        gap = self.gap
        names_room = self.width * COLUMN_SHARE
        name_width = min(max(self.natural(meter.text, "body") for meter in self.meters), names_room)
        names = [self.name(meter, name_width) for meter in self.meters]
        name_width = max(block.width for block in names)
        reads = [self.readout_stack(i, self.width * COLUMN_SHARE) for i in range(len(self.meters))]
        read_width = max(stack.width for stack in reads)
        left = name_width + 2 * gap
        right = self.width - read_width - 2 * gap
        if bullet:
            # Half the widest end label, so the number under the track's end stays
            # clear of the readout beside it.
            right -= (
                max(
                    self.text_width(number(meter.max, tick_unit(meter.unit)))
                    for meter in self.meters
                )
                / 2
            )
        track_width = right - left
        if track_width < 8 * self.line.height:
            raise FitError(
                f"the tracks are {track_width:.0f} units wide once the names and readouts are "
                f"measured. Shorten the names, give the diagram more width, or draw fewer bands."
            )
        thick = self.line.height * (1.7 if bullet else 1.2)
        tick = self.theme.edge.head_length / 2

        primitives: list[Primitive] = []
        texts: list[Primitive] = []
        words: list[Box] = []
        tracks: list[Box] = []
        readings: list[float] = []
        targets: list[float | None] = []
        bands_placed: list[tuple[Box, ...]] = []
        y = 0.0
        for index, meter in enumerate(self.meters):
            scale = track_width / meter.max

            def x_of(value: float, scale: float = scale) -> float:
                return left + value * scale

            above = (self.word.height + self.clearance / 2) if bullet else 0.0
            below = (tick + self.clearance / 2 + self.line.height) if bullet else 0.0
            # The track's middle, with the row's top at 0, then the whole row moved down.
            middle = max(names[index].height / 2, reads[index].height / 2, above + thick / 2)
            bottom = max(
                middle + names[index].height / 2,
                middle + reads[index].height / 2,
                middle + thick / 2 + below,
            )
            middle += y
            top, base = middle - thick / 2, middle + thick / 2
            tracks.append((left, top, right, base))
            role = "emphasis" if meter.role == "emphasis" else "step"
            end = x_of(meter.amount)
            readings.append(end)

            placed: list[Box] = []
            if bullet:
                start = 0.0
                count = len(meter.bands)
                for position, band in enumerate(meter.bands):
                    low, high = x_of(start), x_of(band.to)
                    primitives.append(
                        Polygon(
                            "step",
                            points=_rect(low, top, high, base),
                            fill="solid",
                            fill_colour="currentColor",
                            fill_opacity=self.tone(position, count),
                            region=True,
                        )
                    )
                    wide = self.text_width(band.text, "body")
                    if wide > high - low - self.clearance / 2:
                        raise FitError(
                            f"the band {band.text!r} of {_plain(meter.text)!r} is "
                            f"{high - low:.0f} units long, too short for its word. Shorten the "
                            f"word, widen the band, or give the diagram more width."
                        )
                    box = self.tick_box(
                        (low + high) / 2,
                        top - self.clearance / 2 - self.word.height,
                        band.text,
                        "middle",
                        "body",
                    )
                    texts.append(
                        self.tick_label((low + high) / 2, box[1], band.text, "middle", "body")
                    )
                    placed.append(box)
                    start = band.to
                inner = thick / 3
                if meter.amount > 0:
                    primitives.append(
                        Polygon(
                            role,
                            points=_rect(left, middle - inner / 2, end, middle + inner / 2),
                            fill="solid",
                            fill_colour="currentColor",
                            region=True,
                        )
                    )
                primitives.append(Polygon(role, points=_rect(left, top, right, base), fill="none"))
                # The ticks under the track, from zero.
                ticks = _ticks(
                    meter.max,
                    track_width,
                    self.text_width(number(meter.max, tick_unit(meter.unit))) + 3 * gap,
                    tick_unit(meter.unit),
                )
                previous: Box | None = None
                for position, (value, text) in enumerate(ticks):
                    x = x_of(value)
                    anchor = "middle"
                    box = self.tick_box(x, base + tick + self.clearance / 2, text, anchor)
                    last = position == len(ticks) - 1
                    if previous is not None and _overlap(box, previous, gap):
                        if not last:
                            continue
                        # The end is always labelled: drop the tick before it instead.
                        texts.pop()
                        words.pop()
                    primitives.append(Path(AXIS_ROLE, points=((x, base), (x, base + tick))))
                    texts.append(self.tick_label(x, box[1], text, anchor))
                    words.append(box)
                    previous = box
            else:
                if meter.amount > 0:
                    primitives.append(self.filled(role, _rect(left, top, end, base)))
                    primitives.append(Path(AXIS_ROLE, points=((end, top), (end, base))))
                primitives.append(Polygon(role, points=_rect(left, top, right, base), fill="none"))
            bands_placed.append(tuple(placed))
            words.extend(placed)

            if meter.target is not None:
                x = x_of(meter.target)
                reach = thick * (0.35 if bullet else 0.5) + (0 if bullet else self.clearance / 2)
                primitives.append(
                    Path(TARGET_ROLE, points=((x, middle - reach), (x, middle + reach)))
                )
                targets.append(x)
            else:
                targets.append(None)

            name = names[index]
            texts.extend(_lines(name, 0.0, middle - name.height / 2, "start"))
            words.append((0.0, middle - name.height / 2, name.width, middle + name.height / 2))
            stack = reads[index]
            placed_texts, boxes = stack.place(right + 2 * gap, middle - stack.height / 2, "start")
            texts.extend(placed_texts)
            words.extend(boxes)
            y += bottom + 2.5 * gap

        height = y - 2.5 * gap
        return MeterDrawing(
            scene=self.scene([*primitives, *texts], height),
            style=self.style,
            tracks=tuple(tracks),
            readings=tuple(readings),
            targets=tuple(targets),
            readouts=tuple("\n".join(_plain(t) for t in lines) for lines in self.readouts),
            words=tuple(words),
            bands=tuple(bands_placed),
        )

    # -- thermometers -------------------------------------------------------

    def thermometers(self) -> MeterDrawing:
        count = len(self.meters)
        column = self.width / count
        gap = self.gap
        tube = min(max(column * 0.12, TUBE_WIDTH[0] * self.unit), TUBE_WIDTH[1] * self.unit)
        bulb = tube * 0.8
        cap = tube / 2
        length = max(self.width * TUBE_SHARE, 10 * self.line.height)
        tick = self.theme.edge.head_length / 2
        tube_top = max(cap, self.line.height / 2)
        zero = tube_top + length
        bulb_y = zero + bulb * math.sqrt(1 - (tube / 2 / bulb) ** 2) if bulb > tube / 2 else zero
        bulb_bottom = bulb_y + bulb

        primitives: list[Primitive] = []
        texts: list[Primitive] = []
        words: list[Box] = []
        tracks: list[Box] = []
        readings: list[float] = []
        targets: list[float | None] = []
        bottom = 0.0
        for index, meter in enumerate(self.meters):
            labels = _ticks(
                meter.max,
                length,
                3 * self.line.height,
                tick_unit(meter.unit),
            )
            widest = max(self.text_width(text) for _, text in labels)
            # The tube and its tick labels are centred together in the column.
            half = tube / 2
            # Tick labels stand clear of the bulb as well as the tube.
            side = max(half + tick, bulb) + gap / 2
            centre = column * (index + 0.5) + (widest + side - half) / 2
            if centre - side - widest < column * index - 1e-6:
                raise FitError(
                    f"the thermometer for {_plain(meter.text)!r} and its scale are wider than the "
                    f"{column:.0f} units each of {count} columns gets. Draw fewer meters, or give "
                    f"the diagram more width."
                )

            def y_of(value: float, meter: Meter = meter) -> float:
                return zero - length * value / meter.max

            tracks.append((centre - half, y_of(meter.max), centre + half, zero))
            role = "emphasis" if meter.role == "emphasis" else "step"
            outline = _thermometer(centre, tube_top, zero, half, bulb, bulb_y)
            level = y_of(meter.amount)
            readings.append(level)
            fill = _thermometer(centre, max(level, tube_top), zero, half, bulb, bulb_y, flat=True)
            primitives.append(self.filled(role, fill))
            if meter.amount > 0:
                primitives.append(
                    Path(AXIS_ROLE, points=((centre - half, level), (centre + half, level)))
                )
            primitives.append(Polygon(role, points=outline, fill="none"))
            previous: Box | None = None
            for position, (value, text) in enumerate(reversed(labels)):
                y = y_of(value)
                box = self.tick_box(centre - side, y - self.line.height / 2, text, "end")
                if previous is not None and _overlap(box, previous, self.unit):
                    continue
                primitives.append(
                    Path(
                        AXIS_ROLE,
                        points=((centre - side + gap / 2, y), (centre - half, y)),
                    )
                )
                texts.append(self.tick_label(box[2], box[1], text, "end"))
                words.append(box)
                previous = box
                del position
            if meter.target is not None:
                y = y_of(meter.target)
                reach = self.clearance
                primitives.append(
                    Path(TARGET_ROLE, points=((centre - half, y), (centre + half + reach, y)))
                )
                targets.append(y)
            else:
                targets.append(None)

            room = column - gap
            middle = column * (index + 0.5)
            top = bulb_bottom + gap
            stack = self.readout_stack(index, room)
            placed_texts, boxes = stack.place(middle, top, "middle")
            texts.extend(placed_texts)
            words.extend(boxes)
            top += stack.height + self.unit * 2
            name = self.name(meter, room)
            texts.extend(_lines(name, middle, top, "middle"))
            words.append((middle - name.width / 2, top, middle + name.width / 2, top + name.height))
            bottom = max(bottom, top + name.height)

        return MeterDrawing(
            scene=self.scene([*primitives, *texts], bottom),
            style=self.style,
            tracks=tuple(tracks),
            readings=tuple(readings),
            targets=tuple(targets),
            readouts=tuple("\n".join(_plain(t) for t in lines) for lines in self.readouts),
            words=tuple(words),
            bands=tuple(() for _ in self.meters),
        )

    # -- dials --------------------------------------------------------------

    def dials(self) -> MeterDrawing:
        count = len(self.meters)
        rows = math.ceil(count / DIALS_PER_ROW)
        across = math.ceil(count / rows)
        column = self.width / across
        gap = self.gap
        reach = gap  # From the arc's outer edge to a band's word.
        radius = self._radius(column, reach)
        if radius < 4 * self.line.height:
            raise FitError(
                f"each of {count} dials gets {column:.0f} units, which leaves a half-circle "
                f"{2 * max(radius, 0):.0f} across once its band words are set round it. Shorten "
                f"the band words, draw fewer dials, or use `bullet`."
            )
        thick = radius * 0.24
        above = gap / 2
        for meter in self.meters:
            start = meter.min
            for band in meter.bands:
                middle = math.radians(
                    180.0 * (1 - ((start + band.to) / 2 - meter.min) / (meter.max - meter.min))
                )
                box = self._outside(0.0, 0.0, radius + reach, middle, band.text)
                above = max(above, -box[1] - radius)
                start = band.to

        primitives: list[Primitive] = []
        texts: list[Primitive] = []
        words: list[Box] = []
        tracks: list[Box] = []
        readings: list[float] = []
        targets: list[float | None] = []
        bands_placed: list[tuple[Box, ...]] = []
        row_top = 0.0
        for row in range(rows):
            members = list(range(row * across, min((row + 1) * across, count)))
            offset = (across - len(members)) * column / 2
            hub_y = row_top + above + radius
            row_bottom = hub_y
            for slot, index in enumerate(members):
                meter = self.meters[index]
                cx = offset + column * (slot + 0.5)
                span = meter.max - meter.min

                def angle_of(value: float, meter: Meter = meter, span: float = span) -> float:
                    return 180.0 * (1 - (value - meter.min) / span)

                tracks.append((cx - radius, hub_y - radius, cx + radius, hub_y))
                role = "emphasis" if meter.role == "emphasis" else "step"
                inner = radius - thick
                placed: list[Box] = []
                if meter.bands:
                    start = meter.min
                    total = len(meter.bands)
                    for position, band in enumerate(meter.bands):
                        primitives.append(
                            Polygon(
                                "step",
                                points=_sector(
                                    cx, hub_y, inner, radius, angle_of(start), angle_of(band.to)
                                ),
                                fill="solid",
                                fill_colour="currentColor",
                                fill_opacity=self.tone(position, total),
                                region=True,
                            )
                        )
                        if position:
                            a = math.radians(angle_of(start))
                            primitives.append(
                                Path(
                                    AXIS_ROLE,
                                    points=(
                                        (cx + inner * math.cos(a), hub_y - inner * math.sin(a)),
                                        (cx + radius * math.cos(a), hub_y - radius * math.sin(a)),
                                    ),
                                )
                            )
                        middle = math.radians((angle_of(start) + angle_of(band.to)) / 2)
                        box = self._outside(cx, hub_y, radius + reach, middle, band.text)
                        for other in placed:
                            if _overlap(box, other, self.unit):
                                raise FitError(
                                    f"the band words {band.text!r} and its neighbour on "
                                    f"{_plain(meter.text)!r} run into each other round the dial. "
                                    f"Shorten them, widen the narrow band, or use `bullet`."
                                )
                        texts.append(self.tick_label(box[0], box[1], band.text, "start", "body"))
                        placed.append(box)
                        start = band.to
                elif meter.amount > meter.min:
                    primitives.append(
                        self.filled(
                            role, _sector(cx, hub_y, inner, radius, 180.0, angle_of(meter.amount))
                        )
                    )
                primitives.append(
                    Polygon(role, points=_sector(cx, hub_y, inner, radius, 180.0, 0.0), fill="none")
                )
                bands_placed.append(tuple(placed))
                words.extend(placed)

                if meter.target is not None:
                    a = angle_of(meter.target)
                    r = math.radians(a)
                    out, into = radius + reach * 0.6, inner - reach * 0.3
                    primitives.append(
                        Path(
                            TARGET_ROLE,
                            points=(
                                (cx + into * math.cos(r), hub_y - into * math.sin(r)),
                                (cx + out * math.cos(r), hub_y - out * math.sin(r)),
                            ),
                        )
                    )
                    targets.append(a)
                else:
                    targets.append(None)

                # The needle, from the hub into the arc.
                a = angle_of(meter.amount)
                readings.append(a)
                r = math.radians(a)
                tip = radius - thick * 0.25
                base = thick * 0.16
                primitives.append(
                    Polygon(
                        role,
                        points=(
                            (cx + tip * math.cos(r), hub_y - tip * math.sin(r)),
                            (
                                cx + base * math.cos(r + math.pi / 2),
                                hub_y - base * math.sin(r + math.pi / 2),
                            ),
                            (
                                cx + base * math.cos(r - math.pi / 2),
                                hub_y - base * math.sin(r - math.pi / 2),
                            ),
                        ),
                        fill="solid",
                        fill_colour="currentColor",
                    )
                )
                primitives.append(
                    Ellipse(
                        role,
                        cx=cx,
                        cy=hub_y,
                        rx=thick * 0.3,
                        ry=thick * 0.3,
                        fill="solid",
                        fill_colour="currentColor",
                    )
                )

                # The scale's two ends under the arc's, then the readout and the name.
                ends_top = hub_y + self.clearance / 2
                unit = tick_unit(meter.unit)
                for value, x in (
                    (meter.min, cx - radius + thick / 2),
                    (meter.max, cx + radius - thick / 2),
                ):
                    text = number(value, unit)
                    box = self.tick_box(x, ends_top, text, "middle")
                    texts.append(self.tick_label(x, ends_top, text, "middle"))
                    words.append(box)
                top = ends_top + self.line.height + gap / 2
                room = column - gap
                stack = self.readout_stack(index, room)
                placed_texts, boxes = stack.place(cx, top, "middle")
                texts.extend(placed_texts)
                words.extend(boxes)
                top += stack.height + self.unit * 2
                name = self.name(meter, room)
                texts.extend(_lines(name, cx, top, "middle"))
                words.append((cx - name.width / 2, top, cx + name.width / 2, top + name.height))
                row_bottom = max(row_bottom, top + name.height)
            row_top = row_bottom + 2.5 * gap

        return MeterDrawing(
            scene=self.scene([*primitives, *texts], row_top - 2.5 * gap),
            style=self.style,
            tracks=tuple(tracks),
            readings=tuple(readings),
            targets=tuple(targets),
            readouts=tuple("\n".join(_plain(t) for t in lines) for lines in self.readouts),
            words=tuple(words),
            bands=tuple(bands_placed),
        )

    def _radius(self, column: float, reach: float) -> float:
        """The largest half-circle whose band words all stay inside its column."""

        def fits(radius: float) -> bool:
            for meter in self.meters:
                span = meter.max - meter.min
                start = meter.min
                for band in meter.bands:
                    middle = math.radians(180.0 * (1 - ((start + band.to) / 2 - meter.min) / span))
                    box = self._outside(0.0, 0.0, radius + reach, middle, band.text)
                    if box[0] < -column / 2 + self.unit or box[2] > column / 2 - self.unit:
                        return False
                    start = band.to
            return True

        low, high = 0.0, min(column / 2 - self.gap, self.width * 0.2)
        if fits(high):
            return high
        for _ in range(30):
            middle = (low + high) / 2
            low, high = (middle, high) if fits(middle) else (low, middle)
        return low

    def _outside(self, cx: float, cy: float, reach: float, angle: float, text: str) -> Box:
        """A band word's box outside the arc at `angle`, pushed out until it clears it."""
        wide, tall = self.text_width(text, "body"), self.word.height
        cos, sin = math.cos(angle), math.sin(angle)
        distance = reach
        for _ in range(200):
            px, py = cx + distance * cos, cy - distance * sin
            x_centre = px + wide / 2 * math.copysign(abs(cos) ** 0.5, cos)
            y_centre = py - tall / 2 * sin
            box = (
                x_centre - wide / 2,
                y_centre - tall / 2,
                x_centre + wide / 2,
                y_centre + tall / 2,
            )
            nearest_x = min(max(cx, box[0]), box[2])
            nearest_y = min(max(cy, box[1]), box[3])
            if math.hypot(nearest_x - cx, nearest_y - cy) >= reach - 1e-6:
                return box
            distance += self.unit
        return box


def _arc(
    cx: float, cy: float, radius: float, start: float, end: float
) -> list[tuple[float, float]]:
    """Points along a circle from angle `start` to `end`, in degrees, y down."""
    steps = max(2, int(abs(end - start) * ARC_STEPS_PER_DEGREE) + 1)
    points: list[tuple[float, float]] = []
    for step in range(steps + 1):
        a = math.radians(start + (end - start) * step / steps)
        points.append((cx + radius * math.cos(a), cy - radius * math.sin(a)))
    return points


def _sector(
    cx: float, cy: float, inner: float, outer: float, start: float, end: float
) -> tuple[tuple[float, float], ...]:
    """A piece of a ring from angle `start` to `end`: outer arc out, inner arc back."""
    return (*_arc(cx, cy, outer, start, end), *_arc(cx, cy, inner, end, start))


def _thermometer(
    cx: float,
    top: float,
    zero: float,
    half: float,
    bulb: float,
    bulb_y: float,
    *,
    flat: bool = False,
) -> tuple[tuple[float, float], ...]:
    """A tube on a bulb: up the right side to `top`, round, down the left, round the bulb.

    `flat` ends the tube square at `top`, for the filling; otherwise it is capped
    with a half-circle.
    """
    join = math.degrees(math.asin(min(half / bulb, 1.0)))
    points: list[tuple[float, float]] = [(cx + half, zero)]
    if flat:
        points += [(cx + half, top), (cx - half, top)]
    else:
        points += _arc(cx, top, half, 0.0, 180.0)
    points.append((cx - half, zero))
    # Round the bulb, from where the tube's left side meets it, under, to the right.
    points += _arc(cx, bulb_y, bulb, 90.0 + join, 450.0 - join)
    return tuple(points)


# ---------------------------------------------------------------------------
# Text: a progress bar per meter
# ---------------------------------------------------------------------------

#: A bar's ends, per charset and role: heavier for the meter the panel is about.
TEXT_ENDS: Final = {
    "unicode": {"step": ("[", "]"), "emphasis": ("┃", "┃")},
    "ascii": {"step": ("[", "]"), "emphasis": ("|", "|")},
}

#: A bar's filled part, empty part and target mark, per charset.
TEXT_BARS: Final = {
    "unicode": {"fill": "█", "empty": "░", "target": "│"},
    "ascii": {"fill": "#", "empty": "-", "target": "!"},
}

#: The shortest track worth drawing, and the longest: past forty cells a bar
#: says nothing more precisely than its readout already does.
TEXT_TRACK: Final = (10, 40)

#: Cells between the name, the track and the readout.
TEXT_GAP: Final = 2


def _readouts(document: Document, charset: str) -> list[list[str]]:
    """Each meter's readout lines as text: no bold, a hyphen for a minus in ASCII."""
    style = document.meter_style
    return [
        [
            spelt(line.replace("**", "").replace(MINUS, "-"), charset, f"/meters/{position}")
            if charset == "ascii"
            else line.replace("**", "")
            for line in readout(meter, style)
        ]
        for position, meter in enumerate(document.meters)
    ]


def meter_text(document: Document, width: int, charset: str) -> str:
    """A meter panel as plain text, in the panel's style.

    A row of cells for `bar`; the same row on its bands' shades for `bullet`; a
    tube for `thermometer`; a half-circle of cells with a needle for `dial`.

    Raises:
        FitError: the panel is wider than `width`.
    """
    if document.meter_style == "thermometer":
        return _thermometer_text(document, width, charset)
    if document.meter_style == "bullet":
        return _bullet_text(document, width, charset)
    if document.meter_style == "dial":
        return _dial_text(document, width, charset)
    return _bar_text(document, width, charset)


def _bar_text(document: Document, width: int, charset: str) -> str:
    """A `bar` meter panel as plain text: `name  [██████░░░░]  7 of 12 chapters`.

    The rows layout's three columns — names, tracks sharing one left and one
    right edge, readouts — with the track filled to the amount on the meter's own
    scale, a target as a bar across it, and the readout `readout` writes, its
    lines joined. An `emphasis` meter takes heavier ends.

    Raises:
        FitError: the names and readouts leave the tracks too few columns.
    """
    glyphs = TEXT_BARS[charset]
    meters = document.meters
    names = [
        label_lines(meter.text, charset, f"/meters/{position}/text")
        for position, meter in enumerate(meters)
    ]
    reads = _readouts(document, charset)
    name_width = max(cells(line) for name in names for line in name)
    read_width = max(cells(line) for read in reads for line in read)
    track = min(width - name_width - read_width - 2 * TEXT_GAP - 2, TEXT_TRACK[1])
    if track < TEXT_TRACK[0]:
        position = max(
            range(len(meters)),
            key=lambda number: (
                max(cells(line) for line in names[number])
                + max(cells(line) for line in reads[number])
            ),
        )
        raise too_wide(
            f"/meters/{position}/text",
            f"the name {names[position][0]!r} and its readout {reads[position][0]!r}",
            name_width + read_width + 2 * TEXT_GAP + 2 + TEXT_TRACK[0],
            width,
        )
    drawn: list[Drawn] = []
    for position, meter in enumerate(meters):
        share = min(max(meter.amount / meter.max, 0.0), 1.0) if meter.max else 0.0
        filled = round(share * track)
        bar = [glyphs["fill"]] * filled + [glyphs["empty"]] * (track - filled)
        if meter.target is not None and meter.max:
            bar[min(round(meter.target / meter.max * track), track - 1)] = glyphs["target"]
        opening, closing = TEXT_ENDS[charset]["emphasis" if meter.role == "emphasis" else "step"]
        track_text = opening + "".join(bar) + closing
        gap = " " * TEXT_GAP
        what = f"the meter {names[position][0]!r}"
        # The name's caption under the name and the readout's band and target under
        # its amount, each in its own column, as the SVG stacks them.
        for line in range(max(len(names[position]), len(reads[position]))):
            name = names[position][line] if line < len(names[position]) else ""
            read = reads[position][line] if line < len(reads[position]) else ""
            middle = track_text if line == 0 else " " * cells(track_text)
            text = pad(name, name_width) + gap + middle + gap + read
            drawn.append(Drawn(text, f"/meters/{position}/text", what))
    widest(drawn, width)
    return finished([line.text for line in drawn] + caption_lines(document.caption, width, charset))


#: A thermometer's tube in rows, from `max` at the top to zero at the bottom.
TUBE_ROWS: Final = 10

#: Cells between two thermometers side by side.
TUBE_GAP: Final = 4


@dataclass(frozen=True)
class _TubeGlyphs:
    """One thermometer's glyphs: its cap, walls, ticks, target and bulb."""

    cap: str
    wall: str
    tick: str
    """A tick's stub and the wall it meets, left of the tube."""
    target: tuple[str, str, str, str]
    """The target across the tube: left wall, inside, right wall, beyond."""
    ticked_target: str
    """The left wall where a tick and the target share a row."""
    neck: tuple[str, str]
    bulb: tuple[str, str]
    base: str
    fill: str


def _tube_glyphs(charset: str, emphasis: bool) -> _TubeGlyphs:
    if charset == "ascii":
        rule = "=" if emphasis else "-"
        return _TubeGlyphs(
            cap=f".{rule * 3}.",
            wall="|",
            tick="-|",
            target=("|", "=", "|", "=="),
            ticked_target="-|",
            neck=(".'", "'."),
            bulb=("|", "|"),
            base=f"'{rule * 5}'",
            fill="#",
        )
    if emphasis:
        return _TubeGlyphs(
            cap="┏━━━┓",
            wall="┃",
            tick="─┨",
            target=("┣", "━", "╋", "━━"),
            ticked_target="─╋",
            neck=("┏┛", "┗┓"),
            bulb=("┃", "┃"),
            base="┗━━━━━┛",
            fill="█",
        )
    return _TubeGlyphs(
        cap="╭───╮",
        wall="│",
        tick="─┤",
        target=("┝", "━", "┿", "━━"),
        ticked_target="─┿",
        neck=("╭┘", "└╮"),
        bulb=("│", "│"),
        base="╰─────╯",
        fill="█",
    )


def _tube(meter: Meter, charset: str, position: int) -> tuple[list[str], int]:
    """One thermometer, its tick labels at the left: equally wide lines, and its centre.

    The tube is `TUBE_ROWS` rows from `max` at the top to zero at the bottom,
    filled up from the bulb to the amount; the bulb is always filled, as the
    SVG's is. Ticks are the SVG's, `max` always labelled at the top; a target is
    a heavy stroke across the tube and out past its right wall.
    """
    glyphs = _tube_glyphs(charset, meter.role == "emphasis")
    last = TUBE_ROWS - 1
    unit = tick_unit(meter.unit)

    def row_of(value: float) -> int:
        share = min(max(value / meter.max, 0.0), 1.0) if meter.max else 0.0
        return round((1 - share) * last)

    labels: dict[int, str] = {}
    for value, text in reversed(_ticks(meter.max, TUBE_ROWS, 3, unit)):
        row = row_of(value)
        if row not in labels:
            labels[row] = spelt(text.replace(MINUS, "-"), charset, f"/meters/{position}/unit")
    # The labels right-aligned, a space, then the tick's stub into the wall.
    side = max(cells(text) for text in labels.values()) + 1
    # The fill reaches the row its amount's tick would sit on, the same scale
    # as the ticks and the target, so a meter at its target reads as at it.
    share = min(max(meter.amount / meter.max, 0.0), 1.0) if meter.max else 0.0
    top = row_of(meter.amount) if share > 0 else TUBE_ROWS
    target = row_of(meter.target) if meter.target is not None else None
    empty = " "
    lines = [" " * (side + 1) + glyphs.cap]
    for row in range(TUBE_ROWS):
        label = labels.get(row, "")
        inside = (glyphs.fill if row >= top else empty) * 3
        if row == target:
            left, across, right, beyond = glyphs.target
            if label:
                lead = " " * (side - 1 - cells(label)) + label + " " + glyphs.ticked_target
            else:
                lead = " " * (side + 1) + left
            lines.append(lead + across * 3 + right + beyond)
            continue
        if label:
            lead = " " * (side - 1 - cells(label)) + label + " " + glyphs.tick
        else:
            lead = " " * (side + 1) + glyphs.wall
        lines.append(lead + inside + glyphs.wall)
    opening, closing = glyphs.neck
    lines.append(" " * side + opening + glyphs.fill * 3 + closing)
    lines.append(" " * side + glyphs.bulb[0] + glyphs.fill * 5 + glyphs.bulb[1])
    lines.append(" " * side + glyphs.base)
    room = max(cells(line) for line in lines)
    return [pad(line, room) for line in lines], side + 3


def _thermometer_text(document: Document, width: int, charset: str) -> str:
    """A `thermometer` panel as plain text: tubes side by side, words under each.

    The columns layout: each meter a column holding its tube on its bulb, its
    readout under the bulb and its name under that, as the SVG stacks them.

    Raises:
        FitError: the columns side by side are wider than `width`.
    """
    meters = document.meters
    names = [
        label_lines(meter.text, charset, f"/meters/{position}/text")
        for position, meter in enumerate(meters)
    ]
    reads = _readouts(document, charset)
    tubes = [_tube(meter, charset, position) for position, meter in enumerate(meters)]
    columns: list[list[str]] = []
    depth = max(len(read) for read in reads)
    for (tube, middle), read, name in zip(tubes, reads, names, strict=True):
        # The words centred under the bulb, the tube's labels hanging to its left,
        # every name on the same row however many lines the readouts above take.
        words = [*read, *[""] * (depth - len(read)), "", *name]
        left = max(middle, *(cells(line) // 2 for line in words))
        right = max(cells(tube[0]) - middle, *(cells(line) - cells(line) // 2 for line in words))
        column = left + right
        columns.append(
            [pad(" " * (left - middle) + line, column) for line in tube]
            + [""]
            + [pad(" " * (left - cells(line) // 2) + line, column) for line in words]
        )
    sizes = [cells(column[0]) for column in columns]
    needed = sum(sizes) + TUBE_GAP * (len(columns) - 1)
    if needed > width:
        position = max(range(len(columns)), key=lambda number: sizes[number])
        raise too_wide(
            f"/meters/{position}/text",
            f"the thermometer {names[position][0]!r} beside "
            f"{len(columns) - 1} other{'s' if len(columns) > 2 else ''}"
            if len(columns) > 1
            else f"the thermometer {names[position][0]!r}",
            needed,
            width,
        )
    height = max(len(column) for column in columns)
    gap = " " * TUBE_GAP
    lines = [
        gap.join(
            column[row] if row < len(column) else " " * size
            for column, size in zip(columns, sizes, strict=True)
        )
        for row in range(height)
    ]
    return finished(lines + caption_lines(document.caption, width, charset))


#: A band's shade, lightest first as the SVG's tones go, by how many bands the
#: meter has: each set as far apart as the charset allows.
TEXT_SHADES: Final = {
    "unicode": {2: "░▓", 3: "░▒▓", 4: "·░▒▓", 5: "·░▒▓█"},
    "ascii": {2: ".#", 3: ".:#", 4: ".:+#", 5: ".:+%#"},
}

#: A bullet's measure: a thin heavy bar along the middle of its bands.
TEXT_MEASURE: Final = {"unicode": "━", "ascii": "="}


def _band_at(meter: Meter, value: float) -> int:
    """The band `value` is in, as `band_of` reads the amount."""
    for index, band in enumerate(meter.bands):
        if value < band.to:
            return index
    return len(meter.bands) - 1


def _band_cells(meter: Meter, track: int) -> list[int]:
    """Each cell's band along a track `track` cells long, by the value at its centre."""
    return [_band_at(meter, (cell + 0.5) / track * meter.max) for cell in range(track)]


def _band_words(meter: Meter, track: int, words: list[str]) -> str | None:
    """The band words centred over their bands, or `None` if one has too few cells.

    A word must be shorter than its band, so two neighbours keep a space between.
    """
    owners = _band_cells(meter, track)
    placed: list[tuple[int, str]] = []
    for index, word in enumerate(words):
        spans = [cell for cell, owner in enumerate(owners) if owner == index]
        if not spans or cells(word) >= len(spans):
            return None
        placed.append((spans[0] + (len(spans) - cells(word)) // 2, word))
    return _set(placed)


def _set(placed: list[tuple[int, str]]) -> str:
    """Words set at their cells along a row, left to right, spaces between."""
    row = ""
    for start, text in placed:
        row += " " * (start - cells(row)) + text
    return row


def _tick_row(meter: Meter, track: int, charset: str, position: int) -> str:
    """A bullet's ticks under its track: zero at the left, the end flush right.

    The SVG's ticks; one that would run into its neighbour is dropped, never the
    end, which drops the ones before it that it would run into.
    """
    unit = tick_unit(meter.unit)
    texts = [
        (value, spelt(text.replace(MINUS, "-"), charset, f"/meters/{position}/unit"))
        for value, text in _ticks(meter.max, track, cells(number(meter.max, unit)) + 3, unit)
    ]
    placed: list[tuple[int, str]] = []

    def clear(start: int) -> bool:
        return not placed or placed[-1][0] + cells(placed[-1][1]) + 1 <= start

    for value, text in texts[:-1]:
        size = cells(text)
        start = 0 if value == 0 else round(value / meter.max * track) - size // 2
        if start >= 0 and start + size <= track and clear(start):
            placed.append((start, text))
    text = texts[-1][1]
    start = max(track - cells(text), 0)
    while not clear(start):
        placed.pop()
    placed.append((start, text))
    return _set(placed)


def _bullet_track(document: Document, words: list[list[str]], room: int) -> tuple[int, int]:
    """The track's length in cells, and the least its band words need.

    As a bar's, up to `TEXT_TRACK`'s longest; longer only when a band is too
    short for its word, which no shorter track can carry.
    """
    least = TEXT_TRACK[0]
    while least < 400 and any(
        _band_words(meter, least, said) is None
        for meter, said in zip(document.meters, words, strict=True)
    ):
        least += 1
    return max(min(room, TEXT_TRACK[1]), least), least


def _bullet_text(document: Document, width: int, charset: str) -> str:
    """A `bullet` panel as plain text: a bar's three columns, the track on its bands.

    Each meter is a block of rows: its band words over their bands; the track
    three rows deep, the bands in shades lightest first as the SVG's tones; the
    measure a thin heavy bar along the middle row to the amount; the target a
    stroke down all three; and the ticks from zero under it. The name and the
    readout start on the measure's row.

    Raises:
        FitError: the names, readouts and band words leave the tracks too few
            columns.
    """
    glyphs = TEXT_BARS[charset]
    meters = document.meters
    names = [
        label_lines(meter.text, charset, f"/meters/{position}/text")
        for position, meter in enumerate(meters)
    ]
    bands = [
        [
            spelt(plain(band.text), charset, f"/meters/{position}/bands/{number_}/text")
            for number_, band in enumerate(meter.bands)
        ]
        for position, meter in enumerate(meters)
    ]
    reads = _readouts(document, charset)
    name_width = max(cells(line) for name in names for line in name)
    read_width = max(cells(line) for read in reads for line in read)
    beside = name_width + read_width + 2 * TEXT_GAP + 2
    track, least = _bullet_track(document, bands, width - beside)
    if beside + track > width:
        position = max(
            range(len(meters)),
            key=lambda number_: (
                max(cells(line) for line in names[number_])
                + max(cells(line) for line in reads[number_])
            ),
        )
        crowded = next(
            (
                number_
                for number_, meter in enumerate(meters)
                if _band_words(meter, TEXT_TRACK[0], bands[number_]) is None
            ),
            None,
        )
        if least > TEXT_TRACK[0] and crowded is not None:
            position = crowded
            what = f"the bands of {names[position][0]!r} with their words over them"
        else:
            what = f"the name {names[position][0]!r} and its readout {reads[position][0]!r}"
        raise too_wide(f"/meters/{position}/text", what, beside + least, width)
    shades = TEXT_SHADES[charset]
    gap = " " * TEXT_GAP
    lead = " " * (name_width + TEXT_GAP + 1)
    drawn: list[Drawn] = []
    for position, meter in enumerate(meters):
        pointer = f"/meters/{position}/text"
        what = f"the meter {names[position][0]!r}"
        ramp = shades[len(meter.bands)]
        under = [ramp[band] for band in _band_cells(meter, track)]
        share = min(max(meter.amount / meter.max, 0.0), 1.0)
        filled = round(share * track)
        middle = [TEXT_MEASURE[charset]] * filled + under[filled:]
        rows_ = [list(under), middle, list(under)]
        if meter.target is not None:
            mark = min(round(meter.target / meter.max * track), track - 1)
            for row in rows_:
                row[mark] = glyphs["target"]
        opening, closing = TEXT_ENDS[charset]["emphasis" if meter.role == "emphasis" else "step"]
        tracks = [opening + "".join(row) + closing for row in rows_]
        said = _band_words(meter, track, bands[position]) or ""
        lines = [lead + said, " " * (name_width + TEXT_GAP) + tracks[0]]
        rest = [tracks[1], tracks[2], " " + _tick_row(meter, track, charset, position)]
        name, read = names[position], reads[position]
        for line in range(max(len(rest), len(name), len(read))):
            left = name[line] if line < len(name) else ""
            right = read[line] if line < len(read) else ""
            body = rest[line] if line < len(rest) else ""
            text = pad(left, name_width) + gap + pad(body, track + 2) + gap + right
            lines.append(text)
        if position:
            drawn.append(Drawn("", pointer, what))
        drawn.extend(Drawn(line, pointer, what) for line in lines)
    widest(drawn, width)
    return finished([line.text for line in drawn] + caption_lines(document.caption, width, charset))


#: A dial's half-circle in cells: the outer radius in rows and the arc's depth,
#: a cell being twice as tall as it is wide.
DIAL_RADIUS: Final = 5.0
DIAL_DEPTH: Final = 1.3

#: Cells between two dials side by side, and rows between two rows of them.
DIAL_GAP: Final = 4


@dataclass(frozen=True)
class _DialGlyphs:
    """One dial's glyphs: the needle by its direction, its hub, the target, the fill."""

    needle: tuple[str, str, str]
    """Level, rising to the right, upright; falling to the right is `fall`."""
    fall: str
    hub: str
    target: str
    fill: str
    empty: str


def _dial_glyphs(charset: str, emphasis: bool) -> _DialGlyphs:
    if charset == "ascii":
        return _DialGlyphs(("-", "/", "|"), "\\", "@" if emphasis else "o", "*", "#", ".")
    rising = "\N{BOX DRAWINGS LIGHT DIAGONAL UPPER RIGHT TO LOWER LEFT}"
    return _DialGlyphs(("─", rising, "│"), "╲", "◉" if emphasis else "●", "◆", "█", "░")


def _needle_glyph(glyphs: _DialGlyphs, angle: float) -> str:
    """The stroke for a needle at `angle` degrees, each glyph taking the angles nearest its own.

    A cell is twice as tall as it is wide, so a diagonal from corner to corner
    rises at 63.4 degrees, not 45.
    """
    diagonal = math.degrees(math.atan2(1.0, 0.5))
    if angle < diagonal / 2 or angle > 180 - diagonal / 2:
        return glyphs.needle[0]
    if angle < (diagonal + 90) / 2:
        return glyphs.needle[1]
    if angle <= 180 - (diagonal + 90) / 2:
        return glyphs.needle[2]
    return glyphs.fall


def _dial(meter: Meter, charset: str, position: int) -> tuple[list[str], int]:
    """One dial's half-circle with its ends under it: equally wide lines, and its hub's column.

    The arc's cells are those between `DIAL_RADIUS` and `DIAL_DEPTH` in from it,
    measured in rows with a cell half as wide as tall, from `min` at the left
    round to `max` at the right. Each cell takes its band's shade by the value at
    its centre — or, with no bands, the fill up to the amount — as the SVG's
    sectors do. The needle runs from the hub to the arc at the amount's angle,
    each cell drawn by the stroke nearest its direction; the target is the arc's
    cells on the target's angle.
    """
    glyphs = _dial_glyphs(charset, meter.role == "emphasis")
    span = meter.max - meter.min

    def angle_of(value: float) -> float:
        return 180.0 * (1 - (min(max(value, meter.min), meter.max) - meter.min) / span)

    outer, inner = DIAL_RADIUS, DIAL_RADIUS - DIAL_DEPTH
    across = int(2 * outer)
    rows_ = math.ceil(outer)
    grid: dict[tuple[int, int], str] = {}
    arc: dict[tuple[int, int], float] = {}
    for row in range(rows_):
        for column in range(-across, across + 1):
            distance = math.hypot(column / 2, row)
            if inner <= distance < outer:
                arc[(column, row)] = math.degrees(math.atan2(row, column / 2))
    reading = angle_of(meter.amount)
    ramp = TEXT_SHADES[charset].get(len(meter.bands), "")
    for cell, angle in arc.items():
        value = meter.min + (180.0 - angle) / 180.0 * span
        if meter.bands:
            grid[cell] = ramp[_band_at(meter, value)]
        else:
            full = meter.amount > meter.min and angle >= reading - 1e-9
            grid[cell] = glyphs.fill if full else glyphs.empty

    def ray(angle: float, start: float, end: float) -> list[tuple[int, int]]:
        found: list[tuple[int, int]] = []
        radians = math.radians(angle)
        steps = int((end - start) / 0.05) + 1
        for step in range(steps + 1):
            reach = start + (end - start) * step / steps
            cell = (round(2 * reach * math.cos(radians)), round(reach * math.sin(radians)))
            if cell not in found:
                found.append(cell)
        return found

    # The needle one cell per row where it is steep and one per column where it
    # is shallow, so it is a stroke rather than a staircase two cells thick.
    radians = math.radians(reading)
    reach = inner - 0.6
    tip = (2 * reach * math.cos(radians), reach * math.sin(radians))
    stroke = _needle_glyph(glyphs, reading)
    if abs(tip[0]) >= abs(tip[1]):
        needle = [
            (column, round(tip[1] * column / tip[0]))
            for column in range(1, round(abs(tip[0])) + 1)
            for column in (int(math.copysign(column, tip[0])),)
        ]
    else:
        needle = [(round(tip[0] * row / tip[1]), row) for row in range(1, round(tip[1]) + 1)]
    for cell in needle:
        if cell not in arc:
            grid[cell] = stroke
    grid[(0, 0)] = glyphs.hub
    if meter.target is not None:
        aim = angle_of(meter.target)
        marks = [cell for cell in ray(aim, inner, outer - 0.01) if cell in arc]
        if not marks:
            marks = [min(arc, key=lambda cell: abs(arc[cell] - aim))]
        for cell in marks:
            grid[cell] = glyphs.target
    used = [column for column, _ in grid]
    low, high = min(used), max(used)
    lines = [
        "".join(grid.get((column, row), " ") for column in range(low, high + 1))
        for row in range(rows_ - 1, -1, -1)
    ]
    lines = [line for line in lines if line.strip()]
    unit = tick_unit(meter.unit)
    first, last = (
        spelt(number(value, unit).replace(MINUS, "-"), charset, f"/meters/{position}/unit")
        for value in (meter.min, meter.max)
    )
    room = max(high - low + 1, cells(first) + 1 + cells(last))
    # The arc centred over the ends, which sit under its two feet.
    indent = (room - (high - low + 1)) // 2
    lines = [pad(" " * indent + line, room) for line in lines]
    ends = first + " " * (room - cells(first) - cells(last)) + last
    return [*lines, ends], indent - low


def _key(meter: Meter, charset: str, position: int, room: int) -> list[str]:
    """A dial's bands as a key — each shade then its word — packed into lines of `room`."""
    if not meter.bands:
        return []
    ramp = TEXT_SHADES[charset][len(meter.bands)]
    entries = [
        ramp[number_]
        + " "
        + spelt(plain(band.text), charset, f"/meters/{position}/bands/{number_}/text")
        for number_, band in enumerate(meter.bands)
    ]
    lines: list[str] = []
    for entry in entries:
        if lines and cells(lines[-1]) + 2 + cells(entry) <= room:
            lines[-1] += "  " + entry
        else:
            lines.append(entry)
    # Left-aligned as one block, so the shades stand in a column under each other.
    size = max(cells(line) for line in lines)
    return [pad(line, size) for line in lines]


def _dial_text(document: Document, width: int, charset: str) -> str:
    """A `dial` panel as plain text: half-circles side by side, words under each.

    As the SVG sets them: up to `DIALS_PER_ROW` to a row, the rows as even as
    the count allows and a short one centred. Under each arc are its scale's
    ends, its bands' key, its readout and its name, every name in a row on the
    same line.

    Raises:
        FitError: a row of dials side by side is wider than `width`.
    """
    meters = document.meters
    names = [
        label_lines(meter.text, charset, f"/meters/{position}/text")
        for position, meter in enumerate(meters)
    ]
    reads = _readouts(document, charset)
    dials = [_dial(meter, charset, position) for position, meter in enumerate(meters)]
    keys = [
        _key(meter, charset, position, cells(dial[0][0]))
        for position, (meter, dial) in enumerate(zip(meters, dials, strict=True))
    ]
    count = len(meters)
    rows_ = math.ceil(count / DIALS_PER_ROW)
    across = math.ceil(count / rows_)
    blocks: list[list[str]] = []
    first_width = 0
    for row in range(rows_):
        members = list(range(row * across, min((row + 1) * across, count)))
        depth = max(len(reads[index]) for index in members)
        keyed = max(len(keys[index]) for index in members)
        columns: list[list[str]] = []
        for index in members:
            arc, hub = dials[index]
            key = [*keys[index], *[""] * (keyed - len(keys[index]))]
            words = [*reads[index], *[""] * (depth - len(reads[index])), "", *names[index]]
            under = [*key, *([""] if key else []), *words]
            left = max(hub, *(cells(line) // 2 for line in under))
            right = max(cells(arc[0]) - hub, *(cells(line) - cells(line) // 2 for line in under))
            size = left + right
            columns.append(
                [pad(" " * (left - hub) + line, size) for line in arc]
                + [""]
                + [pad(" " * (left - cells(line) // 2) + line, size) for line in under]
            )
        sizes = [cells(column[0]) for column in columns]
        needed = sum(sizes) + DIAL_GAP * (len(columns) - 1)
        if needed > width:
            slot = max(range(len(columns)), key=lambda number_: sizes[number_])
            position = members[slot]
            raise too_wide(
                f"/meters/{position}/text",
                f"the dial {names[position][0]!r} beside {len(columns) - 1} other"
                f"{'s' if len(columns) > 2 else ''}"
                if len(columns) > 1
                else f"the dial {names[position][0]!r}",
                needed,
                width,
            )
        first_width = first_width or needed
        indent = " " * max((first_width - needed) // 2, 0)
        height = max(len(column) for column in columns)
        gap = " " * DIAL_GAP
        if blocks:
            blocks.append([""])
        blocks.append(
            [
                indent
                + gap.join(
                    column[line] if line < len(column) else " " * size
                    for column, size in zip(columns, sizes, strict=True)
                )
                for line in range(height)
            ]
        )
    lines = [line for block in blocks for line in block]
    return finished(lines + caption_lines(document.caption, width, charset))


__all__ = [
    "MeterDrawing",
    "band_of",
    "meter_drawing",
    "meter_scene",
    "meter_text",
    "number",
    "readout",
]

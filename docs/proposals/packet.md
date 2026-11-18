# `packet` — bit fields in rows: a protocol header, a register map

A protocol header or a hardware register drawn as its bit fields, laid out in rows of a
fixed width under a bit ruler: each field a box as wide as its bits, a field that
crosses a row's end split across the two rows, reserved bits greyed out. The reference
is the header diagram every RFC prints — the IPv4 header of RFC 791 — and the register
table every microcontroller datasheet prints.

This came as an owner request (kinds borrowed from Mermaid, PlantUML, WaveDrom, D2…),
and it answers a real gap: nothing drawspec draws puts things on a **bit grid**. A
`barmodel` sizes parts by an amount, a `stack` sizes layers by their words, a `matrix`
is rows against named columns; none of them wraps one field across a row boundary at a
bit position, which is the whole difficulty of the figure and where hand-made ones go
wrong.

## The originals

Found by web search, as the owner approved for this request: published figures, not
hand-drawn ones.

| # | Original | What it shows | What it asks of the design |
|---|---|---|---|
| P1 | [RFC 791, section 3.1](https://www.rfc-editor.org/rfc/rfc791#section-3.1) — the Internet header format ([mirror](https://freesoft.org/CIE/RFC/791/12.htm)) | ASCII art, 32-bit rows, a two-line ruler (tens over units) with bit 0 at the left, `+-+-+` lines with a `+` at every bit, `Options` + `Padding` as a last row | Rows of 32; RFC numbering; a text form that *is* this picture; variable fields drawn as a row of known width |
| P2 | [RFC 9293, section 3.1](https://www.rfc-editor.org/rfc/rfc9293#section-3.1) — the TCP header (RFC 793's, revised) | Eight 1-bit control flags side by side; RFC 793 wrote their names **stood on end**, a letter to a line (`U`/`R`/`G`) | A name too wide for one bit, turned on its side; a reserved field |
| P3 | AVR status register SREG ([Microchip AVR documentation, "Status Register"](https://onlinedocs.microchip.com/oxy/GUID-B990D80E-52D0-4869-8631-E8A045F89631-en-US-4/GUID-ACB6832F-2425-47FC-B115-F9B79D05A421.html); the same table in the ATmega328P datasheet) | 8 bits, **bit 7 at the left**, a one-letter name per bit (`I T H S V N Z C`), a Read/Write row and an Initial Value row under it, the names spelt out in the text below | Register numbering; a small line under the name (`R/W`, `0`); a key for what the letters mean |
| P4 | [Mermaid `packet-beta`](https://mermaid.js.org/syntax/packet.html) ([config: `bitsPerRow`, default 32](https://mermaid.js.org/config/schema-docs/config-defs-packet-diagram-config.html)) | Fields as bit ranges (`0-15: "Source Port"`) or, since v11.7, counts (`+16: "Source Port"`); a row width | Input as counts, not ranges — a range is a position, and one wrong range shifts nothing else into place |
| P5 | [WaveDrom bit-field](https://www.npmjs.com/package/bit-field) ([Python port](https://pypi.org/project/bit-field/0.3.0/)), used by the RISC-V ISA manual for its instruction formats | `[{bits, name, attr}]` from the LSB, cut into `lanes` rows, ticks at every bit, an `attr` line under a name | Fields as widths in order (the input shape); a register cut into rows, so a field may cross one; ticks at every bit; a second line for an attribute |
| P6 | [Augmented packet diagrams, draft-mcquistin-augmented-ascii-diagrams](https://www.ietf.org/archive/id/draft-mcquistin-augmented-ascii-diagrams-05.html) | The IETF's own survey of how RFCs draw these, and the field-list prose that follows each | A key under the drawing, field by field, as an RFC describes its header |

Checked against the design: P1 and P2 draw as printed (`packet-ipv4.json`, `packet-tcp.json`;
their text forms follow the RFCs' two-columns-a-bit layout, with RFC 791's 3-bit `Flags`
written as its three named bits); P3 draws with every flag a
letter and its meaning in the key (`packet-sreg.json`); P5's RISC-V formats draw with
`numbering: right` (`packet-riscv.json`); the split field is `packet-vlan.json`, an
802.1Q-tagged Ethernet header whose two 48-bit addresses each cross a 32-bit row.

## The design

```json
{
  "version": 1,
  "kind": "packet",
  "bits_per_row": 32,
  "numbering": "left",
  "fields": [
    {"text": "Version", "bits": 4, "holds": "4"},
    {"text": "Don't Fragment", "short": "DF", "bits": 1},
    {"text": "Reserved", "bits": 1, "role": "reserved", "note": "Must be zero."}
  ]
}
```

**No coordinates.** A field is its width in `bits`, in reading order: left to right,
then row after row. Its place is the sum of the widths before it; `start`, `end`,
`offset`, `position` and `range` are refused, because a bit range is a position and one
wrong range is a gap or an overlap nothing else notices (Mermaid added counts for the
same reason).

**`numbering` is a field, decided per document.** `left` (default) is the RFC's: bit 0 is
the first bit on the wire, at the left of every word, one ruler on top counting 0–31.
`right` is a register's: the highest bit at the top left, counting down to bit 0 at the
bottom right, each row with its own ruler. The fields are still written in reading
order — the highest bits first, as the datasheet table reads — so a register's fields
must fill whole rows (otherwise bit 0 would land mid-row); an unused stretch is a
`reserved` field.

**`bits_per_row`** is 8, 16, 32 (default) or 64 — the widths that line up with a byte.

**The drawing is derived:**

- *Rows of equal bits.* Each bit is an equal share of the canvas, so a column of bit 8
  lines up down every row. Every bit boundary is ticked into each row from its top and
  bottom edge (P5); the ruler's ticks stand taller at a byte.
- *The ruler writes as many numbers as fit*: every bit, else every 2nd, 4th or 8th, and
  always both ends.
- *A field that crosses a row's end is split.* Both pieces are drawn, the edges where it
  was cut **dashed** (the field goes on); the name and `holds` sit in the widest piece,
  and a narrower piece repeats the name only where it fits.
- *A name is fitted, never shrunk and never abbreviated by drawspec*: across the field,
  broken onto two lines at a space; the author's `short`; the name, then the short,
  turned on its side when the field is narrow and the word short (P2); and last a
  letter (`a`, `b`, … — not a digit, which a bit diagram reads as a value). Everything
  a cell could not say — a short or letter spelt out, a `holds` too wide, every `note` —
  goes to a **key** under the drawing (P3, P6).
- *Reserved fields are hatched* in the theme's `[packet] reserved_fill` (P3's grey,
  without colour) and may go without a name; `emphasis` (at most two) outlines a field
  heavier and sets its name bold.

**Text form** (`render --format text`): two columns a bit, the RFC's own picture (P1) —
the two-line ruler, `+-+-+` lines and `|` edges in ASCII, box drawing in unicode, a cut
edge `:` (`┆`), a short name stood on end a letter to a line (P2), the key under it. A
64-bit row needs 129 columns and is refused at 80 with the width it needs.

## What it refuses

Each at its JSON pointer, each a test:

- a row of other than 8, 16, 32 or 64 bits; a field of no bits;
- positions: `start`, `end`, `offset`, `position`, `range`;
- other tools' names for its fields: `name`/`label` (`text`), `value`/`attr`/`reset`/
  `access` (`holds`), `reserved: true` (`role`), `lanes`/`vspace`/`hspace` (WaveDrom's
  layout knobs: derived), `rotate` (drawspec decides), `colour`, `edges`;
- `variable`: a variable-length field (options, a payload) is drawn as a row of known
  width with its words saying so — `Options (variable)` — as RFC 791 does;
- a field with no `text` unless it is `reserved`; a name with a newline (drawspec breaks
  it); an empty `short`, `holds` or `note`; a `short` no shorter than its name;
- `numbering: right` with fields that do not fill their last row;
- `bits_per_row` or `numbering` inside a field (they are the document's).

## Budget

40 fields (a TCP header with every flag is 18) and 16 rows (a 64-byte header). Past
that a register map is searched, not read: split it, the header in one drawing and each
long part in its own. A field too narrow even for its key letter (64 one-bit fields on
a narrow canvas) is a `FitError`, with the advice to draw fewer bits a row.

## Status

**Built.** `src/drawspec/kinds/packet.py`, schema and validation in
`src/drawspec/schema.py`, theme `[packet]` in `src/drawspec/theme.py`, references
`docs/reference/packet-*.json` (IPv4, TCP, AVR SREG, RISC-V I-type, 802.1Q Ethernet),
tests in `tests/test_kinds_packet.py`.

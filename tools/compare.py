"""Build the old-against-new comparison page: each original beside its redraw.

The point of this project is that the hand-drawn originals in the opos temario
can be replaced by declarative documents. That claim is only checkable one
diagram at a time, side by side, by a person — so this puts them side by side.

Where the two halves come from:

* **Old** — `originals/<name>.svg`, extracted from the temario and gitignored.
  They are study material belonging to the other project, not source. When the
  directory is absent the left column says so and the page still builds, because
  a page that only works on one machine is a page nobody runs.
* **New** — `docs/corpus/<name>.json`, a drawspec document written against the
  original. Also gitignored: these are the consumer's diagrams expressed through
  drawspec, not this repository's source. What drawspec ships as its own worked
  examples is `docs/reference`. Both halves of the comparison therefore live
  outside the repository, and the tool that puts them together lives in it.

The page lists **every** original, not only the ones already redrawn, so it is
also the progress board for that work: an entry with no document yet shows its
original and says so. A redraw is not a tracing — the originals have known
defects, which is why they are being replaced — so the reviewer's note on each
one (carried in `originals/index.json`) is printed with the pair and the two
should be judged against it.

Usage, from the repository root:

    uv run python tools/compare.py                  # write docs/corpus/index.html
    uv run python tools/compare.py --check          # report coverage, write nothing
    uv run python tools/compare.py --artifact P.html  # also write a body-only page

`--artifact` writes the same page without the document shell, which is the shape
the Artifact publisher wraps in its own `<head>`.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from drawspec.errors import DrawspecError
from drawspec.render import render_document
from drawspec.schema import load_document

ROOT = Path(__file__).resolve().parents[1]
ORIGINALS = ROOT / "originals"
CORPUS = ROOT / "docs" / "corpus"
PAGE = CORPUS / "index.html"

# The temario's own top-level divisions, in the order it presents them. Anything
# unrecognised keeps its raw prefix rather than being folded into an "other".
AREAS = {
    "tic": "Tecnologies de la informació",
    "estado": "Estat i administració",
    "barcelona": "Barcelona",
    "cataluna": "Catalunya",
}


# Three originals will not be redrawn, and the page should say so rather than
# leave them looking merely unfinished. The reasoning is in `docs/kinds-wanted.md`;
# these are the one-line versions, shown in place of the drawing.
DECLINED = {
    "tic__redes-wifi": "A picture, not a diagram. Overlapping Wi-Fi cells are an "
    "illustration of a physical thing, and a language whose author never writes a "
    "coordinate is the wrong tool for one.",
    "tic__servicios-digitales-geograficos": "A picture, not a diagram: one parcel of "
    "land drawn vector against raster. Same reason.",
    "tic__drp-y-bcp": "Wanted, not refused. RPO, RTO, WRT and MTD are spans — "
    "intervals between events — and drawspec's timeline draws marks on a line, not "
    "durations along it. This is the next kind worth adding.",
}


# Words too common to be evidence of anything, in the languages the corpus and
# this tool are written in. Written without accents, because comparison folds them.
_COMMON = """
    amb dels dins aixo aquest aquesta aquests aquestes altre altra altres cada
    com des dues entre esta estan tenir tots tota totes una unes uns seu seva
    seves seus sobre son pero perque quan quant qual quals aqui alla mateix
    del las los para por quien sus unos unas como esta este estos cuando
    and are for from into its not that the their them they this those was were
    what when which with your you have has had can also each only both
"""
STOPWORDS = frozenset(_COMMON.split())

# A word has to be this long to count, and two words are treated as the same word
# when they share this many leading letters — enough to make `públic` and
# `pública`, or `concepte` and `conceptes`, the same word without pairing things
# that merely rhyme.
SHORTEST = 4
STEM = 5


def _fold(text: str) -> list[str]:
    """The content words of a piece of text, accent-folded and lowercased."""
    plain = unicodedata.normalize("NFKD", text.lower())
    plain = "".join(letter for letter in plain if not unicodedata.combining(letter))
    words = re.findall(r"[a-z0-9]+", plain)
    return [word for word in words if len(word) >= SHORTEST and word not in STOPWORDS]


def _absent(these: list[str], those: list[str]) -> list[str]:
    """The words in `these` that nothing in `those` accounts for."""
    stems = {word[:STEM] for word in those}
    missing, seen = [], set()
    for word in these:
        if word[:STEM] not in stems and word not in seen:
            seen.add(word)
            missing.append(word)
    return missing


def _authored(value: object) -> list[str]:
    """Every string an author wrote in a drawspec document, at any depth."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [word for item in value for word in _authored(item)]
    if isinstance(value, dict):
        return [
            word
            for key, item in value.items()
            # `$schema`, `kind`, `theme` and ids are machinery, not prose.
            if key in {"title", "description", "text", "label", "name", "note", "unit"}
            or isinstance(item, (list, dict))
            for word in _authored(item)
        ]
    return []


@dataclass(frozen=True)
class Pair:
    """One original and whatever drawspec makes of it."""

    number: int
    name: str
    slug: str
    area: str
    title: str
    note: str
    wants: str
    kind: str
    old: str
    new: str
    added: tuple[str, ...] = ()
    dropped: tuple[str, ...] = ()
    promoted: tuple[str, ...] = ()
    failure: str = ""

    @property
    def drawn_as(self) -> str:
        """The kind actually used, falling back to the one the survey wanted.

        They differ when reading the original more carefully changed the answer,
        and the page shows both in that case rather than quietly keeping the
        survey's guess.
        """
        return self.kind or self.wants

    @property
    def declined(self) -> str:
        return DECLINED.get(self.name, "")

    @property
    def state(self) -> str:
        if self.failure:
            return "failed"
        if self.new:
            return "drawn"
        return "declined" if self.declined else "pending"


def _namespaced(svg: str, key: str) -> str:
    """An original's ids, prefixed, so two of them on one page cannot collide.

    The originals were not written to be embedded together and several share
    `id="a"`. drawspec's own output is already namespaced by content digest, so
    this only ever touches the left-hand column.
    """
    svg = re.sub(r'\bid="([^"]+)"', lambda match: f'id="{key}-{match.group(1)}"', svg)
    return re.sub(r"url\(#([^)]+)\)", lambda match: f"url(#{key}-{match.group(1)})", svg)


def _index() -> list[dict[str, str]]:
    """The originals' index, in temario order. Empty when the directory is absent."""
    path = ORIGINALS / "index.json"
    if not path.is_file():
        return []
    loaded = json.loads(path.read_text(encoding="utf-8"))
    rows = loaded if isinstance(loaded, list) else list(loaded.values())
    # Keyed on `name`, which is the file stem; `slug` carries a slash and is what
    # the temario calls it, so it is display text rather than a key.
    return [row for row in rows if isinstance(row, dict) and "name" in row]


def _drawn(name: str) -> tuple[str, str, str]:
    """The rendered redraw for one original, its kind, or the error that stopped it."""
    document = CORPUS / f"{name}.json"
    if not document.is_file():
        return "", "", ""
    kind = str(json.loads(document.read_text(encoding="utf-8")).get("kind", ""))
    try:
        return render_document(load_document(document)), kind, ""
    except DrawspecError as error:
        return "", kind, f"{type(error).__name__}: {error}"


def _spoken(svg: str, tags: str) -> str:
    found = re.findall(rf"<(?:{tags})[^>]*>(.*?)</(?:{tags})>", svg, re.S)
    return " ".join(re.sub(r"<[^>]+>", " ", part) for part in found)


def _said(name: str) -> tuple[list[str], list[str]]:
    """What the original draws, and everything it says including its description.

    The two are kept apart because the difference matters: a word that was in the
    original's `<desc>` and is now on the drawing was moved, not invented.
    """
    path = ORIGINALS / f"{name}.svg"
    if not path.is_file():
        return [], []
    svg = path.read_text(encoding="utf-8")
    drawn = _fold(_spoken(svg, "title|text|tspan"))
    return drawn, drawn + _fold(_spoken(svg, "desc"))


def _wrote(name: str) -> tuple[list[str], list[str]]:
    """What the redraw draws, and everything it says including its description."""
    document = CORPUS / f"{name}.json"
    if not document.is_file():
        return [], []
    loaded = json.loads(document.read_text(encoding="utf-8"))
    described = str(loaded.pop("description", ""))
    drawn = _fold(" ".join(_authored(loaded)))
    return drawn, drawn + _fold(described)


def pairs() -> list[Pair]:
    """Every original with its redraw beside it, plus any redraw the index lost.

    Driven from the index rather than from `docs/corpus`, so the page covers the
    whole job and not just the done part of it.
    """
    rows = _index()
    seen = {str(row["name"]) for row in rows}
    extra = sorted(path.stem for path in CORPUS.glob("*.json") if path.stem not in seen)
    rows = rows + [{"name": name} for name in extra]

    found = []
    for position, row in enumerate(rows, start=1):
        name = str(row["name"])
        original = ORIGINALS / f"{name}.svg"
        new, kind, failure = _drawn(name)
        drew, said = _said(name)
        redrew, wrote = _wrote(name)
        found.append(
            Pair(
                number=position,
                name=name,
                slug=str(row.get("slug", name)),
                area=name.split("__")[0],
                title=str(row.get("title", name)),
                note=str(row.get("note", "")),
                wants=str(row.get("wants", "")),
                kind=kind,
                old=(
                    _namespaced(original.read_text(encoding="utf-8"), f"old-{name}")
                    if original.is_file()
                    else ""
                ),
                new=new,
                # Words now on the drawing that the original never said at all.
                added=tuple(_absent(redrew, said)) if new and said else (),
                # Words the original drew that the redraw does not say anywhere.
                dropped=tuple(_absent(drew, wrote)) if new and said else (),
                # Words moved from the original's description onto the drawing.
                promoted=tuple(_absent(_absent(redrew, drew), _absent(redrew, said)))
                if new and said
                else (),
                failure=failure,
            )
        )
    return found


# Only the tokens change between themes, so the dark set is written once and
# placed in both the media query and the explicit stamp.
DARK = """
  --ground: #101315; --plate: #191e20; --sunk: #14181a;
  --ink: #e3e7e6; --muted: #929d9e; --faint: #6b7573;
  --rule: #272e30; --edge: #313a3c;
  --accent: #6bb6c2; --signal: #c7a55e;
"""

STYLE = f"""
:root {{
  --ground: #e8eae7; --plate: #ffffff; --sunk: #dfe2de;
  --ink: #14181a; --muted: #5e686b; --faint: #98a09f;
  --rule: #d0d5d2; --edge: #c2c8c4;
  --accent: #1e6b7b; --signal: #8a6a28;

  --serif: "Iowan Old Style", "Palatino Linotype", Palatino, "Book Antiqua", Georgia, serif;
  --sans: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{{DARK}}} }}
:root[data-theme="dark"] {{{DARK}}}

* {{ box-sizing: border-box; }}
body {{
  margin: 0; background: var(--ground); color: var(--ink);
  font: 15px/1.6 var(--sans);
  -webkit-font-smoothing: antialiased;
}}
.wrap {{ max-width: 1180px; margin: 0 auto; padding: 0 24px; }}

/* ── masthead ─────────────────────────────────────────────────────────── */
.masthead {{ padding: 72px 0 40px; }}
.eyebrow {{
  font: 500 11px/1 var(--mono); letter-spacing: .16em; text-transform: uppercase;
  color: var(--accent); margin: 0 0 18px;
}}
h1 {{
  font: 400 44px/1.08 var(--serif); letter-spacing: -.015em;
  margin: 0 0 16px; text-wrap: balance;
}}
.lede {{ color: var(--muted); margin: 0; max-width: 64ch; font-size: 16px; }}
.lede em {{ color: var(--ink); font-style: normal; }}

/* ── the sticky rail: coverage, then filters ──────────────────────────── */
.rail {{
  position: sticky; top: 0; z-index: 5;
  background: color-mix(in srgb, var(--ground) 92%, transparent);
  backdrop-filter: blur(8px);
  border-bottom: 1px solid var(--rule);
}}
.rail-inner {{
  display: flex; flex-wrap: wrap; align-items: center; gap: 12px 20px;
  max-width: 1180px; margin: 0 auto; padding: 12px 24px;
}}
.coverage {{
  display: flex; align-items: baseline; gap: 8px;
  font: 500 12px/1 var(--mono); letter-spacing: .06em;
}}
.coverage b {{ font-size: 15px; font-weight: 600; font-variant-numeric: tabular-nums; }}
.coverage span {{ color: var(--muted); text-transform: uppercase; letter-spacing: .1em; }}
.gauge {{
  flex: 1 1 120px; min-width: 90px; height: 3px;
  background: var(--sunk); border-radius: 2px; overflow: hidden;
}}
.gauge i {{ display: block; height: 100%; background: var(--accent); }}
.filters {{ display: flex; flex-wrap: wrap; gap: 6px; }}
.chip {{
  font: 500 11px/1 var(--mono); letter-spacing: .06em; text-transform: uppercase;
  color: var(--muted); background: none; border: 1px solid var(--edge);
  border-radius: 2px; padding: 5px 8px; cursor: pointer;
}}
.chip:hover {{ color: var(--ink); border-color: var(--muted); }}
.chip[aria-pressed="true"] {{
  color: var(--plate); background: var(--ink); border-color: var(--ink);
}}
.chip em {{
  font-style: normal; opacity: .55; margin-left: 5px;
  font-variant-numeric: tabular-nums;
}}
:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}

/* ── sections and pairs ───────────────────────────────────────────────── */
.area {{ padding-top: 52px; }}
.area > h2 {{
  font: 500 11px/1 var(--mono); letter-spacing: .16em; text-transform: uppercase;
  color: var(--muted); margin: 0 0 4px; padding-bottom: 12px; border-bottom: 1px solid var(--rule);
  display: flex; justify-content: space-between; gap: 16px;
}}
.pair {{ padding: 34px 0; border-bottom: 1px solid var(--rule); }}
.head {{ display: flex; align-items: baseline; gap: 12px; margin-bottom: 4px; }}
.num {{
  font: 500 12px/1.4 var(--mono); color: var(--faint);
  font-variant-numeric: tabular-nums; flex: none;
}}
.pair h3 {{ font: 400 21px/1.28 var(--serif); margin: 0; text-wrap: balance; }}
.kind s {{ color: var(--faint); text-decoration-thickness: 1px; }}
.kind {{
  font: 500 10px/1 var(--mono); letter-spacing: .1em; text-transform: uppercase;
  color: var(--muted); border: 1px solid var(--edge); border-radius: 2px;
  padding: 4px 6px; flex: none; align-self: center;
}}
.name {{ font: 12px/1.5 var(--mono); color: var(--faint); margin: 0 0 16px 32px; }}
.note {{
  margin: 0 0 18px 32px; padding: 1px 0 1px 14px; max-width: 74ch;
  border-left: 2px solid var(--signal); color: var(--muted); font-size: 14.5px;
}}
.note b {{
  display: block; font: 500 10px/1 var(--mono); letter-spacing: .12em;
  text-transform: uppercase; color: var(--signal); margin-bottom: 5px;
}}
.changed {{
  list-style: none; margin: 0 0 18px 32px; padding: 10px 14px; max-width: 86ch;
  border: 1px solid var(--rule); border-radius: 3px; background: var(--sunk);
  font-size: 13px; line-height: 1.5;
}}
.changed li + li {{ margin-top: 4px; }}
.changed i {{
  font: 500 10px/1 var(--mono); letter-spacing: .1em; text-transform: uppercase;
  font-style: normal; color: var(--muted); margin-right: 8px;
}}
.changed b {{ font-weight: 600; }}
.changed .check {{ color: var(--signal); }}
.changed .check i, .changed .check b {{ color: var(--signal); }}
.cols {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; align-items: start; }}
@media (max-width: 880px) {{ .cols {{ grid-template-columns: 1fr; }} }}
figure {{ margin: 0; }}
figcaption {{
  font: 500 10px/1 var(--mono); letter-spacing: .12em; text-transform: uppercase;
  color: var(--muted); margin-bottom: 8px;
}}
.plate {{
  background: var(--plate); border: 1px solid var(--rule); border-radius: 3px;
  padding: 16px; overflow-x: auto;
}}
.plate svg {{ display: block; width: 100%; height: auto; }}
.blank {{
  border: 1px dashed var(--edge); border-radius: 3px; padding: 24px 18px;
  color: var(--faint); font: 13px/1.55 var(--sans); max-width: 62ch;
}}
.blank b {{ color: var(--muted); display: block; margin-bottom: 4px; }}
.blank.bad {{ color: var(--signal); border-color: var(--signal); font-family: var(--mono);
              font-size: 12px; white-space: pre-wrap; }}
footer {{ padding: 56px 0 88px; color: var(--faint); font-size: 13px; }}
[hidden] {{ display: none !important; }}
"""

SCRIPT = """
const chips = [...document.querySelectorAll('.chip')];
const pairs = [...document.querySelectorAll('.pair')];
const shown = document.getElementById('shown');
let kind = 'all', state = 'all', words = 'all';

function apply() {
  let count = 0;
  for (const pair of pairs) {
    const ok = (kind === 'all' || pair.dataset.kind === kind)
            && (state === 'all' || pair.dataset.state === state)
            && (words === 'all' || pair.dataset.words === words);
    pair.hidden = !ok;
    if (ok) count++;
  }
  for (const area of document.querySelectorAll('.area'))
    area.hidden = ![...area.querySelectorAll('.pair')].some(p => !p.hidden);
  shown.textContent = String(count).padStart(2, '0');
  const chosen = { kind, state, words };
  for (const chip of chips)
    chip.setAttribute(
      'aria-pressed',
      String(chip.dataset[chip.dataset.axis] === chosen[chip.dataset.axis]),
    );
}

for (const chip of chips) chip.addEventListener('click', () => {
  const axis = chip.dataset.axis;
  if (axis === 'kind') kind = chip.dataset.kind;
  else if (axis === 'state') state = chip.dataset.state;
  // The words filter is the only one that toggles: it has no "all" chip of its own.
  else words = words === 'check' ? 'all' : 'check';
  apply();
});
apply();
"""


def _plate(svg: str, failure: str, *, missing: str) -> str:
    if svg:
        return f"<div class=plate>{svg}</div>"
    if failure:
        return f"<p class='blank bad'>{escape(failure)}</p>"
    return f"<p class=blank>{missing}</p>"


def _changed(pair: Pair) -> str:
    """What this redraw did to the original, in the terms a checker needs.

    The reviewer's question about every one of these drawings was the same — did
    you take this from the source or make it up? — and answering it per drawing in
    prose does not scale and cannot be trusted. So it is computed: the words on
    the redraw that the original never said, the words it says that the original
    only said in its description, and the words the original drew that the redraw
    dropped. It is a signal, not a proof: it compares words, not meanings.
    """
    if not pair.new:
        return ""
    rows = []
    if pair.kind and pair.wants and pair.kind != pair.wants:
        rows.append(
            f"<li><i>Kind</i> Drawn as <b>{escape(pair.kind)}</b>; "
            f"the survey said <b>{escape(pair.wants)}</b>.</li>"
        )
    if pair.added:
        rows.append(
            "<li class=check><i>Not in the original</i> "
            + ", ".join(f"<b>{escape(word)}</b>" for word in pair.added)
            + " &mdash; check these against the source.</li>"
        )
    if pair.promoted:
        rows.append(
            "<li><i>Moved onto the drawing</i> "
            + ", ".join(escape(word) for word in pair.promoted)
            + " &mdash; said by the original, but only in its description.</li>"
        )
    if pair.dropped:
        rows.append(
            "<li><i>Dropped</i> "
            + ", ".join(escape(word) for word in pair.dropped)
            + " &mdash; drawn on the original, said nowhere here.</li>"
        )
    if not rows:
        rows.append("<li><i>Words</i> Nothing added, nothing dropped.</li>")
    return f"<ul class=changed>{''.join(rows)}</ul>"


def _article(pair: Pair) -> str:
    note = f"<p class=note><b>The reviewer's note</b>{escape(pair.note)}</p>" if pair.note else ""
    kind = ""
    if pair.drawn_as:
        moved = pair.kind and pair.wants and pair.kind != pair.wants
        was = f"<s>{escape(pair.wants)}</s> " if moved else ""
        kind = f"<span class=kind>{was}{escape(pair.drawn_as)}</span>"
    old = _plate(
        pair.old,
        "",
        missing="The originals are gitignored study material and are not in this checkout.",
    )
    new = _plate(
        pair.new,
        pair.failure,
        missing=(
            f"<b>Not being redrawn.</b> {escape(pair.declined)}"
            if pair.declined
            else "Not redrawn yet."
        ),
    )
    return (
        f"<article class=pair id='{escape(pair.name)}'"
        f" data-kind='{escape(pair.drawn_as or 'none')}' data-state='{pair.state}'"
        f" data-words='{'check' if pair.added else 'clean'}'>"
        f"<div class=head><span class=num>{pair.number:02d}</span>"
        f"<h3>{escape(pair.title)}</h3>{kind}</div>"
        f"<p class=name>{escape(pair.slug)}</p>{note}{_changed(pair)}"
        f"<div class=cols>"
        f"<figure><figcaption>The original</figcaption>{old}</figure>"
        f"<figure><figcaption>drawspec</figcaption>{new}</figure>"
        f"</div></article>"
    )


def _rail(found: list[Pair]) -> str:
    drawn = sum(1 for pair in found if pair.new)
    # Coverage is measured against what drawspec is meant to draw, so the three
    # set-aside originals come out of the denominator rather than holding the
    # bar permanently short of full.
    total = sum(1 for pair in found if not pair.declined) or 1
    kinds = Counter(pair.drawn_as or "none" for pair in found)
    states = Counter(pair.state for pair in found)

    chips = [
        f"<button class=chip data-axis=kind data-kind=all aria-pressed=true>"
        f"All<em>{len(found)}</em></button>"
    ]
    chips += [
        f"<button class=chip data-axis=kind data-kind='{escape(name)}'>"
        f"{escape(name)}<em>{count}</em></button>"
        for name, count in kinds.most_common()
    ]
    chips.append(
        "<button class=chip data-axis=state data-state=all aria-pressed=true>Any state</button>"
    )
    check = sum(1 for pair in found if pair.added)
    if check:
        chips.append(
            "<button class=chip data-axis=words data-words=check>"
            f"Words to check<em>{check}</em></button>"
        )
    chips += [
        f"<button class=chip data-axis=state data-state='{name}'>"
        f"{label}<em>{states[name]}</em></button>"
        for name, label in (
            ("drawn", "Redrawn"),
            ("pending", "Pending"),
            ("declined", "Out of scope"),
            ("failed", "Failing"),
        )
        if states[name]
    ]
    return (
        "<div class=rail><div class=rail-inner>"
        f"<div class=coverage><b>{drawn:02d}</b><span>of {total} drawable redrawn</span></div>"
        f"<div class=gauge><i style='width:{drawn / total:.1%}'></i></div>"
        f"<div class=filters>{''.join(chips)}</div>"
        f"<div class=coverage><b id=shown>{len(found):02d}</b><span>shown</span></div>"
        "</div></div>"
    )


def render_page(found: list[Pair], *, standalone: bool = True) -> str:
    parts = []
    if standalone:
        parts += [
            "<!doctype html>",
            "<meta charset='utf-8'>",
            "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        ]
    parts += [
        "<title>drawspec Corpus Redraws</title>",
        f"<style>{STYLE}</style>",
        "<div class=wrap><div class=masthead>",
        "<p class=eyebrow>drawspec &middot; corpus</p>",
        "<h1>Old against new</h1>",
        "<p class=lede>Every hand-drawn diagram in the temario, beside the drawing "
        "drawspec makes of it from a declarative document. A redraw is <em>not a "
        "tracing</em>: the originals have known defects, which is the reason for "
        "replacing them, so the reviewer's own note is printed with each pair and the "
        "two should be judged against it.</p>",
        "</div></div>",
        _rail(found),
        "<div class=wrap>",
    ]

    order: list[str] = []
    for pair in found:
        if pair.area not in order:
            order.append(pair.area)
    for area in order:
        members = [pair for pair in found if pair.area == area]
        drawn = sum(1 for pair in members if pair.new)
        drawable = sum(1 for pair in members if not pair.declined)
        parts.append(
            f"<section class=area><h2><span>{escape(AREAS.get(area, area))}</span>"
            f"<span>{drawn} / {drawable}</span></h2>"
        )
        parts += [_article(pair) for pair in members]
        parts.append("</section>")

    parts += [
        "<footer>Both halves belong to the opos project, not to drawspec: the "
        "originals are study material from the temario, and the documents on the "
        "right are those same diagrams expressed as drawspec documents. Neither is "
        "kept in this repository. What is kept is the tool that draws them.</footer>",
        "</div>",
        f"<script>{SCRIPT}</script>",
    ]
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report only, write nothing")
    parser.add_argument("--artifact", type=Path, help="also write a body-only page here")
    arguments = parser.parse_args(argv)

    found = pairs()
    failed = [pair for pair in found if pair.failure]
    drawn = [pair for pair in found if pair.new]
    for pair in found:
        print(f"{pair.number:3d}  {pair.name:52} {pair.drawn_as:10} {pair.failure or pair.state}")
    declined = [pair for pair in found if pair.declined]
    print(
        f"\n{len(drawn)} of {len(found) - len(declined)} drawable redrawn, "
        f"{len(declined)} out of scope, {len(failed)} failing"
    )

    if not arguments.check:
        CORPUS.mkdir(parents=True, exist_ok=True)
        PAGE.write_text(render_page(found), encoding="utf-8")
        print(PAGE)
        if arguments.artifact:
            arguments.artifact.parent.mkdir(parents=True, exist_ok=True)
            arguments.artifact.write_text(render_page(found, standalone=False), encoding="utf-8")
            print(arguments.artifact)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

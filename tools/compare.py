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
    def state(self) -> str:
        if self.failure:
            return "failed"
        return "drawn" if self.new else "pending"


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
  border: 1px dashed var(--edge); border-radius: 3px; padding: 28px 16px;
  color: var(--faint); font: 13px/1.5 var(--sans);
}}
.blank.bad {{ color: var(--signal); border-color: var(--signal); font-family: var(--mono);
              font-size: 12px; white-space: pre-wrap; }}
footer {{ padding: 56px 0 88px; color: var(--faint); font-size: 13px; }}
[hidden] {{ display: none !important; }}
"""

SCRIPT = """
const chips = [...document.querySelectorAll('.chip')];
const pairs = [...document.querySelectorAll('.pair')];
const shown = document.getElementById('shown');
let kind = 'all', state = 'all';

function apply() {
  let count = 0;
  for (const pair of pairs) {
    const ok = (kind === 'all' || pair.dataset.kind === kind)
            && (state === 'all' || pair.dataset.state === state);
    pair.hidden = !ok;
    if (ok) count++;
  }
  for (const area of document.querySelectorAll('.area'))
    area.hidden = ![...area.querySelectorAll('.pair')].some(p => !p.hidden);
  shown.textContent = String(count).padStart(2, '0');
  for (const chip of chips)
    chip.setAttribute(
      'aria-pressed',
      String(chip.dataset[chip.dataset.axis] === (chip.dataset.axis === 'kind' ? kind : state)),
    );
}

for (const chip of chips) chip.addEventListener('click', () => {
  if (chip.dataset.axis === 'kind') kind = chip.dataset.kind;
  else state = chip.dataset.state;
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
    new = _plate(pair.new, pair.failure, missing="Not redrawn yet.")
    return (
        f"<article class=pair id='{escape(pair.name)}'"
        f" data-kind='{escape(pair.drawn_as or 'none')}' data-state='{pair.state}'>"
        f"<div class=head><span class=num>{pair.number:02d}</span>"
        f"<h3>{escape(pair.title)}</h3>{kind}</div>"
        f"<p class=name>{escape(pair.slug)}</p>{note}"
        f"<div class=cols>"
        f"<figure><figcaption>The original</figcaption>{old}</figure>"
        f"<figure><figcaption>drawspec</figcaption>{new}</figure>"
        f"</div></article>"
    )


def _rail(found: list[Pair]) -> str:
    drawn = sum(1 for pair in found if pair.new)
    total = len(found) or 1
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
    chips += [
        f"<button class=chip data-axis=state data-state='{name}'>"
        f"{label}<em>{states[name]}</em></button>"
        for name, label in (("drawn", "Redrawn"), ("pending", "Pending"), ("failed", "Failing"))
        if states[name]
    ]
    return (
        "<div class=rail><div class=rail-inner>"
        f"<div class=coverage><b>{drawn:02d}</b><span>of {len(found)} redrawn</span></div>"
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
        parts.append(
            f"<section class=area><h2><span>{escape(AREAS.get(area, area))}</span>"
            f"<span>{drawn} / {len(members)}</span></h2>"
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
    print(f"\n{len(drawn)} of {len(found)} redrawn, {len(failed)} failing")

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

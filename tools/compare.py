"""Build the old-against-new comparison page: each original beside its redraw.

The point of this project is that the hand-drawn originals in the opos temario
can be replaced by declarative documents. That claim is only checkable one
diagram at a time, side by side, by a person — so this puts them side by side.

Where the two halves come from:

* **Old** — `originals/<slug>.svg`, extracted from the temario and gitignored.
  They are study material belonging to the other project, not source. When the
  directory is absent the left column says so and the page still builds, because
  a page that only works on one machine is a page nobody runs.
* **New** — `docs/corpus/<slug>.json`, a drawspec document written against the
  original. These *are* source: they are the deliverable this project exists to
  produce.

A redraw is not a tracing. The originals have known defects — that is why they
are being replaced — so the redraw fixes them, and the reviewer's note on each
one (carried in `originals/index.json`) is printed under the pair so the two can
be judged against what was actually wrong with the first.

Usage, from the repository root:

    uv run python tools/compare.py            # write docs/corpus/index.html
    uv run python tools/compare.py --check    # report coverage, write nothing
"""

from __future__ import annotations

import argparse
import json
import re
import sys
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


@dataclass(frozen=True)
class Pair:
    """One original and whatever drawspec makes of it."""

    slug: str
    title: str
    note: str
    wants: str
    old: str
    new: str
    failure: str = ""


def _namespaced(svg: str, key: str) -> str:
    """An original's ids, prefixed, so two of them on one page cannot collide.

    The originals were not written to be embedded together and several share
    `id="a"`. drawspec's own output is already namespaced by content digest, so
    this only ever touches the left-hand column.
    """
    svg = re.sub(r'\bid="([^"]+)"', lambda match: f'id="{key}-{match.group(1)}"', svg)
    return re.sub(r"url\(#([^)]+)\)", lambda match: f"url(#{key}-{match.group(1)})", svg)


def _index() -> dict[str, dict[str, str]]:
    path = ORIGINALS / "index.json"
    if not path.is_file():
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    rows = loaded if isinstance(loaded, list) else list(loaded.values())
    # Keyed by `name`, which is the file stem; `slug` carries a slash and is
    # what the temario calls it, so it is display text rather than a key.
    return {str(row["name"]): row for row in rows if isinstance(row, dict) and "name" in row}


def pairs() -> list[Pair]:
    """Every redraw in `docs/corpus`, with its original beside it when present."""
    index = _index()
    found = []
    for document in sorted(CORPUS.glob("*.json")):
        slug = document.stem
        row = index.get(slug, {})
        original = ORIGINALS / f"{slug}.svg"
        old = (
            _namespaced(original.read_text(encoding="utf-8"), f"old-{slug}")
            if original.is_file()
            else ""
        )
        try:
            new, failure = render_document(load_document(document)), ""
        except DrawspecError as error:
            new, failure = "", f"{type(error).__name__}: {error}"
        found.append(
            Pair(
                slug=slug,
                title=str(row.get("title", slug)),
                note=str(row.get("note", "")),
                wants=str(row.get("wants", "")),
                old=old,
                new=new,
                failure=failure,
            )
        )
    return found


STYLE = """
:root { color-scheme: light dark; }
body { font: 15px/1.55 system-ui, sans-serif; margin: 0; padding: 0 24px 96px;
       background: #fbfbf9; color: #17181c; }
.wrap { max-width: 1200px; margin: 0 auto; }
header { padding: 56px 0 24px; border-bottom: 1px solid #e3e2dd; }
h1 { font-size: 32px; margin: 0 0 10px; letter-spacing: -.01em; }
.lede { color: #5b6069; margin: 0; max-width: 62ch; }
.count { font: 500 12px/1 ui-monospace, monospace; letter-spacing: .08em;
         text-transform: uppercase; color: #5b6069; }
article { padding: 34px 0; border-bottom: 1px solid #e3e2dd; }
h2 { font-size: 19px; margin: 0 0 4px; }
.meta { color: #5b6069; font-size: 13.5px; margin: 0 0 16px; }
.kind { font: 500 11px/1 ui-monospace, monospace; letter-spacing: .08em;
        text-transform: uppercase; border: 1px solid #c9c8c2; border-radius: 3px;
        padding: 3px 5px; margin-left: 8px; }
.note { border-left: 3px solid #c9762f; padding: 2px 0 2px 12px; margin: 0 0 18px;
        color: #4a4d54; font-size: 14px; max-width: 78ch; }
.cols { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; align-items: start; }
@media (max-width: 860px) { .cols { grid-template-columns: 1fr; } }
.cell h3 { font: 500 11px/1 ui-monospace, monospace; letter-spacing: .1em;
           text-transform: uppercase; color: #5b6069; margin: 0 0 8px; }
.plate { background: #fff; border: 1px solid #e3e2dd; border-radius: 4px;
         padding: 14px; overflow-x: auto; }
.plate svg { display: block; width: 100%; height: auto; }
.missing, .failed { color: #5b6069; font-size: 14px; padding: 20px 14px;
                    border: 1px dashed #cfcec8; border-radius: 4px; }
.failed { color: #8a3b1e; border-color: #d8b3a2; white-space: pre-wrap; }
"""


def render_page(found: list[Pair]) -> str:
    drawn = sum(1 for pair in found if pair.new)
    parts = [
        "<!doctype html><meta charset='utf-8'>",
        "<title>drawspec — the corpus, old against new</title>",
        f"<style>{STYLE}</style>",
        "<div class=wrap><header>",
        "<div class=count>drawspec &middot; corpus comparison</div>",
        "<h1>Old against new</h1>",
        "<p class=lede>Each hand-drawn original from the temario beside the drawing "
        "drawspec makes from a declarative document. A redraw is not a tracing: the "
        "originals have known defects, which is the reason for replacing them, so the "
        "reviewer's own note on each one is printed underneath and the pair should be "
        "judged against it.</p>",
        f"<p class=count>{drawn} redrawn</p>",
        "</header>",
    ]
    for pair in found:
        old = (
            f"<div class=plate>{pair.old}</div>"
            if pair.old
            else "<p class=missing>The originals are gitignored study material and are "
            "not in this checkout.</p>"
        )
        if pair.new:
            new = f"<div class=plate>{pair.new}</div>"
        else:
            new = f"<p class=failed>{escape(pair.failure)}</p>"
        note = f"<p class=note>{escape(pair.note)}</p>" if pair.note else ""
        kind = f"<span class=kind>{escape(pair.wants)}</span>" if pair.wants else ""
        parts.append(
            f"<article><h2>{escape(pair.title)}{kind}</h2>"
            f"<p class=meta>{escape(pair.slug)}</p>{note}"
            f"<div class=cols>"
            f"<div class=cell><h3>The original</h3>{old}</div>"
            f"<div class=cell><h3>drawspec</h3>{new}</div>"
            f"</div></article>"
        )
    parts.append("</div>")
    return "\n".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report only, write nothing")
    arguments = parser.parse_args(argv)

    found = pairs()
    failed = [pair for pair in found if pair.failure]
    for pair in found:
        state = pair.failure or ("drawn" if pair.new else "?")
        print(f"{pair.slug:52} {pair.wants:10} {state}")
    print(f"\n{len(found)} redrawn, {len(failed)} failing")

    if not arguments.check:
        CORPUS.mkdir(parents=True, exist_ok=True)
        PAGE.write_text(render_page(found), encoding="utf-8")
        print(PAGE)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

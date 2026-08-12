"""T0 — the gallery: render every reference document and look at it.

There is no gate here about how anything *looks* — that judgement is a human's,
and this task exists to put the work in front of one. What is asserted is that
the gallery keeps working while the tool is half built, because a gallery that
breaks on the first unimplemented kind is a gallery nobody runs, and then nobody
looks.

The one substantive check is the shared page. Every diagram is inlined into one
HTML document, which is the real test of the inline promise: two diagrams on one
page, no colliding ids, no leaked style.
"""

from __future__ import annotations

import re
from pathlib import Path

import gallery
import pytest

from drawspec.schema import KINDS, load_document

ENTRIES = gallery.build()


def test_gallery_covers_every_kind_in_the_vocabulary() -> None:
    """A kind with no reference document never gets looked at."""
    kinds = {load_document(path).kind for path in gallery.reference_documents()}
    assert kinds == set(KINDS)


def test_gallery_renders_every_reference_document_it_can() -> None:
    drawn = {entry.name for entry in ENTRIES if entry.rendered}
    assert drawn, "nothing rendered at all"
    for entry in ENTRIES:
        assert entry.rendered or entry.skipped, entry.name


def test_gallery_now_renders_every_reference_document() -> None:
    """T11 was the last family. Nothing in the reference set is skipped.

    The skip path itself is still exercised — by the FitError test below, which
    is the shape a skip takes now that every kind has a renderer.
    """
    assert [entry.name for entry in ENTRIES if not entry.rendered] == []


def test_gallery_reports_a_fiterror_with_its_message_rather_than_crashing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refusal is an outcome. Its message is the product, so it goes on the page."""
    impossible = tmp_path / "impossible.json"
    impossible.write_text(
        '{"version": 1, "kind": "columns", "width": 200,'
        ' "items": [{"text": "Before"}, {"text": "Afterwards"}, {"text": "Difference"}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(gallery, "reference_documents", lambda: [impossible])

    entries = gallery.build()
    assert len(entries) == 1
    assert not entries[0].rendered
    assert entries[0].skipped.startswith("FitError")
    assert "restructure" in entries[0].skipped
    # And it survives being put on the page.
    assert "FitError" in gallery.page(entries, "inline")


def test_gallery_page_holds_every_rendered_diagram_with_no_duplicate_ids() -> None:
    """The inline promise, on a real page with several diagrams on it."""
    html = gallery.page(ENTRIES, "inline")
    assert html.count("<svg") == sum(entry.rendered for entry in ENTRIES)

    identifiers = re.findall(r'\bid="([^"]*)"', html)
    assert identifiers
    assert len(identifiers) == len(set(identifiers))


def test_gallery_page_leaks_no_style_from_a_diagram() -> None:
    """The page has one <style>, its own. No diagram contributes another."""
    html = gallery.page(ENTRIES, "inline")
    assert html.count("<style") == 1


def test_gallery_page_names_every_document_and_its_kind() -> None:
    html = gallery.page(ENTRIES, "inline")
    for entry in ENTRIES:
        assert entry.name in html
        assert entry.kind in html


def test_gallery_escapes_a_skip_message_into_the_page() -> None:
    entry = gallery.Entry(name="x", kind="flow", skipped="a < b & c")
    assert "a &lt; b &amp; c" in gallery.page([entry], "inline")


@pytest.mark.parametrize("profile", ["inline", "standalone"])
def test_gallery_builds_in_both_profiles(profile: str) -> None:
    entries = gallery.build(profile)
    assert any(entry.rendered for entry in entries)


def test_gallery_check_mode_writes_nothing_and_succeeds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(gallery, "GALLERY_DIR", tmp_path / "gallery")
    monkeypatch.setattr(gallery, "PAGE", tmp_path / "gallery" / "index.html")
    assert gallery.main(["--check"]) == 0
    assert not (tmp_path / "gallery").exists()


def test_gallery_writes_the_page_and_one_svg_per_rendered_document(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    out = tmp_path / "gallery"
    monkeypatch.setattr(gallery, "GALLERY_DIR", out)
    monkeypatch.setattr(gallery, "PAGE", out / "index.html")
    assert gallery.main([]) == 0
    assert (out / "index.html").is_file()
    assert len(list(out.glob("*.svg"))) == sum(entry.rendered for entry in ENTRIES)


def test_gallery_report_names_every_document() -> None:
    text = gallery.report(ENTRIES)
    for entry in ENTRIES:
        assert entry.name in text

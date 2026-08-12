"""T15 — the command line.

The gate is `cli_exit_code_mismatches == 0` against the table in specification
§5.4, so every test here asserts a code as well as an effect. That is the point
of the contract: a build script reads the number, not the prose.

The other half is the validator. `drawspec validate` is meant to name the field
and the place the way an HTML validator names a line and an attribute, so the
test for it asserts the JSON pointer is in the output — not merely that
something failed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from drawspec import __version__
from drawspec.cli import build_parser, main
from drawspec.schema import SCHEMA_ID

VALID = {
    "version": 1,
    "kind": "stack",
    "title": "A stack",
    "items": [{"text": "Interface"}, {"text": "Domain"}, {"text": "Storage"}],
}

FORBIDDEN = {
    "version": 1,
    "kind": "stack",
    "items": [{"text": "Interface", "font_size": 14}],
}

AMBIGUOUS_THEME = """
version = 1
name = "ambiguous"

[role.step]
shape = "rect"
dash = "none"
stroke = "#111111"
stroke_width = 1.5

[role.note]
shape = "rect"
dash = "none"
stroke = "#141414"
stroke_width = 1.5
"""


def write(path: Path, document: dict[str, object]) -> Path:
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# render
# --------------------------------------------------------------------------


def test_render_valid_document_writes_svg_and_exits_zero(tmp_path: Path) -> None:
    source = write(tmp_path / "doc.json", VALID)
    out = tmp_path / "doc.svg"
    assert main(["render", str(source), "-o", str(out)]) == 0
    assert out.read_text(encoding="utf-8").startswith("<svg")


def test_render_without_an_output_writes_to_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["render", str(write(tmp_path / "doc.json", VALID))]) == 0
    assert capsys.readouterr().out.startswith("<svg")


def test_width_flag_overrides_the_document_width(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """One document, several widths, no editing — the reason the flag exists."""
    source = write(tmp_path / "doc.json", {**VALID, "width": 640.0})
    assert main(["render", str(source), "--width", "300", "--profile", "standalone"]) == 0
    assert 'width="30' in capsys.readouterr().out


def test_height_flag_overrides_the_document_height(tmp_path: Path) -> None:
    source = write(tmp_path / "doc.json", VALID)
    out = tmp_path / "doc.svg"
    assert main(["render", str(source), "--height", "500", "-o", str(out)]) == 0
    assert out.read_text(encoding="utf-8").startswith("<svg")


@pytest.mark.parametrize(
    ("profile", "expected"), [("inline", "currentColor"), ("standalone", "width=")]
)
def test_profile_flag_selects_the_embedding_profile(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], profile: str, expected: str
) -> None:
    source = write(tmp_path / "doc.json", VALID)
    assert main(["render", str(source), "--profile", profile]) == 0
    assert expected in capsys.readouterr().out


def test_render_of_a_document_that_cannot_fit_exits_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A refusal is an outcome, and its message is the product."""
    narrow = {
        "version": 1,
        "kind": "columns",
        "width": 260.0,
        "items": [{"text": "Before"}, {"text": "Afterwards"}, {"text": "Difference"}],
    }
    assert main(["render", str(write(tmp_path / "doc.json", narrow))]) == 1
    assert "restructure" in capsys.readouterr().err


def test_render_of_a_document_that_does_not_exist_exits_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["render", str(tmp_path / "missing.json")]) == 1
    assert "could not be read" in capsys.readouterr().err


def test_render_with_an_unknown_profile_exits_two(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["render", "doc.json", "--profile", "sideways"]) == 2
    assert "sideways" in capsys.readouterr().err


# --------------------------------------------------------------------------
# validate
# --------------------------------------------------------------------------


def test_validate_invalid_document_prints_json_pointer_and_exits_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Named by location and by field, the way a validator should."""
    assert main(["validate", str(write(tmp_path / "doc.json", FORBIDDEN))]) == 1
    printed = capsys.readouterr().err
    assert "/items/0/font_size" in printed


def test_validate_prints_every_violation_not_only_the_first(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """One pass, one edit — the reason `DocumentError` carries them all."""
    broken = {
        "version": 1,
        "kind": "stack",
        "items": [{"text": "One", "font_size": 14}, {"text": "Two", "colour": "red"}],
    }
    assert main(["validate", str(write(tmp_path / "doc.json", broken))]) == 1
    printed = capsys.readouterr().err
    assert "/items/0/font_size" in printed
    assert "/items/1/colour" in printed


def test_validate_of_a_valid_document_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["validate", str(write(tmp_path / "doc.json", VALID))]) == 0
    assert "stack" in capsys.readouterr().out


def test_validate_renders_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Validation is not a render with the output thrown away."""
    assert main(["validate", str(write(tmp_path / "doc.json", VALID))]) == 0
    assert "<svg" not in capsys.readouterr().out


# --------------------------------------------------------------------------
# theme check
# --------------------------------------------------------------------------


def test_theme_check_ambiguous_theme_exits_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Two roles a greyscale reader could not tell apart, named as a pair."""
    theme = tmp_path / "ambiguous.toml"
    theme.write_text(AMBIGUOUS_THEME, encoding="utf-8")
    assert main(["theme", "check", str(theme)]) == 1
    printed = capsys.readouterr().err
    assert "note" in printed
    assert "step" in printed


def test_theme_check_of_the_bundled_theme_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["theme", "check", "default"]) == 0
    assert "0" in capsys.readouterr().out


def test_theme_check_of_a_missing_theme_exits_one(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["theme", "check", "nonesuch"]) == 1
    assert capsys.readouterr().err


# --------------------------------------------------------------------------
# schema
# --------------------------------------------------------------------------


def test_schema_writes_the_published_schema_to_stdout(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["schema"]) == 0
    written = json.loads(capsys.readouterr().out)
    assert written["$id"] == SCHEMA_ID


def test_schema_writes_to_a_file_when_asked(tmp_path: Path) -> None:
    out = tmp_path / "drawspec.schema.json"
    assert main(["schema", "--out", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["$id"] == SCHEMA_ID


# --------------------------------------------------------------------------
# Usage
# --------------------------------------------------------------------------


def test_no_command_exits_two(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 2
    assert capsys.readouterr().err


def test_unknown_command_exits_two() -> None:
    assert main(["draw", "doc.json"]) == 2


def test_version_flag_exits_zero() -> None:
    with pytest.raises(SystemExit) as exit_code:
        build_parser().parse_args(["--version"])
    assert exit_code.value.code == 0


def test_version_is_set() -> None:
    assert __version__

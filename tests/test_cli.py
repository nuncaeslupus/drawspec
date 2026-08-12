"""Scaffold-level checks: the package imports and the entry point runs."""

from __future__ import annotations

import pytest

from drawspec import __version__
from drawspec.cli import build_parser, main


def test_version_is_set() -> None:
    assert __version__


def test_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "drawspec" in capsys.readouterr().out


def test_version_flag_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["--version"])
    assert exc.value.code == 0

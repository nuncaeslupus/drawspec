"""What the built distribution promises, checked against the built distribution.

Everything here is a claim that is true in the repository and can quietly stop
being true in the wheel, which is the only copy anyone else ever sees. The
project runs mypy with `disallow_untyped_defs` over the whole source tree and
passes clean — and until `py.typed` shipped, none of that reached a consumer:
PEP 561 says a checker must treat a package without the marker as untyped, so
every `render_document(...)` in their code was `Any`. The strictness was real and
the benefit was zero, with nothing anywhere to say so.

The metadata checks are the same shape. `keywords` and `classifiers` do nothing
in the repository and are the whole of a package's discoverability on PyPI, so
they are exactly the kind of thing that gets dropped in a refactor and noticed by
nobody.

Building a wheel is slower than the rest of the suite, so it happens once and the
result is shared.
"""

from __future__ import annotations

import re
import subprocess
import tomllib
import zipfile
from pathlib import Path
from typing import Any

import pytest

import drawspec

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def wheel_names(tmp_path_factory: pytest.TempPathFactory) -> frozenset[str]:
    """Every path inside a freshly built wheel.

    Built into a temporary directory rather than the repository's own `dist/`,
    so running the suite never leaves an artefact behind that a later release
    could pick up by mistake — a stale `dist/` is one of the two classic
    release-day failures.
    """
    out = tmp_path_factory.mktemp("wheel")
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(out)],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    built = sorted(out.glob("drawspec-*.whl"))
    assert built, f"no wheel was produced in {out}"
    with zipfile.ZipFile(built[-1]) as archive:
        return frozenset(archive.namelist())


@pytest.fixture(scope="module")
def project() -> dict[str, Any]:
    parsed = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    section = parsed["project"]
    assert isinstance(section, dict)
    return section


def test_the_marker_that_makes_the_strict_build_worth_something_is_in_the_wheel(
    wheel_names: frozenset[str],
) -> None:
    """Without `py.typed`, a consumer's checker sees `Any` and nothing says why."""
    assert "drawspec/py.typed" in wheel_names


def test_the_published_schema_travels_with_the_package(wheel_names: frozenset[str]) -> None:
    """`force-include` is easy to lose; the schema is how an editor completes."""
    assert "drawspec/schemas/drawspec-v1.schema.json" in wheel_names


def test_the_version_agrees_in_both_places_it_is_written(project: dict[str, Any]) -> None:
    """The other classic release-day failure: a tag against a stale `__version__`."""
    assert drawspec.__version__ == project["version"]


def test_the_metadata_a_stranger_finds_the_package_by_is_present(
    project: dict[str, Any],
) -> None:
    for field in ("keywords", "classifiers", "urls", "authors"):
        assert project.get(field), f"[project] {field} is missing or empty"


def test_every_url_a_pypi_sidebar_offers_is_declared(project: dict[str, Any]) -> None:
    urls = {key.lower() for key in project["urls"]}
    assert {"homepage", "documentation", "repository", "issues"} <= urls


def test_the_typed_classifier_is_only_claimed_while_the_marker_exists(
    project: dict[str, Any],
) -> None:
    """`Typing :: Typed` on a package with no marker is a promise to a checker
    that the checker will not believe — and PyPI shows the badge either way."""
    classifiers = project["classifiers"]
    assert isinstance(classifiers, list)
    if any(str(item).startswith("Typing ::") for item in classifiers):
        assert (ROOT / "src" / "drawspec" / "py.typed").exists()


def test_the_declared_python_floor_matches_the_versions_that_are_classified(
    project: dict[str, Any],
) -> None:
    """A classifier list that drifts from `requires-python` sends installers on
    3.11 to a release that cannot run, which pip reports as a resolution error
    rather than as the version mismatch it is."""
    floor = str(project["requires-python"])
    minimum = re.search(r"(\d+)\.(\d+)", floor)
    assert minimum is not None, floor
    classifiers = project["classifiers"]
    assert isinstance(classifiers, list)
    versions = {
        item.rsplit(" :: ", 1)[-1]
        for item in (str(entry) for entry in classifiers)
        if item.startswith("Programming Language :: Python :: ") and item[-1].isdigit()
    }
    assert f"{minimum.group(1)}.{minimum.group(2)}" in versions, (
        f"requires-python is {floor} but the classifiers list {sorted(versions)}"
    )


def test_every_bundled_resource_the_code_reaches_for_by_path_is_in_the_wheel(
    wheel_names: frozenset[str],
) -> None:
    """Themes and fonts, which are found relative to `__file__` at runtime.

    `theme._THEMES_DIR` and `text.fontlib._FONTS_DIR` both resolve against the
    installed package, so a packaging change that dropped either directory would
    build a wheel that installs cleanly and then fails on the first render —
    `load_theme()` with no default to load, or a measurer with no faces. The
    suite would not notice, because it runs against the source tree where the
    files are always there.

    Derived from what is on disk rather than from a list, so a new theme or a
    new face is covered the day it is added.
    """
    expected = {
        f"drawspec/{directory}/{path.name}"
        for directory, pattern in (("themes", "*.toml"), ("fonts", "*.ttf"))
        for path in (ROOT / "src" / "drawspec" / directory).glob(pattern)
    }
    assert expected, "no bundled themes or fonts were found in the source tree"
    missing = sorted(expected - wheel_names)
    assert not missing, f"the wheel is missing bundled resources: {missing}"

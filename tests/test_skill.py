"""`skills/drawspec/SKILL.md` names only commands that exist.

The skill is a pointer, not a copy of the format, so the only way it can drift
is by naming a command, a flag or an MCP tool the tool no longer has. An agent
following it would then fail on its first step, which is the worst place to.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from drawspec.cli import build_parser

SKILL = Path(__file__).resolve().parents[1] / "skills" / "drawspec" / "SKILL.md"
TEXT = SKILL.read_text(encoding="utf-8")


def subcommands() -> dict[str, argparse.ArgumentParser]:
    parser = build_parser()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    raise AssertionError("the CLI has no subcommands")


def test_front_matter_carries_a_name_and_a_description_with_its_limits() -> None:
    match = re.match(r"---\n(.*?)\n---\n", TEXT, re.DOTALL)
    assert match, "SKILL.md must open with YAML front matter"
    fields = dict(line.split(": ", 1) for line in match.group(1).splitlines())
    assert fields["name"] == "drawspec"
    assert "Use when" in fields["description"]
    assert "Do NOT use" in fields["description"]


def test_every_command_and_flag_the_skill_names_exists() -> None:
    commands = subcommands()
    invocations = re.findall(r"`drawspec ([a-z]+)([^`]*)`", TEXT)
    assert invocations, "the skill names no command, so nothing pins it to the CLI"
    for name, rest in invocations:
        assert name in commands, f"SKILL.md names `drawspec {name}`, which does not exist"
        known = {flag for action in commands[name]._actions for flag in action.option_strings}
        for flag in re.findall(r"(?<!\S)(--?[a-z][a-z-]*)", rest):
            assert flag in known, f"SKILL.md names `drawspec {name} {flag}`, which does not exist"


def test_every_mcp_tool_the_skill_names_exists() -> None:
    source = (Path(__file__).resolve().parents[1] / "src" / "drawspec" / "mcp.py").read_text(
        encoding="utf-8"
    )
    served = set(re.findall(r'name="([a-z_]+)"', source))
    for tool in ("list_kinds", "get_example", "get_schema", "validate_document", "render_document"):
        assert tool in served
        assert f"`{tool}`" in TEXT

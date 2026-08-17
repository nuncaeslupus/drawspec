"""One sentence and one minimal document per kind, for `drawspec kinds` / `example`.

**Who this is for.** An agent that has drawspec installed and not its
documentation. `--help` lists the commands and says nothing about what a document
looks like; `drawspec schema` emits the full JSON Schema, which is the right
artefact for an editor and thirty thousand characters of the wrong one for a
preamble. These two commands sit in the gap: what are the kinds, and what does
one of them look like.

**Minimal means minimal.** Each document here is the fewest fields that render —
no `title`, no `description`, no roles beyond what the shape needs. That is the
opposite of `docs/reference/`, whose documents are deliberately full so the
gallery exercises the hard cases, and it is why these are not simply those. An
example a reader has to trim before they understand it has failed at the one job
it has.

**They are checked.** `tests/test_cli.py` renders every one of them, so a field
that changes shape breaks this file rather than surfacing as an example that no
longer works — the same arrangement the generated references have.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

#: What each kind is *for*, in one line. Phrased as the claim the diagram makes,
#: because that is the axis an author chooses on: the mistake is picking a shape
#: that looks right rather than one that says the right thing.
PURPOSE: Final[Mapping[str, str]] = {
    "flow": "steps with branching; a process that can merge and loop back",
    "tree": "a hierarchy; one parent per child",
    "cycle": "a loop that returns to where it started, through every step",
    "stack": "ordered layers, read down",
    "timeline": "events along time, with what happened above the line and when below",
    "columns": "side-by-side comparison",
    "matrix": "rows against columns, with cells that may span",
    "pyramid": "levels where size means quantity or rank",
    "rings": "nested scopes, concentric",
    "funnel": "narrowing stages, with named thresholds between them",
    "chart": "a small number you already know — not for exploring data",
    "quadrant": "items placed against two named axes",
    "curve": "a named shape with labelled waypoints",
}

#: The smallest document of each kind that renders.
EXAMPLES: Final[Mapping[str, Mapping[str, Any]]] = {
    "flow": {
        "version": 1,
        "kind": "flow",
        "nodes": [
            {"id": "start", "text": "A report arrives", "role": "start"},
            {"id": "ask", "text": "Does it reproduce?", "role": "decision"},
            {"id": "fix", "text": "Schedule a fix"},
        ],
        "edges": [
            {"from": "start", "to": "ask"},
            {"from": "ask", "to": "fix", "label": "yes"},
        ],
    },
    "tree": {
        "version": 1,
        "kind": "tree",
        "nodes": [
            {"id": "root", "text": "The service"},
            {"id": "api", "text": "Its API"},
            {"id": "store", "text": "Its store"},
        ],
        "edges": [
            {"from": "root", "to": "api"},
            {"from": "root", "to": "store"},
        ],
    },
    # A cycle is refused unless the edges close one loop through every node, so
    # the minimum is a full ring rather than a chain.
    "cycle": {
        "version": 1,
        "kind": "cycle",
        "nodes": [
            {"id": "plan", "text": "Plan"},
            {"id": "build", "text": "Build"},
            {"id": "learn", "text": "Learn"},
        ],
        "edges": [
            {"from": "plan", "to": "build"},
            {"from": "build", "to": "learn"},
            {"from": "learn", "to": "plan"},
        ],
    },
    "stack": {
        "version": 1,
        "kind": "stack",
        "items": [
            {"text": "What the reader sees"},
            {"text": "What decides it"},
            {"text": "What it is stored in"},
        ],
    },
    "timeline": {
        "version": 1,
        "kind": "timeline",
        "items": [
            {"text": "Brief", "note": "March"},
            {"text": "Plan", "note": "May"},
            {"text": "Built", "note": "August"},
        ],
    },
    "columns": {
        "version": 1,
        "kind": "columns",
        "items": [
            {"text": "Before"},
            {"text": "After"},
            {"text": "What changed"},
        ],
    },
    "matrix": {
        "version": 1,
        "kind": "matrix",
        "columns": ["Likely", "Unlikely"],
        "rows": ["Severe", "Minor"],
        "cells": [
            {"text": "Fix now", "column": 0, "row": 0},
            {"text": "Watch", "column": 1, "row": 0},
            {"text": "Schedule", "column": 0, "row": 1},
            {"text": "Accept", "column": 1, "row": 1},
        ],
    },
    "pyramid": {
        "version": 1,
        "kind": "pyramid",
        "levels": [
            {"text": "The few that decide"},
            {"text": "The several that shape"},
            {"text": "The many that are affected"},
        ],
    },
    "rings": {
        "version": 1,
        "kind": "rings",
        "rings": [
            {"text": "What we control"},
            {"text": "What we influence"},
            {"text": "What we only observe"},
        ],
    },
    "funnel": {
        "version": 1,
        "kind": "funnel",
        "stages": [
            {"text": "Everyone who arrived", "gate": "signed up"},
            {"text": "Everyone who tried it", "gate": "came back"},
            {"text": "Everyone who stayed"},
        ],
    },
    "chart": {
        "version": 1,
        "kind": "chart",
        "axes": {
            "horizontal": {"label": "Quarter", "min": 0, "max": 4},
            "vertical": {"label": "Incidents"},
        },
        "series": [
            {"name": "Reported", "mark": "bar", "data": [[1, 34], [2, 41], [3, 28]]},
        ],
    },
    "quadrant": {
        "version": 1,
        "kind": "quadrant",
        "axes": {
            "horizontal": {"label": "Effort"},
            "vertical": {"label": "Value"},
        },
        "positions": [
            {"text": "Do this first", "across": 0.2, "up": 0.8},
            {"text": "Do this if there is time", "across": 0.8, "up": 0.7},
            {"text": "Do not", "across": 0.8, "up": 0.2},
        ],
    },
    "curve": {
        "version": 1,
        "kind": "curve",
        "axes": {
            "horizontal": {"label": "Time"},
            "vertical": {"label": "Attention"},
        },
        "curves": [
            {
                "name": "Interest",
                "waypoints": [
                    {"across": 0.0, "up": 0.1},
                    {"across": 0.3, "up": 0.9, "text": "The peak"},
                    {"across": 1.0, "up": 0.4},
                ],
            }
        ],
    },
}


__all__ = ["EXAMPLES", "PURPOSE"]

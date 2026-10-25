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
    "tree": "a hierarchy; one parent per child — or, as a bracket, a knockout draw or a cladogram",
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
    "scatter": "points placed by two measured values — a quadrant with real ticks",
    "curve": "a named shape with labelled waypoints",
    "files": "a directory listing — folders and files from their paths",
    "states": "a state machine — the conditions something is in, and the events that move it",
    "sequence": "who says what to whom, in order — messages between participants, read down",
    "lanes": "a flow whose actors are swimlanes — the hand-offs between parties are the point",
    "entities": "a data model, schema or class diagram — boxes of fields, relations between them",
    "gantt": "a plan — one row per task, each an interval on a numbered axis; no dates",
    "board": "cards sorted into columns — a kanban board, a retrospective, a story map",
    "fishbone": "one effect and its causes by category — a root-cause (Ishikawa) diagram",
    "venn": "two to four overlapping sets — what each holds alone, and what they share",
    "journey": "one person's feeling across the stages of an experience — a journey map",
    "treemap": "the parts of one known total, each by its area — a few proportions, stated",
    "sankey": "where a known quantity goes — bands as thick as the amounts, a few flows stated",
    "numberline": "values and ranges on one scale, each end in or out — an inequality, a spectrum",
    "barmodel": "a word problem as bars of parts in proportion, braced — the tape diagram",
    "pie": "the shares of one known total as labelled sectors — a few proportions, stated",
    "waterfall": "from one total to another, step by step, subtotals checked — the bridge chart",
    "mindmap": "a topic in the middle, its branches as peers round it — revision notes, a plan",
    "argument": "a claim, the reasons for it and the objections, by stance — an argument map",
    "familytree": "people, couples and their children by generation — a family tree or pedigree",
    "meter": "one amount against its scale — a progress bar, a thermometer, a dial, a bullet",
    "rag": "workstreams or risks rated red, amber or green, in words and shapes — a status report",
    "clock": "analogue clock faces showing a time, for teaching it — quarter past, half past",
    "sunburst": "a hierarchy as concentric rings of sectors, read from the middle outward",
    "network": "networks as buses with the hosts on them between — a DMZ, an office LAN",
    "timing": "signals over one time axis — clocks, levels, buses, states: an SPI figure",
    "gitgraph": "commits on branches over time, with forks, merges, tags and cherry-picks",
    "railroad": "a grammar's rules as syntax diagrams — tracks through keywords, choices and loops",
    "usecase": "who uses a system for what — UML actors, use cases, «include» and «extend»",
    "packet": "a protocol header or a register as bit fields in rows, under a bit ruler",
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
    "files": {
        "version": 1,
        "kind": "files",
        "root": "project",
        "entries": [
            {"path": "src/main.py", "note": "entry point"},
            {"path": "src/..."},
            {"path": "tests/"},
            {"path": "README.md"},
        ],
    },
    "states": {
        "version": 1,
        "kind": "states",
        "initial": "off",
        "states": [
            {"id": "off", "text": "Off"},
            {"id": "on", "text": "On"},
        ],
        "transitions": [
            {"from": "off", "to": "on", "event": "switch pressed"},
            {"from": "on", "to": "off", "event": "switch pressed"},
        ],
    },
    "sequence": {
        "version": 1,
        "kind": "sequence",
        "participants": [
            {"id": "browser", "text": "Browser"},
            {"id": "server", "text": "Server"},
        ],
        "messages": [
            {"from": "browser", "to": "server", "text": "GET /"},
            {"from": "server", "to": "browser", "text": "the page", "role": "weak"},
        ],
    },
    "lanes": {
        "version": 1,
        "kind": "lanes",
        "nodes": [
            {"id": "ask", "text": "Asks for access", "actor": "Requester"},
            {"id": "grant", "text": "Grants it", "actor": "Owner"},
        ],
        "edges": [{"from": "ask", "to": "grant"}],
    },
    "entities": {
        "version": 1,
        "kind": "entities",
        "entities": [
            {"id": "author", "text": "Author", "fields": [{"text": "name", "key": "primary"}]},
            {"id": "book", "text": "Book", "fields": [{"text": "title"}, {"text": "year"}]},
        ],
        "edges": [{"from": "author", "to": "book", "from_end": "one", "to_end": "one-or-many"}],
    },
    "gantt": {
        "version": 1,
        "kind": "gantt",
        "axis": {"label": "Week"},
        "tasks": [
            {"id": "build", "text": "Build it", "start": 0, "end": 3},
            {"id": "ship", "text": "Ship it", "at": 3},
        ],
        "edges": [{"from": "build", "to": "ship"}],
    },
    "board": {
        "version": 1,
        "kind": "board",
        "columns": [
            {"id": "todo", "text": "To do"},
            {"id": "doing", "text": "Doing", "limit": 2},
            {"id": "done", "text": "Done"},
        ],
        "cards": [
            {"text": "Write the tests", "column": "doing"},
            {"text": "Draft the guide", "column": "todo"},
        ],
    },
    "fishbone": {
        "version": 1,
        "kind": "fishbone",
        "effect": {"text": "The build is slow"},
        "categories": [
            {"text": "Code", "causes": [{"text": "No incremental compile"}]},
            {"text": "Machines", "causes": [{"text": "Runners share one disk"}]},
        ],
    },
    "venn": {
        "version": 1,
        "kind": "venn",
        "sets": [{"id": "a", "text": "Cats"}, {"id": "b", "text": "Dogs"}],
        "regions": [{"in": ["a", "b"], "text": "Pets"}],
    },
    "journey": {
        "version": 1,
        "kind": "journey",
        "feelings": ["unhappy", "happy"],
        "stages": [
            {"text": "Orders", "feeling": "happy"},
            {"text": "Waits", "feeling": "unhappy"},
        ],
    },
    "treemap": {
        "version": 1,
        "kind": "treemap",
        "parts": [{"text": "Rent", "amount": 60}, {"text": "Food", "amount": 40}],
    },
    "sankey": {
        "version": 1,
        "kind": "sankey",
        "nodes": [{"id": "pay", "text": "Pay"}, {"id": "rent", "text": "Rent"}],
        "flows": [{"from": "pay", "to": "rent", "amount": 60}],
    },
    "numberline": {
        "version": 1,
        "kind": "numberline",
        "axis": {"min": -5, "max": 5},
        "ranges": [{"from": -2, "to": 3, "to_open": True, "text": "\N{MINUS SIGN}2 ≤ x < 3"}],
    },
    "barmodel": {
        "version": 1,
        "kind": "barmodel",
        "bars": [{"parts": [{"amount": 12}, {"amount": 18, "text": "?"}]}],
    },
    "pie": {
        "version": 1,
        "kind": "pie",
        "unit": "pupils",
        "parts": [{"text": "Walk", "amount": 12}, {"text": "Bus", "amount": 18}],
    },
    "waterfall": {
        "version": 1,
        "kind": "waterfall",
        "axis": {"label": "Cash, £"},
        "bars": [
            {"text": "Opening", "total": 120},
            {"text": "Sales", "amount": 45},
            {"text": "Rent", "amount": -60},
            {"text": "Closing", "total": 105},
        ],
    },
    "mindmap": {
        "version": 1,
        "kind": "mindmap",
        "centre": "The move",
        "branches": [
            {"text": "Before", "branches": [{"text": "Book the van"}]},
            {"text": "After", "branches": [{"text": "Unpack the kitchen"}]},
        ],
    },
    "argument": {
        "version": 1,
        "kind": "argument",
        "claim": "Cycle to work",
        "points": [
            {"id": "fit", "on": "claim", "stance": "for", "text": "It keeps me fit"},
            {"id": "rain", "on": "claim", "stance": "against", "text": "It often rains"},
        ],
    },
    "familytree": {
        "version": 1,
        "kind": "familytree",
        "people": [
            {"id": "mum", "sex": "female"},
            {"id": "dad", "sex": "male"},
            {"id": "kid", "sex": "unknown"},
        ],
        "couples": [{"between": ["mum", "dad"], "children": ["kid"]}],
    },
    "meter": {
        "version": 1,
        "kind": "meter",
        "meters": [{"text": "Chapters drafted", "amount": 7, "max": 12, "unit": "chapters"}],
    },
    "clock": {
        "version": 1,
        "kind": "clock",
        "clocks": [{"time": "3:15"}],
    },
    "gitgraph": {
        "version": 1,
        "kind": "gitgraph",
        "branches": [{"name": "main"}, {"name": "feature", "from": "main"}],
        "steps": [
            {"on": "main", "text": "Initial commit"},
            {"on": "feature", "text": "Add a feature"},
            {"on": "main", "merge": "feature", "tag": "v1.0"},
        ],
    },
    "railroad": {
        "version": 1,
        "kind": "railroad",
        "rules": [
            {
                "name": "list",
                "expr": {
                    "seq": [
                        {"terminal": "["},
                        {
                            "repeat": {"rule": "item"},
                            "separator": {"terminal": ","},
                            "min": 0,
                        },
                        {"terminal": "]"},
                    ]
                },
            }
        ],
        "external": ["item"],
    },
    "packet": {
        "version": 1,
        "kind": "packet",
        "bits_per_row": 16,
        "fields": [
            {"text": "Enable", "short": "EN", "bits": 1},
            {"text": "Mode", "bits": 3},
            {"text": "Count", "bits": 12},
        ],
    },
    "sunburst": {
        "version": 1,
        "kind": "sunburst",
        "centre": "Feelings",
        "nodes": [
            {"text": "Angry", "children": [{"text": "Hurt"}, {"text": "Mad"}]},
            {"text": "Happy", "children": [{"text": "Proud"}, {"text": "Playful"}]},
        ],
    },
    "network": {
        "version": 1,
        "kind": "network",
        "networks": [
            {"id": "dmz", "address": "210.x.x.x/24"},
            {"id": "internal", "address": "172.x.x.x/24"},
        ],
        "hosts": [
            {
                "id": "web01",
                "networks": [
                    {"network": "dmz", "address": ".1"},
                    {"network": "internal", "address": ".1"},
                ],
            },
            {"id": "db01", "role": "store", "networks": [{"network": "internal", "address": ".2"}]},
        ],
    },
    "timing": {
        "version": 1,
        "kind": "timing",
        "signals": [
            {"text": "CLK", "values": ["p", ".", ".", "."]},
            {"text": "DATA", "lane": "bus", "values": ["x", "A1", "B2", "z"]},
        ],
    },
    "usecase": {
        "version": 1,
        "kind": "usecase",
        "systems": [{"id": "atm", "text": "ATM"}],
        "actors": [{"id": "customer", "text": "Customer"}],
        "usecases": [{"id": "withdraw", "text": "Withdraw cash"}],
        "edges": [{"from": "customer", "to": "withdraw"}],
    },
    "rag": {
        "version": 1,
        "kind": "rag",
        "rows": [{"text": "Data migration", "rag": "amber", "trend": "worse"}],
    },
    "scatter": {
        "version": 1,
        "kind": "scatter",
        "axes": {
            "horizontal": {"label": "Cost"},
            "vertical": {"label": "Impact"},
        },
        "positions": [
            {"text": "Cache the slow query", "across": 1, "up": 6},
            {"text": "Migrate the database", "across": 9, "up": 4},
            {"text": "Ship the mobile app", "across": 7, "up": 8},
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
